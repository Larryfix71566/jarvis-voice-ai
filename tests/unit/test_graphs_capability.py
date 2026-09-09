"""Tests for jarvis.graphs.capability_graph (MORTIMER_GRAPH_LAYER_PLAN.md §5 step 4, §7)."""
from pathlib import Path

import pytest

from jarvis.db import get_conn, run_migrations
from jarvis.graphs.capability_graph import build_capability_graph, resolve_capability_focus

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "graphs"


@pytest.fixture()
def conn(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "g.db"))
    c = get_conn(tmp_path / "g.db")
    run_migrations(c)
    yield c
    c.close()


def _seed(conn):
    conn.execute(
        "INSERT INTO procedures(id, agent, label, description, source_run_ids, created_at, updated_at) "
        "VALUES (1, 'developer', 'p1', 'd1', '[\"r1\",\"r2\"]', 't', 't')"
    )
    conn.execute(
        "INSERT INTO procedures(id, agent, label, description, source_run_ids, created_at, updated_at) "
        "VALUES (2, 'ghost', 'p2', 'd2', 'not json', 't', 't')"
    )
    conn.execute(
        "INSERT INTO agent_runs(run_id, agent, task, status, started_at) "
        "VALUES ('r1', 'developer', 't', 'ok', 't')"
    )
    conn.execute(
        "INSERT INTO memories(kind, key, content, created_at, updated_at, archived_at, became) "
        "VALUES ('fact', 'k', 'v', 't', 't', 't', 'workflow:graph-test-workflow')"
    )
    conn.execute(
        "INSERT INTO memories(kind, key, content, created_at, updated_at, archived_at, became) "
        "VALUES ('fact', 'k2', 'v', 't', 't', 't', 'workflow:no-such-file')"
    )
    conn.commit()


def _build(conn, *, skills_dir=None, skills_config=None):
    return build_capability_graph(
        conn,
        skills_dir=skills_dir or FIXTURES / "skills",
        skills_config=skills_config or FIXTURES / "skills.yaml",
        workflows_dir=FIXTURES / "workflows",
        agents_yaml=FIXTURES / "agents.yaml",
    )


def test_procedure_edges(conn):
    _seed(conn)
    g = _build(conn)
    learned_by = [(e.src, e.dst) for e in g.edges if e.type == "learned_by"]
    assert ("procedure:1", "agent:developer") in learned_by
    learned_from = [(e.src, e.dst) for e in g.edges if e.type == "learned_from"]
    assert ("procedure:1", "run:r1") in learned_from
    assert ("procedure:1", "run:r2") in learned_from
    assert g.nodes["run:r1"].attrs.get("status") == "ok"
    assert g.nodes["run:r2"].attrs.get("pruned") is True
    assert g.nodes["agent:ghost"].attrs.get("unknown") is True


def test_skill_promoted_from_and_for_agent(conn):
    _seed(conn)
    g = _build(conn)
    promoted = [(e.src, e.dst) for e in g.edges if e.type == "promoted_from"]
    assert ("skill:graph-test-skill", "procedure:1") in promoted
    for_agent = [(e.src, e.dst) for e in g.edges if e.type == "for_agent"]
    assert ("skill:graph-test-skill", "agent:developer") in for_agent


def test_promoted_from_two_procedures(conn):
    _seed(conn)
    g = _build(conn)
    promoted = [(e.src, e.dst) for e in g.edges
                if e.type == "promoted_from" and e.src == "skill:graph-two-proc-skill"]
    dsts = {dst for _, dst in promoted}
    assert dsts == {"procedure:1", "procedure:99"}
    assert g.nodes["procedure:99"].attrs.get("missing") is True


def test_skill_enabled_attr_false_when_not_in_skills_yaml(conn, tmp_path):
    _seed(conn)
    g = _build(conn)
    assert g.nodes["skill:graph-test-skill"].attrs.get("enabled") is False

    enabled_yaml = tmp_path / "skills_enabled.yaml"
    enabled_yaml.write_text("enabled: [graph-test-skill]\n", encoding="utf-8")
    g2 = _build(conn, skills_config=enabled_yaml)
    assert g2.nodes["skill:graph-test-skill"].attrs.get("enabled") is True


def test_workflow_extracted_from_fact(conn):
    _seed(conn)
    g = _build(conn)
    extracted = [(e.src, e.dst) for e in g.edges if e.type == "extracted_from"]
    assert ("workflow:graph-test-workflow", "fact:k") in extracted
    assert ("workflow:no-such-file", "fact:k2") in extracted
    assert g.nodes["workflow:no-such-file"].attrs.get("missing") is True


def test_malformed_source_run_ids_is_empty(conn):
    _seed(conn)
    g = _build(conn)
    from_p2 = [e for e in g.edges if e.src == "procedure:2" and e.type == "learned_from"]
    assert from_p2 == []


def test_resolve_focus_order(conn):
    _seed(conn)
    g = _build(conn)
    assert resolve_capability_focus(conn, g, "graph-test-skill") == "skill:graph-test-skill"
    assert resolve_capability_focus(conn, g, "graph-test-workflow") == "workflow:graph-test-workflow"
    assert resolve_capability_focus(conn, g, "1") == "procedure:1"
    assert resolve_capability_focus(conn, g, "developer") == "agent:developer"
    assert resolve_capability_focus(conn, g, "zzz") is None
