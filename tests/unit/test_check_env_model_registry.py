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
default: kimi-k3
profiles:
  - name: kimi-k3
    api_key_env: MOONSHOT_API_KEY
  - name: claude-opus
    api_key_env: ANTHROPIC_API_KEY
"""


class TestProfileReporting:
    def test_present_key_reports_pass(self, check_env, monkeypatch, tmp_path, capsys):
        _write_registry(tmp_path, REGISTRY_YAML)
        monkeypatch.setenv("MOONSHOT_API_KEY", "x")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "y")
        check_env.check_model_registry()
        out = capsys.readouterr().out
        assert "[PASS]" in out
        assert "[WARN]" not in out
        assert check_env.failures == []

    def test_missing_key_reports_warn_not_fail(self, check_env, monkeypatch, tmp_path, capsys):
        _write_registry(tmp_path, REGISTRY_YAML)
        monkeypatch.delenv("MOONSHOT_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        check_env.check_model_registry()
        out = capsys.readouterr().out
        assert "[WARN]" in out
        assert "[FAIL]" not in out
        assert check_env.failures == []  # never blocks preflight

    def test_default_profile_labeled_as_registry_default(self, check_env, monkeypatch, tmp_path, capsys):
        _write_registry(tmp_path, REGISTRY_YAML)
        monkeypatch.delenv("MOONSHOT_API_KEY", raising=False)
        check_env.check_model_registry()
        out = capsys.readouterr().out
        assert "kimi-k3 (registry default)" in out
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
    model_profile: kimi-k3
    on_profile_fallback: refuse
""")
        monkeypatch.setenv("MOONSHOT_API_KEY", "x")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "y")
        check_env.check_model_registry()
        out = capsys.readouterr().out
        assert "developer's model_profile (kimi-k3, on_profile_fallback=refuse)" in out
        assert "MOONSHOT_API_KEY present" in out

    def test_refuse_mode_missing_key_gets_refuse_wording(self, check_env, monkeypatch, tmp_path, capsys):
        _write_registry(tmp_path, REGISTRY_YAML)
        _write_agents(tmp_path, """
sub_agents:
  - name: developer
    model_profile: kimi-k3
    on_profile_fallback: refuse
""")
        monkeypatch.delenv("MOONSHOT_API_KEY", raising=False)
        check_env.check_model_registry()
        out = capsys.readouterr().out
        assert "developer will REFUSE every delegation until this is fixed" in out
        assert check_env.failures == []

    def test_warn_mode_missing_key_gets_silent_fallback_wording(self, check_env, monkeypatch, tmp_path, capsys):
        _write_registry(tmp_path, REGISTRY_YAML)
        _write_agents(tmp_path, """
sub_agents:
  - name: scheduler
    model_profile: claude-opus
""")
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
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

    def test_unknown_profile_falls_back_to_openai_api_key_env(self, check_env, monkeypatch, tmp_path, capsys):
        _write_registry(tmp_path, REGISTRY_YAML)
        _write_agents(tmp_path, """
sub_agents:
  - name: analyst
    model_profile: nonexistent-profile
""")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        check_env.check_model_registry()
        out = capsys.readouterr().out
        assert "analyst's model_profile (nonexistent-profile" in out
        assert "OPENAI_API_KEY missing" in out
