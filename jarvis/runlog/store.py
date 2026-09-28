"""RunLogger: durable per-run logging for sub-agent delegations.

MORTIMER_RUN_LOGGING_PLAN.md §5.3/§5.3a. One RunLogger instance per
delegation (created in SubAgent.run(), plan §5.4). Every public method
swallows its own exceptions and logs once at WARNING (plan D6) — a
run-logging failure must never affect the voice pipeline.

Two-tier storage (plan D5): SQLite (agent_runs/agent_events, migration
0006 in jarvis/db.py) holds bounded, indexed previews; the full,
untruncated payload for one run (arguments, results, the final reply)
is buffered in memory and written once, at run end, to a single JSONL
file under logs/agents/<date>/<run_id>.jsonl (plan D7). See §5.3a for the
exact JSONL record shapes — three separate consumers (CLI, admin API,
console panel) read this file and must agree on its fields.

A run's buffered payload is bounded (plan D8): once MAX_BUFFERED_EVENTS
or MAX_PAYLOAD_BYTES is exceeded, further payload values are replaced
with a fixed marker string and one `truncated` record is appended.
SQLite previews are never affected by this cap — they are bounded by
PREVIEW_CHARS regardless.
"""

from __future__ import annotations

import base64
import json
import logging
import re
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from jarvis.db import get_conn, now_iso
from jarvis.sensitive import (
    detect_financial,  # stdlib-only; no bot-package import cycle
)
from jarvis.skill_step_checks import (
    SkillStepCheckReceipt,
    SkillStepReceiptError,
    load_required_check_ids,
    validate_skill_step_receipt,
)
from jarvis.tenant import current_user_id

logger = logging.getLogger(__name__)

# ⚙ TUNING KNOB (plan §6) — chars kept in SQLite preview columns. Full
# values always go to the JSONL payload regardless of this value.
PREVIEW_CHARS = 2000

# ⚙ TUNING KNOB (plan §6, D8) — caps on one run's buffered payload, so a
# pathological run (a runaway tool loop, a huge tool result) cannot
# exhaust memory.
MAX_BUFFERED_EVENTS = 200
MAX_PAYLOAD_BYTES = 5_000_000

# ⚙ TUNING KNOB (plan §6, D9) — a `running` row older than this is
# displayed as `orphaned` by readers (list_runs/get_run below). The
# stored row itself is never rewritten — this is a presentation rule
# only, so it is idempotent and cannot corrupt data.
ORPHAN_AFTER_S = 300

# ⚙ TUNING KNOB (MORTIMER_AGENT_TRUST_PLAN.md D16/D20) — a `running` row
# older than this at BOT STARTUP is rewritten to `orphaned` by
# reconcile_orphaned_runs below. Deliberately a separate, larger constant
# from ORPHAN_AFTER_S above: that one only changes what a live reader
# *displays* for a run that might still be in flight; this one only runs
# once at startup, when nothing in the process is holding any run open,
# so anything still `running` at that moment is definitionally orphaned
# (D16's rationale) — the larger value just keeps it from ever being
# mistaken for the display-only threshold.
RUN_ORPHAN_AFTER_S = 900

RUNLOG_DIR = Path("logs/agents")

_DROPPED = "<dropped: run payload cap exceeded>"

# T4a K3 — replaces a payload value on a sensitive turn. A STRING, and
# deliberately shaped like the _DROPPED sentinel above, so every reader
# (mcp_runlog/logic.py, the Runs drawer tab, tests) still finds every key
# present with the type it expects. K3: "run-log payloads reduced to tool
# names" — the tool name, seq, ok and latency are always kept.
SENSITIVE_SENTINEL = "<sensitive>"

# Must exactly match jarvis.agents.base.TIMEOUT_MESSAGE. Duplicated here
# (rather than imported) because jarvis.agents.base imports jarvis.runlog
# — importing it back would be a cycle. tests/unit/test_runlog_store.py
# asserts the two stay equal so they cannot silently drift apart.
_TIMEOUT_MESSAGE = "FAILED: the task took too long; please try again."

_SINCE_RE = re.compile(r"^(\d+)([dhm])$")
_SKILL_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_SKILL_REVISION_RE = re.compile(r"^[a-f0-9]{64}$")
_SKILL_EVENT_TYPES = frozenset({
    "skill_selected", "skill_resource_read", "skill_step_started",
    "skill_step_finished", "skill_step_skipped", "skill_selection_refused",
})
_SKILL_EVENT_STATUSES = frozenset({"running", "passed", "failed", "skipped", "unknown"})
_SKILL_EVIDENCE_KINDS = frozenset({"tool_call_id", "check_receipt_id", "artifact_id"})
MAX_SKILL_EVENTS = 256
MAX_SKILL_EVIDENCE_REFS = 8


def _next_skill_event_seq(conn, user_id: str, run_id: str, *, minimum: int = 1) -> int:
    """Allocate against durable activity, inside the caller's write transaction.

    The insert must use the same BEGIN IMMEDIATE transaction. A process-local
    RunLogger counter alone cannot order activity written by a later worker.
    """
    last = conn.execute(
        "SELECT MAX(seq) FROM skill_events WHERE user_id=? AND run_id=?",
        (user_id, run_id),
    ).fetchone()[0]
    return max(minimum, 1 if last is None else last + 1)


def _truncate(value: str, limit: int = PREVIEW_CHARS) -> str:
    return value if len(value) <= limit else value[:limit]


