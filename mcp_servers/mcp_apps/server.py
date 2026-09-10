"""mcp-apps FastMCP server (thin wrapper over logic.py + github.py).

Tools are two-phase where writes are involved: app_create with
confirm=False previews, with confirm=True executes. There is no delete
tool. Degraded mode: without GITHUB_TOKEN every tool returns the
documented error dict instead of raising.
"""

from fastmcp import FastMCP

from . import logic
from .github import GitHubClient, GitHubError
# D6 — app-build tools are thin HTTP clients of the admin sidecar, the
# SAME AdminClient class mcp_selfedit uses (not a second implementation).
from mcp_servers.mcp_selfedit.logic import AdminClient

mcp = FastMCP("mcp-apps")

_client: GitHubClient | None = None
_admin_client: AdminClient | None = None


def _get_client() -> GitHubClient:
    global _client
    if _client is None:
        _client = GitHubClient()
    return _client


def _get_admin_client() -> AdminClient:
    global _admin_client
    if _admin_client is None:
        _admin_client = AdminClient()
    return _admin_client


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
    """Retired direct writer. Use app_build_start even for a single-file change;
    app_build_status and app_build_submit provide verified draft publication."""
    return logic.app_write_file(None, app, path, content, rationale)


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


@mcp.tool()
def app_build_start(
    app: str, goal: str, profile: str = "", confirm: bool = False,
    plan_path: str = "",
) -> dict:
    """Offline sandbox, sidecar-driven: build an implementation of GOAL
    inside an EXISTING app's own repo (use app_create first if the app
    doesn't exist yet). Use this for every development change, including a single-file edit. Two-phase:
    call with confirm=false to preview, then — only after the user
    explicitly agrees — call again with confirm=true. PROFILE optionally
    names a planner from the registry; empty uses the default.
    PLAN_PATH, when set, names an existing repo plan/spec document (from
    the planning pathway) that seeds the build. The run is asynchronous —
    use app_build_status to check progress."""
    return logic.app_build_start(
        _get_admin_client(), app, goal, profile, confirm, plan_path,
    )


@mcp.tool()
def app_build_status() -> dict:
    """Report progress of the current app-build run: whether it's still
    working, which files are proposed and why, whether validation passed,
    and the PR URL once submitted."""
    return logic.app_build_status(_get_admin_client())


@mcp.tool()
def app_build_submit(confirm: bool = False) -> dict:
    """Open a pull request with the validated app-build edits.

    Two-phase: confirm=false previews; confirm=true submits. Call with
    confirm=true ONLY after validation has passed AND the user has
    explicitly asked to submit in a new turn. The PR is never merged by
    the agent — merging always stays with the human on GitHub."""
    return logic.app_build_submit(_get_admin_client(), confirm)


if __name__ == "__main__":
    mcp.run(transport="stdio")
