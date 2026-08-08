"""Sidecar admin API (upgrade plan §10 U1.5-G3).

Localhost-only FastAPI service backing the console's Git panel and the
self-development Edit mode. Every write endpoint goes through draft →
confirm → commit machinery (mcp_git.logic) or the sandboxed self-edit
service (jarvis.selfedit) — the panels are front ends, not bypasses.

Self-edit endpoints (plan §3/§3.5):
- POST /api/selfedit/run      {goal}  — start a session and run the Upgrade
  Agent synchronously; returns the agent summary + proposals. (v1 blocks;
  an agent run can take minutes.)
- GET  /api/selfedit/status           — session state, proposals, validation
- POST /api/selfedit/validate         — run the validation gate
- POST /api/selfedit/submit           — commit/push/open PR (needs validation)
- POST /api/selfedit/revert           — drop the session, restore rollback tag

There is deliberately no merge endpoint. Merging happens on GitHub only.

Run: scripts/run_admin.sh  (binds 127.0.0.1:7861)
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from jarvis.agents.upgrade_agent import UpgradeAgent
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


# Single self-edit session for the sidecar process (plan §3: one at a time).
_selfedit_service = SelfEditService()


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


@app.get("/api/selfedit/status")
def selfedit_status() -> dict:
    return _selfedit_service.status()


@app.post("/api/selfedit/run")
def selfedit_run(body: GoalIn) -> dict:
    """Start (or continue) a session and let the Upgrade Agent work the goal."""
    agent = UpgradeAgent(_selfedit_service)
    return agent.run(body.goal)


@app.post("/api/selfedit/validate")
def selfedit_validate() -> dict:
    return _selfedit_service.validate()


@app.post("/api/selfedit/submit")
def selfedit_submit() -> dict:
    return _selfedit_service.submit()


@app.post("/api/selfedit/revert")
def selfedit_revert() -> dict:
    return _selfedit_service.revert()


def main() -> None:
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=7861, log_level="warning")


if __name__ == "__main__":
    main()
