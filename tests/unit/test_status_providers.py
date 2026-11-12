"""T2.1 — provider discovery and catalog coverage (L3)."""

from __future__ import annotations

import urllib.request

import pytest

from jarvis.status import providers as P
from jarvis.status.providers import ADAPTERS, coverage_gaps, discover_providers


def _by_id(refs):
    return {r.id: r for r in refs}


def test_real_config_has_no_coverage_gaps():
    """The L3 tripwire: a provider added to the real config without a
    catalog adapter fails here."""
    refs = discover_providers(env={})
    assert coverage_gaps(refs) == []
    ids = {r.id for r in refs}
    # Everything §3.2 lists is discovered from the real config.
    for expected in ("anthropic", "moonshot", "openrouter", "voice",
                     "claude-subscription", "codex-subscription", "saygm",
                     "local", "deepgram", "elevenlabs", "tavily", "github",
                     "github-selfedit"):
        assert expected in ids, expected
    for r in refs:
        assert r.adapter in ADAPTERS


def test_real_config_is_the_split_registry_and_has_no_coverage_gaps(monkeypatch):
    """Spec P5 A5: the L3 tripwire holds against the JOINED view of the
    split registry (model_endpoints.yaml + model_profiles.yaml), read by the
    default loader path — not a legacy file or an env override — and every
    profile lands on the provider its endpoint names."""
    from jarvis.agents import upgrade_agent as ua

    monkeypatch.delenv(ua.REGISTRY_PATH_ENV, raising=False)
    layers = ua.load_registry_layers()
    assert layers["shape"] == "split"
    assert ua.registry_source().name == ua.PROFILES_FILENAME
    refs = discover_providers(env={})
    assert coverage_gaps(refs) == []
    served = {name: r for r in refs for name in r.profiles}
    assert set(served) == {p["name"] for p in layers["profiles"]}
    for prof in layers["profiles"]:
        endpoint = layers["endpoints"][prof["endpoint"]]
        ref = served[prof["name"]]
        if endpoint.get("base_url"):
            assert ref.base_url == endpoint["base_url"], prof["name"]
            assert ref.credential_env == endpoint["api_key_env"], prof["name"]
        else:  # A1: the credential-less subscription endpoint
            assert (ref.id, ref.adapter) == ("codex-subscription", "subscription_probe")


def test_unknown_provider_is_reported_as_gap():
    registry = {"default": "x", "profiles": {
        "newco": {"name": "newco", "base_url": "https://api.newco.ai/v1",
                  "api_key_env": "NEWCO_API_KEY", "model": "n1"},
        "other": {"name": "other", "base_url": "https://api.othco.io/v1",
                  "api_key_env": "OTH_KEY", "model": "o1"},
    }}
    refs = discover_providers(registry=registry, access={"routes": {}}, env={})
    gaps = coverage_gaps(refs)
    assert "unknown:api.newco.ai" in gaps
    # Two unknown providers never merge.
    assert "unknown:api.othco.io" in gaps
    ref = _by_id(refs)["unknown:api.newco.ai"]
    assert ref.adapter == "UNMAPPED"
    assert ref.profiles == ("newco",)
    assert ref.credential_env == "NEWCO_API_KEY"


def test_unmapped_route_and_baseless_profile_are_gaps():
    registry = {"profiles": {"mystery": {"name": "mystery", "provider": "x"}}}
    refs = discover_providers(registry=registry,
                              access={"routes": {"warp": {}}}, env={})
    assert coverage_gaps(refs) == ["profile:mystery", "route:warp"]


def test_codex_subscription_profile_attaches_to_route():
    registry = {"profiles": {"codex-subscription": {
        "name": "codex-subscription", "provider": "openai",
        "model": "gpt-6-astra", "tier": "frontier"}}}
    access = {"routes": {"codex_subscription": {"adapter": "codex_subscription_runtime"}}}
    refs = _by_id(discover_providers(registry=registry, access=access, env={}))
    ref = refs["codex-subscription"]
    assert ref.adapter == "subscription_probe"
    assert ref.profiles == ("codex-subscription",)
    assert ref.sources == ("registry:codex-subscription", "route:codex_subscription")
    assert ref.credential_env is None
    assert "profile:codex-subscription" not in refs


def test_access_routes_map_to_adapters():
    access = {"routes": {
        "subscription": {}, "codex_subscription": {}, "local": {},
        "saygm": {"credential_env": "SAYGM_API_KEY",
                  "base_url": "https://api.saygm.com/v1"}},
        # Workload routes are never read.
        "workloads": {"x": {"route": "direct_api"}}}
    refs = _by_id(discover_providers(registry={"profiles": {}}, access=access, env={}))
    assert refs["claude-subscription"].adapter == "subscription_probe"
    assert refs["codex-subscription"].adapter == "subscription_probe"
    assert refs["local"].adapter == "not_configured"
    assert refs["saygm"].adapter == "saygm_catalog"
    assert refs["saygm"].credential_env == "SAYGM_API_KEY"
    assert refs["saygm"].base_url == "https://api.saygm.com/v1"
    assert "route:direct_api" not in refs


def test_voice_ref_follows_openai_base_url():
    refs = _by_id(discover_providers(
        registry={"profiles": {}}, access={"routes": {}},
        env={"OPENAI_BASE_URL": "https://api.anthropic.com/v1"}))
    voice = refs["voice"]
    assert voice.adapter == "anthropic_models"
    assert voice.credential_env == "OPENAI_API_KEY"
    assert voice.sources == ("settings:OPENAI_BASE_URL",)
    default = _by_id(discover_providers(registry={"profiles": {}},
                                        access={"routes": {}}, env={}))["voice"]
    assert default.base_url == "https://api.openai.com/v1"
    assert default.adapter == "openai_models"


def test_services_always_emitted():
    refs = _by_id(discover_providers(registry={"profiles": {}},
                                     access={"routes": {}}, env={}))
    for sid, key_env in P.SERVICE_CREDENTIALS.items():
        assert refs[sid].kind == "service"
        assert refs[sid].adapter == "service_health"
        assert refs[sid].credential_env == key_env


def test_no_network(monkeypatch):
    import httpx

    def boom(*a, **k):
        raise AssertionError("network I/O during discovery")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    for name in ("get", "post", "request", "stream"):
        monkeypatch.setattr(httpx, name, boom)
    monkeypatch.setattr(httpx.Client, "send", boom)
    monkeypatch.setattr(httpx.AsyncClient, "send", boom)
    refs = discover_providers(env={})
    assert refs


def test_discovery_is_deterministic():
    a = discover_providers(env={"OPENAI_BASE_URL": "https://api.anthropic.com/v1"})
    b = discover_providers(env={"OPENAI_BASE_URL": "https://api.anthropic.com/v1"})
    assert a == b
    assert [r.id for r in a] == sorted(r.id for r in a)


def test_registry_profiles_group_by_provider():
    refs = _by_id(discover_providers(env={}))
    assert refs["anthropic"].adapter == "anthropic_models"
    assert refs["anthropic"].credential_env == "ANTHROPIC_API_KEY"
    assert "claude-opus" in refs["anthropic"].profiles
    assert refs["openrouter"].adapter == "openai_models"
    assert refs["moonshot"].adapter == "openai_models"


def test_no_key_values(monkeypatch):
    secret = "sk-ant-FIXTURE-SECRET-1234567890"
    env = {"ANTHROPIC_API_KEY": secret, "OPENAI_API_KEY": secret,
           "OPENAI_BASE_URL": "https://api.anthropic.com/v1"}
    refs = discover_providers(env=env)
    assert secret not in repr(refs)
