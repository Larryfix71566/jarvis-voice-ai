"""The graph shape every builder fills and every consumer reads (MORTIMER_GRAPH_LAYER_PLAN.md GL3/GL4/GL8).

Pure data + pure functions. Imports nothing from the rest of the package."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

Attrs = dict[str, "str | int | float | bool | None"]

#: GL3 — the `<type>` half of every node id, reserved types included.
KNOWN_TYPES = frozenset({
    "fact", "prefix", "turn", "archive", "run", "session", "agent", "tool", "model",
    "procedure", "skill", "workflow", "round", "proposal", "profile",
    "doc", "note", "entity",
})


@dataclass(frozen=True)
class Node:
    id: str          # "<type>:<key>"
    type: str
    label: str
    attrs: Attrs = field(default_factory=dict)


@dataclass(frozen=True)
class Edge:
    src: str         # node id
    dst: str         # node id
    type: str
    attrs: Attrs = field(default_factory=dict)


@dataclass
class Graph:
    name: str
    nodes: dict[str, Node] = field(default_factory=dict)
    edges: list[Edge] = field(default_factory=list)
    truncated: bool = False
    truncated_reason: str = ""

    def add_node(self, node: Node) -> None:
        """First writer wins; later attrs fill only missing keys (GL8)."""
        cur = self.nodes.get(node.id)
        if cur is None:
            self.nodes[node.id] = node
        else:
            merged = {**node.attrs, **cur.attrs}
            self.nodes[node.id] = Node(cur.id, cur.type, cur.label, merged)

    def add_edge(self, edge: Edge) -> None:
        """Both endpoints must exist; a dangling edge is a bug in the builder (§0.13)."""
        if edge.src not in self.nodes or edge.dst not in self.nodes:
            raise KeyError(f"dangling edge {edge.src}->{edge.dst}")
        self.edges.append(edge)

    def adjacency(self, edge_types: set[str] | None = None) -> dict[str, set[str]]:
        adj: dict[str, set[str]] = {nid: set() for nid in self.nodes}
        for e in self.edges:
            if edge_types is not None and e.type not in edge_types:
                continue
            adj[e.src].add(e.dst)
            adj[e.dst].add(e.src)          # undirected (GL5)
        return adj

    def neighbors(self, node_id: str, depth: int = 1,
                  edge_types: set[str] | None = None) -> set[str]:
        """Ids within `depth` undirected hops of node_id, node_id included."""
        adj = self.adjacency(edge_types)
        seen, frontier = {node_id}, deque([(node_id, 0)])
        while frontier:
            nid, d = frontier.popleft()
            if d == depth:
                continue
            for nxt in sorted(adj.get(nid, ())):
                if nxt not in seen:
                    seen.add(nxt)
                    frontier.append((nxt, d + 1))
        return seen

    def subgraph(self, keep: set[str], edge_types: set[str] | None = None) -> "Graph":
        g = Graph(self.name, truncated=self.truncated, truncated_reason=self.truncated_reason)
        for nid in sorted(keep):
            if nid in self.nodes:
                g.nodes[nid] = self.nodes[nid]
        for e in self.edges:
            if e.src in g.nodes and e.dst in g.nodes and (edge_types is None or e.type in edge_types):
                g.edges.append(e)
        return g

    def to_json(self, *, focus: str | None, depth: int, edge_types: list[str], legend: dict) -> dict:
        nodes = [{"id": n.id, "type": n.type, "label": n.label, "attrs": dict(n.attrs)}
                 for n in sorted(self.nodes.values(), key=lambda n: n.id)]
        edges = [{"from": e.src, "to": e.dst, "type": e.type, "attrs": dict(e.attrs)}
                 for e in self.edges]
        if self.truncated and focus in self.nodes:
            for n in nodes:
                if n["id"] == focus:
                    n["attrs"]["truncated_reason"] = self.truncated_reason
        return {"ok": True, "graph": self.name, "focus": focus, "depth": depth,
                "edge_types": list(edge_types), "node_count": len(nodes), "edge_count": len(edges),
                "truncated": self.truncated, "truncated_reason": self.truncated_reason,
                "nodes": nodes, "edges": edges, "legend": legend}


def from_json(result: dict) -> Graph:
    """Inverse of Graph.to_json (used by the image endpoint, §5 step 10)."""
    g = Graph(str(result["graph"]), truncated=bool(result.get("truncated")),
              truncated_reason=str(result.get("truncated_reason") or ""))
    for n in result["nodes"]:
        attrs = dict(n.get("attrs") or {})
        if g.truncated and "truncated_reason" in attrs and not g.truncated_reason:
            g.truncated_reason = str(attrs["truncated_reason"])
        g.nodes[n["id"]] = Node(n["id"], n["type"], n["label"], attrs)
    for e in result["edges"]:
        g.edges.append(Edge(e["from"], e["to"], e["type"], dict(e.get("attrs") or {})))
    return g


def federate(graphs: list[Graph]) -> Graph:
    """GL8 — union plus nothing."""
    out = Graph("federated")
    seen: set[tuple] = set()
    for g in graphs:
        for n in g.nodes.values():
            out.add_node(n)
        out.truncated = out.truncated or g.truncated
        if g.truncated and not out.truncated_reason:
            out.truncated_reason = g.truncated_reason
    for g in graphs:
        for e in g.edges:
            key = (e.src, e.dst, e.type, frozenset(e.attrs.items()))
            if key in seen:
                continue
            seen.add(key)
            out.add_edge(e)
    return out


def typed_lookup(graph: Graph, focus: str) -> tuple[bool, str | None]:
    """GL6 step 1. (True, id-or-None) when focus is '<known type>:<rest>'; (False, None) otherwise."""
    head, sep, _ = focus.partition(":")
    if sep and head in KNOWN_TYPES:
        return True, (focus if focus in graph.nodes else None)
    return False, None


def unique_prefix_match(graph: Graph, prefix: str) -> str | None:
    """The one id in graph.nodes starting with `prefix`, else None (0 or >1 matches)."""
    hits = [nid for nid in graph.nodes if nid.startswith(prefix)]
    return hits[0] if len(hits) == 1 else None


def preview(text: object, max_chars: int) -> str:
    """Label/preview truncation with a trailing ellipsis (GL4 label rule)."""
    s = "" if text is None else str(text)
    return s if len(s) <= max_chars else s[: max_chars - 1] + "…"
