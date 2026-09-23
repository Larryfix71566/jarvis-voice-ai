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
- POST /api/selfedit/run      {staging_id} or {goal, profile?} — start an
  upgrade run ASYNC (background thread + GET /api/selfedit/run polling):
  planning takes minutes and voice turns cannot block. `staging_id`
  replays a /api/selfedit/stage record (preferred); the bare {goal,
  profile?} form still works for one release as a logged-deprecation
  fallback (G2).
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
import logging
import os
import re
import sys
import threading
import time
import uuid
from contextlib import closing
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, Response
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
from jarvis.model_routing import available_routes, load_access_config
from jarvis.model_preferences import (
    ModelPreferenceError,
    confirm_preference,
    list_preferences,
    stage_preference,
)
from jarvis.agents.workspace import AppWorkspace
from jarvis.admin.reminder_notifier import ReminderNotifier
from jarvis import memory as memory_module
from jarvis.council import config as council_config
from jarvis.council import council as council_mod
from jarvis.db import get_conn, now_iso, run_migrations
from jarvis import graphs
from jarvis.graphs import config as gcfg, render
from jarvis.prompts import (
    PLAN_AUTHOR_PROMPT,
    PLAN_REVIEW_PROMPT,
    RESEARCH_PROMPT,
    RESEARCH_SYSTEM_PROMPT,
)
from jarvis.research import crawl as research_crawl
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
    # app's Edit tab (macos/MortimerHost/.../Drawer/EditTab.swift:91 →
    # AdminAPI.selfeditRun) posts a bare {goal, profile} — no plan, no
    # staging — and reads `started` to know a run began; it has no way to
    # author anything, so it needs the planner (C1/SE10). The developer
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


class ResearchSaveIn(BaseModel):
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
            logger.info("selfedit_run_staging_resolved requested=%r used=%s",
                        requested, used)
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

# Single-run gate: one upgrade job at a time, ever.
_run_lock = threading.Lock()
# The UpgradeAgent instance currently driving _run_job (None when idle) —
# held only so POST /api/selfedit/cancel can reach its cooperative
# cancel flag (the same reason _appbuild_workspace exists).
_run_agent_instance: Any = None
_run_job: dict[str, Any] = {
    "state": "idle",  # idle | running | done | error | cancelled
    "cancel_requested": False,
    "goal": None,
    "profile": None,
    "summary": None,
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
    "run_id": None,
    "started_at": None,
    "finished_at": None,
}

# VM preparation outlives the voice client's HTTP deadline. Keep the start
# request short and expose progress; Session persists the underlying task.
_opening_lock = threading.Lock()
_opening_job: dict[str, Any] = {"state": "idle", "cancel_requested": False}


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
            if service.branch and (service.goal or "") != goal:
                discarded = service.revert()
                if not discarded.get("ok"):
                    raise RuntimeError("Previous workspace could not be discarded")
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
    except Exception:
        logger.exception("sandbox authoring setup failed")
        with _opening_lock:
            job.update(state="error", error="Sandbox setup failed; inspect the saved session before retrying.")
    finally:
        with _opening_lock:
            if job.get("cancel_requested"):
                job["state"] = "cancelled"
            job["finished_at"] = time.time()


def _begin_authoring(goal, run_id, target_paths, *, resume_session_id=None):
    global _opening_job
    with _run_lock, _finish_lock, _opening_lock:
        if (_run_job["state"] == "running" or _finish_job["state"] in {"validating", "submitting"}
                or _opening_job["state"] == "starting"):
            return {"ok": False, "error": "an upgrade run is already in progress — ask for status instead"}
        job = dict(state="starting", goal=goal, run_id=run_id,
            target_paths=target_paths, resume_session_id=resume_session_id,
            cancel_requested=False, started_at=time.time())
        _opening_job = job
    worker = threading.Thread(target=_open_authoring,
        args=(_selfedit_service, goal, run_id, target_paths, job), daemon=True)
    worker.start()
    # An already-open session may finish immediately. A fresh VM never holds
    # this request open for the duration of its preparation.
    worker.join(timeout=0.05)
    with _opening_lock:
        if job["state"] == "ready":
            return job["result"]
        if job["state"] == "error":
            return {"ok": False, "error": job.get("error")}
    return {"ok": True, "started": True, "opening": True, "state": "starting"}

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
}


