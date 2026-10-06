"""Sidecar admin API (upgrade plan §10 U1.5-G3).

Localhost-only FastAPI service backing the console's Git panel and the
self-development Edit mode. Every write endpoint goes through draft →
confirm → commit machinery (mcp_git.logic) or the sandboxed self-edit
service (jarvis.selfedit) — the panels are front ends, not bypasses.

This process is the SINGLE OWNER of the self-edit service and of every git
operation in the loop: the console panels (HTTP) and the mcp_selfedit skill
server (voice) are both thin clients of these endpoints, so no second
process ever runs git against the live repo.

Self-edit endpoints (plan §3/§3.5):
- GET  /api/selfedit/models           — planner registry (key presence only)
- POST /api/selfedit/stage    {goal, profile?, plan_path?} — G2
  (MORTIMER_SESSION_GAPS_AND_SELFEDIT_CONVERGENCE_PLAN.md): create a
  stateful staging record for a preview, returns {staging_id}. mcp_selfedit
  calls this on confirm=false so the confirm=true call can replay the
  EXACT goal rather than the model re-deriving it — the previous stateless
  form let goal/profile drift between the two calls and produced an
  invented "session expired" narrative (there was never a session to
  expire). TTL 10 minutes (SELFEDIT_STAGING_TTL_S).
- POST /api/selfedit/run      {staging_id} or {goal, profile?, run_id} — start an
  upgrade run ASYNC (background thread + GET /api/selfedit/run polling):
  planning takes minutes and voice turns cannot block. `staging_id`
  replays a /api/selfedit/stage record (preferred); the bare form is a
  compatibility fallback and requires a stable action ID for durable
  duplicate protection. Bare requests without run_id are refused.
- GET  /api/selfedit/run              — poll the current/last run job
- GET  /api/selfedit/status           — session state, proposals, validation
- POST /api/selfedit/validate         — run the validation gate
- POST /api/selfedit/submit           — commit/push/open PR (needs validation)
- POST /api/selfedit/revert           — drop the session, restore rollback tag

While a run is in progress, a second run and the mutating endpoints are
refused with a spoken-friendly error — ask for status instead.

There is deliberately no merge endpoint. Merging happens on GitHub only.

Memory endpoints (plan Phase 5e — visibility/correction surface):
- GET    /api/memory              — facts, observations (with promotion
  progress), running summary, capacity usage
- DELETE /api/memory/fact/{key}   — forget one fact ("forget that" via the
  console instead of by voice)
Both are thin pass-throughs over jarvis.memory, same convention as the git
endpoints above — no memory logic is duplicated here.

Run: scripts/run_admin.sh  (binds 127.0.0.1:7861)
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import sys
import threading
import time
import uuid
from contextvars import ContextVar, copy_context
from contextlib import closing
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field

from jarvis import graphs
from jarvis.auth import auth_enabled, service_headers
from jarvis.authmw import BearerAuthMiddleware
from jarvis.bind import BindRefused, resolve_bind_host, resolve_port
from jarvis import memory as memory_module
from jarvis.admin.reminder_notifier import ReminderNotifier
from jarvis.agents.upgrade_agent import (
    AppBuildAgent,
    UnknownModelProfileError,
    UpgradeAgent,
    available_models,
    load_model_registry,
    resolve_profile,
)
from jarvis.agents.workspace import AppWorkspace
from jarvis.council import config as council_config
from jarvis.council import council as council_mod
from jarvis.db import (
    claim_execution_action,
    get_conn,
    get_execution_action,
    now_iso,
    run_migrations,
    update_execution_action,
)
from jarvis.graphs import config as gcfg
from jarvis.graphs import render
from jarvis.model_preferences import (
    ModelPreferenceError,
    confirm_preference,
    list_preferences,
    stage_preference,
)
from jarvis.model_routing import (
    available_routes, describe_route_choice, load_access_config,
    model_profile_for_workload, ModelRouteError, resolve_policy,
)
from jarvis.model_budget import (
    ModelBudgetUnavailable, TaskBudget, begin_model_task_budget, remaining_seconds,
)
from jarvis.privacy_policy import DataPolicy
from jarvis import keyhealth
from jarvis.prompts import (
    PLAN_AUTHOR_PROMPT,
    PLAN_REVIEW_PROMPT,
    RESEARCH_PROMPT,
    RESEARCH_SYSTEM_PROMPT,
)
from jarvis.research import crawl as research_crawl
from jarvis.runlog import get_run, list_runs, parse_since
from jarvis.runlog.store import get_skill_events, list_skill_runs
from jarvis.tenant import current_user_id
from jarvis.selfedit.service import SelfEditService
from jarvis.vault import inject_env
from mcp_servers.mcp_apps.logic import validate_app_name
from mcp_servers.mcp_git import logic
from mcp_servers.mcp_repo import logic as repo_logic

logger = logging.getLogger(__name__)

# Credential vault (MORTIMER_CREDENTIAL_VAULT_PLAN.md S4, call site 2 of
# 3): the sidecar never calls load_settings, and UpgradeAgent reads its
# planner keys straight from os.environ — inject at import time, before
# any endpoint or agent run can look for a token.
inject_env()

REPO_ROOT = Path(__file__).resolve().parents[2]

app = FastAPI(title="jarvis-admin", docs_url=None, redoc_url=None, openapi_url=None)

# Middleware is wrapped in reverse registration order. Register auth first so
# CORS is outside it and can add headers to authenticated failures/preflights.
app.add_middleware(BearerAuthMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)




@app.middleware("http")
async def _log_5xx_responses(request: Request, call_next):
    """D17: every request returning 5xx is logged — this process is the
    sole owner of the self-edit service, so a silent 500 here is a self-
    edit failure with no trace of what request triggered it."""
    response = await call_next(request)
    if response.status_code >= 500:
        logger.warning(
            "admin_5xx method=%s path=%s status=%d",
            request.method, request.url.path, response.status_code,
        )
    return response


class MessageIn(BaseModel):
    message: str


class CommitDraftIn(BaseModel):
    """Retain the legacy request shape so old clients receive the explicit
    sandbox-required response instead of an unrelated schema error."""
    message: str
    paths: list[str] | None = None


class ActionIn(BaseModel):
    action_id: int


class GoalIn(BaseModel):
    goal: str = ""
    profile: str | None = None
    # MORTIMER_PLANNING_PATHWAY_PLAN.md P7 — an optional pre-written plan
    # (typically adopted via POST /api/plan/adopt) that UpgradeAgent.run()
    # injects as a system message before its edit loop begins.
    plan: str | None = None
    # Voice-path equivalent of `plan`: a repo path to a plan document the
    # sidecar reads ONCE, synchronously, at start (same read-and-refuse
    # pattern as plan_start's review_path — an unreadable plan must never
    # seed a run). Ignored when `plan` is set explicitly.
    plan_path: str | None = None
    # G2 — when set, replaces goal/profile/plan_path with the staged
    # record from POST /api/selfedit/stage; `goal` may be empty in that
    # case (it's optional above specifically to allow this).
    staging_id: str | None = None
    # MORTIMER_GRAPH_LAYER_PLAN.md GL9 — the delegating run (bare-form only;
    # the staged path reads it from the staging record). "" is normalised to None.
    run_id: str | None = None
    # SE3 — "open the session and let ME write it" (the developer, via
    # mcp_selfedit). Default False, which is today's behaviour exactly.
    #
    # This is an EXPLICIT flag rather than an inference from "no plan_path"
    # because this route has two callers with different needs. The native
    # app's Edit tab posts a bare {goal, profile, run_id} — no plan or
    # staging — and reads `started` to know a run began; it has no way to
    # author anything, so it needs the planner (C1/SE10). The request ID
    # lets the client reconcile a transport retry. The developer
    # sets author=true and writes the files itself. An older mcp_selfedit
    # build that does not send the flag gets the planner, the safe default.
    author: bool = False


class SelfEditStageIn(BaseModel):
    """G2 — the confirm=false half of the stateful staging handshake."""
    goal: str
    profile: str | None = None
    plan_path: str | None = None
    run_id: str | None = None      # GL9
    # 2026-09-07 (review F5): the files the edit will change, classified
    # by preflight instead of the paths the goal prose happens to mention.
    target_paths: list[str] | None = None


class ConveneIn(BaseModel):
    placement: str
    goal: str | None = None
    # D9/D10 wire-format completion (see jarvis/council/config.py's
    # module docstring): the console's per-tier membership picker
    # narrows which registry profiles are eligible, keyed by tier name
    # (economy/mid/frontier). Omitted/empty per tier falls back to that
    # tier's full registry membership.
    members: dict[str, list[str]] | None = None


class PlanStartIn(BaseModel):
    """MORTIMER_PLANNING_PATHWAY_PLAN.md P7."""
    goal: str
    mode: str  # "single" | "council"
    profile: str | None = None
    # council mode only: {"proposers": [...], "judges": [...]} — profile
    # names, not tier names (draft_candidates fans out the full registry
    # by default, unlike convene()'s tier ladder).
    members: dict[str, list[str]] | None = None
    # MORTIMER_PLAN_REVIEW_AND_DOCS_PLAN.md R1 — when set, this job is a
    # REVIEW of the repo document at this path instead of authoring a new
    # plan; empty (default) is today's authoring behavior, unchanged.
    review_path: str = ""
    run_id: str | None = None      # GL9


class PlanChooseIn(BaseModel):
    label: str


class PlanAdoptIn(BaseModel):
    path: str | None = None


class MemoryReviewResolveIn(BaseModel):
    """MORTIMER_MEMORY_AUTOCONSOLIDATION_PLAN.md A3. `action` is
    kind-dependent — see jarvis.memory_sweep.resolve_review's docstring
    for the valid set per review kind."""

    action: str
    rewrite_content: str | None = None


class ResearchStartIn(BaseModel):
    """MORTIMER_SITE_RESEARCH_AND_COMPARISON_PLAN.md R1/R2. `urls` is
    exactly the two URLs to compare — the schema exposes no crawl bounds
    (max_depth/limit/etc.) at all; those live only in config/research.yaml
    plus the hard cap in jarvis/research/crawl.py, per R2."""
    urls: list[str]
    focus: str = ""
    run_id: str | None = None


class ResearchSaveIn(BaseModel):
    path: str | None = None


class AdvisorySourceIn(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    owner_id: str
    bot_session_id: str
    caller_run_id: str
    caller_agent: Literal['developer', 'analyst']
    tool_name: str
    arguments: dict[str, Any]
    task_id: str
    tool_call_id: str
    challenge: str
    input_policy: Literal['approved_external', 'confidential', 'local_only']
    owner_scope_id: str | None = None
    child_scope_id: str | None = None
    preparation_id: str | None = None
    source_context: dict[str, str] | None = None


class SkillRequestIn(BaseModel):
    """Closed, versioned mutation surface for Skills workspace requests."""
    model_config = ConfigDict(extra="forbid")
    schema_version: int = 1
    operation: str
    request_id: str
    bot_session_id: str | None = None
    expected_catalog_revision: str
    skill_id: str
    skill_revision: str | None = None
    privacy_context: str
    task_brief: str | None = None
    example_ids: list[str] | None = None
    scope: str | None = None
    route_policy_ref: str | None = None
    budget: dict[str, int] | None = None
    review_artifact_ref: str | None = None
    candidate_digest: str | None = None
    job_id: str | None = None


class SkillRuntimeInventoryIn(BaseModel):
    """Bounded, content-free inventory reported by the authenticated bot."""

    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: int
    runtime_id: str = Field(min_length=36, max_length=36)
    owner_id: str = Field(min_length=1, max_length=64)
    active: bool
    complete: bool
    tools: list[Annotated[str, Field(max_length=128)]] = Field(max_length=256)


class SkillCreatorAssociationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    owner_id: str = Field(min_length=1, max_length=64)
    bot_session_id: str = Field(min_length=36, max_length=36)
    request_id: str = Field(min_length=36, max_length=36)
    developer_run_id: str = Field(min_length=36, max_length=36)
    creator_revision: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_authority: bool = False


class SkillCreatorToolIn(SkillCreatorAssociationIn):
    tool_name: str = Field(min_length=1, max_length=64)
    arguments: dict[str, Any] = Field(default_factory=dict)
    source_challenge: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    source_task_id: str | None = Field(default=None, min_length=1, max_length=256)
    source_tool_call_id: str | None = Field(default=None, min_length=1, max_length=256)
    source_input_policy: Literal["approved_external", "confidential", "local_only"] | None = None



class AppBuildGoalIn(BaseModel):
    """MORTIMER_MODEL_DISCIPLINE_AND_MAC_SHELL_PLAN.md D5. Same
    plan/plan_path shape as GoalIn — plan_path is read-and-refuse
    identical to selfedit's."""
    app: str
    goal: str
    profile: str | None = None
    plan: str | None = None
    plan_path: str | None = None
    run_id: str | None = None


