"""Pipeline construction and session runner (plan Phase 4 step 4.2, Phase 5 step 5.1).

Locked processor order (Phase 5):
    transport.input()
      -> VADProcessor(SileroVADAnalyzer)          # D-004: VAD is a processor in pipecat 1.4
      -> DeepgramFluxSTTService (flux-general-en) # should_interrupt=True => interruptions
      -> context_aggregator.user()
      -> OpenAILLMService
      -> TranscriptLogger
      -> ElevenLabsTTSService (eleven_flash_v2_5)
      -> transport.output()
      -> context_aggregator.assistant()

Exactly two functions are registered on the LLM: delegate_task and set_voice.
run_session() owns everything per-connection so bot.py's entry shape never
changes again.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from dataclasses import dataclass
from typing import Any

from pipecat.frames.frames import OutputTransportMessageUrgentFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineTask

from jarvis.agents.base import load_sub_agents
from jarvis.agents.delegate import build_delegate_tool
from jarvis.bot.reminders_watcher import RemindersWatcher
from jarvis.bot.transcript_log import TranscriptLogger, TranscriptObserver
from jarvis.bot.voice_switch import (
    available_list,
    build_set_voice_tool,
    catalog_summary,
    load_voice_catalog,
    resolve_voice,
)
from jarvis.cli import bridge_settings_to_env
from jarvis.config import Settings, load_settings
from jarvis.db import run_migrations
from jarvis.memory import render_memory_context, update_memory_from_session
from jarvis.prompts import (
    SUPERVISOR_PROMPT,
    VOICE_ADDENDUM,
    render_agent_catalog,
)
from jarvis.skills.registry import REPO_ROOT, SkillRegistry

# Service imports are module-level names so tests can monkeypatch them.
# D-004: pipecat 1.4.0 class locations/settings classes differ from the
# plan's draft API (Flux under services.deepgram.flux.stt, ToolsSchema
# under adapters.schemas, FunctionSchema instead of raw OpenAI dicts,
# VAD as VADProcessor, interruptions via Flux should_interrupt).
from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.processors.audio.vad_processor import VADProcessor
from pipecat.services.deepgram.flux.base import DeepgramFluxSTTSettings
from pipecat.services.deepgram.flux.stt import DeepgramFluxSTTService
from pipecat.services.elevenlabs.tts import (
    ElevenLabsTTSService,
    ElevenLabsTTSSettings,
)
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
)

# Cap for the task summary forwarded to the UI in agent "working" messages.
UI_TASK_SUMMARY_CHARS = 120


@dataclass
class Runtime:
    """Per-session resources shared by the pipeline and event handlers."""

    settings: Settings
    registry: SkillRegistry
    session_id: str


def bot_event_log(event: dict) -> None:
    """stdout agent-activity feed (Phase 4; UI feed arrives in Phase 6)."""
    if event.get("type") == "delegate_start":
        print(f"[AGENT] {event['display_name']} working: {event['task']!r}", flush=True)
    elif event.get("type") == "agent_tool":
        print(f"[AGENT] {event['display_name']} calling {event['tool']}…", flush=True)
    elif event.get("type") in ("agent_done", "delegate_done"):
        print(f"[AGENT] {event['display_name']} done", flush=True)


def make_agent_event_handler(transport: Any) -> Any:
    """Plan Phase 6 step 6.3: log agent events AND feed them to the UI.

    on_event callbacks are sync (agents/base.py EventCallback), so the async
    app-message send is scheduled on the running loop. Message shape (locked):
    {"type": "agent", "name": "<agent>", "state": "working"|"done"} —
    "working" messages additionally carry "task": the delegated task text,
    truncated to UI_TASK_SUMMARY_CHARS, so the console can show what the
    specialist is doing (satellite cards).
    """

    def on_agent_event(event: dict) -> None:
        bot_event_log(event)
        etype = event.get("type")
        if etype not in ("agent_start", "agent_done"):
            return
        message: dict[str, Any] = {
            "type": "agent",
            "name": event.get("agent"),
            "state": "working" if etype == "agent_start" else "done",
        }
        if etype == "agent_start":
            task = str(event.get("task", "")).strip()
            if task:
                message["task"] = task[:UI_TASK_SUMMARY_CHARS]
        try:
            asyncio.get_running_loop().create_task(
                send_app_message(transport, message))
        except RuntimeError:
            pass  # no running loop (tests calling the handler directly)

    return on_agent_event


class FramePusher:
    """Indirection so handlers built before the PipelineTask can push frames."""

    def __init__(self) -> None:
        self._task: Any = None

    def bind(self, task: Any) -> None:
        self._task = task

    async def push(self, frame: Any) -> None:
        if self._task is not None:
            await self._task.queue_frame(frame)


def build_pipeline(
    transport: Any, runtime: Runtime, pusher: FramePusher | None = None
) -> tuple[Pipeline, Any, Any, FramePusher]:
    """Build the locked pipeline. Returns (pipeline, llm, aggregators, pusher)."""
    settings = runtime.settings
    pusher = pusher or FramePusher()
    catalog = load_voice_catalog()
    default_voice = next(
        v for v in catalog["voices"] if v["id"] == catalog["default"])

    sub_agents = load_sub_agents(settings, runtime.registry)
    delegate_schema, delegate_handler = build_delegate_tool(
        sub_agents, on_event=make_agent_event_handler(transport)
    )
    set_voice_schema, set_voice_handler = build_set_voice_tool(pusher.push, catalog)

    def adapt_to_pipecat(dict_handler):
        """D-009: pipecat 1.4 register_function handlers receive one
        FunctionCallParams object and deliver results via
        params.result_callback(...); jarvis function handlers keep the locked
        (arguments dict) -> confirmation str contract used by the Supervisor."""

        async def wrapper(params):
            result = await dict_handler(params.arguments)
            await params.result_callback(result)

        return wrapper
    agent_catalog = render_agent_catalog([
        {"name": a.name, "display_name": a.display_name,
         "description": a.description}
        for a in sub_agents.values()
    ])
    system_prompt = (
        SUPERVISOR_PROMPT.format(
            jarvis_name=settings.jarvis_name,
            user_name=settings.jarvis_user_name,
            timezone=settings.jarvis_timezone,
            agent_catalog=agent_catalog,
            voice_catalog=catalog_summary(catalog),
            memory_context=render_memory_context(),  # U2.5 persistent memory
        )
        + "\n"
        + VOICE_ADDENDUM
    )

    stt = DeepgramFluxSTTService(
        api_key=settings.deepgram_api_key,
        settings=DeepgramFluxSTTSettings(model="flux-general-en"),
        should_interrupt=True,  # plan Phase 5: allow_interruptions (D-004)
    )
    llm = OpenAILLMService(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        model=settings.openai_model,
    )
    llm.register_function("delegate_task", adapt_to_pipecat(delegate_handler))
    llm.register_function("set_voice", adapt_to_pipecat(set_voice_handler))
    tts = ElevenLabsTTSService(
        api_key=settings.elevenlabs_api_key,
        settings=ElevenLabsTTSSettings(
            voice=default_voice["elevenlabs_voice_id"],
            model="eleven_flash_v2_5",
            stability=0.5,
            similarity_boost=0.75,
        ),
    )

    def to_function_schema(schema: dict) -> FunctionSchema:
        fn = schema["function"]
        return FunctionSchema(
            name=fn["name"],
            description=fn["description"],
            properties=fn["parameters"]["properties"],
            required=fn["parameters"]["required"],
        )

    context = LLMContext(
        messages=[{"role": "system", "content": system_prompt}],
        tools=ToolsSchema(standard_tools=[
            to_function_schema(delegate_schema),
            to_function_schema(set_voice_schema),
        ]),
    )
    aggregators = LLMContextAggregatorPair(context)
    transcript = TranscriptLogger(session_id=runtime.session_id)

    pipeline = Pipeline([
        transport.input(),
        # stop_secs 2.5 (default 0.2): wiring tuning so a mid-sentence pause
        # (~2 s) does not trigger the local smart-turn analyzer to close the
        # turn early (Phase 4 acceptance item 11; recorded in DEVIATIONS.md
        # D-010). Turn end is decided by pipecat's TurnAnalyzer on VAD stop,
        # so the VAD stop window is the lever — Flux EOT only finalizes
        # transcripts, which accumulate harmlessly mid-turn.
        VADProcessor(vad_analyzer=SileroVADAnalyzer(params=VADParams(stop_secs=2.5))),
        stt,
        aggregators.user(),
        llm,
        transcript,
        tts,
        transport.output(),
        aggregators.assistant(),
    ])
    return pipeline, llm, aggregators, pusher


def _wrap_rtvi(message: dict) -> dict:
    """D-005: client-js 1.13 drops data-channel messages that are not
    rtvi-ai labeled, so app payloads are wrapped in a server-message
    envelope. The payload itself keeps the locked shape."""
    return {
        "id": str(uuid.uuid4()),
        "label": "rtvi-ai",
        "type": "server-message",
        "data": message,
    }


def _unwrap_client_message(message: Any) -> dict | None:
    """D-005: normalize inbound client messages to the locked raw shape.

    Accepts the locked shape ({"type": "voice/set", ...}) verbatim, plus the
    client-js RTVI envelope ({"type": "client-message",
    "data": {"t": <type>, "d": {...}}}) — client-js 1.13 has no raw
    sendAppMessage, its sendClientMessage always wraps.
    """
    if not isinstance(message, dict):
        return None
    if message.get("type") == "client-message":
        data = message.get("data")
        if not isinstance(data, dict):
            return None
        msg_type = data.get("t")
        payload = data.get("d")
        if not isinstance(msg_type, str):
            return None
        return {"type": msg_type, **(payload if isinstance(payload, dict) else {})}
    return message


async def send_app_message(transport: Any, message: dict) -> None:
    """Server->client app message over the WebRTC data channel."""
    await transport.output().send_message(
        OutputTransportMessageUrgentFrame(message=_wrap_rtvi(message)))


async def run_session(transport: Any, webrtc_connection: Any = None) -> None:
    """Build per-connection resources and run the pipeline to completion."""
    settings = load_settings()
    bridge_settings_to_env(settings)
    run_migrations()

    registry = SkillRegistry(REPO_ROOT / "config" / "mcp_servers.yaml")
    await registry.start()
    runtime = Runtime(settings=settings, registry=registry,
                      session_id=str(uuid.uuid4()))
    print(f"[session] {runtime.session_id}", flush=True)

    try:
        catalog = load_voice_catalog()
        pipeline, _llm, aggregators, pusher = build_pipeline(transport, runtime)
        # D-007: user-side transcript logging lives in a task observer because
        # pipecat 1.4's user aggregator consumes TranscriptionFrame; the locked
        # 9-processor order is unchanged.
        observers = [TranscriptObserver(runtime.session_id)]
        if os.environ.get("JARVIS_DEBUG_OBSERVER"):
            # Temporary diagnostic: print every function-call frame hop with
            # timestamps to find where post-result frames stall.
            from pipecat.frames.frames import (
                FunctionCallInProgressFrame,
                FunctionCallResultFrame,
            )
            from pipecat.observers.base_observer import BaseObserver

            class _FnFrameProbe(BaseObserver):
                async def on_push_frame(self, data) -> None:
                    if isinstance(
                        data.frame,
                        (FunctionCallInProgressFrame, FunctionCallResultFrame),
                    ):
                        src = type(data.source).__name__ if data.source else "?"
                        dst = (
                            type(data.destination).__name__
                            if data.destination else "?"
                        )
                        print(
                            f"[FNPROBE] {type(data.frame).__name__} "
                            f"{src}->{dst} dir={data.direction}",
                            flush=True,
                        )

            observers.append(_FnFrameProbe())
        task = PipelineTask(pipeline, observers=observers)
        pusher.bind(task)

        client_connected = {"value": False}

        @transport.event_handler("on_client_connected")
        async def on_client_connected(transport: Any, client: Any) -> None:
            print("[session] client connected", flush=True)
            client_connected["value"] = True
            await send_app_message(transport, {
                "type": "voice/catalog",
                "voices": catalog["voices"],
                "current": catalog["default"],
            })
            # D-008: pipecat 1.4 has add_messages (plural) and requires an
            # explicit push_context_frame() to trigger the LLM run.
            aggregators.user().add_messages([{
                "role": "user",
                "content": "[system] The user just connected. "
                           "Greet them briefly by name.",
            }])
            await aggregators.user().push_context_frame()

        @transport.event_handler("on_client_disconnected")
        async def on_client_disconnected(transport: Any, client: Any) -> None:
            print("[session] client disconnected", flush=True)
            client_connected["value"] = False

        async def inject_context(text: str) -> None:
            # D-008: same 1.4 context-injection pattern as the greeting.
            aggregators.user().add_messages([{"role": "user", "content": text}])
            await aggregators.user().push_context_frame()

        watcher = RemindersWatcher(
            runtime.registry,
            inject=inject_context,
            is_connected=lambda: client_connected["value"],
        )
        watcher.start()

        voice_state = {"current": catalog["default"]}

        async def handle_voice_set(message: Any) -> None:
            msg = _unwrap_client_message(message)
            if msg is None or msg.get("type") != "voice/set":
                return
            print(f"[appmsg] voice/set: {msg.get('voice')}", flush=True)
            voice = resolve_voice(str(msg.get("voice", "")), catalog)
            if voice is not None:
                from pipecat.frames.frames import TTSUpdateSettingsFrame
                voice_state["current"] = voice["id"]
                await pusher.push(TTSUpdateSettingsFrame(
                    settings={"voice": voice["elevenlabs_voice_id"]}))
            # Reply on failure too (unchanged id) so the UI reconciles its
            # optimistic select against server truth.
            await send_app_message(transport, {
                "type": "voice/current", "voice": voice_state["current"]})

        @transport.event_handler("on_app_message")
        async def on_app_message(message: Any, sender: str) -> None:
            await handle_voice_set(message)

        if webrtc_connection is not None:
            # D-005 update: on the installed pipecat 1.4.0 runner stack the
            # transport-level on_app_message event demonstrably does NOT
            # dispatch to handlers registered as above (the message reaches
            # the pipeline as InputTransportMessageFrame — the runner-added
            # RTVIProcessor logs "Ignoring not RTVI message" — but the
            # transport event never fires our handler). The connection-level
            # "app-message" event is the same event the transport itself
            # subscribes to; registering there is the working receive path
            # for both the locked raw shape and the client-js envelope.
            @webrtc_connection.event_handler("app-message")
            async def on_connection_app_message(connection: Any, message: Any) -> None:
                await handle_voice_set(message)

        runner = PipelineRunner()
        try:
            await runner.run(task)
        finally:
            await watcher.stop()
            # U2.5: fold this session into long-term memory. Best-effort,
            # hard-capped — memory work must never delay shutdown.
            try:
                await asyncio.wait_for(
                    update_memory_from_session(settings, runtime.session_id),
                    timeout=30,
                )
            except Exception:  # noqa: BLE001
                pass
    finally:
        await registry.stop()
