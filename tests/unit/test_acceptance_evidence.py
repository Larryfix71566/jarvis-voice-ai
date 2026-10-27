"""WS-23 V1–V12: synthetic inputs only; no runner or acceptance automation.

Run with stdlib unittest (no shared fixture/runtime imports) or collect with the
repository's normal pytest job. Guard tests load only this module's source into
an isolated module name, with all source bytes read before I/O is prohibited.
"""

from __future__ import annotations

import builtins
import io
import logging
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import time
import types
import unittest
import uuid
from contextlib import ExitStack
from dataclasses import FrozenInstanceError, fields, replace
from itertools import permutations
from unittest.mock import patch

from jarvis import acceptance_evidence as E


def digest(character="a"):
    return character * 64


def fixtures(evidence_class=E.EvidenceClass.SOURCE):
    checks = (
        E.CheckManifest("shape", digest("1"), digest("2")),
        E.CheckManifest("safety", digest("3"), digest("4")),
    )
    bindings = (
        E.Binding(E.BindingKey.SOURCE_COMMIT, "a" * 40),
        E.Binding(E.BindingKey.CANDIDATE, digest("b")),
        E.Binding(E.BindingKey.CONFIGURATION, digest("c")),
        E.Binding(E.BindingKey.BASELINE, digest("d")),
        E.Binding(E.BindingKey.IMAGE, digest("e")),
        E.Binding(E.BindingKey.PROFILE, digest("f")),
        E.Binding(E.BindingKey.RUNNER, digest("0")),
        E.Binding(E.BindingKey.DEVELOPMENT_TASK, "synthetic-task"),
    )
    part = E.Subpart(
        "source", evidence_class, ("shape", "safety"),
        tuple(b.key for b in bindings), checks,
        (E.Prerequisite("available", E.PrerequisiteState.MET),),
    )
    criterion = E.Criterion("criterion", digest(), (part,))
    receipt = E.Receipt(
        "receipt", criterion.criterion_id, criterion.revision_sha256,
        evidence_class, bindings, checks,
        tuple(E.Observation("source", name, E.ObservationOutcome.PASSED)
              for name in part.assertions),
    )
    return criterion, receipt, E.ExpectedContext(bindings)


def fail(receipt):
    return replace(receipt, observations=(
        replace(receipt.observations[0], outcome=E.ObservationOutcome.FAILED),
        receipt.observations[1],
    ))


def prerequisite(criterion, state):
    return replace(criterion, subparts=(replace(
        criterion.subparts[0], prerequisites=(E.Prerequisite("available", state),)),))


class AcceptanceEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.criterion, self.receipt, self.context = fixtures()

    def evaluate(self, receipts=None, criterion=None, context=None):
        result = E.evaluate_evidence(
            criterion if criterion is not None else self.criterion,
            (self.receipt,) if receipts is None else receipts,
            context if context is not None else self.context,
        )
        self.assertIsInstance(result, E.Evaluation)
        return result

    def test_matching_source_and_synthetic_only_pass_demonstrated_subpart(self):
        for kind in (E.EvidenceClass.SOURCE, E.EvidenceClass.SYNTHETIC):
            with self.subTest(kind=kind):
                criterion, receipt, context = fixtures(kind)
                result = self.evaluate((receipt,), criterion, context)
                part = result.subparts[0]
                self.assertEqual(part.status, E.Status.PASSED)
                self.assertEqual(part.passed_assertions, ("safety", "shape"))
                self.assertEqual(part.uncovered_assertions, ())
                self.assertIn("metadata_match_is_not_authenticity_or_log_verification", result.limits)
                self.assertFalse(hasattr(result, "accepted"))
                self.assertFalse(hasattr(result, "status"))
                self.assertEqual({b.key: b.value for b in result.evidence[0].tested_bindings},
                                 {b.key: b.value for b in receipt.bindings})

    def test_v1_observed_failure_not_transport_success(self):
        result = self.evaluate((fail(self.receipt),))
        self.assertEqual(result.subparts[0].status, E.Status.FAILED)
        self.assertEqual(result.subparts[0].failed_assertions, ("shape",))
        self.assertIn(E.Reason.OBSERVED_FAILURE, result.subparts[0].reasons)

    def test_v1a_failure_precedes_unknown_or_unmet_prerequisite(self):
        for state, reason in (
            (E.PrerequisiteState.UNKNOWN, E.Reason.PREREQUISITE_UNKNOWN),
            (E.PrerequisiteState.UNMET, E.Reason.PREREQUISITE_UNMET),
        ):
            with self.subTest(state=state):
                result = self.evaluate((fail(self.receipt),), prerequisite(self.criterion, state))
                self.assertEqual(result.subparts[0].status, E.Status.FAILED)
                self.assertEqual(result.subparts[0].reasons[0], E.Reason.OBSERVED_FAILURE)
                self.assertIn(reason, result.subparts[0].reasons)
                self.assertEqual(result.subparts[0].unmet_prerequisites,
                                 (E.Prerequisite("available", state),))

    def test_v1b_positive_cannot_override_unknown_or_unmet_prerequisite(self):
        for state in (E.PrerequisiteState.UNKNOWN, E.PrerequisiteState.UNMET):
            with self.subTest(state=state):
                result = self.evaluate(criterion=prerequisite(self.criterion, state))
                self.assertEqual(result.subparts[0].status, E.Status.BLOCKED)
                self.assertEqual(result.subparts[0].passed_assertions, ("safety", "shape"))
                self.assertEqual(result.subparts[0].uncovered_assertions, ())

    def test_v2_v3_v5_each_wrong_binding_is_historical_not_current_proof(self):
        for index, binding in enumerate(self.receipt.bindings):
            with self.subTest(binding=binding.key):
                value = "other-task" if binding.key is E.BindingKey.DEVELOPMENT_TASK else (
                    "1" * 40 if binding.key is E.BindingKey.SOURCE_COMMIT else digest("9"))
                bindings = list(self.receipt.bindings)
                bindings[index] = replace(binding, value=value)
                result = self.evaluate((replace(self.receipt, bindings=tuple(bindings)),))
                self.assertEqual(result.subparts[0].status, E.Status.UNTESTED)
                self.assertEqual(result.subparts[0].admitted_receipts, ())
                self.assertEqual(result.evidence[0].disposition, E.Disposition.HISTORICAL)
                self.assertEqual(result.evidence[0].reason, E.Reason.BINDING_MISMATCH)
                self.assertEqual(result.evidence[0].binding, binding.key)

    def test_v3_revision_is_historical_even_if_old_assertion_names_differ(self):
        receipt = replace(self.receipt, revision_sha256=digest("9"), observations=(
            E.Observation("old", "old", E.ObservationOutcome.PASSED),))
        result = self.evaluate((receipt,))
        self.assertEqual(result.subparts[0].status, E.Status.UNTESTED)
        self.assertEqual(result.evidence[0].reason, E.Reason.STALE_CRITERION)
        self.assertEqual(result.evidence[0].disposition, E.Disposition.HISTORICAL)

    def test_other_criterion_is_rejected_not_reused(self):
        result = self.evaluate((replace(self.receipt, criterion_id="other"),))
        self.assertEqual(result.subparts[0].status, E.Status.UNTESTED)
        self.assertEqual(result.evidence[0].reason, E.Reason.WRONG_CRITERION)

    def test_missing_receipt_binding_does_not_become_failed_assertion(self):
        result = self.evaluate((replace(fail(self.receipt), bindings=self.receipt.bindings[1:]),))
        self.assertEqual(result.subparts[0].status, E.Status.UNTESTED)
        self.assertEqual(result.evidence[0].reason, E.Reason.MISSING_BINDING)

    def test_receipt_cannot_supply_missing_host_binding(self):
        context = replace(self.context, bindings=self.context.bindings[1:])
        result = self.evaluate((fail(self.receipt),), context=context)
        self.assertEqual(result.subparts[0].status, E.Status.BLOCKED)
        self.assertIn(E.Reason.MISSING_EXPECTED_BINDING, result.subparts[0].reasons)
        self.assertEqual(result.subparts[0].failed_assertions, ())

    def test_v4_v6_every_unsupported_class_remains_blocked_even_on_failure(self):
        for kind in E.EvidenceClass:
            if kind in E.SUPPORTED_CLASSES:
                continue
            for observation in (self.receipt, fail(self.receipt)):
                with self.subTest(kind=kind, outcome=observation.observations[0].outcome):
                    unsupported = replace(self.criterion.subparts[0], subpart_id="human",
                                          evidence_class=kind)
                    criterion = replace(self.criterion, subparts=(self.criterion.subparts[0], unsupported))
                    extra = replace(observation, receipt_id="human-receipt", evidence_class=kind,
                                    observations=tuple(replace(o, subpart_id="human")
                                                       for o in observation.observations))
                    result = self.evaluate((self.receipt, extra), criterion)
                    self.assertEqual(result.subparts[0].status, E.Status.PASSED)
                    self.assertEqual(result.subparts[1].status, E.Status.BLOCKED)
                    self.assertEqual(result.subparts[1].admitted_receipts, ())
                    self.assertEqual(result.subparts[1].failed_assertions, ())
                    self.assertIn(E.Reason.UNSUPPORTED_CLASS, result.subparts[1].reasons)

    def test_wrong_evidence_class_cannot_prove_source(self):
        result = self.evaluate((replace(self.receipt, evidence_class=E.EvidenceClass.HUMAN),))
        self.assertEqual(result.subparts[0].status, E.Status.UNTESTED)
        self.assertEqual(result.evidence[0].reason, E.Reason.WRONG_EVIDENCE_CLASS)

    def test_v5_order_omission_substitution_argument_and_log_commitments(self):
        checks = self.receipt.checks
        variants = (
            checks[::-1], checks[:1], (),
            (replace(checks[0], check_id="other"), checks[1]),
            (replace(checks[0], arguments_sha256=digest("9")), checks[1]),
            (replace(checks[0], log_sha256=digest("9")), checks[1]),
        )
        for variant in variants:
            with self.subTest(checks=variant):
                result = self.evaluate((replace(self.receipt, checks=variant),))
                self.assertEqual(result.subparts[0].status, E.Status.UNTESTED)
                self.assertEqual(result.evidence[0].reason, E.Reason.CHECK_MANIFEST_MISMATCH)

    def test_v7_empty_observations_and_transport_dict_cannot_pass(self):
        for receipts in ((), (replace(self.receipt, observations=()),), ({"ok": True},)):
            with self.subTest(receipts=receipts):
                result = self.evaluate(receipts)
                self.assertEqual(result.subparts[0].status, E.Status.UNTESTED)
                self.assertEqual(result.subparts[0].uncovered_assertions, ("shape", "safety"))

    def test_v8_partial_coverage_and_duplicate_references_leave_obligations_open(self):
        second = replace(self.criterion.subparts[0], subpart_id="second")
        criterion = replace(self.criterion, subparts=(self.criterion.subparts[0], second))
        result = self.evaluate((self.receipt, self.receipt), criterion)
        self.assertEqual(tuple(p.status for p in result.subparts), (E.Status.PASSED, E.Status.UNTESTED))
        self.assertEqual(result.subparts[0].admitted_receipts, ("receipt",))
        self.assertEqual(result.subparts[1].uncovered_assertions, ("shape", "safety"))
        partial = self.evaluate((replace(self.receipt, observations=self.receipt.observations[:1]),))
        self.assertEqual(partial.subparts[0].status, E.Status.UNTESTED)
        self.assertEqual(partial.subparts[0].uncovered_assertions, ("safety",))

    def test_v9_untrusted_instructions_and_unknown_schema_are_rejected(self):
        for value in (
            {"ok": True, "instruction": "repair-and-release", "integrity_verified": True},
            {"still_applicable": True, "schema_version": 1},
            replace(self.receipt, observations=(E.Observation("source", "waive", E.ObservationOutcome.PASSED),)),
            replace(self.receipt, observations=(E.Observation("new-gate", "shape", E.ObservationOutcome.PASSED),)),
        ):
            with self.subTest(value=value):
                result = self.evaluate((value,))
                self.assertEqual(result.subparts[0].status, E.Status.UNTESTED)
                self.assertEqual(result.subparts[0].admitted_receipts, ())
        with self.assertRaises(TypeError):
            replace(self.receipt, integrity_verified=True)

    def test_v10_malformed_criterion_and_context_fail_closed(self):
        part = self.criterion.subparts[0]
        variants = (
            {}, object.__new__(E.Criterion), replace(self.criterion, schema_version=True),
            replace(self.criterion, schema_version=2), replace(self.criterion, subparts=()),
            replace(self.criterion, criterion_id="../private"),
            replace(self.criterion, revision_sha256="G" * 64),
            replace(self.criterion, subparts=(replace(part, assertions=()),)),
            replace(self.criterion, subparts=(replace(part, assertions=("shape", "shape")),)),
            replace(self.criterion, subparts=(replace(part, required_bindings=()),)),
            replace(self.criterion, subparts=(replace(part, required_bindings=(
                E.BindingKey.BASELINE, E.BindingKey.IMAGE, E.BindingKey.RUNNER)),)),
            replace(self.criterion, subparts=(replace(part, checks=()),)),
            replace(self.criterion, subparts=(replace(part, evidence_class="source"),)),
            replace(self.criterion, subparts=(replace(part, prerequisites=(
                E.Prerequisite("p", "met"),)),)),
            replace(self.criterion, subparts=(part, part)),
        )
        for value in variants:
            with self.subTest(value_type=type(value)):
                result = E.evaluate_evidence(value, (self.receipt,), self.context)
                self.assertIsInstance(result, E.InputRejection)
                self.assertEqual(result.reason, E.Reason.INVALID_CRITERION)
        for value in ({}, object.__new__(E.ExpectedContext), replace(self.context, schema_version=True),
                      replace(self.context, bindings=self.context.bindings + self.context.bindings[:1])):
            result = E.evaluate_evidence(self.criterion, (self.receipt,), value)
            self.assertEqual(result.reason, E.Reason.INVALID_CONTEXT)

    def test_v10_malformed_receipt_cannot_erase_independent_failure(self):
        invalid = (
            {}, object.__new__(E.Receipt), replace(self.receipt, schema_version=True),
            replace(self.receipt, receipt_id=True), replace(self.receipt, revision_sha256=True),
            replace(self.receipt, evidence_class="source"), replace(self.receipt, bindings=[]),
            replace(self.receipt, checks=(replace(self.receipt.checks[0], log_sha256="bad"),)),
            replace(self.receipt, observations=(replace(self.receipt.observations[0], outcome=True),)),
            replace(self.receipt, observations=(self.receipt.observations[0],) * 2),
            replace(self.receipt, bindings=(E.Binding("source_commit", "a" * 40),)),
        )
        valid_failure = replace(fail(self.receipt), receipt_id="independent")
        for value in invalid:
            with self.subTest(value_type=type(value)):
                result = self.evaluate((value, valid_failure))
                self.assertEqual(result.subparts[0].status, E.Status.FAILED)
                self.assertEqual(result.subparts[0].admitted_receipts, ("independent",))
                self.assertTrue(any(d.reason is E.Reason.MALFORMED_RECEIPT for d in result.evidence))

    def test_v10_finite_limits_accept_boundary_and_refuse_one_over(self):
        ids = tuple(f"a{i}" for i in range(E.MAX_ASSERTIONS))
        part = replace(self.criterion.subparts[0], assertions=ids)
        criterion = replace(self.criterion, subparts=(part,))
        receipt = replace(self.receipt, observations=tuple(
            E.Observation("source", name, E.ObservationOutcome.PASSED) for name in ids))
        self.assertEqual(self.evaluate((receipt,), criterion).subparts[0].status, E.Status.PASSED)
        oversized = replace(criterion, subparts=(replace(part, assertions=ids + ("extra",)),))
        self.assertIsInstance(E.evaluate_evidence(oversized, (), self.context), E.InputRejection)
        receipts = tuple(replace(self.receipt, receipt_id=f"r{i}") for i in range(E.MAX_RECEIPTS))
        self.assertEqual(len(self.evaluate(receipts).subparts[0].admitted_receipts), E.MAX_RECEIPTS)
        self.assertEqual(E.evaluate_evidence(self.criterion, receipts + (self.receipt,), self.context).reason,
                         E.Reason.INVALID_EVIDENCE_SEQUENCE)
        for bad in (list(receipts), iter(receipts), True):
            self.assertIsInstance(E.evaluate_evidence(self.criterion, bad, self.context), E.InputRejection)
        for length in (E.MAX_ID_CHARS, E.MAX_ID_CHARS + 1):
            result = self.evaluate((replace(self.receipt, receipt_id="r" * length),))
            self.assertEqual(result.subparts[0].status,
                             E.Status.PASSED if length == E.MAX_ID_CHARS else E.Status.UNTESTED)

    def test_v10_all_collection_caps_are_enforced(self):
        part = self.criterion.subparts[0]
        criteria = (
            replace(self.criterion, subparts=tuple(replace(part, subpart_id=f"p{i}")
                    for i in range(E.MAX_SUBPARTS + 1))),
            replace(self.criterion, subparts=(replace(part, prerequisites=tuple(
                E.Prerequisite(f"p{i}", E.PrerequisiteState.MET)
                for i in range(E.MAX_PREREQUISITES + 1))),)),
            replace(self.criterion, subparts=(replace(part, checks=tuple(
                replace(part.checks[0], check_id=f"c{i}") for i in range(E.MAX_CHECKS + 1))),)),
        )
        for criterion in criteria:
            self.assertIsInstance(E.evaluate_evidence(criterion, (), self.context), E.InputRejection)
        receipt = replace(self.receipt, observations=tuple(
            E.Observation("source", f"a{i}", E.ObservationOutcome.PASSED)
            for i in range(E.MAX_OBSERVATIONS + 1)))
        self.assertEqual(self.evaluate((receipt,)).evidence[0].validation, E.ValidationCode.COLLECTION)

    def test_v11_failure_survives_positive_and_permuted_receipts(self):
        failure = replace(fail(self.receipt), receipt_id="failure")
        unknown = prerequisite(self.criterion, E.PrerequisiteState.UNKNOWN)
        results = [self.evaluate(tuple(order), unknown) for order in permutations((self.receipt, failure))]
        self.assertEqual(results[0], results[1])
        self.assertEqual(results[0].subparts[0].status, E.Status.FAILED)
        self.assertEqual(results[0].subparts[0].failed_assertions, ("shape",))

    def test_v11_conflicting_same_id_is_rejected_without_hiding_other_failure(self):
        conflicting = fail(self.receipt)
        independent = replace(conflicting, receipt_id="independent")
        results = [self.evaluate(tuple(order))
                   for order in permutations((self.receipt, conflicting, independent))]
        self.assertTrue(all(result == results[0] for result in results))
        self.assertEqual(results[0].subparts[0].status, E.Status.FAILED)
        self.assertEqual(results[0].subparts[0].admitted_receipts, ("independent",))
        self.assertTrue(any(d.reason is E.Reason.CONFLICTING_RECEIPT_ID for d in results[0].evidence))
        only_conflict = self.evaluate((self.receipt, conflicting))
        self.assertEqual(only_conflict.subparts[0].status, E.Status.UNTESTED)

    def test_malformed_id_collision_cannot_leave_clean_copy_admitted(self):
        malformed = replace(self.receipt, schema_version=999)
        result = self.evaluate((self.receipt, malformed))
        self.assertEqual(result.subparts[0].status, E.Status.UNTESTED)
        self.assertEqual(result.subparts[0].admitted_receipts, ())

    def test_strict_records_do_not_call_hostile_objects_or_subclasses(self):
        class Hostile:
            def __getattribute__(self, name):
                raise AssertionError("untrusted object executed")
        class HostileString(str):
            def __len__(self):
                raise AssertionError("string subclass executed")
        for value in (Hostile(), replace(self.receipt, receipt_id=HostileString("receipt"))):
            result = self.evaluate((value,))
            self.assertEqual(result.subparts[0].status, E.Status.UNTESTED)
        class DerivedReceipt(E.Receipt):
            pass
        derived = DerivedReceipt(**{field.name: getattr(self.receipt, field.name) for field in fields(self.receipt)})
        self.assertEqual(self.evaluate((derived,)).evidence[0].reason, E.Reason.MALFORMED_RECEIPT)

    def test_immutable_inputs_and_results_have_no_mutable_nested_fields(self):
        before = repr((self.criterion, self.receipt, self.context))
        result = self.evaluate()
        self.assertEqual(before, repr((self.criterion, self.receipt, self.context)))
        with self.assertRaises(FrozenInstanceError):
            result.criterion_id = "changed"
        with self.assertRaises(FrozenInstanceError):
            self.receipt.checks[0].check_id = "changed"
        self.assertIs(type(result.subparts), tuple)
        self.assertIs(type(result.evidence), tuple)

    def test_v12_import_and_evaluation_deny_ambient_io_with_negative_controls(self):
        source = Path(E.__file__).read_text()
        compiled = compile(source, "<isolated-acceptance-evidence>", "exec")
        name = "_ws23_guarded_contract"
        module = types.ModuleType(name)
        module.__file__ = "<isolated-acceptance-evidence>"
        targets = (
            "builtins.open", "io.open", "os.open", "os.getenv", "os.putenv",
            "socket.socket", "socket.create_connection", "subprocess.Popen", "os.system",
            "sqlite3.connect", "time.time", "time.monotonic", "uuid.uuid4", "logging.getLogger",
        )
        def denied(*args, **kwargs):
            raise AssertionError("ambient access denied")
        with ExitStack() as stack:
            stack.enter_context(patch.dict(sys.modules, {name: module}))
            for target in targets:
                stack.enter_context(patch(target, denied))
            stack.enter_context(patch.object(type(os.environ), "__getitem__", denied))
            stack.enter_context(patch.object(type(os.environ), "__setitem__", denied))
            exec(compiled, module.__dict__)
            c = module
            bindings = (
                c.Binding(c.BindingKey.SOURCE_COMMIT, "a" * 40),
                c.Binding(c.BindingKey.CANDIDATE, digest("b")),
                c.Binding(c.BindingKey.CONFIGURATION, digest("c")),
            )
            checks = (c.CheckManifest("check", digest("1"), digest("2")),)
            criterion = c.Criterion("criterion", digest(), (c.Subpart(
                "source", c.EvidenceClass.SOURCE, ("check",), c.COMMON_BINDINGS, checks),))
            receipt = c.Receipt("receipt", "criterion", digest(), c.EvidenceClass.SOURCE,
                                bindings, checks, (c.Observation("source", "check", c.ObservationOutcome.PASSED),))
            self.assertEqual(c.evaluate_evidence(criterion, (receipt,), c.ExpectedContext(bindings))
                             .subparts[0].status, c.Status.PASSED)
            for attempt in (
                lambda: builtins.open("must-not-open"), lambda: io.open("must-not-open"),
                lambda: os.getenv("WS23_MUST_NOT_READ"), lambda: os.environ["WS23_MUST_NOT_READ"],
                lambda: socket.socket(), lambda: subprocess.Popen(["must-not-start"]),
                lambda: sqlite3.connect(":memory:"), lambda: time.time(),
                lambda: time.monotonic(), lambda: uuid.uuid4(), lambda: logging.getLogger("test"),
            ):
                with self.assertRaisesRegex(AssertionError, "ambient access denied"):
                    attempt()


if __name__ == "__main__":
    unittest.main()
