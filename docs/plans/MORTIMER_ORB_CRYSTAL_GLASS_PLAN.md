# Mortimer orb crystal glass plan — crystal shell only

**Status:** ACCEPTED BY LARRY 2026-09-30 — PR #112 merged as `e9388fc` and is included in deployed release `c3607e6` and later production `03b9e60`. Larry explicitly confirmed WS-08 tested and accepted. Individual fixture/state/placement observations were not separately itemized; the overall human acceptance closes the remaining visual/live gate. The former protected-window capture failure was fixed under WS-16 and passed DEPLOY-MAIN.
**Recorded:** 2026-09-30.
**Original 2026-09-24 receipt:** `docs/acceptance/adaptive-interface/receipts/orb-crystal-glass-2026-09-24.md`.

### Revision 2 — crystal is the only orb shell (Larry, 2026-09-29)

Larry directed that the crystal orb be the sole implementation. Remove the old
orb-shell drawing branch, its `JARVIS_ORB_CRYSTAL` environment/UserDefaults
rollback flag, and tests that instantiate the old shell. The app must always
render the crystal shell; do not retain a hidden legacy fallback. This applies
to the atom orb only: the separate Silo wave in legacy layout 0 remains outside
this plan's scope. Keep the approved crystal design, colors, geometry, motion,
accessibility behavior, and frame-time budget unchanged. Existing static
research images may remain as historical references; they are not runtime
alternatives.

This amendment supersedes earlier D2/D3 rollback instructions, legacy-vs-crystal
comparisons in tests, the legacy-relative frame-time gate, and the rollback part
of step 9. Keep the empty-canvas sensitivity and 16.7 ms crystal p95 budget.
The implementation removes the flag test because the source structure makes
the crystal path unconditional; do not add a runtime shell selector. No change
to art constants is authorized.

Larry's 2026-09-29 live observations on the deployed crystal build: compact and
expanded layouts both displayed the orb correctly; Reduce Motion left the orb
visible and stopped its movement. These are reported acceptance checks and must
be recorded as user-observed, not as automated or independently observed facts.
After the single-shell change is deployed, Larry rechecks those two behaviors;
there is no rollback-to-old-shell check.
**Design owner:** Larry. **Implementation:** Codex under WS-08 on the branch named in `ROADMAP.md`; commit and PR follow `AGENTS.md`. Larry merges and deploys. The implementer does not modify production, install the app, or change `defaults`.
**Approved design:** option A ("Crystal") from the orb glass comparison, chosen by Larry on 2026-09-23. The comparison page is the Claude artifact https://claude.ai/artifact/852XZZzAqkt5WmHUe6ruGY. A copy of it and reference renders are checked in under `docs/interface-research/orb-crystal/`.
**Baseline inspected:** `origin/main` at `0cc42f2` before the WS-08 implementation branch was created; the claim merge is the branch parent.
**Safety claim:** the adaptive interface plan's contracts UI-1 through UI-7 (`docs/plans/MORTIMER_ADAPTIVE_INTERFACE_PLAN.md` §3) stay in force word for word. This plan adds no contract and relaxes none. It changes pixels inside the orb's glass and nothing else.

Path shorthand: `MH/` = `macos/MortimerHost/Sources/MortimerHost/`, `JK/` = `macos/JarvisKit/Sources/JarvisKit/`, `MHT/` = `macos/MortimerHost/Tests/MortimerHostTests/`, `JKT/` = `macos/JarvisKit/Tests/JarvisKitTests/`.

| Rev | Date | Change |
|---|---|---|
| 1 | 2026-09-23 | First version. |
| 2 | 2026-09-29 | Crystal shell is the sole implementation; remove legacy shell and rollback flag at Larry's direction. |

## 0. Binding constraints for the implementing model

