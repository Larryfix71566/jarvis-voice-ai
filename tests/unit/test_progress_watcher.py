"""Unit tests for ProgressWatcher (MORTIMER_SESSION_GAPS_AND_SELFEDIT_
CONVERGENCE_PLAN.md G12). Modeled on tests/unit/test_plan_watcher.py's
shape: injected async seams (fetch_delegations, fetch_selfedit_job) so no
real DB or network is exercised."""

from __future__ import annotations

import pytest

from jarvis.bot.progress_watcher import PROGRESS_UPDATE_INTERVAL_S, ProgressWatcher


class _Recorder:
    def __init__(self):
        self.spoken: list[str] = []

    async def speak(self, text: str) -> None:
        self.spoken.append(text)


def _watcher(
    rec: _Recorder,
    delegations: list[dict] | None = None,
    selfedit_job: dict | None = None,
    connected: bool = True,
    speaking: bool = False,
) -> ProgressWatcher:
    async def fetch_delegations():
        return delegations or []

    async def fetch_selfedit_job():
        return selfedit_job

    return ProgressWatcher(
        speak=rec.speak,
        is_connected=lambda: connected,
        is_speaking=lambda: speaking,
        fetch_delegations=fetch_delegations,
        fetch_selfedit_job=fetch_selfedit_job,
    )


# ------------------------------------------------------------- basics


async def test_default_interval_is_thirty_seconds():
    assert PROGRESS_UPDATE_INTERVAL_S == 30.0


async def test_disconnected_skips_tick_entirely():
    rec = _Recorder()
    w = _watcher(rec, delegations=[{"display_name": "Developer", "tool_count": 3}], connected=False)
    await w.tick_once()
    assert rec.spoken == []


async def test_speaking_suppresses_the_tick():
    """Suppressed, never queued: the plan explicitly requires skip-not-
    queue while user or bot is speaking."""
    rec = _Recorder()
    w = _watcher(
        rec, delegations=[{"display_name": "Developer", "tool_count": 3}], speaking=True,
    )
    await w.tick_once()
    assert rec.spoken == []


async def test_nothing_in_flight_produces_no_update():
    """G12's core rule: work that finished inside the 30s window gets no
    update at all — the absence of an announcement IS the correct
    behavior, not a missed one."""
    rec = _Recorder()
    w = _watcher(rec, delegations=[], selfedit_job=None)
    await w.tick_once()
    assert rec.spoken == []


# ------------------------------------------------------------- delegations


async def test_one_delegation_produces_one_update():
    rec = _Recorder()
    w = _watcher(rec, delegations=[
        {"display_name": "Developer", "tool_count": 4, "last_tool": "repo_read_file"},
    ])
    await w.tick_once()
    assert len(rec.spoken) == 1
    assert "Developer" in rec.spoken[0]
    assert "4 tool calls in" in rec.spoken[0]
    assert "last was repo_read_file" in rec.spoken[0]


async def test_tool_count_one_uses_singular_call():
    rec = _Recorder()
    w = _watcher(rec, delegations=[{"display_name": "Analyst", "tool_count": 1}])
    await w.tick_once()
    assert "1 tool call in" in rec.spoken[0]
    assert "1 tool calls" not in rec.spoken[0]


async def test_missing_last_tool_omits_that_clause():
    rec = _Recorder()
    w = _watcher(rec, delegations=[{"display_name": "Analyst", "tool_count": 0}])
    await w.tick_once()
    assert "last was" not in rec.spoken[0]


async def test_concurrent_delegations_produce_one_aggregated_update():
    """Never two separate spoken utterances back to back for one tick —
    everything in flight rides in a single speak() call."""
    rec = _Recorder()
    w = _watcher(rec, delegations=[
        {"display_name": "Analyst", "tool_count": 2},
        {"display_name": "Developer", "tool_count": 5},
    ])
    await w.tick_once()
    assert len(rec.spoken) == 1
    assert "Analyst" in rec.spoken[0]
    assert "Developer" in rec.spoken[0]


