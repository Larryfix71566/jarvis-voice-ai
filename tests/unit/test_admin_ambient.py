"""Unit tests for the admin sidecar's /api/ambient endpoint
(MORTIMER_ENGAGEMENT_DESIGN_PLAN.md E4). Same DB-isolation pattern as
test_admin_council.py."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from jarvis.admin.server import app
from jarvis.db import get_conn, run_migrations


@pytest.fixture(autouse=True)
def _db(tmp_path, monkeypatch):
    db_path = tmp_path / "ambient_test.db"
    monkeypatch.setenv("JARVIS_DB_PATH", str(db_path))
    conn = get_conn(db_path)
    run_migrations(conn)
    conn.close()
    return db_path


def _insert_reminder(db_path, message, due_at, status="pending"):
    conn = get_conn(db_path)
    conn.execute(
        "INSERT INTO reminders (message, due_at, status, delivered, created_at) "
        "VALUES (?, ?, ?, 0, ?)",
        (message, due_at, status, due_at),
    )
    conn.commit()
    conn.close()


def test_empty_state_nulls(_db):
    res = TestClient(app).get("/api/ambient").json()
    assert res["ok"] is True
    assert res["reminder"] is None
    assert res["summary"] is None


def test_next_reminder_is_earliest_pending(_db):
    _insert_reminder(_db, "later thing", "2026-09-02T09:00:00")
    _insert_reminder(_db, "sooner thing", "2026-09-01T09:00:00")
    _insert_reminder(_db, "done thing", "2026-08-01T09:00:00", status="done")
    res = TestClient(app).get("/api/ambient").json()
    assert res["reminder"] == {
        "text": "sooner thing", "due_at": "2026-09-01T09:00:00",
    }


def test_summary_passthrough(_db, monkeypatch):
    import jarvis.admin.server as srv

    monkeypatch.setattr(
        srv.memory_module, "get_summary_text", lambda: "Larry shipped the vault."
    )
    res = TestClient(app).get("/api/ambient").json()
    assert res["summary"] == "Larry shipped the vault."
