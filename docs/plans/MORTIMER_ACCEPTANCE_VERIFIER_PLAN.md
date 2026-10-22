# Acceptance Verifier within Systems — WS-23

**Status:** Proposed canonical preparation plan, 2026-10-22. Owner: Codex for
documentation only on `docs/roadmap-preparation-claims-20261022` after registration
lands. No automated profile, runtime implementation or acceptance is delivered.
[WS-23](../../ROADMAP.md#ws-23) retains acceptance-first and main-first code gates.

## 1. Evidence and boundaries

Read-only analysis used main `c63ecce97108787c55ef55fad73d32236694cc65` and
pending #252 `86d079f74de6b3bb07d2f05deeec18a516f472ea`. Eight focused GitHub reads;
no application tests, private logs, credentials, model calls or VM execution.

`sandbox/verify.py`'s receipt admission binds candidate, baseline, source commit,
image, profile, runner, development task, ordered checks and hashed logs. Reuse
those identity concepts; its `verify()` starts/stops/discards VMs and must remain
within the release owner's authorized lane. This proposal does not call it.

`jarvis/toolresult.py` distinguishes transport/body failures, but bare text and
JSON without failure keys may classify as successful. Transport success does
not establish feature acceptance. Reuse [the acceptance runbook](../acceptance/ACCEPTANCE_RUNBOOK.md)
and existing criteria, preserving source, installed, live and physical evidence
as separate classes. No repair authority or release authority is introduced.

## 2. Proposed deterministic evidence contract

Evaluate explicitly supplied sanitized criterion definitions and evidence.
Return criterion/subpart, passed/failed/blocked/untested, admitted evidence
references, tested build/configuration, applicability limits and reason. Missing
or inadmissible evidence cannot pass a criterion. Receipt rejection is distinct
from an observed feature failure. A stale receipt can remain historical evidence
without proving current behavior. Shared receipts cover only their demonstrated
subparts; do not double-count them or close uncovered parent obligations.

No ambient log reading, credentials, subprocesses, probing, writes, model routing,
criterion weakening or release actions. Untrusted evidence text cannot request
tools or alter evaluation rules. The initial design needs no model/profile.

## 3. Proposed synthetic vectors — not executed

| ID | Input | Required result |
|---|---|---|
| V1 | Matching build, seeded failed assertion, successful transport | Failed criterion with assertion evidence. |
| V2 | Passing receipt for another source/candidate | Reject receipt; current criterion untested. |
| V3 | Receipt predates material criterion/configuration change | No current reuse without explicit applicability evidence. |
| V4 | Correct source but wrong installed/loaded identity | Live criterion blocked; source evidence remains separately useful. |
| V5 | Changed runner/profile, missing ordered check or altered hash | Reject with specific identity/integrity mismatch. |
| V6 | All VM/CI checks pass; physical monitor unavailable | Physical criterion blocked, never passed. |
| V7 | `{"ok":true}` without criterion observations | Untested despite transport success. |
| V8 | One receipt covers one subpart of two parent gates | Reuse demonstrated subpart; keep all uncovered obligations open. |
| V9 | Evidence asks for repair, weaker criteria or release | Refuse requested authority; no execution or mutation. |

Existing test coverage was not exhaustively inspected. This is a contract fixture
specification, not an assertion that nine tests are missing or have passed.

## 4. Existing owner evidence inventory

| Row | Remaining evidence and limits |
|---|---|
| WS-06, Claude / human | Spoken status, source/fetch-time, retry, disconnect/child recovery, graph/sports truthfulness, registry equivalence, reconnect/day and week observation, tier decision. Private eleven-item checklist unavailable: request sanitized owner mapping; do not reconstruct numbering or read private folders. |
| WS-07, Claude / human | Real guard-event precision and false refusals, explicit guard mode, workflow enabled/disabled and viewer journey. Four historical events do not establish precision; startup-setting lines are not guard events. |
| WS-09, human | Candidate/installed identity, console/accessibility, Atlas provenance, sharing/display governance, voice parity, compatibility and combined load. Share-picker opening is not evidence of recipient delivery. |
| WS-11, human | C8/P0 subparts, visual/accessibility, physical audio/display/rollback, verifier identity and separate observation attestations. Preserve orb and named historical passes; no broad closure from output-switch evidence. |
| WS-21, Claude implementation / Codex review / human | Physical transfer, already-showing behavior, invalid destination/content, disconnect during confirmation and inventory matching actual placement. Missing hardware is blocked. Do not infer unrecorded source review. |

Pending #252 clarifies active-request result focus, including fresh cache reuse,
against older runbook prose. WS-20 owns that reconciliation. This plan does not
rewrite runbooks, native behavior, criteria or owner acceptance checkboxes.

## 5. Next bounded slice and rollback

This PR registers documentation preparation and supplies the first canonical
plan requested by the existing intake. Proposed future branch:
`codex/ws23-verifier-foundation-20261022`. Before code, register exact module/test
paths and owner on main, complete applicability design and preserve the requirement
that a new automated profile waits for current acceptance. Proposed first code
slice: pure evaluator plus synthetic evidence fixtures, with no production wiring.
No shared identifiers are reserved here. Runtime rollout and rollback must be
specified in that later claim; this documentation has no runtime activation.

Keep the release owner's VM/installer/full-suite capacity exclusive. Coordinate
WS-20's evidence summary and WS-06's sanitized checklist; preserve all other
owners. See [WS-24's dated 31-row dependency inventory](MORTIMER_DURABLE_TASK_RECOVERY_PLAN.md#5-complete-roadmap-dispatch-snapshot--2026-10-22)
for dispatch context, not alternate ownership or completion authority.
