"""Unit tests for mcp_servers/mcp_memory/logic.py (Larry 2026-08-21 —
voice control of the Memory panel's review queue, wired to the librarian).
Thin-wrapper discipline: these tests pin that the tools call the SAME
jarvis.memory_sweep functions the sidecar endpoints use, so voice and
console cannot disagree about what resolving a review does."""

from __future__ import annotations

import json

import pytest

from jarvis.db import get_conn, now_iso, run_migrations
from mcp_servers.mcp_memory import logic


@pytest.fixture()
def conn(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "mem.db"))
    c = get_conn(tmp_path / "mem.db")
    run_migrations(c)
    yield c
    c.close()


def _fact(conn, key, content, tier="preference"):
    conn.execute(
        "INSERT INTO memories (kind, key, content, created_at, updated_at, tier) "
        "VALUES ('fact', ?, ?, ?, ?, ?)",
        (key, content, now_iso(), now_iso(), tier),
    )


def _review(conn, kind, keys, detail="d"):
    conn.execute(
        "INSERT INTO memory_reviews (kind, keys_json, detail, status, created_at) "
        "VALUES (?, ?, ?, 'open', ?)",
        (kind, json.dumps(keys), detail, now_iso()),
    )
    conn.commit()
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


class TestReviewList:
    def test_lists_open_reviews_with_valid_actions(self, conn):
        _review(conn, "contradiction", ["a", "b"], "a vs b")
        _review(conn, "audience", ["c"], "c is a task rule")
        out = logic.review_list()
        assert out["ok"] is True
        assert out["total_open"] == 2
        kinds = {r["kind"]: r for r in out["reviews"]}
        assert "keep_a" in kinds["contradiction"]["actions"]
        assert "convert_workflow" in kinds["audience"]["actions"]

    def test_limit_is_bounded(self, conn):
        for i in range(5):
            _review(conn, "cluster", [f"k{i}", f"j{i}"])
        out = logic.review_list(limit=2)
        assert len(out["reviews"]) == 2
        assert out["total_open"] == 5

    def test_empty_queue_is_ok_not_error(self, conn):
        out = logic.review_list()
        assert out == {"ok": True, "total_open": 0, "reviews": []}


class TestReviewResolve:
    def test_keep_a_archives_b(self, conn):
        _fact(conn, "a", "short answers")
        _fact(conn, "b", "long answers")
        rid = _review(conn, "contradiction", ["a", "b"])
        out = logic.review_resolve(rid, "keep_a")
        assert out["ok"] is True
        row = conn.execute(
            "SELECT archived_at FROM memories WHERE key='b'").fetchone()
        assert row["archived_at"] is not None
        live_a = conn.execute(
            "SELECT archived_at FROM memories WHERE key='a'").fetchone()
        assert live_a["archived_at"] is None

    def test_dismiss_keeps_both(self, conn):
        _fact(conn, "a", "x")
        _fact(conn, "b", "y")
        rid = _review(conn, "contradiction", ["a", "b"])
        out = logic.review_resolve(rid, "dismiss")
        assert out["ok"] is True
        live = conn.execute(
            "SELECT COUNT(*) FROM memories WHERE archived_at IS NULL"
        ).fetchone()[0]
        assert live == 2

    def test_bad_action_returns_spoken_friendly_error(self, conn):
        _fact(conn, "a", "x")
        _fact(conn, "b", "y")
        rid = _review(conn, "contradiction", ["a", "b"])
        out = logic.review_resolve(rid, "obliterate")
        assert out["ok"] is False
        assert "unsupported action" in out["error"]

    def test_unknown_id_returns_error_not_traceback(self, conn):
        out = logic.review_resolve(99999, "dismiss")
        assert out["ok"] is False
