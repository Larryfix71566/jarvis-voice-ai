"""Unit tests for jarvis/bot/speaker_gate.py
(MORTIMER_VOICE_ISOLATION_TIER12_PLAN.md Tier 2, §5).

Two groups:
- TranscriptGate/SpeakerTap frame-processing logic, tested directly against
  the processors with push_frame monkeypatched (real pipecat FrameProcessors
  refuse to push_frame before a StartFrame has gone through, which unit
  tests never send — see class docstrings below for why this is safe).
- build_pipeline wiring guard: gate-enabled-but-no-profile inserts NEITHER
  processor into the pipeline (reusing the fakes pattern from
  tests/integration/test_bot_wiring.py).
"""

from __future__ import annotations

import logging
from types import SimpleNamespace

import numpy as np
import pytest

from jarvis import speaker
from jarvis.bot.speaker_gate import (
    MAX_SCORE_WINDOWS,
    MIN_EMBED_SECS,
    SCORE_HOP_SECS,
    SCORE_WINDOW_SECS,
    GateState,
    SpeakerTap,
    SpeakerVerifiedMinWordsTurnStartStrategy,
    TranscriptGate,
    _window_slices,
)
from pipecat.frames.frames import (
    InterimTranscriptionFrame,
    TranscriptionFrame,
)
from pipecat.processors.frame_processor import FrameDirection


def _make_gate(state: GateState, profile_loaded: bool = True, inject=None):
    sent = []

    async def send_message(message: dict) -> None:
        sent.append(message)

    gate = TranscriptGate(
        state, send_message, profile_loaded=profile_loaded, inject=inject,
    )
    pushed = []

    async def fake_push_frame(frame, direction=FrameDirection.DOWNSTREAM):
        pushed.append(frame)

    # Real FrameProcessor.push_frame logs an error and no-ops unless a
    # StartFrame has gone through __start(); unit tests never send one, so
    # push_frame is monkeypatched at the instance level to capture calls
    # instead of silently swallowing them.
    gate.push_frame = fake_push_frame
    return gate, pushed, sent


class TestTranscriptGateDrop:
    async def test_gate_drops_unknown_speaker(self, monkeypatch):
        monkeypatch.delenv(speaker.THRESHOLD_ENV, raising=False)
        state = GateState(turn_id=1)
        state.scores[1] = 0.1  # well below the 0.40 default threshold
        state.speech_secs[1] = 2.0
        gate, pushed, sent = _make_gate(state)

        frame = TranscriptionFrame(
            text="secret plan details", user_id="u", timestamp="t"
        )
        await gate.process_frame(frame, FrameDirection.DOWNSTREAM)

        assert pushed == []  # never forwarded
        assert sent == [{
            "type": "speaker_gate", "verdict": "dropped",
            "score": 0.1, "near_threshold": False,
        }]

    async def test_gate_never_logs_transcript_text(self, monkeypatch, caplog):
        monkeypatch.delenv(speaker.THRESHOLD_ENV, raising=False)
        state = GateState(turn_id=1)
        state.scores[1] = 0.1
        state.speech_secs[1] = 2.0
        gate, _, _ = _make_gate(state)

        secret_text = "unmistakable-secret-marker-xyz"
        frame = TranscriptionFrame(text=secret_text, user_id="u", timestamp="t")
        with caplog.at_level(logging.INFO):
            await gate.process_frame(frame, FrameDirection.DOWNSTREAM)

        for record in caplog.records:
            assert secret_text not in record.getMessage()

    async def test_gate_passes_known_speaker(self, monkeypatch):
        monkeypatch.delenv(speaker.THRESHOLD_ENV, raising=False)
        state = GateState(turn_id=1)
        state.scores[1] = 0.9
        state.speech_secs[1] = 2.0
        gate, pushed, sent = _make_gate(state)

        frame = TranscriptionFrame(text="hello there", user_id="u", timestamp="t")
        await gate.process_frame(frame, FrameDirection.DOWNSTREAM)

        assert pushed == [frame]
        assert sent == []


