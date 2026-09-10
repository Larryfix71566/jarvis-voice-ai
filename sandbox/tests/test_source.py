import base64
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from sandbox.artifacts import SandboxError
from sandbox.source import GitSource


class SourceCacheTests(unittest.TestCase):
    def api_results(self):
        return [{"object": {"sha": "a" * 40}}, {"sha": "a" * 40, "tree": {"sha": "b" * 40}},
                {"truncated": False, "tree": [{"type": "blob", "mode": "100644", "size": 10}]}]

    def test_fetch_uses_bare_objects_and_ephemeral_host_only_auth(self):
        with tempfile.TemporaryDirectory() as temp:
            source = GitSource(Path(temp))
            calls = []
            token = "example-private-token"
            def run(argv, **kwargs):
                calls.append((argv, kwargs["env"].copy()))
                stdout = "a" * 40 + "\n" if "rev-parse" in argv else ""
                return subprocess.CompletedProcess(argv, 0, stdout=stdout, stderr="")
            with patch("sandbox.source.GitHubAPI.call", side_effect=self.api_results()), patch("sandbox.source.subprocess.run", side_effect=run):
                directory, sha = source.fetch("owner/repo", "main", token)
            self.assertEqual(sha, "a" * 40)
            self.assertTrue(directory.name.endswith(".git"))
            self.assertIn("--bare", calls[0][0])
            fetch_argv, fetch_env = calls[1]
            self.assertIn("core.hooksPath=/dev/null", fetch_argv)
            self.assertIn("http.followRedirects=false", fetch_argv)
            self.assertIn("--no-recurse-submodules", fetch_argv)
            self.assertIn("--depth=1", fetch_argv)
            self.assertEqual(fetch_argv[-1], "+" + "a" * 40 + ":refs/remotes/origin/main")
            self.assertEqual(fetch_env["GIT_CONFIG_KEY_0"], "http.https://github.com/.extraheader")
            self.assertNotIn(token, repr(fetch_argv))
            self.assertNotIn("GIT_CONFIG_VALUE_0", calls[2][1])
            for file in Path(temp).rglob("*"):
                if file.is_file():
                    self.assertNotIn(token.encode(), file.read_bytes())

    def test_invalid_remote_branch_and_fetch_errors_do_not_disclose_auth(self):
        with tempfile.TemporaryDirectory() as temp:
            source = GitSource(Path(temp))
            with patch("sandbox.source.subprocess.run") as run:
                for repo, branch in [("https://elsewhere/repo", "main"), ("owner/repo", "../main"), ("owner/repo", "main:other")]:
                    with self.assertRaises(SandboxError):
                        source.fetch(repo, branch, "secret")
                run.assert_not_called()
            failed = subprocess.CompletedProcess([], 1, stdout="", stderr="secret")
            with patch("sandbox.source.GitHubAPI.call", side_effect=self.api_results()), patch("sandbox.source.subprocess.run", return_value=failed):
                with self.assertRaises(SandboxError) as result:
                    source.fetch("owner/repo", "main", "secret")
            self.assertNotIn("secret", str(result.exception))

    def test_oversized_remote_is_rejected_before_git_download(self):
        with tempfile.TemporaryDirectory() as temp:
            results = self.api_results()
            results[-1]["tree"][0]["size"] = 1024 * 1024 * 1024
            with patch("sandbox.source.GitHubAPI.call", side_effect=results), patch("sandbox.source.subprocess.run") as run:
                with self.assertRaises(SandboxError):
                    GitSource(Path(temp)).fetch("owner/repo", "main", "secret")
                run.assert_not_called()

    def test_mismatched_commit_is_rejected_before_git_download(self):
        with tempfile.TemporaryDirectory() as temp:
            results = self.api_results()
            results[1]["sha"] = "c" * 40
            with patch("sandbox.source.GitHubAPI.call", side_effect=results), patch("sandbox.source.subprocess.run") as run:
                with self.assertRaises(SandboxError):
                    GitSource(Path(temp)).fetch("owner/repo", "main", "secret")
                run.assert_not_called()

    def test_lost_initialization_can_be_retried_with_the_same_cache(self):
        with tempfile.TemporaryDirectory() as temp:
            source = GitSource(Path(temp))
            failure = subprocess.CompletedProcess([], 1, stdout='', stderr='unavailable')
            with patch('sandbox.source.GitHubAPI.call', side_effect=self.api_results()), patch('sandbox.source.subprocess.run', return_value=failure):
                with self.assertRaises(SandboxError): source.fetch('owner/repo', 'main', 'secret')
            calls = []
            def run(argv, **kwargs):
                calls.append(argv)
                return subprocess.CompletedProcess(argv, 0, stdout='a' * 40 if 'rev-parse' in argv else '', stderr='')
            with patch('sandbox.source.GitHubAPI.call', side_effect=self.api_results()), patch('sandbox.source.subprocess.run', side_effect=run):
                source.fetch('owner/repo', 'main', 'secret')
            self.assertIn('init', calls[0])


if __name__ == "__main__":
    unittest.main()
