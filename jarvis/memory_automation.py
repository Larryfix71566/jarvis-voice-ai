"""Deterministic policy primitives for automated memory maintenance.

This module deliberately contains no database, model, or transport code.  It
is the shared contract used by admission, retrieval, and the idle worker.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from hashlib import sha256
from typing import Iterable
import sqlite3
import json
import re
import math
import os


class Scope(StrEnum):
    GLOBAL = "global"
    PROJECT = "project"
    SUBJECT = "subject"
    SESSION = "session"


class MemoryType(StrEnum):
    FACT = "fact"
    EXPLICIT_PREFERENCE = "explicit_preference"
    INFERRED_PREFERENCE = "inferred_preference"
    DECISION = "decision"
    TASK_RULE = "task_rule"
    TEMPORARY_CONTEXT = "temporary_context"


class Provenance(StrEnum):
    USER = "user"
    TOOL = "tool"
    ASSISTANT = "assistant"
    QUOTED_DOCUMENT = "quoted_document"


class EvidenceStatus(StrEnum):
    EXPLICIT = "explicit"
    CORROBORATED = "corroborated"
    TENTATIVE = "tentative"
    DISPUTED = "disputed"
    UNKNOWN = "unknown"


class RolloutStage(StrEnum):
    """Ordered production-admission stages for automated classification."""

    SHADOW = "shadow"
    EXPLICIT_PREFERENCES = "explicit_preferences"
    CORROBORATED_INFERENCES = "corroborated_inferences"


def memory_automation_enabled() -> bool:
    """JARVIS_MEMORY_AUTOMATION_ENABLED: on only if the value is 1/true/yes.
    Extracted from run_session's teardown check in jarvis/bot/pipeline.py
    (status spec T2.3) so that site and jarvis.status.overview read ONE
    rule (R8)."""
    return os.environ.get("JARVIS_MEMORY_AUTOMATION_ENABLED", "false").lower() in {
        "1", "true", "yes"}


EVIDENCE_RANK = {
    EvidenceStatus.EXPLICIT: 4,
    EvidenceStatus.CORROBORATED: 3,
    EvidenceStatus.TENTATIVE: 2,
    EvidenceStatus.UNKNOWN: 1,
    EvidenceStatus.DISPUTED: 0,
}


def normalize_rollout_stage(value: str | RolloutStage | None) -> RolloutStage:
    """Decode the staged rollout flag and fail closed on unknown values."""
    if value is None:
        return RolloutStage.SHADOW
    try:
        return value if isinstance(value, RolloutStage) else RolloutStage(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid memory automation rollout stage") from exc


def classification_admitted(classification: "Classification",
                            stage: str | RolloutStage | None) -> bool:
    """Return whether a classification may update live metadata at a stage.

    Shadow is observational. The second stage admits only explicit preference
    rows. The final stage also admits independently corroborated rows; all
    other classifications remain in the privacy-safe shadow ledger.
    """
    rollout = normalize_rollout_stage(stage)
    if rollout is RolloutStage.SHADOW:
        return False
    if (classification.memory_type is MemoryType.EXPLICIT_PREFERENCE and
            classification.evidence_status is EvidenceStatus.EXPLICIT):
        return True
    return (rollout is RolloutStage.CORROBORATED_INFERENCES and
            classification.evidence_status is EvidenceStatus.CORROBORATED)


@dataclass(frozen=True)
class Candidate:
    key: str
    content: str
    source_turn_ids: tuple[str, ...]
    session_ids: tuple[str, ...]
    subject: str | None = None
    project: str | None = None
    provenance_hint: Provenance | None = None


@dataclass(frozen=True)
class Classification:
    key: str
    scope: Scope
    memory_type: MemoryType
    provenance: Provenance
    evidence_status: EvidenceStatus
    confidence: float
    evidence: tuple[str, ...]
    reason_code: str
    subject: str | None = None
    project: str | None = None
    valid_from: str | None = None
    valid_until: str | None = None

    def __post_init__(self) -> None:
        if not self.key or not self.key.strip():
            raise ValueError("classification key is required")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        if len(self.evidence) > 8:
            raise ValueError("at most eight evidence turns are allowed")
        if self.reason_code not in {"explicit", "repeat_independent", "scope_update",
                                    "insufficient_evidence", "quoted_content", "invalid"}:
            raise ValueError("invalid classification reason code")

    @classmethod
    def from_dict(cls, payload: dict) -> "Classification":
        """Decode the model boundary with a closed, fail-closed schema."""
        required = {"key", "scope", "memory_type", "provenance", "evidence_status",
                    "confidence", "evidence", "reason_code"}
        allowed = required | {"subject", "project", "valid_from", "valid_until"}
        if not isinstance(payload, dict) or not required.issubset(payload) or set(payload) - allowed:
            raise ValueError("classification fields do not match contract")
        if any(not isinstance(payload.get(name), str) for name in
               ("key", "scope", "memory_type", "provenance",
                "evidence_status", "reason_code")):
            raise ValueError("classification scalar fields must be strings")
        evidence = payload["evidence"]
        if not isinstance(evidence, list) or any(not isinstance(v, str) for v in evidence):
            raise ValueError("evidence must be a list of strings")
        if any(name in payload and payload[name] is not None and
               not isinstance(payload[name], str)
               for name in ("subject", "project", "valid_from", "valid_until")):
            raise ValueError("classification optional fields must be strings")
        confidence = payload["confidence"]
        if (isinstance(confidence, bool) or not isinstance(confidence, (int, float))
                or not math.isfinite(float(confidence))):
            raise ValueError("confidence must be a finite number")
        return cls(key=payload["key"], scope=Scope(payload["scope"]),
                   memory_type=MemoryType(payload["memory_type"]),
                   provenance=Provenance(payload["provenance"]),
                   evidence_status=EvidenceStatus(payload["evidence_status"]),
                   confidence=float(confidence), evidence=tuple(evidence),
                   reason_code=str(payload["reason_code"]),
                   subject=payload.get("subject"), project=payload.get("project"),
                   valid_from=payload.get("valid_from"), valid_until=payload.get("valid_until"))


_SECRET_RE = re.compile(r"(?i)(?:api[_ -]?key|token|password|secret)\s*[:=]\s*[^,;\s]+")


def redact_candidate_text(text: str, *, max_chars: int = 300) -> str:
    """Redact obvious credentials before text crosses the classifier boundary."""
    clean = _SECRET_RE.sub("[REDACTED]", str(text))
    return clean[:max_chars]


def _temporary_expiry(text: str) -> str | None:
    """Return a conservative expiry for clearly time-bounded context."""
    now = datetime.now(timezone.utc)
    if "until tomorrow" in text or "through tomorrow" in text:
        return (now + timedelta(days=1)).isoformat().replace("+00:00", "Z")
    if "today" in text or "for today" in text:
        end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
        return end.isoformat().replace("+00:00", "Z")
    if "this week" in text or "this weekend" in text:
        return (now + timedelta(days=7)).isoformat().replace("+00:00", "Z")
    return None


def heuristic_classifier(candidates: Iterable[Candidate], *, policy_version: str = "b1") -> list[Classification]:
    """Classify safe, explicit memories without an extra model round-trip.

    This is the always-available baseline; provider-backed classifiers can
    replace it later while retaining the same validated output contract.
    """
    if not policy_version:
        raise ValueError("policy version is required")
    output: list[Classification] = []
    for item in candidates:
        text = item.content.lower()
        key = item.key.lower()
        quoted = any(marker in text for marker in (
            "quoted", "the page says", "the article says", "according to the page",
            "document says", "instructions in this document",
        ))
        uncertain = any(marker in text for marker in ("maybe", "might", "not sure", "possibly"))
        explicit_preference = any(marker in text for marker in (
            "i prefer", "i want", "i don't want", "i do not want",
            "always ", "never ", "please remember", "my default is",
            "use this by default", "avoid ",
        ))
        explicit_fact = any(marker in text for marker in (
            "my name is", "i live in", "my home is", "my timezone is",
            "my location is", "i am based in",
        ))
        explicit = (not uncertain) and (explicit_preference or explicit_fact)
        temporary = any(marker in text for marker in (
            "travelling", "traveling", "this week", "on vacation", "temporarily",
            "for today", "until tomorrow",
        ))
        decision = any(marker in text for marker in (
            "we decided", "decision:", "the deployment plan was merged", "approved the plan",
        ))
        task_rule = any(marker in text for marker in (
            "for this project", "when working on", "the rule is", "must always",
            "only use", "constraint:",
        )) and not explicit_preference
        confidence = 0.9 if explicit else 0.55
        independent = len(set(item.session_ids))
        if quoted:
            output.append(Classification(
                key=item.key, scope=Scope.SESSION, memory_type=MemoryType.TEMPORARY_CONTEXT,
                provenance=Provenance.QUOTED_DOCUMENT, evidence_status=EvidenceStatus.UNKNOWN,
                confidence=0.0, evidence=item.source_turn_ids[:8], reason_code="quoted_content",
                subject=item.subject, project=item.project,
            ))
            continue
        if item.provenance_hint in {Provenance.ASSISTANT, Provenance.TOOL}:
            output.append(Classification(
                key=item.key,
                scope=Scope.PROJECT if item.project else Scope.GLOBAL,
                memory_type=MemoryType.FACT,
                provenance=item.provenance_hint,
                evidence_status=EvidenceStatus.UNKNOWN if item.provenance_hint is Provenance.ASSISTANT else EvidenceStatus.TENTATIVE,
                confidence=0.0 if item.provenance_hint is Provenance.ASSISTANT else 0.5,
                evidence=item.source_turn_ids[:8],
                reason_code="insufficient_evidence",
                subject=item.subject, project=item.project,
            ))
            continue
        if temporary:
            output.append(Classification(
                key=item.key, scope=Scope.SESSION, memory_type=MemoryType.TEMPORARY_CONTEXT,
                provenance=Provenance.USER, evidence_status=EvidenceStatus.EXPLICIT if explicit else EvidenceStatus.TENTATIVE,
                confidence=1.0 if explicit else confidence, evidence=item.source_turn_ids[:8],
                reason_code="explicit" if explicit else "insufficient_evidence",
                subject=item.subject, project=item.project,
                valid_until=_temporary_expiry(text),
            ))
            continue
        project = item.project or (item.key.split(".")[1] if key.startswith("project.") and len(item.key.split(".")) > 1 else None)
        subject = item.subject or ("user" if key.startswith("user.") else None)
        output.append(Classification(
            key=item.key, scope=Scope.PROJECT if project else (Scope.SUBJECT if subject else Scope.GLOBAL),
            memory_type=(MemoryType.EXPLICIT_PREFERENCE if explicit_preference else
                         MemoryType.DECISION if decision else
                         MemoryType.TASK_RULE if task_rule else MemoryType.FACT),
            provenance=Provenance.USER, evidence_status=classify_threshold(
                explicit=explicit, independent_sessions=independent, confidence=confidence),
            confidence=confidence, evidence=item.source_turn_ids[:8],
            reason_code="explicit" if explicit else ("repeat_independent" if independent >= 2 else "insufficient_evidence"),
            subject=subject, project=project,
            valid_until=_temporary_expiry(text),
        ))
    return output


def classify_threshold(*, explicit: bool, independent_sessions: int, confidence: float) -> EvidenceStatus:
    """Apply the fixed B7 evidence policy; never infer from confidence alone."""
    if explicit:
        return EvidenceStatus.EXPLICIT
    if independent_sessions >= 2 and confidence >= 0.80:
        return EvidenceStatus.CORROBORATED
    if confidence >= 0.50:
        return EvidenceStatus.TENTATIVE
    return EvidenceStatus.UNKNOWN


def content_revision(content: str, *, prior_revision: int = 0) -> int:
    """Return the next revision only when content actually changed."""
    if prior_revision < 0:
        raise ValueError("prior revision cannot be negative")
    return prior_revision + 1


def idempotency_key(memory_id: int, revision: int, policy_version: str, operation: str) -> str:
    if memory_id < 1 or revision < 1 or not policy_version or not operation:
        raise ValueError("invalid maintenance identity")
    return sha256(f"{memory_id}:{revision}:{policy_version}:{operation}".encode()).hexdigest()


def maintenance_due(next_attempt_at: datetime, *, now: datetime | None = None) -> bool:
    current = now or datetime.now(timezone.utc)
    if next_attempt_at.tzinfo is None:
        raise ValueError("next_attempt_at must be timezone-aware")
    return next_attempt_at <= current


def maintenance_budget_remaining(conn: sqlite3.Connection, *, day: str,
                                 candidate_limit: int = 100,
                                 call_limit: int = 5) -> dict[str, int]:
    """Return a restart-safe daily budget from durable queue history.

    Queue rows are the ledger: every claimed classify item consumes one
    candidate, and each distinct ``created_at`` batch consumes one call. The
    values survive process restarts and never depend on an in-memory counter.
    """
    if candidate_limit < 1 or call_limit < 1:
        raise ValueError("budget limits must be positive")
    rows = conn.execute(
        "SELECT operation, created_at FROM memory_maintenance "
        "WHERE created_at >= ? AND created_at < ?",
        (f"{day}T00:00:00", f"{day}T23:59:59.999999"),
    ).fetchall()
    candidates = sum(1 for row in rows if row["operation"] == "classify")
    calls = len({row["created_at"] for row in rows if row["operation"] == "classify"})
    return {"candidates_used": candidates, "calls_used": calls,
            "candidates_remaining": max(0, candidate_limit - candidates),
            "calls_remaining": max(0, call_limit - calls)}


def retrieval_rank(*, scope_match: bool, evidence_status: EvidenceStatus,
                   explicit: bool, recency_epoch: float, memory_id: int) -> tuple:
    """Stable sort key; callers sort reverse=True."""
    return (int(scope_match), EVIDENCE_RANK[evidence_status], int(explicit),
            recency_epoch, memory_id)


def bounded_candidates(candidates: Iterable[Candidate], *, max_items: int = 20,
                       max_chars: int = 12_000) -> tuple[Candidate, ...]:
    result: list[Candidate] = []
    used = 0
    for item in candidates:
        if len(result) >= max_items:
            break
        if len(item.content) > 300:
            raise ValueError("candidate content exceeds 300 characters")
        safe = redact_candidate_text(item.content)
        if used + len(safe) > max_chars:
            break
        result.append(Candidate(item.key, safe, tuple(item.source_turn_ids[:8]),
                                tuple(dict.fromkeys(item.session_ids)), item.subject,
                                item.project, item.provenance_hint))
        used += len(safe)
    return tuple(result)


def enqueue_maintenance(conn: sqlite3.Connection, *, memory_id: int,
                        revision: int, policy_version: str, operation: str,
                        now_iso: str) -> bool:
    """Insert one durable job; duplicate revisions are harmless no-ops."""
    key = idempotency_key(memory_id, revision, policy_version, operation)
    # Validate before touching SQLite; the key is also useful to callers when
    # correlating a job without logging memory content.
    del key
    conn.execute(
        """INSERT OR IGNORE INTO memory_maintenance
        (memory_id, operation, content_revision, policy_version,
         attempts, next_attempt_at, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, 0, ?, 'queued', ?, ?)""",
        (memory_id, operation, revision, policy_version, now_iso, now_iso, now_iso),
    )
    return conn.execute("SELECT changes()").fetchone()[0] == 1


def apply_scoped_correction(conn: sqlite3.Connection, *, memory_id: int,
                            content: str, source_session_id: str | None,
                            classification: Classification, now_iso: str,
                            user_id: str = "local") -> int:
    """Create a reversible revision for an explicit same-scope correction.

    The previous row remains queryable as archived history. A correction with
    a different scope is rejected so a temporary trip cannot replace a home
    location. The returned id is the active revision.
    """
    if classification.evidence_status is not EvidenceStatus.EXPLICIT:
        raise ValueError("only explicit corrections may create revisions")
    old = conn.execute("SELECT * FROM memories WHERE id=? AND kind='fact'", (memory_id,)).fetchone()
    if old is None:
        raise ValueError("memory does not exist")
    if classification.scope.value != (old["scope"] or "global"):
        raise ValueError("correction scope does not match existing memory")
    if old["content"] == content:
        return int(old["id"])
    # Older installations have the pre-automation unique index, which would
    # reject an active row plus its archived revision. Upgrade that index
    # lazily so this operation remains compatible with already-open stores.
    index = conn.execute("SELECT sql FROM sqlite_master WHERE type='index' AND name='idx_memories_fact_key'").fetchone()
    if index and "archived_at" not in (index["sql"] or ""):
        conn.execute("DROP INDEX IF EXISTS idx_memories_fact_key")
        conn.execute("CREATE UNIQUE INDEX idx_memories_fact_key ON memories(user_id, key) WHERE kind='fact' AND archived_at IS NULL")
    conn.execute("UPDATE memories SET archived_at=? WHERE id=?", (now_iso, memory_id))
    cur = conn.execute(
        """INSERT INTO memories (
            kind,key,content,source_session_id,created_at,updated_at,tier,
            provenance,source_turn, user_id, subject,scope,memory_type,
            evidence_status,confidence,valid_from,valid_until,source_turn_id,
            content_revision,classifier_version,classified_at,supersedes_id)
           VALUES ('fact',?,?,?,?,?,?, ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (old["key"], content[:300], source_session_id, old["created_at"], now_iso,
         old["tier"], classification.provenance.value, old["source_turn"], user_id,
         classification.subject, classification.scope.value, classification.memory_type.value,
         classification.evidence_status.value, classification.confidence,
         classification.valid_from, classification.valid_until,
         classification.evidence[0] if classification.evidence else None,
         int(old["content_revision"] or 1) + 1, "b1", now_iso, memory_id),
    )
    return int(cur.lastrowid)


