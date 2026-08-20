"""mcp-reminders: SQLite-backed reminders pure logic (plan Phase 1, §1.3).

The relative-date parsing logic is intentionally COPIED here (from
mcp-time) — per the plan, MCP servers must not import each other.
`_now()` is monkeypatchable so tests can freeze time.
"""

from __future__ import annotations

import logging
import os
import re
import sqlite3
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from dateutil import parser as date_parser

from jarvis.db import get_conn, now_iso

_WEEKDAYS = (
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
)
_WEEKDAY_ALT = "|".join(_WEEKDAYS)
_RELATIVE_IN_RE = re.compile(
    r"^in\s+(\d+)\s+(minute|hour|day|week)s?$", re.IGNORECASE
)
_DAY_PART_RE = re.compile(
    r"^(?P<day>day after tomorrow|tomorrow|today|tonight|now|"
    r"(?:next|this)\s+(?:" + _WEEKDAY_ALT + r")|"
    r"(?:" + _WEEKDAY_ALT + r")s?)"
    r"(?P<rest>\s+.*)?$",
    re.IGNORECASE,
)
_TIME_RE = re.compile(
    r"(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b|(?:at\s+)(\d{1,2}):(\d{2})\b",
    re.IGNORECASE,
)
logger = logging.getLogger(__name__)

_VALID_STATUSES = ("pending", "done", "cancelled", "all")


def _tz() -> ZoneInfo:
    """The configured timezone, or UTC.

    MORTIMER_ENV_BRIDGE_PLAN.md E2. `expand_env_vars` leaves an unresolved
    `${VAR}` as literal text by design, so this once received the seven
    characters `"${JARVIS_TIMEZONE}"` and raised ZoneInfoNotFoundError from
    inside a subprocess — a stack trace whose top frame named `zoneinfo`,
    not the configuration that caused it.

    Same defence `mcp_git`/`mcp_repo`'s `_repo_root()` already applies to a
    phantom repo root: a value containing `"${"` is treated as UNSET.
    Wrong-but-running beats a crash, and E1's parent-side warning is what
    makes the misconfiguration findable — this half only keeps the tool
    alive while someone reads it.
    """
    value = os.environ.get("JARVIS_TIMEZONE", "").strip()
    if not value or "${" in value:
        if value:
            logger.warning(
                "reminders_timezone_unresolved value=%s — falling back to "
                "UTC; JARVIS_TIMEZONE was not set in the parent process",
                value)
        return ZoneInfo("UTC")
    try:
        return ZoneInfo(value)
    except Exception:  # noqa: BLE001 — a bad zone must not kill the tool
        logger.warning(
            "reminders_timezone_invalid value=%s — falling back to UTC", value)
        return ZoneInfo("UTC")


def _now() -> datetime:
    return datetime.now(_tz())


def _human(dt: datetime) -> str:
    s = dt.strftime("%A, %B %d, %Y, %I:%M %p %Z")
    return re.sub(r"(?<=[, ])0(?=\d)", "", s)


def _apply_explicit_time(dt: datetime, text: str) -> datetime:
    m = _TIME_RE.search(text)
    if not m:
        return dt
    if m.group(4):
        hour, minute = int(m.group(4)), int(m.group(5))
    else:
        hour = int(m.group(1))
        minute = int(m.group(2)) if m.group(2) else 0
        meridiem = (m.group(3) or "").lower()
        if meridiem == "pm" and hour != 12:
            hour += 12
        elif meridiem == "am" and hour == 12:
            hour = 0
    if hour > 23 or minute > 59:
        return dt
    return dt.replace(hour=hour, minute=minute, second=0, microsecond=0)


def _resolve_day_part(day: str, now: datetime) -> datetime:
    day = day.strip().lower()
    if day in ("now", "today"):
        return now
    if day == "tomorrow":
        return now + timedelta(days=1)
    if day == "day after tomorrow":
        return now + timedelta(days=2)
    if day == "tonight":
        return now.replace(hour=20, minute=0, second=0, microsecond=0)
    m = re.match(r"^(next|this)?\s*(" + _WEEKDAY_ALT + r")s?$", day)
    qualifier, weekday = m.group(1), m.group(2)
    target = _WEEKDAYS.index(weekday)
    if qualifier == "next":
        days_to_next_monday = (7 - now.weekday()) % 7 or 7
        return now + timedelta(days=days_to_next_monday + target)
    return now + timedelta(days=(target - now.weekday()) % 7)


