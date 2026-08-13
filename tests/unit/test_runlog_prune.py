"""Unit tests for jarvis/runlog/prune.py (run-logging plan §7)."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from jarvis.db import get_conn, run_migrations
from jarvis.runlog.prune import prune
from jarvis.runlog.store import RUNLOG_DIR


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "prune.db"
    conn = get_conn(path)
    run_migrations(conn)
    conn.close()
    return path


def insert_run(db_path, run_id: str, started_at: str) -> None:
    conn = get_conn(db_path)
    conn.execute(
        "INSERT INTO agent_runs (run_id, agent, display_name, task, "
        "status, started_at) VALUES (?, 'developer', 'Developer', 't', "
        "'ok', ?)",
        (run_id, started_at),
    )
    conn.execute(
        "INSERT INTO agent_events (run_id, seq, type, created_at) "
        "VALUES (?, 0, 'tool_call', ?)",
        (run_id, started_at),
    )
    conn.commit()
    conn.close()


def iso_days_ago(n: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=n)).isoformat()


class TestRowPruning:
    def test_old_rows_removed_recent_rows_kept(self, db_path):
        insert_run(db_path, "old", iso_days_ago(40))
        insert_run(db_path, "recent", iso_days_ago(1))

        result = prune(30, db_path=db_path)
        assert result["runs_deleted"] == 1

        conn = get_conn(db_path)
        conn.row_factory = sqlite3.Row
        remaining_runs = {r["run_id"] for r in conn.execute("SELECT run_id FROM agent_runs")}
        remaining_events = {r["run_id"] for r in conn.execute("SELECT run_id FROM agent_events")}
        conn.close()
        assert remaining_runs == {"recent"}
        assert remaining_events == {"recent"}

    def test_retention_zero_disables_pruning(self, db_path):
        insert_run(db_path, "old", iso_days_ago(400))
        result = prune(0, db_path=db_path)
        assert result == {"runs_deleted": 0, "dirs_deleted": 0}
        conn = get_conn(db_path)
        count = conn.execute("SELECT COUNT(*) FROM agent_runs").fetchone()[0]
        conn.close()
        assert count == 1

    def test_negative_retention_disables_pruning(self, db_path):
        insert_run(db_path, "old", iso_days_ago(400))
        result = prune(-5, db_path=db_path)
        assert result == {"runs_deleted": 0, "dirs_deleted": 0}


class TestDirPruning:
    def test_old_directories_removed_recent_kept(self, db_path, tmp_path):
        root = tmp_path / "root"
        old_dir = root / RUNLOG_DIR / (datetime.now(timezone.utc) - timedelta(days=40)).strftime("%Y-%m-%d")
        recent_dir = root / RUNLOG_DIR / (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
        old_dir.mkdir(parents=True)
        recent_dir.mkdir(parents=True)
        (old_dir / "r.jsonl").write_text("{}")
        (recent_dir / "r.jsonl").write_text("{}")

        result = prune(30, db_path=db_path, root=root)
        assert result["dirs_deleted"] == 1
        assert not old_dir.exists()
        assert recent_dir.exists()

    def test_missing_base_dir_does_not_raise(self, db_path, tmp_path):
        result = prune(30, db_path=db_path, root=tmp_path / "nope")
        assert result["dirs_deleted"] == 0
