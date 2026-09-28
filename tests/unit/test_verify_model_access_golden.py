"""T4.2 — `scripts/verify_model_access.py`'s JSON output stays byte-identical
after its subscription probe moved to `jarvis.status.subscriptions`.

The goldens below were captured from the UNMODIFIED script (before T4.2's
refactor) with the same fake runners and fixture access policy, so any
drift in the report the operator reads is a failure here.
"""

from __future__ import annotations

import json
import shutil

import pytest

import scripts.verify_model_access as V

ACCESS = {
    "routes": {
        "subscription": {"adapter": "subscription_runtime", "billing": "subscription",
                         "privacy": "approved_external", "capabilities": ["text"]},
        "codex_subscription": {"adapter": "codex_subscription_runtime",
                               "billing": "subscription", "privacy": "approved_external",
                               "capabilities": ["text"]},
        "saygm": {"adapter": "saygm_gateway", "billing": "saygm_credit",
                  "credential_env": "SAYGM_API_KEY", "base_url": "https://api.saygm.com/v1",
                  "privacy": "approved_external", "capabilities": ["tools", "text"]},
    },
    "workloads": {},
}

FULL_GOLDEN = """{
  "policy": "config/model_access.yaml",
  "routes": {
    "codex_subscription": {
      "adapter": "codex_subscription_runtime",
      "api_credentials_stripped_before_launch": true,
      "billing": "subscription",
      "capabilities": [
        "text"
      ],
      "command": "codex",
      "credential_env": null,
      "credential_present": false,
      "installed": true,
      "privacy": "approved_external"
    },
    "saygm": {
      "adapter": "saygm_gateway",
      "billing": "saygm_credit",
      "capabilities": [
        "text",
        "tools"
      ],
      "credential_env": "SAYGM_API_KEY",
      "credential_present": false,
      "privacy": "approved_external"
    },
    "subscription": {
      "adapter": "subscription_runtime",
      "api_credentials_stripped_before_launch": true,
      "billing": "subscription",
      "capabilities": [
        "text"
      ],
      "command": "claude",
      "credential_env": null,
      "credential_present": false,
      "installed": true,
      "privacy": "approved_external"
    }
  },
  "routing_enabled": false,
  "saygm_catalog": null,
  "subscription_probes": {
    "claude": {
      "ok": true,
      "response_present": true
    },
    "codex": {
      "category": "authentication",
      "ok": false
    }
  },
  "workloads": {}
}"""


def _raise(message):
    def runner(model, messages, timeout):
        raise V.SubscriptionRuntimeError(message)
    return runner


def _say(text):
    def runner(model, messages, timeout):
        return text
    return runner


# outcome of a fake runner -> the script's JSON for that probe (captured pre-refactor)
OUTCOMES = [
    (_say("MORTIMER_SUBSCRIPTION_PROBE_OK"), '{"ok": true, "response_present": true}'),
    (_say("  MORTIMER_SUBSCRIPTION_PROBE_OK\n"), '{"ok": true, "response_present": true}'),
    (_say("Sure! MORTIMER_SUBSCRIPTION_PROBE_OK"), '{"ok": false, "response_present": true}'),
    (_say("   "), '{"ok": false, "response_present": false}'),
    (_raise("HTTP 401 revoked token"), '{"category": "authentication", "ok": false}'),
    (_raise('{"result":"Not logged in · Please run /login"}'),
     '{"category": "authentication", "ok": false}'),
    (_raise("model gpt-7 not found"), '{"category": "model_unavailable", "ok": false}'),
    (_raise("unsupported option"), '{"category": "model_unavailable", "ok": false}'),
    (_raise("Codex subscription runtime failed: Command timed out after 45 seconds"),
     '{"category": "timeout", "ok": false}'),
    (_raise("Operation not permitted"), '{"category": "runtime_environment", "ok": false}'),
    (_raise("failed to open readonly database"),
     '{"category": "runtime_environment", "ok": false}'),
    (_raise("exited 1: boom"), '{"category": "runtime_error", "ok": false}'),
    (_raise("Claude subscription runtime failed: [Errno 2] No such file or directory: 'claude'"),
     '{"category": "runtime_error", "ok": false}'),
]


@pytest.fixture
def fixture_env(monkeypatch):
    monkeypatch.setattr(V, "load_access_config", lambda: ACCESS)
    monkeypatch.delenv("JARVIS_MODEL_ACCESS_CONFIG", raising=False)
    monkeypatch.delenv("JARVIS_MODEL_ROUTING_ENABLED", raising=False)
    monkeypatch.delenv("SAYGM_API_KEY", raising=False)
    monkeypatch.delenv("JARVIS_CLAUDE_SUBSCRIPTION_COMMAND", raising=False)
    monkeypatch.delenv("JARVIS_CODEX_SUBSCRIPTION_COMMAND", raising=False)
    monkeypatch.setattr(shutil, "which", lambda cmd, *a, **k: f"/usr/local/bin/{cmd}")


def test_script_output_unchanged(fixture_env, monkeypatch):
    calls = []

    def claude(model, messages, timeout):
        calls.append(("claude", model, messages, timeout))
        return "MORTIMER_SUBSCRIPTION_PROBE_OK"

    def codex(model, messages, timeout):
        calls.append(("codex", model, messages, timeout))
        raise V.SubscriptionRuntimeError("HTTP 401 revoked token secret-value")

    monkeypatch.setattr(V, "_run_claude", claude)
    monkeypatch.setattr(V, "_run_codex", codex)
    report = V.build_report(probe_subscriptions=True)
    assert json.dumps(report, indent=2, sort_keys=True) == FULL_GOLDEN
    prompt = [{"role": "user", "content":
               "Reply with exactly MORTIMER_SUBSCRIPTION_PROBE_OK and do not use tools."}]
    assert calls == [("claude", "claude-sonnet-5", prompt, 45.0),
                     ("codex", "gpt-6-astra", prompt, 45.0)]


@pytest.mark.parametrize("runner,golden", OUTCOMES)
def test_probe_json_per_outcome_unchanged(fixture_env, monkeypatch, runner, golden):
    monkeypatch.setattr(V, "_run_claude", runner)
    monkeypatch.setattr(V, "_run_codex", runner)
    report = V.build_report(probe_subscriptions=True)
    probes = report["subscription_probes"]
    assert json.dumps(probes["claude"], sort_keys=True) == golden
    assert json.dumps(probes["codex"], sort_keys=True) == golden


def test_missing_cli_still_runs_the_runner_like_before(fixture_env, monkeypatch):
    """Pre-refactor, the script never checked installation before probing:
    a missing CLI surfaced through the runner's own failure. Keep that."""
    monkeypatch.setattr(shutil, "which", lambda cmd, *a, **k: None)
    ran = []
    monkeypatch.setattr(V, "_run_claude", lambda *a: ran.append("claude") or "MORTIMER_SUBSCRIPTION_PROBE_OK")
    monkeypatch.setattr(V, "_run_codex", _raise(
        "Codex subscription runtime failed: [Errno 2] No such file or directory: 'codex'"))
    report = V.build_report(probe_subscriptions=True)
    assert ran == ["claude"]
    assert report["routes"]["subscription"]["installed"] is False
    assert json.dumps(report["subscription_probes"], sort_keys=True) == (
        '{"claude": {"ok": true, "response_present": true}, '
        '"codex": {"category": "runtime_error", "ok": false}}')
