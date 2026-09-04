"""Unit tests for mcp_servers/mcp_reminders/logic.py (plan Phase 1 Tests)."""

import sqlite3
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from mcp_servers.mcp_reminders import logic

TZ = ZoneInfo("America/New_York")
FIXED_NOW = datetime(2026, 8, 4, 15, 0, tzinfo=TZ)


@pytest.fixture(autouse=True)
def freeze_time(monkeypatch):
    monkeypatch.setenv("JARVIS_TIMEZONE", "America/New_York")
    monkeypatch.setattr(logic, "_now", lambda: FIXED_NOW)


def _due_at_of(reminder_id):
    from jarvis.db import get_conn
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM reminders WHERE id = ?", (reminder_id,)
        ).fetchone()
    return row


class TestSetReminder:
    def test_happy_path_resolves_absolute_time(self, fresh_db):
        result = logic.set_reminder("call the dentist", "tomorrow at 9am")
        assert result["id"] == 1
        assert "Reminder set for Wednesday, August 5, 2026, 9:00 AM EDT" in result["message"]
        row = _due_at_of(result["id"])
        assert row["status"] == "pending"
        assert row["due_at"].startswith("2026-08-05T09:00")
        assert row["delivered"] == 0

    def test_relative_in_hours(self, fresh_db):
        result = logic.set_reminder("stretch", "in 2 hours")
        assert _due_at_of(result["id"])["due_at"].startswith("2026-08-04T17:00")

    def test_empty_message_error(self, fresh_db):
        assert "error" in logic.set_reminder("  ", "tomorrow")

    def test_unparseable_expression_error(self, fresh_db):
        assert "error" in logic.set_reminder("thing", "flibberty zzz")

    def test_past_time_rejected(self, fresh_db):
        result = logic.set_reminder("too late", "in 0 minutes")
        assert "in the past" in result["error"]


class TestListReminders:
    def test_pending_default_and_ordering(self, fresh_db):
        logic.set_reminder("later one", "in 3 hours")
        logic.set_reminder("sooner one", "in 1 hours")
        reminders = logic.list_reminders()["reminders"]
        assert [r["message"] for r in reminders] == ["sooner one", "later one"]

    def test_invalid_status_error(self, fresh_db):
        assert "error" in logic.list_reminders("bogus")

    def test_all_status(self, fresh_db):
        rid = logic.set_reminder("a", "in 1 hours")["id"]
        logic.complete_reminder(rid)
        logic.set_reminder("b", "in 2 hours")
        assert len(logic.list_reminders("all")["reminders"]) == 2
        assert len(logic.list_reminders("pending")["reminders"]) == 1
        assert len(logic.list_reminders("done")["reminders"]) == 1


class TestTransitions:
    def test_complete_happy(self, fresh_db):
        rid = logic.set_reminder("a", "in 1 hours")["id"]
        assert "marked done" in logic.complete_reminder(rid)["message"]
        assert _due_at_of(rid)["status"] == "done"

    def test_cancel_happy(self, fresh_db):
        rid = logic.set_reminder("a", "in 1 hours")["id"]
        assert "cancelled" in logic.cancel_reminder(rid)["message"]
        assert _due_at_of(rid)["status"] == "cancelled"

    def test_already_done_error(self, fresh_db):
        rid = logic.set_reminder("a", "in 1 hours")["id"]
        logic.complete_reminder(rid)
        assert "already done" in logic.complete_reminder(rid)["error"]
        assert "already done" in logic.cancel_reminder(rid)["error"]

    def test_not_found_error(self, fresh_db):
        assert "error" in logic.complete_reminder(999)
        assert "error" in logic.cancel_reminder(999)


