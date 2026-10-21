import asyncio
import copy
import json
from types import SimpleNamespace

import pytest
from pipecat.frames.frames import FunctionCallInProgressFrame
from pipecat.processors.aggregators.llm_response_universal import LLMContextAggregatorPair

from jarvis.privacy_policy import DataPolicy, issue_tool_result
from jarvis.voice_sources import (
    ClassifiedText, VoiceSources, UNKNOWN, bound_context_type,
    observe_source, source_scope, text_policy,
)
from tests.unit.test_subscription_voice import Native, context as synthetic_context, setup

PUBLIC = DataPolicy("approved_external", "synthetic-public-source")
LOCAL = DataPolicy("local_only", "synthetic-local-source")


def public_context():
    sources = VoiceSources()
    message = {"role": "user", "content": "synthetic public request"}
    sources.bind(message, PUBLIC)
    context = bound_context_type()(sources=sources, messages=[message])
    return sources, context


def test_copy_mutation_and_wire_labels_cannot_supply_provenance():
    sources, context = public_context()
    assert sources.policy_for_context(context).level == "approved_external"
    clone = copy.deepcopy(context.get_messages()[0])
    clone["data_policy"] = "approved_external"
    context.add_message(clone)
    assert sources.policy_for_context(context).level == "confidential"
    other, ctx = public_context()
    ctx.get_messages()[0]["content"] = "private replacement"
    assert other.policy_for_context(ctx).level == "confidential"


def test_local_floor_survives_rewrite_deletion_and_new_public_turn():
    sources, context = public_context()
    message = sources.append(context, ClassifiedText("synthetic protected result", LOCAL))
    sources.rewrite(message, lambda item: item.update(content="Result already relayed"))
    assert sources.message_policy(message).level == "local_only"
    context.set_messages([])
    sources.append(context, ClassifiedText("new public turn", PUBLIC))
    assert sources.policy_for_context(context).level == "local_only"


def test_serialized_text_and_another_context_cannot_reuse_host_authority():
    value = ClassifiedText("synthetic result", LOCAL)
    assert text_policy(value).level == "local_only"
    assert text_policy(ClassifiedText(value, PUBLIC)).level == "local_only"
    assert text_policy(json.loads(json.dumps(value))).level == "confidential"
    with pytest.raises(AttributeError):
        value._policy = PUBLIC
    sources, _ = public_context()
    _, other = public_context()
    assert sources.policy_for_context(other).level == "confidential"


def test_nested_scope_cannot_lower_parent_source_floor():
    with source_scope(LOCAL):
        with source_scope(PUBLIC) as child:
            assert child.policy.level == "local_only"


def test_rebuilt_context_gets_new_identities_but_cannot_drop_the_old_floor():
    sources, original = public_context()
    sources.append(original, ClassifiedText("synthetic local-only result", LOCAL))
    child = sources.for_new_context()
    message = {"role": "system", "content": "new public instructions"}
    child.bind(message, PUBLIC)
    rebuilt = bound_context_type()(sources=child, messages=[message])
    assert sources.context is original and child.context is rebuilt
    assert child.policy_for_context(rebuilt).level == "local_only"
    assert child.policy_for_context(original).level == "local_only"


@pytest.mark.parametrize("policy", [PUBLIC, LOCAL])
async def test_real_pipecat_tool_materialization_keeps_exact_result_policy(policy):
    sources, context = public_context()
    call = SimpleNamespace(tool_call_id="synthetic-call", name="fixture_tool", arguments={})
    sources.model_output(context, SimpleNamespace(text="", tool_calls=[call]), PUBLIC)
    assistant = LLMContextAggregatorPair(context).assistant()
    await assistant._handle_function_call_in_progress(FunctionCallInProgressFrame(
        function_name="fixture_tool", tool_call_id=call.tool_call_id, arguments={},
        cancel_on_interruption=True))
    assert sources.policy_for_context(context).level == "approved_external"
    sources.tool_result(call.tool_call_id, "synthetic result", policy)
    assistant._update_function_call_result("fixture_tool", call.tool_call_id,
                                          json.dumps("synthetic result", ensure_ascii=False))
    assert sources.policy_for_context(context).level == policy.level
    placeholder = context.get_messages()[-1]
    assert sources.message_policy(placeholder).level == policy.level
    placeholder["content"] = '"different private bytes"'
    assert sources.policy_for_context(context).level == (
        "local_only" if policy is LOCAL else "confidential")


async def test_parallel_and_cancelled_source_scopes_do_not_cross_tasks():
    ready = asyncio.Event()
    release = asyncio.Event()
    async def protected():
        with source_scope(PUBLIC) as scope:
            observe_source(LOCAL)
            ready.set()
            await release.wait()
        return scope.policy
    task = asyncio.create_task(protected())
    await ready.wait()
    with source_scope(PUBLIC) as sibling:
        assert sibling.policy.level == "approved_external"
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert sibling.policy.level == "approved_external"
    with source_scope() as fresh:
        assert fresh.policy is None


async def test_actual_base_loop_exports_acquired_local_only_floor():
    from tests.unit.test_subagent_tool_policy import routed
    from tests.unit.test_subagent import FakeRegistry
    from jarvis.bot.sensitive_turn import SensitiveTurn, current_sensitive_turn
    class LocalRegistry(FakeRegistry):
        async def call_classified(self, *_args, execution_scope):
            return issue_tool_result(execution_scope, "synthetic private bytes",
                source_policy=LOCAL, source_scope="synthetic_local")
    subject, provider = routed(LocalRegistry(), private=True)
    token = current_sensitive_turn.set(SensitiveTurn())
    try:
        with source_scope(PUBLIC) as scope:
            result = await subject.run("synthetic task", private_result_sink=lambda *_: None)
        assert scope.policy.level == "local_only"
        assert "synthetic private bytes" not in result
        assert len(provider.requests) == 1
    finally:
        current_sensitive_turn.reset(token)


