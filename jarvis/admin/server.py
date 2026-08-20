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
- POST /api/selfedit/run      {goal, profile?} — start an upgrade run ASYNC
  (background thread + GET /api/selfedit/run polling): planning takes
  minutes and voice turns cannot block
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
import logging
import os
import re
import sys
import threading
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from jarvis.agents.upgrade_agent import (
    AppBuildAgent,
    UnknownModelProfileError,
    UpgradeAgent,
    available_models,
    load_model_registry,
    resolve_profile,
)
from jarvis.agents.workspace import AppWorkspace
from jarvis import memory as memory_module
from jarvis.council import config as council_config
from jarvis.council import council as council_mod
from jarvis.db import get_conn, now_iso, run_migrations
from jarvis.prompts import PLAN_AUTHOR_PROMPT, PLAN_REVIEW_PROMPT
from jarvis.runlog import get_run, list_runs, parse_since
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


# MORTIMER_AGENT_TRUST_PLAN.md D17: logs/admin.log was 0 bytes across every
# rotation. Root cause was uvicorn.run(..., log_level="warning") in main()
# below suppressing uvicorn's own startup/access logging entirely, with
# nothing in this module configuring a logger of its own to fill the gap —
# so the redirect in scripts/mortimer.sh (`>> logs/admin.log 2>&1`) had
# nothing to capture. This basicConfig call is what actually produces
# output; it must run before uvicorn.run() so the first log lines (the
# startup line emitted from main(), below) are not lost to an unconfigured
# root logger. stream=sys.stdout matches the redirect's expectation that
# both this process's own logs and any survivng uvicorn output land in the
# same file.
logging.basicConfig(
    level=logging.INFO,
    stream=sys.stdout,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
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


class ActionIn(BaseModel):
    action_id: int


class GoalIn(BaseModel):
    goal: str
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


class PlanChooseIn(BaseModel):
    label: str


class PlanAdoptIn(BaseModel):
    path: str | None = None


class AppBuildGoalIn(BaseModel):
    """MORTIMER_MODEL_DISCIPLINE_AND_MAC_SHELL_PLAN.md D5. Same
    plan/plan_path shape as GoalIn — plan_path is read-and-refuse
    identical to selfedit's."""
    app: str
    goal: str
    profile: str | None = None
    plan: str | None = None
    plan_path: str | None = None


# Single self-edit session for the sidecar process (plan §3: one at a time).
_selfedit_service = SelfEditService()

# Single-run gate: one upgrade job at a time, ever.
_run_lock = threading.Lock()
_run_job: dict[str, Any] = {
    "state": "idle",  # idle | running | done | error
    "goal": None,
    "profile": None,
    "summary": None,
    "started_at": None,
    "finished_at": None,
}

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
}

# MORTIMER_MODEL_DISCIPLINE_AND_MAC_SHELL_PLAN.md D5 — a fourth async-job
# slot, same shape/pattern as _run_job/_plan_job/_council_job above. Unlike
# _selfedit_service (one fixed Mortimer-repo session), the AppWorkspace is
# constructed fresh per app-build job (the app name varies), so there is
# no persistent module-level workspace — _appbuild_workspace holds the
# CURRENT job's workspace only, for the status/submit/cancel endpoints to
# reach. One app build at a time (one slot), and an app build does not
# block self-edit jobs — separate slots, separate locks.
_appbuild_lock = threading.Lock()
_appbuild_workspace: AppWorkspace | None = None
_appbuild_job: dict[str, Any] = {
    "state": "idle",  # idle | running | done | error
    "app": None,
    "goal": None,
    "profile": None,
    "summary": None,
    "started_at": None,
    "finished_at": None,
}


def _make_agent(service: SelfEditService, profile: str | None) -> UpgradeAgent:
    """Construct the planner (seam for tests)."""
    return UpgradeAgent(service, profile=profile)


def _run_agent(goal: str, profile: str | None, plan: str | None = None) -> None:
    """Background thread target: plan edits, then settle the job state."""
    try:
        agent = _make_agent(_selfedit_service, profile)
        result = agent.run(goal, plan=plan)
        state = "done" if result.get("ok") else "error"
        with _run_lock:
            _run_job.update(
                state=state,
                summary=result.get("summary", ""),
                finished_at=time.time(),
            )
        # D17 — every self-edit state transition is logged.
        logger.info("selfedit_state_transition state=%s goal=%r", state, goal)
    except Exception as exc:  # planner crash must still settle the job
        logger.exception("upgrade run crashed")
        with _run_lock:
            _run_job.update(
                state="error",
                summary=f"upgrade run crashed: {type(exc).__name__}: {exc}",
                finished_at=time.time(),
            )
        logger.info("selfedit_state_transition state=error goal=%r", goal)


