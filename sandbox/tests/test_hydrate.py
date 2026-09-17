import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from sandbox import artifacts
from sandbox.artifacts import Candidate, File, SandboxError

spec = importlib.util.spec_from_file_location("hydrate_test", Path(__file__).resolve().parents[1] / "guest" / "hydrate.py")
hydrate = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {"artifacts": artifacts}):
    spec.loader.exec_module(hydrate)


class HydrateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "source" / ".venv").mkdir(parents=True)
        (self.root / "source" / ".venv" / "installed").write_text("dependency")
        (self.root / "source" / "old.py").write_text("stale source")
        (self.root / "state").mkdir()
        (self.root / "state" / "old.db").write_text("old synthetic state")
        (self.root / "development.env").write_text("export RUN_LIVE=0\n")

    def test_hydration_replaces_source_and_state_but_preserves_protected_dependencies(self):
        candidate = Candidate((File("app.py", 0o644, b"new source"),))
        hydrate.hydrate(self.root, candidate, [".venv"], os.getuid(), os.getgid())
        self.assertFalse((self.root / "source" / "old.py").exists())
        self.assertFalse((self.root / "state" / "old.db").exists())
        self.assertEqual((self.root / "source" / "app.py").read_bytes(), b"new source")
        self.assertTrue((self.root / "source" / ".venv").is_symlink())
        self.assertEqual((self.root / "dependencies" / "python" / "installed").read_text(), "dependency")
        self.assertFalse((self.root / "hydration-cache").exists())

    def test_interrupted_hydration_and_unknown_cache_paths_fail_closed(self):
        candidate = Candidate((File("app.py", 0o644, b"new"),))
        with self.assertRaises(SandboxError):
            hydrate.hydrate(self.root, candidate, ["../outside"], os.getuid(), os.getgid())
        (self.root / "hydration-cache").mkdir()
        with self.assertRaises(FileExistsError):
            hydrate.hydrate(self.root, candidate, [".venv"], os.getuid(), os.getgid())

    def test_baseline_tests_use_baseline_source_and_exclude_candidate_tests(self):
        baseline = Candidate((File("tests/test_app.py", 0o644, b"original required test"),
                              File("jarvis/app.py", 0o644, b"old application")))
        candidate = Candidate((File("tests/test_app.py", 0o644, b"weakened test"),
                               File("tests/test_added.py", 0o644, b"new test"),
                               File("jarvis/app.py", 0o644, b"updated application")))
        (self.root / "source" / "jarvis").mkdir()
        (self.root / "source" / "jarvis" / "app.py").write_bytes(b"updated application")
        hydrate.verification_tree(self.root, baseline, candidate, [])
        checks = self.root / "verification"
        self.assertEqual((checks / "tests" / "test_app.py").read_bytes(), b"original required test")
        self.assertFalse((checks / "tests" / "test_added.py").exists())
        self.assertEqual((checks / "jarvis" / "app.py").read_bytes(), b"old application")
        self.assertIn(checks / "jarvis" / "app.py", list(checks.rglob("*.py")))

    def test_swift_verification_copies_dependencies_without_candidate_build_products(self):
        source = self.root / 'source' / 'macos' / 'Kit' / '.build'
        destination = self.root / 'verification' / 'macos' / 'Kit' / '.build'
        destination.parent.mkdir(parents=True)
        for name in ['artifacts', 'checkouts', 'repositories', 'arm64-apple-macosx']:
            (source / name).mkdir(parents=True)
            (source / name / 'data').write_text(name)
        (source / 'workspace-state.json').write_text(str(source / 'artifacts'))
        hydrate.swift_dependencies(self.root, source, destination)
        self.assertFalse((destination / 'arm64-apple-macosx').exists())
        self.assertEqual((destination / 'workspace-state.json').read_text(), str(destination / 'artifacts'))
        (source / 'checkouts' / 'data').write_text('mutated')
        self.assertEqual((destination / 'checkouts' / 'data').read_text(), 'checkouts')


if __name__ == "__main__":
    unittest.main()
