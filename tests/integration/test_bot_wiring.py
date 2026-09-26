"""Bot pipeline wiring tests (plan Phase 4 Tests).

Constructs the pipeline with mocked transport/STT/LLM and asserts:
- processor order is exactly the locked Phase 4 order,
- delegate_task, set_voice, and remember (reliable-memory plan D6) are the
  functions registered on the LLM service,
- transcript logging writes conversations rows for both roles (user side via
  the D-007 task observer, assistant side via the TranscriptLogger processor).
"""

import asyncio
import logging
import re
from types import SimpleNamespace

import pytest

import jarvis.bot.pipeline as bp
from jarvis.bot.pipeline import Runtime, build_pipeline, connection_greeting_note
from jarvis.bot.transcript_log import TranscriptLogger


class FakeTransport:
    def __init__(self):
        self.sent = []  # app messages sent via output().send_message

    def input(self):
        return "TRANSPORT_INPUT"

    def output(self):
        sent = self.sent

        class Out(str):  # str so processor-order assertions still work
            async def send_message(self, frame):
                sent.append(frame.message)

        return Out("TRANSPORT_OUTPUT")

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


class FakeAnthropicLLM:
    """Mirrors AnthropicLLMService's constructor shape for the Path A
    wiring tests below -- api_key is accepted but unused when a client is
    given (matches the real service, which does `client or
    AsyncAnthropic(api_key=api_key)`)."""

    class Settings:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    def __init__(self, api_key, client, settings):
        self.api_key = api_key
        self.client = client
        self.settings = settings
        self.functions = {}

    def register_function(self, name, handler):
        self.functions[name] = handler


class FakeTTS:
    class Settings:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    def __init__(self, api_key, settings, text_filters=None):
        self.api_key = api_key
        self.settings = settings
        # S9: the real ElevenLabsTTSService takes text_filters (a
        # TTSService kwarg); the fake must accept it or every pipeline
        # build in this file raises TypeError.
        self.text_filters = list(text_filters or [])


class FakePipeline:
    """Captures the processor list in order."""

    def __init__(self, processors):
        self.processors = list(processors)


