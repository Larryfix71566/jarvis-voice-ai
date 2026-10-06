"""Host budget publication and recovery across actual Python processes."""
import json
import math
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from dataclasses import replace
from contextlib import closing

import pytest

from jarvis import model_budget, usage_ledger
from jarvis.model_budget import (
    ModelBudgetUnavailable, TaskBudget, begin_model_child_budget,
    begin_model_task_budget, bind_model_task_budget_for_transport,
    recover_model_task_budget_for_transport, remaining_child_seconds,
    resolve_model_child_budget,
)
from jarvis.model_routing import WorkloadLimits
from jarvis.tenant import user_id_scope
from tests.unit.test_model_budget import isolated_budget


def bind(limits=WorkloadLimits(), child_limits=WorkloadLimits(), *, parent="transport-parent"):
    owner = begin_model_task_budget("developer", parent, limits, now=100)
    return bind_model_task_budget_for_transport(owner, "planning", child_limits,
                                               started_at=100, now=110)


def records(table):
    with sqlite3.connect(usage_ledger.DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(row) for row in conn.execute(f"SELECT * FROM {table}")]


_RECEIVER = """
import json, sys
from jarvis.model_budget import (ModelBudgetUnavailable,
    recover_model_task_budget_for_transport, resolve_model_child_budget,
    reserve_model_child_call_budget)
from jarvis.model_routing import WorkloadLimits
packet = json.load(sys.stdin)
try:
    # Expected workloads are host-side constants, not packet policy.
    root = recover_model_task_budget_for_transport('developer', packet['parent'],
                                                   scope_id=packet['owner_scope_id'])
    child = resolve_model_child_budget('planning', packet['parent'], WorkloadLimits(),
                                       now=packet['now'])
    if child is None or (child.owner.scope_id, child.child.scope_id) != (
            root.scope_id, packet['child_scope_id']):
        raise ModelBudgetUnavailable('budget_scope_mismatch')
    reservation = None
    if packet.get('reserve'):
        reservation = reserve_model_child_call_budget(child, 'same-task', 'test', 'model',
            'direct_api', 'provider_api', 100_000,
            child.limits.max_output_tokens_per_call or 100, now=packet['now'])
    print(json.dumps({'owner_scope': root.scope_id, 'child_scope': child.child.scope_id,
        'owner_workload': root.workload, 'child_workload': child.workload,
        'parent': child.parent_request_id, 'owner_start': root.started_at,
        'child_start': child.child.started_at, 'deadline': child.child.deadline_at,
        'limits': child.limits.as_metadata(),
        'reservation': None if reservation is None else reservation.reservation_id}))
except ModelBudgetUnavailable as exc:
    print(json.dumps({'error': exc.code}))
"""


def receive(binding, *, now=110, reserve=False, owner_scope=None, child_scope=None, tenant="local"):
    prices = usage_ledger.DB_PATH.parent / "transport-prices.json"
    prices.write_text(json.dumps(usage_ledger.load_price_map()))
    env = {**os.environ, "RUN_LIVE": "0", "JARVIS_COSTS_DB": str(usage_ledger.DB_PATH),
           "JARVIS_PRICE_MAP": str(prices), "JARVIS_USER_ID": tenant,
           "JARVIS_DB_PATH": str(prices.parent / "unused-app.db"),
           "JARVIS_VAULT_PATH": str(prices.parent / "no.vault"),
           "PYTHONPATH": str(Path(__file__).resolve().parents[2])}
    packet = {"parent": binding.parent_request_id, "owner_scope_id": owner_scope or binding.owner.scope_id,
              "child_scope_id": child_scope or binding.child.scope_id, "now": now, "reserve": reserve}
    completed = subprocess.run([sys.executable, "-c", _RECEIVER], input=json.dumps(packet),
        text=True, capture_output=True, check=True, timeout=10, env=env,
        cwd=Path(__file__).resolve().parents[2])
    return json.loads(completed.stdout)


@pytest.mark.parametrize("limits, child_limits, output", [
    (WorkloadLimits(), WorkloadLimits(), None),
    (WorkloadLimits(7), WorkloadLimits(), 7),
    (WorkloadLimits(), WorkloadLimits(9), 9),
])
def test_fresh_process_recovers_null_and_output_only_authority(limits, child_limits, output):
    binding = bind(limits, child_limits)
    assert binding.owner.scope_id is not None and binding.child.scope_id is not None
    received = receive(binding)
    assert received["owner_scope"] == binding.owner.scope_id
    assert received["child_scope"] == binding.child.scope_id
    assert received["owner_workload"] == "developer" and received["child_workload"] == "planning"
    assert received["owner_start"] == received["child_start"] == 100
    assert received["limits"]["max_output_tokens_per_call"] == output
    assert received["limits"]["deadline_seconds"] is None
    assert received["limits"]["max_estimated_spend_usd_per_task"] is None
    assert math.isinf(remaining_child_seconds(binding, now=110))
    assert records("model_call_budget_reservations") == records("llm_calls") == []


