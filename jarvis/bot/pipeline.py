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
import uuid
from dataclasses import dataclass
from typing import Any

from pipecat.frames.frames import OutputTransportMessageUrgentFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineTask

from jarvis.agents.base import load_sub_agents
from jarvis.agents.delegate import build_delegate_tool
from jarvis.bot.transcript_log import TranscriptLogger
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
    {"type": "agent", "name": "<agent>", "state": "working"|"done"}.
    """

    def on_agent_event(event: dict) -> None:
        bot_event_log(event)
        etype = event.get("type")
        if etype not in ("agent_start", "agent_done"):
            return
        message = {
            "type": "agent",
            "name": event.get("agent"),
            "state": "working" if etype == "agent_start" else "done",
        }
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
    llm.register_function("delegate_task", delegate_handler)
    llm.register_function("set_voice", set_voice_handler)
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
        VADProcessor(vad_analyzer=SileroVADAnalyzer()),
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


async def run_session(transport: Any) -> None:
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
        task = PipelineTask(pipeline)
        pusher.bind(task)

        @transport.event_handler("on_client_connected")
        async def on_client_connected(transport: Any, client: Any) -> None:
            print("[session] client connected", flush=True)
            await send_app_message(transport, {
                "type": "voice/catalog",
                "voices": catalog["voices"],
                "current": catalog["default"],
            })
            aggregators.user().add_message({
                "role": "user",
                "content": "[system] The user just connected. "
                           "Greet them briefly by name.",
            })

        voice_state = {"current": catalog["default"]}

        @transport.event_handler("on_app_message")
        async def on_app_message(message: Any, sender: str) -> None:
            msg = _unwrap_client_message(message)
            if msg is None or msg.get("type") != "voice/set":
                return
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

        runner = PipelineRunner()
        await runner.run(task)
    finally:
        await registry.stop()
