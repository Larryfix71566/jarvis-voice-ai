"""Strict, transport-neutral Command Console protocol primitives."""
from __future__ import annotations

import math
import uuid
from typing import Any

MAX_SUMMARY = 240
MAX_MESSAGE = 32 * 1024
ALLOWED_ACTIONS = frozenset({
    "inventory", "help", "view_set", "result_select", "result_close", "result_pin",
    "result_unpin", "result_next", "result_previous", "result_mode", "compare_set",
    "compare_end", "compare_side", "content_scroll", "source_select", "source_open",
    "source_inspector", "image_select", "atlas_fit", "atlas_arrange", "atlas_zoom",
    "atlas_pan", "atlas_move", "group_create", "group_rename", "group_assign",
    "group_remove_card", "group_dissolve", "graph_search", "graph_focus", "graph_select",
    "graph_select_edge", "graph_back", "graph_fit", "graph_reset", "graph_retry",
    "graph_zoom", "graph_pan", "graph_filter", "graph_group", "graph_path",
    "graph_path_clear", "graph_inspector", "graph_original", "graph_center",
    "graph_move_node", "panel_detach", "panel_move", "panel_return", "panel_close",
    "panel_focus", "panel_fullscreen", "panels_return_all", "sidecar_width", "sidecar_text",
    "sidecar_scroll_tabs", "appearance_set", "console_caption", "console_status",
    "wave_tuning_open", "wave_tuning_set", "reset_layout", "share_preview", "share_copy",
    "share_save", "share_picker", "share_cancel", "share_source", "input_paste",
    "input_choose", "input_remove", "input_clear", "input_preview", "input_question",
    "input_cancel", "input_new_conversation", "export_folder_choose", "export_folder_clear",
    "shared_content",
})

# The action enum is closed, and so is each action's argument object. Keeping
# this table beside the validator prevents a new UI control from smuggling an
# unreviewed field across the voice/native boundary.
ACTION_ARG_FIELDS: dict[str, frozenset[str]] = {
    "inventory": frozenset({"scope", "cursor"}),
    "view_set": frozenset({"mode"}),
    "result_mode": frozenset({"mode"}),
    "compare_side": frozenset({"side"}),
    "content_scroll": frozenset({"panel", "direction", "viewport"}),
    "source_select": frozenset({"source", "index"}),
    "source_open": frozenset({"source", "index"}),
    "source_inspector": frozenset({"open"}),
    "image_select": frozenset({"index"}),
    "atlas_zoom": frozenset({"direction"}),
    "atlas_pan": frozenset({"direction"}),
    "atlas_move": frozenset({"relation", "row", "column"}),
    "group_create": frozenset({"name"}),
    "group_rename": frozenset({"name"}),
    "group_assign": frozenset({"group"}),
    "group_remove_card": frozenset({"group"}),
    "graph_search": frozenset({"query"}),
    "graph_focus": frozenset({"depth"}),
    "graph_filter": frozenset({"kind", "visible"}),
    "graph_group": frozenset({"collapsed"}),
    "graph_inspector": frozenset({"open"}),
    "graph_original": frozenset({"enabled"}),
    "graph_move_node": frozenset({"x", "y"}),
    "panel_move": frozenset({"screen_id"}),
    "panel_fullscreen": frozenset({"enabled"}),
    "sidecar_width": frozenset({"points"}),
    "sidecar_text": frozenset({"size"}),
    "sidecar_scroll_tabs": frozenset({"direction"}),
    "appearance_set": frozenset({"layout"}),
    "console_caption": frozenset({"expanded"}),
    "console_status": frozenset({"open"}),
    "wave_tuning_set": frozenset({"key", "value"}),
    "share_preview": frozenset({"format", "scope", "ordinal"}),
    "share_source": frozenset({"source", "index"}),
    "input_paste": frozenset({"format"}),
    "input_choose": frozenset({"format"}),
    "input_question": frozenset({"question"}),
    "input_new_conversation": frozenset({"confirmed"}),
    "shared_content": frozenset({"attachment_ids", "question"}),
}

# Keep the server boundary aligned with ConsoleActionRegistry's native
# validation. A target is an inventory identity, not a substitute for an
# enum-like argument; legacy callers may still supply the latter in target
# where the native coordinator explicitly supports that fallback.
REQUIRED_TARGET_ACTIONS = frozenset({
    "result_select", "result_close", "result_pin", "result_unpin", "result_mode",
    "compare_set", "group_rename", "group_assign", "group_remove_card",
    "group_dissolve", "atlas_move", "graph_focus", "graph_select",
    "graph_select_edge", "graph_filter", "graph_group", "graph_path",
    "graph_center", "graph_move_node", "panel_detach", "panel_move",
    "panel_return", "panel_close", "panel_focus", "panel_fullscreen",
    "input_remove",
})
REQUIRED_SECONDARY_TARGET_ACTIONS = frozenset({"compare_set", "graph_path"})

