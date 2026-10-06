import math
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from decimal import Decimal

import pytest

from jarvis import model_budget, usage_ledger
from jarvis.model_budget import (
    ModelBudgetUnavailable,
    begin_model_task_budget,
    remaining_seconds,
    reserve_model_call_budget,
)
from jarvis.model_routing import WorkloadLimits
from jarvis.tenant import user_id_scope


@pytest.fixture(autouse=True)
def isolated_budget(tmp_path, monkeypatch):
    monkeypatch.setattr(usage_ledger, "DB_PATH", tmp_path / "costs.db")
    monkeypatch.setenv("JARVIS_USER_ID", "local")
    monkeypatch.setattr(usage_ledger, "_price_map_cache", {"version": "fixture", "models": {
        "test/model": {
            "input_per_m": 1, "output_per_m": 2,
            "cache_write_mult": 1, "cache_read_mult": 0.1,
        },
    }})


def _budget(*, ceiling=0.2004, deadline=None, output=100, now=100):
    return begin_model_task_budget(
        "analyst", "parent-1", WorkloadLimits(output, deadline, ceiling), now=now,
    )


def _reserve(budget, *, task="call-1", now=100, provider="test", model="model",
             input_tokens=100_000, output_tokens=100, route="direct_api", billing="provider_api"):
    return reserve_model_call_budget(
        budget, task, provider, model, route, billing, input_tokens, output_tokens, now=now,
    )


def _counts():
    with sqlite3.connect(usage_ledger.DB_PATH) as conn:
        return tuple(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in (
            "model_task_budgets", "model_call_budget_reservations", "llm_calls",
        ))


@pytest.mark.parametrize("limits", [WorkloadLimits(), WorkloadLimits(100)])
def test_new_uncapped_task_never_creates_storage_or_samples_clock(limits, monkeypatch):
    def unexpected():
        raise AssertionError("unexpected mutable ledger or clock")

    monkeypatch.setattr(usage_ledger, "model_budget_connection", unexpected)
    monkeypatch.setattr(model_budget.time, "time", unexpected)
    budget = begin_model_task_budget("analyst", "parent-1", limits)
    assert budget.started_at is budget.deadline_at is budget.scope_id is None
    assert remaining_seconds(budget) == math.inf
    first = _reserve(budget)
    second = _reserve(budget)
    assert first.reservation_id != second.reservation_id
    assert first.reserved_cost_usd is first.reserved_total_usd is None
    assert not usage_ledger.DB_PATH.exists()


def test_old_ledger_without_budget_schema_stays_unchanged_for_uncapped_task():
    usage_ledger.record_call("analyst", "test", "model", input_tokens=1, output_tokens=1)
    before = usage_ledger.DB_PATH.read_bytes()
    budget = begin_model_task_budget("analyst", "parent-1", WorkloadLimits())
    assert budget.scope_id is None
    assert usage_ledger.DB_PATH.read_bytes() == before
    with sqlite3.connect(usage_ledger.DB_PATH) as conn:
        assert conn.execute(
            "SELECT 1 FROM sqlite_master WHERE name='model_task_budgets'",
        ).fetchone() is None
        assert conn.execute("SELECT COUNT(*) FROM llm_calls").fetchone() == (1,)


def test_uncapped_new_parent_does_not_write_to_existing_budget_storage():
    _budget()
    with sqlite3.connect(usage_ledger.DB_PATH) as conn:
        before = conn.execute("SELECT * FROM model_task_budgets").fetchall()
    uncapped = begin_model_task_budget("analyst", "new-parent", WorkloadLimits())
    assert uncapped.scope_id is None
    with sqlite3.connect(usage_ledger.DB_PATH) as conn:
        assert conn.execute("SELECT * FROM model_task_budgets").fetchall() == before
    assert _counts() == (1, 0, 0)


def test_atomic_reservations_exhaust_exact_decimal_ceiling_without_usage_rows():
    budget = _budget()
    first = _reserve(budget)
    second = _reserve(budget, task="call-2")
    assert first.reserved_cost_usd == second.reserved_cost_usd == 0.1002
    assert second.reserved_total_usd == 0.2004
    with pytest.raises(ModelBudgetUnavailable, match="budget_spend_exhausted"):
        _reserve(budget, task="call-3")
    assert _counts() == (1, 2, 0)


