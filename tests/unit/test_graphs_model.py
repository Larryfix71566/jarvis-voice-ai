"""Tests for jarvis.graphs.model (MORTIMER_GRAPH_LAYER_PLAN.md §5 step 1, §7).

Build/dispatcher tests below need every builder module plus render.py, so
they were written once step 7 landed rather than after step 1 (build()
unconditionally imports capability_graph/execution_graph/deliberation_graph/
render at call time, regardless of which graph name is requested — an
implementer note, not a code change).
"""
import pytest

from jarvis.db import get_conn, run_migrations
from jarvis.graphs import ALL_NAMES, EXECUTION_NEEDS_FOCUS, build, summary_line, tool_result
from jarvis.graphs import config as gcfg
from jarvis.graphs.model import (
    Edge,
    Graph,
    Node,
    federate,
    from_json,
    typed_lookup,
    unique_prefix_match,
)


def test_add_node_first_writer_wins_attrs_fill_missing():
    g = Graph("memory")
    g.add_node(Node("fact:a", "fact", "a", {"tier": "x"}))
    g.add_node(Node("fact:a", "fact", "A", {"tier": "y", "z": 1}))
    n = g.nodes["fact:a"]
    assert n.label == "a"
    assert n.attrs == {"tier": "x", "z": 1}


def test_add_edge_rejects_dangling():
    g = Graph("memory")
    g.add_node(Node("fact:a", "fact", "a"))
    with pytest.raises(KeyError):
        g.add_edge(Edge("fact:a", "fact:missing", "child_of"))


def test_neighbors_depth_is_undirected_hops():
    g = Graph("memory")
    for nid in ("a", "b", "c", "d"):
        g.add_node(Node(nid, "fact", nid))
    g.add_edge(Edge("a", "b", "x"))
    g.add_edge(Edge("b", "c", "x"))
    g.add_edge(Edge("c", "d", "x"))
    assert g.neighbors("a", 2) == {"a", "b", "c"}
    assert g.neighbors("d", 1) == {"d", "c"}


def test_neighbors_respects_edge_types():
    g = Graph("memory")
    for nid in ("a", "b", "c"):
        g.add_node(Node(nid, "fact", nid))
    g.add_edge(Edge("a", "b", "x"))
    g.add_edge(Edge("b", "c", "y"))
    assert g.neighbors("a", 2, {"x"}) == {"a", "b"}


def test_subgraph_keeps_only_edges_with_both_endpoints():
    g = Graph("memory")
    for nid in ("a", "b", "c"):
        g.add_node(Node(nid, "fact", nid))
    g.add_edge(Edge("a", "b", "x"))
    g.add_edge(Edge("b", "c", "x"))
    sub = g.subgraph({"a", "b"})
    assert set(sub.nodes) == {"a", "b"}
    assert len(sub.edges) == 1
    assert sub.edges[0].src == "a" and sub.edges[0].dst == "b"


def test_to_json_from_json_roundtrip():
    g = Graph("memory")
    g.add_node(Node("fact:a", "fact", "a", {"tier": "x"}))
    g.add_node(Node("fact:b", "fact", "b"))
    g.add_edge(Edge("fact:a", "fact:b", "child_of"))
    result = g.to_json(focus=None, depth=1, edge_types=["child_of"], legend={})
    back = from_json(result)
    assert set(back.nodes) == set(g.nodes)
    assert len(back.edges) == len(g.edges)
    assert back.truncated is False

    gt = Graph("memory", truncated=True, truncated_reason="node cap 5")
    gt.add_node(Node("fact:a", "fact", "a"))
    result_t = gt.to_json(focus="fact:a", depth=1, edge_types=[], legend={})
    back_t = from_json(result_t)
    assert back_t.truncated_reason == gt.truncated_reason


def test_federate_unions_and_dedups_edges():
    g1 = Graph("memory")
    g1.add_node(Node("fact:a", "fact", "a", {"tier": "x"}))
    g1.add_node(Node("fact:b", "fact", "b"))
    g1.add_edge(Edge("fact:a", "fact:b", "child_of"))

    g2 = Graph("capability")
    g2.add_node(Node("fact:a", "fact", "a", {"tier": "y", "extra": 1}))
    g2.add_node(Node("fact:b", "fact", "b"))
    g2.add_edge(Edge("fact:a", "fact:b", "child_of"))
    g2.add_edge(Edge("fact:a", "fact:b", "child_of", {"note": "diff"}))

    out = federate([g1, g2])
    assert out.nodes["fact:a"].attrs == {"tier": "x", "extra": 1}
    child_of_edges = [e for e in out.edges if e.type == "child_of"]
    assert len(child_of_edges) == 2  # same attrs dedup'd once, differing attrs kept


