"""TranscriptLogger pipeline processor (plan Phase 4, step 4.2; Phase 5, step 5.1).

Sits between the LLM service and the rest of the pipeline and:
(a) prints every finalized user transcription with a timestamp,
(b) prints assistant text turns,
(c) appends both to the conversations table under the session_id,
(d) prints per-turn latency lines:
    - TURN user_end->llm_done = <ms>      (Phase 4)
    - TURN user_end->first_audio = <ms>   (Phase 5, first outbound audio)
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
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from jarvis.db import get_conn, now_iso


class TranscriptLogger(FrameProcessor):
    def __init__(self, session_id: str, **kwargs: Any):
        super().__init__(**kwargs)
        self._session_id = session_id
        self._turn_start: float | None = None
        self._audio_logged_for_turn = False
        self._assistant_buffer: list[str] = []

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)

        if isinstance(frame, UserStoppedSpeakingFrame):
            self._turn_start = time.perf_counter()
            self._audio_logged_for_turn = False

        elif isinstance(frame, TranscriptionFrame):
            # Finalized user transcript (Flux sends TranscriptionFrame with
            # finalized=True for completed utterances).
            if getattr(frame, "finalized", True):
                text = frame.text.strip()
                if text:
                    print(f"[{_ts()}] USER: {text}", flush=True)
                    self._persist("user", text)

        elif isinstance(frame, LLMTextFrame):
            self._assistant_buffer.append(frame.text)

        elif isinstance(frame, LLMFullResponseEndFrame):
            text = "".join(self._assistant_buffer).strip()
            self._assistant_buffer = []
            if text:
                print(f"[{_ts()}] JARVIS: {text}", flush=True)
                self._persist("assistant", text)
            self._log_turn("llm_done")

        elif isinstance(frame, OutputAudioRawFrame):
            if not self._audio_logged_for_turn:
                self._audio_logged_for_turn = True
                self._log_turn("first_audio")

        await self.push_frame(frame, direction)

    def _log_turn(self, metric: str) -> None:
        if self._turn_start is None:
            return
        ms = int((time.perf_counter() - self._turn_start) * 1000)
        print(f"TURN user_end->{metric} = {ms}ms", flush=True)

    def _persist(self, role: str, content: str) -> None:
        try:
            with get_conn() as conn:
                conn.execute(
                    "INSERT INTO conversations (session_id, role, content, created_at) "
                    "VALUES (?, ?, ?, ?)",
                    (self._session_id, role, content, now_iso()),
                )
        except Exception as exc:  # noqa: BLE001 — logging must never break audio
            print(f"TranscriptLogger persist error: {exc}", flush=True)


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S")
