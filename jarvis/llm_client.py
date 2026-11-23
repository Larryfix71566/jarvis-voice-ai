"""jarvis/llm_client.py — the one factory for OpenAI-compatible API clients
(sub-agents, executor, council/planning/research) on gateways that are still
allowed, such as OpenRouter's non-retired models and SAYGM.

Larry 2026-11-23: Anthropic, OpenAI, Kimi (Moonshot) and DeepSeek are never
reached per token. Their models run only through the subscription routes
(jarvis/subscription.py), and jarvis.provider_access.require_not_retired
refuses their API hosts, provider labels and gateway model slugs here, at
client construction AND on every request, in every access mode. The old
native Anthropic shim (jarvis/anthropic_shim.py) is gone.

`openai.OpenAI`/`openai.AsyncOpenAI` are looked up as module attributes at
call time so a test's `monkeypatch.setattr(openai, "OpenAI", Fake)` works.
"""

from __future__ import annotations

import time
from functools import wraps
from typing import Any

import openai
import httpx

from jarvis.usage_ledger import ApiCompletionMetadata, provider_from_base_url
from jarvis.provider_access import (
    ProviderAccessError, require_api_access, require_api_request, require_not_retired,
    selective_api_policy,
)


def _instrument_completion(client: Any, provider: str, *, asynchronous: bool, base_url: str | None = None) -> Any:
    """Measure this API adapter without changing its client/response identity.

    The wrapper forwards every argument unchanged and does not write a ledger
    row: existing record_completion callers remain the single accounting owner.
    Streaming durations cannot be recovered from the initial SDK return and
    are deliberately left unknown. API billing labels describe the adapter,
    not verified account charges. No model/provider response text is inspected.
    """
    completions = getattr(getattr(client, "chat", None), "completions", None)
    create = getattr(completions, "create", None)
    if not callable(create) or getattr(create, "_mortimer_measured", False):
        return client
    route = "saygm" if provider == "saygm" else "direct_api"
    billing = "saygm_credit" if provider == "saygm" else "provider_api"

    def mark(response: Any, kwargs: dict[str, Any], started: float) -> Any:
        if kwargs.get("stream") is True:
            # A foreign test/cache client may reuse a previous object. Never
            # let its earlier non-streaming duration describe this stream.
            try:
                if isinstance(getattr(response, "_mortimer_api_call", None), ApiCompletionMetadata):
                    object.__delattr__(response, "_mortimer_api_call")
            except (AttributeError, TypeError):
                pass
            return response
        metadata = ApiCompletionMetadata(route, billing, (time.monotonic() - started) * 1000)
        try:
            object.__setattr__(response, "_mortimer_api_call", metadata)
        except (AttributeError, TypeError):
            # Immutable/foreign responses keep unknown measurements. Never
            # replace the result with a proxy or infer timing retrospectively.
            pass
        return response

    if asynchronous:
        @wraps(create)
        async def measured(**kwargs: Any) -> Any:
            _require_safe_api_transport(client)
            require_api_request(kwargs, provider=provider,
                                base_url=str(getattr(client, "base_url", base_url) or ""))
            started = time.monotonic()
            return mark(await create(**kwargs), kwargs, started)
    else:
        @wraps(create)
        def measured(**kwargs: Any) -> Any:
            _require_safe_api_transport(client)
            require_api_request(kwargs, provider=provider,
                                base_url=str(getattr(client, "base_url", base_url) or ""))
            started = time.monotonic()
            return mark(create(**kwargs), kwargs, started)
    measured._mortimer_measured = True
    try:
        completions.create = measured
    except (AttributeError, TypeError):
        pass
    return client


def _require_safe_api_transport(client: Any) -> None:
    if not selective_api_policy():
        return
    transport = getattr(client, "_client", None)
    if isinstance(transport, (httpx.Client, httpx.AsyncClient)) and transport.follow_redirects:
        raise ProviderAccessError("API transport must not follow redirects under selective retirement")


def _pin_api_transport(client: Any) -> None:
    # The SDK defaults to following redirects. A known gateway must never
    # redirect a credential-bearing request to a retired or unknown provider.
    transport = getattr(client, "_client", None)
    if selective_api_policy() and isinstance(transport, (httpx.Client, httpx.AsyncClient)):
        transport.follow_redirects = False


def _resolve_provider(provider: str | None, base_url: str | None) -> str:
    # No base_url would let the openai SDK fall back to OPENAI_BASE_URL or
    # api.openai.com: a paid API this module never reaches (Larry 2026-11-23).
    if not base_url:
        raise ProviderAccessError(
            "an API client needs an explicit non-retired endpoint; no paid API call was made")
    return provider or provider_from_base_url(base_url)


def _client_kwargs(api_key: str, base_url: str | None,
                   timeout: float | None, max_retries: int | None) -> dict[str, Any]:
    kwargs: dict[str, Any] = {"api_key": api_key, "base_url": base_url}
    if timeout is not None:
        kwargs["timeout"] = timeout
    if max_retries is not None:
        kwargs["max_retries"] = max_retries
    return kwargs


def make_async_client(*, api_key: str, base_url: str | None, provider: str | None = None,
                       model: str | None = None, timeout: float | None = None,
                       max_retries: int | None = None) -> Any:
    """Async drop-in for `openai.AsyncOpenAI(...)` — used by
    `jarvis/agents/base.py`'s four client-construction sites (the
    default/fallback settings client, the boot-time `model_profile`
    resolution, and the per-run `resolve_model_profile()` override path).

    A construction-time `model` naming a retired vendor is refused here;
    the per-call `.create(model=...)` slug is checked again on every request."""
    resolved = _resolve_provider(provider, base_url)
    require_api_access(provider=resolved, base_url=base_url)
    require_not_retired(model=model)
    kwargs = _client_kwargs(api_key, base_url, timeout, max_retries)
    client = openai.AsyncOpenAI(**kwargs)
    _pin_api_transport(client)
    return _instrument_completion(client, resolved, asynchronous=True, base_url=base_url)


def make_sync_client(*, api_key: str, base_url: str | None, provider: str | None = None,
                      model: str | None = None, timeout: float | None = None,
                      max_retries: int | None = None) -> Any:
    """Sync drop-in for `openai.OpenAI(...)` — used by
    `jarvis/agents/upgrade_agent.py`'s `_build_client()` and
    `jarvis/council/council.py`'s `_call_profile()`. See
    `make_async_client` for the decision rules; identical, sync-flavoured."""
    resolved = _resolve_provider(provider, base_url)
    require_api_access(provider=resolved, base_url=base_url)
    require_not_retired(model=model)
    kwargs = _client_kwargs(api_key, base_url, timeout, max_retries)
    client = openai.OpenAI(**kwargs)
    _pin_api_transport(client)
    return _instrument_completion(client, resolved, asynchronous=False, base_url=base_url)
