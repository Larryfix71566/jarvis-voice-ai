from dataclasses import FrozenInstanceError, fields
from pathlib import Path
from types import MappingProxyType

import pytest
import yaml

from jarvis.model_routing import (
    AccessRoute,
    ModelRouteError,
    ResolvedModelRoute,
    WorkloadLimits,
    WorkloadPolicy,
    describe_route_choice,
    resolve_model_route,
    resolve_policy,
    workload_limits_from_policy,
)


ROOT = Path(__file__).resolve().parents[2]
LIMIT_VALUES = {
    "max_output_tokens_per_call": 512,
    "deadline_seconds": 12.5,
    "max_estimated_spend_usd_per_task": 0.75,
}


def _access_config():
    data = yaml.safe_load((ROOT / "config/model_access.yaml").read_text(encoding="utf-8"))
    data["defaults"].update(LIMIT_VALUES)
    return data


def _write_policy(tmp_path, data):
    path = tmp_path / "model_access.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


@pytest.mark.parametrize("value", [True, False, 0, -1, 32_001, 1.0, "512", [], {}])
def test_output_limit_rejects_unsupported_values_at_construction_and_resolution(value):
    with pytest.raises(ModelRouteError, match="max_output_tokens_per_call"):
        WorkloadLimits(max_output_tokens_per_call=value)
    raw = _access_config()
    raw["workloads"]["analyst"]["max_output_tokens_per_call"] = value
    with pytest.raises(ModelRouteError, match="max_output_tokens_per_call"):
        resolve_policy("analyst", access_config=raw, include_preferences=False)


@pytest.mark.parametrize("name", ["deadline_seconds", "max_estimated_spend_usd_per_task"])
@pytest.mark.parametrize("value", [
    True, False, 0, -1, float("nan"), float("inf"), float("-inf"),
    "12", [], {}, 10 ** 400,
])
def test_duration_and_spend_limits_reject_invalid_values_at_all_entry_points(name, value):
    with pytest.raises(ModelRouteError, match=name):
        WorkloadLimits(**{name: value})
    with pytest.raises(ModelRouteError, match=name):
        workload_limits_from_policy({name: value})
    raw = _access_config()
    raw["workloads"]["analyst"][name] = value
    with pytest.raises(ModelRouteError, match=name):
        resolve_policy("analyst", access_config=raw, include_preferences=False)


@pytest.mark.parametrize("raw", [None, [], True])
def test_limit_helper_requires_a_mapping(raw):
    with pytest.raises(ModelRouteError, match="policy must be a mapping"):
        workload_limits_from_policy(raw)


def test_limit_helper_accepts_merged_read_only_policy_and_supported_boundary_values():
    raw = MappingProxyType({
        "profile": "claude-sonnet-5", "max_output_tokens_per_call": 32_000,
        "deadline_seconds": 0.125, "max_estimated_spend_usd_per_task": 1,
    })
    assert workload_limits_from_policy(raw) == WorkloadLimits(32_000, 0.125, 1)
    assert WorkloadLimits(max_output_tokens_per_call=1).max_output_tokens_per_call == 1


def test_absent_and_explicit_null_limits_retain_existing_policy_behavior():
    raw = _access_config()
    for key in LIMIT_VALUES:
        raw["defaults"].pop(key)
    absent = resolve_policy("analyst", access_config=raw, include_preferences=False)
    raw["workloads"]["analyst"].update(dict.fromkeys(LIMIT_VALUES))
    unset = resolve_policy("analyst", access_config=raw, include_preferences=False)
    assert absent == unset
    assert absent.limits == WorkloadLimits()


def test_workload_values_override_defaults_and_null_clears_only_its_inherited_limit():
    raw = _access_config()
    raw["workloads"]["analyst"].update({
        "max_output_tokens_per_call": 256,
        "deadline_seconds": None,
    })
    policy = resolve_policy("analyst", access_config=raw, include_preferences=False)
    assert policy.limits == WorkloadLimits(256, None, 0.75)