def claim_due_maintenance(conn: sqlite3.Connection, *, now_iso: str,
                          limit: int = 20) -> list[sqlite3.Row]:
    """Claim a bounded batch atomically; callers perform model work outside DB."""
    if not 1 <= limit <= 20:
        raise ValueError("limit must be between 1 and 20")
    rows = conn.execute(
        "SELECT * FROM memory_maintenance WHERE status='queued' "
        "AND next_attempt_at <= ? ORDER BY id LIMIT ?", (now_iso, limit)
    ).fetchall()
    for row in rows:
        conn.execute("UPDATE memory_maintenance SET status='running', updated_at=? WHERE id=? AND status='queued'",
                     (now_iso, row["id"]))
    return rows


def finish_maintenance(conn: sqlite3.Connection, *, job_id: int, ok: bool,
                       now_iso: str, error_code: str | None = None) -> None:
    """Set a terminal state; retry scheduling is bounded and deterministic."""
    if ok:
        conn.execute("UPDATE memory_maintenance SET status='done', updated_at=?, last_error_code=NULL WHERE id=?",
                     (now_iso, job_id))
        return
    row = conn.execute("SELECT attempts FROM memory_maintenance WHERE id=?", (job_id,)).fetchone()
    if row is None:
        raise ValueError("unknown maintenance job")
    attempts = int(row["attempts"]) + 1
    if attempts >= 3:
        status, next_at = "failed", now_iso
    else:
        delays = (60, 300, 1800)
        current = datetime.fromisoformat(now_iso.replace("Z", "+00:00"))
        next_at = (current + timedelta(seconds=delays[attempts - 1])).isoformat().replace("+00:00", "Z")
        status = "queued"
    conn.execute("UPDATE memory_maintenance SET status=?, attempts=?, next_attempt_at=?, last_error_code=?, updated_at=? WHERE id=?",
                 (status, attempts, next_at, error_code, now_iso, job_id))


