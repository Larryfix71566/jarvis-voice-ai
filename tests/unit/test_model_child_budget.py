"""Durable host sponsorship: one attempt, exact parent and both ceilings."""
import math
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest

from jarvis import model_budget, usage_ledger
from jarvis.model_budget import (
    ChildTaskBudget, ModelBudgetUnavailable, begin_model_child_budget,
    begin_model_task_budget, remaining_child_seconds, reserve_model_child_call_budget,
    reserve_model_call_budget, resolve_model_child_budget,
)
from jarvis.model_routing import WorkloadLimits
from jarvis.tenant import user_id_scope
from tests.unit.test_model_budget import isolated_budget


def owner(limits=WorkloadLimits(100, 100, .2004), *, now=100, workload="developer"):
    return begin_model_task_budget(workload, "parent-1", limits, now=now)


def child(root=None, limits=WorkloadLimits(200, 50, 1), *, now=100, workload="council"):
    return begin_model_child_budget(root or owner(), workload, limits, now=now)


def reserve(binding, *, task="call", now=100):
    return reserve_model_child_call_budget(binding, task, "test", "model", "direct_api",
                                           "provider_api", 100_000, 100, now=now)


def rows(table):
    with sqlite3.connect(usage_ledger.DB_PATH) as conn:
        return conn.execute(f"SELECT * FROM {table}").fetchall()


def test_every_attempt_is_one_cost_row_and_two_scope_memberships():
    binding = child()
    first = reserve(binding)
    again = reserve(binding)  # identical task ID is not a free replay
    assert first.reservation_id != again.reservation_id
    assert first.reserved_cost_usd == .1002 and again.reserved_total_usd == .2004
    assert len(rows("model_call_budget_reservations")) == 2
    assert len(rows("model_call_budget_reservation_scopes")) == 4
    assert rows("llm_calls") == []
    with pytest.raises(ModelBudgetUnavailable, match="budget_spend_exhausted"):
        reserve(binding)


def test_existing_ordinary_owner_reservation_and_child_debits_share_total():
    root = owner()
    reserve_model_call_budget(root, "before-child", "test", "model", "direct_api", "provider_api", 100_000, 100, now=100)
    binding = child(root)
    reserve(binding)
    with pytest.raises(ModelBudgetUnavailable, match="budget_spend_exhausted"):
        reserve_model_call_budget(root, "after-child", "test", "model", "direct_api", "provider_api", 100_000, 100, now=100)
    assert len(rows("model_call_budget_reservations")) == 2


def test_stricter_child_pool_does_not_lower_whole_owner_ceiling():
    binding = child(owner(WorkloadLimits(100, None, 1)), WorkloadLimits(100, None, .1002))
    reserve(binding)
    with pytest.raises(ModelBudgetUnavailable, match="budget_spend_exhausted"):
        reserve(binding)
    reserve_model_call_budget(binding.owner, "ordinary", "test", "model", "direct_api", "provider_api", 100_000, 100, now=100)
    assert binding.owner.limits.max_estimated_spend_usd_per_task == 1
    assert len(rows("model_call_budget_reservations")) == 2


def test_concurrent_independent_connections_admit_only_owner_capacity():
    binding = child()
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(reserve, binding, task=f"parallel-{n}") for n in range(6)]
    values = []
    for future in futures:
        try:
            values.append(future.result())
        except ModelBudgetUnavailable as exc:
            assert exc.code == "budget_spend_exhausted"
    assert len(values) == 2 and len(rows("model_call_budget_reservations")) == 2
    assert len(rows("model_call_budget_reservation_scopes")) == 4


def test_null_and_omitted_sponsor_resume_recovers_same_scope_and_start():
    binding = child(now=110)
    reserve(binding, now=110)
    resumed = resolve_model_child_budget("council", "parent-1", WorkloadLimits(), now=120)
    assert resumed.owner.scope_id == binding.owner.scope_id
    assert resumed.child.scope_id == binding.child.scope_id
    assert resumed.child.started_at == binding.child.started_at == 110
    assert resumed.limits == binding.limits
    assert remaining_child_seconds(resumed, now=120) == 40
    reserve(resumed, now=120)
    with pytest.raises(ModelBudgetUnavailable, match="budget_spend_exhausted"):
        reserve(resumed, now=120)


def test_null_root_configuration_cannot_clear_linked_bounds():
    binding = child()
    root = begin_model_task_budget("developer", "parent-1", WorkloadLimits(), now=105)
    reopened = begin_model_child_budget(root, "council", WorkloadLimits(), now=106)
    assert root.limits == binding.owner.limits and reopened.limits == binding.limits


@pytest.mark.parametrize("table", ["model_task_budget_links", "model_call_budget_reservation_scopes"])
def test_partial_sponsorship_schema_never_looks_like_unlinked_scope(table):
    child()
    with sqlite3.connect(usage_ledger.DB_PATH) as conn:
        conn.execute(f"DROP TABLE {table}")
    with pytest.raises(ModelBudgetUnavailable, match="budget_storage_unavailable"):
        resolve_model_child_budget("council", "parent-1", WorkloadLimits(), now=110)