def test_preferences_and_explicit_route_choices_cannot_replace_configured_limits(monkeypatch):
    raw = _access_config()
    monkeypatch.setenv("JARVIS_MODEL_PREFERENCES_ENABLED", "1")
    monkeypatch.setattr("jarvis.model_preferences.list_preferences", lambda: [{
        "workload": "analyst", "profile": "claude-opus", "route": "direct_api",
        "privacy": "approved_external", "max_output_tokens_per_call": None,
        "deadline_seconds": None, "max_estimated_spend_usd_per_task": None,
        "limits": WorkloadLimits(),
    }])
    saved = resolve_policy("analyst", access_config=raw)
    explicit = resolve_policy(
        "analyst", access_config=raw, explicit_profile="claude-sonnet-5",
        explicit_route="direct_api",
    )
    assert saved.profile == "claude-opus"
    assert explicit.profile == "claude-sonnet-5"
    assert saved.limits == explicit.limits == WorkloadLimits(**LIMIT_VALUES)
    assert explicit.minimum_quality_tier == saved.minimum_quality_tier == "mid"
    assert explicit.privacy == saved.privacy == "approved_external"
    assert explicit.fallback_routes == saved.fallback_routes == ()


def test_environment_overrides_preserve_configured_limits(monkeypatch):
    monkeypatch.setenv("JARVIS_MODEL_PROFILE_ANALYST", "claude-opus")
    monkeypatch.setenv("JARVIS_MODEL_ROUTE_ANALYST", "subscription")
    policy = resolve_policy("analyst", access_config=_access_config(), include_preferences=False)
    assert policy.profile == "claude-opus"
    assert policy.route == "subscription"
    assert policy.limits == WorkloadLimits(**LIMIT_VALUES)


def test_resolved_route_snapshots_limits_without_starting_a_task_deadline(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_MODEL_PREFERENCES_ENABLED", "0")
    data = _access_config()
    path = _write_policy(tmp_path, data)
    resolved = resolve_model_route(
        "analyst", policy_path=path, environ={"ANTHROPIC_API_KEY": "synthetic-key"},
    )
    assert resolved.limits == WorkloadLimits(**LIMIT_VALUES)
    assert {item.name for item in fields(resolved.limits)} == set(LIMIT_VALUES)
    data["defaults"]["deadline_seconds"] = 1
    _write_policy(tmp_path, data)
    assert resolved.limits.deadline_seconds == 12.5
    with pytest.raises(FrozenInstanceError):
        resolved.limits.deadline_seconds = 1


def test_native_route_selection_preserves_limits_for_execution_to_enforce(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_MODEL_PREFERENCES_ENABLED", "0")
    data = _access_config()
    data["workloads"]["analyst"]["capabilities"] = ["text"]
    path = _write_policy(tmp_path, data)
    resolved = resolve_model_route(
        "analyst", explicit_route="subscription", policy_path=path, environ={},
    )
    assert resolved.route.name == "subscription"
    assert resolved.limits == WorkloadLimits(**LIMIT_VALUES)
    assert resolved.api_key_env is None


def test_descriptor_publishes_limits_without_account_or_billing_evidence():
    choice = describe_route_choice(
        "analyst", "claude-sonnet-5", "direct_api", access_config=_access_config(),
        environ={"ANTHROPIC_API_KEY": "secret-must-not-be-displayed"},
    )
    assert choice["compatible"] is True
    assert choice["limits"] == LIMIT_VALUES
    assert "secret-must-not-be-displayed" not in repr(choice)
    assert "provider_bill_or_allowance_verified" not in choice


@pytest.mark.parametrize("value", [None, {}, {"deadline_seconds": 5}])
def test_direct_policy_and_resolved_route_construction_require_typed_limits(value):
    with pytest.raises(ModelRouteError, match="validated WorkloadLimits"):
        WorkloadPolicy(
            "analyst", "claude-sonnet-5", "direct_api", "approved_external", "interactive",
            limits=value,
        )
    route = AccessRoute("direct_api", "openai_compatible", "provider_api", "KEY", "approved_external")
    with pytest.raises(ModelRouteError, match="validated WorkloadLimits"):
        ResolvedModelRoute(
            "analyst", "claude-sonnet-5", "claude-sonnet-5", "anthropic", "https://example.com",
            route, "KEY", "anthropic/claude-sonnet-5", limits=value,
        )
