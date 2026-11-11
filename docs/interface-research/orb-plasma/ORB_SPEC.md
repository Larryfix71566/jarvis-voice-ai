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

## Sources

- `mortimer-ui-directions.html` in this folder is a copy of the mockups page (version 12). The original is a private page in Larry's account. Line numbers below refer to this copy. The direction 6 orb code starts at line 1137.

## What to build

1. **Glass.** Use the existing crystal shell unchanged (`CrystalGlassRig.swift`; its values are frozen with Larry's approval). Refraction and the shadow (see "Depth of the orb itself" below) are added around it.
   - Replace only the `plasma()` call at `CometOrbRenderer.swift:300`, inside the 0.885 clip.
   - Drop the orbiting comets at `:286` and `:345`.
2. **Energy.** Port the demo's `bolt()`, `arc()` and core code as written (page lines 1137 onward; `bolt()` and `arc()` are at 1159 and 1160).
   - Work in demo units: R = 148 sits on the shell's 0.885 inner wall.
   - The state table S is at line 1140:

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

3. **Arc depth** (line 1177). This is the arcs' own depth, separate from the orb's refraction below.
   - Each arc end has a depth z. Each frame it moves by up to ±0.025, staying within [−0.9, 0.95]. It projects to r = R·√(1−z²).
   - Front arcs (z > 0) are 1 + 0.9z wider. When z > 0.15 they end in a contact spot of radius (6+8·level)(1+1.6z).
   - Back arcs are drawn at alpha 0.4 + 0.6(1+z). They are drawn before a dark occluder (radius 0.8·core) and before the core.
   - A touch or the pointer inside the glass pulls arc ends to that point on the front face.
4. **Small sizes: arc-width floor** (line 1152). Let s be points per demo unit; the demo uses 0.85.
   - At s ≥ 0.85, widths are unchanged.
   - Below that, let r = s/0.85. The bright line's on-screen width is 0.85·w·√r + max(0, 1.5·min(1, (1−r)/0.25) − 1.02·√r) pt.
   - The mid stroke is 2.5× that and the glow 6×.
   - Dots and contact spots scale by 1/√r. The branch count is unchanged.
5. **Core** (line 1193). The gradient radius is 74.3 + 3 + 22·level + 3·sin(5t) units. Its half-strength edge (0.75 × that radius) is always at least 1/3 of the glass radius, in every state.
6. **Flash cap** (line 1204). The far-wall echo and the cast light below ride this cap. After drawing each frame:
   - Measure the frame's mean luminance L on a 24×24 downsample.
   - Show clamp(L, A ± 3% of Lref). The anchor A moves at most 4% of Lref per frame and reverses at most once per 220 ms. Lref = max(0.995·Lref, L).
   - Apply the gain evenly to the whole frame, or blend with the previous frame. Never clip individual passes.
   - In the model this gives at most 2.5 flashes a second; the uncapped demo gives about 14. This is a brightness model, not a measurement of rendered pixels.
7. **Input** (line 1225). Larry decided this works from the first version, not hover alone.
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

## Depth of the orb itself: refraction plus option 1's shadow

Larry asked at 03:12 UTC whether the orb could look less flat. At 03:18:31 he picked option 3 ("I think the third"), and at 03:19:59 he refined that: "I actually like the third but add the shadow from the first".
Shown on the mockups page (version 12, line 531, section "Depth for the orb itself", option 3, which now carries option 1's shadow too). Option 2 (tilt parallax) is built only if the fallback below is triggered.

**Shadow and cast light (from option 1).** Drawn in the orb's Canvas, outside and below the glass, before the bloom.
- Floor line at centre + 1.14 Rg.
- Contact shadow: an ellipse 1.05 Rg wide and 0.2 of that tall. Black, at 0.62 opacity in the middle, 0.34 at 45%, and 0 at the edge.
- Cast light: an ellipse 0.62 Rg wide and 0.24 of that tall, drawn additively. White at 0.42 × L in the middle, the state colour at 0.5 × L at 22%, then 0, where L is the capped brightness Ls / Lref.
- It needs about a quarter of the orb's height free below the orb in the rail layout.

**Look.** Inside the glass radius Rg, what is behind the orb shows through as a solid glass ball would show it: inverted and magnified in the middle, squeezed toward the rim. For a pixel at offset d from the centre, with rho = |d| / Rg, sample the backdrop at centre + d / k, where k = -(0.42 + 1.25 (1 - rho^2)). That is -1.67 in the middle and -0.42 at the rim. The mockup draws this as 18 stepped rings; the shader should use the continuous formula. Darken the result 30% toward #060A0E (glass absorption). Outside Rg, pass the pixels through unchanged. A faint far-wall echo of the arcs sits on top: the same capped energy frame, inverted, scaled by 0.8 around the centre, drawn additively at alpha 0.16 × the cap's gain.

**Minimum OS (checked at 5777e98).** The orb lives in `macos/MortimerHost` (`Console/CometOrbRenderer.swift`), and MortimerHost is `.macOS(.v26)`. Other targets: JarvisKit `.macOS(.v26), .iOS(.v26)`; MortimerShell package `.macOS(.v14)`, with its app project at `MACOSX_DEPLOYMENT_TARGET = 26.5`; MortimerPhoneCore `.iOS(.v17)`; MortimerPhoneApp `IPHONEOS_DEPLOYMENT_TARGET = 17.0`. `layerEffect` needs macOS 14 / iOS 17, so every target meets it.

**Swift approach (proposed; untested).**
- Put a SwiftUI `layerEffect` Metal shader (`ShaderLibrary`) on the rail content behind the orb. It is the only built-in way for SwiftUI to sample pixels at another position; a Canvas can't see the views behind it.
- `maxSampleOffset` must cover the rim case. A rim pixel samples 1/0.42 ≈ 2.4 Rg away on the opposite side, so allow about 3.4 Rg.
- Inputs: orb centre, Rg, and the far-wall tint.
- The orb's own Canvas stays on top, unchanged: the crystal shell, the energy, and the far-wall echo, which goes inside the shell's 0.885 interior clip and before the energy.
- This would be the app's first Metal shader; nothing in the app uses Metal today.
- Alternative if the shader route is blocked: redraw the rail's static background inside the orb Canvas and refract only that. It is cheaper but wouldn't show live content.

**Fallbacks.**
- Reduce Transparency: no refraction. The orb uses the existing `Glass.swift` opaque fallback.
- Reduce Motion: no change. Refraction is static apart from what moves behind it.
- Low frame rate: see the budget below.

**Flash safety.** The echo is a fixed share of the capped frame, and the cast light follows the capped brightness, so both ride the same cap. The refracted backdrop is steady, apart from content scrolling behind the orb, which moves through it magnified and inverted. Watch for that being distracting in the rail; it is not a flash risk on the brightness model.

**Measure first (box 810: more than 10% over baseline counts as a regression; plan item C10 records the baseline).**
1. Before building the rest of the orb, add two probes to `OrbShellFrameTimeTests`, using the same 1440×220 size and 300 frames: arcs only, and arcs plus refraction. Compare both with the crystal shell probe (receipt 2026-09-29: p50 4.933 ms, p95 14.150 ms).
2. Include the shadow and cast light in the arcs plus refraction probe. Pass: p50 and p95 each at most 1.10× the crystal shell, and p95 under 16.7 ms.
3. If the test harness can't render a `layerEffect` off-screen, measure the same scene on screen with Instruments on the Mac and record the method.
4. The phone has no frame-time probe yet; one is needed before the phone orb ships.
5. If arcs plus refraction fails while arcs alone passes, the proposed fallback is options 1 and 2 together: keep the contact shadow with cast light, and replace refraction with tilt parallax. Switching needs Larry's OK. Both options are in the mockup and cost two gradient fills and some offsets.
