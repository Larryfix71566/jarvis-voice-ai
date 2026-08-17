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

    # Selection order mirrors upgrade_agent.resolve_profile: an explicit
    # (spoken) choice, then the JARVIS_UPGRADE_PROFILE env override, then
    # the registry default. Ignoring the env override here sends the user
    # to a planner whose key they deliberately replaced.
    chosen = (
        profile
        or os.environ.get("JARVIS_UPGRADE_PROFILE")
        or next((m["name"] for m in models if m.get("default")), None)
    )
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


# ------------------------------------------------------- planning pathway
# MORTIMER_PLANNING_PATHWAY_PLAN.md P7. Same thin-HTTP-client, two-phase-
# confirmation conventions as the self-edit tools above — no planning
# logic lives here, only the sidecar's /api/plan/* pass-throughs shaped
# into spoken-friendly summaries.


def plan_start(
    client, goal: str, mode: str = "single", profile: str | None = None,
    confirm: bool = False, review_path: str = "",
) -> dict[str, Any]:
    """Two-phase start of a planning job. `mode` is 'single' (one named
    model authors the plan) or 'council' (every usable model drafts a
    full plan in parallel; the user chooses among them with plan_choose).
    REVIEW_PATH, when set, reviews that existing repo document instead of
    authoring a new plan — use this whenever the user asks to have a
    plan, spec, or document reviewed, critiqued, or checked by a model."""
    goal = (goal or "").strip()
    if not goal:
        return {"ok": False, "error": "I need a goal — what should the plan cover?"}
    mode = (mode or "single").strip().lower()
    if mode not in ("single", "council"):
        return {
            "ok": False,
            "error": "mode must be 'single' (one model) or 'council' "
                     "(parallel drafts you choose between).",
        }
    review_path = (review_path or "").strip()
    is_review = bool(review_path)

    if not confirm:
        if is_review:
            if mode == "single":
                summary = (
                    f"Ready to have {profile or 'the default planner'} review "
                    f"{review_path}. This can take a few minutes. Say yes to start."
                )
            else:
                summary = (
                    f"Ready to have the council draft parallel reviews of "
                    f"{review_path}, so you can choose between them. This can "
                    f"take a few minutes. Say yes to start."
                )
        elif mode == "single":
            summary = (
                f"Ready to draft a plan for “{goal}” with "
                f"{profile or 'the default planner'}. This can take a few "
                f"minutes. Say yes to start."
            )
        else:
            summary = (
                f"Ready to have the council draft parallel plans for "
                f"“{goal}”, so you can choose between them. This can take "
                f"a few minutes. Say yes to start."
            )
        return {
            "ok": True, "needs_confirmation": True, "summary": summary,
            "goal": goal, "mode": mode, "profile": profile,
            "review_path": review_path or None,
        }

    resp = _call(lambda: client.post(
        "/api/plan/start", json={
            "goal": goal, "mode": mode, "profile": profile,
            "review_path": review_path,
        },
    ))
    if not resp.get("ok"):
        return resp
    if is_review:
        if mode == "single":
            summary = (
                f"Started the review with {profile or 'the default planner'}. "
                f"This can take a few minutes — ask me how it's coming along anytime."
            )
        else:
            summary = (
                "Started the council drafting parallel reviews. This can take "
                "a few minutes — ask me when they're ready."
            )
    elif mode == "single":
        summary = (
            f"Started drafting the plan with {profile or 'the default planner'}. "
            f"This can take a few minutes — ask me how it's coming along anytime."
        )
    else:
        summary = (
            "Started the council drafting parallel plans. This can take a "
            "few minutes — ask me when they're ready."
        )
    return {"ok": True, "started": True, "summary": summary}


def plan_status(client) -> dict[str, Any]:
    """Report the current planning job: still drafting, candidates ready
    to choose between, or a finished plan ready to adopt."""
    resp = _call(lambda: client.get("/api/plan/job"))
    if not resp.get("ok"):
        return resp
    job = resp.get("job", {}) or {}
    state = job.get("state")
    # R5 — say "review" instead of "plan" when the polled job carries a
    # review_path.
    noun = "review" if job.get("review_path") else "plan"

    if state in (None, "idle"):
        return {"ok": True, "summary": "No planning job is active.", "job": job}
    if state == "running":
        mode = job.get("mode") or "planning"
        return {
            "ok": True,
            "summary": (
                f"Still drafting ({mode} mode) — goal: “{job.get('goal', '')}”. "
                f"I'll keep at it."
            ),
            "job": job,
        }
    if state == "error":
        return {
            "ok": True,
            "summary": f"The planning job failed: {job.get('error') or 'unknown error'}",
            "job": job,
        }
    if state == "awaiting_choice":
        candidates = job.get("candidates") or []
        parts = []
        for c in candidates:
            score = c.get("advisory_mean")
            score_note = f" (advisory score {score:.1f})" if score is not None else ""
            parts.append(f"{c['label']} by {c['profile']}{score_note}")
        return {
            "ok": True,
            "summary": (
                f"{len(candidates)} candidate {noun}(s) are ready: "
                + "; ".join(parts) + ". Which one would you like?"
            ),
            "job": job,
        }
    if state == "done":
        return {
            "ok": True,
            "summary": (
                f"The {noun} is ready, drafted by {job.get('author') or 'the planner'}. "
                f"Say the word and I'll save it as a draft for your review."
            ),
            "job": job,
        }
    return {"ok": True, "summary": "Planning status unknown.", "job": job}


def plan_choose(client, label: str) -> dict[str, Any]:
    """Choose one candidate from a council-mode planning round. No
    confirmation phase — choosing among drafts is not a write."""
    label = (label or "").strip()
    if not label:
        return {"ok": False, "error": "which candidate? name its label, e.g. Proposal A."}
    resp = _call(lambda: client.post("/api/plan/choose", json={"label": label}))
    if not resp.get("ok"):
        return resp
    return {
        "ok": True,
        "summary": (
            f"Chose {label}. Say the word and I'll save it as a draft "
            f"for your review."
        ),
    }


def plan_adopt(client, path: str | None = None, confirm: bool = False) -> dict[str, Any]:
    """Two-phase: save the finished plan as a draft repo write (the same
    draft-gated action_id flow as repo_write_file/repo_commit_write —
    nothing is committed by this call, confirm or not)."""
    status = _call(lambda: client.get("/api/plan/job"))
    if not status.get("ok"):
        return status
    job = status.get("job", {}) or {}
    if job.get("state") != "done":
        return {"ok": False, "error": "there's no finished plan to adopt yet."}
    # R5 — say "review" instead of "plan" when the polled job carries a
    # review_path; the adopt preview names the docs/reviews/ default.
    noun = "review" if job.get("review_path") else "plan"
    default_dir = "docs/reviews/" if job.get("review_path") else "docs/plans/"

    if not confirm:
        target = path or f"a {default_dir} file named after the goal"
        return {
            "ok": True,
            "needs_confirmation": True,
            "summary": (
                f"Ready to save the {noun} as a draft at {target}. Say yes to "
                f"draft it — nothing is written until you separately confirm "
                f"the write itself."
            ),
            "path": path,
        }

    resp = _call(lambda: client.post("/api/plan/adopt", json={"path": path}))
    if not resp.get("ok"):
        return resp
    return {
        "ok": True,
        "pending": resp.get("pending"),
        "action_id": resp.get("action_id"),
        "path": resp.get("path"),
        "summary": (
            f"Drafted the {noun} at {resp.get('path')} — nothing has been "
            f"written yet. Say the word to commit it."
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
