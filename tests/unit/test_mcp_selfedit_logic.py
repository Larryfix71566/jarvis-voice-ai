"""Unit tests for mcp_selfedit logic (thin client of the admin sidecar)."""

from __future__ import annotations

import pytest

from mcp_servers.mcp_selfedit import logic


@pytest.fixture(autouse=True)
def _clear_profile_env(monkeypatch):
    """Selection order must not leak from the developer's own shell env."""
    monkeypatch.delenv("JARVIS_UPGRADE_PROFILE", raising=False)


class FakeClient:
    """Duck-typed AdminClient stand-in: routes keyed on (method, path)."""

    def __init__(self, routes=None, fail=False):
        self.routes = routes or {}
        self.fail = fail
        self.posts = []

    def get(self, path):
        if self.fail:
            raise ConnectionError("refused")
        return self.routes[("GET", path)]

    def post(self, path, json=None):
        if self.fail:
            raise ConnectionError("refused")
        self.posts.append((path, json))
        return self.routes[("POST", path)]


MODELS = {
    "ok": True,
    "models": [
        {"name": "kimi-k2", "label": "Kimi K2.7 Code", "provider": "moonshot",
         "model": "kimi-k2.7-code", "key_env": "MOONSHOT_API_KEY",
         "key_present": True, "default": True},
        {"name": "kimi-k3", "label": "Kimi K3", "provider": "moonshot",
         "model": "kimi-k3", "key_env": "MOONSHOT_API_KEY",
         "key_present": False, "default": False},
        {"name": "claude-opus", "label": "Claude Opus 5", "provider": "anthropic",
         "model": "claude-opus-5", "key_env": "ANTHROPIC_API_KEY",
         "key_present": True, "default": False},
    ],
}

SESSION_ACTIVE = {
    "ok": True,
    "job": {"state": "done", "goal": "add a clock", "profile": "kimi-k2 (kimi-k2.7-code)",
            "summary": "3 planning iterations, 1 file edit(s) proposed"},
    "status": {
        "active": True,
        "branch": "jarvis/self-edit/20260811-add-clock",
        "proposals": [{"path": "web/src/components/ClockPanel.tsx",
                       "rationale": "add a clock panel", "diff": "+..."}],
        "validated_ok": True,
    },
}


def _client(overrides: dict | None = None) -> FakeClient:
    routes = {
        ("GET", "/api/selfedit/models"): MODELS,
        ("GET", "/api/selfedit/run"): {"ok": True, "job": {"state": "idle"}, "status": {}},
        ("POST", "/api/selfedit/run"): {"ok": True, "started": True,
                                         "profile": "kimi-k2 (kimi-k2.7-code)"},
        ("POST", "/api/selfedit/validate"): {"ok": True, "checks": [{"name": "allowlist", "ok": True, "output": ""}]},
        ("POST", "/api/selfedit/submit"): {"ok": True, "pr_url": "https://github.com/x/y/pull/9"},
        ("POST", "/api/selfedit/revert"): {"ok": True},
    }
    routes.update(overrides or {})
    return FakeClient(routes)


# ── selfedit_start ─────────────────────────────────────────────────────────

def test_start_preview_starts_nothing():
    c = _client()
    r = logic.selfedit_start(c, "add a clock panel")
    assert r["ok"] and r["needs_confirmation"]
    assert r["profile"] == "kimi-k2"  # registry default
    assert "add a clock panel" in r["summary"]
    assert c.posts == []  # preview never POSTs


def test_start_honors_spoken_profile():
    c = _client()
    r = logic.selfedit_start(c, "add a clock", profile="claude-opus", confirm=True)
    assert r["ok"] and r["started"]
    assert c.posts == [("/api/selfedit/run", {"goal": "add a clock", "profile": "claude-opus"})]
    assert "several minutes" in r["summary"]


def test_start_unknown_profile_names_available():
    r = logic.selfedit_start(_client(), "x", profile="gpt-99")
    assert r["ok"] is False
    assert "gpt-99" in r["error"] and "kimi-k2" in r["error"]


def test_start_missing_key_names_env_var():
    r = logic.selfedit_start(_client(), "x", profile="kimi-k3")
    assert r["ok"] is False
    assert "MOONSHOT_API_KEY" in r["error"]


def test_start_confirm_posts_goal_and_profile():
    c = _client()
    r = logic.selfedit_start(c, "dark theme", confirm=True)
    assert r["started"]
    assert c.posts == [("/api/selfedit/run", {"goal": "dark theme", "profile": "kimi-k2"})]


def test_start_env_profile_beats_registry_default(monkeypatch):
    monkeypatch.setenv("JARVIS_UPGRADE_PROFILE", "claude-opus")
    c = _client()
    r = logic.selfedit_start(c, "add a clock")
    assert r["ok"] and r["profile"] == "claude-opus"  # env beats registry default


