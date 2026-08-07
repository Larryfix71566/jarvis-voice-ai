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

EMPTY_CONTEXT = "(no memories yet)"

EXTRACTION_PROMPT = """You maintain the long-term memory of a personal AI assistant.
You are given the previous running summary (possibly empty) and the transcript
of one conversation session. Produce a memory update as STRICT JSON only:

{"facts": [{"key": "<dotted.key>", "value": "<one short statement>"}],
 "summary": "<rewritten running summary, at most 500 characters>"}

Rules:
- Facts are durable, keyed statements worth remembering across sessions:
  the user's name, preferences, people, projects, standing decisions.
  Keys are lowercase dotted paths, e.g. "user.name", "user.preference.music",
  "project.jarvis". Resend a key with a new value to correct it.
- Do NOT record one-off requests, small talk, or anything time-bound
  (that is what reminders and notes are for).
- The summary must stand alone: it replaces the previous summary, so carry
  forward anything still relevant and fold in this session's essentials.
- If the session contains nothing worth remembering, return
  {"facts": [], "summary": "<previous summary unchanged>"}.
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
    return {"facts": clean_facts, "summary": summary.strip()}


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
            if update["summary"]:
                set_summary(conn, update["summary"], session_id)
        logger.info(
            "memory_updated session=%s facts=%d", session_id, len(update["facts"])
        )
        return True
    except Exception:  # noqa: BLE001 — memory must never break the pipeline
        logger.exception("memory_update_failed session=%s", session_id)
        return False
