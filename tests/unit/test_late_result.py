"""Unit tests for jarvis/bot/late_result.py's LateResultNeutralizer
(MORTIMER_SESSION_MISSES_PLAN.md S6-S8).

No pipeline: on_push_frame is driven directly with FramePushed wrapping
the REAL pipecat 1.4.0 frame classes (the same construction
tests/unit/test_usage_watcher.py and test_speaker_gate.py use), so a
pipecat rename of LLMFullResponseStart/EndFrame or InterruptionFrame
fails here first. The note is a plain dict, exactly what
pipeline.inject_late_result hands to add_messages — identity, not
equality, is what the in-place rewrite depends on (test at the bottom).
"""

from __future__ import annotations

import logging

import pytest
from pipecat.frames.frames import (
    InterruptionFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
)
from pipecat.observers.base_observer import FramePushed
from pipecat.processors.frame_processor import FrameDirection

from jarvis.bot.late_result import LATE_RESULT_RELAYED_NOTE, LateResultNeutralizer

NOTE = (
    "[system] Background update: the Analyst task delegated earlier finished "
    "after the conversation moved on. Result: Three and a half centuries…\n"
    "Relay this to the user once, in one or two short sentences, and do not "
    "repeat it in later turns."
)


def _pushed(frame, direction=FrameDirection.DOWNSTREAM) -> FramePushed:
    return FramePushed(source=None, destination=None, frame=frame,
                       direction=direction, timestamp=0)


def _note() -> dict:
    return {"role": "user", "content": NOTE}


@pytest.fixture
def neutralizer():
    return LateResultNeutralizer(enabled=True)


class TestRelayTurn:
    @pytest.mark.asyncio
    async def test_relay_turn_neutralizes_the_note(self, neutralizer):
        note = _note()
        neutralizer.arm(note)
        await neutralizer.on_push_frame(_pushed(LLMFullResponseStartFrame()))
        await neutralizer.on_push_frame(_pushed(LLMFullResponseEndFrame()))
        assert note["content"] == LATE_RESULT_RELAYED_NOTE
        assert note["role"] == "user"                # only the content changes
        assert neutralizer.pending_count == 0

    @pytest.mark.asyncio
    async def test_stale_end_frame_while_armed_is_ignored(self, neutralizer):
        """The response already in flight when the note landed ends AFTER
        arm() but BEFORE the relay starts. Neutralizing then would hide a
        result the model has not spoken yet — the one failure worse than
        the repeat this fixes."""
        note = _note()
        neutralizer.arm(note)
        await neutralizer.on_push_frame(_pushed(LLMFullResponseEndFrame()))
        assert note["content"] == NOTE
        assert neutralizer.pending_count == 1
        # …and the relay that follows still neutralizes normally.
        await neutralizer.on_push_frame(_pushed(LLMFullResponseStartFrame()))
        await neutralizer.on_push_frame(_pushed(LLMFullResponseEndFrame()))
        assert note["content"] == LATE_RESULT_RELAYED_NOTE

    @pytest.mark.asyncio
    async def test_interruption_during_relay_neutralizes(self, neutralizer):
        note = _note()
        neutralizer.arm(note)
        await neutralizer.on_push_frame(_pushed(LLMFullResponseStartFrame()))
        await neutralizer.on_push_frame(_pushed(InterruptionFrame()))
        assert note["content"] == LATE_RESULT_RELAYED_NOTE
        assert neutralizer.pending_count == 0

    @pytest.mark.asyncio
    async def test_interruption_while_only_armed_is_ignored(self, neutralizer):
        """An interruption of the PREVIOUS response (before the relay has
        started) is not the user cutting off the relay."""
        note = _note()
        neutralizer.arm(note)
        await neutralizer.on_push_frame(_pushed(InterruptionFrame()))
        assert note["content"] == NOTE
        assert neutralizer.pending_count == 1

    @pytest.mark.asyncio
    async def test_two_pending_notes_both_neutralized(self, neutralizer):
        a, b = _note(), _note()
        neutralizer.arm(a)
        neutralizer.arm(b)
        await neutralizer.on_push_frame(_pushed(LLMFullResponseStartFrame()))
        await neutralizer.on_push_frame(_pushed(LLMFullResponseEndFrame()))
        assert a["content"] == LATE_RESULT_RELAYED_NOTE
        assert b["content"] == LATE_RESULT_RELAYED_NOTE
        assert neutralizer.pending_count == 0

    @pytest.mark.asyncio
    async def test_other_frames_do_not_advance_the_state(self, neutralizer):
        note = _note()
        neutralizer.arm(note)
        await neutralizer.on_push_frame(_pushed(LLMTextFrame(text="Three and")))
        await neutralizer.on_push_frame(_pushed(LLMFullResponseEndFrame()))
        # A text frame is not a start frame: still ARMED, so the end is stale.
        assert note["content"] == NOTE

    @pytest.mark.asyncio
    async def test_logs_once_per_neutralization(self, neutralizer, caplog):
        note = _note()
        neutralizer.arm(note)
        with caplog.at_level(logging.INFO, logger="jarvis.bot.late_result"):
            await neutralizer.on_push_frame(_pushed(LLMFullResponseStartFrame()))
            await neutralizer.on_push_frame(_pushed(LLMFullResponseEndFrame()))
        assert "late_result_neutralized count=1 via=LLMFullResponseEndFrame" in caplog.text


