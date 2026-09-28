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
# unreachable once they fall out of memories' per-tier fact caps.
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
  status TEXT NOT NULL,              -- running | ok | failed | timeout | cancelled
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

# K1 (MORTIMER_KNOWLEDGE_FRAMEWORK_PLAN.md) — memory tiers. The single
# flat fact pool was the structural defect: on 2026-08-18 the store held
# 180 facts and only ~14 reached the Supervisor, because 67 facts ABOUT
# MORTIMER'S OWN CONFIG (re-derivable from the repo) competed for the same
# 30 slots as durable facts about Larry. Tier is about DURABILITY, not
# topic: identity never drops, preference is consolidated rather than
# evicted, project ages out, system is excluded from context by default.
#
# Backfill is a best-effort key-prefix heuristic — deliberately
# conservative: anything unrecognized lands in 'project', the middle tier,
# so a misclassification can neither pin junk forever (identity) nor hide
# something real (system). Larry re-tiers by review, not by trusting this.
MIGRATION_0012 = """
ALTER TABLE memories ADD COLUMN tier TEXT;

UPDATE memories SET tier = 'system'
 WHERE tier IS NULL AND (
   key LIKE '%.mortimer.%' OR key LIKE 'mortimer.%'
   OR key LIKE '%.jarvis.%' OR key LIKE 'jarvis.%'
   OR key LIKE '%.system.%' OR key LIKE 'system.%'
 );

UPDATE memories SET tier = 'identity'
 WHERE tier IS NULL AND (
   key = 'user.name' OR key LIKE 'user.identity.%'
   OR key LIKE 'user.location%' OR key LIKE 'user.timezone%'
   OR key LIKE 'user.contact.%'
 );

UPDATE memories SET tier = 'preference'
 WHERE tier IS NULL AND (
   key LIKE 'user.preference.%' OR key LIKE 'user.style.%'
   OR key LIKE 'user.frustration%'
 );

UPDATE memories SET tier = 'project' WHERE tier IS NULL AND kind = 'fact';
"""

# K6.3 (MORTIMER_KNOWLEDGE_FRAMEWORK_PLAN.md) — archive, never destroy.
#
# The conversion layer moves facts between buckets. On 2026-08-18 a fact
# was over-deleted during cleanup and had to be reconstructed from
# TRUNCATED console output — its tail is still incomplete. That is not an
# acceptable recovery story for a layer whose whole job is moving things
# around, so a converted fact is marked, not removed:
#   archived_at  — when it left active memory (NULL = still live)
#   became       — what it turned into ("workflow:git-flow", "deleted:stale")
# Reads filter on archived_at IS NULL; nothing has to be reconstructed.
MIGRATION_0013 = """
ALTER TABLE memories ADD COLUMN archived_at TEXT;
ALTER TABLE memories ADD COLUMN became TEXT;
"""

# MORTIMER_KEY_VALIDITY_PLAN.md K6 (Larry 2026-08-19). proposer_count and
# judge_count record who ANSWERED, not who was asked. A member whose call
# fails is logged as a warning and dropped from the list
# (`council_proposer_failed` in council.py's `_gather_proposals._one`), so a
# round convened with four proposers and lost two to a dead credential is
# indistinguishable in the database from a round that only ever had two.
#
# That is the same class of blindness that hid a credential-less
# gpt-4.1-mini for months: tier 1 fans out ALL economy profiles, one had no
# usable key, and every tier-1 round quietly ran on a single proposer while
# `select_winner` dutifully "selected" the only candidate. A council of one
# is not a council, and nothing recorded that it had happened.
#
# NULL on pre-migration rows and never backfilled — the information does
# not exist for them, and inventing it is worse than admitting the gap.
MIGRATION_0014 = """
ALTER TABLE council_rounds ADD COLUMN proposers_attempted INTEGER;
ALTER TABLE council_rounds ADD COLUMN judges_attempted INTEGER;
"""

