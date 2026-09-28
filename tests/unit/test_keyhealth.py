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

import logging

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
        assert keyhealth.detail("KEY_A") == (
            "Provider could not bill the credential")

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
        # The key is passed to the probe and nowhere else — neither the value
        # nor its environment-variable name is formatted into a log line.
        assert "key_health key=%s" not in source
        assert "%s\", key" not in source
        assert "key[:" not in source

    def test_probe_error_and_endpoint_are_not_exposed(
            self, monkeypatch, caplog):
        caplog.set_level(logging.INFO, logger="jarvis.keyhealth")
        key_name = "PRIVATE_KEY_NAME_CANARY"
        monkeypatch.setenv(key_name, "PRIVATE_KEY_VALUE_CANARY")
        endpoint = "https://private-endpoint-canary.invalid/v1"
        exception_text = "PRIVATE_PROVIDER_BODY_CANARY /Users/private/path"
        registry = {
            "profiles": {
                "private": {
                    "api_key_env": key_name,
                    "base_url": endpoint,
                    "model": "private-model",
                }
            }
        }

        def boom(_base_url, _key, _model):
            raise RuntimeError(exception_text)

        keyhealth.probe_all(registry, probe=boom)

        assert keyhealth.verdict(key_name) == "unreachable"
        assert keyhealth.detail(key_name) == _SAFE_DETAIL_UNREACHABLE
        logs = caplog.text
        assert "key_health outcome=unreachable" in logs
        assert key_name not in logs
        assert "PRIVATE_KEY_VALUE_CANARY" not in logs
        assert endpoint not in logs
        assert exception_text not in logs
        assert "/Users/private/path" not in logs
        assert exception_text not in keyhealth.detail(key_name)

    def test_unrecognized_probe_output_is_bounded(self, caplog):
        caplog.set_level(logging.INFO, logger="jarvis.keyhealth")
        hostile_outcome = "PRIVATE_OUTCOME_CANARY"
        keyhealth.probe_all(
            REGISTRY,
            probe=lambda *_args: (hostile_outcome, "PRIVATE_DETAIL_CANARY"),
        )

        assert keyhealth.verdict("KEY_A") == "unknown"
        assert keyhealth.detail("KEY_A") == _SAFE_DETAIL_UNKNOWN
        assert "key_health outcome=unknown" in caplog.text
        assert hostile_outcome not in caplog.text
        assert "PRIVATE_DETAIL_CANARY" not in caplog.text


_SAFE_DETAIL_UNREACHABLE = "Provider could not be reached"
_SAFE_DETAIL_UNKNOWN = "Credential probe was inconclusive"


