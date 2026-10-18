import json
import fcntl
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

from sandbox.artifacts import SandboxError
from sandbox.control import Controller
from sandbox import prune
from sandbox.prune import Pruner

DAY = 86400
TB = 1024 ** 4


class PruneTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.c = Controller(self.root, "/missing/tart", "/missing/softnet")
        self.now = time.time()
        self.vms = {"mortimer-base": "stopped", "mortimer-image-0123456789abcdef0123": "stopped"}
        self.deleted = []
        patcher = patch.object(self.c, "command", side_effect=self.command)
        patcher.start(); self.addCleanup(patcher.stop)
        free = patch.object(prune, "free_bytes", return_value=TB)
        free.start(); self.addCleanup(free.stop)
        self.pruner = Pruner(self.c)

    def command(self, *args, **kwargs):
        if args[0] == "list":
            return subprocess.CompletedProcess(args, 0, stdout=json.dumps(
                [{"Name": name, "State": state} for name, state in self.vms.items()]))
        if args[0] == "delete":
            if args[1] not in self.vms:
                raise subprocess.CalledProcessError(1, args)
            del self.vms[args[1]]
            self.deleted.append(args[1])
        return subprocess.CompletedProcess(args, 0)

    def task(self, identifier, *, age=2 * 3600, status="stopped", vm_state="stopped", **fields):
        (self.root / "tasks" / identifier / "input").mkdir(parents=True)
        self.c.save(identifier, {"id": identifier, "vm": "mortimer-" + identifier, "status": status, **fields})
        record = self.root / "tasks" / identifier / "state.json"
        os.utime(record, (self.now - age, self.now - age))
        if vm_state is not None:
            self.vms["mortimer-" + identifier] = vm_state
        return identifier

    def session(self, task, *, phase="editing", idle=0, cancelled=False):
        directory = self.root / "sessions" / (task * 3)[:32]
        directory.mkdir(parents=True)
        (directory / "session.json").write_text(json.dumps(
            {"id": directory.name, "task": task, "phase": phase, "updated_at": int(self.now - idle)}))
        if cancelled:
            (directory / "cancelled.json").write_text("{}")

    def reasons(self):
        return {item["task"]: item["reason"] for item in self.pruner.plan(self.now)}

    def test_templates_active_and_fresh_records_are_never_candidates(self):
        self.task("aaaaaaaaaaa1", status="running", vm_state="running", purpose="verification")
        self.task("aaaaaaaaaaa2", status="provisioning", vm_state="running")
        self.task("aaaaaaaaaaa3", status="deleted", vm_state=None, purpose="verification")
        self.task("aaaaaaaaaaa4", age=60, purpose="verification")  # inside the grace period
        self.task("aaaaaaaaaaa5", purpose="verification")
        self.c.save("aaaaaaaaaaa5", {**self.c.read("aaaaaaaaaaa5"), "vm": "mortimer-base"})
        os.utime(self.root / "tasks" / "aaaaaaaaaaa5" / "state.json", (self.now - DAY, self.now - DAY))
        self.assertEqual(self.reasons(), {})
        self.pruner.run(now=self.now)
        self.assertEqual(self.deleted, [])
        self.assertIn("mortimer-base", self.vms)

    def test_stopped_verification_vm_is_deleted_and_its_evidence_kept(self):
        task = self.task("bbbbbbbbbbb1", purpose="verification", parent_task="bbbbbbbbbbb2")
        evidence = self.root / "tasks" / task / "verification" / ("c" * 32)
        evidence.mkdir(parents=True)
        (evidence / "receipt.json").write_text("{}")
        report = self.pruner.run(now=self.now)
        self.assertEqual(self.deleted, ["mortimer-" + task])
        self.assertEqual([item["task"] for item in report["destroyed"]], [task])
        self.assertEqual(self.c.read(task)["status"], "deleted")
        self.assertTrue((evidence / "receipt.json").exists())
        self.assertTrue((self.root / "prune.log").exists())

    def test_development_vm_follows_its_session(self):
        ended = self.task("ddddddddddd1", purpose="development"); self.session(ended, phase="published")
        cancelled = self.task("ddddddddddd2", purpose="development"); self.session(cancelled, cancelled=True)
        orphan = self.task("ddddddddddd3", age=7 * 3600, purpose="development")
        open_recent = self.task("ddddddddddd4", purpose="development"); self.session(open_recent, idle=6 * DAY)
        open_idle = self.task("ddddddddddd5", purpose="development"); self.session(open_idle, idle=8 * DAY)
        reasons = self.reasons()
        self.assertEqual(set(reasons), {ended, cancelled, orphan, open_idle})
        self.assertIn("published", reasons[ended])
        self.assertIn("idle for 8 days", reasons[open_idle])
        self.pruner.run(now=self.now)
        self.assertNotIn("mortimer-" + open_recent, self.deleted)
        self.assertEqual(self.c.read(open_recent)["status"], "stopped")

    def test_unowned_development_vm_waits_for_a_quiet_period_and_its_children(self):
        # Acceptance campaigns drive Images/Verifier directly: no session record.
        recent = self.task("eeeeeeeeeee1", age=3 * 3600, purpose="development")
        quiet = self.task("eeeeeeeeeee2", age=7 * 3600, purpose="development")
        validating = self.task("eeeeeeeeeee3", age=9 * 3600, purpose="development")
        self.task("eeeeeeeeeee4", age=2 * 3600, status="running", vm_state="running",
                  purpose="verification", parent_task=validating)
        child_recent = self.task("eeeeeeeeeee5", age=9 * 3600, purpose="development")
        self.task("eeeeeeeeeee6", age=30 * 60, purpose="verification", parent_task=child_recent)
        child_done = self.task("eeeeeeeeeee7", age=9 * 3600, purpose="development")
        done = self.task("eeeeeeeeeee8", age=7 * 3600, purpose="verification", parent_task=child_done)
        reasons = self.reasons()
        self.assertEqual(set(reasons), {quiet, child_done, done})
        self.assertIn("quiet for 7 hours", reasons[quiet])
        self.assertNotIn(recent, reasons)

    def test_low_disk_shortens_the_idle_allowance(self):
        task = self.task("abcdef000001", purpose="development"); self.session(task, idle=2 * DAY)
        orphan = self.task("abcdef000002", age=3 * 3600, purpose="development")
        self.assertEqual(self.reasons(), {})
        with patch.object(prune, "free_bytes", return_value=prune.LOW_DISK_BYTES - 1):
            self.assertEqual(set(self.reasons()), {task, orphan})

    def test_legacy_provisioning_task_waits_for_the_idle_allowance(self):
        recent = self.task("fffffffffff1", age=2 * DAY, network="provisioning", prepared=True)
        old = self.task("fffffffffff2", age=9 * DAY, network="provisioning", prepared=True)
        self.assertEqual(set(self.reasons()), {old})
        self.assertIn(recent, self.c.read(recent)["id"])

    def test_a_vm_tart_still_reports_running_is_refused_and_others_continue(self):
        live = self.task("abcabcabcab1", purpose="verification", vm_state="running")  # record says stopped
        done = self.task("abcabcabcab2", purpose="verification")
        report = self.pruner.run(now=self.now)
        self.assertEqual(self.deleted, ["mortimer-" + done])
        self.assertEqual([item["task"] for item in report["failed"]], [live])
        self.assertEqual(self.c.read(live)["status"], "stopped")
        self.assertIn("mortimer-" + live, self.vms)

    def test_dry_run_deletes_nothing(self):
        task = self.task("123412341231", purpose="verification")
        report = self.pruner.run(dry_run=True, now=self.now)
        self.assertEqual([item["task"] for item in report["kept"]], [task])
        self.assertEqual(self.deleted, [])
        self.assertEqual(self.c.read(task)["status"], "stopped")
        self.assertFalse((self.root / "prune.log").exists())

    def test_reclaim_never_raises_and_headroom_fails_closed(self):
        with patch.object(Pruner, "run", side_effect=OSError("tart unavailable")):
            self.assertIsNone(prune.reclaim(self.c))
        self.assertIn("tart unavailable", (self.root / "prune.log").read_text())
        prune.require_headroom(self.c)
        with patch.object(prune, "free_bytes", return_value=prune.MIN_FREE_BYTES - 1):
            with self.assertRaises(SandboxError) as result:
                prune.require_headroom(self.c)
        self.assertIn("sandbox.prune", str(result.exception))

    def test_stale_plan_revalidates_session_activity(self):
        task = self.task("aaaabbbb0001", purpose="development")
        self.session(task, idle=8 * DAY)
        session = self.root / "sessions" / (task * 3)[:32] / "session.json"
        original = self.pruner.plan
        def plan(now=None):
            result = original(now)
            data = json.loads(session.read_bytes())
            data["updated_at"] = int(self.now)
            session.write_text(json.dumps(data))
            return result
        with patch.object(self.pruner, "plan", side_effect=plan):
            report = self.pruner.run(now=self.now)
        self.assertEqual(self.deleted, [])
        self.assertEqual([x["task"] for x in report["failed"]], [task])
        self.assertEqual(self.c.read(task)["status"], "stopped")

    def test_stale_plan_revalidates_new_verification_child(self):
        task = self.task("aaaabbbb0002", age=7 * 3600, purpose="development")
        original = self.pruner.plan
        def plan(now=None):
            result = original(now)
            if not (self.root / "tasks" / "aaaabbbb0003").exists():
                self.task("aaaabbbb0003", age=1, status="creating", vm_state=None,
                          purpose="verification", parent_task=task)
            return result
        with patch.object(self.pruner, "plan", side_effect=plan):
            report = self.pruner.run(now=self.now)
        self.assertEqual(self.deleted, [])
        self.assertEqual([x["task"] for x in report["failed"]], [task])

    def test_revalidates_task_activity_after_tart_stopped_probe(self):
        task = self.task("aaaabbbb0004", age=7 * 3600, purpose="development")
        original = self.command
        def command(*args, **kwargs):
            result = original(*args, **kwargs)
            if args[0] == "list":
                record = self.root / "tasks" / task / "state.json"
                os.utime(record, (self.now, self.now))
            return result
        with patch.object(self.c, "command", side_effect=command):
            self.pruner.run(now=self.now)
        self.assertEqual(self.deleted, [])
        self.assertEqual(self.c.read(task)["status"], "stopped")

    def test_busy_mutation_locks_retain_old_stopped_tasks(self):
        task = self.task("aaaabbbb0005", purpose="development")
        self.session(task, idle=8 * DAY)
        for path in [self.root / "sessions" / (task * 3)[:32] / "session.lock",
                     self.root / "tasks" / task / "files.lock"]:
            with self.subTest(path=path.name), path.open("a") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                report = self.pruner.run(now=self.now)
                self.assertEqual(self.deleted, [])
                self.assertEqual([x["task"] for x in report["failed"]], [task])

    def test_malformed_ownership_cannot_grant_orphan_cleanup(self):
        task = self.task("aaaabbbb0006", age=7 * 3600, purpose="development")
        session = self.root / "sessions" / (task * 3)[:32]
        session.mkdir(parents=True)
        (session / "session.json").write_text("invalid json")
        self.pruner.run(now=self.now)
        self.assertEqual(self.deleted, [])
        (session / "session.json").unlink()
        child = self.root / "tasks" / "aaaabbbb0007"
        child.mkdir()
        (child / "state.json").write_text("invalid json")
        self.pruner.run(now=self.now)
        self.assertEqual(self.deleted, [])
        self.assertEqual(self.c.read(task)["status"], "stopped")

    def test_discard_reports_instead_of_raising(self):
        task = self.task("abcdefabcdef", purpose="verification")
        self.assertEqual(prune.discard(self.c, task), "deleted")
        self.assertTrue(prune.discard(self.c, "000000000000").startswith("retained: "))


if __name__ == "__main__":
    unittest.main()
