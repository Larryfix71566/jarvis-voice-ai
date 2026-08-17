"""Unit tests for jarvis/db.py (plan Phase 0 Tests)."""

import sqlite3

from jarvis.db import get_conn, now_iso, run_migrations

EXPECTED_TABLES = {
    "migrations", "notes", "reminders", "conversations", "actions", "memories",
    "observations", "conversations_fts", "agent_runs", "agent_events",
    "procedures", "procedures_fts", "council_rounds", "council_scores",
}

EXPECTED_MIGRATION_IDS = [
    "0001_init", "0002_actions", "0003_memory", "0004_observations",
    "0005_conversation_search", "0006_agent_runs", "0007_procedures",
    "0008_tool_outcomes", "0009_council", "0010_council_v2",
    "0011_run_model",
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


def test_migration_0008_columns_and_defaults(tmp_path):
    """MORTIMER_AGENT_TRUST_PLAN.md D24 — new columns exist with the
    documented (non-fabricated) defaults."""
    conn = get_conn(tmp_path / "cols.db")
    run_migrations(conn)
    run_cols = {row["name"]: row for row in conn.execute("PRAGMA table_info(agent_runs)")}
    assert "tools_ok" in run_cols
    assert "tools_failed" in run_cols

    proc_cols = {row["name"]: row for row in conn.execute("PRAGMA table_info(procedures)")}
    assert "task_tokens" in proc_cols

    conn.execute(
        "INSERT INTO agent_runs (run_id, agent, task, status, started_at) "
        "VALUES ('r1', 'developer', 't', 'ok', '2026-01-01T00:00:00+00:00')"
    )
    row = conn.execute(
        "SELECT tools_ok, tools_failed FROM agent_runs WHERE run_id='r1'"
    ).fetchone()
    # NULL, not 0 — a pre-migration-style row cannot distinguish ok from
    # failed calls, and defaulting to 0 would assert something unsupported.
    assert row["tools_ok"] is None
    assert row["tools_failed"] is None

    conn.execute(
        "INSERT INTO procedures (agent, label, description, created_at, updated_at) "
        "VALUES ('developer', 'x', 'y', '2026-01-01T00:00:00+00:00', "
        "'2026-01-01T00:00:00+00:00')"
    )
    prow = conn.execute("SELECT task_tokens FROM procedures WHERE label='x'").fetchone()
    assert prow["task_tokens"] == ""
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


def test_migration_0009_council_columns_and_defaults(tmp_path):
    """MORTIMER_LLM_COUNCIL_PLAN.md D8 — tables exist with the documented
    columns, and council_scores.shadow (D8.2) defaults to 0 (live), never
    NULL, since every read path branches on it directly."""
    conn = get_conn(tmp_path / "council.db")
    run_migrations(conn)

    round_cols = {row["name"] for row in conn.execute("PRAGMA table_info(council_rounds)")}
    assert {
        "round_id", "run_id", "workflow", "placement", "trigger", "tier",
        "goal", "proposer_count", "judge_count", "abstentions",
        "winner_profile", "winner_label", "winner_mean", "select_reason",
        "retry_validated", "status", "started_at", "ended_at", "latency_ms",
    } <= round_cols

    score_cols = {row["name"] for row in conn.execute("PRAGMA table_info(council_scores)")}
    assert {
        "round_id", "judge_profile", "judge_tier", "shadow",
        "proposal_label", "proposal_profile", "score", "abstain_reason",
        "justification", "created_at",
    } <= score_cols

    conn.execute(
        "INSERT INTO council_rounds (round_id, workflow, placement, trigger, "
        "tier, goal, proposer_count, judge_count, status, started_at) "
        "VALUES ('r1', 'selfedit', 'planner', 'E1', 1, 'g', 2, 1, 'running', "
        "'2026-01-01T00:00:00+00:00')"
    )
    conn.execute(
        "INSERT INTO council_scores (round_id, judge_profile, judge_tier, "
        "proposal_label, proposal_profile, score, justification, created_at) "
        "VALUES ('r1', 'kimi-k3', 'mid', 'Proposal A', 'kimi-k2', 7.5, 'ok', "
        "'2026-01-01T00:00:00+00:00')"
    )
    row = conn.execute(
        "SELECT shadow FROM council_scores WHERE round_id='r1'"
    ).fetchone()
    assert row["shadow"] == 0

    indexes = {
        row["name"]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")
    }
    assert "idx_council_rounds_run" in indexes
    assert "idx_council_scores_round" in indexes
    assert "idx_council_scores_shadow" in indexes
    conn.close()


def test_migration_0010_council_v2_columns_and_defaults(tmp_path):
    """MORTIMER_LLM_COUNCIL_V2_PLAN.md V9/V13 — new columns exist and
    default to NULL (unknown), never 0/empty, same discipline as
    MIGRATION_0008."""
    conn = get_conn(tmp_path / "council_v2.db")
    run_migrations(conn)

    round_cols = {row["name"] for row in conn.execute("PRAGMA table_info(council_rounds)")}
    assert {"prompt_tokens", "completion_tokens", "registry_order"} <= round_cols

    conn.execute(
        "INSERT INTO council_rounds (round_id, workflow, placement, trigger, "
        "tier, goal, proposer_count, judge_count, status, started_at) "
        "VALUES ('r1', 'selfedit', 'planner', 'E1', 1, 'g', 2, 1, 'running', "
        "'2026-01-01T00:00:00+00:00')"
    )
    row = conn.execute(
        "SELECT prompt_tokens, completion_tokens, registry_order "
        "FROM council_rounds WHERE round_id='r1'"
    ).fetchone()
    assert row["prompt_tokens"] is None
    assert row["completion_tokens"] is None
    assert row["registry_order"] is None
    conn.close()


def test_migration_0011_run_model_column_and_default(tmp_path):
    """MORTIMER_PLANNING_PATHWAY_PLAN.md P3 — `model` exists on agent_runs
    and defaults to NULL (unknown), never an empty string, same discipline
    as MIGRATION_0008's tools_ok/tools_failed."""
    conn = get_conn(tmp_path / "run_model.db")
    run_migrations(conn)

    cols = {row["name"] for row in conn.execute("PRAGMA table_info(agent_runs)")}
    assert "model" in cols

    conn.execute(
        "INSERT INTO agent_runs (run_id, agent, display_name, task, status, "
        "started_at, tool_count) VALUES ('r1', 'developer', 'Developer', "
        "'t', 'running', '2026-01-01T00:00:00+00:00', 0)"
    )
    row = conn.execute("SELECT model FROM agent_runs WHERE run_id='r1'").fetchone()
    assert row["model"] is None
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


def test_migration_0010_applies_over_existing_0009_db(tmp_path):
    """§6 verification item 3 (V2 plan) — 0010 must apply cleanly to a DB
    that already has 0009 (the upgrade path), not just to a fresh DB."""
    db_path = tmp_path / "upgrade.db"
    conn = get_conn(db_path)
    # Simulate a pre-v2 install: apply everything through 0009 only.
    from jarvis.db import MIGRATIONS, now_iso as _now_iso

    conn.execute(
        "CREATE TABLE IF NOT EXISTS migrations "
        "(id TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    for migration_id, sql in MIGRATIONS:
        if migration_id == "0010_council_v2":
            break
        conn.executescript(sql)
        conn.execute(
            "INSERT INTO migrations (id, applied_at) VALUES (?, ?)",
            (migration_id, _now_iso()),
        )
    conn.commit()
    conn.execute(
        "INSERT INTO council_rounds (round_id, workflow, placement, trigger, "
        "tier, goal, proposer_count, judge_count, status, started_at) "
        "VALUES ('pre-v2', 'selfedit', 'planner', 'E1', 1, 'g', 2, 1, 'ok', "
        "'2026-01-01T00:00:00+00:00')"
    )
    conn.commit()

    newly = run_migrations(conn)
    # 0011_run_model also applies in this same upgrade run — it comes
    # after 0010_council_v2 in MIGRATIONS and was equally absent from
    # this pre-v2 DB.
    assert newly == ["0010_council_v2", "0011_run_model"]
    row = conn.execute(
        "SELECT prompt_tokens, completion_tokens, registry_order "
        "FROM council_rounds WHERE round_id='pre-v2'"
    ).fetchone()
    assert row["prompt_tokens"] is None  # pre-v2 row: NULL, not backfilled
    conn.close()


def test_now_iso_is_utc_isoformat():
    stamp = now_iso()
    assert stamp.endswith("+00:00")
    assert "T" in stamp
