# GC24-02 — app-build submission session claim

**Snapshot:** dirty isolated worktree `codex/isolated-20260924`, base/HEAD `977f50bec7b77bd7d3381d3b8f3d63fa69bd00e2`; not a clean commit, live GitHub publication, or deployed Mac result.

## Change

The app-build PR submission endpoint now uses the sandbox's persisted session ID as its stable action identity in the existing SQLite `execution_action_claims` table, under the separate `mcp-apps.app_build_submit` scope. This prevents the same app-build session from submitting twice even after the in-memory job slot moves or the sidecar recovers the workspace. The endpoint verifies active branch, proposed edits, and successful validation before it claims or dispatches. A prior claim without a verifiable saved PR returns a reconciliation-needed outcome and is never automatically replayed. A legacy/recovered `publishing` or `publication_pending` workspace also fails closed even if it predates a durable claim. A saved publication URL remains authoritative when SQLite is unavailable. `app_build_status` accepts the returned `submission_id` to inspect that exact claim/session. Claim-store read/write failure blocks new dispatch.

The public two-phase MCP confirmation and existing workspace publisher remain in place. No arguments, source content, proposal text, or PR contents are added to the claim receipt.

## Validation

```text
./.venv/bin/python -m pytest tests/unit/test_admin_appbuild.py tests/unit/test_mcp_apps_logic.py -q --tb=short
76 passed, 1 warning in 2.22s
```

Coverage includes successful submission followed by duplicate requests, recovery of the saved PR URL even when the claim store cannot be read, status lookup by submission ID, a pre-existing pending-publication session without a claim, claim-store failure before dispatch, unknown outcome after a submission exception with replay blocked, validation refusal before claim/dispatch, honest MCP handling of unknown/completed responses, and the existing asynchronous submission/status path. The warning is the existing Starlette `httpx` deprecation.

`.venv/bin/ruff check jarvis/admin/server.py tests/unit/test_admin_appbuild.py --select F,I`, compileall for `jarvis/admin/server.py`, and `git diff --check` passed.

After integration into the full dirty snapshot, `RUN_LIVE=0 ./.venv/bin/python -m pytest tests/unit tests/integration -q --tb=short` passed **3,053**, with **4 skipped**, **11 warnings**, and **2 subtests**, in 99.47 seconds. The exact snapshot includes the self-edit async-test timing stabilization recorded in the current review plan.

## Limits

This is one app-build submission action family. It does not close other mutation families, end-to-end caller lifecycle/cancellation, full source-to-sink privacy, or live GitHub/Mac acceptance. A claim cannot undo a PR that was already created; ambiguous outcomes require status/repository reconciliation before any separate action.
