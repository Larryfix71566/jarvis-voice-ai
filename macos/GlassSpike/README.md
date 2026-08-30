# GlassSpike

A throwaway T1.1 target answering one question for Larry's Liquid Glass
design review (T1.0): does `.glassEffect()` over a transparent `NSWindow`
actually read as glass, and is text on it legible over a busy desktop?

Delete this target after G1(a) (signed below) — see `macos/README.md`.

## Running it

```
cd macos/GlassSpike
swift build
swift run
```

Two windows open (Panel A, Panel B). Each has a segmented control to
switch between **Arm 1** (a transparent `NSWindow` with SwiftUI's
`.glassEffect()`) and **Arm 2** (the `NSVisualEffectView` fallback ported
from `MortimerShell/WindowVibrancy.swift`), and a toggle for
`JARVIS_GLASS_ENABLED` that swaps to the rollback look
(`.regularMaterial`, matching plan §9).

## The screenshot checklist (§8 S1–S6)

Take these on Larry's hardware, two displays connected, over a
**deliberately busy desktop**: a full-screen photo with both light and
dark regions, plus a terminal with white-on-black text visible behind the
panel.

| Shot | Setup | Pass | Fail |
|---|---|---|---|
| **S1 — transparency exists** | Arm 1, one window, `.regular` panel over the photo | The photo is *recognisable* through the panel; the window is not a grey rectangle | Uniform grey/white → Arm 1 failed; take S1b with Arm 2 and note it |
| **S2 — `.regular` vs `.clear` side by side** | Both panels in one window | Both visibly different from each other and both showing the desktop | Indistinguishable → record it; the T1.0 review needs to know the two treatments do not differ meaningfully here |
| **S3 — legibility over the worst case** | Panel positioned over the boundary between the photo's brightest and darkest region | All three text sizes readable **without leaning in**, including the 13 pt line | The 13 pt line unreadable → record the smallest size that *is* readable; T1.3's type floor is that number |
| **S4 — two windows, two displays** | Both windows open, two displays attached | One window fully on each display, each filling `visibleFrame` | Both on one display → `SpikeScreenPlacement` / `openWindow` did not take effect; capture `Console.app` output for `screen-placement` |
| **S5 — one display, both windows** | Unplug the second display with both open | Left window 60% width, right 40%, both full height (DP8) | Any other split |
| **S6 — hot-plug** | With both windows open on one display, plug the second display back in | Windows relocate **without a relaunch** (`didChangeScreenParametersNotification`) | Requires relaunch → the observer is not registered |

A failing S1 does not block G1(b) — it blocks T1.0's design brief, which
is exactly what the spike is for.

## Results (Larry, 2026-08-30)

All six shots passed as described:

- **S1 — PASS.** Arm 1 (`.glassEffect()` over a transparent `NSWindow`)
  composites the real desktop: the photo is recognisable through the
  `.regular` panel. The T1.0 design brief can build on Arm 1; Arm 2
  remains the known-good fallback.
- **S2 — PASS.** `.regular` and `.clear` are visibly distinct treatments,
  both showing the desktop.
- **S3 — PASS.** All three text sizes readable over the bright/dark
  boundary without leaning in — **T1.3's type floor is 13 pt.**
- **S4 — PASS.** One window per display, each filling `visibleFrame`.
- **S5 — PASS.** Second display unplugged: 60/40 split, full height (DP8).
- **S6 — PASS.** Hot-plug relocated both windows without a relaunch.

## Sign-off

**G1(a) passes only when Larry signs this line:**

Signed: ___LEF___  Date: ___08/30/26___