class TestHonestDropNote:
    """F3/F4/F5 (MORTIMER_GATE_V2_AND_MODEL_REQUEST_PLAN.md) — the
    honest-drop context note and app-message score/near_threshold flag."""

    async def test_deep_drop_injects_nothing(self, monkeypatch):
        """TV-band score: no note, no matter how confident the drop."""
        monkeypatch.delenv(speaker.THRESHOLD_ENV, raising=False)
        state = GateState(turn_id=1)
        state.scores[1] = 0.10  # deep in the measured TV band
        state.speech_secs[1] = 2.0
        injected = []

        async def inject(text):
            injected.append(text)

        gate, _, sent = _make_gate(state, inject=inject)
        frame = TranscriptionFrame(text="whatever", user_id="u", timestamp="t")
        await gate.process_frame(frame, FrameDirection.DOWNSTREAM)

        assert injected == []
        assert sent[0]["near_threshold"] is False

    async def test_near_threshold_drop_injects_note(self, monkeypatch):
        from jarvis.bot.speaker_gate import DROP_NOTE_MIN_SCORE
        from jarvis.prompts import DROP_NOTICE

        monkeypatch.delenv(speaker.THRESHOLD_ENV, raising=False)
        state = GateState(turn_id=1)
        state.scores[1] = DROP_NOTE_MIN_SCORE + 0.05  # plausibly Larry
        state.speech_secs[1] = 5.0
        injected = []

        async def inject(text):
            injected.append(text)

        gate, _, sent = _make_gate(state, inject=inject)
        frame = TranscriptionFrame(text="whatever", user_id="u", timestamp="t")
        await gate.process_frame(frame, FrameDirection.DOWNSTREAM)

        assert injected == [DROP_NOTICE]
        assert sent[0]["near_threshold"] is True
        assert sent[0]["score"] == state.scores[1]

    async def test_cooldown_suppresses_second_note(self, monkeypatch):
        from jarvis.bot.speaker_gate import DROP_NOTE_MIN_SCORE

        monkeypatch.delenv(speaker.THRESHOLD_ENV, raising=False)
        state = GateState(turn_id=1)
        state.scores[1] = DROP_NOTE_MIN_SCORE + 0.05
        state.speech_secs[1] = 5.0
        injected = []

        async def inject(text):
            injected.append(text)

        gate, _, _ = _make_gate(state, inject=inject)
        frame = TranscriptionFrame(text="one", user_id="u", timestamp="t")
        await gate.process_frame(frame, FrameDirection.DOWNSTREAM)

        # Second near-threshold drop immediately after — cooldown blocks it.
        state.turn_id = 2
        state.scores[2] = DROP_NOTE_MIN_SCORE + 0.05
        state.speech_secs[2] = 3.0
        frame2 = TranscriptionFrame(text="two", user_id="u", timestamp="t")
        await gate.process_frame(frame2, FrameDirection.DOWNSTREAM)

        assert len(injected) == 1

    async def test_drop_note_never_contains_transcript_text(self, monkeypatch):
        from jarvis.bot.speaker_gate import DROP_NOTE_MIN_SCORE

        monkeypatch.delenv(speaker.THRESHOLD_ENV, raising=False)
        state = GateState(turn_id=1)
        state.scores[1] = DROP_NOTE_MIN_SCORE + 0.05
        state.speech_secs[1] = 5.0
        injected = []

        async def inject(text):
            injected.append(text)

        gate, _, _ = _make_gate(state, inject=inject)
        secret_text = "unmistakable-secret-marker-xyz"
        frame = TranscriptionFrame(text=secret_text, user_id="u", timestamp="t")
        await gate.process_frame(frame, FrameDirection.DOWNSTREAM)

        assert all(secret_text not in text for text in injected)

    async def test_no_inject_callback_still_works(self, monkeypatch):
        """inject=None (the default, matching every pre-F3 caller) must
        not raise — the message still sends, no note attempted."""
        from jarvis.bot.speaker_gate import DROP_NOTE_MIN_SCORE

        monkeypatch.delenv(speaker.THRESHOLD_ENV, raising=False)
        state = GateState(turn_id=1)
        state.scores[1] = DROP_NOTE_MIN_SCORE + 0.05
        state.speech_secs[1] = 5.0
        gate, pushed, sent = _make_gate(state, inject=None)

        frame = TranscriptionFrame(text="whatever", user_id="u", timestamp="t")
        await gate.process_frame(frame, FrameDirection.DOWNSTREAM)

        assert pushed == []
        assert sent[0]["near_threshold"] is True


