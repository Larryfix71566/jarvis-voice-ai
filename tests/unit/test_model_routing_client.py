import pytest

from jarvis.model_routing import ModelRouteError, make_route_client, resolve_model_route, resolve_model_route_checked


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
    from jarvis.saygm import parse_catalog
    monkeypatch.setenv("SAYGM_API_KEY", "gm-key")
    monkeypatch.setattr("jarvis.saygm.fetch_catalog", lambda **_: parse_catalog({"data": [{
        "id": "claude-fable-5", "tier": "frontier", "api_shapes": ["chat.completions"],
    }]}))
    route = resolve_model_route_checked("planning", explicit_route="saygm")
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


def test_native_tool_factory_requires_explicit_capability_gate_and_receipt(monkeypatch, tmp_path):
    from dataclasses import replace
    from jarvis.subscription_tools import ClaudeSubscriptionToolClient
    monkeypatch.setenv("JARVIS_SUBSCRIPTION_TEXT_ENABLED", "1")
    monkeypatch.delenv("JARVIS_SUBSCRIPTION_TOOLS_ENABLED", raising=False)
    text = resolve_model_route("planning", explicit_route="subscription")
    assert not isinstance(make_route_client(text), ClaudeSubscriptionToolClient)
    tools = replace(text, route=replace(text.route, capabilities=("text", "tools")))
    with pytest.raises(ModelRouteError, match="native tool adapter is disabled"):
        make_route_client(tools)
    monkeypatch.setenv("JARVIS_SUBSCRIPTION_TOOLS_ENABLED", "1")
    monkeypatch.delenv("JARVIS_SUBSCRIPTION_TOOL_CAPABILITY_RECEIPT", raising=False)
    with pytest.raises(ModelRouteError, match="receipt is required"):
        make_route_client(tools)
    receipt = tmp_path / "receipt.json"
    receipt.write_text("{}")
    monkeypatch.setenv("JARVIS_SUBSCRIPTION_TOOL_CAPABILITY_RECEIPT", str(receipt))
    assert isinstance(make_route_client(tools), ClaudeSubscriptionToolClient)


async def test_native_tool_flag_and_placeholder_receipt_cannot_start_provider(monkeypatch, tmp_path):
    from dataclasses import replace
    from jarvis import subscription_tools
    from jarvis.model_execution import ModelExecutionRequest, ModelToolReference, execute_chat
    from jarvis.privacy_policy import DataPolicy
    from jarvis.subscription import SubscriptionCapabilityError
    monkeypatch.setenv("JARVIS_SUBSCRIPTION_TOOLS_ENABLED", "1")
    receipt = tmp_path / "receipt.json"
    receipt.write_text("{}")
    monkeypatch.setenv("JARVIS_SUBSCRIPTION_TOOL_CAPABILITY_RECEIPT", str(receipt))
    monkeypatch.setattr(subscription_tools, "claude_tool_runtime_identity", lambda: {
        "path": "/fixture/claude", "version": "fixture", "sha256": "fixture",
    })
    monkeypatch.setattr(subscription_tools.asyncio, "create_subprocess_exec",
                        lambda *_a, **_k: pytest.fail("unverified receipt started provider"))
    route = resolve_model_route("planning", explicit_route="subscription")
    route = replace(route, route=replace(route.route, capabilities=("text", "tools")))
    with pytest.raises(SubscriptionCapabilityError):
        await execute_chat(ModelExecutionRequest(
            "planning", "fixture", "parent", "Synthetic public input",
            tools=(ModelToolReference("fixture", {"type": "object"}),),
            data_policy=DataPolicy("approved_external", "public-fixture"),
        ), route)


def test_sync_and_codex_native_tool_routes_never_fall_back_to_text(monkeypatch):
    from dataclasses import replace
    from jarvis.model_routing import make_sync_route_client
    monkeypatch.setenv("JARVIS_SUBSCRIPTION_TEXT_ENABLED", "1")
    claude = resolve_model_route("planning", explicit_route="subscription")
    claude = replace(claude, route=replace(claude.route, capabilities=("text", "tools")))
    with pytest.raises(ModelRouteError, match="asynchronous execution"):
        make_sync_route_client(claude)
    codex = resolve_model_route("planning", explicit_profile="codex-subscription", explicit_route="codex_subscription")
    codex = replace(codex, route=replace(codex.route, capabilities=("text", "tools")))
    for factory in (make_route_client, make_sync_route_client):
        with pytest.raises(ModelRouteError, match="native tools are not verified"):
            factory(codex)
