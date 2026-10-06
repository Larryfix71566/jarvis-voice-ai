"""One attempt funds the complete sealed Developer/planning/council path."""
from contextlib import closing
from dataclasses import replace
import json
import math
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from jarvis import model_budget, usage_ledger
from jarvis.model_budget import (
    ChildTaskBudget, ModelBudgetUnavailable, begin_model_task_budget,
    begin_model_child_budget, begin_model_descendant_budget,
    bind_model_task_budget_for_transport, remaining_child_seconds,
    reserve_model_call_budget, reserve_model_child_call_budget,
    resolve_model_child_budget, validate_model_child_budget,
)
from jarvis.model_routing import WorkloadLimits
from jarvis.tenant import user_id_scope
from tests.unit.test_model_budget import isolated_budget


def coordinator(root_limits=WorkloadLimits(100, 100, 1), group_limits=WorkloadLimits(100, 50, .2004)):
    root = begin_model_task_budget("developer", "parent-1", root_limits, now=100)
    return bind_model_task_budget_for_transport(root, "planning", group_limits, started_at=100, now=100)


def adviser(parent=None, limits=WorkloadLimits(100, 20, 1), *, now=110):
    return begin_model_descendant_budget(parent or coordinator(), "council", limits, now=now)


def reserve(binding, *, now=110, task="same-task", input_tokens=100_000):
    return reserve_model_child_call_budget(binding, task, "test", "model", "direct_api", "provider_api",
        input_tokens, binding.limits.max_output_tokens_per_call or 100, now=now)


