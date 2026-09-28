"""Unit tests for the admin sidecar's planning-pathway endpoints
(MORTIMER_PLANNING_PATHWAY_PLAN.md P7). Fake council/profile resolution
(no network); the module-level _selfedit_service singleton is never
touched by these tests. Same TestClient + polling pattern as
tests/unit/test_admin_council.py.

# implementer: MORTIMER_GRAPH_LAYER_PLAN.md GL9 (step 11c) added a run_id
# kwarg to _run_plan_council's call to council_mod.draft_candidates. This
# file's _fake_draft_candidates stand-ins predate that plan and were not
# named in its §4 file manifest, but without run_id=None accepted here
# every council-mode /api/plan/start call in this file raises TypeError
# (unexpected keyword argument) — the same failure mode the plan already
# anticipated and fixed for _make_agent's lambdas in test_admin_selfedit.py/
# test_admin_appbuild.py. Extending the same accept-and-ignore fix here
# keeps the fix's own contract (a test double for a function whose real
# signature gained an optional kwarg) rather than leaving the suite red.
"""

from __future__ import annotations

import threading
import time
import uuid

import pytest
from fastapi.testclient import TestClient as FastAPITestClient

import jarvis.admin.server as srv
from jarvis.admin.server import app
from jarvis.agents.upgrade_agent import UnknownModelProfileError
from jarvis.council.types import Proposal, RoundResult
from jarvis.db import get_conn, run_migrations


class TestClient(FastAPITestClient):
    """Model the run ID injected by the current registered plan_start tool."""

    def post(self, url, *args, **kwargs):
        body = kwargs.get("json")
        if (
            url == "/api/plan/start"
            and isinstance(body, dict)
            and (body.get("goal") or "").strip()
            and not (body.get("run_id") or "").strip()
        ):
            kwargs["json"] = {**body, "run_id": uuid.uuid4().hex}
        return super().post(url, *args, **kwargs)


@pytest.fixture(autouse=True)
def _db(tmp_path, monkeypatch):
    db_path = tmp_path / "admin_plan_test.db"
    monkeypatch.setenv("JARVIS_DB_PATH", str(db_path))
    conn = get_conn(db_path)
    run_migrations(conn)
    conn.close()
    return db_path


@pytest.fixture(autouse=True)
def _reset_plan_job():
    idle = dict(
        state="idle", mode=None, goal=None, profile=None, round_id=None,
        candidates=None, plan=None, author=None, error=None,
        started_at=None, finished_at=None, review_path=None, run_id=None,
    )
    with srv._plan_lock:
        srv._plan_job.update(idle)
    yield
    with srv._plan_lock:
        srv._plan_job.update(idle)


def _wait_for_job(c: TestClient, states=("done", "error", "awaiting_choice"),
                   timeout: float = 2.0) -> dict:
    deadline = time.time() + timeout
    job = {}
    while time.time() < deadline:
        job = c.get("/api/plan/job").json()["job"]
        if job["state"] in states:
            return job
        time.sleep(0.01)
    raise AssertionError(f"job never settled: {job}")


FAKE_PROFILE = {"name": "kimi-k2", "model": "kimi-k2-latest", "provider": "moonshot"}


# --------------------------------------------------------------- single mode

def test_single_mode_happy_path(monkeypatch):
    monkeypatch.setattr(srv, "_resolve_planning_profile", lambda explicit: FAKE_PROFILE)

    async def _fake_call_profile(profile, system_prompt, user_content, timeout_s, rung=None):
        assert system_prompt == srv.PLAN_AUTHOR_PROMPT
        return "# The Plan\n\nDo the thing.", None

    monkeypatch.setattr(srv.council_mod, "_call_profile", _fake_call_profile)
    c = TestClient(app)
    res = c.post("/api/plan/start", json={"goal": "write a spec", "mode": "single"}).json()
    assert res == {"ok": True, "started": True}

    job = _wait_for_job(c, states=("done", "error"))
    assert job["state"] == "done"
    assert job["mode"] == "single"
    assert job["author"] == "kimi-k2"
    assert job["plan"] == "# The Plan\n\nDo the thing."


