"""Admin sidecar routes: skill runtime inventory and creator bridge (/api/skills/runtime-inventory, /api/skills/creator/*).

Moved verbatim from jarvis/admin/server.py (B6). Helpers, state and imported
modules are reached as `srv.<name>` at call time, never imported here, so a
test that monkeypatches jarvis.admin.server is seen by these handlers.
Only jarvis.admin.server imports this module.
"""

from __future__ import annotations

from fastapi import Request

from jarvis.admin import server as srv
from jarvis.admin.server import (  # request bodies named in signatures
    SkillCreatorAssociationIn,
    SkillCreatorToolIn,
    SkillRuntimeInventoryIn,
)

# Routes register on the server's one FastAPI app (see the B6 note there).
app = srv.app


@app.post("/api/skills/runtime-inventory")
def skills_runtime_inventory(body: SkillRuntimeInventoryIn, request: Request) -> dict:
    """Accept a fresh inventory only from Mortimer's service-bot token.

    This records discovered tools, never tool-call success or package/provider
    readiness. The receipt is held in process memory and expires quickly.
    """
    if not srv.auth_enabled():
        raise srv.HTTPException(status_code=503, detail="runtime evidence requires bearer authentication")
    identity = request.scope.get("client_identity")
    if identity is None:
        raise srv.HTTPException(status_code=503, detail="authenticated identity is unavailable")
    if getattr(identity, "name", None) != "service-bot":
        raise srv.HTTPException(status_code=403, detail="runtime evidence requires the service-bot identity")
    if body.schema_version != 1:
        raise srv.HTTPException(status_code=400, detail="unsupported runtime inventory schema")
    from jarvis.skill_runtime import update_runtime_inventory

    try:
        update_runtime_inventory(
            body.runtime_id, body.tools, body.complete,
            active=body.active, owner_id=body.owner_id,
        )
    except ValueError as exc:
        if str(exc) == "runtime_capacity_exceeded":
            raise srv.HTTPException(status_code=503, detail="runtime inventory capacity is full") from None
        raise srv.HTTPException(status_code=400, detail="invalid runtime inventory") from None
    return {"ok": True}


@app.post("/api/skills/creator/associate")
def associate_skill_creator_run(body: SkillCreatorAssociationIn, request: Request) -> dict:
    """Durably bind only a RunLogger-created Developer run to a creator job."""
    srv._creator_internal_owner(body, request)
    srv._verify_developer_run(body)
    from jarvis.skill_requests import SkillRequestError, associate_developer_run
    try:
        associate_developer_run(
            body.owner_id, body.request_id,
            session_id=body.bot_session_id, run_id=body.developer_run_id,
            creator_revision=body.creator_revision,
        )
    except SkillRequestError as exc:
        raise srv.HTTPException(status_code=exc.status_code, detail=str(exc)) from None
    result = {"ok": True, "developer_run_id": body.developer_run_id}
    if body.source_authority:
        from jarvis.development_attestation import ensure_admin_source_authority
        from jarvis.development_sources import creator_context
        from jarvis.skill_requests import _service

        state = srv._creator_internal_owner(body, request)
        run = srv._verify_developer_run(body)
        if state.get("cancel_requested"):
            raise srv.HTTPException(status_code=409, detail="creator request is cancelling")
        try:
            source_context = creator_context(
                _service(state["skill_id"], expected_job_id=state["sandbox_job_id"]), state, run,
            )
            ensure_admin_source_authority()
            result["source_context"] = source_context.as_metadata()
        except Exception:
            raise srv.HTTPException(status_code=503, detail="creator source authority is unavailable") from None
    return result


