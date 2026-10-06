"""Upgrade Agent: the LLM-driven brain of the self-development loop (plan section 3.5).

The agent interprets a natural-language goal, reads allowlisted source files,
and produces edits — but its only tools are the closed set below, backed by
jarvis/selfedit/service.py. It never gets shell or raw git access.

Behavior contract (any model swapped in via config must pass this — it is the
acceptance suite for the agent's brain):
- Present every proposed diff before validating; summarize validation
  results before submitting. No silent edits.
- One automatic repair attempt after a failed validation; if it fails again,
  end the session and report. Never retry-submit in a loop.
- Decline goals that require off-allowlist changes and say they need human
  development.
- Hard loop bounds: max_iterations tool cycles and max_session_minutes
  wall-clock, from config/upgrade_agent.yaml (overridable via env).

Planner model
-------------
Which model does the planning comes from the model registry:
``config/model_profiles.yaml`` (the routine profile pool) joined with
``config/model_endpoints.yaml`` (the human-only endpoint/credential map) by
:func:`load_model_registry` — the one loader (override path via
``JARVIS_UPGRADE_MODELS``; docs/plans/MORTIMER_MODEL_REGISTRY_SPLIT_PLAN.md).
Selection order: an explicit per-session ``profile`` argument >
``JARVIS_UPGRADE_PROFILE`` env > the registry's ``default`` key, which
``supervisor:`` pins in the endpoints file. Profiles are OpenAI-compatible
endpoints; the API key comes from the endpoint's ``api_key_env`` — keys
live in the environment, never in config. A profile
with ``temperature: null`` OMITS the parameter entirely (DEVIATIONS.md D-003:
kimi-k2.x rejects any value other than 1).

If no registry file exists, the agent falls back to the legacy single-slot
config in ``config/upgrade_agent.yaml`` (provider/model/base_url/temperature,
with JARVIS_UPGRADE_MODEL / JARVIS_UPGRADE_BASE_URL env overrides) —
byte-identical behavior to before the registry existed.

The client factory is injectable for tests.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import os
import re
import threading
import time
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable
from urllib.parse import urlsplit

import yaml

from jarvis import effort, llm_client
from jarvis.model_execution import (
    ModelContextMessage,
    ModelExecutionRequest,
    ModelToolCall,
    ModelToolReference,
    execute_chat,
)
from jarvis.model_routing import (
    ModelRouteError,
    ResolvedModelRoute,
    make_route_client,
    resolve_model_route,
)
from jarvis.privacy_policy import DataPolicy
from jarvis.repo_map import load_architecture_suffix, load_repo_map_suffix
from jarvis.selfedit.service import SelfEditService
from jarvis.usage_ledger import (
    provider_from_base_url,
    record_completion,
    record_execution_result,
)

logger = logging.getLogger(__name__)


def _log_safe_failure(event: str, exc: Exception) -> None:
    """Log a bounded failure category without exception or traceback data."""
    logger.warning("%s error_type=%s", event, type(exc).__name__[:80])

DEFAULT_CONFIG_PATH = (
    Path(__file__).resolve().parents[2] / "config" / "upgrade_agent.yaml"
)
DEFAULT_CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"
# The model registry is two files joined by load_model_registry()
# (docs/plans/MORTIMER_MODEL_REGISTRY_SPLIT_PLAN.md): the DENIED endpoint /
# credential map and the ROUTINE profile pool. The legacy single file is
# still read when neither split file exists (rollback, §9) and whenever a
# test or script points at one explicitly (§3 item 2).
ENDPOINTS_FILENAME = "model_endpoints.yaml"
PROFILES_FILENAME = "model_profiles.yaml"
LEGACY_REGISTRY_FILENAME = "upgrade_models.yaml"
DEFAULT_ENDPOINTS_PATH = DEFAULT_CONFIG_DIR / ENDPOINTS_FILENAME
DEFAULT_PROFILES_PATH = DEFAULT_CONFIG_DIR / PROFILES_FILENAME
DEFAULT_REGISTRY_PATH = DEFAULT_CONFIG_DIR / LEGACY_REGISTRY_FILENAME
REGISTRY_PATH_ENV = "JARVIS_UPGRADE_MODELS"
PROFILE_ENV = "JARVIS_UPGRADE_PROFILE"

# Planner call bounds + model failover (Larry 2026-08-22: "if we are going
# to choose a model that ends up unreachable then we need a way to kill the
# request so that it can be delegated to another model — spin on a dead
# model is not a great look").
#
# 120s matches COUNCIL_MEMBER_TIMEOUT_S deliberately: the council already
# solved this exact problem (bound the call, drop the member, keep going)
# and one number is better than two that drift. Calibration note from the
# same day: a measured kimi-k3 planner call took 112.2s for a two-sentence
# answer (always-on thinking, 1,369 completion tokens), so kimi-k3 sits
# just inside this bound and WILL trip it under any additional load. That
# is the correct outcome, not a mis-set threshold — a planner that needs
# ~2 minutes per round cannot finish a 25-round session inside
# max_session_minutes anyway, so failing over is strictly better than
# spinning.
PLANNER_CALL_TIMEOUT_S = 120.0

# At most two failovers per session: three distinct models failing
# unreachably is an outage, not a bad pick, and continuing to shop makes
# the user wait longer for the same bad news.
MAX_PLANNER_FAILOVERS = 2

SYSTEM_PROMPT = """You are the Jarvis Upgrade Agent. You develop upgrades to the
Jarvis interface by proposing code edits, under these NON-NEGOTIABLE rules:

1. `main` changes only via a human merging a pull request on GitHub. You can
   only open PRs. You can never merge, force-push, or touch main.
2. You may only read and edit files on the self-edit allowlist. Routine
   (Tier A): UI sources under web/src and web/public, non-secret config
   (including the model PROFILE pool, config/model_profiles.yaml: a profile
   names an endpoint id and may never carry a base_url or key),
   jarvis/prompts.py, jarvis/skills, jarvis/services, mcp_servers, tests,
   docs. Core (Tier B): the rest of jarvis/ — the voice pipeline
   (jarvis/bot), the agents (jarvis/agents), memory, wake word, scripts —
   is EDITABLE too, with ceremony: a core edit runs an extra import gate
   and its PR is flagged CORE CHANGE for a human run before merge. Do not
   decline a core goal because it is "not UI" — do it, carefully, in
   small self-contained edits. Human-only (Tier 0), never written:
   the self-edit machinery itself (jarvis/selfedit, jarvis/admin,
   upgrade_agent.py), the allowlist, the model ENDPOINTS file
   (config/model_endpoints.yaml: hosts and keys), jarvis/db.py
   migrations, the vault and .env, CI, dependency manifests, and under
   macos/: Package.swift, Package.resolved, plists, entitlements,
   scripts/, GlassSpike/ and MortimerShell/. The Swift SOURCES of
   macos/JarvisKit and macos/MortimerHost ARE editable (routine): a
   changed Swift package is gated by `swift build` and `swift test` in
   the session worktree, and its PR is flagged SWIFT CHANGE because it
   reaches the app only when Larry deploys (DEPLOY-MAIN rebuilds it).
   file_read shows a Tier-0 file read-only, and an edit_propose to one is
   saved as a PROPOSAL (a patch under docs/proposals/) that Larry approves
   and applies himself; say so in your summary, naming the file. Vault
   files (*.vault), .env and runtime data (data/) are refused outright:
   decline that part with the path named.
3. Your only tools are file_read, edit_propose, session_validate,
   session_submit. There is no shell and no git tool.
4. Propose edits with edit_propose, then call session_validate, and only if
   every check passes call session_submit. If validation fails you get ONE
   repair attempt; if it fails again, stop and report the failure.
5. Keep edits small, self-contained, and explained by a one-line rationale.

When you decline, you MUST call session_decline with the reason. Do not
decline in prose alone.

