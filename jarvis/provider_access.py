"""Operator-owned LLM billing policy, independent of provider wire formats.

The opt-in retirement mode is deliberately enforced at API construction as
well as route selection. It never turns a missing subscription into permission
to buy inference elsewhere. Speech, search and other non-LLM services are not
covered by this policy.
"""
from __future__ import annotations

import os
import hashlib
import json
from collections.abc import Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from urllib.parse import urlsplit

ACCESS_MODE_ENV = "JARVIS_LLM_ACCESS_MODE"
SUBSCRIPTION_ROUTES = frozenset({"subscription", "codex_subscription", "local"})
_api_request = ContextVar("authorized_openrouter_request", default=None)


class ProviderAccessError(ValueError):
    """A payload-free refusal before inference client construction."""


def access_mode(environ: Mapping[str, str] | None = None) -> str:
    mode = (os.environ.get(ACCESS_MODE_ENV, "legacy") if environ is None
            else environ.get(ACCESS_MODE_ENV, "legacy"))
    if mode not in {"legacy", "subscription_only", "direct_apis_disabled"}:
        raise ProviderAccessError("invalid LLM access mode; inference is unavailable")
    return mode


def subscription_only(environ: Mapping[str, str] | None = None) -> bool:
    return access_mode(environ) == "subscription_only"


def selective_api_policy(mode: str | None = None) -> bool:
    return access_mode() == "direct_apis_disabled" or (
        mode is not None and access_mode({ACCESS_MODE_ENV: mode}) == "direct_apis_disabled")


def _openrouter_endpoint(provider, base_url) -> bool:
    # Match the actual destination, never a model name, SDK or provider label.
    if provider not in {None, "openrouter"} or not isinstance(base_url, str):
        return False
    try:
        url = urlsplit(base_url)
        return (url.scheme == "https" and url.netloc == "openrouter.ai"
                and url.path in {"/api/v1", "/api/v1/"}
                and not url.query and not url.fragment)
    except ValueError:
        return False


def require_api_access(mode: str | None = None, *, provider=None, base_url=None) -> None:
    """Guard API destinations; protocol compatibility grants no billing permission."""
    if subscription_only() or (mode is not None and subscription_only({ACCESS_MODE_ENV: mode})):
        raise ProviderAccessError(
            "subscription-only mode prohibits LLM API inference; no paid fallback was used"
        )
    if selective_api_policy(mode) and not _openrouter_endpoint(provider, base_url):
        raise ProviderAccessError(
            "direct provider APIs are disabled; only an explicit verified OpenRouter endpoint is eligible"
        )


def _request_digest(arguments):
    try:
        return hashlib.sha256(json.dumps(arguments, sort_keys=True, ensure_ascii=True,
            allow_nan=False, separators=(",", ":")).encode()).digest()
    except (TypeError, ValueError, RecursionError):
        raise ProviderAccessError("unverifiable API request payload") from None


@contextmanager
def validated_api_request(resolved, policy, arguments):
    """Scope one already privacy-validated payload; never a route/source grant."""
    if not selective_api_policy() or resolved.route.name in SUBSCRIPTION_ROUTES:
        yield
        return
    from jarvis.privacy_policy import DataPolicy, assert_route_allowed
    require_api_access(provider=resolved.provider, base_url=resolved.base_url)
    if type(policy) is not DataPolicy or policy.level != "approved_external":
        raise ProviderAccessError("OpenRouter requires an approved external source policy")
    assert_route_allowed(resolved.route, policy)
    admission = {"endpoint": resolved.base_url.rstrip("/"),
                 "digest": _request_digest(arguments), "active": True, "used": False}
    token = _api_request.set(admission)
    try:
        yield
    finally:
        # Copied ContextVars in child tasks must not keep authority alive.
        admission["active"] = False
        _api_request.reset(token)


def require_api_request(arguments, *, provider=None, base_url=None):
    require_api_access(provider=provider, base_url=base_url)
    if selective_api_policy():
        admission = _api_request.get()
        if (admission is None or not admission["active"] or admission["used"]
                or admission["endpoint"] != base_url.rstrip("/")
                or admission["digest"] != _request_digest(arguments)):
            raise ProviderAccessError("OpenRouter request lacks exact validated source-policy admission")
        admission["used"] = True


def require_route_access(route: str, *, fallback_routes=(), provider=None,
                         base_url=None, resolved=False) -> None:
    if subscription_only() and (
        route not in SUBSCRIPTION_ROUTES or fallback_routes
    ):
        raise ProviderAccessError(
            "subscription-only mode requires a subscription/local route with no fallback"
        )
    if selective_api_policy():
        if fallback_routes or route not in SUBSCRIPTION_ROUTES | {"direct_api"}:
            raise ProviderAccessError("direct provider APIs are disabled; implicit fallback is prohibited")
        if resolved and route == "direct_api":
            require_api_access(provider=provider, base_url=base_url)


def require_voice_readiness(mode: str | None = None) -> None:
    """Never instantiate an API voice client while native voice is unverified."""
    if subscription_only() or (mode is not None and subscription_only({ACCESS_MODE_ENV: mode})):
        raise ProviderAccessError(
            "subscription voice streaming and tools are not verified; voice is unavailable "
            "and no API fallback was used"
        )
    if selective_api_policy(mode):
        raise ProviderAccessError(
            "voice requires an eligible full-context route; direct APIs are disabled and no fallback was used"
        )
