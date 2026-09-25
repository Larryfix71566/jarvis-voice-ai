# Mortimer orb crystal glass plan — replace the orb's glass shell with option A

**Status:** IMPLEMENTED 2026-09-24, receipt `docs/acceptance/adaptive-interface/receipts/orb-crystal-glass-2026-09-24.md`. Step 9's placement, Reduce Motion and rollback checks are open until recorded in that receipt.
**Owner:** Larry. Implementation goes to a coding model in one pass. Larry runs every commit, merge and install, and steps 8 and 9. The implementer never runs `git merge`, `git push`, `launchctl`, `defaults write`, or `bundle.sh`.
**Approved design:** option A ("Crystal") from the orb glass comparison, chosen by Larry on 2026-09-23. The comparison page is the Claude artifact https://claude.ai/artifact/852XZZzAqkt5WmHUe6ruGY. A copy of it and reference renders are checked in under `docs/interface-research/orb-crystal/`.
**Baseline inspected:** `main` at `a1ca3c8` (2026-09-23). File hashes in §0 rule 2.
**Safety claim:** the adaptive interface plan's contracts UI-1 through UI-7 (`docs/plans/MORTIMER_ADAPTIVE_INTERFACE_PLAN.md` §3) stay in force word for word. This plan adds no contract and relaxes none. It changes pixels inside the orb's glass and nothing else.

Path shorthand: `MH/` = `macos/MortimerHost/Sources/MortimerHost/`, `JK/` = `macos/JarvisKit/Sources/JarvisKit/`, `MHT/` = `macos/MortimerHost/Tests/MortimerHostTests/`, `JKT/` = `macos/JarvisKit/Tests/JarvisKitTests/`.

| Rev | Date | Change |
|---|---|---|
| 1 | 2026-09-23 | First version. |

## 0. Binding constraints for the implementing model

1. **Copy, do not author.** Every line of new or changed code is in Appendices A–F. Insert it exactly. Do not rename, reorder, reformat, "simplify" or re-derive anything, and do not change any number.
2. **Check the baseline first.** Before editing, run `shasum -a 256` on the two files you will edit. They must match:
   - `MH/Console/CometOrbRenderer.swift` → `1ee8617c735cb8488d80e26a642e5b502d580755dbbf9c64008da2bdc22d932c`
   - `JK/JarvisConfig.swift` → `dbc184c9211c572590f1846c5b9b0a34af9fb76fd4068bebd7efaa7083962a52`

   If either differs, stop and report both hashes and `git log -3 --oneline -- <file>`. Do not merge by hand.
3. **Compile errors.** The appendix code was written against Apple's SwiftUI documentation but has not been compiled. If `swift build` fails, you may fix only type and syntax problems (an argument label, a missing explicit `CGFloat(...)` or `Double(...)` conversion, a missing `self.` or `Self.`, an import). A fix may not change a numeric constant, a color, a blend mode, a draw order, a clip, a filter radius or a shape. Record each fix in `DEVIATIONS.md` using that file's entry format (next free `D-` number, "Architecture impact: none"). If the only fix you can find changes one of those things, stop and report the compiler output.
4. **Tests.** Existing tests are not edited, skipped or loosened (UI-7). If an existing test fails after the change, stop and report the test name and its output. If a new test from this plan fails, stop and report its output and any JSON or PNG it wrote. Do not tune a threshold or a design constant to make a test pass.
5. **Scope.** Touch only the files in §4. Nothing under `jarvis/`, `web/`, `config/`, `scripts/`, or any other Swift file.
6. **Look.** Do not judge whether the result "looks right" and adjust it. Visual acceptance is Larry's, in step 8.

## 1. Background (verified against the source at `a1ca3c8`)

The orb is drawn by `CometOrbRenderer.draw` (`MH/Console/CometOrbRenderer.swift`), called only from `WaveEngine.drawAtom` (`MH/Console/VoiceWaveView.swift:475-486`) when a `VoicePresentationState` is present. That is every adaptive layout: the default Command Console (layout 2, `ConsoleView.swift:71` → `CommandConsoleView` → `AdaptiveStageView`) and layout 1 (`ConsoleView.swift:75` → `AdaptiveStageView`), in all three `AdaptiveStageView` placements: conversation (full width, 150–220 pt tall, `:95`), rail (200 × 150, `:102`) and bottom (220–280 × 180, `:114`). Layout 0 (`ConsoleView.swift:57`) draws the legacy Silo wave without a presentation state, not the orb, and is unaffected.

`draw` has two parts. Lines 25–48 compute the shared state: center, `radius = 0.255 × extent`, `energy`, `ambient`, `ready`, `tint` by activity, `strength` (0.52 + 0.48 × energy when ready, 0.16 otherwise) and `breath`. Lines 50–103 draw the shell around two unchanged helpers, `plasma(…)` (`:106`) and `comets(…)` (`:200`). All motion comes from `phase`, which `AtomMotion` advances from elapsed time; the renderer itself reads no clock.

Why the current shell reads as light and not glass, from the code:

- The sphere fill is 2.5% → 6% opacity from the center to 65% radius (`:62-68`). There is no glass body.
- The only highlight is a disc 0.25 × radius wide, 40% peak opacity, blurred (`:93-99`).
- The rim band, the four arcs and the highlight are multiplied by `strength`, which is 0.16 in standby (`:65-66`, `:90`, `:98`). The glass nearly disappears when Mortimer is offline.
- The back half of each comet orbit is drawn first (`:52-55`) under that thin fill, so it shows through at nearly full brightness.

## 2. Scope

**In scope:** a new shell for the adaptive orb, option A. It adds a glass body, a thick-wall line, a Fresnel-weighted room reflection, a two-pane window reflection and a rim strip light placed by mirror-sphere geometry, a softer second window reflection off the far wall, a caustic, rim dispersion and a silhouette hairline. It also adds a rollback flag, tests, reference images and two documentation updates.

**Unchanged, and tested where a test can see it:**

- `plasma(…)`, `comets(…)`, `AtomMotion`, `WaveEngine`, `VoicePresentationState`, `AudioPresentationTuning` (colors, gains, dB windows).
- Orb geometry: radius 0.255 × extent, comet orbits 1.53 / 1.17 × radius, tilts −0.48 / +0.56.
- Nucleus color by talker, both channels visible during overlap, standby and Reduce Motion stillness, "audio unavailable" stillness.
- Accessibility label and value (`VoiceWaveView.swift:28-29`), window-visibility sampling, wake flash, Debug ▸ Wave level windows.
- `OrbFieldView` (readout, satellites, beams, captions, notices), every drawer tab, `Glass.swift` panels, the legacy Silo wave for layout 0.

**Out of scope:** options B and C; the frozen web console (`web/src/components/OrbField.tsx`); any change to how comets or plasma look; caching reflections into bitmaps (D5); removing the legacy shell (a later cleanup once the crystal shell has shipped).

## 3. Decisions

**D1 — Option A exactly as previewed.** Every constant in Appendix A equals the value in the approved preview (`docs/interface-research/orb-crystal/glass-orb.html`, `STYLE.crystal`, `KEY`, `STRIP`, `FRESNEL`, `buildEnv`, `drawGlass`). *Why:* Larry chose what he saw. Changing a value, even to "improve" it, is a new design decision.

**D2 — Only the shell changes; the legacy shell stays byte-for-byte.** `draw` gains a `shell` parameter and branches right after `breath` is computed. The crystal path calls the same `plasma` and `comets` with the same arguments as the legacy path. The legacy lines are not edited. *Why:* the request was "all existing features the same outside of the look of the glass". Leaving the old lines untouched makes the rollback exact.

**D3 — Rollback flag `JARVIS_ORB_CRYSTAL`, default on, read once per launch.** It follows the `JarvisFlags.audioMeterEnabled` pattern. The environment wins: `off`, `false`, `0` and `no` turn it off, anything else turns it on. Otherwise `UserDefaults` is used, and an absent key means on. `OrbShell.resolved` is a `static let`, so the flag is read once and changes take effect on the next launch. *Why:* this repo keeps a no-rebuild rollback lever for visual changes (`JARVIS_GLASS_ENABLED`, `JARVIS_FORCE_WEBRTC`). Reading once avoids an environment lookup on every frame at 60 Hz. **Decision made on Larry's behalf. Larry: confirm it, or strike it. If it is struck, this plan gets a rev 2 that removes the flag everywhere it appears; do not implement rev 1 with parts deleted.**

