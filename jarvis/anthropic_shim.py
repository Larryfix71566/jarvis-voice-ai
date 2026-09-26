"""jarvis/anthropic_shim.py — a drop-in OpenAI-shaped client over Anthropic's
native Messages API.

MORTIMER_OPTIMIZATION_PLAN.md Phase 1 (Rev 3.2), Path B, landing step (i).

Why this exists: Anthropic's OpenAI-compatibility layer does not support
prompt caching (confirmed against platform.claude.com, 2026-09-01) — every
Anthropic-direct call site in this repo (jarvis/agents/base.py,
jarvis/agents/upgrade_agent.py, jarvis/council/council.py) is built against
`openai.OpenAI`/`AsyncOpenAI`'s `.chat.completions.create(...)` surface, and
caching requires the native `anthropic.Anthropic`/`AsyncAnthropic` client
instead. Rewriting those three call sites' request/response handling,
their trust/draft/tool-loop logic, and every test that scripts
`chat.completions.create` would be a much larger and riskier change than
translating at the boundary. This module IS that boundary: it accepts the
exact `model=`, `messages=`, `tools=`, `temperature=`, `extra_body=` shape
those call sites already send, and returns a real `openai.types.chat.
ChatCompletion` — so nothing downstream of `.create()` needs to know the
call went to a different API.

Verified against the real installed packages before writing a line of
translation logic (no guessing from memory — both were pip-installed and
introspected on 2026-09-01):
  - `anthropic==0.125.0` (what `pipecat-ai[...,anthropic]`'s
    `anthropic<1,>=0.49.0` constraint actually resolves to today).
  - `openai==2.53.0`, `httpx==0.28.1` (this repo's own
    requirements-lock.txt pins) — `openai`'s `APIStatusError`/
    `APIConnectionError`/`APITimeoutError` take plain `httpx.Response`/
    `httpx.Request` at this version (a newer openai pin uses a forked
    `httpx2`; this repo's pin does not, so S9 below needs no translation
    beyond swapping which exception class wraps the same httpx objects).
  - `output_config`, `cache_control`, `system` (str or block list),
    `tools`, `tool_choice`, `thinking`, `extra_body` are all named,
    non-beta parameters on `anthropic.Anthropic().messages.create` at
    0.125.0 — no `.beta.messages` namespace needed for anything this
    module does (pipecat's own Path A service uses `.beta.messages` only
    for interleaved-thinking betas this module never requests).
  - `openai.types.completion_usage.PromptTokensDetails` already has a
    native `cache_write_tokens` field alongside `cached_tokens` at this
    openai version — so cache-write tokens ride the SAME OpenAI-shaped
    field `jarvis.usage_ledger`'s OpenRouter alias reads (Phase 1 task 3),
    not a bolted-on extra attribute.

Rollback: this module is never imported except by `jarvis/llm_client.py`
(Phase 1 landing step (ii)), and that factory only returns a shim when
`JARVIS_ANTHROPIC_NATIVE` is unset/"1" AND the route is Anthropic-direct.
Setting `JARVIS_ANTHROPIC_NATIVE=0` means this file is never touched at
runtime.
"""

from __future__ import annotations

import json
import time
from typing import Any

import anthropic
import httpx
import openai
from openai.types.chat import ChatCompletion, ChatCompletionMessage
from openai.types.chat.chat_completion import Choice
from openai.types.chat.chat_completion_message_function_tool_call import (
    ChatCompletionMessageFunctionToolCall,
    Function,
)
from openai.types.completion_usage import CompletionUsage, PromptTokensDetails

# Automatic caching, one breakpoint slot (S6): sent on every request so each
# call in a multi-turn / multi-iteration loop can read the previous call's
# prefix. See the module docstring's "Verified against" note for why no
# `ttl` override is used here — 5-minute ephemeral is the safe default for
# loops that iterate in seconds, not minutes.
_AUTO_CACHE = {"type": "ephemeral"}
_LEADING_CACHE = {"type": "ephemeral"}  # S2: marks the stable system[0] block
_DEFAULT_MAX_TOKENS = 8192  # native max_tokens is required; this repo's
# compat-path calls never set it, relying on the provider default — 8192
# matches pipecat's own AnthropicLLMService default (Path A) so both paths
# behave the same way absent an explicit override.

_FINISH_REASON = {
    "end_turn": "stop",
    "max_tokens": "length",
    "stop_sequence": "stop",
    "tool_use": "tool_calls",
    "pause_turn": "stop",
    "refusal": "content_filter",
    "model_context_window_exceeded": "length",
}


class ShimError(Exception):
    """Raised for a request shape this shim deliberately does not support
    (S1/S8) — a caller finding out at the call site beats a silently
    dropped parameter."""


