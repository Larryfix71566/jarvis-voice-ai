from pathlib import Path

import pytest

from jarvis.model_routing import (
    ModelRouteError,
    available_routes,
    model_profile_for_workload,
    resolve_model_route,
    resolve_policy,
)
from jarvis.saygm import parse_catalog

ROOT = Path(__file__).resolve().parents[2]


def test_policy_selection_is_deterministic_and_explicit_override_wins(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    policy = resolve_policy("developer", explicit_route="direct_api")
    route = resolve_model_route("developer", explicit_route="direct_api")
    assert policy.route == "direct_api"
    assert route.profile_name == "claude-opus"
    assert route.route.name == "direct_api"
    assert route.identity == "anthropic/claude-opus-5"


def test_voice_haiku_is_resolved_as_voice_only_builtin(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    profile = model_profile_for_workload("voice_supervisor")
    assert profile["model"] == "claude-haiku-4-5"
    assert profile["identity"] == "anthropic/claude-haiku-4-5"


def test_vision_workload_requires_image_capability(monkeypatch):
    route = resolve_model_route(
        "vision", environ={"ANTHROPIC_API_KEY": "synthetic-key"}
    )
    assert "images" in route.route.capabilities


def test_unknown_workload_fails_closed():
    with pytest.raises(ModelRouteError, match="unknown workload"):
        resolve_policy("not-a-workload")


def test_confidential_workload_cannot_use_external_default(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    with pytest.raises(ModelRouteError, match="requires confidential"):
        resolve_model_route("memory", explicit_route="direct_api")


def test_missing_route_credential_fails_closed(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ModelRouteError, match="requires ANTHROPIC_API_KEY"):
        resolve_model_route("developer")


def test_profile_routes_are_reported_without_credentials():
    profile = {"api_key_env": "SECRET", "routes": {"saygm": {}}}
    assert available_routes(profile) == ["direct_api", "saygm"]


def test_saygm_catalog_can_upgrade_route_to_confidential(monkeypatch):
    monkeypatch.setenv("SAYGM_API_KEY", "gm-key")
    catalog = parse_catalog({"data": [{
        "id": "claude-opus-5-TEE", "tier": "confidential",
        "gateway_provider": "chutes",
    }]})
    route = resolve_model_route("developer", explicit_route="saygm",
                               saygm_model=catalog[0])
    assert route.route.privacy == "confidential"


def test_confidential_memory_requires_catalog_proof(monkeypatch):
    monkeypatch.setenv("SAYGM_API_KEY", "gm-key")
    catalog = parse_catalog({"data": [{
        "id": "claude-sonnet-5-TEE", "tier": "confidential",
    }]})
    route = resolve_model_route("memory", explicit_route="saygm",
                               saygm_model=catalog[0])
    assert route.route.privacy == "confidential"


def test_checked_route_fetches_catalog_only_for_confidential_saygm(monkeypatch):
    monkeypatch.setenv("SAYGM_API_KEY", "gm-key")
    catalog = parse_catalog({"data": [{"id": "claude-sonnet-5-TEE", "tier": "confidential"}]})
    monkeypatch.setattr("jarvis.saygm.fetch_catalog", lambda **_: catalog)
    route = __import__("jarvis.model_routing", fromlist=["resolve_model_route_checked"]).resolve_model_route_checked(
        "memory", explicit_route="saygm")
    assert route.route.privacy == "confidential"