def _busy() -> bool:
    with _run_lock:
        return _run_job["state"] == "running"


def _make_appbuild_agent(workspace: AppWorkspace, profile: str | None) -> AppBuildAgent:
    """Construct the planner (seam for tests), mirroring _make_agent."""
    return AppBuildAgent(workspace, profile=profile)


def _appbuild_busy() -> bool:
    with _appbuild_lock:
        return _appbuild_job["state"] == "running"


def _run_appbuild_agent(
    app: str, goal: str, profile: str | None, plan: str | None = None,
) -> None:
    """Background thread target, mirroring _run_agent: build one app, then
    settle _appbuild_job. The AppWorkspace itself lives on _appbuild_
    workspace so the status/submit/cancel endpoints can reach the same
    session this thread is driving."""
    global _appbuild_workspace
    try:
        workspace = AppWorkspace(app)
        with _appbuild_lock:
            _appbuild_workspace = workspace
        agent = _make_appbuild_agent(workspace, profile)
        result = agent.run(goal, plan=plan)
        state = "done" if result.get("ok") else "error"
        with _appbuild_lock:
            _appbuild_job.update(
                state=state, summary=result.get("summary", ""),
                finished_at=time.time(),
            )
        logger.info("appbuild_state_transition state=%s app=%r goal=%r", state, app, goal)
    except Exception as exc:  # a build crash must still settle the job
        logger.exception("app build run crashed")
        with _appbuild_lock:
            _appbuild_job.update(
                state="error",
                summary=f"app build run crashed: {type(exc).__name__}: {exc}",
                finished_at=time.time(),
            )
        logger.info("appbuild_state_transition state=error app=%r goal=%r", app, goal)


def _council_busy() -> bool:
    with _council_lock:
        return _council_job["state"] == "running"


def _run_council_job(
    *, trigger: str, goal: str, context: dict[str, Any], placement: str = "planner",
) -> None:
    """MORTIMER_LLM_COUNCIL_V2_PLAN.md V5 — background thread target,
    mirroring `_run_agent`'s shape: run the round, then settle
    `_council_job`. `convene()` returning None (D13's structural-failure
    case) settles the job as `error`; a `RoundResult` with `winner=None`
    (the round ran but selected nobody) settles as `done` with
    `winner=None` and `select_reason` populated — the same distinction
    `_maybe_escalate` makes between `result is None` and
    `result.winner is None`."""
    try:
        result = asyncio.run(council_mod.convene(
            workflow="selfedit", placement=placement, trigger=trigger,
            goal=goal, tier=1, context=context,
        ))
    except Exception as exc:  # noqa: BLE001 — a crash must still settle the job
        logger.exception("council job crashed")
        with _council_lock:
            _council_job.update(
                state="error",
                error=f"council job crashed: {type(exc).__name__}: {exc}",
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
) -> None:
    # MORTIMER_PLAN_REVIEW_AND_DOCS_PLAN.md R3 — single mode now shares
    # the same _proposer_user_message assembly council mode uses, so a
    # review job's document lands here automatically instead of via an
    # ad-hoc f-string that had no room for it.
    is_review = context.get("document") is not None
    system_prompt = PLAN_REVIEW_PROMPT if is_review else PLAN_AUTHOR_PROMPT
    user_content = council_mod._proposer_user_message(goal, context, "doc")
    try:
        content, _usage = asyncio.run(council_mod._call_profile(
            profile, system_prompt, user_content,
            council_config.PLANNING_MEMBER_TIMEOUT_S,
        ))
    except Exception as exc:  # noqa: BLE001 — a crash must still settle the job
        logger.exception("plan single-mode job crashed")
        with _plan_lock:
            _plan_job.update(
                state="error",
                error=f"planning call failed: {type(exc).__name__}: {exc}",
                finished_at=time.time(),
            )
        return
    with _plan_lock:
        _plan_job.update(
            state="done", plan=content, author=profile["name"],
            finished_at=time.time(),
        )