def test_replaying_same_call_id_charges_a_fresh_attempt_and_retains_failures():
    budget = _budget()
    first = _reserve(budget)
    # A failed or cancelled provider attempt has no refund operation. A
    # subsequent attempt with the same caller ID consumes another slot.
    second = _reserve(budget)
    assert first.reservation_id != second.reservation_id
    with pytest.raises(ModelBudgetUnavailable, match="budget_spend_exhausted"):
        _reserve(budget)
    assert _counts() == (1, 2, 0)


def test_reservations_are_durable_across_independent_budget_handles():
    first_handle = _budget()
    _reserve(first_handle)
    second_handle = _budget(now=101)
    assert first_handle.scope_id == second_handle.scope_id
    assert second_handle.started_at == first_handle.started_at == 100
    second = _reserve(second_handle, now=101)
    assert second.reserved_total_usd == 0.2004
    assert _counts() == (1, 2, 0)


def test_concurrent_independent_connections_cannot_overspend(monkeypatch):
    budget = _budget(ceiling=0.1002)
    barrier = threading.Barrier(12)
    original = usage_ledger.model_budget_connection
    connection_calls = []

    def tracked_connection():
        result = original()
        connection_calls.append(result)
        return result

    monkeypatch.setattr(usage_ledger, "model_budget_connection", tracked_connection)

    def attempt(index):
        barrier.wait(timeout=5)
        try:
            return _reserve(budget, task=f"call-{index}")
        except ModelBudgetUnavailable as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(attempt, range(12)))
    assert sum(not isinstance(value, str) for value in results) == 1
    assert results.count("budget_spend_exhausted") == 11
    assert len(connection_calls) == len({id(conn) for conn in connection_calls}) == 12
    assert _counts() == (1, 1, 0)


def test_strictest_parent_constraints_survive_looser_policy_and_stale_handles():
    original = _budget(ceiling=1, deadline=30)
    tighter = _budget(ceiling=0.2, deadline=10, output=50, now=105)
    looser = _budget(ceiling=9, deadline=90, output=1000, now=106)
    assert tighter == replace(looser)
    assert looser.started_at == 100
    assert looser.deadline_at == 110
    assert looser.spend_ceiling_usd == 0.2
    assert looser.limits.max_output_tokens_per_call == 50
    assert remaining_seconds(original, now=107) == 3
    with pytest.raises(ModelBudgetUnavailable, match="budget_output_limit"):
        _reserve(original, output_tokens=51, now=107)
    _reserve(original, output_tokens=50, now=107)
    assert _counts() == (1, 1, 0)


def test_restart_with_all_null_limits_cannot_clear_deadline_or_reserved_spend():
    prior = _budget(deadline=10)
    _reserve(prior)
    restarted = begin_model_task_budget("analyst", "parent-1", WorkloadLimits(), now=105)
    assert restarted.scope_id == prior.scope_id
    assert restarted.started_at == 100
    assert restarted.limits == prior.limits
    assert remaining_seconds(restarted, now=105) == 5
    _reserve(restarted, now=105)
    with pytest.raises(ModelBudgetUnavailable, match="budget_spend_exhausted"):
        _reserve(restarted, now=105)
    assert _counts() == (1, 2, 0)


def test_output_only_reopen_inherits_spend_and_tightens_prior_output_limit():
    prior = _budget()
    restarted = begin_model_task_budget("analyst", "parent-1", WorkloadLimits(50), now=105)
    assert restarted.scope_id == prior.scope_id
    assert restarted.spend_ceiling_usd == prior.spend_ceiling_usd
    assert restarted.limits.max_output_tokens_per_call == 50


def test_deadline_uses_original_task_start_and_expired_parent_cannot_restart():
    budget = _budget(deadline=5)
    assert remaining_seconds(budget, now=102) == 3
    reopened = _budget(deadline=5, now=105)
    assert reopened.started_at == 100
    assert remaining_seconds(reopened, now=105) == 0
    with pytest.raises(ModelBudgetUnavailable, match="budget_deadline_exhausted"):
        _reserve(reopened, now=105)
    assert _counts() == (1, 0, 0)


