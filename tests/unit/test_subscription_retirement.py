"""No network: prove retirement rejects API construction and paid failover."""
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from jarvis import llm_client
from jarvis.provider_access import ProviderAccessError, access_mode, require_voice_readiness
from jarvis.model_routing import ModelRouteError, make_route_client, resolve_model_route, resolve_policy


@pytest.fixture
def retired(monkeypatch, fresh_db):
    monkeypatch.setenv("JARVIS_LLM_ACCESS_MODE", "subscription_only")
    monkeypatch.setenv("JARVIS_MODEL_PREFERENCES_ENABLED", "0")
    return monkeypatch


@pytest.mark.parametrize("provider,url", [
    ("anthropic", "https://api.anthropic.com/v1"),
    ("openai", "https://api.openai.com/v1"),
    ("openrouter", "https://openrouter.ai/api/v1"),
    (None, "https://unknown.example/v1"),
])
@pytest.mark.parametrize("factory", [llm_client.make_async_client, llm_client.make_sync_client])
def test_retirement_precedes_api_client_construction(retired, provider, url, factory):
    constructors = [Mock(side_effect=AssertionError("API constructed")) for _ in range(4)]
    for target, stub in zip([
        "openai.OpenAI", "openai.AsyncOpenAI",
        "jarvis.llm_client.AnthropicChatShim", "jarvis.llm_client.AsyncAnthropicChatShim",
    ], constructors):
        retired.setattr(target, stub)
    with pytest.raises(ProviderAccessError, match="no paid fallback"):
        factory(api_key="synthetic", base_url=url, provider=provider)
    assert all(not stub.called for stub in constructors)


def test_api_client_created_before_retirement_is_refused(monkeypatch):
    call = Mock(return_value=SimpleNamespace())
    call._mortimer_measured = False
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=call)))
    monkeypatch.setenv("JARVIS_LLM_ACCESS_MODE", "legacy")
    llm_client._instrument_completion(client, "anthropic", asynchronous=False)
    monkeypatch.setenv("JARVIS_LLM_ACCESS_MODE", "subscription_only")
    with pytest.raises(ProviderAccessError):
        client.chat.completions.create(model="synthetic", messages=[])
    call.assert_not_called()


def test_text_workload_selects_subscription_without_api_key(retired):
    retired.delenv("ANTHROPIC_API_KEY", raising=False)
    route = resolve_model_route("planning")
    assert route.route.name == "subscription"
    assert route.route.billing == "subscription"
    assert route.api_key_env is None
    assert route.base_url == "subscription://claude"


def test_codex_subscription_remains_selectable_without_openai_key(retired):
    retired.delenv("OPENAI_API_KEY", raising=False)
    route = resolve_model_route("planning", explicit_profile="codex-subscription",
                                explicit_route="codex_subscription")
    assert route.route.billing == "subscription"
    assert route.base_url == "subscription://codex"


@pytest.mark.parametrize("route", ["direct_api", "saygm"])
def test_explicit_paid_selection_cannot_override_retirement(retired, route):
    with pytest.raises(ModelRouteError, match="no fallback"):
        resolve_model_route("planning", explicit_route=route)


def test_forged_api_route_is_refused_at_client_boundary(retired):
    route = resolve_model_route("planning")
    forged = replace(route, route=replace(route.route, name="direct_api"))
    with pytest.raises(ModelRouteError, match="no fallback"):
        make_route_client(forged)


@pytest.mark.asyncio
async def test_retained_api_route_cannot_use_injected_execution_client(retired):
    from jarvis.model_execution import execute_chat
    route = resolve_model_route("planning")
    forged = replace(route, route=replace(route.route, name="direct_api"))
    factory = Mock(side_effect=AssertionError("retained API client used"))
    with pytest.raises(ProviderAccessError, match="no fallback"):
        await execute_chat(None, forged, client_factory=factory)
    factory.assert_not_called()


def test_private_source_policy_is_not_relaxed(retired):
    with pytest.raises(ModelRouteError):
        resolve_model_route("memory")
    assert resolve_policy("memory").privacy == "confidential"


def test_tools_do_not_become_supported_by_selecting_subscription(retired):
    with pytest.raises(ModelRouteError, match="capabilities"):
        resolve_model_route("developer")


def test_legacy_executor_cannot_shop_for_paid_fallback(retired):
    from jarvis.agents.upgrade_agent import UpgradeAgent
    retired.setattr("jarvis.agents.upgrade_agent.available_models",
                    Mock(side_effect=AssertionError("fallback enumeration")))
    assert UpgradeAgent.__new__(UpgradeAgent)._next_failover_profile() is None


def test_voice_refuses_even_when_only_typed_settings_select_retirement(monkeypatch):
    monkeypatch.setenv("JARVIS_LLM_ACCESS_MODE", "legacy")
    with pytest.raises(ProviderAccessError, match="voice is unavailable"):
        require_voice_readiness("subscription_only")


def test_unknown_access_mode_fails_closed():
    with pytest.raises(ProviderAccessError):
        access_mode({"JARVIS_LLM_ACCESS_MODE": "subscription-onli"})


def test_retirement_settings_do_not_require_api_credential(retired):
    from jarvis.config import Settings
    retired.delenv("OPENAI_API_KEY", raising=False)
    settings = Settings(_env_file=None, deepgram_api_key="synthetic", elevenlabs_api_key="synthetic")
    assert settings.openai_api_key == ""


def test_screen_child_receives_retirement_policy(retired):
    from jarvis.skills.registry import build_child_env
    env = build_child_env({"name": "mcp-screen"})
    assert env["JARVIS_LLM_ACCESS_MODE"] == "subscription_only"


def test_vision_refuses_before_constructing_client(retired):
    from mcp_servers.mcp_screen.logic import _default_vision_client
    constructor = Mock(side_effect=AssertionError("vision API constructed"))
    retired.setattr("openai.OpenAI", constructor)
    with pytest.raises(ProviderAccessError):
        _default_vision_client({"model": "synthetic", "api_key_env": "SYNTHETIC_KEY"})
    constructor.assert_not_called()


def test_saved_paid_preference_is_refused_not_rewritten(retired):
    retired.setenv("JARVIS_MODEL_PREFERENCES_ENABLED", "1")
    retired.setattr("jarvis.model_preferences.list_preferences", lambda: [{
        "workload": "planning", "profile": "claude-fable-5",
        "route": "direct_api", "privacy": "approved_external",
    }])
    with pytest.raises(ModelRouteError, match="no fallback"):
        resolve_policy("planning")


def test_subscription_policy_cannot_gain_a_paid_fallback(retired):
    from jarvis.model_routing import load_access_config
    config = load_access_config()
    config["workloads"]["planning"]["fallback_routes"] = ["direct_api"]
    with pytest.raises(ModelRouteError, match="no fallback"):
        resolve_policy("planning", access_config=config)


def test_readiness_does_not_claim_account_or_activation(monkeypatch):
    from jarvis import subscription_readiness as readiness
    monkeypatch.setattr(readiness.shutil, "which", lambda _: None)
    report = readiness.retirement_readiness()
    assert report["inference_attempts"] == 0
    assert report["activation_ready"] is False
    assert report["runtimes"]["codex"]["authentication"] == "not_checked"
