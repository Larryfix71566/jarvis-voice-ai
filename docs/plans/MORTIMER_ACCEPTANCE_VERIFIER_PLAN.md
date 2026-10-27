# Acceptance Verifier within Systems — WS-23

**Current integration receipt — 2026-10-27:** This document's authored candidate/history is included in a new aggregate **draft, not ready to merge**, at Larry's request. See the [exact source manifest](../roadmap-log/2026-10-27-unmerged-integration.md). Historical test/after-merge statements below retain their source/date; no new product acceptance or runtime activation is claimed. Independent aggregate review remains pending.


**Status:** LANDED VIA THIS PR, source-only after-merge state: unused pure
evidence contract on `codex/ws23-verifier-foundation-20261022`, implemented after
claim #267 merged as `4c02709`. The candidate passes 25 focused offline unit
tests; exact-source independent review and publication CI are separate integration
gates. No runner, automated profile, production wiring or product acceptance is
delivered. Current acceptance/access gates and fresh claims still precede real
receipt adapters or runtime rollout. Earlier preparation and section 6's claim
are preserved as dated history; section 7 records this implementation's limits.

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

## 6. Offline evidence-contract claim — 2026-10-22

### Dispatch, references and exact locks

Larry's expanded all-current-and-future-roadmap direction permits a bounded
offline engineering increment, not a release decision or acceptance waiver.
This documentation registration uses `docs/ws23-evidence-contract-claim-20261022`
from main `ab31dfa8ddf58ad0583afcb25dffd18afbee5765`. Only future branch
`codex/ws23-verifier-foundation-20261022` is the source claim, effective after
registration lands on main. No implementation precedes that gate.

Read-only preparation at `cd8d809e003238738899d903ae24d95667206055` inspected
repository rules, current scopes, this plan, WS-24 section 8,
`jarvis/toolresult.py` and `sandbox/verify.py`'s receipt boundary. The new paths
remain absent at the registration baseline. The existing transport/body
classifier is not a criterion evaluator: bare successful data cannot prove a
feature. Verifier receipts bind candidate, baseline, source, image, profile,
runner, task, ordered checks and log hashes. Those are useful identity concepts,
not permission to call the verifier or replace its real file/hash checks.

Only new `jarvis/acceptance_evidence.py` and
`tests/unit/test_acceptance_evidence.py` are code locks, with inline synthetic
fixtures. Documentation is limited to this canonical plan, the WS-23 roadmap
block and `docs/roadmap-log/2026-10-22-ws-23-evidence-foundation.md`.

No edits to `sandbox/**`, existing transport classification, DB/runlog/notices,
Systems prompts/tools, bot/admin, providers, configuration, scripts, native
code, shared conftest/tests, CI, runbooks/criteria or other owners' plans.
No production importer, endpoint, CLI, startup hook or automated profile invokes
the module. No WS-24 import or source coupling. No schema, migration, config key,
protocol, service, port, tool grant or persisted-report identifier is reserved.
Rollback is reverting the isolated unused module/tests and recording that state;
there is no active behavior, persisted state or configuration to undo.

### Minimal pure contract

Implement `evaluate_evidence(criterion, evidence, expected_context)` with
standard-library immutable typed records. Return a bounded input rejection or
an evaluation containing explicit subpart statuses (`passed`, `failed`,
`blocked`, `untested`), admitted/rejected/historical evidence references,
tested identity/configuration, applicability limits and stable reasons.
There is no overall `accepted` output, product percentage, release verdict or
instruction to execute a check. No parent obligation closes automatically.

1. Caller-supplied criterion definitions contain ID/revision digest, required
   subparts/observations, evidence classes, identity requirements and prerequisite
   state. Evidence cannot add/remove obligations or waive those rules. Use
   bounded opaque IDs/digests and fixed documented finite collection limits;
   reject malformed types, booleans used as numeric values, unknown fields/enums,
   empty obligation sets and oversize records. No arbitrary paths, raw log,
   goal/prompt, secret or private payload is part of this contract.
