"""Durable, draft-confirmed workload route preferences."""
from __future__ import annotations

import uuid
import hashlib
import hmac
import json
import os
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from typing import Any

from jarvis.db import get_conn, now_iso, run_migrations
from jarvis.model_routing import (
    ModelRouteError, assert_model_quality, inspect_route_choice, model_profile_exists, resolve_policy,
    verify_saygm_route_choice,
)

DRAFT_TTL_S = 600
HARNESS_SWITCH_BLOCK = (
    "Harness switching is unavailable: legacy settings, routed policy and runtime adoption "
    "do not yet share a durable exact-model approval contract. No preference was changed."
)


def _require_supported_workload(workload: str) -> None:
    if workload == "voice_supervisor":
        raise ModelPreferenceError(HARNESS_SWITCH_BLOCK)

# Least to most private. A route must provide at least the chosen level, and
# the chosen level must be at least the workload's configured one.
PRIVACY_ORDER = {"approved_external": 1, "confidential": 2, "local_only": 3}


class ModelPreferenceError(ModelRouteError):
    pass


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _conn(conn=None):
    if conn is not None:
        run_migrations(conn)
        return conn, False
    own = get_conn()
    run_migrations(own)
    return own, True


def list_preferences(*, conn=None) -> list[dict[str, Any]]:
    db, own = _conn(conn)
    try:
        rows = db.execute(
            "SELECT workload, profile, route, privacy, updated_at, user_id "
            "FROM model_route_preferences ORDER BY workload"
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        if own:
            db.close()


def _validate_choice(workload: str, profile: str, route: str,
                     privacy: str | None = None, *,
                     expected_validation_digest: str | None = None) -> dict[str, str]:
    try:
        policy, profile_record, route_record = inspect_route_choice(workload, profile, route)
        assert_model_quality(policy, profile_record)
    except ModelRouteError as exc:
        raise ModelPreferenceError(str(exc)) from exc
    if (expected_validation_digest is not None and not hmac.compare_digest(
            expected_validation_digest, _validation_digest(policy, profile_record, route_record))):
        raise ModelPreferenceError("model route proposal is stale; validation configuration changed")
    if not model_profile_exists(profile, workload=workload):
        raise ModelPreferenceError(f"unknown model profile {profile!r}")
    selected_privacy = privacy or policy.privacy
    if selected_privacy not in PRIVACY_ORDER:
        raise ModelPreferenceError(f"unknown privacy level {selected_privacy!r}")
    # A preference may keep or raise a workload's privacy, never lower it.
    # From #80 (88b206f) until this check, staging "approved_external" for the
    # confidential librarian or the local_only systems workload was accepted,
    # and confirming it replaced the configured level in resolve_policy, which
    # the run-log redaction and the delegation status masking both read.
    # `policy` here is the configured one: inspect_route_choice resolves it
    # with include_preferences=False.
    if PRIVACY_ORDER[selected_privacy] < PRIVACY_ORDER[policy.privacy]:
        raise ModelPreferenceError(
            f"{selected_privacy!r} is below workload {workload!r}'s configured "
            f"{policy.privacy!r} privacy; a preference may keep or raise it, never lower it"
        )
    if route == "saygm" and selected_privacy == "confidential":
        # Confidential choices need current proof at both stage and confirm;
        # saving an unverified TEE label would make the console misleading.
        try:
            route_record, _model = verify_saygm_route_choice(profile_record, route_record)
        except ModelRouteError as exc:
            raise ModelPreferenceError(str(exc)) from exc
    missing = set(policy.required_capabilities) - set(route_record.capabilities)
    if missing:
        raise ModelPreferenceError(
            f"route {route!r} lacks required capabilities: {', '.join(sorted(missing))}"
        )
    if PRIVACY_ORDER[route_record.privacy] < PRIVACY_ORDER[selected_privacy]:
        raise ModelPreferenceError(
            f"route {route!r} provides {route_record.privacy!r}, "
            f"but {selected_privacy!r} privacy is required"
        )
    # Ordinary choices may be saved while credentials are unavailable.
    # Confidential SAYGM choices are the exception: proof is required above,
    # and execution obtains fresh proof again before sending any content.
    return {"workload": workload, "profile": profile, "route": route,
            "privacy": selected_privacy}


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def _validation_digest(policy, record, access) -> str:
    return _digest({"policy": asdict(policy), "profile": record, "access": asdict(access)})


def _identity(workload: str, profile: str, route: str, privacy: str) -> dict[str, Any]:
    policy, record, access = inspect_route_choice(workload, profile, route)
    model = record.get("model")
    if not isinstance(model, str) or not model.strip():
        raise ModelPreferenceError("exact configured model is unavailable; cannot confirm a label")
    # Metadata only. No credential values, catalog request or model probe.
    return {"profile": profile, "model": model, "identity": record.get("identity"),
            "provider": record.get("provider"), "route": route, "privacy": privacy,
            "access": asdict(access), "policy": asdict(policy),
            "temperature": record.get("temperature"), "tier": record.get("tier"),
            "profile_digest": _digest(record),
            "validation_digest": _validation_digest(policy, record, access),
            "resolution_state": "resolved",
            "eligibility": "unverified", "runtime_adoption": "unverified"}


def _proposal(db, choice: dict[str, str]) -> dict[str, Any]:
    workload = choice["workload"]
    row = db.execute("SELECT * FROM model_route_preferences WHERE workload = ?",
                     (workload,)).fetchone()
    saved = dict(row) if row is not None else None
    policy = resolve_policy(workload, include_preferences=False)
    from jarvis.storage_context import preferences_enabled
    use_saved = preferences_enabled(os.environ.get("JARVIS_MODEL_PREFERENCES_ENABLED", "1") != "0")
    current = {"profile": policy.profile, "route": policy.route, "privacy": policy.privacy}
    if saved and use_saved:
        current.update({key: saved[key] for key in current})
    for key in ("profile", "route"):
        override = os.environ.get(f"JARVIS_MODEL_{key.upper()}_{workload.upper()}")
        if override:
            current[key] = override
    flags = {key: os.environ.get(key) for key in (
        "JARVIS_MODEL_ROUTING_ENABLED", "JARVIS_MODEL_PREFERENCES_ENABLED", "JARVIS_LLM_ACCESS_MODE",
        f"JARVIS_MODEL_PROFILE_{workload.upper()}", f"JARVIS_MODEL_ROUTE_{workload.upper()}")}
    try:
        current_identity = _identity(workload, **current)
    except ModelRouteError:
        # A broken saved selection must not prevent a valid repair. Bind the
        # unresolved labels, saved revision and overrides, never invent a model.
        current_identity = {**current, "model": None, "resolution_state": "unresolved",
                            "resolution_error": "Configured profile or route is unavailable.",
                            "eligibility": "unverified", "runtime_adoption": "unverified"}
    return {"schema_version": 1, "workload": workload,
            "current": current_identity,
            "candidate": _identity(**choice), "saved_revision": saved,
            "flags": flags, "preferences_enabled": use_saved,
            "evidence": "No comparative evaluation is asserted by this configuration preview.",
            "expected_latency_quality": "unknown", "quota_cost": "not measured; no inference authorized",
            "application": "Save selection only; future registry edits can change its resolution. Runtime adoption is unverified."}


def stage_preference(workload: str, profile: str, route: str,
                     privacy: str | None = None, *, conn=None) -> dict[str, Any]:
    _require_supported_workload(workload)
    try:
        choice = _validate_choice(workload, profile, route, privacy)
    except ModelRouteError as exc:
        raise ModelPreferenceError(str(exc)) from exc
    created = datetime.now(timezone.utc)
    expires = created + timedelta(seconds=DRAFT_TTL_S)
    db, own = _conn(conn)
    try:
        # No schema migration: the existing opaque ID binds the full preview.
        # The random prefix prevents a public digest from being an approval token.
        with db:
            db.execute("BEGIN IMMEDIATE")
            proposal = _proposal(db, choice)
            digest = _digest(proposal)
            draft_id = f"v1:{uuid.uuid4().hex}:{digest}"
            db.execute(
                "INSERT INTO model_route_drafts "
                "(draft_id, workload, profile, route, privacy, created_at, expires_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (draft_id, choice["workload"], choice["profile"], choice["route"],
                 choice["privacy"], created.isoformat(), expires.isoformat()),
            )
        return {"draft_id": draft_id, **choice, "expires_at": expires.isoformat(),
                "proposal_digest": digest, "proposal": proposal}
    except ModelRouteError as exc:
        raise ModelPreferenceError(str(exc)) from exc
    finally:
        if own:
            db.close()


