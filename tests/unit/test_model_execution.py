import asyncio
import threading
from dataclasses import replace
from types import SimpleNamespace

import pytest

from jarvis.bot.shared_content import normalize_shared_content
from jarvis.model_execution import (
    ModelAdmissionController,
    ModelAttachment,
    ModelContextMessage,
    ModelExecutionEvent,
    ModelExecutionInputError,
    ModelExecutionOutputError,
    ModelExecutionRequest,
    ModelOutputRequirements,
    ModelToolCall,
    ModelToolReference,
    execute_chat,
)
from jarvis.model_routing import AccessRoute, ModelRouteError, ResolvedModelRoute
from jarvis.privacy_policy import DataPolicy


class FakeCompletions:
    def __init__(self, *, delay=0, response=None):
        self.kwargs = None
        self.delay = delay
        self.cancelled = False
        self.response = response

    async def create(self, **kwargs):
        self.kwargs = kwargs
        if self.delay:
            try:
                await asyncio.sleep(self.delay)
            except asyncio.CancelledError:
                self.cancelled = True
                raise
        return self.response or SimpleNamespace(choices=[SimpleNamespace(
            message=SimpleNamespace(content="ok"))])


class FakeClient:
    def __init__(self, *, delay=0, response=None):
        self.completions = FakeCompletions(delay=delay, response=response)
        self.chat = SimpleNamespace(completions=self.completions)


class FakeAsyncStream:
    def __init__(self, chunks):
        self.chunks = chunks
        self.closed = False

    def __aiter__(self):
        async def iterate():
            for chunk in self.chunks:
                yield chunk
        return iterate()

    async def aclose(self):
        self.closed = True


class FakeStreamingClient:
    def __init__(self, chunks):
        self.stream = FakeAsyncStream(chunks)
        self.kwargs = None

        async def create(**kwargs):
            self.kwargs = kwargs
            return self.stream

        self.chat = SimpleNamespace(completions=SimpleNamespace(create=create))


class BlockingAsyncStream(FakeAsyncStream):
    def __init__(self, first_chunk):
        super().__init__([first_chunk])
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    def __aiter__(self):
        async def iterate():
            yield self.chunks[0]
            self.started.set()
            await self.release.wait()
        return iterate()


def resolved_route(*, privacy="confidential", capabilities=("text", "images")):
    return ResolvedModelRoute(
        workload="developer", profile_name="test", model="m", provider="test",
        base_url="https://example.invalid", identity="test/m",
        route=AccessRoute("saygm", "saygm_gateway", "saygm_credit", "SAYGM_API_KEY",
                          privacy, capabilities=capabilities),
        api_key_env="SAYGM_API_KEY",
    )


@pytest.mark.asyncio
async def test_execution_preserves_parent_request_and_route_metadata():
    route = resolved_route(capabilities=("text",))
    client = FakeClient()
    result = await execute_chat(
        ModelExecutionRequest("developer", "task-1", "parent-1", "hello"),
        route,
        client_factory=lambda _: client,
        admission=ModelAdmissionController(),
    )
    assert result.text == "ok"
    assert result.parent_request_id == "parent-1"
    assert result.billing == "saygm_credit"
    assert result.data_policy.level == "confidential"
    assert client.completions.kwargs["messages"] == [
        {"role": "user", "content": "hello"}
    ]


@pytest.mark.asyncio
async def test_execution_forwards_only_approved_anthropic_effort_parameter():
    route = replace(resolved_route(), provider="anthropic")
    client = FakeClient()
    await execute_chat(
        ModelExecutionRequest(
            "developer", "task-effort", "parent-effort", "hello",
            extra_body={"output_config": {"effort": "medium"}},
        ),
        route, client_factory=lambda _: client,
        admission=ModelAdmissionController(),
    )
    assert client.completions.kwargs["extra_body"] == {
        "output_config": {"effort": "medium"}
    }


@pytest.mark.asyncio
async def test_execution_preserves_explicit_temperature_and_omits_none():
    client = FakeClient()
    await execute_chat(
        ModelExecutionRequest(
            "developer", "task-temperature", "parent-temperature", "hello",
            temperature=0.2,
        ),
        resolved_route(), client_factory=lambda _: client,
        admission=ModelAdmissionController(),
    )
    assert client.completions.kwargs["temperature"] == 0.2

    omitted = FakeClient()
    await execute_chat(
        ModelExecutionRequest(
            "developer", "task-temperature-none", "parent-temperature-none", "hello",
        ),
        resolved_route(), client_factory=lambda _: omitted,
        admission=ModelAdmissionController(),
    )
    assert "temperature" not in omitted.completions.kwargs


@pytest.mark.asyncio
async def test_execution_rejects_unapproved_provider_parameters_before_client_creation():
    created = []
    request = ModelExecutionRequest(
        "developer", "task-param", "parent-param", "hello",
        extra_body={"arbitrary": "value"},
    )
    with pytest.raises(ModelExecutionInputError):
        await execute_chat(
            request, resolved_route(),
            client_factory=lambda route: created.append(FakeClient()),
            admission=ModelAdmissionController(),
        )
    assert created == []


