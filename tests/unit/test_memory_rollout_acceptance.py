"""B9 staged-rollout, monitoring, and first-20 review acceptance tests."""

from copy import deepcopy
import json
from pathlib import Path

import pytest

from jarvis.memory_automation_eval import evaluate_rollout_gate


FIXTURE = Path(__file__).parents[1] / "fixtures" / "memory_rollout_acceptance.json"


def _payload() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_rollout_fixture_passes_all_b9_gates():
    receipt = evaluate_rollout_gate(_payload())
    assert receipt.passed
    assert receipt.stage_order_ok
    assert receipt.first_review_ok
    assert receipt.benefit_ok and receipt.safety_ok and receipt.budget_ok
    assert receipt.p95_latency_ms == 210
    assert receipt.cost_limit_usd == pytest.approx(0.04)
    assert receipt.violations == ()


def test_first_twenty_requires_review_and_reversible_decisions():
    payload = _payload()
    payload["first_20"][7]["reviewed"] = False
    payload["first_20"][12]["reversible"] = False
    receipt = evaluate_rollout_gate(payload)
    assert not receipt.passed
    assert not receipt.first_review_ok
    assert "unreviewed:decision-08" in receipt.violations
    assert "irreversible:decision-13" in receipt.violations


def test_rollout_stage_order_is_fixed():
    payload = _payload()
    payload["stages"] = [payload["stages"][1], payload["stages"][0], payload["stages"][2]]
    receipt = evaluate_rollout_gate(payload)
    assert not receipt.stage_order_ok
    assert "stage_order" in receipt.violations


def test_each_rollout_stage_requires_its_observation_day():
    payload = _payload()
    payload["stages"][0]["observed_days"] = 0
    receipt = evaluate_rollout_gate(payload)
    assert not receipt.stage_order_ok
    assert "stage_duration:shadow" in receipt.violations


def test_quality_and_cost_regressions_block_enablement():
    payload = _payload()
    payload["candidate"]["relevant_recall"] = 5
    payload["candidate"]["cost_usd"] = 0.51
    receipt = evaluate_rollout_gate(payload)
    assert not receipt.benefit_ok
    assert "quality_regression:relevant_recall" in receipt.violations
    assert "cost_limit" in receipt.violations


def test_privacy_duplicate_and_budget_regressions_block_enablement():
    payload = _payload()
    payload["candidate"]["privacy_regressions"] = 1
    payload["candidate"]["duplicate_durable_rows"] = 1
    payload["candidate"]["model_calls"] = 6
    payload["candidate"]["admission_latencies_ms"][-1] = 2501
    receipt = evaluate_rollout_gate(payload)
    assert not receipt.passed
    assert not receipt.safety_ok and not receipt.budget_ok
    assert "safety:privacy_regressions" in receipt.violations
    assert "safety:duplicate_durable_rows" in receipt.violations
    assert "model_call_budget" in receipt.violations
    assert "admission_p95" in receipt.violations


def test_rollout_evaluator_rejects_nonfinite_measurements():
    payload = deepcopy(_payload())
    payload["candidate"]["admission_latencies_ms"][0] = float("nan")
    with pytest.raises(ValueError, match="finite"):
        evaluate_rollout_gate(payload)