# ------------------------------------------------------------- self-edit


async def test_selfedit_job_alone_still_updates():
    rec = _Recorder()
    w = _watcher(rec, selfedit_job={"state": "running", "profile": "kimi-k3 (kimi-k3-model)"})
    await w.tick_once()
    assert len(rec.spoken) == 1
    assert "Self-edit still running" in rec.spoken[0]
    assert "kimi-k3 (kimi-k3-model)" in rec.spoken[0]


async def test_finish_job_is_announced_while_the_gates_run():
    """SE4 — on the authored path no planner job ever starts, so the finish
    job's gates are the only thing in flight. They run for minutes (the
    Swift build plus the suite); silence there is the worst case for a
    progress watcher."""
    rec = _Recorder()
    w = _watcher(rec, selfedit_job={"finish_state": "validating"})
    await w.tick_once()
    assert len(rec.spoken) == 1
    assert "Self-edit validating" in rec.spoken[0]

    rec2 = _Recorder()
    w2 = _watcher(rec2, selfedit_job={"finish_state": "submitting"})
    await w2.tick_once()
    assert "opening the pull request" in rec2.spoken[0]


async def test_the_fetcher_treats_a_running_finish_as_in_flight():
    """The shape _default_fetch_selfedit_job returns for each case, without
    HTTP: an idle planner job plus a validating finish is IN flight; both
    idle is not."""
    from jarvis.bot import progress_watcher as pw

    class _Resp:
        def __init__(self, payload):
            self._payload = payload

        def json(self):
            return self._payload

    class _Client:
        def __init__(self, payload):
            self._payload = payload

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, url):
            return _Resp(self._payload)

    async def fetch(payload, monkeypatched=None):
        import sys
        import types
        fake = types.ModuleType("httpx")
        fake.AsyncClient = lambda timeout=None: _Client(payload)
        saved = sys.modules.get("httpx")
        sys.modules["httpx"] = fake
        try:
            return await pw._default_fetch_selfedit_job("http://x")
        finally:
            if saved is not None:
                sys.modules["httpx"] = saved
            else:
                del sys.modules["httpx"]

    idle = {"ok": True, "job": {"state": "idle"}, "finish": {"state": "idle"}}
    assert await fetch(idle) is None

    validating = {"ok": True, "job": {"state": "idle"},
                  "finish": {"state": "validating"}}
    assert await fetch(validating) == {"finish_state": "validating"}

    planning = {"ok": True, "job": {"state": "running", "profile": "kimi-k3"},
                "finish": {"state": "idle"}}
    assert (await fetch(planning))["profile"] == "kimi-k3"


async def test_delegation_and_selfedit_together_one_update():
    rec = _Recorder()
    w = _watcher(
        rec,
        delegations=[{"display_name": "Developer", "tool_count": 1}],
        selfedit_job={"state": "running", "profile": "kimi-k2"},
    )
    await w.tick_once()
    assert len(rec.spoken) == 1
    assert "Developer" in rec.spoken[0]
    assert "Self-edit still running" in rec.spoken[0]


# ------------------------------------------------------------- resilience


async def test_delegations_fetch_failure_does_not_raise():
    rec = _Recorder()

    async def _explode():
        raise ConnectionError("db unreachable")

    w = ProgressWatcher(
        speak=rec.speak,
        is_connected=lambda: True,
        is_speaking=lambda: False,
        fetch_delegations=_explode,
        fetch_selfedit_job=lambda: _no_job(),
    )
    await w.tick_once()
    assert rec.spoken == []  # degrades to "nothing to report", not a crash


async def test_selfedit_fetch_failure_still_reports_delegations():
    rec = _Recorder()

    async def _explode():
        raise ConnectionError("sidecar offline")

    w = ProgressWatcher(
        speak=rec.speak,
        is_connected=lambda: True,
        is_speaking=lambda: False,
        fetch_delegations=lambda: _one_delegation(),
        fetch_selfedit_job=_explode,
    )
    await w.tick_once()
    assert len(rec.spoken) == 1
    assert "Developer" in rec.spoken[0]