1. **Preserve the approved design.** Revision 2 authorizes only removing the retired shell branch/selector and updating tests and documentation to match. Do not change any crystal art, color, geometry, motion, accessibility behavior or performance threshold.
2. **Branch.** Work only on the WS-08 branch recorded in `ROADMAP.md`. Reconcile a different branch or unexpected base before editing.
3. **Design.** Preserve the approved crystal artwork and all motion, accessibility and performance thresholds. The crystal renderer is the only atom-orb renderer; do not add a shell selector or fallback.
4. **Tests.** Update only tests that directly assert the retired shell, and delete the obsolete flag test. Do not skip or loosen other tests (UI-7). Report every full-suite failure with its exact name and output. Do not tune a threshold or design constant to make a test pass.
5. **Scope.** Touch only the files in §4, plus the roadmap and acceptance/plan documentation required to report status. Nothing under `jarvis/`, `web/`, `config/`, `scripts/`, or unrelated Swift files.
6. **Look.** Do not adjust the approved design based on the implementer's own visual judgment. Visual acceptance is Larry's, after deployment.

## 1. Background (verified against the source at `a1ca3c8`)

The orb is drawn by `CometOrbRenderer.draw` (`MH/Console/CometOrbRenderer.swift`), called only from `WaveEngine.drawAtom` (`MH/Console/VoiceWaveView.swift:475-486`) when a `VoicePresentationState` is present. That is every adaptive layout: the default Command Console (layout 2, `ConsoleView.swift:71` → `CommandConsoleView` → `AdaptiveStageView`) and layout 1 (`ConsoleView.swift:75` → `AdaptiveStageView`), in all three `AdaptiveStageView` placements: conversation (full width, 150–220 pt tall, `:95`), rail (200 × 150, `:102`) and bottom (220–280 × 180, `:114`). Layout 0 (`ConsoleView.swift:57`) draws the legacy Silo wave without a presentation state, not the orb, and is unaffected.

`draw` has two parts. Lines 25–48 compute the shared state: center, `radius = 0.255 × extent`, `energy`, `ambient`, `ready`, `tint` by activity, `strength` (0.52 + 0.48 × energy when ready, 0.16 otherwise) and `breath`. Lines 50–103 draw the shell around two unchanged helpers, `plasma(…)` (`:106`) and `comets(…)` (`:200`). All motion comes from `phase`, which `AtomMotion` advances from elapsed time; the renderer itself reads no clock.

Why the current shell reads as light and not glass, from the code:

- The sphere fill is 2.5% → 6% opacity from the center to 65% radius (`:62-68`). There is no glass body.
- The only highlight is a disc 0.25 × radius wide, 40% peak opacity, blurred (`:93-99`).
- The rim band, the four arcs and the highlight are multiplied by `strength`, which is 0.16 in standby (`:65-66`, `:90`, `:98`). The glass nearly disappears when Mortimer is offline.
- The back half of each comet orbit is drawn first (`:52-55`) under that thin fill, so it shows through at nearly full brightness.

## 2. Scope

**In scope:** option A crystal glass as the only adaptive atom-orb renderer. Remove the former shell drawing branch and `JARVIS_ORB_CRYSTAL` toggle; update tests, plan and roadmap. Preserve the approved glass body, wall, Fresnel reflection, window and strip lights, second window reflection, caustic, rim dispersion, hairline, voice response, motion and frame-time budget.

**Unchanged, and tested where a test can see it:**

- `plasma(…)`, `comets(…)`, `AtomMotion`, `WaveEngine`, `VoicePresentationState`, `AudioPresentationTuning` (colors, gains, dB windows).
- Orb geometry: radius 0.255 × extent, comet orbits 1.53 / 1.17 × radius, tilts −0.48 / +0.56.
- Nucleus color by talker, both channels visible during overlap, standby and Reduce Motion stillness, "audio unavailable" stillness.
- Accessibility label and value (`VoiceWaveView.swift:28-29`), window-visibility sampling, wake flash, Debug ▸ Wave level windows.
- `OrbFieldView` (readout, satellites, beams, captions, notices), every drawer tab, `Glass.swift` panels, the legacy Silo wave for layout 0.

