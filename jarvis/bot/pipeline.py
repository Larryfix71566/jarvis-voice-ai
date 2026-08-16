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

Three functions are registered on the LLM: delegate_task, set_voice, and
remember (reliable-memory plan D6). run_session() owns everything
per-connection so bot.py's entry shape never changes again.
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from pipecat.frames.frames import OutputTransportMessageUrgentFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineTask

from jarvis.agents.base import load_sub_agents
from jarvis.agents.delegate import build_delegate_tool
from jarvis.bot.display import build_display_payload
from jarvis.bot.interruption import InterruptionNotifier
from jarvis.bot.memory_watcher import MemorySweepWatcher
from jarvis.bot.reminders_watcher import RemindersWatcher
from jarvis.bot.remember_tool import build_remember_tool
from jarvis.bot.transcript_log import TranscriptLogger, TranscriptObserver
from jarvis.bot.ui_control import build_ui_control_tool
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
from jarvis.logging_config import setup_logging
from jarvis.memory import (
    MEMORY_EXTRACTION_TIMEOUT_S,
    render_memory_context,
    update_memory_from_session,
)
from jarvis.prompts import (
    SUPERVISOR_PROMPT,
    UI_CONTROL_ADDENDUM,
    VOICE_ADDENDUM,
    render_agent_catalog,
)
from jarvis.council import prune as prune_council
from jarvis.runlog import prune as prune_runlog
from jarvis.runlog import reconcile_orphaned_runs
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