async def _no_job():
    return None


async def _one_delegation():
    return [{"display_name": "Developer", "tool_count": 2}]


# ------------------------------------------------------------- repeating cadence


async def test_repeated_ticks_speak_every_time_work_continues():
    """G12 is a REPEATING ambient ping, not a one-shot per-transition
    announcement (unlike PlanWatcher) — three ticks with work still in
    flight produce three updates."""
    rec = _Recorder()
    w = _watcher(rec, delegations=[{"display_name": "Developer", "tool_count": 1}])
    await w.tick_once()
    await w.tick_once()
    await w.tick_once()
    assert len(rec.spoken) == 3


class TestSpeakingStateTracker:
    """The observer ProgressWatcher's is_speaking suppression relies on."""

    async def test_starts_not_busy(self):
        from jarvis.bot.progress_watcher import SpeakingStateTracker

        assert SpeakingStateTracker().is_busy() is False

    async def test_bot_speaking_sets_busy(self):
        from pipecat.frames.frames import BotStartedSpeakingFrame, BotStoppedSpeakingFrame
        from pipecat.observers.base_observer import FramePushed
        from pipecat.processors.frame_processor import FrameDirection

        from jarvis.bot.progress_watcher import SpeakingStateTracker

        t = SpeakingStateTracker()
        await t.on_push_frame(FramePushed(
            source=None, destination=None, frame=BotStartedSpeakingFrame(),
            direction=FrameDirection.DOWNSTREAM, timestamp=0,
        ))
        assert t.is_busy() is True
        await t.on_push_frame(FramePushed(
            source=None, destination=None, frame=BotStoppedSpeakingFrame(),
            direction=FrameDirection.DOWNSTREAM, timestamp=0,
        ))
        assert t.is_busy() is False

    async def test_user_speaking_sets_busy(self):
        from pipecat.frames.frames import UserStartedSpeakingFrame, UserStoppedSpeakingFrame
        from pipecat.observers.base_observer import FramePushed
        from pipecat.processors.frame_processor import FrameDirection

        from jarvis.bot.progress_watcher import SpeakingStateTracker

        t = SpeakingStateTracker()
        await t.on_push_frame(FramePushed(
            source=None, destination=None, frame=UserStartedSpeakingFrame(),
            direction=FrameDirection.DOWNSTREAM, timestamp=0,
        ))
        assert t.is_busy() is True
        await t.on_push_frame(FramePushed(
            source=None, destination=None, frame=UserStoppedSpeakingFrame(),
            direction=FrameDirection.DOWNSTREAM, timestamp=0,
        ))
        assert t.is_busy() is False

    async def test_upstream_frames_ignored(self):
        from pipecat.frames.frames import BotStartedSpeakingFrame
        from pipecat.observers.base_observer import FramePushed
        from pipecat.processors.frame_processor import FrameDirection

        from jarvis.bot.progress_watcher import SpeakingStateTracker

        t = SpeakingStateTracker()
        await t.on_push_frame(FramePushed(
            source=None, destination=None, frame=BotStartedSpeakingFrame(),
            direction=FrameDirection.UPSTREAM, timestamp=0,
        ))
        assert t.is_busy() is False


async def test_kill_switch_env_read_at_pipeline_construction_site():
    """The kill switch lives in jarvis/bot/pipeline.py's run_session, same
    pattern as JARVIS_PLAN_WATCHER_ENABLED — this module itself has no
    env-reading logic to test in isolation."""
    import jarvis.bot.pipeline as pipeline_module

    assert "JARVIS_PROGRESS_UPDATES_ENABLED" in pipeline_module.__loader__.get_source(
        pipeline_module.__name__
    )
