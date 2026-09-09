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
def selfedit_start(
    goal: str = "", profile: str = "", confirm: bool = False, plan_path: str = "",
    staging_id: str = "", run_id: str = "", target_paths: list[str] | None = None,
) -> dict:
    """Start a self-development run for GOAL (a change to Mortimer itself).

    Two-phase: call with confirm=false to preview the goal and planner
    model. The result carries a `staging_id` — after the user explicitly
    agrees, call again with confirm=true AND that same staging_id (goal/
    profile don't need to be restated; the sidecar replays exactly what
    was previewed). PROFILE optionally names a planner from the registry
    (e.g. 'kimi-k2', 'kimi-k3', 'claude-opus'); empty uses the default.
    PLAN_PATH, when set, names an existing repo plan/spec document (e.g.
    docs/plans/GEOLOCATION_DEVELOPMENT_PLAN.md) that seeds the run — use it
    whenever the user asks to implement a plan, spec, or phase document.
    Staging expires after 10 minutes; if confirm=true reports the staging
    is gone, call selfedit_start again to preview a fresh one. The run
    itself is asynchronous: it plans in the background for several
    minutes; use selfedit_status to check progress. `run_id` is filled in
    by the system; leave it empty. TARGET_PATHS lists the repo files the
    edit will CHANGE (e.g. ["docs/REPO_MAP.md"]); the preview's tier check
    reads these, not the files the goal merely mentions — always pass it
    when the goal names any file.
    """
    return logic.selfedit_start(
        _get_client(), goal, profile or None, confirm,
        plan_path=plan_path, staging_id=staging_id, run_id=run_id,
        target_paths=target_paths,
    )


@mcp.tool()
def selfedit_status(staging_id: str = "") -> dict:
    """Report progress of the current upgrade run and edit session: whether
    the planner is still working, which files are proposed and why, whether
    validation passed, and the PR URL once submitted.

    Pass staging_id to check whether a specific staged preview (from
    selfedit_start with confirm=false) is still live before confirming it —
    the answer comes from the real staging record, not a guess about TTLs."""
    return logic.selfedit_status(_get_client(), staging_id)


@mcp.tool()
def selfedit_read(path: str) -> dict:
    """Read one repo file from the OPEN self-edit session's worktree.

    Use this after selfedit_start(confirm=true) reports a session, to see
    the current content of each file you are about to change. Reading the
    live checkout with repo_read_file instead risks writing a change based
    on a version the session does not have."""
    return logic.selfedit_read(_get_client(), path)


@mcp.tool()
def selfedit_write(path: str, content: str, rationale: str,
                   visual_intent: str = "") -> dict:
    """Write one file in the OPEN self-edit session's worktree.

    `content` is the COMPLETE new file, not a patch or a fragment — read
    the file first with selfedit_read and send it back with your change
    applied. `rationale` is one line saying why, and appears in the pull
    request. Set `visual_intent` for a change to the native app's interface
    (macos/MortimerHost): one sentence saying what should look different,
    which is what "check your appearance" verifies after the rebuild.

    The allowlist applies exactly as it does to any self-edit: a denied
    path is refused here, not silently written. Nothing is committed —
    call selfedit_finish when the whole change is written."""
    return logic.selfedit_write(_get_client(), path, content, rationale,
                                visual_intent)


@mcp.tool()
def selfedit_finish() -> dict:
    """Validate everything written in this session and, if every check
    passes, open the pull request.

    This is the end of the self-edit: the user already approved it at the
    preview ("I will write the change, validate it, and if every check
    passes open the pull request"), so no further confirmation is needed.
    Runs in the background — the gates take minutes — so report the summary
    and STOP; call selfedit_status when the user asks how it is going. If
    validation fails, the session stays open: read the failing check, fix
    the file with selfedit_write, and call selfedit_finish again."""
    return logic.selfedit_finish(_get_client())


@mcp.tool()
def selfedit_verify_appearance(branch_override: bool = False,
                               display: int = 1) -> dict:
    """Look at the running console and report whether this session's
    intended appearance is actually true.

    Use AFTER the user has pulled and run the branch — the validation checks
    cannot see the screen, so a visual change is unverified until someone
    looks. Read-only, no confirmation needed, and it never blocks a submit.

    Refuses if a different branch is checked out (pass branch_override=true
    only when the changes are already merged into what is running), or if
    the session recorded no intended appearance to check for."""
    return logic.selfedit_verify_appearance(
        _get_client(), branch_override, display)




@mcp.tool()
def selfedit_revert(confirm: bool = False) -> dict:
    """Discard the current edit session and restore the repo.

    Two-phase: confirm=false previews what will be discarded; confirm=true
    reverts, only after the user explicitly agrees."""
    return logic.selfedit_revert(_get_client(), confirm)


@mcp.tool()
def plan_start(
    goal: str, mode: str = "single", profile: str = "", confirm: bool = False,
    review_path: str = "", run_id: str = "",
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
    plan, spec, or document reviewed, critiqued, or checked by a model.
    `run_id` is filled in by the system; leave it empty."""
    return logic.plan_start(
        _get_client(), goal, mode or "single", profile or None, confirm,
        review_path or "", run_id=run_id,
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