def test_deadline_only_scope_does_not_require_prices_or_charge_usage(monkeypatch):
    budget = _budget(ceiling=None, deadline=5)
    monkeypatch.setattr(usage_ledger, "load_price_map", lambda: pytest.fail("price lookup"))
    reservation = _reserve(budget, now=101)
    assert reservation.reserved_cost_usd is None
    assert _counts() == (1, 0, 0)


@pytest.mark.parametrize("now", [True, -1, float("inf"), float("nan"), "100"])
def test_invalid_clock_refuses_with_fixed_status(now):
    with pytest.raises(ModelBudgetUnavailable, match="budget_clock_unavailable"):
        _budget(now=now)
    assert not usage_ledger.DB_PATH.exists()


def test_backward_clock_refuses_instead_of_extending_existing_budget():
    budget = _budget(deadline=10)
    _reserve(budget, now=102)
    with pytest.raises(ModelBudgetUnavailable, match="budget_clock_mismatch"):
        remaining_seconds(budget, now=101)
    with pytest.raises(ModelBudgetUnavailable, match="budget_clock_mismatch"):
        _budget(now=101)
    assert _counts() == (1, 1, 0)


def test_expired_call_refusal_retains_clock_floor_against_rollback():
    budget = _budget(deadline=5)
    with pytest.raises(ModelBudgetUnavailable, match="budget_deadline_exhausted"):
        _reserve(budget, now=105)
    with pytest.raises(ModelBudgetUnavailable, match="budget_clock_mismatch"):
        _reserve(budget, now=104)
    assert _counts() == (1, 0, 0)


def test_budget_deadline_includes_time_waiting_for_storage_admission(monkeypatch):
    samples = iter([100, 104])
    monkeypatch.setattr(model_budget.time, "time", lambda: next(samples))
    budget = _budget(deadline=5, now=None)
    assert budget.started_at == 100
    assert budget.deadline_at == 105
    assert remaining_seconds(budget, now=104) == 1


@pytest.mark.parametrize("field,value", [
    ("parent_request_id", "other-parent"), ("workload", "developer"),
    ("user_id", "other-user"), ("scope_id", "other-scope"), ("started_at", 99),
])
def test_rebound_budget_handle_fails_closed(field, value):
    budget = _budget()
    with pytest.raises(ModelBudgetUnavailable, match="budget_scope_mismatch"):
        _reserve(replace(budget, **{field: value}))
    assert _counts() == (1, 0, 0)


def test_parent_scopes_are_owned_by_authenticated_user_identity():
    with user_id_scope("alice"):
        alice = _budget(ceiling=0.1002)
        _reserve(alice)
    with user_id_scope("bob"):
        bob = _budget(ceiling=0.1002)
        _reserve(bob)
        with pytest.raises(ModelBudgetUnavailable, match="budget_scope_mismatch"):
            _reserve(alice)
    assert alice.scope_id != bob.scope_id
    assert _counts() == (2, 2, 0)


@pytest.mark.parametrize("field", ["input_per_m", "output_per_m", "cache_write_mult", "cache_read_mult"])
@pytest.mark.parametrize("value", [None, True, -1, float("nan"), float("inf"), "1"])
def test_bad_prices_never_become_free_reservations(field, value):
    budget = _budget()
    usage_ledger._price_map_cache["models"]["test/model"][field] = value
    with pytest.raises(ModelBudgetUnavailable, match="budget_price_unavailable"):
        _reserve(budget)
    assert _counts() == (1, 0, 0)


@pytest.mark.parametrize("field", ["input_per_m", "output_per_m", "cache_write_mult", "cache_read_mult"])
def test_missing_price_fields_fail_closed(field):
    budget = _budget()
    usage_ledger._price_map_cache["models"]["test/model"].pop(field)
    with pytest.raises(ModelBudgetUnavailable, match="budget_price_unavailable"):
        _reserve(budget)


