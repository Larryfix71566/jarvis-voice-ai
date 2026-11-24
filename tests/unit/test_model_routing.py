from pathlib import Path

import pytest
import yaml

from jarvis.model_routing import (
    ModelRouteError,
    available_routes,
    load_skill_evaluation_limits,
    model_profile_for_workload,
    resolve_model_route,
    resolve_policy,
)
from jarvis.saygm import parse_catalog

ROOT = Path(__file__).resolve().parents[2]


def _skill_eval_policy(tmp_path, *, enabled=True, spend_ceiling=1.0,
                       priority="background", fallbacks=None,
                       route="subscription"):
    path = tmp_path / "model-access.yaml"
    path.write_text(yaml.safe_dump({
        "defaults": {"route": route, "fallback_routes": []},
        "routes": {
            "subscription": {
                "adapter": "subscription_runtime", "billing": "subscription",
                "provider": "claude", "privacy": "approved_external",
                "capabilities": ["text", "tools"],
            },
            "saygm": {
                "adapter": "saygm_gateway", "billing": "saygm_credit",
                "credential_env": "SAYGM_API_KEY",
                "base_url": "https://api.saygm.com/v1",
                "privacy": "approved_external",
                "capabilities": ["text", "tools"],
            },
        },
        "workloads": {
            "skill_eval": {
                "profile": "claude-opus", "route": route,
                "privacy": "approved_external", "priority": priority,
                "fallback_routes": fallbacks or [], "capabilities": ["text"],
            },
        },
        "skill_evaluation": {
            "schema_version": 1, "enabled": enabled,
            "max_cases": 6, "repetitions": 2, "max_calls": 96,
            "max_calls_per_trial": 4, "deadline_seconds": 900,
            "max_input_tokens_per_call": 32_000,
            "max_output_tokens_per_call": 4_000,
            "spend_ceiling_usd": spend_ceiling,
        },
    }), encoding="utf-8")
    return path


def test_policy_selection_is_deterministic_and_explicit_override_wins(monkeypatch):
    # direct_api is gone for the Claude profiles (no API key); the explicit
    # route override is exercised on the subscription route instead.
    policy = resolve_policy("developer", explicit_route="subscription")
    route = resolve_model_route("developer", explicit_route="subscription")
    assert policy.route == "subscription"
    assert route.profile_name == "claude-opus"
    assert route.route.name == "subscription"
    assert route.identity == "anthropic/claude-opus-5"
    assert route.priority == "interactive"


def test_streaming_capability_is_explicit_to_verified_direct_profiles(monkeypatch):
    # The subscription routes do not carry streaming (2026-11-23: no direct
    # Claude API); only a verified direct_api profile could advertise it.
    route = resolve_model_route("developer")
    assert "streaming" not in route.route.capabilities
    saygm_route = resolve_model_route(
        "memory", explicit_route="saygm",
        environ={"SAYGM_API_KEY": "synthetic-key"},
        saygm_model=parse_catalog({"data": [{
            "id": "claude-sonnet-5-TEE", "tier": "confidential",
            "api_shapes": ["chat.completions"],
        }]})[0],
    )
    assert "streaming" not in saygm_route.route.capabilities


def test_voice_uses_newest_sonnet_and_old_haiku_builtin_is_gone(monkeypatch):
    # Larry 2026-11-23: voice runs on the newest Sonnet on the subscription.
    assert model_profile_for_workload("voice_supervisor")["model"] == "claude-sonnet-5-5"
    route = resolve_model_route("voice_supervisor")
    assert route.model == "claude-sonnet-5-5"
    assert route.route.name == "subscription"
    assert route.api_key_env is None
    # An old saved or env selection of the Haiku 4.5 builtin now fails loudly.
    for workload in ("voice_supervisor", "developer"):
        with pytest.raises(ModelRouteError, match="unknown model profile"):
            resolve_model_route(workload, explicit_profile="claude-haiku")


