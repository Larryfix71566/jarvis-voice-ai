# GC24-02 receipt — research start requires stable action identity

**Date:** 2026-09-25  
**Worktree:** `codex/isolated-20260924`  
**Base snapshot:** `977f50bec7b77bd7d3381d3b8f3d63fa69bd00e2`  
**Scope:** identity, duplicate suppression, and status reconciliation for the
paid asynchronous website-comparison start.

The registered `research_compare_start` tool receives the owning SubAgent
execution ID through the existing hidden `run_id` injection. Its preview
still works without an ID and does not dispatch. A confirmed call without a
bounded ID now fails closed in both MCP logic and `/api/research/start`,
before any crawl or model work. The sidecar claims the ID in the existing
SQLite execution-action table, returns a duplicate receipt without starting a
second crawl, includes the ID in the live research job, and updates its
content-free claim state when the job reaches a terminal result. The
registered `research_status` call uses the injected ID to query that exact
action; when a later job has replaced the one live result slot, the status
still reports the prior claim's terminal/unknown state without inventing a
result payload. URL limits, explicit cost preview/confirmation, sensitive
turn blocking, result display, and sandbox-save flow remain unchanged.

Validation:

- `./.venv/bin/python -m pytest tests/unit/test_admin_research.py tests/unit/test_mcp_web_logic.py tests/unit/test_run_id_injection.py tests/integration/test_mcp_servers.py -q --tb=short` — **71 passed, 1 skipped, 1 dependency deprecation warning**.
- `RUN_LIVE=0 ./.venv/bin/python -m pytest tests/unit tests/integration -q --tb=short` — **3,039 passed, 4 skipped, 11 warnings, 2 subtests passed**.
- `./.venv/bin/ruff check --select F,I` on all touched Python files — passed.
- `./.venv/bin/python -m compileall -q` on all touched Python files — passed.
- `git diff --check` — passed.

This closes only the unkeyed/duplicate confirmed research-start dispatch.
Other mutation families, generic provider/tool terminal ownership, complete
cancellation and late-effect suppression, and live candidate acceptance
remain open. This is evidence for the dirty isolated tree only; it is not a
merge, deployment, or release claim.