**Out of scope:** options B and C; the frozen web console (`web/src/components/OrbField.tsx`); any change to how comets or plasma look; caching reflections into bitmaps (D5); the separate Silo wave in legacy layout 0.

## 3. Decisions

**D1 — Option A exactly as previewed.** Every constant in Appendix A equals the value in the approved preview (`docs/interface-research/orb-crystal/glass-orb.html`, `STYLE.crystal`, `KEY`, `STRIP`, `FRESNEL`, `buildEnv`, `drawGlass`). *Why:* Larry chose what he saw. Changing a value, even to "improve" it, is a new design decision.

**D2 — Original revision decision (superseded by Revision 2).** Revision 1 used a shell parameter and retained legacy shell code as a rollback. Revision 2 removes that branch and makes crystal rendering unconditional; shared plasma/comet helpers and their design values remain unchanged.

**D3 — Original revision decision (superseded by Revision 2).** Revision 1 proposed `JARVIS_ORB_CRYSTAL`; Larry's Revision 2 decision removes it. Rollback for this code change is a standard source/deployment rollback only; there is no in-app shell selector.

**D4 — Light geometry is computed, not drawn by hand.** A distant light in direction *d* reflects toward the viewer where the surface normal is `normalize(d + view)`. Its screen position is that normal's x and y times the radius (`CrystalGlassRig.mirrorPoint`). The window panes and the strip are superellipse rectangles in light space, mapped point by point (96 samples). The outlines are `static let`s in unit coordinates, computed once per process and scaled each frame. *Why:* this is what makes the reflection curve with the sphere. It is also the preview's exact method, and it is pure math, so it is unit-tested.

**D5 — Draw every frame; no bitmap caching.** The reflections do not depend on voice state, so they could be cached, but they are drawn as vector fills each frame. *Why:* `CometOrbRenderer`'s own header rule is that no bitmap is substituted for voice feedback. Caching also adds size and scale invalidation to get wrong. D6 measures whether drawing every frame is affordable.

**D6 — Frame-time gate.** `OrbShellFrameTimeTests` uses the `MemoryGraphFrameTimeTests` span on a 1440 × 220 pt canvas, with 300 frames each for an empty canvas and the crystal orb. Revision 2 removes the legacy-relative comparison. The gates are:
  - **Sensitivity:** crystal p50 > 1.10 × empty p50. This proves the span sees drawing cost; the same rule is in P4.
  - **Budget:** crystal p95 ≤ 16.7 ms, one 60 Hz frame. `VoiceWaveAnimation` samples at 60 Hz while audio is active.

  If any gate fails: **stop and report the JSON** (§0 rule 4). Do not optimize. *Why:* UI2-21 requires "bounded rendering cost", and it has never been measured for the orb.

**D7 — Reflections ignore voice state; only the halo and the wall glow follow it.** The body, wall line, room reflection, caustic, window, strip, back reflection, dispersion and hairline all use fixed opacities. The halo and the wall glow are multiplied by `strength`. *Why:* a glass object keeps its reflections when the light inside goes out. This is the property the preview showed in standby, and a test pins it.

**D8 — Blur a group by filtering the layer, not its contents.** Each blurred group is drawn as `var copy = context; copy.addFilter(.blur(radius:)); copy.drawLayer { … }`. *Why:* Apple's documentation for `addFilter` says a filter "applies to subsequent drawing operations", and each one is rasterized, filtered and composited on its own. A `drawLayer` call is one operation, so this blurs the group as a whole, as in the preview.

**D9 — The Fresnel layer's 0.62 opacity is multiplied into its gradient.** It is not set as a layer opacity. *Why:* under `.destinationIn` the result alpha is sky alpha × Fresnel alpha, so multiplying the sky alpha by 0.62 gives an identical result. It also avoids depending on how `drawLayer` treats `GraphicsContext.opacity`, which Apple's documentation does not state.

**D10 — The reflections are one screened layer.** The whole room reflection is drawn inside one `drawLayer` on a context copy whose `blendMode` is `.screen`, matching the preview's single screened canvas. The wall glow uses `.plusLighter`, the preview's `lighter`.

