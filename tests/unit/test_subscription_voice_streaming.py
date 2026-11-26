"""WS-43: streamed voice replies and pre-started CLI, behind flags. Fakes only."""
import asyncio
import copy
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.frames.frames import EndFrame, InterruptionFrame, LLMTextFrame, StartFrame
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.frame_processor import FrameDirection

from jarvis.bot import subscription_llm as voice
from jarvis.model_routing import (
    AccessRoute, ModelRouteError, ResolvedModelRoute, make_route_client,
    resolve_model_route,
)
from jarvis.privacy_policy import DataPolicy
from jarvis.voice_sources import VoiceSources, bound_context_type

STREAM_ENV = "JARVIS_VOICE_STREAMING_ENABLED"


def route(*, streaming=True):
    caps = ("text", "tools", "streaming") if streaming else ("text", "tools")
    return ResolvedModelRoute(
        "voice_supervisor", "claude-sonnet-5-5", "claude-sonnet-5-5", "anthropic",
        "subscription://claude", AccessRoute("subscription", "subscription_runtime",
        "subscription", None, "approved_external", capabilities=caps),
        None, "anthropic/claude-sonnet-5-5",
    )


def context():
    return LLMContext(messages=[{"role": "system", "content": "Synthetic test only."},
                                {"role": "user", "content": "Read the synthetic clock."}],
        tools=ToolsSchema(standard_tools=[FunctionSchema(
            name="fixture_clock", description="Return synthetic time", properties={}, required=[])]))


def text_chunk(text):
    return SimpleNamespace(id=None, usage=None, choices=[SimpleNamespace(
        delta=SimpleNamespace(content=text, tool_calls=None), finish_reason=None)])


def final_chunk(*, tool_parent=None, tool_task=None):
    if tool_parent is None:
        return SimpleNamespace(id=None, usage=None, choices=[SimpleNamespace(
            delta=SimpleNamespace(content=None, tool_calls=None), finish_reason="stop")])
    call = SimpleNamespace(index=0, id="fixture-call", type="function",
        function=SimpleNamespace(name="fixture_clock", arguments="{}"),
        model_extra={"mortimer_parent_id": tool_parent, "mortimer_task_id": tool_task})
    return SimpleNamespace(id=None, usage=None, choices=[SimpleNamespace(
        delta=SimpleNamespace(content=None, tool_calls=[call]), finish_reason="tool_calls")])


class StreamNative:
    """Fake native client: execute_request returns an async generator of chunks."""

    def __init__(self, *, texts=("Hello. ", "How can I help?"), tool=False,
                 hold_after_first=False, prestart_error=None):
        self.texts, self.tool, self.hold_after_first = texts, tool, hold_after_first
        self.prestart_error = prestart_error
        self.requests, self.closed, self.prestarts = [], [], []
        self.discarded = 0
        self.first_sent = asyncio.Event()

    async def execute_request(self, request, resolved, args):
        self.requests.append((request, copy.deepcopy(args)))
        tool = self.tool and len(self.requests) == 1

        async def chunks():
            for index, text in enumerate(self.texts):
                yield text_chunk(text)
                if index == 0:
                    self.first_sent.set()
                    if self.hold_after_first:
                        await asyncio.Event().wait()
            yield final_chunk(tool_parent=request.parent_request_id if tool else None,
                              tool_task=request.task_id)
        return chunks()

    async def close_request(self, parent):
        self.closed.append(parent)

    def prestart(self, request, resolved, args):
        if self.prestart_error:
            raise self.prestart_error
        self.prestarts.append((request, resolved, copy.deepcopy(args)))

    async def discard_spares(self):
        self.discarded += 1


class FakeSources:
    def __init__(self):
        self.outputs = []

    def policy_for_context(self, ctx):
        return DataPolicy("approved_external", "synthetic-fixture")

    def policy_for_projection(self, ctx, messages):
        return DataPolicy("approved_external", "synthetic-fixture")

    def model_output(self, ctx, result, policy):
        self.outputs.append((result.text, tuple(getattr(result, "tool_calls", ()))))


