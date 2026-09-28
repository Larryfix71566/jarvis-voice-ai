"""Skills activity API is bounded, user-scoped, and content-free."""
from __future__ import annotations

import base64
import json

from fastapi.testclient import TestClient

from jarvis import auth
from jarvis.admin.server import app
from jarvis.db import get_conn, now_iso, run_migrations
from jarvis.runlog.store import RunLogger


def _seed_run(db_path, root, *, user_id="local", sensitive=False):
    conn = get_conn(db_path)
    run_migrations(conn)
    conn.close()
    logger = RunLogger(
        "skill-run-1", "developer", "Developer", "private task text",
        db_path=db_path, root=root, sensitive=sensitive,
    )
    logger.user_id = user_id
    logger.start()
    logger.skill_event(
        "technical-plan-document", "a" * 64, "skill_selected",
        request_id="request-1",
    )
    logger.finish("private response text")


def test_skill_activity_endpoints_return_run_cards_and_typed_events(
    tmp_path, monkeypatch,
):
    db_path = tmp_path / "events.db"
    _seed_run(db_path, tmp_path / "logs")
    monkeypatch.setenv("JARVIS_DB_PATH", str(db_path))
    monkeypatch.setenv("JARVIS_USER_ID", "local")
    client = TestClient(app)

    runs = client.get("/api/skills/technical-plan-document/runs")
    assert runs.status_code == 200
    data = runs.json()
    assert data["schema_version"] == 1
    assert data["runs"][0]["run_id"] == "skill-run-1"
    assert "task" not in data["runs"][0]
    assert "private task text" not in runs.text

    events = client.get("/api/skills/runs/skill-run-1/events")
    assert events.status_code == 200
    body = events.json()
    assert body["trace_status"] == "recorded"
    assert body["events"][0]["type"] == "skill_selected"
    assert body["events"][0]["skill_id"] == "technical-plan-document"
    assert "private response text" not in events.text


def test_legacy_run_without_skill_events_is_explicitly_unavailable(
    tmp_path, monkeypatch,
):
    """A pre-instrumentation run must not acquire an invented skill trace."""
    db_path = tmp_path / "legacy-events.db"
    conn = get_conn(db_path)
    run_migrations(conn)
    conn.close()

    logger = RunLogger(
        "legacy-run", "developer", "Developer", "legacy private task",
        db_path=db_path, root=tmp_path / "logs",
    )
    logger.user_id = "local"
    logger.start()
    logger.finish("legacy private reply")

    with get_conn(db_path) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM skill_events WHERE user_id=? AND run_id=?",
            ("local", "legacy-run"),
        ).fetchone()[0] == 0

    monkeypatch.setenv("JARVIS_DB_PATH", str(db_path))
    monkeypatch.setenv("JARVIS_USER_ID", "local")
    response = TestClient(app).get("/api/skills/runs/legacy-run/events")

    assert response.status_code == 200
    assert response.json()["trace_status"] == "unavailable"
    assert response.json()["events"] == []
    assert response.json()["next_after_seq"] == 0
    assert "legacy private task" not in response.text
    assert "legacy private reply" not in response.text


def test_skill_activity_endpoints_enforce_user_ownership_and_bounds(
    tmp_path, monkeypatch,
):
    db_path = tmp_path / "events.db"
    _seed_run(db_path, tmp_path / "logs", user_id="owner")
    monkeypatch.setenv("JARVIS_DB_PATH", str(db_path))
    monkeypatch.setenv("JARVIS_USER_ID", "other")
    client = TestClient(app)

    assert client.get("/api/skills/runs/skill-run-1/events").status_code == 404
    assert client.get(
        "/api/skills/technical-plan-document/runs",
    ).json()["runs"] == []
    assert client.get(
        "/api/skills/runs/skill-run-1/events", params={"after_seq": -1},
    ).status_code == 400
    assert client.get(
        "/api/skills/technical-plan-document/runs", params={"limit": 101},
    ).status_code == 400