**D11 — Reference images are checked in.** Reference PNGs rendered by the preview go under `docs/interface-research/orb-crystal/`. They are the look Larry approved. The new test writes the Swift renders next to its other fixtures for side-by-side comparison. *Why:* the implementer cannot open the artifact link, and "looks like the preview" needs something to compare against.

**D12 — Tests.** Existing tests remain unchanged unless they directly test the retired selector or compare against the retired renderer. `CrystalOrbShellTests` covers glass geometry/reflection visibility, speaker color and visual fixture rendering. `OrbShellFrameTimeTests` keeps the empty-canvas sensitivity and absolute 16.7 ms p95 gate. `OrbShellFlagTests` is removed because the runtime selector no longer exists. Preview-based geometry and reflection thresholds remain unchanged.

## 4. File manifest

| File | Change | Appendix |
|---|---|---|
| `MH/Console/CrystalGlassRig.swift` | remove `OrbShell`; preserve `CrystalGlassRig` constants and geometry | A |
| `MH/Console/CometOrbRenderer.swift` | remove shell parameter and old shell drawing; call crystal renderer unconditionally; preserve crystal artwork/helpers | B |
| `MH/Console/VoiceWaveView.swift` | update stale comment to describe the unconditional crystal renderer | — |
| `JK/JarvisConfig.swift` | remove `JarvisFlags.orbCrystalShellEnabled` | C |
| `JKT/OrbShellFlagTests.swift` | delete; the selector no longer exists | D |
| `MHT/CrystalOrbShellTests.swift` | update tests to exercise the sole renderer; retain geometry/reflection checks and visual fixtures | E |
| `MHT/OrbShellFrameTimeTests.swift` | compare crystal to empty canvas; retain sensitivity and 16.7 ms p95 gates | F |
| `docs/interface-research/orb-crystal/*` | **new** (already written when this plan was delivered; verify they exist) | — |
| `docs/plans/MORTIMER_ADAPTIVE_INTERFACE_PLAN.md` | edit: one amendment paragraph | G.1 |
| `docs/acceptance/adaptive-interface/receipts/orb-crystal-glass-<YYYY-MM-DD>.md` | **new**: acceptance receipt | G.2 |
| `DEVIATIONS.md` | edit only if §0 rule 3 applied | — |

`docs/interface-research/orb-crystal/` contains `glass-orb.html` (the approved comparison page; open it in a browser), `crystal-{standby,idle,user,mortimer,overlap}-400x180.png` and `current-{…}-400x180.png` (the preview's renders at the test canvas size on black), and `contact-sheet-240x180.png` (current row above crystal row, on the app's `#15191D`, at the bottom-layout size).

## 5. Steps

Run everything from the repository root. A step is complete only when its check passes.

**Step 0 — Preconditions.** Use the Codex-owned WS-08 branch and worktree recorded in `ROADMAP.md`, merged with main before edits. Confirm the reference files in §4 exist. Never edit production.

**Step 1 — Remove the shell selector.** Delete `orbCrystalShellEnabled` from `JK/JarvisConfig.swift`, remove `OrbShell` from `MH/Console/CrystalGlassRig.swift`, delete `JKT/OrbShellFlagTests.swift`, and remove the shell parameter and branch from `CometOrbRenderer.draw`.

**Step 2 — Rig.** Preserve `CrystalGlassRig` constants and light geometry in `MH/Console/CrystalGlassRig.swift`; remove only the `OrbShell` type and its selector documentation.

**Step 3 — Renderer.** In `MH/Console/CometOrbRenderer.swift`, remove the legacy shell's draw code and call the crystal renderer unconditionally. Keep crystal design and shared plasma/comet helpers unchanged.
Check: Swift package tests build successfully.

**Step 4 — Behavior tests.** Completed: `CrystalOrbShellTests` now checks geometry/reflections, speaker color, and five crystal-state fixtures. Focused check passed (7 tests, 0 failures); fixtures are under `macos/MortimerHost/.build/interface-fixtures/`.