# --------------------------------------------------------------------------
# S1 — tools
# --------------------------------------------------------------------------

def _convert_tools(openai_tools: list[dict] | None) -> list[dict] | anthropic.NotGiven:
    if not openai_tools:
        return anthropic.NOT_GIVEN
    converted = []
    for t in openai_tools:
        if t.get("type") != "function":
            raise ShimError(
                f"anthropic_shim: unsupported tool type {t.get('type')!r} "
                "(only OpenAI 'function' tools are translated)"
            )
        fn = t["function"]
        converted.append({
            "name": fn["name"],
            "description": fn.get("description", ""),
            "input_schema": fn.get("parameters") or {"type": "object", "properties": {}},
        })
    return converted


# --------------------------------------------------------------------------
# S2-S4 — messages
# --------------------------------------------------------------------------

def _text_block(text: str, *, cache: bool = False) -> dict:
    block = {"type": "text", "text": text}
    if cache:
        block["cache_control"] = dict(_LEADING_CACHE)
    return block


def _convert_messages(
    openai_messages: list[dict],
) -> tuple[list[dict] | anthropic.NotGiven, list[dict]]:
    """Returns (system_blocks_or_NOT_GIVEN, anthropic_messages).

    S2: the LEADING run of role=='system' messages becomes the top-level
    `system` block list, in order; cache_control marks ONLY the first
    block (the agent's stable base prompt — base.py's `_system_prompt_for`
    / upgrade_agent.py's `self._system_prompt` / council.py's
    `system_prompt` argument — vs. blocks 2..n, which are the per-task
    procedure/skill/workflow injections base.py:511-555 appends and which
    differ run to run, so caching them would never hit).

    S3: a NON-leading role=='system' message (the D3 tool-failure
    constraint, PENDING_DRAFT_CONSTRAINT, executor notes) becomes a text
    block appended to the PRECEDING message when it is role=='user'
    (the tool-result turn — Anthropic allows text blocks after
    tool_result blocks in the same message) or a new user message
    otherwise. Sonnet 5 rejects role:'system' inside `messages` natively
    (only Fable 5.1/Mythos 5.1/Opus 4.8/Opus 5 accept it); translating
    unconditionally, rather than only for models that reject it, keeps
    the behaviour identical across every profile this shim serves.

    S4: assistant tool_calls -> tool_use blocks; role=='tool' ->
    tool_result blocks, merged into one user message per consecutive run
    (Anthropic requires all tool_results for one assistant turn in a
    single user message; this repo's loops already emit them
    consecutively, one dict per call, exactly the shape this expects).
    Consecutive same-role messages are merged (strict alternation is
    required natively).
    """
    i = 0
    system_blocks: list[dict] = []
    while i < len(openai_messages) and openai_messages[i]["role"] == "system":
        content = openai_messages[i].get("content") or ""
        if content:
            system_blocks.append(_text_block(content, cache=(len(system_blocks) == 0)))
        i += 1

    anthropic_messages: list[dict] = []

    def _last_role() -> str | None:
        return anthropic_messages[-1]["role"] if anthropic_messages else None

    def _append_block(role: str, block: dict) -> None:
        if _last_role() == role:
            anthropic_messages[-1]["content"].append(block)
        else:
            anthropic_messages.append({"role": role, "content": [block]})

    while i < len(openai_messages):
        m = openai_messages[i]
        role = m["role"]

        if role == "system":
            content = m.get("content") or ""
            if content:
                _append_block("user", _text_block(content))

        elif role == "user":
            content = m.get("content") or ""
            _append_block("user", _text_block(content))

        elif role == "tool":
            _append_block("user", {
                "type": "tool_result",
                "tool_use_id": m["tool_call_id"],
                "content": m.get("content") or "",
            })

        elif role == "assistant":
            blocks: list[dict] = []
            content = m.get("content")
            if content:
                blocks.append({"type": "text", "text": content})
            for tc in m.get("tool_calls") or []:
                blocks.append({
                    "type": "tool_use",
                    "id": tc["id"],
                    "name": tc["function"]["name"],
                    "input": json.loads(tc["function"]["arguments"] or "{}"),
                })
            if not blocks:
                # An assistant message with neither content nor tool_calls
                # is not meaningful to Anthropic (every message needs a
                # non-empty content list) — skip rather than send an
                # empty turn that would 400.
                i += 1
                continue
            if _last_role() == "assistant":
                anthropic_messages[-1]["content"].extend(blocks)
            else:
                anthropic_messages.append({"role": "assistant", "content": blocks})

        else:
            raise ShimError(f"anthropic_shim: unsupported message role {role!r}")

        i += 1

    if not anthropic_messages:
        raise ShimError("anthropic_shim: no messages after the leading system run")

    # S6: automatic caching, one more breakpoint, on the top-level request
    # (see create()) — nothing further needed here.
    return (system_blocks if system_blocks else anthropic.NOT_GIVEN), anthropic_messages


