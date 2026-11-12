"""Admin sidecar routes: self-edit session endpoints (/api/selfedit/* except stage and run).

Moved verbatim from jarvis/admin/server.py (B6). Helpers, state and imported
modules are reached as `srv.<name>` at call time, never imported here, so a
test that monkeypatches jarvis.admin.server is seen by these handlers.
Only jarvis.admin.server imports this module.
"""

from __future__ import annotations

from jarvis.admin import server as srv
from jarvis.admin.server import (  # request bodies named in signatures
    SelfEditWriteIn,
    VerifyAppearanceBody,
)

# Routes register on the server's one FastAPI app (see the B6 note there).
app = srv.app


# ------------------------------------------------------------- self-edit


@app.get("/api/selfedit/models")
def selfedit_models() -> dict:
    return {"ok": True, "models": srv.available_models()}


@app.get("/api/selfedit/status")
def selfedit_status() -> dict:
    if srv._busy():
        return {"ok": False, "error": "an upgrade run is in progress — ask for status instead"}
    return srv._selfedit_service.status()


@app.get("/api/selfedit/file")
def selfedit_file(path: str) -> dict:
    """SE2 — read one file from the SESSION worktree, allowlist-checked.
    Thin wrapper over the read_file the planner has always used."""
    if not srv.authoring_enabled():
        return dict(srv._AUTHORING_OFF)
    pending = srv._prepare_file_access()
    if pending is not None:
        return pending
    return srv._selfedit_service.read_file(path)


@app.post("/api/selfedit/write")
def selfedit_write(body: SelfEditWriteIn) -> dict:
    """SE2 — write one allowlisted edit into the session worktree.

    Same SelfEditService.propose_edit the planner calls: the same allowlist
    check, the same worktree, the same returned diff. Nothing about WHAT an
    edit may touch changes here — only which agent does the writing."""
    if not srv.authoring_enabled():
        return dict(srv._AUTHORING_OFF)
    if not srv._selfedit_service.branch:
        return {"ok": False, "error": "no open self-edit session — start one first"}
    pending = srv._prepare_file_access()
    if pending is not None:
        return pending
    if srv._busy():
        return {"ok": False, "error": "validation is running — wait for it to finish, then edit"}
    return srv._selfedit_service.propose_edit(
        body.path, body.content, body.rationale, body.visual_intent,
        proposal=body.proposal,
    )


@app.post("/api/selfedit/finish")
def selfedit_finish() -> dict:
    """SE4 — start the finish job: validate, and submit if green."""
    if not srv.authoring_enabled():
        return dict(srv._AUTHORING_OFF)
    service = srv._lifecycle_service(srv._selfedit_service, terminal=True)
    session = service.status()
    action_run_id = str(session.get("id") or "")
    if action_run_id:
        prior = srv._prior_selfedit_publish(action_run_id)
        if prior is not None:
            return prior
    if session.get("phase") == "publication_pending":
        return {
            "ok": False, "state": "unknown", "action_run_id": action_run_id or None,
            "error": "a previous publication may have started; inspect the saved sandbox and PR state before retrying",
        }
    if not session.get("branch"):
        return {"ok": False, "error": "no open self-edit session"}
    if not session.get("proposals"):
        return {"ok": False, "error": "nothing has been written yet"}
    with srv._finish_lock:
        # The busy check is INLINED rather than calling _busy(): _busy()
        # acquires _finish_lock itself, and calling it from inside this
        # block would deadlock. _run_job's state is read without _run_lock
        # deliberately — a single dict lookup, and the authoritative guard
        # against two jobs is this lock plus _run_lock in selfedit_run.
        if srv._opening_job["state"] == "starting" or srv._run_job["state"] == "running" or srv._finish_job["state"] in (
            "validating", "submitting",
        ):
            return {"ok": False,
                    "error": "a run is already in progress — ask for status instead"}
        srv._finish_job.update(
            state="validating", checks=None, pr_url=None, notice=None, cancel_requested=False,
            human_only=None, apply_command=None,
            run_id=session.get("run_id") or service.run_id,
            action_run_id=action_run_id,
            started_at=srv.time.time(), finished_at=None,
        )
    srv.logger.info("selfedit_state_transition state=finish_validating run_id=%s",
                srv._selfedit_service.run_id)
    srv.threading.Thread(target=srv._source_worker_target(srv._run_finish), daemon=True).start()
    return {
        "ok": True, "started": True, "state": "validating",
        "action_run_id": action_run_id,
    }


@app.post("/api/selfedit/validate")
def selfedit_validate() -> dict:
    if srv._busy():
        return {"ok": False, "error": "an upgrade run is in progress — ask for status instead"}
    result = srv._selfedit_service.validate()
    srv.logger.info("selfedit_state_transition state=validated ok=%s", result.get("ok"))
    return result


@app.post("/api/selfedit/verify-appearance")
def selfedit_verify_appearance(body: VerifyAppearanceBody | None = None) -> dict:
    """B2 — a CHECK, not a gate. Deliberately absent from validate()'s checks
    list: validation runs before the branch is on screen, so a capture then
    photographs the pre-change console and its green tick would mean
    nothing."""
    if srv._busy():
        return {"ok": False, "error": "an upgrade run is in progress — ask for status instead"}
    body = body or srv.VerifyAppearanceBody()
    result = srv._selfedit_service.verify_appearance(
        branch_override=body.branch_override, display=body.display)
    srv.logger.info("selfedit_verify_appearance ok=%s branch_present=%s",
                result.get("ok"), bool(result.get("branch")))
    return result


