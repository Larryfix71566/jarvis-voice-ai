---
date: 2026-10-11
system: codex
rows: [WS-17]
prs: [203]
---

Larry's exact-main DEPLOY-MAIN failed phase A on `d5d3e7e`; production remains
`bde22bb`. Unchanged-capture controls isolated pointer-overlay nondeterminism.
Source `d7a72a0` adds only three lines disabling the cursor in the synthetic
thread capture. Full pixel equality, nonblank witness, privacy guards and
timing remain intact. Deliberately exposing synthetic private text still
fails the original pixel assertion, and runtime source was restored exactly.

The full Mac suite passed 551 tests / six prerequisite skips / zero failures
on 10-11, including both actual SCK capture cases. Retain the prior native
run's unrelated old-test SCK `-3811` startup failure; its cause is unproven
and no legacy test edit was retained. Same-approved-reference twelve-check
offline verification is running, with all runtime/configuration/verifier
source unchanged. PR #203 waits on that result and CI before merge/deployment.

Current-main's existing WS-13 ownership checker error remains reported in the
10-10 handoff; this slice does not edit Claude's row. See the capture receipt
and dated progress in the existing Command Console plan. No live gate closed.
