"""Offline durable-authority store contract for phone admission.

This is an isolated SQLite/fake-anchor candidate, not production wiring.  The
caller supplies both the SQLite connection and an independently protected
anchor implementation.  The only anchor used by tests is an in-memory fake.
No credentials, private keys, listeners, routes, or provider state live here.
"""
from __future__ import annotations

import json
import math
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Protocol

from jarvis.auth import ClientIdentity


SCHEMA_VERSION = 1
ALLOWED_SCOPES = frozenset({"read", "voice", "action", "calls"})
OFFER_TTL_S = 30.0
AUTHORITY_TABLES = frozenset({"phone_remote_meta", "phone_remote_devices",
                              "phone_remote_grants", "phone_remote_sessions"})
AUTHORITY_COLUMNS = {
    "phone_remote_meta": {"singleton_id", "schema_version", "host_id", "host_generation",
                          "transition_id", "transition_state"},
    "phone_remote_devices": {"device_id", "owner_id", "public_key", "key_algorithm", "revoked_at"},
    "phone_remote_grants": {"grant_id", "device_id", "owner_id", "scopes_json",
                            "grant_generation", "revoked_at"},
    "phone_remote_sessions": {"session_id", "host_id", "grant_id", "owner_id",
                              "login_incarnation", "host_generation", "session_generation",
                              "expires_at", "revoked_at"},
}
# Canonical schema is part of the authority contract.  Comparing normalized
# sqlite_master SQL catches lost PK/UNIQUE/CHECK/FK constraints, not just names.
SCHEMA_SQL = {
    "phone_remote_meta": """CREATE TABLE phone_remote_meta (
        singleton_id INTEGER PRIMARY KEY CHECK(singleton_id=1),
        schema_version INTEGER NOT NULL,
        host_id TEXT NOT NULL CHECK(length(trim(host_id)) > 0),
        host_generation INTEGER NOT NULL CHECK(host_generation > 0),
        transition_id TEXT,
        transition_state TEXT NOT NULL CHECK(transition_state IN ('stable','pending'))
    )""",
    "phone_remote_devices": """CREATE TABLE phone_remote_devices (
        device_id TEXT PRIMARY KEY CHECK(length(trim(device_id)) > 0),
        owner_id TEXT NOT NULL CHECK(length(trim(owner_id)) > 0),
        public_key BLOB NOT NULL CHECK(length(public_key) > 0),
        key_algorithm TEXT NOT NULL CHECK(length(trim(key_algorithm)) > 0),
        revoked_at REAL,
        UNIQUE(device_id, owner_id)
    )""",
    "phone_remote_grants": """CREATE TABLE phone_remote_grants (
        grant_id TEXT PRIMARY KEY CHECK(length(trim(grant_id)) > 0),
        device_id TEXT NOT NULL,
        owner_id TEXT NOT NULL,
        scopes_json TEXT NOT NULL,
        grant_generation INTEGER NOT NULL CHECK(grant_generation > 0),
        revoked_at REAL,
        UNIQUE(grant_id, owner_id),
        FOREIGN KEY(device_id, owner_id) REFERENCES phone_remote_devices(device_id, owner_id)
    )""",
    "phone_remote_sessions": """CREATE TABLE phone_remote_sessions (
        session_id TEXT PRIMARY KEY CHECK(length(trim(session_id)) > 0),
        host_id TEXT NOT NULL CHECK(length(trim(host_id)) > 0),
        grant_id TEXT NOT NULL,
        owner_id TEXT NOT NULL,
        login_incarnation TEXT NOT NULL UNIQUE,
        host_generation INTEGER NOT NULL CHECK(host_generation > 0),
        session_generation INTEGER NOT NULL CHECK(session_generation > 0),
        expires_at REAL NOT NULL,
        revoked_at REAL,
        FOREIGN KEY(grant_id, owner_id) REFERENCES phone_remote_grants(grant_id, owner_id)
    )""",
}
_PROCESS_EPOCH = uuid.uuid4().hex
_PROCESS_ADMISSIONS: set[tuple[int, str, str, str]] = set()


class StoreDenied(Exception):
    """Fail-closed refusal; callers should not infer existence from details."""


class StoreUnavailable(Exception):
    """Anchor or SQLite state cannot be safely used right now."""


@dataclass(frozen=True)
class AnchorState:
    anchor_version: int
    host_id: str
    host_generation: int
    transition_id: str | None
    transition_state: str
    login_counter: int


@dataclass(frozen=True)
class SessionBinding:
    owner_id: str
    device_id: str
    grant_id: str
    session_id: str
    login_incarnation: str
    host_id: str
    host_generation: int
    grant_generation: int
    session_generation: int
    process_epoch: str
    scopes: frozenset[str]


class ProtectedAnchor(Protocol):
    """Injected anchor; `exclusive` must serialize all writers/readers sharing authority."""
    def read(self) -> AnchorState: ...
    def write(self, state: AnchorState) -> None: ...
    def exclusive(self): ...