def test_typed_lookup_and_unique_prefix_match():
    g = Graph("memory")
    g.add_node(Node("fact:a", "fact", "a"))
    assert typed_lookup(g, "fact:a") == (True, "fact:a")
    assert typed_lookup(g, "fact:zz") == (True, None)
    assert typed_lookup(g, "zz") == (False, None)

    g.add_node(Node("fact:ab", "fact", "ab"))
    g.add_node(Node("prefix:x", "prefix", "x"))
    assert unique_prefix_match(g, "prefix:") == "prefix:x"
    assert unique_prefix_match(g, "fact:") is None
    assert unique_prefix_match(g, "nope:") is None


@pytest.fixture()
def conn(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "g.db"))
    c = get_conn(tmp_path / "g.db")
    run_migrations(c)
    yield c
    c.close()


def _insert_fact(conn, key, content="x", updated_at="t"):
    conn.execute(
        "INSERT INTO memories(kind, key, content, created_at, updated_at) VALUES ('fact', ?, ?, ?, ?)",
        (key, content, updated_at, updated_at),
    )


def test_build_rejects_reserved_and_unknown(conn):
    r1 = build("knowledge", conn)
    assert r1["ok"] is False
    assert "not built yet" in r1["error"]
    r2 = build("bogus", conn)
    assert r2["ok"] is False
    assert "unknown graph" in r2["error"]


def test_build_execution_without_focus_errors(conn):
    r = build("execution", conn)
    assert r["ok"] is False
    assert r["error"] == EXECUTION_NEEDS_FOCUS


def test_build_disabled_by_env(conn, monkeypatch):
    monkeypatch.setenv("JARVIS_GRAPHS_ENABLED", "false")
    for name in ALL_NAMES:
        r = build(name, conn)
        assert r["ok"] is False
        assert "JARVIS_GRAPHS_ENABLED" in r["error"]


def test_build_caps_nodes_and_flags_truncated(conn, monkeypatch):
    monkeypatch.setattr(gcfg, "GRAPH_MAX_NODES", 20)
    for i in range(30):
        _insert_fact(conn, f"user.style.f{i:02d}")
    conn.commit()
    r = build("memory", conn, focus="prefix:user.style", depth=1)
    assert r["ok"] is True
    assert r["node_count"] == 20
    assert r["truncated"] is True
    focus_node = next(n for n in r["nodes"] if n["id"] == "prefix:user.style")
    assert focus_node["attrs"]["truncated_reason"] == "node cap 20"


def test_trim_without_focus_keeps_high_degree_nodes(conn, monkeypatch):
    # implementer: the §7 bullet's literal fixture (30 facts under one
    # second-level prefix) ties prefix:user's degree with every leaf fact
    # at 1, so it loses the (degree desc, id) tiebreak to "fact:*" ids
    # purely alphabetically -- that tests the tiebreak, not the rule the
    # test is named for. Adding two more facts directly under "user" gives
    # prefix:user real structural degree (3) so the intended behaviour
    # (hubs survive, leaves get cut) is what's actually being asserted.
    monkeypatch.setattr(gcfg, "GRAPH_MAX_NODES", 5)
    for i in range(30):
        _insert_fact(conn, f"user.style.f{i:02d}")
    _insert_fact(conn, "user.name")
    _insert_fact(conn, "user.age")
    conn.commit()
    r = build("memory", conn)
    ids = {n["id"] for n in r["nodes"]}
    assert "prefix:user.style" in ids
    assert "prefix:user" in ids
    assert r["truncated"] is True


