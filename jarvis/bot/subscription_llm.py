"""Buffered native-subscription voice adapter; no API client or tool executor.

The pinned Claude gateway publishes complete assistant messages, not verified
token deltas. This service preserves Pipecat's speech/tool frame protocol but
does not claim token streaming. Production activation stays separately gated.
Unclassified voice context is confidential and cannot enter a subscription.
"""
from __future__ import annotations

import asyncio
import copy
import json
import uuid
from collections.abc import Callable

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
from jarvis.subscription import SubscriptionCapabilityError
from jarvis.usage_ledger import record_execution_result


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

    def can_generate_metrics(self):
        return True

    def _client(self, resolved):
        if self._native_client is None:
            self._native_client = make_route_client(resolved)
        return self._native_client

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

    async def _close_turn(self):
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
        raw_tools = params["tools"]
        if not isinstance(raw_tools, list) or not raw_tools:
            raise SubscriptionCapabilityError("subscription voice requires explicit registered tools")
        tools = tuple(ModelToolReference(
            tool["function"]["name"], tool["function"]["parameters"],
            tool["function"].get("description", "")) for tool in raw_tools)
        if any(tool.name not in self._functions for tool in tools):
            raise SubscriptionCapabilityError("voice advertised an unregistered handler")
        self._parent_id = self._parent_id or str(uuid.uuid4())
        self._turn_policy = policy
        request = ModelExecutionRequest(
            workload="voice_supervisor", task_id=str(uuid.uuid4()),
            parent_request_id=self._parent_id, instructions="",
            context=_model_context_messages(native_messages, policy), tools=tools,
            data_policy=policy, timeout_s=120.0,
        )
        generation = self._turn_generation
        await self.start_ttfb_metrics()
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
        if self.sources is not None:
            self.sources.model_output(context, result, policy)
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
        if result.text:
            await self.push_frame(LLMTextFrame(result.text))
        if result.tool_calls and generation == self._turn_generation:
            await self.run_function_calls([FunctionCallFromLLM(
                context=context, tool_call_id=call.tool_call_id,
                function_name=call.name, arguments=dict(call.arguments),
            ) for call in result.tool_calls])

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        if isinstance(frame, InterruptionFrame):
            await self._close_turn()
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
            except Exception:
                await self._close_turn()
                # Provider exception strings can contain private input.
                await self.push_error(error_msg="Subscription voice request unavailable")
            finally:
                await self.stop_processing_metrics()
                await self.push_frame(LLMFullResponseEndFrame())

    async def stop(self, frame):
        await self._close_turn()
        await super().stop(frame)

    async def cancel(self, frame):
        await self._close_turn()
        await super().cancel(frame)

    async def cleanup(self):
        await self._close_turn()
        await super().cleanup()
