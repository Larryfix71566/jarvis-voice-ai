"""GL7 *memory* — the only place memory nodes and edges are derived."""
from __future__ import annotations

import re
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


# W11 (MORTIMER_VOICE_WORKFLOWS_PLAN.md Phase 4): a spoken topic is not a
# node id. The logged misses (2026-09-09 to 09-18): "interests",
# "brief_answers", "user.style.brief_answers" (no such key) and
# "user.preference,user.style" (two topics at once).
_TOPIC_STOPWORDS = frozenset({
    "a", "about", "all", "an", "and", "fact", "facts", "for", "graph", "i", "in", "know",
    "me", "memories", "memory", "my", "of", "on", "remember", "show", "the", "to", "what", "you",
})
_TOPIC_SPLIT = re.compile(r"\s*(?:,|;|&|\band\b)\s*", re.I)


def _singular(word: str) -> str:
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def _topic_words(text: str) -> list[str]:
    return [_singular(w) for w in re.split(r"[^a-z0-9]+", text.lower()) if w and w not in _TOPIC_STOPWORDS]


def _last_segment(node_id: str) -> str:
    return _singular(node_id.split(":", 1)[1].rsplit(".", 1)[-1].lower())


def _common_prefix(graph: Graph, node_ids: list[str]) -> str | None:
    """The deepest prefix node every one of `node_ids` sits under."""
    split = [nid.split(":", 1)[1].split(".") for nid in node_ids]
    common: list[str] = []
    for segments in zip(*split):
        if len(set(segments)) != 1:
            break
        common.append(segments[0])
    while common:
        cand = "prefix:" + ".".join(common)
        if cand in graph.nodes:
            return cand
        common.pop()
    return None


def _group_named(graph: Graph, words: list[str]) -> str | None:
    """A prefix node whose last segment IS the topic ("interests" ->
    prefix:user.interest); the shallowest wins, then alphabetical."""
    wanted = "_".join(words)
    hits = sorted((nid for nid in graph.nodes if nid.startswith("prefix:") and _last_segment(nid) == wanted),
                  key=lambda nid: (nid.count("."), nid))
    return hits[0] if hits else None


def _successor(became: str | None) -> str | None:
    """The live key an archived fact was folded into, when its `became`
    names one (merged:/consolidated:/reviewed:kept:)."""
    head, _, tail = (became or "").partition(":")
    if head in ("merged", "consolidated") and tail:
        return tail
    if head == "reviewed" and tail.startswith("kept:"):
        return tail[len("kept:"):]
    return None


def _fact_by_key_words(conn: sqlite3.Connection, graph: Graph, words: list[str], scope: str = "") -> str | None:
    """The live fact whose key names the most topic words (all of them
    beats some); a live match beats an archived one, then the shorter key
    wins. An archived fact stands for the live fact it was folded into
    ("brief" -> user.style.commands.brief, consolidated into
    user.preference.communication_style); one with no live successor is
    skipped. `scope` limits the search to keys under one prefix."""
    rows = conn.execute("SELECT key, archived_at, became FROM memories WHERE kind = 'fact'").fetchall()
    archived = {key: became for key, archived_at, became in rows if archived_at is not None}
    live = {key for key, archived_at, _ in rows if archived_at is None}

    def live_successor(key: str) -> str | None:
        for _ in range(5):                 # a fold chain, never a loop
            if key in live:
                return key
            key = _successor(archived.get(key))
            if key is None:
                return None
        return None

    best: tuple[int, int, int, str, str] | None = None
    for key, archived_at, _became in rows:
        if scope and not key.startswith(scope + "."):
            continue
        key_words = {_singular(w) for w in re.split(r"[^a-z0-9]+", key[len(scope):].lower()) if w}
        score = sum(w in key_words for w in words)
        if not score:
            continue
        target = live_successor(key)
        if target is None or f"fact:{target}" not in graph.nodes:
            continue
        rank = (-score, 0 if archived_at is None else 1, len(key), key, target)
        if best is None or rank < best:
            best = rank
    return f"fact:{best[4]}" if best else None


def resolve_memory_focus(conn: sqlite3.Connection, graph: Graph, focus: str) -> str | None:
    typed, hit = typed_lookup(graph, focus)
    if typed:
        return hit
    for cand in (f"fact:{focus}", f"prefix:{focus}"):
        if cand in graph.nodes:
            return cand
    parts = [part for part in _TOPIC_SPLIT.split(focus) if part.strip()]
    if len(parts) > 1:
        hits = [h for h in (resolve_memory_focus(conn, graph, part.strip()) for part in parts) if h]
        if not hits:
            return None
        return hits[0] if len(set(hits)) == 1 else (_common_prefix(graph, hits) or hits[0])
    if "." in focus:
        # A dotted name that isn't a key ("user.style.brief_answers"): look
        # under its deepest existing prefix for the rest, else show that prefix.
        segments = focus.split(".")
        for cut in range(len(segments) - 1, 0, -1):
            scope = ".".join(segments[:cut])
            if f"prefix:{scope}" in graph.nodes:
                rest = _topic_words(" ".join(segments[cut:]))
                return (_fact_by_key_words(conn, graph, rest, scope) if rest else None) or f"prefix:{scope}"
    words = _topic_words(focus)
    if not words:
        return None
    hit = _group_named(graph, words) or _fact_by_key_words(conn, graph, words)
    if hit:
        return hit
    from jarvis.memory import search_facts
    found = search_facts(conn, " ".join(words), 1)
    if found and f"fact:{found[0]['key']}" in graph.nodes:
        return f"fact:{found[0]['key']}"
    return None