@pytest.mark.asyncio
async def test_execution_emits_ordered_policy_carrying_lifecycle_events():
    events = []
    request = ModelExecutionRequest(
        "developer", "task-event", "parent-event", "hello",
        data_policy=DataPolicy("confidential", "test-source"),
    )
    result = await execute_chat(
        request, resolved_route(), client_factory=lambda _: FakeClient(),
        event_sink=events.append,
        admission=ModelAdmissionController(),
    )
    assert result.text == "ok"
    assert all(isinstance(event, ModelExecutionEvent) for event in events)
    assert [event.event_type for event in events] == [
        "queued", "started", "progress", "progress", "completed",
    ]
    assert [event.sequence for event in events] == [1, 2, 3, 4, 5]
    assert [event.progress_stage for event in events if event.event_type == "progress"] == [
        "provider_request", "response_received",
    ]
    assert {(event.task_id, event.parent_request_id) for event in events} == {
        ("task-event", "parent-event")
    }
    assert all(event.data_policy.level == "confidential" for event in events)


@pytest.mark.asyncio
async def test_tool_result_lifecycle_event_contains_identity_without_result_content():
    events = []
    reference = ModelToolReference(
        "kb_search", {"type": "object", "properties": {"query": {"type": "string"}}},
    )
    request = ModelExecutionRequest(
        "developer", "task-tool-result-event", "parent-tool-result-event", "Continue.",
        context=(
            ModelContextMessage("assistant", "", tool_calls=(ModelToolCall(
                "call-search-1", "kb_search", {"query": "orb"},
            ),)),
            ModelContextMessage(
                "tool", "Sensitive search result content", name="kb_search",
                tool_call_id="call-search-1",
                data_policy=DataPolicy("local_only", "tool-result"),
            ),
        ),
        tools=(reference,),
    )
    result = await execute_chat(
        request, resolved_route(privacy="local_only", capabilities=("text", "tools")),
        client_factory=lambda _: FakeClient(), event_sink=events.append,
        admission=ModelAdmissionController(),
    )

    assert result.text == "ok"
    assert [event.event_type for event in events] == [
        "queued", "started", "tool_result", "progress", "progress", "completed",
    ]
    tool_result = events[2]
    assert tool_result.sequence == 3
    assert tool_result.task_id == "task-tool-result-event"
    assert tool_result.parent_request_id == "parent-tool-result-event"
    assert tool_result.tool_call_id == "call-search-1"
    assert tool_result.tool_name == "kb_search"
    assert tool_result.data_policy.level == "local_only"
    assert not hasattr(tool_result, "content")
    assert all("Sensitive search result content" not in repr(event) for event in events)


@pytest.mark.asyncio
async def test_streamed_text_emits_policy_carrying_deltas_and_collects_compat_result():
    client = FakeStreamingClient([
        SimpleNamespace(id="response-1", usage=None, choices=[SimpleNamespace(
            delta=SimpleNamespace(content="Hello", tool_calls=[]), finish_reason=None,
        )]),
        SimpleNamespace(id="response-1", usage=None, choices=[SimpleNamespace(
            delta=SimpleNamespace(content=" world", tool_calls=[]), finish_reason=None,
        )]),
        SimpleNamespace(id="response-1", usage=SimpleNamespace(
            prompt_tokens=7, completion_tokens=2, total_tokens=9,
        ), choices=[SimpleNamespace(
            delta=SimpleNamespace(content=None, tool_calls=[]), finish_reason="stop",
        )]),
    ])
    events = []
    route = resolved_route(capabilities=("text", "streaming"))
    result = await execute_chat(
        ModelExecutionRequest(
            "developer", "task-stream-text", "parent-stream-text", "hello",
            data_policy=DataPolicy("confidential", "stream-test"), stream_text=True,
        ), route, client_factory=lambda _: client, event_sink=events.append,
        event_sink_policy=DataPolicy("local_only", "local-test"),
        admission=ModelAdmissionController(),
    )
    assert client.kwargs["stream"] is True
    assert result.text == "Hello world"
    assert result.prompt_tokens == 7 and result.completion_tokens == 2
    deltas = [event for event in events if event.event_type == "text_delta"]
    assert [event.text_delta for event in deltas] == ["Hello", " world"]
    assert all(event.data_policy.level == "confidential" for event in deltas)
    assert events[-1].event_type == "completed"
    assert client.stream.closed


