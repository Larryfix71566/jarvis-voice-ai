from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace
import asyncio

import pytest

from scripts import run_model_use_pilot as pilot


def fake_client(text, *, error=None, usage=None):
    async def create(**kwargs):
        if error:
            raise error
        return SimpleNamespace(id=None, choices=[SimpleNamespace(message=SimpleNamespace(
            content=text, tool_calls=[], model_extra={}))], usage=usage)
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


def test_fixture_digest_prevents_unreviewed_case_or_scorer_input_changes(tmp_path, monkeypatch):
    changed = tmp_path / "changed.json"
    changed.write_bytes(pilot.FIXTURE.read_bytes() + b" ")
    monkeypatch.setattr(pilot, "FIXTURE", changed)
    with pytest.raises(pilot.PilotUnavailable, match="digest"):
        pilot.load_fixture()


def test_research_scorer_rejects_wrong_source_boolean_as_number_and_extra_claim():
    data, _ = pilot.load_fixture()
    case = data["cases"][0]
    text = '{"year":2026,"margin_percent":40,"source_id":"A","unknown_customer_count":null}'
    scored = pilot.score_case(case, text)
    assert not scored["passed"]
    assert scored["content_scored"] is True and scored["strict_format_passed"] is True
    assert not pilot.score_case(case, '{"year":true,"margin_percent":40,"source_id":"B","unknown_customer_count":null}')["passed"]
    payload = dict(case["expected"], fabricated="unsupported claim")
    assert not pilot.score_case(case, json.dumps(payload))["passed"]


def test_memory_scorer_inspects_provider_metadata_not_input_text():
    data, _ = pilot.load_fixture()
    case = next(c for c in data["cases"] if c["id"] == "memory-quoted-permission-injection")
    payload = json.loads(pilot._golden_response(case))
    assert pilot.score_case(case, json.dumps(payload))["passed"]
    payload[0]["provenance"] = "user"
    payload[0]["evidence_status"] = "explicit"
    assert not pilot.score_case(case, json.dumps(payload))["passed"]
    payload[0]["credential"] = "secret"
    assert not pilot.score_case(case, json.dumps(payload))["schema_valid"]


async def test_default_dry_uses_real_policy_guards_without_clients(monkeypatch):
    import jarvis.model_routing as routing
    monkeypatch.setattr(routing, "make_route_client", lambda *a, **k: pytest.fail("provider client created"))
    monkeypatch.setattr(routing, "resolve_model_route_checked", lambda *a, **k: pytest.fail("live/catalog resolver called"))
    report = await pilot.run_pilot()
    assert all(row["status"] == "dry_ready_unverified" for row in report["trials"])
    assert report["provider_requests_attempted"] == 0
    assert report["summary"]["completed"] == 0
    assert report["mar_i_complete"] is False


async def test_offline_research_crosses_actual_execution_boundary_with_unknown_usage():
    report = await pilot.run_pilot(mode="offline", group="research")
    assert report["summary"]["completed"] == report["summary"]["passed"] == 3
    for row in report["trials"]:
        assert row["execution_route"] == "direct_api"
        assert row["execution_billing_source"] == "provider_api"
        assert row["usage"]["usage_known"] is False
        assert row["timing"]["queue_ms"] >= 0
        assert row["timing"]["total_ms"] >= row["timing"]["provider_ms"]
    assert report["provider_requests_attempted"] == 0
    assert report["summary"]["sufficient_for_stable_p95_claim"] is False


async def test_confidential_memory_is_blocked_before_client_on_external_route():
    report = await pilot.run_pilot(mode="offline", group="memory",
                                   client_factory=lambda *a: pytest.fail("confidential payload leaked"))
    assert all(row["status"] == "unavailable" for row in report["trials"])
    assert report["summary"]["completed"] == 0


async def test_memory_offline_local_fixture_tests_real_schema_with_protected_policy():
    report = await pilot.run_pilot(mode="offline", group="memory", route="local", max_output_tokens=None)
    assert report["summary"]["completed"] == report["summary"]["passed"] == 4
    assert all(row["result_policy"] == "confidential" for row in report["trials"])
    assert report["provider_requests_attempted"] == 0


async def test_offline_subscription_still_enforces_required_tool_capability():
    # Developer is explicitly held until a genuine sandbox integration exists.
    report = await pilot.run_pilot(mode="offline", group="development", route="subscription",
                                   client_factory=lambda *a: pytest.fail("fake development acceptance"))
    assert report["trials"][0]["reason"] == "sandbox_development_driver_required"
    assert report["summary"]["passed"] == 0


