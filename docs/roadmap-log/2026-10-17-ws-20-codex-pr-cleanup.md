---
date: 2026-10-17
system: codex
rows: [WS-20, WS-21]
prs: [172, 174, 205, 206, 207]
---

# Review and cleanup of the open PR backlog

Larry requested review and cleanup after the acceptance-first PR #206 merged
as `1338fc72d26faa2adbcf84d25b211c6ffac5886c`. This is documentation reconciliation,
not new feature development or product acceptance. Branch:
`codex/pr-backlog-cleanup-20261017`; session:
`01a14bae-5269-78b0-abe8-6611e9c357dc`.

## Disposition of the older documentation PRs

- **#172**, `33f5778fca287b39f892ba845b04b446fd752bbc`: its WS-21 merged-state,
  missing re-review qualification and CX-16 resolution are already reflected
  in newer main. Its unique historical log is also carried by #174. Preserve
  that log verbatim in this reconciliation; close #172 as superseded after
  publishing the replacement. Retain the source branch.
- **#174**, `011fdb99021be991c078ec01e0714d24c4834e07`: its old roadmap edits
  predate later production, ownership, acceptance lists, and the acceptance-first
  decision. Do not merge the old roadmap wholesale. Preserve the two historical
  log files verbatim and the still-missing WS-21 plan status/progress correction.
  Close #174 as superseded after publishing this replacement; retain its branch.
- Copied paths are `docs/plans/MORTIMER_SUPPORTING_DISPLAY_TRANSFER_PLAN.md`,
  `docs/roadmap-log/2026-10-05-ws-20-claude-roadmap-sync.md`, and
  `docs/roadmap-log/2026-10-05-ws-21-claude-after-merge.md`. Their bytes match
  published #174; Claude's attribution is unchanged. Historical statements are
  dated observations, not current status. The plan explicitly retains live Mac
  acceptance and does not invent the unrecorded repaired-head review.

## Other PRs

#206 is already merged; WS-22 stays parked. #205 is a separate code review at
`09150adbbb5a804315a93f8b0b7c344f69c08627`, not included in this documentation
patch. Its 28 focused registry/preflight tests passed in an isolated test
environment with the real vault disabled and no live mailbox/provider call.
Passing those tests is not itself a review verdict or M1-1 live acceptance.
The independent reviewer result and any further probes belong to the review
handoff, not a fabricated product checkbox here.

## Validation scope

Validate unchanged existing checkbox lines, roadmap blocks for WS-13/17/21,
Production line, and parked WS-22; byte equality of the three recovered files
with #174; relative links and `git diff --check`. The baseline checker still
has the one inherited WS-13 merged-branch error that #205 corrects. Do not
change Claude's row just to make this independent documentation check green.

All product gates, source/provider authority, credentials, runtime flags and
deployment state remain unchanged. No branch deletion, deployment, or mail
code modification is part of this cleanup.


## Exact-head review result

Independent review and separate synthetic probes reproduced two issues in
#205 at `09150ad`: P2, shell-unset inherited values remain in the diagnostic
because it only overlays variables; P3, nested relative `--env-file` paths are
resolved twice after the subprocess changes directory. The
[recorded review](https://github.com/Larryfix71566/jarvis-voice-ai/pull/205#pullrequestreview-5560191620)
requests corrections with inline references. GitHub event is COMMENT, not a
formal REQUEST_CHANGES, because the connected account authors the PR. The
specialized Bugbot runtime was unavailable; an independent subagent review
was used and both findings were separately reproduced. No code was modified.


## Cleanup action completed

Replacement [PR #207](https://github.com/Larryfix71566/jarvis-voice-ai/pull/207)
was published before the closures. Immediately before closing, GitHub confirmed
#172 and #174 still matched the reviewed heads above. Both were closed as
superseded on 2026-10-17; neither branch was deleted. #207 retains the unique
content for review/merge. #205 remains open with the recorded findings.
No code PR was merged or deployed. All pre-existing checkboxes and WS-22's hold
remain unchanged.
