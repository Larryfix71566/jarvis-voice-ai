"""Persistent memory (upgrade plan U2.5).

Two layers over the existing per-session ``conversations`` transcript log:

- **facts** — keyed, durable statements about the user and their world
  (``user.name``, ``user.preference.*``, ``project.*`` …). Upserted by key;
  newer information replaces older.
- **summary** — exactly one running summary row, rewritten after each
  processed session so older context compacts instead of growing forever.

The Supervisor prompt injects :func:`render_memory_context` at pipeline
build time, so every new session starts already knowing the user's name,
preferences, and what was previously discussed. After a session ends,
:func:`update_memory_from_session` reads that session's transcript and asks
the LLM for a strict-JSON memory update (new/changed facts + rewritten
summary). Memory is advisory context only — it can never trigger actions,
and a failure anywhere in this module must never break the voice pipeline
(every public function degrades to a safe empty result).
"""

from __future__ import annotations

import json
import logging
import sqlite3
from typing import Any, Callable

from openai import AsyncOpenAI

from jarvis.config import Settings
from jarvis.db import get_conn, now_iso

logger = logging.getLogger(__name__)

MAX_FACTS = 30
MAX_FACT_CHARS = 200
MAX_SUMMARY_CHARS = 600
MAX_CONTEXT_CHARS = 1600
MAX_TRANSCRIPT_ROWS = 60
MAX_ROW_CHARS = 300

# U2.6 tendency learning: a behavioral pattern must be observed in this many
# distinct sessions before it is promoted to a user.style.* fact and starts
# shaping behavior. One odd session must never teach Jarvis a bad habit.
PROMOTE_AFTER = 3

EMPTY_CONTEXT = "(no memories yet)"

EXTRACTION_PROMPT = """You maintain the long-term memory of a personal AI assistant.
You are given the previous running summary (possibly empty) and the transcript
of one conversation session. Produce a memory update as STRICT JSON only:

{"facts": [{"key": "<dotted.key>", "value": "<one short statement>"}],
 "observations": [{"key": "user.style.<pattern>", "value": "<what was observed>"}],
 "summary": "<rewritten running summary, at most 500 characters>"}

Rules:
- Facts are durable, keyed statements worth remembering across sessions:
  the user's name, preferences, people, projects, standing decisions.
  Keys are lowercase dotted paths, e.g. "user.name", "user.preference.music",
  "project.jarvis". Resend a key with a new value to correct it.
- Anything the user EXPLICITLY states about how they want things done
  ("I prefer short answers", "stop doing that", "always ask me first")
  is a fact with a user.style.* key — record it immediately in facts,
  not observations. Explicit statements override everything inferred.
- Observations are INFERRED behavioral tendencies: how the user phrases
  requests, what they react well or badly to, formats they pick,
  pacing, tone. Keys are "user.style.<pattern>". Observations are
  evidence, not truth — record them even when unsure; they only become
  active after recurring across sessions.
- Do NOT record one-off requests, small talk, or anything time-bound
  (that is what reminders and notes are for).
- The summary must stand alone: it replaces the previous summary, so carry
  forward anything still relevant and fold in this session's essentials.
- If the session contains nothing worth remembering, return
  {"facts": [], "observations": [], "summary": "<previous summary unchanged>"}.
- Output JSON only. No markdown, no commentary."""


