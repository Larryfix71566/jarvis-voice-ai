"""Admin sidecar routes: self-edit staging and the async run job (/api/selfedit/stage, /api/selfedit/run).

Moved verbatim from jarvis/admin/server.py (B6). Helpers, state and imported
modules are reached as `srv.<name>` at call time, never imported here, so a
test that monkeypatches jarvis.admin.server is seen by these handlers.
Only jarvis.admin.server imports this module.
"""

from __future__ import annotations

from jarvis.admin import server as srv
from jarvis.admin.server import (  # request bodies named in signatures
    GoalIn,
    SelfEditStageIn,
)

# Routes register on the server's one FastAPI app (see the B6 note there).
app = srv.app


@app.post("/api/selfedit/stage")
def selfedit_stage(body: SelfEditStageIn) -> dict:
    """G2: create a stateful staging record for a self-edit preview.

    mcp_selfedit.logic.selfedit_start(confirm=false) calls this instead of
    just composing a summary client-side — the returned staging_id is what
    confirm=true must pass back, so the goal/profile/plan_path actually
    started are BYTE-IDENTICAL to what was previewed, never re-derived by
    the model from conversational memory."""
    goal = (body.goal or "").strip()
    if not goal:
        return {"ok": False, "error": "a goal is required — what should I change?"}
    plan_path = (body.plan_path or "").strip() or None
    # MORTIMER_SELFEDIT_TIERS_PLAN.md — tier pre-flight at PREVIEW time: a
    # goal naming a Tier-0 (human-only) file, or a Tier-B (core) file with
    # no plan, is refused here in one sentence — before staging, before
    # confirm, before a planner run rediscovers the same wall (2026-08-30:
    # three runs, ~2.5 minutes each, all "declined: not on the allowlist").
    flight = srv._selfedit_service.preflight(
        goal, has_plan=bool(plan_path), target_paths=body.target_paths,
    )
    if not flight["ok"]:
        return {"ok": False, "error": flight["error"], "tiers": flight["tiers"]}
    staging_id = srv._new_staging_id()
    with srv._staging_lock:
        srv._prune_expired_stagings()
        srv._selfedit_stagings[staging_id] = {
            "goal": goal,
            "profile": body.profile,
            "plan_path": plan_path,
            "run_id": (body.run_id or "").strip() or None,   # GL9
            # SE3 — kept, not dropped: the confirm returns these to the
            # developer as the files it said it would change, so authoring
            # starts from the same list preflight classified.
            "target_paths": list(body.target_paths or []),
            "created_at": srv.time.time(),
        }
    return {
        "ok": True,
        "staging_id": staging_id,
        "expires_in_s": srv.SELFEDIT_STAGING_TTL_S,
        # The tool's spoken preview names core files so the user hears
        # "this touches the voice core" before saying yes.
        "tiers": flight["tiers"],
        # W8 — and the human-only files, whose change becomes a proposal.
        "human_only": flight.get("human_only") or [],
        "core_change": bool(flight["tiers"]["core"]),
    }


