"""cost_summary tool (MORTIMER_OPTIMIZATION_PLAN.md Phase 0, readiness
checklist step 9 — the voice-skill half of the costs service).

A Supervisor-only tool, wired exactly like remember/set_voice
(jarvis/bot/remember_tool.py is the template this follows): a direct
completion tool with no sub-agent delegation, no side-effect injection.
Calls jarvis.costs_api.summary_text() directly rather than going over
HTTP to the costs service (:8487) — same process, same DB file, so an
in-process call is simpler and one fewer moving part than a loopback
request, and it means this tool still works even if the costs Procfile
entry isn't running for some reason (the SwiftUI dashboard, by contrast,
genuinely needs the HTTP surface, since it's a separate app/process).

Never raises into the voice turn — wrapped the same way every other
ledger-adjacent call in this repo is (usage_ledger.record_call/
record_completion's own try/except discipline): a read failure here
must degrade to an apologetic spoken line, never break the turn.
"""

from __future__ import annotations

from typing import Callable

from jarvis.costs_api import summary_text

COST_SUMMARY_SCHEMA = {
    "type": "function",
    "function": {
        "name": "cost_summary",
        "description": (
            "Report how much has been spent on AI model usage this month "
            "(or a past month) — total spend, which part of the system is "
            "spending the most, and budget status if a budget is set. Use "
            "this for any question about API/model costs, spend, or "
            "budget — 'how much have we spent', 'what's our AI bill "
            "looking like', 'are we over budget'."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "month": {
                    "type": "string",
                    "description": (
                        "Billing month as YYYY-MM. Omit for the current "
                        "month; only set this when the user asks about a "
                        "specific past month."
                    ),
                },
            },
            "required": [],
        },
    },
}


def build_cost_summary_tool() -> tuple[dict, Callable[[dict], object]]:
    """Return (openai_tool_schema, async_handler) for cost_summary."""

    async def handler(arguments: dict) -> str:
        month = str(arguments.get("month", "")).strip() or None
        try:
            return summary_text(month)
        except Exception:  # noqa: BLE001 — a cost-reporting bug must never
            # break the live voice turn, same discipline as
            # usage_ledger.record_call's own catch-all.
            return "I couldn't pull up the cost summary just now."

    return COST_SUMMARY_SCHEMA, handler
