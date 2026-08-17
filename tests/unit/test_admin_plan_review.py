"""Unit tests for the planning pathway's review mode
(MORTIMER_PLAN_REVIEW_AND_DOCS_PLAN.md R1/R3/R4): POST /api/plan/start
with `review_path` set, synchronous read-and-refuse, and the review
adopt-footer/default-path behavior. Same TestClient + polling pattern as
tests/unit/test_admin_plan.py.
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

import jarvis.admin.server as srv
from jarvis.admin.server import app
from jarvis.council import config as council_config
from jarvis.db import get_conn, run_migrations


@pytest.fixture(autouse=True)
def _db(tmp_path, monkeypatch):
    db_path = tmp_path / "admin_plan_review_test.db"
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
        started_at=None, finished_at=None, review_path=None,
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


# ------------------------------------------------------- single-mode start

def test_review_single_mode_reads_document_and_builds_context(monkeypatch):
    monkeypatch.setattr(srv, "_resolve_planning_profile", lambda explicit: FAKE_PROFILE)

    seen = {}

    def _fake_read_file(path):
        seen["path"] = path
        return {"ok": True, "path": path, "bytes": 10, "content": "PLAN BODY"}

    monkeypatch.setattr(srv.repo_logic, "repo_read_file", _fake_read_file)

    async def _fake_call_profile(profile, system_prompt, user_content, timeout_s):
        assert system_prompt == srv.PLAN_REVIEW_PROMPT
        assert "DOCUMENT UNDER REVIEW (docs/plans/x.md):" in user_content
        assert "PLAN BODY" in user_content
        return "# Review\n\nLooks fine.", None

    monkeypatch.setattr(srv.council_mod, "_call_profile", _fake_call_profile)
    c = TestClient(app)
    res = c.post("/api/plan/start", json={
        "goal": "review the plan", "mode": "single", "review_path": "docs/plans/x.md",
    }).json()
    assert res == {"ok": True, "started": True}
    assert seen["path"] == "docs/plans/x.md"

    job = _wait_for_job(c, states=("done", "error"))
    assert job["state"] == "done"
    assert job["review_path"] == "docs/plans/x.md"
    assert job["plan"] == "# Review\n\nLooks fine."


def test_review_single_mode_truncates_over_max_chars(monkeypatch):
    monkeypatch.setattr(srv, "_resolve_planning_profile", lambda explicit: FAKE_PROFILE)

    big_content = "x" * (council_config.PLAN_REVIEW_DOC_MAX_CHARS + 5000)
    monkeypatch.setattr(
        srv.repo_logic, "repo_read_file",
        lambda path: {"ok": True, "path": path, "bytes": len(big_content), "content": big_content},
    )

    seen = {}

    async def _fake_call_profile(profile, system_prompt, user_content, timeout_s):
        seen["user_content"] = user_content
        return "# Review", None

    monkeypatch.setattr(srv.council_mod, "_call_profile", _fake_call_profile)
    c = TestClient(app)
    c.post("/api/plan/start", json={
        "goal": "review", "mode": "single", "review_path": "docs/plans/big.md",
    })
    _wait_for_job(c, states=("done", "error"))
    assert "… (truncated for review — flag this truncation in your verdict)" in seen["user_content"]
    # truncated content is capped at PLAN_REVIEW_DOC_MAX_CHARS chars plus the suffix
    doc_start = seen["user_content"].index("DOCUMENT UNDER REVIEW")
    doc_section = seen["user_content"][doc_start:]
    assert len(doc_section) < len(big_content)


# --------------------------------------------------- synchronous read-refuse

def test_review_bad_path_refuses_synchronously_before_any_thread(monkeypatch):
    monkeypatch.setattr(srv, "_resolve_planning_profile", lambda explicit: FAKE_PROFILE)

    def _fake_read_file(path):
        return {"ok": False, "error": f"{path} does not exist"}

    monkeypatch.setattr(srv.repo_logic, "repo_read_file", _fake_read_file)

    called = {"n": 0}

    async def _fake_call_profile(*a, **k):
        called["n"] += 1
        return "should never run", None

    monkeypatch.setattr(srv.council_mod, "_call_profile", _fake_call_profile)
    c = TestClient(app)
    res = c.post("/api/plan/start", json={
        "goal": "review a ghost", "mode": "single", "review_path": "docs/plans/nope.md",
    }).json()
    assert res == {"ok": False, "error": "docs/plans/nope.md does not exist"}

    # No thread should ever have launched — the job stays idle.
    time.sleep(0.05)
    job = c.get("/api/plan/job").json()["job"]
    assert job["state"] == "idle"
    assert called["n"] == 0


def test_review_bad_path_council_mode_also_refuses_synchronously(monkeypatch):
    monkeypatch.setattr(
        srv.repo_logic, "repo_read_file",
        lambda path: {"ok": False, "error": "denied path"},
    )
    c = TestClient(app)
    res = c.post("/api/plan/start", json={
        "goal": "review a ghost", "mode": "council", "review_path": ".env",
    }).json()
    assert res == {"ok": False, "error": "denied path"}
    job = c.get("/api/plan/job").json()["job"]
    assert job["state"] == "idle"


# ------------------------------------------------------------- council mode

def test_review_council_mode_context_passed_to_draft_candidates(monkeypatch):
    monkeypatch.setattr(
        srv.repo_logic, "repo_read_file",
        lambda path: {"ok": True, "path": path, "bytes": 4, "content": "BODY"},
    )
    seen = {}

    async def _fake_draft_candidates(goal, *, members=None, judge=True, context=None):
        seen["context"] = context
        from jarvis.council.types import Proposal, RoundResult
        return RoundResult(
            round_id="round-review-1", winner=None, winner_mean=None,
            select_reason="awaiting user choice among 1 candidate(s)",
            proposals=[Proposal(label="Proposal A", profile="p1", content="a review")],
            scores=[], abstentions=0, tier=0,
        )

    monkeypatch.setattr(srv.council_mod, "draft_candidates", _fake_draft_candidates)
    c = TestClient(app)
    res = c.post("/api/plan/start", json={
        "goal": "review the spec", "mode": "council", "review_path": "docs/plans/x.md",
    }).json()
    assert res == {"ok": True, "started": True}

    job = _wait_for_job(c)
    assert job["state"] == "awaiting_choice"
    assert job["review_path"] == "docs/plans/x.md"
    assert seen["context"] == {"document": "BODY", "document_path": "docs/plans/x.md"}


# ------------------------------------------------------------------- adopt

def test_adopt_review_uses_review_footer_and_default_reviews_path(tmp_path, monkeypatch):
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
            state="done", mode="single", goal="review the geolocation plan",
            plan="# Review\n\nLooks fine.", author="kimi-k2",
            review_path="docs/plans/GEOLOCATION_DEVELOPMENT_PLAN.md",
        )
    captured = {}

    def _fake_write(path, content, rationale=""):
        captured.update(path=path, content=content, rationale=rationale)
        return {"ok": True, "pending": True, "action_id": 1, "path": path,
                "action": "create", "bytes": len(content)}

    monkeypatch.setattr(srv.repo_logic, "repo_write_file", _fake_write)
    c = TestClient(app)
    res = c.post("/api/plan/adopt", json={}).json()
    assert res["ok"] is True
    assert captured["path"] == "docs/reviews/review-the-geolocation-plan.md"
    assert captured["content"].startswith("# Review\n\nLooks fine.")
    assert (
        "*Review by kimi-k2 (kimi-k2-latest) —" in captured["content"]
    )
    assert (
        "Reviewed: docs/plans/GEOLOCATION_DEVELOPMENT_PLAN.md.*" in captured["content"]
    )
    assert "Drafted by" not in captured["content"]
    assert "Selected by Larry" not in captured["content"]  # single mode


def test_adopt_review_council_mode_appends_selected_by_clause(tmp_path, monkeypatch):
    registry_path = tmp_path / "upgrade_models.yaml"
    registry_path.write_text(
        "default: p1\nprofiles:\n  - name: p1\n    model: model-one\n"
        "    provider: x\n    base_url: https://x\n    api_key_env: X\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("JARVIS_UPGRADE_MODELS", str(registry_path))
    with srv._plan_lock:
        srv._plan_job.update(
            state="done", mode="council", goal="review the spec",
            round_id="round-99", plan="a review", author="p1",
            review_path="docs/plans/x.md",
            candidates=[
                {"label": "Proposal A", "profile": "p1", "content": "a review", "advisory_mean": 8.0},
                {"label": "Proposal B", "profile": "p2", "content": "b review", "advisory_mean": 6.0},
            ],
        )
    captured = {}
    monkeypatch.setattr(
        srv.repo_logic, "repo_write_file",
        lambda path, content, rationale="": captured.update(path=path, content=content) or
        {"ok": True, "pending": True, "action_id": 1},
    )
    c = TestClient(app)
    res = c.post("/api/plan/adopt", json={}).json()
    assert res["ok"] is True
    assert captured["path"] == "docs/reviews/review-the-spec.md"
    assert "Selected by Larry from 2 council candidates (round round-99)." in captured["content"]


def test_adopt_plan_mode_unaffected_by_review_changes(tmp_path, monkeypatch):
    """Regression: a plain (non-review) adopt still uses docs/plans/ and
    the 'Drafted by' footer, unchanged by R4."""
    registry_path = tmp_path / "upgrade_models.yaml"
    registry_path.write_text(
        "default: p1\nprofiles:\n  - name: p1\n    model: m\n"
        "    provider: x\n    base_url: https://x\n    api_key_env: X\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("JARVIS_UPGRADE_MODELS", str(registry_path))
    with srv._plan_lock:
        srv._plan_job.update(state="done", mode="single", goal="a fresh plan", plan="c", author="p1")
    captured = {}
    monkeypatch.setattr(
        srv.repo_logic, "repo_write_file",
        lambda path, content, rationale="": captured.update(path=path, content=content) or
        {"ok": True, "pending": True, "action_id": 1},
    )
    c = TestClient(app)
    c.post("/api/plan/adopt", json={})
    assert captured["path"] == "docs/plans/a-fresh-plan.md"
    assert "*Drafted by p1 (m) —" in captured["content"]
