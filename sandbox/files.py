"""Host-owned edit journal and immutable candidate store for sandbox sessions."""
from __future__ import annotations

import fcntl
import hashlib
import json
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from sandbox.artifacts import Candidate, File, SandboxError, source_path_allowed
from sandbox.durable import atomic_bytes, atomic_json


@dataclass
class SourceCapture:
    """Installed host observer; neither this object nor its policy enters the VM."""
    input_level: str
    baseline_level: str
    observations: list = field(default_factory=list, repr=False)


_source_capture = ContextVar('sandbox_source_capture', default=None)
_levels = {'approved_external': 1, 'confidential': 2, 'local_only': 3}


@contextmanager
def capture_sources(input_level: str, baseline_level: str):
    if input_level not in _levels or baseline_level not in _levels:
        raise SandboxError('Invalid host source policy')
    capture = SourceCapture(input_level, baseline_level)
    token = _source_capture.set(capture)
    try:
        yield capture
    finally:
        _source_capture.reset(token)


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

    def _observe(self, file: File, journal: dict, *, baseline_only=False):
        capture = _source_capture.get()
        if capture is None:
            return
        baseline = next((item for item in self.baseline.files if item.path == file.path), None)
        task_floor = journal.get('source_floor', 'confidential')
        if task_floor not in _levels:
            task_floor = 'confidential'
        level = max(('confidential', task_floor), key=_levels.get)
        if baseline_only:
            if file == baseline:
                level = capture.baseline_level
        elif journal.get('pending_edit'):
            pass  # A lost write response never approves a later read.
        else:
            edits = [p for p in journal['proposals'] if p.get('path') == file.path]
            if edits:
                admitted = edits[-1]
                expected = Candidate((file,)).fingerprint
                if admitted.get('fingerprint') == expected:
                    admitted_level = admitted.get('source_level', 'confidential')
                    if admitted_level not in _levels:
                        admitted_level = 'confidential'
                    level = max((admitted_level, task_floor), key=_levels.get)
            elif file == baseline:
                level = capture.baseline_level
        capture.observations.append((self.task, self.baseline.fingerprint, file,
                                     baseline, level))

    def observe_baseline(self, file: File):
        """Record an exact inert baseline read without broadening path permissions."""
        with self._locked():
            self._observe(file, self._journal(), baseline_only=True)

    def read(self, path: str) -> File:
        self._path(path)
        with self._locked():
            result = Candidate.decode(self.controller.rpc(self.task, {"operation": "read", "path": path}))
            if len(result.files) != 1 or result.files[0].path != path:
                raise SandboxError("Guest returned a different file")
            self._observe(result.files[0], self._journal())
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
            capture = _source_capture.get()
            level = capture.input_level if capture else 'confidential'
            prior_floor = journal.get('source_floor', 'approved_external')
            if prior_floor not in _levels:
                prior_floor = 'confidential'
            level = max((level, prior_floor), key=_levels.get)
            # Persist the strongest floor BEFORE the guest may receive the
            # bytes. An absent/lost ACK cannot undo their privacy requirement.
            journal['source_floor'] = level
            # Persist invalidation BEFORE invoking the guest. A lost response
            # can never leave an earlier approval attached to changed code.
            journal.update(candidate=None, verification=None, revision=journal["revision"] + 1,
                           pending_edit={"path": path, "fingerprint": requested.fingerprint,
                                         "source_level": level})
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
                                         "fingerprint": requested.fingerprint,
                                         "source_level": level})
            self._save(journal)
            self._observe(requested.files[0], journal)
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
