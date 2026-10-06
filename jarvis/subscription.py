"""Official subscription-runtime adapter for isolated text-only calls.

Provider CLIs run as short-lived child processes. They receive no Mortimer
tools, project working directory, project configuration, prompt in argv, or
inherited application environment. Provider-managed sign-in remains outside
the project vault. Tool-capable subscription execution is a separate gate.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import pwd
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from collections.abc import Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
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


_text_owner = ContextVar('subscription_text_owner', default=None)


def _assert_text_owner() -> None:
    owner = _text_owner.get()
    if owner is not None and owner.cleanup_unverified:
        raise SubscriptionRuntimeError('owned subscription cleanup is unverified', category='cleanup')


@contextmanager
def _text_owner_scope(owner):
    token = _text_owner.set(owner)
    try:
        _assert_text_owner()
        try:
            yield
            # Another active call on this owner may have failed its cleanup
            # while this one awaited the runtime. Do not publish its output.
            _assert_text_owner()
        except SubscriptionRuntimeError as exc:
            if exc.category == 'cleanup':
                owner.cleanup_unverified = True
            raise
    finally:
        _text_owner.reset(token)


# These are the only caller environment values copied to a provider process.
# HOME lets the official CLIs find their default provider-managed sign-in store;
# USER/LOGNAME let them find it in the macOS login Keychain (without USER the
# Claude CLI reports "Not logged in" even when signed in; verified live
# 2026-09-29). Neither is a credential. The provider CLI is told to ignore
# user/project behavior configuration. Proxy, API key, endpoint, and arbitrary
# application variables are intentionally not inherited.
_ENV_ALLOWLIST = frozenset({
    "PATH", "HOME", "USER", "LOGNAME", "LANG", "LC_ALL", "LC_CTYPE",
    "TMPDIR", "TMP", "TEMP", "SSL_CERT_FILE", "SSL_CERT_DIR",
})

# Which executable runs each provider CLI. The same variable feeds the status
# probe's "installed" check (jarvis.status.subscriptions), so the check and
# the run can never disagree about which binary is meant.
COMMAND_ENV = {
    "claude": "JARVIS_CLAUDE_SUBSCRIPTION_COMMAND",
    "codex": "JARVIS_CODEX_SUBSCRIPTION_COMMAND",
}


def provider_command(which: str) -> str:
    """The configured CLI for `which` ('claude' or 'codex'), else its bare name."""
    return os.environ.get(COMMAND_ENV[which]) or which

_CODEX_NO_TOOL_VERIFICATION_ENV = "JARVIS_CODEX_SUBSCRIPTION_NO_TOOLS_VERIFIED"
CODEX_CAPABILITY_RECEIPT_ENV = "JARVIS_CODEX_SUBSCRIPTION_CAPABILITY_RECEIPT"
CODEX_VERIFIED_VERSIONS = frozenset({"codex-cli 0.160.0"})
_CODEX_CATALOG_ARGUMENT = "<mortimer-pinned-model-catalog>"
# These names were checked against the installed 0.160.0 feature registry.
# Code Mode's host remains enabled: the selected model requires it even when
# the model-visible tool registry is empty. Disabling the host emits an error
# item, which our strict completion parser correctly rejects.
CODEX_DISABLED_FEATURES = (
    "agent_message_board", "apps", "artifact", "auth_elicitation", "browser_use",
    "browser_use_external", "browser_use_full_cdp_access", "chronicle", "code_mode",
    "computer_use", "context_management", "current_time_reminder",
    "default_mode_request_user_input", "deferred_executor", "deferred_tool_world_state",
    "enable_mcp_apps", "executor_capability_discovery", "goals",
    "guardian_conversation_history_tools", "hooks", "image_generation", "in_app_browser",
    "in_app_chat", "in_app_local_automation", "memories", "multi_agent", "multi_agent_v2",
    "non_prefixed_mcp_tool_names", "plugins", "remote_plugin", "request_permissions_tool",
    "send_message_to_user_async", "shell_snapshot", "shell_snapshot_v2", "shell_tool",
    "skill_mcp_dependency_install", "skill_search", "sleep_tool", "standalone_web_search",
    "tool_call_mcp_elicitation", "tool_suggest", "unified_exec", "view_image",
    "workspace_dependencies", "worktrees", "unbounded_connection_retries",
    "respect_system_proxy", "system_proxy_fallback",
)
CODEX_ISOLATION_CONFIG = {
    "web_search": "disabled", "mcp_servers": {}, "tool_suggest.discoverables": [],
    "tools.update_plan.enabled": False, "tools.experimental_request_user_input.enabled": False,
    "tools.web_search": False, "history.persistence": "none", "analytics.enabled": False,
    "otel.log_user_prompt": False, "otel.log_agent_responses": False,
    "project_doc_max_bytes": 0, "memories.generate_memories": False,
    "check_for_update_on_startup": False, "features.enable_request_compression": False,
}


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _json_digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def codex_runtime_identity() -> dict[str, str]:
    """Inspect executable identity only; never read an authentication store."""
    command = provider_command("codex")
    selected = shutil.which(command)
    if selected is None:
        raise SubscriptionCapabilityError("Codex subscription command is unavailable")
    executable = Path(selected).resolve()
    try:
        digest = _file_digest(executable)
        with _temp_cwd() as workdir:
            result = subprocess.run(
                [str(executable), "--version"], cwd=workdir,
                env=_subscription_env(workdir), capture_output=True, text=True,
                timeout=5, check=False,
            )
        version = result.stdout.strip()
        if result.returncode != 0 or version not in CODEX_VERIFIED_VERSIONS:
            raise SubscriptionCapabilityError("Codex installed version has no verified capability contract")
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SubscriptionCapabilityError("Codex runtime identity could not be verified") from exc
    return {"path": str(executable), "sha256": digest, "version": version}


def validate_codex_capability_receipt(model: str) -> tuple[list[str], dict[str, Any]]:
    """Require exact installed binary/model/config evidence, never a bare flag.

    The catalog content is embedded in the receipt. The subprocess launcher
    copies that content to its private request directory; a mutable catalog
    path cannot alter the tool surface between validation and execution.
    Local mock evidence proves tool construction, not account access or billing.
    """
    receipt_path = os.environ.get(CODEX_CAPABILITY_RECEIPT_ENV)
    if not receipt_path:
        raise SubscriptionCapabilityError("Codex no-tools capability receipt is required")
    try:
        path = Path(receipt_path)
        if not path.is_file() or path.stat().st_size > 2_000_000:
            raise ValueError("invalid receipt file")
        receipt = json.loads(path.read_text(encoding="utf-8"))
        if (not isinstance(receipt, dict) or type(receipt.get("schema_version")) is not int
                or receipt.get("schema_version") != 1):
            raise ValueError("invalid receipt schema")
        identity = codex_runtime_identity()
        catalog = receipt["catalog"]
        if (receipt.get("runtime") != "codex" or receipt.get("model") != model
                or receipt.get("executable") != identity
                or receipt.get("proof_kind") != "installed_cli_loopback_mock"
                or receipt.get("advertised_tools") != []
                or receipt.get("terminal_success_without_error_items") is not True
                or receipt.get("negative_unadvertised_tool_rejected") is not True
                or receipt.get("api_credentials_absent") is not True
                or type(receipt.get("real_provider_calls")) is not int
                or receipt.get("real_provider_calls") != 0
                or not isinstance(catalog, dict)
                or not isinstance(catalog.get("models"), list)
                or len(catalog["models"]) != 1
                or catalog["models"][0].get("slug") != model
                or receipt.get("catalog_sha256") != _json_digest(catalog)):
            raise ValueError("capability evidence mismatch")
        argv = _codex_argv(model, command=identity["path"])
        if receipt.get("invocation_sha256") != _json_digest(argv):
            raise ValueError("invocation evidence mismatch")
    except SubscriptionCapabilityError:
        raise
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        raise SubscriptionCapabilityError("Codex capability receipt does not match this runtime request") from exc
    return argv, catalog


def _subscription_env(temp_dir: str | None = None) -> dict[str, str]:
    """Construct the minimal child environment without API credentials."""
    env = {key: value for key, value in os.environ.items()
           if key in _ENV_ALLOWLIST and value}
    if "USER" not in env:
        # Some launch contexts omit USER; the account name is not a secret.
        try:
            name = pwd.getpwuid(os.getuid()).pw_name
        except (KeyError, OSError):
            name = ""
        if name:
            env["USER"] = name
            env.setdefault("LOGNAME", name)
    if temp_dir is not None:
        # Keep runtime scratch data inside the per-request directory so its
        # lifetime is tied to the provider child process.
        env.update(TMPDIR=temp_dir, TMP=temp_dir, TEMP=temp_dir)
    return env


def _prompt(messages: list[dict[str, Any]]) -> str:
    if any(not isinstance(item, dict) or item.get("role") not in {"system", "user", "assistant"}
           or not isinstance(item.get("content"), str) or item.get("tool_calls")
           for item in messages):
        raise SubscriptionCapabilityError("subscription text input does not support images or tool history")
    return "\n\n".join(
        f"{str(item.get('role', 'user')).upper()}: {item.get('content', '')}"
        for item in messages
    )


def _temp_cwd() -> tempfile.TemporaryDirectory[str]:
    # Do not let an inherited TMPDIR redirect provider execution into the
    # project checkout. Both macOS and Linux provide a system-owned /tmp.
    return tempfile.TemporaryDirectory(prefix="mortimer-subscription-", dir="/tmp")


def _claude_argv(model: str) -> list[str]:
    command = provider_command("claude")
    return [
        command, "--print", "--input-format", "text", "--output-format", "json",
        "--no-session-persistence", "--safe-mode", "--restricted", "--tools", "",
        "--disallowed-tools", "mcp__*", "--permission-prompts", "none",
        "--model", model,
    ]


def _codex_argv(model: str, *, command: str | None = None) -> list[str]:
    """Build a constrained Codex invocation after its no-tools gate is proven."""
    command = command or provider_command("codex")
    argv = [
        command, "exec", "--json", "--ephemeral", "--ignore-user-config",
        "--ignore-rules", "--skip-git-repo-check", "--strict-config",
        "--sandbox", "read-only", "--model", model,
    ]
    for feature in CODEX_DISABLED_FEATURES:
        argv.extend(["--disable", feature])
    argv.extend(["--enable", "code_mode_host"])
    for name, value in CODEX_ISOLATION_CONFIG.items():
        argv.extend(["-c", name + "=" + _canonical_json(value)])
    argv.extend(["-c", "model_catalog_json=" + json.dumps(_CODEX_CATALOG_ARGUMENT), "-"])
    return argv


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
    if any(event["item"].get("type") not in {"agent_message", "reasoning"}
           for event in events if isinstance(event.get("item"), dict)):
        raise SubscriptionRuntimeError("Codex text runtime returned a non-text item",
                                       category="capability")

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


def _owned_group_absent_after_permission_error(pid: int) -> bool:
    """BSD signal-zero can return EPERM for a vanished group; verify only it.

    This is read-only, selects the exact owned process group, and never prints
    process commands, arguments, environment, or unrelated process metadata.
    An unavailable/denied inspection remains unverified.
    """
    if sys.platform != "darwin":
        return False
    try:
        result = subprocess.run(["/bin/ps", "-g", str(pid), "-o", "pid=,pgid=,stat="],
                                capture_output=True, text=True, timeout=1, check=False,
                                env=_subscription_env())
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 1 and not result.stdout.strip() and not result.stderr.strip()


def _owned_group_present(pid: int) -> bool:
    try:
        os.killpg(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError as exc:
        if _owned_group_absent_after_permission_error(pid):
            return False
        raise SubscriptionRuntimeError("owned provider cleanup could not be verified", category="cleanup") from exc
    return True


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
        if not _owned_group_present(process.pid):
            break
        time.sleep(0.05)
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired as exc:
        raise SubscriptionRuntimeError("owned provider cleanup could not be verified", category="cleanup") from exc
    deadline = time.monotonic() + 2
    while True:
        if not _owned_group_present(process.pid):
            return
        if time.monotonic() >= deadline:
            raise SubscriptionRuntimeError("owned provider descendants remain after cleanup", category="cleanup")
        time.sleep(0.05)


def _materialize_catalog(argv: Sequence[str], workdir: str,
                         catalog: dict[str, Any] | None) -> list[str]:
    if catalog is None:
        return list(argv)
    path = Path(workdir) / "approved-model-catalog.json"
    path.write_text(_canonical_json(catalog), encoding="utf-8")
    path.chmod(0o600)
    return [arg.replace(_CODEX_CATALOG_ARGUMENT, str(path)) for arg in argv]


def _encoded_prompt(prompt: str) -> bytes:
    try:
        return prompt.encode("utf-8")
    except (AttributeError, UnicodeError) as exc:
        raise SubscriptionRuntimeError("subscription prompt is not valid UTF-8 text",
                                       category="malformed_input") from exc


def _run_sync(argv: Sequence[str], prompt: str, timeout: float, *, provider: str,
              catalog: dict[str, Any] | None = None) -> str:
    _encoded_prompt(prompt)  # Validate before a text-mode child can be created.
    if os.name != "posix":
        raise SubscriptionCapabilityError(
            f"{provider} subscription runtime requires verified process-group cancellation on this platform"
        )
    with _temp_cwd() as workdir:
        _assert_text_owner()
        process: subprocess.Popen[str] | None = None
        try:
            process = subprocess.Popen(
                _materialize_catalog(argv, workdir, catalog), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
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
    return _run_claude_response(model, messages, timeout).choices[0].message.content


def _count(source: Any, key: str) -> int | None:
    value = source.get(key) if isinstance(source, dict) else None
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def normalize_claude_usage(source: Any) -> dict[str, int | None]:
    """Preserve token counts only, with Anthropic's inclusive input semantics."""
    counts = [_count(source, key) for key in (
        "input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")]
    return {"prompt_tokens": sum(counts) if all(value is not None for value in counts) else None,
            "completion_tokens": _count(source, "output_tokens"),
            "cache_read_input_tokens": counts[1], "cache_creation_input_tokens": counts[2]}