# MORTIMER_MEMORY_AUTOCONSOLIDATION_PLAN.md A3/A5 (Larry 2026-08-20). The
# manual 2026-08-20 cleanup proved automation can resolve ~80% of memory
# bloat mechanically but the remaining ~20% (real contradictions, a
# scorer's wrong keep-choice, mixed-content facts) needs Larry — this
# table is where those cases wait for him rather than being silently
# guessed at.
#
# memory_reviews: one row per contradiction/cluster the sweep found but
# would not act on. `keys_json` is the JSON list of the memories.key
# values involved (never the row ids — keys survive archive/restore,
# ids are an implementation detail); `detail` is the human-readable
# explanation shown in the console panel and read aloud by voice.
# `dismissed` is a resolution ("both true"), not a delete — the pair's
# hash stays in the sweep's classification cache either way so it is
# never re-queued for the same content.
#
# audience column on memories: A5's segmentation. NULL means
# unclassified and is treated as 'interaction' by render_memory_context
# (fail-open — see jarvis/memory.py) so an unclassified fact never
# silently drops out of the prompt while waiting for the next sweep to
# classify it.
MIGRATION_0015 = """
CREATE TABLE IF NOT EXISTS memory_reviews (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  kind TEXT NOT NULL,                 -- 'contradiction' | 'cluster'
  keys_json TEXT NOT NULL,
  detail TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'open',  -- 'open' | 'resolved' | 'dismissed'
  created_at TEXT NOT NULL,
  resolved_at TEXT
);
ALTER TABLE memories ADD COLUMN audience TEXT;
"""

# MORTIMER_OPTIMIZATION_PLAN.md Phase 2 (extraction gate) — the new
# per-exchange worker (jarvis/memory_extraction_worker.py) needs a
# cross-process watermark (it is a separate process from the bot, unlike
# today's in-process MemorySweepWatcher) and both memories/observations
# need somewhere to record "we've seen this again" so the novelty gate
# can bump an existing row instead of writing a near-duplicate sibling —
# see jarvis/memory_extraction.py's module docstring for the full design.
#
# recurrence_count/last_seen_at/provenance added to BOTH tables (not just
# observations) because the novelty gate runs before either an immediate
# fact admission or a staged observation insert — a re-stated fact is
# exactly as much "we already know this" as a re-observed tendency.
# provenance defaults differ by table: memories rows (facts) default
# 'stated' (today's fact-admission path is reserved for explicit/durable
# statements per EXTRACTION_PROMPT's existing rules); observations
# default 'inferred' (that is the whole point of the staging tier).
# last_seen_at backfills from the best existing timestamp so no row is
# left NULL for the novelty gate's ORDER BY to trip on.
MIGRATION_0016 = """
ALTER TABLE memories ADD COLUMN recurrence_count INTEGER NOT NULL DEFAULT 1;
ALTER TABLE memories ADD COLUMN last_seen_at TEXT;
ALTER TABLE memories ADD COLUMN provenance TEXT NOT NULL DEFAULT 'stated';
ALTER TABLE memories ADD COLUMN source_turn INTEGER;
UPDATE memories SET last_seen_at = COALESCE(updated_at, created_at)
  WHERE last_seen_at IS NULL;

ALTER TABLE observations ADD COLUMN recurrence_count INTEGER NOT NULL DEFAULT 1;
ALTER TABLE observations ADD COLUMN last_seen_at TEXT;
ALTER TABLE observations ADD COLUMN provenance TEXT NOT NULL DEFAULT 'inferred';
ALTER TABLE observations ADD COLUMN source_turn INTEGER;
UPDATE observations SET last_seen_at = created_at WHERE last_seen_at IS NULL;

-- Single-row cursor: the worker is a separate process from the bot (and
-- from the admin sidecar), so "where did I leave off" must live in the
-- WAL-mode db, not in that process's memory. id=1 CHECK enforces the
-- exactly-one-row invariant at the schema level, matching set_summary's
-- "exactly one row" convention for the summary kind.
CREATE TABLE IF NOT EXISTS memory_extraction_cursor (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  last_processed_conversation_id INTEGER NOT NULL DEFAULT 0,
  updated_at TEXT NOT NULL
);
INSERT OR IGNORE INTO memory_extraction_cursor
  (id, last_processed_conversation_id, updated_at)
  VALUES (1, 0, '1970-01-01T00:00:00+00:00');
"""

