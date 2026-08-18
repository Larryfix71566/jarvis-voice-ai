"""Unit tests for PlanWatcher (MORTIMER_CONFIRMATION_AND_CAPABILITY_PLAN.md
F4). Modeled on tests/unit/test_reminders_watcher.py's shape: an injected
async seam (`fetch_job` here, `registry.call` there) so no real network or
event loop polling is exercised."""

from __future__ import annotations

import pytest

from jarvis.bot.plan_watcher import PlanWatcher


class _Recorder:
    def __init__(self):
        self.spoken: list[str] = []
        self.displayed: list[dict] = []

    async def speak(self, text: str) -> None:
        self.spoken.append(text)

    async def push_display(self, payload: dict) -> None:
        self.displayed.append(payload)


def _watcher(rec: _Recorder, jobs: list[dict], connected: bool = True) -> PlanWatcher:
    calls = {"n": 0}

    async def fetch_job():
        i = min(calls["n"], len(jobs) - 1)
        calls["n"] += 1
        return jobs[i]

    return PlanWatcher(
        speak=rec.speak, push_display=rec.push_display,
        is_connected=lambda: connected, fetch_job=fetch_job,
    )


async def _tick_n(w: PlanWatcher, n: int) -> None:
    for _ in range(n):
        await w.tick_once()


# ------------------------------------------------------------- disconnected

@pytest.mark.asyncio
async def test_disconnected_skips_tick_entirely():
    rec = _Recorder()
    w = _watcher(rec, [{"ok": True, "job": {"state": "done", "started_at": 1, "plan": "x", "saved_path": "docs/plans/x.md"}}], connected=False)
    await w.tick_once()
    assert rec.spoken == []
    assert rec.displayed == []


# --------------------------------------------------------------- non-terminal

@pytest.mark.asyncio
async def test_running_state_produces_no_announcement():
    rec = _Recorder()
    w = _watcher(rec, [{"ok": True, "job": {"state": "running", "started_at": 1}}])
    await w.tick_once()
    assert rec.spoken == []


@pytest.mark.asyncio
async def test_idle_state_produces_no_announcement():
    rec = _Recorder()
    w = _watcher(rec, [{"ok": True, "job": {"state": "idle"}}])
    await w.tick_once()
    assert rec.spoken == []


# -------------------------------------------------------------------- done

@pytest.mark.asyncio
async def test_done_speaks_and_pushes_display():
    rec = _Recorder()
    job = {
        "state": "done", "started_at": 100, "plan": "# The Plan\n\nBody.",
        "goal": "add dark mode", "saved_path": "docs/plans/add-dark-mode.md",
    }
    w = _watcher(rec, [{"ok": True, "job": job}])
    await w.tick_once()
    assert len(rec.spoken) == 1
    assert "add-dark-mode.md" in rec.spoken[0]
    assert "on your display" in rec.spoken[0]
    assert len(rec.displayed) == 1
    assert rec.displayed[0]["title"] == "Plan — add dark mode"
    assert "The Plan" in rec.displayed[0]["body"]
    assert rec.displayed[0]["surface"] == "window"


@pytest.mark.asyncio
async def test_done_review_job_uses_review_wording():
    rec = _Recorder()
    job = {
        "state": "done", "started_at": 100, "plan": "# Review",
        "goal": "review the spec", "saved_path": "docs/reviews/review-the-spec.md",
        "review_path": "docs/plans/spec.md",
    }
    w = _watcher(rec, [{"ok": True, "job": job}])
    await w.tick_once()
    assert "review" in rec.spoken[0].lower()
    assert rec.displayed[0]["title"].startswith("Review —")


@pytest.mark.asyncio
async def test_done_save_failure_speaks_but_does_not_push_display():
    rec = _Recorder()
    job = {
        "state": "done", "started_at": 100, "plan": "content",
        "goal": "x", "saved_path": None, "save_error": "disk full",
    }
    w = _watcher(rec, [{"ok": True, "job": job}])
    await w.tick_once()
    assert "disk full" in rec.spoken[0]
    assert rec.displayed == []


@pytest.mark.asyncio
async def test_done_announced_only_once_across_ticks():
    rec = _Recorder()
    job = {
        "state": "done", "started_at": 100, "plan": "content",
        "goal": "x", "saved_path": "docs/plans/x.md",
    }
    resp = {"ok": True, "job": job}
    w = _watcher(rec, [resp, resp, resp])
    await _tick_n(w, 3)
    assert len(rec.spoken) == 1
    assert len(rec.displayed) == 1


@pytest.mark.asyncio
async def test_new_job_started_at_announces_again():
    """A second plan run (new started_at) after a first one finished must
    be announced independently — the dedupe key is (started_at, state)."""
    rec = _Recorder()
    job1 = {"state": "done", "started_at": 1, "plan": "a", "goal": "g1", "saved_path": "docs/plans/g1.md"}
    job2 = {"state": "done", "started_at": 2, "plan": "b", "goal": "g2", "saved_path": "docs/plans/g2.md"}
    w = _watcher(rec, [{"ok": True, "job": job1}, {"ok": True, "job": job2}])
    await _tick_n(w, 2)
    assert len(rec.spoken) == 2


# ---------------------------------------------------------- awaiting_choice

@pytest.mark.asyncio
async def test_awaiting_choice_speaks_candidate_names():
    rec = _Recorder()
    job = {
        "state": "awaiting_choice", "started_at": 5,
        "candidates": [{"label": "Proposal A"}, {"label": "Proposal B"}],
    }
    w = _watcher(rec, [{"ok": True, "job": job}])
    await w.tick_once()
    assert len(rec.spoken) == 1
    assert "Proposal A" in rec.spoken[0] and "Proposal B" in rec.spoken[0]
    assert "2 candidate" in rec.spoken[0]
    assert rec.displayed == []  # no single document to push yet


# ------------------------------------------------------------------- error

@pytest.mark.asyncio
async def test_error_speaks_once():
    rec = _Recorder()
    job = {"state": "error", "started_at": 9, "error": "planner crashed"}
    w = _watcher(rec, [{"ok": True, "job": job}, {"ok": True, "job": job}])
    await _tick_n(w, 2)
    assert len(rec.spoken) == 1
    assert "planner crashed" in rec.spoken[0]


# --------------------------------------------------------- transport failure

@pytest.mark.asyncio
async def test_fetch_job_exception_is_swallowed():
    rec = _Recorder()

    async def _boom():
        raise ConnectionError("sidecar offline")

    w = PlanWatcher(speak=rec.speak, push_display=rec.push_display,
                     is_connected=lambda: True, fetch_job=_boom)
    await w.tick_once()  # must not raise
    assert rec.spoken == []


@pytest.mark.asyncio
async def test_not_ok_response_is_ignored():
    rec = _Recorder()
    w = _watcher(rec, [{"ok": False, "error": "boom"}])
    await w.tick_once()
    assert rec.spoken == []


# --------------------------------------------------------------- start/stop

@pytest.mark.asyncio
async def test_start_and_stop_cancel_cleanly():
    rec = _Recorder()
    w = _watcher(rec, [{"ok": True, "job": {"state": "idle"}}], connected=True)
    w.start()
    await w.stop()  # must not raise, must not leak a task
    assert w._task is None
