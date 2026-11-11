# Mortimer interface direction and orb spec, approved 2026-11-11

This is the approved design for the release closure interface work (`docs/plans/MORTIMER_RELEASE_CLOSURE_PLAN.md`, items C0b to C9). Build it on the `next` branch. It comes from mockups and has not been rendered in Swift.

## Approved direction (4 + 5 + 6)

Larry picked the direction on 2026-11-10 in his Claude Duet channel. Directions 4, 5 and 6 are sections of `mortimer-ui-directions.html` in this folder:

- **4, Composed Answers:** a result is laid out as one composed answer, not a raw tool dump.
- **5, Result Carousel:** results sit in a glass carousel. Placement A is the default, and B is "show all results".
- **6, the orb:** a glass energy orb that reacts to voice and to pointer and touch, on the Mac and the phone. Rust is reserved for Mortimer.

Larry approved the orb on 2026-11-11 at 03:07 UTC ("Looks right"). The palette was approved earlier that day. All palette entries are new tokens; `amber`, `green` and `red` keep their values (plan C0b, C2):

| Token | Value | Use |
|---|---|---|
| `listening` | `#6673FF` | listening arcs |
| `user` | `#2DD4BF` | arcs while you speak |
| `mortimer` | `#E07020` | arcs while Mortimer speaks |
| `ok` | `#A6FFC1` | success |
| `approval` | `#FFD84A` | needs-you ring |
| `error` | `#FF598B` | errors |

## Pending: depth of the orb itself

On 2026-11-11 at 03:12 UTC, Larry asked whether the orb itself can have depth so it doesn't look flat on the screen. Options are being mocked up, so the depth treatment is **pending Larry's pick**. Items 1 (glass) and 3 (arc depth) below may change with that pick. Don't build the shell or shading part of C6 until this section records his answer.

## Sources

- `mortimer-ui-directions.html` in this folder is a copy of the mockups page (version 9). The original is a private page in Larry's account. Line numbers below refer to this copy. It also contains the plasma demo's code (from line 1114).

## What to build

1. **Glass.** Use the existing crystal shell unchanged (`CrystalGlassRig.swift`; its values are frozen with Larry's approval). Pending the depth pick above.
   - Replace only the `plasma()` call at `CometOrbRenderer.swift:300`, inside the 0.885 clip.
   - Drop the orbiting comets at `:286` and `:345`.
2. **Energy.** Port the demo's `bolt()`, `arc()` and core code as written (page lines 1114 onward).
   - Work in demo units: R = 148 sits on the shell's 0.885 inner wall.
   - The state table S is at line 1117:

     | State | Arcs | Colour / extra |
     |---|---|---|
     | listening | 4 | `#6673FF` |
     | you | 9 | `#2DD4BF` |
     | Mortimer | 9 | `#E07020` |
     | thinking | 5 | spinning |
     | muted | 1 | `#5A6478`, plus a mic-slash |
     | connecting | 2 | plus a rim sweep |
     | offline | none | |
     | you over Mortimer | rust arcs | plus one teal bolt |

3. **Arc depth** (line 1154). Pending the depth pick above.
   - Each arc end has a depth z. Each frame it moves by up to ±0.025, staying within [−0.9, 0.95]. It projects to r = R·√(1−z²).
   - Front arcs (z > 0) are 1 + 0.9z wider. When z > 0.15 they end in a contact spot of radius (6+8·level)(1+1.6z).
   - Back arcs are drawn at alpha 0.4 + 0.6(1+z). They are drawn before a dark occluder (radius 0.8·core) and before the core.
   - A touch or the pointer inside the glass pulls arc ends to that point on the front face.
4. **Small sizes: arc-width floor** (line 1134). Let s be points per demo unit; the demo uses 0.85.
   - At s ≥ 0.85, widths are unchanged.
   - Below that, let r = s/0.85. The bright line's on-screen width is 0.85·w·√r + max(0, 1.5·min(1, (1−r)/0.25) − 1.02·√r) pt.
   - The mid stroke is 2.5× that and the glow 6×.
   - Dots and contact spots scale by 1/√r. The branch count is unchanged.
5. **Core** (line 1174). The gradient radius is 74.3 + 3 + 22·level + 3·sin(5t) units. Its half-strength edge (0.75 × that radius) is always at least 1/3 of the glass radius, in every state.
6. **Flash cap** (line 1184). After drawing each frame:
   - Measure the frame's mean luminance L on a 24×24 downsample.
   - Show clamp(L, A ± 3% of Lref). The anchor A moves at most 4% of Lref per frame and reverses at most once per 220 ms. Lref = max(0.995·Lref, L).
   - Apply the gain evenly to the whole frame, or blend with the previous frame. Never clip individual passes.
   - In the model this gives at most 2.5 flashes a second; the uncapped demo gives about 14. This is a brightness model, not a measurement of rendered pixels.
7. **Input** (line 1200). Larry decided this works from the first version, not hover alone.
   - Hover or touch pulls an arc to that point.
   - Tap or click toggles the mic, like `MicControlsView.swift:34`.
   - Press and hold for 350 ms is push-to-talk. It must share the `pttOwned` guard (`MicControlsView.swift:19`, `:105`, `:110`), because releasing Space always mutes (`:113`). It must restore the mic to its state before the hold.
   - The orb needs a button role and an accessibility label. Today it ignores hits (`VoiceWaveView.swift:63`).
8. **Needs you.** Show a yellow `#FFD84A` ring outside the glass, in any state. It is driven by a pending draft (today `OrbFieldView.swift:289`, `displayResults.hasPendingDraft`) and by a file-send approval.
9. **Reduce Motion.** Redraw arcs every 6th frame, as the demo does. Thinking keeps a still ring. Reduce Transparency uses the existing `Glass.swift` fallbacks.

Line references are checked against `origin/main` at `5777e98`.

## Gates and open items

- **Performance:** add an arcs probe to `OrbShellFrameTimeTests` (1440×220, 300 frames). A p50 or p95 more than 10% above the crystal shell's counts as a regression (box 810; plan item C10 records its baseline).
- **Tests that need Larry's OK:**
  - The idle colour in code is still `#7C8CFF` (`AppTuning.swift:127`).
  - Two tests expect a coloured nucleus, which is now white (`VoiceWaveRenderingTests.swift:297`, `:314`).
- **Untested:** Swift Canvas rendering, Mac and iPhone frame time, touch feel, and flash safety measured on real pixels.
