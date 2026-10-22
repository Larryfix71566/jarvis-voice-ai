# Durable task ownership and restart recovery — WS-24

**Status:** Proposed canonical preparation plan, 2026-10-22. This documentation
registration records completed source analysis and proposed contracts. No runtime
implementation, schema, activation or acceptance is delivered. The main-first
claim rule and acceptance-first dependency in [WS-24](../../ROADMAP.md#ws-24)
remain binding. Owner: Codex, documentation preparation only on
`docs/roadmap-preparation-claims-20261022` after registration lands.

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