**D4 — Light geometry is computed, not drawn by hand.** A distant light in direction *d* reflects toward the viewer where the surface normal is `normalize(d + view)`. Its screen position is that normal's x and y times the radius (`CrystalGlassRig.mirrorPoint`). The window panes and the strip are superellipse rectangles in light space, mapped point by point (96 samples). The outlines are `static let`s in unit coordinates, computed once per process and scaled each frame. *Why:* this is what makes the reflection curve with the sphere. It is also the preview's exact method, and it is pure math, so it is unit-tested.

**D5 — Draw every frame; no bitmap caching.** The reflections do not depend on voice state, so they could be cached, but they are drawn as vector fills each frame. *Why:* `CometOrbRenderer`'s own header rule is that no bitmap is substituted for voice feedback. Caching also adds size and scale invalidation to get wrong. D6 measures whether drawing every frame is affordable.

**D6 — Frame-time gate.** New test `OrbShellFrameTimeTests` uses the `MemoryGraphFrameTimeTests` span on a 1440 × 220 pt canvas, 300 frames each for an empty canvas, the legacy shell and the crystal shell. The gates are:
  - **Sensitivity:** legacy p50 > 1.10 × empty p50. This proves the span sees drawing cost; the same rule is in P4.
  - **Budget:** crystal p95 ≤ 16.7 ms, one 60 Hz frame. `VoiceWaveAnimation` samples at 60 Hz while audio is active.
  - **Relative:** crystal p50 ≤ 1.5 × legacy p50. The crystal shell adds 4 blurred layers to the legacy 10, which is 1.4×. The gate allows that with a small margin.

  If any gate fails: **stop and report the JSON** (§0 rule 4). Do not optimize. *Why:* UI2-21 requires "bounded rendering cost", and it has never been measured for the orb.

**D7 — Reflections ignore voice state; only the halo and the wall glow follow it.** The body, wall line, room reflection, caustic, window, strip, back reflection, dispersion and hairline all use fixed opacities. The halo and the wall glow are multiplied by `strength`. *Why:* a glass object keeps its reflections when the light inside goes out. This is the property the preview showed in standby, and a test pins it.

**D8 — Blur a group by filtering the layer, not its contents.** Each blurred group is drawn as `var copy = context; copy.addFilter(.blur(radius:)); copy.drawLayer { … }`. *Why:* Apple's documentation for `addFilter` says a filter "applies to subsequent drawing operations", and each one is rasterized, filtered and composited on its own. A `drawLayer` call is one operation, so this blurs the group as a whole, which is what the preview did. The legacy code blurs each stroke inside the layer instead; it is not touched (D2).

**D9 — The Fresnel layer's 0.62 opacity is multiplied into its gradient.** It is not set as a layer opacity. *Why:* under `.destinationIn` the result alpha is sky alpha × Fresnel alpha, so multiplying the sky alpha by 0.62 gives an identical result. It also avoids depending on how `drawLayer` treats `GraphicsContext.opacity`, which Apple's documentation does not state.

**D10 — The reflections are one screened layer.** The whole room reflection is drawn inside one `drawLayer` on a context copy whose `blendMode` is `.screen`, matching the preview's single screened canvas. The wall glow uses `.plusLighter`, the preview's `lighter`.

**D11 — Reference images are checked in.** Reference PNGs rendered by the preview go under `docs/interface-research/orb-crystal/`. They are the look Larry approved. The new test writes the Swift renders next to its other fixtures for side-by-side comparison. *Why:* the implementer cannot open the artifact link, and "looks like the preview" needs something to compare against.

**D12 — Tests.** Existing tests are unchanged and must pass. They exercise the crystal shell automatically, because `WaveEngine` uses `OrbShell.resolved`. New tests: `OrbShellFlagTests` (JarvisKit), `CrystalOrbShellTests` and `OrbShellFrameTimeTests` (MortimerHost). Every expected number in them was measured from the preview on 2026-09-23 and is stated in the test's header comment. The bright-area threshold is half the preview's measurement, and the other tolerances are wider than the differences the preview showed (reflection area ±15% against 0.4%, center pixel ±0.06 against 0.012), so a small Canvas-versus-SwiftUI difference does not trip them.

## 4. File manifest

| File | Change | Appendix |
|---|---|---|
| `MH/Console/CrystalGlassRig.swift` | **new**: `OrbShell`, `CrystalGlassRig` constants and geometry | A |
| `MH/Console/CometOrbRenderer.swift` | edit: `shell` parameter (E1), crystal branch (E2), crystal extension appended (E3) | B |
| `JK/JarvisConfig.swift` | edit: `JarvisFlags.orbCrystalShellEnabled` | C |
| `JKT/OrbShellFlagTests.swift` | **new** | D |
| `MHT/CrystalOrbShellTests.swift` | **new** | E |
| `MHT/OrbShellFrameTimeTests.swift` | **new** | F |
| `docs/interface-research/orb-crystal/*` | **new** (already written when this plan was delivered; verify they exist) | — |
| `docs/plans/MORTIMER_ADAPTIVE_INTERFACE_PLAN.md` | edit: one amendment paragraph | G.1 |
| `docs/acceptance/adaptive-interface/receipts/orb-crystal-glass-<YYYY-MM-DD>.md` | **new**: acceptance receipt | G.2 |
| `DEVIATIONS.md` | edit only if §0 rule 3 applied | — |

`docs/interface-research/orb-crystal/` contains `glass-orb.html` (the approved comparison page; open it in a browser), `crystal-{standby,idle,user,mortimer,overlap}-400x180.png` and `current-{…}-400x180.png` (the preview's renders at the test canvas size on black), and `contact-sheet-240x180.png` (current row above crystal row, on the app's `#15191D`, at the bottom-layout size).

## 5. Steps

Run everything from the repository root. A step is complete only when its check passes.

**Step 0 — Preconditions.** Larry creates the branch `feat/orb-crystal-glass` from `main`. Check the §0 rule 2 hashes. Confirm the reference files in §4 exist. Then, before any edit, run `swift test --package-path macos/JarvisKit` and `swift test --package-path macos/MortimerHost` in Larry's logged-in session and save both outputs as the baseline for step 7.

**Step 1 — Flag (Appendix C, D).** Insert the Appendix C lines into `JK/JarvisConfig.swift` directly after the line `    public static var glassEnabled: Bool { on("JARVIS_GLASS_ENABLED") }`. Create `JKT/OrbShellFlagTests.swift` from Appendix D.
Check: `swift test --package-path macos/JarvisKit --filter OrbShellFlagTests` → 4 tests, 0 failures.

**Step 2 — Rig (Appendix A).** Create `MH/Console/CrystalGlassRig.swift` from Appendix A.

**Step 3 — Renderer (Appendix B).** Apply E1, E2 and E3 to `MH/Console/CometOrbRenderer.swift`. Each anchor occurs exactly once in the baseline file; if one does not, stop (§0 rule 2).
Check: `swift build --package-path macos/MortimerHost` succeeds (§0 rule 3 applies).

**Step 4 — Behavior tests (Appendix E).** Create `MHT/CrystalOrbShellTests.swift`.
Check: `swift test --package-path macos/MortimerHost --filter CrystalOrbShellTests` → 7 tests, 0 failures. The test writes `orb-crystal-*.png` and `orb-legacy-*.png` for five states into the same `.build/interface-fixtures/` directory `VoiceWaveRenderingTests` already uses; it is relative to the test process's working directory, so locate it with `find . -name 'orb-crystal-standby.png' -path '*interface-fixtures*'` and record the path in the receipt.

**Step 5 — Existing orb tests.** Check: `swift test --package-path macos/MortimerHost --filter VoiceWaveRenderingTests` and `--filter WindowVisibilityTests`, 0 failures, no edits. Run these in Larry's logged-in session; `WindowVisibilityTests` is known to fail headless (closure plan G20).

**Step 6 — Frame time (Appendix F).** Create `MHT/OrbShellFrameTimeTests.swift`.
Check: `swift test --package-path macos/MortimerHost --filter OrbShellFrameTimeTests` in the logged-in session. All three gates pass, and `orb-frame-time.json` exists in the directory step 4 found. On a failed gate, D6 applies: stop and report.

**Step 7 — Full suites.** Check: `swift test --package-path macos/JarvisKit` and `swift test --package-path macos/MortimerHost`, in the same session as step 0. The set of failing tests must equal step 0's baseline set. The new tests add to the executed count and must pass. Any failure not in the baseline: stop and report.