# --------------------------------------------------------------------------
# S5/S7 — response translation
# --------------------------------------------------------------------------

def _convert_response(msg: "anthropic.types.Message", *, model: str) -> ChatCompletion:
    text_parts = []
    tool_calls: list[ChatCompletionMessageFunctionToolCall] = []
    for block in msg.content:
        if block.type == "text":
            text_parts.append(block.text)
        elif block.type == "tool_use":
            tool_calls.append(ChatCompletionMessageFunctionToolCall(
                id=block.id,
                type="function",
                function=Function(name=block.name, arguments=json.dumps(block.input)),
            ))

    message = ChatCompletionMessage(
        role="assistant",
        content="".join(text_parts) or None,
        tool_calls=tool_calls or None,
    )
    finish_reason = _FINISH_REASON.get(msg.stop_reason or "end_turn", "stop")

    u = msg.usage
    cache_read = u.cache_read_input_tokens or 0
    cache_write = u.cache_creation_input_tokens or 0
    # S7: OpenAI-inclusive semantics — prompt_tokens covers the WHOLE
    # prompt (uncached + read + written), matching what usage_ledger's
    # existing `_CACHED_TOKEN_ALIASES` subtraction already assumes for the
    # compat path. Anthropic's own `input_tokens` is uncached-only.
    usage = CompletionUsage(
        prompt_tokens=u.input_tokens + cache_read + cache_write,
        completion_tokens=u.output_tokens,
        total_tokens=u.input_tokens + cache_read + cache_write + u.output_tokens,
        prompt_tokens_details=PromptTokensDetails(
            cached_tokens=cache_read,
            cache_write_tokens=cache_write,
        ),
    )

    return ChatCompletion(
        id=msg.id,
        object="chat.completion",
        created=int(time.time()),
        model=model,
        choices=[Choice(index=0, message=message, finish_reason=finish_reason)],
        usage=usage,
    )


# --------------------------------------------------------------------------
# S9 — error translation
# --------------------------------------------------------------------------

def _translate_error(exc: Exception) -> Exception:
    """Anthropic SDK exceptions -> the openai exception classes
    jarvis/agents/upgrade_agent.py:416-421's failover classifier
    `isinstance`-checks. Both SDKs' exception constructors take plain
    `httpx.Request`/`httpx.Response` at the versions this repo pins
    (verified 2026-09-01 — see module docstring); no field translation
    needed beyond swapping the class."""
    if isinstance(exc, anthropic.APITimeoutError):
        return openai.APITimeoutError(request=exc.request)
    if isinstance(exc, anthropic.APIConnectionError):
        return openai.APIConnectionError(message=str(exc), request=exc.request)
    if isinstance(exc, anthropic.APIStatusError):
        return openai.APIStatusError(str(exc), response=exc.response, body=exc.body)
    return exc


_SUPPORTED_KWARGS = {"model", "messages", "tools", "tool_choice", "temperature",
                     "extra_body", "max_tokens", "stream"}


def _build_request(**kwargs: Any) -> dict[str, Any]:
    unknown = set(kwargs) - _SUPPORTED_KWARGS
    if unknown:
        raise TypeError(f"anthropic_shim: unsupported chat.completions.create kwarg(s): {sorted(unknown)}")
    if kwargs.get("stream"):
        raise ShimError("anthropic_shim: stream=True is not supported (no Path B caller streams)")
    if "tool_choice" in kwargs:
        raise ShimError(
            "anthropic_shim: tool_choice is not translated (no call site sends it "
            "today) — implement S1's tool_choice mapping before using it"
        )
    system, messages = _convert_messages(kwargs["messages"])
    request: dict[str, Any] = {
        "model": kwargs["model"],
        "max_tokens": kwargs.get("max_tokens") or _DEFAULT_MAX_TOKENS,
        "messages": messages,
        "system": system,
        "tools": _convert_tools(kwargs.get("tools")),
        "cache_control": dict(_AUTO_CACHE),
    }
    if kwargs.get("temperature") is not None:
        request["temperature"] = kwargs["temperature"]
    extra_body = kwargs.get("extra_body")
    if extra_body:
        # Phase 1b: extra_body_for() emits {"output_config": {"effort": ...}}
        # for provider=='anthropic' — merged as top-level native request
        # fields, the same place `extra_body` would have landed on the
        # compat path (openai's extra_body is spread into the request body
        # too), so effort.py needs no Path-B-specific branch.
        request.update(extra_body)
    return request


