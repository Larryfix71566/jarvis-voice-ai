"""Admission reaches real SDK transports, without a provider or credentials."""
import asyncio
import json
import sqlite3
import threading
from dataclasses import replace
from types import SimpleNamespace

import httpx
import openai
import pytest

from jarvis import usage_ledger
from jarvis import model_budget
from jarvis import model_execution
from jarvis.model_budget import ModelBudgetUnavailable, begin_model_task_budget
from jarvis.model_execution import (
    ModelAdmissionController, ModelAttachment, ModelExecutionRequest,
    ModelOutputRequirements, execute_chat,
)
from jarvis.model_routing import AccessRoute, ResolvedModelRoute, WorkloadLimits, ModelRouteError
from jarvis.privacy_policy import DataPolicy
from jarvis.bot.shared_content import normalize_shared_content


def route(limits=WorkloadLimits(), *, native=False):
    return ResolvedModelRoute(
        "developer", "fixture", "fixture", "subscription" if native else "openai", "",
        AccessRoute("subscription" if native else "direct_api",
                    "subscription_runtime" if native else "openai_compatible",
                    "subscription" if native else "provider_api", None,
                    "approved_external", capabilities=("text",)),
        None, "openai/fixture", "interactive", limits=limits,
    )


def request(*, parent="budget-parent", task="budget-task", cap=None):
    return ModelExecutionRequest("developer", task, parent, "public fixture",
                                 output=ModelOutputRequirements(max_tokens=cap),
                                 data_policy=DataPolicy("approved_external", "public-fixture"))


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    path = tmp_path / "costs.db"
    monkeypatch.setattr(usage_ledger, "DB_PATH", path)
    monkeypatch.setattr(usage_ledger, "load_price_map", lambda: {"models": {
        "openai/fixture": {"input_per_m": 1, "output_per_m": 1,
                           "cache_write_mult": 1, "cache_read_mult": 1},
    }})
    return path


def rows(path, table):
    with sqlite3.connect(path) as conn:
        return conn.execute(f"SELECT * FROM {table}").fetchall()


def sdk(handler, *, retries=0):
    return openai.AsyncOpenAI(api_key="synthetic-unused-key", base_url="https://fixture.invalid/v1",
                             max_retries=retries,
                             http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))


