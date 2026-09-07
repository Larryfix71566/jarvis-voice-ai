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
            started_at=None, finished_at=None, submitted=False, pr_url=None,
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

    def model_label(self):
        return f"{self.profile or 'kimi-k2'} (fake-model)"

    def __init__(self, service, profile=None):
        self.profile = profile
        self._cancel = threading.Event()

    def request_cancel(self):
        self._cancel.set()

    def run(self, goal, plan=None):
        if FakeAgent.gate is not None:
            FakeAgent.gate.wait(timeout=5)
        if FakeAgent.crash:
            raise RuntimeError("boom")
        if self._cancel.is_set():
            return {"ok": False, "cancelled": True,
                    "summary": "cancelled by the user before the next planner step"}
        # A "planned" fake run is a COMPLETED one: it reports the PR it
        # opened, the way a real UpgradeAgent.run() does after session_submit.
        return {"ok": True, "summary": f"planned {goal!r}",
                "submitted": True, "pr_url": "https://example.invalid/pr/1"}


def _install_fake_agent(monkeypatch, crash=False, gate=None):
    FakeAgent.crash = crash
    FakeAgent.gate = gate
    monkeypatch.setattr(srv, "_make_agent", lambda service, profile, run_id=None: FakeAgent(service, profile))


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
        for ep in ("validate", "submit"):
            blocked = c.post(f"/api/selfedit/{ep}").json()
            assert blocked["ok"] is False and "in progress" in blocked["error"]
    finally:
        gate.set()
    _wait_for_job(c, "done")


def test_cancel_stops_a_running_planner_and_settles_cancelled(registry_file, monkeypatch):
    """2026-08-22/23: a kimi-k3 planner sat 'still running' and nothing could
    stop it — revert refused while busy, and no cancel existed. Cancel is
    cooperative (takes effect at the loop's next step) and the job settles
    as `cancelled`, not `error`."""
    gate = threading.Event()
    _install_fake_agent(monkeypatch, gate=gate)
    c = TestClient(app)
    assert c.post("/api/selfedit/run", json={"goal": "long one"}).json()["started"]
    res = c.post("/api/selfedit/cancel").json()
    assert res["ok"] is True and res["cancel_requested"] is True
    gate.set()
    job = _wait_for_job(c, "cancelled")
    assert "cancelled" in job["summary"]


def test_revert_while_running_requests_cancel_instead_of_refusing(registry_file, monkeypatch):
    """The voice path reaches revert, not cancel — so revert-while-busy
    must mean 'stop and discard', never 'ask for status instead'."""
    gate = threading.Event()
    _install_fake_agent(monkeypatch, gate=gate)
    c = TestClient(app)
    assert c.post("/api/selfedit/run", json={"goal": "runaway"}).json()["started"]
    res = c.post("/api/selfedit/revert").json()
    assert res["ok"] is True and res["cancel_requested"] is True
    gate.set()
    _wait_for_job(c, "cancelled")


def test_cancel_when_idle_is_refused(registry_file):
    c = TestClient(app)
    res = c.post("/api/selfedit/cancel").json()
    assert res["ok"] is False and "no self-edit run is in progress" in res["error"]


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
        srv, "_make_agent", lambda service, profile, run_id=None: PlanCapturingAgent(service, profile)
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
        srv, "_make_agent", lambda service, profile, run_id=None: PlanCapturingAgent(service, profile)
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
        srv, "_make_agent", lambda service, profile, run_id=None: CapturingAgent(service, profile)
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


def test_staging_carries_run_id_to_agent(registry_file, monkeypatch):
    """MORTIMER_GRAPH_LAYER_PLAN.md GL9 (contract G2, step 11c): the staged
    run_id reaches _make_agent — the staged record is the source of truth,
    same discipline as the goal/profile it already replays."""
    seen = {}

    def _spy(service, profile, run_id=None):
        seen["run_id"] = run_id
        return FakeAgent(service, profile)

    monkeypatch.setattr(srv, "_make_agent", _spy)
    c = TestClient(app)
    stage = c.post("/api/selfedit/stage", json={
        "goal": "add a clock panel", "run_id": "r9",
    }).json()
    sid = stage["staging_id"]

    res = c.post("/api/selfedit/run", json={"staging_id": sid}).json()
    assert res["ok"] and res["started"]
    _wait_for_job(c, "done")
    assert seen["run_id"] == "r9"


def test_bare_run_empty_run_id_is_none(registry_file, monkeypatch):
    """GL9: the bare {goal, ...} confirm=true form normalises an empty
    run_id to None, never the empty string, reaching _make_agent."""
    seen = {}

    def _spy(service, profile, run_id=None):
        seen["run_id"] = run_id
        return FakeAgent(service, profile)

    monkeypatch.setattr(srv, "_make_agent", _spy)
    c = TestClient(app)
    res = c.post(
        "/api/selfedit/run", json={"goal": "add a clock", "run_id": ""},
    ).json()
    assert res["ok"] and res["started"]
    _wait_for_job(c, "done")
    assert seen["run_id"] is None


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


