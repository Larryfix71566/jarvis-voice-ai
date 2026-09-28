# GC24-02 — Run-scoped app-build start claim

**Date:** 2026-09-25  
**Branch:** `codex/isolated-20260924`  
**Base/current source:** `977f50bec7b77bd7d3381d3b8f3d63fa69bd00e2` plus dirty isolated-tree changes. This is not a commit, merge, candidate, or release receipt.

## Change

The existing MCP registry now injects its owning SubAgent `run_id` into
`app_build_start` and removes that field from the model-visible tool schema.
The admin sidecar atomically claims `mcp-apps.app_build_start` in the existing
tenant-scoped SQLite `execution_action_claims` table before starting the job.
The worker updates only a bounded terminal status. Repeating a start with a
new provider call ID but the same SubAgent run ID returns `started: false` and
does not run a second build. A specific `action_run_id` can query the live job
or its content-free status receipt after the singleton status slot has moved.
If the claim store cannot be read or written, the endpoint refuses to start.

The action receipt stores no goal, plan, app arguments, or result. Calls with
no injected run ID preserve prior behavior. The guard applies only to one
SubAgent run: a fresh SubAgent run ID can still issue the same real-world
request, direct Supervisor calls are not covered, and a content-free receipt
cannot determine whether a side effect committed after the owning process
lost its live result. Those are still open GC24-02 requirements.

## Verification

- Focused app-build, MCP logic, and registry tests:
  `./.venv/bin/python -m pytest tests/unit/test_admin_appbuild.py tests/unit/test_mcp_apps_logic.py tests/unit/test_registry.py -q --tb=short`
  — **78 passed, 1 warning**.
- Full Python unit/integration suite on the final source snapshot:
  `./.venv/bin/python -m pytest tests/unit tests/integration -q --tb=short`
  — **2,937 passed, 4 skipped, 11 warnings, 2 subtests passed**.
- Ruff `F`/`I` on the changed Python files and `git diff --check` pass.

## Next action

Continue GC24-02 with a mutating action that has an
approved identity across fresh SubAgent runs or direct Supervisor calls.
Do not infer cross-run equivalence from a hash of action arguments.