def test_single_mode_unknown_profile_fails_fast_synchronously(monkeypatch):
    def _fake_resolve(explicit):
        raise UnknownModelProfileError("unknown profile 'bogus'")

    monkeypatch.setattr(srv, "_resolve_planning_profile", _fake_resolve)
    c = TestClient(app)
    res = c.post("/api/plan/start", json={
        "goal": "write a spec", "mode": "single", "profile": "bogus",
    }).json()
    assert res["ok"] is False
    assert "bogus" in res["error"]
    job = c.get("/api/plan/job").json()["job"]
    assert job["state"] == "idle"  # never started


def test_single_mode_transport_failure_settles_job_as_error(monkeypatch):
    monkeypatch.setattr(srv, "_resolve_planning_profile", lambda explicit: FAKE_PROFILE)

    async def _fake_call_profile(profile, system_prompt, user_content, timeout_s, rung=None):
        raise RuntimeError("simulated network failure")

    monkeypatch.setattr(srv.council_mod, "_call_profile", _fake_call_profile)
    c = TestClient(app)
    c.post("/api/plan/start", json={"goal": "write a spec", "mode": "single"})
    job = _wait_for_job(c, states=("done", "error"))
    assert job["state"] == "error"
    assert "planning call failed" in job["error"]


def test_same_execution_cannot_start_plan_twice_under_new_provider_call_id(monkeypatch):
    """A fresh provider call ID is not a fresh planning action: the hidden
    SubAgent run_id stays stable through retries of this delegated task."""
    starts = []

    def _fake_start(goal, profile, context, run_id=None):
        starts.append((goal, run_id))
        with srv._plan_lock:
            srv._plan_job.update(
                state="done", mode="single", goal=goal,
                profile=profile["name"], plan="# Plan", author=profile["name"],
                run_id=run_id, finished_at=time.time(),
            )
        srv._update_plan_start_claim(run_id, "completed")

    monkeypatch.setattr(srv, "_resolve_planning_profile", lambda explicit: FAKE_PROFILE)
    monkeypatch.setattr(srv, "_run_plan_single", _fake_start)
    c = TestClient(app)
    first = c.post("/api/plan/start", json={
        "goal": "write the plan", "mode": "single", "run_id": "stable-run-001",
    }).json()
    _wait_for_job(c, states=("done", "error"))
    duplicate = c.post("/api/plan/start", json={
        # Different arguments/provider call ID are not exposed to this API;
        # the owning run identity is the cross-round idempotency boundary.
        "goal": "write the plan again", "mode": "single", "run_id": "stable-run-001",
    }).json()

    assert first == {"ok": True, "started": True}
    assert duplicate["ok"] is True
    assert duplicate["started"] is False
    assert duplicate["duplicate"] is True
    assert duplicate["action_run_id"] == "stable-run-001"
    assert len(starts) == 1
    assert starts[0] == ("write the plan", "stable-run-001")
    status = c.get("/api/plan/job", params={"run_id": "stable-run-001"}).json()
    assert status["job"]["state"] == "done"
    assert status["job"]["plan"] == "# Plan"


def test_duplicate_plan_start_claim_survives_loss_of_live_job_slot(monkeypatch):
    monkeypatch.setattr(srv, "_resolve_planning_profile", lambda explicit: FAKE_PROFILE)

    def _fake_start(goal, profile, context, run_id=None):
        with srv._plan_lock:
            srv._plan_job.update(
                state="done", goal=goal, run_id=run_id,
                plan="# Complete", author=profile["name"],
            )
        srv._update_plan_start_claim(run_id, "completed")

    monkeypatch.setattr(srv, "_run_plan_single", _fake_start)
    c = TestClient(app)
    c.post("/api/plan/start", json={
        "goal": "first plan", "mode": "single", "run_id": "stable-run-002",
    })
    _wait_for_job(c, states=("done", "error"))
    # A later independent request replaces the singleton status slot.
    with srv._plan_lock:
        srv._plan_job.update(state="done", run_id="another-run")

    duplicate = c.post("/api/plan/start", json={
        "goal": "retry first plan", "mode": "single", "run_id": "stable-run-002",
    }).json()
    status = c.get("/api/plan/job", params={"run_id": "stable-run-002"}).json()
    assert duplicate["duplicate"] is True
    assert duplicate["state"] == "completed"
    assert status["job"] == {
        "state": "completed",
        "run_id": "stable-run-002",
        "result_available": False,
        "reconciliation_required": False,
    }


