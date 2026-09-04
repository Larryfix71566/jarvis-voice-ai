"""costs_api.py — HTTP surface over the cost ledger.

MORTIMER_OPTIMIZATION_PLAN.md Phase 0, readiness checklist step 7.
Landed from the plan's Rev 3 draft (docs/plans/optimization_rev3_files/
costs_api.py) with its schema cross-checked against the actually-shipped
jarvis/usage_ledger.py (llm_calls: ts, month, session_id, rung, provider,
model, input_tokens, output_tokens, cache_write_tokens, cache_read_tokens,
reported_cost, computed_cost, gen_id) — the draft's queries match that
schema exactly, so this landed with no structural changes, only this note.

Serves both consumers agreed for the design:
  A (voice skill): call summary_text() directly, or GET /costs/summary
    and speak the 'spoken' field.
  B (SwiftUI card): GET /costs/summary and /costs/daily for the card +
    sparkline.

Run standalone (own Procfile entry, port 8487 by default):
    uvicorn jarvis.costs_api:app --port 8487
or mount `router` into an existing FastAPI app in the service family.

Budget: JARVIS_MONTHLY_BUDGET_USD env/config (0 = no budget). Threshold
crossings are reported in the payload; conversational alerting wires in
after Phase 0 per plan (voice skill + SwiftUI card, readiness checklist
steps 8-9 — not yet wired as of this commit).
"""

from __future__ import annotations

import calendar
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, FastAPI

# Same root-anchored default as jarvis/usage_ledger.py (this service is
# started from its own Procfile line, so CWD must not decide the path).
_REPO_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get("JARVIS_COSTS_DB") or _REPO_ROOT / "data" / "costs.db")
BUDGET = float(os.environ.get("JARVIS_MONTHLY_BUDGET_USD", "0") or 0)

router = APIRouter(prefix="/costs", tags=["costs"])
EFF = "COALESCE(reported_cost, computed_cost)"
# MORTIMER_SESSION_MISSES_PLAN.md S1 — the voice transport rungs
# (jarvis.usage_ledger.RUNGS' tts/stt), the "voice" bucket of
# scripts/cost_report.py.
VOICE_RUNGS = frozenset({"tts", "stt"})


def _conn() -> sqlite3.Connection:
    # Read-only consumer of a WAL database with two writer processes;
    # timeout covers the rare checkpoint moment.
    return sqlite3.connect(DB_PATH, timeout=5.0)


def _month_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _summary(month: str) -> dict:
    if not DB_PATH.exists():
        return {"month": month, "calls": 0, "total_usd": 0.0,
                "projected_usd": 0.0, "by_rung": [], "by_provider": [],
                "budget_usd": BUDGET, "budget_used_pct": 0.0,
                "unpriced_calls": 0,
                "voice_usd": 0.0, "llm_usd": 0.0}
    with _conn() as conn:
        total, calls = conn.execute(
            f"SELECT COALESCE(SUM({EFF}),0), COUNT(*) FROM llm_calls"
            " WHERE month=?", (month,)).fetchone()
        unpriced = conn.execute(
            "SELECT COUNT(*) FROM llm_calls WHERE month=?"
            " AND reported_cost IS NULL AND computed_cost IS NULL",
            (month,)).fetchone()[0]
        rungs = conn.execute(
            f"SELECT rung, COALESCE(SUM({EFF}),0) FROM llm_calls"
            " WHERE month=? GROUP BY rung ORDER BY 2 DESC", (month,)).fetchall()
        provs = conn.execute(
            f"SELECT provider, COALESCE(SUM({EFF}),0) FROM llm_calls"
            " WHERE month=? GROUP BY provider ORDER BY 2 DESC", (month,)).fetchall()
        days_elapsed = conn.execute(
            "SELECT COUNT(DISTINCT substr(ts,1,10)) FROM llm_calls WHERE month=?",
            (month,)).fetchone()[0] or 1

    year, mon = map(int, month.split("-"))
    dim = calendar.monthrange(year, mon)[1]
    projected = (total / days_elapsed) * dim if total else 0.0
    # MORTIMER_SESSION_MISSES_PLAN.md S5 — the LLM-vs-voice split. The tts
    # and stt rungs already appear in by_rung by construction; these two
    # keys exist so a reader (the spoken summary, the Costs tab later) can
    # say how much of the total was transport without re-deriving it.
    voice = sum(v for r, v in rungs if r in VOICE_RUNGS)
    return {
        "month": month,
        "calls": calls,
        "total_usd": round(total, 2),
        "projected_usd": round(projected, 2),
        "by_rung": [{"rung": r, "usd": round(v, 2)} for r, v in rungs],
        "by_provider": [{"provider": p, "usd": round(v, 2)} for p, v in provs],
        "budget_usd": BUDGET,
        "budget_used_pct": round(total / BUDGET * 100, 1) if BUDGET else 0.0,
        "unpriced_calls": unpriced,
        "voice_usd": round(voice, 2),
        "llm_usd": round(total - voice, 2),
    }


def summary_text(month: str | None = None) -> str:
    """Spoken-form summary for the voice skill."""
    s = _summary(month or _month_now())
    if not s["calls"]:
        return "No model spend recorded this month yet."
    parts = [f"So far this month we've spent {s['total_usd']:.2f} dollars"
             f" across {s['calls']} model calls,"
             f" projecting to about {s['projected_usd']:.0f} by month end."]
    if s.get("voice_usd", 0.0) > 0:
        # S5: the transport share, spoken — the number the LLM-only ledger
        # hid for the whole of Phases 0-4.
        parts.append(f"About {s['voice_usd']:.2f} dollars of that was voice"
                     " — text to speech and transcription.")
    if s["by_rung"]:
        top = s["by_rung"][0]
        parts.append(f"The biggest line is {top['rung']} at {top['usd']:.2f}.")
    if s["budget_usd"]:
        parts.append(f"That's {s['budget_used_pct']:.0f} percent of the"
                     f" {s['budget_usd']:.0f} dollar budget.")
    if s["unpriced_calls"]:
        parts.append(f"Heads up: {s['unpriced_calls']} calls have no price"
                     " mapping and aren't counted.")
    return " ".join(parts)


@router.get("/summary")
def get_summary(month: str | None = None) -> dict:
    s = _summary(month or _month_now())
    s["spoken"] = summary_text(month)
    return s


@router.get("/daily")
def get_daily(month: str | None = None) -> dict:
    month = month or _month_now()
    if not DB_PATH.exists():
        return {"month": month, "daily": []}
    with _conn() as conn:
        rows = conn.execute(
            f"SELECT substr(ts,1,10), COALESCE(SUM({EFF}),0) FROM llm_calls"
            " WHERE month=? GROUP BY 1 ORDER BY 1", (month,)).fetchall()
    return {"month": month,
            "daily": [{"day": d, "usd": round(v, 4)} for d, v in rows]}


@router.get("/months")
def get_months() -> dict:
    if not DB_PATH.exists():
        return {"months": []}
    with _conn() as conn:
        rows = conn.execute(
            f"SELECT month, COALESCE(SUM({EFF}),0) FROM llm_calls"
            " GROUP BY month ORDER BY month DESC").fetchall()
    return {"months": [{"month": m, "usd": round(v, 2)} for m, v in rows]}


app = FastAPI(title="mortimer-costs")
app.include_router(router)
