"""Unit tests for jarvis/bot/interruption.py (plan Phase 3).

Mandatory negative case: a normal completed turn — where Flux's
should_interrupt=True broadcasts an InterruptionFrame at the START of every
new user turn, not just genuine barge-ins — must produce NO injected note.
"""

from __future__ import annotations

from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    InterruptionFrame,
    LLMFullResponseEndFrame,
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
    """Simulate a turn that completes cleanly: text ends, audio plays and
    stops, THEN the next user turn's StartOfTurn fires an InterruptionFrame
    (the routine Flux broadcast, not a barge-in)."""
    await notifier.on_push_frame(pushed(UserStoppedSpeakingFrame()))
    await notifier.on_push_frame(pushed(LLMFullResponseEndFrame()))
    await notifier.on_push_frame(pushed(BotStartedSpeakingFrame()))
    await notifier.on_push_frame(pushed(BotStoppedSpeakingFrame()))
    # Next turn's StartOfTurn always broadcasts InterruptionFrame.
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


class TestGenuineInterruption:
    async def test_mid_speech_interruption(self):
        """Bot was actively speaking (audio started) when interrupted."""
        injected = []

        async def inject(text):
            injected.append(text)

        notifier = InterruptionNotifier(inject, enabled=True)
        await notifier.on_push_frame(pushed(UserStoppedSpeakingFrame()))
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
        await notifier.on_push_frame(pushed(UserStoppedSpeakingFrame()))
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
        await notifier.on_push_frame(pushed(UserStoppedSpeakingFrame()))
        await notifier.on_push_frame(pushed(InterruptionFrame()))

        assert injected == []

    async def test_upstream_direction_ignored(self):
        """InterruptionFrame is broadcast both directions; only the
        downstream hop should be counted (avoids double-injection)."""
        injected = []

        async def inject(text):
            injected.append(text)

        notifier = InterruptionNotifier(inject, enabled=True)
        await notifier.on_push_frame(pushed(UserStoppedSpeakingFrame()))
        upstream_interrupt = FramePushed(
            source=None, destination=None, frame=InterruptionFrame(),
            direction=FrameDirection.UPSTREAM, timestamp=0,
        )
        await notifier.on_push_frame(upstream_interrupt)

        assert injected == []

    async def test_second_interruption_in_same_turn_not_double_counted(self):
        """After a barge-in resets assistant_active, a second
        InterruptionFrame with no new UserStoppedSpeakingFrame in between
        must not fire again."""
        injected = []

        async def inject(text):
            injected.append(text)

        notifier = InterruptionNotifier(inject, enabled=True)
        await notifier.on_push_frame(pushed(UserStoppedSpeakingFrame()))
        await notifier.on_push_frame(pushed(InterruptionFrame()))
        await notifier.on_push_frame(pushed(InterruptionFrame()))

        assert injected == [INTERRUPTION_NOTICE_WHILE_THINKING]
