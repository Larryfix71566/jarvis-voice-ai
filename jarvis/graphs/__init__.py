"""Derived, read-only relationship graphs over Mortimer's own stores
(MORTIMER_GRAPH_LAYER_PLAN.md). `build()` is the ONE entry point (§0.3); the
sidecar endpoints and the two MCP tools call it and nothing else computes an edge."""
from __future__ import annotations

import os
from collections import deque
from urllib.parse import urlencode

from jarvis.graphs.model import Edge, Graph, Node, federate, from_json  # noqa: F401 — re-exports

GRAPH_NAMES = ("memory", "capability", "execution", "deliberation")
RESERVED_GRAPHS = ("knowledge", "world")
ALL_NAMES = (*GRAPH_NAMES, "federated")

DISABLED_ERROR = "graphs are disabled (JARVIS_GRAPHS_ENABLED=false)"
EXECUTION_NEEDS_FOCUS = ("the execution graph needs a focus (a run id, tool, agent, model, "
                         "or session) — it is too large to draw whole")


def graphs_enabled() -> bool:
    """GL15 — the kill switch, read here and nowhere else."""
    return os.environ.get("JARVIS_GRAPHS_ENABLED", "").strip().lower() not in ("0", "false", "no", "off")


def _trim_to(graph: Graph, focus_id: str | None, n: int) -> set[str]:
    """Node cap. With a focus: BFS order from it (undirected, all edge types), first n.
    Without: (degree desc, id) so prefix/archive/session hubs survive and leaves are cut (Rev 2)."""
    adj = graph.adjacency()
    if focus_id is not None and focus_id in graph.nodes:
        seen, order, frontier = {focus_id}, [focus_id], deque([focus_id])
        while frontier and len(order) < n:
            nid = frontier.popleft()
            for nxt in sorted(adj.get(nid, ())):
                if nxt not in seen:
                    seen.add(nxt)
                    order.append(nxt)
                    frontier.append(nxt)
                    if len(order) >= n:
                        break
        return set(order[:n])
    ranked = sorted(graph.nodes, key=lambda nid: (-len(adj[nid]), nid))
    return set(ranked[:n])


def build(name: str, conn, *, focus: str = "", depth: int | None = None,
          edge_types: str = "", since: str | None = None) -> dict:
    """The ONE entry point. Returns GL4 JSON or {"ok": False, "error": ...}."""
    from jarvis.graphs import (capability_graph, config as gcfg, deliberation_graph,
                               execution_graph, memory_graph, render)
    from jarvis.runlog.store import parse_since

    if not graphs_enabled():
        return {"ok": False, "error": DISABLED_ERROR}
    if name in RESERVED_GRAPHS:
        return {"ok": False, "error": f"graph '{name}' is not built yet"}
    if name not in ALL_NAMES:
        return {"ok": False, "error": f"unknown graph '{name}'; one of memory, capability, "
                                      "execution, deliberation, federated"}
    depth = gcfg.GRAPH_DEFAULT_DEPTH if depth is None else max(1, min(gcfg.GRAPH_MAX_DEPTH, int(depth)))
    wanted = [t.strip() for t in (edge_types or "").split(",") if t.strip()] or None
    wanted_set = set(wanted) if wanted else None
    since_norm = parse_since(since or gcfg.GRAPH_DEFAULT_SINCE)      # None => no lower bound

    resolvers = {
        "memory": memory_graph.resolve_memory_focus,
        "capability": capability_graph.resolve_capability_focus,
        "execution": execution_graph.resolve_execution_focus,
        "deliberation": deliberation_graph.resolve_deliberation_focus,
    }
    builders = {
        "memory": lambda: memory_graph.build_memory_graph(conn),
        "capability": lambda: capability_graph.build_capability_graph(conn),
        "execution": lambda: execution_graph.build_execution_graph(conn, since=since_norm),
        "deliberation": lambda: deliberation_graph.build_deliberation_graph(conn, since=since_norm),
    }

    def _resolve_any(conn_, graph_, focus_):
        for n in GRAPH_NAMES:                     # first graph whose resolver answers wins
            hit = resolvers[n](conn_, graph_, focus_)
            if hit is not None:
                return hit
        return None

    if name == "federated":
        graph = federate([builders[n]() for n in GRAPH_NAMES])
        resolver = _resolve_any
    else:
        graph = builders[name]()
        resolver = resolvers[name]

    focus_id: str | None = None
    if focus.strip():
        focus_id = resolver(conn, graph, focus.strip())
        if focus_id is None:
            if name == "memory":
                # Status spec T4.6: an unknown topic in the memory graph shows
                # the overview (flagged), never a dead end. Other graphs keep
                # the error.
                result = build(name, conn, focus="", depth=depth,
                               edge_types=edge_types, since=since)
                if result.get("ok"):
                    result["focus_miss"] = focus.strip()
                return result
            return {"ok": False, "error": f"no node matches '{focus.strip()}' in the {name} graph"}
    elif name == "execution":
        return {"ok": False, "error": EXECUTION_NEEDS_FOCUS}

    if focus_id is not None:
        keep = graph.neighbors(focus_id, depth, wanted_set)
        graph = graph.subgraph(keep, wanted_set)
    elif wanted_set:
        graph = graph.subgraph(set(graph.nodes), wanted_set)

    if len(graph.nodes) > gcfg.GRAPH_MAX_NODES:
        keep = _trim_to(graph, focus_id, gcfg.GRAPH_MAX_NODES)
        graph = graph.subgraph(keep, wanted_set)
        graph.truncated, graph.truncated_reason = True, f"node cap {gcfg.GRAPH_MAX_NODES}"

    return graph.to_json(focus=focus_id, depth=depth,
                         edge_types=wanted or render.all_edge_types(name),
                         legend=render.legend_for(name))


