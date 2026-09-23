import pytest

import jarvis.memory_model as memory_model


class Settings:
    jarvis_memory_profile = "claude-sonnet-5"
    jarvis_background_profile = "claude-sonnet-5"
    openai_model = "supervisor-haiku"
    openai_api_key = "supervisor-key"
    openai_base_url = "https://supervisor.invalid/v1"


def test_memory_route_is_independent_of_supervisor_settings(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "memory-key")
    monkeypatch.setenv("OPENAI_MODEL", "supervisor-haiku")
    route = memory_model.resolve_memory_route(Settings())
    assert route.profile == "claude-sonnet-5"
    assert route.model == "claude-sonnet-5"
    assert route.provider == "anthropic"
    assert route.api_key_env == "ANTHROPIC_API_KEY"
    assert route.model != Settings.openai_model
    assert route.base_url != Settings.openai_base_url


def test_memory_route_fails_closed_when_its_credential_is_missing(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(memory_model.MemoryModelUnavailable, match="ANTHROPIC_API_KEY"):
        memory_model.resolve_memory_route(Settings())


def test_memory_client_factory_uses_resolved_route(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "memory-key")
    seen = {}

    def fake_factory(**kwargs):
        seen.update(kwargs)
        return object()

    monkeypatch.setattr(memory_model, "make_async_client", fake_factory)
    client, route = memory_model.make_memory_async_client(Settings())
    assert client is not None
    assert seen == {
        "api_key": "memory-key",
        "base_url": "https://api.anthropic.com/v1/",
        "provider": "anthropic",
        "model": "claude-sonnet-5",
        "timeout": 60,
        "max_retries": 0,
    }
    assert route.profile == "claude-sonnet-5"


def test_background_route_is_independent_of_supervisor_settings(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "background-key")
    route = memory_model.resolve_background_route(Settings())
    assert route.profile == "claude-sonnet-5"
    assert route.model == "claude-sonnet-5"
    assert route.model != Settings.openai_model
    assert route.api_key_env == "ANTHROPIC_API_KEY"


def test_background_route_fails_closed_when_its_credential_is_missing(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(memory_model.MemoryModelUnavailable, match="background model profile"):
        memory_model.resolve_background_route(Settings())
