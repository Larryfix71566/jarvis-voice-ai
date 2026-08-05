"""Unit tests for jarvis/config.py (plan Phase 0 Tests)."""

import os

import pytest

from jarvis.config import expand_env_vars, load_settings

REQUIRED = ("OPENAI_API_KEY", "DEEPGRAM_API_KEY", "ELEVENLABS_API_KEY")


@pytest.fixture
def clean_env(monkeypatch):
    """Strip all jarvis-related env vars so tests are hermetic."""
    for name in list(os.environ):
        if name.startswith(("OPENAI", "DEEPGRAM", "ELEVENLABS", "TAVILY", "JARVIS")):
            monkeypatch.delenv(name, raising=False)
    return monkeypatch


def _set_required(monkeypatch):
    for name in REQUIRED:
        monkeypatch.setenv(name, f"test-{name.lower()}")


def test_missing_required_key_raises_and_lists_it(clean_env):
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        load_settings(env_file=None)


def test_missing_multiple_required_keys_all_listed(clean_env):
    clean_env.setenv("OPENAI_API_KEY", "x")
    with pytest.raises(RuntimeError) as excinfo:
        load_settings(env_file=None)
    assert "DEEPGRAM_API_KEY" in str(excinfo.value)
    assert "ELEVENLABS_API_KEY" in str(excinfo.value)


def test_bad_timezone_raises(clean_env):
    _set_required(clean_env)
    clean_env.setenv("JARVIS_TIMEZONE", "Not/AZone")
    with pytest.raises(RuntimeError, match="Configuration error"):
        load_settings(env_file=None)


def test_valid_settings_load_with_defaults(clean_env):
    _set_required(clean_env)
    with pytest.warns(UserWarning, match="TAVILY_API_KEY"):
        settings = load_settings(env_file=None)
    assert settings.openai_base_url == "https://api.openai.com/v1"
    assert settings.openai_model == "gpt-4.1-mini"
    assert settings.jarvis_bot_port == 7860
    assert str(settings.db_path) == "data/jarvis.db"


def test_tavily_present_suppresses_warning(clean_env, recwarn):
    _set_required(clean_env)
    clean_env.setenv("TAVILY_API_KEY", "tvly-test")
    load_settings(env_file=None)
    assert not [w for w in recwarn.list if "TAVILY" in str(w.message)]


def test_expand_env_vars(clean_env):
    clean_env.setenv("JARVIS_TEST_VAR", "expanded")
    assert expand_env_vars("a-${JARVIS_TEST_VAR}-b") == "a-expanded-b"
    # Unknown variables stay literal so misconfiguration is visible.
    assert expand_env_vars("${JARVIS_NOPE_NOPE}") == "${JARVIS_NOPE_NOPE}"
    assert expand_env_vars("no placeholders") == "no placeholders"
