"""Unit tests for jarvis/llm_client.py.

Larry 2026-11-23: the Anthropic, OpenAI, Kimi (Moonshot) and DeepSeek
pay-per-token APIs are retired. llm_client now builds only a plain
openai.OpenAI / AsyncOpenAI for a non-retired OpenAI-compatible endpoint
(OpenRouter, SAYGM) and refuses a retired vendor's provider, host or model
slug before any client exists. Fixtures only, no network: constructing an
openai client never makes a network call.
"""

from __future__ import annotations

import openai
import pytest

from jarvis import llm_client
from jarvis.provider_access import ProviderAccessError

OPENROUTER = "https://openrouter.ai/api/v1"


class TestRetiredVendorsRefused:
    @pytest.mark.parametrize("provider", ["anthropic", "openai", "moonshot", "deepseek"])
    def test_retired_provider_refused_sync(self, provider):
        with pytest.raises(ProviderAccessError, match="retired"):
            llm_client.make_sync_client(api_key="sk-test", base_url=OPENROUTER, provider=provider)

    @pytest.mark.parametrize("provider", ["anthropic", "openai", "moonshot", "deepseek"])
    def test_retired_provider_refused_async(self, provider):
        with pytest.raises(ProviderAccessError, match="retired"):
            llm_client.make_async_client(api_key="sk-test", base_url=OPENROUTER, provider=provider)

    @pytest.mark.parametrize("base_url", [
        "https://api.anthropic.com/v1/",
        "https://api.openai.com/v1",
        "https://api.moonshot.cn/v1",
        "https://api.moonshot.ai/v1",
        "https://api.kimi.com/coding/v1",
        "https://api.deepseek.com/v1",
    ])
    def test_retired_host_refused_without_provider(self, base_url):
        with pytest.raises(ProviderAccessError, match="retired"):
            llm_client.make_sync_client(api_key="sk-test", base_url=base_url)
        with pytest.raises(ProviderAccessError, match="retired"):
            llm_client.make_async_client(api_key="sk-test", base_url=base_url)

    @pytest.mark.parametrize("model", [
        "anthropic/claude-sonnet-5", "openai/gpt-5.1", "moonshotai/kimi-k2", "deepseek/deepseek-v4",
    ])
    def test_retired_model_slug_refused_through_openrouter(self, model):
        with pytest.raises(ProviderAccessError, match="retired"):
            llm_client.make_sync_client(api_key="sk-test", base_url=OPENROUTER,
                                        provider="openrouter", model=model)


class TestAllowedEndpoints:
    def test_openrouter_sync_is_plain_openai(self):
        c = llm_client.make_sync_client(api_key="sk-test", base_url=OPENROUTER, provider="openrouter")
        assert isinstance(c, openai.OpenAI)

    def test_openrouter_async_is_plain_async_openai(self):
        c = llm_client.make_async_client(api_key="sk-test", base_url=OPENROUTER, provider="openrouter")
        assert isinstance(c, openai.AsyncOpenAI)

    def test_non_retired_model_slug_allowed(self):
        c = llm_client.make_sync_client(api_key="sk-test", base_url=OPENROUTER,
                                        provider="openrouter", model="x-ai/grok-4.3")
        assert isinstance(c, openai.OpenAI)

    def test_timeout_and_max_retries_reach_the_openai_client(self):
        c = llm_client.make_sync_client(api_key="sk-test", base_url=OPENROUTER,
                                        timeout=30.0, max_retries=0)
        assert c.timeout == 30.0
        assert c.max_retries == 0

    def test_base_url_still_identifies_provider_for_usage(self):
        from jarvis.usage_ledger import provider_from_base_url
        c = llm_client.make_sync_client(api_key="sk-test", base_url=OPENROUTER, provider="openrouter")
        assert provider_from_base_url(str(c.base_url)) == "openrouter"


class TestOpenAIModuleAttributeLookup:
    """llm_client must look up openai.OpenAI / AsyncOpenAI at CALL time so a
    raw module-attribute monkeypatch in other tests keeps working."""

    def test_sync_patch_on_openai_module_is_honored(self):
        constructed = {}

        class FakeOpenAI:
            def __init__(self, **kwargs):
                constructed.update(kwargs)

        original = openai.OpenAI
        openai.OpenAI = FakeOpenAI
        try:
            c = llm_client.make_sync_client(api_key="sk-test", base_url=OPENROUTER,
                                            timeout=99.0, max_retries=0)
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
            c = llm_client.make_async_client(api_key="sk-test", base_url=OPENROUTER)
        finally:
            openai.AsyncOpenAI = original
        assert isinstance(c, FakeAsyncOpenAI)
        assert constructed["api_key"] == "sk-test"


def test_missing_base_url_is_refused_before_sdk_defaults_apply(monkeypatch):
    # The openai SDK would otherwise read OPENAI_BASE_URL or use api.openai.com.
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.anthropic.com/v1/")
    with pytest.raises(ProviderAccessError):
        llm_client.make_async_client(api_key="sk-test", base_url=None)
    with pytest.raises(ProviderAccessError):
        llm_client.make_sync_client(api_key="sk-test", base_url="")
