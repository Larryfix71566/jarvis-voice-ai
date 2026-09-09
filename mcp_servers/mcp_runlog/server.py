"""mcp-runlog FastMCP server (thin wrapper over logic.py).

Read-only by construction — no tool in this server writes anything.
Every tool description starts with "Run log (read-only):" for the same
schema-text-drives-selection reason mcp-repo/mcp-apps state which one
they are (D13/D14).
"""

from fastmcp import FastMCP

from . import logic

mcp = FastMCP("mcp-runlog")


@mcp.tool()
def runlog_list(
    agent: str = "", status: str = "", since: str = "",
    task_contains: str = "", limit: int = 20,
) -> dict:
    """Run log (read-only): list recent sub-agent delegation runs,
    newest first. All filters optional: AGENT (e.g. 'developer'), STATUS
    ('ok'/'failed'/'timeout'/'orphaned'), SINCE ('7d'/'24h'/'30m' or an
    ISO timestamp), TASK_CONTAINS (substring match on the task text).
    LIMIT capped at 50."""
    return logic.runlog_list(agent, status, since, task_contains, limit)


@mcp.tool()
def runlog_detail(run_id: str) -> dict:
    """Run log (read-only): full detail for one run — status, timing,
    tool counts, model, the task, the failure error if any, and every
    tool call's bounded preview. Use runlog_list first to find a run_id."""
    return logic.runlog_detail(run_id)


@mcp.tool()
def runlog_stats(since: str = "7d") -> dict:
    """Run log (read-only): per-agent status counts and per-model
    success rates over the window (default 7 days) — use this to answer
    "is this model working" rather than counting a run list by hand."""
    return logic.runlog_stats(since)


@mcp.tool()
def council_list(limit: int = 10) -> dict:
    """Run log (read-only): recent council rounds (self-edit escalation,
    planning, review, app-build) with their workflow, status, goal, and
    winning profile. LIMIT capped at 50."""
    return logic.council_list(limit)


@mcp.tool()
def graph_view(graph: str, focus: str = "", depth: int = 2, since: str = "7d") -> dict:
    """Draw one of Mortimer's own relationship graphs from its run log and council records: `execution` (runs, tools, models, sessions — needs a focus), `deliberation` (council rounds, proposals, judges), or `capability` (procedures, skills, workflows and the runs that taught them). Read-only; opens the picture on the user's display. Use when investigating which model or tool a run used, how a council round went, or where a rule came from."""
    return logic.graph_view(graph, focus, depth, since)


if __name__ == "__main__":
    mcp.run()