async def test_delegate_immediate_result_keeps_source_without_changing_text():
    from jarvis.agents.delegate import build_delegate_tool
    from tests.unit.test_delegate import SlowFakeSubAgent
    from jarvis.bot.sensitive_turn import SensitiveTurn, current_sensitive_turn
    class LocalAgent(SlowFakeSubAgent):
        async def run(self, *_args, **_kwargs):
            observe_source(LOCAL)
            return "synthetic completed result"
    _, handler = build_delegate_tool({"analyst": LocalAgent("analyst")})
    token = current_sensitive_turn.set(SensitiveTurn())
    try:
        with source_scope(PUBLIC):
            result = await handler({"agent_name": "analyst", "task": "synthetic request"})
        assert str(result) == "synthetic completed result"
        assert text_policy(result).level == "local_only"
    finally:
        current_sensitive_turn.reset(token)


def test_memory_snapshot_is_classified_without_changing_rendered_bytes():
    from jarvis.memory import classify_memory_context
    original = "synthetic retained memory"
    result = classify_memory_context(original)
    assert str(result) == original
    assert result.policy.level == "confidential"


async def test_native_adapter_continues_actual_pipecat_projection_with_bound_sources(setup):
    native = Native(tool=True)
    service = setup(native)
    sources = VoiceSources()
    original = synthetic_context()
    for message in original.get_messages():
        sources.bind(message, PUBLIC)
    context = bound_context_type()(sources=sources, messages=original.get_messages(), tools=original.tools)
    service.sources = sources
    service.policy_for_context = sources.policy_for_context
    assistant = LLMContextAggregatorPair(context).assistant()
    try:
        await service._process_context(context)
        context.add_message({"role": "assistant", "content": "Checking."})
        await assistant._handle_function_call_in_progress(FunctionCallInProgressFrame(
            function_name="fixture_clock", tool_call_id="fixture-call", arguments={},
            cancel_on_interruption=True))
        sources.tool_result("fixture-call", "noon", PUBLIC)
        assistant._update_function_call_result("fixture_clock", "fixture-call", json.dumps("noon"))
        await service._process_context(context)
        assert len(native.requests) == 2
        assert native.requests[0][0].parent_request_id == native.requests[1][0].parent_request_id
        assert sources.policy_for_context(context).level == "approved_external"
        context.add_message({"role": "assistant", "content": "Synthetic clock says noon."})
        sources.append(context, ClassifiedText("Repeat the synthetic answer.", PUBLIC))
        await service._process_context(context)
        assert len(native.requests) == 3
        assert native.requests[2][0].parent_request_id != native.requests[1][0].parent_request_id
    finally:
        await service.cleanup()


async def test_cancelled_delegate_late_result_retains_policy_after_scope_restoration():
    from jarvis.agents.delegate import build_delegate_tool
    from tests.unit.test_delegate import SlowFakeSubAgent
    from jarvis.bot.sensitive_turn import SensitiveTurn, current_sensitive_turn
    started, release, delivered = asyncio.Event(), asyncio.Event(), asyncio.Event()
    notes = []
    class LocalAgent(SlowFakeSubAgent):
        async def run(self, *_args, **_kwargs):
            started.set()
            await release.wait()
            observe_source(LOCAL)
            return "synthetic private late result"
    async def deliver(note):
        notes.append(note)
        delivered.set()
        return True
    _, handler = build_delegate_tool({"analyst": LocalAgent("analyst")}, late_delivery={"fn": deliver})
    token = current_sensitive_turn.set(SensitiveTurn())
    try:
        with source_scope(PUBLIC):
            turn = asyncio.create_task(handler({"agent_name": "analyst", "task": "synthetic late request"}))
        await started.wait()
        turn.cancel()
        with pytest.raises(asyncio.CancelledError):
            await turn
        with source_scope(PUBLIC) as unrelated:
            release.set()
            await asyncio.wait_for(delivered.wait(), 2)
            assert unrelated.policy.level == "approved_external"
        assert len(notes) == 1 and text_policy(notes[0]).level == "local_only"
    finally:
        release.set()
        current_sensitive_turn.reset(token)


async def test_native_adapter_checks_materialized_payload_after_classification(setup, monkeypatch):
    from jarvis.model_routing import ModelRouteError
    native = Native()
    service = setup(native)
    sources = VoiceSources()
    context = synthetic_context()
    sources.context = context
    for message in context.get_messages():
        sources.bind(message, PUBLIC)
    service.sources = sources
    service.policy_for_context = sources.policy_for_context
    adapter = service.get_llm_adapter()
    original = adapter.get_llm_invocation_params
    def changed_projection(ctx, **kwargs):
        params = original(ctx, **kwargs)
        params['messages'] = copy.deepcopy(params['messages'])
        params['messages'][0]['content'] = 'SYNTHETIC_UNCLASSIFIED_PROJECTION'
        return params
    monkeypatch.setattr(adapter, 'get_llm_invocation_params', changed_projection)
    try:
        with pytest.raises(ModelRouteError):
            await service._process_context(context)
        assert native.requests == []
    finally:
        await service.cleanup()
