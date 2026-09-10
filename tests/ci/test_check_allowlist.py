"""Run the real gate against real named and detached Git checkouts."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class AllowlistGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.env = {k: v for k, v in os.environ.items()
                    if not k.startswith(("GIT_", "GITHUB_"))}
        self.env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
        for rel in ["scripts/check_allowlist.py", "jarvis/selfedit/allowlist.py",
                    "config/self_edit_allowlist.json"]:
            dest = self.root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / rel, dest)
        self.git("init", "-q", "-b", "feature/maintenance")
        self.git("add", ".")
        self.git("commit", "-qm", "base")
        (self.root / "requirements.txt").write_text("example-dependency\n")
        self.git("add", ".")
        self.git("commit", "-qm", "human dependency update")

    def git(self, *args):
        return subprocess.run(["git", "-c", "user.name=Test", "-c",
                               "user.email=test@example.invalid", *args],
                              cwd=self.root, env=self.env, check=True,
                              capture_output=True, text=True)

    def gate(self, *, branch=None, event="pull_request", ci=True, diff="HEAD~1...HEAD"):
        env = dict(self.env)
        if ci:
            env.update(GITHUB_ACTIONS="true", GITHUB_EVENT_NAME=event)
        if branch is not None:
            env["GITHUB_HEAD_REF"] = branch
        return subprocess.run([sys.executable, "scripts/check_allowlist.py", diff],
                              cwd=self.root, env=env, capture_output=True, text=True)

    def test_named_human_branch_passes_locally(self):
        self.assertEqual(self.gate(ci=False).returncode, 0)

    def test_detached_human_pr_uses_event_branch(self):
        self.git("checkout", "--detach", "-q")
        self.assertEqual(self.gate(branch="feature/maintenance").returncode, 0)

    def test_detached_agent_pr_remains_restricted(self):
        self.git("checkout", "--detach", "-q")
        result = self.gate(branch="jarvis/self-edit/task")
        self.assertEqual(result.returncode, 1)
        self.assertIn("requirements.txt", result.stdout)

    def test_sandbox_publisher_branches_remain_restricted_in_ci_and_locally(self):
        branch = 'mortimer/selfedit/session-123'
        self.git('checkout', '-qb', branch)
        self.assertEqual(self.gate(ci=False).returncode, 1)
        self.git('checkout', '--detach', '-q')
        result = self.gate(branch=branch)
        self.assertEqual(result.returncode, 1)
        self.assertIn('requirements.txt', result.stdout)

    def test_missing_ci_branch_is_conservative_even_on_named_checkout(self):
        self.assertEqual(self.gate().returncode, 1)

    def test_unexpected_event_is_conservative(self):
        self.assertEqual(self.gate(branch="feature/maintenance", event="push").returncode, 1)

    def test_local_detached_checkout_is_conservative(self):
        self.git("checkout", "--detach", "-q")
        self.assertEqual(self.gate(ci=False).returncode, 1)

    def test_non_ci_head_ref_cannot_exempt_agent_branch(self):
        self.git("checkout", "-qb", "jarvis/self-edit/task")
        self.assertEqual(self.gate(ci=False, branch="feature/maintenance").returncode, 1)

    def test_bad_diff_cannot_pass_agent_gate(self):
        result = self.gate(branch="jarvis/self-edit/task", diff="missing-ref...HEAD")
        self.assertEqual(result.returncode, 1)
        self.assertIn("git diff failed", result.stdout)


if __name__ == "__main__":
    unittest.main()