def test_vision_workload_requires_image_capability(monkeypatch):
    # The subscription route carries no images, so vision fails closed rather
    # than silently dropping the image requirement.
    with pytest.raises(ModelRouteError, match="lacks required capabilities"):
        resolve_model_route("vision")


def test_unknown_workload_fails_closed():
    with pytest.raises(ModelRouteError, match="unknown workload"):
        resolve_policy("not-a-workload")


@pytest.mark.usefixtures("subscription_without_carry")
def test_confidential_workload_cannot_use_external_default(monkeypatch):
    with pytest.raises(ModelRouteError, match="requires confidential"):
        resolve_model_route("memory", explicit_route="subscription")
    # direct_api is not even offered for a keyless Claude profile.
    with pytest.raises(ModelRouteError, match="does not offer route 'direct_api'"):
        resolve_model_route("memory", explicit_route="direct_api")


def test_missing_route_credential_fails_closed(monkeypatch):
    monkeypatch.delenv("SAYGM_API_KEY", raising=False)
    from jarvis.model_routing import resolve_model_route_checked
    with pytest.raises(ModelRouteError, match="requires SAYGM_API_KEY"):
        resolve_model_route_checked("developer", explicit_route="saygm", environ={})


def test_profile_routes_are_reported_without_credentials():
    profile = {"api_key_env": "SECRET", "routes": {"saygm": {}}}
    assert available_routes(profile) == ["direct_api", "saygm"]


def test_saygm_catalog_can_upgrade_route_to_confidential(monkeypatch):
    monkeypatch.setenv("SAYGM_API_KEY", "gm-key")
    catalog = parse_catalog({"data": [{
        "id": "claude-opus-5-TEE", "tier": "confidential",
        "gateway_provider": "chutes",
        "api_shapes": ["chat.completions"],
    }]})
    route = resolve_model_route("planning", explicit_profile="claude-opus", explicit_route="saygm",
                               saygm_model=catalog[0])
    assert route.route.privacy == "confidential"
    assert route.model == "claude-opus-5-TEE"
    assert route.route.capabilities == ("text",)


def test_confidential_memory_requires_catalog_proof(monkeypatch):
    monkeypatch.setenv("SAYGM_API_KEY", "gm-key")
    catalog = parse_catalog({"data": [{
        "id": "claude-sonnet-5-TEE", "tier": "confidential",
        "api_shapes": ["chat.completions"],
    }]})
    route = resolve_model_route("memory", explicit_route="saygm",
                               saygm_model=catalog[0])
    assert route.route.privacy == "confidential"
    assert route.priority == "background"


def test_checked_route_fetches_catalog_only_for_confidential_saygm(monkeypatch):
    monkeypatch.setenv("SAYGM_API_KEY", "gm-key")
    catalog = parse_catalog({"data": [{"id": "claude-sonnet-5-TEE", "tier": "confidential",
                                       "api_shapes": ["chat.completions"]}]})
    monkeypatch.setattr("jarvis.saygm.fetch_catalog", lambda **_: catalog)
    route = __import__("jarvis.model_routing", fromlist=["resolve_model_route_checked"]).resolve_model_route_checked(
        "memory", explicit_route="saygm")
    assert route.route.privacy == "confidential"


def test_checked_route_does_not_fall_back_to_process_key_for_explicit_environment(
    monkeypatch,
):
    monkeypatch.setenv("SAYGM_API_KEY", "ambient-key-must-not-be-used")
    catalog_calls = []

    def fetch_catalog(**kwargs):
        catalog_calls.append(kwargs)
        return []

    monkeypatch.setattr("jarvis.saygm.fetch_catalog", fetch_catalog)
    from jarvis.model_routing import resolve_model_route_checked

    with pytest.raises(ModelRouteError, match="requires SAYGM_API_KEY"):
        resolve_model_route_checked(
            "memory", explicit_route="saygm", environ={}
        )

    assert catalog_calls == []


