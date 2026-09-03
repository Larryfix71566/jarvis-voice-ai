"""Unit tests for the admin sidecar's council endpoints (MORTIMER_LLM_
COUNCIL_PLAN.md D10; MORTIMER_LLM_COUNCIL_V2_PLAN.md V5). Fake council (no
network); the module-level _selfedit_service singleton is patched directly
rather than started for real, so these tests never touch the actual local
git repo.

V5: council_convene and the E3 half of selfedit_reject no longer run the
council inline — they launch it on the shared _council_job background-
thread slot and return immediately. Tests poll GET /api/council/job until
the job settles rather than asserting on the POST response body directly."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

import jarvis.admin.server as srv
from jarvis.admin.server import app
from jarvis.council.types import Proposal, RoundResult
from jarvis.db import get_conn, run_migrations


@pytest.fixture(autouse=True)
def _db(tmp_path, monkeypatch):
    db_path = tmp_path / "admin_council_test.db"
    monkeypatch.setenv("JARVIS_DB_PATH", str(db_path))
    conn = get_conn(db_path)
    run_migrations(conn)
    conn.close()
    return db_path


@pytest.fixture(autouse=True)
def _reset_service(monkeypatch):
    # Never let a test accidentally touch the real local git repo.
    monkeypatch.setattr(srv._selfedit_service, "branch", None)
    monkeypatch.setattr(srv._selfedit_service, "goal", None)
    monkeypatch.setattr(srv._selfedit_service, "proposals", [])


@pytest.fixture(autouse=True)
def _reset_council_job():
    # The job slot is module-level shared state — start and end every test
    # with it idle so tests can't leak into one another.
    with srv._council_lock:
        srv._council_job.update(
            state="idle", trigger=None, goal=None, round_id=None, winner=None,
            winner_mean=None, select_reason=None, error=None, started_at=None,
            finished_at=None,
        )
    yield
    with srv._council_lock:
        srv._council_job.update(
            state="idle", trigger=None, goal=None, round_id=None, winner=None,
            winner_mean=None, select_reason=None, error=None, started_at=None,
            finished_at=None,
        )


async def _fake_convene_winner(**kwargs):
    winner = Proposal(label="Proposal A", profile="kimi-k2", content="do X then Y")
    return RoundResult(
        round_id="round-1", winner=winner, winner_mean=8.5,
        select_reason="highest mean score (8.5)", proposals=[winner],
        scores=[], abstentions=0, tier=1,
    )


async def _fake_convene_none(**kwargs):
    return None


async def _fake_convene_slow(**kwargs):
    time.sleep(0.05)
    return await _fake_convene_winner(**kwargs)


def _wait_for_job_done(c: TestClient, timeout: float = 2.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = c.get("/api/council/job").json()["job"]
        if job["state"] in ("done", "error"):
            return job
        time.sleep(0.01)
    raise AssertionError(f"job never settled: {job}")


# ------------------------------------------------------------- convene


def test_convene_planner_starts_job_and_polling_reaches_done(monkeypatch):
    monkeypatch.setattr(srv.council_mod, "convene", _fake_convene_winner)
    c = TestClient(app)
    res = c.post("/api/council/convene", json={
        "placement": "planner", "goal": "fix the thing",
    }).json()
    assert res == {"ok": True, "started": True}

    job = _wait_for_job_done(c)
    assert job["state"] == "done"
    assert job["trigger"] == "manual"
    assert job["round_id"] == "round-1"
    assert job["winner"]["profile"] == "kimi-k2"
    assert job["winner"]["content"] == "do X then Y"
    assert job["winner_mean"] == 8.5


def test_convene_requires_goal_when_no_active_session():
    c = TestClient(app)
    res = c.post("/api/council/convene", json={"placement": "planner"}).json()
    assert res["ok"] is False
    assert "goal" in res["error"]


def test_convene_falls_back_to_active_session_goal(monkeypatch):
    monkeypatch.setattr(srv._selfedit_service, "branch", "jarvis/self-edit/x")
    monkeypatch.setattr(srv._selfedit_service, "goal", "the active session's goal")
    monkeypatch.setattr(srv.council_mod, "convene", _fake_convene_winner)
    c = TestClient(app)
    res = c.post("/api/council/convene", json={"placement": "planner"}).json()
    assert res["ok"] is True
    job = _wait_for_job_done(c)
    assert job["state"] == "done"


def test_convene_reviewer_placement_not_implemented():
    c = TestClient(app)
    res = c.post("/api/council/convene", json={
        "placement": "reviewer", "goal": "review this",
    }).json()
    assert res["ok"] is False
    assert "not implemented" in res["error"]
    # Nothing was ever started.
    job = c.get("/api/council/job").json()["job"]
    assert job["state"] == "idle"


def test_convene_council_unavailable_settles_job_as_error(monkeypatch):
    monkeypatch.setattr(srv.council_mod, "convene", _fake_convene_none)
    c = TestClient(app)
    res = c.post("/api/council/convene", json={
        "placement": "planner", "goal": "fix it",
    }).json()
    assert res == {"ok": True, "started": True}

    job = _wait_for_job_done(c)
    assert job["state"] == "error"
    assert "unavailable" in job["error"]
    assert job["winner"] is None


def test_convene_passes_members_through_context(monkeypatch):
    seen = {}

    async def _capture(**kwargs):
        seen.update(kwargs)
        return await _fake_convene_winner(**kwargs)

    monkeypatch.setattr(srv.council_mod, "convene", _capture)
    c = TestClient(app)
    res = c.post("/api/council/convene", json={
        "placement": "planner", "goal": "fix it",
        "members": {"economy": ["kimi-k2"]},
    }).json()
    assert res["ok"] is True
    _wait_for_job_done(c)
    assert seen["context"]["members"] == {"economy": ["kimi-k2"]}


def test_second_convene_while_running_is_refused(monkeypatch):
    monkeypatch.setattr(srv.council_mod, "convene", _fake_convene_slow)
    c = TestClient(app)
    first = c.post("/api/council/convene", json={
        "placement": "planner", "goal": "fix the thing",
    }).json()
    assert first == {"ok": True, "started": True}

    second = c.post("/api/council/convene", json={
        "placement": "planner", "goal": "fix something else",
    }).json()
    assert second["ok"] is False
    assert "already in progress" in second["error"]
    assert second["job"]["state"] == "running"

    _wait_for_job_done(c)


# ------------------------------------------------------------ round/rounds


def test_round_detail_not_found():
    c = TestClient(app)
    res = c.get("/api/council/round/does-not-exist").json()
    assert res["ok"] is False
    assert res["error"] == "not found"


def _insert_round(db_path, round_id, workflow="selfedit", status="ok"):
    conn = get_conn(db_path)
    try:
        conn.execute(
            "INSERT INTO council_rounds (round_id, workflow, placement, "
            "trigger, tier, goal, proposer_count, judge_count, status, "
            "started_at) VALUES (?, ?, 'planner', 'manual', 1, 'g', 2, 1, ?, "
            "'2026-01-01T00:00:00+00:00')",
            (round_id, workflow, status),
        )
        conn.execute(
            "INSERT INTO council_scores (round_id, judge_profile, "
            "judge_tier, proposal_label, proposal_profile, score, "
            "justification, created_at) VALUES (?, 'kimi-k3', 'mid', "
            "'Proposal A', 'kimi-k2', 7.5, 'ok', '2026-01-01T00:00:00+00:00')",
            (round_id,),
        )
        conn.commit()
    finally:
        conn.close()


def test_round_detail_found(_db):
    _insert_round(_db, "round-abc")
    c = TestClient(app)
    res = c.get("/api/council/round/round-abc").json()
    assert res["ok"] is True
    assert res["round"]["round_id"] == "round-abc"
    assert len(res["scores"]) == 1


def test_rounds_list(_db):
    _insert_round(_db, "round-1")
    _insert_round(_db, "round-2", workflow="apps")
    c = TestClient(app)
    res = c.get("/api/council/rounds").json()
    assert res["ok"] is True
    assert {r["round_id"] for r in res["rounds"]} == {"round-1", "round-2"}

    filtered = c.get("/api/council/rounds", params={"workflow": "apps"}).json()
    assert {r["round_id"] for r in filtered["rounds"]} == {"round-2"}


# -------------------------------------------------------------------- roster
# MORTIMER_OPTIMIZATION_PLAN.md's Interface Task. build_roster's own rules
# are pinned in tests/unit/test_council_roster.py against the real round's
# shape; these cover only what the ENDPOINT adds — filters, the clamp, and
# that the assembled shape survives the round trip.


def test_roster_assembles_each_round(_db):
    _insert_round(_db, "round-r1")
    c = TestClient(app)
    res = c.get("/api/council/roster").json()
    assert res["ok"] is True
    roster = next(r for r in res["rounds"] if r["round_id"] == "round-r1")
    # _insert_round writes one live score: kimi-k3 scoring kimi-k2 7.5.
    assert [p["profile"] for p in roster["proposers"]] == ["kimi-k2"]
    assert roster["proposers"][0]["mean"] == 7.5
    assert [j["profile"] for j in roster["judges"]] == ["kimi-k3"]
    assert roster["degraded"] is False


def test_roster_takes_the_same_filters_as_the_rounds_list(_db):
    _insert_round(_db, "round-r1")
    _insert_round(_db, "round-r2", workflow="apps")
    c = TestClient(app)
    filtered = c.get("/api/council/roster", params={"workflow": "apps"}).json()
    assert {r["round_id"] for r in filtered["rounds"]} == {"round-r2"}

    by_status = c.get("/api/council/roster", params={"status": "ok"}).json()
    assert {r["round_id"] for r in by_status["rounds"]} == {"round-r1", "round-r2"}


def _insert_bare_rounds(db_path, count):
    """`count` scoreless rounds in one connection — enough to prove the
    ceiling clamp, which needs more rounds than the ceiling."""
    conn = get_conn(db_path)
    try:
        conn.executemany(
            "INSERT INTO council_rounds (round_id, workflow, placement, "
            "trigger, tier, goal, proposer_count, judge_count, status, "
            "started_at) VALUES (?, 'selfedit', 'planner', 'manual', 1, 'g', "
            "2, 1, 'ok', '2026-01-01T00:00:00+00:00')",
            [(f"bulk-{i:03d}",) for i in range(count)],
        )
        conn.commit()
    finally:
        conn.close()


def test_roster_limit_is_clamped_tighter_than_the_rounds_list(_db):
    """Each roster entry is much larger than a rounds row and the panel
    polls it, so this endpoint's ceiling is 50 where /rounds allows 200."""
    _insert_bare_rounds(_db, 60)
    c = TestClient(app)
    assert len(c.get("/api/council/roster", params={"limit": 2}).json()["rounds"]) == 2
    # Above the ceiling clamps DOWN to 50 — /api/council/rounds would
    # have returned all 60 for the same query.
    assert len(c.get("/api/council/roster", params={"limit": 9999}).json()["rounds"]) == 50
    assert len(c.get("/api/council/rounds", params={"limit": 9999}).json()["rounds"]) == 60
    # Non-positive clamps UP to 1 rather than erroring or returning none.
    assert len(c.get("/api/council/roster", params={"limit": 0}).json()["rounds"]) == 1


