from __future__ import annotations

from scripts.verify_model_access import build_report


def test_access_report_is_secret_free_and_lists_workloads(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "must-not-appear")
    report = build_report()
    rendered = str(report)
    assert "must-not-appear" not in rendered
    assert "developer" in report["workloads"]
    assert report["routes"]["subscription"]["billing"] == "subscription"
    assert report["routes"]["subscription"]["capabilities"] == ["text"]
    assert report["routes"]["subscription"]["api_credentials_stripped_before_launch"] is True


def test_subscription_probe_is_explicit_and_sanitizes_errors(monkeypatch):
    import scripts.verify_model_access as probe
    monkeypatch.setattr(probe, "_run_claude", lambda *args: "MORTIMER_SUBSCRIPTION_PROBE_OK")
    monkeypatch.setattr(probe, "_run_codex", lambda *args: (_ for _ in ()).throw(
        probe.SubscriptionRuntimeError("HTTP 401 revoked token secret-value")))
    report = probe.build_report(probe_subscriptions=True)
    assert report["subscription_probes"]["claude"]["ok"] is True
    assert report["subscription_probes"]["codex"] == {"ok": False, "category": "authentication"}
    assert "secret-value" not in str(report)


def test_subscription_probe_classifies_cli_not_logged_in_as_authentication(monkeypatch):
    import scripts.verify_model_access as probe
    monkeypatch.setattr(
        probe, "_run_claude",
        lambda *args: (_ for _ in ()).throw(
            probe.SubscriptionRuntimeError('{"result":"Not logged in · Please run /login"}')
        ),
    )
    monkeypatch.setattr(probe, "_run_codex", lambda *args: "unused")
    report = probe.build_report(probe_subscriptions=True)
    assert report["subscription_probes"]["claude"] == {
        "ok": False, "category": "authentication"
    }


def test_subscription_probe_classifies_readonly_cli_state_as_environment(monkeypatch):
    import scripts.verify_model_access as probe
    monkeypatch.setattr(probe, "_run_claude", lambda *args: "unused")
    monkeypatch.setattr(
        probe, "_run_codex",
        lambda *args: (_ for _ in ()).throw(
            probe.SubscriptionRuntimeError("failed to open readonly database")
        ),
    )
    report = probe.build_report(probe_subscriptions=True)
    assert report["subscription_probes"]["codex"] == {
        "ok": False, "category": "runtime_environment"
    }


def test_readiness_report_deduplicates_missing_saygm_credential(monkeypatch):
    import scripts.verify_model_access as probe
    report = probe.build_report(check_saygm=False)
    report["routes"]["saygm"]["credential_present"] = False
    report["saygm_catalog"] = {"ok": False, "error": "SAYGM_API_KEY is not set"}
    issues = probe._not_ready(report)
    assert issues.count("saygm: SAYGM_API_KEY is not set") == 1


def test_readiness_report_includes_failed_subscription_probe():
    import scripts.verify_model_access as probe
    report = {
        "routes": {},
        "workloads": {},
        "saygm_catalog": None,
        "subscription_probes": {
            "claude": {"ok": False, "category": "authentication"},
            "codex": {"ok": True},
        },
    }
    assert probe._not_ready(report) == ["claude subscription: authentication"]
