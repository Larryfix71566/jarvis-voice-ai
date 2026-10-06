"""mcp-web FastMCP server (thin wrapper over logic.py — plan §1 template)."""

import json

from fastmcp import Context, FastMCP
from fastmcp.tools.tool import ToolResult
from mcp.types import TextContent

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


def _advisory_response(ctx, tool, arguments):
    if ctx is None:
        return None
    request = ctx.request_context
    meta = request.meta if request is not None else None
    value = meta.model_dump().get('mortimer_advisory_source') if meta is not None else None
    if value is None:
        return None
    response = logic.advisory_source_request(_get_admin_client(), tool, arguments, value)
    body, hidden = {'ok': False, 'error': 'advisory_source_unavailable'}, {}
    if response.get('ok') is True:
        if value.get('phase') == 'associate':
            body = {'ok': True}
        else:
            try:
                receipt = response['source_receipt']
                body = json.loads(receipt['result']['content'])
                hidden = {'source_receipt': receipt}
                if value['phase'] == 'prepare':
                    hidden.update(source_context=response['source_context'], preparation_id=response['preparation_id'])
            except (ValueError, TypeError, KeyError):
                pass
    return ToolResult(content=[TextContent(type='text', text=json.dumps(body, sort_keys=True,
        separators=(',', ':'), ensure_ascii=True))], structured_content=body,
        meta={'mortimer_advisory_source': hidden})


@mcp.tool()
def web_search(query: str, max_results: int = 5) -> dict:
    """Search the web for current information. Returns a short synthesized answer plus titled results with URLs and snippets."""
    return logic.web_search(query, max_results)


@mcp.tool()
def get_weather(city: str, days: int = 1) -> dict:
    """Get current weather conditions (with humidity and wind), a forecast of 1-7 days with chance of rain, the next 12 hours, and active NWS alerts for a city, including a one-sentence human summary."""
    return logic.get_weather(city, days)


@mcp.tool()
def get_weather_radar(city: str) -> dict:
    """Get the latest precipitation radar for a city as a 3×3 grid of map tile URLs (RainViewer, keyless) — show these to the user as one stitched radar map."""
    return logic.get_weather_radar(city)


@mcp.tool()
def sports_scores(league: str, date: str = "") -> dict:
    """Game scores and schedule for one league on one day, from a structured source. LEAGUE: "nfl" or "mlb" (any other league returns an error — then search the web). DATE: YYYY-MM-DD in the user's timezone; empty means today. Each game has away/home, scores (null until played), status (scheduled, in_progress, final, or the source's own words) and start_local."""
    return logic.sports_scores(league, date)


@mcp.tool()
def research_compare_start(
    urls: list, focus: str = "", confirm: bool = False, run_id: str = "", ctx: Context = None,
) -> dict:
    """Start a deep comparison of TWO websites' content (not a quick search) — crawls each site and writes a comparison review. Two-phase: confirm=false previews the cost and asks; only after the user explicitly agrees, call again with confirm=true. FOCUS optionally steers what the comparison is about (e.g. "pricing and support"). Runs in the background for a few minutes — use research_status for progress."""
    source = _advisory_response(ctx, 'research_compare_start', dict(urls=urls, focus=focus,
        confirm=confirm, run_id=run_id))
    if source is not None:
        return source
    return logic.research_compare_start(
        _get_admin_client(), urls, focus, confirm, run_id=run_id,
    )


@mcp.tool()
def research_status(run_id: str = "", ctx: Context = None) -> dict:
    """Report progress of the current site comparison: still crawling, failed, or ready to view/save."""
    source = _advisory_response(ctx, 'research_status', dict(run_id=run_id))
    return source if source is not None else logic.research_status(_get_admin_client(), run_id=run_id)


@mcp.tool()
def research_save(path: str = "", confirm: bool = False, ctx: Context = None) -> dict:
    """Save the comparison in an open self-edit sandbox session, under
    docs/research/ by default. confirm=false previews; confirm=true writes a VM
    proposal. Follow session/retry guidance; selfedit_finish verifies and
    prepares a draft PR. This does not create a legacy commit action."""
    source = _advisory_response(ctx, 'research_save', dict(path=path or None, confirm=confirm))
    return source if source is not None else logic.research_save(_get_admin_client(), path or None, confirm)


if __name__ == "__main__":
    mcp.run(transport="stdio")
