---
date: 2026-11-12
system: claude
rows: [WS-35]
prs: [339]
---

# WS-35 F1 phone-test prerequisites — Claude's independent review of #339, Claude, 2026-11-12

System: Claude (Claude Code cloud session, Larry's Claude Duet channel). Nonauthor reviewer. The closure plan and #339's body name Kimi as F1's reviewer. Larry reassigned this review to Claude on 2026-11-12 at 15:52:31 UTC ("Yes, Claude takes them", answering whether Claude takes Codex's #337 and #339 reviews from Kimi). Claude did not write #339. This change is documentation only: this entry. It does not change the WS-35 block, which is Codex's scope.

## What was reviewed

[#339](https://github.com/Larryfix71566/jarvis-voice-ai/pull/339), head `baf4dfecbec15c18a30ca9914639300b78d5b32f`, base `main`. All five checks pass at that head (validate, allowlist, policy-tests, controller-tests, knowledge-base). The PR is ready for review, not a draft.

Four files change:

- `macos/MortimerHost/Tests/PhoneRemoteAuthorityTests/PhoneRemoteAuthorityProcessTests.swift`: the fix, in source commit `3e04808`.
- Codex's evidence log `docs/roadmap-log/2026-11-11-ws35-f1-process-prerequisites.md`.
- The WS-35 block in `ROADMAP.md` and two dated-progress lines in `docs/plans/MORTIMER_RELEASE_CLOSURE_PLAN.md`.

No production source changes.

## The fix

`testOrdinaryUnknownWaitRetainsActualSingletonAfterPartialEOF` used `try XCTUnwrap(...)` on `PHONE_REMOTE_AUTHORITY_OWNER_BIN` and `PHONE_REMOTE_AUTHORITY_PYTHON`. In a plain `swift test`, neither variable is set, so the test failed instead of skipping. The fix:

- skips with `XCTSkip` when the owner variable is unset or not an executable file;
- uses the Python variable if set, otherwise `findPython()`, and fails with a message if neither finds one.

| Claim | Evidence | Result |
| --- | --- | --- |
| This was the cause of the F1 failure | Kimi's 2026-11-06 revalidation log on Larry's Mac at `4e58eaa` ([log](2026-11-06-ws-17-kimi-combined-main-revalidation.md), lines 46–60): "XCTUnwrap failed" in this test, which sat at line 76 on `main`; authority target 28 tests, 3 skips, 1 failure | confirmed |
| The new prerequisite handling matches the sibling process tests | The same owner guard and Python fallback appear in the same file at lines 126, 182 and 218 (owner guard in each) | identical pattern |
| `findPython()` searches PATH for `python3.12`, then `python3` | lines 324–333 of the same file | confirmed |
| Every singleton and reaper assertion is kept | the diff changes only the two prerequisite lines; the rest of the test body is untouched | confirmed |
| The test passes when its prerequisites are present | Hosted run of #338 on `e4ef119` (`next`, without this fix): the fixture step exported the owner binary and `/usr/local/bin/python3.12`; `PhoneRemoteAuthorityProcessTests` executed 8 tests with 0 failures and no skips; this test passed in 0.138 s in both hosted runs | independent pass with a real owner |
| Codex's counts on the exact source `3e04808` | Codex's log: enabled authority suite 28 tests, 0 skips; plain authority run 4 skips; full plain run 618 tests, 7 skips, 0 failures (authority 28 with 4 skips, app 590 with 3 skips); log SHA256 `fa1505f1…` | test counts match Kimi's (590 and 28). The authority skips go from 3 to 4, which is this test now skipping. App-target skips differ: Kimi had 5 (two Screen Recording, three second-display; log lines 65–76), Codex reports 3, all second-display. That fits Screen Recording being granted in Codex's run, but this review has not confirmed it. The app target is untouched by #339 |

Closure plan §8 accepts a Swift test run by Codex, Kimi or CI recorded in the PR with counts. Codex's run is recorded in the PR body and its log. Claude ran no Swift; this environment has no Swift toolchain.

## Findings

No blocking findings.

- **Merge conflict (needs the author).** GitHub reports #339 as not mergeable. Since its base `4a0dd96`, `main` gained #333 and #348. A local merge of `pr/339` into `origin/main` at `d5bf2c8` conflicts only in `docs/plans/MORTIMER_RELEASE_CLOSURE_PLAN.md` dated progress: main's three 2026-11-11/12 lines against #339's two Codex lines. Keeping both sides resolves it. `ROADMAP.md` and the test file merge cleanly.
- **Nit, reviewer named in the block.** The WS-35 "Next step" says "kimi: review #339". This review now covers it under Larry's reassignment; the next step is Larry's approval by name. Codex can update the line when it resolves the conflict.
- **Not a finding.** In a plain `swift test`, this test now skips rather than running. That is the documented behavior of its siblings, and the enabled run exercises it.

## Verdict

**APPROVE** at `baf4dfe`. Test-only change, cause confirmed, the pattern matches its siblings, and the test passes with a real owner in an independent hosted run.

Before merge:

1. Codex resolves the closure-plan conflict against current `main`.
2. Larry approves #339 by name. `main` is frozen (§0 rule 15), and this is a code change. This review is not that approval.
3. After an authorized merge, the author merges `main` forward into `next` the same day.

## Unchanged

No source, test, workflow, plan, ROADMAP block or acceptance checkbox was changed. No GitHub review or comment was posted on #339. No Swift test was run.
