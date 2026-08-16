"""Shared tool-result classifier (MORTIMER_AGENT_TRUST_PLAN.md D1).

Three layers of this codebase each used to make their own judgement about
whether a tool call succeeded, and disagreed: SkillRegistry.call() recorded
transport success only; SubAgent._loop's heuristic checked three literal
string prefixes; nothing inspected a tool's own JSON body. The result (see
the plan's §1.2/§1.1) was every `mcp_apps` call in a real incident recording
`ok=True` at both layers while the tool's JSON body said `{"ok": false,
"error": "...HTTP 401..."}}`, and a sub-agent going on to fabricate content
it never received.

This module is the ONE place that judgement is made now. jarvis/agents/base.py
and jarvis/skills/registry.py both import classify_tool_result and record
its verdict — they must never re-derive their own.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

# The three transport-level failure prefixes SkillRegistry.call() can
# return (jarvis/skills/registry.py) — timeout, transport exception, MCP
# isError, unknown tool, and server-not-in-context all funnel through one
# of these three shapes.
TRANSPORT_FAILURE_PREFIXES: tuple[str, ...] = (
    "{tool_name} failed:",
    "Unknown tool ",
    "Tool '{tool_name}' is not available",
)


@dataclass(frozen=True)
class ToolOutcome:
    ok: bool
    error: str | None       # short reason, None when ok
    body_failure: bool      # True when a JSON body said ok:false / error


def classify_tool_result(tool_name: str, result_str: str) -> ToolOutcome:
    """Classify one tool call's result string. Never raises.

    Rules, in order — do not reorder, and do not require an explicit
    `ok: true` in rule 3: many tools return bare data with no `ok`/`error`
    key at all (e.g. {"stat": [...]}), and treating an absent key as
    failure would break every one of them.
    """
    # Rule 1 — transport-level failure prefixes.
    if (
        result_str.startswith(f"{tool_name} failed:")
        or result_str.startswith("Unknown tool ")
        or result_str.startswith(f"Tool '{tool_name}' is not available")
    ):
        return ToolOutcome(ok=False, error=result_str[:300], body_failure=False)

    # Rule 2 — a JSON object whose body says it failed.
    try:
        parsed = json.loads(result_str)
    except (json.JSONDecodeError, TypeError, ValueError):
        parsed = None

    if isinstance(parsed, dict):
        body_ok = parsed.get("ok")
        body_error = parsed.get("error")
        if body_ok is False or body_error:
            error = str(body_error) if body_error else "tool reported ok: false"
            return ToolOutcome(ok=False, error=error[:300], body_failure=True)

    # Rule 3 — everything else (non-JSON text, JSON arrays, JSON objects
    # with no ok/error key, or a JSON object explicitly ok=True).
    return ToolOutcome(ok=True, error=None, body_failure=False)
