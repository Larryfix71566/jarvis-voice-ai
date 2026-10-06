"""The actual council SDK route spends from D -> planning -> adviser pools."""
from dataclasses import replace
import json

import pytest

from jarvis import model_budget
from jarvis.council import council
from jarvis.model_routing import WorkloadLimits
from tests.unit.test_council_budget_ownership import transport_env, rows
from tests.unit.test_model_budget import isolated_budget


def coordinator(state, *, planning_limits=WorkloadLimits(9, 60, .1)):
    state.limits["planning"] = planning_limits
    state.limits["council"] = WorkloadLimits(7, 90, .2)
    owner = model_budget.begin_model_task_budget("developer", "original-developer", WorkloadLimits(23, 120, .3))
    binding = model_budget.bind_model_task_budget_for_transport(owner, "planning", planning_limits,
        started_at=owner.started_at)
    return owner, binding


async def draft(owner, binding):
    return await council.draft_candidates("synthetic public plan",
        members={"proposers": ["frontier-one"], "judges": ["economy-one"]},
        parent_budget=owner, coordinator_budget=binding)


async def test_existing_planning_scope_is_reused_and_adviser_debits_all_three_pools(transport_env):
    state = transport_env
    owner, binding = coordinator(state)
    report = await draft(owner, binding)
    assert report is not None and len(state.sent) == 2
    author, adviser = state.captured
    assert author[0].workload == author[1].workload == "planning"
    assert adviser[0].workload == adviser[1].workload == "council"
    assert author[2]["child_budget"].child.scope_id == binding.child.scope_id
    child = adviser[2]["child_budget"]
    assert child.owner.scope_id == owner.scope_id
    assert [item.scope_id for item in child._ancestors] == [binding.child.scope_id]
    assert state.sent[0]["max_tokens"] == 9 and state.sent[1]["max_tokens"] == 7
    links = rows("model_task_budget_links")
    assert {(row["child_scope_id"], row["parent_scope_id"]) for row in links} == {
        (binding.child.scope_id, owner.scope_id), (child.child.scope_id, binding.child.scope_id)}
    assert len(rows("model_call_budget_reservations")) == len(rows("llm_calls")) == 2
    memberships = rows("model_call_budget_reservation_scopes")
    assert len(memberships) == 5
    assert sorted(sum(row["reservation_id"] == attempt["reservation_id"] for row in memberships)
        for attempt in rows("model_call_budget_reservations")) == [2, 3]


async def test_planning_pool_exhaustion_refuses_adviser_before_another_client(transport_env):
    state = transport_env
    owner, binding = coordinator(state, planning_limits=WorkloadLimits(9, 60, .003))
    with pytest.raises(model_budget.ModelBudgetUnavailable, match="budget_spend_exhausted"):
        await draft(owner, binding)
    assert len(state.sent) == len(state.clients) == 1
    assert len(rows("model_call_budget_reservations")) == len(rows("llm_calls")) == 1


async def test_forged_coordinator_ancestry_refuses_before_clients(transport_env):
    state = transport_env
    owner, binding = coordinator(state)
    forged = replace(binding, _ancestors=(owner,))
    with pytest.raises(model_budget.ModelBudgetUnavailable):
        await draft(owner, forged)
    assert state.sent == state.clients == []


async def test_foreign_root_cannot_attach_the_original_planning_coordinator(transport_env):
    state = transport_env
    _, binding = coordinator(state)
    other = model_budget.begin_model_task_budget("developer", "replacement-developer", WorkloadLimits(23, 120, .3))
    with pytest.raises(model_budget.ModelBudgetUnavailable, match="budget_scope_mismatch"):
        await draft(other, binding)
    assert state.sent == state.clients == []


async def test_json_coordinator_locators_are_not_budget_authority(transport_env):
    state = transport_env
    report = await council.draft_candidates("public plan",
        members={"proposers": ["frontier-one"], "judges": ["economy-one"]},
        context={"coordinator_budget": {"scope_id": "foreign", "max_estimated_spend_usd_per_task": .1}})
    assert report is not None and len(state.sent) == 2
    assert all(item[2]["child_budget"].owner.parent_request_id != "foreign" for item in state.captured)


