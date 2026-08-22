"""Speaker gate pipeline wiring — two FrameProcessors.
MORTIMER_VOICE_ISOLATION_TIER12_PLAN.md Tier 2 (§4.3).

``SpeakerTap`` sits immediately AFTER the VADProcessor, BEFORE the STT
service: it watches raw audio for the current speaking turn and computes a
verification score on a background thread as soon as enough speech has
accumulated (L9). ``TranscriptGate`` sits immediately AFTER the STT
service, BEFORE the context aggregator: it holds a final TranscriptionFrame
briefly for that score, then applies the pass/drop policy in
``jarvis.speaker.verdict``.

Both pass every OTHER frame through untouched. Neither processor is
inserted into the pipeline at all unless the gate is enabled, a profile is
on disk, AND the encoder loads (jarvis/bot/pipeline.py's build_pipeline) —
so a disabled or half-configured gate costs nothing and changes nothing.

L7: this module NEVER touches UserStartedSpeakingFrame/
UserStoppedSpeakingFrame in a way that would gate interruption — it only
ever holds or drops TranscriptionFrame. An unknown voice can still
interrupt Mortimer's TTS; that limitation is intentional and documented in
the plan, not an oversight here.
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pipecat.frames.frames import (
    Frame,
    InputAudioRawFrame,
    InterimTranscriptionFrame,
    TranscriptionFrame,
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.turns.types import ProcessFrameResult
from pipecat.turns.user_start import MinWordsUserTurnStartStrategy

from jarvis import speaker
from jarvis.prompts import DROP_NOTICE

logger = logging.getLogger(__name__)

#: Bound on how much audio a single turn accumulates, so a very long or
#: stuck "speaking" state can't grow the buffer without limit.
MAX_BUFFER_SECS = 12

#: Minimum accumulated speech before an embedding is even attempted.
#: Below this ECAPA's convolutions have fewer feature frames than their
#: padding and raise (observed live 2026-08-21: "padding (2, 2) at
#: dimension 2 of input [1, 80, 1]") — and a clip this short always
#: passes via MIN_VERIFY_SECS anyway, so scoring it buys nothing.
MIN_EMBED_SECS = 0.4

# F1/F2 (MORTIMER_GATE_V2_AND_MODEL_REQUEST_PLAN.md, 2026-08-22) —
# windowed scoring. A single whole-buffer embedding dilutes when a long
# turn mixes Larry's voice with background TV: measured live, three
# 7-12s turns at 0.29-0.34 (his clean-turn score is ~0.59+) against a
# TV-alone band of 0.00-0.26. Scoring sliding sub-windows and keeping the
# MAX finds his voice inside the mixture without lowering the threshold
# (which would just let more of the TV band through instead).
SCORE_WINDOW_SECS = 3.0
SCORE_HOP_SECS = 1.5
#: Bounds worst-case embedding calls per turn (a MAX_BUFFER_SECS=12
#: buffer at these window/hop values would otherwise produce ~7
#: windows plus the whole buffer — already under this, so it is a
#: guardrail against future constant changes, not an active limit today).
MAX_SCORE_WINDOWS = 8


def _window_slices(n_bytes: int, sample_rate: int) -> list[slice]:
    """Byte-offset slices for F1's sliding sub-windows, PLUS the whole
    buffer as the final entry — the caller always compares max-over-all,
    so the whole-buffer score (the pre-F1 behavior) is never lost, only
    ever beaten by a better window. Pure and total: never raises, and
    returns just [whole buffer] when the buffer is too short to window
    (short turns already had exactly this scoring before F1).

    int16 mono: 2 bytes/sample.
    """
    bytes_per_sec = 2 * sample_rate
    whole = slice(0, n_bytes)
    window_bytes = int(SCORE_WINDOW_SECS * bytes_per_sec)
    hop_bytes = int(SCORE_HOP_SECS * bytes_per_sec)
    min_embed_bytes = int(MIN_EMBED_SECS * bytes_per_sec)

    if window_bytes <= 0 or hop_bytes <= 0 or n_bytes <= window_bytes:
        return [whole]

    slices: list[slice] = []
    start = 0
    while start + min_embed_bytes <= n_bytes and len(slices) < MAX_SCORE_WINDOWS:
        end = min(start + window_bytes, n_bytes)
        slices.append(slice(start, end))
        if end == n_bytes:
            break
        start += hop_bytes
    slices.append(whole)
    return slices

#: Live-path enrollment capture (2026-08-21, after the first full live
#: session): Larry's QuickTime-enrolled profile scored 0.89-0.94 offline
#: but his LIVE speech scored 0.30-0.55 — the mic path (WebRTC capture,
#: browser processing, RNNoise) is a different audio domain than a
#: QuickTime recording, and the gate dropped several of his own turns.
#: With JARVIS_SPEAKER_CAPTURE=true, each turn's buffer (>= 1s) is saved
#: as a WAV under data/speaker_captures/ so enrollment can be re-run FROM
#: THE PATH THE GATE ACTUALLY SCORES. Bounded, opt-in, and meant to be
#: turned off after re-enrolling — it records everything the mic hears.
CAPTURE_ENV = "JARVIS_SPEAKER_CAPTURE"
CAPTURE_DIR = Path("data/speaker_captures")
CAPTURE_MIN_SECS = 1.0
CAPTURE_MAX_FILES = 20


# F3/F4 (MORTIMER_GATE_V2_AND_MODEL_REQUEST_PLAN.md, 2026-08-22) — the
# honest-drop note and UI chip. Doubly bounded so this can never recreate
# the 2026-08-22 InterruptionNotifier flood (90 false notices in one
# session): a note/chip fires ONLY for a drop whose score is plausibly
# the enrolled speaker (near the threshold, not deep in the TV band —
# measured TV scores were 0.00-0.26, overwhelmingly <=0.21) AND only
# once per cooldown window, regardless of how many near-threshold drops
# happen in between.
DROP_NOTE_MIN_SCORE = 0.25
DROP_NOTE_COOLDOWN_S = 60.0


def capture_enabled() -> bool:
    value = os.environ.get(CAPTURE_ENV)
    return value is not None and value.strip().lower() in ("true", "1", "yes")


def _write_capture(pcm16: bytes, sample_rate: int) -> None:
    """Write one turn's audio as a WAV (stdlib wave — int16 mono) and
    prune to the newest CAPTURE_MAX_FILES. Any failure is logged and
    swallowed: capture is a calibration aid, never worth breaking audio."""
    try:
        import time
        import wave

        CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
        path = CAPTURE_DIR / f"turn-{time.strftime('%H%M%S')}-{int(time.time() * 1000) % 1000:03d}.wav"
        with wave.open(str(path), "wb") as f:
            f.setnchannels(1)
            f.setsampwidth(2)
            f.setframerate(sample_rate)
            f.writeframes(pcm16)
        existing = sorted(CAPTURE_DIR.glob("turn-*.wav"))
        for old in existing[:-CAPTURE_MAX_FILES]:
            old.unlink(missing_ok=True)
        logger.info("speaker_capture_saved path=%s secs=%.1f", path,
                    len(pcm16) / (2 * sample_rate))
    except Exception:
        logger.warning("speaker_capture_failed", exc_info=True)


@dataclass
class GateState:
    """Shared between SpeakerTap and TranscriptGate for one connection.
    Plain data holder — no behavior, so it's trivial to fake in tests."""

    turn_id: int = 0
    scores: dict[int, float | None] = field(default_factory=dict)
    speech_secs: dict[int, float] = field(default_factory=dict)


