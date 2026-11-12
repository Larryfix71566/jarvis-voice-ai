"""Admin sidecar routes: skills catalog, requests and activity (/api/skills, /api/skills/requests*, /api/skills/{skill_id}*, /api/skills/runs/*).

Moved verbatim from jarvis/admin/server.py (B6). Helpers, state and imported
modules are reached as `srv.<name>` at call time, never imported here, so a
test that monkeypatches jarvis.admin.server is seen by these handlers.
Only jarvis.admin.server imports this module.
"""

from __future__ import annotations

from fastapi import Request

from jarvis.admin import server as srv
from jarvis.admin.server import (  # request bodies named in signatures
    SkillRequestIn,
)

# Routes register on the server's one FastAPI app (see the B6 note there).
app = srv.app


@app.get("/api/skills")
def skills_catalog(cursor: str = "", limit: int = 50) -> dict:
    """Read-only, bounded inventory for the native Skills workspace."""
    from jarvis.skill_catalog import list_catalog
    from jarvis.skill_service import assess_current_readiness, configured_tool_inventory
    from jarvis.skill_requests import authoring_available

    if len(cursor) > 12 or (cursor and not cursor.isdecimal()):
        raise srv.HTTPException(status_code=400, detail="invalid catalog cursor")
    if not 1 <= limit <= 100:
        raise srv.HTTPException(status_code=400, detail="limit must be between 1 and 100")
    entries = list_catalog()
    tool_inventory = configured_tool_inventory()
    catalog_revision = srv.hashlib.sha256("\n".join(
        f"{item.skill_id}:{item.revision or 'invalid'}:{int(item.enabled)}"
        for item in entries
    ).encode("utf-8")).hexdigest()
    offset = int(cursor or "0")
    page = entries[offset:offset + limit]
    next_offset = offset + len(page)
    return {
        "schema_version": 1,
        "catalog_revision": catalog_revision,
        "capabilities": {"process_view": True, "activity_trace": True,
                         "authoring": authoring_available()},
        "items": [{
            "skill_id": item.skill_id,
            "display_name": item.display_name,
            "description": item.description,
            "category": item.category,
            "example_ids": list(item.example_ids[:32]),
            "revision": item.revision,
            "installation": item.installation,
            "enabled": item.enabled,
            "readiness": (readiness := assess_current_readiness(
                item, tool_inventory=tool_inventory,
            )).state,
            "readiness_reasons": list(readiness.reason_codes),
            "verification": item.verification,
            "blockers": item.blockers,
        } for item in page],
        "next_cursor": str(next_offset) if next_offset < len(entries) else None,
    }