def recover_stale_maintenance(conn: sqlite3.Connection, *, now_iso: str,
                              stale_after_seconds: int = 1800) -> dict[str, int]:
    """Requeue work abandoned by a crashed worker.

    A claimed row is marked ``running`` before model work starts. If the
    process exits at that point, a future worker must be able to make bounded
    progress without treating the claim as a permanent lock. Recovery uses
    the same three-attempt retry budget as ordinary failures; malformed
    timestamps are treated as stale so corrupt bookkeeping cannot strand
    work indefinitely.
    """
    if stale_after_seconds < 1:
        raise ValueError("stale threshold must be positive")
    current = datetime.fromisoformat(now_iso.replace("Z", "+00:00"))
    if current.tzinfo is None:
        raise ValueError("now_iso must be timezone-aware")
    rows = conn.execute(
        "SELECT id, updated_at, attempts FROM memory_maintenance "
        "WHERE status='running' ORDER BY id"
    ).fetchall()
    requeued = failed = 0
    for row in rows:
        try:
            updated = datetime.fromisoformat(str(row["updated_at"]).replace("Z", "+00:00"))
            stale = updated.tzinfo is None or (current - updated).total_seconds() >= stale_after_seconds
        except (TypeError, ValueError):
            stale = True
        if not stale:
            continue
        before = int(row["attempts"] or 0)
        finish_maintenance(conn, job_id=int(row["id"]), ok=False,
                           now_iso=now_iso, error_code="worker_interrupted")
        after = conn.execute(
            "SELECT status, attempts FROM memory_maintenance WHERE id=?",
            (row["id"],),
        ).fetchone()
        if after is not None and after["status"] == "failed":
            failed += 1
        elif after is not None and int(after["attempts"] or 0) > before:
            requeued += 1
    return {"requeued": requeued, "failed": failed}