def _research_enabled() -> bool:
    return os.environ.get(RESEARCH_ENABLED_ENV, "").strip().lower() not in ("false", "0", "no")


def _research_busy() -> bool:
    with _research_lock:
        return _research_job["state"] == "running"


def _run_research_job(urls: list[str], focus: str) -> None:
    """Background thread target (R1): crawl both sites (sync, one at a
    time — Tavily's own crawl is already parallel internally, and two
    concurrent 120s calls would only double the memory footprint for no
    real time saving), assemble the digest in CODE, then one model call
    for the prose comparison (R4/R5). Settles _research_job on every exit
    path, mirroring every other job target on this page."""
    try:
        cfg = research_crawl.load_research_config()
        api_key = os.environ.get(research_crawl.TAVILY_API_KEY_ENV)
        if not api_key:
            with _research_lock:
                _research_job.update(
                    state="error",
                    error="TAVILY_API_KEY is not configured",
                    finished_at=time.time(),
                )
            return
        client = research_crawl.TavilyCrawlClient(timeout=float(cfg.get("timeout_s", 120)) + 10.0)
        results = [
            research_crawl.crawl_site(client, url, focus, api_key, cfg)
            for url in urls
        ]
        # R9 — per-site failure, never all-or-nothing: only when EVERY
        # site failed does this become a terminal error.
        if not any(r.get("ok") for r in results):
            with _research_lock:
                _research_job.update(
                    state="error",
                    sites=[_site_summary(r) for r in results],
                    error="both sites failed to crawl — " + "; ".join(
                        f"{r['url']}: {r.get('error', 'unknown')}" for r in results
                    ),
                    finished_at=time.time(),
                )
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
        except UnknownModelProfileError as exc:
            with _research_lock:
                _research_job.update(
                    state="error",
                    sites=[_site_summary(r) for r in results],
                    error=f"no usable planner model: {exc}",
                    finished_at=time.time(),
                )
            return
        content, _usage = asyncio.run(council_mod._call_profile(
            profile, RESEARCH_SYSTEM_PROMPT, user_content,
            council_config.PLANNING_MEMBER_TIMEOUT_S, rung="research",
        ))
        with _research_lock:
            _research_job.update(
                state="done",
                sites=[_site_summary(r) for r in results],
                comparison=content,
                model=profile["name"],
                credits_used=research_crawl.total_credits(*results),
                finished_at=time.time(),
            )
        logger.info("research_state_transition state=done urls=%r", urls)
    except Exception as exc:  # noqa: BLE001 — a crash must still settle the job
        logger.exception("research job crashed")
        with _research_lock:
            _research_job.update(
                state="error",
                error=f"research job crashed: {type(exc).__name__}: {exc}",
                finished_at=time.time(),
            )


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


def _run_finish() -> None:
    """SE4 — background thread target: validate, and on green, submit.

    Auto-submit is not a new decision: it is the confirmation the user
    already gave at the preview, whose sentence says the run will validate
    and open the pull request if every check passes. On a failure the
    session stays OPEN with the check output, so repair is the developer on
    the next turn (read → write → finish again) rather than a dead end."""
    try:
        with _finish_lock:
            if _finish_job.get("cancel_requested"):
                _finish_job.update(state="cancelled", finished_at=time.time())
                return
        result = _selfedit_service.validate()
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
        with _finish_lock:
            _finish_job["state"] = "submitting"
        submitted = _selfedit_service.submit()
        with _finish_lock:
            if submitted.get("ok"):
                _finish_job.update(
                    state="done", pr_url=submitted.get("pr_url"),
                    notice=submitted.get("notice"), finished_at=time.time(),
                )
            else:
                _finish_job.update(
                    state="cancelled" if _finish_job.get("cancel_requested") else "error", notice=submitted.get("error"),
                    finished_at=time.time(),
                )
            state, pr_url, run_id = (_finish_job["state"], _finish_job["pr_url"],
                                     _finish_job["run_id"])
            notice = _finish_job.get("notice")
        # The notice carries the git/GitHub error text on failure. Logging
        # only the state (2026-09-08) meant a submit that died in 0.47 s
        # left NO record of why, and the reason had to be chased through a
        # live API call before it was overwritten by the next attempt.
        logger.info("selfedit_state_transition state=finish_%s pr=%s run_id=%s notice=%r",
                    state, pr_url, run_id, notice)
    except Exception as exc:  # noqa: BLE001 — a crash must still settle the job
        # Without this the job would sit in "validating" forever and the
        # developer would keep reporting it as still running.
        logger.exception("selfedit finish job crashed")
        with _finish_lock:
            _finish_job.update(
                state="cancelled" if _finish_job.get("cancel_requested") else "error",
                notice=f"finish crashed: {type(exc).__name__}: {exc}",
                finished_at=time.time(),
            )


