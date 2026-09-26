"""mcp-memory FastMCP server (thin wrapper over logic.py — plan §1 template).

NOTE the entrypoint at the bottom: omitting it makes the process import
cleanly, print nothing, and exit 0 without starting the stdio transport,
which surfaces at SkillRegistry.start() as "Connection closed" on the NEXT
server in the list (see CLAUDE.md's mcp_runlog note — this exact mistake
has been made before).
"""

from fastmcp import FastMCP

from . import logic

mcp = FastMCP("mcp-memory")


@mcp.tool()
def memory_review_list(limit: int = 10) -> dict:
    """List memory conflicts and cleanup items waiting for the user's review (duplicate clusters, contradictions, task-rule/implemented classifications). Each item includes its id, the fact keys involved, a human-readable detail line, and the valid resolve actions for its kind."""
    return logic.review_list(limit)


@mcp.tool()
def memory_review_resolve(review_id: int, action: str, rewrite_content: str | None = None) -> dict:
    """Resolve one memory review by id, ONLY after the user has explicitly chosen. Actions: keep_a / keep_b (archive the other fact), rewrite (requires rewrite_content, replaces both facts), dismiss (both facts stay, never asked again); for audience items: convert_workflow, archive_implemented, keep_interaction. Speak the review's detail to the user and get their choice BEFORE calling this — never resolve on your own judgment."""
    return logic.review_resolve(review_id, action, rewrite_content)


@mcp.tool()
def memory_search(query: str, limit: int = 10) -> dict:
    """Search stored memory by keyword, across BOTH live facts (already in the prompt) and archived facts (demoted by capacity enforcement or consolidation, but never deleted). Use this to recall something that isn't showing up in ordinary conversation context — a preference, note, or fact that was merged, aged out, or otherwise archived is still findable here."""
    return logic.memory_search(query, limit)


@mcp.tool()
def memory_restore(key: str) -> dict:
    """Bring one archived memory back into live memory, by its exact key, when the user asks to restore or undo an archived memory (for example one the memory tidy-up archived). Find the key with memory_search first if the user named it loosely; on a miss the result lists close archived keys. The memory returns unchanged, with its original age. Report the result's content and what it had been archived as ("was")."""
    return logic.memory_restore(key)


@mcp.tool()
def memory_graph_view(focus: str = "", depth: int = 2, edge_types: str = "") -> dict:
    """Draw the relationship graph of Mortimer's own memory store around a fact, key prefix, or search term: sibling facts under the same key path, what an archived fact became, and the conversation turn that stated it. Read-only; opens the picture on the user's display. Use when the user asks what Mortimer knows around a topic, why it believes something, or what happened to a memory."""
    return logic.memory_graph_view(focus, depth, edge_types)


if __name__ == "__main__":
    mcp.run(transport="stdio")
