"""Voice-safe model route preference tool.

Route changes use the same draft/confirm boundary as the native console. A
spoken request can create a bounded draft, but it cannot silently persist a
provider or billing change.
"""
from __future__ import annotations

from typing import Any

from jarvis.model_preferences import ModelPreferenceError, confirm_preference, stage_preference


MODEL_ROUTE_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "model_route",
        "description": (
            "Draft or confirm a model access route for a workload. First draft the "
            "choice; only confirm after the user explicitly approves the exact choice."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "workload": {"type": "string"},
                "profile": {"type": "string"},
                "route": {"type": "string", "enum": [
                    "direct_api", "subscription", "codex_subscription", "saygm", "local"
                ]},
                "privacy": {"type": "string", "enum": [
                    "approved_external", "confidential", "local_only"
                ]},
                "confirm": {"type": "boolean"},
                "draft_id": {"type": ["string", "null"]},
            },
            "required": ["workload", "profile", "route", "confirm"],
        },
    },
}


async def handle_model_route(arguments: dict[str, Any]) -> str:
    workload = str(arguments.get("workload") or "").strip()
    profile = str(arguments.get("profile") or "").strip()
    route = str(arguments.get("route") or "").strip()
    privacy = arguments.get("privacy")
    privacy = str(privacy).strip() if privacy is not None else None
    try:
        if bool(arguments.get("confirm")):
            draft_id = str(arguments.get("draft_id") or "").strip()
            if not draft_id:
                return "I need the draft ID before I can confirm that route."
            result = confirm_preference(draft_id)
            return (f"Saved {result['workload']} on {result['route']} using "
                    f"{result['profile']} with {result['privacy']} privacy.")
        draft = stage_preference(workload, profile, route, privacy)
        return (f"I drafted {draft['workload']} on {draft['route']} using "
                f"{draft['profile']} with {draft['privacy']} privacy. "
                f"The draft expires in ten minutes. Ask me to confirm draft {draft['draft_id']}.")
    except ModelPreferenceError as exc:
        return f"I could not change that model route: {exc}."


def build_model_route_tool():
    return MODEL_ROUTE_TOOL_SCHEMA, handle_model_route
