"""Admin sidecar routes: planning pathway job (/api/plan/*).

Moved verbatim from jarvis/admin/server.py (B6). Helpers, state and imported
modules are reached as `srv.<name>` at call time, never imported here, so a
test that monkeypatches jarvis.admin.server is seen by these handlers.
Only jarvis.admin.server imports this module.
"""

from __future__ import annotations

from typing import Any

from jarvis.admin import server as srv
from jarvis.admin.server import (  # request bodies named in signatures
    PlanAdoptIn,
    PlanChooseIn,
    PlanStartIn,
)

# Routes register on the server's one FastAPI app (see the B6 note there).
app = srv.app


# ------------------------------------------------------- planning pathway
# MORTIMER_PLANNING_PATHWAY_PLAN.md P7. Thin pass-throughs over
# jarvis.council.council (draft_candidates/record_user_choice) and
# mcp_repo.logic (the SAME draft-gated write voice uses) — no write
# primitive is duplicated here.


@app.post("/api/plan/start")
def plan_start(body: PlanStartIn) -> dict:
    advisory_started_at = srv.time.time()
    srv.run_migrations()
    goal = (body.goal or "").strip()
    if not goal:
        return {"ok": False, "error": "a goal is required — what should the plan cover?"}
    if body.mode not in ("single", "council"):
        return {"ok": False, "error": f"mode={body.mode!r} must be 'single' or 'council'"}
    run_id = (body.run_id or "").strip() or None
    if not run_id:
        return {
            "ok": False,
            "error": "a stable run_id is required for a planning start",
        }
    if len(run_id) > 256:
        return {"ok": False, "error": "run identity is invalid; no planning job was started"}

    review_path = (body.review_path or "").strip()
    context: dict[str, Any] = {}
    if review_path:
        # MORTIMER_PLAN_REVIEW_AND_DOCS_PLAN.md R1 — read the document to
        # review ONCE, synchronously, before any thread launches. A
        # review of an unreadable document must never start.
        read_result = srv.repo_logic.repo_read_file(review_path)
        if not read_result.get("ok"):
            return {"ok": False, "error": read_result.get("error")}
        source = srv._advisory_transport_context.get()
        if source is not None:
            from jarvis.advisory_sources import prepared_review_source
            context = prepared_review_source(source, srv._selfedit_service, review_path, read_result)
        else:
            content = read_result.get("content") or ""
            if len(content) > srv.council_config.PLAN_REVIEW_DOC_MAX_CHARS:
                content = (
                    content[: srv.council_config.PLAN_REVIEW_DOC_MAX_CHARS]
                    + "\n\n… (truncated for review — flag this truncation in your verdict)"
                )
            context = {"document": content, "document_path": review_path}

    with srv._plan_lock:
        try:
            prior = srv.get_execution_action(srv._PLAN_START_ACTION_SCOPE, run_id)
        except Exception as exc:
            srv.logger.warning("plan_start_claim_read_failed error_type=%s", type(exc).__name__)
            return {
                "ok": False,
                "error": "could not verify whether this planning action already started; "
                         "no retry was launched",
                "outcome": "unknown",
                "action_run_id": run_id,
            }
        if prior is not None:
            if srv._plan_job.get("run_id") == run_id:
                state = srv._plan_job.get("state") or "unknown"
            elif prior.get("status") in {"completed", "failed"}:
                state = prior["status"]
            else:
                # A server restart or a later job can evict the result
                # from the single live status slot. The durable claim
                # prevents a retry, but cannot establish the effect.
                state = "unknown"
            return {
                "ok": True,
                "started": False,
                "duplicate": True,
                "state": state,
                "action_run_id": run_id,
                "summary": (
                    "This planning action was already claimed for this execution; "
                    "no new job was started. Check plan_status with this action_run_id "
                    "before considering any retry."
                ),
            }
        if srv._plan_job["state"] == "running":
            return {
                "ok": False,
                "error": "a planning job is already in progress — ask for status instead",
                "job": dict(srv._plan_job),
            }
        resolved_profile_name: str | None = None
        profile: dict[str, Any] | None = None
        if body.mode == "single":
            try:
                # Construct now so an unknown profile fails fast,
                # synchronously — same rule selfedit_run's _make_agent
                # call follows above.
                profile = srv._resolve_planning_profile(body.profile)
            except srv.UnknownModelProfileError as exc:
                return {"ok": False, "error": str(exc)}
            resolved_profile_name = profile["name"]
        try:
            claimed = srv.claim_execution_action(srv._PLAN_START_ACTION_SCOPE, run_id)
        except Exception as exc:
            srv.logger.warning("plan_start_claim_write_failed error_type=%s", type(exc).__name__)
            return {
                "ok": False,
                "error": "could not safely record this planning action; no job was started",
            }
        if not claimed:
            # A concurrent request won between the read and claim. Treat
            # it exactly like a replay, never as permission to dispatch.
            return {
                "ok": True, "started": False, "duplicate": True,
                "state": "unknown", "action_run_id": run_id,
                "summary": (
                    "This planning action was already claimed for this execution; "
                    "no new job was started. Check plan_status with this action_run_id "
                    "before considering any retry."
                ),
            }
        srv._plan_job.update(
            state="running", mode=body.mode, goal=goal,
            profile=resolved_profile_name, round_id=None, candidates=None,
            plan=None, author=None, error=None,
            started_at=srv.time.time(), finished_at=None,
            review_path=review_path or None,
            run_id=run_id,
        )
        srv._activate_advisory(srv._plan_job)
    srv._update_plan_start_claim(run_id, "running")
    if body.mode == "single":
        srv._start_advisory_thread(
            srv._run_plan_single, args=(goal, profile, context, run_id),
            started_at=advisory_started_at,
        )
    else:
        srv._start_advisory_thread(
            srv._run_plan_council, args=(goal, body.members, context, run_id),
            started_at=advisory_started_at,
        )
    return {"ok": True, "started": True}