class WorkspaceSourceAssociationIn(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    owner_id: str = Field(min_length=1, max_length=64)
    bot_session_id: str = Field(min_length=36, max_length=36)
    developer_run_id: str = Field(min_length=36, max_length=36)
    workspace_kind: Literal['selfedit', 'app-build']


class WorkspaceSourcePrepareIn(WorkspaceSourceAssociationIn):
    tool_name: str = Field(min_length=1, max_length=64)
    arguments: dict[str, Any] = Field(default_factory=dict)
    source_challenge: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_task_id: str = Field(min_length=1, max_length=256)
    source_tool_call_id: str = Field(min_length=1, max_length=256)
    source_input_policy: Literal["approved_external", "confidential", "local_only"]


class WorkspaceSourceToolIn(WorkspaceSourcePrepareIn):
    source_context: dict[str, str]
    source_preparation_id: str = Field(pattern=r"^[0-9a-f]{64}$")


class ModelRouteStageIn(BaseModel):
    workload: str
    profile: str
    route: str
    privacy: str | None = None


class ModelRouteConfirmIn(BaseModel):
    draft_id: str


# G2 (MORTIMER_SESSION_GAPS_AND_SELFEDIT_CONVERGENCE_PLAN.md) — stateful
# staging for the selfedit_start confirm=false/confirm=true handshake,
# mirroring the git `actions` draft→confirm-by-id pattern (jarvis/db.py's
# `actions` table) but kept in-process rather than in SQLite: like every
# other job slot on this page, staging state is sidecar-process state, not
# durable across a restart, and a restart mid-confirmation was never a
# case any of these slots handled either. Sole owner of the "did goal/
# profile drift between confirm=false and confirm=true" question that used
# to be answered by the model re-stating the goal from memory.
SELFEDIT_STAGING_TTL_S = 600.0  # 10 minutes
_staging_lock = threading.Lock()
_selfedit_stagings: dict[str, dict[str, Any]] = {}


def _prune_expired_stagings() -> None:
    """Drop stagings past TTL. Caller must hold _staging_lock."""
    now = time.time()
    expired = [
        sid for sid, rec in _selfedit_stagings.items()
        if now - rec["created_at"] > SELFEDIT_STAGING_TTL_S
    ]
    for sid in expired:
        del _selfedit_stagings[sid]


def _take_staging(requested: str) -> tuple[dict[str, Any] | None, str, list[str]]:
    """Pop the staging a confirm refers to.

    Exact id first. Otherwise, when exactly ONE staging is live, that one:
    the id travels developer → supervisor → user → supervisor → developer
    as relayed text, and on 2026-09-07 it arrived as 'stg-0d049db0947d'
    and as '43' — each bounced the user back to a fresh preview for a
    typo the sidecar could have resolved, since only one preview was ever
    live. With more than one live staging the caller refuses and names
    them; guessing between two approved previews is never done here.
    Takes _staging_lock itself. Returns (record | None, id_used,
    ids_still_live)."""
    with _staging_lock:
        _prune_expired_stagings()
        used = requested
        rec = _selfedit_stagings.pop(requested, None) if requested else None
        if rec is None and len(_selfedit_stagings) == 1:
            used, rec = _selfedit_stagings.popitem()
            logger.info("selfedit_run_staging_resolved")
        live = sorted(_selfedit_stagings)
    return rec, used, live


# Single self-edit session for the sidecar process (plan §3: one at a time).
_selfedit_service = SelfEditService()

# GC9 (gap-closure plan, 2026-09-04): the persistent reminder notifier --
# started here because the sidecar is the one always-on process that
# already talks to the reminders table (see /api/ambient below). Only
# ever sets notified_at, never delivered -- the bot's own RemindersWatcher
# semantics are untouched. Same four falsy spellings as
# jarvis/skills/registry.py's env_scoping_enabled().
_reminder_notifier = ReminderNotifier()
if os.environ.get("JARVIS_REMINDER_NOTIFICATIONS_ENABLED", "").strip().lower() not in (
    "0", "false", "no", "off",
):
    _reminder_notifier.start()

# Status spec T2.2 (fact 3.6): the sidecar answers /api/status/models, and
# key health verdicts live in memory in the process that probed — so this
# process probes too (once, on a daemon thread, never blocking startup).
# Honors JARVIS_KEY_HEALTH_ENABLED inside keyhealth.
keyhealth.start_background_probe()
# Status spec T3.3: and re-probes its bad keys every 10 minutes, so a key
# that was fixed stops reading as rejected (per-process singleton).
keyhealth.start_refresh_loop()

# Single-run gate: one upgrade job at a time, ever.
_run_lock = threading.Lock()
# The UpgradeAgent instance currently driving _run_job (None when idle) —
# held only so POST /api/selfedit/cancel can reach its cooperative
# cancel flag (the same reason _appbuild_workspace exists).
_run_agent_instance: Any = None
_SELFEDIT_STAGED_START_ACTION_SCOPE = "mcp-selfedit.staged_start"
_SELFEDIT_RUN_START_ACTION_SCOPE = "mcp-selfedit.run_start"
_SELFEDIT_PUBLISH_ACTION_SCOPE = "mcp-selfedit.publish"
_run_job: dict[str, Any] = {
    "state": "idle",  # idle | running | done | error | cancelled
    "cancel_requested": False,
    "goal": None,
    "profile": None,
    "summary": None,
    "run_id": None,
    "action_run_id": None,
    "action_scope": None,
    "started_at": None,
    "finished_at": None,
    # 2026-09-07 (review F6): "done" says the planner stopped; these say
    # whether a pull request exists. Set from the agent's result, never
    # from its prose.
    "submitted": False,
    "pr_url": None,
}

# SE11 (MORTIMER_SELFEDIT_AUTHORING_PLAN.md) — the authoring kill switch,
# read in exactly ONE place. Off restores today's behaviour exactly:
# confirm=true launches the Upgrade Agent for every staging and the three
# authoring routes refuse with a named reason. Same four falsy spellings as
# jarvis/skills/registry.py's env_scoping_enabled().
SELFEDIT_AUTHORING_ENABLED_ENV = "JARVIS_SELFEDIT_AUTHORING_ENABLED"


def authoring_enabled() -> bool:
    """True unless JARVIS_SELFEDIT_AUTHORING_ENABLED is an explicit false."""
    return os.environ.get(SELFEDIT_AUTHORING_ENABLED_ENV, "").strip().lower() not in (
        "0", "false", "no", "off",
    )


_AUTHORING_OFF = {
    "ok": False,
    "error": "developer authoring is disabled "
             "(JARVIS_SELFEDIT_AUTHORING_ENABLED=false) — the planner path is active",
}

# SE4 — the finish job: validate, and if every check passes, submit. It is a
# JOB and not a synchronous route because jarvis/skills/registry.py's
# CALL_TIMEOUT is 30 s and the pytest gate alone runs for ~330 s: a
# developer-driven validate could never have completed as a tool call.
# Process state, reset on restart, exactly like _run_job.
_finish_lock = threading.Lock()
_finish_job: dict[str, Any] = {
    "cancel_requested": False,
    "state": "idle",  # idle | validating | submitting | done | failed | error | cancelled
    "checks": None,
    "pr_url": None,
    "notice": None,
    # W8 — the human-only files this PR only PROPOSES, and the one command
    # Larry runs once he approves (None when the PR proposes nothing).
    "human_only": None,
    "apply_command": None,
    "run_id": None,
    "action_run_id": None,
    "started_at": None,
    "finished_at": None,
}

# VM preparation outlives the voice client's HTTP deadline. Keep the start
# request short and expose progress; Session persists the underlying task.
_opening_lock = threading.Lock()
_opening_job: dict[str, Any] = {
    "state": "idle", "cancel_requested": False,
    "action_run_id": None, "action_scope": None,
}


def _update_staged_selfedit_claim(
    action_run_id: str | None, status: str,
    action_scope: str = _SELFEDIT_STAGED_START_ACTION_SCOPE,
) -> None:
    if not action_run_id:
        return
    try:
        update_execution_action(
            action_scope, action_run_id, status,
        )
    except Exception as exc:  # action outcome reporting must not break work
        logger.warning("selfedit_start_claim_update_failed error_type=%s", type(exc).__name__)


def _prior_staged_selfedit_action(
    action_run_id: str,
    action_scope: str = _SELFEDIT_STAGED_START_ACTION_SCOPE,
) -> dict[str, Any] | None:
    try:
        prior = get_execution_action(
            action_scope, action_run_id,
        )
    except Exception as exc:
        logger.warning("selfedit_start_claim_read_failed error_type=%s", type(exc).__name__)
        return {
            "ok": False,
            "error": "could not verify whether this self-edit already started; no retry was launched",
            "outcome": "unknown", "action_run_id": action_run_id,
        }
    if prior is None:
        return None
    with _run_lock:
        same_run = (
            _run_job.get("action_run_id") == action_run_id
            and _run_job.get("action_scope", _SELFEDIT_STAGED_START_ACTION_SCOPE)
            == action_scope
        )
        state = _run_job.get("state") if same_run else None
    with _opening_lock:
        same_opening = (
            _opening_job.get("action_run_id") == action_run_id
            and _opening_job.get("action_scope", _SELFEDIT_STAGED_START_ACTION_SCOPE)
            == action_scope
        )
        if same_opening:
            state = _opening_job.get("state")
    if not same_run and not same_opening and prior.get("status") in {
        "claimed", "running", "awaiting_choice",
    }:
        state = "unknown"
    return {
        "ok": True, "started": False, "duplicate": True,
        "state": state or prior.get("status", "unknown"),
        "action_run_id": action_run_id,
        "summary": (
            "This self-edit start was already claimed; no new job was started. "
            "Check selfedit_status with this action_run_id before considering any retry."
        ),
    }


def _prior_selfedit_publish(action_run_id: str) -> dict[str, Any] | None:
    try:
        prior = get_execution_action(_SELFEDIT_PUBLISH_ACTION_SCOPE, action_run_id)
    except Exception as exc:
        logger.warning("selfedit_publish_claim_read_failed error_type=%s", type(exc).__name__)
        return {
            "ok": False,
            "error": "could not verify whether this sandbox session was already submitted; no retry was launched",
            "outcome": "unknown", "action_run_id": action_run_id,
        }
    if prior is None:
        return None
    with _finish_lock:
        same_finish = (
            _finish_job.get("action_run_id") == action_run_id
            and _finish_job.get("state") != "idle"
        )
        state = _finish_job.get("state") if same_finish else None
        finish_url = _finish_job.get("pr_url") if same_finish else None
    publication = {}
    if not same_finish or state not in {"validating", "submitting"}:
        try:
            session = _selfedit_service.status()
            if session.get("id") == action_run_id:
                publication = session.get("publication") or {}
                finish_url = finish_url or publication.get("url") or session.get("pr_url")
        except Exception as exc:
            logger.warning("selfedit_publish_status_read_failed error_type=%s", type(exc).__name__)
    if finish_url:
        state = "completed"
        try:
            update_execution_action(
                _SELFEDIT_PUBLISH_ACTION_SCOPE, action_run_id, "completed",
            )
        except Exception as exc:
            logger.warning("selfedit_publish_claim_update_failed error_type=%s", type(exc).__name__)
    if not same_finish and prior.get("status") in {"claimed", "running", "awaiting_choice"}:
        if not finish_url:
            state = "unknown"
    if prior.get("status") == "completed" and not finish_url and not same_finish:
        # The durable claim records completion but intentionally carries no
        # publication payload. If the sandbox cannot confirm it now, do not
        # turn a missing result into either success or a retry.
        state = "unknown"
    result = {
        "ok": True, "started": False, "duplicate": True,
        "state": state or prior.get("status", "unknown"),
        "action_run_id": action_run_id,
        "summary": (
            "Submission for this sandbox session was already claimed; no new publication was started. "
            "Check selfedit_status with this action_run_id before any retry."
        ),
    }
    if finish_url:
        result["pr_url"] = finish_url
    return result


def _open_authoring(service, goal, run_id, target_paths, job):
    try:
        with _opening_lock:
            if job.get("cancel_requested"):
                return
        if job.get("resume_session_id"):
            opened = service.resume(job["resume_session_id"])
            if not opened.get("ok"):
                with _opening_lock:
                    job.update(state="error", error=opened.get("error"))
                return
        else:
            _cleanup_existing_workspace(service, goal)
            if not service.branch:
                opened = service.start_session(goal, run_id=run_id)
                if not opened.get("ok"):
                    with _opening_lock:
                        job.update(state="error", error=opened.get("error"))
                    return
        state = service.status()
        if state.get("ready") is False:
            resumed = service.resume(state.get("id"))
            if not resumed.get("ok"):
                with _opening_lock:
                    job.update(state="error", error=resumed.get("error"))
                return
            state = service.status()
        result = {"ok": True, "started": False, "session": {
            "branch": service.branch, "goal": goal, "target_paths": target_paths,
            "run_id": run_id, "worktree": None,
            "sandbox_task": state.get("task"), "session_id": state.get("id")}}
        with _opening_lock:
            cancelled = job.get("cancel_requested", False)
            if not cancelled:
                job.update(state="ready", result=result)
        if cancelled:
            service.cancel()
    except Exception as exc:
        logger.warning("sandbox_authoring_setup_failed error_type=%s",
                       type(exc).__name__)
        with _opening_lock:
            job.update(state="error", error="Sandbox setup failed; inspect the saved session before retrying.")
    finally:
        with _opening_lock:
            if job.get("cancel_requested"):
                job["state"] = "cancelled"
            job["finished_at"] = time.time()
            claim_status = "completed" if job.get("state") == "ready" else "failed"
        _update_staged_selfedit_claim(
            job.get("action_run_id"), claim_status,
            job.get("action_scope", _SELFEDIT_STAGED_START_ACTION_SCOPE),
        )


def _begin_authoring(
    goal, run_id, target_paths, *, resume_session_id=None,
    action_run_id: str | None = None,
    action_scope: str = _SELFEDIT_STAGED_START_ACTION_SCOPE,
):
    global _opening_job
    duplicate = False
    with _run_lock, _finish_lock, _opening_lock:
        if (_run_job["state"] == "running" or _finish_job["state"] in {"validating", "submitting"}
                or _opening_job["state"] == "starting"):
            return {"ok": False, "error": "an upgrade run is already in progress — ask for status instead"}
        if action_run_id:
            try:
                claimed = claim_execution_action(
                    action_scope, action_run_id,
                )
            except Exception as exc:
                logger.warning("selfedit_start_claim_write_failed error_type=%s", type(exc).__name__)
                return {"ok": False, "error": "could not safely record this self-edit; no session was opened"}
            if not claimed:
                duplicate = True
        if not duplicate:
            job = dict(state="starting", goal=goal, run_id=run_id,
                target_paths=target_paths, resume_session_id=resume_session_id,
                cancel_requested=False, started_at=time.time(),
                action_run_id=action_run_id, action_scope=action_scope)
            _opening_job = job
    if duplicate:
        return _prior_staged_selfedit_action(action_run_id, action_scope) or {
            "ok": False, "error": "the self-edit claim could not be reconciled; no session was opened",
        }
    worker = threading.Thread(target=_source_worker_target(_open_authoring),
        args=(_selfedit_service, goal, run_id, target_paths, job), daemon=True)
    try:
        worker.start()
    except Exception as exc:
        logger.warning("selfedit_authoring_thread_start_failed error_type=%s", type(exc).__name__)
        with _opening_lock:
            job.update(state="error", error="Sandbox setup worker could not be started.",
                       finished_at=time.time())
        _update_staged_selfedit_claim(action_run_id, "failed", action_scope)
        return {"ok": False, "error": "Sandbox setup worker could not be started."}
    # An already-open session may finish immediately. A fresh VM never holds
    # this request open for the duration of its preparation.
    worker.join(timeout=0.05)
    with _opening_lock:
        if job["state"] == "ready":
            return {**job["result"], "action_run_id": action_run_id}
        setup_failed = job["state"] == "error"
        setup_error = job.get("error")
    if setup_failed:
        # The worker records its terminal state before its finally block
        # settles the durable claim. If the request observes that small gap,
        # settle it here before returning a failure to the caller.
        _update_staged_selfedit_claim(action_run_id, "failed", action_scope)
        return {"ok": False, "error": setup_error}
    return {
        "ok": True, "started": True, "opening": True, "state": "starting",
        "action_run_id": action_run_id,
    }

def _prepare_file_access():
    """Start only VM warmup; the caller must retry its read or edit explicitly."""
    with _opening_lock:
        opening = _opening_job["state"] == "starting"
    state = _selfedit_service.status()
    if not opening and state.get("active") and state.get("ready") is False:
        if _busy():
            return {"ok": False, "error": "Sandbox work is in progress; wait before reading or editing files."}
        result = _begin_authoring(state.get("goal", ""), state.get("run_id"), [],
                                  resume_session_id=state["id"])
        if not result.get("ok"):
            return result
        # Return a pending response even if this warmup finished immediately:
        # no file operation was executed by the background worker.
        opening = True
    if opening:
        return {"ok": False, "pending": True, "retryable": True, "opening": True,
                "error": "The sandbox workspace is reopening. Retry this file request once self-edit status reports it ready; no edit was queued."}
    return None


# MORTIMER_LLM_COUNCIL_V2_PLAN.md V5 — the council's own async-job slot,
# same shape/pattern as _run_job/_run_lock above (one council round at a
# time, ever). POST /api/council/convene and the E3 half of POST
# /api/selfedit/reject both settle into this one slot; GET /api/council/job
# is the polling target.
_council_lock = threading.Lock()
_council_job: dict[str, Any] = {
    "state": "idle",   # idle | running | done | error
    "trigger": None,    # 'manual' | 'E3'
    "goal": None,
    "round_id": None,
    "winner": None,     # {"profile": ..., "content": ...} | None
    "winner_mean": None,
    "select_reason": None,
    "error": None,
    "started_at": None,
    "finished_at": None,
}

# MORTIMER_PLANNING_PATHWAY_PLAN.md P7 — a third async-job slot, same
# shape/pattern as _run_job/_council_job above (one planning job at a
# time, ever). GET /api/plan/job is the polling target.
_plan_lock = threading.Lock()
_PLAN_START_ACTION_SCOPE = "mcp-selfedit.plan_start"
_plan_job: dict[str, Any] = {
    "state": "idle",   # idle | running | awaiting_choice | done | error
    "mode": None,       # "single" | "council"
    "goal": None,
    "profile": None,    # single mode: the resolved author profile name
    "round_id": None,   # council mode
    "candidates": None,  # council mode: [{"label", "profile", "content",
                         #   "advisory_mean": float | None}, ...]
    "plan": None,        # the final chosen/authored plan text
    "author": None,      # profile name of the chosen/single author
    "error": None, "started_at": None, "finished_at": None,
    # MORTIMER_PLAN_REVIEW_AND_DOCS_PLAN.md R1 — set (repo-relative path)
    # for a review job, None for an authoring job.
    "review_path": None,
    # GL9 supplies the owning SubAgent run identity. It remains stable across
    # provider tool-call IDs, allowing /api/plan/start to reject a replay.
    "run_id": None,
}


def _update_plan_start_claim(run_id: str | None, status: str) -> None:
    """Best-effort status for the content-free plan-start claim."""
    if not run_id:
        return
    try:
        update_execution_action(_PLAN_START_ACTION_SCOPE, run_id, status)
    except Exception as exc:  # the accepted result must not be lost to telemetry
        logger.warning("plan_start_claim_update_failed error_type=%s", type(exc).__name__)

# MORTIMER_MODEL_DISCIPLINE_AND_MAC_SHELL_PLAN.md D5 — a fourth async-job
# slot, same shape/pattern as _run_job/_plan_job/_council_job above. Unlike
# _selfedit_service (one fixed Mortimer-repo session), the AppWorkspace is
# constructed fresh per app-build job (the app name varies), so there is
# no persistent module-level workspace — _appbuild_workspace holds the
# CURRENT job's workspace only, for the status/submit/cancel endpoints to
# reach. One app build at a time (one slot), and an app build does not
# block self-edit jobs — separate slots, separate locks.
_appbuild_lock = threading.Lock()
_APPBUILD_START_ACTION_SCOPE = "mcp-apps.app_build_start"
_APPBUILD_SUBMIT_ACTION_SCOPE = "mcp-apps.app_build_submit"
_appbuild_workspace: AppWorkspace | None = None
_appbuild_agent_instance: AppBuildAgent | None = None
_appbuild_job: dict[str, Any] = {
    "state": "idle",  # idle | running | done | error | cancelled
    "cancel_requested": False,
    "app": None,
    "goal": None,
    "profile": None,
    "summary": None,
    "started_at": None,
    "finished_at": None,
}


# MORTIMER_SITE_RESEARCH_AND_COMPARISON_PLAN.md R1 — a fifth async-job
# slot, same background-thread-plus-polling shape as _run_job/_plan_job/
# _council_job/_appbuild_job. R10 — the kill switch is checked ONCE, at
# the top of research_start below.
RESEARCH_ENABLED_ENV = "JARVIS_RESEARCH_ENABLED"
RESEARCH_DISABLED_MESSAGE = "site research is turned off"

_research_lock = threading.Lock()
_RESEARCH_START_ACTION_SCOPE = "mcp-web.research_compare_start"
_research_job: dict[str, Any] = {
    "state": "idle",  # idle | running | done | error
    "urls": None,
    "focus": None,
    "sites": None,       # [{"url","ok","page_count","credits","error","error_kind"}, ...]
    "comparison": None,  # the model's markdown review text
    "model": None,
    "credits_used": None,
    "error": None,
    "started_at": None,
    "finished_at": None,
    "saved_path": None,
    "save_error": None,
    "run_id": None,
}


def _update_research_start_claim(run_id: str | None, status: str) -> None:
    if not run_id:
        return
    try:
        update_execution_action(_RESEARCH_START_ACTION_SCOPE, run_id, status)
    except Exception as exc:
        logger.warning("research_start_claim_update_failed error_type=%s", type(exc).__name__)


def _research_duplicate(
    run_id: str, prior: dict[str, Any], current_job: dict[str, Any] | None = None,
) -> dict[str, Any]:
    current_job = current_job or {}
    same_job = current_job.get("run_id") == run_id
    state = current_job.get("state") if same_job else None
    if not state:
        state = prior.get("status", "unknown")
        if state in {"claimed", "running", "awaiting_choice"}:
            state = "unknown"
    state = {"completed": "done", "failed": "error"}.get(state, state)
    return {
        "ok": True, "started": False, "duplicate": True,
        "state": state, "action_run_id": run_id,
        "summary": (
            "This research comparison was already claimed; no second crawl was started. "
            "Check research_status with this action_run_id before considering a retry."
        ),
    }


def _research_enabled() -> bool:
    return os.environ.get(RESEARCH_ENABLED_ENV, "").strip().lower() not in ("false", "0", "no")


def _research_busy() -> bool:
    with _research_lock:
        return _research_job["state"] == "running"


_advisory_transport_context = ContextVar('advisory_transport_context', default=None)
_advisory_job_guards = {}


def _advisory_slot(kind):
    return (_plan_lock, _plan_job) if kind == 'planning' else (_research_lock, _research_job)


def _advisory_new_guard(kind, run_id, cancel_event=None):
    lock, slot = _advisory_slot(kind)
    source = _advisory_transport_context.get()
    event = source.cancel_event if source is not None else (cancel_event or threading.Event())
    with lock:
        guard = {'run_id': slot.get('run_id'), 'event': event, 'source': source}
        if slot.get('run_id') not in {None, run_id}:
            event.set()
        else:
            _advisory_job_guards[kind] = guard
        return guard


def _advisory_publish(kind, guard, values, run_id, *, claim_status, policy=None, failure=False):
    lock, slot = _advisory_slot(kind)
    with lock:
        if (_advisory_job_guards.get(kind) is not guard or slot.get('run_id') != guard['run_id']
                or (guard['event'].is_set() and not failure)):
            return False
        source = guard['source']
        if source is not None:
            from jarvis.advisory_sources import check_advisory_source, record_advisory_job
            try:
                check_advisory_source(source, slot, allow_cancelled=failure)
            except ModelRouteError:
                return False
        slot.update(values)
        if source is not None and not guard['event'].is_set():
            record_advisory_job(source, slot, policy=policy)
        updater = _update_plan_start_claim if kind == 'planning' else _update_research_start_claim
        updater(run_id, claim_status)
        return True


def _advisory_worker_kwargs():
    source = _advisory_transport_context.get()
    return {} if source is None else {'parent_budget': source.parent_budget,
        'data_policy': source.input_floor, 'cancel_event': source.cancel_event}


def _activate_advisory(slot):
    source = _advisory_transport_context.get()
    if source is not None:
        from jarvis.advisory_sources import activate_advisory_source
        activate_advisory_source(source, slot)


def _advisory_context_for_job(kind, slot):
    if os.environ.get('JARVIS_MODEL_ROUTING_ENABLED') != '1':
        return None
    from jarvis.advisory_sources import manual_advisory_source, verify_advisory_job
    try:
        source = _advisory_transport_context.get()
        if source is None:
            source = manual_advisory_source(kind, slot, current_user_id())
        if source is not None:
            verify_advisory_job(source, slot)
        return source
    except ModelRouteError:
        raise HTTPException(status_code=409, detail='advisory source owner changed') from None


def _start_advisory_thread(target, *, args=(), kwargs=None, started_at=None) -> None:
    """Keep the authenticated host context in council/planning workers."""
    host_kwargs = dict(kwargs or {})
    host_kwargs.update(_advisory_worker_kwargs())
    kind = ('planning' if target in {_run_plan_single, _run_plan_council} else
            'research' if target is _run_research_job else None)
    if kind is not None and (os.environ.get('JARVIS_MODEL_ROUTING_ENABLED') == '1'
                             or _advisory_transport_context.get() is not None):
        guard = _advisory_new_guard(kind, args[-1], host_kwargs.get('cancel_event'))
        host_kwargs.update(cancel_event=guard['event'], job_guard=guard)
    if os.environ.get("JARVIS_MODEL_ROUTING_ENABLED") == "1":
        host_kwargs["started_at"] = time.time() if started_at is None else started_at
    threading.Thread(target=copy_context().run, args=(target, *args),
                     kwargs=host_kwargs, daemon=True).start()


def _advisory_owner(
    workload: str, context: dict[str, Any], run_id: str | None, *,
    parent_budget: TaskBudget | None, data_policy: DataPolicy | None,
    cancel_event: threading.Event | None, started_at: float,
) -> tuple[TaskBudget | None, DataPolicy | None]:
    if os.environ.get("JARVIS_MODEL_ROUTING_ENABLED") != "1":
        if parent_budget is not None:
            raise ModelBudgetUnavailable("budget_unsupported_route")
        return None, None
    # Raw API dictionaries and returned crawl JSON cannot approve a source.
    policy = council_mod._host_policy(
        context, workload, DataPolicy() if data_policy is None else data_policy,
    )
    source = _advisory_transport_context.get()
    if source is not None:
        from jarvis.advisory_sources import check_advisory_source
        from jarvis.privacy_policy import strictest
        _, slot = _advisory_slot(source.as_metadata()['advisory_kind'])
        policy = strictest(policy, check_advisory_source(source, slot))
    if parent_budget is not None:
        if type(parent_budget) is not TaskBudget:
            raise ModelBudgetUnavailable("budget_scope_mismatch")
        owner = parent_budget
    else:
        owner = begin_model_task_budget(
            workload, run_id or f"admin:{uuid.uuid4().hex}",
            resolve_policy(workload, include_preferences=False).limits,
            started_at=started_at,
        )
    _check_advisory_owner(owner, cancel_event)
    return owner, policy


def _check_advisory_owner(owner: TaskBudget | None, cancel_event: threading.Event | None) -> None:
    if cancel_event is not None:
        if type(cancel_event) is not threading.Event:
            raise ModelBudgetUnavailable("budget_scope_mismatch")
        if cancel_event.is_set():
            raise asyncio.CancelledError
    if owner is not None and remaining_seconds(owner) <= 0:
        raise ModelBudgetUnavailable("budget_deadline_exhausted")


def _advisory_failure(exc: BaseException, legacy_prefix: str) -> str:
    if isinstance(exc, ModelBudgetUnavailable):
        return exc.code
    if isinstance(exc, asyncio.CancelledError):
        return "budget_cancelled"
    if isinstance(exc, ModelRouteError):
        return "model_policy_refused"
    return f"{legacy_prefix} ({type(exc).__name__})"


def _run_research_job(
    urls: list[str], focus: str, run_id: str, *,
    parent_budget: TaskBudget | None = None, data_policy: DataPolicy | None = None,
    cancel_event: threading.Event | None = None, started_at: float | None = None, job_guard=None,
) -> None:
    """Background thread target (R1): crawl both sites (sync, one at a
    time — Tavily's own crawl is already parallel internally, and two
    concurrent 120s calls would only double the memory footprint for no
    real time saving), assemble the digest in CODE, then one model call
    for the prose comparison (R4/R5). Settles _research_job on every exit
    path, mirroring every other job target on this page."""
    started_at = time.time() if started_at is None else started_at
    guard = job_guard or _advisory_new_guard('research', run_id, cancel_event)
    cancel_event = guard['event']
    policy = data_policy
    try:
        owner, policy = _advisory_owner(
            "planning", {}, run_id, parent_budget=parent_budget,
            data_policy=data_policy, cancel_event=cancel_event, started_at=started_at,
        )
        cfg = research_crawl.load_research_config()
        api_key = os.environ.get(research_crawl.TAVILY_API_KEY_ENV)
        if not api_key:
            _advisory_publish('research', guard, dict(
                    state="error",
                    error="TAVILY_API_KEY is not configured",
                    finished_at=time.time(),
                ), run_id, claim_status='failed', failure=True)
            return
        client = research_crawl.TavilyCrawlClient(timeout=float(cfg.get("timeout_s", 120)) + 10.0)
        results = []
        for url in urls:
            _check_advisory_owner(owner, cancel_event)
            results.append(research_crawl.crawl_site(client, url, focus, api_key, cfg))
            if owner is not None:
                from jarvis.privacy_policy import strictest
                policy = strictest(policy, research_crawl.crawl_source_policy(results[-1]))
                if guard['source'] is not None:
                    from jarvis.advisory_sources import record_advisory_job
                    record_advisory_job(guard['source'], _research_job, policy=policy)
            _check_advisory_owner(owner, cancel_event)
        # R9 — per-site failure, never all-or-nothing: only when EVERY
        # site failed does this become a terminal error.
        if not any(r.get("ok") for r in results):
            _advisory_publish('research', guard, dict(
                    state="error",
                    sites=[_site_summary(r) for r in results],
                    error="both sites failed to crawl — " + "; ".join(
                        f"{r['url']}: {r.get('error', 'unknown')}" for r in results
                    ),
                    finished_at=time.time(),
                ), run_id, claim_status='failed', policy=policy, failure=True)
            return

        digests = research_crawl.assemble_digests(results[0], results[1])
        site_a = results[0].get("url", urls[0] if urls else "")
        site_b = results[1].get("url", urls[1] if len(urls) > 1 else "")
        user_content = RESEARCH_PROMPT.format(
            focus=(focus or research_crawl.DEFAULT_FOCUS),
            site_a=site_a, site_b=site_b, digests=digests,
        )
        registry = load_model_registry()
        profile_name = os.environ.get("JARVIS_PLANNING_PROFILE") or registry.get("default")
        try:
            profile = resolve_profile(registry, profile_name)
        except UnknownModelProfileError:
            _advisory_publish('research', guard, dict(
                    state="error",
                    sites=[_site_summary(r) for r in results],
                    error="no usable planner model",
                    finished_at=time.time(),
                ), run_id, claim_status='failed', policy=policy, failure=True)
            return
        call_kwargs = {}
        if owner is not None:
            policy = council_mod._host_policy({}, "council", policy)
            execution = council_mod._child_execution(
                owner, "council", policy, cancel_event, started_at=started_at,
                sponsored=parent_budget is not None,
            )
            call_kwargs = {"execution": execution, "data_policy": policy}
        content, _usage = asyncio.run(council_mod._call_profile(
            profile, RESEARCH_SYSTEM_PROMPT, user_content,
            council_config.PLANNING_MEMBER_TIMEOUT_S, rung="research", **call_kwargs,
        ))
        _check_advisory_owner(owner, cancel_event)
        _advisory_publish('research', guard, dict(
                state="done",
                sites=[_site_summary(r) for r in results],
                comparison=content,
                model=profile["name"],
                credits_used=research_crawl.total_credits(*results),
                finished_at=time.time(),
            ), run_id, claim_status='completed', policy=policy)
        logger.info("research_state_transition state=done site_count=%d", len(urls))
    except (Exception, asyncio.CancelledError) as exc:  # every exit settles the job
        logger.warning("research_job_failed error_type=%s", type(exc).__name__)
        _advisory_publish('research', guard, dict(
                state="error",
                error=_advisory_failure(exc, "research job failed"),
                finished_at=time.time(),
            ), run_id, claim_status='failed', policy=policy, failure=True)


def _site_summary(result: dict[str, Any]) -> dict[str, Any]:
    """R8 — the job-status view of one site's crawl: enough to report
    credits/page counts/failures without echoing full page content back
    through the polling endpoint (the comparison text is what carries the
    substance)."""
    if result.get("ok"):
        return {
            "url": result.get("url"), "ok": True,
            "page_count": result.get("page_count"),
            "credits": result.get("credits"),
        }
    return {
        "url": result.get("url"), "ok": False,
        "error": result.get("error"), "error_kind": result.get("error_kind"),
    }


def _make_agent(service: SelfEditService, profile: str | None,
                run_id: str | None = None) -> UpgradeAgent:
    """Construct the planner (seam for tests). run_id: GL9 (contract G2)."""
    return UpgradeAgent(service, profile=profile, run_id=run_id)


# Only the authenticated source adapter binds this host capability. No
# Pydantic field or provider-supplied privacy label can construct it.
_workspace_start_policy = ContextVar('workspace_start_policy', default=None)
_workspace_lifecycle_context = ContextVar('workspace_lifecycle_context', default=None)
_workspace_cleanup_context = ContextVar('workspace_cleanup_context', default=None)
_appbuild_parent_id = ContextVar('appbuild_parent_id', default=None)


def _source_plan_observed(path, result):
    source = _workspace_start_policy.get()
    if source is not None:
        from jarvis.development_sources import host_plan_policy
        from jarvis.privacy_policy import strictest
        source['plan_policy'] = strictest(source['data_policy'], host_plan_policy(_selfedit_service, path, result))
        if 'run' in source:
            from jarvis.development_sources import retain_workspace_floor
            retain_workspace_floor(source['run'], source['plan_policy'])


def _source_worker_kwargs():
    source = _workspace_start_policy.get()
    return {key: value for key, value in source.items() if key in {'data_policy', 'plan_policy'}} if source is not None else {}


def _source_worker_target(target):
    from sandbox.workspace import _source_session
    if (_workspace_start_policy.get() is None and _workspace_lifecycle_context.get() is None
            and _workspace_cleanup_context.get() is None and _source_session.get() is None):
        return target
    from functools import partial
    return partial(copy_context().run, target)


def _lifecycle_service(service, *, terminal=False):
    context = _workspace_lifecycle_context.get()
    if context is None:
        return service
    from jarvis.development_sources import _live, refresh_workspace_floor
    if service is not context._service:
        raise RuntimeError('workspace_source_changed')
    _live(service, context.as_metadata()['developer_run_id'], context, terminal=terminal)
    refresh_workspace_floor(context)
    return service


def _cleanup_existing_workspace(service, goal):
    """Stale cleanup uses its own host proof, never the new start's actor."""
    context = _workspace_cleanup_context.get()
    if _workspace_start_policy.get() is None:
        if service.branch and (service.goal or '') != goal:
            service.revert()
        return
    if context is None:
        runtime = service._runtime()
        record = runtime.workspaces / (runtime._key(service._repository(), service._kind) + '.json')
        try:
            record.lstat()
        except FileNotFoundError:
            return
        raise RuntimeError('workspace_source_changed')
    if service is not context._service:
        raise RuntimeError('workspace_source_changed')
    from jarvis.development_sources import _live
    from sandbox.workspace import pin_source_session
    with pin_source_session(service, context._session, context._identity):
        _live(service, context.as_metadata()['developer_run_id'], context, terminal=True)
        if service.branch and (service.goal or '') != goal:
            service.revert()


def _run_finish() -> None:
    """SE4 — background thread target: validate, and on green, submit.

    Auto-submit is not a new decision: it is the confirmation the user
    already gave at the preview, whose sentence says the run will validate
    and open the pull request if every check passes. On a failure the
    session stays OPEN with the check output, so repair is the developer on
    the next turn (read → write → finish again) rather than a dead end."""
    action_run_id = None
    publication_dispatched = False
    claimed = False
    try:
        service = _lifecycle_service(_selfedit_service)
        with _finish_lock:
            if _finish_job.get("cancel_requested"):
                _finish_job.update(state="cancelled", finished_at=time.time())
                return
            action_run_id = _finish_job.get("action_run_id")
        result = service.validate()
        with _finish_lock:
            _finish_job["checks"] = result.get("checks")
            if _finish_job.get("cancel_requested"):
                _finish_job.update(state="cancelled", finished_at=time.time())
                return
        if not result.get("ok"):
            with _finish_lock:
                _finish_job.update(state="failed", finished_at=time.time())
                run_id = _finish_job["run_id"]
            logger.info("selfedit_state_transition state=finish_failed run_id=%s", run_id)
            return
        if not action_run_id:
            with _finish_lock:
                _finish_job.update(
                    state="error", notice="Sandbox session identity is unavailable; no pull request was submitted.",
                    finished_at=time.time(),
                )
            return
        try:
            claimed = claim_execution_action(
                _SELFEDIT_PUBLISH_ACTION_SCOPE, action_run_id,
            )
        except Exception as exc:
            logger.warning("selfedit_publish_claim_write_failed error_type=%s", type(exc).__name__)
            with _finish_lock:
                _finish_job.update(
                    state="error", notice="Submission could not be safely recorded; no pull request was submitted.",
                    finished_at=time.time(),
                )
            return
        if not claimed:
            prior = _prior_selfedit_publish(action_run_id)
            current = _lifecycle_service(service, terminal=True).status()
            publication = current.get("publication") or {}
            with _finish_lock:
                if prior and prior.get("state") == "completed" and publication.get("url"):
                    _finish_job.update(
                        state="done", pr_url=publication.get("url"),
                        finished_at=time.time(),
                    )
                else:
                    _finish_job.update(
                        state="unknown", notice="Submission was already claimed; inspect the saved publication state before retrying.",
                        finished_at=time.time(),
                    )
            return
        try:
            update_execution_action(
                _SELFEDIT_PUBLISH_ACTION_SCOPE, action_run_id, "running",
            )
        except Exception as exc:
            logger.warning("selfedit_publish_claim_update_failed error_type=%s", type(exc).__name__)
        with _finish_lock:
            if _finish_job.get("cancel_requested"):
                _finish_job.update(state="cancelled", finished_at=time.time())
                try:
                    update_execution_action(
                        _SELFEDIT_PUBLISH_ACTION_SCOPE, action_run_id, "failed",
                    )
                except Exception as exc:
                    logger.warning("selfedit_publish_claim_update_failed error_type=%s", type(exc).__name__)
                return
            _finish_job["state"] = "submitting"
        publication_dispatched = True
        submitted = _lifecycle_service(service).submit()
        if submitted.get("ok"):
            try:
                update_execution_action(
                    _SELFEDIT_PUBLISH_ACTION_SCOPE, action_run_id, "completed",
                )
            except Exception as exc:
                logger.warning("selfedit_publish_claim_update_failed error_type=%s", type(exc).__name__)
        with _finish_lock:
            if submitted.get("ok"):
                _finish_job.update(
                    state="done", pr_url=submitted.get("pr_url"),
                    notice=submitted.get("notice"), finished_at=time.time(),
                    human_only=submitted.get("human_only"),
                    apply_command=submitted.get("apply_command"),
                )
            else:
                _finish_job.update(
                    state="unknown",
                    notice="Submission outcome is unresolved; inspect the saved workspace status before retrying.",
                    finished_at=time.time(),
                )
            state, pr_url, run_id = (_finish_job["state"], _finish_job["pr_url"],
                                     _finish_job["run_id"])
            notice = _finish_job.get("notice")
        # Keep the fact that a notice exists observable without copying
        # provider or GitHub error text into the diagnostic log.
        logger.info("selfedit_state_transition state=finish_%s pr_present=%s run_id=%s notice_present=%s",
                    state, bool(pr_url), run_id, bool(notice))
    except Exception as exc:  # noqa: BLE001 — a crash must still settle the job
        # Without this the job would sit in "validating" forever and the
        # developer would keep reporting it as still running.
        logger.warning("selfedit_finish_job_failed error_type=%s",
                       type(exc).__name__)
        if claimed and not publication_dispatched and action_run_id:
            try:
                update_execution_action(
                    _SELFEDIT_PUBLISH_ACTION_SCOPE, action_run_id, "failed",
                )
            except Exception as update_exc:
                logger.warning("selfedit_publish_claim_update_failed error_type=%s",
                               type(update_exc).__name__)
        with _finish_lock:
            _finish_job.update(
                state=("unknown" if publication_dispatched else
                       "cancelled" if _finish_job.get("cancel_requested") else "error"),
                notice=f"finish failed ({type(exc).__name__})",
                finished_at=time.time(),
            )


def _run_agent(goal: str, profile: str | None, plan: str | None = None,
               run_id: str | None = None,
               action_run_id: str | None = None,
               action_scope: str = _SELFEDIT_STAGED_START_ACTION_SCOPE, *,
               data_policy=None, plan_policy=None) -> None:
    """Background thread target: plan edits, then settle the job state."""
    global _run_agent_instance
    try:
        agent = _make_agent(_selfedit_service, profile, run_id)
        with _run_lock:
            _run_agent_instance = agent
            cancelled = _run_job.get("cancel_requested", False)
        if cancelled:
            agent.request_cancel()
        # A session left open by an earlier run that ended without
        # submitting (review F6) must not be inherited by a NEW goal:
        # UpgradeAgent.run() reuses an active session as-is, so the next
        # goal would plan on the old branch with the old proposal still
        # applied. Same goal → resume it (validate/submit by voice); a
        # different goal → drop the leftover first, and say so in the log.
        _cleanup_existing_workspace(_selfedit_service, goal)
        policies = {key: value for key, value in {'data_policy': data_policy, 'plan_policy': plan_policy}.items()
                    if value is not None}
        result = agent.run(goal, plan=plan, **policies)
        if result.get("cancelled") or _run_job.get("cancel_requested", False):
            state = "cancelled"
            # Cancellation stops the VM and revokes publication eligibility;
            # the saved session remains available for inspection and cleanup.
            _selfedit_service.cancel()
        else:
            state = "done" if result.get("ok") else "error"
        summary = result.get("summary", "") or ""
        submitted = bool(result.get("submitted"))
        if state == "done" and not submitted:
            # Mechanical, not prompt-based (review F6): the planner's prose
            # after a failed validation reads like a report, and "done"
            # sounded like a PR. Say what actually happened, then relay it.
            proposals = len(_selfedit_service.proposals) if _selfedit_service.branch else 0
            still_open = (
                f" The session is still open with {proposals} proposed edit(s) — "
                "say finish to validate and open the PR, or revert to drop it."
                if _selfedit_service.branch else ""
            )
            summary = f"Ended without submitting a pull request.{still_open} {summary}".strip()
        with _run_lock:
            # The job must not become terminal until its durable action claim
            # has settled. Status readers use this lock and may immediately
            # look up the receipt after seeing "done".
            _update_staged_selfedit_claim(
                action_run_id, "failed" if state in {"error", "cancelled"} else "completed",
                action_scope,
            )
            _run_agent_instance = None
            _run_job.update(
                state=state,
                # The summary is what the developer relays and what the Edit
                # panel shows; logging it too means a declined/failed run's
                # REASON survives in admin.log instead of only in memory
                # (2026-08-30: three state=error transitions logged with no
                # cause anywhere on disk).
                summary=summary,
                submitted=submitted,
                pr_url=result.get("pr_url"),
                finished_at=time.time(),
            )
        # Record job state without persisting user-authored instructions or
        # model-generated summaries to the diagnostic log.
        logger.info("selfedit_state_transition state=%s submitted=%s",
                    state, submitted)
    except Exception as exc:  # planner crash must still settle the job
        logger.warning("upgrade_run_failed error_type=%s", type(exc).__name__)
        with _run_lock:
            _update_staged_selfedit_claim(action_run_id, "failed", action_scope)
            _run_agent_instance = None
            _run_job.update(
                state="error",
                summary=f"Upgrade run failed ({type(exc).__name__}).",
                finished_at=time.time(),
            )
        logger.info("selfedit_state_transition state=error")


def _busy() -> bool:
    """True while EITHER self-edit job holds the single session (SE4/SE10).
    The console's own /validate and /submit routes are gated on this, so a
    finish job in flight reports "a run is in progress" rather than two
    validations racing over one worktree."""
    with _opening_lock:
        if _opening_job["state"] == "starting":
            return True
    with _run_lock:
        if _run_job["state"] == "running":
            return True
    with _finish_lock:
        return _finish_job["state"] in ("validating", "submitting")


def _make_appbuild_agent(workspace: AppWorkspace, profile: str | None) -> AppBuildAgent:
    """Construct the planner (seam for tests), mirroring _make_agent."""
    return AppBuildAgent(workspace, profile=profile, run_id=_appbuild_parent_id.get())


def _appbuild_busy() -> bool:
    with _appbuild_lock:
        return _appbuild_job["state"] in {"running", "submitting"}


def _update_appbuild_start_claim(run_id: str | None, status: str) -> None:
    if not run_id:
        return
    try:
        update_execution_action(_APPBUILD_START_ACTION_SCOPE, run_id, status)
    except Exception as exc:  # the accepted result must not be lost to telemetry
        logger.warning("appbuild_start_claim_update_failed error_type=%s", type(exc).__name__)


def _update_appbuild_submit_claim(session_id: str | None, status: str) -> None:
    if not session_id:
        return
    try:
        update_execution_action(_APPBUILD_SUBMIT_ACTION_SCOPE, session_id, status)
    except Exception as exc:
        logger.warning("appbuild_submit_claim_update_failed error_type=%s", type(exc).__name__)


def _prior_appbuild_submit(session_id: str, workspace_status: dict[str, Any]) -> dict[str, Any] | None:
    """Resolve or block a repeated PR submission for one persisted sandbox session."""
    publication = workspace_status.get("publication") or {}
    pr_url = workspace_status.get("pr_url") or publication.get("url")
    if pr_url:
        # The sandbox's saved publication is authoritative even if the claim
        # store is temporarily unavailable during recovery.
        try:
            claim_execution_action(_APPBUILD_SUBMIT_ACTION_SCOPE, session_id)
        except Exception as exc:
            logger.warning("appbuild_submit_claim_write_failed error_type=%s", type(exc).__name__)
        _update_appbuild_submit_claim(session_id, "completed")
        return {
            "ok": True, "started": False, "duplicate": True,
            "state": "completed", "action_run_id": session_id,
            "pr_url": pr_url,
            "summary": "The draft pull request for this app-build session is already available.",
        }
    try:
        prior = get_execution_action(_APPBUILD_SUBMIT_ACTION_SCOPE, session_id)
    except Exception as exc:
        logger.warning("appbuild_submit_claim_read_failed error_type=%s", type(exc).__name__)
        return {
            "ok": False, "state": "unknown", "action_run_id": session_id,
            "error": "could not verify whether this app-build session was already submitted; no retry was launched",
        }
    if workspace_status.get("phase") in {"publishing", "publication_pending"}:
        if prior is None:
            try:
                if claim_execution_action(_APPBUILD_SUBMIT_ACTION_SCOPE, session_id):
                    _update_appbuild_submit_claim(session_id, "running")
            except Exception as exc:
                logger.warning("appbuild_submit_claim_write_failed error_type=%s", type(exc).__name__)
        return {
            "ok": True, "started": False, "duplicate": True,
            "state": "unknown", "action_run_id": session_id,
            "reconciliation_required": True,
            "summary": (
                "This sandbox session has a publication in progress or pending reconciliation; "
                "no new pull request was started. Inspect the saved workspace and GitHub repository."
            ),
        }
    if prior is None and not pr_url:
        return None
    same_live_job = (
        _appbuild_job.get("submit_action_id") == session_id
        and _appbuild_job.get("state") == "submitting"
    )
    state = "submitting" if same_live_job else "unknown"
    return {
        "ok": True, "started": False, "duplicate": True,
        "state": state, "action_run_id": session_id,
        "reconciliation_required": state == "unknown",
        "summary": (
            "Submission for this app-build session was already claimed; no new pull request was started. "
            "Check app-build status and the saved GitHub repository before considering any retry."
        ),
    }


def _run_appbuild_agent(
    app: str, goal: str, profile: str | None, plan: str | None = None,
    run_id: str | None = None, *, data_policy=None, plan_policy=None,
) -> None:
    """Background thread target, mirroring _run_agent: build one app, then
    settle _appbuild_job. The AppWorkspace itself lives on _appbuild_
    workspace so the status/submit/cancel endpoints can reach the same
    session this thread is driving."""
    global _appbuild_workspace, _appbuild_agent_instance
    workspace = None
    try:
        cleanup = _workspace_cleanup_context.get()
        workspace = cleanup._service if cleanup is not None else AppWorkspace(app)
        if _workspace_start_policy.get() is not None:
            from jarvis.agents.workspace import AppWorkspace as InstalledAppWorkspace
            if type(workspace) is not InstalledAppWorkspace or workspace.app_name != app:
                raise RuntimeError('workspace_source_changed')
            _cleanup_existing_workspace(workspace, goal)
        parent_token = _appbuild_parent_id.set(run_id)
        try:
            agent = _make_appbuild_agent(workspace, profile)
        finally:
            _appbuild_parent_id.reset(parent_token)
        with _appbuild_lock:
            _appbuild_workspace = workspace
            _appbuild_agent_instance = agent
            cancelled = _appbuild_job.get("cancel_requested", False)
        if cancelled:
            agent.request_cancel()
        policies = {key: value for key, value in {'data_policy': data_policy, 'plan_policy': plan_policy}.items()
                    if value is not None}
        result = agent.run(goal, plan=plan, **policies)
        with _appbuild_lock:
            cancelled = _appbuild_job.get("cancel_requested", False) or result.get("cancelled", False)
        if cancelled:
            workspace.cancel()
        state = "cancelled" if cancelled else ("done" if result.get("ok") else "error")
        with _appbuild_lock:
            if _appbuild_job.get("cancel_requested", False):
                state = "cancelled"
            # Persist the terminal receipt before publishing a terminal job.
            # A replay may read the receipt as soon as it sees this job finish.
            _update_appbuild_start_claim(
                run_id, "failed" if state in {"error", "cancelled"} else "completed",
            )
            _appbuild_agent_instance = None
            _appbuild_job.update(
                state=state, summary=result.get("summary", ""),
                submitted=bool(result.get("submitted")), pr_url=result.get("pr_url"),
                finished_at=time.time(),
            )
        logger.info("appbuild_state_transition state=%s", state)
    except Exception as exc:  # a build crash must still settle the job
        logger.warning("appbuild_run_failed error_type=%s", type(exc).__name__)
        with _appbuild_lock:
            cancelled = _appbuild_job.get("cancel_requested", False)
            _update_appbuild_start_claim(run_id, "failed")
            _appbuild_agent_instance = None
            _appbuild_job.update(
                state="cancelled" if cancelled else "error",
                summary="Build cancelled." if cancelled else f"App build failed ({type(exc).__name__}).",
                finished_at=time.time(),
            )
        logger.info("appbuild_state_transition state=%s",
                    "cancelled" if cancelled else "error")


def _council_busy() -> bool:
    with _council_lock:
        return _council_job["state"] == "running"


def _run_council_job(
    *, trigger: str, goal: str, context: dict[str, Any], placement: str = "planner",
    parent_budget: TaskBudget | None = None, data_policy: DataPolicy | None = None,
    cancel_event: threading.Event | None = None, started_at: float | None = None,
) -> None:
    """MORTIMER_LLM_COUNCIL_V2_PLAN.md V5 — background thread target,
    mirroring `_run_agent`'s shape: run the round, then settle
    `_council_job`. `convene()` returning None (D13's structural-failure
    case) settles the job as `error`; a `RoundResult` with `winner=None`
    (the round ran but selected nobody) settles as `done` with
    `winner=None` and `select_reason` populated — the same distinction
    `_maybe_escalate` makes between `result is None` and
    `result.winner is None`."""
    started_at = time.time() if started_at is None else started_at
    try:
        owner, policy = _advisory_owner(
            "council", context, None, parent_budget=parent_budget,
            data_policy=data_policy, cancel_event=cancel_event, started_at=started_at,
        )
        host_kwargs = ({"parent_budget": owner, "data_policy": policy,
                        "cancel_event": cancel_event} if owner is not None else {})
        result = asyncio.run(council_mod.convene(
            workflow="selfedit", placement=placement, trigger=trigger,
            goal=goal, tier=1, context=context, **host_kwargs,
        ))
        _check_advisory_owner(owner, cancel_event)
    except (Exception, asyncio.CancelledError) as exc:  # every exit settles the job
        logger.warning("council_job_failed error_type=%s", type(exc).__name__)
        with _council_lock:
            _council_job.update(
                state="error",
                error=_advisory_failure(exc, "council job failed"),
                finished_at=time.time(),
            )
        return

    if result is None:
        with _council_lock:
            _council_job.update(
                state="error",
                error="council unavailable — see admin sidecar logs",
                finished_at=time.time(),
            )
        return

    winner = (
        {"profile": result.winner.profile, "content": result.winner.content}
        if result.winner is not None else None
    )
    with _council_lock:
        _council_job.update(
            state="done", round_id=result.round_id, winner=winner,
            winner_mean=result.winner_mean, select_reason=result.select_reason,
            error=None, finished_at=time.time(),
        )


# --------------------------------------------------------- planning pathway
# MORTIMER_PLANNING_PATHWAY_PLAN.md P7. Two background-thread targets
# (single-model vs council-parallel), mirroring `_run_agent`/`_run_council_
# job`'s shape: each settles `_plan_job` on every exit path, never leaving
# it stuck at "running".


def _resolve_planning_profile(explicit: str | None) -> dict[str, Any]:
    """explicit > JARVIS_PLANNING_PROFILE env > registry default — the
    same three-level precedence `resolve_profile` already implements for
    self-edit's PROFILE_ENV, just fed OUR env var so the two pathways
    can be configured independently. Raises UnknownModelProfileError
    (caught by callers, same as `_make_agent` above) for an unknown name."""
    registry = load_model_registry()
    name = explicit or os.environ.get("JARVIS_PLANNING_PROFILE") or registry.get("default")
    return resolve_profile(registry, name)


def _run_plan_single(
    goal: str, profile: dict[str, Any], context: dict[str, Any],
    run_id: str | None = None,
    *, parent_budget: TaskBudget | None = None, data_policy: DataPolicy | None = None,
    cancel_event: threading.Event | None = None, started_at: float | None = None, job_guard=None,
) -> None:
    # MORTIMER_PLAN_REVIEW_AND_DOCS_PLAN.md R3 — single mode now shares
    # the same _proposer_user_message assembly council mode uses, so a
    # review job's document lands here automatically instead of via an
    # ad-hoc f-string that had no room for it.
    is_review = context.get("document") is not None
    system_prompt = PLAN_REVIEW_PROMPT if is_review else PLAN_AUTHOR_PROMPT
    user_content = council_mod._proposer_user_message(goal, context, "doc")
    started_at = time.time() if started_at is None else started_at
    guard = job_guard or _advisory_new_guard('planning', run_id, cancel_event)
    cancel_event = guard['event']
    policy = data_policy
    try:
        owner, policy = _advisory_owner(
            "planning", context, run_id, parent_budget=parent_budget,
            data_policy=data_policy, cancel_event=cancel_event, started_at=started_at,
        )
        call_kwargs = {}
        if owner is not None:
            workload = "council" if is_review else "planning"
            policy = council_mod._host_policy(context, workload, policy)
            execution = council_mod._child_execution(
                owner, workload, policy, cancel_event, started_at=started_at,
                sponsored=parent_budget is not None,
            )
            call_kwargs = {"execution": execution, "data_policy": policy}
        content, _usage = asyncio.run(council_mod._call_profile(
            profile, system_prompt, user_content,
            council_config.PLANNING_MEMBER_TIMEOUT_S, rung="planning", **call_kwargs,
        ))
        _check_advisory_owner(owner, cancel_event)
    except (Exception, asyncio.CancelledError) as exc:  # every exit settles the job
        logger.warning("plan_single_job_failed error_type=%s", type(exc).__name__)
        _advisory_publish('planning', guard, dict(
                state="error",
                error=_advisory_failure(exc, "planning call failed"),
                finished_at=time.time(),
            ), run_id, claim_status='failed', policy=policy, failure=True)
        return
    _advisory_publish('planning', guard, dict(
            state="done", plan=content, author=profile["name"],
            finished_at=time.time(),
        ), run_id, claim_status='completed', policy=policy)


def _run_plan_council(
    goal: str, members: dict[str, list[str]] | None, context: dict[str, Any],
    run_id: str | None = None,
    *, parent_budget: TaskBudget | None = None, data_policy: DataPolicy | None = None,
    cancel_event: threading.Event | None = None, started_at: float | None = None, job_guard=None,
) -> None:
    started_at = time.time() if started_at is None else started_at
    guard = job_guard or _advisory_new_guard('planning', run_id, cancel_event)
    cancel_event = guard['event']
    policy = data_policy
    try:
        owner, policy = _advisory_owner(
            "planning", context, run_id, parent_budget=parent_budget,
            data_policy=data_policy, cancel_event=cancel_event, started_at=started_at,
        )
        host_kwargs = ({"parent_budget": owner, "data_policy": policy,
                        "cancel_event": cancel_event} if owner is not None else {})
        result = asyncio.run(council_mod.draft_candidates(
            goal, members=members, judge=True, context=context, run_id=run_id,
            **host_kwargs,
        ))
        _check_advisory_owner(owner, cancel_event)
    except (Exception, asyncio.CancelledError) as exc:
        logger.warning("plan_council_job_failed error_type=%s", type(exc).__name__)
        _advisory_publish('planning', guard, dict(
                state="error",
                error=_advisory_failure(exc, "planning round failed"),
                finished_at=time.time(),
            ), run_id, claim_status='failed', policy=policy, failure=True)
        return
    if result is None:
        _advisory_publish('planning', guard, dict(
                state="error",
                error="council unavailable — see admin sidecar logs",
                finished_at=time.time(),
            ), run_id, claim_status='failed', policy=policy, failure=True)
        return
    if not result.proposals:
        _advisory_publish('planning', guard, dict(
                state="error",
                error=result.select_reason or "no candidates were produced",
                finished_at=time.time(),
            ), run_id, claim_status='failed', policy=policy, failure=True)
        return
    candidates = [
        {
            "label": p.label, "profile": p.profile, "content": p.content,
            "advisory_mean": council_mod.mean_of(p.label, result.scores),
        }
        for p in result.proposals
    ]
    _advisory_publish('planning', guard, dict(
            state="awaiting_choice", round_id=result.round_id,
            candidates=candidates, finished_at=time.time(),
        ), run_id, claim_status='awaiting_choice', policy=policy)


def _slugify_goal(goal: str) -> str:
    """Default adopt path (P7's endpoint table): docs/plans/<slug>.md."""
    slug = re.sub(r"[^a-z0-9]+", "-", goal.lower()).strip("-")
    return slug[:60] or "plan"


@app.get("/api/health")
def health() -> dict:
    return {"ok": True}


@app.get("/api/git/status")
def status() -> dict:
    return logic.git_status()


@app.get("/api/architecture")
def architecture_reference() -> dict:
    """Expose the checked-in architecture contract to the native sidecar.

    This is a read-only view of the repository document, not a second
    architecture store.  The digest lets the UI identify exactly which
    document the user is reading, while the bounded response protects the
    local admin service if a future document grows unexpectedly.
    """
    root = Path(os.environ.get("JARVIS_REPO_ROOT", str(REPO_ROOT)))
    path = root / "docs" / "ARCHITECTURE.md"
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        return {"ok": False, "error": f"architecture reference unavailable: {exc}"}
    max_chars = 120_000
    truncated = len(content) > max_chars
    visible = content[:max_chars] if truncated else content
    return {
        "ok": True,
        "path": "docs/ARCHITECTURE.md",
        "content": visible,
        "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "truncated": truncated,
    }


@app.get("/api/git/log")
def log(n: int = 5) -> dict:
    return logic.git_log(n)


@app.get("/api/git/diff")
def diff() -> dict:
    return logic.git_diff_summary()


@app.get("/api/git/actions")
def actions(status: str = "all", limit: int = 10) -> dict:
    return logic.list_actions(status, limit)


@app.post("/api/git/prepare-commit")
def prepare_commit(body: CommitDraftIn) -> dict:
    # Legacy console requests must refuse without inspecting or staging the
    # host index, even when the client omitted the old optional file list.
    return logic.prepare_commit(body.message, body.paths or [])


@app.post("/api/git/commit")
def commit(body: ActionIn) -> dict:
    return logic.commit(body.action_id)


@app.post("/api/git/prepare-push")
def prepare_push() -> dict:
    return logic.prepare_push()


@app.post("/api/git/push")
def push(body: ActionIn) -> dict:
    return logic.push(body.action_id)


# ------------------------------------------------------------- self-edit


@app.get("/api/selfedit/models")
def selfedit_models() -> dict:
    return {"ok": True, "models": available_models()}


@app.get("/api/model-routes")
def model_routes() -> dict:
    """Return route/workload policy metadata without credential material."""
    try:
        access = load_access_config()
        registry = load_model_registry()
        workloads = access.get("workloads") or {}
        configured_routes = access.get("routes") or {}
        profile_pool = dict(registry.get("profiles") or {})
        restricted_profiles = {}
        # Preserve Haiku's voice-only exception without adding an economy
        # profile to the general registry or hiding its current selection.
        if "voice_supervisor" in workloads:
            voice_name = workloads["voice_supervisor"].get("profile")
            if voice_name and voice_name not in profile_pool:
                profile_pool[voice_name] = model_profile_for_workload("voice_supervisor")
                restricted_profiles[voice_name] = ["voice_supervisor"]
        profiles = []
        choices = {name: {} for name in workloads}
        for name, profile in sorted(profile_pool.items()):
            routes = available_routes(profile, route_catalog=configured_routes)
            supported_workloads = restricted_profiles.get(name, sorted(workloads))
            profiles.append({
                "name": name,
                "identity": profile.get("identity", ""),
                "provider": profile.get("provider", ""),
                "model": profile.get("model", ""),
                "tier": profile.get("tier"),
                "routes": routes,
                "supported_workloads": supported_workloads,
                "api_key_env": profile.get("api_key_env"),
                "key_present": bool(profile.get("api_key_env")
                                     and os.environ.get(profile["api_key_env"])),
            })
            for workload in supported_workloads:
                choices[workload][name] = {
                    route: describe_route_choice(
                        workload, name, route, access_config=access,
                        registry=registry,
                    )
                    for route in routes
                }
        route_catalog = {}
        for name, route in configured_routes.items():
            route_catalog[name] = {
                "adapter": route.get("adapter", name),
                "billing": route.get("billing", name),
                "privacy": route.get("privacy", "approved_external"),
                "capabilities": list(route.get("capabilities") or []),
                "credential_env": route.get("credential_env"),
                "key_present": bool(route.get("credential_env")
                                     and os.environ.get(route["credential_env"])),
            }
        # Direct API is synthesized per profile by the resolver, not a global
        # YAML route. Its credentials/capabilities are in choices above.
        route_catalog.setdefault("direct_api", {
            "adapter": "profile_api", "billing": "provider_api",
            "privacy": "approved_external", "capabilities": [],
            "per_profile": True,
        })
        return {"ok": True, "routes": route_catalog,
                "workloads": workloads, "choices": choices,
                "profiles": profiles, "preferences": list_preferences(),
                "routing_enabled": os.environ.get("JARVIS_MODEL_ROUTING_ENABLED") == "1",
                "routing_process": "admin"}
    except Exception as exc:  # noqa: BLE001 - read-only status boundary
        logger.warning("model_routes_status_failed error_type=%s",
                       type(exc).__name__)
        return {"ok": False, "error": "model route status unavailable"}


@app.post("/api/model-routes/stage")
def model_routes_stage(body: ModelRouteStageIn) -> dict:
    """Draft a route choice; confirmation is a separate request by design."""
    try:
        return {"ok": True, **stage_preference(
            body.workload, body.profile, body.route, body.privacy)}
    except ModelPreferenceError as exc:
        return {"ok": False, "error": str(exc)}


@app.post("/api/model-routes/confirm")
def model_routes_confirm(body: ModelRouteConfirmIn) -> dict:
    try:
        return {"ok": True, **confirm_preference(body.draft_id)}
    except ModelPreferenceError as exc:
        return {"ok": False, "error": str(exc)}


@app.get("/api/selfedit/status")
def selfedit_status() -> dict:
    if _busy():
        return {"ok": False, "error": "an upgrade run is in progress — ask for status instead"}
    return _selfedit_service.status()


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
    flight = _selfedit_service.preflight(
        goal, has_plan=bool(plan_path), target_paths=body.target_paths,
    )
    if not flight["ok"]:
        return {"ok": False, "error": flight["error"], "tiers": flight["tiers"]}
    staging_id = uuid.uuid4().hex[:12]
    with _staging_lock:
        _prune_expired_stagings()
        _selfedit_stagings[staging_id] = {
            "goal": goal,
            "profile": body.profile,
            "plan_path": plan_path,
            "run_id": (body.run_id or "").strip() or None,   # GL9
            # SE3 — kept, not dropped: the confirm returns these to the
            # developer as the files it said it would change, so authoring
            # starts from the same list preflight classified.
            "target_paths": list(body.target_paths or []),
            "created_at": time.time(),
        }
    return {
        "ok": True,
        "staging_id": staging_id,
        "expires_in_s": SELFEDIT_STAGING_TTL_S,
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
    requested_action_scope = _SELFEDIT_STAGED_START_ACTION_SCOPE
    # Issued staging IDs are exactly 12 lowercase hexadecimal characters.
    # Avoid querying the execution-claim table for arbitrary/mangled input;
    # the one-live-stage repair below resolves that to the canonical ID.
    if requested_action_id and re.fullmatch(r"[0-9a-f]{12}", requested_action_id):
        duplicate = _prior_staged_selfedit_action(requested_action_id)
        if duplicate is not None:
            return duplicate
    # Refuse a confirm that lands during a live run BEFORE touching the
    # staging (2026-09-07 review, F4): the pop used to come first, so the
    # refusal itself consumed the preview the user had just approved.
    duplicate_claim = False
    with _run_lock:
        if (_run_job["state"] == "running" or _opening_job["state"] == "starting"
                or _finish_job["state"] in {"validating", "submitting"}):
            return {
                "ok": False,
                "error": "an upgrade run is already in progress — ask for status instead",
                "job": dict(_run_job),
            }
    if staging_id or not bare_goal:
        rec, staging_id, live = _take_staging(staging_id)
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
                    f"expired (staging lasts {int(SELFEDIT_STAGING_TTL_S // 60)} "
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
        logger.warning(
            "selfedit_run_stateless_confirm — pass staging_id instead "
            "(deprecated fallback, see G2)"
        )
        profile = body.profile
        plan_path = (body.plan_path or "").strip()
        run_id = run_id or None
        requested_action_id = run_id
        requested_action_scope = _SELFEDIT_RUN_START_ACTION_SCOPE
        prior = _prior_staged_selfedit_action(
            requested_action_id, requested_action_scope,
        )
        if prior is not None:
            return prior
        # The deprecated bare-goal form carries no target_paths (GoalIn has
        # no such field and gains none): only a staged preview classified
        # them.
        target_paths = []

    if authoring_enabled() and body.author and not plan_path and body.plan is None:
        # SE3 — developer-authored: an author=true confirm with no plan
        # document is a single stated goal, which the developer can author
        # in a few tool calls
        # (measured exploring runs: 15-72 s). Open the session synchronously
        # and hand it back; the developer writes in the SAME delegation
        # rather than restating the goal to a second LLM that starts blind.
        # A plan_path (or an explicit plan) is implementation-scale work and
        # still goes to the Upgrade Agent, below. Two declared fields
        # (author, plan_path), no judgment.
        return _begin_authoring(
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
        read_result = repo_logic.repo_read_file(plan_path)
        _source_plan_observed(plan_path, read_result)
        if not read_result.get("ok"):
            return {"ok": False, "error": read_result.get("error")}
        plan = read_result.get("content") or ""
        if len(plan) > council_config.PLAN_REVIEW_DOC_MAX_CHARS:
            plan = (
                plan[: council_config.PLAN_REVIEW_DOC_MAX_CHARS]
                + "\n\n… (plan truncated at injection)"
            )
    with _run_lock:
        if (_run_job["state"] == "running" or _opening_job["state"] == "starting"
                or _finish_job["state"] in {"validating", "submitting"}):
            return {
                "ok": False,
                "error": "an upgrade run is already in progress — ask for status instead",
                "job": dict(_run_job),
            }
        try:
            # Construct now so an unknown profile fails fast, synchronously,
            # before we report the run as started.
            agent = _make_agent(_selfedit_service, profile, run_id)
        except UnknownModelProfileError as exc:
            return {"ok": False, "error": str(exc)}
        if requested_action_id:
            try:
                claimed = claim_execution_action(
                    requested_action_scope, requested_action_id,
                )
            except Exception as exc:
                logger.warning("selfedit_start_claim_write_failed error_type=%s", type(exc).__name__)
                return {"ok": False, "error": "could not safely record this self-edit; no job was started"}
            if not claimed:
                duplicate_claim = True
        if not duplicate_claim:
            _run_job.update(
                state="running", cancel_requested=False,
                run_id=run_id,
                goal=goal,
                profile=agent.model_label(),
                summary=None,
                started_at=time.time(),
                finished_at=None,
                submitted=False,
                pr_url=None,
                action_run_id=requested_action_id,
                action_scope=requested_action_scope,
            )
    if duplicate_claim:
        return _prior_staged_selfedit_action(
            requested_action_id, requested_action_scope,
        ) or {
            "ok": False, "error": "the self-edit claim could not be reconciled; no job was started",
        }
    logger.info("selfedit_state_transition state=running")
    try:
        threading.Thread(
            target=_source_worker_target(_run_agent),
            args=(goal, profile, plan, run_id, requested_action_id,
                  requested_action_scope),
            **({'kwargs': _source_worker_kwargs()} if _workspace_start_policy.get() is not None else {}),
            daemon=True,
        ).start()
    except Exception as exc:
        logger.warning("selfedit_worker_start_failed error_type=%s", type(exc).__name__)
        with _run_lock:
            _run_job.update(
                state="error", summary="Upgrade worker could not be started.",
                finished_at=time.time(),
            )
        _update_staged_selfedit_claim(
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
    with _run_lock:
        job = dict(_run_job)
    with _opening_lock:
        opening = dict(_opening_job)
    requested_action_id = (action_run_id or "").strip()
    requested_finish_id = (finish_action_id or "").strip()
    if requested_action_id and requested_finish_id:
        return {"ok": False, "error": "request only one self-edit action identity"}
    if requested_finish_id:
        if len(requested_finish_id) > 256:
            return {"ok": False, "error": "self-edit action identity is invalid"}
        with _finish_lock:
            finish_snapshot = dict(_finish_job)
        if finish_snapshot.get("action_run_id") != requested_finish_id:
            try:
                receipt = get_execution_action(
                    _SELFEDIT_PUBLISH_ACTION_SCOPE, requested_finish_id,
                )
            except Exception as exc:
                logger.warning("selfedit_status_claim_read_failed error_type=%s", type(exc).__name__)
                return {"ok": False, "error": "the self-edit submission receipt is unavailable"}
            session = _selfedit_service.status()
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
                    update_execution_action(
                        _SELFEDIT_PUBLISH_ACTION_SCOPE, requested_finish_id, "completed",
                    )
                except Exception as exc:
                    logger.warning("selfedit_publish_claim_update_failed error_type=%s", type(exc).__name__)
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
            and job.get("action_scope", _SELFEDIT_STAGED_START_ACTION_SCOPE)
            in {_SELFEDIT_STAGED_START_ACTION_SCOPE, _SELFEDIT_RUN_START_ACTION_SCOPE}
        ) or (
            opening.get("action_run_id") == requested_action_id
            and opening.get("action_scope", _SELFEDIT_STAGED_START_ACTION_SCOPE)
            in {_SELFEDIT_STAGED_START_ACTION_SCOPE, _SELFEDIT_RUN_START_ACTION_SCOPE}
        )
        if not live_action_matches:
            try:
                receipt = get_execution_action(
                    _SELFEDIT_STAGED_START_ACTION_SCOPE, requested_action_id,
                )
                if receipt is None:
                    receipt = get_execution_action(
                        _SELFEDIT_RUN_START_ACTION_SCOPE, requested_action_id,
                    )
            except Exception as exc:
                logger.warning("selfedit_status_claim_read_failed error_type=%s", type(exc).__name__)
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
    with _staging_lock:
        _prune_expired_stagings()
        now = time.time()
        stagings = [
            {
                "staging_id": sid,
                "age_s": round(now - rec["created_at"], 1),
                "expires_in_s": round(
                    SELFEDIT_STAGING_TTL_S - (now - rec["created_at"]), 1,
                ),
            }
            for sid, rec in _selfedit_stagings.items()
        ]
    with _finish_lock:
        finish = dict(_finish_job)
    return {
        "ok": True,
        "job": job,
        "finish": finish,
        "opening": opening,
        "status": _selfedit_service.status(),
        "stagings": stagings,
    }


@app.get("/api/selfedit/file")
def selfedit_file(path: str) -> dict:
    """SE2 — read one file from the SESSION worktree, allowlist-checked.
    Thin wrapper over the read_file the planner has always used."""
    if not authoring_enabled():
        return dict(_AUTHORING_OFF)
    pending = _prepare_file_access()
    if pending is not None:
        return pending
    return _selfedit_service.read_file(path)


class SelfEditWriteIn(BaseModel):
    """SE2 — the developer's own edit_propose."""
    path: str
    content: str
    rationale: str = ""
    visual_intent: str = ""
    # W8 — route a TEST that needs a human-only change into that proposal.
    # A human-only path is always routed; this flag never widens a write.
    proposal: bool = False


@app.post("/api/selfedit/write")
def selfedit_write(body: SelfEditWriteIn) -> dict:
    """SE2 — write one allowlisted edit into the session worktree.

    Same SelfEditService.propose_edit the planner calls: the same allowlist
    check, the same worktree, the same returned diff. Nothing about WHAT an
    edit may touch changes here — only which agent does the writing."""
    if not authoring_enabled():
        return dict(_AUTHORING_OFF)
    if not _selfedit_service.branch:
        return {"ok": False, "error": "no open self-edit session — start one first"}
    pending = _prepare_file_access()
    if pending is not None:
        return pending
    if _busy():
        return {"ok": False, "error": "validation is running — wait for it to finish, then edit"}
    return _selfedit_service.propose_edit(
        body.path, body.content, body.rationale, body.visual_intent,
        proposal=body.proposal,
    )


def _save_document_to_sandbox(path: str, content: str, rationale: str = "") -> dict:
    """Save generated documents through the same guarded VM editor as code.

    Reuse an explicitly opened session. Never discard another goal, start an
    unreviewed replacement session, or fall back to the installed checkout.
    """
    parts = path.split("/")
    if (len(parts) < 3 or parts[0] != "docs"
            or parts[1] not in {"plans", "reviews", "research"}
            or any(part in {"", ".", ".."} for part in parts)
            or "\\" in path or "\0" in path or not path.endswith(".md")):
        return {"ok": False, "error": "Save a Markdown file under docs/plans/, docs/reviews/, or docs/research/."}
    if not authoring_enabled():
        return dict(_AUTHORING_OFF)
    if not _selfedit_service.branch:
        return {"ok": False, "code": "sandbox_session_required",
                "error": "Open a self-edit sandbox session for saving this document, then retry the save. The generated document is still available.",
                "path": path}
    if _selfedit_service.is_human_only(path):
        # W8 routes a human-only write into a proposal; a generated
        # document is never one — refuse, as before.
        return {"ok": False, "error": f"{path} is human-only; save the document under another name."}
    source = _advisory_transport_context.get()
    if source is None:
        result = selfedit_write(SelfEditWriteIn(path=path, content=content, rationale=rationale))
    else:
        from jarvis.advisory_sources import save_advisory_document
        try:
            result = save_advisory_document(source, _selfedit_service, path, content, rationale,
                lambda: selfedit_write(SelfEditWriteIn(path=path, content=content, rationale=rationale)))
        except Exception:
            return {'ok': False, 'code': 'advisory_transfer_unavailable',
                    'error': 'The generated document cannot be saved into this unverified workspace.'}
    if not result.get("ok"):
        return result
    return {**result, "path": path, "saved_to_sandbox": True,
            "verified": False, "published": False,
            "summary": "Saved in the sandbox. Use selfedit_finish to verify the document and prepare a draft PR."}


@app.post("/api/selfedit/finish")
def selfedit_finish() -> dict:
    """SE4 — start the finish job: validate, and submit if green."""
    if not authoring_enabled():
        return dict(_AUTHORING_OFF)
    service = _lifecycle_service(_selfedit_service, terminal=True)
    session = service.status()
    action_run_id = str(session.get("id") or "")
    if action_run_id:
        prior = _prior_selfedit_publish(action_run_id)
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
    with _finish_lock:
        # The busy check is INLINED rather than calling _busy(): _busy()
        # acquires _finish_lock itself, and calling it from inside this
        # block would deadlock. _run_job's state is read without _run_lock
        # deliberately — a single dict lookup, and the authoritative guard
        # against two jobs is this lock plus _run_lock in selfedit_run.
        if _opening_job["state"] == "starting" or _run_job["state"] == "running" or _finish_job["state"] in (
            "validating", "submitting",
        ):
            return {"ok": False,
                    "error": "a run is already in progress — ask for status instead"}
        _finish_job.update(
            state="validating", checks=None, pr_url=None, notice=None, cancel_requested=False,
            human_only=None, apply_command=None,
            run_id=session.get("run_id") or service.run_id,
            action_run_id=action_run_id,
            started_at=time.time(), finished_at=None,
        )
    logger.info("selfedit_state_transition state=finish_validating run_id=%s",
                _selfedit_service.run_id)
    threading.Thread(target=_source_worker_target(_run_finish), daemon=True).start()
    return {
        "ok": True, "started": True, "state": "validating",
        "action_run_id": action_run_id,
    }


@app.post("/api/selfedit/validate")
def selfedit_validate() -> dict:
    if _busy():
        return {"ok": False, "error": "an upgrade run is in progress — ask for status instead"}
    result = _selfedit_service.validate()
    logger.info("selfedit_state_transition state=validated ok=%s", result.get("ok"))
    return result


class VerifyAppearanceBody(BaseModel):
    branch_override: bool = False
    display: int = 1


@app.post("/api/selfedit/verify-appearance")
def selfedit_verify_appearance(body: VerifyAppearanceBody | None = None) -> dict:
    """B2 — a CHECK, not a gate. Deliberately absent from validate()'s checks
    list: validation runs before the branch is on screen, so a capture then
    photographs the pre-change console and its green tick would mean
    nothing."""
    if _busy():
        return {"ok": False, "error": "an upgrade run is in progress — ask for status instead"}
    body = body or VerifyAppearanceBody()
    result = _selfedit_service.verify_appearance(
        branch_override=body.branch_override, display=body.display)
    logger.info("selfedit_verify_appearance ok=%s branch_present=%s",
                result.get("ok"), bool(result.get("branch")))
    return result


@app.post("/api/selfedit/submit")
def selfedit_submit() -> dict:
    if _busy():
        return {"ok": False, "error": "an upgrade run is in progress — ask for status instead"}
    session = _selfedit_service.status()
    action_run_id = str(session.get("id") or "")
    if not action_run_id:
        return {"ok": False, "error": "no open self-edit session"}
    prior = _prior_selfedit_publish(action_run_id)
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
        claimed = claim_execution_action(
            _SELFEDIT_PUBLISH_ACTION_SCOPE, action_run_id,
        )
    except Exception as exc:
        logger.warning("selfedit_publish_claim_write_failed error_type=%s", type(exc).__name__)
        return {"ok": False, "error": "could not safely record publication; no pull request was submitted"}
    if not claimed:
        return _prior_selfedit_publish(action_run_id) or {
            "ok": False, "state": "unknown", "action_run_id": action_run_id,
            "error": "publication was already claimed; inspect status before retrying",
        }
    try:
        update_execution_action(
            _SELFEDIT_PUBLISH_ACTION_SCOPE, action_run_id, "running",
        )
    except Exception as exc:
        logger.warning("selfedit_publish_claim_update_failed error_type=%s", type(exc).__name__)
    result = _selfedit_service.submit()
    if result.get("ok"):
        try:
            update_execution_action(
                _SELFEDIT_PUBLISH_ACTION_SCOPE, action_run_id, "completed",
            )
        except Exception as exc:
            logger.warning("selfedit_publish_claim_update_failed error_type=%s", type(exc).__name__)
    logger.info("selfedit_state_transition state=submitted ok=%s", result.get("ok"))
    return {**result, "action_run_id": action_run_id}


@app.post("/api/selfedit/cancel")
def selfedit_cancel() -> dict:
    """Cancel planner, validation or publication through the saved VM session."""
    with _run_lock:
        running = _run_job["state"] == "running"
        agent = _run_agent_instance
        if running:
            _run_job["cancel_requested"] = True
    with _finish_lock:
        finishing = _finish_job["state"] in {"validating", "submitting"}
        if finishing:
            _finish_job["cancel_requested"] = True
    with _opening_lock:
        opening = _opening_job["state"] == "starting"
        if opening:
            _opening_job["cancel_requested"] = True
    if not running and not finishing and not opening:
        phase = _selfedit_service.status().get("phase")
        if phase not in {"creating", "starting", "validating", "publishing", "publication_pending"}:
            return {"ok": False, "error": "no self-edit run is in progress — use revert to drop an idle session"}
    if running and agent is not None:
        agent.request_cancel()
    else:
        _selfedit_service.cancel()
    logger.info("selfedit_state_transition state=cancel_requested")
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
    if _busy():
        return selfedit_cancel()
    result = _selfedit_service.revert()
    logger.info("selfedit_state_transition state=reverted ok=%s", result.get("ok"))
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
    if _busy():
        return {"ok": False, "error": "an upgrade run is in progress — ask for status instead"}
    if not _selfedit_service.branch:
        return {"ok": False, "error": "no active self-edit session to reject"}
    goal = _selfedit_service.goal or ""
    context = {"diff": _selfedit_service.proposals, "checks": None}

    council_started = False
    with _council_lock:
        if _council_job["state"] != "running":
            _council_job.update(
                state="running", trigger="E3", goal=goal, round_id=None,
                winner=None, winner_mean=None, select_reason=None, error=None,
                started_at=time.time(), finished_at=None,
            )
            council_started = True
    if council_started:
        _start_advisory_thread(
            _run_council_job,
            kwargs={"trigger": "E3", "goal": goal, "context": context},
        )

    revert_result = _selfedit_service.revert()
    logger.info("selfedit_state_transition state=rejected ok=%s", revert_result.get("ok"))
    return {
        "ok": True, "reverted": revert_result, "council_started": council_started,
    }


# ------------------------------------------------------------- app-build
# MORTIMER_MODEL_DISCIPLINE_AND_MAC_SHELL_PLAN.md D5. Same background-
# thread-plus-polling shape as self-edit above, in its own job slot/lock
# so an app build never blocks a self-edit run (or vice versa). No merge
# endpoint here either — merging an app-build PR is human, on GitHub,
# always, same rule as self-edit.


@app.post("/api/appbuild/start")
def appbuild_start(body: AppBuildGoalIn) -> dict:
    """Start an app-build run in the background; poll GET /api/appbuild/job."""
    global _appbuild_workspace, _appbuild_agent_instance
    goal = (body.goal or "").strip()
    if not goal:
        return {"ok": False, "error": "a goal is required — what should I build?"}
    try:
        app_name = validate_app_name(body.app)
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
        prior = get_execution_action(_APPBUILD_START_ACTION_SCOPE, run_id)
    except Exception as exc:
        logger.warning("appbuild_start_claim_read_failed error_type=%s", type(exc).__name__)
        return {
            "ok": False,
            "error": "could not verify whether this app-build action already started; no retry was launched",
            "outcome": "unknown", "action_run_id": run_id,
        }
    if prior is not None:
        with _appbuild_lock:
            same_live_job = _appbuild_job.get("run_id") == run_id
            live_state = _appbuild_job.get("state") or "unknown"
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
        read_result = repo_logic.repo_read_file(plan_path)
        _source_plan_observed(plan_path, read_result)
        if not read_result.get("ok"):
            return {"ok": False, "error": read_result.get("error")}
        plan = read_result.get("content") or ""
        if len(plan) > council_config.PLAN_REVIEW_DOC_MAX_CHARS:
            plan = (
                plan[: council_config.PLAN_REVIEW_DOC_MAX_CHARS]
                + "\n\n… (plan truncated at injection)"
            )
    with _appbuild_lock:
        if _appbuild_job["state"] in {"running", "submitting"}:
            return {
                "ok": False,
                "error": "an app build is already in progress — ask for status instead",
                "job": dict(_appbuild_job),
            }
        try:
            # Construct now (against a throwaway probe workspace, never
            # cloned) so an unknown profile or a missing GITHUB_TOKEN fails
            # fast, synchronously, before we report the build as started —
            # same rule selfedit_run's _make_agent call follows.
            probe = AppWorkspace(app_name)
            agent = _make_appbuild_agent(probe, body.profile)
        except UnknownModelProfileError as exc:
            return {"ok": False, "error": str(exc)}
        except Exception as exc:  # noqa: BLE001 — e.g. GitHubError: no token configured
            return {"ok": False, "error": str(exc)}
        try:
            claimed = claim_execution_action(_APPBUILD_START_ACTION_SCOPE, run_id)
        except Exception as exc:
            logger.warning("appbuild_start_claim_write_failed error_type=%s", type(exc).__name__)
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
        _appbuild_workspace = None
        _appbuild_agent_instance = None
        _appbuild_job.update(
            state="running", app=app_name, goal=goal, cancel_requested=False,
            submitted=False, pr_url=None,
            profile=agent.model_label(), summary=None,
            started_at=time.time(), finished_at=None,
            run_id=run_id or None,
        )
    logger.info("appbuild_state_transition state=running")
    _update_appbuild_start_claim(run_id, "running")
    worker = threading.Thread(
        target=_source_worker_target(_run_appbuild_agent), args=(app_name, goal, body.profile, plan, run_id), daemon=True,
        **({'kwargs': _source_worker_kwargs()} if _workspace_start_policy.get() is not None else {}),
    )
    try:
        worker.start()
    except Exception as exc:
        logger.warning("appbuild_thread_start_failed error_type=%s", type(exc).__name__)
        with _appbuild_lock:
            _appbuild_job.update(state="error", finished_at=time.time())
        _update_appbuild_start_claim(run_id, "failed")
        return {"ok": False, "error": "the app-build worker could not be started"}
    return {"ok": True, "started": True, "profile": agent.model_label()}


def _recover_appbuild_workspace():
    global _appbuild_workspace
    with _appbuild_lock:
        if _appbuild_workspace is not None or _appbuild_job["state"] in {"running", "submitting"}:
            return _appbuild_workspace
    try:
        recovered = AppWorkspace.recover()
    except Exception:
        # No configured runtime is normal on a host that has never developed
        # an app. Start still reports its actionable setup/configuration error.
        return None
    with _appbuild_lock:
        if _appbuild_workspace is None and _appbuild_job["state"] not in {"running", "submitting"}:
            _appbuild_workspace = recovered
        return _appbuild_workspace


@app.get("/api/appbuild/job")
def appbuild_job_status(
    run_id: str | None = None, submit_action_id: str | None = None,
) -> dict:
    _recover_appbuild_workspace()
    with _appbuild_lock:
        job = dict(_appbuild_job)
        workspace = _appbuild_workspace
    requested_submit_id = (submit_action_id or "").strip()
    if requested_submit_id:
        if len(requested_submit_id) > 256:
            return {"ok": False, "error": "app-build submission identity is invalid"}
        status = workspace.status() if workspace is not None else {"active": False}
        try:
            receipt = get_execution_action(
                _APPBUILD_SUBMIT_ACTION_SCOPE, requested_submit_id,
            )
        except Exception as exc:
            logger.warning("appbuild_submit_status_claim_read_failed error_type=%s", type(exc).__name__)
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
                receipt = get_execution_action(_APPBUILD_START_ACTION_SCOPE, requested_run_id)
            except Exception as exc:
                logger.warning("appbuild_status_claim_read_failed error_type=%s", type(exc).__name__)
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


def _submit_appbuild(workspace, operation_id, session_id, output):
    try:
        workspace = _lifecycle_service(workspace)
        result = workspace.submit()
    except Exception as exc:
        logger.warning("app_workspace_submission_failed error_type=%s",
                       type(exc).__name__)
        result = {"ok": False, "error": "App submission failed; inspect the saved workspace before retrying."}
    output["result"] = result
    with _appbuild_lock:
        if _appbuild_job.get("operation_id") == operation_id:
            _appbuild_job.update(state="done" if result.get("ok") else
                ("cancelled" if _appbuild_job.get("cancel_requested") else "error"),
                submitted=bool(result.get("ok")), pr_url=result.get("pr_url"),
                summary=result.get("notice") or result.get("error") or "Draft pull request opened.",
                finished_at=time.time())
    if result.get("ok") and result.get("pr_url"):
        _update_appbuild_submit_claim(session_id, "completed")
    elif result.get("ok"):
        _update_appbuild_submit_claim(session_id, "running")


@app.post("/api/appbuild/submit")
def appbuild_submit() -> dict:
    workspace = _lifecycle_service(_recover_appbuild_workspace(), terminal=True)
    if workspace is None:
        return {"ok": False, "error": "no active app-build session to submit"}
    workspace_status = workspace.status()
    session_id = str(workspace_status.get("id") or "").strip()
    if not session_id or len(session_id) > 256:
        return {"ok": False, "error": "the app-build session has no stable submission identity; no pull request was submitted"}
    with _appbuild_lock:
        if _appbuild_job["state"] in {"running", "submitting"}:
            return {"ok": False, "error": "an app build is in progress — ask for status instead"}
    prior = _prior_appbuild_submit(session_id, workspace_status)
    if prior is not None:
        return prior
    with _appbuild_lock:
        if _appbuild_job["state"] in {"running", "submitting"}:
            return {"ok": False, "error": "an app build is in progress — ask for status instead"}
        prior = _prior_appbuild_submit(session_id, workspace_status)
        if prior is not None:
            return prior
        if not workspace_status.get("active") or not workspace_status.get("branch"):
            return {"ok": False, "error": "no active app-build session to submit"}
        if not workspace_status.get("proposals"):
            return {"ok": False, "error": "no app-build edits have been proposed"}
        if not workspace_status.get("validated_ok"):
            return {"ok": False, "error": "validation must pass before app-build submission"}
        try:
            claimed = claim_execution_action(_APPBUILD_SUBMIT_ACTION_SCOPE, session_id)
        except Exception as exc:
            logger.warning("appbuild_submit_claim_write_failed error_type=%s", type(exc).__name__)
            return {"ok": False, "error": "could not safely record app-build submission; no pull request was submitted"}
        if not claimed:
            return {
                "ok": False, "state": "unknown", "action_run_id": session_id,
                "reconciliation_required": True,
                "error": "app-build submission was already claimed; inspect status before retrying",
            }
        _update_appbuild_submit_claim(session_id, "running")
        operation_id = uuid.uuid4().hex
        _appbuild_job.update(state="submitting", operation_id=operation_id, cancel_requested=False,
                            submitted=False, pr_url=None, finished_at=None,
                            submit_action_id=session_id)
    output = {}
    worker = threading.Thread(
        target=_source_worker_target(_submit_appbuild),
        args=(workspace, operation_id, session_id, output), daemon=True,
    )
    try:
        worker.start()
    except Exception as exc:
        logger.warning("appbuild_submit_thread_start_failed error_type=%s", type(exc).__name__)
        with _appbuild_lock:
            if _appbuild_job.get("operation_id") == operation_id:
                _appbuild_job.update(state="unknown", finished_at=time.time())
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
    _recover_appbuild_workspace()
    with _appbuild_lock:
        running = _appbuild_job["state"] in {"running", "submitting"}
        workspace = _appbuild_workspace
        agent = _appbuild_agent_instance
        if running:
            _appbuild_job["cancel_requested"] = True
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
    logger.info("appbuild_state_transition state=cancelled ok=%s", result.get("ok"))
    return result


# ------------------------------------------------------------- research
# MORTIMER_SITE_RESEARCH_AND_COMPARISON_PLAN.md R1/R6/R10. Same background-
# thread-plus-polling shape as self-edit/plan/council/app-build above.


@app.post("/api/research/start")
def research_start(body: ResearchStartIn) -> dict:
    advisory_started_at = time.time()
    if not _research_enabled():
        return {"ok": False, "error": RESEARCH_DISABLED_MESSAGE}
    run_id = (body.run_id or "").strip()
    if not run_id:
        return {"ok": False, "error": "a stable run_id is required for a research start"}
    if len(run_id) > 256:
        return {"ok": False, "error": "run identity is invalid; no research job was started"}
    urls = [u.strip() for u in (body.urls or []) if u.strip()]
    cfg = research_crawl.load_research_config()
    max_sites = int(cfg.get("max_sites", 2))
    if len(urls) < 2:
        return {"ok": False, "error": "two URLs are required to compare"}
    if len(urls) > max_sites:
        return {"ok": False, "error": f"at most {max_sites} sites can be compared at once"}
    if not os.environ.get(research_crawl.TAVILY_API_KEY_ENV):
        return {"ok": False, "error": "TAVILY_API_KEY is not configured"}
    with _research_lock:
        try:
            prior = get_execution_action(_RESEARCH_START_ACTION_SCOPE, run_id)
        except Exception as exc:
            logger.warning("research_start_claim_read_failed error_type=%s", type(exc).__name__)
            return {
                "ok": False,
                "error": "could not verify whether this research already started; no retry was launched",
                "outcome": "unknown", "action_run_id": run_id,
            }
        if prior is not None:
            return _research_duplicate(run_id, prior, _research_job)
        if _research_job["state"] == "running":
            return {
                "ok": False,
                "error": "a comparison is already in progress — ask for status instead",
                "job": dict(_research_job),
            }
        try:
            claimed = claim_execution_action(_RESEARCH_START_ACTION_SCOPE, run_id)
        except Exception as exc:
            logger.warning("research_start_claim_write_failed error_type=%s", type(exc).__name__)
            return {
                "ok": False,
                "error": "could not safely record research start; no crawl was launched",
                "outcome": "unknown", "action_run_id": run_id,
            }
        if not claimed:
            try:
                prior = get_execution_action(_RESEARCH_START_ACTION_SCOPE, run_id)
            except Exception:
                prior = None
            return _research_duplicate(
                run_id, prior or {"status": "unknown"}, _research_job,
            )
        _research_job.update(
            state="running", urls=urls, focus=(body.focus or "").strip() or None,
            sites=None, comparison=None, model=None, credits_used=None, error=None,
            started_at=time.time(), finished_at=None, saved_path=None, save_error=None,
            run_id=run_id,
        )
        _activate_advisory(_research_job)
    _update_research_start_claim(run_id, "running")
    logger.info("research_state_transition state=running site_count=%d", len(urls))
    try:
        _start_advisory_thread(
            _run_research_job, args=(urls, body.focus or "", run_id),
            started_at=advisory_started_at,
        )
    except Exception as exc:
        logger.warning("research_job_dispatch_failed error_type=%s", type(exc).__name__)
        with _research_lock:
            _research_job.update(state="error", error="research job could not be started",
                                 finished_at=time.time())
        _update_research_start_claim(run_id, "failed")
        return {"ok": False, "error": "research job could not be started",
                "action_run_id": run_id}
    return {"ok": True, "started": True, "action_run_id": run_id}


@app.get("/api/research/job")
def research_job_status(run_id: str | None = None) -> dict:
    requested_run_id = (run_id or "").strip()
    with _research_lock:
        _advisory_context_for_job('research', _research_job)
        job = dict(_research_job)
    if requested_run_id and job.get("run_id") != requested_run_id:
        try:
            prior = get_execution_action(_RESEARCH_START_ACTION_SCOPE, requested_run_id)
        except Exception as exc:
            logger.warning("research_status_claim_read_failed error_type=%s", type(exc).__name__)
            return {"ok": False, "error": "research status is temporarily unavailable"}
        if prior is None:
            return {"ok": False, "error": "no research action found for that execution ID"}
        state = prior.get("status", "unknown")
        if state in {"claimed", "running", "awaiting_choice"}:
            state = "unknown"
        state = {"completed": "done", "failed": "error"}.get(state, state)
        job = {"state": state, "run_id": requested_run_id,
               "finished_at": None, "error": None}
    return {"ok": True, "job": job}


@app.post("/api/research/save")
def research_save(body: ResearchSaveIn) -> dict:
    """Save through the guarded sandbox editor. Attribution names model, URLs, page
    counts, and credits — a comparison without its sources and cost is a
    claim with no provenance (R6/R8)."""
    with _research_lock:
        source = _advisory_context_for_job('research', _research_job)
        if _research_job["state"] != "done":
            return {"ok": False, "error": "no finished comparison to save"}
        job = dict(_research_job)
    comparison = job.get("comparison") or ""
    if not comparison:
        return {"ok": False, "error": "the comparison is empty"}

    urls = job.get("urls") or []
    slug = re.sub(r"[^a-z0-9]+", "-", "-vs-".join(urls).lower()).strip("-")[:60] or "comparison"
    path = (body.path or "").strip() or f"docs/research/{slug}.md"

    registry = load_model_registry()
    profiles = registry.get("profiles", {})
    model_name = job.get("model") or "unknown"
    provider_model = (profiles.get(model_name) or {}).get("model", model_name)
    sites = job.get("sites") or []
    pages_note = ", ".join(
        f"{s.get('url')}: {s.get('page_count')} pages" if s.get("ok")
        else f"{s.get('url')}: failed ({s.get('error_kind', 'unknown')})"
        for s in sites
    )
    footer = (
        f"\n\n---\n*Comparison by {model_name} ({provider_model}) — {now_iso()[:10]}. "
        f"Sites: {', '.join(urls)}. Pages: {pages_note}. "
        f"Credits used: {job.get('credits_used', 0)}.*"
    )
    token = _advisory_transport_context.set(source)
    try:
        result = _save_document_to_sandbox(
            path, comparison + footer,
            rationale=f"Site comparison: {', '.join(urls)}",
        )
    finally:
        _advisory_transport_context.reset(token)
    if result.get("ok"):
        with _research_lock:
            _advisory_context_for_job('research', _research_job)
            _research_job.update(saved_path=result.get("path"), save_error=None)
            if source is not None:
                from jarvis.advisory_sources import record_advisory_job
                record_advisory_job(source, _research_job)
    else:
        with _research_lock:
            _advisory_context_for_job('research', _research_job)
            _research_job.update(save_error=result.get("error"))
            if source is not None:
                from jarvis.advisory_sources import record_advisory_job
                record_advisory_job(source, _research_job)
    return dict(result)


@app.post("/api/research/cancel")
def research_cancel() -> dict:
    if _research_busy() and _advisory_transport_context.get() is None:
        return {"ok": False, "error": "a comparison is in progress — ask for status instead"}
    with _research_lock:
        source = _advisory_transport_context.get()
        guard = _advisory_job_guards.get('research')
        if source is not None and (_research_job.get('run_id') != source.as_metadata()['action_run_id']
                or (guard is not None and guard['source'] is not None and guard['source']._action is not source._action)):
            return {'ok': True, 'already_idle': True}
        _advisory_context_for_job('research', _research_job)
        guard = _advisory_job_guards.pop('research', None)
        if guard is not None:
            guard['event'].set()
        if _research_job["state"] == "idle":
            return {"ok": True, "already_idle": True}
        _research_job.update(
            state="idle", urls=None, focus=None, sites=None, comparison=None,
            model=None, credits_used=None, error=None, started_at=None,
            finished_at=None, saved_path=None, save_error=None,
            run_id=guard['run_id'] if guard is not None and guard['source'] is not None else None,
        )
        if guard is not None and guard['source'] is not None:
            from jarvis.advisory_sources import record_advisory_job
            record_advisory_job(guard['source'], _research_job, allow_cancelled=True)
    return {"ok": True}


# --------------------------------------------------------------- memory
# Plan Phase 5e: visibility/correction surface. Thin pass-throughs over
# jarvis.memory — matching the git panel's convention above (logic lives in
# the shared module; the sidecar only adapts it to HTTP). run_migrations()
# is idempotent and mirrors mcp_git.logic._db()'s own pattern of ensuring
# the schema exists before every call, since this endpoint can be hit
# before any voice session has run migrations itself.


@app.get("/api/memory")
def memory_overview() -> dict:
    run_migrations()
    return {
        "ok": True,
        "facts": memory_module.list_facts(),
        "summary": memory_module.get_summary_text(),
        "observations": memory_module.list_observation_groups(),
        "usage": memory_module.memory_usage(),
    }


_WORKSPACE_SOURCE_TOOLS = frozenset({
    'selfedit_start', 'selfedit_status', 'selfedit_read', 'selfedit_write', 'selfedit_finish',
    'app_build_start', 'app_build_status', 'app_build_submit',
})
_workspace_preparation_lock = threading.Lock()
_workspace_preparations: dict[str, tuple] = {}


def _workspace_source_run(body, request):
    """The service credential authenticates transport, never JSON authority."""
    from jarvis.runlog.store import get_run
    from jarvis.skill_runtime import runtime_owner

    identity = request.scope.get('client_identity')
    if not auth_enabled() or identity is None or getattr(identity, 'name', None) != 'service-bot':
        raise HTTPException(status_code=403, detail='workspace source requires authenticated service-bot')
    try:
        for raw in (body.bot_session_id, body.developer_run_id):
            if str(uuid.UUID(raw)) != raw:
                raise ValueError()
        detail = get_run(body.developer_run_id)
        run = detail['run'] if type(detail) is dict else None
        role = 'app_builder' if body.workspace_kind == 'app-build' else 'developer'
        if (type(run) is not dict or run.get('agent') != role or run.get('status') != 'running'
                or run.get('user_id') != body.owner_id or run.get('session_id') != body.bot_session_id
                or runtime_owner(body.bot_session_id) != body.owner_id):
            raise ValueError()
        return run
    except Exception:
        raise HTTPException(status_code=409, detail='workspace source caller is stale') from None


def _workspace_source_arguments(body):
    import inspect
    from jarvis.privacy_policy import bounded_tool_arguments
    from mcp_servers.mcp_selfedit import logic as selfedit_logic
    from mcp_servers.mcp_apps import logic as apps_logic

    kind = 'app-build' if body.tool_name.startswith('app_') else 'selfedit'
    if body.tool_name not in _WORKSPACE_SOURCE_TOOLS or 'run_id' in body.arguments or body.workspace_kind != kind:
        raise HTTPException(status_code=403, detail='tool is outside workspace source capability')
    try:
        bounded_tool_arguments(body.tool_name, body.arguments)
        module = apps_logic if body.tool_name.startswith('app_') else selfedit_logic
        function = getattr(module, body.tool_name)
        bound = inspect.signature(function).bind(None, **body.arguments)
        bound.apply_defaults()
        values = dict(bound.arguments)
        values.pop('client')
        for key, value in values.items():
            if key in {'confirm', 'proposal'}:
                if type(value) is not bool:
                    raise ValueError()
            elif key == 'target_paths':
                if value is not None and (type(value) is not list or any(type(p) is not str for p in value)):
                    raise ValueError()
            elif value is not None and type(value) is not str:
                raise ValueError()
        if 'run_id' in values:
            values['run_id'] = body.developer_run_id
        return function, values
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(status_code=400, detail='invalid workspace source arguments') from None


def _workspace_source_context(body, run, values, *, terminal=False):
    from jarvis.development_sources import ordinary_context
    from jarvis.runlog.store import get_run

    kind = 'app-build' if body.tool_name.startswith('app_') else 'selfedit'
    service, retained, job = None, None, None
    lineage = body.developer_run_id
    if body.tool_name == 'selfedit_start' and values['confirm']:
        with _staging_lock:
            _prune_expired_stagings()
            sid = values['staging_id'].strip()
            record = _selfedit_stagings.get(sid)
            if record is None and (sid or not values['goal'].strip()) and len(_selfedit_stagings) == 1:
                sid, record = next(iter(_selfedit_stagings.items()))
            if record is not None:
                job = record.get('run_id')
                digest = hashlib.sha256(json.dumps(record, sort_keys=True, separators=(',', ':'),
                                                   allow_nan=False).encode()).hexdigest()
                lineage = sid + ':' + digest
        if job is None and (values['staging_id'] or not values['goal'].strip()):
            for lock, slot in ((_opening_lock, _opening_job), (_run_lock, _run_job)):
                with lock:
                    snapshot = dict(slot)
                if snapshot.get('action_run_id') == values['staging_id'].strip():
                    claim = get_execution_action(snapshot.get('action_scope') or _SELFEDIT_STAGED_START_ACTION_SCOPE,
                                                 snapshot['action_run_id'])
                    if claim is not None:
                        job, lineage = snapshot.get('run_id'), snapshot['action_run_id']
                        break
            if job is None:
                raise HTTPException(status_code=409, detail='workspace source lineage is unavailable')
    elif body.tool_name in {'selfedit_read', 'selfedit_write', 'selfedit_finish'}:
        service = _selfedit_service
    elif body.tool_name == 'selfedit_status':
        if values['staging_id']:
            with _staging_lock:
                record = _selfedit_stagings.get(values['staging_id'].strip())
                if record is not None:
                    job, lineage = record.get('run_id'), values['staging_id'].strip()
        if job is None:
            try:
                _selfedit_service._session()
                service = _selfedit_service
            except Exception:
                for lock, slot in ((_opening_lock, _opening_job), (_run_lock, _run_job)):
                    with lock:
                        candidate = slot.get('run_id')
                    if candidate:
                        job, lineage = candidate, candidate
                        break
    elif body.tool_name in {'app_build_status', 'app_build_submit'}:
        with _appbuild_lock:
            service, job = _appbuild_workspace, _appbuild_job.get('run_id')
        if body.tool_name == 'app_build_submit' and service is None:
            raise HTTPException(status_code=409, detail='workspace source lineage is unavailable')
    if service is not None:
        state = service._session()._read()
        job, lineage = state.get('run_id'), state.get('id')
    if job is not None:
        detail = get_run(job)
        retained = detail.get('run') if type(detail) is dict else None
        if retained is None:
            raise HTTPException(status_code=409, detail='workspace source lineage is unavailable')
    return ordinary_context(service, run, retained, workspace_kind=kind,
                            lineage_id=lineage, terminal=terminal)


def _workspace_source_cleanup(body, run, values):
    """Separate local capability for any workspace a fresh start may retire."""
    if not body.tool_name.endswith('start') or not values.get('confirm'):
        return None
    from jarvis.development_sources import ordinary_context, _host_session
    from jarvis.runlog.store import get_run
    from sandbox.runtime import Runtime
    service = _selfedit_service if body.workspace_kind == 'selfedit' else AppWorkspace(validate_app_name(values['app']))
    runtime = service._runtime()
    if type(runtime) is not Runtime:
        raise ValueError()
    record = runtime.workspaces / (runtime._key(service._repository(), service._kind) + '.json')
    try:
        record.lstat()
    except FileNotFoundError:
        return None
    session = _host_session(service)
    state = session._read()
    retained = get_run(state['run_id'])['run']
    return ordinary_context(service, run, retained, workspace_kind=body.workspace_kind,
                            lineage_id=state['id'], terminal=True)


def _same_cleanup(before, after):
    if before is None or after is None:
        return before is after
    from jarvis.development_sources import _verify_workspace_floor_pins
    _verify_workspace_floor_pins(before)
    return (before.as_metadata() == after.as_metadata() and before._identity == after._identity
            and before._pins == after._pins)


class _WorkspaceSourceClient:
    """Installed ordinary transformations over existing guarded handlers."""
    def __init__(self, scope, context, run, cleanup=None):
        self.scope, self.context, self.classified = scope, context, None
        self.start_policy = {'data_policy': scope.input_policy, 'run': run}
        self.cleanup = cleanup

    def _lifecycle(self, invoke):
        if self.context._session is None:
            return invoke()
        from sandbox.workspace import pin_source_session
        from jarvis.development_sources import _live
        _live(self.context._service, self.scope.parent_request_id, self.context, terminal=True)
        token = _workspace_lifecycle_context.set(self.context)
        try:
            with pin_source_session(self.context._service, self.context._session, self.context._identity):
                return invoke()
        finally:
            _workspace_lifecycle_context.reset(token)

    def _file(self, name, values, invoke):
        from jarvis.development_sources import dispatch_workspace_tool
        from jarvis.privacy_policy import make_tool_execution_scope, validate_tool_result
        inner = make_tool_execution_scope(self.scope.parent_request_id, self.scope.task_id,
            self.scope.tool_call_id, name, values, self.scope.input_policy)
        self.classified = dispatch_workspace_tool(_selfedit_service, name, values,
            execution_scope=inner, context=self.context, invoke=invoke)
        self.policy, content = validate_tool_result(inner, self.classified)
        return json.loads(content)

    def get(self, path, params=None):
        params = params or {}
        if path == '/api/selfedit/file':
            return self._file('file_read', {'path': params['path']}, lambda: selfedit_file(params['path']))
        if path == '/api/selfedit/models':
            return selfedit_models()
        if path == '/api/selfedit/run':
            return self._lifecycle(lambda: selfedit_run_status(**params))
        if path == '/api/appbuild/job':
            return self._lifecycle(lambda: appbuild_job_status(**params))
        raise ValueError('workspace_source_unavailable')

    def post(self, path, json=None):
        values = json or {}
        if path == '/api/selfedit/write':
            body = SelfEditWriteIn(**values)
            args = {'path': body.path, 'new_content': body.content, 'rationale': body.rationale,
                    'visual_intent': body.visual_intent, 'proposal': body.proposal}
            return self._file('edit_propose', args, lambda: selfedit_write(body))
        if path == '/api/selfedit/stage':
            return selfedit_stage(SelfEditStageIn(**values))
        if path == '/api/selfedit/run':
            token = _workspace_start_policy.set(self.start_policy)
            cleanup_token = _workspace_cleanup_context.set(self.cleanup)
            try:
                return selfedit_run(GoalIn(**values))
            finally:
                _workspace_start_policy.reset(token)
                _workspace_cleanup_context.reset(cleanup_token)
        if path == '/api/selfedit/finish':
            return self._lifecycle(selfedit_finish)
        if path == '/api/appbuild/start':
            token = _workspace_start_policy.set(self.start_policy)
            cleanup_token = _workspace_cleanup_context.set(self.cleanup)
            try:
                return appbuild_start(AppBuildGoalIn(**values))
            finally:
                _workspace_start_policy.reset(token)
                _workspace_cleanup_context.reset(cleanup_token)
        if path == '/api/appbuild/submit':
            return self._lifecycle(appbuild_submit)
        raise ValueError('workspace_source_unavailable')


def _workspace_lifecycle_result(name, values, result):
    """Explicit host reduction drops raw logs, URLs, goals and error text."""
    if type(result) is not dict or result.get('ok') is not True:
        return {'ok': False, 'error': 'development_operation_failed'}
    if name == 'selfedit_start' and not values['confirm']:
        sid = result.get('staging_id')
        with _staging_lock:
            stage = _selfedit_stagings.get(sid)
            if (type(stage) is not dict or stage.get('goal') != values['goal'].strip()
                    or stage.get('run_id') != values['run_id']):
                return {'ok': False, 'error': 'development_operation_failed'}
        return result  # Exact installed caller-input/profile/allowlist preview.
    if name == 'app_build_start' and not values['confirm']:
        return result  # Pure caller-input preview; no acquired application data.
    reduced = {'ok': True}
    for key in ('started', 'opening', 'duplicate', 'needs_confirmation', 'active',
                'staging_found', 'already_submitted', 'reconciliation_required'):
        if type(result.get(key)) is bool:
            reduced[key] = result[key]
    states = {'idle', 'starting', 'ready', 'running', 'validating', 'submitting', 'done',
              'error', 'cancelled', 'completed', 'failed', 'unknown', 'recovered'}
    state = result.get('state')
    for key in ('opening', 'finish', 'job'):
        if type(result.get(key)) is dict and result[key].get('state') in states:
            state = result[key]['state']
            if state not in {'idle', 'done'}:
                break
    if state in states:
        reduced['state'] = state
    for key in ('action_run_id', 'submission_id'):
        value = result.get(key)
        if type(value) is str and re.fullmatch(r'(?:[0-9a-f]{12}|[0-9a-f]{32}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})', value):
            reduced[key] = value
    if result.get('session') or (name == 'selfedit_status' and result.get('active')):
        reduced['session_open'] = True
    if reduced.get('reconciliation_required') or state == 'unknown':
        reduced['summary'] = 'The outcome is unresolved. Check this action again; do not retry automatically.'
    elif name in {'selfedit_start', 'selfedit_status'} and reduced.get('session_open'):
        reduced['summary'] = 'The isolated session is open. Read each file, write the approved change, then call selfedit_finish.'
    elif name == 'selfedit_finish':
        reduced['summary'] = 'Validation and draft submission are being checked. Ask for self-edit status; merging stays with you.'
    elif name == 'app_build_submit':
        reduced['summary'] = 'Draft submission is being checked. Ask for app-build status; merging stays with you.'
    else:
        reduced['summary'] = 'The development lifecycle state is available. Check status before another operation.'
    return reduced


@app.post('/api/development/source/associate')
def associate_workspace_source(body: WorkspaceSourceAssociationIn, request: Request) -> dict:
    _workspace_source_run(body, request)
    from jarvis.development_attestation import ensure_admin_source_authority
    ensure_admin_source_authority()
    _workspace_source_run(body, request)
    return {'ok': True}


@app.post('/api/development/source/prepare')
def prepare_workspace_source(body: WorkspaceSourcePrepareIn, request: Request) -> dict:
    run = _workspace_source_run(body, request)
    _, values = _workspace_source_arguments(body)
    try:
        from jarvis.development_sources import retain_workspace_floor
        from jarvis.privacy_policy import DataPolicy
        retain_workspace_floor(run, DataPolicy(body.source_input_policy, 'workspace-caller-floor'))
        context = _workspace_source_context(body, run, values, terminal=body.tool_name.endswith(('status', 'finish', 'submit')))
        cleanup = _workspace_source_cleanup(body, run, values)
        _workspace_source_run(body, request)
        import secrets
        key = secrets.token_hex(32)
        with _workspace_preparation_lock:
            now = time.monotonic()
            for prior, record in list(_workspace_preparations.items()):
                if now - record[0] >= 60:
                    _workspace_preparations.pop(prior, None)
            if len(_workspace_preparations) >= 4096:
                raise ValueError()
            _workspace_preparations[key] = (now, body.model_dump(), context, cleanup)
        return {'ok': True, 'source_context': context.as_metadata(), 'source_preparation_id': key}
    except Exception:
        raise HTTPException(status_code=409, detail='workspace source context is unavailable') from None


@app.post('/api/development/source/tool')
def execute_workspace_source(body: WorkspaceSourceToolIn, request: Request) -> dict:
    from jarvis.development_attestation import sign_workspace_source
    from jarvis.development_sources import ordinary_context, _verify_workspace_floor_pins, published_workspace_result
    from jarvis.privacy_policy import DataPolicy, issue_tool_result, make_tool_execution_scope, strictest, validate_tool_result
    from jarvis.tenant import user_id_scope

    run = _workspace_source_run(body, request)
    function, values = _workspace_source_arguments(body)
    terminal = body.tool_name.endswith(('status', 'finish', 'submit'))
    try:
        with _workspace_preparation_lock:
            prepared = _workspace_preparations.pop(body.source_preparation_id, None)
        binding = body.model_dump(exclude={'source_context', 'source_preparation_id'})
        if prepared is None or not 0 <= time.monotonic() - prepared[0] < 60 or binding != prepared[1]:
            raise ValueError()
        context = prepared[2]
        _verify_workspace_floor_pins(context)
        current_context = _workspace_source_context(body, run, values, terminal=terminal)
        cleanup = _workspace_source_cleanup(body, run, values)
        if not _same_cleanup(prepared[3], cleanup):
            raise ValueError()
        if (context.as_metadata() != body.source_context or current_context.as_metadata() != body.source_context
                or current_context._identity != context._identity or current_context._pins != context._pins):
            raise ValueError()
        # A host acquisition can strengthen a run after preparation. The
        # current verified floor must precede admission of any guest bytes.
        context = current_context
        scope = make_tool_execution_scope(body.developer_run_id, body.source_task_id, body.source_tool_call_id,
            body.tool_name, body.arguments, strictest(context.input_floor,
                cleanup.input_floor if cleanup is not None else context.input_floor,
                DataPolicy(body.source_input_policy, 'workspace-caller-floor')))
        from jarvis.development_sources import retain_workspace_floor
        retain_workspace_floor(run, scope.input_policy)
        retained_id = context.as_metadata().get('sandbox_job_id')
        if retained_id and retained_id != run['run_id']:
            from jarvis.runlog.store import get_run
            retained = get_run(retained_id)['run']
            if retained['user_id'] != run['user_id'] or retained['session_id'] != run['session_id']:
                raise ValueError()
            retain_workspace_floor(retained, scope.input_policy)
        if cleanup is not None:
            from jarvis.runlog.store import get_run
            retain_workspace_floor(get_run(cleanup.as_metadata()['sandbox_job_id'])['run'], scope.input_policy)
            cleanup = _workspace_source_cleanup(body, run, values)
        # Only the just-issued restriction update may add a missing floor
        # record. Re-pin that actual host journal before the installed tool.
        admitted = _workspace_source_context(body, run, values, terminal=terminal)
        if (admitted.as_metadata() != context.as_metadata() or admitted._identity != context._identity
                or admitted._pins != context._pins):
            raise ValueError()
        context = admitted
        client = _WorkspaceSourceClient(scope, context, run, cleanup)
        with user_id_scope(run['user_id']):
            result = function(client, **values)
        from jarvis.development_sources import refresh_workspace_floor
        latest_floor = refresh_workspace_floor(context)
        policy, source_scope, refs = strictest(context.input_floor, latest_floor), 'workspace-generated-lifecycle', ()
        if client.classified is not None:
            policy = strictest(policy, client.policy)
            source_scope, refs = client.classified.source_scope, client.classified.canonical_refs
        else:
            result = _workspace_lifecycle_result(body.tool_name, values, result)
        policy = strictest(policy, *(value for value in client.start_policy.values() if type(value) is DataPolicy))
        current_run = _workspace_source_run(body, request)
        if body.tool_name == 'selfedit_start':
            if values['confirm'] and result.get('ok'):
                expected_job = context.as_metadata().get('sandbox_job_id', body.developer_run_id)
                with _opening_lock, _run_lock:
                    if not any(slot.get('run_id') == expected_job for slot in (_opening_job, _run_job)):
                        raise ValueError()
            after = ordinary_context(None, current_run, workspace_kind='selfedit',
                                     lineage_id=context.as_metadata()['lineage_id'])
        else:
            after = _workspace_source_context(body, current_run, values, terminal=terminal)
            if after.as_metadata() != context.as_metadata():
                raise ValueError()
        policy = strictest(policy, after.input_floor)
        if (result.get('ok') is True and context._session is not None
                and body.tool_name in {'selfedit_status', 'selfedit_finish', 'app_build_status', 'app_build_submit'}):
            metadata = context.as_metadata()
            identities = {'selfedit_status': ('action_run_id', 'sandbox_session_id'),
                          'app_build_status': ('submission_id', 'sandbox_session_id')}
            selected = identities.get(body.tool_name)
            same = selected is None or not values.get(selected[0]) or values[selected[0]] == metadata.get(selected[1])
            if body.tool_name == 'app_build_status' and values.get('action_run_id'):
                same = same and values['action_run_id'] == metadata.get('sandbox_job_id')
            if same:
                published = published_workspace_result(context._service, execution_scope=scope, context=context)
                if published is not None:
                    pub_policy, pub_content = validate_tool_result(scope, published)
                    handle = json.loads(pub_content)
                    result.update(pr_url=handle['pr_url'], pr_number=handle['pr_number'], commit=handle['commit'])
                    result['summary'] = ('Draft pull request: ' + handle['pr_url'] + '. '
                        'Review it on GitHub; approval and merging remain with you.')
                    if handle.get('human_only') is True:
                        result['human_only'] = True
                        result['summary'] = ('Human-only proposal: ' + handle['pr_url'] + '. '
                            'Ask Larry to approve and apply it himself; do not merge this proposal as it is.')
                    policy = strictest(policy, pub_policy)
                    refs += published.canonical_refs
        classified = issue_tool_result(scope, json.dumps(result, sort_keys=True, separators=(',', ':'),
            ensure_ascii=True, allow_nan=False), policy, source_scope, refs)
        receipt = sign_workspace_source(scope, classified, context=context.as_metadata(), challenge=body.source_challenge)
        _workspace_source_run(body, request)
        if client.classified is not None:
            final = _workspace_source_context(body, current_run, values, terminal=terminal)
            if final.as_metadata() != context.as_metadata():
                raise ValueError()
        return {'ok': True, 'source_receipt': receipt}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=409, detail='workspace source binding changed') from None


_advisory_preparations = {}
_advisory_preparation_lock = threading.RLock()


def _advisory_source_run(body, request, *, terminal=False):
    from jarvis.advisory_sources import kind_for_tool
    from jarvis.runlog.store import get_run
    from jarvis.skill_runtime import runtime_owner
    if not auth_enabled() or request.scope.get('client_identity') is None or request.scope['client_identity'].name != 'service-bot':
        raise HTTPException(status_code=403, detail='advisory source requires authenticated service bot')
    kind = kind_for_tool(body.tool_name)
    expected = 'developer' if kind == 'planning' else 'analyst'
    detail = get_run(body.caller_run_id)
    run = detail.get('run') if type(detail) is dict else None
    if (type(run) is not dict or run.get('agent') != expected or body.caller_agent != expected
            or run.get('user_id') != body.owner_id or run.get('session_id') != body.bot_session_id
            or (not terminal and run.get('status') != 'running')
            or runtime_owner(body.bot_session_id) != body.owner_id):
        raise HTTPException(status_code=409, detail='advisory source caller changed')
    return run


def _advisory_source_arguments(body):
    import inspect
    from jarvis.privacy_policy import bounded_tool_arguments
    from mcp_servers.mcp_selfedit import logic as plan_logic
    from mcp_servers.mcp_web import logic as web_logic
    bounded_tool_arguments(body.tool_name, body.arguments)
    module = plan_logic if body.tool_name.startswith('plan_') else web_logic
    function = getattr(module, body.tool_name)
    bound = inspect.signature(function).bind(None, **body.arguments)
    bound.apply_defaults()
    values = dict(bound.arguments)
    values.pop('client')
    for key, value in values.items():
        if key == 'confirm':
            if type(value) is not bool:
                raise ValueError()
        elif key == 'urls':
            if type(value) is not list or any(type(url) is not str for url in value):
                raise ValueError()
        elif value is not None and type(value) is not str:
            raise ValueError()
    if body.tool_name in {'plan_start', 'research_compare_start'}:
        if 'run_id' in body.arguments:
            raise ValueError()
        values['run_id'] = body.caller_run_id
    if body.tool_name == 'plan_start' and (values['mode'] != 'single' or values['review_path']):
        raise HTTPException(status_code=409, detail='advisory nested or review sponsorship is unavailable')
    return function, values


def _advisory_scope(body):
    from jarvis.privacy_policy import make_tool_execution_scope, DataPolicy
    return make_tool_execution_scope(body.caller_run_id, body.task_id, body.tool_call_id,
        body.tool_name, body.arguments, DataPolicy(body.input_policy, 'advisory-caller-floor'))


def _advisory_binding(body):
    return body.model_dump(exclude={'challenge', 'preparation_id', 'source_context'})


class _AdvisorySourceClient:
    def __init__(self, context):
        self.context = context

    def _check(self, kind):
        from jarvis.advisory_sources import verify_advisory_job
        _, slot = _advisory_slot(kind)
        verify_advisory_job(self.context, slot)

    def get(self, path, params=None):
        params = params or {}
        kind = 'planning' if path == '/api/plan/job' else 'research'
        self._check(kind)
        target = self.context.as_metadata()['action_run_id']
        if params.get('run_id') and params['run_id'] != target:
            raise ValueError()
        if path == '/api/plan/job':
            return plan_job_status(target)
        if path == '/api/research/job':
            return research_job_status(target)
        raise ValueError()

    def post(self, path, json=None):
        values = json or {}
        if path == '/api/plan/start':
            return plan_start(PlanStartIn(**values))
        if path == '/api/research/start':
            return research_start(ResearchStartIn(**values))
        kind = 'planning' if path.startswith('/api/plan/') else 'research'
        self._check(kind)
        if path == '/api/plan/choose':
            return plan_choose(PlanChooseIn(**values))
        if path == '/api/plan/adopt':
            return plan_adopt(PlanAdoptIn(**values))
        if path == '/api/research/save':
            return research_save(ResearchSaveIn(**values))
        raise ValueError()


@app.post('/api/advisory/source/associate')
def associate_advisory_source(body: AdvisorySourceIn, request: Request) -> dict:
    _advisory_source_run(body, request)
    from jarvis.development_attestation import ensure_admin_source_authority
    ensure_admin_source_authority()
    _advisory_source_run(body, request)
    return {'ok': True}


@app.post('/api/advisory/source/prepare')
def prepare_advisory_source(body: AdvisorySourceIn, request: Request) -> dict:
    from jarvis import advisory_sources as sources
    from jarvis.development_attestation import sign_advisory_source
    from jarvis.tenant import user_id_scope
    run = _advisory_source_run(body, request)
    try:
        _, values = _advisory_source_arguments(body)
        scope = _advisory_scope(body)
        with user_id_scope(run['user_id']):
            if body.tool_name in {'plan_start', 'research_compare_start'}:
                context = sources.prepare_advisory_source(scope, run,
                    owner_scope_id=body.owner_scope_id, child_scope_id=body.child_scope_id)
            else:
                if body.owner_scope_id is not None or body.child_scope_id is not None:
                    raise ValueError()
                _, slot = _advisory_slot(sources.kind_for_tool(body.tool_name))
                context = sources.retained_advisory_source(scope, run, slot)
                requested = values.get('action_run_id') if body.tool_name == 'plan_status' else values.get('run_id')
                if requested and requested != context.as_metadata()['action_run_id']:
                    raise ValueError()
        key = uuid.uuid4().hex + uuid.uuid4().hex
        value = {'ok': True, 'preparation_id': key, 'source_context': context.as_metadata()}
        envelope = sources.issue_advisory_result(scope, context, value, pending=True)
        receipt = sign_advisory_source(scope, envelope, context=context.as_metadata(),
            challenge=body.challenge, phase='prepare')
        _advisory_source_run(body, request)
        with _advisory_preparation_lock:
            now = time.monotonic()
            for old, entry in list(_advisory_preparations.items()):
                if now - entry['created_at'] > 600:
                    _advisory_preparations.pop(old, None)
            if len(_advisory_preparations) >= 4096:
                raise ValueError()
            _advisory_preparations[key] = {'created_at': now, 'binding': _advisory_binding(body),
                                         'context': context, 'used': False}
        return {**value, 'source_receipt': receipt}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=409, detail='advisory source binding changed') from None


def _prepared_advisory(body, *, consume):
    with _advisory_preparation_lock:
        entry = _advisory_preparations.get(body.preparation_id)
        if (entry is None or entry['binding'] != _advisory_binding(body)
                or entry['context'].as_metadata() != body.source_context
                or not 0 <= time.monotonic() - entry['created_at'] < 600
                or (consume and entry['used'])):
            raise ValueError()
        if consume:
            entry['used'] = True
        return entry['context']


@app.post('/api/advisory/source/tool')
def execute_advisory_source(body: AdvisorySourceIn, request: Request) -> dict:
    from jarvis import advisory_sources as sources
    from jarvis.development_attestation import sign_advisory_source
    from jarvis.tenant import user_id_scope
    run = _advisory_source_run(body, request)
    try:
        context = _prepared_advisory(body, consume=True)
        function, values = _advisory_source_arguments(body)
        scope = _advisory_scope(body)
        with user_id_scope(run['user_id']):
            context = sources.refresh_advisory_source(context, run)
            if context.cancel_event.is_set():
                raise ValueError()
            if body.tool_name == 'research_status':
                values['run_id'] = context.as_metadata()['action_run_id']
            token = _advisory_transport_context.set(context)
            try:
                value = function(_AdvisorySourceClient(context), **values)
            finally:
                _advisory_transport_context.reset(token)
            if type(value) is not dict or value.get('ok') is not True:
                value = {'ok': False, 'error': 'advisory_operation_failed'}
            pending = body.tool_name in {'plan_start', 'research_compare_start'}
            envelope = sources.issue_advisory_result(scope, context, value, pending=pending)
        _advisory_source_run(body, request)
        return {'ok': True, 'source_receipt': sign_advisory_source(scope, envelope,
            context=context.as_metadata(), challenge=body.challenge, phase='execute')}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=409, detail='advisory source binding changed') from None


