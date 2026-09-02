"""Unit tests for jarvis/effort.py's extra_body_for()
(MORTIMER_OPTIMIZATION_PLAN.md Phase 1b, Rev 3.2).

No jarvis dependencies needed -- this module only imports stdlib
os/typing, so these tests run directly against the module.
"""

from __future__ import annotations

import pytest

from jarvis import effort


class TestNonAnthropicProvider:
    """output_config only exists on Anthropic's native Messages API --
    every other provider always gets {} regardless of explicit/model."""

    def test_moonshot_with_explicit_returns_empty(self):
        assert effort.extra_body_for(
            rung="scheduler", provider="moonshot", explicit="low", model="kimi-k2"
        ) == {}

    def test_openrouter_with_explicit_returns_empty(self):
        assert effort.extra_body_for(
            rung="scheduler", provider="openrouter", explicit="high", model="or-gpt-5-mini"
        ) == {}

    def test_plain_openai_with_explicit_returns_empty(self):
        assert effort.extra_body_for(
            rung="scheduler", provider="openai", explicit="max", model="gpt-5"
        ) == {}

    def test_non_anthropic_ignores_env_override_too(self, monkeypatch):
        monkeypatch.setenv("JARVIS_EFFORT_SCHEDULER", "low")
        assert effort.extra_body_for(
            rung="scheduler", provider="moonshot", explicit=None, model="kimi-k2"
        ) == {}


class TestHaikuGuard:
    """Haiku 4.5 is not a supported model for output_config.effort --
    refuse regardless of what's configured, case-insensitive substring."""

    def test_haiku_lowercase_returns_empty(self):
        assert effort.extra_body_for(
            rung="supervisor", provider="anthropic", explicit="low", model="claude-haiku-4-5"
        ) == {}

    def test_haiku_uppercase_returns_empty(self):
        assert effort.extra_body_for(
            rung="supervisor", provider="anthropic", explicit="low", model="CLAUDE-HAIKU-4-5"
        ) == {}

    def test_haiku_mixed_case_substring_returns_empty(self):
        assert effort.extra_body_for(
            rung="supervisor", provider="anthropic", explicit="high", model="Claude-Haiku-X"
        ) == {}

    def test_haiku_ignores_env_override_too(self, monkeypatch):
        monkeypatch.setenv("JARVIS_EFFORT_SUPERVISOR", "low")
        assert effort.extra_body_for(
            rung="supervisor", provider="anthropic", explicit=None, model="claude-haiku-4-5"
        ) == {}

    def test_none_model_is_not_haiku(self):
        # model=None must not crash the "haiku" in (model or "").lower() check
        assert effort.extra_body_for(
            rung="scheduler", provider="anthropic", explicit=None, model=None
        ) == {}


class TestAnthropicNonHaiku:
    def test_no_explicit_no_env_returns_empty(self):
        assert effort.extra_body_for(
            rung="scheduler", provider="anthropic", explicit=None, model="claude-sonnet-5"
        ) == {}

    def test_explicit_level_returns_output_config(self):
        assert effort.extra_body_for(
            rung="scheduler", provider="anthropic", explicit="low", model="claude-sonnet-5"
        ) == {"output_config": {"effort": "low"}}

    @pytest.mark.parametrize("level", sorted(effort.VALID_LEVELS))
    def test_every_valid_level_accepted(self, level):
        assert effort.extra_body_for(
            rung="analyst", provider="anthropic", explicit=level, model="claude-opus"
        ) == {"output_config": {"effort": level}}

    def test_invalid_explicit_level_raises(self):
        with pytest.raises(ValueError, match="invalid effort level"):
            effort.extra_body_for(
                rung="scheduler", provider="anthropic", explicit="ultra", model="claude-sonnet-5"
            )


class TestEnvVarOverride:
    def test_env_var_wins_over_explicit(self, monkeypatch):
        monkeypatch.setenv("JARVIS_EFFORT_SCHEDULER", "xhigh")
        result = effort.extra_body_for(
            rung="scheduler", provider="anthropic", explicit="low", model="claude-sonnet-5"
        )
        assert result == {"output_config": {"effort": "xhigh"}}

    def test_env_var_applies_when_explicit_is_none(self, monkeypatch):
        monkeypatch.setenv("JARVIS_EFFORT_LIBRARIAN", "medium")
        result = effort.extra_body_for(
            rung="librarian", provider="anthropic", explicit=None, model="claude-sonnet-5"
        )
        assert result == {"output_config": {"effort": "medium"}}

    def test_invalid_env_var_level_raises(self, monkeypatch):
        monkeypatch.setenv("JARVIS_EFFORT_SCHEDULER", "bogus")
        with pytest.raises(ValueError, match="invalid effort level"):
            effort.extra_body_for(
                rung="scheduler", provider="anthropic", explicit="low", model="claude-sonnet-5"
            )

    def test_underscored_rung_maps_to_env_var_name(self, monkeypatch):
        monkeypatch.setenv("JARVIS_EFFORT_SELFEDIT_EXECUTOR", "low")
        result = effort.extra_body_for(
            rung="selfedit_executor", provider="anthropic", explicit=None, model="claude-sonnet-5"
        )
        assert result == {"output_config": {"effort": "low"}}

    def test_empty_env_var_falls_back_to_explicit(self, monkeypatch):
        # An unset env var (monkeypatch.delenv/never set) must not shadow
        # a real explicit value -- confirms os.environ.get(...) returning
        # None doesn't accidentally short-circuit into "" or similar.
        monkeypatch.delenv("JARVIS_EFFORT_SCHEDULER", raising=False)
        result = effort.extra_body_for(
            rung="scheduler", provider="anthropic", explicit="medium", model="claude-sonnet-5"
        )
        assert result == {"output_config": {"effort": "medium"}}


class TestReturnShapeIsFreshDict:
    def test_two_calls_do_not_share_mutable_state(self):
        r1 = effort.extra_body_for(
            rung="scheduler", provider="anthropic", explicit="low", model="claude-sonnet-5"
        )
        r2 = effort.extra_body_for(
            rung="scheduler", provider="anthropic", explicit="high", model="claude-sonnet-5"
        )
        r1["output_config"]["effort"] = "mutated"
        assert r2["output_config"]["effort"] == "high"
