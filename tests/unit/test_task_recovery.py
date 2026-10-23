"""Synthetic, offline contract tests; no storage or production service fixtures.

Also runnable with stdlib unittest, avoiding repository-wide pytest fixtures.
"""
import ast
from contextlib import ExitStack
from dataclasses import FrozenInstanceError, replace
import os
from pathlib import Path
import pickle
import sys
import types
import unittest
from unittest.mock import patch

from jarvis import task_recovery as tr

D = "a" * 64
SCOPE = "b" * 64
STOP = "c" * 64
ACTION = "d" * 64
RESULT = tr.Result("result-1", "e" * 64)


def initial(**changes):
    s = tr.Snapshot("task-1", "request-1", D, "owner-1", SCOPE, STOP,
                    1000, 0, tr.Status.QUEUED, 3, 30)
    return replace(s, **changes)


def context(now=100, **changes):
    a = tr.Authority("task-1", D, "owner-1", SCOPE, now, 900, False)
    return replace(tr.Context(now, a), **changes)


def attempt(number=1, **changes):
    a = tr.Attempt(f"attempt-{number}", f"run-{number}", "job-1", "action-1",
                   ACTION, number, 500, tr.AttemptState.RUNNING)
    return replace(a, **changes)


def event(s, kind, **changes):
    a = s.attempts[-1] if s.attempts else None
    e = tr.Event(f"event-{s.version + 1}", s.task_id, s.request_id,
                 s.request_digest, s.version, a.attempt_id if a else None,
                 a.fence if a else 0, kind)
    return replace(e, **changes)


def start(s=None, c=None, **changes):
    s = initial() if s is None else s
    c = context() if c is None else c
    e = event(s, tr.Kind.START, attempt=attempt(len(s.attempts) + 1), reserve_units=10)
    return tr.evaluate_transition(s, replace(e, **changes), c)


def receipt(s, outcome=tr.Outcome.COMPLETED, **changes):
    a = s.attempts[-1]
    r = tr.ActionReceipt(s.task_id, s.owner_id, a.attempt_id, a.action_id,
                         a.action_digest, outcome,
                         RESULT if outcome is tr.Outcome.COMPLETED else None)
    return replace(r, **changes)


def outcome(s, value=tr.Outcome.COMPLETED):
    r = receipt(s, value)
    return tr.evaluate_transition(s, event(s, tr.Kind.RECONCILE, receipt=r),
                                  context(verified_receipt=r))


