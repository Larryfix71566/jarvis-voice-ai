"""Independent WS-05 boundary probes; SDK requests stop at MockTransport."""
import asyncio
from dataclasses import replace
import json
import math
import sqlite3
from types import SimpleNamespace
from unittest.mock import patch

import anthropic
import httpx
import openai
import pytest

from jarvis import usage_ledger
from jarvis.agents.base import SubAgent
from jarvis.anthropic_shim import AsyncAnthropicChatShim
from jarvis.bot.sensitive_turn import SensitiveTurn, current_sensitive_turn
from jarvis.model_budget import (
    ModelBudgetUnavailable, TaskBudget, begin_model_task_budget, remaining_seconds,
)
from jarvis.model_execution import ModelExecutionRequest, ModelOutputRequirements, execute_chat
from jarvis.model_preferences import confirm_preference, stage_preference
from jarvis.model_routing import AccessRoute, ResolvedModelRoute, WorkloadLimits
from jarvis.privacy_policy import DataPolicy


@pytest.fixture
def isolation(tmp_path, monkeypatch):
    costs = tmp_path / "review-costs.sqlite"
    monkeypatch.setattr(usage_ledger, "DB_PATH", costs)
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "review-preferences.sqlite"))
    monkeypatch.setenv("JARVIS_MODEL_PREFERENCES_ENABLED", "0")
    monkeypatch.setenv("JARVIS_WORKFLOWS_ENABLED", "0")
    monkeypatch.setattr(usage_ledger, "load_price_map", lambda: {"models": {
        "openai/review-model": {"input_per_m": 1, "output_per_m": 1,
                                "cache_write_mult": 1, "cache_read_mult": 1},
        "anthropic/claude-review-model": {"input_per_m": 1, "output_per_m": 1,
                                           "cache_write_mult": 1.25, "cache_read_mult": .1},
    }})
    token = current_sensitive_turn.set(SensitiveTurn())
    try:
        yield costs
    finally:
        current_sensitive_turn.reset(token)


def route(limits=WorkloadLimits(), *, native=False, anthropic=False):
    model = "claude-review-model" if anthropic else "review-model"
    provider = "subscription" if native else "anthropic" if anthropic else "openai"
    access = AccessRoute(
        "subscription" if native else "direct_api",
        "subscription_runtime" if native else "openai_compatible",
        "subscription" if native else "provider_api", None,
        "approved_external", capabilities=("text",),
    )
    return ResolvedModelRoute("developer", "review-profile", model, provider,
                              "" if native else "https://review.invalid/v1", access,
                              None, f"{provider}/{model}", limits=limits)


def request(*, parent="review-parent", task="review-task", cap=None):
    return ModelExecutionRequest(
        "developer", task, parent, "public synthetic review request",
        output=ModelOutputRequirements(max_tokens=cap),
        data_policy=DataPolicy("approved_external", "review-public-fixture"),
    )


