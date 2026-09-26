"""Tests for jarvis.graphs.memory_graph (MORTIMER_GRAPH_LAYER_PLAN.md §5 step 3, §7)."""
import pytest

from jarvis.db import get_conn, run_migrations
from jarvis.graphs.memory_graph import build_memory_graph, resolve_memory_focus
from jarvis.graphs import config as gcfg


@pytest.fixture()
def conn(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "g.db"))
    c = get_conn(tmp_path / "g.db")
    run_migrations(c)
    yield c
    c.close()


def _insert_fact(conn, key, content, *, created_at="2026-01-01T00:00:00Z", updated_at=None,
                  tier="preference", archived_at=None, became=None, source_turn=None):
    conn.execute(
        "INSERT INTO memories(kind, key, content, created_at, updated_at, tier, archived_at, "
        "became, source_turn) VALUES ('fact', ?, ?, ?, ?, ?, ?, ?, ?)",
        (key, content, created_at, updated_at or created_at, tier, archived_at, became, source_turn),
    )
    conn.commit()


def test_prefix_nodes_and_child_of_edges(conn):
    _insert_fact(conn, "user.style.a", "a")
    _insert_fact(conn, "user.style.b", "b")
    _insert_fact(conn, "user.name", "Larry")
    g = build_memory_graph(conn)
    assert "prefix:user.style" in g.nodes
    assert "prefix:user" in g.nodes
    child_of = [(e.src, e.dst) for e in g.edges if e.type == "child_of"]
    assert ("fact:user.style.a", "prefix:user.style") in child_of
    assert child_of.count(("prefix:user.style", "prefix:user")) == 1
    assert ("fact:user.name", "prefix:user") in child_of
    assert "fact:user.style.b" in g.neighbors("fact:user.style.a", 2)


def test_became_merged_points_at_surviving_fact(conn):
    _insert_fact(conn, "k2", "surviving")
    _insert_fact(conn, "k1", "old", archived_at="2026-01-02T00:00:00Z", became="merged:k2")
    g = build_memory_graph(conn)
    hits = [e for e in g.edges if e.src == "fact:k1" and e.dst == "fact:k2"]
    assert len(hits) == 1
    assert hits[0].type == "became"
    assert hits[0].attrs["archived_at"] == "2026-01-02T00:00:00Z"


def test_became_workflow_points_at_workflow_node(conn):
    _insert_fact(conn, "k1", "old", archived_at="2026-01-02T00:00:00Z",
                 became="workflow:research-first")
    g = build_memory_graph(conn)
    assert g.nodes["workflow:research-first"].type == "workflow"
    hits = [e for e in g.edges if e.src == "fact:k1" and e.dst == "workflow:research-first"]
    assert hits and hits[0].type == "became"


def test_became_reason_points_at_archive_node(conn):
    _insert_fact(conn, "k1", "x", archived_at="t", became="aged-out")
    _insert_fact(conn, "k2", "x", archived_at="t", became="consolidated")
    _insert_fact(conn, "k3", "x", archived_at="t", became="config:jarvis_units")
    _insert_fact(conn, "k4", "x", archived_at="t", became="something-unknown:x")
    g = build_memory_graph(conn)
    assert "archive:aged-out" in g.nodes
    assert "archive:consolidated" in g.nodes
    assert "archive:config" in g.nodes
    assert "archive:something-unknown" in g.nodes


def test_became_merged_missing_target_uses_placeholder(conn):
    _insert_fact(conn, "k1", "old", archived_at="t", became="merged:gone")
    g = build_memory_graph(conn)
    assert "archive:merged-missing" in g.nodes
    hits = [e for e in g.edges if e.src == "fact:k1" and e.dst == "archive:merged-missing"]
    assert len(hits) == 1


