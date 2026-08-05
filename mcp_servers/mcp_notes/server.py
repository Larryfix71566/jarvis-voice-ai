"""mcp-notes FastMCP server (thin wrapper over logic.py — plan §1 template)."""

from fastmcp import FastMCP

from . import logic

mcp = FastMCP("mcp-notes")


@mcp.tool()
def create_note(title: str, body: str, tags: str = "") -> dict:
    """Save a note or fact to long-term memory. Title should be a 3-6 word summary; tags are comma-separated keywords used for later recall."""
    return logic.create_note(title, body, tags)


@mcp.tool()
def list_notes(tag: str | None = None, limit: int = 20) -> dict:
    """List saved notes, newest first. Optionally filter to notes matching a tag."""
    return logic.list_notes(tag, limit)


@mcp.tool()
def search_notes(query: str) -> dict:
    """Search saved notes by keyword across title, body and tags. Use this to recall anything the user asked to remember."""
    return logic.search_notes(query)


@mcp.tool()
def get_note(note_id: int) -> dict:
    """Fetch one note by its id."""
    return logic.get_note(note_id)


@mcp.tool()
def update_note(note_id: int, title: str | None = None, body: str | None = None, tags: str | None = None) -> dict:
    """Update a note's title, body and/or tags. Only provided fields change."""
    return logic.update_note(note_id, title, body, tags)


@mcp.tool()
def delete_note(note_id: int) -> dict:
    """Permanently delete a note by id."""
    return logic.delete_note(note_id)


if __name__ == "__main__":
    mcp.run(transport="stdio")
