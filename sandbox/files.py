"""Host-owned edit journal and immutable candidate store for sandbox sessions."""
from __future__ import annotations

import fcntl
import hashlib
import json
from pathlib import Path
from typing import Callable

from sandbox.artifacts import Candidate, File, SandboxError, source_path_allowed
from sandbox.durable import atomic_bytes, atomic_json


class WorkspaceFiles:
    """All source access goes through the VM; the host keeps only inert data.

    The policy callable belongs to the installed host application, not the
    guest source. Both explicit edits and changes made by running programs
    must satisfy it before a candidate can be accepted.
    """

    def __init__(self, controller, task: str, allowed: Callable[[str], bool]):
        self.controller, self.task, self.allowed = controller, task, allowed
        self.directory = controller.task_dir(task)
        source = self.directory / "input" / "source.tar"
        expected = controller.read(task).get("source_sha256")
        if expected != hashlib.sha256(source.read_bytes()).hexdigest():
            raise SandboxError("Baseline source does not match the task record")
        self.baseline = Candidate.from_snapshot(source)

    def _locked(self):
        lock = (self.directory / "files.lock").open("a")
        fcntl.flock(lock, fcntl.LOCK_EX)
        return lock

    def _journal(self) -> dict:
        path = self.directory / "files.json"
        if path.exists():
            journal = json.loads(path.read_bytes())
            if journal.get("baseline") != self.baseline.fingerprint:
                raise SandboxError("Edit journal belongs to a different baseline")
            return journal
        return {"version": 1, "baseline": self.baseline.fingerprint, "revision": 0,
                "proposals": [], "candidate": None, "verification": None}

    def _save(self, journal: dict):
        atomic_json(self.directory / "files.json", journal)

    def _path(self, path: str):
        if not source_path_allowed(path) or not self.allowed(path):
            raise SandboxError("Path is outside the workspace policy")

    def read(self, path: str) -> File:
        self._path(path)
        with self._locked():
            result = Candidate.decode(self.controller.rpc(self.task, {"operation": "read", "path": path}))
            if len(result.files) != 1 or result.files[0].path != path:
                raise SandboxError("Guest returned a different file")
            return result.files[0]

    def write(self, path: str, content: bytes, rationale: str, mode: int = 0o644) -> File:
        self._path(path)
        requested = Candidate((File(path, mode, content),))
        if not isinstance(rationale, str) or len(rationale) > 8000:
            raise SandboxError("Invalid edit rationale")
        with self._locked():
            if (self.directory / "publication.json").exists():
                raise SandboxError("Publication has started; begin a new session for further edits")
            journal = self._journal()
            # Persist invalidation BEFORE invoking the guest. A lost response
            # can never leave an earlier approval attached to changed code.
            journal.update(candidate=None, verification=None, revision=journal["revision"] + 1,
                           pending_edit={"path": path, "fingerprint": requested.fingerprint})
            self._save(journal)
            response = Candidate.decode(self.controller.rpc(self.task, {
                "operation": "write", "candidate": json.loads(requested.encode())}))
            if response != requested:
                raise SandboxError("Guest did not acknowledge the requested content")
            observed = Candidate.decode(self.controller.rpc(self.task, {"operation": "read", "path": path}))
            if observed != requested:
                raise SandboxError("Guest file differs after writing")
            journal.pop("pending_edit", None)
            journal["proposals"].append({"path": path, "rationale": rationale,
                                         "fingerprint": requested.fingerprint})
            self._save(journal)
            return requested.files[0]

    def _capture(self) -> Candidate:
        candidate = Candidate.decode(self.controller.rpc(self.task, {
            "operation": "capture", "baseline_paths": [file.path for file in self.baseline.files]}))
        candidate.changes(self.baseline, self.allowed)
        return candidate

    def freeze(self) -> Candidate:
        """Collect and bind a complete candidate; this does not approve it."""
        with self._locked():
            journal = self._journal()
            journal.update(verification=None, candidate=None)
            self._save(journal)
            first = self._capture()
            second = self._capture()
            if first != second:
                raise SandboxError("Candidate changed while being collected")
            objects = self.directory / "candidates"
            objects.mkdir(exist_ok=True, mode=0o700)
            atomic_bytes(objects / (first.fingerprint + ".json"), first.encode())
            journal.update(candidate=first.fingerprint, pending_edit=None)
            self._save(journal)
            return first

    def frozen(self) -> Candidate:
        with self._locked():
            digest = self._journal().get("candidate")
            if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                raise SandboxError("No frozen candidate")
            candidate = Candidate.decode((self.directory / "candidates" / (digest + ".json")).read_bytes())
            if candidate.fingerprint != digest:
                raise SandboxError("Frozen candidate content does not match its record")
            candidate.changes(self.baseline, self.allowed)
            return candidate

    def status(self) -> dict:
        with self._locked():
            return self._journal()

    def assert_unchanged(self, fingerprint: str) -> None:
        """Publisher rechecks the running development task before using a receipt."""
        with self._locked():
            journal = self._journal()
            try:
                matches = (journal.get("candidate") == fingerprint
                           and self._capture().fingerprint == fingerprint
                           and self._capture().fingerprint == fingerprint)
            except Exception:
                journal.update(candidate=None, verification=None)
                self._save(journal)
                raise
            if not matches:
                journal.update(candidate=None, verification=None)
                self._save(journal)
                raise SandboxError("Development source changed after verification")