# Automated memory classification metadata and durable idle-maintenance queue
# (MORTIMER_MEMORY_AUTOCONSOLIDATION_PLAN.md B7).  This is intentionally a
# later migration: 0016 is already the extraction-v2 migration in production.
MIGRATION_0022 = """
ALTER TABLE memories ADD COLUMN subject TEXT;
ALTER TABLE memories ADD COLUMN scope TEXT DEFAULT 'global';
ALTER TABLE memories ADD COLUMN memory_type TEXT DEFAULT 'fact';
ALTER TABLE memories ADD COLUMN evidence_status TEXT DEFAULT 'unknown';
ALTER TABLE memories ADD COLUMN confidence REAL DEFAULT 0.0;
ALTER TABLE memories ADD COLUMN valid_from TEXT;
ALTER TABLE memories ADD COLUMN valid_until TEXT;
ALTER TABLE memories ADD COLUMN source_turn_id TEXT;
ALTER TABLE memories ADD COLUMN content_revision INTEGER NOT NULL DEFAULT 1;
ALTER TABLE memories ADD COLUMN classifier_version TEXT DEFAULT 'legacy-v1';
ALTER TABLE memories ADD COLUMN classified_at TEXT;
ALTER TABLE memories ADD COLUMN supersedes_id INTEGER;
CREATE INDEX IF NOT EXISTS idx_memories_automation_scope ON memories(scope, memory_type);
CREATE TABLE IF NOT EXISTS memory_maintenance (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id TEXT NOT NULL DEFAULT 'local',
  memory_id INTEGER NOT NULL,
  operation TEXT NOT NULL,
  content_revision INTEGER NOT NULL,
  policy_version TEXT NOT NULL,
  attempts INTEGER NOT NULL DEFAULT 0,
  next_attempt_at TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued',
  last_error_code TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(memory_id, content_revision, policy_version, operation)
);
CREATE INDEX IF NOT EXISTS idx_memory_maintenance_due
  ON memory_maintenance(status, next_attempt_at);
"""

# Shadow classification evidence is deliberately separate from ``memories``:
# it records what the classifier proposed without making that proposal part
# of live retrieval. The table stores only bounded metadata and a digest of
# the redacted candidate, never candidate text.
MIGRATION_0023 = """
CREATE TABLE IF NOT EXISTS memory_classification_shadow (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  maintenance_id INTEGER NOT NULL UNIQUE,
  user_id TEXT NOT NULL DEFAULT 'local',
  memory_id INTEGER NOT NULL,
  content_revision INTEGER NOT NULL,
  policy_version TEXT NOT NULL,
  candidate_digest TEXT NOT NULL,
  classification_json TEXT NOT NULL,
  observed_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_memory_classification_shadow_observed
  ON memory_classification_shadow(observed_at);
"""


# MORTIMER_OPTIMIZATION_PLAN.md Phase 2, continued — a single global
# cursor (migration 0016) cannot express "session X has an unresolved
# trailing user turn" without one of two bad outcomes: block every OTHER
# session's advancement behind it (one busy or stuck session stalls
# extraction for the whole system), or advance past it and lose the
# pairing forever. Worse, jarvis/bot/transcript_log.py's P2/P6 privacy
# gate deliberately never persists a sensitive assistant reply at all —
# so a dangling user row with NO reply ever coming is not a rare timing
# glitch, it is designed, expected behavior of this codebase. A cursor
# that blocks on "wait for the reply" would stall permanently the first
# time that gate fires.
#
# memory_extraction_pending fixes this by tracking the one open user turn
# per session OUTSIDE the global cursor: the cursor advances unconditionally
# every poll, and jarvis/memory_extraction_worker.py consults this table
# (not in-process memory, so it survives a worker restart too) to recover
# pairing state across polls. A row here older than the worker's orphan
# timeout is simply dropped — the pairing is given up on, not extracted,
# which matches the pipeline's own privacy intent: if the assistant side
# was never safe to persist, extracting from the lone user question isn't
# either. One row per session (PRIMARY KEY) — a newer user turn overwrites
# an older unresolved one rather than queuing both, since only the most
# recent user utterance is ever the trigger for the next reply.
MIGRATION_0017 = """
CREATE TABLE IF NOT EXISTS memory_extraction_pending (
  session_id TEXT PRIMARY KEY,
  user_content TEXT NOT NULL,
  user_turn_id INTEGER NOT NULL,
  first_seen_at TEXT NOT NULL
);
"""