def test_run_resolves_a_mangled_staging_id_when_exactly_one_is_live(registry_file, monkeypatch):
    """2026-09-07: the id is relayed as spoken text and arrived as
    'stg-<id>' and '43'. With one live staging there is nothing to guess —
    the sidecar starts the preview the user actually approved."""
    seen = {}

    class CapturingAgent(FakeAgent):
        def run(self, goal, plan=None):
            seen["goal"] = goal
            return {"ok": True, "summary": "done"}

    monkeypatch.setattr(
        srv, "_make_agent", lambda service, profile, run_id=None: CapturingAgent(service, profile)
    )
    c = TestClient(app)
    sid = c.post("/api/selfedit/stage", json={"goal": "add a clock panel"}).json()["staging_id"]
    res = c.post("/api/selfedit/run", json={"staging_id": f"stg-{sid}"}).json()
    assert res["ok"] and res["started"], res
    _wait_for_job(c, "done")
    assert seen["goal"] == "add a clock panel"
    assert c.get("/api/selfedit/run").json()["stagings"] == []  # consumed


def test_run_with_no_id_and_no_goal_uses_the_single_live_staging(registry_file, monkeypatch):
    _install_fake_agent(monkeypatch)
    c = TestClient(app)
    c.post("/api/selfedit/stage", json={"goal": "add a clock panel"})
    res = c.post("/api/selfedit/run", json={}).json()
    assert res["ok"] and res["started"], res
    job = _wait_for_job(c, "done")
    assert job["goal"] == "add a clock panel"


def test_run_refuses_to_guess_between_two_live_stagings(registry_file, monkeypatch):
    _install_fake_agent(monkeypatch)
    c = TestClient(app)
    a = c.post("/api/selfedit/stage", json={"goal": "goal A"}).json()["staging_id"]
    b = c.post("/api/selfedit/stage", json={"goal": "goal B"}).json()["staging_id"]
    res = c.post("/api/selfedit/run", json={"staging_id": "43"}).json()
    assert res["ok"] is False
    assert a in res["error"] and b in res["error"]
    # Neither approved preview was consumed by the refusal.
    live = {s["staging_id"] for s in c.get("/api/selfedit/run").json()["stagings"]}
    assert live == {a, b}
    # An exact id still works with two live.
    res = c.post("/api/selfedit/run", json={"staging_id": b}).json()
    assert res["ok"] and res["started"]
    assert _wait_for_job(c, "done")["goal"] == "goal B"


def test_run_with_no_live_staging_still_names_the_real_state(registry_file):
    c = TestClient(app)
    res = c.post("/api/selfedit/run", json={}).json()
    assert res["ok"] is False
    assert "no staged edit" in res["error"]


def test_confirm_during_a_running_job_does_not_consume_the_staging(registry_file, monkeypatch):
    """The busy refusal must come before the staging pop: before this, a
    confirm that landed mid-run burned the preview it was refusing."""
    gate = threading.Event()
    _install_fake_agent(monkeypatch, gate=gate)
    c = TestClient(app)
    first = c.post("/api/selfedit/run", json={"goal": "long running"}).json()
    assert first["ok"] and first["started"]
    try:
        sid = c.post("/api/selfedit/stage", json={"goal": "the next one"}).json()["staging_id"]
        res = c.post("/api/selfedit/run", json={"staging_id": sid}).json()
        assert res["ok"] is False
        assert "already in progress" in res["error"]
        live = {s["staging_id"] for s in c.get("/api/selfedit/run").json()["stagings"]}
        assert sid in live
    finally:
        gate.set()
        _wait_for_job(c, "done")


def test_run_job_records_the_pull_request_the_agent_opened(registry_file, monkeypatch):
    _install_fake_agent(monkeypatch)
    c = TestClient(app)
    c.post("/api/selfedit/run", json={"goal": "add a clock"})
    job = _wait_for_job(c, "done")
    assert job["submitted"] is True
    assert job["pr_url"] == "https://example.invalid/pr/1"
    assert job["summary"] == "planned 'add a clock'"  # no prefix when a PR exists


def test_run_that_ends_without_a_pull_request_says_so_first(registry_file, monkeypatch):
    """Review F6 (2026-09-07): the run that ended in planner prose after two
    failed validations was reported as state=done. The user must hear
    that no PR exists before hearing the planner's report."""

    class ProseEndAgent(FakeAgent):
        def run(self, goal, plan=None):
            return {"ok": True, "summary": "I looked and the tests are unrelated.",
                    "submitted": False, "pr_url": None}

    monkeypatch.setattr(
        srv, "_make_agent", lambda service, profile, run_id=None: ProseEndAgent(service, profile)
    )
    c = TestClient(app)
    c.post("/api/selfedit/run", json={"goal": "add a clock"})
    job = _wait_for_job(c, "done")
    assert job["submitted"] is False and job["pr_url"] is None
    assert job["summary"].startswith("Ended without submitting a pull request.")
    assert job["summary"].endswith("I looked and the tests are unrelated.")