@pytest.fixture
def setup(monkeypatch, fresh_db):
    monkeypatch.setenv("JARVIS_LLM_ACCESS_MODE", "subscription_only")
    monkeypatch.setenv("JARVIS_MODEL_ROUTING_ENABLED", "0")
    monkeypatch.delenv(STREAM_ENV, raising=False)
    monkeypatch.delenv("JARVIS_VOICE_PRESTART_ENABLED", raising=False)
    monkeypatch.delenv("JARVIS_VOICE_EFFORT", raising=False)
    no_api = Mock(side_effect=AssertionError("API client created"))
    monkeypatch.setattr("openai.AsyncOpenAI", no_api)

    def build(native, *, streaming=True, sources=None, prestart=False):
        if prestart:
            monkeypatch.setenv(STREAM_ENV, "1")
        monkeypatch.setattr(voice, "make_route_client", lambda _: native)
        service = voice.SubscriptionVoiceLLMService(
            resolved=route(streaming=streaming), enable_direct_mode=True, sources=sources,
            policy_for_context=(None if sources else
                lambda _: DataPolicy("approved_external", "synthetic-fixture")))
        service.register_function("fixture_clock", AsyncMock())
        service.push_frame = AsyncMock()
        service.push_error = AsyncMock()
        service.run_function_calls = AsyncMock()
        service.stop_ttfb_metrics = AsyncMock()
        return service
    yield build
    no_api.assert_not_called()


def pushed(service):
    return [call.args[0] for call in service.push_frame.await_args_list]


def texts(service):
    return [frame.text for frame in pushed(service) if isinstance(frame, LLMTextFrame)]


# 1. route capability -------------------------------------------------------

def test_streaming_capability_is_opt_in_for_voice_only(monkeypatch):
    monkeypatch.setenv("JARVIS_LLM_ACCESS_MODE", "subscription_only")
    monkeypatch.delenv(STREAM_ENV, raising=False)
    off = resolve_model_route("voice_supervisor", environ={})
    assert "streaming" not in off.route.capabilities
    monkeypatch.setenv(STREAM_ENV, "0")
    assert "streaming" not in resolve_model_route(
        "voice_supervisor", environ={}).route.capabilities
    monkeypatch.setenv(STREAM_ENV, "1")
    on = resolve_model_route("voice_supervisor", environ={})
    assert on.route.capabilities == off.route.capabilities + ("streaming",)
    for workload in ("planning", "council"):
        other = resolve_model_route(workload, environ={})
        assert "streaming" not in other.route.capabilities


# 2. effort at client construction -----------------------------------------

@pytest.fixture
def native_factory(monkeypatch, tmp_path):
    built = []

    class Client:
        def __init__(self, model, **kwargs):
            built.append((model, kwargs))
    monkeypatch.setattr("jarvis.subscription_tools.ClaudeSubscriptionToolClient", Client)
    receipt = tmp_path / "receipt.json"
    receipt.write_text("{}")
    monkeypatch.setenv("JARVIS_SUBSCRIPTION_TOOLS_ENABLED", "1")
    monkeypatch.setenv("JARVIS_SUBSCRIPTION_TOOL_CAPABILITY_RECEIPT", str(receipt))
    monkeypatch.delenv("JARVIS_VOICE_EFFORT", raising=False)
    return built


def test_effort_reaches_only_the_voice_client(monkeypatch, native_factory):
    monkeypatch.setenv("JARVIS_LLM_ACCESS_MODE", "subscription_only")
    voice_route = resolve_model_route("voice_supervisor", environ={})
    other = resolve_model_route("planning", explicit_route="subscription")
    other = replace(other, route=replace(other.route, capabilities=("text", "tools")))
    make_route_client(voice_route)
    assert native_factory[-1][1] == {"effort": None}
    monkeypatch.setenv("JARVIS_VOICE_EFFORT", "low")
    make_route_client(voice_route)
    assert native_factory[-1] == ("claude-sonnet-5-5", {"effort": "low"})
    make_route_client(other)
    assert native_factory[-1][1] == {"effort": None}