@pytest.mark.asyncio
async def test_streamed_tool_arguments_are_not_exposed_before_validation():
    tool_reference = ModelToolReference(
        "kb_search", {"type": "object", "properties": {"query": {"type": "string"}}},
    )
    client = FakeStreamingClient([
        SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(
            tool_calls=[SimpleNamespace(index=0, id="call-1", function=SimpleNamespace(
                name="kb_search", arguments=""), model_extra={})], content=None,
        ), finish_reason=None)]),
        SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(
            tool_calls=[SimpleNamespace(index=0, id=None, function=SimpleNamespace(
                name=None, arguments='{"query":"orb"}'), model_extra={})], content=None,
        ), finish_reason=None)]),
        SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(
            tool_calls=[], content=None,
        ), finish_reason="tool_calls")]),
    ])
    events = []
    result = await execute_chat(
        ModelExecutionRequest(
            "developer", "task-stream-tool", "parent-stream-tool", "find",
            tools=(tool_reference,), stream_text=True,
        ), resolved_route(capabilities=("text", "tools", "streaming")),
        client_factory=lambda _: client, event_sink=events.append,
        event_sink_policy=DataPolicy("local_only", "local-test"),
        admission=ModelAdmissionController(),
    )
    assert result.tool_calls[0].arguments == {"query": "orb"}
    assert [event.event_type for event in events if event.event_type in {
        "tool_request", "tool_result", "text_delta"
    }] == ["tool_request"]
    assert events[-1].event_type == "completed"


@pytest.mark.asyncio
async def test_streaming_capability_is_required_before_client_creation():
    created = []
    with pytest.raises(ModelRouteError, match="streaming"):
        await execute_chat(
            ModelExecutionRequest(
                "developer", "task-stream-disabled", "parent-stream-disabled", "hello",
                stream_text=True,
            ), resolved_route(), client_factory=lambda _: created.append(True),
        )
    assert created == []


@pytest.mark.asyncio
async def test_streamed_text_requires_a_sink_policy_that_allows_the_result():
    created = []
    request = ModelExecutionRequest(
        "developer", "task-stream-policy", "parent-stream-policy", "hello",
        data_policy=DataPolicy("confidential", "protected"), stream_text=True,
    )
    with pytest.raises(ModelExecutionInputError, match="classified event sink"):
        await execute_chat(
            request, resolved_route(capabilities=("text", "streaming")),
            client_factory=lambda _: created.append(True), event_sink=lambda _: None,
        )
    with pytest.raises(ModelRouteError, match="provides 'approved_external'"):
        await execute_chat(
            request, resolved_route(capabilities=("text", "streaming")),
            client_factory=lambda _: created.append(True), event_sink=lambda _: None,
            event_sink_policy=DataPolicy("approved_external", "external-sink"),
        )
    assert created == []


@pytest.mark.asyncio
async def test_stream_without_finish_marker_fails_and_closes_transport():
    client = FakeStreamingClient([
        SimpleNamespace(choices=[SimpleNamespace(
            delta=SimpleNamespace(content="partial", tool_calls=[]), finish_reason=None,
        )]),
    ])
    events = []
    with pytest.raises(ModelExecutionOutputError, match="finish marker"):
        await execute_chat(
            ModelExecutionRequest(
                "developer", "task-stream-incomplete", "parent-stream-incomplete", "hello",
                stream_text=True,
            ), resolved_route(capabilities=("text", "streaming")),
            client_factory=lambda _: client, event_sink=events.append,
            event_sink_policy=DataPolicy("local_only", "local-test"),
            admission=ModelAdmissionController(),
        )
    assert client.stream.closed
    assert events[-1].event_type == "failed"
    assert events[-1].error_code == "ModelExecutionOutputError"


@pytest.mark.asyncio
async def test_stream_rejects_changed_response_identity_and_unknown_finish_reason():
    malformed_streams = [
        [
            SimpleNamespace(id="response-a", choices=[SimpleNamespace(
                delta=SimpleNamespace(content="one", tool_calls=[]), finish_reason=None,
            )]),
            SimpleNamespace(id="response-b", choices=[SimpleNamespace(
                delta=SimpleNamespace(content=None, tool_calls=[]), finish_reason="stop",
            )]),
        ],
        [SimpleNamespace(id="response-a", choices=[SimpleNamespace(
            delta=SimpleNamespace(content="one", tool_calls=[]), finish_reason="mystery",
        )])],
    ]
    for index, chunks in enumerate(malformed_streams):
        client = FakeStreamingClient(chunks)
        with pytest.raises(ModelExecutionOutputError):
            await execute_chat(
                ModelExecutionRequest(
                    "developer", f"task-stream-malformed-{index}",
                    f"parent-stream-malformed-{index}", "hello", stream_text=True,
                ), resolved_route(capabilities=("text", "streaming")),
                client_factory=lambda _, current_client=client: current_client,
                admission=ModelAdmissionController(),
            )
        assert client.stream.closed


