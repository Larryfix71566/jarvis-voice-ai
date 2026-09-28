# GC24-02 — Run-scoped planning-start claim

**Date:** 2026-09-25  
**Branch:** codex/isolated-20260924  
**Base/current source:** 977f50bec7b77bd7d3381d3b8f3d63fa69bd00e2 plus the dirty
isolated-tree changes. This is not a commit, merge, candidate, or release
receipt.

## Change

plan_start now claims one mcp-selfedit.plan_start action per owning SubAgent
run_id before it starts its asynchronous planning job. The hidden run ID is
supplied by the existing MCP registry injection and remains stable across
provider tool-call rounds. A repeated start with that same run ID returns the
existing state/receipt and launches no second job, even if the provider gave
the retry a new tool_call_id.

Migration 0029_execution_action_claims stores only the user scope, action
scope, execution ID, bounded status, and timestamps. It stores no prompt,
arguments, or result. Claims are unique per user/action/execution, use an
atomic SQLite insert, and survive status-slot replacement and process
restart. plan_status(action_run_id=...) returns the live result when the
action still owns the status slot; otherwise it returns the content-free
terminal or unknown receipt and warns against an automatic retry.

## Verification

- Focused DB/admin/MCP/manifest/tenant suites:
  ./.venv/bin/python -m pytest tests/unit/test_admin_plan.py tests/unit/test_mcp_selfedit_logic.py tests/unit/test_db.py tests/unit/test_admin_plan_review.py tests/unit/test_plan_manifests.py tests/unit/test_tenant_columns.py -q --tb=short
  — **126 passed, 1 warning**.
- Full Python unit/integration suite:
  ./.venv/bin/python -m pytest tests/unit tests/integration -q --tb=short
  — **2,930 passed, 4 skipped, 11 warnings, 2 subtests passed**.
- Ruff:
  ./.venv/bin/ruff check --select F,I jarvis/db.py jarvis/admin/server.py mcp_servers/mcp_selfedit/logic.py mcp_servers/mcp_selfedit/server.py tests/unit/test_db.py tests/unit/test_admin_plan.py tests/unit/test_mcp_selfedit_logic.py
  — passed.
- git diff --check — passed.

Regressions prove one start for repeated IDs within an execution, status
recovery after the single live-job slot is replaced, unknown status after loss
of the live slot, exactly one concurrent database claim, tenant isolation,
and that receipts contain no action payload.

## Limits still open

This closes only same-SubAgent-run replay for plan_start. It does not dedupe
an action across a new SubAgent run ID, protect direct Supervisor handlers,
or reconcile other mutating tool families. Calls without an injected run ID
retain their prior behavior. A durable unknown receipt is surfaced but does
not prove whether the planner completed, and no operator resolution control
is added here. Full GC24-02 action-specific reconciliation, caller lifecycle,
cancellation/late-write, and live-candidate gates remain open.
