"""mcp-web FastMCP server (thin wrapper over logic.py — plan §1 template)."""

from fastmcp import FastMCP

from . import logic

mcp = FastMCP("mcp-web")

# MORTIMER_SITE_RESEARCH_AND_COMPARISON_PLAN.md R1 — same lazy-singleton
# AdminClient pattern as mcp_selfedit/server.py.
_admin_client = None


def _get_admin_client():
    global _admin_client
    if _admin_client is None:
        from mcp_servers.mcp_selfedit.logic import AdminClient
        _admin_client = AdminClient()
    return _admin_client


@mcp.tool()
def web_search(query: str, max_results: int = 5) -> dict:
    """Search the web for current information. Returns a short synthesized answer plus titled results with URLs and snippets."""
    return logic.web_search(query, max_results)


@mcp.tool()
def get_weather(city: str, days: int = 1) -> dict:
    """Get current weather conditions and a short forecast (1-3 days) for a city, including a one-sentence human summary."""
    return logic.get_weather(city, days)


@mcp.tool()
def get_weather_radar(city: str) -> dict:
    """Get the latest precipitation radar for a city as a 3×3 grid of map tile URLs (RainViewer, keyless) — show these to the user as one stitched radar map."""
    return logic.get_weather_radar(city)


@mcp.tool()
def research_compare_start(urls: list, focus: str = "", confirm: bool = False) -> dict:
    """Start a deep comparison of TWO websites' content (not a quick search) — crawls each site and writes a comparison review. Two-phase: confirm=false previews the cost and asks; only after the user explicitly agrees, call again with confirm=true. FOCUS optionally steers what the comparison is about (e.g. "pricing and support"). Runs in the background for a few minutes — use research_status for progress."""
    return logic.research_compare_start(_get_admin_client(), urls, focus, confirm)


@mcp.tool()
def research_status() -> dict:
    """Report progress of the current site comparison: still crawling, failed, or ready to view/save."""
    return logic.research_status(_get_admin_client())


@mcp.tool()
def research_save(path: str = "", confirm: bool = False) -> dict:
    """Save the comparison in an open self-edit sandbox session, under
    docs/research/ by default. confirm=false previews; confirm=true writes a VM
    proposal. Follow session/retry guidance; selfedit_finish verifies and
    prepares a draft PR. This does not create a legacy commit action."""
    return logic.research_save(_get_admin_client(), path or None, confirm)


if __name__ == "__main__":
    mcp.run(transport="stdio")