def test_unknown_plan_start_after_live_slot_loss_is_not_relaunched(monkeypatch):
    starts = []
    dispatched = threading.Event()
    monkeypatch.setattr(srv, "_resolve_planning_profile", lambda explicit: FAKE_PROFILE)

    def _fake_start(goal, profile, context, run_id=None):
        starts.append(run_id)
        dispatched.set()

    monkeypatch.setattr(srv, "_run_plan_single", _fake_start)
    c = TestClient(app)
    c.post("/api/plan/start", json={
        "goal": "possibly started", "mode": "single", "run_id": "stable-run-003",
    })
    assert dispatched.wait(timeout=2)
    # Simulate losing the one live status slot while the durable claim remains
    # running, as after a process restart or a later task replacing the slot.
    with srv._plan_lock:
        srv._plan_job.update(state="idle", run_id=None)

    status = c.get("/api/plan/job", params={"run_id": "stable-run-003"}).json()
    duplicate = c.post("/api/plan/start", json={
        "goal": "possibly started", "mode": "single", "run_id": "stable-run-003",
    }).json()
    assert status["job"]["state"] == "unknown"
    assert status["job"]["reconciliation_required"] is True
    assert duplicate["duplicate"] is True
    assert duplicate["state"] == "unknown"
    assert starts == ["stable-run-003"]


# -------------------------------------------------------------- council mode

def _fake_round(n=2, with_scores=True):
    proposals = [
        Proposal(label=f"Proposal {chr(65 + i)}", profile=f"profile-{i}", content=f"plan {i}")
        for i in range(n)
    ]
    scores = []
    if with_scores:
        from jarvis.council.types import Score
        scores = [
            Score(judge_profile="judge-1", proposal_label=p.label, value=7.0 + i)
            for i, p in enumerate(proposals)
        ]
    return RoundResult(
        round_id="round-plan-1", winner=None, winner_mean=None,
        select_reason="awaiting user choice among 2 candidate(s)",
        proposals=proposals, scores=scores, abstentions=0, tier=0,
    )


def test_council_mode_happy_path_reaches_awaiting_choice(monkeypatch):
    async def _fake_draft_candidates(goal, *, members=None, judge=True, context=None,
                                      run_id=None):
        return _fake_round()

    monkeypatch.setattr(srv.council_mod, "draft_candidates", _fake_draft_candidates)
    c = TestClient(app)
    res = c.post("/api/plan/start", json={"goal": "write a spec", "mode": "council"}).json()
    assert res == {"ok": True, "started": True}

    job = _wait_for_job(c)
    assert job["state"] == "awaiting_choice"
    assert job["round_id"] == "round-plan-1"
    assert len(job["candidates"]) == 2
    labels = {cand["label"] for cand in job["candidates"]}
    assert labels == {"Proposal A", "Proposal B"}
    a = next(cand for cand in job["candidates"] if cand["label"] == "Proposal A")
    assert a["advisory_mean"] == 7.0


def test_council_mode_none_result_settles_job_as_error(monkeypatch):
    async def _fake_draft_candidates(goal, *, members=None, judge=True, context=None,
                                      run_id=None):
        return None

    monkeypatch.setattr(srv.council_mod, "draft_candidates", _fake_draft_candidates)
    c = TestClient(app)
    c.post("/api/plan/start", json={"goal": "write a spec", "mode": "council"})
    job = _wait_for_job(c)
    assert job["state"] == "error"
    assert "unavailable" in job["error"]


def test_council_mode_members_narrowing_passed_through(monkeypatch):
    seen = {}

    async def _fake_draft_candidates(goal, *, members=None, judge=True, context=None,
                                      run_id=None):
        seen["members"] = members
        return _fake_round()

    monkeypatch.setattr(srv.council_mod, "draft_candidates", _fake_draft_candidates)
    c = TestClient(app)
    c.post("/api/plan/start", json={
        "goal": "write a spec", "mode": "council",
        "members": {"proposers": ["kimi-k2"]},
    })
    _wait_for_job(c)
    assert seen["members"] == {"proposers": ["kimi-k2"]}


def test_start_requires_goal():
    c = TestClient(app)
    res = c.post("/api/plan/start", json={"goal": "  ", "mode": "single"}).json()
    assert res["ok"] is False
    assert "goal" in res["error"]