def render_memory_context(conn: sqlite3.Connection | None = None) -> str:
    """Build the memory block for the Supervisor system prompt.

    Facts first (most actionable), then the running summary, total size
    capped at MAX_CONTEXT_CHARS. Returns EMPTY_CONTEXT when nothing is
    stored or when the read fails.
    """
    own_connection = conn is None
    conn = conn or get_conn()
    try:
        fact_rows = conn.execute(
            "SELECT key, content FROM memories WHERE kind = 'fact' "
            "ORDER BY updated_at DESC LIMIT ?",
            (MAX_FACTS,),
        ).fetchall()
        summary_row = conn.execute(
            "SELECT content FROM memories WHERE kind = 'summary' "
            "ORDER BY updated_at DESC LIMIT 1"
        ).fetchone()
    except Exception:  # noqa: BLE001 — memory must never break the pipeline
        logger.exception("memory_context_read_failed")
        return EMPTY_CONTEXT
    finally:
        if own_connection:
            conn.close()

    lines: list[str] = []
    for row in fact_rows:
        line = f"- {row['key']}: {row['content'][:MAX_FACT_CHARS]}"
        if sum(len(l) for l in lines) + len(line) > MAX_CONTEXT_CHARS:
            break
        lines.append(line)
    if summary_row is not None:
        summary = summary_row["content"][:MAX_SUMMARY_CHARS]
        remaining = MAX_CONTEXT_CHARS - sum(len(l) for l in lines)
        if remaining > 80:
            lines.append(f"Previously discussed: {summary[:remaining]}")
    return "\n".join(lines) if lines else EMPTY_CONTEXT


def upsert_fact(
    conn: sqlite3.Connection, key: str, value: str, session_id: str | None
) -> None:
    """Insert or replace one keyed fact."""
    now = now_iso()
    conn.execute(
        "INSERT INTO memories (kind, key, content, source_session_id, "
        "created_at, updated_at) VALUES ('fact', ?, ?, ?, ?, ?) "
        "ON CONFLICT(key) WHERE kind = 'fact' "
        "DO UPDATE SET content = excluded.content, "
        "source_session_id = excluded.source_session_id, "
        "updated_at = excluded.updated_at",
        (key, value[:MAX_FACT_CHARS], session_id, now, now),
    )


def set_summary(
    conn: sqlite3.Connection, summary: str, session_id: str | None
) -> None:
    """Rewrite the single running-summary row."""
    now = now_iso()
    existing = conn.execute(
        "SELECT id FROM memories WHERE kind = 'summary' LIMIT 1"
    ).fetchone()
    if existing is None:
        conn.execute(
            "INSERT INTO memories (kind, key, content, source_session_id, "
            "created_at, updated_at) VALUES ('summary', NULL, ?, ?, ?, ?)",
            (summary[:MAX_SUMMARY_CHARS], session_id, now, now),
        )
    else:
        conn.execute(
            "UPDATE memories SET content = ?, source_session_id = ?, "
            "updated_at = ? WHERE id = ?",
            (summary[:MAX_SUMMARY_CHARS], session_id, now, existing["id"]),
        )


def add_observation(
    conn: sqlite3.Connection, key: str, value: str, session_id: str | None
) -> None:
    """Record one observed instance of an inferred behavioral tendency."""
    conn.execute(
        "INSERT INTO observations (key, content, source_session_id, "
        "created_at) VALUES (?, ?, ?, ?)",
        (key, value[:MAX_FACT_CHARS], session_id, now_iso()),
    )


def promote_observations(conn: sqlite3.Connection) -> list[str]:
    """Promote tendencies with enough evidence to user.style.* facts.

    A pattern promotes when its key has at least PROMOTE_AFTER observations
    from DISTINCT sessions. Promotion can only CREATE a fact — it never
    overwrites one. Once a fact exists for a key (typically from an explicit
    user statement), only another explicit statement may change it; inferred
    evidence never clobbers what the user actually said.
    """
    rows = conn.execute(
        "SELECT key, COUNT(DISTINCT source_session_id) AS sessions "
        "FROM observations GROUP BY key"
    ).fetchall()
    promoted: list[str] = []
    for row in rows:
        if row["sessions"] < PROMOTE_AFTER:
            continue
        fact = conn.execute(
            "SELECT 1 FROM memories WHERE kind = 'fact' AND key = ?",
            (row["key"],),
        ).fetchone()
        if fact is not None:
            continue  # explicit fact stands; inference never overwrites it
        latest = conn.execute(
            "SELECT content FROM observations WHERE key = ? "
            "ORDER BY id DESC LIMIT 1",
            (row["key"],),
        ).fetchone()
        upsert_fact(conn, row["key"], latest["content"], None)
        promoted.append(row["key"])
    return promoted


