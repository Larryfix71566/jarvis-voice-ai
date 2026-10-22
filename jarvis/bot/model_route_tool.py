"""Voice-safe model route preference tool.

Voice may preview supported selections only. LLM-generated confirmation is
refused until a host-owned human admission channel exists. Harness changes
are unavailable across both voice and native draft/confirm entry points.
"""
from __future__ import annotations

from typing import Any

from jarvis.model_preferences import ModelPreferenceError, stage_preference


MODEL_ROUTE_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "model_route",
        "description": (
            "Preview a model access route for a workload. Confirmation through this voice tool is unavailable; "
            "the user must review a supported selection in Mortimer Model Access. Harness switching is blocked."
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
            return ("Voice confirmation is unavailable: an LLM argument is not a host-owned user approval. "
                    "Review a supported selection in Mortimer Model Access. No preference was changed.")
        draft = stage_preference(workload, profile, route, privacy)
        proposal = draft["proposal"]
        current, candidate = proposal["current"], proposal["candidate"]
        return (f"Configured selection: {current['model']} via {current['route']}. "
                f"Proposed selection: {candidate['model']} via {candidate['route']} "
                f"with {candidate['privacy']} privacy. Eligibility and active runtime are unverified. "
                "Review and confirm a supported selection in Mortimer Model Access; "
                "this voice draft cannot authorize a model change.")
    except ModelPreferenceError as exc:
        return f"I could not change that model route: {exc}."


def build_model_route_tool():
    return MODEL_ROUTE_TOOL_SCHEMA, handle_model_route
