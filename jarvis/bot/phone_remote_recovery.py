"""Closed, offline-only recovery journal primitives for phone authority.

This module deliberately has no default filesystem root, anchor client, owner
transport, service command, or restore invocation. Callers must inject a
disposable root and an authenticated owner capability. It is not wired to a
production controller or to deployment scripts.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import stat
import sqlite3
import math
import shutil
import struct
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

MAX_JOURNAL_BYTES = 65_536
MAX_DATABASE_BYTES = 1 << 30
MAX_MANIFEST_BYTES = 16_384
JOURNAL_NAME = "journal.json"
JOURNAL_TEMP = "journal.next.tmp"
JOURNAL_FIELDS = frozenset({
    "journal_version", "operation_id", "manifest_sha256", "phase",
    "rename_step", "files", "staged_database_sha256",
    "installed_database_sha256", "final_database_sha256", "cleanup_artifacts",
})
PHASES = (
    "checkpoint_bound", "staged", "quiesced", "installing", "installed",
    "database_committed", "database_finalized", "anchor_committed", "cleaning", "complete",
)
CLEANUP_NAMES = ("checkpoint", "staged_database", "old_database", "old_wal", "old_shm")
RENAME_ORDER = ("wal", "shm", "database", "staged_database")
HEX256 = re.compile(r"^[0-9a-f]{64}$")
MANIFEST_FIELDS = frozenset({
    "manifest_version", "operation_id", "host_id", "base_generation",
    "target_generation", "source_id", "source_schema_version",
    "source_size_bytes", "source_sha256", "checkpoint_size_bytes",
    "checkpoint_sha256", "authority_sha256", "base_database_sha256",
})
from jarvis.bot.phone_admission_store import RESTORE_RECEIPT_SQL as RECEIPT_DDL
PINNED_DDL_SHA256 = "c20e361bd2bea55869dcd330aa108c96b7edb6342400f5a3b4e06e4b942006d6"
PHONE_TABLES = frozenset({"phone_remote_meta", "phone_remote_devices", "phone_remote_grants",
                          "phone_remote_sessions", "phone_remote_restore_receipt"})
RESTORE_RECEIPT_COLUMNS = ("operation_id", "host_id", "target_generation", "manifest_sha256",
                           "checkpoint_sha256", "authority_sha256", "receipt_version")


def _receipt_row(db: sqlite3.Connection) -> tuple[Any, ...] | None:
    try:
        row = db.execute("SELECT " + ",".join(RESTORE_RECEIPT_COLUMNS)
            + " FROM phone_remote_restore_receipt WHERE singleton_id=1").fetchone()
    except sqlite3.Error as exc:
        raise RecoveryUnavailable("restore receipt is unavailable") from exc
    return None if row is None else tuple(row)


def _verify_expected_receipt(observed: tuple[Any, ...] | None,
                             expected: tuple[Any, ...] | None) -> None:
    if expected is not None and (type(expected) is not tuple or len(expected) != 7):
        raise RecoveryUnavailable("expected prior receipt is invalid")
    if observed != expected:
        raise RecoveryUnavailable("prior restore receipt differs from the protected checkpoint")


class RecoveryUnavailable(Exception):
    """Recovery state is ambiguous or outside the closed offline contract."""


def _pairs_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _uuid(value: object) -> bool:
    if type(value) is not str or len(value) != 36:
        return False
    try:
        return str(uuid.UUID(value)) == value
    except (ValueError, AttributeError):
        return False


def _digest(value: object, *, nullable: bool = False) -> bool:
    return (nullable and value is None) or (type(value) is str and HEX256.fullmatch(value) is not None)


def _exact_keys(value: object, expected: set[str] | frozenset[str]) -> bool:
    return type(value) is dict and value.keys() == expected


@dataclass(frozen=True)
class FileRecord:
    present: bool
    size_bytes: int
    sha256: str | None

    def as_json(self) -> dict[str, object]:
        return {"present": self.present, "size_bytes": self.size_bytes, "sha256": self.sha256}


def validate_manifest(value: object) -> dict[str, Any]:
    """Validate the canonical v1 restore manifest contract."""
    if not _exact_keys(value, MANIFEST_FIELDS):
        raise RecoveryUnavailable("invalid manifest fields")
    for field in ("manifest_version", "base_generation", "target_generation",
                  "source_schema_version", "source_size_bytes", "checkpoint_size_bytes"):
        if type(value[field]) is not int or not 0 <= value[field] < (1 << 64):
            raise RecoveryUnavailable("invalid manifest integer")
    if value["manifest_version"] != 1 or value["source_schema_version"] != 1:
        raise RecoveryUnavailable("unsupported manifest version")
    if value["base_generation"] >= (1 << 64) - 1 or value["target_generation"] != value["base_generation"] + 1:
        raise RecoveryUnavailable("invalid target generation")
    if not _uuid(value["operation_id"]):
        raise RecoveryUnavailable("invalid operation identifier")
    host_id = value["host_id"]
    source_id = value["source_id"]
    if (type(host_id) is not str or not host_id or len(host_id.encode("utf-8", "strict")) > 256
            or not _uuid(source_id)):
        raise RecoveryUnavailable("invalid manifest identity")
    if not (1 <= value["source_size_bytes"] <= MAX_DATABASE_BYTES
            and 1 <= value["checkpoint_size_bytes"] <= MAX_DATABASE_BYTES):
        raise RecoveryUnavailable("invalid manifest size")
    for field in ("source_sha256", "checkpoint_sha256", "authority_sha256", "base_database_sha256"):
        if not _digest(value[field]):
            raise RecoveryUnavailable("invalid manifest digest")
    return value


def encode_manifest(value: Mapping[str, Any]) -> bytes:
    """Encode canonical duplicate-free JSON and enforce the manifest byte cap."""
    data = json.dumps(validate_manifest(dict(value)), ensure_ascii=False, allow_nan=False,
                      sort_keys=True, separators=(",", ":")).encode("utf-8", "strict")
    if len(data) > MAX_MANIFEST_BYTES:
        raise RecoveryUnavailable("manifest exceeds size limit")
    return data


def decode_manifest(data: bytes) -> dict[str, Any]:
    if type(data) is not bytes or not 1 <= len(data) <= MAX_MANIFEST_BYTES:
        raise RecoveryUnavailable("invalid manifest size")
    try:
        value = json.loads(data.decode("utf-8", "strict"), object_pairs_hook=_pairs_no_duplicates,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError("constant")))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError) as exc:
        raise RecoveryUnavailable("invalid manifest encoding") from exc
    validated = validate_manifest(value)
    if encode_manifest(validated) != data:
        raise RecoveryUnavailable("manifest is not canonical")
    return validated


def validate_pending_anchor_v2(anchor: object, *, manifest_bytes: bytes,
                               checkpoint_sha256: str) -> dict[str, Any]:
    """Bind an exact pending protected-v2 value to its canonical manifest.

    This validates a value read by the injected/native owner; it does not read
    or write Keychain and does not treat a Python mapping as authenticated.
    """
    fields = {"anchor_version", "host_id", "host_generation", "transition_id",
              "transition_state", "login_counter", "pending_restore",
              "last_completed_restore"}
    if not _exact_keys(anchor, fields):
        raise RecoveryUnavailable("invalid protected anchor-v2 shape")
    manifest = decode_manifest(manifest_bytes)
    digest = hashlib.sha256(manifest_bytes).hexdigest()
    if (not _digest(checkpoint_sha256) or checkpoint_sha256 != manifest["checkpoint_sha256"]
            or type(anchor["anchor_version"]) is not int or anchor["anchor_version"] != 2
            or type(anchor["host_id"]) is not str or anchor["host_id"] != manifest["host_id"]
            or type(anchor["host_generation"]) is not int
            or anchor["host_generation"] != manifest["target_generation"]
            or type(anchor["transition_id"]) is not str
            or anchor["transition_id"] != manifest["operation_id"]
            or anchor["transition_state"] != "pending"
            or type(anchor["login_counter"]) is not int
            or not 0 <= anchor["login_counter"] < (1 << 64)):
        raise RecoveryUnavailable("protected pending anchor does not bind the manifest")
    pending = anchor["pending_restore"]
    pending_fields = {"operation_id", "target_generation", "manifest_sha256", "checkpoint_sha256"}
    expected_pending = {"operation_id": manifest["operation_id"],
        "target_generation": manifest["target_generation"],
        "manifest_sha256": digest, "checkpoint_sha256": checkpoint_sha256}
    if (not _exact_keys(pending, pending_fields)
            or type(pending["target_generation"]) is not int
            or pending != expected_pending):
        raise RecoveryUnavailable("protected pending record does not bind the manifest")
    tombstone = anchor["last_completed_restore"]
    if tombstone is not None:
        tombstone_fields = {"operation_id", "target_generation", "manifest_sha256",
                            "checkpoint_sha256", "database_sha256"}
        if (not _exact_keys(tombstone, tombstone_fields) or not _uuid(tombstone["operation_id"])
                or type(tombstone["target_generation"]) is not int
                or tombstone["target_generation"] < 1
                or any(not _digest(tombstone[key]) for key in
                       ("manifest_sha256", "checkpoint_sha256", "database_sha256"))
                or tombstone["operation_id"] == manifest["operation_id"]):
            raise RecoveryUnavailable("protected prior tombstone is invalid")
    return manifest


RECOVERY_BLOCK_CODES = frozenset({
    "legacy_pending_unbound", "operation_mismatch", "manifest_invalid",
    "source_unavailable", "source_integrity", "schema_unsupported",
    "checkpoint_mismatch", "authority_conflict", "transaction_mismatch",
    "storage_uncertain", "owner_busy", "health_unavailable",
})


class RecoveryProtocolSession:
    """Closed v4 recovery-mode request sequencer with injected local effects.

    This is the child-side protocol core. It accepts only already-decoded,
    envelope-validated v4 messages from its private channel. The injected
    executor names are fixed at construction and are never selected by wire
    data. The class is intentionally not a controller or production channel.
    """
    _REQUESTS = {
        "owner.restore.preflight": ("child.restore.preflight_result",
            {"operation_id", "manifest_sha256"},
            {"operation_id", "status", "manifest_sha256", "checkpoint_sha256",
             "authority_sha256", "base_database_sha256", "checkpoint_size_bytes"}),
        "owner.restore.resume_preflight": ("child.restore.resume_preflight_result",
            {"operation_id", "manifest_sha256", "base_database_sha256"},
            {"operation_id", "status", "database_state", "base_database_sha256"}),
        "owner.restore.commit_pending": ("child.restore.pending_result",
            {"operation_id", "manifest_sha256", "checkpoint_sha256", "authority_sha256",
             "target_generation"},
            {"operation_id", "status", "host_id", "target_generation", "transition_state"}),
        "owner.restore.inspect": ("child.restore.inspect_result",
            {"operation_id", "manifest_sha256"},
            {"operation_id", "status", "phase", "database_state", "checkpoint_sha256",
             "authority_sha256", "base_database_sha256", "staged_database_sha256",
             "installed_database_sha256"}),
        "owner.restore.stage": ("child.restore.stage_result",
            {"operation_id", "manifest_sha256", "checkpoint_sha256"},
            {"operation_id", "status", "staged_database_sha256", "staged_size_bytes",
             "store_schema_version"}),
        "owner.restore.install": ("child.restore.install_result",
            {"operation_id", "manifest_sha256", "checkpoint_sha256", "staged_database_sha256"},
            {"operation_id", "status", "installed_database_sha256", "phase"}),
        "owner.restore.commit_database": ("child.restore.database_committed",
            {"operation_id", "manifest_sha256", "checkpoint_sha256",
             "installed_database_sha256", "target_generation"},
            {"operation_id", "status", "receipt_version", "database_sha256", "phase"}),
    }
    _PHASES = {"checkpoint_bound", "staged", "quiesced", "installing", "installed",
               "database_committed", "database_finalized", "anchor_committed", "cleaning", "complete"}

    def __init__(self, *, mode: str, operation_id: str, host_id: str,
                 target_generation: int, manifest_sha256: str,
                 executors: Mapping[str, Any], checkpoint_sha256: str | None = None,
                 authority_sha256: str | None = None):
        if (mode not in {"prepare", "prepare_resume", "recover"}
                or not _uuid(operation_id) or type(host_id) is not str or not host_id
                or len(host_id.encode("utf-8", "strict")) > 256
                or type(target_generation) is not int or not 1 <= target_generation < (1 << 64)
                or not _digest(manifest_sha256) or type(executors) is not dict):
            raise RecoveryUnavailable("invalid recovery child configuration")
        expected = ({"preflight", "commit_pending"} if mode == "prepare" else
            {"resume_preflight", "commit_pending"} if mode == "prepare_resume" else
            {"inspect", "stage", "install", "commit_database"})
        if executors.keys() != expected or any(not callable(value) for value in executors.values()):
            raise RecoveryUnavailable("recovery executor set is not closed")
        self.mode = mode
        self.operation_id = operation_id
        self.host_id = host_id
        self.target_generation = target_generation
        self.manifest_sha256 = manifest_sha256
        self.executors = dict(executors)
        self.phase = "ready"
        self.database_state: str | None = None
        self._shutdown = False
        self._failed = False
        self._handling = False
        self._checkpoint_digest = checkpoint_sha256
        self._authority_digest = authority_sha256
        self._base_digest = None
        if mode == "prepare_resume" and (not _digest(checkpoint_sha256) or not _digest(authority_sha256)):
            raise RecoveryUnavailable("resume requires the protected manifest identity")

    @property
    def ready_payload(self) -> dict[str, Any]:
        return {"mode": self.mode, "operation_id": self.operation_id,
                "host_id": self.host_id, "target_generation": self.target_generation,
                "manifest_sha256": self.manifest_sha256,
                "maximum_store_schema_version": 2}

    def handle(self, kind: str, payload: object) -> tuple[str, dict[str, Any]]:
        if self._failed or self._handling:
            self._failed = True
            raise RecoveryUnavailable("recovery session is terminal or reentrant")
        self._handling = True
        try:
            result = self._handle(kind, payload)
            if self._failed:
                raise RecoveryUnavailable("reentrant recovery execution is uncertain")
            return result
        except BaseException:
            self._failed = True
            raise
        finally:
            self._handling = False

    def _handle(self, kind: str, payload: object) -> tuple[str, dict[str, Any]]:
        if self._shutdown or type(kind) is not str or type(payload) is not dict:
            raise RecoveryUnavailable("recovery child is terminal or request malformed")
        if kind == "owner.shutdown":
            return self._shutdown_request(payload)
        contract = self._REQUESTS.get(kind)
        if contract is None:
            raise RecoveryUnavailable("recovery request is not allowlisted")
        reply_kind, fields, reply_fields = contract
        if (payload.keys() != fields or payload.get("operation_id") != self.operation_id
                or payload.get("manifest_sha256") != self.manifest_sha256):
            raise RecoveryUnavailable("recovery request identity or fields are invalid")
        for field in ("target_generation",):
            if field in payload and (type(payload[field]) is not int or payload[field] != self.target_generation):
                raise RecoveryUnavailable("invalid exact recovery integer")
        if kind == "owner.restore.preflight":
            self._require(self.mode == "prepare" and self.phase == "ready", kind)
            self.phase = "preflight_running"
            result = self.executors["preflight"](dict(payload))
            self._validate_result(result, reply_fields, kind)
            if result.get("operation_id") != self.operation_id:
                raise RecoveryUnavailable("preflight result operation mismatch")
            if result["status"] == "blocked":
                self.phase = "preflight_denied"
            elif (result["status"] == "ok"
                  and result["operation_id"] == self.operation_id
                  and result["manifest_sha256"] == self.manifest_sha256
                  and _digest(result["checkpoint_sha256"])
                  and _digest(result["authority_sha256"])
                  and _digest(result["base_database_sha256"])
                  and type(result["checkpoint_size_bytes"]) is int
                  and 1 <= result["checkpoint_size_bytes"] <= MAX_DATABASE_BYTES):
                if (self._checkpoint_digest is not None and self._checkpoint_digest != result["checkpoint_sha256"]
                        or self._authority_digest is not None and self._authority_digest != result["authority_sha256"]):
                    raise RecoveryUnavailable("preflight changed the bound manifest identity")
                self._base_digest = result["base_database_sha256"]
                self._authority_digest = result["authority_sha256"]
                self._checkpoint_digest = result["checkpoint_sha256"]
                self.phase = "preflight_ok"
            else:
                raise RecoveryUnavailable("preflight result is inconsistent")
        elif kind == "owner.restore.resume_preflight":
            self._require(self.mode == "prepare_resume" and self.phase == "ready", kind)
            if not _digest(payload["base_database_sha256"]):
                raise RecoveryUnavailable("resume base digest is invalid")
            self.phase = "resume_running"
            result = self.executors["resume_preflight"](dict(payload))
            self._validate_result(result, reply_fields, kind)
            if (result["status"] != "ok" or result["operation_id"] != self.operation_id
                    or result["base_database_sha256"] != payload["base_database_sha256"]
                    or result["database_state"] not in {"base", "pending"}):
                raise RecoveryUnavailable("resume preflight result is inconsistent")
            self.database_state = result["database_state"]
            self.phase = "resume_base" if self.database_state == "base" else "resume_pending"
        elif kind == "owner.restore.commit_pending":
            self._require((self.mode == "prepare" and self.phase == "preflight_ok")
                or (self.mode == "prepare_resume" and self.phase == "resume_base"), kind)
            if (payload["target_generation"] != self.target_generation
                    or payload["checkpoint_sha256"] != self._checkpoint_digest
                    or payload["authority_sha256"] != self._authority_digest):
                raise RecoveryUnavailable("pending transition identity is invalid")
            self._checkpoint_digest = payload["checkpoint_sha256"]
            result = self.executors["commit_pending"](dict(payload))
            self._validate_result(result, reply_fields, kind)
            if (result["status"] != "ok" or result["operation_id"] != self.operation_id
                    or result["host_id"] != self.host_id
                    or result["target_generation"] != self.target_generation
                    or result["transition_state"] != "pending"):
                raise RecoveryUnavailable("pending transition result is inconsistent")
            self.database_state = "pending"
            self.phase = "pending_committed"
        elif kind == "owner.restore.inspect":
            self._require(self.mode == "recover" and self.phase in ({"ready", "recovering"} | self._PHASES), kind)
            prior_phase = self.phase
            self.phase = "recovering"
            result = self.executors["inspect"](dict(payload))
            self._validate_result(result, reply_fields, kind)
            if (result["status"] != "ok" or result["operation_id"] != self.operation_id
                    or result["phase"] not in self._PHASES
                    or result["database_state"] not in {"base", "pending", "committed"}
                    or not _digest(result["checkpoint_sha256"])
                    or not _digest(result["authority_sha256"])
                    or not _digest(result["base_database_sha256"])
                    or not _digest(result["staged_database_sha256"], nullable=True)
                    or not _digest(result["installed_database_sha256"], nullable=True)):
                raise RecoveryUnavailable("recovery inspection result is inconsistent")
            allowed_database_phases = {
                "base": {"checkpoint_bound"},
                "pending": {"checkpoint_bound", "staged", "quiesced", "installing", "installed"},
                "committed": {"installed", "database_committed", "database_finalized"},
            }
            if result["phase"] not in allowed_database_phases[result["database_state"]]:
                raise RecoveryUnavailable("database phase and state are contradictory")
            if prior_phase in PHASES and PHASES.index(result["phase"]) < PHASES.index(prior_phase):
                raise RecoveryUnavailable("inspection moved durable state backwards")
            for observed, bound in ((result["checkpoint_sha256"], self._checkpoint_digest),
                                    (result["authority_sha256"], self._authority_digest),
                                    (result["base_database_sha256"], self._base_digest)):
                if bound is not None and observed != bound:
                    raise RecoveryUnavailable("inspection changed the bound manifest identity")
            self._authority_digest = result["authority_sha256"]
            self._base_digest = result["base_database_sha256"]
            self.database_state = result["database_state"]
            self.phase = result["phase"]
            self._checkpoint_digest = result["checkpoint_sha256"]
            self._staged_digest = result["staged_database_sha256"]
        elif kind == "owner.restore.stage":
            self._require(self.mode == "recover" and self.phase in {"checkpoint_bound", "pending"}
                          and self.database_state in {"pending", "committed"}, kind)
            if payload["checkpoint_sha256"] != self._checkpoint_digest:
                raise RecoveryUnavailable("stage checkpoint identity mismatch")
            result = self.executors["stage"](dict(payload))
            self._validate_result(result, reply_fields, kind)
            if (result["status"] != "ok" or result["operation_id"] != self.operation_id
                    or not _digest(result["staged_database_sha256"])
                    or type(result["staged_size_bytes"]) is not int
                    or not 1 <= result["staged_size_bytes"] <= MAX_DATABASE_BYTES
                    or result["store_schema_version"] != 2):
                raise RecoveryUnavailable("staged database result is inconsistent")
            self._staged_digest = result["staged_database_sha256"]
            self.phase = "staged"
        elif kind == "owner.restore.install":
            self._require(self.mode == "recover" and self.phase in {"staged", "quiesced", "installing"}, kind)
            if (payload["checkpoint_sha256"] != self._checkpoint_digest
                    or payload["staged_database_sha256"] != self._staged_digest):
                raise RecoveryUnavailable("install identity mismatch")
            result = self.executors["install"](dict(payload))
            self._validate_result(result, reply_fields, kind)
            if (result["status"] != "ok" or result["operation_id"] != self.operation_id
                    or result["installed_database_sha256"] != self._staged_digest
                    or result["phase"] != "installed"):
                raise RecoveryUnavailable("database install result is inconsistent")
            self.phase = "installed"
        else:  # owner.restore.commit_database
            self._require(self.mode == "recover" and self.phase in {"installed", "database_committed", "database_finalized"}, kind)
            if (payload["checkpoint_sha256"] != self._checkpoint_digest
                    or payload["installed_database_sha256"] != self._staged_digest
                    or payload["target_generation"] != self.target_generation):
                raise RecoveryUnavailable("database commit identity mismatch")
            result = self.executors["commit_database"](dict(payload))
            self._validate_result(result, reply_fields, kind)
            if (result["status"] != "ok" or result["operation_id"] != self.operation_id
                    or result["receipt_version"] != 1 or not _digest(result["database_sha256"])
                    or result["phase"] != "database_committed"):
                raise RecoveryUnavailable("database commit result is inconsistent")
            self.phase = "database_committed"
        if kind in {"owner.restore.preflight", "owner.restore.resume_preflight",
                    "owner.restore.commit_pending", "owner.restore.inspect"}:
            checkpoint = result.get("checkpoint_sha256")
            if checkpoint is not None:
                self._checkpoint_digest = checkpoint
        return reply_kind, result

    def _shutdown_request(self, payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        if payload.keys() != {"operation_id", "reason"} or payload["operation_id"] != self.operation_id:
            raise RecoveryUnavailable("shutdown identity is invalid")
        reason = payload["reason"]
        allowed = ((self.mode == "prepare" and (
                (self.phase == "preflight_denied" and reason == "preflight_denied")
                or (self.phase == "pending_committed" and reason == "prepare_complete")))
            or (self.mode == "prepare_resume" and self.phase in {"resume_pending", "pending_committed"}
                and reason == "prepare_resume_complete")
            or (self.mode == "recover" and self.phase in {"database_committed", "database_finalized"}
                and reason == "recovery_complete"))
        self._require(allowed, "owner.shutdown")
        self._shutdown = True
        return "child.shutdown_ack", {"operation_id": self.operation_id}

    @staticmethod
    def _validate_result(result: object, expected_fields: set[str], kind: str) -> None:
        if type(result) is not dict:
            raise RecoveryUnavailable(f"{kind} executor returned an invalid shape")
        for field in ("target_generation", "receipt_version", "store_schema_version", "checkpoint_size_bytes", "staged_size_bytes"):
            if field in result and (type(result[field]) is not int or result[field] < 1):
                raise RecoveryUnavailable("executor returned a non-exact integer")
        if result.get("status") == "blocked":
            if result.keys() != {"operation_id", "status", "code"} or result["code"] not in RECOVERY_BLOCK_CODES:
                raise RecoveryUnavailable("blocked result is not a closed failure shape")
        elif result.keys() != expected_fields or result.get("status") != "ok":
            raise RecoveryUnavailable("result status is invalid")

    @staticmethod
    def _require(condition: bool, kind: str) -> None:
        if not condition:
            raise RecoveryUnavailable(f"{kind} is illegal in the current recovery phase")


def _pinned_ddl_material() -> list[tuple[str, str, str]]:
    """Return the reviewed migration and authority DDL vector in fixed order."""
    from jarvis.db import MIGRATIONS
    from jarvis.usage_ledger import _MODEL_BUDGET_SCHEMA, _SCHEMA
    from jarvis.bot.phone_admission_store import SCHEMA_SQL

    values = [("app", migration_id, sql) for migration_id, sql in MIGRATIONS]
    values.extend((("ledger", "usage", _SCHEMA), ("ledger", "budget", _MODEL_BUDGET_SCHEMA)))
    values.extend(("phone", name, sql) for name, sql in SCHEMA_SQL.items())
    values.append(("phone", "receipt", RECEIPT_DDL))
    return values


def _pinned_ddl_digest() -> str:
    digest = hashlib.sha256(b"MortimerPinnedRecoveryDDL\0v1\0")
    for kind, name, sql in _pinned_ddl_material():
        for item in (kind.encode("ascii"), name.encode("utf-8"), sql.encode("utf-8")):
            digest.update(struct.pack(">I", len(item)))
            digest.update(item)
    return digest.hexdigest()


def _schema_rows(db: sqlite3.Connection) -> list[tuple[str, str, str, str | None]]:
    try:
        rows = db.execute("SELECT type,name,tbl_name,sql FROM sqlite_master "
                          "WHERE type IN ('table','index','view','trigger')").fetchall()
    except sqlite3.Error as exc:
        raise RecoveryUnavailable("schema catalog is unavailable") from exc
    result: list[tuple[str, str, str, str | None]] = []
    for row in rows:
        if (type(row[0]) is not str or type(row[1]) is not str or type(row[2]) is not str
                or (row[3] is not None and type(row[3]) is not str)):
            raise RecoveryUnavailable("schema catalog row is malformed")
        result.append((row[0], row[1], row[2], row[3]))
    return sorted(result, key=lambda row: tuple(part.encode("utf-8") for part in row[:3]))


def _field_bytes(value: str | None) -> bytes:
    if value is None:
        return b"\x00"
    encoded = value.encode("utf-8", "strict")
    if len(encoded) > 0xFFFFFFFF:
        raise RecoveryUnavailable("schema field is too large")
    return b"\x01" + struct.pack(">I", len(encoded)) + encoded


def _schema_fingerprint(rows: list[tuple[str, str, str, str | None]]) -> str:
    digest = hashlib.sha256(b"MortimerSQLiteSchemaCatalog\0v1\0")
    digest.update(struct.pack(">I", len(rows)))
    for row in rows:
        for value in row:
            digest.update(_field_bytes(value))
    return digest.hexdigest()


def _build_pinned_application_catalog() -> tuple[tuple[str, str, str, str | None], ...]:
    """Build the expected application catalog from pinned migrations in memory."""
    if _pinned_ddl_digest() != PINNED_DDL_SHA256:
        raise RecoveryUnavailable("pinned migration vector changed")
    from jarvis.db import MIGRATIONS
    from jarvis.usage_ledger import _MODEL_BUDGET_SCHEMA, _SCHEMA

    db = sqlite3.connect(":memory:")
    try:
        db.execute("CREATE TABLE migrations (id TEXT PRIMARY KEY, applied_at TEXT NOT NULL)")
        for migration_id, sql in MIGRATIONS:
            db.executescript(sql)
            db.execute("INSERT INTO migrations(id,applied_at) VALUES(?,?)", (migration_id, "pinned"))
        db.executescript(_SCHEMA)
        db.executescript(_MODEL_BUDGET_SCHEMA)
        rows = _schema_rows(db)
        application = tuple(row for row in rows if row[2] not in PHONE_TABLES)
        if not application:
            raise RecoveryUnavailable("pinned application catalog is empty")
        return application
    except (sqlite3.Error, UnicodeError) as exc:
        raise RecoveryUnavailable("pinned application catalog cannot be built") from exc
    finally:
        db.close()


def _validate_phone_catalog(db: sqlite3.Connection, rows: list[tuple[str, str, str, str | None]]) -> None:
    phone_tables = {row[1] for row in rows if row[0] == "table" and row[1] in PHONE_TABLES}
    if not phone_tables:
        return
    if not {"phone_remote_meta", "phone_remote_devices", "phone_remote_grants",
            "phone_remote_sessions"}.issubset(phone_tables):
        raise RecoveryUnavailable("phone authority schema is partial")
    receipt_present = "phone_remote_restore_receipt" in phone_tables
    try:
        meta = db.execute("SELECT schema_version FROM phone_remote_meta WHERE singleton_id=1").fetchone()
    except sqlite3.Error as exc:
        raise RecoveryUnavailable("phone authority version is unavailable") from exc
    if meta is None or type(meta[0]) is not int or meta[0] not in {1, 2}:
        raise RecoveryUnavailable("phone authority version is unsupported")
    if receipt_present != (meta[0] == 2):
        raise RecoveryUnavailable("phone restore receipt schema does not match store version")
    from jarvis.bot.phone_admission_store import SCHEMA_SQL
    expected = sqlite3.connect(":memory:")
    try:
        for table in ("phone_remote_meta", "phone_remote_devices", "phone_remote_grants", "phone_remote_sessions"):
            expected.execute(SCHEMA_SQL[table])
        if receipt_present:
            expected.execute(RECEIPT_DDL)
        expected_rows = [row for row in _schema_rows(expected) if row[2] in PHONE_TABLES]
        observed_rows = [row for row in rows if row[2] in PHONE_TABLES]
        if observed_rows != expected_rows:
            raise RecoveryUnavailable("phone authority DDL catalog differs from pinned schema")
    except sqlite3.Error as exc:
        raise RecoveryUnavailable("pinned phone authority catalog cannot be built") from exc
    finally:
        expected.close()


def _application_rows_equal(left: sqlite3.Connection, right: sqlite3.Connection) -> bool:
    """Compare every application table row without trusting row order or IDs."""
    left_rows, right_rows = _schema_rows(left), _schema_rows(right)
    left_tables = sorted((row[1] for row in left_rows if row[0] == "table" and row[2] not in PHONE_TABLES),
                         key=lambda value: value.encode("utf-8"))
    right_tables = sorted((row[1] for row in right_rows if row[0] == "table" and row[2] not in PHONE_TABLES),
                          key=lambda value: value.encode("utf-8"))
    if left_tables != right_tables:
        return False
    for table in left_tables:
        columns = [row[1] for row in left.execute(f'PRAGMA table_info("{table}")')]
        if not columns:
            raise RecoveryUnavailable("application table has no columns")
        selection = ",".join(f'"{column}"' for column in columns)
        query = f'SELECT {selection} FROM "{table}" ORDER BY {selection}'
        first = left.execute(query); second = right.execute(query)
        while True:
            left_batch = first.fetchmany(256)
            right_batch = second.fetchmany(256)
            if len(left_batch) != len(right_batch):
                return False
            if [tuple(row) for row in left_batch] != [tuple(row) for row in right_batch]:
                return False
            if not left_batch:
                break
    return True


def validate_source_catalog(db: sqlite3.Connection) -> str:
    """Validate an application DB against pinned migrations and phone schema.

    The caller must open the source read-only from an owner-selected fixed
    descriptor and separately validate file type, size, hash, quick_check and
    foreign keys. This function does not accept a path or import source rows.
    """
    if _pinned_ddl_digest() != PINNED_DDL_SHA256:
        raise RecoveryUnavailable("pinned migration vector changed")
    rows = _schema_rows(db)
    expected_app = _build_pinned_application_catalog()
    observed_app = tuple(row for row in rows if row[2] not in PHONE_TABLES)
    if observed_app != expected_app:
        raise RecoveryUnavailable("application schema catalog differs from pinned migrations")
    _validate_phone_catalog(db, rows)
    from jarvis.db import MIGRATIONS
    try:
        applied = [row[0] for row in db.execute("SELECT id FROM migrations ORDER BY rowid")]
    except sqlite3.Error as exc:
        raise RecoveryUnavailable("migration vector is unavailable") from exc
    expected_ids = [migration_id for migration_id, _ in MIGRATIONS]
    if applied != expected_ids:
        raise RecoveryUnavailable("migration vector differs from pinned order")
    return _schema_fingerprint(rows)


def reconcile_staged_database(source_db: sqlite3.Connection,
                              checkpoint_db: sqlite3.Connection,
                              staged_db: sqlite3.Connection, *,
                              host_id: str, base_generation: int,
                              authority_sha256: str,
                              expected_previous_receipt: tuple[Any, ...] | None = None) -> str:
    """Build an offline staged image from app data plus current authority.

    Application tables come from the selected source. Phone devices, grants,
    and the prior completed receipt come only from the checkpoint bound to the
    protected authority. Sessions and process-local admissions are never
    imported. The caller must verify a schema-v2 prior receipt against the
    protected tombstone before passing it here, own the recovery singleton,
    and supply already-open, verified SQLite connections; this helper never
    accepts or opens a path.
    """
    if (type(source_db) is not sqlite3.Connection or type(checkpoint_db) is not sqlite3.Connection
            or type(staged_db) is not sqlite3.Connection or len({id(source_db), id(checkpoint_db), id(staged_db)}) != 3
            or staged_db.in_transaction or type(host_id) is not str or not host_id.strip()
            or len(host_id.encode("utf-8", "strict")) > 256
            or type(base_generation) is not int or base_generation < 1
            or not _digest(authority_sha256)):
        raise RecoveryUnavailable("invalid staged database inputs")
    validate_source_catalog(source_db)
    validate_source_catalog(checkpoint_db)
    for candidate in (source_db, checkpoint_db):
        if [tuple(row) for row in candidate.execute("PRAGMA quick_check").fetchall()] != [("ok",)]:
            raise RecoveryUnavailable("source database integrity check failed")
        if candidate.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise RecoveryUnavailable("source database has foreign-key violations")
    checkpoint_meta = _meta(checkpoint_db)
    if (checkpoint_meta["schema_version"] not in {1, 2}
            or checkpoint_meta["host_id"] != host_id
            or checkpoint_meta["host_generation"] != base_generation
            or checkpoint_meta["transition_id"] is not None
            or checkpoint_meta["transition_state"] != "stable"
            or authority_projection_sha256(checkpoint_db) != authority_sha256):
        raise RecoveryUnavailable("checkpoint authority does not match the protected base")
    checkpoint_receipt: tuple[Any, ...] | None = None
    if checkpoint_meta["schema_version"] == 2:
        _validate_phone_catalog(checkpoint_db, _schema_rows(checkpoint_db))
        checkpoint_receipt = _receipt_row(checkpoint_db)
        if checkpoint_receipt is None:
            raise RecoveryUnavailable("schema-v2 checkpoint has no prior restore receipt")
        _verify_expected_receipt(checkpoint_receipt, expected_previous_receipt)
    elif expected_previous_receipt is not None:
        raise RecoveryUnavailable("schema-v1 checkpoint cannot have a prior receipt")
    try:
        if staged_db.execute("SELECT 1 FROM sqlite_master LIMIT 1").fetchone() is not None:
            raise RecoveryUnavailable("staged database target is not empty")
        source_db.backup(staged_db, pages=256, sleep=0.001)
        staged_db.execute("PRAGMA foreign_keys=OFF")
        with staged_db:
            for table in ("phone_remote_restore_receipt", "phone_remote_sessions",
                          "phone_remote_grants", "phone_remote_devices", "phone_remote_meta"):
                staged_db.execute(f'DROP TABLE IF EXISTS "{table}"')
            from jarvis.bot.phone_admission_store import SCHEMA_SQL
            for table in ("phone_remote_meta", "phone_remote_devices", "phone_remote_grants",
                          "phone_remote_sessions"):
                staged_db.execute(SCHEMA_SQL[table])
            staged_schema_version = checkpoint_meta["schema_version"]
            staged_db.execute("INSERT INTO phone_remote_meta VALUES(1,?,?,?,NULL,'stable')",
                              (staged_schema_version, host_id, base_generation))
            if staged_schema_version == 2:
                staged_db.execute(RECEIPT_DDL)
                assert checkpoint_receipt is not None
                staged_db.execute("INSERT INTO phone_remote_restore_receipt VALUES(1,?,?,?,?,?,?,?)",
                                  checkpoint_receipt)
            for table, order in (("phone_remote_devices", "device_id"),
                                 ("phone_remote_grants", "grant_id")):
                columns = sorted({
                    row[1] for row in checkpoint_db.execute(f"PRAGMA table_info({table})")
                }, key=lambda item: item.encode("utf-8"))
                if not columns:
                    raise RecoveryUnavailable("checkpoint authority table is malformed")
                rows = checkpoint_db.execute(
                    f'SELECT {",".join(chr(34) + column + chr(34) for column in columns)} '
                    f'FROM "{table}" ORDER BY CAST("{order}" AS BLOB)').fetchall()
                if len(rows) > 100_000:
                    raise RecoveryUnavailable("checkpoint authority exceeds row limit")
                placeholders = ",".join("?" for _ in columns)
                names = ",".join(f'"{column}"' for column in columns)
                staged_db.executemany(f'INSERT INTO "{table}"({names}) VALUES({placeholders})', rows)
            if staged_db.execute("SELECT count(*) FROM phone_remote_sessions").fetchone()[0] != 0:
                raise RecoveryUnavailable("staged sessions must be empty")
        staged_db.execute("PRAGMA foreign_keys=ON")
        if staged_db.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
            raise RecoveryUnavailable("staged foreign-key enforcement is unavailable")
        if staged_db.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise RecoveryUnavailable("staged authority violates foreign keys")
        if authority_projection_sha256(staged_db) != authority_sha256:
            raise RecoveryUnavailable("staged authority differs from checkpoint")
        staged_fingerprint = validate_source_catalog(staged_db)
        # The whole schema fingerprint changes when source phone tables are
        # replaced, but the pinned application portion must remain identical.
        staged_rows = _schema_rows(staged_db)
        source_rows = _schema_rows(source_db)
        if (tuple(row for row in staged_rows if row[2] not in PHONE_TABLES)
                != tuple(row for row in source_rows if row[2] not in PHONE_TABLES)):
            raise RecoveryUnavailable("application source rows changed during staging")
        return staged_fingerprint
    except RecoveryUnavailable:
        raise
    except (sqlite3.Error, OSError, UnicodeError) as exc:
        raise RecoveryUnavailable("staged database reconciliation failed") from exc


def stage_pending_database(source_db: sqlite3.Connection,
                           checkpoint_db: sqlite3.Connection,
                           staged_db: sqlite3.Connection, *,
                           operation_id: str, host_id: str,
                           base_generation: int, target_generation: int,
                           manifest_sha256: str, checkpoint_sha256: str,
                           authority_sha256: str,
                           expected_previous_receipt: tuple[Any, ...] | None = None) -> str:
    """Create the exact schema-v2 pending image expected by file installation.

    This is a transaction helper, not an owner command. The caller must have
    validated the protected pending anchor, tombstone and prior receipt, and
    must retain the singleton lock while the returned file is staged and
    installed.
    """
    reconcile_staged_database(source_db, checkpoint_db, staged_db,
        host_id=host_id, base_generation=base_generation,
        authority_sha256=authority_sha256,
        expected_previous_receipt=expected_previous_receipt)
    state = apply_pending_database(staged_db, operation_id=operation_id,
        host_id=host_id, base_generation=base_generation,
        target_generation=target_generation, manifest_sha256=manifest_sha256,
        checkpoint_sha256=checkpoint_sha256, authority_sha256=authority_sha256,
        expected_previous_receipt=expected_previous_receipt)
    if state != "pending":
        raise RecoveryUnavailable("staged database did not enter pending state")
    meta = _meta(staged_db)
    if (meta["schema_version"] != 2 or meta["host_id"] != host_id
            or meta["host_generation"] != target_generation
            or meta["transition_id"] != operation_id
            or meta["transition_state"] != "pending"):
        raise RecoveryUnavailable("staged database pending metadata failed verification")
    _validate_phone_catalog(staged_db, _schema_rows(staged_db))
    _verify_expected_receipt(_receipt_row(staged_db), expected_previous_receipt)
    if [tuple(row) for row in staged_db.execute("PRAGMA quick_check").fetchall()] != [("ok",)]:
        raise RecoveryUnavailable("staged database integrity check failed")
    if staged_db.execute("PRAGMA foreign_key_check").fetchone() is not None:
        raise RecoveryUnavailable("staged database has foreign-key violations")
    return _schema_fingerprint(_schema_rows(staged_db))


def authority_projection_sha256(db: sqlite3.Connection) -> str:
    """Hash the exact device/grant authority projection from a pinned store DB."""
    try:
        devices = db.execute("""SELECT device_id,owner_id,public_key,key_algorithm,revoked_at
            FROM phone_remote_devices ORDER BY CAST(device_id AS BLOB)""").fetchall()
        grants = db.execute("""SELECT grant_id,device_id,owner_id,scopes_json,grant_generation,revoked_at
            FROM phone_remote_grants ORDER BY CAST(grant_id AS BLOB)""").fetchall()
    except sqlite3.Error as exc:
        raise RecoveryUnavailable("authority projection is unavailable") from exc
    if len(devices) > 0xFFFFFFFF or len(grants) > 0xFFFFFFFF:
        raise RecoveryUnavailable("authority projection is too large")
    output = bytearray(b"MortimerPhoneAuthorityCheckpoint\0v1\0")
    output.extend(struct.pack(">I", len(devices)))

    def field(raw: bytes) -> None:
        if len(raw) > 0xFFFFFFFF:
            raise RecoveryUnavailable("authority field is too large")
        output.extend(struct.pack(">I", len(raw)))
        output.extend(raw)

    def text(value: object) -> bytes:
        if type(value) is not str:
            raise RecoveryUnavailable("authority text field is invalid")
        return value.encode("utf-8", "strict")

    def revoked(value: object) -> None:
        if value is None:
            output.append(0)
            return
        if type(value) not in (float, int) or not math.isfinite(value) or value < 0:
            raise RecoveryUnavailable("authority revocation time is invalid")
        output.append(1)
        output.extend(struct.pack(">d", float(value)))

    for row in devices:
        output.append(1)
        field(text(row[0])); field(text(row[1]))
        if type(row[2]) is not bytes or not row[2]:
            raise RecoveryUnavailable("authority public key is invalid")
        field(row[2]); field(text(row[3])); revoked(row[4])
    output.extend(struct.pack(">I", len(grants)))
    for row in grants:
        output.append(2)
        field(text(row[0])); field(text(row[1])); field(text(row[2]))
        try:
            scopes = json.loads(row[3], object_pairs_hook=_pairs_no_duplicates)
        except (TypeError, json.JSONDecodeError, ValueError) as exc:
            raise RecoveryUnavailable("authority scopes are invalid") from exc
        allowed = {"read", "voice", "action", "calls"}
        if (type(scopes) is not list or any(type(scope) is not str or scope not in allowed for scope in scopes)
                or len(set(scopes)) != len(scopes)):
            raise RecoveryUnavailable("authority scopes are invalid")
        canonical_scopes = sorted(scopes, key=lambda item: item.encode("utf-8"))
        field(json.dumps(canonical_scopes, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        generation = row[4]
        if type(generation) is not int or not 0 <= generation <= (1 << 63) - 1:
            raise RecoveryUnavailable("authority generation is invalid")
        output.extend(struct.pack(">Q", generation)); revoked(row[5])
    return hashlib.sha256(output).hexdigest()


def _meta(db: sqlite3.Connection) -> sqlite3.Row:
    db.row_factory = sqlite3.Row
    try:
        row = db.execute("SELECT schema_version,host_id,host_generation,transition_id,transition_state "
                         "FROM phone_remote_meta WHERE singleton_id=1").fetchone()
    except sqlite3.Error as exc:
        raise RecoveryUnavailable("authority metadata is unavailable") from exc
    if row is None:
        raise RecoveryUnavailable("authority metadata is missing")
    return row


def inspect_database_state(db: sqlite3.Connection, *, operation_id: str,
                           host_id: str, base_generation: int,
                           target_generation: int, manifest_sha256: str,
                           checkpoint_sha256: str, authority_sha256: str,
                           base_database_sha256: str,
                           actual_database_sha256: str,
                           expected_previous_receipt: tuple[Any, ...] | None = None) -> str:
    """Classify only the exact base, pending, or committed DB for one recovery.

    ``actual_database_sha256`` must be obtained by the owner from the fixed,
    closed database file. The logical connection state alone cannot establish
    the normalized base-file identity. This routine never mutates the DB and
    intentionally refuses every third state.
    """
    if (not _uuid(operation_id) or type(host_id) is not str or not host_id
            or type(base_generation) is not int or type(target_generation) is not int
            or target_generation != base_generation + 1
            or not all(_digest(item) for item in (manifest_sha256, checkpoint_sha256,
                                                   authority_sha256, base_database_sha256,
                                                   actual_database_sha256))
            or db.in_transaction):
        raise RecoveryUnavailable("invalid database inspection identity")
    if [tuple(row) for row in db.execute("PRAGMA quick_check").fetchall()] != [("ok",)]:
        raise RecoveryUnavailable("database integrity is unavailable")
    if db.execute("PRAGMA foreign_key_check").fetchone() is not None:
        raise RecoveryUnavailable("database foreign keys are invalid")
    _validate_phone_catalog(db, _schema_rows(db))
    row = _meta(db)
    if row["host_id"] != host_id or authority_projection_sha256(db) != authority_sha256:
        raise RecoveryUnavailable("database authority does not match the bound checkpoint")
    expected_pending = (row["schema_version"] == 2
        and row["host_generation"] == target_generation
        and row["transition_id"] == operation_id
        and row["transition_state"] == "pending")
    if expected_pending:
        _verify_expected_receipt(_receipt_row(db), expected_previous_receipt)
        return "pending"
    expected_base = (row["schema_version"] in {1, 2}
        and row["host_generation"] == base_generation
        and row["transition_id"] is None
        and row["transition_state"] == "stable"
        and actual_database_sha256 == base_database_sha256)
    if expected_base:
        if row["schema_version"] == 1:
            _verify_expected_receipt(None, expected_previous_receipt)
        else:
            _verify_expected_receipt(_receipt_row(db), expected_previous_receipt)
        return "base"
    expected_committed_receipt = (operation_id, host_id, target_generation,
        manifest_sha256, checkpoint_sha256, authority_sha256, 1)
    expected_committed = (row["schema_version"] == 2
        and row["host_generation"] == target_generation
        and row["transition_id"] is None
        and row["transition_state"] == "stable"
        and _receipt_row(db) == expected_committed_receipt)
    if expected_committed:
        # The receipt proves the DB transaction committed. The current byte
        # digest may differ after ordinary service writes; it is not the
        # completion-boundary digest stored in the protected tombstone.
        return "committed"
    raise RecoveryUnavailable("database is not the exact base, pending, or committed state")


@contextlib.contextmanager
def _atomic_recovery_transaction(db: sqlite3.Connection):
    # Explicit BEGIN is required even for DDL and isolation_level=None.
    if db.in_transaction:
        raise RecoveryUnavailable("database transaction ownership is uncertain")
    db.execute("BEGIN IMMEDIATE")
    try:
        yield
        db.commit()
    except BaseException:
        db.rollback()
        raise


def apply_pending_database(db: sqlite3.Connection, *, operation_id: str, host_id: str,
                           base_generation: int, target_generation: int,
                           manifest_sha256: str, checkpoint_sha256: str,
                           authority_sha256: str,
                           expected_previous_receipt: tuple[Any, ...] | None = None) -> str:
    """Commit the one-way v1→v2/pending DB transition; return base or pending.

    The caller must have verified the matching pending protected anchor and
    prior tombstone/receipt mapping and must hold the singleton owner lock.
    This helper never reads/writes an anchor, replaces a database, or provides
    a stable rollback operation. An existing schema-v2 receipt is preserved
    unchanged until the completion transaction replaces it.
    """
    for digest in (manifest_sha256, checkpoint_sha256, authority_sha256):
        if not _digest(digest):
            raise RecoveryUnavailable("invalid recovery digest")
    if (not _uuid(operation_id) or type(host_id) is not str or not host_id
            or type(base_generation) is not int or type(target_generation) is not int
            or target_generation != base_generation + 1):
        raise RecoveryUnavailable("invalid pending database identity")
    if db.in_transaction:
        raise RecoveryUnavailable("database transaction ownership is uncertain")
    row = _meta(db)
    if (row["schema_version"] == 2 and row["host_id"] == host_id
            and row["host_generation"] == target_generation
            and row["transition_id"] == operation_id and row["transition_state"] == "pending"):
        _validate_phone_catalog(db, _schema_rows(db))
        _verify_expected_receipt(_receipt_row(db), expected_previous_receipt)
        return "pending"
    if (row["schema_version"] not in {1, 2} or row["host_id"] != host_id
            or row["host_generation"] != base_generation
            or row["transition_id"] is not None or row["transition_state"] != "stable"):
        raise RecoveryUnavailable("database is neither exact base nor matching pending state")
    if row["schema_version"] == 1:
        _verify_expected_receipt(None, expected_previous_receipt)
    else:
        _validate_phone_catalog(db, _schema_rows(db))
        _verify_expected_receipt(_receipt_row(db), expected_previous_receipt)
    before_authority = authority_projection_sha256(db)
    if before_authority != authority_sha256:
        raise RecoveryUnavailable("checkpoint authority does not match current database")
    try:
        with _atomic_recovery_transaction(db):
            if row["schema_version"] == 1:
                db.execute(RECEIPT_DDL)
            db.execute("UPDATE phone_remote_meta SET schema_version=2,host_generation=?,transition_id=?,transition_state='pending' WHERE singleton_id=1",
                       (target_generation, operation_id))
            if db.execute("SELECT changes()").fetchone()[0] != 1:
                raise RecoveryUnavailable("pending metadata row was not updated exactly once")
            db.execute("DELETE FROM phone_remote_sessions")
    except (sqlite3.Error, RecoveryUnavailable) as exc:
        raise RecoveryUnavailable("pending database commit is uncertain") from exc
    if authority_projection_sha256(db) != authority_sha256:
        raise RecoveryUnavailable("pending database authority changed")
    return "pending"


def commit_reconciled_database(db: sqlite3.Connection, *, operation_id: str,
                               host_id: str, target_generation: int,
                               manifest_sha256: str, checkpoint_sha256: str,
                               authority_sha256: str,
                               expected_previous_receipt: tuple[Any, ...] | None = None) -> dict[str, object]:
    """Commit stable meta and the exact v1 receipt in one SQLite transaction."""
    if (not _uuid(operation_id) or type(host_id) is not str or not host_id
            or type(target_generation) is not int or target_generation < 2
            or any(not _digest(item) for item in
                   (manifest_sha256, checkpoint_sha256, authority_sha256))):
        raise RecoveryUnavailable("invalid completion receipt")
    if db.in_transaction:
        raise RecoveryUnavailable("database transaction ownership is uncertain")
    row = _meta(db)
    expected_receipt = (operation_id, host_id, target_generation, manifest_sha256,
                        checkpoint_sha256, authority_sha256, 1)
    if (row["schema_version"] == 2 and row["host_id"] == host_id
            and row["host_generation"] == target_generation
            and row["transition_id"] is None and row["transition_state"] == "stable"):
        _validate_phone_catalog(db, _schema_rows(db))
        try:
            existing = db.execute("SELECT operation_id,host_id,target_generation,manifest_sha256,"
                "checkpoint_sha256,authority_sha256,receipt_version FROM phone_remote_restore_receipt "
                "WHERE singleton_id=1").fetchone()
        except sqlite3.Error as exc:
            raise RecoveryUnavailable("completed restore receipt is unavailable") from exc
        if existing is None or tuple(existing) != expected_receipt:
            raise RecoveryUnavailable("stable database receipt does not match this operation")
        if authority_projection_sha256(db) != authority_sha256:
            raise RecoveryUnavailable("completed database authority changed")
        return {"operation_id": operation_id, "host_id": host_id,
                "target_generation": target_generation, "manifest_sha256": manifest_sha256,
                "checkpoint_sha256": checkpoint_sha256, "authority_sha256": authority_sha256,
                "receipt_version": 1}
    if (row["schema_version"] != 2 or row["host_id"] != host_id
            or row["host_generation"] != target_generation
            or row["transition_id"] != operation_id or row["transition_state"] != "pending"):
        raise RecoveryUnavailable("database is not pending for this operation")
    if authority_projection_sha256(db) != authority_sha256:
        raise RecoveryUnavailable("reconciled authority digest mismatch")
    _validate_phone_catalog(db, _schema_rows(db))
    _verify_expected_receipt(_receipt_row(db), expected_previous_receipt)
    try:
        with _atomic_recovery_transaction(db):
            db.execute("UPDATE phone_remote_meta SET transition_id=NULL,transition_state='stable' WHERE singleton_id=1")
            db.execute("INSERT INTO phone_remote_restore_receipt VALUES(1,?,?,?,?,?,?,1) "
                       "ON CONFLICT(singleton_id) DO UPDATE SET operation_id=excluded.operation_id,"
                       "host_id=excluded.host_id,target_generation=excluded.target_generation,"
                       "manifest_sha256=excluded.manifest_sha256,checkpoint_sha256=excluded.checkpoint_sha256,"
                       "authority_sha256=excluded.authority_sha256",
                       (operation_id, host_id, target_generation, manifest_sha256,
                        checkpoint_sha256, authority_sha256))
    except sqlite3.Error as exc:
        raise RecoveryUnavailable("database completion commit is uncertain") from exc
    result = {"operation_id": operation_id, "host_id": host_id,
            "target_generation": target_generation, "manifest_sha256": manifest_sha256,
            "checkpoint_sha256": checkpoint_sha256, "authority_sha256": authority_sha256,
            "receipt_version": 1}
    try:
        saved = db.execute("SELECT operation_id,host_id,target_generation,manifest_sha256,"
            "checkpoint_sha256,authority_sha256,receipt_version FROM phone_remote_restore_receipt "
            "WHERE singleton_id=1").fetchone()
    except sqlite3.Error as exc:
        raise RecoveryUnavailable("completion receipt readback failed") from exc
    if saved is None or tuple(saved) != expected_receipt:
        raise RecoveryUnavailable("completion receipt did not verify")
    return result


def validate_receipt_tombstone(db: sqlite3.Connection, *, tombstone: Mapping[str, Any],
                               host_id: str, retained_manifest_bytes: bytes) -> dict[str, Any]:
    """Check the receipt map; never compare the historical DB hash to live bytes."""
    required_tombstone = {"operation_id", "target_generation", "manifest_sha256",
                          "checkpoint_sha256", "database_sha256"}
    if not _exact_keys(dict(tombstone), required_tombstone):
        raise RecoveryUnavailable("invalid protected completion tombstone")
    if (not _uuid(tombstone["operation_id"])
            or type(tombstone["target_generation"]) is not int
            or tombstone["target_generation"] < 1
            or any(not _digest(tombstone[field]) for field in
                   ("manifest_sha256", "checkpoint_sha256", "database_sha256"))
            or type(host_id) is not str or not host_id.strip()
            or len(host_id.encode("utf-8", "strict")) > 256):
        raise RecoveryUnavailable("invalid protected completion receipt fields")
    manifest = decode_manifest(retained_manifest_bytes)
    manifest_digest = hashlib.sha256(retained_manifest_bytes).hexdigest()
    if (manifest_digest != tombstone["manifest_sha256"]
            or manifest["operation_id"] != tombstone["operation_id"]
            or manifest["target_generation"] != tombstone["target_generation"]
            or manifest["host_id"] != host_id
            or manifest["checkpoint_sha256"] != tombstone["checkpoint_sha256"]):
        raise RecoveryUnavailable("retained manifest does not bind the tombstone")
    try:
        receipt = db.execute("SELECT operation_id,host_id,target_generation,manifest_sha256,"
                             "checkpoint_sha256,authority_sha256,receipt_version "
                             "FROM phone_remote_restore_receipt WHERE singleton_id=1").fetchone()
    except sqlite3.Error as exc:
        raise RecoveryUnavailable("restore receipt is unavailable") from exc
    if receipt is None:
        raise RecoveryUnavailable("restore receipt is missing")
    observed = tuple(receipt)
    expected = (tombstone["operation_id"], host_id, tombstone["target_generation"],
                tombstone["manifest_sha256"], tombstone["checkpoint_sha256"],
                manifest["authority_sha256"], 1)
    if observed != expected or type(observed[2]) is not int or type(observed[6]) is not int:
        raise RecoveryUnavailable("restore receipt does not match tombstone")
    # database_sha256 is intentionally historical evidence and is not compared
    # with the current database, which ordinary service operations mutate.
    return {"operation_id": observed[0], "host_id": observed[1],
            "target_generation": observed[2], "manifest_sha256": observed[3],
            "checkpoint_sha256": observed[4], "authority_sha256": observed[5],
            "receipt_version": observed[6]}


def _validate_files(value: object) -> None:
    if not _exact_keys(value, {"database", "wal", "shm"}):
        raise RecoveryUnavailable("invalid journal files")
    for record in value.values():
        if not _exact_keys(record, {"present", "size_bytes", "sha256"}):
            raise RecoveryUnavailable("invalid journal file record")
        if type(record["present"]) is not bool or type(record["size_bytes"]) is not int:
            raise RecoveryUnavailable("invalid journal file record")
        if not 0 <= record["size_bytes"] <= MAX_DATABASE_BYTES:
            raise RecoveryUnavailable("invalid journal file size")
        if not _digest(record["sha256"], nullable=not record["present"]):
            raise RecoveryUnavailable("invalid journal file digest")
        if not record["present"] and record["size_bytes"] != 0:
            raise RecoveryUnavailable("absent file has nonzero size")
        if record["present"] and record["size_bytes"] == 0:
            raise RecoveryUnavailable("present file has empty content")


def _validate_cleanup(value: object) -> None:
    if not _exact_keys(value, set(CLEANUP_NAMES)):
        raise RecoveryUnavailable("invalid cleanup catalog")
    for record in value.values():
        if not _exact_keys(record, {"state", "sha256"}):
            raise RecoveryUnavailable("invalid cleanup entry")
        state = record["state"]
        if state not in {"absent", "pending", "intent", "done"}:
            raise RecoveryUnavailable("invalid cleanup state")
        if not _digest(record["sha256"], nullable=state == "absent"):
            raise RecoveryUnavailable("invalid cleanup digest")


def validate_journal(value: object) -> dict[str, Any]:
    """Validate the exact mutable-journal v1 shape without normalizing it."""
    if not _exact_keys(value, JOURNAL_FIELDS):
        raise RecoveryUnavailable("invalid journal fields")
    if value["journal_version"] != 1 or type(value["journal_version"]) is not int:
        raise RecoveryUnavailable("unsupported journal version")
    if not _uuid(value["operation_id"]) or not _digest(value["manifest_sha256"]):
        raise RecoveryUnavailable("invalid journal identity")
    if value["phase"] not in PHASES:
        raise RecoveryUnavailable("invalid journal phase")
    for key in ("staged_database_sha256", "installed_database_sha256", "final_database_sha256"):
        if not _digest(value[key], nullable=True):
            raise RecoveryUnavailable("invalid journal digest")
    if value["phase"] not in {"database_finalized", "anchor_committed", "cleaning", "complete"} and value["final_database_sha256"] is not None:
        raise RecoveryUnavailable("final database digest precedes finalization")
    step = value["rename_step"]
    if step is not None:
        if not _exact_keys(step, {"name", "action", "expected_sha256", "state"}):
            raise RecoveryUnavailable("invalid rename step")
        if step["name"] not in {"wal", "shm", "database", "staged_database"}:
            raise RecoveryUnavailable("invalid rename name")
        if step["action"] not in {"move_to_quarantine", "install"} or step["state"] not in {"intent", "done"}:
            raise RecoveryUnavailable("invalid rename step")
        if not _digest(step["expected_sha256"], nullable=True):
            raise RecoveryUnavailable("invalid rename digest")
    _validate_files(value["files"])
    _validate_cleanup(value["cleanup_artifacts"])
    phase = value["phase"]
    cleanup = value["cleanup_artifacts"]
    if phase == "checkpoint_bound":
        if (value["staged_database_sha256"] is not None
                or value["installed_database_sha256"] is not None
                or value["final_database_sha256"] is not None or step is not None):
            raise RecoveryUnavailable("checkpoint-bound journal contains later-phase state")
    if phase in {"staged", "quiesced", "installing"}:
        if (not _digest(value["staged_database_sha256"])
                or value["final_database_sha256"] is not None):
            raise RecoveryUnavailable("staged journal identity is incomplete")
        if phase in {"staged", "quiesced"} and value["installed_database_sha256"] is not None:
            raise RecoveryUnavailable("installed database precedes installation")
        if phase == "installing" and value["installed_database_sha256"] is not None:
            if (value["installed_database_sha256"] != value["staged_database_sha256"]
                    or step is None or step["name"] != "staged_database"
                    or step["action"] != "install" or step["state"] != "done"
                    or cleanup["staged_database"] != {
                        "state": "done", "sha256": value["staged_database_sha256"]}):
                raise RecoveryUnavailable("install acknowledgment does not match the staged image")
        elif cleanup["staged_database"] != {
                "state": "pending", "sha256": value["staged_database_sha256"]}:
            raise RecoveryUnavailable("staged artifact cleanup identity is invalid")
    if phase in {"installed", "database_committed", "database_finalized",
                 "anchor_committed", "cleaning", "complete"}:
        allowed_old_database_states = {"pending", "done", "intent"} if phase == "cleaning" else {"pending", "done"}
        if (not _digest(value["staged_database_sha256"])
                or value["installed_database_sha256"] != value["staged_database_sha256"]
                or step is None or step["name"] != "staged_database"
                or step["action"] != "install" or step["state"] != "done"
                or cleanup["staged_database"] != {
                        "state": "done", "sha256": value["staged_database_sha256"]}
                or cleanup["old_database"]["state"] not in allowed_old_database_states):
            raise RecoveryUnavailable("installed journal identity is incomplete")
    if phase in {"database_finalized", "anchor_committed", "cleaning", "complete"}:
        if not _digest(value["final_database_sha256"]):
            raise RecoveryUnavailable("final database digest is required after finalization")
    if phase in {"anchor_committed", "complete"}:
        if any(record["state"] == "intent" for record in cleanup.values()):
            raise RecoveryUnavailable("cleanup intent precedes cleanup phase")
    if phase == "complete" and any(record["state"] not in {"absent", "done"}
                                    for record in cleanup.values()):
        raise RecoveryUnavailable("completed journal still has cleanup work")
    return value


def decode_journal(data: bytes) -> dict[str, Any]:
    if type(data) is not bytes or not 1 <= len(data) <= MAX_JOURNAL_BYTES:
        raise RecoveryUnavailable("invalid journal size")
    try:
        value = json.loads(data.decode("utf-8", "strict"), object_pairs_hook=_pairs_no_duplicates,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError("constant")))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError) as exc:
        raise RecoveryUnavailable("invalid journal encoding") from exc
    return validate_journal(value)


def encode_journal(value: Mapping[str, Any]) -> bytes:
    validated = validate_journal(dict(value))
    data = json.dumps(validated, ensure_ascii=False, allow_nan=False,
                      sort_keys=True, separators=(",", ":")).encode("utf-8")
    if len(data) > MAX_JOURNAL_BYTES:
        raise RecoveryUnavailable("journal exceeds size limit")
    return data


def file_record(path: Path) -> FileRecord:
    try:
        before = path.lstat()
    except FileNotFoundError:
        return FileRecord(False, 0, None)
    if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
            or before.st_size > MAX_DATABASE_BYTES):
        raise RecoveryUnavailable("recovery file is not a bounded regular file")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
        try:
            info = os.fstat(fd)
            if ((info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns) !=
                    (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
                    or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1):
                raise RecoveryUnavailable("recovery file changed before hashing")
            digest = hashlib.sha256()
            total = 0
            while True:
                block = os.read(fd, min(1024 * 1024, info.st_size - total + 1))
                if not block:
                    break
                total += len(block)
                if total > info.st_size:
                    raise RecoveryUnavailable("recovery file grew while hashing")
                digest.update(block)
            after = os.fstat(fd)
            if total != info.st_size or (after.st_size, after.st_mtime_ns) != (info.st_size, info.st_mtime_ns):
                raise RecoveryUnavailable("recovery file changed while hashing")
            return FileRecord(True, total, digest.hexdigest())
        finally:
            os.close(fd)
    except OSError as exc:
        raise RecoveryUnavailable("recovery file cannot be read safely") from exc


def _private_regular_file(path: Path, *, allow_missing: bool = False) -> os.stat_result | None:
    try:
        info = path.lstat()
    except FileNotFoundError:
        if allow_missing:
            return None
        raise RecoveryUnavailable("required recovery database is missing")
    except OSError as exc:
        raise RecoveryUnavailable("recovery database cannot be inspected") from exc
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_nlink != 1
            or stat.S_IMODE(info.st_mode) & 0o077 or info.st_size > MAX_DATABASE_BYTES):
        raise RecoveryUnavailable("database file is not private, owned, and bounded")
    return info


def _fsync_file_and_parent(path: Path) -> None:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags)
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                    or stat.S_IMODE(info.st_mode) & 0o077):
                raise RecoveryUnavailable("database file ownership changed")
            os.fsync(fd)
        finally:
            os.close(fd)
        dir_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except OSError as exc:
        raise RecoveryUnavailable("database durability check failed") from exc


def normalize_live_database(path: str | os.PathLike[str]) -> FileRecord:
    """Checkpoint and close one quiescent SQLite DB before hashing its main file.

    The caller must already hold the authority singleton, have drained/reaped
    every writer, and verify the stable authority pair. This helper does not
    acquire service locks or infer that an in-flight transaction was undone.
    """
    live = Path(path)
    _private_regular_file(live)
    wal = Path(f"{live}-wal")
    shm = Path(f"{live}-shm")
    for sidecar in (wal, shm):
        _private_regular_file(sidecar, allow_missing=True)
    db: sqlite3.Connection | None = None
    try:
        db = sqlite3.connect(str(live), timeout=0, isolation_level=None)
        if db.in_transaction:
            raise RecoveryUnavailable("database transaction is active")
        result = db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        if (type(result) is not tuple or len(result) != 3
                or type(result[0]) is not int or result[0] != 0):
            raise RecoveryUnavailable("WAL checkpoint is busy or malformed")
        mode = db.execute("PRAGMA journal_mode=DELETE").fetchone()
        if (type(mode) is not tuple or len(mode) != 1
                or type(mode[0]) is not str or mode[0].lower() != "delete"):
            raise RecoveryUnavailable("SQLite refused DELETE journal mode")
        integrity = db.execute("PRAGMA quick_check").fetchall()
        if integrity != [("ok",)]:
            raise RecoveryUnavailable("database integrity check failed")
        if db.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise RecoveryUnavailable("database contains foreign-key violations")
    except RecoveryUnavailable:
        raise
    except sqlite3.Error as exc:
        raise RecoveryUnavailable("database normalization failed") from exc
    finally:
        if db is not None:
            db.close()
    if wal.exists() or wal.is_symlink() or shm.exists() or shm.is_symlink():
        raise RecoveryUnavailable("SQLite sidecar remains after normalization")
    _fsync_file_and_parent(live)
    return file_record(live)


def create_checkpoint(live_path: str | os.PathLike[str], checkpoint_path: str | os.PathLike[str],
                      *, expected_live_sha256: str) -> FileRecord:
    """Create a distinct SQLite-backup image and verify it before journaling."""
    live, checkpoint = Path(live_path), Path(checkpoint_path)
    if not _digest(expected_live_sha256):
        raise RecoveryUnavailable("invalid live database digest")
    live_record = file_record(live)
    if not live_record.present or live_record.sha256 != expected_live_sha256:
        raise RecoveryUnavailable("normalized live database changed")
    _private_regular_file(live)
    if checkpoint.exists() or checkpoint.is_symlink():
        raise RecoveryUnavailable("checkpoint path already exists")
    checkpoint.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    parent = checkpoint.parent.lstat()
    if (not stat.S_ISDIR(parent.st_mode) or parent.st_uid != os.geteuid()
            or stat.S_IMODE(parent.st_mode) & 0o077):
        raise RecoveryUnavailable("checkpoint directory is not private and owned")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(checkpoint, flags, 0o600)
        os.close(fd)
    except OSError as exc:
        raise RecoveryUnavailable("checkpoint path cannot be created exclusively") from exc
    source_db: sqlite3.Connection | None = None
    target_db: sqlite3.Connection | None = None
    try:
        source_db = sqlite3.connect(str(live), timeout=0)
        target_db = sqlite3.connect(str(checkpoint), timeout=0)
        source_db.backup(target_db, pages=256, sleep=0.001)
        validate_source_catalog(source_db)
        validate_source_catalog(target_db)
        integrity = target_db.execute("PRAGMA quick_check").fetchall()
        if integrity != [("ok",)]:
            raise RecoveryUnavailable("checkpoint integrity check failed")
        if target_db.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise RecoveryUnavailable("checkpoint has foreign-key violations")
        live_meta = _meta(source_db)
        checkpoint_meta = _meta(target_db)
        if (tuple(live_meta) != tuple(checkpoint_meta)
                or authority_projection_sha256(source_db) != authority_projection_sha256(target_db)):
            raise RecoveryUnavailable("checkpoint authority differs from live database")
        mode = target_db.execute("PRAGMA journal_mode=DELETE").fetchone()
        if (mode is None or len(mode) != 1 or type(mode[0]) is not str
                or mode[0].lower() != "delete"):
            raise RecoveryUnavailable("checkpoint refused DELETE journal mode")
        if [tuple(row) for row in target_db.execute("PRAGMA quick_check").fetchall()] != [("ok",)]:
            raise RecoveryUnavailable("checkpoint integrity changed during normalization")
    except RecoveryUnavailable:
        raise
    except sqlite3.Error as exc:
        raise RecoveryUnavailable("SQLite backup failed") from exc
    finally:
        if target_db is not None:
            target_db.close()
        if source_db is not None:
            source_db.close()
    if Path(f"{checkpoint}-wal").exists() or Path(f"{checkpoint}-shm").exists():
        raise RecoveryUnavailable("checkpoint sidecar remains after close")
    _fsync_file_and_parent(checkpoint)
    record = file_record(checkpoint)
    if not record.present or record.size_bytes == 0 or record.size_bytes > MAX_DATABASE_BYTES:
        raise RecoveryUnavailable("checkpoint size is outside the supported range")
    return record


class RecoveryJournal:
    """Atomic fixed-name journal writer for a caller-owned disposable root.

    The caller must already hold the authority singleton and ensure the root is
    its fixed protected directory. This class refuses symlinks and never
    accepts paths from a request.
    """

    def __init__(self, root: str | os.PathLike[str], *, operation_id: str,
                 manifest_sha256: str) -> None:
        if not _uuid(operation_id) or not _digest(manifest_sha256):
            raise RecoveryUnavailable("invalid recovery identity")
        self.root = Path(root)
        try:
            info = self.root.lstat()
        except OSError as exc:
            raise RecoveryUnavailable("recovery root is unavailable") from exc
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) & 0o077):
            raise RecoveryUnavailable("recovery root is not a private owned directory")
        self.path = self.root / JOURNAL_NAME
        self.temp_path = self.root / JOURNAL_TEMP
        self.manifest_path = self.root / "manifest.json"
        self.operation_id = operation_id
        self.manifest_sha256 = manifest_sha256

    def bind_manifest(self, manifest_bytes: bytes) -> dict[str, Any]:
        """Durably retain the immutable manifest before its journal reference."""
        manifest = decode_manifest(manifest_bytes)
        digest = hashlib.sha256(manifest_bytes).hexdigest()
        if (digest != self.manifest_sha256 or manifest["operation_id"] != self.operation_id
                or Path(self.manifest_path).parent != self.root):
            raise RecoveryUnavailable("manifest does not match the fixed journal identity")
        checkpoint = _private_file_record(self.root / "checkpoint.db")
        if (checkpoint.sha256 != manifest["checkpoint_sha256"]
                or checkpoint.size_bytes != manifest["checkpoint_size_bytes"]):
            raise RecoveryUnavailable("checkpoint does not match the immutable manifest")
        existing = _private_file_record(self.manifest_path, allow_missing=True)
        if existing.present:
            if existing.sha256 != digest or self.manifest_path.read_bytes() != manifest_bytes:
                raise RecoveryUnavailable("immutable recovery manifest changed")
            return manifest
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            fd = os.open(self.manifest_path, flags, 0o600)
            try:
                view = memoryview(manifest_bytes)
                while view:
                    count = os.write(fd, view)
                    if count <= 0:
                        raise RecoveryUnavailable("manifest write was incomplete")
                    view = view[count:]
                os.fsync(fd)
            finally:
                os.close(fd)
            self._fsync_root()
        except RecoveryUnavailable:
            raise
        except OSError as exc:
            raise RecoveryUnavailable("manifest write durability is uncertain") from exc
        if _private_file_record(self.manifest_path).sha256 != digest:
            raise RecoveryUnavailable("manifest failed exact readback")
        return manifest

    def load_manifest(self) -> dict[str, Any]:
        data = _read_private_file(self.manifest_path, MAX_MANIFEST_BYTES)
        if hashlib.sha256(data).hexdigest() != self.manifest_sha256:
            raise RecoveryUnavailable("retained manifest digest mismatch")
        value = decode_manifest(data)
        if value["operation_id"] != self.operation_id:
            raise RecoveryUnavailable("retained manifest operation mismatch")
        return value

    def stage_database(self, source_db: sqlite3.Connection,
                       checkpoint_db: sqlite3.Connection, *,
                       expected_previous_receipt: tuple[Any, ...] | None = None) -> FileRecord:
        """Create the fixed staged image, verify it closed, then journal its hash."""
        current = self.load()
        if current["phase"] != "checkpoint_bound":
            raise RecoveryUnavailable("staged database is not the next journal phase")
        manifest = self.load_manifest()
        target = self.root / "staged.db"
        if (manifest["operation_id"] != self.operation_id
                or manifest["checkpoint_sha256"] != current["cleanup_artifacts"]["checkpoint"]["sha256"]
                or manifest["host_id"] != _meta(checkpoint_db)["host_id"]
                or manifest["base_generation"] != _meta(checkpoint_db)["host_generation"]):
            raise RecoveryUnavailable("staged database checkpoint is not bound")
        if target.exists() or target.is_symlink():
            record = self._verify_staged_database(target, source_db, checkpoint_db,
                manifest, expected_previous_receipt)
            self.mark_staged(target)
            if self.load()["staged_database_sha256"] != record.sha256:
                raise RecoveryUnavailable("recovered staged database hash is inconsistent")
            return record
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            fd = os.open(target, flags, 0o600)
            os.close(fd)
        except OSError as exc:
            raise RecoveryUnavailable("staged database path cannot be created exclusively") from exc
        staged: sqlite3.Connection | None = None
        try:
            staged = sqlite3.connect(str(target), timeout=0, isolation_level=None)
            stage_pending_database(source_db, checkpoint_db, staged,
                operation_id=self.operation_id, host_id=manifest["host_id"],
                base_generation=manifest["base_generation"],
                target_generation=manifest["target_generation"],
                manifest_sha256=self.manifest_sha256,
                checkpoint_sha256=manifest["checkpoint_sha256"],
                authority_sha256=manifest["authority_sha256"],
                expected_previous_receipt=expected_previous_receipt)
            mode = staged.execute("PRAGMA journal_mode=DELETE").fetchone()
            if (mode is None or len(mode) != 1 or type(mode[0]) is not str
                    or mode[0].lower() != "delete"):
                raise RecoveryUnavailable("staged database refused DELETE journal mode")
            if [tuple(row) for row in staged.execute("PRAGMA quick_check").fetchall()] != [("ok",)]:
                raise RecoveryUnavailable("staged database integrity verification failed")
            if staged.execute("PRAGMA foreign_key_check").fetchone() is not None:
                raise RecoveryUnavailable("staged database foreign keys are invalid")
            validate_source_catalog(staged)
        except RecoveryUnavailable:
            raise
        except sqlite3.Error as exc:
            raise RecoveryUnavailable("staged database file creation failed") from exc
        finally:
            if staged is not None:
                staged.close()
        if Path(f"{target}-wal").exists() or Path(f"{target}-shm").exists():
            raise RecoveryUnavailable("staged database sidecar remains after close")
        _fsync_file_and_parent(target)
        record = self._verify_staged_database(target, source_db, checkpoint_db,
            manifest, expected_previous_receipt)
        self.mark_staged(target)
        if self.load()["staged_database_sha256"] != record.sha256:
            raise RecoveryUnavailable("staged database journal identity failed readback")
        return record

    @staticmethod
    def _verify_staged_database(path: Path, source_db: sqlite3.Connection,
                                checkpoint_db: sqlite3.Connection,
                                manifest: Mapping[str, Any],
                                expected_previous_receipt: tuple[Any, ...] | None) -> FileRecord:
        record = _private_file_record(path)
        if not record.present or record.size_bytes <= 0:
            raise RecoveryUnavailable("staged database file is empty")
        if Path(f"{path}-wal").exists() or Path(f"{path}-shm").exists():
            raise RecoveryUnavailable("staged database sidecar remains")
        uri = path.resolve().as_uri() + "?mode=ro"
        staged: sqlite3.Connection | None = None
        try:
            staged = sqlite3.connect(uri, uri=True, timeout=0)
            staged.row_factory = None
            if [tuple(row) for row in staged.execute("PRAGMA quick_check").fetchall()] != [("ok",)]:
                raise RecoveryUnavailable("staged database integrity verification failed")
            if staged.execute("PRAGMA foreign_key_check").fetchone() is not None:
                raise RecoveryUnavailable("staged database foreign keys are invalid")
            validate_source_catalog(staged)
            meta = _meta(staged)
            if (meta["schema_version"] != 2 or meta["host_id"] != manifest["host_id"]
                    or meta["host_generation"] != manifest["target_generation"]
                    or meta["transition_id"] != manifest["operation_id"]
                    or meta["transition_state"] != "pending"):
                raise RecoveryUnavailable("staged database pending identity is invalid")
            _verify_expected_receipt(_receipt_row(staged), expected_previous_receipt)
            if (staged.execute("SELECT count(*) FROM phone_remote_sessions").fetchone()[0] != 0
                    or authority_projection_sha256(staged) != manifest["authority_sha256"]
                    or authority_projection_sha256(checkpoint_db) != manifest["authority_sha256"]
                    or not _application_rows_equal(source_db, staged)):
                raise RecoveryUnavailable("staged database contents differ from source/checkpoint")
            return record
        except RecoveryUnavailable:
            raise
        except sqlite3.Error as exc:
            raise RecoveryUnavailable("staged database cannot be verified") from exc
        finally:
            if staged is not None:
                staged.close()

    def create(self, *, files: Mapping[str, FileRecord], checkpoint_sha256: str) -> dict[str, Any]:
        if self.path.exists() or self.path.is_symlink():
            raise RecoveryUnavailable("journal already exists")
        if not _digest(checkpoint_sha256):
            raise RecoveryUnavailable("invalid checkpoint digest")
        if set(files) != {"database", "wal", "shm"}:
            raise RecoveryUnavailable("invalid initial file catalog")
        cleanup = {name: {"state": "absent", "sha256": None} for name in CLEANUP_NAMES}
        cleanup["checkpoint"] = {"state": "pending", "sha256": checkpoint_sha256}
        journal = {
            "journal_version": 1, "operation_id": self.operation_id,
            "manifest_sha256": self.manifest_sha256, "phase": "checkpoint_bound",
            "rename_step": None,
            "files": {name: files[name].as_json() for name in ("database", "wal", "shm")},
            "staged_database_sha256": None, "installed_database_sha256": None,
            "final_database_sha256": None, "cleanup_artifacts": cleanup,
        }
        self._write_new(journal)
        return journal

    def load(self) -> dict[str, Any]:
        self._reclaim_valid_orphan_temp()
        value = decode_journal(_read_private_file(self.path, MAX_JOURNAL_BYTES))
        if value["operation_id"] != self.operation_id or value["manifest_sha256"] != self.manifest_sha256:
            raise RecoveryUnavailable("journal identity mismatch")
        return value

    def advance(self, new_value: Mapping[str, Any]) -> dict[str, Any]:
        current = self.load()
        candidate = validate_journal(dict(new_value))
        if candidate["operation_id"] != self.operation_id or candidate["manifest_sha256"] != self.manifest_sha256:
            raise RecoveryUnavailable("journal identity mismatch")
        if PHASES.index(candidate["phase"]) < PHASES.index(current["phase"]):
            raise RecoveryUnavailable("journal phase cannot move backwards")
        if PHASES.index(candidate["phase"]) > PHASES.index(current["phase"]) + 1:
            raise RecoveryUnavailable("journal phase cannot skip a durable boundary")
        self._validate_transition(current, candidate)
        self._write_new(candidate)
        return candidate

    @staticmethod
    def _validate_transition(current: Mapping[str, Any], candidate: Mapping[str, Any]) -> None:
        """Reject a well-formed journal that rewrites already-bound evidence.

        The JSON codec validates a snapshot. This second check validates the
        only permitted transition between two snapshots, so a caller cannot
        use a valid-looking later snapshot to replace the original file set,
        checkpoint identity, rename intent, or cleanup receipt.
        """
        if current["files"] != candidate["files"]:
            raise RecoveryUnavailable("initial database file catalog is immutable")
        old_cleanup = current["cleanup_artifacts"]
        new_cleanup = candidate["cleanup_artifacts"]
        for name in CLEANUP_NAMES:
            before, after = old_cleanup[name], new_cleanup[name]
            permitted = {
                # A predeclared absent slot may acquire one journaled identity
                # only when staging or a verified quarantine rename creates it.
                "absent": {"absent", "pending"},
                "pending": {"pending", "intent", "done"},
                "intent": {"intent", "done"},
                "done": {"done"},
            }
            if after["state"] not in permitted[before["state"]]:
                raise RecoveryUnavailable("cleanup state cannot move backwards or appear")
            if before["sha256"] != after["sha256"]:
                staged_identity = (name == "staged_database" and before["state"] == "absent"
                    and after["state"] == "pending" and current["phase"] == "checkpoint_bound"
                    and candidate["phase"] == "staged"
                    and after["sha256"] == candidate["staged_database_sha256"])
                move_names = {"old_wal": "wal", "old_shm": "shm", "old_database": "database"}
                step = candidate["rename_step"]
                moved_identity = (name in move_names and before["state"] == "absent"
                    and after["state"] == "pending" and current["phase"] == "installing"
                    and candidate["phase"] == "installing" and step is not None
                    and step["name"] == move_names[name]
                    and step["action"] == "move_to_quarantine" and step["state"] == "done"
                    and step["expected_sha256"] == after["sha256"])
                if not (staged_identity or moved_identity):
                    raise RecoveryUnavailable("cleanup artifact identity is immutable")

        for field in ("staged_database_sha256", "installed_database_sha256", "final_database_sha256"):
            before, after = current[field], candidate[field]
            if before is not None and after != before:
                raise RecoveryUnavailable("journaled database identity cannot be replaced")
        if (current["staged_database_sha256"] is None
                and candidate["staged_database_sha256"] is not None
                and (current["phase"] != "checkpoint_bound"
                     or candidate["phase"] != "staged")):
            raise RecoveryUnavailable("staged database identity is out of phase")
        if (current["installed_database_sha256"] is None
                and candidate["installed_database_sha256"] is not None
                and (current["phase"] != "installing"
                     or candidate["phase"] != "installing")):
            raise RecoveryUnavailable("installed database identity is out of phase")
        if (current["final_database_sha256"] is None
                and candidate["final_database_sha256"] is not None
                and (current["phase"] != "database_committed"
                     or candidate["phase"] != "database_finalized")):
            raise RecoveryUnavailable("final database identity is out of phase")

        before = current["rename_step"]
        after = candidate["rename_step"]
        if before is None:
            if after is not None and (after["state"] != "intent"
                    or after["name"] != RENAME_ORDER[0]):
                raise RecoveryUnavailable("first rename intent is out of order")
        elif after != before:
            if (before["state"] == "intent"
                    and after == {**before, "state": "done"}):
                pass
            elif (before["state"] == "done" and after is not None
                    and after["state"] == "intent"
                    and RENAME_ORDER.index(after["name"]) == RENAME_ORDER.index(before["name"]) + 1):
                pass
            else:
                raise RecoveryUnavailable("rename journal cannot skip or replace an intent")

    def mark_staged(self, staged_database: str | os.PathLike[str]) -> dict[str, Any]:
        current = self.load()
        if current["phase"] != "checkpoint_bound":
            raise RecoveryUnavailable("staging is not the next journal phase")
        record = _private_file_record(Path(staged_database))
        if (Path(staged_database) != self.root / "staged.db"
                or not record.present or record.size_bytes == 0):
            raise RecoveryUnavailable("staged database is not the fixed verified artifact")
        candidate = dict(current)
        candidate["phase"] = "staged"
        candidate["staged_database_sha256"] = record.sha256
        artifacts = dict(candidate["cleanup_artifacts"])
        artifacts["staged_database"] = {"state": "pending", "sha256": record.sha256}
        candidate["cleanup_artifacts"] = artifacts
        return self.advance(candidate)

    def mark_quiesced(self) -> dict[str, Any]:
        current = self.load()
        if current["phase"] != "staged":
            raise RecoveryUnavailable("quiescence is not the next journal phase")
        candidate = dict(current, phase="quiesced")
        return self.advance(candidate)

    def begin_installation(self) -> dict[str, Any]:
        current = self.load()
        if current["phase"] != "quiesced":
            raise RecoveryUnavailable("installation is not the next journal phase")
        candidate = dict(current, phase="installing")
        return self.advance(candidate)

    def mark_installed(self) -> dict[str, Any]:
        current = self.load()
        step = current["rename_step"]
        if (current["phase"] != "installing" or step is None
                or step["name"] != "staged_database" or step["action"] != "install"
                or step["state"] != "done"
                or current["installed_database_sha256"] != current["staged_database_sha256"]):
            raise RecoveryUnavailable("installed database has not been verified")
        candidate = dict(current, phase="installed")
        return self.advance(candidate)

    def mark_database_committed(self) -> dict[str, Any]:
        current = self.load()
        if current["phase"] != "installed":
            raise RecoveryUnavailable("database commit is not the next journal phase")
        candidate = dict(current, phase="database_committed")
        return self.advance(candidate)

    def mark_database_finalized(self, final_database_sha256: str) -> dict[str, Any]:
        current = self.load()
        if current["phase"] != "database_committed" or not _digest(final_database_sha256):
            raise RecoveryUnavailable("database finalization is not ready")
        live = self.root.parent.parent / "jarvis.db"
        record = _private_file_record(live)
        if record.sha256 != final_database_sha256:
            raise RecoveryUnavailable("final database digest does not match the live file")
        candidate = dict(current, phase="database_finalized",
                         final_database_sha256=final_database_sha256)
        return self.advance(candidate)

    def mark_anchor_committed(self) -> dict[str, Any]:
        current = self.load()
        if current["phase"] != "database_finalized":
            raise RecoveryUnavailable("anchor completion is not the next journal phase")
        return self.advance(dict(current, phase="anchor_committed"))

    def begin_cleanup(self) -> dict[str, Any]:
        current = self.load()
        if current["phase"] != "anchor_committed":
            raise RecoveryUnavailable("cleanup is not the next journal phase")
        return self.advance(dict(current, phase="cleaning"))

    def cleanup_artifact(self, name: str) -> dict[str, Any]:
        current = self.load()
        if current["phase"] != "cleaning" or name not in CLEANUP_NAMES:
            raise RecoveryUnavailable("cleanup operation is outside the fixed cleanup phase")
        index = CLEANUP_NAMES.index(name)
        if any(current["cleanup_artifacts"][prior]["state"] not in {"absent", "done"}
               for prior in CLEANUP_NAMES[:index]):
            raise RecoveryUnavailable("cleanup artifacts must be removed in the fixed order")
        path = self._cleanup_path(name)
        artifacts = dict(current["cleanup_artifacts"])
        entry = dict(artifacts[name])
        if entry["state"] == "absent" or entry["state"] == "done":
            record = _private_file_record(path, allow_missing=True)
            if record.present:
                raise RecoveryUnavailable("completed cleanup artifact unexpectedly exists")
            return current
        if entry["state"] == "pending":
            entry["state"] = "intent"
            artifacts[name] = entry
            current = self.advance(dict(current, cleanup_artifacts=artifacts))
            entry = dict(current["cleanup_artifacts"][name])
        record = _private_file_record(path, allow_missing=True)
        if record.present:
            if record.sha256 != entry["sha256"]:
                raise RecoveryUnavailable("cleanup artifact identity changed")
            try:
                os.unlink(path)
            except OSError as exc:
                raise RecoveryUnavailable("cleanup removal is uncertain") from exc
            self._fsync_directory(self.root)
        elif entry["state"] != "intent":
            raise RecoveryUnavailable("cleanup artifact disappeared without intent")
        artifacts = dict(current["cleanup_artifacts"])
        artifacts[name] = {"state": "done", "sha256": entry["sha256"]}
        return self.advance(dict(current, cleanup_artifacts=artifacts))

    def complete_cleanup(self) -> dict[str, Any]:
        current = self.load()
        if current["phase"] != "cleaning" or any(
                record["state"] not in {"absent", "done"}
                for record in current["cleanup_artifacts"].values()):
            raise RecoveryUnavailable("cleanup is not durably complete")
        for name in CLEANUP_NAMES:
            if _private_file_record(self._cleanup_path(name), allow_missing=True).present:
                raise RecoveryUnavailable("cleanup artifact remains on disk")
        return self.advance(dict(current, phase="complete"))

    def _cleanup_path(self, name: str) -> Path:
        return {
            "checkpoint": self.root / "checkpoint.db",
            "staged_database": self.root / "staged.db",
            "old_database": self.root / "old.db",
            "old_wal": self.root / "old.wal",
            "old_shm": self.root / "old.shm",
        }[name]

    def move_database_file(self, live_database: str | os.PathLike[str], *,
                           name: str, action: str, expected_sha256: str | None) -> dict[str, Any]:
        """Perform one fixed-name, journaled DB/WAL/SHM rename.

        This is a recovery primitive, not a restore controller. It accepts no
        caller-selected source or destination path: the live DB directory and
        operation directory must have the adopted `.phone-restore/<UUID>`
        layout, and the journal supplies the expected identities.
        """
        live = Path(live_database)
        if (live.name != "jarvis.db" or self.root.name != self.operation_id
                or self.root.parent.name != ".phone-restore"
                or self.root.parent.parent != live.parent):
            raise RecoveryUnavailable("database recovery paths are not the fixed layout")
        root_info = self.root.lstat()
        live_dir_info = live.parent.lstat()
        if (not stat.S_ISDIR(root_info.st_mode) or root_info.st_uid != os.geteuid()
                or stat.S_IMODE(root_info.st_mode) & 0o077
                or not stat.S_ISDIR(live_dir_info.st_mode) or live_dir_info.st_uid != os.geteuid()
                or stat.S_IMODE(live_dir_info.st_mode) & 0o077):
            raise RecoveryUnavailable("database recovery directories are not private and owned")
        if root_info.st_dev != live_dir_info.st_dev:
            raise RecoveryUnavailable("database recovery paths are on different filesystems")
        restore_parent = self.root.parent
        parent_info = restore_parent.lstat()
        if (restore_parent.name != ".phone-restore" or not stat.S_ISDIR(parent_info.st_mode)
                or parent_info.st_uid != os.geteuid() or stat.S_IMODE(parent_info.st_mode) & 0o077
                or parent_info.st_dev != root_info.st_dev):
            raise RecoveryUnavailable("restore parent is not a private same-filesystem directory")
        if action == "move_to_quarantine" and name in {"wal", "shm", "database"}:
            source = {"wal": live.parent / "jarvis.db-wal",
                      "shm": live.parent / "jarvis.db-shm",
                      "database": live}[name]
            target = {"wal": self.root / "old.wal",
                      "shm": self.root / "old.shm",
                      "database": self.root / "old.db"}[name]
            expected_record = self.load()["files"][name]
            cleanup_name = {"wal": "old_wal", "shm": "old_shm", "database": "old_database"}[name]
        elif action == "install" and name == "staged_database":
            source, target = self.root / "staged.db", live
            state = self.load()
            if state["staged_database_sha256"] is None:
                raise RecoveryUnavailable("staged database digest is not journaled")
            expected_record = {"present": True, "size_bytes": None,
                               "sha256": state["staged_database_sha256"]}
            cleanup_name = "staged_database"
        else:
            raise RecoveryUnavailable("database rename is not allowlisted")
        if expected_sha256 != expected_record["sha256"]:
            raise RecoveryUnavailable("database rename digest does not match the journal")
        state = self.load()
        cleanup = state["cleanup_artifacts"][cleanup_name]
        if action == "install" and (cleanup["state"] != "pending"
                                     or cleanup["sha256"] != expected_sha256):
            raise RecoveryUnavailable("staged database cleanup identity is not journaled")

        source_record = _private_file_record(source, allow_missing=True)
        target_record = _private_file_record(target, allow_missing=True)
        if expected_sha256 is None:
            if (name not in {"wal", "shm"} or source_record.present or target_record.present
                    or expected_record["present"]):
                raise RecoveryUnavailable("only an absent WAL/SHM may skip quarantine")
        else:
            if (source_record.present and source_record.sha256 != expected_sha256
                    or target_record.present and target_record.sha256 != expected_sha256
                    or source_record.present == target_record.present):
                raise RecoveryUnavailable("database rename placement is ambiguous")

        latest_index = (RENAME_ORDER.index(state["rename_step"]["name"])
                        if state["rename_step"] is not None else None)
        already_done = ((action == "move_to_quarantine" and not source_record.present
                            and target_record.present and target_record.sha256 == expected_sha256
                            and cleanup["state"] in {"pending", "done"}
                            and cleanup["sha256"] == expected_sha256)
                        or (action == "install" and not source_record.present and target_record.present
                            and target_record.sha256 == expected_sha256
                            and state["installed_database_sha256"] == expected_sha256))
        if expected_sha256 is None and not source_record.present and not target_record.present:
            already_done = (state["phase"] != "installing"
                            or (latest_index is not None and latest_index > RENAME_ORDER.index(name))
                            or (state["rename_step"] is not None
                                and state["rename_step"]["name"] == name
                                and state["rename_step"]["state"] == "done"))
        if already_done:
            if state["phase"] != "installing" or (latest_index is not None
                    and latest_index > RENAME_ORDER.index(name)):
                return state
            # Re-sync on a replay after an interruption between rename and
            # directory fsync; placement alone is not the durability receipt.
            self._fsync_directory(source.parent)
            if target.parent != source.parent:
                self._fsync_directory(target.parent)
            return state
        if state["phase"] != "installing":
            raise RecoveryUnavailable("database rename is outside the installing phase")

        latest = state["rename_step"]
        step = {"name": name, "action": action, "expected_sha256": expected_sha256,
                "state": "intent"}
        if latest is not None and latest["state"] == "intent":
            if {key: latest[key] for key in ("name", "action", "expected_sha256")} != {
                    key: step[key] for key in ("name", "action", "expected_sha256")}:
                raise RecoveryUnavailable("a prior database rename intent is unresolved")
        else:
            self._require_prior_renames_done(state, name)
            candidate = dict(state)
            candidate["rename_step"] = step
            self.advance(candidate)

        if expected_sha256 is None:
            # Absence is a journaled observation, not a rename. The source
            # catalog recorded this sidecar absent before the install phase.
            pass
        elif source_record.present:
            # The owner lock and drained child provide the single-writer
            # exclusion. Destination absence was checked before the durable
            # intent; replacement is never used for database artifacts.
            try:
                os.rename(source, target)
            except OSError as exc:
                raise RecoveryUnavailable("database rename or directory sync is uncertain") from exc
            target_record = _private_file_record(target)
            if target_record.sha256 != expected_sha256:
                raise RecoveryUnavailable("database rename destination failed verification")
        elif not target_record.present or target_record.sha256 != expected_sha256:
            raise RecoveryUnavailable("database rename destination is not verified")
        self._fsync_directory(source.parent)
        if target.parent != source.parent:
            self._fsync_directory(target.parent)

        current = self.load()
        done = dict(current)
        done["rename_step"] = {**step, "state": "done"}
        if action == "move_to_quarantine":
            artifacts = dict(done["cleanup_artifacts"])
            artifacts[cleanup_name] = ({"state": "absent", "sha256": None}
                                       if expected_sha256 is None else
                                       {"state": "pending", "sha256": expected_sha256})
            done["cleanup_artifacts"] = artifacts
        else:
            done["installed_database_sha256"] = expected_sha256
            artifacts = dict(done["cleanup_artifacts"])
            artifacts["staged_database"] = {"state": "done", "sha256": expected_sha256}
            done["cleanup_artifacts"] = artifacts
        return self.advance(done)

    @staticmethod
    def _require_prior_renames_done(state: Mapping[str, Any], name: str) -> None:
        index = RENAME_ORDER.index(name)
        files = state["files"]
        cleanup = state["cleanup_artifacts"]
        done = {
            "wal": (not files["wal"]["present"] or cleanup["old_wal"]["state"] == "pending"),
            "shm": (not files["shm"]["present"] or cleanup["old_shm"]["state"] == "pending"),
            "database": cleanup["old_database"]["state"] == "pending",
            "staged_database": state["installed_database_sha256"] is not None,
        }
        for prior in RENAME_ORDER[:index]:
            if not done[prior]:
                raise RecoveryUnavailable("database renames must follow the fixed order")

    def _fsync_directory(self, directory: Path) -> None:
        try:
            fd = os.open(directory, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        except OSError as exc:
            raise RecoveryUnavailable("database directory sync is uncertain") from exc

    def _write_new(self, journal: Mapping[str, Any]) -> None:
        data = encode_journal(journal)
        self._reclaim_valid_orphan_temp()
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            fd = os.open(self.temp_path, flags, 0o600)
            try:
                view = memoryview(data)
                while view:
                    written = os.write(fd, view)
                    if written <= 0:
                        raise RecoveryUnavailable("journal write was incomplete")
                    view = view[written:]
                os.fsync(fd)
            finally:
                os.close(fd)
            os.replace(self.temp_path, self.path)
            self._fsync_root()
        except RecoveryUnavailable:
            raise
        except OSError as exc:
            raise RecoveryUnavailable("journal write, rename, or directory sync is uncertain") from exc

    def _reclaim_valid_orphan_temp(self) -> None:
        try:
            info = self.temp_path.lstat()
        except FileNotFoundError:
            return
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_nlink != 1
                or stat.S_IMODE(info.st_mode) & 0o077 or info.st_size > MAX_JOURNAL_BYTES
                or not self.path.exists()):
            raise RecoveryUnavailable("orphan journal temp cannot be safely reclaimed")
        current = decode_journal(_read_private_file(self.path, MAX_JOURNAL_BYTES))
        if current["operation_id"] != self.operation_id or current["manifest_sha256"] != self.manifest_sha256:
            raise RecoveryUnavailable("canonical journal identity mismatch")
        os.unlink(self.temp_path)
        self._fsync_root()

    def _fsync_root(self) -> None:
        fd = os.open(self.root, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def _read_private_file(path: Path, limit: int) -> bytes:
    """Read one owner-only regular file without following a symlink."""
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise RecoveryUnavailable("private recovery file cannot be opened") from exc
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_nlink != 1
                or stat.S_IMODE(info.st_mode) & 0o077 or info.st_size > limit):
            raise RecoveryUnavailable("private recovery file has unsafe ownership or mode")
        chunks: list[bytes] = []
        remaining = limit + 1
        while remaining:
            block = os.read(fd, min(remaining, 64 * 1024))
            if not block:
                break
            chunks.append(block)
            remaining -= len(block)
        data = b"".join(chunks)
        if len(data) > limit:
            raise RecoveryUnavailable("private recovery file exceeds its size limit")
        return data
    finally:
        os.close(fd)


def _private_file_record(path: Path, *, allow_missing: bool = False) -> FileRecord:
    """Hash one private regular file without following a final-component symlink."""
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags)
    except FileNotFoundError:
        if allow_missing:
            return FileRecord(False, 0, None)
        raise RecoveryUnavailable("required recovery file is missing")
    except OSError as exc:
        raise RecoveryUnavailable("recovery file cannot be opened safely") from exc
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_nlink != 1
                or stat.S_IMODE(info.st_mode) & 0o077 or info.st_size > MAX_DATABASE_BYTES
                or info.st_size <= 0):
            raise RecoveryUnavailable("recovery file ownership, mode, or size is invalid")
        digest = hashlib.sha256()
        total = 0
        while True:
            block = os.read(fd, 1024 * 1024)
            if not block:
                break
            total += len(block)
            if total > MAX_DATABASE_BYTES:
                raise RecoveryUnavailable("recovery file exceeds its size limit")
            digest.update(block)
        if total != info.st_size:
            raise RecoveryUnavailable("recovery file changed while being hashed")
        return FileRecord(True, total, digest.hexdigest())
    finally:
        os.close(fd)


def validate_normal_anchor(value: object) -> dict[str, Any]:
    """Closed stable protected shape for the normal-child startup snapshot."""
    from jarvis.bot.phone_remote_authority_channel import _state_from_wire
    base = {"anchor_version", "host_id", "host_generation", "transition_id",
            "transition_state", "login_counter"}
    if type(value) is not dict or type(value.get("anchor_version")) is not int:
        raise RecoveryUnavailable("invalid protected normal snapshot")
    version = value["anchor_version"]
    if version not in {1, 2} or value.keys() != (base if version == 1 else
            base | {"pending_restore", "last_completed_restore"}):
        raise RecoveryUnavailable("invalid protected normal schema")
    projection = {key: value[key] for key in base}
    projection["anchor_version"] = 1
    state = _state_from_wire(projection, allow_pending=False)
    if state.host_generation < 1 or len(state.host_id.encode("utf-8")) > 256:
        raise RecoveryUnavailable("invalid stable host identity")
    if version == 2:
        t = value["last_completed_restore"]
        if (value["pending_restore"] is not None or type(t) is not dict
                or t.keys() != {"operation_id", "target_generation", "manifest_sha256",
                                "checkpoint_sha256", "database_sha256"}
                or not _uuid(t["operation_id"])
                or type(t["target_generation"]) is not int
                or not 1 <= t["target_generation"] <= state.host_generation
                or any(not _digest(t[key]) for key in
                       ("manifest_sha256", "checkpoint_sha256", "database_sha256"))):
            raise RecoveryUnavailable("invalid stable completion tombstone")
    return json.loads(json.dumps(value))


def normal_service_receipt(db: sqlite3.Connection, protected_anchor: object) -> dict[str, Any]:
    """Read-only readiness gate; retained manifest paths are owner-derived."""
    anchor = validate_normal_anchor(protected_anchor)
    _validate_phone_catalog(db, _schema_rows(db))
    meta = _meta(db)
    if (meta["schema_version"] != anchor["anchor_version"]
            or meta["host_id"] != anchor["host_id"]
            or meta["host_generation"] != anchor["host_generation"]
            or meta["transition_state"] != "stable" or meta["transition_id"] is not None):
        raise RecoveryUnavailable("protected anchor and store are not a stable versioned pair")
    tombstone = anchor.get("last_completed_restore")
    if tombstone is None:
        if db.execute("SELECT 1 FROM sqlite_master WHERE name='phone_remote_restore_receipt'").fetchone():
            raise RecoveryUnavailable("v1 authority cannot carry a completion receipt")
    else:
        path = next((row[2] for row in db.execute("PRAGMA database_list") if row[1] == "main"), "")
        if not path:
            raise RecoveryUnavailable("completion requires a file-backed store")
        root = Path(path).parent / ".phone-restore" / tombstone["operation_id"]
        journal = RecoveryJournal(root, operation_id=tombstone["operation_id"],
                                  manifest_sha256=tombstone["manifest_sha256"])
        if journal.load()["phase"] != "complete":
            raise RecoveryUnavailable("recovery cleanup is incomplete")
        manifest_bytes = _read_private_file(root / "manifest.json", MAX_MANIFEST_BYTES)
        validate_receipt_tombstone(db, tombstone=tombstone,
            host_id=anchor["host_id"], retained_manifest_bytes=manifest_bytes)
    return {"host_id": anchor["host_id"], "host_generation": anchor["host_generation"],
            "store_schema_version": anchor["anchor_version"], "last_completed_restore": tombstone}


class RecoveryDiskExecutor:
    """Fixed-path disk effects used only by a supervised recovery child.

    The owner supplies the already-open source descriptor, immutable manifest,
    and protected snapshot over its inherited configuration. Wire requests can
    select neither a path nor another source. The child never writes an anchor.
    """
    def __init__(self, live_database: Path, journal: RecoveryJournal, source_fd: int,
                 protected_anchor: dict[str, Any]):
        self.live = Path(live_database)
        self.journal = journal
        self.manifest = journal.load_manifest()
        self.anchor = protected_anchor
        self.source_fd = source_fd
        if (self.live.name != "jarvis.db" or journal.root.parent.parent != self.live.parent
                or journal.root.parent.name != ".phone-restore"
                or journal.root.name != self.manifest["operation_id"]):
            raise RecoveryUnavailable("recovery paths are not fixed owner paths")
        self.checkpoint = journal.root / "checkpoint.db"
        record = _private_file_record(self.checkpoint)
        if (record.sha256 != self.manifest["checkpoint_sha256"]
                or record.size_bytes != self.manifest["checkpoint_size_bytes"]):
            raise RecoveryUnavailable("checkpoint identity mismatch")
        with self.connection(self.checkpoint) as db:
            validate_source_catalog(db)
            if authority_projection_sha256(db) != self.manifest["authority_sha256"]:
                raise RecoveryUnavailable("checkpoint authority mismatch")
            self.previous_receipt = None if _meta(db)["schema_version"] == 1 else _receipt_row(db)
        self.identity = {key: self.manifest[key] for key in
                         ("operation_id", "host_id", "base_generation", "target_generation",
                          "checkpoint_sha256", "authority_sha256")}
        self.identity["manifest_sha256"] = journal.manifest_sha256

    @staticmethod
    @contextlib.contextmanager
    def connection(path: Path, *, writable=False):
        _private_regular_file(path)
        db = sqlite3.connect(path.as_uri() + ("?mode=rw" if writable else "?mode=ro"),
                             uri=True, isolation_level=None, timeout=0)
        db.execute("PRAGMA foreign_keys=ON")
        try:
            yield db
        finally:
            db.close()

    @contextlib.contextmanager
    def source(self):
        info = os.fstat(self.source_fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) & 0o077
                or info.st_size != self.manifest["source_size_bytes"]):
            raise RecoveryUnavailable("source descriptor identity mismatch")
        data = os.pread(self.source_fd, info.st_size + 1, 0)
        if len(data) != info.st_size or hashlib.sha256(data).hexdigest() != self.manifest["source_sha256"]:
            raise RecoveryUnavailable("source descriptor content mismatch")
        db = sqlite3.connect(":memory:", isolation_level=None)
        try:
            db.deserialize(data)
            validate_source_catalog(db)
            if [tuple(row) for row in db.execute("PRAGMA quick_check")] != [("ok",)]:
                raise RecoveryUnavailable("source integrity failed")
            if db.execute("PRAGMA foreign_key_check").fetchone() is not None:
                raise RecoveryUnavailable("source foreign keys failed")
            yield db
        finally:
            db.close()

    def session(self, mode: str):
        if mode in {"prepare_resume", "recover"}:
            validate_pending_anchor_v2(self.anchor,
                manifest_bytes=_read_private_file(self.journal.root / "manifest.json", MAX_MANIFEST_BYTES),
                checkpoint_sha256=_private_file_record(self.checkpoint).sha256)
        elif mode == "prepare":
            validate_normal_anchor(self.anchor)
        else:
            raise RecoveryUnavailable("unsupported recovery mode")
        names = ({"preflight", "commit_pending"} if mode == "prepare" else
                 {"resume_preflight", "commit_pending"} if mode == "prepare_resume" else
                 {"inspect", "stage", "install", "commit_database"})
        return RecoveryProtocolSession(mode=mode, operation_id=self.manifest["operation_id"],
            host_id=self.manifest["host_id"], target_generation=self.manifest["target_generation"],
            manifest_sha256=self.journal.manifest_sha256,
            checkpoint_sha256=self.manifest["checkpoint_sha256"],
            authority_sha256=self.manifest["authority_sha256"],
            executors={name: getattr(self, name) for name in names})

    def result(self, **values):
        return {"operation_id": self.manifest["operation_id"], "status": "ok", **values}

    def database_state(self):
        with self.connection(self.live) as db:
            return inspect_database_state(db, **self.identity,
                base_database_sha256=self.manifest["base_database_sha256"],
                actual_database_sha256=_private_file_record(self.live).sha256,
                expected_previous_receipt=self.previous_receipt)

    def preflight(self, payload):
        with self.source():
            pass
        anchor = validate_normal_anchor(self.anchor)
        if (anchor["host_id"] != self.manifest["host_id"]
                or anchor["host_generation"] != self.manifest["base_generation"]
                or self.database_state() != "base"):
            raise RecoveryUnavailable("prepare requires the exact stable base")
        return self.result(manifest_sha256=self.journal.manifest_sha256,
            **{key: self.manifest[key] for key in
               ("checkpoint_sha256", "authority_sha256", "base_database_sha256", "checkpoint_size_bytes")})

    def resume_preflight(self, payload):
        validate_pending_anchor_v2(self.anchor,
            manifest_bytes=_read_private_file(self.journal.root / "manifest.json", MAX_MANIFEST_BYTES),
            checkpoint_sha256=_private_file_record(self.checkpoint).sha256)
        state = self.database_state()
        if state not in {"base", "pending"}:
            raise RecoveryUnavailable("resume does not match base or pending")
        return self.result(database_state=state, base_database_sha256=self.manifest["base_database_sha256"])

    def commit_pending(self, payload):
        # The owner sends this only after verified protected pending readback.
        if self.database_state() != "base":
            raise RecoveryUnavailable("pending commit requires exact base")
        with self.connection(self.live, writable=True) as db:
            apply_pending_database(db, **self.identity, expected_previous_receipt=self.previous_receipt)
        normalize_live_database(self.live)
        return self.result(host_id=self.manifest["host_id"],
            target_generation=self.manifest["target_generation"], transition_state="pending")

    def inspect(self, payload):
        state = self.journal.load()
        # During an interrupted quarantine the exact pending database may be at
        # old.db. Never use file existence alone as proof of a completed move.
        if state["phase"] == "installing" and not self.live.exists():
            path = self.journal.root / "old.db"
            if _private_file_record(path).sha256 != state["files"]["database"]["sha256"]:
                raise RecoveryUnavailable("quarantined database mismatch")
            database_state = "pending"
        else:
            database_state = self.database_state()
        return self.result(phase=state["phase"], database_state=database_state,
            checkpoint_sha256=self.manifest["checkpoint_sha256"],
            authority_sha256=self.manifest["authority_sha256"],
            base_database_sha256=self.manifest["base_database_sha256"],
            staged_database_sha256=state["staged_database_sha256"],
            installed_database_sha256=state["installed_database_sha256"])

    def stage(self, payload):
        if self.database_state() != "pending":
            raise RecoveryUnavailable("staging requires matching pending database")
        # Pending metadata is a separate committed image from the manifest's
        # pre-pending base. Freeze its quarantine identity before any rename.
        state = self.journal.load()
        if state["phase"] != "checkpoint_bound" or state["rename_step"] is not None:
            raise RecoveryUnavailable("pending file inventory is already frozen")
        files = {"database": _private_file_record(self.live).as_json(),
                 "wal": _private_file_record(Path(str(self.live) + "-wal"), allow_missing=True).as_json(),
                 "shm": _private_file_record(Path(str(self.live) + "-shm"), allow_missing=True).as_json()}
        if files["wal"]["present"] or files["shm"]["present"]:
            raise RecoveryUnavailable("pending database was not normalized")
        self.journal._write_new(dict(state, files=files))
        with self.source() as source, self.connection(self.checkpoint) as checkpoint:
            record = self.journal.stage_database(source, checkpoint,
                expected_previous_receipt=self.previous_receipt)
        return self.result(staged_database_sha256=record.sha256,
                           staged_size_bytes=record.size_bytes, store_schema_version=2)

    def install(self, payload):
        state = self.journal.load()
        if state["phase"] == "staged":
            state = self.journal.mark_quiesced()
        if state["phase"] == "quiesced":
            state = self.journal.begin_installation()
        if state["phase"] != "installing":
            raise RecoveryUnavailable("installation is not pending")
        for name in RENAME_ORDER:
            state = self.journal.load()
            step = state["rename_step"]
            if step is not None and RENAME_ORDER.index(step["name"]) > RENAME_ORDER.index(name):
                continue
            if step is not None and step["name"] == name and step["state"] == "done":
                continue
            self.journal.move_database_file(self.live, name=name,
                action="install" if name == "staged_database" else "move_to_quarantine",
                expected_sha256=state["staged_database_sha256"] if name == "staged_database"
                    else state["files"][name]["sha256"])
        state = self.journal.mark_installed()
        return self.result(installed_database_sha256=state["installed_database_sha256"], phase="installed")

    def commit_database(self, payload):
        state = self.journal.load()
        observed = self.database_state()
        if observed == "pending":
            if state["phase"] != "installed":
                raise RecoveryUnavailable("database is not installed")
            identity = dict(self.identity)
            del identity["base_generation"]
            with self.connection(self.live, writable=True) as db:
                commit_reconciled_database(db, **identity, expected_previous_receipt=self.previous_receipt)
        elif observed != "committed":
            raise RecoveryUnavailable("database is not pending or committed")
        if state["phase"] == "installed":
            state = self.journal.mark_database_committed()
        if state["phase"] == "database_committed":
            record = normalize_live_database(self.live)
            if self.database_state() != "committed":
                raise RecoveryUnavailable("completion failed read-only verification")
            state = self.journal.mark_database_finalized(record.sha256)
        if (state["phase"] != "database_finalized"
                or _private_file_record(self.live).sha256 != state["final_database_sha256"]):
            raise RecoveryUnavailable("final database digest is uncertain")
        return self.result(receipt_version=1, database_sha256=state["final_database_sha256"],
                           phase="database_committed")
