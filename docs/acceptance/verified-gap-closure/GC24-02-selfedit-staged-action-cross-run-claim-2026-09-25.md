# GC24-02 — Staged self-edit action claim across runs

**Date:** 2026-09-25  
**Branch:** `codex/isolated-20260924`  
**Base/HEAD:** `977f50bec7b77bd7d3381d3b8f3d63fa69bd00e2` (dirty worktree)  
**Status:** implemented and tested in the isolated worktree only; not merged,
deployed, or live-Mac accepted.

## Gap and invariant

A `/api/selfedit/stage` response issues a stable 12-character staging ID which
the user confirms. The prior one-shot in-memory staging guard could not
reconcile the same confirmed action after the live job slot moved or across a
fresh caller run. Matching goal text or arguments would not safely identify an
action. The invariant is now: a staged confirm claims exactly its issued
staging ID in the existing SQLite execution-action table before the planner or
authoring session starts; a duplicate does not dispatch; an unknown receipt
blocks automatic retry.

Claims are scoped to `mcp-selfedit.staged_start`. Bare deprecated goal-only
starts remain outside this claim because they have no stable issued approval
identity. This receipt does not establish replay safety for other mutation
families or undo an external effect already committed inside a tool.

## Changes

- Added an atomic, content-free claim for staged planner and developer-authoring
  starts. Claim-store read/write failure fails closed before start.
- Canonicalized an ID only after the existing single-live-stage repair resolves
  it, so the claim uses the ID actually issued by the stage endpoint.
- Added durable status lookup by `action_run_id` after the singleton live job
  slot is replaced. Pending receipts without a matching live job report
  `unknown` and require reconciliation.
- Returned duplicate staged starts as `started: false` with the action ID and
  bounded status. The MCP client preserves this distinction and asks status to
  inspect the durable receipt.
- Covered planner and authoring worker failures and terminal outcomes in the
  claim lifecycle. Moved duplicate reconciliation outside the non-reentrant
  job locks to avoid deadlock.
- Migrated self-edit unit and end-to-end test fixtures to isolated temporary
  migrated SQLite databases.

## Verification

- Focused admin/self-edit/MCP/app-build/plan/run-log suites:
  `.venv/bin/python -m pytest tests/unit/test_admin_selfedit.py tests/unit/test_mcp_selfedit_logic.py tests/unit/test_admin_appbuild.py tests/unit/test_admin_plan.py tests/unit/test_runlog_store.py -q --tb=short`
  — **212 passed**.
- Focused self-edit/MCP/end-to-end suites:
  `.venv/bin/python -m pytest tests/unit/test_admin_selfedit.py tests/unit/test_mcp_selfedit_logic.py tests/integration/test_selfedit_end_to_end.py -q --tb=short`
  — **144 passed**.
- Self-edit end-to-end suite:
  `.venv/bin/python -m pytest tests/integration/test_selfedit_end_to_end.py -q --tb=short`
  — **3 passed**.
- Full Python regression:
  `.venv/bin/python -m pytest tests/unit tests/integration -q --tb=short`
  — **2,950 passed, 4 skipped, 11 warnings, 2 subtests passed**.
- Ruff `F` on the five changed Python implementation/test files and Ruff `I`
  on `jarvis/admin/server.py` and `mcp_servers/mcp_selfedit/logic.py` — pass.
- `git diff --check` — pass.

The four suite skips remain skips; they are not converted into passes here.
An initial full-suite run exposed missing temporary-database setup in three
end-to-end fixtures; after adding the fixture dependency, the focused tests
and complete regression run passed. A follow-up added explicit coverage that
an authoring setup failure settles its claim as failed; the full suite was
rerun after that change.

## Files touched for this slice

- `jarvis/admin/server.py`
- `mcp_servers/mcp_selfedit/logic.py`
- `tests/unit/test_admin_selfedit.py`
- `tests/unit/test_mcp_selfedit_logic.py`
- `tests/integration/test_selfedit_end_to_end.py`
- `docs/acceptance/IMPLEMENTATION_STATUS.md`
- `docs/plans/MORTIMER_FRESH_REVIEW_IMPLEMENTATION_PLAN_2026-09-25.md`

These files also contain pre-existing concurrent edits from the dirty tree;
this list does not imply exclusive ownership of their full diffs.

## Remaining work and next action

Cross-run protection is closed only for staged self-edit confirmations. Next,
reconcile the remaining inventoried mutating caller families and complete the
GC24-02 lifecycle/late-effect proof. Do not infer stable identity from
arguments or goal text. Continue the full GC24-03 privacy, GC24-04 route,
GC24-05 production-memory prerequisites, GC24-06 Atlas live acceptance, and
GC24-07–10 candidate/release gates. No provider route or production-memory
feature was enabled by this change.
