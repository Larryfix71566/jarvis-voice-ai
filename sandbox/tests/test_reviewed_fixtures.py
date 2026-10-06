"""Actual reviewed fixture bytes remain bound to exact paths and whole-file hashes."""
import hashlib
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest

from sandbox import artifacts, control

ROOT = Path(__file__).resolve().parents[2]
FROZEN_FIXTURES = {
    'tests/unit/test_admin_status.py': 'fd0bc1f3a204c2d6baf8995f3b01785955b599309df321775597dcd1b80610e2',
    'tests/unit/test_mcp_apps_github.py': 'e284f44537e596f49f7c6a7e3b711c8d810cb7874ff07562aa3f84a6eaed0f62',
    'tests/unit/test_memory.py': '43647f889b835169f3bd8defb618d81b8fcf24001a55e8ad6c925a6611efba10',
    'tests/unit/test_status_catalog.py': 'f6dbf4db8bb1806dbf7c92e4e636875cf7cd9eefd44dc1d728796567e96c49ac',
    'tests/unit/test_status_daily.py': '2dd60a76e8628e8364d9609b38a887ed4fb305f2d5ffd9788eed0340135d4be4',
    'tests/unit/test_status_logs.py': '7155b12e72ca71e2f1f22bee12608868db52ef51df6ef46a086314600cdcb43c',
    'tests/unit/test_status_models.py': '0f18478d9d27763edd055df760b4a6840e33995f0515608b1bdd4e90b1e894a3',
    'tests/unit/test_status_providers.py': '68eb01078156221de31ea83ea8b3588bfbc634a9fa78ca4ff04c47b08daa3caf',
    'tests/unit/test_status_subscriptions.py': 'd858ce77c07280591ce2b2f1405308834edc9e26e3c35d266c741099201d3979',
    'tests/unit/test_status_summaries.py': '17fa5cae14825cbe0a6ec6e8e6fa7e903377e32bf2f0121ead63b01f27e2a266',
}


class ReviewedFixtureTests(unittest.TestCase):
    def data(self, path):
        data = (ROOT / path).read_bytes()
        self.assertEqual(hashlib.sha256(data).hexdigest(), FROZEN_FIXTURES[path])
        self.assertIsNotNone(artifacts.SECRET.search(data))
        return data

    def test_exact_current_fixtures_are_accepted_but_edits_and_moves_are_not(self):
        for path, digest in FROZEN_FIXTURES.items():
            with self.subTest(path=path):
                data = self.data(path)
                self.assertEqual(artifacts.REVIEWED_TEST_FIXTURES.get(path), digest)
                artifacts.Candidate((artifacts.File(path, 0o644, data),))
                for name, changed in ((path, data + b"\n# changed\n"),
                                      ("tests/fixtures/moved.py", data)):
                    with self.assertRaises(artifacts.SandboxError):
                        artifacts.Candidate((artifacts.File(name, 0o644, changed),))

    def test_historical_baseline_pin_and_private_path_exclusions_are_unchanged(self):
        self.assertEqual(artifacts.REVIEWED_BASELINE_TEST_FIXTURES, {
            "tests/unit/test_memory.py":
            "dce7e7a64402906bf726f79534aa65011a578b1fa578577ee1ba57cb1bb84f5e",
        })
        for name in (".env", "data/private.txt", "logs/bot.log", "secrets.vault",
                     "secret.pem", "private.db", ".git/config"):
            with self.subTest(path=name):
                self.assertFalse(artifacts.source_path_allowed(name))

    def test_actual_snapshot_accepts_exact_bytes_and_cleans_refused_mutation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            repo = root / "repo"
            repo.mkdir()
            env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
            env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
            def git(*args):
                subprocess.run(["git", "-c", "user.name=Test", "-c",
                                "user.email=test@example.invalid", *args],
                               cwd=repo, env=env, check=True, capture_output=True)
            git("init", "-q")
            for name in FROZEN_FIXTURES:
                path = repo / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(self.data(name))
            (repo / ".env").write_text("excluded fixture")
            (repo / "data").mkdir()
            (repo / "data/private.txt").write_text("excluded fixture")
            git("add", ".")
            git("commit", "-qm", "reviewed source")
            archive = root / "source.tar"
            result = control.snapshot(repo, "HEAD", archive)
            self.assertEqual(result["source_files"], len(FROZEN_FIXTURES))
            with tarfile.open(archive) as exported:
                self.assertEqual(set(exported.getnames()), set(FROZEN_FIXTURES))
            artifacts.Candidate.from_snapshot(archive)
            name = next(iter(FROZEN_FIXTURES))
            path = repo / name
            path.write_bytes(path.read_bytes() + b"\n# changed\n")
            git("add", name)
            git("commit", "-qm", "changed source")
            refused = root / "changed.tar"
            with self.assertRaises(artifacts.SandboxError) as caught:
                control.snapshot(repo, "HEAD", refused)
            self.assertEqual(str(caught.exception), "Potential credential in source: " + name)
            self.assertFalse(refused.exists())
            self.assertFalse(refused.with_suffix(".partial").exists())


if __name__ == "__main__":
    unittest.main()