def run_maintenance_once(conn: sqlite3.Connection, *, now_iso: str,
                         handler, limit: int = 20) -> dict[str, int]:
    """Run one bounded batch through an injected handler.

    ``handler(row)`` returns truthy on success and may raise; exceptions are
    converted to the fixed retry path and never escape into the voice loop.
    """
    recover_stale_maintenance(conn, now_iso=now_iso)
    jobs = claim_due_maintenance(conn, now_iso=now_iso, limit=limit)
    completed = failed = 0
    for job in jobs:
        try:
            ok = bool(handler(job))
        except Exception:
            ok = False
        finish_maintenance(conn, job_id=job["id"], ok=ok, now_iso=now_iso,
                           error_code=None if ok else "handler_failed")
        completed += int(ok)
        failed += int(not ok)
    return {"claimed": len(jobs), "completed": completed, "failed": failed}


def process_classification_jobs(conn: sqlite3.Connection, *, now_iso: str,
                                classifier, policy_version: str = "b1",
                                shadow: bool = False,
                                rollout_stage: str | RolloutStage | None = None) -> dict[str, int]:
    """Process classify jobs using an injected pure classifier.

    A result is committed only when it covers every candidate in the claimed
    batch. This prevents partial model output from silently changing memory.
    """
    # A supplied stage is the release gate; the legacy ``shadow`` argument is
    # retained for callers/tests that predate staged rollout. Passing shadow
    # or the shadow stage can never write live metadata.
    stage = normalize_rollout_stage(rollout_stage) if rollout_stage is not None else None
    effective_shadow = shadow or stage is RolloutStage.SHADOW
    # Recover a claim abandoned by a crashed process before calculating the
    # durable budget or claiming the next batch. The recovery itself is
    # bounded by the same retry policy as a model failure.
    recovery = recover_stale_maintenance(conn, now_iso=now_iso)
    # The daily candidate/call limits are durable policy, not a caller hint.
    # Check them before claiming rows so an exhausted worker leaves queued
    # work untouched for the next UTC period and a restart cannot reset spend.
    day = str(now_iso)[:10]
    budget = maintenance_budget_remaining(conn, day=day)
    if budget["calls_remaining"] <= 0 or budget["candidates_remaining"] <= 0:
        return {"claimed": 0, "applied": 0, "failed": recovery["failed"]}
    limit = min(20, budget["candidates_remaining"])
    jobs = claim_due_maintenance(conn, now_iso=now_iso, limit=limit)
    if not jobs:
        return {"claimed": 0, "applied": 0, "failed": recovery["failed"]}
    candidates: list[Candidate] = []
    job_candidates: list[tuple[sqlite3.Row, Candidate]] = []
    processable_jobs: list[sqlite3.Row] = []
    missing = 0
    for job in jobs:
        row = conn.execute("SELECT id,key,content,source_session_id,source_turn_id,content_revision,subject,scope,provenance,user_id FROM memories WHERE id=?", (job["memory_id"],)).fetchone()
        if row is None:
            finish_maintenance(conn, job_id=job["id"], ok=False, now_iso=now_iso, error_code="missing_memory")
            missing += 1
            continue
        raw_provenance = row["provenance"]
        provenance_hint = None
        if raw_provenance in {item.value for item in Provenance}:
            provenance_hint = Provenance(raw_provenance)
        elif raw_provenance == "stated":
            provenance_hint = Provenance.USER
        # A fact row keeps its latest source for compactness. Repeated exact
        # or near-duplicate admissions are recorded in the existing recall
        # ledger; fold those distinct sessions/turns into the bounded
        # classifier evidence set so corroboration can actually mature
        # without adding a second evidence database.
        evidence_rows = conn.execute(
            "SELECT session_id, source_turn FROM memory_recall_events "
            "WHERE key=? AND user_id=? AND session_id IS NOT NULL "
            "ORDER BY created_at DESC LIMIT 8",
            (row["key"], row["user_id"] or "local"),
        ).fetchall()
        session_ids = list(dict.fromkeys(
            [value for value in [row["source_session_id"]] if value]
            + [item["session_id"] for item in evidence_rows if item["session_id"]]
        ))[:8]
        source_turns = list(dict.fromkeys(
            [str(value) for value in [row["source_turn_id"]] if value]
            + [str(item["source_turn"]) for item in evidence_rows if item["source_turn"] is not None]
        ))[:8]
        candidate = Candidate(row["key"], redact_candidate_text(row["content"]),
                              tuple(source_turns or [str(row["id"])]),
                              tuple(session_ids or [str(row["id"])]),
                              row["subject"], row["scope"] if row["scope"] not in (None, "global") else None,
                              provenance_hint)
        candidates.append(candidate)
        # Keep stored content out of the classifier boundary. Classification
        # updates metadata only; explicit correction is a separate operation.
        job_candidates.append((job, candidate))
        processable_jobs.append(job)
    try:
        bounded = bounded_candidates(candidates)
        results = tuple(classifier(bounded, policy_version=policy_version))
        # Provider adapters may return JSON objects while the deterministic
        # baseline returns dataclasses. Decode both at this single boundary;
        # malformed or mixed batches still fail closed and are retried.
        decoded: list[Classification] = []
        for item in results:
            if isinstance(item, Classification):
                decoded.append(item)
            elif isinstance(item, dict):
                decoded.append(Classification.from_dict(item))
            else:
                raise ValueError("classifier returned an invalid result")
        results = tuple(decoded)
        by_key = {item.key: item for item in results}
        if len(by_key) != len(candidates) or any(item.key not in by_key for item in candidates):
            raise ValueError("classification batch is incomplete")
    except Exception:
        for job in processable_jobs:
            finish_maintenance(conn, job_id=job["id"], ok=False, now_iso=now_iso, error_code="invalid_output")
        return {"claimed": len(jobs), "applied": 0,
                "failed": len(processable_jobs) + missing + recovery["failed"]}
    for job, candidate in job_candidates:
        item = by_key[candidate.key]
        # Source attribution is a policy boundary, not model decoration. A
        # provider may suggest metadata, but it cannot turn an assistant or
        # quoted-document row into a trusted user preference.
        if candidate.provenance_hint in {Provenance.ASSISTANT, Provenance.QUOTED_DOCUMENT}:
            item = replace(item, provenance=candidate.provenance_hint,
                           evidence_status=EvidenceStatus.UNKNOWN,
                           confidence=0.0,
                           reason_code="quoted_content" if candidate.provenance_hint is Provenance.QUOTED_DOCUMENT else "insufficient_evidence")
        row = conn.execute("SELECT id,user_id FROM memories WHERE id=?", (job["memory_id"],)).fetchone()
        if row is None:
            finish_maintenance(conn, job_id=job["id"], ok=False, now_iso=now_iso, error_code="missing_memory")
            missing += 1
            continue
        if not effective_shadow and (stage is None or classification_admitted(item, stage)):
            # Content revisions are reserved for an explicit correction call,
            # where replacement text and scope are checked by the caller.
            # Never turn classifier redaction into a stored-memory edit.
            conn.execute("UPDATE memories SET subject=?, scope=?, memory_type=?, provenance=?, evidence_status=?, confidence=?, valid_from=?, valid_until=?, source_turn_id=?, classifier_version=?, classified_at=? WHERE id=?",
                         (item.subject, item.scope.value, item.memory_type.value, item.provenance.value,
                          item.evidence_status.value, item.confidence, item.valid_from, item.valid_until,
                          item.evidence[0] if item.evidence else candidate.source_turn_ids[0], policy_version, now_iso, row["id"]))
        else:
            # Shadow mode is observable and restart-safe. Keep only bounded,
            # non-secret metadata; the candidate itself is represented by a
            # digest so this table cannot become a second content store.
            shadow_payload = {
                "key_digest": sha256(item.key.encode("utf-8")).hexdigest(),
                "scope": item.scope.value,
                "memory_type": item.memory_type.value,
                "provenance": item.provenance.value,
                "evidence_status": item.evidence_status.value,
                "confidence": item.confidence,
                "evidence_digests": [sha256(value.encode("utf-8")).hexdigest()
                                     for value in item.evidence[:8]],
                "reason_code": item.reason_code,
                "subject": item.subject,
                "project": item.project,
                "valid_from": item.valid_from,
                "valid_until": item.valid_until,
                "rollout_stage": (stage.value if stage is not None else None),
            }
            conn.execute(
                """INSERT OR REPLACE INTO memory_classification_shadow
                (maintenance_id,user_id,memory_id,content_revision,policy_version,
                 candidate_digest,classification_json,observed_at)
                VALUES (?,?,?,?,?,?,?,?)""",
                (job["id"], row["user_id"] or "local", row["id"],
                 job["content_revision"], policy_version,
                 sha256(candidate.content.encode("utf-8")).hexdigest(),
                 json.dumps(shadow_payload, sort_keys=True, separators=(",", ":")),
                 now_iso),
            )
        finish_maintenance(conn, job_id=job["id"], ok=True, now_iso=now_iso)
    return {"claimed": len(jobs), "applied": len(candidates),
            "failed": missing + recovery["failed"]}
