"""Unit tests for jarvis/bot/usage_watcher.py's UsageMetricsObserver
(MORTIMER_OPTIMIZATION_PLAN.md Phase 1, Rev 3.2, Path A, landing step
(iii), task 7 -- the compat/native usage-semantics branch -- and task 8's
supervisor_cache_cold WARNING).

No pipeline is built here: on_push_frame is called directly with a
hand-built FramePushed wrapping a real MetricsFrame/LLMUsageMetricsData/
LLMTokenUsage (all plain pydantic/dataclass models -- constructing them
makes no network call and needs no running pipeline; the same pattern
tests/unit/test_speaker_gate.py already uses for pipecat frames), against
the real installed pipecat 1.4.0 classes rather than fakes, so a future
pipecat upgrade that changes these shapes fails here first.

Each test that pushes more than one frame through the SAME observer
keeps an explicit reference to every frame for the test's duration --
the dedup mechanism keys on id(frame), not a held reference, so a frame
that's already been garbage-collected can have its id() reused by a
later one and be wrongly treated as "already seen" (caught while writing
these tests: an inline `pushed(...)` expression passed straight into
on_push_frame is eligible for GC the instant the call returns).
"""

from __future__ import annotations

import logging

import pytest
from pipecat.frames.frames import MetricsFrame
from pipecat.metrics.metrics import LLMTokenUsage, LLMUsageMetricsData
from pipecat.observers.base_observer import FramePushed
from pipecat.processors.frame_processor import FrameDirection

import jarvis.bot.usage_watcher as usage_watcher
from jarvis.bot.usage_watcher import UsageMetricsObserver


def _pushed(usage: LLMTokenUsage, model: str = "m") -> FramePushed:
    frame = MetricsFrame(data=[LLMUsageMetricsData(processor="llm", model=model, value=usage)])
    return FramePushed(source=None, destination=None, frame=frame,
                       direction=FrameDirection.DOWNSTREAM, timestamp=0)


@pytest.fixture
def calls(monkeypatch):
    recorded = []

    def fake_record_call(**kwargs):
        recorded.append(kwargs)

    monkeypatch.setattr(usage_watcher, "record_call", fake_record_call)
    return recorded


@pytest.fixture
def observer():
    return UsageMetricsObserver(rung="supervisor", provider="anthropic", session_id="s1")


class TestCompatSemantics:
    """cache_creation_input_tokens is None -> today's OpenAI/compat
    branch: prompt_tokens is cache-INCLUSIVE, subtract reads back out;
    cache_write always reports 0 (the permanent half of the KNOWN GAP)."""

    @pytest.mark.asyncio
    async def test_subtracts_cached_from_prompt_tokens(self, observer, calls):
        usage = LLMTokenUsage(prompt_tokens=100, completion_tokens=5, total_tokens=105,
                               cache_read_input_tokens=40, cache_creation_input_tokens=None)
        await observer.on_push_frame(_pushed(usage))
        assert calls[0]["input_tokens"] == 60
        assert calls[0]["cache_read_tokens"] == 40
        assert calls[0]["cache_write_tokens"] == 0

    @pytest.mark.asyncio
    async def test_no_cache_fields_at_all(self, observer, calls):
        usage = LLMTokenUsage(prompt_tokens=100, completion_tokens=5, total_tokens=105)
        await observer.on_push_frame(_pushed(usage))
        assert calls[0]["input_tokens"] == 100
        assert calls[0]["cache_read_tokens"] == 0
        assert calls[0]["cache_write_tokens"] == 0

    @pytest.mark.asyncio
    async def test_never_warns(self, observer, calls, caplog):
        usage = LLMTokenUsage(prompt_tokens=100, completion_tokens=5, total_tokens=105,
                               cache_read_input_tokens=0, cache_creation_input_tokens=None)
        with caplog.at_level(logging.WARNING):
            await observer.on_push_frame(_pushed(usage))
            await observer.on_push_frame(_pushed(usage))
        assert "supervisor_cache_cold" not in caplog.text


