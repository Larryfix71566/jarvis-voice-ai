"""jarvis/memory_extraction_worker.py — Phase 2 standalone per-exchange
memory extraction service (MORTIMER_OPTIMIZATION_PLAN.md Phase 2,
"Extraction Gate", task 1: "Async post-turn extraction worker — new
service (Procfile entry now, launchd later)").

Companion to jarvis/memory_extraction.py, which does the actual candidate
extraction + novelty gate for ONE finished exchange. This module's whole
job is turning the conversations table into a stream of finished exchanges
and feeding them there, as its own long-lived process (own Procfile line,
not an in-process asyncio task started by the bot the way
jarvis/bot/memory_watcher.py's MemorySweepWatcher is) — Larry's explicit
choice (2026-09-02) of a full rearchitecture over a narrower "close the
gaps in the existing watcher" alternative.

THE PAIRING PROBLEM this module exists to solve: conversations rows are
role-tagged (user | assistant | tool) but nothing marks which user row a
given assistant row replies to, or which rows have already been turned
into an exchange. A single global watermark (memory_extraction_cursor,
migration 0016) is enough to say "everything up to here has been looked
at", but NOT enough on its own to say "everything up to here has been
correctly PAIRED" — a user row's assistant reply can land in a LATER poll
(ordinary latency), or never land at all: jarvis/bot/transcript_log.py's
P2/P6 privacy gate deliberately never persists a sensitive assistant
reply, so a dangling user row with no reply ever coming is DESIGNED
behavior of this codebase, not a rare glitch. A cursor that blocks
advancement until a pairing resolves would stall the very first time that
gate fires — and since the cursor is global, it would stall extraction
for every OTHER session too, not just the one with the dangling turn.

The fix (migration 0017, memory_extraction_pending): track the one
open/unresolved user turn per session in its OWN small table, separate
from the cursor. The cursor advances unconditionally, every poll, to the
last row id fetched. Pairing state survives across polls (and worker
restarts) by living in the pending table rather than in this process's
memory. A pending row older than ORPHAN_TIMEOUT_S is dropped, ungracefully
but deliberately: giving up on it matches the pipeline's own privacy
intent (if the reply side was never safe to persist, extracting from the
lone user question isn't obviously safer either), and losing one
extraction opportunity from an unanswered turn is a low-stakes, rare gap
— not the kind of "facts Larry actually stated" loss the plan's exit
criteria cares about, since a turn with no reply is unusual to begin with.

WHY NOT persist a "processed" flag per conversations row instead of a
pending-turn table: the pairing problem is about PENDING work (what's
still open), and a table that tracks only the open items is one row per
session at most (cheap, self-cleaning), versus a flag on every row ever
written (unbounded growth, and no clearer for it — you would still need
to scan for "the most recent user row without a following assistant row"
to recover pairing state after a restart).

CRASH SAFETY / AT-LEAST-ONCE, NOT EXACTLY-ONCE: each tick's cursor advance
and pending-table updates commit on ONE connection at the end of the tick,
but jarvis.memory_extraction.extract_from_exchange opens and commits on
its OWN separate connection per exchange (matching jarvis.memory's own
update_memory_from_session convention). If the process dies between an
exchange's extraction committing and the tick's own cursor-advance commit,
that exchange is re-fetched and re-extracted on the next poll. This is
deliberately accepted rather than engineered away with two-phase commit or
similar: jarvis.memory_extraction's novelty gate already makes a repeat
extraction of the same exchange cheap and safe (an exact-key fact refresh,
a same-tier near-duplicate recurrence bump, or a within-session observation
duplicate bump — never a silent duplicate row), so a rare crash-recovery
re-run costs a little redundant bookkeeping, not corrupted memory.

Summary regeneration is NOT this module's job — see
jarvis/memory_extraction.py's own docstring for why that stays on
jarvis.memory.update_memory_from_session's existing whole-session path.
"""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Callable
from uuid import uuid4