def test_missing_scope_table_with_prior_authority_is_never_an_old_uncapped_ledger():
    child()
    with sqlite3.connect(usage_ledger.DB_PATH) as conn:
        conn.execute("DROP TABLE model_task_budgets")
    for workload, parent in (("council", "parent-1"), ("council", "new-parent")):
        with pytest.raises(ModelBudgetUnavailable, match="budget_storage_unavailable"):
            begin_model_task_budget(workload, parent, WorkloadLimits(), now=110)


def test_partial_sponsorship_schema_also_refuses_new_ordinary_parent():
    child()
    with sqlite3.connect(usage_ledger.DB_PATH) as conn:
        conn.execute("DROP TABLE model_task_budget_links")
    with pytest.raises(ModelBudgetUnavailable, match="budget_storage_unavailable"):
        begin_model_task_budget("planning", "new-parent", WorkloadLimits(), now=110)


def test_direct_reservation_never_recreates_lost_child_accounting():
    binding = child(owner(WorkloadLimits(100, None, 1)), WorkloadLimits(100, None, .1002))
    reserve(binding)
    with sqlite3.connect(usage_ledger.DB_PATH) as conn:
        conn.execute("DROP TABLE model_call_budget_reservation_scopes")
    with pytest.raises(ModelBudgetUnavailable, match="budget_storage_unavailable"):
        reserve(binding)
    assert len(rows("model_call_budget_reservations")) == 1
    with sqlite3.connect(usage_ledger.DB_PATH) as conn:
        assert conn.execute("SELECT 1 FROM sqlite_master WHERE name='model_call_budget_reservation_scopes'").fetchone() is None


def test_child_absolute_deadline_uses_first_child_start_and_owner_expiry():
    binding = child(owner(WorkloadLimits(100, 30)), WorkloadLimits(200, 20), now=110)
    assert binding.owner.deadline_at == binding.child.deadline_at == 130
    resumed = resolve_model_child_budget("council", "parent-1", WorkloadLimits(None, 100), now=120)
    assert resumed.child.started_at == 110 and resumed.child.deadline_at == 130
    assert remaining_child_seconds(resumed, now=125) == 5
    assert remaining_child_seconds(resumed, now=131) == 0
    with pytest.raises(ModelBudgetUnavailable, match="budget_clock_mismatch"):
        remaining_child_seconds(resumed, now=126)


def test_expired_resolver_retains_only_authenticated_clock_before_rollback():
    root = owner(WorkloadLimits(100, 5, 1))
    with pytest.raises(ModelBudgetUnavailable, match="budget_deadline_exhausted"):
        begin_model_child_budget(root, "council", WorkloadLimits(10, None, .1), now=108)
    assert len(rows("model_task_budgets")) == 1 and rows("model_task_budget_links") == []
    with pytest.raises(ModelBudgetUnavailable, match="budget_clock_mismatch"):
        begin_model_child_budget(root, "council", WorkloadLimits(), now=102)


def test_output_only_sponsorship_is_durable_but_ordinary_output_only_stays_ephemeral():
    root = owner(WorkloadLimits(10))
    assert root.scope_id is None and not usage_ledger.DB_PATH.exists()
    binding = child(root, WorkloadLimits(50))
    assert binding.owner.scope_id is not None and binding.child.scope_id is not None
    resumed = resolve_model_child_budget("council", "parent-1", WorkloadLimits())
    assert resumed.limits.max_output_tokens_per_call == 10
    assert remaining_child_seconds(resumed) == math.inf
    assert rows("model_call_budget_reservations") == []


def test_fresh_all_null_binding_never_creates_storage_or_samples_clock(monkeypatch):
    root = owner(WorkloadLimits())
    monkeypatch.setattr(model_budget.time, "time", lambda: pytest.fail("sampled empty scope clock"))
    binding = child(root, WorkloadLimits())
    assert binding.child.scope_id is None and remaining_child_seconds(binding) == math.inf
    assert reserve(binding).reserved_cost_usd is None and not usage_ledger.DB_PATH.exists()


def test_orphan_durable_owner_cannot_use_all_null_fast_path():
    root = replace(owner(WorkloadLimits()), scope_id="orphan", started_at=100, _ephemeral_seal="")
    with pytest.raises(ModelBudgetUnavailable, match="budget_scope_mismatch"):
        child(root, WorkloadLimits())