**Step 8 — Visual acceptance (Larry).** Open `orb-crystal-<state>.png` from the directory step 4 found next to `docs/interface-research/orb-crystal/crystal-<state>-400x180.png` for all five states. Pass means the same features in the same places: the two-pane window upper left near the rim, the strip light and the softer second window lower right, the dark wall line, the wall glow lower right in the talker's color, and the glass still visible in standby. Canvas and SwiftUI blur and gradient rendering differ slightly, so this is not a pixel match. If Larry wants any value changed, that is a new revision of this plan, not an implementation fix.

**Step 9 — Live check and rollback proof (Larry).** Run `macos/MortimerHost/scripts/bundle.sh` and connect.
- Confirm the crystal shell in Listening, while you speak, while Mortimer speaks, while both speak, and in Standby.
- Confirm it in the conversation, rail and bottom placements.
- Confirm Reduce Motion (System Settings ▸ Accessibility ▸ Display) freezes it.

Then prove the rollback:
- Quit the app. Run `defaults write com.mortimer.host JARVIS_ORB_CRYSTAL -bool false`, relaunch, and confirm the old shell is back.
- Quit again. Run `defaults delete com.mortimer.host JARVIS_ORB_CRYSTAL`, relaunch, and confirm the crystal shell is back.

**Step 10 — Documentation (Appendix G).**
- Insert G.1 into `docs/plans/MORTIMER_ADAPTIVE_INTERFACE_PLAN.md` directly after the paragraph that ends ``receipt is `docs/acceptance/adaptive-interface/receipts/candidate-atom-wave-2026-09-18.md`.``
- Create the receipt from G.2, filled in with the real counts and results from steps 4–9.
- Change this plan's **Status** line to `IMPLEMENTED <date>, receipt <path>`.

Larry commits.

## 6. Where tuning values live

Every crystal-shell number is a named `static let` in `CrystalGlassRig` (Appendix A). The drawing code in Appendix B E3 contains no design numbers of its own. The only literals there are structural: gradient stop locations 0, 0.5 and 1, opacity 0 at a gradient's transparent end, `Double.pi` for the half-turn, `2` for diameters and midpoints, and `1` as the fallback length for a zero vector. A later visual change edits `CrystalGlassRig` only, and it needs Larry's approval and a plan revision (D1).

## 7. Verification

| Check | Where | Evidence |
|---|---|---|
| Flag default and both levers | `OrbShellFlagTests` (4) | test output |
| Light geometry equals the preview's math | `CrystalOrbShellTests.testMirrorPointIsTheHalfVector`, `testTheKeyWindowSitsUpperLeftNearTheRim`, `testFresnelStopsFollowSchlickForGlass` | test output |
| Default shell is crystal | `testTheShellDefaultsToCrystal` | test output |
| Glass stays visible in standby (the reported defect) | `testCrystalKeepsItsReflectionsInStandby`: crystal ≥ 35 pt² of bright reflection in the 0.55–0.95 radius band (preview 70), legacy 0 | test output |
| Reflections ignore voice state (D7) | `testCrystalReflectionsDoNotFollowVoiceState`: listening, user, Mortimer and overlap within ±15% of standby (preview: within 0.4%) | test output |
| Comets and nucleus unchanged (§2) | `testCometsAndNucleusAreUnchanged`: every pixel beyond 1.25 × radius within 2/255 of legacy, and center pixel within 0.06 per channel (preview: 0 pixels differ, center within 3/255) | test output, fixtures |
| Existing behavior | `VoiceWaveRenderingTests`, `WindowVisibilityTests`, full suites | test output |
| Cost | `OrbShellFrameTimeTests` (D6) | `orb-frame-time.json` |
| Look | Larry, step 8 | fixtures vs reference PNGs |
| Live, placements, Reduce Motion, rollback | Larry, step 9 | receipt |

## 8. Rollback

- **No rebuild:** `defaults write com.mortimer.host JARVIS_ORB_CRYSTAL -bool false`, then relaunch MortimerHost. Or launch with `JARVIS_ORB_CRYSTAL=off` in the environment. The legacy shell lines are unchanged (D2), so this is the exact previous look.
- **Full:** revert the commit. No data, settings or server state is involved.

## 9. Risks

| Risk | Likelihood | Effect | Handling |
|---|---|---|---|
| Appendix code does not compile as written | medium: written against the docs, not compiled | step 3 fails | §0 rule 3: type and syntax fixes only, logged in `DEVIATIONS.md`, otherwise stop |
| SwiftUI blur radius or gradient interpolation differs from the browser, so the look drifts from the preview | medium | window softer or harder, glow stronger or weaker | thresholds at half the preview's numbers; Larry judges in step 8; changes go through a plan revision |
| `blendMode` does not apply to a `drawLayer` composite | low | reflections composite normally instead of screened; on the dark body, for near-white reflections, the difference is small | step 8 catches a visible difference; report it and do not work around it |
| Frame cost too high on the MacBook Air at full width | unknown; not yet measured | dropped frames while talking | D6 gate; stop and report |
| The frame-time span does not see drawing cost | unknown | gate would pass without meaning anything | sensitivity gate; stop and report |
| Flag left `false` after the step 9 check | low | old look persists | step 9 ends with `defaults delete` and a visual check |

## 10. Approval

- [ ] Larry: D3 (keep a rollback flag), confirmed or struck.
- [ ] Larry: plan approved for implementation.
- [ ] Larry: step 8 visual acceptance.
- [ ] Larry: step 9 live check and rollback proof.

## 11. Handoff prompt for the implementing model

> Implement `docs/plans/MORTIMER_ORB_CRYSTAL_GLASS_PLAN.md` steps 0–7 and step 10's receipt draft in the repository at `~/jarvis-voice-ai-clean` on branch `feat/orb-crystal-glass`. Read §0 first; it overrides anything you would otherwise do. Copy code only from Appendices A–F, exactly. Do not change any number, color, blend mode, order or shape. Do not edit or skip existing tests. Run every check in §5 and paste its output. Stop and report at the first failed check, with its output. Do not run git merge or push, do not install the app, and do not run `defaults write`. Steps 8 and 9 are Larry's.

---

## Appendix A — `MH/Console/CrystalGlassRig.swift` (new file, entire content)