def test_connection_greeting_keeps_memory_maintenance_silent():
    """Open review rows never become a reconnect-time voice chore.

    The Memory panel and explicit librarian requests remain the inspection and
    correction paths. The connect context must contain only the time-aware
    greeting instruction, so the model cannot turn a stale queue count into a
    spoken request for cleanup.
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo

    note = connection_greeting_note(
        "America/New_York",
        datetime(2026, 9, 18, 14, 7, tzinfo=ZoneInfo("America/New_York")),
    )

    assert note == (
        "[system] The user just connected. Greet them briefly by name; "
        "it is 2:07 PM their time."
    )
    assert "memory" not in note.lower()
    assert "review" not in note.lower()


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
        jarvis_units="imperial",
        jarvis_max_parallel_delegations=3,
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
    # -> TTS -> output -> assistant, plus MORTIMER_VOICE_WORKFLOWS_PLAN.md
    # D5/D6: the voice-workflow injector right before the LLM and the reply
    # guard right after it, so nothing reaches the transcript or TTS unchecked.
    assert kinds == [
        "TRANSPORT_INPUT", "VAD", "STT", "LLMUserAggregator",
        "VoiceWorkflowInjector", "LLM", "ReplyGuard",
        "TRANSCRIPT", "TTS", "TRANSPORT_OUTPUT", "LLMAssistantAggregator",
    ]


def test_websocket_case_puts_the_client_message_processor_right_after_input(runtime, fakes):
    """Native-audio transport plan §3.2 findings: on the WebSocket
    transport client app messages arrive as InputTransportMessageFrame, so
    run_session hands build_pipeline a ClientMessageProcessor and it sits
    directly after transport.input(); the locked order is otherwise
    unchanged. The WebRTC case passes None (the test above)."""
    from jarvis.bot.ws_transport import ClientMessageProcessor

    processor = ClientMessageProcessor()
    pipeline, _llm, _aggregators, _pusher = build_pipeline(
        FakeTransport(), runtime, client_messages=processor)
    assert pipeline.processors[0] == "TRANSPORT_INPUT"
    assert pipeline.processors[1] is processor
    assert isinstance(pipeline.processors[2], FakeVAD)
    assert len(pipeline.processors) == 12   # the order above plus this processor


def test_anthropic_base_url_builds_native_service_with_caching(runtime, fakes, monkeypatch):
    """Phase 1 (Rev 3.2) landing step (iii), task 6: an Anthropic-direct
    base_url with native routing on (the default) builds pipecat's own
    AnthropicLLMService with prompt caching enabled -- not OpenAILLMService.
    AnthropicLLMService is imported lazily inside its branch (same reason
    the Google branch above it is), so it's patched at its real module
    path rather than as a `bp` attribute -- `from pipecat.services.
    anthropic.llm import X` re-reads that module's attribute fresh every
    call to build_pipeline() (verified directly against pytest-monkeypatch
    before relying on it here)."""
    monkeypatch.setattr("pipecat.services.anthropic.llm.AnthropicLLMService", FakeAnthropicLLM)
    runtime.settings.openai_base_url = "https://api.anthropic.com/v1/"
    pipeline, llm, aggregators, pusher = build_pipeline(FakeTransport(), runtime)
    assert isinstance(llm, FakeAnthropicLLM)
    assert llm.settings.kwargs["enable_prompt_caching"] is True
    assert llm.settings.kwargs["model"] == runtime.settings.openai_model
    # The real anthropic.AsyncAnthropic client, built explicitly with the
    # OpenAI-compat "/v1" suffix stripped -- the same bug step (ii) found
    # and fixed in jarvis/anthropic_shim.py, reused here rather than
    # trusting the service's own base_url-less default.
    assert str(llm.client.base_url) == "https://api.anthropic.com"


def test_anthropic_base_url_with_native_off_stays_on_openai_service(runtime, fakes, monkeypatch):
    monkeypatch.setenv("JARVIS_ANTHROPIC_NATIVE", "0")
    runtime.settings.openai_base_url = "https://api.anthropic.com/v1/"
    pipeline, llm, aggregators, pusher = build_pipeline(FakeTransport(), runtime)
    assert isinstance(llm, FakeLLM)


def test_flux_never_interrupts_on_its_own(runtime, fakes, monkeypatch):
    """2026-08-22: should_interrupt must stay False. True made Flux
    broadcast an interruption on every VAD-level StartOfTurn — before any
    transcript or speaker score existed — so the TV kept killing in-flight
    replies while the speaker gate correctly dropped its transcripts.
    Interruption duty belongs solely to the (speaker-verified) user-turn-
    start strategy on the aggregator."""
    captured = {}

    class InterruptCheckingSTT(FakeSTT):
        def __init__(self, api_key, settings, should_interrupt=None):
            super().__init__(api_key, settings)
            captured["should_interrupt"] = should_interrupt

    monkeypatch.setattr(bp, "DeepgramFluxSTTService", InterruptCheckingSTT)
    build_pipeline(FakeTransport(), runtime)
    assert captured["should_interrupt"] is False


def test_memory_context_size_is_logged_at_build(runtime, fakes, caplog):
    """MORTIMER_OPTIMIZATION_PLAN.md Phase 4 Rev 3.4 Stage A2 — the memory
    block is the one part of the cached Supervisor prefix that grows on its
    own, so its size is logged once per pipeline build. Without this, the
    only way to know how close the prefix sits to Haiku 4.5's 4,096-token
    cache floor (below which caching silently stops) is to query the store
    by hand."""
    import logging

    with caplog.at_level(logging.INFO, logger="jarvis.bot.pipeline"):
        build_pipeline(FakeTransport(), runtime)
    line = next(
        (r for r in caplog.records if r.msg.startswith("memory_context_rendered")),
        None,
    )
    assert line is not None, "no memory_context_rendered log line"
    rendered = line.getMessage()
    for field in ("chars=", "approx_tokens=", "facts=",
                  "dropped_tier_cap=", "dropped_char_budget=", "prompt_chars="):
        assert field in rendered
    # prompt_chars is the WHOLE assembled prompt, so it must exceed the
    # memory half it contains — this is what makes the pair readable
    # against the cache floor rather than just a number in a log.
    chars = int(rendered.split("chars=")[1].split()[0])
    prompt_chars = int(rendered.split("prompt_chars=")[1].split()[0])
    assert prompt_chars > chars


def test_six_functions_registered(runtime, fakes):
    # remember (memory plan D6), ui_control (MORTIMER_VOICE_UI_PLAN.md U1),
    # show_commands/clear_clipboard/read_clipboard (HANDOFF_LOOP H3/H4 —
    # the handoff loop: show a command, Larry runs it, read the output back)
    _, llm, _, _ = build_pipeline(FakeTransport(), runtime)
    assert sorted(llm.functions) == [
        "clear_clipboard", "cost_summary", "delegate_task", "list_screens", "read_clipboard",
        "remember", "set_voice", "show_commands", "system_status", "ui_control",
        "view_screen",
    ]
    assert llm.kwargs == {"api_key": "sk", "base_url": "http://llm", "model": "m"}


def test_ui_control_kill_switch_unregisters_tool(runtime, fakes, monkeypatch):
    """U6: JARVIS_UI_CONTROL_ENABLED=false removes the tool from both the
    registered functions and the schema list — the Supervisor cannot call
    what it cannot see."""
    monkeypatch.setenv("JARVIS_UI_CONTROL_ENABLED", "false")
    _, llm, _, _ = build_pipeline(FakeTransport(), runtime)
    assert sorted(llm.functions) == [
        "clear_clipboard", "cost_summary", "delegate_task", "list_screens", "read_clipboard",
        "remember", "set_voice", "show_commands", "system_status", "view_screen",
    ]


def test_status_kill_switch_unregisters_tool(runtime, fakes, monkeypatch):
    """Status spec T2.5 / R9: JARVIS_STATUS_TOOLS_ENABLED=false removes
    system_status from the registered functions, the schema list and the
    prompt addendum — off means absent."""
    from jarvis.prompts import STATUS_ADDENDUM

    monkeypatch.setenv("JARVIS_STATUS_TOOLS_ENABLED", "false")
    _, llm, aggregators, _ = build_pipeline(FakeTransport(), runtime)
    assert sorted(llm.functions) == [
        "clear_clipboard", "cost_summary", "delegate_task", "list_screens", "read_clipboard",
        "remember", "set_voice", "show_commands", "ui_control", "view_screen",
    ]
    assert STATUS_ADDENDUM not in _system_prompt_of(aggregators)


def test_status_tool_ships_with_its_addendum(runtime, fakes, monkeypatch):
    from jarvis.prompts import STATUS_ADDENDUM

    monkeypatch.delenv("JARVIS_STATUS_TOOLS_ENABLED", raising=False)
    _, llm, aggregators, _ = build_pipeline(FakeTransport(), runtime)
    assert "system_status" in llm.functions
    assert STATUS_ADDENDUM in _system_prompt_of(aggregators)


def test_screen_vision_kill_switch_unregisters_tools(runtime, fakes, monkeypatch):
    """V4: JARVIS_SCREEN_ENABLED=false removes view_screen/list_screens
    from both the registered functions and the schema list."""
    monkeypatch.setenv("JARVIS_SCREEN_ENABLED", "false")
    _, llm, _, _ = build_pipeline(FakeTransport(), runtime)
    assert sorted(llm.functions) == [
        "clear_clipboard", "cost_summary", "delegate_task", "read_clipboard", "remember",
        "set_voice", "show_commands", "system_status", "ui_control",
    ]


def _system_prompt_of(aggregators) -> str:
    """The system message the pipeline actually built, however the
    installed pipecat exposes its context."""
    ctx = getattr(aggregators.user(), "context", None) or getattr(
        aggregators, "_context", None)
    messages = ctx.get_messages() if hasattr(ctx, "get_messages") else ctx.messages
    return str(messages[0]["content"])


def test_clipboard_kill_switch_unregisters_the_pair(runtime, fakes, monkeypatch):
    """HANDOFF_LOOP H4.5 — JARVIS_CLIPBOARD_ENABLED=false removes the
    clipboard pair. show_commands SURVIVES: putting a command on screen
    instead of speaking it is useful even with the return channel off."""
    monkeypatch.setenv("JARVIS_CLIPBOARD_ENABLED", "false")
    _, llm, _, _ = build_pipeline(FakeTransport(), runtime)
    assert "clear_clipboard" not in llm.functions
    assert "read_clipboard" not in llm.functions
    assert "show_commands" in llm.functions


def test_the_handoff_addendum_ships_only_with_the_tools(runtime, fakes, monkeypatch):
    """Same rule as UI_CONTROL_ADDENDUM: a prompt describing an
    unregistered tool invites hallucinated calls."""
    from jarvis.prompts import HANDOFF_ADDENDUM

    _, _, aggregators, _ = build_pipeline(FakeTransport(), runtime)
    assert HANDOFF_ADDENDUM in _system_prompt_of(aggregators)

    monkeypatch.setenv("JARVIS_CLIPBOARD_ENABLED", "false")
    _, _, aggregators, _ = build_pipeline(FakeTransport(), runtime)
    assert HANDOFF_ADDENDUM not in _system_prompt_of(aggregators)


async def test_registered_handlers_accept_pipecat_params(runtime, fakes):
    """D-009: pipecat 1.4 invokes register_function handlers with a single
    FunctionCallParams object and expects the result via result_callback —
    not the locked (arguments dict) -> str contract the jarvis handlers use."""
    _, llm, _, _ = build_pipeline(FakeTransport(), runtime)

    delivered = []

    class FakeParams:
        def __init__(self, arguments):
            self.arguments = arguments

        async def result_callback(self, result):
            delivered.append(result)

    await llm.functions["delegate_task"](
        FakeParams({"agent_name": "scheduler", "task": "set alarm"}))
    assert delivered == ["done"]

    # 2026-08-25 — this used to hardcode "rachel". config/voices.yaml is
    # now GENERATED by scripts/sync_voices.py from the live ElevenLabs
    # account, and a re-sync legitimately dropped Rachel (she is not on
    # the account any more), failing a test that was never about that
    # voice. The handler contract is what is under test, so pick a voice
    # the catalog actually declares instead of naming one — a generated
    # file changing its contents must not be able to fail this.
    from jarvis.bot.voice_switch import load_voice_catalog

    delivered.clear()
    catalog = load_voice_catalog()
    voice_id = catalog["default"]
    label = next(v["label"] for v in catalog["voices"] if v["id"] == voice_id)
    await llm.functions["set_voice"](FakeParams({"voice": voice_id}))
    assert delivered and label.split()[0] in delivered[0]


def test_tts_settings_from_voices_yaml(runtime, fakes):
    pipeline, _, _, _ = build_pipeline(FakeTransport(), runtime)
    tts = next(p for p in pipeline.processors if isinstance(p, FakeTTS))
    kw = tts.settings.kwargs
    assert kw["model"] == "eleven_flash_v2_5"
    assert kw["stability"] == 0.5
    assert kw["similarity_boost"] == 0.75
    assert kw["voice"]  # default voice id from voices.yaml
    assert tts.api_key == "el"


def test_tts_has_markdown_filter(runtime, fakes):
    """MORTIMER_SESSION_MISSES_PLAN.md S9 — the binding half of "no
    markdown in speech": VOICE_ADDENDUM asks, this filter enforces."""
    from pipecat.utils.text.markdown_text_filter import MarkdownTextFilter

    pipeline, _, _, _ = build_pipeline(FakeTransport(), runtime)
    tts = next(p for p in pipeline.processors if isinstance(p, FakeTTS))
    assert any(isinstance(f, MarkdownTextFilter) for f in tts.text_filters)