**Step 5 — Existing orb tests.** These remained unchanged and ran as part of the full suite. Three `WindowVisibilityTests` cases skipped because the test host could not become active (closure plan G20).

**Step 6 — Frame time.** Completed: the legacy probe and relative gate were removed. Focused test passed sensitivity and 16.7 ms p95 gates; JSON is under `macos/MortimerHost/.build/interface-fixtures/`.

**Step 7 — Full suites.** Run `swift test --package-path macos/JarvisKit` and `swift test --package-path macos/MortimerHost`. The orb tests must pass. Report any unrelated existing failure without changing its code under this workstream; establish whether it reproduces on the unchanged base before attributing it to the orb.

**Step 8 — Visual acceptance (Larry).** Open `orb-crystal-<state>.png` from the directory step 4 found next to `docs/interface-research/orb-crystal/crystal-<state>-400x180.png` for all five states. Pass means the same features in the same places: the two-pane window upper left near the rim, the strip light and the softer second window lower right, the dark wall line, the wall glow lower right in the talker's color, and the glass still visible in standby. Canvas and SwiftUI blur and gradient rendering differ slightly, so this is not a pixel match. If Larry wants any value changed, that is a new revision of this plan, not an implementation fix.

**Step 9 — Live check (Larry, after deployment).** Run `macos/MortimerHost/scripts/bundle.sh` and connect.
- Confirm the crystal shell in Listening, while you speak, while Mortimer speaks, while both speak, and in Standby.
- Confirm it in the conversation, rail and bottom placements.
- Confirm Reduce Motion (System Settings ▸ Accessibility ▸ Display) freezes it.

There is no runtime rollback-to-old-shell check. If a release must be reverted, use the standard source/deployment rollback procedure.

**Step 10 — Documentation.** Code, automated checks and release evidence are recorded in this plan, `ROADMAP.md`, and `docs/acceptance/adaptive-interface/receipts/orb-crystal-glass-2026-09-29.md`. Larry explicitly accepted WS-08 on 2026-09-30; the receipt distinguishes that overall approval from unitemized individual observations.

Larry commits.

## 6. Where tuning values live

Every crystal-shell number is a named `static let` in `CrystalGlassRig` (Appendix A). The drawing code in Appendix B E3 contains no design numbers of its own. The only literals there are structural: gradient stop locations 0, 0.5 and 1, opacity 0 at a gradient's transparent end, `Double.pi` for the half-turn, `2` for diameters and midpoints, and `1` as the fallback length for a zero vector. A later visual change edits `CrystalGlassRig` only, and it needs Larry's approval and a plan revision (D1).

## 7. Verification

| Check | Where | Evidence |
|---|---|---|
| Light geometry equals the preview's math | `CrystalOrbShellTests.testMirrorPointIsTheHalfVector`, `testTheKeyWindowSitsUpperLeftNearTheRim`, `testFresnelStopsFollowSchlickForGlass` | test output |
| Crystal renderer stays visible in standby (the reported defect) | `testCrystalKeepsItsReflectionsInStandby`: crystal ≥ 35 pt² of bright reflection in the 0.55–0.95 radius band (preview 70) | test output |
| Reflections ignore voice state (D7) | `testCrystalReflectionsDoNotFollowVoiceState`: listening, user, Mortimer and overlap within ±15% of standby (preview: within 0.4%) | test output |
| Speaker color and visual states | `testNucleusReflectsTheCurrentSpeaker`, `testReferenceStatesRenderCrystalFixtures` | test output and five crystal PNG fixtures |
| Existing behavior | `VoiceWaveRenderingTests`, `WindowVisibilityTests`, full suites | test output |
| Cost | `OrbShellFrameTimeTests` (D6) | `orb-frame-time.json` |
| Look | Larry, step 8 | fixtures vs reference PNGs |
| Live, placements and Reduce Motion | Larry, step 9 | receipt |

## 8. Rollback

