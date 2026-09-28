# GC24-02 receipt — app-build start requires stable action identity

**Date:** 2026-09-25  
**Worktree:** `codex/isolated-20260924`  
**Base snapshot:** `977f50bec7b77bd7d3381d3b8f3d63fa69bd00e2`  
**Scope:** fail-closed execution identity for MCP and sidecar app-build starts.

`app_build_start` already received a system-injected SubAgent `run_id` through
the registry and the admin sidecar already persisted that ID in its SQLite
start-claim scope. However, the MCP helper and `/api/appbuild/start` also
allowed confirmed direct calls without an ID; those requests could bypass
duplicate protection. The MCP helper now refuses a confirmed call without
the injected ID before sending it. The sidecar independently refuses missing,
blank, or over-256-character IDs before claiming or dispatching. Valid
duplicate handling, status recovery, run setup, and sandbox behavior retain
the existing claim/status path.

Focused tests verify client-side refusal/no network request, server-side
missing and oversized ID refusal/no job dispatch, registry injection,
duplicate detection, claim-store failure behavior, and unchanged sandbox
start behavior.

Validation:

- `./.venv/bin/python -m pytest tests/unit/test_admin_appbuild.py tests/unit/test_run_id_injection.py tests/unit/test_mcp_apps_logic.py tests/unit/test_admin_selfedit.py tests/unit/test_mcp_selfedit_logic.py -q --tb=short` — **218 passed**, **1 dependency deprecation warning**.
- `RUN_LIVE=0 ./.venv/bin/python -m pytest tests/unit tests/integration -q --tb=short` — **3,030 passed, 4 skipped, 11 warnings, 2 subtests passed** in 99.56 seconds. Four skips are existing environment/provider-gated tests.
- `./.venv/bin/ruff check --select F,I jarvis/admin/server.py mcp_servers/mcp_apps/logic.py mcp_servers/mcp_apps/server.py mcp_servers/mcp_selfedit/logic.py tests/unit/test_admin_appbuild.py tests/unit/test_admin_selfedit.py tests/unit/test_mcp_apps_logic.py tests/unit/test_mcp_selfedit_logic.py` — passed.
- `./.venv/bin/python -m compileall -q jarvis/admin/server.py mcp_servers/mcp_apps/logic.py mcp_servers/mcp_apps/server.py mcp_servers/mcp_selfedit/logic.py tests/unit/test_admin_appbuild.py tests/unit/test_admin_selfedit.py tests/unit/test_mcp_apps_logic.py tests/unit/test_mcp_selfedit_logic.py` — passed.
- `git diff --check` — passed.

This closes the no-ID direct-start paths for app-build and self-edit and
preserves the caller-owned action IDs. It does not close action reconciliation
for all other mutations, completed provider/tool lifecycle ownership, or
late effects after cancellation. The tree remains dirty and isolated; no
merge, deployment, or live GitHub publication was performed.
