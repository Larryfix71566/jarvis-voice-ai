"""T4.2 — subscription probes (fake runners; no CLI, no quota)."""

from __future__ import annotations

import json
import shutil

import pytest

from jarvis.status import subscriptions as S
from jarvis.subscription import SubscriptionRuntimeError


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    S.clear_cache_for_tests()
    monkeypatch.delenv("JARVIS_CLAUDE_SUBSCRIPTION_COMMAND", raising=False)
    monkeypatch.delenv("JARVIS_CODEX_SUBSCRIPTION_COMMAND", raising=False)
    monkeypatch.setattr(shutil, "which", lambda cmd, *a, **k: f"/opt/homebrew/bin/{cmd}")
    yield
    S.clear_cache_for_tests()


class Runner:
    def __init__(self, outcome):
        self.outcome = outcome
        self.calls = []

    def __call__(self, model, messages, timeout):
        self.calls.append((model, messages, timeout))
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


# fake runner outcome -> (ok, response_present, category); the five
# pre-existing categories are the script's former _probe_subscription table.
TABLE = [
    ("MORTIMER_SUBSCRIPTION_PROBE_OK", (True, True, None)),
    ("\n MORTIMER_SUBSCRIPTION_PROBE_OK \n", (True, True, None)),
    ("Here you go: MORTIMER_SUBSCRIPTION_PROBE_OK", (False, True, None)),
    ("", (False, False, None)),
    (SubscriptionRuntimeError("HTTP 401 Unauthorized"), (False, False, "authentication")),
    (SubscriptionRuntimeError("token revoked"), (False, False, "authentication")),
    (SubscriptionRuntimeError("Please authenticate first"), (False, False, "authentication")),
    (SubscriptionRuntimeError('{"result":"Not logged in · Please run /login"}'),
     (False, False, "authentication")),
    (SubscriptionRuntimeError("model claude-fable-5-1 not found"),
     (False, False, "model_unavailable")),
    (SubscriptionRuntimeError("unsupported value"), (False, False, "model_unavailable")),
    (SubscriptionRuntimeError("Command timed out after 25 seconds"), (False, False, "timeout")),
    (SubscriptionRuntimeError("read timeout"), (False, False, "timeout")),
    (SubscriptionRuntimeError("Operation not permitted"), (False, False, "runtime_environment")),
    (SubscriptionRuntimeError("Permission denied: ~/.codex"), (False, False, "runtime_environment")),
    (SubscriptionRuntimeError("attempt to write a readonly database"),
     (False, False, "runtime_environment")),
    (SubscriptionRuntimeError("Read-only file system"), (False, False, "runtime_environment")),
    (SubscriptionRuntimeError("exited 1: segfault"), (False, False, "runtime_error")),
]


@pytest.mark.parametrize("outcome,expected", TABLE)
def test_probe_categories_match_script(outcome, expected):
    res = S.probe_subscription("claude", "claude-sonnet-5", runner=Runner(outcome))
    assert (res["ok"], res["response_present"], res["category"]) == expected


def test_result_shape():
    res = S.probe_subscription("codex", "gpt-6-astra", runner=Runner("MORTIMER_SUBSCRIPTION_PROBE_OK"))
    assert set(res) == {"which", "model", "ok", "response_present", "category", "installed",
                        "command", "probed_at", "cached"}
    assert res["which"] == "codex" and res["command"] == "codex" and res["installed"] is True
    assert res["cached"] is False


def test_prompt_token_and_default_timeout():
    runner = Runner("MORTIMER_SUBSCRIPTION_PROBE_OK")
    S.probe_subscription("claude", runner=runner)
    model, messages, timeout = runner.calls[0]
    assert model == "claude-sonnet-5"
    assert messages == [{"role": "user", "content":
                         "Reply with exactly MORTIMER_SUBSCRIPTION_PROBE_OK and do not use tools."}]
    assert timeout == 25.0


