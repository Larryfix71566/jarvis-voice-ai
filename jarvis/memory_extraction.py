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

import hashlib
import json
import logging
import os
from typing import Any, Callable

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
from jarvis.memory_model import make_memory_async_client
from jarvis.model_execution import (
    ModelContextMessage,
    ModelExecutionRequest,
    execute_chat,
)
from jarvis.model_routing import ModelRouteError, make_route_client
from jarvis.privacy_policy import DataPolicy
from jarvis.procedures import _overlap_score, _tokens
from jarvis.usage_ledger import (
    provider_from_base_url,
    record_completion,
    record_execution_result,
)

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
- Only the USER line is evidence. MORTIMER's reply is there to help you
  understand the user; never record something only Mortimer said. His
  greetings, summaries and status reports repeat what memory already
  holds, and recording them turns an old fact into a "new" one.
- Never record where the user is right now (user.location,
  user.location.current): the location comes from the user's device.
  Asking about a place (its weather, news or time) does not mean the user
  is there. Durable places the user states (home, office) are fine under
  their own keys.
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


# MORTIMER_VOICE_WORKFLOWS_PLAN.md D-L7 (Larry, 2026-09-25) — the
# Spartanburg loop. Mortimer's greeting read "here in Spartanburg" from
# the identity memory user.location; the extractor then took that greeting
# as the user restating it. 8 of the 10 recorded rewrites of user.location
# (memory_recall_events) came from exchanges where "Spartanburg" was only
# in Mortimer's reply ("Hello?" -> "Hey Larry. It's two fifteen PM here in
# Spartanburg."), and 83 refreshes of user.name the same way. The prompt
# rule above asks the model not to; this check makes it hold regardless.
# A fact is an echo when its words appear in the reply and none appear in
# the user's line. Words match on their first ECHO_STEM_CHARS characters,
# so "availability" still counts as the user's "available". Replayed over
# the 150 logged extractions with a known source turn (2026-09-25), the
# echo check alone rejects 102: 95 greeting echoes (user.name,
# user.location, user.location.timezone) and 7 facts built from Mortimer's
# own status reports or explanations. With CURRENT_LOCATION_KEYS as well,
# 104 are rejected (93 echoes + all 11 user.location rows) and 46 admitted.
ECHO_STEM_CHARS = 5
# D-L6: where the user is right now comes from the device, never memory.
CURRENT_LOCATION_KEYS = frozenset({"user.location", "user.location.current"})


def echo_guard_enabled() -> bool:
    """Kill switch (env-only rollback), default on."""
    raw = os.environ.get("JARVIS_MEMORY_ECHO_GUARD", "true").strip().lower()
    return raw not in ("false", "0", "no", "off")


def _stems(text: str) -> set[str]:
    return {t[:ECHO_STEM_CHARS] for t in _tokens(text)}


def source_exchange(conn, assistant_turn_id: int | None) -> dict | None:
    """The exchange a fact was extracted from, as the worker paired it.

    `source_turn` on a fact (and on a memory_recall_events row) is the id
    of the ASSISTANT row that closed the exchange (memory_extraction_worker
    passes row["id"] of the assistant turn). Its user half is the latest
    user row of the same session before it, provided no other assistant
    row came in between (that reply would have consumed it). Returns
    {"session_id", "user_turn", "assistant_turn", "user", "assistant"}, or
    None when the turn is missing, is not an assistant row, or has no user
    half. Read-only; used by the W10 settle check and the D1 replay."""
    if assistant_turn_id is None:
        return None
    reply = conn.execute(
        "SELECT id, session_id, role, content FROM conversations WHERE id = ?",
        (int(assistant_turn_id),),
    ).fetchone()
    if reply is None or reply["role"] != "assistant":
        return None
    user = conn.execute(
        "SELECT id, content FROM conversations WHERE session_id = ? AND id < ? "
        "AND role = 'user' ORDER BY id DESC LIMIT 1",
        (reply["session_id"], reply["id"]),
    ).fetchone()
    if user is None:
        return None
    between = conn.execute(
        "SELECT 1 FROM conversations WHERE session_id = ? AND id > ? AND id < ? "
        "AND role = 'assistant' LIMIT 1",
        (reply["session_id"], user["id"], reply["id"]),
    ).fetchone()
    if between is not None:
        return None
    return {"session_id": reply["session_id"], "user_turn": user["id"],
            "assistant_turn": reply["id"], "user": user["content"],
            "assistant": reply["content"]}


