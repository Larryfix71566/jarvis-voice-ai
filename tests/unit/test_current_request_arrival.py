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
    await owner.on_push_frame(SimpleNamespace(
        source=source, frame=frame, direction=FrameDirection.DOWNSTREAM))


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
            await owner.calls_started(self, [SimpleNamespace(tool_call_id=call_id)])
    await request_bound_service(InferenceProbe)().process_frame(frame, FrameDirection.DOWNSTREAM)


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