# MORTIMER_OPTIMIZATION_PLAN.md Phase 3 Rev 3.3 (2026-09-03). D8.1's
# retry_validated (1|0|NULL) was NULL on every council round ever recorded
# — including the one real planner round (e48cfbe1, 2026-09-01) — because
# it is only written when the post-council retry reaches a session_validate
# call, and nothing wrote anything when the retry never got there (prose
# reply, iteration cap, time limit, cancel, decline). NULL therefore could
# not distinguish "council brief was abandoned" from "not yet". This column
# makes the outcome explicit at session end; retry_validated keeps its
# meaning and its readers (compute_agreement etc.) untouched. Vocabulary is
# documented on jarvis.council.council.record_retry_outcome.
MIGRATION_0018 = """
ALTER TABLE council_rounds ADD COLUMN retry_outcome TEXT;
"""

# MORTIMER_OPTIMIZATION_PLAN.md Phase 4 Rev 3.4, Stage A3 (2026-09-03).
# The recall-failure proxy. Phase 2's novelty gate already computes, per
# extracted fact candidate, whether the user just restated something the
# store already had (outcome 'exact_update' or 'near_duplicate:<key>') —
# a signal that was thrown away. Not every restatement is a recall miss
# (people repeat themselves), but the RATE per session is the only signal
# available that scales without a human labelling anything, and Phase 4's
# Stage B is gated on it rather than on the assumption that recall is bad.
# One row per restated fact; 'inserted' and 'rejected' write nothing, and
# observations are never counted (they are inferred, not restated).
MIGRATION_0019 = """
CREATE TABLE IF NOT EXISTS memory_recall_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT,
  source_turn INTEGER,
  key TEXT NOT NULL,
  outcome TEXT NOT NULL,             -- 'exact_update' | 'near_duplicate'
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_recall_events_created
  ON memory_recall_events(created_at);
"""

MIGRATION_0020_user_id = """
BEGIN;
ALTER TABLE notes ADD COLUMN user_id TEXT NOT NULL DEFAULT 'local';
ALTER TABLE reminders ADD COLUMN user_id TEXT NOT NULL DEFAULT 'local';
ALTER TABLE conversations ADD COLUMN user_id TEXT NOT NULL DEFAULT 'local';
ALTER TABLE actions ADD COLUMN user_id TEXT NOT NULL DEFAULT 'local';
ALTER TABLE memories ADD COLUMN user_id TEXT NOT NULL DEFAULT 'local';
ALTER TABLE observations ADD COLUMN user_id TEXT NOT NULL DEFAULT 'local';
ALTER TABLE agent_runs ADD COLUMN user_id TEXT NOT NULL DEFAULT 'local';
ALTER TABLE agent_events ADD COLUMN user_id TEXT NOT NULL DEFAULT 'local';
ALTER TABLE procedures ADD COLUMN user_id TEXT NOT NULL DEFAULT 'local';
ALTER TABLE council_rounds ADD COLUMN user_id TEXT NOT NULL DEFAULT 'local';
ALTER TABLE council_scores ADD COLUMN user_id TEXT NOT NULL DEFAULT 'local';
ALTER TABLE memory_reviews ADD COLUMN user_id TEXT NOT NULL DEFAULT 'local';
ALTER TABLE memory_extraction_cursor ADD COLUMN user_id TEXT NOT NULL DEFAULT 'local';
ALTER TABLE memory_extraction_pending ADD COLUMN user_id TEXT NOT NULL DEFAULT 'local';
ALTER TABLE memory_recall_events ADD COLUMN user_id TEXT NOT NULL DEFAULT 'local';
DROP INDEX IF EXISTS idx_memories_fact_key;
CREATE UNIQUE INDEX IF NOT EXISTS idx_memories_fact_key
  ON memories(user_id, key) WHERE kind = 'fact';
COMMIT;
"""