@pytest.mark.asyncio
async def test_markdown_filter_strips_the_emphasis_that_reached_elevenlabs():
    """The exact string from logs/bot.log 2026-09-03 13:44:49, and the
    prose that must survive it unchanged. Runs the REAL filter from the
    deployment venv, so a pipecat behaviour change fails here."""
    from pipecat.utils.text.markdown_text_filter import MarkdownTextFilter

    f = MarkdownTextFilter()
    spoken = await f.filter(
        "**Scheduler** handles time, dates, reminders, and calendar planning."
    )
    assert spoken == "Scheduler handles time, dates, reminders, and calendar planning."
    untouched = "It's 93 degrees — high 96, tonight 73. BMW's 1994 plant near Greer."
    assert await f.filter(untouched) == untouched


def test_stt_model_is_flux(runtime, fakes):
    pipeline, _, _, _ = build_pipeline(FakeTransport(), runtime)
    stt = next(p for p in pipeline.processors if isinstance(p, FakeSTT))
    assert stt.settings.model == "flux-general-en"
    assert stt.api_key == "dg"


async def test_agent_events_pushed_as_app_messages(runtime, fakes, monkeypatch,
                                                   capsys):
    """Plan Phase 6 step 6.3: delegate_start/delegate_done -> {"type":"agent",...}.

    The delegate_* pair owns the UI lifecycle (one status card per
    delegation); agent_start/agent_done are log-only so the UI never sees a
    duplicate working/done pair, and agent_tool feeds the card's progress.
    """
    captured = {}
    real = bp.build_delegate_tool

    def spy(sub_agents, on_event=None, max_parallel=3, **kwargs):
        captured["on_event"] = on_event
        return real(sub_agents, on_event=on_event, max_parallel=max_parallel,
                    **kwargs)

    monkeypatch.setattr(bp, "build_delegate_tool", spy)
    transport = FakeTransport()
    build_pipeline(transport, runtime)
    handler = captured["on_event"]
    assert handler is not None

    handler({"type": "delegate_start", "agent": "scheduler",
             "display_name": "Scheduler", "task": "t"})
    handler({"type": "agent_start", "agent": "scheduler",
             "display_name": "Scheduler", "task": "t"})
    handler({"type": "agent_tool", "agent": "scheduler",
             "display_name": "Scheduler", "tool": "get_time"})
    handler({"type": "agent_done", "agent": "scheduler",
             "display_name": "Scheduler"})
    handler({"type": "delegate_done", "agent": "scheduler",
             "display_name": "Scheduler", "ok": True, "detail": ""})
    await asyncio.sleep(0)  # flush scheduled create_task sends

    # Locked payload shape, sent inside the rtvi-ai server-message envelope
    # (D-005); the log-only agent_start/agent_done produce no UI message.
    payloads = [m["data"] for m in transport.sent]
    for m in transport.sent:
        assert m["label"] == "rtvi-ai"
        assert m["type"] == "server-message"
        assert m["id"]
    assert payloads == [
        {"type": "agent", "name": "scheduler", "display_name": "Scheduler",
         "state": "working", "run_id": None, "task": "t",
         # 2026-08-19 — the Agents tab card header shows the resolved
         # model. Absent from this synthetic event, so it arrives None.
         "model": None, "model_fallback": False,
         "model_unusable": False, "model_unusable_detail": ""},
        {"type": "agent_tool", "name": "scheduler",
         "display_name": "Scheduler", "tool": "get_time"},
        {"type": "agent", "name": "scheduler", "display_name": "Scheduler",
         "state": "done", "ok": True, "detail": ""},
    ]
    # stdout feed (Phase 4 behavior) still intact.
    assert "[AGENT] Scheduler working" in capsys.readouterr().out


def test_dead_on_app_message_handler_removed():
    """MORTIMER_AGENT_TRUST_PLAN.md D19: the transport-level
    @transport.event_handler("on_app_message") handler never fired on the
    installed pipecat 1.4.0 runner stack (DEVIATIONS.md D-005) and has
    been deleted. Regression guard, mirroring the plan's own exact
    precondition command: exactly one "app-message" event registration
    remains (the working connection-level handler), and the dead
    "on_app_message" registration is gone."""
    import inspect

    source = inspect.getsource(bp)
    assert source.count('event_handler("app-message")') == 1
    assert 'event_handler("on_app_message")' not in source
    assert "def on_app_message(" not in source


def test_unwrap_client_message_shapes():
    """D-005: locked raw shape passes through; client-js envelope unwraps."""
    assert bp._unwrap_client_message({"type": "voice/set", "voice": "george"}) == {
        "type": "voice/set", "voice": "george"}
    env = {"id": "1", "label": "rtvi-ai", "type": "client-message",
           "data": {"t": "voice/set", "d": {"voice": "eric"}}}
    assert bp._unwrap_client_message(env) == {"type": "voice/set", "voice": "eric"}
    assert bp._unwrap_client_message({"type": "client-message",
                                      "data": "junk"}) is None
    assert bp._unwrap_client_message("not a dict") is None


def test_wrap_rtvi_envelope():
    wrapped = bp._wrap_rtvi({"type": "voice/current", "voice": "rachel"})
    assert wrapped["label"] == "rtvi-ai"
    assert wrapped["type"] == "server-message"
    assert wrapped["data"] == {"type": "voice/current", "voice": "rachel"}
    assert wrapped["id"]