@app.post('/api/advisory/source/cancel')
def cancel_advisory_source(body: AdvisorySourceIn, request: Request) -> dict:
    from jarvis import advisory_sources as sources
    from jarvis.development_attestation import sign_advisory_source
    from jarvis.tenant import user_id_scope
    run = _advisory_source_run(body, request, terminal=True)
    try:
        if body.tool_name not in {'plan_start', 'research_compare_start'}:
            raise ValueError()
        context = _prepared_advisory(body, consume=False)
        sources.cancel_advisory_source(context)
        kind = sources.kind_for_tool(body.tool_name)
        lock, slot = _advisory_slot(kind)
        with user_id_scope(run['user_id']):
            with lock:
                owns_slot = (context._action.slot is slot and sources._active.get(kind) is context._action
                    and slot.get('run_id') == context.as_metadata()['action_run_id'])
            if owns_slot:
                token = _advisory_transport_context.set(context)
                try:
                    plan_cancel() if kind == 'planning' else research_cancel()
                finally:
                    _advisory_transport_context.reset(token)
            scope = _advisory_scope(body)
            envelope = sources.issue_advisory_result(scope, context, {'ok': True, 'cancelled': True,
                'action_run_id': context.as_metadata()['action_run_id']}, pending=True)
        _advisory_source_run(body, request, terminal=True)
        return {'ok': True, 'source_receipt': sign_advisory_source(scope, envelope,
            context=context.as_metadata(), challenge=body.challenge, phase='cancel')}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=409, detail='advisory source binding changed') from None