class RunLogger:
    """One instance per sub-agent run (plan D1, D3, D17).

    The ContextVar in jarvis.runlog.context holds the *instance*, not a
    bare run_id, so SkillRegistry.call() can record mcp_call events on
    the same buffer SubAgent is writing tool_call/tool_result events to
    (plan D3) — otherwise MCP-layer failures would never reach the JSONL
    payload.
    """

    def __init__(
        self,
        run_id: str,
        agent: str,
        display_name: str,
        task: str,
        *,
        session_id: str | None = None,
        enabled: bool = True,
        db_path: str | Path | None = None,
        root: Path | None = None,
        model: str | None = None,
        sensitive: bool = False,
    ) -> None:
        self.run_id = run_id
        self.agent = agent
        self.display_name = display_name
        self.task = task
        self.session_id = session_id
        self.enabled = enabled
        self.payload_path: Path | None = None
        # MORTIMER_PLANNING_PATHWAY_PLAN.md P3 — which model authored this
        # run (settings.openai_model), NULL when the caller doesn't pass
        # one (never re-derived or defaulted here; the caller is the only
        # place that has settings in hand).
        self.model = model
        # T4a K3 (plan D-H7). Snapshotted at construction because a delegation
        # runs in a DETACHED task that outlives the turn — reading the live
        # flag at write time would see it cleared (review F6).
        self._sensitive = sensitive
        self.user_id = current_user_id()

        self._db_path = db_path
        self._root = root if root is not None else Path(".")

        self._seq = 0
        self._buffer: list[dict[str, Any]] = []
        self._payload_bytes = 0
        self._capped = False
        self._finished = False
        self._started_at: str | None = None
        self._tool_count = 0
        # MORTIMER_AGENT_TRUST_PLAN.md D5 — counted here (mirroring
        # _tool_count's existing pattern) rather than passed in from
        # SubAgent._loop, so the classifier's verdict (jarvis.toolresult,
        # D1) recorded via tool_result() below is the ONLY source of these
        # counts. Two independent counters would risk drifting apart.
        self._tools_ok = 0
        self._tools_failed = 0

    # -- internal helpers ---------------------------------------------

    def _next_seq(self) -> int:
        seq = self._seq
        self._seq += 1
        return seq

    def _next_skill_seq(self, conn) -> int:
        seq = _next_skill_event_seq(
            conn, self.user_id, self.run_id, minimum=self._seq,
        )
        self._seq = seq + 1
        return seq

    def _redact(self, value: str) -> bool:
        if self._sensitive:
            return True
        try:
            return detect_financial(value) is not None
        except Exception:  # noqa: BLE001 — logging must never break the run
            return False

    def mark_sensitive(self) -> None:
        """Redact future records and scrub any earlier skill trace for this run."""
        self._sensitive = True

        def _scrub_skill_trace() -> None:
            conn = get_conn(self._db_path)
            try:
                conn.execute("BEGIN IMMEDIATE")
                existed = conn.execute(
                    "SELECT 1 FROM skill_events WHERE user_id=? AND run_id=? LIMIT 1",
                    (self.user_id, self.run_id),
                ).fetchone() is not None
                # Preserve the cursor high-water mark before deleting traces.
                # A worker may have appended beyond this logger's counter.
                scrub_seq = self._next_skill_seq(conn)
                conn.execute(
                    "DELETE FROM skill_events WHERE user_id=? AND run_id=?",
                    (self.user_id, self.run_id),
                )
                conn.execute(
                    "DELETE FROM skill_step_check_receipts WHERE user_id=? AND run_id=?",
                    (self.user_id, self.run_id),
                )
                if existed:
                    conn.execute(
                        "INSERT INTO skill_events (user_id, run_id, request_id, event_id, "
                        "seq, schema_version, occurred_at, type, status, evidence_refs) "
                        "VALUES (?, ?, ?, ?, ?, 1, ?, 'protected_activity', 'unknown', '[]')",
                        (self.user_id, self.run_id, self.run_id, str(uuid.uuid4()),
                         scrub_seq, now_iso()),
                    )
                conn.commit()
            finally:
                conn.close()

        self._safe("skill_trace_redaction", _scrub_skill_trace)

    def _trip_cap(self, added_bytes: int) -> bool:
        """Update byte/event counters; return True the first moment
        either cap is exceeded, so the caller marks its own record as
        dropped and emits the truncated marker."""
        self._payload_bytes += added_bytes
        if (
            len(self._buffer) + 1 >= MAX_BUFFERED_EVENTS
            or self._payload_bytes > MAX_PAYLOAD_BYTES
        ):
            self._capped = True
            return True
        return False

    def _append(
        self,
        record: dict[str, Any],
        *,
        payload_key: str | None = None,
        payload_value: Any = None,
        size_str: str | None = None,
    ) -> None:
        """Append `record` to the buffer, applying the D8 cap to
        `record[payload_key]` when given. If this record trips the cap
        for the first time, its own payload becomes the dropped marker
        and a `truncated` record is appended immediately after it."""
        just_capped = False
        if payload_key is not None:
            if self._capped:
                record[payload_key] = _DROPPED
            else:
                just_capped = self._trip_cap(
                    len((size_str or "").encode("utf-8", errors="ignore"))
                )
                record[payload_key] = _DROPPED if just_capped else payload_value
        self._buffer.append(record)
        if just_capped:
            reason = "events" if len(self._buffer) >= MAX_BUFFERED_EVENTS else "bytes"
            self._buffer.append({
                "type": "truncated",
                "seq": self._next_seq(),
                "reason": reason,
                "dropped_after_seq": record["seq"],
                "at": now_iso(),
            })

    def _execute(self, sql: str, params: tuple) -> None:
        conn = get_conn(self._db_path)
        try:
            conn.execute(sql, params)
            conn.commit()
        finally:
            conn.close()

    def _safe(self, op: str, fn) -> None:
        if not self.enabled:
            return
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 — plan D6, never raise
            logger.warning(
                "runlog_write_failed run_id=%s op=%s error_type=%s",
                self.run_id, op, type(exc).__name__[:64],
            )

    def _derive_status(self, reply: str) -> str:
        if reply == _TIMEOUT_MESSAGE:
            return "timeout"
        if reply.startswith("CANCELLED:"):
            return "cancelled"
        if reply.startswith("FAILED:"):
            return "failed"
        return "ok"

    def _elapsed_ms(self, ended_at: str) -> int | None:
        if not self._started_at:
            return None
        try:
            start = datetime.fromisoformat(self._started_at)
            end = datetime.fromisoformat(ended_at)
        except ValueError:
            return None
        return int((end - start).total_seconds() * 1000)

    def _write_payload(self) -> None:
        if self.payload_path is None:
            return
        full_path = self._root / self.payload_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        with full_path.open("w", encoding="utf-8") as f:
            for record in self._buffer:
                f.write(json.dumps(record, default=str))
                f.write("\n")

    # -- public API ------------------------------------------------------

    def start(self) -> None:
        def _do() -> None:
            self._started_at = now_iso()
            date = self._started_at[:10]
            self.payload_path = RUNLOG_DIR / date / f"{self.run_id}.jsonl"
            # T4a K3 (P12, review F5) — task is known at construction, so the
            # snapshot alone suffices.
            task = SENSITIVE_SENTINEL if self._redact(self.task) else self.task
            self._buffer.append({
                "type": "run_start",
                "seq": self._next_seq(),
                "run_id": self.run_id,
                "agent": self.agent,
                "display_name": self.display_name,
                "session_id": self.session_id,
                "task": task,
                "started_at": self._started_at,
            })
            self._execute(
                "INSERT INTO agent_runs (run_id, session_id, agent, "
                "display_name, task, status, started_at, tool_count, model, user_id) "
                "VALUES (?, ?, ?, ?, ?, 'running', ?, 0, ?, ?)",
                (self.run_id, self.session_id, self.agent, self.display_name,
                 task, self._started_at, self.model, self.user_id),
            )
        self._safe("start", _do)

    def skill_event(
        self,
        skill_id: str,
        skill_revision: str,
        event_type: str,
        *,
        request_id: str | None = None,
        step_id: str | None = None,
        attempt_id: str | None = None,
        status: str = "unknown",
        evidence_refs: list[dict[str, str]] | None = None,
    ) -> None:
        """Persist one validated, content-free Skills execution receipt.

        This is best-effort telemetry: malformed input or a storage failure
        never interrupts the agent run. Protected executions persist only a
        generic lifecycle marker, with every skill-specific value removed.

        This generic event path cannot assert process-step success. Successful
        tool calls and model-authored progress are not proof that a step's
        acceptance criteria passed. Passed step events require the separate
        controller-issued, mapped check-receipt path below.
        """
        if event_type == "skill_step_finished" and status == "passed":
            return
        self._skill_event_impl(
            skill_id, skill_revision, event_type,
            request_id=request_id, step_id=step_id, attempt_id=attempt_id,
            status=status, evidence_refs=evidence_refs,
        )

    def accept_skill_step_check_receipt(self, value: object) -> str:
        """Persist a mapped, signed check for a started attempt on this active run."""
        if not self.enabled:
            return "disabled"
        if self._sensitive:
            return "protected"
        return _accept_step_receipt(
            value, user_id=self.user_id, run_id=self.run_id, db_path=self._db_path,
        )

    def _skill_event_impl(
        self,
        skill_id: str,
        skill_revision: str,
        event_type: str,
        *,
        request_id: str | None = None,
        step_id: str | None = None,
        attempt_id: str | None = None,
        status: str = "unknown",
        evidence_refs: list[dict[str, str]] | None = None,
    ) -> None:
        if event_type not in _SKILL_EVENT_TYPES or status not in _SKILL_EVENT_STATUSES:
            return
        expected_statuses = {
            "skill_selected": {"unknown"},
            "skill_resource_read": {"passed", "failed", "unknown"},
            "skill_step_started": {"running"},
            "skill_step_finished": {"failed", "unknown"},
            "skill_step_skipped": {"skipped"},
            "skill_selection_refused": {"failed", "unknown"},
        }
        if status not in expected_statuses[event_type]:
            return
        if not isinstance(skill_id, str) or not _SKILL_ID_RE.fullmatch(skill_id):
            return
        if not isinstance(skill_revision, str) or not _SKILL_REVISION_RE.fullmatch(skill_revision):
            return
        if step_id is not None and (
            not isinstance(step_id, str) or not _SKILL_ID_RE.fullmatch(step_id)
        ):
            return
        if attempt_id is not None and (
            not isinstance(attempt_id, str)
            or not re.fullmatch(r"[A-Za-z0-9_-]{1,96}", attempt_id)
        ):
            return
        resolved_request_id = request_id or self.run_id
        if not isinstance(resolved_request_id, str) or not re.fullmatch(
            r"[A-Za-z0-9_-]{1,128}", resolved_request_id
        ):
            return
        refs = evidence_refs or []
        if not isinstance(refs, list) or len(refs) > MAX_SKILL_EVIDENCE_REFS:
            return
        normalized_refs = []
        for ref in refs:
            if not isinstance(ref, dict) or set(ref) != {"kind", "id"}:
                return
            kind, identifier = ref.get("kind"), ref.get("id")
            if kind not in _SKILL_EVIDENCE_KINDS or not isinstance(identifier, str):
                return
            if not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", identifier):
                return
            normalized_refs.append({"kind": kind, "id": identifier})

        def _do() -> None:
            conn = get_conn(self._db_path)
            try:
                conn.execute("BEGIN IMMEDIATE")
                count = conn.execute(
                    "SELECT COUNT(*) FROM skill_events WHERE user_id=? AND run_id=?",
                    (self.user_id, self.run_id),
                ).fetchone()[0]
                if count >= MAX_SKILL_EVENTS:
                    return
                protected = self._sensitive
                if protected and conn.execute(
                    "SELECT 1 FROM skill_events WHERE user_id=? AND run_id=? "
                    "AND type='protected_activity' LIMIT 1",
                    (self.user_id, self.run_id),
                ).fetchone():
                    return
                truncated = count == MAX_SKILL_EVENTS - 1
                seq = self._next_skill_seq(conn)
                record = {
                    "user_id": self.user_id,
                    "run_id": self.run_id,
                    "request_id": resolved_request_id,
                    "event_id": str(uuid.uuid4()),
                    "seq": seq,
                    "schema_version": 1,
                    "occurred_at": now_iso(),
                    "skill_id": None if protected else skill_id,
                    "skill_revision": None if protected else skill_revision,
                    "step_id": None if protected else step_id,
                    "attempt_id": None if protected else attempt_id,
                    "type": "protected_activity" if protected else (
                        "truncated" if truncated else event_type
                    ),
                    "status": "unknown" if protected or truncated else status,
                    "evidence_refs": "[]" if protected or truncated else json.dumps(
                        normalized_refs, separators=(",", ":")
                    ),
                }
                columns = ", ".join(record)
                placeholders = ", ".join("?" for _ in record)
                conn.execute(
                    f"INSERT INTO skill_events ({columns}) VALUES ({placeholders})",
                    tuple(record.values()),
                )
                conn.commit()
            finally:
                conn.close()
        self._safe("skill_event", _do)

    def tool_call(self, tool: str, arguments: dict,
                  tool_call_id: str | None = None) -> None:
        def _do() -> None:
            self._tool_count += 1
            seq = self._next_seq()
            args_json = json.dumps(arguments, default=str)
            redact = self._redact(args_json)
            stored_args = SENSITIVE_SENTINEL if redact else arguments
            args_json = SENSITIVE_SENTINEL if redact else args_json
            self._append(
                {"type": "tool_call", "seq": seq, "tool": tool,
                 "tool_call_id": tool_call_id, "at": now_iso()},
                payload_key="arguments", payload_value=stored_args,
                size_str=args_json,
            )
            self._execute(
                "INSERT INTO agent_events (run_id, seq, type, tool, tool_call_id, "
                "args_preview, created_at, user_id) "
                "VALUES (?, ?, 'tool_call', ?, ?, ?, ?, ?)",
                (self.run_id, seq, tool, tool_call_id, _truncate(args_json),
                 now_iso(), self.user_id),
            )
        self._safe("tool_call", _do)

    def tool_result(self, tool: str, result: str, latency_ms: int, ok: bool,
                    tool_call_id: str | None = None) -> None:
        def _do() -> None:
            # D5: counted from the SAME `ok` the caller already derived via
            # jarvis.toolresult.classify_tool_result (D1) — not re-derived
            # here, so there is exactly one place this judgement is made.
            if ok:
                self._tools_ok += 1
            else:
                self._tools_failed += 1
            seq = self._next_seq()
            stored = SENSITIVE_SENTINEL if self._redact(result) else result
            self._append(
                {"type": "tool_result", "seq": seq, "tool": tool,
                 "tool_call_id": tool_call_id, "ok": bool(ok),
                 "latency_ms": latency_ms, "at": now_iso()},
                payload_key="result", payload_value=stored, size_str=stored,
            )
            self._execute(
                "INSERT INTO agent_events (run_id, seq, type, tool, tool_call_id, ok, "
                "latency_ms, result_preview, created_at, user_id) "
                "VALUES (?, ?, 'tool_result', ?, ?, ?, ?, ?, ?, ?)",
                (self.run_id, seq, tool, tool_call_id, 1 if ok else 0, latency_ms,
                 _truncate(stored), now_iso(), self.user_id),
            )
        self._safe("tool_result", _do)

    def tool_outcome_unknown(self, tool: str, tool_call_id: str,
                             reason_code: str = "cancelled") -> None:
        """Persist a dispatched tool whose side effect may have completed.

        The event deliberately contains no arguments or result. An unresolved
        call identity is a reconciliation receipt, not a retry instruction.
        """
        if not isinstance(tool_call_id, str) or not tool_call_id.strip():
            return
        if reason_code not in {"cancelled", "cancelled_after_return"}:
            reason_code = "unknown"

        def _do() -> None:
            seq = self._next_seq()
            stamp = now_iso()
            self._append({
                "type": "tool_outcome_unknown", "seq": seq, "tool": tool,
                "tool_call_id": tool_call_id, "reason_code": reason_code,
                "at": stamp,
            })
            self._execute(
                "INSERT INTO agent_events (run_id, seq, type, tool, tool_call_id, "
                "result_preview, created_at, user_id) "
                "VALUES (?, ?, 'tool_outcome_unknown', ?, ?, ?, ?, ?)",
                (self.run_id, seq, tool, tool_call_id, reason_code, stamp,
                 self.user_id),
            )
        self._safe("tool_outcome_unknown", _do)

    def mcp_call(
        self, tool: str, server: str, ok: bool, latency_ms: int,
        error: str | None = None,
    ) -> None:
        def _do() -> None:
            seq = self._next_seq()
            err = (SENSITIVE_SENTINEL
                   if (error is not None and self._redact(error)) else error)
            self._buffer.append({
                "type": "mcp_call", "seq": seq, "tool": tool, "server": server,
                "ok": bool(ok), "latency_ms": latency_ms, "error": err,
                "at": now_iso(),
            })
            self._execute(
                "INSERT INTO agent_events (run_id, seq, type, tool, server, "
                "ok, latency_ms, created_at, user_id) "
                "VALUES (?, ?, 'mcp_call', ?, ?, ?, ?, ?, ?)",
                (self.run_id, seq, tool, server, 1 if ok else 0, latency_ms,
                 now_iso(), self.user_id),
            )
        self._safe("mcp_call", _do)

    def finish(self, reply: str) -> None:
        def _do() -> None:
            # `reply` is rebound below (redaction). Without this declaration
            # Python makes it a LOCAL of _do, so the first read raises
            # UnboundLocalError BEFORE anything runs, _safe swallows it, and
            # the run row stays status='running' forever with no payload
            # file. That was every run from 2026-08-28 (the first bot
            # session after the redaction landed) to 2026-08-31 — 45
            # `runlog_write_failed op=finish` warnings, all of today's runs
            # orphaned at each restart. Pinned by
            # test_finish_redaction_path_binds_reply.
            nonlocal reply
            if self._finished:
                return
            self._finished = True
            status = self._derive_status(reply)
            ended_at = now_iso()
            latency_ms = self._elapsed_ms(ended_at)
            error = _truncate(reply) if status != "ok" else None
            reply_preview = _truncate(reply)
            if self._redact(reply):
                reply = SENSITIVE_SENTINEL
                reply_preview = SENSITIVE_SENTINEL
                if error is not None:
                    error = SENSITIVE_SENTINEL
            seq = self._next_seq()
            self._append(
                {"type": "run_end", "seq": seq, "status": status,
                 "latency_ms": latency_ms, "tool_count": self._tool_count,
                 "error": error, "ended_at": ended_at},
                payload_key="reply", payload_value=reply, size_str=reply,
            )
            self._execute(
                "UPDATE agent_runs SET status=?, ended_at=?, latency_ms=?, "
                "tool_count=?, tools_ok=?, tools_failed=?, error=?, "
                "reply_preview=?, payload_path=? WHERE run_id=?",
                (status, ended_at, latency_ms, self._tool_count,
                 self._tools_ok, self._tools_failed, error, reply_preview,
                 str(self.payload_path) if self.payload_path else None,
                 self.run_id),
            )
            self._write_payload()
        self._safe("finish", _do)


