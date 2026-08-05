"""mcp-time: time & date pure logic (plan Phase 1, §1.1).

No I/O, no DB, no network. All datetimes timezone-aware in JARVIS_TIMEZONE
(env var, default UTC for standalone use). `_now()` is monkeypatchable so
tests can freeze time.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from dateutil import parser as date_parser

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


def _tz() -> ZoneInfo:
    return ZoneInfo(os.environ.get("JARVIS_TIMEZONE", "UTC"))


def _now() -> datetime:
    return datetime.now(_tz())


def _human(dt: datetime) -> str:
    """e.g. 'Tuesday, August 4, 2026, 3:25 PM EDT'."""
    s = dt.strftime("%A, %B %d, %Y, %I:%M %p %Z")
    # Drop leading zeros on the day-of-month and 12-hour clock hour.
    return re.sub(r"(?<=[, ])0(?=\d)", "", s)


def get_current_time() -> dict:
    """Current time in the configured timezone."""
    now = _now()
    return {
        "iso": now.isoformat(),
        "human": _human(now),
        "timezone": str(now.tzinfo),
        "unix": int(now.timestamp()),
    }


def _apply_explicit_time(dt: datetime, text: str) -> datetime:
    """If the text contains an explicit clock time, apply it."""
    m = _TIME_RE.search(text)
    if not m:
        return dt
    if m.group(4):  # 24h "at 14:30" form
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
    """Resolve the leading day keyword/phrase to a datetime (time untouched)."""
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
        # That weekday within the following calendar week (weeks start Monday).
        days_to_next_monday = (7 - now.weekday()) % 7 or 7
        return now + timedelta(days=days_to_next_monday + target)
    # Bare / "this" weekday: the next occurrence including today.
    return now + timedelta(days=(target - now.weekday()) % 7)


def resolve_date_expression(expression: str, *, now: datetime | None = None) -> dict:
    """Resolve natural English dates/times to an absolute, tz-aware datetime.

    Handles: now/today/tomorrow/day after tomorrow/tonight, "in N
    minutes/hours/days/weeks", weekday names ("friday", "next friday",
    "this friday"), explicit times ("at 9am", "at 14:30"), combinations
    ("tomorrow at 9am", "next friday at 2:30pm"), and anything
    python-dateutil can parse ("August 20 at 9am", "2026-08-20").

    Deterministic weekday rules: bare "<weekday>" and "this <weekday>" mean
    the next occurrence including today; "next <weekday>" means that weekday
    in the following calendar week (weeks start Monday).
    """
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


def date_add(base_iso: str, amount: int, unit: str) -> dict:
    """Add an amount of minutes|hours|days|weeks to an ISO datetime."""
    unit = (unit or "").strip().lower()
    deltas = {
        "minutes": timedelta(minutes=amount),
        "hours": timedelta(hours=amount),
        "days": timedelta(days=amount),
        "weeks": timedelta(weeks=amount),
    }
    if unit not in deltas:
        return {"error": f"Invalid unit '{unit}'. Use minutes, hours, days or weeks."}
    try:
        base = datetime.fromisoformat(base_iso)
    except (ValueError, TypeError):
        return {"error": f"Invalid ISO datetime: '{base_iso}'."}
    if base.tzinfo is None:
        base = base.replace(tzinfo=_tz())
    result = base + deltas[unit]
    return {"iso": result.isoformat(), "human": _human(result)}


def date_diff(a_iso: str, b_iso: str) -> dict:
    """Signed difference (b minus a): {'days': int, 'hours': float}.

    Positive when b is later than a.
    """
    try:
        a = datetime.fromisoformat(a_iso)
        b = datetime.fromisoformat(b_iso)
    except (ValueError, TypeError):
        return {"error": "Both arguments must be ISO datetimes."}
    total_seconds = (b - a).total_seconds()
    days = int(total_seconds // 86400)
    hours = round(total_seconds / 3600, 1)
    return {"days": days, "hours": hours}