def _run_agent(goal: str, profile: str | None, plan: str | None = None,
               run_id: str | None = None) -> None:
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
        stale = _selfedit_service.branch
        if stale and (_selfedit_service.goal or "") != goal:
            logger.info("selfedit_stale_session_reverted branch=%s old_goal=%r new_goal=%r",
                        stale, _selfedit_service.goal, goal)
            _selfedit_service.revert()
        result = agent.run(goal, plan=plan)
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
        # D17 — every self-edit state transition is logged.
        logger.info("selfedit_state_transition state=%s submitted=%s goal=%r summary=%r",
                    state, submitted, goal, summary[:400])
    except Exception as exc:  # planner crash must still settle the job
        logger.exception("upgrade run crashed")
        with _run_lock:
            _run_agent_instance = None
            _run_job.update(
                state="error",
                summary=f"upgrade run crashed: {type(exc).__name__}: {exc}",
                finished_at=time.time(),
            )
        logger.info("selfedit_state_transition state=error goal=%r", goal)


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
    return AppBuildAgent(workspace, profile=profile)


def _appbuild_busy() -> bool:
    with _appbuild_lock:
        return _appbuild_job["state"] in {"running", "submitting"}


def _run_appbuild_agent(
    app: str, goal: str, profile: str | None, plan: str | None = None,
) -> None:
    """Background thread target, mirroring _run_agent: build one app, then
    settle _appbuild_job. The AppWorkspace itself lives on _appbuild_
    workspace so the status/submit/cancel endpoints can reach the same
    session this thread is driving."""
    global _appbuild_workspace, _appbuild_agent_instance
    workspace = None
    try:
        workspace = AppWorkspace(app)
        agent = _make_appbuild_agent(workspace, profile)
        with _appbuild_lock:
            _appbuild_workspace = workspace
            _appbuild_agent_instance = agent
            cancelled = _appbuild_job.get("cancel_requested", False)
        if cancelled:
            agent.request_cancel()
        result = agent.run(goal, plan=plan)
        with _appbuild_lock:
            cancelled = _appbuild_job.get("cancel_requested", False) or result.get("cancelled", False)
        if cancelled:
            workspace.cancel()
        state = "cancelled" if cancelled else ("done" if result.get("ok") else "error")
        with _appbuild_lock:
            if _appbuild_job.get("cancel_requested", False):
                state = "cancelled"
            _appbuild_agent_instance = None
            _appbuild_job.update(
                state=state, summary=result.get("summary", ""),
                submitted=bool(result.get("submitted")), pr_url=result.get("pr_url"),
                finished_at=time.time(),
            )
        logger.info("appbuild_state_transition state=%s app=%r goal=%r", state, app, goal)
    except Exception as exc:  # a build crash must still settle the job
        logger.exception("app build run crashed")
        with _appbuild_lock:
            cancelled = _appbuild_job.get("cancel_requested", False)
            _appbuild_agent_instance = None
            _appbuild_job.update(
                state="cancelled" if cancelled else "error",
                summary="Build cancelled." if cancelled else f"app build run crashed: {type(exc).__name__}: {exc}",
                finished_at=time.time(),
            )
        logger.info("appbuild_state_transition state=%s app=%r", "cancelled" if cancelled else "error", app)


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
            council_config.PLANNING_MEMBER_TIMEOUT_S, rung="planning",
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
    run_id: str | None = None,
) -> None:
    try:
        result = asyncio.run(council_mod.draft_candidates(
            goal, members=members, judge=True, context=context, run_id=run_id,
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
        profiles = []
        for name, profile in sorted((registry.get("profiles") or {}).items()):
            routes = available_routes(profile)
            profiles.append({
                "name": name,
                "identity": profile.get("identity", ""),
                "provider": profile.get("provider", ""),
                "model": profile.get("model", ""),
                "tier": profile.get("tier"),
                "routes": routes,
                "api_key_env": profile.get("api_key_env"),
                "key_present": bool(profile.get("api_key_env")
                                     and os.environ.get(profile["api_key_env"])),
            })
        route_catalog = {}
        for name, route in (access.get("routes") or {}).items():
            route_catalog[name] = {
                "adapter": route.get("adapter", name),
                "billing": route.get("billing", name),
                "privacy": route.get("privacy", "approved_external"),
                "capabilities": list(route.get("capabilities") or []),
                "credential_env": route.get("credential_env"),
                "key_present": bool(route.get("credential_env")
                                     and os.environ.get(route["credential_env"])),
            }
        return {"ok": True, "routes": route_catalog,
                "workloads": access.get("workloads") or {},
                "profiles": profiles, "preferences": list_preferences()}
    except Exception as exc:  # noqa: BLE001 - read-only status boundary
        logger.exception("model_routes_status_failed")
        return {"ok": False, "error": str(exc)}


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
        "core_change": bool(flight["tiers"]["core"]),
    }


@app.post("/api/selfedit/run")
def selfedit_run(body: GoalIn) -> dict:
    """Start an upgrade run in the background; poll GET /api/selfedit/run.

    G2: prefer {staging_id} (from POST /api/selfedit/stage) over the bare
    {goal, profile?} form — the staged record is the source of truth for
    what was actually previewed. The bare form still works for one release
    (logged as a deprecation signal), so an older mcp_selfedit build in the
    field doesn't break."""
    staging_id = (body.staging_id or "").strip()
    bare_goal = (body.goal or "").strip()
    # Refuse a confirm that lands during a live run BEFORE touching the
    # staging (2026-09-07 review, F4): the pop used to come first, so the
    # refusal itself consumed the preview the user had just approved.
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
        profile = rec["profile"]
        plan_path = rec["plan_path"] or ""
        run_id = rec.get("run_id")
        target_paths = list(rec.get("target_paths") or [])
    else:
        goal = bare_goal
        logger.warning(
            "selfedit_run_stateless_confirm goal=%r — pass staging_id instead "
            "(deprecated fallback, see G2)", goal,
        )
        profile = body.profile
        plan_path = (body.plan_path or "").strip()
        run_id = (body.run_id or "").strip() or None
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
        return _begin_authoring(goal, run_id, target_paths)

    plan = body.plan
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
        _run_job.update(
            state="running", cancel_requested=False,
            goal=goal,
            profile=agent.model_label(),
            summary=None,
            started_at=time.time(),
            finished_at=None,
            submitted=False,
            pr_url=None,
        )
    # D17 — every self-edit state transition is logged.
    logger.info("selfedit_state_transition state=running goal=%r", goal)
    threading.Thread(
        target=_run_agent, args=(goal, profile, plan, run_id), daemon=True,
    ).start()
    return {"ok": True, "started": True, "profile": agent.model_label()}


@app.get("/api/selfedit/run")
def selfedit_run_status() -> dict:
    with _run_lock:
        job = dict(_run_job)
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
        "opening": dict(_opening_job),
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
    result = selfedit_write(SelfEditWriteIn(path=path, content=content, rationale=rationale))
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
    if not _selfedit_service.branch:
        return {"ok": False, "error": "no open self-edit session"}
    if not _selfedit_service.proposals:
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
            run_id=_selfedit_service.run_id, started_at=time.time(), finished_at=None,
        )
    logger.info("selfedit_state_transition state=finish_validating run_id=%s",
                _selfedit_service.run_id)
    threading.Thread(target=_run_finish, daemon=True).start()
    return {"ok": True, "started": True, "state": "validating"}


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
    global _appbuild_workspace, _appbuild_agent_instance
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
        _appbuild_workspace = None
        _appbuild_agent_instance = None
        _appbuild_job.update(
            state="running", app=app_name, goal=goal, cancel_requested=False,
            submitted=False, pr_url=None,
            profile=agent.model_label(), summary=None,
            started_at=time.time(), finished_at=None,
        )
    logger.info("appbuild_state_transition state=running app=%r goal=%r", app_name, goal)
    threading.Thread(
        target=_run_appbuild_agent, args=(app_name, goal, body.profile, plan), daemon=True,
    ).start()
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
def appbuild_job_status() -> dict:
    _recover_appbuild_workspace()
    with _appbuild_lock:
        job = dict(_appbuild_job)
        workspace = _appbuild_workspace
    status = workspace.status() if workspace is not None else {"active": False}
    if job["state"] == "idle" and status.get("id"):
        job.update(state="recovered", app=status.get("app"), goal=status.get("goal"),
                   summary="Reopened the saved workspace. The earlier planner is not running.")
    return {"ok": True, "job": job, "status": status}


