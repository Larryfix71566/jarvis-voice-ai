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
import re
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


# WS-38 2A (docs/reviews/2026-11-19-request-resolution-design-note.md §6).
# Every failure carries one of three classes, because the next step differs:
#   transient — the same step may succeed if tried once more;
#   approach  — the same step will fail again; change the tool, the input or
#               the agent;
#   policy    — a guard refused on purpose; stop and tell the user, never
#               route around it.
# At 9:51 PM on 2026-11-18 an analyst repeated an identical refused weather
# call four times because nothing said which of these it was.
FAILURE_CLASSES: tuple[str, ...] = ("transient", "approach", "policy")

# A failure whose reason is not in REASON_CLASSES. Its class is `approach`,
# so nothing retries blindly.
UNLISTED_REASON = "tool_reported_failure"
DEFAULT_FAILURE_CLASS = "approach"

# The ONE table from closed reason code to class. A reason is always a key
# of this table or UNLISTED_REASON, never free text, so it is safe to log on
# a private turn (see RunLogger.tool_result).
REASON_CLASSES: dict[str, str] = {
    # Host categories from SkillRegistry._invoke.
    "tool_timeout": "transient",
    "tool_transport_error": "transient",
    "tool_exception": "approach",
    "mcp_tool_error": "approach",
    "unknown_tool": "approach",
    "tool_not_available": "approach",
    UNLISTED_REASON: "approach",
    "invalid_tool_result_content": "approach",
    "development_operation_failed": "approach",
    "workspace_source_unavailable": "approach",
    "advisory_source_unavailable": "approach",
    "tool_source_scope_invalid": "policy",
    "protected_turn": "policy",
    "private_route_required": "policy",
    # Whole-run outcomes a sub-agent reports without a tool reason.
    "agent_timeout": "transient",
    "iterations_exhausted": "approach",
    # Named-weather reuse refusals (jarvis/bot/weather_reuse.py codes,
    # prefixed by the registry as weather_reuse_<code>).
    "weather_reuse_timeout": "transient",
    "weather_reuse_disconnected": "transient",
    "weather_reuse_not_ready": "transient",
    "weather_reuse_query_failed": "transient",
    "weather_reuse_stale_selection": "transient",
    "weather_reuse_invalid_request": "approach",
    "weather_reuse_invalid_reply": "approach",
    "weather_reuse_unsupported": "approach",
    "weather_reuse_ambiguous_result": "approach",
    "weather_reuse_result_unavailable": "approach",
    "weather_reuse_not_confirmed": "approach",
    "weather_reuse_protected_turn": "policy",
    "weather_reuse_protected_result": "policy",
    # The place guard (WeatherIntent.permits). Today it surfaces as
    # weather_reuse_invalid_request; the weather saved-card fix splits it out.
    "weather_reuse_not_requested": "policy",
    "weather_place_not_requested": "policy",
}

# Fixed phrases in transport-shaped failure strings ("<tool> failed: ...")
# that name a closed reason. Checked in order; first match wins.
_TRANSPORT_PHRASES: tuple[tuple[str, str], ...] = (
    ("protected turn cannot call", "protected_turn"),
    ("device location is not the requested place", "weather_place_not_requested"),
    ("stopped and could not be restarted", "tool_transport_error"),
    ("timed out after", "tool_timeout"),
)
_CODE_RE = re.compile(r"weather_reuse_[a-z_]+|[a-z][a-z0-9_]{2,63}")
_EXCEPTION_NAME_RE = re.compile(r"[A-Z][A-Za-z0-9_]{1,63}\.?")

# The tag appended to a FAILED: result so the Supervisor and the voice
# workflows can read the class without parsing prose. Appended, never
# prefixed: many callers test result.startswith("FAILED:").
FAILURE_TAG_RE = re.compile(
    r"\[failure class: (transient|approach|policy); reason: ([a-z][a-z0-9_]*)\]"
)


