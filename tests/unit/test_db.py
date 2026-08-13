"""Unit tests for jarvis/db.py (plan Phase 0 Tests)."""

import sqlite3

from jarvis.db import get_conn, now_iso, run_migrations

EXPECTED_TABLES = {
    "migrations", "notes", "reminders", "conversations", "actions", "memories",
    "observations", "conversations_fts", "agent_runs", "agent_events",
}

EXPECTED_MIGRATION_IDS = [
    "0001_init", "0002_actions", "0003_memory", "0004_observations",
    "0005_conversation_search", "0006_agent_runs",
]


def _table_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {row["name"] for row in rows}


def test_migrations_apply_cleanly_to_fresh_db(tmp_path):
    conn = get_conn(tmp_path / "fresh.db")
    newly = run_migrations(conn)
    assert newly == EXPECTED_MIGRATION_IDS
    assert EXPECTED_TABLES <= _table_names(conn)
    conn.close()


def test_migrations_are_idempotent(tmp_path):
    conn = get_conn(tmp_path / "twice.db")
    first = run_migrations(conn)
    second = run_migrations(conn)
    assert first == EXPECTED_MIGRATION_IDS
    assert second == []
    # Still exactly one recorded migration row per migration.
    rows = conn.execute("SELECT id FROM migrations").fetchall()
    assert [row["id"] for row in rows] == EXPECTED_MIGRATION_IDS
    conn.close()


def test_expected_indexes_exist(tmp_path):
    conn = get_conn(tmp_path / "idx.db")
    run_migrations(conn)
    indexes = {
        row["name"]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")
    }
    assert "idx_reminders_due" in indexes
    assert "idx_notes_tags" in indexes
    assert "idx_memories_fact_key" in indexes
    assert "idx_observations_key" in indexes
    conn.close()


def test_row_factory_and_wal(tmp_path):
    conn = get_conn(tmp_path / "wal.db")
    run_migrations(conn)
    conn.execute(
        "INSERT INTO notes (title, body, tags, created_at, updated_at) "
        "VALUES ('t', 'b', '', '2026-01-01', '2026-01-01')"
    )
    row = conn.execute("SELECT title FROM notes").fetchone()
    assert isinstance(row, sqlite3.Row)
    assert row["title"] == "t"
    assert conn.execute("PRAGMA journal_mode;").fetchone()[0] == "wal"
    conn.close()


def test_now_iso_is_utc_isoformat():
    stamp = now_iso()
    assert stamp.endswith("+00:00")
    assert "T" in stamp
