# GC24-06 receipt: classify headless window fixtures

**Date:** 2026-09-25  
**Worktree:** `codex/isolated-20260924`  
**Source state:** dirty isolated worktree based on `977f50bec7b77bd7d3381d3b8f3d63fa69bd00e2`  
**Scope:** remove false product failures from tests that require a real visible WindowServer; preserve those checks for an interactive Mac and keep their acceptance gates open here.

## Findings and changes

The runner reports `NSScreen.screens.count == 0`, `NSScreen.main == nil`,
and `NSApp.activationPolicy()` as `-1`. The former window-visibility test
attempted to show/minimize windows despite the absence of a screen and then
failed animation and visibility assertions. The graph frame-time test
similarly reported a passing transaction p95 while its `NSViewBackingLayer`
remained dirty and no screen backing factor existed. Those values did not
establish on-screen behavior.

- `WindowVisibilityTests` now skip only the three tests that require a visible
  window when the test process has no screen or cannot activate as a regular
  app. The observer-stop test remains active and passes.
- The dense-graph frame benchmark now requires a visible display and a regular
  app policy before measuring. It checks dirty layers after render-server
  completion, rather than between `CATransaction.flush()` and that completion,
  and includes each layer's `needsDisplay` state in its diagnostic survey.
  A headless transaction no longer produces a misleading on-screen p95 result.
- `ScreenPlacement` accepts an injectable screen-unlock observer. Production
  still registers `com.apple.screenIsUnlocked` with
  `DistributedNotificationCenter`; the unit test supplies the same callback
  deterministically instead of depending on loginwindow's distributed-notice
  service inside XCTest.

## Verification

- `SWIFTPM_MODULECACHE_OVERRIDE=/private/tmp/mortimer-swiftpm-module-cache swift test --disable-sandbox --package-path macos/MortimerHost --filter KnowledgeAtlasTests` — **10 passed**, 0 failures.
- `SWIFTPM_MODULECACHE_OVERRIDE=/private/tmp/mortimer-swiftpm-module-cache swift test --disable-sandbox --package-path macos/MortimerHost --filter 'WindowVisibilityTests|ScreenPlacementTests|MemoryGraphFrameTimeTests'` — **14 executed, 5 skipped, 0 failures**. Skips: three visible-window tests (no screen), frame benchmark (no screen), and external-display topology (fewer than two non-mirrored displays).
- `SWIFTPM_MODULECACHE_OVERRIDE=/private/tmp/mortimer-swiftpm-module-cache swift test --disable-sandbox --package-path macos/MortimerHost` — **265 executed, 7 skipped, 0 failures**. The other skips are the two physical supporting-display journeys; the remaining listed skips are the three window-server tests, external-display topology, and on-screen graph benchmark.
- The Python unit/integration regression remains **2,923 passed, 4 skipped, 11 warnings, and 2 subtests** from the current source snapshot; no Python source changed in this increment.

## Remaining acceptance

This is test-fixture classification and deterministic source-test evidence. It
does not establish window occlusion/animation, real unlock delivery, the
on-screen graph p95, a two-display result journey, live Atlas authentication
recovery, accessibility, or the deployed candidate. Run those checks in an
interactive Mac session with the required display topology and record the
exact candidate and environment. The documented frame p95 threshold remains
33 ms; this headless run has no valid p95 gate result.
