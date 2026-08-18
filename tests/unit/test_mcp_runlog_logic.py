"""Unit tests for mcp_runlog logic (MORTIMER_MODEL_DISCIPLINE_AND_MAC_SHELL_PLAN.md C1).

Isolated DB per test (JARVIS_DB_PATH override, same T1 discipline as
test_upgrade_agent.py) — this module must never write to the live
data/jarvis.db just by being imported/tested.
"""

from __future__ import annotations

import pytest

from jarvis.db import get_conn, now_iso, run_migrations
from jarvis.runlog.store import RunLogger
from mcp_servers.mcp_runlog import logic


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "runlog_test.db"
    monkeypatch.setenv("JARVIS_DB_PATH", str(db_path))
    conn = get_conn(db_path)
    run_migrations(conn)
    conn.close()
    monkeypatch.chdir(tmp_path)  # payload files write relative to cwd


def _make_run(run_id, agent="developer", task="do a thing", status="ok",
              model="kimi-k3", error=None):
    rl = RunLogger(run_id, agent, agent.title(), task, model=model, enabled=True)
    rl.start()
    if status == "ok":
        rl.finish("done")
    else:
        rl.finish(f"FAILED: {error or 'boom'}")
    return rl


class TestRunlogList:
    def test_lists_newest_first_with_filters(self):
        _make_run("r1", agent="developer", task="implement geolocation")
        _make_run("r2", agent="analyst", task="get weather")
        _make_run("r3", agent="developer", task="add a dismiss button", status="failed")
        result = logic.runlog_list(agent="developer")
        assert result["ok"] is True
        run_ids = [r["run_id"] for r in result["runs"]]
        assert run_ids == ["r3", "r1"]  # newest first, analyst excluded

    def test_task_contains_filters_case_insensitively(self):
        _make_run("r1", task="implement geolocation phase 1")
        _make_run("r2", task="get the weather")
        result = logic.runlog_list(task_contains="GEOLOCATION")
        assert [r["run_id"] for r in result["runs"]] == ["r1"]

    def test_limit_clamped_to_max(self):
        for i in range(5):
            _make_run(f"r{i}")
        result = logic.runlog_list(limit=1000)
        assert len(result["runs"]) <= logic.LIST_LIMIT_MAX

    def test_status_filter(self):
        _make_run("r1", status="ok")
        _make_run("r2", status="failed", error="kaboom")
        result = logic.runlog_list(status="failed")
        assert [r["run_id"] for r in result["runs"]] == ["r2"]

    def test_never_returns_full_payload_only_preview(self):
        _make_run("r1", task="x" * 500)
        result = logic.runlog_list()
        assert len(result["runs"][0]["task"]) <= logic.TASK_PREVIEW_CHARS + 1


class TestRunlogDetail:
    def test_returns_run_and_events(self):
        _make_run("r1", agent="developer", task="do the thing")
        result = logic.runlog_detail("r1")
        assert result["ok"] is True
        assert result["run"]["run_id"] == "r1"
        assert result["run"]["agent"] == "developer"
        assert "events" in result

    def test_unknown_run_id_returns_error(self):
        result = logic.runlog_detail("does-not-exist")
        assert result["ok"] is False
        assert "does-not-exist" in result["error"]


class TestRunlogStats:
    def test_aggregates_by_agent_and_model(self):
        _make_run("r1", agent="developer", model="kimi-k3", status="ok")
        _make_run("r2", agent="developer", model="kimi-k3", status="failed", error="x")
        _make_run("r3", agent="analyst", model=None, status="ok")
        result = logic.runlog_stats(since="30d")
        assert result["ok"] is True
        assert result["total_runs"] == 3
        assert result["by_agent_status"]["developer"]["ok"] == 1
        assert result["by_agent_status"]["developer"]["failed"] == 1
        assert result["model_success_rate"]["kimi-k3"] == 0.5


class TestCouncilList:
    def test_lists_recent_rounds(self):
        conn = get_conn()
        conn.execute(
            "INSERT INTO council_rounds (round_id, workflow, placement, "
            "trigger, tier, goal, proposer_count, judge_count, "
            "winner_profile, status, started_at) VALUES "
            "('round-1', 'planning', 'doc', 'manual', 1, 'test goal', "
            "2, 1, 'kimi-k3', 'ok', ?)",
            (now_iso(),),
        )
        conn.commit()
        conn.close()
        result = logic.council_list()
        assert result["ok"] is True
        assert len(result["rounds"]) == 1
        assert result["rounds"][0]["round_id"] == "round-1"
        assert result["rounds"][0]["workflow"] == "planning"
        assert result["rounds"][0]["winner_profile"] == "kimi-k3"