class SpeakerTap(FrameProcessor):
    """Watches raw audio, schedules embedding + scoring on a thread, and
    writes the result into the shared GateState keyed by turn_id."""

    def __init__(
        self,
        state: GateState,
        encoder: "speaker.Encoder",
        profile,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._state = state
        self._encoder = encoder
        self._profile = profile
        self._buffer = bytearray()
        self._sample_rate = 16000
        self._verified_this_turn = False

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)

        if isinstance(frame, UserStartedSpeakingFrame):
            self._state.turn_id += 1
            self._buffer = bytearray()
            self._verified_this_turn = False

        elif isinstance(frame, InputAudioRawFrame):
            self._sample_rate = frame.sample_rate or self._sample_rate
            max_bytes = MAX_BUFFER_SECS * self._sample_rate * 2  # int16 mono
            if len(self._buffer) < max_bytes:
                self._buffer.extend(frame.audio)
            accumulated_secs = len(self._buffer) / (2 * self._sample_rate)
            if (
                not self._verified_this_turn
                and accumulated_secs >= speaker.MIN_VERIFY_SECS
            ):
                self._verified_this_turn = True
                self._schedule_score()

        elif isinstance(frame, UserStoppedSpeakingFrame):
            self._schedule_score(final=True)

        await self.push_frame(frame, direction)

    def _schedule_score(self, final: bool = False) -> None:
        turn_id = self._state.turn_id
        pcm16 = bytes(self._buffer)
        sample_rate = self._sample_rate
        speech_secs = len(pcm16) / (2 * sample_rate) if sample_rate else 0.0
        self._state.speech_secs[turn_id] = speech_secs
        # Capture only the FINAL (end-of-utterance) buffer — the mid-turn
        # call at MIN_VERIFY_SECS would save a truncated 1s clip.
        if final and capture_enabled() and speech_secs >= CAPTURE_MIN_SECS:
            _write_capture(pcm16, sample_rate)
        if speech_secs < MIN_EMBED_SECS:
            # Too little audio to embed (see MIN_EMBED_SECS) — leave the
            # score absent; verdict() passes anything under MIN_VERIFY_SECS.
            return

        def _score_all_windows() -> tuple[float | None, int, float | None]:
            """Runs inside ONE to_thread call (F2): embeds every window
            plus the whole buffer and returns (max_score, window_count,
            whole_buffer_score). Never raises — caller treats any
            exception as "no score", matching pre-F1 behavior."""
            if self._profile is None:
                return None, 0, None
            slices = _window_slices(len(pcm16), sample_rate)
            scores: list[float] = []
            whole_score: float | None = None
            for i, sl in enumerate(slices):
                chunk = pcm16[sl]
                is_whole = sl.stop - sl.start == len(pcm16)
                embedding = self._encoder.embed(chunk, sample_rate)
                if embedding is None:
                    continue
                s = speaker.cosine(embedding, self._profile)
                scores.append(s)
                if is_whole:
                    whole_score = s
            if not scores:
                return None, 0, whole_score
            return max(scores), len(scores), whole_score

        async def _run() -> None:
            try:
                best, n_windows, whole = await asyncio.to_thread(_score_all_windows)
                self._state.scores[turn_id] = best
                if final:
                    logger.info(
                        "speaker_gate_scored turn_id=%s windows=%d best=%s whole=%s",
                        turn_id, n_windows,
                        f"{best:.2f}" if best is not None else "none",
                        f"{whole:.2f}" if whole is not None else "none",
                    )
            except Exception:
                logger.warning("speaker_gate_score_failed turn_id=%s", turn_id, exc_info=True)
                self._state.scores[turn_id] = None

        asyncio.create_task(_run())