There is no runtime selector for the retired shell. Use the standard source/deployment rollback if a release must be reverted. No data, settings or server state is involved.

## 9. Risks

| Risk | Likelihood | Effect | Handling |
|---|---|---|---|
| SwiftUI blur radius or gradient interpolation differs from the browser, so the look drifts from the preview | medium | window softer or harder, glow stronger or weaker | Larry judges after deployment; changes go through a plan revision |
| SwiftUI blur radius or gradient interpolation differs from the browser, so the look drifts from the preview | medium | window softer or harder, glow stronger or weaker | thresholds at half the preview's numbers; Larry judges in step 8; changes go through a plan revision |
| `blendMode` does not apply to a `drawLayer` composite | low | reflections composite normally instead of screened; on the dark body, for near-white reflections, the difference is small | step 8 catches a visible difference; report it and do not work around it |
| Frame cost too high on the MacBook Air at full width | unknown; not yet measured | dropped frames while talking | D6 gate; stop and report |
| The frame-time span does not see drawing cost | unknown | gate would pass without meaning anything | sensitivity gate; stop and report |

## 10. Approval

- [x] Larry: plan approved for implementation (single-shell direction, 2026-09-29).
- [x] Larry: step 8 visual acceptance — overall WS-08 sign-off reported 2026-09-30; no per-fixture observations supplied.
- [x] Larry: step 9 post-deployment check — overall WS-08 sign-off reported 2026-09-30; compact/expanded and Reduce Motion were separately reported earlier, while other individual state/placement observations were not itemized.

## 11. Handoff prompt for the implementing model

> Implement the Revision 2 crystal-only cleanup on the WS-08 branch recorded in `ROADMAP.md`. Work only in the assigned worktree, never production. Remove the old atom-orb branch and `JARVIS_ORB_CRYSTAL`; preserve crystal art, separate Silo wave, motion, accessibility and performance limits. Update only tests that directly assert the retired shell and run all focused/native package suites. Report unrelated full-suite failures accurately. Leave deployment and post-deployment visual/Reduce Motion checks to Larry. Do not use `defaults` or install the app.

---

## Historical revision-1 appendices (reference only)

The following code appendices document the original crystal-shell implementation
and are retained for decision history. They contain the retired `OrbShell`
selector, legacy renderer, flag tests and relative performance comparison.
**Do not apply those appendices. Revision 2 above and the 2026-09-29 progress
record below define the current implementation.**

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


## 2026-09-28 — authorized rendering performance follow-up (WS-08)

Larry assigned the orb performance fix to Codex alongside the Skills fix after
DEPLOY-MAIN at `1ec20d6` stopped before production changes. This bounded
assignment supersedes the original one-pass "do not optimize"/stop instruction
and prior Claude ownership for this follow-up. All design constants, draw
order, blend modes, filter radii, legacy rendering and performance thresholds
remain unchanged. No bitmap cache is introduced.

The crystal path previously rebuilt the same five 96-point light paths and
96 dispersion segment paths each frame, including fixed trigonometry and
falloff calculations. It now prepares immutable unit-space vector paths and
weights once, then transforms them to the current center/radius every frame.
Animated plasma, comets, voice colors, and glass rendering are still drawn
on every frame. Resizing needs no raster invalidation.

Initial targeted verification: all nine crystal/benchmark tests pass. Orb
median: 4.989 ms crystal / 5.216 ms legacy; crystal p95 14.232 ms. Decoded
pixels for five crystal and five legacy voice-state fixtures are exactly
unchanged against `1ec20d6` at 800x360 on the same host. Evidence lives in
`docs/acceptance/skills-workspace/receipts/rendering-performance-2026-09-28/`.
Full native suite, PR CI, merge and exact-main deployment remain pending;
step 9 physical/Reduce Motion/rollback acceptance is not closed by this work.

