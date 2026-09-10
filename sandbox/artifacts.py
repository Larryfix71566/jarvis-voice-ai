"""Untrusted guest files are data, never host paths, archives, or commands."""
from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
import hashlib
import json
import re
import tarfile
import unicodedata
from pathlib import Path
from typing import Callable

MAX_SOURCE_BYTES = 256 * 1024 * 1024
MAX_FILE_BYTES = 32 * 1024 * 1024
MAX_FILES = 50000
SECRET = re.compile(rb"(?:gh[pousr]_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9_-]{24,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY)")
REVIEWED_TEST_FIXTURES = {
    "tests/unit/test_mcp_apps_github.py": "ce15f378a89c7b056ba88ca5c421342c303fcfc07670141927d2bb5398888e03",
    "tests/unit/test_memory.py": "5de5186a0ecb7d4698e388825a3b1fc8cd6fec6d7960866500418d4bf11ec3d2",
}


class SandboxError(RuntimeError):
    pass


def path_key(name: str) -> str:
    """Reject ambiguous paths before any host filesystem or Git operation."""
    if not isinstance(name, str) or not name or len(name.encode("utf-8")) > 1024:
        raise SandboxError("Invalid candidate path")
    if any(unicodedata.category(char).startswith("C") for char in name) or "\\" in name or ":" in name:
        raise SandboxError("Invalid candidate path")
    parts = name.split("/")
    if any(not part or part in {".", ".."} or part.endswith((".", " ")) for part in parts):
        raise SandboxError("Invalid candidate path")
    return unicodedata.normalize("NFC", name).casefold()


def source_path_allowed(name: str) -> bool:
    try:
        parts = path_key(name).split("/")
    except (SandboxError, UnicodeError):
        return False
    if parts[0] in {"data", "logs", "models", "node_modules", ".sandbox-data"}:
        return False
    for part in parts:
        if part in {".git", ".venv", "__pycache__", ".ssh", ".aws", ".tart"}:
            return False
        if part.startswith(".env") and part != ".env.example":
            return False
        if part.endswith((".vault", ".vault.lock", ".p12", ".pfx", ".key", ".pem", ".db", ".sqlite", ".bak")):
            return False
    return True


def check_paths(names) -> None:
    seen = set()
    prefixes = {}
    for name in names:
        key = path_key(name)
        if key in seen:
            raise SandboxError("Candidate contains colliding paths")
        seen.add(key)
        parts = name.split("/")
        for length in range(1, len(parts) + 1):
            prefix = "/".join(parts[:length])
            normalized = path_key(prefix)
            if normalized in prefixes and prefixes[normalized] != prefix:
                raise SandboxError("Candidate contains colliding directory names")
            prefixes[normalized] = prefix
    for key in seen:
        parts = key.split("/")
        if any("/".join(parts[:i]) in seen for i in range(1, len(parts))):
            raise SandboxError("Candidate file overlaps a directory")


@dataclass(frozen=True)
class File:
    path: str
    mode: int
    data: bytes

    def record(self) -> dict:
        return {"path": self.path, "mode": self.mode,
                "content": base64.b64encode(self.data).decode("ascii")}


@dataclass(frozen=True)
class Candidate:
    files: tuple[File, ...]

    def __post_init__(self):
        if len(self.files) > MAX_FILES:
            raise SandboxError("Candidate file count limit exceeded")
        check_paths(file.path for file in self.files)
        total = 0
        for file in self.files:
            if not source_path_allowed(file.path) or type(file.mode) is not int or file.mode not in {0o644, 0o755}:
                raise SandboxError("Candidate contains a forbidden path or mode")
            if type(file.data) is not bytes:
                raise SandboxError("Candidate content must be bytes")
            total += len(file.data)
            if len(file.data) > MAX_FILE_BYTES or total > MAX_SOURCE_BYTES:
                raise SandboxError("Candidate size limit exceeded")
            reviewed = REVIEWED_TEST_FIXTURES.get(file.path) == hashlib.sha256(file.data).hexdigest()
            if SECRET.search(file.data) and not reviewed:
                raise SandboxError("Candidate contains a potential credential")
        object.__setattr__(self, "files", tuple(sorted(self.files, key=lambda file: file.path)))

    @classmethod
    def decode(cls, payload: bytes) -> Candidate:
        # Bound the encoded representation before parsing; never accept tar,
        # pickle, a guest-provided output filename, or a guest-provided hash.
        if len(payload) > MAX_SOURCE_BYTES * 4 // 3 + MAX_FILES * 2048:
            raise SandboxError("Candidate transfer limit exceeded")
        def unique_object(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise SandboxError("Duplicate candidate field")
                result[key] = value
            return result
        try:
            obj = json.loads(payload, object_pairs_hook=unique_object)
            if not isinstance(obj, dict) or set(obj) != {"version", "files"} or type(obj["version"]) is not int or obj["version"] != 1:
                raise ValueError()
            if not isinstance(obj["files"], list) or len(obj["files"]) > MAX_FILES:
                raise ValueError()
            files = []
            for record in obj["files"]:
                if not isinstance(record, dict) or set(record) != {"path", "mode", "content"}:
                    raise ValueError()
                if not isinstance(record["content"], str) or len(record["content"]) > (MAX_FILE_BYTES + 2) // 3 * 4:
                    raise ValueError()
                data = base64.b64decode(record["content"], validate=True)
                files.append(File(record["path"], record["mode"], data))
            return cls(tuple(files))
        except (ValueError, TypeError, UnicodeError, binascii.Error, RecursionError):
            raise SandboxError("Invalid candidate transfer") from None

    @classmethod
    def from_snapshot(cls, path: Path) -> Candidate:
        # This is the host-owned committed source archive, read as data only.
        files = []
        total = 0
        with tarfile.open(path, "r:") as archive:
            for item in archive:
                if not item.isfile() or item.mode not in {0o644, 0o755} or not 0 <= item.size <= MAX_FILE_BYTES:
                    raise SandboxError("Invalid baseline source archive")
                total += item.size
                if total > MAX_SOURCE_BYTES or len(files) >= MAX_FILES:
                    raise SandboxError("Baseline size limit exceeded")
                files.append(File(item.name, item.mode, archive.extractfile(item).read()))
        return cls(tuple(files))

    def encode(self) -> bytes:
        return json.dumps({"version": 1, "files": [file.record() for file in self.files]},
                          ensure_ascii=True, separators=(",", ":")).encode("ascii")

    @property
    def fingerprint(self) -> str:
        # Canonical path/mode/content binding, independent of guest Git state.
        digest = hashlib.sha256(b"mortimer-candidate-v1\0")
        for file in self.files:
            record = json.dumps([file.path, file.mode, len(file.data), hashlib.sha256(file.data).hexdigest()],
                                ensure_ascii=True, separators=(",", ":")).encode("ascii")
            digest.update(record + b"\n")
        return digest.hexdigest()

    def changes(self, baseline: Candidate, allowed: Callable[[str], bool]) -> tuple[str, ...]:
        before = {file.path: file for file in baseline.files}
        after = {file.path: file for file in self.files}
        changed = tuple(sorted(path for path in before.keys() | after.keys() if before.get(path) != after.get(path)))
        if any(not allowed(path) for path in changed):
            raise SandboxError("Candidate changes a protected path")
        return changed
