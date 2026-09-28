"""Deterministic, fail-closed primary-skill selection for the v2 rollout.

This module is pure policy: callers supply the candidate snapshot and trusted
runtime evidence. It does not load packages, inspect secrets, invoke models,
or change the legacy selector. That keeps dry-run evaluation independent from
the voice hot path until the explicit selection flag is enabled by a later
acceptance increment.
"""
from __future__ import annotations

import logging
import re
import threading
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import yaml

from jarvis.agent_skills import (
    MATCH_THRESHOLD,
    MIN_SHARED_TOKENS,
    Skill,
    _overlap_score,
    _tokens,
    load_skills,
    read_skill_registry,
    skill_selection_v2_enabled,
    skills_workspace_enabled,
)
from jarvis.skill_catalog import SkillCatalogEntry, inspect_package
from jarvis.skill_service import (
    current_credential_presence,
    evaluate_readiness,
)

MAX_SKILL_INJECTION_CHARS = 16_000
RUNTIME_PACKAGE_SNAPSHOT_TTL_SECONDS = 60.0
SKILL_CAPABILITIES_PATH = Path(__file__).resolve().parents[1] / "config" / "skill_capabilities.yaml"
_CAPABILITY_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_TOOL_RE = re.compile(r"^[a-z][a-z0-9_]{0,127}$")
_ROUTE_CAPABILITIES = frozenset({"text", "tools", "images"})
_RUNTIME_SNAPSHOT_LOCK = threading.RLock()
_RUNTIME_SNAPSHOT_BUILD_LOCK = threading.Lock()
_RUNTIME_PACKAGE_SNAPSHOT: _RuntimePackageSnapshot | None = None
_RUNTIME_SNAPSHOT_REFRESHING: set[tuple] = set()
_RUNTIME_SNAPSHOT_LAST_REFRESH_ATTEMPT: dict[tuple, float] = {}
_RUNTIME_SNAPSHOT_RETRY_BACKOFF_SECONDS = 5.0
_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class _RuntimePackageSnapshot:
    created_at: float
    key: tuple
    skills: tuple[Skill, ...]
    catalog: Mapping[str, SkillCatalogEntry]


def clear_runtime_package_snapshot() -> None:
    """Clear the short-lived package snapshot (tests and explicit refresh)."""
    global _RUNTIME_PACKAGE_SNAPSHOT
    with _RUNTIME_SNAPSHOT_LOCK:
        _RUNTIME_PACKAGE_SNAPSHOT = None
        _RUNTIME_SNAPSHOT_REFRESHING.clear()
        _RUNTIME_SNAPSHOT_LAST_REFRESH_ATTEMPT.clear()


def prewarm_runtime_package_snapshot() -> bool:
    """Prepare the 60-second package snapshot before the voice request path."""
    if not skill_selection_v2_enabled() or not skills_workspace_enabled():
        return False
    _runtime_package_snapshot()
    return True


def _runtime_package_snapshot() -> _RuntimePackageSnapshot:
    """Load validated package metadata once per registry revision and TTL."""
    from jarvis import agent_skills as skill_runtime

    names, pins, version, valid = read_skill_registry()
    if not valid or version != 2 or pins is None:
        raise ValueError("revision_pin_unverified")
    key = (
        str(skill_runtime.SKILLS_DIR.resolve()),
        str(skill_runtime.SKILLS_CONFIG.resolve()),
        tuple(names),
        tuple(sorted(pins.items())),
    )
    now = time.monotonic()
    with _RUNTIME_SNAPSHOT_LOCK:
        # Registry history is not a cache: retain retry state only for the
        # single active key so repeated package revisions cannot grow it.
        for old_key in tuple(_RUNTIME_SNAPSHOT_LAST_REFRESH_ATTEMPT):
            if old_key != key:
                del _RUNTIME_SNAPSHOT_LAST_REFRESH_ATTEMPT[old_key]
        cached = _RUNTIME_PACKAGE_SNAPSHOT
        if cached is not None and cached.key == key:
            if now - cached.created_at < RUNTIME_PACKAGE_SNAPSHOT_TTL_SECONDS:
                return cached
            # Package pins have not changed. Keep using the prior immutable
            # snapshot while a refresh runs; the selected package is still
            # re-read and compared with the current pin before injection.
            last_attempt = _RUNTIME_SNAPSHOT_LAST_REFRESH_ATTEMPT.get(key)
            if (key not in _RUNTIME_SNAPSHOT_REFRESHING
                    and (last_attempt is None or now - last_attempt
                         >= _RUNTIME_SNAPSHOT_RETRY_BACKOFF_SECONDS)):
                _RUNTIME_SNAPSHOT_REFRESHING.add(key)
                _RUNTIME_SNAPSHOT_LAST_REFRESH_ATTEMPT[key] = now
                try:
                    _start_runtime_snapshot_refresh(key)
                except RuntimeError:
                    _RUNTIME_SNAPSHOT_REFRESHING.discard(key)
                    _LOGGER.warning("skill_snapshot_refresh_start_failed")
            return cached

    return _build_runtime_package_snapshot(key, skill_runtime)