Full native follow-up: MortimerHost 372 tests, seven environment skips, zero
failures. Skills selection-to-layout p95: 13.127 ms wide / 7.970 ms compact;
cached navigation 44.558/28.313 ms. Crystal orb p50/p95: 4.830/14.705 ms;
legacy p50 4.911 ms. All original budgets pass. The strengthened real-button
interaction test was compiled and passed separately after the full run.
Compact receipts and exact source hashes are in the rendering-performance
receipt directory above. CI/merge and exact-main deployment are still required;
production remains `0b76f49` and no live activation gates are closed.


### 2026-09-28 — staged Mac deployment completed

PR #96 merged as `539f8f6`; all GitHub workflows passed. DEPLOY-MAIN then
verified that exact commit: JarvisKit 219 tests/zero failures, MortimerHost
372 tests/seven environment skips/zero failures, Python 4,860 passes/seven
skips/two subtests passed. Release measurements: Skills selection-to-layout
p95 14.480 ms wide / 7.911 ms compact; crystal orb p50/p95 4.841/13.370 ms
versus legacy p50 4.833 ms. All original performance gates pass.

At 20:19 EDT the script backed up databases, code and the prior app, installed
and opened the production app, and restarted vault/bot/extractor/admin/costs.
Production HEAD and bundle revision both equal `539f8f6`; all six processes
were independently rechecked alive with the intended production paths.
Admin/vault returned HTTP 200; bot returned the expected 307. The deployment
receipt reports `deployed` with no problems. Database migrations through
`0036_skill_step_check_receipts` are present (0035 remains reserved).

Receipt: `docs/acceptance/skills-workspace/receipts/rendering-performance-2026-09-28/deployment-receipt.json`.
Local rollback: `~/MortimerRollback/release-539f8f6-20260928-201417/ROLLBACK.sh`.
This closes staged source deployment, not live feature acceptance or activation.
No runtime feature flags or provider routes were deliberately changed by this
operation. Remote enabled-mode acceptance, provider/VM/voice/display/accessibility
and plan-specific activation/rollback gates remain open where previously open.


## 2026-09-29 — WS-08 single-shell direction claimed

Larry confirmed that the crystal orb should be the only atom-orb shell. This revision removes the production fallback and rollback test; it does not change the crystal artwork or the separate Silo wave. Larry reports the current build passes compact/expanded appearance and Reduce Motion stillness checks. Implementation was pending the WS-08 claim merge.

## 2026-09-29 — WS-08 crystal-only implementation

Codex removed `OrbShell`, the legacy draw branch and `JARVIS_ORB_CRYSTAL`; the
crystal renderer is now unconditional. The Silo wave in layout 0, shared plasma
and comet drawing, colors, geometry, motion and accessibility are unchanged.
The tests now check approved crystal reflections and geometry, speaker-colored
nucleus, five crystal fixture states, and the unchanged empty-canvas sensitivity
plus 16.7 ms p95 performance gates. The obsolete JarvisKit flag test was removed.

Verification on Apple M5 / macOS 27.0: JarvisKit 215 tests, zero failures;
focused CrystalOrbShellTests 7/0; OrbShellFrameTimeTests 1/0 (focused p50/p95
4.933/14.150 ms; empty p50 0.842 ms). Full MortimerHost ran 374 tests, five
skips and one failure in
`ProtectedDisplayContentTests.testProtectedContentInActualWindowCaptureMatchesBodyOnlyReference` at line 134. The failure is outside WS-08's files. On unchanged base `0cc42f2`, that
window-capture test skipped because the test host could not become active; the
focused current-branch run skipped it for the same WindowServer limitation.
Thus the full-suite capture mismatch is recorded as an environment-sensitive
unrelated failure, not as a passing full suite or an orb regression.

Crystal visual fixtures and the timing JSON are under the ignored
`macos/MortimerHost/.build/interface-fixtures/`. PR/CI, Larry's source-image
comparison, merge/deployment, and post-deployment compact/expanded plus Reduce
Motion checks remain open. No production files or app settings were changed.

## 2026-09-29 — WS-08 merged and CI green

