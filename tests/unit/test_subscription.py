from __future__ import annotations

from types import SimpleNamespace

import pytest

from jarvis.subscription import (
    CodexSubscriptionTextClient,
    SubscriptionRuntimeError,
    _subscription_env,
    _run_codex,
)


def test_codex_jsonl_adapter_returns_final_assistant_text(monkeypatch):
    seen = {}

    def fake_run(argv, **kwargs):
        seen["argv"] = argv
        return SimpleNamespace(
            returncode=0,
            stderr="",
            stdout='{"type":"progress","text":"working"}\n'
                   '{"type":"message","text":"final answer"}\n',
        )

    monkeypatch.setattr("jarvis.subscription.subprocess.run", fake_run)
    assert _run_codex("gpt-5.1-codex-max", [{"role": "user", "content": "hi"}], 3) == "final answer"
    assert seen["argv"][:8] == ["codex", "exec", "--json", "--ephemeral",
                                  "--skip-git-repo-check", "--sandbox", "read-only", "--model"]


def test_codex_jsonl_adapter_reads_item_completed_agent_message(monkeypatch):
    monkeypatch.setattr(
        "jarvis.subscription.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0, stderr="",
            stdout='{"type":"item.completed","item":{"type":"agent_message","text":"MORTIMER_SUBSCRIPTION_PROBE_OK"}}\n',
        ),
    )
    assert _run_codex("gpt-6-astra", [], 3) == "MORTIMER_SUBSCRIPTION_PROBE_OK"


def test_subscription_environment_strips_api_credentials_and_endpoint_overrides(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "should-not-leak")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://paid.example/v1")
    monkeypatch.setenv("OPENROUTER_API_KEY", "should-not-leak")
    monkeypatch.setenv("HOME", "/Users/tester")

    env = _subscription_env()

    assert "ANTHROPIC_API_KEY" not in env
    assert "OPENAI_BASE_URL" not in env
    assert "OPENROUTER_API_KEY" not in env
    assert env["HOME"] == "/Users/tester"


def test_codex_probe_passes_isolated_environment(monkeypatch):
    seen = {}
    monkeypatch.setenv("OPENAI_API_KEY", "should-not-leak")

    def fake_run(argv, **kwargs):
        seen["env"] = kwargs["env"]
        return SimpleNamespace(returncode=0, stderr="", stdout='{"type":"message","text":"ok"}\n')

    monkeypatch.setattr("jarvis.subscription.subprocess.run", fake_run)
    assert _run_codex("gpt-6-astra", [], 3) == "ok"
    assert "OPENAI_API_KEY" not in seen["env"]


def test_codex_adapter_reports_cli_failure(monkeypatch):
    monkeypatch.setattr(
        "jarvis.subscription.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(returncode=2, stderr="not logged in", stdout=""),
    )
    with pytest.raises(SubscriptionRuntimeError, match="not logged in"):
        _run_codex("gpt-5.1-codex-max", [], 3)


@pytest.mark.asyncio
async def test_codex_client_keeps_tools_disabled(monkeypatch):
    client = CodexSubscriptionTextClient("gpt-5.1-codex-max")
    with pytest.raises(SubscriptionRuntimeError, match="does not support Mortimer tools"):
        await client.chat.completions.create(tools=[{"type": "function"}], messages=[])
