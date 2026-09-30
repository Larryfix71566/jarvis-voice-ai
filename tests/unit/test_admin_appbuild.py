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
import uuid

import pytest
import yaml
from fastapi.testclient import TestClient as FastAPITestClient

import jarvis.admin.server as srv
from jarvis.admin.server import app


class TestClient(FastAPITestClient):
    """Supply the current registry-injected app-build action identity."""

    def post(self, url, *args, **kwargs):
        body = kwargs.get("json")
        if (
            url == "/api/appbuild/start"
            and isinstance(body, dict)
            and (body.get("goal") or "").strip()
            and not (body.get("run_id") or "").strip()
        ):
            kwargs["json"] = {**body, "run_id": uuid.uuid4().hex}
        return super().post(url, *args, **kwargs)

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
            state="idle", app=None, goal=None, profile=None, summary=None, cancel_requested=False,
            started_at=None, finished_at=None,
            run_id=None, submit_action_id=None,
        )
        srv._appbuild_workspace = None
        srv._appbuild_agent_instance = None
    with srv._run_lock:
        srv._run_job.update(
            state="idle", goal=None, profile=None, summary=None,
            started_at=None, finished_at=None,
        )
    yield


@pytest.fixture
def registry_file(tmp_path, monkeypatch, fresh_db):
    p = tmp_path / "upgrade_models.yaml"
    p.write_text(yaml.safe_dump(REGISTRY))
    monkeypatch.setenv("JARVIS_UPGRADE_MODELS", str(p))
    monkeypatch.delenv("MOONSHOT_API_KEY", raising=False)
    monkeypatch.delenv("JARVIS_APPBUILD_PROFILE", raising=False)
    return p


class FakeWorkspace:
    """AppWorkspace stand-in: no git, no network."""

    @classmethod
    def recover(cls): return None

    def __init__(self, app_name):
        self.app_name = app_name
        self.session_id = uuid.uuid4().hex
        self.branch = None
        self.goal = None
        self.proposals: list[dict] = []
        self.validated_ok = False
        self.publication = None
        self.phase = "open"
        self.submit_count = 0
        self.submit_error = None

    def status(self):
        return {
            "id": self.session_id,
            "active": self.branch is not None, "app": self.app_name,
            "branch": self.branch, "goal": self.goal,
            "proposals": self.proposals, "validated_ok": self.validated_ok,
            "publication": self.publication,
            "phase": self.phase,
        }

    def submit(self):
        self.submit_count += 1
        if self.submit_error:
            self.phase = "publication_pending"
            raise self.submit_error
        self.publication = {"url": "https://example.invalid/pr/1"}
        self.phase = "published"
        return {"ok": True, "pr_url": self.publication["url"]}

    def cancel(self):
        self.branch = None
        return {"ok": True, "cancelled": True}

    def revert(self):
        self.branch = None
        return {"ok": True}


class FakeAgent:
    crash = False
    gate: threading.Event | None = None
    run_count = 0

    def __init__(self, workspace, profile=None):
        self.workspace = workspace
        self.profile = profile
        self.cancelled = False

    def request_cancel(self):
        self.cancelled = True
        self.workspace.cancel()
        if self.gate is not None:
            self.gate.set()

    def model_label(self):
        return f"{self.profile or 'kimi-k2'} (fake-model)"

    def run(self, goal, plan=None):
        FakeAgent.run_count += 1
        if self.cancelled:
            return {"ok": False, "cancelled": True, "summary": "Cancelled before starting"}
        self.workspace.branch = "mortimer/app-build/fake"
        self.workspace.goal = goal
        self.workspace.proposals = [{"path": "src/app.js", "rationale": "test proposal"}]
        self.workspace.validated_ok = True
        self.workspace.phase = "validated"
        if FakeAgent.gate is not None:
            FakeAgent.gate.wait(timeout=5)
        if self.cancelled:
            return {"ok": False, "cancelled": True, "summary": "Cancelled"}
        if FakeAgent.crash:
            raise RuntimeError("boom")
        return {"ok": True, "summary": f"built {goal!r}"}


