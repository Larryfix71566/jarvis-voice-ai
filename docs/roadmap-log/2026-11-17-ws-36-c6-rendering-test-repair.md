---
date: 2026-11-17
system: kimi
rows: [WS-36]
prs: [376]
---

# WS-36 C6 rendering-test repair — 2026-11-17

**System:** Kimi
**Branch:** `kimi/ws-36-c6-rendering-test-repair`
**Target:** `next`

## After-merge state

This PR carries the approved measured-time and 0.1-second Reduced Motion follow-up, repairs the C6 rendering behavior exposed by run `43997964123`, updates obsolete pre-C6 expectations, and points the native agent-roster parity guard at `VoiceWaveView.swift`. It is stacked on Claude's reviewed #375 compile fixes so hosted MortimerHost testing can reach these tests before #375 lands. It does not merge or modify #375.

## Failure decisions

- **Unavailable assistant speech:** renderer defect. Freezing `AtomMotion` did not freeze `OrbEnergyState`; colour, level, depth and flash continued changing with no measured audio. The unavailable/static path now keeps energy time at zero, so repeated frames are identical.
- **Reduced Motion idle and muted:** stale expectations. C6's approved schedule is one advance per 0.1 second, not a permanently frozen orb. Rendering tests now require identical pointer-style repaints between ticks and a changed frame at the next tick. Offline remains static.
- **Connected muted versus listening:** stale expectation. C6 specifies one slate arc and a mic slash for muted, versus four indigo listening arcs. Normal muted motion remains covered.
- **Measured speaker colours:** test defect. The old test sampled after only 100 ms, while the approved colour easing was still mid-transition. Tests now render 60 frames at 60 Hz before checking teal and rust pixels.
- **User-over-Mortimer overlap:** renderer defect. The implementation used teal arcs and a teal bolt; the approved design is rust arcs plus one teal bolt. The energy pass now uses Mortimer rust during overlap and retains the separate teal bolt.
- **Nucleus colour:** stale expectations. The approved C6 nucleus is white. Both voice-wave tests and the crystal-shell speaker test now assert a neutral core rather than teal, orange or periwinkle.
- **Crystal reflection area:** test-measurement defect. The room pass is screened over energy, so full-frame bright-pixel counts included white arc strokes. The test now renders the state-independent room pass directly instead of attributing those extra pixels to reflections.
- **Python agent parity:** stale path. C6 deleted standalone `OrbFieldView.swift`; `AGENT_LAYOUT` and the legacy compact type now live in `Console/VoiceWaveView.swift`. Both roster guards read that file and their diagnostics name it.

`tests/unit/test_agents_yaml_frontend_parity.py` is outside C6's original file list but is included under Larry's explicit 2026-11-17 repair assignment. Codex's separate command-console manifest failure is not included.

## Verification

- `git diff --check`: passed locally.
- Direct invocation of all three tests in `tests/unit/test_agents_yaml_frontend_parity.py`: passed (`PARITY_OK: 3 tests passed`). The sandbox does not have `pytest` installed.
- Swift/MortimerHost: not run locally; this Linux sandbox has no Swift toolchain. Hosted B1 results on the exact PR head are the authoritative compile and rendering evidence.
- No production deployment, restart, live test, merge, or main-branch change is included.

## Claude takeover — 2026-11-18

Larry handed #376 to Claude to finish (2026-11-18, "You fix it"). Claude merged `next` (`fec254e`, with #375, #378 and #382) into this branch and fixed the five failures read from the CI logs at `3dac764e`. No tolerance was widened and no test was skipped.

- **White nucleus (2 tests):** every front arc and the barge-in bolt start at the centre, so their tinted halos were drawn over the core and left it 6-9% teal or rust. `drawEnergy` now re-lights the inner quarter of the core in white (plus-lighter) after the front arcs and the bolt. Speaker colour stays in the arcs and the core's outer ring.
- **Flash cap (1 test):** `OrbFlashCap.advance` stopped once the remaining difference was under `step × 0.5`, a band that grows with dt, so the 15 Hz cap settled at 0.096 instead of 0.100 and ended 0.004 apart (0.480 vs 0.484). Moving on in the current direction now always lands exactly on the target; only a reversal keeps a dead band, fixed at 2% of Lref (the 60 Hz half-step). A Python port reproduces the old 0.480/0.484 and gives equal anchors at 15, 30, 60 and 120 Hz for 2,000 random targets with the fix.
- **Reduce Motion test (1 test):** renamed to `testReducedMotionSamplesVisibleWaveAtTenHertzOrSlower`. It asserts the 0.1 s contract Larry chose on 2026-11-14 (at most 6 samples and at least 1 in 0.5 s) instead of the paused orb.
- **Window visibility (1 test):** CI facts: `testActualWindowHideShowAndDetachUpdateVisibility` passes on `next` `fec254e` (17.8 s) and on #375 `214de6b` (18.2 s), and fails on #376 in 3 of 3 runs (23.4 s at `6049c91`). A first try at `6049c91` changed `WindowVisibilityView` delivery (coalesce instead of cancel); the test still failed, so that change is reverted and the observer is byte-identical to `next` again. The largest process-level change #376 makes before this test is window churn: `renderSettled` in `VoiceWaveRenderingTests` (the suite just before it) opened 61 fixture windows per call, about 370 per run, and that suite went from 3.6 s to 34.9 s. The 60 warm-up frames now draw offscreen through `ImageRenderer` (with a check that all 60 drew), and only the sampled frame uses a window. Cause still unproven until CI on this head; if it still fails, the next step is the Mac reverts.
- **Boot ramp:** commit `108df44` dropped the `min(1, …)` clamp on the legacy wave's E2 boot ramp, so amplitude fell to 0 at 1.8 s and went negative after it. The ramp is now `WaveEngine.bootRamp(now:bootStart:)`, clamped to [0, 1], with `testLegacyBootRampHoldsSteadyAmplitudeAfterItCompletes` (full amplitude at bootStart + 5 s, never falling back).
- **ORB_SPEC:** restored the C10 receipt path, which this branch had pointed at the #358 review.

Swift was not run in Claude's sandbox (no toolchain). Hosted MortimerHost CI on this branch's head is the evidence. Larry waived outside Kimi/Codex review for this work (non-prod).