@pytest.mark.parametrize("change", ["seal", "limits", "parent", "user"])
def test_replaced_or_direct_capability_is_rejected(change):
    binding = child()
    if change == "seal":
        bad = replace(binding, _seal="0" * 64)
    else:
        altered = replace(binding.child, **{
            "limits": {"limits": WorkloadLimits()}, "parent": {"parent_request_id": "other"},
            "user": {"user_id": "other"},
        }[change])
        bad = replace(binding, child=altered)
    with pytest.raises(ModelBudgetUnavailable):
        resolve_model_child_budget("council", "parent-1", WorkloadLimits(), child_budget=bad, now=100)
    with pytest.raises(ModelBudgetUnavailable):
        reserve_model_child_call_budget(ChildTaskBudget(binding.owner, binding.child),
                                       "call", "test", "model", "direct_api", "provider_api", 1, 100, now=100)


def test_foreign_tenant_cannot_reopen_or_reserve_binding():
    binding = child()
    with user_id_scope("foreign"):
        assert resolve_model_child_budget("council", "parent-1", WorkloadLimits(), now=100) is None
        with pytest.raises(ModelBudgetUnavailable, match="budget_scope_mismatch"):
            reserve(binding)


def test_direct_linked_child_reservation_cannot_bypass_sponsor():
    binding = child()
    with pytest.raises(ModelBudgetUnavailable, match="budget_policy_mismatch"):
        reserve_model_call_budget(binding.child, "call", "test", "model", "direct_api", "provider_api", 1, 100, now=100)
    assert rows("model_call_budget_reservations") == []


def test_same_workload_coalesces_one_scope_no_self_link_one_membership():
    binding = child(owner(workload="council"), workload="council")
    assert binding.owner.scope_id == binding.child.scope_id and rows("model_task_budget_links") == []
    reserve(binding)
    assert len(rows("model_task_budgets")) == len(rows("model_call_budget_reservations")) == 1
    assert len(rows("model_call_budget_reservation_scopes")) == 1


def test_nested_and_replacement_owner_refuse_without_partial_link_mutation():
    binding = child()
    with pytest.raises(ModelBudgetUnavailable, match="budget_scope_mismatch"):
        begin_model_child_budget(binding.child, "planning", WorkloadLimits(10), now=100)
    alternate = begin_model_task_budget("planning", "parent-1", WorkloadLimits(10, None, 1), now=100)
    before = rows("model_task_budget_links")
    with pytest.raises(ModelBudgetUnavailable, match="budget_scope_mismatch"):
        child(alternate, WorkloadLimits(10))
    assert rows("model_task_budget_links") == before


def test_tighter_live_owner_policy_requires_reopening_before_request_proofs():
    binding = child(owner(WorkloadLimits(100, None, 10)), WorkloadLimits(100, None, 10))
    begin_model_task_budget("developer", "parent-1", WorkloadLimits(50, None, 2), now=101)
    with pytest.raises(ModelBudgetUnavailable, match="budget_policy_mismatch"):
        reserve(binding, now=101)
    reopened = resolve_model_child_budget("council", "parent-1", WorkloadLimits(), child_budget=binding, now=101)
    assert reopened.limits.max_output_tokens_per_call == 50
    assert reopened.limits.max_estimated_spend_usd_per_task == 2


@pytest.mark.parametrize("field,value", [("input_per_m", None), ("output_per_m", float("nan")),
                                        ("cache_write_mult", True)])
def test_missing_or_malformed_price_retains_no_partial_reservation(field, value):
    binding = child()
    usage_ledger._price_map_cache["models"]["test/model"][field] = value
    with pytest.raises(ModelBudgetUnavailable, match="budget_price_unavailable"):
        reserve(binding)
    assert rows("model_call_budget_reservations") == rows("model_call_budget_reservation_scopes") == []


def test_sqlite_admission_error_is_fixed_unavailable(monkeypatch):
    binding = child()
    monkeypatch.setattr(usage_ledger, "model_budget_connection", lambda: (_ for _ in ()).throw(sqlite3.OperationalError("PRIVATE_STORAGE_ERROR")))
    with pytest.raises(ModelBudgetUnavailable, match="budget_storage_unavailable"):
        reserve(binding)


def test_valid_old_ephemeral_root_handle_honors_later_durable_deadline():
    old = owner(WorkloadLimits(100))
    child(old, WorkloadLimits(100))
    begin_model_task_budget("developer", "parent-1", WorkloadLimits(None, 5), now=100)
    assert model_budget.remaining_seconds(old, now=103) == 2
    assert model_budget.remaining_seconds(old, now=106) == 0
    with pytest.raises(ModelBudgetUnavailable, match="budget_clock_mismatch"):
        model_budget.remaining_seconds(old, now=104)


def test_valid_old_ephemeral_reservation_handle_cannot_bypass_later_bound():
    old = owner(WorkloadLimits(100))
    child(old, WorkloadLimits(100))
    begin_model_task_budget("developer", "parent-1", WorkloadLimits(None, None, .001), now=100)
    with pytest.raises(ModelBudgetUnavailable, match="budget_policy_mismatch"):
        reserve_model_call_budget(old, "old", "test", "model", "direct_api", "provider_api", 100_000, 100, now=100)
    assert rows("model_call_budget_reservations") == []