class TestGetDueReminders:
    def _insert_due(self, message, due_at, delivered=0):
        from jarvis.db import get_conn, now_iso
        with get_conn() as conn:
            cur = conn.execute(
                "INSERT INTO reminders (message, due_at, status, delivered, created_at) "
                "VALUES (?, ?, 'pending', ?, ?)",
                (message, due_at, delivered, now_iso()),
            )
            return cur.lastrowid

    def test_fetches_and_marks_delivered_atomically(self, fresh_db):
        self._insert_due("overdue one", "2026-08-04T14:00:00-04:00")
        self._insert_due("future one", "2026-08-04T16:00:00-04:00")
        result = logic.get_due_reminders()
        assert [r["message"] for r in result["reminders"]] == ["overdue one"]
        row = _due_at_of(result["reminders"][0]["id"])
        assert row["delivered"] == 1

    def test_second_call_returns_empty(self, fresh_db):
        self._insert_due("overdue one", "2026-08-04T14:00:00-04:00")
        logic.get_due_reminders()
        assert logic.get_due_reminders()["reminders"] == []

    def test_already_delivered_not_returned(self, fresh_db):
        self._insert_due("old", "2026-08-04T14:00:00-04:00", delivered=1)
        assert logic.get_due_reminders()["reminders"] == []


class TestPeekDueRemindersAndMarkNotified:
    """GC9 (gap-closure plan, 2026-09-04): plain functions, not tools --
    peek_due_reminders never sets delivered (only get_due_reminders does),
    and mark_notified never touches delivered either."""

    def _insert(self, message, due_at, *, delivered=0, notified_at=None):
        from jarvis.db import get_conn, now_iso
        with get_conn() as conn:
            cur = conn.execute(
                "INSERT INTO reminders (message, due_at, status, delivered, "
                "notified_at, created_at) VALUES (?, ?, 'pending', ?, ?, ?)",
                (message, due_at, delivered, notified_at, now_iso()),
            )
            return cur.lastrowid

    def test_peek_excludes_delivered_notified_and_inside_grace(self, fresh_db):
        overdue = (FIXED_NOW - timedelta(minutes=2)).isoformat()
        inside_grace = (FIXED_NOW - timedelta(seconds=10)).isoformat()

        self._insert("due and unspoken", overdue)
        self._insert("just barely due", inside_grace)
        self._insert("delivered already", overdue, delivered=1)
        self._insert("notified already", overdue, notified_at="2026-08-04T14:00:00-04:00")

        result = logic.peek_due_reminders(grace_s=60.0)

        assert [r["message"] for r in result["reminders"]] == ["due and unspoken"]

    def test_mark_notified_leaves_delivered_untouched(self, fresh_db):
        rid = self._insert("call mom", (FIXED_NOW - timedelta(minutes=2)).isoformat())

        result = logic.mark_notified([rid])

        assert result == {"marked": 1}
        row = _due_at_of(rid)
        assert row["notified_at"] is not None
        assert row["delivered"] == 0


class TestCopiedDateLogic:
    """The copied date-parsing logic must behave like mcp-time's."""

    def test_relative_and_error(self):
        assert logic._resolve_date_expression("tomorrow")["iso"].startswith("2026-08-05")
        assert "error" in logic._resolve_date_expression("")
        assert "error" in logic._resolve_date_expression("zzz qqq nothing")

    def test_weekday_and_explicit_time(self):
        assert logic._resolve_date_expression("next friday")["iso"].startswith("2026-08-14")
        result = logic._resolve_date_expression("tomorrow at 2:30pm")
        assert result["iso"].startswith("2026-08-05T14:30")

    def test_tonight_and_dateutil_fallback(self):
        assert logic._resolve_date_expression("tonight")["iso"].startswith("2026-08-04T20:00")
        assert logic._resolve_date_expression("August 20 at 9am")["iso"].startswith(
            "2026-08-20T09:00"
        )

    def test_day_after_and_24h_time(self):
        assert logic._resolve_date_expression("day after tomorrow")["iso"].startswith(
            "2026-08-06"
        )
        assert logic._resolve_date_expression("tomorrow at 14:30")["iso"].startswith(
            "2026-08-05T14:30"
        )

    def test_invalid_explicit_time_keeps_date(self):
        result = logic._resolve_date_expression("tomorrow at 25:99")
        assert result["iso"].startswith("2026-08-05T15:00")