def _start_runtime_snapshot_refresh(key: tuple) -> None:
    """Refresh an expired same-revision snapshot outside the request path."""
    thread = threading.Thread(
        target=_refresh_runtime_package_snapshot,
        args=(key,),
        name="mortimer-skill-snapshot-refresh",
        daemon=True,
    )
    thread.start()


def _refresh_runtime_package_snapshot(key: tuple) -> None:
    """Publish a complete refresh atomically, retaining the previous on error."""
    from jarvis import agent_skills as skill_runtime

    try:
        _build_runtime_package_snapshot(key, skill_runtime)
    except Exception as exc:  # noqa: BLE001 — old snapshot remains pin-checked
        _LOGGER.warning("skill_snapshot_refresh_failed error_type=%s",
                        type(exc).__name__[:64])
    finally:
        with _RUNTIME_SNAPSHOT_LOCK:
            _RUNTIME_SNAPSHOT_REFRESHING.discard(key)


def _build_runtime_package_snapshot(key: tuple, skill_runtime) -> _RuntimePackageSnapshot:
    """Build and atomically publish a complete snapshot for the current key."""
    global _RUNTIME_PACKAGE_SNAPSHOT
    with _RUNTIME_SNAPSHOT_BUILD_LOCK:
        with _RUNTIME_SNAPSHOT_LOCK:
            cached = _RUNTIME_PACKAGE_SNAPSHOT
            if (cached is not None and cached.key == key
                    and time.monotonic() - cached.created_at
                    < RUNTIME_PACKAGE_SNAPSHOT_TTL_SECONDS):
                return cached

        skills = tuple(load_skills(
            directory=skill_runtime.SKILLS_DIR,
            config_path=skill_runtime.SKILLS_CONFIG,
        ))
        catalog = {
            skill.name: inspect_package(
                skill.path.parent, config_path=skill_runtime.SKILLS_CONFIG,
            )
            for skill in skills
        }
        confirmed_names, confirmed_pins, confirmed_version, confirmed_valid = (
            read_skill_registry()
        )
        confirmed_key = (
            str(skill_runtime.SKILLS_DIR.resolve()),
            str(skill_runtime.SKILLS_CONFIG.resolve()),
            tuple(confirmed_names),
            tuple(sorted((confirmed_pins or {}).items())),
        )
        if (not confirmed_valid or confirmed_version != 2 or confirmed_key != key):
            raise ValueError("skill_registry_changed_during_snapshot")
        snapshot = _RuntimePackageSnapshot(
            created_at=time.monotonic(), key=key, skills=skills, catalog=catalog,
        )
        with _RUNTIME_SNAPSHOT_LOCK:
            _RUNTIME_PACKAGE_SNAPSHOT = snapshot
        return snapshot


