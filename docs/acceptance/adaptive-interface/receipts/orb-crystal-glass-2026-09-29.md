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
- Fixture comparison against the approved reference: pending Larry review.
- Post-deployment compact/expanded and Reduce Motion recheck: pending.
- Deployment: not performed by Codex.