class TestTranscriptGateFailOpen:
    async def test_gate_holds_then_fails_open(self, monkeypatch):
        # Speed the test up without changing the mechanism under test: the
        # hold loop reads speaker.GATE_HOLD_TIMEOUT_S live on every call.
        monkeypatch.setattr(speaker, "GATE_HOLD_TIMEOUT_S", 0.1)
        state = GateState(turn_id=1)
        state.speech_secs[1] = 2.0  # long enough to be judged, if a score arrived
        # Deliberately never populate state.scores[1].
        gate, pushed, sent = _make_gate(state)

        frame = TranscriptionFrame(text="hello there", user_id="u", timestamp="t")
        await gate.process_frame(frame, FrameDirection.DOWNSTREAM)

        # No score ever arrived -> verdict(None, ...) -> "pass" (L5/L9).
        assert pushed == [frame]
        assert sent == []

    async def test_interim_frames_pass_untouched(self):
        state = GateState(turn_id=1)  # no score at all
        gate, pushed, sent = _make_gate(state)

        frame = InterimTranscriptionFrame(text="hel", user_id="u", timestamp="t")
        await gate.process_frame(frame, FrameDirection.DOWNSTREAM)

        assert pushed == [frame]  # forwarded immediately, no hold
        assert sent == []


class TestSpeakerTapMinEmbedGuard:
    def test_tiny_buffer_never_schedules_an_embed(self):
        """Observed live 2026-08-21: near-empty buffers crashed ECAPA's
        padding ("input [1, 80, 1]"). Under MIN_EMBED_SECS the tap must
        record speech_secs but never attempt an embedding."""
        state = GateState(turn_id=3)

        class ExplodingEncoder:
            def embed(self, pcm16, sample_rate):  # pragma: no cover
                raise AssertionError("embed must not be called for tiny buffers")

        tap = SpeakerTap(state, ExplodingEncoder(), profile=object())
        tap._sample_rate = 16000
        # Just under the guard: MIN_EMBED_SECS worth of int16 mono, minus a frame.
        n_bytes = int((MIN_EMBED_SECS - 0.05) * 16000) * 2
        tap._buffer = bytearray(n_bytes)

        tap._schedule_score()  # would raise via ExplodingEncoder if scheduled

        assert state.speech_secs[3] < MIN_EMBED_SECS
        assert 3 not in state.scores  # no score attempt recorded


class TestWindowSlices:
    """F1/F2 (MORTIMER_GATE_V2_AND_MODEL_REQUEST_PLAN.md) — pure slicing
    helper, no audio/model involved."""

    def test_short_buffer_scores_single_window(self):
        sample_rate = 16000
        n_bytes = int(1.0 * sample_rate) * 2  # 1s, well under SCORE_WINDOW_SECS
        slices = _window_slices(n_bytes, sample_rate)
        assert slices == [slice(0, n_bytes)]

    def test_long_buffer_covers_end_and_includes_whole(self):
        sample_rate = 16000
        n_bytes = int(12.0 * sample_rate) * 2  # MAX_BUFFER_SECS-length turn
        slices = _window_slices(n_bytes, sample_rate)
        # Last entry is always the whole buffer.
        assert slices[-1] == slice(0, n_bytes)
        # Every window (all but the last) is bounded by SCORE_WINDOW_SECS
        # worth of bytes and does not exceed the buffer.
        for sl in slices[:-1]:
            assert sl.stop <= n_bytes
            assert (sl.stop - sl.start) <= int(SCORE_WINDOW_SECS * sample_rate) * 2
        # Coverage: the windows reach the end of the buffer.
        assert slices[-2].stop == n_bytes

    def test_never_exceeds_max_score_windows_plus_whole(self):
        sample_rate = 16000
        n_bytes = int(60.0 * sample_rate) * 2  # pathologically long, hypothetically
        slices = _window_slices(n_bytes, sample_rate)
        # MAX_SCORE_WINDOWS sliding windows + 1 whole-buffer entry, at most.
        assert len(slices) <= MAX_SCORE_WINDOWS + 1

    def test_no_window_shorter_than_min_embed_secs(self):
        sample_rate = 16000
        n_bytes = int(12.0 * sample_rate) * 2
        slices = _window_slices(n_bytes, sample_rate)
        min_embed_bytes = int(MIN_EMBED_SECS * sample_rate) * 2
        for sl in slices[:-1]:
            assert (sl.stop - sl.start) >= min_embed_bytes


