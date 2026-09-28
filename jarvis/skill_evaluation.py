"""Budget controls for opt-in, host-owned Agent Skill comparisons.

This module does not invoke a provider. Callers must resolve the dedicated
``skill_eval`` workload first, then reserve each bounded call before handing
it to the existing model-execution boundary.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import secrets
import stat
import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jarvis.model_routing import (
    ResolvedModelRoute,
    SkillEvaluationLimits,
)


class SkillEvaluationBudgetError(RuntimeError):
    """A trial cannot start without exceeding or losing its configured cap."""


_INPUT_MESSAGE_OVERHEAD_TOKENS = 256
_MAX_FIXTURE_BYTES = 1_048_576
_MAX_TRIAL_RESPONSE_CHARS = 128_000

# Approval is for exact, reviewed public fixture bytes, not just a caller-chosen
# fixture_id. To revise prompts or rubric criteria, add a new versioned fixture
# ID (for example skill-creator-v2), review it, then add its SHA-256 here. Never
# replace an existing digest: prior evaluation receipts must remain reproducible.
FROZEN_SKILL_EVALUATION_FIXTURE_SHA256 = {
    "skill-creator-v1": "43c563255e96bf4f081dcd497005af05986b6d01662e5c41cf11691140b85c12",
}


def require_frozen_skill_evaluation_fixture(fixture_id: str, digest: str) -> None:
    """Reject unreviewed fixture bytes even when their fixture ID is approved."""
    expected = FROZEN_SKILL_EVALUATION_FIXTURE_SHA256.get(fixture_id)
    if expected is None or not isinstance(digest, str) or digest != expected:
        raise ValueError("evaluation fixture bytes are not an approved frozen version")


def require_frozen_skill_evaluation_cases(
    cases: tuple[SkillEvaluationCase, ...],
    *,
    fixture_id: str | None,
    fixture_sha256: str | None,
    max_cases: int,
) -> None:
    """Bind provider-bound prompts to the exact reviewed fixture cases.

    A matching caller-supplied digest alone is insufficient: compare the
    supplied objects to cases loaded from the checked-in fixture after
    independently verifying its frozen byte digest.
    """
    if not isinstance(fixture_id, str) or not re.fullmatch(
            r"[A-Za-z0-9_-]{1,64}", fixture_id):
        raise ValueError("evaluation requires an approved frozen fixture identity")
    if not isinstance(fixture_sha256, str):
        raise TypeError("evaluation requires verified frozen fixture provenance")
    require_frozen_skill_evaluation_fixture(fixture_id, fixture_sha256)
    fixture_path = (
        Path(__file__).resolve().parents[1] / "tests" / "fixtures"
        / "skills_workspace" / "evaluations" / f"{fixture_id}.json"
    )
    frozen_cases, on_disk_digest = load_skill_evaluation_fixture(
        fixture_path, max_cases=max_cases, expected_fixture_id=fixture_id,
    )
    if on_disk_digest != fixture_sha256 or cases != frozen_cases:
        raise ValueError("evaluation cases do not match the approved frozen fixture")


@dataclass(frozen=True)
class SkillEvaluationReservation:
    call_number: int
    trial_id: str
    reserved_cost_usd: float
    reserved_total_usd: float


class SkillEvaluationBudget:
    """In-memory batch budget with conservative pre-call spend reservation."""

    def __init__(
        self,
        limits: SkillEvaluationLimits,
        route: ResolvedModelRoute,
        *,
        cost_estimator: Callable[[str, str, int, int], float | None] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.limits = limits
        self.route = route
        if route.workload != "skill_eval":
            raise ValueError("skill evaluation requires the dedicated skill_eval route")
        self._clock = clock
        self._started = clock()
        self._calls = 0
        self._trial_calls: dict[str, int] = defaultdict(int)
        self._reserved_cost_usd = 0.0
        if cost_estimator is None:
            from jarvis.usage_ledger import compute_cost
            cost_estimator = compute_cost
        self._cost_estimator = cost_estimator

    @property
    def calls_reserved(self) -> int:
        return self._calls

    @property
    def spend_reserved_usd(self) -> float:
        return self._reserved_cost_usd

    def remaining_seconds(self) -> float:
        """Return the current batch time remaining, clamped at zero."""
        return max(0.0, self.limits.deadline_seconds - (self._clock() - self._started))

    def reserve_call(
        self,
        trial_id: str,
        *,
        input_token_upper_bound: int,
        output_token_upper_bound: int,
    ) -> SkillEvaluationReservation:
        """Reserve a worst-case call before provider execution begins.

        Failed and cancelled calls retain their reservation because billing is
        not known at this boundary. This prevents retries from overshooting a
        spend cap when an upstream result is uncertain.
        """
        if not isinstance(trial_id, str) or not re.fullmatch(
                r"[A-Za-z0-9_-]{1,96}", trial_id):
            raise SkillEvaluationBudgetError("invalid evaluation trial ID")
        for name, value, ceiling in (
            ("input", input_token_upper_bound,
             self.limits.max_input_tokens_per_call),
            ("output", output_token_upper_bound,
             self.limits.max_output_tokens_per_call),
        ):
            if type(value) is not int or value < 1 or value > ceiling:
                raise SkillEvaluationBudgetError(
                    f"evaluation {name} token bound exceeds its limit"
                )
        if self._clock() - self._started >= self.limits.deadline_seconds:
            raise SkillEvaluationBudgetError("evaluation batch deadline reached")
        if self._calls >= self.limits.max_calls:
            raise SkillEvaluationBudgetError("evaluation call budget exhausted")
        if self._trial_calls[trial_id] >= self.limits.max_calls_per_trial:
            raise SkillEvaluationBudgetError("evaluation trial call budget exhausted")

        reserved_cost = 0.0
        if self.route.route.billing not in {"subscription", "local"}:
            try:
                estimate = self._cost_estimator(
                    self.route.provider, self.route.model,
                    input_token_upper_bound, output_token_upper_bound,
                )
            except Exception as exc:
                raise SkillEvaluationBudgetError(
                    "evaluation price estimate is unavailable"
                ) from exc
            if (estimate is None or isinstance(estimate, bool)
                    or not isinstance(estimate, (int, float))
                    or not math.isfinite(estimate) or estimate < 0):
                raise SkillEvaluationBudgetError(
                    "evaluation price estimate is unavailable"
                )
            ceiling = self.limits.spend_ceiling_usd
            if ceiling is None:
                raise SkillEvaluationBudgetError(
                    "paid evaluation requires an explicit spend ceiling"
                )
            reserved_cost = float(estimate)
            if self._reserved_cost_usd + reserved_cost > ceiling:
                raise SkillEvaluationBudgetError(
                    "evaluation spend ceiling would be exceeded"
                )

        self._calls += 1
        self._trial_calls[trial_id] += 1
        self._reserved_cost_usd += reserved_cost
        return SkillEvaluationReservation(
            call_number=self._calls,
            trial_id=trial_id,
            reserved_cost_usd=reserved_cost,
            reserved_total_usd=self._reserved_cost_usd,
        )

    def preflight_calls(
        self,
        planned: tuple[tuple[str, int, int], ...],
    ) -> None:
        """Prove the complete batch fits before starting its first provider call."""
        if not isinstance(planned, tuple) or not planned:
            raise SkillEvaluationBudgetError("evaluation batch has no planned calls")
        if self._calls + len(planned) > self.limits.max_calls:
            raise SkillEvaluationBudgetError("complete evaluation exceeds its call budget")
        per_trial: dict[str, int] = defaultdict(int)
        projected_cost = 0.0
        for trial_id, input_bound, output_bound in planned:
            if not isinstance(trial_id, str) or not re.fullmatch(
                    r"[A-Za-z0-9_-]{1,96}", trial_id):
                raise SkillEvaluationBudgetError("invalid planned evaluation trial ID")
            per_trial[trial_id] += 1
            if per_trial[trial_id] > self.limits.max_calls_per_trial:
                raise SkillEvaluationBudgetError("planned trial exceeds its call budget")
            for name, value, ceiling in (
                ("input", input_bound, self.limits.max_input_tokens_per_call),
                ("output", output_bound, self.limits.max_output_tokens_per_call),
            ):
                if type(value) is not int or value < 1 or value > ceiling:
                    raise SkillEvaluationBudgetError(
                        f"planned evaluation {name} token bound exceeds its limit"
                    )
            if self.route.route.billing in {"subscription", "local"}:
                continue
            try:
                estimate = self._cost_estimator(
                    self.route.provider, self.route.model, input_bound, output_bound,
                )
            except Exception as exc:
                raise SkillEvaluationBudgetError(
                    "evaluation price estimate is unavailable"
                ) from exc
            if (estimate is None or isinstance(estimate, bool)
                    or not isinstance(estimate, (int, float))
                    or not math.isfinite(estimate) or estimate < 0):
                raise SkillEvaluationBudgetError(
                    "evaluation price estimate is unavailable"
                )
            projected_cost += float(estimate)
        if self.route.route.billing not in {"subscription", "local"}:
            ceiling = self.limits.spend_ceiling_usd
            if ceiling is None:
                raise SkillEvaluationBudgetError(
                    "paid evaluation requires an explicit spend ceiling"
                )
            if self._reserved_cost_usd + projected_cost > ceiling:
                raise SkillEvaluationBudgetError(
                    "complete evaluation exceeds its spend ceiling"
                )


@dataclass(frozen=True)
class SkillEvaluationCase:
    """Frozen, non-user fixture used for a paired skill comparison."""

    case_id: str
    prompt: str
    review_criteria: tuple[str, ...] = ()


@dataclass(frozen=True)
class SkillEvaluationTrial:
    """One condition's output, bound to the fixture and condition digest."""

    artifact_id: str
    case_id: str
    condition: str
    repetition: int
    text: str
    result: Any
    review_criteria: tuple[str, ...] = ()
    reserved_cost_usd: float = 0.0


