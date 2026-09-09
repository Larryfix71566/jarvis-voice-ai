"""Tests for jarvis.graphs.execution_graph (MORTIMER_GRAPH_LAYER_PLAN.md §5 step 5, §7)."""
import pytest

from jarvis.db import get_conn, run_migrations
from jarvis.graphs.execution_graph import build_execution_graph, resolve_execution_focus
from jarvis.graphs import config as gcfg


@pytest.fixture()
def conn(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "g.db"))
    c = get_conn(tmp_path / "g.db")
    run_migrations(c)
    yield c
    c.close()


def _insert_run(conn, run_id, *, agent="developer", session_id="s", model=None,
                 started_at="2026-01-01T00:00:00Z", status="ok"):
    conn.execute(
        "INSERT INTO agent_runs(run_id, session_id, agent, task, status, started_at, model) "
        "VALUES (?, ?, ?, 't', ?, ?, ?)",
        (run_id, session_id, agent, status, started_at, model),
    )


def _insert_event(conn, run_id, seq, type_, tool, ok=None):
    conn.execute(
        "INSERT INTO agent_events(run_id, seq, type, tool, ok, created_at) VALUES (?, ?, ?, ?, ?, 't')",
        (run_id, seq, type_, tool, ok),
    )


def _seed_base(conn):
    _insert_run(conn, "r1", model="m", started_at="2026-01-02T00:00:00Z")
    _insert_run(conn, "r2", model=None, started_at="2026-01-01T00:00:00Z")
    _insert_event(conn, "r1", 1, "mcp_call", "t1", ok=1)
    _insert_event(conn, "r1", 3, "mcp_call", "t2", ok=0)
    _insert_event(conn, "r1", 2, "tool_result", "t1", ok=1)
    _insert_event(conn, "r1", 4, "tool_result", "t2", ok=0)
    _insert_event(conn, "r1", 0, "tool_call", "t1", ok=1)
    _insert_event(conn, "r1", 5, "tool_result", None, ok=1)
    _insert_event(conn, "r2", 1, "tool_result", "t3", ok=1)
    conn.execute(
        "INSERT INTO procedures(id, agent, label, description, source_run_ids, created_at, updated_at) "
        "VALUES (1, 'developer', 'p1', 'd1', '[\"r1\"]', 't', 't')"
    )
    conn.execute(
        "INSERT INTO procedures(id, agent, label, description, source_run_ids, created_at, updated_at) "
        "VALUES (2, 'developer', 'p2', 'd2', '[\"outside1\"]', 't', 't')"
    )
    conn.commit()


def test_nodes_and_structural_edges(conn):
    _seed_base(conn)
    g = build_execution_graph(conn, since=None)
    in_session = {(e.src, e.dst) for e in g.edges if e.type == "in_session"}
    assert ("run:r1", "session:s") in in_session
    assert ("run:r2", "session:s") in in_session
    by_agent = {(e.src, e.dst) for e in g.edges if e.type == "by_agent"}
    assert ("run:r1", "agent:developer") in by_agent
    assert ("run:r2", "agent:developer") in by_agent
    ran_on = {(e.src, e.dst) for e in g.edges if e.type == "ran_on"}
    assert ran_on == {("run:r1", "model:m")}
    assert "model:m" in g.nodes
    assert not any(nid.startswith("model:") and nid != "model:m" for nid in g.nodes)


def test_called_edges_prefer_mcp_call_rows(conn):
    _seed_base(conn)
    g = build_execution_graph(conn, since=None)
    r1_called = [e for e in g.edges if e.type == "called" and e.src == "run:r1"]
    assert len(r1_called) == 2
    assert all(e.attrs["event_type"] == "mcp_call" for e in r1_called)
    t2_edge = [e for e in r1_called if e.dst == "tool:t2"][0]
    assert t2_edge.attrs["ok"] == 0


def test_called_edges_fall_back_to_tool_result_when_no_mcp_call(conn):
    _seed_base(conn)
    g = build_execution_graph(conn, since=None)
    r2_called = [e for e in g.edges if e.type == "called" and e.src == "run:r2"]
    assert r2_called and all(e.attrs["event_type"] == "tool_result" for e in r2_called)


def test_taught_edge_from_procedures(conn):
    _seed_base(conn)
    g = build_execution_graph(conn, since=None)
    taught = [(e.src, e.dst) for e in g.edges if e.type == "taught"]
    assert ("run:r1", "procedure:1") in taught
    assert "procedure:2" not in g.nodes


def test_since_filters_and_run_cap_truncates(conn, monkeypatch):
    _seed_base(conn)
    g = build_execution_graph(conn, since="2026-01-01T12:00:00Z")
    assert "run:r2" not in g.nodes
    assert "run:r1" in g.nodes

    g_all = build_execution_graph(conn, since=None)
    assert "run:r1" in g_all.nodes and "run:r2" in g_all.nodes
    assert g_all.truncated is False

    monkeypatch.setattr(gcfg, "GRAPH_EXECUTION_MAX_RUNS", 1)
    g2 = build_execution_graph(conn, since=None)
    assert g2.truncated is True
    assert g2.truncated_reason == "run cap"


def test_resolve_focus_order(conn):
    _insert_run(conn, "dup1abc", model="m", started_at="2026-01-01T00:00:00Z")
    _insert_run(conn, "dup2xyz", model=None, started_at="2026-01-01T00:00:00Z")
    _insert_event(conn, "dup1abc", 1, "mcp_call", "dup", ok=1)
    conn.commit()
    g = build_execution_graph(conn, since=None)

    assert resolve_execution_focus(conn, g, "dup1abc") == "run:dup1abc"
    assert resolve_execution_focus(conn, g, "dup1") == "run:dup1abc"          # unique prefix
    assert resolve_execution_focus(conn, g, "dup") == "tool:dup"             # ambiguous run prefix -> tool
    assert resolve_execution_focus(conn, g, "developer") == "agent:developer"
    assert resolve_execution_focus(conn, g, "nonexistent-zzz") is None
