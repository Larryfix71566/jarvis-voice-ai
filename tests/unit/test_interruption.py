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


class TestTheSameFrameAtEveryHop:
    """Item 14 (2026-09-17). A task-level observer sees one InterruptionFrame
    once per downstream hop, and the hops after the LLM arrive after the
    next reply's LLMFullResponseStartFrame has re-armed the notifier.
    Measured 2026-09-16 11:43: exactly one `broadcasting interruption` per
    user turn in the pipecat log, exactly three notes per user turn in the
    context -- the three hops downstream of the LLM. Every test above this
    class pushes each frame once, which is why none of them caught it."""

    async def test_a_routine_boundary_seen_at_four_hops_across_a_rearm_injects_nothing(self):
        injected = []

        async def inject(text):
            injected.append(text)

        notifier = InterruptionNotifier(inject)
        for frame in (LLMFullResponseStartFrame(), LLMFullResponseEndFrame(),
                      BotStartedSpeakingFrame(), BotStoppedSpeakingFrame()):
            await notifier.on_push_frame(pushed(frame))          # a clean reply
        boundary = InterruptionFrame()                            # the next turn opening
        await notifier.on_push_frame(pushed(boundary))            # hop: aggregator -> LLM
        await notifier.on_push_frame(pushed(LLMFullResponseStartFrame()))  # the new reply re-arms
        for _ in range(3):                                        # LLM -> TTS -> output -> assistant agg
            await notifier.on_push_frame(pushed(boundary))
        assert injected == []

    async def test_a_genuine_barge_in_seen_at_four_hops_injects_exactly_once(self):
        injected = []

        async def inject(text):
            injected.append(text)

        notifier = InterruptionNotifier(inject)
        await notifier.on_push_frame(pushed(LLMFullResponseStartFrame()))   # reply in flight
        cut = InterruptionFrame()
        await notifier.on_push_frame(pushed(cut))                            # hop 1: genuine
        await notifier.on_push_frame(pushed(LLMFullResponseStartFrame()))   # reply to the interruption
        for _ in range(3):
            await notifier.on_push_frame(pushed(cut))
        assert injected == [INTERRUPTION_NOTICE_WHILE_THINKING]

    async def test_two_distinct_interruptions_after_two_replies_inject_twice(self):
        """The dedupe is by frame, not by turn: a second real barge-in on a
        second reply must still be reported."""
        injected = []

        async def inject(text):
            injected.append(text)

        notifier = InterruptionNotifier(inject)
        for _ in range(2):
            await notifier.on_push_frame(pushed(LLMFullResponseStartFrame()))
            await notifier.on_push_frame(pushed(InterruptionFrame()))
        assert injected == [INTERRUPTION_NOTICE_WHILE_THINKING] * 2

    async def test_a_hop_arriving_mid_inject_does_not_see_the_reply_as_active(self):
        """Two DISTINCT frames, so this isolates the check-then-await race
        from the dedupe: the second lands while the first's inject is still
        awaiting, and must find the reply already marked inactive."""
        import asyncio

        gate = asyncio.Event()
        injected = []

        async def inject(text):
            injected.append(text)
            await gate.wait()

        notifier = InterruptionNotifier(inject)
        await notifier.on_push_frame(pushed(LLMFullResponseStartFrame()))
        first = asyncio.create_task(notifier.on_push_frame(pushed(InterruptionFrame())))
        await asyncio.sleep(0)                                    # parked inside inject
        await notifier.on_push_frame(pushed(InterruptionFrame()))  # arrives mid-await
        gate.set()
        await first
        assert injected == [INTERRUPTION_NOTICE_WHILE_THINKING]


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