def _run_plan_council(
    goal: str, members: dict[str, list[str]] | None, context: dict[str, Any],
) -> None:
    try:
        result = asyncio.run(council_mod.draft_candidates(
            goal, members=members, judge=True, context=context,
        ))
    except Exception as exc:  # noqa: BLE001
        logger.exception("plan council-mode job crashed")
        with _plan_lock:
            _plan_job.update(
                state="error",
                error=f"planning round crashed: {type(exc).__name__}: {exc}",
                finished_at=time.time(),
            )
        return
    if result is None:
        with _plan_lock:
            _plan_job.update(
                state="error",
                error="council unavailable — see admin sidecar logs",
                finished_at=time.time(),
            )
        return
    if not result.proposals:
        with _plan_lock:
            _plan_job.update(
                state="error",
                error=result.select_reason or "no candidates were produced",
                finished_at=time.time(),
            )
        return
    candidates = [
        {
            "label": p.label, "profile": p.profile, "content": p.content,
            "advisory_mean": council_mod.mean_of(p.label, result.scores),
        }
        for p in result.proposals
    ]
    with _plan_lock:
        _plan_job.update(
            state="awaiting_choice", round_id=result.round_id,
            candidates=candidates, finished_at=time.time(),
        )


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
def prepare_commit(body: MessageIn) -> dict:
    return logic.prepare_commit(body.message)


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


@app.get("/api/selfedit/status")
def selfedit_status() -> dict:
    if _busy():
        return {"ok": False, "error": "an upgrade run is in progress — ask for status instead"}
    return _selfedit_service.status()


@app.post("/api/selfedit/run")
def selfedit_run(body: GoalIn) -> dict:
    """Start an upgrade run in the background; poll GET /api/selfedit/run."""
    goal = (body.goal or "").strip()
    if not goal:
        return {"ok": False, "error": "a goal is required — what should I change?"}
    plan = body.plan
    plan_path = (body.plan_path or "").strip()
    if plan is None and plan_path:
        # Voice-path plan seeding: read the plan document once,
        # synchronously, before the thread launches — mirrors plan_start's
        # review_path read-and-refuse (MORTIMER_PLAN_REVIEW_AND_DOCS_PLAN.md
        # R1). Same truncation knob: a seeded plan is a document injection
        # with the same size concerns as a reviewed one.
        read_result = repo_logic.repo_read_file(plan_path)
        if not read_result.get("ok"):
            return {"ok": False, "error": read_result.get("error")}
        plan = read_result.get("content") or ""
        if len(plan) > council_config.PLAN_REVIEW_DOC_MAX_CHARS:
            plan = (
                plan[: council_config.PLAN_REVIEW_DOC_MAX_CHARS]
                + "\n\n… (plan truncated at injection)"
            )
    with _run_lock:
        if _run_job["state"] == "running":
            return {
                "ok": False,
                "error": "an upgrade run is already in progress — ask for status instead",
                "job": dict(_run_job),
            }
        try:
            # Construct now so an unknown profile fails fast, synchronously,
            # before we report the run as started.
            agent = _make_agent(_selfedit_service, body.profile)
        except UnknownModelProfileError as exc:
            return {"ok": False, "error": str(exc)}
        _run_job.update(
            state="running",
            goal=goal,
            profile=agent.model_label(),
            summary=None,
            started_at=time.time(),
            finished_at=None,
        )
    # D17 — every self-edit state transition is logged.
    logger.info("selfedit_state_transition state=running goal=%r", goal)
    threading.Thread(
        target=_run_agent, args=(goal, body.profile, plan), daemon=True,
    ).start()
    return {"ok": True, "started": True, "profile": agent.model_label()}


@app.get("/api/selfedit/run")
def selfedit_run_status() -> dict:
    with _run_lock:
        job = dict(_run_job)
    return {"ok": True, "job": job, "status": _selfedit_service.status()}


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
    logger.info("selfedit_verify_appearance ok=%s branch=%s",
                result.get("ok"), result.get("branch"))
    return result


@app.post("/api/selfedit/submit")
def selfedit_submit() -> dict:
    if _busy():
        return {"ok": False, "error": "an upgrade run is in progress — ask for status instead"}
    result = _selfedit_service.submit()
    logger.info("selfedit_state_transition state=submitted ok=%s", result.get("ok"))
    return result


