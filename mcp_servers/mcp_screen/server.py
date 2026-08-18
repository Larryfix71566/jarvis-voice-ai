"""mcp-screen FastMCP server (thin wrapper over logic.py — plan §1 template).

MORTIMER_SHELL_FIX_AND_SCREEN_VISION_PLAN.md V1. Wired to `systems` and
`developer` in config/agents.yaml so troubleshooting delegations can look
at screens themselves; the Supervisor's own `view_screen` tool
(jarvis/bot/screen_tool.py) calls the SAME logic.py functions directly —
one implementation, two entry points.
"""

from fastmcp import FastMCP

from . import logic

mcp = FastMCP("mcp-screen")


@mcp.tool()
def screen_list() -> dict:
    """List connected displays: 1-based index (for screen_view's `display` argument), resolution, and which one is the main display."""
    return logic.screen_list()


@mcp.tool()
def screen_view(question: str, display: int = 1) -> dict:
    """Capture a screenshot of the given display (1-based, from screen_list) and ask a vision model your question about what's showing — e.g. verifying window placement, reading an error dialog, or describing what's on screen. Returns only a text answer; the image itself is never stored or returned."""
    return logic.screen_view(question, display)


if __name__ == "__main__":
    mcp.run(transport="stdio")