_logger = logging.getLogger(__name__)


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
    app-message send is scheduled on the running loop. Message shapes:
    {"type": "agent", "name", "display_name", "state": "working",
     "task": <delegated task>} on delegate_start;
    {"type": "agent", "name", "display_name", "state": "done",
     "ok": <bool>, "detail": <failure reason or "">} on delegate_done;
    {"type": "agent_tool", "name", "display_name", "tool"} while a
    specialist calls a tool; and {"type": "display", "display": <payload>}
    when a tool result is display-worthy (see jarvis/bot/display.py).
    The delegate_* pair owns the lifecycle the UI shows (one status card
    per delegation); agent_start/agent_done remain log-only so the UI
    never sees duplicate working/done messages.
    """

    def on_agent_event(event: dict) -> None:
        bot_event_log(event)
        etype = event.get("type")
        if etype == "agent_tool_result":
            payload = build_display_payload(
                agent=str(event.get("agent") or ""),
                display_name=str(event.get("display_name") or ""),
                tool=str(event.get("tool") or ""),
                arguments=event.get("arguments")
                if isinstance(event.get("arguments"), dict) else {},
                result_str=str(event.get("result") or ""),
            )
            if payload is None:
                return  # voice-only tool result — nothing to show
            # MORTIMER_AGENT_TRUST_PLAN.md D18: one INFO line whenever a
            # display payload is actually built, so MORTIMER_SIDE_DRAWER_
            # PLAN.md D36's surface routing (drawer vs. floating window)
            # is confirmable from logs alone, without a browser attached.
            _logger.info(
                "display_payload tool=%s surface=%s agent=%s kind=%s",
                event.get("tool"), payload.get("surface"),
                event.get("agent"), payload.get("kind"),
            )
            message = {"type": "display", "display": payload}
        elif etype == "delegate_start":
            message = {
                "type": "agent",
                "name": event.get("agent"),
                "display_name": event.get("display_name"),
                "state": "working",
                "task": str(event.get("task") or "")[:200],
            }
        elif etype == "delegate_done":
            message = {
                "type": "agent",
                "name": event.get("agent"),
                "display_name": event.get("display_name"),
                "state": "done",
                "ok": bool(event.get("ok", True)),
                "detail": str(event.get("detail") or "")[:300],
            }
        elif etype == "agent_tool":
            message = {
                "type": "agent_tool",
                "name": event.get("agent"),
                "display_name": event.get("display_name"),
                "tool": event.get("tool"),
            }
        else:
            return  # agent_start / agent_done: log-only (lifecycle is delegate_*)
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
        sub_agents,
        on_event=make_agent_event_handler(transport),
        max_parallel=settings.jarvis_max_parallel_delegations,
        session_id=runtime.session_id,
    )
    set_voice_schema, set_voice_handler = build_set_voice_tool(pusher.push, catalog)
    remember_schema, remember_handler = build_remember_tool(runtime.session_id)

    # MORTIMER_VOICE_UI_PLAN.md U1/U6 — voice control of the console's UI
    # chrome. Kill switch read here, at the single registration site (same
    # env-first pattern as the council's): false = the tool is not
    # registered and not in the schema list, so the Supervisor cannot call
    # what it cannot see, and the prompt addendum is omitted to match.
    ui_control_enabled = os.environ.get(
        "JARVIS_UI_CONTROL_ENABLED", ""
    ).strip().lower() not in ("false", "0", "no")

    async def _send_ui_message(message: dict) -> None:
        await send_app_message(transport, message)

    ui_control_schema, ui_control_handler = build_ui_control_tool(_send_ui_message)

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
        # U5/U6: the addendum ships only when the tool does — a prompt
        # describing an unregistered tool would invite hallucinated calls.
        + ("\n" + UI_CONTROL_ADDENDUM if ui_control_enabled else "")
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
    llm.register_function("remember", adapt_to_pipecat(remember_handler))
    if ui_control_enabled:
        llm.register_function("ui_control", adapt_to_pipecat(ui_control_handler))
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

    standard_tools = [
        to_function_schema(delegate_schema),
        to_function_schema(set_voice_schema),
        to_function_schema(remember_schema),
    ]
    if ui_control_enabled:
        standard_tools.append(to_function_schema(ui_control_schema))
    context = LLMContext(
        messages=[{"role": "system", "content": system_prompt}],
        tools=ToolsSchema(standard_tools=standard_tools),
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
    # Enable INFO root logging so registry/subagent lifecycle lines
    # (mcp_server_started, subagent_done, turn_complete) reach logs/bot.log.
    setup_logging()

    # Run-logging plan D10/§5.8: retention pruning runs once at startup —
    # outside the latency-critical per-turn path, guaranteed to happen
    # regularly, no scheduler needed. Best-effort; a failure here must
    # never block the bot from starting.
    try:
        prune_counts = prune_runlog(settings.jarvis_runlog_retention_days)
        _logger.info(
            "runlog_prune runs_deleted=%d dirs_deleted=%d",
            prune_counts["runs_deleted"], prune_counts["dirs_deleted"],
        )
    except Exception as exc:  # noqa: BLE001 — must never block startup
        _logger.warning("runlog_prune_failed error=%s", exc)

    # MORTIMER_LLM_COUNCIL_V2_PLAN.md V11: council retention pruning, same
    # startup moment and best-effort shape as the runlog prune above.
    try:
        council_prune_counts = prune_council(settings.jarvis_council_retention_days)
        _logger.info(
            "council_prune rounds_deleted=%d dirs_deleted=%d",
            council_prune_counts["rounds_deleted"], council_prune_counts["dirs_deleted"],
        )
    except Exception as exc:  # noqa: BLE001 — must never block startup
        _logger.warning("council_prune_failed error=%s", exc)

    # MORTIMER_AGENT_TRUST_PLAN.md D16: reconcile orphaned runs at the same
    # startup moment as the retention prune above — nothing is `running`
    # in this process yet, so any row still marked `running` from a
    # previous, now-dead process is definitionally orphaned. Best-effort,
    # same as the prune call: must never block the bot from starting.
    try:
        orphaned_count = reconcile_orphaned_runs()
        if orphaned_count:
            _logger.info("runlog_reconcile_orphaned count=%d", orphaned_count)
    except Exception as exc:  # noqa: BLE001 — must never block startup
        _logger.warning("runlog_reconcile_orphaned_failed error=%s", exc)

    registry = SkillRegistry(REPO_ROOT / "config" / "mcp_servers.yaml")
    await registry.start()
    runtime = Runtime(settings=settings, registry=registry,
                      session_id=str(uuid.uuid4()))
    print(f"[session] {runtime.session_id}", flush=True)

    try:
        catalog = load_voice_catalog()
        pipeline, _llm, aggregators, pusher = build_pipeline(transport, runtime)
        async def inject_silent(text: str) -> None:
            # Phase 3: interruption notice. Unlike inject_context (greeting,
            # reminders), this does NOT call push_context_frame() — it only
            # appends to the shared context so the note surfaces naturally on
            # the next real user turn instead of triggering an immediate,
            # unprompted spoken reply.
            aggregators.user().add_messages([{"role": "user", "content": text}])

        # D-007: user-side transcript logging lives in a task observer because
        # pipecat 1.4's user aggregator consumes TranscriptionFrame; the locked
        # 9-processor order is unchanged. InterruptionNotifier is a task
        # observer for the same reason: BotStartedSpeakingFrame/
        # BotStoppedSpeakingFrame are born downstream of the TTS service.
        observers = [
            TranscriptObserver(runtime.session_id),
            InterruptionNotifier(
                inject_silent,
                enabled=settings.jarvis_interruption_notice_enabled,
            ),
        ]
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
            # Include the user's local time: the model has no clock, and a
            # blind greeting guesses the wrong time of day.
            now_local = datetime.now(ZoneInfo(settings.jarvis_timezone))
            greeting_time = now_local.strftime("%I:%M %p").lstrip("0")
            aggregators.user().add_messages([{
                "role": "user",
                "content": "[system] The user just connected. Greet them "
                           f"briefly by name; it is {greeting_time} their time.",
            }])
            await aggregators.user().push_context_frame()

        @transport.event_handler("on_client_disconnected")
        async def on_client_disconnected(transport: Any, client: Any) -> None:
            print("[session] client disconnected", flush=True)
            client_connected["value"] = False
            # End the pipeline task so `await runner.run(task)` returns and the
            # finally block below actually runs. Without this the task blocks
            # forever after the client goes away: the session's memory fold-in
            # never happens (facts/observations are lost until process exit,
            # and only for the last session) and RemindersWatcher leaks one
            # polling task per connection. One PipelineTask is built per
            # WebRTC connection (jarvis/bot/bot.py builds a fresh transport
            # and calls run_session per connection), so cancelling here ends
            # only this session — a reconnect gets a new pipeline.
            await task.cancel()

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

        # Reliable-memory plan D2: periodic mid-session fold-in, so an
        # unclean disconnect loses at most one sweep interval instead of
        # everything discussed. The end-of-session call below remains — it
        # is the last sweep, covering anything since the watcher's last tick.
        memory_watcher = MemorySweepWatcher(
            settings, runtime.session_id, settings.jarvis_memory_sweep_interval_s,
        )
        memory_watcher.start()

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

        async def handle_ui_noop(message: Any) -> None:
            """MORTIMER_VOICE_UI_PLAN.md U2 — the hybrid feedback's spoken
            half. When a ui_control command changed nothing client-side
            (drawer already open, wake sidecar unavailable), the client
            sends {"type": "ui/noop", "reason": "<sentence>"} and the bot
            speaks the reason VERBATIM via TTSSpeakFrame — deliberately
            NOT through the LLM: the tool call already returned "ok" and
            the Supervisor's turn is over by the time the no-op is
            detected, so canned TTS is immediate, deterministic, and
            costs no tokens. No LLM involvement also means this path can
            never trigger further tool calls (no feedback loop)."""
            msg = _unwrap_client_message(message)
            if msg is None or msg.get("type") != "ui/noop":
                return
            reason = str(msg.get("reason", "")).strip()
            if not reason or len(reason) > 200:
                return
            print(f"[appmsg] ui/noop: {reason}", flush=True)
            from pipecat.frames.frames import TTSSpeakFrame
            await pusher.push(TTSSpeakFrame(text=reason))

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
            #
            # MORTIMER_AGENT_TRUST_PLAN.md D19: the dead transport-level
            # on_app_message handler (registered via @transport's own
            # event_handler decorator) that used to sit above this comment
            # never fired, per the D-005 note above, and has been removed.
            # Its removal was gated on the plan's exact precondition —
            # grepping this file for the connection-level registration
            # immediately below and confirming it was the ONLY match —
            # before deleting anything.
            @webrtc_connection.event_handler("app-message")
            async def on_connection_app_message(connection: Any, message: Any) -> None:
                await handle_voice_set(message)
                await handle_ui_noop(message)

        runner = PipelineRunner()
        try:
            await runner.run(task)
        finally:
            await watcher.stop()
            await memory_watcher.stop()
            # U2.5: fold this session into long-term memory. Best-effort,
            # hard-capped — memory work must never delay shutdown.
            #
            # Reliable-memory plan D1: the only failure this outer except can
            # actually catch is asyncio.TimeoutError from the wait_for below
            # (update_memory_from_session already catches and logs every
            # internal failure itself). Previously that specific case was
            # swallowed with zero log line, making it impossible to tell from
            # the logs whether a session's memory fold-in happened, timed
            # out, or errored.
            try:
                await asyncio.wait_for(
                    update_memory_from_session(settings, runtime.session_id),
                    timeout=MEMORY_EXTRACTION_TIMEOUT_S,
                )
            except asyncio.TimeoutError:
                _logger.warning(
                    "memory_extraction_timeout session=%s", runtime.session_id
                )
            except Exception:  # noqa: BLE001 — memory must never break shutdown
                _logger.exception(
                    "memory_extraction_failed session=%s", runtime.session_id
                )
    finally:
        await registry.stop()
