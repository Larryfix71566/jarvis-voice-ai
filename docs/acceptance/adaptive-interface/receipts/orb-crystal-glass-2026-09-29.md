# Orb crystal glass — 2026-09-29

Plan: `docs/plans/MORTIMER_ORB_CRYSTAL_GLASS_PLAN.md` (Revision 2).
Implementation branch: `codex/ws08-crystal-only-20260929`.
Hardware: Mac17,4 / Apple M5 / macOS 27.0; main display scale 2.

## Automated checks

- JarvisKit: 215 executed, 0 failures.
- Focused `CrystalOrbShellTests`: 7 executed, 0 failures.
- Focused `OrbShellFrameTimeTests`: 1 executed, 0 failures.
- Focused `WindowVisibilityTests`: 4 executed, 3 skipped because the test host could not become active in this WindowServer session; 0 failures.
- Full MortimerHost: 374 executed, 5 skipped, 1 failure. The failure was `ProtectedDisplayContentTests.testProtectedContentInActualWindowCaptureMatchesBodyOnlyReference` at line 134. It is outside WS-08's changed files. On unchanged base `0cc42f2`, the same actual-window test skipped because the test host could not become active; the focused current-branch run skipped it for the same limitation. The full-suite mismatch is recorded as environment-sensitive; the full suite is not claimed green.
- Crystal fixture images: `.build/interface-fixtures/orb-crystal-{standby,idle,user,mortimer,overlap}.png` under `macos/MortimerHost/` (generated, ignored build artifacts).

## Frame time

Focused benchmark, 300 frames per probe at 1440 × 220 pt:

- Empty p50/p95: 0.842 / 0.917 ms.
- Crystal p50/p95: 4.933 / 14.150 ms.
- Sensitivity: pass (`4.933 ms > 1.10 × 0.842 ms`).
- Absolute budget: pass (`14.150 ms ≤ 16.7 ms`).
- JSON: `macos/MortimerHost/.build/interface-fixtures/orb-frame-time.json` (ignored build artifact).

## Visual and live acceptance

- Existing deployed build, Larry-reported before this cleanup: compact and expanded layouts showed the orb correctly; Reduce Motion kept it visible and stopped movement.
- Deployment: Larry's DEPLOY-MAIN installed `c3607e6` on 2026-09-29. The release gate passed JarvisKit 218/0, MortimerHost 383 tests with six unrelated skips and zero failures (including the executed real protected-window capture), Python 4,924 passed and seven skipped, and healthy service/revision checks.
- Larry reaffirmed in this task after deployment that compact/expanded appearance and Reduce Motion behavior were already confirmed. Do not ask for these checks again.
- Codex regenerated the five fixtures from merged source matching the deployed orb product files; `CrystalOrbShellTests` passed 7/0. The production `.build` fixture PNGs were dated 09-24 and were not used. Current PNGs below are 400 × 180; approved references render at 800 × 360. Codex's visual inspection found the required features in the same relative positions, with normal renderer blur/gradient differences. Larry's step 8 visual approval was open at this 09-29 check; the final sign-off below closes it.
- [Idle current](orb-crystal-glass-2026-09-29-fixtures/orb-crystal-idle.png) · [approved reference](../../../interface-research/orb-crystal/crystal-idle-400x180.png)
- [Standby current](orb-crystal-glass-2026-09-29-fixtures/orb-crystal-standby.png) · [approved reference](../../../interface-research/orb-crystal/crystal-standby-400x180.png)
- [User current](orb-crystal-glass-2026-09-29-fixtures/orb-crystal-user.png) · [approved reference](../../../interface-research/orb-crystal/crystal-user-400x180.png)
- [Mortimer current](orb-crystal-glass-2026-09-29-fixtures/orb-crystal-mortimer.png) · [approved reference](../../../interface-research/orb-crystal/crystal-mortimer-400x180.png)
- [Overlap current](orb-crystal-glass-2026-09-29-fixtures/orb-crystal-overlap.png) · [approved reference](../../../interface-research/orb-crystal/crystal-overlap-400x180.png)
- The plan's named live voice states (listening, user, Mortimer, overlap, standby) and placements (conversation, rail, bottom) are not all itemized in the post-deployment record. At this 09-29 check, unobserved combinations remained; compact/expanded and Reduce Motion were already confirmed. Larry's overall sign-off below closes the WS-08 gate without asserting those individual observations.

## Final human acceptance — 2026-09-30

Larry explicitly confirmed in the Codex task that WS-08 has been tested and accepted. This closes the outstanding human visual/live acceptance gate for the deployed crystal-only orb. The 09-29 fixture links and automated/deployment evidence above remain the supporting record. Larry did not provide a separate observation matrix for each named live state and placement, so this receipt records his overall acceptance without attributing unreported individual observations. No additional WS-08 test is requested.