def _install_fake_agent(monkeypatch, crash=False, gate=None):
    FakeAgent.crash = crash
    FakeAgent.gate = gate
    FakeAgent.run_count = 0
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
        blocked = c.post("/api/appbuild/submit").json()
        assert blocked["ok"] is False and "in progress" in blocked["error"]
    finally:
        gate.set()
    _wait_for_job(c, "done")


def test_appbuild_does_not_block_selfedit_and_vice_versa(
    registry_file, fresh_db, monkeypatch,
):
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
        selfedit_res = c.post("/api/selfedit/run", json={
            "goal": "unrelated", "run_id": "selfedit-while-appbuild-running",
        }).json()
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


def test_appbuild_start_requires_stable_action_id(registry_file, fresh_db):
    c = FastAPITestClient(app)
    res = c.post("/api/appbuild/start", json={
        "app": "demo-app", "goal": "build it",
    }).json()
    assert res["ok"] is False
    assert "stable run_id is required" in res["error"]
    assert srv._appbuild_job["state"] == "idle"


def test_appbuild_start_rejects_oversized_action_id(registry_file, fresh_db):
    c = FastAPITestClient(app)
    res = c.post("/api/appbuild/start", json={
        "app": "demo-app", "goal": "build it", "run_id": "x" * 257,
    }).json()
    assert res["ok"] is False
    assert "identity is invalid" in res["error"]
    assert srv._appbuild_job["state"] == "idle"


def test_empty_goal_rejected(registry_file):
    c = TestClient(app)
    res = c.post("/api/appbuild/start", json={"app": "demo-app", "goal": "  "}).json()
    assert res["ok"] is False and "goal" in res["error"]


def test_agent_crash_settles_job_as_error_without_logging_user_content(
    registry_file, monkeypatch, caplog,
):
    _install_fake_agent(monkeypatch, crash=True)
    c = TestClient(app)
    c.post("/api/appbuild/start", json={"app": "demo-app", "goal": "explode"})
    job = _wait_for_job(c, "error")
    assert job["summary"] == "App build failed (RuntimeError)."
    assert "appbuild_run_failed error_type=RuntimeError" in caplog.text
    assert "goal='explode'" not in caplog.text
    assert "app='demo-app'" not in caplog.text
    assert "boom" not in caplog.text


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
    workspace = srv._appbuild_workspace
    assert workspace.submit_count == 1
    duplicate = c.post("/api/appbuild/submit").json()
    assert duplicate["ok"] and duplicate["duplicate"]
    assert duplicate["state"] == "completed"
    assert duplicate["pr_url"] == "https://example.invalid/pr/1"
    assert workspace.submit_count == 1
    monkeypatch.setattr(
        srv, "get_execution_action",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("db down")),
    )
    recovered = c.post("/api/appbuild/submit").json()
    assert recovered["ok"] and recovered["state"] == "completed"
    assert recovered["pr_url"] == "https://example.invalid/pr/1"
    assert workspace.submit_count == 1
    by_submission = c.get(
        "/api/appbuild/job", params={"submit_action_id": workspace.session_id},
    ).json()
    assert by_submission["job"]["state"] == "completed"
    assert by_submission["job"]["pr_url"] == "https://example.invalid/pr/1"


def test_submit_fails_closed_when_claim_store_unavailable(registry_file, monkeypatch):
    _install_fake_agent(monkeypatch)
    client = TestClient(app)
    client.post("/api/appbuild/start", json={"app": "demo-app", "goal": "ship it"})
    _wait_for_job(client, "done")
    monkeypatch.setattr(
        srv, "claim_execution_action",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("db down")),
    )
    result = client.post("/api/appbuild/submit").json()
    assert not result["ok"]
    assert "no pull request was submitted" in result["error"]
    assert srv._appbuild_workspace.submit_count == 0


def test_submit_unknown_outcome_cannot_be_replayed(registry_file, monkeypatch):
    _install_fake_agent(monkeypatch)
    client = TestClient(app)
    client.post("/api/appbuild/start", json={"app": "demo-app", "goal": "ship it"})
    _wait_for_job(client, "done")
    workspace = srv._appbuild_workspace
    workspace.submit_error = RuntimeError("provider response lost")
    first = client.post("/api/appbuild/submit").json()
    assert first["ok"] is False
    assert workspace.submit_count == 1
    retry = client.post("/api/appbuild/submit").json()
    assert retry["ok"] and retry["duplicate"]
    assert retry["state"] == "unknown"
    assert retry["reconciliation_required"] is True
    status = client.get(
        "/api/appbuild/job", params={"submit_action_id": workspace.session_id},
    ).json()
    assert status["job"]["state"] == "unknown"
    assert status["job"]["reconciliation_required"] is True
    assert workspace.submit_count == 1