class RecoveryContractTests(unittest.TestCase):
    def proposed(self, value):
        self.assertIsInstance(value, tr.Proposed)
        return value.snapshot

    def reject(self, value, reason):
        self.assertEqual(value, tr.Rejected(reason))

    def running(self):
        return self.proposed(start())

    def interrupted(self):
        s = self.running()
        return self.proposed(tr.evaluate_transition(
            s, event(s, tr.Kind.INTERRUPT), context(orphaned=True)))

    def completed(self):
        return self.proposed(outcome(self.running()))

    def test_authorized_start_is_immutable_cas_proposal(self):
        s = initial()
        p = start(s)
        n = self.proposed(p)
        self.assertEqual(p.expected_version, 0)
        self.assertEqual((n.version, n.status, n.remaining_attempts, n.remaining_units),
                         (1, tr.Status.RUNNING, 2, 20))
        self.assertEqual(s, initial())
        with self.assertRaises(FrozenInstanceError):
            n.version = 2
        with self.assertRaises(FrozenInstanceError):
            n.attempts[0].fence = 4

    def test_status_vocabulary_preserves_ws22(self):
        self.assertEqual({x.value for x in tr.Status}, {
            "queued", "running", "blocked", "cancelling", "succeeded", "partial",
            "failed", "cancelled", "interrupted"})

    def test_last_event_replay_is_noop_even_after_authority_expiry(self):
        s = self.running()
        p = tr.evaluate_transition(s, s.last_event, context(now=950, authority=None))
        self.assertTrue(p.replay)
        self.assertIs(p.snapshot, s)
        self.assertEqual(p.expected_version, s.version)

    def test_changed_replay_payload_and_request_reuse_conflict(self):
        s = self.running()
        for e in (replace(s.last_event, reserve_units=11),
                  replace(s.last_event, request_digest="f" * 64),
                  replace(s.last_event, request_id="different")):
            with self.subTest(event=e):
                self.reject(tr.evaluate_transition(s, e, context()), tr.Reason.CONFLICT)

    def test_stale_version_attempt_and_fence_refuse(self):
        s = self.running()
        e = event(s, tr.Kind.INTERRUPT)
        for changes in ({"expected_version": 0}, {"expected_fence": 0},
                        {"expected_attempt_id": "other"}):
            with self.subTest(changes=changes):
                self.reject(tr.evaluate_transition(s, replace(e, **changes),
                                                   context(orphaned=True)), tr.Reason.STALE)

    def test_competing_proposals_require_future_atomic_compare_and_swap(self):
        s = initial()
        first = start(s)
        other = start(s, event_id="event-other", attempt=attempt(2))
        self.assertIsInstance(other, tr.Proposed)  # evaluator is not a lock
        self.assertEqual(first.expected_version, other.expected_version)
        # Once one result is the stored snapshot, the other's event is stale.
        self.reject(tr.evaluate_transition(first.snapshot, other.snapshot.last_event,
                                           context()), tr.Reason.STALE)

    def test_missing_revoked_stale_or_mismatched_authority_refuses(self):
        a = context().authority
        for authority in (None, replace(a, revoked=True), replace(a, expires_at=100),
                          replace(a, checked_at=99), replace(a, task_id="other"),
                          replace(a, owner_id="other"), replace(a, scope_digest="f" * 64),
                          replace(a, request_digest="f" * 64)):
            with self.subTest(authority=authority):
                self.reject(start(c=context(authority=authority)), tr.Reason.AUTHORITY)

    def test_explicit_budget_and_stopping_gate(self):
        for s in (initial(remaining_attempts=0), initial(remaining_units=9)):
            self.reject(start(s), tr.Reason.BUDGET)
        self.reject(start(initial(deadline=100)), tr.Reason.STOPPING)
        for units in (None, -1, True, "10"):
            self.reject(start(reserve_units=units), tr.Reason.INVALID)

    def test_explicit_zero_unit_reservation_still_consumes_attempt_budget(self):
        n = self.proposed(start(initial(remaining_units=0), reserve_units=0))
        self.assertEqual((n.remaining_units, n.remaining_attempts), (0, 2))

    def test_lease_must_fit_authority_and_stopping_window(self):
        for lease in (None, 100, 901, 1001):
            self.reject(start(attempt=attempt(lease_until=lease)), tr.Reason.CONFLICT)
        self.reject(start(initial(deadline=400)), tr.Reason.CONFLICT)

    def test_orphan_or_missing_expired_lease_interrupts_not_requeues(self):
        s = self.running()
        for snapshot, c in ((s, context(orphaned=True)), (s, context(now=500)),
                            (replace(s, attempts=(replace(s.attempts[0], lease_until=None),)), context())):
            n = self.proposed(tr.evaluate_transition(snapshot, event(snapshot, tr.Kind.INTERRUPT), c))
            self.assertEqual(n.status, tr.Status.INTERRUPTED)
            self.assertEqual((n.remaining_attempts, n.remaining_units), (2, 20))
            self.reject(start(n), tr.Reason.UNCERTAIN)
        self.reject(tr.evaluate_transition(s, event(s, tr.Kind.INTERRUPT), context()),
                    tr.Reason.EVIDENCE)

    def test_receipt_must_be_verified_and_bind_task_owner_action_attempt_digest(self):
        s = self.interrupted()
        r = receipt(s)
        self.reject(tr.evaluate_transition(s, event(s, tr.Kind.RECONCILE, receipt=r),
                                           context()), tr.Reason.EVIDENCE)
        for field, value in (("task_id", "other"), ("owner_id", "other"),
                             ("attempt_id", "other"), ("action_id", "other"),
                             ("action_digest", "f" * 64)):
            wrong = replace(r, **{field: value})
            self.reject(tr.evaluate_transition(s, event(s, tr.Kind.RECONCILE, receipt=wrong),
                                               context(verified_receipt=wrong)), tr.Reason.EVIDENCE)

    def test_completed_orphan_action_never_duplicates_and_terminal_attempt_unchanged(self):
        s = self.interrupted()
        n = self.proposed(outcome(s))
        self.assertEqual(n.status, tr.Status.SUCCEEDED)
        self.assertEqual(n.attempts, s.attempts)
        self.assertEqual(n.result, RESULT)
        self.reject(start(n), tr.Reason.STATE)

    def test_definitive_not_executed_permits_linked_retry_without_budget_reset(self):
        s = self.interrupted()
        resolved = self.proposed(outcome(s, tr.Outcome.NOT_EXECUTED))
        self.assertEqual(resolved.status, tr.Status.BLOCKED)
        self.assertEqual(resolved.attempts, s.attempts)
        # Synthetic serialization does not replenish budgets/stopping criteria.
        restored = pickle.loads(pickle.dumps(resolved))
        n = self.proposed(start(restored))
        self.assertEqual((n.remaining_attempts, n.remaining_units, n.stopping_digest,
                          n.deadline), (1, 10, STOP, 1000))
        self.assertEqual(n.attempts[0], s.attempts[0])
        self.assertEqual(n.attempts[-1].attempt_id, "attempt-2")

    def test_retry_cannot_change_action_job_reuse_run_or_lower_fence(self):
        s = self.proposed(outcome(self.interrupted(), tr.Outcome.NOT_EXECUTED))
        for changes in ({"action_id": "other"}, {"action_digest": "f" * 64},
                        {"domain_job_id": "other"}, {"run_id": "run-1"},
                        {"attempt_id": "attempt-1"}, {"fence": 1}):
            self.reject(start(s, attempt=attempt(2, **changes)), tr.Reason.CONFLICT)

    def test_stale_old_attempt_cannot_reconcile_after_retry(self):
        old = self.interrupted()
        s = self.proposed(start(self.proposed(outcome(old, tr.Outcome.NOT_EXECUTED))))
        r = receipt(old)
        self.reject(tr.evaluate_transition(s, event(s, tr.Kind.RECONCILE, receipt=r),
                                           context(verified_receipt=r)), tr.Reason.EVIDENCE)

    def test_retry_exhaustion_is_not_refilled(self):
        s = initial(remaining_attempts=1)
        s = self.proposed(outcome(self.proposed(start(s)), tr.Outcome.NOT_EXECUTED))
        self.reject(start(s), tr.Reason.BUDGET)

    def test_conflicting_or_repeated_outcome_cannot_rewrite_evidence(self):
        s = self.completed()
        self.reject(outcome(s, tr.Outcome.NOT_EXECUTED), tr.Reason.CONFLICT)
        self.reject(outcome(s), tr.Reason.CONFLICT)
        self.assertEqual(s.result, RESULT)

    def test_cancel_before_start_has_no_dispatch(self):
        s = initial()
        n = self.proposed(tr.evaluate_transition(s, event(s, tr.Kind.CANCEL), context()))
        self.assertEqual(n.status, tr.Status.CANCELLED)
        self.assertEqual(n.attempts, ())
        self.reject(start(n), tr.Reason.STATE)

    def test_inflight_cancel_waits_for_termination_and_orphan_is_not_cleanup(self):
        for s in (self.running(), self.interrupted()):
            n = self.proposed(tr.evaluate_transition(s, event(s, tr.Kind.CANCEL), context()))
            self.assertEqual(n.status, tr.Status.CANCELLING)
            self.reject(start(n), tr.Reason.STATE)
            stop = event(n, tr.Kind.CONFIRM_STOP)
            self.reject(tr.evaluate_transition(n, stop, context(orphaned=True)), tr.Reason.EVIDENCE)
            stopped = self.proposed(tr.evaluate_transition(n, stop, context(termination_confirmed=True)))
            self.assertEqual(stopped.status, tr.Status.CANCELLED)
            self.reject(start(stopped), tr.Reason.STATE)
            if s.status is tr.Status.INTERRUPTED:
                self.assertEqual(stopped.attempts, s.attempts)

    def test_action_outcome_is_not_worker_cleanup_confirmation(self):
        s = self.proposed(outcome(self.running(), tr.Outcome.NOT_EXECUTED))
        terminal_attempt = s.attempts[-1]
        s = self.proposed(tr.evaluate_transition(s, event(s, tr.Kind.CANCEL), context()))
        self.assertEqual(s.status, tr.Status.CANCELLING)
        self.reject(tr.evaluate_transition(s, event(s, tr.Kind.CONFIRM_STOP), context()),
                    tr.Reason.EVIDENCE)
        s = self.proposed(tr.evaluate_transition(s, event(s, tr.Kind.CONFIRM_STOP),
                                                context(termination_confirmed=True)))
        self.assertEqual(s.status, tr.Status.CANCELLED)
        self.assertEqual(s.stopped_attempts, (terminal_attempt.attempt_id,))
        self.assertEqual(s.attempts[-1], terminal_attempt)

    def test_cancelled_persisted_snapshot_requires_retained_stop_evidence(self):
        for original in (self.running(), self.interrupted()):
            cancelling = self.proposed(tr.evaluate_transition(
                original, event(original, tr.Kind.CANCEL), context()))
            cancelled = self.proposed(tr.evaluate_transition(
                cancelling, event(cancelling, tr.Kind.CONFIRM_STOP),
                context(termination_confirmed=True)))
            # Simulate losing the explicit stop evidence in a restored snapshot.
            broken = replace(pickle.loads(pickle.dumps(cancelled)), stopped_attempts=())
            self.reject(tr.evaluate_transition(broken, broken.last_event, context()),
                        tr.Reason.INVALID)
            r = receipt(broken)
            self.reject(tr.evaluate_transition(broken, event(broken, tr.Kind.RECONCILE, receipt=r),
                                               context(verified_receipt=r)), tr.Reason.INVALID)
            # Retained stop evidence allows late results without reopening work.
            valid = self.proposed(outcome(cancelled))
            self.assertEqual(valid.status, tr.Status.CANCELLED)
            self.assertEqual(valid.stopped_attempts, cancelled.stopped_attempts)
            self.assertEqual(valid.attempts, cancelled.attempts)
            self.assertTrue(tr.evaluate_transition(valid, valid.last_event, context()).replay)
            if original.status is tr.Status.RUNNING:
                # A terminal STOPPED attempt needs its stop evidence in any task state.
                broken = replace(broken, status=tr.Status.BLOCKED, last_event=None)
                self.reject(tr.evaluate_transition(broken, event(broken, tr.Kind.CANCEL), context()),
                            tr.Reason.INVALID)

    def test_timeout_requires_deadline_and_still_waits_for_stop(self):
        s = self.running()
        e = event(s, tr.Kind.TIMEOUT)
        self.reject(tr.evaluate_transition(s, e, context()), tr.Reason.EVIDENCE)
        n = self.proposed(tr.evaluate_transition(s, e, context(now=1000)))
        self.assertEqual(n.status, tr.Status.CANCELLING)

    def test_late_success_retained_without_reopening_cancelled_task(self):
        s = self.running()
        s = self.proposed(tr.evaluate_transition(s, event(s, tr.Kind.CANCEL), context()))
        s = self.proposed(tr.evaluate_transition(s, event(s, tr.Kind.CONFIRM_STOP),
                                                context(termination_confirmed=True)))
        n = self.proposed(outcome(s))
        self.assertEqual((n.status, n.result), (tr.Status.CANCELLED, RESULT))
        self.assertEqual(n.attempts, s.attempts)
        self.reject(start(n), tr.Reason.STATE)

    def test_result_after_cancel_does_not_prove_cleanup(self):
        s = self.running()
        s = self.proposed(tr.evaluate_transition(s, event(s, tr.Kind.CANCEL), context()))
        n = self.proposed(outcome(s))
        self.assertEqual(n.status, tr.Status.CANCELLING)
        self.reject(tr.evaluate_transition(n, event(n, tr.Kind.CONFIRM_STOP), context()),
                    tr.Reason.EVIDENCE)

    def test_posting_is_not_ack_and_lost_ack_keeps_notice_and_result(self):
        s = self.completed()
        n = self.proposed(tr.evaluate_transition(s, event(s, tr.Kind.BIND_NOTICE,
            notice_id="notice-1", result=RESULT), context()))
        self.assertEqual(n.delivery, tr.Delivery.PENDING)
        unknown = self.proposed(tr.evaluate_transition(n, event(n, tr.Kind.DELIVERY_UNKNOWN,
            notice_id="notice-1", result=RESULT), context()))
        self.assertEqual(unknown.delivery, tr.Delivery.UNKNOWN)
        self.assertEqual((unknown.result, unknown.notice_id, unknown.attempts),
                         (RESULT, "notice-1", s.attempts))
        ack = event(unknown, tr.Kind.ACKNOWLEDGE, notice_id="notice-1", result=RESULT)
        self.reject(tr.evaluate_transition(unknown, ack, context()), tr.Reason.EVIDENCE)
        self.reject(tr.evaluate_transition(unknown, ack, context(acknowledged_notice_id="other")),
                    tr.Reason.EVIDENCE)
        n = self.proposed(tr.evaluate_transition(unknown, ack, context(acknowledged_notice_id="notice-1")))
        self.assertEqual(n.delivery, tr.Delivery.ACKNOWLEDGED)
        replay = tr.evaluate_transition(n, ack, context())
        self.assertTrue(replay.replay)
        self.reject(tr.evaluate_transition(n, event(n, tr.Kind.DELIVERY_UNKNOWN,
            notice_id="notice-1", result=RESULT), context()), tr.Reason.STATE)

    def test_delivery_cannot_replace_saved_result_or_notice(self):
        s = self.completed()
        wrong = replace(RESULT, result_id="other")
        self.reject(tr.evaluate_transition(s, event(s, tr.Kind.BIND_NOTICE,
            notice_id="notice-1", result=wrong), context()), tr.Reason.EVIDENCE)
        s = self.proposed(tr.evaluate_transition(s, event(s, tr.Kind.BIND_NOTICE,
            notice_id="notice-1", result=RESULT), context()))
        self.reject(tr.evaluate_transition(s, event(s, tr.Kind.BIND_NOTICE,
            notice_id="notice-2", result=RESULT), context()), tr.Reason.CONFLICT)
        self.reject(tr.evaluate_transition(s, event(s, tr.Kind.ACKNOWLEDGE,
            notice_id="notice-2", result=RESULT), context(acknowledged_notice_id="notice-2")),
            tr.Reason.CONFLICT)

    def test_invalid_inputs_fail_closed_without_mutation(self):
        s = initial()
        e = event(s, tr.Kind.START, attempt=attempt(), reserve_units=10)
        snapshots = [None, {}, replace(s, version=True), replace(s, remaining_units=-1),
                     replace(s, status="queued"), replace(s, task_id="/private/path"),
                     replace(s, owner_id="x" * 129), replace(s, request_digest="payload"),
                     replace(s, attempts=[]), replace(s, attempts=(attempt(),) * 65),
                     replace(s, receipts=(object(),)), replace(s, result=RESULT),
                     replace(s, delivery=tr.Delivery.ACKNOWLEDGED)]
        for invalid in snapshots:
            with self.subTest(snapshot=invalid):
                self.reject(tr.evaluate_transition(invalid, e, context()), tr.Reason.INVALID)
        for invalid in (None, {}, replace(e, kind="start"), replace(e, notice_id="extra"),
                        replace(e, attempt=replace(attempt(), fence=True))):
            self.reject(tr.evaluate_transition(s, invalid, context()), tr.Reason.INVALID)
        for invalid in (None, {}, replace(context(), now=True),
                        replace(context(), termination_confirmed=1)):
            self.reject(tr.evaluate_transition(s, e, invalid), tr.Reason.INVALID)
        self.assertEqual(s, initial())

    def test_inconsistent_history_and_terminal_attempts_refuse(self):
        s = self.running()
        broken = [replace(s, status=tr.Status.CANCELLED),
                  replace(s, attempts=(replace(s.attempts[0], state=tr.AttemptState.FAILED),)),
                  replace(s, receipts=(receipt(s),)),
                  replace(s, last_event=replace(s.last_event, expected_version=5)),
                  replace(s, attempts=(replace(attempt(), state=tr.AttemptState.INTERRUPTED), attempt(2)))]
        for invalid in broken:
            self.reject(tr.evaluate_transition(invalid, event(s, tr.Kind.CANCEL), context()),
                        tr.Reason.INVALID)

    def test_bounded_history_and_version_overflow_refuse_without_discarding_evidence(self):
        s = initial(remaining_attempts=65, remaining_units=650)
        for number in range(1, 65):
            s = self.proposed(start(s))
            s = self.proposed(outcome(s, tr.Outcome.NOT_EXECUTED))
        self.assertEqual(len(s.attempts), 64)
        self.reject(start(s), tr.Reason.LIMIT)
        huge = initial(version=2**63 - 1)
        self.reject(start(huge), tr.Reason.LIMIT)
        self.reject(start(initial(version=2**63)), tr.Reason.INVALID)

    def test_terminal_and_contradictory_states_cannot_grant_dispatch(self):
        for status in (tr.Status.PARTIAL, tr.Status.FAILED, tr.Status.CANCELLED):
            self.reject(start(initial(status=status)), tr.Reason.STATE)
        for status in (tr.Status.RUNNING, tr.Status.INTERRUPTED, tr.Status.CANCELLING,
                       tr.Status.SUCCEEDED):
            self.reject(start(initial(status=status)), tr.Reason.INVALID)
        s = self.completed()
        invalid = replace(s, status=tr.Status.BLOCKED)
        self.reject(tr.evaluate_transition(invalid, event(invalid, tr.Kind.CANCEL), context()),
                    tr.Reason.INVALID)

    def test_no_ambient_effects_at_module_execution_or_evaluation(self):
        source = Path(tr.__file__).read_text()
        tree = ast.parse(source)
        imports = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
        imports |= {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
        self.assertEqual(imports, {"__future__", "dataclasses", "enum", "re"})
        compiled = compile(source, "synthetic-contract", "exec")
        module = types.ModuleType("synthetic_recovery")
        s = initial()
        e = event(s, tr.Kind.START, attempt=attempt(), reserve_units=10)
        c = context()

        def forbidden(*args, **kwargs):
            raise AssertionError("ambient effect attempted")

        class NoEnvironment(dict):
            __getitem__ = get = __iter__ = __contains__ = forbidden

        with ExitStack() as stack:
            for name in ("builtins.open", "io.open", "os.getenv", "os.system", "socket.socket",
                         "subprocess.Popen", "time.time", "time.monotonic", "time.sleep"):
                stack.enter_context(patch(name, forbidden))
            stack.enter_context(patch.object(os, "environ", NoEnvironment()))
            stack.enter_context(patch.dict(sys.modules, {module.__name__: module}))
            exec(compiled, module.__dict__)
            self.assertIsInstance(tr.evaluate_transition(s, e, c), tr.Proposed)


if __name__ == "__main__":
    unittest.main()