def test_roster_of_an_empty_database_is_an_empty_list(_db):
    c = TestClient(app)
    res = c.get("/api/council/roster").json()
    assert res == {"ok": True, "rounds": []}


# -------------------------------------------------------------------- reject


def test_reject_no_active_session():
    c = TestClient(app)
    res = c.post("/api/selfedit/reject").json()
    assert res["ok"] is False
    assert "no active" in res["error"]


def test_reject_revert_is_synchronous_council_lands_in_job(monkeypatch):
    monkeypatch.setattr(srv._selfedit_service, "branch", "jarvis/self-edit/x")
    monkeypatch.setattr(srv._selfedit_service, "goal", "rejected goal")
    monkeypatch.setattr(
        srv._selfedit_service, "revert",
        lambda: {"ok": True, "reverted_to": "pre-selfedit-fake"},
    )
    monkeypatch.setattr(srv.council_mod, "convene", _fake_convene_slow)
    c = TestClient(app)
    res = c.post("/api/selfedit/reject").json()
    # The revert result is present synchronously, in the same response,
    # even though the (slow) council fake is still mid-flight.
    assert res["ok"] is True
    assert res["reverted"]["reverted_to"] == "pre-selfedit-fake"
    assert res["council_started"] is True

    job = _wait_for_job_done(c)
    assert job["state"] == "done"
    assert job["trigger"] == "E3"
    assert job["round_id"] == "round-1"
    assert job["winner"]["profile"] == "kimi-k2"


