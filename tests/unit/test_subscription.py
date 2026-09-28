from __future__ import annotations

import asyncio
import json
import os
import signal
import sys
from pathlib import Path

import pytest

from jarvis.subscription import (
    _CODEX_NO_TOOL_VERIFICATION_ENV,
    CodexSubscriptionTextClient,
    SubscriptionCapabilityError,
    SubscriptionRuntimeError,
    _codex_text,
    _failure_category,
    _run_async,
    _run_claude,
    _run_codex,
    _subscription_env,
    _terminate_sync,
)


def _codex_events(text: str = "final answer") -> str:
    return "\n".join((
        '{"type":"thread.started","thread_id":"thread-test"}',
        '{"type":"turn.started","turn_id":"turn-test"}',
        json.dumps({"type": "item.completed", "item": {
            "id": "item-test", "type": "agent_message", "text": text,
        }}),
        '{"type":"turn.completed","usage":{}}',
    )) + "\n"


class _FakePopen:
    def __init__(self, argv, **kwargs):
        self.argv = argv
        self.kwargs = kwargs
        self.returncode = 0
        self.input = None

    def communicate(self, input=None, timeout=None):
        self.input = input
        return self.kwargs.pop("fake_stdout"), self.kwargs.pop("fake_stderr", "")

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        return self.returncode


def test_subscription_environment_is_allowlisted(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "secret-canary")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://paid.example/v1")
    monkeypatch.setenv("OPENROUTER_API_KEY", "secret-canary")
    monkeypatch.setenv("JARVIS_PRIVATE_SETTING", "must-not-inherit")
    monkeypatch.setenv("HOME", "/Users/tester")
    monkeypatch.setenv("PATH", "/usr/bin")
    monkeypatch.setenv("CODEX_HOME", "/project/.codex")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", "/Users/tester/.claude")

    env = _subscription_env()

    assert env["HOME"] == "/Users/tester"
    assert env["PATH"] == "/usr/bin"
    assert set(env) <= {
        "PATH", "HOME", "LANG", "LC_ALL", "LC_CTYPE", "TMPDIR", "TMP", "TEMP",
        "SSL_CERT_FILE", "SSL_CERT_DIR",
    }
    assert "CODEX_HOME" not in env
    assert "CLAUDE_CONFIG_DIR" not in env
    assert "ANTHROPIC_API_KEY" not in env
    assert "OPENAI_BASE_URL" not in env
    assert "OPENROUTER_API_KEY" not in env
    assert "JARVIS_PRIVATE_SETTING" not in env


def test_claude_prompt_is_stdin_and_process_is_isolated(monkeypatch, tmp_path):
    seen = {}
    canary = "PRIVATE_SKILL_TASK_CANARY_7f49"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("JARVIS_PRIVATE_SETTING", "must-not-inherit")

    def fake_popen(argv, **kwargs):
        process = _FakePopen(argv, **kwargs)
        process.kwargs["fake_stdout"] = '{"is_error":false,"result":"answer"}'
        seen.update(argv=argv, kwargs=kwargs, process=process)
        return process

    monkeypatch.setattr("jarvis.subscription.subprocess.Popen", fake_popen)
    assert _run_claude("claude-sonnet", [{"role": "user", "content": canary}], 3) == "answer"

    assert canary not in seen["argv"]
    assert seen["process"].input == f"USER: {canary}"
    assert seen["kwargs"]["cwd"] != str(tmp_path)
    assert not Path(seen["kwargs"]["cwd"]).exists()
    assert seen["kwargs"]["env"].get("JARVIS_PRIVATE_SETTING") is None
    assert seen["kwargs"]["env"]["TMPDIR"] == seen["kwargs"]["cwd"]
    assert "--safe-mode" in seen["argv"]
    assert "--restricted" in seen["argv"]
    assert seen["argv"][seen["argv"].index("--tools") + 1] == ""
    assert seen["argv"][seen["argv"].index("--disallowed-tools") + 1] == "mcp__*"
    assert "--no-session-persistence" in seen["argv"]


@pytest.mark.parametrize("output", [
    "not-json",
    '{"is_error":true,"result":"provider error text"}',
    '{"is_error":false,"result":""}',
    '{"result":"missing status"}',
])
def test_claude_rejects_malformed_failed_or_empty_envelopes(monkeypatch, output):
    def fake_popen(argv, **kwargs):
        process = _FakePopen(argv, **kwargs)
        process.kwargs["fake_stdout"] = output
        return process

    monkeypatch.setattr("jarvis.subscription.subprocess.Popen", fake_popen)
    with pytest.raises(SubscriptionRuntimeError):
        _run_claude("claude-sonnet", [], 3)