class TestRefresh:
    """Status spec T3.3 — verdicts used to be measured once, at startup, and
    never again: a key fixed mid-session stayed red until a restart."""

    def test_refresh_loop_is_singleton(self):
        first = keyhealth.start_refresh_loop(interval_s=3600)
        second = keyhealth.start_refresh_loop(interval_s=3600)
        assert first is not None and first is second
        assert first.daemon, "a hung provider must never keep the process alive"
        assert first.name == "key-health-refresh"

    def test_refresh_loop_is_off_with_the_kill_switch(self, monkeypatch):
        monkeypatch.setenv(keyhealth.KILL_SWITCH_ENV, "false")
        assert keyhealth.start_refresh_loop(interval_s=3600) is None

    def test_refresh_loop_runs_refresh_every_interval(self, monkeypatch):
        import threading

        ran = threading.Event()
        monkeypatch.setattr(keyhealth, "refresh_bad_keys", lambda *a, **k: ran.set())
        keyhealth.start_refresh_loop(interval_s=0.01)
        assert ran.wait(2.0)

    def test_refresh_reprobes_only_bad_keys(self, monkeypatch):
        registry = {"profiles": {
            name: {"api_key_env": f"KEY_{name.upper()}",
                   "base_url": f"https://{name}.example/v1", "model": f"m-{name}"}
            for name in ("ok", "rej", "unf", "unr", "unk")
        }}
        for name in ("ok", "rej", "unf", "unr", "unk"):
            monkeypatch.setenv(f"KEY_{name.upper()}", "present")
        first = _probe({
            "https://rej.example/v1": ("rejected", "HTTP 401"),
            "https://unf.example/v1": ("unfunded", "HTTP 402"),
            "https://unr.example/v1": ("unreachable", "timeout"),
        })
        keyhealth.probe_all({"profiles": {k: v for k, v in registry["profiles"].items()
                                          if k != "unk"}}, probe=first)

        second = _probe({"https://unf.example/v1": ("unfunded", "HTTP 402")})
        probed = keyhealth.refresh_bad_keys(registry, probe=second)

        assert sorted(second.calls) == [
            ("https://rej.example/v1", "m-rej"),
            ("https://unf.example/v1", "m-unf"),
            ("https://unr.example/v1", "m-unr"),
        ], "ok and never-probed (unknown) keys are not re-probed"
        assert probed == {"KEY_REJ": "ok", "KEY_UNF": "unfunded", "KEY_UNR": "ok"}
        assert keyhealth.verdict("KEY_REJ") == "ok"
        assert keyhealth.is_unusable("KEY_UNF") is True
        assert keyhealth.verdict("KEY_UNK") == "unknown"

    def test_refresh_redacts_provider_output_and_configuration(self, caplog, monkeypatch):
        caplog.set_level(logging.INFO, logger="jarvis.keyhealth")
        key_name = "PRIVATE_REFRESH_KEY_CANARY"
        endpoint = "https://private-refresh.invalid/v1"
        body = "PRIVATE_REFRESH_BODY_CANARY /private/refresh/path"
        monkeypatch.setenv(key_name, "PRIVATE_REFRESH_VALUE_CANARY")
        registry = {"profiles": {"private": {
            "api_key_env": key_name, "base_url": endpoint, "model": "private-model",
        }}}
        keyhealth.probe_all(registry, probe=lambda *_args: ("rejected", "HTTP 401"))
        caplog.clear()
        result = keyhealth.refresh_bad_keys(
            registry, probe=lambda *_args: (_ for _ in ()).throw(RuntimeError(body)),
        )

        assert result == {key_name: "unreachable"}
        assert keyhealth.detail(key_name) == _SAFE_DETAIL_UNREACHABLE
        for private_value in (key_name, endpoint, body, "PRIVATE_REFRESH_VALUE_CANARY", "/private/refresh/path"):
            assert private_value not in caplog.text

    def test_refresh_with_nothing_bad_makes_no_calls(self):
        keyhealth.probe_all(REGISTRY, probe=_probe({}))
        second = _probe({})
        assert keyhealth.refresh_bad_keys(REGISTRY, probe=second) == {}
        assert second.calls == []

    def test_note_success_recovers_verdict(self):
        keyhealth.probe_all(REGISTRY, probe=_probe(
            {"https://a.example/v1": ("rejected", "HTTP 401")}))
        assert keyhealth.is_unusable("KEY_A") is True
        keyhealth.note_success("KEY_A")
        assert keyhealth.verdict("KEY_A") == "ok"
        assert keyhealth.detail("KEY_A") == "recovered: a call succeeded"
        assert keyhealth.is_unusable("KEY_A") is False

    def test_note_success_leaves_an_ok_verdict_alone(self):
        keyhealth.probe_all(REGISTRY, probe=_probe({}))
        before = keyhealth.detail("KEY_C")
        keyhealth.note_success("KEY_C")
        assert keyhealth.detail("KEY_C") == before

    def test_note_success_respects_the_kill_switch(self, monkeypatch):
        monkeypatch.setenv(keyhealth.KILL_SWITCH_ENV, "false")
        keyhealth.note_success("KEY_A")
        assert keyhealth.verdict("KEY_A") == "unknown"
        keyhealth.note_success("")