@pytest.mark.asyncio
async def test_cancellation_closes_stream_and_emits_terminal_without_late_deltas():
    first_chunk = SimpleNamespace(choices=[SimpleNamespace(
        delta=SimpleNamespace(content="before cancel", tool_calls=[]), finish_reason=None,
    )])
    stream = BlockingAsyncStream(first_chunk)
    client = FakeStreamingClient([])
    client.stream = stream
    async def create(**kwargs):
        client.kwargs = kwargs
        return stream
    client.chat.completions.create = create
    events = []
    task = asyncio.create_task(execute_chat(
        ModelExecutionRequest(
            "developer", "task-stream-cancel", "parent-stream-cancel", "hello",
            stream_text=True,
        ), resolved_route(capabilities=("text", "streaming")),
        client_factory=lambda _: client, event_sink=events.append,
        event_sink_policy=DataPolicy("local_only", "local-test"),
        admission=ModelAdmissionController(),
    ))
    await asyncio.wait_for(stream.started.wait(), timeout=1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert stream.closed
    assert [event.event_type for event in events if event.event_type in {
        "completed", "cancelled", "failed",
    }] == ["cancelled"]
    assert [event.text_delta for event in events if event.event_type == "text_delta"] == [
        "before cancel",
    ]


@pytest.mark.asyncio
async def test_tool_reference_is_forwarded_and_result_is_validated_without_execution():
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(
            content=None,
            tool_calls=[SimpleNamespace(
                id="call-1",
                function=SimpleNamespace(name="kb_search", arguments='{"query":"orb"}'),
                model_extra={"thought_signature": "opaque-signature"},
            )],
            model_extra={"vendor_turn_state": "opaque-state"},
        ))],
        usage=SimpleNamespace(
            prompt_tokens=12, completion_tokens=5, total_tokens=17,
            prompt_tokens_details=SimpleNamespace(cached_tokens=3, cache_write_tokens=1),
        ),
    )
    client = FakeClient(response=response)
    events = []
    reference = ModelToolReference(
        "kb_search", {"type": "object", "properties": {"query": {"type": "string"}}},
        "Search the local knowledge base",
    )
    result = await execute_chat(
        ModelExecutionRequest(
            "developer", "task-tools", "parent-tools", "Find prior work.",
            tools=(reference,), output=ModelOutputRequirements(max_tokens=300),
        ),
        resolved_route(capabilities=("text", "tools")),
        client_factory=lambda _: client, event_sink=events.append,
        admission=ModelAdmissionController(),
    )
    sent = client.completions.kwargs
    assert sent["max_tokens"] == 300
    assert sent["tools"][0]["function"]["name"] == "kb_search"
    assert result.tool_calls[0].arguments == {"query": "orb"}
    assert result.tool_calls[0].raw_arguments == '{"query":"orb"}'
    assert result.tool_calls[0].provider_extras == {"thought_signature": "opaque-signature"}
    assert result.provider_extras == {"vendor_turn_state": "opaque-state"}
    assert result.prompt_tokens == 12 and result.completion_tokens == 5
    assert result.total_tokens == 17 and result.duration_ms >= 0
    assert result.cache_read_tokens == 3 and result.cache_write_tokens == 1
    assert [event.event_type for event in events] == [
        "queued", "started", "progress", "progress", "tool_request", "completed"
    ]
    assert events[4].tool_call_id == "call-1" and events[4].tool_name == "kb_search"
    assert not hasattr(events[4], "arguments")


@pytest.mark.asyncio
async def test_provider_cannot_reissue_a_tool_call_id_from_request_history():
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(
            content=None,
            tool_calls=[SimpleNamespace(
                id="call-replayed",
                function=SimpleNamespace(name="kb_search", arguments='{"query":"again"}'),
                model_extra={},
            )],
            model_extra={},
        ))],
        usage=None,
    )
    events = []
    reference = ModelToolReference(
        "kb_search", {"type": "object", "properties": {"query": {"type": "string"}}},
    )
    request = ModelExecutionRequest(
        "developer", "task-tool-replay", "parent-tool-replay", "continue",
        context=(
            ModelContextMessage("assistant", "", tool_calls=(ModelToolCall(
                "call-replayed", "kb_search", {"query": "first"},
            ),)),
            ModelContextMessage(
                "tool", "first result", name="kb_search", tool_call_id="call-replayed",
            ),
        ),
        tools=(reference,),
    )
    with pytest.raises(ModelExecutionOutputError, match="tool-call identity"):
        await execute_chat(
            request, resolved_route(capabilities=("text", "tools")),
            client_factory=lambda _: FakeClient(response=response), event_sink=events.append,
            admission=ModelAdmissionController(),
        )
    assert [event.event_type for event in events] == [
        "queued", "started", "tool_result", "progress", "progress", "failed",
    ]


@pytest.mark.asyncio
async def test_provider_cannot_return_a_tool_outside_the_caller_allowlist():
    response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
        content=None,
        tool_calls=[SimpleNamespace(
            id="call-forged",
            function=SimpleNamespace(name="repo_commit_write", arguments="{}"),
        )],
    ))])
    client = FakeClient(response=response)
    events = []
    allowed = ModelToolReference("kb_search", {"type": "object"})
    with pytest.raises(ModelExecutionOutputError, match="allowlist"):
        await execute_chat(
            ModelExecutionRequest(
                "developer", "task-forged", "parent-forged", "Search.",
                tools=(allowed,),
            ),
            resolved_route(capabilities=("text", "tools")),
            client_factory=lambda _: client, event_sink=events.append,
            admission=ModelAdmissionController(),
        )
    assert [event.event_type for event in events] == [
        "queued", "started", "progress", "progress", "failed",
    ]
    assert events[-1].error_code == "ModelExecutionOutputError"


