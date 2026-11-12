---
date: 2026-11-12
system: codex
rows: [WS-35]
prs: [338]
---

# PR #338: progress moved out of the shared plan

Larry requested this bounded migration under the daily batch rule recorded in #359. The closure plan progress section now matches the PR base next at cb3b6b13681b6822f49f2c602ee2f8e10fb34ee3; its non-progress content and all other existing files are unchanged. Source head before this update: e4ef1196c7db5ac4677bb41bf957e615f08cf9fa. No review, merge, deployment or acceptance gate is changed. Claude folds eligible merged progress into the daily status batch; existing next actors remain as recorded below.

## Preserved progress text

- 2026-11-11: #328 merged (`b2fbb2d`), giving the flaky deadline test headroom; #325 to #327 and #329 (docs) followed. Claude recorded `5777e98cf1cdbaa65eb13079044693794c071927` as the freeze SHA in WS-17's combined-source review claim on Larry's 01:58:16 direction and cut `next` from it (item A2).
- 2026-11-11: Larry approved the orb (03:07 UTC, "Looks right"); its spec and the mockups page are now in `docs/interface-research/orb-plasma/`. Claude rechecked the four orb-dependent items against it. (1) C1a still keeps `OrbFieldView`'s compact mode until C6, and C6 must move its pending-draft signal (`OrbFieldView.swift:289`) to the `#FFD84A` needs-you ring before removing it. (2) The C0b/C2 tokens match the spec unchanged; the muted arc grey `#5A6478` and the white core stay renderer constants, not theme tokens, and changing the idle `#7C8CFF` and the two nucleus tests needs Larry's OK (spec, Gates). (3) C6's tap versus Space rule is now settled by the spec (tap toggles, 350 ms hold is push-to-talk on the `pttOwned` guard); the C6 row says so. (4) C9's shared package still holds: the spec keeps `CrystalGlassRig.swift` and changes only `CometOrbRenderer.swift`, the same two files, and its arc-width floor is what keeps arcs visible at phone size. For the orb's own depth (his 03:12 question) Larry picked refraction plus option 1's contact shadow and cast light (03:18:31 "I think the third", 03:19:59 "I actually like the third but add the shadow from the first"). This adds to C6: a `layerEffect` Metal shader on the rail behind the orb, the app's first, and frame-time probes before the rest of the orb. The tilt-parallax fallback needs Larry's OK.

- 2026-11-11 (Codex, WS-35): independently reviewed C0/C0b #332 at `1f8aca7`; three contract clarifications requested (fallback revision identity, direct-result completion, legacy transcript-to-result route). Verdict: `docs/roadmap-log/2026-11-11-ws35-c0-contract-review.md`. Larry approved the starter-prompt claim exception and review publication. C10 steps next; no code or live acceptance performed.
- 2026-11-11 (Codex, WS-35 C10): baseline instructions ready at `docs/acceptance/ws35-c10-freeze-performance-baseline.md`; commands/output paths checked against freeze sources. Measurements not run. Larry captures the verified freeze baseline before C1a merges; Kimi reviews the instructions. #334 carries the separate C0/C0b review.

- 2026-11-11 (Codex, WS-35 B1): added full JarvisKit, MortimerHost and MortimerPhoneCore `swift test` jobs as an independent matrix in `validate.yml`, preserving A1 triggers and all existing jobs. Corrected the incompatible macOS 15 runner proposal to the officially listed `macos-26-intel`, retaining Xcode 26.3 via `DEVELOPER_DIR`, without installing tools or lowering deployment targets. Static validation and nine policy tests pass; local Swift suites were not rerun while other lane tests were active. Hosted execution, named reviews and acceptance remain pending. Evidence and runner sources: `docs/roadmap-log/2026-11-11-ws35-b1-swift-ci.md`.

- 2026-11-11 (Codex, WS-35 B1): the Host matrix leg builds the existing offline owner and supplies preinstalled Python 3.12 plus repository/owner paths, avoiding the unchanged-tree missing-fixture failure without importing F1. No toolchain or Python dependency installation is added. PhoneCore retains its existing explicit process-fixture skip; hosted results must disclose that and any GUI/environment skips.

- 2026-11-12 (Codex, WS-35 B1, #338): first hosted Xcode 26.3 / Swift 6.2.4 Host build failed type checking the Skills workspace modifier chain. Larry approved splitting that expression into behavior-preserving helpers and rerunning hosted checks. Four opaque-return helpers preserve the exact ordered expression; no toolchain, workflow, test, model or deployment change. Hosted verification of the repair remains pending.

- 2026-11-12 (Codex, WS-35 B1, #338): hosted run 43240213503 compiled repaired head `3c85fcb` on Swift 6.2.4 and ran 618 Host tests (three skipped), exposing 16 assertions across seven OCR, rendering/performance, image-cancellation and visibility tests. JarvisKit and PhoneCore passed. No tests weakened; B1 stays blocked and #338 draft pending a separately scoped follow-up. Exact evidence is in the existing B1 log.
