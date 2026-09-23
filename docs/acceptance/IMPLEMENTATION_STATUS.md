# Implementation and acceptance status

Updated September 18, 2026 from the release-review worktree; verification
counts reconciled and a model-use section added 2026-09-22 against main
`88b206f`. This matrix
separates repository implementation evidence from release acceptance evidence.
An implementation row is complete when its source, tests, and receipt are
present. A release row stays open when it needs physical hardware, a live
provider journey, or an observation period.

## Automated memory management

| Requirement | Implementation evidence | Acceptance evidence | Status |
| --- | --- | --- | --- |
| Admission classification without user labeling | `jarvis/memory_model.py`, `jarvis/memory_automation.py` | Memory fixtures and focused tests | Complete in sandbox |
| Scoped corrections, provenance, revisions, validity | Memory and sweep changes | Offline B5 receipt; acceptance tests | Complete in sandbox |
| Task-relevant retrieval and usage accounting | Retrieval changes and `used_for` assertions | Focused memory suite | Complete in sandbox |
| Quiet bounded idle maintenance | `memory_watcher.py`, retry/budget tests | Worker and teardown tests | Complete in sandbox |
| Privacy-safe shadow and provider route | Provider runner and registry route | Provider shadow receipt and dry-run | Complete in sandbox; production disabled |
| Staged rollout and rollback thresholds | `JARVIS_MEMORY_AUTOMATION_STAGE`, evaluator | Rollout receipt; manifest checks | Complete in sandbox |
| Mac staged enablement and benefit/cost observation | Runtime procedure in runbook | Redacted daily-driver receipt | Open: requires Mac observation |

## Command Center and Knowledge Atlas

| Requirement | Implementation evidence | Acceptance evidence | Status |
| --- | --- | --- | --- |
| Layout 2 command console and compact Conversation startup | Native composition and layout tests | Full-console and live candidate inspection | Complete in sandbox; live candidate observed |
| Shared pointer/voice action ownership | `ConsoleActionCoordinator`, protocol/registry | Swift/Python parity and stale-target tests | Complete in sandbox |
| Atlas, graph, pins, comparison, reading state | Atlas/graph stores and rendering tests | Atlas, graph, large-fixture and frame-time receipts | Complete in sandbox |
| One response result per request | `ResponseResultRouter`, stable workspace/display IDs | Response-routing and focused native receipt | Complete in sandbox; live ownership observed |
| Bounded supporting display and return-to-main | Display stage budget and placement owner | Live two-result stage, automatic unplug/rehome, reconnect restoration, and close/return receipts | Open: voice-triggered repeat and provider/fetch evidence remain |
| Text/image sharing and inbound approval | Share coordinator, attachment transfer, privacy latch | Unit and protocol tests | Open: live picker/provider journey |
| Voice parity and two-channel measured audio | Native voice routing and waveform tests | `READY VOICE` observed; live spoken-response receipt | Open: active user/output audio evidence |
| Accessibility, rollback, independent verification | Test hooks and legacy layout paths | Mac accessibility, rollback, verifier receipts | Open |
| Five-day daily-driver acceptance | Candidate freeze/runbook | Dated daily-driver log | Open |

## Current automated verification

Reconciled 2026-09-22 against main `88b206f`. The figures below are the
counts recorded in the committed 2026-09-18 receipts (Mac, release-review
worktree). They are receipt-time counts, not current pass counts; the current
static test counts at `88b206f` are given for comparison.

- Python: **2611 passed, 4 skipped** in the Mac receipt. At `88b206f` on
  Linux, `pytest tests/unit` gave **2,526 passed** (run by Claude
  2026-09-22; a different platform and collection, so not directly comparable).
- JarvisKit: **190 passed** in the linked receipt. The earlier "195 passed"
  figure here (including the five `GraphImageRequestsTests`) is not recorded
  in a committed receipt; the source at `88b206f` has **195** static
  `func test` methods, so 195 is a static count, not a verified pass count.
- MortimerHost: **244 executed, 3 skipped, 0 failures** in the latest
  complete run in the receipt; the display-dependent skips require two
  connected displays and are covered by live monitor receipts. The source at
  `88b206f` has **250** static `func test` methods; no committed receipt
  records a run of all 250.
- Focused native rerun: **47 passed** in
  [current-focused-native-2026-09-18.md](command-console/receipts/current-focused-native-2026-09-18.md)
  (`ScreenPlacementTests` 8 + Command Center/rendering/ownership filter 39).
  The later full-verification receipt records `ScreenPlacementTests` **9/9**,
  which matches the 9 static tests now in that file.
- Plan manifest: **7 passed** (receipt); also 7 passed at `88b206f` on Linux,
  2026-09-22.
- Formatting: `git diff --check` passed.

The latest complete verification is recorded in
[full-verification-2026-09-18.md](command-console/receipts/full-verification-2026-09-18.md).

## Model use enhancements

Added 2026-09-22 (reconciled against main `88b206f`). The detailed record is
[model-use-enhancements/STATUS.md](model-use-enhancements/STATUS.md). The
committed receipts under `model-use-enhancements/receipts/` show only the
following:

| Requirement | Committed receipt | What it shows | Status |
| --- | --- | --- | --- |
| Call-site inventory (MAR-G) | `model-call-site-inventory-2026-09-20.json` | Static inventory: 13 call sites, 13 covered, 0 review-required, `secret_free: true` | Implementation evidence; enabled-mode runtime evidence open |
| Secret-free route readiness | `route-readiness-2026-09-20.json`, `vault-backed-route-readiness-2026-09-20.json` | Without the vault, every workload reports `ANTHROPIC_API_KEY is not set`; with the vault, `ready_issues: []`, `routing_enabled: false`, SAYGM route `credential_present: false`, no catalog or probe run | Readiness report only |
| SAYGM (MAR-E) | `saygm-readiness-2026-09-20.json` | Catalog check failed closed: `SAYGM_API_KEY is not set` | Open |
| Subscriptions (MAR-F) | `subscription-probes-2026-09-20.md`, `subscription-readiness-2026-09-20.json` | Codex probe returned `SUBSCRIPTION_PROBE_OK`; Claude reported `Not logged in` | Open |
| Memory pilot (MAR-I) | `../memory-automation/provider-shadow-receipt.json`, `../memory-automation/rollout-monitoring-receipt.json` | Direct-API 8-case synthetic memory shadow (8/8, no regression) and offline rollout gate; routing layer not enabled | Open |

The status file also describes user-run checks on 2026-09-21 and 2026-09-22
(Claude login and probe, SAYGM catalog with 56 models). They are not recorded
in a committed receipt and remain unverified.

The exact procedures for remaining rows are in
[ACCEPTANCE_RUNBOOK.md](ACCEPTANCE_RUNBOOK.md). Detailed checklists remain in
[memory status](memory-automation/STATUS.md), [Command Center status](command-console/STATUS.md),
[model-use status](model-use-enhancements/STATUS.md),
and [adaptive-interface release readiness](adaptive-interface/RELEASE_READINESS.md).