2. Match every required source/candidate/configuration/criterion identity and,
   where required by the evidence class, baseline, profile, runner, image and
   development-task identity. Missing or different required bindings reject
   current applicability; keep a stale reference only as historical evidence.
   No implicit newest-receipt rule, recency threshold, ancestry inference,
   content equivalence or generic applicability waiver. Cross-revision proof
   adapters are outside this first slice.
3. Compare required ordered check IDs/arguments and expected manifest digests
   with the supplied metadata. Omission, reordering, substitution or mismatch
   rejects the receipt; an evidence-provided `integrity_verified` assertion is
   not authority. This pure function cannot authenticate the caller or evidence,
   read logs, or prove hashes of bytes it never sees. Its classifications are
   conditional on host-established inputs. Real acquisition, integrity checking
   and trust establishment remain later integration obligations.
4. Classify each source/synthetic subpart in this exact order, retaining all
   evidence dispositions and unmet prerequisites alongside the primary status:
   - First admit observations against the criterion's identity/integrity rules.
     Rejected or conflicting evidence is not a feature failure and cannot pass.
   - If any applicable admitted observation demonstrates a required assertion
     failed, return `failed` for that subpart **even if a prerequisite is unknown
     or unmet**, or another applicable receipt passes. Preserve the failure and
     prerequisite reasons; do not hide the observed failure behind `blocked`.
   - Otherwise an unknown/unmet prerequisite or unsupported required evidence
     class returns `blocked`. A positive observation cannot override that block.
   - Otherwise missing applicable observations returns `untested`.
   - Only established prerequisites and passing observations for every required
     assertion yield `passed` for that demonstrated source/synthetic subpart.
   Transport `ok:true`, exit zero or green CI without criterion observations
   remains insufficient. Receipt admission rejection is separate from failure
   of an observed product assertion; preserve that distinction in reasons.
5. Identical receipt ID/content deduplicates; different content under the same
   identity is rejected as a conflict, never last-write-wins. Other independently
   applicable failed evidence still follows the failure-first rule. Reordering
   inputs cannot erase a failure. Shared receipts cover only demonstrated
   subparts; list uncovered obligations rather than counting references as extra
   coverage or accepting their parents.
6. Required installed/loaded-build, hardware, elapsed-observation and human
   judgment subparts cannot receive an automatic pass in this initial slice.
   They remain `blocked` with a specific unsupported/prerequisite reason;
   separate source subparts retain their own applicable failures/passes.
   Human-attestation references may remain unevaluated provenance, not converted
   to observations by this module. Actual attestation/installed-state admission
   belongs to a later owner-coordinated adapter. No physical absence becomes
   not-applicable, skipped-as-pass or an empty successful obligation set.
7. Import/evaluation has no ambient clock, environment, filesystem, network,
   subprocess, database, model, logging, generated-ID or callback I/O. All facts
   are explicit data; outputs are immutable and inputs unchanged. Never call
   `Verifier.verify()`, `Verifier.receipt()`, a collector or provider probe.
   No scheduling, persistence, notification, repair, approval, criterion edit,
   model route or acceptance-checkbox mutation can result from evaluation.

### Focused synthetic vectors — not executed by this registration

The original V1–V9 remain obligations. Extend their explicit boundaries with:

