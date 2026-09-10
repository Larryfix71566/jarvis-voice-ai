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

    def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._client.get(path, params=params).json()

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


def selfedit_start(
    client,
    goal: str = "",
    profile: str | None = None,
    confirm: bool = False,
    plan_path: str = "",
    staging_id: str = "",
    run_id: str = "",
    target_paths: list[str] | None = None,
) -> dict[str, Any]:
    """Two-phase start of an upgrade run (preview, then confirm).

    TARGET_PATHS (2026-09-07): the repo files the edit will CHANGE. The
    sidecar's preflight classifies these (Tier 0 / B / routine) instead of
    whatever paths the goal prose mentions, so "add a line about
    jarvis/model_catalog.py to docs/REPO_MAP.md" is a docs edit, not a
    core one.

    PLAN_PATH, when set, names a repo plan/spec document the sidecar reads
    and injects into the run — use it whenever the user asks to implement
    an existing plan, spec, or phase document.

    G2 (MORTIMER_SESSION_GAPS_AND_SELFEDIT_CONVERGENCE_PLAN.md): the
    confirm=false call now STAGES the preview on the sidecar (POST
    /api/selfedit/stage) and returns a `staging_id`. Pass that SAME
    staging_id back with confirm=true instead of restating goal/profile —
    the sidecar replays the exact staged record, so nothing can drift
    between preview and confirm. GOAL/PROFILE on the confirm=true call are
    then optional and ignored when staging_id is present; they remain
    required (goal) for a bare confirm=true with no staging_id, which
    still works for one release as a deprecated fallback."""
    staging_id = (staging_id or "").strip()

    # Confirm path with a staging_id — or with no goal at all — replays the
    # sidecar's staged record. The sidecar resolves a mangled or missing id
    # to the single live staging (2026-09-07: 'stg-…' and '43' both arrived
    # here and bounced the user back to a fresh preview for a typo the
    # sidecar could see through) and refuses, naming them, when more than
    # one is live.
    if confirm and (staging_id or not (goal or "").strip()):
        # SE3 — author=true asks the sidecar to open the session and hand it
        # back so THIS agent writes the change, instead of restating the
        # goal to a planner that starts with no map of the repo. A staged
        # record carrying a plan_path still goes to the planner; the
        # sidecar decides, from fields, not from anything said here.
        run_resp = _call(
            lambda: client.post(
                "/api/selfedit/run",
                json={"staging_id": staging_id, "author": True},
            )
        )
        if not run_resp.get("ok"):
            return run_resp
        if run_resp.get("opening"):
            return {"ok": True, "started": True, "opening": True,
                    "summary": "The isolated workspace is being prepared. Ask for self-edit status; edits can begin when it is ready."}
        session = run_resp.get("session")
        if session:
            return _describe_session(session)
        return {
            "ok": True,
            "started": True,
            "summary": (
                f"Started planning with {run_resp.get('profile', 'the chosen planner')}. "
                f"This can take several minutes — ask me how the edit is coming "
                f"along anytime."
            ),
            "profile": run_resp.get("profile"),
            # G7 — same value, explicit name: this is the field the Agents-
            # tab card actually looks for on this tool's result.
            "planner_model": run_resp.get("profile"),
        }

    goal = (goal or "").strip()
    if not goal:
        return {"ok": False, "error": "I need a goal — what should I change about myself?"}
    plan_path = (plan_path or "").strip()

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
        # G2 — stage the preview on the sidecar; the returned staging_id is
        # what the confirm=true call must pass back.
        targets = [t.strip() for t in (target_paths or []) if t and t.strip()]
        stage_resp = _call(lambda: client.post(
            "/api/selfedit/stage",
            json={"goal": goal, "profile": chosen, "plan_path": plan_path or None,
                  "run_id": run_id or None, "target_paths": targets or None},
        ))
        if not stage_resp.get("ok"):
            return stage_resp
        sid = stage_resp.get("staging_id", "")
        seeded = f", seeded with the plan at {plan_path}" if plan_path else ""
        # Tier B (MORTIMER_SELFEDIT_TIERS_PLAN.md): the preview SAYS a goal
        # touches the voice/agent core, so the user hears it before yes.
        core_paths = (stage_resp.get("tiers") or {}).get("core") or []
        core_note = (
            f" This touches the voice/agent core ({', '.join(core_paths)}) — "
            f"the PR will be flagged CORE CHANGE and needs a real run before merging."
            if core_paths else ""
        )
        return {
            "ok": True,
            "needs_confirmation": True,
            "summary": (
                f"Ready to make this edit{seeded}: “{goal}”.{core_note} I will "
                f"write the change, validate it, and if every check passes "
                f"open the pull request. Say yes to start (staging_id {sid})."
            ),
            "goal": goal,
            "profile": chosen,
            "staging_id": sid,
            "core_change": bool(core_paths),
        }

    # Deprecated fallback: confirm=true with no staging_id, goal restated.
    payload: dict[str, Any] = {"goal": goal, "profile": chosen, "run_id": run_id or None}
    if plan_path:
        payload["plan_path"] = plan_path
    run_resp = _call(lambda: client.post("/api/selfedit/run", json=payload))
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
        "planner_model": run_resp.get("profile", chosen),  # G7
    }


