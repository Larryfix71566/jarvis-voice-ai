"""Unit tests for jarvis/keyhealth.py — MORTIMER_KEY_VALIDITY_PLAN.md K4.

The probe is injected, so nothing here touches the network.

The property under test is narrower than "does the probe work": it is that
an ABSENT or INCONCLUSIVE measurement never degrades anything. Two real
events on 2026-08-19 set that bar — a probe using the wrong endpoint
declared a live ANTHROPIC key dead while voice was working on it, and a
funded-then-unfunded OpenRouter key was valid and unusable at the same time.
A red chip that appears because the network hiccuped is as damaging as a
green one over a dead key.
"""

from __future__ import annotations

import pytest

from jarvis import keyhealth

REGISTRY = {
    "profiles": {
        "a": {"name": "a", "api_key_env": "KEY_A",
              "base_url": "https://a.example/v1", "model": "m-a"},
        "b": {"name": "b", "api_key_env": "KEY_A",
              "base_url": "https://a.example/v1", "model": "m-a2"},
        "c": {"name": "c", "api_key_env": "KEY_C",
              "base_url": "https://c.example/v1", "model": "m-c"},
    }
}


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    keyhealth.reset_for_tests()
    monkeypatch.delenv(keyhealth.KILL_SWITCH_ENV, raising=False)
    monkeypatch.setenv("KEY_A", "present")
    monkeypatch.setenv("KEY_C", "present")
    yield
    keyhealth.reset_for_tests()


def _probe(outcomes):
    calls = []

    def fake(base_url, key, model):
        calls.append((base_url, model))
        return outcomes.get(base_url, ("ok", "fine"))

    fake.calls = calls
    return fake


class TestVerdicts:
    def test_a_rejected_key_is_unusable(self):
        probe = _probe({"https://a.example/v1": ("rejected", "HTTP 401")})
        keyhealth.probe_all(REGISTRY, probe=probe)
        assert keyhealth.is_unusable("KEY_A") is True
        assert keyhealth.is_unusable("KEY_C") is False

    def test_an_unfunded_key_is_unusable(self):
        """Valid credential, no balance. Every call fails, so the agent is
        just as broken as with a dead key — but the remedy differs, which is
        why the verdict is kept distinct in the detail string."""
        probe = _probe({"https://a.example/v1": ("unfunded", "HTTP 402")})
        keyhealth.probe_all(REGISTRY, probe=probe)
        assert keyhealth.is_unusable("KEY_A") is True
        assert "402" in keyhealth.detail("KEY_A")

    def test_unreachable_is_never_unusable(self):
        """THE test this module exists for. A blocked network and a dead
        credential call for opposite responses; painting a working agent red
        because the probe could not reach anything is the invent-a-cause
        error AGENT_DISCIPLINE forbids."""
        probe = _probe({"https://a.example/v1": ("unreachable", "DNS")})
        keyhealth.probe_all(REGISTRY, probe=probe)
        assert keyhealth.is_unusable("KEY_A") is False
        assert keyhealth.verdict("KEY_A") == "unreachable"

    def test_unknown_before_any_probe(self):
        assert keyhealth.verdict("KEY_A") == "unknown"
        assert keyhealth.is_unusable("KEY_A") is False


class TestProbeScope:
    def test_one_probe_per_key_not_per_profile(self):
        """Two profiles share KEY_A. The question is whether the CREDENTIAL
        works, and one call answers it for both — a per-profile probe would
        double the startup cost for no additional information."""
        probe = _probe({})
        keyhealth.probe_all(REGISTRY, probe=probe)
        assert len(probe.calls) == 2

    def test_a_missing_key_is_not_probed_or_marked(self, monkeypatch):
        """Absence is already handled by profile resolution and reported by
        check_env; marking it unusable here would double-report it as a
        different kind of problem."""
        monkeypatch.delenv("KEY_C", raising=False)
        probe = _probe({})
        keyhealth.probe_all(REGISTRY, probe=probe)
        assert keyhealth.verdict("KEY_C") == "unknown"

    def test_a_raising_probe_becomes_unreachable_not_unusable(self):
        def boom(base_url, key, model):
            raise RuntimeError("socket exploded")

        keyhealth.probe_all(REGISTRY, probe=boom)
        assert keyhealth.verdict("KEY_A") == "unreachable"
        assert keyhealth.is_unusable("KEY_A") is False


class TestKillSwitch:
    def test_disabled_probes_nothing_and_reports_unknown(self, monkeypatch):
        monkeypatch.setenv(keyhealth.KILL_SWITCH_ENV, "false")
        probe = _probe({"https://a.example/v1": ("rejected", "HTTP 401")})
        keyhealth.probe_all(REGISTRY, probe=probe)
        assert probe.calls == []
        assert keyhealth.is_unusable("KEY_A") is False

    def test_disabled_starts_no_thread(self, monkeypatch):
        monkeypatch.setenv(keyhealth.KILL_SWITCH_ENV, "false")
        assert keyhealth.start_background_probe() is None


class TestNoSecretLeak:
    def test_the_module_never_logs_a_key_value(self):
        source = open(keyhealth.__file__, encoding="utf-8").read()
        # The key is passed to the probe and nowhere else — never formatted
        # into a log line, not even truncated.
        assert "key=%s" in source          # the NAME is logged
        assert "%s\", key" not in source
        assert "key[:" not in source
