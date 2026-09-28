import hashlib
import json
from pathlib import Path

import pytest

from jarvis.skill_evaluation import (
    FROZEN_SKILL_EVALUATION_FIXTURE_SHA256,
    load_skill_evaluation_fixture,
)
from jarvis.skill_evaluation_review import (
    SkillEvaluationReviewError,
    prepare_human_review,
    score_human_review,
)

_CASES = (
    "create-new-skill", "improve-existing-skill", "ambiguous-scope",
    "reuse-existing-skill", "malicious-resource-content", "missing-dependency",
)


def _artifacts(*, candidate_passes=10, baseline_passes=9,
               unsafe_candidate=False, unknown_cost=False):
    fixture_id, fixture_sha256 = next(iter(
        FROZEN_SKILL_EVALUATION_FIXTURE_SHA256.items(),
    ))
    frozen_cases, actual_digest = load_skill_evaluation_fixture(
        Path(__file__).resolve().parents[1]
        / "fixtures" / "skills_workspace" / "evaluations" / f"{fixture_id}.json",
        max_cases=6, expected_fixture_id=fixture_id,
    )
    assert actual_digest == fixture_sha256
    criteria_by_case = {case.case_id: list(case.review_criteria) for case in frozen_cases}
    trials = []
    conditions = []
    metrics = []
    expected_conditions = {}
    quality_outcomes = {}
    for case_index, case_id in enumerate(_CASES):
        for repetition in (1, 2):
            pair_index = case_index * 2 + repetition - 1
            for condition in ("with_skill", "without_skill"):
                artifact_id = f"artifact_{case_index}_{repetition}_{condition}"
                expected_conditions[artifact_id] = condition
                quality_outcomes[artifact_id] = (
                    pair_index < (candidate_passes if condition == "with_skill"
                                  else baseline_passes)
                )
                trials.append({
                    "artifact_id": artifact_id,
                    "case_id": case_id,
                    "repetition": repetition,
                    "review_criteria": criteria_by_case[case_id],
                    "text": f"Answer {artifact_id}",
                })
                conditions.append({
                    "artifact_id": artifact_id,
                    "condition": condition,
                    "case_id": case_id,
                    "repetition": repetition,
                })
                metrics.append({
                    "artifact_id": artifact_id,
                    "provider": "anthropic",
                    "model": "claude-sonnet",
                    "route": "direct_api",
                    "billing": "provider_api",
                    "input_tokens": 20,
                    "output_tokens": 10,
                    "tool_call_count": 0,
                    "duration_ms": 10.0 + pair_index,
                    "actual_cost_usd": None if unknown_cost else 0.01,
                    "reserved_cost_usd": 0.02,
                    "cost_basis": "unknown" if unknown_cost else "price_map_actual_usage",
                })
    condition_key = {
        "schema_version": 1, "conditions": conditions,
    }
    metrics_artifact = {"schema_version": 1, "calls": metrics}
    def evidence_digest(payload):
        canonical = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    review = {
        "schema_version": 1,
        "fixture_sha256": fixture_sha256,
        "skill_revision": "b" * 64,
        "model_identity": "fake-model-route",
        "condition_key_sha256": evidence_digest(condition_key),
        "metrics_sha256": evidence_digest(metrics_artifact),
        "trials": trials,
    }
    review_bytes = json.dumps(review, sort_keys=True).encode()
    ratings = prepare_human_review(review_bytes)
    ratings["reviewer"] = "reviewer-1"
    for row in ratings["ratings"]:
        condition = expected_conditions[row["artifact_id"]]
        case_id = next(item["case_id"] for item in trials
                       if item["artifact_id"] == row["artifact_id"])
        pass_all_criteria = not (
            unsafe_candidate and condition == "with_skill"
            and case_id == "malicious-resource-content"
        )
        for criterion in row["rubric"]:
            criterion["passed"] = pass_all_criteria
        row["task_quality_pass"] = quality_outcomes[row["artifact_id"]]
    return review_bytes, ratings, condition_key, metrics_artifact


def test_human_scoring_rejects_review_criteria_detached_from_frozen_fixture():
    review, ratings, key, metrics = _artifacts()
    payload = json.loads(review)
    payload["trials"][0]["review_criteria"][0] = "Caller supplied a different rubric."
    review = json.dumps(payload, sort_keys=True).encode()
    ratings = prepare_human_review(review)
    ratings["reviewer"] = "reviewer-1"
    for row in ratings["ratings"]:
        for criterion in row["rubric"]:
            criterion["passed"] = True
        row["task_quality_pass"] = True

    with pytest.raises(SkillEvaluationReviewError, match="rubric differs"):
        score_human_review(
            review_bytes=review, ratings=ratings, condition_key=key, metrics=metrics,
        )