from jarvis.config import Settings, load_settings
from jarvis.db import get_conn, now_iso, run_migrations
from jarvis.logging_config import setup_logging
from jarvis.memory import current_user_id, promote_observations
from jarvis.memory_admission import (
    cancel_job,
    claim_due_jobs,
    complete_job,
    defer_job_until,
    enqueue_exchange,
    fail_or_retry_job,
    next_utc_day,
    reclaim_abandoned_jobs,
    save_classification,
    save_extracted_candidates,
)
from jarvis.memory_automation import (
    Candidate,
    Classification,
    RolloutStage,
    bounded_candidates,
    classification_admitted,
    normalize_rollout_stage,
    redact_candidate_text,
    reserve_classification_budget,
)
from jarvis.memory_automation_eval import ConfiguredMemoryClassifier
from jarvis.memory_extraction import (
    admit_fact_candidate,
    admit_observation_candidate,
    extract_candidates_from_exchange,
    extract_from_exchange,
    filter_echo_candidates,
)

logger = logging.getLogger(__name__)

# [guessing] Starting values, not load-tested — easy to override without a
# code change (env var) or a deploy (constant) if Larry's actual usage
# pattern wants something different. 20s is a deliberate, large step down
# from MemorySweepWatcher's 300s default: per-exchange extraction is the
# whole point of Phase 2, and a poll that finds nothing new costs one
# cheap SQLite query, not an LLM call — the cost only shows up when there
# is real work to do.
DEFAULT_POLL_INTERVAL_S = 20.0

# [guessing] Long enough to comfortably outlast a slow LLM call or a brief
# network hiccup; short enough that a permanently-orphaned (sensitive-skip)
# pending row does not linger indefinitely. One row per session either way
# — the cost of getting this wrong in either direction is small.
DEFAULT_ORPHAN_TIMEOUT_S = 600.0


def _poll_interval_s() -> float:
    raw = os.environ.get("JARVIS_MEMORY_EXTRACTION_POLL_INTERVAL_S")
    if raw:
        try:
            return float(raw)
        except ValueError:
            logger.warning(
                "invalid JARVIS_MEMORY_EXTRACTION_POLL_INTERVAL_S, using default"
            )
    return DEFAULT_POLL_INTERVAL_S


def _orphan_timeout_s() -> float:
    raw = os.environ.get("JARVIS_MEMORY_EXTRACTION_ORPHAN_TIMEOUT_S")
    if raw:
        try:
            return float(raw)
        except ValueError:
            logger.warning(
                "invalid JARVIS_MEMORY_EXTRACTION_ORPHAN_TIMEOUT_S, using default"
            )
    return DEFAULT_ORPHAN_TIMEOUT_S


def _iso_minus(iso_str: str, seconds: float) -> str:
    """`iso_str` (as produced by jarvis.db.now_iso) minus `seconds`,
    formatted the same way -- used to build the orphan-cleanup cutoff."""
    dt = datetime.fromisoformat(iso_str)
    return (dt - timedelta(seconds=seconds)).isoformat()


def _get_cursor(conn) -> int:
    row = conn.execute(
        "SELECT last_processed_conversation_id FROM memory_extraction_cursor WHERE id = 1"
    ).fetchone()
    return row["last_processed_conversation_id"] if row is not None else 0


def _set_cursor(conn, value: int) -> None:
    conn.execute(
        "UPDATE memory_extraction_cursor SET last_processed_conversation_id = ?, "
        "updated_at = ? WHERE id = 1",
        (value, now_iso()),
    )


def _get_pending(conn, session_id: str):
    return conn.execute(
        "SELECT * FROM memory_extraction_pending WHERE session_id = ?",
        (session_id,),
    ).fetchone()


def _set_pending(
    conn, session_id: str, content: str, turn_id: int, first_seen_at: str
) -> None:
    conn.execute(
        "INSERT INTO memory_extraction_pending "
        "(session_id, user_content, user_turn_id, first_seen_at) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(session_id) DO UPDATE SET "
        "user_content = excluded.user_content, "
        "user_turn_id = excluded.user_turn_id, "
        "first_seen_at = excluded.first_seen_at",
        (session_id, content, turn_id, first_seen_at),
    )


def _clear_pending(conn, session_id: str) -> None:
    conn.execute(
        "DELETE FROM memory_extraction_pending WHERE session_id = ?", (session_id,)
    )


