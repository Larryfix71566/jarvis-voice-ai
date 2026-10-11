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

Terminal result: the unchanged approved `08c0635` → `d7a72a0` comparison
passed all twelve checks in 1,634.9 seconds. The exact-artifact audit passed
path/mode/blob, log hash, image/profile/runner, desktop and cleanup checks;
both owned VMs stopped, zero running, settings/image record unchanged. An
independent Codex reviewer verified the actual terminal artifacts. Source-head
CI `3e557c8` passed all five checks. Final evidence-only publication preserves
the normal CI merge gate. Larry reviews/merges #203 and reruns DEPLOY-MAIN;
production and exact-build live gates remain open.