async def test_transcript_logger_writes_both_roles(fresh_db):
    """User rows come from TranscriptObserver (D-007: the 1.4 user aggregator
    consumes TranscriptionFrame, so the processor never sees it); assistant
    rows still come from the TranscriptLogger processor.

    T4a K3 (gap-closure plan GC1): persistence is gated on the sensitive-turn
    holder, which is FAIL-CLOSED when unset (jarvis/bot/sensitive_turn.py).
    The live sites (cli.py, pipeline.py) set it before any turn; this test
    must too, exactly as test_orchestrator.py's
    test_user_and_assistant_rows_written already does for the orchestrator
    path. Reset via token so the ambient context doesn't leak into whatever
    test runs next in this process."""
    from pipecat.frames.frames import (
        LLMFullResponseEndFrame, LLMTextFrame, TranscriptionFrame,
        UserStoppedSpeakingFrame,
    )
    from pipecat.observers.base_observer import FramePushed
    from pipecat.processors.frame_processor import FrameDirection

    from jarvis.bot.sensitive_turn import SensitiveTurn, current_sensitive_turn
    from jarvis.bot.transcript_log import TranscriptObserver

    token = current_sensitive_turn.set(SensitiveTurn())
    try:
        observer = TranscriptObserver(session_id="s1")
        await observer.on_push_frame(FramePushed(
            source=None, destination=None,
            frame=TranscriptionFrame(
                text="hello jarvis", finalized=True, user_id="u", timestamp="t"),
            direction=FrameDirection.DOWNSTREAM, timestamp=0))
        # D-007/review F13: the user side is buffered and only flushed (armed,
        # printed, persisted) at turn close, so a UserStoppedSpeakingFrame is
        # required after the transcription for the row to land.
        await observer.on_push_frame(FramePushed(
            source=None, destination=None,
            frame=UserStoppedSpeakingFrame(),
            direction=FrameDirection.DOWNSTREAM, timestamp=0))

        logger = TranscriptLogger(session_id="s1")

        async def noop(frame, direction):
            pass
        logger.push_frame = noop  # detach from pipeline plumbing

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
    finally:
        current_sensitive_turn.reset(token)


async def test_observer_logs_first_audio_latency(capsys):
    """Phase 5 first_audio TURN line comes from the D-007 observer: the locked
    order places TranscriptLogger upstream of the TTS service, so
    OutputAudioRawFrame never reaches the processor. The observer sees the
    frame once per downstream hop — the line must still be single-shot."""
    from pipecat.frames.frames import OutputAudioRawFrame, UserStoppedSpeakingFrame
    from pipecat.observers.base_observer import FramePushed
    from pipecat.processors.frame_processor import FrameDirection

    from jarvis.bot.transcript_log import TranscriptObserver

    observer = TranscriptObserver(session_id="s1")

    def pushed(frame):
        return FramePushed(
            source=None, destination=None, frame=frame,
            direction=FrameDirection.DOWNSTREAM, timestamp=0)

    await observer.on_push_frame(pushed(UserStoppedSpeakingFrame()))
    audio = OutputAudioRawFrame(audio=b"\x00\x00", sample_rate=24000, num_channels=1)
    await observer.on_push_frame(pushed(audio))  # TTS -> output transport hop
    await observer.on_push_frame(pushed(audio))  # output transport -> assistant agg hop

    out = capsys.readouterr().out
    lines = [ln for ln in out.splitlines() if "user_end->first_audio" in ln]
    assert len(lines) == 1
    assert lines[0].startswith("TURN user_end->first_audio = ")
    ms = int(lines[0].rsplit("=", 1)[1].strip().removesuffix("ms"))
    assert ms >= 0


# --- session lifecycle -----------------------------------------------------


class HandlerCapturingTransport(FakeTransport):
    """FakeTransport that stores registered event handlers so a test can fire them."""

    def __init__(self):
        super().__init__()
        self.handlers = {}

    def event_handler(self, name):
        def deco(fn):
            self.handlers[name] = fn
            return fn
        return deco


