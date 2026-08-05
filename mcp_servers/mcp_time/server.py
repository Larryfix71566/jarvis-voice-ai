"""mcp-time FastMCP server (thin wrapper over logic.py — plan §1 template)."""

from fastmcp import FastMCP

from . import logic

mcp = FastMCP("mcp-time")


@mcp.tool()
def get_current_time() -> dict:
    """Get the current date and time in the user's timezone, as ISO, human-readable text, and unix timestamp."""
    return logic.get_current_time()


@mcp.tool()
def resolve_date_expression(expression: str) -> dict:
    """Convert a natural-language date/time expression ("tomorrow", "next Friday", "in 3 days", "August 20 at 9am") into an absolute ISO datetime. Use this before any date math or storage."""
    return logic.resolve_date_expression(expression)


@mcp.tool()
def date_add(base_iso: str, amount: int, unit: str) -> dict:
    """Add an amount of time (unit: minutes, hours, days or weeks) to an ISO datetime and return the resulting datetime."""
    return logic.date_add(base_iso, amount, unit)


@mcp.tool()
def date_diff(a_iso: str, b_iso: str) -> dict:
    """Compute the signed difference between two ISO datetimes (b minus a), in days and hours."""
    return logic.date_diff(a_iso, b_iso)


if __name__ == "__main__":
    mcp.run(transport="stdio")
