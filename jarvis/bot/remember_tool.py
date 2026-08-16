"""remember tool (MORTIMER_MEMORY_PROCEDURES_PLAN.md D6/D8).

A Supervisor-only tool (not a sub-agent tool) for immediate, high-confidence
memory writes — when the user explicitly states a durable preference,
correction, or standing instruction, the Supervisor can store it right now
instead of waiting for end-of-session extraction or the next periodic sweep.

Wired exactly like set_voice (jarvis/bot/voice_switch.py's
build_set_voice_tool is the template) since remember is a direct Supervisor
action with no sub-agent involved — the same category set_voice already is.

Calls jarvis.memory.upsert_fact directly rather than re-implementing any of
its safety properties: the Phase 5b content scan (scan_memory_content),
key-based upsert semantics, and MAX_FACT_CHARS truncation all apply exactly
as they do to end-of-session extraction, so remember can never silently
diverge from what that path considers safe to store.

D8: a content-scan rejection is silent to the user beyond the generic
confirmation sentence — upsert_fact's own logger.warning is sufficient. The
rejection reason is never surfaced back to the LLM, which could otherwise
try to "fix" and resubmit flagged content.
"""

from __future__ import annotations

from typing import Callable

from jarvis.db import get_conn
from jarvis.memory import upsert_fact

REMEMBER_SCHEMA = {
    "type": "function",
    "function": {
        "name": "remember",
        "description": (
            "Immediately store one durable fact about the user, stated "
            "explicitly and unambiguously in this turn — a preference, "
            "a correction, a standing instruction. Do not use this for "
            "one-off requests, small talk, or anything uncertain; those "
            "are handled by ordinary end-of-session memory."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "description": "lowercase dotted path, e.g. "
                                   "user.preference.units",
                },
                "value": {"type": "string"},
            },
            "required": ["key", "value"],
        },
    },
}


def build_remember_tool(session_id: str) -> tuple[dict, Callable[[dict], object]]:
    """Return (openai_tool_schema, async_handler) for remember."""

    async def handler(arguments: dict) -> str:
        key = str(arguments.get("key", "")).strip()
        value = str(arguments.get("value", "")).strip()
        if not key or not value:
            return "Nothing to remember — both a key and a value are required."
        with get_conn() as conn:
            upsert_fact(conn, key, value, session_id)
        return f"Got it — I'll remember {key}."

    return REMEMBER_SCHEMA, handler
