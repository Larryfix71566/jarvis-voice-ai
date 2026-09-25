# Orb crystal glass — 2026-09-24

Plan: `docs/plans/MORTIMER_ORB_CRYSTAL_GLASS_PLAN.md` (rev 1). Commit: PENDING (Larry commits).
Baseline: `a1ca3c8`. Both edited files matched the plan's §0 rule 2 hashes before editing, and again in the baseline copy.
Hardware: Mac17,4, Apple M5, macOS 27.0 (26A428), main screen scale 2. Apple Swift 6.4.
Runner: `Claude outputs/orb-crystal/run_orb_checks.sh` (scratch, not committed). Each suite ran with its package directory as the working directory, so fixtures are in `macos/MortimerHost/.build/interface-fixtures/`.

## Differences from the plan's letter
- Step 0 ran the baseline suites in a throwaway checkout of `a1ca3c8` (a detached worktree, removed afterwards) instead of in the working tree before editing. It is the same code, and the working tree was not touched. The edits had been written before a Mac terminal was available to run the baseline.
- No compile fixes were needed (§0 rule 3). `DEVIATIONS.md` is unchanged.

## Tests
- OrbShellFlagTests: 4 executed, 0 failures (rerun after `swift package reset`; see the JarvisKit note below)
- CrystalOrbShellTests: 7 executed, 0 failures
- VoiceWaveRenderingTests: 10 executed, 0 failures
- WindowVisibilityTests: 4 executed, 0 failures
- Full MortimerHost: baseline 250 executed, 3 skipped, 0 failures. After the change: 258 executed (the 250 plus 8 new), 3 skipped, 0 failures. The same 3 tests skip in both runs: `ScreenPlacementTests.testConnectedExternalDisplayIsExposedToPlacementTopology` and two `SupportingDisplayAcceptanceTests`, all of which need a second display.
- Full JarvisKit: baseline 195 executed, 0 failures. After the change: 199 executed (the 195 plus the 4 new), 0 failures.
- JarvisKit note: `macos/JarvisKit/.build/workspace-state.json` points the WebRTC artifact at `/Users/larryfix/Documents/jarvis-voice-ai-clean/…`, the repository's former location. As a result, `swift test` in `macos/JarvisKit` fails while planning the build, before anything compiles. This is not caused by the change: the baseline built JarvisKit in a clean checkout and passed. MortimerHost also compiles JarvisKit from source in its own build directory, and that build includes `JarvisFlags.orbCrystalShellEnabled`, which `CrystalGlassRig.swift` calls. Larry ran `swift package reset` in `macos/JarvisKit`, which rebuilt the cache, and then both JarvisKit runs above passed.

## Frame time (`orb-frame-time.json`; 1440 × 220 pt, 300 frames each, Mortimer speaking)
- Empty canvas p50/p95: 0.83 / 0.89 ms. Legacy shell: 7.01 / 14.17 ms. Crystal shell: 5.72 / 13.59 ms.
- Gates:
  - Sensitivity: pass (7.01 > 1.10 × 0.83)
  - Budget: pass (13.59 ≤ 16.7)
  - Relative: pass (5.72 ≤ 1.5 × 7.01)
- The crystal shell measured faster than the legacy shell at both p50 and p95 on this run.

## Visual acceptance (Larry)
- Live: Larry reported "the new orb looks good" on 2026-09-24.
- Fixtures vs references: Claude compared the Swift renders side by side with `docs/interface-research/orb-crystal/crystal-<state>-400x180.png` for all five states. They show the same features in the same places:
  - the two-pane window at the upper left, near the rim
  - the strip light and the softer second window at the lower right
  - the dark wall line
  - the wall glow in the talker's color
  - the glass still visible in standby

## Live check (Larry)
- States seen live: accepted by Larry, 2026-09-24 ("the new orb looks good")
- Placements (conversation, rail, bottom): NOT YET RECORDED
- Reduce Motion: NOT YET RECORDED
- Rollback off and on via `defaults`: NOT YET RECORDED