@pytest.mark.parametrize("field,value", [
    ("skill_revision", "not-a-digest"),
    ("model_identity", ""),
])
def test_human_scoring_rejects_invalid_review_identity(field, value):
    review, ratings, key, metrics = _artifacts()
    payload = json.loads(review)
    payload[field] = value
    review = json.dumps(payload, sort_keys=True).encode()
    ratings = prepare_human_review(review)
    ratings["reviewer"] = "reviewer-1"
    for row in ratings["ratings"]:
        for criterion in row["rubric"]:
            criterion["passed"] = True
        row["task_quality_pass"] = True

    with pytest.raises(SkillEvaluationReviewError, match="identity is invalid"):
        score_human_review(
            review_bytes=review, ratings=ratings, condition_key=key, metrics=metrics,
        )


def test_human_scoring_enforces_blind_acceptance_and_reports_metrics():
    review, ratings, key, metrics = _artifacts()
    result = score_human_review(
        review_bytes=review, ratings=ratings, condition_key=key, metrics=metrics,
    )
    assert result["accepted_for_maintainer_review"] is True
    assert result["candidate_quality_passes"] == 10
    assert result["baseline_quality_passes"] == 9
    assert result["metrics_by_condition"]["with_skill"]["call_count"] == 12
    assert result["metrics_by_condition"]["without_skill"]["actual_cost_usd"] == pytest.approx(0.12)
    assert result["reviewed_safety_rubric_pass"] is True
    assert result["no_tool_execution"] is True
    assert result["same_route_across_conditions"] is True


def test_rating_form_includes_exact_blinded_responses_for_review():
    review, ratings, key, metrics = _artifacts()
    review_payload = json.loads(review)
    expected_text = {
        trial["artifact_id"]: trial["text"] for trial in review_payload["trials"]
    }
    assert {
        row["artifact_id"]: row["response_text"] for row in ratings["ratings"]
    } == expected_text
    # Keeping a copied response in the human-edited form must not make the
    # review artifact editable or permit scoring a different response.
    ratings["reviewer"] = "reviewer-1"
    for row in ratings["ratings"]:
        row["response_text"] += " edited"
        for criterion in row["rubric"]:
            criterion["passed"] = True
        row["task_quality_pass"] = True
    with pytest.raises(SkillEvaluationReviewError, match="rating row is invalid"):
        score_human_review(
            review_bytes=review, ratings=ratings, condition_key=key, metrics=metrics,
        )


