"""Admin sidecar routes: app-build job (/api/appbuild/*).

Moved verbatim from jarvis/admin/server.py (B6). Helpers, state and imported
modules are reached as `srv.<name>` at call time, never imported here, so a
test that monkeypatches jarvis.admin.server is seen by these handlers.
Only jarvis.admin.server imports this module.
"""

from __future__ import annotations

from jarvis.admin import server as srv
from jarvis.admin.server import (  # request bodies named in signatures
    AppBuildGoalIn,
)

# Routes register on the server's one FastAPI app (see the B6 note there).
app = srv.app


# ------------------------------------------------------------- app-build
# MORTIMER_MODEL_DISCIPLINE_AND_MAC_SHELL_PLAN.md D5. Same background-
# thread-plus-polling shape as self-edit above, in its own job slot/lock
# so an app build never blocks a self-edit run (or vice versa). No merge
# endpoint here either — merging an app-build PR is human, on GitHub,
# always, same rule as self-edit.


@app.post("/api/appbuild/start")
def appbuild_start(body: AppBuildGoalIn) -> dict:
    """Start an app-build run in the background; poll GET /api/appbuild/job."""
    goal = (body.goal or "").strip()
    if not goal:
        return {"ok": False, "error": "a goal is required — what should I build?"}
    try:
        app_name = srv.validate_app_name(body.app)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    run_id = (body.run_id or "").strip()
    if not run_id:
        return {
            "ok": False,
            "error": "a stable run_id is required for an app-build start",
        }
    if len(run_id) > 256:
        return {"ok": False, "error": "app-build action identity is invalid"}
    try:
        prior = srv.get_execution_action(srv._APPBUILD_START_ACTION_SCOPE, run_id)
    except Exception as exc:
        srv.logger.warning("appbuild_start_claim_read_failed error_type=%s", type(exc).__name__)
        return {
            "ok": False,
            "error": "could not verify whether this app-build action already started; no retry was launched",
            "outcome": "unknown", "action_run_id": run_id,
        }
    if prior is not None:
        with srv._appbuild_lock:
            same_live_job = srv._appbuild_job.get("run_id") == run_id
            live_state = srv._appbuild_job.get("state") or "unknown"
        state = live_state if same_live_job else prior.get("status", "unknown")
        if state in {"claimed", "running", "awaiting_choice"} and not same_live_job:
            state = "unknown"
        return {
            "ok": True, "started": False, "duplicate": True,
            "state": state, "action_run_id": run_id,
            "summary": (
                "This app-build action was already claimed for this execution; "
                "no new build was started. Check app_build_status with this "
                "action_run_id before considering any retry."
            ),
        }
    plan = body.plan
    plan_path = (body.plan_path or "").strip()
    if plan is None and plan_path:
        # Voice-path plan seeding — identical read-and-refuse pattern to
        # selfedit_run's, so an unreadable plan can never seed a build.
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
    with srv._appbuild_lock:
        if srv._appbuild_job["state"] in {"running", "submitting"}:
            return {
                "ok": False,
                "error": "an app build is already in progress — ask for status instead",
                "job": dict(srv._appbuild_job),
            }
        try:
            # Construct now (against a throwaway probe workspace, never
            # cloned) so an unknown profile or a missing GITHUB_TOKEN fails
            # fast, synchronously, before we report the build as started —
            # same rule selfedit_run's _make_agent call follows.
            probe = srv.AppWorkspace(app_name)
            agent = srv._make_appbuild_agent(probe, body.profile)
        except srv.UnknownModelProfileError as exc:
            return {"ok": False, "error": str(exc)}
        except Exception as exc:  # noqa: BLE001 — e.g. GitHubError: no token configured
            return {"ok": False, "error": str(exc)}
        try:
            claimed = srv.claim_execution_action(srv._APPBUILD_START_ACTION_SCOPE, run_id)
        except Exception as exc:
            srv.logger.warning("appbuild_start_claim_write_failed error_type=%s", type(exc).__name__)
            return {"ok": False, "error": "could not safely record this app-build action; no build was started"}
        if not claimed:
            return {
                "ok": True, "started": False, "duplicate": True,
                "state": "unknown", "action_run_id": run_id,
                "summary": (
                    "This app-build action was already claimed for this execution; "
                    "no new build was started. Check app_build_status with this "
                    "action_run_id before considering any retry."
                ),
            }
        srv._appbuild_workspace = None
        srv._appbuild_agent_instance = None
        srv._appbuild_job.update(
            state="running", app=app_name, goal=goal, cancel_requested=False,
            submitted=False, pr_url=None,
            profile=agent.model_label(), summary=None,
            started_at=srv.time.time(), finished_at=None,
            run_id=run_id or None,
        )
    srv.logger.info("appbuild_state_transition state=running")
    srv._update_appbuild_start_claim(run_id, "running")
    worker = srv.threading.Thread(
        target=srv._source_worker_target(srv._run_appbuild_agent), args=(app_name, goal, body.profile, plan, run_id), daemon=True,
        **({'kwargs': srv._source_worker_kwargs()} if srv._workspace_start_policy.get() is not None else {}),
    )
    try:
        worker.start()
    except Exception as exc:
        srv.logger.warning("appbuild_thread_start_failed error_type=%s", type(exc).__name__)
        with srv._appbuild_lock:
            srv._appbuild_job.update(state="error", finished_at=srv.time.time())
        srv._update_appbuild_start_claim(run_id, "failed")
        return {"ok": False, "error": "the app-build worker could not be started"}
    return {"ok": True, "started": True, "profile": agent.model_label()}