def success(req):
    body = json.loads(req.content)
    return httpx.Response(200, json={
        "id": "review-result", "object": "chat.completion", "created": 1,
        "model": body["model"], "choices": [{"index": 0, "finish_reason": "stop",
            "message": {"role": "assistant", "content": body["model"]}}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    })


def sdk(handler, *, retries=0):
    return openai.AsyncOpenAI(
        api_key="synthetic-unused-key", base_url="https://review.invalid/v1", max_retries=retries,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


async def test_output_only_handle_survives_cleared_route_without_creating_a_store(isolation):
    budget = begin_model_task_budget("developer", "review-parent", WorkloadLimits(max_output_tokens_per_call=31))
    sent = []
    async with sdk(lambda req: sent.append(json.loads(req.content)) or success(req)) as client:
        await execute_chat(request(cap=60), route(), task_budget=budget, client_factory=lambda _route: client)
        await execute_chat(request(task="next-review-task", cap=17), route(), task_budget=budget,
                           client_factory=lambda _route: client)
    assert [body["max_tokens"] for body in sent] == [31, 17]
    assert not isolation.exists()
    assert math.isinf(remaining_seconds(budget))
    assert budget._ephemeral_seal not in repr(budget)


@pytest.mark.parametrize("changes", [
    {"limits": WorkloadLimits()},
    {"limits": WorkloadLimits(max_output_tokens_per_call=100)},
    {"parent_request_id": "other-parent"},
    {"workload": "analyst"},
    {"scope_id": "pretend-durable-scope"},
    {"_ephemeral_seal": ""},
    {"_ephemeral_seal": "0" * 64},
    {"_ephemeral_seal": "\N{SNOWMAN}" * 64},
])
def test_transient_budget_tampering_fails_closed_without_creating_storage(isolation, changes):
    budget = begin_model_task_budget("developer", "review-parent", WorkloadLimits(max_output_tokens_per_call=31))
    with pytest.raises(ModelBudgetUnavailable, match="^budget_policy_mismatch$"):
        remaining_seconds(replace(budget, **changes))
    assert not isolation.exists()


async def test_cleared_transient_cap_is_refused_before_client_or_transport(isolation):
    budget = begin_model_task_budget("developer", "review-parent", WorkloadLimits(max_output_tokens_per_call=31))
    cleared = replace(budget, limits=WorkloadLimits())
    created = []
    with pytest.raises(ModelBudgetUnavailable, match="^budget_policy_mismatch$"):
        await execute_chat(request(), route(), task_budget=cleared,
                           client_factory=lambda _route: created.append(True))
    assert created == []
    assert not isolation.exists()


def test_bare_transient_dataclass_is_not_host_issuance_authority(isolation):
    genuine = begin_model_task_budget("developer", "review-parent", WorkloadLimits(max_output_tokens_per_call=31))
    bare = TaskBudget(genuine.user_id, genuine.workload, genuine.parent_request_id, genuine.limits)
    with pytest.raises(ModelBudgetUnavailable, match="^budget_policy_mismatch$"):
        remaining_seconds(bare)
    assert not isolation.exists()


async def test_all_null_host_scope_preserves_sdk_arguments_and_no_storage(isolation):
    budget = begin_model_task_budget("developer", "review-parent", WorkloadLimits())
    sent = []
    async with sdk(lambda req: sent.append(json.loads(req.content)) or success(req)) as client:
        await execute_chat(request(), route(), task_budget=budget, client_factory=lambda _route: client)
    assert sent == [{"model": "review-model", "messages": [
        {"role": "user", "content": "public synthetic review request"},
    ]}]
    assert not isolation.exists()


async def test_existing_durable_scope_remains_authoritative_when_handle_fields_clear(isolation):
    budget = begin_model_task_budget("developer", "review-parent", WorkloadLimits(31, 10, None))
    cleared = replace(budget, limits=WorkloadLimits(), deadline_at=None)
    sent = []
    async with sdk(lambda req: sent.append(json.loads(req.content)) or success(req)) as client:
        await execute_chat(request(), route(), task_budget=cleared, client_factory=lambda _route: client)
    assert sent[0]["max_tokens"] == 31
    with sqlite3.connect(isolation) as conn:
        row = conn.execute("SELECT max_output_tokens_per_call,deadline_at FROM model_task_budgets").fetchone()
    assert row[0] == 31
    assert row[1] == budget.deadline_at


async def test_unknown_client_retry_attribute_does_not_establish_supported_admission(isolation):
    called = []

    async def foreign_create(**_kwargs):
        called.append(True)

    foreign = SimpleNamespace(max_retries=0, chat=SimpleNamespace(completions=SimpleNamespace(create=foreign_create)))
    with pytest.raises(ModelBudgetUnavailable, match="^budget_unsupported_route$"):
        await execute_chat(request(), route(WorkloadLimits(31, None, .1)), client_factory=lambda _route: foreign)
    assert called == []


async def test_actual_anthropic_sdk_keeps_cap_and_failed_attempt_without_hidden_retries(isolation):
    sent = []

    def reject(req):
        sent.append(json.loads(req.content))
        return httpx.Response(500, json={"type": "error", "error": {
            "type": "api_error", "message": "synthetic transient refusal",
        }})

    http = httpx.AsyncClient(transport=httpx.MockTransport(reject))
    sdk_class = anthropic.AsyncAnthropic
    # Scope the constructor seam narrowly; admission sees the real SDK type
    # and retry configuration after the patch has been removed.
    with patch("jarvis.anthropic_shim.anthropic.AsyncAnthropic", side_effect=lambda **kwargs:
               sdk_class(**kwargs, http_client=http)):
        client = AsyncAnthropicChatShim(api_key="synthetic-unused-key", max_retries=0)
    try:
        resolved = route(WorkloadLimits(31, None, .003), anthropic=True)
        with pytest.raises(openai.APIStatusError):
            await execute_chat(request(), resolved, client_factory=lambda _route: client)
        with pytest.raises(ModelBudgetUnavailable, match="^budget_spend_exhausted$"):
            await execute_chat(request(task="next-review-task"), resolved, client_factory=lambda _route: client)
    finally:
        await http.aclose()
    assert len(sent) == 1
    assert sent[0]["max_tokens"] == 31
    with sqlite3.connect(isolation) as conn:
        assert conn.execute("SELECT count(*) FROM model_call_budget_reservations").fetchone()[0] == 1


def settings():
    return SimpleNamespace(openai_model="unused-fallback", openai_api_key="synthetic-unused",
                           openai_base_url="https://unused.invalid", jarvis_timezone="UTC",
                           jarvis_runlog_enabled=False, jarvis_procedures_enabled=False,
                           jarvis_model_routing_enabled=True)


def test_named_model_preflight_cannot_construct_a_new_owner_to_escape_quarantine(isolation, monkeypatch):
    native = route(native=True)
    monkeypatch.setattr("jarvis.agents.base.resolve_model_route_checked", lambda *_args, **_kwargs: native)
    created = []

    def factory(_route):
        client = SimpleNamespace(cleanup_unverified=False)
        created.append(client)
        return client

    monkeypatch.setattr("jarvis.agents.base.make_route_client", factory)
    subject = SubAgent("developer", "Developer", "review fixture", [], settings(), SimpleNamespace(),
                       model_profile="claude-opus", on_profile_fallback="refuse")
    owner = subject._routed_client_for(native)
    owner.cleanup_unverified = True

    client, model, refusal = subject.resolve_model_profile("review-profile")

    assert client is None
    assert model == ""
    assert refusal
    assert len(created) == 1


async def test_task_deadline_includes_hanging_run_association_before_client_creation(isolation, monkeypatch):
    resolved = route(WorkloadLimits(deadline_seconds=.05))
    monkeypatch.setattr("jarvis.agents.base.resolve_model_route_checked", lambda *_args, **_kwargs: resolved)
    created = []
    monkeypatch.setattr("jarvis.agents.base.make_route_client", lambda _route: created.append(True))
    subject = SubAgent("developer", "Developer", "review fixture", [], settings(), SimpleNamespace(),
                       model_profile="claude-opus", on_profile_fallback="refuse")
    cancelled = asyncio.Event()

    async def associate(_run_id):
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    result = await asyncio.wait_for(subject.run(
        "public synthetic review task", on_run_created=associate, tool_specs_override=[],
    ), timeout=.5)

    assert cancelled.is_set()
    assert result.startswith("FAILED:") or "timed out" in result.lower()
    assert created == []


async def test_confirmed_saved_selection_is_used_after_agent_creation_with_actual_sdk_transport(isolation, monkeypatch):
    monkeypatch.setenv("JARVIS_MODEL_ROUTING_ENABLED", "1")
    monkeypatch.setenv("JARVIS_MODEL_PREFERENCES_ENABLED", "1")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "synthetic-unused-key")
    monkeypatch.setattr("jarvis.agents.base.record_execution_result", lambda *_args, **_kwargs: None)

    def save(profile):
        draft = stage_preference("developer", profile, "direct_api")
        confirm_preference(draft["draft_id"])

    sent, clients = [], []

    def factory(_route):
        client = sdk(lambda req: sent.append(json.loads(req.content)) or success(req))
        clients.append(client)
        return client

    monkeypatch.setattr("jarvis.agents.base.make_route_client", factory)
    save("claude-sonnet-5")
    subject = SubAgent("developer", "Developer", "review fixture", [], settings(), SimpleNamespace(),
                       model_profile="claude-sonnet-5", on_profile_fallback="refuse")
    try:
        save("claude-opus")
        result = await subject.run("public synthetic review task", tool_specs_override=[])
    finally:
        for client in clients:
            await client.close()
    assert result == "claude-opus-5"
    assert len(sent) == 1
    assert sent[0]["model"] == "claude-opus-5"
