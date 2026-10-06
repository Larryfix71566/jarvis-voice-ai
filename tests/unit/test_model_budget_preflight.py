"""Dry admission shares atomic authority without consuming an attempt."""
from contextlib import closing
import sqlite3

import pytest

from jarvis import model_budget, usage_ledger
from jarvis.model_budget import (
    ChildTaskBudget, ModelBudgetUnavailable, begin_model_task_budget,
    begin_model_child_budget, begin_model_descendant_budget,
    check_model_call_budget, reserve_model_call_budget, reserve_model_child_call_budget,
)
from jarvis.model_routing import WorkloadLimits
from tests.unit.test_model_budget import isolated_budget


def budget(kind, limits=WorkloadLimits(100, 20, .2004)):
    root = begin_model_task_budget("developer", "dry-parent", limits, now=100)
    if kind == "root":
        return root
    child = begin_model_child_budget(root, "planning", WorkloadLimits(), now=100)
    return child if kind == "child" else begin_model_descendant_budget(child, "council", WorkloadLimits(), now=100)


def invoke(value, *, dry=True, **overrides):
    arguments = dict(task_id="same-task", provider="test", model="model", route_name="direct_api",
        billing_source="provider_api", estimated_input_tokens=100_000, output_token_upper_bound=100, now=100)
    arguments.update(overrides)
    operation = (check_model_call_budget if dry else
                 reserve_model_child_call_budget if type(value) is ChildTaskBudget else reserve_model_call_budget)
    return operation(value, **arguments)


def snapshot():
    with closing(sqlite3.connect(usage_ledger.DB_PATH)) as conn:
        return {table: conn.execute(f"SELECT * FROM {table}").fetchall() for table in (
            "model_task_budgets", "model_call_budget_reservations", "model_task_budget_links",
            "model_call_budget_reservation_scopes", "llm_calls")}


@pytest.mark.parametrize("kind", ["root", "child", "descendant"])
def test_preflight_never_creates_uuid_reservation_membership_or_clock_write(kind, monkeypatch):
    value = budget(kind)
    before = snapshot()
    with closing(sqlite3.connect(usage_ledger.DB_PATH)) as conn:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    data = usage_ledger.DB_PATH.read_bytes()
    monkeypatch.setattr(model_budget, "uuid4", lambda: pytest.fail("dry preflight minted UUID"))
    monkeypatch.setattr(usage_ledger, "model_budget_connection", lambda: pytest.fail("dry writable connection"))
    assert invoke(value, now=110) is None and invoke(value, now=111) is None
    assert snapshot() == before and usage_ledger.DB_PATH.read_bytes() == data


@pytest.mark.parametrize("kind", ["root", "child", "descendant"])
@pytest.mark.parametrize("overrides, code", [
    ({"now": 99}, "budget_clock_mismatch"),
    ({"now": 121}, "budget_deadline_exhausted"),
    ({"estimated_input_tokens": True}, "budget_input_invalid"),
    ({"estimated_input_tokens": 0}, "budget_input_invalid"),
    ({"output_token_upper_bound": True}, "budget_output_limit"),
    ({"output_token_upper_bound": 101}, "budget_output_limit"),
    ({"model": "unknown-model"}, "budget_price_unavailable"),
    ({"route_name": "subscription", "billing_source": "subscription"}, "budget_unsupported_route"),
])
def test_dry_and_atomic_admission_return_same_fixed_refusals(kind, overrides, code):
    value = budget(kind)
    before = snapshot()
    with pytest.raises(ModelBudgetUnavailable, match=f"^{code}$"):
        invoke(value, **overrides)
    assert snapshot() == before
    with pytest.raises(ModelBudgetUnavailable, match=f"^{code}$"):
        invoke(value, dry=False, **overrides)
    assert snapshot()["model_call_budget_reservations"] == []
    assert snapshot()["model_call_budget_reservation_scopes"] == []


@pytest.mark.parametrize("pool", ["root", "planning", "council"])
def test_exhausted_inherited_pool_refuses_dry_without_new_attempt(pool):
    root = begin_model_task_budget("developer", "dry-parent", WorkloadLimits(100, 20, .2004 if pool == "root" else 1), now=100)
    parent = begin_model_child_budget(root, "planning", WorkloadLimits(100, None, .2004 if pool == "planning" else 1), now=100)
    child = begin_model_descendant_budget(parent, "council", WorkloadLimits(100, None, .1002 if pool == "council" else 1), now=100)
    if pool == "root":
        invoke(root, dry=False)
        invoke(parent, dry=False)
    elif pool == "planning":
        invoke(parent, dry=False)
        invoke(child, dry=False)
    else:
        invoke(child, dry=False)
    before = snapshot()
    with pytest.raises(ModelBudgetUnavailable, match="^budget_spend_exhausted$"):
        invoke(child)
    assert snapshot() == before
    with pytest.raises(ModelBudgetUnavailable, match="^budget_spend_exhausted$"):
        invoke(child, dry=False)
    assert snapshot()["model_call_budget_reservations"] == before["model_call_budget_reservations"]