@pytest.mark.parametrize("value", ["extreme", "LOW", "xhigh"])
def test_bad_effort_is_refused_when_the_voice_client_is_built(monkeypatch, native_factory, value):
    monkeypatch.setenv("JARVIS_LLM_ACCESS_MODE", "subscription_only")
    monkeypatch.setenv("JARVIS_VOICE_EFFORT", value)
    with pytest.raises(ModelRouteError, match="JARVIS_VOICE_EFFORT"):
        make_route_client(resolve_model_route("voice_supervisor", environ={}))
    assert not native_factory
    with pytest.raises(ModelRouteError, match="JARVIS_VOICE_EFFORT"):
        voice.SubscriptionVoiceLLMService(resolved=route())


def test_record_tool_menu_carries_stream_and_effort(monkeypatch, setup):
    calls = []
    monkeypatch.setattr("jarvis.subscription_tools.record_tool_menu",
                        lambda *a, **k: calls.append((a, k)))
    monkeypatch.setenv("JARVIS_VOICE_EFFORT", "medium")
    ctx = context()
    service = setup(StreamNative())
    service.record_tool_menu(ctx)
    assert calls[-1][1] == {"stream": True, "effort": "medium"}
    assert service._prestart_context is ctx
    buffered = setup(StreamNative(), streaming=False)
    buffered.record_tool_menu(ctx)
    assert calls[-1][1] == {"stream": False, "effort": "medium"}


# Startup must warm the first turn, not just the next one.
def startup_context(sources, level="approved_external"):
    system = {"role": "system", "content": "Synthetic startup system prompt."}
    sources.bind(system, DataPolicy(level, "synthetic-fixture"))
    return bound_context_type()(
        sources=sources, messages=[system], tools=context().tools)


async def test_start_frame_prestarts_before_any_prompt_and_first_turn_reuses_ids(
        setup, monkeypatch):
    native, sources = StreamNative(), VoiceSources()
    service = setup(native, prestart=True, sources=sources)
    ctx = startup_context(sources)
    menu_record = Mock()
    monkeypatch.setattr("jarvis.subscription_tools.record_tool_menu", menu_record)
    service.record_tool_menu(ctx)
    assert native.prestarts == []
    await service.process_frame(StartFrame(), FrameDirection.DOWNSTREAM)
    assert native.requests == []
    assert len(native.prestarts) == 1
    spare, _, args = native.prestarts[0]
    assert spare.context == ()
    assert args["messages"] == ctx.get_messages()
    assert spare.data_policy.level == "approved_external"
    assert menu_record.call_count == 1  # service keeps the normal menu-record call
    user = {"role": "user", "content": "Synthetic first prompt."}
    sources.bind(user, DataPolicy("approved_external", "synthetic-fixture"))
    ctx.add_message(user)
    await service._process_context(ctx)
    assert native.requests[0][0].parent_request_id == spare.parent_request_id
    assert native.requests[0][0].task_id == spare.task_id
    assert len(native.prestarts) == 2  # ordinary post-turn rearming remains
    await service.cleanup()
    assert service._next_parent_id is None
    assert native.discarded == 1


@pytest.mark.parametrize("case", ["streaming-off", "prestart-off", "no-context",
                                 "confidential", "mixed", "mutated", "unregistered"])
@pytest.mark.usefixtures("subscription_without_carry")
async def test_start_frame_never_preloads_unapproved_context(setup, monkeypatch, case):
    native, sources = StreamNative(), VoiceSources()
    if case == "prestart-off":
        monkeypatch.setenv("JARVIS_VOICE_PRESTART_ENABLED", "0")
    service = setup(native, streaming=case != "streaming-off",
                    prestart=True, sources=sources)
    ctx = startup_context(sources, "confidential" if case == "confidential" else
                          "approved_external")
    if case == "mixed":
        msg = {"role": "assistant", "content": "Synthetic history, never preload."}
        sources.bind(msg, DataPolicy("approved_external", "synthetic-fixture"))
        ctx.add_message(msg)
    if case == "mutated":
        ctx.get_messages()[0]["content"] = "Synthetic tamper after binding."
    if case == "unregistered":
        service.unregister_function("fixture_clock")
    menu_record = Mock()
    monkeypatch.setattr("jarvis.subscription_tools.record_tool_menu", menu_record)
    if case != "no-context":
        service.record_tool_menu(ctx)
    await service.process_frame(StartFrame(), FrameDirection.DOWNSTREAM)
    assert service._native_client is None
    assert native.prestarts == native.requests == []
    assert service._next_parent_id is None


