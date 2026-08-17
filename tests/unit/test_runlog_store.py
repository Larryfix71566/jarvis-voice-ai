"""Unit tests for jarvis/runlog/store.py (run-logging plan §7).

No network. Each test gets its own tmp SQLite DB and tmp JSONL root so
runs are fully isolated.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from jarvis.agents.base import TIMEOUT_MESSAGE
from jarvis.db import get_conn, run_migrations
from jarvis.runlog import store
from jarvis.runlog.store import (
    MAX_BUFFERED_EVENTS,
    RUN_ORPHAN_AFTER_S,
    RunLogger,
    _display_status,
    get_run,
    list_runs,
    parse_since,
    reconcile_orphaned_runs,
)


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "runlog.db"
    conn = get_conn(path)
    run_migrations(conn)
    conn.close()
    return path


@pytest.fixture
def root(tmp_path):
    return tmp_path / "payload_root"


def make_logger(db_path, root, run_id="r1", **kwargs):
    return RunLogger(
        run_id, "developer", "Developer", "do a thing",
        session_id="sess-1", db_path=db_path, root=root, **kwargs,
    )


class TestFullRun:
    def test_writes_one_agent_runs_row_and_expected_events(self, db_path, root):
        rl = make_logger(db_path, root)
        rl.start()
        rl.tool_call("git_status", {"a": 1})
        rl.tool_result("git_status", "clean", 12, True)
        rl.mcp_call("git_status", "mcp_git", True, 10)
        rl.finish("all done")

        conn = get_conn(db_path)
        conn.row_factory = sqlite3.Row
        runs = conn.execute("SELECT * FROM agent_runs").fetchall()
        assert len(runs) == 1
        row = dict(runs[0])
        assert row["status"] == "ok"
        assert row["tool_count"] == 1
        assert row["session_id"] == "sess-1"
        assert row["reply_preview"] == "all done"
        assert row["error"] is None

        events = conn.execute(
            "SELECT * FROM agent_events ORDER BY seq"
        ).fetchall()
        assert [e["type"] for e in events] == ["tool_call", "tool_result", "mcp_call"]
        conn.close()

    def test_model_recorded_when_passed(self, db_path, root):
        """MORTIMER_PLANNING_PATHWAY_PLAN.md P3."""
        rl = make_logger(db_path, root, model="gpt-test-model")
        rl.start()
        rl.finish("ok")

        conn = get_conn(db_path)
        conn.row_factory = sqlite3.Row
        row = dict(conn.execute("SELECT * FROM agent_runs").fetchone())
        assert row["model"] == "gpt-test-model"
        conn.close()

    def test_model_null_when_not_passed(self, db_path, root):
        """No caller-supplied model -> NULL, never a guessed/default value."""
        rl = make_logger(db_path, root)
        rl.start()
        rl.finish("ok")

        conn = get_conn(db_path)
        conn.row_factory = sqlite3.Row
        row = dict(conn.execute("SELECT * FROM agent_runs").fetchone())
        assert row["model"] is None
        conn.close()

    def test_jsonl_holds_untruncated_value_sqlite_holds_preview(self, db_path, root):
        rl = make_logger(db_path, root)
        big_result = "x" * (store.PREVIEW_CHARS + 500)
        rl.start()
        rl.tool_call("t", {})
        rl.tool_result("t", big_result, 1, True)
        rl.finish("ok")

        conn = get_conn(db_path)
        conn.row_factory = sqlite3.Row
        ev = conn.execute(
            "SELECT * FROM agent_events WHERE type='tool_result'"
        ).fetchone()
        assert len(ev["result_preview"]) == store.PREVIEW_CHARS
        conn.close()

        payload_file = root / rl.payload_path
        records = [json.loads(l) for l in payload_file.read_text().splitlines()]
        result_record = next(r for r in records if r["type"] == "tool_result")
        assert result_record["result"] == big_result
        assert len(result_record["result"]) > store.PREVIEW_CHARS


class TestStatusDerivation:
    @pytest.mark.parametrize("reply,expected", [
        ("all done", "ok"),
        ("", "ok"),
        (TIMEOUT_MESSAGE, "timeout"),
        ("FAILED: boom", "failed"),
        ("FAILED: the task could not be completed.", "failed"),
    ])
    def test_status_from_reply(self, db_path, root, reply, expected):
        rl = make_logger(db_path, root, run_id=f"r-{expected}")
        rl.start()
        rl.finish(reply)
        conn = get_conn(db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT status, error FROM agent_runs WHERE run_id=?",
            (f"r-{expected}",),
        ).fetchone()
        conn.close()
        assert row["status"] == expected
        if expected == "ok":
            assert row["error"] is None
        else:
            assert row["error"] == reply

    def test_timeout_message_matches_base_module(self):
        """Regression guard for store.py's local duplicate of
        jarvis.agents.base.TIMEOUT_MESSAGE (plan §5.3 note) — the two
        cannot be imported from each other without a cycle, so this test
        is what keeps them from silently drifting apart."""
        assert store._TIMEOUT_MESSAGE == TIMEOUT_MESSAGE


class TestIdempotentFinish:
    def test_finish_twice_is_a_noop(self, db_path, root):
        rl = make_logger(db_path, root)
        rl.start()
        rl.finish("first")
        rl.finish("second")  # must not raise, must not overwrite
        conn = get_conn(db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT reply_preview FROM agent_runs WHERE run_id=?", ("r1",)
        ).fetchone()
        conn.close()
        assert row["reply_preview"] == "first"


class TestEnabledFlag:
    def test_disabled_writes_no_row_and_no_file(self, db_path, root):
        rl = make_logger(db_path, root, enabled=False)
        rl.start()
        rl.tool_call("t", {})
        rl.tool_result("t", "r", 1, True)
        rl.finish("done")

        conn = get_conn(db_path)
        rows = conn.execute("SELECT * FROM agent_runs").fetchall()
        conn.close()
        assert rows == []
        assert not root.exists() or not any(root.rglob("*.jsonl"))


class TestWriteFailureIsSwallowed:
    def test_unwritable_db_path_does_not_raise(self, root, tmp_path):
        bad_path = tmp_path / "does" / "not" / "exist" / "unwritable.db"
        # Parent dir doesn't exist and get_conn will try to create it —
        # simulate a genuine failure by pointing at a path that collides
        # with a file instead of a directory.
        collision = tmp_path / "collision"
        collision.write_text("not a directory")
        bad_db = collision / "sub" / "runlog.db"
        rl = RunLogger("r-fail", "developer", "Developer", "task",
                        db_path=bad_db, root=root)
        rl.start()  # must not raise
        rl.finish("done")  # must not raise


class TestPayloadCap:
    def test_cap_trips_and_marks_dropped(self, db_path, root):
        rl = make_logger(db_path, root, run_id="r-cap")
        rl.start()
        for i in range(MAX_BUFFERED_EVENTS + 5):
            rl.tool_call(f"t{i}", {"i": i})
            rl.tool_result(f"t{i}", "r", 1, True)
        rl.finish("done")

        payload_file = root / rl.payload_path
        records = [json.loads(l) for l in payload_file.read_text().splitlines()]
        truncated = [r for r in records if r["type"] == "truncated"]
        assert len(truncated) == 1
        dropped_args = [
            r for r in records
            if r["type"] == "tool_call" and r.get("arguments") == store._DROPPED
        ]
        assert len(dropped_args) > 0


class TestParseSince:
    def test_relative_units(self):
        assert parse_since("2d") is not None
        assert parse_since("6h") is not None
        assert parse_since("30m") is not None

    def test_iso_date(self):
        assert parse_since("2026-01-01") is not None

    def test_none_and_garbage(self):
        assert parse_since(None) is None
        assert parse_since("") is None
        assert parse_since("not-a-date") is None


class TestDisplayStatusOrphan:
    def test_orphaned_past_threshold_without_rewriting_row(self, db_path, root):
        rl = make_logger(db_path, root, run_id="r-orphan")
        rl.start()  # never finished — simulates a crashed process

        conn = get_conn(db_path)
        conn.row_factory = sqlite3.Row
        row = dict(conn.execute(
            "SELECT * FROM agent_runs WHERE run_id=?", ("r-orphan",)
        ).fetchone())
        conn.close()

        from datetime import datetime, timedelta, timezone
        far_future = datetime.now(timezone.utc) + timedelta(seconds=store.ORPHAN_AFTER_S + 60)
        assert _display_status(row, far_future) == "orphaned"
        # The stored row itself is untouched — still 'running' at rest.
        assert row["status"] == "running"

        soon = datetime.now(timezone.utc) + timedelta(seconds=1)
        assert _display_status(row, soon) == "running"


class TestReconcileOrphanedRuns:
    """MORTIMER_AGENT_TRUST_PLAN.md D16."""

    def _insert_running_row(self, db_path, run_id, started_at):
        conn = get_conn(db_path)
        conn.execute(
            "INSERT INTO agent_runs (run_id, agent, display_name, task, "
            "status, started_at, tool_count) VALUES (?, 'developer', "
            "'Developer', 'task', 'running', ?, 0)",
            (run_id, started_at),
        )
        conn.commit()
        conn.close()

    def test_old_running_row_rewritten_to_orphaned(self, db_path):
        from datetime import datetime, timedelta, timezone
        old = (datetime.now(timezone.utc)
               - timedelta(seconds=RUN_ORPHAN_AFTER_S + 60)).isoformat()
        self._insert_running_row(db_path, "r-old", old)

        count = reconcile_orphaned_runs(db_path=db_path)
        assert count == 1

        conn = get_conn(db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT status FROM agent_runs WHERE run_id=?", ("r-old",)
        ).fetchone()
        conn.close()
        assert row["status"] == "orphaned"

    def test_recent_running_row_untouched(self, db_path):
        from datetime import datetime, timezone
        recent = datetime.now(timezone.utc).isoformat()
        self._insert_running_row(db_path, "r-recent", recent)

        count = reconcile_orphaned_runs(db_path=db_path)
        assert count == 0

        conn = get_conn(db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT status FROM agent_runs WHERE run_id=?", ("r-recent",)
        ).fetchone()
        conn.close()
        assert row["status"] == "running"

    def test_already_finished_rows_untouched(self, db_path, root):
        rl = make_logger(db_path, root, run_id="r-done")
        rl.start()
        rl.finish("ok")

        count = reconcile_orphaned_runs(db_path=db_path)
        assert count == 0

        conn = get_conn(db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT status FROM agent_runs WHERE run_id=?", ("r-done",)
        ).fetchone()
        conn.close()
        assert row["status"] == "ok"

    def test_idempotent_on_repeated_calls(self, db_path):
        from datetime import datetime, timedelta, timezone
        old = (datetime.now(timezone.utc)
               - timedelta(seconds=RUN_ORPHAN_AFTER_S + 60)).isoformat()
        self._insert_running_row(db_path, "r-old2", old)

        first = reconcile_orphaned_runs(db_path=db_path)
        second = reconcile_orphaned_runs(db_path=db_path)
        assert first == 1
        assert second == 0  # already orphaned, not 'running' anymore


class TestListAndGetRun:
    def test_list_runs_and_get_run_roundtrip(self, db_path, root):
        rl = make_logger(db_path, root, run_id="r-list")
        rl.start()
        rl.tool_call("t", {"x": 1})
        rl.tool_result("t", "ok", 5, True)
        rl.finish("done")

        runs = list_runs(db_path=db_path)
        assert len(runs) == 1
        assert runs[0]["run_id"] == "r-list"
        assert runs[0]["status"] == "ok"

        detail = get_run("r-list", db_path=db_path, root=root)
        assert detail is not None
        assert detail["run"]["run_id"] == "r-list"
        assert len(detail["events"]) == 2
        assert len(detail["payload"]) == 4  # run_start, tool_call, tool_result, run_end

    def test_get_run_missing_payload_file_returns_empty_list(self, db_path, root):
        rl = make_logger(db_path, root, run_id="r-nopayload")
        rl.start()
        rl.finish("done")
        # Delete the payload file to simulate pruning.
        (root / rl.payload_path).unlink()
        detail = get_run("r-nopayload", db_path=db_path, root=root)
        assert detail["payload"] == []

    def test_get_run_unknown_id_returns_none(self, db_path):
        assert get_run("does-not-exist", db_path=db_path) is None
