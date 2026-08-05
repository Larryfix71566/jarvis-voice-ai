"""mcp-reminders FastMCP server (thin wrapper over logic.py — plan §1 template)."""

from fastmcp import FastMCP

from . import logic

mcp = FastMCP("mcp-reminders")


@mcp.tool()
def set_reminder(message: str, due_expression: str) -> dict:
    """Set a reminder for a natural-language time ("tomorrow at 9am", "in 2 hours"). The due time is resolved to an absolute time; reminders in the past are rejected."""
    return logic.set_reminder(message, due_expression)


@mcp.tool()
def list_reminders(status: str = "pending") -> dict:
    """List reminders by status: pending (default), done, cancelled, or all."""
    return logic.list_reminders(status)


@mcp.tool()
def complete_reminder(reminder_id: int) -> dict:
    """Mark a pending reminder as done."""
    return logic.complete_reminder(reminder_id)


@mcp.tool()
def cancel_reminder(reminder_id: int) -> dict:
    """Cancel a pending reminder."""
    return logic.cancel_reminder(reminder_id)


@mcp.tool()
def get_due_reminders() -> dict:
    """Fetch reminders that are due now and not yet delivered, marking them delivered. Used by the reminder watcher — not for listing upcoming reminders."""
    return logic.get_due_reminders()


if __name__ == "__main__":
    mcp.run(transport="stdio")