@app.post("/api/selfedit/revert")
def selfedit_revert() -> dict:
    if _busy():
        return {"ok": False, "error": "an upgrade run is in progress — ask for status instead"}
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
        threading.Thread(
            target=_run_council_job,
            kwargs={"trigger": "E3", "goal": goal, "context": context},
            daemon=True,
        ).start()

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
    goal = (body.goal or "").strip()
    if not goal:
        return {"ok": False, "error": "a goal is required — what should I build?"}
    try:
        app_name = validate_app_name(body.app)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    plan = body.plan
    plan_path = (body.plan_path or "").strip()
    if plan is None and plan_path:
        # Voice-path plan seeding — identical read-and-refuse pattern to
        # selfedit_run's, so an unreadable plan can never seed a build.
        read_result = repo_logic.repo_read_file(plan_path)
        if not read_result.get("ok"):
            return {"ok": False, "error": read_result.get("error")}
        plan = read_result.get("content") or ""
        if len(plan) > council_config.PLAN_REVIEW_DOC_MAX_CHARS:
            plan = (
                plan[: council_config.PLAN_REVIEW_DOC_MAX_CHARS]
                + "\n\n… (plan truncated at injection)"
            )
    with _appbuild_lock:
        if _appbuild_job["state"] == "running":
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
        _appbuild_job.update(
            state="running", app=app_name, goal=goal,
            profile=agent.model_label(), summary=None,
            started_at=time.time(), finished_at=None,
        )
    logger.info("appbuild_state_transition state=running app=%r goal=%r", app_name, goal)
    threading.Thread(
        target=_run_appbuild_agent, args=(app_name, goal, body.profile, plan), daemon=True,
    ).start()
    return {"ok": True, "started": True, "profile": agent.model_label()}


@app.get("/api/appbuild/job")
def appbuild_job_status() -> dict:
    with _appbuild_lock:
        job = dict(_appbuild_job)
        workspace = _appbuild_workspace
    status = workspace.status() if workspace is not None else {"active": False}
    return {"ok": True, "job": job, "status": status}


@app.post("/api/appbuild/submit")
def appbuild_submit() -> dict:
    if _appbuild_busy():
        return {"ok": False, "error": "an app build is in progress — ask for status instead"}
    with _appbuild_lock:
        workspace = _appbuild_workspace
    if workspace is None or not workspace.branch:
        return {"ok": False, "error": "no active app-build session to submit"}
    result = workspace.submit()
    logger.info("appbuild_state_transition state=submitted ok=%s", result.get("ok"))
    return result


@app.post("/api/appbuild/cancel")
def appbuild_cancel() -> dict:
    """Discard the active app-build session (mirrors selfedit_revert)."""
    if _appbuild_busy():
        return {"ok": False, "error": "an app build is in progress — ask for status instead"}
    with _appbuild_lock:
        workspace = _appbuild_workspace
    if workspace is None or not workspace.branch:
        return {"ok": False, "error": "no active app-build session to cancel"}
    result = workspace.revert()
    logger.info("appbuild_state_transition state=cancelled ok=%s", result.get("ok"))
    return result


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


@app.get("/api/knowledge")
def knowledge_overview() -> dict:
    """K5 (MORTIMER_KNOWLEDGE_FRAMEWORK_PLAN.md) — the four layers, with
    counts, in one read-only call.

    The specific thing this exists to prevent: on 2026-08-18 the store
    held 180 facts and ~14 reached the Supervisor, and that was
    discoverable ONLY by reading a `memory_context_facts_dropped` log
    line. Truncation must be visible in the console, not archaeology.
    `dropped` is computed by rendering the context and comparing — the
    same code path the prompt uses, so the number cannot drift from
    reality."""
    run_migrations()
    import logging as _logging

    from jarvis.db import get_conn as _get_conn

    tiers: dict[str, int] = {}
    archived = 0
    live = 0
    try:
        with _get_conn() as conn:
            for tier, n in conn.execute(
                "SELECT COALESCE(tier,'project'), COUNT(*) FROM memories "
                "WHERE kind='fact' AND archived_at IS NULL GROUP BY 1"
            ):
                tiers[str(tier)] = int(n)
            live = sum(tiers.values())
            archived = conn.execute(
                "SELECT COUNT(*) FROM memories WHERE kind='fact' "
                "AND archived_at IS NOT NULL"
            ).fetchone()[0]
            procedures = {
                str(st): int(n)
                for st, n in conn.execute(
                    "SELECT status, COUNT(*) FROM procedures GROUP BY 1"
                )
            }
    except Exception:  # noqa: BLE001 — a panel must never break the sidecar
        logger.exception("knowledge_overview_read_failed")
        return {"ok": False, "error": "could not read the knowledge store"}

    # How many facts actually reach the prompt right now.
    _logging.disable(_logging.WARNING)
    try:
        rendered = memory_module.render_memory_context()
    finally:
        _logging.disable(_logging.NOTSET)
    reaching = len([l for l in rendered.splitlines() if l.startswith("- ")])

    try:
        from jarvis.workflows import load_workflows

        workflows = [
            {"name": w.name, "source": w.source, "has_done_when": bool(w.done_when)}
            for w in load_workflows()
        ]
    except Exception:  # noqa: BLE001
        workflows = []

    # K3 skills. Both numbers matter and they are deliberately separate:
    # `on_disk` is what has been imported, `enabled` is what has been
    # reviewed and is actually loaded. A large gap is the normal, safe
    # state after importing a community pack — not a defect to fix.
    try:
        from jarvis.agent_skills import discover, enabled_names, load_skills

        found = discover()
        skills = {
            "on_disk": len(found),
            "invalid": len([1 for _, s, _ in found if s is None]),
            "registered": len(enabled_names()),
            "enabled": [
                {"name": s.name, "has_scripts": s.has_scripts}
                for s in load_skills()
            ],
        }
    except Exception:  # noqa: BLE001
        skills = {"on_disk": 0, "invalid": 0, "registered": 0, "enabled": []}

    return {
        "ok": True,
        "memory": {
            "live": live,
            "archived": archived,
            "tiers": tiers,
            "reaching_prompt": reaching,
            # The honest number: facts stored that the Supervisor never
            # sees, because `system` is excluded and the rest are capped.
            "not_reaching_prompt": max(0, live - reaching),
            "context_chars": len(rendered),
        },
        "procedures": procedures,
        "skills": skills,
        "workflows": workflows,
    }


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
    except Exception:  # noqa: BLE001 — never break the ambient strip
        logger.exception("ambient_system_vitals_failed")
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
    threading.Thread(
        target=_run_council_job,
        kwargs={"trigger": "manual", "goal": goal, "context": context},
        daemon=True,
    ).start()
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