def test_ordinary_all_null_defaults_still_avoid_store_and_clock(monkeypatch):
    def unexpected():
        pytest.fail("ordinary uncapped call sampled a clock or created storage")
    monkeypatch.setattr(model_budget.time, "time", unexpected)
    monkeypatch.setattr(usage_ledger, "model_budget_connection", unexpected)
    root = begin_model_task_budget("developer", "ordinary-parent", WorkloadLimits())
    child = begin_model_child_budget(root, "planning", WorkloadLimits())
    assert root.scope_id is child.child.scope_id is None
    assert not usage_ledger.DB_PATH.exists()


def test_binding_and_nullable_resume_preserve_scope_start_and_strictest_bounds():
    binding = bind(WorkloadLimits(100, 50, 1), WorkloadLimits(80, 40, .5))
    begin_model_task_budget("developer", binding.parent_request_id, WorkloadLimits(7, 20, .2004), now=112)
    received = receive(binding, now=113)
    assert received["owner_scope"] == binding.owner.scope_id and received["child_scope"] == binding.child.scope_id
    assert received["owner_start"] == received["child_start"] == 100
    assert received["deadline"] == 120
    assert received["limits"] == WorkloadLimits(7, 20, .2004).as_metadata()
    root = recover_model_task_budget_for_transport("developer", binding.parent_request_id,
                                                    scope_id=binding.owner.scope_id)
    rebound = bind_model_task_budget_for_transport(root, "planning", WorkloadLimits(), started_at=115, now=115)
    assert rebound.owner.scope_id == binding.owner.scope_id and rebound.child.scope_id == binding.child.scope_id
    assert rebound.owner.started_at == rebound.child.started_at == 100
    assert rebound.child.deadline_at == 120 and rebound.limits == WorkloadLimits(7, 20, .2004)


def test_each_fresh_process_reserves_one_attempt_against_original_pools():
    binding = bind(WorkloadLimits(100, None, .2004), WorkloadLimits(200, None, 1))
    first, second = receive(binding, reserve=True), receive(binding, reserve=True)
    assert first["reservation"] != second["reservation"]
    assert receive(binding, reserve=True) == {"error": "budget_spend_exhausted"}
    attempts = records("model_call_budget_reservations")
    memberships = records("model_call_budget_reservation_scopes")
    assert len(attempts) == 2 and len(memberships) == 4
    assert {row["scope_id"] for row in attempts} == {binding.owner.scope_id}
    assert {row["scope_id"] for row in memberships} == {binding.owner.scope_id, binding.child.scope_id}
    assert records("llm_calls") == []


@pytest.mark.parametrize("change", ["owner_scope", "child_scope", "tenant"])
def test_fresh_process_rejects_wrong_locator_or_tenant_before_reservation(change):
    binding = bind(WorkloadLimits(100, None, .2))
    options = {"owner_scope": {"owner_scope": "0" * 32},
               "child_scope": {"child_scope": "0" * 32},
               "tenant": {"tenant": "foreign"}}[change]
    assert receive(binding, reserve=True, **options) == {"error": "budget_scope_mismatch"}
    assert records("model_call_budget_reservations") == records("llm_calls") == []


def test_recover_only_never_samples_clock_or_writes_authority(monkeypatch):
    binding = bind()
    with closing(sqlite3.connect(usage_ledger.DB_PATH)) as conn:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    before = usage_ledger.DB_PATH.read_bytes()
    def unexpected():
        pytest.fail("recovery sampled a new clock or opened mutable storage")
    monkeypatch.setattr(model_budget.time, "time", unexpected)
    monkeypatch.setattr(usage_ledger, "model_budget_connection", unexpected)
    owner = recover_model_task_budget_for_transport("developer", binding.parent_request_id,
                                                    scope_id=binding.owner.scope_id)
    assert owner == binding.owner
    assert usage_ledger.DB_PATH.read_bytes() == before