@app.get("/api/plan/job")
def plan_job_status(run_id: str | None = None) -> dict:
    with srv._plan_lock:
        srv._advisory_context_for_job('planning', srv._plan_job)
        job = dict(srv._plan_job)
    requested_run_id = (run_id or "").strip()
    if requested_run_id:
        if len(requested_run_id) > 256:
            return {"ok": False, "error": "planning action identity is invalid"}
        if job.get("run_id") == requested_run_id:
            return {"ok": True, "job": job}
        try:
            receipt = srv.get_execution_action(srv._PLAN_START_ACTION_SCOPE, requested_run_id)
        except Exception as exc:
            srv.logger.warning("plan_start_status_read_failed error_type=%s", type(exc).__name__)
            return {"ok": False, "error": "the planning action receipt is unavailable"}
        if receipt is None:
            return {"ok": False, "error": "no planning action receipt exists for that execution"}
        state = receipt["status"]
        if state in {"claimed", "running", "awaiting_choice"}:
            state = "unknown"
        return {
            "ok": True,
            "job": {
                "state": state,
                "run_id": requested_run_id,
                "result_available": False,
                "reconciliation_required": state == "unknown",
            },
        }
    return {"ok": True, "job": job}


@app.post("/api/plan/choose")
def plan_choose(body: PlanChooseIn) -> dict:
    with srv._plan_lock:
        source = srv._advisory_context_for_job('planning', srv._plan_job)
        if srv._plan_job["state"] != "awaiting_choice":
            return {"ok": False, "error": "no planning round is awaiting a choice"}
        round_id = srv._plan_job["round_id"]
        candidates = list(srv._plan_job["candidates"] or [])
    label = (body.label or "").strip()
    match = next((c for c in candidates if c["label"] == label), None)
    if match is None:
        return {"ok": False, "error": f"no candidate with label {label!r}"}
    srv.council_mod.record_user_choice(round_id, label)
    with srv._plan_lock:
        if srv._advisory_context_for_job('planning', srv._plan_job) is not source:
            # Metadata-only manual contexts may be freshly sealed; the
            # action identity is the retained authority.
            current = srv._advisory_context_for_job('planning', srv._plan_job)
            if source is not None and (current is None or current._action is not source._action):
                raise srv.HTTPException(status_code=409, detail='advisory source action changed')
        srv._plan_job.update(
            state="done", plan=match["content"], author=match["profile"],
            finished_at=srv.time.time(),
        )
        chosen_run_id = srv._plan_job.get("run_id")
        if source is not None:
            from jarvis.advisory_sources import record_advisory_job
            record_advisory_job(source, srv._plan_job)
    srv._update_plan_start_claim(chosen_run_id, "completed")
    return {"ok": True}


