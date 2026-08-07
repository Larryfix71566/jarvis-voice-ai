"""mcp-git FastMCP server (thin wrapper over logic.py — upgrade plan U1.5)."""

from fastmcp import FastMCP

from . import logic

mcp = FastMCP("mcp-git")


@mcp.tool()
def git_status() -> dict:
    """Repository status: current branch, changed files, commits ahead/behind origin."""
    return logic.git_status()


@mcp.tool()
def git_log(n: int = 5) -> dict:
    """Recent commits, newest first (default 5, max 20)."""
    return logic.git_log(n)


@mcp.tool()
def git_diff_summary() -> dict:
    """Summary of uncommitted changes versus HEAD (files + line counts)."""
    return logic.git_diff_summary()


@mcp.tool()
def prepare_commit(message: str) -> dict:
    """Stage all changes and draft a commit with the given message. Returns an action_id and a summary to read back to the user. Nothing is committed until the user confirms and commit(action_id) is called."""
    return logic.prepare_commit(message)


@mcp.tool()
def commit(action_id: int) -> dict:
    """Execute a prepared commit after the user has confirmed. Requires the action_id from prepare_commit."""
    return logic.commit(action_id)


@mcp.tool()
def prepare_push() -> dict:
    """Draft a push of the current branch to origin. Returns an action_id and summary. Nothing is pushed until the user confirms and push(action_id) is called."""
    return logic.prepare_push()


@mcp.tool()
def push(action_id: int) -> dict:
    """Execute a prepared push after the user has confirmed. Requires the action_id from prepare_push."""
    return logic.push(action_id)


@mcp.tool()
def list_actions(status: str = "all", limit: int = 10) -> dict:
    """Audit trail of privileged git actions: pending, committed, failed, expired, or all."""
    return logic.list_actions(status, limit)


if __name__ == "__main__":
    mcp.run()