MIGRATION_0021_reminders_notified = """
ALTER TABLE reminders ADD COLUMN notified_at TEXT;
"""

MIGRATION_0024_model_route_preferences = """
CREATE TABLE IF NOT EXISTS model_route_preferences (
  workload TEXT PRIMARY KEY,
  profile TEXT NOT NULL,
  route TEXT NOT NULL,
  privacy TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  user_id TEXT NOT NULL DEFAULT 'local'
);
CREATE TABLE IF NOT EXISTS model_route_drafts (
  draft_id TEXT PRIMARY KEY,
  workload TEXT NOT NULL,
  profile TEXT NOT NULL,
  route TEXT NOT NULL,
  privacy TEXT NOT NULL,
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  user_id TEXT NOT NULL DEFAULT 'local'
);
CREATE INDEX IF NOT EXISTS idx_model_route_drafts_expiry
  ON model_route_drafts(expires_at);
"""

# Durable staging for new extraction exchanges before the global cursor moves
# past them. Payloads remain staging-only and are removed on terminal success,
# cancellation, or an authorized forget request.
MIGRATION_0025_memory_admission_jobs = """
CREATE TABLE IF NOT EXISTS memory_admission_jobs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  idempotency_key TEXT NOT NULL UNIQUE,
  user_id TEXT NOT NULL DEFAULT 'local',
  session_id TEXT NOT NULL,
  user_turn_id INTEGER NOT NULL,
  assistant_turn_id INTEGER NOT NULL,
  policy_version TEXT NOT NULL,
  stage TEXT NOT NULL DEFAULT 'extract'
    CHECK (stage IN ('extract','classify','apply')),
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending','running','complete','failed','cancelled')),
  candidate_json TEXT,
  classification_json TEXT,
  attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
  next_attempt_at TEXT NOT NULL,
  claimed_at TEXT,
  last_error_code TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(user_id, session_id, user_turn_id, assistant_turn_id, policy_version)
);
CREATE INDEX IF NOT EXISTS idx_memory_admission_jobs_due
  ON memory_admission_jobs(status, next_attempt_at, id);
CREATE INDEX IF NOT EXISTS idx_memory_admission_jobs_turns
  ON memory_admission_jobs(user_id, user_turn_id, assistant_turn_id);
"""

# Atomic shared classification budget for the legacy maintenance queue and
# durable exchange-admission jobs. Existing rows remain countable as legacy
# usage; new provider work reserves before it leaves the process.
MIGRATION_0026_memory_classification_budget = """
ALTER TABLE memory_maintenance ADD COLUMN budget_reservation_id TEXT;
CREATE TABLE IF NOT EXISTS memory_classification_budget_reservations (
  reservation_id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL DEFAULT 'local',
  usage_day TEXT NOT NULL,
  candidate_count INTEGER NOT NULL CHECK (candidate_count >= 0),
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_memory_classification_budget_day
  ON memory_classification_budget_reservations(usage_day);
"""

MIGRATION_0027_memory_admission_shadow = """
CREATE TABLE IF NOT EXISTS memory_admission_shadow (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id INTEGER NOT NULL UNIQUE,
  user_id TEXT NOT NULL DEFAULT 'local',
  candidate_digest TEXT NOT NULL,
  classification_json TEXT NOT NULL,
  observed_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_memory_admission_shadow_observed
  ON memory_admission_shadow(observed_at);
"""

# GC24-02: correlate durable tool requests/results and expose actions whose
# outcome is unknown after cancellation or process interruption. Legacy event
# rows remain readable with a NULL call identity.
MIGRATION_0028_agent_event_tool_call_identity = """
ALTER TABLE agent_events ADD COLUMN tool_call_id TEXT;
CREATE INDEX idx_agent_events_tool_call
  ON agent_events(run_id, tool_call_id, type);
"""