# -- module-level read helpers (plan §5.3, D9, D20) --------------------
#
# Shared by both the CLI (jarvis/runlog/cli.py) and the admin sidecar
# (jarvis/admin/server.py) so the orphan-status rule and the `since`
# parser live in exactly one place.

def parse_since(value: str | None) -> str | None:
    """Normalize "Nd"/"Nh"/"Nm"/ISO-8601 into a UTC ISO string. Returns
    None (no lower bound) for None or anything unparseable — never
    raises (plan D20)."""
    if not value:
        return None
    value = value.strip()
    m = _SINCE_RE.match(value)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        delta = {"d": timedelta(days=n), "h": timedelta(hours=n),
                  "m": timedelta(minutes=n)}[unit]
        return (datetime.now(timezone.utc) - delta).isoformat()
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _display_status(row: dict, now: datetime) -> str:
    """Applies the D9 orphan rule for presentation only — never writes
    back to the row."""
    if row.get("status") != "running":
        return row.get("status", "running")
    started = row.get("started_at")
    if not started:
        return "running"
    try:
        started_dt = datetime.fromisoformat(started)
    except ValueError:
        return "running"
    if started_dt.tzinfo is None:
        started_dt = started_dt.replace(tzinfo=timezone.utc)
    if (now - started_dt).total_seconds() > ORPHAN_AFTER_S:
        return "orphaned"
    return "running"


