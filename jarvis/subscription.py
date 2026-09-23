"""Official subscription-runtime adapter for text-only model calls.

This adapter intentionally exposes no tools. Mortimer's existing MCP and
sandbox tool loops must not be bypassed by a CLI process. Tool-capable
subscription execution is a separate capability gate.
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
from types import SimpleNamespace
from typing import Any


class SubscriptionRuntimeError(RuntimeError):
    pass


_API_AUTH_ENV_VARS = frozenset({
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_BASE_URL",
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "OPENROUTER_API_KEY",
    "OPENROUTER_BASE_URL",
    "CODEX_API_KEY",
    "CODEX_BASE_URL",
})


def _subscription_env() -> dict[str, str]:
    """Return a subprocess environment that cannot silently select API billing.

    The provider CLIs must authenticate through their own subscription login
    and keychain/session mechanisms. Inheriting a project's API key or endpoint
    override would make a route labelled ``subscription`` charge the wrong
    account while still looking healthy to Mortimer. Keep ordinary process
    context (including HOME/PATH, which the official CLIs need), but remove
    every supported API credential and endpoint override.
    """
    return {key: value for key, value in os.environ.items()
            if key not in _API_AUTH_ENV_VARS}


def _prompt(messages: list[dict[str, Any]]) -> str:
    return "\n\n".join(
        f"{item.get('role', 'user').upper()}: {item.get('content', '')}"
        for item in messages
    )


def _decode(stdout: str) -> str:
    text = stdout.strip()
    if not text:
        return ""
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return text
    if isinstance(payload, dict):
        return str(payload.get("result") or payload.get("text") or payload.get("content") or "")
    return text


def _run_claude(model: str, messages: list[dict[str, Any]], timeout: float) -> str:
    command = os.environ.get("JARVIS_CLAUDE_SUBSCRIPTION_COMMAND", "claude")
    # Do not use Claude's --bare mode here: it intentionally disables OAuth
    # and keychain reads, which would force this subscription adapter onto an
    # API key. Session persistence is still disabled and all common tools are
    # denied below.
    argv = [command, "--print", "--output-format", "json",
            "--no-session-persistence", "--permission-mode", "dontAsk",
            # The adapter is text-only. Explicitly deny the standard tool
            # families so a CLI-side model loop cannot become a second
            # filesystem, shell, web, or delegation boundary.
            "--disallowed-tools", "Bash", "Edit", "Write", "Read", "Glob", "Grep",
            "WebFetch", "WebSearch", "NotebookEdit", "Task",
            "--model", model, _prompt(messages)]
    try:
        completed = subprocess.run(argv, capture_output=True, text=True,
                                   timeout=timeout, check=False,
                                   env=_subscription_env())
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SubscriptionRuntimeError(f"Claude subscription runtime failed: {exc}") from exc
    if completed.returncode:
        detail = (completed.stderr or completed.stdout).strip()[-500:]
        raise SubscriptionRuntimeError(f"Claude subscription runtime exited {completed.returncode}: {detail}")
    return _decode(completed.stdout)


def _run_codex(model: str, messages: list[dict[str, Any]], timeout: float) -> str:
    """Run the authenticated Codex CLI in non-interactive text mode.

    The command and flags are overrideable because Codex CLI versions can
    expose the same subscription runtime with slightly different spellings.
    No Mortimer tools are passed to this process; it is intentionally the
    text-only subscription adapter until a sandbox-preserving bridge exists.
    """
    command = os.environ.get("JARVIS_CODEX_SUBSCRIPTION_COMMAND", "codex")
    argv = [command, "exec", "--json", "--ephemeral", "--skip-git-repo-check",
            "--sandbox", "read-only", "--model", model, _prompt(messages)]
    try:
        completed = subprocess.run(argv, capture_output=True, text=True,
                                   timeout=timeout, check=False,
                                   env=_subscription_env())
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SubscriptionRuntimeError(f"Codex subscription runtime failed: {exc}") from exc
    if completed.returncode:
        detail = (completed.stderr or completed.stdout).strip()[-500:]
        raise SubscriptionRuntimeError(f"Codex subscription runtime exited {completed.returncode}: {detail}")
    # `codex exec --json` emits JSONL events. Prefer the final assistant text,
    # while retaining compatibility with a single JSON object or plain output.
    lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    texts: list[str] = []
    for line in lines:
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            event_type = str(payload.get("type") or payload.get("event") or "")
            if event_type in {"message", "assistant", "output_text", "final"}:
                value = payload.get("text") or payload.get("content") or payload.get("message")
                if isinstance(value, str) and value:
                    texts.append(value)
            elif event_type == "item.completed":
                # Current Codex CLI JSON mode wraps the final assistant text
                # in an item.completed event rather than emitting a top-level
                # message event.
                item = payload.get("item")
                if isinstance(item, dict) and item.get("type") in {
                    "agent_message", "message", "output_text"
                }:
                    value = item.get("text") or item.get("content")
                    if isinstance(value, str) and value:
                        texts.append(value)
            elif isinstance(payload.get("result"), str):
                texts.append(payload["result"])
    return texts[-1] if texts else _decode(completed.stdout)


class _Completions:
    def __init__(self, model: str, timeout: float):
        self.model = model
        self.timeout = timeout

    def create(self, **kwargs: Any) -> Any:
        if kwargs.get("tools"):
            raise SubscriptionRuntimeError("subscription text adapter does not support Mortimer tools")
        text = _run_claude(str(kwargs.get("model") or self.model),
                           list(kwargs.get("messages") or []), self.timeout)
        return SimpleNamespace(choices=[SimpleNamespace(
            message=SimpleNamespace(content=text, tool_calls=[]))])


class _AsyncCompletions(_Completions):
    async def create(self, **kwargs: Any) -> Any:
        return await asyncio.to_thread(super().create, **kwargs)


class SubscriptionTextClient:
    """OpenAI-shaped client for explicitly enabled text-only subscription calls."""
    def __init__(self, model: str, *, timeout: float = 120.0):
        self.base_url = "subscription://claude"
        self.chat = SimpleNamespace(completions=_AsyncCompletions(model, timeout))


class SubscriptionSyncTextClient:
    def __init__(self, model: str, *, timeout: float = 120.0):
        self.base_url = "subscription://claude"
        self.chat = SimpleNamespace(completions=_Completions(model, timeout))


class _CodexCompletions(_Completions):
    def create(self, **kwargs: Any) -> Any:
        if kwargs.get("tools"):
            raise SubscriptionRuntimeError("Codex subscription text adapter does not support Mortimer tools")
        text = _run_codex(str(kwargs.get("model") or self.model),
                          list(kwargs.get("messages") or []), self.timeout)
        return SimpleNamespace(choices=[SimpleNamespace(
            message=SimpleNamespace(content=text, tool_calls=[]))])


class _AsyncCodexCompletions(_CodexCompletions):
    async def create(self, **kwargs: Any) -> Any:
        return await asyncio.to_thread(super().create, **kwargs)


class CodexSubscriptionTextClient:
    """OpenAI-shaped, text-only client for the user's Codex subscription."""
    def __init__(self, model: str, *, timeout: float = 120.0):
        self.base_url = "subscription://codex"
        self.chat = SimpleNamespace(completions=_AsyncCodexCompletions(model, timeout))


class CodexSubscriptionSyncTextClient:
    def __init__(self, model: str, *, timeout: float = 120.0):
        self.base_url = "subscription://codex"
        self.chat = SimpleNamespace(completions=_CodexCompletions(model, timeout))
