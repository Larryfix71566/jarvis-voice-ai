import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from sandbox.artifacts import Candidate, File, SandboxError
from sandbox.control import Controller, snapshot
from sandbox.images import Images
from sandbox.profiles import Profile


class ImageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.git("init", "-q")
        (self.repo / "deps.lock").write_text("version 1")
        (self.repo / "app.py").write_text("original")
        self.git("add", ".")
        self.git("commit", "-qm", "baseline")
        self.c = Controller(self.root / "runtime", "/missing/tart", "/missing/softnet")
        self.task = "0123456789ab"
        inputs = self.c.home / "tasks" / self.task / "input"
        inputs.mkdir(parents=True)
        (inputs / "prepare.sh").write_text("trusted recipe")
        record = snapshot(self.repo, "HEAD", inputs / "source.tar")
        self.c.save(self.task, {"vm": "fresh", "prepared": True, "status": "stopped",
                               "network": "provisioning", "image": "raw-base", **record})
        self.profile = Profile("test", ("deps.lock",), (".venv",), (("check", ("python", "-m", "pytest")),))
        self.vms = {"fresh": "stopped"}
        self.clones = []
        self.lost_clone = None
        self.commands = patch.object(self.c, "command", side_effect=self.command)
        self.commands.start()
        self.addCleanup(self.commands.stop)
        self.images = Images(self.c)

    def git(self, *args):
        env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
        env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
        return subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid", *args],
            cwd=self.repo, env=env, check=True, capture_output=True)

    def command(self, *args, **kwargs):
        if args[0] == "list":
            return subprocess.CompletedProcess(args, 0, stdout=json.dumps([
                {"Name": name, "State": state} for name, state in self.vms.items()]))
        if args[0] == "clone":
            if self.lost_clone == "before":
                self.lost_clone = None
                raise OSError("connection lost")
            self.clones.append(args[1:])
            self.vms[args[2]] = "stopped"
            if self.lost_clone == "after":
                self.lost_clone = None
                raise OSError("response lost")
        if args[0] == "stop":
            self.vms[args[1]] = "stopped"
        return subprocess.CompletedProcess(args, 0)

    def test_image_rejects_a_vm_that_has_entered_development(self):
        state = self.c.read(self.task)
        state["network"] = "offline"
        self.c.save(self.task, state)
        with self.assertRaises(SandboxError):
            self.images.register(self.task, self.profile)
        self.assertEqual(self.clones, [])

    def test_image_registration_recovers_before_and_after_lost_clone_response(self):
        for when in ["before", "after"]:
            with self.subTest(when=when):
                # Give each trial a different trusted recipe/image identity.
                (self.c.task_dir(self.task) / "input" / "prepare.sh").write_text(when)
                self.lost_clone = when
                before = len(self.clones)
                with self.assertRaises(OSError):
                    self.images.register(self.task, self.profile)
                image = self.images.register(self.task, self.profile)
                self.assertEqual(len(self.clones), before + 1)
                self.assertEqual(self.images.register(self.task, self.profile), image)
                self.assertEqual(len(self.clones), before + 1)

    def test_fresh_task_binds_source_profile_and_candidate(self):
        image = self.images.register(self.task, self.profile)
        candidate = Candidate((File("deps.lock", 0o644, b"version 1"), File("app.py", 0o644, b"updated")))
        task = self.images.create(image, self.repo, "HEAD", self.profile, purpose="verification", candidate=candidate)
        state = self.c.read(task)
        self.assertEqual(state["candidate"], candidate.fingerprint)
        self.assertEqual(state["profile_sha256"], self.profile.fingerprint)
        self.assertFalse(state["hydrated"])
        self.assertEqual(state["purpose"], "verification")
        self.assertEqual(Candidate.decode((self.c.task_dir(task) / "input" / "candidate.json").read_bytes()), candidate)
        self.assertEqual(self.clones[-1][0], self.images.read(image, self.profile)["vm"])

    def test_dependency_changes_fail_before_cloning_or_execution(self):
        image = self.images.register(self.task, self.profile)
        before = len(self.clones)
        candidate = Candidate((File("deps.lock", 0o644, b"different dependency"),))
        with self.assertRaises(SandboxError):
            self.images.create(image, self.repo, "HEAD", self.profile, candidate=candidate)
        self.assertEqual(len(self.clones), before)

    def test_failed_hydration_stops_and_cannot_be_retried_in_place(self):
        image = self.images.register(self.task, self.profile)
        task = self.images.create(image, self.repo, "HEAD", self.profile)
        state = self.c.read(task)
        state.update(status="running", network="offline")
        self.c.save(task, state)
        self.vms[state["vm"]] = "running"
        with patch.object(self.c, "guest", side_effect=SandboxError("bootstrap failed")), patch.object(self.c, "rpc") as rpc:
            with self.assertRaises(SandboxError):
                self.images.hydrate(task)
            rpc.assert_not_called()
        self.assertEqual(self.c.read(task)["status"], "stopped")
        self.assertTrue(self.c.read(task)["hydration_failed"])
        state = self.c.read(task)
        state["status"] = "running"
        self.c.save(task, state)
        with patch.object(self.c, "guest") as guest:
            with self.assertRaises(SandboxError):
                self.images.hydrate(task)
            guest.assert_not_called()

    def test_profile_tasks_cannot_fall_back_to_an_admin_worker(self):
        for state in [{"purpose": "development"}, {"purpose": "verification"}, {"worker": "admin"}]:
            with self.assertRaises(SandboxError):
                self.c.worker_prefix(state)
        self.assertEqual(self.c.worker_prefix({"worker": "mortimer-dev"})[-1], "mortimer-dev")


if __name__ == "__main__":
    unittest.main()