```swift
import CoreGraphics
import Foundation
import JarvisKit

/// Which glass shell the adaptive orb draws
/// (docs/plans/MORTIMER_ORB_CRYSTAL_GLASS_PLAN.md D3).
enum OrbShell: Equatable {
    /// Option A, approved by Larry 2026-09-23: clear, thick-walled glass lit
    /// by a studio window. The default.
    case crystal
    /// The shell exactly as it was before the plan (the 2026-09-18
    /// glass/comet revision), kept verbatim as the rollback.
    case legacy

    /// Resolved once per launch. `JARVIS_ORB_CRYSTAL=off` in the environment,
    /// or `defaults write com.mortimer.host JARVIS_ORB_CRYSTAL -bool false`,
    /// selects `.legacy` from the next launch on.
    static let resolved: OrbShell = JarvisFlags.orbCrystalShellEnabled ? .crystal : .legacy
}

/// Everything about the crystal shell that does not depend on voice state
/// or phase: the constants of the approved preview
/// (docs/interface-research/orb-crystal/glass-orb.html, option A) and the
/// light-rig geometry computed from them. Values are frozen by the plan;
/// change them only with Larry's approval.
enum CrystalGlassRig {
    /// A light's reflection on the sphere, in unit-disc coordinates
    /// (x right, y down; multiply by the sphere radius and add the center).
    struct LightOutline {
        let points: [CGPoint]
        /// Reflection of the light's center; orients its gradient.
        let mid: CGPoint
    }

    // MARK: - Colours (0...255 RGB)

    static let inkRGB: (Double, Double, Double) = (6, 10, 14)
    static let skyRGB: (Double, Double, Double) = (206, 228, 255)
    static let dispersionCoolRGB: (Double, Double, Double) = (110, 215, 255)
    static let dispersionWarmRGB: (Double, Double, Double) = (255, 165, 110)

    // MARK: - Body and wall

    /// Plasma bloom just outside the glass, times voice strength.
    static let haloOpacity = 0.035
    static let haloExtent = 1.2
    static let haloStops: [(location: Double, weight: Double)] = [(0.80, 0), (0.86, 1), (1, 0)]
    /// Glass body: absorbs more toward the edge, where the path is longer.
    static let bodyStops: [(location: Double, opacity: Double)] = [
        (0, 0.04), (0.7, 0.09), (0.88, 0.22), (0.965, 0.34), (1, 0.18),
    ]
    static let plasmaClipFraction = 0.885
    /// Plasma light carried in the wall, strongest opposite the key light.
    static let wallInnerFraction = 0.84
    static let wallOuterFraction = 1.02
    static let wallGlowOpacity = 0.46
    static let wallGlowBlurFraction = 0.035
    static let wallGlowStart = CGPoint(x: -0.2, y: -0.2)
    static let wallGlowEnd = CGPoint(x: 0.75, y: 0.75)
    /// The inner surface of a thick wall reads as a dark line with a faint
    /// light line just outside it.
    static let wallLineFraction = 0.885
    static let wallLineOpacity = 0.38
    static let wallLineWidthFraction = 0.022
    static let wallLineMinWidth = 0.8
    static let wallHighlightOffset = 0.018
    static let wallHighlightOpacity = 0.10
    static let wallHighlightWidth = 0.6

    // MARK: - Reflections (independent of voice state)

    /// Room reflection: sky gradient (top to bottom) masked by Fresnel.
    static let fresnelOpacity = 0.62
    static let skyStops: [(location: Double, opacity: Double)] = [(0, 1), (0.45, 0.55), (0.6, 0.22), (1, 0.10)]
    /// Key light focused through the globe onto the far inner wall.
    static let causticOpacity = 0.24
    static let causticMidOpacityRatio = 0.4
    static let causticCenter = CGPoint(x: 0.50, y: 0.58)
    static let causticRadiusFraction = 0.26
    static let causticBlurFraction = 0.05
    static let causticClipFraction = 0.985
    /// Two-pane window key and rim strip.
    static let keyOpacity = 0.95
    static let stripOpacity = 0.45
    static let lightsBlurFraction = 0.010
    static let lightsMinBlur = 0.35
    static let lightInnerOpacityRatio = 0.55
    static let lightGradientInnerFraction = 0.35
    /// The window seen again off the inside of the far wall.
    static let backKeyOpacity = 0.22
    static let backKeyScale = 0.74
    static let backKeyBlurFraction = 0.03
    /// Faint dispersion along the lit rim.
    static let dispersionStartRadians = -175 * Double.pi / 180
    static let dispersionEndRadians = -95 * Double.pi / 180
    static let dispersionCoolRadius = 1.0
    static let dispersionWarmRadius = 0.982
    static let dispersionCoolPeak = 0.34
    static let dispersionWarmPeak = 0.24
    static let dispersionWidth = 0.9
    static let dispersionBlur = 0.3
    static let arcSegmentCount = 48
    static let arcFalloffExponent = 1.6
    /// Silhouette hairline.
    static let hairlineFraction = 0.996
    static let hairlineOpacity = 0.20
    static let hairlineWidth = 0.7

    // MARK: - Light rig (camera space: x right, y down, z toward the viewer)

    static let keyDirection = SIMD3<Double>(-0.74, -0.70, -0.10)
    static let keyPaneHalfWidth = 0.12
    static let keyPaneHalfHeight = 0.21
    static let keyPaneOffset = 0.14
    static let stripDirection = SIMD3<Double>(0.80, 0.50, -0.30)
    static let stripHalfWidth = 0.10
    static let stripHalfHeight = 0.55
    static let outlineExponent = 6.0
    static let outlineSamples = 96

    static let keyPanes: [LightOutline] = [
        lightOutline(direction: keyDirection, halfWidth: keyPaneHalfWidth,
                     halfHeight: keyPaneHalfHeight, exponent: outlineExponent,
                     offset: -keyPaneOffset),
        lightOutline(direction: keyDirection, halfWidth: keyPaneHalfWidth,
                     halfHeight: keyPaneHalfHeight, exponent: outlineExponent,
                     offset: keyPaneOffset),
    ]
    static let strip: LightOutline = lightOutline(
        direction: stripDirection, halfWidth: stripHalfWidth,
        halfHeight: stripHalfHeight, exponent: outlineExponent, offset: 0)

    /// Schlick's approximation for glass (R0 = 0.04), sampled at these radii.
    static let fresnelSampleRadii: [Double] = [
        0, 0.3, 0.5, 0.65, 0.75, 0.82, 0.87, 0.9, 0.93, 0.95, 0.965, 0.975, 0.985, 0.992, 0.997, 1,
    ]
    static let fresnelStops: [(location: Double, reflectance: Double)] =
        fresnelSampleRadii.map { (location: $0, reflectance: schlick($0)) }

    static func schlick(_ rho: Double) -> Double {
        let cosine = max(0, 1 - rho * rho).squareRoot()
        return 0.04 + 0.96 * pow(1 - cosine, 5)
    }

    /// A distant light in `direction` reflects toward the viewer where the
    /// surface normal is the half vector normalize(direction + view). Its
    /// screen position is that normal's x and y.
    static func mirrorPoint(_ direction: SIMD3<Double>) -> CGPoint {
        let normal = normalized(SIMD3<Double>(direction.x, direction.y, direction.z + 1))
        return CGPoint(x: normal.x, y: normal.y)
    }

    /// A flat rounded-rectangle light (superellipse with `exponent`) facing
    /// the globe along `direction`, shifted sideways by `offset`.
    static func lightOutline(direction: SIMD3<Double>, halfWidth: Double, halfHeight: Double,
                             exponent: Double, offset: Double,
                             samples: Int = outlineSamples) -> LightOutline {
        let axis = normalized(direction)
        let across = normalized(cross(axis, SIMD3<Double>(0, -1, 0)))
        let up = cross(across, axis)
        func at(_ u: Double, _ v: Double) -> SIMD3<Double> {
            normalized(axis + u * across + v * up)
        }
        var points: [CGPoint] = []
        points.reserveCapacity(samples)
        for index in 0..<samples {
            let t = Double(index) / Double(samples) * 2 * Double.pi
            let cu = cos(t), su = sin(t)
            let u = offset + halfWidth * signum(cu) * pow(abs(cu), 2 / exponent)
            let v = halfHeight * signum(su) * pow(abs(su), 2 / exponent)
            points.append(mirrorPoint(at(u, v)))
        }
        return LightOutline(points: points, mid: mirrorPoint(at(offset, 0)))
    }

    private static func signum(_ value: Double) -> Double {
        value > 0 ? 1 : (value < 0 ? -1 : 0)
    }

    private static func normalized(_ v: SIMD3<Double>) -> SIMD3<Double> {
        v / (v * v).sum().squareRoot()
    }

    private static func cross(_ a: SIMD3<Double>, _ b: SIMD3<Double>) -> SIMD3<Double> {
        SIMD3<Double>(a.y * b.z - a.z * b.y, a.z * b.x - a.x * b.z, a.x * b.y - a.y * b.x)
    }
}
```

## Appendix B — `MH/Console/CometOrbRenderer.swift` edits

**E1.** Replace this line (baseline line 27):

```swift
                     outputEnergy: Double, activity: VoicePresentationState.Activity) {
```

with:

```swift
                     outputEnergy: Double, activity: VoicePresentationState.Activity,
                     shell: OrbShell = .resolved) {
```

**E2.** Directly after this line (baseline line 48):

```swift
        let breath = ambient ? 0.94 + 0.06 * sin(phase * 1.2) : 1
```

insert:

```swift

        // docs/plans/MORTIMER_ORB_CRYSTAL_GLASS_PLAN.md: the crystal shell
        // replaces everything below this point; the legacy shell stays
        // verbatim as the rollback (JARVIS_ORB_CRYSTAL=off).
        if shell == .crystal {
            drawCrystalShell(context: &context, center: center, radius: radius, phase: phase,
                             userEnergy: userEnergy, outputEnergy: outputEnergy, tint: tint,
                             strength: strength, breath: breath, energy: energy, ready: ready)
            return
        }
```

**E3.** Append the following after the file's last line (the `}` that closes `enum CometOrbRenderer`, baseline line 276):

