---
date: 2026-11-12
system: codex
rows: [WS-35]
prs: [335]
---

# PR #335: progress moved out of the shared plan

Larry requested this bounded migration under the daily batch rule recorded in #359. The closure plan progress section now matches the PR base next at cb3b6b13681b6822f49f2c602ee2f8e10fb34ee3; its non-progress content and all other existing files are unchanged. Source head before this update: 073c5ac039a03450c40323d478d48850857663b0. No review, merge, deployment or acceptance gate is changed. Claude folds eligible merged progress into the daily status batch; existing next actors remain as recorded below.

## Preserved progress text

- 2026-11-11: #328 merged (`b2fbb2d`), giving the flaky deadline test headroom; #325 to #327 and #329 (docs) followed. Claude recorded `5777e98cf1cdbaa65eb13079044693794c071927` as the freeze SHA in WS-17's combined-source review claim on Larry's 01:58:16 direction and cut `next` from it (item A2).
- 2026-11-11: Larry approved the orb (03:07 UTC, "Looks right"); its spec and the mockups page are now in `docs/interface-research/orb-plasma/`. Claude rechecked the four orb-dependent items against it. (1) C1a still keeps `OrbFieldView`'s compact mode until C6, and C6 must move its pending-draft signal (`OrbFieldView.swift:289`) to the `#FFD84A` needs-you ring before removing it. (2) The C0b/C2 tokens match the spec unchanged; the muted arc grey `#5A6478` and the white core stay renderer constants, not theme tokens, and changing the idle `#7C8CFF` and the two nucleus tests needs Larry's OK (spec, Gates). (3) C6's tap versus Space rule is now settled by the spec (tap toggles, 350 ms hold is push-to-talk on the `pttOwned` guard); the C6 row says so. (4) C9's shared package still holds: the spec keeps `CrystalGlassRig.swift` and changes only `CometOrbRenderer.swift`, the same two files, and its arc-width floor is what keeps arcs visible at phone size. For the orb's own depth (his 03:12 question) Larry picked refraction plus option 1's contact shadow and cast light (03:18:31 "I think the third", 03:19:59 "I actually like the third but add the shadow from the first"). This adds to C6: a `layerEffect` Metal shader on the rail behind the orb, the app's first, and frame-time probes before the rest of the orb. The tilt-parallax fallback needs Larry's OK.

- 2026-11-11 (Codex, WS-35): independently reviewed C0/C0b #332 at `1f8aca7`; three contract clarifications requested (fallback revision identity, direct-result completion, legacy transcript-to-result route). Verdict: `docs/roadmap-log/2026-11-11-ws35-c0-contract-review.md`. Larry approved the starter-prompt claim exception and review publication. C10 steps next; no code or live acceptance performed.
- 2026-11-11 (Codex, WS-35 C10): baseline instructions ready at `docs/acceptance/ws35-c10-freeze-performance-baseline.md`; commands/output paths checked against freeze sources. Measurements not run. Larry captures the verified freeze baseline before C1a merges; Kimi reviews the instructions. #334 carries the separate C0/C0b review.

- 2026-11-12 (Codex, WS-35 C10, #335): Larry requested reviewer-ready draft promotion. Exact prior head `745b76b649dea9b08cb39f8a518d8c44d11c2579` had green hosted workflows and no merge conflict. This handoff changes documentation only; source and prior test evidence are unchanged. Kimi reviews the instructions; Larry captures the freeze baseline before #337 merges. Reviewer-ready is not approval to merge or live acceptance.
