"""Official subscription-runtime adapter for isolated text-only calls.

Provider CLIs run as short-lived child processes. They receive no Mortimer
tools, project working directory, project configuration, prompt in argv, or
inherited application environment. Provider-managed sign-in remains outside
the project vault. Tool-capable subscription execution is a separate gate.
"""
from __future__ import annotations

import asyncio
import json
import os
import signal
import subprocess
import tempfile
import time
from collections.abc import Sequence
from types import SimpleNamespace
from typing import Any


class SubscriptionRuntimeError(RuntimeError):
    """A safe, normalized subscription runtime failure."""

    def __init__(self, message: str, *, category: str = "provider_failure") -> None:
        super().__init__(message)
        self.category = category


class SubscriptionCapabilityError(SubscriptionRuntimeError):
    """The selected installed runtime cannot meet the adapter contract."""

    def __init__(self, message: str) -> None:
        super().__init__(message, category="capability")


# These are the only caller environment values copied to a provider process.
# HOME lets the official CLIs find their default provider-managed sign-in store; the
# provider CLI is told to ignore user/project behavior configuration. Proxy,
# API key, endpoint, and arbitrary application variables are intentionally not
# inherited.
_ENV_ALLOWLIST = frozenset({
    "PATH", "HOME", "LANG", "LC_ALL", "LC_CTYPE", "TMPDIR", "TMP", "TEMP",
    "SSL_CERT_FILE", "SSL_CERT_DIR",
})

_CODEX_NO_TOOL_VERIFICATION_ENV = "JARVIS_CODEX_SUBSCRIPTION_NO_TOOLS_VERIFIED"


def _subscription_env(temp_dir: str | None = None) -> dict[str, str]:
    """Construct the minimal child environment without API credentials."""
    env = {key: value for key, value in os.environ.items()
           if key in _ENV_ALLOWLIST and value}
    if temp_dir is not None:
        # Keep runtime scratch data inside the per-request directory so its
        # lifetime is tied to the provider child process.
        env.update(TMPDIR=temp_dir, TMP=temp_dir, TEMP=temp_dir)
    return env


def _prompt(messages: list[dict[str, Any]]) -> str:
    return "\n\n".join(
        f"{str(item.get('role', 'user')).upper()}: {item.get('content', '')}"
        for item in messages
    )


def _temp_cwd() -> tempfile.TemporaryDirectory[str]:
    # Do not let an inherited TMPDIR redirect provider execution into the
    # project checkout. Both macOS and Linux provide a system-owned /tmp.
    return tempfile.TemporaryDirectory(prefix="mortimer-subscription-", dir="/tmp")


def _claude_argv(model: str) -> list[str]:
    command = "claude"
    return [
        command, "--print", "--input-format", "text", "--output-format", "json",
        "--no-session-persistence", "--safe-mode", "--restricted", "--tools", "",
        "--disallowed-tools", "mcp__*", "--permission-prompts", "none",
        "--model", model,
    ]


def _codex_argv(model: str) -> list[str]:
    """Build a constrained Codex invocation after its no-tools gate is proven."""
    command = "codex"
    return [
        command, "exec", "--json", "--ephemeral", "--ignore-user-config",
        "--ignore-rules", "--skip-git-repo-check",
        "--sandbox", "read-only", "--disable", "shell_tool", "--disable",
        "unified_exec", "--disable", "view_image", "--disable", "sleep_tool",
        "--disable", "code_mode", "--disable", "code_mode_host", "--disable",
        "browser_use", "--disable", "browser_use_external", "--disable",
        "computer_use", "--disable", "apps", "--disable", "plugins",
        "--disable", "multi_agent", "--disable", "image_generation",
        "--disable", "request_permissions_tool", "-c", 'web_search="disabled"',
        "--model", model, "-",
    ]


def _claude_text(stdout: str) -> str:
    try:
        payload = json.loads(stdout)
    except (TypeError, json.JSONDecodeError) as exc:
        raise SubscriptionRuntimeError(
            "Claude returned malformed structured output", category="malformed_output") from exc
    if not isinstance(payload, dict) or payload.get("is_error") is not False:
        raise SubscriptionRuntimeError("Claude did not return a successful completion")
    result = payload.get("result")
    if not isinstance(result, str) or not result.strip():
        raise SubscriptionRuntimeError(
            "Claude completion contained no assistant text", category="malformed_output")
    return result


_CODEX_NONTERMINAL_EVENTS = frozenset({
    "thread.started", "turn.started", "item.started", "item.updated", "item.completed",
})