@app.post("/api/skills/runtime-inventory")
def skills_runtime_inventory(body: SkillRuntimeInventoryIn, request: Request) -> dict:
    """Accept a fresh inventory only from Mortimer's service-bot token.

    This records discovered tools, never tool-call success or package/provider
    readiness. The receipt is held in process memory and expires quickly.
    """
    if not auth_enabled():
        raise HTTPException(status_code=503, detail="runtime evidence requires bearer authentication")
    identity = request.scope.get("client_identity")
    if identity is None:
        raise HTTPException(status_code=503, detail="authenticated identity is unavailable")
    if getattr(identity, "name", None) != "service-bot":
        raise HTTPException(status_code=403, detail="runtime evidence requires the service-bot identity")
    if body.schema_version != 1:
        raise HTTPException(status_code=400, detail="unsupported runtime inventory schema")
    from jarvis.skill_runtime import update_runtime_inventory

    try:
        update_runtime_inventory(
            body.runtime_id, body.tools, body.complete,
            active=body.active, owner_id=body.owner_id,
        )
    except ValueError as exc:
        if str(exc) == "runtime_capacity_exceeded":
            raise HTTPException(status_code=503, detail="runtime inventory capacity is full") from None
        raise HTTPException(status_code=400, detail="invalid runtime inventory") from None
    return {"ok": True}