@pytest.mark.asyncio
async def test_provider_tool_arguments_must_match_registered_schema():
    response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
        content=None,
        tool_calls=[SimpleNamespace(
            id="call-invalid-args",
            function=SimpleNamespace(name="kb_search", arguments='{"query":42}'),
        )],
    ))])
    client = FakeClient(response=response)
    reference = ModelToolReference(
        "kb_search", {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
            "additionalProperties": False,
        },
    )
    with pytest.raises(ModelExecutionOutputError, match="registered schema"):
        await execute_chat(
            ModelExecutionRequest(
                "developer", "task-invalid-args", "parent-invalid-args", "Search.",
                tools=(reference,),
            ),
            resolved_route(capabilities=("text", "tools")),
            client_factory=lambda _: client,
            admission=ModelAdmissionController(),
        )


@pytest.mark.asyncio
async def test_tools_fail_before_client_creation_when_route_lacks_tools_capability():
    created = []
    reference = ModelToolReference("kb_search", {"type": "object"})
    request = ModelExecutionRequest(
        "developer", "task-no-tools", "parent-no-tools", "Search.", tools=(reference,)
    )
    with pytest.raises(ModelRouteError, match="tools"):
        await execute_chat(
            request, resolved_route(capabilities=("text",)),
            client_factory=lambda _: created.append(True),
            admission=ModelAdmissionController(),
        )
    assert created == []


@pytest.mark.asyncio
async def test_output_requirements_fail_closed_when_route_cannot_enforce_them():
    created = []
    route = resolved_route()
    route = replace(route, route=replace(route.route, adapter="subscription_runtime"))
    request = ModelExecutionRequest(
        "developer", "task-output", "parent-output", "hello",
        output=ModelOutputRequirements(max_tokens=200),
    )
    with pytest.raises(ModelRouteError, match="cannot enforce"):
        await execute_chat(request, route, client_factory=lambda _: created.append(True))
    assert created == []


@pytest.mark.asyncio
async def test_required_text_output_rejects_empty_and_non_text_provider_content():
    for content in (None, {"unexpected": "object"}):
        response = SimpleNamespace(choices=[SimpleNamespace(
            message=SimpleNamespace(content=content)
        )])
        with pytest.raises(ModelExecutionOutputError):
            await execute_chat(
                ModelExecutionRequest(
                    "developer", "task-empty", "parent-empty", "hello",
                    output=ModelOutputRequirements(require_nonempty_text=True),
                ),
                resolved_route(capabilities=("text",)),
                client_factory=lambda _, r=response: FakeClient(response=r),
                admission=ModelAdmissionController(),
            )


@pytest.mark.asyncio
async def test_background_admission_reserves_capacity_and_prioritizes_interactive():
    admission = ModelAdmissionController()
    first_background_started = asyncio.Event()
    release_first_background = asyncio.Event()
    second_background_started = asyncio.Event()
    first_interactive_started = asyncio.Event()
    release_first_interactive = asyncio.Event()
    interactive_started = asyncio.Event()

    async def hold_background(started, release=None):
        async with admission.slot("background"):
            started.set()
            if release is not None:
                await release.wait()

    async def interactive():
        async with admission.slot("interactive"):
            interactive_started.set()

    async def hold_interactive():
        async with admission.slot("interactive"):
            first_interactive_started.set()
            await release_first_interactive.wait()

    first = asyncio.create_task(
        hold_background(first_background_started, release_first_background)
    )
    await first_background_started.wait()
    occupying_interactive = asyncio.create_task(hold_interactive())
    await first_interactive_started.wait()
    second = asyncio.create_task(hold_background(second_background_started))
    await asyncio.sleep(0)
    assert not second_background_started.is_set()
    assert admission.active_counts == (1, 1)

    foreground = asyncio.create_task(interactive())
    for _ in range(20):
        if admission.waiting_interactive:
            break
        await asyncio.sleep(0)
    assert admission.waiting_interactive == 1
    assert not second_background_started.is_set()

    release_first_interactive.set()
    await asyncio.wait_for(interactive_started.wait(), timeout=1)
    await asyncio.wait_for(occupying_interactive, timeout=1)
    assert not second_background_started.is_set()
    release_first_background.set()
    await asyncio.wait_for(first, timeout=1)
    await asyncio.wait_for(foreground, timeout=1)
    await asyncio.wait_for(second_background_started.wait(), timeout=1)
    await asyncio.wait_for(second, timeout=1)
    assert admission.active_counts == (0, 0)


