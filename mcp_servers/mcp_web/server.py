"""mcp-web FastMCP server (thin wrapper over logic.py — plan §1 template)."""

from fastmcp import FastMCP

from . import logic

mcp = FastMCP("mcp-web")


@mcp.tool()
def web_search(query: str, max_results: int = 5) -> dict:
    """Search the web for current information. Returns a short synthesized answer plus titled results with URLs and snippets."""
    return logic.web_search(query, max_results)


@mcp.tool()
def get_weather(city: str, days: int = 1) -> dict:
    """Get current weather conditions and a short forecast (1-3 days) for a city, including a one-sentence human summary."""
    return logic.get_weather(city, days)


if __name__ == "__main__":
    mcp.run(transport="stdio")
