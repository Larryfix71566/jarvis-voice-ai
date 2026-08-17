"""mcp-runlog logic (MORTIMER_MODEL_DISCIPLINE_AND_MAC_SHELL_PLAN.md C1).

Read-only agent access to Mortimer's own run log — the investigator gap:
"review the recent logs and find why that failed" previously had no
pathway, because no agent had a tool to query jarvis.runlog. Every
function here is a thin read-only wrapper over jarvis.runlog.store's and
jarvis.council.council's existing read helpers — the SAME functions the
CLI, the admin sidecar, and the console's Runs/council panels already
use, so this becomes a fourth consumer that cannot disagree with the
other three. No function in this module writes anything.
"""

from __future__ import annotations

from typing import Any

from jarvis.council import council as council_mod
from jarvis.runlog import store as runlog_store

# Caps mirror the admin sidecar's own clamps (jarvis/admin/server.py) —
# a small model must not be able to request an unbounded dump.
LIST_LIMIT_MAX = 50
COUNCIL_LIMIT_MAX = 50
TASK_PREVIEW_CHARS = 200


def _preview_task(task: str | None) -> str:
    task = task or ""
    return task if len(task) <= TASK_PREVIEW_CHARS else task[:TASK_PREVIEW_CHARS] + "…"


def runlog_list(
    agent: str = "",
    status: str = "",
    since: str = "",
    task_contains: str = "",
    limit: int = 20,
) -> dict[str, Any]:
    """List recent sub-agent runs, newest first. All filters optional.
    `since` accepts "7d"/"24h"/"30m" or an ISO-8601 timestamp."""
    clamped_limit = max(1, min(LIST_LIMIT_MAX, limit))
    rows = runlog_store.list_runs(
        agent=agent or None,
        status=status or None,
        since=runlog_store.parse_since(since or None),
        limit=clamped_limit,
    )
    needle = task_contains.strip().lower()
    if needle:
        rows = [r for r in rows if needle in (r.get("task") or "").lower()]
    return {
        "ok": True,
        "runs": [
            {
                "run_id": r.get("run_id"),
                "started_at": r.get("started_at"),
                "agent": r.get("agent"),
                "status": r.get("status"),
                "latency_ms": r.get("latency_ms"),
                "tools_ok": r.get("tools_ok"),
                "tools_failed": r.get("tools_failed"),
                "model": r.get("model"),
                "task": _preview_task(r.get("task")),
            }
            for r in rows
        ],
    }


def runlog_detail(run_id: str) -> dict[str, Any]:
    """Full detail for one run: the row, its bounded event previews, and
    the on-disk JSONL payload path for human follow-up (never the raw
    payload content itself — event previews are already bounded and
    sufficient for diagnosis; the path lets a human go deeper)."""
    detail = runlog_store.get_run(run_id)
    if detail is None:
        return {"ok": False, "error": f"no such run: {run_id}"}
    run = detail["run"]
    return {
        "ok": True,
        "run": {
            "run_id": run.get("run_id"),
            "started_at": run.get("started_at"),
            "finished_at": run.get("finished_at"),
            "agent": run.get("agent"),
            "status": run.get("status"),
            "latency_ms": run.get("latency_ms"),
            "tools_ok": run.get("tools_ok"),
            "tools_failed": run.get("tools_failed"),
            "model": run.get("model"),
            "task": run.get("task"),
            "error": run.get("error"),
            "payload_path": run.get("payload_path"),
        },
        "events": [
            {
                "seq": e.get("seq"),
                "type": e.get("type"),
                "tool": e.get("tool"),
                "ok": e.get("ok"),
                "latency_ms": e.get("latency_ms"),
                "args_preview": e.get("args_preview"),
                "result_preview": e.get("result_preview"),
            }
            for e in detail["events"]
        ],
    }


def runlog_stats(since: str = "7d") -> dict[str, Any]:
    """Per-agent, per-status counts and per-model success rates over the
    window — precomputed so a small model can't misaggregate it from a
    raw run list."""
    rows = runlog_store.list_runs(
        since=runlog_store.parse_since(since or "7d"), limit=1000,
    )
    by_agent: dict[str, dict[str, int]] = {}
    by_model: dict[str, dict[str, int]] = {}
    for r in rows:
        agent = r.get("agent") or "?"
        status = r.get("status") or "?"
        model = r.get("model") or "(unknown)"
        by_agent.setdefault(agent, {}).setdefault(status, 0)
        by_agent[agent][status] += 1
        by_model.setdefault(model, {"ok": 0, "total": 0})
        by_model[model]["total"] += 1
        if status == "ok":
            by_model[model]["ok"] += 1
    model_success_rate = {
        model: (round(counts["ok"] / counts["total"], 3) if counts["total"] else None)
        for model, counts in by_model.items()
    }
    return {
        "ok": True,
        "since": since,
        "total_runs": len(rows),
        "by_agent_status": by_agent,
        "by_model": by_model,
        "model_success_rate": model_success_rate,
    }


def council_list(limit: int = 10) -> dict[str, Any]:
    """Recent council rounds (escalation, planning, review, appbuild)."""
    clamped_limit = max(1, min(COUNCIL_LIMIT_MAX, limit))
    rounds = council_mod.list_rounds(limit=clamped_limit)
    return {
        "ok": True,
        "rounds": [
            {
                "round_id": r.get("round_id"),
                "started_at": r.get("started_at"),
                "workflow": r.get("workflow"),
                "placement": r.get("placement"),
                "status": r.get("status"),
                "goal": _preview_task(r.get("goal")),
                "winner_profile": r.get("winner_profile"),
            }
            for r in rounds
        ],
    }
