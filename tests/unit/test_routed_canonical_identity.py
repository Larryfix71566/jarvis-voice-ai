"""Routed council rejects registry aliases before a model can judge itself."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from jarvis import model_routing as routing
from jarvis.agents.upgrade_agent import (
    ModelRegistryError,
    _join_profile,
    load_model_registry,
    load_registry_layers,
)
from jarvis.council import config as council_config
from jarvis.council import council
from jarvis.privacy_policy import DataPolicy

CONFIG = Path(__file__).resolve().parents[2] / "config"


def _preloaded_registry(path):
    """An older cached snapshot must be rechecked at membership/selection."""
    layers = load_registry_layers(path)
    return {"default": layers["default"], "profiles": {
        profile["name"]: _join_profile(profile, layers["endpoints"][profile["endpoint"]])
        for profile in layers["profiles"]
    }}


@pytest.fixture(params=["same_endpoint", "different_endpoint"])
def split_registry(tmp_path, monkeypatch, request):
    """A real split registry with endpoints copied intact and one alias."""
    profiles = yaml.safe_load((CONFIG / "model_profiles.yaml").read_text())
    alias = deepcopy(next(profile for profile in profiles["profiles"]
                          if profile["name"] == "claude-opus"))
    alias["name"] = "same-opus-different-profile"
    if request.param == "different_endpoint":
        alias["endpoint"] = "openrouter"
        alias["model"] = alias["identity"]
    profiles["profiles"].append(alias)
    profile_path = tmp_path / "model_profiles.yaml"
    profile_path.write_text(yaml.safe_dump(profiles))
    (tmp_path / "model_endpoints.yaml").write_text((CONFIG / "model_endpoints.yaml").read_text())
    monkeypatch.setenv("JARVIS_UPGRADE_MODELS", str(profile_path))
    monkeypatch.setenv("JARVIS_MODEL_PREFERENCES_ENABLED", "0")
    monkeypatch.setenv("OPENROUTER_API_KEY", "SYNTHETIC_KEY_ONLY")
    return profile_path


@pytest.mark.parametrize("resolver", [routing.resolve_model_route, routing.resolve_model_route_checked])
@pytest.mark.parametrize("profile", ["claude-opus", "same-opus-different-profile", "claude-sonnet-5"])
def test_real_split_registry_alias_refuses_every_routed_choice_before_credentials(
    split_registry, monkeypatch, resolver, profile,
):
    # A directly requested routing resolver also validates when the global
    # rollout gate is off; legacy call sites do not enter that resolver.
    monkeypatch.setenv("JARVIS_MODEL_ROUTING_ENABLED", "0")
    class NoCredentialLookup(dict):
        def get(self, key, *args):
            pytest.fail(f"duplicate registry read credential {key}")
    monkeypatch.setattr("jarvis.saygm.fetch_catalog", lambda **_: pytest.fail("ambiguous catalog request"))
    with pytest.raises(routing.ModelRouteError, match="duplicate canonical model identities"):
        resolver("council", explicit_profile=profile, explicit_route="saygm",
                 registry_path=split_registry, environ=NoCredentialLookup())


def test_enabled_registry_load_rejects_alias_and_preloaded_descriptor_is_unavailable(
    split_registry, monkeypatch,
):
    registry = _preloaded_registry(split_registry)
    monkeypatch.setenv("JARVIS_MODEL_ROUTING_ENABLED", "1")
    with pytest.raises(routing.ModelRouteError, match="duplicate canonical model identities"):
        routing._load_model_registry(split_registry)
    descriptor = routing.describe_route_choice(
        "council", "claude-opus", "direct_api",
        access_config=routing.load_access_config(), registry=registry, environ={},
    )
    assert descriptor["compatible"] is False
    assert descriptor["status"] == "incompatible"
    assert "duplicate canonical model identities" in descriptor["reason"]


@pytest.mark.parametrize("routing_enabled", ["0", "1"])
async def test_actual_council_alias_roles_are_blocked_before_any_provider_creation(
    split_registry, monkeypatch, caplog, routing_enabled,
):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "SYNTHETIC_KEY_ONLY")
    monkeypatch.setenv("JARVIS_MODEL_ROUTING_ENABLED", routing_enabled)
    monkeypatch.setattr(council, "_council_enabled", lambda: True)
    selected = {"frontier": ["claude-opus", "same-opus-different-profile"],
                "mid": ["claude-sonnet-5"]}
    monkeypatch.setattr("jarvis.llm_client.make_async_client",
                        lambda **_: pytest.fail("ambiguous council constructed a provider"))
    monkeypatch.setattr("jarvis.llm_client.make_sync_client",
                        lambda **_: pytest.fail("ambiguous council constructed a legacy provider"))
    monkeypatch.setattr(council, "record_execution_result",
                        lambda *_: pytest.fail("ambiguous council invented accounting"))
    for role in ("proposers", "judges"):
        with pytest.raises(ModelRegistryError, match="duplicate canonical model identities"):
            council_config.resolve_members(2, role, selected=selected, seed="fixture")
    assert await council.convene(
        workflow="public-fixture", placement="planner", trigger="unit", goal="public fixture",
        tier=2, context={"privacy": "approved_external"},
    ) is None
    assert "council_convene_failed error_type=ModelRegistryIdentityError" in caplog.text


def test_globally_off_legacy_council_rejects_aliases_before_provider_creation(split_registry, monkeypatch):
    monkeypatch.setenv("JARVIS_MODEL_ROUTING_ENABLED", "0")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "SYNTHETIC_KEY_ONLY")
    monkeypatch.setattr("jarvis.llm_client.make_sync_client",
                        lambda **_: pytest.fail("ambiguous legacy council constructed a provider"))
    with pytest.raises(ModelRegistryError, match="duplicate canonical model identities"):
        routing._load_model_registry(split_registry)
    with pytest.raises(ModelRegistryError, match="duplicate canonical model identities"):
        council_config.resolve_members(2, "judges", registry=_preloaded_registry(split_registry),
                                       exclude={"claude-opus"}, seed="fixture")


async def test_real_economy_council_profile_still_executes_with_unique_registry(monkeypatch):
    monkeypatch.delenv("JARVIS_UPGRADE_MODELS", raising=False)
    monkeypatch.setenv("JARVIS_MODEL_ROUTING_ENABLED", "1")
    monkeypatch.setenv("JARVIS_MODEL_PREFERENCES_ENABLED", "0")
    monkeypatch.setenv("OPENROUTER_API_KEY", "SYNTHETIC_KEY_ONLY")
    profile = load_model_registry()["profiles"]["or-gpt-5-mini"]
    selected = {"economy": [profile["name"]]}
    assert council_config.resolve_members(1, "proposers", selected=selected) == [profile["name"]]
    observed = []
    async def create(**kwargs):
        observed.append(kwargs["model"])
        return SimpleNamespace(id="fixture", usage=None, choices=[SimpleNamespace(
            message=SimpleNamespace(content="public fixture", tool_calls=[]))])
    monkeypatch.setattr("jarvis.llm_client.make_async_client", lambda **_: SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    monkeypatch.setattr(council, "record_execution_result", lambda *_args: None)
    text, usage = await council._call_profile(profile, "public system", "public fixture", 1,
                                            rung="council", data_policy=DataPolicy("approved_external", "public-fixture"))
    assert text == "public fixture" and usage is None
    assert observed == ["openai/gpt-5-mini"]
