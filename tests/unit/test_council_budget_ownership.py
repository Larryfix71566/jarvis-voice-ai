"""Council ownership reaches actual SDK transports with synthetic fixtures."""
import asyncio
import json
import sqlite3
import threading
from types import SimpleNamespace

import httpx
import openai
import pytest
import pytest_asyncio

from jarvis import model_budget, model_execution, model_routing, usage_ledger
from jarvis.council import council as council
from jarvis.council import __main__ as cli
from jarvis.model_budget import ModelBudgetUnavailable, begin_model_task_budget
from jarvis.model_routing import WorkloadLimits, WorkloadPolicy
from jarvis.privacy_policy import DataPolicy
from jarvis.tenant import current_user_id, user_id_scope


@pytest_asyncio.fixture
async def transport_env(fresh_db, tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_MODEL_ROUTING_ENABLED", "1")
    monkeypatch.setenv("JARVIS_MODEL_PREFERENCES_ENABLED", "0")
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-unused-key")
    monkeypatch.setattr(usage_ledger, "DB_PATH", tmp_path / "costs.db")
    monkeypatch.setattr(council, "COUNCIL_LOG_DIR", tmp_path / "council")
    monkeypatch.setattr(council.council_config, "COUNCIL_SHADOW_RATE", 0)
    monkeypatch.setattr(council.council_config, "COUNCIL_JUDGE_TARGET", 1)
    profiles = [{"name": name, "model": name, "identity": f"openai/{name}",
                 "provider": "openai", "api_key_env": "OPENAI_API_KEY",
                 "base_url": "https://api.openai.com/v1", "tier": tier,
                 "temperature": .2 if name == "economy-one" else None}
                for name, tier in [("economy-one", "economy"), ("economy-two", "economy"),
                                   ("mid-one", "mid"), ("frontier-one", "frontier"),
                                   ("frontier-two", "frontier")]]
    registry = tmp_path / "upgrade_models.yaml"
    registry.write_text(json.dumps({"default": "frontier-one", "profiles": profiles}))
    monkeypatch.setenv("JARVIS_UPGRADE_MODELS", str(registry))
    state = SimpleNamespace(sent=[], clients=[], captured=[], limits={}, handler=None, client_hook=None)
    def policy(workload, *, explicit_profile=None, **kwargs):
        return WorkloadPolicy(workload, explicit_profile or (
            "frontier-one" if workload == "planning" else "economy-one"),
            "direct_api", "approved_external", "background", required_capabilities=("text",),
            minimum_quality_tier="frontier" if workload == "planning" else "economy",
            limits=state.limits.get(workload, WorkloadLimits()))
    monkeypatch.setattr(model_routing, "resolve_policy", policy)
    monkeypatch.setattr(council, "resolve_policy", policy)
    monkeypatch.setattr(usage_ledger, "load_price_map", lambda: {"models": {
        f"openai/{profile['model']}": {"input_per_m": 1, "output_per_m": 1,
            "cache_write_mult": 1, "cache_read_mult": 1} for profile in profiles}})

    async def handler(request):
        body = json.loads(request.content)
        state.sent.append(body)
        if state.handler is not None:
            await state.handler(body)
        system = body["messages"][0]["content"]
        text = ("Synthetic member plan" if system in {
            council.PROPOSER_PROMPT, council.SCOPE_ADVISOR_PROMPT,
            council.PLAN_AUTHOR_PROMPT, council.PLAN_REVIEW_PROMPT} else
            "SCORES:\nProposal A: 8.0 - synthetic\nProposal B: 7.0 - synthetic\n")
        return httpx.Response(200, json={"id": "synthetic", "object": "chat.completion",
            "created": 1, "model": body["model"], "choices": [{"index": 0,
            "finish_reason": "stop", "message": {"role": "assistant", "content": text}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}})

    def factory(route, **kwargs):
        assert kwargs.get("max_retries", 0) == 0
        if state.client_hook is not None:
            state.client_hook()
        client = openai.AsyncOpenAI(api_key="synthetic-unused-key",
            base_url="https://fixture.invalid/v1", max_retries=0,
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
        state.clients.append(client)
        return client
    monkeypatch.setattr(model_execution, "make_route_client", factory)
    execute = model_execution.execute_chat
    async def capture(request, route, **kwargs):
        state.captured.append((request, route, kwargs))
        return await execute(request, route, **kwargs)
    monkeypatch.setattr(council, "execute_chat", capture)
    try:
        yield state
    finally:
        for client in state.clients:
            await client.close()


def rows(table):
    if not usage_ledger.DB_PATH.exists():
        return []
    with sqlite3.connect(usage_ledger.DB_PATH) as connection:
        connection.row_factory = sqlite3.Row
        return [dict(row) for row in connection.execute(f"SELECT * FROM {table}")]


async def convene(**kwargs):
    return await council.convene(workflow="selfedit", placement="planner", trigger="unit",
        goal="public synthetic goal", tier=1, context={}, **kwargs)


async def test_real_members_share_one_child_and_one_parent_cost_pool(transport_env):
    state = transport_env
    state.limits["council"] = WorkloadLimits(7)
    owner = begin_model_task_budget("developer", "owned-parent", WorkloadLimits(17, 60, .1))
    report = await convene(parent_budget=owner, data_policy=DataPolicy("approved_external", "unit"))
    assert report.winner is not None and len(state.sent) == 3
    assert {body["max_tokens"] for body in state.sent} == {7}
    requests = [item[0] for item in state.captured]
    bindings = [item[2]["child_budget"] for item in state.captured]
    assert all(binding is bindings[0] for binding in bindings)
    assert {request.parent_request_id for request in requests} == {"owned-parent"}
    assert len({request.task_id for request in requests}) == 3
    assert {request.workload for request in requests} == {"council"}
    attempts = rows("model_call_budget_reservations")
    membership = rows("model_call_budget_reservation_scopes")
    assert len(attempts) == 3 and len(rows("llm_calls")) == 3
    # One cost record per attempt; memberships fund both ceilings without
    # creating a second charge or a second observed provider call.
    assert len(membership) == 6
    assert all(sum(member["reservation_id"] == attempt["reservation_id"]
                   for member in membership) == 2 for attempt in attempts)
    sent_by_model = {body["model"]: body for body in state.sent}
    assert sent_by_model["economy-one"]["temperature"] == .2
    assert "temperature" not in sent_by_model["economy-two"]


async def test_shared_ceiling_cannot_be_reset_by_next_round_or_member(transport_env):
    state = transport_env
    owner = begin_model_task_budget("developer", "owned-parent", WorkloadLimits(17, 60, .003))
    with pytest.raises(ModelBudgetUnavailable, match="^budget_spend_exhausted$"):
        await convene(parent_budget=owner)
    count = len(state.sent)
    assert count == 1 and len(rows("model_call_budget_reservations")) == 1
    with pytest.raises(ModelBudgetUnavailable, match="^budget_spend_exhausted$"):
        await convene(parent_budget=owner)
    assert len(state.sent) == count


@pytest.mark.parametrize("sponsored", [False, True])
async def test_planning_authors_and_advisers_keep_separate_workloads(transport_env, sponsored):
    state = transport_env
    state.limits["planning"] = WorkloadLimits(19, 60, .1)
    owner = (begin_model_task_budget("developer", "developer-parent", WorkloadLimits(23, 60, .2))
             if sponsored else None)
    report = await council.draft_candidates("public synthetic plan",
        members={"proposers": ["frontier-one"], "judges": ["economy-one"]}, parent_budget=owner)
    assert report.winner is None and len(report.proposals) == 1 and len(report.scores) == 1
    author, adviser = state.captured
    assert author[0].workload == author[1].workload == "planning"
    assert adviser[0].workload == adviser[1].workload == "council"
    assert author[1].profile_name == "frontier-one" and adviser[1].profile_name == "economy-one"
    assert author[0].parent_request_id == adviser[0].parent_request_id
    root_workload = "developer" if sponsored else "planning"
    assert all(item[2]["child_budget"].owner.workload == root_workload for item in state.captured)
    assert len(rows("model_call_budget_reservations")) == 2
    assert len(rows("llm_calls")) == 2


async def test_explicit_below_floor_author_refuses_before_any_model_call(transport_env):
    state = transport_env
    report = await council.draft_candidates("public plan",
        members={"proposers": ["frontier-one", "economy-one"]}, judge=False)
    assert report is None and state.sent == [] and state.clients == []


async def test_review_adviser_retains_council_economy_eligibility(transport_env):
    state = transport_env
    report = await council.draft_candidates("public review", context={"document": "public document"},
        members={"proposers": ["economy-one"]}, judge=False)
    assert report is not None and len(report.proposals) == 1
    assert len(state.sent) == 1 and state.captured[0][0].workload == "council"


async def test_owner_cancellation_drains_inflight_transport_before_publication(transport_env):
    state = transport_env
    entered, ended = asyncio.Event(), asyncio.Event()
    async def hanging(body):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            ended.set()
    state.handler = hanging
    cancel = threading.Event()
    owner = begin_model_task_budget("developer", "owned-parent", WorkloadLimits(17, 60, .1))
    operation = asyncio.create_task(convene(parent_budget=owner, cancel_event=cancel))
    try:
        await asyncio.wait_for(entered.wait(), 3)
        cancel.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(operation, 3)
    finally:
        if not operation.done():
            operation.cancel()
            await asyncio.gather(operation, return_exceptions=True)
    assert ended.is_set() and rows("llm_calls") == []


async def test_owner_cancel_during_client_setup_cannot_start_provider_request(transport_env):
    state = transport_env
    cancel = threading.Event()
    state.client_hook = cancel.set
    owner = begin_model_task_budget("developer", "owned-parent", WorkloadLimits(17, 60, .1))
    with pytest.raises(asyncio.CancelledError):
        await convene(parent_budget=owner, cancel_event=cancel)
    assert state.clients and state.sent == [] and rows("llm_calls") == []


async def test_absolute_parent_deadline_cancels_inflight_members(transport_env, monkeypatch):
    state = transport_env
    clock = SimpleNamespace(now=model_budget.time.time())
    monkeypatch.setattr(model_budget, "time", SimpleNamespace(time=lambda: clock.now))
    monkeypatch.setattr(council, "time", SimpleNamespace(time=lambda: clock.now,
        monotonic=council.time.monotonic))
    monkeypatch.setattr(model_execution, "time", SimpleNamespace(time=lambda: clock.now,
        monotonic=model_execution.time.monotonic, perf_counter=model_execution.time.perf_counter))
    owner = begin_model_task_budget("developer", "owned-parent", WorkloadLimits(17, 60, .1))
    ended = []
    async def expire(body):
        clock.now = owner.deadline_at + 1
        try:
            await asyncio.Event().wait()
        finally:
            ended.append(True)
    state.handler = expire
    with pytest.raises(ModelBudgetUnavailable, match="^budget_deadline_exhausted$"):
        await asyncio.wait_for(convene(parent_budget=owner), 3)
    assert ended and rows("llm_calls") == []
    assert model_budget.remaining_seconds(owner) == 0


async def test_sponsored_shadow_finishes_inline_under_same_binding(transport_env, monkeypatch):
    state = transport_env
    monkeypatch.setattr(council.council_config, "COUNCIL_SHADOW_RATE", 1)
    monkeypatch.setattr(council, "COUNCIL_SHADOW_INLINE", False)
    monkeypatch.setattr(council, "_last_shadow_thread", None)
    owner = begin_model_task_budget("developer", "owned-parent", WorkloadLimits(17, 60, .1))
    report = await convene(parent_budget=owner)
    assert report.winner is not None and len(state.sent) == 5
    assert council._last_shadow_thread is None
    bindings = [kwargs["child_budget"] for _, _, kwargs in state.captured]
    assert all(binding is bindings[0] for binding in bindings)
    assert len(rows("model_call_budget_reservations")) == 5


async def test_global_off_host_sponsor_refuses_without_legacy_client(transport_env, monkeypatch):
    monkeypatch.delenv("JARVIS_MODEL_ROUTING_ENABLED")
    owner = begin_model_task_budget("developer", "owned-parent", WorkloadLimits(17, 60, .1))
    monkeypatch.setattr(council.llm_client, "make_sync_client", lambda **kwargs:
                        pytest.fail("host sponsor cannot enter uncontrolled compatibility client"))
    with pytest.raises(ModelBudgetUnavailable, match="^budget_unsupported_route$"):
        await convene(parent_budget=owner)
    assert transport_env.sent == []


async def test_json_sponsor_fields_do_not_bind_an_unrelated_parent(transport_env):
    state = transport_env
    report = await council.convene(workflow="selfedit", placement="planner", trigger="unit",
        goal="public synthetic goal", tier=1, run_id="foreign-parent",
        context={"parent_budget": {"parent_request_id": "foreign-parent"},
                 "task_budget": {"scope_id": "foreign-scope"}})
    assert report.winner is not None
    assert all(request.parent_request_id != "foreign-parent" for request, _, _ in state.captured)


async def test_host_privacy_cannot_be_lowered_by_public_context(transport_env):
    report = await council.convene(workflow="selfedit", placement="planner", trigger="unit",
        goal="private synthetic goal", tier=1, context={"privacy": "approved_external"},
        data_policy=DataPolicy("confidential", "private-host-floor"))
    assert report is None and transport_env.sent == [] and transport_env.clients == []


async def test_output_only_sponsor_keeps_cap_across_rounds(transport_env):
    state = transport_env
    owner = begin_model_task_budget("developer", "owned-parent", WorkloadLimits(13))
    assert owner.scope_id is None
    for _ in range(2):
        report = await convene(parent_budget=owner)
        assert report.winner is not None
    assert len(state.sent) == 6 and {body["max_tokens"] for body in state.sent} == {13}
    assert rows("model_call_budget_reservations") == []
    assert len(rows("model_task_budgets")) == 2


async def test_standalone_round_aggregates_members_without_double_counting(transport_env):
    state = transport_env
    state.limits["council"] = WorkloadLimits(17, 60, .003)
    with pytest.raises(ModelBudgetUnavailable, match="^budget_spend_exhausted$"):
        await convene()
    assert len(state.sent) == 1
    assert len(rows("model_task_budgets")) == 1
    assert len(rows("model_call_budget_reservations")) == 1
    assert len(rows("model_call_budget_reservation_scopes")) == 1


async def test_all_member_routes_are_pinned_before_first_transport(transport_env, monkeypatch):
    state = transport_env
    state.limits["council"] = WorkloadLimits(11)
    resolver = council.resolve_model_route_checked
    checked = []
    def resolve(workload, **kwargs):
        checked.append((workload, kwargs["explicit_profile"]))
        return resolver(workload, **kwargs)
    monkeypatch.setattr(council, "resolve_model_route_checked", resolve)
    async def changed_after_first(body):
        monkeypatch.setattr(council, "resolve_model_route_checked", lambda *args, **kwargs:
                            pytest.fail("round re-resolved a pinned member after output started"))
        state.limits["council"] = WorkloadLimits(1)
    state.handler = changed_after_first
    report = await convene()
    assert report.winner is not None and len(state.sent) == 3
    assert len(checked) == 3 and len(set(checked)) == 3
    assert {body["max_tokens"] for body in state.sent} == {11}


async def test_detached_standalone_shadow_preserves_authenticated_tenant(transport_env, monkeypatch):
    state = transport_env
    state.limits["council"] = WorkloadLimits(17, 60, .1)
    monkeypatch.setattr(council.council_config, "COUNCIL_SHADOW_RATE", 1)
    monkeypatch.setattr(council, "COUNCIL_SHADOW_INLINE", False)
    monkeypatch.setattr(council, "_last_shadow_thread", None)
    seen_owners = []
    async def observe_owner(body):
        seen_owners.append(current_user_id())
    state.handler = observe_owner
    with user_id_scope("authenticated-reviewer"):
        report = await convene()
    thread = council._last_shadow_thread
    assert report.winner is not None and thread is not None
    await asyncio.to_thread(thread.join, 3)
    assert not thread.is_alive() and len(state.sent) == 5
    assert seen_owners == ["authenticated-reviewer"] * 5
    assert {row["user_id"] for row in rows("model_task_budgets")} == {"authenticated-reviewer"}


async def test_replay_fresh_budget_refuses_public_spoofed_private_payload(
    transport_env, capsys,
):
    state = transport_env
    owner = begin_model_task_budget("developer", "old-parent", WorkloadLimits(17, 60, .1))
    report = await convene(parent_budget=owner)
    state.sent.clear()
    state.captured.clear()
    clients_before = len(state.clients)
    row = cli._load_round_row(report.round_id)
    payload = council._payload_path(report.round_id, row["started_at"])
    records = [json.loads(line) for line in payload.read_text().splitlines()]
    canary = "PRIVATE_HISTORICAL_REPLAY_CANARY_d318"
    for record in records:
        if record["type"] == "round_start":
            record["context"] = {"privacy": "approved_external",
                                 "parent_budget": {"parent_request_id": "old-parent"}}
        if record["type"] == "proposal":
            record["content"] = canary
    payload.write_text("\n".join(json.dumps(record) for record in records) + "\n")
    with sqlite3.connect(usage_ledger.DB_PATH) as connection:
        connection.execute("UPDATE model_task_budgets SET deadline_at=started_at WHERE parent_request_id=?",
                           ("old-parent",))
    state.limits["council"] = WorkloadLimits(17, 60, .1)
    assert await cli._do_replay(report.round_id, "frontier", dry_run=True) == 1
    assert state.sent == [] and state.captured == [] and len(state.clients) == clients_before
    assert any(row["workload"] == "council" and row["parent_request_id"] != "old-parent"
               for row in rows("model_task_budgets"))
    output = capsys.readouterr()
    assert "no verified permitted route" in output.err
    assert canary not in output.out + output.err


async def test_enabled_replay_cannot_read_another_tenants_payload(transport_env, monkeypatch):
    with user_id_scope("authenticated-owner"):
        report = await convene()
        assert cli._load_round_row(report.round_id)["user_id"] == "authenticated-owner"
    monkeypatch.setattr(cli, "_load_payload", lambda *args, **kwargs:
                        pytest.fail("foreign tenant payload cannot be read"))
    transport_env.sent.clear()
    with user_id_scope("other-reviewer"):
        assert await cli._do_replay(report.round_id, "frontier", dry_run=True) == 1
    assert transport_env.sent == []