@pytest.mark.asyncio
async def test_execution_preserves_context_order_and_image_attachment():
    route = resolved_route()
    client = FakeClient()
    attachment = ModelAttachment(
        normalize_shared_content(kind="image", data=b"image-bytes", mime_type="image/png"),
        DataPolicy("confidential", "user-image"),
    )
    request = ModelExecutionRequest(
        "developer", "task-2", "parent-2", "Describe the image.",
        context=(ModelContextMessage("system", "Be concise."), "Earlier user context."),
        attachments=(attachment,),
    )
    await execute_chat(request, route, client_factory=lambda _: client,
                       admission=ModelAdmissionController())
    messages = client.completions.kwargs["messages"]
    assert messages[:2] == [
        {"role": "system", "content": "Be concise."},
        {"role": "user", "content": "Earlier user context."},
    ]
    blocks = messages[2]["content"]
    assert blocks[0] == {"type": "text", "text": "Describe the image."}
    assert blocks[1]["type"] == "image_url"
    assert blocks[1]["image_url"]["url"].startswith("data:image/png;base64,")
    assert messages[2]["role"] == "user"


@pytest.mark.asyncio
async def test_execution_round_trips_assistant_tool_calls_and_tool_results():
    raw_arguments = '{ "query" : "orb" }'
    call = ModelToolCall(
        "call-history-1", "kb_search", {"query": "orb"}, raw_arguments,
        {"thought_signature": "opaque-signature"},
    )
    request = ModelExecutionRequest(
        "developer", "task-tools-2", "parent-tools-2", "",
        context=(
            ModelContextMessage(
                "assistant", "", tool_calls=(call,),
                provider_extras={"vendor_turn_state": "opaque-state"},
            ),
            ModelContextMessage(
                "tool", '{"results":[]}', name="kb_search",
                tool_call_id="call-history-1",
            ),
        ),
        tools=(ModelToolReference(
            "kb_search", {"type": "object", "properties": {"query": {"type": "string"}}}
        ),),
    )
    client = FakeClient()
    await execute_chat(
        request, resolved_route(capabilities=("text", "tools")),
        client_factory=lambda _: client,
        admission=ModelAdmissionController(),
    )
    assert client.completions.kwargs["messages"] == [
        {
            "role": "assistant", "content": None,
            "tool_calls": [{
                "id": "call-history-1", "type": "function",
                "function": {"name": "kb_search", "arguments": raw_arguments},
                "thought_signature": "opaque-signature",
            }],
            "vendor_turn_state": "opaque-state",
        },
        {
            "role": "tool", "tool_call_id": "call-history-1",
            "name": "kb_search", "content": '{"results":[]}',
        },
    ]


@pytest.mark.asyncio
async def test_tool_history_requires_matching_complete_call_result_pairs():
    requests = (
        ModelExecutionRequest(
            "developer", "task-orphan", "parent-orphan", "",
            context=(ModelContextMessage(
                "tool", "{}", name="kb_search", tool_call_id="missing-call",
            ),),
        ),
        ModelExecutionRequest(
            "developer", "task-unanswered", "parent-unanswered", "",
            context=(ModelContextMessage(
                "assistant", "", tool_calls=(ModelToolCall(
                    "call-pending", "kb_search", {"query": "orb"},
                ),),
            ),),
        ),
        ModelExecutionRequest(
            "developer", "task-unallowed-history", "parent-unallowed-history", "",
            context=(
                ModelContextMessage("assistant", "", tool_calls=(ModelToolCall(
                    "call-old", "kb_search", {"query": "orb"},
                ),)),
                ModelContextMessage(
                    "tool", "{}", name="kb_search", tool_call_id="call-old",
                ),
            ),
        ),
        ModelExecutionRequest(
            "developer", "task-replayed-tool-id", "parent-replayed-tool-id", "",
            context=(
                ModelContextMessage("assistant", "", tool_calls=(ModelToolCall(
                    "call-reused", "kb_search", {"query": "first"},
                ),)),
                ModelContextMessage(
                    "tool", "first result", name="kb_search", tool_call_id="call-reused",
                ),
                ModelContextMessage("assistant", "", tool_calls=(ModelToolCall(
                    "call-reused", "kb_search", {"query": "replay"},
                ),)),
                ModelContextMessage(
                    "tool", "replayed result", name="kb_search", tool_call_id="call-reused",
                ),
            ),
        ),
    )
    created = []

    def client_factory(route):
        client = FakeClient()
        created.append(client)
        return client

    for request in requests:
        with pytest.raises(ModelExecutionInputError):
            await execute_chat(
                request, resolved_route(), client_factory=client_factory,
                admission=ModelAdmissionController(),
            )
    assert created == []


@pytest.mark.asyncio
async def test_text_and_image_attachments_keep_their_input_order():
    client = FakeClient()
    request = ModelExecutionRequest(
        "developer", "task-2b", "parent-2b", "Review both.",
        attachments=(
            ModelAttachment(normalize_shared_content(kind="text", text="first")),
            ModelAttachment(normalize_shared_content(kind="image", data=b"second",
                                                     mime_type="image/webp")),
            ModelAttachment(normalize_shared_content(kind="text", text="third")),
        ),
    )
    await execute_chat(request, resolved_route(), client_factory=lambda _: client,
                       admission=ModelAdmissionController())
    blocks = client.completions.kwargs["messages"][-1]["content"]
    assert [block["type"] for block in blocks] == ["text", "image_url", "text"]
    assert blocks[1]["image_url"]["url"].startswith("data:image/webp;base64,")
    assert "third" in blocks[2]["text"]


