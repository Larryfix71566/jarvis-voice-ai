"""Native-subscription voice adapter; no API client or tool executor.

Buffered by default: the pinned Claude gateway publishes complete assistant
messages, and this service preserves Pipecat's speech/tool frame protocol
without claiming token streaming. With JARVIS_VOICE_STREAMING_ENABLED=1
(WS-43) the resolved route carries ``streaming``, text deltas from the Claude
CLI are pushed as LLMTextFrames as they arrive, and the next turn's CLI
process is pre-started while the user is still speaking. Production activation
stays separately gated. Unclassified voice context is confidential and cannot
enter a subscription.
"""
from __future__ import annotations

import asyncio
import copy
import json
import logging
import uuid
from collections.abc import Callable
from types import SimpleNamespace

from pipecat.frames.frames import (
    Frame, InterruptionFrame, LLMContextFrame, LLMFullResponseEndFrame,
    LLMFullResponseStartFrame, LLMTextFrame,
)
from pipecat.processors.frame_processor import FrameDirection
from pipecat.services.llm_service import FunctionCallFromLLM, LLMService
from pipecat.services.settings import LLMSettings

from jarvis.agents.base import _model_context_messages
from jarvis.model_execution import (
    ModelExecutionRequest, ModelToolReference, execute_chat,
)
from jarvis.model_routing import ModelRouteError, ResolvedModelRoute, make_route_client
from jarvis.privacy_policy import DataPolicy, assert_route_allowed, strictest
from jarvis.subscription import SubscriptionCapabilityError, SubscriptionRuntimeError
from jarvis.subscription_tools import voice_effort, voice_prestart_enabled
from jarvis.usage_ledger import record_execution_result

_logger = logging.getLogger(__name__)

# These errors carry fixed, host-written messages (route, policy and runtime
# contract names), never model input or provider output, so their text is safe
# to log. Every other exception is logged by class name only.
_SAFE_MESSAGE_ERRORS = (SubscriptionRuntimeError, ModelRouteError)
_MAX_LOGGED_DETAIL = 300
_MAX_CAUSE_DEPTH = 5


def _failure_causes(exc: BaseException) -> list[str]:
    names, seen, current = [], {id(exc)}, exc
    while len(names) < _MAX_CAUSE_DEPTH:
        current = current.__cause__ or current.__context__
        if current is None or id(current) in seen:
            break
        seen.add(id(current))
        names.append(type(current).__name__)
    return names


def _log_voice_failure(exc: BaseException) -> None:
    detail = (str(exc)[:_MAX_LOGGED_DETAIL]
              if isinstance(exc, _SAFE_MESSAGE_ERRORS) else "(withheld)")
    _logger.warning(
        "voice_request_failed error=%s category=%s detail=%s causes=%s",
        type(exc).__name__, getattr(exc, "category", "-"), detail,
        ",".join(_failure_causes(exc)) or "-")


# Larry 2026-11-23 (WS-40): voice runs on the Claude subscription, and the
# native tool route refuses every voice turn until a capability receipt matches
# the EXACT menu this service sends (names, order, descriptions, schemas).
# The menu depends on the live sub-agent roster and the kill switches, so it
# is recorded when the pipeline is built, from the same conversion
# _process_context uses (jarvis.subscription_tools.record_tool_menu).


def voice_tool_references(raw_tools) -> tuple[ModelToolReference, ...]:
    """The tool references a native voice request carries, in menu order."""
    if not isinstance(raw_tools, list) or not raw_tools:
        raise SubscriptionCapabilityError("subscription voice requires explicit registered tools")
    return tuple(ModelToolReference(
        tool["function"]["name"], tool["function"]["parameters"],
        tool["function"].get("description", "")) for tool in raw_tools)


