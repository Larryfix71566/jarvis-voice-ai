"""Deterministic model-route and workload-policy resolution.

This module owns policy, not provider execution. It deliberately fails closed:
an unavailable subscription, missing credential, unsupported privacy tier, or
unknown model is a route error and never an invitation to pick another model.
"""
from __future__ import annotations

import math
import os
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import yaml

ROUTES = {"local", "subscription", "codex_subscription", "direct_api", "saygm"}
PRIVACY_LEVELS = {"local_only", "confidential", "approved_external"}
PRIORITIES = {"interactive", "background"}
_PRIVACY_ORDER = {"approved_external": 1, "confidential": 2, "local_only": 3}
_QUALITY_ORDER = {"economy": 1, "mid": 2, "frontier": 3}
_STANDING_QUALITY_FLOORS = {
    "voice_supervisor": "economy", "council": "economy", "planning": "frontier",
}
DEFAULT_POLICY_PATH = Path(__file__).resolve().parents[1] / "config" / "model_access.yaml"
POLICY_PATH_ENV = "JARVIS_MODEL_ACCESS_CONFIG"
ROUTE_ENV_PREFIX = "JARVIS_ROUTE_"
SKILL_EVAL_ENABLED_ENV = "JARVIS_SKILL_EVAL_ENABLED"
# Route configuration is editable by the routine self-edit loop. It can
# restrict capabilities, but cannot authorize a new credential destination,
# convert a subscription into an API, or certify remote processing as local.
_ROUTE_CONTRACTS = {
    "direct_api": ("openai_compatible", "provider_api", "approved_external"),
    "subscription": ("subscription_runtime", "subscription", "approved_external"),
    "codex_subscription": ("codex_subscription_runtime", "subscription", "approved_external"),
    "saygm": ("saygm_gateway", "saygm_credit", "approved_external"),
    "local": ("local_runtime", "local", "local_only"),
}
_ROUTE_CONFIG_KEYS = frozenset({
    "adapter", "billing", "privacy", "provider", "base_url", "credential_env",
    "api_key_env", "capabilities",
})
_NATIVE_ROUTE_URLS = {
    "subscription": "subscription://claude", "codex_subscription": "subscription://codex",
}


class ModelRouteError(RuntimeError):
    """A requested route cannot safely execute the workload."""


def _assert_unique_canonical_identities(registry: dict[str, Any]) -> None:
    """An enabled routed registry cannot give one model multiple votes.

    Council membership excludes profile names, so two profiles for one
    identity could otherwise let a model score its own proposal. Check the
    whole joined registry before selection, credentials, or catalog calls.
    The legacy loader is unchanged while shared routing is disabled.
    """
    seen: set[str] = set()
    for profile in (registry.get("profiles") or {}).values():
        identity = profile.get("identity")
        if (not isinstance(identity, str) or identity != identity.strip()
                or "/" not in identity or not all(identity.split("/", 1))):
            raise ModelRouteError("routed model registry has an unavailable canonical identity")
        if identity in seen:
            raise ModelRouteError("routed model registry has duplicate canonical model identities")
        seen.add(identity)