async def test_stop_before_first_prompt_discards_startup_spare(setup, monkeypatch):
    native, sources = StreamNative(), VoiceSources()
    service = setup(native, prestart=True, sources=sources)
    monkeypatch.setattr("jarvis.subscription_tools.record_tool_menu", Mock())
    service.record_tool_menu(startup_context(sources))
    await service.process_frame(StartFrame(), FrameDirection.DOWNSTREAM)
    assert len(native.prestarts) == 1
    await service.process_frame(EndFrame(), FrameDirection.DOWNSTREAM)
    assert not native.requests
    assert native.discarded == 1
    assert service._next_parent_id is None
    assert service._next_task_id is None


async def test_start_frame_spare_failure_leaves_cold_first_turn_available(setup, monkeypatch):
    native, sources = StreamNative(prestart_error=RuntimeError("synthetic miss")), VoiceSources()
    service = setup(native, prestart=True, sources=sources)
    ctx = startup_context(sources)
    monkeypatch.setattr("jarvis.subscription_tools.record_tool_menu", Mock())
    service.record_tool_menu(ctx)
    await service.process_frame(StartFrame(), FrameDirection.DOWNSTREAM)
    assert service._next_parent_id is None
    service.push_error.assert_not_called()
    user = {"role": "user", "content": "Synthetic first prompt."}
    sources.bind(user, DataPolicy("approved_external", "synthetic-fixture"))
    ctx.add_message(user)
    await service._process_context(ctx)
    assert len(native.requests) == 1


# 3. streamed turn -----------------------------------------------------------

@pytest.mark.asyncio
async def test_streamed_turn_speaks_each_delta_once_and_registers_text_once(setup):
    native, sources = StreamNative(), FakeSources()
    service = setup(native, sources=sources)
    ctx = context()
    sources.context = ctx
    await service._process_context(ctx)
    assert texts(service) == ["Hello. ", "How can I help?"]
    assert sources.outputs == [("Hello. How can I help?", ())]
    # TTFB ended at the first delta (and again, harmlessly, in the finally).
    assert service.stop_ttfb_metrics.await_count >= 1
    assert native.requests[0][1]["stream"] is True
    assert native.requests[0][0].stream_text is True
    assert native.closed == [native.requests[0][0].parent_request_id]
    assert service._streamed == [] and service._streamed_meta is None


@pytest.mark.asyncio
async def test_ttfb_stops_at_first_text_not_at_result(setup):
    native = StreamNative(hold_after_first=True)
    service = setup(native)
    task = asyncio.create_task(service._process_context(context()))
    await asyncio.wait_for(native.first_sent.wait(), 2)
    await asyncio.sleep(0.05)
    assert texts(service) == ["Hello. "]
    service.stop_ttfb_metrics.assert_awaited()
    await service._close_turn()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_stream_with_no_deltas_speaks_nothing_and_does_not_fail(setup):
    class Silent(StreamNative):
        async def execute_request(self, request, resolved, args):
            self.requests.append((request, args))

            async def chunks():
                yield SimpleNamespace(id=None, usage=None, choices=[SimpleNamespace(
                    delta=SimpleNamespace(content=None, tool_calls=None), finish_reason="stop")])
            return chunks()
    service = setup(Silent())
    await service._process_context(context())
    assert texts(service) == []  # empty reply: nothing to speak


# 4. streamed tool turn ------------------------------------------------------