def _describe_session(session: dict[str, Any]) -> dict[str, Any]:
    """SE3 — the confirm opened a session for THIS agent to write in.

    The summary is an instruction to itself as much as a report: the next
    move is selfedit_read/selfedit_write/selfedit_finish in this same
    delegation, not a status poll waiting for a planner that was never
    launched."""
    targets = session.get("target_paths") or []
    named = f" Files to change: {', '.join(targets)}." if targets else ""
    return {
        "ok": True,
        "started": False,
        "session": session,
        "branch": session.get("branch"),
        "target_paths": targets,
        "summary": (
            f"Session open on {session.get('branch')}.{named} Read each file "
            f"with selfedit_read, write the change with selfedit_write, then "
            f"call selfedit_finish — it validates and opens the pull request "
            f"if every check passes."
        ),
    }


def selfedit_read(client, path: str) -> dict[str, Any]:
    """Read one file from the open session's worktree."""
    path = (path or "").strip()
    if not path:
        return {"ok": False, "error": "which file? selfedit_read needs a repo path"}
    return _call(lambda: client.get("/api/selfedit/file", params={"path": path}))


def selfedit_write(client, path: str, content: str, rationale: str = "",
                   visual_intent: str = "") -> dict[str, Any]:
    """Write one file in the open session's worktree (whole-file content)."""
    path = (path or "").strip()
    if not path:
        return {"ok": False, "error": "which file? selfedit_write needs a repo path"}
    if not (rationale or "").strip():
        return {"ok": False,
                "error": "selfedit_write needs a rationale — one line saying why"}
    resp = _call(lambda: client.post("/api/selfedit/write", json={
        "path": path, "content": content, "rationale": rationale,
        "visual_intent": visual_intent,
    }))
    if not resp.get("ok"):
        return resp
    return {
        "ok": True,
        "path": resp.get("path", path),
        "diff": resp.get("diff", ""),
        "summary": f"Wrote {resp.get('path', path)}. "
                   f"Call selfedit_finish when the change is complete.",
    }


def selfedit_finish(client) -> dict[str, Any]:
    """Validate the session and, if every check passes, open the PR.

    Asynchronous by necessity: jarvis/skills/registry.py's CALL_TIMEOUT is
    30 s and the pytest gate alone runs for minutes. Ask selfedit_status
    for progress."""
    resp = _call(lambda: client.post("/api/selfedit/finish", json={}))
    if not resp.get("ok"):
        return resp
    return {
        "ok": True,
        "started": True,
        "summary": (
            "Validating now — the gates take a few minutes. I'll open the "
            "pull request if every check passes; ask me how it's going "
            "anytime."
        ),
    }


def _describe_finish(finish: dict[str, Any]) -> str:
    """One sentence for the finish job's state, or "" when it never ran."""
    state = (finish or {}).get("state")
    if state in (None, "idle"):
        return ""
    if state == "validating":
        return "Validating the change now — the gates take a few minutes."
    if state == "submitting":
        return "Validation passed; opening the pull request now."
    if state == "done":
        notice = (finish.get("notice") or "").strip()
        pr = finish.get("pr_url") or ""
        return (f"{notice} Pull request: {pr} — merging is yours on GitHub."
                if notice else
                f"Pull request: {pr} — merging is yours on GitHub.")
    if state == "failed":
        failed = [c for c in (finish.get("checks") or []) if not c.get("ok")]
        if failed:
            first = failed[0]
            return (
                f"Validation failed at {first.get('name')}: "
                f"{(first.get('output') or '')[:200]}. The session is still "
                f"open — want me to fix it?"
            )
        return "Validation failed. The session is still open — want me to fix it?"
    if state == "error":
        return (f"The finish step errored: {finish.get('notice') or 'no detail'}. "
                f"The session is still open."
                )
    return ""


def _describe_staging(
    staging_id: str, stagings: list[dict[str, Any]],
) -> tuple[str, bool | None]:
    """One sentence answering "is this staging_id still live", plus the
    machine-readable verdict. Returns ("", None) when no staging_id was
    asked about — the caller then says nothing about staging at all,
    rather than volunteering a state nobody asked for."""
    staging_id = (staging_id or "").strip()
    if not staging_id:
        return "", None
    matched = next(
        (s for s in stagings if s.get("staging_id") == staging_id), None,
    )
    if matched is not None:
        return (
            f"Staging {staging_id} is still live, expires in "
            f"{int(matched.get('expires_in_s', 0))}s."
        ), True
    return (
        f"Staging {staging_id} is not currently live — it may have "
        "already been used to start a run, expired, or never existed. "
        "This is the actual staging list, not a guess."
    ), False


