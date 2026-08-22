"""Unit tests for jarvis/config.py (plan Phase 0 Tests)."""

import os

import pytest

from jarvis.config import expand_env_vars, load_settings

REQUIRED = ("OPENAI_API_KEY", "DEEPGRAM_API_KEY", "ELEVENLABS_API_KEY")


@pytest.fixture
def clean_env(monkeypatch, tmp_path):
    """Strip all jarvis-related env vars so tests are hermetic."""
    for name in list(os.environ):
        if name.startswith(("OPENAI", "DEEPGRAM", "ELEVENLABS", "TAVILY", "JARVIS")):
            monkeypatch.delenv(name, raising=False)
    # Re-apply the vault isolation the JARVIS_* sweep above just deleted
    # (conftest.py sets it at collection time): load_settings() now calls
    # jarvis.vault.inject_env() first, and on a dev machine with a REAL
    # data/secrets.vault, an un-isolated call would either decrypt real
    # credentials into these hermetic tests or hard-error (S6) where the
    # keychain is unavailable. A nonexistent path = inject_env no-op.
    monkeypatch.setenv("JARVIS_VAULT_PATH", str(tmp_path / "no-such.vault"))
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


# --- W3 (MORTIMER_WEATHER_FAHRENHEIT_AND_RADAR_PLAN.md) -------------------


def test_units_defaults_to_imperial(clean_env):
    _set_required(clean_env)
    settings = load_settings(env_file=None)
    assert settings.jarvis_units == "imperial"


def test_units_setting_rejects_unknown_values(clean_env):
    _set_required(clean_env)
    clean_env.setenv("JARVIS_UNITS", "furlongs")
    with pytest.raises(RuntimeError, match="JARVIS_UNITS"):
        load_settings(env_file=None)


def test_units_setting_accepts_metric(clean_env):
    _set_required(clean_env)
    clean_env.setenv("JARVIS_UNITS", "metric")
    settings = load_settings(env_file=None)
    assert settings.jarvis_units == "metric"


def test_units_bridged_to_child_env(clean_env):
    """W3: the same transport JARVIS_TIMEZONE already uses to reach MCP
    children — a real env var wins (setdefault precedence), matching every
    other name bridge_settings_to_env carries."""
    from jarvis.config import bridge_settings_to_env

    _set_required(clean_env)
    clean_env.setenv("JARVIS_UNITS", "metric")
    settings = load_settings(env_file=None)

    clean_env.delenv("JARVIS_UNITS", raising=False)
    bridge_settings_to_env(settings)
    assert os.environ["JARVIS_UNITS"] == "metric"


def test_units_bridge_does_not_override_real_env_var(clean_env):
    from jarvis.config import bridge_settings_to_env

    _set_required(clean_env)
    settings = load_settings(env_file=None)  # settings.jarvis_units == imperial

    clean_env.setenv("JARVIS_UNITS", "metric")  # a real override already present
    bridge_settings_to_env(settings)
    assert os.environ["JARVIS_UNITS"] == "metric"  # untouched, not overwritten
