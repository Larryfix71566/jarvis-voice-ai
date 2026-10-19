"""Public synthetic input → real pipeline wrapper → real transport envelopes.

No service/model is contacted. The probe replaces inference, not the request
observer, frame scoping, function callback adapter or message sender.
"""
import asyncio
from types import SimpleNamespace

import pytest
from pipecat.frames.frames import LLMContextFrame, TranscriptionFrame, UserStartedSpeakingFrame
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.frame_processor import FrameDirection
from pipecat.processors.frame_processor import FrameProcessor
from pipecat.processors.aggregators.llm_response_universal import LLMContextAggregatorPair, LLMUserAggregatorParams
from pipecat.turns.user_turn_strategies import UserTurnStrategies
from pipecat.turns.user_start import MinWordsUserTurnStartStrategy
from pipecat.turns.user_stop import ExternalUserTurnStopStrategy
from pipecat.services.llm_service import LLMService, FunctionCallFromLLM, FunctionCallParams

from jarvis.bot.pipeline import (
    ForegroundRequests, _foreground_request, adapt_to_pipecat,
    make_agent_event_handler, request_bound_service, send_app_message,
)


class Transport:
    def __init__(self):
        self.messages = []

    def output(self):
        return self

    async def send_message(self, frame):
        self.messages.append(frame.message["data"])


class Params:
    def __init__(self, call_id):
        self.tool_call_id, self.arguments = call_id, {}
        self.results = []

    async def result_callback(self, result):
        self.results.append(result)


def fixture():
    transport = Transport()
    owner = ForegroundRequests(transport, "session", "generation")
    owner.input_source, owner.user_aggregator = object(), object()
    return owner, transport


async def push(owner, source, frame):
    await owner.before_push(source, frame)


async def user_context(owner, text, timestamp):
    await push(owner, owner.input_source, UserStartedSpeakingFrame())
    await push(owner, owner.input_source, TranscriptionFrame(text, "synthetic-user", timestamp, finalized=True))
    context = LLMContext([{"role": "user", "content": text}])
    frame = LLMContextFrame(context)
    await push(owner, owner.user_aggregator, frame)
    return frame


async def bind_call(owner, frame, call_id):
    class InferenceProbe:
        async def process_frame(self, received, direction):
            await self.run_function_calls([SimpleNamespace(tool_call_id=call_id)])

        async def run_function_calls(self, calls):
            pass
    await request_bound_service(InferenceProbe, owner)().process_frame(frame, FrameDirection.DOWNSTREAM)


async def test_actual_frame_and_callback_scope_survives_new_turn_and_sequential_runner():
    owner, transport = fixture()
    old = await user_context(owner, "Weather here", "synthetic-input-1")
    await bind_call(owner, old, "call-old")
    old_id = transport.messages[-1]["request_id"]
    new = await user_context(owner, "Weather in Atlanta", "synthetic-input-2")
    await bind_call(owner, new, "call-new")
    new_id = transport.messages[-1]["request_id"]
    assert old_id != new_id

    async def handler(_):
        await send_app_message(transport, {"type": "display", "display": {
            "kind": "markdown", "title": "Synthetic weather", "origin_request_id": "untrusted"}})
        return "done"

    # A reusable sequential runner has no inference ContextVar. The exact
    # tool-call binding must win; looking at the latest context would fail.
    assert _foreground_request.get() is None
    await adapt_to_pipecat("local_weather", handler, foreground_requests=owner)(Params("call-old"))
    await adapt_to_pipecat("local_weather", handler, foreground_requests=owner)(Params("call-new"))
    displays = [m["display"] for m in transport.messages if m["type"] == "display"]
    assert [d["origin_request_id"] for d in displays] == [old_id, new_id]
    assert not owner.calls


async def test_detached_agent_event_keeps_original_request_after_supersession():
    owner, transport = fixture()
    frame = await user_context(owner, "Synthetic search", "synthetic-input-1")
    await bind_call(owner, frame, "call-1")
    original = transport.messages[-1]["request_id"]
    release = asyncio.Event()
    tasks = []

    async def detached():
        await release.wait()
        # The real delegate event handler builds and sends a display payload.
        make_agent_event_handler(transport)({
            "type": "agent_tool_result", "agent": "analyst", "display_name": "Analyst",
            "run_id": "synthetic-run", "tool": "web_search", "ok": True,
            "arguments": {"query": "synthetic"},
            "result": '{"results":[{"title":"Synthetic","url":"https://example.test","snippet":"Public fixture"}]}',
        })
        await asyncio.sleep(0)

    async def handler(_):
        tasks.append(asyncio.create_task(detached()))
        return "running"

    await adapt_to_pipecat("delegate_task", handler, foreground_requests=owner)(Params("call-1"))
    await user_context(owner, "A different request", "synthetic-input-2")
    release.set()
    await asyncio.gather(*tasks)
    displays = [m["display"] for m in transport.messages if m["type"] == "display"]
    assert len(displays) == 1
    assert displays[0]["origin_request_id"] == original


