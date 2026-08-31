"""mcp-kb FastMCP server (thin wrapper over logic.py — mirrors
mcp_servers/mcp_memory/server.py's template exactly).

Only the READ-ORIENTED tools are exposed here (kb_search, kb_read,
kb_neighbors). kb_write, kb_delete, and kb_flush exist in logic.py but are
deliberately NOT wired as @mcp.tool() functions: config/agents.yaml grants
access per-SERVER, not per-tool, so exposing them here would hand write/
delete access to whichever agent gets this server. The session-end
digester (jarvis/kb_digest.py) calls logic.kb_write/kb_flush directly as
plain Python function calls — it never goes through MCP tool-calling, so
it does not need them registered here. Voice-triggered writes are
deliberately out of scope for W1; add a tool for them later, explicitly,
once digest quality has been observed for a while.

NOTE the entrypoint at the bottom: omitting it makes the process import
cleanly, print nothing, and exit 0 without starting the stdio transport,
which surfaces at SkillRegistry.start() as "Connection closed" on the NEXT
server in the list (see CLAUDE.md's mcp_runlog note).
"""

from fastmcp import FastMCP

from . import logic

mcp = FastMCP("mcp-kb")


@mcp.tool()
def kb_search(
    query: str,
    k: int | None = None,
    type: str | None = None,
    tags: list[str] | None = None,
    confidence_min: str | None = None,
) -> dict:
    """Search the knowledge base of curated project documents and session digests. Returns ranked snippets with document ids."""
    return logic.kb_search(query, k, type, tags, confidence_min)


@mcp.tool()
def kb_read(id: str) -> dict:
    """Read one knowledge-base document in full by id. Use ids returned by kb_search or kb_neighbors."""
    return logic.kb_read(id)


@mcp.tool()
def kb_neighbors(id: str) -> dict:
    """List documents linked to or from the given document id."""
    return logic.kb_neighbors(id)


if __name__ == "__main__":
    mcp.run(transport="stdio")

