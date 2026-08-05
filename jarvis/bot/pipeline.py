"""Pipeline construction and session runner (plan Phase 4, steps 4.1-4.2).

Locked processor order (Phase 4):
    transport.input()
      -> DeepgramFluxSTTService (flux-general-en)
      -> context_aggregator.user()
      -> OpenAILLMService
      -> TranscriptLogger
      -> context_aggregator.assistant()

Phase 5 inserts ElevenLabsTTSService + transport.output() before
context_aggregator.assistant() and enables audio out + interruptions.

Exactly one function is registered on the LLM: delegate_task (Phase 5 adds
set_voice). run_session() owns everything per-connection so bot.py's entry
shape never changes again.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineTask

from jarvis.agents.base import load_sub_agents
from jarvis.agents.delegate import build_delegate_tool
from jarvis.bot.transcript_log import TranscriptLogger
from jarvis.cli import bridge_settings_to_env
from jarvis.config import Settings, load_settings
from jarvis.db import run_migrations
from jarvis.prompts import SUPERVISOR_PROMPT, VOICE_ADDENDUM, render_agent_catalog
from jarvis.skills.registry import REPO_ROOT, SkillRegistry

# Service imports are module-level names so tests can monkeypatch them.
# D-004: pipecat 1.4.0 class locations/settings classes differ from the
# plan's draft API (Flux under services.deepgram.flux.stt, ToolsSchema
# under adapters.schemas, FunctionSchema instead of raw OpenAI dicts).
from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.services.deepgram.flux.base import DeepgramFluxSTTSettings
from pipecat.services.deepgram.flux.stt import DeepgramFluxSTTService
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


def build_pipeline(transport: Any, runtime: Runtime) -> tuple[Pipeline, Any, Any]:
    """Build the locked pipeline. Returns (pipeline, llm_service, aggregators)."""
    settings = runtime.settings

    sub_agents = load_sub_agents(settings, runtime.registry)
    delegate_schema, delegate_handler = build_delegate_tool(
        sub_agents, on_event=bot_event_log
    )
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
            voice_catalog="(none configured yet)",
        )
        + "\n"
        + VOICE_ADDENDUM
    )

    stt = DeepgramFluxSTTService(
        api_key=settings.deepgram_api_key,
        settings=DeepgramFluxSTTSettings(model="flux-general-en"),
    )
    llm = OpenAILLMService(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        model=settings.openai_model,
    )
    llm.register_function("delegate_task", delegate_handler)

    # D-004: pipecat's universal ToolsSchema wants FunctionSchema objects
    # (converted from the locked OpenAI delegate_task shape), not raw dicts.
    delegate_fn = FunctionSchema(
        name="delegate_task",
        description=delegate_schema["function"]["description"],
        properties=delegate_schema["function"]["parameters"]["properties"],
        required=delegate_schema["function"]["parameters"]["required"],
    )
    context = LLMContext(
        messages=[{"role": "system", "content": system_prompt}],
        tools=ToolsSchema(standard_tools=[delegate_fn]),
    )
    aggregators = LLMContextAggregatorPair(context)
    transcript = TranscriptLogger(session_id=runtime.session_id)

    pipeline = Pipeline([
        transport.input(),
        stt,
        aggregators.user(),
        llm,
        transcript,
        aggregators.assistant(),
    ])
    return pipeline, llm, aggregators


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
        pipeline, _llm, aggregators = build_pipeline(transport, runtime)
        task = PipelineTask(pipeline)

        @transport.event_handler("on_client_connected")
        async def on_client_connected(transport: Any, client: Any) -> None:
            print("[session] client connected", flush=True)
            aggregators.user().add_message({
                "role": "user",
                "content": "[system] The user just connected. "
                           "Greet them briefly by name.",
            })

        runner = PipelineRunner()
        await runner.run(task)
    finally:
        await registry.stop()