def summary_line(result: dict) -> str:
    """§5 step 8 — the spoken sentence, deterministic templates only."""
    nodes = result.get("nodes") or []
    edges = result.get("edges") or []
    depth = result.get("depth")
    focus = result.get("focus")
    label = "the whole graph"
    if focus:
        for n in nodes:
            if n["id"] == focus:
                label = n["label"]
                break
    by_type: dict[str, int] = {}
    for n in nodes:
        by_type[n["type"]] = by_type.get(n["type"], 0) + 1
    name = result.get("graph")
    if name == "memory":
        archived = sum(1 for n in nodes if n["attrs"].get("archived") is True)
        s = (f"{by_type.get('fact', 0)} memories and {by_type.get('prefix', 0)} key groups "
             f"within {depth} of {label}; {archived} of them archived.")
    elif name == "capability":
        s = (f"{by_type.get('skill', 0)} skills, {by_type.get('workflow', 0)} workflows and "
             f"{by_type.get('procedure', 0)} procedures within {depth} of {label}.")
    elif name == "execution":
        failed = sum(1 for e in edges if e["type"] == "called" and e["attrs"].get("ok") == 0)
        s = (f"{by_type.get('run', 0)} runs, {by_type.get('tool', 0)} tools and "
             f"{by_type.get('model', 0)} models within {depth} of {label}; {failed} tool calls failed.")
    elif name == "deliberation":
        live = [e for e in edges if e["type"] == "scored" and not e["attrs"].get("superseded")]
        judges = len({e["from"] for e in live})
        abst = sum(1 for e in live if e["attrs"].get("score") is None)
        s = (f"{by_type.get('round', 0)} rounds, {by_type.get('proposal', 0)} proposals and "
             f"{judges} judges within {depth} of {label}; {abst} abstentions.")
    else:
        s = f"{len(nodes)} nodes and {len(edges)} edges within {depth} of {label}."
    if result.get("truncated"):
        s += f" Truncated ({result.get('truncated_reason') or 'guard'})."
    return s


def tool_result(result: dict, *, since: str | None = None) -> dict:
    """GL12 — the dict both MCP tools return for an ok graph (never nodes/edges)."""
    admin_url = os.environ.get("JARVIS_ADMIN_URL") or "http://127.0.0.1:7861"
    query = {"focus": result.get("focus") or "", "depth": result["depth"],
             "edge_types": ",".join(result["edge_types"])}
    if since is not None:
        query["since"] = since
    out = {
        "ok": True, "graph": result["graph"], "focus": result.get("focus"),
        "depth": result["depth"], "node_count": result["node_count"],
        "edge_count": result["edge_count"], "truncated": bool(result.get("truncated")),
        "truncated_reason": str(result.get("truncated_reason") or "") if result.get("truncated") else "",
        "image_url": f"{admin_url}/api/graph/{result['graph']}/image.png?{urlencode(query)}",
        "summary": summary_line(result),
    }
    if result.get("focus_miss"):
        out["focus_miss"] = result["focus_miss"]  # T4.6: reaches the tool and the display
    return out
