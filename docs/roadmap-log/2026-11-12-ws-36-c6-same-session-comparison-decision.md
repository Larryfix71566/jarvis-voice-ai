---
date: 2026-11-12
system: claude
rows: [WS-36, WS-35]
prs: [335]
---

# WS-36 C6 orb frame-time comparison: same-session crystal control, Larry's decision, 2026-11-12

System: Claude (Claude Code cloud session, Larry's Claude Duet channel). This entry records a decision by Larry. It changes the C6 comparison rule in `docs/interface-research/orb-plasma/ORB_SPEC.md` and adds a dated line to the closure plan's progress log. No code or test changed.

## Decision

Larry, 2026-11-12 at 16:32:00 UTC: "Use your pick for C6". He was answering the coordinator session's 16:18 UTC message, which proposed measuring crystal and arcs back to back in the same session, five runs each, and comparing those instead of a stored p50.

The rule for both C6 probes (arcs only; arcs plus refraction with the shadow and cast light):

1. On the Mac, in one session, run the crystal probe and the arcs probe back to back, five runs of each.
2. Take the median p50 and the median p95 of each side's five runs.
3. Pass if all three hold:
   - the arcs median p50 is at most 1.10× the crystal median p50 from that session;
   - the arcs median p95 is at most 1.10× the crystal median p95 from that session;
   - p95 is under 16.7 ms, as the spec already required.

The C10 component receipt ([2026-11-12-ws-35-c10-component-baseline-receipt.md](2026-11-12-ws-35-c10-component-baseline-receipt.md)) stays as the record of the freeze. It is not C6's comparison point. Neither is the historical 2026-09-29 receipt (p50 4.933 ms, p95 14.150 ms), which the spec previously named.

The decision does not fix the order of the ten runs, and it does not say whether the 16.7 ms limit applies to the median or to every arcs run. The spec's existing wording ("p95 under 16.7 ms") is kept unchanged on that point.

## Why

In Larry's C10 baseline on the frozen build `5777e98`, crystal p50 was 5.428, 7.576 and 6.150 ms over three runs, so run 2 is 23% above the median. Crystal p95 was 13.499, 13.413 and 13.677 ms, about 2% apart. Against a stored p50, the 10% rule could fail on run-to-run variation with no change to the orb. The raw files are in [the receipt's raw folder](2026-11-12-ws-35-c10-component-baseline-raw/).

## Where the rule is written

| Document | Branch | Change |
| --- | --- | --- |
| `docs/interface-research/orb-plasma/ORB_SPEC.md`, Gates (Performance) and Measure first | `main`, this change | Updated: compare against same-session crystal runs; new step 3 gives the method; steps renumbered 4 to 6 |
| `docs/plans/MORTIMER_RELEASE_CLOSURE_PLAN.md` | `main`, this change | The C6 row never stated the 10% rule, so the row is unchanged; a dated progress line records the decision |
| `docs/acceptance/ws35-c10-freeze-performance-baseline.md` section 4, third bullet ("Each p50 and p95 must be ≤1.10× the crystal baseline") | #335 into `next`, Codex's, already approved | **Not edited here.** Follow-up for Codex after #335 merges: replace "≤1.10× the crystal baseline" with "≤1.10× the median of five crystal runs measured back to back in the same session as five arcs runs (Larry, 2026-11-12)" |

## Unchanged

No source, test, workflow, ROADMAP block or acceptance checkbox was changed. #335 was not edited. No benchmark was run.
