"""GL7 *capability* — procedures, skills, workflows, agents, and the runs that taught them."""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

import yaml

from jarvis.graphs import config as gcfg
from jarvis.graphs.model import Edge, Graph, Node, preview, typed_lookup

_PROMOTED_RE = re.compile(r"^procedure:(\d+(?:\+\d+)*)$")      # Rev 2: "procedure:18+22"
_REPO_ROOT = Path(__file__).resolve().parents[2]


def _source_run_ids(raw: object) -> list[str]:
    try:
        value = json.loads(raw or "[]")
    except (TypeError, ValueError):
        return []
    return [str(x) for x in value] if isinstance(value, list) else []


def _agent_names(agents_yaml: Path) -> list[str]:
    data = yaml.safe_load(agents_yaml.read_text(encoding="utf-8")) or {}
    return [str(a["name"]) for a in (data.get("sub_agents") or []) if isinstance(a, dict) and a.get("name")]


def _ensure_agent(g: Graph, name: str) -> str:
    nid = f"agent:{name}"
    if nid not in g.nodes:
        g.add_node(Node(nid, "agent", name, {"unknown": True}))
    return nid


def _ensure_run(g: Graph, rid: str, run_rows: dict[str, sqlite3.Row]) -> str:
    nid = f"run:{rid}"
    if nid not in g.nodes:
        row = run_rows.get(rid)
        attrs = ({"status": row["status"], "started_at": row["started_at"]}
                 if row is not None else {"pruned": True})
        g.add_node(Node(nid, "run", rid[:8], attrs))
    return nid


def _ensure_procedure(g: Graph, pid: str) -> str:
    nid = f"procedure:{pid}"
    if nid not in g.nodes:
        g.add_node(Node(nid, "procedure", pid, {"missing": True}))
    return nid


def build_capability_graph(conn: sqlite3.Connection, *, skills_dir: Path | None = None,
                           skills_config: Path | None = None, workflows_dir: Path | None = None,
                           agents_yaml: Path | None = None) -> Graph:
    from jarvis.agent_skills import SKILLS_CONFIG, SKILLS_DIR, discover, enabled_names
    from jarvis.workflows import WORKFLOWS_DIR, load_workflows

    skills_dir = Path(skills_dir or SKILLS_DIR)
    skills_config = Path(skills_config or SKILLS_CONFIG)
    workflows_dir = Path(workflows_dir or WORKFLOWS_DIR)
    agents_yaml = Path(agents_yaml or (_REPO_ROOT / "config" / "agents.yaml"))
    max_chars = gcfg.GRAPH_LABEL_MAX_CHARS
    g = Graph("capability")

    for name in _agent_names(agents_yaml):
        g.add_node(Node(f"agent:{name}", "agent", name, {}))

    procs = conn.execute(
        "SELECT id, agent, label, status, success_count, failure_count, source_run_ids "
        "FROM procedures ORDER BY id"
    ).fetchall()
    for p in procs:
        g.add_node(Node(f"procedure:{p['id']}", "procedure", preview(p["label"], max_chars), {
            "agent": p["agent"], "status": p["status"], "success_count": p["success_count"],
            "failure_count": p["failure_count"], "label": preview(p["label"], max_chars),
        }))
    wanted = sorted({rid for p in procs for rid in _source_run_ids(p["source_run_ids"])})
    run_rows: dict[str, sqlite3.Row] = {}
    if wanted:
        marks = ",".join("?" * len(wanted))
        for r in conn.execute(
            f"SELECT run_id, status, started_at FROM agent_runs WHERE run_id IN ({marks})", tuple(wanted)
        ):
            run_rows[r["run_id"]] = r
    for p in procs:
        pid = f"procedure:{p['id']}"
        g.add_edge(Edge(pid, _ensure_agent(g, str(p["agent"] or "")), "learned_by", {}))
        for rid in _source_run_ids(p["source_run_ids"]):
            g.add_edge(Edge(pid, _ensure_run(g, rid, run_rows), "learned_from", {}))

    enabled = set(enabled_names(skills_config))
    for path, skill, _problems in discover(skills_dir):
        if skill is None:
            g.add_node(Node(f"skill:{path.parent.name}", "skill", path.parent.name, {"invalid": True}))
            continue
        sid = f"skill:{skill.name}"
        g.add_node(Node(sid, "skill", preview(skill.name, max_chars), {
            "enabled": skill.name in enabled, "description": preview(skill.description, max_chars),
        }))
        meta = skill.metadata if isinstance(skill.metadata, dict) else {}
        m = _PROMOTED_RE.match(str(meta.get("source", "")))
        if m:
            for proc_id in m.group(1).split("+"):
                g.add_edge(Edge(sid, _ensure_procedure(g, proc_id), "promoted_from", {}))
        agent = meta.get("agent")
        if agent:
            g.add_edge(Edge(sid, _ensure_agent(g, str(agent)), "for_agent", {}))

    for wf in load_workflows(workflows_dir):
        g.add_node(Node(f"workflow:{wf.name}", "workflow", preview(wf.name, max_chars),
                        {"when": preview(wf.when, max_chars)}))

    for r in conn.execute(
        "SELECT key, became FROM memories WHERE kind='fact' AND became LIKE 'workflow:%' ORDER BY key"
    ):
        slug = str(r["became"]).partition(":")[2]
        if not slug:
            continue
        wid = f"workflow:{slug}"
        if wid not in g.nodes:
            g.add_node(Node(wid, "workflow", preview(slug, max_chars), {"missing": True}))
        fid = f"fact:{r['key']}"
        g.add_node(Node(fid, "fact", preview(r["key"], max_chars), {"archived": True}))
        g.add_edge(Edge(wid, fid, "extracted_from", {}))
    return g


def resolve_capability_focus(conn: sqlite3.Connection, graph: Graph, focus: str) -> str | None:
    typed, hit = typed_lookup(graph, focus)
    if typed:
        return hit
    cands = [f"skill:{focus}", f"workflow:{focus}"]
    if focus.isdigit():
        cands.append(f"procedure:{focus}")
    cands.append(f"agent:{focus}")
    for c in cands:
        if c in graph.nodes:
            return c
    return None
