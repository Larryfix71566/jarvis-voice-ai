"""T4.3 — jarvis/status/github.py (fake `_request`; no network)."""

from __future__ import annotations

import json

import httpx
import pytest

from jarvis.status import github as G
from mcp_servers.mcp_apps import github as gh

TOKEN = "ghp_FIXTURE-SECRET-TOKEN-0123456789abcdef"

PR = {"number": 81, "title": "P4", "state": "open", "draft": False,
      "head": {"ref": "impl/p4", "sha": "abc1234"}, "base": {"ref": "main"},
      "updated_at": "2026-09-23T12:00:00Z", "html_url": "https://github.com/o/r/pull/81"}


class Calls(list):
    responses: dict


@pytest.fixture
def calls(monkeypatch):
    """Route every GitHubClient._request through a fake; record the calls."""
    seen = Calls()
    responses: dict = {}

    def fake_request(self, method, url, **kwargs):
        seen.append((method, url, kwargs, self.token, self.owner))
        status, payload = responses.get(url, (404, {"message": "Not Found"}))
        return httpx.Response(status, json=payload, request=httpx.Request(method, url))

    monkeypatch.setattr(gh.GitHubClient, "_request", fake_request)
    monkeypatch.delenv("JARVIS_GITHUB_REPO", raising=False)
    monkeypatch.setenv("JARVIS_GITHUB_TOKEN", TOKEN)
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_other-token-should-lose-000000000000")
    seen.responses = responses
    return seen


def test_prs_uses_selfedit_repo_default_and_token(calls):
    base = "https://api.github.com/repos/Larryfix71566/jarvis-voice-ai"
    calls.responses[f"{base}/pulls"] = (200, [PR])
    out = G.github_status("prs", state="open", limit=5)
    assert out["ok"] is True
    assert out["repo"] == "Larryfix71566/jarvis-voice-ai"
    assert out["source"].startswith("github:Larryfix71566/jarvis-voice-ai@")
    assert out["pulls"][0]["number"] == 81 and out["pulls"][0]["head"] == "impl/p4"
    method, url, kwargs, token, owner = calls[0]
    assert (method, url, kwargs["params"]) == ("GET", f"{base}/pulls", {"state": "open", "per_page": 5})
    assert token == TOKEN and owner == "Larryfix71566"


def test_repo_and_token_fallbacks(calls, monkeypatch):
    monkeypatch.setenv("JARVIS_GITHUB_REPO", "acme/widgets")
    monkeypatch.delenv("JARVIS_GITHUB_TOKEN")
    calls.responses["https://api.github.com/repos/acme/widgets/pulls"] = (200, [])
    out = G.github_status("prs")
    assert out["ok"] and out["pulls"] == []
    assert calls[0][3] == "ghp_other-token-should-lose-000000000000"
    assert calls[0][4] == "acme"


def test_checks(calls):
    base = "https://api.github.com/repos/Larryfix71566/jarvis-voice-ai"
    calls.responses[f"{base}/pulls/81"] = (200, PR)
    calls.responses[f"{base}/commits/abc1234/check-runs"] = (200, {"check_runs": [
        {"name": "Unit tests", "status": "completed", "conclusion": "failure"}]})
    out = G.github_status("checks", number=81)
    assert out["ok"] and out["number"] == 81 and out["sha"] == "abc1234"
    assert out["checks"] == [{"name": "Unit tests", "status": "completed", "conclusion": "failure"}]


def test_no_write_methods_called(calls):
    base = "https://api.github.com/repos/Larryfix71566/jarvis-voice-ai"
    calls.responses[f"{base}/pulls"] = (200, [PR])
    calls.responses[f"{base}/pulls/81"] = (200, PR)
    calls.responses[f"{base}/commits/abc1234/check-runs"] = (200, {"check_runs": []})
    G.github_status("prs", state="all", limit=50)
    G.github_status("checks", number=81)
    assert calls and {c[0] for c in calls} == {"GET"}
    # And the module reaches only the two read methods.
    import inspect

    src = inspect.getsource(G)
    for writer in ("put_file", "create_repo", "post", "PUT", "PATCH", "DELETE"):
        assert writer not in src


def test_token_never_in_output(calls, monkeypatch):
    out_401 = G.github_status("prs")  # 404 default -> error
    assert out_401["ok"] is False
    calls.responses["https://api.github.com/repos/Larryfix71566/jarvis-voice-ai/pulls"] = (
        401, {"message": "Bad credentials"})
    out = G.github_status("prs")
    assert out["ok"] is False and "HTTP 401" in out["error"]

    def leaky(self, method, url, **kwargs):
        raise RuntimeError(f"proxy refused Authorization: Bearer {TOKEN} ({TOKEN})")

    monkeypatch.setattr(gh.GitHubClient, "_request", leaky)
    out2 = G.github_status("prs")
    for payload in (out_401, out, out2):
        blob = json.dumps(payload)
        assert TOKEN not in blob and "FIXTURE-SECRET" not in blob


def test_validation_and_missing_token(calls, monkeypatch):
    assert G.github_status("issues")["error"] == "kind must be 'prs' or 'checks'"
    assert G.github_status("prs", state="merged")["ok"] is False
    assert G.github_status("checks")["error"] == "checks needs a pull request number"
    monkeypatch.delenv("JARVIS_GITHUB_TOKEN")
    monkeypatch.delenv("GITHUB_TOKEN")
    assert G.github_status("prs") == {
        "ok": False, "error": "no GitHub token configured (JARVIS_GITHUB_TOKEN or GITHUB_TOKEN)"}
    assert calls == []


def test_limit_is_clamped(calls):
    calls.responses["https://api.github.com/repos/Larryfix71566/jarvis-voice-ai/pulls"] = (200, [])
    G.github_status("prs", limit=500)
    assert calls[0][2]["params"]["per_page"] == G.MAX_LIMIT