class TranscriptGate(FrameProcessor):
    """Holds a final TranscriptionFrame for its turn's score (up to
    GATE_HOLD_TIMEOUT_S), then applies jarvis.speaker.verdict. Interim
    transcripts and every other frame pass through untouched (L7)."""

    def __init__(
        self,
        state: GateState,
        send_message: Any,
        profile_loaded: bool,
        inject: Any = None,
        **kwargs: Any,
    ) -> None:
        """``send_message`` is an async callable(dict) -> None — the same
        app-message channel every other tool in pipeline.py uses (passed
        in rather than imported here to avoid speaker_gate.py <-> pipeline.py
        becoming a circular import).

        ``inject`` (F3, optional) is an async callable(str) -> None — the
        SAME silent-append channel InterruptionNotifier uses
        (pipeline.py's ``inject_silent``), so a near-threshold drop can
        tell the Supervisor's NEXT turn that something may have been
        missed, without speaking up now. None (the default) disables the
        note entirely — existing callers/tests that don't pass it keep
        exact prior behavior."""
        super().__init__(**kwargs)
        self._state = state
        self._send_message = send_message
        self._profile_loaded = profile_loaded
        self._inject = inject
        self._last_drop_note_at: float = 0.0

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)

        if isinstance(frame, InterimTranscriptionFrame):
            await self.push_frame(frame, direction)
            return

        if not isinstance(frame, TranscriptionFrame):
            await self.push_frame(frame, direction)
            return

        turn_id = self._state.turn_id
        score = await self._await_score(turn_id)
        speech_secs = self._state.speech_secs.get(turn_id, 0.0)
        result = speaker.verdict(score, speech_secs, self._profile_loaded)

        if result == "pass":
            await self.push_frame(frame, direction)
            return

        # "drop" — never log or transmit the transcript text itself
        # (L6/§4.3/F5).
        logger.info(
            "speaker_gate_dropped score=%s secs=%.1f text_len=%d",
            f"{score:.2f}" if score is not None else "none",
            speech_secs,
            len(frame.text or ""),
        )
        near_threshold = score is not None and score >= DROP_NOTE_MIN_SCORE
        try:
            await self._send_message({
                "type": "speaker_gate", "verdict": "dropped",
                "score": score, "near_threshold": near_threshold,
            })
        except Exception:
            logger.debug("speaker_gate_ui_notify_failed", exc_info=True)

        # F3 — the honest-drop context note. Doubly bounded: only for a
        # score plausibly the enrolled speaker (near_threshold), and only
        # once per DROP_NOTE_COOLDOWN_S regardless of how many
        # near-threshold drops happen in between.
        if near_threshold and self._inject is not None:
            now = asyncio.get_event_loop().time()
            if now - self._last_drop_note_at >= DROP_NOTE_COOLDOWN_S:
                self._last_drop_note_at = now
                try:
                    await self._inject(DROP_NOTICE)
                except Exception:
                    logger.debug("speaker_gate_drop_note_failed", exc_info=True)
        # Do not push the frame downstream.

    async def _await_score(self, turn_id: int) -> float | None:
        elapsed = 0.0
        step = 0.05
        while elapsed < speaker.GATE_HOLD_TIMEOUT_S:
            if turn_id in self._state.scores:
                return self._state.scores.get(turn_id)
            await asyncio.sleep(step)
            elapsed += step
        return self._state.scores.get(turn_id)