async def test_client_disconnect_ends_task_and_folds_memory(monkeypatch, tmp_path, caplog):
    """Regression: a client disconnect must end the PipelineTask.

    `run_session` blocks on `await runner.run(task)` and does its cleanup in the
    following `finally`: the session's memory fold-in and `watcher.stop()`. The
    on_client_disconnected handler previously only flipped a flag, so the task
    never ended, `runner.run` never returned, and that finally never ran —
    every session lost its memory (until process exit, and then only for the
    last session) and leaked one RemindersWatcher polling task per connection.

    This test models that shape: the fake runner blocks until the task is
    cancelled, so if the handler stops cancelling, the test times out.
    """
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "session.db"))

    settings = SimpleNamespace(
        deepgram_api_key="dg", openai_api_key="sk", openai_base_url="http://llm",
        openai_model="m", elevenlabs_api_key="el", jarvis_name="Jarvis",
        jarvis_user_name="Boss", jarvis_timezone="America/New_York",
        jarvis_units="imperial",
        jarvis_interruption_notice_enabled=True,
        jarvis_late_result_neutralize_enabled=True,
        jarvis_memory_sweep_interval_s=300.0,
    )
    cancelled, folded, watcher_stopped, registry_stopped = [], [], [], []
    memory_watcher_stopped = []

    class FakeTask:
        def __init__(self, pipeline, observers=None, params=None):
            self._ended = asyncio.Event()

        async def cancel(self):
            cancelled.append(True)
            self._ended.set()

        async def wait_ended(self):
            await self._ended.wait()

        def event_handler(self, name):
            # Real PipelineTask API (pipecat BaseObject.event_handler):
            # run_session registers on_pipeline_started for the greeting.
            def register(fn):
                self.__dict__.setdefault("handlers", {})[name] = fn
                return fn
            return register

    class FakeRunner:
        async def run(self, task):
            # Real PipelineRunner.run returns when the task ends; blocking here
            # is what makes the missing cancel() observable as a hang.
            await task.wait_ended()

    class FakeWatcher:
        def __init__(self, *a, **kw):
            pass

        def start(self):
            pass

        async def stop(self):
            watcher_stopped.append(True)

    class FakeMemoryWatcher:
        def __init__(self, *a, **kw):
            pass

        def start(self):
            pass

        async def stop(self):
            memory_watcher_stopped.append(True)

    class FakeRegistry:
        def __init__(self, *a, **kw):
            pass

        async def start(self):
            pass

        async def stop(self):
            registry_stopped.append(True)

    class FakePusher:
        def bind(self, task):
            pass

    class FakeAggregators:
        def user(self):
            return SimpleNamespace()

        def assistant(self):
            return SimpleNamespace()

    async def fake_fold(settings_arg, session_id, **kwargs):
        # Phase 2 kill switch (MORTIMER_OPTIMIZATION_PLAN.md): pipeline.py
        # now passes extract_facts_and_observations=... as a kwarg.
        folded.append(session_id)
        return True

    monkeypatch.setattr(bp, "load_settings", lambda: settings)
    monkeypatch.setattr(bp, "bridge_settings_to_env", lambda s: None)
    monkeypatch.setattr(bp, "run_migrations", lambda *a, **kw: None)
    monkeypatch.setattr(bp, "setup_logging", lambda *a, **kw: None)
    monkeypatch.setattr(bp, "SkillRegistry", FakeRegistry)
    # T3.1: the per-session registry, so registry_stopped stays meaningful.
    monkeypatch.setenv("JARVIS_REGISTRY_SHARED_ENABLED", "false")
    monkeypatch.setattr(
        bp, "load_voice_catalog",
        lambda: {"default": "rachel",
                 "voices": [{"id": "rachel", "label": "Rachel",
                             "elevenlabs_voice_id": "vid"}]},
    )
    monkeypatch.setattr(
        bp, "build_pipeline",
        lambda transport, runtime: (
            FakePipeline([]), FakeLLM("k", "u", "m"), FakeAggregators(), FakePusher()
        ),
    )
    monkeypatch.setattr(bp, "PipelineTask", FakeTask)
    monkeypatch.setattr(bp, "PipelineRunner", FakeRunner)
    monkeypatch.setattr(bp, "RemindersWatcher", FakeWatcher)
    monkeypatch.setattr(bp, "MemorySweepWatcher", FakeMemoryWatcher)
    monkeypatch.setattr(bp, "update_memory_from_session", fake_fold)

    transport = HandlerCapturingTransport()

    async def fire_disconnect():
        for _ in range(500):  # wait for run_session to register its handlers
            if "on_client_disconnected" in transport.handlers:
                break
            await asyncio.sleep(0.01)
        else:
            raise AssertionError("on_client_disconnected was never registered")
        await transport.handlers["on_client_disconnected"](transport, None)

    # Without `await task.cancel()` in the handler this never returns.
    caplog.set_level(logging.INFO, logger=bp.__name__)
    await asyncio.wait_for(
        asyncio.gather(bp.run_session(transport), fire_disconnect()), timeout=10
    )

    assert cancelled == [True], "disconnect handler must cancel the PipelineTask"
    # Status spec P7: one session_disconnect line; WebSocket case, no code.
    lines = [r.getMessage() for r in caplog.records
             if r.getMessage().startswith("session_disconnect ")]
    assert len(lines) == 1, lines
    assert re.fullmatch(r"session_disconnect session=[0-9a-f-]{36} "
                        r"duration_s=\d+\.\d transport=ws close_code=unknown",
                        lines[0]), lines[0]
    assert folded, "memory fold-in did not run for the disconnected session"
    assert watcher_stopped, "RemindersWatcher was not stopped (leaks per connection)"
    assert memory_watcher_stopped, "MemorySweepWatcher was not stopped (leaks per connection)"
    assert registry_stopped, "skill registry was not stopped"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "env_value, expect_constructed",
    [("false", False), ("0", False), ("no", False), (" OFF ", False), (None, True)],
)
async def test_keyhealth_notice_kill_switch(monkeypatch, tmp_path, env_value, expect_constructed):
    """GC5 (gap-closure plan, 2026-09-04): JARVIS_KEYHEALTH_NOTICE_ENABLED
    gates construction of KeyHealthNotice exactly where
    JARVIS_PROGRESS_UPDATES_ENABLED is read. Same disconnect scaffold as
    test_client_disconnect_ends_task_and_folds_memory above."""
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "session.db"))
    if env_value is None:
        monkeypatch.delenv("JARVIS_KEYHEALTH_NOTICE_ENABLED", raising=False)
    else:
        monkeypatch.setenv("JARVIS_KEYHEALTH_NOTICE_ENABLED", env_value)

    settings = SimpleNamespace(
        deepgram_api_key="dg", openai_api_key="sk", openai_base_url="http://llm",
        openai_model="m", elevenlabs_api_key="el", jarvis_name="Jarvis",
        jarvis_user_name="Boss", jarvis_timezone="America/New_York",
        jarvis_units="imperial",
        jarvis_interruption_notice_enabled=True,
        jarvis_late_result_neutralize_enabled=True,
        jarvis_memory_sweep_interval_s=300.0,
    )
    cancelled, folded, constructed = [], [], []

    class FakeTask:
        def __init__(self, pipeline, observers=None, params=None):
            self._ended = asyncio.Event()

        async def cancel(self):
            cancelled.append(True)
            self._ended.set()

        async def wait_ended(self):
            await self._ended.wait()

        def event_handler(self, name):
            # Real PipelineTask API (pipecat BaseObject.event_handler):
            # run_session registers on_pipeline_started for the greeting.
            def register(fn):
                self.__dict__.setdefault("handlers", {})[name] = fn
                return fn
            return register

    class FakeRunner:
        async def run(self, task):
            await task.wait_ended()

    class FakeWatcher:
        def __init__(self, *a, **kw):
            pass

        def start(self):
            pass

        async def stop(self):
            pass

    class FakeMemoryWatcher:
        def __init__(self, *a, **kw):
            pass

        def start(self):
            pass

        async def stop(self):
            pass

    class FakeKeyHealthNotice:
        def __init__(self, *a, **kw):
            constructed.append(True)

        def start(self):
            pass

        async def stop(self):
            pass

    class FakeRegistry:
        def __init__(self, *a, **kw):
            pass

        async def start(self):
            pass

        async def stop(self):
            pass

    class FakePusher:
        def bind(self, task):
            pass

    class FakeAggregators:
        def user(self):
            return SimpleNamespace()

        def assistant(self):
            return SimpleNamespace()

    async def fake_fold(settings_arg, session_id, **kwargs):
        folded.append(session_id)
        return True

    monkeypatch.setattr(bp, "load_settings", lambda: settings)
    monkeypatch.setattr(bp, "bridge_settings_to_env", lambda s: None)
    monkeypatch.setattr(bp, "run_migrations", lambda *a, **kw: None)
    monkeypatch.setattr(bp, "setup_logging", lambda *a, **kw: None)
    monkeypatch.setattr(bp, "SkillRegistry", FakeRegistry)
    # T3.1: the per-session registry, so registry_stopped stays meaningful.
    monkeypatch.setenv("JARVIS_REGISTRY_SHARED_ENABLED", "false")
    monkeypatch.setattr(
        bp, "load_voice_catalog",
        lambda: {"default": "rachel",
                 "voices": [{"id": "rachel", "label": "Rachel",
                             "elevenlabs_voice_id": "vid"}]},
    )
    monkeypatch.setattr(
        bp, "build_pipeline",
        lambda transport, runtime: (
            FakePipeline([]), FakeLLM("k", "u", "m"), FakeAggregators(), FakePusher()
        ),
    )
    monkeypatch.setattr(bp, "PipelineTask", FakeTask)
    monkeypatch.setattr(bp, "PipelineRunner", FakeRunner)
    monkeypatch.setattr(bp, "RemindersWatcher", FakeWatcher)
    monkeypatch.setattr(bp, "MemorySweepWatcher", FakeMemoryWatcher)
    monkeypatch.setattr(bp, "KeyHealthNotice", FakeKeyHealthNotice)
    monkeypatch.setattr(bp, "update_memory_from_session", fake_fold)

    transport = HandlerCapturingTransport()

    async def fire_disconnect():
        for _ in range(500):
            if "on_client_disconnected" in transport.handlers:
                break
            await asyncio.sleep(0.01)
        else:
            raise AssertionError("on_client_disconnected was never registered")
        await transport.handlers["on_client_disconnected"](transport, None)

    await asyncio.wait_for(
        asyncio.gather(bp.run_session(transport), fire_disconnect()), timeout=10
    )

    assert cancelled == [True]
    assert folded
    if expect_constructed:
        assert constructed == [True], "KeyHealthNotice must be constructed when the switch is on"
    else:
        assert constructed == [], "KeyHealthNotice must not be constructed when the switch is off"


