"""Durable optional model-task deadlines and configured-price admission.

Reservations describe local estimates, never verified provider charges.
Every admitted attempt is charged to its task before execution, including
retries whose earlier provider outcome is unknown. No result or failure
releases a reservation, and no reservation writes an observed usage row.
"""
from __future__ import annotations

import math
import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import time
from collections.abc import Iterator, Mapping
from contextlib import closing, contextmanager
from dataclasses import dataclass, field, replace
from decimal import Decimal, InvalidOperation, localcontext
from uuid import uuid4

from jarvis import usage_ledger
from jarvis.model_routing import ModelRouteError, WorkloadLimits
from jarvis.tenant import current_user_id, is_valid_user_id

_OPAQUE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,255}\Z")
_MODEL_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_./:-]{0,255}\Z")
_WORKLOAD = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
_SQLITE_MAX_INT = 2 ** 63 - 1
_EPHEMERAL_SEAL = re.compile(r"[0-9a-f]{64}\Z")
_EPHEMERAL_BUDGET_KEY = secrets.token_bytes(32)


class ModelBudgetUnavailable(ModelRouteError):
    """Fixed, payload-free refusal raised by authoritative admission."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class TaskBudget:
    user_id: str
    workload: str
    parent_request_id: str
    limits: WorkloadLimits
    scope_id: str | None = None
    started_at: float | None = None
    deadline_at: float | None = None
    spend_ceiling_usd: float | None = None
    _ephemeral_seal: str = field(default="", repr=False)


def _ephemeral_budget_seal(budget: TaskBudget) -> str:
    """Authenticate a host-issued transient handle without creating storage.

    Durable scopes use their independent SQLite record as authority. Output-
    only/all-null scopes have no such record, so a dataclass alone cannot
    authorize changing or clearing the captured parent policy.
    """
    try:
        payload = json.dumps({
            "schema_version": 1,
            "user_id": budget.user_id,
            "workload": budget.workload,
            "parent_request_id": budget.parent_request_id,
            "limits": budget.limits.as_metadata(),
            "scope_id": budget.scope_id,
            "started_at": budget.started_at,
            "deadline_at": budget.deadline_at,
            "spend_ceiling_usd": budget.spend_ceiling_usd,
        }, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
        return hmac.new(_EPHEMERAL_BUDGET_KEY, payload.encode("utf-8"), hashlib.sha256).hexdigest()
    except (ValueError, TypeError, AttributeError, OverflowError):
        raise ModelBudgetUnavailable("budget_policy_mismatch") from None


def _issue_ephemeral_budget(owner: str, workload: str, parent: str, limits: WorkloadLimits) -> TaskBudget:
    value = TaskBudget(owner, workload, parent, limits)
    return replace(value, _ephemeral_seal=_ephemeral_budget_seal(value))


@dataclass(frozen=True)
class ModelCallReservation:
    reservation_id: str
    scope_id: str | None
    reserved_cost_usd: float | None = None
    reserved_total_usd: float | None = None


def _clock_value(now: float | None) -> float:
    try:
        value = time.time() if now is None else now
        if type(value) not in {int, float} or not math.isfinite(value) or value < 0:
            raise ValueError
        return float(value)
    except Exception:
        raise ModelBudgetUnavailable("budget_clock_unavailable") from None


def _owner() -> str:
    try:
        user_id = current_user_id()
    except Exception:
        raise ModelBudgetUnavailable("budget_scope_mismatch") from None
    if not is_valid_user_id(user_id):
        raise ModelBudgetUnavailable("budget_scope_mismatch")
    return user_id


def _identifiers(workload: str, parent_request_id: str) -> None:
    if (not isinstance(workload, str) or not _WORKLOAD.fullmatch(workload)
            or not isinstance(parent_request_id, str) or not _OPAQUE_ID.fullmatch(parent_request_id)):
        raise ModelBudgetUnavailable("budget_input_invalid")


def _decimal(value: object, *, code: str) -> Decimal:
    try:
        if type(value) not in {int, float, str}:
            raise ValueError
        result = Decimal(str(value))
        if not result.is_finite() or result < 0:
            raise ValueError
        return result
    except (InvalidOperation, ValueError, OverflowError):
        raise ModelBudgetUnavailable(code) from None


def _tightest(first, second):
    if first is None:
        return second
    if second is None:
        return first
    return min(first, second)


@contextmanager
def _transaction(*, retain_clock_on_refusal: bool = False) -> Iterator[sqlite3.Connection]:
    try:
        with closing(usage_ledger.model_budget_connection()) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
                conn.commit()
            except ModelBudgetUnavailable:
                # Call admission changes only the last observed timestamp
                # before its checks. Keep that timestamp even on refusal:
                # a wall-clock rollback must not resurrect an expired task.
                if retain_clock_on_refusal:
                    conn.commit()
                else:
                    conn.rollback()
                raise
            except Exception:
                conn.rollback()
                raise
    except ModelBudgetUnavailable:
        raise
    except Exception:
        raise ModelBudgetUnavailable("budget_storage_unavailable") from None


def _row_budget(row: sqlite3.Row) -> TaskBudget:
    try:
        start = _clock_value(row["started_at"])
        deadline = row["deadline_at"]
        if deadline is not None:
            deadline = _clock_value(deadline)
            if deadline < start:
                raise ValueError
        ceiling = row["spend_ceiling_usd"]
        spend = (None if ceiling is None else
                 float(_decimal(ceiling, code="budget_policy_mismatch")))
        limits = WorkloadLimits(
            max_output_tokens_per_call=row["max_output_tokens_per_call"],
            deadline_seconds=None if deadline is None else deadline - start,
            max_estimated_spend_usd_per_task=spend,
        )
        return TaskBudget(
            row["user_id"], row["workload"], row["parent_request_id"], limits,
            row["scope_id"], start, deadline, spend,
        )
    except ModelBudgetUnavailable:
        raise
    except Exception:
        raise ModelBudgetUnavailable("budget_policy_mismatch") from None


def _check_clock(row: sqlite3.Row, now: float) -> None:
    try:
        if now < max(_clock_value(row["started_at"]), _clock_value(row["last_seen_at"])):
            raise ModelBudgetUnavailable("budget_clock_mismatch")
    except ModelBudgetUnavailable:
        raise
    except Exception:
        raise ModelBudgetUnavailable("budget_clock_mismatch") from None


def _validate_handle(budget: TaskBudget) -> None:
    if (not isinstance(budget, TaskBudget) or type(budget.limits) is not WorkloadLimits
            or budget.user_id != _owner()):
        raise ModelBudgetUnavailable("budget_scope_mismatch")
    if budget.scope_id is None and (
            budget.limits.deadline_seconds is not None
            or budget.limits.max_estimated_spend_usd_per_task is not None
            or budget.started_at is not None or budget.deadline_at is not None
            or budget.spend_ceiling_usd is not None):
        raise ModelBudgetUnavailable("budget_policy_mismatch")
    if (budget.scope_id is None or budget._ephemeral_seal) and (
            type(budget._ephemeral_seal) is not str
            or not _EPHEMERAL_SEAL.fullmatch(budget._ephemeral_seal)
            or not hmac.compare_digest(budget._ephemeral_seal, _ephemeral_budget_seal(budget))):
        raise ModelBudgetUnavailable("budget_policy_mismatch")
    if budget.scope_id is not None:
        _identifiers(budget.workload, budget.parent_request_id)


def _scope_row(conn: sqlite3.Connection, budget: TaskBudget, now: float) -> sqlite3.Row:
    row = conn.execute(
        "SELECT * FROM model_task_budgets WHERE user_id=? AND workload=? AND parent_request_id=?",
        (budget.user_id, budget.workload, budget.parent_request_id),
    ).fetchone()
    if (row is None or row["scope_id"] != budget.scope_id
            or row["started_at"] != budget.started_at):
        raise ModelBudgetUnavailable("budget_scope_mismatch")
    _row_budget(row)
    _check_clock(row, now)
    conn.execute(
        "UPDATE model_task_budgets SET last_seen_at=? WHERE scope_id=?", (now, budget.scope_id),
    )
    return row


def _existing_scope(owner: str, workload: str, parent_request_id: str) -> TaskBudget | None:
    try:
        conn = usage_ledger.existing_model_budget_connection()
        if conn is None:
            return None
        with closing(conn):
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM model_task_budgets WHERE user_id=? AND workload=? AND parent_request_id=?",
                (owner, workload, parent_request_id),
            ).fetchone()
            if row is None:
                return None
            budget = _row_budget(row)
            if (budget.limits.deadline_seconds is None
                    and budget.limits.max_estimated_spend_usd_per_task is None):
                raise ModelBudgetUnavailable("budget_policy_mismatch")
            return budget
    except ModelBudgetUnavailable:
        raise
    except Exception:
        raise ModelBudgetUnavailable("budget_storage_unavailable") from None


def begin_model_task_budget(
    workload: str, parent_request_id: str, limits: WorkloadLimits, *,
    started_at: float | None = None, now: float | None = None,
) -> TaskBudget:
    """Start/reopen one user's task budget; reused parents only tighten.

    ``started_at`` is the trusted host's execution-entry Unix timestamp for
    a new durable scope, including time waiting for this worker or storage.
    ``now`` independently supplies the current check clock for simulations;
    it never changes a persisted parent's start. New output-only or uncapped
    scopes never create storage or sample the budget clock.
    Existing storage is read without writes to find prior restrictions, so
    clearing configuration cannot reset a resumed parent's budget.
    The provider execution owner starts this at task creation, never while
    constructing or resolving a reusable model route.
    """
    if type(limits) is not WorkloadLimits:
        raise ModelBudgetUnavailable("budget_policy_mismatch")
    owner = _owner()
    if limits.deadline_seconds is None and limits.max_estimated_spend_usd_per_task is None:
        prior = _existing_scope(owner, workload, parent_request_id)
        if prior is None:
            return _issue_ephemeral_budget(owner, workload, parent_request_id, limits)
        limits = WorkloadLimits(
            _tightest(prior.limits.max_output_tokens_per_call, limits.max_output_tokens_per_call),
            prior.limits.deadline_seconds, prior.limits.max_estimated_spend_usd_per_task,
        )
    _identifiers(workload, parent_request_id)
    called_at = _clock_value(now)
    origin = called_at if started_at is None else _clock_value(started_at)
    if origin > called_at:
        raise ModelBudgetUnavailable("budget_clock_mismatch")
    with _transaction() as conn:
        # Take a fresh wall-clock sample after acquiring SQLite's write lock.
        # Concurrent requests can acquire that lock in a different order
        # from their initial timestamps; that is not a clock rollback.
        current = called_at if now is not None else _clock_value(None)
        if origin > current or current < called_at:
            raise ModelBudgetUnavailable("budget_clock_mismatch")
        row = conn.execute(
            "SELECT * FROM model_task_budgets WHERE user_id=? AND workload=? AND parent_request_id=?",
            (owner, workload, parent_request_id),
        ).fetchone()
        if row is None:
            start, scope_id = origin, uuid4().hex
            prior_deadline = prior_output = prior_ceiling = None
        else:
            _row_budget(row)
            _check_clock(row, current)
            start, scope_id = float(row["started_at"]), row["scope_id"]
            prior_deadline, prior_output = row["deadline_at"], row["max_output_tokens_per_call"]
            prior_ceiling = (None if row["spend_ceiling_usd"] is None else
                             _decimal(row["spend_ceiling_usd"], code="budget_policy_mismatch"))
        proposed_deadline = (None if limits.deadline_seconds is None else
                             _clock_value(start + limits.deadline_seconds))
        deadline = _tightest(prior_deadline, proposed_deadline)
        output = _tightest(prior_output, limits.max_output_tokens_per_call)
        proposed_ceiling = (None if limits.max_estimated_spend_usd_per_task is None else
                            _decimal(limits.max_estimated_spend_usd_per_task, code="budget_policy_mismatch"))
        ceiling = _tightest(prior_ceiling, proposed_ceiling)
        conn.execute(
            "INSERT INTO model_task_budgets "
            "(user_id,workload,parent_request_id,scope_id,started_at,last_seen_at,"
            "deadline_at,max_output_tokens_per_call,spend_ceiling_usd) VALUES (?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(user_id,workload,parent_request_id) DO UPDATE SET "
            "last_seen_at=excluded.last_seen_at,deadline_at=excluded.deadline_at,"
            "max_output_tokens_per_call=excluded.max_output_tokens_per_call,spend_ceiling_usd=excluded.spend_ceiling_usd",
            (owner, workload, parent_request_id, scope_id, start, current, deadline, output,
             None if ceiling is None else str(ceiling)),
        )
        row = conn.execute("SELECT * FROM model_task_budgets WHERE scope_id=?", (scope_id,)).fetchone()
        result = _row_budget(row)
    return result


def remaining_seconds(budget: TaskBudget, *, now: float | None = None) -> float:
    """Return current durable task time remaining, or infinity when unset."""
    _validate_handle(budget)
    if budget.scope_id is None:
        return math.inf
    with _transaction(retain_clock_on_refusal=True) as conn:
        current = _clock_value(now)
        row = _scope_row(conn, budget, current)
        deadline = row["deadline_at"]
        return math.inf if deadline is None else max(0.0, deadline - current)


def _reservation_cost(provider: str, model: str, input_tokens: int, output_tokens: int) -> Decimal:
    try:
        prices = usage_ledger.load_price_map()
        if not isinstance(prices, Mapping) or not isinstance(prices.get("models"), Mapping):
            raise ValueError
        row = prices["models"].get(f"{provider}/{model}")
        required = {"input_per_m", "output_per_m", "cache_write_mult", "cache_read_mult"}
        if not isinstance(row, Mapping) or not required.issubset(row):
            raise ValueError
        values = {}
        for key in required:
            value = row[key]
            if type(value) not in {int, float} or not math.isfinite(value) or value < 0:
                raise ValueError
            values[key] = Decimal(str(value))
        # Reserve the highest configured input/cache rate. The repository's
        # pricing contract also records Anthropic's one-hour write premium
        # as 2x: a five-minute 1.25x row alone is not its worst input estimate.
        anthropic = (provider == "anthropic" or model.startswith("anthropic/")
                     or model.startswith("claude-"))
        multiplier = max(Decimal(1), values["cache_write_mult"], values["cache_read_mult"],
                         Decimal(2) if anthropic else Decimal(1))
        with localcontext() as context:
            context.prec = 100
            return (Decimal(input_tokens) * values["input_per_m"] * multiplier
                    + Decimal(output_tokens) * values["output_per_m"]) / Decimal(1_000_000)
    except Exception:
        raise ModelBudgetUnavailable("budget_price_unavailable") from None


def reserve_model_call_budget(
    budget: TaskBudget, task_id: str, provider: str, model: str,
    route_name: str, billing_source: str, estimated_input_tokens: int,
    output_token_upper_bound: int, *, now: float | None = None,
) -> ModelCallReservation:
    """Atomically reserve a fresh outbound attempt; never refund uncertainty.

    The execution owner must independently verify text inputs, its output
    cap and absence of hidden adapter retries. Token/price reservations are
    estimates, not a promise about actual billing or subscription overage.
    """
    _validate_handle(budget)
    reservation_id = uuid4().hex
    if budget.scope_id is None:
        return ModelCallReservation(reservation_id, None)
    with _transaction(retain_clock_on_refusal=True) as conn:
        current = _clock_value(now)
        row = _scope_row(conn, budget, current)
        if row["deadline_at"] is not None and current >= row["deadline_at"]:
            raise ModelBudgetUnavailable("budget_deadline_exhausted")
        if row["spend_ceiling_usd"] is None:
            return ModelCallReservation(reservation_id, budget.scope_id)
        if (not isinstance(task_id, str) or not _OPAQUE_ID.fullmatch(task_id)
                or not isinstance(provider, str) or not _MODEL_ID.fullmatch(provider)
                or not isinstance(model, str) or not _MODEL_ID.fullmatch(model)):
            raise ModelBudgetUnavailable("budget_input_invalid")
        if ((route_name, billing_source) not in {
                ("direct_api", "provider_api"), ("saygm", "saygm_credit")}
                or provider in {"subscription", "local"}
                or (route_name == "saygm" and provider != "saygm")):
            raise ModelBudgetUnavailable("budget_unsupported_route")
        if (type(estimated_input_tokens) is not int
                or not 1 <= estimated_input_tokens <= _SQLITE_MAX_INT):
            raise ModelBudgetUnavailable("budget_input_invalid")
        if (type(output_token_upper_bound) is not int
                or not 1 <= output_token_upper_bound <= 32_000
                or (row["max_output_tokens_per_call"] is not None
                    and output_token_upper_bound > row["max_output_tokens_per_call"])):
            raise ModelBudgetUnavailable("budget_output_limit")
        cost = _reservation_cost(provider, model, estimated_input_tokens, output_token_upper_bound)
        prior_rows = conn.execute(
            "SELECT reserved_cost_usd FROM model_call_budget_reservations WHERE scope_id=?",
            (budget.scope_id,),
        ).fetchall()
        with localcontext() as context:
            context.prec = 100
            total = cost + sum(
                (_decimal(item[0], code="budget_policy_mismatch") for item in prior_rows), Decimal(0),
            )
        if total > _decimal(row["spend_ceiling_usd"], code="budget_policy_mismatch"):
            raise ModelBudgetUnavailable("budget_spend_exhausted")
        conn.execute(
            "INSERT INTO model_call_budget_reservations "
            "(reservation_id,scope_id,task_id,provider,model,route_name,billing_source,"
            "estimated_input_tokens,output_token_upper_bound,reserved_cost_usd,created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (reservation_id, budget.scope_id, task_id, provider, model, route_name, billing_source,
             estimated_input_tokens, output_token_upper_bound, str(cost), current),
        )
        return ModelCallReservation(reservation_id, budget.scope_id, float(cost), float(total))