STRING_ARGUMENTS = frozenset({
    "scope", "cursor", "mode", "side", "panel", "direction", "source", "relation",
    "name", "group", "query", "kind", "screen_id", "key", "format", "question",
})
NUMBER_ARGUMENTS = frozenset({"viewport", "points", "x", "y", "value"})
BOOLEAN_ARGUMENTS = frozenset({"open", "visible", "collapsed", "enabled", "expanded", "confirmed"})
INTEGER_ARGUMENTS = frozenset({"index", "ordinal", "row", "column", "size", "layout", "depth"})


def _uuid(value: Any, field: str) -> str:
    try:
        parsed = uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError(f"{field} must be a UUID") from exc
    return str(parsed)


def validate_request(message: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize a console/request dictionary; never mutate input."""
    if not isinstance(message, dict) or set(message) - {
        "type", "version", "session_id", "generation", "request_id", "revision",
        "action", "target", "secondary_target", "args",
    }:
        raise ValueError("unknown console request field")
    if message.get("type") != "console/request" or message.get("version") != 1:
        raise ValueError("unsupported console request")
    if len(repr(message)) > MAX_MESSAGE:
        raise ValueError("console request exceeds size limit")
    action = message.get("action")
    if action not in ALLOWED_ACTIONS:
        raise ValueError("unsupported console action")
    revision = message.get("revision")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 0:
        raise ValueError("revision must be a non-negative integer")
    args = message.get("args", {})
    if not isinstance(args, dict):
        raise ValueError("args must be an object")
    allowed_args = ACTION_ARG_FIELDS.get(action, frozenset())
    if set(args) - allowed_args:
        raise ValueError("unknown console action argument")
    for field in ("target", "secondary_target"):
        value = message.get(field)
        if value is not None and not isinstance(value, str):
            raise ValueError(f"{field} must be a string or null")
        if isinstance(value, str) and (not value or len(value) > 120):
            raise ValueError(f"{field} exceeds its identity limit")
    if action in REQUIRED_TARGET_ACTIONS and not message.get("target"):
        raise ValueError("console action requires a target")
    if action in REQUIRED_SECONDARY_TARGET_ACTIONS and not message.get("secondary_target"):
        raise ValueError("console action requires a secondary target")
    if action == "atlas_move":
        has_relation = "relation" in args
        has_row = "row" in args
        has_column = "column" in args
        if has_relation == (has_row or has_column) or has_row != has_column:
            raise ValueError("atlas_move requires relation+secondary target or row+column")
        if has_relation and not message.get("secondary_target"):
            raise ValueError("atlas_move relation requires a secondary target")
    for value in args.values():
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("non-finite numeric argument")
        if isinstance(value, str) and len(value) > 2_000:
            raise ValueError("console action argument exceeds size limit")
        if isinstance(value, list):
            if not 1 <= len(value) <= 4:
                raise ValueError("console action array exceeds its item limit")
            if any(not isinstance(item, str) or len(item) > 120 for item in value):
                raise ValueError("console action array contains an invalid item")
    for key, value in args.items():
        if key in STRING_ARGUMENTS and not isinstance(value, str):
            raise ValueError(f"{key} must be a string")
        if key in NUMBER_ARGUMENTS and (isinstance(value, bool) or not isinstance(value, (int, float))):
            raise ValueError(f"{key} must be numeric")
        if key in BOOLEAN_ARGUMENTS and not isinstance(value, bool):
            raise ValueError(f"{key} must be boolean")
        if key in INTEGER_ARGUMENTS and (isinstance(value, bool) or not isinstance(value, int)):
            raise ValueError(f"{key} must be an integer")
    if action == "atlas_move":
        for key in ("row", "column"):
            if key in args and not 1 <= args[key] <= 100:
                raise ValueError("atlas_move row and column must be between 1 and 100")
    if action == "graph_search" and "query" in args and len(args["query"]) > 200:
        raise ValueError("graph_search query exceeds 200 characters")
    if action == "graph_focus" and "depth" in args and not 1 <= args["depth"] <= 4:
        raise ValueError("graph_focus depth must be between 1 and 4")
    result = dict(message)
    result.update(session_id=_uuid(message.get("session_id"), "session_id"),
                 generation=_uuid(message.get("generation"), "generation"),
                 request_id=_uuid(message.get("request_id"), "request_id"),
                 args=dict(args))
    return result


def response(*, request_id: str, session_id: str, generation: str,
             status: str, code: str, summary: str,
             choices: list[dict[str, str]] | None = None,
             data: dict[str, Any] | None = None) -> dict[str, Any]:
    if status not in {"ok", "noop", "needs_choice", "pending_user", "unsupported", "error"}:
        raise ValueError("invalid response status")
    summary = str(summary)
    result = {"type": "console/result", "version": 1,
            "session_id": _uuid(session_id, "session_id"),
            "generation": _uuid(generation, "generation"),
            "request_id": _uuid(request_id, "request_id"),
            "status": status, "code": str(code), "summary": summary[:MAX_SUMMARY]}
    if choices is not None:
        result["choices"] = [
            {"id": str(item.get("id", ""))[:120], "label": str(item.get("label", ""))[:120]}
            for item in choices[:10]
        ]
    if data is not None:
        result["data"] = data
    return result


def hello(*, session_id: str, generation: str,
          actions: list[str], input_profile: dict[str, str] | None = None) -> dict[str, Any]:
    """Build the bounded connection capability disclosure."""
    payload: dict[str, Any] = {
        "type": "console/hello", "version": 1,
        "session_id": _uuid(session_id, "session_id"),
        "generation": _uuid(generation, "generation"),
        "actions": [str(a)[:80] for a in actions[:100]],
        "input_types": ["text/plain", "image/png", "image/jpeg"],
    }
    if input_profile is not None:
        payload["input_profile"] = {
            "id": str(input_profile.get("id", ""))[:120],
            "label": str(input_profile.get("label", ""))[:120],
        }
    return payload


def validate_ready(message: dict[str, Any], *, session_id: str,
                   generation: str) -> dict[str, Any]:
    """Validate the client half of the console capability handshake."""
    allowed = {"type", "version", "session_id", "generation", "actions", "input_types"}
    if not isinstance(message, dict) or set(message) - allowed:
        raise ValueError("unknown console ready field")
    if message.get("type") != "console/ready" or message.get("version") != 1:
        raise ValueError("unsupported console ready")
    if _uuid(message.get("session_id"), "session_id") != _uuid(session_id, "session_id"):
        raise ValueError("stale console session")
    if _uuid(message.get("generation"), "generation") != _uuid(generation, "generation"):
        raise ValueError("stale console generation")
    actions = message.get("actions")
    input_types = message.get("input_types")
    if (not isinstance(actions, list) or len(actions) > 100 or
            not all(isinstance(item, str) and len(item) <= 80 for item in actions)):
        raise ValueError("invalid console actions")
    if (not isinstance(input_types, list) or len(input_types) > 8 or
            not all(isinstance(item, str) and len(item) <= 80 for item in input_types)):
        raise ValueError("invalid console input types")
    return {"type": "console/ready", "version": 1,
            "session_id": _uuid(session_id, "session_id"),
            "generation": _uuid(generation, "generation"),
            "actions": list(actions), "input_types": list(input_types)}


def validate_inventory(message: dict[str, Any], *, session_id: str,
                       generation: str) -> dict[str, Any]:
    """Validate a native-owned inventory snapshot.

    Inventory is deliberately a separate, client-to-server message.  It
    contains identifiers and bounded labels only; the server never receives
    result bodies, clipboard contents, paths, or image bytes through this
    path.  A snapshot is accepted only for the currently negotiated session.
    """
    allowed = {"type", "version", "session_id", "generation", "revision", "data"}
    if not isinstance(message, dict) or set(message) - allowed:
        raise ValueError("unknown console inventory field")
    if message.get("type") != "console/inventory" or message.get("version") != 1:
        raise ValueError("unsupported console inventory")
    if _uuid(message.get("session_id"), "session_id") != _uuid(session_id, "session_id"):
        raise ValueError("stale console session")
    if _uuid(message.get("generation"), "generation") != _uuid(generation, "generation"):
        raise ValueError("stale console generation")
    revision = message.get("revision")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 0:
        raise ValueError("revision must be a non-negative integer")
    data = message.get("data")
    if not isinstance(data, dict):
        raise ValueError("console inventory data must be an object")
    if len(repr(message)) > MAX_MESSAGE:
        raise ValueError("console inventory exceeds size limit")
    return {
        "type": "console/inventory", "version": 1,
        "session_id": _uuid(session_id, "session_id"),
        "generation": _uuid(generation, "generation"),
        "revision": revision, "data": data,
    }
