"""FastMCP server exposing the self-development loop to the Developer agent.

All state and git operations live in the admin sidecar; these tools are thin,
spoken-friendly wrappers around its HTTP API (see logic.py).
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from mcp_servers.mcp_selfedit import logic

mcp = FastMCP("mcp-selfedit")

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = logic.AdminClient()
    return _client


@mcp.tool()
def selfedit_start(goal: str, profile: str = "", confirm: bool = False) -> dict:
    """Start a self-development run for GOAL (a change to Mortimer itself).

    Two-phase: call with confirm=false to preview the goal and planner model,
    then — only after the user explicitly agrees — call again with
    confirm=true. PROFILE optionally names a planner from the registry (e.g.
    'kimi-k2', 'kimi-k3', 'claude-opus'); empty uses the default. The run is
    asynchronous: it plans in the background for several minutes; use
    selfedit_status to check progress.
    """
    return logic.selfedit_start(_get_client(), goal, profile or None, confirm)


@mcp.tool()
def selfedit_status() -> dict:
    """Report progress of the current upgrade run and edit session: whether
    the planner is still working, which files are proposed and why, whether
    validation passed, and the PR URL once submitted."""
    return logic.selfedit_status(_get_client())


@mcp.tool()
def selfedit_validate() -> dict:
    """Validate the proposed edits (allowlist, backend imports, frontend
    build). Read-only — no user confirmation required. Must pass before
    selfedit_submit."""
    return logic.selfedit_validate(_get_client())


@mcp.tool()
def selfedit_submit(confirm: bool = False) -> dict:
    """Open a pull request with the validated edits.

    Two-phase: confirm=false previews; confirm=true submits. Call with
    confirm=true ONLY after validation has passed AND the user has explicitly
    asked to submit in a new turn. The PR is never merged by the agent."""
    return logic.selfedit_submit(_get_client(), confirm)


@mcp.tool()
def selfedit_revert(confirm: bool = False) -> dict:
    """Discard the current edit session and restore the repo.

    Two-phase: confirm=false previews what will be discarded; confirm=true
    reverts, only after the user explicitly agrees."""
    return logic.selfedit_revert(_get_client(), confirm)


@mcp.tool()
def plan_start(
    goal: str, mode: str = "single", profile: str = "", confirm: bool = False,
    review_path: str = "",
) -> dict:
    """Start drafting an implementation plan, specification, or design
    document for GOAL — use this instead of writing the document yourself
    in this conversation.

    MODE is 'single' (one named model authors the whole plan; PROFILE
    optionally names it, e.g. 'kimi-k2', 'claude-opus'; empty uses the
    default) or 'council' (every usable model drafts a COMPLETE plan in
    parallel, judges score them advisorily, and the user picks between
    them with plan_choose). Two-phase: call with confirm=false to preview,
    then — only after the user explicitly agrees — call again with
    confirm=true. Drafting is asynchronous and can take several minutes;
    use plan_status to check progress. Applies equally to interface
    upgrades/self-edits, new apps, and standalone plans.

    REVIEW_PATH, when set, reviews that existing repo document instead of
    authoring a new plan — use this whenever the user asks to have a
    plan, spec, or document reviewed, critiqued, or checked by a model."""
    return logic.plan_start(
        _get_client(), goal, mode or "single", profile or None, confirm,
        review_path or "",
    )


@mcp.tool()
def plan_status() -> dict:
    """Report progress of the current planning job: whether it is still
    drafting, whether council candidates are ready for the user to choose
    between (name each candidate's label and advisory score), or whether
    a finished plan is ready to be saved as a draft with plan_adopt."""
    return logic.plan_status(_get_client())


@mcp.tool()
def plan_choose(label: str) -> dict:
    """Choose one candidate plan from a council-mode planning round by its
    label (e.g. 'Proposal A'). No confirmation needed — this only records
    the user's choice; it writes nothing."""
    return logic.plan_choose(_get_client(), label)


@mcp.tool()
def plan_adopt(path: str = "", confirm: bool = False) -> dict:
    """Save the finished plan as a draft file in the repo (PATH defaults
    to a docs/plans/ file named after the goal).

    Two-phase, same as repo_write_file: confirm=false previews;
    confirm=true creates the draft. Even after confirm=true here, nothing
    is actually written until the draft is separately committed with
    repo_commit_write — describe it as a draft awaiting confirmation, not
    as written or saved."""
    return logic.plan_adopt(_get_client(), path or None, confirm)


if __name__ == "__main__":
    mcp.run()
