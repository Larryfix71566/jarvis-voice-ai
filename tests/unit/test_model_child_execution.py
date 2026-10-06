"""Sponsored execution reaches inert real SDK transports under one owner."""
import asyncio
import json
import sqlite3
from dataclasses import replace
from decimal import Decimal

import httpx
import openai
import pytest

from jarvis.model_budget import (
    ModelBudgetUnavailable, begin_model_task_budget, begin_model_child_budget,
)
from jarvis.model_execution import execute_chat
from jarvis.model_routing import WorkloadLimits
from tests.unit.test_model_execution_limits import ledger, request, route, sdk, success


def sponsored(*, owner_limits=WorkloadLimits(100, None, .002), child_limits=WorkloadLimits(200, None, .01)):
    owner = begin_model_task_budget('developer', 'budget-parent', owner_limits)
    return owner, begin_model_child_budget(owner, 'council', child_limits)


def council_request(*, task='council-attempt'):
    return replace(request(task=task), workload='council')


def council_route(limits=WorkloadLimits()):
    return replace(route(limits), workload='council')


def reservations(path):
    with sqlite3.connect(path) as conn:
        return conn.execute('SELECT reservation_id,reserved_cost_usd FROM model_call_budget_reservations').fetchall()


async def test_sponsored_sdk_call_charges_one_attempt_to_both_scopes_and_retains_owner_cap(ledger):
    owner, child = sponsored()
    sent = []
    async with sdk(lambda req: sent.append(json.loads(req.content)) or success(req)) as client:
        await execute_chat(council_request(), council_route(), child_budget=child,
                           client_factory=lambda _: client)
        with pytest.raises(ModelBudgetUnavailable, match='budget_spend_exhausted'):
            await execute_chat(council_request(task='second-attempt'), council_route(), child_budget=child,
                               client_factory=lambda _: client)
    assert len(sent) == 1 and sent[0]['max_tokens'] == 100
    recorded = reservations(ledger)
    assert len(recorded) == 1 and Decimal(recorded[0][1]) > 0
    with sqlite3.connect(ledger) as conn:
        assert {row[0] for row in conn.execute(
            'SELECT scope_id FROM model_call_budget_reservation_scopes WHERE reservation_id=?',
            (recorded[0][0],))} == {owner.scope_id, child.child.scope_id}
        assert conn.execute('SELECT COUNT(*) FROM llm_calls').fetchone() == (0,)


async def test_omitted_child_keyword_recovers_sponsor_after_route_limits_are_cleared(ledger):
    owner, child = sponsored()
    sent = []
    async with sdk(lambda req: sent.append(json.loads(req.content)) or success(req)) as client:
        await execute_chat(council_request(), council_route(), child_budget=child,
                           client_factory=lambda _: client)
        with pytest.raises(ModelBudgetUnavailable, match='budget_spend_exhausted'):
            await execute_chat(council_request(task='reopened'), council_route(),
                               client_factory=lambda _: client)
    assert len(sent) == 1 and len(reservations(ledger)) == 1


async def test_failed_sdk_attempt_keeps_both_pools_reserved(ledger):
    _, child = sponsored()
    calls = []
    def fail(req):
        calls.append(True)
        raise httpx.ConnectError('synthetic lost acknowledgement', request=req)
    async with sdk(fail) as client:
        with pytest.raises(openai.APIConnectionError):
            await execute_chat(council_request(), council_route(), child_budget=child,
                               client_factory=lambda _: client)
        with pytest.raises(ModelBudgetUnavailable, match='budget_spend_exhausted'):
            await execute_chat(council_request(task='retry'), council_route(), child_budget=child,
                               client_factory=lambda _: client)
    assert calls == [True] and len(reservations(ledger)) == 1


async def test_cancelled_sdk_attempt_cannot_restart_with_a_fresh_pool(ledger):
    _, child = sponsored()
    entered = asyncio.Event()
    async def hold(req):
        entered.set()
        await asyncio.Event().wait()
    async with sdk(hold) as client:
        task = asyncio.create_task(execute_chat(council_request(), council_route(), child_budget=child,
                                               client_factory=lambda _: client))
        await asyncio.wait_for(entered.wait(), 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        with pytest.raises(ModelBudgetUnavailable, match='budget_spend_exhausted'):
            await execute_chat(council_request(task='after-cancel'), council_route(),
                               client_factory=lambda _: client)
    assert len(reservations(ledger)) == 1


async def test_parent_and_child_handles_are_exclusive_and_bound_before_client_creation(ledger):
    owner, child = sponsored()
    made = []
    for kwargs in ({'task_budget': owner, 'child_budget': child},
                   {'child_budget': replace(child, _seal='0' * 64)}):
        with pytest.raises(ModelBudgetUnavailable):
            await execute_chat(council_request(), council_route(), **kwargs,
                               client_factory=lambda _: made.append(True))
    with pytest.raises(ModelBudgetUnavailable, match='budget_scope_mismatch'):
        await execute_chat(replace(council_request(), parent_request_id='other-parent'), council_route(),
                           child_budget=child, client_factory=lambda _: made.append(True))
    assert made == [] and reservations(ledger) == []


async def test_sponsored_spend_requires_real_retry_free_sdk_before_reserving(ledger):
    _, child = sponsored()
    sent = []
    async with sdk(lambda req: sent.append(True) or success(req), retries=2) as client:
        with pytest.raises(ModelBudgetUnavailable, match='budget_unsupported_route'):
            await execute_chat(council_request(), council_route(), child_budget=child,
                               client_factory=lambda _: client)
    assert sent == [] and reservations(ledger) == []


async def test_output_only_sponsor_cap_survives_omission_without_spend_accounting(ledger):
    owner, child = sponsored(owner_limits=WorkloadLimits(10), child_limits=WorkloadLimits(50))
    sent = []
    async with sdk(lambda req: sent.append(json.loads(req.content)) or success(req)) as client:
        await execute_chat(council_request(), council_route(), child_budget=child,
                           client_factory=lambda _: client)
        await execute_chat(council_request(task='output-only-resume'), council_route(),
                           client_factory=lambda _: client)
    assert [item['max_tokens'] for item in sent] == [10, 10]
    assert reservations(ledger) == []


async def test_same_workload_sponsor_coalesces_without_self_link_or_double_charge(ledger):
    owner = begin_model_task_budget('council', 'budget-parent', WorkloadLimits(100, None, .002))
    child = begin_model_child_budget(owner, 'council', WorkloadLimits(200, None, .01))
    sent = []
    async with sdk(lambda req: sent.append(json.loads(req.content)) or success(req)) as client:
        await execute_chat(council_request(), council_route(), child_budget=child,
                           client_factory=lambda _: client)
    assert len(sent) == 1 and sent[0]['max_tokens'] == 100
    with sqlite3.connect(ledger) as conn:
        assert conn.execute('SELECT child_scope_id,parent_scope_id FROM model_task_budget_links').fetchall() == []
        assert conn.execute('SELECT COUNT(*) FROM model_call_budget_reservations').fetchone() == (1,)
        assert conn.execute('SELECT COUNT(*) FROM model_call_budget_reservation_scopes').fetchone() == (1,)
