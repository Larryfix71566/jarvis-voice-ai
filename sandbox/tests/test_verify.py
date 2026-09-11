from contextlib import nullcontext
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

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
        self.start_kwargs = []
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
    def start(self, task, **kwargs):
        self.events.append(("start", task)); self.start_kwargs.append(kwargs)
    def command(self, *args, **kwargs): return subprocess.CompletedProcess(args, 0)
    def create(self, *args, **kwargs):
        self.assertEqual(self.events[-1], ("stop", self.task))
        self.assertEqual(kwargs["purpose"], "verification")
        self.assertEqual(kwargs["candidate"], self.candidate)
        return "independent-task"
    def hydrate(self, task): self.events.append(("hydrate", task))
    def read(self, task):
        return {"vm": task, "hydrated": True, "network": "offline", "worker": "mortimer-dev", "source_commit": "a" * 40}
    def worker_prefix(self, state): return ["sudo", "-u", "mortimer-dev"]
    def rpc(self, task, request):
        self.assertEqual(task, "independent-task")
        return self.final_candidate.encode()
    def guest(self, task, argv, **kwargs):
        self.assertEqual(task, "independent-task")
        self.assertEqual(argv[:3], ["sudo", "-u", "mortimer-dev"])
        self.assertEqual(argv[3:7], ["/bin/bash", "--noprofile", "--norc", "-c"])
        self.events.append(("check", task))
        if self.edit_during_check:
            self.journal.update(candidate=None, verification=None, revision=2)
        if self.failure:
            raise SandboxError("guest interrupted")
        return subprocess.CompletedProcess(argv, self.exit_code, stdout=b"check output", stderr=b"")

    def verify(self):
        return self.verifier.verify(self, self.directory, "prepared-image", self.profile)

    def test_mortimer_full_unit_gates_keep_900_second_timeout(self):
        self.profile = Profile("mortimer", (), (), tuple(
            (name, ("/protected/python", "check.py"))
            for name in ("baseline-backend", "backend", "native")
        ))
        with patch.object(self.verifier, "run_check", wraps=self.verifier.run_check) as check:
            self.assertTrue(self.verify()["passed"])
        self.assertEqual([call.args[-1] for call in check.call_args_list], [900, 900, 1800])

    def test_graphics_required_profile_runs_independent_clone_with_desktop(self):
        self.profile = Profile("graphics", (), (), (("required", ("check.py",)),), requires_graphics=True)
        self.assertTrue(self.verify()["passed"])
        self.assertEqual(len(self.start_kwargs), 2)
        self.assertEqual(self.start_kwargs[-1], {"provisioning": False, "headless": False})

    def test_default_profile_verification_remains_headless(self):
        self.assertTrue(self.verify()["passed"])
        self.assertEqual(self.start_kwargs[-1], {"provisioning": False, "headless": True})

    def test_check_creates_its_log_directory_before_executing(self):
        directory = self.directory / 'new-check-logs'
        def guest(task, argv, **kwargs):
            self.assertTrue(directory.is_dir())
            kwargs['on_output'](b'progress\n', b'')
            return subprocess.CompletedProcess(argv, 0, stdout=b'done\n', stderr=b'')
        with patch.object(self, 'guest', side_effect=guest):
            self.verifier.run_check('independent-task', 'test', ('true',), directory, 5)
        self.assertEqual((directory / 'test.log').read_bytes(), b'done\n\n')

    def test_live_log_withholds_partial_lines_and_redacts_completed_credentials(self):
        fake_secret = b"sk-" + b"a" * 30
        log = self.directory / "live.log"
        def guest(task, argv, **kwargs):
            kwargs['on_output'](b"started\n" + fake_secret[:12], b"")
            self.assertEqual(log.read_bytes(), b"started\n\n")
            kwargs['on_output'](b"started\n" + fake_secret + b"\n", b"")
            self.assertNotIn(fake_secret, log.read_bytes())
            self.assertIn(b"[redacted credential-shaped value]", log.read_bytes())
            return subprocess.CompletedProcess(argv, 0, stdout=b"done\n", stderr=b"")
        with patch.object(self, 'guest', side_effect=guest):
            result = self.verifier.run_check('independent-task', 'live', ('true',), self.directory, 5)
        self.assertTrue(result['passed'])
        self.assertEqual(log.read_bytes(), b"done\n\n")

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

    def test_native_checks_reselect_synthetic_keychain_before_execution(self):
        calls = []
        def guest(task, argv, **kwargs):
            calls.append(argv)
            return subprocess.CompletedProcess(argv, 0, stdout=b'', stderr=b'')
        with patch.object(self, 'guest', side_effect=guest):
            result = self.verifier.run_check('independent-task', 'native', ('swift', 'test'), self.directory, 30)
        self.assertTrue(result['passed'])
        self.assertEqual([args[4] for args in calls[:3]], ['list-keychains', 'default-keychain', 'unlock-keychain'])
        self.assertEqual(calls[-1][3:7], ['/bin/bash', '--noprofile', '--norc', '-c'])


if __name__ == "__main__":
    unittest.main()