class FakeProtectedAnchor:
    """Deterministic injected anchor for isolated tests only."""

    def __init__(self, host_id: str = "host-test") -> None:
        self.state = AnchorState(1, host_id, 1, None, "stable", 0)
        self.available = True
        self.fail_next_write = False
        self._serialization_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._exclusive_owner: int | None = None

    @contextmanager
    def exclusive(self):
        """Non-reentrant authority-wide mutex shared by all stores using anchor."""
        ident = threading.get_ident()
        with self._state_lock:
            if self._exclusive_owner == ident:
                raise StoreUnavailable("authority lock reentry is forbidden")
        self._serialization_lock.acquire()
        try:
            with self._state_lock:
                self._exclusive_owner = ident
            yield
        finally:
            with self._state_lock:
                self._exclusive_owner = None
            self._serialization_lock.release()

    def _require_exclusive(self):
        with self._state_lock:
            if self._exclusive_owner != threading.get_ident():
                raise StoreUnavailable("anchor access requires exclusive authority lock")

    def read(self) -> AnchorState:
        self._require_exclusive()
        if not self.available:
            raise StoreUnavailable("anchor unavailable")
        return self.state

    def write(self, state: AnchorState) -> None:
        self._require_exclusive()
        if not self.available:
            raise StoreUnavailable("anchor unavailable")
        if self.fail_next_write:
            self.fail_next_write = False
            raise StoreUnavailable("anchor write failed")
        self.state = state


