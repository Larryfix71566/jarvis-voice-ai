"""Durable, idempotent staging for automatic memory admission.

This queue is not a retrieval source. Its APIs persist source identity before
cursor advancement, make stage transitions compare-and-set operations, and
remove staged payloads when work succeeds, is cancelled, or is forgotten.
Provider calls are intentionally not made by this module.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

STAGES = frozenset({"extract", "classify", "apply"})
STATUSES = frozenset({"pending", "running", "complete", "failed", "cancelled"})
MAX_STAGED_JSON_BYTES = 64_000
MAX_CANDIDATES_PER_EXCHANGE = 20
MAX_CANDIDATE_CHARS_PER_EXCHANGE = 12_000
RETRY_DELAYS_S = (60, 300, 1800)


class AdmissionJobError(ValueError):
    """A staged memory-admission payload or transition is invalid."""


def _digest_exchange(*, user_id: str, session_id: str, user_turn_id: int,
                     assistant_turn_id: int, policy_version: str) -> str:
    canonical = json.dumps(
        [user_id, session_id, int(user_turn_id), int(assistant_turn_id), policy_version],
        ensure_ascii=True, separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _encode_json(value: Any, *, label: str, required_type: type) -> str:
    if not isinstance(value, required_type):
        raise AdmissionJobError(f"{label} must be {required_type.__name__}")
    try:
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False,
                             sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise AdmissionJobError(f"{label} is not valid JSON data") from exc
    if len(encoded.encode("utf-8")) > MAX_STAGED_JSON_BYTES:
        raise AdmissionJobError(f"{label} exceeds staging quota")
    return encoded


def enqueue_exchange(conn: sqlite3.Connection, *, user_id: str,
                     session_id: str, user_turn_id: int,
                     assistant_turn_id: int, policy_version: str,
                     now_iso: str) -> tuple[int, bool]:
    """Persist a finished exchange before a caller advances its cursor.

    The source transcript remains canonical; only its IDs are placed in the
    initial job. Both turns must exist, have the expected roles, belong to the
    same session and user, and be in chronological order.
    """
    if not user_id or not session_id or not policy_version:
        raise AdmissionJobError("user, session and policy identities are required")
    if (isinstance(user_turn_id, bool) or not isinstance(user_turn_id, int)
            or isinstance(assistant_turn_id, bool) or not isinstance(assistant_turn_id, int)
            or user_turn_id < 1 or assistant_turn_id <= user_turn_id):
        raise AdmissionJobError("exchange turn IDs are invalid")
    rows = conn.execute(
        "SELECT id,session_id,role,user_id FROM conversations "
        "WHERE id IN (?,?) ORDER BY id",
        (user_turn_id, assistant_turn_id),
    ).fetchall()
    if len(rows) != 2:
        raise AdmissionJobError("exchange source turns do not exist")
    user_row, assistant_row = rows
    if (user_row["role"] != "user" or assistant_row["role"] != "assistant"
            or user_row["session_id"] != session_id
            or assistant_row["session_id"] != session_id
            or user_row["user_id"] != user_id
            or assistant_row["user_id"] != user_id):
        raise AdmissionJobError("exchange source identity does not match transcript")
    key = _digest_exchange(
        user_id=user_id, session_id=session_id, user_turn_id=user_turn_id,
        assistant_turn_id=assistant_turn_id, policy_version=policy_version,
    )
    cur = conn.execute(
        "INSERT OR IGNORE INTO memory_admission_jobs "
        "(idempotency_key,user_id,session_id,user_turn_id,assistant_turn_id,"
        "policy_version,stage,status,next_attempt_at,created_at,updated_at) "
        "VALUES (?,?,?,?,?,?,'extract','pending',?,?,?)",
        (key, user_id, session_id, user_turn_id, assistant_turn_id,
         policy_version, now_iso, now_iso, now_iso),
    )
    row = conn.execute(
        "SELECT id FROM memory_admission_jobs WHERE idempotency_key=?", (key,)
    ).fetchone()
    return int(row["id"]), cur.rowcount == 1


def enqueue_finished_session_exchanges(conn: sqlite3.Connection, *, session_id: str,
                                       policy_version: str, now_iso: str) -> int:
    """Idempotently stage every finished pair in one session at teardown.

    This is a safety net for a final exchange that the standalone global
    cursor worker has not polled yet. It does not move that global cursor;
    duplicate enqueue is harmless by canonical exchange idempotency.
    """
    rows = conn.execute(
        "SELECT id,role,user_id FROM conversations WHERE session_id=? ORDER BY id",
        (session_id,),
    ).fetchall()
    pending: tuple[int, str] | None = None
    enqueued = 0
    for row in rows:
        if row["role"] == "user":
            pending = (int(row["id"]), str(row["user_id"] or "local"))
        elif row["role"] == "assistant" and pending is not None:
            user_turn_id, user_id = pending
            _, created = enqueue_exchange(
                conn, user_id=user_id, session_id=session_id,
                user_turn_id=user_turn_id, assistant_turn_id=int(row["id"]),
                policy_version=policy_version, now_iso=now_iso,
            )
            enqueued += int(created)
            pending = None
    return enqueued


def claim_due_jobs(conn: sqlite3.Connection, *, now_iso: str,
                   limit: int = 20) -> list[sqlite3.Row]:
    """Claim due jobs and commit the claim before returning to provider code."""
    if not 1 <= limit <= 20:
        raise ValueError("limit must be between 1 and 20")
    if conn.in_transaction:
        raise AdmissionJobError("claim requires a clean connection")
    conn.execute("BEGIN IMMEDIATE")
    try:
        rows = conn.execute(
            "SELECT id FROM memory_admission_jobs WHERE status='pending' "
            "AND next_attempt_at<=? ORDER BY id LIMIT ?", (now_iso, limit),
        ).fetchall()
        ids = [int(row["id"]) for row in rows]
        for job_id in ids:
            conn.execute(
                "UPDATE memory_admission_jobs SET status='running',claimed_at=?,updated_at=? "
                "WHERE id=? AND status='pending'",
                (now_iso, now_iso, job_id),
            )
        claimed = []
        if ids:
            placeholders = ",".join("?" for _ in ids)
            claimed = conn.execute(
                f"SELECT * FROM memory_admission_jobs WHERE id IN ({placeholders}) "
                "AND status='running' ORDER BY id", ids,
            ).fetchall()
        conn.commit()
        return claimed
    except Exception:
        conn.rollback()
        raise


def save_extracted_candidates(conn: sqlite3.Connection, *, job_id: int,
                              candidates: dict[str, Any], now_iso: str,
                              expected_claimed_at: str | None = None) -> bool:
    """Commit extraction output and advance only a running extract-stage job."""
    encoded = _encode_json(candidates, label="candidate_json", required_type=dict)
    if set(candidates) != {"facts", "observations"}:
        raise AdmissionJobError("candidate payload fields do not match the contract")
    facts = candidates.get("facts")
    observations = candidates.get("observations")
    if not isinstance(facts, list) or not isinstance(observations, list):
        raise AdmissionJobError("candidate payload requires facts and observations arrays")
    items = [*facts, *observations]
    if len(items) > MAX_CANDIDATES_PER_EXCHANGE:
        raise AdmissionJobError("candidate count exceeds per-exchange limit")
    keys: list[str] = []
    text_chars = 0
    for item in items:
        if (not isinstance(item, dict) or set(item) != {"key", "value"}
                or not isinstance(item["key"], str) or not item["key"].strip()
                or not isinstance(item["value"], str) or not item["value"].strip()):
            raise AdmissionJobError("candidate item does not match the key/value contract")
        if len(item["key"].strip()) > 120 or len(item["value"].strip()) > 300:
            raise AdmissionJobError("candidate row exceeds the per-item bound")
        keys.append(item["key"])
        text_chars += len(item["key"]) + len(item["value"])
    if len(keys) != len(set(keys)):
        raise AdmissionJobError("candidate keys must be unique")
    if text_chars > MAX_CANDIDATE_CHARS_PER_EXCHANGE:
        raise AdmissionJobError("candidate text exceeds per-exchange limit")
    claim_clause = " AND claimed_at=?" if expected_claimed_at is not None else ""
    params: tuple[Any, ...] = (encoded, now_iso, now_iso, job_id)
    if expected_claimed_at is not None:
        params += (expected_claimed_at,)
    conn.execute(
        "UPDATE memory_admission_jobs SET candidate_json=?,stage='classify',status='pending',"
        "claimed_at=NULL,next_attempt_at=?,updated_at=? "
        "WHERE id=? AND status='running' AND stage='extract'" + claim_clause,
        params,
    )
    changed = conn.execute("SELECT changes()").fetchone()[0] == 1
    if changed:
        conn.commit()
    return changed


def save_classification(conn: sqlite3.Connection, *, job_id: int,
                        classifications: list[dict[str, Any]],
                        now_iso: str,
                        expected_claimed_at: str | None = None) -> bool:
    """Commit a validated full classification batch before the apply stage."""
    encoded = _encode_json(classifications, label="classification_json", required_type=list)
    row = conn.execute(
        "SELECT candidate_json FROM memory_admission_jobs WHERE id=? "
        "AND status='running' AND stage='classify'", (job_id,),
    ).fetchone()
    if row is None or row["candidate_json"] is None:
        return False
    try:
        candidates = json.loads(row["candidate_json"])
    except (TypeError, ValueError) as exc:
        raise AdmissionJobError("stored candidate payload is malformed") from exc
    from jarvis.memory_automation import Classification
    try:
        for item in classifications:
            Classification.from_dict(item)
    except (TypeError, ValueError) as exc:
        raise AdmissionJobError("classification row does not match the locked schema") from exc
    candidate_keys = [str(item.get("key", "")) for group in ("facts", "observations")
                      for item in candidates[group] if isinstance(item, dict)]
    result_keys = [str(item.get("key", "")) for item in classifications
                   if isinstance(item, dict)]
    if (len(candidate_keys) != len(set(candidate_keys))
            or len(result_keys) != len(classifications)
            or result_keys != candidate_keys):
        raise AdmissionJobError("classification rows do not match candidate keys/order")
    claim_clause = " AND claimed_at=?" if expected_claimed_at is not None else ""
    params: tuple[Any, ...] = (encoded, now_iso, now_iso, job_id)
    if expected_claimed_at is not None:
        params += (expected_claimed_at,)
    conn.execute(
        "UPDATE memory_admission_jobs SET classification_json=?,stage='apply',status='pending',"
        "claimed_at=NULL,next_attempt_at=?,updated_at=? "
        "WHERE id=? AND status='running' AND stage='classify'" + claim_clause,
        params,
    )
    changed = conn.execute("SELECT changes()").fetchone()[0] == 1
    if changed:
        conn.commit()
    return changed


def complete_job(conn: sqlite3.Connection, *, job_id: int, now_iso: str,
                 expected_claimed_at: str | None = None) -> bool:
    """Drop sensitive staged payloads while retaining the idempotency receipt."""
    claim_clause = " AND claimed_at=?" if expected_claimed_at is not None else ""
    params: tuple[Any, ...] = (now_iso, job_id)
    if expected_claimed_at is not None:
        params += (expected_claimed_at,)
    conn.execute(
        "UPDATE memory_admission_jobs SET status='complete',candidate_json=NULL,"
        "classification_json=NULL,claimed_at=NULL,last_error_code=NULL,updated_at=? "
        "WHERE id=? AND status='running' AND stage='apply'" + claim_clause,
        params,
    )
    changed = conn.execute("SELECT changes()").fetchone()[0] == 1
    if changed:
        conn.commit()
    return changed


def defer_job_until(conn: sqlite3.Connection, *, job_id: int,
                    next_attempt_at: str, now_iso: str,
                    error_code: str = "daily_budget_exhausted",
                    expected_claimed_at: str | None = None) -> bool:
    """Return a claimed job to pending without consuming a failure attempt."""
    claim_clause = " AND claimed_at=?" if expected_claimed_at is not None else ""
    params: tuple[Any, ...] = (next_attempt_at, error_code[:64], now_iso, job_id)
    if expected_claimed_at is not None:
        params += (expected_claimed_at,)
    conn.execute(
        "UPDATE memory_admission_jobs SET status='pending',claimed_at=NULL,"
        "next_attempt_at=?,last_error_code=?,updated_at=? "
        "WHERE id=? AND status='running'" + claim_clause,
        params,
    )
    changed = conn.execute("SELECT changes()").fetchone()[0] == 1
    if changed:
        conn.commit()
    return changed


def next_utc_day(now_iso: str) -> str:
    """Return the next UTC midnight in the stored ISO timestamp format."""
    stamp = datetime.fromisoformat(now_iso.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("now_iso must be timezone-aware")
    next_day = stamp.astimezone(timezone.utc).date() + timedelta(days=1)
    return datetime.combine(next_day, datetime.min.time(), tzinfo=timezone.utc).isoformat()


def fail_or_retry_job(conn: sqlite3.Connection, *, job_id: int, now_iso: str,
                      error_code: str,
                      expected_claimed_at: str | None = None) -> bool:
    """Schedule the existing bounded 60/300/1800-second retry policy."""
    claim_clause = " AND claimed_at=?" if expected_claimed_at is not None else ""
    params: tuple[Any, ...] = (job_id,)
    if expected_claimed_at is not None:
        params += (expected_claimed_at,)
    row = conn.execute(
        "SELECT attempts FROM memory_admission_jobs WHERE id=? AND status='running'"
        + claim_clause,
        params,
    ).fetchone()
    if row is None:
        return False
    attempts = int(row["attempts"]) + 1
    if attempts >= len(RETRY_DELAYS_S):
        status, next_at = "failed", now_iso
    else:
        stamp = datetime.fromisoformat(now_iso.replace("Z", "+00:00"))
        next_at = (stamp + timedelta(seconds=RETRY_DELAYS_S[attempts - 1])).isoformat()
        status = "pending"
    update_params: tuple[Any, ...] = (
        status, attempts, next_at, error_code[:64], now_iso, job_id,
    )
    if expected_claimed_at is not None:
        update_params += (expected_claimed_at,)
    conn.execute(
        "UPDATE memory_admission_jobs SET status=?,attempts=?,next_attempt_at=?,"
        "claimed_at=NULL,last_error_code=?,updated_at=? WHERE id=? AND status='running'"
        + claim_clause,
        update_params,
    )
    changed = conn.execute("SELECT changes()").fetchone()[0] == 1
    if changed:
        conn.commit()
    return changed


def cancel_job(conn: sqlite3.Connection, *, job_id: int, now_iso: str,
               reason: str = "cancelled") -> bool:
    """Invalidate a queued/in-flight claim and remove its private payload."""
    conn.execute(
        "UPDATE memory_admission_jobs SET status='cancelled',candidate_json=NULL,"
        "classification_json=NULL,claimed_at=NULL,last_error_code=?,updated_at=? "
        "WHERE id=? AND status IN ('pending','running','failed')",
        (reason[:64], now_iso, job_id),
    )
    changed = conn.execute("SELECT changes()").fetchone()[0] == 1
    if changed:
        conn.commit()
    return changed


def cancel_user_jobs(conn: sqlite3.Connection, *, user_id: str, now_iso: str,
                     session_id: str | None = None) -> int:
    """Forget all staged payloads for a user or one of their sessions."""
    if session_id is None:
        cursor = conn.execute(
            "UPDATE memory_admission_jobs SET status='cancelled',candidate_json=NULL,"
            "classification_json=NULL,claimed_at=NULL,last_error_code='forgotten',updated_at=? "
            "WHERE user_id=? AND status IN ('pending','running','failed')",
            (now_iso, user_id),
        )
    else:
        cursor = conn.execute(
            "UPDATE memory_admission_jobs SET status='cancelled',candidate_json=NULL,"
            "classification_json=NULL,claimed_at=NULL,last_error_code='forgotten',updated_at=? "
            "WHERE user_id=? AND session_id=? AND status IN ('pending','running','failed')",
            (now_iso, user_id, session_id),
        )
    if cursor.rowcount:
        conn.commit()
    return cursor.rowcount


def cancel_jobs_for_turn(conn: sqlite3.Connection, *, user_id: str,
                         session_id: str, user_turn_id: int,
                         now_iso: str) -> int:
    """Invalidate every staged exchange whose user source was forgotten."""
    cursor = conn.execute(
        "UPDATE memory_admission_jobs SET status='cancelled',candidate_json=NULL,"
        "classification_json=NULL,claimed_at=NULL,last_error_code='forgotten',updated_at=? "
        "WHERE user_id=? AND session_id=? AND user_turn_id=? "
        "AND status IN ('pending','running','failed')",
        (now_iso, user_id, session_id, int(user_turn_id)),
    )
    if cursor.rowcount:
        conn.commit()
    return cursor.rowcount


def cancel_jobs_for_key(conn: sqlite3.Connection, *, user_id: str, key: str,
                        now_iso: str) -> int:
    """Forget pending or in-flight staged candidates for one memory key."""
    rows = conn.execute(
        "SELECT id,candidate_json FROM memory_admission_jobs WHERE user_id=? "
        "AND status IN ('pending','running','failed') AND candidate_json IS NOT NULL",
        (user_id,),
    ).fetchall()
    matching_ids: list[int] = []
    for row in rows:
        try:
            payload = json.loads(row["candidate_json"] or "{}")
        except (TypeError, json.JSONDecodeError):
            continue
        if any(str(candidate.get("key", "")) == key
               for group in ("facts", "observations")
               for candidate in payload.get(group, [])
               if isinstance(candidate, dict)):
            matching_ids.append(int(row["id"]))
    if not matching_ids:
        return 0
    placeholders = ",".join("?" for _ in matching_ids)
    cursor = conn.execute(
        "UPDATE memory_admission_jobs SET status='cancelled',candidate_json=NULL,"
        "classification_json=NULL,claimed_at=NULL,last_error_code='forgotten',updated_at=? "
        f"WHERE id IN ({placeholders}) AND user_id=? "
        "AND status IN ('pending','running','failed')",
        (now_iso, *matching_ids, user_id),
    )
    if cursor.rowcount:
        conn.commit()
    return cursor.rowcount


def reclaim_abandoned_jobs(conn: sqlite3.Connection, *, now_iso: str,
                           lease_timeout_s: int = 180) -> int:
    """Return abandoned running claims to bounded retry after worker death."""
    if lease_timeout_s < 1:
        raise ValueError("lease timeout must be positive")
    now = datetime.fromisoformat(now_iso.replace("Z", "+00:00"))
    cutoff = (now - timedelta(seconds=lease_timeout_s)).isoformat()
    rows = conn.execute(
        "SELECT id,claimed_at FROM memory_admission_jobs WHERE status='running' "
        "AND claimed_at IS NOT NULL AND claimed_at<=? ORDER BY id", (cutoff,),
    ).fetchall()
    for row in rows:
        fail_or_retry_job(conn, job_id=int(row["id"]), now_iso=now_iso,
                          error_code="worker_interrupted",
                          expected_claimed_at=str(row["claimed_at"]))
    return len(rows)