class TestWindowedScoring:
    """F1/F2: the turn's recorded score is the MAX across all windows
    (including the whole buffer), computed in exactly one to_thread call."""

    async def test_best_window_score_is_recorded(self):
        state = GateState(turn_id=5)
        sample_rate = 16000
        n_bytes = int(12.0 * sample_rate) * 2

        class FakeEncoder:
            def __init__(self):
                self.calls = 0

            def embed(self, pcm16, sample_rate):
                self.calls += 1
                # Every call gets a distinct embedding so cosine varies;
                # rig the profile below so exactly one window/whole-buffer
                # combination scores highest.
                return np.array([len(pcm16)], dtype=np.float32)

        encoder = FakeEncoder()
        # profile chosen so cosine(embedding, profile) == 1.0 only for an
        # embedding whose "length" exactly matches a mid-length window,
        # and lower for the (longer) whole buffer — proving the max comes
        # from windowing, not just from the whole buffer.
        tap = SpeakerTap(state, encoder, profile=np.array([1.0], dtype=np.float32))
        tap._sample_rate = sample_rate
        tap._buffer = bytearray(n_bytes)

        tap._schedule_score(final=True)
        # Let the scheduled task run.
        import asyncio
        await asyncio.sleep(0.05)

        assert encoder.calls > 1  # more than just the whole buffer
        assert state.scores[5] is not None

    async def test_all_windows_scored_in_one_thread_call(self, monkeypatch):
        state = GateState(turn_id=6)
        sample_rate = 16000
        n_bytes = int(12.0 * sample_rate) * 2

        class CountingEncoder:
            def __init__(self):
                self.embed_calls = 0

            def embed(self, pcm16, sample_rate):
                self.embed_calls += 1
                return np.array([0.5], dtype=np.float32)

        encoder = CountingEncoder()
        tap = SpeakerTap(state, encoder, profile=np.array([0.5], dtype=np.float32))
        tap._sample_rate = sample_rate
        tap._buffer = bytearray(n_bytes)

        to_thread_calls = []
        import jarvis.bot.speaker_gate as sg_module

        real_to_thread = sg_module.asyncio.to_thread

        async def counting_to_thread(fn, *args, **kwargs):
            to_thread_calls.append(1)
            return await real_to_thread(fn, *args, **kwargs)

        monkeypatch.setattr(sg_module.asyncio, "to_thread", counting_to_thread)

        tap._schedule_score(final=True)
        import asyncio
        await asyncio.sleep(0.05)

        assert len(to_thread_calls) == 1  # ONE hop regardless of window count
        assert encoder.embed_calls > 1  # but multiple embeddings happened inside it

    async def test_short_mid_turn_checkpoint_unaffected(self):
        """The mid-turn (final=False) checkpoint fires at ~MIN_VERIFY_SECS
        of buffer — short enough that _window_slices returns a single
        whole-buffer entry, so this path is behaviorally unchanged."""
        state = GateState(turn_id=7)
        sample_rate = 16000
        n_bytes = int(speaker.MIN_VERIFY_SECS * sample_rate) * 2

        class FakeEncoder:
            def __init__(self):
                self.calls = 0

            def embed(self, pcm16, sample_rate):
                self.calls += 1
                return np.array([1.0], dtype=np.float32)

        encoder = FakeEncoder()
        tap = SpeakerTap(state, encoder, profile=np.array([1.0], dtype=np.float32))
        tap._sample_rate = sample_rate
        tap._buffer = bytearray(n_bytes)

        tap._schedule_score(final=False)
        import asyncio
        await asyncio.sleep(0.05)

        assert encoder.calls == 1


