"""Status spec T3.2 (L12) — the notice outbox, jarvis/notices.py."""

from __future__ import annotations

import logging

import pytest

from jarvis import notices
from jarvis.db import get_conn


@pytest.fixture(autouse=True)
def _db(fresh_db, monkeypatch):
    monkeypatch.delenv("JARVIS_NOTICES_ENABLED", raising=False)
    return fresh_db


def _rows():
    conn = get_conn()
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM notices ORDER BY id")]
    finally:
        conn.close()


def test_add_take_delivered_once():
    first = notices.add_notice("late_result", "Developer", "audit finished")
    second = notices.add_notice("daily_status", "daily", "all keys ok")
    assert first > 0 and second > first

    taken = notices.take_pending()
    assert [(n["id"], n["kind"], n["source"], n["text"]) for n in taken] == [
        (first, "late_result", "Developer", "audit finished"),
        (second, "daily_status", "daily", "all keys ok"),
    ]
    assert all(r["delivered_at"] for r in _rows())
    assert notices.take_pending() == [], "a notice is spoken once"


def test_take_is_oldest_first_and_bounded():
    ids = [notices.add_notice("late_result", "Analyst", f"n{i}") for i in range(7)]
    first = notices.take_pending()
    assert [n["id"] for n in first] == ids[:notices.MAX_DELIVERED_PER_CONNECT]
    rest = notices.take_pending()
    assert [n["id"] for n in rest] == ids[notices.MAX_DELIVERED_PER_CONNECT:]
    assert notices.take_pending(limit=1) == []


def test_text_is_truncated_to_600():
    notices.add_notice("late_result", "Developer", "x" * 5000)
    (row,) = _rows()
    assert len(row["text"]) == notices.MAX_NOTICE_CHARS == 600


def test_unknown_kind_is_refused_without_raising():
    assert notices.add_notice("gossip", "x", "y") == -1
    assert _rows() == []


@pytest.mark.parametrize("value", ["false", "0", "no", " OFF "])
def test_kill_switch(monkeypatch, value):
    notices.add_notice("late_result", "Developer", "queued while on")
    monkeypatch.setenv("JARVIS_NOTICES_ENABLED", value)
    assert notices.add_notice("late_result", "Developer", "while off") == -1
    assert notices.take_pending() == []
    assert len(_rows()) == 1 and _rows()[0]["delivered_at"] is None
    monkeypatch.delenv("JARVIS_NOTICES_ENABLED")
    assert [n["text"] for n in notices.take_pending()] == ["queued while on"]


def test_a_missing_table_never_raises(tmp_path, monkeypatch, caplog):
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "unmigrated.db"))
    with caplog.at_level(logging.WARNING, logger="jarvis.notices"):
        assert notices.add_notice("late_result", "Developer", "x") == -1
        assert notices.take_pending() == []
    assert "notice_add_failed" in caplog.text
    assert "notice_take_failed" in caplog.text


def test_render_for_greeting_golden():
    assert notices.render_for_greeting([]) == ""
    items = [{"text": "The developer finished the audit."},
             {"text": "All model keys work."}]
    assert notices.render_for_greeting(items) == (
        " While they were away: The developer finished the audit. / All model "
        "keys work. Mention these in one or two short sentences after greeting."
    )
