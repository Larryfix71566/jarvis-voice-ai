"""Bot pipeline wiring tests (plan Phase 4 Tests).

Constructs the pipeline with mocked transport/STT/LLM and asserts:
- processor order is exactly the locked Phase 4 order,
- delegate_task is the one function registered on the LLM service,
- TranscriptLogger writes conversations rows for both roles.
"""

from types import SimpleNamespace

import pytest

import jarvis.bot.pipeline as bp
from jarvis.bot.pipeline import Runtime, build_pipeline
from jarvis.bot.transcript_log import TranscriptLogger


class FakeTransport:
    def input(self):
        return "TRANSPORT_INPUT"

    def output(self):
        return "TRANSPORT_OUTPUT"

    def event_handler(self, name):
        def deco(fn):
            return fn
        return deco


class FakeSTT:
    class Settings:
        def __init__(self, model):
            self.model = model

    def __init__(self, api_key, settings, **kwargs):
        self.api_key = api_key
        self.settings = settings


class FakeLLM:
    def __init__(self, api_key, base_url, model):
        self.kwargs = {"api_key": api_key, "base_url": base_url, "model": model}
        self.functions = {}

    def register_function(self, name, handler):
        self.functions[name] = handler


class FakeTTS:
    class Settings:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    def __init__(self, api_key, settings):
        self.api_key = api_key
        self.settings = settings


class FakePipeline:
    """Captures the processor list in order."""

    def __init__(self, processors):
        self.processors = list(processors)


@pytest.fixture
def runtime(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "wiring.db"))
    from jarvis.db import run_migrations
    run_migrations()
    settings = SimpleNamespace(
        deepgram_api_key="dg",
        openai_api_key="sk",
        openai_base_url="http://llm",
        openai_model="m",
        elevenlabs_api_key="el",
        jarvis_name="Jarvis",
        jarvis_user_name="Boss",
        jarvis_timezone="America/New_York",
    )
    return Runtime(settings=settings, registry=None, session_id="test-session")


@pytest.fixture
def fakes(monkeypatch):
    monkeypatch.setattr(bp, "DeepgramFluxSTTService", FakeSTT)
    monkeypatch.setattr(bp, "OpenAILLMService", FakeLLM)
    monkeypatch.setattr(bp, "ElevenLabsTTSService", FakeTTS)
    monkeypatch.setattr(bp, "ElevenLabsTTSSettings", FakeTTS.Settings)
    monkeypatch.setattr(bp, "Pipeline", FakePipeline)
    monkeypatch.setattr(bp, "VADProcessor", FakeVAD)
    monkeypatch.setattr(bp, "load_sub_agents",
                        lambda settings, registry: _fake_sub_agents())


class FakeVAD:
    def __init__(self, vad_analyzer):
        self.vad_analyzer = vad_analyzer


def _fake_sub_agents():
    from tests.unit.test_orchestrator import FakeSubAgent
    return {n: FakeSubAgent(n)
            for n in ("scheduler", "librarian", "analyst", "systems")}


def test_pipeline_processor_order_locked(runtime, fakes):
    pipeline, llm, aggregators, pusher = build_pipeline(FakeTransport(), runtime)
    kinds = []
    for p in pipeline.processors:
        if isinstance(p, str):
            kinds.append(p)
        elif isinstance(p, FakeVAD):
            kinds.append("VAD")
        elif isinstance(p, FakeSTT):
            kinds.append("STT")
        elif isinstance(p, FakeLLM):
            kinds.append("LLM")
        elif isinstance(p, TranscriptLogger):
            kinds.append("TRANSCRIPT")
        elif isinstance(p, FakeTTS):
            kinds.append("TTS")
        else:  # context aggregators user()/assistant()
            kinds.append(type(p).__name__)
    # Locked Phase 5 order: input -> VAD -> STT -> user -> LLM -> transcript
    # -> TTS -> output -> assistant
    assert kinds == [
        "TRANSPORT_INPUT", "VAD", "STT", "LLMUserAggregator", "LLM",
        "TRANSCRIPT", "TTS", "TRANSPORT_OUTPUT", "LLMAssistantAggregator",
    ]


def test_interruptions_enabled_on_flux(runtime, fakes, monkeypatch):
    captured = {}

    class InterruptCheckingSTT(FakeSTT):
        def __init__(self, api_key, settings, should_interrupt=None):
            super().__init__(api_key, settings)
            captured["should_interrupt"] = should_interrupt

    monkeypatch.setattr(bp, "DeepgramFluxSTTService", InterruptCheckingSTT)
    build_pipeline(FakeTransport(), runtime)
    assert captured["should_interrupt"] is True


def test_two_functions_registered(runtime, fakes):
    _, llm, _, _ = build_pipeline(FakeTransport(), runtime)
    assert sorted(llm.functions) == ["delegate_task", "set_voice"]
    assert llm.kwargs == {"api_key": "sk", "base_url": "http://llm", "model": "m"}


def test_tts_settings_from_voices_yaml(runtime, fakes):
    pipeline, _, _, _ = build_pipeline(FakeTransport(), runtime)
    tts = next(p for p in pipeline.processors if isinstance(p, FakeTTS))
    kw = tts.settings.kwargs
    assert kw["model"] == "eleven_flash_v2_5"
    assert kw["stability"] == 0.5
    assert kw["similarity_boost"] == 0.75
    assert kw["voice"]  # default voice id from voices.yaml
    assert tts.api_key == "el"


def test_stt_model_is_flux(runtime, fakes):
    pipeline, _, _, _ = build_pipeline(FakeTransport(), runtime)
    stt = next(p for p in pipeline.processors if isinstance(p, FakeSTT))
    assert stt.settings.model == "flux-general-en"
    assert stt.api_key == "dg"


async def test_transcript_logger_writes_both_roles(fresh_db):
    from pipecat.frames.frames import LLMFullResponseEndFrame, LLMTextFrame, TranscriptionFrame

    logger = TranscriptLogger(session_id="s1")

    async def noop(frame, direction):
        pass
    logger.push_frame = noop  # detach from pipeline plumbing

    await logger.process_frame(TranscriptionFrame(
        text="hello jarvis", finalized=True, user_id="u", timestamp="t"), None)
    await logger.process_frame(LLMTextFrame(text="Good "), None)
    await logger.process_frame(LLMTextFrame(text="afternoon."), None)
    await logger.process_frame(LLMFullResponseEndFrame(), None)

    from jarvis.db import get_conn
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT role, content FROM conversations WHERE session_id='s1' ORDER BY id"
        ).fetchall()
    assert [(r["role"], r["content"]) for r in rows] == [
        ("user", "hello jarvis"),
        ("assistant", "Good afternoon."),
    ]
