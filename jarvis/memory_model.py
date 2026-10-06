"""Dedicated model routing for non-voice background work.

The voice Supervisor's ``OPENAI_MODEL`` is intentionally not a memory-model
selection mechanism. Memory extraction, consolidation and classification use
an explicit model-registry profile and its own credential variable. Knowledge-
base and procedure maintenance use a separate background profile. If a
profile is unavailable, callers fail closed and preserve the existing
best-effort behavior.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from jarvis.agents.upgrade_agent import load_model_registry, resolve_profile
from jarvis.llm_client import make_async_client
from jarvis.model_routing import (
    ModelRouteError,
    ResolvedModelRoute,
    make_route_client,
    resolve_model_route,
    resolve_model_route_checked,
    resolve_policy,
)
from jarvis.privacy_policy import DataPolicy, assert_route_allowed, strictest

MEMORY_PROFILE_ENV = "JARVIS_MEMORY_PROFILE"
BACKGROUND_PROFILE_ENV = "JARVIS_BACKGROUND_PROFILE"
DEFAULT_MEMORY_PROFILE = "claude-sonnet-5"
DEFAULT_BACKGROUND_PROFILE = "claude-sonnet-5"


class MemoryModelUnavailable(RuntimeError):
    """The explicitly selected background memory route cannot run."""


@dataclass(frozen=True)
class MemoryModelRoute:
    profile: str
    provider: str
    model: str
    base_url: str
    api_key_env: str
    resolved: ResolvedModelRoute | None = None


def _assert_background_source_policy(resolved: ResolvedModelRoute, workload: str) -> None:
    configured = resolve_policy(workload, include_preferences=False)
    # Real memory/background sources contain private exchanges, facts or
    # successful tasks. The separately declared memory_shadow workload owns
    # public fixtures; a route preference cannot approve private sources.
    required = strictest(
        DataPolicy("confidential", f"{workload}-source"),
        DataPolicy(configured.privacy, f"configured-workload:{workload}"),
    )
    assert_route_allowed(resolved.route, required)


def _resolve_route(settings: Any, *, profile_attr: str, env_name: str,
                   default_profile: str, purpose: str) -> MemoryModelRoute:
    """Resolve a non-Supervisor background route without voice-key fallback.

    An injected test client bypasses this helper at each call site. Production
    calls require a registry profile and a non-empty value for that profile's
    declared credential variable; no fallback to ``settings.openai_*`` is
    permitted.
    """
    profile_name = (getattr(settings, profile_attr, None)
                    or os.environ.get(env_name)
                    or default_profile)
    registry = load_model_registry()
    try:
        profile = resolve_profile(registry, profile_name)
    except Exception as exc:  # noqa: BLE001 - stable boundary error
        raise MemoryModelUnavailable(
            f"{purpose} model profile {profile_name!r} is unavailable"
        ) from exc
    fields = ("provider", "model", "base_url", "api_key_env")
    if any(not profile.get(field) for field in fields):
        raise MemoryModelUnavailable(
            f"{purpose} model profile {profile_name!r} is incomplete"
        )
    key_env = str(profile["api_key_env"])
    if not os.environ.get(key_env):
        raise MemoryModelUnavailable(
            f"{purpose} model profile {profile_name!r} requires {key_env}"
        )
    return MemoryModelRoute(
        profile=str(profile_name), provider=str(profile["provider"]),
        model=str(profile["model"]), base_url=str(profile["base_url"]),
        api_key_env=key_env,
    )


def resolve_memory_route(settings: Any) -> MemoryModelRoute:
    """Resolve the dedicated memory route without consulting Supervisor keys."""
    profile = getattr(settings, "jarvis_memory_profile", None) or os.environ.get(
        MEMORY_PROFILE_ENV) or DEFAULT_MEMORY_PROFILE
    if not (getattr(settings, "jarvis_model_routing_enabled", False)
            or os.environ.get("JARVIS_MODEL_ROUTING_ENABLED") == "1"):
        return _resolve_route(settings, profile_attr="jarvis_memory_profile",
                              env_name=MEMORY_PROFILE_ENV,
                              default_profile=DEFAULT_MEMORY_PROFILE,
                              purpose="memory")
    try:
        resolved = resolve_model_route_checked("memory", explicit_profile=profile)
        _assert_background_source_policy(resolved, "memory")
    except ModelRouteError as exc:
        raise MemoryModelUnavailable(str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - provider/config diagnostics may contain private values
        raise MemoryModelUnavailable(
            f"memory model route unavailable (error_type={type(exc).__name__[:64]})"
        ) from None
    return MemoryModelRoute(profile=resolved.profile_name, provider=resolved.provider,
                            model=resolved.model, base_url=resolved.base_url,
                            api_key_env=str(resolved.api_key_env or ""), resolved=resolved)


def resolve_background_route(settings: Any) -> MemoryModelRoute:
    """Resolve the shared route for non-voice maintenance jobs.

    This covers knowledge-base digests and procedure descriptions. It is
    intentionally separate from ``OPENAI_MODEL`` so Haiku remains exclusive
    to the voice Supervisor, while the provider/model stays configurable via
    the same registry used by the other background workloads.
    """
    profile = getattr(settings, "jarvis_background_profile", None) or os.environ.get(
        BACKGROUND_PROFILE_ENV) or DEFAULT_BACKGROUND_PROFILE
    if not (getattr(settings, "jarvis_model_routing_enabled", False)
            or os.environ.get("JARVIS_MODEL_ROUTING_ENABLED") == "1"):
        return _resolve_route(settings, profile_attr="jarvis_background_profile",
                              env_name=BACKGROUND_PROFILE_ENV,
                              default_profile=DEFAULT_BACKGROUND_PROFILE,
                              purpose="background")
    try:
        resolved = resolve_model_route_checked("background", explicit_profile=profile)
        _assert_background_source_policy(resolved, "background")
    except ModelRouteError as exc:
        raise MemoryModelUnavailable(str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - provider/config diagnostics may contain private values
        raise MemoryModelUnavailable(
            f"background model route unavailable (error_type={type(exc).__name__[:64]})"
        ) from None
    return MemoryModelRoute(profile=resolved.profile_name, provider=resolved.provider,
                            model=resolved.model, base_url=resolved.base_url,
                            api_key_env=str(resolved.api_key_env or ""), resolved=resolved)


def _make_async_client(settings: Any, route_resolver) -> tuple[Any, MemoryModelRoute]:
    """Build the async client and return its resolved route for usage logs."""
    route = route_resolver(settings)
    if route.resolved is not None:
        return make_route_client(route.resolved, timeout=60, max_retries=0), route
    client = make_async_client(
        api_key=os.environ[route.api_key_env], base_url=route.base_url,
        provider=route.provider, model=route.model, timeout=60, max_retries=0,
    )
    return client, route


def make_memory_async_client(settings: Any) -> tuple[Any, MemoryModelRoute]:
    return _make_async_client(settings, resolve_memory_route)


def make_background_async_client(settings: Any) -> tuple[Any, MemoryModelRoute]:
    return _make_async_client(settings, resolve_background_route)