def _group_by_session(rows: list) -> dict:
    """Preserves fetch order (id ASC) within each session's list — Python
    dicts keep insertion order, so iterating this dict processes sessions
    in the order their first new row appeared, and each session's own rows
    stay in strict chronological order."""
    by_session: dict[str, list] = {}
    for row in rows:
        by_session.setdefault(row["session_id"], []).append(row)
    return by_session


def _automation_admission_enabled(settings: Settings) -> bool:
    return (
        bool(getattr(settings, "jarvis_memory_automation_enabled", False))
        and os.environ.get("JARVIS_MEMORY_AUTOMATION_ENABLED", "false").lower()
        in {"1", "true", "yes"}
    )


def _load_job_exchange(conn, job) -> dict[str, Any] | None:
    rows = conn.execute(
        "SELECT id,session_id,role,content,user_id FROM conversations "
        "WHERE id IN (?,?) ORDER BY id",
        (job["user_turn_id"], job["assistant_turn_id"]),
    ).fetchall()
    if len(rows) != 2:
        return None
    user_row, assistant_row = rows
    if (user_row["role"] != "user" or assistant_row["role"] != "assistant"
            or user_row["session_id"] != job["session_id"]
            or assistant_row["session_id"] != job["session_id"]
            or user_row["user_id"] != job["user_id"]
            or assistant_row["user_id"] != job["user_id"]):
        return None
    return {
        "session_id": str(job["session_id"]),
        "user_id": str(job["user_id"]),
        "user_turn_id": int(user_row["id"]),
        "assistant_turn_id": int(assistant_row["id"]),
        "user_content": str(user_row["content"]),
        "assistant_content": str(assistant_row["content"]),
    }


def _candidate_evidence(conn, *, user_id: str, key: str,
                        current_turn_id: int) -> tuple[tuple[str, ...], tuple[str, ...]]:
    proposed = [str(current_turn_id)]
    memory = conn.execute(
        "SELECT source_turn_id FROM memories WHERE user_id=? AND kind='fact' "
        "AND key=? AND archived_at IS NULL",
        (user_id, key),
    ).fetchone()
    if memory is not None and memory["source_turn_id"]:
        proposed.append(str(memory["source_turn_id"]))
    recall = conn.execute(
        "SELECT source_turn FROM memory_recall_events WHERE user_id=? AND key=? "
        "AND outcome IN ('exact_update','near_duplicate') AND source_turn IS NOT NULL "
        "ORDER BY created_at DESC LIMIT 7", (user_id, key),
    ).fetchall()
    proposed.extend(str(row["source_turn"]) for row in recall)
    verified: list[tuple[str, str]] = []
    for value in dict.fromkeys(proposed):
        try:
            turn_id = int(value)
        except (TypeError, ValueError):
            continue
        row = conn.execute(
            "SELECT id,session_id FROM conversations WHERE id=? AND user_id=? AND role='user'",
            (turn_id, user_id),
        ).fetchone()
        if row is not None:
            verified.append((str(row["id"]), str(row["session_id"])))
        if len(verified) >= 8:
            break
    return tuple(turn for turn, _ in verified), tuple(
        dict.fromkeys(session for _, session in verified)
    )


def _classification_dict(item: Classification) -> dict[str, Any]:
    return {
        "key": item.key, "scope": item.scope.value,
        "memory_type": item.memory_type.value, "provenance": item.provenance.value,
        "evidence_status": item.evidence_status.value,
        "confidence": item.confidence, "evidence": list(item.evidence),
        "reason_code": item.reason_code, "subject": item.subject,
        "project": item.project, "valid_from": item.valid_from,
        "valid_until": item.valid_until,
    }


