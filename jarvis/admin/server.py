"""Sidecar admin API (upgrade plan §10 U1.5-G3).

Localhost-only FastAPI service backing the console's Git panel. Every write
endpoint goes through the same draft → confirm → commit machinery as the
voice path (mcp_git.logic) — the panel is a second front end, not a bypass.

Run: scripts/run_admin.sh  (binds 127.0.0.1:7861)
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from mcp_servers.mcp_git import logic

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


def main() -> None:
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=7861, log_level="warning")


if __name__ == "__main__":
    main()