def test_start_rejects_bad_mode():
    c = TestClient(app)
    res = c.post("/api/plan/start", json={"goal": "x", "mode": "parallel"}).json()
    assert res["ok"] is False
    assert "mode" in res["error"]


def test_start_without_stable_action_id_is_refused_before_dispatch():
    c = FastAPITestClient(app)
    res = c.post("/api/plan/start", json={
        "goal": "write a spec", "mode": "single",
    }).json()
    assert res["ok"] is False
    assert "stable run_id is required" in res["error"]
    assert srv._plan_job["state"] == "idle"


def test_start_rejects_oversized_action_id_before_dispatch():
    c = FastAPITestClient(app)
    res = c.post("/api/plan/start", json={
        "goal": "write a spec", "mode": "single", "run_id": "x" * 257,
    }).json()
    assert res["ok"] is False
    assert "run identity is invalid" in res["error"]
    assert srv._plan_job["state"] == "idle"


def test_second_start_while_running_is_refused(monkeypatch):
    async def _fake_draft_candidates(goal, *, members=None, judge=True, context=None,
                                      run_id=None):
        time.sleep(0.1)
        return _fake_round()

    monkeypatch.setattr(srv.council_mod, "draft_candidates", _fake_draft_candidates)
    c = TestClient(app)
    first = c.post("/api/plan/start", json={"goal": "x", "mode": "council"}).json()
    assert first == {"ok": True, "started": True}
    second = c.post("/api/plan/start", json={"goal": "y", "mode": "council"}).json()
    assert second["ok"] is False
    assert "already in progress" in second["error"]
    _wait_for_job(c)


# ------------------------------------------------------------------- choose

def test_choose_sets_plan_and_author_and_calls_record_user_choice(monkeypatch):
    with srv._plan_lock:
        srv._plan_job.update(
            state="awaiting_choice", mode="council", round_id="round-x",
            candidates=[
                {"label": "Proposal A", "profile": "p1", "content": "content A", "advisory_mean": 8.0},
                {"label": "Proposal B", "profile": "p2", "content": "content B", "advisory_mean": 6.0},
            ],
        )
    recorded = {}
    monkeypatch.setattr(
        srv.council_mod, "record_user_choice",
        lambda round_id, label: recorded.update(round_id=round_id, label=label),
    )
    c = TestClient(app)
    res = c.post("/api/plan/choose", json={"label": "Proposal B"}).json()
    assert res == {"ok": True}
    assert recorded == {"round_id": "round-x", "label": "Proposal B"}

    job = c.get("/api/plan/job").json()["job"]
    assert job["state"] == "done"
    assert job["plan"] == "content B"
    assert job["author"] == "p2"


def test_choose_wrong_state_refused():
    c = TestClient(app)
    res = c.post("/api/plan/choose", json={"label": "Proposal A"}).json()
    assert res["ok"] is False
    assert "awaiting a choice" in res["error"]


def test_choose_unknown_label_refused():
    with srv._plan_lock:
        srv._plan_job.update(
            state="awaiting_choice", round_id="round-x",
            candidates=[{"label": "Proposal A", "profile": "p1", "content": "c", "advisory_mean": None}],
        )
    c = TestClient(app)
    res = c.post("/api/plan/choose", json={"label": "Proposal Z"}).json()
    assert res["ok"] is False
    job = c.get("/api/plan/job").json()["job"]
    assert job["state"] == "awaiting_choice"  # unchanged


# -------------------------------------------------------------------- adopt

def test_adopt_requires_done_state():
    c = TestClient(app)
    res = c.post("/api/plan/adopt", json={}).json()
    assert res["ok"] is False
    assert "no finished plan" in res["error"]


def test_adopt_without_session_keeps_plan(monkeypatch):
    monkeypatch.setattr(srv, "authoring_enabled", lambda: True)
    monkeypatch.setattr(srv, "_selfedit_service", type("Missing", (), {"branch": None})())
    with srv._plan_lock:
        srv._plan_job.update(state="done", mode="single", goal="saved plan",
                             plan="# Keep this plan", author="unknown-profile")
    result = TestClient(app).post("/api/plan/adopt", json={}).json()
    assert result["ok"] is False and result["code"] == "sandbox_session_required"
    assert "action_id" not in result
    assert srv._plan_job["plan"] == "# Keep this plan"


