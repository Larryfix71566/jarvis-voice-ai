"""Unit tests for ResearchWatcher
(MORTIMER_SITE_RESEARCH_AND_COMPARISON_PLAN.md R7). Modeled directly on
tests/unit/test_plan_watcher.py's shape — same injected async fetch_job
seam, no real network or event-loop polling exercised. Pins the R7 test
named in the plan: `test_watcher_announces_once_per_transition`."""

from __future__ import annotations

import pytest

from jarvis.bot.research_watcher import ResearchWatcher


class _Recorder:
    def __init__(self):
        self.spoken: list[str] = []
        self.displayed: list[dict] = []

    async def speak(self, text: str) -> None:
        self.spoken.append(text)

    async def push_display(self, payload: dict) -> None:
        self.displayed.append(payload)


def _watcher(rec: _Recorder, jobs: list[dict], connected: bool = True) -> ResearchWatcher:
    calls = {"n": 0}

    async def fetch_job():
        i = min(calls["n"], len(jobs) - 1)
        calls["n"] += 1
        return jobs[i]

    return ResearchWatcher(
        speak=rec.speak, push_display=rec.push_display,
        is_connected=lambda: connected, fetch_job=fetch_job,
    )


async def _tick_n(w: ResearchWatcher, n: int) -> None:
    for _ in range(n):
        await w.tick_once()


@pytest.mark.asyncio
async def test_disconnected_skips_tick_entirely():
    rec = _Recorder()
    w = _watcher(rec, [{"ok": True, "job": {"state": "done", "started_at": 1}}], connected=False)
    await w.tick_once()
    assert rec.spoken == []
    assert rec.displayed == []


@pytest.mark.asyncio
async def test_running_state_produces_no_announcement():
    rec = _Recorder()
    w = _watcher(rec, [{"ok": True, "job": {"state": "running", "started_at": 1}}])
    await w.tick_once()
    assert rec.spoken == []


@pytest.mark.asyncio
async def test_done_speaks_and_pushes_display():
    rec = _Recorder()
    job = {
        "state": "done", "started_at": 100,
        "comparison": "### a.com\n\ncontent\n\n### b.com\n\ncontent",
        "urls": ["https://a.com", "https://b.com"],
        "sites": [
            {"url": "https://a.com", "ok": True, "page_count": 5, "credits": 4},
            {"url": "https://b.com", "ok": True, "page_count": 6, "credits": 5},
        ],
        "credits_used": 9,
    }
    w = _watcher(rec, [{"ok": True, "job": job}])
    await w.tick_once()
    assert len(rec.spoken) == 1
    assert "9 credits" in rec.spoken[0]
    assert "on your display" in rec.spoken[0]
    assert len(rec.displayed) == 1
    assert rec.displayed[0]["surface"] == "window"
    assert "content" in rec.displayed[0]["body"]


@pytest.mark.asyncio
async def test_error_speaks_once():
    rec = _Recorder()
    job = {"state": "error", "started_at": 9, "error": "both sites failed to crawl"}
    w = _watcher(rec, [{"ok": True, "job": job}, {"ok": True, "job": job}])
    await _tick_n(w, 2)
    assert len(rec.spoken) == 1
    assert "both sites failed" in rec.spoken[0]


# ---- R7: exactly one announcement per (started_at, state) transition -----

@pytest.mark.asyncio
async def test_watcher_announces_once_per_transition():
    rec = _Recorder()
    job = {
        "state": "done", "started_at": 100,
        "comparison": "content", "urls": ["a", "b"],
        "sites": [], "credits_used": 3,
    }
    resp = {"ok": True, "job": job}
    w = _watcher(rec, [resp, resp, resp, resp])
    await _tick_n(w, 4)
    assert len(rec.spoken) == 1
    assert len(rec.displayed) == 1

    # A second, later run (new started_at) announces independently.
    job2 = {**job, "started_at": 200}
    w2 = _watcher(rec, [{"ok": True, "job": job2}])
    await w2.tick_once()
    assert len(rec.spoken) == 2


@pytest.mark.asyncio
async def test_fetch_job_exception_is_swallowed():
    rec = _Recorder()

    async def _boom():
        raise ConnectionError("sidecar offline")

    w = ResearchWatcher(speak=rec.speak, push_display=rec.push_display,
                         is_connected=lambda: True, fetch_job=_boom)
    await w.tick_once()  # must not raise
    assert rec.spoken == []


@pytest.mark.asyncio
async def test_start_and_stop_cancel_cleanly():
    rec = _Recorder()
    w = _watcher(rec, [{"ok": True, "job": {"state": "idle"}}], connected=True)
    w.start()
    await w.stop()
    assert w._task is None
