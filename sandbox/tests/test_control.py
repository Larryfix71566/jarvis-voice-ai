import importlib.util
import hashlib
import json
import os
import shlex
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

    def test_reviewed_synthetic_fixture_requires_exact_path_and_content(self):
        data = ("sk-" + "a" * 30).encode()
        (self.repo / "fixture.py").write_bytes(data)
        self.commit()
        reviewed = {"fixture.py": hashlib.sha256(data).hexdigest()}
        with patch.dict(control.REVIEWED_TEST_FIXTURES, reviewed, clear=True):
            control.snapshot(self.repo, "HEAD", self.root / "source.tar")
            (self.repo / "fixture.py").write_bytes(data + b"changed")
            self.commit()
            with self.assertRaises(control.SandboxError):
                control.snapshot(self.repo, "HEAD", self.root / "changed.tar")
            (self.repo / "fixture.py").unlink()
            (self.repo / "elsewhere.py").write_bytes(data)
            self.commit()
            with self.assertRaises(control.SandboxError):
                control.snapshot(self.repo, "HEAD", self.root / "moved.tar")


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

    def test_provisioning_blocks_private_ranges_and_all_host_ipv4_addresses(self):
        interfaces = 'lo0:\n\tinet 127.0.0.1 netmask 0xff000000\nen0:\n\tinet 192.168.1.4 netmask 0xffffff00\nen1:\n\tinet 203.0.113.7 netmask 0xffffff00\n'
        with patch.object(control.subprocess, 'check_output', return_value=interfaces):
            args = self.c.run_args(self.task, True, True)
        blocks = next(arg.split('=', 1)[1] for arg in args if arg.startswith('--net-softnet-block='))
        networks = [control.ipaddress.IPv4Network(value) for value in blocks.split(',')]
        for address in ['192.168.2.1', '10.0.0.1', '172.16.0.1', '169.254.169.254', '203.0.113.7']:
            self.assertTrue(any(control.ipaddress.IPv4Address(address) in net for net in networks))
        self.assertFalse(any(control.ipaddress.IPv4Address('1.1.1.1') in net for net in networks))

    def test_provisioning_refuses_unknown_host_interfaces(self):
        with patch.object(control.subprocess, 'check_output', return_value=''):
            with self.assertRaises(control.SandboxError):
                self.c.run_args(self.task, True, True)

    def test_development_cannot_run_during_provisioning(self):
        self.c.save(self.task, {"vm": "mortimer-" + self.task, "status": "provisioning", "network": "provisioning"})
        with self.assertRaises(control.SandboxError): self.c.execute(self.task, ["whoami"], 10)

    def test_preparation_flushes_guest_writes_before_marking_ready_and_stopping(self):
        self.c.save(self.task, {"vm": "mortimer-" + self.task, "status": "provisioning"})
        commands = []
        def guest(task, argv, **kwargs):
            self.assertFalse(self.c.read(task).get('prepared'))
            commands.append(argv)
        def stop(task):
            self.assertEqual(commands[-1], ['/bin/sync'])
            self.assertTrue(self.c.read(task)['prepared'])
        with patch.object(self.c, 'guest', side_effect=guest), patch.object(self.c, 'stop', side_effect=stop):
            self.c.prepare(self.task)

    def test_failed_flush_does_not_mark_preparation_complete(self):
        self.c.save(self.task, {"vm": "mortimer-" + self.task, "status": "provisioning"})
        with patch.object(self.c, 'guest', side_effect=[None, control.SandboxError('sync failed')]):
            with self.assertRaises(control.SandboxError):
                self.c.prepare(self.task)
        self.assertFalse(self.c.read(self.task).get('prepared'))

    def test_timeout_stops_guest_not_only_client(self):
        self.c.save(self.task, {"vm": "mortimer-" + self.task, "status": "running"})
        with patch.object(self.c, "command", side_effect=subprocess.TimeoutExpired("tart", 1)), patch.object(self.c, "stop") as stop:
            with self.assertRaises(control.SandboxError): self.c.guest(self.task, ["sleep", "99"], timeout=1)
            stop.assert_called_once_with(self.task)

    def test_stop_reconciles_a_vm_that_already_exited(self):
        self.c.save(self.task, {"vm": "mortimer-" + self.task, "status": "running"})
        listing = subprocess.CompletedProcess([], 0, stdout=json.dumps([
            {"Name": "mortimer-" + self.task, "State": "stopped"}]))
        with patch.object(self.c, "command", side_effect=[subprocess.CalledProcessError(1, "stop"), listing]):
            self.c.stop(self.task)
        self.assertEqual(self.c.read(self.task)["status"], "stopped")

    def test_failed_stop_does_not_claim_a_running_or_unknown_vm_stopped(self):
        for entries in [[], [{"Name": "mortimer-" + self.task, "State": "running"}]]:
            self.c.save(self.task, {"vm": "mortimer-" + self.task, "status": "running"})
            listing = subprocess.CompletedProcess([], 0, stdout=json.dumps(entries))
            with patch.object(self.c, "command", side_effect=[subprocess.CalledProcessError(1, "stop"), listing]):
                with self.assertRaises(subprocess.CalledProcessError):
                    self.c.stop(self.task)
            self.assertEqual(self.c.read(self.task)["status"], "running")

    def export_writer(self, payload):
        executable = self.root / "fake-tart"
        executable.write_text("#!/bin/sh\nprintf %s " + shlex.quote(payload) + "\n")
        executable.chmod(0o755)
        self.c.tart = str(executable)
        self.c.save(self.task, {"vm": "mortimer-" + self.task,
                               "status": "running", "network": "offline"})

    def test_patch_export_is_data_with_a_fingerprint(self):
        payload = "diff --git a/app.py b/app.py\n+print('hello')\n"
        self.export_writer(payload)
        output = self.c.export(self.task)
        self.assertEqual(output.read_text(), payload)
        self.assertEqual(self.c.read(self.task)["export_sha256"], hashlib.sha256(payload.encode()).hexdigest())

    def test_oversized_export_stops_the_guest(self):
        self.export_writer("a" * 100)
        with patch.object(control, "MAX_SOURCE_BYTES", 4), patch.object(self.c, "stop") as stop:
            with self.assertRaises(control.SandboxError): self.c.export(self.task)
            stop.assert_called_once_with(self.task)
        self.assertFalse((self.c.task_dir(self.task) / "candidate.patch").exists())

    def test_secret_shaped_export_is_not_written(self):
        self.export_writer("sk-" + "a" * 30)
        with self.assertRaises(control.SandboxError): self.c.export(self.task)
        self.assertFalse((self.c.task_dir(self.task) / "candidate.patch").exists())


if __name__ == "__main__": unittest.main()