@pytest.mark.asyncio
async def test_text_attachment_is_transmitted_and_its_policy_is_enforced():
    client = FakeClient()
    route = resolved_route(privacy="approved_external", capabilities=("text",))
    attachment = ModelAttachment(
        normalize_shared_content(kind="text", text="source text"),
        DataPolicy("approved_external", "explicitly-approved-source"),
        approved_route="saygm",
        approved_model_identity="test/m",
    )
    request = ModelExecutionRequest(
        "developer", "task-3", "parent-3", "Summarize.",
        attachments=(attachment,),
        data_policy=DataPolicy("approved_external", "approved-task"),
    )
    result = await execute_chat(request, route, client_factory=lambda _: client,
                                admission=ModelAdmissionController())
    assert "source text" in client.completions.kwargs["messages"][-1]["content"]
    assert result.data_policy.level == "approved_external"


@pytest.mark.asyncio
async def test_external_attachment_requires_approval_for_exact_route_and_model():
    route = resolved_route(privacy="approved_external", capabilities=("text",))
    content = normalize_shared_content(kind="text", text="private document")
    for approved_route, approved_identity in ((None, None), ("direct_api", "test/m"),
                                               ("saygm", "different/model")):
        client_created = []
        request = ModelExecutionRequest(
            "developer", "task-3b", "parent-3b", "Summarize.",
            attachments=(ModelAttachment(
                content,
                DataPolicy("approved_external", "approved-share"),
                approved_route=approved_route,
                approved_model_identity=approved_identity,
            ),),
            data_policy=DataPolicy("approved_external", "approved-task"),
        )
        with pytest.raises(ModelExecutionInputError, match="approval"):
            await execute_chat(request, route,
                               client_factory=lambda _, created=client_created: created.append(True),
                               admission=ModelAdmissionController())
        assert client_created == []


@pytest.mark.asyncio
async def test_confidential_context_blocks_external_route_before_client_creation():
    created = []
    route = resolved_route(privacy="approved_external", capabilities=("text",))
    request = ModelExecutionRequest(
        "developer", "task-4", "parent-4", "hello",
        context=(ModelContextMessage("user", "private context"),),
        data_policy=DataPolicy("approved_external", "approved-task"),
    )
    with pytest.raises(ModelRouteError):
        await execute_chat(request, route, client_factory=lambda _: created.append(True))
    assert created == []


@pytest.mark.asyncio
async def test_image_capability_is_checked_before_client_creation():
    created = []
    route = resolved_route(capabilities=("text",))
    attachment = ModelAttachment(
        normalize_shared_content(kind="image", data=b"image", mime_type="image/jpeg"),
        DataPolicy("confidential", "test-image"),
    )
    request = ModelExecutionRequest(
        "developer", "task-5", "parent-5", "Describe.", attachments=(attachment,)
    )
    with pytest.raises(ModelRouteError, match="images"):
        await execute_chat(request, route, client_factory=lambda _: created.append(True))
    assert created == []


@pytest.mark.asyncio
async def test_untyped_context_and_malformed_attachments_fail_before_client_creation():
    created = []
    route = resolved_route()
    for request in (
        ModelExecutionRequest("developer", "task-6", "parent-6", "hello", context=(object(),)),
        ModelExecutionRequest("developer", "task-6b", "parent-6b", "hello", context=["mutable"]),
        ModelExecutionRequest("developer", "task-7", "parent-7", "hello", attachments=(object(),)),
    ):
        with pytest.raises(ModelExecutionInputError):
            await execute_chat(request, route, client_factory=lambda _: created.append(True))
    assert created == []


@pytest.mark.asyncio
async def test_duplicate_attachment_identity_is_rejected_before_client_creation():
    created = []
    content = normalize_shared_content(kind="text", text="same item")
    request = ModelExecutionRequest(
        "developer", "task-7b", "parent-7b", "Review.",
        attachments=(ModelAttachment(content), ModelAttachment(content)),
    )
    with pytest.raises(ModelExecutionInputError, match="duplicate"):
        await execute_chat(request, resolved_route(),
                           client_factory=lambda _: created.append(True))
    assert created == []


@pytest.mark.asyncio
async def test_route_workload_mismatch_fails_before_client_creation():
    created = []
    request = ModelExecutionRequest("memory", "task-8", "parent-8", "hello")
    with pytest.raises(ModelExecutionInputError, match="workload"):
        await execute_chat(request, resolved_route(), client_factory=lambda _: created.append(True))
    assert created == []


