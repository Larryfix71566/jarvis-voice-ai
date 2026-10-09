"""Supervisor-facing Command Console action handler.

The handler is deliberately transport-agnostic: the pipeline supplies the
current inventory and a send callback. It performs no repository, credential,
or memory mutation.
"""
from __future__ import annotations

from typing import Any, Callable
import asyncio
import uuid
import inspect
import json
import re
import unicodedata

from pathlib import Path

from jarvis.bot.console_protocol import validate_request, response

# MORTIMER_WORKFLOW_VIEWER_PLAN.md piece 3: the view_set modes, from the one
# file MortimerHost's coordinator test also reads. Until 2026-09-25 nothing
# the Supervisor saw named them, so "show me the workflows" could not be
# resolved to a mode by voice.
VIEW_MODES_PATH = Path(__file__).resolve().parents[2] / "config" / "console_view_modes.json"
VIEW_SET_MODES: tuple[str, ...] = tuple(json.loads(VIEW_MODES_PATH.read_text(encoding="utf-8"))["view_set"])

CONSOLE_ACTION_SCHEMA = {
    "type": "function",
    "function": {
        "name": "console_action",
        "description": (
            "Navigate Mortimer's Command Console, results, Atlas, and Skills. "
            "action view_set switches the main view: args.mode is one of "
            + ", ".join(VIEW_SET_MODES)
            + " (workflows is the read-only gallery of Larry's workflows). "
            "Skills actions search/filter the library, refresh its catalog, open "
            "listed skill, process-step, run, or example details, and transfer "
            "selected skill details to the supporting display. skill_creator_open "
            "only opens the composer. skill_request_preview followed by "
            "skill_request starts a sandbox draft. Voice cannot publish, activate, "
            "or roll back a skill; opening a review PR requires native exact-diff "
            "review. display_show puts content on the other (supporting) display: "
            "target is a result id from the inventory, or memory_graph, skills or "
            "workflows; optional args.screen_id is a screens id from the inventory. "
            "It returns only after the app confirms the content is showing on that "
            "screen; say it is there only when the result says so, and relay its "
            "reason when it fails. "
            "result_select, result_close, result_pin, result_unpin and compare_set "
            "take a result id, or the Recents number or subject Larry said "
            "(\"3\", \"Folly Beach weather\"); the inventory's results list "
            "each number, kind and subject. When the result is needs_choice, "
            "nothing changed: ask Larry which of the listed choices he means, "
            "by number. For result commands, read inventory with args.scope='results' "
            "before using a number or subject, and pass "
            "that inventory's revision as inventory_revision. Numbers refer to that "
            "observed list, never a newer list. compare_set also requires secondary_target."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "description": "A registered console action."},
                "target": {"type": ["string", "null"]},
                "secondary_target": {"type": ["string", "null"]},
                "inventory_revision": {"type": "integer", "minimum": 0,
                    "description": "The revision returned by the inventory you observed; required for a spoken number or subject."},
                "args": {"type": "object"},
            },
            "required": ["action"],
        },
    },
}


_RESULT_REFERENCE_ACTIONS = frozenset({
    "result_select", "result_close", "result_pin", "result_unpin", "compare_set",
})
_INVENTORY_SCOPES = frozenset({
    "all", "results", "panels", "screens", "nodes", "sources", "groups", "attachments",
})
_INVENTORY_SCOPE_FIELDS = {
    "panels": {"panels", "focused_panel_id"},
    "screens": {"screens", "supporting_display"},
    "nodes": {"nodes"}, "sources": {"sources"}, "groups": {"groups"},
    "attachments": {"attachments"},
}
_RESULT_FILLERS = frozenset({
    "the", "a", "an", "of", "for", "in", "at", "on", "to", "my", "that", "this",
    "result", "results", "card", "one", "show", "open", "again", "number", "no",
})
_RESULT_NUMBERS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
}


