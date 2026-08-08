"""mcp-apps FastMCP server (thin wrapper over logic.py + github.py).

Tools are two-phase where writes are involved: app_create with
confirm=False previews, with confirm=True executes. There is no delete
tool. Degraded mode: without GITHUB_TOKEN every tool returns the
documented error dict instead of raising.
"""

from fastmcp import FastMCP

from . import logic
from .github import GitHubClient, GitHubError

mcp = FastMCP("mcp-apps")

_client: GitHubClient | None = None


def _get_client() -> GitHubClient:
    global _client
    if _client is None:
        _client = GitHubClient()
    return _client


def _degraded(fn) -> dict:
    try:
        return fn(_get_client())
    except GitHubError as exc:
        return {"ok": False, "error": str(exc)}


@mcp.tool()
def app_create(name: str, template: str = "web_app", description: str = "",
               confirm: bool = False) -> dict:
    """Create a new application as its OWN private GitHub repo from a template. Two-phase: call with confirm=False to preview the repo name and file list (creates nothing), speak the summary, and only after the user confirms call again with confirm=True. Registers the app in the Mortimer app registry automatically."""
    return _degraded(lambda c: logic.app_create(c, name, template, description, confirm))


@mcp.tool()
def app_write_file(app: str, path: str, content: str, rationale: str = "") -> dict:
    """Create or update one file in an existing app's repo (default branch). One file per call; path is confined to the repo and may not touch .git."""
    return _degraded(lambda c: logic.app_write_file(c, app, path, content, rationale))


@mcp.tool()
def app_register(app: str, repo_url: str, description: str = "") -> dict:
    """Record an app in the Mortimer app registry (apps/index.json on the working branch). Idempotent; normally called automatically by app_create."""
    return _degraded(lambda c: logic.app_register(c, app, repo_url, description))


@mcp.tool()
def app_list() -> dict:
    """List all applications Mortimer has built, from the app registry."""
    return _degraded(lambda c: logic.app_list(c))


@mcp.tool()
def app_read(app: str, path: str) -> dict:
    """Read one file from an app's repo."""
    return _degraded(lambda c: logic.app_read(c, app, path))


if __name__ == "__main__":
    mcp.run(transport="stdio")