def _codex_text(stdout: str) -> str:
    """Parse Codex JSONL and require exactly one successful terminal event."""
    lines = [line for line in stdout.splitlines() if line.strip()]
    if not lines:
        raise SubscriptionRuntimeError("Codex returned no structured events", category="malformed_output")
    events: list[dict[str, Any]] = []
    for line in lines:
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SubscriptionRuntimeError(
                "Codex returned malformed structured output", category="malformed_output") from exc
        if not isinstance(event, dict) or not isinstance(event.get("type"), str):
            raise SubscriptionRuntimeError("Codex returned an unrecognized event", category="malformed_output")
        events.append(event)

    terminal_events = [event for event in events
                       if event["type"] in {"turn.completed", "turn.failed", "error"}]
    if len(terminal_events) != 1 or terminal_events[0]["type"] != "turn.completed":
        raise SubscriptionRuntimeError("Codex did not return one successful terminal event")
    if events[-1] is not terminal_events[0]:
        raise SubscriptionRuntimeError("Codex emitted events after its terminal event",
                                       category="malformed_output")
    if any(event["type"] not in _CODEX_NONTERMINAL_EVENTS | {
            "turn.completed", "turn.failed", "error"} for event in events):
        raise SubscriptionRuntimeError("Codex returned an unsupported event type",
                                       category="malformed_output")
    if any(event.get("item", {}).get("type") == "error"
           for event in events if isinstance(event.get("item"), dict)):
        raise SubscriptionRuntimeError("Codex returned a failed item")

    messages = [event.get("item") for event in events
                if event["type"] == "item.completed"
                and isinstance(event.get("item"), dict)
                and event["item"].get("type") == "agent_message"]
    if not messages:
        raise SubscriptionRuntimeError("Codex completion contained no assistant text",
                                       category="malformed_output")
    text = messages[-1].get("text")
    if not isinstance(text, str) or not text.strip():
        raise SubscriptionRuntimeError("Codex completion contained no assistant text",
                                       category="malformed_output")
    return text


def _failure_category(stderr: str) -> str:
    """Map provider diagnostics to a small safe category vocabulary."""
    detail = stderr.casefold()
    if any(token in detail for token in ("401", "unauthorized", "not logged in", "authentication")):
        return "authentication"
    if any(token in detail for token in ("out of credits", "insufficient credits", "credit balance")):
        return "credit"
    if any(token in detail for token in ("rate limit", "usage limit", "allowance", "quota")):
        return "allowance"
    if any(token in detail for token in ("permission denied", "policy denied", "blocked by policy")):
        return "policy"
    if any(token in detail for token in ("unsupported", "not supported", "model not found")):
        return "capability"
    return "provider_failure"


def _terminate_sync(process: subprocess.Popen[str]) -> None:
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGTERM)
        else:
            process.terminate()
    except ProcessLookupError:
        pass
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        process.poll()  # Reap an exited leader while checking its descendants.
        try:
            os.killpg(process.pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.05)
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    process.wait()


