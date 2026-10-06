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
_SCOPE_ID = re.compile(r"[0-9a-f]{32}\Z")
_EPHEMERAL_BUDGET_KEY = secrets.token_bytes(32)
_MAX_BUDGET_SCOPES = 64


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


@dataclass(frozen=True)
class ChildTaskBudget:
    """Host-issued sponsorship; public fields and JSON cannot mint it."""

    owner: TaskBudget
    child: TaskBudget
    _seal: str = field(default="", repr=False)
    _ancestors: tuple[TaskBudget, ...] = field(default=(), repr=False)

    @property
    def limits(self) -> WorkloadLimits:
        path = _budget_path(self)
        def minimum(name):
            return min((getattr(b.limits, name) for b in path
                        if getattr(b.limits, name) is not None), default=None)
        return WorkloadLimits(minimum("max_output_tokens_per_call"), minimum("deadline_seconds"),
                              minimum("max_estimated_spend_usd_per_task"))

    @property
    def workload(self) -> str:
        return self.child.workload

    @property
    def parent_request_id(self) -> str:
        return self.child.parent_request_id

    @property
    def user_id(self) -> str:
        return self.child.user_id


def _child_seal(binding: ChildTaskBudget) -> str:
    try:
        parts = []
        for budget in (binding.owner, *binding._ancestors, binding.child):
            parts.append((budget.user_id, budget.workload, budget.parent_request_id,
                          budget.limits.as_metadata(), budget.scope_id, budget.started_at,
                          budget.deadline_at, budget.spend_ceiling_usd, budget._ephemeral_seal))
        payload = json.dumps(["model-child-budget-v1", parts], sort_keys=True,
                             separators=(",", ":"), allow_nan=False)
        return hmac.new(_EPHEMERAL_BUDGET_KEY, payload.encode(), hashlib.sha256).hexdigest()
    except Exception:
        raise ModelBudgetUnavailable("budget_policy_mismatch") from None


def _issue_child(owner: TaskBudget, child: TaskBudget, *, ancestors: tuple[TaskBudget, ...] = ()) -> ChildTaskBudget:
    value = ChildTaskBudget(owner, child, _ancestors=ancestors)
    return replace(value, _seal=_child_seal(value))


def _budget_path(binding: ChildTaskBudget) -> tuple[TaskBudget, ...]:
    if (not binding._ancestors and binding.owner.workload == binding.child.workload
            and binding.owner.scope_id == binding.child.scope_id):
        return (binding.child,)
    return (binding.owner, *binding._ancestors, binding.child)


def _validate_child(binding: ChildTaskBudget) -> None:
    if type(binding) is not ChildTaskBudget:
        raise ModelBudgetUnavailable("budget_scope_mismatch")
    if type(binding._ancestors) is not tuple or len(binding._ancestors) > _MAX_BUDGET_SCOPES - 2:
        raise ModelBudgetUnavailable("budget_scope_mismatch")
    for budget in (binding.owner, *binding._ancestors, binding.child):
        _validate_handle(budget)
        if (budget.user_id != binding.owner.user_id
                or budget.parent_request_id != binding.owner.parent_request_id):
            raise ModelBudgetUnavailable("budget_scope_mismatch")
    path = _budget_path(binding)
    if (len({budget.workload for budget in path}) != len(path)
            or len({budget.scope_id for budget in path if budget.scope_id is not None})
            != sum(budget.scope_id is not None for budget in path)
            or any(budget.scope_id is None for budget in path) != all(budget.scope_id is None for budget in path)):
        raise ModelBudgetUnavailable("budget_scope_mismatch")
    if (type(binding._seal) is not str or not _EPHEMERAL_SEAL.fullmatch(binding._seal)
            or not hmac.compare_digest(binding._seal, _child_seal(binding))):
        raise ModelBudgetUnavailable("budget_policy_mismatch")


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