async def test_bare_approved_policy_cannot_approve_acquired_review_bytes(transport_env):
    from jarvis.privacy_policy import DataPolicy
    state = transport_env
    report = await council.draft_candidates("public review",
        members={"proposers": ["economy-one"]}, judge=False,
        context={"document": "UNVERIFIED_REVIEW_CONTENT_051c", "privacy": "approved_external"},
        data_policy=DataPolicy("approved_external", "unbound-label"))
    assert report is None and state.sent == state.clients == []


async def test_actual_round_preserves_nested_context_before_member_await(monkeypatch,transport_env):
    state=transport_env
    owner,binding=coordinator(state)
    context={"checks":{"outputs":["PUBLIC_ORIGINAL_SNAPSHOT_5aba"]}}
    original=council._pin_members
    mutated=False
    async def mutate_after_snapshot(*args,**kwargs):
        nonlocal mutated
        if not mutated:
            context["checks"]["outputs"][0]="PRIVATE_LATE_CONTEXT_MUTATION_5aba"
            context["document"]="PRIVATE_LATE_CONTEXT_MUTATION_5aba"
            context["privacy"]="approved_external"
            mutated=True
        return await original(*args,**kwargs)
    monkeypatch.setattr(council,"_pin_members",mutate_after_snapshot)
    result=await council.draft_candidates("public plan",context=context,
        members={"proposers":["frontier-one"],"judges":["economy-one"]},
        parent_budget=owner,coordinator_budget=binding)
    assert result is not None and mutated and len(state.sent)==2
    assert all("PUBLIC_ORIGINAL_SNAPSHOT_5aba" in json.dumps(body) for body in state.sent)
    assert all("PRIVATE_LATE_CONTEXT_MUTATION_5aba" not in json.dumps(body) for body in state.sent)
    assert [request.workload for request,route,kwargs in state.captured] == ["planning","council"]
    assert [len((kwargs["child_budget"].owner,*kwargs["child_budget"]._ancestors,kwargs["child_budget"].child)) for request,route,kwargs in state.captured] == [2,3]

async def test_actual_exclusive_sqlite_validation_respects_request_deadline(monkeypatch,isolated_budget):
    import asyncio, sqlite3, threading
    from dataclasses import replace
    from jarvis import model_budget,model_execution,usage_ledger
    from jarvis.model_routing import WorkloadLimits
    from tests.unit.test_model_execution_limits import request,route
    root=model_budget.begin_model_task_budget("developer","budget-parent",WorkloadLimits(7,30,.1))
    binding=model_budget.begin_model_child_budget(root,"planning",WorkloadLimits(7,30,.1))
    started=threading.Event()
    validate=model_execution.validate_model_child_budget
    def real_validation(value):
        started.set()
        return validate(value)
    monkeypatch.setattr(model_execution,"validate_model_child_budget",real_validation)
    holder=sqlite3.connect(usage_ledger.DB_PATH)
    holder.execute("PRAGMA locking_mode=EXCLUSIVE")
    holder.execute("BEGIN EXCLUSIVE")
    holder.execute("SELECT COUNT(*) FROM model_task_budgets").fetchone()
    calls=[]
    task=asyncio.create_task(model_execution.execute_chat(
        replace(request(cap=7),workload="planning",timeout_s=.04),
        replace(route(),workload="planning"),child_budget=binding,
        client_factory=lambda value:calls.append(value)))
    delayed=False
    try:
        assert await asyncio.to_thread(started.wait,1)
        done,pending=await asyncio.wait({task},timeout=.15)
        delayed=task not in done
    finally:
        holder.rollback()
        holder.close()
        await asyncio.gather(task,return_exceptions=True)
    assert not calls
    assert delayed is False,"actual readonly SQLite validation outlived .04s request deadline until outer .15s timer released its lock"
    assert isinstance(task.exception(),TimeoutError)