def load_capability_requirements(
    path: str | Path | None = None,
) -> dict[str, tuple[frozenset[str], frozenset[str]]]:
    """Read the strict, reviewed capability-to-tool/route requirement map."""
    selected = Path(path) if path is not None else SKILL_CAPABILITIES_PATH
    try:
        data = yaml.safe_load(selected.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ValueError("skill capability registry unavailable") from exc
    if not isinstance(data, dict) or set(data) != {"schema_version", "capabilities"}:
        raise ValueError("invalid skill capability registry")
    if data.get("schema_version") != 1 or not isinstance(data.get("capabilities"), dict):
        raise ValueError("unsupported skill capability registry")

    normalized: dict[str, tuple[frozenset[str], frozenset[str]]] = {}
    for capability, requirement in data["capabilities"].items():
        if not isinstance(capability, str) or not _CAPABILITY_RE.fullmatch(capability):
            raise ValueError("invalid capability ID")
        if (not isinstance(requirement, dict)
                or set(requirement) != {"route_capabilities", "tools"}):
            raise ValueError("invalid capability requirement")
        routes, tools = requirement["route_capabilities"], requirement["tools"]
        if (not isinstance(routes, list) or not isinstance(tools, list)
                or any(not isinstance(value, str) or value not in _ROUTE_CAPABILITIES
                       for value in routes)
                or any(not isinstance(value, str) or not _TOOL_RE.fullmatch(value)
                       for value in tools)
                or len(routes) != len(set(routes)) or len(tools) != len(set(tools))):
            raise ValueError("invalid capability inventory requirement")
        normalized[capability] = (frozenset(routes), frozenset(tools))
    return normalized


def capabilities_for_inventory(
    route_capabilities: frozenset[str],
    available_tools: frozenset[str],
    *,
    requirements: Mapping[str, tuple[frozenset[str], frozenset[str]]] | None = None,
) -> frozenset[str]:
    """Return only capabilities fully supported by this route and tool set."""
    registry = requirements if requirements is not None else load_capability_requirements()
    return frozenset(
        capability for capability, (routes, tools) in registry.items()
        if routes <= route_capabilities and tools <= available_tools
    )


def select_runtime_primary_skill(
    task: str,
    *,
    registry: object,
    server_names: Sequence[str],
    resolved_route: object | None,
    private_route: bool,
    sensitive_task: bool,
    explicit_skill_id: str | None = None,
) -> SkillSelectionDecision:
    """Run the opt-in selector using host-owned route and tool evidence.

    Both independent rollout flags are mandatory. Missing or malformed runtime
    evidence produces no skill selection; there is no fallback to the legacy
    matcher while the v2 selection flag is explicitly enabled.
    """
    if not skill_selection_v2_enabled():
        return SkillSelectionDecision(None, "selector_disabled", ())
    if not skills_workspace_enabled():
        return SkillSelectionDecision(None, "revision_enforcement_disabled", ())
    route = getattr(resolved_route, "route", None)
    route_capabilities = frozenset(getattr(route, "capabilities", ()) or ())
    route_privacy = getattr(route, "privacy", None)
    if "text" not in route_capabilities or route_privacy not in {
        "approved_external", "confidential", "local_only",
    }:
        return SkillSelectionDecision(None, "model_route_unverified", ())
    if sensitive_task and (not private_route or route_privacy == "approved_external"):
        return SkillSelectionDecision(None, "privacy_compatibility_unverified", ())

    try:
        available_tools = frozenset(registry.tools_for(list(server_names)))
        capabilities = capabilities_for_inventory(route_capabilities, available_tools)
        snapshot = _runtime_package_snapshot()
        skills = snapshot.skills
        catalog = snapshot.catalog
        pins = dict(snapshot.key[3])
        readiness = {
            skill_id: evaluate_readiness(
                entry,
                tool_inventory=None,
                credential_presence=current_credential_presence(entry.required_credentials),
                runtime_tools=available_tools,
                revision_pins=pins,
                revision_pins_complete=True,
                revision_enforcement=True,
                route_compatible=True,
            ).state
            for skill_id, entry in catalog.items()
        }
        privacy_compatible = (
            frozenset(catalog)
            if (not sensitive_task or private_route) else frozenset()
        )
    except Exception:  # noqa: BLE001 — selector evidence fails closed per run
        return SkillSelectionDecision(None, "runtime_evidence_unavailable", ())

    return select_primary_skill(
        task, skills, catalog,
        available_tools=available_tools,
        available_capabilities=capabilities,
        readiness=readiness,
        privacy_compatible_skill_ids=privacy_compatible,
        explicit_skill_id=explicit_skill_id,
    )


@dataclass(frozen=True)
class SkillCandidateDecision:
    skill_id: str
    score: float
    shared_token_count: int
    threshold_met: bool
    eligible: bool
    reason: str


@dataclass(frozen=True)
class SkillSelectionDecision:
    selected: Skill | None
    reason: str
    candidates: tuple[SkillCandidateDecision, ...]
    supporting: Skill | None = None
    support_reason: str | None = None


def select_primary_skill(
    task: str,
    skills: Sequence[Skill],
    catalog: Mapping[str, SkillCatalogEntry],
    *,
    available_tools: frozenset[str] | None,
    available_capabilities: frozenset[str] | None,
    readiness: Mapping[str, str],
    privacy_compatible_skill_ids: frozenset[str] | None,
    explicit_skill_id: str | None = None,
    threshold: float = MATCH_THRESHOLD,
    max_injection_chars: int = MAX_SKILL_INJECTION_CHARS,
) -> SkillSelectionDecision:
    """Choose one eligible skill using reviewed evidence and stable ordering.

    Explicit selection bypasses lexical scoring only; it cannot bypass enabled
    state, readiness, tool/capability compatibility, or the prompt budget.
    Unknown evidence is a refusal. At most one independently eligible support
    is added when both reviewed manifests declare mutual compatibility and the
    combined prompt body fits the same fixed budget.
    """
    task_tokens = _tokens(task)
    skill_ids = [skill.name for skill in skills]
    # A duplicated slug makes the package body depend on caller iteration
    # order while the catalog/pin map can describe only one package. Refuse
    # the whole snapshot instead of silently letting the last body win.
    if len(skill_ids) != len(set(skill_ids)):
        return SkillSelectionDecision(None, "duplicate_skill_id", ())
    by_id = {skill.name: skill for skill in skills}
    budget_limit = min(max_injection_chars, MAX_SKILL_INJECTION_CHARS)
    scored: list[tuple[float, str, Skill, int, bool, str]] = []

    for skill_id in sorted(by_id):
        skill = by_id[skill_id]
        entry = catalog.get(skill_id)
        tokens = _tokens(skill.card)
        shared_count = len(task_tokens & tokens)
        score = _overlap_score(tokens, task_tokens) if task_tokens else 0.0
        threshold_met = score >= threshold and shared_count >= MIN_SHARED_TOKENS

        reason = "eligible"
        if entry is None or entry.skill_id != skill_id:
            reason = "catalog_snapshot_missing"
        elif entry.installation != "installed" or not entry.revision or entry.blockers:
            reason = "package_not_validated"
        elif not entry.enabled:
            reason = "skill_disabled"
        elif readiness.get(skill_id) != "ready":
            reason = "readiness_unverified"
        elif privacy_compatible_skill_ids is None or skill_id not in privacy_compatible_skill_ids:
            reason = "privacy_compatibility_unverified"
        elif entry.required_tools and (
            available_tools is None or not set(entry.required_tools) <= available_tools
        ):
            reason = "required_tool_unavailable_or_unknown"
        elif entry.capabilities and (
            available_capabilities is None
            or not set(entry.capabilities) <= available_capabilities
        ):
            reason = "capability_unavailable_or_unknown"
        elif explicit_skill_id is None and not threshold_met:
            reason = "below_lexical_threshold"

        scored.append((score, skill_id, skill, shared_count, threshold_met, reason))

    if explicit_skill_id is not None:
        explicit = next((row for row in scored if row[1] == explicit_skill_id), None)
        if explicit is None:
            result_reason = "explicit_skill_unavailable"
        elif explicit[5] != "eligible":
            result_reason = explicit[5]
        elif budget_limit < 0 or len(explicit[2].as_prompt()) > budget_limit:
            result_reason = "injection_budget_exceeded"
            return SkillSelectionDecision(
                None, result_reason,
                _decisions(scored, refused_id=explicit_skill_id,
                           refused_reason=result_reason),
            )
        else:
            result_reason = "explicit_selection"
            selected = explicit[2]
            primary_result = SkillSelectionDecision(
                selected, result_reason,
                _decisions(scored, selected_id=selected.name),
            )
            return _add_optional_support(
                primary_result, explicit, scored, catalog, budget_limit,
            )
        return SkillSelectionDecision(None, result_reason, _decisions(scored))

    eligible = [row for row in scored if row[5] == "eligible"]
    if not eligible:
        reason = "no_eligible_skill"
    else:
        # Score descending, then slug ascending is the stable tie-break.
        winner = min(eligible, key=lambda row: (-row[0], row[1]))
        if budget_limit < 0 or len(winner[2].as_prompt()) > budget_limit:
            return SkillSelectionDecision(
                None, "injection_budget_exceeded",
                _decisions(scored, refused_id=winner[1],
                           refused_reason="injection_budget_exceeded"),
            )
        primary_result = SkillSelectionDecision(
            winner[2], "automatic_match", _decisions(scored, selected_id=winner[1])
        )
        return _add_optional_support(
            primary_result, winner, scored, catalog, budget_limit,
        )
    return SkillSelectionDecision(None, reason, _decisions(scored))


def _decisions(
    rows: Sequence[tuple[float, str, Skill, int, bool, str]],
    *,
    selected_id: str | None = None,
    supporting_id: str | None = None,
    refused_id: str | None = None,
    refused_reason: str | None = None,
) -> tuple[SkillCandidateDecision, ...]:
    return tuple(
        SkillCandidateDecision(
            skill_id=skill_id,
            score=score,
            shared_token_count=shared_count,
            threshold_met=threshold_met,
            eligible=(reason == "eligible" or skill_id in {selected_id, supporting_id}),
            reason=("selected" if skill_id == selected_id else
                    "support_selected" if skill_id == supporting_id else
                    refused_reason if skill_id == refused_id and refused_reason else reason),
        )
        for score, skill_id, _skill, shared_count, threshold_met, reason in rows
    )


def _add_optional_support(
    primary: SkillSelectionDecision,
    primary_row: tuple[float, str, Skill, int, bool, str],
    rows: Sequence[tuple[float, str, Skill, int, bool, str]],
    catalog: Mapping[str, SkillCatalogEntry],
    budget_limit: int,
) -> SkillSelectionDecision:
    """Attach at most one independently matching, mutually compatible skill."""
    primary_entry = catalog.get(primary_row[1])
    if primary_entry is None:
        return SkillSelectionDecision(
            primary.selected, primary.reason, primary.candidates,
            support_reason="primary_catalog_snapshot_missing",
        )
    independent = [
        row for row in rows
        if row[1] != primary_row[1] and row[5] == "eligible" and row[4]
    ]
    if not independent:
        return SkillSelectionDecision(
            primary.selected, primary.reason, primary.candidates,
            support_reason="no_independent_support_candidate",
        )
    reciprocal = [
        row for row in independent
        if (row[1] in primary_entry.compatible_with
            and primary_row[1] in catalog[row[1]].compatible_with)
    ]
    if not reciprocal:
        return SkillSelectionDecision(
            primary.selected, primary.reason, primary.candidates,
            support_reason="mutual_compatibility_not_declared",
        )
    for row in sorted(reciprocal, key=lambda item: (-item[0], item[1])):
        combined_size = len(primary_row[2].as_prompt()) + 2 + len(row[2].as_prompt())
        if combined_size <= budget_limit:
            return SkillSelectionDecision(
                primary.selected, primary.reason,
                _decisions(rows, selected_id=primary_row[1], supporting_id=row[1]),
                supporting=row[2], support_reason="mutually_compatible",
            )
    return SkillSelectionDecision(
        primary.selected, primary.reason, primary.candidates,
        support_reason="combined_injection_budget_exceeded",
    )