def test_start_explicit_profile_beats_env(monkeypatch):
    monkeypatch.setenv("JARVIS_UPGRADE_PROFILE", "claude-opus")
    c = _client()
    logic.selfedit_start(c, "add a clock", profile="kimi-k2", confirm=True)
    assert c.posts == [("/api/selfedit/run", {"goal": "add a clock", "profile": "kimi-k2"})]


def test_start_env_profile_missing_key_names_env_profile(monkeypatch):
    monkeypatch.setenv("JARVIS_UPGRADE_PROFILE", "kimi-k3")
    r = logic.selfedit_start(_client(), "x")
    assert r["ok"] is False and "MOONSHOT_API_KEY" in r["error"] and "kimi-k3" in r["error"]


# ── selfedit_status ────────────────────────────────────────────────────────

def test_status_while_running():
    c = _client({("GET", "/api/selfedit/run"): {
        "ok": True,
        "job": {"state": "running", "goal": "add a clock", "profile": "kimi-k2 (kimi-k2.7-code)"},
        "status": {}}})
    r = logic.selfedit_status(c)
    assert "Still planning" in r["summary"] and "add a clock" in r["summary"]


def test_status_composes_session_and_proposals():
    c = _client({("GET", "/api/selfedit/run"): SESSION_ACTIVE})
    r = logic.selfedit_status(c)
    assert "ClockPanel.tsx" in r["summary"]
    assert "Validation has passed" in r["summary"]
    assert r["active"] is True


def test_status_when_idle():
    r = logic.selfedit_status(_client())
    assert "No upgrade run" in r["summary"]


# ── selfedit_validate ──────────────────────────────────────────────────────

def test_validate_pass():
    r = logic.selfedit_validate(_client())
    assert r["ok"] and r["validated_ok"]
    assert "Validation passed" in r["summary"]


def test_validate_failure_details():
    c = _client({("POST", "/api/selfedit/validate"): {
        "ok": True,
        "checks": [{"name": "allowlist", "ok": False, "output": "jarvis/agents denied"}]}})
    r = logic.selfedit_validate(c)
    assert r["ok"] is False and "allowlist" in r["error"]


# ── selfedit_submit ────────────────────────────────────────────────────────

def test_submit_gated_on_session_state():
    idle = logic.selfedit_submit(_client(), confirm=True)
    assert idle["ok"] is False and "no edit session" in idle["error"]

    unvalidated = _client({("GET", "/api/selfedit/run"): {
        "ok": True, "job": {"state": "done", "summary": "x"},
        "status": {"active": True, "proposals": [{"path": "a", "rationale": "b"}],
                   "validated_ok": False}}})
    r = logic.selfedit_submit(unvalidated, confirm=True)
    assert r["ok"] is False and "validation" in r["error"]


def test_submit_preview_then_confirm():
    c = _client({("GET", "/api/selfedit/run"): SESSION_ACTIVE})
    preview = logic.selfedit_submit(c, confirm=False)
    assert preview["needs_confirmation"] and "cannot merge" in preview["summary"]
    done = logic.selfedit_submit(c, confirm=True)
    assert done["ok"] and done["pr_url"].endswith("/pull/9")
    assert "cannot merge" in done["summary"]


# ── selfedit_revert ────────────────────────────────────────────────────────

def test_revert_two_phase():
    c = _client({("GET", "/api/selfedit/run"): SESSION_ACTIVE})
    preview = logic.selfedit_revert(c, confirm=False)
    assert preview["needs_confirmation"] and "1 proposed edit" in preview["summary"]
    done = logic.selfedit_revert(c, confirm=True)
    assert done["ok"] and "back to normal" in done["summary"]


def test_revert_refused_while_running():
    c = _client({("GET", "/api/selfedit/run"): {
        "ok": True, "job": {"state": "running", "goal": "x"}, "status": {"active": True}}})
    r = logic.selfedit_revert(c, confirm=True)
    assert r["ok"] is False and "still working" in r["error"]


# ── offline degradation ────────────────────────────────────────────────────

@pytest.mark.parametrize("call", [
    lambda c: logic.selfedit_start(c, "goal", confirm=True),
    lambda c: logic.selfedit_status(c),
    lambda c: logic.selfedit_validate(c),
    lambda c: logic.selfedit_submit(c, confirm=True),
    lambda c: logic.selfedit_revert(c, confirm=True),
])
def test_offline_degrades_to_spoken_error(call):
    r = call(FakeClient(fail=True))
    assert r["ok"] is False
    assert "mortimer.sh" in r["error"]