def test_submit_requires_validation_before_claim_or_dispatch(registry_file, monkeypatch):
    _install_fake_agent(monkeypatch)
    client = TestClient(app)
    client.post("/api/appbuild/start", json={"app": "demo-app", "goal": "ship it"})
    _wait_for_job(client, "done")
    workspace = srv._appbuild_workspace
    workspace.validated_ok = False
    result = client.post("/api/appbuild/submit").json()
    assert not result["ok"]
    assert "validation must pass" in result["error"]
    assert workspace.submit_count == 0


def test_pending_publication_without_claim_is_not_redispatched(registry_file, monkeypatch):
    _install_fake_agent(monkeypatch)
    workspace = FakeWorkspace("demo-app")
    workspace.branch = "mortimer/app-build/fake"
    workspace.goal = "ship it"
    workspace.proposals = [{"path": "src/app.js", "rationale": "tested"}]
    workspace.validated_ok = True
    workspace.phase = "publication_pending"
    srv._appbuild_workspace = workspace
    client = TestClient(app)
    result = client.post("/api/appbuild/submit").json()
    assert result["ok"] and result["state"] == "unknown"
    assert result["reconciliation_required"] is True
    assert workspace.submit_count == 0


def test_cancel_after_done_delegates_to_workspace(registry_file, monkeypatch):
    _install_fake_agent(monkeypatch)
    c = TestClient(app)
    c.post("/api/appbuild/start", json={"app": "demo-app", "goal": "abandon it"})
    _wait_for_job(c, "done")
    res = c.post("/api/appbuild/cancel").json()
    assert res["ok"] is True


def test_cancel_stops_an_active_build(registry_file, monkeypatch):
    gate = threading.Event()
    _install_fake_agent(monkeypatch, gate=gate)
    c = TestClient(app)
    c.post("/api/appbuild/start", json={"app": "demo-app", "goal": "cancel me"})
    try:
        response = c.post("/api/appbuild/cancel").json()
        assert response["ok"] and response["cancel_requested"]
        _wait_for_job(c, "cancelled")
        assert not c.get("/api/appbuild/job").json()["status"]["active"]
    finally:
        gate.set()


def test_cancel_before_worker_starts_does_not_open_session(registry_file, monkeypatch):
    _install_fake_agent(monkeypatch)
    # Exercise the scheduling window directly, before the worker owns an agent.
    with srv._appbuild_lock:
        srv._appbuild_job.update(state="running", app="demo-app", cancel_requested=False)
    c = TestClient(app)
    assert c.post("/api/appbuild/cancel").json()["cancel_requested"]
    srv._run_appbuild_agent("demo-app", "cancel before start", None)
    result = c.get("/api/appbuild/job").json()
    assert result["job"]["state"] == "cancelled"
    assert not result["status"]["active"]


def test_appbuild_run_id_prevents_replay_after_live_slot_is_replaced(
    registry_file, fresh_db, monkeypatch,
):
    _install_fake_agent(monkeypatch)
    client = TestClient(app)
    identity = "subagent-run-appbuild-once"
    first = client.post("/api/appbuild/start", json={
        "app": "demo-app", "goal": "add a button", "run_id": identity,
    }).json()
    assert first["ok"] and first["started"]
    _wait_for_job(client, "done")
    assert FakeAgent.run_count == 1

    with srv._appbuild_lock:
        srv._appbuild_job.update(state="idle", run_id="a-later-run", app=None, goal=None)
    replay = client.post("/api/appbuild/start", json={
        "app": "demo-app", "goal": "add a button", "run_id": identity,
    }).json()
    assert replay["ok"] and replay["duplicate"] and not replay["started"]
    assert replay["state"] == "completed"
    assert FakeAgent.run_count == 1

    status = client.get("/api/appbuild/job", params={"run_id": identity}).json()
    assert status["ok"]
    assert status["job"]["state"] == "completed"
    assert status["job"]["result_available"] is False