def test_reject_council_unavailable_settles_job_error_but_still_reverts(monkeypatch):
    monkeypatch.setattr(srv._selfedit_service, "branch", "jarvis/self-edit/x")
    monkeypatch.setattr(srv._selfedit_service, "goal", "rejected goal")
    monkeypatch.setattr(
        srv._selfedit_service, "revert",
        lambda: {"ok": True, "reverted_to": "pre-selfedit-fake"},
    )
    monkeypatch.setattr(srv.council_mod, "convene", _fake_convene_none)
    c = TestClient(app)
    res = c.post("/api/selfedit/reject").json()
    assert res["ok"] is True
    assert res["reverted"]["ok"] is True
    assert res["council_started"] is True

    job = _wait_for_job_done(c)
    assert job["state"] == "error"
    assert job["winner"] is None


def test_reject_refused_while_run_in_progress(monkeypatch):
    with srv._run_lock:
        srv._run_job.update(state="running")
    try:
        c = TestClient(app)
        res = c.post("/api/selfedit/reject").json()
        assert res["ok"] is False
        assert "in progress" in res["error"]
    finally:
        with srv._run_lock:
            srv._run_job.update(state="idle")


def test_reject_council_already_running_reverts_without_starting_second_job(monkeypatch):
    monkeypatch.setattr(srv._selfedit_service, "branch", "jarvis/self-edit/x")
    monkeypatch.setattr(srv._selfedit_service, "goal", "rejected goal")
    monkeypatch.setattr(
        srv._selfedit_service, "revert",
        lambda: {"ok": True, "reverted_to": "pre-selfedit-fake"},
    )
    with srv._council_lock:
        srv._council_job.update(state="running", trigger="manual", goal="other goal")
    try:
        c = TestClient(app)
        res = c.post("/api/selfedit/reject").json()
        assert res["ok"] is True
        assert res["reverted"]["reverted_to"] == "pre-selfedit-fake"
        assert res["council_started"] is False
        # The pre-existing job wasn't clobbered.
        job = c.get("/api/council/job").json()["job"]
        assert job["trigger"] == "manual"
        assert job["goal"] == "other goal"
    finally:
        with srv._council_lock:
            srv._council_job.update(state="idle")
