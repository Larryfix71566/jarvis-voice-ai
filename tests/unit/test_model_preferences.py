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