@pytest.mark.asyncio
async def test_stt_row_written_at_teardown(monkeypatch, tmp_path):
    """MORTIMER_SESSION_MISSES_PLAN.md S3 — Deepgram Flux emits no usage
    metric, so run_session's teardown bills the session's wall-clock as one
    `stt` ledger row (unit 'seconds'). Same disconnect scaffold as
    test_client_disconnect_ends_task_and_folds_memory; record_call is
    captured rather than written so the assertion is on the row's shape."""
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "session.db"))
    settings = SimpleNamespace(
        deepgram_api_key="dg", openai_api_key="sk", openai_base_url="http://llm",
        openai_model="m", elevenlabs_api_key="el", jarvis_name="Jarvis",
        jarvis_user_name="Boss", jarvis_timezone="America/New_York",
        jarvis_units="imperial",
        jarvis_interruption_notice_enabled=True,
        jarvis_late_result_neutralize_enabled=True,
        jarvis_memory_sweep_interval_s=300.0,
    )
    recorded: list[dict] = []

    class FakeTask:
        def __init__(self, pipeline, observers=None, params=None):
            self._ended = asyncio.Event()

        async def cancel(self):
            self._ended.set()

        async def wait_ended(self):
            await self._ended.wait()

        def event_handler(self, name):
            # Real PipelineTask API (pipecat BaseObject.event_handler):
            # run_session registers on_pipeline_started for the greeting.
            def register(fn):
                self.__dict__.setdefault("handlers", {})[name] = fn
                return fn
            return register

    class FakeRunner:
        async def run(self, task):
            await task.wait_ended()

    class FakeQuiet:
        def __init__(self, *a, **kw):
            pass

        def start(self):
            pass

        async def start_async(self):
            pass

        async def stop(self):
            pass

    class FakeRegistry(FakeQuiet):
        async def start(self):
            pass

    class FakeAggregators:
        def user(self):
            return SimpleNamespace()

        def assistant(self):
            return SimpleNamespace()

    class FakePusher:
        def bind(self, task):
            pass

    async def fake_fold(settings_arg, session_id, **kwargs):
        return True

    async def fake_digest(settings_arg, session_id):
        return False

    monkeypatch.setattr(bp, "load_settings", lambda: settings)
    monkeypatch.setattr(bp, "bridge_settings_to_env", lambda s: None)
    monkeypatch.setattr(bp, "run_migrations", lambda *a, **kw: None)
    monkeypatch.setattr(bp, "setup_logging", lambda *a, **kw: None)
    monkeypatch.setattr(bp, "SkillRegistry", FakeRegistry)
    # T3.1: the per-session registry, so registry_stopped stays meaningful.
    monkeypatch.setenv("JARVIS_REGISTRY_SHARED_ENABLED", "false")
    monkeypatch.setattr(
        bp, "load_voice_catalog",
        lambda: {"default": "rachel",
                 "voices": [{"id": "rachel", "label": "Rachel",
                             "elevenlabs_voice_id": "vid"}]},
    )
    monkeypatch.setattr(
        bp, "build_pipeline",
        lambda transport, runtime: (
            FakePipeline([]), FakeLLM("k", "u", "m"), FakeAggregators(), FakePusher()
        ),
    )
    monkeypatch.setattr(bp, "PipelineTask", FakeTask)
    monkeypatch.setattr(bp, "PipelineRunner", FakeRunner)
    monkeypatch.setattr(bp, "RemindersWatcher", FakeQuiet)
    monkeypatch.setattr(bp, "MemorySweepWatcher", FakeQuiet)
    monkeypatch.setattr(bp, "update_memory_from_session", fake_fold)
    monkeypatch.setattr(bp, "write_session_digest", fake_digest)
    monkeypatch.setattr(bp, "record_call", lambda **kw: recorded.append(kw))

    transport = HandlerCapturingTransport()

    async def fire_disconnect():
        for _ in range(500):
            if "on_client_disconnected" in transport.handlers:
                break
            await asyncio.sleep(0.01)
        else:
            raise AssertionError("on_client_disconnected was never registered")
        await asyncio.sleep(0.05)   # a measurable session, so quantity > 0
        await transport.handlers["on_client_disconnected"](transport, None)

    await asyncio.wait_for(
        asyncio.gather(bp.run_session(transport), fire_disconnect()), timeout=10
    )

    stt = [r for r in recorded if r.get("rung") == "stt"]
    assert len(stt) == 1, recorded
    row = stt[0]
    assert row["provider"] == "deepgram"
    assert row["model"] == "flux-general-en"
    assert row["unit"] == "seconds"
    assert row["quantity"] > 0
    assert row["session_id"]
    # No token kwargs on a voice row.
    assert "input_tokens" not in row


