# Implementation and acceptance status

Updated September 18, 2026 from the release-review worktree. This matrix
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

- Python: **2611 passed, 4 skipped**.
- JarvisKit: **195 passed** (including five graph request-sharing tests).
- MortimerHost: **244 executed, 3 skipped, 0 failures** in the latest
  complete run; the display-dependent skips require two connected displays and
  are covered by live monitor receipts.
- Current focused native rerun: **47 passed**.
- Plan manifest: **7 passed**.
- Formatting: `git diff --check` passed.

The latest complete verification is recorded in
[full-verification-2026-09-18.md](command-console/receipts/full-verification-2026-09-18.md).

The exact procedures for remaining rows are in
[ACCEPTANCE_RUNBOOK.md](ACCEPTANCE_RUNBOOK.md). Detailed checklists remain in
[memory status](memory-automation/STATUS.md), [Command Center status](command-console/STATUS.md),
and [adaptive-interface release readiness](adaptive-interface/RELEASE_READINESS.md).