# GC24-02: durable one-shot claims for side-effecting job starts. The
# execution id is supplied by the owning execution (currently a SubAgent run
# id for plan_start), so a provider may issue a fresh tool_call_id without
# starting the same job again. No prompt, arguments, or result content is
# stored in this table.
MIGRATION_0029_execution_action_claims = """
CREATE TABLE IF NOT EXISTS execution_action_claims (
  user_id TEXT NOT NULL DEFAULT 'local',
  action_scope TEXT NOT NULL,
  execution_id TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'claimed'
    CHECK (status IN ('claimed','running','awaiting_choice','completed','failed')),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY(user_id, action_scope, execution_id)
);
CREATE INDEX IF NOT EXISTS idx_execution_action_claims_updated
  ON execution_action_claims(user_id, updated_at);
"""

# Skills workspace SW2: bounded, content-free execution receipts. These are
# separate from agent_events so the UI never has to interpret preview fields
# as a skill schema. Retention is explicitly coupled in runlog.prune.
MIGRATION_0030_skill_events = """
CREATE TABLE IF NOT EXISTS skill_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id TEXT NOT NULL DEFAULT 'local',
  run_id TEXT NOT NULL,
  request_id TEXT NOT NULL,
  event_id TEXT NOT NULL,
  seq INTEGER NOT NULL,
  schema_version INTEGER NOT NULL CHECK (schema_version = 1),
  occurred_at TEXT NOT NULL,
  skill_id TEXT,
  skill_revision TEXT,
  step_id TEXT,
  attempt_id TEXT,
  type TEXT NOT NULL CHECK (type IN (
    'skill_selected', 'skill_resource_read', 'skill_step_started',
    'skill_step_finished', 'skill_step_skipped', 'skill_selection_refused',
    'protected_activity', 'truncated'
  )),
  status TEXT NOT NULL CHECK (status IN (
    'running', 'passed', 'failed', 'skipped', 'unknown'
  )),
  evidence_refs TEXT NOT NULL DEFAULT '[]',
  UNIQUE(user_id, run_id, event_id),
  UNIQUE(user_id, run_id, seq)
);
CREATE INDEX IF NOT EXISTS idx_skill_events_skill_revision
  ON skill_events(user_id, skill_id, skill_revision, run_id, seq);
CREATE INDEX IF NOT EXISTS idx_skill_events_run_cursor
  ON skill_events(user_id, run_id, seq);
"""

# K1 (MORTIMER_REMOTE_ACCESS_PLAN.md A1/A3): per-client bearer tokens.
# Only SHA-256 digests are stored; plaintext is shown once by the CLI.
# No backfill is needed: an empty table means no caller is authorized.
MIGRATION_0031 = """
CREATE TABLE IF NOT EXISTS client_tokens (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id TEXT NOT NULL DEFAULT 'larry',
  name TEXT NOT NULL UNIQUE,
  token_hash TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL,
  last_used_at TEXT,
  revoked_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_client_tokens_revoked
  ON client_tokens(revoked_at);
"""

