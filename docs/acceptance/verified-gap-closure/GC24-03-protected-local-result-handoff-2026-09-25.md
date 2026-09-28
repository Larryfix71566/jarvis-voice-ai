# GC24-03 — Protected local specialist-result handoff

**Date:** 2026-09-25  
**Branch:** `codex/isolated-20260924`  
**Base:** `977f50bec7b77bd7d3381d3b8f3d63fa69bd00e2`; source tree remains dirty.  
**State:** one specialist-result path implemented and tested; GC24-03 remains open.

## Gap and behavior

A confidential or local-only SubAgent could return its full answer as ordinary
delegate tool text to the external voice supervisor. The protected path now
requires a local-result sink, awaits its delivery, and returns only a fixed
content-free status with an opaque reference. If policy requires protected
handling but the selected route is not private, the request fails before
`execute_chat` constructs a provider client. Missing local delivery fails
before a request, and protected route clients are deferred until after the
route and result-sink checks pass. Missing or failed local delivery does not
return the protected answer.

The workload privacy floor now comes from static configured workload policy,
not the user-selectable model route preference. The static privacy requirement
is combined with selected-route and sensitive-turn policy using the existing
strictest-policy rule, so a preference cannot downgrade a confidential
workload to approved-external processing.

Protected SubAgent activity events are allow-listed to status metadata. The
private result is carried over the existing `type: display` transport and
retains its policy label and reference in the native payload. The app marks
protected content, prevents it from being copied/shared/exported, rejects
protected comparison and preview actions, and includes the policy label in
display identity so public and protected payloads cannot collide. No second
result store or protected-content persistence was added.

## Validation

- `RUN_LIVE=0 .venv/bin/python -m pytest tests/unit tests/integration -q --tb=short`:
  **2,867 passed, 4 skipped, 11 warnings, 2 subtests passed**.
- Focused SubAgent, delegate, pipeline-event, and run-log suite:
  **131 passed**, covering a `Future` result sink, no client creation when a
  private route has no local sink, and rejection when a route preference tries
  to lower the configured workload privacy floor.
- MortimerHost `ShareCoordinatorTests|ConsoleActionCoordinatorTests`:
  **19 passed, 0 failures**. The first sandboxed SwiftPM attempt could not
  launch macOS `sandbox-exec`; the same focused test command completed when
  run with the required elevated build-tool access.
- `scripts/audit_model_call_sites.py --require-covered`: **26/26 covered,
  0 review-required, secret-free**. This confirms call-site inventory only;
  it does not prove the separate source-to-sink audit.
- Ruff `F`/`I` checks on touched Python files: passed.
- `git diff --check`: passed.

## Limits and next work

This is only the SubAgent-to-local-results path. It does not prove all model,
tool-continuation, memory, voice-supervisor, TTS, sharing, export, telemetry,
provider-session, or direct-mode sinks. The configured workload labels do not
by themselves prove confidential-compute capability; GC24-04 remains required
before any such route is enabled. There was no Mac candidate, provider call,
vault access, deployment, merge, or production-memory enablement in this
verification.

Continue GC24-02's remaining production-consumer, whole provider/tool-loop
terminal, cancellation/late-write, and mutating-tool reconciliation work;
continue GC24-03 with a complete source-to-sink inventory and negative
canaries. Do not close either parent phase from this receipt.
