import pytest

import jarvis.memory_model as memory_model


class Settings:
    jarvis_memory_profile = "claude-sonnet-5"
    jarvis_background_profile = "claude-sonnet-5"
    openai_model = "supervisor-haiku"
    openai_api_key = "supervisor-key"
    openai_base_url = "https://supervisor.invalid/v1"


@pytest.mark.parametrize("purpose", ["memory", "background"])
def test_legacy_route_fails_closed_and_ignores_supervisor_and_vendor_keys(monkeypatch, purpose):
    # The legacy (routing-disabled) path used to read ANTHROPIC_API_KEY for the
    # Claude profile. Claude is subscription-only now: the profile has no
    # api_key_env/base_url, so no paid route exists, whatever keys are set.
    monkeypatch.delenv("JARVIS_MODEL_ROUTING_ENABLED", raising=False)
    for key in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.setenv(key, "present-but-unusable")
    monkeypatch.setenv("OPENAI_MODEL", "supervisor-haiku")
    resolver = memory_model.resolve_memory_route if purpose == "memory" else memory_model.resolve_background_route
    with pytest.raises(memory_model.MemoryModelUnavailable, match=f"{purpose} model profile 'claude-sonnet-5' is incomplete") as caught:
        resolver(Settings())
    for secret in ("present-but-unusable", Settings.openai_api_key, Settings.openai_base_url):
        assert secret not in str(caught.value)


@pytest.mark.parametrize("purpose", ["memory", "background"])
def test_legacy_client_factory_builds_no_client_for_subscription_only_profile(monkeypatch, purpose):
    monkeypatch.delenv("JARVIS_MODEL_ROUTING_ENABLED", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "memory-key")
    monkeypatch.setattr(memory_model, "make_async_client", lambda **_: pytest.fail("a paid API client was constructed"))
    monkeypatch.setattr(memory_model, "make_route_client", lambda *a, **k: pytest.fail("a routed client was constructed"))
    factory = memory_model.make_memory_async_client if purpose == "memory" else memory_model.make_background_async_client
    with pytest.raises(memory_model.MemoryModelUnavailable, match="is incomplete"):
        factory(Settings())


def test_legacy_route_requires_credential_of_a_non_retired_profile(monkeypatch):
    monkeypatch.delenv("JARVIS_MODEL_ROUTING_ENABLED", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    settings = Settings()
    settings.jarvis_memory_profile = "or-grok-4.6"
    with pytest.raises(memory_model.MemoryModelUnavailable, match="OPENROUTER_API_KEY"):
        memory_model.resolve_memory_route(settings)
    monkeypatch.setenv("OPENROUTER_API_KEY", "memory-key")
    route = memory_model.resolve_memory_route(settings)
    assert route.profile == "or-grok-4.6"
    assert route.api_key_env == "OPENROUTER_API_KEY"
    assert route.base_url == "https://openrouter.ai/api/v1"
    assert route.model != Settings.openai_model
    assert route.base_url != Settings.openai_base_url


def test_legacy_client_factory_uses_resolved_non_retired_route(monkeypatch):
    monkeypatch.delenv("JARVIS_MODEL_ROUTING_ENABLED", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "memory-key")
    seen = {}

    def fake_factory(**kwargs):
        seen.update(kwargs)
        return object()

    monkeypatch.setattr(memory_model, "make_async_client", fake_factory)
    settings = Settings()
    settings.jarvis_memory_profile = "or-grok-4.6"
    client, route = memory_model.make_memory_async_client(settings)
    assert client is not None
    assert seen["api_key"] == "memory-key"
    assert seen["base_url"] == "https://openrouter.ai/api/v1"
    assert seen["provider"] == route.provider
    assert seen["model"] == route.model
    assert (seen["timeout"], seen["max_retries"]) == (60, 0)
    assert route.profile == "or-grok-4.6"


@pytest.mark.parametrize("purpose", ["memory", "background"])
def test_enabled_source_floor_refuses_external_before_client_construction(monkeypatch, purpose):
    from jarvis.model_routing import AccessRoute, ResolvedModelRoute
    monkeypatch.setenv("JARVIS_MODEL_ROUTING_ENABLED", "1")
    external = ResolvedModelRoute(
        purpose, "fixture", "fixture", "openai", "https://fixture.invalid/v1",
        AccessRoute("direct_api", "openai_compatible", "provider_api", "OPENAI_API_KEY", "approved_external"),
        "OPENAI_API_KEY", "openai/fixture",
    )
    monkeypatch.setattr(memory_model, "resolve_model_route_checked", lambda *args, **kwargs: external)
    monkeypatch.setattr(memory_model, "make_route_client", lambda *args, **kwargs: pytest.fail("private source reached client"))
    factory = memory_model.make_memory_async_client if purpose == "memory" else memory_model.make_background_async_client
    with pytest.raises(memory_model.MemoryModelUnavailable, match="requires 'confidential'"):
        factory(Settings())


@pytest.mark.parametrize("purpose", ["memory", "background"])
def test_unexpected_enabled_route_failure_does_not_echo_provider_diagnostic(monkeypatch, purpose):
    monkeypatch.setenv("JARVIS_MODEL_ROUTING_ENABLED", "1")
    def fail(*args, **kwargs):
        raise RuntimeError("PRIVATE_ROUTE_DIAGNOSTIC_CANARY")
    monkeypatch.setattr(memory_model, "resolve_model_route_checked", fail)
    resolver = memory_model.resolve_memory_route if purpose == "memory" else memory_model.resolve_background_route
    with pytest.raises(memory_model.MemoryModelUnavailable) as caught:
        resolver(Settings())
    assert "error_type=RuntimeError" in str(caught.value)
    assert "PRIVATE_ROUTE_DIAGNOSTIC_CANARY" not in str(caught.value)
