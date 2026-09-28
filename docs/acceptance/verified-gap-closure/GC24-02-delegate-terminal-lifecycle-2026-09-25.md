# GC24-02 delegate terminal lifecycle

**Date:** 2026-09-25  
**Scope:** delegate-task event observer isolation, exactly-once terminal
status, and detached-run failure handling. This is a partial GC24-02 receipt.

## Change and lifecycle boundary

The existing `delegate_start`/`delegate_done` UI lifecycle is retained. Event
observer failures no longer interrupt specialist execution. Each started
delegation now has an idempotent terminal-event owner: normal completion emits
the existing terminal event, while detached task cancellation or an
unexpected runner exception receives one bounded failure terminal from the
task completion path. This also resolves a status card when session shutdown
cancels the detached runner.

Unexpected runner errors return only a bounded exception class. Late delivery
uses that same bounded failure result rather than raw exception text. The
existing barge-in behavior is preserved: interruption of the voice waiter
does not cancel the specialist; its eventual result still uses the existing
late-delivery hook.

Canaries cover an observer that raises on start and terminal events, an
unexpected runner exception, direct child cancellation at shutdown, and a
detached exception after barge-in. The orphaned-success test also verifies
exactly one terminal event.

## Verification

- Focused delegate suite: **56 passed**.
- Full unit/integration suite:
  `RUN_LIVE=0 .venv/bin/python -m pytest tests/unit tests/integration -q --tb=short`
  — **2,887 passed, 4 skipped, 11 warnings, 2 subtests**.
- Ruff `F` checks on delegate implementation/tests: passed.
- `git diff --check`: passed.

This closes only the delegate-card terminal/failure slice. GC24-02 remains
open: provider and full tool-loop lifecycle correlation, production text-delta
consumption, artifact/tool-result ownership, cancellation propagation to all
provider/tool/UI/database owners, late side-effect suppression, and unknown
mutating-tool reconciliation still require implementation and proof. This is
dirty isolated-tree evidence, not a Mac candidate or release claim.
