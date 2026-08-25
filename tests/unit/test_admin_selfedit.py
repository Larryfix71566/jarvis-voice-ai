"""Unit tests for the admin sidecar's async upgrade-run endpoints."""

from __future__ import annotations

import threading
import time

import pytest
import yaml
from fastapi.testclient import TestClient

import jarvis.admin.server as srv
from jarvis.admin.server import app


REGISTRY = {
    "default": "kimi-k2",
    "profiles": [
        {
            "name": "kimi-k2",
            "label": "Kimi K2.7 Code",
            "provider": "moonshot",
            "model": "kimi-k2.7-code",
            "base_url": "https://api.moonshot.ai/v1",
            "api_key_env": "MOONSHOT_API_KEY",
            "temperature": None,
        },
        {
            "name": "claude-opus",
            "label": "Claude Opus 5",
            "provider": "anthropic",
            "model": "claude-opus-5",
            "base_url": "https://api.anthropic.com/v1/",
            "api_key_env": "ANTHROPIC_API_KEY",
            "temperature": 0.2,
        },
    ],
}


@pytest.fixture(autouse=True)
def reset_run_job():
    with srv._run_lock:
        srv._run_job.update(
            state="idle", goal=None, profile=None, summary=None,
            started_at=None, finished_at=None,
        )
    yield


@pytest.fixture(autouse=True)
def reset_stagings():
    """G2: staging state must not leak between tests."""
    with srv._staging_lock:
        srv._selfedit_stagings.clear()
    yield
    with srv._staging_lock:
        srv._selfedit_stagings.clear()


