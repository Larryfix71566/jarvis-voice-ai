"""mcp-repo FastMCP server (thin wrapper over logic.py).

D14: every tool description below begins "Local working tree on this
machine:" specifically to stop the Supervisor/Developer sub-agent from
confusing this with mcp-apps (GitHub). See logic.py's module docstring
for the incident this guards against.
"""

from fastmcp import FastMCP

from . import logic

mcp = FastMCP("mcp-repo")


@mcp.tool()
def repo_read_file(path: str) -> dict:
    """Local working tree on this machine: read one file's contents by
    path relative to the repo root. Refuses paths outside the repo,
    secrets/credentials, and files over the size limit."""
    return logic.repo_read_file(path)


@mcp.tool()
def repo_list_files(subdir: str = "", pattern: str = "") -> dict:
    """Local working tree on this machine: list files under subdir
    (repo root if omitted), optionally filtered by a filename glob
    pattern. Denied directories (.git, .env, node_modules, etc.) are
    never listed."""
    return logic.repo_list_files(subdir, pattern)


@mcp.tool()
def repo_search(query: str, subdir: str = "") -> dict:
    """Local working tree on this machine: substring search across text
    files under subdir (repo root if omitted). Returns matching lines
    with file path and line number, capped and best-effort (binary/huge
    files are skipped, not errored)."""
    return logic.repo_search(query, subdir)


@mcp.tool()
def repo_write_file(path: str, content: str, rationale: str = "") -> dict:
    """Local working tree on this machine: writing is retired. Use selfedit_start,
    selfedit_write and selfedit_finish to edit and verify in the sandbox."""
    return logic.repo_write_file(path, content, rationale)


@mcp.tool()
def repo_commit_write(action_id: int) -> dict:
    """Local working tree on this machine: legacy write confirmations are retired,
    including previously issued action IDs. Use the self-edit sandbox workflow."""
    return logic.repo_commit_write(action_id)


if __name__ == "__main__":
    mcp.run()