def _creator_internal_owner(body, request: Request) -> dict:
    """Authorize a service-bot call against the owner-bound live session."""
    if not auth_enabled():
        raise HTTPException(status_code=503, detail="creator dispatch requires bearer authentication")
    identity = request.scope.get("client_identity")
    if identity is None or getattr(identity, "name", None) != "service-bot":
        raise HTTPException(status_code=403, detail="creator capability requires service-bot identity")
    from jarvis.skill_creator_agent import CREATOR_PACKAGE_REVISION
    if body.creator_revision != CREATOR_PACKAGE_REVISION:
        raise HTTPException(status_code=409, detail="creator package revision changed")
    try:
        session_uuid = uuid.UUID(body.bot_session_id)
        request_uuid = uuid.UUID(body.request_id)
        run_uuid = uuid.UUID(body.developer_run_id)
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(status_code=400, detail="creator identity is invalid") from None
    if any(str(value) != raw for value, raw in (
        (session_uuid, body.bot_session_id),
        (request_uuid, body.request_id),
        (run_uuid, body.developer_run_id),
    )):
        raise HTTPException(status_code=400, detail="creator identity is invalid")
    from jarvis.skill_runtime import runtime_owner
    if runtime_owner(body.bot_session_id) != body.owner_id:
        raise HTTPException(status_code=409, detail="creator session is stale or belongs to another owner")
    from jarvis.skill_requests import get as get_skill_request
    try:
        state = get_skill_request(body.owner_id, body.request_id)
    except Exception:
        state = None
    if (not state or state.get("operation") != "draft"
            or state.get("bot_session_id") != body.bot_session_id):
        raise HTTPException(status_code=404, detail="creator request is unavailable")
    return state


