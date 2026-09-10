"""Vault module: the only code that touches vault files directly (§6)."""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ulid import ULID

from . import DIGEST_MAX_CHARS, USER_ID
from .config import Paths
from .mdfile import ParseError, parse, serialize
from .schema import TYPE_TO_FOLDER, is_valid_slug, now_iso, validate_strict, ValidationError


class VaultError(Exception):
    """Structured vault error (§6.3)."""

    def __init__(self, code: str, message: str, id: str | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.id = id

    def to_dict(self) -> dict:
        d = {"error": self.code, "message": self.message}
        if self.id is not None:
            d["id"] = self.id
        return d


@dataclass
class Record:
    id: str
    frontmatter: dict[str, Any]
    body: str
    content_hash: str
    path: Path


def _hash_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


class Vault:
    def __init__(self, paths: Paths, user_id: str = USER_ID):
        self.paths = paths
        self.user_id = user_id
        self.user_dir = paths.user_dir(user_id)
        # buffered last_accessed updates: id -> new timestamp
        self._pending_access: dict[str, str] = {}
        from . import gitutil

        self._git = gitutil
        self._git.ensure_repo(paths.vault)
        for sub in ("areas", "sessions", "inbox"):
            (self.user_dir / sub).mkdir(parents=True, exist_ok=True)

    # ---- id / path resolution -------------------------------------------------

    def _find_path(self, id: str) -> Path | None:
        for sub in ("areas", "sessions", "inbox"):
            p = self.user_dir / sub / f"{id}.md"
            if p.exists():
                return p
        return None

    def _all_ids(self) -> set[str]:
        ids = set()
        for sub in ("areas", "sessions", "inbox"):
            d = self.user_dir / sub
            if d.exists():
                for p in d.glob("*.md"):
                    ids.add(p.stem)
        return ids

    # ---- read -------------------------------------------------------------

    def read(self, id: str) -> Record:
        path = self._find_path(id)
        if path is None:
            raise VaultError("NOT_FOUND", f"no file with id {id!r}", id=id)
        raw = path.read_bytes()
        content_hash = _hash_bytes(raw)
        try:
            fm, body = parse(raw.decode("utf-8"))
        except ParseError as e:
            raise VaultError("VALIDATION_FAILED", str(e), id=id) from e

        self._pending_access[id] = now_iso()
        return Record(id=id, frontmatter=fm, body=body, content_hash=content_hash, path=path)

    # ---- write --------------------------------------------------------------

    def write(
        self,
        type: str,
        body: str,
        tags: list[str],
        confidence: str,
        source_sessions: list[str],
        id: str | None = None,
        expected_hash: str | None = None,
        previous_excerpt: str | None = None,
    ) -> Record:
        if type not in TYPE_TO_FOLDER:
            raise VaultError("VALIDATION_FAILED", f"unknown type {type!r}")
        folder = TYPE_TO_FOLDER[type]

        if type == "session-digest" and len(body) > DIGEST_MAX_CHARS:
            raise VaultError(
                "VALIDATION_FAILED",
                "digest exceeds DIGEST_MAX_CHARS; split into detail files and link",
            )

        is_create = id is None or self._find_path(id) is None

        if is_create:
            if type in ("area", "decision"):
                if not id:
                    raise VaultError("VALIDATION_FAILED", f"id is required for type {type!r}")
                if not is_valid_slug(id):
                    raise VaultError("BAD_ID", f"id {id!r} does not match slug rules")
            else:
                id = str(ULID()).lower()

            if id in self._all_ids():
                raise VaultError("DUPLICATE_ID", f"id {id!r} already exists", id=id)

            ts = now_iso()
            fm = {
                "id": id,
                "type": type,
                "created": ts,
                "updated": ts,
                "last_accessed": ts,
                "tags": list(tags),
                "confidence": confidence,
                "source_sessions": list(source_sessions),
                "schema": 1,
            }
            try:
                validate_strict(fm)
            except ValidationError as e:
                raise VaultError("VALIDATION_FAILED", e.message, id=id) from e

            path = self.user_dir / folder / f"{id}.md"
            self._atomic_write(path, serialize(fm, body))
            self._git.commit(self.paths.vault, f"vault: create {id}")
            return Record(id=id, frontmatter=fm, body=body, content_hash=_hash_bytes(path.read_bytes()), path=path)

        # update path
        path = self._find_path(id)
        current_raw = path.read_bytes()
        current_hash = _hash_bytes(current_raw)
        if expected_hash is None or expected_hash != current_hash:
            raise VaultError("STALE_FILE", "file has changed since last read; re-read before writing", id=id)

        current_fm, current_body = parse(current_raw.decode("utf-8"))

        if current_fm.get("type") == "decision":
            if not previous_excerpt or previous_excerpt not in current_body:
                raise VaultError(
                    "DECISION_GUARD",
                    "updating a decision file requires previous_excerpt to appear verbatim in the current body",
                    id=id,
                )

        new_fm = dict(current_fm)
        new_fm["updated"] = now_iso()
        new_fm["tags"] = list(tags)
        new_fm["confidence"] = confidence
        new_fm["source_sessions"] = list(source_sessions)
        # created/last_accessed preserved
        try:
            validate_strict(new_fm)
        except ValidationError as e:
            raise VaultError("VALIDATION_FAILED", e.message, id=id) from e

        self._atomic_write(path, serialize(new_fm, body))
        self._git.commit(self.paths.vault, f"vault: update {id}")
        return Record(id=id, frontmatter=new_fm, body=body, content_hash=_hash_bytes(path.read_bytes()), path=path)

    # ---- delete -------------------------------------------------------------

    def delete(self, id: str) -> None:
        path = self._find_path(id)
        if path is None:
            raise VaultError("NOT_FOUND", f"no file with id {id!r}", id=id)
        fm, _ = parse(path.read_bytes().decode("utf-8"))
        if fm.get("type") != "capture":
            raise VaultError("DELETE_FORBIDDEN", "only type 'capture' files may be deleted", id=id)
        rel = str(path.relative_to(self.paths.vault))
        self._git.rm(self.paths.vault, rel, f"vault: delete {id}")

    # ---- list -----------------------------------------------------------------

    def list(self, type: str | None = None, folder: str | None = None) -> list[dict]:
        out = []
        folders = [folder] if folder else ["areas", "sessions", "inbox"]
        for sub in folders:
            d = self.user_dir / sub
            if not d.exists():
                continue
            for p in sorted(d.glob("*.md")):
                try:
                    fm, _ = parse(p.read_text(encoding="utf-8"))
                except ParseError:
                    continue
                if type is not None and fm.get("type") != type:
                    continue
                out.append(fm)
        return out

    # ---- access flush (§6.1) -------------------------------------------------

    def flush_access(self) -> int:
        if not self._pending_access:
            return 0
        touched_paths = []
        for id, ts in self._pending_access.items():
            path = self._find_path(id)
            if path is None:
                continue
            raw = path.read_bytes().decode("utf-8")
            try:
                fm, body = parse(raw)
            except ParseError:
                continue
            fm["last_accessed"] = ts
            self._atomic_write(path, serialize(fm, body))
            touched_paths.append(str(path.relative_to(self.paths.vault)))
        n = len(touched_paths)
        self._pending_access.clear()
        if n:
            self._git.commit(self.paths.vault, f"vault: access flush ({n} files)", paths=touched_paths)
        return n

    # ---- atomic write helper (§6) ---------------------------------------------

    @staticmethod
    def _atomic_write(path: Path, text: str) -> None:
        tmp = path.parent / f".{path.name}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.rename(tmp, path)