@pytest.mark.asyncio
async def test_shared_registry_survives_session_teardown(monkeypatch, tmp_path):
    """Status spec T3.1 (L11): with JARVIS_REGISTRY_SHARED_ENABLED on (the
    default), two sessions in a row share ONE registry — started by the
    first, reused by the second, stopped by neither. Built through the
    factory, so bp.SkillRegistry is still what gets constructed."""
    from jarvis.skills import shared

    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "session.db"))
    monkeypatch.delenv("JARVIS_REGISTRY_SHARED_ENABLED", raising=False)
    settings = SimpleNamespace(
        deepgram_api_key="dg", openai_api_key="sk", openai_base_url="http://llm",
        openai_model="m", elevenlabs_api_key="el", jarvis_name="Jarvis",
        jarvis_user_name="Boss", jarvis_timezone="America/New_York",
        jarvis_units="imperial",
        jarvis_interruption_notice_enabled=True,
        jarvis_late_result_neutralize_enabled=True,
        jarvis_memory_sweep_interval_s=300.0,
    )
    constructed, started, stopped, seen = [], [], [], []

    class FakeTask:
        def __init__(self, pipeline, observers=None, params=None):
            self._ended = asyncio.Event()

        async def cancel(self):
            self._ended.set()

        async def wait_ended(self):
            await self._ended.wait()

        def event_handler(self, name):
            # Real PipelineTask API (pipecat BaseObject.event_handler):
            # run_session registers on_pipeline_started for the greeting.
            def register(fn):
                self.__dict__.setdefault("handlers", {})[name] = fn
                return fn
            return register

    class FakeRunner:
        async def run(self, task):
            await task.wait_ended()

    class FakeQuiet:
        def __init__(self, *a, **kw):
            pass

        def start(self):
            pass

        async def stop(self):
            pass

    class FakeRegistry:
        def __init__(self, *a, **kw):
            constructed.append(self)

        async def start(self):
            started.append(self)

        async def stop(self):
            stopped.append(self)

    class FakeAggregators:
        def user(self):
            return SimpleNamespace()

        def assistant(self):
            return SimpleNamespace()

    class FakePusher:
        def bind(self, task):
            pass

    async def fake_fold(settings_arg, session_id, **kwargs):
        return True

    async def fake_digest(settings_arg, session_id):
        return False

    def fake_build_pipeline(transport, runtime):
        seen.append(runtime.registry)
        return FakePipeline([]), FakeLLM("k", "u", "m"), FakeAggregators(), FakePusher()

    monkeypatch.setattr(bp, "load_settings", lambda: settings)
    monkeypatch.setattr(bp, "bridge_settings_to_env", lambda s: None)
    monkeypatch.setattr(bp, "run_migrations", lambda *a, **kw: None)
    monkeypatch.setattr(bp, "setup_logging", lambda *a, **kw: None)
    monkeypatch.setattr(bp, "SkillRegistry", FakeRegistry)
    monkeypatch.setattr(
        bp, "load_voice_catalog",
        lambda: {"default": "rachel",
                 "voices": [{"id": "rachel", "label": "Rachel",
                             "elevenlabs_voice_id": "vid"}]},
    )
    monkeypatch.setattr(bp, "build_pipeline", fake_build_pipeline)
    monkeypatch.setattr(bp, "PipelineTask", FakeTask)
    monkeypatch.setattr(bp, "PipelineRunner", FakeRunner)
    monkeypatch.setattr(bp, "RemindersWatcher", FakeQuiet)
    monkeypatch.setattr(bp, "MemorySweepWatcher", FakeQuiet)
    monkeypatch.setattr(bp, "update_memory_from_session", fake_fold)
    monkeypatch.setattr(bp, "write_session_digest", fake_digest)
    monkeypatch.setattr(bp, "record_call", lambda **kw: None)

    async def one_session():
        transport = HandlerCapturingTransport()

        async def fire_disconnect():
            for _ in range(500):
                if "on_client_disconnected" in transport.handlers:
                    break
                await asyncio.sleep(0.01)
            else:
                raise AssertionError("on_client_disconnected was never registered")
            await transport.handlers["on_client_disconnected"](transport, None)

        await asyncio.wait_for(
            asyncio.gather(bp.run_session(transport), fire_disconnect()), timeout=10
        )

    shared._reset_for_tests()
    try:
        await one_session()
        await one_session()
        assert len(constructed) == 1, "one registry per process"
        assert len(started) == 1, "started by the first session only"
        assert stopped == [], "session teardown never stops the shared registry"
        assert seen == [constructed[0], constructed[0]]
    finally:
        shared._reset_for_tests()


@pytest.mark.asyncio
@pytest.mark.parametrize("flag", [True, False])
async def test_late_result_hook_arms_the_neutralizer(monkeypatch, tmp_path, flag):
    """MORTIMER_SESSION_MISSES_PLAN.md S6 — run_session installs
    inject_late_result as the barge-in late-delivery hook: the note it
    appends to the user aggregator is the SAME dict the LateResultNeutralizer
    (in the task's observers) holds, so the observer's in-place rewrite is
    what the aggregator serves next. Same disconnect scaffold as above."""
    from jarvis.bot.late_result import LateResultNeutralizer

    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "session.db"))
    settings = SimpleNamespace(
        deepgram_api_key="dg", openai_api_key="sk", openai_base_url="http://llm",
        openai_model="m", elevenlabs_api_key="el", jarvis_name="Jarvis",
        jarvis_user_name="Boss", jarvis_timezone="America/New_York",
        jarvis_units="imperial",
        jarvis_interruption_notice_enabled=True,
        jarvis_late_result_neutralize_enabled=flag,   # the kill switch, both ways
        jarvis_memory_sweep_interval_s=300.0,
    )
    captured: dict = {}

    class FakeTask:
        def __init__(self, pipeline, observers=None, params=None):
            captured["observers"] = list(observers or [])
            self._ended = asyncio.Event()

        async def cancel(self):
            self._ended.set()

        async def wait_ended(self):
            await self._ended.wait()

        def event_handler(self, name):
            # Real PipelineTask API (pipecat BaseObject.event_handler):
            # run_session registers on_pipeline_started for the greeting.
            def register(fn):
                self.__dict__.setdefault("handlers", {})[name] = fn
                return fn
            return register

    class FakeRunner:
        async def run(self, task):
            await task.wait_ended()

    class FakeQuiet:
        def __init__(self, *a, **kw):
            pass

        def start(self):
            pass

        async def stop(self):
            pass

    class FakeRegistry(FakeQuiet):
        async def start(self):
            pass

    class FakeUserAggregator:
        def __init__(self):
            self.messages: list[dict] = []

        def add_messages(self, messages):
            self.messages.extend(messages)     # keeps the caller's objects, like pipecat

        async def push_context_frame(self, *a, **kw):
            pass

    user_agg = FakeUserAggregator()

    class FakeAggregators:
        def user(self):
            return user_agg

        def assistant(self):
            return SimpleNamespace()

    class FakePusher:
        def bind(self, task):
            pass

    async def fake_fold(settings_arg, session_id, **kwargs):
        return True

    async def fake_digest(settings_arg, session_id):
        return False

    def fake_build_pipeline(transport, runtime):
        captured["runtime"] = runtime
        return FakePipeline([]), FakeLLM("k", "u", "m"), FakeAggregators(), FakePusher()

    monkeypatch.setattr(bp, "load_settings", lambda: settings)
    monkeypatch.setattr(bp, "bridge_settings_to_env", lambda s: None)
    monkeypatch.setattr(bp, "run_migrations", lambda *a, **kw: None)
    monkeypatch.setattr(bp, "setup_logging", lambda *a, **kw: None)
    monkeypatch.setattr(bp, "SkillRegistry", FakeRegistry)
    # T3.1: the per-session registry, so registry_stopped stays meaningful.
    monkeypatch.setenv("JARVIS_REGISTRY_SHARED_ENABLED", "false")
    monkeypatch.setattr(
        bp, "load_voice_catalog",
        lambda: {"default": "rachel",
                 "voices": [{"id": "rachel", "label": "Rachel",
                             "elevenlabs_voice_id": "vid"}]},
    )
    monkeypatch.setattr(bp, "build_pipeline", fake_build_pipeline)
    monkeypatch.setattr(bp, "PipelineTask", FakeTask)
    monkeypatch.setattr(bp, "PipelineRunner", FakeRunner)
    monkeypatch.setattr(bp, "RemindersWatcher", FakeQuiet)
    monkeypatch.setattr(bp, "MemorySweepWatcher", FakeQuiet)
    monkeypatch.setattr(bp, "update_memory_from_session", fake_fold)
    monkeypatch.setattr(bp, "write_session_digest", fake_digest)
    monkeypatch.setattr(bp, "record_call", lambda **kw: None)

    transport = HandlerCapturingTransport()
    note = "[system] Background update: … Relay this to the user once …"

    async def drive():
        for _ in range(500):
            if "on_client_disconnected" in transport.handlers and "runtime" in captured:
                break
            await asyncio.sleep(0.01)
        else:
            raise AssertionError("run_session never installed its handlers")
        fn = captured["runtime"].late_delivery["fn"]
        assert fn.__name__ == "inject_late_result"
        await fn(note)
        await transport.handlers["on_client_disconnected"](transport, None)

    await asyncio.wait_for(asyncio.gather(bp.run_session(transport), drive()), timeout=10)

    neutralizers = [o for o in captured["observers"] if isinstance(o, LateResultNeutralizer)]
    assert len(neutralizers) == 1, "exactly one LateResultNeutralizer in the task's observers"
    assert neutralizers[0].enabled is flag
    assert user_agg.messages[-1] == {"role": "user", "content": note}
    if flag:
        assert neutralizers[0].pending_count == 1
        # The held note is the very object the aggregator has (in-place rewrite works).
        assert neutralizers[0]._pending[0] is user_agg.messages[-1]
    else:
        # Disabled: the note still reaches the aggregator (pre-plan behaviour
        # exactly), and nothing is held to rewrite.
        assert neutralizers[0].pending_count == 0