def test_unknown_model_and_price_loader_failure_refuse_without_exception_payload(monkeypatch, capsys):
    budget = _budget()
    with pytest.raises(ModelBudgetUnavailable, match="budget_price_unavailable"):
        _reserve(budget, model="missing")

    def bad_prices():
        raise RuntimeError("PRIVATE_PRICE_EXCEPTION_CANARY")

    monkeypatch.setattr(usage_ledger, "load_price_map", bad_prices)
    with pytest.raises(ModelBudgetUnavailable) as caught:
        _reserve(budget)
    assert str(caught.value) == caught.value.code == "budget_price_unavailable"
    assert "PRIVATE_PRICE_EXCEPTION_CANARY" not in capsys.readouterr().err


@pytest.mark.parametrize("provider,model", [("anthropic", "claude-sonnet-5"), ("openrouter", "anthropic/claude-sonnet-5")])
def test_anthropic_reservation_includes_one_hour_cache_write_premium(provider, model):
    usage_ledger._price_map_cache["models"][f"{provider}/{model}"] = {
        "input_per_m": 1, "output_per_m": 2,
        "cache_write_mult": 1.25, "cache_read_mult": 0.1,
    }
    result = _reserve(_budget(ceiling=1), provider=provider, model=model)
    assert result.reserved_cost_usd == 0.2002


def test_highest_configured_cache_rate_is_reserved():
    row = usage_ledger._price_map_cache["models"]["test/model"]
    row["cache_write_mult"] = 3
    row["cache_read_mult"] = 4
    result = _reserve(_budget(ceiling=1))
    assert result.reserved_cost_usd == 0.4002


def test_decimal_accounting_does_not_reject_three_exact_tenths_or_admit_a_fourth():
    usage_ledger._price_map_cache["models"]["test/model"]["output_per_m"] = 0
    budget = _budget(ceiling=0.3)
    for _ in range(3):
        last = _reserve(budget)
    assert last.reserved_total_usd == 0.3
    with pytest.raises(ModelBudgetUnavailable, match="budget_spend_exhausted"):
        _reserve(budget)
    with sqlite3.connect(usage_ledger.DB_PATH) as conn:
        values = conn.execute("SELECT reserved_cost_usd FROM model_call_budget_reservations").fetchall()
    assert sum(Decimal(value[0]) for value in values) == Decimal("0.3")


@pytest.mark.parametrize("route,billing", [("subscription", "subscription"), ("direct_api", "subscription"), ("local", "local")])
def test_spend_admission_requires_bound_api_billing(route, billing):
    with pytest.raises(ModelBudgetUnavailable, match="budget_unsupported_route"):
        _reserve(_budget(), route=route, billing=billing)


@pytest.mark.parametrize("value", [None, True, 0, 101, 32_001])
def test_spend_reservation_requires_supported_output_bound(value):
    with pytest.raises(ModelBudgetUnavailable, match="budget_output_limit"):
        _reserve(_budget(), output_tokens=value)


def test_unreadable_existing_storage_cannot_make_uncapped_parent_unrestricted(monkeypatch, capsys):
    usage_ledger.DB_PATH.write_bytes(b"PRIVATE_DATABASE_EXCEPTION_CANARY")
    with pytest.raises(ModelBudgetUnavailable, match="budget_storage_unavailable"):
        begin_model_task_budget("analyst", "parent-1", WorkloadLimits())
    assert "PRIVATE_DATABASE_EXCEPTION_CANARY" not in capsys.readouterr().err


def test_mutable_database_failure_is_authoritative_and_payload_free(monkeypatch, capsys):
    budget = _budget()

    def failed_connection():
        raise RuntimeError("PRIVATE_DATABASE_EXCEPTION_CANARY")

    monkeypatch.setattr(usage_ledger, "model_budget_connection", failed_connection)
    with pytest.raises(ModelBudgetUnavailable) as caught:
        _reserve(budget)
    assert str(caught.value) == caught.value.code == "budget_storage_unavailable"
    assert "PRIVATE_DATABASE_EXCEPTION_CANARY" not in capsys.readouterr().err
    assert _counts() == (1, 0, 0)