def test_summary_line_templates():
    mem = {
        "graph": "memory", "focus": "fact:a", "depth": 2,
        "nodes": [
            {"id": "fact:a", "type": "fact", "label": "a", "attrs": {"archived": False}},
            {"id": "fact:b", "type": "fact", "label": "b", "attrs": {"archived": True}},
            {"id": "prefix:x", "type": "prefix", "label": "x", "attrs": {}},
        ],
        "edges": [], "truncated": False, "truncated_reason": "",
    }
    assert summary_line(mem) == "2 memories and 1 key groups within 2 of a; 1 of them archived."

    cap = {
        "graph": "capability", "focus": None, "depth": 1,
        "nodes": [
            {"id": "skill:s1", "type": "skill", "label": "s1", "attrs": {}},
            {"id": "workflow:w1", "type": "workflow", "label": "w1", "attrs": {}},
            {"id": "procedure:1", "type": "procedure", "label": "1", "attrs": {}},
        ],
        "edges": [], "truncated": False, "truncated_reason": "",
    }
    assert summary_line(cap) == "1 skills, 1 workflows and 1 procedures within 1 of the whole graph."

    exe = {
        "graph": "execution", "focus": "run:r1", "depth": 1,
        "nodes": [
            {"id": "run:r1", "type": "run", "label": "r1", "attrs": {}},
            {"id": "tool:t1", "type": "tool", "label": "t1", "attrs": {}},
            {"id": "model:m1", "type": "model", "label": "m1", "attrs": {}},
        ],
        "edges": [{"from": "run:r1", "to": "tool:t1", "type": "called", "attrs": {"ok": 0}}],
        "truncated": False, "truncated_reason": "",
    }
    assert summary_line(exe) == "1 runs, 1 tools and 1 models within 1 of r1; 1 tool calls failed."

    delib = {
        "graph": "deliberation", "focus": None, "depth": 2,
        "nodes": [
            {"id": "round:rd", "type": "round", "label": "rd", "attrs": {}},
            {"id": "proposal:p", "type": "proposal", "label": "p", "attrs": {}},
        ],
        "edges": [
            {"from": "profile:j1", "to": "proposal:p", "type": "scored",
             "attrs": {"score": 5.0, "superseded": False}},
            {"from": "profile:j2", "to": "proposal:p", "type": "scored",
             "attrs": {"score": None, "superseded": False}},
            {"from": "profile:j1", "to": "proposal:p", "type": "scored",
             "attrs": {"score": None, "superseded": True}},
        ],
        "truncated": False, "truncated_reason": "",
    }
    # the superseded edge is excluded from both the judge count and the abstention count
    assert summary_line(delib) == "1 rounds, 1 proposals and 2 judges within 2 of the whole graph; 1 abstentions."

    fed = {
        "graph": "federated", "focus": None, "depth": 1,
        "nodes": [{"id": "a", "type": "x", "label": "a", "attrs": {}}],
        "edges": [], "truncated": True, "truncated_reason": "node cap 5",
    }
    assert summary_line(fed) == "1 nodes and 0 edges within 1 of the whole graph. Truncated (node cap 5)."


def test_tool_result_shape_and_url(monkeypatch):
    result = {
        "graph": "memory", "focus": "fact:a", "depth": 2,
        "edge_types": ["child_of"], "node_count": 3, "edge_count": 1,
        "truncated": False, "truncated_reason": "",
        "nodes": [{"id": "fact:a", "type": "fact", "label": "a", "attrs": {}}],
        "edges": [],
    }
    out = tool_result(result, since="7d")
    assert set(out) == {"ok", "graph", "focus", "depth", "node_count", "edge_count",
                        "truncated", "truncated_reason", "image_url", "summary"}
    assert "nodes" not in out
    assert out["image_url"].startswith("http://127.0.0.1:7861/api/graph/memory/image.png?")
    assert "focus=" in out["image_url"]
    assert "since=7d" in out["image_url"]

    monkeypatch.setenv("JARVIS_ADMIN_URL", "http://x:1")
    out2 = tool_result(result, since="7d")
    assert out2["image_url"].startswith("http://x:1")


def test_memory_graph_unmatched_focus_falls_back_to_overview(conn):
    """Status spec T4.6: the unfocused memory graph, ok, flagged focus_miss."""
    _insert_fact(conn, "user.style.a")
    _insert_fact(conn, "user.name", "Larry")
    conn.commit()
    overview = build("memory", conn)
    r = build("memory", conn, focus="  zzz-nothing  ")
    assert r["ok"] is True
    assert r["focus_miss"] == "zzz-nothing"
    assert r["focus"] is None
    assert {n["id"] for n in r["nodes"]} == {n["id"] for n in overview["nodes"]}
    out = tool_result(r)
    assert out["focus_miss"] == "zzz-nothing"
    assert "focus_miss" not in tool_result(overview)


@pytest.mark.parametrize("name", ["execution", "capability", "deliberation"])
def test_execution_graph_still_errors_on_unmatched_focus(conn, name):
    r = build(name, conn, focus="nonexistent-zzz")
    assert r["ok"] is False
    assert r["error"] == f"no node matches 'nonexistent-zzz' in the {name} graph"
    assert "focus_miss" not in r