async def test_provider_output_and_error_text_never_enter_receipt():
    marker = "secret-provider-output-sentinel"
    result = await pilot.run_pilot(mode="offline", client_factory=lambda *a: fake_client(marker))
    assert marker not in json.dumps(result)
    assert result["summary"]["passed"] == 0
    result = await pilot.run_pilot(mode="offline", client_factory=lambda *a: fake_client("", error=RuntimeError(marker)))
    assert marker not in json.dumps(result)
    assert all(row["error_category"] == "RuntimeError" for row in result["trials"])


async def test_inherited_production_db_paths_and_preferences_are_overwritten(monkeypatch):
    monkeypatch.setenv("JARVIS_DB_PATH", "/production/jarvis.db")
    monkeypatch.setenv("JARVIS_COSTS_DB", "/production/costs.db")
    monkeypatch.setenv("JARVIS_MODEL_PREFERENCES_ENABLED", "1")
    observed = []
    def factory(resolved, case):
        observed.append((os.environ["JARVIS_DB_PATH"], os.environ["JARVIS_COSTS_DB"], os.environ["JARVIS_MODEL_PREFERENCES_ENABLED"]))
        return fake_client(pilot._golden_response(case))
    await pilot.run_pilot(mode="offline", client_factory=factory)
    assert all("/production/" not in db and "/production/" not in cost and prefs == "0" for db, cost, prefs in observed)
    assert os.environ["JARVIS_DB_PATH"] == "/production/jarvis.db"
    assert os.environ["JARVIS_MODEL_PREFERENCES_ENABLED"] == "1"


@pytest.mark.parametrize("kwargs", [
    {"repetitions": 6}, {"max_calls": 2}, {"max_calls": 33}, {"deadline_s": 301},
    {"timeout_s": 61}, {"max_input_bytes": 0}, {"max_output_tokens": 2001},
    {"max_spend_usd": float("nan")}, {"max_output_tokens": None},
    {"mode": "live"},
])
async def test_invalid_or_insufficient_budget_rejected_before_execution(kwargs, monkeypatch):
    import jarvis.model_routing as routing
    monkeypatch.setattr(routing, "make_route_client", lambda *a, **k: pytest.fail("budget bypassed"))
    with pytest.raises(pilot.PilotUnavailable):
        await pilot.run_pilot(**kwargs)


async def test_live_paid_route_without_budget_never_calls_provider(monkeypatch):
    import jarvis.model_routing as routing
    monkeypatch.setenv("ANTHROPIC_API_KEY", "credential-sentinel")
    monkeypatch.setattr(routing, "make_route_client", lambda *a, **k: pytest.fail("unbudgeted paid request"))
    report = await pilot.run_pilot(mode="live", profile="claude-sonnet-5")
    assert all(row["status"] == "unavailable" for row in report["trials"])
    assert report["provider_requests_attempted"] == 0
    assert "credential-sentinel" not in json.dumps(report)


async def test_live_spend_reservation_stops_before_over_budget_request(monkeypatch):
    import jarvis.model_routing as routing
    monkeypatch.setenv("ANTHROPIC_API_KEY", "credential-sentinel")
    monkeypatch.setattr(pilot, "_reserve_cost", lambda *a: 0.1)
    monkeypatch.setattr(routing, "make_route_client", lambda *a, **k: fake_client(
        '{"year":2026,"margin_percent":40,"source_id":"B","unknown_customer_count":null}'))
    report = await pilot.run_pilot(mode="live", profile="claude-sonnet-5", max_spend_usd=0.15)
    assert report["provider_requests_attempted"] == 1
    assert report["trials"][1]["reason"] == "configured_price_reservation_exceeds_budget"
    assert report["budget"]["configured_price_reserved_usd"] == 0.1


async def test_subscription_unbounded_output_is_explicit_and_marked_unavailable_budget():
    report = await pilot.run_pilot(mode="offline", route="subscription", max_output_tokens=None)
    assert report["budget"]["output_token_budget_available"] is False
    assert report["budget"]["max_output_tokens"] is None
    assert report["provider_requests_attempted"] == 0
    assert report["mar_i_complete"] is False


