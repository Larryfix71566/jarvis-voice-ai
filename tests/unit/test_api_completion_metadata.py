"""WS-05 prospective API attribution; actual client factory and ledger boundary."""
import asyncio
from types import SimpleNamespace

import pytest

from jarvis import llm_client, usage_ledger


def completion():
    return SimpleNamespace(id="synthetic-response", usage=SimpleNamespace(prompt_tokens=2, completion_tokens=3),
                           choices=[SimpleNamespace(message=SimpleNamespace(content="public fixture"))])


async def test_actual_async_factory_keeps_identity_and_forwards_arguments_without_writing(monkeypatch):
    response, observed = completion(), []
    async def create(**kwargs):
        observed.append(kwargs)
        return response
    sdk = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setattr(llm_client.openai, "AsyncOpenAI", lambda **_: sdk)
    ticks = iter([10.0, 10.025])
    monkeypatch.setattr(llm_client, "time", SimpleNamespace(monotonic=lambda: next(ticks)))
    monkeypatch.setattr(usage_ledger, "record_call", lambda **_: pytest.fail("factory must not record/double-count"))
    client = llm_client.make_async_client(api_key="synthetic-key", base_url="https://api.openai.com/v1", provider="openai")
    assert client is sdk
    kwargs = {"model": "synthetic-model", "messages": [{"role": "user", "content": "public fixture"}],
              "tools": [{"type": "function", "function": {"name": "fixture", "parameters": {}}}], "max_tokens": 32}
    result = await client.chat.completions.create(**kwargs)
    assert result is response and observed == [kwargs]
    assert result._mortimer_api_call.route_name == "direct_api"
    assert result._mortimer_api_call.billing_source == "provider_api"
    assert result._mortimer_api_call.duration_ms == pytest.approx(25)


def test_sync_factory_keeps_native_provider_class_and_measurement(monkeypatch):
    response = completion()
    class NativeShim:
        def __init__(self, **_):
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=lambda **_: response))
    monkeypatch.setattr(llm_client, "AnthropicChatShim", NativeShim)
    client = llm_client.make_sync_client(api_key="synthetic-key", base_url="https://api.anthropic.com/v1", provider="anthropic")
    assert isinstance(client, NativeShim)
    assert client.chat.completions.create(model="synthetic", messages=[]) is response
    assert response._mortimer_api_call.duration_ms >= 0


async def test_openrouter_cache_control_is_preserved_under_measurement(monkeypatch):
    response, observed = completion(), []
    async def create(**kwargs):
        observed.append(kwargs)
        return response
    sdk = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setattr(llm_client.openai, "AsyncOpenAI", lambda **_: sdk)
    client = llm_client.make_async_client(api_key="synthetic-key", base_url="https://openrouter.ai/api/v1", provider="openrouter")
    assert await client.chat.completions.create(model="anthropic/fixture", messages=[], extra_body={"other": "kept"}) is response
    assert observed[0]["extra_body"] == {"other": "kept", "cache_control": {"type": "ephemeral"}}
    assert response._mortimer_api_call.route_name == "direct_api"


async def test_saygm_transport_is_not_relabelled_as_direct_api(monkeypatch):
    response = completion()
    async def create(**_):
        return response
    sdk = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setattr(llm_client.openai, "AsyncOpenAI", lambda **_: sdk)
    client = llm_client.make_async_client(api_key="synthetic-key", base_url="https://api.saygm.com/v1", provider="saygm")
    await client.chat.completions.create(model="fixture-TEE", messages=[])
    assert response._mortimer_api_call.route_name == "saygm"
    assert response._mortimer_api_call.billing_source == "saygm_credit"


async def test_saygm_actual_endpoint_inference_has_correct_metadata_without_provider_override(monkeypatch):
    response = completion()
    async def create(**_):
        return response
    sdk = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setattr(llm_client.openai, "AsyncOpenAI", lambda **_: sdk)
    client = llm_client.make_async_client(api_key="synthetic-key", base_url="https://api.saygm.com/v1")
    await client.chat.completions.create(model="fixture", messages=[])
    assert response._mortimer_api_call.route_name == "saygm"
    assert response._mortimer_api_call.billing_source == "saygm_credit"
    assert usage_ledger.provider_from_base_url("https://api.saygm.com.evil.invalid/v1") == "unknown"
    assert usage_ledger.provider_from_base_url("https://evil.invalid/?target=api.saygm.com") == "unknown"


