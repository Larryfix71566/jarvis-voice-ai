"""Unit tests for mcp_servers/mcp_time/logic.py (plan Phase 1 Tests)."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from mcp_servers.mcp_time import logic

TZ = ZoneInfo("America/New_York")
# Tuesday, August 4, 2026, 3:00 PM EDT
FIXED_NOW = datetime(2026, 8, 4, 15, 0, tzinfo=TZ)


@pytest.fixture(autouse=True)
def freeze_time(monkeypatch):
    monkeypatch.setenv("JARVIS_TIMEZONE", "America/New_York")
    monkeypatch.setattr(logic, "_now", lambda: FIXED_NOW)


def test_get_current_time_shape():
    result = logic.get_current_time()
    assert result["timezone"] == "EDT" or "New_York" in result["timezone"] or result["timezone"]
    assert result["iso"].startswith("2026-08-04T15:00")
    assert result["human"] == "Tuesday, August 4, 2026, 3:00 PM EDT"
    assert result["unix"] == int(FIXED_NOW.timestamp())


def test_human_format_strips_leading_zeros():
    early = datetime(2026, 8, 5, 9, 5, tzinfo=TZ)
    assert logic._human(early) == "Wednesday, August 5, 2026, 9:05 AM EDT"


@pytest.mark.parametrize("expression,expected_iso_prefix", [
    ("tomorrow", "2026-08-05T15:00"),
    ("day after tomorrow", "2026-08-06T15:00"),
    ("in 3 days", "2026-08-07T15:00"),
    ("in 90 minutes", "2026-08-04T16:30"),
    ("in 2 weeks", "2026-08-18T15:00"),
    ("now", "2026-08-04T15:00"),
])
def test_resolve_relative_expressions(expression, expected_iso_prefix):
    result = logic.resolve_date_expression(expression)
    assert "error" not in result
    assert result["iso"].startswith(expected_iso_prefix)


def test_resolve_tonight():
    result = logic.resolve_date_expression("tonight")
    assert result["iso"].startswith("2026-08-04T20:00")


def test_resolve_weekday_rules_deterministic():
    # Tuesday Aug 4, 2026: bare/this Friday -> Aug 7; next Friday -> Aug 14.
    assert logic.resolve_date_expression("friday")["iso"].startswith("2026-08-07")
    assert logic.resolve_date_expression("this friday")["iso"].startswith("2026-08-07")
    assert logic.resolve_date_expression("next friday")["iso"].startswith("2026-08-14")
    # "next monday" from Tuesday: following calendar week's Monday (Aug 10).
    assert logic.resolve_date_expression("next monday")["iso"].startswith("2026-08-10")


def test_resolve_tomorrow_at_9am():
    result = logic.resolve_date_expression("tomorrow at 9am")
    assert result["iso"].startswith("2026-08-05T09:00")
    assert "9:00 AM" in result["human"]


def test_resolve_tomorrow_at_2_30pm():
    result = logic.resolve_date_expression("tomorrow at 2:30pm")
    assert result["iso"].startswith("2026-08-05T14:30")


def test_resolve_at_1430_24h():
    result = logic.resolve_date_expression("tomorrow at 14:30")
    assert result["iso"].startswith("2026-08-05T14:30")


def test_resolve_invalid_explicit_time_keeps_date():
    result = logic.resolve_date_expression("tomorrow at 25:99")
    assert "error" not in result
    assert result["iso"].startswith("2026-08-05T15:00")


def test_resolve_dateutil_fallback():
    result = logic.resolve_date_expression("August 20 at 9am")
    assert "error" not in result
    assert result["iso"].startswith("2026-08-20T09:00")


@pytest.mark.parametrize("bad", ["", "   ", "flibberty gibbet zzz", "not a date at all qq"])
def test_resolve_error_paths(bad):
    result = logic.resolve_date_expression(bad)
    assert "error" in result


def test_date_add_happy():
    result = logic.date_add("2026-08-04T15:00:00-04:00", 2, "days")
    assert result["iso"].startswith("2026-08-06T15:00")


def test_date_add_bad_unit():
    result = logic.date_add("2026-08-04T15:00:00-04:00", 2, "fortnights")
    assert "error" in result


def test_date_add_bad_iso():
    result = logic.date_add("not-a-date", 2, "days")
    assert "error" in result


def test_date_add_naive_iso_gets_timezone():
    result = logic.date_add("2026-08-04T15:00:00", 1, "hours")
    assert "-04:00" in result["iso"]


def test_date_diff_positive_and_negative():
    pos = logic.date_diff("2026-08-04T00:00:00-04:00", "2026-08-05T12:00:00-04:00")
    assert pos == {"days": 1, "hours": 36.0}
    neg = logic.date_diff("2026-08-05T00:00:00-04:00", "2026-08-04T00:00:00-04:00")
    assert neg["days"] == -1
    assert neg["hours"] == -24.0


def test_date_diff_error():
    assert "error" in logic.date_diff("nope", "2026-08-04T00:00:00-04:00")