class TestNativeSemantics:
    """cache_creation_input_tokens is a real int (never None) -> Path A:
    prompt_tokens is already uncached-only, no subtraction; cache_write
    is real, no gap; turn >= 2 with a zero cache read warns."""

    @pytest.mark.asyncio
    async def test_prompt_tokens_used_as_is(self, observer, calls):
        usage = LLMTokenUsage(prompt_tokens=60, completion_tokens=5, total_tokens=65,
                               cache_read_input_tokens=0, cache_creation_input_tokens=7745)
        await observer.on_push_frame(_pushed(usage))
        assert calls[0]["input_tokens"] == 60
        assert calls[0]["cache_write_tokens"] == 7745

    @pytest.mark.asyncio
    async def test_cache_hit_reported(self, observer, calls):
        cold = LLMTokenUsage(prompt_tokens=60, completion_tokens=5, total_tokens=65,
                             cache_read_input_tokens=0, cache_creation_input_tokens=7745)
        warm = LLMTokenUsage(prompt_tokens=8, completion_tokens=5, total_tokens=13,
                             cache_read_input_tokens=7717, cache_creation_input_tokens=33)
        frame_cold, frame_warm = _pushed(cold), _pushed(warm)  # held for the test's duration
        await observer.on_push_frame(frame_cold)
        await observer.on_push_frame(frame_warm)
        assert calls[1]["cache_read_tokens"] == 7717
        assert calls[1]["input_tokens"] == 8

    @pytest.mark.asyncio
    async def test_turn_1_cold_never_warns(self, observer, calls, caplog):
        usage = LLMTokenUsage(prompt_tokens=60, completion_tokens=5, total_tokens=65,
                              cache_read_input_tokens=0, cache_creation_input_tokens=7745)
        with caplog.at_level(logging.WARNING):
            await observer.on_push_frame(_pushed(usage))
        assert "supervisor_cache_cold" not in caplog.text

    @pytest.mark.asyncio
    async def test_turn_2_cold_warns(self, observer, calls, caplog):
        turn1 = LLMTokenUsage(prompt_tokens=60, completion_tokens=5, total_tokens=65,
                              cache_read_input_tokens=0, cache_creation_input_tokens=7745)
        turn2_cold = LLMTokenUsage(prompt_tokens=61, completion_tokens=5, total_tokens=66,
                                   cache_read_input_tokens=0, cache_creation_input_tokens=61)
        frame1, frame2 = _pushed(turn1), _pushed(turn2_cold)
        with caplog.at_level(logging.WARNING):
            await observer.on_push_frame(frame1)
            await observer.on_push_frame(frame2)
        assert "supervisor_cache_cold turn=2 prompt_tokens=61" in caplog.text

    @pytest.mark.asyncio
    async def test_turn_2_warm_never_warns(self, observer, calls, caplog):
        turn1 = LLMTokenUsage(prompt_tokens=60, completion_tokens=5, total_tokens=65,
                              cache_read_input_tokens=0, cache_creation_input_tokens=7745)
        turn2_warm = LLMTokenUsage(prompt_tokens=8, completion_tokens=5, total_tokens=13,
                                    cache_read_input_tokens=7717, cache_creation_input_tokens=33)
        frame1, frame2 = _pushed(turn1), _pushed(turn2_warm)
        with caplog.at_level(logging.WARNING):
            await observer.on_push_frame(frame1)
            await observer.on_push_frame(frame2)
        assert "supervisor_cache_cold" not in caplog.text


class TestDedupStillHolds:
    @pytest.mark.asyncio
    async def test_same_frame_recorded_once(self, observer, calls):
        usage = LLMTokenUsage(prompt_tokens=60, completion_tokens=5, total_tokens=65,
                              cache_read_input_tokens=0, cache_creation_input_tokens=7745)
        frame = _pushed(usage)
        await observer.on_push_frame(frame)
        await observer.on_push_frame(frame)  # same frame object, second hop
        assert len(calls) == 1