def _scope_row(conn: sqlite3.Connection, budget: TaskBudget, now: float, *, observe_clock: bool = True) -> sqlite3.Row:
    row = conn.execute(
        "SELECT * FROM model_task_budgets WHERE user_id=? AND workload=? AND parent_request_id=?",
        (budget.user_id, budget.workload, budget.parent_request_id),
    ).fetchone()
    if (row is None or row["scope_id"] != budget.scope_id
            or row["started_at"] != budget.started_at):
        raise ModelBudgetUnavailable("budget_scope_mismatch")
    _row_budget(row)
    _check_clock(row, now)
    if observe_clock:
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
            _has_child_schema(conn)
            row = conn.execute(
                "SELECT * FROM model_task_budgets WHERE user_id=? AND workload=? AND parent_request_id=?",
                (owner, workload, parent_request_id),
            ).fetchone()
            if row is None:
                return None
            budget = _row_budget(row)
            if (budget.limits == WorkloadLimits()
                    and not _scope_has_link(conn, budget.scope_id)):
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
        prior = _existing_scope(budget.user_id, budget.workload, budget.parent_request_id)
        if prior is not None:
            return remaining_seconds(prior, now=now)
        return math.inf
    with _transaction(retain_clock_on_refusal=True) as conn:
        current = _clock_value(now)
        row = _scope_row(conn, budget, current)
        if _parent_link(conn, budget.scope_id) is not None:
            raise ModelBudgetUnavailable("budget_policy_mismatch")
        deadline = row["deadline_at"]
        return math.inf if deadline is None else max(0.0, deadline - current)