def _canonical_uuid(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        return str(uuid.UUID(value))
    except (ValueError, TypeError, AttributeError):
        return None


def _reference_words(value: str, *, fillers: bool = True) -> list[str]:
    folded = unicodedata.normalize("NFKD", value.casefold())
    folded = "".join(char for char in folded if not unicodedata.combining(char))
    words = re.sub(r"[^a-z0-9#]+", " ", folded).strip().split()
    return [w for w in words if w not in _RESULT_FILLERS] if fillers else words


def _resolve_observed_reference(reference: str, snapshot: dict) -> tuple[str | None, str | None]:
    """Resolve only the bounded, public entries actually disclosed by inventory.

    This snapshot is not a second state owner: native revision validation still
    decides whether the UUID action may run. Async inventory updates do not alter
    what the model observed, so an old number cannot acquire a new meaning.
    """
    rows = [row for row in snapshot.get("results", [])
            if isinstance(row, dict) and _canonical_uuid(row.get("id"))
            and type(row.get("number")) is int and row["number"] > 0]
    raw_words = _reference_words(reference, fillers=False)
    numbered = raw_words[1:] if raw_words and raw_words[0] in {"number", "no"} else raw_words
    number = None
    if len(numbered) == 1:
        word = numbered[0].removeprefix("#")
        number = int(word) if word.isdecimal() else _RESULT_NUMBERS.get(word)
    if number is not None:
        matches = [row for row in rows if row["number"] == number]
    else:
        words = _reference_words(reference)
        matches = [row for row in rows if words and set(words).issubset(set(
            _reference_words(" ".join(str(row.get(field) or "") for field in ("kind", "subject", "title")))))]
        exact = [row for row in matches if
                 [w for w in words if w not in set(_reference_words(str(row.get("kind") or "")))]
                 == _reference_words(str(row.get("subject") or ""))]
        if len(exact) == 1:
            matches = exact
    if len(matches) == 1:
        return _canonical_uuid(matches[0]["id"]), None
    if not matches:
        return None, "That result was not in the observed Recents list. Ask for inventory, then ask which result to use."
    labels = "; ".join(
        f"{row['number']}  {str(row.get('kind') or '')[:40]} · {str(row.get('subject') or row.get('title') or '')[:80]}"
        for row in matches[:10]
    )
    return None, f"More than one result matches. Nothing changed. Ask which one, by number. Choices: {labels}"


def _disclosed_inventory(data: dict, *, scope: str | None = None) -> tuple[dict, str] | None:
    """Keep exactly what is returned, without saving an undisclosed truncated tail."""
    if type(data.get("revision")) is not int or data["revision"] < 0:
        return None
    try:
        copied = json.loads(json.dumps(data, ensure_ascii=True))
        encoded = json.dumps(copied, separators=(",", ":"), ensure_ascii=True)
    except (ValueError, TypeError, OverflowError):
        return None
    prior_omitted = copied.get("results_omitted", 0)
    prior_fields = copied.get("omitted_fields", [])
    if (type(prior_omitted) is not int or prior_omitted < 0
            or not isinstance(prior_fields, list)
            or any(not isinstance(field, str) for field in prior_fields)):
        return None
    if scope != "results" and len(encoded) <= 12000:
        return copied, encoded
    rows = copied.get("results")
    if not isinstance(rows, list):
        return None
    if scope in _INVENTORY_SCOPE_FIELDS:
        requested_fields = _INVENTORY_SCOPE_FIELDS[scope]
        if not requested_fields.intersection(copied):
            return None  # This native client supplies no data for that scope.
        fields = requested_fields | {"revision"}
        copied = {key: value for key, value in copied.items() if key in fields} | {
            "scope": scope, "omitted_fields": sorted(set(prior_fields) | (set(data) - fields - {
                "scope", "omitted_fields", "results_omitted"})),
        }
        encoded = json.dumps(copied, separators=(",", ":"), ensure_ascii=True)
        return (copied, encoded) if len(encoded) <= 12000 else None
    # The existing results scope projects the actual native inventory; it
    # does not depend on native filtering (its inventory currently ignores
    # scope). Large default disclosures use this explicitly labelled fallback.
    fields = {"revision", "mode", "active_result_id", "comparison"}
    row_fields = {"id", "number", "kind", "subject", "title", "pinned", "unread"}
    projected = [{key: value for key, value in row.items() if key in row_fields}
                 for row in rows if isinstance(row, dict)]
    numbered = [row for row in projected if type(row.get("number")) is int]
    older = [row for row in projected if type(row.get("number")) is not int]
    copied = {key: value for key, value in copied.items() if key in fields} | {
        "scope": "results", "results": numbered,
        "results_omitted": prior_omitted + len(older),
        "omitted_fields": sorted(set(prior_fields) | (set(data) - fields - {
            "results", "scope", "omitted_fields", "results_omitted"})),
    }
    encoded = json.dumps(copied, separators=(",", ":"), ensure_ascii=True)
    # Never omit a numbered row: doing so would make subject ambiguity and
    # the highest visible numbers impossible to resolve truthfully.
    if len(encoded) > 12000:
        return None
    for row in older:
        copied["results"].append(row)
        copied["results_omitted"] -= 1
        trial = json.dumps(copied, separators=(",", ":"), ensure_ascii=True)
        if len(trial) > 12000:
            copied["results"].pop()
            copied["results_omitted"] += 1
            break
        encoded = trial
    encoded = json.dumps(copied, separators=(",", ":"), ensure_ascii=True)
    return copied, encoded


def build_console_action_tool(send: Callable[[dict], Any], *, session_id: str,
                              generation: str, revision: int | Callable[[], int] = 0,
                              await_result: Callable[[str], Any] | None = None,
                              is_ready: Callable[[], bool] | None = None):
    observed_inventory: dict | None = None

    async def handler(arguments: dict) -> str:
        nonlocal observed_inventory
        action = arguments.get("action")
        if not isinstance(action, str):
            return "Console action rejected: action must be a string."
        args = arguments.get("args", {})
        inventory_scope = args.get("scope") if isinstance(args, dict) else None
        if (action == "inventory" and inventory_scope not in (None, "")
                and (not isinstance(inventory_scope, str) or inventory_scope not in _INVENTORY_SCOPES)):
            return "Console action rejected: unsupported inventory scope. Use all, results, panels, screens, nodes, sources, groups or attachments."
        if is_ready is not None and not is_ready():
            return "The Command Console is not ready on this client yet."
        current_revision = revision() if callable(revision) else revision
        requested_revision = arguments.get("inventory_revision")
        if requested_revision is not None:
            if type(requested_revision) is not int or requested_revision < 0:
                return "Console action rejected: inventory_revision must be a non-negative integer."
            # An explicit observation binds UUID requests too. Silently
            # replacing it with latest would defeat the native stale check.
            current_revision = requested_revision
        target = arguments.get("target")
        secondary = arguments.get("secondary_target")
        references = [target] + ([secondary] if action == "compare_set" else [])
        if action in _RESULT_REFERENCE_ACTIONS and any(
            isinstance(ref, str) and _canonical_uuid(ref) is None for ref in references
        ):
            if (observed_inventory is None or type(requested_revision) is not int
                    or requested_revision != observed_inventory["revision"]):
                return "The Recents list used for that number or subject is not available. Nothing changed. Ask for inventory before choosing a result."
            current_revision = observed_inventory["revision"]
            resolved = []
            for ref in references:
                canonical = _canonical_uuid(ref)
                if canonical is None:
                    if not isinstance(ref, str):
                        return "Console action rejected: a result reference is required."
                    canonical, refusal = _resolve_observed_reference(ref, observed_inventory)
                    if refusal:
                        return refusal
                resolved.append(canonical)
            target = resolved[0]
            secondary = resolved[1] if len(resolved) > 1 else secondary
        message = {"type": "console/request", "version": 1,
                   "session_id": session_id, "generation": generation,
                   "request_id": str(uuid.uuid4()), "revision": current_revision,
                   "action": action, "target": target,
                   "args": arguments.get("args", {})}
        if secondary is not None:
            message["secondary_target"] = secondary
        try:
            validate_request(message)
        except ValueError as exc:
            return f"Console action rejected: {exc}."
        # Production registers its runtime-owned Future synchronously here,
        # before send can deliver an immediate acknowledgement. Older async
        # injected seams still execute when awaited after send.
        pending = await_result(message["request_id"]) if await_result is not None else None
        try:
            sent = send(message)
            if inspect.isawaitable(sent):
                await sent
            if await_result is None:
                return f"Console action {action} submitted."
            try:
                result = await asyncio.wait_for(pending, timeout=5.0) if inspect.isawaitable(pending) else pending
            except asyncio.TimeoutError:
                result = None
        finally:
            if isinstance(pending, asyncio.Future) and not pending.done():
                pending.cancel()
            elif inspect.iscoroutine(pending):
                pending.close()
        if not isinstance(result, dict):
            return "I couldn't confirm that console action."
        status = result.get("status")
        summary = str(result.get("summary", ""))[:240]
        if status in {"ok", "noop", "needs_choice", "pending_user"}:
            # Inventory is the one read response the Supervisor needs to
            # resolve ordinals, duplicate titles and dynamic targets. Return
            # only the bounded, privacy-safe data supplied by the native
            # client; all other actions retain the concise spoken summary.
            data = result.get("data")
            choices = result.get("choices")
            if status == "needs_choice" and isinstance(choices, list) and choices:
                # CC7a.3: an ambiguous Recents number or subject. Return the
                # bounded labels so Mortimer can ask which one, by number.
                labels = "; ".join(str(c.get("label", ""))[:120] for c in choices[:10]
                                   if isinstance(c, dict))
                return f"{summary or 'More than one result matches.'} Choices: {labels}"
            if action == "inventory" and isinstance(data, dict):
                disclosed = _disclosed_inventory(data, scope=inventory_scope)
                if disclosed is None:
                    return "The requested console inventory is unavailable or cannot be disclosed within its size limit. Nothing changed. Use a known result UUID or choose it in the app."
                snapshot, encoded = disclosed
                if isinstance(snapshot.get("results"), list):
                    observed_inventory = snapshot
                return f"{summary or 'Console inventory ready.'} {encoded}"
            return summary or f"Console action {action} acknowledged."
        if status == "unsupported":
            return summary or "That console action is unavailable here."
        return summary or "The console could not apply that action."
    return CONSOLE_ACTION_SCHEMA, handler


def handle_console_request(message: dict[str, Any], *, inventory: Callable[[], dict],
                           apply: Callable[[dict], tuple[str, str]] | None = None) -> dict:
    request = validate_request(message)
    current = inventory()
    if not isinstance(current, dict) or not isinstance(current.get("revision"), int):
        return response(request_id=request["request_id"], session_id=request["session_id"],
                        generation=request["generation"], status="error", code="inventory_unavailable",
                        summary="Console inventory is unavailable.")
    if request["revision"] != current["revision"]:
        return response(request_id=request["request_id"], session_id=request["session_id"],
                        generation=request["generation"], status="error", code="stale_selection",
                        summary="The console changed; please choose the item again.")
    if request["action"] == "inventory":
        return response(request_id=request["request_id"], session_id=request["session_id"],
                        generation=request["generation"], status="ok", code="inventory",
                        summary="Console inventory ready.") | {"data": current}
    if apply is None:
        return response(request_id=request["request_id"], session_id=request["session_id"],
                        generation=request["generation"], status="unsupported", code="not_wired",
                        summary="That console action is not available yet.")
    status, summary = apply(request)
    return response(request_id=request["request_id"], session_id=request["session_id"],
                    generation=request["generation"], status=status, code=status,
                    summary=summary)