def rows(table):
    with closing(sqlite3.connect(usage_ledger.DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(row) for row in conn.execute(f"SELECT * FROM {table}")]


def test_adviser_attempt_has_original_root_three_memberships_and_no_observed_usage():
    parent = coordinator()
    child = adviser(parent)
    assert child.owner.scope_id == parent.owner.scope_id
    assert child._ancestors == (parent.child,)
    assert child.child.workload == "council" and child.child.started_at == 110
    links = {row["child_scope_id"]: row["parent_scope_id"] for row in rows("model_task_budget_links")}
    assert links == {parent.child.scope_id: parent.owner.scope_id, child.child.scope_id: parent.child.scope_id}
    booked = reserve(child)
    assert len(rows("model_call_budget_reservations")) == 1
    assert {r["scope_id"] for r in rows("model_call_budget_reservation_scopes")} == {
        child.owner.scope_id, parent.child.scope_id, child.child.scope_id}
    assert {r["reservation_id"] for r in rows("model_call_budget_reservation_scopes")} == {booked.reservation_id}
    assert rows("llm_calls") == []


def test_planning_author_coalesces_existing_group_even_after_adviser_link():
    parent = coordinator()
    adviser(parent)
    author = begin_model_descendant_budget(parent, "planning", WorkloadLimits(17), now=110)
    assert author.owner.scope_id == parent.owner.scope_id and author.child.scope_id == parent.child.scope_id
    assert author._ancestors == () and author.limits.max_output_tokens_per_call == 17
    reserve(author)
    assert len(rows("model_task_budgets")) == 3 and len(rows("model_task_budget_links")) == 2
    assert len(rows("model_call_budget_reservation_scopes")) == 2


def test_group_exhausts_from_authors_and_advisers_even_with_root_and_leaf_capacity():
    parent = coordinator()
    reserve(parent, now=100)
    child = adviser(parent)
    reserve(child)
    with pytest.raises(ModelBudgetUnavailable, match="budget_spend_exhausted"):
        reserve(child)
    assert len(rows("model_call_budget_reservations")) == 2
    assert len(rows("model_call_budget_reservation_scopes")) == 5


def test_root_pool_includes_ordinary_work_outside_planning_group():
    parent = coordinator(WorkloadLimits(100, 100, .2004), WorkloadLimits(100, 50, 1))
    reserve_model_call_budget(parent.owner, "ordinary", "test", "model", "direct_api", "provider_api", 100_000, 100, now=100)
    reserve(parent, now=100)
    child = adviser(parent)
    with pytest.raises(ModelBudgetUnavailable, match="budget_spend_exhausted"):
        reserve(child)
    assert len(rows("model_call_budget_reservations")) == 2


def test_leaf_ceiling_is_independent_of_author_pool():
    parent = coordinator(group_limits=WorkloadLimits(100, 50, 1))
    child = adviser(parent, WorkloadLimits(100, 20, .1002))
    reserve(child)
    reserve(parent, now=110)
    with pytest.raises(ModelBudgetUnavailable, match="budget_spend_exhausted"):
        reserve(child)
    assert len(rows("model_call_budget_reservations")) == 2


@pytest.mark.parametrize("root, group, leaf, expected", [
    (WorkloadLimits(7, 15, 1), WorkloadLimits(11, 50, 1), WorkloadLimits(17, 50, 1), (7, 115)),
    (WorkloadLimits(17, 100, 1), WorkloadLimits(7, 15, 1), WorkloadLimits(11, 50, 1), (7, 115)),
    (WorkloadLimits(17, 100, 1), WorkloadLimits(11, 50, 1), WorkloadLimits(7, 5, 1), (7, 115)),
])
def test_every_scope_contributes_output_cap_and_absolute_deadline(root, group, leaf, expected):
    child = adviser(coordinator(root, group), leaf)
    assert (child.limits.max_output_tokens_per_call, child.child.deadline_at) == expected
    assert remaining_child_seconds(child, now=114) == 1
    assert remaining_child_seconds(child, now=116) == 0
    with pytest.raises(ModelBudgetUnavailable, match="budget_deadline_exhausted"):
        reserve(child, now=116)


def test_failed_or_cancelled_attempts_never_refund_and_same_task_retries_charge_again():
    child = adviser()
    first, second = reserve(child), reserve(child)
    assert first.reservation_id != second.reservation_id
    with pytest.raises(ModelBudgetUnavailable, match="budget_spend_exhausted"):
        reserve(child)
    assert len(rows("model_call_budget_reservations")) == 2 and len(rows("model_call_budget_reservation_scopes")) == 6


def test_null_configuration_and_intermediate_tightening_preserve_entire_chain():
    parent = coordinator()
    child = adviser(parent)
    tightened = begin_model_descendant_budget(parent, "planning", WorkloadLimits(7, 15, .1002), now=111)
    with pytest.raises(ModelBudgetUnavailable, match="budget_policy_mismatch"):
        reserve(child, now=111)
    recovered = resolve_model_child_budget("council", "parent-1", WorkloadLimits(), now=112)
    assert recovered.owner.scope_id == child.owner.scope_id and recovered.child.scope_id == child.child.scope_id
    assert recovered._ancestors[0].scope_id == tightened.child.scope_id
    assert recovered.limits == WorkloadLimits(7, 5, .1002) and recovered.child.deadline_at == 115


def test_expired_status_validation_reads_current_bounds_without_clock_or_write(monkeypatch):
    child = adviser()
    assert remaining_child_seconds(child, now=131) == 0
    with closing(sqlite3.connect(usage_ledger.DB_PATH)) as conn:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    before = usage_ledger.DB_PATH.read_bytes()
    monkeypatch.setattr(model_budget.time, "time", lambda: pytest.fail("status sampled a clock"))
    monkeypatch.setattr(usage_ledger, "model_budget_connection", lambda: pytest.fail("status opened writable storage"))
    recovered = validate_model_child_budget(child)
    assert recovered == child and usage_ledger.DB_PATH.read_bytes() == before


@pytest.mark.parametrize("mutation", ["seal", "ancestors", "workload", "parent", "scope", "limits"])
def test_mutated_parent_or_ancestry_cannot_mint_or_reserve(mutation):
    child = adviser()
    group = child._ancestors[0]
    if mutation == "seal":
        bad = replace(child, _seal="0" * 64)
    elif mutation == "ancestors":
        bad = replace(child, _ancestors=())
    else:
        changed = replace(group, **{
            "workload": {"workload": "research"}, "parent": {"parent_request_id": "other-parent"},
            "scope": {"scope_id": "f" * 32}, "limits": {"limits": WorkloadLimits()},
        }[mutation])
        bad = replace(child, _ancestors=(changed,))
    for operation in (lambda: validate_model_child_budget(bad), lambda: reserve(bad),
                      lambda: begin_model_descendant_budget(bad, "research", WorkloadLimits(7), now=110)):
        with pytest.raises(ModelBudgetUnavailable):
            operation()
    assert rows("model_call_budget_reservations") == []


@pytest.mark.parametrize("damage", ["cycle", "missing", "foreign", "parent", "replaced", "weakened"])
def test_invalid_stored_ancestor_refuses_without_direct_root_fallback(damage):
    child = adviser()
    group = child._ancestors[0]
    with closing(sqlite3.connect(usage_ledger.DB_PATH)) as conn:
        if damage == "cycle":
            conn.execute("INSERT INTO model_task_budget_links VALUES (?,?,?)", (child.owner.scope_id, child.child.scope_id, 110))
        elif damage == "missing":
            conn.execute("DELETE FROM model_task_budgets WHERE scope_id=?", (group.scope_id,))
        else:
            field, value = {"foreign": ("user_id", "foreign"), "parent": ("parent_request_id", "other-parent"),
                            "replaced": ("scope_id", "f" * 32), "weakened": ("spend_ceiling_usd", "99")}[damage]
            conn.execute(f"UPDATE model_task_budgets SET {field}=? WHERE scope_id=?", (value, group.scope_id))
        conn.commit()
    with pytest.raises(ModelBudgetUnavailable):
        validate_model_child_budget(child)
    with pytest.raises(ModelBudgetUnavailable):
        reserve(child)
    if damage != "weakened":
        with pytest.raises(ModelBudgetUnavailable):
            resolve_model_child_budget("council", "parent-1", WorkloadLimits(), now=110)
    assert rows("model_call_budget_reservations") == []


def test_existing_direct_council_cannot_be_reparented_to_planning():
    parent = coordinator()
    direct = begin_model_child_budget(parent.owner, "council", WorkloadLimits(100, 20, 1), now=110)
    before = rows("model_task_budget_links")
    with pytest.raises(ModelBudgetUnavailable, match="budget_scope_mismatch"):
        adviser(parent)
    assert rows("model_task_budget_links") == before
    assert validate_model_child_budget(direct).owner.scope_id == parent.owner.scope_id


def test_bare_group_handle_and_older_ancestor_workload_do_not_authorize_descendants():
    parent = coordinator()
    for budget, workload in ((parent.child, "council"), (ChildTaskBudget(parent.owner, parent.child), "council"),
                             (parent, "developer")):
        with pytest.raises(ModelBudgetUnavailable):
            begin_model_descendant_budget(budget, workload, WorkloadLimits(), now=110)


def test_foreign_tenant_cannot_validate_recover_or_spend():
    child = adviser()
    with user_id_scope("foreign"):
        with pytest.raises(ModelBudgetUnavailable, match="budget_scope_mismatch"):
            validate_model_child_budget(child)
        with pytest.raises(ModelBudgetUnavailable, match="budget_scope_mismatch"):
            reserve(child)
        assert resolve_model_child_budget("council", "parent-1", WorkloadLimits(), now=110) is None


def test_genuinely_all_null_ordinary_descendants_avoid_storage_and_clock(monkeypatch):
    root = begin_model_task_budget("developer", "parent-1", WorkloadLimits())
    parent = begin_model_child_budget(root, "planning", WorkloadLimits())
    monkeypatch.setattr(model_budget.time, "time", lambda: pytest.fail("uncapped clock"))
    monkeypatch.setattr(usage_ledger, "model_budget_connection", lambda: pytest.fail("uncapped database"))
    child = begin_model_descendant_budget(parent, "council", WorkloadLimits())
    assert child.owner.scope_id is child.child.scope_id is child._ancestors[0].scope_id is None
    assert math.isinf(remaining_child_seconds(child)) and reserve(child).reserved_cost_usd is None
    assert not usage_ledger.DB_PATH.exists()


def test_constraint_materializes_complete_previously_ephemeral_chain():
    root = begin_model_task_budget("developer", "parent-1", WorkloadLimits())
    parent = begin_model_child_budget(root, "planning", WorkloadLimits())
    child = begin_model_descendant_budget(parent, "council", WorkloadLimits(), now=100)
    leaf = begin_model_descendant_budget(child, "research", WorkloadLimits(7), now=110)
    assert [b.workload for b in (leaf.owner, *leaf._ancestors, leaf.child)] == ["developer", "planning", "council", "research"]
    assert len(rows("model_task_budgets")) == 4 and len(rows("model_task_budget_links")) == 3
    assert validate_model_child_budget(leaf) == leaf


def test_standalone_coalesced_planning_parent_does_not_double_root():
    root = begin_model_task_budget("planning", "parent-1", WorkloadLimits(100, 50, 1), now=100)
    parent = begin_model_child_budget(root, "planning", root.limits, now=100)
    child = begin_model_descendant_budget(parent, "council", WorkloadLimits(), now=110)
    assert child._ancestors == ()
    reserve(child)
    assert len(rows("model_call_budget_reservation_scopes")) == 2


def test_all_null_standalone_coalesced_planning_descendant_has_unique_root(monkeypatch):
    root = begin_model_task_budget("planning", "parent-1", WorkloadLimits())
    parent = begin_model_child_budget(root, "planning", WorkloadLimits())
    monkeypatch.setattr(model_budget.time, "time", lambda: pytest.fail("coalesced uncapped clock"))
    monkeypatch.setattr(usage_ledger, "model_budget_connection", lambda: pytest.fail("coalesced uncapped database"))
    child = begin_model_descendant_budget(parent, "council", WorkloadLimits())
    assert child.owner.workload == "planning" and child.child.workload == "council" and child._ancestors == ()
    assert child.limits == WorkloadLimits() and math.isinf(remaining_child_seconds(child))
    assert reserve(child).reserved_cost_usd is None and not usage_ledger.DB_PATH.exists()


def test_read_only_validation_reports_tighter_root_bounds_without_mutating_leaf():
    child = adviser()
    begin_model_task_budget("developer", "parent-1", WorkloadLimits(7, 15, .1002), now=111)
    before = rows("model_task_budgets")
    updated = validate_model_child_budget(child)
    assert updated.limits.max_output_tokens_per_call == 7
    assert updated.limits.max_estimated_spend_usd_per_task == .1002
    assert updated.limits.deadline_seconds == 15
    assert rows("model_task_budgets") == before


def test_fresh_process_recovers_full_null_sponsorship_and_shared_remaining_pool():
    child = adviser()
    reserve(child)
    price_path = usage_ledger.DB_PATH.parent / "prices.json"
    price_path.write_text(json.dumps(usage_ledger.load_price_map()))
    env = {**os.environ, "RUN_LIVE": "0", "JARVIS_COSTS_DB": str(usage_ledger.DB_PATH),
           "JARVIS_PRICE_MAP": str(price_path), "JARVIS_USER_ID": "local",
           "JARVIS_VAULT_PATH": str(price_path.parent / "no.vault"),
           "JARVIS_DB_PATH": str(price_path.parent / "unused-app.db"),
           "PYTHONPATH": str(Path(__file__).resolve().parents[2])}
    code = '''import json
from jarvis.model_budget import resolve_model_child_budget,reserve_model_child_call_budget,ModelBudgetUnavailable
from jarvis.model_routing import WorkloadLimits
b=resolve_model_child_budget("council","parent-1",WorkloadLimits(),now=110)
r=reserve_model_child_call_budget(b,"same-task","test","model","direct_api","provider_api",100000,100,now=110)
try:
 reserve_model_child_call_budget(b,"same-task","test","model","direct_api","provider_api",100000,100,now=110)
except ModelBudgetUnavailable as e:
 print(json.dumps({"scopes":[x.scope_id for x in (b.owner,*b._ancestors,b.child)],"error":e.code}))
'''
    result = subprocess.run([sys.executable, "-c", code], text=True, capture_output=True, check=True,
        timeout=10, env=env, cwd=Path(__file__).resolve().parents[2])
    observed = json.loads(result.stdout)
    assert observed == {"scopes": [child.owner.scope_id, child._ancestors[0].scope_id, child.child.scope_id],
                        "error": "budget_spend_exhausted"}
    assert len(rows("model_call_budget_reservations")) == 2 and len(rows("model_call_budget_reservation_scopes")) == 6
    assert rows("llm_calls") == []
