"""W12 (MORTIMER_VOICE_WORKFLOWS_PLAN.md Phase 4, Larry 2026-09-25: option
B) — jarvis/bot/follow_up.py: one-shot timed checks and the voice control
of the progress-update interval."""

from __future__ import annotations

import asyncio

import pytest

from jarvis.bot import follow_up as fu
from jarvis.bot.follow_up import (
    FOLLOW_UP_SCHEMA,
    PROGRESS_UPDATES_SCHEMA,
    FollowUps,
    build_follow_up_tool,
    build_progress_updates_tool,
    spoken_duration,
)


class _Clock:
    """A sleep that records how long it was asked for and returns at once
    after yielding, so a follow-up's whole life runs in microseconds."""

    def __init__(self):
        self.slept: list[float] = []

    async def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        await asyncio.sleep(0)


async def _settle():
    for _ in range(20):
        await asyncio.sleep(0)


async def test_a_follow_up_comes_due_once_as_a_note_to_run_the_check():
    delivered: list[str] = []

    async def deliver(text):
        delivered.append(text)
        return True

    clock = _Clock()
    f = FollowUps(deliver, lambda: False, sleep=clock.sleep)
    result = f.schedule(60, "  the status of the\nself-edit run ")
    assert result == {"ok": True, "id": 1, "after_seconds": 60,
                      "check": "the status of the self-edit run"}
    assert f.pending() == [{"id": 1, "after_seconds": 60, "check": "the status of the self-edit run"}]
    await _settle()
    assert clock.slept == [60]
    assert delivered == [
        "[follow-up due] 60 seconds ago you told the user you would check back on this: "
        "the status of the self-edit run. Do that check now — through the tool or specialist "
        "that can answer it, never from memory — and tell the user what you found in one or "
        "two sentences."
    ]
    assert f.pending() == []


async def test_it_waits_while_anyone_is_speaking_then_delivers():
    delivered: list[str] = []
    speaking = {"left": 3}

    def is_speaking():
        speaking["left"] -= 1
        return speaking["left"] >= 0

    async def deliver(text):
        delivered.append(text)
        return True

    clock = _Clock()
    f = FollowUps(deliver, is_speaking, sleep=clock.sleep)
    f.schedule(120, "the build")
    await _settle()
    assert clock.slept == [120, 1.0, 1.0, 1.0]
    assert len(delivered) == 1
    assert delivered[0].startswith("[follow-up due] 2 minutes 3 seconds ago ")


async def test_speech_that_never_stops_delays_delivery_by_at_most_a_minute():
    delivered: list[str] = []

    async def deliver(text):
        delivered.append(text)
        return True

    clock = _Clock()
    f = FollowUps(deliver, lambda: True, sleep=clock.sleep)
    f.schedule(10, "x")
    await asyncio.sleep(0.05)
    assert sum(clock.slept[1:]) == fu.MAX_SPEAKING_WAIT_S
    assert len(delivered) == 1


@pytest.mark.parametrize("after, check, error", [
    (9, "x", "after_seconds must be 10 to 1800"),
    (1801, "x", "after_seconds must be 10 to 1800"),
    (60, "   ", "say what to check"),
])
async def test_out_of_range_or_empty_is_refused(after, check, error):
    f = FollowUps(lambda _t: None, lambda: False)
    result = f.schedule(after, check)
    assert result["ok"] is False and error in result["error"]
    assert f.pending() == []


async def test_at_most_three_pending_and_cancel_all():
    f = FollowUps(lambda _t: None, lambda: False)   # real sleep: nothing comes due
    for i in range(fu.MAX_PENDING):
        assert f.schedule(600, f"check {i}")["ok"]
    assert f.schedule(600, "one more") == {"ok": False, "error": "3 follow-ups are already pending"}
    assert f.cancel_all() == 3
    assert f.pending() == []
    assert f.schedule(600, "after cancel")["ok"]
    await f.stop()
    assert f.pending() == []


async def test_a_session_that_is_ending_drops_the_follow_up_without_raising():
    async def deliver(_text):
        return False                 # inject_late_result after teardown began

    clock = _Clock()
    f = FollowUps(deliver, lambda: False, sleep=clock.sleep)
    f.schedule(30, "x")
    await _settle()
    assert f.pending() == []


def test_spoken_duration():
    assert spoken_duration(10) == "10 seconds"
    assert spoken_duration(119) == "119 seconds"
    assert spoken_duration(120) == "2 minutes"
    assert spoken_duration(125) == "2 minutes 5 seconds"
    assert spoken_duration(1800) == "30 minutes"


# ------------------------------------------------------------ the tools


async def test_follow_up_tool_schedules_cancels_and_explains_refusals():
    holder: dict = {}
    schema, handler = build_follow_up_tool(holder)
    assert schema is FOLLOW_UP_SCHEMA
    assert await handler({"after_seconds": 60, "check": "x"}) == \
        "Follow-ups are not available in this session."
    holder["follow_ups"] = FollowUps(lambda _t: None, lambda: False)
    said = await handler({"after_seconds": 60, "check": "the self-edit run"})
    assert said == ("Follow-up set: in 60 seconds the check comes back to you — the self-edit "
                    "run. Tell the user when you will check; do not check now.")
    assert await handler({"after_seconds": 5, "check": "x"}) == \
        "Not scheduled: after_seconds must be 10 to 1800 (0 cancels pending follow-ups)."
    assert await handler({"after_seconds": "soon", "check": "x"}) == \
        "Not scheduled: after_seconds must be a whole number of seconds."
    assert await handler({"after_seconds": 0}) == "Cancelled 1 pending follow-up."
    assert await handler({"after_seconds": 0}) == "Cancelled 0 pending follow-ups."


async def test_progress_updates_tool_sets_the_session_interval():
    class _Watcher:
        interval = 30

        def set_interval(self, seconds):
            if seconds not in (0, 20):
                raise ValueError("every_seconds must be 0 (off) or 10 to 300")
            self.interval = seconds

    holder: dict = {}
    schema, handler = build_progress_updates_tool(holder)
    assert schema is PROGRESS_UPDATES_SCHEMA
    assert await handler({"every_seconds": 20}) == "Progress updates are not running in this session."
    holder["progress"] = _Watcher()
    assert await handler({"every_seconds": 20}) == (
        "Progress updates are now every 20 seconds for the rest of this conversation, spoken "
        "only while a task is running.")
    assert holder["progress"].interval == 20
    assert await handler({"every_seconds": 0}) == \
        "Progress updates are off for the rest of this conversation."
    assert await handler({"every_seconds": 5}) == \
        "Not changed: every_seconds must be 0 (off) or 10 to 300."
    assert (await handler({})).startswith("Not changed:")


@pytest.mark.parametrize("env", [fu.FOLLOW_UPS_ENV, fu.PROGRESS_UPDATES_ENV])
def test_kill_switches(monkeypatch, env):
    check = fu.follow_ups_enabled if env == fu.FOLLOW_UPS_ENV else fu.progress_updates_enabled
    monkeypatch.delenv(env, raising=False)
    assert check() is True
    for off in ("false", "0", "no", " OFF "):
        monkeypatch.setenv(env, off)
        assert check() is False
    monkeypatch.setenv(env, "true")
    assert check() is True