def test_stated_in_and_restated_edges(conn):
    conn.execute(
        "INSERT INTO conversations (id, session_id, role, content, created_at) "
        "VALUES (7, 's1', 'user', 'hi', '2026-01-01T00:00:00Z')"
    )
    conn.commit()
    _insert_fact(conn, "user.name", "Larry", source_turn=7)
    conn.execute(
        "INSERT INTO memory_recall_events (session_id, source_turn, key, outcome, created_at) "
        "VALUES ('s1', 7, 'user.name', 'exact_update', '2026-01-01T00:00:00Z')"
    )
    conn.execute(
        "INSERT INTO memory_recall_events (session_id, source_turn, key, outcome, created_at) "
        "VALUES ('s1', 7, 'user.unknown', 'exact_update', '2026-01-01T00:00:00Z')"
    )
    conn.execute(
        "INSERT INTO memories(kind, key, content, created_at, updated_at, source_turn) "
        "VALUES ('fact', 'user.pruned', 'x', 't', 't', 99)"
    )
    conn.commit()
    g = build_memory_graph(conn)
    assert g.nodes["turn:7"].attrs["session_id"] == "s1"
    stated = [e for e in g.edges if e.type == "stated_in" and e.src == "fact:user.name"]
    assert stated and stated[0].dst == "turn:7"
    restated = [e for e in g.edges if e.type == "restated" and e.src == "fact:user.name"]
    assert restated and restated[0].attrs["outcome"] == "exact_update"
    # unknown-key recall event skipped: no edge from a nonexistent fact node
    assert all(e.src in g.nodes for e in g.edges)
    assert g.nodes["turn:99"].attrs.get("pruned") is True


def test_resolve_focus_order(conn):
    _insert_fact(conn, "user.name", "Larry")
    _insert_fact(conn, "user.style.a", "x")
    _insert_fact(conn, "user.preference.temperature_units", "Fahrenheit")
    g = build_memory_graph(conn)
    assert resolve_memory_focus(conn, g, "fact:user.name") == "fact:user.name"
    assert resolve_memory_focus(conn, g, "fact:nope") is None
    assert resolve_memory_focus(conn, g, "user.style") == "prefix:user.style"
    assert resolve_memory_focus(conn, g, "temperature") == "fact:user.preference.temperature_units"
    assert resolve_memory_focus(conn, g, "zzz-nothing") is None


def test_spoken_topics_resolve_to_memory_nodes(conn):
    """W11 (MORTIMER_VOICE_WORKFLOWS_PLAN.md Phase 4): the five logged
    misses of 2026-09-09..18, each against the shape of production memory
    that made it miss."""
    _insert_fact(conn, "user.interest.cooking", "Enjoys smoking brisket")
    _insert_fact(conn, "user.interest.cars", "Follows the Corvette ZR1")
    _insert_fact(conn, "user.preference.communication_style", "Terse, direct commands")
    _insert_fact(conn, "user.preference.display", "Results in the display window")
    _insert_fact(conn, "user.style.interruption", "Stop talking when interrupted")
    _insert_fact(conn, "user.style.commands.brief", "Prefers terse commands",
                 archived_at="2026-08-20T00:00:00Z", became="consolidated:user.preference.communication_style")
    _insert_fact(conn, "user.style.answer_length", "Short answers",
                 archived_at="2026-08-20T00:00:00Z", became="consolidated:user.preference.answer_style")
    _insert_fact(conn, "user.preference.answer_style", "Short answers",
                 archived_at="2026-09-01T00:00:00Z", became="aged-out")
    g = build_memory_graph(conn)
    r = lambda focus: resolve_memory_focus(conn, g, focus)
    assert r("interests") == "prefix:user.interest"                  # plural of a group
    assert r("my interests") == "prefix:user.interest"
    assert r("preferences") == "prefix:user.preference"
    # An archived match stands for the live fact it was folded into; one
    # whose successor also aged out (answer_style) is skipped.
    assert r("brief_answers") == "fact:user.preference.communication_style"
    # A dotted key that does not exist: look under its deepest prefix.
    assert r("user.style.brief_answers") == "fact:user.preference.communication_style"
    assert r("user.style.nothing_like_this") == "prefix:user.style"
    # Two topics at once: the prefix both sit under.
    assert r("user.preference,user.style") == "prefix:user"
    assert r("interests and preferences") == "prefix:user"
    assert r("zzz-nothing") is None


def test_row_guard_truncates_by_updated_at(conn, monkeypatch):
    monkeypatch.setattr(gcfg, "GRAPH_MEMORY_MAX_FACTS", 3)
    for i in range(5):
        _insert_fact(conn, f"user.f{i}", "x", updated_at=f"2026-01-0{i+1}T00:00:00Z")
    g = build_memory_graph(conn)
    assert g.truncated is True
    assert g.truncated_reason == "fact cap"
    kept = {nid for nid in g.nodes if nid.startswith("fact:")}
    assert kept == {"fact:user.f4", "fact:user.f3", "fact:user.f2"}
