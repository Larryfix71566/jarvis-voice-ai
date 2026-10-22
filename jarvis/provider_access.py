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
from pathlib import Path

import yaml
from urllib.parse import urlsplit

ACCESS_MODE_ENV = "JARVIS_LLM_ACCESS_MODE"
SUBSCRIPTION_ROUTES = frozenset({"subscription", "codex_subscription", "local"})
_api_request = ContextVar("authorized_api_request", default=None)


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


def _endpoint_identity(base_url):
    """Exact HTTPS destination; no aliases, redirect hints or URL credentials."""
    if not isinstance(base_url, str) or any(ord(c) <= 32 for c in base_url):
        return None
    try:
        url = urlsplit(base_url)
        if (url.scheme != "https" or not url.hostname or url.netloc != url.hostname
                or url.query or url.fragment or "%" in url.path
                or any(segment in {".", ".."} for segment in url.path.split("/"))):
            return None
        return url.hostname, url.path.removesuffix("/")
    except ValueError:
        return None


def _eligible_api_endpoint(provider, base_url) -> bool:
    # This fixed, human-owned file is identity authority. Model profiles,
    # caller registry overrides and an OpenAI-compatible SDK are not.
    if provider in {"openai", "anthropic"}:
        return False
    if provider in {None, "saygm"}:
        from jarvis.saygm import validate_endpoint, SayGMError
        try:
            validate_endpoint(base_url)
            return True
        except SayGMError:
            pass
    identity = _endpoint_identity(base_url)
    if identity is None:
        return False
    host, _ = identity
    if any(host == domain or host.endswith("." + domain)
           for domain in ("openai.com", "anthropic.com")):
        return False
    try:
        registry = yaml.safe_load((Path(__file__).resolve().parents[1]
                                   / "config/model_endpoints.yaml").read_text())
        endpoints = registry["endpoints"]
        if not isinstance(endpoints, dict):
            return False
        matches = {entry.get("provider") for entry in endpoints.values()
                   if isinstance(entry, dict) and entry.get("kind", "api") == "api"
                   and _endpoint_identity(entry.get("base_url")) == identity
                   and isinstance(entry.get("provider"), str)}
        # Ambiguous identity fails closed, even if one label appears eligible.
        return (len(matches) == 1 and not matches & {"openai", "anthropic"}
                and (provider is None or provider in matches))
    except (OSError, ValueError, TypeError, KeyError, yaml.YAMLError):
        return False


def require_api_access(mode: str | None = None, *, provider=None, base_url=None) -> None:
    """Guard API destinations; protocol compatibility grants no billing permission."""
    if subscription_only() or (mode is not None and subscription_only({ACCESS_MODE_ENV: mode})):
        raise ProviderAccessError(
            "subscription-only mode prohibits LLM API inference; no paid fallback was used"
        )
    if selective_api_policy(mode) and not _eligible_api_endpoint(provider, base_url):
        raise ProviderAccessError(
            "direct OpenAI/Anthropic APIs are disabled; other APIs require a recognized endpoint identity"
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
    if type(policy) is not DataPolicy:
        raise ProviderAccessError("API request requires a validated source policy")
    assert_route_allowed(resolved.route, policy)
    # Only catalog-verified SAYGM can carry confidential data. A forged route
    # privacy label cannot promote another API or permit local-only content.
    if policy.level != "approved_external" and not (
        resolved.route.name == "saygm" and resolved.provider == "saygm"
        and policy.level == "confidential"
    ):
        raise ProviderAccessError("API route cannot carry this protected source policy")
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
            raise ProviderAccessError("API request lacks exact validated source-policy admission")
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
        if fallback_routes or route not in SUBSCRIPTION_ROUTES | {"direct_api", "saygm"}:
            raise ProviderAccessError("direct OpenAI/Anthropic APIs are disabled; implicit fallback is prohibited")
        if resolved and route in {"direct_api", "saygm"}:
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
            "voice requires an eligible full-context route; direct OpenAI/Anthropic APIs are disabled and no fallback was used"
        )