def list_runs(
    agent: str | None = None,
    status: str | None = None,
    since: str | None = None,
    limit: int = 50,
    db_path: str | Path | None = None,
) -> list[dict]:
    """List runs newest-first. `since` must already be normalized (see
    parse_since) — this function does not parse it. `status='orphaned'`
    is applied in Python, after the D9 rule, not in SQL."""
    conn = get_conn(db_path)
    try:
        conn.row_factory = sqlite3.Row
        clauses: list[str] = []
        params: list[Any] = []
        if agent:
            clauses.append("agent = ?")
            params.append(agent)
        if since:
            clauses.append("started_at >= ?")
            params.append(since)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = conn.execute(
            f"SELECT * FROM agent_runs {where} ORDER BY started_at DESC LIMIT ?",
            (*params, limit),
        ).fetchall()
    finally:
        conn.close()
    now = datetime.now(timezone.utc)
    out = []
    for row in rows:
        d = dict(row)
        d["status"] = _display_status(d, now)
        out.append(d)
    if status:
        out = [d for d in out if d["status"] == status]
    return out


def reconcile_orphaned_runs(db_path: str | Path | None = None) -> int:
    """MORTIMER_AGENT_TRUST_PLAN.md D16: run once at bot startup, alongside
    the existing retention prune (jarvis.runlog.prune, called from
    jarvis/bot/pipeline.py). One UPDATE over agent_runs: any row still
    `status = 'running'` whose started_at is older than RUN_ORPHAN_AFTER_S
    is rewritten to `status = 'orphaned'`. Safe to call on every boot —
    a process is only ever `running` while it holds the row, and nothing
    is running when the bot has just started, so anything left in that
    state is, by definition, orphaned. Returns the number of rows updated.
    """
    cutoff = (
        datetime.now(timezone.utc) - timedelta(seconds=RUN_ORPHAN_AFTER_S)
    ).isoformat()
    conn = get_conn(db_path)
    try:
        cur = conn.execute(
            "UPDATE agent_runs SET status = 'orphaned' "
            "WHERE status = 'running' AND started_at < ?",
            (cutoff,),
        )
        conn.commit()
        return cur.rowcount if cur.rowcount is not None and cur.rowcount > 0 else 0
    finally:
        conn.close()