def _resolve_date_expression(expression: str, *, now: datetime | None = None) -> dict:
    """Copied from mcp_servers.mcp_time.logic.resolve_date_expression
    (plan: MCP servers must not import each other)."""
    text = (expression or "").strip().lower()
    if not text:
        return {"error": "Empty date/time expression."}

    now = now or _now()

    m = _RELATIVE_IN_RE.match(text)
    if m:
        amount, unit = int(m.group(1)), m.group(2).lower()
        delta = {
            "minute": timedelta(minutes=amount),
            "hour": timedelta(hours=amount),
            "day": timedelta(days=amount),
            "week": timedelta(weeks=amount),
        }[unit]
        resolved = now + delta
        return {"iso": resolved.isoformat(), "human": _human(resolved)}

    m = _DAY_PART_RE.match(text)
    if m:
        base = _resolve_day_part(m.group("day"), now)
        resolved = _apply_explicit_time(base, m.group("rest") or "")
        return {"iso": resolved.isoformat(), "human": _human(resolved)}

    try:
        parsed = date_parser.parse(expression, default=now.replace(second=0, microsecond=0))
    except (ValueError, OverflowError):
        return {"error": f"I couldn't understand the date/time expression '{expression}'."}
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_tz())
    return {"iso": parsed.isoformat(), "human": _human(parsed)}


def _row_to_reminder(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "message": row["message"],
        "due_at": row["due_at"],
        "status": row["status"],
        "delivered": row["delivered"],
        "created_at": row["created_at"],
    }


def set_reminder(message: str, due_expression: str) -> dict:
    message = (message or "").strip()
    if not message:
        return {"error": "A reminder needs a message."}
    resolved = _resolve_date_expression(due_expression)
    if "error" in resolved:
        return resolved
    due = datetime.fromisoformat(resolved["iso"])
    if due <= _now():
        return {"error": f"That time is in the past ({resolved['human']})."}
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO reminders (message, due_at, status, delivered, created_at) "
            "VALUES (?, ?, 'pending', 0, ?)",
            (message, due.isoformat(), now_iso()),
        )
        reminder_id = cur.lastrowid
    return {
        "id": reminder_id,
        "message": f"Reminder set for {resolved['human']}: {message}",
    }


def list_reminders(status: str = "pending") -> dict:
    status = (status or "pending").strip().lower()
    if status not in _VALID_STATUSES:
        return {"error": f"Invalid status '{status}'. Use pending, done, cancelled or all."}
    with get_conn() as conn:
        if status == "all":
            rows = conn.execute(
                "SELECT * FROM reminders ORDER BY due_at ASC"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM reminders WHERE status = ? ORDER BY due_at ASC",
                (status,),
            ).fetchall()
    return {"reminders": [_row_to_reminder(row) for row in rows]}


def _transition(reminder_id: int, expected_from: str, to: str, verb: str) -> dict:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM reminders WHERE id = ?", (reminder_id,)
        ).fetchone()
        if row is None:
            return {"error": f"No reminder with id {reminder_id}."}
        if row["status"] != expected_from:
            return {"error": f"Reminder {reminder_id} is already {row['status']}."}
        conn.execute(
            "UPDATE reminders SET status = ? WHERE id = ?", (to, reminder_id)
        )
    return {"message": f"Reminder {reminder_id} {verb}."}


def complete_reminder(reminder_id: int) -> dict:
    return _transition(reminder_id, "pending", "done", "marked done")


def cancel_reminder(reminder_id: int) -> dict:
    return _transition(reminder_id, "pending", "cancelled", "cancelled")


def get_due_reminders() -> dict:
    """Atomically fetch due, undelivered reminders and mark them delivered."""
    now = _now().isoformat()
    with get_conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        rows = conn.execute(
            "SELECT * FROM reminders WHERE status = 'pending' "
            "AND due_at <= ? AND delivered = 0 ORDER BY due_at ASC",
            (now,),
        ).fetchall()
        ids = [row["id"] for row in rows]
        if ids:
            conn.execute(
                f"UPDATE reminders SET delivered = 1 WHERE id IN "
                f"({','.join('?' * len(ids))})",
                ids,
            )
        conn.commit()
    return {"reminders": [_row_to_reminder(row) for row in rows]}