@app.get("/api/appbuild/job")
def appbuild_job_status(
    run_id: str | None = None, submit_action_id: str | None = None,
) -> dict:
    srv._recover_appbuild_workspace()
    with srv._appbuild_lock:
        job = dict(srv._appbuild_job)
        workspace = srv._appbuild_workspace
    requested_submit_id = (submit_action_id or "").strip()
    if requested_submit_id:
        if len(requested_submit_id) > 256:
            return {"ok": False, "error": "app-build submission identity is invalid"}
        status = workspace.status() if workspace is not None else {"active": False}
        try:
            receipt = srv.get_execution_action(
                srv._APPBUILD_SUBMIT_ACTION_SCOPE, requested_submit_id,
            )
        except Exception as exc:
            srv.logger.warning("appbuild_submit_status_claim_read_failed error_type=%s", type(exc).__name__)
            if not (status.get("id") == requested_submit_id
                    and (status.get("publication") or {}).get("url")):
                return {"ok": False, "error": "the app-build submission receipt is unavailable"}
            receipt = None
        publication = status.get("publication") or {}
        pr_url = status.get("pr_url") or publication.get("url")
        if pr_url:
            state = "completed"
        elif status.get("id") != requested_submit_id and receipt is None:
            return {"ok": False, "error": "no app-build submission receipt exists for that session"}
        elif status.get("phase") in {"publishing", "publication_pending"}:
            state = "unknown"
        elif receipt is None:
            return {"ok": False, "error": "no app-build submission receipt exists for that session"}
        elif receipt.get("status") in {"claimed", "running", "awaiting_choice"}:
            same_live_job = (
                job.get("submit_action_id") == requested_submit_id
                and job.get("state") == "submitting"
            )
            state = "submitting" if same_live_job else "unknown"
        else:
            state = receipt.get("status", "unknown")
        submit_job = {
            "state": state,
            "submit_action_id": requested_submit_id,
            "result_available": bool(pr_url),
            "reconciliation_required": state == "unknown",
        }
        if pr_url:
            submit_job["pr_url"] = pr_url
        return {"ok": True, "job": submit_job, "status": status}
    requested_run_id = (run_id or "").strip()
    if requested_run_id:
        if len(requested_run_id) > 256:
            return {"ok": False, "error": "app-build action identity is invalid"}
        if job.get("run_id") != requested_run_id:
            try:
                receipt = srv.get_execution_action(srv._APPBUILD_START_ACTION_SCOPE, requested_run_id)
            except Exception as exc:
                srv.logger.warning("appbuild_status_claim_read_failed error_type=%s", type(exc).__name__)
                return {"ok": False, "error": "the app-build action receipt is unavailable"}
            if receipt is None:
                return {"ok": False, "error": "no app-build action receipt exists for that execution"}
            state = receipt["status"]
            if state in {"claimed", "running", "awaiting_choice"}:
                state = "unknown"
            return {
                "ok": True,
                "job": {
                    "state": state, "run_id": requested_run_id,
                    "result_available": False,
                    "reconciliation_required": state == "unknown",
                },
                "status": {"active": False},
            }
    status = workspace.status() if workspace is not None else {"active": False}
    if job["state"] == "idle" and status.get("id"):
        job.update(state="recovered", app=status.get("app"), goal=status.get("goal"),
                   summary="Reopened the saved workspace. The earlier planner is not running.")
    return {"ok": True, "job": job, "status": status}