def test_human_scoring_rejects_paired_arms_from_different_routes():
    review, ratings, key, metrics = _artifacts()
    conditions = {row["artifact_id"]: row["condition"] for row in key["conditions"]}
    for row in metrics["calls"]:
        if conditions[row["artifact_id"]] == "with_skill":
            row.update({
                "provider": "openai",
                "model": "gpt-test",
                "route": "subscription_runtime",
                "billing": "subscription",
                "actual_cost_usd": 0.0,
                "reserved_cost_usd": 0.0,
                "cost_basis": "subscription_fixed_fee",
            })
    review_payload = json.loads(review)
    review_payload["metrics_sha256"] = hashlib.sha256(json.dumps(
        metrics, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode()).hexdigest()
    review = json.dumps(review_payload, sort_keys=True).encode()
    ratings = prepare_human_review(review)
    ratings["reviewer"] = "reviewer-1"
    for row in ratings["ratings"]:
        for criterion in row["rubric"]:
            criterion["passed"] = True
        row["task_quality_pass"] = True

    result = score_human_review(
        review_bytes=review, ratings=ratings, condition_key=key, metrics=metrics,
    )
    assert result["metrics_by_condition"]["with_skill"]["complete"] is True
    assert result["metrics_by_condition"]["without_skill"]["complete"] is True
    assert result["same_route_across_conditions"] is False
    assert result["metrics_complete"] is False
    assert result["accepted_for_maintainer_review"] is False


def test_human_scoring_requires_digest_bound_complete_ratings():
    review, ratings, key, metrics = _artifacts()
    ratings["review_sha256"] = "0" * 64
    with pytest.raises(SkillEvaluationReviewError, match="do not bind"):
        score_human_review(
            review_bytes=review, ratings=ratings, condition_key=key, metrics=metrics,
        )


def test_human_scoring_rejects_candidate_safety_rubric_failure_even_when_quality_passes():
    review, ratings, key, metrics = _artifacts(unsafe_candidate=True)
    result = score_human_review(
        review_bytes=review, ratings=ratings, condition_key=key, metrics=metrics,
    )
    assert result["candidate_quality_passes"] == 10
    assert result["reviewed_safety_rubric_pass"] is False
    assert result["accepted_for_maintainer_review"] is False


@pytest.mark.parametrize("tool_call_count", [1, None])
def test_human_scoring_requires_validated_zero_tool_call_counts(tool_call_count):
    review, ratings, key, metrics = _artifacts()
    metrics["calls"][0]["tool_call_count"] = tool_call_count
    # The review binds exact metrics bytes, so update the binding to model a
    # correctly paired artifact whose runner evidence itself is unsafe/invalid.
    review_payload = json.loads(review)
    review_payload["metrics_sha256"] = hashlib.sha256(json.dumps(
        metrics, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode()).hexdigest()
    review = json.dumps(review_payload, sort_keys=True).encode()
    ratings = prepare_human_review(review)
    ratings["reviewer"] = "reviewer-1"
    for row in ratings["ratings"]:
        for criterion in row["rubric"]:
            criterion["passed"] = True
        row["task_quality_pass"] = True

    result = score_human_review(
        review_bytes=review, ratings=ratings, condition_key=key, metrics=metrics,
    )
    assert result["no_tool_execution"] is False
    assert result["accepted_for_maintainer_review"] is False


@pytest.mark.parametrize("mutation", ["unknown_basis", "subscription_basis_mismatch"])
def test_human_scoring_rejects_inconsistent_cost_evidence(mutation):
    review, ratings, key, metrics = _artifacts()
    if mutation == "unknown_basis":
        # Numeric amounts alone are not enough to establish complete cost
        # evidence; the runner's unknown pricing state must fail closed.
        metrics["calls"][0]["cost_basis"] = "unknown"
    else:
        # Subscription calls have a fixed-fee basis and zero incremental cost
        # and reservation. A price-map label cannot stand in for that proof.
        for row in metrics["calls"]:
            row.update({
                "billing": "subscription",
                "actual_cost_usd": 0.0,
                "reserved_cost_usd": 0.0,
                "cost_basis": "price_map_actual_usage",
            })
    review_payload = json.loads(review)
    review_payload["metrics_sha256"] = hashlib.sha256(json.dumps(
        metrics, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode()).hexdigest()
    review = json.dumps(review_payload, sort_keys=True).encode()
    ratings = prepare_human_review(review)
    ratings["reviewer"] = "reviewer-1"
    for row in ratings["ratings"]:
        for criterion in row["rubric"]:
            criterion["passed"] = True
        row["task_quality_pass"] = True

    result = score_human_review(
        review_bytes=review, ratings=ratings, condition_key=key, metrics=metrics,
    )
    assert result["metrics_complete"] is False
    assert result["accepted_for_maintainer_review"] is False


def test_human_scoring_rejects_worse_than_baseline_and_unknown_cost():
    review, ratings, key, metrics = _artifacts(candidate_passes=9, baseline_passes=10,
                                                unknown_cost=True)
    result = score_human_review(
        review_bytes=review, ratings=ratings, condition_key=key, metrics=metrics,
    )
    assert result["candidate_no_worse_than_baseline"] is False
    assert result["metrics_complete"] is False
    assert result["accepted_for_maintainer_review"] is False


def test_human_scoring_treats_missing_token_usage_as_incomplete_metrics():
    review, ratings, key, metrics = _artifacts()
    metrics["calls"][0].pop("input_tokens")
    review_payload = json.loads(review)
    review_payload["metrics_sha256"] = hashlib.sha256(json.dumps(
        metrics, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode()).hexdigest()
    review = json.dumps(review_payload, sort_keys=True).encode()
    ratings = prepare_human_review(review)
    ratings["reviewer"] = "reviewer-1"
    for row in ratings["ratings"]:
        for criterion in row["rubric"]:
            criterion["passed"] = True
        row["task_quality_pass"] = True

    result = score_human_review(
        review_bytes=review, ratings=ratings, condition_key=key, metrics=metrics,
    )
    assert result["metrics_complete"] is False
    assert result["metrics_by_condition"]["with_skill"]["token_usage_complete"] is False
    assert result["accepted_for_maintainer_review"] is False


def test_human_scoring_rejects_incomplete_trial_set():
    review, ratings, key, metrics = _artifacts()
    import json

    payload = json.loads(review)
    payload["trials"].pop()
    review = json.dumps(payload).encode()
    ratings["review_sha256"] = hashlib.sha256(review).hexdigest()
    with pytest.raises(SkillEvaluationReviewError, match="24 blinded"):
        score_human_review(
            review_bytes=review, ratings=ratings,
            condition_key=key, metrics=metrics,
        )


@pytest.mark.parametrize("evidence", ["condition_key", "metrics"])
def test_human_scoring_rejects_evidence_detached_from_blinded_review(evidence):
    review, ratings, key, metrics = _artifacts()
    if evidence == "condition_key":
        key["conditions"][0]["condition"] = (
            "without_skill" if key["conditions"][0]["condition"] == "with_skill"
            else "with_skill"
        )
    else:
        metrics["calls"][0]["duration_ms"] += 1
    with pytest.raises(SkillEvaluationReviewError, match="does not bind|do not bind"):
        score_human_review(
            review_bytes=review, ratings=ratings, condition_key=key, metrics=metrics,
        )
