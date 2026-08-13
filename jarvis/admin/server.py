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

import logging
import threading
import time
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from jarvis.agents.upgrade_agent import (
    UnknownModelProfileError,
    UpgradeAgent,
    available_models,
)
from jarvis import memory as memory_module
from jarvis.db import get_conn, run_migrations
from jarvis.selfedit.service import SelfEditService
from mcp_servers.mcp_git import logic

logger = logging.getLogger(__name__)

app = FastAPI(title="jarvis-admin", docs_url=None, redoc_url=None, openapi_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


class MessageIn(BaseModel):
    message: str


class ActionIn(BaseModel):
    action_id: int


class GoalIn(BaseModel):
    goal: str
    profile: str | None = None


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


def _make_agent(service: SelfEditService, profile: str | None) -> UpgradeAgent:
    """Construct the planner (seam for tests)."""
    return UpgradeAgent(service, profile=profile)


def _run_agent(goal: str, profile: str | None) -> None:
    """Background thread target: plan edits, then settle the job state."""
    try:
        agent = _make_agent(_selfedit_service, profile)
        result = agent.run(goal)
        with _run_lock:
            _run_job.update(
                state="done" if result.get("ok") else "error",
                summary=result.get("summary", ""),
                finished_at=time.time(),
            )
    except Exception as exc:  # planner crash must still settle the job
        logger.exception("upgrade run crashed")
        with _run_lock:
            _run_job.update(
                state="error",
                summary=f"upgrade run crashed: {type(exc).__name__}: {exc}",
                finished_at=time.time(),
            )


def _busy() -> bool:
    with _run_lock:
        return _run_job["state"] == "running"


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
    return _selfedit_service.validate()


@app.post("/api/selfedit/submit")
def selfedit_submit() -> dict:
    if _busy():
        return {"ok": False, "error": "an upgrade run is in progress — ask for status instead"}
    return _selfedit_service.submit()


@app.post("/api/selfedit/revert")
def selfedit_revert() -> dict:
    if _busy():
        return {"ok": False, "error": "an upgrade run is in progress — ask for status instead"}
    return _selfedit_service.revert()


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


@app.delete("/api/memory/fact/{key}")
def memory_delete_fact(key: str) -> dict:
    run_migrations()
    with get_conn() as conn:
        deleted = memory_module.delete_fact(conn, key)
    if not deleted:
        return {"ok": False, "error": f"No fact with key '{key}'."}
    return {"ok": True, "key": key}


def main() -> None:
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=7861, log_level="warning")


if __name__ == "__main__":
    main()