def delete_fact(conn: sqlite3.Connection, key: str) -> bool:
    """Forget one fact and its accumulated observations ('forget that' path)."""
    cur = conn.execute(
        "DELETE FROM memories WHERE kind = 'fact' AND key = ?", (key,)
    )
    conn.execute("DELETE FROM observations WHERE key = ?", (key,))
    return cur.rowcount > 0


def _session_transcript(
    conn: sqlite3.Connection, session_id: str
) -> tuple[list[sqlite3.Row], str]:
    """(recent rows for the session, previous summary or '')."""
    rows = conn.execute(
        "SELECT role, content FROM conversations WHERE session_id = ? "
        "ORDER BY id DESC LIMIT ?",
        (session_id, MAX_TRANSCRIPT_ROWS),
    ).fetchall()
    rows.reverse()
    summary_row = conn.execute(
        "SELECT content FROM memories WHERE kind = 'summary' "
        "ORDER BY updated_at DESC LIMIT 1"
    ).fetchone()
    return rows, (summary_row["content"] if summary_row else "")


def _parse_update(text: str) -> dict | None:
    """Strict-JSON parse with a markdown-fence fallback. None on failure."""
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = candidate.strip("`")
        if candidate.startswith("json"):
            candidate = candidate[4:]
    try:
        data = json.loads(candidate)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    facts = data.get("facts")
    summary = data.get("summary")
    if not isinstance(facts, list) or not isinstance(summary, str):
        return None
    clean_facts = [
        (str(f["key"]).strip(), str(f["value"]).strip())
        for f in facts
        if isinstance(f, dict) and f.get("key") and f.get("value")
    ]
    observations = data.get("observations") or []
    clean_observations = [
        (str(o["key"]).strip(), str(o["value"]).strip())
        for o in observations
        if isinstance(o, dict) and o.get("key") and o.get("value")
    ]
    return {
        "facts": clean_facts,
        "observations": clean_observations,
        "summary": summary.strip(),
    }


async def update_memory_from_session(
    settings: Settings,
    session_id: str,
    client_factory: Callable[[Settings], Any] | None = None,
) -> bool:
    """Fold one finished session into long-term memory. Never raises.

    Returns True when a parsed update was applied. Skips sessions with no
    user utterances (nothing to learn) and any failure mode (LLM error,
    malformed JSON) leaves memory untouched.
    """
    try:
        with get_conn() as conn:
            rows, previous_summary = _session_transcript(conn, session_id)
        if not any(r["role"] == "user" for r in rows):
            return False

        transcript = "\n".join(
            f"{r['role'].upper()}: {r['content'][:MAX_ROW_CHARS]}" for r in rows
        )
        client = (
            client_factory(settings)
            if client_factory is not None
            else AsyncOpenAI(
                api_key=settings.openai_api_key,
                base_url=settings.openai_base_url,
            )
        )
        response = await client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": EXTRACTION_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Previous summary:\n{previous_summary or '(none)'}\n\n"
                        f"Session transcript:\n{transcript}"
                    ),
                },
            ],
        )
        update = _parse_update(response.choices[0].message.content or "")
        if update is None:
            logger.warning("memory_update_unparseable session=%s", session_id)
            return False

        with get_conn() as conn:
            for key, value in update["facts"]:
                upsert_fact(conn, key, value, session_id)
            for key, value in update["observations"]:
                add_observation(conn, key, value, session_id)
            promoted = promote_observations(conn)
            if update["summary"]:
                set_summary(conn, update["summary"], session_id)
        logger.info(
            "memory_updated session=%s facts=%d observations=%d promoted=%s",
            session_id, len(update["facts"]), len(update["observations"]),
            promoted,
        )
        return True
    except Exception:  # noqa: BLE001 — memory must never break the pipeline
        logger.exception("memory_update_failed session=%s", session_id)
        return False
