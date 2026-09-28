"""Unit tests for jarvis/runlog/store.py (run-logging plan §7).

No network. Each test gets its own tmp SQLite DB and tmp JSONL root so
runs are fully isolated.
"""

from __future__ import annotations

import json
import sqlite3

import pytest

from jarvis.agents.base import CANCELLED_MESSAGE, TIMEOUT_MESSAGE
from jarvis.db import get_conn, run_migrations
from jarvis.runlog import store
from jarvis.runlog.store import (
    MAX_BUFFERED_EVENTS,
    MAX_SKILL_EVENTS,
    RUN_ORPHAN_AFTER_S,
    RunLogger,
    _display_status,
    get_run,
    get_skill_events,
    list_runs,
    list_skill_runs,
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
    def test_skill_cursor_survives_external_writer_and_privacy_scrub(self, db_path, root):
        rl = make_logger(db_path, root)
        rl.start()
        rl.skill_event("skill-creator", "a" * 64, "skill_selected")
        # Simulate durable activity beyond the still-live logger's counter.
        conn = get_conn(db_path)
        conn.execute("UPDATE skill_events SET seq=100 WHERE run_id='r1'")
        conn.commit()
        conn.close()
        rl.skill_event("skill-creator", "a" * 64, "skill_step_started",
                       step_id="offline-validate", attempt_id="attempt-1", status="running")
        page = get_skill_events("r1", after_seq=100, db_path=db_path)
        assert [event["seq"] for event in page["events"]] == [101]
        rl.mark_sensitive()
        page = get_skill_events("r1", after_seq=101, db_path=db_path)
        assert [event["seq"] for event in page["events"]] == [102]
        assert page["events"][0]["type"] == "protected_activity"
        assert page["events"][0]["skill_id"] is None

    def test_skill_sequence_allocation_serializes_independent_writers(self, db_path, root):
        from concurrent.futures import ThreadPoolExecutor

        rl = make_logger(db_path, root)
        rl.start()
        rl.skill_event("skill-creator", "a" * 64, "skill_selected")
        owner = rl.user_id

        def append(index):
            conn = get_conn(db_path)
            try:
                conn.execute("BEGIN IMMEDIATE")
                seq = store._next_skill_event_seq(conn, owner, "r1")
                conn.execute(
                    "INSERT INTO skill_events (user_id, run_id, request_id, event_id, seq, "
                    "schema_version, occurred_at, skill_id, skill_revision, type, status) "
                    "VALUES (?, 'r1', 'r1', ?, ?, 1, ?, 'skill-creator', ?, "
                    "'skill_resource_read', 'unknown')",
                    (owner, f"external-{index}", seq, store.now_iso(), "a" * 64),
                )
                conn.commit()
                return seq
            finally:
                conn.close()

        with ThreadPoolExecutor(max_workers=4) as pool:
            sequences = list(pool.map(append, range(16)))
        assert len(set(sequences)) == 16
        assert sorted(sequences) == list(range(min(sequences), max(sequences) + 1))
        rl.skill_event("skill-creator", "a" * 64, "skill_resource_read")
        page = get_skill_events("r1", after_seq=max(sequences), db_path=db_path)
        assert [event["seq"] for event in page["events"]] == [max(sequences) + 1]

    def test_skill_trace_storage_failure_does_not_log_exception_text(
        self, db_path, root, monkeypatch, caplog,
    ):
        rl = make_logger(db_path, root)

        def fail_with_private_detail(*_args, **_kwargs):
            raise RuntimeError("PRIVATE_SKILL_TRACE_CANARY")

        monkeypatch.setattr(store, "get_conn", fail_with_private_detail)
        rl.skill_event("technical-plan-document", "a" * 64, "skill_selected")

        assert "runlog_write_failed" in caplog.text
        assert "error_type=RuntimeError" in caplog.text
        assert "PRIVATE_SKILL_TRACE_CANARY" not in caplog.text

    def test_skill_events_are_typed_bounded_and_linked_to_run(self, db_path, root):
        rl = make_logger(db_path, root)
        rl.start()
        revision = "a" * 64
        rl.skill_event("technical-plan-document", revision, "skill_selected")
        rl.skill_event(
            "technical-plan-document", revision, "skill_step_finished",
            step_id="establish-scope", status="unknown",
            evidence_refs=[{"kind": "tool_call_id", "id": "tool-123"}],
        )
        rl.finish("done")

        page = get_skill_events("r1", db_path=db_path)
        assert page["trace_status"] == "recorded"
        assert [event["type"] for event in page["events"]] == [
            "skill_selected", "skill_step_finished",
        ]
        assert page["events"][0]["skill_revision"] == revision
        assert page["events"][1]["status"] == "unknown"
        assert page["events"][1]["evidence_refs"] == [
            {"kind": "tool_call_id", "id": "tool-123"},
        ]
        runs = list_skill_runs("technical-plan-document", db_path=db_path)
        assert [run["run_id"] for run in runs["runs"]] == ["r1"]
        assert "task" not in runs["runs"][0]

    def test_sensitive_skill_event_persists_no_skill_specific_data(self, db_path, root):
        rl = make_logger(db_path, root, sensitive=True)
        rl.start()
        rl.skill_event("technical-plan-document", "b" * 64, "skill_selected")
        rl.skill_event("technical-plan-document", "b" * 64, "skill_resource_read")
        rl.finish("protected")

        page = get_skill_events("r1", db_path=db_path)
        assert len(page["events"]) == 1
        event = page["events"][0]
        assert event["type"] == "protected_activity"
        assert event["skill_id"] is None
        assert event["skill_revision"] is None
        assert event["step_id"] is None
        assert event["evidence_refs"] == []
        assert list_skill_runs("technical-plan-document", db_path=db_path)["runs"] == []

    def test_becoming_sensitive_scrubs_earlier_skill_identity(self, db_path, root):
        rl = make_logger(db_path, root)
        rl.start()
        rl.skill_event("technical-plan-document", "e" * 64, "skill_selected")
        rl.mark_sensitive()
        rl.finish("protected")

        page = get_skill_events("r1", db_path=db_path)
        assert len(page["events"]) == 1
        assert page["events"][0]["type"] == "protected_activity"
        assert page["events"][0]["skill_id"] is None
        assert page["events"][0]["skill_revision"] is None

    def test_skill_event_caps_at_256_and_marks_truncation(self, db_path, root):
        rl = make_logger(db_path, root)
        rl.start()
        for _ in range(MAX_SKILL_EVENTS + 3):
            rl.skill_event("technical-plan-document", "c" * 64, "skill_selected")
        page = get_skill_events("r1", limit=100, db_path=db_path)
        assert page["has_more"] is True
        assert page["truncated"] is True  # trace-level state, even before the marker page
        all_events = []
        while True:
            all_events.extend(page["events"])
            if not page["has_more"]:
                break
            page = get_skill_events(
                "r1", after_seq=page["next_after_seq"], limit=100, db_path=db_path,
            )
        assert len(all_events) == MAX_SKILL_EVENTS
        assert all_events[-1]["type"] == "truncated"

    def test_skill_trace_is_user_scoped_and_cursors_are_validated(self, db_path, root):
        rl = make_logger(db_path, root)
        rl.start()
        rl.skill_event("technical-plan-document", "d" * 64, "skill_selected")
        rl.finish("done")
        assert get_skill_events("r1", db_path=db_path, user_id="other") is None
        assert list_skill_runs(
            "technical-plan-document", db_path=db_path, user_id="other",
        )["runs"] == []
        with pytest.raises(ValueError):
            list_skill_runs("technical-plan-document", cursor="bad cursor", db_path=db_path)

    def test_skill_run_cursor_pages_without_duplicate_runs(self, db_path, root):
        for run_id in ("older-run", "newer-run"):
            rl = make_logger(db_path, root, run_id=run_id)
            rl.start()
            rl.skill_event("technical-plan-document", "f" * 64, "skill_selected")
            rl.finish("done")

        first = list_skill_runs("technical-plan-document", limit=1, db_path=db_path)
        assert len(first["runs"]) == 1
        assert first["next_cursor"]
        second = list_skill_runs(
            "technical-plan-document", cursor=first["next_cursor"],
            limit=1, db_path=db_path,
        )
        assert len(second["runs"]) == 1
        assert second["next_cursor"] is None
        assert first["runs"][0]["run_id"] != second["runs"][0]["run_id"]

    def test_skill_event_rejects_malformed_evidence_and_false_status(self, db_path, root):
        rl = make_logger(db_path, root)
        rl.start()
        rl.skill_event(
            "technical-plan-document", "a" * 64, "skill_selected", status="passed",
        )
        rl.skill_event(
            "technical-plan-document", "a" * 64, "skill_step_finished",
            step_id="collect-evidence", status="passed",
            evidence_refs=[{"kind": "tool_call_id", "id": "../../private"}],
        )
        assert get_skill_events("r1", db_path=db_path)["events"] == []

    def test_generic_skill_event_cannot_claim_pass_even_with_receipt_reference(
        self, db_path, root,
    ):
        rl = make_logger(db_path, root)
        rl.start()
        rl.skill_event(
            "technical-plan-document", "a" * 64, "skill_step_finished",
            step_id="establish-scope", status="passed",
            evidence_refs=[{"kind": "check_receipt_id", "id": "receipt-123"}],
        )
        assert get_skill_events("r1", db_path=db_path)["events"] == []

    def test_run_can_become_sensitive_after_a_tool_result_source(self, db_path, root):
        rl = make_logger(db_path, root)
        rl.start()
        rl.mark_sensitive()
        rl.tool_result("repo_read_file", "PRIVATE_CANARY_midtask", 4, True)
        rl.finish("protected details withheld")

        conn = get_conn(db_path)
        row = conn.execute(
            "SELECT result_preview FROM agent_events WHERE run_id = ?", ("r1",)
        ).fetchone()
        conn.close()
        assert row[0] == "<sensitive>"
        payload = next(root.rglob("*.jsonl")).read_text()
        assert "PRIVATE_CANARY_midtask" not in payload

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
        (CANCELLED_MESSAGE, "cancelled"),
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


class TestFinishRedactionBinding:
    def test_finish_redaction_path_binds_reply(self, db_path, root):
        """T4a's redaction rebinds `reply` inside finish()'s _do closure.
        Without `nonlocal reply` that rebinding made `reply` a LOCAL of
        _do, so the first read raised UnboundLocalError, _safe swallowed
        it, and EVERY run stayed status='running' with no payload file
        (2026-08-28 → 08-31, 45 warnings, all of a day's runs orphaned).
        Both branches must finalize the row: plain and sensitive."""
        rl = make_logger(db_path, root, run_id="r-plain")
        rl.start()
        rl.finish("plain reply")
        rl2 = make_logger(db_path, root, run_id="r-sensitive", sensitive=True)
        rl2.start()
        rl2.finish("card 4111 1111 1111 1111")
        conn = get_conn(db_path)
        conn.row_factory = sqlite3.Row
        rows = {r["run_id"]: r for r in conn.execute(
            "SELECT run_id, status, reply_preview FROM agent_runs").fetchall()}
        conn.close()
        assert rows["r-plain"]["status"] == "ok"
        assert rows["r-plain"]["reply_preview"] == "plain reply"
        assert rows["r-sensitive"]["status"] == "ok"
        assert rows["r-sensitive"]["reply_preview"] == "<sensitive>"


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

    def test_unknown_tool_outcome_is_durable_and_never_exposes_arguments(
        self, db_path, root, capsys,
    ):
        rl = make_logger(db_path, root, run_id="r-unknown")
        rl.start()
        rl.tool_call(
            "send_message", {"recipient": "private@example.test", "body": "secret"},
            tool_call_id="provider-call-17",
        )
        rl.tool_outcome_unknown(
            "send_message", "provider-call-17", reason_code="cancelled_after_return",
        )
        rl.finish("CANCELLED: interrupted")

        detail = get_run("r-unknown", db_path=db_path, root=root)
        assert detail["unresolved_tool_calls"] == [{
            "tool_call_id": "provider-call-17",
            "tool": "send_message",
            "status": "unknown",
        }]
        unknown_event = next(
            event for event in detail["events"]
            if event["type"] == "tool_outcome_unknown"
        )
        assert unknown_event["tool_call_id"] == "provider-call-17"
        assert unknown_event["result_preview"] == "cancelled_after_return"
        assert unknown_event["args_preview"] is None
        assert unknown_event["args_preview"] is None
        assert "private@example.test" not in json.dumps(unknown_event)
        assert "secret" not in json.dumps(unknown_event)

        records = [
            json.loads(line)
            for line in (root / rl.payload_path).read_text().splitlines()
        ]
        unknown_record = next(
            record for record in records
            if record["type"] == "tool_outcome_unknown"
        )
        assert unknown_record["tool_call_id"] == "provider-call-17"
        assert "arguments" not in unknown_record
        assert "result" not in unknown_record
        assert "private@example.test" not in json.dumps(unknown_record)
        assert "secret" not in json.dumps(unknown_record)

        from jarvis.runlog.cli import _print_detail

        _print_detail(detail)
        output = capsys.readouterr().out
        assert "UNRESOLVED TOOL OUTCOMES" in output
        assert "verify before retrying" in output
        assert "provider-call-17" in output

    def test_interrupted_tool_call_without_result_is_exposed_as_unresolved(
        self, db_path, root,
    ):
        rl = make_logger(db_path, root, run_id="r-interrupted")
        rl.start()
        rl.tool_call("write_file", {"path": "safe.txt"}, tool_call_id="call-unknown")

        detail = get_run("r-interrupted", db_path=db_path, root=root)
        assert detail["unresolved_tool_calls"] == [{
            "tool_call_id": "call-unknown",
            "tool": "write_file",
            "status": "unresolved",
        }]

    def test_correlated_successful_tool_call_is_not_unresolved(self, db_path, root):
        rl = make_logger(db_path, root, run_id="r-resolved")
        rl.start()
        rl.tool_call("read_file", {"path": "safe.txt"}, tool_call_id="call-ok")
        rl.tool_result("read_file", "contents", 1, True, tool_call_id="call-ok")
        detail = get_run("r-resolved", db_path=db_path, root=root)
        assert detail["unresolved_tool_calls"] == []
