"""Supervisor-facing Command Console action handler.

The handler is deliberately transport-agnostic: the pipeline supplies the
current inventory and a send callback. It performs no repository, credential,
or memory mutation.
"""
from __future__ import annotations

from typing import Any, Callable
import uuid
import inspect
import json

from jarvis.bot.console_protocol import validate_request, response

CONSOLE_ACTION_SCHEMA = {
    "type": "function",
    "function": {
        "name": "console_action",
        "description": "Change the visible Mortimer Command Console view or result selection.",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "description": "A registered console action."},
                "target": {"type": ["string", "null"]},
                "args": {"type": "object"},
            },
            "required": ["action"],
        },
    },
}


def build_console_action_tool(send: Callable[[dict], Any], *, session_id: str,
                              generation: str, revision: int | Callable[[], int] = 0,
                              await_result: Callable[[str], Any] | None = None,
                              is_ready: Callable[[], bool] | None = None):
    async def handler(arguments: dict) -> str:
        action = arguments.get("action")
        if is_ready is not None and not is_ready():
            return "The Command Console is not ready on this client yet."
        current_revision = revision() if callable(revision) else revision
        message = {"type": "console/request", "version": 1,
                   "session_id": session_id, "generation": generation,
                   "request_id": str(uuid.uuid4()), "revision": current_revision,
                   "action": action, "target": arguments.get("target"),
                   "args": arguments.get("args", {})}
        try:
            validate_request(message)
        except ValueError as exc:
            return f"Console action rejected: {exc}."
        sent = send(message)
        if inspect.isawaitable(sent):
            await sent
        if await_result is None:
            return f"Console action {action} submitted."
        result = await await_result(message["request_id"])
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
            if action == "inventory" and isinstance(data, dict):
                encoded = json.dumps(data, separators=(",", ":"), ensure_ascii=True)
                return f"{summary or 'Console inventory ready.'} {encoded[:12000]}"
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
