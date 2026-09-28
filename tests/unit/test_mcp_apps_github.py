"""Unit tests for mcp_servers/mcp_apps/github.py (MORTIMER_AGENT_TRUST_PLAN.md D8).

httpx.Response objects are constructed directly (no real network) via
httpx.Response(status_code, ...) — GitHubClient._raise_for_status takes a
Response and never touches the network itself.
"""

import httpx
import pytest

from mcp_servers.mcp_apps.github import GitHubClient, GitHubError


def make_client() -> GitHubClient:
    return GitHubClient(token="fake-token", owner="fake-owner")


class TestAuthFailureMessage:
    def test_401_message_is_specific_and_disclaims_admin_sidecar(self):
        client = make_client()
        resp = httpx.Response(401, json={"message": "Bad credentials"},
                               request=httpx.Request("GET", "https://api.github.com/user"))
        with pytest.raises(GitHubError) as exc_info:
            client._raise_for_status(resp, "lookup of authenticated user")
        message = str(exc_info.value)
        assert "HTTP 401" in message
        assert "GITHUB_TOKEN" in message
        assert "admin sidecar" in message.lower()
        # The message must not silently swallow into a generic template —
        # confirm it does NOT contain the raw GitHub "Bad credentials" body,
        # which would be a sign the special case did not trigger.
        assert "failed (HTTP 401): Bad credentials" not in message

    def test_403_gets_the_same_treatment_as_401(self):
        client = make_client()
        resp = httpx.Response(403, json={"message": "Forbidden"},
                               request=httpx.Request("GET", "https://api.github.com/user"))
        with pytest.raises(GitHubError) as exc_info:
            client._raise_for_status(resp, "creation of repo x")
        message = str(exc_info.value)
        assert "HTTP 403" in message
        assert "GITHUB_TOKEN" in message
        assert "admin sidecar" in message.lower()

    def test_never_leaks_the_token_value(self):
        client = GitHubClient(token="ghp_supersecretvalue1234567890", owner="o")
        resp = httpx.Response(401, json={"message": "Bad credentials"},
                               request=httpx.Request("GET", "https://api.github.com/user"))
        with pytest.raises(GitHubError) as exc_info:
            client._raise_for_status(resp, "lookup")
        assert "supersecret" not in str(exc_info.value)


class TestOtherFailuresUnchanged:
    def test_404_style_error_keeps_the_generic_shape(self):
        # Regression: only 401/403 get the special-cased message; every
        # other status keeps the original "{what} failed (HTTP {code}):
        # {detail}" shape used by repo_exists's 404 short-circuit and other
        # callers that inspect this text.
        client = make_client()
        resp = httpx.Response(422, json={"message": "Validation Failed"},
                               request=httpx.Request("POST", "https://api.github.com/user/repos"))
        with pytest.raises(GitHubError) as exc_info:
            client._raise_for_status(resp, "creation of repo x")
        message = str(exc_info.value)
        assert "creation of repo x failed (HTTP 422): Validation Failed" == message

    def test_500_keeps_the_generic_shape(self):
        client = make_client()
        resp = httpx.Response(500, text="internal error",
                               request=httpx.Request("GET", "https://api.github.com/user"))
        with pytest.raises(GitHubError) as exc_info:
            client._raise_for_status(resp, "lookup")
        assert "HTTP 500" in str(exc_info.value)
        assert "admin sidecar" not in str(exc_info.value).lower()


class TestReadMethods:
    """Status spec T4.3: list_pulls / pull_checks, GET only."""

    PR = {"number": 81, "title": "P4: external reads", "state": "open", "draft": True,
          "head": {"ref": "impl/p4-external", "sha": "abc1234def"},
          "base": {"ref": "main", "sha": "000"}, "updated_at": "2026-09-23T12:00:00Z",
          "html_url": "https://github.com/o/r/pull/81", "body": "long text", "user": {"login": "x"}}

    def _client(self, responses):
        client = GitHubClient(token="ghp_fixturetokenvalue000000000000", owner="o")
        calls = []

        def fake_request(method, url, **kwargs):
            calls.append((method, url, kwargs))
            status, payload = responses[len(calls) - 1]
            return httpx.Response(status, json=payload, request=httpx.Request(method, url))

        client._request = fake_request
        return client, calls

    def test_list_pulls_shape_and_params(self):
        client, calls = self._client([(200, [self.PR, {**self.PR, "number": 80}])])
        out = client.list_pulls("r", state="all", limit=1)
        assert calls == [("GET", "https://api.github.com/repos/o/r/pulls",
                          {"params": {"state": "all", "per_page": 1}})]
        assert out == [{"number": 81, "title": "P4: external reads", "state": "open",
                        "draft": True, "head": "impl/p4-external", "base": "main",
                        "updated_at": "2026-09-23T12:00:00Z",
                        "html_url": "https://github.com/o/r/pull/81"}]

    def test_pull_checks_reads_head_sha_then_check_runs(self):
        runs = {"total_count": 2, "check_runs": [
            {"name": "Unit tests", "status": "completed", "conclusion": "success", "id": 1},
            {"name": "evals", "status": "in_progress", "conclusion": None, "id": 2}]}
        client, calls = self._client([(200, self.PR), (200, runs)])
        out = client.pull_checks("r", 81)
        assert [c[1] for c in calls] == [
            "https://api.github.com/repos/o/r/pulls/81",
            "https://api.github.com/repos/o/r/commits/abc1234def/check-runs"]
        assert out == {"sha": "abc1234def", "checks": [
            {"name": "Unit tests", "status": "completed", "conclusion": "success"},
            {"name": "evals", "status": "in_progress", "conclusion": None}]}

    def test_no_write_methods_called(self):
        client, calls = self._client([(200, [self.PR]), (200, self.PR), (200, {"check_runs": []})])
        client.list_pulls("r")
        client.pull_checks("r", 81)
        assert {c[0] for c in calls} == {"GET"}

    def test_read_errors_keep_the_auth_message_and_hide_the_token(self):
        client, _ = self._client([(401, {"message": "Bad credentials"})])
        with pytest.raises(GitHubError) as exc_info:
            client.list_pulls("r")
        assert "HTTP 401" in str(exc_info.value)
        assert "fixturetoken" not in str(exc_info.value)
