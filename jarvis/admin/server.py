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
import sys
import threading
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from jarvis.agents.upgrade_agent import (
    UnknownModelProfileError,
    UpgradeAgent,
    available_models,
)
from jarvis import memory as memory_module
from jarvis.council import council as council_mod
from jarvis.db import get_conn, run_migrations
from jarvis.runlog import get_run, list_runs, parse_since
from jarvis.selfedit.service import SelfEditService
from jarvis.vault import inject_env
from mcp_servers.mcp_git import logic

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


class ConveneIn(BaseModel):
    placement: str
    goal: str | None = None
    # D9/D10 wire-format completion (see jarvis/council/config.py's
    # module docstring): the console's per-tier membership picker
    # narrows which registry profiles are eligible, keyed by tier name
    # (economy/mid/frontier). Omitted/empty per tier falls back to that
    # tier's full registry membership.
    members: dict[str, list[str]] | None = None


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


def _make_agent(service: SelfEditService, profile: str | None) -> UpgradeAgent:
    """Construct the planner (seam for tests)."""
    return UpgradeAgent(service, profile=profile)


def _run_agent(goal: str, profile: str | None) -> None:
    """Background thread target: plan edits, then settle the job state."""
    try:
        agent = _make_agent(_selfedit_service, profile)
        result = agent.run(goal)
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
    threading.Thread(target=_run_agent, args=(goal, body.profile), daemon=True).start()
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
    return {"ok": True, "reminder": reminder, "summary": summary}


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
