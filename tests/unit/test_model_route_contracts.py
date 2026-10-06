"""Config is a choice surface, not credential or model-floor authority."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
import yaml

from jarvis import model_routing as routing
from jarvis.db import get_conn, run_migrations
from jarvis.model_preferences import (
    ModelPreferenceError,
    confirm_preference,
    list_preferences,
    stage_preference,
)


@pytest.fixture(autouse=True)
def isolate_preferences(monkeypatch):
    monkeypatch.setenv("JARVIS_MODEL_PREFERENCES_ENABLED", "0")


class NoCredentialLookup(dict):
    def get(self, key, *args):
        pytest.fail(f"rejected route read credential {key}")


def write_policy(tmp_path, route_name=None, changes=None):
    access = routing.load_access_config()
    if route_name:
        access["routes"].setdefault(route_name, {}).update(changes or {})
    path = tmp_path / "model-access.yaml"
    path.write_text(yaml.safe_dump(access))
    return path


@pytest.mark.parametrize("route_name,workload,profile,changes", [
    ("direct_api", "developer", "claude-opus", {"base_url": "https://attacker.invalid/v1"}),
    ("direct_api", "developer", "claude-opus", {"credential_env": "OTHER_KEY"}),
    ("direct_api", "developer", "claude-opus", {"api_key_env": "OTHER_KEY"}),
    ("direct_api", "developer", "claude-opus", {"billing": "subscription"}),
    ("direct_api", "developer", "claude-opus", {"privacy": "local_only"}),
    ("direct_api", "developer", "claude-opus", {"adapter": "local_runtime"}),
    ("subscription", "planning", "claude-opus", {"adapter": "openai_compatible"}),
    ("subscription", "planning", "claude-opus", {"base_url": "https://attacker.invalid/v1"}),
    ("subscription", "planning", "claude-opus", {"credential_env": "ANTHROPIC_API_KEY"}),
    ("subscription", "planning", "claude-opus", {"api_key_env": "ANTHROPIC_API_KEY"}),
    ("subscription", "planning", "claude-opus", {"billing": "provider_api"}),
    ("subscription", "planning", "claude-opus", {"privacy": "confidential"}),
    ("codex_subscription", "planning", "codex-subscription", {"adapter": "openai_compatible"}),
    ("codex_subscription", "planning", "codex-subscription", {"credential_env": "OPENAI_API_KEY"}),
    ("local", "systems", "claude-sonnet-5", {"adapter": "openai_compatible"}),
    ("local", "systems", "claude-sonnet-5", {"base_url": "https://attacker.invalid/v1"}),
    ("local", "systems", "claude-sonnet-5", {"credential_env": "ANTHROPIC_API_KEY"}),
    ("local", "systems", "claude-sonnet-5", {"billing": "provider_api"}),
    ("saygm", "memory", "claude-sonnet-5", {"adapter": "openai_compatible"}),
    ("saygm", "memory", "claude-sonnet-5", {"billing": "subscription"}),
    ("saygm", "memory", "claude-sonnet-5", {"api_key_env": "OTHER_KEY"}),
    ("direct_api", "developer", "claude-opus", {"extra_headers": {"Authorization": "fixture"}}),
])
def test_routine_route_override_is_refused_before_key_or_client(tmp_path, monkeypatch, route_name, workload, profile, changes):
    path = write_policy(tmp_path, route_name, changes)
    def forbidden(**kwargs):
        pytest.fail("rejected config constructed a provider client or fetched catalog")
    monkeypatch.setattr("jarvis.llm_client.make_async_client", forbidden)
    monkeypatch.setattr("jarvis.saygm.fetch_catalog", forbidden)
    with pytest.raises(routing.ModelRouteError, match="override|cannot carry|not approved|unsupported"):
        resolved = routing.resolve_model_route_checked(
            workload, explicit_profile=profile, explicit_route=route_name,
            policy_path=path, environ=NoCredentialLookup())
        routing.make_route_client(resolved)


@pytest.mark.parametrize("factory", [routing.make_route_client, routing.make_sync_route_client])
@pytest.mark.parametrize("route_name", ["subscription", "codex_subscription", "local"])
def test_forged_native_or_local_route_cannot_transmit_fixture_key(monkeypatch, factory, route_name):
    workload = "systems" if route_name == "local" else "planning"
    profile = "codex-subscription" if route_name == "codex_subscription" else "claude-opus"
    resolved = routing.resolve_model_route(workload, explicit_profile=profile, explicit_route=route_name)
    malicious = replace(resolved, base_url="https://attacker.invalid/v1", api_key_env="FIXTURE_KEY",
                        route=replace(resolved.route, adapter="openai_compatible", credential_env="FIXTURE_KEY"))
    monkeypatch.setattr(routing.os.environ, "get", NoCredentialLookup().get)
    with pytest.raises(routing.ModelRouteError, match="protected adapter or billing"):
        factory(malicious)


def test_direct_api_uses_authoritative_registry_endpoint_and_provider_billing(tmp_path, monkeypatch):
    profile = routing._load_model_registry()["profiles"]["claude-opus"]
    path = write_policy(tmp_path, "direct_api", {
        "base_url": profile["base_url"], "credential_env": profile["api_key_env"],
        "api_key_env": profile["api_key_env"], "adapter": "openai_compatible",
        "billing": "provider_api", "privacy": "approved_external",
    })
    monkeypatch.setenv(profile["api_key_env"], "FIXTURE_ONLY_KEY")
    recorded = []
    monkeypatch.setattr("jarvis.llm_client.make_async_client", lambda **kwargs: recorded.append(kwargs))
    resolved = routing.resolve_model_route("developer", policy_path=path)
    routing.make_route_client(resolved)
    assert recorded[0]["base_url"] == resolved.route.base_url == profile["base_url"]
    assert recorded[0]["api_key"] == "FIXTURE_ONLY_KEY"
    assert recorded[0]["provider"] == profile["provider"]
    assert resolved.route.billing == "provider_api"


def test_subscription_and_local_routes_never_inherit_api_profile_credentials():
    native = routing.resolve_model_route("planning", explicit_route="subscription")
    assert native.base_url == "subscription://claude"
    assert native.api_key_env is None and native.route.credential_env is None
    local = routing.resolve_model_route("systems", explicit_route="local")
    assert local.base_url == "" and local.api_key_env is None
    with pytest.raises(routing.ModelRouteError, match="local model runtime is not configured"):
        routing.make_route_client(local)


def test_api_capabilities_cannot_be_promoted_by_global_route_config(tmp_path):
    path = write_policy(tmp_path, "direct_api", {"capabilities": ["text", "tools", "images"]})
    with pytest.raises(routing.ModelRouteError, match="unverified model capabilities"):
        routing.resolve_model_route("developer", explicit_profile="or-gpt-5.1",
                                    policy_path=path, environ=NoCredentialLookup())


@pytest.mark.parametrize("workload,profile,required", [
    ("developer", "or-gpt-5-mini", "mid"),
    ("background", "or-gpt-5-mini", "mid"),
    ("planning", "claude-sonnet-5", "frontier"),
])
@pytest.mark.parametrize("resolver", [routing.resolve_model_route, routing.resolve_model_route_checked])
def test_model_quality_floor_refuses_before_credentials_or_catalog(workload, profile, required, resolver, monkeypatch):
    monkeypatch.setattr("jarvis.saygm.fetch_catalog", lambda **_: pytest.fail("quality floor fetched catalog"))
    with pytest.raises(routing.ModelRouteError, match=f"minimum '{required}'"):
        resolver(workload, explicit_profile=profile, explicit_route="saygm", environ=NoCredentialLookup())


def test_council_economy_and_voice_exception_preserve_documented_floors():
    council = routing.resolve_model_route("council", explicit_profile="or-gpt-5-mini",
                                         environ={"OPENROUTER_API_KEY": "fixture"})
    assert council.model == "openai/gpt-5-mini"
    voice = routing.resolve_model_route("voice_supervisor", environ={"ANTHROPIC_API_KEY": "fixture"})
    assert voice.model == "claude-haiku-4-5"
    assert routing.resolve_policy("council").minimum_quality_tier == "economy"
    assert routing.resolve_policy("voice_supervisor").minimum_quality_tier == "economy"


@pytest.mark.parametrize("tier", [None, "unknown", 1])
def test_unknown_profile_quality_is_unavailable_before_key_lookup(monkeypatch, tier):
    registry = routing._load_model_registry()
    registry["profiles"]["claude-opus"]["tier"] = tier
    monkeypatch.setattr(routing, "_load_model_registry", lambda *_: registry)
    with pytest.raises(routing.ModelRouteError, match="unknown model quality tier"):
        routing.resolve_model_route("developer", environ=NoCredentialLookup())


@pytest.mark.parametrize("tier", ["economy", "unknown", None])
def test_configured_quality_cannot_lower_standing_floor(tmp_path, tier):
    path = write_policy(tmp_path)
    access = yaml.safe_load(path.read_text())
    access["workloads"]["developer"]["minimum_quality_tier"] = tier
    path.write_text(yaml.safe_dump(access))
    with pytest.raises(routing.ModelRouteError, match="standing|unknown minimum quality"):
        routing.resolve_policy("developer", path=path)


def test_descriptor_exposes_required_and_model_quality_without_key_lookup():
    descriptor = routing.describe_route_choice("developer", "or-gpt-5-mini", "direct_api",
                                                environ=NoCredentialLookup())
    assert descriptor["applicable"] is True and descriptor["compatible"] is False
    assert descriptor["minimum_quality_tier"] == "mid"
    assert descriptor["model_quality_tier"] == "economy"
    assert "below" in descriptor["reason"]


def test_stage_and_legacy_confirm_refuse_lower_quality(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "quality.db"))
    with pytest.raises(ModelPreferenceError, match="minimum 'mid'"):
        stage_preference("developer", "or-gpt-5-mini", "direct_api")
    with get_conn() as conn:
        run_migrations(conn)
        now = datetime.now(timezone.utc)
        conn.execute("INSERT INTO model_route_drafts(draft_id,workload,profile,route,privacy,created_at,expires_at) "
                     "VALUES('old-quality','developer','or-gpt-5-mini','direct_api','approved_external',?,?)",
                     (now.isoformat(), (now + timedelta(minutes=5)).isoformat()))
        conn.commit()
    with pytest.raises(ModelPreferenceError, match="minimum 'mid'"):
        confirm_preference("old-quality")
    assert list_preferences() == []


def test_legacy_persisted_lower_quality_preference_is_refused_at_execution(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "legacy-quality.db"))
    monkeypatch.setenv("JARVIS_MODEL_PREFERENCES_ENABLED", "1")
    with get_conn() as conn:
        run_migrations(conn)
        conn.execute("INSERT INTO model_route_preferences(workload,profile,route,privacy,updated_at) "
                     "VALUES('developer','or-gpt-5-mini','direct_api','approved_external','2026-09-01')")
        conn.commit()
    with pytest.raises(routing.ModelRouteError, match="minimum 'mid'"):
        routing.resolve_model_route_checked("developer", environ=NoCredentialLookup())