def _verify_developer_run(body, *, require_running: bool = True) -> dict:
    from jarvis.runlog.store import get_run
    detail = get_run(body.developer_run_id)
    run = detail.get("run") if isinstance(detail, dict) else None
    if (not run or run.get("agent") != "developer"
            or run.get("user_id") != body.owner_id
            or run.get("session_id") != body.bot_session_id
            or (require_running and run.get("status") != "running")):
        raise HTTPException(status_code=409, detail="creator Developer run does not match this request")
    return run


@app.post("/api/skills/creator/associate")
def associate_skill_creator_run(body: SkillCreatorAssociationIn, request: Request) -> dict:
    """Durably bind only a RunLogger-created Developer run to a creator job."""
    _creator_internal_owner(body, request)
    _verify_developer_run(body)
    from jarvis.skill_requests import SkillRequestError, associate_developer_run
    try:
        associate_developer_run(
            body.owner_id, body.request_id,
            session_id=body.bot_session_id, run_id=body.developer_run_id,
            creator_revision=body.creator_revision,
        )
    except SkillRequestError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from None
    result = {"ok": True, "developer_run_id": body.developer_run_id}
    if body.source_authority:
        from jarvis.development_attestation import ensure_admin_source_authority
        from jarvis.development_sources import creator_context
        from jarvis.skill_requests import _service

        state = _creator_internal_owner(body, request)
        run = _verify_developer_run(body)
        if state.get("cancel_requested"):
            raise HTTPException(status_code=409, detail="creator request is cancelling")
        try:
            source_context = creator_context(
                _service(state["skill_id"], expected_job_id=state["sandbox_job_id"]), state, run,
            )
            ensure_admin_source_authority()
            result["source_context"] = source_context.as_metadata()
        except Exception:
            raise HTTPException(status_code=503, detail="creator source authority is unavailable") from None
    return result