@pytest.mark.asyncio
async def test_streamed_tool_turn_speaks_before_the_tool_runs(setup):
    native = StreamNative(texts=("One moment.",), tool=True)
    service = setup(native)
    order = []
    service.push_frame = AsyncMock(side_effect=lambda f, *a: order.append(("frame", f)))
    service.run_function_calls = AsyncMock(side_effect=lambda calls: order.append(("tools", calls)))
    await service._process_context(context())
    kinds = [kind for kind, _ in order]
    assert kinds == ["frame", "tools"]
    assert order[0][1].text == "One moment."
    assert service._pending_assistant["content"] == "One moment."
    call = service._pending_assistant["tool_calls"][0]
    assert call["id"] == "fixture-call" and call["mortimer_parent_id"]
    assert native.closed == []  # the session stays open for the continuation
    await service._close_turn()


# 5. interruption ------------------------------------------------------------

@pytest.mark.asyncio
async def test_interruption_registers_the_spoken_prefix_once_and_drops_late_deltas(setup):
    native, sources = StreamNative(hold_after_first=True), FakeSources()
    service = setup(native, sources=sources)
    ctx = context()
    sources.context = ctx
    task = asyncio.create_task(service._process_context(ctx))
    await asyncio.wait_for(native.first_sent.wait(), 2)
    await asyncio.sleep(0.05)
    await service.process_frame(InterruptionFrame(), FrameDirection.DOWNSTREAM)
    with pytest.raises(asyncio.CancelledError):
        await task
    assert sources.outputs == [("Hello. ", ())]
    assert texts(service) == ["Hello. "]
    assert native.closed
    # A late delta from the dead generation is ignored by the sink.
    await service._close_turn()
    assert sources.outputs == [("Hello. ", ())]


@pytest.mark.asyncio
async def test_error_after_partial_speech_still_registers_the_prefix(setup):
    class Breaks(StreamNative):
        async def execute_request(self, request, resolved, args):
            async def chunks():
                yield text_chunk("Partial ")
                raise RuntimeError("PRIVATE_PROVIDER_ERROR_CANARY")
            return chunks()
    sources = FakeSources()
    service = setup(Breaks(), sources=sources)
    ctx = context()
    sources.context = ctx
    from pipecat.frames.frames import LLMContextFrame
    await service.process_frame(LLMContextFrame(ctx), FrameDirection.DOWNSTREAM)
    assert sources.outputs == [("Partial ", ())]
    assert service.push_error.await_args.kwargs == {
        "error_msg": "Subscription voice request unavailable"}


# 6. pre-start ----------------------------------------------------------------

def system_text(messages):
    return "\n\n".join(m["content"] for m in messages if m.get("role") == "system")


@pytest.mark.asyncio
async def test_prestart_after_a_turn_and_next_turn_uses_its_ids(setup):
    native = StreamNative()
    service = setup(native, prestart=True)
    ctx = context()
    service._prestart_context = ctx
    await service._schedule_prestart()          # as start() does
    assert len(native.prestarts) == 1
    await service._process_context(ctx)          # first turn uses the spare's ids
    first_request, first_args = native.requests[0]
    spare_request, spare_resolved, spare_args = native.prestarts[0]
    assert (first_request.parent_request_id, first_request.task_id) == (
        spare_request.parent_request_id, spare_request.task_id)
    assert spare_args["stream"] is True and spare_args["model"] == "claude-sonnet-5-5"
    assert all(m["role"] == "system" for m in spare_args["messages"])
    assert system_text(spare_args["messages"]) == system_text(first_args["messages"])
    assert spare_request.tools == first_request.tools == service.tool_menu_references(ctx)
    # The completed turn scheduled the next spare, with fresh ids.
    assert len(native.prestarts) == 2
    second_spare = native.prestarts[1][0]
    assert second_spare.parent_request_id != spare_request.parent_request_id
    await service._process_context(ctx)
    assert native.requests[1][0].parent_request_id == second_spare.parent_request_id
    assert native.requests[1][0].task_id == second_spare.task_id


@pytest.mark.asyncio
async def test_no_second_prestart_while_one_is_pending(setup):
    native = StreamNative()
    service = setup(native, prestart=True)
    service._prestart_context = context()
    await service._schedule_prestart()
    await service._schedule_prestart()
    assert len(native.prestarts) == 1