def test_skill_run_cursor_tie_boundary_is_complete_and_rejects_malformed_positions(
    tmp_path, monkeypatch,
):
    db_path = tmp_path / "events.db"
    logs = tmp_path / "logs"
    conn = get_conn(db_path)
    run_migrations(conn)
    conn.close()
    for run_id in ("run-a", "run-b", "run-c"):
        logger = RunLogger(
            run_id, "developer", "Developer", "private task",
            db_path=db_path, root=logs,
        )
        logger.user_id = "local"
        logger.start()
        logger.skill_event("technical-plan-document", "a" * 64, "skill_selected")
        logger.finish("private response")
    # Force the exact timestamp tie that exercises the secondary run_id key.
    with get_conn(db_path) as conn:
        conn.execute(
            "UPDATE agent_runs SET started_at=? WHERE user_id=?",
            ("2026-09-28T12:00:00+00:00", "local"),
        )
        conn.commit()

    monkeypatch.setenv("JARVIS_DB_PATH", str(db_path))
    monkeypatch.setenv("JARVIS_USER_ID", "local")
    client = TestClient(app)
    collected = []
    cursor = ""
    while True:
        response = client.get(
            "/api/skills/technical-plan-document/runs",
            params={"cursor": cursor, "limit": 1},
        )
        assert response.status_code == 200
        page = response.json()
        collected.extend(item["run_id"] for item in page["runs"])
        cursor = page["next_cursor"]
        if cursor is None:
            break

    assert collected == ["run-c", "run-b", "run-a"]

    # This is valid base64 and JSON but not a cursor the server could issue.
    malformed = base64.urlsafe_b64encode(
        json.dumps(["not-a-time", "run-a"]).encode(),
    ).decode().rstrip("=")
    response = client.get(
        "/api/skills/technical-plan-document/runs",
        params={"cursor": malformed},
    )
    assert response.status_code == 400


def test_protected_skill_activity_is_generic_at_api_boundary(tmp_path, monkeypatch):
    db_path = tmp_path / "events.db"
    _seed_run(db_path, tmp_path / "logs", sensitive=True)
    monkeypatch.setenv("JARVIS_DB_PATH", str(db_path))
    monkeypatch.setenv("JARVIS_USER_ID", "local")
    response = TestClient(app).get("/api/skills/runs/skill-run-1/events")
    assert response.status_code == 200
    assert "technical-plan-document" not in response.text
    event = response.json()["events"][0]
    assert event["type"] == "protected_activity"
    assert event["skill_id"] is None
    assert event["skill_revision"] is None


def test_mixed_legacy_trace_fails_closed_when_protected_marker_exists(
    tmp_path, monkeypatch,
):
    """A stale ordinary row must not bypass run-wide protected status."""
    db_path = tmp_path / "events.db"
    _seed_run(db_path, tmp_path / "logs")
    with get_conn(db_path) as conn:
        conn.execute(
            "INSERT INTO skill_events (user_id, run_id, request_id, event_id, seq, "
            "schema_version, occurred_at, type, status, evidence_refs) "
            "VALUES (?, ?, ?, ?, ?, 1, ?, 'protected_activity', 'unknown', '[]')",
            ("local", "skill-run-1", "skill-run-1", "protected-marker", 2, now_iso()),
        )
        conn.commit()
    monkeypatch.setenv("JARVIS_DB_PATH", str(db_path))
    monkeypatch.setenv("JARVIS_USER_ID", "local")
    client = TestClient(app)

    runs = client.get("/api/skills/technical-plan-document/runs")
    assert runs.status_code == 200
    assert runs.json()["runs"] == []
    events = client.get("/api/skills/runs/skill-run-1/events")
    assert events.status_code == 200
    assert "technical-plan-document" not in events.text
    assert "a" * 64 not in events.text
    assert len(events.json()["events"]) == 1
    assert events.json()["events"][0] == {
        "event_id": "protected-marker", "run_id": "skill-run-1",
        "request_id": "skill-run-1", "seq": 2, "schema_version": 1,
        "occurred_at": events.json()["events"][0]["occurred_at"],
        "skill_id": None, "skill_revision": None, "step_id": None,
        "attempt_id": None, "type": "protected_activity",
        "status": "unknown", "evidence_refs": [],
    }


def test_authenticated_activity_reads_use_bearer_owner_not_process_tenant(
    tmp_path, monkeypatch,
):
    db_path = tmp_path / "events.db"
    _seed_run(db_path, tmp_path / "logs", user_id="token-owner")
    monkeypatch.setenv("JARVIS_DB_PATH", str(db_path))
    monkeypatch.setenv("JARVIS_AUTH_ENABLED", "true")
    # Deliberately disagree with the authenticated principal. This is a
    # process-wide setting and must not select a different user's run rows.
    monkeypatch.setenv("JARVIS_USER_ID", "process-owner")
    token = auth.mint_token()
    with get_conn(db_path) as conn:
        conn.execute(
            "INSERT INTO client_tokens (user_id, name, token_hash, created_at) "
            "VALUES (?, ?, ?, ?)",
            ("token-owner", "skills-test", auth.hash_token(token), now_iso()),
        )
        conn.commit()

    client = TestClient(app)
    headers = {"Authorization": f"Bearer {token}"}
    runs = client.get(
        "/api/skills/technical-plan-document/runs", headers=headers,
    )
    assert runs.status_code == 200
    assert [row["run_id"] for row in runs.json()["runs"]] == ["skill-run-1"]
    events = client.get(
        "/api/skills/runs/skill-run-1/events", headers=headers,
    )
    assert events.status_code == 200
    assert events.json()["events"][0]["type"] == "skill_selected"
