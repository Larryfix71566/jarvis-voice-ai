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


if __name__ == "__main__":
    mcp.run()