@app.post("/api/skills/creator/tool")
def execute_skill_creator_tool(body: SkillCreatorToolIn, request: Request) -> dict:
    """Execute one of the four creator tools for its exact live run/job pair."""
    from jarvis.skill_requests import _service

    state = srv._creator_internal_owner(body, request)
    if (state.get("developer_run_id") != body.developer_run_id
            or state.get("creator_revision") != body.creator_revision):
        raise srv.HTTPException(status_code=409, detail="creator tool is not bound to this Developer run")
    run = srv._verify_developer_run(body)
    if state.get("cancel_requested"):
        raise srv.HTTPException(status_code=409, detail="creator request is cancelling")
    tool = body.tool_name
    args = body.arguments
    service = _service(state["skill_id"], expected_job_id=state["sandbox_job_id"])
    live = service.status()
    if live.get("run_id") != state.get("sandbox_job_id"):
        raise srv.HTTPException(status_code=409, detail="creator sandbox job changed")
    def invoke() -> dict:
        if tool == "file_read":
            if set(args) != {"path"} or not isinstance(args.get("path"), str):
                raise srv.HTTPException(status_code=400, detail="invalid creator tool arguments")
            result = service.read_file(args["path"])
        elif tool == "edit_propose":
            allowed = {"path", "new_content", "rationale", "visual_intent"}
            if (not {"path", "new_content"} <= set(args) or set(args) - allowed
                    or not isinstance(args.get("path"), str)
                    or not isinstance(args.get("new_content"), str)
                    or len(args["new_content"].encode("utf-8")) > 512 * 1024
                    or not isinstance(args.get("rationale", ""), str)
                    or len(args.get("rationale", "")) > 2000
                    or not isinstance(args.get("visual_intent", ""), str)
                    or len(args.get("visual_intent", "")) > 1000):
                raise srv.HTTPException(status_code=400, detail="invalid creator tool arguments")
            result = service.propose_edit(
                args["path"], args["new_content"], args.get("rationale", ""),
                args.get("visual_intent", ""),
            )
        elif tool == "session_validate":
            if args:
                raise srv.HTTPException(status_code=400, detail="invalid creator tool arguments")
            result = service.validate()
        elif tool == "session_decline":
            if set(args) != {"reason"} or not isinstance(args.get("reason"), str) or len(args["reason"]) > 2000:
                raise srv.HTTPException(status_code=400, detail="invalid creator tool arguments")
            from jarvis.skill_requests import update as update_skill_request
            update_skill_request(
                body.owner_id, body.request_id, state="draft_needs_attention",
                result_code="creator_declined",
            )
            result = {"ok": False, "declined": True, "reason": args["reason"]}
        else:
            raise srv.HTTPException(status_code=403, detail="tool is outside the creator capability")
        if not isinstance(result, dict):
            raise srv.HTTPException(status_code=502, detail="creator tool returned an invalid result")
        return result

    source_fields = (body.source_challenge, body.source_task_id,
                     body.source_tool_call_id, body.source_input_policy)
    if not any(value is not None for value in source_fields):
        return {"ok": True, "result": invoke()}
    if any(value is None for value in source_fields):
        raise srv.HTTPException(status_code=400, detail="invalid creator source binding")
    from jarvis.development_attestation import sign_tool_source
    from jarvis.development_sources import creator_context, dispatch_workspace_tool
    from jarvis.privacy_policy import (DataPolicy, issue_tool_result, make_tool_execution_scope,
                                      strictest, validate_tool_result)

    try:
        source_context = creator_context(service, state, run)
        source_scope = make_tool_execution_scope(
            body.developer_run_id, body.source_task_id, body.source_tool_call_id,
            tool, args, strictest(source_context.input_floor,
                                 DataPolicy(body.source_input_policy, "creator-caller-floor")),
        )
        classified = dispatch_workspace_tool(
            service, tool, args, execution_scope=source_scope, context=source_context, invoke=invoke,
        )
        # Do not hold the request lock across the workspace operation: a
        # concurrent cancellation must remain able to win before signing.
        current = srv._creator_internal_owner(body, request)
        current_run = srv._verify_developer_run(body)
        after_live = service.status()
        if (current.get("cancel_requested")
                or current.get("developer_run_id") != body.developer_run_id
                or current.get("creator_revision") != body.creator_revision
                or current.get("sandbox_job_id") != state.get("sandbox_job_id")
                or after_live.get("run_id") != state.get("sandbox_job_id")):
            raise srv.HTTPException(status_code=409, detail="creator source binding changed")
        after_context = creator_context(service, current, current_run)
        if after_context.as_metadata() != source_context.as_metadata():
            raise srv.HTTPException(status_code=409, detail="creator source binding changed")
        policy, content = validate_tool_result(source_scope, classified)
        classified = issue_tool_result(
            source_scope, content, strictest(policy, after_context.input_floor),
            classified.source_scope, classified.canonical_refs,
        )
        from jarvis.skill_requests import _paths
        import fcntl
        import stat

        _, lock_path = _paths(body.owner_id, body.request_id)
        descriptor = srv.os.open(lock_path, srv.os.O_RDWR | srv.os.O_CREAT | srv.os.O_NOFOLLOW | srv.os.O_CLOEXEC, 0o600)
        with srv.os.fdopen(descriptor, "a") as lock:
            metadata = srv.os.fstat(lock.fileno())
            if (not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != srv.os.getuid()
                    or stat.S_IMODE(metadata.st_mode) != 0o600 or metadata.st_nlink != 1):
                raise srv.HTTPException(status_code=409, detail="creator source binding changed")
            fcntl.flock(lock, fcntl.LOCK_EX)
            final_state = srv._creator_internal_owner(body, request)
            srv._verify_developer_run(body)
            if (final_state.get("cancel_requested")
                    or any(final_state.get(key) != current.get(key) for key in (
                        "bot_session_id", "developer_run_id", "creator_revision", "skill_id",
                        "sandbox_job_id", "sandbox_session_id", "sandbox_task_id", "source_commit",
                    ))):
                raise srv.HTTPException(status_code=409, detail="creator source binding changed")
            # The long workspace operation and source snapshot ran before
            # this lock. A cancellation/request replacement cannot race the
            # final durable check and receipt signature.
            receipt = sign_tool_source(source_scope, classified, context=source_context.as_metadata(),
                                       challenge=body.source_challenge)
        return {"ok": True, "source_receipt": receipt}
    except srv.HTTPException:
        raise
    except Exception:
        raise srv.HTTPException(status_code=409, detail="creator source receipt could not be verified") from None
