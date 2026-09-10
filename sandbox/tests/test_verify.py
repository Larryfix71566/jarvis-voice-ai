from contextlib import nullcontext
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from sandbox.artifacts import Candidate, File, SandboxError
from sandbox.profiles import Profile
from sandbox.verify import Verifier


class VerificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.task = "development-task"
        self.candidate = Candidate((File("app.py", 0o644, b"accepted"),))
        self.baseline = self.candidate
        self.journal = {"candidate": self.candidate.fingerprint, "revision": 1, "verification": None}
        self.events = []
        self.exit_code = 0
        self.final_candidate = self.candidate
        self.failure = False
        self.edit_during_check = False
        self.profile = Profile("test", (), (), (("required", ("/protected/python", "check.py")),))
        self.verifier = Verifier(self, self)

    def _locked(self): return nullcontext()
    def _journal(self): return self.journal.copy()
    def _save(self, journal): self.journal = journal
    def status(self): return self.journal.copy()
    def freeze(self):
        self.journal["verification"] = None
        return self.candidate
    def frozen(self): return self.candidate

    def stop(self, task): self.events.append(("stop", task))
    def start(self, task, **kwargs): self.events.append(("start", task))
    def command(self, *args, **kwargs): return subprocess.CompletedProcess(args, 0)
    def create(self, *args, **kwargs):
        self.assertEqual(self.events[-1], ("stop", self.task))
        self.assertEqual(kwargs["purpose"], "verification")
        self.assertEqual(kwargs["candidate"], self.candidate)
        return "independent-task"
    def hydrate(self, task): self.events.append(("hydrate", task))
    def read(self, task):
        return {"vm": task, "hydrated": True, "network": "offline", "worker": "mortimer-dev"}
    def worker_prefix(self, state): return ["sudo", "-u", "mortimer-dev"]
    def rpc(self, task, request):
        self.assertEqual(task, "independent-task")
        return self.final_candidate.encode()
    def guest(self, task, argv, **kwargs):
        self.assertEqual(task, "independent-task")
        self.assertEqual(argv[:3], ["sudo", "-u", "mortimer-dev"])
        self.events.append(("check", task))
        if self.edit_during_check:
            self.journal.update(candidate=None, verification=None, revision=2)
        if self.failure:
            raise SandboxError("guest interrupted")
        return subprocess.CompletedProcess(argv, self.exit_code, stdout=b"check output", stderr=b"")

    def verify(self):
        return self.verifier.verify(self, self.directory, "HEAD", "prepared-image", self.profile)

    def test_receipt_binds_a_separate_vm_candidate_profile_and_logs(self):
        receipt = self.verify()
        self.assertTrue(receipt["passed"])
        self.assertEqual(receipt["verification_task"], "independent-task")
        self.assertEqual(self.events[-1], ("stop", "independent-task"))
        self.assertEqual(self.verifier.receipt(self, "prepared-image", self.profile), receipt)
        changed = replace(self.profile, checks=(("other", ("/protected/python", "other.py")),))
        with self.assertRaises(SandboxError):
            self.verifier.receipt(self, "prepared-image", changed)
        directory = self.directory / "verification" / receipt["attempt"]
        (directory / "required.log").write_text("corrupt")
        with self.assertRaises(SandboxError):
            self.verifier.receipt(self, "prepared-image", self.profile)

    def test_failing_check_and_source_mutation_never_approve_publication(self):
        for mode in ["check", "mutation"]:
            with self.subTest(mode=mode):
                self.exit_code = 1 if mode == "check" else 0
                self.final_candidate = self.candidate if mode == "check" else Candidate((File("app.py", 0o644, b"changed by test"),))
                receipt = self.verify()
                self.assertFalse(receipt["passed"])
                with self.assertRaises(SandboxError):
                    self.verifier.receipt(self, "prepared-image", self.profile)

    def test_interruption_stops_verifier_and_persists_failure(self):
        self.failure = True
        with self.assertRaises(SandboxError):
            self.verify()
        self.assertEqual(self.events[-1], ("stop", "independent-task"))
        self.assertFalse(self.journal["verification"]["passed"])
        receipt = json.loads(next((self.directory / "verification").glob("*/receipt.json")).read_bytes())
        self.assertFalse(receipt["passed"])

    def test_concurrent_edit_cannot_receive_an_older_receipt(self):
        self.edit_during_check = True
        self.verify()
        self.assertIsNone(self.journal["verification"])
        with self.assertRaises(SandboxError):
            self.verifier.receipt(self, "prepared-image", self.profile)

    def test_missing_required_check_is_rejected_even_if_receipt_says_passed(self):
        receipt = self.verify()
        path = self.directory / "verification" / receipt["attempt"] / "receipt.json"
        receipt["checks"] = []
        path.write_text(json.dumps(receipt))
        with self.assertRaises(SandboxError):
            self.verifier.receipt(self, "prepared-image", self.profile)


if __name__ == "__main__":
    unittest.main()