def _submit_appbuild(workspace, operation_id, output):
    try:
        result = workspace.submit()
    except Exception:
        logger.exception("app workspace submission failed")
        result = {"ok": False, "error": "App submission failed; inspect the saved workspace before retrying."}
    output["result"] = result
    with _appbuild_lock:
        if _appbuild_job.get("operation_id") == operation_id:
            _appbuild_job.update(state="done" if result.get("ok") else
                ("cancelled" if _appbuild_job.get("cancel_requested") else "error"),
                submitted=bool(result.get("ok")), pr_url=result.get("pr_url"),
                summary=result.get("notice") or result.get("error") or "Draft pull request opened.",
                finished_at=time.time())


@app.post("/api/appbuild/submit")
def appbuild_submit() -> dict:
    workspace = _recover_appbuild_workspace()
    with _appbuild_lock:
        if _appbuild_job["state"] in {"running", "submitting"}:
            return {"ok": False, "error": "an app build is in progress — ask for status instead"}
        if workspace is None or not workspace.branch:
            return {"ok": False, "error": "no active app-build session to submit"}
        operation_id = uuid.uuid4().hex
        _appbuild_job.update(state="submitting", operation_id=operation_id, cancel_requested=False,
                            submitted=False, pr_url=None, finished_at=None)
    output = {}
    worker = threading.Thread(target=_submit_appbuild, args=(workspace, operation_id, output), daemon=True)
    worker.start()
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
    if not _research_enabled():
        return {"ok": False, "error": RESEARCH_DISABLED_MESSAGE}
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
        if _research_job["state"] == "running":
            return {
                "ok": False,
                "error": "a comparison is already in progress — ask for status instead",
                "job": dict(_research_job),
            }
        _research_job.update(
            state="running", urls=urls, focus=(body.focus or "").strip() or None,
            sites=None, comparison=None, model=None, credits_used=None, error=None,
            started_at=time.time(), finished_at=None, saved_path=None, save_error=None,
        )
    logger.info("research_state_transition state=running urls=%r", urls)
    threading.Thread(
        target=_run_research_job, args=(urls, body.focus or ""), daemon=True,
    ).start()
    return {"ok": True, "started": True}