```swift
// MARK: - Crystal shell (docs/plans/MORTIMER_ORB_CRYSTAL_GLASS_PLAN.md, option A)
//
// Same file as the legacy shell on purpose: it calls the private `plasma`,
// `comets`, `disc`, `color` and `ice` members unchanged. Every blurred group
// is drawn as ONE layer through a context copy that carries the filter, so
// the blur applies to the composited group (GraphicsContext.addFilter
// filters each drawing operation, and a drawLayer call is one operation).
extension CometOrbRenderer {
    private static func drawCrystalShell(context: inout GraphicsContext, center: CGPoint,
                                         radius: Double, phase: Double, userEnergy: Double,
                                         outputEnergy: Double, tint: Color, strength: Double,
                                         breath: Double, energy: Double, ready: Bool) {
        typealias Rig = CrystalGlassRig
        let sphere = disc(center, radius)

        // 1. Plasma bloom just outside the glass; follows the voice state.
        let haloRadius = radius * Rig.haloExtent
        context.fill(disc(center, haloRadius), with: .radialGradient(
            Gradient(stops: Rig.haloStops.map {
                Gradient.Stop(color: tint.opacity($0.weight * Rig.haloOpacity * strength),
                              location: $0.location)
            }),
            center: center, startRadius: 0, endRadius: haloRadius))

        // 2. Back half of each orbit, drawn before the body so the glass dims it.
        if ready {
            comets(context: &context, center: center, radius: radius, phase: phase,
                   userEnergy: userEnergy, outputEnergy: outputEnergy, front: false)
        }

        // 3. Glass body.
        context.fill(sphere, with: .radialGradient(
            Gradient(stops: Rig.bodyStops.map {
                Gradient.Stop(color: color(Rig.inkRGB).opacity($0.opacity), location: $0.location)
            }),
            center: center, startRadius: 0, endRadius: radius))

        // 4. Plasma, seen through the wall (plasma() itself is unchanged).
        var inside = context
        inside.clip(to: disc(center, radius * Rig.plasmaClipFraction))
        plasma(context: &inside, center: center, radius: radius, phase: phase,
               tint: tint, strength: strength * breath, energy: energy)

        // 5. Plasma light carried in the wall, strongest opposite the key light.
        var wall = context
        wall.clip(to: sphere)
        wall.blendMode = .plusLighter
        wall.addFilter(.blur(radius: radius * Rig.wallGlowBlurFraction))
        wall.drawLayer { layer in
            var ring = Path()
            ring.addEllipse(in: CGRect(x: center.x - radius * Rig.wallOuterFraction,
                                       y: center.y - radius * Rig.wallOuterFraction,
                                       width: radius * Rig.wallOuterFraction * 2,
                                       height: radius * Rig.wallOuterFraction * 2))
            ring.addEllipse(in: CGRect(x: center.x - radius * Rig.wallInnerFraction,
                                       y: center.y - radius * Rig.wallInnerFraction,
                                       width: radius * Rig.wallInnerFraction * 2,
                                       height: radius * Rig.wallInnerFraction * 2))
            layer.fill(ring, with: .linearGradient(
                Gradient(colors: [tint.opacity(0), tint.opacity(Rig.wallGlowOpacity * strength)]),
                startPoint: CGPoint(x: center.x + radius * Rig.wallGlowStart.x,
                                    y: center.y + radius * Rig.wallGlowStart.y),
                endPoint: CGPoint(x: center.x + radius * Rig.wallGlowEnd.x,
                                  y: center.y + radius * Rig.wallGlowEnd.y)),
                style: FillStyle(eoFill: true))
        }

        // 6. Wall thickness: dark inner-surface line, faint light line outside it.
        context.stroke(disc(center, radius * Rig.wallLineFraction),
                       with: .color(.black.opacity(Rig.wallLineOpacity)),
                       lineWidth: max(Rig.wallLineMinWidth, radius * Rig.wallLineWidthFraction))
        context.stroke(disc(center, radius * (Rig.wallLineFraction + Rig.wallHighlightOffset)),
                       with: .color(ice.opacity(Rig.wallHighlightOpacity)),
                       lineWidth: Rig.wallHighlightWidth)

        // 7. Reflections of the room: one layer, screened onto the scene.
        // Nothing in it depends on voice state or phase.
        var room = context
        room.blendMode = .screen
        room.drawLayer { env in
            drawCrystalReflections(into: &env, center: center, radius: radius)
        }

        // 8. Front half of each orbit.
        if ready {
            comets(context: &context, center: center, radius: radius, phase: phase,
                   userEnergy: userEnergy, outputEnergy: outputEnergy, front: true)
        }
    }

    private static func drawCrystalReflections(into env: inout GraphicsContext,
                                               center: CGPoint, radius: Double) {
        typealias Rig = CrystalGlassRig
        let sphere = disc(center, radius)

        // a. Room reflection: sky gradient masked by Fresnel reflectance.
        // The 0.62 layer opacity is folded into the gradient's alpha, which
        // is mathematically identical under destinationIn.
        env.drawLayer { layer in
            layer.fill(sphere, with: .linearGradient(
                Gradient(stops: Rig.skyStops.map {
                    Gradient.Stop(color: color(Rig.skyRGB).opacity($0.opacity * Rig.fresnelOpacity),
                                  location: $0.location)
                }),
                startPoint: CGPoint(x: center.x, y: center.y - radius),
                endPoint: CGPoint(x: center.x, y: center.y + radius)))
            layer.blendMode = .destinationIn
            layer.fill(sphere, with: .radialGradient(
                Gradient(stops: Rig.fresnelStops.map {
                    Gradient.Stop(color: Color.white.opacity($0.reflectance), location: $0.location)
                }),
                center: center, startRadius: 0, endRadius: radius))
        }

        // b. Caustic on the far inner wall.
        let focus = CGPoint(x: center.x + radius * Rig.causticCenter.x,
                            y: center.y + radius * Rig.causticCenter.y)
        let focusRadius = radius * Rig.causticRadiusFraction
        var caustic = env
        caustic.clip(to: disc(center, radius * Rig.causticClipFraction))
        caustic.addFilter(.blur(radius: radius * Rig.causticBlurFraction))
        caustic.drawLayer { layer in
            layer.fill(disc(focus, focusRadius), with: .radialGradient(
                Gradient(stops: [
                    .init(color: Color.white.opacity(Rig.causticOpacity), location: 0),
                    .init(color: ice.opacity(Rig.causticOpacity * Rig.causticMidOpacityRatio), location: 0.5),
                    .init(color: ice.opacity(0), location: 1),
                ]),
                center: focus, startRadius: 0, endRadius: focusRadius))
        }

        // c. Studio lights: the two-pane window key and the rim strip.
        var lights = env
        lights.addFilter(.blur(radius: max(Rig.lightsMinBlur, radius * Rig.lightsBlurFraction)))
        lights.drawLayer { layer in
            for pane in Rig.keyPanes {
                fillLight(&layer, pane, center: center, radius: radius, opacity: Rig.keyOpacity)
            }
            fillLight(&layer, Rig.strip, center: center, radius: radius, opacity: Rig.stripOpacity)
        }

        // d. The window again, off the inside of the far wall: rotated a
        // half turn about the center and scaled down.
        var back = env
        back.addFilter(.blur(radius: radius * Rig.backKeyBlurFraction))
        back.drawLayer { layer in
            layer.translateBy(x: center.x, y: center.y)
            layer.rotate(by: .radians(Double.pi))
            layer.scaleBy(x: Rig.backKeyScale, y: Rig.backKeyScale)
            layer.translateBy(x: -center.x, y: -center.y)
            for pane in Rig.keyPanes {
                fillLight(&layer, pane, center: center, radius: radius, opacity: Rig.backKeyOpacity)
            }
        }

        // e. Dispersion along the lit rim.
        var dispersion = env
        dispersion.addFilter(.blur(radius: Rig.dispersionBlur))
        dispersion.drawLayer { layer in
            strokeRimArc(&layer, center: center, radius: radius * Rig.dispersionCoolRadius,
                         peak: Rig.dispersionCoolPeak, color: color(Rig.dispersionCoolRGB))
            strokeRimArc(&layer, center: center, radius: radius * Rig.dispersionWarmRadius,
                         peak: Rig.dispersionWarmPeak, color: color(Rig.dispersionWarmRGB))
        }

        // f. Silhouette hairline.
        env.stroke(disc(center, radius * Rig.hairlineFraction),
                   with: .color(Color.white.opacity(Rig.hairlineOpacity)),
                   lineWidth: Rig.hairlineWidth)
    }

    /// Fills a light's reflection, brighter toward the rim.
    private static func fillLight(_ layer: inout GraphicsContext, _ light: CrystalGlassRig.LightOutline,
                                  center: CGPoint, radius: Double, opacity: Double) {
        typealias Rig = CrystalGlassRig
        var path = Path()
        for (index, point) in light.points.enumerated() {
            let p = CGPoint(x: center.x + point.x * radius, y: center.y + point.y * radius)
            if index == 0 { path.move(to: p) } else { path.addLine(to: p) }
        }
        path.closeSubpath()
        let length = hypot(light.mid.x, light.mid.y)
        let norm = length > 0 ? length : 1
        let ux = light.mid.x / norm, uy = light.mid.y / norm
        layer.fill(path, with: .linearGradient(
            Gradient(colors: [Color.white.opacity(opacity),
                              Color.white.opacity(opacity * Rig.lightInnerOpacityRatio)]),
            startPoint: CGPoint(x: center.x + ux * radius, y: center.y + uy * radius),
            endPoint: CGPoint(x: center.x + ux * radius * Rig.lightGradientInnerFraction,
                              y: center.y + uy * radius * Rig.lightGradientInnerFraction)))
    }

    /// One dispersion arc: short segments whose opacity rises and falls
    /// as sin(pi * t)^1.6 along the arc.
    private static func strokeRimArc(_ layer: inout GraphicsContext, center: CGPoint,
                                     radius: Double, peak: Double, color: Color) {
        typealias Rig = CrystalGlassRig
        let count = Rig.arcSegmentCount
        let start = Rig.dispersionStartRadians, end = Rig.dispersionEndRadians
        for index in 0..<count {
            let t0 = Double(index) / Double(count)
            let t1 = Double(index + 1) / Double(count)
            let alpha = peak * pow(sin(Double.pi * (t0 + t1) / 2), Rig.arcFalloffExponent)
            let a0 = start + (end - start) * t0, a1 = start + (end - start) * t1
            var segment = Path()
            segment.move(to: CGPoint(x: center.x + cos(a0) * radius, y: center.y + sin(a0) * radius))
            segment.addLine(to: CGPoint(x: center.x + cos(a1) * radius, y: center.y + sin(a1) * radius))
            layer.stroke(segment, with: .color(color.opacity(alpha)),
                         style: StrokeStyle(lineWidth: Rig.dispersionWidth, lineCap: .round))
        }
    }
}
```

