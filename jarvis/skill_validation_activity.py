"""Host-only asynchronous creator activity; never creates or reopens agent runs."""
from __future__ import annotations

import fcntl
import json
import logging
import uuid
from datetime import datetime, timezone

from jarvis.db import get_conn, now_iso
from jarvis.runlog.store import (
    MAX_SKILL_EVENTS,
    _accept_step_receipt,
    _next_skill_event_seq,
)
from jarvis.skill_creator_agent import CREATOR_PACKAGE_REVISION

logger = logging.getLogger(__name__)


def _bound_state(user_id, request_id):
    from jarvis import skill_requests as requests

    state = requests.get(user_id, request_id)
    if not state or state.get("operation") != "test":
        return None
    parent_id = state.get("parent_request_id")
    parent = requests.get(user_id, parent_id) if parent_id else None
    if (not parent or parent.get("operation") != "draft"
            or parent.get("skill_id") != state.get("skill_id")
            or parent.get("sandbox_job_id") != state.get("parent_job_id")
            or not state.get("originating_developer_run_id")
            or state.get("originating_developer_run_id") != parent.get("developer_run_id")
            or state.get("originating_creator_revision") != CREATOR_PACKAGE_REVISION
            or parent.get("creator_revision") != CREATOR_PACKAGE_REVISION
            or not state.get("validation_attempt_id")
            or not state.get("validation_started_at")):
        return None
    return state


def verify_validation_context(context):
    """Recheck host state and candidate evidence, independently of model output."""
    from jarvis import skill_requests as requests

    state = _bound_state(context["user_id"], context["validation_request_id"])
    if (not state or state.get("state") != "completed" or state.get("cancel_requested")
            or state.get("result_code") != "offline_validation_passed"
            or state["originating_developer_run_id"] != context["run_id"]
            or state["validation_attempt_id"] != context["attempt_id"]
            or state["originating_creator_revision"] != context["creator_revision"]):
        return False
    live = requests._service(state["skill_id"], expected_job_id=state["parent_job_id"]).status()
    return (
        live.get("run_id") == state["parent_job_id"]
        and live.get("validation_request_id") == state["request_id"]
        and live.get("validation_attempt_id") == state["validation_attempt_id"]
        and live.get("validated_ok") is True
        and isinstance(state.get("candidate_digest"), str)
        and requests._DIGEST.fullmatch(state["candidate_digest"]) is not None
        and isinstance(state.get("candidate_revision"), str)
        and requests._DIGEST.fullmatch(state["candidate_revision"]) is not None
        and live.get("candidate") == state["candidate_digest"]
        and live.get("package_revision") == state["candidate_revision"]
    )


def _event(user_id, state, *, start, db_path):
    run_id = state["originating_developer_run_id"]
    attempt = state["validation_attempt_id"]
    revision = state["originating_creator_revision"]
    conn = get_conn(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        run = conn.execute("SELECT agent FROM agent_runs WHERE user_id=? AND run_id=?",
                           (user_id, run_id)).fetchone()
        if run is None or run["agent"] != "developer":
            return "unavailable_run"
        if conn.execute("SELECT 1 FROM skill_events WHERE user_id=? AND run_id=? "
                        "AND type='protected_activity'", (user_id, run_id)).fetchone():
            return "protected"
        if not conn.execute(
            "SELECT 1 FROM skill_events WHERE user_id=? AND run_id=? AND request_id=? "
            "AND skill_id='skill-creator' AND skill_revision=? AND type='skill_selected'",
            (user_id, run_id, run_id, revision),
        ).fetchone():
            return "not_selected"
        events = conn.execute(
            "SELECT type FROM skill_events WHERE user_id=? AND run_id=? AND request_id=? "
            "AND skill_id='skill-creator' AND skill_revision=? AND step_id='offline-validate' "
            "AND attempt_id=?", (user_id, run_id, run_id, revision, attempt),
        ).fetchall()
        types = {row["type"] for row in events}
        if "skill_step_finished" in types or (start and "skill_step_started" in types):
            return "already_recorded"
        if not start and "skill_step_started" not in types:
            return "attempt_not_started"
        count = conn.execute("SELECT COUNT(*) FROM skill_events WHERE user_id=? AND run_id=?",
                             (user_id, run_id)).fetchone()[0]
        if count >= MAX_SKILL_EVENTS:
            return "event_limit_reached"
        status = "running" if start else ("failed" if state["state"] == "failed" else "unknown")
        conn.execute(
            "INSERT INTO skill_events (user_id, run_id, request_id, event_id, seq, schema_version, "
            "occurred_at, skill_id, skill_revision, step_id, attempt_id, type, status, evidence_refs) "
            "VALUES (?, ?, ?, ?, ?, 1, ?, 'skill-creator', ?, 'offline-validate', ?, ?, ?, ?)",
            (user_id, run_id, run_id, str(uuid.uuid4()), _next_skill_event_seq(conn, user_id, run_id),
             now_iso(), revision, attempt, "skill_step_started" if start else "skill_step_finished",
             status, json.dumps([{"kind": "artifact_id", "id": state["request_id"]}])),
        )
        conn.commit()
        return "recorded"
    finally:
        conn.close()


def sync_validation_activity(user_id, request_id, *, start=False, db_path=None):
    """Append idempotent activity while cancellation is excluded by the job lock.

    Only the worker may call start=True before validation; recovery never
    backfills a missing started event. All failures are content-free telemetry.
    """
    from jarvis import skill_requests as requests
    from jarvis.skill_step_checks import (
        MAX_RECEIPT_TTL,
        RECEIPT_ISSUER,
        issue_host_controller_receipt,
    )

    try:
        _, lock_path = requests._paths(user_id, request_id)
        with lock_path.open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            state = _bound_state(user_id, request_id)
            if state is None:
                return "unbound"
            if start:
                if state["state"] != "testing" or state.get("cancel_requested"):
                    return "not_startable"
                return _event(user_id, state, start=True, db_path=db_path)
            if state["state"] == "completed" and not state.get("cancel_requested"):
                run_id = state["originating_developer_run_id"]
                now = datetime.now(timezone.utc)
                fields = {
                    "schema_version": 1, "receipt_id": str(uuid.uuid4()), "issuer": RECEIPT_ISSUER,
                    "issued_at": now.isoformat(), "expires_at": (now + MAX_RECEIPT_TTL).isoformat(),
                    "user_id": user_id, "run_id": run_id, "request_id": run_id,
                    "skill_id": "skill-creator", "skill_revision": state["originating_creator_revision"],
                    "step_id": "offline-validate", "attempt_id": state["validation_attempt_id"],
                }
                receipt = issue_host_controller_receipt(fields, context={
                    "user_id": user_id, "validation_request_id": request_id, "run_id": run_id,
                    "attempt_id": state["validation_attempt_id"],
                    "creator_revision": state["originating_creator_revision"],
                })
                return _accept_step_receipt(receipt, user_id=user_id, run_id=run_id,
                                            db_path=db_path, deferred_creator=True)
            if state["state"] in {"failed", "cancelled", "cancel_requested", "needs_reconciliation"}:
                return _event(user_id, state, start=False, db_path=db_path)
            return "pending"
    except Exception as exc:  # noqa: BLE001 — optional telemetry must not fail validation
        logger.info("validation_activity_unavailable error_type=%s", type(exc).__name__)
        return "unavailable"