@pytest.fixture
def registry_file(tmp_path, monkeypatch):
    p = tmp_path / "upgrade_models.yaml"
    p.write_text(yaml.safe_dump(REGISTRY))
    monkeypatch.setenv("JARVIS_UPGRADE_MODELS", str(p))
    monkeypatch.delenv("MOONSHOT_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("JARVIS_UPGRADE_PROFILE", raising=False)
    return p


class FakeAgent:
    """UpgradeAgent stand-in: instant or gated scripted run."""

    crash = False
    gate: threading.Event | None = None

    def __init__(self, service, profile=None):
        self.profile = profile

    def model_label(self):
        return f"{self.profile or 'kimi-k2'} (fake-model)"

    def run(self, goal, plan=None):
        if FakeAgent.gate is not None:
            FakeAgent.gate.wait(timeout=5)
        if FakeAgent.crash:
            raise RuntimeError("boom")
        return {"ok": True, "summary": f"planned {goal!r}"}


def _install_fake_agent(monkeypatch, crash=False, gate=None):
    FakeAgent.crash = crash
    FakeAgent.gate = gate
    monkeypatch.setattr(srv, "_make_agent", lambda service, profile: FakeAgent(service, profile))


def _wait_for_job(client, state, timeout=5.0):
    deadline = time.time() + timeout
    job = None
    while time.time() < deadline:
        job = client.get("/api/selfedit/run").json()["job"]
        if job["state"] == state:
            return job
        time.sleep(0.02)
    raise AssertionError(f"job never reached state {state!r}")


# ----------------------------------------------------------------- models


def test_models_endpoint_lists_profiles(registry_file):
    c = TestClient(app)
    body = c.get("/api/selfedit/models").json()
    assert body["ok"] is True
    by_name = {p["name"]: p for p in body["models"]}
    assert set(by_name) == {"kimi-k2", "claude-opus"}
    assert by_name["kimi-k2"]["default"] is True
    assert by_name["kimi-k2"]["key_present"] is False  # env unset in fixture
    assert all("key_env" in p for p in body["models"])


# -------------------------------------------------------------------- run


def test_run_is_async_and_completes(registry_file, monkeypatch):
    _install_fake_agent(monkeypatch)
    c = TestClient(app)
    res = c.post("/api/selfedit/run",
                 json={"goal": "add a clock", "profile": "claude-opus"}).json()
    assert res["ok"] and res["started"]
    assert res["profile"] == "claude-opus (fake-model)"
    job = _wait_for_job(c, "done")
    assert job["summary"] == "planned 'add a clock'"
    assert job["profile"] == "claude-opus (fake-model)"


def test_second_run_refused_while_running_and_writes_gated(registry_file, monkeypatch):
    gate = threading.Event()
    _install_fake_agent(monkeypatch, gate=gate)
    c = TestClient(app)
    res = c.post("/api/selfedit/run", json={"goal": "one"}).json()
    assert res["started"] is True
    try:
        again = c.post("/api/selfedit/run", json={"goal": "two"}).json()
        assert again["ok"] is False and "already in progress" in again["error"]
        for ep in ("validate", "submit", "revert"):
            blocked = c.post(f"/api/selfedit/{ep}").json()
            assert blocked["ok"] is False and "in progress" in blocked["error"]
    finally:
        gate.set()
    _wait_for_job(c, "done")


def test_run_unknown_profile_rejected(registry_file):
    c = TestClient(app)  # real _make_agent → resolves against the test registry
    res = c.post("/api/selfedit/run",
                 json={"goal": "add a clock", "profile": "gpt-99"}).json()
    assert not res["ok"]
    assert "unknown upgrade model profile" in res["error"]
    assert "kimi-k2" in res["error"]
    assert c.get("/api/selfedit/run").json()["job"]["state"] == "idle"


def test_empty_goal_rejected(registry_file):
    c = TestClient(app)
    res = c.post("/api/selfedit/run", json={"goal": "   "}).json()
    assert res["ok"] is False and "goal" in res["error"]


def test_agent_crash_settles_job_as_error(registry_file, monkeypatch):
    _install_fake_agent(monkeypatch, crash=True)
    c = TestClient(app)
    c.post("/api/selfedit/run", json={"goal": "explode"})
    job = _wait_for_job(c, "error")
    assert "boom" in job["summary"]


def test_run_plan_path_read_and_seeded(registry_file, monkeypatch):
    """plan_path is read synchronously and its CONTENT reaches the agent."""
    seen = {}

    class PlanCapturingAgent(FakeAgent):
        def run(self, goal, plan=None):
            seen["plan"] = plan
            return {"ok": True, "summary": "done"}

    monkeypatch.setattr(
        srv, "_make_agent", lambda service, profile: PlanCapturingAgent(service, profile)
    )
    monkeypatch.setattr(
        srv.repo_logic, "repo_read_file",
        lambda path: {"ok": True, "path": path, "content": "# The Plan\ndo the thing"},
    )
    c = TestClient(app)
    res = c.post("/api/selfedit/run", json={
        "goal": "implement it", "plan_path": "docs/plans/X.md",
    }).json()
    assert res["ok"] and res["started"]
    _wait_for_job(c, "done")
    assert seen["plan"] == "# The Plan\ndo the thing"


def test_run_plan_path_read_failure_refuses_synchronously(registry_file, monkeypatch):
    _install_fake_agent(monkeypatch)
    monkeypatch.setattr(
        srv.repo_logic, "repo_read_file",
        lambda path: {"ok": False, "error": f"{path} does not exist"},
    )
    c = TestClient(app)
    res = c.post("/api/selfedit/run", json={
        "goal": "implement it", "plan_path": "docs/plans/NOPE.md",
    }).json()
    assert res["ok"] is False and "does not exist" in res["error"]
    assert c.get("/api/selfedit/run").json()["job"]["state"] == "idle"


def test_run_explicit_plan_beats_plan_path(registry_file, monkeypatch):
    """An explicit plan body wins; plan_path is not even read."""
    seen = {}

    class PlanCapturingAgent(FakeAgent):
        def run(self, goal, plan=None):
            seen["plan"] = plan
            return {"ok": True, "summary": "done"}

    def _explode(path):  # must never be called
        raise AssertionError("plan_path was read despite explicit plan")

    monkeypatch.setattr(
        srv, "_make_agent", lambda service, profile: PlanCapturingAgent(service, profile)
    )
    monkeypatch.setattr(srv.repo_logic, "repo_read_file", _explode)
    c = TestClient(app)
    res = c.post("/api/selfedit/run", json={
        "goal": "implement it", "plan": "inline plan", "plan_path": "docs/plans/X.md",
    }).json()
    assert res["ok"]
    _wait_for_job(c, "done")
    assert seen["plan"] == "inline plan"


def test_run_status_endpoint_shape(registry_file, monkeypatch):
    _install_fake_agent(monkeypatch)
    c = TestClient(app)
    c.post("/api/selfedit/run", json={"goal": "check shape"})
    _wait_for_job(c, "done")
    body = c.get("/api/selfedit/run").json()
    assert body["ok"] is True
    assert set(body["job"]) >= {"state", "goal", "profile", "summary",
                                "started_at", "finished_at"}
    assert "status" in body


# ---------------------------------------------------------------- staging (G2)


def test_stage_returns_staging_id(registry_file):
    c = TestClient(app)
    res = c.post("/api/selfedit/stage", json={"goal": "add a clock panel"}).json()
    assert res["ok"] is True
    assert res["staging_id"]
    assert res["expires_in_s"] == srv.SELFEDIT_STAGING_TTL_S


def test_stage_empty_goal_rejected(registry_file):
    c = TestClient(app)
    res = c.post("/api/selfedit/stage", json={"goal": "   "}).json()
    assert res["ok"] is False and "goal" in res["error"]


def test_run_with_staging_id_replays_staged_goal(registry_file, monkeypatch):
    """G2: the staged goal/profile — never anything re-derived on the
    confirm call — is what actually reaches the agent."""
    seen = {}

    class CapturingAgent(FakeAgent):
        def run(self, goal, plan=None):
            seen["goal"] = goal
            return {"ok": True, "summary": "done"}

    monkeypatch.setattr(
        srv, "_make_agent", lambda service, profile: CapturingAgent(service, profile)
    )
    c = TestClient(app)
    stage = c.post("/api/selfedit/stage", json={
        "goal": "add a clock panel", "profile": "claude-opus",
    }).json()
    sid = stage["staging_id"]

    res = c.post("/api/selfedit/run", json={"staging_id": sid}).json()
    assert res["ok"] and res["started"]
    assert res["profile"] == "claude-opus (fake-model)"
    _wait_for_job(c, "done")
    assert seen["goal"] == "add a clock panel"


def test_run_with_staging_id_consumes_it_once(registry_file, monkeypatch):
    """A staging record is single-use — a second confirm with the SAME id
    must fail honestly rather than silently starting a second run."""
    _install_fake_agent(monkeypatch)
    c = TestClient(app)
    stage = c.post("/api/selfedit/stage", json={"goal": "add a clock"}).json()
    sid = stage["staging_id"]
    first = c.post("/api/selfedit/run", json={"staging_id": sid}).json()
    assert first["ok"] and first["started"]
    _wait_for_job(c, "done")

    second = c.post("/api/selfedit/run", json={"staging_id": sid}).json()
    assert second["ok"] is False
    assert "no staged edit" in second["error"]
    assert "session expired" not in second["error"]  # G2: name the real state


def test_run_unknown_staging_id_names_real_state(registry_file):
    c = TestClient(app)
    res = c.post("/api/selfedit/run", json={"staging_id": "does-not-exist"}).json()
    assert res["ok"] is False
    assert "does-not-exist" in res["error"]
    assert "expired" in res["error"] or "already used" in res["error"]


def test_run_stale_staging_id_errors_honestly(registry_file, monkeypatch):
    """G2: TTL expiry names the real cause, never an invented narrative."""
    c = TestClient(app)
    stage = c.post("/api/selfedit/stage", json={"goal": "add a clock"}).json()
    sid = stage["staging_id"]
    with srv._staging_lock:
        srv._selfedit_stagings[sid]["created_at"] -= srv.SELFEDIT_STAGING_TTL_S + 1
    res = c.post("/api/selfedit/run", json={"staging_id": sid}).json()
    assert res["ok"] is False
    assert "expired" in res["error"] or "no staged edit" in res["error"]


def test_run_bare_form_without_staging_id_still_works(registry_file, monkeypatch):
    """G2: the deprecated stateless {goal, profile} form must keep working
    for one release — an older mcp_selfedit build must not break."""
    _install_fake_agent(monkeypatch)
    c = TestClient(app)
    res = c.post("/api/selfedit/run", json={"goal": "dark theme"}).json()
    assert res["ok"] and res["started"]
    _wait_for_job(c, "done")


def test_stage_does_not_start_a_run(registry_file):
    """Staging is a preview-time record only — GET /api/selfedit/run must
    still report idle until confirm actually replays it."""
    c = TestClient(app)
    c.post("/api/selfedit/stage", json={"goal": "add a clock panel"})
    assert c.get("/api/selfedit/run").json()["job"]["state"] == "idle"


# ------------------------------------------------- staging visibility (2026-08-25)


def test_run_status_reports_live_staging(registry_file):
    """2026-08-25 — GET /api/selfedit/run previously had no way to answer
    'is staging X still live'. A live staged record must now appear in
    the `stagings` list, without leaking its goal text."""
    c = TestClient(app)
    stage = c.post("/api/selfedit/stage", json={"goal": "add a clock panel"}).json()
    sid = stage["staging_id"]
    body = c.get("/api/selfedit/run").json()
    assert body["ok"] is True
    ids = [s["staging_id"] for s in body["stagings"]]
    assert sid in ids
    entry = next(s for s in body["stagings"] if s["staging_id"] == sid)
    assert "goal" not in entry
    assert entry["expires_in_s"] > 0


def test_run_status_omits_consumed_staging(registry_file, monkeypatch):
    """A staging_id already consumed by a confirm call must not still
    appear as live."""
    _install_fake_agent(monkeypatch)
    c = TestClient(app)
    stage = c.post("/api/selfedit/stage", json={"goal": "add a clock"}).json()
    sid = stage["staging_id"]
    c.post("/api/selfedit/run", json={"staging_id": sid})
    _wait_for_job(c, "done")
    body = c.get("/api/selfedit/run").json()
    assert sid not in [s["staging_id"] for s in body["stagings"]]


def test_run_status_omits_expired_staging(registry_file):
    c = TestClient(app)
    stage = c.post("/api/selfedit/stage", json={"goal": "add a clock"}).json()
    sid = stage["staging_id"]
    with srv._staging_lock:
        srv._selfedit_stagings[sid]["created_at"] -= srv.SELFEDIT_STAGING_TTL_S + 1
    body = c.get("/api/selfedit/run").json()
    assert sid not in [s["staging_id"] for s in body["stagings"]]
