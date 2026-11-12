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
