# Revised WS-05 / WS-17 source verification

Verified source [`e74e4b8e66916bb0de64c76a62333e6e4971e90f`](https://github.com/Larryfix71566/jarvis-voice-ai/commit/e74e4b8e66916bb0de64c76a62333e6e4971e90f),
tree `d9094de25702299fbddc633c57282618c1214d00`, published ref
`codex/ws05-ws17-selective-preview-e74e4b8`.
This reuses exact handed-off preview `794a298` and replays provider `fec3d51`
without conflicts. Acceptance publication input is `a7a269a`; its program bytes
are `d242ba4`. Content inputs and actual ancestry are recorded separately.
Earlier preview evidence remains historical and does not validate the new guard.

**All twelve original independent checks PASS**, terminal 12:14:25 UTC.
Candidate fingerprint: `258a67be2bdc289c28ee6db54bd3ff5a8fc1c3d5a7bfb63a5fc066caefb484f9`.
Owned cleanup and source/settings/prior-asset preservation checks pass. Original
image/profile/runner/dependency key/protected baseline and fixtures are unchanged.
No check, assertion, timeout or source scanner was weakened.

| Original check | Result | Seconds | Log SHA-256 prefix |
|---|---|---:|---|
| backend-imports | PASS | 1.489 | `01ba4719c80b6fe9…` |
| baseline-backend | PASS | 428.811 | `260932cd663ed46b…` |
| backend | PASS | 455.171 | `240dba28752f6088…` |
| scripted-evals | PASS | 1.783 | `d2aa9ece20bb36a8…` |
| latency | PASS | 0.127 | `c192bbb7b228dedb…` |
| knowledge-base | PASS | 3.191 | `240556f3214f990e…` |
| baseline-knowledge-base | PASS | 4.969 | `f110740aaa938162…` |
| web | PASS | 30.976 | `6889ec8cb7eade7f…` |
| native-library | PASS | 89.217 | `012bb66cd0db6255…` |
| native-app | PASS | 212.158 | `7fb946f36afd9907…` |
| baseline-native-library | PASS | 23.049 | `fd1f6c45b58e6a3a…` |
| baseline-native-app | PASS | 182.253 | `c20623d2ecf748a6…` |

Candidate backend: **6,764 passed, 11 skipped, two subtests passed**,59warnings.
Candidate native: **580 executed, eight prerequisite skips, zero failures**;
JarvisKit235 tests, zero failures. Native skips concern capture, displays and
active-app prerequisites and confer no physical acceptance. The latency check
uses a fixture; it establishes no live provider latency.

Combined affected regressions: **457 passed**,10warnings,13.65s. Complete host
integration suite: **197 passed, four skipped**,3warnings,66.02s. An earlier
restricted integration attempt failed14 tests/4errors because the command sandbox
denied synthetic localhost listeners and process inspection. That failed record
is preserved; one supported rerun used unchanged tests and code. No persistent
setting or access change. Test groups overlap; do not sum as acceptance totals.

The previously recorded physical-host native suite on `f3aa78b` passes580cases,
five prerequisite skips, zero failures, and actual-window control passes1/0.
Native program/test bytes match this candidate exactly. Earlier failures remain
historical non-passing evidence; their causation is not retroactively established.
Strict candidate roadmap validation has zero errors/warnings against explicit
main `3061408`, without warn-only mode. Both input PR heads `fec3d51`/`a7a269a`
had all five CI checks pass. New publication/integration-head CI is separate.

Actual PR integration reuses the verified pipeline resolution verbatim and
preserves both workstream histories. Every non-documentation program/config/
dependency/test byte matches `e74e4b8`; the JSON records the source manifest,
original command arguments, full log hashes, fingerprints and exact skip reasons.
The [JSON receipt](ws05-ws17-selective-integration-2026-10-21.json) contains source
and synthetic test evidence only; operational/account/ledger records remain local.

Required exact-source cross-system review is **not completed**; no review verdict
is inferred from test or CI passes. Merge authorization exists, but required
review and final current-head checks remain binding. No automated result closes
UI2-22/23/24/25, dependent04/09/13, physical/human acceptance, deployment/runtime
or real observation requirements. No canonical acceptance checkbox changes.