@pytest.mark.asyncio
async def test_request_deadline_cancels_the_await_and_returns_no_late_result():
    client = FakeClient(delay=0.1)
    events = []
    request = ModelExecutionRequest(
        "developer", "task-9", "parent-9", "hello", timeout_s=0.005
    )
    with pytest.raises(TimeoutError):
        await execute_chat(request, resolved_route(capabilities=("text",)),
                           client_factory=lambda _: client, event_sink=events.append,
                           admission=ModelAdmissionController())
    assert client.completions.kwargs is not None
    assert client.completions.cancelled
    assert [event.event_type for event in events] == [
        "queued", "started", "progress", "failed",
    ]
    assert events[-1].error_code == "timeout"


@pytest.mark.asyncio
async def test_caller_cancellation_emits_terminal_event_and_releases_capacity():
    client = FakeClient(delay=0.1)
    admission = ModelAdmissionController()
    events = []
    task = asyncio.create_task(execute_chat(
        ModelExecutionRequest("developer", "task-10", "parent-10", "hello"),
        resolved_route(capabilities=("text",)), client_factory=lambda _: client,
        event_sink=events.append, admission=admission,
    ))
    for _ in range(50):
        if client.completions.kwargs is not None:
            break
        await asyncio.sleep(0)
    assert client.completions.kwargs is not None
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert client.completions.cancelled
    assert [event.event_type for event in events] == [
        "queued", "started", "progress", "cancelled",
    ]
    assert admission.active_counts == (0, 0)


@pytest.mark.asyncio
async def test_cancellation_during_queued_event_still_emits_one_terminal_event():
    events = []
    queued_observed = asyncio.Event()
    block_queued_observer = asyncio.Event()

    async def event_sink(event):
        events.append(event)
        if event.event_type == "queued":
            queued_observed.set()
            await block_queued_observer.wait()

    task = asyncio.create_task(execute_chat(
        ModelExecutionRequest("developer", "task-queued-cancel", "parent-queued-cancel", "hello"),
        resolved_route(capabilities=("text",)), client_factory=lambda _: FakeClient(),
        event_sink=event_sink, admission=ModelAdmissionController(),
    ))
    await asyncio.wait_for(queued_observed.wait(), timeout=1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert [event.event_type for event in events] == ["queued", "cancelled"]
    assert [event.sequence for event in events] == [1, 2]


@pytest.mark.asyncio
async def test_deadline_includes_admission_wait_and_does_not_create_client():
    admission = ModelAdmissionController(max_active=1, max_background=0)
    slot_started = asyncio.Event()
    release_slot = asyncio.Event()
    events = []

    async def occupy_only_slot():
        async with admission.slot("interactive"):
            slot_started.set()
            await release_slot.wait()

    holder = asyncio.create_task(occupy_only_slot())
    await slot_started.wait()
    created = []
    request = ModelExecutionRequest(
        "developer", "task-11", "parent-11", "hello", timeout_s=0.005
    )
    with pytest.raises(TimeoutError):
        await execute_chat(
            request, resolved_route(capabilities=("text",)),
            client_factory=lambda _: created.append(True),
            event_sink=events.append, admission=admission,
        )
    assert created == []
    assert [event.event_type for event in events] == ["queued", "failed"]
    assert events[-1].error_code == "timeout"
    release_slot.set()
    await asyncio.wait_for(holder, timeout=1)
    assert admission.active_counts == (0, 0)


@pytest.mark.asyncio
async def test_process_admission_controller_shares_capacity_across_event_loops():
    admission = ModelAdmissionController(max_active=1, max_background=0)
    started = threading.Event()
    entered = threading.Event()

    def use_from_new_loop():
        async def acquire():
            started.set()
            async with admission.slot("interactive"):
                entered.set()
        asyncio.run(acquire())

    async with admission.slot("interactive"):
        worker = asyncio.create_task(asyncio.to_thread(use_from_new_loop))
        assert await asyncio.to_thread(started.wait, 1)
        await asyncio.sleep(0.1)
        assert not entered.is_set()
        assert admission.active_counts == (1, 0)
    await asyncio.wait_for(worker, timeout=1)
    assert entered.is_set()
    assert admission.active_counts == (0, 0)


@pytest.mark.asyncio
async def test_cancelled_admission_waiter_is_removed():
    admission = ModelAdmissionController(max_active=1, max_background=0)
    started = asyncio.Event()

    async def waiting_request():
        started.set()
        async with admission.slot("interactive"):
            pytest.fail("cancelled waiter must not enter the slot")

    async with admission.slot("interactive"):
        waiter = asyncio.create_task(waiting_request())
        await started.wait()
        for _ in range(50):
            if admission.waiting_interactive:
                break
            await asyncio.sleep(0.01)
        assert admission.waiting_interactive == 1
        waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiter
        for _ in range(50):
            if admission.waiting_interactive == 0:
                break
            await asyncio.sleep(0.01)
        assert admission.waiting_interactive == 0
        assert admission.active_counts == (1, 0)
    assert admission.active_counts == (0, 0)