class SpeakerVerifiedMinWordsTurnStartStrategy(MinWordsUserTurnStartStrategy):
    """Min-words turn start PLUS speaker verification for interruptions.

    Added 2026-08-21 after the first live session with the transcript gate:
    the gate correctly dropped every TV transcript (scores 0.07-0.18 vs the
    0.40 threshold) but the TV still interrupted Mortimer's TTS constantly
    — the log showed four consecutive "reply was interrupted before any
    audio played" notes. Gating transcripts alone (the plan's L7 boundary)
    was not enough; the interruption itself needed the speaker check.

    Semantics, layered on the parent's:
    - Bot NOT speaking: unchanged — one word starts a turn, no speaker
      check. TV may open a turn while Mortimer is quiet; its transcript is
      then dropped by TranscriptGate and nothing is aggregated, so the
      turn dies silently. Zero added latency for Larry.
    - Bot SPEAKING: an interruption requires the parent's min_words AND a
      speaker score at/above threshold for the current turn. A missing
      score (SpeakerTap schedules it ~1s into speech) means "not yet" —
      the next interim transcription rechecks, so a real interruption by
      the enrolled voice lands within roughly a second. This is
      deliberately fail-CLOSED for interruptions only: the enrolled
      speaker's WORDS are never eaten (fail-open L5 still governs the
      transcript gate); worst case their barge-in takes effect a beat
      late or when the bot finishes its sentence.
    """

    def __init__(self, state: GateState, *, min_words: int, **kwargs: Any) -> None:
        super().__init__(min_words=min_words, **kwargs)
        self._gate_state = state

    async def _handle_transcription(
        self, frame: TranscriptionFrame | InterimTranscriptionFrame
    ) -> ProcessFrameResult:
        # NOTE: reads the parent's private _bot_speaking — accepted coupling,
        # pinned by test_strategy_tracks_parent_bot_speaking_attr so a pipecat
        # upgrade that renames it fails loudly here instead of silently
        # disabling the speaker check.
        if self._bot_speaking:
            score = self._gate_state.scores.get(self._gate_state.turn_id)
            if score is None or score < speaker.threshold():
                return ProcessFrameResult.CONTINUE
        return await super()._handle_transcription(frame)