def failure_class_for(reason: str | None) -> str:
    return REASON_CLASSES.get(reason or "", DEFAULT_FAILURE_CLASS)


def closed_reason(code: str | None) -> str:
    """Return `code` when it is a listed reason, else UNLISTED_REASON."""
    return code if isinstance(code, str) and code in REASON_CLASSES else UNLISTED_REASON


def failure_tag(failure_class: str, reason: str) -> str:
    return f"[failure class: {failure_class}; reason: {closed_reason(reason)}]"


_CLASS_NOTES = {
    "transient": ("Failure class: transient (reason `{reason}`). The same call "
                  "may succeed if you try it once more."),
    "approach": ("Failure class: approach (reason `{reason}`). The same call "
                 "will fail again: change the arguments, use a different tool, "
                 "or report the failure."),
    "policy": ("Failure class: policy (reason `{reason}`). A guard refused this "
               "on purpose. Do not retry it, do not get the same thing another "
               "way (another tool, place or agent), and do not propose a code "
               "change to remove the guard. Tell the user what was refused."),
}


def failure_class_note(failure_class: str, reason: str) -> str:
    note = _CLASS_NOTES.get(failure_class, _CLASS_NOTES[DEFAULT_FAILURE_CLASS])
    return note.format(reason=closed_reason(reason))


@dataclass(frozen=True)
class ToolOutcome:
    ok: bool
    error: str | None       # short reason, None when ok
    body_failure: bool      # True when a JSON body said ok:false / error
    # WS-38 2A: None when ok. `reason` is always a REASON_CLASSES key.
    failure_class: str | None = None
    reason: str | None = None


def _failed(error: str, body_failure: bool, reason: str) -> ToolOutcome:
    reason = closed_reason(reason)
    return ToolOutcome(ok=False, error=error[:300], body_failure=body_failure,
                       failure_class=failure_class_for(reason), reason=reason)


def _transport_reason(tool_name: str, result_str: str) -> str:
    if result_str.startswith("Unknown tool "):
        return "unknown_tool"
    if result_str.startswith(f"Tool '{tool_name}' is not available"):
        return "tool_not_available"
    detail = result_str[len(f"{tool_name} failed:"):].strip()
    lowered = detail.lower()
    for phrase, reason in _TRANSPORT_PHRASES:
        if phrase in lowered:
            return reason
    head = detail.split()[0].rstrip(".") if detail else ""
    if head in REASON_CLASSES:
        return head
    # SkillRegistry reports a contained exception as "<tool> failed: <Class>."
    if _EXCEPTION_NAME_RE.fullmatch(detail):
        return "tool_exception"
    return UNLISTED_REASON


def classify_tool_result(tool_name: str, result_str: str, *,
                         failure_category: str | None = None) -> ToolOutcome:
    """Classify one tool call's result string. Never raises.

    Rules, in order — do not reorder, and do not require an explicit
    `ok: true` in rule 3: many tools return bare data with no `ok`/`error`
    key at all (e.g. {"stat": [...]}), and treating an absent key as
    failure would break every one of them.

    `failure_category` is the registry's closed category for this call when
    it has one; it decides the reason ahead of anything read from the text.
    """
    # Rule 1 — transport-level failure prefixes.
    if (
        result_str.startswith(f"{tool_name} failed:")
        or result_str.startswith("Unknown tool ")
        or result_str.startswith(f"Tool '{tool_name}' is not available")
    ):
        return _failed(result_str, False,
                       failure_category or _transport_reason(tool_name, result_str))

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
            reason = failure_category
            if reason not in REASON_CLASSES and isinstance(body_error, str):
                match = _CODE_RE.fullmatch(body_error.strip())
                reason = match.group(0) if match else None
            return _failed(error, True, reason or UNLISTED_REASON)

    # Rule 3 — everything else (non-JSON text, JSON arrays, JSON objects
    # with no ok/error key, or a JSON object explicitly ok=True).
    return ToolOutcome(ok=True, error=None, body_failure=False)