class TestGuards:
    @pytest.mark.asyncio
    async def test_nothing_pending_is_a_no_op(self, neutralizer):
        await neutralizer.on_push_frame(_pushed(LLMFullResponseStartFrame()))
        await neutralizer.on_push_frame(_pushed(LLMFullResponseEndFrame()))
        assert neutralizer.pending_count == 0     # and no exception

    @pytest.mark.asyncio
    async def test_disabled_never_rewrites(self):
        off = LateResultNeutralizer(enabled=False)
        note = _note()
        off.arm(note)
        await off.on_push_frame(_pushed(LLMFullResponseStartFrame()))
        await off.on_push_frame(_pushed(LLMFullResponseEndFrame()))
        assert note["content"] == NOTE
        assert off.pending_count == 0             # disabled never holds a note
        assert off.enabled is False

    @pytest.mark.asyncio
    async def test_upstream_frames_ignored(self, neutralizer):
        note = _note()
        neutralizer.arm(note)
        await neutralizer.on_push_frame(_pushed(LLMFullResponseStartFrame(), FrameDirection.UPSTREAM))
        await neutralizer.on_push_frame(_pushed(LLMFullResponseEndFrame(), FrameDirection.UPSTREAM))
        assert note["content"] == NOTE
        assert neutralizer.pending_count == 1

    @pytest.mark.asyncio
    async def test_same_dict_object_is_mutated(self, neutralizer):
        """What makes this work at all: pipecat's LLMContext.add_messages
        extends its list with the caller's dict objects (llm_context.py:394),
        so rewriting THIS object is what the next get_messages() returns.
        A copy would leave the aggregator holding the imperative."""
        note = _note()
        held_by_aggregator = note                 # same object, as add_messages keeps it
        neutralizer.arm(note)
        await neutralizer.on_push_frame(_pushed(LLMFullResponseStartFrame()))
        await neutralizer.on_push_frame(_pushed(LLMFullResponseEndFrame()))
        assert held_by_aggregator is note
        assert held_by_aggregator["content"] == LATE_RESULT_RELAYED_NOTE

    @pytest.mark.asyncio
    async def test_a_second_note_after_neutralizing_starts_fresh(self, neutralizer):
        first = _note()
        neutralizer.arm(first)
        await neutralizer.on_push_frame(_pushed(LLMFullResponseStartFrame()))
        await neutralizer.on_push_frame(_pushed(LLMFullResponseEndFrame()))
        second = _note()
        neutralizer.arm(second)
        # The relay that just ended must not count for the new note.
        await neutralizer.on_push_frame(_pushed(LLMFullResponseEndFrame()))
        assert second["content"] == NOTE
        await neutralizer.on_push_frame(_pushed(LLMFullResponseStartFrame()))
        await neutralizer.on_push_frame(_pushed(LLMFullResponseEndFrame()))
        assert second["content"] == LATE_RESULT_RELAYED_NOTE


class TestArmDuringRelay:
    @pytest.mark.asyncio
    async def test_note_armed_mid_relay_waits_for_its_own_relay(self, neutralizer):
        """Two orphaned delegations landing close together: b arrives while
        a's relay is already being spoken. The End of a's relay must NOT
        neutralize b — b has not been relayed yet (that would be the silent
        loss S8 exists to prevent). arm() therefore re-arms the state; a's
        imperative survives one extra turn (a repeat risk, once), b is
        relayed on the next response and both are then neutralized."""
        a, b = _note(), _note()
        neutralizer.arm(a)
        await neutralizer.on_push_frame(_pushed(LLMFullResponseStartFrame()))   # a's relay starts
        neutralizer.arm(b)                                                       # b lands mid-relay
        await neutralizer.on_push_frame(_pushed(LLMFullResponseEndFrame()))     # a's relay ends
        assert b["content"] == NOTE, "b must not be neutralized by a relay it was not part of"
        assert neutralizer.pending_count == 2
        await neutralizer.on_push_frame(_pushed(LLMFullResponseStartFrame()))
        await neutralizer.on_push_frame(_pushed(LLMFullResponseEndFrame()))
        assert a["content"] == LATE_RESULT_RELAYED_NOTE
        assert b["content"] == LATE_RESULT_RELAYED_NOTE
        assert neutralizer.pending_count == 0
