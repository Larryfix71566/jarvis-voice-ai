"""Unit tests for jarvis/council/prune.py (MORTIMER_LLM_COUNCIL_V2_PLAN.md
V11), a structural copy of tests/unit/test_runlog_prune.py."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from jarvis.council.council import COUNCIL_LOG_DIR
from jarvis.council.prune import prune
from jarvis.db import get_conn, run_migrations


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "prune.db"
    conn = get_conn(path)
    run_migrations(conn)
    conn.close()
    return path


def insert_round(db_path, round_id: str, started_at: str) -> None:
    conn = get_conn(db_path)
    conn.execute(
        "INSERT INTO council_rounds (round_id, workflow, placement, trigger, "
        "tier, goal, proposer_count, judge_count, status, started_at) "
        "VALUES (?, 'selfedit', 'planner', 'E1', 1, 'g', 2, 1, 'ok', ?)",
        (round_id, started_at),
    )
    conn.execute(
        "INSERT INTO council_scores (round_id, judge_profile, judge_tier, "
        "proposal_label, proposal_profile, score, created_at) "
        "VALUES (?, 'kimi-k3', 'mid', 'Proposal A', 'kimi-k2', 7.5, ?)",
        (round_id, started_at),
    )
    conn.commit()
    conn.close()


def iso_days_ago(n: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=n)).isoformat()


class TestRowPruning:
    def test_old_rows_removed_recent_rows_kept(self, db_path):
        insert_round(db_path, "old", iso_days_ago(200))
        insert_round(db_path, "recent", iso_days_ago(1))

        result = prune(180, db_path=db_path)
        assert result["rounds_deleted"] == 1

        conn = get_conn(db_path)
        conn.row_factory = sqlite3.Row
        remaining_rounds = {
            r["round_id"] for r in conn.execute("SELECT round_id FROM council_rounds")
        }
        remaining_scores = {
            r["round_id"] for r in conn.execute("SELECT round_id FROM council_scores")
        }
        conn.close()
        assert remaining_rounds == {"recent"}
        assert remaining_scores == {"recent"}

    def test_retention_zero_disables_pruning(self, db_path):
        insert_round(db_path, "old", iso_days_ago(400))
        result = prune(0, db_path=db_path)
        assert result == {"rounds_deleted": 0, "dirs_deleted": 0}
        conn = get_conn(db_path)
        count = conn.execute("SELECT COUNT(*) FROM council_rounds").fetchone()[0]
        conn.close()
        assert count == 1

    def test_negative_retention_disables_pruning(self, db_path):
        insert_round(db_path, "old", iso_days_ago(400))
        result = prune(-5, db_path=db_path)
        assert result == {"rounds_deleted": 0, "dirs_deleted": 0}


class TestDirPruning:
    def test_old_directories_removed_recent_kept(self, db_path, tmp_path):
        root = tmp_path / "root"
        old_dir = root / COUNCIL_LOG_DIR / (
            datetime.now(timezone.utc) - timedelta(days=200)
        ).strftime("%Y-%m-%d")
        recent_dir = root / COUNCIL_LOG_DIR / (
            datetime.now(timezone.utc) - timedelta(days=1)
        ).strftime("%Y-%m-%d")
        old_dir.mkdir(parents=True)
        recent_dir.mkdir(parents=True)
        (old_dir / "r.jsonl").write_text("{}")
        (recent_dir / "r.jsonl").write_text("{}")

        result = prune(180, db_path=db_path, root=root)
        assert result["dirs_deleted"] == 1
        assert not old_dir.exists()
        assert recent_dir.exists()

    def test_missing_base_dir_does_not_raise(self, db_path, tmp_path):
        result = prune(180, db_path=db_path, root=tmp_path / "nope")
        assert result["dirs_deleted"] == 0


class TestStartupWiring:
    """The defect the other tests in this file could not catch.

    They import `prune` directly, which proves the function works; production
    reaches it through jarvis/bot/pipeline.py, and THAT is what broke. These
    pin the caller's binding instead."""

    def test_pipeline_binds_the_prune_function_not_the_module(self):
        import types

        from jarvis.bot import pipeline

        assert not isinstance(pipeline.prune_council, types.ModuleType), (
            "pipeline.prune_council is the jarvis.council.prune MODULE — calling "
            "it raises \"'module' object is not callable\" and council retention "
            "pruning silently never runs (2026-09-07)"
        )
        assert callable(pipeline.prune_council)

    def test_both_startup_pruners_are_callable(self):
        """Symmetry guard: runlog resolves via a package re-export and council
        via the submodule, so a future refactor of either __init__ must keep
        both callable."""
        from jarvis.bot import pipeline

        assert callable(pipeline.prune_council)
        assert callable(pipeline.prune_runlog)