class _ChatCompletionsShim:
    def __init__(self, client: "anthropic.Anthropic", model_holder: dict) -> None:
        self._client = client
        self._model_holder = model_holder

    def create(self, **kwargs: Any) -> ChatCompletion:
        request = _build_request(**kwargs)
        try:
            msg = self._client.messages.create(**request)
        except Exception as exc:  # noqa: BLE001 — translate, then re-raise
            raise _translate_error(exc) from exc
        return _convert_response(msg, model=kwargs["model"])


class _AsyncChatCompletionsShim:
    def __init__(self, client: "anthropic.AsyncAnthropic") -> None:
        self._client = client

    async def create(self, **kwargs: Any) -> ChatCompletion:
        request = _build_request(**kwargs)
        try:
            msg = await self._client.messages.create(**request)
        except Exception as exc:  # noqa: BLE001 — translate, then re-raise
            raise _translate_error(exc) from exc
        return _convert_response(msg, model=kwargs["model"])


def native_base_url(base_url: str | None) -> str | None:
    """Strip an OpenAI-compat-style trailing `/v1` (with or without a
    trailing slash) from `base_url` before handing it to the native SDK.

    Bug found 2026-09-02, before this shim was ever wired to a live call
    site: `anthropic.Anthropic`/`AsyncAnthropic` build every request path
    by concatenating `base_url`'s own path with the resource's OWN literal
    `/v1/messages` (verified against the installed anthropic==0.125.0's
    `_base_client._prepare_url` -- string concatenation, not `urljoin`
    replacement). Every `base_url` this repo actually configures already
    ends in `/v1/` (the OpenAI-compat convention -- `config/model_endpoints
    .yaml`, `.env`'s `OPENAI_BASE_URL`) -- forwarding that unchanged would
    concatenate to `/v1/v1/messages` and 404 every request. Stripping the
    suffix here, once, is what lets the shim accept the exact same
    `base_url` strings every existing call site already passes without
    each of them needing to know this native-vs-compat convention
    mismatch exists. A `base_url` that does NOT end in `/v1` (a bare host,
    or a proxy prefix with no `/v1`) passes through unchanged -- this only
    strips the one suffix the native SDK does not expect, never anything
    else in the path."""
    if not base_url:
        return None
    stripped = base_url.rstrip("/")
    if stripped.endswith("/v1"):
        stripped = stripped[: -len("/v1")]
    return stripped or None


class _ChatShimBase:
    """Shared `.chat.completions` / `.base_url` surface. `.base_url` is the
    ORIGINAL plain string passed in (not the native-SDK-adjusted one
    `native_base_url` derives, and not an `httpx.URL`) — every existing
    caller already does `provider_from_base_url(str(client.base_url))`,
    which only substring-matches "anthropic.com" and works the same
    whether or not a `/v1` suffix is present, and `str()` of a plain
    string is itself, so no caller needs to change."""

    def __init__(self, base_url: str | None) -> None:
        self.base_url = base_url or ""


class AnthropicChatShim(_ChatShimBase):
    """Sync drop-in for `openai.OpenAI` — used by
    `jarvis/council/council.py` and `jarvis/agents/upgrade_agent.py`."""

    def __init__(self, *, api_key: str, base_url: str | None = None,
                 timeout: float | None = None, max_retries: int | None = None) -> None:
        super().__init__(base_url)
        client_kwargs: dict[str, Any] = {"api_key": api_key}
        resolved_base_url = native_base_url(base_url)
        if resolved_base_url is not None:
            client_kwargs["base_url"] = resolved_base_url
        if timeout is not None:
            client_kwargs["timeout"] = timeout
        if max_retries is not None:
            client_kwargs["max_retries"] = max_retries
        self._anthropic = anthropic.Anthropic(**client_kwargs)
        self.chat = type("_Chat", (), {"completions": _ChatCompletionsShim(self._anthropic, {})})()


class AsyncAnthropicChatShim(_ChatShimBase):
    """Async drop-in for `openai.AsyncOpenAI` — used by
    `jarvis/agents/base.py`."""

    def __init__(self, *, api_key: str, base_url: str | None = None,
                 timeout: float | None = None, max_retries: int | None = None) -> None:
        super().__init__(base_url)
        client_kwargs: dict[str, Any] = {"api_key": api_key}
        resolved_base_url = native_base_url(base_url)
        if resolved_base_url is not None:
            client_kwargs["base_url"] = resolved_base_url
        if timeout is not None:
            client_kwargs["timeout"] = timeout
        if max_retries is not None:
            client_kwargs["max_retries"] = max_retries
        self._anthropic = anthropic.AsyncAnthropic(**client_kwargs)
        self.chat = type("_Chat", (), {"completions": _AsyncChatCompletionsShim(self._anthropic)})()
