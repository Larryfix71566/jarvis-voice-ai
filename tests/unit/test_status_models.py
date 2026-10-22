"""T2.2 — model_access_status()."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from jarvis import keyhealth
from jarvis.status.models import model_access_status

SECRET = "sk-ant-FIXTURE-KEY-0123456789abcdef"

REGISTRY = {
    "default": "claude-opus",
    "profiles": {
        "claude-opus": {"name": "claude-opus", "provider": "anthropic",
                        "model": "claude-opus-5", "identity": "anthropic/claude-opus-5",
                        "base_url": "https://api.anthropic.com/v1/",
                        "api_key_env": "ANTHROPIC_API_KEY", "tier": "frontier"},
        "or-x": {"name": "or-x", "provider": "openrouter", "model": "x/y",
                 "identity": "x/y", "base_url": "https://openrouter.ai/api/v1",
                 "api_key_env": "OPENROUTER_API_KEY", "tier": "mid"},
        "codex-subscription": {"name": "codex-subscription", "provider": "openai",
                               "model": "gpt-6-astra", "identity": "openai/gpt-6-astra",
                               "tier": "frontier"},
    },
}
ACCESS = {
    "routes": {"codex_subscription": {"adapter": "codex_subscription_runtime"}},
    "workloads": {
        "developer": {"profile": "claude-opus", "route": "direct_api"},
        "noroute": {"profile": "or-x"},
    },
}


@pytest.fixture(autouse=True)
def _reset_keyhealth():
    keyhealth.reset_for_tests()
    yield
    keyhealth.reset_for_tests()


def _status():
    env = {"ANTHROPIC_API_KEY": SECRET, "OPENAI_API_KEY": SECRET,
           "OPENAI_BASE_URL": "https://api.anthropic.com/v1"}
    return model_access_status(registry=REGISTRY, access=ACCESS, env=env)


def test_payload_shape():
    with keyhealth._lock:
        keyhealth._verdicts["ANTHROPIC_API_KEY"] = "ok"
        keyhealth._details["ANTHROPIC_API_KEY"] = "200 from /models"
    payload = _status()
    assert payload["ok"] is True
    assert payload["source"] == "registry"
    assert payload["default"] == "claude-opus"
    assert payload["generated_at"].endswith("+00:00")
    by_name = {p["name"]: p for p in payload["profiles"]}
    assert set(by_name) == {"claude-opus", "or-x", "codex-subscription"}
    opus = by_name["claude-opus"]
    assert set(opus) == {"name", "provider", "model", "identity", "tier", "routes",
                         "key_env", "key_present", "key_health", "key_health_detail"}
    assert opus["key_present"] is True
    assert opus["key_health"] == "ok"
    assert opus["key_health_detail"] == "200 from /models"
    assert opus["routes"] == ["direct_api"]
    assert by_name["or-x"]["key_present"] is False
    assert by_name["or-x"]["key_health"] == "unknown"
    assert payload["workloads"] == {
        "developer": {"profile": "claude-opus", "route": "direct_api"},
        "noroute": {"profile": "or-x", "route": "direct_api"},
    }
    ids = [p["id"] for p in payload["providers"]]
    assert "anthropic" in ids and "voice" in ids and "codex-subscription" in ids
    assert payload["coverage_gaps"] == []
    json.dumps(payload)  # serializable


def test_subscription_profiles_report_na():
    by_name = {p["name"]: p for p in _status()["profiles"]}
    sub = by_name["codex-subscription"]
    assert sub["key_health"] == "n/a (subscription)"
    assert sub["key_health_detail"] == ""
    assert sub["key_env"] is None
    assert sub["key_present"] is False


def test_fixture_key_never_in_payload(caplog):
    caplog.set_level(logging.DEBUG)
    payload = _status()
    assert SECRET not in json.dumps(payload)
    assert all(SECRET not in r.getMessage() for r in caplog.records)


def test_real_config_payload():
    payload = model_access_status(env={})
    assert payload["ok"] is True
    assert payload["coverage_gaps"] == []
    assert payload["profiles"]


def test_sidecar_probes_key_health_at_start():
    """Fact 3.6: the sidecar must hold verdicts of its own."""
    src = (Path(__file__).resolve().parents[2] / "jarvis" / "admin" / "server.py").read_text()
    notifier = src.index("_reminder_notifier.start()")
    probe = src.index("keyhealth.start_background_probe()")
    assert probe > notifier