@app.post("/api/selfedit/run")
def selfedit_run(body: GoalIn) -> dict:
    """Start an upgrade run in the background; poll GET /api/selfedit/run.

    G2: prefer {staging_id} (from POST /api/selfedit/stage) over the bare
    {goal, profile?, run_id} form — the staged record is the source of truth
    for what was actually previewed. A bare start without a stable run_id is
    refused because it cannot be reconciled safely after a transport retry."""
    staging_id = (body.staging_id or "").strip()
    bare_goal = (body.goal or "").strip()
    requested_action_id = staging_id or None
    requested_action_scope = srv._SELFEDIT_STAGED_START_ACTION_SCOPE
    # Issued staging IDs are exactly 12 lowercase hexadecimal characters.
    # Avoid querying the execution-claim table for arbitrary/mangled input;
    # the one-live-stage repair below resolves that to the canonical ID.
    if requested_action_id and srv.re.fullmatch(r"[0-9a-f]{12}", requested_action_id):
        duplicate = srv._prior_staged_selfedit_action(requested_action_id)
        if duplicate is not None:
            return duplicate
    # Refuse a confirm that lands during a live run BEFORE touching the
    # staging (2026-09-07 review, F4): the pop used to come first, so the
    # refusal itself consumed the preview the user had just approved.
    duplicate_claim = False
    with srv._run_lock:
        if (srv._run_job["state"] == "running" or srv._opening_job["state"] == "starting"
                or srv._finish_job["state"] in {"validating", "submitting"}):
            return {
                "ok": False,
                "error": "an upgrade run is already in progress — ask for status instead",
                "job": dict(srv._run_job),
            }
    if staging_id or not bare_goal:
        rec, staging_id, live = srv._take_staging(staging_id)
        if rec is None:
            if len(live) > 1:
                return {
                    "ok": False,
                    "error": (
                        "more than one staged edit is live ("
                        + ", ".join(live)
                        + ") — say which one to start, or preview again."
                    ),
                    "stagings": live,
                }
            what = (
                f"no staged edit with id '{staging_id}'" if staging_id
                else "no staged edit is live and no goal was given"
            )
            return {
                "ok": False,
                "error": (
                    f"{what} — the staging may have "
                    f"expired (staging lasts {int(srv.SELFEDIT_STAGING_TTL_S // 60)} "
                    "minutes) or was already used. Call selfedit_start again "
                    "(confirm=false) to preview a new one."
                ),
            }
        goal = rec["goal"]
        # The claim identity must be the exact ID issued by /stage, even
        # when _take_staging repaired a harmless relay typo.
        requested_action_id = staging_id
        profile = rec["profile"]
        plan_path = rec["plan_path"] or ""
        run_id = rec.get("run_id")
        target_paths = list(rec.get("target_paths") or [])
    else:
        goal = bare_goal
        run_id = (body.run_id or "").strip()
        if not run_id:
            return {
                "ok": False,
                "error": "a stable run_id is required for a bare self-edit start; preview and confirm a staged request instead",
            }
        if len(run_id) > 256:
            return {"ok": False, "error": "run_id exceeds the supported length"}
        srv.logger.warning(
            "selfedit_run_stateless_confirm — pass staging_id instead "
            "(deprecated fallback, see G2)"
        )
        profile = body.profile
        plan_path = (body.plan_path or "").strip()
        run_id = run_id or None
        requested_action_id = run_id
        requested_action_scope = srv._SELFEDIT_RUN_START_ACTION_SCOPE
        prior = srv._prior_staged_selfedit_action(
            requested_action_id, requested_action_scope,
        )
        if prior is not None:
            return prior
        # The deprecated bare-goal form carries no target_paths (GoalIn has
        # no such field and gains none): only a staged preview classified
        # them.
        target_paths = []

    if srv.authoring_enabled() and body.author and not plan_path and body.plan is None:
        # SE3 — developer-authored: an author=true confirm with no plan
        # document is a single stated goal, which the developer can author
        # in a few tool calls
        # (measured exploring runs: 15-72 s). Open the session synchronously
        # and hand it back; the developer writes in the SAME delegation
        # rather than restating the goal to a second LLM that starts blind.
        # A plan_path (or an explicit plan) is implementation-scale work and
        # still goes to the Upgrade Agent, below. Two declared fields
        # (author, plan_path), no judgment.
        return srv._begin_authoring(
            goal, run_id, target_paths, action_run_id=requested_action_id,
            action_scope=requested_action_scope,
        )

    plan = body.plan
    if plan is None and plan_path:
        # Voice-path plan seeding: read the plan document once,
        # synchronously, before the thread launches — mirrors plan_start's
        # review_path read-and-refuse (MORTIMER_PLAN_REVIEW_AND_DOCS_PLAN.md
        # R1). Same truncation knob: a seeded plan is a document injection
        # with the same size concerns as a reviewed one.
        read_result = srv.repo_logic.repo_read_file(plan_path)
        srv._source_plan_observed(plan_path, read_result)
        if not read_result.get("ok"):
            return {"ok": False, "error": read_result.get("error")}
        plan = read_result.get("content") or ""
        if len(plan) > srv.council_config.PLAN_REVIEW_DOC_MAX_CHARS:
            plan = (
                plan[: srv.council_config.PLAN_REVIEW_DOC_MAX_CHARS]
                + "\n\n… (plan truncated at injection)"
            )
    with srv._run_lock:
        if (srv._run_job["state"] == "running" or srv._opening_job["state"] == "starting"
                or srv._finish_job["state"] in {"validating", "submitting"}):
            return {
                "ok": False,
                "error": "an upgrade run is already in progress — ask for status instead",
                "job": dict(srv._run_job),
            }
        try:
            # Construct now so an unknown profile fails fast, synchronously,
            # before we report the run as started.
            agent = srv._make_agent(srv._selfedit_service, profile, run_id)
        except srv.UnknownModelProfileError as exc:
            return {"ok": False, "error": str(exc)}
        if requested_action_id:
            try:
                claimed = srv.claim_execution_action(
                    requested_action_scope, requested_action_id,
                )
            except Exception as exc:
                srv.logger.warning("selfedit_start_claim_write_failed error_type=%s", type(exc).__name__)
                return {"ok": False, "error": "could not safely record this self-edit; no job was started"}
            if not claimed:
                duplicate_claim = True
        if not duplicate_claim:
            srv._run_job.update(
                state="running", cancel_requested=False,
                run_id=run_id,
                goal=goal,
                profile=agent.model_label(),
                summary=None,
                started_at=srv.time.time(),
                finished_at=None,
                submitted=False,
                pr_url=None,
                action_run_id=requested_action_id,
                action_scope=requested_action_scope,
            )
    if duplicate_claim:
        return srv._prior_staged_selfedit_action(
            requested_action_id, requested_action_scope,
        ) or {
            "ok": False, "error": "the self-edit claim could not be reconciled; no job was started",
        }
    srv.logger.info("selfedit_state_transition state=running")
    try:
        srv.threading.Thread(
            target=srv._source_worker_target(srv._run_agent),
            args=(goal, profile, plan, run_id, requested_action_id,
                  requested_action_scope),
            **({'kwargs': srv._source_worker_kwargs()} if srv._workspace_start_policy.get() is not None else {}),
            daemon=True,
        ).start()
    except Exception as exc:
        srv.logger.warning("selfedit_worker_start_failed error_type=%s", type(exc).__name__)
        with srv._run_lock:
            srv._run_job.update(
                state="error", summary="Upgrade worker could not be started.",
                finished_at=srv.time.time(),
            )
        srv._update_staged_selfedit_claim(
            requested_action_id, "failed", requested_action_scope,
        )
        return {"ok": False, "error": "Upgrade worker could not be started."}
    return {
        "ok": True, "started": True, "profile": agent.model_label(),
        "action_run_id": requested_action_id,
    }


