import pytest

from jarvis.model_routing import ModelRouteError, make_route_client, resolve_model_route


def test_subscription_adapter_does_not_fall_back_to_api(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    route = resolve_model_route("planning", explicit_route="subscription")
    with pytest.raises(ModelRouteError, match="subscription text adapter"):
        make_route_client(route)


def test_tool_workload_cannot_select_text_only_subscription(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    with pytest.raises(ModelRouteError, match="lacks required capabilities"):
        resolve_model_route("developer", explicit_route="subscription")


def test_saygm_route_uses_saygm_credential_and_endpoint(monkeypatch):
    monkeypatch.setenv("SAYGM_API_KEY", "gm-key")
    route = resolve_model_route("developer", explicit_route="saygm")
    assert route.base_url == "https://api.saygm.com/v1"
    assert route.api_key_env == "SAYGM_API_KEY"
    assert route.route.adapter == "saygm_gateway"
    assert route.provider == "saygm"


def test_subscription_text_adapter_is_explicitly_enabled(monkeypatch):
    monkeypatch.setenv("JARVIS_SUBSCRIPTION_TEXT_ENABLED", "1")
    route = resolve_model_route("planning", explicit_route="subscription")
    client = make_route_client(route)
    assert client.base_url == "subscription://claude"


@pytest.mark.asyncio
async def test_subscription_text_adapter_rejects_tools_before_cli(monkeypatch):
    monkeypatch.setenv("JARVIS_SUBSCRIPTION_TEXT_ENABLED", "1")
    route = resolve_model_route("planning", explicit_route="subscription")
    client = make_route_client(route)
    with pytest.raises(Exception, match="does not support Mortimer tools"):
        await client.chat.completions.create(tools=[{"type": "function"}], messages=[])


def test_codex_subscription_route_is_text_only_and_uses_subscription_billing(monkeypatch):
    monkeypatch.setenv("JARVIS_SUBSCRIPTION_TEXT_ENABLED", "1")
    route = resolve_model_route("planning", explicit_profile="codex-subscription",
                               explicit_route="codex_subscription")
    assert route.provider == "subscription"
    assert route.route.billing == "subscription"
    client = make_route_client(route)
    assert client.base_url == "subscription://codex"


@pytest.mark.asyncio
async def test_codex_subscription_adapter_rejects_tools_before_cli(monkeypatch):
    monkeypatch.setenv("JARVIS_SUBSCRIPTION_TEXT_ENABLED", "1")
    route = resolve_model_route("planning", explicit_profile="codex-subscription",
                               explicit_route="codex_subscription")
    client = make_route_client(route)
    with pytest.raises(Exception, match="does not support Mortimer tools"):
        await client.chat.completions.create(tools=[{"type": "function"}], messages=[])