Work style: first read the files relevant to the goal, then propose complete
new file contents for each file you change, then validate, then submit.
Reply to the user with a concise summary of what you changed (or why you
declined), in plain language."""

# MORTIMER_OPTIMIZATION_PLAN.md Phase 3 — "the executor's escalation rule
# is load-bearing." Injected by run() only alongside a supplied `plan`
# (P7's plan-adoption kwarg): the invariant a plan gives the executor is
# NOT "this spec is complete" (no spec is) — it is that every
# irreversible or architectural decision already got made IN the plan.
# When what the executor actually finds diverges from what the plan
# describes, the correct move is to stop and report the divergence, not
# bridge the gap with its own architectural judgment — that decision
# belongs in a plan revision (a human, or the planning pathway), not a
# silent edit. An unplanned single-file self-edit has no spec to diverge
# from, so this text is meaningless noise there and stays out.
PLAN_DIVERGENCE_RULE = (
    "A pre-written plan may not perfectly match what you actually find in "
    "the repository. That is expected. What is NOT allowed is bridging a "
    "real divergence yourself: if the plan's design assumptions do not "
    "hold, or an irreversible/architectural decision the plan should have "
    "made was left for you, stop and report the divergence in your "
    "summary instead of deciding it on your own. The plan is where "
    "architectural decisions live; your job is executing it, not "
    "revising it."
)

TOOL_SPECS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "file_read",
            "description": "Read an allowlisted repo file.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_propose",
            "description": "Propose a full-file replacement for an allowlisted "
                           "path. Returns the diff.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "new_content": {"type": "string"},
                    "rationale": {"type": "string"},
                },
                "required": ["path", "new_content", "rationale"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "session_validate",
            "description": "Run the validation gates (allowlist, backend "
                           "imports, core imports for a core change, "
                           "pytest).",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "session_submit",
            "description": "Commit, push the session branch and open a PR. "
                           "Only works after validation has passed. Merge "
                           "remains manual on GitHub.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "session_decline",
            "description": "Decline the goal because it requires changes "
                           "outside the self-edit allowlist. Provide the "
                           "reason. Use this INSTEAD of replying in prose "
                           "that you cannot do it.",
            "parameters": {
                "type": "object",
                "properties": {"reason": {"type": "string"}},
                "required": ["reason"],
            },
        },
    },
]


def load_agent_config(path: str | Path | None = None, section: str | None = None) -> dict:
    """`section`, when given (D1/D7: e.g. "app_build"), overlays that
    subsection's `max_iterations`/`max_session_minutes` on top of the
    top-level provider/model/base_url/temperature defaults — those stay
    self-edit's legacy fallback values either way; the registry profile
    resolution in UpgradeAgent.__init__ overrides them for both workflows
    whenever the model registry has profiles, which it does. A
    missing section falls back to the top-level (self-edit) loop bounds,
    so an app_build section left unconfigured degrades gracefully rather
    than raising."""
    cfg_path = Path(path) if path else DEFAULT_CONFIG_PATH
    data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    bounds = data.get(section, {}) if section else data
    if not isinstance(bounds, dict):
        bounds = {}
    return {
        "provider": data.get("provider", "openai"),
        "model": os.environ.get("JARVIS_UPGRADE_MODEL")
                 or data.get("model", "gpt-4.1-mini"),
        "base_url": os.environ.get("JARVIS_UPGRADE_BASE_URL")
                    or data.get("base_url", "https://api.openai.com/v1"),
        "temperature": float(data.get("temperature", 0.2)),
        "max_iterations": int(bounds.get("max_iterations", data.get("max_iterations", 10))),
        "max_session_minutes": int(
            bounds.get("max_session_minutes", data.get("max_session_minutes", 30))
        ),
    }


class UnknownModelProfileError(ValueError):
    """Raised when a requested planner profile is not in the registry."""


class ModelRegistryError(ValueError):
    """The model registry is unsafe or inconsistent and must not be used.

    Raised, never logged-and-continued: a registry that silently loads
    with a profile dropped, an endpoint missing, or a credential key in
    the routine file is worse than one that refuses to load (split plan
    D3, §3 item 3, §10).
    """


class ModelRegistryIdentityError(ModelRegistryError, ModelRouteError):
    """Unsafe canonical identity, including on the legacy routing-off path."""


_CANONICAL_IDENTITY = re.compile(r"[a-z0-9][a-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9_./:-]{0,255}\Z")
_PROVIDER_NAMESPACE = {"moonshot": "moonshotai"}


def _wire_model_identity(profile: dict[str, Any]) -> str:
    provider = profile.get("provider")
    if provider is None:
        base_url = profile.get("base_url")
        if not isinstance(base_url, str):
            raise ModelRegistryIdentityError("model registry has an unavailable canonical identity")
        try:
            host = urlsplit(base_url).hostname
        except ValueError:
            host = None
        if host not in {"api.openai.com", "api.anthropic.com", "api.moonshot.ai",
                        "api.moonshot.cn", "openrouter.ai", "api.saygm.com"}:
            raise ModelRegistryIdentityError("model registry has an unavailable canonical identity")
        provider = provider_from_base_url(base_url)
    model = profile.get("model")
    if (not isinstance(provider, str) or provider != provider.strip()
            or not isinstance(model, str) or model != model.strip()):
        raise ModelRegistryIdentityError("model registry has an unavailable canonical identity")
    namespace = _PROVIDER_NAMESPACE.get(provider, provider)
    if namespace in {"openrouter", "saygm"}:
        # A gateway is a route, not the vendor whose model casts the vote.
        # Its qualified wire model is sufficient; a bare gateway model is
        # unavailable without an explicit canonical identity.
        identity = model
    elif model.startswith(namespace + "/"):
        identity = model
    else:
        identity = f"{namespace}/{model}"
    if not _CANONICAL_IDENTITY.fullmatch(identity) or "//" in identity or identity.endswith("/"):
        raise ModelRegistryIdentityError("model registry has an unavailable canonical identity")
    return identity


def canonical_model_identity(profile: dict[str, Any]) -> str:
    """One model identity regardless of profile name, credentials or route.

    Historical profiles without ``identity`` derive it from their provider
    and wire model. This never adds keys to a frozen historical registry.
    An explicitly malformed identity is a refusal, never a request to
    guess a replacement from the profile name.
    """
    if not isinstance(profile, dict):
        raise ModelRegistryIdentityError("model registry has an unavailable canonical identity")
    if "identity" not in profile:
        return _wire_model_identity(profile)
    identity = profile["identity"]
    if (not isinstance(identity, str) or not _CANONICAL_IDENTITY.fullmatch(identity)
            or "//" in identity or identity.endswith("/")):
        raise ModelRegistryIdentityError("model registry has an unavailable canonical identity")
    return identity


def validate_model_registry_identities(registry: dict[str, Any]) -> dict[str, str]:
    """Reject alias votes before credential lookup, independent of rollout.

    Also accepts an already loaded registry, so membership callers cannot
    bypass the loader's check by supplying a previously cached snapshot.
    Authoritative wire identities additionally catch two profiles that
    give different declared identities to the exact same provider model.
    """
    if not isinstance(registry, dict) or not isinstance(registry.get("profiles"), dict):
        raise ModelRegistryIdentityError("model registry has an unavailable canonical identity")
    identities: dict[str, str] = {}
    seen: set[str] = set()
    seen_wire: set[str] = set()
    seen_endpoint_models: set[tuple[str, str, str]] = set()
    for name, profile in registry["profiles"].items():
        identity = canonical_model_identity(profile)
        if identity in seen:
            raise ModelRegistryIdentityError("model registry has duplicate canonical model identities")
        seen.add(identity)
        try:
            wire_identity = _wire_model_identity(profile)
        except ModelRegistryIdentityError:
            # Explicit identities remain authoritative when a gateway's
            # opaque wire model or historical sparse profile cannot derive
            # a qualified wire identity. Missing identities already failed.
            wire_identity = None
        if wire_identity is not None:
            if wire_identity in seen_wire:
                raise ModelRegistryIdentityError("model registry has duplicate canonical model identities")
            seen_wire.add(wire_identity)
        provider, base_url, model = (profile.get("provider"), profile.get("base_url"), profile.get("model"))
        if (isinstance(provider, str) and isinstance(model, str) and model
                and (base_url is None or isinstance(base_url, str))):
            endpoint_model = (provider, (base_url or "").rstrip("/"), model)
            if endpoint_model in seen_endpoint_models:
                raise ModelRegistryIdentityError("model registry has duplicate canonical model identities")
            seen_endpoint_models.add(endpoint_model)
        identities[name] = identity
    return identities


# Split plan D3 — the credential boundary is VOCABULARY. A profile in the
# routine file may not say where a request goes or which key it carries;
# those come only from its endpoint in the denied file. `provider` is
# joined from the endpoint too (D2), and `routes` is refused because
# jarvis.model_routing reads a per-profile route's own base_url and
# credential_env. Checked at every depth, together with any value that
# looks like a URL, so a nested map cannot carry a host either.
PROFILE_FORBIDDEN_KEYS = frozenset({
    "base_url", "api_base", "api_key", "api_key_env", "credential_env",
    "host", "url", "headers", "default_headers", "extra_headers",
    "provider", "routes",
})
#: The only keys an endpoint entry may carry (the denied file is strict so
#: that a typo is a load error, not a silently ignored field).
ENDPOINT_KEYS = frozenset({"provider", "kind", "base_url", "api_key_env", "route", "label"})
#: What the join copies from an endpoint into each of its profiles (D2).
#: Only keys the endpoint actually has, so a credential-less endpoint
#: (A1: codex-subscription) yields a profile with NO base_url/api_key_env
#: keys, exactly as before the split.
JOINED_ENDPOINT_KEYS = ("provider", "base_url", "api_key_env")


def _read_yaml_mapping(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ModelRegistryError(f"{path}: the model registry must be a mapping")
    return data


def registry_source(path: str | os.PathLike[str] | None = None, *,
                    config_dir: str | os.PathLike[str] | None = None) -> Path:
    """The file :func:`load_model_registry` reads first (it may not exist).

    Precedence: explicit ``path`` > ``JARVIS_UPGRADE_MODELS`` > the default
    under ``config_dir`` (``config/`` unless given). The default is the
    split profile pool whenever EITHER split file exists — so a missing
    endpoints file is an error rather than a silent fall back — and the
    legacy ``upgrade_models.yaml`` only when neither does (rollback, §9).
    """
    if path is None:
        path = os.environ.get(REGISTRY_PATH_ENV) or None
    if path is not None:
        return Path(path)
    base = Path(config_dir) if config_dir is not None else DEFAULT_CONFIG_DIR
    endpoints = base / ENDPOINTS_FILENAME
    profiles = base / PROFILES_FILENAME
    legacy = base / LEGACY_REGISTRY_FILENAME
    if endpoints.exists() or profiles.exists():
        if legacy.exists():
            raise ModelRegistryError(
                f"both the split registry ({endpoints.name}, {profiles.name}) and "
                f"the legacy {legacy} exist in {base}; remove one — the loader "
                "will not guess which is authoritative")
        return profiles
    return legacy


def _host_bearing(node: Any, trail: str) -> list[str]:
    """Every forbidden key or URL-looking value under ``node`` (D3)."""
    found: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            where = f"{trail}.{key}" if trail else str(key)
            if str(key) in PROFILE_FORBIDDEN_KEYS:
                found.append(where)
            else:
                found.extend(_host_bearing(value, where))
    elif isinstance(node, list):
        for i, value in enumerate(node):
            found.extend(_host_bearing(value, f"{trail}[{i}]"))
    elif isinstance(node, str) and "://" in node:
        found.append(trail)
    return found


def _validate_endpoints(raw: Any, source: Path) -> dict[str, dict[str, Any]]:
    if not isinstance(raw, dict) or not raw:
        raise ModelRegistryError(f"{source}: `endpoints:` must be a non-empty mapping")
    endpoints: dict[str, dict[str, Any]] = {}
    for eid, entry in raw.items():
        where = f"{source}: endpoint {eid!r}"
        if not isinstance(entry, dict):
            raise ModelRegistryError(f"{where} must be a mapping")
        unknown = sorted(set(map(str, entry)) - ENDPOINT_KEYS)
        if unknown:
            raise ModelRegistryError(f"{where} has unknown keys {unknown}")
        if not entry.get("provider"):
            raise ModelRegistryError(f"{where} names no provider")
        kind = entry.get("kind", "api")
        if kind == "api":
            if not entry.get("base_url") or not entry.get("api_key_env"):
                raise ModelRegistryError(
                    f"{where} needs base_url and api_key_env (or kind: subscription)")
        elif kind == "subscription":
            if "base_url" in entry or "api_key_env" in entry:
                raise ModelRegistryError(
                    f"{where} is kind: subscription and may not carry base_url/api_key_env")
        else:
            raise ModelRegistryError(f"{where} has unknown kind {kind!r}")
        endpoints[str(eid)] = dict(entry)
    return endpoints


def load_registry_layers(path: str | os.PathLike[str] | None = None, *,
                         config_dir: str | os.PathLike[str] | None = None
                         ) -> dict[str, Any]:
    """Parse and validate the registry WITHOUT joining it.

    The first half of :func:`load_model_registry`, exposed for the readers
    that need the layers themselves (``check_env``'s catalogue report, the
    split invariants). Returns ``{"shape", "source", "endpoints_source",
    "default", "profiles", "endpoints", "supervisor"}`` where ``shape`` is
    ``"split"``, ``"legacy"`` or ``"missing"`` and ``profiles`` is the raw
    list in file order.

    Shapes (§3 item 2): a file with an ``endpoints:`` section is a whole
    split registry in one file (the §9 rollback concatenation); a file
    named ``model_profiles.yaml``, or whose profiles name an ``endpoint:``,
    is the profile pool and its endpoints come from ``model_endpoints.yaml``
    beside it; anything else is a legacy single-file registry, used as is.
    The profile pool can never be read in the legacy shape and never
    carries its own endpoints — that would put the credential map back in
    the routine file.
    """
    explicit = path is not None or bool(os.environ.get(REGISTRY_PATH_ENV))
    src = registry_source(path, config_dir=config_dir)
    empty = {"shape": "missing", "source": None, "endpoints_source": None,
             "default": None, "profiles": [], "endpoints": {}, "supervisor": None}
    if not src.exists():
        if not explicit and src.name == PROFILES_FILENAME:
            raise ModelRegistryError(
                f"{src} is missing but {src.parent / ENDPOINTS_FILENAME} exists")
        return empty
    data = _read_yaml_mapping(src)
    raw_profiles = data.get("profiles") or []
    if not isinstance(raw_profiles, list):
        raise ModelRegistryError(f"{src}: `profiles:` must be a list")
    is_pool = src.name == PROFILES_FILENAME
    names_endpoint = any(isinstance(p, dict) and "endpoint" in p for p in raw_profiles)

    if is_pool and ("endpoints" in data or "supervisor" in data):
        raise ModelRegistryError(
            f"{src} may not declare `endpoints:` or `supervisor:` — they live only "
            f"in {ENDPOINTS_FILENAME}, which is human-only")
    if "endpoints" in data:
        endpoints_doc, endpoints_src = data, src
    elif is_pool or names_endpoint:
        endpoints_src = src.parent / ENDPOINTS_FILENAME
        if not endpoints_src.exists():
            raise ModelRegistryError(
                f"{src} names endpoints but {endpoints_src} does not exist — "
                "refusing to load profiles without their endpoints")
        endpoints_doc = _read_yaml_mapping(endpoints_src)
        if "profiles" in endpoints_doc or "default" in endpoints_doc:
            raise ModelRegistryError(
                f"{endpoints_src} may not declare profiles or a default")
    else:
        # Legacy single file: today's shape, today's semantics.
        return {"shape": "legacy", "source": src, "endpoints_source": None,
                "default": data.get("default"),
                "profiles": [p for p in raw_profiles
                             if isinstance(p, dict) and p.get("name")],
                "endpoints": {}, "supervisor": None}

    endpoints = _validate_endpoints(endpoints_doc.get("endpoints"), endpoints_src)
    profiles: list[dict[str, Any]] = []
    seen: set[str] = set()
    for i, prof in enumerate(raw_profiles):
        if not isinstance(prof, dict) or not prof.get("name"):
            raise ModelRegistryError(f"{src}: profile #{i + 1} has no name")
        name = str(prof["name"])
        where = f"{src}: profile {name!r}"
        if name in seen:
            raise ModelRegistryError(f"{where} is declared twice")
        seen.add(name)
        bad = _host_bearing(prof, "")
        if bad:
            raise ModelRegistryError(
                f"{where} declares {', '.join(bad)} — endpoints, hosts and keys "
                f"belong in {ENDPOINTS_FILENAME}, never in a profile (D3)")
        endpoint = prof.get("endpoint")
        if not endpoint:
            raise ModelRegistryError(f"{where} names no endpoint")
        if str(endpoint) not in endpoints:
            raise ModelRegistryError(
                f"{where} names unknown endpoint {endpoint!r}; known: "
                f"{', '.join(sorted(endpoints))}")
        if not prof.get("identity"):
            raise ModelRegistryError(f"{where} has no identity (the join key)")
        profiles.append(prof)

    default = data.get("default")
    if default is not None and str(default) not in seen:
        raise ModelRegistryError(f"{src}: default {default!r} is not a profile")
    supervisor = endpoints_doc.get("supervisor")
    if supervisor is not None:
        if (not isinstance(supervisor, dict) or not supervisor.get("identity")
                or not supervisor.get("endpoint")):
            raise ModelRegistryError(
                f"{endpoints_src}: `supervisor:` must pin identity and endpoint")
        if str(supervisor["endpoint"]) not in endpoints:
            raise ModelRegistryError(
                f"{endpoints_src}: supervisor pins unknown endpoint "
                f"{supervisor['endpoint']!r}")
        # D4: the planner's brain is pinned in the denied file. The routine
        # `default` must name the pinned identity on the pinned endpoint;
        # re-pointing the planner is a human PR against both files. (Its
        # model STRING is checked against the generated catalogue by
        # tests/unit/test_model_registry_split.py.)
        planner = next((p for p in profiles if str(p["name"]) == str(default)), None)
        if planner is None or (
                str(planner.get("identity")) != str(supervisor["identity"])
                or str(planner.get("endpoint")) != str(supervisor["endpoint"])):
            raise ModelRegistryError(
                f"{src}: default {default!r} does not match the supervisor pin "
                f"{supervisor['identity']!r} on {supervisor['endpoint']!r} "
                f"({endpoints_src.name}) — changing the planner is a human PR")
    return {"shape": "split", "source": src, "endpoints_source": endpoints_src,
            "default": default, "profiles": profiles, "endpoints": endpoints,
            "supervisor": dict(supervisor) if supervisor else None}


def _join_profile(profile: dict[str, Any], endpoint: dict[str, Any]) -> dict[str, Any]:
    """One profile with its endpoint's provider/base_url/api_key_env merged
    in where ``endpoint:`` stood, and the ``endpoint`` key itself dropped —
    the joined profile has exactly the pre-split keys (D2, D6)."""
    joined: dict[str, Any] = {}
    for key, value in profile.items():
        if key == "endpoint":
            for ekey in JOINED_ENDPOINT_KEYS:
                if ekey in endpoint:
                    joined[ekey] = endpoint[ekey]
        else:
            joined[key] = value
    return joined


def load_model_registry(path: str | os.PathLike[str] | None = None, *,
                        config_dir: str | os.PathLike[str] | None = None
                        ) -> dict[str, Any]:
    """Load the model registry — the ONE loader (spec I6, split plan D2).

    Path precedence: explicit ``path`` > ``JARVIS_UPGRADE_MODELS`` env >
    the default under ``config/`` (``model_profiles.yaml`` joined with
    ``model_endpoints.yaml``; the legacy ``upgrade_models.yaml`` only when
    neither exists). See :func:`load_registry_layers` for the shapes.

    Returns exactly the pre-split shape, ``{"default", "profiles": {name:
    profile}}`` in file order, with each split profile's endpoint joined in,
    so no caller changes semantics. A missing file returns the empty
    registry ``{"default": None, "profiles": {}}`` so callers fall back to
    legacy mode; an unsafe or inconsistent one raises ModelRegistryError.
    Canonical identities are validated before credentials, including when
    shared model routing is disabled; aliases never become independent votes.
    """
    layers = load_registry_layers(path, config_dir=config_dir)
    if layers["shape"] == "legacy":
        names = [prof["name"] for prof in layers["profiles"]]
        if len(names) != len(set(names)):
            raise ModelRegistryError("model registry profile is declared twice")
        profiles = {prof["name"]: prof for prof in layers["profiles"]}
    else:
        endpoints = layers["endpoints"]
        profiles = {prof["name"]: _join_profile(prof, endpoints[str(prof["endpoint"])])
                    for prof in layers["profiles"]}
    registry = {"default": layers["default"], "profiles": profiles}
    validate_model_registry_identities(registry)
    return registry


# Split plan §4a: what each provider currently offers, one generated file per
# endpoint, joined to profiles by `identity`. Written by the sync job (never
# by hand); seeded from the pre-split registry with fetched_at null and
# source "seeded" so the first sync reads as a diff.
GENERATED_DIRNAME = "generated"
CATALOG_PREFIX = "model_catalog."
CATALOG_SUFFIX = ".json"
#: Every catalogue entry carries these keys (price fields null when the
#: provider publishes none), so a later price/deprecation migration is a
#: deletion rather than a re-fetch (§4a.5).
CATALOG_ENTRY_KEYS = (
    "identity", "model", "context_window", "input_price_per_mtok",
    "output_price_per_mtok", "input_modalities", "deprecation",
    "fetched_at", "source",
)


def catalog_path(endpoint: str, *, config_dir: str | os.PathLike[str] | None = None) -> Path:
    base = Path(config_dir) if config_dir is not None else DEFAULT_CONFIG_DIR
    return base / GENERATED_DIRNAME / f"{CATALOG_PREFIX}{endpoint}{CATALOG_SUFFIX}"


def load_upstream_catalogs(*, config_dir: str | os.PathLike[str] | None = None
                           ) -> dict[str, dict[str, Any]]:
    """Endpoint id -> parsed ``model_catalog.<endpoint>.json`` (§4a).

    Read-only facts about what a provider offers. Never joined INTO the
    profiles load_model_registry returns (that shape is fixed, D2/D6);
    readers that want them (check_env's age and deprecation report, the
    supervisor-pin test) ask for them here. A malformed file raises.
    """
    base = Path(config_dir) if config_dir is not None else DEFAULT_CONFIG_DIR
    out: dict[str, dict[str, Any]] = {}
    for path in sorted((base / GENERATED_DIRNAME).glob(f"{CATALOG_PREFIX}*{CATALOG_SUFFIX}")):
        endpoint = path.name[len(CATALOG_PREFIX):-len(CATALOG_SUFFIX)]
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("endpoint") != endpoint \
                or not isinstance(data.get("models"), list):
            raise ModelRegistryError(f"{path}: not a model catalogue for {endpoint!r}")
        out[endpoint] = data
    return out


def catalog_retirement(entry: dict[str, Any]) -> str | None:
    """The ISO date a catalogue entry retires on, or None (§4a.3).

    ``deprecation`` is null, an ISO date string, or a mapping carrying
    ``retires_at``; whatever the sync job writes, this is the one reader.
    """
    dep = entry.get("deprecation")
    if isinstance(dep, dict):
        dep = dep.get("retires_at")
    return str(dep)[:10] if dep else None


def resolve_profile(registry: dict[str, Any], requested: str | None = None) -> dict[str, Any]:
    """Resolve which profile to use: explicit > env > registry default."""
    validate_model_registry_identities(registry)
    profiles: dict[str, dict[str, Any]] = registry.get("profiles", {})
    name = requested or os.environ.get(PROFILE_ENV) or registry.get("default")
    if not name or name not in profiles:
        available = ", ".join(sorted(profiles)) or "(none)"
        raise UnknownModelProfileError(
            f"unknown upgrade model profile {name!r}; available profiles: {available}"
        )
    return profiles[name]


def available_models(registry_path: str | os.PathLike[str] | None = None, *,
                     registry: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """List planner profiles for pickers — includes key presence, never key material.

    `tier` (economy | mid | frontier | None) is surfaced here so the
    council module (jarvis/council/config.py) and the console's membership
    picker (MORTIMER_LLM_COUNCIL_PLAN.md D9) read it from this one place
    rather than re-parsing the registry YAML themselves.
    """
    registry = registry if registry is not None else load_model_registry(registry_path)
    validate_model_registry_identities(registry)
    default = registry.get("default")
    out: list[dict[str, Any]] = []
    for name, prof in sorted(registry.get("profiles", {}).items()):
        key_env = prof.get("api_key_env", "")
        out.append(
            {
                "name": name,
                "label": prof.get("label", name),
                "provider": prof.get("provider", ""),
                "model": prof.get("model", ""),
                "key_env": key_env,
                "key_present": bool(key_env and os.environ.get(key_env)),
                "default": name == default,
                "tier": prof.get("tier"),
            }
        )
    return out


class UpgradeAgent:
    """Drives one self-edit session from a natural-language goal."""

    def __init__(
        self,
        service: SelfEditService,
        config_path: str | Path | None = None,
        registry_path: str | os.PathLike[str] | None = None,
        profile: str | None = None,
        client_factory: Callable[[], Any] | None = None,
        *,
        config_section: str | None = None,
        system_prompt: str | None = None,
        council_workflow: str = "selfedit",
        run_id: str | None = None,
        tool_specs: list[dict[str, Any]] | None = None,
    ):
        self.service = service
        # MORTIMER_GRAPH_LAYER_PLAN.md GL9 (contract G2): the delegating sub-agent
        # run, threaded from SkillRegistry.call() through the sidecar; None for a
        # console-initiated run. Every convene() below passes it through.
        self._run_id = run_id
        # Most callers use the normal self-edit toolset. A reviewed workflow
        # may supply a narrower closed set; keep a private copy so later
        # mutation by a caller cannot widen an active agent's authority.
        self._tool_specs = json.loads(json.dumps(tool_specs if tool_specs is not None else TOOL_SPECS))
        self._workload = "app_builder" if config_section == "app_build" else "developer"
        self._execution_loop: asyncio.AbstractEventLoop | None = None
        self._execution_parent_id: str | None = None
        self._routed_client: Any = None
        self._routed_client_identity: tuple[str, str, str] | None = None
        self.cfg = load_agent_config(config_path, section=config_section)
        self._system_prompt = system_prompt or SYSTEM_PROMPT
        # Cooperative cancel (Larry 2026-08-30/31: a kimi-k3 planner sat
        # "still running" for the caption goal and nothing could stop it —
        # selfedit_revert refuses while busy, and there was no cancel at
        # all). POST /api/selfedit/cancel sets this; the edit loop checks
        # it before every planner step. It cannot interrupt a completion
        # call already in flight (that returns or hits its own read
        # timeout first), so "cancel" means "stop at the next step".
        self._cancel = threading.Event()
        # G5 (MORTIMER_SESSION_GAPS_AND_SELFEDIT_CONVERGENCE_PLAN.md): the
        # developer-loop (SubAgent) has read docs/REPO_MAP.md into its
        # prompt since the Model Discipline plan; this loop — which does
        # most of the actual self-edit authoring — never did, so a self-
        # edit session rediscovered the codebase from scratch every run.
        # `load_repo_map_suffix` is the SAME shared helper SubAgent uses
        # (jarvis/repo_map.py) — one read/cap/skip implementation, not two.
        # Keep the repository map and the architecture contract together in
        # the authoring context.  The latter is read-only guidance, not a
        # second configuration source; the loop still verifies current files
        # before proposing an edit.
        self._system_prompt += load_repo_map_suffix() + load_architecture_suffix()
        # D7 — council rounds convened from this loop are tagged with the
        # workflow that started them ("selfedit" vs "appbuild"), so
        # compute_agreement (which excludes only workflow="planning") keeps
        # treating both as judge-quality evidence without special-casing.
        self._council_workflow = council_workflow

        # Registry mode overlays the planner slot; loop bounds always come
        # from the agent config.
        self.profile_name: str | None = None
        # Kept so _next_failover_profile resolves against the SAME registry
        # this agent was constructed from (tests point it elsewhere).
        self._registry_path = registry_path
        registry = load_model_registry(registry_path)
        if registry.get("profiles"):
            prof = resolve_profile(registry, profile)
            self.profile_name = prof["name"]
            self.cfg["provider"] = prof.get("provider", self.cfg["provider"])
            self.cfg["model"] = prof.get("model", self.cfg["model"])
            self.cfg["base_url"] = prof.get("base_url") or self.cfg["base_url"]
            if "temperature" in prof:
                # null means: omit the parameter entirely (D-003)
                self.cfg["temperature"] = prof["temperature"]
            # Phase 1b (effort control) -- optional per-profile
            # output_config.effort override (model_profiles.yaml); absent
            # means self.cfg.get("effort") stays None, and
            # extra_body_for() emits nothing, exactly like an agents.yaml
            # entry with no `effort:` field.
            if "effort" in prof:
                self.cfg["effort"] = prof["effort"]
            self._api_key_env = prof.get("api_key_env", "OPENAI_API_KEY")
            self._resolved_route = None
            if os.environ.get("JARVIS_MODEL_ROUTING_ENABLED") == "1":
                try:
                    self._resolved_route = resolve_model_route(
                        self._workload, explicit_profile=self.profile_name,
                        registry_path=registry_path)
                    self.cfg["provider"] = self._resolved_route.provider
                    self.cfg["model"] = self._resolved_route.model
                    self.cfg["base_url"] = self._resolved_route.base_url
                    self._api_key_env = self._resolved_route.api_key_env or ""
                except ModelRouteError as exc:
                    self._resolved_route = exc
        else:
            self._api_key_env = "OPENAI_API_KEY"
            self._resolved_route = None

        # Uniform attribute view for status lines and tests.
        self.model = self.cfg["model"]
        self.base_url = self.cfg["base_url"]

        # MORTIMER_LLM_COUNCIL_PLAN.md D2.1/D8.1 — escalation state. Reset
        # to a clean slate at the top of run() too, so a reused agent
        # instance starts clean (a fresh UpgradeAgent per session is the
        # normal case, but tests and any future pooling should not leak
        # escalation counters across sessions).
        self._escalations_used = 0
        self._pending_council_round_id: str | None = None
        # MORTIMER_LLM_COUNCIL_V2_PLAN.md V1 — the tier-1 winning proposal,
        # carried forward into a tier-2 convene as an additional candidate.
        # (profile, content); reset alongside the other escalation state.
        self._last_council_winner: tuple[str, str] | None = None
        # V14 — at most one scope-advisor council per run (E2); reset in
        # run(), same lifecycle as the escalation counters above.
        self._scope_council_used: bool = False
        # Phase 3 Rev 3.3 — 'planned' | 'planless' for this session's
        # ledger rows (usage_ledger.record_call's plan_state); set at the
        # top of run() from whether a `plan` was supplied.
        self._plan_state: str | None = None
        self._submit_result: dict | None = None

        # Defer client construction when credentials/runtime access are
        # unavailable so run() can report a route-specific readiness error.
        subscription_adapters = {
            "subscription_runtime", "codex_subscription_runtime",
        }
        route_is_subscription = (
            isinstance(self._resolved_route, ResolvedModelRoute)
            and self._resolved_route.route.adapter in subscription_adapters
        )
        self._missing_access_reason = None
        if client_factory is not None:
            pass
        elif route_is_subscription and os.environ.get("JARVIS_SUBSCRIPTION_TEXT_ENABLED") != "1":
            self._missing_access_reason = "the subscription text adapter is disabled"
        elif (self._resolved_route is not None
              and not isinstance(self._resolved_route, ModelRouteError)
              and not route_is_subscription
              and (not self._api_key_env or not os.environ.get(self._api_key_env))):
            self._missing_access_reason = f"{self._api_key_env or 'route credential'} is not set"
        elif isinstance(self._resolved_route, ModelRouteError):
            self._missing_access_reason = str(self._resolved_route)
        elif (self._resolved_route is None
              and (not self._api_key_env or not os.environ.get(self._api_key_env))):
            self._missing_access_reason = f"{self._api_key_env or 'route credential'} is not set"
        self._key_missing = self._missing_access_reason is not None
        # Failover state (Larry 2026-08-22: "spin on a dead model is not a
        # great look"). Profiles that have already failed UNREACHABLY this
        # session are never selected again by _completion_with_failover.
        self._failed_profiles: set[str] = set()
        self._failover_notes: list[str] = []

        self._client: Any = None
        if client_factory is not None:
            self._client = client_factory()
        elif not self._key_missing:
            if self._resolved_route is None:
                self._client = self._build_client(
                    self._api_key_env, self.cfg["base_url"], self.cfg.get("provider"))

    def _build_client(self, api_key_env: str, base_url: str | None,
                      provider: str | None = None) -> Any:
        """Construct the planner client with a BOUNDED call timeout.

        Before 2026-08-22 this passed no `timeout`, so the openai SDK's
        default applied: a 600-second read timeout. `max_session_minutes`
        could not save it — that bound is checked BETWEEN iterations, and a
        hung call blocks inside the HTTP read where the loop never regains
        control. One unreachable kimi-k3 call therefore spun for up to ten
        minutes. `max_retries=0` is deliberate and load-bearing: the SDK's
        default of 2 would silently turn a 120s bound into a 360s one, and
        retrying a model that just proved unreachable is strictly worse
        than failing over to one that answers.

        `provider` (MORTIMER_OPTIMIZATION_PLAN.md Phase 1, Rev 3.2, landing
        step (ii), 2026-09-02): optional so every existing caller and test
        that only ever passed two positional args keeps working — falls
        back to base_url-detection inside llm_client.make_sync_client
        itself when omitted. Routes to jarvis/anthropic_shim.py (prompt
        caching) instead of the plain OpenAI-compat client when the
        resolved provider is "anthropic" and JARVIS_ANTHROPIC_NATIVE is
        not "0".
        """
        return llm_client.make_sync_client(
            api_key=os.environ[api_key_env],
            base_url=base_url,
            provider=provider,
            timeout=PLANNER_CALL_TIMEOUT_S,
            max_retries=0,
        )

    def model_label(self) -> str:
        """Human-readable 'profile (model)' for status lines and TTS summaries."""
        if self.profile_name:
            return f"{self.profile_name} ({self.model})"
        return self.model

    @staticmethod
    def _is_unreachable(exc: Exception) -> bool:
        """Is this failure the UNREACHABLE class, i.e. worth failing over?

        Deliberately narrow, mirroring `jarvis/keyhealth.py`'s three-verdict
        discipline (rejected / unfunded / unreachable): only a timeout, a
        connection failure, or a 5xx means "this endpoint isn't answering,
        try another one." A 4xx is a REAL error that would repeat
        identically on every profile — and worse, failing over on 4xx would
        MASK it. That is not hypothetical: on 2026-08-22 `claude-opus` sent
        a `temperature` the model rejects, 400ing every self-edit in ~38ms;
        had failover been triggered by 4xx, it would have burned through
        every profile in the registry and reported an outage instead of the
        one-line config bug it actually was.
        """
        from openai import APIConnectionError, APIStatusError, APITimeoutError

        if isinstance(exc, (APITimeoutError, APIConnectionError)):
            return True
        if isinstance(exc, APIStatusError):
            return getattr(exc, "status_code", 0) >= 500
        return False

    def _next_failover_profile(self) -> dict[str, Any] | None:
        """The next key-present registry profile that has not failed yet.

        Registry order, skipping the current profile, anything already
        failed this session, and anything whose key is absent. Returns the
        resolved profile dict, or None when nothing is left to try.
        """
        try:
            registry = load_model_registry(self._registry_path)
        except Exception:  # noqa: BLE001 — failover must never itself raise
            return None
        for entry in available_models(self._registry_path):
            name = entry["name"]
            if name == self.profile_name or name in self._failed_profiles:
                continue
            try:
                candidate = resolve_profile(registry, name)
                if os.environ.get("JARVIS_MODEL_ROUTING_ENABLED") == "1":
                    resolve_model_route(
                        self._workload, explicit_profile=name,
                        registry_path=self._registry_path,
                    )
                elif not entry.get("key_present"):
                    continue
                return candidate
            except Exception:  # noqa: BLE001 — try the next candidate
                continue
        return None

    def _completion(self, request: dict[str, Any]) -> Any:
        """One completion call, bounded and failover-capable.

        On an UNREACHABLE-class failure the current profile is retired for
        this session and the next key-present profile takes over mid-run —
        the conversation so far (`request["messages"]`) carries across
        unchanged, so the new model resumes rather than restarting.

        Larry chose announce-then-failover (2026-08-22) over ask-first even
        for an explicitly NAMED model. That is a deliberate, recorded
        narrowing of the F6-F9 rule ("an explicit request always REFUSES
        rather than silently falling back"): F6-F9 governs RESOLUTION
        failure — an unknown profile or missing key, knowable BEFORE any
        work starts — whereas this is a runtime timeout on a model that
        resolved fine and may have already done half the session. The
        no-silent-substitution half of that rule is preserved by
        `_failover_notes`, which the run summary appends mechanically, so
        Mortimer can never report work as done by a model that did not do
        it.
        """
        attempts = 0
        while True:
            # Phase 1b -- recomputed on EVERY iteration, not just once
            # before the loop: unlike SubAgent._loop (client/model fixed
            # for the whole run), a failover below can reassign
            # self._client mid-loop, and output_config.effort must track
            # whatever profile actually ends up making the request.
            # `request` itself is never mutated with this -- an ephemeral
            # copy per attempt, so a failover onto a non-Anthropic profile
            # drops it cleanly rather than leaving a stale key behind.
            # getattr(..., "") rather than a bare attribute access: the
            # record_completion call below already tolerated a test double
            # with no .base_url (it sat inside a bare try/except Exception
            # before this Phase 1b change moved the access earlier) -- a
            # fake client missing base_url now resolves to
            # provider="unknown" (never "anthropic"), so extra_body_for()
            # cleanly returns {} instead of the whole call raising.
            provider = (
                self._resolved_route.provider
                if isinstance(self._resolved_route, ResolvedModelRoute)
                else provider_from_base_url(str(getattr(self._client, "base_url", "")))
            )
            extra_body = effort.extra_body_for(
                rung=f"{self._council_workflow}_executor", provider=provider,
                explicit=self.cfg.get("effort"), model=self.model,
            )
            call_request = {**request, "extra_body": extra_body} if extra_body else request
            try:
                if isinstance(self._resolved_route, ResolvedModelRoute):
                    if self._execution_loop is None:
                        raise RuntimeError("routed planner execution loop is unavailable")
                    response = self._execution_loop.run_until_complete(
                        self._routed_completion(call_request)
                    )
                else:
                    response = self._client.chat.completions.create(**call_request)
                    try:
                        record_completion(
                            rung=f"{self._council_workflow}_executor",
                            provider=provider,
                            model=self.model,
                            response=response,
                            plan_state=self._plan_state,
                        )
                    except Exception:
                        pass
                return response
            except Exception as exc:  # noqa: BLE001 — classified immediately below
                if not self._is_unreachable(exc) or attempts >= MAX_PLANNER_FAILOVERS:
                    raise
                failed_name = self.profile_name or self.model
                self._failed_profiles.add(failed_name)
                nxt = self._next_failover_profile()
                if nxt is None:
                    logger.warning(
                        "planner_failover_exhausted failed=%s error=%s",
                        failed_name, type(exc).__name__[:80],
                    )
                    raise
                note = (
                    f"{failed_name} did not respond "
                    f"({type(exc).__name__}); continued on {nxt['name']}"
                )
                logger.warning("planner_failover from=%s to=%s error=%s",
                               failed_name, nxt["name"], type(exc).__name__[:80])
                self._failover_notes.append(note)

                self.profile_name = nxt["name"]
                self.cfg["model"] = nxt.get("model", self.cfg["model"])
                self.cfg["base_url"] = nxt.get("base_url") or self.cfg["base_url"]
                self.cfg["temperature"] = nxt.get("temperature")
                # Phase 1 Rev 3.2 fix (2026-09-02): this line's four
                # siblings above already refresh from `nxt` on every
                # failover; `provider` was the one field nothing consumed
                # until now, so it went stale silently. A native-vs-compat
                # client-construction decision now reads it, and a
                # failover FROM an Anthropic profile TO a differently-
                # provided one (or vice versa) must not build the wrong
                # kind of client on the new profile's base_url.
                self.cfg["provider"] = nxt.get("provider", self.cfg["provider"])
                # Phase 1b -- mirrors the provider refresh immediately
                # above: a failover profile's own effort setting (or its
                # absence) must replace the old profile's, not linger.
                if "effort" in nxt:
                    self.cfg["effort"] = nxt["effort"]
                self._api_key_env = nxt.get("api_key_env", "OPENAI_API_KEY")
                self.model = self.cfg["model"]
                self.base_url = self.cfg["base_url"]
                if os.environ.get("JARVIS_MODEL_ROUTING_ENABLED") == "1":
                    if self._execution_loop is not None:
                        self._execution_loop.run_until_complete(self._close_routed_client())
                    self._resolved_route = resolve_model_route(
                        self._workload, explicit_profile=self.profile_name,
                        registry_path=self._registry_path,
                    )
                    self._api_key_env = self._resolved_route.api_key_env or ""
                    self._client = None
                else:
                    self._client = self._build_client(
                        self._api_key_env, self.cfg["base_url"], self.cfg.get("provider"))

                # The retry must carry the NEW model and its temperature
                # rule (D-003), not the dead profile's.
                request["model"] = self.cfg["model"]
                request.pop("temperature", None)
                if self.cfg["temperature"] is not None:
                    request["temperature"] = self.cfg["temperature"]
                attempts += 1

    async def _close_routed_client(self) -> None:
        client = self._routed_client
        self._routed_client = None
        self._routed_client_identity = None
        if client is None:
            return
        close = getattr(client, "close", None)
        if callable(close):
            result = close()
            if inspect.isawaitable(result):
                await result

    async def _routed_completion(self, request: dict[str, Any]) -> Any:
        route = self._resolved_route
        if not isinstance(route, ResolvedModelRoute):
            raise ModelRouteError("planner route is not resolved")
        identity = (route.identity, route.route.name, route.model)
        if self._routed_client is None or self._routed_client_identity != identity:
            await self._close_routed_client()
            self._routed_client = make_route_client(
                route, timeout=PLANNER_CALL_TIMEOUT_S, max_retries=0,
            )
            self._routed_client_identity = identity

        policy = DataPolicy(route.route.privacy, f"{self._workload}-planner")
        context = _planner_context_messages(request.get("messages"), policy)
        references = tuple(
            ModelToolReference(
                spec["function"]["name"],
                spec["function"]["parameters"],
                spec["function"].get("description", ""),
            )
            for spec in request.get("tools", TOOL_SPECS)
        )
        execution_request = ModelExecutionRequest(
            workload=route.workload,
            task_id=f"{self._council_workflow}-planner:{uuid.uuid4().hex}",
            parent_request_id=self._execution_parent_id or uuid.uuid4().hex,
            instructions="",
            context=context,
            tools=references,
            data_policy=policy,
            timeout_s=PLANNER_CALL_TIMEOUT_S,
            temperature=request.get("temperature"),
            extra_body=request.get("extra_body"),
        )
        operation = asyncio.create_task(execute_chat(
            execution_request, route,
            client_factory=lambda _route: self._routed_client,
        ))
        while not operation.done():
            if self._cancel.is_set():
                operation.cancel()
                break
            await asyncio.wait({operation}, timeout=0.05)
        result = await operation
        # Cancellation may land after execute_chat completes but before this
        # coroutine resumes. Do not ledger or expose a stale completion in
        # that race; the synchronous run loop converts this into its normal
        # structured cancelled result.
        if self._cancel.is_set():
            raise asyncio.CancelledError
        record_execution_result(
            f"{self._council_workflow}_executor", result,
            session_id=self._run_id,
            plan_state=self._plan_state,
        )
        message = SimpleNamespace(
            content=result.text or None,
            tool_calls=[
                SimpleNamespace(
                    id=call.tool_call_id,
                    type="function",
                    function=SimpleNamespace(
                        name=call.name,
                        arguments=call.raw_arguments or json.dumps(
                            dict(call.arguments), separators=(",", ":")
                        ),
                    ),
                    model_extra=dict(call.provider_extras),
                )
                for call in result.tool_calls
            ],
            model_extra=dict(result.provider_extras),
        )
        usage = None
        if result.prompt_tokens is not None and result.completion_tokens is not None:
            usage = SimpleNamespace(
                prompt_tokens=result.prompt_tokens,
                completion_tokens=result.completion_tokens,
                total_tokens=result.total_tokens,
            )
        return SimpleNamespace(
            id=result.response_id,
            choices=[SimpleNamespace(message=message)],
            usage=usage,
        )

    def run(
        self, goal: str, on_event: Callable[[dict], None] | None = None,
        *, plan: str | None = None,
    ) -> dict:
        """Run synchronously while keeping one async client loop per session."""
        loop = asyncio.new_event_loop()
        self._execution_loop = loop
        self._execution_parent_id = self._run_id or f"{self._council_workflow}:{uuid.uuid4().hex}"
        try:
            return self._run_with_execution_loop(goal, on_event, plan=plan)
        finally:
            if not loop.is_closed():
                try:
                    loop.run_until_complete(self._close_routed_client())
                except Exception as exc:  # noqa: BLE001 — cleanup cannot mask the session result
                    _log_safe_failure("planner_async_client_cleanup_failed", exc)
                loop.close()
            self._execution_loop = None
            self._execution_parent_id = None

    def _run_with_execution_loop(
        self, goal: str, on_event: Callable[[dict], None] | None = None,
        *, plan: str | None = None,
    ) -> dict:
        """Execute a full session: start → edit loop → validate → submit.

        Never raises; returns a result dict with ok/summary plus session state.

        `plan` (MORTIMER_PLANNING_PATHWAY_PLAN.md P7): an optional pre-
        written implementation plan — from the planning pathway's
        POST /api/plan/adopt or POST /api/selfedit/run's own `plan` param
        — injected as a system message right after the goal, before the
        edit loop's first completion call. Same injection SHAPE as the
        mid-run council escalation brief below (a system message wrapping
        the plan text), just at session start instead of after a failure.
        PLAN_DIVERGENCE_RULE (Phase 3) rides in the same message, ahead
        of the plan text — see that constant's comment.
        """
        if self._cancel.is_set():
            return {"ok": False, "cancelled": True, "session_started": False,
                    "summary": "Cancelled before starting a development session.", "status": self.service.status()}
        if self._key_missing:
            return {
                "ok": False,
                "summary": (
                    f"{self._missing_access_reason}; the {self.model_label()} planner "
                    "cannot run until its configured route is ready"
                ),
                "session_started": False,
                "status": self.service.status(),
            }

        # D2.1 — a reused agent instance starts with a clean escalation slate.
        self._escalations_used = 0
        self._pending_council_round_id = None
        self._last_council_winner = None  # V1 — clean slate per session
        self._scope_council_used = False  # V14 — clean slate per session
        self._failed_profiles = set()     # failover — clean slate per session
        self._failover_notes = []
        self._plan_state = "planned" if plan else "planless"  # Rev 3.3 ledger tag
        # 2026-09-07 (review F6): a run "ended" is not a run "submitted".
        # The loop's `ok` means the planner stopped cleanly — including by
        # writing prose after a failed validation. What the user needs to
        # hear is whether a pull request exists, so the submit result is
        # recorded here mechanically (never from the planner's prose) and
        # returned alongside `ok`.
        self._submit_result: dict | None = None

        started = time.monotonic()
        if not self.service.branch:
            # SE8 — the planner path carries the same run_id the developer
            # path does, so a session opened here is joinable to its
            # delegating run without a timestamp join.
            res = self.service.start_session(goal, run_id=self._run_id)
            if not res["ok"]:
                return {"ok": False, "summary": res["error"],
                        "status": self.service.status()}

        messages = [
            {"role": "system", "content": self._system_prompt},
            {"role": "user", "content": goal},
        ]
        if plan:
            messages.append({
                "role": "system",
                "content": (
                    PLAN_DIVERGENCE_RULE + "\n\n"
                    "A pre-written implementation plan for this goal "
                    "follows. Follow it.\n\n" + plan
                ),
            })
        repairs_used = 0
        summary = "the agent reached its iteration limit without finishing"
        ok = False

        # MORTIMER_LLM_COUNCIL_V2_PLAN.md V10 — the ONLY structural change
        # to this loop: a growable budget instead of a fixed range(), so a
        # tier-2 escalation late in a session can't win a council round and
        # then die on the iteration cap before the retry acts. The
        # wall-clock check inside the loop body is unchanged and stays the
        # absolute outer bound.
        iterations_used = 0
        iterations_budget = self.cfg["max_iterations"]
        # G6 (MORTIMER_SESSION_GAPS_AND_SELFEDIT_CONVERGENCE_PLAN.md):
        # halfway through the ORIGINAL budget (not a council-extended one —
        # this checkpoint is about the session's initial allotment, not a
        # moving target), if zero edits have been proposed yet, force a
        # convergence nudge. Two live self-edit runs (the independent-
        # display-windows build and the model-card fix) died at the cap
        # having produced ZERO edit_propose calls — the whole budget spent
        # reading/orienting. Equality (not >=) makes this fire exactly
        # once: iterations_used only increases, and a later council-retry
        # budget extension can't push it back to this value.
        halfway_checkpoint = self.cfg["max_iterations"] // 2
        cancelled = False
        # Phase 3 Rev 3.3 — why the loop stopped, for _close_pending_round
        # (only consulted when a council brief was injected and its retry
        # never reached session_validate). Falls through as
        # "iteration_limit" when the `while` condition itself ends the loop.
        end_reason = "iteration_limit"
        seen_tool_call_ids: set[str] = set()
        while iterations_used < iterations_budget:
            if self._cancel.is_set():
                cancelled = True
                end_reason = "cancelled"
                summary = ("cancelled by the user before the next planner step; "
                           "no changes were submitted")
                break
            iterations_used += 1
            if iterations_used == halfway_checkpoint and not self.service.proposals:
                messages.append({
                    "role": "system",
                    "content": (
                        "You are halfway through this session's iteration budget "
                        "and have not proposed a single edit yet. Stop reading "
                        "further files unless strictly necessary — call "
                        "edit_propose now with a concrete change, even a partial "
                        "one, so the remaining iterations can refine it instead "
                        "of being spent entirely on exploration."
                    ),
                })
            if time.monotonic() - started > self.cfg["max_session_minutes"] * 60:
                end_reason = "time_limit"
                summary = "session time limit reached; no changes were submitted"
                break
            request: dict[str, Any] = {
                "model": self.cfg["model"],
                "messages": messages,
                "tools": self._tool_specs,
            }
            if self.cfg["temperature"] is not None:
                request["temperature"] = self.cfg["temperature"]
            try:
                response = self._completion(request)
            except asyncio.CancelledError:
                cancelled = True
                end_reason = "cancelled"
                summary = (
                    "cancelled by the user while the planner was running; "
                    "no changes were submitted"
                )
                break
            # A cancellation can arrive immediately after a completion
            # returns. Suppress its content and every tool call before they
            # can affect the sandbox or the next planner request.
            if self._cancel.is_set():
                cancelled = True
                end_reason = "cancelled"
                summary = (
                    "cancelled by the user while the planner was running; "
                    "no changes were submitted"
                )
                break
            message = response.choices[0].message
            tool_calls = list(getattr(message, "tool_calls", None) or [])
            if not tool_calls:
                summary = message.content or ""
                ok = True
                end_reason = "prose_end"
                break
            response_call_ids = [getattr(call, "id", None) for call in tool_calls]
            if any(
                not isinstance(call_id, str) or not call_id.strip()
                or len(call_id) > 256 or call_id in seen_tool_call_ids
                for call_id in response_call_ids
            ) or len(set(response_call_ids)) != len(response_call_ids):
                summary = (
                    "the provider repeated an invalid or previously used "
                    "tool-call identity; no tool in this batch was executed"
                )
                end_reason = "tool_call_identity_replay"
                break
            seen_tool_call_ids.update(response_call_ids)
            messages.append(_assistant_message(message))
            for tc in tool_calls:
                self._emit(on_event, {"type": "agent_tool", "tool": tc.function.name})
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                result = self._dispatch(tc.function.name, args)
                if tc.function.name == "session_decline" and result.get("declined"):
                    reason = result.get("reason", "")
                    messages.append({
                        "role": "tool", "tool_call_id": tc.id,
                        "content": json.dumps(result),
                    })
                    # MORTIMER_LLM_COUNCIL_V2_PLAN.md V14 — E2: at most one
                    # scope-advisor council per run (by counter, not
                    # judgment). Advisory only: the brief rides in
                    # `summary`; the session still ends declined either way.
                    scope_brief = None
                    if not self._scope_council_used:
                        self._scope_council_used = True
                        try:
                            allowlist_text = self.service.describe_boundary()
                        except Exception:  # noqa: BLE001 — best-effort context
                            allowlist_text = "(allowlist file unavailable)"
                        scope_brief = self._maybe_scope_council(
                            goal=goal, reason=reason, allowlist=allowlist_text,
                        )
                    if scope_brief:
                        reason = reason + "\n\n[Council scope advice]\n" + scope_brief
                    self._close_pending_round("declined")
                    self._emit(on_event, {"type": "agent_done", "ok": False,
                                          "declined": True})
                    return {"ok": False, "declined": True, "summary": reason,
                            "status": self.service.status()}
                if tc.function.name == "session_validate":
                    # D8.1 — the FIRST validate result after an escalation
                    # is what "did the retry validate" means; recorded
                    # once, then cleared, regardless of ok/fail, so a
                    # later un-escalated validate in the same retry's own
                    # one-repair budget doesn't overwrite it.
                    if self._pending_council_round_id is not None:
                        round_id = self._pending_council_round_id
                        self._pending_council_round_id = None
                        try:
                            from jarvis.council.council import record_retry_validated
                            record_retry_validated(round_id, bool(result.get("ok")))
                        except Exception as exc:  # noqa: BLE001 — never break the agent loop
                            _log_safe_failure(
                                "council_record_retry_validated_call_failed", exc
                            )
                if tc.function.name == "session_validate" and not result.get("ok"):
                    repairs_used += 1
                    if repairs_used > 1:
                        council_brief = self._maybe_escalate(
                            goal=goal, trigger="E1",
                            context={"diff": self.service.proposals,
                                     "checks": result.get("checks")},
                        )
                        if council_brief is None:
                            result = {
                                "ok": False,
                                "error": "validation failed again after the single "
                                         "allowed repair attempt — stop and report "
                                         "the failure to the user",
                                "checks": result.get("checks"),
                            }
                            messages.append({
                                "role": "tool", "tool_call_id": tc.id,
                                "content": json.dumps(result),
                            })
                            summary = ("validation failed twice; session ended without "
                                       "submitting. " + json.dumps(result.get("checks")))
                            self._close_pending_round("unfinished")
                            self._emit(on_event, {"type": "agent_done", "ok": False})
                            return {"ok": False, "summary": summary,
                                    "status": self.service.status()}
                        messages.append({
                            "role": "tool", "tool_call_id": tc.id,
                            "content": json.dumps(result),
                        })
                        # Correction to the plan's literal D2.1 snippet: the
                        # inner `for tc in tool_calls` loop is nested inside
                        # the outer iteration-budget `while` loop (V10), so
                        # a bare `continue` here would only advance to the
                        # NEXT tool_call in this same batch, not resume the
                        # outer loop as the plan's own prose says it should.
                        # `break` is what actually resumes the outer loop,
                        # since the inner loop is the last statement in the
                        # outer loop's body. Any tool_calls in this batch
                        # that were never reached still need a tool-role
                        # response before the next completion() call, or the
                        # API rejects the next request — so they get an
                        # explicit "skipped" result rather than being
                        # silently dropped from `messages`.
                        for remaining_tc in tool_calls[tool_calls.index(tc) + 1:]:
                            messages.append({
                                "role": "tool", "tool_call_id": remaining_tc.id,
                                "content": json.dumps({
                                    "ok": False,
                                    "error": "skipped — a council escalation "
                                             "started before this tool call "
                                             "was processed",
                                }),
                            })
                        # Retry once with the council's winning approach as
                        # added context.
                        messages.append({
                            "role": "system",
                            "content": (
                                "A council of models reviewed this failure. Their "
                                "highest-scored corrected approach follows. Follow it, then "
                                "validate again.\n\n" + council_brief
                            ),
                        })
                        repairs_used = 0          # the retry gets its own repair budget
                        # V10 — grant extra iterations so this council-
                        # guided retry isn't starved by budget the failed
                        # attempts already spent. Lazy import: same
                        # circular-import rationale as _maybe_escalate's.
                        from jarvis.council.config import COUNCIL_RETRY_EXTRA_ITERATIONS
                        iterations_budget += COUNCIL_RETRY_EXTRA_ITERATIONS
                        break                     # resume the outer `while` loop
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result)[:8000],
                })

        # G6 — name the REAL cause of a natural iteration-budget exhaustion
        # when it happened with zero edit proposals: not a failed edit, a
        # session that never got to a first one. Only reachable when the
        # loop exited by exhausting `iterations_budget` (the time-limit and
        # validation-failure paths already set/return their own summary).
        if (
            not ok
            and summary == "the agent reached its iteration limit without finishing"
            and not self.service.proposals
        ):
            summary = (
                "the session never converged on a first edit within its "
                "iteration budget — every iteration was spent reading and "
                "orienting, not failing on a bad edit; a plan_path or named "
                "files would likely narrow this"
            )

        # Failover disclosure — a MECHANICAL backstop, not a prompt
        # instruction, mirroring the `[ran on <model>]` suffix delegate.py
        # appends: grounded by construction, so Mortimer can never report
        # work as done by a model that did not do it. This is what keeps
        # announce-then-failover honest for an explicitly NAMED model.
        if self._failover_notes:
            summary = (summary or "") + " [" + "; ".join(self._failover_notes) + "]"

        self._close_pending_round(end_reason)
        self._emit(on_event, {"type": "agent_done", "ok": ok})
        return {
            "ok": ok, "summary": summary, "status": self.service.status(),
            "failovers": list(self._failover_notes),
            "final_profile": self.profile_name,
            "cancelled": cancelled,
            "submitted": self._submit_result is not None,
            "pr_url": (self._submit_result or {}).get("pr_url"),
        }

    def request_cancel(self) -> None:
        """Ask the running edit loop to stop at its next step (see
        __init__). Safe to call from any thread; idempotent."""
        self._cancel.set()
        cancel = getattr(self.service, "cancel", None)
        if callable(cancel):
            cancel()

    @property
    def cancel_requested(self) -> bool:
        return self._cancel.is_set()

    def _close_pending_round(self, reason: str) -> None:
        """MORTIMER_OPTIMIZATION_PLAN.md Phase 3 Rev 3.3 (2026-09-03). Called
        from every session exit. If a council brief was injected this
        session and its retry never reached session_validate (which is the
        only place _pending_council_round_id is otherwise cleared), record
        WHY as council_rounds.retry_outcome = "no_retry:<reason>" and say so
        at WARNING — before this, that case wrote nothing, and
        retry_validated stayed NULL on every round ever recorded, so "is
        the council earning its cost" had no data behind it at all.
        Never raises (D13); lazy import for the usual circular-import
        reason."""
        round_id = self._pending_council_round_id
        if round_id is None:
            return
        self._pending_council_round_id = None
        logger.warning(
            "council_retry_never_validated round_id=%s reason=%s", round_id, reason,
        )
        try:
            from jarvis.council.council import record_retry_outcome
            record_retry_outcome(round_id, f"no_retry:{reason}")
        except Exception as exc:  # noqa: BLE001 — never break the agent loop
            _log_safe_failure("council_record_retry_outcome_call_failed", exc)

    def _maybe_escalate(self, *, goal: str, trigger: str,
                        context: dict) -> str | None:
        """MORTIMER_LLM_COUNCIL_PLAN.md D2.1. Returns the winning
        proposal's content, or None to fall through to the ordinary
        failure path. Never raises (D13).

        Lazy imports: jarvis.council.council and jarvis.council.config
        both import jarvis.agents.upgrade_agent at module level (for
        load_model_registry/available_models), so importing them here —
        inside the method, not at module load time — avoids a circular
        import.
        """
        from jarvis.council.config import (
            COUNCIL_MAX_ESCALATIONS,
            COUNCIL_PLANNER_START_TIER,
        )

        if self._escalations_used >= COUNCIL_MAX_ESCALATIONS:
            return None
        # MORTIMER_OPTIMIZATION_PLAN.md Phase 3: this placement="planner"
        # escalation starts at COUNCIL_PLANNER_START_TIER (2), not tier 1 —
        # see council/config.py's comment on that constant for why (in
        # short: with only tiers 1-2 defined, this caps a session to one
        # real escalation attempt; a would-be 2nd attempt computes tier=3,
        # which resolve_members() rejects, and falls through below exactly
        # like "council unavailable").
        tier = self._escalations_used + COUNCIL_PLANNER_START_TIER
        self._escalations_used += 1
        # MORTIMER_LLM_COUNCIL_V2_PLAN.md V1 — carry the previous tier's
        # winning proposal into tier >= 2 as an additional candidate.
        if tier >= 2 and self._last_council_winner is not None:
            context = dict(context)
            context["carry_forward"] = {
                "profile": self._last_council_winner[0],
                "content": self._last_council_winner[1],
            }
        try:
            from jarvis.council.council import convene
            result = asyncio.run(convene(
                workflow=self._council_workflow, placement="planner", trigger=trigger,
                goal=goal, tier=tier, context=context, run_id=self._run_id,
            ))
        except Exception as exc:                    # noqa: BLE001
            _log_safe_failure("council_escalation_failed", exc)
            return None
        if result is None or result.winner is None:
            return None
        # V1 — remembered immediately, before the existing
        # _pending_council_round_id write-back, so a subsequent tier-2
        # escalation in the same session carries this round's winner.
        self._last_council_winner = (result.winner.profile, result.winner.content)
        # D8.1 — remembered so the NEXT session_validate result (the
        # retry this brief produces) can be written back as
        # retry_validated.
        self._pending_council_round_id = result.round_id
        return result.winner.content

    def _maybe_scope_council(self, *, goal: str, reason: str,
                             allowlist: str) -> str | None:
        """MORTIMER_LLM_COUNCIL_V2_PLAN.md V14 — E2. Shaped exactly like
        `_maybe_escalate` (lazy imports, `asyncio.run`, catches
        everything, returns `result.winner.content` or `None`), but for
        the scope-advisor prompt pair: `placement='scope'`, always tier
        1 (there is no "second failure" concept for a decline), and does
        NOT touch `_escalations_used` — the escalation ladder is for E1
        only. Advisory only: the caller decides what to do with the
        returned brief; nothing here executes it."""
        try:
            from jarvis.council.council import convene
            result = asyncio.run(convene(
                workflow=self._council_workflow, placement="scope", trigger="E2",
                goal=goal, tier=1,
                context={"reason": reason, "allowlist": allowlist}, run_id=self._run_id,
            ))
        except Exception as exc:                    # noqa: BLE001
            _log_safe_failure("council_scope_council_failed", exc)
            return None
        if result is None or result.winner is None:
            return None
        return result.winner.content

    def _dispatch(self, name: str, args: dict) -> dict:
        """Closed toolset — unknown tools are refused outright."""
        if name == "file_read":
            return self.service.read_file(str(args.get("path", "")))
        if name == "edit_propose":
            return self.service.propose_edit(
                str(args.get("path", "")),
                str(args.get("new_content", "")),
                str(args.get("rationale", "")),
            )
        if name == "session_validate":
            return self.service.validate()
        if name == "session_submit":
            result = self.service.submit()
            if result.get("ok"):
                self._submit_result = result
            return result
        if name == "session_decline":
            return {"ok": False, "declined": True,
                    "reason": str(args.get("reason", ""))}
        return {"ok": False, "error": f"unknown tool: {name}"}

    @staticmethod
    def _emit(on_event: Callable[[dict], None] | None, event: dict) -> None:
        if on_event is not None:
            try:
                on_event(event)
            except Exception as exc:  # noqa: BLE001 — observers must not break agents
                logger.warning("planner_event_callback_failed error_type=%s",
                               type(exc).__name__[:64])


APPBUILD_PROFILE_ENV = "JARVIS_APPBUILD_PROFILE"

APP_BUILD_SYSTEM_PROMPT = """You are the Mortimer App-Build Agent. You develop
applications by proposing code edits inside the app's OWN private GitHub
repository, under these NON-NEGOTIABLE rules:

1. The app's default branch changes only via a human merging a pull request
   on GitHub. You can only open PRs. You can never merge, force-push, or
   touch the default branch directly.
2. You may edit any file in the app's repo EXCEPT .git/**, .env and .env.*,
   any *.vault file, and .github/workflows/** — you must never grant
   yourself CI powers on the app repo. If the goal requires touching one of
   those, decline that part and say it requires human development.
3. Your only tools are file_read, edit_propose, session_validate,
   session_submit. There is no shell and no git tool.
4. Propose edits with edit_propose, then call session_validate, and only if
   every check passes call session_submit. If validation fails you get ONE
   repair attempt; if it fails again, stop and report the failure. If the
   app has no mortimer.app.yaml validation manifest, session_validate will
   say so explicitly — treat that PR as UNVALIDATED in your summary, never
   as passing.
5. Keep edits small, self-contained, and explained by a one-line rationale.

When you decline, you MUST call session_decline with the reason. Do not
decline in prose alone.

Work style: first read the files relevant to the goal, then propose complete
new file contents for each file you change, then validate, then submit.
Reply to the user with a concise summary of what you changed (or why you
declined), in plain language."""


class AppBuildAgent(UpgradeAgent):
    """D1/D7: the SAME edit loop as UpgradeAgent, bound to an AppWorkspace
    instead of a SelfEditWorkspace — a foreign app repo instead of
    Mortimer's own. Three differences from the base class, all supplied
    via UpgradeAgent's existing constructor parameters (no loop code is
    duplicated): the app-build system prompt, the `app_build:` loop-bound
    section of config/upgrade_agent.yaml (own max_iterations/
    max_session_minutes — app builds legitimately run longer than
    self-edits), and JARVIS_APPBUILD_PROFILE as the env-level profile
    fallback (independent of self-edit's JARVIS_UPGRADE_PROFILE, so the
    two workflows can be pointed at different planner tiers). Council
    escalation rounds this agent convenes are tagged
    workflow="appbuild" (D7) via the base class's `council_workflow` param."""

    def __init__(
        self,
        workspace: Any,
        config_path: str | Path | None = None,
        registry_path: str | os.PathLike[str] | None = None,
        profile: str | None = None,
        client_factory: Callable[[], Any] | None = None,
        run_id: str | None = None,
    ):
        # Selection order mirrors resolve_profile's own: explicit >
        # env > registry default. resolve_profile only checks
        # JARVIS_UPGRADE_PROFILE, so the app-build env fallback is applied
        # here, before the base class ever calls it.
        profile = profile or os.environ.get(APPBUILD_PROFILE_ENV)
        super().__init__(
            workspace, config_path=config_path, registry_path=registry_path,
            profile=profile, client_factory=client_factory,
            config_section="app_build", system_prompt=APP_BUILD_SYSTEM_PROMPT,
            council_workflow="appbuild", run_id=run_id,
        )


def _assistant_message(message: Any) -> dict:
    result = {
        "role": "assistant",
        "content": message.content,
        "tool_calls": [
            {
                "id": tc.id,
                "type": "function",
                "function": {"name": tc.function.name,
                             "arguments": tc.function.arguments},
                **(getattr(tc, "model_extra", None) or {}),
            }
            for tc in message.tool_calls
        ],
    }
    result.update(getattr(message, "model_extra", None) or {})
    return result


def _planner_context_messages(
    messages: Any, policy: DataPolicy,
) -> tuple[ModelContextMessage, ...]:
    """Convert planner protocol history without losing tool-call identity."""
    if not isinstance(messages, list):
        raise ValueError("planner messages must be a list")
    context: list[ModelContextMessage] = []
    pending_names: dict[str, str] = {}
    for message in messages:
        if not isinstance(message, dict):
            raise ValueError("planner message must be a mapping")
        role = message.get("role")
        content = message.get("content")
        if role == "assistant" and message.get("tool_calls"):
            if not isinstance(content, (str, type(None))):
                raise ValueError("planner assistant content must be text")
            calls: list[ModelToolCall] = []
            for raw_call in message["tool_calls"]:
                function = raw_call.get("function") or {}
                call_id = raw_call.get("id")
                name = function.get("name")
                raw_arguments = function.get("arguments")
                if not isinstance(raw_arguments, str):
                    raise ValueError("planner tool call arguments must be serialized JSON")
                try:
                    arguments = json.loads(raw_arguments)
                except json.JSONDecodeError as exc:
                    raise ValueError("planner tool call arguments are malformed") from exc
                if not isinstance(arguments, dict):
                    raise ValueError("planner tool arguments must be a JSON object")
                extras = {key: value for key, value in raw_call.items()
                          if key not in {"id", "type", "function"}}
                calls.append(ModelToolCall(
                    call_id, name, arguments, raw_arguments, extras,
                ))
                pending_names[call_id] = name
            message_extras = {
                key: value for key, value in message.items()
                if key not in {"role", "content", "tool_calls"}
            }
            context.append(ModelContextMessage(
                "assistant", content or "", policy, tool_calls=tuple(calls),
                provider_extras=message_extras,
            ))
        elif role == "tool":
            call_id = message.get("tool_call_id")
            name = pending_names.pop(call_id, None)
            if not name or not isinstance(content, str):
                raise ValueError("planner tool result has no matching call")
            context.append(ModelContextMessage(
                "tool", content, policy, name=name, tool_call_id=call_id,
            ))
        elif role in {"system", "user", "assistant"} and isinstance(content, str):
            context.append(ModelContextMessage(role, content, policy))
        else:
            raise ValueError("planner history has an unsupported message")
    if pending_names:
        raise ValueError("planner history ends before its tool calls return")
    return tuple(context)
