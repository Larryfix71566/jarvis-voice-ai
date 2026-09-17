"""Interruption awareness (plan Phase 3).

Detects genuine user barge-in and, when one occurs, silently appends a short
note to the shared LLM context so the Supervisor knows on the *next* turn
that its previous reply was cut off — without triggering an immediate
spoken reaction the way the greeting/reminder injections do.

Why "genuine" needs its own detection:
the LLMUserAggregator calls `broadcast_interruption()` (emits
`InterruptionFrame` both upstream and downstream) whenever its user-turn-
start strategy triggers — i.e. every time a user turn opens, including the
ordinary case where the assistant has already finished its previous reply.
(Until 2026-08-22 Flux's `should_interrupt=True` did the same thing one
layer earlier, on every VAD-level StartOfTurn — that's now off; see
pipeline.py's stt construction.) Naively treating every
`InterruptionFrame` as a barge-in would attach a false note to every
single turn. An `InterruptionFrame` only reflects a real interruption when
the assistant's turn was still active (LLM still generating, or TTS audio
still playing) at the moment it fires.

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
    LLMFullResponseStartFrame,
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
    - ``LLMFullResponseStartFrame`` -> a reply is genuinely in flight
      (active=True). NOT ``UserStoppedSpeakingFrame`` — that was the
      2026-08-22 defect: VAD-level user-stop fires for utterances the
      speaker gate then DROPS (TV speech), so every TV line armed the
      notifier with no reply in flight, and the next routine
      InterruptionFrame injected a false "your reply was interrupted"
      note. Measured in one 2026-08-21 session's final LLM context:
      90 notices against 12 real user messages — the model's view of the
      conversation was 88% interruption spam, which is what made its
      replies read clipped and apologetic. Arming on the LLM's own
      response-start frame makes "active" mean exactly "there is a reply
      to interrupt", by construction.
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
        # Item 14 (2026-09-17): the id of the last InterruptionFrame acted
        # on. An observer sees the same frame once per downstream hop, and
        # the hops after the LLM land after the next reply's
        # LLMFullResponseStartFrame has re-armed this notifier -- so
        # without this, one routine turn boundary produced three notes,
        # every turn (measured 2026-09-16 11:43: one broadcast per turn in
        # the pipecat log, three notes per turn in the context).
        self._last_interruption_id: int | None = None

    async def on_push_frame(self, data: FramePushed) -> None:
        # InterruptionFrame is broadcast both directions; every other frame
        # here flows downstream once. Filtering to one direction keeps each
        # event single-shot.
        if data.direction != FrameDirection.DOWNSTREAM:
            return

        frame = data.frame

        if isinstance(frame, LLMFullResponseStartFrame):
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
            # One frame, one decision -- recorded on first sight regardless
            # of state, so a boundary observed while no reply was in flight
            # stays ignored at its later hops even after a re-arm.
            if frame.id == self._last_interruption_id:
                return
            self._last_interruption_id = frame.id
            if self._assistant_active:
                # Cleared BEFORE the await: a hop that lands while the
                # inject is still in flight must not read the reply as
                # still active.
                self._assistant_active = False
                if self._enabled:
                    note = (
                        INTERRUPTION_NOTICE_MID_SPEECH
                        if self._audio_played
                        else INTERRUPTION_NOTICE_WHILE_THINKING
                    )
                    await self._inject(note)
            return
