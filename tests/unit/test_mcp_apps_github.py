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
