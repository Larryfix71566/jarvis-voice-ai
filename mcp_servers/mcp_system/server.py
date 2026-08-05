"""mcp-system FastMCP server (thin wrapper over logic.py — plan §1 template)."""

from fastmcp import FastMCP

from . import logic

mcp = FastMCP("mcp-system")


@mcp.tool()
def get_system_status() -> dict:
    """Get local machine health: CPU, memory and disk usage percent, battery if present, uptime, and a one-sentence summary flagging anything at or above 85%."""
    return logic.get_system_status()


@mcp.tool()
def get_top_processes(limit: int = 5) -> dict:
    """List the top processes by CPU usage, with memory percent. Use when the machine is slow or the user asks what is running."""
    return logic.get_top_processes(limit)


if __name__ == "__main__":
    mcp.run(transport="stdio")