def get_run(
    run_id: str, db_path: str | Path | None = None, root: Path | None = None,
) -> dict | None:
    """Full detail for one run: the row (with the D9 status rule
    applied), its agent_events in seq order, and the parsed JSONL
    payload (empty list if the file is missing — pruned or never
    written; a malformed line is skipped rather than raising)."""
    conn = get_conn(db_path)
    try:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM agent_runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        if row is None:
            return None
        run = dict(row)
        run["status"] = _display_status(run, datetime.now(timezone.utc))
        events = [
            dict(r) for r in conn.execute(
                "SELECT * FROM agent_events WHERE run_id = ? ORDER BY seq",
                (run_id,),
            ).fetchall()
        ]
        resolved_call_ids = {
            event["tool_call_id"] for event in events
            if event.get("tool_call_id") and event["type"] == "tool_result"
        }
        unknown_call_ids = {
            event["tool_call_id"] for event in events
            if event.get("tool_call_id") and event["type"] == "tool_outcome_unknown"
        }
        unresolved_tool_calls = []
        for event in events:
            call_id = event.get("tool_call_id")
            if event["type"] != "tool_call" or not call_id or call_id in resolved_call_ids:
                continue
            unresolved_tool_calls.append({
                "tool_call_id": call_id,
                "tool": event.get("tool"),
                "status": "unknown" if call_id in unknown_call_ids else "unresolved",
            })
    finally:
        conn.close()

    payload: list[dict] = []
    payload_path = run.get("payload_path")
    if payload_path:
        full_path = (root if root is not None else Path(".")) / payload_path
        if full_path.exists():
            for line in full_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    payload.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return {
        "run": run, "events": events, "payload": payload,
        "unresolved_tool_calls": unresolved_tool_calls,
    }