def test_codex_default_is_the_registry_profile_model():
    from jarvis.agents.upgrade_agent import load_model_registry

    profiles = load_model_registry()["profiles"]
    assert S.default_probe_model("codex") == profiles["codex-subscription"]["model"]
    reg = {"profiles": {"codex-subscription": {"model": "gpt-7-nova"}}}
    assert S.default_probe_model("codex", reg) == "gpt-7-nova"
    runner = Runner("x")
    S.probe_subscription("codex", runner=runner)
    assert runner.calls[0][0] == profiles["codex-subscription"]["model"]


def test_model_passed_through_verbatim():
    runner = Runner(SubscriptionRuntimeError("model not found"))
    res = S.probe_subscription("claude", "Fable 5.1 ", runner=runner)
    assert runner.calls[0][0] == "Fable 5.1 "
    assert res["model"] == "Fable 5.1 "
    assert res["category"] == "model_unavailable"


def test_rate_limit_and_force(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(S.time, "monotonic", lambda: clock[0])
    runner = Runner("MORTIMER_SUBSCRIPTION_PROBE_OK")
    first = S.probe_subscription("claude", "claude-sonnet-5", runner=runner)
    again = S.probe_subscription("claude", "claude-sonnet-5", runner=runner)
    assert len(runner.calls) == 1
    assert again["cached"] is True and first["cached"] is False
    assert again["probed_at"] == first["probed_at"]
    # A different model is a different key.
    S.probe_subscription("claude", "claude-opus-5", runner=runner)
    assert len(runner.calls) == 2
    # force bypasses; the window expires after PROBE_RATE_LIMIT_S.
    S.probe_subscription("claude", "claude-sonnet-5", runner=runner, force=True)
    assert len(runner.calls) == 3
    clock[0] += S.PROBE_RATE_LIMIT_S - 1
    S.probe_subscription("claude", "claude-sonnet-5", runner=runner)
    assert len(runner.calls) == 3
    clock[0] += 2
    S.probe_subscription("claude", "claude-sonnet-5", runner=runner)
    assert len(runner.calls) == 4
    assert S.PROBE_RATE_LIMIT_S == 600


def test_not_installed_runs_nothing(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda cmd, *a, **k: None)
    monkeypatch.setenv("JARVIS_CODEX_SUBSCRIPTION_COMMAND", "/nowhere/codex")
    runner = Runner("MORTIMER_SUBSCRIPTION_PROBE_OK")
    res = S.probe_subscription("codex", "gpt-6-astra", runner=runner)
    assert runner.calls == []
    assert (res["ok"], res["category"], res["installed"], res["command"]) == (
        False, "not_installed", False, "/nowhere/codex")
    # Nothing was spent, so nothing is rate-limited: a fix shows at once.
    monkeypatch.setattr(shutil, "which", lambda cmd, *a, **k: cmd)
    assert S.probe_subscription("codex", "gpt-6-astra", runner=runner)["ok"] is True


def test_unknown_which_is_refused():
    with pytest.raises(ValueError):
        S.probe_subscription("gemini", runner=Runner("x"))  # type: ignore[arg-type]
    assert S.subscription_status("gemini") == {"ok": False,
                                              "error": "which must be 'claude' or 'codex'"}


def test_subscription_status_payload(monkeypatch):
    monkeypatch.setattr(S, "_default_runner", lambda which: Runner(
        SubscriptionRuntimeError("HTTP 401 sk-ant-secret-should-not-matter")))
    out = S.subscription_status("claude", "claude-fable-5-1", force=True)
    assert out["ok"] is True
    assert out["source"] == f"probe:claude@{out['probe']['probed_at']}"
    assert out["probe"]["model"] == "claude-fable-5-1"
    assert out["probe"]["category"] == "authentication"
    # Error text is classified, never relayed (I1).
    assert "sk-ant" not in json.dumps(out)
