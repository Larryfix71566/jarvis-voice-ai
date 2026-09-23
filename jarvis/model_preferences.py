"""Durable, draft-confirmed workload route preferences."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from jarvis.db import get_conn, now_iso, run_migrations
from jarvis.model_routing import (
    ModelRouteError, inspect_route_choice, model_profile_exists, resolve_policy,
)

DRAFT_TTL_S = 600


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
                     privacy: str | None = None) -> dict[str, str]:
    try:
        policy, _profile, route_record = inspect_route_choice(workload, profile, route)
    except ModelRouteError as exc:
        raise ModelPreferenceError(str(exc)) from exc
    if not model_profile_exists(profile, workload=workload):
        raise ModelPreferenceError(f"unknown model profile {profile!r}")
    selected_privacy = privacy or policy.privacy
    if selected_privacy not in {"local_only", "confidential", "approved_external"}:
        raise ModelPreferenceError(f"unknown privacy level {selected_privacy!r}")
    missing = set(policy.required_capabilities) - set(route_record.capabilities)
    if missing:
        raise ModelPreferenceError(
            f"route {route!r} lacks required capabilities: {', '.join(sorted(missing))}"
        )
    privacy_order = {"approved_external": 1, "confidential": 2, "local_only": 3}
    if privacy_order[route_record.privacy] < privacy_order[selected_privacy]:
        raise ModelPreferenceError(
            f"route {route!r} provides {route_record.privacy!r}, "
            f"but {selected_privacy!r} privacy is required"
        )
    # Reuse the policy validator without probing credentials. Confirmation is
    # allowed to save an unavailable choice so the console can show why it is
    # unavailable and the user can correct it; execution still fails closed.
    return {"workload": workload, "profile": profile, "route": route,
            "privacy": selected_privacy}


def stage_preference(workload: str, profile: str, route: str,
                     privacy: str | None = None, *, conn=None) -> dict[str, Any]:
    choice = _validate_choice(workload, profile, route, privacy)
    draft_id = uuid.uuid4().hex[:16]
    created = datetime.now(timezone.utc)
    expires = created + timedelta(seconds=DRAFT_TTL_S)
    db, own = _conn(conn)
    try:
        with db:
            db.execute(
                "INSERT INTO model_route_drafts "
                "(draft_id, workload, profile, route, privacy, created_at, expires_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (draft_id, choice["workload"], choice["profile"], choice["route"],
                 choice["privacy"], created.isoformat(), expires.isoformat()),
            )
        return {"draft_id": draft_id, **choice, "expires_at": expires.isoformat()}
    finally:
        if own:
            db.close()


def confirm_preference(draft_id: str, *, conn=None) -> dict[str, Any]:
    db, own = _conn(conn)
    try:
        row = db.execute(
            "SELECT draft_id, workload, profile, route, privacy, expires_at "
            "FROM model_route_drafts WHERE draft_id = ?", (draft_id,)
        ).fetchone()
        if row is None:
            raise ModelPreferenceError(f"unknown or already confirmed model route draft {draft_id!r}")
        if _parse_iso(row["expires_at"]) <= datetime.now(timezone.utc):
            with db:
                db.execute("DELETE FROM model_route_drafts WHERE draft_id = ?", (draft_id,))
            raise ModelPreferenceError(f"model route draft {draft_id!r} expired")
        choice = _validate_choice(row["workload"], row["profile"], row["route"], row["privacy"])
        with db:
            db.execute(
                "INSERT INTO model_route_preferences(workload, profile, route, privacy, updated_at) "
                "VALUES (?, ?, ?, ?, ?) ON CONFLICT(workload) DO UPDATE SET "
                "profile=excluded.profile, route=excluded.route, privacy=excluded.privacy, "
                "updated_at=excluded.updated_at",
                (choice["workload"], choice["profile"], choice["route"],
                 choice["privacy"], now_iso()),
            )
            db.execute("DELETE FROM model_route_drafts WHERE draft_id = ?", (draft_id,))
        return {"confirmed": True, **choice}
    finally:
        if own:
            db.close()