async def test_timeout_discards_late_response_and_records_no_response_text():
    async def slow(**kwargs):
        await asyncio.sleep(0.1)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="late private sentinel", tool_calls=[]))])
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=slow)))
    report = await pilot.run_pilot(mode="offline", timeout_s=0.01, deadline_s=1,
                                   client_factory=lambda *a: client)
    assert report["summary"]["completed"] == 0
    assert all(row["error_category"] == "TimeoutError" for row in report["trials"])
    assert "late private sentinel" not in json.dumps(report)


async def test_failed_confidential_catalog_preflight_is_cached_once(monkeypatch):
    import jarvis.model_routing as routing
    calls = []
    def unavailable(*a, **k):
        calls.append(1)
        raise routing.ModelRouteError("provider catalog secret sentinel")
    monkeypatch.setattr(routing, "resolve_model_route_checked", unavailable)
    monkeypatch.setattr(routing, "make_route_client", lambda *a, **k: pytest.fail("unqualified confidential inference"))
    report = await pilot.run_pilot(mode="live", group="memory", profile="claude-sonnet-5", route="saygm")
    assert calls == [1]
    assert report["catalog_preflight_attempts"] == 1
    assert report["provider_requests_attempted"] == 0
    assert "secret sentinel" not in json.dumps(report)


def comparison_receipt(*, duration=100, passed=True, mode="live"):
    return {"mode": mode, "fixture_sha256": pilot.FIXTURE_SHA256,
            "scorer_version": pilot.SCORER_VERSION, "group": "research",
            "trials": [{"case_id": "fixture", "repetition": 1, "status": "completed",
                        "timing": {"total_ms": duration}, "quality": {"passed": passed, "content_scored": True}}]}


def test_matching_live_comparison_flags_latency_and_quality_regression_without_acceptance():
    report = pilot.compare_receipts(comparison_receipt(duration=100), comparison_receipt(duration=2201, passed=False))
    assert report["median_delta_ms"] == 2101
    assert report["p95_review_threshold_exceeded"] is True
    assert report["candidate_quality_no_regression"] is False
    assert report["stable_p95_or_rollout_acceptance_claimed"] is False


def test_comparison_rejects_offline_or_mismatched_fixture_evidence():
    with pytest.raises(pilot.PilotUnavailable, match="live"):
        pilot.compare_receipts(comparison_receipt(mode="offline"), comparison_receipt())
    candidate = comparison_receipt()
    candidate["fixture_sha256"] = "changed"
    with pytest.raises(pilot.PilotUnavailable, match="corpus"):
        pilot.compare_receipts(comparison_receipt(), candidate)


@pytest.mark.parametrize("response,reason", [
    ('```json\n{"answer":42}\n```', "markdown_code_fence"),
    ('not valid JSON secret-output-sentinel', "invalid_json"),
    ('[1,2,3]', "unexpected_json_type_or_count"),
])
def test_format_failures_leave_content_unscored_without_saving_it(response, reason):
    data, _ = pilot.load_fixture()
    result = pilot.score_case(data["cases"][0], response)
    assert result["format_failure_reason"] == reason
    assert result["content_scored"] is False
    assert result["strict_format_passed"] is False
    assert "secret-output-sentinel" not in json.dumps(result)


def test_zero_pass_or_invalid_baseline_quality_is_inconclusive_not_no_regression():
    baseline = comparison_receipt(passed=False)
    candidate = comparison_receipt(passed=False)
    baseline["trials"][0]["quality"]["content_scored"] = False
    result = pilot.compare_receipts(baseline, candidate)
    assert result["baseline_gate_failed"] is True
    assert result["quality_comparison_available"] is False
    assert result["candidate_quality_no_regression"] is None


def test_unavailable_baseline_does_not_discard_completed_candidate_receipt(tmp_path, monkeypatch, capsys):
    async def measured(**kwargs):
        return comparison_receipt()
    monkeypatch.setattr(pilot, "run_pilot", measured)
    destination = tmp_path / "candidate.json"
    assert pilot.main(["--mode", "live", "--profile", "claude-sonnet-5",
                       "--baseline-receipt", str(tmp_path / "missing-private-sentinel.json"),
                       "--output", str(destination)]) == 0
    result = json.loads(destination.read_bytes())
    assert result["trials"][0]["status"] == "completed"
    assert result["comparison"]["reason"] == "baseline_receipt_unavailable"
    assert "private-sentinel" not in capsys.readouterr().out
