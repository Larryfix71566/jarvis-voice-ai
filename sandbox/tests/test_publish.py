import base64
from contextlib import nullcontext
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from sandbox.artifacts import Candidate, File, SandboxError
from sandbox.publish import GitHubAPI, NoRedirect, Publisher


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.baseline = Candidate((File("app.py", 0o644, b"old"), File("delete.sh", 0o755, b"old executable"),
                                   File("policy.md", 0o644, b"protected")))
        self.candidate = Candidate((File("app.py", 0o644, b"new"), File("new.bin", 0o755, b"\x00\xff"),
                                    File("policy.md", 0o644, b"protected")))
        self.journal = {"candidate": self.candidate.fingerprint, "verification": {"attempt": "verified", "passed": True}}
        self.calls = []
        self.commit_objects = set()
        self.remote = None
        self.pulls = []
        self.fail_after = None
        self.fail_verification = False
        self.changed_source = False
        self.publisher = Publisher(self)

    def _locked(self): return nullcontext()
    def _journal(self): return self.journal
    def allowed(self, path): return path in {"app.py", "delete.sh", "new.bin"}
    def frozen(self): return self.candidate
    def assert_unchanged(self, fingerprint):
        self.assertEqual(fingerprint, self.candidate.fingerprint)
        if self.changed_source:
            raise SandboxError("source changed")
    def receipt(self, *args):
        if self.fail_verification:
            raise SandboxError("no valid receipt")
        return {"source_commit": "a" * 40, "attempt": "verified"}

    def maybe_lose(self, stage):
        if self.fail_after == stage:
            self.fail_after = None
            raise SandboxError("response lost")

    def call(self, method, path, body=None, **kwargs):
        self.calls.append((method, path, body))
        if method == "GET" and "/git/commits/" in path:
            return {"sha": "a" * 40, "tree": {"sha": "b" * 40}}
        if method == "POST" and path.endswith("/git/blobs"):
            data = base64.b64decode(body["content"])
            return {"sha": hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()}
        if method == "POST" and path.endswith("/git/trees"):
            self.tree_body = body
            return {"sha": "c" * 40}
        if method == "POST" and path.endswith("/git/commits"):
            sha = hashlib.sha1(json.dumps(body, sort_keys=True).encode()).hexdigest()
            self.commit_objects.add(sha)
            self.maybe_lose("commit")
            return {"sha": sha}
        if method == "GET" and "/git/ref/heads/" in path:
            return self.remote
        if method == "POST" and path.endswith("/git/refs"):
            self.remote = {"ref": body["ref"], "object": {"sha": body["sha"]}}
            self.maybe_lose("branch")
            return self.remote
        if method == "GET" and "/pulls?" in path:
            return self.pulls
        if method == "POST" and path.endswith("/pulls"):
            pr = {"number": 23, "state": "open", "base": {"ref": body["base"]},
                  "head": {"ref": body["head"], "sha": self.remote["object"]["sha"], "repo": {"full_name": "owner/repo"}}}
            self.pulls.append(pr)
            self.maybe_lose("pr")
            return pr
        raise AssertionError((method, path))

    def publish(self, **overrides):
        args = {"repository": "owner/repo", "branch": "mortimer/selfedit/task-1", "base_branch": "main",
                "title": "Tested update", "body": "Independent checks passed."}
        args.update(overrides)
        return self.publisher.publish(self, self, "image", "profile", **args)

    def test_only_accepted_changes_are_written_and_original_tree_is_preserved(self):
        result = self.publish()
        self.assertEqual(result["url"], "https://github.com/owner/repo/pull/23")
        self.assertEqual(self.tree_body["base_tree"], "b" * 40)
        entries = {entry["path"]: entry for entry in self.tree_body["tree"]}
        self.assertEqual(set(entries), {"app.py", "delete.sh", "new.bin"})
        self.assertIsNone(entries["delete.sh"]["sha"])
        self.assertEqual(entries["new.bin"]["mode"], "100755")
        self.assertFalse((self.directory / "app.py").exists())
        self.assertFalse((self.directory / "new.bin").exists())
        posts = [body for method, path, body in self.calls if method == "POST" and path.endswith("/pulls")]
        self.assertTrue(posts[0]["draft"])

    def test_lost_commit_response_reuses_exact_commit_object(self):
        self.fail_after = "commit"
        with self.assertRaises(SandboxError): self.publish()
        result = self.publish()
        commits = [body for method, path, body in self.calls if method == "POST" and path.endswith("/git/commits")]
        self.assertEqual(len(commits), 2)
        self.assertEqual(commits[0], commits[1])
        self.assertEqual(self.commit_objects, {result["commit"]})

    def test_lost_branch_and_pr_responses_do_not_create_duplicates(self):
        for stage in ["branch", "pr"]:
            with self.subTest(stage=stage):
                (self.directory / "publication.json").unlink(missing_ok=True)
                self.calls, self.pulls, self.remote = [], [], None
                self.fail_after = stage
                with self.assertRaises(SandboxError): self.publish()
                self.publish()
                self.assertEqual(len(self.pulls), 1)
                self.assertEqual(sum(method == "POST" and path.endswith("/git/refs") for method, path, _ in self.calls), 1)
                self.assertEqual(sum(method == "POST" and path.endswith("/pulls") for method, path, _ in self.calls), 1)

    def test_branch_with_other_code_is_never_overwritten(self):
        self.remote = {"ref": "refs/heads/mortimer/selfedit/task-1", "object": {"sha": "d" * 40}}
        with self.assertRaises(SandboxError): self.publish()
        self.assertFalse(any(method in {"PATCH", "PUT", "DELETE"} for method, _, _ in self.calls))
        self.assertEqual(self.pulls, [])

    def test_cancellation_after_commit_prevents_branch_or_pr_creation(self):
        original = self.call
        def cancelled(method, path, *args, **kwargs):
            result = original(method, path, *args, **kwargs)
            if method == 'POST' and path.endswith('/git/commits'):
                (self.directory / 'cancelled.json').write_text('{}')
            return result
        with patch.object(self, 'call', side_effect=cancelled):
            with self.assertRaises(SandboxError): self.publish()
        self.assertIsNone(self.remote)
        self.assertEqual(self.pulls, [])
        self.assertIn('commit', json.loads((self.directory / 'publication.json').read_bytes()))

    def test_missing_receipt_source_changes_and_invalid_targets_fail_before_network(self):
        self.fail_verification = True
        with self.assertRaises(SandboxError): self.publish()
        self.fail_verification = False
        self.changed_source = True
        with self.assertRaises(SandboxError): self.publish()
        self.changed_source = False
        for override in [{"branch": "main"}, {"repository": "https://elsewhere/repo"}, {"base_branch": "../main"}]:
            with self.assertRaises(SandboxError): self.publish(**override)
        self.assertEqual(self.calls, [])

    def test_policy_changes_and_description_credentials_are_rejected(self):
        self.candidate = Candidate((File("policy.md", 0o644, b"bypass"),))
        with self.assertRaises(SandboxError): self.publish()
        with self.assertRaises(SandboxError): self.publish(body="sk-" + "x" * 30)
        self.assertEqual(self.calls, [])

    def test_changed_intent_cannot_resume_a_different_publication(self):
        self.fail_after = "commit"
        with self.assertRaises(SandboxError): self.publish()
        calls = len(self.calls)
        with self.assertRaises(SandboxError): self.publish(title="Different title")
        self.assertEqual(len(self.calls), calls)

    def test_api_errors_do_not_disclose_token_and_redirects_are_disabled(self):
        token = "private-host-credential"
        api = GitHubAPI(token)
        with patch.object(api._opener, "open", side_effect=HTTPError("https://api.github.com/repos/owner/repo", 403, token, {}, None)):
            with self.assertRaises(SandboxError) as result:
                api.call("GET", "/repos/owner/repo/git/commits/" + "a" * 40)
        self.assertNotIn(token, str(result.exception))
        self.assertIsNone(NoRedirect().redirect_request(None, None, 302, "", {}, "https://elsewhere.invalid"))


if __name__ == "__main__":
    unittest.main()
