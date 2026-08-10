"""Thin HTTP client of the admin sidecar for the self-development loop.

This module contains NO git operations and NO planner logic — the admin
sidecar (jarvis/admin/server.py, 127.0.0.1:7861) is the single owner of the
SelfEditService and every git mutation. These functions only call its HTTP
API and shape the responses into spoken-friendly summaries, so the Developer
sub-agent can drive the whole loop by voice.

Every mutating tool follows the repo's two-phase confirmation pattern
(preview with confirm=false, act with confirm=true), mirroring
mcp_git.prepare_commit/commit and mcp_apps.app_create.
"""

from __future__ import annotations

import os
from typing import Any

DEFAULT_ADMIN_URL = "http://127.0.0.1:7861"
ADMIN_URL_ENV = "JARVIS_ADMIN_URL"

OFFLINE_ERROR = (
    "the admin sidecar looks offline — it runs the self-development loop. "
    "Start the stack with ./scripts/mortimer.sh (or ./scripts/run_admin.sh) "
    "and ask me again."
)


class AdminClient:
    """Duck-typed httpx.Client wrapper so tests can inject a fake."""

    def __init__(self, base_url: str | None = None, timeout: float = 10.0):
        import httpx  # local import: keeps module import light for tests

        self._client = httpx.Client(
            base_url=base_url or os.environ.get(ADMIN_URL_ENV) or DEFAULT_ADMIN_URL,
            timeout=timeout,
        )

    def get(self, path: str) -> dict[str, Any]:
        return self._client.get(path).json()

    def post(self, path: str, json: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._client.post(path, json=json).json()


def _call(fn) -> dict[str, Any]:
    """Run one admin call, mapping any transport failure to the offline error."""
    try:
        return fn()
    except Exception:
        return {"ok": False, "error": OFFLINE_ERROR}


def _format_models(models: list[dict[str, Any]]) -> str:
    parts = []
    for m in models:
        flag = "" if m.get("key_present") else " (key missing)"
        dflt = " (default)" if m.get("default") else ""
        parts.append(f"{m['name']}{dflt}{flag}")
    return ", ".join(parts) if parts else "none"


def selfedit_start(client, goal: str, profile: str | None = None, confirm: bool = False) -> dict[str, Any]:
    """Two-phase start of an upgrade run (preview, then confirm)."""
    goal = (goal or "").strip()
    if not goal:
        return {"ok": False, "error": "I need a goal — what should I change about myself?"}

    models_resp = _call(lambda: client.get("/api/selfedit/models"))
    if not models_resp.get("ok"):
        return models_resp
    models = models_resp.get("models", [])
    by_name = {m["name"]: m for m in models}

    chosen = profile or next((m["name"] for m in models if m.get("default")), None)
    if chosen and chosen not in by_name:
        return {
            "ok": False,
            "error": (
                f"I don't know a planner called '{chosen}'. "
                f"Available planners: {_format_models(models)}."
            ),
        }
    if chosen and not by_name[chosen].get("key_present"):
        return {
            "ok": False,
            "error": (
                f"the {by_name[chosen]['key_env']} environment variable is not set, "
                f"so the {chosen} planner can't run — add it to .env and restart, "
                f"or pick another planner: {_format_models(models)}."
            ),
        }

    if not confirm:
        return {
            "ok": True,
            "needs_confirmation": True,
            "summary": (
                f"Ready to plan this edit with {chosen or 'the default planner'}: "
                f"“{goal}”. Planning runs in the background and can take several "
                f"minutes; I can check progress anytime. Say yes to start."
            ),
            "goal": goal,
            "profile": chosen,
        }

    run_resp = _call(lambda: client.post("/api/selfedit/run", json={"goal": goal, "profile": chosen}))
    if not run_resp.get("ok"):
        return run_resp
    return {
        "ok": True,
        "started": True,
        "summary": (
            f"Started planning with {run_resp.get('profile', chosen)}. This can take "
            f"several minutes — ask me how the edit is coming along anytime."
        ),
        "profile": run_resp.get("profile", chosen),
    }


def selfedit_status(client) -> dict[str, Any]:
    """Compose the run job + session state into one spoken summary."""
    resp = _call(lambda: client.get("/api/selfedit/run"))
    if not resp.get("ok"):
        return resp
    job = resp.get("job", {})
    status = resp.get("status", {}) or {}

    if job.get("state") == "running":
        return {
            "ok": True,
            "summary": (
                f"Still planning with {job.get('profile', 'the planner')} — "
                f"goal: “{job.get('goal', '')}”. I'll keep at it."
            ),
            "job": job,
        }

    parts: list[str] = []
    if job.get("state") in ("done", "error") and job.get("summary"):
        parts.append(str(job["summary"]))

    if status.get("active"):
        proposals = status.get("proposals", []) or []
        if proposals:
            parts.append(
                "Proposed edits: "
                + "; ".join(f"{p['path']} — {p.get('rationale', '')}" for p in proposals)
            )
        else:
            parts.append("The session is active but no edits have been proposed yet.")
        if status.get("validated_ok"):
            parts.append("Validation has passed — say the word and I'll submit the pull request.")
        if status.get("pr_url"):
            parts.append(f"Pull request: {status['pr_url']} — merging is yours on GitHub.")
    elif not parts:
        parts.append("No upgrade run or edit session is active right now.")

    return {"ok": True, "summary": " ".join(parts), "job": job, "active": bool(status.get("active"))}


def selfedit_validate(client) -> dict[str, Any]:
    """Run the validation pipeline (read-only — no confirmation needed)."""
    resp = _call(lambda: client.post("/api/selfedit/validate"))
    if not resp.get("ok"):
        return resp
    failed = [c for c in resp.get("checks", []) if not c.get("ok")]
    if failed:
        detail = "; ".join(f"{c['name']}: {c.get('output', '')[:200]}" for c in failed)
        return {"ok": False, "error": f"validation failed — {detail}"}
    return {
        "ok": True,
        "validated_ok": True,
        "summary": (
            "Validation passed: edits stay inside the allowlist, the backend still "
            "imports, and the frontend still builds. Review the diffs, then tell me "
            "to submit the pull request."
        ),
    }


def selfedit_submit(client, confirm: bool = False) -> dict[str, Any]:
    """Two-phase PR submission. Only valid after validation has passed."""
    status = _call(lambda: client.get("/api/selfedit/run"))
    if not status.get("ok"):
        return status
    if status.get("job", {}).get("state") == "running":
        return {"ok": False, "error": "the planner is still working — ask for status instead."}
    sess = status.get("status", {}) or {}
    if not sess.get("active"):
        return {"ok": False, "error": "there's no edit session to submit — start one first."}
    if not sess.get("proposals"):
        return {"ok": False, "error": "no edits have been proposed yet."}
    if not sess.get("validated_ok"):
        return {"ok": False, "error": "validation hasn't passed — run validation first."}

    if not confirm:
        files = ", ".join(p["path"] for p in sess["proposals"])
        return {
            "ok": True,
            "needs_confirmation": True,
            "summary": (
                f"Ready to open a pull request with these edits: {files}. "
                f"I cannot merge it — merging always stays with you on GitHub. "
                f"Say ‘submit the PR’ to proceed."
            ),
        }

    resp = _call(lambda: client.post("/api/selfedit/submit"))
    if not resp.get("ok"):
        return resp
    return {
        "ok": True,
        "pr_url": resp.get("pr_url"),
        "summary": (
            f"Pull request opened: {resp.get('pr_url')}. Review and merge it on "
            f"GitHub — I cannot merge it myself."
        ),
    }


def selfedit_revert(client, confirm: bool = False) -> dict[str, Any]:
    """Two-phase revert: discard the edit session entirely."""
    status = _call(lambda: client.get("/api/selfedit/run"))
    if not status.get("ok"):
        return status
    if status.get("job", {}).get("state") == "running":
        return {"ok": False, "error": "the planner is still working — wait for it to finish first."}
    sess = status.get("status", {}) or {}
    if not sess.get("active"):
        return {"ok": False, "error": "there's no edit session to revert."}

    if not confirm:
        n = len(sess.get("proposals", []) or [])
        return {
            "ok": True,
            "needs_confirmation": True,
            "summary": (
                f"This discards the whole edit session — {n} proposed edit(s) on "
                f"{sess.get('branch', 'the sandbox branch')} — and restores the repo. "
                f"Say yes to revert."
            ),
        }

    resp = _call(lambda: client.post("/api/selfedit/revert"))
    if not resp.get("ok"):
        return resp
    return {"ok": True, "summary": "Done — the edit session is gone and the repo is back to normal."}
