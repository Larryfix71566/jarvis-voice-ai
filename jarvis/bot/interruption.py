"""Interruption awareness (plan Phase 3).

Detects genuine user barge-in and, when one occurs, silently appends a short
note to the shared LLM context so the Supervisor knows on the *next* turn
that its previous reply was cut off — without triggering an immediate
spoken reaction the way the greeting/reminder injections do.

Why "genuine" needs its own detection:
`DeepgramFluxSTTService(should_interrupt=True)` calls
`broadcast_interruption()` (emits `InterruptionFrame` both upstream and
downstream) on every StartOfTurn event — i.e. every time the user starts
speaking, including the ordinary case where the assistant has already
finished its previous reply. Naively treating every `InterruptionFrame` as
a barge-in would attach a false note to every single turn. An
`InterruptionFrame` only reflects a real interruption when the assistant's
turn was still active (LLM still generating, or TTS audio still playing) at
the moment it fires.

This is a task-level observer (the `TranscriptObserver` / D-007 pattern in
`transcript_log.py`): it sees frames at every hop regardless of the locked
9-processor order, which matters here because `BotStartedSpeakingFrame` /
`BotStoppedSpeakingFrame` are born downstream of the TTS service.
"""

from __future__ import annotations

from typing import Awaitable, Callable

from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    InterruptionFrame,
    LLMFullResponseEndFrame,
    UserStoppedSpeakingFrame,
)
from pipecat.observers.base_observer import BaseObserver, FramePushed
from pipecat.processors.frame_processor import FrameDirection

from jarvis.prompts import (
    INTERRUPTION_NOTICE_MID_SPEECH,
    INTERRUPTION_NOTICE_WHILE_THINKING,
)

InjectCallback = Callable[[str], Awaitable[None]]


class InterruptionNotifier(BaseObserver):
    """Detects genuine barge-in; injects a context note when one happens.

    State machine (reset each assistant turn):
    - ``UserStoppedSpeakingFrame`` -> assistant turn begins (active=True).
    - ``LLMFullResponseEndFrame`` -> text generation finished.
    - ``BotStartedSpeakingFrame`` -> audio has started playing this turn.
    - ``BotStoppedSpeakingFrame`` -> if text was also done, the turn ended
      cleanly (active=False); a *later* InterruptionFrame is then just
      routine turn-boundary noise, not a barge-in.
    - ``InterruptionFrame`` -> only counts as a barge-in if the turn was
      still active. mid-speech vs while-thinking is distinguished by
      whether audio had already started for this turn.
    """

    def __init__(self, inject: InjectCallback, enabled: bool = True):
        super().__init__()
        self._inject = inject
        self._enabled = enabled
        self._assistant_active = False
        self._llm_response_ended = False
        self._audio_played = False

    async def on_push_frame(self, data: FramePushed) -> None:
        # InterruptionFrame is broadcast both directions; every other frame
        # here flows downstream once. Filtering to one direction keeps each
        # event single-shot.
        if data.direction != FrameDirection.DOWNSTREAM:
            return

        frame = data.frame

        if isinstance(frame, UserStoppedSpeakingFrame):
            self._assistant_active = True
            self._llm_response_ended = False
            self._audio_played = False
            return

        if isinstance(frame, LLMFullResponseEndFrame):
            self._llm_response_ended = True
            return

        if isinstance(frame, BotStartedSpeakingFrame):
            self._audio_played = True
            return

        if isinstance(frame, BotStoppedSpeakingFrame):
            if self._llm_response_ended:
                self._assistant_active = False
            return

        if isinstance(frame, InterruptionFrame):
            if self._assistant_active:
                if self._enabled:
                    note = (
                        INTERRUPTION_NOTICE_MID_SPEECH
                        if self._audio_played
                        else INTERRUPTION_NOTICE_WHILE_THINKING
                    )
                    await self._inject(note)
                self._assistant_active = False
            return