def success(req):
    return httpx.Response(200, json={"id": "synthetic", "object": "chat.completion",
        "created": 1, "model": "fixture", "choices": [
            {"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "ok"}}
        ], "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}})


async def test_output_cap_is_forwarded_as_the_tighter_explicit_bound(ledger):
    sent = []
    def handler(req):
        sent.append(json.loads(req.content))
        return success(req)
    async with sdk(handler) as client:
        await execute_chat(request(cap=80), route(WorkloadLimits(max_output_tokens_per_call=40)),
                           client_factory=lambda _: client)
        await execute_chat(request(cap=20), route(WorkloadLimits(max_output_tokens_per_call=40)),
                           client_factory=lambda _: client)
    assert [body["max_tokens"] for body in sent] == [40, 20]
    assert not ledger.exists()  # output-only admission creates no accounting store


async def test_absent_limits_keep_call_arguments_and_do_not_create_storage(ledger):
    sent = []
    def handler(req):
        sent.append(json.loads(req.content))
        return success(req)
    async with sdk(handler) as client:
        await execute_chat(request(), route(), client_factory=lambda _: client)
    assert sent == [{"model": "fixture", "messages": [{"role": "user", "content": "public fixture"}]}]
    assert not ledger.exists()


async def test_parent_spend_ceiling_refuses_second_call_before_transport(ledger):
    calls = []
    async with sdk(lambda req: calls.append(True) or success(req)) as client:
        resolved = route(WorkloadLimits(100, None, 0.002))
        await execute_chat(request(), resolved, client_factory=lambda _: client)
        with pytest.raises(ModelBudgetUnavailable, match="budget_spend_exhausted"):
            await execute_chat(request(task="attempt-two"), resolved, client_factory=lambda _: client)
    assert len(calls) == 1
    assert len(rows(ledger, "model_call_budget_reservations")) == 1
    assert rows(ledger, "llm_calls") == []  # reservation is not observed usage


async def test_failed_provider_attempt_keeps_its_reservation(ledger):
    calls = []
    def failed(req):
        calls.append(True)
        return httpx.Response(500, json={"error": {"message": "synthetic refusal"}})
    async with sdk(failed) as client:
        resolved = route(WorkloadLimits(100, None, 0.002))
        with pytest.raises(openai.InternalServerError):
            await execute_chat(request(), resolved, client_factory=lambda _: client)
        with pytest.raises(ModelBudgetUnavailable, match="budget_spend_exhausted"):
            await execute_chat(request(), resolved, client_factory=lambda _: client)
    assert len(calls) == 1
    assert len(rows(ledger, "model_call_budget_reservations")) == 1


async def test_concurrent_attempts_share_one_atomic_parent_ceiling(ledger):
    calls = []
    async with sdk(lambda req: calls.append(True) or success(req)) as client:
        resolved = route(WorkloadLimits(100, None, 0.002))
        outcomes = await asyncio.gather(*(
            execute_chat(request(task=f"attempt-{n}"), resolved, client_factory=lambda _: client)
            for n in range(2)
        ), return_exceptions=True)
    assert len(calls) == 1
    assert sum(isinstance(outcome, ModelBudgetUnavailable) for outcome in outcomes) == 1


async def test_clearing_config_or_forging_handle_fields_cannot_reset_parent_spend(ledger):
    calls = []
    budget = begin_model_task_budget("developer", "budget-parent", WorkloadLimits(100, None, .002))
    async with sdk(lambda req: calls.append(True) or success(req)) as client:
        await execute_chat(request(), route(), task_budget=budget, client_factory=lambda _: client)
        forged = replace(budget, limits=WorkloadLimits())
        with pytest.raises(ModelBudgetUnavailable, match="budget_spend_exhausted"):
            await execute_chat(request(), route(), task_budget=forged, client_factory=lambda _: client)
    assert len(calls) == 1


@pytest.mark.parametrize("limits", [WorkloadLimits(50), WorkloadLimits(None, None, .01)])
async def test_native_unsupported_caps_refuse_before_client_creation(ledger, limits):
    created = []
    with pytest.raises(ModelRouteError if limits.max_output_tokens_per_call else ModelBudgetUnavailable):
        await execute_chat(request(), route(limits, native=True),
                           client_factory=lambda _: created.append(True))
    assert created == []


async def test_spend_limit_requires_a_known_output_bound(ledger):
    created = []
    with pytest.raises(ModelBudgetUnavailable, match="budget_output_limit"):
        await execute_chat(request(), route(WorkloadLimits(None, None, .01)),
                           client_factory=lambda _: created.append(True))
    assert created == []


async def test_unknown_prices_never_become_zero_cost(ledger, monkeypatch):
    monkeypatch.setattr(usage_ledger, "load_price_map", lambda: {"models": {}})
    calls = []
    async with sdk(lambda req: calls.append(True) or success(req)) as client:
        with pytest.raises(ModelBudgetUnavailable, match="budget_price_unavailable"):
            await execute_chat(request(), route(WorkloadLimits(100, None, .01)),
                               client_factory=lambda _: client)
    assert calls == []


async def test_hidden_sdk_retries_are_refused(ledger):
    calls = []
    async with sdk(lambda req: calls.append(True) or success(req), retries=2) as client:
        with pytest.raises(ModelBudgetUnavailable, match="budget_unsupported_route"):
            await execute_chat(request(), route(WorkloadLimits(100, None, .01)),
                               client_factory=lambda _: client)
    assert calls == []


async def test_foreign_retry_flag_is_not_authority(ledger):
    fake = SimpleNamespace(max_retries=0, chat=SimpleNamespace(completions=SimpleNamespace(
        create=lambda **_: pytest.fail("foreign client must never be called"))))
    with pytest.raises(ModelBudgetUnavailable, match="budget_unsupported_route"):
        await execute_chat(request(), route(WorkloadLimits(100, None, .01)),
                           client_factory=lambda _: fake)


async def test_nontext_estimate_shapes_are_refused_before_client_creation(ledger):
    payload = normalize_shared_content(kind="text", text="public fixture")
    with_attachment = replace(request(), attachments=(ModelAttachment(
        payload, DataPolicy("approved_external", "public-fixture"),
        "direct_api", "openai/fixture"),))
    created = []
    with pytest.raises(ModelBudgetUnavailable, match="budget_input_invalid"):
        await execute_chat(with_attachment, route(WorkloadLimits(100, None, .01)),
                           client_factory=lambda _: created.append(True))
    assert created == []


async def test_expired_parent_deadline_cannot_be_reset_by_configuration(ledger, monkeypatch):
    # Expire the durable wall-clock deadline without racing execution's
    # independent setup timeout while SQLite opens on a loaded CI worker.
    clock = SimpleNamespace(now=model_budget.time.time())
    monkeypatch.setattr(model_budget, "time", SimpleNamespace(time=lambda: clock.now))
    budget = begin_model_task_budget("developer", "budget-parent", WorkloadLimits(deadline_seconds=60))
    clock.now = budget.deadline_at + 1
    assert model_budget.remaining_seconds(budget) == 0
    created = []
    with pytest.raises(ModelBudgetUnavailable, match="budget_deadline_exhausted"):
        await execute_chat(request(), route(), task_budget=budget,
                           client_factory=lambda _: created.append(True))
    assert created == []


async def test_deadline_includes_time_queued_for_admission(ledger, monkeypatch):
    controller = ModelAdmissionController()
    entered = threading.Event()
    can_start = controller._can_start
    def capture_waiter(priority, token):
        if priority == "interactive" and controller.active_counts == (1, 1):
            entered.set()
        return can_start(priority, token)
    monkeypatch.setattr(controller, "_can_start", capture_waiter)
    clock = SimpleNamespace(now=model_budget.time.time())
    monkeypatch.setattr(model_budget, "time", SimpleNamespace(time=lambda: clock.now))
    monkeypatch.setattr(model_execution, "time", SimpleNamespace(time=lambda: clock.now,
        monotonic=model_execution.time.monotonic))
    budgets = []
    begin = model_execution.begin_model_task_budget
    def capture_budget(*args, **kwargs):
        budget = begin(*args, **kwargs)
        budgets.append(budget)
        return budget
    monkeypatch.setattr(model_execution, "begin_model_task_budget", capture_budget)
    async with controller.slot("interactive"), controller.slot("background"):
        created = []
        operation = asyncio.create_task(execute_chat(
            request(), route(WorkloadLimits(deadline_seconds=60)),
            admission=controller, client_factory=lambda _: created.append(True)))
        try:
            assert await asyncio.to_thread(entered.wait, 3)
            assert controller.waiting_interactive == 1 and len(budgets) == 1
            advance = budgets[0].deadline_at - clock.now + 1
            clock.now += advance
            assert model_budget.remaining_seconds(budgets[0]) == 0
            loop = asyncio.get_running_loop()
            loop_time = loop.time
            with monkeypatch.context() as timer_patch:
                timer_patch.setattr(loop, "time", lambda: loop_time() + advance)
                with pytest.raises(TimeoutError):
                    await asyncio.wait_for(operation, 3)
        finally:
            if not operation.done():
                operation.cancel()
                await asyncio.gather(operation, return_exceptions=True)
        assert created == []
        assert controller.waiting_interactive == 0
    assert controller.active_counts == (0, 0)


async def test_budget_handle_cannot_borrow_another_parent(ledger):
    budget = begin_model_task_budget("developer", "other-parent", WorkloadLimits(deadline_seconds=1))
    created = []
    with pytest.raises(ModelBudgetUnavailable, match="budget_scope_mismatch"):
        await execute_chat(request(), route(), task_budget=budget,
                           client_factory=lambda _: created.append(True))
    assert created == []