@app.post("/api/selfedit/submit")
def selfedit_submit() -> dict:
    if srv._busy():
        return {"ok": False, "error": "an upgrade run is in progress — ask for status instead"}
    session = srv._selfedit_service.status()
    action_run_id = str(session.get("id") or "")
    if not action_run_id:
        return {"ok": False, "error": "no open self-edit session"}
    prior = srv._prior_selfedit_publish(action_run_id)
    if prior is not None:
        return prior
    if session.get("phase") == "publication_pending":
        return {
            "ok": False, "state": "unknown", "action_run_id": action_run_id,
            "error": "a previous publication may have started; inspect the saved sandbox and PR state before retrying",
        }
    if not session.get("validated_ok") or not session.get("proposals"):
        return {"ok": False, "error": "validation must pass and edits must exist before submission"}
    try:
        claimed = srv.claim_execution_action(
            srv._SELFEDIT_PUBLISH_ACTION_SCOPE, action_run_id,
        )
    except Exception as exc:
        srv.logger.warning("selfedit_publish_claim_write_failed error_type=%s", type(exc).__name__)
        return {"ok": False, "error": "could not safely record publication; no pull request was submitted"}
    if not claimed:
        return srv._prior_selfedit_publish(action_run_id) or {
            "ok": False, "state": "unknown", "action_run_id": action_run_id,
            "error": "publication was already claimed; inspect status before retrying",
        }
    try:
        srv.update_execution_action(
            srv._SELFEDIT_PUBLISH_ACTION_SCOPE, action_run_id, "running",
        )
    except Exception as exc:
        srv.logger.warning("selfedit_publish_claim_update_failed error_type=%s", type(exc).__name__)
    result = srv._selfedit_service.submit()
    if result.get("ok"):
        try:
            srv.update_execution_action(
                srv._SELFEDIT_PUBLISH_ACTION_SCOPE, action_run_id, "completed",
            )
        except Exception as exc:
            srv.logger.warning("selfedit_publish_claim_update_failed error_type=%s", type(exc).__name__)
    srv.logger.info("selfedit_state_transition state=submitted ok=%s", result.get("ok"))
    return {**result, "action_run_id": action_run_id}


@app.post("/api/selfedit/cancel")
def selfedit_cancel() -> dict:
    """Cancel planner, validation or publication through the saved VM session."""
    with srv._run_lock:
        running = srv._run_job["state"] == "running"
        agent = srv._run_agent_instance
        if running:
            srv._run_job["cancel_requested"] = True
    with srv._finish_lock:
        finishing = srv._finish_job["state"] in {"validating", "submitting"}
        if finishing:
            srv._finish_job["cancel_requested"] = True
    with srv._opening_lock:
        opening = srv._opening_job["state"] == "starting"
        if opening:
            srv._opening_job["cancel_requested"] = True
    if not running and not finishing and not opening:
        phase = srv._selfedit_service.status().get("phase")
        if phase not in {"creating", "starting", "validating", "publishing", "publication_pending"}:
            return {"ok": False, "error": "no self-edit run is in progress — use revert to drop an idle session"}
    if running and agent is not None:
        agent.request_cancel()
    else:
        srv._selfedit_service.cancel()
    srv.logger.info("selfedit_state_transition state=cancel_requested")
    return {"ok": True, "cancel_requested": True,
            "note": "Sandbox cancellation requested; the planner stops at its next step. Any already-created pull request remains visible."}


@app.post("/api/selfedit/revert")
def selfedit_revert() -> dict:
    # A revert while the planner is RUNNING used to be refused outright,
    # which left no path at all to stop a runaway run (2026-08-22/23). It
    # now means "stop and discard": request the cooperative cancel and let
    # _run_agent perform the revert when the loop yields. This is what the
    # voice path (mcp_selfedit's selfedit_revert tool) reaches, so "cancel
    # the self-edit" works by voice with no new tool.
    if srv._busy():
        return srv.selfedit_cancel()
    result = srv._selfedit_service.revert()
    srv.logger.info("selfedit_state_transition state=reverted ok=%s", result.get("ok"))
    return result


@app.post("/api/selfedit/reject")
def selfedit_reject() -> dict:
    """E3 (MORTIMER_LLM_COUNCIL_PLAN.md D2). MORTIMER_LLM_COUNCIL_V2_
    PLAN.md V5: the revert stays SYNCHRONOUS (it is fast and its result
    must be in the response); the council moves to the same background
    job slot as a manual convene (`trigger='E3'`), with its goal/context
    captured BEFORE the revert clears `_selfedit_service.proposals` (the
    revert must never race the council reading the diff it's advising
    on). Advisory only: unlike D2.1's in-loop E1 escalation, there is no
    live agent run waiting to consume a brief here, so this endpoint
    does not auto-start a new run — starting one with the council's
    winning approach is a separate, explicit POST /api/selfedit/run.
    Poll GET /api/council/job for the council result."""
    if srv._busy():
        return {"ok": False, "error": "an upgrade run is in progress — ask for status instead"}
    if not srv._selfedit_service.branch:
        return {"ok": False, "error": "no active self-edit session to reject"}
    goal = srv._selfedit_service.goal or ""
    context = {"diff": srv._selfedit_service.proposals, "checks": None}

    council_started = False
    with srv._council_lock:
        if srv._council_job["state"] != "running":
            srv._council_job.update(
                state="running", trigger="E3", goal=goal, round_id=None,
                winner=None, winner_mean=None, select_reason=None, error=None,
                started_at=srv.time.time(), finished_at=None,
            )
            council_started = True
    if council_started:
        srv._start_advisory_thread(
            srv._run_council_job,
            kwargs={"trigger": "E3", "goal": goal, "context": context},
        )

    revert_result = srv._selfedit_service.revert()
    srv.logger.info("selfedit_state_transition state=rejected ok=%s", revert_result.get("ok"))
    return {
        "ok": True, "reverted": revert_result, "council_started": council_started,
    }
