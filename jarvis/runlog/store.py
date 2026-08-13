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

import json
import logging
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from jarvis.db import get_conn, now_iso

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

RUNLOG_DIR = Path("logs/agents")

_DROPPED = "<dropped: run payload cap exceeded>"

# Must exactly match jarvis.agents.base.TIMEOUT_MESSAGE. Duplicated here
# (rather than imported) because jarvis.agents.base imports jarvis.runlog
# — importing it back would be a cycle. tests/unit/test_runlog_store.py
# asserts the two stay equal so they cannot silently drift apart.
_TIMEOUT_MESSAGE = "FAILED: the task took too long; please try again."

_SINCE_RE = re.compile(r"^(\d+)([dhm])$")


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
    ) -> None:
        self.run_id = run_id
        self.agent = agent
        self.display_name = display_name
        self.task = task
        self.session_id = session_id
        self.enabled = enabled
        self.payload_path: Path | None = None

        self._db_path = db_path
        self._root = root if root is not None else Path(".")

        self._seq = 0
        self._buffer: list[dict[str, Any]] = []
        self._payload_bytes = 0
        self._capped = False
        self._finished = False
        self._started_at: str | None = None
        self._tool_count = 0

    # -- internal helpers ---------------------------------------------

    def _next_seq(self) -> int:
        seq = self._seq
        self._seq += 1
        return seq

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
                "runlog_write_failed run_id=%s op=%s error=%s",
                self.run_id, op, exc,
            )

    def _derive_status(self, reply: str) -> str:
        if reply == _TIMEOUT_MESSAGE:
            return "timeout"
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
            self._buffer.append({
                "type": "run_start",
                "seq": self._next_seq(),
                "run_id": self.run_id,
                "agent": self.agent,
                "display_name": self.display_name,
                "session_id": self.session_id,
                "task": self.task,
                "started_at": self._started_at,
            })
            self._execute(
                "INSERT INTO agent_runs (run_id, session_id, agent, "
                "display_name, task, status, started_at, tool_count) "
                "VALUES (?, ?, ?, ?, ?, 'running', ?, 0)",
                (self.run_id, self.session_id, self.agent, self.display_name,
                 self.task, self._started_at),
            )
        self._safe("start", _do)

    def tool_call(self, tool: str, arguments: dict) -> None:
        def _do() -> None:
            self._tool_count += 1
            seq = self._next_seq()
            args_json = json.dumps(arguments, default=str)
            self._append(
                {"type": "tool_call", "seq": seq, "tool": tool, "at": now_iso()},
                payload_key="arguments", payload_value=arguments, size_str=args_json,
            )
            self._execute(
                "INSERT INTO agent_events (run_id, seq, type, tool, "
                "args_preview, created_at) VALUES (?, ?, 'tool_call', ?, ?, ?)",
                (self.run_id, seq, tool, _truncate(args_json), now_iso()),
            )
        self._safe("tool_call", _do)

    def tool_result(self, tool: str, result: str, latency_ms: int, ok: bool) -> None:
        def _do() -> None:
            seq = self._next_seq()
            self._append(
                {"type": "tool_result", "seq": seq, "tool": tool, "ok": bool(ok),
                 "latency_ms": latency_ms, "at": now_iso()},
                payload_key="result", payload_value=result, size_str=result,
            )
            self._execute(
                "INSERT INTO agent_events (run_id, seq, type, tool, ok, "
                "latency_ms, result_preview, created_at) "
                "VALUES (?, ?, 'tool_result', ?, ?, ?, ?, ?)",
                (self.run_id, seq, tool, 1 if ok else 0, latency_ms,
                 _truncate(result), now_iso()),
            )
        self._safe("tool_result", _do)

    def mcp_call(
        self, tool: str, server: str, ok: bool, latency_ms: int,
        error: str | None = None,
    ) -> None:
        def _do() -> None:
            seq = self._next_seq()
            self._buffer.append({
                "type": "mcp_call", "seq": seq, "tool": tool, "server": server,
                "ok": bool(ok), "latency_ms": latency_ms, "error": error,
                "at": now_iso(),
            })
            self._execute(
                "INSERT INTO agent_events (run_id, seq, type, tool, server, "
                "ok, latency_ms, created_at) "
                "VALUES (?, ?, 'mcp_call', ?, ?, ?, ?, ?)",
                (self.run_id, seq, tool, server, 1 if ok else 0, latency_ms,
                 now_iso()),
            )
        self._safe("mcp_call", _do)

    def finish(self, reply: str) -> None:
        def _do() -> None:
            if self._finished:
                return
            self._finished = True
            status = self._derive_status(reply)
            ended_at = now_iso()
            latency_ms = self._elapsed_ms(ended_at)
            error = _truncate(reply) if status != "ok" else None
            reply_preview = _truncate(reply)
            seq = self._next_seq()
            self._append(
                {"type": "run_end", "seq": seq, "status": status,
                 "latency_ms": latency_ms, "tool_count": self._tool_count,
                 "error": error, "ended_at": ended_at},
                payload_key="reply", payload_value=reply, size_str=reply,
            )
            self._execute(
                "UPDATE agent_runs SET status=?, ended_at=?, latency_ms=?, "
                "tool_count=?, error=?, reply_preview=?, payload_path=? "
                "WHERE run_id=?",
                (status, ended_at, latency_ms, self._tool_count, error,
                 reply_preview,
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
    return {"run": run, "events": events, "payload": payload}
