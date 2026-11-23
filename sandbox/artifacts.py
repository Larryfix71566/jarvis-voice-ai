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
# Independently reviewed synthetic redaction/scanner fixtures, frozen 2026-10-06.
# Exact whole-file pins grant no path-only/pattern exemption; any edit is rescanned.
REVIEWED_TEST_FIXTURES = {
    'tests/unit/test_admin_status.py': '8871fe3f0f4f091a762df392be510b0a9bcb3280d0c5ad57d50a0e79cdf4703d',
    'tests/unit/test_mcp_apps_github.py': 'e284f44537e596f49f7c6a7e3b711c8d810cb7874ff07562aa3f84a6eaed0f62',
    'tests/unit/test_memory.py': '43647f889b835169f3bd8defb618d81b8fcf24001a55e8ad6c925a6611efba10',
    'tests/unit/test_status_catalog.py': 'b47dc4eb56748d7e64ee53c8d31b3cc1b5b5fb434d5c80c015dc238dd306ca4b',
    'tests/unit/test_status_daily.py': '59bf0ed277c4dd0453a4f7aea3175a7852e86c487461e42a48f281c9f4e03315',
    'tests/unit/test_status_logs.py': '7155b12e72ca71e2f1f22bee12608868db52ef51df6ef46a086314600cdcb43c',
    'tests/unit/test_status_models.py': '3f784168198e6a974fb7a5100c95f09d14e4e33d78b911997752a59b3e76d94b',
    'tests/unit/test_status_providers.py': '1c92bfa5401a6ee43bda6c5274a2bab350ef7116da7514d8010489328dcee05a',
    'tests/unit/test_status_subscriptions.py': 'd858ce77c07280591ce2b2f1405308834edc9e26e3c35d266c741099201d3979',
    'tests/unit/test_status_summaries.py': '17fa5cae14825cbe0a6ec6e8e6fa7e903377e32bf2f0121ead63b01f27e2a266',
}
# Historical baseline of the already-reviewed memory scanner tests. The three
# credential-shaped literals are byte-identical to the current reviewed file;
# only surrounding tests changed. This grants no path-only or pattern exemption.
REVIEWED_BASELINE_TEST_FIXTURES = {
    "tests/unit/test_memory.py": "dce7e7a64402906bf726f79534aa65011a578b1fa578577ee1ba57cb1bb84f5e",
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
            digest = hashlib.sha256(file.data).hexdigest()
            reviewed = (REVIEWED_TEST_FIXTURES.get(file.path) == digest
                        or REVIEWED_BASELINE_TEST_FIXTURES.get(file.path) == digest)
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
