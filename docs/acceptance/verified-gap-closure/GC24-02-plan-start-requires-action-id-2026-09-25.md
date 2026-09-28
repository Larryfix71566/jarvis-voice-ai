# GC24-02 receipt — plan start requires stable action identity

**Date:** 2026-09-25  
**Worktree:** `codex/isolated-20260924`  
**Base snapshot:** `977f50bec7b77bd7d3381d3b8f3d63fa69bd00e2`  
**Scope:** MCP and admin sidecar `plan_start` identity validation.

`plan_start` already had a durable SQLite claim keyed by the injected
SubAgent `run_id`, but the MCP helper and `/api/plan/start` also accepted
confirmed requests without it. Those requests could launch work outside the
claim ledger. The helper now returns a clear refusal without calling the
sidecar when the execution ID is absent. The sidecar independently refuses
missing/blank or over-256-character IDs before reading a review document,
claiming an action, or starting a worker. Valid confirmed calls continue to
use the same claim/status scope. Preview-only requests need no ID.

Focused tests cover client-side no-dispatch, missing/oversized server IDs,
duplicate claims, current registry injection, preview behavior, and planning
mode behavior. The full-suite rerun found the separate plan-review test
fixture still modeled a direct sidecar caller; it now supplies the same
system-injected stable ID as the registered `plan_start` caller. The
review-specific path continues to exercise synchronous document read/refusal
and single/council review behavior with no model network access.

Validation:

- `./.venv/bin/python -m pytest tests/unit/test_admin_plan.py tests/unit/test_mcp_selfedit_logic.py tests/unit/test_run_id_injection.py -q --tb=short` — **109 passed**, **1 dependency deprecation warning**.
- `./.venv/bin/python -m pytest tests/unit/test_admin_plan_review.py tests/unit/test_admin_plan.py tests/unit/test_mcp_selfedit_logic.py tests/unit/test_run_id_injection.py -q --tb=short` — **117 passed**, **1 dependency deprecation warning**.
- `RUN_LIVE=0 ./.venv/bin/python -m pytest tests/unit tests/integration -q --tb=short` — **3,033 passed, 4 skipped, 11 warnings, 2 subtests passed**.
- `./.venv/bin/ruff check --select F,I jarvis/admin/server.py mcp_servers/mcp_apps/logic.py mcp_servers/mcp_apps/server.py mcp_servers/mcp_selfedit/logic.py tests/unit/test_admin_appbuild.py tests/unit/test_admin_selfedit.py tests/unit/test_admin_plan.py tests/unit/test_mcp_apps_logic.py tests/unit/test_mcp_selfedit_logic.py` — passed.
- `./.venv/bin/python -m compileall -q jarvis/admin/server.py mcp_servers/mcp_apps/logic.py mcp_servers/mcp_apps/server.py mcp_servers/mcp_selfedit/logic.py tests/unit/test_admin_appbuild.py tests/unit/test_admin_selfedit.py tests/unit/test_admin_plan.py tests/unit/test_mcp_apps_logic.py tests/unit/test_mcp_selfedit_logic.py` — passed.
- `git diff --check` — passed.

This closes only unkeyed plan-start dispatch. Other mutating caller families,
full provider/tool terminal ownership, cancellation late effects, and live
candidate acceptance remain open. This is a dirty isolated-tree receipt, not
a merge or release result.
