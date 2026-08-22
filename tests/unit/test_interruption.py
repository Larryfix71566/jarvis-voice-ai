"""Unit tests for jarvis/bot/interruption.py (plan Phase 3, arming fix
2026-08-22).

Two mandatory negative cases:
1. A normal completed turn — a routine turn-boundary InterruptionFrame
   (the LLMUserAggregator broadcasts one whenever a user turn opens) must
   produce NO injected note.
2. The TV-flood case (2026-08-22): a VAD-level user turn whose transcript
   the speaker gate DROPS never starts an LLM response, so the routine
   InterruptionFrame that follows must produce NO note. The old
   UserStoppedSpeakingFrame arming failed exactly this — one live session
   accumulated 90 false notices against 12 real user messages.
"""

from __future__ import annotations

from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    InterruptionFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    UserStoppedSpeakingFrame,
)
from pipecat.observers.base_observer import FramePushed
from pipecat.processors.frame_processor import FrameDirection

from jarvis.bot.interruption import InterruptionNotifier
from jarvis.prompts import (
    INTERRUPTION_NOTICE_MID_SPEECH,
    INTERRUPTION_NOTICE_WHILE_THINKING,
)


def pushed(frame):
    return FramePushed(
        source=None, destination=None, frame=frame,
        direction=FrameDirection.DOWNSTREAM, timestamp=0,
    )


async def _full_normal_turn(notifier: InterruptionNotifier) -> None:
    """Simulate a turn that completes cleanly: generation starts and ends,
    audio plays and stops, THEN the next user turn's opening fires an
    InterruptionFrame (the routine aggregator broadcast, not a barge-in)."""
    await notifier.on_push_frame(pushed(LLMFullResponseStartFrame()))
    await notifier.on_push_frame(pushed(LLMFullResponseEndFrame()))
    await notifier.on_push_frame(pushed(BotStartedSpeakingFrame()))
    await notifier.on_push_frame(pushed(BotStoppedSpeakingFrame()))
    # Next turn's opening always broadcasts InterruptionFrame.
    await notifier.on_push_frame(pushed(InterruptionFrame()))


class TestNoFalsePositive:
    async def test_completed_turn_produces_no_note(self):
        """The important negative case: no barge-in occurred, so no note."""
        injected = []

        async def inject(text):
            injected.append(text)

        notifier = InterruptionNotifier(inject, enabled=True)
        await _full_normal_turn(notifier)

        assert injected == []

    async def test_dropped_turn_with_no_reply_in_flight_produces_no_note(self):
        """The 2026-08-22 TV-flood defect, pinned: a VAD-level user stop
        (an utterance the speaker gate then dropped — no LLM response ever
        started) followed by a routine InterruptionFrame must inject
        NOTHING. The old arming on UserStoppedSpeakingFrame injected a
        false 'your reply was interrupted' note for every TV line."""
        injected = []

        async def inject(text):
            injected.append(text)

        notifier = InterruptionNotifier(inject, enabled=True)
        # TV speaks: VAD opens and closes a turn, gate drops the
        # transcript, no LLM run follows.
        await notifier.on_push_frame(pushed(UserStoppedSpeakingFrame()))
        # Next sound triggers the routine interruption broadcast.
        await notifier.on_push_frame(pushed(InterruptionFrame()))

        assert injected == []

    async def test_repeated_dropped_turns_never_accumulate_notes(self):
        """The flood shape itself: many dropped turns in a row (a TV left
        on) must inject zero notes total, not one per turn."""
        injected = []

        async def inject(text):
            injected.append(text)

        notifier = InterruptionNotifier(inject, enabled=True)
        for _ in range(20):
            await notifier.on_push_frame(pushed(UserStoppedSpeakingFrame()))
            await notifier.on_push_frame(pushed(InterruptionFrame()))

        assert injected == []


class TestGenuineInterruption:
    async def test_mid_speech_interruption(self):
        """Bot was actively speaking (audio started) when interrupted."""
        injected = []

        async def inject(text):
            injected.append(text)

        notifier = InterruptionNotifier(inject, enabled=True)
        await notifier.on_push_frame(pushed(LLMFullResponseStartFrame()))
        await notifier.on_push_frame(pushed(LLMFullResponseEndFrame()))
        await notifier.on_push_frame(pushed(BotStartedSpeakingFrame()))
        # User barges in mid-speech — no BotStoppedSpeakingFrame yet.
        await notifier.on_push_frame(pushed(InterruptionFrame()))

        assert injected == [INTERRUPTION_NOTICE_MID_SPEECH]

    async def test_while_thinking_interruption(self):
        """Bot was still generating text (no audio yet) when interrupted."""
        injected = []

        async def inject(text):
            injected.append(text)

        notifier = InterruptionNotifier(inject, enabled=True)
        await notifier.on_push_frame(pushed(LLMFullResponseStartFrame()))
        # No LLMFullResponseEndFrame, no BotStartedSpeakingFrame yet —
        # the assistant is still "thinking" when the user barges in.
        await notifier.on_push_frame(pushed(InterruptionFrame()))

        assert injected == [INTERRUPTION_NOTICE_WHILE_THINKING]

    async def test_disabled_flag_suppresses_injection(self):
        """JARVIS_INTERRUPTION_NOTICE_ENABLED=false must produce no note
        even during a genuine barge-in."""
        injected = []

        async def inject(text):
            injected.append(text)

        notifier = InterruptionNotifier(inject, enabled=False)
        await notifier.on_push_frame(pushed(LLMFullResponseStartFrame()))
        await notifier.on_push_frame(pushed(InterruptionFrame()))

        assert injected == []

    async def test_upstream_direction_ignored(self):
        """InterruptionFrame is broadcast both directions; only the
        downstream hop should be counted (avoids double-injection)."""
        injected = []

        async def inject(text):
            injected.append(text)

        notifier = InterruptionNotifier(inject, enabled=True)
        await notifier.on_push_frame(pushed(LLMFullResponseStartFrame()))
        upstream_interrupt = FramePushed(
            source=None, destination=None, frame=InterruptionFrame(),
            direction=FrameDirection.UPSTREAM, timestamp=0,
        )
        await notifier.on_push_frame(upstream_interrupt)

        assert injected == []

    async def test_second_interruption_in_same_turn_not_double_counted(self):
        """After a barge-in resets assistant_active, a second
        InterruptionFrame with no new LLMFullResponseStartFrame in between
        must not fire again."""
        injected = []

        async def inject(text):
            injected.append(text)

        notifier = InterruptionNotifier(inject, enabled=True)
        await notifier.on_push_frame(pushed(LLMFullResponseStartFrame()))
        await notifier.on_push_frame(pushed(InterruptionFrame()))
        await notifier.on_push_frame(pushed(InterruptionFrame()))

        assert injected == [INTERRUPTION_NOTICE_WHILE_THINKING]