async def test_cancelled_callback_emits_exact_request_cancellation():
    owner, transport = fixture()
    frame = await user_context(owner, "Synthetic weather", "synthetic-input-1")
    await bind_call(owner, frame, "call-1")
    request = transport.messages[-1]["request_id"]
    entered = asyncio.Event()

    async def handler(_):
        entered.set()
        await asyncio.Future()

    task = asyncio.create_task(adapt_to_pipecat(
        "local_weather", handler, foreground_requests=owner)(Params("call-1")))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert transport.messages[-1]["state"] == "cancelled"
    assert transport.messages[-1]["request_id"] == request
    assert not owner.calls


async def test_unknown_or_injected_context_cannot_acquire_foreground():
    owner, transport = fixture()
    # A transcription from an unaccepted processor cannot establish origin.
    await push(owner, object(), TranscriptionFrame("Synthetic", "u", "input-1"))
    frame = LLMContextFrame(LLMContext([{"role": "user", "content": "Synthetic"}]))
    await push(owner, owner.user_aggregator, frame)
    await bind_call(owner, frame, "unknown")
    assert owner.calls["unknown"] is None
    assert transport.messages == []
    # The sender also refuses a payload's own claim when the host has none.
    await send_app_message(transport, {"type": "display", "display": {"origin_request_id": "forged"}})
    assert "origin_request_id" not in transport.messages[-1]["display"]


async def test_repeated_phrase_has_distinct_input_and_old_continuation_keeps_its_id():
    owner, transport = fixture()
    first = await user_context(owner, "Weather here", "input-1")
    await bind_call(owner, first, "one")
    old = owner.calls["one"]
    second = await user_context(owner, "Weather here", "input-2")
    await bind_call(owner, second, "two")
    assert owner.calls["two"].request_id != old.request_id
    continuation = LLMContextFrame(first.context)
    await push(owner, owner.user_aggregator, continuation)
    await bind_call(owner, continuation, "old-continuation")
    assert owner.calls["old-continuation"] == old
    assert [m["state"] for m in transport.messages] == ["started", "cancelled", "started"]


async def test_real_sdk_dispatch_binds_before_async_events_and_reused_runner():
    owner, transport = fixture()
    frame = await user_context(owner, "Synthetic direct tool", "sdk-input-1")
    origin = transport.messages[-1]["request_id"]
    seen = []

    class DispatchProbe(LLMService):
        async def process_frame(self, received, direction):
            await self.run_function_calls([FunctionCallFromLLM(
                function_name="local_weather", tool_call_id="sdk-call", arguments={}, context=received.context)])

        async def broadcast_frame(self, *_args, **_kwargs):
            pass  # No audio pipeline is started in this synthetic dispatch.

        async def _run_parallel_function_calls(self, items):
            # Use SDK-created registry/runner items and real FunctionCallParams;
            # the scheduler seam deliberately has no inference ContextVar.
            token = _foreground_request.set(None)
            try:
                for item in items:
                    async def callback(result):
                        seen.append(result)
                    await item.registry_item.handler(FunctionCallParams(
                        function_name=item.function_name, tool_call_id=item.tool_call_id,
                        arguments=item.arguments, context=item.context, llm=self,
                        pipeline_worker=None, result_callback=callback))
            finally:
                _foreground_request.reset(token)

    async def handler(_):
        await send_app_message(transport, {"type": "display", "display": {"kind": "markdown"}})
        return "synthetic result"

    service = request_bound_service(DispatchProbe, owner)()
    service.register_function("local_weather", adapt_to_pipecat(
        "local_weather", handler, foreground_requests=owner))
    await service.process_frame(frame, FrameDirection.DOWNSTREAM)
    assert seen == ["synthetic result"]
    assert transport.messages[-1]["display"]["origin_request_id"] == origin
    assert not owner.calls


async def test_aggregator_duplicate_start_after_final_does_not_erase_accepted_input():
    owner, transport = fixture()
    await push(owner, owner.input_source, UserStartedSpeakingFrame())
    await push(owner, owner.input_source, TranscriptionFrame(
        "Synthetic weather", "synthetic-user", "input-1", finalized=True))
    await push(owner, owner.user_aggregator, UserStartedSpeakingFrame())
    frame = LLMContextFrame(LLMContext([{"role": "user", "content": "Synthetic weather"}]))
    await push(owner, owner.user_aggregator, frame)
    await bind_call(owner, frame, "call-1")
    assert owner.calls["call-1"] is not None
    assert [m["state"] for m in transport.messages] == ["started"]


