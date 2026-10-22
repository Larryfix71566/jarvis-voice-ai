"""Offline WS24 transition proposals; no persistence, dispatch or approval authority.

The host supplies verified authority/receipts and a single evaluation time. It
must atomically compare the returned expected_version before storing a proposal
and coordinate with the existing domain action ledger. These values are metadata,
not credentials. A proposal alone provides neither a lock nor permission to run.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
import re


class Status(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    BLOCKED = "blocked"
    CANCELLING = "cancelling"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"


class AttemptState(str, Enum):
    RUNNING = "running"
    INTERRUPTED = "interrupted"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    STOPPED = "stopped"


class Delivery(str, Enum):
    NONE = "none"
    PENDING = "pending"
    UNKNOWN = "unknown"
    ACKNOWLEDGED = "acknowledged"


class Kind(str, Enum):
    START = "start"
    INTERRUPT = "interrupt"
    RECONCILE = "reconcile"
    CANCEL = "cancel"
    TIMEOUT = "timeout"
    CONFIRM_STOP = "confirm_stop"
    BIND_NOTICE = "bind_notice"
    DELIVERY_UNKNOWN = "delivery_unknown"
    ACKNOWLEDGE = "acknowledge"


class Outcome(str, Enum):
    COMPLETED = "completed"
    NOT_EXECUTED = "not_executed"


class Reason(str, Enum):
    INVALID = "invalid_input"
    CONFLICT = "identity_conflict"
    STALE = "stale_precondition"
    AUTHORITY = "authority_required"
    BUDGET = "budget_exhausted"
    STOPPING = "stopping_condition"
    STATE = "invalid_state"
    UNCERTAIN = "reconciliation_required"
    EVIDENCE = "matching_evidence_required"
    LIMIT = "bounded_history_full"


@dataclass(frozen=True)
class Result:
    result_id: str
    digest: str


@dataclass(frozen=True)
class Attempt:
    attempt_id: str
    run_id: str
    domain_job_id: str
    action_id: str
    action_digest: str
    fence: int
    lease_until: int | None
    state: AttemptState


@dataclass(frozen=True)
class Authority:
    task_id: str
    request_digest: str
    owner_id: str
    scope_digest: str
    checked_at: int
    expires_at: int
    revoked: bool


@dataclass(frozen=True)
class ActionReceipt:
    task_id: str
    owner_id: str
    attempt_id: str
    action_id: str
    action_digest: str
    outcome: Outcome
    result: Result | None


@dataclass(frozen=True)
class Context:
    now: int
    authority: Authority | None = None
    orphaned: bool = False
    # Supplied only after the host verifies against the domain action authority.
    verified_receipt: ActionReceipt | None = None
    termination_confirmed: bool = False
    # Posting/transport/legacy delivered_at must never set this field.
    acknowledged_notice_id: str | None = None


@dataclass(frozen=True)
class Event:
    event_id: str
    task_id: str
    request_id: str
    request_digest: str
    expected_version: int
    expected_attempt_id: str | None
    expected_fence: int
    kind: Kind
    attempt: Attempt | None = None
    reserve_units: int | None = None
    receipt: ActionReceipt | None = None
    notice_id: str | None = None
    result: Result | None = None


@dataclass(frozen=True)
class Snapshot:
    task_id: str
    request_id: str
    request_digest: str
    owner_id: str
    scope_digest: str
    stopping_digest: str
    deadline: int
    version: int
    status: Status
    remaining_attempts: int
    remaining_units: int
    attempts: tuple[Attempt, ...] = ()
    receipts: tuple[ActionReceipt, ...] = ()
    stopped_attempts: tuple[str, ...] = ()
    result: Result | None = None
    notice_id: str | None = None
    delivery: Delivery = Delivery.NONE
    last_event: Event | None = None


@dataclass(frozen=True)
class Rejected:
    reason: Reason


@dataclass(frozen=True)
class Proposed:
    expected_version: int
    snapshot: Snapshot
    replay: bool = False


# Resource bounds, not retry/spend/lease defaults. The host chooses all budgets.
_MAX_HISTORY = 64
_MAX_INT = 2**63 - 1
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", re.ASCII)
_DIGEST = re.compile(r"[0-9a-f]{64}", re.ASCII)


def _id(value):
    return type(value) is str and _ID.fullmatch(value) is not None


def _digest(value):
    return type(value) is str and _DIGEST.fullmatch(value) is not None


def _number(value):
    return type(value) is int and 0 <= value <= _MAX_INT


def _result(value):
    return type(value) is Result and _id(value.result_id) and _digest(value.digest)


def _attempt(value):
    return (type(value) is Attempt
            and all(_id(x) for x in (value.attempt_id, value.run_id,
                                    value.domain_job_id, value.action_id))
            and _digest(value.action_digest) and _number(value.fence)
            and value.fence > 0
            and (value.lease_until is None or _number(value.lease_until))
            and type(value.state) is AttemptState)


def _receipt(value):
    return (type(value) is ActionReceipt
            and all(_id(x) for x in (value.task_id, value.owner_id,
                                    value.attempt_id, value.action_id))
            and _digest(value.action_digest) and type(value.outcome) is Outcome
            and ((_result(value.result) and value.outcome is Outcome.COMPLETED)
                 or (value.result is None and value.outcome is Outcome.NOT_EXECUTED)))


def _event(value):
    if not (type(value) is Event
            and all(_id(x) for x in (value.event_id, value.task_id, value.request_id))
            and _digest(value.request_digest) and _number(value.expected_version)
            and (value.expected_attempt_id is None or _id(value.expected_attempt_id))
            and _number(value.expected_fence) and type(value.kind) is Kind):
        return False
    # Reject extraneous controls instead of silently ignoring unsupported fields.
    if value.kind is Kind.START:
        return (_attempt(value.attempt) and _number(value.reserve_units)
                and value.receipt is None
                and value.notice_id is None and value.result is None)
    if value.attempt is not None or value.reserve_units is not None:
        return False
    if value.kind is Kind.RECONCILE:
        return (_receipt(value.receipt) and value.notice_id is None
                and value.result is None)
    if value.receipt is not None:
        return False
    if value.kind in (Kind.BIND_NOTICE, Kind.DELIVERY_UNKNOWN, Kind.ACKNOWLEDGE):
        return _id(value.notice_id) and _result(value.result)
    return value.notice_id is None and value.result is None


def _context(value):
    if not (type(value) is Context and _number(value.now)
            and type(value.orphaned) is bool
            and type(value.termination_confirmed) is bool
            and (value.verified_receipt is None or _receipt(value.verified_receipt))
            and (value.acknowledged_notice_id is None
                 or _id(value.acknowledged_notice_id))):
        return False
    a = value.authority
    return a is None or (type(a) is Authority
            and _id(a.task_id) and _id(a.owner_id)
            and _digest(a.request_digest) and _digest(a.scope_digest)
            and _number(a.checked_at) and _number(a.expires_at)
            and type(a.revoked) is bool)


def _matches(receipt, snapshot, attempt):
    return (receipt.task_id == snapshot.task_id
            and receipt.owner_id == snapshot.owner_id
            and receipt.attempt_id == attempt.attempt_id
            and receipt.action_id == attempt.action_id
            and receipt.action_digest == attempt.action_digest)


def _snapshot(s):
    if not (type(s) is Snapshot
            and all(_id(x) for x in (s.task_id, s.request_id, s.owner_id))
            and all(_digest(x) for x in (s.request_digest, s.scope_digest, s.stopping_digest))
            and all(_number(x) for x in (s.deadline, s.version,
                                         s.remaining_attempts, s.remaining_units))
            and type(s.status) is Status and type(s.delivery) is Delivery
            and type(s.attempts) is tuple and len(s.attempts) <= _MAX_HISTORY
            and all(_attempt(a) for a in s.attempts)
            and type(s.receipts) is tuple and len(s.receipts) <= _MAX_HISTORY
            and all(_receipt(r) for r in s.receipts)
            and type(s.stopped_attempts) is tuple
            and len(s.stopped_attempts) <= _MAX_HISTORY
            and all(_id(a) for a in s.stopped_attempts)
            and (s.result is None or _result(s.result))
            and (s.notice_id is None or _id(s.notice_id))
            and (s.last_event is None or _event(s.last_event))):
        return False
    if len({a.attempt_id for a in s.attempts}) != len(s.attempts):
        return False
    if len({a.run_id for a in s.attempts}) != len(s.attempts):
        return False
    if any(a.fence >= b.fence for a, b in zip(s.attempts, s.attempts[1:])):
        return False
    if any(a.state is AttemptState.RUNNING for a in s.attempts[:-1]):
        return False
    if (len(set(s.stopped_attempts)) != len(s.stopped_attempts)
            or not set(s.stopped_attempts).issubset({a.attempt_id for a in s.attempts})):
        return False
    if any(a.state is AttemptState.RUNNING and a.attempt_id in s.stopped_attempts
           for a in s.attempts):
        return False
    current = s.attempts[-1] if s.attempts else None
    running = current is not None and current.state is AttemptState.RUNNING
    if running and s.status not in (Status.RUNNING, Status.CANCELLING):
        return False
    if s.status is Status.RUNNING and not running:
        return False
    if s.status is Status.QUEUED and s.attempts:
        return False
    if s.status is Status.CANCELLING and current is None:
        return False
    if s.status is Status.INTERRUPTED and (
            current is None or current.state is not AttemptState.INTERRUPTED):
        return False
    if len({r.attempt_id for r in s.receipts}) != len(s.receipts):
        return False
    for r in s.receipts:
        a = next((a for a in s.attempts if a.attempt_id == r.attempt_id), None)
        if a is None or not _matches(r, s, a):
            return False
    for a in s.attempts:
        receipt = next((r for r in s.receipts if r.attempt_id == a.attempt_id), None)
        if a.state is AttemptState.SUCCEEDED and (
                receipt is None or receipt.outcome is not Outcome.COMPLETED):
            return False
        if a.state is AttemptState.FAILED and (
                receipt is None or receipt.outcome is not Outcome.NOT_EXECUTED):
            return False
    for a in s.attempts[:-1]:
        receipt = next((r for r in s.receipts if r.attempt_id == a.attempt_id), None)
        if receipt is None or receipt.outcome is not Outcome.NOT_EXECUTED:
            return False
        if (a.domain_job_id, a.action_id, a.action_digest) != (
                current.domain_job_id, current.action_id, current.action_digest):
            return False
    if running and any(r.attempt_id == current.attempt_id for r in s.receipts):
        return False
    completed = tuple(r for r in s.receipts if r.outcome is Outcome.COMPLETED)
    if len(completed) > 1 or (s.result is not None) != bool(completed):
        return False
    if completed and s.result != completed[0].result:
        return False
    if s.status is Status.SUCCEEDED and s.result is None:
        return False
    if s.result is not None and s.status not in (
            Status.SUCCEEDED, Status.CANCELLING, Status.CANCELLED, Status.PARTIAL, Status.FAILED):
        return False
    if (s.notice_id is None) != (s.delivery is Delivery.NONE):
        return False
    if s.notice_id is not None and s.result is None:
        return False
    if s.last_event is not None:
        e = s.last_event
        if ((e.task_id, e.request_id, e.request_digest)
                != (s.task_id, s.request_id, s.request_digest)
                or e.expected_version + 1 != s.version):
            return False
    return True


def evaluate_transition(snapshot: Snapshot, event: Event,
                        context: Context) -> Proposed | Rejected:
    """Evaluate one bounded event without effects; invalid input fails closed.

    Only the latest event is retained for idempotency. Older callbacks must fail
    their version precondition. Terminal attempts are never rewritten. Receipt
    evidence is stored separately, including late evidence after cancellation.
    """
    if not (_snapshot(snapshot) and _event(event) and _context(context)):
        return Rejected(Reason.INVALID)
    s, e, c = snapshot, event, context
    if (e.task_id, e.request_id, e.request_digest) != (s.task_id, s.request_id, s.request_digest):
        return Rejected(Reason.CONFLICT)
    if s.last_event is not None and e.event_id == s.last_event.event_id:
        if e != s.last_event:
            return Rejected(Reason.CONFLICT)
        return Proposed(s.version, s, replay=True)
    current = s.attempts[-1] if s.attempts else None
    if (e.expected_version != s.version
            or e.expected_attempt_id != (current.attempt_id if current else None)
            or e.expected_fence != (current.fence if current else 0)):
        return Rejected(Reason.STALE)
    if s.version == _MAX_INT:
        return Rejected(Reason.LIMIT)

    def accept(**changes):
        proposed = replace(s, version=s.version + 1, last_event=e, **changes)
        if not _snapshot(proposed):
            return Rejected(Reason.INVALID)
        return Proposed(s.version, proposed)

    if e.kind is Kind.START:
        if s.status not in (Status.QUEUED, Status.BLOCKED, Status.INTERRUPTED):
            return Rejected(Reason.STATE)
        if c.now >= s.deadline:
            return Rejected(Reason.STOPPING)
        a = c.authority
        if (a is None or a.revoked or a.checked_at != c.now or a.expires_at <= c.now
                or (a.task_id, a.request_digest, a.owner_id, a.scope_digest)
                != (s.task_id, s.request_digest, s.owner_id, s.scope_digest)):
            return Rejected(Reason.AUTHORITY)
        if s.remaining_attempts == 0 or e.reserve_units > s.remaining_units:
            return Rejected(Reason.BUDGET)
        if s.result is not None:
            return Rejected(Reason.STATE)
        if current is not None:
            receipt = next((r for r in s.receipts if r.attempt_id == current.attempt_id), None)
            if receipt is None or receipt.outcome is not Outcome.NOT_EXECUTED:
                return Rejected(Reason.UNCERTAIN)
        new = e.attempt
        if (new.state is not AttemptState.RUNNING or new.lease_until is None
                or new.lease_until <= c.now or new.lease_until > a.expires_at
                or new.lease_until > s.deadline
                or any(new.attempt_id == old.attempt_id or new.run_id == old.run_id
                       for old in s.attempts)
                or (current is not None and (new.fence <= current.fence
                    or (new.domain_job_id, new.action_id, new.action_digest)
                    != (current.domain_job_id, current.action_id, current.action_digest)))):
            return Rejected(Reason.CONFLICT)
        if len(s.attempts) == _MAX_HISTORY:
            return Rejected(Reason.LIMIT)
        return accept(status=Status.RUNNING, attempts=s.attempts + (new,),
                      remaining_attempts=s.remaining_attempts - 1,
                      remaining_units=s.remaining_units - e.reserve_units)

    if e.kind is Kind.INTERRUPT:
        if current is None or current.state is not AttemptState.RUNNING:
            return Rejected(Reason.STATE)
        if not (c.orphaned or current.lease_until is None or current.lease_until <= c.now):
            return Rejected(Reason.EVIDENCE)
        return accept(status=Status.CANCELLING if s.status is Status.CANCELLING else Status.INTERRUPTED,
                      attempts=s.attempts[:-1] + (replace(current, state=AttemptState.INTERRUPTED),))

    if e.kind in (Kind.CANCEL, Kind.TIMEOUT):
        if s.status in (Status.SUCCEEDED, Status.PARTIAL, Status.FAILED, Status.CANCELLED):
            return Rejected(Reason.STATE)
        if e.kind is Kind.TIMEOUT and c.now < s.deadline:
            return Rejected(Reason.EVIDENCE)
        # An orphan is not proof of termination or cleanup. Keep cancellation pending.
        pending = current is not None and current.attempt_id not in s.stopped_attempts
        return accept(status=Status.CANCELLING if pending else Status.CANCELLED)

    if e.kind is Kind.CONFIRM_STOP:
        if s.status is not Status.CANCELLING or not c.termination_confirmed:
            return Rejected(Reason.EVIDENCE)
        attempts = s.attempts
        if current is not None and current.state is AttemptState.RUNNING:
            attempts = attempts[:-1] + (replace(current, state=AttemptState.STOPPED),)
        stopped = s.stopped_attempts
        if current is not None and current.attempt_id not in stopped:
            stopped += (current.attempt_id,)
        return accept(status=Status.CANCELLED, attempts=attempts, stopped_attempts=stopped)

    if e.kind is Kind.RECONCILE:
        r = e.receipt
        if (current is None or c.verified_receipt != r or not _matches(r, s, current)):
            return Rejected(Reason.EVIDENCE)
        prior = next((r for r in s.receipts if r.attempt_id == current.attempt_id), None)
        if prior is not None:
            return Rejected(Reason.CONFLICT)
        if len(s.receipts) == _MAX_HISTORY:
            return Rejected(Reason.LIMIT)
        attempts = s.attempts
        completed = r.outcome is Outcome.COMPLETED
        if current.state is AttemptState.RUNNING:
            state = AttemptState.SUCCEEDED if completed else AttemptState.FAILED
            attempts = attempts[:-1] + (replace(current, state=state),)
        status = s.status
        if status not in (Status.CANCELLING, Status.CANCELLED, Status.PARTIAL, Status.FAILED):
            status = Status.SUCCEEDED if completed else Status.BLOCKED
        return accept(status=status, attempts=attempts, receipts=s.receipts + (r,),
                      result=r.result if completed else s.result)

    # Delivery transitions retain exact result/notice identities and never send.
    if s.result is None or e.result != s.result:
        return Rejected(Reason.EVIDENCE)
    if e.kind is Kind.BIND_NOTICE:
        if s.notice_id is not None:
            return Rejected(Reason.CONFLICT)
        return accept(notice_id=e.notice_id, delivery=Delivery.PENDING)
    if e.notice_id != s.notice_id:
        return Rejected(Reason.CONFLICT)
    if e.kind is Kind.DELIVERY_UNKNOWN:
        if s.delivery is Delivery.ACKNOWLEDGED:
            return Rejected(Reason.STATE)
        return accept(delivery=Delivery.UNKNOWN)
    if e.kind is Kind.ACKNOWLEDGE:
        if c.acknowledged_notice_id != s.notice_id:
            return Rejected(Reason.EVIDENCE)
        return accept(delivery=Delivery.ACKNOWLEDGED)
    return Rejected(Reason.STATE)
