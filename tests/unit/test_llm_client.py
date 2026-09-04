"""Unit tests for jarvis/llm_client.py (MORTIMER_OPTIMIZATION_PLAN.md
Phase 1, Rev 3.2, Path B, landing step (ii), tasks 4+5).

Fixtures only, no network: openai.OpenAI/AsyncOpenAI construction never
makes a network call (it only builds an httpx transport), and neither
does anthropic.Anthropic/AsyncAnthropic (verified in
tests/unit/test_anthropic_shim.py). The OpenRouter wrapper's .create()
tests use a fake completions object, never a real client.
"""

from __future__ import annotations

import openai
import pytest

from jarvis import llm_client
from jarvis.anthropic_shim import AnthropicChatShim, AsyncAnthropicChatShim


@pytest.fixture(autouse=True)
def _clean_native_env(monkeypatch):
    monkeypatch.delenv("JARVIS_ANTHROPIC_NATIVE", raising=False)


class TestNativeEnabled:
    def test_default_on(self):
        assert llm_client.native_enabled() is True

    def test_explicit_1_is_on(self, monkeypatch):
        monkeypatch.setenv("JARVIS_ANTHROPIC_NATIVE", "1")
        assert llm_client.native_enabled() is True

    def test_explicit_0_is_off(self, monkeypatch):
        monkeypatch.setenv("JARVIS_ANTHROPIC_NATIVE", "0")
        assert llm_client.native_enabled() is False

    def test_read_fresh_not_cached(self, monkeypatch):
        assert llm_client.native_enabled() is True
        monkeypatch.setenv("JARVIS_ANTHROPIC_NATIVE", "0")
        assert llm_client.native_enabled() is False
        monkeypatch.delenv("JARVIS_ANTHROPIC_NATIVE")
        assert llm_client.native_enabled() is True


class TestMakeSyncClientRouting:
    def test_anthropic_provider_native_on_returns_shim(self):
        c = llm_client.make_sync_client(
            api_key="sk-test", base_url="https://api.anthropic.com/v1/", provider="anthropic",
        )
        assert isinstance(c, AnthropicChatShim)

    def test_anthropic_provider_native_off_returns_openai(self, monkeypatch):
        monkeypatch.setenv("JARVIS_ANTHROPIC_NATIVE", "0")
        c = llm_client.make_sync_client(
            api_key="sk-test", base_url="https://api.anthropic.com/v1/", provider="anthropic",
        )
        assert isinstance(c, openai.OpenAI)

    def test_no_provider_falls_back_to_base_url_detection(self):
        # Settings-based client sites (jarvis/agents/base.py) have no
        # `provider` concept at all -- base_url alone must still route
        # correctly to the shim when it's an Anthropic endpoint.
        c = llm_client.make_sync_client(
            api_key="sk-test", base_url="https://api.anthropic.com/v1/",
        )
        assert isinstance(c, AnthropicChatShim)

    def test_non_anthropic_base_url_returns_plain_openai(self):
        c = llm_client.make_sync_client(
            api_key="sk-test", base_url="https://api.moonshot.cn/v1",
        )
        assert isinstance(c, openai.OpenAI)
        assert not isinstance(c, llm_client._OpenRouterCachingClient)

    def test_openrouter_provider_returns_wrapped_client(self):
        c = llm_client.make_sync_client(
            api_key="sk-test", base_url="https://openrouter.ai/api/v1", provider="openrouter",
        )
        assert isinstance(c, llm_client._OpenRouterCachingClient)

    def test_explicit_provider_overrides_base_url_mismatch(self):
        # A profile's declared provider is the authoritative source
        # (task 5's rationale) -- even if base_url alone would have
        # detected something else, an explicit provider="anthropic" wins.
        c = llm_client.make_sync_client(
            api_key="sk-test", base_url="https://custom-proxy.example.com/", provider="anthropic",
        )
        assert isinstance(c, AnthropicChatShim)

    def test_timeout_and_max_retries_reach_the_openai_client(self):
        # tests/unit/test_upgrade_agent.py's existing pattern (patches
        # openai.OpenAI itself) is the rigorous version of this; this is
        # the plain construction-doesn't-raise-and-values-land check.
        c = llm_client.make_sync_client(
            api_key="sk-test", base_url="https://api.moonshot.cn/v1",
            timeout=30.0, max_retries=0,
        )
        assert c.timeout == 30.0
        assert c.max_retries == 0

    def test_timeout_and_max_retries_reach_the_shim(self):
        c = llm_client.make_sync_client(
            api_key="sk-test", base_url="https://api.anthropic.com/v1/", provider="anthropic",
            timeout=30.0, max_retries=0,
        )
        assert c._anthropic.timeout == 30.0
        assert c._anthropic.max_retries == 0


class TestMakeAsyncClientRouting:
    def test_anthropic_provider_native_on_returns_shim(self):
        c = llm_client.make_async_client(
            api_key="sk-test", base_url="https://api.anthropic.com/v1/", provider="anthropic",
        )
        assert isinstance(c, AsyncAnthropicChatShim)

    def test_anthropic_provider_native_off_returns_openai(self, monkeypatch):
        monkeypatch.setenv("JARVIS_ANTHROPIC_NATIVE", "0")
        c = llm_client.make_async_client(
            api_key="sk-test", base_url="https://api.anthropic.com/v1/", provider="anthropic",
        )
        assert isinstance(c, openai.AsyncOpenAI)

    def test_openrouter_provider_returns_wrapped_client(self):
        c = llm_client.make_async_client(
            api_key="sk-test", base_url="https://openrouter.ai/api/v1", provider="openrouter",
        )
        assert isinstance(c, llm_client._OpenRouterCachingClient)