def echoes_reply(value: str, user_content: str, assistant_content: str) -> bool:
    """D-L7 — True when the fact's words come from Mortimer, not the user."""
    words = _stems(value)
    return bool(words & _stems(assistant_content)) and not (words & _stems(user_content))


def extractor_rejection(key: str, value: str, user_content: str,
                        assistant_content: str) -> str | None:
    """The reason this exchange may not produce this fact, or None."""
    if not echo_guard_enabled():
        return None
    if (key or "").strip().lower() in CURRENT_LOCATION_KEYS:
        return "current_location"
    if echoes_reply(value, user_content, assistant_content):
        return "echo_of_reply"
    return None


def filter_echo_candidates(candidates: dict, user_content: str,
                           assistant_content: str) -> dict:
    """Drop reply echoes/current-location facts before durable classification.

    The admission worker calls this immediately after extraction and before it
    persists candidates, so rejected content never reaches the durable queue's
    classifier stage. Observations are retained here; their provenance/evidence
    is independently validated by the admission classifier.
    """
    facts = []
    for item in candidates.get("facts", []):
        key = item.get("key", "")
        value = item.get("value", "")
        reason = extractor_rejection(key, value, user_content, assistant_content)
        if reason is None:
            facts.append(item)
        else:
            logger.info("memory_write_rejected kind=fact reason=%s", reason)
    return {"facts": facts, "observations": list(candidates.get("observations", []))}


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


def _parse_candidates_strict(text: str) -> dict[str, list[dict[str, str]]]:
    """Parse a complete bounded candidate batch for durable staging.

    Unlike the legacy direct-write parser, this rejects the whole response if
    any row is malformed, duplicated, oversized, or carries extra fields.
    """
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = candidate.strip("`").strip()
        if candidate.startswith("json"):
            candidate = candidate[4:].strip()
    try:
        data = json.loads(candidate)
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError("memory candidate response is not valid JSON") from exc
    if not isinstance(data, dict) or set(data) != {"facts", "observations"}:
        raise ValueError("memory candidate response fields do not match contract")
    result: dict[str, list[dict[str, str]]] = {"facts": [], "observations": []}
    all_keys: set[str] = set()
    total_chars = 0
    for group in ("facts", "observations"):
        items = data[group]
        if not isinstance(items, list):
            raise ValueError("memory candidate groups must be arrays")
        for item in items:
            if (not isinstance(item, dict) or set(item) != {"key", "value"}
                    or not isinstance(item["key"], str)
                    or not isinstance(item["value"], str)):
                raise ValueError("memory candidate row does not match contract")
            key, value = item["key"].strip(), item["value"].strip()
            if not key or not value or len(key) > 120 or len(value) > 300:
                raise ValueError("memory candidate row is empty or oversized")
            if key in all_keys:
                raise ValueError("memory candidate keys must be unique")
            all_keys.add(key)
            total_chars += len(key) + len(value)
            result[group].append({"key": key, "value": value})
    if sum(map(len, result.values())) > 20 or total_chars > 12_000:
        raise ValueError("memory candidate batch exceeds staging bounds")
    return result


async def _request_exchange_candidate_text(
    settings: Settings, session_id: str, user_content: str,
    assistant_content: str, source_turn: int | None,
    client_factory: Callable[[Settings], Any] | None = None,
    *, require_confidential_route: bool = False,
) -> str:
    """Call the configured confidential memory route and return raw JSON text."""
    if require_confidential_route:
        if client_factory is not None:
            raise RuntimeError("test client injection cannot prove a confidential route")
        from jarvis.memory_model import resolve_memory_route
        from jarvis.privacy_policy import assert_route_allowed

        preflight = resolve_memory_route(settings)
        if preflight.resolved is None:
            raise RuntimeError("durable memory admission requires a verified confidential route")
        assert_route_allowed(
            preflight.resolved.route,
            DataPolicy("confidential", "memory-extraction-candidates"),
        )
    exchange_text = f"USER: {user_content[:MAX_ROW_CHARS]}"
    if assistant_content:
        exchange_text += f"\nMORTIMER: {assistant_content[:MAX_ROW_CHARS]}"
    if require_confidential_route:
        client = make_route_client(preflight.resolved, timeout=60, max_retries=0)
        model = preflight.model
        resolved = preflight.resolved
    elif client_factory is not None:
        client = client_factory(settings)
        model = settings.openai_model
        resolved = None
    else:
        client, route = make_memory_async_client(settings)
        model = route.model
        resolved = route.resolved
    if require_confidential_route:
        if resolved is None:
            raise RuntimeError("durable memory admission requires a verified confidential route")
        from jarvis.privacy_policy import assert_route_allowed
        assert_route_allowed(
            resolved.route, DataPolicy("confidential", "memory-extraction-candidates")
        )
    if resolved is not None:
        request_id = hashlib.sha256(
            f"{session_id}:{source_turn}".encode("utf-8")
        ).hexdigest()[:24]
        execution = await execute_chat(
            ModelExecutionRequest(
                workload=resolved.workload,
                task_id=f"memory-extraction:{request_id}",
                parent_request_id=f"memory-extraction:{request_id}",
                instructions=exchange_text,
                context=(ModelContextMessage(
                    "system", EXCHANGE_EXTRACTION_PROMPT,
                    DataPolicy("confidential", "memory-extraction-prompt"),
                ),),
                data_policy=DataPolicy("confidential", "conversation-exchange"),
                timeout_s=30.0,
            ),
            resolved,
            client_factory=lambda _: client,
        )
        record_execution_result("memory_extraction", execution, session_id=session_id)
        return execution.text

    # Compatibility path for routing-disabled installs and injected tests.
    response = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": EXCHANGE_EXTRACTION_PROMPT},
            {"role": "user", "content": exchange_text},
        ],
    )
    try:
        record_completion(
            rung="memory_extraction",
            provider=provider_from_base_url(str(client.base_url)),
            model=model,
            response=response,
            session_id=session_id,
        )
    except Exception:
        pass
    return response.choices[0].message.content or ""