@pytest.mark.parametrize("crash,terminal,receipt_status", [
    (False, "done", "completed"),
    (True, "error", "failed"),
])
def test_appbuild_settles_claim_before_terminal_job(
    registry_file, fresh_db, monkeypatch, crash, terminal, receipt_status,
):
    """A completed app-build job must already have a durable outcome."""
    _install_fake_agent(monkeypatch, crash=crash)
    entered = threading.Event()
    release = threading.Event()
    original_update = srv._update_appbuild_start_claim

    def pause_terminal_update(run_id, status):
        if status in {"completed", "failed"}:
            entered.set()
            assert release.wait(5)
        return original_update(run_id, status)

    monkeypatch.setattr(srv, "_update_appbuild_start_claim", pause_terminal_update)
    c = TestClient(app)
    identity = f"appbuild-settlement-{terminal}"
    try:
        started = c.post("/api/appbuild/start", json={
            "app": "demo-app", "goal": "add a button", "run_id": identity,
        }).json()
        assert started["ok"] and started["started"]
        assert entered.wait(2)
        # Inspect the in-memory slot while the worker holds its lock; using
        # the status route here would block until the claim write resumes.
        assert srv._appbuild_job["state"] == "running"
        receipt = srv.get_execution_action(srv._APPBUILD_START_ACTION_SCOPE, identity)
        assert receipt["status"] != receipt_status
    finally:
        release.set()
    _wait_for_job(c, terminal)
    receipt = srv.get_execution_action(srv._APPBUILD_START_ACTION_SCOPE, identity)
    assert receipt["status"] == receipt_status


def test_appbuild_run_id_fails_closed_when_claim_store_is_unavailable(
    registry_file, fresh_db, monkeypatch,
):
    _install_fake_agent(monkeypatch)
    monkeypatch.setattr(srv, "claim_execution_action", lambda *a, **k: (_ for _ in ()).throw(RuntimeError()))
    client = TestClient(app)
    result = client.post("/api/appbuild/start", json={
        "app": "demo-app", "goal": "add a button", "run_id": "claim-fails",
    }).json()
    assert not result["ok"]
    assert "no build was started" in result["error"]
    assert FakeAgent.run_count == 0


def test_saved_workspace_is_recovered_after_process_state_is_lost(registry_file, monkeypatch):
    _install_fake_agent(monkeypatch)
    saved = FakeWorkspace('saved-app')
    saved.branch = 'mortimer/app-build/saved'
    saved.goal = 'Resume the application'
    original_status = saved.status
    saved.status = lambda: {**original_status(), 'id':'a'*32}
    monkeypatch.setattr(FakeWorkspace, 'recover', classmethod(lambda cls: saved))
    client = TestClient(app)
    result = client.get('/api/appbuild/job').json()
    assert result['status']['active']
    assert result['job']['state'] == 'recovered'
    assert result['job']['app'] == 'saved-app'
    assert client.post('/api/appbuild/cancel').json()['ok']
    assert not saved.branch


def test_app_submission_returns_while_vm_and_github_work_are_pending(registry_file, monkeypatch):
    _install_fake_agent(monkeypatch)
    saved = FakeWorkspace('saved-app'); saved.branch = 'mortimer/app-build/saved'
    saved.proposals = [{'path': 'src/app.js', 'rationale': 'verified change'}]
    saved.validated_ok = True
    srv._appbuild_workspace = saved
    entered, release = threading.Event(), threading.Event()
    def slow_submit():
        entered.set()
        assert release.wait(5)
        return {'ok':True, 'pr_url':'https://example.invalid/pr/1'}
    saved.submit = slow_submit
    client = TestClient(app)
    started = time.monotonic()
    response = client.post('/api/appbuild/submit').json()
    assert time.monotonic()-started < 1
    assert response['started'] and response['state'] == 'submitting'
    assert entered.wait(1)
    try:
        assert not client.post('/api/appbuild/submit').json()['ok']
        assert client.get('/api/appbuild/job').json()['job']['state'] == 'submitting'
    finally:
        release.set()
    job = _wait_for_job(client, 'done')
    assert job['submitted'] and job['pr_url'].endswith('/1')