def _response(text: str, usage: Any) -> Any:
    return SimpleNamespace(choices=[SimpleNamespace(
        message=SimpleNamespace(content=text, tool_calls=[]))], usage=usage)


def _claude_response(stdout: str) -> Any:
    text = _claude_text(stdout)
    return _response(text, normalize_claude_usage(json.loads(stdout).get("usage")))


def _codex_response(stdout: str) -> Any:
    text = _codex_text(stdout)
    terminal = next(json.loads(line) for line in stdout.splitlines()
                    if line.strip() and json.loads(line).get("type") == "turn.completed")
    usage = terminal.get("usage")
    return _response(text, {"prompt_tokens": _count(usage, "input_tokens"),
                            "completion_tokens": _count(usage, "output_tokens"),
                            "cache_read_input_tokens": _count(usage, "cached_input_tokens"),
                            "cache_creation_input_tokens": None})


def _run_claude_response(model: str, messages: list[dict[str, Any]], timeout: float) -> Any:
    stdout = _run_sync(_claude_argv(model), _prompt(messages), timeout, provider="Claude")
    return _claude_response(stdout)


def _run_codex(model: str, messages: list[dict[str, Any]], timeout: float) -> str:
    """Run Codex only after an operator has recorded no-tools verification.

    The installed Codex runtime's feature flags do not by themselves prove
    every built-in/hosted tool has been removed. Keep this route closed until
    the exact installed version passes the plan's tool-surface acceptance.
    """
    return _run_codex_response(model, messages, timeout).choices[0].message.content