def test_a_leftover_session_is_reverted_before_a_different_goal(registry_file, monkeypatch, tmp_path):
    """UpgradeAgent.run() reuses an active session as-is; a run that ended
    without submitting therefore handed its branch and proposal to the
    NEXT goal. The sidecar drops the leftover first — but resumes it when
    the goal is the same one (validate/submit by voice)."""
    _install_fake_agent(monkeypatch)
    svc = _preflight_service(monkeypatch, tmp_path)
    svc.branch = "jarvis/self-edit/20260907-old"
    svc.goal = "old goal"
    reverted = []

    def fake_revert():
        reverted.append(svc.branch)
        svc.branch = None
        svc.goal = None
        return {"ok": True}

    monkeypatch.setattr(svc, "revert", fake_revert)
    c = TestClient(app)
    c.post("/api/selfedit/run", json={"goal": "old goal"})
    _wait_for_job(c, "done")
    assert reverted == []  # same goal → resumed, not dropped

    svc.branch = "jarvis/self-edit/20260907-old"
    svc.goal = "old goal"
    c.post("/api/selfedit/run", json={"goal": "a different goal"})
    _wait_for_job(c, "done")
    assert reverted == ["jarvis/self-edit/20260907-old"]


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


# ------------------------------------------------------------ tier preflight


def _preflight_service(monkeypatch, tmp_path):
    """A SelfEditService over a scratch allowlist with a core tier, so the
    stage endpoint's pre-flight has real tiers to classify against."""
    import json
    from jarvis.selfedit.service import SelfEditService
    al = tmp_path / "allow.json"
    al.write_text(json.dumps({
        "allow": ["web/src/**"], "core": ["jarvis/**"],
        "deny": ["jarvis/vault.py"],
    }))
    svc = SelfEditService(repo_root=tmp_path, allowlist_path=al, github_token=None)
    monkeypatch.setattr(srv, "_selfedit_service", svc)
    return svc


def test_stage_classifies_target_paths_not_the_prose(registry_file, monkeypatch, tmp_path):
    _preflight_service(monkeypatch, tmp_path)
    c = TestClient(app)
    # docs/README.md is unlisted in this fixture's allowlist (only web/src
    # is routine, and web/ is frozen), which is exactly the point: the
    # tier check must see the docs target, not the core file the prose
    # mentions.
    goal = "add a note about jarvis/bot/display.py to docs/README.md"
    refused = c.post("/api/selfedit/stage", json={"goal": goal}).json()
    assert refused["ok"] is False and "jarvis/bot/display.py" in refused["error"]
    staged = c.post("/api/selfedit/stage", json={
        "goal": goal, "target_paths": ["docs/README.md"],
    }).json()
    assert staged["ok"] is True, staged
    assert staged["tiers"]["core"] == []
    assert staged["core_change"] is False


def test_stage_refuses_a_tier0_goal_before_staging(registry_file, monkeypatch, tmp_path):
    _preflight_service(monkeypatch, tmp_path)
    c = TestClient(app)
    res = c.post("/api/selfedit/stage", json={"goal": "rotate keys in jarvis/vault.py"}).json()
    assert res["ok"] is False
    assert "jarvis/vault.py" in res["error"] and "human-only" in res["error"]
    assert c.get("/api/selfedit/run").json()["stagings"] == []


def test_stage_refuses_a_core_goal_without_a_plan(registry_file, monkeypatch, tmp_path):
    _preflight_service(monkeypatch, tmp_path)
    c = TestClient(app)
    res = c.post("/api/selfedit/stage",
                 json={"goal": "consolidate output in jarvis/bot/display.py"}).json()
    assert res["ok"] is False and "plan" in res["error"]
    assert res["tiers"]["core"] == ["jarvis/bot/display.py"]


def test_stage_accepts_a_core_goal_with_a_plan_and_flags_it(registry_file, monkeypatch, tmp_path):
    _preflight_service(monkeypatch, tmp_path)
    c = TestClient(app)
    res = c.post("/api/selfedit/stage", json={
        "goal": "consolidate output in jarvis/bot/display.py",
        "plan_path": "docs/plans/CONSOLIDATED_DISPLAY.md",
    }).json()
    assert res["ok"] is True and res["core_change"] is True
    assert res["tiers"]["core"] == ["jarvis/bot/display.py"]


def test_stage_routine_goal_unchanged(registry_file, monkeypatch, tmp_path):
    _preflight_service(monkeypatch, tmp_path)
    c = TestClient(app)
    res = c.post("/api/selfedit/stage", json={"goal": "tidy docs/README.md"}).json()  # GC4: web/ frozen
    assert res["ok"] is True and res["core_change"] is False