async def extract_candidates_from_exchange(
    settings: Settings, session_id: str, user_content: str,
    assistant_content: str, assistant_turn_id: int,
    client_factory: Callable[[Settings], Any] | None = None,
) -> dict[str, list[dict[str, str]]]:
    """Extract a strictly validated candidate batch without writing memory."""
    # Durable admission candidates are extracted from the user's own turn
    # only. Mortimer's answer can help the legacy novelty extractor, but it
    # is not evidence that the user stated a preference or fact.
    del assistant_content
    result_text = await _request_exchange_candidate_text(
        settings, session_id, user_content, "",
        assistant_turn_id, client_factory,
        require_confidential_route=True,
    )
    return _parse_candidates_strict(result_text)


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
    except Exception as exc:  # noqa: BLE001 — never break an admission over a metric
        logger.warning(
            "memory_recall_event_write_failed error_type=%s",
            type(exc).__name__,
        )


def admit_fact_candidate(conn, key: str, value: str, session_id: str | None,
                          source_turn: int | None, *,
                          evidence_turn_id: int | None = None,
                          enqueue_classification: bool = True) -> str:
    """One fact candidate through the novelty gate, then to the store.
    Returns 'rejected' | 'exact_update' | 'near_duplicate:<matched_key>'
    | 'inserted' — outcomes are strings so tests and the worker's own
    logging can assert on them without a second enum to keep in sync."""
    reason = scan_memory_content(key) or scan_memory_content(value)
    if reason is not None:
        logger.warning(
            "memory_write_rejected kind=fact reason=%s",
            reason,
        )
        return "rejected"
    if _is_volatile_state(key, value):
        logger.warning(
            "memory_write_rejected kind=fact reason=volatile_state",
        )
        return "rejected"

    match, is_exact = _find_fact_match(conn, key, value)
    if is_exact:
        upsert_fact(conn, key, value, session_id, source_turn_id=evidence_turn_id,
                    enqueue_classification=enqueue_classification)
        _touch_recurrence(conn, "memories", match["id"], source_turn, bump=True)
        # Stage A3: the stored fact's key, not the candidate's — for an
        # exact match they are the same, for a near-duplicate they are not,
        # and what we want to know is which STORED fact went unrecalled.
        _record_recall_event(conn, match["key"], "exact_update",
                             session_id, evidence_turn_id if evidence_turn_id is not None else source_turn)
        return "exact_update"
    if match is not None:
        _touch_recurrence(conn, "memories", match["id"], source_turn, bump=True)
        logger.info(
            "memory_novelty_gate kind=fact outcome=near_duplicate",
        )
        _record_recall_event(conn, match["key"], "near_duplicate",
                             session_id, evidence_turn_id if evidence_turn_id is not None else source_turn)
        return f"near_duplicate:{match['key']}"

    upsert_fact(conn, key, value, session_id, source_turn_id=evidence_turn_id,
                enqueue_classification=enqueue_classification)
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
            "memory_write_rejected kind=observation reason=%s",
            reason,
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


