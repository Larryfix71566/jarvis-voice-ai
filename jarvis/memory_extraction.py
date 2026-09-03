"""jarvis/memory_extraction.py — Phase 2 per-exchange candidate
extraction + novelty gate (MORTIMER_OPTIMIZATION_PLAN.md Phase 2,
"Extraction Gate").

Companion to jarvis/memory.py, not a replacement for it. jarvis.memory's
`update_memory_from_session` reviews a whole TRANSCRIPT WINDOW (up to
MAX_TRANSCRIPT_ROWS) on a periodic tick or at session teardown; this
module is called once per FINISHED EXCHANGE (one user utterance + one
Mortimer reply) by the new standalone jarvis/memory_extraction_worker.py
service. Summary regeneration stays with jarvis.memory's existing path
entirely -- a running summary is inherently a whole-session digest, the
plan's Phase 2 section never mentions it, and regenerating it once per
exchange would be wasteful for no benefit. Only facts/observations
extraction moves here.

Why a second extraction path instead of just calling
update_memory_from_session more often: the plan's own goal is "stop
treating every utterance as memory... shrink the candidate pool AT THE
SOURCE" -- finer-grained, single-exchange extraction is what makes a
novelty gate possible in the first place. A 60-row window re-scanned
every 5 minutes has already blurred together everything worth deduping
against by the time it reaches the LLM.

THE NOVELTY GATE (task 3) is the actual point of this module. Today,
jarvis.memory.upsert_fact only dedupes on an EXACT key match; two facts
meaning the same thing under different keys ("dark roast" under
project.coffee vs a fresh user.preference.coffee) both get written, and
jarvis.consolidate's sweep-time merge is the only thing that ever
notices -- after both are already written, already competing for a tier
cap, and possibly already reaching the Supervisor's context. This module
moves that check to WRITE time: before admitting a candidate, it looks
for a near-duplicate (same tier, token-overlap >= consolidate.py's own
DUPLICATE_THRESHOLD -- reusing that module's constant and jarvis.
procedures' `_tokens`/`_overlap_score`, the ONE tokenizer/scorer this
repo already shares between procedures.py and consolidate.py, not a
second implementation) and, if found, bumps that existing row's
recurrence_count/last_seen_at/source_turn instead of writing a sibling.
Exact-key matches still go through jarvis.memory.upsert_fact's existing
correction semantics unchanged (resending a key updates its content);
the near-duplicate path never touches an existing row's content, only
its recurrence bookkeeping -- corroborating evidence, not a rewrite.

Known, deliberate scope limits (not attempted here):
  - The novelty gate for OBSERVATIONS only dedupes WITHIN one (key,
    session_id) pair. Cross-session dedup is left alone on purpose:
    jarvis.memory.promote_observations counts DISTINCT SESSIONS, and
    collapsing rows across sessions would corrupt that count -- one
    tendency mentioned in 3 different sessions must still look like 3
    distinct sessions to the promotion check. What this gate prevents is
    the SAME tendency, mentioned 3 times in one long session, inflating
    to 3 rows for no reason.
  - Cross-KEY near-duplicate merging for still-staged (unpromoted)
    observations is not attempted -- only for facts. An observation's
    key is already narrower (user.style.<pattern>) and short-lived by
    design (staging, not durable); consolidate.py's downstream merge
    operates on promoted preference-tier facts, so a genuine cross-key
    observation duplicate is a real, documented gap, left for a future
    pass if it proves to matter in practice.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable

from openai import AsyncOpenAI

from jarvis.config import Settings
from jarvis.consolidate import DUPLICATE_THRESHOLD
from jarvis.db import get_conn, now_iso
from jarvis.memory import (
    MAX_ROW_CHARS,
    _is_volatile_state,
    add_observation,
    infer_tier,
    promote_observations,
    scan_memory_content,
    upsert_fact,
)
from jarvis.procedures import _overlap_score, _tokens
from jarvis.usage_ledger import provider_from_base_url, record_completion

logger = logging.getLogger(__name__)

EXCHANGE_EXTRACTION_PROMPT = """You maintain the long-term memory of a personal AI assistant, working
one conversational exchange at a time instead of reviewing a whole
session. You are given ONE user utterance and Mortimer's reply to it.
Produce a memory update as STRICT JSON only:

{"facts": [{"key": "<dotted.key>", "value": "<one short statement>"}],
 "observations": [{"key": "user.style.<pattern>", "value": "<what was observed>"}]}

Rules:
- Facts are durable, keyed statements worth remembering across sessions:
  the user's name, preferences, people, projects, standing decisions.
  Keys are lowercase dotted paths, e.g. "user.name", "user.preference.music",
  "project.jarvis". Resend a key with a new value to correct it.
- Anything the user EXPLICITLY states about how they want things done
  ("I prefer short answers", "stop doing that", "always ask me first")
  is a fact with a user.style.* key — record it immediately in facts,
  not observations. Explicit statements override everything inferred.
- Observations are INFERRED behavioral tendencies visible in just this
  one exchange: how the user phrased the request, what they reacted to,
  formats they picked, pacing, tone. Keys are "user.style.<pattern>".
  Record them even when unsure from one exchange alone — they only
  become active after recurring across multiple exchanges/sessions.
- This exchange may be a command (a tool ran, a task executed) rather
  than conversation — extract exactly the same way regardless. A durable
  fact mentioned in passing while a command executes ("remind me at 5,
  by the way I start a new job Monday") is still a fact worth recording.
- NEVER record facts or observations about the assistant's own capabilities,
  access rights, or restrictions (e.g. "cannot edit code", "no repository
  access"). Capabilities change with every software update; remembered
  restrictions become stale lies that contradict the current system prompt.
- Do NOT record one-off requests, small talk, or anything time-bound
  (that is what reminders and notes are for) or anything only true right
  now (a git branch, a file count, "3 tabs open") — that is stale within
  hours and re-derivable on demand.
- If this exchange has nothing worth remembering, return
  {"facts": [], "observations": []}.
- Output JSON only. No markdown, no commentary."""


def _parse_candidates(text: str) -> dict | None:
    """Strict-JSON parse with a markdown-fence fallback. None on failure.
    Same contract as jarvis.memory._parse_update minus the summary field
    (a single exchange has no session-level summary to carry)."""
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
    observations = data.get("observations") or []
    if not isinstance(facts, list) or not isinstance(observations, list):
        return None
    clean_facts = [
        (str(f["key"]).strip(), str(f["value"]).strip())
        for f in facts
        if isinstance(f, dict) and f.get("key") and f.get("value")
    ]
    clean_observations = [
        (str(o["key"]).strip(), str(o["value"]).strip())
        for o in observations
        if isinstance(o, dict) and o.get("key") and o.get("value")
    ]
    return {"facts": clean_facts, "observations": clean_observations}


def _touch_recurrence(conn, table: str, row_id: int, source_turn: int | None, *, bump: bool) -> None:
    """Refresh last_seen_at/source_turn on an existing row by id (never by
    key — observations can have several rows sharing one key, one per
    session, and only the specific matched row should move). bump=True
    also increments recurrence_count: both an exact-key rewrite and a
    near-duplicate match are "we saw this again", not a fresh candidate."""
    now = now_iso()
    if bump:
        conn.execute(
            f"UPDATE {table} SET recurrence_count = recurrence_count + 1, "
            f"last_seen_at = ?, source_turn = ? WHERE id = ?",
            (now, source_turn, row_id),
        )
    else:
        conn.execute(
            f"UPDATE {table} SET last_seen_at = ?, source_turn = ? WHERE id = ?",
            (now, source_turn, row_id),
        )


def _find_fact_match(conn, key: str, value: str):
    """(row, is_exact) for the existing fact this candidate should attach
    to, or (None, False) if it is genuinely new. Exact key match always
    wins (jarvis.memory.upsert_fact's existing correction semantics).
    Failing that, a same-tier, token-overlap match at or above
    consolidate.py's DUPLICATE_THRESHOLD is a recurrence of that fact
    under a different name. Never crosses tiers (consolidate.py's own
    rule 1 — a preference and a project fact that share words are not
    the same fact)."""
    exact = conn.execute(
        "SELECT * FROM memories WHERE kind='fact' AND key=? AND archived_at IS NULL",
        (key,),
    ).fetchone()
    if exact is not None:
        return exact, True
    tier = infer_tier(key)
    same_tier = conn.execute(
        "SELECT * FROM memories WHERE kind='fact' AND COALESCE(tier,'project')=? "
        "AND archived_at IS NULL",
        (tier,),
    ).fetchall()
    value_tokens = _tokens(value)
    best, best_score = None, 0.0
    for row in same_tier:
        score = _overlap_score(value_tokens, _tokens(row["content"]))
        if score >= DUPLICATE_THRESHOLD and score > best_score:
            best, best_score = row, score
    return best, False


def _record_recall_event(conn, key: str, outcome: str, session_id: str | None,
                         source_turn: int | None) -> None:
    """MORTIMER_OPTIMIZATION_PLAN.md Phase 4 Rev 3.4 Stage A3 — one row per
    RESTATED fact (the user told Mortimer something the store already had).
    Phase 4 Stage B is gated on this rate; see migration 0019's comment for
    why a restatement is a proxy rather than proof. Best-effort by design:
    an instrumentation write must never cost a real memory write, so a
    failure here is logged and swallowed. Shares the caller's connection
    and transaction — it is part of the same admission, not a side trip."""
    try:
        conn.execute(
            "INSERT INTO memory_recall_events "
            "(session_id, source_turn, key, outcome, created_at) "
            "VALUES (?,?,?,?,?)",
            (session_id, source_turn, key, outcome, now_iso()),
        )
    except Exception:  # noqa: BLE001 — never break an admission over a metric
        logger.warning("memory_recall_event_write_failed key=%s", key, exc_info=True)


def admit_fact_candidate(conn, key: str, value: str, session_id: str | None,
                          source_turn: int | None) -> str:
    """One fact candidate through the novelty gate, then to the store.
    Returns 'rejected' | 'exact_update' | 'near_duplicate:<matched_key>'
    | 'inserted' — outcomes are strings so tests and the worker's own
    logging can assert on them without a second enum to keep in sync."""
    reason = scan_memory_content(key) or scan_memory_content(value)
    if reason is not None:
        logger.warning(
            "memory_write_rejected kind=fact key=%s reason=%s session=%s",
            key, reason, session_id,
        )
        return "rejected"
    if _is_volatile_state(key, value):
        logger.warning(
            "memory_write_rejected kind=fact key=%s reason=volatile_state session=%s",
            key, session_id,
        )
        return "rejected"

    match, is_exact = _find_fact_match(conn, key, value)
    if is_exact:
        upsert_fact(conn, key, value, session_id)
        _touch_recurrence(conn, "memories", match["id"], source_turn, bump=True)
        # Stage A3: the stored fact's key, not the candidate's — for an
        # exact match they are the same, for a near-duplicate they are not,
        # and what we want to know is which STORED fact went unrecalled.
        _record_recall_event(conn, match["key"], "exact_update",
                             session_id, source_turn)
        return "exact_update"
    if match is not None:
        _touch_recurrence(conn, "memories", match["id"], source_turn, bump=True)
        logger.info(
            "memory_novelty_gate kind=fact key=%s matched=%s session=%s",
            key, match["key"], session_id,
        )
        _record_recall_event(conn, match["key"], "near_duplicate",
                             session_id, source_turn)
        return f"near_duplicate:{match['key']}"

    upsert_fact(conn, key, value, session_id)
    row = conn.execute(
        "SELECT id FROM memories WHERE kind='fact' AND key=?", (key,)
    ).fetchone()
    _touch_recurrence(conn, "memories", row["id"], source_turn, bump=False)
    return "inserted"


def _find_observation_match(conn, key: str, value: str, session_id: str | None):
    """Within-(key, session) novelty check only — see the module docstring
    for why cross-session dedup is deliberately NOT done here."""
    rows = conn.execute(
        "SELECT * FROM observations WHERE key=? AND source_session_id=?",
        (key, session_id),
    ).fetchall()
    value_tokens = _tokens(value)
    best, best_score = None, 0.0
    for row in rows:
        score = _overlap_score(value_tokens, _tokens(row["content"]))
        if score >= DUPLICATE_THRESHOLD and score > best_score:
            best, best_score = row, score
    return best


def admit_observation_candidate(conn, key: str, value: str, session_id: str | None,
                                 source_turn: int | None) -> str:
    """Returns 'rejected' | 'within_session_duplicate' | 'inserted'."""
    reason = scan_memory_content(key) or scan_memory_content(value)
    if reason is not None:
        logger.warning(
            "memory_write_rejected kind=observation key=%s reason=%s session=%s",
            key, reason, session_id,
        )
        return "rejected"

    match = _find_observation_match(conn, key, value, session_id)
    if match is not None:
        _touch_recurrence(conn, "observations", match["id"], source_turn, bump=True)
        return "within_session_duplicate"

    add_observation(conn, key, value, session_id)
    row = conn.execute(
        "SELECT id FROM observations WHERE key=? AND source_session_id=? "
        "ORDER BY id DESC LIMIT 1",
        (key, session_id),
    ).fetchone()
    _touch_recurrence(conn, "observations", row["id"], source_turn, bump=False)
    return "inserted"


async def extract_from_exchange(
    settings: Settings,
    session_id: str,
    user_content: str,
    assistant_content: str,
    source_turn: int | None,
    client_factory: Callable[[Settings], Any] | None = None,
) -> dict:
    """One finished exchange in, candidates admitted. Never raises —
    mirrors jarvis.memory.update_memory_from_session's safety discipline
    exactly: a failure here must never break the worker's poll loop, and
    the worker has no voice pipeline to protect but the same principle
    applies to not wedging the poll loop on one bad exchange.

    Returns a small dict for logging/tests:
    {"facts": n, "observations": n, "outcomes": [...], "promoted": [...]}
    (or {"error": True} alongside zeroed counts on failure)."""
    try:
        exchange_text = (
            f"USER: {user_content[:MAX_ROW_CHARS]}\n"
            f"MORTIMER: {assistant_content[:MAX_ROW_CHARS]}"
        )
        client = (
            client_factory(settings) if client_factory is not None
            else AsyncOpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url)
        )
        response = await client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": EXCHANGE_EXTRACTION_PROMPT},
                {"role": "user", "content": exchange_text},
            ],
        )
        try:
            record_completion(
                rung="memory_extraction",
                provider=provider_from_base_url(str(client.base_url)),
                model=settings.openai_model,
                response=response,
                session_id=session_id,
            )
        except Exception:
            pass

        parsed = _parse_candidates(response.choices[0].message.content or "")
        if parsed is None:
            logger.warning(
                "memory_extraction_unparseable session=%s source_turn=%s",
                session_id, source_turn,
            )
            return {"facts": 0, "observations": 0, "outcomes": [], "promoted": []}

        outcomes: list[tuple[str, str, str]] = []
        conn = get_conn()
        try:
            for key, value in parsed["facts"]:
                outcomes.append(
                    ("fact", key, admit_fact_candidate(conn, key, value, session_id, source_turn))
                )
            for key, value in parsed["observations"]:
                outcomes.append(
                    ("observation", key,
                     admit_observation_candidate(conn, key, value, session_id, source_turn))
                )
            promoted = promote_observations(conn) if outcomes else []
            conn.commit()
        finally:
            conn.close()

        logger.info(
            "memory_exchange_extracted session=%s source_turn=%s facts=%d "
            "observations=%d promoted=%s",
            session_id, source_turn, len(parsed["facts"]), len(parsed["observations"]),
            promoted,
        )
        return {
            "facts": len(parsed["facts"]),
            "observations": len(parsed["observations"]),
            "outcomes": outcomes,
            "promoted": promoted,
        }
    except Exception:  # noqa: BLE001 — one bad exchange must never wedge the worker
        logger.exception(
            "memory_extraction_failed session=%s source_turn=%s", session_id, source_turn
        )
        return {"facts": 0, "observations": 0, "outcomes": [], "promoted": [], "error": True}
