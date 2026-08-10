"""Admin sidecar (127.0.0.1:7861) — SINGLE OWNER of the self-edit service.

All git operations for the self-development loop happen in this process and
nowhere else. Both the console's Edit panel (HTTP, below) and the
mcp_selfedit skill server (which gives the Developer sub-agent voice access)
are thin clients of these endpoints — that avoids two processes doing
``git checkout`` on the live repo.

Endpoints
---------
GET  /api/health                    liveness
GET  /api/selfedit/models           planner model registry (key presence only)
POST /api/selfedit/run              start an upgrade run — ASYNC (background
                                    thread), because planning takes minutes
                                    and voice turns cannot block
GET  /api/selfedit/run              poll the current/last run job
GET  /api/selfedit/status           session + proposals + validation state
POST /api/selfedit/validate         run the validation pipeline (sync)
POST /api/selfedit/submit           open the PR (refused unless validated)
POST /api/selfedit/revert           discard the session

While a run is in progress, mutating endpoints (validate/submit/revert) and
new runs are refused with a spoken-friendly error — ask for status instead.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from jarvis.agents.upgrade_agent import (
    UnknownModelProfileError,
    UpgradeAgent,
    available_models,
)
from jarvis.selfedit.service import SelfEditError, SelfEditService

app = FastAPI(title="mortimer-admin")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_service = SelfEditService()
_service_lock = threading.RLock()

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


class GoalIn(BaseModel):
    goal: str
    profile: str | None = None


def _make_agent(service: SelfEditService, profile: str | None) -> UpgradeAgent:
    """Construct the planner (seam for tests)."""
    return UpgradeAgent(service, profile=profile)


def _run_agent(goal: str, profile: str | None) -> None:
    """Background thread target: plan edits, then settle the job state."""
    try:
        agent = _make_agent(_service, profile)
        result = agent.run(goal)
        with _run_lock:
            _run_job.update(
                state="done" if result.get("ok") else "error",
                summary=result.get("summary", ""),
                finished_at=time.time(),
            )
    except Exception as exc:  # planner crash must still settle the job
        with _run_lock:
            _run_job.update(
                state="error",
                summary=f"upgrade run crashed: {type(exc).__name__}: {exc}",
                finished_at=time.time(),
            )


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"ok": True}


@app.get("/api/selfedit/models")
def models() -> dict[str, Any]:
    return {"ok": True, "models": available_models()}


@app.post("/api/selfedit/run")
def run(body: GoalIn) -> dict[str, Any]:
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
            # Construct now so an unknown profile or missing key fails fast,
            # synchronously, before we report the run as started.
            agent = _make_agent(_service, body.profile)
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
def run_status() -> dict[str, Any]:
    with _run_lock:
        job = dict(_run_job)
    return {"ok": True, "job": job, "status": _service.status()}


@app.get("/api/selfedit/status")
def status() -> dict[str, Any]:
    with _run_lock:
        busy = _run_job["state"] == "running"
    if busy:
        return {"ok": False, "error": "an upgrade run is in progress — ask for status instead"}
    with _service_lock:
        return _service.status()


@app.post("/api/selfedit/validate")
def validate() -> dict[str, Any]:
    with _run_lock:
        busy = _run_job["state"] == "running"
    if busy:
        return {"ok": False, "error": "an upgrade run is in progress — ask for status instead"}
    with _service_lock:
        try:
            return _service.validate()
        except SelfEditError as exc:
            return {"ok": False, "error": str(exc)}


@app.post("/api/selfedit/submit")
def submit() -> dict[str, Any]:
    with _run_lock:
        busy = _run_job["state"] == "running"
    if busy:
        return {"ok": False, "error": "an upgrade run is in progress — ask for status instead"}
    with _service_lock:
        try:
            return _service.submit()
        except SelfEditError as exc:
            return {"ok": False, "error": str(exc)}


@app.post("/api/selfedit/revert")
def revert() -> dict[str, Any]:
    with _run_lock:
        busy = _run_job["state"] == "running"
    if busy:
        return {"ok": False, "error": "an upgrade run is in progress — ask for status instead"}
    with _service_lock:
        try:
            return _service.revert()
        except SelfEditError as exc:
            return {"ok": False, "error": str(exc)}