@pytest.mark.parametrize("change", ["scope", "parent", "workload", "child", "foreign"])
def test_exact_durable_root_recovery_rejects_identity_changes(change):
    binding = bind(WorkloadLimits(7))
    workload, parent, scope = "developer", binding.parent_request_id, binding.owner.scope_id
    if change == "scope":
        scope = "0" * 32
    elif change == "parent":
        parent = "different-parent"
    elif change == "workload":
        workload = "analyst"
    elif change == "child":
        workload, scope = "planning", binding.child.scope_id
    with user_id_scope("foreign" if change == "foreign" else "local"):
        with pytest.raises(ModelBudgetUnavailable, match="budget_scope_mismatch"):
            recover_model_task_budget_for_transport(workload, parent, scope_id=scope)


@pytest.mark.parametrize("locator", [None, True, "", "scope", "f" * 64])
def test_invalid_or_missing_locator_never_creates_authority(locator):
    with pytest.raises(ModelBudgetUnavailable, match="budget_scope_mismatch"):
        recover_model_task_budget_for_transport("developer", "missing-parent", scope_id=locator)
    assert not usage_ledger.DB_PATH.exists()


def test_valid_looking_missing_root_refuses_without_storage_creation():
    with pytest.raises(ModelBudgetUnavailable, match="budget_scope_mismatch"):
        recover_model_task_budget_for_transport("developer", "missing-parent", scope_id="0" * 32)
    assert not usage_ledger.DB_PATH.exists()


def test_transport_cannot_publish_forged_ephemeral_or_orphan_durable_owner():
    issued = begin_model_task_budget("developer", "transport-parent", WorkloadLimits(7))
    bad = [TaskBudget("local", "developer", "transport-parent", WorkloadLimits()),
           replace(issued, limits=WorkloadLimits()),
           replace(issued, scope_id="f" * 32, started_at=100, _ephemeral_seal="")]
    for owner in bad:
        with pytest.raises(ModelBudgetUnavailable):
            bind_model_task_budget_for_transport(owner, "planning", WorkloadLimits(), started_at=100, now=110)
    assert records("model_task_budgets") == []


def test_json_limits_are_not_recovery_arguments_and_replaced_root_is_refused():
    binding = bind(WorkloadLimits(7, None, .1))
    with pytest.raises(TypeError):
        recover_model_task_budget_for_transport("developer", binding.parent_request_id,
            scope_id=binding.owner.scope_id, limits=WorkloadLimits(None, None, 999))
    with sqlite3.connect(usage_ledger.DB_PATH) as conn:
        conn.execute("UPDATE model_task_budgets SET scope_id=? WHERE scope_id=?",
                     ("f" * 32, binding.owner.scope_id))
    with pytest.raises(ModelBudgetUnavailable, match="budget_scope_mismatch"):
        recover_model_task_budget_for_transport("developer", binding.parent_request_id,
                                                 scope_id=binding.owner.scope_id)


@pytest.mark.parametrize("started_at", [None, True, float("nan"), float("inf"), -1])
def test_transport_requires_valid_host_entry_timestamp(started_at):
    root = begin_model_task_budget("developer", "transport-parent", WorkloadLimits())
    with pytest.raises(ModelBudgetUnavailable, match="budget_clock_unavailable"):
        bind_model_task_budget_for_transport(root, "planning", WorkloadLimits(), started_at=started_at, now=110)
    assert not usage_ledger.DB_PATH.exists()


def test_nested_and_self_transport_refuse_without_new_link():
    binding = bind(WorkloadLimits(7))
    before = records("model_task_budget_links")
    for owner, workload in ((binding.child, "council"), (binding.owner, "developer")):
        with pytest.raises(ModelBudgetUnavailable, match="budget_scope_mismatch"):
            bind_model_task_budget_for_transport(owner, workload, WorkloadLimits(), started_at=100, now=110)
    assert records("model_task_budget_links") == before


def test_recovered_expired_root_cannot_restart_child_deadline():
    binding = bind(WorkloadLimits(7, 20))
    assert receive(binding, now=121) == {"error": "budget_deadline_exhausted"}
    assert receive(binding, now=115) == {"error": "budget_clock_mismatch"}


def test_unreadable_existing_authority_has_fixed_storage_refusal():
    usage_ledger.DB_PATH.write_bytes(b"not a sqlite database")
    with pytest.raises(ModelBudgetUnavailable, match="budget_storage_unavailable"):
        recover_model_task_budget_for_transport("developer", "transport-parent", scope_id="0" * 32)
