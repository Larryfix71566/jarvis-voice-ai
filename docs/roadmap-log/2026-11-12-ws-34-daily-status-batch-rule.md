---
date: 2026-11-12
system: claude
rows: [WS-34]
prs: []
---

# Daily status batch rule — Larry's decision, 2026-11-12

System: Claude (Claude Code cloud session, Larry's Claude Duet channel). This entry records a rule Larry adopted. It is the status record for this change; under the rule itself, the WS-34 row and the closure plan's progress log are not edited here.

## Decision

Larry, 2026-11-12 at 16:41:17 UTC, in his Claude Duet channel: "Adopt the batch rule". He was answering the coordinator's 16:37:54 UTC post, which found that eight open PRs (#334, #335, #337, #338, #339, #350, #351, #352) conflict with `main` in `docs/plans/MORTIMER_RELEASE_CLOSURE_PLAN.md` and in no other file, and proposed: PRs record status only in their own `docs/roadmap-log/` file, and one batch PR a day, written by Claude, updates the plan's progress lines.

## Where the rule is written

| File | Change |
| --- | --- |
| `AGENTS.md` | New section *Status records and the daily batch* with the five-point rule; "One plan per row" and "When you finish a slice" now point to it instead of asking for row and plan updates |
| `CLAUDE.md` | The two coordination bullets that asked for plan progress and row updates in the same change now point to the batch |
| `ROADMAP.md` §0 | New rule 16; rule 5 points to it. Rule 16 says it replaces rule 10's and the shared update format's in-PR row and plan updates |
| `docs/plans/MORTIMER_RELEASE_CLOSURE_PLAN.md` | One line under *Progress log*: only the batch PR adds lines there |

## Claude's reading, for Larry to correct

The coordinator's wording named "progress/status lines" and "checklist/progress rows". Claude took these as status lines: a row's Status, Remaining work, Next step and Updated lines, plan progress entries and checklist boxes. Claims (Owner and Where), new rows, rule and scope changes, §3 reservations and §4 entries stay in the PR that needs them, because the protocol depends on them landing before work starts (§0 rules 3, 6 and 4). Checklist boxes go through the batch, which keeps Larry's ticks in one daily review.

## Applied so far

#358 (Claude's C10 receipt and C6 rule) dropped its closure-plan progress line at `6354680d`; that status is in its two log files.

## Open

- The batch time is not set. Claude proposed 08:00 US Eastern, folding everything merged since the previous batch.
- The eight PRs above still carry closure-plan progress edits. Codex drops them and moves the text into each PR's log file.

## Freeze note

`AGENTS.md` and `CLAUDE.md` are outside `docs/` and `ROADMAP.md`, so §0 rule 15 lets this PR merge only with Larry's approval by name. No source, test, workflow or configuration file changed.