class TestSpeakerVerifiedTurnStart:
    """The interruption gate (added after the first live session: TV never
    got a transcript through but interrupted Mortimer constantly)."""

    def _make(self, state: GateState) -> tuple:
        strategy = SpeakerVerifiedMinWordsTurnStartStrategy(state, min_words=2)
        triggered = []

        async def fake_trigger():
            triggered.append(True)

        async def fake_reset():
            pass

        strategy.trigger_user_turn_started = fake_trigger
        strategy.trigger_reset_aggregation = fake_reset
        return strategy, triggered

    def test_strategy_tracks_parent_bot_speaking_attr(self):
        # Pins the accepted private-API coupling: the parent must still
        # carry _bot_speaking, or the speaker check silently disappears.
        state = GateState()
        strategy, _ = self._make(state)
        assert hasattr(strategy, "_bot_speaking")

    async def test_quiet_bot_single_word_starts_turn_no_speaker_check(self):
        state = GateState(turn_id=1)  # no score at all
        strategy, triggered = self._make(state)
        strategy._bot_speaking = False

        frame = TranscriptionFrame(text="hello", user_id="u", timestamp="t")
        await strategy._handle_transcription(frame)

        assert triggered == [True]

    async def test_speaking_bot_unknown_voice_cannot_interrupt(self, monkeypatch):
        monkeypatch.delenv(speaker.THRESHOLD_ENV, raising=False)
        state = GateState(turn_id=1)
        state.scores[1] = 0.1  # TV
        strategy, triggered = self._make(state)
        strategy._bot_speaking = True

        frame = TranscriptionFrame(
            text="and now the weather for the weekend", user_id="u", timestamp="t"
        )
        await strategy._handle_transcription(frame)

        assert triggered == []

    async def test_speaking_bot_enrolled_voice_interrupts(self, monkeypatch):
        monkeypatch.delenv(speaker.THRESHOLD_ENV, raising=False)
        state = GateState(turn_id=1)
        state.scores[1] = 0.9  # Larry
        strategy, triggered = self._make(state)
        strategy._bot_speaking = True

        frame = TranscriptionFrame(text="stop for a second", user_id="u", timestamp="t")
        await strategy._handle_transcription(frame)

        assert triggered == [True]

    async def test_speaking_bot_no_score_yet_holds_not_triggers(self):
        state = GateState(turn_id=1)  # score not computed yet
        strategy, triggered = self._make(state)
        strategy._bot_speaking = True

        frame = TranscriptionFrame(text="hold on a moment", user_id="u", timestamp="t")
        await strategy._handle_transcription(frame)

        assert triggered == []  # not yet — next interim rechecks


class TestVerdictWiringConsistency:
    def test_no_profile_gate_always_passes(self):
        # profile_loaded=False mirrors the constructor argument build_pipeline
        # passes when speaker.load_profile() returned None — verdict() must
        # short-circuit to "pass" regardless of any score.
        assert speaker.verdict(0.0, 5.0, profile_loaded=False) == "pass"


# --- build_pipeline wiring guard --------------------------------------------


class _FakeVAD:
    def __init__(self, vad_analyzer):
        self.vad_analyzer = vad_analyzer


class _FakeSTT:
    class Settings:
        def __init__(self, model):
            self.model = model

    def __init__(self, api_key, settings, **kwargs):
        self.api_key = api_key


class _FakeLLM:
    def __init__(self, api_key, base_url, model):
        self.functions = {}

    def register_function(self, name, handler):
        self.functions[name] = handler


class _FakeTTS:
    class Settings:
        def __init__(self, **kwargs):
            pass

    def __init__(self, api_key, settings):
        pass


class _FakePipeline:
    def __init__(self, processors):
        self.processors = list(processors)


class _FakeTransport:
    def input(self):
        return "IN"

    def output(self):
        class Out(str):
            async def send_message(self, frame):
                pass
        return Out("OUT")

    def event_handler(self, name):
        def deco(fn):
            return fn
        return deco


