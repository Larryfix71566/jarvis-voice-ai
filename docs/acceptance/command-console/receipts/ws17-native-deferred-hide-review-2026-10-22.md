## Independent Static Review — `WindowVisibilityTests.swift` (revision `00fa4a0`, diff against prior `157f195` state)

**Method:** Review limited to the diff and resulting full file content supplied above. No execution, no tool use. Treated the quoted run-history/pass-fail narrative (six-case gate, 845cb34, combined-636, native-trace timestamps) as user-asserted context, not independently verified.

### 1. Source isolation
Confirmed. Every hunk in the diff is inside `WindowVisibilityTests.swift`. `WindowVisibilityReader.swift` and `VoiceWaveView.swift` have no diff hunks against them — reviewed only for context, and both are consistent with "no product/observer change."

### 2. What actually changed in this revision vs. the prior one
Two substantive changes, both additive/narrowing, not replacing prior logic:
1. `waitForVisibleFixture` now requires the visible/non-hidden/occluded/`condition()` conjunction to hold **continuously for ≥0.35s** before returning (unchanged from the prior static review's description of `157f195`'s helper — this part is not new in this diff).
2. **New in this revision:** the call site inside `testVisibleFixtureRecoversFromAnApplicationHideAfterShowing` that establishes the *initial* positive fixture was changed from a raw `pumpEvents(until: { reports.last == true })` to `waitForVisibleFixture(window, until: { reports.last == true })`.

This second change is the actual delta being reviewed here, and it's the one claimed to fix "3 initial-visibility assertions failing in the immediate-hide regression." That claim is causally coherent: the three failing assertions immediately follow that call site (`window.isVisible`, `occlusionState.contains(.visible)`, `reports.last == true`), and prior to this change that specific site was the **only remaining place in the file that established a positive fixture without going through the settling helper** — every other positive-establishment call site (`testActualWindowHideShowAndDetachUpdateVisibility`, the two `VoiceWave` tests, and the second half of this same test after the explicit hide) already used `waitForVisibleFixture`. So this closes the one gap consistent with the reported failure mode (a momentary true sample followed by a real transition back to hidden/invisible). I independently traced all `pumpEvents(until:)` call sites in the file and found no other positive-check site still on the unsettled path.

### 3. Setup isolation / helper reuse vs. negative checks
Verified line-by-line: the hide/miniaturize/orderOut/close *negative* assertions (`app.isHidden && reports.last == false`, `window.isMiniaturized && reports.last == false`, etc.) all remain on the original raw `pumpEvents(until:)`, untouched. This is correct — `waitForVisibleFixture` performs corrective `unhideWithoutActivation()`/`orderFrontRegardless()` inside its poll, which would actively fight a test that is trying to observe a transition *into* hidden/invisible/occluded. The diff does not introduce any helper reuse on a negative-check path. `testStoppedObserverCannotDeliverQueuedState` (the negative-wait test) is untouched.

### 4. Assertion / bound preservation
All pre-existing `XCTAssertTrue`/`XCTAssertEqual` lines in `testVisibleFixtureRecoversFromAnApplicationHideAfterShowing` are textually unchanged and in the same order. The 3-second default in `pumpEvents(until:timeout:)` is unmodified. The one new assertion (`XCTAssertTrue(settled, ...)`) is additive inside the helper, not a replacement.

### 5. New regression test (`testVisibleFixtureRecoversFromADeferredApplicationHide`)
Unchanged from what the diff adds (not newly modified in this revision's delta, but part of what's under review as the full file). I independently re-traced the ordering guarantee claimed:
- The helper's settle threshold (0.35s) is strictly larger than the scheduled hide delay (0.1s), so the hide will always land inside the helper's wait window and force at least one reset/retry — not a coincidental race.
- The async closure's nested `pumpEvents(until: { NSApp.isHidden })` is reentrant (it recursively calls `RunLoop.main.run(until:)` from inside a dispatch block that is itself being drained by an outer `RunLoop.main.run(until:)`). I confirmed this is structurally safe here, not merely "usually fine": because the nested call is synchronous and must return before control passes back to the outer run-loop tick, `deliveredHiddenState` is guaranteed to be set **before** the outer helper's condition closure can next observe `NSApp.isHidden == true`. There is no interleaving under which the outer helper could reset/recover from the hide before the inner closure records it. All mutated state (`visibleSince`, `settled`, `deliveredHiddenState`) is touched only on the main thread/run loop, so there's no genuine data race, only reentrancy, which is a supported (if fragile) Cocoa pattern.
- This test still bypasses the production `WindowVisibilityReader` observer path and asserts directly on `NSWindow`/`NSApp`. That's correct in scope, since the defect under repair is in the test helper, not production code — consistent with the stated "observer/application unchanged" constraint.

### 6. Residual timing margin
The settle threshold (0.35s) still has only ~44ms headroom over the single quoted empirical race gap (0.306s). This revision doesn't touch that number; it only extends the *coverage* of the existing settling logic to one more call site. The margin concern from the prior review is unchanged by this diff and remains a margin risk, not a logic defect.

### 7. Minor code observation (not a defect)
In the rewritten helper, the early `if NSApp.isHidden || !window.isVisible || !window.occlusionState.contains(.visible) { visibleSince = nil }` is redundant with the `guard ... else { visibleSince = nil; return false }` a few lines later — both paths reset `visibleSince` under an overlapping set of conditions (the guard's condition set is a superset, adding `condition()`). This doesn't produce incorrect behavior (the earlier reset only ever duplicates work the guard would also do), just dead-weight duplication.

---

## Blockers
**None found** in this diff under static review.

## Optional hardening (non-blocking)
1. 0.35s settle margin retains only ~44ms headroom over the one quoted empirical race sample (0.306s); if the regression reappears, widen the margin or make it environment-scaled rather than fixed.
2. The redundant `visibleSince = nil` reset before the guard clause (§7 above) can be deleted without behavior change; harmless as-is.
3. The deferred-hide test's nested/reentrant `pumpEvents` call (async closure calling `pumpEvents` while already inside a `pumpEvents`-driven run-loop turn) works by construction but is timing-fragile; a short comment marking the reentrancy as intentional would prevent a future "cleanup" from silently changing its timing.

## Coverage limits
- Static/source-only review; no execution performed, no pass/fail claim made for this or any prior revision. Per instructions, the six-case/full-profile/845cb34/00fa4a0 run outcomes referenced in the prompt are treated as asserted context supplied by the user, not verified here.
- I did not have an independent pre-diff full file for `157f195`; "no other positive-check site remains unsettled" was established by scanning the complete final file's call sites, not by a separate before/after diff of the whole file.
- Real WindowServer/run-loop timing behavior (true latency of hide/occlusion notification delivery, reentrant-run-loop interaction specifics) can't be confirmed without execution on real hardware; the margin analysis in §6 rests on the one quoted empirical sample only.

## Verdict
**No blocking findings.** The reviewed delta (reusing the settled helper at the initial positive-establishment call site) is a narrowly scoped, assertion-preserving change that plausibly and traceably closes the one remaining unsettled positive-check path consistent with the reported "3 initial-visibility assertions" failure; negative/hide-path checks and all original assertions/bounds are unmodified. Do not treat this as a claim that the current `a672239`/`00fa4a0` six-case or full-profile run has passed — that remains pending per the stated context.