## Appendix C — `JK/JarvisConfig.swift` insertion

Insert directly after `    public static var glassEnabled: Bool { on("JARVIS_GLASS_ENABLED") }`:

```swift
    /// docs/plans/MORTIMER_ORB_CRYSTAL_GLASS_PLAN.md D3 — the orb's glass
    /// shell. Default on (the crystal shell). `JARVIS_ORB_CRYSTAL=off` (or
    /// false/0/no) in the environment, or `defaults write com.mortimer.host
    /// JARVIS_ORB_CRYSTAL -bool false`, restores the previous shell. The
    /// environment wins. MortimerHost reads it once per launch
    /// (`OrbShell.resolved`).
    public static var orbCrystalShellEnabled: Bool {
        if let raw = ProcessInfo.processInfo.environment["JARVIS_ORB_CRYSTAL"]?.lowercased() {
            return !["off", "false", "0", "no"].contains(raw)
        }
        return on("JARVIS_ORB_CRYSTAL")
    }
```

## Appendix D — `JKT/OrbShellFlagTests.swift` (new file)

```swift
import XCTest
@testable import JarvisKit

/// docs/plans/MORTIMER_ORB_CRYSTAL_GLASS_PLAN.md D3 — the orb shell rollback
/// lever: default on, either lever turns it off, the environment wins.
final class OrbShellFlagTests: XCTestCase {
    private let key = "JARVIS_ORB_CRYSTAL"

    override func setUp() {
        super.setUp()
        UserDefaults.standard.removeObject(forKey: key)
        unsetenv(key)
    }

    override func tearDown() {
        UserDefaults.standard.removeObject(forKey: key)
        unsetenv(key)
        super.tearDown()
    }

    func testDefaultsToTheCrystalShell() {
        XCTAssertTrue(JarvisFlags.orbCrystalShellEnabled)
    }

    func testUserDefaultsFalseSelectsTheLegacyShell() {
        UserDefaults.standard.set(false, forKey: key)
        XCTAssertFalse(JarvisFlags.orbCrystalShellEnabled)
    }

    func testEnvironmentOffValuesSelectTheLegacyShell() {
        for raw in ["off", "false", "0", "no", "OFF"] {
            setenv(key, raw, 1)
            XCTAssertFalse(JarvisFlags.orbCrystalShellEnabled, raw)
        }
    }

    func testEnvironmentBeatsUserDefaults() {
        UserDefaults.standard.set(false, forKey: key)
        setenv(key, "on", 1)
        XCTAssertTrue(JarvisFlags.orbCrystalShellEnabled)
    }
}
```

## Appendix E — `MHT/CrystalOrbShellTests.swift` (new file)

```swift
import XCTest
import AppKit
import SwiftUI
@testable import MortimerHost

/// docs/plans/MORTIMER_ORB_CRYSTAL_GLASS_PLAN.md §7. Expected numbers come
/// from the approved preview (docs/interface-research/orb-crystal/), measured
/// 2026-09-23 at 400 × 180 pt on black: the key-window reflection covers
/// 70–79 pt² of the reflection band at ≥ 0.6 brightness in every voice
/// state, the legacy shell covers 0 pt², and pixels farther than
/// 1.25 × radius from the center are identical between the two shells.
@MainActor
final class CrystalOrbShellTests: XCTestCase {
    private static let width = 400.0, height = 180.0
    /// CometOrbRenderer: extent = min(height, 2 * min(cx, width - cx)) = 180, radius = 0.255 * extent.
    private static var radius: Double { min(height, 2 * min(width / 2, width / 2)) * 0.255 }