@pytest.fixture
def wiring_runtime(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "speaker_wiring.db"))
    from jarvis.db import run_migrations
    run_migrations()
    import jarvis.bot.pipeline as bp

    settings = SimpleNamespace(
        deepgram_api_key="dg",
        openai_api_key="sk",
        openai_base_url="http://llm",
        openai_model="m",
        elevenlabs_api_key="el",
        jarvis_name="Jarvis",
        jarvis_user_name="Boss",
        jarvis_timezone="America/New_York",
        jarvis_units="imperial",
        jarvis_max_parallel_delegations=3,
    )
    monkeypatch.setattr(bp, "DeepgramFluxSTTService", _FakeSTT)
    monkeypatch.setattr(bp, "OpenAILLMService", _FakeLLM)
    monkeypatch.setattr(bp, "ElevenLabsTTSService", _FakeTTS)
    monkeypatch.setattr(bp, "ElevenLabsTTSSettings", _FakeTTS.Settings)
    monkeypatch.setattr(bp, "Pipeline", _FakePipeline)
    monkeypatch.setattr(bp, "VADProcessor", _FakeVAD)

    from tests.unit.test_orchestrator import FakeSubAgent
    monkeypatch.setattr(
        bp, "load_sub_agents",
        lambda settings, registry: {
            n: FakeSubAgent(n) for n in ("scheduler", "librarian", "analyst", "systems")
        },
    )
    return bp, bp.Runtime(settings=settings, registry=None, session_id="s")


def test_no_profile_disables_gate_not_pipeline(wiring_runtime, monkeypatch):
    bp, runtime = wiring_runtime
    monkeypatch.setenv(speaker.KILL_SWITCH_ENV, "true")
    monkeypatch.setattr(speaker, "load_profile", lambda: None)

    pipeline, _, _, _ = bp.build_pipeline(_FakeTransport(), runtime)

    assert not any(isinstance(p, SpeakerTap) for p in pipeline.processors)
    assert not any(isinstance(p, TranscriptGate) for p in pipeline.processors)


def test_gate_disabled_by_kill_switch_inserts_nothing(wiring_runtime, monkeypatch):
    bp, runtime = wiring_runtime
    monkeypatch.delenv(speaker.KILL_SWITCH_ENV, raising=False)  # default off

    pipeline, _, _, _ = bp.build_pipeline(_FakeTransport(), runtime)

    assert not any(isinstance(p, SpeakerTap) for p in pipeline.processors)
    assert not any(isinstance(p, TranscriptGate) for p in pipeline.processors)


async def test_gate_inject_appends_drop_note_to_real_context(wiring_runtime, monkeypatch):
    """F3 wiring: the TranscriptGate built inside build_pipeline is given
    a REAL closure over the REAL aggregators object (not a fake), and
    calling it actually appends to that context — not just constructed
    and never wired."""
    bp, runtime = wiring_runtime
    monkeypatch.setenv(speaker.KILL_SWITCH_ENV, "true")
    monkeypatch.setattr(speaker, "load_profile", lambda: np.zeros(3, dtype=np.float32))
    monkeypatch.setattr(speaker.Encoder, "load", lambda self: True)

    pipeline, _, aggregators, _ = bp.build_pipeline(_FakeTransport(), runtime)

    gate = next(p for p in pipeline.processors if isinstance(p, TranscriptGate))
    assert gate._inject is not None

    before = len(aggregators.user().context.messages)
    await gate._inject("[system] test drop note")
    after = len(aggregators.user().context.messages)
    assert after == before + 1


def test_gate_active_when_profile_and_encoder_load_succeed(wiring_runtime, monkeypatch):
    bp, runtime = wiring_runtime
    monkeypatch.setenv(speaker.KILL_SWITCH_ENV, "true")
    monkeypatch.setattr(speaker, "load_profile", lambda: np.zeros(3, dtype=np.float32))
    monkeypatch.setattr(speaker.Encoder, "load", lambda self: True)

    pipeline, _, _, _ = bp.build_pipeline(_FakeTransport(), runtime)

    kinds = [type(p).__name__ for p in pipeline.processors]
    assert "SpeakerTap" in kinds
    assert "TranscriptGate" in kinds
    # SpeakerTap after VAD, before STT; TranscriptGate after STT.
    vad_i = next(i for i, p in enumerate(pipeline.processors) if isinstance(p, _FakeVAD))
    tap_i = next(i for i, p in enumerate(pipeline.processors) if isinstance(p, SpeakerTap))
    stt_i = next(i for i, p in enumerate(pipeline.processors) if isinstance(p, _FakeSTT))
    gate_i = next(i for i, p in enumerate(pipeline.processors) if isinstance(p, TranscriptGate))
    assert vad_i < tap_i < stt_i < gate_i
