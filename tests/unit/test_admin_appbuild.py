"""Unit tests for the admin sidecar's async app-build endpoints
(MORTIMER_MODEL_DISCIPLINE_AND_MAC_SHELL_PLAN.md D5). Mirrors
test_admin_selfedit.py's fixtures/patterns exactly — same fake-agent
seam, same async-job-plus-polling assertions — but for
/api/appbuild/{start,job,submit,cancel} and _appbuild_job/_appbuild_lock
instead of /api/selfedit/* and _run_job/_run_lock. What's specific to
app-build is tested here: the separate job slot (an app build never
blocks a self-edit run or vice versa), app-name validation, and that
GET /api/appbuild/job's `status` reflects the workspace this job's
thread constructed (not a persistent module-level one)."""

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
    ],
}


@pytest.fixture(autouse=True)
def reset_jobs():
    with srv._appbuild_lock:
        srv._appbuild_job.update(
            state="idle", app=None, goal=None, profile=None, summary=None,
            started_at=None, finished_at=None,
        )
        srv._appbuild_workspace = None
    with srv._run_lock:
        srv._run_job.update(
            state="idle", goal=None, profile=None, summary=None,
            started_at=None, finished_at=None,
        )
    yield


@pytest.fixture
def registry_file(tmp_path, monkeypatch):
    p = tmp_path / "upgrade_models.yaml"
    p.write_text(yaml.safe_dump(REGISTRY))
    monkeypatch.setenv("JARVIS_UPGRADE_MODELS", str(p))
    monkeypatch.delenv("MOONSHOT_API_KEY", raising=False)
    monkeypatch.delenv("JARVIS_APPBUILD_PROFILE", raising=False)
    return p


class FakeWorkspace:
    """AppWorkspace stand-in: no git, no network."""

    def __init__(self, app_name):
        self.app_name = app_name
        self.branch = None
        self.goal = None
        self.proposals: list[dict] = []

    def status(self):
        return {
            "active": self.branch is not None, "app": self.app_name,
            "branch": self.branch, "goal": self.goal,
            "proposals": self.proposals, "validated_ok": False,
        }

    def submit(self):
        return {"ok": True, "pr_url": "https://example.invalid/pr/1"}

    def revert(self):
        self.branch = None
        return {"ok": True}


class FakeAgent:
    crash = False
    gate: threading.Event | None = None

    def __init__(self, workspace, profile=None):
        self.workspace = workspace
        self.profile = profile

    def model_label(self):
        return f"{self.profile or 'kimi-k2'} (fake-model)"

    def run(self, goal, plan=None):
        self.workspace.branch = "mortimer/app-build/fake"
        self.workspace.goal = goal
        if FakeAgent.gate is not None:
            FakeAgent.gate.wait(timeout=5)
        if FakeAgent.crash:
            raise RuntimeError("boom")
        return {"ok": True, "summary": f"built {goal!r}"}


def _install_fake_agent(monkeypatch, crash=False, gate=None):
    FakeAgent.crash = crash
    FakeAgent.gate = gate
    monkeypatch.setattr(
        srv, "_make_appbuild_agent",
        lambda workspace, profile: FakeAgent(workspace, profile),
    )
    monkeypatch.setattr(srv, "AppWorkspace", FakeWorkspace)


def _wait_for_job(client, state, timeout=5.0):
    deadline = time.time() + timeout
    job = None
    while time.time() < deadline:
        job = client.get("/api/appbuild/job").json()["job"]
        if job["state"] == state:
            return job
        time.sleep(0.02)
    raise AssertionError(f"job never reached state {state!r}")


def test_start_is_async_and_completes(registry_file, monkeypatch):
    _install_fake_agent(monkeypatch)
    c = TestClient(app)
    res = c.post("/api/appbuild/start",
                 json={"app": "demo-app", "goal": "add a button"}).json()
    assert res["ok"] and res["started"]
    job = _wait_for_job(c, "done")
    assert job["summary"] == "built 'add a button'"
    assert job["app"] == "demo-app"


