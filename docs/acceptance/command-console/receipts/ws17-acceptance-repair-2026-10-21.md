# WS-17 acceptance repair — frozen-source evidence

Frozen implementation: [`d242ba405915aec9c12af4c2553ef1b42cf1079e`](https://github.com/Larryfix71566/jarvis-voice-ai/commit/d242ba405915aec9c12af4c2553ef1b42cf1079e).
Draft [#233](https://github.com/Larryfix71566/jarvis-voice-ai/pull/233).
Automated checks do not close live acceptance. Host capture, cross-system review,
provider integration, release and observation gates remain open.

Accepted-input targets reject wrong device/generated-city weather before lookup,
fetch or display. Actual SDK/router/store witnesses confirm the wrong-first-card
cause; the one-opening rule and native cache/timestamp/privacy authority remain.
Exact pending operations are not duplicated. Explicit task-stop input cancels work
and refuses a fresh delegation on that turn; speech barge-in lets work continue.
Guidance separates rendered roadmap/build authority, reported versus verified
versus canonical Git-updated acceptance, and missing-executor handoff. No dedicated
wizard, runner grant, provider activation or deployment.

## Completed automated checks

| Check | Recorded result |
|---|---|
| Full host backend | 6,859 passed, 15 skipped, two subtests; 19 warnings; 287.81s |
| Affected regressions | 901 passed; ten warnings; overlaps full suites |
| Public synthetic phrase matrix | 55 passed; no model/provider calls |
| Bound-intent Registry/cache/privacy controls | Five passed; no provider fetch |
| Native SDK/router/store witnesses | Two passed; no production/audio/provider |
| Original independent profile | Twelve original checks PASS; source/log hashes verified |
| Candidate independent backend | 6,662 passed, 11 skipped, two subtests; 59 warnings |
| Candidate independent native | 580 executed, eight prerequisite skips, zero failures |
| Frozen-source CI | All five checks PASS on `d242ba4` |
| Strict roadmap drift | Zero errors/warnings; 144 checkbox and 29 owner lines preserved |
| Publication metadata contracts | 57 passed, two warnings; runtime/test bytes unchanged |

These groups overlap; they are not a total of acceptance obligations. Native VM
skips cover actual capture, multiple displays and activation prerequisites. They
confer no physical pass; exact reasons remain in the JSON receipt.

| Original check | Result | Seconds | Log SHA-256 prefix |
|---|---|---:|---|
| backend-imports | PASS | 2.051 | `01ba4719c80b6fe9…` |
| baseline-backend | PASS | 437.472 | `a5bc586f0d4bf32b…` |
| backend | PASS | 486.086 | `f4922b08f1a577e5…` |
| scripted-evals | PASS | 1.367 | `1442154f0176fe37…` |
| latency | PASS | 0.117 | `c192bbb7b228dedb…` |
| knowledge-base | PASS | 3.357 | `36d0d975ad07c14e…` |
| baseline-knowledge-base | PASS | 5.754 | `d4c63f609526ddf5…` |
| web | PASS | 30.998 | `1eae799df088a7de…` |
| native-library | PASS | 91.953 | `6c46d03c10b59be4…` |
| native-app | PASS | 232.163 | `051530d232a83183…` |
| baseline-native-library | PASS | 31.736 | `db9fc1e2d50d2140…` |
| baseline-native-app | PASS | 187.809 | `b15732956f1cace9…` |

The [JSON receipt](ws17-acceptance-repair-2026-10-21.json) records full commands,
log hashes, fingerprints and the changed source/test manifest. Candidate:
`8acff7746a353ad5ada562fb1893a60312a29ff6fa81292e202daaed197e1014`.
Protected baseline: `08c0635`. Original image/profile/runner remain unchanged.

## Non-passing evidence and remaining gates

The original host native run stalls; the bounded repeat times out at 600s.
A one-worker isolated diagnostic schedules 580 cases and fails two actual
ScreenCaptureKit captures plus two unchanged nil-NSApp test processes. A fresh
post-VM serial capture still fails `SCStreamErrorDomain -3811` despite permission
preflight, with no competing test process. The four failure-path files match
main `3061408` byte-for-byte; source identity does not prove environmental cause.
No test, assertion, prerequisite or security setting is removed or waived.

The early `30bbcea` VM attempt is interrupted for proven source regressions.
The first `d242ba4` attempt loses its orchestrator during the executor disconnect;
its partial candidate log has no verdict. Both remain non-passing. Recovery
confirms no guest test remains, cleans the orphan child, refreezes identical source
and reruns all twelve original checks in one bounded process. Owned cleanup and
preservation checks pass; settings, prior assets and production stay unchanged.
The scheduled cleanup job remains paused.

The exact 474,299-byte source/synthetic cross-review packet is prepared locally,
SHA-256 `206c1a4449f9870d8c936b96815d882e2b505e66d31c36693915a7d457c5d4a5`.
It has not been transmitted; parent-managed consent/review is pending. No verdict.
Provider owns the newer tool-dispatch preview conflict: preserve both stop-turn
refusal and source-policy scope, then review and reverify integrated source.

No canonical checkbox closes here. UI2-22/23/24/25, dependent UI2-04/09/13,
hardware/human checks, gated deployment/rollback, five-day release observation
and the separate WS-06 week remain open. After release gates, use one short
session: roadmap/main-window/build truth; multi-turn references; speech versus
task stop; Spartanburg → Atlanta → Spartanburg reuse/opening; and observation
versus reviewed canonical readback.

This publication changes docs/evidence only. Runtime/test bytes stay identical
to frozen `d242ba4`; publication-head CI is separate. Raw production records,
operational installed metadata and reviewer reasoning remain local.
