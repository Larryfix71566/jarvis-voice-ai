"""jarvis/llm_client.py — the one decision point: native Anthropic client
(jarvis/anthropic_shim.py, translating to the Messages API so prompt
caching works) or the plain OpenAI-compatible client, for every Path-B
call site (sub-agents, executor, council/planning/research).

MORTIMER_OPTIMIZATION_PLAN.md Phase 1 (Rev 3.2), Path B, landing step (ii),
task 5 (client factory + call sites) + task 4 (OpenRouter cache_control).

Design:
  - `native_enabled()` reads `JARVIS_ANTHROPIC_NATIVE` FRESH on every call
    (never cached at import time) — unset or "1" means native is on,
    "0" restores today's compat-everywhere behaviour. This is the one
    kill switch for the whole of Path B: a `.env` edit and a restart,
    never a code change, per the plan's rollback design.
  - Provider resolution: a caller passes `provider=` when it has one (a
    registry profile's own `provider:` field — the authoritative source,
    since one host can carry more than one provider's models, e.g.
    OpenRouter); when it doesn't (the Settings-based voice-model client,
    which has no provider concept at all) `provider=None` is fine — this
    module falls back to `provider_from_base_url(base_url)` itself, so
    every call site gets the same fallback without repeating the idiom.
    (The plan's task-5 text sketches callers doing `profile.get(
    "provider") or provider_from_base_url(...)` themselves; doing the
    fallback here instead is a simplification found while wiring the
    real call sites — same result, one implementation instead of four.)
  - `provider == "anthropic"` and native enabled -> the shim
    (`AnthropicChatShim`/`AsyncAnthropicChatShim`). Everything else ->
    the real `openai.OpenAI`/`AsyncOpenAI`, looked up as `openai.OpenAI`/
    `openai.AsyncOpenAI` (an ATTRIBUTE lookup on the `openai` module at
    call time, never `from openai import OpenAI`) so a test's
    `monkeypatch.setattr(openai, "OpenAI", Fake)` (tests/unit/
    test_upgrade_agent.py:169-174's existing pattern) keeps working —
    binding the name at import time here would freeze it to the
    original class before any test patch could apply.
  - `provider == "openrouter"`: task 4. OpenRouter documents `cache_control`
    passthrough for Anthropic models routed through its OpenAI-compatible
    API, keyed off the vendor-prefixed model string ("anthropic/claude-
    sonnet-5") — the provider string alone can't distinguish an
    anthropic/* request from an openai/* one on the SAME openrouter.ai
    base_url, so this has to be a per-call decision, not a per-client
    one. The returned client is wrapped so `.chat.completions.create(...)`
    merges `extra_body={"cache_control": {"type": "ephemeral"}}` in
    exactly when `model` (the per-call kwarg, read fresh on every call —
    never a construction-time guess) starts with "anthropic/"; every
    other provider's client is returned completely unwrapped, unchanged
    from today.
"""

from __future__ import annotations

import os
from typing import Any

import openai

from jarvis.anthropic_shim import AnthropicChatShim, AsyncAnthropicChatShim
from jarvis.usage_ledger import provider_from_base_url


def native_enabled() -> bool:
    """JARVIS_ANTHROPIC_NATIVE: unset or "1" -> native Path B on; "0" ->
    today's OpenAI-compat client everywhere. Read fresh every call (not
    cached at import time) so `monkeypatch.setenv(...)` in a test, or an
    env change without a process restart, takes effect immediately."""
    return os.environ.get("JARVIS_ANTHROPIC_NATIVE", "1") != "0"


def _resolve_provider(provider: str | None, base_url: str | None) -> str:
    return provider or provider_from_base_url(base_url or "")


def _openrouter_cache_extra_body(provider: str, model: str | None) -> dict[str, Any]:
    """Phase 1 task 4. `model` is the per-call kwarg, not anything fixed
    at client construction — the same client can, in principle, be asked
    for both an anthropic/* and a non-anthropic/* completion, and only
    the former gets the cache_control breakpoint."""
    if provider == "openrouter" and (model or "").startswith("anthropic/"):
        return {"cache_control": {"type": "ephemeral"}}
    return {}


def _merge_cache_control(kwargs: dict[str, Any], provider: str) -> dict[str, Any]:
    extra = _openrouter_cache_extra_body(provider, kwargs.get("model"))
    if not extra:
        return kwargs
    merged = dict(kwargs)
    merged["extra_body"] = {**(kwargs.get("extra_body") or {}), **extra}
    return merged


class _SyncOpenRouterCompletions:
    def __init__(self, completions: Any, provider: str) -> None:
        self._completions = completions
        self._provider = provider

    def create(self, **kwargs: Any) -> Any:
        return self._completions.create(**_merge_cache_control(kwargs, self._provider))


class _AsyncOpenRouterCompletions:
    def __init__(self, completions: Any, provider: str) -> None:
        self._completions = completions
        self._provider = provider

    async def create(self, **kwargs: Any) -> Any:
        return await self._completions.create(**_merge_cache_control(kwargs, self._provider))


class _OpenRouterCachingClient:
    """Wraps a real `openai.OpenAI`/`AsyncOpenAI` client so an OpenRouter-
    routed `anthropic/*` request gets Phase 1 task 4's `cache_control`
    passthrough. `.base_url` and everything else the wrapped client has
    delegate straight through via `__getattr__` — `provider_from_base_url
    (str(client.base_url))`, what every existing `record_completion()`
    call site does, is unaffected. Only `provider == "openrouter"` clients
    are ever wrapped; every other provider's client is returned exactly
    as it is today."""

    def __init__(self, client: Any, provider: str, completions_cls: type) -> None:
        self._client = client
        self.chat = type(
            "_Chat", (), {"completions": completions_cls(client.chat.completions, provider)}
        )()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._client, name)


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

    `model=` is accepted for interface symmetry with `make_sync_client`
    and the plan's documented signature; it plays no role in the
    native-vs-compat decision (that's `provider` + `native_enabled()`
    only) or in the OpenRouter wrapping decision (that's read per-call
    from the actual `.create(model=...)` kwarg, which is the only place
    a per-call model can be trusted)."""
    resolved = _resolve_provider(provider, base_url)
    kwargs = _client_kwargs(api_key, base_url, timeout, max_retries)
    if resolved == "anthropic" and native_enabled():
        return AsyncAnthropicChatShim(**kwargs)
    client = openai.AsyncOpenAI(**kwargs)
    if resolved == "openrouter":
        return _OpenRouterCachingClient(client, resolved, _AsyncOpenRouterCompletions)
    return client


def make_sync_client(*, api_key: str, base_url: str | None, provider: str | None = None,
                      model: str | None = None, timeout: float | None = None,
                      max_retries: int | None = None) -> Any:
    """Sync drop-in for `openai.OpenAI(...)` — used by
    `jarvis/agents/upgrade_agent.py`'s `_build_client()` and
    `jarvis/council/council.py`'s `_call_profile()`. See
    `make_async_client` for the decision rules; identical, sync-flavoured."""
    resolved = _resolve_provider(provider, base_url)
    kwargs = _client_kwargs(api_key, base_url, timeout, max_retries)
    if resolved == "anthropic" and native_enabled():
        return AnthropicChatShim(**kwargs)
    client = openai.OpenAI(**kwargs)
    if resolved == "openrouter":
        return _OpenRouterCachingClient(client, resolved, _SyncOpenRouterCompletions)
    return client
