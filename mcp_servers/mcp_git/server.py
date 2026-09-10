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
def prepare_commit(message: str, paths: list[str]) -> dict:
    """Retired host staging tool. Use selfedit_start and selfedit_write;
    selfedit_finish verifies the sandbox candidate and prepares a draft PR."""
    return logic.prepare_commit(message, paths)


@mcp.tool()
def commit(action_id: int) -> dict:
    """Retired host commit tool. Old action IDs cannot commit; use selfedit_finish."""
    return logic.commit(action_id)


@mcp.tool()
def prepare_push() -> dict:
    """Retired host push tool. Use the verified sandbox publication workflow."""
    return logic.prepare_push()


@mcp.tool()
def push(action_id: int) -> dict:
    """Retired host push confirmation. Old action IDs cannot publish."""
    return logic.push(action_id)


@mcp.tool()
def list_actions(status: str = "all", limit: int = 10) -> dict:
    """Audit trail of privileged git actions: pending, committed, failed, expired, or all."""
    return logic.list_actions(status, limit)


if __name__ == "__main__":
    mcp.run()