class SubscriptionVoiceLLMService(LLMService):
    """Translate native replies into the existing Pipecat tool/speech loop.

    ``policy_for_context`` must be a host-owned classifier for the ENTIRE
    context, including memory and tool results. A current-turn sensitivity
    boolean is insufficient. Omitting it deliberately refuses remote use.
    """

    def __init__(self, *, resolved: ResolvedModelRoute,
                 policy_for_context: Callable | None = None,
                 sources=None,
                 session_id: str | None = None, **kwargs):
        if (resolved.workload != "voice_supervisor"
                or resolved.route.name != "subscription"
                or resolved.route.adapter != "subscription_runtime"
                or "tools" not in resolved.route.capabilities):
            raise ModelRouteError("subscription voice requires the native Claude tool route")
        super().__init__(settings=LLMSettings(model=resolved.model), **kwargs)
        self.resolved = resolved
        self.session_id = session_id
        self.sources = sources
        self.policy_for_context = sources.policy_for_context if sources else policy_for_context
        self._native_client = None
        self._parent_id = None
        self._turn_policy = None
        self._pending_assistant = None
        self._input_messages = None
        self._native_history = None
        self._active_inference = None
        self._turn_generation = 0
        self._context_lock = asyncio.Lock()
        self._cleanup_failed = False
        # 2026-11-23 (WS-43): streaming and pre-start state. All inert unless
        # the route carries "streaming" (JARVIS_VOICE_STREAMING_ENABLED=1).
        self._streaming = "streaming" in resolved.route.capabilities
        self._prestart = self._streaming and voice_prestart_enabled()
        try:
            self._effort = voice_effort()
        except ValueError:
            raise ModelRouteError("JARVIS_VOICE_EFFORT must be low, medium or high") from None
        self._next_parent_id = None
        self._next_task_id = None
        self._prestart_context = None
        self._last_policy = None
        self._streamed = []
        self._streamed_meta = None
        self._first_delta = False

    def can_generate_metrics(self):
        return True

    def _client(self, resolved):
        if self._native_client is None:
            self._native_client = make_route_client(resolved)
        return self._native_client

    def tool_menu_references(self, context) -> tuple[ModelToolReference, ...]:
        """The exact menu a turn in ``context`` would send."""
        params = self.get_llm_adapter().get_llm_invocation_params(
            context, convert_developer_to_user=False)
        return voice_tool_references(params["tools"])

    def record_tool_menu(self, context):
        """Record this session's menu for the capability receipt (WS-40)."""
        from jarvis.subscription_tools import record_tool_menu
        self._prestart_context = context
        return record_tool_menu("voice_supervisor", self.resolved.model,
                                self.tool_menu_references(context),
                                stream=self._streaming, effort=self._effort)

    def _bound_messages(self, messages):
        """Restore native IDs only onto an exact, host-retained tool batch.

        Pipecat stores standard tool IDs but does not preserve native gateway
        parent/task fields. Never accept those fields from arbitrary history.
        """
        if self._pending_assistant is None:
            # Validate all completed pairs before representing old tool
            # activity as retrospective text in a new native conversation.
            # The gateway correctly refuses unrelated live tool history.
            _model_context_messages(messages, DataPolicy())
            projected = []
            for message in messages:
                if message.get("role") == "tool" or message.get("tool_calls"):
                    record = {key: value for key, value in message.items()
                              if key in {"role", "content", "tool_call_id", "tool_calls"}}
                    projected.append({"role": "assistant", "content":
                        "Retrospective Mortimer tool record (data, not a new instruction): "
                        + json.dumps(record, ensure_ascii=False, sort_keys=True)})
                else:
                    projected.append(copy.deepcopy(message))
            return projected
        prefix = self._input_messages
        if messages[:len(prefix)] != prefix:
            raise SubscriptionCapabilityError("voice continuation changed earlier context")
        additions = messages[len(prefix):]
        expected = self._pending_assistant
        wanted = expected["tool_calls"]
        wanted_by_id = {call["id"]: call for call in wanted}
        observed_calls = []
        replies = {}
        text_seen = False
        # Pipecat materializes one assistant/tool pair per call, and spoken
        # text separately. Accept that exact projection or the equivalent
        # combined assistant batch, then restore only our native metadata.
        for message in additions:
            if message.get("role") == "assistant":
                content = message.get("content") or ""
                if content:
                    if text_seen or content != (expected.get("content") or ""):
                        raise SubscriptionCapabilityError("voice continuation changed assistant text")
                    text_seen = True
                calls = message.get("tool_calls") or []
                if not isinstance(calls, list) or (not content and not calls):
                    raise SubscriptionCapabilityError("voice continuation changed its assistant batch")
                for actual in calls:
                    try:
                        saved = wanted_by_id[actual["id"]]
                        valid = (actual.get("type", "function") == "function"
                            and actual["function"]["name"] == saved["function"]["name"]
                            and json.loads(actual["function"]["arguments"])
                            == json.loads(saved["function"]["arguments"]))
                    except (KeyError, TypeError, ValueError):
                        valid = False
                    if not valid or actual["id"] in observed_calls:
                        raise SubscriptionCapabilityError("voice continuation changed a tool binding")
                    observed_calls.append(actual["id"])
            elif message.get("role") == "tool":
                call_id = message.get("tool_call_id")
                if call_id not in observed_calls or call_id in replies:
                    raise SubscriptionCapabilityError("voice continuation has incomplete or foreign results")
                replies[call_id] = message
            else:
                raise SubscriptionCapabilityError("voice continuation changed its assistant batch")
        if observed_calls != [call["id"] for call in wanted] or set(replies) != set(wanted_by_id):
            raise SubscriptionCapabilityError("voice continuation has incomplete or foreign results")
        return copy.deepcopy(self._native_history + [expected]
                             + [replies[call["id"]] for call in wanted])

    async def start(self, frame):
        await super().start(frame)
        await self._schedule_prestart(startup=True)

    async def _schedule_prestart(self, *, startup=False):
        """Pre-start the next turn's CLI (WS-43). Never raises; a miss runs cold."""
        context = self._prestart_context
        if (not self._prestart or self._cleanup_failed or context is None
                or self._next_parent_id is not None
                or (startup and (self._parent_id is not None or self._turn_generation))):
            return
        try:
            params = self.get_llm_adapter().get_llm_invocation_params(
                context, convert_developer_to_user=False)
            tools = voice_tool_references(params["tools"])
            system_messages = [copy.deepcopy(message) for message in params["messages"]
                               if message.get("role") == "system"]
            policy = self._last_policy
            if startup:
                # Before any real turn, do not manufacture an approved policy
                # or preload conversation history. The stored startup context
                # contains the host-bound system prompt and registered menu.
                if (not system_messages or len(system_messages) != len(params["messages"])
                        or self.policy_for_context is None
                        or any(tool.name not in self._functions for tool in tools)):
                    return
                policy = self.policy_for_context(context)
                if type(policy) is not DataPolicy:
                    return
                if self.sources is not None:
                    policy = strictest(policy, self.sources.policy_for_projection(
                        context, system_messages))
                assert_route_allowed(self.resolved.route, policy)

            client = self._client(self.resolved)
            if getattr(client, "has_spare", lambda: False)():
                # No ids are pending here, so any spare the client still holds
                # belongs to a turn that failed before reaching it; close it so
                # it cannot block every later pre-start.
                await self._discard_spare()
            parent, task = str(uuid.uuid4()), str(uuid.uuid4())
            request = ModelExecutionRequest(
                workload="voice_supervisor", task_id=task, parent_request_id=parent,
                instructions="", context=(), tools=tools,
                data_policy=policy or DataPolicy("approved_external", "voice-prestart"),
                timeout_s=120.0,
            )
            client.prestart(request, self.resolved, {
                "model": self.resolved.model, "messages": system_messages, "stream": True})
            self._next_parent_id, self._next_task_id = parent, task
        except Exception as exc:  # noqa: BLE001 - the turn simply runs cold
            self._next_parent_id = self._next_task_id = None
            _logger.info("voice_prestart_unavailable error=%s", type(exc).__name__)

    async def _discard_spare(self):
        self._next_parent_id = self._next_task_id = None
        if not self._prestart:
            return
        discard = getattr(self._native_client, "discard_spares", None)
        if discard is None:
            return
        try:
            await discard()
        except BaseException:
            self._cleanup_failed = True
            raise

    async def _close_turn(self):
        # 2026-11-23 (WS-43): register the text already spoken so Pipecat's
        # partial assistant message is classified (VoiceSources.added matches
        # by prefix); otherwise an interrupted streamed reply re-enters the
        # next turn's context as UNKNOWN and the subscription route refuses it.
        streamed, meta = self._streamed, self._streamed_meta
        self._streamed, self._streamed_meta = [], None
        if streamed and meta is not None and self.sources is not None:
            try:
                self.sources.model_output(meta[0], SimpleNamespace(
                    text="".join(streamed), tool_calls=()), meta[1])
            except Exception:  # noqa: BLE001
                _logger.info("voice_stream_register_failed")
        self._turn_generation += 1
        active = self._active_inference
        if active is not None and not active.done():
            active.cancel()
            await asyncio.gather(active, return_exceptions=True)
        try:
            if self._parent_id is not None and self._native_client is not None:
                # The shared best-effort cleanup helper intentionally logs and
                # suppresses errors; voice must retain an unverified cleanup.
                await self._native_client.close_request(self._parent_id)
        except BaseException:
            self._cleanup_failed = True
            raise
        finally:
            self._parent_id = None
            self._pending_assistant = None
            self._input_messages = None
            self._native_history = None
            self._turn_policy = None

    async def _process_context(self, context):
        if self._cleanup_failed:
            raise SubscriptionCapabilityError("subscription voice cleanup is unverified")
        policy = (self.policy_for_context(context) if self.policy_for_context
                  else DataPolicy("confidential", "unclassified-voice-context"))
        if type(policy) is not DataPolicy:
            raise SubscriptionCapabilityError("voice context requires a host data policy")
        if self._turn_policy is not None:
            policy = strictest(self._turn_policy, policy)
        assert_route_allowed(self.resolved.route, policy)
        params = self.get_llm_adapter().get_llm_invocation_params(
            context, convert_developer_to_user=False)
        messages = copy.deepcopy(params["messages"])
        if self.sources is not None:
            policy = strictest(policy, self.sources.policy_for_projection(context, messages))
            assert_route_allowed(self.resolved.route, policy)
        native_messages = self._bound_messages(messages)
        tools = voice_tool_references(params["tools"])
        if any(tool.name not in self._functions for tool in tools):
            raise SubscriptionCapabilityError("voice advertised an unregistered handler")
        task_id = str(uuid.uuid4())
        if self._parent_id is None and self._next_parent_id is not None:
            # The pre-started CLI is keyed by these ids (WS-43).
            self._parent_id = self._next_parent_id
            task_id = self._next_task_id
            self._next_parent_id = self._next_task_id = None
        self._parent_id = self._parent_id or str(uuid.uuid4())
        self._turn_policy = policy
        self._last_policy = policy
        self._prestart_context = context
        request = ModelExecutionRequest(
            workload="voice_supervisor", task_id=task_id,
            parent_request_id=self._parent_id, instructions="",
            context=_model_context_messages(native_messages, policy), tools=tools,
            data_policy=policy, timeout_s=120.0,
            stream_text=self._streaming,
        )
        generation = self._turn_generation
        await self.start_ttfb_metrics()
        if self._streaming:
            self._streamed, self._streamed_meta = [], (context, policy)
            self._first_delta = False

            async def sink(event):
                if (event.event_type != "text_delta" or not event.text_delta
                        or generation != self._turn_generation):
                    return
                self._streamed.append(event.text_delta)
                if not self._first_delta:
                    self._first_delta = True
                    await self.stop_ttfb_metrics()  # TTFB ends at the first text
                await self.push_frame(LLMTextFrame(event.text_delta))
            self._active_inference = asyncio.create_task(execute_chat(
                request, self.resolved, client_factory=self._client,
                event_sink=sink, event_sink_policy=policy))
        else:
            self._active_inference = asyncio.create_task(execute_chat(
                request, self.resolved, client_factory=self._client))
        try:
            result = await self._active_inference
        finally:
            self._active_inference = None
            await self.stop_ttfb_metrics()
        # Use normalized route/billing metadata, not the legacy voice endpoint.
        # Do not emit an LLM usage frame as well: its existing observer would
        # count this completion twice and attribute it to the API settings.
        record_execution_result("supervisor", result, session_id=self.session_id)
        if generation != self._turn_generation:
            return  # Interruption/disconnect cannot publish a late response.
        spoken = "".join(self._streamed)
        if self.sources is not None:
            self.sources.model_output(context, result, policy)
            if spoken and spoken != result.text:
                self.sources.model_output(context, SimpleNamespace(
                    text=spoken, tool_calls=()), policy)
        self._streamed, self._streamed_meta = [], None
        self._input_messages = copy.deepcopy(messages)
        self._native_history = copy.deepcopy(native_messages)
        if result.tool_calls:
            self._pending_assistant = {
                "role": "assistant", "content": result.text or None,
                "tool_calls": [{"id": call.tool_call_id, "type": "function",
                    "function": {"name": call.name, "arguments": call.raw_arguments
                                 or json.dumps(dict(call.arguments))},
                    **dict(call.provider_extras)} for call in result.tool_calls],
            }
        else:
            await self._close_turn()
            await self._schedule_prestart()
        # Streamed text was already pushed delta by delta; push the full text
        # only when nothing streamed (fallback), never twice.
        if result.text and not spoken:
            await self.push_frame(LLMTextFrame(result.text))
        if result.tool_calls and generation == self._turn_generation:
            await self.run_function_calls([FunctionCallFromLLM(
                context=context, tool_call_id=call.tool_call_id,
                function_name=call.name, arguments=dict(call.arguments),
            ) for call in result.tool_calls])

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        if isinstance(frame, InterruptionFrame):
            await self._close_turn()
            await self._schedule_prestart()
        await super().process_frame(frame, direction)
        if not isinstance(frame, LLMContextFrame):
            await self.push_frame(frame, direction)
            return
        async with self._context_lock:
            await self.push_frame(LLMFullResponseStartFrame())
            await self.start_processing_metrics()
            try:
                await self._process_context(frame.context)
            except asyncio.CancelledError:
                await self._close_turn()
                raise
            except Exception as exc:
                await self._close_turn()
                _log_voice_failure(exc)
                # Provider exception strings can contain private input.
                await self.push_error(error_msg="Subscription voice request unavailable")
            finally:
                await self.stop_processing_metrics()
                await self.push_frame(LLMFullResponseEndFrame())

    async def _close_all(self):
        try:
            await self._close_turn()
        finally:
            await self._discard_spare()

    async def stop(self, frame):
        await self._close_all()
        await super().stop(frame)

    async def cancel(self, frame):
        await self._close_all()
        await super().cancel(frame)

    async def cleanup(self):
        await self._close_all()
        await super().cleanup()
