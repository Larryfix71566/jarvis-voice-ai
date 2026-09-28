"""Shared vision-profile resolution for screen and shared-content analysis."""
from __future__ import annotations

import os
from typing import Any

from mcp_servers.mcp_screen.logic import (
    NoVisionProfileError,
    _default_vision_client,
    _resolve_vision_profile,
)


def resolve_vision_profile(registry: dict[str, Any] | None = None) -> dict[str, Any]:
    """Resolve the configured vision profile without capturing a screen."""
    return _resolve_vision_profile(registry)


def build_vision_client(profile: dict[str, Any]) -> tuple[Any, str]:
    """Build the existing OpenAI-compatible client for a resolved profile."""
    return _default_vision_client(profile)


def profile_summary(profile: dict[str, Any]) -> dict[str, str]:
    """Safe metadata for UI disclosure; never returns keys, URLs or prompts."""
    return {"id": str(profile.get("id", profile.get("model", "vision")))[:120],
            "label": str(profile.get("label", profile.get("model", "Vision model")))[:120]}


def resolve_vision_execution_route(*, routing_enabled: bool):
    """Resolve one immutable route snapshot for shared-content analysis.

    With model routing enabled, honor the configured vision workload route.
    With it disabled, retain the existing key-present vision-profile choice
    and its direct-API behavior, but represent it through the common route
    contract so policy, capability, billing, and execution remain consistent.
    """
    from jarvis.model_routing import resolve_model_route, resolve_model_route_checked

    if routing_enabled:
        return resolve_model_route_checked("vision")
    profile = resolve_vision_profile()
    return resolve_model_route(
        "vision", explicit_profile=str(profile["name"]), explicit_route="direct_api",
    )


def execution_route_summary(resolved: Any) -> dict[str, str]:
    """Return the exact selected model and route for the approval UI."""
    route = resolved.route
    return {
        "id": str(resolved.identity or f"{route.name}:{resolved.model}")[:120],
        "label": f"{resolved.model} via {route.name} ({route.billing})"[:120],
    }