def _load_model_registry(path: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    """The joined model registry, through the ONE loader (spec I6/A2).

    This used to parse the registry YAML itself, which after the split
    (docs/plans/MORTIMER_MODEL_REGISTRY_SPLIT_PLAN.md) would have read the
    profile pool without its endpoints. Imported lazily: upgrade_agent
    imports this module at load time.
    """
    from jarvis.agents.upgrade_agent import load_model_registry

    registry = load_model_registry(path or None)
    if os.environ.get("JARVIS_MODEL_ROUTING_ENABLED") == "1":
        _assert_unique_canonical_identities(registry)
    return registry


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
                         registry_path: str | os.PathLike[str] | None = None,
                         access_config: dict[str, Any] | None = None,
                         registry: dict[str, Any] | None = None,
                         ) -> tuple[WorkloadPolicy, dict[str, Any], AccessRoute]:
    """Inspect a proposed route without probing credentials or providers.

    Preference UIs use this to reject capability/privacy mismatches at draft
    time while still allowing a syntactically valid but currently unauthenticated
    route to be saved and displayed as unavailable.
    """
    access = access_config if access_config is not None else load_access_config(policy_path)
    policy = resolve_policy(workload, explicit_profile=profile_name,
                            explicit_route=route_name, path=policy_path,
                            include_preferences=False, access_config=access)
    selected_registry = registry if registry is not None else _load_model_registry(registry_path)
    _assert_unique_canonical_identities(selected_registry)
    profile = _resolve_model_profile(selected_registry, profile_name, workload=workload)
    route = _route_for_profile(
        profile, route_name, (access.get("routes") or {})
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
class WorkloadLimits:
    """Optional task limits; spending refers to configured-price estimates.

    A deadline is a duration, never a timestamp established during route
    resolution. The execution owner starts it for each task. Unset limits
    preserve the existing workload behavior.
    """

    max_output_tokens_per_call: int | None = None
    deadline_seconds: float | None = None
    max_estimated_spend_usd_per_task: float | None = None

    def __post_init__(self) -> None:
        output = self.max_output_tokens_per_call
        if output is not None and (type(output) is not int or not 1 <= output <= 32_000):
            raise ModelRouteError(
                "workload max_output_tokens_per_call must be an integer from 1 to 32000 or null")
        for name in ("deadline_seconds", "max_estimated_spend_usd_per_task"):
            value = getattr(self, name)
            if value is None:
                continue
            if type(value) not in {int, float}:
                raise ModelRouteError(f"workload {name} must be positive and finite or null")
            try:
                valid = math.isfinite(value) and value > 0
            except OverflowError:
                valid = False
            if not valid:
                raise ModelRouteError(f"workload {name} must be positive and finite or null")

    def as_metadata(self) -> dict[str, int | float | None]:
        """Return only public policy values, without account or billing claims."""
        return {
            "max_output_tokens_per_call": self.max_output_tokens_per_call,
            "deadline_seconds": self.deadline_seconds,
            "max_estimated_spend_usd_per_task": self.max_estimated_spend_usd_per_task,
        }


def workload_limits_from_policy(raw: Mapping[str, Any]) -> WorkloadLimits:
    """Validate limits from the already merged default/workload policy.

    This helper does not read configuration, preferences, time, or providers.
    A workload's explicit null clears an inherited default value.
    """
    if not isinstance(raw, Mapping):
        raise ModelRouteError("workload policy must be a mapping")
    return WorkloadLimits(
        max_output_tokens_per_call=raw.get("max_output_tokens_per_call"),
        deadline_seconds=raw.get("deadline_seconds"),
        max_estimated_spend_usd_per_task=raw.get("max_estimated_spend_usd_per_task"),
    )


@dataclass(frozen=True)
class WorkloadPolicy:
    workload: str
    profile: str
    route: str
    privacy: str
    priority: str
    fallback_routes: tuple[str, ...] = ()
    required_capabilities: tuple[str, ...] = ("text",)
    minimum_quality_tier: str = "mid"
    limits: WorkloadLimits = field(default_factory=WorkloadLimits)

    def __post_init__(self) -> None:
        if not isinstance(self.limits, WorkloadLimits):
            raise ModelRouteError("workload limits must be a validated WorkloadLimits record")


@dataclass(frozen=True)
class SkillEvaluationLimits:
    """Hard upper bounds for an explicitly enabled skill-evaluation batch."""

    max_cases: int
    repetitions: int
    max_calls: int
    max_calls_per_trial: int
    deadline_seconds: int
    max_input_tokens_per_call: int
    max_output_tokens_per_call: int
    spend_ceiling_usd: float | None


def load_skill_evaluation_limits(
    path: str | os.PathLike[str] | None = None,
) -> SkillEvaluationLimits | None:
    """Read optional bounded evaluation config; absence keeps it unavailable."""
    data = load_access_config(path)
    raw = data.get("skill_evaluation")
    if raw is None:
        return None
    if not isinstance(raw, dict) or raw.get("schema_version") != 1:
        raise ModelRouteError("skill evaluation configuration is invalid")
    if raw.get("enabled") is not True:
        return None
    required = {
        "schema_version", "enabled", "max_cases", "repetitions", "max_calls",
        "max_calls_per_trial", "deadline_seconds", "max_input_tokens_per_call",
        "max_output_tokens_per_call", "spend_ceiling_usd",
    }
    if set(raw) != required:
        raise ModelRouteError("skill evaluation budget fields are invalid")

    def bounded_int(name: str, minimum: int, maximum: int) -> int:
        value = raw[name]
        if type(value) is not int or not minimum <= value <= maximum:
            raise ModelRouteError(f"skill evaluation {name} is outside its limit")
        return value

    max_cases = bounded_int("max_cases", 1, 6)
    repetitions = bounded_int("repetitions", 1, 2)
    calls_per_trial = bounded_int("max_calls_per_trial", 1, 4)
    max_calls = bounded_int("max_calls", 1, 96)
    if max_calls > max_cases * 2 * repetitions * calls_per_trial:
        raise ModelRouteError("skill evaluation max_calls exceeds the trial budget")
    deadline = bounded_int("deadline_seconds", 1, 900)
    input_tokens = bounded_int("max_input_tokens_per_call", 1, 64_000)
    output_tokens = bounded_int("max_output_tokens_per_call", 1, 4_000)
    spend_ceiling = raw["spend_ceiling_usd"]
    if spend_ceiling is not None and (
            isinstance(spend_ceiling, bool)
            or not isinstance(spend_ceiling, (int, float))
            or not math.isfinite(spend_ceiling) or spend_ceiling <= 0):
        raise ModelRouteError("skill evaluation spend ceiling must be positive or null")
    return SkillEvaluationLimits(
        max_cases=max_cases, repetitions=repetitions, max_calls=max_calls,
        max_calls_per_trial=calls_per_trial, deadline_seconds=deadline,
        max_input_tokens_per_call=input_tokens,
        max_output_tokens_per_call=output_tokens,
        spend_ceiling_usd=float(spend_ceiling) if spend_ceiling is not None else None,
    )


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
    # Snapshot admission priority together with model/route selection so a
    # later preference edit cannot reclassify an in-flight request.
    priority: str = "interactive"
    limits: WorkloadLimits = field(default_factory=WorkloadLimits)

    def __post_init__(self) -> None:
        if not isinstance(self.limits, WorkloadLimits):
            raise ModelRouteError("resolved workload limits must be a validated WorkloadLimits record")


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
    standing_floor = _STANDING_QUALITY_FLOORS.get(workload, "mid")
    minimum_quality = raw.get("minimum_quality_tier", standing_floor)
    if not isinstance(minimum_quality, str) or minimum_quality not in _QUALITY_ORDER:
        raise ModelRouteError(f"workload {workload!r} has an unknown minimum quality tier")
    if _QUALITY_ORDER[minimum_quality] < _QUALITY_ORDER[standing_floor]:
        raise ModelRouteError(
            f"workload {workload!r} minimum quality cannot be below its standing {standing_floor!r} floor")
    return WorkloadPolicy(workload, profile, route, privacy, priority, fallbacks,
                          capabilities, minimum_quality, workload_limits_from_policy(raw))


def resolve_policy(workload: str, *, explicit_profile: str | None = None,
                   explicit_route: str | None = None,
                   path: str | os.PathLike[str] | None = None,
                   include_preferences: bool = True,
                   access_config: dict[str, Any] | None = None) -> WorkloadPolicy:
    skill_eval = workload == "skill_eval"
    data = access_config if access_config is not None else load_access_config(path)
    if skill_eval:
        limits = load_skill_evaluation_limits(path)
        if (limits is None
                or os.environ.get(SKILL_EVAL_ENABLED_ENV) != "1"):
            raise ModelRouteError("skill evaluation is disabled")
    workloads = data.get("workloads") or {}
    if workload not in workloads:
        raise ModelRouteError(f"unknown workload {workload!r}")
    raw = dict(data.get("defaults") or {})
    raw.update(workloads.get(workload) or {})
    from jarvis.storage_context import preferences_enabled
    if (not skill_eval and include_preferences
            and preferences_enabled(os.environ.get("JARVIS_MODEL_PREFERENCES_ENABLED", "1") != "0")):
        try:
            from jarvis.model_preferences import list_preferences
            preference = next((item for item in list_preferences()
                               if item.get("workload") == workload), None)
        except Exception:  # noqa: BLE001 — a read failure cannot authorize model substitution
            raise ModelRouteError("saved model preferences are unavailable") from None
        if preference:
            configured_privacy = raw.get("privacy")
            saved_privacy = preference.get("privacy")
            if (configured_privacy in _PRIVACY_ORDER and saved_privacy in _PRIVACY_ORDER
                    and _PRIVACY_ORDER[saved_privacy] < _PRIVACY_ORDER[configured_privacy]):
                # Older releases could persist a weaker preference. Read-side
                # enforcement protects every factory, including consumers that
                # have not yet moved to the shared execution boundary.
                raise ModelRouteError(
                    f"saved preference for workload {workload!r} is below its "
                    f"configured {configured_privacy!r} privacy requirement")
            raw["profile"] = preference["profile"]
            raw["route"] = preference["route"]
            raw["privacy"] = preference["privacy"]
    env_profile = os.environ.get(f"JARVIS_MODEL_PROFILE_{workload.upper()}")
    env_route = os.environ.get(f"JARVIS_MODEL_ROUTE_{workload.upper()}")
    if skill_eval and (env_profile or env_route):
        raise ModelRouteError("skill evaluation route overrides are not allowed")
    if skill_eval and (
            (explicit_profile is not None and explicit_profile != raw.get("profile"))
            or (explicit_route is not None and explicit_route != raw.get("route"))):
        raise ModelRouteError("skill evaluation route must match explicit configuration")
    if env_profile:
        raw["profile"] = env_profile
    if env_route:
        raw["route"] = env_route
    if explicit_profile is not None:
        raw["profile"] = explicit_profile
    if explicit_route is not None:
        raw["route"] = explicit_route
    policy = _validate_policy(workload, raw)
    if workload == "skill_eval":
        if policy.priority != "background" or policy.fallback_routes:
            raise ModelRouteError(
                "skill evaluation must use background priority with no fallback"
            )
        if "text" not in policy.required_capabilities:
            raise ModelRouteError("skill evaluation requires text capability")
    return policy


def _route_for_profile(profile: dict[str, Any], route_name: str,
                       route_catalog: dict[str, Any] | None = None) -> AccessRoute:
    routes = profile.get("routes") or {}
    raw = routes.get(route_name) or (route_catalog or {}).get(route_name) or {}
    if route_name not in _ROUTE_CONTRACTS:
        raise ModelRouteError(f"unknown route {route_name!r}")
    if route_name == "direct_api":
        if not profile.get("api_key_env"):
            raise ModelRouteError(
                f"profile {profile.get('name')!r} does not offer route {route_name!r}")
        if not raw:
            raw = {"capabilities": ["text", "tools"]}
    if not raw:
        raise ModelRouteError(
            f"profile {profile.get('name')!r} does not offer route {route_name!r}")
    if not isinstance(raw, dict) or set(raw) - _ROUTE_CONFIG_KEYS:
        raise ModelRouteError(f"route {route_name!r} contains unsupported configuration fields")
    adapter, billing, privacy = _ROUTE_CONTRACTS[route_name]
    for field, expected in (("adapter", adapter), ("billing", billing), ("privacy", privacy)):
        if field in raw and raw[field] != expected:
            raise ModelRouteError(f"route {route_name!r} cannot override its protected {field} contract")
    subscription_provider = {
        "subscription": "anthropic", "codex_subscription": "openai",
    }.get(route_name)
    if subscription_provider and (
            profile.get("provider") != subscription_provider
            or str(profile.get("identity") or "").split("/")[0] != subscription_provider):
        raise ModelRouteError(
            f"route {route_name!r} requires a {subscription_provider!r} model profile")
    credential_env = None
    base_url = None
    if route_name == "direct_api":
        # These profile fields came from the protected endpoint registry, not
        # model_access.yaml. Even a route override with the same model cannot
        # rebind its key or host. Compare before reading any key value.
        credential_env = profile["api_key_env"]
        base_url = profile.get("base_url")
        if not base_url:
            raise ModelRouteError("direct_api requires an authoritative registry endpoint")
        for field, expected in (("base_url", base_url), ("credential_env", credential_env),
                                ("api_key_env", credential_env), ("provider", profile.get("provider"))):
            if field in raw and raw[field] != expected:
                raise ModelRouteError(f"route 'direct_api' cannot override its authoritative registry {field}")
    elif route_name in _NATIVE_ROUTE_URLS or route_name == "local":
        if any(field in raw for field in ("base_url", "credential_env", "api_key_env")):
            raise ModelRouteError(f"route {route_name!r} cannot carry an API endpoint or credential")
        expected_provider = {"subscription": "claude", "codex_subscription": "codex"}.get(route_name)
        if "provider" in raw and raw["provider"] != expected_provider:
            raise ModelRouteError(f"route {route_name!r} cannot override its protected provider contract")
    if route_name == "saygm":
        # A config label cannot prove that inference stays in a TEE. Only an
        # exact catalog binding may promote this external route's privacy.
        privacy = "approved_external"
        from jarvis.saygm import (
            API_KEY_ENV,
            DEFAULT_BASE_URL,
            SayGMError,
            validate_endpoint,
        )
        try:
            validate_endpoint(str(raw.get("base_url") or DEFAULT_BASE_URL),
                              raw.get("credential_env") or raw.get("api_key_env") or API_KEY_ENV)
        except SayGMError as exc:
            raise ModelRouteError(str(exc)) from exc
        if "provider" in raw and raw["provider"] != "saygm":
            raise ModelRouteError("route 'saygm' cannot override its protected provider contract")
        # Validate both aliases independently so a valid first value cannot
        # hide an unapproved second credential reference.
        for field in ("credential_env", "api_key_env"):
            if field in raw and raw[field] != API_KEY_ENV:
                raise ModelRouteError("SAYGM credential reference is not approved")
        base_url, credential_env = DEFAULT_BASE_URL, API_KEY_ENV
    requested_capabilities = raw.get("capabilities", ("text", "tools"))
    if (not isinstance(requested_capabilities, (list, tuple))
            or any(not isinstance(item, str) for item in requested_capabilities)):
        raise ModelRouteError(f"route {route_name!r} capabilities must be a list of names")
    capabilities = tuple(dict.fromkeys(requested_capabilities))
    permitted = {"text", "tools"}
    if route_name == "direct_api":
        if profile.get("vision") is True:
            permitted.add("images")
        if profile.get("streaming") is True:
            permitted.add("streaming")
    elif route_name == "saygm":
        # Catalog binding below intersects these with exact model proof.
        permitted.update({"images", "streaming"})
    if set(capabilities) - permitted:
        raise ModelRouteError(f"route {route_name!r} cannot add unverified model capabilities")
    # Streaming is opt-in per model profile. Provider SDK support alone does
    # not silently advertise a capability for every configured endpoint.
    if (route_name == "direct_api" and profile.get("streaming") is True
            and "streaming" not in capabilities):
        capabilities = capabilities + ("streaming",)
    if route_name == "direct_api" and profile.get("vision") and "images" not in capabilities:
        capabilities = capabilities + ("images",)
    return AccessRoute(
        name=route_name,
        adapter=adapter,
        billing=billing,
        credential_env=credential_env,
        privacy=privacy,
        base_url=base_url,
        capabilities=capabilities,
    )


def _bind_saygm_model(profile: dict[str, Any], route: AccessRoute,
                      catalog_model: Any) -> tuple[AccessRoute, str]:
    from jarvis.saygm import SayGMError, SayGMModel, confidential_model

    if not isinstance(catalog_model, SayGMModel):
        raise ModelRouteError("SAYGM route requires a parsed catalog model")
    profile_model = str(profile.get("model", ""))
    if catalog_model.model not in {profile_model, profile_model + "-TEE"}:
        raise ModelRouteError(
            f"SAYGM catalog model {catalog_model.model!r} "
            f"does not match profile {profile_model!r}")
    if catalog_model.confidential:
        try:
            confidential_model([catalog_model], profile_model)
        except SayGMError as exc:
            raise ModelRouteError(str(exc)) from exc
    bound = replace(
        route,
        privacy="confidential" if catalog_model.confidential else "approved_external",
        upstream_provider=catalog_model.gateway_provider,
        capabilities=tuple(capability for capability in route.capabilities
                           if capability in catalog_model.capabilities),
    )
    return bound, catalog_model.model


def verify_saygm_route_choice(profile: dict[str, Any], route: AccessRoute, *,
                              environ: dict[str, str] | None = None,
                              privacy: str = "confidential",
                              ) -> tuple[AccessRoute, str]:
    """Bind confidential proof to the exact endpoint, credential and model.

    Staging, confirmation and execution use this same provider boundary. It
    does not execute inference or try a paid fallback.
    """
    from jarvis.saygm import (
        SayGMError,
        catalog_model,
        confidential_model,
        fetch_catalog,
        validate_endpoint,
    )

    if route.name != "saygm":
        raise ModelRouteError("catalog verification requires the SAYGM route")
    if privacy == "local_only":
        raise ModelRouteError("SAYGM cannot provide local_only processing")
    try:
        base_url = validate_endpoint(str(route.base_url or ""), route.credential_env)
    except SayGMError as exc:
        raise ModelRouteError(str(exc)) from exc
    env = environ if environ is not None else os.environ
    if not route.credential_env or not env.get(route.credential_env):
        raise ModelRouteError(
            f"route 'saygm' requires {route.credential_env or 'a credential reference'}")
    try:
        catalog = fetch_catalog(api_key=env[route.credential_env], base_url=base_url)
        selected = (confidential_model if privacy == "confidential" else catalog_model)(
            catalog, str(profile.get("model", "")))
    except SayGMError as exc:
        raise ModelRouteError(str(exc)) from exc
    return _bind_saygm_model(profile, route, selected)


def _assert_policy_route(policy: WorkloadPolicy, route: AccessRoute) -> None:
    if policy.privacy == "local_only" and route.privacy != "local_only":
        raise ModelRouteError(
            f"workload {policy.workload!r} requires local_only but route {route.name!r} is external")
    if policy.privacy == "confidential" and route.privacy not in {"local_only", "confidential"}:
        raise ModelRouteError(
            f"workload {policy.workload!r} requires confidential processing; "
            f"route {route.name!r} is {route.privacy}")
    missing = set(policy.required_capabilities) - set(route.capabilities)
    if missing:
        raise ModelRouteError(
            f"route {route.name!r} lacks required capabilities: "
            + ", ".join(sorted(missing)))


def assert_model_quality(policy: WorkloadPolicy, profile: dict[str, Any]) -> None:
    """Enforce workload quality independently of route price or availability."""
    if policy.minimum_quality_tier not in _QUALITY_ORDER:
        raise ModelRouteError(f"workload {policy.workload!r} has an unknown minimum quality tier")
    tier = profile.get("tier")
    if not isinstance(tier, str) or tier not in _QUALITY_ORDER:
        raise ModelRouteError(f"profile {profile.get('name')!r} has an unknown model quality tier")
    if _QUALITY_ORDER[tier] < _QUALITY_ORDER[policy.minimum_quality_tier]:
        raise ModelRouteError(
            f"profile {profile.get('name')!r} quality tier {tier!r} is below workload "
            f"{policy.workload!r} minimum {policy.minimum_quality_tier!r}")


def describe_route_choice(workload: str, profile_name: str, route_name: str, *,
                          policy_path: str | os.PathLike[str] | None = None,
                          registry_path: str | os.PathLike[str] | None = None,
                          environ: dict[str, str] | None = None,
                          access_config: dict[str, Any] | None = None,
                          registry: dict[str, Any] | None = None) -> dict[str, Any]:
    """Safe configured choice metadata; never probes a provider or the DB.

    Compatibility describes the workload contract, not runtime availability.
    A confidential SAYGM choice stays unverified until stage/execute obtains
    catalog evidence. Credential values are never included.
    """
    result: dict[str, Any] = {"profile": profile_name, "route": route_name,
                              "applicable": False,
                              "compatible": False, "verification_required": False}
    try:
        policy, profile, route = inspect_route_choice(
            workload, profile_name, route_name,
            policy_path=policy_path, registry_path=registry_path,
            access_config=access_config, registry=registry)
        result.update({
            "applicable": True,
            "model": profile.get("model", ""),
            "provider": profile.get("provider", ""),
            "billing": route.billing, "privacy": route.privacy,
            "adapter": route.adapter, "capabilities": list(route.capabilities),
            "credential_env": route.credential_env,
            "required_privacy": policy.privacy,
            "required_capabilities": list(policy.required_capabilities),
            "minimum_quality_tier": policy.minimum_quality_tier,
            "model_quality_tier": profile.get("tier"),
            "limits": policy.limits.as_metadata(),
        })
        assert_model_quality(policy, profile)
        env = environ if environ is not None else os.environ
        result["key_present"] = bool(route.credential_env and env.get(route.credential_env))
        if route.name == "saygm" and policy.privacy != "local_only":
            result["verification_required"] = True
            result["status"] = "catalog_verification_required"
            result["capabilities"] = []
            result["reason"] = "Exact model and capabilities require catalog verification"
            return result
        if (route.adapter in {"subscription_runtime", "codex_subscription_runtime"}
                and "tools" in route.capabilities):
            result.update({
                "verification_required": True, "status": "runtime_verification_required",
                "reason": "Exact runtime and tool contract require capability acceptance",
                "capabilities": [],
            })
            return result
        _assert_policy_route(policy, route)
        result.update({"compatible": True, "status": "configured", "reason": None})
    except ModelRouteError as exc:
        result.update({"status": "incompatible", "reason": str(exc)})
    return result


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
    _assert_unique_canonical_identities(registry)
    profile = _resolve_model_profile(registry, policy.profile, workload=workload)
    assert_model_quality(policy, profile)
    route = _route_for_profile(profile, policy.route, (load_access_config(policy_path).get("routes") or {}))
    return _resolved_route(policy, profile, route, env, policy_path=policy_path,
                           saygm_model=saygm_model)


def _resolved_route(policy: WorkloadPolicy, profile: dict[str, Any], route: AccessRoute,
                     env: dict[str, str], *,
                     policy_path: str | os.PathLike[str] | None = None,
                     saygm_model: Any | None = None,
                     model: str | None = None) -> ResolvedModelRoute:
    assert_model_quality(policy, profile)
    if policy.workload == "skill_eval":
        limits = load_skill_evaluation_limits(policy_path)
        if limits is None:
            raise ModelRouteError("skill evaluation is disabled")
        if route.billing != "subscription" and limits.spend_ceiling_usd is None:
            raise ModelRouteError(
                "paid skill evaluation requires an explicit spend ceiling"
            )
    if route.name == "saygm" and saygm_model is not None:
        route, model = _bind_saygm_model(profile, route, saygm_model)
    if route.name == "saygm" and model is None and policy.privacy != "local_only":
        raise ModelRouteError("SAYGM catalog verification is required before execution")
    _assert_policy_route(policy, route)
    if route.credential_env and not env.get(route.credential_env):
        raise ModelRouteError(
            f"route {route.name!r} for workload {policy.workload!r} requires {route.credential_env}")
    return ResolvedModelRoute(
        workload=policy.workload,
        profile_name=str(profile["name"]),
        model=model or str(profile["model"]),
        provider=("saygm" if route.name == "saygm" else
                  "subscription" if route.adapter in {"subscription_runtime", "codex_subscription_runtime"} else
                  str(profile.get("provider") or "")),
        base_url=(_NATIVE_ROUTE_URLS[route.name] if route.name in _NATIVE_ROUTE_URLS else
                  "" if route.name == "local" else str(route.base_url or "")),
        route=route,
        api_key_env=route.credential_env,
        identity=str(profile.get("identity") or ""),
        priority=policy.priority,
        limits=policy.limits,
    )


def resolve_model_route_checked(workload: str, *, explicit_profile: str | None = None,
                                explicit_route: str | None = None,
                                policy_path: str | os.PathLike[str] | None = None,
                                registry_path: str | os.PathLike[str] | None = None,
                                environ: dict[str, str] | None = None) -> ResolvedModelRoute:
    """Resolve a route and obtain SAYGM catalog proof when it is required."""
    policy = resolve_policy(workload, explicit_profile=explicit_profile,
                            explicit_route=explicit_route, path=policy_path)
    registry = _load_model_registry(registry_path)
    _assert_unique_canonical_identities(registry)
    profile = _resolve_model_profile(registry, policy.profile, workload=workload)
    assert_model_quality(policy, profile)
    route = _route_for_profile(profile, policy.route, (load_access_config(policy_path).get("routes") or {}))
    model = None
    if policy.route == "saygm" and policy.privacy != "local_only":
        route, model = verify_saygm_route_choice(profile, route, environ=environ, privacy=policy.privacy)
    return _resolved_route(policy, profile, route,
                           environ if environ is not None else os.environ,
                           policy_path=policy_path, model=model)


def available_routes(profile: dict[str, Any],
                     route_catalog: dict[str, Any] | None = None) -> list[str]:
    """Return configured routes without exposing credential values."""
    names = set((profile.get("routes") or {}).keys())
    if profile.get("api_key_env"):
        names.add("direct_api")
    if route_catalog is not None:
        names.update(route_catalog)
        applicable = []
        for name in sorted(names):
            try:
                _route_for_profile(profile, name, route_catalog)
            except ModelRouteError:
                continue
            applicable.append(name)
        return applicable
    return sorted(names)


def _validate_client_endpoint(resolved: ResolvedModelRoute) -> None:
    # Validate even manually supplied route objects before credentials are
    # read or an SDK client is constructed. Config is not an egress authority.
    route = resolved.route
    if route.name not in _ROUTE_CONTRACTS:
        raise ModelRouteError(f"unknown route {route.name!r}")
    adapter, billing, privacy = _ROUTE_CONTRACTS[route.name]
    if route.adapter != adapter or route.billing != billing:
        raise ModelRouteError(f"route {route.name!r} violates its protected adapter or billing contract")
    permitted_privacy = {privacy, "confidential"} if route.name == "saygm" else {privacy}
    if route.privacy not in permitted_privacy:
        raise ModelRouteError(f"route {route.name!r} violates its protected privacy contract")
    if route.credential_env != resolved.api_key_env:
        raise ModelRouteError(f"route {route.name!r} credential binding is inconsistent")
    if route.name in _NATIVE_ROUTE_URLS or route.name == "local":
        expected_url = _NATIVE_ROUTE_URLS.get(route.name, "")
        if route.credential_env or route.base_url or resolved.base_url != expected_url:
            raise ModelRouteError(f"route {route.name!r} cannot carry an API endpoint or credential")
    if route.name == "direct_api" and (not route.base_url or route.base_url != resolved.base_url):
        raise ModelRouteError("direct_api requires an authoritative registry endpoint binding")
    if (route.name == "saygm" or resolved.provider == "saygm"
            or resolved.route.adapter == "saygm_gateway"):
        from jarvis.saygm import SayGMError, validate_endpoint
        try:
            validate_endpoint(resolved.base_url, resolved.api_key_env)
            validate_endpoint(resolved.route.base_url or resolved.base_url,
                              resolved.route.credential_env)
        except SayGMError as exc:
            raise ModelRouteError(str(exc)) from exc


def make_route_client(resolved: ResolvedModelRoute, *, timeout: float | None = 60,
                      max_retries: int = 0) -> Any:
    """Build only an API-compatible client for an already validated route.

    Subscription and local adapters intentionally fail until their official
    runtimes are installed and capability-tested; this prevents a route label
    from masquerading as an implementation.
    """
    _validate_client_endpoint(resolved)
    if resolved.route.adapter == "subscription_runtime":
        if "tools" in resolved.route.capabilities:
            from jarvis.subscription_tools import (
                TOOL_CAPABILITY_RECEIPT_ENV,
                TOOLS_ENABLED_ENV,
                ClaudeSubscriptionToolClient,
            )
            if os.environ.get(TOOLS_ENABLED_ENV) != "1":
                raise ModelRouteError("subscription native tool adapter is disabled")
            receipt_path = os.environ.get(TOOL_CAPABILITY_RECEIPT_ENV)
            if not receipt_path or not Path(receipt_path).is_file():
                raise ModelRouteError("native tool capability acceptance receipt is required")
            # The request's exact tool set is available only at execute_chat.
            # execute_request validates that receipt against model, executable,
            # version, argv and tool names before starting a provider process.
            return ClaudeSubscriptionToolClient(resolved.model)
        if os.environ.get("JARVIS_SUBSCRIPTION_TEXT_ENABLED") != "1":
            raise ModelRouteError("subscription text adapter is disabled")
        from jarvis.subscription import SubscriptionTextClient
        return SubscriptionTextClient(resolved.model, timeout=float(timeout or 120))
    if resolved.route.adapter == "codex_subscription_runtime":
        if "tools" in resolved.route.capabilities:
            raise ModelRouteError("Codex subscription native tools are not verified")
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
    _validate_client_endpoint(resolved)
    if resolved.route.adapter == "subscription_runtime":
        if "tools" in resolved.route.capabilities:
            raise ModelRouteError("subscription native tools require asynchronous execution")
        if os.environ.get("JARVIS_SUBSCRIPTION_TEXT_ENABLED") != "1":
            raise ModelRouteError("subscription text adapter is disabled")
        from jarvis.subscription import SubscriptionSyncTextClient
        return SubscriptionSyncTextClient(resolved.model, timeout=float(timeout or 120))
    if resolved.route.adapter == "codex_subscription_runtime":
        if "tools" in resolved.route.capabilities:
            raise ModelRouteError("Codex subscription native tools are not verified")
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
