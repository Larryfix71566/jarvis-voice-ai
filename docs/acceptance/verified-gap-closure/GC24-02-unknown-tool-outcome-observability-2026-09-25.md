# GC24-02 — Unknown tool outcome observability

**Date:** 2026-09-25  
**Source revision:** `977f50bec7b77bd7d3381d3b8f3d63fa69bd00e2`  
**Tree:** dirty isolated worktree `codex/isolated-20260924`; receipt describes the tested working-tree snapshot, not a commit.  
**State:** this observability slice is verified; GC24-02 remains open.

## Behavior verified

- Agent events carry the provider `tool_call_id` through dispatched tool calls and correlated results; migration `0028_agent_event_tool_call_identity` adds the nullable column and lookup index while preserving legacy rows.
- SubAgent cancellation during a registered tool call records a metadata-only `tool_outcome_unknown` event. If the process stops after dispatch without a result, `get_run` reports the correlated call as `unresolved`.
- Run details expose unresolved/unknown calls through the runlog CLI and MCP run detail. The warning explicitly says to verify before retrying.
- Unknown-outcome records contain the tool name, call ID, bounded reason code, and timestamp, without tool arguments or result. This does not remove the preexisting argument payload from the original `tool_call` event.
- A matching `tool_result` resolves the call in run detail. A call with no result remains visible as unresolved.

## Validation

Command:

```text
.venv/bin/python -m pytest tests/unit/test_db.py tests/unit/test_runlog_store.py tests/unit/test_subagent.py tests/unit/test_mcp_runlog_logic.py tests/integration/test_runlog_end_to_end.py -q --tb=short
```

Result: **124 passed**.

Command:

```text
.venv/bin/ruff check --select F,I jarvis/db.py jarvis/runlog/store.py jarvis/runlog/cli.py jarvis/agents/base.py mcp_servers/mcp_runlog/logic.py tests/unit/test_db.py tests/unit/test_runlog_store.py tests/unit/test_subagent.py
```

Result: **All checks passed**. `git diff --check` also passed.

Repository-wide regression after the schema and test updates:

```text
.venv/bin/python -m pytest tests/unit tests/integration -q --tb=short
```

Result: **2,917 passed, 4 skipped, 11 warnings, and 2 subtests passed** in
94.90 seconds. The four skips and warnings remain visible; this run covers
the dirty isolated snapshot and does not establish Mac, provider, or release
acceptance.

## Limits and next work

This is an audit/reconciliation signal, not an idempotency guarantee. It does
not prove whether an external mutation committed, provide an action-specific
reconciliation UI, or prevent a later request from repeating the same action
under a new provider call ID. It covers SubAgent run logging, not every
provider/tool caller. The original tool-call payload may include arguments
under the existing run-log policy; the new unknown event itself is
metadata-only. Do not treat this receipt as closure of GC24-02 or as
authorization for automatic retries.

Next: map mutating action identity to the existing permission/action owner and
durable receipts, determine whether an authoritative action-specific
idempotency key exists, then implement and test cross-request reconciliation
without creating another executor or retry path. Continue caller-by-caller
cancellation and late-write coverage separately.
