# GC24-06 — Atlas refresh lifecycle implementation progress

**Date:** 2026-09-24
**Worktree:** `codex/isolated-20260924`
**Base:** `977f50b` (dirty isolated worktree)
**State:** implementation progress; live acceptance open.

## Implemented in this worktree

- `AtlasStore` owns per-source asynchronous refresh tasks, coalesces an
  in-flight request unless an explicit forced refresh replaces it, and
  cancels active work when the Atlas view exits.
- Per-source generations reject responses from canceled or superseded loads.
- Each source distinguishes idle, loading, loaded, empty and failed states;
  failures retain last-good cards and mark them stale. Failure categories are
  bounded to unavailable, timed out and invalid response.
- The Atlas shows per-source status and freshness, has an explicit refresh
  action, refreshes on backend reconnect, and retains the existing result and
  context projections. No periodic polling or new network client was added.
- Focused tests cover store-owned success, failed refresh with stale
  last-good retention, empty-vs-failed state, generation rejection, stable
  identity and preservation of result selection/placement/grouping.

## Verification

Command:

```text
swift test --package-path macos/MortimerHost --filter KnowledgeAtlasTests
```

Result: **7 tests, 0 failures**. Xcode emitted existing deprecation warnings
for accessibility setup in unrelated test files.

The full MortimerHost suite was also attempted. It reported eight failures,
all in `WindowVisibilityTests`; a targeted rerun reproduced those GUI fixture
failures with the app inactive, one screen and occlusion 8192. They are not
counted as passing or waived by this receipt. The Atlas-focused suite passes.

## Still open

This receipt does not establish successful live authentication, partial source
failure, expired-auth recovery, a reliable source-change event, display-move or
tab-switch no-duplicate-fetch behavior, VoiceOver/keyboard acceptance,
multi-display behavior, current candidate identity, or graph/frame-time
performance. Verify these on an identified candidate and preserve the existing
graph acceptance budgets. GC24-06 remains open until its full plan criteria
pass.

No deployment, merge, provider transmission, secret access, or user-level
acceptance is claimed.
