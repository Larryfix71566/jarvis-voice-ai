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
    LLMFullResponseEndFrame,
    LLMTextFrame,
    OutputAudioRawFrame,
    TranscriptionFrame,
    UserStoppedSpeakingFrame,
)
from pipecat.observers.base_observer import BaseObserver, FramePushed
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

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
        await super().process_frame(frame, direction)

        if isinstance(frame, UserStoppedSpeakingFrame):
            self._turn_start = time.perf_counter()

        elif isinstance(frame, LLMTextFrame):
            self._assistant_buffer.append(frame.text)

        elif isinstance(frame, LLMFullResponseEndFrame):
            text = "".join(self._assistant_buffer).strip()
            self._assistant_buffer = []
            if text:
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

    async def on_push_frame(self, data: FramePushed) -> None:
        frame = data.frame
        if data.direction != FrameDirection.DOWNSTREAM:
            return

        if isinstance(frame, UserStoppedSpeakingFrame):
            self._turn_start = time.perf_counter()
            self._audio_logged_for_turn = False
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
        print(f"[{_ts()}] USER: {text}", flush=True)
        _persist(self._session_id, "user", text)


def _persist(session_id: str, role: str, content: str) -> None:
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
