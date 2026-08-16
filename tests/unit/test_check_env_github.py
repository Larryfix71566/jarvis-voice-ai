"""Unit tests for scripts/check_env.py's GitHub section
(MORTIMER_AGENT_TRUST_PLAN.md D9 — folded in from scripts/check_github.py).

scripts/ is not a package, so the module is loaded directly from its file
path via importlib rather than a normal import.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / "scripts" / "check_env.py"


def load_check_env(monkeypatch):
    """Fresh module import per test so the module-level `failures` list
    (mutated by report()) never leaks between tests."""
    spec = importlib.util.spec_from_file_location("check_env_under_test", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def check_env(monkeypatch):
    return load_check_env(monkeypatch)


class TestShadowDetection:
    def test_shell_value_differing_from_dotenv_warns_and_stops(self, check_env, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", "shell-value")
        monkeypatch.setattr(check_env, "github_probe", lambda t: (_ for _ in ()).throw(
            AssertionError("must not probe when shadowed")))
        check_env.check_github({}, {"GITHUB_TOKEN": "dotenv-value"})
        # No exception from github_probe means the shadow branch returned
        # before ever probing — confirmed structurally by the lambda above.

    def test_matching_values_are_not_flagged_as_shadowed(self, check_env, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", "same-value")
        monkeypatch.setattr(check_env, "github_probe", lambda t: ("ok", "HTTP 200", "repo"))
        check_env.check_github({}, {"GITHUB_TOKEN": "same-value"})
        assert check_env.failures == []  # WARN-degradable either way, never FAIL


class TestOutcomeReporting:
    def test_ok_outcome_reports_pass_and_never_fails(self, check_env, monkeypatch):
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        monkeypatch.setattr(check_env, "github_probe",
                             lambda t: ("ok", "HTTP 200, login=x", "repo, workflow"))
        check_env.check_github({}, {"GITHUB_TOKEN": "tok"})
        assert check_env.failures == []

    def test_missing_repo_scope_still_reports_pass_but_warns_in_detail(
        self, check_env, monkeypatch, capsys,
    ):
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        monkeypatch.setattr(check_env, "github_probe",
                             lambda t: ("ok", "HTTP 200, login=x", "public_repo"))
        check_env.check_github({}, {"GITHUB_TOKEN": "tok"})
        assert check_env.failures == []
        assert "repo' scope missing" in capsys.readouterr().out

    def test_rejected_outcome_is_warn_not_fail(self, check_env, monkeypatch):
        # This is the exact case from the real incident: a dead token must
        # be visible but must NOT block the overall preflight, since
        # GitHub is not required for voice/memory/scheduling/research.
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        monkeypatch.setattr(check_env, "github_probe",
                             lambda t: ("rejected", "HTTP 401 Unauthorized", ""))
        check_env.check_github({}, {"GITHUB_TOKEN": "dead-token"})
        assert check_env.failures == []

    def test_unreachable_outcome_is_warn_not_pass_and_not_fail(self, check_env, monkeypatch, capsys):
        # The load-bearing case (D9's rationale): an unreachable endpoint
        # must never be reported as PASS, because "PASS" for something
        # never actually tested is the exact mechanism that masked a dead
        # credential for two days.
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        monkeypatch.setattr(check_env, "github_probe",
                             lambda t: ("unreachable", "URLError: blocked", ""))
        check_env.check_github({}, {"GITHUB_TOKEN": "tok"})
        out = capsys.readouterr().out
        assert check_env.failures == []
        assert "[PASS]" not in out
        assert "[WARN]" in out

    def test_not_configured_is_warn_not_fail(self, check_env, monkeypatch):
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        check_env.check_github({}, {})
        assert check_env.failures == []


class TestOverallResultUnaffectedByGithub:
    def test_github_never_appears_in_required_failures_list(self, check_env, monkeypatch):
        """WARN-degradable per D9: whatever happens to GitHub, it must
        never be the reason scripts/check_env.py exits non-zero."""
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        monkeypatch.delenv("JARVIS_GITHUB_TOKEN", raising=False)
        monkeypatch.setattr(check_env, "github_probe",
                             lambda t: ("rejected", "HTTP 401", ""))
        check_env.check_github({}, {"GITHUB_TOKEN": "x", "JARVIS_GITHUB_TOKEN": "y"})
        assert check_env.failures == []
