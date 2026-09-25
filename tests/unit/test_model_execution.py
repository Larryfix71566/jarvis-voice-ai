import asyncio
from dataclasses import replace
from types import SimpleNamespace

import pytest

from jarvis.bot.shared_content import normalize_shared_content
from jarvis.model_execution import (
    ModelAttachment,
    ModelAdmissionController,
    ModelContextMessage,
    ModelExecutionEvent,
    ModelExecutionInputError,
    ModelExecutionRequest,
    ModelExecutionOutputError,
    ModelOutputRequirements,
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
    assert [event.event_type for event in events] == ["queued", "started", "completed"]
    assert [event.sequence for event in events] == [1, 2, 3]
    assert {(event.task_id, event.parent_request_id) for event in events} == {
        ("task-event", "parent-event")
    }
    assert all(event.data_policy.level == "confidential" for event in events)


@pytest.mark.asyncio
async def test_tool_reference_is_forwarded_and_result_is_validated_without_execution():
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(
            content=None,
            tool_calls=[SimpleNamespace(
                id="call-1",
                function=SimpleNamespace(name="kb_search", arguments='{"query":"orb"}'),
            )],
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
    assert result.prompt_tokens == 12 and result.completion_tokens == 5
    assert result.total_tokens == 17 and result.duration_ms >= 0
    assert result.cache_read_tokens == 3 and result.cache_write_tokens == 1
    assert [event.event_type for event in events] == [
        "queued", "started", "tool_request", "completed"
    ]
    assert events[2].tool_call_id == "call-1" and events[2].tool_name == "kb_search"
    assert not hasattr(events[2], "arguments")


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
    assert [event.event_type for event in events] == ["queued", "started", "failed"]
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
                               client_factory=lambda _: client_created.append(True),
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
    assert [event.event_type for event in events] == ["queued", "started", "failed"]
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
    assert [event.event_type for event in events] == ["queued", "started", "cancelled"]
    assert admission.active_counts == (0, 0)


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
async def test_process_admission_controller_rejects_a_second_event_loop():
    admission = ModelAdmissionController()
    async with admission.slot("interactive"):
        pass

    def use_from_new_loop():
        async def acquire():
            async with admission.slot("interactive"):
                pass
        asyncio.run(acquire())

    with pytest.raises(RuntimeError, match="another event loop"):
        await asyncio.to_thread(use_from_new_loop)
