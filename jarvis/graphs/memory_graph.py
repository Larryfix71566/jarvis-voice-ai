"""GL7 *memory* — the only place memory nodes and edges are derived."""
from __future__ import annotations

import sqlite3

from jarvis.graphs import config as gcfg
from jarvis.graphs.model import Edge, Graph, Node, preview, typed_lookup


def became_target(value: str) -> tuple[str, str, str]:
    """(node_id, node_type, label) for an archived fact's `became` value."""
    head, _, tail = value.partition(":")
    if head == "merged" and tail:
        return f"fact:{tail}", "fact", tail
    if head == "workflow" and tail:
        return f"workflow:{tail}", "workflow", tail
    if head == "config":
        return "archive:config", "archive", "config"
    return f"archive:{head}", "archive", head


def _add_prefix_chain(g: Graph, key: str, seen: set[tuple[str, str]]) -> None:
    """For key a.b.c: nodes prefix:a and prefix:a.b; edge prefix:a.b -> prefix:a (once)."""
    parts = key.split(".")
    prefixes = [".".join(parts[:i]) for i in range(1, len(parts))]     # ["a", "a.b"]
    for p in prefixes:
        g.add_node(Node(f"prefix:{p}", "prefix", p, {}))
    for child, parent in zip(prefixes[1:], prefixes[:-1]):
        pair = (f"prefix:{child}", f"prefix:{parent}")
        if pair not in seen:
            seen.add(pair)
            g.add_edge(Edge(pair[0], pair[1], "child_of", {}))


def build_memory_graph(conn: sqlite3.Connection) -> Graph:
    g = Graph("memory")
    rows = conn.execute(
        "SELECT key, content, COALESCE(tier,'project') AS tier, archived_at, became, "
        "updated_at, recurrence_count, provenance, source_turn "
        "FROM memories WHERE kind='fact' AND key IS NOT NULL "
        "ORDER BY updated_at DESC, key"
    ).fetchall()
    cap = gcfg.GRAPH_MEMORY_MAX_FACTS
    if len(rows) > cap:
        rows = rows[:cap]                                  # newest by updated_at
        g.truncated, g.truncated_reason = True, "fact cap"
    facts: dict[str, sqlite3.Row] = {}
    for r in rows:
        facts.setdefault(r["key"], r)                      # keys are unique; belt-and-braces

    for key, r in facts.items():
        g.add_node(Node(f"fact:{key}", "fact", preview(key, gcfg.GRAPH_LABEL_MAX_CHARS), {
            "tier": r["tier"], "archived": r["archived_at"] is not None,
            "updated_at": r["updated_at"], "recurrence_count": r["recurrence_count"],
            "provenance": r["provenance"],
            "content_preview": preview(r["content"], gcfg.GRAPH_LABEL_MAX_CHARS),
        }))

    seen_prefix_edges: set[tuple[str, str]] = set()
    for key in facts:
        if "." not in key:
            continue
        _add_prefix_chain(g, key, seen_prefix_edges)
        g.add_edge(Edge(f"fact:{key}", f"prefix:{key.rsplit('.', 1)[0]}", "child_of", {}))

    for key, r in facts.items():
        if not r["became"]:
            continue
        target_id, target_type, label = became_target(str(r["became"]))
        if target_type == "fact" and target_id not in g.nodes:
            target_id, target_type, label = "archive:merged-missing", "archive", "merged-missing"
        if target_id not in g.nodes:
            g.add_node(Node(target_id, target_type, label, {}))
        g.add_edge(Edge(f"fact:{key}", target_id, "became", {"archived_at": r["archived_at"]}))

    recall = conn.execute(
        "SELECT key, source_turn, outcome FROM memory_recall_events WHERE source_turn IS NOT NULL"
    ).fetchall()
    recall = [r for r in recall if f"fact:{r['key']}" in g.nodes]        # unknown key -> skipped
    turn_ids = {int(r["source_turn"]) for r in facts.values() if r["source_turn"] is not None}
    turn_ids |= {int(r["source_turn"]) for r in recall}
    turn_rows: dict[int, sqlite3.Row] = {}
    if turn_ids:
        marks = ",".join("?" * len(turn_ids))
        for t in conn.execute(
            f"SELECT id, session_id, role, created_at FROM conversations WHERE id IN ({marks})",
            tuple(sorted(turn_ids)),
        ):
            turn_rows[int(t["id"])] = t
    for tid in sorted(turn_ids):
        t = turn_rows.get(tid)
        attrs = ({"session_id": t["session_id"], "created_at": t["created_at"], "role": t["role"]}
                 if t is not None else {"pruned": True})
        g.add_node(Node(f"turn:{tid}", "turn", str(tid), attrs))
    for key, r in facts.items():
        if r["source_turn"] is not None:
            g.add_edge(Edge(f"fact:{key}", f"turn:{int(r['source_turn'])}", "stated_in", {}))
    for r in recall:
        g.add_edge(Edge(f"fact:{r['key']}", f"turn:{int(r['source_turn'])}", "restated",
                        {"outcome": r["outcome"]}))
    return g


def resolve_memory_focus(conn: sqlite3.Connection, graph: Graph, focus: str) -> str | None:
    typed, hit = typed_lookup(graph, focus)
    if typed:
        return hit
    for cand in (f"fact:{focus}", f"prefix:{focus}"):
        if cand in graph.nodes:
            return cand
    from jarvis.memory import search_facts
    hits = search_facts(conn, focus, 1)
    if hits and f"fact:{hits[0]['key']}" in graph.nodes:
        return f"fact:{hits[0]['key']}"
    return None