def _run_codex_response(model: str, messages: list[dict[str, Any]], timeout: float) -> Any:
    if os.environ.get(_CODEX_NO_TOOL_VERIFICATION_ENV) != "1":
        raise SubscriptionCapabilityError(
            "Codex subscription text route is disabled until its no-tools runtime capability is verified"
        )
    argv, catalog = validate_codex_capability_receipt(model)
    stdout = _run_sync(argv, _prompt(messages), timeout, provider="Codex", catalog=catalog)
    return _codex_response(stdout)


async def _terminate_async(process: asyncio.subprocess.Process) -> None:
    # The leader may already have exited while a descendant still holds the
    # pipes open. Signal/check the process group even when returncode is set.
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        if not await asyncio.to_thread(_owned_group_present, process.pid):
            break
        await asyncio.sleep(0.05)
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:
        await asyncio.wait_for(process.wait(), timeout=2)
    except asyncio.TimeoutError as exc:
        raise SubscriptionRuntimeError("owned provider cleanup could not be verified", category="cleanup") from exc
    deadline = time.monotonic() + 2
    while True:
        if not await asyncio.to_thread(_owned_group_present, process.pid):
            return
        if time.monotonic() >= deadline:
            raise SubscriptionRuntimeError("owned provider descendants remain after cleanup", category="cleanup")
        await asyncio.sleep(0.05)


