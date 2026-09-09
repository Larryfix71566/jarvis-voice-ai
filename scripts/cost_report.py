#!/usr/bin/env python3
"""cost_report.py — Phase 0 baseline report from the ledger.

MORTIMER_OPTIMIZATION_PLAN.md Phase 0, readiness checklist step 7. Landed
from the plan's Rev 3 draft (docs/plans/optimization_rev3_files/
cost_report.py) with one change from the draft: DB_PATH is root-anchored
via this file's own __file__ (same JARVIS_COSTS_DB-overridable pattern as
jarvis/usage_ledger.py and jarvis/costs_api.py), not CWD-relative — the
draft assumed "run from repo root", which the other two ledger-adjacent
files deliberately do NOT assume, for the same two-writer-process reason
documented in usage_ledger.py. BUCKETS below double-checked against the
actually-shipped jarvis.usage_ledger.RUNGS (16 entries, all present here).

Usage:
    python scripts/cost_report.py            # current month
    python scripts/cost_report.py 2026-09    # specific month
    python scripts/cost_report.py 2026-09 --json

Reports: total spend, input vs output share, per-rung share, per-model
spend, cache hit rate, run-rate projection, and verdicts on assumptions
A1 (input dominance), A3 (sub-agent share), A5 (routed cache passthrough).
A2 (prefix share) needs prompt-assembly sizes, not the ledger — measured
in Phase 1 when breakpoints go in.

Effective cost per row: reported_cost when present (OpenRouter ground
truth) else computed_cost. Rows with neither are counted and flagged —
an unmapped model must be visible, never silently free.
"""

from __future__ import annotations

import calendar
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get("JARVIS_COSTS_DB") or _REPO_ROOT / "data" / "costs.db")

# Rev 3: the plan's A3 ("sub-agents are ~30% of spend") is about the FIVE
# delegated specialists, not every non-supervisor call. Background
# maintenance and the planner/executor loop are their own buckets — folding
# them into "sub-agent share" would overstate A3 by exactly the rungs Phase
# 2 and Phase 3 target separately. Vocabulary mirrors jarvis/usage_ledger.RUNGS.
BUCKETS = {
    "supervisor": {"supervisor"},
    "sub_agents": {"scheduler", "librarian", "analyst", "systems",
                   "developer", "app_builder"},
    "background": {"memory_merge", "memory_classify", "memory_extraction",
                   "kb_digest", "procedures_describe"},
    "planner":    {"planning", "council"},
    "executor":   {"selfedit_executor", "appbuild_executor"},
    "research":   {"research"},
    # MORTIMER_SESSION_MISSES_PLAN.md S1 — voice transport (rows carry
    # quantity/unit, zero tokens; priced per natural unit).
    "voice":      {"tts", "stt"},
}


def bucket_of(rung: str) -> str:
    for name, rungs in BUCKETS.items():
        if rung in rungs:
            return name
    return "unknown"


def q(conn, sql, args=()):
    return conn.execute(sql, args).fetchall()