# ------------------------------------------------------- planning pathway
# MORTIMER_PLANNING_PATHWAY_PLAN.md P7. Thin pass-throughs over
# jarvis.council.council (draft_candidates/record_user_choice) and
# mcp_repo.logic (the SAME draft-gated write voice uses) — no write
# primitive is duplicated here.


@app.post("/api/plan/start")
def plan_start(body: PlanStartIn) -> dict:
    run_migrations()
    goal = (body.goal or "").strip()
    if not goal:
        return {"ok": False, "error": "a goal is required — what should the plan cover?"}
    if body.mode not in ("single", "council"):
        return {"ok": False, "error": f"mode={body.mode!r} must be 'single' or 'council'"}

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
        _plan_job.update(
            state="running", mode=body.mode, goal=goal,
            profile=resolved_profile_name, round_id=None, candidates=None,
            plan=None, author=None, error=None,
            started_at=time.time(), finished_at=None,
            review_path=review_path or None,
        )
    if body.mode == "single":
        threading.Thread(
            target=_run_plan_single, args=(goal, profile, context), daemon=True,
        ).start()
    else:
        threading.Thread(
            target=_run_plan_council, args=(goal, body.members, context), daemon=True,
        ).start()
    return {"ok": True, "started": True}


@app.get("/api/plan/job")
def plan_job_status() -> dict:
    with _plan_lock:
        job = dict(_plan_job)
    return {"ok": True, "job": job}


@app.post("/api/plan/choose")
def plan_choose(body: PlanChooseIn) -> dict:
    with _plan_lock:
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
        _plan_job.update(
            state="done", plan=match["content"], author=match["profile"],
            finished_at=time.time(),
        )
    return {"ok": True}


@app.post("/api/plan/adopt")
def plan_adopt(body: PlanAdoptIn) -> dict:
    """Creates a draft-gated repo write of the finished plan (the SAME
    actions-table gate voice's repo_write_file/repo_commit_write use) —
    P7's attribution footer is appended HERE, once, at adoption: a
    candidate on the ballot stays footer-free and byte-comparable, and a
    plan never adopted stamps nothing."""
    with _plan_lock:
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

    result = repo_logic.repo_write_file(
        path, plan_text + footer, rationale=f"Adopted plan: {job.get('goal') or ''}",
    )
    return dict(result)


@app.post("/api/plan/cancel")
def plan_cancel() -> dict:
    with _plan_lock:
        if _plan_job["state"] == "idle":
            return {"ok": True, "already_idle": True}
        _plan_job.update(
            state="idle", mode=None, goal=None, profile=None, round_id=None,
            candidates=None, plan=None, author=None, error=None,
            started_at=None, finished_at=None, review_path=None,
        )
    return {"ok": True}


def main() -> None:
    import uvicorn

    host, port = "127.0.0.1", 7861
    # D17 — at minimum, log startup with host/port/repo root. Logged via
    # this module's own logger (configured above), not uvicorn's —
    # log_level stays "warning" deliberately, to keep per-request access
    # logs quiet; the explicit points this decision requires (startup,
    # self-edit transitions, 5xx) are covered by our own logger calls.
    logger.info("admin_sidecar_startup host=%s port=%d repo_root=%s",
                host, port, REPO_ROOT)
    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
