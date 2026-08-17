"""SQLite persistence (plan Phase 0 step 0.4, schema locked in §5/§0.4).

Stdlib sqlite3 only. WAL mode, row_factory = sqlite3.Row. Migrations are
applied in order and tracked in the `migrations` table; running them twice
is idempotent.

Exposes exactly (per plan): get_conn(), run_migrations(), now_iso().
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

MIGRATION_0001 = """
CREATE TABLE IF NOT EXISTS migrations (
  id TEXT PRIMARY KEY, applied_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS notes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL,
  body TEXT NOT NULL,
  tags TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reminders (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  message TEXT NOT NULL,
  due_at TEXT NOT NULL,              -- ISO 8601, timezone-aware
  status TEXT NOT NULL DEFAULT 'pending',   -- pending | done | cancelled
  delivered INTEGER NOT NULL DEFAULT 0,     -- 1 once spoken to the user
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS conversations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT NOT NULL,
  role TEXT NOT NULL,                -- user | assistant | tool
  content TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_reminders_due ON reminders(status, due_at);
CREATE INDEX IF NOT EXISTS idx_notes_tags ON notes(tags);
"""

MIGRATION_0002 = """
CREATE TABLE IF NOT EXISTS actions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tool TEXT NOT NULL,                -- e.g. git_commit, git_push
  action_class TEXT NOT NULL,        -- standard | privileged
  draft_payload TEXT NOT NULL,       -- JSON of the prepared action
  summary TEXT NOT NULL,             -- human-readable read-back text
  status TEXT NOT NULL DEFAULT 'pending',  -- pending | committed | failed | expired
  created_at TEXT NOT NULL,
  resolved_at TEXT,
  transcript_excerpt TEXT,
  result TEXT
);
CREATE INDEX IF NOT EXISTS idx_actions_status ON actions(status, tool);
"""

MIGRATION_0003 = """
CREATE TABLE IF NOT EXISTS memories (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  kind TEXT NOT NULL,                -- fact | summary
  key TEXT,                          -- facts only, e.g. user.name (unique per fact)
  content TEXT NOT NULL,
  source_session_id TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_memories_fact_key
  ON memories(key) WHERE kind = 'fact';
"""

MIGRATION_0004 = """
CREATE TABLE IF NOT EXISTS observations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  key TEXT NOT NULL,                 -- tendency key, e.g. user.style.brevity
  content TEXT NOT NULL,             -- one observed instance of the pattern
  source_session_id TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_observations_key ON observations(key);
"""

# Upgrade plan Phase 5a: FTS5 full-text search over conversations, so old
# sessions become recallable ("what did we discuss last month?") instead of
# unreachable once they fall out of memories' MAX_FACTS window.
#
# External-content table (content='conversations', content_rowid='id'):
# the FTS index stores only the inverted index, not a copy of the text, so
# it can never drift out of sync with row content itself — only with which
# rows exist, which the three triggers below keep synchronized. This is the
# standard SQLite-recommended pattern for FTS-over-an-existing-table.
MIGRATION_0005 = """
CREATE VIRTUAL TABLE IF NOT EXISTS conversations_fts USING fts5(
  content, session_id UNINDEXED, role UNINDEXED, created_at UNINDEXED,
  content='conversations', content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS conversations_fts_ai AFTER INSERT ON conversations BEGIN
  INSERT INTO conversations_fts(rowid, content, session_id, role, created_at)
  VALUES (new.id, new.content, new.session_id, new.role, new.created_at);
END;

CREATE TRIGGER IF NOT EXISTS conversations_fts_ad AFTER DELETE ON conversations BEGIN
  INSERT INTO conversations_fts(conversations_fts, rowid, content, session_id, role, created_at)
  VALUES ('delete', old.id, old.content, old.session_id, old.role, old.created_at);
END;

CREATE TRIGGER IF NOT EXISTS conversations_fts_au AFTER UPDATE ON conversations BEGIN
  INSERT INTO conversations_fts(conversations_fts, rowid, content, session_id, role, created_at)
  VALUES ('delete', old.id, old.content, old.session_id, old.role, old.created_at);
  INSERT INTO conversations_fts(rowid, content, session_id, role, created_at)
  VALUES (new.id, new.content, new.session_id, new.role, new.created_at);
END;

INSERT INTO conversations_fts(rowid, content, session_id, role, created_at)
SELECT id, content, session_id, role, created_at FROM conversations;
"""

# Run-logging plan (MORTIMER_RUN_LOGGING_PLAN.md §5.1): durable, queryable
# records of every sub-agent delegation and the MCP calls it made. Full
# payloads (untruncated tool args/results, the full reply) live in a JSONL
# file per run under logs/agents/<date>/<run_id>.jsonl (payload_path);
# these tables hold bounded, indexed previews plus the pointer to that
# file. See jarvis/runlog/store.py.
MIGRATION_0006 = """
CREATE TABLE IF NOT EXISTS agent_runs (
  run_id TEXT PRIMARY KEY,
  session_id TEXT,
  agent TEXT NOT NULL,
  display_name TEXT NOT NULL DEFAULT '',
  task TEXT NOT NULL,
  status TEXT NOT NULL,              -- running | ok | failed | timeout
  started_at TEXT NOT NULL,
  ended_at TEXT,
  latency_ms INTEGER,
  tool_count INTEGER NOT NULL DEFAULT 0,
  error TEXT,                        -- the FAILED: reason, else NULL
  reply_preview TEXT,                -- first PREVIEW_CHARS of the reply
  payload_path TEXT                  -- repo-relative path to the JSONL
);
CREATE INDEX IF NOT EXISTS idx_agent_runs_agent  ON agent_runs(agent, started_at);
CREATE INDEX IF NOT EXISTS idx_agent_runs_status ON agent_runs(status, started_at);
CREATE INDEX IF NOT EXISTS idx_agent_runs_session ON agent_runs(session_id);

CREATE TABLE IF NOT EXISTS agent_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL,
  seq INTEGER NOT NULL,
  type TEXT NOT NULL,                -- tool_call | tool_result | mcp_call
  tool TEXT,
  server TEXT,                       -- MCP server name; mcp_call only
  ok INTEGER,                        -- 1 | 0 | NULL
  latency_ms INTEGER,
  args_preview TEXT,
  result_preview TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_agent_events_run ON agent_events(run_id, seq);
"""

# Reliable-memory + procedures plan (MORTIMER_MEMORY_PROCEDURES_PLAN.md
# D19), Part B: procedures learned from jarvis.runlog run outcomes and
# injected as prompt hints (jarvis/procedures.py). FTS5 structure copied
# field-for-field from conversations_fts's three triggers (MIGRATION_0005)
# — same external-content pattern, same delete-then-reinsert shape for
# UPDATE. No backfill INSERT here (unlike MIGRATION_0005) — procedures is a
# brand-new, empty table at migration time.
MIGRATION_0007 = """
CREATE TABLE IF NOT EXISTS procedures (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  agent TEXT NOT NULL,
  label TEXT NOT NULL,
  description TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'candidate',  -- candidate | active | deprecated
  success_count INTEGER NOT NULL DEFAULT 0,
  failure_count INTEGER NOT NULL DEFAULT 0,
  source_run_ids TEXT NOT NULL DEFAULT '[]', -- JSON array, capped
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  last_used_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_procedures_agent_status
  ON procedures(agent, status);

CREATE VIRTUAL TABLE IF NOT EXISTS procedures_fts USING fts5(
  label, description, agent UNINDEXED,
  content='procedures', content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS procedures_fts_ai AFTER INSERT ON procedures BEGIN
  INSERT INTO procedures_fts(rowid, label, description, agent)
  VALUES (new.id, new.label, new.description, new.agent);
END;

CREATE TRIGGER IF NOT EXISTS procedures_fts_ad AFTER DELETE ON procedures BEGIN
  INSERT INTO procedures_fts(procedures_fts, rowid, label, description, agent)
  VALUES ('delete', old.id, old.label, old.description, old.agent);
END;

CREATE TRIGGER IF NOT EXISTS procedures_fts_au AFTER UPDATE ON procedures BEGIN
  INSERT INTO procedures_fts(procedures_fts, rowid, label, description, agent)
  VALUES ('delete', old.id, old.label, old.description, old.agent);
  INSERT INTO procedures_fts(rowid, label, description, agent)
  VALUES (new.id, new.label, new.description, new.agent);
END;
"""

# MORTIMER_AGENT_TRUST_PLAN.md D24: both of the plan's schema changes land
# in ONE migration deliberately — two independently-numbered migrations
# from one plan is how a half-applied schema happens.
#
# agent_runs.tools_ok / tools_failed (D5): per-run counts of tool calls the
# D1 classifier judged ok vs failed, so a run's success/failure is visible
# as fact rather than inferred from a fabricated-sounding reply. Existing
# rows get NULL (SQLite's ALTER TABLE ... ADD COLUMN default), NOT
# backfilled from tool_count — a pre-migration row cannot actually
# distinguish ok from failed calls, and asserting tools_failed=0 for it
# would assert something the data does not support. Every reader (CLI,
# admin API, console) must treat NULL as "unknown, fall back to
# tool_count", never as zero.
#
# procedures.task_tokens (D21): the stopword-filtered token set of the task
# that created each procedure, written once by _create_candidate
# (jarvis/procedures.py) from the exact same _tokens(task) call the match
# path uses. Existing rows default to '' (via SQLite's column default),
# which can never match under D21's scoring — those 13 rows are
# intentionally left inert rather than back-filled from their
# descriptions; see the plan's D24 note for why.
MIGRATION_0008 = """
ALTER TABLE agent_runs ADD COLUMN tools_ok INTEGER;
ALTER TABLE agent_runs ADD COLUMN tools_failed INTEGER;
ALTER TABLE procedures ADD COLUMN task_tokens TEXT NOT NULL DEFAULT '';
"""

# MORTIMER_LLM_COUNCIL_PLAN.md D8: council rounds are delegations in all but
# name, so the shape mirrors MIGRATION_0006's two-tier pattern (bounded
# SQLite previews here; full proposal texts in logs/council/<date>/<round_id>
# .jsonl, written by jarvis/council/council.py). Both tables land in ONE
# migration deliberately (same D24 rule MIGRATION_0008's comment cites) —
# two migrations from one plan is how a half-applied schema happens.
#
# council_scores.shadow (D8.2): 1 == an advisory-only score from a shadow
# judge tier, written for judge-tier validation and NEVER consumed by
# select_winner. council.py must filter WHERE shadow = 0 before selecting a
# winner — this column is load-bearing, not cosmetic (D8's own note). The
# composite index on (round_id, shadow) exists so that filter is cheap.
MIGRATION_0009 = """
CREATE TABLE IF NOT EXISTS council_rounds (
  round_id TEXT PRIMARY KEY,
  run_id TEXT,                       -- reserved: agent-run correlation for
                                     -- future workflows (e.g. apps). NULL
                                     -- for all selfedit rounds -- the
                                     -- sidecar has no run_id
                                     -- (MORTIMER_LLM_COUNCIL_V2_PLAN.md V12)
  workflow TEXT NOT NULL,            -- 'selfedit' | 'apps'
  placement TEXT NOT NULL,           -- 'planner' | 'reviewer'
  trigger TEXT NOT NULL,             -- 'E1' | 'E2' | 'E3' | 'manual'
  tier INTEGER NOT NULL,             -- 1 | 2
  goal TEXT NOT NULL,
  proposer_count INTEGER NOT NULL,
  judge_count INTEGER NOT NULL,
  abstentions INTEGER NOT NULL DEFAULT 0,
  winner_profile TEXT,               -- unmasked AFTER selection
  winner_label TEXT,                 -- 'Proposal A'
  winner_mean REAL,
  select_reason TEXT,                -- which D7 branch decided it
  retry_validated INTEGER,           -- 1|0|NULL: did the retry pass? (D8.1)
  status TEXT NOT NULL,              -- running | ok | failed | too_small
  started_at TEXT NOT NULL,
  ended_at TEXT,
  latency_ms INTEGER
);
CREATE INDEX IF NOT EXISTS idx_council_rounds_run ON council_rounds(run_id);

CREATE TABLE IF NOT EXISTS council_scores (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  round_id TEXT NOT NULL,
  judge_profile TEXT NOT NULL,
  judge_tier TEXT NOT NULL,          -- 'economy'|'mid'|'frontier' (D8.2)
  shadow INTEGER NOT NULL DEFAULT 0, -- 1 == advisory only, excluded from
                                     -- selection (D8.2). Live scores are 0.
  proposal_label TEXT NOT NULL,
  proposal_profile TEXT NOT NULL,    -- unmasked at write time, post-selection
  score REAL,                        -- NULL == abstained
  abstain_reason TEXT,               -- NULL unless score IS NULL
  justification TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_council_scores_round ON council_scores(round_id);
CREATE INDEX IF NOT EXISTS idx_council_scores_shadow
  ON council_scores(round_id, shadow);
"""

# MORTIMER_LLM_COUNCIL_V2_PLAN.md V9/V13: both new column groups land in
# ONE migration deliberately (same D24 rule MIGRATION_0009's comment
# cites). All three columns are nullable; pre-v2 rows stay NULL, readers
# treat NULL as "unknown", never zero/empty — same discipline as
# MIGRATION_0008's tools_ok/tools_failed.
#
# prompt_tokens/completion_tokens (V9): summed across a round's proposer
# + live-judge calls only (never replay, never shadow — see V9's
# _gather_* usage-dict contract); NULL when no member response reported
# usage at all, not 0.
#
# registry_order (V13): JSON array of profile names in registry order at
# convene() time, so agreement.py and --replay can reproduce D7's rule-4
# tiebreak exactly instead of approximating it from row order.
MIGRATION_0010 = """
ALTER TABLE council_rounds ADD COLUMN prompt_tokens INTEGER;
ALTER TABLE council_rounds ADD COLUMN completion_tokens INTEGER;
ALTER TABLE council_rounds ADD COLUMN registry_order TEXT;
"""

# MORTIMER_PLANNING_PATHWAY_PLAN.md P3: which model authored a run was
# recorded nowhere — invisible in the Runs panel and the runlog CLI alike.
# Nullable, never backfilled — same discipline as MIGRATION_0008's
# tools_ok/tools_failed: pre-migration rows show "—", not a guessed value.
MIGRATION_0011 = """
ALTER TABLE agent_runs ADD COLUMN model TEXT;
"""

# (migration_id, sql) — applied strictly in list order.
MIGRATIONS: list[tuple[str, str]] = [
    ("0001_init", MIGRATION_0001),
    ("0002_actions", MIGRATION_0002),
    ("0003_memory", MIGRATION_0003),
    ("0004_observations", MIGRATION_0004),
    ("0005_conversation_search", MIGRATION_0005),
    ("0006_agent_runs", MIGRATION_0006),
    ("0007_procedures", MIGRATION_0007),
    ("0008_tool_outcomes", MIGRATION_0008),
    ("0009_council", MIGRATION_0009),
    ("0010_council_v2", MIGRATION_0010),
    ("0011_run_model", MIGRATION_0011),
]


def _default_db_path() -> Path:
    return Path(os.environ.get("JARVIS_DB_PATH", "data/jarvis.db"))


def get_conn(db_path: str | Path | None = None) -> sqlite3.Connection:
    """Open a connection (WAL mode, Row factory). Creates the parent dir."""
    path = Path(db_path) if db_path is not None else _default_db_path()
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def now_iso() -> str:
    """Current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def run_migrations(conn: sqlite3.Connection | None = None) -> list[str]:
    """Apply pending migrations. Returns the ids applied in this run."""
    own_connection = conn is None
    conn = conn or get_conn()
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS migrations "
            "(id TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        already = {row["id"] for row in conn.execute("SELECT id FROM migrations")}
        newly_applied: list[str] = []
        for migration_id, sql in MIGRATIONS:
            if migration_id in already:
                continue
            conn.executescript(sql)
            conn.execute(
                "INSERT INTO migrations (id, applied_at) VALUES (?, ?)",
                (migration_id, now_iso()),
            )
            newly_applied.append(migration_id)
        conn.commit()
        return newly_applied
    finally:
        if own_connection:
            conn.close()