async def test_real_sdk_synchronous_frame_hook_binds_before_downstream_delivery():
    transport = Transport()
    owner = ForegroundRequests(transport, "session", "generation")
    received = []

    class Sender(FrameProcessor):
        def _check_started(self, frame):
            return True  # Only the start/clock scheduler is omitted, not push dispatch.

        async def queue_frame(self, frame, direction=FrameDirection.DOWNSTREAM, **kwargs):
            # Keep the actual upstream propagation through the accepted source.
            await self.push_frame(frame, direction)

    class Consumer(FrameProcessor):
        async def queue_frame(self, frame, direction=FrameDirection.DOWNSTREAM, **kwargs):
            if isinstance(frame, LLMContextFrame):
                received.append(frame)
                assert transport.messages[-1]["state"] == "started"

    context = LLMContext([])
    # No audio/model/turn analyzer is loaded. Stop detection is not exercised.
    pair = LLMContextAggregatorPair(context, user_params=LLMUserAggregatorParams(
        user_turn_strategies=UserTurnStrategies(start=[MinWordsUserTurnStartStrategy(min_words=2)],
                                               stop=[ExternalUserTurnStopStrategy()])))
    user = pair.user()
    user._check_started = lambda _frame: True
    source = Sender()
    # Inference/turn scheduling is omitted; public push/broadcast dispatch and
    # the real source -> aggregator -> sink links run in both directions.
    async def no_inference(*_args, **_kwargs):
        pass
    user.queue_frame = no_inference
    source.link(user); user.link(Consumer())
    owner.install(source, user)
    await source.broadcast_frame(UserStartedSpeakingFrame)
    await source.push_frame(TranscriptionFrame(
        "Synthetic current question", "synthetic-user", "hook-input-1", finalized=True))
    user.add_messages([{"role": "user", "content": "Synthetic current question"}])
    await user.broadcast_frame(UserStartedSpeakingFrame) # the real post-transcript duplicate
    await user.push_context_frame()
    assert len(received) == 1
    await bind_call(owner, received[0], "hook-call")
    assert owner.calls["hook-call"].input_timestamp == "hook-input-1"


async def test_blocked_ui_sender_is_bounded_and_does_not_break_request_capture(monkeypatch):
    owner, _transport = fixture()
    cancelled = asyncio.Event()
    async def blocked(*_args):
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            cancelled.set()
            raise
    monkeypatch.setattr("jarvis.bot.pipeline.send_app_message", blocked)
    frame = await asyncio.wait_for(user_context(owner, "Synthetic weather", "input-1"), timeout=1.0)
    await bind_call(owner, frame, "call-1")
    assert owner.calls["call-1"] is not None
    assert cancelled.is_set(), "The real UI-send deadline must cancel the blocked sender."


async def test_one_accepted_input_cannot_mint_authority_for_a_copied_boundary():
    owner, transport = fixture()
    frame = await user_context(owner, "Weather here", "input-1")
    await bind_call(owner, frame, "original")
    origin = owner.calls["original"]
    copied = LLMContextFrame(LLMContext([dict(m) for m in frame.context.get_messages()]))
    await push(owner, owner.user_aggregator, copied)
    await bind_call(owner, copied, "copied")
    assert owner.calls["copied"] is None
    assert owner.current == origin
    assert [m["state"] for m in transport.messages] == ["started"]


