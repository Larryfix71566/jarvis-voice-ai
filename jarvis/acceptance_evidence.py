"""WS-23's unused, pure evidence contract; this is not a verifier runner.

The caller owns the criterion and expected context. Receipts are untrusted data.
Matching metadata is conditional evidence, never proof of authenticity, actual
log bytes, an installed build or human acceptance. There are no production
callers, state stores, clocks, callbacks or I/O here. See the canonical WS-23 plan.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


MAX_ID_CHARS = 80
MAX_SUBPARTS = 32
MAX_ASSERTIONS = 64
MAX_PREREQUISITES = 16
MAX_CHECKS = 32
MAX_RECEIPTS = 128
MAX_OBSERVATIONS = 256


class EvidenceClass(str, Enum):
    SOURCE = "source"
    SYNTHETIC = "synthetic"
    INSTALLED = "installed"
    LIVE = "live"
    HARDWARE = "hardware"
    OBSERVATION = "observation"
    HUMAN = "human"


class BindingKey(str, Enum):
    SOURCE_COMMIT = "source_commit"
    CANDIDATE = "candidate"
    CONFIGURATION = "configuration"
    BASELINE = "baseline"
    IMAGE = "image"
    PROFILE = "profile"
    RUNNER = "runner"
    DEVELOPMENT_TASK = "development_task"
    INSTALLED = "installed"
    LOADED = "loaded"


class PrerequisiteState(str, Enum):
    MET = "met"
    UNMET = "unmet"
    UNKNOWN = "unknown"


class ObservationOutcome(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


class Status(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    BLOCKED = "blocked"
    UNTESTED = "untested"


class Disposition(str, Enum):
    ADMITTED = "admitted"
    REJECTED = "rejected"
    HISTORICAL = "historical"


class Reason(str, Enum):
    INVALID_CRITERION = "invalid_criterion"
    INVALID_CONTEXT = "invalid_context"
    INVALID_EVIDENCE_SEQUENCE = "invalid_evidence_sequence"
    MALFORMED_RECEIPT = "malformed_receipt"
    CONFLICTING_RECEIPT_ID = "conflicting_receipt_id"
    WRONG_CRITERION = "wrong_criterion"
    STALE_CRITERION = "stale_criterion"
    UNKNOWN_OBSERVATION = "unknown_observation"
    UNSUPPORTED_CLASS = "unsupported_class"
    WRONG_EVIDENCE_CLASS = "wrong_evidence_class"
    MISSING_EXPECTED_BINDING = "missing_expected_binding"
    MISSING_BINDING = "missing_binding"
    BINDING_MISMATCH = "binding_mismatch"
    CHECK_MANIFEST_MISMATCH = "check_manifest_mismatch"
    MATCHED_METADATA = "matched_metadata"
    OBSERVED_FAILURE = "observed_failure"
    PREREQUISITE_UNMET = "prerequisite_unmet"
    PREREQUISITE_UNKNOWN = "prerequisite_unknown"
    MISSING_OBSERVATIONS = "missing_observations"
    ALL_REQUIRED_OBSERVED = "all_required_observed"


class ValidationCode(str, Enum):
    RECORD_TYPE = "record_type"
    VERSION = "version"
    TOKEN = "token"
    DIGEST = "digest"
    ENUM = "enum"
    COLLECTION = "collection"
    DUPLICATE = "duplicate"
    REQUIRED_BINDINGS = "required_bindings"


@dataclass(frozen=True, slots=True)
class Binding:
    key: BindingKey
    value: str


@dataclass(frozen=True, slots=True)
class CheckManifest:
    """Commitments to ordered check arguments/log bytes, not executable argv."""

    check_id: str
    arguments_sha256: str
    log_sha256: str


@dataclass(frozen=True, slots=True)
class Prerequisite:
    prerequisite_id: str
    state: PrerequisiteState


COMMON_BINDINGS = (
    BindingKey.SOURCE_COMMIT, BindingKey.CANDIDATE, BindingKey.CONFIGURATION,
)
SUPPORTED_CLASSES = (EvidenceClass.SOURCE, EvidenceClass.SYNTHETIC)


@dataclass(frozen=True, slots=True)
class Subpart:
    subpart_id: str
    evidence_class: EvidenceClass
    assertions: tuple[str, ...]
    required_bindings: tuple[BindingKey, ...]
    checks: tuple[CheckManifest, ...]
    prerequisites: tuple[Prerequisite, ...] = ()


@dataclass(frozen=True, slots=True)
class Criterion:
    criterion_id: str
    revision_sha256: str
    subparts: tuple[Subpart, ...]
    schema_version: int = 1


@dataclass(frozen=True, slots=True)
class ExpectedContext:
    bindings: tuple[Binding, ...]
    schema_version: int = 1


@dataclass(frozen=True, slots=True)
class Observation:
    subpart_id: str
    assertion_id: str
    outcome: ObservationOutcome


@dataclass(frozen=True, slots=True)
class Receipt:
    receipt_id: str
    criterion_id: str
    revision_sha256: str
    evidence_class: EvidenceClass
    bindings: tuple[Binding, ...]
    checks: tuple[CheckManifest, ...]
    observations: tuple[Observation, ...]
    schema_version: int = 1


@dataclass(frozen=True, slots=True)
class InputRejection:
    reason: Reason
    validation: ValidationCode


@dataclass(frozen=True, slots=True)
class EvidenceDisposition:
    receipt_id: str | None
    subpart_id: str | None
    disposition: Disposition
    reason: Reason
    binding: BindingKey | None = None
    validation: ValidationCode | None = None
    tested_bindings: tuple[Binding, ...] = ()


@dataclass(frozen=True, slots=True)
class SubpartResult:
    subpart_id: str
    status: Status
    reasons: tuple[Reason, ...]
    unmet_prerequisites: tuple[Prerequisite, ...]
    admitted_receipts: tuple[str, ...]
    passed_assertions: tuple[str, ...]
    failed_assertions: tuple[str, ...]
    uncovered_assertions: tuple[str, ...]
    expected_bindings: tuple[Binding, ...]


@dataclass(frozen=True, slots=True)
class Evaluation:
    criterion_id: str
    revision_sha256: str
    subparts: tuple[SubpartResult, ...]
    evidence: tuple[EvidenceDisposition, ...]
    # Fixed caveats cannot be replaced by receipt text.
    limits: tuple[str, ...] = (
        "conditional_on_host_established_inputs",
        "metadata_match_is_not_authenticity_or_log_verification",
        "source_and_synthetic_subparts_only",
        "no_parent_or_human_acceptance",
    )


class _Invalid(ValueError):
    def __init__(self, code: ValidationCode):
        self.code = code


def _require(condition: bool, code: ValidationCode) -> None:
    if not condition:
        raise _Invalid(code)


def _token(value: object) -> None:
    _require(type(value) is str and 0 < len(value) <= MAX_ID_CHARS
             and all(c in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.:-"
                     for c in value), ValidationCode.TOKEN)


def _digest(value: object, sizes: tuple[int, ...] = (64,)) -> None:
    _require(type(value) is str and len(value) in sizes
             and all(c in "0123456789abcdef" for c in value), ValidationCode.DIGEST)


def _tuple(value: object, maximum: int, minimum: int = 0) -> None:
    _require(type(value) is tuple and minimum <= len(value) <= maximum,
             ValidationCode.COLLECTION)


def _version(value: object) -> None:
    _require(type(value) is int and value == 1, ValidationCode.VERSION)


def _unique(values: tuple) -> None:
    _require(len(set(values)) == len(values), ValidationCode.DUPLICATE)


def _bindings(values: object) -> None:
    _tuple(values, len(BindingKey))
    for item in values:
        _require(type(item) is Binding, ValidationCode.RECORD_TYPE)
        _require(type(item.key) is BindingKey, ValidationCode.ENUM)
        if item.key is BindingKey.DEVELOPMENT_TASK:
            _token(item.value)
        else:
            _digest(item.value, (40, 64) if item.key is BindingKey.SOURCE_COMMIT else (64,))
    _unique(tuple(item.key for item in values))


def _checks(values: object, minimum: int = 0) -> None:
    _tuple(values, MAX_CHECKS, minimum)
    for item in values:
        _require(type(item) is CheckManifest, ValidationCode.RECORD_TYPE)
        _token(item.check_id)
        _digest(item.arguments_sha256)
        _digest(item.log_sha256)
    _unique(tuple(item.check_id for item in values))


def _criterion(value: object) -> None:
    _require(type(value) is Criterion, ValidationCode.RECORD_TYPE)
    _version(value.schema_version)
    _token(value.criterion_id)
    _digest(value.revision_sha256)
    _tuple(value.subparts, MAX_SUBPARTS, 1)
    for part in value.subparts:
        _require(type(part) is Subpart, ValidationCode.RECORD_TYPE)
        _token(part.subpart_id)
        _require(type(part.evidence_class) is EvidenceClass, ValidationCode.ENUM)
        _tuple(part.assertions, MAX_ASSERTIONS, 1)
        for name in part.assertions:
            _token(name)
        _unique(part.assertions)
        _tuple(part.required_bindings, len(BindingKey), len(COMMON_BINDINGS))
        for key in part.required_bindings:
            _require(type(key) is BindingKey, ValidationCode.ENUM)
        _unique(part.required_bindings)
        _require(set(COMMON_BINDINGS) <= set(part.required_bindings),
                 ValidationCode.REQUIRED_BINDINGS)
        _checks(part.checks, 1 if part.evidence_class in SUPPORTED_CLASSES else 0)
        _tuple(part.prerequisites, MAX_PREREQUISITES)
        for prerequisite in part.prerequisites:
            _require(type(prerequisite) is Prerequisite, ValidationCode.RECORD_TYPE)
            _token(prerequisite.prerequisite_id)
            _require(type(prerequisite.state) is PrerequisiteState, ValidationCode.ENUM)
        _unique(tuple(p.prerequisite_id for p in part.prerequisites))
    _unique(tuple(part.subpart_id for part in value.subparts))


def _context(value: object) -> None:
    _require(type(value) is ExpectedContext, ValidationCode.RECORD_TYPE)
    _version(value.schema_version)
    _bindings(value.bindings)


def _receipt(value: object) -> None:
    _require(type(value) is Receipt, ValidationCode.RECORD_TYPE)
    _version(value.schema_version)
    _token(value.receipt_id)
    _token(value.criterion_id)
    _digest(value.revision_sha256)
    _require(type(value.evidence_class) is EvidenceClass, ValidationCode.ENUM)
    _bindings(value.bindings)
    _checks(value.checks)
    _tuple(value.observations, MAX_OBSERVATIONS)
    for observation in value.observations:
        _require(type(observation) is Observation, ValidationCode.RECORD_TYPE)
        _token(observation.subpart_id)
        _token(observation.assertion_id)
        _require(type(observation.outcome) is ObservationOutcome, ValidationCode.ENUM)
    _unique(tuple((o.subpart_id, o.assertion_id) for o in value.observations))


def _safe_reference(value: object) -> str | None:
    if type(value) is Receipt:
        try:
            _token(value.receipt_id)
            return value.receipt_id
        except (_Invalid, AttributeError):
            pass
    return None


def _binding_tuple(values: tuple[Binding, ...]) -> tuple[Binding, ...]:
    return tuple(sorted(values, key=lambda item: item.key.value))


def evaluate_evidence(
    criterion: Criterion, evidence: tuple[Receipt, ...], expected_context: ExpectedContext,
) -> Evaluation | InputRejection:
    """Classify supplied metadata only; never acquire evidence or execute rules.

    Exact record types and tuples are required; mappings, subclasses, generators
    and unknown schemas are refused rather than interpreted as trusted policy.
    Malformed receipts are individually rejected so they cannot hide an unrelated
    admitted failure. A malformed receipt also poisons reuse of its own ID.
    """
    for value, validator, reason in (
        (criterion, _criterion, Reason.INVALID_CRITERION),
        (expected_context, _context, Reason.INVALID_CONTEXT),
    ):
        try:
            validator(value)
        except _Invalid as exc:
            return InputRejection(reason, exc.code)
        except AttributeError:
            return InputRejection(reason, ValidationCode.RECORD_TYPE)
    try:
        _tuple(evidence, MAX_RECEIPTS)
    except _Invalid as exc:
        return InputRejection(Reason.INVALID_EVIDENCE_SEQUENCE, exc.code)

    dispositions: set[EvidenceDisposition] = set()
    grouped: dict[str, list[Receipt]] = {}
    malformed_ids: set[str] = set()
    for receipt in evidence:
        try:
            _receipt(receipt)
        except (_Invalid, AttributeError) as exc:
            reference = _safe_reference(receipt)
            if reference is not None:
                malformed_ids.add(reference)
            dispositions.add(EvidenceDisposition(
                reference, None, Disposition.REJECTED, Reason.MALFORMED_RECEIPT,
                validation=exc.code if type(exc) is _Invalid else ValidationCode.RECORD_TYPE,
            ))
            continue
        grouped.setdefault(receipt.receipt_id, []).append(receipt)

    parts = {part.subpart_id: part for part in criterion.subparts}
    usable: list[Receipt] = []
    for reference in sorted(grouped):
        group = grouped[reference]
        receipt = group[0]
        if reference in malformed_ids or any(r != receipt for r in group[1:]):
            dispositions.add(EvidenceDisposition(
                reference, None, Disposition.REJECTED, Reason.CONFLICTING_RECEIPT_ID))
        elif receipt.criterion_id != criterion.criterion_id:
            dispositions.add(EvidenceDisposition(
                reference, None, Disposition.REJECTED, Reason.WRONG_CRITERION))
        elif receipt.revision_sha256 != criterion.revision_sha256:
            dispositions.add(EvidenceDisposition(
                reference, None, Disposition.HISTORICAL, Reason.STALE_CRITERION))
        elif any(o.subpart_id not in parts or o.assertion_id not in parts[o.subpart_id].assertions
                 for o in receipt.observations):
            dispositions.add(EvidenceDisposition(
                reference, None, Disposition.REJECTED, Reason.UNKNOWN_OBSERVATION))
        else:
            usable.append(receipt)

    expected = {item.key: item.value for item in expected_context.bindings}
    results: list[SubpartResult] = []
    for part in criterion.subparts:
        failed: set[str] = set()
        passed: set[str] = set()
        admitted: list[str] = []
        missing_expected = next((key for key in part.required_bindings if key not in expected), None)
        supported = part.evidence_class in SUPPORTED_CLASSES
        for receipt in usable:
            reason, binding = Reason.MATCHED_METADATA, None
            actual = {item.key: item.value for item in receipt.bindings}
            if not supported:
                reason = Reason.UNSUPPORTED_CLASS
            elif receipt.evidence_class is not part.evidence_class:
                reason = Reason.WRONG_EVIDENCE_CLASS
            elif missing_expected is not None:
                reason, binding = Reason.MISSING_EXPECTED_BINDING, missing_expected
            else:
                for key in part.required_bindings:
                    if key not in actual:
                        reason, binding = Reason.MISSING_BINDING, key
                        break
                    if actual[key] != expected[key]:
                        reason, binding = Reason.BINDING_MISMATCH, key
                        break
                if reason is Reason.MATCHED_METADATA and receipt.checks != part.checks:
                    reason = Reason.CHECK_MANIFEST_MISMATCH
            matched = reason is Reason.MATCHED_METADATA
            disposition = Disposition.ADMITTED if matched else Disposition.REJECTED
            # A bound but older source/config snapshot is history, never current proof.
            if reason is Reason.BINDING_MISMATCH:
                disposition = Disposition.HISTORICAL
            dispositions.add(EvidenceDisposition(
                receipt.receipt_id, part.subpart_id, disposition, reason, binding,
                tested_bindings=_binding_tuple(receipt.bindings) if matched else (),
            ))
            if matched:
                admitted.append(receipt.receipt_id)
                for observation in receipt.observations:
                    if observation.subpart_id == part.subpart_id:
                        target = failed if observation.outcome is ObservationOutcome.FAILED else passed
                        target.add(observation.assertion_id)

        blockers = tuple(p for p in part.prerequisites if p.state is not PrerequisiteState.MET)
        reasons: list[Reason] = []
        if not supported:
            reasons.append(Reason.UNSUPPORTED_CLASS)
        if missing_expected is not None:
            reasons.append(Reason.MISSING_EXPECTED_BINDING)
        if any(p.state is PrerequisiteState.UNMET for p in blockers):
            reasons.append(Reason.PREREQUISITE_UNMET)
        if any(p.state is PrerequisiteState.UNKNOWN for p in blockers):
            reasons.append(Reason.PREREQUISITE_UNKNOWN)
        uncovered = tuple(name for name in part.assertions if name not in passed | failed)
        if failed:
            status = Status.FAILED
            reasons.insert(0, Reason.OBSERVED_FAILURE)
        elif reasons:
            status = Status.BLOCKED
        elif uncovered:
            status = Status.UNTESTED
            reasons.append(Reason.MISSING_OBSERVATIONS)
        else:
            status = Status.PASSED
            reasons.append(Reason.ALL_REQUIRED_OBSERVED)
        results.append(SubpartResult(
            part.subpart_id, status, tuple(reasons), blockers, tuple(admitted),
            tuple(sorted(passed)), tuple(sorted(failed)), uncovered,
            tuple(Binding(key, expected[key]) for key in part.required_bindings if key in expected),
        ))

    ordered = tuple(sorted(dispositions, key=lambda d: (
        d.receipt_id or "", d.subpart_id or "", d.disposition.value, d.reason.value,
        d.binding.value if d.binding else "", d.validation.value if d.validation else "",
    )))
    return Evaluation(criterion.criterion_id, criterion.revision_sha256, tuple(results), ordered)
