# ROADMAP.md history archive — 2026-11-10

History moved out of `ROADMAP.md` on 2026-11-10 under WS-33 so the roadmap stays well below the reader limit. Source: `ROADMAP.md` at `origin/main` commit `837bb04`. Each section below is moved verbatim; the heading above each piece names its origin and line range at that commit. These sections are history, not current status: §2 and the live gates in `ROADMAP.md` are authoritative.

## From ROADMAP.md New aggregate draft — 2026-10-27 UTC (lines 11–23 at 837bb04)

## New aggregate draft — 2026-10-27 UTC

Larry requested a new PR for all remaining unmerged work after #275/#276/#277
landed. Codex assembles the identified current candidates on
`integration/unmerged-mortimer-20261027`, based on main `5581d4f` (2026-10-27
02:08:07 UTC). The [complete source manifest](docs/roadmap-log/2026-10-27-unmerged-integration.md)
separates included WS-03 documentation, unused WS-23 source and synthetic WS-30
source/dirty repairs from missing implementations, already adopted history and
explicitly deferred unknown/obsolete refs. All original authors/owners/scopes and
acceptance checks are retained. This draft is not approval to merge or acceptance
of unfinished source; independent aggregate and WS-30 oracle review remain open.
No implementation of the missing adapter, fixture repair or NR1 is fabricated.


## From ROADMAP.md Current source reconciliation — 2026-10-27 UTC (lines 24–91 at 837bb04)

## Current source reconciliation — 2026-10-27 UTC

The conflict-resolution refresh fetched `origin/main` at
`6f7c58ecd832782debc28c52e2eeb60865292c1d` (commit time 2026-10-27 01:56:13 UTC),
after #275 and #276 merged. PR #276's merge event is recorded at 01:56:14 UTC. The initial review baseline was `ae035de` (2026-10-23
20:20:18 UTC). This update records source and documentation evidence, not installed
behavior or new product acceptance. Larry dispatched the roadmap reconciliation;
WS-19 owns this documentation-only slice on `docs/local-roadmap-review-20261027`.
Every implementation owner, active scope and future acceptance gate is retained.