def test_successful_dry_check_cannot_authorize_around_later_atomic_admission():
    value = budget("descendant", WorkloadLimits(100, 20, .1002))
    invoke(value)
    booked = invoke(value, dry=False)
    with pytest.raises(ModelBudgetUnavailable, match="^budget_spend_exhausted$"):
        invoke(value, dry=False)
    observed = snapshot()
    assert len(observed["model_call_budget_reservations"]) == 1
    assert len(observed["model_call_budget_reservation_scopes"]) == 3
    assert all(row[0] == booked.reservation_id for row in observed["model_call_budget_reservation_scopes"])
    assert observed["llm_calls"] == []


@pytest.mark.parametrize("field,value", [("input_per_m", float("nan")), ("cache_write_mult", True), ("cache_read_mult", -1)])
def test_malformed_prices_refuse_identically_without_dry_accounting(field, value):
    selected = budget("descendant")
    usage_ledger._price_map_cache["models"]["test/model"][field] = value
    before = snapshot()
    for dry in (True, False):
        with pytest.raises(ModelBudgetUnavailable, match="^budget_price_unavailable$"):
            invoke(selected, dry=dry)
    assert snapshot()["model_call_budget_reservations"] == before["model_call_budget_reservations"]


def test_cache_premium_uses_same_conservative_admission_estimate():
    value = budget("descendant", WorkloadLimits(100, 20, .15))
    usage_ledger._price_map_cache["models"]["anthropic/claude-fixture"] = {
        "input_per_m": 1, "output_per_m": 2, "cache_write_mult": 1.25, "cache_read_mult": .1}
    for dry in (True, False):
        with pytest.raises(ModelBudgetUnavailable, match="^budget_spend_exhausted$"):
            invoke(value, dry=dry, provider="anthropic", model="claude-fixture")
    assert snapshot()["model_call_budget_reservations"] == []


def test_unknown_storage_failure_is_fixed_and_dry_creates_nothing(monkeypatch):
    value = budget("descendant")
    before = snapshot()
    def broken():
        raise RuntimeError("PRIVATE_exception_canary")
    monkeypatch.setattr(usage_ledger, "existing_model_budget_connection", broken)
    monkeypatch.setattr(usage_ledger, "model_budget_connection", broken)
    for dry in (True, False):
        with pytest.raises(ModelBudgetUnavailable, match="^budget_storage_unavailable$"):
            invoke(value, dry=dry)
    assert snapshot() == before


@pytest.mark.parametrize("kind", ["root", "child", "descendant"])
def test_genuinely_uncapped_preflight_never_samples_clock_prices_or_store(kind, monkeypatch):
    value = budget(kind, WorkloadLimits())
    for owner, field in ((model_budget.time, "time"), (model_budget, "uuid4"),
                         (usage_ledger, "load_price_map"), (usage_ledger, "model_budget_connection")):
        monkeypatch.setattr(owner, field, lambda: pytest.fail("uncapped preflight side effect"))
    assert invoke(value, now=None) is None
    assert not usage_ledger.DB_PATH.exists()


def test_deadline_only_preflight_checks_expiry_without_price_or_charge(monkeypatch):
    value = budget("root", WorkloadLimits(100, 20))
    monkeypatch.setattr(usage_ledger, "load_price_map", lambda: pytest.fail("deadline-only prices"))
    before = snapshot()
    invoke(value, now=110)
    with pytest.raises(ModelBudgetUnavailable, match="^budget_deadline_exhausted$"):
        invoke(value, now=121)
    assert snapshot() == before


def test_dry_preflight_does_not_clear_already_recorded_forward_clock():
    value = budget("descendant")
    with pytest.raises(ModelBudgetUnavailable, match="budget_deadline_exhausted"):
        invoke(value, dry=False, now=121)
    before = snapshot()
    with pytest.raises(ModelBudgetUnavailable, match="^budget_clock_mismatch$"):
        invoke(value, now=115)
    assert snapshot() == before
