"""mcp-status FastMCP server (thin wrapper over logic.py).

Read-only by construction: every tool is a GET against the admin sidecar's
/api/status/* routes, except status_subscription, a POST that spends a
little subscription quota and is rate-limited in the sidecar (spec I2). Every tool description starts with "Mortimer status
(read-only):" for the same schema-text-drives-selection reason mcp-runlog
states which server it is.
"""

from fastmcp import FastMCP

from . import logic

mcp = FastMCP("mcp-status")


@mcp.tool()
def status_models() -> dict:
    """Mortimer status (read-only): the configured models from the registry
    (default, provider, tier, routes), whether each key is present and its
    key-health verdict, the workloads, and every configured provider with
    any catalog coverage gap. Configured is not proof of availability."""
    return logic.status_models()


@mcp.tool()
def status_services() -> dict:
    """Mortimer status (read-only): which background services are up right
    now (bot, admin, vault, costs, extractor, backup), their launchd state,
    and the checkout's commit and count of uncommitted files."""
    return logic.status_services()


@mcp.tool()
def status_overview() -> dict:
    """Mortimer status (read-only): the configuration — agents with their
    model and MCP servers, the MCP server list, workloads, which feature
    switches are on or off, and the knowledge-layer counts."""
    return logic.status_overview()


@mcp.tool()
def status_build() -> dict:
    """Mortimer status (read-only): whether the Mac app bundle exists, when
    it was built, the commit it was built from, and whether that matches
    the current checkout."""
    return logic.status_build()


@mcp.tool()
def log_search(source: str, query: str = "", since_minutes: int = 60, limit: int = 50) -> dict:
    """Mortimer status (read-only): search one of Mortimer's own logs by
    SOURCE (bot, admin, extractor, costs, vault, backup, app) for lines
    containing QUERY (case-insensitive; empty matches all) within the last
    SINCE_MINUTES. Conversation lines are never returned and keys are
    redacted. LIMIT capped at 200."""
    return logic.log_search(source, query, since_minutes, limit)


@mcp.tool()
def status_catalog(provider: str = "all", force: bool = False) -> dict:
    """Mortimer status (read-only): what each configured model provider's
    account offers RIGHT NOW, read live from its model list (PROVIDER is a
    provider id such as anthropic, openrouter, moonshot, saygm, voice, or
    'all'), compared with the registry: configured models missing from the
    catalog and models offered but not configured. Cached for an hour;
    FORCE refreshes. Subscriptions have no list — use status_subscription."""
    return logic.status_catalog(provider, force)


@mcp.tool()
def status_subscription(which: str, model: str = "", force: bool = False) -> dict:
    """Mortimer status (read-only, but USES A LITTLE SUBSCRIPTION QUOTA):
    whether the Claude or Codex subscription (WHICH = claude or codex)
    answers on MODEL, tried exactly as named (empty = the default model).
    Reports the exact model tried and a failure category. One probe per
    (which, model) every 10 minutes unless FORCE."""
    return logic.status_subscription(which, model, force)


@mcp.tool()
def github_prs(state: str = "open", limit: int = 10) -> dict:
    """Mortimer status (read-only): pull requests on Mortimer's own GitHub
    repository in STATE (open, closed or all), up to LIMIT (max 50):
    number, title, draft, head and base branch, last update, link."""
    return logic.github_prs(state, limit)


@mcp.tool()
def github_pr_checks(number: int) -> dict:
    """Mortimer status (read-only): the CI check runs (name, status,
    conclusion) on the head commit of pull request NUMBER in Mortimer's own
    GitHub repository."""
    return logic.github_pr_checks(number)


if __name__ == "__main__":
    mcp.run()