| Vector | Required result |
|---|---|
| V1a | Matching failed assertion plus unknown/unmet prerequisite and passing transport remains `failed`; retain the prerequisite reason. |
| V1b | Matching positive observations plus unknown/unmet prerequisite are `blocked`; no positive override. |
| V2/V3 | Wrong source/candidate/configuration/criterion revision rejects current proof; with established prerequisites and no applicable observations, source subpart stays `untested`. Generic waiver text/boolean changes nothing. |
| V4/V6 | Source observations remain separately useful; wrong/unknown loaded identity, missing hardware or synthetic human-attestation text cannot pass the live/human subpart. |
| V5 | Changed required runner/profile/image/task, omitted/reordered check, wrong digest or missing expected integrity metadata produces a specific rejection, not a fabricated feature failure. |
| V7 | Bare successful tool/transport/exit status without assertion observations stays `untested` when prerequisites are established. |
| V8 | One receipt reused for one subpart of two parent gates demonstrates only that subpart; duplicate references add no coverage, uncovered obligations remain open. |
| V9 | Evidence requesting tools, repair, criterion weakening or release cannot execute anything or change evaluation rules. |
| V10 | Invalid types/enums/digests, empty obligations, conflicting duplicate IDs and oversize collections reject safely without input mutation. |
| V11 | Independent applicable pass/fail observations retain the failure across input permutations; a conflicting duplicate does not erase a separate admitted failure. |
| V12 | Guard import/evaluation against ambient access; a deliberate prohibited-access negative control fails. No real verifier, network/process or live operation. |

Run only focused offline tests and mandatory publication checks for the future
source slice; no competing full-suite/VM campaign. Independent exact-source
review must inspect applicability, failure precedence, spoofed metadata,
uncovered obligations and immutability. Record performed versus proposed checks
separately. Pure fixture passes prove the contract's behavior, not the truth of
real receipts or any physical/live acceptance.

### Dependencies, deficiencies and next handoff

WS-20 retains canonical runbook/criteria reconciliation and roadmap summaries.
WS-17 retains release/installer/native/full-suite/VM coordination; WS-28 retains
sandbox cleanup. WS-05/03 retain provider, source-policy and creator boundaries.
WS-22 retains investigation stages. WS-24's claimed transition module is not a
durable store or delivery implementation: reuse its distinction between task,
attempt, run, result and notice references conceptually, with no import, shared
state or lifecycle mutation. Later persisted verifier work needs a fresh claim
and the actual lifecycle/receipt adapters, not a second task store.

Existing test coverage was not exhaustively audited, so these vectors are not
a claim that twelve tests are missing or have passed. No real receipt adapter
authenticates these proposed inputs yet. Exact finite field bounds and typed
denial enums must be documented with the implementation and reviewed; they must
not silently weaken the rules above. WS-06's private eleven-item checklist still
needs a sanitized owner-supplied mapping; do not reconstruct numbering or read
private owner folders. Hardware, installed identity and observation remain
external evidence. No installed state or model capability was remeasured.

All four WS-23 acceptance boxes remain open in this registration. Current
acceptance-first criteria and privacy/access gates still apply before a new
automated profile or runtime rollout. After this exact claim lands on main,
implement only the named unused module/tests, obtain independent review and
publication CI, and return the immutable candidate to the sole serial merge
coordinator. No source creation, production operation or acceptance follows
from publishing this documentation alone.

## 7. Unused source implementation — 2026-10-23 UTC

Codex implemented the two registered files after #267 landed as
`4c02709204b4f3e5330311b58e0406d2e47444e3`. The retained dispatcher first recorded
implementation start in `9eb6c96`; no other source path or owner is acquired.
The module is standard-library-only and has no production caller, automatic
profile, store, WS-24 import or effect. Its records and results are frozen typed
dataclasses with tuple members. Only exact record types are admitted; mappings,
subclasses, generators and unknown schema versions are refused, not interpreted
as trusted policy.

### Concrete input and result bounds

Schema version is integer 1 (a boolean is not an integer version here). Opaque
IDs are 1–80 ASCII letters/digits or `_.:-`; paths, whitespace and arbitrary
payload text are not accepted. SHA-256 commitments are 64 lowercase hex digits;
source commits allow 40 or 64 lowercase hex digits. Fixed finite limits are:
32 subparts per criterion, 64 assertions and 16 prerequisites per subpart,
32 checks per manifest, 128 receipts per evaluation, 256 observations per
receipt, and at most one binding for each of the ten defined binding keys.
These are input resource bounds, not user budgets or new configuration keys.

