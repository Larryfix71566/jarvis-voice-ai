"""Deterministic model-route and workload-policy resolution.

This module owns policy, not provider execution. It deliberately fails closed:
an unavailable subscription, missing credential, unsupported privacy tier, or
unknown model is a route error and never an invitation to pick another model.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

REGISTRY_PATH_ENV = "JARVIS_UPGRADE_MODELS"
DEFAULT_REGISTRY_PATH = Path(__file__).resolve().parents[1] / "config" / "upgrade_models.yaml"

ROUTES = {"local", "subscription", "codex_subscription", "direct_api", "saygm"}
PRIVACY_LEVELS = {"local_only", "confidential", "approved_external"}
PRIORITIES = {"interactive", "background"}
DEFAULT_POLICY_PATH = Path(__file__).resolve().parents[1] / "config" / "model_access.yaml"
POLICY_PATH_ENV = "JARVIS_MODEL_ACCESS_CONFIG"
ROUTE_ENV_PREFIX = "JARVIS_ROUTE_"


class ModelRouteError(RuntimeError):
    """A requested route cannot safely execute the workload."""


def _load_model_registry(path: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    selected = Path(path or os.environ.get(REGISTRY_PATH_ENV) or DEFAULT_REGISTRY_PATH)
    if not selected.exists():
        return {"default": None, "profiles": {}}
    data = yaml.safe_load(selected.read_text(encoding="utf-8")) or {}
    profiles = {
        str(item["name"]): item for item in data.get("profiles", []) or []
        if isinstance(item, dict) and item.get("name")
    }
    return {"default": data.get("default"), "profiles": profiles}


def _resolve_model_profile(registry: dict[str, Any], requested: str, *,
                           workload: str | None = None) -> dict[str, Any]:
    profile = (registry.get("profiles") or {}).get(requested)
    # Haiku is intentionally not a general registry profile: the model-floor
    # contract keeps it exclusive to the latency-critical voice supervisor.
    # Keep that preserved route resolvable without advertising it to the
    # non-voice model picker or weakening the floor test for background work.
    if (not profile and workload == "voice_supervisor"
            and requested in {"claude-haiku", "claude-haiku-4-5"}):
        return {
            "name": "claude-haiku",
            "label": "Claude Haiku 4.5 — voice supervisor (direct API)",
            "provider": "anthropic",
            "model": "claude-haiku-4-5",
            "identity": "anthropic/claude-haiku-4-5",
            "base_url": "https://api.anthropic.com/v1/",
            "api_key_env": "ANTHROPIC_API_KEY",
            "temperature": None,
            "tier": "economy",
        }
    if not profile:
        raise ModelRouteError(f"unknown model profile {requested!r}")
    return profile


def model_profile_exists(profile: str, *, workload: str | None = None,
                         path: str | os.PathLike[str] | None = None) -> bool:
    """Return whether a profile is available without probing credentials.

    Haiku is deliberately exposed only when the caller identifies the voice
    supervisor workload; it is never added to the general registry picker.
    """
    if profile in (_load_model_registry(path).get("profiles") or {}):
        return True
    return workload == "voice_supervisor" and profile in {"claude-haiku", "claude-haiku-4-5"}


def model_profile_for_workload(workload: str, *,
                               policy_path: str | os.PathLike[str] | None = None,
                               registry_path: str | os.PathLike[str] | None = None
                               ) -> dict[str, Any]:
    """Return the metadata record selected for a workload.

    This is a read-only catalog operation: it applies the same voice-only
    built-in exception as route resolution but does not inspect credentials or
    contact a provider. Readiness/reporting surfaces should use this instead
    of reading the raw registry directly.
    """
    policy = resolve_policy(workload, path=policy_path, include_preferences=False)
    return _resolve_model_profile(
        _load_model_registry(registry_path), policy.profile, workload=workload
    )


def inspect_route_choice(workload: str, profile_name: str, route_name: str,
                         *, policy_path: str | os.PathLike[str] | None = None,
                         registry_path: str | os.PathLike[str] | None = None
                         ) -> tuple[WorkloadPolicy, dict[str, Any], AccessRoute]:
    """Inspect a proposed route without probing credentials or providers.

    Preference UIs use this to reject capability/privacy mismatches at draft
    time while still allowing a syntactically valid but currently unauthenticated
    route to be saved and displayed as unavailable.
    """
    policy = resolve_policy(workload, explicit_profile=profile_name,
                            explicit_route=route_name, path=policy_path,
                            include_preferences=False)
    profile = _resolve_model_profile(
        _load_model_registry(registry_path), profile_name, workload=workload
    )
    route = _route_for_profile(
        profile, route_name, (load_access_config(policy_path).get("routes") or {})
    )
    return policy, profile, route


@dataclass(frozen=True)
class AccessRoute:
    name: str
    adapter: str
    billing: str
    credential_env: str | None
    privacy: str
    upstream_provider: str | None = None
    base_url: str | None = None
    capabilities: tuple[str, ...] = ("text", "tools")


@dataclass(frozen=True)
class WorkloadPolicy:
    workload: str
    profile: str
    route: str
    privacy: str
    priority: str
    fallback_routes: tuple[str, ...] = ()
    required_capabilities: tuple[str, ...] = ("text",)


@dataclass(frozen=True)
class ResolvedModelRoute:
    workload: str
    profile_name: str
    model: str
    provider: str
    base_url: str
    route: AccessRoute
    api_key_env: str | None
    identity: str


def load_access_config(path: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    selected = Path(path or os.environ.get(POLICY_PATH_ENV) or DEFAULT_POLICY_PATH)
    if not selected.exists():
        raise ModelRouteError(f"model access policy is missing: {selected}")
    data = yaml.safe_load(selected.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ModelRouteError("model access policy must be a mapping")
    return data


def _validate_policy(workload: str, raw: dict[str, Any]) -> WorkloadPolicy:
    try:
        profile = str(raw["profile"])
        route = str(raw["route"])
        privacy = str(raw["privacy"])
        priority = str(raw["priority"])
    except (KeyError, TypeError) as exc:
        raise ModelRouteError(f"workload {workload!r} is incomplete") from exc
    if route not in ROUTES:
        raise ModelRouteError(f"workload {workload!r} has unknown route {route!r}")
    if privacy not in PRIVACY_LEVELS:
        raise ModelRouteError(f"workload {workload!r} has unknown privacy {privacy!r}")
    if priority not in PRIORITIES:
        raise ModelRouteError(f"workload {workload!r} has unknown priority {priority!r}")
    fallbacks = tuple(str(item) for item in raw.get("fallback_routes", ()))
    if any(item not in ROUTES for item in fallbacks):
        raise ModelRouteError(f"workload {workload!r} has an unknown fallback route")
    capabilities = tuple(str(item) for item in raw.get("capabilities", ("text",)))
    return WorkloadPolicy(workload, profile, route, privacy, priority, fallbacks, capabilities)


def resolve_policy(workload: str, *, explicit_profile: str | None = None,
                   explicit_route: str | None = None,
                   path: str | os.PathLike[str] | None = None,
                   include_preferences: bool = True) -> WorkloadPolicy:
    data = load_access_config(path)
    workloads = data.get("workloads") or {}
    if workload not in workloads:
        raise ModelRouteError(f"unknown workload {workload!r}")
    raw = dict(data.get("defaults") or {})
    raw.update(workloads.get(workload) or {})
    if include_preferences and os.environ.get("JARVIS_MODEL_PREFERENCES_ENABLED", "1") != "0":
        try:
            from jarvis.model_preferences import list_preferences
            preference = next((item for item in list_preferences()
                               if item.get("workload") == workload), None)
        except Exception:
            preference = None
        if preference:
            raw["profile"] = preference["profile"]
            raw["route"] = preference["route"]
            raw["privacy"] = preference["privacy"]
    env_profile = os.environ.get(f"JARVIS_MODEL_PROFILE_{workload.upper()}")
    env_route = os.environ.get(f"JARVIS_MODEL_ROUTE_{workload.upper()}")
    if env_profile:
        raw["profile"] = env_profile
    if env_route:
        raw["route"] = env_route
    if explicit_profile is not None:
        raw["profile"] = explicit_profile
    if explicit_route is not None:
        raw["route"] = explicit_route
    return _validate_policy(workload, raw)


def _route_for_profile(profile: dict[str, Any], route_name: str,
                       route_catalog: dict[str, Any] | None = None) -> AccessRoute:
    routes = profile.get("routes") or {}
    raw = routes.get(route_name) or (route_catalog or {}).get(route_name) or {}
    if route_name == "direct_api" and not raw:
        raw = {"adapter": "openai_compatible", "billing": "provider_api",
               "credential_env": profile.get("api_key_env"),
               "privacy": "approved_external",
               "capabilities": ["text", "tools"]}
    if not raw:
        raise ModelRouteError(
            f"profile {profile.get('name')!r} does not offer route {route_name!r}")
    adapter = str(raw.get("adapter") or route_name)
    privacy = str(raw.get("privacy") or "approved_external")
    if privacy not in PRIVACY_LEVELS:
        raise ModelRouteError(f"route {route_name!r} has unknown privacy {privacy!r}")
    capabilities = tuple(str(item) for item in raw.get("capabilities", ("text", "tools")))
    if route_name == "direct_api" and profile.get("vision") and "images" not in capabilities:
        capabilities = capabilities + ("images",)
    return AccessRoute(
        name=route_name,
        adapter=adapter,
        billing=str(raw.get("billing") or route_name),
        credential_env=raw.get("credential_env") or raw.get("api_key_env"),
        privacy=privacy,
        upstream_provider=raw.get("upstream_provider"),
        base_url=raw.get("base_url"),
        capabilities=capabilities,
    )


def resolve_model_route(workload: str, *, explicit_profile: str | None = None,
                        explicit_route: str | None = None,
                        policy_path: str | os.PathLike[str] | None = None,
                        registry_path: str | os.PathLike[str] | None = None,
                        environ: dict[str, str] | None = None,
                        saygm_model: Any | None = None) -> ResolvedModelRoute:
    env = environ if environ is not None else os.environ
    policy = resolve_policy(workload, explicit_profile=explicit_profile,
                            explicit_route=explicit_route, path=policy_path)
    registry = _load_model_registry(registry_path)
    profile = _resolve_model_profile(registry, policy.profile, workload=workload)
    route = _route_for_profile(profile, policy.route, (load_access_config(policy_path).get("routes") or {}))
    if route.name == "saygm" and saygm_model is not None:
        catalog_model = str(getattr(saygm_model, "model", ""))
        profile_model = str(profile.get("model", ""))
        if catalog_model != profile_model and catalog_model.removesuffix("-TEE") != profile_model:
            raise ModelRouteError(
                f"SAYGM catalog model {getattr(saygm_model, 'model', None)!r} "
                f"does not match profile {profile.get('model')!r}")
        if getattr(saygm_model, "confidential", False):
            route = AccessRoute(route.name, route.adapter, route.billing,
                                route.credential_env, "confidential",
                                route.upstream_provider, route.base_url,
                                route.capabilities)
    if route.privacy == "approved_external" and policy.privacy == "local_only":
        raise ModelRouteError(
            f"workload {workload!r} requires local_only but route {route.name!r} is external")
    if policy.privacy == "confidential" and route.privacy not in {"local_only", "confidential"}:
        raise ModelRouteError(
            f"workload {workload!r} requires confidential processing; "
            f"route {route.name!r} is {route.privacy}")
    missing_capabilities = set(policy.required_capabilities) - set(route.capabilities)
    if missing_capabilities:
        raise ModelRouteError(
            f"route {route.name!r} lacks required capabilities: "
            + ", ".join(sorted(missing_capabilities)))
    if route.credential_env and not env.get(route.credential_env):
        raise ModelRouteError(
            f"route {route.name!r} for workload {workload!r} requires {route.credential_env}")
    return ResolvedModelRoute(
        workload=workload,
        profile_name=str(profile["name"]),
        model=str(profile["model"]),
        provider=("saygm" if route.name == "saygm" else
                  "subscription" if route.adapter in {"subscription_runtime", "codex_subscription_runtime"} else
                  str(profile.get("provider") or "")),
        base_url=str(route.base_url or profile.get("base_url") or ""),
        route=route,
        api_key_env=route.credential_env,
        identity=str(profile.get("identity") or ""),
    )


def resolve_model_route_checked(workload: str, *, explicit_profile: str | None = None,
                                explicit_route: str | None = None,
                                policy_path: str | os.PathLike[str] | None = None,
                                registry_path: str | os.PathLike[str] | None = None,
                                environ: dict[str, str] | None = None) -> ResolvedModelRoute:
    """Resolve a route and obtain SAYGM catalog proof when it is required."""
    policy = resolve_policy(workload, explicit_profile=explicit_profile,
                            explicit_route=explicit_route, path=policy_path)
    if policy.route != "saygm" or policy.privacy != "confidential":
        return resolve_model_route(workload, explicit_profile=explicit_profile,
                                   explicit_route=explicit_route,
                                   policy_path=policy_path,
                                   registry_path=registry_path,
                                   environ=environ)
    from jarvis.saygm import fetch_catalog
    catalog = fetch_catalog(api_key=(environ or os.environ).get("SAYGM_API_KEY"))
    registry = _load_model_registry(registry_path)
    profile = _resolve_model_profile(registry, policy.profile, workload=workload)
    wanted = str(profile.get("model", ""))
    match = next((item for item in catalog
                  if item.model == wanted or item.model.removesuffix("-TEE") == wanted), None)
    if match is None:
        raise ModelRouteError(
            f"SAYGM has no catalog entry for confidential profile {wanted!r}")
    return resolve_model_route(workload, explicit_profile=explicit_profile,
                               explicit_route=explicit_route,
                               policy_path=policy_path, registry_path=registry_path,
                               environ=environ, saygm_model=match)


def available_routes(profile: dict[str, Any]) -> list[str]:
    """Return configured routes without exposing credential values."""
    names = set((profile.get("routes") or {}).keys())
    if profile.get("api_key_env"):
        names.add("direct_api")
    return sorted(names)


def make_route_client(resolved: ResolvedModelRoute, *, timeout: float | None = 60,
                      max_retries: int = 0) -> Any:
    """Build only an API-compatible client for an already validated route.

    Subscription and local adapters intentionally fail until their official
    runtimes are installed and capability-tested; this prevents a route label
    from masquerading as an implementation.
    """
    if resolved.route.adapter == "subscription_runtime":
        if os.environ.get("JARVIS_SUBSCRIPTION_TEXT_ENABLED") != "1":
            raise ModelRouteError("subscription text adapter is disabled")
        from jarvis.subscription import SubscriptionTextClient
        return SubscriptionTextClient(resolved.model, timeout=float(timeout or 120))
    if resolved.route.adapter == "codex_subscription_runtime":
        if os.environ.get("JARVIS_SUBSCRIPTION_TEXT_ENABLED") != "1":
            raise ModelRouteError("subscription text adapter is disabled")
        from jarvis.subscription import CodexSubscriptionTextClient
        return CodexSubscriptionTextClient(resolved.model, timeout=float(timeout or 120))
    if resolved.route.adapter == "local_runtime":
        raise ModelRouteError("local model runtime is not configured")
    if not resolved.api_key_env:
        raise ModelRouteError(f"route {resolved.route.name!r} has no credential reference")
    key = os.environ.get(resolved.api_key_env)
    if not key:
        raise ModelRouteError(f"route {resolved.route.name!r} requires {resolved.api_key_env}")
    from jarvis.llm_client import make_async_client
    return make_async_client(
        api_key=key,
        base_url=resolved.base_url,
        provider="saygm" if resolved.route.name == "saygm" else resolved.provider,
        model=resolved.model,
        timeout=timeout,
        max_retries=max_retries,
    )


def make_sync_route_client(resolved: ResolvedModelRoute, *, timeout: float | None = 120,
                           max_retries: int = 0) -> Any:
    """Synchronous counterpart used by the self-edit planner."""
    if resolved.route.adapter == "subscription_runtime":
        if os.environ.get("JARVIS_SUBSCRIPTION_TEXT_ENABLED") != "1":
            raise ModelRouteError("subscription text adapter is disabled")
        from jarvis.subscription import SubscriptionSyncTextClient
        return SubscriptionSyncTextClient(resolved.model, timeout=float(timeout or 120))
    if resolved.route.adapter == "codex_subscription_runtime":
        if os.environ.get("JARVIS_SUBSCRIPTION_TEXT_ENABLED") != "1":
            raise ModelRouteError("subscription text adapter is disabled")
        from jarvis.subscription import CodexSubscriptionSyncTextClient
        return CodexSubscriptionSyncTextClient(resolved.model, timeout=float(timeout or 120))
    if resolved.route.adapter == "local_runtime":
        raise ModelRouteError("local model runtime is not configured")
    if not resolved.api_key_env:
        raise ModelRouteError(f"route {resolved.route.name!r} has no credential reference")
    key = os.environ.get(resolved.api_key_env)
    if not key:
        raise ModelRouteError(f"route {resolved.route.name!r} requires {resolved.api_key_env}")
    from jarvis.llm_client import make_sync_client
    return make_sync_client(
        api_key=key,
        base_url=resolved.base_url,
        provider="saygm" if resolved.route.name == "saygm" else resolved.provider,
        model=resolved.model,
        timeout=timeout,
        max_retries=max_retries,
    )
