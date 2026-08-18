"""view_screen tool (MORTIMER_SHELL_FIX_AND_SCREEN_VISION_PLAN.md V3).

A Supervisor-only direct tool, wired exactly like set_voice/ui_control
(jarvis/bot/voice_switch.py's build_set_voice_tool is the template) — no
sub-agent involved, so "what's on my second monitor?" answers in one
turn instead of a delegation round-trip. Calls the SAME
mcp_servers.mcp_screen.logic functions the mcp-screen MCP server's tools
call — one implementation of screen_list/screen_view, two entry points
(this direct tool for the Supervisor, the MCP server for systems/
developer sub-agents).

logic.screen_list/screen_view are synchronous (subprocess capture, then
a blocking vision-model HTTP call) — run in a thread via asyncio.to_thread
so a slow capture/vision call never blocks the voice event loop.
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable

from mcp_servers.mcp_screen import logic as screen_logic

VIEW_SCREEN_SCHEMA = {
    "type": "function",
    "function": {
        "name": "view_screen",
        "description": (
            "Look at what's currently on a connected screen/monitor and "
            "answer a question about it — e.g. 'what's on my second "
            "monitor?', 'is the panel window actually there?', 'what does "
            "my screen look like right now?'. Call screen_list first if "
            "you need to know which display index to use (display 1 is "
            "usually the main screen). Only call this when the user is "
            "asking about something visual on their own screen — not for "
            "reading files or code, which belongs to the developer "
            "sub-agent instead."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "What to look for or answer about the screen",
                },
                "display": {
                    "type": "integer",
                    "description": "1-based display index from screen_list (default 1)",
                },
            },
            "required": ["question"],
        },
    },
}

LIST_SCREENS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "list_screens",
        "description": (
            "List connected displays/monitors with their index and "
            "resolution. Call before view_screen when you need to know "
            "which display index to target, or when the user asks how "
            "many screens are connected."
        ),
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}


def build_view_screen_tool(
    screen_view: Callable[..., dict] = screen_logic.screen_view,
) -> tuple[dict, Callable[[dict], Any]]:
    """Return (openai_tool_schema, async_handler) for view_screen."""

    async def handler(arguments: dict) -> str:
        question = str(arguments.get("question", "")).strip()
        if not question:
            return "What would you like me to look for on the screen?"
        display = arguments.get("display", 1)
        try:
            display = int(display)
        except (TypeError, ValueError):
            display = 1
        result = await asyncio.to_thread(screen_view, question, display)
        if "error" in result:
            return result["error"]
        return result.get("answer") or "I couldn't make out anything useful on that screen."

    return VIEW_SCREEN_SCHEMA, handler


def build_list_screens_tool(
    screen_list: Callable[..., dict] = screen_logic.screen_list,
) -> tuple[dict, Callable[[dict], Any]]:
    """Return (openai_tool_schema, async_handler) for list_screens."""

    async def handler(arguments: dict) -> str:
        result = await asyncio.to_thread(screen_list)
        if "error" in result:
            return result["error"]
        displays = result.get("displays", [])
        if not displays:
            return "I couldn't detect any connected displays."
        parts = [
            f"display {d['index']}"
            + (" (main)" if d.get("main") else "")
            + f" — {d.get('resolution', 'unknown resolution')}"
            for d in displays
        ]
        return "Connected displays: " + "; ".join(parts) + "."

    return LIST_SCREENS_SCHEMA, handler