Criterion/subpart/context definitions are caller-owned. Every subpart requires
source, candidate and configuration bindings; additional baseline/image/profile/
runner/development-task bindings can be required explicitly. Supported source
and synthetic subparts require a nonempty ordered check manifest. The argument
field is an SHA-256 commitment to check arguments, not an executable argv or a
path to read; log digests likewise compare caller-supplied commitments only.
This does not authenticate their origin or verify actual log bytes.

The public enums make supported evidence classes, prerequisite states,
observation outcomes, validation codes and reasons explicit. Outcomes are only
`passed` or `failed`; final subpart statuses are only `passed`, `failed`,
`blocked`, `untested`. There is no overall status or accepted output. Every
evaluation carries fixed applicability limits describing the host-input trust
assumption, metadata-only comparison and lack of human/parent acceptance.
Installed/live/hardware/observation/human classes remain unsupported and blocked,
even when a supplied record claims a pass or failure. Separate source subparts
retain their own evidence. The module never reads actual installed state.

Malformed top-level criterion/context/sequence input gives a bounded typed
rejection. Malformed receipts are individually rejected so they cannot erase an
unrelated admitted failure; a malformed receipt also prevents admission of a
clean copy under that same ID. Identical records deduplicate. Conflicting records
under one ID are rejected rather than choosing the latest. Wrong criterion IDs
are rejected; different revisions or required binding values remain historical
references, never current proof. Unknown observation IDs cannot extend the
criterion. Ordered checks and argument/log commitments must match exactly.

For supported subparts, an admitted observed failure always wins over positive
observations and unknown/unmet prerequisites, retaining those prerequisite
reasons. Without failure, unsupported/missing expected authority bindings or
unmet/unknown prerequisites block positive evidence. Otherwise uncovered
assertions remain untested; all required observed passes yield only that
demonstrated subpart's pass. Input receipt order cannot erase an independent
failure. Admitted references expose their tested binding metadata; uncovered
assertions and rejected/historical dispositions remain explicit.

### Focused evidence and limitations

Executed on Python 3.12.13:
`python3.12 -m unittest discover -s tests/unit -p test_acceptance_evidence.py -v`.
All 25 test methods pass, including parameterized subcases for V1–V12. The tests
are standard-library `unittest` cases that the normal pytest job can also collect;
this local command does not load shared conftest or invoke unrelated runtime
fixtures. The default system Python lacks pytest; no dependency installation or
claim of a local pytest/full-suite pass is made. Required publication CI remains
separate.

Negative cases cover each required identity mismatch, stale revisions, missing
trusted bindings, altered/omitted/reordered check commitments, empty observations,
wrong evidence classes, unknown/malformed records, numeric booleans, collection
limits, input immutability and receipt permutations/conflicts. Source pass/fail
receipts cannot turn unsupported human/live subparts into automatic results.
Failure-plus-unknown/unmet-prerequisite cases remain failed; positive equivalents
remain blocked. Partial coverage and duplicate references leave uncovered
obligations open. A hostile object/string subclass cannot execute a callback
through record validation.

The import/evaluation guard preloads this source's bytes and standard-library
dependencies, then executes an isolated module with file, environment, network,
process, database, clock, generated-ID and logging entry points denied. The
actual evaluator passes; deliberate prohibited-access controls fail at the
guard. This tests the module's behavior, not a claim that Python's ordinary
source loader performs no file reads. No actual verifier, database, socket,
process or live model was invoked by these cases.

Strict roadmap, whitespace and preservation checks accompany the committed
candidate; exact review head and publication CI belong in their separate
receipts. Independent review has not yet occurred for this implementation.
Real evidence authenticity, real log integrity, installed build observation,
admitted receipt adapters and all four WS-23 acceptance checkboxes remain open.
No automated verification profile, WS-24 lifecycle coupling, physical test,
installation, source-policy/model change or release authority is introduced.