# Skills workspace SW2: one-shot host-controller receipts for verifiable
# process-step checks. The receipt payload is not retained; its digest, exact
# scope and bounded lifetime suffice for replay/idempotency checks.
MIGRATION_0032_skill_step_check_receipts = """
CREATE TABLE IF NOT EXISTS skill_step_check_receipts (
  user_id TEXT NOT NULL DEFAULT 'local',
  receipt_id TEXT NOT NULL,
  run_id TEXT NOT NULL,
  request_id TEXT NOT NULL,
  skill_id TEXT NOT NULL,
  skill_revision TEXT NOT NULL,
  step_id TEXT NOT NULL,
  attempt_id TEXT NOT NULL,
  receipt_sha256 TEXT NOT NULL,
  issued_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  accepted_at TEXT NOT NULL,
  UNIQUE(user_id, receipt_id),
  UNIQUE(user_id, run_id, skill_id, skill_revision, step_id, attempt_id)
);
CREATE INDEX IF NOT EXISTS idx_skill_step_receipts_run
  ON skill_step_check_receipts(user_id, run_id);
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
    ("0012_memory_tiers", MIGRATION_0012),
    ("0013_memory_archive", MIGRATION_0013),
    ("0014_council_attempted", MIGRATION_0014),
    ("0015_memory_reviews", MIGRATION_0015),
    ("0016_memory_extraction_v2", MIGRATION_0016),
    ("0017_memory_extraction_pending", MIGRATION_0017),
    ("0018_council_retry_outcome", MIGRATION_0018),
    ("0019_memory_recall_events", MIGRATION_0019),
    ("0020_user_id", MIGRATION_0020_user_id),  # GC8 (gap-closure plan, 2026-09-04)
    ("0021_reminders_notified", MIGRATION_0021_reminders_notified),  # GC9
    ("0022_memory_automation", MIGRATION_0022),
    ("0023_memory_classification_shadow", MIGRATION_0023),
    ("0024_model_route_preferences", MIGRATION_0024_model_route_preferences),
    ("0025_memory_admission_jobs", MIGRATION_0025_memory_admission_jobs),
    ("0026_memory_classification_budget", MIGRATION_0026_memory_classification_budget),
    ("0027_memory_admission_shadow", MIGRATION_0027_memory_admission_shadow),
    ("0028_agent_event_tool_call_identity", MIGRATION_0028_agent_event_tool_call_identity),
    ("0029_execution_action_claims", MIGRATION_0029_execution_action_claims),
    ("0030_skill_events", MIGRATION_0030_skill_events),
    ("0031_client_tokens", MIGRATION_0031),
    ("0032_skill_step_check_receipts", MIGRATION_0032_skill_step_check_receipts),
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


def claim_execution_action(
    action_scope: str, execution_id: str, db_path: str | Path | None = None,
    *, user_id: str = "local",
) -> bool:
    """Atomically claim one side effect for a stable owning execution id.

    This does not infer equivalence from tool arguments. Callers must choose
    an action scope and an execution identity whose lifecycle matches the
    protected operation. A false result means a prior attempt may have
    produced an effect and must be reconciled before retry.
    """
    scope = str(action_scope or "").strip()
    identity = str(execution_id or "").strip()
    owner = str(user_id or "").strip()
    if (not scope or len(scope) > 160 or not identity or len(identity) > 256
            or not owner or len(owner) > 128):
        raise ValueError("action scope and execution id must be bounded and non-empty")
    stamp = now_iso()
    conn = get_conn(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        cur = conn.execute(
            "INSERT OR IGNORE INTO execution_action_claims "
            "(user_id, action_scope, execution_id, status, created_at, updated_at) "
            "VALUES (?, ?, ?, 'claimed', ?, ?)",
            (owner, scope, identity, stamp, stamp),
        )
        conn.commit()
        return cur.rowcount == 1
    finally:
        conn.close()


def update_execution_action(
    action_scope: str, execution_id: str, status: str,
    db_path: str | Path | None = None, *, user_id: str = "local",
) -> bool:
    """Update a claimed action's bounded lifecycle state; never creates it."""
    if status not in {"claimed", "running", "awaiting_choice", "completed", "failed"}:
        raise ValueError("unsupported execution action status")
    conn = get_conn(db_path)
    try:
        cur = conn.execute(
            "UPDATE execution_action_claims SET status = ?, updated_at = ? "
            "WHERE user_id = ? AND action_scope = ? AND execution_id = ?",
            (status, now_iso(), user_id, action_scope, execution_id),
        )
        conn.commit()
        return cur.rowcount == 1
    finally:
        conn.close()


def get_execution_action(
    action_scope: str, execution_id: str, db_path: str | Path | None = None,
    *, user_id: str = "local",
) -> dict[str, str] | None:
    """Return only the content-free receipt for one claimed action."""
    conn = get_conn(db_path)
    try:
        row = conn.execute(
            "SELECT user_id, action_scope, execution_id, status, created_at, updated_at "
            "FROM execution_action_claims WHERE user_id = ? AND action_scope = ? "
            "AND execution_id = ?",
            (user_id, action_scope, execution_id),
        ).fetchone()
        return dict(row) if row is not None else None
    finally:
        conn.close()


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
