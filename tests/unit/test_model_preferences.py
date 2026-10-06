from __future__ import annotations

import pytest

from jarvis.db import get_conn, run_migrations
from jarvis.model_preferences import (
    ModelPreferenceError,
    confirm_preference,
    list_preferences,
    stage_preference,
)


def test_preference_requires_known_workload_and_profile(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "prefs.db"))
    with pytest.raises(ModelPreferenceError, match="unknown workload"):
        stage_preference("missing", "claude-opus", "direct_api")
    with pytest.raises(ModelPreferenceError, match="unknown model profile"):
        stage_preference("developer", "missing", "direct_api")


def test_preference_is_draft_then_confirmed(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "prefs.db"))
    draft = stage_preference("developer", "claude-opus", "direct_api")
    assert draft["draft_id"]
    assert list_preferences() == []
    result = confirm_preference(draft["draft_id"])
    assert result["confirmed"] is True
    assert result["workload"] == "developer"
    assert list_preferences()[0]["route"] == "direct_api"
    with pytest.raises(ModelPreferenceError, match="unknown or already confirmed"):
        confirm_preference(draft["draft_id"])


def test_preference_migrations_apply_to_supplied_connection(tmp_path):
    conn = get_conn(tmp_path / "manual.db")
    run_migrations(conn)
    draft = stage_preference("scheduler", "claude-sonnet-5", "direct_api", conn=conn)
    assert confirm_preference(draft["draft_id"], conn=conn)["confirmed"]
    conn.close()


def test_voice_supervisor_builtin_profile_can_be_confirmed(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "voice-prefs.db"))
    draft = stage_preference(
        "voice_supervisor", "claude-haiku-4-5", "direct_api",
        "approved_external",
    )
    result = confirm_preference(draft["draft_id"])
    assert result["confirmed"] is True


def test_tool_workload_cannot_select_text_only_subscription(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "capability-prefs.db"))
    with pytest.raises(ModelPreferenceError, match="lacks required capabilities"):
        stage_preference("developer", "claude-opus", "subscription")


@pytest.mark.parametrize("workload, configured", [("librarian", "confidential"),
                                                  ("systems", "local_only")])
def test_a_preference_can_never_lower_a_workloads_privacy(tmp_path, monkeypatch, workload, configured):
    # The hole #80 (88b206f) shipped: staging "approved_external" for these
    # workloads was accepted, and confirming it replaced the configured level
    # that the run-log redaction and the delegation status masking read.
    from jarvis.model_routing import resolve_policy

    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "privacy-prefs.db"))
    assert resolve_policy(workload, include_preferences=False).privacy == configured
    for route in ("direct_api", "saygm", "local"):
        with pytest.raises(ModelPreferenceError, match="never lower it"):
            stage_preference(workload, "claude-sonnet-5", route, "approved_external")
    assert list_preferences() == []
    assert resolve_policy(workload).privacy == configured


def test_a_draft_staged_before_the_fix_is_refused_at_confirm(tmp_path, monkeypatch):
    # confirm_preference re-validates, so a lowering draft already in the
    # table (staged by the old code) cannot be confirmed either.
    import uuid
    from datetime import datetime, timedelta, timezone

    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "old-draft.db"))
    conn = get_conn(tmp_path / "old-draft.db")
    run_migrations(conn)
    draft_id = uuid.uuid4().hex[:16]
    now = datetime.now(timezone.utc)
    conn.execute("INSERT INTO model_route_drafts (draft_id, workload, profile, route, privacy, "
                 "created_at, expires_at) VALUES (?, 'librarian', 'claude-sonnet-5', 'direct_api', "
                 "'approved_external', ?, ?)",
                 (draft_id, now.isoformat(), (now + timedelta(minutes=5)).isoformat()))
    conn.commit()
    conn.close()
    with pytest.raises(ModelPreferenceError, match="never lower it"):
        confirm_preference(draft_id)
    assert list_preferences() == []


def test_keeping_or_raising_privacy_is_still_allowed(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "raise.db"))
    # direct_api provides only approved_external, so librarian's kept level
    # needs the local route; analyst may raise its level on the same route.
    kept = stage_preference("librarian", "claude-sonnet-5", "local")
    assert kept["privacy"] == "confidential"
    confirm_preference(kept["draft_id"])
    raised = stage_preference("analyst", "claude-sonnet-5", "local", "local_only")
    assert raised["privacy"] == "local_only"
    confirm_preference(raised["draft_id"])
    assert {(row["workload"], row["privacy"]) for row in list_preferences()} == {
        ("librarian", "confidential"), ("analyst", "local_only")}


def _confidential_catalog():
    from jarvis.saygm import parse_catalog
    return parse_catalog({"data": [{
        "id": "claude-sonnet-5-TEE", "tier": "confidential",
        "api_shapes": ["chat.completions"],
    }]})


def test_confidential_saygm_preference_validates_stage_confirm_and_execution(tmp_path, monkeypatch):
    from jarvis.model_routing import resolve_model_route_checked

    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "confidential-prefs.db"))
    monkeypatch.setenv("SAYGM_API_KEY", "fixture-key")
    monkeypatch.setenv("JARVIS_MODEL_PREFERENCES_ENABLED", "1")
    calls = []

    def fetch(**kwargs):
        calls.append(kwargs)
        return _confidential_catalog()

    monkeypatch.setattr("jarvis.saygm.fetch_catalog", fetch)
    draft = stage_preference("memory", "claude-sonnet-5", "saygm", "confidential")
    assert list_preferences() == []
    confirm_preference(draft["draft_id"])
    resolved = resolve_model_route_checked("memory")
    assert resolved.model == "claude-sonnet-5-TEE"
    assert resolved.route.capabilities == ("text",)
    assert resolved.route.privacy == "confidential"
    assert calls == [{"api_key": "fixture-key", "base_url": "https://api.saygm.com/v1"}] * 3


def test_confidential_preference_rechecks_catalog_when_confirming(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "changed-catalog.db"))
    monkeypatch.setenv("SAYGM_API_KEY", "fixture-key")
    monkeypatch.setattr("jarvis.saygm.fetch_catalog", lambda **_: _confidential_catalog())
    draft = stage_preference("memory", "claude-sonnet-5", "saygm", "confidential")
    monkeypatch.setattr("jarvis.saygm.fetch_catalog", lambda **_: [])
    with pytest.raises(ModelPreferenceError, match="not present"):
        confirm_preference(draft["draft_id"])
    assert list_preferences() == []


def test_confidential_preference_requires_credential_before_catalog(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "no-key.db"))
    monkeypatch.delenv("SAYGM_API_KEY", raising=False)
    def forbidden(**_kwargs):
        raise AssertionError("catalog called without the selected credential")
    monkeypatch.setattr("jarvis.saygm.fetch_catalog", forbidden)
    with pytest.raises(ModelPreferenceError, match="requires SAYGM_API_KEY"):
        stage_preference("memory", "claude-sonnet-5", "saygm", "confidential")
    assert list_preferences() == []


def test_confidential_text_catalog_cannot_stage_tool_workload(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "no-tools.db"))
    monkeypatch.setenv("SAYGM_API_KEY", "fixture-key")
    monkeypatch.setattr("jarvis.saygm.fetch_catalog", lambda **_: _confidential_catalog())
    with pytest.raises(ModelPreferenceError, match="lacks required capabilities: tools"):
        stage_preference("developer", "claude-sonnet-5", "saygm", "confidential")
    assert list_preferences() == []