def test_skill_evaluation_is_disabled_without_both_explicit_gates(
    monkeypatch, tmp_path,
):
    from jarvis.model_routing import ModelRouteError

    path = _skill_eval_policy(tmp_path)
    monkeypatch.delenv("JARVIS_SKILL_EVAL_ENABLED", raising=False)
    with pytest.raises(ModelRouteError, match="skill evaluation is disabled"):
        resolve_policy("skill_eval", path=path)

    monkeypatch.setenv("JARVIS_SKILL_EVAL_ENABLED", "1")
    disabled_path = _skill_eval_policy(tmp_path, enabled=False)
    with pytest.raises(ModelRouteError, match="skill evaluation is disabled"):
        resolve_policy("skill_eval", path=disabled_path)


def test_current_model_access_policy_has_no_skill_eval_configuration(monkeypatch):
    from jarvis.model_routing import ModelRouteError

    assert load_skill_evaluation_limits() is None
    monkeypatch.setenv("JARVIS_SKILL_EVAL_ENABLED", "1")
    with pytest.raises(ModelRouteError, match="skill evaluation is disabled"):
        resolve_policy("skill_eval")


def test_skill_evaluation_route_requires_budget_and_background_no_fallback(
    monkeypatch, tmp_path,
):
    from jarvis.model_routing import ModelRouteError

    monkeypatch.setenv("JARVIS_SKILL_EVAL_ENABLED", "1")
    monkeypatch.setenv("JARVIS_MODEL_PREFERENCES_ENABLED", "0")
    monkeypatch.delenv("JARVIS_MODEL_PROFILE_SKILL_EVAL", raising=False)
    monkeypatch.delenv("JARVIS_MODEL_ROUTE_SKILL_EVAL", raising=False)
    # A paid route (saygm credit) still needs a spend ceiling; the
    # subscription route is exempt.
    missing_spend = _skill_eval_policy(tmp_path, spend_ceiling=None, route="saygm")
    with pytest.raises(ModelRouteError, match="requires an explicit spend ceiling"):
        resolve_model_route(
            "skill_eval", policy_path=missing_spend,
            environ={"SAYGM_API_KEY": "synthetic-key"},
        )

    interactive = _skill_eval_policy(tmp_path, priority="interactive")
    with pytest.raises(ModelRouteError, match="background priority with no fallback"):
        resolve_policy("skill_eval", path=interactive)

    fallback = _skill_eval_policy(tmp_path, fallbacks=["saygm"])
    with pytest.raises(ModelRouteError, match="background priority with no fallback"):
        resolve_policy("skill_eval", path=fallback)

    monkeypatch.setenv("JARVIS_MODEL_ROUTE_SKILL_EVAL", "saygm")
    with pytest.raises(ModelRouteError, match="route overrides are not allowed"):
        resolve_policy("skill_eval", path=_skill_eval_policy(tmp_path))


def test_skill_evaluation_uses_only_its_reviewed_background_route(
    monkeypatch, tmp_path,
):
    monkeypatch.setenv("JARVIS_SKILL_EVAL_ENABLED", "1")
    monkeypatch.setenv("JARVIS_MODEL_PREFERENCES_ENABLED", "1")
    monkeypatch.delenv("JARVIS_MODEL_PROFILE_SKILL_EVAL", raising=False)
    monkeypatch.delenv("JARVIS_MODEL_ROUTE_SKILL_EVAL", raising=False)
    path = _skill_eval_policy(tmp_path)
    route = resolve_model_route(
        "skill_eval", policy_path=path,
        environ={},
    )
    assert route.profile_name == "claude-opus"
    assert route.route.billing == "subscription"
    assert route.priority == "background"
    assert route.workload == "skill_eval"


def test_skill_evaluation_budget_fields_have_hard_ceilings(monkeypatch, tmp_path):
    from jarvis.model_routing import ModelRouteError

    monkeypatch.setenv("JARVIS_SKILL_EVAL_ENABLED", "1")
    path = _skill_eval_policy(tmp_path)
    assert load_skill_evaluation_limits(path).max_calls == 96
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    raw["skill_evaluation"]["max_calls"] = 97
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(ModelRouteError, match="max_calls is outside its limit"):
        load_skill_evaluation_limits(path)