- **October 23 merges:** [#273](https://github.com/Larryfix71566/jarvis-voice-ai/pull/273)
  adopted WS-20 policy/acceptance handoff; [#272](https://github.com/Larryfix71566/jarvis-voice-ai/pull/272)
  registered the fixture-isolation lane; [#254](https://github.com/Larryfix71566/jarvis-voice-ai/pull/254)
  corrected mail status and recorded unresolved roadmap/cleanup review findings;
  [#269](https://github.com/Larryfix71566/jarvis-voice-ai/pull/269) registered REA NR1;
  [#270](https://github.com/Larryfix71566/jarvis-voice-ai/pull/270) landed the offline recovery contract;
  [#264](https://github.com/Larryfix71566/jarvis-voice-ai/pull/264) landed recommendation-only harness work;
  [#224](https://github.com/Larryfix71566/jarvis-voice-ai/pull/224) preserved older frozen-candidate verification;
  [#274](https://github.com/Larryfix71566/jarvis-voice-ai/pull/274) registered WS-32.
  These were already in the October 23 baseline; they are not new October 27 completions.
- **Document collision repaired:** the `e2cfcd6` → `204a741` (#264) roadmap diff
  reverted the historical Production receipt, WS-13's #254 corrections and
  WS-20's #271/#273 continuity/policy closeout. Restore those exact earlier
  entries before updating this dated status; label WS-13's older deployment
  assertion superseded by the later receipt without closing M1-1. The sole checkbox restoration is
  WS-20's already approved and verified checker-policy decision, backed by
  [#250's post-merge receipt](docs/roadmap-log/2026-10-22-ws-20-checker-enforcement.md#post-merge-enforcement-receipt--2026-10-22).
  All product/live acceptance checkboxes remain unchanged.
- **Merged reader repair:** [#275](https://github.com/Larryfix71566/jarvis-voice-ai/pull/275)
  merged as `51a3f567d6f1f0ad1dc085cdc1127260cefffb77` on 2026-10-27 at 01:47:56 UTC,
  from head `212ffde56a29dfa66908bf11567caf6dc1c25bbd`. Kimi authored the bounded
  reader repair; Codex corrected only WS-05's active-location metadata after
  Larry's dispatch. All five exact-head checks passed: [validation](https://github.com/Larryfix71566/jarvis-voice-ai/actions/runs/40433238770),
  [controller](https://github.com/Larryfix71566/jarvis-voice-ai/actions/runs/40433238832)
  and [knowledge base](https://github.com/Larryfix71566/jarvis-voice-ai/actions/runs/40433238813).
  Validation recorded 7,085 unit passes/11 skips/29 subtests, 197 integration
  passes/four skips and 13 offline evaluation passes, plus latency and frontend
  success. The original [WS-05 drift failure](https://github.com/Larryfix71566/jarvis-voice-ai/actions/runs/40020174071/job/120642366798)
  is historical and corrected. Independent review approved the metadata delta;
  that verdict does not review the original reader implementation or establish
  installation/live acceptance. This refresh preserves main's entire WS-05 and
  WS-32 blocks, including the registered future fixture lane and Kimi's records.
- **Unmerged owner work:** WS-03 branch `369057b` contains author-dispatch,
  timeout/recovery and historical-link documentation, with no adapter source
  applied. WS-23 branch `1b07fd8` contains the unused evidence-contract candidate
  (25 author-recorded unittest methods); independent review/publication remain
  pending. WS-30 committed candidate `954c8ee`, branch head `ffecab1`, has later
  uncommitted model/fixture edits; its earlier three-method synthetic result
  does not validate those newer bytes. Independent oracle review remains pending.
  These owner worktrees were inspected read-only and are excluded from main
  acceptance counts. WS-31 NR1 source and the WS-05 fixture repair were not found
  in the inspected claimed lanes; their main registrations remain active.
- **Validation limits:** #264 head `33c5441` has successful
  [publication workflows](https://github.com/Larryfix71566/jarvis-voice-ai/actions/runs/40012479064).
  #269 and #270 retain failed historical validation runs
  [39875353340](https://github.com/Larryfix71566/jarvis-voice-ai/actions/runs/39875353340)
  and [39875623174](https://github.com/Larryfix71566/jarvis-voice-ai/actions/runs/39875623174);
  their merges do not erase those failures. Final independent review and
  combined-main validation are not established by this documentation audit.
- **Installed state and authority:** the Production line is a historical
  successful receipt, independently read back for `b136a2a`, not a current
  loaded-build assertion. The later owner-attested development baseline is
  `c63ecce`, app closed and services/cleanup held, as recorded in the
  [joint plan](docs/plans/ROADMAP_JOINT_WORKING_PLAN.md#historical-continuity-adoption-and-current-authority--2026-10-22).
  This review performed no installation, service operation or live inference.
  Changing Mortimer's harness-controller model always requires Larry's explicit
  approval before the action; recommendation publication grants no such authority.


## From ROADMAP.md Historical acceptance source status — 2026-10-21 (lines 92–109 at 837bb04)

## Historical acceptance source status — 2026-10-21

The current WS-17 source milestone supersedes the older PR/review status prose
below. Provider/acceptance repairs #232/#233 and verifier correction #234 are
merged. Narrow native-version compatibility #235 is merged as `63c5cde`; frozen
source `e9c30b0` passed independent static review, all five exact-head CI checks
and all twelve original independent-profile checks. The
[source verification receipt](docs/acceptance/command-console/receipts/ws17-native291-source-verification-2026-10-21.md)
records exact fingerprints, coverage and limits. Original evidence, owners and
checkboxes are preserved; no live acceptance follows from source test totals.

The Production line is a historical documented receipt, not a current loaded
build attestation. Source identity, installed application/backend identity,
canonical host verification, eligible private routes and live/human/observation
criteria remain separate. Actual operational records stay local. The following
October18 inventory and reconciliation preserve their recorded source/date;
their old open-PR and missing-review statements are historical.


## From ROADMAP.md Acceptance clearance — priority inventory · 2026-10-18 (lines 110–157 at 837bb04)

## Acceptance clearance — priority inventory · 2026-10-18

Larry requested clearing the accumulated acceptance backlog first, with an
accurate status report and the shortest practical Mac sessions. The
[clearance plan and complete obligation inventory](docs/plans/ROADMAP_JOINT_WORKING_PLAN.md#9-acceptance-clearance--current-priority-2026-10-18)
are in the existing WS-20 plan; the [current status report](docs/acceptance/IMPLEMENTATION_STATUS.md)
and [release checklist](docs/acceptance/adaptive-interface/RELEASE_READINESS.md)
record then-current main `9ea27c7` after the documentation-only #218/#219 merges; the detailed inventory links pin initial source `28420af`. Existing ownership and acceptance
criteria remain binding. No checkbox is closed by this audit.

**Backlog counts:** 26 existing workstreams: 14 with open acceptance/decision
obligations, seven closed, five parked (WS-22–26). Their **112 unchecked workstream
bullets comprise 97 current aggregate obligations and 15 parked future criteria**, not 112 individual tests; eight extra MAR summary bullets duplicate
WS-05. The canonical release list has **23 open UI2 IDs** (02–20,22–25), with
24 compound P0 rows and five C8 umbrellas overlapping that coverage. Release
readiness is **34 unchecked / 19 checked** entries, correcting stale 30/19 prose.
New WS-27 documentation is excluded from these product counts. The 15 parked criteria restored by merged #219 are excluded from the 97-current-obligation clearance queue.

The 97 obligations classify by primary next need as **27 Larry UX/voice,
11 hardware, 16 system/sandbox, four automated regressions, one explicit code
prerequisite, 22 decisions/access/dependencies, 12 review/release/evidence and
four observation**. These categories are exclusive for counting only; many
obligations need several stages. The linked inventory lists every source bullet,
existing actor, dependency and required evidence. Do not sum overlapping matrices.

| Order | Next action and existing actor | Exit / estimated Larry time |
|---|---|---|
| 0 | Existing owners reconcile reusable receipts, repair/re-review #210 cleanup race/fingerprint under its own scope, obtain missing #216 exact-source review, freeze one candidate and complete required independent verification before a separately authorized deployment | One source/app/backend/config/hash manifest; safe verifier and deployment receipt. Setup/repair duration unknown; decisions 10–15 min estimate |
| 1 | Larry + Codex: fail-fast UI2-24/25 Recents/reuse | Correct two-result identity/fetchcounts, targeting/ambiguity/pin/close/reopen; 10–15 min estimate. Stop on failure |
| 2 | Larry + recorder:22/23, dependent 04/09/13, Atlas/graph/sharing/inbound/roadmap controls and matching P0/C8/ready Skills subparts | One evidence packet, no redundant parent replay; 35–50 min estimate |
| 3 | Larry + recorder: physical display transfer/recovery batch; owners automate contracts/security/compatibility and prepare audio/load checks | Display 20–30 min when hardware exists; audible checks 15–25 min estimate. Missing topologies stay blocked |
| 4 | Existing verifier/owners + Larry: rollback/loaded release proof, frozen daily-driver observations, final evidence reconciliation | Five-day release observation and separate WS-06 week retain their criteria; brief daily notes plus final decisions, no elapsed-only pass |

Rough total: **1.5–2.5 hours active Larry time**, plus daily observations,
excluding unresolved repairs/setup, special hardware and prerequisite features.
These are estimates, not a completion promise. Offline evidence mapping,
contract preparation and review can proceed independently in separate scopes;
no concurrent candidate mutation, competing audio tests or VM pruning.

Acceptance-first prioritizes the current release and scoped repairs needed to
accept it. Unbuilt/undecided onboarding, mail P2/P3, creator/model/private-route
and memory-stage prerequisites are **not runnable Larry chores or newly imposed
global release gates**. Keep them in their owning rows with explicit decisions.
Unavailable hardware may be deferred or accepted as a named limitation only
where the governing plan permits and Larry records it; never mark it passed.
New enhancement implementation remains subsequent, parked and freshly dispatched;
sandbox planning can proceed. See [the new end-of-roadmap plan](#ws-27).


## From ROADMAP.md Historical acceptance reconciliation — 2026-10-18 (lines 158–207 at 837bb04)

## Historical acceptance reconciliation — 2026-10-18

At its recorded date, this report superseded stale next-action/PR-status prose below while
preserving every receipt and existing owner's scope. Source is `9ea27c7`, not
proof of the installed build. [#218](https://github.com/Larryfix71566/jarvis-voice-ai/pull/218)
merged as `0b49706`; [#219](https://github.com/Larryfix71566/jarvis-voice-ai/pull/219)
merged as `9ea27c7` during publication. Their WS-17 update, enhancement intake,
four parked cards and WS-22 dependency note are preserved. Only this draft
[#220](https://github.com/Larryfix71566/jarvis-voice-ai/pull/220) remained open
at refresh. The incoming summary's stale claim that #210 was open is corrected
by its actual merged state below.

- **Accepted with bounded evidence:** WS-08/12/14/15/16/18 and WS-19 documentation
  are closed. Preserve the accepted AirPods switch, Skills B/C and Versions
  wording, orb, named historical displays and bounded 22/23 results; reuse only
  after candidate/scenario applicability review. No parent UI2 gate closes here.
- **Current release blocked by review/deployment:** #216 merged as `28420af`
  with five green checks; Claude review timed out without verdict. Independent
  exact-release verification, deployment/loaded identity and UI2-24/25 live
  retest remain open. #210 merged unchanged as `34e5d55`; its stale prune-plan
  deletion race and omitted runner fingerprint remain. No pruning/reclaim or
  affected sandbox creation until reviewed repair/safe environment proof.
- **Newer versus historical tests:** October 17 campaign's physical OCR failures
  remain failed at their source. Later [#216 scoped evidence](docs/roadmap-log/2026-10-17-ws-17-codex-roadmap-controls.md)
  records MortimerHost 563 tests, five skips, zero failures. Reconcile exact
  coverage/configuration before scheduling more OCR diagnosis; that local suite
  does not replace independent release verification or live acceptance.
- **Unimplemented/prerequisite-blocked:** WS-04 onboarding; WS-13 P2/P3 (P4/P5
  later); Skills creator/auth/VM/source/model/eval; WS-02/05 runtime/source/account
  and eligible confidential route; WS-10 staged real use; WS-06 eleven-check
  repository map. Feature-specific gates remain separate from runnable release
  checks; no provider/credential/activation or spend authority is created.
- **Shared source evidence:** #209 preserves the final campaign and validated
  twelve-check manifest; #207 superseded closed #172/#174. #205/#212 are merged;
  the prior source review recorded 117 synthetic mail tests passing. These
  historical checks do not establish a fresh deployed candidate.
- **Mail:** D1–D9 were answered October 10; do not reopen superseded questions.
  R.12 replaces August V1–V10. Preserve October 13 M1-2/3; repeat M1-1 only after
  fixed #212 deployment. Eight P2/P3 Mac rows wait implementation. Larry's actual
  deployed daily-report path remains unverified; do not create a duplicate report.
- **Hardware/observation:** external monitor unavailable October 17; mirrored/three-screen,
  portrait/non-Retina cases remain hardware-blocked until supplied or properly
  dispositioned. Five frozen-release days, separate native attestation and WS-06
  week remain elapsed evidence gates. UI2-14/15/16/17/18, enabled-feature gates,
  and checker-enforcement decision stay open.
- **Installed provenance:** latest successful deployment receipt in the roadmap
  is `575cc7b`, October 13 20:02 EDT. October 17 recorded dirty-source provenance; the
  production checkout revision alone cannot establish installed artifact identity.
  This documentation performs no new host probe or deployment.


## From ROADMAP.md Consolidated enhancement intake — Larry, 2026-10-17 (lines 208–293 at 837bb04)

## Consolidated enhancement intake — Larry, 2026-10-17

This records all eight requested additions as planning inputs, not permission to
implement, activate, contact anyone, or release. Codex owns this documentation
follow-up on `codex/roadmap-status-20261017` after #211 merged; new implementation owners,
branches and scope must be dispatched before code. Existing acceptance-first
priority remains in force. The next plans must build on the existing host,
SQLite, run logs, result identities and durable notification/outbox pathways.

1. **Baseline and existing acceptance — existing rows, no duplicate project.**
   Under WS-20 coordination and each current owner, record source commit,
   installed artifact/build/hash, running backend and relevant configuration
   separately. Inventory the actual daily report's mail, calendar, reminders
   and generated-summary behavior before defining gaps. Larry reports mail in
   the daily report as existing: preserve it and validate its actual deployed
   path; source-only P1 status does not establish the whole report's behavior.
   Correct stale documentation. Resolve known WS-17 Recents/reuse, WS-13
   preflight and host OCR verification blockers under their owners. Preserve
   accepted evidence; unavailable hardware, skips and unresolved prerequisites
   stay blocked or untested. **Pass condition:** each applicable requirement
   has tested-build evidence or an explicit blocker; implementation, automated
   verification, deployment and live acceptance remain separate.
2. **Acceptance Verifier — [WS-23](#ws-23).** Extend Systems with a bounded
   verification role, starting with a repeatable checklist using existing tools.
   Any new automated profile follows current acceptance; no new general reviewer.
3. **Durable task ownership and restart recovery — [WS-24](#ws-24).** Highest-value
   new foundation. Reconcile existing task/run/job identities before choosing
   the authoritative task record; do not build a competing scheduler or store.
4. **Commitment review — [WS-25](#ws-25).** Extend Scheduler and Librarian using
   WS-24; interpretation belongs to models, authority and durable timing to host code.
5. **Interactive Mail Reader — existing [WS-13](#ws-13) P5.** Preserve existing
   daily-report mail. First probe the latest eligible deployed build for
   interactive questions and implement only missing behavior: finding the
   message about an appointment, identifying requested actions, and tracing a
   report item to its supporting message. Require correct sender/thread/source
   attribution, bounded retrieval and explicit incomplete-result disclosure.
   Use only mail-reading tools; replies, mail mutation, calendar writes and
   general computer control are separate scopes. Existing private-route,
   protected-result and logging prerequisites still apply. Mail instructions
   are data, never permission. Optional model-written brief prose remains P4,
   separate from P5; calendar/report additions require a verified baseline gap.
   **Acceptance:** correct message and attribution; incomplete results disclosed;
   hostile mail cannot grant authority; private content cannot enter ordinary
   logs or unapproved outputs; current daily reporting remains intact without
   duplicate report items. Claude retains WS-13 and its canonical plan; this
   intake grants no P5 claim or model-route enablement.
6. **Relevant changes → useful follow-through — [WS-26](#ws-26).** Extend existing
   reminders/watchers/notifications through WS-24, initially only bounded cases.
7. **Evidence-backed investigation and handoff — existing [WS-22](#ws-22).**
   Preserve goals, requirements, evidence, decisions, contradictions, unknowns
   and next action; distinguish observations, inferences and unsupported claims.
   An eligible replacement model must resume accurately without rebuilding the
   conversation. Bind completion to verification and exact source/build identity;
   changed inputs invalidate affected conclusions. Read-only investigation
   never grants edit/publication authority. **Acceptance:** fresh-model resume,
   unknown unsupported claims, stale-evidence invalidation and a verification
   trace for every claimed requirement. Use its existing canonical plan, with
   WS-24 as the shared lifecycle dependency, rather than creating a second plan.
8. **Shared safeguards and rollout — apply to every increment.** Reuse task,
   run, result and notification identities. Host software enforces permissions,
   approval scope, privacy, ownership and budgets outside the model. Preserve
   voice responsiveness, transcript continuity, reading focus and stable result
   references through interruption/recovery. Select models by workload and
   privacy eligibility; changing models cannot replace persistence or proof.
   Before coding, specify owner, dependencies, schema reuse/change, reserved
   migration if needed, feature gate, rollback and acceptance tests. Keep
   operational diagnostics sufficient to investigate failures without sensitive
   payload logging. Each rollout separately records implementation, automated
   verification, deployment and live acceptance; none waives existing gates.

**Sequence:** baseline/current acceptance → WS-24 durable recovery → WS-25
commitments → missing WS-13 P5 capabilities and verified connector gaps → WS-26
follow-through → WS-22 investigation/handoffs. Apply the WS-23 checklist and
shared safeguards throughout. WS-23 automated-profile implementation remains a
later claimed increment. New development remains parked until the existing
acceptance priority and explicit dispatch permit it.

References: [architecture](docs/ARCHITECTURE.md),
[mail/calendar/brief canonical design](docs/plans/MORTIMER_MAIL_CALENDAR_BRIEF_PLAN.md),
[evidence-workflow canonical design](docs/plans/MORTIMER_EVIDENCE_WORKFLOW_IMPLEMENTATION_PLAN.md),
[merged acceptance receipt](docs/acceptance/command-console/receipts/acceptance-campaign-2026-10-17.md)
and [merged final evidence #209](https://github.com/Larryfix71566/jarvis-voice-ai/pull/209).

<details>
<summary>Historical navigation — October 7 (superseded handoffs; retained for context)</summary>


## From ROADMAP.md Operational summary — 2026-10-07 (lines 294–349 at 837bb04)

## Operational summary — 2026-10-07

Read this summary with the linked §2 blocks: implementation, deployment and acceptance are separate states. This is a navigation layer in the shared source, not a second tracker or an overall completion score. Production identity remains the receipt above.

**Recommended next milestone: everyday conversation and result handling (WS-17/21).** Keep both speakers' full words in one thread, open only the requested result, preserve reading focus, target Recents safely, reuse fresh results under the same identity, and transfer content to the intended screen with confirmed, truthful outcomes. Larry assigned Codex the remaining WS-17 implementation on 10-07; Claude retains WS-21. Required cross-review and Larry’s release/acceptance decisions remain. Finish CC7a.3 repairs/review, then CC7a.4 and the remaining exact-build UI2-22…25/display checks; dependent WS-09/11 checks follow. This recommendation makes no new assignment or approval.

| Priority / source | Implementation | Deployment | Next action, actor and blocker | Pass condition |
|---|---|---|---|---|
| [Conversation and results](#ws-17), [supporting display](#ws-21) | CC7a.1/1b/2/2b and #171 landed; #173 Recents needs repairs; CC7a.4 remains | Earlier increments/#171 deployed in `bde22bb`; Recents/reuse not included | **codex:** repair #173 and implement CC7a.4; **cross-reviewer:** review each exact head; **larry:** remaining current-build checks, then separately approve merge/deploy | Safe UUID targeting and ambiguity/stale handling; exact-build UI2-22…25 and physical transfer receipts with Larry's outcome |
| [Shared roadmap](#ws-20) | B1–B4, ten-PR log observation and #191 lifecycle/evidence publication complete | Documentation needs no app deployment | **claude:** integrate conflicting #172/#174; **codex:** keep this draft scoped and reuse merged #191 evidence; **larry:** review draft and later decide checker enforcement | Owners, gates and receipts retained; remaining owner corrections integrated; checker stays clean before strict-mode decision |
| [Model access](#ws-05), [subscription isolation](#ws-02) | #177 prerequisite repairs landed; runtime/workload acceptance open | Merged source does not establish enabled routing or a released candidate | **larry:** source/identity/test/account decisions; **claude:** #177 cross-review; **codex:** dependent verification after prerequisites | Exact runtime/workload/privacy/account receipts; eligible confidential route before synthetic confidential pilot; no paid fallback |
| [Local access](#ws-04), [Skills](#ws-03) | Auth foundations and Skills foundations landed; token onboarding not built | Bind guard deployed dormant; Skills Versions wording has a bounded `bde22bb` pass | **larry:** onboarding method; **codex:** fresh claim before provisioning; creator tests also need auth/source/model/VM readiness | Local preparation and activation verified separately; owner-scoped Skills and actual creator/quality gates pass |

### Larry decision queue

These are existing decisions from the linked blocks; recommendations/defaults are not answers. Record each choice in its owning row/plan under the protocol, and provide credentials only through the established vault/OS flow.

| Source | Decision needed | What it unlocks / evidence needed first |
|---|---|---|
| [WS-05](#ws-05), [WS-02](#ws-02) | Exact private `REPO_MAP` → Claude probe; operator-issued identity; native-readiness test repair assignment; manual/private/public-crawl source authority; account allowance, billing source and paid-overage settings | Source/runtime/workload acceptance and later rollout. An eligible catalog-confirmed confidential route is also required; the recorded 64-model catalog offers zero confidential models |
| [WS-04](#ws-04), [WS-03](#ws-03) | Local onboarding method: supervised setup, one-time CLI or Mac pairing; later credential preparation, local activation and remote binding as separate decisions | Fresh provisioning claim first; owner-authenticated Skills checks follow valid preparation/activation |
| [WS-13](#ws-13) | Revised read-only scope/isolation residuals; calendar backend/visibility; Secretary routing/privacy; account/vault access; schedule and permitted brief content | Claude reconciles the existing draft with the [merged #191 review handoff](https://github.com/Larryfix71566/jarvis-voice-ai/blob/b59ec9befbe32d77adebf07eabbee65e2da30f18/docs/roadmap-log/2026-10-06-ws-20-codex-review-handoff.md) before implementation approval; no mail/calendar feature is accepted |
| [WS-07](#ws-07) | Keep reply guard in `log` or approve `correct` | Genuine-event precision/false-refusal evidence; the four recorded events are insufficient |
| [WS-10](#ws-10) | Whether/when to approve each staged memory rollout | Actual classifier/route/stage baseline, WS-05 privacy prerequisites, daily-driver shadow and first 20 real decisions; synthetic/offline gates do not authorize enablement |
| [WS-20](#ws-20) | Whether the warn-only checker becomes a blocking gate | Warning period plus owned corrections, with #191 lifecycle cleanup already merged; no enforcement change in this draft |
| [WS-17/21](#ws-17), [WS-09](#ws-09)/[WS-11](#ws-11), [WS-01](#ws-01) | Acceptance of exact-build remaining outcomes; written hardware limitations if applicable; later candidate release | Recorded positive evidence for the remaining gates and required independent verification/rollback; implementation or green CI alone does not close acceptance |

### Acceptance checks — ready on the recorded build

“Ready” means no new feature increment is needed for these bounded checks. Identify the actual app/backend/configuration first; changed-build evidence needs an affected-case review. It grants no new live workload, activation or credential permission. Use the detailed checklist in each link for the full requirement.

| Source / actor | Remaining check and pass condition |
|---|---|
| [WS-17](#ws-17) · Larry, evidence recorder | Close the current conversation/arrival tail: protected turns, focus/scroll/size behavior, weather while reading, late background/image/card operations and supporting-display routing. Reuse [#191's `bde22bb` voice receipt](https://github.com/Larryfix71566/jarvis-voice-ai/blob/b59ec9befbe32d77adebf07eabbee65e2da30f18/docs/roadmap-log/2026-10-06-ws-20-codex-voice-acceptance-review.md): 17 ordered full accessible rows (7 user/10 Mortimer), five long replies, requested-result opening, research selection preservation and visible New notice. Those subchecks need no redundant run solely for documentation; full UI2-22/23 remain open |
| [WS-21](#ws-21) · Larry, supported by Codex | On the identified build with physical external monitor: confirmed voice/pointer transfer, already-showing, missing/stale/protected destination refusal and disconnect/failure restoration; correct content/screen and conversation stays on main. #191 observed only the built-in screen and proves no external transfer |
| [WS-18](#ws-18) · Larry | AirPods → Mac speaker → AirPods mid-answer: app stays up, at most a short audio gap, `audio output flowing` after each rebuild. Share this receipt with matching WS-11 audio requirements |
| [WS-01](#ws-01), [WS-03](#ws-03), [WS-09](#ws-09), [WS-11](#ws-11) · existing acceptance owners | Unaffected deployed baseline, physical display/sharing/accessibility and recovery tails can be selected from their checklists after candidate/runbook preparation. IDs, reading state, drafts, voice and privacy remain intact. Changed CC7a checks and auth/creator/provider gates wait below |
| [WS-06](#ws-06), [WS-07](#ws-07) · Larry / Claude | Existing repo-backed viewer, spoken-status and recovery cases where their required route/workload permission already exists; truthful tools/source, no invented completion, no unsolicited commands, retained reconnect state. Claude first supplies WS-06's missing eleven-item mapping before claiming full checklist closure; external probes/evals are prerequisite-gated |

### Acceptance checks — waiting on code, evidence or decisions

| Source / actor | Dependency before the remaining acceptance can pass |
|---|---|
| [WS-17](#ws-17) · Codex → cross-reviewer → Larry | #173 at `fb2e06f` has [recorded blocking findings](https://github.com/Larryfix71566/jarvis-voice-ai/pull/173#issuecomment-6027496087), not a formal GitHub review; it is mergeable at this refresh. Repair numbered-target races, lost ambiguity choices and Older Close access; cover the separately recorded comparison transport gap. Review repaired exact head, then separately merge/deploy and run Recents UI2-24. CC7a.4 implementation/review/deploy precedes UI2-25: weather → Atlanta → original gives two cards, fresh ≤15-minute reuse avoids fetch, stale refresh keeps identity |
| [WS-09](#ws-09), [WS-11](#ws-11), [WS-01](#ws-01) · Larry / Codex / verifier | Changed UI2-04/09/13 wait for WS-17 UI2-22…25; reconcile old answer-routing/deployment runbooks before frozen-candidate sign-off. Independent full-profile verification, rollback and frozen daily-driver observation remain separate release gates |
| [WS-04](#ws-04), [WS-03](#ws-03) · Larry / Codex | Onboarding decision → fresh claim → implementation/disposable proof → separately authorized live preparation/activation. Skills owner/run privacy, real offline VM, paired evaluation, lifecycle/activation and release gates additionally depend on source/model/budget readiness; SW-B/C and the Versions wording subcheck stay closed |
| [WS-05](#ws-05), [WS-02](#ws-02), [WS-10](#ws-10) · existing owners | Source authority, operator identity, runtime/test/account choices and eligible confidential route are blockers, not ordinary unrun tests. Complete exact workload/privacy/billing/release evidence under later authorization; memory then requires real staged decisions/benefit/budgets/privacy/rollback and Larry's approval |
| [WS-13](#ws-13) · Claude / Codex / Larry | Draft reconciliation and Larry's scope/backend/isolation/privacy/content decisions precede implementation; V1–V10 and release/Mac outcomes are future acceptance |
| [WS-06](#ws-06), [WS-07](#ws-07), [WS-20](#ws-20) · existing owners | Missing eleven-check mapping, external/runtime/evaluation prerequisites and guard precision/decision remain open. For roadmap closeout, #172/#174 owner integration remains pending; #191 lifecycle/evidence publication is merged as `b6f09f4`; strict checker enforcement and final Phase A/B live-evidence record still require their existing decisions/checks |

**Pending documentation overlap:** #174 already proposes WS-21 merged/deployed wording and WS-11's `bde22bb` reference; this draft reuses those narrow corrections and retains the newer checklists. #172/#174 integration remains Claude's. #191 merged separately as `b6f09f4` during claim preparation. Its WS-10/11 lifecycle corrections, completed documentation check and bounded evidence are retained; this draft links the existing receipts and closes no product gate. All PR states are a dated snapshot; refresh before landing. The detailed source blocks below remain the authority for individual scope and acceptance.

---

</details>


## From ROADMAP.md §1 Who is working on what — historical snapshot with 2026-10-28 handoffs (lines 433–490 at 837bb04)

### Who is working on what — historical snapshot with 2026-10-28 handoffs

Larry requested this assignment view and explicit Kimi coordination. It is a
snapshot of the existing rows and observed PR/local evidence. The two explicit
2026-10-28 handoffs below supersede their older assignments only after this
documentation claim lands; all other entries remain the historical snapshot. Accountable owners and scope locks remain
in the linked workstream blocks. A claimed branch proves an assignment, not that
an agent is currently running. “Unconfirmed” means no current execution receipt
was verified; an old handoff or test pass is not promoted into present activity.
System names identify contributors, not an inferred model or separate GitHub
person: these PRs use the shared `Larryfix71566` account, so attribution also uses
main's registered system/owner and each PR's recorded system/session.

Except WS-23 and WS-31, entries were checked on **2026-10-27 UTC**, with this refresh against main `6f7c58e` at 01:56:54 UTC,
current PR heads/comments and the read-only local inventory described above.
The evidence column names older source dates where relevant. Reviewers below are
separate from authors; “pending/unassigned” is not an approval.

| Work item | Accountable owner retained | Current worker / bounded assignment | Reviewer / acceptance authority | Verified activity and evidence |
|---|---|---|---|---|
| [WS-19](#ws-19) roadmap reconciliation | Codex | Codex: this documentation draft, including this ownership view | Independent Codex review approved the ownership view at `3d5a477`; this conflict-resolution refresh needs a new exact-head verdict. Larry's merge approval remains conditional | Active documentation evidenced by [#277](https://github.com/Larryfix71566/jarvis-voice-ai/pull/277); source/operational work excluded |
| [WS-05](#ws-05) model access / fixture isolation | Codex implementation and acceptance ownership | Kimi: bounded status/plan/log reconciliation #276 landed at `6f7c58e`; no further work without new dispatch. Codex: metadata fix landed in #275; registered future fixture implementation remains unconfirmed | #276 independent review not established here; fixture repair requires its own independent review; Larry retains model/release decisions | [#276](https://github.com/Larryfix71566/jarvis-voice-ai/pull/276) head `0991ba5` merged 01:56:14 UTC; this is a dated source-state snapshot. #272 registers the separate fixture branch; no repair source found in inspected lane |
| [WS-32](#ws-32) reader growth repair | Kimi | Kimi authored the #275 reader repair; Codex authored only its WS-05 metadata follow-up. Both landed via `51a3f56`; no new implementation activity verified | Independent metadata-delta review passed `212ffde`; an independent verdict on the original reader source is not established here. Larry retains live acceptance authority | [#275](https://github.com/Larryfix71566/jarvis-voice-ai/pull/275) merged 2026-10-27 01:47:56 UTC with all five checks green; main's WS-32 source record retained |
| [WS-03](#ws-03) Skills adapter | Codex | Codex owns review/apply/publication; Claude was dispatched bounded returned-patch authorship. Current author execution unconfirmed | Codex integration owner plus independent exact-source reviewer; no adapter-source verdict established | #261 claim; local `369057b` records October 23 timeout/recovery and no applied adapter source. Historical P0 #251/#258 and accepted gates retained |
| [WS-23](#ws-23) evidence contract | Codex implementation accountability; Kimi independent review | Source landed via #278. Kimi assigned review only; acknowledgment pending, execution unconfirmed | Kimi reviews Codex-authored source; Codex answers findings; Larry retains acceptance | Verified 2026-10-28 at main `765f6bca`; source equals `1b07fd8`. Future branch `kimi/ws23-evidence-contract-review-20261028`; [handoff receipt](docs/roadmap-log/2026-10-28-kimi-bounded-handoffs.md) |
| [WS-30](#ws-30) phone access / S0 | Codex accountable; WS-04/17/21/05/24 retain their runtime and release boundaries | GPT-6 Luna: documentation-only approval amendment on `docs/ws30-iphone-approval-20261028`; implementation owner reports S0 successor `codex/ws30-session-revocation-fence-20261028` at `5fec18e` with only the model/fixture paths | Implementation owner reports independent oracle acceptance for the exact model/fixture hashes; source PR/CI and integration remain pending. This amendment still needs an independent exact-head documentation review. Larry retains merge, device, deployment, and live-acceptance decisions | Main `2b50fc6` records earlier S0 history; fresh collision checks found no successor branch/open PR. Owner reports old `codex/ws30-synthetic-admission-s0` is stale/diverged and should remain untouched. Open PRs #281/#283 are WS-23/WS-31, not WS-30 |
| [WS-31](#ws-31) REA NR1 | Kimi bounded implementation after main claim and acknowledgment | Assigned pure offline NR1 contract; no source or active execution verified | Claude independent source reviewer (moved from Codex by Larry 2026-11-06), separate from Kimi author; Larry chooses later actual app outcome | Verified 2026-10-28 at main `765f6bca`; future branch `kimi/ws31-no-reference-contract-20261028`; [scope and gates](docs/roadmap-log/2026-10-28-kimi-bounded-handoffs.md) |
| [WS-28](#ws-28) cleanup/fingerprint prerequisite | Codex bounded repair ownership | Repair source landed; current implementation activity unconfirmed | Independent cross-system review required before real cleanup; Claude's #254 findings remain unresolved here | #222 repair source and #254 review history; no prune/reclaim operation or fresh acceptance verified |
| [WS-17](#ws-17) console / release | Codex; historical Claude authorship retained | No current implementation or operational run verified; source/diagnostics landed | Exact combined-source review/validation remain separate; Larry retains release and live acceptance | #262 diagnostics and #224 historical verification merged; installed development `c63ecce` / services held remains dated owner evidence, not a fresh probe |
| [WS-13](#ws-13) mail/calendar/brief | Claude | 11-03: Claude claimed P3m (mail headlines on request, plan §R.0f) after Larry chose it; earlier, Codex in #277 only restored and qualified roadmap evidence | Existing source review and Larry's formal M1-1/live gates remain open as specified in the row | #212 merged; Claude's #254 correction restored. October 13 acceptance and later deployment ancestry do not prove a new M1-1 repeat |
| [WS-20](#ws-20) coordination / acceptance handoff | Codex; Claude retains B4 authorship/ownership | Codex in #277 restores proven policy closeout; no new checker implementation | Independent documentation review for this draft; existing acceptance owners and Larry retain final Phase A/B | #250/#271/#273 source/evidence landed; final owner-evidence milestone open |
| [WS-24](#ws-24) recovery foundation | Codex retained dispatcher | Offline contract landed; no current persistence/runtime worker assigned or verified | #270 records historical independent source approval; combined validation and later runtime review remain open | #270 at `38b0fcd`, 32 historical synthetic tests; failed historical CI preserved |
| [WS-21](#ws-21) display transfer | Claude implementation | No current implementation run verified | Codex reviews changes; Larry owns physical acceptance | #171 landed; external-display acceptance remains open |
| [WS-06](#ws-06), [WS-07](#ws-07) recovery / voice workflows | Claude | Landed work; current follow-up worker activity unconfirmed | Existing plan reviewers; Larry's outstanding Mac checks | Main rows/linked plans retain implementation history and open acceptance; no new execution receipt |
| [WS-01](#ws-01), [WS-02](#ws-02), [WS-04](#ws-04) reliability / isolation / access | Codex; WS-04 currently documentation preparation only | Current implementation activity unconfirmed; WS-04 runtime needs a fresh claim | Existing cross-review/acceptance owners and Larry's activation decisions | Main rows; #255 preparation does not authorize runtime provisioning or activation |
| [WS-09](#ws-09), [WS-10](#ws-10), [WS-11](#ws-11) acceptance / rollout | Larry for acceptance; original builders retained in rows | No new live acceptance session verified | Larry plus each existing evidence recorder/feature owner | Existing checklists remain open and dependency-gated; no new acceptance inferred |
| [WS-22](#ws-22), [WS-25](#ws-25), [WS-26](#ws-26), [WS-27](#ws-27), [WS-29](#ws-29) future work | Codex documentation/intake only; implementation owners unassigned | Parked/proposed implementation; no current implementation worker | Future reviewer unassigned; Larry's prerequisite acceptance and fresh dispatch required | Existing plans/rows preserve proposal boundaries; documentation is not implementation authority |
| [WS-08](#ws-08), [WS-12](#ws-12), [WS-14](#ws-14), [WS-15](#ws-15), [WS-16](#ws-16), [WS-18](#ws-18) closed bounded work | Codex: WS-08/16; Claude: WS-12/14/15/18; original attribution retained | No new assignment or current activity verified | Historical accepted evidence remains authoritative within its recorded bounds | Accepted rows retained; this view does not reopen them |

**Coordination refresh — verified 2026-10-27 01:56:54 UTC:** #275 merged
as `51a3f56`; Kimi's #276 then merged as `6f7c58e`, from head `0991ba5`.
This branch retains **current main's entire WS-05 block unchanged**, including
Kimi's documentation attribution, plan/log references and Codex's retained
implementation/acceptance ownership. Its earlier duplicate field corrections
remain withdrawn. Prior descriptions of #276 as open/conflicted were historical
snapshots and are superseded by this merge receipt; no new acknowledgement was
posted on the [coordination request](https://github.com/Larryfix71566/jarvis-voice-ai/pull/276#issuecomment-6431413220).
Kimi's row says no further WS-05 work without a new dispatch.

**Remaining claim consistency:** adopted #276 starts WS-05's status with
`landed` for its documentation reconciliation while retaining the future Codex
fixture repair as claimed in prose. Under §0, mechanical scope locking applies
to `claimed`, `in-progress` or `review`, so that prose is not equivalent to a
leading active status. The coordinator/WS-05 owner must reconcile the active
fixture lock before further implementation; this documentation refresh does
not silently reassign ownership or declare the repair complete. #277 still
requires independent review of this current-main reconciliation and fresh
exact-head CI. No model change, installation or live acceptance follows.

## From ROADMAP.md WS-32 Status line, text from "Prior status, retained:" to end of line (line 512 at 837bb04)

Prior status, retained: landed via [#275](https://github.com/Larryfix71566/jarvis-voice-ai/pull/275) at merge commit `51a3f567d6f1f0ad1dc085cdc1127260cefffb77` (source repair only; not deployed or live-accepted): the canonical roadmap has a separate 384 KiB bounded source limit while every other path retains the 256,000-byte cap. Complete current-repository reading/projection and second-read refusal are covered. Candidate validation: 90 focused tests; 7,085 unit passes/11 skips/29 subtests; 197 integration passes/four skips; 13 offline eval passes; latency and frontend build pass. Post-merge verification on main `18dad604852da7be72fc6ab2d92fc8728d2b5ca6` found unchanged implementation/test blobs and 97 focused/manifest tests passed. All five #275 checks passed; independent exact-source review remains pending.

## From ROADMAP.md WS-28 Status line, text from "Prior status, retained:" to end of line (line 530 at 837bb04)

Prior status, retained: landed repair via this PR after merge; candidate synthetic regression checks pass (160 tests, zero failures). Independent exact-head cross-system review remains pending; main and real cleanup are not certified by an unmerged candidate or local tests.

## From ROADMAP.md WS-17 Status line, text from "Historical status follows:" to end of line (line 616 at 837bb04)

Historical status follows: landed via this PR (after-merge test-only state): deferred application-hide fixture settling remains within the original three-second bound, with every original assertion preserved. Exact combined `636880e` comparison finished11/12: native581/five skips/one failure. Full-native trace reproduced visible/unhidden to hidden/invisible306ms after initial readiness; deterministic `845cb34` regression fails three assertions with zero skips. [Follow-up source receipt](docs/acceptance/command-console/receipts/ws17-native-deferred-hide-2026-10-22.md) keeps green/full/review/CI gates pending until verified. First focused157f195 stopped before the full profile: six cases/zero skips/three initial-precondition assertion failures in the immediate-hide regression, while the new deferred-hide case passed. Follow-up00fa4a0 routes that positive setup through the settled helper without changing any original assertion or explicit hide phase. Current-source green/full/review/CI remain required. No runtime observer, human checkbox or owner changes. Historical status follows: landed via this PR (after-merge implementation state): native visibility fixture now prepares its real unhidden/unoccluded window after creation, without a premature frontmost-app prerequisite. Five focused tests pass with zero skips; the late-hidden regression fails four assertions before the repair and passes after it. All original assertions and the three-second window-state bound are preserved; application observer code is unchanged. Required full verification/review/CI precede merge; no installed/live/human criterion closes. Historical source status follows: in-progress: deterministic late-hidden fixture regression failed four assertions with zero skips against the old preparation; native app/observer unchanged. Repair and exact-source verification follow. Historical claim: claimed: bounded native visibility-gate diagnosis/repair dispatched to Codex2026-10-22 before implementation. Reproduce hidden/inactive test-host state with synthetic windows; preserve every visibility/animation assertion and distinguish prerequisites from app behavior. No skipped case or human criterion becomes passed. Historical source status follows: landed: #232/#233 and bounded follow-ups #234/#235 merged after required review/CI. Frozen compatibility source `e9c30b0` passes all twelve original independent checks and330 affected regressions; [source verification receipt](docs/acceptance/command-console/receipts/ws17-native291-source-verification-2026-10-21.md). This is code-source evidence, not installed/live/human acceptance. Existing release/private-route/runtime/hardware/observation gates remain separate; every checkbox retains its recorded state. Historical status follows: in-progress: narrow installed-Claude2.1.291 runtime compatibility after zero-inference positive/hostile localhost proof. Existing request/receipt/privacy/activation gates remain unchanged. Source review/CI precede merge; all human/live checkboxes remain open. Historical status follows: landed via this PR (after-merge implementation state): bounded canonical held-deployment prerequisite has92 focused synthetic/source-contract passes; application runtime bytes remain207bb8b. [Tool evidence](docs/acceptance/command-console/receipts/ws17-held-deployment-tool-2026-10-21.md). No live activation or checkbox closure; final source review/CI remain required. Historical status follows: landed via paired PRs #232/#233 (after-merge implementation state; this preparation is not a merge verdict). Revised combined `e74e4b8` passes all twelve original independent checks, candidate backend6,764/11skips/two subtests, native580/eight prerequisite skips/zero failures and197integration/fourskips. Required exact-source cross-system review remains open; final publication CI is separate. No live/human checkbox closes. Historical status follows: in-progress: standalone acceptance `d242ba4` plus combined preview `794a298` passed all twelve original independent checks; full combined host backend 6,925 passes/15 skips/two subtests. Resumed original host native at publication `f3aa78b` (native bytes match `794a298`) now passes 580 executed/five prerequisite skips/zero failures; actual-window control also passes. [Receipt](docs/acceptance/command-console/receipts/ws05-ws17-integrated-2026-10-21.md) preserves commands/hashes and historical failures. Larry approved both merges; provider selective guard revision to preserve OpenRouter, required revised-source cross-review and exact-head checks remain merge prerequisites. No acceptance-side service restart or inference; immediate API shutdown remains provider-owned. Deployment/live/private-route/overage/interface/observation gates stay separate; no checkbox closes. Historical source/evidence follows: claimed: Larry approved the complete bounded acceptance repair on 2026-10-21 after the multi-turn/weather session. Register `codex/ws17-acceptance-repair-20261021` before code. Reproduce named-city/local-weather misrouting and the inferred foreground-selection cause, then repair existing weather/arrival/task/reporting paths with synthetic evidence. Dedicated acceptance wizard is excluded. Integrated release waits for WS-05 subscription migration, required independent review/verification and absence of another deployment. Historical status follows: review: draft runtime [PR #226](https://github.com/Larryfix71566/jarvis-voice-ai/pull/226) has completed offline source verification on frozen implementation `fbfb669`: all twelve original independent checks PASS, exact-source Claude static follow-up **No blocking findings**, and all five frozen-source CI jobs PASS. Full host native: 579 executed / five explicit prerequisite skips / zero failures; 61 focused caller/cache/privacy/TTL/roadmap cases PASS. Full host Python: 6,809 passed / 15 skipped on `e29973d`, with candidate Python/test trees byte-identical. Independent candidate backend: 6,612 passed / 11 skipped; independent candidate native: 579 executed / 8 prerequisite skips / zero failures. The [final scrubbed receipt](docs/acceptance/command-console/receipts/ws17-current-request-final-2026-10-19.md) preserves exact fingerprints, original ordered commands/log hashes, source/test manifest, review chain and historical failure dispositions. Actual SDK upstream/deferred/interruption ownership, real renderer/cache/roadmap exits, multi-panel visibility and selected-owner read-state defects were reproduced and repaired; all six original review items are NON-BLOCKING. The proposed cache self-unread generalization does not reproduce and is retained as a passing control. The interrupted `e29973d` VM is superseded, not passed; earlier `0f2af66` evidence remains historical. This publication changes ROADMAP/docs only after source freeze; runtime/test identity is checked separately and publication-head CI remains a separate required check. Merge, deployment/rollback, loaded-build identity, UI2-23/24/25 and physical/observation gates remain open. Historical implementation/review status follows: independent release verification/deployment/live acceptance remain open. The exact-source Claude review completed on `61f701d`; focused reviewer reconciliation explicitly marks its primary privacy Finding 1 INVALID as a blocking issue. The field asymmetry is deliberate legacy local rendering, not a new public source grant. Timezone consistency is an unconfirmed coverage note, not a proven defect. Historical prior-merge/attempt evidence follows. PR #216 landed in main as `28420af` on 2026-10-18, after all five GitHub checks passed; the roadmap display, filters, refresh, sharing, and UI2-24/25 repair source are present in main. Cross-system review returned no verdict because the authorized Claude attempt timed out; independent release verification, deployment and live acceptance remain open. Historical implementation evidence follows. #214 claim merged as `bd7fca0`; slices 3.2/3.5 implemented on the claimed branch (spoken-number framing and content-free console diagnostics), with 85 backend and 14 native focused tests passing. A real AppKit menu reproduction now pins stale rows after a second city, pin and close; rebuilding the transient menu on the existing inventory revision fixes that case (35 related native tests pass). The bounded Haiku baseline on `ed4107b` scored 1/2: numbered selection used view_set twice and failed; repeat weather delegated to analyst and passed. The authorized synthetic Haiku comparison on `75694b7` passes 2/2. Retained-weather context now preserves the first relay before minimizing old forecast copies. Under merged claim #215 (`b2d1b10`), guarded roadmap snapshots and exact source validation pass 138 reader/source-policy tests; three native decoder regressions pass. Source `0c6e1af` passes the full backend suite (6,543 passed / 11 skipped) and 28 affected native Recents/router tests; no release acceptance is claimed. Roadmap cards, shared voice/pointer filters, guarded fixed-source refresh, filtered sharing and the complete first-arrival event are implemented via #216. Claim #217 merged as `ed21d82` before the bounded Base edit; CX-22 records WS-05 coordination. Final offline backend validation: 6,802 passed, 15 skipped, zero failures; 111 focused event/source/privacy tests pass. All 22 current workstream cards survive the actual observation path. JarvisKit: 235 passed. Final full MortimerHost verification passed 563 tests, five skipped, zero failures, including the ten roadmap controls/router/accessibility cases. Cross-system review, independent release verification and deployed roadmap/UI2-24/25 acceptance remain open. Earlier landed implementation: #198 (`d5d3e7e`) and test-only capture repair #203 (`dc59bd0`) merged, followed by successful deployments recorded for `dc59bd0` and `575cc7b`. Acceptance remains open: the 10-17 campaign on the installed artifact found stale Recents, incomplete voice selection and missing fresh-result reopen/reference behavior (UI2-24/25). Bounded conversation/arrival passes remain valid only for their recorded cases. Final independent-pass/host-OCR evidence landed via #209 (`a9701c2`); it is not a full physical-Mac pass or release acceptance. Larry dispatched the UI2-24/25 repair to Codex on 10-17 following Claude's read-only diagnosis (`docs/roadmap-log/2026-10-17-ws-17-claude-ui2-24-25-diagnosis.md`): the 10-17 voice failures were Supervisor tool choice (`view_set` instead of `result_select` for "open result number one"; no delegation at all on the repeated weather question), confirmed from the production bot log; the stale Recents menu is separately reproduced in AppKit with two store entries and a Results · 2 button. Larry confirms the original live button showed one result; that distinct store/routing incident remains to be traced/retested and is not closed by the menu repair. Larry approved the context-stub backstop (diagnosis slice 3.4, option b) as a plan §7.2 amendment.

## From ROADMAP.md WS-05 Status line, text from "Historical status follows:" to end of line (line 875 at 837bb04)

Historical status follows: in-progress: selective direct-provider shutdown in draft #232: direct API-capable services reversibly stopped October 21 11:27 UTC; preserve explicit OpenRouter through validated source-policy execution. Subscription activation remains blocked on exact runtime/workload/latency receipts, account billing and private-route prerequisites. Larry dispatched direct OpenAI/Anthropic API retirement and migration to his official subscription runtimes on 2026-10-20 in session `01a1573e-ae10-7388-b7c4-e36ff49120e0`. Claim #230 preceded runtime edits. Preserve all historical acceptance gaps; this candidate changes no running configuration. Prior landed foundation via #177 (`c38d895`), owned-source fixture repair via #200 (`a5b6f88`), and bounded child-directory isolation via #201, merged as `83d90e8` on 10-10 (source `08c0635`, final head `de4381c`; all five CI checks passed). Larry approved revised `08c0635` for offline WS-17 verification only on 10-10. That comparison against candidate `59d57ea` is running; no result or live acceptance is claimed. Broader model/runtime/rollout acceptance remains open; no production activation or deployment

## From ROADMAP.md §4 Conflict register, resolved rows (table at lines 1718–1744 at 837bb04)

| ID | Conflict | Resolves | State |
|---|---|---|---|
| CX-23 | WS-27 new documentation request expanded by Larry 10-18 to front acceptance clearance/current status; #218/#219 edit neighboring status and joint-plan progress. | Larry explicit documentation dispatch; Codex additive reconciliation on its isolated branch | Resolved documentation boundary: update current roadmap summary and existing status reports, append clearance/inventory to existing WS-20 plan, preserve #218/#219 intent, all restored proposals and all owners/criteria/receipts. Both PRs merged during publication and are incorporated via main `9ea27c7`. No runtime claim or review/deployment waiver. The conflict resolution retains the restored intake/cards/WS-22 dependency and both dated plan additions; no runtime change. |
| CX-21 | WS-13 P1 adds the `mcp-mail` source contract to `jarvis/skills/registry.py`, which WS-05 (Codex, claimed) holds for source classification. WS-13 edits only the `mcp-mail` entries (classification and `EXTERNAL_TOOL_SERVERS`/source-operation sets), not `_invoke` or any existing entry; plan §R.13. | `codex` (WS-05): review those entries in the P1 PR | resolved: Codex revision-3 sign-off recorded in WS-13; #204 merged `575cc7b`. Subsequent mail-preflight/live acceptance remains separate |
| CX-16 | WS-21 (supporting display transfer) edits the display-transfer, panel and screen parts of files in WS-17's scope: `console_protocol.py`, `ConsoleProtocol.swift`, `ConsoleActionRegistry.swift`, `ConsoleActionCoordinator.swift`, the `WorkspaceStore` inventory, and the display menu in `WorkspaceView.swift`. Both rows are Claude's; WS-17 has no open branch. | `larry` (10-03): new row WS-21; WS-17's CC7a.3 starts from main after WS-21 merges | resolved 10-06: PR #171 merged as `bde22bb` on 10-03; its live display acceptance remains open in WS-21 |
| CX-13 | WS-14 edits `jarvis/subscription.py`, which is WS-02's scope (Codex; landed, so unlocked, but its live isolation gates are open). The allowlist change adds `USER`/`LOGNAME`, justified by the live `Not logged in` result recorded in WS-06. | `larry` (09-29): Claude lands, and Codex reviews before merge | resolved 09-29: Codex post-merge review of PR #102 found no blocking code issue; Mac Keychain/launchd evidence remains reported live evidence, not independently reproduced |
| CX-15 | WS-17 (Command Console CC7a) changes Codex's adaptive-interface workspace (`WorkspaceStore`, `ResponseResultRouter`, stage, header) and supersedes the stable result tabs and 09-18 per-request response cards. | `larry` (09-30): Claude builds, Codex reviews each increment; `codex` confirms scope before CC7a.1 | resolved 09-30: Codex confirmed scope with boundaries (result identity, Recents as a display limit, UUID-targeted voice actions, reuse under the same identity, no focus stealing); recorded in plan §7.2 |
| CX-14 | WS-15 PR #114 added `URLSession.shared.dataTask` in `Display/RadarMapView.swift`. On main `05c4a40`, the full MortimerHost suite failed two assertions in `MemoryGraphClosureC3Tests.testURLSessionSharedIsOnlyUsedByJarvisHTTPAndTheWakeWordSocket`. The WS-16 protected actual-window capture passed on that tree. | `claude` under active WS-15 scope | resolved by PR #118 (`adeffc1`): radar uses an ephemeral session; merged full MortimerHost suite passes 383 tests, five skips, zero failures |
| CX-01 | Codex's worktree is based on `977f50b` and lacks #86 and the voice-workflows landing (`jarvis/status/`, `notices.py`, `voice_workflows.py`, …). 24 `jarvis/` files changed on both sides. | `codex`: commit, then merge `origin/main` | resolved in main; deployed `539f8f6` |
| CX-02 | Migration ids `0025`–`0027` collide between main and Codex's tree. | `codex`: renumber per §3 | resolved in main; reserved IDs applied; upgrade/idempotency rechecked 09-28 |
| CX-03 | `jarvis/workflows.py`: main has triggers, priority and draft; Codex has redacted parse-failure logs. Keep both. Same care applies to all 24 files in CX-01. | `codex` during the merge | resolved in main; workflow and privacy suites pass |
| CX-04 | Workflow Viewer (landed) and Skills Workspace (in progress) both add a console view through the same five Swift files. | `larry`: **two separate views** (09-27). `codex` adds `skills` as its own mode in WS-03 | decided |
| CX-05 | 12 gap-index plans in Codex's tree that overlap `MORTIMER_VERIFIED_GAP_CLOSURE_PLAN.md` and each other. Fold them into `MORTIMER_VERIFIED_GAP_CLOSURE_PLAN.md`, or archive them with a pointer. | `codex` | resolved in main: 12 originals archived with redirects and canonical topic index |
| CX-06 | T2 code was being written while `MORTIMER_REMOTE_ACCESS_PLAN.md` still says DRAFT. | `larry` (09-27): Codex keeps owning T2; turning it on stays undecided | decided |
| CX-07 | Memory admission is designed in two places that do not know about each other. On main (Claude): the echo guard at extraction, and auto-settle of contradictions in the sweep, with a model call, notices and `memory_restore`. In Codex's worktree (GC24-05): a durable admission queue (extract → classify → apply) with a model classifier on a confidential route. Codex's `memory_extraction.py` lacks the echo guard, and its `memory_sweep.py` lacks auto-settle. See the evaluation's addendum. | `codex`: approved echo guard → durable classification/admission → saved memory → automatic contradiction settlement | resolved in main with approved ordering; full merged-release suite passes; live activation remains open |
| CX-08 | Status files have forked: `docs/acceptance/IMPLEMENTATION_STATUS.md` is 7 KB on main and 50 KB in Codex's tree. | whoever merges WS-01 | resolved in main: concise current status; both original histories archived |
| CX-09 | #86 cites `docs/plans/MORTIMER_SELF_SERVICE_ACCESS_IMPLEMENTATION_SPEC.md`, which is not in main's `docs/plans/` or `docs/archive/`. | `claude` or `larry`: add it, or record where it lives | resolved: the spec and its companion plan were recovered from `plan/self-service-access-and-recovery` and added to main in PR #100 (09-28), with status lines marking them implemented |
| CX-10 | #86's branches were built inside Codex's checkout, and the voice-workflows plan calls #86 "Codex's". | Protocol rules 9 and 12 | closed by protocol |
| CX-12 | Merge reconciliation must carry the three streaming flags from Codex's former live registry into the split live profiles, while preserving main's historical migration fixtures unchanged. Earlier source attribution to main was incorrect: Git rename merging had carried the flags into the historical YAML. | `codex` under WS-01, approved by Larry | resolved in main: three live flags restored; original fixtures preserved; explicit overlay regression passes |