def _has_table(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def _has_child_schema(conn: sqlite3.Connection) -> bool:
    links = _has_table(conn, "model_task_budget_links")
    memberships = _has_table(conn, "model_call_budget_reservation_scopes")
    if links != memberships:
        raise ModelBudgetUnavailable("budget_storage_unavailable")
    return links


def _scope_has_link(conn: sqlite3.Connection, scope: str) -> bool:
    return (_has_child_schema(conn) and conn.execute(
        "SELECT 1 FROM model_task_budget_links WHERE child_scope_id=? OR parent_scope_id=?",
        (scope, scope),
    ).fetchone() is not None)


def _parent_link(conn: sqlite3.Connection, scope: str) -> str | None:
    if not _has_child_schema(conn):
        return None
    row = conn.execute("SELECT parent_scope_id FROM model_task_budget_links WHERE child_scope_id=?", (scope,)).fetchone()
    return None if row is None else row[0]


def _read_budget_chain(conn: sqlite3.Connection, leaf: sqlite3.Row) -> tuple[TaskBudget, ...]:
    """Follow immediate sponsors; every row belongs to this tenant/request."""
    reverse = []
    seen = set()
    row = leaf
    while True:
        if (row is None or row["scope_id"] in seen or len(reverse) >= _MAX_BUDGET_SCOPES
                or row["user_id"] != _owner() or row["parent_request_id"] != leaf["parent_request_id"]):
            raise ModelBudgetUnavailable("budget_scope_mismatch")
        seen.add(row["scope_id"])
        reverse.append(_row_budget(row))
        parent = _parent_link(conn, row["scope_id"])
        if parent is None:
            break
        row = conn.execute("SELECT * FROM model_task_budgets WHERE scope_id=?", (parent,)).fetchone()
    path = tuple(reversed(reverse))
    if len({budget.workload for budget in path}) != len(path):
        raise ModelBudgetUnavailable("budget_scope_mismatch")
    return path


def _linked_binding(workload: str, parent: str) -> ChildTaskBudget | None:
    """Read persisted sponsorship without creating/updating an ordinary store."""
    try:
        conn = usage_ledger.existing_model_budget_connection()
        if conn is None:
            return None
        with closing(conn):
            conn.row_factory = sqlite3.Row
            if not _has_child_schema(conn):
                return None
            child = conn.execute("SELECT * FROM model_task_budgets WHERE user_id=? AND workload=? AND parent_request_id=?",
                                 (_owner(), workload, parent)).fetchone()
            if child is None:
                return None
            if _parent_link(conn, child["scope_id"]) is None:
                return None
            path = _read_budget_chain(conn, child)
            return _issue_child(path[0], path[-1], ancestors=path[1:-1])
    except ModelBudgetUnavailable:
        raise
    except Exception:
        raise ModelBudgetUnavailable("budget_storage_unavailable") from None


def validate_model_child_budget(binding: ChildTaskBudget) -> ChildTaskBudget:
    """Authenticate the complete stored path without admission or clock writes.

    Returned handles use current durable policy, including expired bounds;
    status may remain readable. Remaining-time and reservation helpers still
    enforce expiry before any model/client operation.
    """
    _validate_child(binding)
    expected = _budget_path(binding)
    if binding.child.scope_id is None:
        if any(_existing_scope(b.user_id, b.workload, b.parent_request_id) is not None for b in expected):
            raise ModelBudgetUnavailable("budget_policy_mismatch")
        return binding
    try:
        conn = usage_ledger.existing_model_budget_connection()
        if conn is None:
            raise ModelBudgetUnavailable("budget_scope_mismatch")
        with closing(conn):
            conn.row_factory = sqlite3.Row
            _has_child_schema(conn)
            leaf = conn.execute("SELECT * FROM model_task_budgets WHERE scope_id=?",
                                (binding.child.scope_id,)).fetchone()
            if leaf is None:
                raise ModelBudgetUnavailable("budget_scope_mismatch")
            path = _read_budget_chain(conn, leaf)
            _validate_stored_path(path, expected)
            return _issue_child(path[0], path[-1], ancestors=path[1:-1])
    except ModelBudgetUnavailable:
        raise
    except Exception:
        raise ModelBudgetUnavailable("budget_storage_unavailable") from None


def _validate_stored_path(path, expected):
    if ([(b.scope_id, b.workload, b.parent_request_id, b.started_at) for b in path]
            != [(b.scope_id, b.workload, b.parent_request_id, b.started_at) for b in expected]):
        raise ModelBudgetUnavailable("budget_scope_mismatch")
    for current, prior in zip(path, expected):
        for actual, captured in (
            (current.limits.max_output_tokens_per_call, prior.limits.max_output_tokens_per_call),
            (current.spend_ceiling_usd, prior.spend_ceiling_usd),
            (current.deadline_at, prior.deadline_at),
        ):
            if captured is not None and (actual is None or actual > captured):
                raise ModelBudgetUnavailable("budget_policy_mismatch")


def _write_scope(conn, workload, parent, limits, current, origin, *, absolute_deadline=None):
    row = conn.execute("SELECT * FROM model_task_budgets WHERE user_id=? AND workload=? AND parent_request_id=?",
                       (_owner(), workload, parent)).fetchone()
    if row is None:
        start, scope = origin, uuid4().hex
        prior_output = prior_deadline = prior_spend = None
    else:
        _row_budget(row)
        _check_clock(row, current)
        start, scope = row["started_at"], row["scope_id"]
        prior_output, prior_deadline, prior_spend = row["max_output_tokens_per_call"], row["deadline_at"], row["spend_ceiling_usd"]
    deadline = _tightest(prior_deadline, absolute_deadline)
    if limits.deadline_seconds is not None:
        deadline = _tightest(deadline, _clock_value(start + limits.deadline_seconds))
    output = _tightest(prior_output, limits.max_output_tokens_per_call)
    ceiling = _tightest(None if prior_spend is None else _decimal(prior_spend, code="budget_policy_mismatch"),
                       None if limits.max_estimated_spend_usd_per_task is None else
                       _decimal(limits.max_estimated_spend_usd_per_task, code="budget_policy_mismatch"))
    conn.execute("INSERT INTO model_task_budgets "
        "(user_id,workload,parent_request_id,scope_id,started_at,last_seen_at,deadline_at,max_output_tokens_per_call,spend_ceiling_usd) "
        "VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(user_id,workload,parent_request_id) DO UPDATE SET "
        "last_seen_at=excluded.last_seen_at,deadline_at=excluded.deadline_at,max_output_tokens_per_call=excluded.max_output_tokens_per_call,"
        "spend_ceiling_usd=excluded.spend_ceiling_usd",
        (_owner(), workload, parent, scope, start, current, deadline, output, None if ceiling is None else str(ceiling)))
    return _row_budget(conn.execute("SELECT * FROM model_task_budgets WHERE scope_id=?", (scope,)).fetchone())


def begin_model_child_budget(owner: TaskBudget, workload: str, limits: WorkloadLimits, *,
                             started_at: float | None = None, now: float | None = None) -> ChildTaskBudget:
    """Mint one direct, same-tenant/exact-parent child; resumed bounds only tighten.

    A sponsored output-only policy persists its owner/child authority. Only a
    genuinely all-null fresh binding avoids storage and clock sampling.
    """
    return _begin_model_child_budget(owner, workload, limits, started_at=started_at,
                                     now=now, persist=False)


def bind_model_task_budget_for_transport(
    owner: TaskBudget, child_workload: str, child_limits: WorkloadLimits, *,
    started_at: float, now: float | None = None,
) -> ChildTaskBudget:
    """Publish actual host authority before a cross-process child operation.

    This opt-in persists even an all-null owner/child pair; ordinary task and
    child helpers keep their no-storage defaults. The caller supplies its
    authentic local owner, locally resolved child limits and trusted host
    entry time. Only the resulting owner/child scope IDs may travel as
    locators: serialized ceilings, deadlines or handles are never authority.
    Transport roles require a distinct direct child, never a self/nested link.
    """
    if type(owner) is not TaskBudget:
        raise ModelBudgetUnavailable("budget_scope_mismatch")
    _validate_handle(owner)
    if child_workload == owner.workload:
        raise ModelBudgetUnavailable("budget_scope_mismatch")
    if started_at is None:
        raise ModelBudgetUnavailable("budget_clock_unavailable")
    origin = _clock_value(started_at)
    return _begin_model_child_budget(owner, child_workload, child_limits,
                                     started_at=origin, now=now, persist=True)


def recover_model_task_budget_for_transport(
    workload: str, parent_request_id: str, *, scope_id: str,
) -> TaskBudget:
    """Read one exact durable root in the authenticated receiving process.

    Workload/parent come from the verified host caller contract. A scope ID
    only locates that existing row; missing/foreign/replaced/nested authority
    refuses without creating storage or sampling a new execution clock.
    Resolve the expected child through resolve_model_child_budget afterwards
    and compare both recovered scope IDs to the accepted transport locators.
    """
    _identifiers(workload, parent_request_id)
    if type(scope_id) is not str or not _SCOPE_ID.fullmatch(scope_id):
        raise ModelBudgetUnavailable("budget_scope_mismatch")
    owner = _owner()
    try:
        conn = usage_ledger.existing_model_budget_connection()
        if conn is None:
            raise ModelBudgetUnavailable("budget_scope_mismatch")
        with closing(conn):
            conn.row_factory = sqlite3.Row
            _has_child_schema(conn)
            row = conn.execute(
                "SELECT * FROM model_task_budgets WHERE user_id=? AND workload=? AND parent_request_id=?",
                (owner, workload, parent_request_id),
            ).fetchone()
            if row is None or row["scope_id"] != scope_id or _parent_link(conn, scope_id) is not None:
                raise ModelBudgetUnavailable("budget_scope_mismatch")
            budget = _row_budget(row)
            if budget.limits == WorkloadLimits() and not _scope_has_link(conn, scope_id):
                raise ModelBudgetUnavailable("budget_policy_mismatch")
            return budget
    except ModelBudgetUnavailable:
        raise
    except Exception:
        raise ModelBudgetUnavailable("budget_storage_unavailable") from None


def _begin_model_child_budget(owner: TaskBudget, workload: str, limits: WorkloadLimits, *,
                              started_at: float | None, now: float | None,
                              persist: bool) -> ChildTaskBudget:
    _validate_handle(owner)
    if type(limits) is not WorkloadLimits:
        raise ModelBudgetUnavailable("budget_policy_mismatch")
    _identifiers(workload, owner.parent_request_id)
    prior_root = _existing_scope(owner.user_id, owner.workload, owner.parent_request_id)
    prior_child = _existing_scope(owner.user_id, workload, owner.parent_request_id)
    if (not persist and owner.scope_id is None and owner.limits == WorkloadLimits() and limits == WorkloadLimits()
            and prior_root is None and prior_child is None):
        return _issue_child(owner, _issue_ephemeral_budget(owner.user_id, workload, owner.parent_request_id, limits))
    with _transaction() as conn:
        current = _clock_value(now)
        origin = current if started_at is None else _clock_value(started_at)
        if origin > current:
            raise ModelBudgetUnavailable("budget_clock_mismatch")
        if owner.scope_id is not None:
            _scope_row(conn, owner, current)
        root = _write_scope(conn, owner.workload, owner.parent_request_id, owner.limits,
                            current, owner.started_at if owner.started_at is not None else origin)
        if _parent_link(conn, root.scope_id) is not None:
            raise ModelBudgetUnavailable("budget_scope_mismatch")
        if root.deadline_at is not None and root.deadline_at <= current:
            # Refusing an expired owner must still remember the forward
            # clock. Discard all proposed policy/link changes first, then
            # commit only the authenticated existing owner's observation.
            conn.rollback()
            _scope_row(conn, root, current)
            conn.commit()
            raise ModelBudgetUnavailable("budget_deadline_exhausted")
        if workload == root.workload:
            child = _write_scope(conn, workload, root.parent_request_id, limits, current, origin)
            return _issue_child(child, child)
        inherited = WorkloadLimits(
            _tightest(root.limits.max_output_tokens_per_call, limits.max_output_tokens_per_call),
            limits.deadline_seconds,
            _tightest(root.limits.max_estimated_spend_usd_per_task, limits.max_estimated_spend_usd_per_task),
        )
        child = _write_scope(conn, workload, root.parent_request_id, inherited, current, origin,
                             absolute_deadline=root.deadline_at)
        linked = _parent_link(conn, child.scope_id)
        if linked is not None and linked != root.scope_id:
            raise ModelBudgetUnavailable("budget_scope_mismatch")
        if linked is None and conn.execute("SELECT 1 FROM model_task_budget_links WHERE parent_scope_id=?", (child.scope_id,)).fetchone():
            raise ModelBudgetUnavailable("budget_scope_mismatch")
        conn.execute("INSERT OR IGNORE INTO model_task_budget_links(child_scope_id,parent_scope_id,created_at) VALUES (?,?,?)",
                     (child.scope_id, root.scope_id, current))
        # Existing standalone reservations cannot disappear when sponsorship
        # is first attached to a same-parent child.
        conn.execute("INSERT OR IGNORE INTO model_call_budget_reservation_scopes(reservation_id,scope_id) "
                     "SELECT reservation_id,? FROM model_call_budget_reservations WHERE scope_id=?",
                     (root.scope_id, child.scope_id))
        return _issue_child(root, child)


def _merged_limits(first: WorkloadLimits, second: WorkloadLimits) -> WorkloadLimits:
    return WorkloadLimits(*(_tightest(a, b) for a, b in zip(
        tuple(first.as_metadata().values()), tuple(second.as_metadata().values()))))


def _refresh_model_binding(binding: ChildTaskBudget, limits: WorkloadLimits, *, started_at=None, now=None):
    binding = validate_model_child_budget(binding)
    limits = _merged_limits(limits, binding.child.limits)
    if not binding._ancestors:
        return begin_model_child_budget(binding.owner, binding.workload, limits,
                                        started_at=started_at, now=now)
    parent = _issue_child(binding.owner, binding._ancestors[-1], ancestors=binding._ancestors[:-1])
    return begin_model_descendant_budget(parent, binding.workload, limits,
                                         started_at=started_at, now=now)


def _materialize_model_binding(binding: ChildTaskBudget, *, started_at=None, now=None):
    if not binding._ancestors:
        return _begin_model_child_budget(binding.owner, binding.workload, binding.child.limits,
            started_at=started_at, now=now, persist=True)
    parent = _issue_child(binding.owner, binding._ancestors[-1], ancestors=binding._ancestors[:-1])
    parent = _materialize_model_binding(parent, started_at=started_at, now=now)
    return begin_model_descendant_budget(parent, binding.workload, binding.child.limits,
                                         started_at=started_at, now=now)


def begin_model_descendant_budget(parent: ChildTaskBudget, workload: str, limits: WorkloadLimits, *,
                                  started_at: float | None = None, now: float | None = None) -> ChildTaskBudget:
    """Fund a leaf from an authentic coordinator and every retained ancestor.

    The original root remains .owner. Same-workload calls refine/coalesce the
    actual coordinator. No bare TaskBudget or JSON can create a descendant,
    and an existing leaf with a different immediate sponsor cannot reparent.
    """
    _validate_child(parent)
    if type(limits) is not WorkloadLimits:
        raise ModelBudgetUnavailable("budget_policy_mismatch")
    _identifiers(workload, parent.parent_request_id)
    if workload == parent.workload:
        return _refresh_model_binding(parent, limits, started_at=started_at, now=now)
    if workload in {budget.workload for budget in _budget_path(parent)}:
        raise ModelBudgetUnavailable("budget_scope_mismatch")
    if len(_budget_path(parent)) >= _MAX_BUDGET_SCOPES:
        raise ModelBudgetUnavailable("budget_scope_mismatch")
    parent = validate_model_child_budget(parent)
    if (parent.child.scope_id is None and limits == WorkloadLimits()
            and all(b.limits == WorkloadLimits() for b in _budget_path(parent))
            and _existing_scope(parent.user_id, workload, parent.parent_request_id) is None):
        return _issue_child(parent.owner, _issue_ephemeral_budget(parent.user_id, workload,
            parent.parent_request_id, limits), ancestors=_budget_path(parent)[1:])
    parent = _refresh_model_binding(parent, WorkloadLimits(), started_at=started_at, now=now)
    if parent.child.scope_id is None:
        # Persist the authenticated coordinator only for this constrained
        # descendant; no invented cap is used to force storage.
        parent = _materialize_model_binding(parent, started_at=started_at, now=now)
    with _transaction() as conn:
        current = _clock_value(now)
        origin = current if started_at is None else _clock_value(started_at)
        if origin > current:
            raise ModelBudgetUnavailable("budget_clock_mismatch")
        rows = _binding_rows(conn, parent, current)
        if any(row["deadline_at"] is not None and row["deadline_at"] <= current for row in rows):
            conn.commit()  # only validated ancestor clock observations exist
            raise ModelBudgetUnavailable("budget_deadline_exhausted")
        existing = conn.execute("SELECT * FROM model_task_budgets WHERE user_id=? AND workload=? AND parent_request_id=?",
                                (_owner(), workload, parent.parent_request_id)).fetchone()
        if existing is not None:
            linked = _parent_link(conn, existing["scope_id"])
            if (linked is not None and linked != parent.child.scope_id) or (linked is None and conn.execute(
                    "SELECT 1 FROM model_task_budget_links WHERE parent_scope_id=?", (existing["scope_id"],)).fetchone()):
                raise ModelBudgetUnavailable("budget_scope_mismatch")
        path = tuple(_row_budget(row) for row in rows)
        inherited = limits
        for budget in path:
            inherited = WorkloadLimits(
                _tightest(inherited.max_output_tokens_per_call, budget.limits.max_output_tokens_per_call),
                inherited.deadline_seconds,
                _tightest(inherited.max_estimated_spend_usd_per_task, budget.limits.max_estimated_spend_usd_per_task))
        expiry = min((b.deadline_at for b in path if b.deadline_at is not None), default=None)
        child = _write_scope(conn, workload, parent.parent_request_id, inherited, current, origin,
                             absolute_deadline=expiry)
        conn.execute("INSERT OR IGNORE INTO model_task_budget_links(child_scope_id,parent_scope_id,created_at) VALUES (?,?,?)",
                     (child.scope_id, path[-1].scope_id, current))
        for budget in path:
            conn.execute("INSERT OR IGNORE INTO model_call_budget_reservation_scopes(reservation_id,scope_id) "
                "SELECT r.reservation_id,? FROM model_call_budget_reservations r WHERE r.scope_id=? OR EXISTS "
                "(SELECT 1 FROM model_call_budget_reservation_scopes s WHERE s.reservation_id=r.reservation_id AND s.scope_id=?)",
                (budget.scope_id, child.scope_id, child.scope_id))
        return _issue_child(path[0], child, ancestors=path[1:])


def resolve_model_child_budget(workload: str, parent_request_id: str, limits: WorkloadLimits, *,
                               child_budget: ChildTaskBudget | None = None,
                               started_at: float | None = None, now: float | None = None) -> ChildTaskBudget | None:
    """Validate/reopen a supplied binding, or recover a recorded sponsor.

    Missing serialized metadata is never permission to clear an existing
    parent. This function returns None only for an unlinked ordinary scope.
    """
    _identifiers(workload, parent_request_id)
    if type(limits) is not WorkloadLimits:
        raise ModelBudgetUnavailable("budget_policy_mismatch")
    binding = _linked_binding(workload, parent_request_id)
    if child_budget is not None:
        _validate_child(child_budget)
        if child_budget.workload != workload or child_budget.parent_request_id != parent_request_id:
            raise ModelBudgetUnavailable("budget_scope_mismatch")
        if binding is not None:
            _validate_stored_path(_budget_path(binding), _budget_path(child_budget))
        binding = binding or child_budget
        limits = _merged_limits(limits, child_budget.child.limits)
    if binding is None:
        return None
    return _refresh_model_binding(binding, limits, started_at=started_at, now=now)


def _binding_rows(conn, binding, current, *, observe_clock=True):
    expected = _budget_path(binding)
    rows = tuple(_scope_row(conn, budget, current, observe_clock=observe_clock) for budget in expected)
    _validate_stored_path(_read_budget_chain(conn, rows[-1]), expected)
    return rows


def remaining_child_seconds(binding: ChildTaskBudget, *, now: float | None = None) -> float:
    _validate_child(binding)
    if binding.child.scope_id is None:
        if any(_existing_scope(b.user_id, b.workload, b.parent_request_id) is not None for b in _budget_path(binding)):
            raise ModelBudgetUnavailable("budget_policy_mismatch")
        return math.inf
    with _transaction(retain_clock_on_refusal=True) as conn:
        current = _clock_value(now)
        rows = _binding_rows(conn, binding, current)
        values = [row["deadline_at"] - current for row in rows if row["deadline_at"] is not None]
        return max(0.0, min(values)) if values else math.inf


def _reserved_total(conn, scope):
    rows = conn.execute("SELECT r.reserved_cost_usd FROM model_call_budget_reservations r WHERE r.scope_id=? "
        "OR EXISTS (SELECT 1 FROM model_call_budget_reservation_scopes s WHERE s.reservation_id=r.reservation_id AND s.scope_id=?)",
        (scope, scope)).fetchall()
    return sum((_decimal(row[0], code="budget_policy_mismatch") for row in rows), Decimal(0))


def _call_budget_ephemeral(budget):
    if type(budget) is ChildTaskBudget:
        _validate_child(budget)
        if budget.child.scope_id is None:
            remaining_child_seconds(budget)
            return True
    else:
        _validate_handle(budget)
        if budget.scope_id is None:
            if _existing_scope(budget.user_id, budget.workload, budget.parent_request_id) is not None:
                raise ModelBudgetUnavailable("budget_policy_mismatch")
            return True
    return False


def _call_budget_rows(conn, budget, current, *, observe_clock=True):
    if type(budget) is ChildTaskBudget:
        return _binding_rows(conn, budget, current, observe_clock=observe_clock)
    row = _scope_row(conn, budget, current, observe_clock=observe_clock)
    if _parent_link(conn, budget.scope_id) is not None:
        raise ModelBudgetUnavailable("budget_policy_mismatch")
    return (row,)


def _call_budget_admission(conn, budget, funding, current, task_id, provider, model,
                           route_name, billing_source, estimated_input_tokens, output_token_upper_bound):
    """The same authority checks serve dry reads and atomic reservation."""
    rows = {row["scope_id"]: row for row in funding}
    if any(row["deadline_at"] is not None and current >= row["deadline_at"] for row in funding):
        raise ModelBudgetUnavailable("budget_deadline_exhausted")
    if type(budget) is ChildTaskBudget:
        binding = budget
        current_output = min((row["max_output_tokens_per_call"] for row in funding
                              if row["max_output_tokens_per_call"] is not None), default=None)
        current_spend = min((
            None if row["spend_ceiling_usd"] is None else
            _decimal(row["spend_ceiling_usd"], code="budget_policy_mismatch") for row in funding
            if row["spend_ceiling_usd"] is not None), default=None)
        # A newly stricter DB policy must be reopened before request-output
        # and retry proofs are made; a guessed estimate of 1 is no authority.
        if ((current_output is not None and (binding.limits.max_output_tokens_per_call is None
                                            or current_output < binding.limits.max_output_tokens_per_call))
                or (current_spend is not None and (binding.limits.max_estimated_spend_usd_per_task is None
                    or current_spend < Decimal(str(binding.limits.max_estimated_spend_usd_per_task))))
                or any(row["deadline_at"] is not None and (binding.child.deadline_at is None
                                                           or row["deadline_at"] < binding.child.deadline_at)
                       for row in rows.values())):
            raise ModelBudgetUnavailable("budget_policy_mismatch")
        if type(output_token_upper_bound) is not int or not 1 <= output_token_upper_bound <= 32_000 or (
                current_output is not None and output_token_upper_bound > current_output):
            raise ModelBudgetUnavailable("budget_output_limit")
        if current_spend is None:
            return None, {}
        if (not isinstance(task_id, str) or not _OPAQUE_ID.fullmatch(task_id)
                or not isinstance(provider, str) or not _MODEL_ID.fullmatch(provider)
                or not isinstance(model, str) or not _MODEL_ID.fullmatch(model)
                or type(estimated_input_tokens) is not int or not 1 <= estimated_input_tokens <= _SQLITE_MAX_INT):
            raise ModelBudgetUnavailable("budget_input_invalid")
        if ((route_name, billing_source) not in {("direct_api", "provider_api"), ("saygm", "saygm_credit")}
                or provider in {"subscription", "local"} or (route_name == "saygm" and provider != "saygm")):
            raise ModelBudgetUnavailable("budget_unsupported_route")
    else:
        row = funding[0]
        if row["spend_ceiling_usd"] is None:
            return None, {}
        if (not isinstance(task_id, str) or not _OPAQUE_ID.fullmatch(task_id)
                or not isinstance(provider, str) or not _MODEL_ID.fullmatch(provider)
                or not isinstance(model, str) or not _MODEL_ID.fullmatch(model)):
            raise ModelBudgetUnavailable("budget_input_invalid")
        if ((route_name, billing_source) not in {("direct_api", "provider_api"), ("saygm", "saygm_credit")}
                or provider in {"subscription", "local"} or (route_name == "saygm" and provider != "saygm")):
            raise ModelBudgetUnavailable("budget_unsupported_route")
        if type(estimated_input_tokens) is not int or not 1 <= estimated_input_tokens <= _SQLITE_MAX_INT:
            raise ModelBudgetUnavailable("budget_input_invalid")
        if (type(output_token_upper_bound) is not int or not 1 <= output_token_upper_bound <= 32_000
                or (row["max_output_tokens_per_call"] is not None and output_token_upper_bound > row["max_output_tokens_per_call"])):
            raise ModelBudgetUnavailable("budget_output_limit")
    cost = _reservation_cost(provider, model, estimated_input_tokens, output_token_upper_bound)
    with localcontext() as context:
        context.prec = 100
        totals = {scope: _reserved_total(conn, scope) + cost for scope in rows}
    if any(row["spend_ceiling_usd"] is not None and totals[scope] > _decimal(row["spend_ceiling_usd"], code="budget_policy_mismatch")
           for scope, row in rows.items()):
        raise ModelBudgetUnavailable("budget_spend_exhausted")
    return cost, totals


def check_model_call_budget(budget: TaskBudget | ChildTaskBudget, task_id: str, provider: str, model: str,
                             route_name: str, billing_source: str, estimated_input_tokens: int,
                             output_token_upper_bound: int, *, now: float | None = None) -> None:
    """Read-only preflight; it grants no admission and never creates a UUID.

    A retry-free client must still be proved, followed by atomic reservation
    before outbound execution. Concurrent admission or price changes can make
    that later reservation refuse. No schema, clock or accounting is written.
    """
    if _call_budget_ephemeral(budget):
        return
    try:
        conn = usage_ledger.existing_model_budget_connection()
        if conn is None:
            raise ModelBudgetUnavailable("budget_scope_mismatch")
        with closing(conn):
            conn.row_factory = sqlite3.Row
            _has_child_schema(conn)
            conn.execute("BEGIN")
            # Acquire a coherent read snapshot before sampling the clock;
            # a blocked SQLite read cannot make a stale preflight time pass.
            conn.execute("SELECT scope_id FROM model_task_budgets LIMIT 1").fetchone()
            current = _clock_value(now)
            funding = _call_budget_rows(conn, budget, current, observe_clock=False)
            _call_budget_admission(conn, budget, funding, current, task_id, provider, model,
                route_name, billing_source, estimated_input_tokens, output_token_upper_bound)
    except ModelBudgetUnavailable:
        raise
    except Exception:
        raise ModelBudgetUnavailable("budget_storage_unavailable") from None


def _reserve_call_budget(budget, task_id, provider, model, route_name, billing_source,
                         estimated_input_tokens, output_token_upper_bound, *, now=None):
    ephemeral = _call_budget_ephemeral(budget)
    reservation = uuid4().hex
    if ephemeral:
        return ModelCallReservation(reservation, None)
    with _transaction(retain_clock_on_refusal=True) as conn:
        current = _clock_value(now)
        funding = _call_budget_rows(conn, budget, current)
        cost, totals = _call_budget_admission(conn, budget, funding, current, task_id, provider, model,
            route_name, billing_source, estimated_input_tokens, output_token_upper_bound)
        root = funding[0]
        if cost is None:
            return ModelCallReservation(reservation, root["scope_id"])
        conn.execute("INSERT INTO model_call_budget_reservations "
            "(reservation_id,scope_id,task_id,provider,model,route_name,billing_source,estimated_input_tokens,output_token_upper_bound,reserved_cost_usd,created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)", (reservation, root["scope_id"], task_id, provider, model, route_name,
                                              billing_source, estimated_input_tokens, output_token_upper_bound, str(cost), current))
        if type(budget) is ChildTaskBudget:
            for row in funding:
                conn.execute("INSERT INTO model_call_budget_reservation_scopes(reservation_id,scope_id) VALUES (?,?)",
                             (reservation, row["scope_id"]))
        return ModelCallReservation(reservation, root["scope_id"], float(cost), float(totals[root["scope_id"]]))


def reserve_model_child_call_budget(binding: ChildTaskBudget, task_id: str, provider: str, model: str,
                                    route_name: str, billing_source: str, estimated_input_tokens: int,
                                    output_token_upper_bound: int, *, now: float | None = None) -> ModelCallReservation:
    """Atomically reserve one attempt against every inherited funding scope."""
    if type(binding) is not ChildTaskBudget:
        raise ModelBudgetUnavailable("budget_scope_mismatch")
    return _reserve_call_budget(binding, task_id, provider, model, route_name, billing_source,
                                estimated_input_tokens, output_token_upper_bound, now=now)


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
    return _reserve_call_budget(budget, task_id, provider, model, route_name, billing_source,
                                estimated_input_tokens, output_token_upper_bound, now=now)