async def _run_async(argv: Sequence[str], prompt: str, timeout: float, *, provider: str,
                     catalog: dict[str, Any] | None = None) -> str:
    prompt_bytes = _encoded_prompt(prompt)
    if os.name != "posix":
        raise SubscriptionCapabilityError(
            f"{provider} subscription runtime requires verified process-group cancellation on this platform"
        )
    with _temp_cwd() as workdir:
        # This runs after a Codex capability-receipt worker returns, rather
        # than treating its earlier preflight as permission to start a child.
        _assert_text_owner()
        try:
            process = await asyncio.create_subprocess_exec(
                *_materialize_catalog(argv, workdir, catalog), stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE, cwd=workdir, env=_subscription_env(workdir),
                start_new_session=(os.name == "posix"),
            )
        except OSError as exc:
            raise SubscriptionRuntimeError(
                f"{provider} subscription runtime could not start", category="runtime_unavailable") from exc

        communication = asyncio.create_task(process.communicate(prompt_bytes))
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
    return (await _run_claude_response_async(model, messages, timeout)).choices[0].message.content


async def _run_claude_response_async(model: str, messages: list[dict[str, Any]], timeout: float) -> Any:
    stdout = await _run_async(_claude_argv(model), _prompt(messages), timeout,
                              provider="Claude")
    return _claude_response(stdout)