PR #112 merged to main as `e9388fc`. Its first `validate` run failed in
`tests/unit/test_admin_appbuild.py::test_submit_after_done_delegates_to_workspace`,
which is outside WS-08 and unchanged by the PR. That test passed in an isolated
local run; the full `validate` workflow passed on rerun, as did Sandbox controller
and Knowledge base. The five-fixture comparison, deployment, and Larry's
post-deployment compact/expanded and Reduce Motion checks remain open.

## 2026-09-29 — DEPLOY-MAIN stopped before production changes

Larry ran `scripts/deploy_main.sh` against `origin/main` at `d460809`.
JarvisKit passed (215/0); MortimerHost ran 374 tests with five skips and one
failure, `ProtectedDisplayContentTests.testProtectedContentInActualWindowCaptureMatchesBodyOnlyReference`
at line 134. The script stopped in phase A, so no snapshot, install or service
switch occurred. A read-only check still found production at `e340101`.
The deployment log is local at
`/Users/larryfix/MortimerRollback/logs/deploy-main-20260929-154149.log`.

The failed assertion printed both 1240 × 840 RGBA captures. They differ at
21,946 of 1,041,600 pixels (2.107%). Differences occur in the outer capture
edge and the body-text area (approximately x=24–290, y=29–57); a 64-pixel
inset contains no differences. The fixture creates and captures two separate
windows in sequence. Window composition/text-render timing is a plausible
cause, but this observation alone does not prove it. The source's protected
render path ignores the ancillary fields. The captured arrays do not show
evidence that those fields appeared, and the failed equality cannot be counted
as a privacy pass.

`ProtectedDisplayContentTests.swift` is outside WS-08's orb-specific scope.
A separately assigned repair should make the live capture deterministic while
preserving the privacy comparison, then pass the full MortimerHost suite and
DEPLOY-MAIN before deployment and orb acceptance can continue.

## 2026-09-29 — Deployment and acceptance reconciliation

WS-16 fixed the independent protected-window capture gate. Larry's DEPLOY-MAIN
then deployed `c3607e6`, which includes the WS-08 crystal-only change. The real
capture test executed and passed; MortimerHost ran 383 tests with six unrelated
skips and zero failures, JarvisKit ran 218 tests with zero failures, and Python
reported 4,924 passed and seven skipped. Main, production and app-bundle
revisions matched; services were healthy.

Larry reaffirmed in this task that compact and expanded appearance and Reduce
Motion stillness had already been confirmed. These are user-reported live
checks, not Codex-observed ones, and should not be repeated. The five fixture
PNGs left in production's `.build` directory were dated 09-24 and therefore
were not used as current-release evidence. Codex regenerated all five from the
merged source; orb product files are unchanged from deployed `c3607e6`.
`CrystalOrbShellTests` passed 7/0. The current 400 × 180 fixtures and the
approved 800 × 360 reference images show the specified glass, paired
upper-left reflection, lower-right soft reflection, dark wall, orbit paths,
nucleus and talker colors in the same relative positions. The images are
linked from the existing WS-08 receipt. This is Codex's comparison, not
Larry's final visual sign-off.

The remaining acceptance is narrow: Larry's explicit five-fixture approval
(step 8), plus evidence for any step 9 live states or placements not already
seen. No further deployment or repeat compact/expanded or Reduce Motion check
is required for this WS-08 revision.

## 2026-09-29 — Acceptance evidence landed

PR #115 merged as `8222940` after all five GitHub checks passed, including
the full `validate` job against the WS-01 action-claim fix. This lands the
five current fixture images and the corrected acceptance receipt. It does not
turn Larry's pending five-fixture approval or unobserved live states and
placements into passed checks.

## 2026-09-30 — Larry's final acceptance

Larry explicitly confirmed WS-08 tested and accepted. This overall human
sign-off closes steps 8 and 9 without claiming a separately recorded result
for every fixture, live voice state or placement. The existing receipt retains
the source, deployment, automated and visual-reference evidence. No further
WS-08 implementation, deployment or repeat acceptance test is requested.