@app.post("/api/skills/requests", status_code=202)
def create_skill_request(payload: SkillRequestIn, request: Request) -> dict:
    """Start/reconcile a bounded Skills operation under the bearer owner."""
    from jarvis.skill_catalog import list_catalog
    from jarvis.skill_requests import (
        SkillRequestError, cancel_job, get as get_skill_job, start_draft,
        start_offline_validation, start_publish,
    )

    values = srv._validated_skill_request(payload)
    owner = srv._skill_request_owner(request)
    if values["privacy_context"] == "protected":
        raise srv.HTTPException(status_code=409, detail="protected requests cannot be persisted in a sandbox workspace")
    entries = list_catalog()
    catalog_revision = srv.hashlib.sha256("\n".join(
        f"{item.skill_id}:{item.revision or 'invalid'}:{int(item.enabled)}" for item in entries
    ).encode("utf-8")).hexdigest()
    if (values["operation"] != "cancel"
            and values["expected_catalog_revision"] != catalog_revision):
        raise srv.HTTPException(status_code=409, detail="Skills catalog changed; refresh before retrying")
    current = next((item for item in entries if item.skill_id == values["skill_id"]), None)
    if values["operation"] == "draft":
        if current and current.installation == "installed" and values["skill_revision"] != current.revision:
            raise srv.HTTPException(status_code=409, detail="existing skill revision changed; refresh before drafting")
        try:
            from jarvis.skill_runtime import runtime_owner

            if runtime_owner(values["bot_session_id"]) != owner:
                raise srv.HTTPException(
                    status_code=409,
                    detail="creator requests require the caller's active Mortimer session",
                )
            job, created = start_draft(owner, values)
        except SkillRequestError as exc:
            raise srv.HTTPException(status_code=exc.status_code, detail=str(exc)) from None
        return {"schema_version": 1, **job, "replayed": not created}

    if values["operation"] == "test" and current is None:
        # A just-authored slug is not in the live catalog. It remains valid
        # only when the same caller owns the corresponding sandbox draft.
        from jarvis.skill_requests import get as get_skill_job
        try:
            draft = get_skill_job(owner, values["job_id"])
        except Exception:
            draft = None
        if not draft or draft.get("operation") != "draft" or draft.get("skill_id") != values["skill_id"]:
            raise srv.HTTPException(status_code=404, detail="skill is unavailable")
    elif current is None and values["operation"] not in {"request_publish", "request_activation", "request_rollback", "cancel"}:
        raise srv.HTTPException(status_code=404, detail="skill is unavailable")
    if (values["operation"] != "request_publish" and current is not None
            and values["skill_revision"] is not None and current.revision != values["skill_revision"]):
        raise srv.HTTPException(status_code=409, detail="skill revision changed")
    if values["operation"] == "request_activation":
        # Offline package validation is not the paired SW-G evaluation or its
        # blinded human review. Until an accepted evaluation report is bound to
        # this exact skill revision through an owner-scoped receipt, do not
        # create a maintainer artifact that could look activation-ready.
        raise srv.HTTPException(
            status_code=409,
            detail="accepted live evaluation and blinded human review evidence is required",
        )
    if values["operation"] == "request_rollback":
        # The Versions API currently has no durable accepted-version history;
        # a successful offline test alone cannot identify a valid prior config.
        raise srv.HTTPException(
            status_code=409,
            detail="no previously accepted package and registry revision is recorded",
        )
    if values["operation"] == "cancel":
        try:
            cancelled, created = cancel_job(owner, values)
            return {"schema_version": 1, **cancelled, "replayed": not created}
        except SkillRequestError as exc:
            raise srv.HTTPException(status_code=exc.status_code, detail=str(exc)) from None
    if values["operation"] == "test":
        if values["scope"] == "live":
            raise srv.HTTPException(status_code=409, detail="live skill evaluation is disabled until a reviewed route and budget are configured")
        try:
            draft = get_skill_job(owner, values["job_id"])
            if (not draft or draft.get("operation") != "draft"
                    or draft.get("skill_id") != values["skill_id"]):
                raise srv.HTTPException(status_code=404, detail="authoring job is unavailable")
            if draft.get("state") != "drafting":
                raise srv.HTTPException(status_code=409, detail="authoring job is not ready for offline validation")
            job, created = start_offline_validation(owner, values)
            return {"schema_version": 1, **job, "replayed": not created}
        except SkillRequestError as exc:
            raise srv.HTTPException(status_code=exc.status_code, detail=str(exc)) from None
    if values["operation"] == "request_publish":
        try:
            job, created = start_publish(owner, values)
            return {"schema_version": 1, **job, "replayed": not created}
        except SkillRequestError as exc:
            raise srv.HTTPException(status_code=exc.status_code, detail=str(exc)) from None
    raise srv.HTTPException(status_code=400, detail="unsupported Skills operation")


@app.get("/api/skills/requests/{request_id}")
def skill_request_status(request_id: str, request: Request) -> dict:
    from jarvis.skill_requests import SkillRequestError, _service, reconcile
    owner = srv._skill_request_owner(request)
    try:
        state = reconcile(owner, request_id)
    except SkillRequestError as exc:
        raise srv.HTTPException(status_code=exc.status_code, detail=str(exc)) from None
    if state is None:
        raise srv.HTTPException(status_code=404, detail="request is unavailable")
    response = {"schema_version": 1, **state}
    if state.get("operation") == "draft" and state.get("state") == "review_ready":
        try:
            live = _service(state["skill_id"]).status()
        except Exception:
            live = {}
        proposals = live.get("proposals") if live.get("run_id") == state.get("sandbox_job_id") else None
        if (live.get("candidate") == state.get("candidate_digest")
                and live.get("package_revision") == state.get("candidate_revision")
                and isinstance(proposals, list) and len(proposals) <= 64):
            review_items = []
            total_bytes = 0
            for item in proposals:
                if not isinstance(item, dict):
                    continue
                path, diff = item.get("path"), item.get("diff")
                allowed_prefixes = (
                    f"skills/{state['skill_id']}/",
                    f"tests/fixtures/skills_authoring/{state['skill_id']}/",
                )
                if (not isinstance(path, str) or not isinstance(diff, str)
                        or len(path) > 240 or "\\" in path or ".." in path.split("/")
                        or not path.startswith(allowed_prefixes)):
                    continue
                total_bytes += len(path.encode()) + len(diff.encode())
                if total_bytes > 256 * 1024:
                    review_items = []
                    break
                review_items.append({"path": path, "diff": diff})
            if review_items:
                response["review"] = {
                    "candidate_digest": state["candidate_digest"],
                    "skill_revision": state["candidate_revision"],
                    "files": review_items,
                }
    return response


