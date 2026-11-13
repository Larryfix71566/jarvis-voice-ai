---
date: 2026-11-13
system: kimi
rows: [WS-35, WS-36]
prs: [358]
---

# WS-35 / WS-36: independent review of PR #358

System: Kimi, independent exact-head review of Claude's docs-only PR #358.

## Verdict: APPROVE

Approved at exact head `6354680d56a4a7ba700af99ad64b4f2a273702f3` for its documentation and evidence-record scope. The review was initially pinned at `ddf8c4f78b32d9ed790a54d3a9e0ca3cb8585bf8`; the later docs-only commits were inspected, the C10 raw artifacts and receipt were unchanged, and `ORB_SPEC.md` was unchanged. The C10 receipt agrees with the raw result artifacts, and the `ORB_SPEC.md` comparison rule matches Larry's 2026-11-12 16:32 decision. No numerical or wording discrepancy was found.

This is a documentation verdict, not benchmark execution, deployment, native acceptance, or completion of C10 section 3.

## C10 receipt independently recomputed

The six raw JSON files and the Skills measurement logs were read directly. Values below are milliseconds; each median was recomputed from the three recorded runs rather than copied from the receipt.

| Measurement | Recorded runs | Recomputed median |
| --- | --- | ---: |
| Crystal p50 | 5.428, 7.576, 6.150 | 6.150 |
| Crystal p95 | 13.499, 13.413, 13.677 | 13.499 |
| Crystal max | 14.373, 15.155, 15.346 | 15.155 |
| Empty p50 | 0.745, 0.766, 0.767 | 0.766 |
| Empty p95 | 0.840, 0.871, 0.846 | 0.846 |
| Memory p50 | 8.042, 7.997, 8.078 | 8.042 |
| Memory p95 | 10.689, 9.656, 9.643 | 9.656 |
| Pan p95 | 9.921, 9.660, 9.591 | 9.660 |
| Zoom p95 | 10.788, 9.630, 10.703 | 10.703 |
| Control p50 | 4.031, 3.904, 3.553 | 3.904 |
| Stress control | 1.995, 2.048, 2.274 | 2.048 |
| Wide selection layout | 12.073, 13.402, 13.591 | 13.402 |
| Wide cached navigation | 42.951, 45.383, 45.714 | 45.383 |
| Wide selection render | 28.655, 30.585, 30.704 | 30.585 |
| Compact selection layout | 7.118, 7.958, 8.120 | 7.958 |
| Compact cached navigation | 26.800, 28.598, 28.888 | 28.598 |
| Compact selection render | 14.648, 15.808, 16.057 | 15.808 |

The receipt's variation statements also recompute correctly:

- crystal run-2 p50 is 23.18699% above the 6.150 ms median (reported as 23%);
- crystal p95 spread is 1.95570% (reported as about 2%).

All three Skills cases report 64 distinct rendered frames and zero detail requests during measurement. The orb budget/sensitivity and memory p95 gates passed in all three runs.

## Evidence integrity and checks

- All 16 files listed by the raw folder's `SHA256SUMS.txt` verified successfully.
- `exit-codes.txt` records nine runs, all with `exit=0`.
- `scripts/check_roadmap.py`: `roadmap check: 0 errors, 0 warnings`.
- `git diff --check` reports trailing whitespace only in the raw `run1-OrbShellFrameTimeTests.log`; this preserves uploaded evidence bytes and is nonblocking for this docs/receipt review.

## C6 wording matches Larry's 16:32 decision

`docs/interface-research/orb-plasma/ORB_SPEC.md`, **Measure first**, step 3 requires all of the following:

1. five crystal runs and five arcs runs;
2. back to back on the Mac in one session;
3. median p50 and median p95 for each side;
4. arcs median p50 at most 1.10× crystal median p50;
5. arcs median p95 at most 1.10× crystal median p95;
6. p95 under 16.7 ms;
7. the same rule for arcs plus refraction.

That is an exact match to Larry's requested decision. The separate C6 decision log expressly leaves the order of the ten runs and whether the 16.7 ms ceiling applies to the median or every arcs run unresolved. Those disclosed interpretation limits do not contradict the requested wording.

## Scope limits

No benchmark was run by this reviewer. Nothing was deployed, launched, recovered, restarted, or accepted on a Mac. No provider/live call, credential, Keychain, or vault access occurred, and no acceptance checkbox changed.

This review does not independently confirm the receipt's unrecorded machine-state fields, including AC power, display topology, accessibility settings, or Liquid Glass state. It does not perform or accept C6, accept native performance, deploy the C10 freeze, or unblock C10 section 3.
