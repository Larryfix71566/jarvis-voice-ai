"""Admin sidecar routes: LLM council (/api/council/*).

Moved verbatim from jarvis/admin/server.py (B6). Helpers, state and imported
modules are reached as `srv.<name>` at call time, never imported here, so a
test that monkeypatches jarvis.admin.server is seen by these handlers.
Only jarvis.admin.server imports this module.
"""

from __future__ import annotations

from typing import Any

from jarvis.admin import server as srv
from jarvis.admin.server import (  # request bodies named in signatures
    ConveneIn,
)

# Routes register on the server's one FastAPI app (see the B6 note there).
app = srv.app


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
    advisory_started_at = srv.time.time()
    srv.run_migrations()
    if body.placement != "planner":
        return {
            "ok": False,
            "error": f"placement={body.placement!r} is not implemented — "
                     "only 'planner' has a defined council prompt (D6.1)",
        }
    goal = (body.goal or srv._selfedit_service.goal or "").strip()
    if not goal:
        return {"ok": False, "error": "a goal is required (no active session to fall back on)"}
    with srv._council_lock:
        if srv._council_job["state"] == "running":
            return {
                "ok": False,
                "error": "a council round is already in progress",
                "job": dict(srv._council_job),
            }
        context: dict[str, Any] = {"diff": srv._selfedit_service.proposals, "checks": None}
        if body.members:
            context["members"] = body.members
        srv._council_job.update(
            state="running", trigger="manual", goal=goal, round_id=None,
            winner=None, winner_mean=None, select_reason=None, error=None,
            started_at=srv.time.time(), finished_at=None,
        )
    srv._start_advisory_thread(
        srv._run_council_job,
        kwargs={"trigger": "manual", "goal": goal, "context": context},
        started_at=advisory_started_at,
    )
    return {"ok": True, "started": True}


@app.get("/api/council/job")
def council_job_status() -> dict:
    """MORTIMER_LLM_COUNCIL_V2_PLAN.md V5 — the polling target for both
    a manual convene and the E3 half of a reject, mirroring
    GET /api/selfedit/run."""
    with srv._council_lock:
        job = dict(srv._council_job)
    return {"ok": True, "job": job}


@app.get("/api/council/round/{round_id}")
def council_round_detail(round_id: str) -> dict:
    srv.run_migrations()
    detail = srv.council_mod.get_round(round_id)
    if detail is None:
        return {"ok": False, "error": "not found"}
    return {"ok": True, **detail}


@app.get("/api/council/rounds")
def council_rounds_list(
    workflow: str = "", status: str = "", since: str = "", limit: int = 50,
) -> dict:
    srv.run_migrations()
    clamped_limit = max(1, min(200, limit))
    return {
        "ok": True,
        "rounds": srv.council_mod.list_rounds(
            workflow=workflow or None, status=status or None,
            since=srv.parse_since(since or None), limit=clamped_limit,
        ),
    }


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
    srv.run_migrations()
    clamped_limit = max(1, min(50, limit))
    return {
        "ok": True,
        "rounds": srv.council_mod.list_round_rosters(
            workflow=workflow or None, status=status or None,
            since=srv.parse_since(since or None), limit=clamped_limit,
        ),
    }