    private func render(_ activity: VoicePresentationState.Activity, userEnergy: Double = 0,
                        outputEnergy: Double = 0, phase: Double = 1.3,
                        shell: OrbShell) throws -> NSBitmapImageRep {
        let view = NSHostingView(rootView: Canvas { context, size in
            CometOrbRenderer.draw(context: &context, size: size, stageCenterX: nil, phase: phase,
                                  userEnergy: userEnergy, outputEnergy: outputEnergy,
                                  activity: activity, shell: shell)
        }.background(Color.black))
        view.frame = NSRect(x: 0, y: 0, width: Self.width, height: Self.height)
        let window = NSWindow(contentRect: view.frame, styleMask: [.borderless], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false; window.contentView = view; window.orderFrontRegardless()
        defer { window.close() }
        window.layoutIfNeeded(); view.layoutSubtreeIfNeeded()
        RunLoop.main.run(until: Date().addingTimeInterval(0.05))
        let bitmap = try XCTUnwrap(view.bitmapImageRepForCachingDisplay(in: view.bounds))
        view.cacheDisplay(in: view.bounds, to: bitmap)
        return bitmap
    }

    /// Visits every pixel with its distance from the sphere center in units
    /// of the radius. Orientation-independent, so bitmap row order cannot
    /// change the answer.
    private func forEachPixel(_ bitmap: NSBitmapImageRep,
                              _ body: (_ x: Int, _ y: Int, _ rho: Double, _ rgb: (Double, Double, Double)) -> Void) {
        let scale = Double(bitmap.pixelsWide) / Self.width
        for y in 0..<bitmap.pixelsHigh {
            for x in 0..<bitmap.pixelsWide {
                guard let c = bitmap.colorAt(x: x, y: y)?.usingColorSpace(.deviceRGB) else { continue }
                let dx = (Double(x) + 0.5) / scale - Self.width / 2
                let dy = (Double(y) + 0.5) / scale - Self.height / 2
                body(x, y, (dx * dx + dy * dy).squareRoot() / Self.radius,
                     (Double(c.redComponent), Double(c.greenComponent), Double(c.blueComponent)))
            }
        }
    }

    /// Area (pt²) of the 0.55–0.95 radius band where every channel is ≥ 0.6.
    /// The window reflection lives in this band; plasma and comets do not
    /// reach this brightness there.
    private func reflectionArea(_ bitmap: NSBitmapImageRep) -> Double {
        let scale = Double(bitmap.pixelsWide) / Self.width
        var count = 0
        forEachPixel(bitmap) { _, _, rho, rgb in
            if rho >= 0.55, rho <= 0.95, min(rgb.0, rgb.1, rgb.2) >= 0.6 { count += 1 }
        }
        return Double(count) / (scale * scale)
    }

    // MARK: - Geometry (pure)

    func testMirrorPointIsTheHalfVector() {
        let straight = CrystalGlassRig.mirrorPoint(SIMD3<Double>(0, 0, 1))
        XCTAssertEqual(Double(straight.x), 0, accuracy: 1e-12)
        XCTAssertEqual(Double(straight.y), 0, accuracy: 1e-12)
        let side = CrystalGlassRig.mirrorPoint(SIMD3<Double>(1, 0, 0))
        XCTAssertEqual(Double(side.x), 1 / 2.0.squareRoot(), accuracy: 1e-12)
        XCTAssertEqual(Double(side.y), 0, accuracy: 1e-12)
    }

    func testTheKeyWindowSitsUpperLeftNearTheRim() {
        let panes = CrystalGlassRig.keyPanes
        XCTAssertEqual(panes.count, 2)
        XCTAssertEqual(Double(panes[0].mid.x), -0.5635384769511677, accuracy: 1e-9)
        XCTAssertEqual(Double(panes[0].mid.y), -0.5472685979705555, accuracy: 1e-9)
        XCTAssertEqual(Double(panes[1].mid.x), -0.509180915952978, accuracy: 1e-9)
        XCTAssertEqual(Double(panes[1].mid.y), -0.46948308141197354, accuracy: 1e-9)
        for pane in panes {
            XCTAssertEqual(pane.points.count, CrystalGlassRig.outlineSamples)
            for point in pane.points {
                XCTAssertLessThan(point.x, 0, "the key window must stay left of center")
                XCTAssertLessThan(point.y, 0, "the key window must stay above center")
                let rho = Double(hypot(point.x, point.y))
                XCTAssertGreaterThan(rho, 0.64); XCTAssertLessThan(rho, 0.83)
            }
        }
        XCTAssertEqual(Double(CrystalGlassRig.strip.mid.x), 0.684478514101287, accuracy: 1e-9)
        XCTAssertEqual(Double(CrystalGlassRig.strip.mid.y), 0.4277990713133043, accuracy: 1e-9)
    }

    func testFresnelStopsFollowSchlickForGlass() {
        let stops = CrystalGlassRig.fresnelStops
        XCTAssertEqual(stops.count, 16)
        XCTAssertEqual(stops.first!.location, 0); XCTAssertEqual(stops.first!.reflectance, 0.04, accuracy: 1e-12)
        XCTAssertEqual(stops.last!.location, 1); XCTAssertEqual(stops.last!.reflectance, 1.0, accuracy: 1e-12)
        XCTAssertEqual(CrystalGlassRig.schlick(0.992), 0.5289194569651289, accuracy: 1e-9)
        for (a, b) in zip(stops, stops.dropFirst()) {
            XCTAssertLessThan(a.location, b.location)
            XCTAssertLessThanOrEqual(a.reflectance, b.reflectance)
        }
    }

    func testTheShellDefaultsToCrystal() {
        // The test process has neither JARVIS_ORB_CRYSTAL in its environment
        // nor the key in its own defaults domain (not com.mortimer.host).
        XCTAssertEqual(OrbShell.resolved, .crystal)
    }

    // MARK: - Rendering

    /// The defect this plan fixes, stated as a test: the legacy glass all but
    /// vanishes in standby; the crystal glass keeps its window reflection.
    func testCrystalKeepsItsReflectionsInStandby() throws {
        let legacy = reflectionArea(try render(.offline, shell: .legacy))
        let crystal = reflectionArea(try render(.offline, shell: .crystal))
        XCTAssertEqual(legacy, 0, "legacy standby had no bright reflection in the preview")
        XCTAssertGreaterThanOrEqual(crystal, 35, "half of the preview's 70 pt² window reflection")
    }

    /// Reflections belong to the room, not to the voice state.
    func testCrystalReflectionsDoNotFollowVoiceState() throws {
        let standby = reflectionArea(try render(.offline, shell: .crystal))
        let cases: [(VoicePresentationState.Activity, Double, Double)] = [
            (.listening, 0, 0), (.user, 0.385, 0), (.assistant, 0, 0.294), (.user, 0.385, 0.294),
        ]
        for (activity, user, output) in cases {
            let area = reflectionArea(try render(activity, userEnergy: user, outputEnergy: output, shell: .crystal))
            XCTAssertEqual(area, standby, accuracy: standby * 0.15,
                           "\(activity) changed the reflection area (\(area) vs standby \(standby) pt²)")
        }
    }

    /// Plasma, comets and colors are outside the plan's scope. Beyond
    /// 1.25 × radius only the comets draw, so both shells must match there
    /// pixel for pixel, and the nucleus must keep its color.
    func testCometsAndNucleusAreUnchanged() throws {
        let cases: [(VoicePresentationState.Activity, Double, Double)] = [
            (.listening, 0, 0), (.user, 0.385, 0), (.assistant, 0, 0.294), (.user, 0.385, 0.294),
        ]
        let directory = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
            .appendingPathComponent(".build/interface-fixtures")
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        for (activity, user, output) in cases {
            let legacy = try render(activity, userEnergy: user, outputEnergy: output, shell: .legacy)
            let crystal = try render(activity, userEnergy: user, outputEnergy: output, shell: .crystal)
            XCTAssertEqual(legacy.pixelsWide, crystal.pixelsWide)
            var outside = 0, differing = 0
            forEachPixel(legacy) { x, y, rho, a in
                guard rho > 1.25, let c = crystal.colorAt(x: x, y: y)?.usingColorSpace(.deviceRGB) else { return }
                outside += 1
                let d = max(abs(a.0 - Double(c.redComponent)), abs(a.1 - Double(c.greenComponent)),
                            abs(a.2 - Double(c.blueComponent)))
                if d > 2.0 / 255 { differing += 1 }
            }
            XCTAssertGreaterThan(outside, 10_000)
            XCTAssertEqual(differing, 0, "\(activity): comets changed outside the glass")
            let cx = legacy.pixelsWide / 2, cy = legacy.pixelsHigh / 2
            let a = try XCTUnwrap(legacy.colorAt(x: cx, y: cy)?.usingColorSpace(.deviceRGB))
            let b = try XCTUnwrap(crystal.colorAt(x: cx, y: cy)?.usingColorSpace(.deviceRGB))
            XCTAssertEqual(Double(a.redComponent), Double(b.redComponent), accuracy: 0.06)
            XCTAssertEqual(Double(a.greenComponent), Double(b.greenComponent), accuracy: 0.06)
            XCTAssertEqual(Double(a.blueComponent), Double(b.blueComponent), accuracy: 0.06)
        }
        // Side-by-side fixtures for Larry's visual acceptance (§7 step V).
        let names: [(String, VoicePresentationState.Activity, Double, Double)] = [
            ("standby", .offline, 0, 0), ("idle", .listening, 0, 0), ("user", .user, 0.385, 0),
            ("mortimer", .assistant, 0, 0.294), ("overlap", .user, 0.385, 0.294),
        ]
        for (name, activity, user, output) in names {
            for shell in [OrbShell.legacy, .crystal] {
                let bitmap = try render(activity, userEnergy: user, outputEnergy: output, shell: shell)
                try XCTUnwrap(bitmap.representation(using: .png, properties: [:]))
                    .write(to: directory.appendingPathComponent("orb-\(shell == .crystal ? "crystal" : "legacy")-\(name).png"))
            }
        }
    }
}
```

## Appendix F — `MHT/OrbShellFrameTimeTests.swift` (new file)

```swift
import XCTest
import AppKit
import SwiftUI
import QuartzCore
import Observation
@testable import MortimerHost

/// docs/plans/MORTIMER_ORB_CRYSTAL_GLASS_PLAN.md D6. Measures the crystal
/// shell against the legacy shell and an empty canvas with the per-frame span
/// MemoryGraphFrameTimeTests uses: from the state change until the render
/// server runs the completion block of the Core Animation transaction that
/// carried it. Canvas 1440 × 220 pt, the widest the conversation layout gives
/// the voice region (AdaptiveStageView conversation mode: maxHeight 220 at
/// full workspace width). Blurred layers can be as large as the canvas, so
/// the widest canvas is the one to measure.
/// Writes orb-frame-time.json into .build/interface-fixtures/ under the test
/// process's working directory, next to VoiceWaveRenderingTests' fixtures.
/// Gates: legacy p50 > 1.10 × empty p50 (the span sees drawing cost);
/// crystal p95 ≤ 16.7 ms (one 60 Hz frame); crystal p50 ≤ 1.5 × legacy p50.
/// Needs a logged-in graphical session, like MemoryGraphFrameTimeTests.
@MainActor
final class OrbShellFrameTimeTests: XCTestCase {
    @MainActor @Observable
    final class PhaseModel {
        var phase = 0.0
    }

    enum Probe {
        case empty
        case shell(OrbShell)
    }

    struct ProbeView: View {
        let model: PhaseModel
        let probe: Probe
        var body: some View {
            // Read in body so each phase change re-renders the Canvas.
            let phase = model.phase
            Canvas { context, size in
                guard case .shell(let shell) = probe else { return }
                CometOrbRenderer.draw(context: &context, size: size, stageCenterX: nil, phase: phase,
                                      userEnergy: 0.2, outputEnergy: 0.35, activity: .assistant,
                                      shell: shell)
            }
            .background(Color.black)
        }
    }

    @MainActor
    private final class Harness {
        static let size = CGSize(width: 1440, height: 220)
        final class Presented { var at: Double? }
        let model: PhaseModel
        let window: NSWindow
        var completions = 0

