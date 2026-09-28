# GC24-02 receipt — native Edit-tab self-edit action identity

**Date:** 2026-09-25  
**Worktree:** `codex/isolated-20260924`  
**Base snapshot:** `977f50bec7b77bd7d3381d3b8f3d63fa69bd00e2`  
**Scope:** native Edit-tab bare-goal start identity, in-process transport retry,
and fail-closed handling of unkeyed deprecated bare starts.

The native Edit tab previously posted a bare goal without an action `run_id`.
It now creates a UUID for each newly initiated request and sends it through
the existing typed `AdminAPI.selfeditRun` body. The admin sidecar's existing
SQLite self-edit start claim uses that ID, so replaying the same request
returns the existing action state instead of dispatching a second planner
job.

If the HTTP request throws before a decoded response arrives, the Edit view
model retains the original goal, model selection, request ID, and
`AdminAPI` instance. Its Retry / Check Run action reuses all four, including
the original backend endpoint if the active API configuration changes. A
decoded response clears the pending identity. The UI's spoken preview path,
sandbox boundary, and PR approval step are unchanged.

The admin sidecar also refuses a deprecated bare `/api/selfedit/run`
request with a missing/blank `run_id`, or one over 256 characters, before
constructing an agent, claiming an action, or dispatching work. Staged
requests remain keyed by their issued staging ID. Older raw bare clients
therefore fail safely with an actionable response instead of launching an
unreconcilable mutation.

Validation:

- `./.venv/bin/python -m pytest tests/unit/test_admin_selfedit.py tests/unit/test_admin_appbuild.py tests/integration/test_selfedit_end_to_end.py tests/unit/test_mcp_selfedit_logic.py tests/unit/test_run_id_injection.py -q --tb=short` — **176 passed**, **1 dependency deprecation warning**. Covers claimed bare retries, missing/oversized ID refusal, staged starts, app-build independence, end-to-end sandbox lifecycle, and current registry injection. Test fixtures use synthetic action IDs to model updated clients.
- `./.venv/bin/ruff check --select F,I jarvis/admin/server.py mcp_servers/mcp_selfedit/logic.py tests/unit/test_admin_selfedit.py tests/unit/test_admin_appbuild.py` — passed.
- `./.venv/bin/python -m compileall -q jarvis/admin/server.py mcp_servers/mcp_selfedit/logic.py tests/unit/test_admin_selfedit.py tests/unit/test_admin_appbuild.py` — passed.
- `swiftc -parse macos/JarvisKit/Sources/JarvisKit/AdminAPI.swift macos/JarvisKit/Tests/JarvisKitTests/AdminAPITests.swift macos/MortimerHost/Sources/MortimerHost/Drawer/EditTab.swift` — passed syntax parsing.
- `swift test --package-path macos/JarvisKit --filter AdminAPITests.testSelfeditRunEncodesGoalInKeys --cache-path /private/tmp/jarvis-swift-package-cache --manifest-cache local` — attempted after approval to run outside the restricted sandbox; SwiftPM fetched the pinned WebRTC source, then produced no visible progress while downloading its xcframework artifact for several minutes. The test was interrupted. No Swift compilation or test pass is claimed.
- `RUN_LIVE=0 ./.venv/bin/python -m pytest tests/unit tests/integration -q --tb=short` — **3,026 passed, 4 skipped, 11 warnings, 2 subtests passed** in 99.47 seconds after the server fail-closed change. The skips are existing environment/provider-gated tests, not passes for those gates.
- `git diff --check` — passed.

This closes the missing action ID for the in-repository native Edit-tab
caller, makes same-process transport retries idempotent, and refuses raw
unkeyed bare requests before dispatch. Process-restart reconciliation of a
pending native request and live Mac interaction remain unverified. The full
Python suite passed for this slice, but does not validate native client
compilation or behavior. This receipt covers a
dirty isolated tree, not a clean commit, merged branch, installed app, or
release acceptance.