class TestOpenAIModuleAttributeLookup:
    """The one thing that MUST hold for tests/unit/test_upgrade_agent.py's
    existing `openai.OpenAI = FakeOpenAI` monkeypatch (no monkeypatch
    fixture, a raw module-attribute assignment with manual restore) to
    keep working after this module exists: llm_client.py must look up
    `openai.OpenAI`/`openai.AsyncOpenAI` at CALL time, never bind them at
    import time."""

    def test_sync_patch_on_openai_module_is_honored(self):
        constructed = {}

        class FakeOpenAI:
            def __init__(self, **kwargs):
                constructed.update(kwargs)

        original = openai.OpenAI
        openai.OpenAI = FakeOpenAI
        try:
            c = llm_client.make_sync_client(
                api_key="sk-test", base_url="https://api.moonshot.cn/v1",
                timeout=99.0, max_retries=0,
            )
        finally:
            openai.OpenAI = original
        assert isinstance(c, FakeOpenAI)
        assert constructed["api_key"] == "sk-test"
        assert constructed["timeout"] == 99.0
        assert constructed["max_retries"] == 0

    def test_async_patch_on_openai_module_is_honored(self):
        constructed = {}

        class FakeAsyncOpenAI:
            def __init__(self, **kwargs):
                constructed.update(kwargs)

        original = openai.AsyncOpenAI
        openai.AsyncOpenAI = FakeAsyncOpenAI
        try:
            c = llm_client.make_async_client(
                api_key="sk-test", base_url="https://api.moonshot.cn/v1",
            )
        finally:
            openai.AsyncOpenAI = original
        assert isinstance(c, FakeAsyncOpenAI)
        assert constructed["api_key"] == "sk-test"


# ---------------------------------------------------------------------------
# Task 4 — OpenRouter cache_control passthrough
# ---------------------------------------------------------------------------

class _FakeCompletions:
    def __init__(self):
        self.last_kwargs = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        return "sync-response"


class _FakeAsyncCompletions:
    def __init__(self):
        self.last_kwargs = None

    async def create(self, **kwargs):
        self.last_kwargs = kwargs
        return "async-response"


class TestOpenRouterCacheControl:
    def test_anthropic_model_gets_cache_control(self):
        fake = _FakeCompletions()
        wrapped = llm_client._SyncOpenRouterCompletions(fake, "openrouter")
        wrapped.create(model="anthropic/claude-sonnet-5", messages=[])
        assert fake.last_kwargs["extra_body"] == {"cache_control": {"type": "ephemeral"}}

    def test_non_anthropic_model_untouched(self):
        fake = _FakeCompletions()
        wrapped = llm_client._SyncOpenRouterCompletions(fake, "openrouter")
        wrapped.create(model="openai/gpt-5", messages=[])
        assert "extra_body" not in fake.last_kwargs

    def test_existing_extra_body_is_merged_not_replaced(self):
        fake = _FakeCompletions()
        wrapped = llm_client._SyncOpenRouterCompletions(fake, "openrouter")
        wrapped.create(model="anthropic/claude-sonnet-5", messages=[],
                       extra_body={"output_config": {"effort": "low"}})
        assert fake.last_kwargs["extra_body"] == {
            "output_config": {"effort": "low"},
            "cache_control": {"type": "ephemeral"},
        }

    def test_non_openrouter_provider_never_gets_cache_control(self):
        fake = _FakeCompletions()
        # Same model string, but the wrapper itself is only ever
        # constructed for provider == "openrouter" -- this proves the
        # underlying helper is provider-gated, not model-gated alone.
        wrapped = llm_client._SyncOpenRouterCompletions(fake, "openai")
        wrapped.create(model="anthropic/claude-sonnet-5", messages=[])
        assert "extra_body" not in fake.last_kwargs

    @pytest.mark.asyncio
    async def test_async_anthropic_model_gets_cache_control(self):
        fake = _FakeAsyncCompletions()
        wrapped = llm_client._AsyncOpenRouterCompletions(fake, "openrouter")
        await wrapped.create(model="anthropic/claude-fable-5", messages=[])
        assert fake.last_kwargs["extra_body"] == {"cache_control": {"type": "ephemeral"}}

    def test_wrapped_client_delegates_base_url(self):
        c = llm_client.make_sync_client(
            api_key="sk-test", base_url="https://openrouter.ai/api/v1", provider="openrouter",
        )
        # provider_from_base_url(str(client.base_url)) is what every
        # existing record_completion() call site does -- must still work
        # through the wrapper.
        from jarvis.usage_ledger import provider_from_base_url
        assert provider_from_base_url(str(c.base_url)) == "openrouter"

    def test_wrapped_client_routes_create_through_the_cache_wrapper(self):
        c = llm_client.make_sync_client(
            api_key="sk-test", base_url="https://openrouter.ai/api/v1", provider="openrouter",
        )
        # Swap in a fake completions object post-construction to observe
        # what create() actually receives, without a real network call.
        fake = _FakeCompletions()
        c.chat.completions._completions = fake
        c.chat.completions.create(model="anthropic/claude-sonnet-5", messages=[])
        assert fake.last_kwargs["extra_body"] == {"cache_control": {"type": "ephemeral"}}