def _run_sync(argv: Sequence[str], prompt: str, timeout: float, *, provider: str) -> str:
    if os.name != "posix":
        raise SubscriptionCapabilityError(
            f"{provider} subscription runtime requires verified process-group cancellation on this platform"
        )
    with _temp_cwd() as workdir:
        process: subprocess.Popen[str] | None = None
        try:
            process = subprocess.Popen(
                list(argv), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
                cwd=workdir, env=_subscription_env(workdir),
                start_new_session=(os.name == "posix"),
            )
            stdout, stderr = process.communicate(input=prompt, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            if process is not None:
                _terminate_sync(process)
            # communicate() after wait drains and closes the owned pipe handles.
            if process is not None:
                process.communicate()
            raise SubscriptionRuntimeError(
                f"{provider} subscription runtime timed out", category="timeout") from exc
        except OSError as exc:
            if process is not None:
                _terminate_sync(process)
            raise SubscriptionRuntimeError(
                f"{provider} subscription runtime failed", category="runtime_unavailable") from exc
        except BaseException:
            if process is not None:
                _terminate_sync(process)
            raise
        assert process is not None
        if process.returncode != 0:
            raise SubscriptionRuntimeError(
                f"{provider} subscription runtime failed",
                category=_failure_category(stderr or stdout))
        return stdout


def _run_claude(model: str, messages: list[dict[str, Any]], timeout: float) -> str:
    stdout = _run_sync(_claude_argv(model), _prompt(messages), timeout, provider="Claude")
    return _claude_text(stdout)


def _run_codex(model: str, messages: list[dict[str, Any]], timeout: float) -> str:
    """Run Codex only after an operator has recorded no-tools verification.

    The installed Codex runtime's feature flags do not by themselves prove
    every built-in/hosted tool has been removed. Keep this route closed until
    the exact installed version passes the plan's tool-surface acceptance.
    """
    if os.environ.get(_CODEX_NO_TOOL_VERIFICATION_ENV) != "1":
        raise SubscriptionCapabilityError(
            "Codex subscription text route is disabled until its no-tools runtime capability is verified"
        )
    stdout = _run_sync(_codex_argv(model), _prompt(messages), timeout, provider="Codex")
    return _codex_text(stdout)


async def _terminate_async(process: asyncio.subprocess.Process) -> None:
    # The leader may already have exited while a descendant still holds the
    # pipes open. Signal/check the process group even when returncode is set.
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        try:
            os.killpg(process.pid, 0)
        except ProcessLookupError:
            break
        await asyncio.sleep(0.05)
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    await process.wait()


async def _run_async(argv: Sequence[str], prompt: str, timeout: float, *, provider: str) -> str:
    if os.name != "posix":
        raise SubscriptionCapabilityError(
            f"{provider} subscription runtime requires verified process-group cancellation on this platform"
        )
    with _temp_cwd() as workdir:
        try:
            process = await asyncio.create_subprocess_exec(
                *argv, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE, cwd=workdir, env=_subscription_env(workdir),
                start_new_session=(os.name == "posix"),
            )
        except OSError as exc:
            raise SubscriptionRuntimeError(
                f"{provider} subscription runtime could not start", category="runtime_unavailable") from exc

        communication = asyncio.create_task(process.communicate(prompt.encode("utf-8")))
        try:
            stdout, stderr = await asyncio.wait_for(asyncio.shield(communication), timeout)
        except asyncio.TimeoutError as exc:
            await _terminate_async(process)
            try:
                await asyncio.wait_for(asyncio.shield(communication), timeout=2)
            except asyncio.TimeoutError:
                communication.cancel()
                await asyncio.gather(communication, return_exceptions=True)
            raise SubscriptionRuntimeError(
                f"{provider} subscription runtime timed out", category="timeout") from exc
        except asyncio.CancelledError:
            cleanup = asyncio.create_task(_terminate_async(process))
            try:
                await asyncio.shield(cleanup)
            except asyncio.CancelledError:
                await asyncio.shield(cleanup)
            try:
                await asyncio.wait_for(asyncio.shield(communication), timeout=2)
            except asyncio.TimeoutError:
                communication.cancel()
                await asyncio.gather(communication, return_exceptions=True)
            raise
        except Exception as exc:
            await _terminate_async(process)
            if not communication.done():
                communication.cancel()
            await asyncio.gather(communication, return_exceptions=True)
            raise SubscriptionRuntimeError(
                f"{provider} subscription runtime failed", category="provider_failure") from exc
        except BaseException:
            await _terminate_async(process)
            if not communication.done():
                communication.cancel()
            await asyncio.gather(communication, return_exceptions=True)
            raise
        if process.returncode != 0:
            raise SubscriptionRuntimeError(
                f"{provider} subscription runtime failed",
                category=_failure_category(stderr.decode("utf-8", errors="replace")
                                           or stdout.decode("utf-8", errors="replace")))
        return stdout.decode("utf-8", errors="replace")


async def _run_claude_async(model: str, messages: list[dict[str, Any]], timeout: float) -> str:
    stdout = await _run_async(_claude_argv(model), _prompt(messages), timeout,
                              provider="Claude")
    return _claude_text(stdout)


async def _run_codex_async(model: str, messages: list[dict[str, Any]], timeout: float) -> str:
    if os.environ.get(_CODEX_NO_TOOL_VERIFICATION_ENV) != "1":
        raise SubscriptionCapabilityError(
            "Codex subscription text route is disabled until its no-tools runtime capability is verified"
        )
    stdout = await _run_async(_codex_argv(model), _prompt(messages), timeout,
                              provider="Codex")
    return _codex_text(stdout)


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
        if kwargs.get("tools"):
            raise SubscriptionRuntimeError("subscription text adapter does not support Mortimer tools")
        text = await _run_claude_async(str(kwargs.get("model") or self.model),
                                       list(kwargs.get("messages") or []), self.timeout)
        return SimpleNamespace(choices=[SimpleNamespace(
            message=SimpleNamespace(content=text, tool_calls=[]))])


class SubscriptionTextClient:
    """OpenAI-shaped client for explicitly enabled text-only Claude calls."""
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
        if kwargs.get("tools"):
            raise SubscriptionRuntimeError("Codex subscription text adapter does not support Mortimer tools")
        text = await _run_codex_async(str(kwargs.get("model") or self.model),
                                      list(kwargs.get("messages") or []), self.timeout)
        return SimpleNamespace(choices=[SimpleNamespace(
            message=SimpleNamespace(content=text, tool_calls=[]))])


class CodexSubscriptionTextClient:
    """OpenAI-shaped, gated text-only client for the user's Codex subscription."""
    def __init__(self, model: str, *, timeout: float = 120.0):
        self.base_url = "subscription://codex"
        self.chat = SimpleNamespace(completions=_AsyncCodexCompletions(model, timeout))


class CodexSubscriptionSyncTextClient:
    def __init__(self, model: str, *, timeout: float = 120.0):
        self.base_url = "subscription://codex"
        self.chat = SimpleNamespace(completions=_CodexCompletions(model, timeout))