def selfedit_status(client, staging_id: str = "") -> dict[str, Any]:
    """Compose the run job + session state into one spoken summary.

    2026-08-25 — this endpoint used to have NO way to answer "is staging
    X still live": it only ever read _run_job/_selfedit_service.status(),
    entirely separate state from the _selfedit_stagings dict a staging_id
    lives in. A developer run once fabricated "staging expires after 10
    minutes... it's gone" from this exact tool, which could not possibly
    have known that. GET /api/selfedit/run now also returns a `stagings`
    list; when the caller names a staging_id, report plainly whether it is
    present there — never guessed, never inferred from silence."""
    resp = _call(lambda: client.get("/api/selfedit/run"))
    if not resp.get("ok"):
        return resp
    job = resp.get("job", {})
    status = resp.get("status", {}) or {}
    stagings = resp.get("stagings", []) or []
    finish = resp.get("finish", {}) or {}
    finish_sentence = _describe_finish(finish)

    # The staging answer is computed BEFORE the running-state branch and
    # attached to every return path. The first cut computed it only on the
    # idle path, so asking "is staging X live?" during a run returned a
    # cheerful "still planning…" with no staging_found key and no mention
    # of the question at all — a silent non-answer, which is the precise
    # shape that invites the model to fill the gap with an invention. If
    # the question was asked, it gets an answer.
    staging_sentence, staging_found = _describe_staging(staging_id, stagings)

    opening = resp.get("opening", {}) or {}
    if opening.get("state") == "starting" or status.get("phase") in {"creating", "starting"}:
        summary = "The isolated workspace is being prepared; it is not ready for edits yet."
        if staging_sentence:
            summary += " " + staging_sentence
        return {"ok": True, "opening": opening, "summary": summary,
                "stagings": stagings, "staging_found": staging_found}
    if opening.get("state") == "error" and not status.get("active"):
        return {"ok": False, "error": opening.get("error", "Sandbox setup failed"),
                "stagings": stagings, "staging_found": staging_found}

    # SE4 — the finish job is the ONLY thing running on the authored path
    # (no planner job ever started), so it is reported first and on its own.
    if finish.get("state") in ("validating", "submitting"):
        summary = finish_sentence
        if staging_sentence:
            summary = f"{summary} {staging_sentence}"
        return {
            "ok": True, "summary": summary, "job": job, "finish": finish,
            "active": bool(status.get("active")),
            "stagings": stagings, "staging_found": staging_found,
        }

    if job.get("state") == "running":
        summary = (
            f"Still planning with {job.get('profile', 'the planner')} — "
            f"goal: “{job.get('goal', '')}”. I'll keep at it."
        )
        if staging_sentence:
            summary = f"{summary} {staging_sentence}"
        return {
            "ok": True,
            "summary": summary,
            "job": job,
            # G7 — same value as job["profile"], named for what the
            # Agents-tab card looks for on this tool's result.
            "planner_model": job.get("profile"),
            "stagings": stagings,
            "staging_found": staging_found,
        }

    parts: list[str] = []
    if finish_sentence:
        parts.append(finish_sentence)
    if job.get("state") in ("done", "error") and job.get("summary"):
        parts.append(str(job["summary"]))
    if job.get("pr_url"):
        parts.append(f"Pull request: {job['pr_url']} — merging is yours on GitHub.")

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

    if staging_sentence:
        parts.append(staging_sentence)

    return {
        "ok": True, "summary": " ".join(parts), "job": job, "finish": finish,
        "active": bool(status.get("active")),
        "planner_model": job.get("profile"),  # G7
        "stagings": stagings,
        "staging_found": staging_found,
    }


def selfedit_verify_appearance(client, branch_override: bool = False,
                               display: int = 1) -> dict[str, Any]:
    """MORTIMER_DEVELOPER_SECTIONS_AND_VISUAL_VERIFY_PLAN.md B2.

    A CHECK, not a gate: it cannot block a submit and is not part of
    validation. The four validation gates prove the code compiles, imports
    and passes tests; none of them can see the screen.
    """
    return _call(lambda: client.post(
        "/api/selfedit/verify-appearance",
        json={"branch_override": branch_override, "display": display}))


# SE2 (2026-09-07): selfedit_validate and selfedit_submit are GONE as
# tools and as logic. jarvis/skills/registry.py bounds every MCP tool call
# at 30 s (CALL_TIMEOUT) and the pytest gate alone runs for minutes, so
# neither could ever complete against the real suite — part of why no
# self-edit had reached a pull request. selfedit_finish is the background
# job that replaces both. The sidecar's own /api/selfedit/validate and
# /submit routes are untouched (SE10): the native app's Edit tab drives
# them directly.


def plan_start(
    client, goal: str, mode: str = "single", profile: str | None = None,
    confirm: bool = False, review_path: str = "", run_id: str = "",
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
            "review_path": review_path, "run_id": run_id or None,
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