@pytest.mark.asyncio
async def test_an_orphaned_spare_is_discarded_before_the_next_prestart(setup):
    """A turn that took the spare's ids but failed before reaching the client
    leaves the spare in the client; it must not block every later pre-start."""
    native = StreamNative()
    native.has_spare = lambda: True
    service = setup(native, prestart=True)
    service._prestart_context = context()
    await service._schedule_prestart()
    assert native.discarded == 1 and len(native.prestarts) == 1
    assert service._next_parent_id == native.prestarts[0][0].parent_request_id


@pytest.mark.asyncio
async def test_stop_discards_the_spare(setup):
    native = StreamNative()
    service = setup(native, prestart=True)
    service._prestart_context = context()
    await service._schedule_prestart()
    service._native_client = native
    await service.stop(SimpleNamespace())
    assert native.discarded == 1
    assert service._next_parent_id is None and service._next_task_id is None


@pytest.mark.asyncio
async def test_failed_discard_marks_cleanup_unverified(setup):
    native = StreamNative()
    service = setup(native, prestart=True)
    service._native_client = native
    native.discard_spares = AsyncMock(side_effect=RuntimeError("cleanup failed"))
    with pytest.raises(RuntimeError):
        await service.cleanup()
    assert service._cleanup_failed is True


@pytest.mark.asyncio
async def test_prestart_failure_never_breaks_the_turn(setup):
    native = StreamNative(prestart_error=RuntimeError("PRIVATE_CANARY"))
    service = setup(native, prestart=True)
    ctx = context()
    service._prestart_context = ctx
    await service._schedule_prestart()
    assert service._next_parent_id is None
    await service._process_context(ctx)
    assert texts(service) == ["Hello. ", "How can I help?"]
    service.push_error.assert_not_awaited()


@pytest.mark.asyncio
async def test_prestart_can_be_turned_off_while_streaming(setup, monkeypatch):
    monkeypatch.setenv("JARVIS_VOICE_PRESTART_ENABLED", "0")
    native = StreamNative()
    service = setup(native, prestart=True)
    service._prestart_context = context()
    await service._schedule_prestart()
    await service._process_context(context())
    assert not native.prestarts
    assert texts(service) == ["Hello. ", "How can I help?"]


@pytest.mark.asyncio
async def test_interruption_reschedules_a_spare_only_when_none_is_pending(setup):
    native = StreamNative()
    service = setup(native, prestart=True)
    service._prestart_context = context()
    await service.process_frame(InterruptionFrame(), FrameDirection.DOWNSTREAM)
    assert len(native.prestarts) == 1
    await service.process_frame(InterruptionFrame(), FrameDirection.DOWNSTREAM)
    assert len(native.prestarts) == 1


# 7. flag off ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_flag_off_is_the_buffered_path_with_no_sink_stream_or_prestart(setup, monkeypatch):
    class Buffered(StreamNative):
        async def execute_request(self, request, resolved, args):
            self.requests.append((request, copy.deepcopy(args)))
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
                content="Synthetic clock says noon.", tool_calls=[], model_extra={}))], usage=None)
    seen = {}
    real = voice.execute_chat

    def spy(request, resolved, **kwargs):
        seen.update(kwargs, request=request)
        return real(request, resolved, **kwargs)
    monkeypatch.setattr(voice, "execute_chat", spy)
    native = Buffered()
    service = setup(native, streaming=False)
    assert service._streaming is False and service._prestart is False
    await service._schedule_prestart()
    await service.process_frame(InterruptionFrame(), FrameDirection.DOWNSTREAM)
    await service._process_context(context())
    assert "event_sink" not in seen and seen["request"].stream_text is False
    assert "stream" not in native.requests[0][1]
    assert texts(service) == ["Synthetic clock says noon."]
    assert native.prestarts == []
    await service.stop(SimpleNamespace())
    assert native.discarded == 0


@pytest.mark.asyncio
async def test_prestart_needs_the_streaming_env_even_on_a_streaming_route(setup):
    native = StreamNative()
    service = setup(native, prestart=False)  # route streams, env flag unset
    assert service._streaming is True and service._prestart is False
    service._prestart_context = context()
    await service._schedule_prestart()
    assert native.prestarts == []