def build_report(conn: sqlite3.Connection, month: str) -> dict:
    """The report as a dict — every number the text rendering prints.
    Factored out of main() for MORTIMER_SESSION_MISSES_PLAN.md S1 so the
    voice split can be pinned by a test (tests/unit/test_cost_report.py)
    instead of eyeballed in stdout; main() renders exactly this dict."""
    eff = "COALESCE(reported_cost, computed_cost)"
    base = f"FROM llm_calls WHERE month = ?"

    total, n_calls = q(conn, f"SELECT COALESCE(SUM({eff}),0), COUNT(*) {base}", (month,))[0]
    unpriced = q(conn, f"SELECT COUNT(*), GROUP_CONCAT(DISTINCT model) {base}"
                       " AND reported_cost IS NULL AND computed_cost IS NULL", (month,))[0]

    # input vs output cost split (computed rows only — needs the price split)
    io = q(conn, f"""
        SELECT model,
               SUM(input_tokens), SUM(output_tokens),
               SUM(cache_write_tokens), SUM(cache_read_tokens),
               COALESCE(SUM({eff}),0)
        {base} GROUP BY model ORDER BY 6 DESC""", (month,))

    rungs = q(conn, f"SELECT rung, COUNT(*), COALESCE(SUM({eff}),0) {base}"
                    " GROUP BY rung ORDER BY 3 DESC", (month,))

    # MORTIMER_OPTIMIZATION_PLAN.md Phase 3 Rev 3.3 (2026-09-03): executor
    # rows split by plan_state ('planned' | 'planless' | 'untagged' for rows
    # older than the column). This is the split the planner/executor
    # safety argument needs — agent_events showed ~85% of executor sessions
    # run with no plan. The column is added lazily by usage_ledger._conn(),
    # so a ledger no writer has touched since that landed may not have it
    # yet; skip the section rather than fail the whole report.
    has_plan_state = any(
        r[1] == "plan_state" for r in q(conn, "PRAGMA table_info(llm_calls)")
    )
    plan_split = q(conn, f"""
        SELECT rung, COALESCE(plan_state, 'untagged'), COUNT(*), COALESCE(SUM({eff}),0)
        {base} AND rung IN ('selfedit_executor', 'appbuild_executor')
        GROUP BY 1, 2 ORDER BY 1, 2""", (month,)) if has_plan_state else []

    cache = q(conn, f"""
        SELECT provider,
               SUM(CASE WHEN cache_read_tokens > 0 THEN 1 ELSE 0 END),
               COUNT(*)
        {base} GROUP BY provider""", (month,))

    days = q(conn, f"SELECT substr(ts,1,10), COALESCE(SUM({eff}),0) {base}"
                   " GROUP BY 1 ORDER BY 1", (month,))

    # projection
    year, mon = map(int, month.split("-"))
    days_in_month = calendar.monthrange(year, mon)[1]
    days_elapsed = len(days) or 1
    projected = (total / days_elapsed) * days_in_month if total else 0.0

    by_bucket: dict[str, float] = {}
    for r, _, c in rungs:
        by_bucket[bucket_of(r)] = by_bucket.get(bucket_of(r), 0.0) + c
    sub_cost = by_bucket.get("sub_agents", 0.0)
    sub_share = (sub_cost / total) if total else 0.0

    tin = sum(r[1] for r in io)
    tout = sum(r[2] for r in io)
    tcache_r = sum(r[4] for r in io)

    # MORTIMER_SESSION_MISSES_PLAN.md S1 — voice transport. quantity/unit
    # are added lazily by usage_ledger._conn() (same as plan_state above),
    # so a ledger no writer has touched since may lack them; fall back to
    # zeros rather than fail the report.
    has_quantity = any(
        r[1] == "quantity" for r in q(conn, "PRAGMA table_info(llm_calls)")
    )
    if has_quantity:
        tts_rows, tts_chars, tts_usd = q(conn, f"""
            SELECT COUNT(*), COALESCE(SUM(quantity),0), COALESCE(SUM({eff}),0)
            {base} AND rung = 'tts'""", (month,))[0]
        stt_rows, stt_seconds, stt_usd = q(conn, f"""
            SELECT COUNT(*), COALESCE(SUM(quantity),0), COALESCE(SUM({eff}),0)
            {base} AND rung = 'stt'""", (month,))[0]
    else:
        tts_rows = tts_chars = tts_usd = 0
        stt_rows = stt_seconds = stt_usd = 0
    voice_usd = by_bucket.get("voice", 0.0)
    llm_usd = total - voice_usd

    report = {
        "month": month,
        "calls": n_calls,
        "total_cost_usd": round(total, 4),
        "projected_month_end_usd": round(projected, 2),
        "unpriced_calls": {"count": unpriced[0], "models": unpriced[1]},
        "tokens": {"input_uncached": tin, "output": tout, "cache_read": tcache_r},
        "per_rung": [{"rung": r, "calls": c, "cost": round(v, 4)} for r, c, v in rungs],
        "executor_by_plan_state": [
            {"rung": r, "plan_state": p, "calls": c, "cost": round(v, 4)}
            for r, p, c, v in plan_split
        ],
        "per_bucket": {k: round(v, 4) for k, v in sorted(by_bucket.items(), key=lambda kv: -kv[1])},
        "per_model": [
            {"model": m, "in": i, "out": o, "cache_w": cw, "cache_r": cr,
             "cost": round(v, 4)} for m, i, o, cw, cr, v in io
        ],
        "cache_hit_calls_by_provider": [
            {"provider": p, "with_cache_reads": h, "calls": t} for p, h, t in cache
        ],
        "daily": [{"day": d, "cost": round(v, 4)} for d, v in days],
        "voice": {
            "tts_rows": tts_rows, "tts_chars": tts_chars, "tts_usd": round(tts_usd, 4),
            "stt_rows": stt_rows, "stt_seconds": round(stt_seconds, 1),
            "stt_usd": round(stt_usd, 4),
        },
        "voice_usd": round(voice_usd, 4),
        "llm_usd": round(llm_usd, 4),
        "assumption_verdicts": {},
    }

    # A1: input dominance — token-based proxy; exact split needs price map rows
    if tin + tout:
        report["assumption_verdicts"]["A1_input_token_share"] = round(
            (tin + tcache_r) / (tin + tcache_r + tout), 3)
    # A3: sub-agent share of spend — the five specialists only (see BUCKETS)
    report["assumption_verdicts"]["A3_subagent_cost_share"] = round(sub_share, 3)
    report["assumption_verdicts"]["A3_non_supervisor_share"] = round(
        (total - by_bucket.get("supervisor", 0.0)) / total, 3) if total else 0.0
    # A5: routed cache passthrough
    for p, h, t in cache:
        if p == "openrouter" and t >= 10:
            report["assumption_verdicts"]["A5_routed_cache_working"] = h > 0
    return report


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    month = args[0] if args else datetime.now(timezone.utc).strftime("%Y-%m")
    as_json = "--json" in sys.argv

    if not DB_PATH.exists():
        sys.exit(f"No ledger at {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    report = build_report(conn, month)

    if as_json:
        print(json.dumps(report, indent=2))
        return

    total = report["total_cost_usd"]
    unpriced = report["unpriced_calls"]
    tokens = report["tokens"]
    print(f"=== Mortimer cost report — {month} ===")
    print(f"calls: {report['calls']}   total: ${total:.2f}"
          f"   projected month-end: ${report['projected_month_end_usd']:.2f}")
    if unpriced["count"]:
        print(f"!! {unpriced['count']} calls have NO cost (unmapped models: {unpriced['models']})"
              f" — fill config/model_prices.yaml")
    print(f"tokens: in(uncached)={tokens['input_uncached']:,}"
          f"  cache_read={tokens['cache_read']:,}  out={tokens['output']:,}")
    print("\nby rung:")
    for row in report["per_rung"]:
        pct = (row["cost"] / total * 100) if total else 0
        print(f"  {row['rung']:<14} {row['calls']:>6} calls  ${row['cost']:>8.2f}  {pct:5.1f}%")
    if report["executor_by_plan_state"]:
        print("\nexecutor by plan_state (Phase 3 Rev 3.3):")
        for row in report["executor_by_plan_state"]:
            print(f"  {row['rung']:<18} {row['plan_state']:<9} {row['calls']:>6} calls  ${row['cost']:>8.2f}")
    print("\nby bucket:")
    for k, v in report["per_bucket"].items():
        pct = (v / total * 100) if total else 0
        print(f"  {k:<14} ${v:>8.2f}  {pct:5.1f}%")
    # MORTIMER_SESSION_MISSES_PLAN.md S1 — the split the LLM-only ledger hid.
    voice = report["voice"]
    voice_pct = (report["voice_usd"] / total * 100) if total else 0
    print("\nvoice transport (MORTIMER_SESSION_MISSES_PLAN.md):")
    print(f"  tts: {voice['tts_rows']} rows, {int(voice['tts_chars']):,} chars, ${voice['tts_usd']:.4f}")
    print(f"  stt: {voice['stt_rows']} rows, {voice['stt_seconds'] / 60:.1f} min, ${voice['stt_usd']:.4f}")
    print(f"  llm ${report['llm_usd']:.4f} vs voice ${report['voice_usd']:.4f}"
          f"  (voice share {voice_pct:.0f}%)")
    print("\nby model:")
    for row in report["per_model"]:
        print(f"  {row['model']:<44} ${row['cost']:>8.2f}  cache_r={row['cache_r']:,}")
    print("\ncache reads by provider:")
    for row in report["cache_hit_calls_by_provider"]:
        print(f"  {row['provider']:<12} {row['with_cache_reads']}/{row['calls']} calls had cache reads")
    print("\nverdicts:", json.dumps(report["assumption_verdicts"]))


if __name__ == "__main__":
    main()
