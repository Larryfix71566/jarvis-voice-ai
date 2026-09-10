import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from sandbox import artifacts
from sandbox.artifacts import Candidate, File, SandboxError
from sandbox.durable import atomic_json
from sandbox.files import WorkspaceFiles

spec = importlib.util.spec_from_file_location("guest_rpc_tests", Path(__file__).resolve().parents[1] / "guest" / "rpc.py")
rpc = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {"artifacts": artifacts}):
    spec.loader.exec_module(rpc)


class FilesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.guest = self.root / "guest"
        self.guest.mkdir()
        self.host = self.root / "host"
        (self.host / "input").mkdir(parents=True)
        archive_path = self.host / "input" / "source.tar"
        with tarfile.open(archive_path, "w") as archive:
            for name, data in [("app.py", b"original"), ("policy.json", b"protected")]:
                item = tarfile.TarInfo(name)
                item.mode, item.size = 0o644, len(data)
                archive.addfile(item, io.BytesIO(data))
                (self.guest / name).write_bytes(data)
        self.source_sha = hashlib.sha256(archive_path.read_bytes()).hexdigest()
        self.files = WorkspaceFiles(self, "test", lambda path: path != "policy.json")

    # Test transport implements only guest file operations in a temporary
    # directory. It never runs application commands or accesses real VMs.
    def task_dir(self, task):
        return self.host

    def read(self, task):
        return {"source_sha256": self.source_sha}

    def rpc(self, task, request):
        return rpc.dispatch(self.guest, request)

    def test_edit_freeze_and_reopen_preserve_exact_candidate(self):
        self.files.write("new/app.bin", b"\x00\xff", "new binary", 0o755)
        (self.guest / "app.py").unlink()
        frozen = self.files.freeze()
        reopened = WorkspaceFiles(self, "test", lambda path: path != "policy.json")
        self.assertEqual(reopened.frozen(), frozen)
        self.assertEqual(frozen.changes(self.files.baseline, lambda p: True), ("app.py", "new/app.bin"))
        self.assertFalse((self.host / "new").exists())
        self.assertIsNone(self.files.status()["verification"])

    def test_lost_write_response_invalidates_previous_candidate_durably(self):
        self.files.freeze()
        old = self.files.status()
        old["verification"] = {"candidate": old["candidate"], "passed": True}
        atomic_json(self.host / "files.json", old)
        def lost(task, request):
            rpc.dispatch(self.guest, request)
            raise SandboxError("connection lost")
        with patch.object(self, "rpc", side_effect=lost), self.assertRaises(SandboxError):
            self.files.write("app.py", b"changed", "change")
        state = self.files.status()
        self.assertIsNone(state["verification"])
        self.assertIsNone(state["candidate"])
        self.assertEqual((self.guest / "app.py").read_bytes(), b"changed")
        self.assertIsNotNone(state["pending_edit"])

    def test_gitignore_cannot_hide_a_protected_change(self):
        (self.guest / ".gitignore").write_text("policy.json\n")
        (self.guest / "policy.json").write_bytes(b"bypass")
        with self.assertRaises(SandboxError):
            self.files.freeze()
        self.assertIsNone(self.files.status()["candidate"])

    def test_links_and_special_files_cannot_escape_or_block_file_operations(self):
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "secret").write_text("keep")
        (self.guest / "link").symlink_to(outside, target_is_directory=True)
        for operation in [lambda: self.files.read("link/secret"),
                          lambda: self.files.write("link/secret", b"overwritten", "escape"),
                          self.files.freeze]:
            with self.assertRaises((SandboxError, OSError)):
                operation()
        self.assertEqual((outside / "secret").read_text(), "keep")
        (self.guest / "link").unlink()
        os.link(outside / "secret", self.guest / "hardlink")
        with self.assertRaises(SandboxError):
            self.files.read("hardlink")
        (self.guest / "hardlink").unlink()
        os.mkfifo(self.guest / "pipe")
        with self.assertRaises(SandboxError):
            self.files.read("pipe")

    def test_capture_detects_changes_between_reads(self):
        calls = 0
        def moving(task, request):
            nonlocal calls
            calls += 1
            (self.guest / "app.py").write_text(str(calls))
            return rpc.dispatch(self.guest, request)
        with patch.object(self, "rpc", side_effect=moving), self.assertRaises(SandboxError):
            self.files.freeze()
        self.assertIsNone(self.files.status()["candidate"])

    def test_generated_dependencies_are_excluded_but_baseline_files_remain(self):
        (self.guest / "node_modules").mkdir()
        (self.guest / "node_modules" / "generated.js").write_text("cache")
        (self.guest / ".env").write_text("sandbox-placeholder")
        (self.guest / "package.egg-info").mkdir()
        (self.guest / "package.egg-info" / "PKG-INFO").write_text("generated")
        self.assertEqual(self.files.freeze(), self.files.baseline)
        captured = rpc.capture(self.guest, ["app.py", "policy.json", "package.egg-info/PKG-INFO"])
        self.assertIn("package.egg-info/PKG-INFO", [file.path for file in captured.files])

    def test_corrupt_frozen_object_and_baseline_fail_closed(self):
        candidate = self.files.freeze()
        path = self.host / "candidates" / (candidate.fingerprint + ".json")
        path.write_bytes(Candidate(()).encode())
        with self.assertRaises(SandboxError):
            self.files.frozen()
        (self.host / "input" / "source.tar").write_bytes(b"tampered")
        with self.assertRaises(SandboxError):
            WorkspaceFiles(self, "test", lambda p: True)

    def test_wrong_file_response_is_rejected(self):
        with patch.object(self, "rpc", return_value=Candidate((File("different", 0o644, b"data"),)).encode()):
            with self.assertRaises(SandboxError):
                self.files.read("app.py")


if __name__ == "__main__":
    unittest.main()
