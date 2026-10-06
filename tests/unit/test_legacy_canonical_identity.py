"""Canonical council independence holds before credentials with routing off."""
from copy import deepcopy

import pytest
import yaml

from jarvis.agents import upgrade_agent as ua
from jarvis.council import config as council_config


def _profile(name, model, *, provider="openai", tier="economy", identity=None):
    profile = {
        "name": name, "model": model, "provider": provider, "tier": tier,
        "base_url": "https://api.openai.com/v1", "api_key_env": "FIXTURE_MODEL_KEY",
    }
    if identity is not None:
        profile["identity"] = identity
    return profile


def _registry(*profiles):
    return {"default": profiles[0]["name"], "profiles": {p["name"]: p for p in profiles}}


def _write_legacy(tmp_path, registry):
    path = tmp_path / "legacy_models.yaml"
    path.write_text(yaml.safe_dump({
        "default": registry["default"], "profiles": list(registry["profiles"].values()),
    }), encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def routing_off(monkeypatch):
    monkeypatch.setenv("JARVIS_MODEL_ROUTING_ENABLED", "0")
    monkeypatch.setenv("FIXTURE_MODEL_KEY", "synthetic-key")


@pytest.mark.parametrize("left,right", [
    (_profile("direct", "gpt-5.1", identity="openai/gpt-5.1"),
     _profile("proxy", "openai/gpt-5.1", provider="openrouter", identity="openai/gpt-5.1")),
    (_profile("first", "same-model"), _profile("alias", "same-model")),
    (_profile("direct", "kimi-k3", provider="moonshot"),
     _profile("proxy", "moonshotai/kimi-k3", provider="openrouter")),
    (_profile("first", "same-model", identity="openai/first-label"),
     _profile("alias", "same-model", identity="openai/second-label")),
    (_profile("first", "opaque", provider="openrouter", identity="openai/first-label"),
     _profile("alias", "opaque", provider="openrouter", identity="anthropic/second-label")),
])
def test_authoritative_legacy_loader_rejects_model_aliases_before_key_lookup(tmp_path, monkeypatch, left, right):
    path = _write_legacy(tmp_path, _registry(left, right))

    class CredentialTrap(dict):
        def get(self, key, *args):
            if key == "FIXTURE_MODEL_KEY":
                pytest.fail("ambiguous registry consulted credentials")
            return super().get(key, *args)

    monkeypatch.setattr(ua.os, "environ", CredentialTrap(ua.os.environ))
    with pytest.raises(ua.ModelRegistryError, match="duplicate canonical model identities"):
        ua.available_models(path)


@pytest.mark.parametrize("entrypoint", [
    lambda registry: ua.resolve_profile(registry, "first"),
    lambda registry: ua.available_models(registry=registry),
    lambda registry: council_config.resolve_members(1, "proposers", registry=registry),
    lambda registry: council_config.resolve_members(2, "judges", registry=registry, exclude={"first"}),
    lambda registry: council_config.resolve_tier_name_members("frontier", registry=registry),
])
def test_preloaded_duplicate_snapshot_is_rechecked_before_any_membership_lookup(entrypoint):
    class CredentialTrap(dict):
        def get(self, key, *args):
            if key == "api_key_env":
                pytest.fail("ambiguous cached registry consulted credential reference")
            return super().get(key, *args)

    registry = _registry(
        CredentialTrap(_profile("first", "model", tier="economy", identity="openai/model")),
        CredentialTrap(_profile("alias", "model", tier="frontier", identity="openai/model")),
    )
    with pytest.raises(ua.ModelRegistryError, match="duplicate canonical model identities"):
        entrypoint(registry)


@pytest.mark.parametrize("identity", [None, "", False, 42, "bare", "openai/", "/model", "openai//model", "openai/model/", " openai/model", "openai/model "])
def test_explicit_malformed_identity_never_falls_back_to_a_guessed_identity(tmp_path, identity):
    profile = _profile("first", "model")
    profile["identity"] = identity
    with pytest.raises(ua.ModelRegistryError, match="unavailable canonical identity"):
        ua.load_model_registry(_write_legacy(tmp_path, _registry(profile)))


def test_legacy_identity_derivation_preserves_original_return_shape(tmp_path):
    registry = _registry(
        _profile("direct", "kimi-k3", provider="moonshot"),
        _profile("proxy", "openai/gpt-5.1", provider="openrouter", tier="mid"),
    )
    loaded = ua.load_model_registry(_write_legacy(tmp_path, registry))
    assert loaded == registry
    assert ua.validate_model_registry_identities(loaded) == {
        "direct": "moonshotai/kimi-k3", "proxy": "openai/gpt-5.1",
    }
    assert all("identity" not in p for p in loaded["profiles"].values())


def test_same_bare_wire_model_on_distinct_authoritative_vendors_remains_independent(tmp_path):
    registry = _registry(
        _profile("one", "model", provider="openai"),
        _profile("two", "model", provider="anthropic", tier="mid"),
    )
    loaded = ua.load_model_registry(_write_legacy(tmp_path, registry))
    assert ua.validate_model_registry_identities(loaded) == {
        "one": "openai/model", "two": "anthropic/model",
    }


def test_identity_exclusions_and_seeded_tier_partition_keep_independent_roles():
    registry = _registry(
        _profile("economy-one", "economy-1"), _profile("economy-two", "economy-2"),
        _profile("mid-one", "mid-1", tier="mid"),
        _profile("frontier-one", "frontier-1", tier="frontier"),
        _profile("frontier-two", "frontier-2", tier="frontier"),
        _profile("frontier-three", "frontier-3", tier="frontier"),
    )
    before = deepcopy(registry)
    ids = ua.validate_model_registry_identities(registry)
    assert set(council_config.resolve_members(1, "proposers", registry=registry)) == {
        "economy-one", "economy-two",
    }
    for seed in ("first-round", "second-round"):
        proposers = council_config.resolve_members(2, "proposers", registry=registry, seed=seed)
        judges = council_config.resolve_members(2, "judges", registry=registry, seed=seed, exclude=set(proposers))
        assert proposers and judges
        assert not {ids[name] for name in proposers} & {ids[name] for name in judges}
    assert council_config.resolve_tier_name_members(
        "economy", registry=registry, exclude={"openai/economy-1"},
    ) == ["economy-two"]
    assert registry == before


def test_bare_gateway_model_or_untrusted_provider_inference_is_unavailable(tmp_path):
    for profile in (
        _profile("gateway", "bare", provider="openrouter"),
        {"name": "spoof", "model": "model", "base_url": "https://evil.invalid/path/anthropic.com"},
    ):
        with pytest.raises(ua.ModelRegistryError, match="unavailable canonical identity"):
            ua.load_model_registry(_write_legacy(tmp_path, _registry(profile)))