def _encode_skill_run_cursor(started_at: str, run_id: str) -> str:
    raw = json.dumps([started_at, run_id], separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_skill_run_cursor(cursor: str) -> tuple[str, str] | None:
    if not cursor:
        return None
    if len(cursor) > 512 or not re.fullmatch(r"[A-Za-z0-9_-]+", cursor):
        return None
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        value = json.loads(raw)
    except (ValueError, json.JSONDecodeError):
        return None
    if (
        not isinstance(value, list) or len(value) != 2
        or not all(isinstance(item, str) and len(item) <= 256 for item in value)
    ):
        return None
    started_at, run_id = value
    # A cursor is an opaque keyset position, not an arbitrary SQL filter.
    # Reject syntactically valid base64/JSON that cannot have been emitted by
    # this API instead of silently returning an empty page for malformed data.
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", run_id):
        return None
    try:
        parsed_started_at = datetime.fromisoformat(started_at)
    except ValueError:
        return None
    if parsed_started_at.tzinfo is None or parsed_started_at.utcoffset() is None:
        return None
    return started_at, run_id


def list_skill_runs(
    skill_id: str,
    *,
    cursor: str = "",
    limit: int = 20,
    db_path: str | Path | None = None,
    user_id: str | None = None,
) -> dict:
    """List redacted run cards that have a non-protected trace for a skill."""
    if not _SKILL_ID_RE.fullmatch(skill_id) or not 1 <= limit <= 100:
        raise ValueError("invalid skill run query")
    position = _decode_skill_run_cursor(cursor)
    if cursor and position is None:
        raise ValueError("invalid skill run cursor")
    owner = user_id or current_user_id()
    clauses = [
        "r.user_id = ?",
        # A run that ever carried a protected marker is protected as a whole.
        # Do not let a stale/corrupt mixed trace re-enter the standard activity
        # listing through a surviving non-protected row.
        (
            "NOT EXISTS (SELECT 1 FROM skill_events p WHERE p.user_id = r.user_id "
            "AND p.run_id = r.run_id AND p.type = 'protected_activity')"
        ),
        (
            "EXISTS (SELECT 1 FROM skill_events e WHERE e.user_id = r.user_id "
            "AND e.run_id = r.run_id AND e.skill_id = ? "
            "AND e.type != 'protected_activity')"
        ),
    ]
    params: list[Any] = [owner, skill_id]
    if position:
        clauses.append("(r.started_at < ? OR (r.started_at = ? AND r.run_id < ?))")
        params.extend([position[0], position[0], position[1]])
    conn = get_conn(db_path)
    try:
        rows = conn.execute(
            "SELECT r.run_id, r.agent, r.display_name, r.status, r.started_at, "
            "r.ended_at, r.latency_ms, "
            "(SELECT e.type FROM skill_events e WHERE e.user_id=r.user_id "
            "AND e.run_id=r.run_id AND e.skill_id=? ORDER BY e.seq DESC LIMIT 1) "
            "AS last_event_type, "
            "(SELECT e.status FROM skill_events e WHERE e.user_id=r.user_id "
            "AND e.run_id=r.run_id AND e.skill_id=? ORDER BY e.seq DESC LIMIT 1) "
            "AS last_event_status "
            "FROM agent_runs r WHERE " + " AND ".join(clauses) +
            " ORDER BY r.started_at DESC, r.run_id DESC LIMIT ?",
            (skill_id, skill_id, *params, limit + 1),
        ).fetchall()
    finally:
        conn.close()
    has_more = len(rows) > limit
    rows = rows[:limit]
    now = datetime.now(timezone.utc)
    items = []
    for row in rows:
        item = dict(row)
        item["status"] = _display_status(item, now)
        items.append(item)
    next_cursor = (
        _encode_skill_run_cursor(items[-1]["started_at"], items[-1]["run_id"])
        if has_more and items else None
    )
    return {"runs": items, "next_cursor": next_cursor}


def get_skill_events(
    run_id: str,
    *,
    after_seq: int = 0,
    limit: int = 100,
    db_path: str | Path | None = None,
    user_id: str | None = None,
) -> dict | None:
    """Read an authorized run's typed skill trace after a sequence cursor."""
    if (
        not isinstance(run_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", run_id)
        or not isinstance(after_seq, int) or after_seq < 0
        or not 1 <= limit <= 100
    ):
        raise ValueError("invalid skill event query")
    owner = user_id or current_user_id()
    conn = get_conn(db_path)
    try:
        run = conn.execute(
            "SELECT run_id FROM agent_runs WHERE user_id=? AND run_id=?",
            (owner, run_id),
        ).fetchone()
        if run is None:
            return None
        trace_exists = conn.execute(
            "SELECT 1 FROM skill_events WHERE user_id=? AND run_id=? LIMIT 1",
            (owner, run_id),
        ).fetchone() is not None
        trace_truncated = conn.execute(
            "SELECT 1 FROM skill_events WHERE user_id=? AND run_id=? "
            "AND type='truncated' LIMIT 1",
            (owner, run_id),
        ).fetchone() is not None
        protected = conn.execute(
            "SELECT 1 FROM skill_events WHERE user_id=? AND run_id=? "
            "AND type='protected_activity' LIMIT 1",
            (owner, run_id),
        ).fetchone() is not None
        if protected:
            # Treat protected status as run-wide, even if a historical or
            # malformed database contains ordinary rows beside the marker.
            # Returning only a canonical marker prevents those rows from
            # crossing the API/event boundary.
            marker = conn.execute(
                "SELECT event_id, run_id, request_id, seq, schema_version, occurred_at "
                "FROM skill_events WHERE user_id=? AND run_id=? "
                "AND type='protected_activity' AND seq>? ORDER BY seq LIMIT 1",
                (owner, run_id, after_seq),
            ).fetchone()
            rows = [marker] if marker is not None else []
            trace_truncated = False
        else:
            rows = conn.execute(
                "SELECT event_id, run_id, request_id, seq, schema_version, occurred_at, "
                "skill_id, skill_revision, step_id, attempt_id, type, status, evidence_refs "
                "FROM skill_events WHERE user_id=? AND run_id=? AND seq>? "
                "ORDER BY seq LIMIT ?",
                (owner, run_id, after_seq, limit + 1),
            ).fetchall()
    finally:
        conn.close()
    has_more = len(rows) > limit
    events = []
    for row in rows[:limit]:
        event = dict(row)
        if event.get("type") is None:
            # The canonical protected query intentionally selects only safe
            # envelope fields; complete its generic event shape here.
            event.update(skill_id=None, skill_revision=None, step_id=None,
                         attempt_id=None, type="protected_activity",
                         status="unknown", evidence_refs=[])
        try:
            event["evidence_refs"] = json.loads(event["evidence_refs"])
        except (TypeError, json.JSONDecodeError):
            event["evidence_refs"] = []
        if event["type"] == "protected_activity":
            # Defensive output contract even if an old/corrupt row contains
            # fields that the writer should have omitted.
            event.update(skill_id=None, skill_revision=None, step_id=None,
                         attempt_id=None, evidence_refs=[], status="unknown")
        events.append(event)
    return {
        "trace_status": "recorded" if trace_exists else "unavailable",
        "events": events,
        "after_seq": after_seq,
        "next_after_seq": events[-1]["seq"] if events else after_seq,
        "has_more": has_more,
        "truncated": trace_truncated,
    }


def _accept_step_receipt(value, *, user_id, run_id, db_path=None, deferred_creator=False):
    """Shared signed-receipt persistence; deferred creator callers hold their job lock."""
    try:
        receipt = SkillStepCheckReceipt.from_mapping(value)
        expected = {
            "user_id": user_id,
            "run_id": run_id,
            "request_id": run_id,
            "skill_id": receipt.skill_id,
            "skill_revision": receipt.skill_revision,
            "step_id": receipt.step_id,
            "attempt_id": receipt.attempt_id,
        }
        required = load_required_check_ids(
            receipt.skill_id, receipt.skill_revision, receipt.step_id,
        )
        validate_skill_step_receipt(
            receipt, expected=expected, required_check_ids=required,
        )
    except SkillStepReceiptError as exc:
        logger.info(
            "skill_step_receipt_rejected run_id=%s reason_code=%s",
            run_id, str(exc)[:64],
        )
        return "rejected"

    conn = None
    try:
        conn = get_conn(db_path)
        conn.execute("BEGIN IMMEDIATE")
        run = conn.execute(
            "SELECT status, user_id, agent FROM agent_runs WHERE run_id=?",
            (run_id,),
        ).fetchone()
        if (run is None or run["user_id"] != user_id
                or (not deferred_creator and run["status"] != "running")
                or (deferred_creator and (run["agent"] != "developer"
                    or receipt.skill_id != "skill-creator"
                    or receipt.step_id != "offline-validate"))):
            conn.rollback()
            return "inactive_run"
        # `mark_sensitive()` scrubs the trace in its own transaction. The
        # in-memory flag check above is a fast path, but it can race with
        # that transition. Recheck the durable run-wide marker while
        # holding this write transaction so a late verified receipt
        # cannot repopulate protected activity after the scrub commits.
        protected = conn.execute(
            "SELECT 1 FROM skill_events WHERE user_id=? AND run_id=? "
            "AND type='protected_activity' LIMIT 1",
            (user_id, run_id),
        ).fetchone()
        if protected is not None:
            conn.rollback()
            return "protected"
        started = conn.execute(
            "SELECT 1 FROM skill_events WHERE user_id=? AND run_id=? "
            "AND request_id=? AND skill_id=? AND skill_revision=? AND step_id=? "
            "AND attempt_id=? AND type='skill_step_started' LIMIT 1",
            (user_id, run_id, receipt.request_id, receipt.skill_id,
             receipt.skill_revision, receipt.step_id, receipt.attempt_id),
        ).fetchone()
        selected = conn.execute(
            "SELECT 1 FROM skill_events WHERE user_id=? AND run_id=? "
            "AND request_id=? AND skill_id=? AND skill_revision=? "
            "AND type='skill_selected' LIMIT 1",
            (user_id, run_id, receipt.request_id, receipt.skill_id,
             receipt.skill_revision),
        ).fetchone()
        if started is None or selected is None:
            conn.rollback()
            return "attempt_not_started"
        receipt_digest = receipt.digest()
        existing = conn.execute(
            "SELECT receipt_sha256 FROM skill_step_check_receipts "
            "WHERE user_id=? AND receipt_id=?",
            (user_id, receipt.receipt_id),
        ).fetchone()
        if existing is not None:
            conn.rollback()
            return (
                "already_accepted"
                if existing["receipt_sha256"] == receipt_digest
                else "replay_conflict"
            )
        prior_attempt = conn.execute(
            "SELECT 1 FROM skill_step_check_receipts WHERE user_id=? AND run_id=? "
            "AND skill_id=? AND skill_revision=? AND step_id=? AND attempt_id=? LIMIT 1",
            (user_id, run_id, receipt.skill_id, receipt.skill_revision,
             receipt.step_id, receipt.attempt_id),
        ).fetchone()
        if prior_attempt is not None:
            conn.rollback()
            return "attempt_already_accepted"
        event_count = conn.execute(
            "SELECT COUNT(*) FROM skill_events WHERE user_id=? AND run_id=?",
            (user_id, run_id),
        ).fetchone()[0]
        if event_count >= MAX_SKILL_EVENTS:
            conn.rollback()
            return "event_limit_reached"
        now = now_iso()
        conn.execute(
            "INSERT INTO skill_step_check_receipts "
            "(user_id, receipt_id, run_id, request_id, skill_id, skill_revision, "
            "step_id, attempt_id, receipt_sha256, issued_at, expires_at, accepted_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, receipt.receipt_id, run_id, receipt.request_id,
             receipt.skill_id, receipt.skill_revision, receipt.step_id,
             receipt.attempt_id, receipt_digest, receipt.issued_at,
             receipt.expires_at, now),
        )
        event = {
            "user_id": user_id,
            "run_id": run_id,
            "request_id": receipt.request_id,
            "event_id": str(uuid.uuid4()),
            "seq": _next_skill_event_seq(conn, user_id, run_id),
            "schema_version": 1,
            "occurred_at": now,
            "skill_id": receipt.skill_id,
            "skill_revision": receipt.skill_revision,
            "step_id": receipt.step_id,
            "attempt_id": receipt.attempt_id,
            "type": "skill_step_finished",
            "status": "passed",
            "evidence_refs": json.dumps(
                [{"kind": "check_receipt_id", "id": receipt.receipt_id}],
                separators=(",", ":"),
            ),
        }
        columns = ", ".join(event)
        placeholders = ", ".join("?" for _ in event)
        conn.execute(
            f"INSERT INTO skill_events ({columns}) VALUES ({placeholders})",
            tuple(event.values()),
        )
        conn.commit()
        return "accepted"
    except Exception as exc:  # noqa: BLE001 — telemetry must not fail the run
        if conn is not None:
            conn.rollback()
        logger.warning(
            "runlog_write_failed run_id=%s op=skill_step_receipt error_type=%s",
            run_id, type(exc).__name__[:64],
        )
        return "unavailable"
    finally:
        if conn is not None:
            conn.close()