async def test_streaming_initial_return_is_not_fabricated_as_full_duration(monkeypatch):
    stream = SimpleNamespace()
    async def create(**_):
        return stream
    sdk = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setattr(llm_client.openai, "AsyncOpenAI", lambda **_: sdk)
    client = llm_client.make_async_client(api_key="synthetic-key", base_url="https://api.openai.com/v1", provider="openai")
    await client.chat.completions.create(model="fixture", messages=[])
    assert isinstance(stream._mortimer_api_call, usage_ledger.ApiCompletionMetadata)
    assert await client.chat.completions.create(model="fixture", messages=[], stream=True) is stream
    assert not hasattr(stream, "_mortimer_api_call")


async def test_failed_call_keeps_original_exception(monkeypatch):
    class ProviderError(RuntimeError):
        pass
    error = ProviderError("synthetic-error")
    async def create(**_):
        raise error
    sdk = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setattr(llm_client.openai, "AsyncOpenAI", lambda **_: sdk)
    client = llm_client.make_async_client(api_key="synthetic-key", base_url=None, provider="openai")
    with pytest.raises(ProviderError) as raised:
        await client.chat.completions.create(model="fixture", messages=[])
    assert raised.value is error


async def test_async_cancellation_reaches_original_provider_and_records_nothing(monkeypatch):
    entered, cancelled = asyncio.Event(), asyncio.Event()
    async def create(**_):
        entered.set()
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            cancelled.set()
            raise
    sdk = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setattr(llm_client.openai, "AsyncOpenAI", lambda **_: sdk)
    monkeypatch.setattr(usage_ledger, "record_call", lambda **_: pytest.fail("cancelled attempt invented accounting"))
    client = llm_client.make_async_client(api_key="synthetic-key", base_url=None, provider="openai")
    task = asyncio.create_task(client.chat.completions.create(model="fixture", messages=[]))
    await asyncio.wait_for(entered.wait(), timeout=1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert cancelled.is_set()


def test_prospective_attribution_is_saved_once_in_real_ledger(tmp_path, monkeypatch):
    import sqlite3
    monkeypatch.setenv("JARVIS_COSTS_DB", str(tmp_path / "costs.db"))
    monkeypatch.setattr(usage_ledger, "DB_PATH", tmp_path / "costs.db")
    response = completion()
    sdk = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **_: response)))
    monkeypatch.setattr(llm_client.openai, "OpenAI", lambda **_: sdk)
    client = llm_client.make_sync_client(api_key="synthetic-key", base_url=None, provider="openai")
    result = client.chat.completions.create(model="synthetic-model", messages=[])
    usage_ledger.record_completion("analyst", "openai", "synthetic-model", result)
    with sqlite3.connect(tmp_path / "costs.db") as conn:
        rows = conn.execute("SELECT route_name,billing_source,duration_ms,usage_known,input_tokens,output_tokens FROM llm_calls").fetchall()
    assert len(rows) == 1
    assert rows[0][0:2] == ("direct_api", "provider_api")
    assert rows[0][2] >= 0
    assert rows[0][3:] == (1, 2, 3)


def test_ledger_accepts_only_local_metadata_without_inventing_historical_values(monkeypatch):
    observed = []
    monkeypatch.setattr(usage_ledger, "record_call", lambda **kwargs: observed.append(kwargs))
    response = completion()
    response._mortimer_api_call = usage_ledger.ApiCompletionMetadata("direct_api", "provider_api", 12.5)
    usage_ledger.record_completion("fixture", "openai", "model", response)
    assert observed[-1]["route_name"] == "direct_api"
    assert observed[-1]["billing_source"] == "provider_api"
    assert observed[-1]["duration_ms"] == 12.5
    # Provider JSON extras and old completions are not locally verified tags.
    response._mortimer_api_call = {"route_name": "subscription", "billing_source": "subscription", "duration_ms": 0}
    usage_ledger.record_completion("fixture", "openai", "model", response)
    assert observed[-1]["route_name"] is None
    assert observed[-1]["billing_source"] is None
    assert observed[-1]["duration_ms"] is None
    assert "public fixture" not in str(observed)


def test_explicit_adapter_metadata_remains_authoritative(monkeypatch):
    observed = []
    monkeypatch.setattr(usage_ledger, "record_call", lambda **kwargs: observed.append(kwargs))
    response = completion()
    response._mortimer_api_call = usage_ledger.ApiCompletionMetadata("direct_api", "provider_api", 12.5)
    usage_ledger.record_completion("fixture", "custom", "model", response,
                                  route_name="explicit", billing_source="explicit", duration_ms=42)
    assert observed[-1]["route_name"] == observed[-1]["billing_source"] == "explicit"
    assert observed[-1]["duration_ms"] == 42