def test_adopt_single_mode_appends_attribution_footer(tmp_path, monkeypatch):
    registry_path = tmp_path / "upgrade_models.yaml"
    registry_path.write_text(
        "default: kimi-k2\nprofiles:\n  - name: kimi-k2\n    model: kimi-k2-latest\n"
        "    provider: moonshot\n    base_url: https://api.moonshot.ai/v1\n"
        "    api_key_env: X\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("JARVIS_UPGRADE_MODELS", str(registry_path))
    with srv._plan_lock:
        srv._plan_job.update(
            state="done", mode="single", goal="write a spec",
            plan="# The Plan\n\nDo the thing.", author="kimi-k2",
        )
    captured = {}

    def _fake_write(path, content, rationale=""):
        captured.update(path=path, content=content, rationale=rationale)
        return {"ok": True, "pending": True, "action_id": 1, "path": path,
                "action": "create", "bytes": len(content)}

    monkeypatch.setattr(srv, "_save_document_to_sandbox", _fake_write)
    c = TestClient(app)
    res = c.post("/api/plan/adopt", json={}).json()
    assert res["ok"] is True
    assert res["pending"] is True
    assert captured["path"] == "docs/plans/write-a-spec.md"
    assert captured["content"].startswith("# The Plan\n\nDo the thing.")
    assert "*Drafted by kimi-k2 (kimi-k2-latest) —" in captured["content"]
    assert "Selected by Larry" not in captured["content"]  # single mode


def test_adopt_council_mode_footer_names_candidate_count_and_round(tmp_path, monkeypatch):
    registry_path = tmp_path / "upgrade_models.yaml"
    registry_path.write_text(
        "default: p1\nprofiles:\n  - name: p1\n    model: model-one\n"
        "    provider: x\n    base_url: https://x\n    api_key_env: X\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("JARVIS_UPGRADE_MODELS", str(registry_path))
    with srv._plan_lock:
        srv._plan_job.update(
            state="done", mode="council", goal="write a spec",
            round_id="round-42", plan="content A", author="p1",
            candidates=[
                {"label": "Proposal A", "profile": "p1", "content": "content A", "advisory_mean": 8.0},
                {"label": "Proposal B", "profile": "p2", "content": "content B", "advisory_mean": 6.0},
            ],
        )
    captured = {}
    monkeypatch.setattr(
        srv, "_save_document_to_sandbox",
        lambda path, content, rationale="": captured.update(content=content) or
        {"ok": True, "pending": True, "action_id": 1},
    )
    c = TestClient(app)
    res = c.post("/api/plan/adopt", json={"path": "docs/plans/custom.md"}).json()
    assert res["ok"] is True
    assert "Selected by Larry from 2 council candidates (round round-42)." in captured["content"]


def test_adopt_uses_custom_path(monkeypatch, tmp_path):
    registry_path = tmp_path / "upgrade_models.yaml"
    registry_path.write_text(
        "default: p1\nprofiles:\n  - name: p1\n    model: m\n"
        "    provider: x\n    base_url: https://x\n    api_key_env: X\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("JARVIS_UPGRADE_MODELS", str(registry_path))
    with srv._plan_lock:
        srv._plan_job.update(state="done", mode="single", goal="g", plan="c", author="p1")
    captured = {}
    monkeypatch.setattr(
        srv, "_save_document_to_sandbox",
        lambda path, content, rationale="": captured.update(path=path) or
        {"ok": True, "pending": True, "action_id": 1},
    )
    c = TestClient(app)
    c.post("/api/plan/adopt", json={"path": "docs/plans/my-custom.md"})
    assert captured["path"] == "docs/plans/my-custom.md"


# ------------------------------------------------------------------- cancel

def test_cancel_from_running_resets_to_idle():
    with srv._plan_lock:
        srv._plan_job.update(state="running", mode="single", goal="x")
    c = TestClient(app)
    res = c.post("/api/plan/cancel").json()
    assert res == {"ok": True}
    job = c.get("/api/plan/job").json()["job"]
    assert job["state"] == "idle"
    assert job["goal"] is None


def test_cancel_when_already_idle():
    c = TestClient(app)
    res = c.post("/api/plan/cancel").json()
    assert res == {"ok": True, "already_idle": True}
