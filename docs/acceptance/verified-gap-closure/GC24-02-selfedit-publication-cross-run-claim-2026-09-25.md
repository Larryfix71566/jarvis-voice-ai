# GC24-02 — Self-edit publication cross-run claim

**Date:** 2026-09-25  
**Worktree:** `codex/isolated-20260924`, dirty isolated tree  
**Base:** `977f50bec7b77bd7d3381d3b8f3d63fa69bd00e2`  
**Scope:** final PR publication through background `selfedit_finish` and native `/api/selfedit/submit`.

## Change

The existing persisted sandbox session ID is now returned as the submission
action identity. Both publication paths claim that ID in the existing SQLite
execution-action ledger after validation passes and before calling the
publisher. Validation failures do not create a publication claim, so the same
session remains repairable. A duplicate claim returns `started: false` and
cannot dispatch a second publication.

`GET /api/selfedit/run?finish_action_id=…` now recovers the exact finish
outcome after the in-memory job slot has moved. It distinguishes a saved PR
URL, a repairable validation failure, and an uncertain publication. For an
uncertain result it reports reconciliation required and never retries. The
database receipt stores only action identity and lifecycle state; the PR URL
is recovered from the existing sandbox session. The MCP finish/status tools
return and accept this identity, and do not describe a duplicate as a newly
started validation.

The live two-display result path, user preview, sandbox, and GitHub PR review
boundary were not altered. A local claim cannot undo a publication that has
already committed at GitHub.

## Verification

- `./.venv/bin/pytest -q tests/unit/test_admin_selfedit.py tests/integration/test_selfedit_end_to_end.py tests/unit/test_mcp_selfedit_logic.py` — **151 passed**, 1 dependency deprecation warning.
- `./.venv/bin/pytest -q tests/unit tests/integration` — **2,963 passed, 4 skipped, 11 warnings, 2 subtests passed**.
- `./.venv/bin/ruff check --select F,I jarvis/admin/server.py mcp_servers/mcp_selfedit/logic.py mcp_servers/mcp_selfedit/server.py tests/unit/test_admin_selfedit.py tests/integration/test_selfedit_end_to_end.py tests/unit/test_mcp_selfedit_logic.py tests/sandbox_fakes.py` — passed.
- `./.venv/bin/python -m compileall -q jarvis/admin/server.py mcp_servers/mcp_selfedit/logic.py mcp_servers/mcp_selfedit/server.py` — passed.
- `git diff --check` — passed.

Tests cover repair after validation failure, duplicate finish after clearing the
live slot, PR URL recovery from sandbox state, unknown outcome after simulated
dispatch interruption, direct native submit deduplication, status lookup by
action identity, claim-store failure blocking dispatch, and prevention of a
new sandbox session's PR URL being attributed to an older action. The full suite
uses the isolated test runtime; it does not prove a live GitHub publication,
Mac candidate, merge, deployment, or release acceptance.

## Remaining GC24-02 gaps

This receipt closes only self-edit PR publication replay for the two named
paths. Other mutating caller families, full provider/tool terminal ownership,
downstream cancellation and late-write suppression, and exact live-candidate
voice-to-result evidence remain open. Continue with the next inventoried
caller only after reconciling dirty file ownership.
