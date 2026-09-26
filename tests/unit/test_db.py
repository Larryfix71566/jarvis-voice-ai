"""Unit tests for jarvis/db.py (plan Phase 0 Tests)."""

import sqlite3

import pytest

from jarvis.db import MIGRATION_0020_user_id, MIGRATIONS, get_conn, now_iso, run_migrations

EXPECTED_TABLES = {
    "migrations", "notes", "reminders", "conversations", "actions", "memories",
    "observations", "conversations_fts", "agent_runs", "agent_events",
    "procedures", "procedures_fts", "council_rounds", "council_scores",
    "memory_reviews", "memory_extraction_cursor", "memory_extraction_pending",
    "memory_classification_shadow",
    "model_route_preferences", "model_route_drafts",
    "notices",
}

EXPECTED_MIGRATION_IDS = [
    "0001_init", "0002_actions", "0003_memory", "0004_observations",
    "0005_conversation_search", "0006_agent_runs", "0007_procedures",
    "0008_tool_outcomes", "0009_council", "0010_council_v2",
    "0011_run_model",
    "0012_memory_tiers",
    "0013_memory_archive",
    "0014_council_attempted",
    "0015_memory_reviews",
    "0016_memory_extraction_v2",
    "0017_memory_extraction_pending",
    "0018_council_retry_outcome",
    "0019_memory_recall_events",
    "0020_user_id",
    "0021_reminders_notified",
    "0022_memory_automation",
    "0023_memory_classification_shadow",
    "0024_model_route_preferences",
    "0025_notices",
    "0026_expire_retired_actions",
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
    # Every migration after 0010 applies in this same upgrade run — they
    # come later in MIGRATIONS and were equally absent from this pre-v2
    # DB. Asserted as a prefix + membership rather than a frozen list so
    # adding a migration doesn't falsely fail this upgrade-path test.
    assert newly[0] == "0010_council_v2"
    assert "0011_run_model" in newly
    assert "0012_memory_tiers" in newly
    assert "0013_memory_archive" in newly
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


def test_migration_0020_user_id_everywhere(tmp_path):
    """GC8 (gap-closure plan, 2026-09-04): every table except migrations,
    sqlite_* and *_fts* gains user_id TEXT NOT NULL DEFAULT 'local'. Same
    exclusions as tests/unit/test_tenant_columns.py's generic walk; this one
    additionally pins the 15-table list the migration names explicitly."""
    expected_tables = {
        "notes", "reminders", "conversations", "actions", "memories",
        "observations", "agent_runs", "agent_events", "procedures",
        "council_rounds", "council_scores", "memory_reviews",
        "memory_extraction_cursor", "memory_extraction_pending",
        "memory_recall_events",
    }
    conn = get_conn(tmp_path / "0020.db")
    run_migrations(conn)
    try:
        for name in expected_tables:
            cols = {row["name"]: row for row in conn.execute(f"PRAGMA table_info({name})")}
            assert "user_id" in cols, f"{name} missing user_id"
            assert cols["user_id"]["notnull"] == 1
            assert cols["user_id"]["dflt_value"] == "'local'"
        idx = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='index' AND name='idx_memories_fact_key'"
        ).fetchone()
        assert idx is not None and "user_id" in idx["sql"]
    finally:
        conn.close()


