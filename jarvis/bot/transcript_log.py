"""Transcript logging for the voice pipeline (plan Phase 4 step 4.2, Phase 5 step 5.1).

Two pieces:

- ``TranscriptLogger`` — pipeline processor in its LOCKED position between the
  LLM service and the TTS service. Prints assistant text turns, appends them to
  the conversations table, and prints the per-turn latency line:
    - TURN user_end->llm_done = <ms>      (Phase 4)

- ``TranscriptObserver`` — task-level observer (D-007) handling the USER side:
  prints every finalized user transcription with a timestamp and appends it to
  the conversations table, and prints the Phase 5 latency line:
    - TURN user_end->first_audio = <ms>   (first outbound audio of the turn)
  pipecat 1.4's LLMUserContextAggregator CONSUMES TranscriptionFrame instead of
  forwarding it downstream, so a processor placed after the LLM never sees user
  transcripts. The same routing reality applies to first_audio: TranscriptLogger
  sits UPSTREAM of the TTS service in the locked order, so OutputAudioRawFrame
  (born at the TTS service) never travels back through it — a processor-side
  first_audio branch can never fire. Observers see every frame at every hop
  without altering the locked 9-processor order, which makes them the
  wiring-level mechanism for both duties.
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any

from pipecat.frames.frames import (
    Frame,
    InterruptionFrame,
    LLMFullResponseEndFrame,
    LLMTextFrame,
    OutputAudioRawFrame,
    TranscriptionFrame,
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame,
)
from pipecat.observers.base_observer import BaseObserver, FramePushed
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from jarvis.bot.sensitive_turn import (
    arm_from_text, current_sensitive_turn, is_sensitive, redacted,
)
from jarvis.db import get_conn, now_iso

#: Log prefix for assistant turns. scripts/spoken_acceptance.py parses this
#: marker — keep the two in sync.
ASSISTANT_LOG_PREFIX = "MORTIMER:"


class TranscriptLogger(FrameProcessor):
    def __init__(self, session_id: str, **kwargs: Any):
        super().__init__(**kwargs)
        self._session_id = session_id
        self._turn_start: float | None = None
        self._assistant_buffer: list[str] = []

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        if isinstance(frame, InterruptionFrame):
            # Barge-in: drop the half-built reply so it is never flushed, and
            # clear the flag (plan D-H4). Do this BEFORE super()/push.
            self._assistant_buffer = []
            holder = current_sensitive_turn.get()
            if holder is not None:
                holder.clear()

        await super().process_frame(frame, direction)

        if isinstance(frame, UserStoppedSpeakingFrame):
            self._turn_start = time.perf_counter()

        elif isinstance(frame, LLMTextFrame):
            self._assistant_buffer.append(frame.text)

        elif isinstance(frame, LLMFullResponseEndFrame):
            text = "".join(self._assistant_buffer).strip()
            self._assistant_buffer = []
            if text:
                # P2/P7 (plan D-H6, review F2): the reply itself may be the
                # only place the value appears ("what's my balance?" ->
                # "$2,431.18"). Scan it before printing/persisting.
                arm_from_text(text)
                if is_sensitive():
                    print(f"[{_ts()}] {ASSISTANT_LOG_PREFIX} "
                          f"{redacted(text)}", flush=True)
                else:
                    print(f"[{_ts()}] {ASSISTANT_LOG_PREFIX} {text}", flush=True)
                    self._persist("assistant", text)
            self._log_turn("llm_done")

        await self.push_frame(frame, direction)

    def _log_turn(self, metric: str) -> None:
        if self._turn_start is None:
            return
        ms = int((time.perf_counter() - self._turn_start) * 1000)
        print(f"TURN user_end->{metric} = {ms}ms", flush=True)

    def _persist(self, role: str, content: str) -> None:
        _persist(self._session_id, role, content)


class TranscriptObserver(BaseObserver):
    """Task-level observer for the USER side of the transcript (D-007).

    Sees the finalized TranscriptionFrame on its single hop from the Flux STT
    service to the user context aggregator (which consumes it). Prints the
    USER: line and persists the user row — the work the plan assigned to
    TranscriptLogger before pipecat 1.4's aggregator stopped forwarding
    TranscriptionFrame downstream.
    """

    def __init__(self, session_id: str, only_from: Any = None):
        """``only_from`` (Tier 2 speaker gate, 2026-08-21): when set to a
        pipeline processor, USER transcript lines are logged/persisted ONLY
        for TranscriptionFrames pushed BY that processor. The speaker
        gate's TranscriptGate sits between STT and the aggregator; without
        this filter the observer logs the STT->gate hop and a dropped
        (unknown-speaker) utterance still lands in the conversations table
        — which the memory sweep folds into long-term memory. Observed
        live: TV dialogue persisted as a USER line. With the filter, what
        is persisted is exactly what the LLM received."""
        super().__init__()
        self._session_id = session_id
        self._only_from = only_from
        self._turn_start: float | None = None
        self._audio_logged_for_turn = False
        self._user_buffer: list[str] = []

    async def on_push_frame(self, data: FramePushed) -> None:
        frame = data.frame
        if data.direction != FrameDirection.DOWNSTREAM:
            return

        if isinstance(frame, UserStartedSpeakingFrame):
            holder = current_sensitive_turn.get()
            if holder is not None:
                holder.clear()
            self._user_buffer = []
            return

        if isinstance(frame, UserStoppedSpeakingFrame):
            self._turn_start = time.perf_counter()
            self._audio_logged_for_turn = False
            text = " ".join(self._user_buffer).strip()
            self._user_buffer = []
            if text:
                arm_from_text(text)          # arm on the FULL turn text
                if is_sensitive():
                    # P6 (plan D-H6): no content to bot.log, no conversations row
                    print(f"[{_ts()}] USER: {redacted(text)}", flush=True)
                else:
                    print(f"[{_ts()}] USER: {text}", flush=True)
                    _persist(self._session_id, "user", text)  # P1
            return

        if isinstance(frame, OutputAudioRawFrame):
            # First outbound audio of the turn (Phase 5 first_audio latency).
            # The frame is observed once per downstream hop; the flag keeps the
            # TURN line single-shot per turn.
            if self._turn_start is not None and not self._audio_logged_for_turn:
                self._audio_logged_for_turn = True
                ms = int((time.perf_counter() - self._turn_start) * 1000)
                print(f"TURN user_end->first_audio = {ms}ms", flush=True)
            return

        if not isinstance(frame, TranscriptionFrame):
            return
        if self._only_from is not None and data.source is not self._only_from:
            # Speaker gate active: only the gate's own downstream push
            # counts — the STT->gate hop may carry an utterance the gate
            # is about to drop.
            return
        if not getattr(frame, "finalized", True):
            return
        text = frame.text.strip()
        if not text:
            return
        # review F13: accumulate; detection and emit happen once at turn close
        # (6c). Arm incrementally too, so a single-segment turn is armed as
        # early as possible; arm_from_text is idempotent and total.
        self._user_buffer.append(text)
        arm_from_text(" ".join(self._user_buffer))


def _persist(session_id: str, role: str, content: str) -> None:
    # P3 (plan D-H6) — defence in depth. P1/P2 already avoid calling this on a
    # sensitive turn; this makes a future caller that forgets harmless. Note
    # is_sensitive() is fail-closed, so an unwired context suppresses here too.
    if is_sensitive():
        return
    try:
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO conversations (session_id, role, content, created_at) "
                "VALUES (?, ?, ?, ?)",
                (session_id, role, content, now_iso()),
            )
    except Exception as exc:  # noqa: BLE001 — logging must never break audio
        print(f"TranscriptLogger persist error: {exc}", flush=True)


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S")
