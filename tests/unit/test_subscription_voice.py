"""Synthetic voice/native integration; no provider subprocess or credentials."""
import asyncio
import copy
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.frames.frames import (
    LLMContextFrame, LLMTextFrame, LLMFullResponseStartFrame, LLMFullResponseEndFrame,
    InterruptionFrame,
)
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.frame_processor import FrameDirection

from jarvis.bot import subscription_llm as voice
from jarvis.model_routing import AccessRoute, ResolvedModelRoute, ModelRouteError
from jarvis.privacy_policy import DataPolicy


def route():
    return ResolvedModelRoute(
        "voice_supervisor", "claude-haiku-4-5", "claude-haiku-4-5", "anthropic",
        "subscription://claude", AccessRoute("subscription", "subscription_runtime",
        "subscription", None, "approved_external", capabilities=("text", "tools")),
        None, "anthropic/claude-haiku-4-5",
    )


def context():
    return LLMContext(messages=[{"role": "system", "content": "Synthetic test only."},
                                {"role": "user", "content": "Read the synthetic clock."}],
        tools=ToolsSchema(standard_tools=[FunctionSchema(
            name="fixture_clock", description="Return synthetic time", properties={}, required=[])]))


class Native:
    def __init__(self, *, tool=False, wait=False, fail=False):
        self.tool, self.wait, self.fail = tool, wait, fail
        self.requests = []
        self.closed = []
        self.started = asyncio.Event()
        self.cancelled = False

    async def execute_request(self, request, resolved, args):
        self.requests.append((request, copy.deepcopy(args)))
        self.started.set()
        if self.wait:
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                self.cancelled = True
                raise
        if self.fail:
            raise RuntimeError("PRIVATE_PROVIDER_ERROR_CANARY")
        calls = []
        if self.tool and len(self.requests) == 1:
            calls = [SimpleNamespace(id="fixture-call", type="function",
                function=SimpleNamespace(name="fixture_clock", arguments="{}"),
                model_extra={"mortimer_parent_id": request.parent_request_id,
                             "mortimer_task_id": request.task_id})]
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
            content="Checking." if calls else "Synthetic clock says noon.",
            tool_calls=calls, model_extra={}))], usage=None)

    async def close_request(self, parent):
        self.closed.append(parent)


@pytest.fixture
def setup(monkeypatch, fresh_db):
    monkeypatch.setenv("JARVIS_LLM_ACCESS_MODE", "subscription_only")
    monkeypatch.setenv("JARVIS_MODEL_ROUTING_ENABLED", "0")
    no_api = Mock(side_effect=AssertionError("API client created"))
    monkeypatch.setattr("openai.AsyncOpenAI", no_api)
    monkeypatch.setattr("anthropic.AsyncAnthropic", no_api)

    def build(native, *, classified=True):
        monkeypatch.setattr(voice, "make_route_client", lambda _: native)
        service = voice.SubscriptionVoiceLLMService(resolved=route(),
            enable_direct_mode=True,
            policy_for_context=(lambda _: DataPolicy("approved_external", "synthetic-fixture"))
            if classified else None)
        service.register_function("fixture_clock", AsyncMock())
        service.push_frame = AsyncMock()
        service.push_error = AsyncMock()
        service.run_function_calls = AsyncMock()
        return service
    yield build
    no_api.assert_not_called()


@pytest.mark.asyncio
async def test_actual_frame_boundary_publishes_buffered_speech_without_api(setup):
    native = Native()
    service = setup(native)
    await service.process_frame(LLMContextFrame(context()), FrameDirection.DOWNSTREAM)
    frames = [call.args[0] for call in service.push_frame.await_args_list]
    assert [type(frame) for frame in frames] == [
        LLMFullResponseStartFrame, LLMTextFrame, LLMFullResponseEndFrame]
    assert frames[1].text == "Synthetic clock says noon."
    assert native.requests[0][1].get("stream") is None
    assert native.closed == [native.requests[0][0].parent_request_id]
    service.push_error.assert_not_awaited()