def confirm_preference(draft_id: str, *, conn=None) -> dict[str, Any]:
    db, own = _conn(conn)
    try:
        query = ("SELECT draft_id, workload, profile, route, privacy, expires_at "
                 "FROM model_route_drafts WHERE draft_id = ?")
        row = db.execute(query, (draft_id,)).fetchone()
        if row is None:
            raise ModelPreferenceError(f"unknown or already confirmed model route draft {draft_id!r}")
        original = dict(row)
        if _parse_iso(row["expires_at"]) <= datetime.now(timezone.utc):
            raise ModelPreferenceError("model route draft expired; create a new preview")
        _require_supported_workload(row["workload"])
        parts = draft_id.split(":")
        if len(parts) != 3 or parts[0] != "v1" or len(parts[2]) != 64:
            raise ModelPreferenceError("legacy draft lacks exact model confirmation; create a new preview")
        fields = {key: row[key] for key in ("workload", "profile", "route", "privacy")}
        preview = _proposal(db, fields)
        if not hmac.compare_digest(parts[2], _digest(preview)):
            raise ModelPreferenceError("model route proposal is stale; current model or routing changed; create a new preview")
        # Confidential catalog validation may wait on the network. Bind the
        # metadata it actually validates, without holding SQLite's writer lock.
        choice = _validate_choice(**fields,
            expected_validation_digest=preview["candidate"]["validation_digest"])
        # Re-read, consume and save atomically. Both the row and full proposal
        # must still match after validation; competing confirmations cannot win.
        with db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(query, (draft_id,)).fetchone()
            if row is None or dict(row) != original:
                raise ModelPreferenceError("model route draft changed or was already confirmed; create a new preview")
            if _parse_iso(row["expires_at"]) <= datetime.now(timezone.utc):
                raise ModelPreferenceError("model route draft expired; create a new preview")
            proposal = _proposal(db, choice)
            if not hmac.compare_digest(parts[2], _digest(proposal)):
                raise ModelPreferenceError("model route proposal is stale; current model or routing changed; create a new preview")
            db.execute(
                "INSERT INTO model_route_preferences(workload, profile, route, privacy, updated_at) "
                "VALUES (?, ?, ?, ?, ?) ON CONFLICT(workload) DO UPDATE SET "
                "profile=excluded.profile, route=excluded.route, privacy=excluded.privacy, "
                "updated_at=excluded.updated_at",
                (choice["workload"], choice["profile"], choice["route"],
                 choice["privacy"], now_iso()),
            )
            db.execute("DELETE FROM model_route_drafts WHERE draft_id = ?", (draft_id,))
            saved = dict(db.execute("SELECT * FROM model_route_preferences WHERE workload = ?",
                                    (choice["workload"],)).fetchone())
        return {"confirmed": True, **choice, "proposal_digest": parts[2],
                "saved_preference": saved, "configured_model": proposal["candidate"]["model"],
                "state": "saved", "runtime_adoption": "unverified",
                "message": "Model route saved; active runtime adoption is unverified."}
    except ModelRouteError as exc:
        raise ModelPreferenceError(str(exc)) from exc
    finally:
        if own:
            db.close()
