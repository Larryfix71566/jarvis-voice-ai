---
date: 2026-11-12
system: claude
rows: [WS-35]
prs: [338]
---

# PR #338: WS-35 row status text moved out of `ROADMAP.md`

System: Claude, at Larry's request to clear the open PRs' conflicts (2026-11-12 18:10 and 18:15 UTC: "I am seeing conflicts in all remaining PR", "all still show conflicts unresolved").

Claude merged `next` at `c41004c` into this branch and set `ROADMAP.md` back to `next`'s version. A first pass kept this PR's WS-35 Scope line; at 18:51 UTC the branch conflicted with `next` again on that line, so a second pass merged `next` at `cf317f4` and moved the Scope line here too, leaving `ROADMAP.md` identical to `next`. Under the daily batch rule (§0 rule 16, #359) a PR records status only in its own log file and does not edit a row's Status, Where, Next step or Updated lines; the daily batch PR folds this text into the row after the PR merges. No code, test, workflow or other document changed in this step.

## WS-35 row lines this PR carried (verbatim, from head `2bccae50`)

- **Status:** in-progress; B1 Swift CI implemented by #338; its first hosted Host build failed Swift 6.2.4 type checking. Larry approved the bounded SkillsWorkspaceView expression split on 2026-11-12; repair compiled on hosted Swift 6.2.4, but 618 Host tests exposed 16 assertion failures across seven tests (three skipped). B1 remains blocked, #338 draft; see its evidence log. C10 baseline instructions are #335, measurements not run. C0/C0b review is #334. Larry approved the starter-prompt claim exception on 2026-11-11.
- **Where:** `codex/ws35-b1-swift-ci-20261111` into `next` (B1); `codex/ws35-c10-baseline-20261111` (#335, C10 instructions); `codex/ws35-contract-review-20261111` (#334, contract review). Code items branch from `next`, except F1 from `main`.
- **Next step:** larry: authorize the next bounded investigation of the seven hosted Host test failures recorded in the B1 log; codex: preserve #338 draft until resolved; claude, kimi: review B1 before dependent Swift work; kimi: review C10 instructions; larry: capture the verified freeze baseline in `docs/acceptance/ws35-c10-freeze-performance-baseline.md` before C1a merges; codex: develop C1a separately. claude: address the three findings in `docs/roadmap-log/2026-11-11-ws35-c0-contract-review.md` for #332 before C4; kimi: complete independent contract review. F1 requires named acceptance-fix approval before merge.
- **Updated:** 11-12

## WS-35 Scope line this PR carried (verbatim, moved in the second pass)

This is not a status line. It adds the B1 compile repair Larry approved on 2026-11-12 to WS-35's scope; the daily batch PR (or Codex) puts it back in the row after this PR merges.

- **Scope:** The files named for those items in the plan's §4 WS-35 table: `docs/acceptance/**` (C10); every MortimerHost source and test file that reads `layoutVersion` (C1a); `.github/workflows/validate.yml` (B1, B5, after A1); Larry-approved 2026-11-12 B1 compile repair in `macos/MortimerHost/Sources/MortimerHost/Console/SkillsWorkspaceView.swift` (expression decomposition only); `macos/MortimerHost/Sources/MortimerHost/Display/**`, `App/AppMessageRouter.swift`, `macos/JarvisKit/Sources/JarvisKit/AppMessage.swift` (C4); the C5 result and carousel files; `ios/MortimerPhoneCore/**` and the shared orb package (C9). Hand-off order for shared files is the plan's §4 "Hand-off points"; overlaps with other rows are CX-29.