@app.get("/api/skills/{skill_id}/runs")
def skills_runs(
    skill_id: str, request: Request, cursor: str = "", limit: int = 20,
) -> dict:
    """List bounded, content-free run cards for one skill revision family."""
    from jarvis.skill_catalog import SLUG

    srv.run_migrations()
    if not SLUG.fullmatch(skill_id):
        raise srv.HTTPException(status_code=400, detail="invalid skill identifier")
    if len(cursor) > 512:
        raise srv.HTTPException(status_code=400, detail="invalid skill run cursor")
    if not 1 <= limit <= 100:
        raise srv.HTTPException(status_code=400, detail="limit must be between 1 and 100")
    try:
        page = srv.list_skill_runs(
            skill_id, cursor=cursor, limit=limit,
            user_id=srv._skill_activity_owner(request),
        )
    except ValueError:
        raise srv.HTTPException(status_code=400, detail="invalid skill run cursor") from None
    return {"schema_version": 1, **page}


@app.get("/api/skills/runs/{run_id}/events")
def skills_run_events(
    run_id: str, request: Request, after_seq: int = 0, limit: int = 100,
) -> dict:
    """Read typed activity for an owned run; never fall back to prompt logs."""
    srv.run_migrations()
    if not 0 <= after_seq <= 2**63 - 1:
        raise srv.HTTPException(status_code=400, detail="invalid event cursor")
    if not 1 <= limit <= 100:
        raise srv.HTTPException(status_code=400, detail="limit must be between 1 and 100")
    try:
        page = srv.get_skill_events(
            run_id, after_seq=after_seq, limit=limit,
            user_id=srv._skill_activity_owner(request),
        )
    except ValueError:
        raise srv.HTTPException(status_code=400, detail="invalid run identifier") from None
    if page is None:
        raise srv.HTTPException(status_code=404, detail="run is unavailable")
    return {"schema_version": 1, **page}


@app.get("/api/skills/{skill_id}")
def skill_detail(skill_id: str, revision: str | None = None) -> dict:
    """Return a validated immutable skill description and intended process."""
    from jarvis.skill_catalog import SLUG, SkillPackageError, inspect_package
    from jarvis.skill_service import assess_current_readiness
    from jarvis.agent_skills import SKILLS_DIR

    if not SLUG.fullmatch(skill_id):
        raise srv.HTTPException(status_code=400, detail="invalid skill identifier")
    try:
        item = inspect_package(SKILLS_DIR / skill_id)
    except (OSError, SkillPackageError):
        raise srv.HTTPException(status_code=404, detail="skill is unavailable") from None
    if item.installation != "installed" or item.revision is None:
        raise srv.HTTPException(status_code=409, detail="skill package needs attention")
    if revision is not None and revision != item.revision:
        raise srv.HTTPException(status_code=409, detail="skill revision changed")
    readiness = assess_current_readiness(item)
    return {
        "schema_version": 1,
        **item.as_dict(),
        "readiness": readiness.state,
        "readiness_reasons": list(readiness.reason_codes),
    }


