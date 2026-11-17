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
