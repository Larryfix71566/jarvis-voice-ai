---
date: 2026-11-19
system: claude
rows: [WS-37]
prs: [TBD]
---

# 2026-11-19: WS-37 carousel cards in the orb's glass, follow glow, swipe (Claude)

- **System:** Claude (Claude Code cloud session). Options designed by a Fable 5.2 helper; planned and integrated by the Opus 5.5 thread; two slices implemented in parallel by Sonnet helpers.
- **Larry's words (UTC, Claude Duet channel), 2026-11-19:**
  - 02:53:54 "caracel is there but the open pane doesn't look anything like a piece of glass. I would expect it to look more like the orb"
  - 02:54:53 "would also like to be able to swipe on the caracel to move to another item"
  - 03:08:01 "I like option B but I would like the rim to glow when I am over it with the mouse, thoughts?"
  - 03:08:32 "follow glow I think"
  - 03:11:35 "2 I think we already answered this with the latest updates to the caracel" (interface cleanup plan open decision 2: neighbours stay visible beside the front card, unlit and tilted back)
  - 03:12:45 "I like the follow glow implementation"
- **Mockup he picked from:** Claude Duet project files `mortimer/carousel-glass-2026-11-19/carousel-glass.html` (Option B, plasma-lit crystal; hover glow "Follow").
- **Change (paths under `macos/MortimerHost/Sources/MortimerHost/`):**
  - **Orb glass card.** New `Display/OrbGlassCard.swift`: `.orbGlassCard(lit:glowColor:glowSuppressed:)` keeps the system `.glassEffect(.regular)` underneath with a thinner ink tint (44%, was 58%) and adds the orb rig as static layers: edge absorption, Fresnel top edge and sky wash, two-pane key-light sheen upper left, plasma wall glow in the orb's current colour lower right, caustic, inner wall line with its highlight, cool/warm dispersion at the lit corner, and a key-light rim. One specular sweep when a card arrives (none under Reduce Motion). `OrbGlassCardPolicy` decides lit crystal, unlit crystal or the existing opaque surface; Reduce Transparency, Increase Contrast and the glass-off flag keep exactly today's opaque appearance.
  - **Follow glow.** The front card's rim brightens nearest the pointer and tracks it (`onContinuousHover` into an `@Observable` `RimGlowPointer`; only the glow overlay reads it, so card content does not re-render on pointer moves). 180 ms fade in and out, colour = `CometOrbRenderer.stateColor` of the live voice activity, off on neighbours and while dragging. Reduce Motion: an even static rim at half strength, no tracking. No Metal.
  - **Neighbours peeking.** Side cards use the unlit crystal, content at 70%, scale 0.94, tilted 9° toward the centre.
  - **Swipe.** New `Display/CarouselSwipe.swift` (pure maths) and `Display/ScrollSwipeCatcher.swift`. Click-drag (`DragGesture`, 8 pt minimum, horizontal-dominant) and two-finger trackpad scroll (a local `scrollWheel` monitor active only for events over the carousel, claiming a gesture only when horizontal dominates over the first 12 pt) move the cards with the finger, rubber-band at the ends (at most 18% of the width) and commit one card past 28% of the width or a 500 pt/s flick. Trackpad momentum after a commit is swallowed; the card follows the fingers whatever the natural-scrolling setting; a horizontal mouse wheel steps one card per tick with a 0.35 s cooldown. Under the flat presentation the card does not follow, only the commit applies. Keyboard paths are unchanged; VoiceOver gets an adjustable action (swipe up/down) on the front card.
  - `Console/AdaptiveStageView.swift`: the two `ResultCarouselView` call sites pass the live voice activity for the glow colour. Nothing else in that file.
- **Tests (new):** `OrbGlassCardTests` (8: policy tables, glow focus geometry, constants, layout lit and flat at two widths), `CarouselSwipeTests` (13: offset, rubber band, thresholds, flick, ends, trackpad claim/ignore, momentum, cancel, trackpad flick by velocity, mouse wheel), `CarouselGlassFrameTimeTests` (Mac only, skipped on hosted runners: every frame redraws the card; gate is follow-glow card p50 and p95 within 10% of today's `.mortimerGlass(.card)`, the C6 margin; writes `.build/interface-fixtures/carousel-glass-frame-time.json`).
- **Frame time:** the orb's C6 test (`OrbShellFrameTimeTests`) renders only the orb, so this change cannot move it; the new card test is the comparable check and has not been run yet. If it fails on the Mac, fall back to the whole-rim glow from the mockup.
- **Not tested here:** no Swift toolchain in the session; nothing compiled or run locally. CI's Swift jobs are the first build. Nothing seen on the Mac.
- **Decision recorded:** interface cleanup plan open decision 2 (carousel neighbours) answered by Larry: neighbours stay visible, unlit and tilted. For the daily batch to fold into the plan.
- **Next actor:** CI, then Larry: merge, redeploy next, run `swift test --package-path macos/MortimerHost --filter CarouselGlassFrameTimeTests` on the Mac, look at the carousel.
