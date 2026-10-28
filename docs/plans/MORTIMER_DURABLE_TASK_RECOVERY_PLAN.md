# Durable task ownership and restart recovery — WS-24

**Status:** Landed source-only through #270; documentation-only combined-main
verification landed via this PR, 2026-10-26. The isolated offline transition
evaluator and synthetic tests follow merged claim #263 on
`codex/ws24-recovery-foundation-20261022`. Kimi verified exact combined main
`5581d4f913d21cbc69a707905a9898780b4a1e3c` locally on macOS under Larry's
bounded dispatch; exact-head PR CI remains a separate publication receipt. No
recovery runtime, storage, activation or product acceptance is delivered.
Earlier dated preparation, historical publication failure and claim limitations
below remain evidence. Further storage/runtime implementation requires a fresh
scoped main-first claim and preserves product acceptance, owner coordination
and release gates.

## 1. Evidence and existing components

Source inspected: `c63ecce97108787c55ef55fad73d32236694cc65`. The inspection
read source; it did not execute application tests or inspect private runtime data.

| Component | Observed behavior | Reuse boundary |
|---|---|---|
| `jarvis/agents/delegate.py` | `active` and `orphaned` are session-local; exact pending-operation deduplication uses an in-memory map. Detached tasks survive voice interruption, with bounded teardown drain. | Preserve stop-command authority, existing deduplication and WS-17/WS-05 ownership. This is not durable restart scheduling. |
| `jarvis/runlog/store.py` | `reconcile_orphaned_runs()` changes older running rows to orphaned. Unknown tool outcomes are reconciliation receipts, not retry instructions. | Reuse run/attempt evidence; do not treat an orphaned run as permission to replay work. |
| `jarvis/notices.py` | `take_pending()` selects and marks notices delivered in one transaction before returning them to the client path. | Persistent outbox exists, but a crash after retrieval can precede user-visible delivery. Stable result identities and acknowledgment/deduplication need an explicit contract. |
| `jarvis/skill_requests.py` | Request UUID and canonical payload digest are owner-scoped; reservation uses a cross-process lock and atomic JSON. Developer run, request and sandbox job identities are distinct. | Reuse principles, not a second creator ledger. This is WS-03-owned code; no edits or generalization are authorized here. |
| Existing SQLite and WS-22 design | SQLite and run logging already own durable state; investigation has lifecycle requirements. | Reconcile [WS-22's existing plan](MORTIMER_EVIDENCE_WORKFLOW_IMPLEMENTATION_PLAN.md) before selecting storage or migration. No migration number reserved. |

These findings concern the inspected components, not an exhaustive assertion
that no other recovery mechanism exists. The next design pass must inventory
reminders, scheduled jobs, sandbox durability and delivery consumers before code.

## 2. Proposed contract and state transitions

One overall task owns its goal, source request, owner, completion/stopping
condition, next check, dependencies, blocker, authorization scope, attempt budget
and latest evidence. A task is not its individual agent run or sandbox job.
Persist only admitted data under existing privacy/retention rules; this proposal
does not authorize storing private prompts or credentials in new locations.

Proposed flow: persisted request -> eligible task -> exclusively claimed attempt
-> persisted outcome -> pending delivery -> acknowledged delivery. Cancellation,
expired/revoked authorization and exhausted retry budget prevent a new attempt.
Each transition must retain provenance and stable task/attempt/result identities.

An attempt claim requires a monotonically changing fencing token or equivalent
transactional exclusion. A stale worker cannot commit a new outcome or perform
another consequential action after ownership changes. The design must specify
the boundary between local exclusion and external systems' idempotency support;
it cannot promise exactly-once external execution without that support.

After restart, an uncertain consequential action enters reconciliation. Reuse a
provider receipt or authoritative readback when available. If its outcome cannot
be established, stop with an explicit unknown outcome; do not blindly retry.
Only still-authorized, known-safe work may resume within its recorded budget.

Delivery must use the existing notification path, stable result/notice identity
and consumer deduplication. Do not mark user-visible success merely because a
notice was selected or a transport call returned. Sensitive generic notices carry
no protected payload and resolve only to an authorized result view.

## 3. Synthetic fixture specification — proposed, not executed

| ID | Injected boundary | Required result |
|---|---|---|
| R1 | Restart after request persistence, before execution | Retain request, owner, dependencies and authorization; schedule one eligible attempt. |
| R2 | Two workers compete for one attempt | One owns the attempt; the other performs no effect. |
| R3 | Restart during an external action; outcome unknown | Reconcile or stop unknown; never infer failure and replay. |
| R4 | Old worker returns after a replacement claim | Fencing rejects stale result/action transitions. |
| R5 | Result persisted, process stops before delivery | Recover the same result identity without rerunning work. |
| R6 | Client receives result, acknowledgment is lost | Retry delivery using the same identity; consumer suppresses duplicate visible output. |
| R7 | Cancellation or approval expiry races with resume | No new action; preserve cancellation and exact authorization scope. |
| R8 | Retry budget exhausted | Explicit terminal stop, no session restart reset. |
| R9 | Duplicate/reordered source event | One task transition and relevant update; retain source provenance. |
| R10 | Protected result and generic reconnect notice | No sensitive content in generic notice; authorized view only. |

Use disposable state, fake clock, fake workers and fake providers. No real
network effects, production DB, credentials, launchd or VM jobs. These vectors
are requirements, not claims that existing tests are missing or newly passed.

## 4. Bounded next slice and ownership

First complete the existing-state/schema inventory and design review. Proposed
future branch: `codex/ws24-recovery-foundation-20261022`; it is not claimed by
this documentation registration. Before code, register exact paths, owner,
feature gate, rollback and any shared identifiers on main. A minimal first code
slice should evaluate a pure state-transition contract with synthetic fixtures;
production integration is a later claim.

WS-17 owns release, existing cancellation/weather/foreground paths and exclusive
VM/full-suite capacity. WS-05 owns provider and source/privacy semantics. WS-03
owns creator requests. Obtain explicit scoped coordination before editing any
of those paths. No parallel full suites or runtime repair is introduced here.

WS-22 investigation, WS-25 commitments and WS-26 event follow-through reuse this
task authority. WS-25 fixtures must distinguish user commitments from quoted
mail, preserve corrected-date provenance and stop reminders after cancellation.
WS-26 fixtures add relevance, quiet time, duplicate/reordered events and protected
notification checks. Their implementation owners remain unassigned.

## 5. Complete roadmap dispatch snapshot — 2026-10-22

This is a dated dependency inventory, not a second ownership authority. Main has
29 rows; pending phone #240 and REA #245 supply rows 30 and 31. Preserve their
existing drafts and canonical plans. Re-read main and the owners' current PRs
before work. No implementation owner is transferred by this table.

| Row | Retained actor | Current bounded next work / dependency |
|---|---|---|
| WS-01 | Codex / human acceptance | Frozen-candidate physical/live evidence; no new code gap established. |
| WS-02 | Codex provider owner | Installed subscription isolation/capability/billing evidence; preserve WS-05 coordination. |
| WS-03 | Existing Codex Skills owner | P0 correction and review on `codex/ws03-compatibility-p0-20261022`, #251; full acceptance remains separate. |
| WS-04 | Codex / human method decision | Preparation appendix and method decision; no token minting or activation. |
| WS-05 | Existing Codex provider and harness owners | #244 provider and #242 harness; owner reviews Claude #253 without duplicate test/runtime edits. |
| WS-06 | Claude / human acceptance | Published spoken/reconnect/registry evidence, tier decision and week observation; request sanitized mapping of unavailable private checklist. |
| WS-07 | Claude / human acceptance | Actual guard-event precision and guard-mode decision; workflow/viewer evidence on identified build. |
| WS-08 | Codex | Accepted scoped orb work; reuse, do not rebuild. |
| WS-09 | Human acceptance | Console/Atlas/accessibility/display/sharing evidence after eligible release; share-picker opening is not recipient delivery. |
| WS-10 | Human acceptance / existing memory owner | Eligible dedicated route, shadow isolation and first 20 actual decisions; preserve existing daily budgets and latency gates. |
| WS-11 | Human acceptance | C8/P0 coverage, hardware and observation; preserve accepted subparts and WS-17 dependency. |
| WS-12 | Claude | Accepted scoped CI work; newer WS-20 enforcement remains separate. |
| WS-13 | Claude | P2 session-eligibility preparation and owner-coordinated #254 reconciliation; P3 follows shared foundation. |
| WS-14 | Claude | Accepted bounded subscription probe; reuse. |
| WS-15 | Claude historical / WS-17 repairs | Accepted weather scope; remaining acceptance repairs stay with release owner. |
| WS-16 | Codex | Accepted protected capture; reuse. |
| WS-17 | Existing Codex release owner | Installed-state/recovery audit and eligible acceptance; exclusive installer, VM and full-suite work. |
| WS-18 | Claude | Accepted mid-speech output switch; does not close broader wake/echo/load gates. |
| WS-19 | Codex | Completed repository reconciliation scope; reuse. |
| WS-20 | Existing Codex roadmap owner | Frozen #252 closeout and #254 factual reconciliation; preserve #246/#247 additive histories. |
| WS-21 | Claude implementation / Codex review / human acceptance | Physical display transfer and confirmation cases; missing hardware remains blocked. |
| WS-22 | Codex intake; implementation unassigned | Existing investigation plan reconciles WS-24 task authority and WS-23 verification boundaries. |
| WS-23 | Codex preparation; runtime unassigned | Evidence-contract and checklist design; no repair/release authority or new automated profile. |
| WS-24 | Codex preparation; runtime unassigned | This plan's inventory, fencing, authorization and delivery contract; acceptance-first dependency retained. |
| WS-25 | Codex intake; implementation unassigned | Commitment fixture design only; depends on WS-24 and source authorization. |
| WS-26 | Codex intake; implementation unassigned | Event/relevance fixture design only; depends on WS-24 and, for commitments, WS-25. |
| WS-27 | Existing Codex enhancement planner | Existing enhancement/voice/local-model runbooks; no live benchmark, installation or model change. |
| WS-28 | Existing Codex cleanup/release coordination | Reconcile #254's public review findings before real cleanup; no private review-folder access. |
| WS-29 | Existing Codex consolidation planner | Preserve accepted direction; implementation waits on acceptance and WS-03; no overlapping Skills edits. |
| WS-30 (pending) | Existing Codex phone planner | #240 plan/review/decision dependencies; no phone implementation. |
| WS-31 (pending) | Existing Codex REA planner | #245 app-building plan/research, depends on #240; authorized feature recreation, not self-modification. |

Seven scoped rows above are complete: 08, 12, 14, 15, 16, 18, 19. The older
#246 snapshot of 7/31 closed, 15 partial and nine unimplemented is dated evidence,
not a newly recalculated completion estimate. 7/31 is about 23% of rows, never
weighted code completion; unknown denominators remain unknown.

### Owner-reported operational corrections

The release owner's reconnected read-only audit, relayed through the WS-20 owner,
reports development checkout and installed bundle at `c63ecce`, with original
installation receipt dated 2026-10-22 18:09:49 UTC. No Mortimer app was running;
all six services and cleanup remained held after restoration failed. The audit
reports zero new ledger rows since the pre-install checkpoint using a stable
private-copy query; original DB bytes/mtime were unchanged and the temporary
copy removed. The ledger/app-state audit is complete, not pending. Restoration
diagnosis/recovery, working runtime/private routes and live acceptance remain
open. This is attributed owner evidence, not this task's host verification; it
does not establish loaded, available or accepted behavior. Later owner receipts
supersede this snapshot. No private ledger or local receipt is published here;
the historical roadmap Production line is unchanged.

The parent confirmed separate approval of the WS-03 correction push and bounded
review disclosure. Remote fetch now includes `e13fc89` on the original owner's
branch. Do not describe those actions as awaiting approval; final review and
publication evidence belong to that owner. No private review packet is copied.

Frozen continuation #246 at `028b44e11acff9dff3e00380e1624c8657ce545c` includes the
full testing plan v2 and sanitized compatibility handoff. REA #245 remains at
`b23b824ff15e450fae60535b38a95559eeda9396`. This plan does not mutate or supersede
their content. Their eventual integration must preserve newer WS-20 policy and
release evidence. No claim that every open branch is merged or conflict-free.

## 6. Mail preparation handoff for the retained Claude owner

This is a proposal for adoption into [the existing WS-13 plan](MORTIMER_MAIL_CALENDAR_BRIEF_PLAN.md),
not a competing mail plan or a WS-13 claim. Its section R and settled D1-D9 remain
authoritative. Eight focused source reads found injected mail test seams,
disabled/per-account not-configured handling and a concrete bot entry seam:
`run_session` does not explicitly receive the section R.10.5 transport/peer
eligibility record at the inspected call site. No repository-wide absence claim.

Proposed Claude branch `claude/ws13-p2-preparation-20261022`: docs claim first,
then pure `jarvis/bot/eligible_sessions.py` and focused offline tests only after
main registration. Host-supplied transport/peer identity, per-capability withdrawal,
disconnect removal and newest eligible recipient selection precede production
wiring. Native loopback plus negotiated capability qualifies; identical browser
hello data cannot grant eligibility. A newer browser must not displace the native
recipient; withdrawing calendar capability must preserve display capability.

Follow-on, unexecuted vectors cover wrong request/session/generation, duplicate
or late responses, policy keys, hidden/visible event counts, overnight/DST/request
zones and multibyte truncation. Native wiring crosses WS-17; source-policy issuance
crosses WS-05; harness daily paths belong to #242/#253 and are untouched. No mail
or calendar access, credential changes, sending or calendar writes are authorized.
Current access was not probed; historical absence is not a current fact.

WS-20 is coordinating #254 factual wording with the release owner and Claude.
The formal M1-1 repeat and required Codex review remain distinct from prior
deployment statements. Do not duplicate that reconciliation or reopen D1-D9.

## 7. Execution limits and handoff

Three bounded read-only Codex preparation helpers completed auth/privacy,
verifier evidence and mail readiness; the dispatcher completed recovery mapping.
All fixture vectors above remain proposed. No new Claude call was made for this
dispatch. Existing authorized Claude Max work stays with its owners, without
API fallback, repeated probes or expanded tool access. Direct OpenAI/Anthropic
API execution remains excluded; other APIs retain existing eligibility, privacy
and cost gates. No new model selection, paid API, live benchmark, credential,
installation, merge or deployment is authorized by this plan.

On reconnection the complete available task inventory and empty archive had no
registered match for an earlier uncertain recovery-task launch. No duplicate was
created; the dispatcher completed the preparation here. Internal task IDs and
local tool receipts remain outside the repository. Runtime claims, source tests,
fresh installed-state audit and user/hardware acceptance remain outstanding.

## 8. Offline transition-contract claim — 2026-10-22

### Dispatch, ownership and existing-state decision

Larry requested completing and integrating all current and future roadmap work.
The dispatcher adopts one bounded offline foundation on inspected main
`29440804baf40292d84acbb0798646e67d0c510a`. The registration branch is
`docs/ws24-recovery-contract-claim-20261022`; only the future implementation branch
`codex/ws24-recovery-foundation-20261022` is the source claim. No code precedes
main registration. This is an engineering increment within that dispatch, not a
new product choice or permission to operate a running service.

The additional read-only inventory covers `jarvis/db.py`, `runlog/store.py`,
`agents/delegate.py`, `skill_requests.py`, `notices.py`, reminder logic and its
bot/sidecar consumers, `sandbox/session.py`/`durable.py`, workflows, launchd jobs
and WS-22 plan sections5–6. No private DB, logs, credentials or live process was
read. No application tests ran for the inventory.

- Agent runs are attempts, not overall tasks. Existing action claims use
  insert-once SQLite transactions; their status updater is not a worker fence.
  Preserve this ledger as the domain effect authority, never infer replay
  permission from orphaning or failure.
- Creator and sandbox journals already distinguish queued work, cancellation and
  uncertain publication. Keep their separate identities and authorities. Calling
  sandbox resume can operate VMs; it is outside this claim.
- Notices are marked delivered before greeting rendering; reminders separately
  track context delivery and notification posting. None proves user-visible
  acknowledgment. Do not replace these components with a second outbox or queue.
- WS-22 supplies the shared lifecycle vocabulary and expected-version/attempt/
  lease concepts. Investigation stages remain WS-22's concern. WS-22/25/26 will
  reuse this contract and later one overall-task authority in existing SQLite.

The first slice therefore introduces **no store, scheduler, migration, config
key, port, service label, protocol or persisted report identifier**. Migration
0035 remains mail-reserved; a future storage claim must freshly reserve its own
number and define retention/schema before any code. No migration is reserved here.

### Exact locks and rollback

Only `jarvis/task_recovery.py` and `tests/unit/test_task_recovery.py` are new code
paths, with inline synthetic fixtures. Documentation is limited to this existing
canonical plan, the WS-24 roadmap block and
`docs/roadmap-log/2026-10-22-ws-24-recovery-foundation.md`.

No edits to DB, runlog, notices, delegate, creator, storage context, bot/admin,
sandbox, provider/auth/model/configuration, scripts, native code, WS-22 plan or
other owners' tests. These are read-only references, not acquired locks. No
production importer, startup hook, CLI or public endpoint invokes the module.
Rollback is reverting the isolated unused module/tests and recording that state;
there is no persisted state, configuration or deployed behavior to undo.

### Deterministic contract

Implement `evaluate_transition(snapshot, event, context)` as a standard-library
pure function returning a typed rejection with a bounded reason or an immutable
proposed next snapshot and expected old record version. IDs, time, authority,
lease/fence and evidence are caller-supplied. No clocks, environment, files,
network, processes, databases, generated IDs, timers or effect callbacks are read
or invoked, including at import.

1. Distinguish bounded task/request/owner/attempt/run/domain-job/result/notice
   references and digests. Reject malformed types and oversized collections;
   never coerce arbitrary paths or content into evidence. Initial snapshots
   contain synthetic metadata, not retained goal text, prompts or credentials.
2. Reuse task statuses `queued`, `running`, `blocked`, `cancelling`, `succeeded`,
   `partial`, `failed`, `cancelled`, `interrupted`; keep attempt and delivery
   states separate. Terminal attempt data stays immutable; retry links a new
   attempt. Same-event replay is a bounded no-op; changed request reuse conflicts.
3. Require expected record version and current attempt/fence for mutations;
   increment version on accepted transitions. Reject stale callbacks. The output
   is a CAS precondition, **not cross-process atomic exclusion**. Future storage
   must atomically enforce it with the actual domain action authority.
4. Starting/resuming requires fresh host-established owner/scope/expiry and
   explicit remaining budget. Missing, revoked, expired or mismatched authority
   refuses. These inputs are not signed credentials and create no new approval
   mechanism. No retry-count, spend or lease-duration default is invented.
5. Expired/missing lease or orphaned run yields interruption/reconciliation,
   not automatic requeue. Unknown/unresolved action outcomes block replacement
   actions. Only an explicit matching authoritative result can resolve uncertainty;
   absence of a receipt is not evidence of failure. A completed action prevents
   duplicate execution even when its run is orphaned.
6. Cancellation/timeout prevents new dispatch immediately. In-flight work stays
   `cancelling` until termination is confirmed; unknown cleanup cannot be called
   complete. Late success may be retained as evidence without reopening authority
   or a cancelled task. Restart never resets attempt budget or stopping criteria.
7. Saved-result evidence reuses the same result identity rather than recomputing
   for delivery. Posting, transport success or legacy `delivered_at` alone is not
   acknowledgment. Lost/unknown acknowledgment preserves result/notice identity
   for later consumer deduplication. The function cannot enqueue or send anything.

### Proposed focused checks — not yet executed

- Authorized queued attempt, duplicate replay and changed-request conflict.
- Two proposals expose CAS expectations; applying a stale proposal to an advanced
  snapshot rejects it. This does not claim a real worker-race test.
- Orphan/unknown external outcome refuses replay; missing receipt and timeout do
  not become retry permission. Wrong owner/action/task/digest cannot reconcile.
- Old fence/attempt/version rejects callbacks; terminal attempt cannot be rewritten.
- Cancellation/expiry before start refuses; in-flight cancellation waits for stop
  proof. Unknown cleanup remains unresolved; cancelled work cannot resume.
- Attempt exhaustion survives fresh evaluation of the same serialized fixture.
- Saved result needs no recomputation; repeated/lost acknowledgment keeps stable
  identity and legacy delivery flags remain unconfirmed.
- Invalid type/enum/size/inconsistent states fail closed without input mutation;
  provider text cannot alter authority, budgets or transition rules.
- Import/evaluation deny ambient file/network/subprocess/environment access.

Only focused offline tests and mandatory publication checks run for this slice.
No competing full-suite or VM campaign. Review exact source independently and
verify publication CI before serial integration. Real persistence, cross-process
SQLite fencing, restart durability, consumers, delivery deduplication and all four
WS-24 acceptance checkboxes remain unimplemented/unaccepted by this increment.
WS-17 retains exclusive release/VM/full-suite coordination; WS-03/05 keep their
creator, provider and source-policy boundaries. Later integration needs fresh
scoped claims and the existing privacy/access/release decisions.


### 2026-10-22 — Offline foundation implemented locally

Claim #263 merged at `cd8d809e003238738899d903ae24d95667206055` before
source work on `codex/ws24-recovery-foundation-20261022`. The isolated new
`jarvis/task_recovery.py` implements the section 8 proposal contract; its only
imports are standard-library annotations, dataclasses, enums and regular
expressions. No production code imports it. The WS-22 task status vocabulary
is retained; this slice implements start, interruption, definitive outcome
reconciliation, cancellation/timeout, stop confirmation, stable notice binding,
unknown delivery and acknowledgment. It does not implement every future
workflow, a task store, a scheduler, or an adapter to a domain service.

Engineering choices within the registered scope:

- Frozen dataclasses and tuples carry bounded synthetic identities/digests;
  input validation rejects unknown controls, malformed types and inconsistent
  histories. IDs are ASCII tokens up to 128 characters, digests are lowercase
  SHA-256-shaped values, and each retained attempt/receipt history is capped at
  64 entries. A full history refuses further attempts rather than discarding
  evidence. These are resource bounds, not default retry or spend allowances.
- Callers supply nonnegative integer time in one consistent unit, explicit
  remaining attempt/unit budgets, reservations, deadlines and lease expiries.
  Zero-unit work is permitted only as an explicit reservation and still consumes
  one attempt. Reservations are conservative metadata; no actual billing or
  refund policy is implemented. Authority must have been checked at the exact
  supplied evaluation time and bind task/request digest/owner/scope.
- The latest exact event alone provides bounded no-op replay. Changed payloads
  conflict; older callbacks fail version/attempt/fence preconditions. A replay
  proposal is explicitly marked and grants no new dispatch. The future caller
  must enforce atomic CAS and honor that no-op marker. Terminal attempts stay
  immutable; later definitive evidence lives in a separate receipt tuple.
- Only a matching host-verified completed or definitively-not-executed receipt
  resolves uncertainty. A missing receipt cannot permit replacement work.
  Completed results forbid recomputation. Cancellation of running/orphaned
  work waits for host-confirmed termination, including cleanup, recorded separately from action outcomes; late results
  never reopen a cancelled task.
- Host-supplied authority, authoritative receipts, stop confirmation and actual
  acknowledgment are trusted inputs that future adapters must verify. They are
  not signed credentials or newly granted permissions. A posting/transport/legacy
  delivery flag must never be mapped to acknowledged-notice evidence.

Executed locally: `PYTHONPATH=. python3 tests/unit/test_task_recovery.py -v`
passes 31 synthetic stdlib unittest cases. These cover the section 8 proposed
checks, including stale competing proposals (not an actual race), persisted-shape
round-trip of a synthetic fixture (not database durability), bounded history,
late result/cancellation behavior, missing/wrong receipts, exact notice/result
identity and malformed inputs. Module execution from preloaded source and
evaluation are exercised with ambient file, environment, network, process and
clock access denied; Python's initial source loading is outside that guard.

Independent review and publication CI remain pending with the coordinator.
No full suite, VM campaign, external model/API call, production state access,
push, merge, installation or activation occurred in this worker's slice.
All four WS-24 acceptance checkboxes remain open. Existing status versus installed
source distinctions and other owners' scope are unchanged.


### 2026-10-22 — Publication lifecycle correction

Independent review identified that an active `review` roadmap status would become
stale when the source branch merged. Under roadmap rule 0.10, the WS-24 row now
records **landed via this PR (after-merge source-only state)**. This describes
the proposed merge result; it is not evidence that publication or merge already
happened. Exact-source independent review and publication CI remain pre-integration
gates. This correction closes no acceptance checkbox and grants no persistence,
runtime, storage, deployment or further source scope. A future increment needs
its own main-first claim. Historical local test evidence above is unchanged.

Independent review also found that a restored cancelled snapshot could omit its
stop-confirmation marker and still accept a replay or late receipt. The validator
now requires a cancelled task with an attempt to retain matching stop evidence,
and every terminal `stopped` attempt to retain its corresponding marker. One
new focused test exercises corrupted snapshots from both running and orphaned
paths, rejects replay/reconciliation after marker loss, and preserves valid late
results with retained evidence. The focused suite now passes 32 synthetic tests;
this source correction requires independent rereview before publication.


### 2026-10-26 — Kimi combined-main verification

Larry authorized Kimi to verify the merged WS-24 source read-only and record the
evidence without changing implementation or acceptance. Exact current main was
`5581d4f913d21cbc69a707905a9898780b4a1e3c`; the source worktree had no tracked
modifications after the run.

Local macOS results using the repository's existing Python 3.12 environment:

- WS-24 focused contract: 32 passes and 27 subtests.
- Complete unit suite: 7,085 passes, 11 skips and 29 subtests.
- Integration suite: 197 passes and four skips.
- Offline sub-agent evaluations: 13 passes.
- Detached-checkout policy tests: nine passes.
- Backend import smoke, roadmap checker (zero errors/zero warnings), latency
  budgets and locked-dependency frontend production build passed.

The historical #270 validation failure was one non-WS-24 worker-boundary case
that found `probe.db`; all four parameter cases pass locally at this main
revision. There are no changes to that test or its verification script between
WS-24 source `38b0fcd` and `5581d4f`, so this Mac result is not promoted into
proof that the historical Ubuntu failure is resolved. Exact-head PR validation
is a separate publication receipt.

Frontend installation reported three dependency vulnerabilities (two high, one
critical); no dependency audit or change was attempted. Existing deprecation
and Vite configuration warnings remained non-blocking.

This documentation-only increment adds no storage, runtime importer, activation
or acceptance evidence. All four WS-24 acceptance checkboxes remain open.
Future persistence/runtime work requires a fresh scoped claim; Codex retains
implementation ownership and Larry retains merge and acceptance authority.