@app.post("/api/skills/creator/tool")
def execute_skill_creator_tool(body: SkillCreatorToolIn, request: Request) -> dict:
    """Execute one of the four creator tools for its exact live run/job pair."""
    from jarvis.skill_requests import _service

    state = _creator_internal_owner(body, request)
    if (state.get("developer_run_id") != body.developer_run_id
            or state.get("creator_revision") != body.creator_revision):
        raise HTTPException(status_code=409, detail="creator tool is not bound to this Developer run")
    run = _verify_developer_run(body)
    if state.get("cancel_requested"):
        raise HTTPException(status_code=409, detail="creator request is cancelling")
    tool = body.tool_name
    args = body.arguments
    service = _service(state["skill_id"], expected_job_id=state["sandbox_job_id"])
    live = service.status()
    if live.get("run_id") != state.get("sandbox_job_id"):
        raise HTTPException(status_code=409, detail="creator sandbox job changed")
    def invoke() -> dict:
        if tool == "file_read":
            if set(args) != {"path"} or not isinstance(args.get("path"), str):
                raise HTTPException(status_code=400, detail="invalid creator tool arguments")
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
                raise HTTPException(status_code=400, detail="invalid creator tool arguments")
            result = service.propose_edit(
                args["path"], args["new_content"], args.get("rationale", ""),
                args.get("visual_intent", ""),
            )
        elif tool == "session_validate":
            if args:
                raise HTTPException(status_code=400, detail="invalid creator tool arguments")
            result = service.validate()
        elif tool == "session_decline":
            if set(args) != {"reason"} or not isinstance(args.get("reason"), str) or len(args["reason"]) > 2000:
                raise HTTPException(status_code=400, detail="invalid creator tool arguments")
            from jarvis.skill_requests import update as update_skill_request
            update_skill_request(
                body.owner_id, body.request_id, state="draft_needs_attention",
                result_code="creator_declined",
            )
            result = {"ok": False, "declined": True, "reason": args["reason"]}
        else:
            raise HTTPException(status_code=403, detail="tool is outside the creator capability")
        if not isinstance(result, dict):
            raise HTTPException(status_code=502, detail="creator tool returned an invalid result")
        return result

    source_fields = (body.source_challenge, body.source_task_id,
                     body.source_tool_call_id, body.source_input_policy)
    if not any(value is not None for value in source_fields):
        return {"ok": True, "result": invoke()}
    if any(value is None for value in source_fields):
        raise HTTPException(status_code=400, detail="invalid creator source binding")
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
        current = _creator_internal_owner(body, request)
        current_run = _verify_developer_run(body)
        after_live = service.status()
        if (current.get("cancel_requested")
                or current.get("developer_run_id") != body.developer_run_id
                or current.get("creator_revision") != body.creator_revision
                or current.get("sandbox_job_id") != state.get("sandbox_job_id")
                or after_live.get("run_id") != state.get("sandbox_job_id")):
            raise HTTPException(status_code=409, detail="creator source binding changed")
        after_context = creator_context(service, current, current_run)
        if after_context.as_metadata() != source_context.as_metadata():
            raise HTTPException(status_code=409, detail="creator source binding changed")
        policy, content = validate_tool_result(source_scope, classified)
        classified = issue_tool_result(
            source_scope, content, strictest(policy, after_context.input_floor),
            classified.source_scope, classified.canonical_refs,
        )
        from jarvis.skill_requests import _paths
        import fcntl
        import stat

        _, lock_path = _paths(body.owner_id, body.request_id)
        descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        with os.fdopen(descriptor, "a") as lock:
            metadata = os.fstat(lock.fileno())
            if (not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid()
                    or stat.S_IMODE(metadata.st_mode) != 0o600 or metadata.st_nlink != 1):
                raise HTTPException(status_code=409, detail="creator source binding changed")
            fcntl.flock(lock, fcntl.LOCK_EX)
            final_state = _creator_internal_owner(body, request)
            _verify_developer_run(body)
            if (final_state.get("cancel_requested")
                    or any(final_state.get(key) != current.get(key) for key in (
                        "bot_session_id", "developer_run_id", "creator_revision", "skill_id",
                        "sandbox_job_id", "sandbox_session_id", "sandbox_task_id", "source_commit",
                    ))):
                raise HTTPException(status_code=409, detail="creator source binding changed")
            # The long workspace operation and source snapshot ran before
            # this lock. A cancellation/request replacement cannot race the
            # final durable check and receipt signature.
            receipt = sign_tool_source(source_scope, classified, context=source_context.as_metadata(),
                                       challenge=body.source_challenge)
        return {"ok": True, "source_receipt": receipt}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=409, detail="creator source receipt could not be verified") from None