@app.get("/api/skills/{skill_id}/versions")
def skill_versions(skill_id: str, request: Request) -> dict:
    """Show installed package and caller-owned candidate evidence, read-only."""
    from jarvis.skill_catalog import SLUG, SkillPackageError, inspect_package
    from jarvis.skill_catalog import read_skill_registry
    from jarvis.skill_requests import SkillRequestError, list_for_skill
    from jarvis.agent_skills import SKILLS_CONFIG, SKILLS_DIR

    if not SLUG.fullmatch(skill_id):
        raise srv.HTTPException(status_code=400, detail="invalid skill identifier")
    try:
        owner = srv._skill_request_owner(request)
        item = inspect_package(SKILLS_DIR / skill_id)
        names, pins, registry_version, registry_valid = read_skill_registry(SKILLS_CONFIG)
        candidates = list_for_skill(owner, skill_id)
    except srv.HTTPException:
        raise
    except SkillRequestError as exc:
        raise srv.HTTPException(status_code=exc.status_code, detail=str(exc)) from None
    except (OSError, SkillPackageError):
        raise srv.HTTPException(status_code=404, detail="skill version evidence is unavailable") from None

    active_pin = pins.get(skill_id) if registry_valid and isinstance(pins, dict) else None
    pin_state = (
        "registry_unavailable" if not registry_valid or registry_version != 2
        else "disabled" if skill_id not in names
        else "unverified" if not isinstance(active_pin, str)
        else "matches_installed" if active_pin == item.revision
        else "differs_from_installed"
    )
    return {
        "schema_version": 1,
        "skill_id": skill_id,
        "installed": {
            "declared_version": item.version,
            "package_revision": item.revision,
            "enabled": item.enabled,
        },
        "registry": {
            "schema_version": registry_version if registry_valid else None,
            "active_pin": active_pin,
            "pin_state": pin_state,
        },
        "candidates": candidates,
        "limitations": [
            "Package revision is a SHA-256 digest; declared version is manifest metadata.",
            "Candidate requests are caller-owned ledger records, not activation evidence.",
            "Git commit history and previously installed revisions are not available here.",
            "No activation or rollback is performed by this view.",
        ],
    }


@app.get("/api/skills/{skill_id}/examples/{example_id}")
def skill_example_preview(skill_id: str, example_id: str) -> dict:
    """Return one declared, inert matcher fixture for native preview only."""
    from jarvis.skill_catalog import SLUG, SkillPackageError, inspect_package, read_skill_registry
    from jarvis.agent_skills import SKILLS_DIR

    if not SLUG.fullmatch(skill_id) or not SLUG.fullmatch(example_id):
        raise srv.HTTPException(status_code=400, detail="invalid skill example identifier")
    try:
        package = inspect_package(SKILLS_DIR / skill_id)
    except (OSError, SkillPackageError):
        raise srv.HTTPException(status_code=404, detail="skill example is unavailable") from None
    if package.installation != "installed" or example_id not in package.example_ids:
        raise srv.HTTPException(status_code=404, detail="skill example is unavailable")
    names, pins, version, registry_valid = read_skill_registry()
    if (not registry_valid or version != 2 or skill_id not in names
            or pins is None or pins.get(skill_id) != package.revision):
        raise srv.HTTPException(status_code=409, detail="skill example is not bound to the reviewed package revision")
    repository = srv.REPO_ROOT.resolve()
    fixture = repository / "tests" / "fixtures" / "skills_authoring" / skill_id / "matcher-cases.json"
    try:
        if fixture.is_symlink() or not fixture.is_file() or fixture.stat().st_size > 64 * 1024:
            raise ValueError("fixture unavailable")
        resolved = fixture.resolve(strict=True)
        if not resolved.is_relative_to(repository):
            raise ValueError("fixture escaped repository")
        def unique_pairs(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("duplicate fixture field")
                result[key] = value
            return result
        payload = srv.json.loads(resolved.read_text(encoding="utf-8"), object_pairs_hook=unique_pairs)
        cases = payload.get("cases") if isinstance(payload, dict) and set(payload) == {"schema_version", "cases"} and payload.get("schema_version") == 1 else None
        if not isinstance(cases, list) or not 2 <= len(cases) <= 32:
            raise ValueError("fixture schema invalid")
        seen: set[str] = set()
        outcomes: set[bool] = set()
        selected = None
        for case in cases:
            if (not isinstance(case, dict) or set(case) != {"id", "request", "expect_selected"}
                    or not isinstance(case.get("id"), str)
                    or not SLUG.fullmatch(case["id"])
                    or case["id"] in seen
                    or not isinstance(case.get("request"), str)
                    or not 1 <= len(case["request"].strip()) <= 1_000
                    or type(case.get("expect_selected")) is not bool):
                raise ValueError("fixture case invalid")
            seen.add(case["id"])
            outcomes.add(case["expect_selected"])
            if case["id"] == example_id:
                selected = case
        if selected is None or seen != set(package.example_ids) or outcomes != {False, True}:
            raise ValueError("declared example is absent")
        return {"schema_version": 1, "skill_id": skill_id, "example_id": example_id,
                "request": selected["request"], "expect_selected": selected["expect_selected"],
                "synthetic": True}
    except (OSError, UnicodeError, ValueError, TypeError):
        raise srv.HTTPException(status_code=409, detail="reviewed example preview is unavailable") from None