@pytest.mark.asyncio
async def test_notices_ride_the_greeting_and_a_dead_session_refuses_late_results(
        monkeypatch, tmp_path):
    """Status spec T3.2 (L12), the pipeline half. A pending notice is spoken
    after the greeting, once (take_pending marks it delivered). While the
    session is alive inject_late_result appends and returns True; from the
    first statement of teardown it returns False WITHOUT touching the
    pipeline, which is what sends a late result to the outbox."""
    from jarvis import notices
    from jarvis.db import get_conn, run_migrations

    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "session.db"))
    monkeypatch.delenv("JARVIS_NOTICES_ENABLED", raising=False)
    run_migrations()
    notices.add_notice("late_result", "Developer", "The repo audit finished: 3 findings.")
    settings = SimpleNamespace(
        deepgram_api_key="dg", openai_api_key="sk", openai_base_url="http://llm",
        openai_model="m", elevenlabs_api_key="el", jarvis_name="Jarvis",
        jarvis_user_name="Boss", jarvis_timezone="America/New_York",
        jarvis_units="imperial",
        jarvis_interruption_notice_enabled=True,
        jarvis_late_result_neutralize_enabled=True,
        jarvis_memory_sweep_interval_s=300.0,
    )
    captured: dict = {}
    alive_at_cancel: list[bool] = []
    notices._reset_live_session_for_tests()

    class FakeTask:
        def __init__(self, pipeline, observers=None, params=None):
            self._ended = asyncio.Event()
            self.handlers: dict = {}
            captured["task"] = self

        async def cancel(self):
            alive_at_cancel.append(captured["runtime"].alive)
            self._ended.set()

        async def wait_ended(self):
            await self._ended.wait()

        def event_handler(self, name):
            # Real PipelineTask API (pipecat BaseObject.event_handler):
            # run_session registers on_pipeline_started for the greeting.
            def register(fn):
                self.handlers[name] = fn
                return fn
            return register

    class FakeRunner:
        async def run(self, task):
            await task.wait_ended()

    class FakeQuiet:
        def __init__(self, *a, **kw):
            pass

        def start(self):
            pass

        async def stop(self):
            pass

    class FakeRegistry(FakeQuiet):
        async def start(self):
            pass

    class FakeUserAggregator:
        def __init__(self):
            self.messages: list[dict] = []
            self.pushes = 0

        def add_messages(self, messages):
            self.messages.extend(messages)

        async def push_context_frame(self, *a, **kw):
            self.pushes += 1

    user_agg = FakeUserAggregator()

    class FakeAggregators:
        def user(self):
            return user_agg

        def assistant(self):
            return SimpleNamespace()

    class FakePusher:
        def bind(self, task):
            pass

    async def fake_fold(settings_arg, session_id, **kwargs):
        return True

    async def fake_digest(settings_arg, session_id):
        return False

    def fake_build_pipeline(transport, runtime):
        captured["runtime"] = runtime
        return FakePipeline([]), FakeLLM("k", "u", "m"), FakeAggregators(), FakePusher()

    monkeypatch.setattr(bp, "load_settings", lambda: settings)
    monkeypatch.setattr(bp, "bridge_settings_to_env", lambda s: None)
    monkeypatch.setattr(bp, "run_migrations", lambda *a, **kw: None)
    monkeypatch.setattr(bp, "setup_logging", lambda *a, **kw: None)
    monkeypatch.setattr(bp, "SkillRegistry", FakeRegistry)
    monkeypatch.setenv("JARVIS_REGISTRY_SHARED_ENABLED", "false")
    monkeypatch.setattr(
        bp, "load_voice_catalog",
        lambda: {"default": "rachel",
                 "voices": [{"id": "rachel", "label": "Rachel",
                             "elevenlabs_voice_id": "vid"}]},
    )
    monkeypatch.setattr(bp, "build_pipeline", fake_build_pipeline)
    monkeypatch.setattr(bp, "PipelineTask", FakeTask)
    monkeypatch.setattr(bp, "PipelineRunner", FakeRunner)
    monkeypatch.setattr(bp, "RemindersWatcher", FakeQuiet)
    monkeypatch.setattr(bp, "MemorySweepWatcher", FakeQuiet)
    monkeypatch.setattr(bp, "update_memory_from_session", fake_fold)
    monkeypatch.setattr(bp, "write_session_digest", fake_digest)
    monkeypatch.setattr(bp, "record_call", lambda **kw: None)

    transport = HandlerCapturingTransport()
    outcomes: list[bool] = []

    async def drive():
        for _ in range(500):
            if "on_client_connected" in transport.handlers and "runtime" in captured:
                break
            await asyncio.sleep(0.01)
        else:
            raise AssertionError("run_session never installed its handlers")
        # The greeting waits for the pipeline to start as well as the client
        # (jarvis/bot/connect_greeting.py, main); a real PipelineTask fires this.
        await captured["task"].handlers["on_pipeline_started"](captured["task"], None)
        await transport.handlers["on_client_connected"](transport, None)
        # Review finding 5(b): the connected session is the process's live
        # late-delivery target until it disconnects.
        live_hooks.append(notices.live_session_hook())
        outcomes.append(await captured["runtime"].late_delivery["fn"]("while alive"))
        await transport.handlers["on_client_disconnected"](transport, None)
        live_hooks.append(notices.live_session_hook())

    live_hooks: list = []
    await asyncio.wait_for(asyncio.gather(bp.run_session(transport), drive()), timeout=10)
    # Review finding 5(a): not alive from the top of on_client_disconnected,
    # before the pipeline is cancelled (not only from the teardown finally).
    assert alive_at_cancel == [False]
    assert live_hooks[0] is captured["runtime"].late_delivery["fn"]
    assert live_hooks[1] is None

    greeting = user_agg.messages[0]["content"]
    assert greeting.endswith(
        " While they were away: The repo audit finished: 3 findings. Mention "
        "these in one or two short sentences after greeting.")
    assert outcomes == [True]
    assert user_agg.messages[-1] == {"role": "user", "content": "while alive"}

    runtime = captured["runtime"]
    assert runtime.alive is False
    before = (list(user_agg.messages), user_agg.pushes)
    assert await runtime.late_delivery["fn"]("after teardown") is False
    assert (user_agg.messages, user_agg.pushes) == before, "the dead pipeline was not touched"

    # Delivered once: a second connect finds nothing pending.
    assert notices.take_pending() == []
    with get_conn() as conn:
        row = conn.execute("SELECT delivered_at FROM notices").fetchone()
    assert row["delivered_at"]
