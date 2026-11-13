---
date: 2026-11-14
system: kimi
rows: [WS-36]
prs: [373]
---

# WS-36 C6: Mac glass energy orb

Implementation branch: `kimi/ws-36-c6-glass-energy-orb`, based on `origin/next` at `6a7ac289babee8da959706c16f9cc58abe1a44a6`. Reviewer: Codex. This PR remains draft until C5 has merged and the two `AdaptiveStageView.swift` orb slots are integrated.

## Implemented before the C5 hand-off

- Replaced the renderer's comets/plasma energy with C2-coloured, deterministic depth-projected arcs, voice levels, thinking swirl, pointer attraction, tap ripple, needs-you ring, contact spots, ground shadow and cast light.
- Preserved the crystal rig and added the approved refraction curve and shader-free static fallback. Live backdrop sampling is not claimed.
- Added frame-rate-independent easing for the wave and orb (`r = dt × 60`), including the depth step and flash anchor/decay. The existing paused Reduced Motion schedule is retained.
- Added orb button accessibility, tap-to-toggle and 350 ms hold ownership/restoration. `MicControlsView.swift` is outside C6's file list, so the new guard reproduces Space's ownership semantics but cannot yet share Space's actual `pttOwned` variable; this integration boundary remains explicit for review.
- Removed `OrbFieldView.swift`. Its legacy compact implementation remains temporarily source-compatible inside `VoiceWaveView.swift` for existing tests and the pre-C5 slots; the C6 slots will mount the interactive energy orb instead.
- Added pure easing/PTT/refraction tests and same-session five-run crystal/arcs/arcs+refraction performance probes. Hosted CI skips timing gates; Larry runs them on his Mac.

## Validation and hand-off

- `git diff --check`: passed locally.
- Local `swift test`: not run; this Linux environment has no Swift toolchain. Test counts must come from an actual macOS/hosted run and must not be inferred.
- B1 `swift-tests`: pending at log creation.
- C5 merge, merge of current `next`, and orb slots in `Console/AdaptiveStageView.swift`: pending.
- No merge, deployment, restart, live test or change into `main` performed.
- `data/jarvis.db` is not present in the repository checkout, so there were no stored long-term-memory facts available to review for interface-capability conflicts.