async def run_skill_evaluation(
    cases: tuple[SkillEvaluationCase, ...],
    *,
    skill_instructions: str,
    fixture_id: str | None = None,
    fixture_sha256: str | None = None,
    limits: SkillEvaluationLimits,
    route: ResolvedModelRoute,
    execute: Callable[..., Any],
    budget: SkillEvaluationBudget | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> tuple[SkillEvaluationTrial, ...]:
    """Run a fixed, paired with/without comparison through an injected executor.

    This is intentionally a small host-side orchestration primitive: callers
    must supply the exact approved frozen public/synthetic fixture and the
    existing ``execute_chat`` boundary. Fixture identity and parsed cases are
    revalidated here, rather than trusting a CLI-only gate. It never activates
    a package or grades output.
    Input reservations use a conservative UTF-8 byte bound plus message
    overhead, rather than a caller-supplied token estimate.
    """
    from jarvis.model_execution import (
        ModelExecutionRequest,
        ModelOutputRequirements,
    )
    from jarvis.privacy_policy import DataPolicy

    if not isinstance(cases, tuple) or not 1 <= len(cases) <= limits.max_cases:
        raise ValueError("evaluation requires a fixed tuple within the configured case limit")
    if (not isinstance(skill_instructions, str) or not skill_instructions.strip()
            or len(skill_instructions) > 64_000):
        raise ValueError("candidate skill instructions must be nonempty bounded text")
    if route.workload != "skill_eval":
        raise ValueError("skill evaluation requires the dedicated skill_eval route")
    if route.route.adapter not in {"openai_compatible", "saygm_gateway"}:
        raise ValueError("evaluation route cannot enforce the required output-token cap")
    seen: set[str] = set()
    for case in cases:
        if (not isinstance(case, SkillEvaluationCase)
                or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", case.case_id)
                or case.case_id in seen
                or not isinstance(case.prompt, str) or not case.prompt.strip()
                or len(case.prompt) > 64_000
                or not isinstance(case.review_criteria, tuple)
                or not 1 <= len(case.review_criteria) <= 8
                or any(not isinstance(item, str) or not item.strip()
                       or len(item) > 500 for item in case.review_criteria)):
            raise ValueError("evaluation cases must have unique IDs and bounded prompt text")
        seen.add(case.case_id)

    # This request is approved for external evaluation. Do not trust callers to
    # label arbitrary prompts "public": bind the full case tuple to the exact
    # reviewed fixture bytes before the first executor call.
    require_frozen_skill_evaluation_cases(
        cases, fixture_id=fixture_id, fixture_sha256=fixture_sha256,
        max_cases=limits.max_cases,
    )

    for case in cases:
        upper_bound = (
            len(skill_instructions.encode("utf-8"))
            + len(case.prompt.encode("utf-8"))
            + 2
            + _INPUT_MESSAGE_OVERHEAD_TOKENS
        )
        if upper_bound > limits.max_input_tokens_per_call:
            raise ValueError("fixture input exceeds the configured conservative token bound")

    batch = budget or SkillEvaluationBudget(limits, route, clock=clock)
    planned_trials = []
    for case in cases:
        for repetition in range(1, limits.repetitions + 1):
            paired_conditions = (
                ("with_skill", skill_instructions), ("without_skill", ""),
            )
            # Randomize execution order within each exact pair to avoid always
            # giving one condition the same position in provider-side load or
            # cache conditions. The private condition key records the resulting
            # order; blinded presentation is randomized independently below.
            if secrets.randbelow(2):
                paired_conditions = tuple(reversed(paired_conditions))
            for condition, instructions in paired_conditions:
                trial_id = f"{case.case_id}-{repetition}-{condition}"
                input_bound = (
                    len(instructions.encode("utf-8"))
                    + len(case.prompt.encode("utf-8")) + 2
                    + _INPUT_MESSAGE_OVERHEAD_TOKENS
                )
                planned_trials.append((
                    case, repetition, condition, instructions, trial_id, input_bound,
                ))
    batch.preflight_calls(tuple(
        (trial_id, input_bound, limits.max_output_tokens_per_call)
        for _case, _repetition, _condition, _instructions, trial_id, input_bound
        in planned_trials
    ))
    results: list[SkillEvaluationTrial] = []
    for case, repetition, condition, instructions, trial_id, input_bound in planned_trials:
        # Fixed order and exact paired fixture make results reproducible;
        # the artifact ID is opaque so the later reviewer can be blinded.
        reservation = batch.reserve_call(
            trial_id,
            input_token_upper_bound=input_bound,
            output_token_upper_bound=limits.max_output_tokens_per_call,
        )
        remaining = batch.remaining_seconds()
        if remaining <= 0:
            raise SkillEvaluationBudgetError("evaluation batch deadline reached")
        request = ModelExecutionRequest(
            workload="skill_eval",
            task_id=trial_id,
            parent_request_id="skill-evaluation",
            instructions=(instructions + "\n\n" if instructions else "") + case.prompt,
            context=(),
            tools=(),
            output=ModelOutputRequirements(
                max_tokens=limits.max_output_tokens_per_call,
                require_nonempty_text=True,
            ),
            data_policy=DataPolicy("approved_external", "public-evaluation-fixture"),
            timeout_s=min(remaining, 900),
            temperature=0,
        )
        result = execute(request, route)
        if hasattr(result, "__await__"):
            result = await result
        text = getattr(result, "text", None)
        if not isinstance(text, str) or not text.strip():
            raise SkillEvaluationBudgetError("evaluation executor returned no text")
        # Enforce the artifact bound at the per-call boundary. Waiting until
        # write_blinded_evaluation would allow the remaining paid trials to run
        # even though this batch can no longer produce a valid artifact.
        if len(text) > _MAX_TRIAL_RESPONSE_CHARS:
            raise SkillEvaluationBudgetError(
                "evaluation executor response exceeds the trial artifact limit"
            )
        tool_calls = getattr(result, "tool_calls", None)
        if not isinstance(tool_calls, tuple):
            raise SkillEvaluationBudgetError(
                "evaluation executor did not provide validated tool-call evidence"
            )
        if tool_calls:
            raise SkillEvaluationBudgetError(
                "evaluation executor returned tool calls despite a no-tools request"
            )
        record_skill_evaluation_execution(result)
        results.append(SkillEvaluationTrial(
            artifact_id=secrets.token_urlsafe(18),
            case_id=case.case_id,
            condition=condition,
            repetition=repetition,
            text=text,
            result=result,
            review_criteria=case.review_criteria,
            reserved_cost_usd=reservation.reserved_cost_usd,
        ))
    return tuple(results)


def fixture_digest(path: str | os.PathLike[str]) -> str:
    """Hash exact fixture bytes so results can bind to the frozen source."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_skill_evaluation_cases(
    path: str | os.PathLike[str], *, max_cases: int,
) -> tuple[SkillEvaluationCase, ...]:
    """Load a strict, versioned JSON fixture with review criteria frozen in it."""
    return load_skill_evaluation_fixture(path, max_cases=max_cases)[0]


def load_skill_evaluation_fixture(
    path: str | os.PathLike[str], *, max_cases: int,
    expected_fixture_id: str | None = None,
) -> tuple[tuple[SkillEvaluationCase, ...], str]:
    """Read and validate one fixture snapshot, returning its exact-byte digest."""
    try:
        fixture_path = Path(path)
        size = fixture_path.stat().st_size
    except OSError as exc:
        raise ValueError("evaluation fixture could not be read as JSON") from exc
    if size > _MAX_FIXTURE_BYTES:
        raise ValueError("evaluation fixture exceeds the one-megabyte limit")
    try:
        source = fixture_path.read_bytes()
        payload = json.loads(source.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("evaluation fixture could not be read as JSON") from exc
    if (not isinstance(payload, dict)
            or set(payload) != {"schema_version", "fixture_id", "cases"}
            or type(payload.get("schema_version")) is not int
            or payload.get("schema_version") != 1
            or not isinstance(payload.get("fixture_id"), str)
            or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", payload["fixture_id"])
            or not isinstance(payload.get("cases"), list)
            or not 1 <= len(payload["cases"]) <= max_cases):
        raise ValueError("evaluation fixture schema or case count is invalid")
    if expected_fixture_id is not None and payload["fixture_id"] != expected_fixture_id:
        raise ValueError("evaluation fixture ID does not match its requested identity")
    cases: list[SkillEvaluationCase] = []
    for raw in payload["cases"]:
        if (not isinstance(raw, dict)
                or set(raw) != {"case_id", "prompt", "review_criteria"}
                or not isinstance(raw.get("case_id"), str)
                or not isinstance(raw.get("prompt"), str)
                or not isinstance(raw.get("review_criteria"), list)
                or not 1 <= len(raw["review_criteria"]) <= 8
                or any(not isinstance(item, str) or not item.strip()
                       or len(item) > 500 for item in raw["review_criteria"])):
            raise ValueError("evaluation fixture case is invalid")
        cases.append(SkillEvaluationCase(
            case_id=raw["case_id"], prompt=raw["prompt"],
            review_criteria=tuple(item.strip() for item in raw["review_criteria"]),
        ))
    # Reuse runner validation, including duplicate IDs and prompt bounds.
    seen: set[str] = set()
    for case in cases:
        if (not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", case.case_id)
                or case.case_id in seen or not case.prompt.strip()
                or len(case.prompt) > 64_000):
            raise ValueError("evaluation fixture case IDs or prompt are invalid")
        seen.add(case.case_id)
    return tuple(cases), hashlib.sha256(source).hexdigest()


def write_blinded_evaluation(
    trials: tuple[SkillEvaluationTrial, ...],
    *,
    review_path: str | os.PathLike[str],
    condition_key_path: str | os.PathLike[str],
    metrics_path: str | os.PathLike[str],
    fixture_sha256: str,
    skill_revision: str,
    model_identity: str,
) -> None:
    """Write review outputs and the condition key to separate private locations.

    Files are immutable-create, mode 0600, and never overwrite prior evidence.
    The key path must be in a different directory from the reviewer artifact.
    """
    if (not isinstance(fixture_sha256, str)
            or not re.fullmatch(r"[0-9a-f]{64}", fixture_sha256)):
        raise ValueError("blinded evaluation evidence is incomplete")
    frozen_fixture_id = next((fixture_id for fixture_id, digest
                              in FROZEN_SKILL_EVALUATION_FIXTURE_SHA256.items()
                              if digest == fixture_sha256), None)
    if frozen_fixture_id is None:
        raise ValueError("blinded evaluation requires an approved frozen fixture")
    fixture_path = (
        Path(__file__).resolve().parents[1] / "tests" / "fixtures"
        / "skills_workspace" / "evaluations" / f"{frozen_fixture_id}.json"
    )
    frozen_cases, actual_digest = load_skill_evaluation_fixture(
        fixture_path, max_cases=6, expected_fixture_id=frozen_fixture_id,
    )
    if actual_digest != fixture_sha256:
        raise ValueError("blinded evaluation fixture changed after approval")
    frozen_criteria = {case.case_id: case.review_criteria for case in frozen_cases}
    required_case_ids = set(frozen_criteria)
    if len(trials) != 24:
        raise ValueError("SW-G blinded output requires exactly 24 paired trials")
    for name, value in (("skill revision", skill_revision),
                        ("model identity", model_identity)):
        if not isinstance(value, str) or not value.strip() or len(value) > 256:
            raise ValueError(f"{name} is invalid")
    review = Path(review_path)
    key = Path(condition_key_path)
    metrics_file = Path(metrics_path)
    _require_private_directory(review.parent)
    _require_private_directory(key.parent)
    _require_private_directory(metrics_file.parent)
    if (review.parent.resolve() == key.parent.resolve()
            or review.parent.resolve() == metrics_file.parent.resolve()
            or key.resolve() == metrics_file.resolve()):
        raise ValueError("review artifact and condition key need separate directories")
    artifact_ids = [item.artifact_id for item in trials]
    if len(artifact_ids) != len(set(artifact_ids)):
        raise ValueError("evaluation artifact IDs must be unique")
    paired: dict[tuple[str, int], set[str]] = defaultdict(set)
    for item in trials:
        if (not re.fullmatch(r"[A-Za-z0-9_-]{12,64}", item.artifact_id)
                or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", item.case_id)
                or type(item.repetition) is not int or item.repetition not in {1, 2}
                or item.condition not in {"with_skill", "without_skill"}
                or not isinstance(item.text, str) or not item.text.strip()
                or len(item.text) > _MAX_TRIAL_RESPONSE_CHARS
                or item.case_id not in required_case_ids
                or not isinstance(item.review_criteria, tuple)
                or item.review_criteria != frozen_criteria[item.case_id]):
            raise ValueError("evaluation result contains an invalid trial")
        pair_key = (item.case_id, item.repetition)
        if item.condition in paired[pair_key]:
            raise ValueError("evaluation result contains a duplicate paired condition")
        paired[pair_key].add(item.condition)
    required_pairs = {
        (case_id, repetition)
        for case_id in required_case_ids for repetition in (1, 2)
    }
    if set(paired) != required_pairs or any(
            conditions != {"with_skill", "without_skill"}
            for conditions in paired.values()):
        raise ValueError("SW-G output requires 12 complete frozen case/repetition pairs")
    review_trials = list(trials)
    secrets.SystemRandom().shuffle(review_trials)
    public_payload = {
        "schema_version": 1,
        "fixture_sha256": fixture_sha256,
        "skill_revision": skill_revision,
        "model_identity": model_identity,
        "trials": [{
            "artifact_id": item.artifact_id,
            "case_id": item.case_id,
            "repetition": item.repetition,
            "review_criteria": list(item.review_criteria),
            "text": item.text,
        } for item in review_trials],
    }
    private_payload = {
        "schema_version": 1,
        "conditions": [{
            "artifact_id": item.artifact_id,
            "condition": item.condition,
            "case_id": item.case_id,
            "repetition": item.repetition,
        } for item in trials],
    }
    metrics_payload = {
        "schema_version": 1,
        "calls": [_trial_metrics(item) for item in trials],
    }
    # Bind the private condition key and usage measurements to the blinded
    # artifact that the reviewer rates. These hashes do not reveal conditions.
    public_payload["condition_key_sha256"] = _evidence_digest(private_payload)
    public_payload["metrics_sha256"] = _evidence_digest(metrics_payload)
    created: list[Path] = []
    try:
        _write_private_file(review, public_payload)
        created.append(review)
        _write_private_file(key, private_payload)
        created.append(key)
        _write_private_file(metrics_file, metrics_payload)
        created.append(metrics_file)
    except Exception:
        for created_path in created:
            created_path.unlink(missing_ok=True)
        raise


def _trial_metrics(trial: SkillEvaluationTrial) -> dict[str, Any]:
    result = trial.result
    tokens: dict[str, int | None] = {}
    for output_name, attr in (
        ("input_tokens", "prompt_tokens"), ("output_tokens", "completion_tokens"),
    ):
        value = getattr(result, attr, None)
        tokens[output_name] = value if type(value) is int and value >= 0 else None
    for output_name, attr in (
        ("cache_read_tokens", "cache_read_tokens"),
        ("cache_write_tokens", "cache_write_tokens"),
    ):
        value = getattr(result, attr, None)
        tokens[output_name] = value if type(value) is int and value >= 0 else 0
    duration = getattr(result, "duration_ms", None)
    if (isinstance(duration, bool) or not isinstance(duration, (int, float))
            or not math.isfinite(duration) or duration < 0):
        duration = None
    provider = getattr(result, "provider", None)
    model = getattr(result, "model", None)
    billing = getattr(result, "billing", None)
    route = getattr(result, "route", None)
    actual_cost = None
    cost_basis = "unknown"
    if billing == "subscription":
        cost_basis = "subscription_fixed_fee"
        actual_cost = 0.0
    elif (isinstance(provider, str) and isinstance(model, str)
          and tokens["input_tokens"] is not None
          and tokens["output_tokens"] is not None):
        try:
            from jarvis.usage_ledger import compute_cost
            uncached_input = max(
                0,
                tokens["input_tokens"] - tokens["cache_read_tokens"]
                - tokens["cache_write_tokens"],
            )
            actual_cost = compute_cost(
                provider, model, uncached_input, tokens["output_tokens"],
                tokens["cache_write_tokens"], tokens["cache_read_tokens"],
            )
        except Exception:  # noqa: BLE001 — keep review output when pricing is unavailable
            actual_cost = None
        if actual_cost is not None and math.isfinite(actual_cost) and actual_cost >= 0:
            cost_basis = "price_map_actual_usage"
        else:
            actual_cost = None
    return {
        "artifact_id": trial.artifact_id,
        # The runner admits a trial only after validating ModelExecutionResult
        # carries an empty tool_calls tuple; never infer this from prompt text.
        "tool_call_count": len(result.tool_calls),
        "provider": provider if isinstance(provider, str) else None,
        "model": model if isinstance(model, str) else None,
        "route": route if isinstance(route, str) else None,
        "billing": billing if isinstance(billing, str) else None,
        **tokens,
        "duration_ms": float(duration) if duration is not None else None,
        "reserved_cost_usd": trial.reserved_cost_usd,
        "actual_cost_usd": actual_cost,
        "cost_basis": cost_basis,
    }


def _write_private_file(path: Path, payload: dict[str, Any]) -> None:
    """Create one JSON evidence file without following or replacing a target."""
    if not path.parent.is_dir() or path.parent.is_symlink():
        raise ValueError("evaluation output directory must already exist and be real")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        path.unlink(missing_ok=True)
        raise


def _require_private_directory(path: Path) -> None:
    """Require an existing owner-only writable directory for evaluation data."""
    try:
        info = path.lstat()
    except OSError as exc:
        raise ValueError("evaluation output directories must already exist and be private") from exc
    mode = stat.S_IMODE(info.st_mode)
    if (not stat.S_ISDIR(info.st_mode) or mode & 0o077
            or not mode & 0o200):
        raise ValueError("evaluation output directories must be owner-only and writable")


def _evidence_digest(payload: dict[str, Any]) -> str:
    """Hash canonical JSON so separately carried evidence can be cross-checked."""
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def record_skill_evaluation_execution(result, *, session_id: str | None = None) -> None:
    """Attribute one normalized result to the dedicated usage-ledger rung."""
    from jarvis.usage_ledger import record_execution_result
    record_execution_result("skill_eval", result, session_id=session_id)