def test_second_build_refused_while_running(registry_file, monkeypatch):
    gate = threading.Event()
    _install_fake_agent(monkeypatch, gate=gate)
    c = TestClient(app)
    res = c.post("/api/appbuild/start",
                 json={"app": "demo-app", "goal": "one"}).json()
    assert res["started"] is True
    try:
        again = c.post("/api/appbuild/start",
                       json={"app": "demo-app", "goal": "two"}).json()
        assert again["ok"] is False and "already in progress" in again["error"]
        for ep in ("submit", "cancel"):
            blocked = c.post(f"/api/appbuild/{ep}").json()
            assert blocked["ok"] is False and "in progress" in blocked["error"]
    finally:
        gate.set()
    _wait_for_job(c, "done")


def test_appbuild_does_not_block_selfedit_and_vice_versa(registry_file, monkeypatch):
    """D5 — separate slots, separate locks."""
    gate = threading.Event()
    _install_fake_agent(monkeypatch, gate=gate)

    class FakeSelfEditAgent:
        def __init__(self, service, profile=None):
            pass
        def model_label(self):
            return "kimi-k2 (fake-model)"
        def run(self, goal, plan=None):
            return {"ok": True, "summary": "planned it"}

    monkeypatch.setattr(
        srv, "_make_agent", lambda service, profile, run_id=None: FakeSelfEditAgent(service, profile),
    )
    c = TestClient(app)
    try:
        appbuild_res = c.post("/api/appbuild/start",
                              json={"app": "demo-app", "goal": "busy"}).json()
        assert appbuild_res["started"] is True
        selfedit_res = c.post("/api/selfedit/run", json={"goal": "unrelated"}).json()
        assert selfedit_res["ok"] and selfedit_res["started"]
    finally:
        gate.set()
    _wait_for_job(c, "done")


def test_invalid_app_name_rejected(registry_file):
    c = TestClient(app)
    res = c.post("/api/appbuild/start",
                 json={"app": "Not Valid!", "goal": "do a thing"}).json()
    assert res["ok"] is False
    assert "invalid app name" in res["error"]


def test_empty_goal_rejected(registry_file):
    c = TestClient(app)
    res = c.post("/api/appbuild/start", json={"app": "demo-app", "goal": "  "}).json()
    assert res["ok"] is False and "goal" in res["error"]


def test_agent_crash_settles_job_as_error(registry_file, monkeypatch):
    _install_fake_agent(monkeypatch, crash=True)
    c = TestClient(app)
    c.post("/api/appbuild/start", json={"app": "demo-app", "goal": "explode"})
    job = _wait_for_job(c, "error")
    assert "boom" in job["summary"]


def test_job_status_shape_includes_workspace_status(registry_file, monkeypatch):
    _install_fake_agent(monkeypatch)
    c = TestClient(app)
    c.post("/api/appbuild/start", json={"app": "demo-app", "goal": "check shape"})
    _wait_for_job(c, "done")
    body = c.get("/api/appbuild/job").json()
    assert body["ok"] is True
    assert set(body["job"]) >= {"state", "app", "goal", "profile", "summary",
                                "started_at", "finished_at"}
    assert "status" in body
    assert body["status"]["app"] == "demo-app"


def test_no_job_yet_status_is_inactive(registry_file):
    c = TestClient(app)
    body = c.get("/api/appbuild/job").json()
    assert body["ok"] is True
    assert body["status"] == {"active": False}


def test_submit_with_no_active_session_refused(registry_file):
    c = TestClient(app)
    res = c.post("/api/appbuild/submit").json()
    assert res["ok"] is False
    assert "no active" in res["error"]


def test_cancel_with_no_active_session_refused(registry_file):
    c = TestClient(app)
    res = c.post("/api/appbuild/cancel").json()
    assert res["ok"] is False
    assert "no active" in res["error"]


def test_submit_after_done_delegates_to_workspace(registry_file, monkeypatch):
    _install_fake_agent(monkeypatch)
    c = TestClient(app)
    c.post("/api/appbuild/start", json={"app": "demo-app", "goal": "ship it"})
    _wait_for_job(c, "done")
    res = c.post("/api/appbuild/submit").json()
    assert res["ok"] is True
    assert res["pr_url"] == "https://example.invalid/pr/1"


def test_cancel_after_done_delegates_to_workspace(registry_file, monkeypatch):
    _install_fake_agent(monkeypatch)
    c = TestClient(app)
    c.post("/api/appbuild/start", json={"app": "demo-app", "goal": "abandon it"})
    _wait_for_job(c, "done")
    res = c.post("/api/appbuild/cancel").json()
    assert res["ok"] is True