@app.get("/api/research/job")
def research_job_status() -> dict:
    with _research_lock:
        job = dict(_research_job)
    return {"ok": True, "job": job}


@app.post("/api/research/save")
def research_save(body: ResearchSaveIn) -> dict:
    """Save through the guarded sandbox editor. Attribution names model, URLs, page
    counts, and credits — a comparison without its sources and cost is a
    claim with no provenance (R6/R8)."""
    with _research_lock:
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
    result = _save_document_to_sandbox(
        path, comparison + footer,
        rationale=f"Site comparison: {', '.join(urls)}",
    )
    if result.get("ok"):
        with _research_lock:
            _research_job.update(saved_path=result.get("path"), save_error=None)
    else:
        with _research_lock:
            _research_job.update(save_error=result.get("error"))
    return dict(result)


@app.post("/api/research/cancel")
def research_cancel() -> dict:
    if _research_busy():
        return {"ok": False, "error": "a comparison is in progress — ask for status instead"}
    with _research_lock:
        if _research_job["state"] == "idle":
            return {"ok": True, "already_idle": True}
        _research_job.update(
            state="idle", urls=None, focus=None, sites=None, comparison=None,
            model=None, credits_used=None, error=None, started_at=None,
            finished_at=None, saved_path=None, save_error=None,
        )
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
    except Exception:  # noqa: BLE001 — a panel must never break the sidecar
        logger.exception("memory_reviews_list_failed")
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
    except Exception:  # noqa: BLE001 — a panel must never break the sidecar
        logger.exception("memory_reviews_resolve_failed id=%s", review_id)
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
            target=_run_plan_council,
            args=(goal, body.members, context, (body.run_id or "").strip() or None), daemon=True,
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
    """Save the finished plan through the guarded sandbox editor.
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

    result = _save_document_to_sandbox(
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