@pytest.mark.asyncio
async def test_usage_is_recorded_once_with_subscription_attribution(setup, monkeypatch):
    recorded = Mock()
    monkeypatch.setattr(voice, "record_execution_result", recorded)
    service = setup(Native())
    await service._process_context(context())
    recorded.assert_called_once()
    result = recorded.call_args.args[1]
    assert result.route == "subscription" and result.billing == "subscription"
    assert result.prompt_tokens is None and result.completion_tokens is None


@pytest.mark.asyncio
async def test_real_pipecat_dispatcher_executes_only_registered_mortimer_handler(setup):
    from pipecat.clocks.system_clock import SystemClock
    from pipecat.processors.frame_processor import FrameProcessorSetup
    from pipecat.utils.asyncio.task_manager import TaskManager, TaskManagerParams
    from pipecat.frames.frames import FunctionCallResultFrame, CancelFrame
    native = Native(tool=True)
    service = setup(native)
    manager = TaskManager()
    manager.setup(TaskManagerParams(loop=asyncio.get_running_loop()))
    await service.setup(FrameProcessorSetup(clock=SystemClock(), task_manager=manager,
                                           pipeline_worker=SimpleNamespace(app_resources={})))
    finished = asyncio.Event()
    calls = []
    async def handler(params):
        calls.append(params.arguments)
        await params.result_callback("noon")
        finished.set()
    service.register_function("fixture_clock", handler)
    service.run_function_calls = voice.SubscriptionVoiceLLMService.run_function_calls.__get__(service)
    try:
        await service._process_context(context())
        await asyncio.wait_for(finished.wait(), 2)
        assert calls == [{}]
        results = [call.args[0] for call in service.push_frame.await_args_list
                   if isinstance(call.args[0], FunctionCallResultFrame)]
        assert results and all(result.result == "noon" for result in results)
    finally:
        await service.cancel(CancelFrame())
        await service.cleanup()


@pytest.mark.asyncio
async def test_tool_continuation_preserves_native_parent_and_uses_pipecat_handlers(setup):
    native = Native(tool=True)
    service = setup(native)
    ctx = context()
    await service._process_context(ctx)
    dispatched = service.run_function_calls.await_args.args[0]
    assert len(dispatched) == 1 and dispatched[0].function_name == "fixture_clock"
    assistant = copy.deepcopy(service._pending_assistant)
    for call in assistant["tool_calls"]:
        call.pop("mortimer_parent_id")
        call.pop("mortimer_task_id")
    ctx.add_message(assistant)
    ctx.add_message({"role": "tool", "tool_call_id": "fixture-call", "content": "noon"})
    await service._process_context(ctx)
    first, second = native.requests
    assert first[0].parent_request_id == second[0].parent_request_id
    assert first[0].task_id != second[0].task_id
    bound = second[1]["messages"][-2]["tool_calls"][0]
    assert bound["mortimer_task_id"] == first[0].task_id
    assert second[1]["messages"][-1]["name"] == "fixture_clock"
    assert service._parent_id is None
    # A later real user turn starts a fresh native session. Old completed
    # tool events become clearly labeled history, not fresh executable calls.
    ctx.add_message({"role": "assistant", "content": "Synthetic clock says noon."})
    ctx.add_message({"role": "user", "content": "Repeat the synthetic answer."})
    await service._process_context(ctx)
    third = native.requests[2]
    assert third[0].parent_request_id != first[0].parent_request_id
    assert not any(message.get("tool_calls") or message["role"] == "tool"
                   for message in third[1]["messages"])
    assert "Retrospective Mortimer tool record" in third[1]["messages"][2]["content"]
    assert ctx.get_messages()[2]["tool_calls"][0].get("mortimer_parent_id") is None