def _write_admission_shadow(conn, *, job_id: int, user_id: str,
                            candidate_items: list[dict[str, str]],
                            classifications: list[Classification],
                            admitted: list[bool], now_iso: str) -> None:
    candidate_digest = hashlib.sha256(json.dumps(
        candidate_items, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")).hexdigest()
    rows = []
    for candidate, classification, is_admitted in zip(
            candidate_items, classifications, admitted, strict=True):
        rows.append({
            "key_digest": hashlib.sha256(candidate["key"].encode("utf-8")).hexdigest(),
            "scope": classification.scope.value,
            "memory_type": classification.memory_type.value,
            "provenance": classification.provenance.value,
            "evidence_status": classification.evidence_status.value,
            "confidence": classification.confidence,
            "evidence": list(classification.evidence[:8]),
            "reason_code": classification.reason_code,
            "admitted": bool(is_admitted),
        })
    conn.execute(
        "INSERT OR REPLACE INTO memory_admission_shadow "
        "(job_id,user_id,candidate_digest,classification_json,observed_at) "
        "VALUES (?,?,?,?,?)",
        (job_id, user_id, candidate_digest,
         json.dumps(rows, sort_keys=True, separators=(",", ":")), now_iso),
    )


def _apply_job_atomically(conn, *, job_id: int, expected_claimed_at: str,
                          settings: Settings, now_iso_value: str) -> bool:
    conn.execute("BEGIN IMMEDIATE")
    try:
        job = conn.execute(
            "SELECT * FROM memory_admission_jobs WHERE id=? AND status='running' "
            "AND stage='apply' AND claimed_at=?", (job_id, expected_claimed_at),
        ).fetchone()
        if job is None:
            conn.rollback()
            return False
        exchange = _load_job_exchange(conn, job)
        if exchange is None:
            conn.execute(
                "UPDATE memory_admission_jobs SET status='cancelled',candidate_json=NULL,"
                "classification_json=NULL,claimed_at=NULL,last_error_code='source_unavailable',"
                "updated_at=? WHERE id=? AND status='running'",
                (now_iso_value, job_id),
            )
            conn.commit()
            return False
        if str(job["user_id"]) != current_user_id():
            raise ValueError("admission worker user identity does not match source")
        candidates = json.loads(job["candidate_json"] or "{}")
        classifications_raw = json.loads(job["classification_json"] or "[]")
        if set(candidates) != {"facts", "observations"}:
            raise ValueError("staged candidate payload is malformed")
        candidate_items = [*candidates["facts"], *candidates["observations"]]
        classifications = [Classification.from_dict(item) for item in classifications_raw]
        if len(candidate_items) != len(classifications):
            raise ValueError("staged classification does not cover candidate batch")

        rollout = normalize_rollout_stage(
            getattr(settings, "jarvis_memory_automation_stage", RolloutStage.SHADOW)
        )
        effective_shadow = (
            bool(getattr(settings, "jarvis_memory_automation_shadow", True))
            or rollout is RolloutStage.SHADOW
        )
        admitted_rows: list[bool] = []
        for candidate, item in zip(candidate_items, classifications, strict=True):
            eligible = set(_candidate_evidence(
                conn, user_id=str(job["user_id"]), key=candidate["key"],
                current_turn_id=int(job["user_turn_id"]),
            )[0])
            if (len(set(item.evidence)) != len(item.evidence)
                    or any(turn_id not in eligible for turn_id in item.evidence)):
                raise ValueError("classification cites stale or unverified evidence")
            # Provider output cannot make assistant/tool/quoted material a
            # trusted user memory. Candidate evidence is limited to user turns.
            can_admit = (
                not effective_shadow
                and item.provenance.value == "user"
                and str(job["user_turn_id"]) in item.evidence
                and classification_admitted(item, rollout)
            )
            admitted_rows.append(can_admit)

        user_turn_id = int(job["user_turn_id"])
        assistant_turn_id = int(job["assistant_turn_id"])
        for group, offset in (("facts", 0), ("observations", len(candidates["facts"]))):
            for index, candidate in enumerate(candidates[group], start=offset):
                if not admitted_rows[index]:
                    continue
                if group == "facts":
                    outcome = admit_fact_candidate(
                        conn, candidate["key"], candidate["value"],
                        str(job["session_id"]), assistant_turn_id,
                        evidence_turn_id=user_turn_id,
                        enqueue_classification=False,
                    )
                else:
                    outcome = admit_observation_candidate(
                        conn, candidate["key"], candidate["value"],
                        str(job["session_id"]), assistant_turn_id,
                    )
                if outcome == "rejected":
                    admitted_rows[index] = False
                    continue
        promote_observations(conn)
        # Observation promotion can create a durable fact row. Apply its
        # already-validated classification only after promotion, inside the
        # same admission transaction.
        for candidate, item, is_admitted in zip(
                candidate_items, classifications, admitted_rows, strict=True):
            if not is_admitted:
                continue
            row = conn.execute(
                "SELECT id FROM memories WHERE user_id=? AND kind='fact' AND key=? "
                "AND archived_at IS NULL",
                (job["user_id"], candidate["key"]),
            ).fetchone()
            if row is not None:
                conn.execute(
                    "UPDATE memories SET subject=?,scope=?,memory_type=?,provenance=?,"
                    "evidence_status=?,confidence=?,valid_from=?,valid_until=?,"
                    "source_turn_id=?,classifier_version=?,classified_at=? WHERE id=? AND user_id=?",
                    (item.subject, item.scope.value, item.memory_type.value,
                     item.provenance.value, item.evidence_status.value,
                     item.confidence, item.valid_from, item.valid_until,
                     item.evidence[0] if item.evidence else str(user_turn_id),
                     str(job["policy_version"]), now_iso_value, row["id"], job["user_id"]),
                )
        # Update shadow admission flags after content scans may have rejected
        # a candidate. The metadata record remains content-free.
        _write_admission_shadow(
            conn, job_id=job_id, user_id=str(job["user_id"]),
            candidate_items=candidate_items, classifications=classifications,
            admitted=admitted_rows, now_iso=now_iso_value,
        )
        if not complete_job(
                conn, job_id=job_id, now_iso=now_iso_value,
                expected_claimed_at=str(job["claimed_at"])):
            conn.rollback()
            return False
        return True
    except Exception:
        conn.rollback()
        raise


def process_admission_jobs(
    settings: Settings, db_path: str | None = None, *, classifier=None,
    extractor=None, now_iso_value: str | None = None, limit: int = 20,
) -> dict[str, int]:
    """Advance one committed extract/classify/apply stage per claimed job.

    This synchronous owner is called from a worker thread. Model calls happen
    only after the claim is committed and are bounded by the shared durable
    classifier budget. Missing confidential routes fail closed and enter the
    queue's bounded retry path.
    """
    if not _automation_admission_enabled(settings):
        return {"claimed": 0, "extracted": 0, "classified": 0,
                "applied": 0, "failed": 0, "deferred": 0, "recovered": 0}
    stamp = now_iso_value or now_iso()
    conn = get_conn(db_path)
    counts = {"claimed": 0, "extracted": 0, "classified": 0,
              "applied": 0, "failed": 0, "deferred": 0}
    try:
        counts["recovered"] = reclaim_abandoned_jobs(conn, now_iso=stamp)
        jobs = claim_due_jobs(conn, now_iso=stamp, limit=limit)
        counts["claimed"] = len(jobs)
        configured_classifier = classifier or ConfiguredMemoryClassifier(settings)
        extract_fn = extractor or extract_candidates_from_exchange
        for job in jobs:
            claim_stamp = job["claimed_at"]
            if not isinstance(claim_stamp, str) or not claim_stamp:
                counts["failed"] += 1
                continue
            try:
                source = _load_job_exchange(conn, job)
                if source is None:
                    cancel_job(conn, job_id=int(job["id"]), now_iso=stamp,
                               reason="source_unavailable")
                    continue
                if job["stage"] == "extract":
                    result = extract_fn(
                        settings, source["session_id"], source["user_content"],
                        source["assistant_content"], source["assistant_turn_id"],
                    )
                    if inspect.isawaitable(result):
                        result = asyncio.run(result)
                    # Reject echoes before the durable queue persists candidates
                    # for classification. The transcript remains canonical.
                    result = filter_echo_candidates(
                        result, source["user_content"], source["assistant_content"],
                    )
                    if not save_extracted_candidates(
                            conn, job_id=int(job["id"]), candidates=result,
                            now_iso=stamp, expected_claimed_at=claim_stamp):
                        continue
                    counts["extracted"] += 1
                    continue
                if job["stage"] == "classify":
                    payload = json.loads(job["candidate_json"] or "{}")
                    candidate_items = [*payload.get("facts", []), *payload.get("observations", [])]
                    if not candidate_items:
                        if save_classification(conn, job_id=int(job["id"]),
                                               classifications=[], now_iso=stamp,
                                               expected_claimed_at=claim_stamp):
                            counts["classified"] += 1
                        continue
                    candidates = []
                    for candidate in candidate_items:
                        turn_ids, session_ids = _candidate_evidence(
                            conn, user_id=str(job["user_id"]), key=candidate["key"],
                            current_turn_id=int(job["user_turn_id"]),
                        )
                        candidates.append(Candidate(
                            candidate["key"], redact_candidate_text(candidate["value"]),
                            turn_ids, session_ids,
                        ))
                    bounded = bounded_candidates(candidates)
                    conn.commit()
                    reservation = reserve_classification_budget(
                        conn, now_iso=stamp, candidate_count=len(bounded),
                        reservation_id=f"admission-{job['id']}-{uuid4().hex}",
                    )
                    if reservation is None:
                        defer_job_until(
                            conn, job_id=int(job["id"]), next_attempt_at=next_utc_day(stamp),
                            now_iso=stamp, expected_claimed_at=claim_stamp,
                        )
                        counts["deferred"] += 1
                        continue
                    results = list(configured_classifier(
                        bounded, policy_version=str(job["policy_version"]),
                    ))
                    decoded = [item if isinstance(item, Classification)
                               else Classification.from_dict(item) for item in results]
                    if len(decoded) != len(bounded):
                        raise ValueError("classifier output does not cover candidate batch")
                    for candidate, item in zip(bounded, decoded, strict=True):
                        if (item.key != candidate.key
                                or any(evidence not in set(candidate.source_turn_ids)
                                       for evidence in item.evidence)):
                            raise ValueError("classifier output key/evidence is invalid")
                    if save_classification(
                            conn, job_id=int(job["id"]),
                            classifications=[_classification_dict(item) for item in decoded],
                            now_iso=stamp, expected_claimed_at=claim_stamp):
                        counts["classified"] += 1
                    continue
                if job["stage"] == "apply":
                    if _apply_job_atomically(
                conn, job_id=int(job["id"]), settings=settings,
                now_iso_value=stamp, expected_claimed_at=claim_stamp):
                        counts["applied"] += 1
            except Exception as exc:  # failures stay bounded and content-free
                logger.warning("memory_admission_stage_failed stage=%s error_type=%s",
                               job["stage"], type(exc).__name__[:80])
                fail_or_retry_job(conn, job_id=int(job["id"]), now_iso=stamp,
                                  error_code=type(exc).__name__,
                                  expected_claimed_at=claim_stamp)
                counts["failed"] += 1
        conn.commit()
        return counts
    finally:
        conn.close()


async def tick_once(
    settings: Settings,
    db_path: str | None = None,
    client_factory: Callable[[Settings], Any] | None = None,
    admission_extractor=None,
) -> dict:
    """One poll cycle. Public for tests; never raises — mirrors
    MemorySweepWatcher.tick_once's discipline so one broken poll can never
    take the whole service down, exactly as one bad exchange inside
    extract_from_exchange itself can never wedge this loop.

    Returns {"rows": n, "exchanges": n, "cursor": new_or_unchanged_cursor}
    (plus "error": True on the rare tick-level failure, distinct from a
    single exchange's own failure — extract_from_exchange already reports
    that internally and never raises here).
    """
    try:
        admission_enabled = _automation_admission_enabled(settings)
        admission_result = {}
        if admission_enabled:
            admission_result = await asyncio.to_thread(
                process_admission_jobs, settings, db_path,
                extractor=admission_extractor,
            )
        conn = get_conn(db_path)
        try:
            cursor = _get_cursor(conn)
            rows = conn.execute(
                "SELECT * FROM conversations WHERE id > ? ORDER BY id ASC",
                (cursor,),
            ).fetchall()
            if not rows:
                result = {"rows": 0, "exchanges": 0, "cursor": cursor}
                if admission_enabled:
                    result["admission"] = admission_result
                return result

            now = now_iso()
            exchange_count = 0

            for session_id, session_rows in _group_by_session(rows).items():
                pending = _get_pending(conn, session_id)
                pending_content = pending["user_content"] if pending else None
                pending_turn_id = pending["user_turn_id"] if pending else None
                pending_first_seen = pending["first_seen_at"] if pending else None

                for row in session_rows:
                    role = row["role"]
                    if role == "user":
                        # A newer user turn supersedes an older unresolved
                        # one (e.g. two user turns before any reply) —
                        # only the most recent utterance is ever the
                        # trigger for the next assistant reply. The
                        # superseded turn is never extracted; a documented,
                        # rare edge case, not a silent bug.
                        pending_content = row["content"]
                        pending_turn_id = row["id"]
                        pending_first_seen = now
                    elif role == "assistant":
                        if pending_content is not None:
                            if admission_enabled:
                                _, created = enqueue_exchange(
                                    conn, user_id=str(row["user_id"] or "local"),
                                    session_id=session_id,
                                    user_turn_id=int(pending_turn_id),
                                    assistant_turn_id=int(row["id"]),
                                    policy_version="b1", now_iso=now,
                                )
                                exchange_count += int(created)
                            else:
                                await extract_from_exchange(
                                    settings,
                                    session_id,
                                    pending_content,
                                    row["content"],
                                    row["id"],
                                    client_factory=client_factory,
                                    user_turn_id=pending_turn_id,
                                )
                                exchange_count += 1
                            pending_content = None
                            pending_turn_id = None
                            pending_first_seen = None
                        # else: an assistant row with nothing pending
                        # (proactive message, or its user turn already
                        # timed out of the pending table) — nothing the
                        # user said to extract from; skip.
                    # role == "tool": no pairing effect, passed over.

                if pending_content is not None:
                    _set_pending(
                        conn, session_id, pending_content, pending_turn_id,
                        pending_first_seen or now,
                    )
                else:
                    _clear_pending(conn, session_id)
                # Item 13 (2026-09-17): release the write lock NOW. The
                # INSERT/DELETE above opened an implicit transaction on this
                # connection, and extract_from_exchange writes through a
                # connection of its own -- so without this commit every
                # session after the first blocks on this one, in the same
                # thread, until the busy timeout fails it. Measured on the
                # 2026-09-16 backfill: 28 of 122 exchanges lost, every one
                # inside upsert_fact or add_observation.
                conn.commit()

            new_cursor = rows[-1]["id"]
            _set_cursor(conn, new_cursor)

            cutoff = _iso_minus(now, _orphan_timeout_s())
            conn.execute(
                "DELETE FROM memory_extraction_pending WHERE first_seen_at < ?",
                (cutoff,),
            )

            conn.commit()
            result = {"rows": len(rows), "exchanges": exchange_count, "cursor": new_cursor}
            if admission_enabled:
                result["admission"] = admission_result
            return result
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001 — one bad poll must never crash the worker
        logger.warning(
            "memory_extraction_tick_failed error_type=%s",
            type(exc).__name__[:80],
        )
        return {"rows": 0, "exchanges": 0, "cursor": None, "error": True}


async def run_forever(
    settings: Settings | None = None,
    db_path: str | None = None,
    poll_interval_s: float | None = None,
    client_factory: Callable[[Settings], Any] | None = None,
) -> None:
    """The service loop. Runs until cancelled (task cancellation in tests)
    or the process is killed (SIGTERM under a process manager — no custom
    signal handling here, matching every other long-lived process in this
    repo; none trap signals themselves)."""
    settings = settings or load_settings()
    interval = poll_interval_s if poll_interval_s is not None else _poll_interval_s()
    logger.info("memory_extraction_worker_started poll_interval_s=%s", interval)
    while True:
        result = await tick_once(settings, db_path=db_path, client_factory=client_factory)
        if result.get("exchanges"):
            logger.info("memory_extraction_tick rows=%s exchanges=%s",
                        result.get("rows"), result.get("exchanges"))
        await asyncio.sleep(interval)


def main() -> None:
    setup_logging(os.environ.get("JARVIS_LOG_LEVEL", "INFO"))
    run_migrations()
    try:
        asyncio.run(run_forever())
    except KeyboardInterrupt:
        logger.info("memory_extraction_worker_stopped")


if __name__ == "__main__":
    main()