async def extract_candidates(
    settings: Settings,
    session_id: str,
    user_content: str,
    assistant_content: str,
    client_factory: Callable[[Settings], Any] | None = None,
) -> dict | None:
    """The model half of extract_from_exchange: the candidates one
    exchange yields, or None when the reply is unparseable. Writes nothing
    to memory. Raises on a failed model call (the caller decides). Split
    out for scripts/replay_extraction.py (MORTIMER_VOICE_WORKFLOWS_PLAN.md
    D1), which must decide the writes itself."""
    exchange_text = (
        f"USER: {user_content}\n"
        f"MORTIMER: {assistant_content}"
    )
    if client_factory is not None:
        # Test seam only; production uses JARVIS_MEMORY_PROFILE.
        client = client_factory(settings)
        model = settings.openai_model
        resolved = None
    else:
        client, route = make_memory_async_client(settings)
        model = route.model
        resolved = getattr(route, "resolved", None)
    if resolved is not None:
        # This is the replay extractor, not the normal worker's separately
        # protected durable-admission path. Keep its exact source policy even
        # if configuration or a saved route preference claims a weaker level.
        request_id = hashlib.sha256(
            f"{session_id}:{exchange_text}".encode("utf-8")
        ).hexdigest()[:24]
        request = ModelExecutionRequest(
            workload=resolved.workload,
            task_id=f"memory-replay:{request_id}",
            parent_request_id=f"memory-replay:{request_id}",
            instructions=exchange_text,
            context=(ModelContextMessage(
                "system", EXCHANGE_EXTRACTION_PROMPT,
                DataPolicy("confidential", "memory-replay-prompt"),
            ),),
            data_policy=DataPolicy("confidential", "replayed-conversation-exchange"),
            timeout_s=30.0,
        )
        try:
            execution = await execute_chat(request, resolved, client_factory=lambda _: client)
        except ModelRouteError:
            raise  # policy errors already contain only trusted route/source metadata
        except Exception as exc:  # noqa: BLE001 — replay's caller prints exception strings
            raise RuntimeError(
                f"memory replay model call failed (error_type={type(exc).__name__[:64]})"
            ) from None
        try:
            record_execution_result("memory_extraction", execution, session_id=session_id)
        except Exception as exc:  # noqa: BLE001 — accounting never masks a valid extraction
            logger.warning("memory_replay_usage_record_failed error_type=%s", type(exc).__name__[:64])
        result_text = execution.text
    else:
        # Preserve routing-off behavior and the existing direct-client test
        # seam. This compatibility branch does not assert confidentiality.
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": EXCHANGE_EXTRACTION_PROMPT},
                {"role": "user", "content": exchange_text},
            ],
        )
        try:
            record_completion(
                rung="memory_extraction",
                provider=provider_from_base_url(str(client.base_url)),
                model=model,
                response=response,
                session_id=session_id,
            )
        except Exception:
            pass
        result_text = response.choices[0].message.content or ""
    return _parse_candidates(result_text)


async def extract_from_exchange(
    settings: Settings,
    session_id: str,
    user_content: str,
    assistant_content: str,
    source_turn: int | None,
    client_factory: Callable[[Settings], Any] | None = None,
    *, user_turn_id: int | None = None,
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
        result_text = await _request_exchange_candidate_text(
            settings, session_id, user_content, assistant_content,
            source_turn, client_factory,
        )
        parsed = _parse_candidates(result_text)
        if parsed is None:
            logger.warning(
                "memory_extraction_unparseable",
            )
            return {"facts": 0, "observations": 0, "outcomes": [], "promoted": []}

        outcomes: list[tuple[str, str, str]] = []
        conn = get_conn()
        try:
            for key, value in parsed["facts"]:
                reason = extractor_rejection(key, value, user_content, assistant_content)
                if reason is not None:
                    logger.warning(
                        "memory_write_rejected kind=fact key=%s reason=%s session=%s "
                        "source_turn=%s", key, reason, session_id, source_turn,
                    )
                    outcomes.append(("fact", key, "rejected"))
                    continue
                outcomes.append(
                    ("fact", key, admit_fact_candidate(
                        conn, key, value, session_id, source_turn,
                        evidence_turn_id=user_turn_id,
                    ))
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
            "memory_exchange_extracted facts=%d observations=%d",
            len(parsed["facts"]), len(parsed["observations"]),
        )
        return {
            "facts": len(parsed["facts"]),
            "observations": len(parsed["observations"]),
            "outcomes": outcomes,
            "promoted": promoted,
        }
    except Exception as exc:  # noqa: BLE001 — one bad exchange must never wedge the worker
        logger.warning(
            "memory_extraction_failed error_type=%s",
            type(exc).__name__,
        )
        return {"facts": 0, "observations": 0, "outcomes": [], "promoted": [], "error": True}