@pytest.mark.parametrize(("mode", "deferred"), [
    ("current", False), ("current", True), ("superseded", False), ("cancelled", False),
])
async def test_actual_tool_result_assistant_upstream_round_keeps_original_request(mode, deferred):
    from pipecat.frames.frames import (
        StartFrame, UserStoppedSpeakingFrame, FunctionCallResultFrame,
        LLMFullResponseStartFrame, LLMFullResponseEndFrame,
        BotStartedSpeakingFrame, BotStoppedSpeakingFrame,
    )
    from pipecat.pipeline.pipeline import Pipeline
    from pipecat.pipeline.worker import PipelineWorker, PipelineParams
    from pipecat.workers.runner import WorkerRunner
    from pipecat.turns.user_start import ExternalUserTurnStartStrategy

    transport = Transport()
    owner = ForegroundRequests(transport, "synthetic-session", "synthetic-generation")
    ready, first_entered, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
    second_done, new_inference, first_result = asyncio.Event(), asyncio.Event(), asyncio.Event()
    observed = []

    class Source(FrameProcessor):
        async def process_frame(self, frame, direction):
            await super().process_frame(frame, direction)
            await self.push_frame(frame, direction)
            if isinstance(frame, StartFrame):
                ready.set()

    class InferenceProbe(LLMService):
        def __init__(self):
            super().__init__()
            self.downstream = 0
            self.upstream = 0

        async def process_frame(self, frame, direction):
            await super().process_frame(frame, direction)
            if not isinstance(frame, LLMContextFrame):
                await self.push_frame(frame, direction)
                return
            observed.append((direction, _foreground_request.get()))
            await self.push_frame(LLMFullResponseStartFrame())
            if direction == FrameDirection.DOWNSTREAM:
                self.downstream += 1
                if self.downstream == 1:
                    await self.run_function_calls([FunctionCallFromLLM(
                        function_name="first_round", tool_call_id="real-first-round",
                        arguments={}, context=frame.context)])
                else:
                    new_inference.set()
            else:
                self.upstream += 1
                if self.upstream == 1:
                    await self.run_function_calls([FunctionCallFromLLM(
                        function_name="second_round", tool_call_id="real-second-round",
                        arguments={}, context=frame.context)])
            await self.push_frame(LLMFullResponseEndFrame())

    async def first_handler(_arguments):
        first_entered.set()
        await release.wait()
        return {"public": "Synthetic first tool result"}

    async def second_handler(_arguments):
        await send_app_message(transport, {"type": "display", "display": {
            "kind": "markdown", "title": "Synthetic continuation answer"}})
        second_done.set()
        return {"public": "Synthetic second tool result"}

    context = LLMContext([])
    pair = LLMContextAggregatorPair(context, user_params=LLMUserAggregatorParams(
        user_turn_strategies=UserTurnStrategies(start=[ExternalUserTurnStartStrategy()],
                                               stop=[ExternalUserTurnStopStrategy()])))
    source = Source()
    service = request_bound_service(InferenceProbe, owner)()
    owner.install(source, pair.user(), pair.assistant())
    service.register_function("first_round", adapt_to_pipecat(
        "first_round", first_handler, foreground_requests=owner), cancel_on_interruption=False)
    service.register_function("second_round", adapt_to_pipecat(
        "second_round", second_handler, foreground_requests=owner))

    async def after_assistant(_source, frame):
        if isinstance(frame, FunctionCallResultFrame) and frame.tool_call_id == "real-first-round":
            first_result.set()
    pair.assistant().add_event_handler("on_after_process_frame", after_assistant)
    worker = PipelineWorker(Pipeline([source, pair.user(), service, pair.assistant()]),
                            params=PipelineParams())
    runner = WorkerRunner(handle_sigint=False, handle_sigterm=False)
    running = asyncio.create_task(runner.run(worker))
    try:
        await asyncio.wait_for(ready.wait(), timeout=5)
        await worker.queue_frames([UserStartedSpeakingFrame(), TranscriptionFrame(
            "Synthetic original question", "synthetic-user", "actual-input-1", finalized=True),
            UserStoppedSpeakingFrame()])
        await asyncio.wait_for(first_entered.wait(), timeout=5)
        original = owner.current
        assert original is not None
        if mode == "superseded":
            await worker.queue_frames([UserStartedSpeakingFrame(), TranscriptionFrame(
                "Synthetic newer question", "synthetic-user", "actual-input-2", finalized=True),
                UserStoppedSpeakingFrame()])
            await asyncio.wait_for(new_inference.wait(), timeout=5)
            assert owner.current is not None and owner.current != original
        elif mode == "cancelled":
            await owner.cancel(original)
        if deferred:
            await worker.queue_frame(BotStartedSpeakingFrame())
        release.set()
        await asyncio.wait_for(first_result.wait(), timeout=5)
        if deferred:
            assert not second_done.is_set(), "The real assistant must defer until bot-stopped."
            await worker.queue_frame(BotStoppedSpeakingFrame())
        await asyncio.wait_for(second_done.wait(), timeout=5)
        upstream = [binding for direction, binding in observed if direction == FrameDirection.UPSTREAM]
        assert upstream and upstream[0] == original, "Fresh upstream SDK context retains its actual tool's request, including after newer input."
        display = next(m["display"] for m in transport.messages if m["type"] == "display")
        assert display.get("origin_request_id") == original.request_id
    finally:
        release.set()
        await worker.stop_when_done()
        await asyncio.wait_for(running, timeout=5)
