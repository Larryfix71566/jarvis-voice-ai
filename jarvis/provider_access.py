"""Operator-owned LLM billing policy, independent of provider wire formats.

The opt-in retirement mode is deliberately enforced at API construction as
well as route selection. It never turns a missing subscription into permission
to buy inference elsewhere. Speech, search and other non-LLM services are not
covered by this policy.
"""
from __future__ import annotations

import os
from collections.abc import Mapping

ACCESS_MODE_ENV = "JARVIS_LLM_ACCESS_MODE"
SUBSCRIPTION_ROUTES = frozenset({"subscription", "codex_subscription", "local"})


class ProviderAccessError(ValueError):
    """A payload-free refusal before inference client construction."""


def access_mode(environ: Mapping[str, str] | None = None) -> str:
    mode = (os.environ.get(ACCESS_MODE_ENV, "legacy") if environ is None
            else environ.get(ACCESS_MODE_ENV, "legacy"))
    if mode not in {"legacy", "subscription_only"}:
        raise ProviderAccessError("invalid LLM access mode; inference is unavailable")
    return mode


def subscription_only(environ: Mapping[str, str] | None = None) -> bool:
    return access_mode(environ) == "subscription_only"


def require_api_access(mode: str | None = None) -> None:
    """Guard every legacy API path, including OpenRouter and unknown proxies."""
    if subscription_only() or (mode is not None and subscription_only({ACCESS_MODE_ENV: mode})):
        raise ProviderAccessError(
            "subscription-only mode prohibits LLM API inference; no paid fallback was used"
        )


def require_route_access(route: str, *, fallback_routes=()) -> None:
    if subscription_only() and (
        route not in SUBSCRIPTION_ROUTES or fallback_routes
    ):
        raise ProviderAccessError(
            "subscription-only mode requires a subscription/local route with no fallback"
        )


def require_voice_readiness(mode: str | None = None) -> None:
    """Never instantiate an API voice client while native voice is unverified."""
    if subscription_only() or (mode is not None and subscription_only({ACCESS_MODE_ENV: mode})):
        raise ProviderAccessError(
            "subscription voice streaming and tools are not verified; voice is unavailable "
            "and no API fallback was used"
        )