@app.post("/api/appbuild/submit")
def appbuild_submit() -> dict:
    workspace = srv._lifecycle_service(srv._recover_appbuild_workspace(), terminal=True)
    if workspace is None:
        return {"ok": False, "error": "no active app-build session to submit"}
    workspace_status = workspace.status()
    session_id = str(workspace_status.get("id") or "").strip()
    if not session_id or len(session_id) > 256:
        return {"ok": False, "error": "the app-build session has no stable submission identity; no pull request was submitted"}
    with srv._appbuild_lock:
        if srv._appbuild_job["state"] in {"running", "submitting"}:
            return {"ok": False, "error": "an app build is in progress — ask for status instead"}
    prior = srv._prior_appbuild_submit(session_id, workspace_status)
    if prior is not None:
        return prior
    with srv._appbuild_lock:
        if srv._appbuild_job["state"] in {"running", "submitting"}:
            return {"ok": False, "error": "an app build is in progress — ask for status instead"}
        prior = srv._prior_appbuild_submit(session_id, workspace_status)
        if prior is not None:
            return prior
        if not workspace_status.get("active") or not workspace_status.get("branch"):
            return {"ok": False, "error": "no active app-build session to submit"}
        if not workspace_status.get("proposals"):
            return {"ok": False, "error": "no app-build edits have been proposed"}
        if not workspace_status.get("validated_ok"):
            return {"ok": False, "error": "validation must pass before app-build submission"}
        try:
            claimed = srv.claim_execution_action(srv._APPBUILD_SUBMIT_ACTION_SCOPE, session_id)
        except Exception as exc:
            srv.logger.warning("appbuild_submit_claim_write_failed error_type=%s", type(exc).__name__)
            return {"ok": False, "error": "could not safely record app-build submission; no pull request was submitted"}
        if not claimed:
            return {
                "ok": False, "state": "unknown", "action_run_id": session_id,
                "reconciliation_required": True,
                "error": "app-build submission was already claimed; inspect status before retrying",
            }
        srv._update_appbuild_submit_claim(session_id, "running")
        operation_id = srv.uuid.uuid4().hex
        srv._appbuild_job.update(state="submitting", operation_id=operation_id, cancel_requested=False,
                            submitted=False, pr_url=None, finished_at=None,
                            submit_action_id=session_id)
    output = {}
    worker = srv.threading.Thread(
        target=srv._source_worker_target(srv._submit_appbuild),
        args=(workspace, operation_id, session_id, output), daemon=True,
    )
    try:
        worker.start()
    except Exception as exc:
        srv.logger.warning("appbuild_submit_thread_start_failed error_type=%s", type(exc).__name__)
        with srv._appbuild_lock:
            if srv._appbuild_job.get("operation_id") == operation_id:
                srv._appbuild_job.update(state="unknown", finished_at=srv.time.time())
        return {
            "ok": False, "state": "unknown", "action_run_id": session_id,
            "reconciliation_required": True,
            "error": "submission could not be started safely; inspect the saved workspace before retrying",
        }
    worker.join(timeout=0.05)
    if not worker.is_alive():
        return output["result"]
    return {"ok": True, "started": True, "state": "submitting"}


@app.post("/api/appbuild/cancel")
def appbuild_cancel() -> dict:
    """Stop a running build, including VM work, or discard an idle session."""
    srv._recover_appbuild_workspace()
    with srv._appbuild_lock:
        running = srv._appbuild_job["state"] in {"running", "submitting"}
        workspace = srv._appbuild_workspace
        agent = srv._appbuild_agent_instance
        if running:
            srv._appbuild_job["cancel_requested"] = True
    if running:
        # The job flag also covers cancellation before the worker
        # thread constructs its agent. Never hold the job lock during VM I/O.
        if agent is not None:
            agent.request_cancel()
        elif workspace is not None:
            workspace.cancel()
        return {"ok": True, "cancel_requested": True,
                "note": "Sandbox cancellation requested; the planner stops at its next step."}
    if workspace is None or not workspace.branch:
        return {"ok": False, "error": "no active app-build session to cancel"}
    result = workspace.revert()
    srv.logger.info("appbuild_state_transition state=cancelled ok=%s", result.get("ok"))
    return result
