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

    def event_handler(self, name):
        def deco(fn):
            return fn
        return deco


class FakeSTT:
    class Settings:
        def __init__(self, model):
            self.model = model

    def __init__(self, api_key, settings):
        self.api_key = api_key
        self.settings = settings


class FakeLLM:
    def __init__(self, api_key, base_url, model):
        self.kwargs = {"api_key": api_key, "base_url": base_url, "model": model}
        self.functions = {}

    def register_function(self, name, handler):
        self.functions[name] = handler


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
        jarvis_name="Jarvis",
        jarvis_user_name="Boss",
        jarvis_timezone="America/New_York",
    )
    return Runtime(settings=settings, registry=None, session_id="test-session")


@pytest.fixture
def fakes(monkeypatch):
    monkeypatch.setattr(bp, "DeepgramFluxSTTService", FakeSTT)
    monkeypatch.setattr(bp, "OpenAILLMService", FakeLLM)
    monkeypatch.setattr(bp, "Pipeline", FakePipeline)
    monkeypatch.setattr(bp, "load_sub_agents",
                        lambda settings, registry: _fake_sub_agents())


def _fake_sub_agents():
    from tests.unit.test_orchestrator import FakeSubAgent
    return {n: FakeSubAgent(n)
            for n in ("scheduler", "librarian", "analyst", "systems")}


def test_pipeline_processor_order_locked(runtime, fakes):
    pipeline, llm, aggregators = build_pipeline(FakeTransport(), runtime)
    kinds = []
    for p in pipeline.processors:
        if isinstance(p, str):
            kinds.append(p)
        elif isinstance(p, FakeSTT):
            kinds.append("STT")
        elif isinstance(p, FakeLLM):
            kinds.append("LLM")
        elif isinstance(p, TranscriptLogger):
            kinds.append("TRANSCRIPT")
        else:  # context aggregators user()/assistant()
            kinds.append(type(p).__name__)
    assert kinds[0] == "TRANSPORT_INPUT"
    assert kinds[1] == "STT"
    assert kinds[3] == "LLM"
    assert kinds[4] == "TRANSCRIPT"
    assert kinds[2] == "LLMUserAggregator"
    assert kinds[5] == "LLMAssistantAggregator"


def test_only_delegate_task_registered(runtime, fakes):
    _, llm, _ = build_pipeline(FakeTransport(), runtime)
    assert list(llm.functions) == ["delegate_task"]
    assert llm.kwargs == {"api_key": "sk", "base_url": "http://llm", "model": "m"}


def test_stt_model_is_flux(runtime, fakes):
    pipeline, _, _ = build_pipeline(FakeTransport(), runtime)
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
