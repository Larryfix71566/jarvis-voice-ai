"""Cursor continuity checks for paginated Skills execution traces."""
from __future__ import annotations

from fastapi.testclient import TestClient

from jarvis.admin.server import app
from jarvis.db import get_conn, run_migrations
from jarvis.runlog.store import RunLogger


def test_event_cursor_pages_are_complete_stable_and_replayable(tmp_path, monkeypatch):
    db_path = tmp_path / "events.db"
    logs = tmp_path / "logs"
    conn = get_conn(db_path)
    run_migrations(conn)
    conn.close()

    logger = RunLogger(
        "cursor-run", "developer", "Developer", "private task",
        db_path=db_path, root=logs,
    )
    logger.user_id = "local"
    logger.start()
    logger.skill_event("sample-skill", "a" * 64, "skill_selected")
    logger.skill_event(
        "sample-skill", "a" * 64, "skill_step_started", step_id="step-one",
        status="running",
    )
    logger.skill_event(
        "sample-skill", "a" * 64, "skill_step_finished", step_id="step-one",
        status="unknown", evidence_refs=[{"kind": "tool_call_id", "id": "tool-1"}],
    )
    logger.finish("private response")

    monkeypatch.setenv("JARVIS_DB_PATH", str(db_path))
    monkeypatch.setenv("JARVIS_USER_ID", "local")
    client = TestClient(app)

    first = client.get(
        "/api/skills/runs/cursor-run/events", params={"limit": 2},
    )
    assert first.status_code == 200
    page_one = first.json()
    assert page_one["has_more"] is True
    assert len(page_one["events"]) == 2

    cursor = page_one["next_after_seq"]
    second = client.get(
        "/api/skills/runs/cursor-run/events",
        params={"after_seq": cursor, "limit": 2},
    )
    assert second.status_code == 200
    page_two = second.json()
    assert page_two["has_more"] is False
    assert page_two["after_seq"] == cursor
    assert page_two["events"]

    # Retrying a cursor after reconnect is a read replay: it returns the same
    # events and does not mutate or advance server-side trace state.
    replay = client.get(
        "/api/skills/runs/cursor-run/events",
        params={"after_seq": cursor, "limit": 2},
    )
    assert replay.json() == page_two

    all_events = page_one["events"] + page_two["events"]
    assert [event["seq"] for event in all_events] == sorted(
        {event["seq"] for event in all_events}
    )
    assert all_events[-1]["seq"] == page_two["next_after_seq"]
    assert "private task" not in first.text + second.text
    assert "private response" not in first.text + second.text