@app.get("/api/skills")
def skills_catalog(cursor: str = "", limit: int = 50) -> dict:
    """Read-only, bounded inventory for the native Skills workspace."""
    from jarvis.skill_catalog import list_catalog
    from jarvis.skill_service import assess_current_readiness, configured_tool_inventory
    from jarvis.skill_requests import authoring_available

    if len(cursor) > 12 or (cursor and not cursor.isdecimal()):
        raise HTTPException(status_code=400, detail="invalid catalog cursor")
    if not 1 <= limit <= 100:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 100")
    entries = list_catalog()
    tool_inventory = configured_tool_inventory()
    catalog_revision = hashlib.sha256("\n".join(
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


def _skill_request_owner(request: Request) -> str:
    identity = request.scope.get("client_identity")
    if not auth_enabled():
        raise HTTPException(status_code=503, detail="Skills requests require bearer authentication")
    if identity is not None and isinstance(getattr(identity, "user_id", None), str):
        return identity.user_id
    # A new request route must never collapse an authenticated caller into the
    # legacy process-wide `local` tenant.
    raise HTTPException(status_code=503, detail="authenticated identity is unavailable")


def _skill_activity_owner(request: Request) -> str:
    """Resolve read-API tenancy from the authenticated caller, never process state."""
    if not auth_enabled():
        return current_user_id()
    identity = request.scope.get("client_identity")
    user_id = getattr(identity, "user_id", None)
    if isinstance(user_id, str) and user_id:
        return user_id
    # The bearer middleware normally rejects or annotates every authenticated
    # request. Fail closed if an embedding bypasses that contract; falling back
    # to JARVIS_USER_ID could expose another tenant's run activity.
    raise HTTPException(status_code=503, detail="authenticated identity is unavailable")


def _validated_skill_request(payload: SkillRequestIn) -> dict:
    from jarvis.skill_catalog import SLUG

    values = payload.model_dump() if hasattr(payload, "model_dump") else payload.dict()
    if type(values["schema_version"]) is not int or values["schema_version"] != 1:
        raise HTTPException(status_code=400, detail="unsupported Skills request schema")
    try:
        parsed = uuid.UUID(values["request_id"])
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(status_code=400, detail="invalid request identifier") from None
    if str(parsed) != values["request_id"]:
        raise HTTPException(status_code=400, detail="invalid request identifier")
    if not SLUG.fullmatch(values["skill_id"]):
        raise HTTPException(status_code=400, detail="invalid skill identifier")
    for field in ("expected_catalog_revision",):
        if not isinstance(values[field], str) or not re.fullmatch(r"[0-9a-f]{64}", values[field]):
            raise HTTPException(status_code=400, detail=f"invalid {field}")
    if values["skill_revision"] is not None and not re.fullmatch(r"[0-9a-f]{64}", values["skill_revision"]):
        raise HTTPException(status_code=400, detail="invalid skill revision")
    if values["privacy_context"] not in {"standard", "protected"}:
        raise HTTPException(status_code=400, detail="invalid privacy context")
    operation = values["operation"]
    allowed = {"draft", "test", "request_publish", "request_activation", "request_rollback", "cancel"}
    if operation not in allowed:
        raise HTTPException(status_code=400, detail="unsupported Skills operation")
    base_fields = {"schema_version", "operation", "request_id", "bot_session_id", "expected_catalog_revision",
                   "skill_id", "skill_revision", "privacy_context"}
    operation_fields = {
        "draft": {"task_brief"},
        "test": {"example_ids", "scope", "route_policy_ref", "budget", "job_id"},
        "request_activation": {"review_artifact_ref"},
        "request_rollback": {"review_artifact_ref"},
        "request_publish": {"review_artifact_ref", "candidate_digest"},
        "cancel": {"job_id"},
    }[operation]
    if any(values.get(key) is not None for key in (set(values) - base_fields - operation_fields)):
        raise HTTPException(status_code=400, detail="fields are not valid for this Skills operation")
    required = {
        "draft": ("task_brief", "bot_session_id"), "test": ("example_ids", "scope", "job_id"),
        "request_activation": ("skill_revision", "review_artifact_ref"),
        "request_rollback": ("skill_revision", "review_artifact_ref"),
        "request_publish": ("skill_revision", "review_artifact_ref", "candidate_digest"),
        "cancel": ("job_id",),
    }[operation]
    if any(values.get(field) is None for field in required):
        raise HTTPException(status_code=400, detail="missing operation fields")
    if operation == "draft":
        try:
            session_id = str(uuid.UUID(values["bot_session_id"]))
        except (ValueError, TypeError, AttributeError):
            raise HTTPException(status_code=400, detail="invalid bot session identifier") from None
        if session_id != values["bot_session_id"]:
            raise HTTPException(status_code=400, detail="invalid bot session identifier")
        brief = values["task_brief"]
        if not isinstance(brief, str) or not brief.strip() or len(brief) > 8000:
            raise HTTPException(status_code=400, detail="task brief must contain 1–8,000 characters")
    if operation == "test":
        ids = values["example_ids"]
        if (not isinstance(ids, list) or not 1 <= len(ids) <= 32
                or any(not isinstance(item, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", item) for item in ids)
                or len(set(ids)) != len(ids)):
            raise HTTPException(status_code=400, detail="invalid reviewed example IDs")
        if values["scope"] not in {"offline", "live"}:
            raise HTTPException(status_code=400, detail="invalid test scope")
        try:
            job = uuid.UUID(values["job_id"])
        except (ValueError, TypeError, AttributeError):
            raise HTTPException(status_code=400, detail="invalid authoring job identifier") from None
        if str(job) != values["job_id"]:
            raise HTTPException(status_code=400, detail="invalid authoring job identifier")
        if values.get("route_policy_ref") is not None and not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{0,63}", values["route_policy_ref"]):
            raise HTTPException(status_code=400, detail="invalid route policy reference")
        budget = values.get("budget")
        if budget is not None and (set(budget) - {"max_calls", "max_seconds"}
                                   or any(type(v) is not int or v < 1 for v in budget.values())):
            raise HTTPException(status_code=400, detail="invalid test budget")
    if operation in {"request_activation", "request_rollback"}:
        if not re.fullmatch(r"[0-9a-f]{64}", values["skill_revision"]):
            raise HTTPException(status_code=400, detail="invalid reviewed revision")
        try:
            ref = uuid.UUID(values["review_artifact_ref"])
        except (ValueError, TypeError, AttributeError):
            raise HTTPException(status_code=400, detail="invalid review artifact reference") from None
        if str(ref) != values["review_artifact_ref"]:
            raise HTTPException(status_code=400, detail="invalid review artifact reference")
    if operation == "request_publish":
        if (not re.fullmatch(r"[0-9a-f]{64}", values["skill_revision"])
                or not re.fullmatch(r"[0-9a-f]{64}", values["candidate_digest"])):
            raise HTTPException(status_code=400, detail="invalid reviewed candidate digest")
        try:
            ref = uuid.UUID(values["review_artifact_ref"])
        except (ValueError, TypeError, AttributeError):
            raise HTTPException(status_code=400, detail="invalid review artifact reference") from None
        if str(ref) != values["review_artifact_ref"]:
            raise HTTPException(status_code=400, detail="invalid review artifact reference")
    if operation == "cancel":
        try:
            job = uuid.UUID(values["job_id"])
        except (ValueError, TypeError, AttributeError):
            raise HTTPException(status_code=400, detail="invalid job identifier") from None
        if str(job) != values["job_id"]:
            raise HTTPException(status_code=400, detail="invalid job identifier")
    # Bound total serialized request size, including optional fields.
    if len(json.dumps(values, ensure_ascii=False).encode("utf-8")) > 256 * 1024:
        raise HTTPException(status_code=413, detail="Skills request exceeds 256 KiB")
    return values


@app.post("/api/skills/requests", status_code=202)
def create_skill_request(payload: SkillRequestIn, request: Request) -> dict:
    """Start/reconcile a bounded Skills operation under the bearer owner."""
    from jarvis.skill_catalog import list_catalog
    from jarvis.skill_requests import (
        SkillRequestError, cancel_job, get as get_skill_job, start_draft,
        start_offline_validation, start_publish,
    )

    values = _validated_skill_request(payload)
    owner = _skill_request_owner(request)
    if values["privacy_context"] == "protected":
        raise HTTPException(status_code=409, detail="protected requests cannot be persisted in a sandbox workspace")
    entries = list_catalog()
    catalog_revision = hashlib.sha256("\n".join(
        f"{item.skill_id}:{item.revision or 'invalid'}:{int(item.enabled)}" for item in entries
    ).encode("utf-8")).hexdigest()
    if (values["operation"] != "cancel"
            and values["expected_catalog_revision"] != catalog_revision):
        raise HTTPException(status_code=409, detail="Skills catalog changed; refresh before retrying")
    current = next((item for item in entries if item.skill_id == values["skill_id"]), None)
    if values["operation"] == "draft":
        if current and current.installation == "installed" and values["skill_revision"] != current.revision:
            raise HTTPException(status_code=409, detail="existing skill revision changed; refresh before drafting")
        try:
            from jarvis.skill_runtime import runtime_owner

            if runtime_owner(values["bot_session_id"]) != owner:
                raise HTTPException(
                    status_code=409,
                    detail="creator requests require the caller's active Mortimer session",
                )
            job, created = start_draft(owner, values)
        except SkillRequestError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from None
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
            raise HTTPException(status_code=404, detail="skill is unavailable")
    elif current is None and values["operation"] not in {"request_publish", "request_activation", "request_rollback", "cancel"}:
        raise HTTPException(status_code=404, detail="skill is unavailable")
    if (values["operation"] != "request_publish" and current is not None
            and values["skill_revision"] is not None and current.revision != values["skill_revision"]):
        raise HTTPException(status_code=409, detail="skill revision changed")
    if values["operation"] == "request_activation":
        # Offline package validation is not the paired SW-G evaluation or its
        # blinded human review. Until an accepted evaluation report is bound to
        # this exact skill revision through an owner-scoped receipt, do not
        # create a maintainer artifact that could look activation-ready.
        raise HTTPException(
            status_code=409,
            detail="accepted live evaluation and blinded human review evidence is required",
        )
    if values["operation"] == "request_rollback":
        # The Versions API currently has no durable accepted-version history;
        # a successful offline test alone cannot identify a valid prior config.
        raise HTTPException(
            status_code=409,
            detail="no previously accepted package and registry revision is recorded",
        )
    if values["operation"] == "cancel":
        try:
            cancelled, created = cancel_job(owner, values)
            return {"schema_version": 1, **cancelled, "replayed": not created}
        except SkillRequestError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from None
    if values["operation"] == "test":
        if values["scope"] == "live":
            raise HTTPException(status_code=409, detail="live skill evaluation is disabled until a reviewed route and budget are configured")
        try:
            draft = get_skill_job(owner, values["job_id"])
            if (not draft or draft.get("operation") != "draft"
                    or draft.get("skill_id") != values["skill_id"]):
                raise HTTPException(status_code=404, detail="authoring job is unavailable")
            if draft.get("state") != "drafting":
                raise HTTPException(status_code=409, detail="authoring job is not ready for offline validation")
            job, created = start_offline_validation(owner, values)
            return {"schema_version": 1, **job, "replayed": not created}
        except SkillRequestError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from None
    if values["operation"] == "request_publish":
        try:
            job, created = start_publish(owner, values)
            return {"schema_version": 1, **job, "replayed": not created}
        except SkillRequestError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from None
    raise HTTPException(status_code=400, detail="unsupported Skills operation")


@app.get("/api/skills/requests/{request_id}")
def skill_request_status(request_id: str, request: Request) -> dict:
    from jarvis.skill_requests import SkillRequestError, _service, reconcile
    owner = _skill_request_owner(request)
    try:
        state = reconcile(owner, request_id)
    except SkillRequestError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from None
    if state is None:
        raise HTTPException(status_code=404, detail="request is unavailable")
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

    run_migrations()
    if not SLUG.fullmatch(skill_id):
        raise HTTPException(status_code=400, detail="invalid skill identifier")
    if len(cursor) > 512:
        raise HTTPException(status_code=400, detail="invalid skill run cursor")
    if not 1 <= limit <= 100:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 100")
    try:
        page = list_skill_runs(
            skill_id, cursor=cursor, limit=limit,
            user_id=_skill_activity_owner(request),
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid skill run cursor") from None
    return {"schema_version": 1, **page}


@app.get("/api/skills/runs/{run_id}/events")
def skills_run_events(
    run_id: str, request: Request, after_seq: int = 0, limit: int = 100,
) -> dict:
    """Read typed activity for an owned run; never fall back to prompt logs."""
    run_migrations()
    if not 0 <= after_seq <= 2**63 - 1:
        raise HTTPException(status_code=400, detail="invalid event cursor")
    if not 1 <= limit <= 100:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 100")
    try:
        page = get_skill_events(
            run_id, after_seq=after_seq, limit=limit,
            user_id=_skill_activity_owner(request),
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid run identifier") from None
    if page is None:
        raise HTTPException(status_code=404, detail="run is unavailable")
    return {"schema_version": 1, **page}


@app.get("/api/skills/{skill_id}")
def skill_detail(skill_id: str, revision: str | None = None) -> dict:
    """Return a validated immutable skill description and intended process."""
    from jarvis.skill_catalog import SLUG, SkillPackageError, inspect_package
    from jarvis.skill_service import assess_current_readiness
    from jarvis.agent_skills import SKILLS_DIR

    if not SLUG.fullmatch(skill_id):
        raise HTTPException(status_code=400, detail="invalid skill identifier")
    try:
        item = inspect_package(SKILLS_DIR / skill_id)
    except (OSError, SkillPackageError):
        raise HTTPException(status_code=404, detail="skill is unavailable") from None
    if item.installation != "installed" or item.revision is None:
        raise HTTPException(status_code=409, detail="skill package needs attention")
    if revision is not None and revision != item.revision:
        raise HTTPException(status_code=409, detail="skill revision changed")
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
        raise HTTPException(status_code=400, detail="invalid skill identifier")
    try:
        owner = _skill_request_owner(request)
        item = inspect_package(SKILLS_DIR / skill_id)
        names, pins, registry_version, registry_valid = read_skill_registry(SKILLS_CONFIG)
        candidates = list_for_skill(owner, skill_id)
    except HTTPException:
        raise
    except SkillRequestError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from None
    except (OSError, SkillPackageError):
        raise HTTPException(status_code=404, detail="skill version evidence is unavailable") from None

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
        raise HTTPException(status_code=400, detail="invalid skill example identifier")
    try:
        package = inspect_package(SKILLS_DIR / skill_id)
    except (OSError, SkillPackageError):
        raise HTTPException(status_code=404, detail="skill example is unavailable") from None
    if package.installation != "installed" or example_id not in package.example_ids:
        raise HTTPException(status_code=404, detail="skill example is unavailable")
    names, pins, version, registry_valid = read_skill_registry()
    if (not registry_valid or version != 2 or skill_id not in names
            or pins is None or pins.get(skill_id) != package.revision):
        raise HTTPException(status_code=409, detail="skill example is not bound to the reviewed package revision")
    repository = REPO_ROOT.resolve()
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
        payload = json.loads(resolved.read_text(encoding="utf-8"), object_pairs_hook=unique_pairs)
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
        raise HTTPException(status_code=409, detail="reviewed example preview is unavailable") from None


@app.get("/api/knowledge")
def knowledge_overview() -> dict:
    """K5 (MORTIMER_KNOWLEDGE_FRAMEWORK_PLAN.md) — the four layers, with
    counts, in one read-only call. The body lives in
    jarvis/status/overview.py (status spec T2.3) so this endpoint and
    system_overview() share one implementation (R8); response unchanged."""
    from jarvis.status.overview import knowledge_overview as _knowledge

    return _knowledge()


@app.get("/api/workflows")
def workflows_detail() -> dict:
    """MORTIMER_WORKFLOW_VIEWER_PLAN.md piece 1 — every workflow in full for
    the read-only viewer. Body in jarvis/status/overview.py, beside the
    knowledge overview."""
    from jarvis.status.overview import workflows_detail as _workflows
    return _workflows()


@app.get("/api/ambient")
def ambient() -> dict:
    """Engagement plan E4 — the console's idle ambient strip. Read-only:
    the next pending reminder (mcp_reminders.logic, same cross-boundary
    import pattern as mcp_git's logic above) and the running session
    summary (same jarvis.memory helper /api/memory uses). The client
    polls this every 60s while connected; chips for null fields hide."""
    run_migrations()
    from mcp_servers.mcp_reminders.logic import list_reminders

    reminder = None
    result = list_reminders("pending")
    for r in result.get("reminders", []):
        # due_at ASC — first row is the next one up.
        reminder = {"text": r["message"], "due_at": r["due_at"]}
        break
    summary = memory_module.get_summary_text() or None
    # Larry 2026-08-18: live weather for the current location — fetched
    # HERE (sidecar), never by the client; jarvis/ambient_weather.py
    # caches 15 min and degrades to None on any failure.
    from jarvis.ambient_weather import get_weather

    return {
        "ok": True,
        "reminder": reminder,
        "summary": summary,
        "weather": get_weather(),
        "system": _system_vitals(),
    }


# Machine vitals for the console's bottom-right readout (Larry
# 2026-08-18). Served from the SAME mcp_system.logic the systems agent
# uses — one implementation, so the chip and the spoken answer can never
# disagree about the same machine, the same discipline mcp_runlog follows
# for the run log.
#
# Deliberately NOT a separate endpoint or a faster poll: this rides the
# existing 60s /api/ambient call. psutil is local and cheap, but a
# second poller would be a second thing to keep in sync, and a 1s gauge
# refresh would put continuous motion in the corner of a voice-first
# interface — the engagement layer's rule is that the wave keeps its
# motion monopoly.
def _system_vitals() -> dict | None:
    """CPU/memory/disk/battery/uptime plus which metrics are over the
    threshold. None (chip hidden) on any failure — a vitals readout must
    never be the reason the ambient strip breaks."""
    try:
        from mcp_servers.mcp_system.logic import FLAG_THRESHOLD, get_system_status

        s = get_system_status()
        # The SAME 85% rule the systems agent speaks aloud, read from the
        # module rather than re-declared here, so the chip turns amber at
        # exactly the point the agent starts warning.
        flags = [
            name for name, value in (
                ("cpu", s.get("cpu_percent")),
                ("memory", s.get("memory_percent")),
                ("disk", s.get("disk_percent")),
            )
            if isinstance(value, (int, float)) and value >= FLAG_THRESHOLD
        ]
        return {
            "cpu": s.get("cpu_percent"),
            "memory": s.get("memory_percent"),
            "disk": s.get("disk_percent"),
            "battery": s.get("battery_percent"),
            "uptime_hours": s.get("uptime_hours"),
            "flags": flags,
            "threshold": FLAG_THRESHOLD,
        }
    except Exception as exc:  # noqa: BLE001 — never break the ambient strip
        logger.warning("ambient_system_vitals_failed error_type=%s",
                       type(exc).__name__)
        return None


class LocationBody(BaseModel):
    lat: float
    lon: float
    label: str = ""


@app.post("/api/location")
def set_location(body: LocationBody) -> dict:
    """Device location, posted by the Mac shell's CoreLocation manager
    (Larry 2026-08-18 — "I want to know where I am so that current
    weather is correct for my current location"). Coordinates are held in
    memory only (jarvis/ambient_weather.py), never written to disk or the
    run log, and go stale after an hour so a shell that stops reporting
    falls back to IP geolocation rather than pinning a place Larry left."""
    if not (-90.0 <= body.lat <= 90.0 and -180.0 <= body.lon <= 180.0):
        return {"ok": False, "error": "coordinates out of range"}
    from jarvis.ambient_weather import set_device_location

    set_device_location(body.lat, body.lon, body.label)
    return {"ok": True}


# ---- Self-service status (status spec T2.4, L2) -------------------------
#
# Read-only status computed HERE, in the process that already holds the
# vault's keys, the device location and the key-health verdicts. The voice
# tool `system_status` and the `mcp-status` MCP server are thin HTTP
# clients of these routes, so no secret enters an MCP child. Plain `def`
# routes (FastAPI's threadpool): every one does blocking I/O. Each checks
# the JARVIS_STATUS_TOOLS_ENABLED switch first (jarvis.status.status_enabled,
# its one reader) and never returns a traceback.

STATUS_DISABLED = {"ok": False, "error": "status tools are disabled"}


def _status_call(topic: str, thunk) -> dict:
    from jarvis.status import status_enabled

    if not status_enabled():
        return dict(STATUS_DISABLED)
    try:
        return thunk()
    except Exception as exc:  # noqa: BLE001 — a status read must never 500
        logger.warning("status_route_failed topic=%s error=%s",
                       topic, type(exc).__name__)
        return {"ok": False, "error": str(exc)}


@app.get("/api/status/models")
def status_models() -> dict:
    from jarvis.status import models as _m

    return _status_call("models", lambda: _m.model_access_status())


@app.get("/api/status/services")
def status_services() -> dict:
    from jarvis.status import services as _s

    return _status_call("services", lambda: _s.service_health())


@app.get("/api/status/overview")
def status_overview() -> dict:
    from jarvis.status import overview as _o

    return _status_call("overview", lambda: _o.system_overview())


@app.get("/api/status/build")
def status_build() -> dict:
    from jarvis.status import build as _b

    return _status_call("build", lambda: _b.app_build_status(REPO_ROOT))


@app.get("/api/status/location")
def status_location() -> dict:
    from jarvis.status import location as _l

    return _status_call("location", lambda: _l.current_location())


@app.get("/api/status/logs")
def status_logs(source: str = "", query: str = "", since_minutes: int = 60,
                limit: int = 50) -> dict:
    from jarvis.status import logs as _g

    return _status_call("logs", lambda: _g.log_search(
        source, query, since_minutes=since_minutes, limit=limit))


@app.get("/api/status/catalog")
def status_catalog(provider: str = "all", force: bool = False) -> dict:
    """What each configured provider offers right now (status spec T4.1):
    live `/models` reads with the vault's keys, cached an hour unless
    `force`. Leaves the machine, so the voice tool refuses it on a
    protected turn (I3)."""
    from jarvis.status import catalog as _c

    return _status_call("catalog", lambda: _c.catalog_status(provider, force=force))


class SubscriptionProbeBody(BaseModel):
    which: str
    model: str | None = None
    force: bool = False


@app.post("/api/status/subscription/probe")
def status_subscription_probe(body: SubscriptionProbeBody) -> dict:
    """Try one exact model on the Claude or Codex subscription CLI (status
    spec T4.2). The one status route that spends anything — a little
    subscription quota — so it is rate-limited per (which, model) for 10
    minutes unless `force` (I2)."""
    from jarvis.status import subscriptions as _su

    return _status_call("subscription", lambda: _su.subscription_status(
        body.which, body.model, force=body.force))


@app.get("/api/status/github")
def status_github(kind: str = "prs", state: str = "open", limit: int = 10,
                  number: int | None = None) -> dict:
    """Pull requests and their checks on Mortimer's own repository (status
    spec T4.3). GET-only reads through mcp_apps' GitHubClient; the token
    stays in this process."""
    from jarvis.status import github as _gh

    return _status_call("github", lambda: _gh.github_status(
        kind, state=state, limit=limit, number=number))


@app.post("/api/clipboard/clear")
def clipboard_clear() -> dict:
    """MORTIMER_HANDOFF_LOOP_PLAN.md H4 — wipe the clipboard and arm a
    read. The sidecar runs on Larry's Mac, so pbcopy/pbpaste are reachable
    here without any Swift change; the WKWebView bridge is fire-and-forget
    and browser clipboard read needs a user gesture a voice command cannot
    supply."""
    from jarvis import clipboard

    return clipboard.clear()


@app.get("/api/clipboard")
def clipboard_read() -> dict:
    """H4 — read the clipboard, but ONLY if a clear armed it, and disarm
    afterwards. The refusal is the safety property: an unarmed read would
    return whatever happened to be there, which may be a credential copied
    for an unrelated reason."""
    from jarvis import clipboard

    return clipboard.read()


@app.delete("/api/memory/fact/{key}")
def memory_delete_fact(key: str) -> dict:
    run_migrations()
    with get_conn() as conn:
        deleted = memory_module.delete_fact(conn, key)
    if not deleted:
        return {"ok": False, "error": f"No fact with key '{key}'."}
    return {"ok": True, "key": key}


# MORTIMER_MEMORY_AUTOCONSOLIDATION_PLAN.md A3 — thin wrappers over
# jarvis.memory_sweep, same convention as the memory endpoints above:
# the sidecar owns nothing new, it just exposes the review queue the
# startup sweep (A1/A2/A4/A5) populates.


@app.get("/api/memory/reviews")
def memory_reviews_list() -> dict:
    run_migrations()
    from jarvis import memory_sweep

    try:
        return {"ok": True, "reviews": memory_sweep.list_open_reviews()}
    except Exception as exc:  # noqa: BLE001 — a panel must never break the sidecar
        logger.warning("memory_reviews_list_failed error_type=%s",
                       type(exc).__name__)
        return {"ok": False, "error": "could not read the review queue"}


@app.post("/api/memory/reviews/{review_id}/resolve")
def memory_reviews_resolve(review_id: int, body: MemoryReviewResolveIn) -> dict:
    run_migrations()
    from jarvis import memory_sweep

    try:
        with get_conn() as conn:
            result = memory_sweep.resolve_review(
                conn, review_id, body.action, body.rewrite_content,
            )
            conn.commit()
        return {"ok": True, **result}
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001 — a panel must never break the sidecar
        logger.warning("memory_reviews_resolve_failed error_type=%s",
                       type(exc).__name__)
        return {"ok": False, "error": "could not resolve that review"}


# ----------------------------------------------------------------- runs
# Run-logging plan §5.11: thin pass-throughs over jarvis.runlog, same
# convention as memory/git above. Query normalization (since -> ISO, the
# D9 orphan-status rule) lives in jarvis.runlog.store and must not be
# reimplemented here — both endpoints call parse_since() before calling
# list_runs()/get_run() so the CLI and the console panel can never
# disagree about what "2d" means.


@app.get("/api/runs")
def runs_list(
    agent: str = "", status: str = "", since: str = "", limit: int = 50,
) -> dict:
    run_migrations()
    clamped_limit = max(1, min(200, limit))
    return {
        "ok": True,
        "runs": list_runs(
            agent=agent or None,
            status=status or None,
            since=parse_since(since or None),
            limit=clamped_limit,
        ),
    }


@app.get("/api/runs/{run_id}")
def runs_detail(run_id: str) -> dict:
    run_migrations()
    detail = get_run(run_id)
    if detail is None:
        return {"ok": False, "error": "not found"}
    return {"ok": True, **detail}


# -------------------------------------------------------------- council
# MORTIMER_LLM_COUNCIL_PLAN.md D10. Thin pass-throughs over
# jarvis.council.council, same convention as runs/memory/git above — no
# council logic is duplicated here.


@app.post("/api/council/convene")
def council_convene(body: ConveneIn) -> dict:
    """MORTIMER_LLM_COUNCIL_V2_PLAN.md V5 — manual convene (the plan's
    §5.3 override — "I suspect this is hard," independent of any
    observed failure), now non-blocking: validates as before, then fires
    the round in the background and returns immediately. Poll
    GET /api/council/job for the result. D14: only `placement="planner"`
    is implemented — D6.1's prompts are the only ones this plan defines;
    a reviewer-placement prompt was never specified, so that placement
    is refused rather than improvised."""
    advisory_started_at = time.time()
    run_migrations()
    if body.placement != "planner":
        return {
            "ok": False,
            "error": f"placement={body.placement!r} is not implemented — "
                     "only 'planner' has a defined council prompt (D6.1)",
        }
    goal = (body.goal or _selfedit_service.goal or "").strip()
    if not goal:
        return {"ok": False, "error": "a goal is required (no active session to fall back on)"}
    with _council_lock:
        if _council_job["state"] == "running":
            return {
                "ok": False,
                "error": "a council round is already in progress",
                "job": dict(_council_job),
            }
        context: dict[str, Any] = {"diff": _selfedit_service.proposals, "checks": None}
        if body.members:
            context["members"] = body.members
        _council_job.update(
            state="running", trigger="manual", goal=goal, round_id=None,
            winner=None, winner_mean=None, select_reason=None, error=None,
            started_at=time.time(), finished_at=None,
        )
    _start_advisory_thread(
        _run_council_job,
        kwargs={"trigger": "manual", "goal": goal, "context": context},
        started_at=advisory_started_at,
    )
    return {"ok": True, "started": True}


@app.get("/api/council/job")
def council_job_status() -> dict:
    """MORTIMER_LLM_COUNCIL_V2_PLAN.md V5 — the polling target for both
    a manual convene and the E3 half of a reject, mirroring
    GET /api/selfedit/run."""
    with _council_lock:
        job = dict(_council_job)
    return {"ok": True, "job": job}


@app.get("/api/council/round/{round_id}")
def council_round_detail(round_id: str) -> dict:
    run_migrations()
    detail = council_mod.get_round(round_id)
    if detail is None:
        return {"ok": False, "error": "not found"}
    return {"ok": True, **detail}


@app.get("/api/council/rounds")
def council_rounds_list(
    workflow: str = "", status: str = "", since: str = "", limit: int = 50,
) -> dict:
    run_migrations()
    clamped_limit = max(1, min(200, limit))
    return {
        "ok": True,
        "rounds": council_mod.list_rounds(
            workflow=workflow or None, status=status or None,
            since=parse_since(since or None), limit=clamped_limit,
        ),
    }


# ---- MORTIMER_GRAPH_LAYER_PLAN.md GL11 — read-only graph views. Every edge is
# derived in jarvis/graphs; these endpoints only call build() and render.
@app.get("/api/graph/{name}")
def graph_json(name: str, focus: str = "", depth: int | None = None,
               edge_types: str = "", since: str = "") -> dict:
    run_migrations()
    with closing(get_conn()) as conn:
        return graphs.build(name, conn, focus=focus, depth=depth,
                            edge_types=edge_types, since=since or None)


@app.get("/api/graph/{name}/image.{fmt}")
def graph_image(name: str, fmt: str, focus: str = "", depth: int | None = None,
                edge_types: str = "", since: str = "", w: int = 0, h: int = 0):
    if fmt not in ("png", "svg"):
        return Response(status_code=404)
    width = gcfg.GRAPH_IMAGE_W if w <= 0 else max(gcfg.GRAPH_IMAGE_MIN_PX, min(gcfg.GRAPH_IMAGE_MAX_PX, w))
    height = gcfg.GRAPH_IMAGE_H if h <= 0 else max(gcfg.GRAPH_IMAGE_MIN_PX, min(gcfg.GRAPH_IMAGE_MAX_PX, h))
    run_migrations()
    with closing(get_conn()) as conn:
        result = graphs.build(name, conn, focus=focus, depth=depth, edge_types=edge_types,
                              since=since or None)
    media = "image/png" if fmt == "png" else "image/svg+xml"
    if not result.get("ok"):
        # GL11: never a 4xx for a graph error — an <img>/AsyncImage shows nothing for one.
        body = (render.error_image_png(result["error"], width, height) if fmt == "png"
                else render.error_image_svg(result["error"], width, height))
        return Response(content=body, media_type=media)
    graph = graphs.from_json(result)
    pos = render.layout(graph, result["focus"], width, height)
    body = (render.to_png(graph, pos, width, height, focus=result["focus"]) if fmt == "png"
            else render.to_svg(graph, pos, width, height, focus=result["focus"]))
    return Response(content=body, media_type=media)


@app.get("/api/council/roster")
def council_roster(
    workflow: str = "", status: str = "", since: str = "", limit: int = 20,
) -> dict:
    """MORTIMER_OPTIMIZATION_PLAN.md's Interface Task — the Agents
    surface's read. Same filters as /api/council/rounds, but each round
    arrives assembled (proposers with means, judges with their abstain
    reasons, a degradation verdict) so the view renders rather than
    computes. A lower default and a tighter clamp than the rounds list:
    this one is polled and each entry is much larger."""
    run_migrations()
    clamped_limit = max(1, min(50, limit))
    return {
        "ok": True,
        "rounds": council_mod.list_round_rosters(
            workflow=workflow or None, status=status or None,
            since=parse_since(since or None), limit=clamped_limit,
        ),
    }


# ------------------------------------------------------- planning pathway
# MORTIMER_PLANNING_PATHWAY_PLAN.md P7. Thin pass-throughs over
# jarvis.council.council (draft_candidates/record_user_choice) and
# mcp_repo.logic (the SAME draft-gated write voice uses) — no write
# primitive is duplicated here.


@app.post("/api/plan/start")
def plan_start(body: PlanStartIn) -> dict:
    advisory_started_at = time.time()
    run_migrations()
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
        read_result = repo_logic.repo_read_file(review_path)
        if not read_result.get("ok"):
            return {"ok": False, "error": read_result.get("error")}
        content = read_result.get("content") or ""
        if len(content) > council_config.PLAN_REVIEW_DOC_MAX_CHARS:
            content = (
                content[: council_config.PLAN_REVIEW_DOC_MAX_CHARS]
                + "\n\n… (truncated for review — flag this truncation in your verdict)"
            )
        context = {"document": content, "document_path": review_path}

    with _plan_lock:
        try:
            prior = get_execution_action(_PLAN_START_ACTION_SCOPE, run_id)
        except Exception as exc:
            logger.warning("plan_start_claim_read_failed error_type=%s", type(exc).__name__)
            return {
                "ok": False,
                "error": "could not verify whether this planning action already started; "
                         "no retry was launched",
                "outcome": "unknown",
                "action_run_id": run_id,
            }
        if prior is not None:
            if _plan_job.get("run_id") == run_id:
                state = _plan_job.get("state") or "unknown"
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
        if _plan_job["state"] == "running":
            return {
                "ok": False,
                "error": "a planning job is already in progress — ask for status instead",
                "job": dict(_plan_job),
            }
        resolved_profile_name: str | None = None
        profile: dict[str, Any] | None = None
        if body.mode == "single":
            try:
                # Construct now so an unknown profile fails fast,
                # synchronously — same rule selfedit_run's _make_agent
                # call follows above.
                profile = _resolve_planning_profile(body.profile)
            except UnknownModelProfileError as exc:
                return {"ok": False, "error": str(exc)}
            resolved_profile_name = profile["name"]
        try:
            claimed = claim_execution_action(_PLAN_START_ACTION_SCOPE, run_id)
        except Exception as exc:
            logger.warning("plan_start_claim_write_failed error_type=%s", type(exc).__name__)
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
        _plan_job.update(
            state="running", mode=body.mode, goal=goal,
            profile=resolved_profile_name, round_id=None, candidates=None,
            plan=None, author=None, error=None,
            started_at=time.time(), finished_at=None,
            review_path=review_path or None,
            run_id=run_id,
        )
        _activate_advisory(_plan_job)
    _update_plan_start_claim(run_id, "running")
    if body.mode == "single":
        _start_advisory_thread(
            _run_plan_single, args=(goal, profile, context, run_id),
            started_at=advisory_started_at,
        )
    else:
        _start_advisory_thread(
            _run_plan_council, args=(goal, body.members, context, run_id),
            started_at=advisory_started_at,
        )
    return {"ok": True, "started": True}


@app.get("/api/plan/job")
def plan_job_status(run_id: str | None = None) -> dict:
    with _plan_lock:
        _advisory_context_for_job('planning', _plan_job)
        job = dict(_plan_job)
    requested_run_id = (run_id or "").strip()
    if requested_run_id:
        if len(requested_run_id) > 256:
            return {"ok": False, "error": "planning action identity is invalid"}
        if job.get("run_id") == requested_run_id:
            return {"ok": True, "job": job}
        try:
            receipt = get_execution_action(_PLAN_START_ACTION_SCOPE, requested_run_id)
        except Exception as exc:
            logger.warning("plan_start_status_read_failed error_type=%s", type(exc).__name__)
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
    with _plan_lock:
        source = _advisory_context_for_job('planning', _plan_job)
        if _plan_job["state"] != "awaiting_choice":
            return {"ok": False, "error": "no planning round is awaiting a choice"}
        round_id = _plan_job["round_id"]
        candidates = list(_plan_job["candidates"] or [])
    label = (body.label or "").strip()
    match = next((c for c in candidates if c["label"] == label), None)
    if match is None:
        return {"ok": False, "error": f"no candidate with label {label!r}"}
    council_mod.record_user_choice(round_id, label)
    with _plan_lock:
        if _advisory_context_for_job('planning', _plan_job) is not source:
            # Metadata-only manual contexts may be freshly sealed; the
            # action identity is the retained authority.
            current = _advisory_context_for_job('planning', _plan_job)
            if source is not None and (current is None or current._action is not source._action):
                raise HTTPException(status_code=409, detail='advisory source action changed')
        _plan_job.update(
            state="done", plan=match["content"], author=match["profile"],
            finished_at=time.time(),
        )
        chosen_run_id = _plan_job.get("run_id")
        if source is not None:
            from jarvis.advisory_sources import record_advisory_job
            record_advisory_job(source, _plan_job)
    _update_plan_start_claim(chosen_run_id, "completed")
    return {"ok": True}


@app.post("/api/plan/adopt")
def plan_adopt(body: PlanAdoptIn) -> dict:
    """Save the finished plan through the guarded sandbox editor.
    P7's attribution footer is appended HERE, once, at adoption: a
    candidate on the ballot stays footer-free and byte-comparable, and a
    plan never adopted stamps nothing."""
    with _plan_lock:
        source = _advisory_context_for_job('planning', _plan_job)
        if _plan_job["state"] != "done":
            return {"ok": False, "error": "no finished plan to adopt"}
        job = dict(_plan_job)
    plan_text = job.get("plan") or ""
    if not plan_text:
        return {"ok": False, "error": "the plan is empty"}
    review_path = job.get("review_path")
    if body.path:
        path = body.path.strip()
    elif review_path:
        # MORTIMER_PLAN_REVIEW_AND_DOCS_PLAN.md R4 — a review's default
        # adopt path is docs/reviews/, not docs/plans/.
        path = f"docs/reviews/{_slugify_goal(job.get('goal') or 'review')}.md"
    else:
        path = f"docs/plans/{_slugify_goal(job.get('goal') or 'plan')}.md"

    registry = load_model_registry()
    profiles = registry.get("profiles", {})
    author_name = job.get("author") or "unknown"
    provider_model = (profiles.get(author_name) or {}).get("model", author_name)
    if review_path:
        # R4 — the review-mode footer verb, exact template.
        footer = (
            f"\n\n---\n*Review by {author_name} ({provider_model}) — "
            f"{now_iso()[:10]}. Reviewed: {review_path}.*"
        )
    else:
        footer = f"\n\n---\n*Drafted by {author_name} ({provider_model}) — {now_iso()[:10]}.*"
    if job.get("mode") == "council" and job.get("round_id"):
        n = len(job.get("candidates") or [])
        footer += (
            f" Selected by Larry from {n} council candidate"
            f"{'s' if n != 1 else ''} (round {job['round_id']})."
        )

    token = _advisory_transport_context.set(source)
    try:
        result = _save_document_to_sandbox(
            path, plan_text + footer, rationale=f"Adopted plan: {job.get('goal') or ''}",
        )
    finally:
        _advisory_transport_context.reset(token)
    return dict(result)


@app.post("/api/plan/cancel")
def plan_cancel() -> dict:
    with _plan_lock:
        source = _advisory_transport_context.get()
        guard = _advisory_job_guards.get('planning')
        if source is not None and (_plan_job.get('run_id') != source.as_metadata()['action_run_id']
                or (guard is not None and guard['source'] is not None and guard['source']._action is not source._action)):
            return {'ok': True, 'already_idle': True}
        _advisory_context_for_job('planning', _plan_job)
        guard = _advisory_job_guards.pop('planning', None)
        if guard is not None:
            guard['event'].set()
        if _plan_job["state"] == "idle":
            return {"ok": True, "already_idle": True}
        _plan_job.update(
            state="idle", mode=None, goal=None, profile=None, round_id=None,
            candidates=None, plan=None, author=None, error=None,
            started_at=None, finished_at=None, review_path=None,
        )
        if guard is not None and guard['source'] is not None:
            from jarvis.advisory_sources import record_advisory_job
            record_advisory_job(guard['source'], _plan_job, allow_cancelled=True)
    return {"ok": True}


def main() -> None:
    import uvicorn

    # 2026-09-01 (MORTIMER_OPTIMIZATION_PLAN.md conflict resolution) —
    # moved D17's basicConfig() here from module level. Any test that
    # merely imports jarvis.admin.server (nine test_admin_*.py files do,
    # plus test_classify.py's /api/knowledge tests) used to trigger this
    # as an import-time side effect, fighting pytest's own root-logger
    # handler setup — implicated in tests/unit/test_memory.py's
    # TestCapacityHandling caplog assertions coming back empty when run
    # after those files. main() is the only caller that actually needs
    # configured logging (a real uvicorn process); importing this module
    # for its FastAPI app, endpoints, or helpers must stay side-effect
    # free. Same config, same D17 reasoning — just scoped to where the
    # server actually starts instead of where the module is loaded.
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stdout,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    if auth_enabled() and not service_headers():
        logger.warning(
            "admin_sidecar_service_token_missing internal_clients_will_fail_auth"
        )
    try:
        host = resolve_bind_host("admin-sidecar")
    except BindRefused as exc:
        logger.error("bind_refused process=admin-sidecar %s", exc)
        print(f"bind refused: {exc}", file=sys.stderr)
        raise SystemExit(2)
    port = resolve_port("JARVIS_ADMIN_PORT", 7861)
    # D17 — log startup with host/port. Logged via
    # this module's own logger (configured above), not uvicorn's —
    # log_level stays "warning" deliberately, to keep per-request access
    # logs quiet; the explicit points this decision requires (startup,
    # self-edit transitions, 5xx) are covered by our own logger calls.
    logger.info(
        "admin_sidecar_startup host=%s port=%d",
        host, port,
    )
    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
