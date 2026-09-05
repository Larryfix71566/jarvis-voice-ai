"""GL7 *execution* — runs, sessions, agents, tools, models, and the procedures runs taught."""
from __future__ import annotations

import json
import sqlite3

from jarvis.graphs import config as gcfg
from jarvis.graphs.model import Edge, Graph, Node, preview, typed_lookup, unique_prefix_match


def build_execution_graph(conn: sqlite3.Connection, *, since: str | None) -> Graph:
    g = Graph("execution")
    max_chars = gcfg.GRAPH_LABEL_MAX_CHARS
    limit = gcfg.GRAPH_EXECUTION_MAX_RUNS
    sql = ("SELECT run_id, session_id, agent, task, status, started_at, latency_ms, "
           "tools_ok, tools_failed, model FROM agent_runs")
    params: list[object] = []
    if since:                                            # None => no lower bound (parse_since contract)
        sql += " WHERE started_at >= ?"
        params.append(since)
    sql += " ORDER BY started_at DESC, run_id LIMIT ?"
    params.append(limit)
    runs = conn.execute(sql, params).fetchall()
    if len(runs) >= limit:
        g.truncated, g.truncated_reason = True, "run cap"

    for r in runs:
        rid = f"run:{r['run_id']}"
        g.add_node(Node(rid, "run", str(r["run_id"])[:8], {
            "agent": r["agent"], "status": r["status"], "started_at": r["started_at"],
            "latency_ms": r["latency_ms"], "tools_ok": r["tools_ok"], "tools_failed": r["tools_failed"],
            "task_preview": preview(r["task"], max_chars),
        }))
        if r["session_id"]:
            sid = f"session:{r['session_id']}"
            g.add_node(Node(sid, "session", preview(r["session_id"], max_chars), {}))
            g.add_edge(Edge(rid, sid, "in_session", {}))
        if r["agent"]:
            aid = f"agent:{r['agent']}"
            g.add_node(Node(aid, "agent", str(r["agent"]), {}))
            g.add_edge(Edge(rid, aid, "by_agent", {}))
        if r["model"]:
            mid = f"model:{r['model']}"
            g.add_node(Node(mid, "model", preview(r["model"], max_chars), {}))
            g.add_edge(Edge(rid, mid, "ran_on", {}))

    run_ids = [str(r["run_id"]) for r in runs]
    if run_ids:
        marks = ",".join("?" * len(run_ids))
        events = conn.execute(
            f"SELECT run_id, seq, type, tool, server, ok, latency_ms FROM agent_events "
            f"WHERE run_id IN ({marks}) AND type IN ('tool_result','mcp_call') AND tool IS NOT NULL "
            f"ORDER BY run_id, seq", tuple(run_ids),
        ).fetchall()
        by_run: dict[str, dict[str, list[sqlite3.Row]]] = {}
        for e in events:
            by_run.setdefault(str(e["run_id"]), {"mcp_call": [], "tool_result": []})[e["type"]].append(e)
        for run_id in run_ids:
            groups = by_run.get(run_id)
            if not groups:
                continue
            chosen = groups["mcp_call"] or groups["tool_result"]       # never both
            for e in chosen:
                tid = f"tool:{e['tool']}"
                g.add_node(Node(tid, "tool", str(e["tool"]), {}))
                ok = e["ok"]
                g.add_edge(Edge(f"run:{run_id}", tid, "called", {
                    "ok": None if ok is None else int(ok), "latency_ms": e["latency_ms"],
                    "seq": e["seq"], "server": e["server"], "event_type": e["type"],
                }))

    window = set(run_ids)
    for p in conn.execute("SELECT id, agent, status, label, source_run_ids FROM procedures ORDER BY id"):
        try:
            ids = json.loads(p["source_run_ids"] or "[]")
        except (TypeError, ValueError):
            ids = []
        hits = [str(x) for x in ids if str(x) in window] if isinstance(ids, list) else []
        if not hits:
            continue
        pid = f"procedure:{p['id']}"
        g.add_node(Node(pid, "procedure", preview(p["label"], max_chars),
                        {"agent": p["agent"], "status": p["status"], "label": preview(p["label"], max_chars)}))
        for rid in hits:
            g.add_edge(Edge(f"run:{rid}", pid, "taught", {}))
    return g


def resolve_execution_focus(conn: sqlite3.Connection, graph: Graph, focus: str) -> str | None:
    typed, hit = typed_lookup(graph, focus)
    if typed:
        return hit
    if f"run:{focus}" in graph.nodes:
        return f"run:{focus}"
    hit = unique_prefix_match(graph, f"run:{focus}")
    if hit is not None:
        return hit
    for c in (f"tool:{focus}", f"agent:{focus}", f"model:{focus}", f"session:{focus}"):
        if c in graph.nodes:
            return c
    return None
