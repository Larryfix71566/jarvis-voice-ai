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