@app.get("/api/selfedit/run")
def selfedit_run_status(
    action_run_id: str | None = None,
    finish_action_id: str | None = None,
) -> dict:
    with srv._run_lock:
        job = dict(srv._run_job)
    with srv._opening_lock:
        opening = dict(srv._opening_job)
    requested_action_id = (action_run_id or "").strip()
    requested_finish_id = (finish_action_id or "").strip()
    if requested_action_id and requested_finish_id:
        return {"ok": False, "error": "request only one self-edit action identity"}
    if requested_finish_id:
        if len(requested_finish_id) > 256:
            return {"ok": False, "error": "self-edit action identity is invalid"}
        with srv._finish_lock:
            finish_snapshot = dict(srv._finish_job)
        if finish_snapshot.get("action_run_id") != requested_finish_id:
            try:
                receipt = srv.get_execution_action(
                    srv._SELFEDIT_PUBLISH_ACTION_SCOPE, requested_finish_id,
                )
            except Exception as exc:
                srv.logger.warning("selfedit_status_claim_read_failed error_type=%s", type(exc).__name__)
                return {"ok": False, "error": "the self-edit submission receipt is unavailable"}
            session = srv._selfedit_service.status()
            if receipt is None:
                # Validation is deliberately not claimed, so a failed
                # validation remains repairable. The durable sandbox session
                # is the authority for this specific session's saved checks.
                if session.get("id") != requested_finish_id:
                    return {"ok": False, "error": "no self-edit submission receipt exists for that action"}
                phase = session.get("phase")
                if phase == "validation_failed":
                    finish_state = "failed"
                else:
                    return {"ok": False, "error": "no self-edit submission receipt exists for that action"}
                return {
                    "ok": True,
                    "job": {"state": "idle", "action_run_id": requested_finish_id,
                            "result_available": False},
                    "finish": {"state": finish_state, "action_run_id": requested_finish_id,
                               "checks": [], "result_available": False},
                    "opening": {"state": "idle"}, "status": {"active": True}, "stagings": [],
                }
            receipt_state = receipt["status"]
            same_session = session.get("id") == requested_finish_id
            publication = session.get("publication") or {} if same_session else {}
            pr_url = (
                publication.get("url") or session.get("pr_url")
                if same_session else None
            )
            if pr_url:
                finish_state = "done"
                try:
                    srv.update_execution_action(
                        srv._SELFEDIT_PUBLISH_ACTION_SCOPE, requested_finish_id, "completed",
                    )
                except Exception as exc:
                    srv.logger.warning("selfedit_publish_claim_update_failed error_type=%s", type(exc).__name__)
            elif receipt_state == "failed":
                finish_state = "failed"
            else:
                # Claimed/running can mean publication reached GitHub before
                # the process stopped. Completed without a saved URL is also
                # unresolved. Neither is safe to replay automatically.
                finish_state = "unknown"
            finish_result = {
                "state": finish_state, "action_run_id": requested_finish_id,
                "result_available": bool(pr_url),
                "reconciliation_required": finish_state == "unknown",
            }
            if pr_url:
                finish_result["pr_url"] = pr_url
            return {
                "ok": True,
                "job": {"state": "idle", "action_run_id": requested_finish_id,
                        "result_available": False},
                "finish": finish_result,
                "opening": {"state": "idle"}, "status": {"active": False}, "stagings": [],
            }
    if requested_action_id:
        if len(requested_action_id) > 256:
            return {"ok": False, "error": "self-edit action identity is invalid"}
        live_action_matches = (
            job.get("action_run_id") == requested_action_id
            and job.get("action_scope", srv._SELFEDIT_STAGED_START_ACTION_SCOPE)
            in {srv._SELFEDIT_STAGED_START_ACTION_SCOPE, srv._SELFEDIT_RUN_START_ACTION_SCOPE}
        ) or (
            opening.get("action_run_id") == requested_action_id
            and opening.get("action_scope", srv._SELFEDIT_STAGED_START_ACTION_SCOPE)
            in {srv._SELFEDIT_STAGED_START_ACTION_SCOPE, srv._SELFEDIT_RUN_START_ACTION_SCOPE}
        )
        if not live_action_matches:
            try:
                receipt = srv.get_execution_action(
                    srv._SELFEDIT_STAGED_START_ACTION_SCOPE, requested_action_id,
                )
                if receipt is None:
                    receipt = srv.get_execution_action(
                        srv._SELFEDIT_RUN_START_ACTION_SCOPE, requested_action_id,
                    )
            except Exception as exc:
                srv.logger.warning("selfedit_status_claim_read_failed error_type=%s", type(exc).__name__)
                return {"ok": False, "error": "the self-edit action receipt is unavailable"}
            if receipt is None:
                return {"ok": False, "error": "no self-edit action receipt exists for that action"}
            state = receipt["status"]
            if state in {"claimed", "running", "awaiting_choice"}:
                state = "unknown"
            return {
                "ok": True,
                "job": {
                    "state": state, "action_run_id": requested_action_id,
                    "result_available": False,
                    "reconciliation_required": state == "unknown",
                },
                "finish": {}, "opening": {"state": "idle"},
                "status": {"active": False}, "stagings": [],
            }
    # 2026-08-25 — a live incident: the developer fabricated "staging
    # expires after 10 minutes... it's gone" from THIS endpoint, which had
    # no way to answer that question at all — job/status describe the run
    # loop, not the separate _selfedit_stagings dict a staging_id lives in.
    # Surfacing real staging records (never their goal/plan_path text, just
    # enough to confirm liveness) closes that gap: a tool that gets asked
    # "is staging X still live" can now check, instead of guessing.
    with srv._staging_lock:
        srv._prune_expired_stagings()
        now = srv.time.time()
        stagings = [
            {
                "staging_id": sid,
                "age_s": round(now - rec["created_at"], 1),
                "expires_in_s": round(
                    srv.SELFEDIT_STAGING_TTL_S - (now - rec["created_at"]), 1,
                ),
            }
            for sid, rec in srv._selfedit_stagings.items()
        ]
    with srv._finish_lock:
        finish = dict(srv._finish_job)
    return {
        "ok": True,
        "job": job,
        "finish": finish,
        "opening": opening,
        "status": srv._selfedit_service.status(),
        "stagings": stagings,
    }