# ---------------------------------------------------------------- S2: TTS rows
# MORTIMER_SESSION_MISSES_PLAN.md S2 — pipecat's TTS services push
# TTSUsageMetricsData(value=len(text)) on the same MetricsFrame channel;
# each becomes one ledger row on the `tts` rung with quantity/unit.

from pipecat.metrics.metrics import TTSUsageMetricsData  # noqa: E402


def _tts_pushed(chars: int, model: str | None = "eleven_flash_v2_5") -> FramePushed:
    frame = MetricsFrame(data=[TTSUsageMetricsData(processor="tts", model=model, value=chars)])
    return FramePushed(source=None, destination=None, frame=frame,
                       direction=FrameDirection.DOWNSTREAM, timestamp=0)


class TestTTSUsageRows:
    @pytest.mark.asyncio
    async def test_tts_usage_frame_writes_a_chars_row(self, observer, calls):
        pushed = _tts_pushed(125)
        await observer.on_push_frame(pushed)
        assert len(calls) == 1
        row = calls[0]
        assert row["rung"] == "tts"
        assert row["provider"] == "elevenlabs"
        assert row["model"] == "eleven_flash_v2_5"
        assert row["session_id"] == "s1"
        assert row["quantity"] == 125.0 and row["unit"] == "chars"
        # No token fields on a voice row — the ledger defaults them to 0.
        assert "input_tokens" not in row and "output_tokens" not in row

    @pytest.mark.asyncio
    async def test_tts_frame_is_deduplicated_across_hops(self, observer, calls):
        pushed = _tts_pushed(50)
        await observer.on_push_frame(pushed)
        await observer.on_push_frame(pushed)   # same frame object, later hop
        assert len(calls) == 1

    @pytest.mark.asyncio
    async def test_tts_row_uses_default_model_when_frame_has_none(self, calls):
        obs = UsageMetricsObserver(rung="supervisor", provider="anthropic", session_id="s1",
                                   tts_default_model="eleven_turbo_v2_5")
        pushed = _tts_pushed(10, model=None)
        await obs.on_push_frame(pushed)
        assert calls[0]["model"] == "eleven_turbo_v2_5"

    @pytest.mark.asyncio
    async def test_tts_provider_is_a_constructor_kwarg(self, calls):
        obs = UsageMetricsObserver(rung="supervisor", provider="anthropic", session_id="s1",
                                   tts_provider="cartesia")
        pushed = _tts_pushed(10)
        await obs.on_push_frame(pushed)
        assert calls[0]["provider"] == "cartesia"

    @pytest.mark.asyncio
    async def test_llm_frames_still_recorded_alongside_tts(self, observer, calls):
        usage = LLMTokenUsage(prompt_tokens=6, completion_tokens=24, total_tokens=30,
                               cache_creation_input_tokens=8500, cache_read_input_tokens=0)
        frame = MetricsFrame(data=[
            LLMUsageMetricsData(processor="llm", model="claude-haiku-4-5", value=usage),
            TTSUsageMetricsData(processor="tts", model="eleven_flash_v2_5", value=13),
        ])
        pushed = FramePushed(source=None, destination=None, frame=frame,
                             direction=FrameDirection.DOWNSTREAM, timestamp=0)
        await observer.on_push_frame(pushed)
        rungs = sorted(c["rung"] for c in calls)
        assert rungs == ["supervisor", "tts"]
        llm = next(c for c in calls if c["rung"] == "supervisor")
        assert llm["cache_write_tokens"] == 8500 and llm["output_tokens"] == 24

    @pytest.mark.asyncio
    async def test_tts_record_failure_never_raises(self, observer, monkeypatch, caplog):
        def boom(**kwargs):
            raise RuntimeError("ledger down")
        monkeypatch.setattr(usage_watcher, "record_call", boom)
        with caplog.at_level(logging.WARNING, logger="jarvis.bot.usage_watcher"):
            await observer.on_push_frame(_tts_pushed(5))
        assert "tts record_call failed" in caplog.text
