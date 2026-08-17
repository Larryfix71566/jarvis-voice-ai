"""python -m jarvis.runlog — read-only CLI over the run log (plan §5.10).

Usage:
    python -m jarvis.runlog
    python -m jarvis.runlog --agent developer --status failed --since 2d
    python -m jarvis.runlog --run <run_id>
    python -m jarvis.runlog --json

Colorless plain text, no new dependencies.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime

from jarvis.runlog.store import get_run, list_runs, parse_since

_STATUSES = ("ok", "failed", "timeout", "running", "orphaned")


def _local_time(iso_ts: str) -> str:
    try:
        return datetime.fromisoformat(iso_ts).astimezone().strftime("%H:%M:%S")
    except ValueError:
        return iso_ts[:8]


def _fmt_latency(latency_ms: int | None) -> str:
    return f"{latency_ms}ms" if latency_ms is not None else "-"


def _fmt_tools(r: dict) -> str:
    """D5 (MORTIMER_AGENT_TRUST_PLAN.md): render 'ok/failed' when both
    counts are present; a row written before migration 0008 has NULL for
    both and falls back to the pre-existing tool_count alone, since NULL
    means "unknown", never "zero"."""
    ok, failed = r.get("tools_ok"), r.get("tools_failed")
    if ok is None or failed is None:
        return str(r.get("tool_count", 0))
    return f"{ok}/{failed}"


def _terminal_width() -> int:
    try:
        return shutil.get_terminal_size(fallback=(100, 24)).columns
    except Exception:  # noqa: BLE001 — cosmetic only
        return 100


def _print_table(runs: list[dict]) -> None:
    width = _terminal_width()
    # Fixed columns: time(8) run_id(8) agent(10) status(9) latency(8) tools(5)
    fixed = 8 + 1 + 8 + 1 + 10 + 1 + 9 + 1 + 8 + 1 + 5 + 1
    task_width = max(10, width - fixed)
    header = (
        f"{'time':<8} {'run_id':<8} {'agent':<10} {'status':<9} "
        f"{'latency':<8} {'tools':<5} task"
    )
    print(header)
    print("-" * min(width, len(header) + task_width))
    for r in runs:
        task = (r.get("task") or "").replace("\n", " ")
        if len(task) > task_width:
            task = task[: max(0, task_width - 1)] + "…"
        print(
            f"{_local_time(r['started_at']):<8} "
            f"{r['run_id'][:8]:<8} "
            f"{r['agent']:<10} "
            f"{r['status']:<9} "
            f"{_fmt_latency(r.get('latency_ms')):<8} "
            f"{_fmt_tools(r):<5} "
            f"{task}"
        )


def _print_detail(detail: dict) -> None:
    run = detail["run"]
    print(f"run_id       {run['run_id']}")
    print(f"agent        {run['agent']} ({run.get('display_name', '')})")
    print(f"session_id   {run.get('session_id') or '-'}")
    print(f"status       {run['status']}")
    print(f"started_at   {run['started_at']}")
    print(f"ended_at     {run.get('ended_at') or '-'}")
    print(f"latency_ms   {run.get('latency_ms')}")
    print(f"tool_count   {run.get('tool_count', 0)}")
    print(f"tools        {_fmt_tools(run)}")
    # MORTIMER_PLANNING_PATHWAY_PLAN.md P3 — NULL on pre-migration-0011
    # rows, never backfilled; "—" makes that explicit rather than blank.
    print(f"model        {run.get('model') or '—'}")
    if run.get("error"):
        print(f"error        {run['error']}")
    print(f"task         {run['task']}")
    print()
    print("-- events --")
    for ev in detail["events"]:
        print(
            f"[{ev['seq']:>3}] {ev['type']:<12} tool={ev.get('tool') or '-':<20} "
            f"server={ev.get('server') or '-':<10} ok={ev.get('ok')} "
            f"latency_ms={ev.get('latency_ms')}"
        )
    print()
    if not detail["payload"]:
        print("(payload pruned or unavailable)")
        return
    print("-- payload --")
    for record in detail["payload"]:
        print(json.dumps(record, default=str))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m jarvis.runlog")
    parser.add_argument("--agent", default=None)
    parser.add_argument("--status", default=None, choices=_STATUSES)
    parser.add_argument("--since", default=None,
                         help="Nd | Nh | Nm | ISO-8601 date")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--run", default=None, metavar="RUN_ID",
                         help="show full detail for one run")
    parser.add_argument("--json", action="store_true",
                         help="machine-readable output")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.run:
        detail = get_run(args.run)
        if detail is None:
            print(f"no such run: {args.run}", file=sys.stderr)
            return 1
        if args.json:
            print(json.dumps(detail, indent=2, default=str))
        else:
            _print_detail(detail)
        return 0

    since = parse_since(args.since)
    runs = list_runs(
        agent=args.agent, status=args.status, since=since, limit=args.limit,
    )
    if args.json:
        print(json.dumps(runs, indent=2, default=str))
    else:
        _print_table(runs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
