"""GL7 *deliberation* — council rounds, proposals, judges, and the runs that convened them."""
from __future__ import annotations

import sqlite3
from collections import Counter

from jarvis.graphs import config as gcfg
from jarvis.graphs.model import Edge, Graph, Node, preview, typed_lookup, unique_prefix_match


def build_deliberation_graph(conn: sqlite3.Connection, *, since: str | None) -> Graph:
    from jarvis.council.agreement import supersede_score_rows
    from jarvis.council.council import build_roster

    g = Graph("deliberation")
    max_chars = gcfg.GRAPH_LABEL_MAX_CHARS
    limit = gcfg.GRAPH_DELIBERATION_MAX_ROUNDS
    sql = "SELECT * FROM council_rounds"
    params: list[object] = []
    if since:
        sql += " WHERE started_at >= ?"
        params.append(since)
    sql += " ORDER BY started_at DESC, round_id LIMIT ?"
    params.append(limit)
    rounds = [dict(r) for r in conn.execute(sql, params).fetchall()]
    if len(rounds) >= limit:
        g.truncated, g.truncated_reason = True, "round cap"

    scores_by_round: dict[str, list[dict]] = {}
    round_ids = [str(r["round_id"]) for r in rounds]
    if round_ids:
        marks = ",".join("?" * len(round_ids))
        for s in conn.execute(
            f"SELECT * FROM council_scores WHERE round_id IN ({marks}) ORDER BY id", tuple(round_ids)
        ):
            scores_by_round.setdefault(str(s["round_id"]), []).append(dict(s))

    run_rows: dict[str, sqlite3.Row] = {}
    wanted_runs = sorted({str(r["run_id"]) for r in rounds if r.get("run_id")})
    if wanted_runs:
        marks = ",".join("?" * len(wanted_runs))
        for r in conn.execute(
            f"SELECT run_id, agent, status, started_at FROM agent_runs WHERE run_id IN ({marks})",
            tuple(wanted_runs),
        ):
            run_rows[str(r["run_id"])] = r

    def _profile(name: str) -> str:
        pid = f"profile:{name}"
        g.add_node(Node(pid, "profile", preview(name, max_chars), {}))
        return pid

    for rd in rounds:
        rid = str(rd["round_id"])
        round_id = f"round:{rid}"
        g.add_node(Node(round_id, "round", rid[:8], {
            "workflow": rd.get("workflow"), "placement": rd.get("placement"), "trigger": rd.get("trigger"),
            "tier": rd.get("tier"), "status": rd.get("status"), "winner_profile": rd.get("winner_profile"),
            "winner_mean": rd.get("winner_mean"), "retry_validated": rd.get("retry_validated"),
            "retry_outcome": rd.get("retry_outcome"), "started_at": rd.get("started_at"),
        }))
        srows = scores_by_round.get(rid, [])
        roster = build_roster(rd, srows)                    # the card's numbers, D5 filter included
        for p in roster["proposers"]:
            pid = f"proposal:{rid}/{p['label']}"
            g.add_node(Node(pid, "proposal", preview(p["label"], max_chars),
                            {"profile": p["profile"], "mean": p["mean"]}))
            if p["profile"]:
                g.add_edge(Edge(_profile(p["profile"]), pid, "proposed", {}))
            g.add_edge(Edge(pid, round_id, "in_round", {}))
            if p.get("is_winner"):
                g.add_edge(Edge(pid, round_id, "won", {}))
        # ONE edge per (judge, proposal) — the kept row. 2026-09-05: this used
        # to emit an edge for the dropped row TOO, and since Graph.add_edge
        # appends without dedup (model.py) both landed on identical endpoints.
        # render.py then painted the faded one (FADED_ALPHA 0.45) over the
        # normal one (EDGE_ALPHA 0.70); composited that is ~0.835, so a
        # superseded edge came out BOLDER than an unsuperseded one — the exact
        # inverse of the intent, and invisible as a distinction. A replaced
        # score and its replacement are the same relationship, so the picture
        # draws it once. How many rows it replaced rides along as
        # `superseded_count` for anyone reading the JSON; `--agreement` already
        # reports the total separately, and summary_line already excluded
        # superseded edges from the judge and abstention counts.
        kept, dropped = supersede_score_rows(srows)
        superseded_by = Counter(
            (str(s.get("judge_profile") or ""), s.get("proposal_label") or "")
            for s in dropped
        )
        for s in kept:
            pid = f"proposal:{rid}/{s.get('proposal_label') or ''}"
            if pid not in g.nodes:                          # shadow-only label: skipped, never dangling
                continue
            key = (str(s.get("judge_profile") or ""), s.get("proposal_label") or "")
            g.add_edge(Edge(_profile(str(s.get("judge_profile") or "")), pid, "scored", {
                "score": s.get("score"), "shadow": int(s.get("shadow") or 0),
                "judge_tier": s.get("judge_tier"),
                "abstain_reason": preview(s.get("abstain_reason"), max_chars) or None,
                "superseded": False,
                "superseded_count": superseded_by.get(key, 0),
            }))
        if rd.get("run_id"):
            run_id = str(rd["run_id"])
            nid = f"run:{run_id}"
            row = run_rows.get(run_id)
            attrs = ({"agent": row["agent"], "status": row["status"], "started_at": row["started_at"]}
                     if row is not None else {"pruned": True})
            g.add_node(Node(nid, "run", run_id[:8], attrs))
            g.add_edge(Edge(round_id, nid, "for_run", {}))
    return g


def resolve_deliberation_focus(conn: sqlite3.Connection, graph: Graph, focus: str) -> str | None:
    typed, hit = typed_lookup(graph, focus)
    if typed:
        return hit
    if f"round:{focus}" in graph.nodes:
        return f"round:{focus}"
    hit = unique_prefix_match(graph, f"round:{focus}")
    if hit is not None:
        return hit
    for c in (f"profile:{focus}", f"run:{focus}"):
        if c in graph.nodes:
            return c
    return None