def test_migration_0020_is_atomic(tmp_path, monkeypatch):
    """GC8: MIGRATION_0020_user_id is wrapped in BEGIN/COMMIT because
    run_migrations records the id only after executescript succeeds
    (:609-614 at plan-writing time) -- without the transaction a mid-script
    ALTER failure would leave earlier columns added and 0020 unrecorded,
    and every later boot would die on "duplicate column name". This
    monkeypatches a bogus ALTER into the middle of the script and confirms
    NOTHING from it landed, not even the columns added before the failure."""
    import jarvis.db as db

    db_path = tmp_path / "atomic.db"
    monkeypatch.setenv("JARVIS_DB_PATH", str(db_path))

    pre_0020 = [(mid, sql) for mid, sql in MIGRATIONS if mid != "0020_user_id"]
    monkeypatch.setattr(db, "MIGRATIONS", pre_0020)
    run_migrations()

    bogus_sql = MIGRATION_0020_user_id.replace(
        "ALTER TABLE council_scores ADD COLUMN user_id TEXT NOT NULL DEFAULT 'local';",
        "ALTER TABLE this_table_does_not_exist ADD COLUMN user_id TEXT NOT NULL DEFAULT 'local';",
        1,
    )
    assert bogus_sql != MIGRATION_0020_user_id, "replacement target not found in migration SQL"
    monkeypatch.setattr(db, "MIGRATIONS", pre_0020 + [("0020_user_id", bogus_sql)])

    with pytest.raises(sqlite3.OperationalError):
        run_migrations()

    conn = get_conn(db_path)
    try:
        applied = {row["id"] for row in conn.execute("SELECT id FROM migrations")}
        assert "0020_user_id" not in applied
        # "notes" is ALTERed before "council_scores" in the script -- if the
        # transaction rolled back correctly, even this earlier ALTER is gone.
        cols = {row["name"] for row in conn.execute("PRAGMA table_info(notes)")}
        assert "user_id" not in cols
    finally:
        conn.close()


def test_migration_0021_notified_at(tmp_path):
    """GC9 (gap-closure plan, 2026-09-04): reminders.notified_at exists,
    nullable, and is NULL for a freshly-migrated table."""
    conn = get_conn(tmp_path / "0021.db")
    run_migrations(conn)
    try:
        cols = {row["name"]: row for row in conn.execute("PRAGMA table_info(reminders)")}
        assert "notified_at" in cols
        assert cols["notified_at"]["notnull"] == 0
        cur = conn.execute(
            "INSERT INTO reminders (message, due_at, status, delivered, created_at) "
            "VALUES ('x', '2026-01-01T00:00:00Z', 'pending', 0, '2026-01-01T00:00:00Z')"
        )
        row = conn.execute(
            "SELECT notified_at FROM reminders WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
        assert row["notified_at"] is None
    finally:
        conn.close()


def test_migration_0026_expires_only_the_pending_actions(tmp_path):
    """W9 (MORTIMER_VOICE_WORKFLOWS_PLAN.md Phase 4): the tools that could
    confirm an action were retired on 2026-09-10, so a pending row can never
    resolve. The migration settles those and leaves every other row alone."""
    conn = get_conn(tmp_path / "actions.db")
    run_migrations(conn)
    rows = [("git_commit", "pending", None, None), ("repo_write", "pending", None, None),
            ("git_push", "committed", "2026-08-20T02:31:00+00:00", "ok"),
            ("git_push", "failed", "2026-08-30T21:41:00+00:00", "rejected")]
    for tool, status, resolved_at, result in rows:
        conn.execute(
            "INSERT INTO actions (tool, action_class, draft_payload, summary, status, created_at, resolved_at, result)"
            " VALUES (?, 'privileged', '{}', 's', ?, '2026-08-13T00:39:00+00:00', ?, ?)",
            (tool, status, resolved_at, result))
    conn.execute("DELETE FROM migrations WHERE id = '0026_expire_retired_actions'")
    conn.commit()
    assert run_migrations(conn) == ["0026_expire_retired_actions"]
    got = [dict(r) for r in conn.execute("SELECT tool, status, resolved_at, result FROM actions ORDER BY id")]
    assert [r["status"] for r in got] == ["expired", "expired", "committed", "failed"]
    assert all(r["resolved_at"] and "retired on 2026-09-10" in r["result"] for r in got[:2])
    assert got[2]["result"] == "ok" and got[3]["resolved_at"] == "2026-08-30T21:41:00+00:00"
    assert conn.execute("SELECT COUNT(*) FROM actions WHERE status = 'pending'").fetchone()[0] == 0
    conn.close()
