import base64
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from sandbox import artifacts
from sandbox.artifacts import Candidate, File, SandboxError


class ArtifactTests(unittest.TestCase):
    def test_binary_modes_deletions_and_stable_fingerprint(self):
        a = File("app.py", 0o644, b"\x00\xff\n")
        b = File("run.sh", 0o755, b"#!/bin/sh\n")
        original = Candidate((a, b))
        self.assertEqual(original, Candidate.decode(original.encode()))
        self.assertEqual(original.fingerprint, Candidate((b, a)).fingerprint)
        changed = Candidate((File(a.path, 0o755, a.data),))
        self.assertNotEqual(original.fingerprint, changed.fingerprint)
        self.assertEqual(changed.changes(original, lambda p: True), ("app.py", "run.sh"))

    def test_ambiguous_paths_and_mac_collisions(self):
        for path in ["../a", "/a", "a//b", "a/./b", "a\\b", "a\x00b", "a\nb", "a:", "a. ", "x/.GIT/config", "x/.ENV.local", "x/secret.PEM"]:
            with self.subTest(path=path), self.assertRaises(SandboxError):
                Candidate((File(path, 0o644, b""),))
        for names in [("A", "a"), ("caf\u00e9", "cafe\u0301"), ("x", "x/y"), ("app", "app"),
                      ("jarvis/selfedit/service.py", "jarvis/SelfEdit/new.py")]:
            with self.subTest(names=names), self.assertRaises(SandboxError):
                Candidate(tuple(File(name, 0o644, b"") for name in names))

    def test_special_modes_and_credential_are_rejected_without_disclosure(self):
        for mode in [0o120777, 0o4755, 0o777, True, "644"]:
            with self.assertRaises(SandboxError):
                Candidate((File("a", mode, b""),))
        secret = b"sk-" + b"x" * 30
        with self.assertRaises(SandboxError) as error:
            Candidate((File("a", 0o644, secret),))
        self.assertNotIn(secret.decode(), str(error.exception))

    def test_protected_changes_include_deletion_and_edits_without_proposals(self):
        baseline = Candidate((File("policy.json", 0o644, b"protected"), File("app.py", 0o644, b"old")))
        for candidate in [Candidate((File("app.py", 0o644, b"old"),)),
                          Candidate((File("policy.json", 0o644, b"changed"), File("app.py", 0o644, b"old")))]:
            with self.assertRaises(SandboxError):
                candidate.changes(baseline, lambda path: path == "app.py")

    def test_malformed_and_duplicate_fields_are_not_accepted(self):
        payloads = [b'{}', b'[]', b'\xff', b'{"version":1,"version":1,"files":[]}',
                    b'{"version":true,"files":[]}', b'{"version":1,"files":[],"sha":"trusted"}',
                    b'{"version":1,"files":[{"path":"a","mode":420,"content":"!!!!"}]}']
        for payload in payloads:
            with self.subTest(payload=payload), self.assertRaises(SandboxError):
                Candidate.decode(payload)

    def test_individual_and_combined_size_limits(self):
        with patch.object(artifacts, "MAX_FILE_BYTES", 4), patch.object(artifacts, "MAX_SOURCE_BYTES", 6):
            for files in [(File("a", 0o644, b"12345"),),
                          (File("a", 0o644, b"1234"), File("b", 0o644, b"1234"))]:
                with self.assertRaises(SandboxError):
                    Candidate(files)

    def test_baseline_archive_never_extracts_links_or_host_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            archive_path = Path(temp) / "source.tar"
            for name, kind in [("../outside", tarfile.REGTYPE), ("link", tarfile.SYMTYPE)]:
                with tarfile.open(archive_path, "w") as archive:
                    info = tarfile.TarInfo(name)
                    info.type, info.mode = kind, 0o644
                    info.linkname = "/etc/passwd"
                    archive.addfile(info)
                with self.assertRaises(SandboxError):
                    Candidate.from_snapshot(archive_path)


if __name__ == "__main__":
    unittest.main()