class PhoneAdmissionStore:
    """Small transactional authority store with an injected external anchor.

    SQLite must be disposable/test-local here. `host_generation` binds all
    persisted sessions and one-use tickets; the anchor's monotonically
    increasing login counter contributes a never-reused incarnation to each
    login. All mutating operations serialize on one process lock and use an
    SQLite transaction. Anchor transitions deliberately fail closed if they
    are interrupted; recovery is not inferred from database contents.
    """

    def __init__(self, connection: sqlite3.Connection, anchor: ProtectedAnchor,
                 *, failpoint=None, process_epoch: str | None = None) -> None:
        self.db = connection
        self.anchor = anchor
        self.failpoint = failpoint
        self.process_epoch = _PROCESS_EPOCH if process_epoch is None else self._text(process_epoch, "process_epoch")
        self._lock = threading.RLock()
        # Tickets are process-local only: an intact restart cannot revive them.
        self._tickets: dict[str, dict[str, object]] = {}
        if self.db.in_transaction:
            raise StoreUnavailable("store requires exclusive transaction ownership")
        # Never rely on the caller's SQLite default; DML contexts must have a
        # real rollback boundary, including when injected connection was autocommit.
        self.db.isolation_level = "IMMEDIATE"
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        if self.db.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
            raise StoreUnavailable("SQLite foreign-key enforcement is unavailable")
        self.db.execute("PRAGMA busy_timeout=250")
        self._create_schema()

    def _hit(self, name: str) -> None:
        if self.failpoint is not None:
            self.failpoint(name)

    @contextmanager
    def _authority_guard(self):
        # The outer guard coordinates all Store objects sharing one protected
        # anchor. Acquire it first: a same-thread reentry must be rejected before
        # it can wait on another Store object's local lock.
        with self.anchor.exclusive(), self._lock:
            yield

    def _write_anchor(self, state: AnchorState) -> None:
        try:
            self.anchor.write(state)
            if self.anchor.read() != state:
                raise StoreUnavailable("anchor write did not verify")
        except StoreUnavailable:
            raise
        except Exception as exc:
            raise StoreUnavailable("anchor write/readback failed") from exc

    def _global_security_transition(self, mutate, label: str) -> int:
        """Fence every remote session around one authority mutation.

        Caller holds ``_authority_guard`` and has completed all non-mutating
        authorization/target validation.  The pending anchor is durable before
        SQLite changes; any interruption thereafter leaves admission fail-closed.
        """
        old = self._check_pair()
        transition = f"{label}:{uuid.uuid4().hex}"
        generation = old.host_generation + 1
        pending = AnchorState(old.anchor_version, old.host_id, generation,
                              transition, "pending", old.login_counter)
        self._hit(f"{label}_before_anchor_pending")
        self._write_anchor(pending)
        self._hit(f"{label}_anchor_pending")
        with self.db:
            self.db.execute("UPDATE phone_remote_meta SET host_generation=?,transition_id=?,transition_state='pending' WHERE singleton_id=1",
                            (generation, transition))
            mutate()
            self.db.execute("UPDATE phone_remote_sessions SET revoked_at=COALESCE(revoked_at,0),session_generation=session_generation+1 WHERE revoked_at IS NULL")
            self._hit(f"{label}_before_db_commit")
        self._hit(f"{label}_db_committed")
        stable = AnchorState(old.anchor_version, old.host_id, generation,
                             None, "stable", old.login_counter)
        self._hit(f"{label}_before_anchor_finalize")
        self._write_anchor(stable)
        self._hit(f"{label}_anchor_finalized")
        with self.db:
            self.db.execute("UPDATE phone_remote_meta SET transition_id=NULL,transition_state='stable' WHERE singleton_id=1")
        self._tickets.clear()
        self._drop_admissions()
        return generation

    def _create_schema(self) -> None:
        with self._authority_guard(), self.db:
            preexisting_tables = {row[0] for row in self.db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
            self._validate_authority_schema(allow_empty=True)
            self.db.executescript(";\n".join(
                sql.replace("CREATE TABLE ", "CREATE TABLE IF NOT EXISTS ", 1)
                for sql in SCHEMA_SQL.values()) + ";")
            self._validate_authority_schema(allow_empty=False)
            meta = self.db.execute("SELECT * FROM phone_remote_meta WHERE singleton_id=1").fetchone()
            if meta is None:
                if preexisting_tables & AUTHORITY_TABLES:
                    raise StoreUnavailable("metadata missing from an existing authority schema; no bootstrap")
                anchor = self.anchor.read()
                self._validate_anchor(anchor)
                self.db.execute("INSERT INTO phone_remote_meta VALUES(1,?,?,?,NULL,'stable')",
                                (SCHEMA_VERSION, anchor.host_id, anchor.host_generation))
            elif (meta["schema_version"] != SCHEMA_VERSION
                  or meta["transition_state"] != "stable"
                  or meta["transition_id"] is not None):
                raise StoreUnavailable("unsupported or pending store schema")
            self._check_pair()

    def _check_pair(self) -> AnchorState:
        self._validate_authority_schema(allow_empty=False)
        try:
            anchor = self.anchor.read()
        except Exception as exc:
            raise StoreUnavailable("anchor cannot be read") from exc
        self._validate_anchor(anchor)
        row = self.db.execute("SELECT * FROM phone_remote_meta WHERE singleton_id=1").fetchone()
        if (row is None or anchor.transition_state != "stable" or anchor.transition_id is not None
                or row["transition_state"] != "stable"
                or row["transition_id"] is not None
                or row["schema_version"] != SCHEMA_VERSION
                or row["host_id"] != anchor.host_id
                or row["host_generation"] != anchor.host_generation):
            raise StoreUnavailable("anchor and database are not a stable matching pair")
        for session in self.db.execute("""SELECT host_id,login_incarnation,host_generation,revoked_at
                FROM phone_remote_sessions"""):
            parsed = self._parse_incarnation(session["login_incarnation"])
            if (parsed is None or session["host_id"] != parsed[0]
                    or session["host_generation"] != parsed[1]):
                raise StoreUnavailable("active session contradicts protected anchor")
            if parsed[0] == anchor.host_id and (parsed[2] > anchor.login_counter
                                                or parsed[1] > anchor.host_generation):
                raise StoreUnavailable("stored incarnation exceeds protected anchor")
            if session["revoked_at"] is None and (parsed[0] != anchor.host_id
                    or parsed[1] != anchor.host_generation
                    or session["host_generation"] != anchor.host_generation):
                raise StoreUnavailable("active session contradicts protected anchor")
        return anchor

    def _validate_authority_schema(self, *, allow_empty: bool) -> None:
        if self.db.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
            raise StoreUnavailable("SQLite foreign-key enforcement is disabled")
        names = {row[0] for row in self.db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
        present = names & AUTHORITY_TABLES
        if not present:
            if allow_empty:
                return
            raise StoreUnavailable("authority schema is incomplete")
        if present != AUTHORITY_TABLES:
            raise StoreUnavailable("partial authority schema; no repair/bootstrap")
        for table, expected in AUTHORITY_COLUMNS.items():
            actual = {row[1] for row in self.db.execute(f"PRAGMA table_info({table})")}
            if actual != expected:
                raise StoreUnavailable("authority table columns are malformed")
            row = self.db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
                                  (table,)).fetchone()
            if row is None or self._normalize_ddl(row[0]) != self._normalize_ddl(SCHEMA_SQL[table]):
                raise StoreUnavailable("authority table constraints differ from canonical schema")
        altered = self.db.execute("""SELECT 1 FROM sqlite_master
            WHERE tbl_name IN (?,?,?,?) AND type IN ('trigger','index')
              AND name NOT LIKE 'sqlite_autoindex_%' LIMIT 1""", tuple(AUTHORITY_TABLES)).fetchone()
        if altered is not None:
            raise StoreUnavailable("unexpected authority trigger or index")
        if self.db.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise StoreUnavailable("authority schema contains foreign-key violations")

    @staticmethod
    def _normalize_ddl(sql: str) -> str:
        # sqlite_master preserves quoted identifiers and string-literal case;
        # collapsing whitespace is safe, lowercasing/removing quotes is not.
        return " ".join(sql.split())

    @staticmethod
    def _parse_incarnation(value: object) -> tuple[str, int, int] | None:
        if type(value) is not str:
            return None
        try:
            host_id, generation, counter = value.rsplit(":", 2)
            if not host_id or not generation.isdecimal() or not counter.isdecimal():
                return None
            return host_id, int(generation), int(counter)
        except (ValueError, AttributeError):
            return None

    @staticmethod
    def _valid_scopes(encoded: object) -> list[str] | None:
        try:
            scopes = json.loads(encoded)
        except (TypeError, ValueError):
            return None
        if (type(scopes) is not list or not scopes
                or any(type(scope) is not str or scope not in ALLOWED_SCOPES for scope in scopes)
                or len(set(scopes)) != len(scopes)):
            return None
        return scopes

    def _admission_key(self, session_id: str, incarnation: str) -> tuple[int, str, str, str]:
        return (id(self.anchor), self.process_epoch, session_id, incarnation)

    def _drop_admissions(self, session_id: str | None = None) -> None:
        anchor_id = id(self.anchor)
        retained = {entry for entry in _PROCESS_ADMISSIONS
                    if entry[0] != anchor_id or (session_id is not None and entry[2] != session_id)}
        _PROCESS_ADMISSIONS.clear()
        _PROCESS_ADMISSIONS.update(retained)

    @staticmethod
    def _validate_anchor(anchor: object) -> None:
        if (type(anchor) is not AnchorState or type(anchor.anchor_version) is not int
                or anchor.anchor_version != 1 or type(anchor.host_id) is not str
                or not anchor.host_id.strip() or type(anchor.host_generation) is not int
                or anchor.host_generation <= 0 or type(anchor.login_counter) is not int
                or anchor.login_counter < 0 or anchor.transition_state != "stable"
                or anchor.transition_id is not None):
            raise StoreUnavailable("anchor missing, malformed, or transitioning")

    @staticmethod
    def _text(value: object, name: str) -> str:
        if type(value) is not str or not value.strip() or value != value.strip():
            raise StoreDenied(f"invalid {name}")
        return value

    @staticmethod
    def _verified_owner(identity: object, claimed_owner: str) -> str:
        if (type(identity) is not ClientIdentity or type(identity.name) is not str
                or not identity.name.strip() or type(identity.user_id) is not str
                or not identity.user_id.strip() or identity.user_id != claimed_owner):
            raise StoreDenied("verified identity required")
        return identity.user_id

    def add_device(self, *, identity: ClientIdentity, device_id: str, owner_id: str, public_key: bytes,
                   key_algorithm: str) -> None:
        device_id = self._text(device_id, "device_id")
        owner_id = self._text(owner_id, "owner_id")
        owner_id = self._verified_owner(identity, owner_id)
        key_algorithm = self._text(key_algorithm, "key_algorithm")
        if type(public_key) is not bytes or not public_key:
            raise StoreDenied("invalid public key")
        with self._authority_guard():
            self._check_pair()
            if self.db.execute("SELECT 1 FROM phone_remote_devices WHERE device_id=?", (device_id,)).fetchone():
                raise StoreDenied("device conflict")
            try:
                self._global_security_transition(lambda: self.db.execute(
                    "INSERT INTO phone_remote_devices VALUES(?,?,?,?,NULL)",
                    (device_id, owner_id, public_key, key_algorithm)), "device_enroll")
            except sqlite3.IntegrityError as exc:
                raise StoreDenied("device conflict") from exc

    def add_grant(self, *, identity: ClientIdentity, grant_id: str, device_id: str, owner_id: str,
                  scopes: list[str]) -> None:
        grant_id = self._text(grant_id, "grant_id")
        device_id = self._text(device_id, "device_id")
        owner_id = self._text(owner_id, "owner_id")
        owner_id = self._verified_owner(identity, owner_id)
        if (type(scopes) is not list or not scopes or
                any(type(s) is not str or s not in ALLOWED_SCOPES for s in scopes)
                or len(set(scopes)) != len(scopes)):
            raise StoreDenied("invalid scopes")
        encoded = json.dumps(scopes, separators=(",", ":"), sort_keys=True)
        with self._authority_guard():
            self._check_pair()
            device = self.db.execute("SELECT owner_id,revoked_at FROM phone_remote_devices WHERE device_id=?",
                                     (device_id,)).fetchone()
            if device is None or device["owner_id"] != owner_id or device["revoked_at"] is not None:
                raise StoreDenied("device owner mismatch")
            if self.db.execute("SELECT 1 FROM phone_remote_grants WHERE grant_id=?", (grant_id,)).fetchone():
                raise StoreDenied("grant conflict")
            try:
                self._global_security_transition(lambda: self.db.execute(
                    "INSERT INTO phone_remote_grants VALUES(?,?,?,?,1,NULL)",
                    (grant_id, device_id, owner_id, encoded)), "grant_enroll")
            except sqlite3.IntegrityError as exc:
                raise StoreDenied("grant conflict") from exc

    def replace_device_credential(self, *, identity: ClientIdentity, device_id: str,
                                  owner_id: str, public_key: bytes,
                                  key_algorithm: str) -> None:
        """Replace verification material under a global generation transition."""
        device_id = self._text(device_id, "device_id")
        owner_id = self._verified_owner(identity, self._text(owner_id, "owner_id"))
        key_algorithm = self._text(key_algorithm, "key_algorithm")
        if type(public_key) is not bytes or not public_key:
            raise StoreDenied("invalid public key")
        with self._authority_guard():
            self._check_pair()
            row = self.db.execute("SELECT owner_id,public_key,key_algorithm,revoked_at FROM phone_remote_devices WHERE device_id=?",
                                  (device_id,)).fetchone()
            if row is None or row["owner_id"] != owner_id or row["revoked_at"] is not None:
                raise StoreDenied("device unavailable")
            if row["public_key"] == public_key and row["key_algorithm"] == key_algorithm:
                return
            self._global_security_transition(lambda: self.db.execute(
                "UPDATE phone_remote_devices SET public_key=?,key_algorithm=? WHERE device_id=?",
                (public_key, key_algorithm, device_id)), "credential_replace")

    def login(self, *, identity: ClientIdentity, session_id: str, grant_id: str, owner_id: str,
              now: float, expires_at: float) -> str:
        session_id = self._text(session_id, "session_id")
        grant_id = self._text(grant_id, "grant_id")
        owner_id = self._text(owner_id, "owner_id")
        owner_id = self._verified_owner(identity, owner_id)
        if (type(now) not in (int, float) or type(expires_at) not in (int, float)
                or not math.isfinite(now) or not math.isfinite(expires_at) or expires_at <= now):
            raise StoreDenied("invalid session lifetime")
        with self._authority_guard():
            anchor = self._check_pair()
            grant = self.db.execute("""SELECT g.*,d.owner_id AS device_owner,d.revoked_at AS device_revoked
                FROM phone_remote_grants g JOIN phone_remote_devices d USING(device_id)
                WHERE g.grant_id=?""", (grant_id,)).fetchone()
            if (grant is None or grant["owner_id"] != owner_id or grant["device_owner"] != owner_id
                    or grant["revoked_at"] is not None or grant["device_revoked"] is not None):
                raise StoreDenied("grant unavailable")
            if self._valid_scopes(grant["scopes_json"]) is None:
                raise StoreDenied("grant scope data is invalid")
            previous = self.db.execute("SELECT revoked_at FROM phone_remote_sessions WHERE session_id=?",
                                       (session_id,)).fetchone()
            if previous is not None and previous["revoked_at"] is None:
                old = self.db.execute("SELECT login_incarnation FROM phone_remote_sessions WHERE session_id=?",
                                      (session_id,)).fetchone()[0]
                if self._admission_key(session_id, old) in _PROCESS_ADMISSIONS:
                    raise StoreDenied("session already admitted in this process")
            counter = anchor.login_counter + 1
            incarnation = f"{anchor.host_id}:{anchor.host_generation}:{counter}"
            pending = AnchorState(anchor.anchor_version, anchor.host_id, anchor.host_generation,
                                  f"login:{uuid.uuid4().hex}", "pending", counter)
            self._hit("login_before_anchor_reservation")
            self._write_anchor(pending)
            self._hit("login_anchor_reserved")
            try:
                with self.db:
                    self._check_transition(pending)
                    previous = self.db.execute("SELECT * FROM phone_remote_sessions WHERE session_id=?",
                                               (session_id,)).fetchone()
                    if previous is None:
                        self.db.execute("INSERT INTO phone_remote_sessions VALUES(?,?,?,?,?,?,?,?,NULL)",
                                        (session_id, anchor.host_id, grant_id, owner_id, incarnation,
                                         anchor.host_generation, 1, expires_at))
                    else:
                        self.db.execute("""UPDATE phone_remote_sessions SET host_id=?,grant_id=?,owner_id=?,
                            login_incarnation=?,host_generation=?,session_generation=?,expires_at=?,revoked_at=NULL
                            WHERE session_id=?""", (anchor.host_id, grant_id, owner_id, incarnation,
                            anchor.host_generation, previous["session_generation"] + 1, expires_at, session_id))
                    self._hit("login_before_db_commit")
                self._hit("login_db_committed")
                stable = AnchorState(anchor.anchor_version, anchor.host_id, anchor.host_generation,
                                     None, "stable", counter)
                self._hit("login_before_anchor_finalize")
                self._write_anchor(stable)
                self._hit("login_anchor_finalized")
                self._drop_admissions(session_id)
                _PROCESS_ADMISSIONS.add(self._admission_key(session_id, incarnation))
            except Exception:
                # A pending anchor permanently blocks use until trusted recovery.
                raise
            return incarnation

    def issue_ticket(self, *, identity: ClientIdentity, ticket_id: str, session_id: str, owner_id: str,
                     purpose: str, payload_digest: str, now: float, expires_at: float,
                     peer_id: str | None = None) -> None:
        ticket_id = self._text(ticket_id, "ticket_id")
        session_id = self._text(session_id, "session_id")
        owner_id = self._text(owner_id, "owner_id")
        owner_id = self._verified_owner(identity, owner_id)
        payload_digest = self._text(payload_digest, "payload_digest")
        if purpose == "update":
            peer_id = self._text(peer_id, "peer_id")
        elif purpose == "offer" and peer_id is not None:
            raise StoreDenied("new offer cannot preselect a peer")
        if (purpose not in ("offer", "update") or type(now) not in (int, float)
                or type(expires_at) not in (int, float) or not math.isfinite(now)
                or not math.isfinite(expires_at) or expires_at <= now
                or expires_at - now > OFFER_TTL_S):
            raise StoreDenied("invalid ticket")
        with self._authority_guard():
            anchor = self._check_pair()
            row = self.db.execute("""SELECT s.*,g.revoked_at AS grant_revoked,
                       g.grant_id AS current_grant_id,g.grant_generation,g.scopes_json,
                       g.owner_id AS grant_owner,d.device_id,d.owner_id AS device_owner,
                       d.revoked_at AS device_revoked
                FROM phone_remote_sessions s JOIN phone_remote_grants g USING(grant_id)
                JOIN phone_remote_devices d USING(device_id) WHERE s.session_id=?""",
                                  (session_id,)).fetchone()
            if (row is None or row["owner_id"] != owner_id or row["revoked_at"] is not None
                    or row["grant_revoked"] is not None or row["device_revoked"] is not None
                    or row["expires_at"] <= now or row["host_generation"] != anchor.host_generation
                    or row["host_id"] != anchor.host_id):
                raise StoreDenied("session unavailable")
            scopes = self._valid_scopes(row["scopes_json"])
            if (scopes is None or "voice" not in scopes
                    or row["grant_owner"] != owner_id or row["device_owner"] != owner_id):
                raise StoreDenied("voice scope or owner unavailable")
            if self._admission_key(session_id, row["login_incarnation"]) not in _PROCESS_ADMISSIONS:
                raise StoreDenied("fresh process admission required")
            if ticket_id in self._tickets:
                raise StoreDenied("ticket conflict")
            self._tickets[ticket_id] = {
                "session_id": session_id, "owner_id": owner_id,
                "device_id": row["device_id"], "grant_id": row["current_grant_id"],
                "grant_generation": row["grant_generation"],
                "session_generation": row["session_generation"],
                "login_incarnation": row["login_incarnation"],
                "host_id": anchor.host_id,
                "host_generation": anchor.host_generation, "purpose": purpose,
                "peer_id": peer_id,
                "payload_digest": payload_digest, "expires_at": expires_at,
                "consumed": False,
            }

    def consume_ticket(self, *, identity: ClientIdentity, ticket_id: str, session_id: str, owner_id: str,
                       purpose: str, payload_digest: str, now: float,
                       peer_id: str | None = None) -> SessionBinding:
        """Atomically consume once only while current session identity matches."""
        ticket_id = self._text(ticket_id, "ticket_id")
        session_id = self._text(session_id, "session_id")
        owner_id = self._verified_owner(identity, self._text(owner_id, "owner_id"))
        payload_digest = self._text(payload_digest, "payload_digest")
        if purpose == "update":
            peer_id = self._text(peer_id, "peer_id")
        elif purpose == "offer" and peer_id is not None:
            raise StoreDenied("offer cannot bind an existing peer")
        if (purpose not in ("offer", "update") or type(now) not in (int, float)
                or not math.isfinite(now)):
            raise StoreDenied("invalid ticket consume")
        with self._authority_guard():
            anchor = self._check_pair()
            try:
                with self.db:
                    ticket = self._tickets.get(ticket_id)
                    if (ticket is None or ticket["consumed"] or ticket["session_id"] != session_id
                            or ticket["owner_id"] != owner_id or ticket["purpose"] != purpose
                            or ticket["peer_id"] != peer_id
                            or ticket["payload_digest"] != payload_digest
                            or ticket["expires_at"] <= now
                            or ticket["host_generation"] != anchor.host_generation):
                        raise StoreDenied("ticket stale or invalid")
                    row = self.db.execute("""SELECT s.owner_id,s.host_id,s.grant_id,s.login_incarnation AS current_incarnation,
                              s.host_generation AS session_host,s.expires_at AS session_expires,
                              s.session_generation,g.grant_generation,g.scopes_json,
                              g.owner_id AS grant_owner,d.device_id,d.owner_id AS device_owner,
                              s.revoked_at AS session_revoked,g.revoked_at AS grant_revoked,
                              d.revoked_at AS device_revoked
                        FROM phone_remote_sessions s
                        JOIN phone_remote_grants g USING(grant_id)
                        JOIN phone_remote_devices d USING(device_id)
                        WHERE s.session_id=?""", (session_id,)).fetchone()
                    if (row is None or row["owner_id"] != owner_id
                            or row["host_id"] != anchor.host_id
                            or ticket["login_incarnation"] != row["current_incarnation"]
                            or ticket["device_id"] != row["device_id"]
                            or ticket["grant_id"] != row["grant_id"]
                            or ticket["grant_generation"] != row["grant_generation"]
                            or ticket["session_generation"] != row["session_generation"]
                            or ticket["host_id"] != anchor.host_id
                            or ticket["host_generation"] != row["session_host"]
                            or row["session_expires"] <= now
                            or row["session_revoked"] is not None or row["grant_revoked"] is not None
                            or row["device_revoked"] is not None
                            or row["session_host"] != anchor.host_generation
                            ):
                        raise StoreDenied("ticket stale or invalid")
                    scopes = self._valid_scopes(row["scopes_json"])
                    if (scopes is None or "voice" not in scopes
                            or row["grant_owner"] != owner_id or row["device_owner"] != owner_id):
                        raise StoreDenied("ticket scope or owner is stale")
                    if self._admission_key(session_id, row["current_incarnation"]) not in _PROCESS_ADMISSIONS:
                        raise StoreDenied("fresh process admission required")
                    ticket["consumed"] = True
                    return SessionBinding(owner_id, row["device_id"], row["grant_id"], session_id,
                        row["current_incarnation"], anchor.host_id, anchor.host_generation,
                        row["grant_generation"], row["session_generation"], self.process_epoch,
                        frozenset(scopes))
            except sqlite3.IntegrityError as exc:
                raise StoreDenied("ticket invalid") from exc

    def revoke_session(self, *, identity: ClientIdentity, session_id: str, owner_id: str) -> None:
        session_id = self._text(session_id, "session_id")
        owner_id = self._verified_owner(identity, self._text(owner_id, "owner_id"))
        with self._authority_guard():
            self._check_pair()
            with self.db:
                changed = self.db.execute("UPDATE phone_remote_sessions SET revoked_at=0,session_generation=session_generation+1 WHERE session_id=? AND owner_id=? AND revoked_at IS NULL",
                                          (session_id, owner_id)).rowcount
                if changed != 1:
                    raise StoreDenied("session unavailable")
                self._tickets = {key: value for key, value in self._tickets.items()
                                 if value["session_id"] != session_id}
                self._drop_admissions(session_id)

    def revoke_grant(self, *, identity: ClientIdentity, grant_id: str, owner_id: str) -> None:
        grant_id = self._text(grant_id, "grant_id")
        owner_id = self._verified_owner(identity, self._text(owner_id, "owner_id"))
        with self._authority_guard():
            self._check_pair()
            grant = self.db.execute("SELECT owner_id,revoked_at FROM phone_remote_grants WHERE grant_id=?",
                                    (grant_id,)).fetchone()
            if grant is None or grant["owner_id"] != owner_id or grant["revoked_at"] is not None:
                raise StoreDenied("grant unavailable")
            self._global_security_transition(lambda: self.db.execute(
                "UPDATE phone_remote_grants SET revoked_at=0,grant_generation=grant_generation+1 WHERE grant_id=?",
                (grant_id,)), "grant_revoke")

    def update_grant_scopes(self, *, identity: ClientIdentity, grant_id: str,
                            owner_id: str, scopes: list[str]) -> None:
        """Replace scopes under a global fence; broadening also changes authority."""
        grant_id = self._text(grant_id, "grant_id")
        owner_id = self._verified_owner(identity, self._text(owner_id, "owner_id"))
        if (type(scopes) is not list or not scopes or
                any(type(s) is not str or s not in ALLOWED_SCOPES for s in scopes)
                or len(set(scopes)) != len(scopes)):
            raise StoreDenied("invalid scopes")
        encoded = json.dumps(scopes, separators=(",", ":"), sort_keys=True)
        with self._authority_guard():
            self._check_pair()
            grant = self.db.execute("SELECT owner_id,revoked_at,scopes_json FROM phone_remote_grants WHERE grant_id=?",
                                    (grant_id,)).fetchone()
            if grant is None or grant["owner_id"] != owner_id or grant["revoked_at"] is not None:
                raise StoreDenied("grant unavailable")
            if self._valid_scopes(grant["scopes_json"]) == json.loads(encoded):
                return
            self._global_security_transition(lambda: self.db.execute(
                "UPDATE phone_remote_grants SET scopes_json=?,grant_generation=grant_generation+1 WHERE grant_id=?",
                (encoded, grant_id)), "grant_scope")

    def revoke_device(self, *, identity: ClientIdentity, device_id: str, owner_id: str) -> None:
        device_id = self._text(device_id, "device_id")
        owner_id = self._verified_owner(identity, self._text(owner_id, "owner_id"))
        with self._authority_guard():
            self._check_pair()
            device = self.db.execute("SELECT owner_id,revoked_at FROM phone_remote_devices WHERE device_id=?",
                                     (device_id,)).fetchone()
            if device is None or device["owner_id"] != owner_id or device["revoked_at"] is not None:
                raise StoreDenied("device unavailable")
            def revoke():
                self.db.execute("UPDATE phone_remote_devices SET revoked_at=0 WHERE device_id=?", (device_id,))
                self.db.execute("UPDATE phone_remote_grants SET revoked_at=0,grant_generation=grant_generation+1 WHERE device_id=? AND revoked_at IS NULL", (device_id,))
            self._global_security_transition(revoke, "device_revoke")

    def advance_host_generation(self) -> int:
        """Supported pre-restore fence; unhooked or simultaneous rollback is not detected here.

        The caller must invoke this before every supported database/release
        restore. An old database image then mismatches protected generation and
        stays unavailable for trusted recovery; this is not general rollback
        detection or restore completion.
        """
        with self._authority_guard():
            return self._global_security_transition(lambda: None, "generation")

    def _check_transition(self, anchor: AnchorState) -> None:
        current = self.anchor.read()
        if current != anchor:
            raise StoreUnavailable("anchor transition changed")

    @contextmanager
    def serialized_authority(self):
        """Narrow commit window shared with every authority mutation."""
        with self._authority_guard():
            yield

    def binding_current(self, binding: SessionBinding, *, now: float) -> bool:
        """Check the complete immutable session binding against current authority."""
        if type(binding) is not SessionBinding or type(now) not in (int, float) or not math.isfinite(now):
            return False
        with self._authority_guard():
            return self._binding_current_locked(binding, now=now)

    def binding_current_serialized(self, binding: SessionBinding, *, now: float) -> bool:
        """Variant for callers already inside serialized_authority()."""
        return self._binding_current_locked(binding, now=now)

    def _binding_current_locked(self, binding, *, now):
            anchor = self._check_pair()
            row = self.db.execute("""SELECT s.*,g.grant_generation,g.scopes_json,g.revoked_at AS gr,
                g.owner_id AS go,d.device_id,d.owner_id AS do,d.revoked_at AS dr
                FROM phone_remote_sessions s JOIN phone_remote_grants g USING(grant_id)
                JOIN phone_remote_devices d USING(device_id) WHERE s.session_id=?""",
                (binding.session_id,)).fetchone()
            return bool(row and anchor.host_id == binding.host_id
                and anchor.host_generation == binding.host_generation
                and row["host_id"] == binding.host_id and row["host_generation"] == binding.host_generation
                and row["owner_id"] == binding.owner_id == row["go"] == row["do"]
                and row["device_id"] == binding.device_id and row["grant_id"] == binding.grant_id
                and row["login_incarnation"] == binding.login_incarnation
                and row["grant_generation"] == binding.grant_generation
                and row["session_generation"] == binding.session_generation
                and row["revoked_at"] is None and row["gr"] is None and row["dr"] is None
                and row["expires_at"] > now and self.process_epoch == binding.process_epoch
                and frozenset(self._valid_scopes(row["scopes_json"]) or ()) == binding.scopes
                and self._admission_key(binding.session_id, binding.login_incarnation) in _PROCESS_ADMISSIONS)

    def current_binding(self, *, identity: ClientIdentity, owner_id: str, session_id: str,
                        device_id: str, login_incarnation: str, now: float) -> SessionBinding:
        owner_id = self._verified_owner(identity, self._text(owner_id, "owner_id"))
        session_id, device_id = self._text(session_id, "session_id"), self._text(device_id, "device_id")
        if type(now) not in (int, float) or not math.isfinite(now):
            raise StoreDenied("invalid time")
        with self._authority_guard():
            anchor = self._check_pair()
            row = self.db.execute("""SELECT s.*,g.grant_generation,g.scopes_json,g.revoked_at AS gr,
                g.owner_id AS go,d.device_id,d.owner_id AS do,d.revoked_at AS dr
                FROM phone_remote_sessions s JOIN phone_remote_grants g USING(grant_id)
                JOIN phone_remote_devices d USING(device_id) WHERE s.session_id=?""",
                (session_id,)).fetchone()
            scopes = self._valid_scopes(row["scopes_json"]) if row else None
            if (not row or not scopes or row["owner_id"] != owner_id or row["go"] != owner_id
                    or row["do"] != owner_id or row["device_id"] != device_id
                    or row["login_incarnation"] != login_incarnation or row["revoked_at"] is not None
                    or row["gr"] is not None or row["dr"] is not None or row["expires_at"] <= now
                    or row["host_id"] != anchor.host_id or row["host_generation"] != anchor.host_generation
                    or self._admission_key(session_id, login_incarnation) not in _PROCESS_ADMISSIONS):
                raise StoreDenied("session unavailable")
            return SessionBinding(owner_id, device_id, row["grant_id"], session_id,
                login_incarnation, anchor.host_id, anchor.host_generation,
                row["grant_generation"], row["session_generation"], self.process_epoch,
                frozenset(scopes))

    def binding_terminal(self, binding: SessionBinding, *, now: float) -> bool:
        """Prove terminality from protected epochs and process admission state.

        SQLite row absence or replacement is deliberately not evidence: either
        can be produced by restoring a stale database snapshot.
        """
        if type(binding) is not SessionBinding or type(now) not in (int, float) or not math.isfinite(now):
            return False
        with self._authority_guard():
            anchor = self._check_pair()
            parsed = self._parse_incarnation(binding.login_incarnation)
            if parsed is None or parsed[0] != binding.host_id or parsed[1] != binding.host_generation:
                return False
            if anchor.host_id != binding.host_id or anchor.host_generation > binding.host_generation:
                return True
            if anchor.host_generation < binding.host_generation or anchor.login_counter < parsed[2]:
                return False
            # A removed process admission cannot be restored with SQLite. The
            # protected monotonic login counter prevents that incarnation from
            # being issued again after session-only sign-out.
            return self._admission_key(binding.session_id, binding.login_incarnation) not in _PROCESS_ADMISSIONS

    def status(self) -> dict[str, int]:
        """Non-sensitive synthetic status; no record inventory is exposed."""
        with self._authority_guard():
            anchor = self._check_pair()
            return {"schema_version": SCHEMA_VERSION,
                    "host_generation": anchor.host_generation,
                    "login_counter": anchor.login_counter}