@app.post("/api/plan/adopt")
def plan_adopt(body: PlanAdoptIn) -> dict:
    """Save the finished plan through the guarded sandbox editor.
    P7's attribution footer is appended HERE, once, at adoption: a
    candidate on the ballot stays footer-free and byte-comparable, and a
    plan never adopted stamps nothing."""
    with srv._plan_lock:
        source = srv._advisory_context_for_job('planning', srv._plan_job)
        if srv._plan_job["state"] != "done":
            return {"ok": False, "error": "no finished plan to adopt"}
        job = dict(srv._plan_job)
    plan_text = job.get("plan") or ""
    if not plan_text:
        return {"ok": False, "error": "the plan is empty"}
    review_path = job.get("review_path")
    if body.path:
        path = body.path.strip()
    elif review_path:
        # MORTIMER_PLAN_REVIEW_AND_DOCS_PLAN.md R4 — a review's default
        # adopt path is docs/reviews/, not docs/plans/.
        path = f"docs/reviews/{srv._slugify_goal(job.get('goal') or 'review')}.md"
    else:
        path = f"docs/plans/{srv._slugify_goal(job.get('goal') or 'plan')}.md"

    registry = srv.load_model_registry()
    profiles = registry.get("profiles", {})
    author_name = job.get("author") or "unknown"
    provider_model = (profiles.get(author_name) or {}).get("model", author_name)
    if review_path:
        # R4 — the review-mode footer verb, exact template.
        footer = (
            f"\n\n---\n*Review by {author_name} ({provider_model}) — "
            f"{srv.now_iso()[:10]}. Reviewed: {review_path}.*"
        )
    else:
        footer = f"\n\n---\n*Drafted by {author_name} ({provider_model}) — {srv.now_iso()[:10]}.*"
    if job.get("mode") == "council" and job.get("round_id"):
        n = len(job.get("candidates") or [])
        footer += (
            f" Selected by Larry from {n} council candidate"
            f"{'s' if n != 1 else ''} (round {job['round_id']})."
        )

    token = srv._advisory_transport_context.set(source)
    try:
        result = srv._save_document_to_sandbox(
            path, plan_text + footer, rationale=f"Adopted plan: {job.get('goal') or ''}",
        )
    finally:
        srv._advisory_transport_context.reset(token)
    return dict(result)


@app.post("/api/plan/cancel")
def plan_cancel() -> dict:
    with srv._plan_lock:
        source = srv._advisory_transport_context.get()
        guard = srv._advisory_job_guards.get('planning')
        if source is not None and (srv._plan_job.get('run_id') != source.as_metadata()['action_run_id']
                or (guard is not None and guard['source'] is not None and guard['source']._action is not source._action)):
            return {'ok': True, 'already_idle': True}
        srv._advisory_context_for_job('planning', srv._plan_job)
        guard = srv._advisory_job_guards.pop('planning', None)
        if guard is not None:
            guard['event'].set()
        if srv._plan_job["state"] == "idle":
            return {"ok": True, "already_idle": True}
        srv._plan_job.update(
            state="idle", mode=None, goal=None, profile=None, round_id=None,
            candidates=None, plan=None, author=None, error=None,
            started_at=None, finished_at=None, review_path=None,
        )
        if guard is not None and guard['source'] is not None:
            from jarvis.advisory_sources import record_advisory_job
            record_advisory_job(guard['source'], srv._plan_job, allow_cancelled=True)
    return {"ok": True}
