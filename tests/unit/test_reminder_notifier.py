"""Unit tests for jarvis/admin/reminder_notifier.py (gap-closure plan GC9).
tick_once is exercised directly against a temp DB (JARVIS_DB_PATH) with a
recording `post` fake -- never a real osascript call."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from jarvis.admin.reminder_notifier import ReminderNotifier
from jarvis.db import get_conn, now_iso, run_migrations


@pytest.fixture()
def db(tmp_path, monkeypatch):
    path = tmp_path / "reminders.db"
    monkeypatch.setenv("JARVIS_DB_PATH", str(path))
    # mcp_servers.mcp_reminders.logic._tz() reads JARVIS_TIMEZONE, and
    # jarvis.config.bridge_settings_to_env uses os.environ.setdefault on it
    # -- once any earlier test calls that with no override present, the
    # real process environment keeps a non-UTC zone for the rest of the
    # session (setdefault is not monkeypatch, so nothing reverts it). Pin
    # it here so this test's UTC-based due_at values compare correctly
    # against peek_due_reminders' ISO-string comparison regardless of
    # what ran before it -- same defence test_mcp_reminders_logic.py's
    # freeze_time fixture already takes.
    monkeypatch.setenv("JARVIS_TIMEZONE", "UTC")
    run_migrations()
    return path


def _insert_reminder(due_delta_s: float, *, delivered: int = 0, message: str = "call mom") -> int:
    due_at = (datetime.now(timezone.utc) + timedelta(seconds=due_delta_s)).isoformat()
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO reminders (message, due_at, status, delivered, created_at) "
            "VALUES (?, ?, 'pending', ?, ?)",
            (message, due_at, delivered, now_iso()),
        )
        return cur.lastrowid


def _row(reminder_id: int):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM reminders WHERE id = ?", (reminder_id,)
        ).fetchone()


def test_reminder_due_past_grace_is_notified_and_delivered_stays_0(db):
    rid = _insert_reminder(-120)  # due 2 minutes ago
    posted = []

    def post(message: str) -> bool:
        posted.append(message)
        return True

    notifier = ReminderNotifier(post=post)
    sent = notifier.tick_once()

    assert sent == 1
    assert posted == ["call mom"]
    row = _row(rid)
    assert row["notified_at"] is not None
    assert row["delivered"] == 0


def test_reminder_inside_grace_window_is_not_notified(db):
    _insert_reminder(-10)  # due 10s ago, grace is 60s by default
    posted = []

    notifier = ReminderNotifier(post=lambda m: posted.append(m) or True)
    sent = notifier.tick_once()

    assert sent == 0
    assert posted == []


def test_post_returning_false_leaves_notified_at_null(db):
    rid = _insert_reminder(-120)

    notifier = ReminderNotifier(post=lambda m: False)
    sent = notifier.tick_once()

    assert sent == 0
    assert _row(rid)["notified_at"] is None


def test_second_tick_does_not_renotify(db):
    _insert_reminder(-120)
    posted = []

    notifier = ReminderNotifier(post=lambda m: posted.append(m) or True)
    notifier.tick_once()
    notifier.tick_once()

    assert posted == ["call mom"]  # exactly one call across two ticks


def test_delivered_rows_are_never_notified(db):
    rid = _insert_reminder(-120, delivered=1)
    posted = []

    notifier = ReminderNotifier(post=lambda m: posted.append(m) or True)
    sent = notifier.tick_once()

    assert sent == 0
    assert posted == []
    assert _row(rid)["notified_at"] is None


def test_post_exception_retries_failed_row_and_continues_others(db, caplog):
    failed_id = _insert_reminder(-120, message="retry me")
    other_id = _insert_reminder(-120, message="deliver me")
    posted = []

    def post(message):
        if message == "retry me":
            raise RuntimeError("private notification details")
        posted.append(message)
        return True

    notifier = ReminderNotifier(post=post)
    assert notifier.tick_once() == 1
    assert _row(failed_id)["notified_at"] is None
    assert _row(other_id)["notified_at"] is not None
    assert "RuntimeError" in caplog.text
    assert "private notification details" not in caplog.text
    notifier._post = lambda message: posted.append(message) or True
    assert notifier.tick_once() == 1
    assert notifier.tick_once() == 0
    assert posted == ["deliver me", "retry me"]
    assert _row(failed_id)["delivered"] == _row(other_id)["delivered"] == 0