async def _run_codex_async(model: str, messages: list[dict[str, Any]], timeout: float) -> str:
    return (await _run_codex_response_async(model, messages, timeout)).choices[0].message.content


async def _run_codex_response_async(model: str, messages: list[dict[str, Any]], timeout: float) -> Any:
    if os.environ.get(_CODEX_NO_TOOL_VERIFICATION_ENV) != "1":
        raise SubscriptionCapabilityError(
            "Codex subscription text route is disabled until its no-tools runtime capability is verified"
        )
    argv, catalog = await asyncio.to_thread(validate_codex_capability_receipt, model)
    stdout = await _run_async(argv, _prompt(messages), timeout,
                              provider="Codex", catalog=catalog)
    return _codex_response(stdout)


def _assert_text_capabilities(kwargs: dict[str, Any]) -> None:
    if kwargs.get("max_tokens") is not None:
        raise SubscriptionCapabilityError("subscription runtime cannot enforce max_tokens")
    if kwargs.get("stream") or kwargs.get("response_format") is not None:
        raise SubscriptionCapabilityError("subscription text runtime does not support requested output capability")
    if kwargs.get("temperature") is not None or kwargs.get("extra_body"):
        raise SubscriptionCapabilityError("subscription text runtime cannot enforce provider generation parameters")