def test_codex_requires_no_tools_verification_before_invocation(monkeypatch):
    monkeypatch.delenv(_CODEX_NO_TOOL_VERIFICATION_ENV, raising=False)
    called = False

    def should_not_run(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("provider process must not start")

    monkeypatch.setattr("jarvis.subscription.subprocess.Popen", should_not_run)
    with pytest.raises(SubscriptionCapabilityError, match="no-tools runtime capability"):
        _run_codex("gpt-codex", [], 3)
    assert not called


def test_codex_invocation_uses_stdin_isolated_cwd_and_disabled_tool_families(monkeypatch, tmp_path):
    seen = {}
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(_CODEX_NO_TOOL_VERIFICATION_ENV, "1")

    def fake_popen(argv, **kwargs):
        process = _FakePopen(argv, **kwargs)
        process.kwargs["fake_stdout"] = _codex_events("answer")
        seen.update(argv=argv, kwargs=kwargs, process=process)
        return process

    monkeypatch.setattr("jarvis.subscription.subprocess.Popen", fake_popen)
    assert _run_codex("gpt-codex", [{"role": "user", "content": "private prompt"}], 3) == "answer"

    assert "private prompt" not in seen["argv"]
    assert seen["process"].input == "USER: private prompt"
    assert seen["kwargs"]["cwd"] != str(tmp_path)
    assert not Path(seen["kwargs"]["cwd"]).exists()
    assert seen["kwargs"]["env"]["TMPDIR"] == seen["kwargs"]["cwd"]
    assert _CODEX_NO_TOOL_VERIFICATION_ENV not in seen["kwargs"]["env"]
    for flag in ("--ephemeral", "--ignore-user-config", "--ignore-rules", "--sandbox"):
        assert flag in seen["argv"]
    for feature in ("shell_tool", "unified_exec", "browser_use", "computer_use",
                    "apps", "plugins", "multi_agent", "image_generation"):
        assert any(seen["argv"][index:index + 2] == ["--disable", feature]
                   for index, arg in enumerate(seen["argv"][:-1]) if arg == "--disable")


def test_codex_jsonl_requires_success_terminal_and_final_assistant_text():
    assert _codex_text(_codex_events("MORTIMER_SUBSCRIPTION_PROBE_OK")) == "MORTIMER_SUBSCRIPTION_PROBE_OK"


@pytest.mark.parametrize("output", [
    "",
    '{"type":"message","text":"legacy loose event"}\n',
    '{"type":"turn.failed","error":{"message":"failed"}}\n',
    '{"type":"error","message":"failed"}\n',
    '{"type":"turn.completed"}\n',
    '{"type":"turn.completed"}\n{"type":"turn.completed"}\n',
    '{"type":"turn.completed"}\n{"type":"item.completed"}\n',
    '{"type":"item.completed","item":{"type":"error","message":"failure"}}\n{"type":"turn.completed"}\n',
    '{"type":"unexpected.event"}\n{"type":"turn.completed"}\n',
    '{bad json}\n',
])
def test_codex_rejects_incomplete_failed_or_malformed_jsonl(output):
    with pytest.raises(SubscriptionRuntimeError):
        _codex_text(output)


@pytest.mark.parametrize(("diagnostic", "category"), [
    ("401 Unauthorized", "authentication"),
    ("usage limit reached", "allowance"),
    ("insufficient credits", "credit"),
    ("blocked by policy", "policy"),
    ("model not found", "capability"),
    ("unexpected exit", "provider_failure"),
])
def test_provider_diagnostics_map_to_safe_failure_categories(diagnostic, category):
    assert _failure_category(diagnostic) == category


@pytest.mark.skipif(os.name != "posix", reason="process-group behavior is POSIX-specific")
def test_sync_termination_escalates_to_kill_for_remaining_process_group(monkeypatch):
    calls = []

    class FakeProcess:
        pid = 55555
        returncode = None

        def poll(self):
            return self.returncode

        def wait(self, timeout=None):
            self.returncode = -signal.SIGKILL
            return self.returncode

    process = FakeProcess()
    group_exists = True
    clock = 0.0

    def fake_monotonic():
        nonlocal clock
        clock += 1
        return clock

    def fake_killpg(pid, sig):
        nonlocal group_exists
        calls.append(sig)
        if sig == 0:
            if not group_exists:
                raise ProcessLookupError
            return
        if sig == signal.SIGKILL:
            group_exists = False

    monkeypatch.setattr("jarvis.subscription.os.killpg", fake_killpg)
    monkeypatch.setattr("jarvis.subscription.time.monotonic", fake_monotonic)
    monkeypatch.setattr("jarvis.subscription.time.sleep", lambda _seconds: None)
    _terminate_sync(process)

    assert calls[0] == signal.SIGTERM
    assert calls[-1] == signal.SIGKILL
    assert process.returncode == -signal.SIGKILL


def test_codex_process_failure_does_not_expose_provider_output(monkeypatch):
    def fake_popen(argv, **kwargs):
        process = _FakePopen(argv, **kwargs)
        process.returncode = 2
        process.kwargs["fake_stdout"] = "sensitive provider diagnostics"
        process.kwargs["fake_stderr"] = "Authentication failed: token details suppressed"
        return process

    monkeypatch.setenv(_CODEX_NO_TOOL_VERIFICATION_ENV, "1")
    monkeypatch.setattr("jarvis.subscription.subprocess.Popen", fake_popen)
    with pytest.raises(SubscriptionRuntimeError) as exc:
        _run_codex("gpt-codex", [], 3)
    assert "sensitive provider diagnostics" not in str(exc.value)
    assert exc.value.category == "authentication"


@pytest.mark.asyncio
async def test_async_process_cancellation_terminates_and_reaps_owned_group(monkeypatch, tmp_path):
    signals = []
    group_exists = True
    ready = asyncio.Event()
    released = asyncio.Event()

    class FakeAsyncProcess:
        pid = 123456
        returncode = None

        async def communicate(self, input=None):
            self.input = input
            ready.set()
            await released.wait()
            return b"late result", b""

        async def wait(self):
            self.returncode = -signal.SIGTERM
            released.set()
            return self.returncode

        def terminate(self):
            self.returncode = -signal.SIGTERM
            released.set()

        def kill(self):
            self.returncode = -signal.SIGKILL
            released.set()

    process = FakeAsyncProcess()
    seen = {}
    canary = "PRIVATE_SKILL_TASK_CANARY_ASYNC_21bc"

    async def fake_create(*argv, **kwargs):
        seen.update(argv=argv, kwargs=kwargs)
        return process

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("jarvis.subscription.asyncio.create_subprocess_exec", fake_create)
    def fake_killpg(pid, sig):
        nonlocal group_exists
        if sig == 0:
            if not group_exists:
                raise ProcessLookupError
            return
        signals.append((pid, sig))
        group_exists = False

    monkeypatch.setattr("jarvis.subscription.os.killpg", fake_killpg)

    task = asyncio.create_task(_run_async(["fake-provider", "--json"], canary, 30,
                                          provider="Fake"))
    await ready.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert signals == [(process.pid, signal.SIGTERM)]
    assert process.returncode is not None
    assert process.input == canary.encode("utf-8")
    assert canary not in seen["argv"]
    assert seen["kwargs"]["cwd"] != str(tmp_path)
    assert not Path(seen["kwargs"]["cwd"]).exists()


@pytest.mark.asyncio
@pytest.mark.skipif(os.name != "posix", reason="process-group behavior is POSIX-specific")
async def test_async_cancellation_terminates_real_provider_child_process_group(tmp_path):
    child_pid_file = tmp_path / "child.pid"
    child_code = (
        "import os,subprocess,sys,time; from pathlib import Path; "
        "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); "
        "Path(sys.argv[1]+'.tmp').write_text(str(child.pid)); "
        "os.replace(sys.argv[1]+'.tmp',sys.argv[1]); time.sleep(60)"
    )
    task = asyncio.create_task(_run_async(
        [sys.executable, "-c", child_code, str(child_pid_file)],
        "private prompt", 30, provider="Fake",
    ))
    deadline = asyncio.get_running_loop().time() + 3
    while not child_pid_file.exists() and asyncio.get_running_loop().time() < deadline:
        await asyncio.sleep(0.02)
    assert child_pid_file.exists(), "fake provider child did not start"
    child_pid = int(child_pid_file.read_text())

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    # The child shares its parent's process group. Wait briefly for OS reaping
    # before failing, without relying on a provider process or a long sleep.
    deadline = asyncio.get_running_loop().time() + 2
    while asyncio.get_running_loop().time() < deadline:
        try:
            os.kill(child_pid, 0)
        except ProcessLookupError:
            break
        await asyncio.sleep(0.02)
    else:
        pytest.fail("provider child remained alive after process-group cancellation")


@pytest.mark.asyncio
@pytest.mark.skipif(os.name != "posix", reason="process-group behavior is POSIX-specific")
async def test_timeout_kills_descendant_after_provider_leader_has_exited(tmp_path):
    child_pid_file = tmp_path / "orphan.pid"
    child_code = (
        "import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); time.sleep(60)"
    )
    parent_code = (
        "import subprocess,sys; "
        "child=subprocess.Popen([sys.executable,'-c',sys.argv[2]]); "
        "open(sys.argv[1],'w').write(str(child.pid))"
    )

    with pytest.raises(SubscriptionRuntimeError) as exc:
        await _run_async(
            [sys.executable, "-c", parent_code, str(child_pid_file), child_code],
            "private prompt", 0.05, provider="Fake",
        )
    assert exc.value.category == "timeout"
    assert child_pid_file.exists()
    child_pid = int(child_pid_file.read_text())

    deadline = asyncio.get_running_loop().time() + 2
    while asyncio.get_running_loop().time() < deadline:
        try:
            os.kill(child_pid, 0)
        except ProcessLookupError:
            break
        await asyncio.sleep(0.02)
    else:
        pytest.fail("orphaned provider child remained alive after timeout cleanup")


@pytest.mark.asyncio
async def test_codex_client_rejects_tools_and_unverified_runtime(monkeypatch):
    monkeypatch.delenv(_CODEX_NO_TOOL_VERIFICATION_ENV, raising=False)
    client = CodexSubscriptionTextClient("gpt-codex")
    with pytest.raises(SubscriptionRuntimeError, match="does not support Mortimer tools"):
        await client.chat.completions.create(tools=[{"type": "function"}], messages=[])
    with pytest.raises(SubscriptionCapabilityError, match="no-tools runtime capability"):
        await client.chat.completions.create(messages=[])