        init(probe: Probe) {
            let model = PhaseModel()
            let hosted = NSHostingView(rootView: ProbeView(model: model, probe: probe)
                .frame(width: Harness.size.width, height: Harness.size.height))
            hosted.frame = NSRect(origin: .zero, size: Harness.size)
            let window = NSWindow(contentRect: hosted.frame, styleMask: [.borderless],
                                  backing: .buffered, defer: false)
            window.isReleasedWhenClosed = false
            window.contentView = hosted
            window.orderFrontRegardless()
            RunLoop.main.run(until: Date().addingTimeInterval(0.3))
            self.model = model
            self.window = window
        }

        func close() { window.close() }

        /// One frame: phase change → render server completion, in ms.
        func step(_ phase: Double) -> Double {
            let mark = Presented()
            let start = CACurrentMediaTime()
            CATransaction.begin()
            CATransaction.setCompletionBlock { mark.at = CACurrentMediaTime() }
            model.phase = phase
            RunLoop.main.run(mode: .default, before: Date(timeIntervalSinceNow: 0.0005))
            CATransaction.commit()
            CATransaction.flush()
            let deadline = Date(timeIntervalSinceNow: 0.5)
            while mark.at == nil, Date() < deadline {
                RunLoop.main.run(mode: .default, before: Date(timeIntervalSinceNow: 0.0005))
            }
            if mark.at != nil { completions += 1 }
            return ((mark.at ?? CACurrentMediaTime()) - start) * 1000
        }

        /// 10 warm-up frames (not recorded), then `frames` recorded frames,
        /// advancing 0.025 rad per frame (1.5 rad/s at 60 Hz, the fastest
        /// AtomMotion travels).
        func run(frames: Int) -> [Double] {
            for index in 0..<10 { _ = step(Double(index) * 0.025) }
            return (0..<frames).map { step(0.25 + Double($0) * 0.025) }
        }
    }

    private func percentile(_ values: [Double], _ p: Double) -> Double {
        let s = values.sorted()
        return s[min(s.count - 1, max(0, Int((Double(s.count) * p).rounded(.up)) - 1))]
    }

    private func ms(_ value: Double) -> Double { (value * 1000).rounded() / 1000 }

    // Synchronous on purpose, as in MemoryGraphFrameTimeTests: Core
    // Animation completion blocks must drain on the main run loop.
    func testCrystalShellStaysWithinTheFrameBudget() throws {
        _ = NSApplication.shared
        func measure(_ probe: Probe) -> (frames: [Double], completions: Int) {
            let harness = Harness(probe: probe)
            defer { harness.close() }
            let frames = harness.run(frames: 300)
            return (frames, harness.completions)
        }
        let empty = measure(.empty)
        let legacy = measure(.shell(.legacy))
        let crystal = measure(.shell(.crystal))
        for (name, result) in [("empty", empty), ("legacy", legacy), ("crystal", crystal)] {
            XCTAssertEqual(result.completions, 310, "\(name): every frame must reach the render server")
        }
        func summary(_ frames: [Double]) -> [String: Double] {
            ["p50_ms": ms(percentile(frames, 0.5)), "p95_ms": ms(percentile(frames, 0.95)),
             "max_ms": ms(frames.max() ?? 0)]
        }
        let emptyP50 = percentile(empty.frames, 0.5)
        let legacyP50 = percentile(legacy.frames, 0.5)
        let crystalP50 = percentile(crystal.frames, 0.5)
        let crystalP95 = percentile(crystal.frames, 0.95)
        let record: [String: Any] = [
            "gates": [
                "sensitivity": ["rule": "legacy p50 > 1.10 × empty p50", "passed": legacyP50 > emptyP50 * 1.10],
                "budget": ["rule": "crystal p95 ≤ 16.7 ms", "passed": crystalP95 <= 16.7],
                "relative": ["rule": "crystal p50 ≤ 1.5 × legacy p50", "passed": crystalP50 <= legacyP50 * 1.5],
            ],
            "empty": summary(empty.frames), "legacy": summary(legacy.frames), "crystal": summary(crystal.frames),
            "frames_per_probe": 300,
            "canvas_pt": ["width": Double(Harness.size.width), "height": Double(Harness.size.height)],
            "state": ["activity": "assistant", "user_energy": 0.2, "output_energy": 0.35, "phase_step_rad": 0.025],
            "hardware": ["model": sysctl("hw.model"), "cpu": sysctl("machdep.cpu.brand_string"),
                         "os": ProcessInfo.processInfo.operatingSystemVersionString,
                         "main_screen_scale": Double(NSScreen.main?.backingScaleFactor ?? 0)],
            "recorded_at": ISO8601DateFormatter().string(from: Date()),
            "test": "OrbShellFrameTimeTests.testCrystalShellStaysWithinTheFrameBudget",
        ]
        let directory = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
            .appendingPathComponent(".build/interface-fixtures")
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        try JSONSerialization.data(withJSONObject: record, options: [.prettyPrinted, .sortedKeys])
            .write(to: directory.appendingPathComponent("orb-frame-time.json"))
        print("Orb frame time p50/p95: empty \(ms(emptyP50))/\(ms(percentile(empty.frames, 0.95))), legacy \(ms(legacyP50))/\(ms(percentile(legacy.frames, 0.95))), crystal \(ms(crystalP50))/\(ms(crystalP95)) ms")

        XCTAssertGreaterThan(legacyP50, emptyP50 * 1.10,
            "the span does not respond to drawing cost (legacy p50 \(legacyP50) vs empty \(emptyP50) ms)")
        XCTAssertLessThanOrEqual(crystalP95, 16.7, "crystal p95 \(crystalP95) ms exceeds one 60 Hz frame")
        XCTAssertLessThanOrEqual(crystalP50, legacyP50 * 1.5,
            "crystal p50 \(crystalP50) ms is more than 1.5 × legacy p50 \(legacyP50) ms")
    }

    private func sysctl(_ name: String) -> String {
        var size = 0
        guard sysctlbyname(name, nil, &size, nil, 0) == 0, size > 0 else { return "unknown" }
        var buffer = [CChar](repeating: 0, count: size)
        guard sysctlbyname(name, &buffer, &size, nil, 0) == 0 else { return "unknown" }
        return String(cString: buffer)
    }
}
```

## Appendix G — Documentation text

**G.1** — amendment paragraph for `docs/plans/MORTIMER_ADAPTIVE_INTERFACE_PLAN.md`:

```markdown
**September 23 visual amendment:** the atom's glass shell is replaced by
option A ("Crystal") from the orb glass comparison: a clear, thick-walled
globe with a Fresnel-weighted room reflection, a two-pane window and rim
strip placed by mirror-sphere geometry, a caustic and a faint rim
dispersion. Reflections no longer fade with voice strength, so the glass
stays visible in standby. Plasma, comets, colors, measured-level behavior
and Reduce Motion are unchanged. `JARVIS_ORB_CRYSTAL=off` restores the
previous shell without a rebuild. Plan:
`docs/plans/MORTIMER_ORB_CRYSTAL_GLASS_PLAN.md`; receipt:
`docs/acceptance/adaptive-interface/receipts/orb-crystal-glass-<date>.md`.
```

**G.2** — receipt template (`docs/acceptance/adaptive-interface/receipts/orb-crystal-glass-<YYYY-MM-DD>.md`):

```markdown
# Orb crystal glass — <YYYY-MM-DD>

Plan: `docs/plans/MORTIMER_ORB_CRYSTAL_GLASS_PLAN.md` (rev 1). Commit: <sha>.
Hardware: <model / chip / macOS> (from orb-frame-time.json).

## Tests
- OrbShellFlagTests: <n> executed, <n> failures
- CrystalOrbShellTests: <n> executed, <n> failures
- VoiceWaveRenderingTests: <n> executed, <n> failures
- WindowVisibilityTests: <n> executed, <n> failures
- Full JarvisKit / MortimerHost suites: <n>/<n> executed, failures identical to main at a1ca3c8: <yes/no + list>
- DEVIATIONS.md entries added: <none / D-0xx>

## Frame time (orb-frame-time.json)
- empty p50/p95: <> ms; legacy p50/p95: <> ms; crystal p50/p95: <> ms
- gates: sensitivity <pass/fail>, budget <pass/fail>, relative <pass/fail>

## Visual acceptance (Larry)
- Fixtures vs docs/interface-research/orb-crystal references, five states: <accepted / notes>

## Live check (Larry)
- States (listening, user, Mortimer, overlap, standby): <>
- Placements (conversation, rail, bottom): <>
- Reduce Motion: <>
- Rollback on / off via defaults: <>
```
