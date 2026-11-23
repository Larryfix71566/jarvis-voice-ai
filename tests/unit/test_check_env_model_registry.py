"""Unit tests for scripts/check_env.py's check_model_registry() (H2,
MORTIMER_CONFIRMATION_AND_CAPABILITY_PLAN.md) — reports per-profile key
presence from the model registry, plus a per-sub-agent
cross-reference against config/agents.yaml's model_profile /
on_profile_fallback, with special wording when a REFUSE-mode agent's key
is missing (developer's real-world incident this plan fixes).

scripts/ is not a package, so the module is loaded directly from its file
path via importlib, matching test_check_env_github.py's pattern. Each test
writes its own tiny YAML fixtures to tmp_path and points REPO_ROOT there
so it never depends on the real config/ files.
"""

import importlib.util
from pathlib import Path

import pytest

REAL_REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REAL_REPO_ROOT / "scripts" / "check_env.py"


def load_check_env():
    spec = importlib.util.spec_from_file_location("check_env_under_test_registry", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def check_env(monkeypatch, tmp_path):
    module = load_check_env()
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
    (tmp_path / "config").mkdir()
    return module


def _write_registry(tmp_path, text):
    (tmp_path / "config" / "upgrade_models.yaml").write_text(text, encoding="utf-8")


def _write_agents(tmp_path, text):
    (tmp_path / "config" / "agents.yaml").write_text(text, encoding="utf-8")


REGISTRY_YAML = """
default: or-grok
profiles:
  - name: or-grok
    provider: openrouter
    model: x-ai/grok-4.3
    api_key_env: OPENROUTER_API_KEY
  - name: or-gemini
    provider: openrouter
    model: google/gemini-3.7-flash
    api_key_env: GEMINI_TEST_KEY
  - name: claude-opus
    provider: anthropic
    model: claude-opus-5
"""


class TestProfileReporting:
    def test_present_key_reports_pass(self, check_env, monkeypatch, tmp_path, capsys):
        _write_registry(tmp_path, REGISTRY_YAML)
        monkeypatch.setenv("OPENROUTER_API_KEY", "x")
        monkeypatch.setenv("GEMINI_TEST_KEY", "y")
        check_env.check_model_registry()
        out = capsys.readouterr().out
        assert "[PASS]" in out
        assert "[WARN]" not in out
        assert check_env.failures == []

    def test_missing_key_reports_warn_not_fail(self, check_env, monkeypatch, tmp_path, capsys):
        _write_registry(tmp_path, REGISTRY_YAML)
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_TEST_KEY", raising=False)
        check_env.check_model_registry()
        out = capsys.readouterr().out
        assert "[WARN]" in out
        assert "[FAIL]" not in out
        assert check_env.failures == []  # never blocks preflight

    def test_default_profile_labeled_as_registry_default(self, check_env, monkeypatch, tmp_path, capsys):
        _write_registry(tmp_path, REGISTRY_YAML)
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        check_env.check_model_registry()
        out = capsys.readouterr().out
        assert "or-grok (registry default)" in out
        assert "claude-opus (registry default)" not in out

    def test_missing_registry_file_warns_and_returns(self, check_env, capsys):
        # no upgrade_models.yaml written
        check_env.check_model_registry()
        out = capsys.readouterr().out
        assert "[WARN]" in out
        assert "file not found" in out
        assert check_env.failures == []

    def test_unparseable_registry_warns_and_returns(self, check_env, tmp_path, capsys):
        _write_registry(tmp_path, "not: valid: yaml: [")
        check_env.check_model_registry()
        out = capsys.readouterr().out
        assert "[WARN]" in out
        assert "could not parse" in out


class TestAgentCrossReference:
    def test_agent_with_present_key_reports_pass(self, check_env, monkeypatch, tmp_path, capsys):
        _write_registry(tmp_path, REGISTRY_YAML)
        _write_agents(tmp_path, """
sub_agents:
  - name: developer
    model_profile: or-grok
    on_profile_fallback: refuse
""")
        monkeypatch.setenv("OPENROUTER_API_KEY", "x")
        monkeypatch.setenv("GEMINI_TEST_KEY", "y")
        check_env.check_model_registry()
        out = capsys.readouterr().out
        assert "developer's model_profile (or-grok, on_profile_fallback=refuse)" in out
        assert "OPENROUTER_API_KEY present" in out

    def test_refuse_mode_missing_key_gets_refuse_wording(self, check_env, monkeypatch, tmp_path, capsys):
        _write_registry(tmp_path, REGISTRY_YAML)
        _write_agents(tmp_path, """
sub_agents:
  - name: developer
    model_profile: or-grok
    on_profile_fallback: refuse
""")
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        check_env.check_model_registry()
        out = capsys.readouterr().out
        assert "developer will REFUSE every delegation until this is fixed" in out
        assert check_env.failures == []

    def test_warn_mode_missing_key_gets_silent_fallback_wording(self, check_env, monkeypatch, tmp_path, capsys):
        _write_registry(tmp_path, REGISTRY_YAML)
        _write_agents(tmp_path, """
sub_agents:
  - name: scheduler
    model_profile: or-gemini
""")
        monkeypatch.delenv("GEMINI_TEST_KEY", raising=False)
        check_env.check_model_registry()
        out = capsys.readouterr().out
        assert "scheduler will silently fall back to the voice model" in out
        assert "REFUSE" not in out

    def test_agent_without_model_profile_is_skipped(self, check_env, monkeypatch, tmp_path, capsys):
        _write_registry(tmp_path, REGISTRY_YAML)
        _write_agents(tmp_path, """
sub_agents:
  - name: scheduler
""")
        check_env.check_model_registry()
        out = capsys.readouterr().out
        assert "scheduler's model_profile" not in out

    def test_missing_agents_yaml_does_not_error(self, check_env, tmp_path, capsys):
        _write_registry(tmp_path, REGISTRY_YAML)
        # no agents.yaml written at all
        check_env.check_model_registry()  # must not raise
        out = capsys.readouterr().out
        assert "[WARN]" in out or "[PASS]" in out

    def test_subscription_profile_needs_no_key(self, check_env, monkeypatch, tmp_path, capsys):
        _write_registry(tmp_path, REGISTRY_YAML)
        _write_agents(tmp_path, """
sub_agents:
  - name: analyst
    model_profile: claude-opus
""")
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        check_env.check_model_registry()
        out = capsys.readouterr().out
        assert "analyst's model_profile (claude-opus" in out
        assert "subscription route (no API key)" in out
        assert "ANTHROPIC_API_KEY" not in out

    def test_unknown_profile_warns_not_in_registry(self, check_env, monkeypatch, tmp_path, capsys):
        _write_registry(tmp_path, REGISTRY_YAML)
        _write_agents(tmp_path, """
sub_agents:
  - name: analyst
    model_profile: nonexistent-profile
""")
        check_env.check_model_registry()
        out = capsys.readouterr().out
        assert "analyst's model_profile (nonexistent-profile" in out
        assert "not in the model registry" in out
        assert "OPENAI_API_KEY" not in out


class TestSubscriptionRuntimeAndRetiredKeys:
    def test_missing_flags_fail(self, check_env, capsys):
        check_env.check_subscription_runtime({})
        out = capsys.readouterr().out
        assert "[FAIL] Subscription runtime" in out
        assert "JARVIS_MODEL_ROUTING_ENABLED=1" in out
        assert "JARVIS_SUBSCRIPTION_TEXT_ENABLED=1" in out
        assert check_env.failures == ["Subscription runtime"]

    def test_flags_set_pass(self, check_env, capsys):
        check_env.check_subscription_runtime({"JARVIS_MODEL_ROUTING_ENABLED": "1",
                                              "JARVIS_SUBSCRIPTION_TEXT_ENABLED": "1"})
        assert "[PASS] Subscription runtime" in capsys.readouterr().out
        assert check_env.failures == []

    def test_retired_keys_warn_loudly(self, check_env, capsys):
        check_env.check_retired_keys({"ANTHROPIC_API_KEY": "x", "OPENAI_API_KEY": "y",
                                      "MOONSHOT_API_KEY": "z"})
        out = capsys.readouterr().out
        for name in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "MOONSHOT_API_KEY"):
            assert f"[WARN] RETIRED API key {name} is still set" in out
        assert "revoke it in the provider console" in out
        assert check_env.failures == []

    def test_no_retired_keys_is_silent(self, check_env, capsys):
        check_env.check_retired_keys({})
        assert capsys.readouterr().out == ""

    def test_openai_key_no_longer_required(self, check_env):
        assert "OPENAI_API_KEY" not in check_env.REQUIRED_VARS
