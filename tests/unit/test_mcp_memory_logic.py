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


class TestMemorySearch:
    """M6 (MORTIMER_MEMORY_CAPACITY_PLAN.md) — thin wrapper over
    jarvis.memory.search_facts; pins that the tool finds archived facts
    too, since that is the whole point of the recall path."""

    def test_finds_live_and_archived_facts(self, conn):
        from jarvis.memory import archive_fact

        _fact(conn, "user.preference.old_layout", "Larry liked the old dashboard layout")
        conn.commit()
        archive_fact(conn, "user.preference.old_layout", "aged-out")
        conn.commit()

        out = logic.memory_search("dashboard")
        assert out["ok"] is True
        assert out["count"] == 1
        assert out["results"][0]["key"] == "user.preference.old_layout"
        assert out["results"][0]["archived"] is True

    def test_empty_query_returns_no_results_not_error(self, conn):
        out = logic.memory_search("")
        assert out["ok"] is True
        assert out["results"] == []


class TestMemoryGraphView:
    """MORTIMER_GRAPH_LAYER_PLAN.md GL12 — thin over jarvis.graphs.build; the
    tool never returns nodes/edges, only the picture URL and a sentence."""

    def test_memory_graph_view_returns_url_and_summary_not_nodes(self, conn):
        _fact(conn, "user.style.a", "short answers")
        conn.commit()
        out = logic.memory_graph_view(focus="user.style.a")
        assert out["ok"] is True
        assert "nodes" not in out
        assert out["image_url"].startswith("http://127.0.0.1:7861/api/graph/memory/image.png?")
        assert "focus=" in out["image_url"]

    def test_memory_graph_unmatched_focus_falls_back_to_overview(self, conn):
        # Status spec T4.6 replaces test_memory_graph_view_error_passthrough:
        # an unknown memory topic shows the overview, flagged, not an error.
        _fact(conn, "user.style.a", "short answers")
        conn.commit()
        out = logic.memory_graph_view(focus="zzz-nothing")
        assert out["ok"] is True
        assert out["focus_miss"] == "zzz-nothing"
        assert out["focus"] is None
        assert "nodes" not in out
        assert "focus=&" in out["image_url"]
        assert out["summary"].endswith("of the whole graph; 0 of them archived.")

    def test_memory_graph_matched_focus_has_no_focus_miss(self, conn):
        _fact(conn, "user.style.a", "short answers")
        conn.commit()
        assert "focus_miss" not in logic.memory_graph_view(focus="user.style.a")


class TestMemoryRestore:
    """W10 (MORTIMER_VOICE_WORKFLOWS_PLAN.md): restore any archived memory
    by voice. Thin over jarvis.memory.restore_fact."""

    def test_restores_an_archived_fact_and_commits(self, conn, tmp_path):
        _fact(conn, "user.style.no_lookups", "prefers no lookups")
        conn.execute("UPDATE memories SET archived_at = ?, became = 'not-stated:review-112' "
                     "WHERE key = 'user.style.no_lookups'", (now_iso(),))
        conn.commit()
        out = logic.memory_restore("user.style.no_lookups")
        assert out["ok"] is True and out["was"] == "not-stated:review-112"
        # A fresh connection sees it live: the tool committed.
        fresh = get_conn(tmp_path / "mem.db")
        try:
            row = fresh.execute("SELECT archived_at, became FROM memories "
                                "WHERE key = 'user.style.no_lookups'").fetchone()
            assert row["archived_at"] is None and row["became"] is None
        finally:
            fresh.close()

    def test_a_live_or_unknown_key_is_refused(self, conn):
        _fact(conn, "user.name", "Larry")
        conn.commit()
        assert "already in memory" in logic.memory_restore("user.name")["error"]
        miss = logic.memory_restore("user.nothing")
        assert miss["ok"] is False and miss["candidates"] == []
