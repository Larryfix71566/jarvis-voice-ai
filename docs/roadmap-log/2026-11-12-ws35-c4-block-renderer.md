---
date: 2026-11-12
system: codex
rows: [WS-35]
prs: []
---

# C4 block renderer

## Main integration history

Current main daily-batch status is retained. The old next-side conflict text is preserved verbatim below so no review or claim history is lost. Non-conflicting claim/design changes were retained by the merge.

### ROADMAP.md historical next-side record

- **Status:** claimed; C0/C0b independent review recorded by this PR; C10 instructions next, then C1a. Larry approved following the starter prompt including its claim exception on 2026-11-11.
- **Implemented by:** Codex
- **Remaining work / acceptance:** Items C10 (box 810 performance baseline, before C1a), C1a (delete layouts 0 and 1), B1 (macOS Swift CI job), B5 (wider ruff, offline NLTK data), C4 (Swift block renderer), C5 (result carousel; the second screen keeps its grid, decision 4), C9 (phone orb on synthetic levels, decision 5, after moving the orb renderer to a shared package) and F1 (the `PhoneRemoteAuthorityProcessTests` failure, an acceptance fix on `main` approved by name). Each item in the plan's §4 table for this lane, as a PR into `next` with its tests, reviewed by the item's named reviewer (never its author). Interface items then pass the rewritten UI boxes in `docs/acceptance/mac-acceptance-2026-11-11.md` §4 on the final build; `next` merges into `main` at closure.
- **Model version:** not recorded
- **Where:** `codex/ws35-contract-review-20261111` into `next` (contract review); subsequent items branch from `next`, except F1 from `main`.
- **Plan:** `docs/plans/MORTIMER_RELEASE_CLOSURE_PLAN.md` §4 (WS-35) and §5; add only dated progress for this lane
- **Scope:** The files named for those items in the plan's §4 WS-35 table: `docs/acceptance/**` (C10); every MortimerHost source and test file that reads `layoutVersion` (C1a); `.github/workflows/validate.yml` (B1, B5, after A1); `macos/MortimerHost/Sources/MortimerHost/Display/**`, `App/AppMessageRouter.swift`, `macos/JarvisKit/Sources/JarvisKit/AppMessage.swift` (C4); the C5 result and carousel files; `ios/MortimerPhoneCore/**` and the shared orb package (C9). Hand-off order for shared files is the plan's §4 "Hand-off points"; overlaps with other rows are CX-29.
- **Next step:** claude: address the three findings in `docs/roadmap-log/2026-11-11-ws35-c0-contract-review.md` for #332; kimi: independent contract review; codex: C10 baseline instructions, then C1a on `next`. F1 needs Larry’s named acceptance-fix approval before merge.
- **Updated:** 11-11

### ROADMAP.md historical next-side record

- **Status:** in-progress; C0/C0b independent review landed via this PR with CHANGES REQUESTED on head `1f8aca7`; A3 is next

### ROADMAP.md historical next-side record

- **Next step:** claude: correct the C0/C0b findings for independent re-review. kimi: A3 combined-source review; F1 review when Codex publishes it; C2 after the corrected C0b.
- **Updated:** 11-11

### docs/plans/MORTIMER_RELEASE_CLOSURE_PLAN.md historical next-side record

- 2026-11-11: Kimi's independent WS-36 review of C0/C0b PR #332 at `1f8aca7` is CHANGES REQUESTED (`docs/roadmap-log/2026-11-11-ws-36-c0-contract-review.md`). Five blockers require self-contained approval identity, exact-operation correlation, local no-model decline, enqueue-before-settle behavior, and explicit sensitive-turn guards. Four should-fix items cover request attribution, stale-session replies, replay bounds and zero-open bare yes. The palette values and contrast calculations had no finding. Claude corrects the contract for re-review; Kimi proceeds to A3 and C2 waits for corrected C0b.

## C4 implementation slice

System: Codex. Row: WS-35. Branch: `codex/ws35-c4-block-renderer-20261112`.
Reviewer: Kimi. Draft target: `next`. No merge/deployment authority exercised.

- C0 (#332) and C1a (#337) are ancestors; latest checked main `c23dda5` and next `2e9323a` are ancestors too.
- Added lenient composed layout decoding, atomic answer identity/revision, bounded validated blocks and five transition fixtures. Protected/clipboard content ignores layout. Unknown blocks skip; malformed/all-unknown/future layout falls back without losing identity. Unsupported action blocks intentionally fall back pending C7 transport.
- Added ordered Swift rendering with existing weather/brief, command/image views and shared typed roadmap card details. Roadmap wrappers are read-only; legacy interactive controls remain unchanged. Native bar charts retain signed geometry. Legacy output/export fields remain available.
- Display result/window stores update higher revisions in place, consume replay/stale packets, and preserve placement/pins/expansion. WorkspaceResultPane uses the composed view rather than legacy mode switching.
- Supporting scope: `Stores/DisplayResultStore.swift` is named by contract §1.12; new JarvisKit model/tests/fixture support its AppMessage scope. `RoadmapView.swift` extraction only shares the existing typed detail body.

**Incomplete integration / merge blocker:** `WorkspaceStore.swift` is not edited pending Larry's specific authorization for a bounded C4/C5 overlap. Current workspace routing still assigns a new UUID for repeated answer IDs. The required change is higher-revision in-place replacement preserving reader state and router stale/replay handling, including completion-only update suppression. This slice is not C4 completion or merge-ready. No carousel/C5, C7, SkillsWorkspaceView, harness model, production, credentials or deployment changes.

Evidence so far: JarvisKit full suite 248 passed, zero failures. Host pre-final-refactor full suite 593 tests, 3 existing skips, zero failures; no skips added. Five transition sequences pass at both display stores. Offline seven-block renderer captured at 480/1100 widths; final-source rerun and visual inspection follow below. First Host filter matched no tests and is recorded only as compilation evidence.
