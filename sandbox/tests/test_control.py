import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

MODULE = Path(__file__).resolve().parents[1] / "control.py"
spec = importlib.util.spec_from_file_location("sandbox_control", MODULE)
control = importlib.util.module_from_spec(spec)
spec.loader.exec_module(control)


class SourceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.git("init", "-q")

    def git(self, *args):
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
        return subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid", *args],
                              cwd=self.repo, env=env, check=True, capture_output=True)

    def commit(self):
        self.git("add", ".")
        self.git("commit", "-qm", "source")

    def test_snapshot_excludes_private_files_and_uncommitted_work(self):
        for name in ["app.py", ".env", ".env.example", "data/private.txt", "secret.vault"]:
            p = self.repo / name
            p.parent.mkdir(exist_ok=True)
            p.write_text("original")
        self.commit()
        (self.repo / "app.py").write_text("uncommitted")
        out = self.root / "source.tar"
        manifest = control.snapshot(self.repo, "HEAD", out)
        with tarfile.open(out) as archive:
            self.assertEqual(set(archive.getnames()), {"app.py", ".env.example"})
            self.assertEqual(archive.extractfile("app.py").read(), b"original")
        self.assertEqual(manifest["source_files"], 2)

    def test_symlink_is_rejected(self):
        (self.repo / "escape").symlink_to("/etc/passwd")
        self.commit()
        with self.assertRaises(control.SandboxError):
            control.snapshot(self.repo, "HEAD", self.root / "source.tar")
        self.assertFalse((self.root / "source.tar").exists())

    def test_key_in_source_is_rejected_without_printing_it(self):
        token = "sk-" + "a" * 30
        (self.repo / "app.py").write_text(token)
        self.commit()
        with self.assertRaises(control.SandboxError) as result:
            control.snapshot(self.repo, "HEAD", self.root / "source.tar")
        self.assertNotIn(token, str(result.exception))

    def test_path_policy(self):
        for name in ["../a", "/etc/passwd", "a/.git/config", "a/.env.local", "a/private.pem"]:
            self.assertFalse(control.source_path_allowed(name), name)
        self.assertTrue(control.source_path_allowed("tests/fixtures/example.json"))


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.c = control.Controller(self.root, "/missing/tart", "/missing/softnet")
        self.task = "0123456789ab"
        (self.root / "tasks" / self.task / "input").mkdir(parents=True)
        self.c.save(self.task, {"vm": "mortimer-" + self.task, "status": "created"})

    def test_missing_helper_fails_before_start(self):
        with patch.object(control.subprocess, "Popen") as launch:
            with self.assertRaises(control.SandboxError): self.c.start(self.task)
            launch.assert_not_called()

    def test_offline_boot_has_only_read_only_input(self):
        args = self.c.run_args(self.task, False, True)
        self.assertIn("--net-softnet-block=0.0.0.0/0", args)
        self.assertIn("--no-clipboard", args)
        self.assertIn("--no-audio", args)
        shares = [x for x in args if x.startswith("--dir=")]
        self.assertEqual(len(shares), 1)
        self.assertTrue(shares[0].endswith("/input:ro"))

    def test_task_traversal_is_rejected(self):
        with self.assertRaises(control.SandboxError): self.c.task_dir("../elsewhere")

    def test_development_cannot_run_during_provisioning(self):
        self.c.save(self.task, {"vm": "mortimer-" + self.task, "status": "provisioning", "network": "provisioning"})
        with self.assertRaises(control.SandboxError): self.c.execute(self.task, ["whoami"], 10)

    def test_timeout_stops_guest_not_only_client(self):
        self.c.save(self.task, {"vm": "mortimer-" + self.task, "status": "running"})
        with patch.object(self.c, "command", side_effect=subprocess.TimeoutExpired("tart", 1)), patch.object(self.c, "stop") as stop:
            with self.assertRaises(control.SandboxError): self.c.guest(self.task, ["sleep", "99"], timeout=1)
            stop.assert_called_once_with(self.task)


if __name__ == "__main__": unittest.main()