class _Completions:
    def __init__(self, model: str, timeout: float):
        self.model = model
        self.timeout = timeout
        self.cleanup_unverified = False

    def create(self, **kwargs: Any) -> Any:
        if kwargs.get("tools"):
            raise SubscriptionRuntimeError("subscription text adapter does not support Mortimer tools")
        _assert_text_capabilities(kwargs)
        with _text_owner_scope(self):
            return _run_claude_response(str(kwargs.get("model") or self.model),
                               list(kwargs.get("messages") or []), self.timeout)


class _AsyncCompletions(_Completions):
    async def create(self, **kwargs: Any) -> Any:
        if kwargs.get("tools"):
            raise SubscriptionRuntimeError("subscription text adapter does not support Mortimer tools")
        _assert_text_capabilities(kwargs)
        with _text_owner_scope(self):
            return await _run_claude_response_async(str(kwargs.get("model") or self.model),
                                           list(kwargs.get("messages") or []), self.timeout)


class SubscriptionTextClient:
    """OpenAI-shaped client for explicitly enabled text-only Claude calls."""
    def __init__(self, model: str, *, timeout: float = 120.0):
        self.base_url = "subscription://claude"
        self.chat = SimpleNamespace(completions=_AsyncCompletions(model, timeout))

    @property
    def cleanup_unverified(self):
        return self.chat.completions.cleanup_unverified


class SubscriptionSyncTextClient:
    def __init__(self, model: str, *, timeout: float = 120.0):
        self.base_url = "subscription://claude"
        self.chat = SimpleNamespace(completions=_Completions(model, timeout))

    @property
    def cleanup_unverified(self):
        return self.chat.completions.cleanup_unverified


class _CodexCompletions(_Completions):
    def create(self, **kwargs: Any) -> Any:
        if kwargs.get("tools"):
            raise SubscriptionRuntimeError("Codex subscription text adapter does not support Mortimer tools")
        _assert_text_capabilities(kwargs)
        with _text_owner_scope(self):
            return _run_codex_response(str(kwargs.get("model") or self.model),
                              list(kwargs.get("messages") or []), self.timeout)


class _AsyncCodexCompletions(_CodexCompletions):
    async def create(self, **kwargs: Any) -> Any:
        if kwargs.get("tools"):
            raise SubscriptionRuntimeError("Codex subscription text adapter does not support Mortimer tools")
        _assert_text_capabilities(kwargs)
        with _text_owner_scope(self):
            return await _run_codex_response_async(str(kwargs.get("model") or self.model),
                                          list(kwargs.get("messages") or []), self.timeout)


class CodexSubscriptionTextClient:
    """OpenAI-shaped, gated text-only client for the user's Codex subscription."""
    def __init__(self, model: str, *, timeout: float = 120.0):
        self.base_url = "subscription://codex"
        self.chat = SimpleNamespace(completions=_AsyncCodexCompletions(model, timeout))

    @property
    def cleanup_unverified(self):
        return self.chat.completions.cleanup_unverified


class CodexSubscriptionSyncTextClient:
    def __init__(self, model: str, *, timeout: float = 120.0):
        self.base_url = "subscription://codex"
        self.chat = SimpleNamespace(completions=_CodexCompletions(model, timeout))

    @property
    def cleanup_unverified(self):
        return self.chat.completions.cleanup_unverified