@pytest.mark.asyncio
async def test_images_and_unregistered_tools_refuse_before_native_client(setup):
    native = Native()
    service = setup(native)
    ctx = context()
    service.unregister_function("fixture_clock")
    with pytest.raises(voice.SubscriptionCapabilityError):
        await service._process_context(ctx)
    service.register_function("fixture_clock", AsyncMock())
    ctx.add_message({"role": "user", "content": [{"type": "image_url",
                    "image_url": {"url": "data:image/png;base64,c3ludGhldGlj"}}]})
    with pytest.raises(ValueError):
        await service._process_context(ctx)
    assert not native.requests


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", ["foreign_id", "changed_arguments", "missing_result", "changed_prefix"])
async def test_foreign_or_mutated_continuation_cannot_resume_native_session(setup, mutation):
    native = Native(tool=True)
    service = setup(native)
    ctx = context()
    await service._process_context(ctx)
    assistant = copy.deepcopy(service._pending_assistant)
    if mutation == "foreign_id":
        assistant["tool_calls"][0]["id"] = "foreign"
    if mutation == "changed_arguments":
        assistant["tool_calls"][0]["function"]["arguments"] = '{"extra":true}'
    ctx.add_message(assistant)
    if mutation != "missing_result":
        ctx.add_message({"role": "tool", "tool_call_id": "fixture-call", "content": "noon"})
    if mutation == "changed_prefix":
        ctx.get_messages()[0]["content"] = "changed"
    with pytest.raises(voice.SubscriptionCapabilityError):
        await service._process_context(ctx)
    assert len(native.requests) == 1
    await service._close_turn()


@pytest.mark.asyncio
async def test_unclassified_context_and_private_tool_results_refuse_before_transmission(setup):
    native = Native(tool=True)
    service = setup(native, classified=False)
    with pytest.raises(ModelRouteError):
        await service._process_context(context())
    assert not native.requests
    service = setup(native)
    ctx = context()
    await service._process_context(ctx)
    service.policy_for_context = lambda _: DataPolicy("confidential", "synthetic-private-result")
    with pytest.raises(ModelRouteError):
        await service._process_context(ctx)
    assert len(native.requests) == 1
    await service._close_turn()


@pytest.mark.asyncio
async def test_interruption_drains_inference_and_emits_no_late_speech(setup):
    native = Native(wait=True)
    service = setup(native)
    task = asyncio.create_task(service._process_context(context()))
    await asyncio.wait_for(native.started.wait(), 2)
    await service.process_frame(InterruptionFrame(), FrameDirection.DOWNSTREAM)
    with pytest.raises(asyncio.CancelledError):
        await task
    assert native.cancelled and native.closed
    assert all(not isinstance(call.args[0], LLMTextFrame)
               for call in service.push_frame.await_args_list)


@pytest.mark.asyncio
async def test_error_is_payload_free_and_never_falls_back(setup):
    native = Native(fail=True)
    service = setup(native)
    await service.process_frame(LLMContextFrame(context()), FrameDirection.DOWNSTREAM)
    assert service.push_error.await_args.kwargs == {
        "error_msg": "Subscription voice request unavailable"}
    assert native.closed


@pytest.mark.asyncio
async def test_unverified_cleanup_blocks_reuse(setup):
    native = Native(tool=True)
    service = setup(native)
    await service._process_context(context())
    native.close_request = AsyncMock(side_effect=RuntimeError("cleanup failed"))
    with pytest.raises(RuntimeError):
        await service._close_turn()
    with pytest.raises(voice.SubscriptionCapabilityError, match="cleanup"):
        await service._process_context(context())
    assert len(native.requests) == 1


def test_codex_or_paid_voice_route_is_not_accepted():
    from dataclasses import replace
    candidate = route()
    for name in ("direct_api", "codex_subscription"):
        with pytest.raises(ModelRouteError):
            voice.SubscriptionVoiceLLMService(resolved=replace(
                candidate, route=replace(candidate.route, name=name)))
