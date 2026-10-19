# Mortimer master roadmap

**Production:** `575cc7b770b621b5c8049097ef63e93618ba3016`, deployed 2026-10-13 20:02 EDT (receipt `~/MortimerRollback/logs/deployment-receipt-575cc7b.json`).

This file is the single record of **who is doing what** in this repository, for every system that writes code here. Plans (`docs/plans/`) hold design. Receipts (`docs/acceptance/`) hold evidence. **This file holds ownership and state.**

**Last full reconciliation:** 2026-10-02, read-only review of every §2 block against `origin/main` `a39136a` (before the WS-19 claim), tracked code/configuration, plan and acceptance headers, open PRs, CI, and the 09-30 DEPLOY-MAIN log. That earlier deployment of `39fc6f9` passed Python 4,938 / 7 skipped, MortimerHost 416 / 6 skipped / 0 failures, JarvisKit 219 / 0; phase D reported admin/vault 200, bot 307, and matching source/bundle revision. PRs #143–#149 merged after that earlier deployment; the 10-02 release in the Production line above subsequently included their code. This review created no new live acceptance. Original evaluation: [cross-system evaluation](docs/reviews/CROSS_SYSTEM_PLAN_EVAL_2026-09-27.md).

---

## Acceptance clearance — next priority · 2026-10-18

Larry requested clearing the accumulated acceptance backlog first, with an
accurate status report and the shortest practical Mac sessions. The
[clearance plan and complete obligation inventory](docs/plans/ROADMAP_JOINT_WORKING_PLAN.md#9-acceptance-clearance--current-priority-2026-10-18)
are in the existing WS-20 plan; the [current status report](docs/acceptance/IMPLEMENTATION_STATUS.md)
and [release checklist](docs/acceptance/adaptive-interface/RELEASE_READINESS.md)
use current main `9ea27c7` after the documentation-only #218/#219 merges; the detailed inventory links pin initial source `28420af`. Existing ownership and acceptance
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

## Current acceptance status — reconciled 2026-10-18

This current report supersedes stale next-action/PR-status prose below while
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

## 0. Protocol (binding for every system)

Systems: **`claude`** (Cowork or Claude Code), **`codex`**, **`larry`** (steps only a human can do).

1. **Read this file on `origin/main` before any work.** If your branch is behind `origin/main`, merge main first. Never trust a plan's own "baseline" line over current main.
2. **No row, no work.** Every change belongs to exactly one row in §2. If no row fits, stop and ask Larry. Add a row yourself only when Larry's task tells you to.
3. **Claim before code.** A row counts as claimed once it is on main with your system as `Owner`, your branch in `Where`, and status `claimed`. Larry sets this when he dispatches the work, by editing the file on GitHub or with a docs-only PR.
4. **Scope is a lock.** While a row is `claimed`, `in-progress` or `review`, the paths in its `Scope` belong to that row. Do not edit them from any other row. If you have to, stop, add an entry to §4, and ask Larry.
5. **One plan per row.** Add dated progress entries to the row's plan. Do not write a new plan file for the same work. A new plan file needs a new row, and Larry approves it.
6. **Shared numbers are reserved in §3 first:** DB migration ids, allow-list rows, launchd labels, ports, new config keys. Take the next free number and record it in §3 in your branch's first commit.
7. **Production is deploy-only.** Nobody edits `~/jarvis-voice-ai-clean`. Work in your own worktree or clone. Production changes only through `scripts/deploy_main.sh` (see its note on the 24 Sep incident).
8. **Stay current and visible.** Merge `origin/main` into your branch at the start of every session and before any PR. Commit at the end of every slice. Work that exists only as uncommitted changes can't be seen or merged.
9. **Stay out of the other system's workspace.** Do not read from or write to another system's checkout or worktree. Handoffs go through this file and a PR.
10. **Write your row for its after-merge state.** In the PR, describe what will be true once it merges: for example, `landed via PR #N` (or `landed via this PR` before a number exists), never `review` or `awaiting merge` as the lasting row status. Record the branch and PR in `Where`; record the exact merge commit in a subsequent status update when known. Update the existing plan's status header and dated progress to agree. A `checked` or `verified` claim names the ref or deployed revision checked, so later readers can distinguish evidence from current state.
11. **Status hierarchy:** this file (owner, state) > plan status header (design status) > receipts (evidence). When they disagree, correct the plan header, unless this file is the one that's wrong.
12. **Attribution:** every PR body names the system and its session link.
13. **Everything in progress has a block, including work that isn't code** (reviews, option write-ups, plan edits, guided Mac checks). Add it as `proposed` before starting and mark it `claimed` when you start. If the work produces no PR of its own, update the block through a docs-only PR at the end of the session. Both systems re-read §2 at the start of every session, because the other system may have changed it.

**Joint-working rules (WS-20 Phase C):**

- **C1 — Session start:** Both systems fetch main, read this file on `origin/main`, and run `python3 scripts/check_roadmap.py` once the WS-20 B4 checker lands. Fix findings in your own rows first; report other owners' findings in a change-log entry without editing their rows.
- **C2 — Row ownership:** Each system edits its own workstream blocks. The actor recording evidence may update Larry-owned acceptance blocks (WS-09, WS-10, WS-11). Shared §3–§5 may be edited by either system with a logged explanation. The one-time B2 mechanical sweep of current-production wording is assigned to Codex; other owners review only that wording.
- **C3 — Cross-review:** A PR that changes the other system's code waits for that system's review, as CX-13 and CX-15 already require case by case. A docs-only PR limited to the author's own row may merge on green checks.
- **C4 — PR age:** An open PR older than two days names its next step and actor in its row or is closed. Its owner resolves conflicts.
- **C5 — Handoffs:** `Next step` names `claude:`, `codex:`, or `larry:`. Handoffs travel through main and PRs under rule 9; Claude still does not run git on the Mac.

Claude has one extra rule: it never runs `git` against the Mac repo (see `CLAUDE.md`). Larry commits.

**Status values:** `proposed` → `claimed` → `in-progress` → `review` (PR open) → `landed` (on main) → `accepted` (Mac/live acceptance done). Also `blocked` and `parked`.

**Dispatching work (Larry):**
1. Add or edit the row on main.
2. Tell the system: *"Take WS-xx per ROADMAP.md."*
3. The system confirms that the row, branch and scope match, merges main, and starts.

---


### Shared update format (Codex and Claude)

This Markdown file is the editable source for the expandable roadmap. GitHub
renders the `<details>` sections; both systems can read and edit the same plain
text in their **own** checkout. There is no separate JSON database or HTML copy
to keep synchronized. Chat views are dated snapshots derived from this file,
not a second status authority.

For each update:

1. Follow §0 and the workstream’s existing ownership/scope rules. Read current
   main and integrate it into your own branch before changing status.
2. Edit the existing block identified by `WS-xx` (stable HTML id `ws-xx`). Keep
   **Owner**, **Status**, **Implemented by**, **Remaining work / acceptance**,
   **Model version**, **Where**, **Plan**, **Scope**, **Next step**, and **Updated**.
3. Separate the system that built a feature from the person/system validating
   it. `codex` and `claude` are systems; record an exact model only when the run
   or handoff identifies it. Use “not recorded” or “unassigned” instead of guesses.
4. Keep unfinished acceptance, dormant activation, and proposed assignments in
   §2/§5/§7. Put completed milestones in §6 at the **bottom**. A landed feature
   is not accepted until its live gates have evidence; retain its open block.
5. Update the existing plan’s dated progress and add a file under
   `docs/roadmap-log/` with system, workstream, change, evidence, and remaining
   action. Link receipts rather than copying large logs. Commit/hand off
   through the existing branch/PR protocol.
6. Refresh any requested chat view from the merged roadmap and identify its
   source revision. Never write status changes only into a chat visualization.

**Documentation authorization, 2026-09-28:** Larry asked Codex to make the
annotated expandable roadmap shared and editable by both systems. This bounded
WS-01 documentation slice uses `codex/isolated-20260924`; it does not reassign
Claude’s work or enable any runtime feature.

## 1. Systems and workspaces

| System | Where it works | How work reaches main | Reads |
|---|---|---|---|
| `codex` | Isolated worktrees under `~/Documents/Codex/2026-09-09/can/work/`; the active branch for each task is named in its §2 block. | Codex pushes a scoped branch and opens a PR; Larry may also push a human-only protection change | `AGENTS.md` |
| `claude` | Cowork: Linux VM plus a bridge to the Mac, never runs git on the Mac. Claude Code: a GitHub clone. | A branch or patch plus a commit-message file; Larry commits and pushes unless the session has GitHub access | `CLAUDE.md` |
| `larry` | The Mac, production, the vault, GitHub | Merges PRs; deploys with `scripts/deploy_main.sh` | — |

---

## 2. Workstreams

- Scope locks only while status is `claimed`, `in-progress` or `review`.
- "(proposed)" next to an owner means Larry has not yet confirmed who owns the row.
- Expand a workstream for its editable fields. These blocks replace the former rows; the protocol’s references to a “row” mean the corresponding workstream block.
- Ordered by what still needs work (Larry, 09-29). When a block's status changes, move it to the matching group. Ids are stable, so links keep working.

**Reading the acceptance lists:** Each unfinished block lists its remaining decisions, prerequisite work and checks, with the responsible actor and pass condition. Check a box only when a dated receipt names the tested revision/configuration and result; record Larry's sign-off where the plan requires it. Valid shared receipts may satisfy more than one row. Completed workstreams stay below and are not reopened.

**Documentation authorization, 2026-10-06:** Larry asked Codex to add a list for every item needing acceptance. This bounded WS-20 documentation update adds plan-derived checklists across the open blocks on `codex/ws05-execution-20261005` (#184); implementation owners, existing status fields and acceptance decisions remain unchanged.

### Needs work: not yet built (proposed, claimed, in progress, in review, blocked)







<details id="ws-28">
<summary>WS-28 — Acceptance prerequisite: sandbox cleanup race and verifier fingerprint · Codex</summary>

**Workstream:** Larry approved Codex ownership and steps 1–2 of acceptance clearance on 2026-10-18 at 20:08:26 UTC: register ownership, repair the two #210 cleanup defects, independently review and verify. This is a release prerequisite repair, not new enhancement implementation or additional product acceptance criteria.

- **Owner:** `codex` (bounded #210 repair and synthetic verification); independent cross-system review required before real prune/reclaim or affected sandbox creation
- **Status:** landed repair via this PR after merge; candidate synthetic regression checks pass (160 tests, zero failures). Independent exact-head cross-system review remains pending; main and real cleanup are not certified by an unmerged candidate or local tests.
- **Implemented by:** Claude authored merged #210; Codex owns this explicitly dispatched repair only
- **Remaining work / acceptance:** Candidate revalidates cleanup eligibility under the existing start/delete lock while holding nonblocking target-owner session/file leases; verification-child reservation is serialized before reclamation and rejects an already-deleted parent. Cleanup code now participates in the runner fingerprint. Eight new regressions fail on unrepaired main and pass with the fix; full fake-controller suite 160 tests passes; three additional regressions reproduce and repair the foreign-session headroom blockage and ambiguous ownership on initial `24206281`. Independent review, separately authorized runtime merge and exact-candidate release verification remain open. No real cleanup/clone or product acceptance pass.
- **Model version:** not independently verified; do not infer from system name
- **Where:** `codex/sandbox-cleanup-repair-20261018`, based on main `b29c7aba431eb1c9de6a0aa092128a8ce133119d`; isolated worktree after this claim lands
- **Plan:** `sandbox/IMPLEMENTATION.md` lifecycle/release ledger; existing `docs/plans/ROADMAP_JOINT_WORKING_PLAN.md` §9 retains acceptance sequencing
- **Scope:** Only the two cleanup prerequisite defects: `sandbox/prune.py`, `sandbox/control.py`, `sandbox/images.py`, `sandbox/session.py` and `sandbox/files.py` for eligibility/lifecycle-lock coordination strictly needed to prevent stale-plan deletion; `sandbox/verify.py` for runner fingerprint binding only; directly related synthetic `sandbox/tests/` regressions; dated progress/evidence in `sandbox/IMPLEMENTATION.md`, `sandbox/acceptance/` and WS-28 `docs/roadmap-log/`; this row and the existing cleanup launchd-label reservation in §3. Preserve all source/path/scanner/pin rules, privilege/network/audio/clipboard isolation, profiles, protected baseline, all twelve verification checks and original budgets/timeouts. No guest/dependency installation, startup/job activation, broad controller redesign, other owners’ model/source semantics, production source/settings/app changes or deployment. Synthetic tests use temporary homes and fake Tart only; no real prune/reclaim/clone until the repair has independent review.
- **Next step:** codex: obtain final exact-source Claude agreement on the bounded corruption policy and all current CI. Independently valid stopped verification VMs retain their existing local disposal rule; development/legacy VMs with unknown owner/child relationships remain retained and reported. No ownership index/migration is added. larry: review the completed runtime PR before any merge; no real cleanup/clone/verification or production change is authorized by this candidate.
- **Updated:** 10-18 (Larry-authorized ownership and bounded claim; no runtime change)

</details>

<details id="ws-17">
<summary>WS-17 — Command Console CC7a: conversation-first stage · Codex remaining implementation</summary>

### Acceptance checklist — remaining

The earlier one-row and card-operation subparts keep their recorded passes. Current live checks and future implementation gates are separate below.

**Current live evidence, 2026-10-17:** installed `575cc7b` contains the merged CC7a runtime. The [acceptance campaign](docs/acceptance/command-console/receipts/acceptance-campaign-2026-10-17.md) records bounded conversation/arrival passes but fails UI2-24 (stale Recents omits Atlanta; voice “open result number one” shows Atlanta but asks which result instead of completing selection) and UI2-25 (fresh weather repeat neither reopens nor adds the reference line). Results are not lost; direct card opening works. Keep dependent closure open. Historical deployment/next-step text below describes the October 11 handoff; the October 13 deployment is verified in this current receipt. Next: codex diagnoses these current failures in an explicitly scoped repair slice, then cross-review and Larry’s normal release/retest. No repair is made by this evidence-only campaign.

- [ ] **Larry · current five-turn conversation:** On the identified deployed build, both speakers' full text remains ordered, including an answer >160 characters. Ordinary speech creates no result/tab; reading a result keeps focus while the thread updates; protected-content rules hold. This is release-readiness “UI2-22 — conversation thread.”
- [ ] **Larry · current arrival-routing recheck:** The answer to the still-active explicit request opens from Conversation or another result, including a fresh weather-cache hit; unrelated/background, superseded, stale or cancelled arrivals stay unread without changing focus. This foreground exception was approved by Larry on 2026-10-18; the earlier no-jump rule remains preserved in the plan history. A web result with the supporting display open leaves conversation on main and appears on that display. This is the changed CC7a.2b part of release-readiness “UI2-23 — inline cards.”
- [ ] **Codex / cross-reviewer / Larry · CC7a.3 implementation prerequisite:** PR #173 merged as `bd18033`; corrective #197 merged as `51dcdee` (source `065d500`). Separate exact-source Claude static review and both recorded offline comparisons passed; #198 is merged and included in the recorded deployment; live acceptance remains open. Preserve UUID targets, open/pinned/Output history, numbered pinned-first inventory, unread/updated markers and truthful ambiguity/stale-target resolution; the WS-21 merge dependency is already satisfied.
- [ ] **Larry · Recents live tail after CC7a.3:** Voice/pointer select, close, pin/unpin and reopen by number/subject match the visible inventory; ambiguous/stale requests clarify. Pinned plus approximately ten visible entries does not discard open/pinned/Output records. This completes the unaccepted Recents part of release-readiness UI2-24, not a rerun of its accepted one-row part.
- [ ] **Codex / cross-reviewer, then Larry · CC7a.4 implementation and reuse:** Subject/freshness reuse and exact-source review are complete; #196 and #198 merged 10-10. The test-only deployment-gate repair is in #203, with full Mac and unchanged twelve-check offline verification passed 10-11. The repair merged as #203 and was deployed; the 10-17 reuse check failed and needs a bounded repair/retest. Weather → Atlanta → original weather must yield two cards. Fresh ≤15-minute original content reopens without fetching and adds a reference line; stale refresh replaces the same identity. Record release-readiness UI2-25; remove the temporary feature switch only after UI2-22…25 pass.
- [ ] **Larry / evidence recorder · dependent closure:** Record exact-build conversation/card/Recents/reuse outcomes, then finish changed console preservation, voice parity and accessibility UI2-04/09/13 in WS-09/11. Do not close them from the earlier partial CC7a checks.

### Roadmap display — Larry addition, 2026-10-17

- [ ] **Codex · read-only roadmap result:** "Show the roadmap" opens a readable
  in-app view sourced from the repository's `ROADMAP.md`, with every workstream
  represented, expandable status/owner/next-step/acceptance details, open work
  first and completed work last. Do not silently truncate the document.
- [ ] **Codex · provenance and refresh:** show checkout revision, content hash,
  read time and whether local content is modified. Explicitly distinguish the
  local checkout from verified GitHub main and from the deployed app revision.
  Refresh rereads the source and updates the same result identity.
- [ ] **Codex · voice and existing controls:** voice can show the roadmap,
  show a named WS item and refresh it. Existing select/pin/close, sharing and
  confirmed supporting-display transfer controls continue to work. Viewing
  neither starts self-edit nor changes a status/checkbox.
- [ ] **Codex / Larry · roadmap filters:** voice/pointer filters cover current
  blockers, Larry's pending acceptance/decisions, current owner, topic plus open
  status, a named WS's remaining checklist, completed/open work and dated change
  logs. Visible filter chips and counts, combined filters, clear/reset and empty
  states behave consistently. Preserve prerequisite context and source evidence;
  refresh, sharing and supporting-display transfer retain the disclosed subset.
- [ ] **Cross-reviewer / Larry · acceptance:** all source workstreams and
  acceptance items remain accessible, including sections after character
  30,000; compact/expanded layout, VoiceOver and both display placements work.
  Missing/malformed/unreadable source or failed refresh is explained truthfully;
  an old view is labeled stale, never silently presented as newly verified.

Evidence: [10-10 approved-reference twelve-check receipt](docs/acceptance/command-console/CC7A_OFFLINE_VERIFICATION_2026-10-10.json), preserving [10-09 exact-source review and offline comparison](docs/acceptance/command-console/CC7A_REVIEW_AND_VERIFICATION_2026-10-09.md). These complete bounded pre-release checks, not the compound deployment/live acceptance checkboxes.

Sources: [Command Console plan §7.2](docs/plans/MORTIMER_COMMAND_CONSOLE_ATLAS_PLAN.md), [release-readiness CC7a UI2-22…25](docs/acceptance/adaptive-interface/RELEASE_READINESS.md). The Atlas/developer checks with reused UI2 numbers in another status file are different requirements.

**Larry-approved bounded arrival-policy amendment, 2026-10-18:**
The prior §7.2 design and UI2-23 checklist retained the reader's
stage when weather arrived while another result was showing. Larry approved
the current-request exception at 23:44 UTC. The synthetic sequence is Spartanburg → Atlanta → cached Spartanburg: a result
proven to answer the still-active explicit request would open even from the
results stage. Unrelated, background, superseded, stale and cancelled arrivals
would remain unread without changing focus. This changes the foreground
policy; the earlier diagnosis that the unread arrival alone proved a UI2-24
failure was too broad and is withdrawn. UI2-24 actions remain untested and
UI2-25 has only partial identity/cache evidence. The implementation claim must
land on main before code; no checkbox closes from this amendment. WS-28 remains cleanup-only; it does not own this UI slice.

**Workstream:** Larry, 09-30: conversation is spread over one tab per turn, only Mortimer's side shows, the tab strip fills up, and asking again re-fetches. Increment CC7a of the Command Console plan (WS-09's plan): one conversation thread with both sides, results as inline cards, Recents instead of tabs, reuse a fresh result by subject.

- **Owner:** `codex` (remaining CC7a.3 repairs and CC7a.4 implementation, explicitly assigned by Larry 2026-10-07); historical Claude increments retain attribution; required cross-review and Larry release/acceptance remain separate
- **Status:** review: draft runtime [PR #226](https://github.com/Larryfix71566/jarvis-voice-ai/pull/226) has completed offline source verification on frozen implementation `fbfb669`: all twelve original independent checks PASS, exact-source Claude static follow-up **No blocking findings**, and all five frozen-source CI jobs PASS. Full host native: 579 executed / five explicit prerequisite skips / zero failures; 61 focused caller/cache/privacy/TTL/roadmap cases PASS. Full host Python: 6,809 passed / 15 skipped on `e29973d`, with candidate Python/test trees byte-identical. Independent candidate backend: 6,612 passed / 11 skipped; independent candidate native: 579 executed / 8 prerequisite skips / zero failures. The [final scrubbed receipt](docs/acceptance/command-console/receipts/ws17-current-request-final-2026-10-19.md) preserves exact fingerprints, original ordered commands/log hashes, source/test manifest, review chain and historical failure dispositions. Actual SDK upstream/deferred/interruption ownership, real renderer/cache/roadmap exits, multi-panel visibility and selected-owner read-state defects were reproduced and repaired; all six original review items are NON-BLOCKING. The proposed cache self-unread generalization does not reproduce and is retained as a passing control. The interrupted `e29973d` VM is superseded, not passed; earlier `0f2af66` evidence remains historical. This publication changes ROADMAP/docs only after source freeze; runtime/test identity is checked separately and publication-head CI remains a separate required check. Merge, deployment/rollback, loaded-build identity, UI2-23/24/25 and physical/observation gates remain open. Historical implementation/review status follows: independent release verification/deployment/live acceptance remain open. The exact-source Claude review completed on `61f701d`; focused reviewer reconciliation explicitly marks its primary privacy Finding 1 INVALID as a blocking issue. The field asymmetry is deliberate legacy local rendering, not a new public source grant. Timezone consistency is an unconfirmed coverage note, not a proven defect. Historical prior-merge/attempt evidence follows. PR #216 landed in main as `28420af` on 2026-10-18, after all five GitHub checks passed; the roadmap display, filters, refresh, sharing, and UI2-24/25 repair source are present in main. Cross-system review returned no verdict because the authorized Claude attempt timed out; independent release verification, deployment and live acceptance remain open. Historical implementation evidence follows. #214 claim merged as `bd7fca0`; slices 3.2/3.5 implemented on the claimed branch (spoken-number framing and content-free console diagnostics), with 85 backend and 14 native focused tests passing. A real AppKit menu reproduction now pins stale rows after a second city, pin and close; rebuilding the transient menu on the existing inventory revision fixes that case (35 related native tests pass). The bounded Haiku baseline on `ed4107b` scored 1/2: numbered selection used view_set twice and failed; repeat weather delegated to analyst and passed. The authorized synthetic Haiku comparison on `75694b7` passes 2/2. Retained-weather context now preserves the first relay before minimizing old forecast copies. Under merged claim #215 (`b2d1b10`), guarded roadmap snapshots and exact source validation pass 138 reader/source-policy tests; three native decoder regressions pass. Source `0c6e1af` passes the full backend suite (6,543 passed / 11 skipped) and 28 affected native Recents/router tests; no release acceptance is claimed. Roadmap cards, shared voice/pointer filters, guarded fixed-source refresh, filtered sharing and the complete first-arrival event are implemented via #216. Claim #217 merged as `ed21d82` before the bounded Base edit; CX-22 records WS-05 coordination. Final offline backend validation: 6,802 passed, 15 skipped, zero failures; 111 focused event/source/privacy tests pass. All 22 current workstream cards survive the actual observation path. JarvisKit: 235 passed. Final full MortimerHost verification passed 563 tests, five skipped, zero failures, including the ten roadmap controls/router/accessibility cases. Cross-system review, independent release verification and deployed roadmap/UI2-24/25 acceptance remain open. Earlier landed implementation: #198 (`d5d3e7e`) and test-only capture repair #203 (`dc59bd0`) merged, followed by successful deployments recorded for `dc59bd0` and `575cc7b`. Acceptance remains open: the 10-17 campaign on the installed artifact found stale Recents, incomplete voice selection and missing fresh-result reopen/reference behavior (UI2-24/25). Bounded conversation/arrival passes remain valid only for their recorded cases. Final independent-pass/host-OCR evidence landed via #209 (`a9701c2`); it is not a full physical-Mac pass or release acceptance. Larry dispatched the UI2-24/25 repair to Codex on 10-17 following Claude's read-only diagnosis (`docs/roadmap-log/2026-10-17-ws-17-claude-ui2-24-25-diagnosis.md`): the 10-17 voice failures were Supervisor tool choice (`view_set` instead of `result_select` for "open result number one"; no delegation at all on the repeated weather question), confirmed from the production bot log; the stale Recents menu is separately reproduced in AppKit with two store entries and a Results · 2 button. Larry confirms the original live button showed one result; that distinct store/routing incident remains to be traced/retested and is not closed by the menu repair. Larry approved the context-stub backstop (diagnosis slice 3.4, option b) as a plan §7.2 amendment.
- **Implemented by:** Claude (Cowork): CC7a.1/1b/2/2b; Claude (Claude Code): CC7a.3 foundation from #173; Codex: observed-inventory voice/acknowledgement and Older-result repair `fee4ac0`, inventory-size/capacity correction `065d500`, measured reader retention `adf2597`, and CC7a.4 native-owned reuse/reference/upsert `6e218cd`/`47f9e05`; real thread-window capture readiness `0a2ff94`; source-age menu/VoiceOver/choices `748b1e5`
- **Remaining work / acceptance:** CC7a.1-CC7a.4, each a reviewed PR; RELEASE_READINESS UI2-22..UI2-25 on the Mac. UI2-04, UI2-09 and UI2-13 are held until then. Larry, Mac, 10-02, build `ae70f2c`: one console row with nothing below it in conversation, results and Knowledge Atlas (UI2-24's CC7a.1b part; its Recents parts wait for CC7a.3); Knowledge ▾ and Tools ▾ send content to the supporting display with no result open, and "Return display content here" brings it back; a spoken answer showed once in the thread. Larry, Mac, 10-03, build `9545641` (UI2-23): cards sat after their replies; Open showed the result and Conversation came back; pin, compare and close worked from a card and closing kept the Output record; after a layout 1 to 2 switch a new result arrived without taking the screen. A weather asked for from the conversation stayed a card; Larry decided it should open (CC7a.2b). After Codex's review of #169, only the answer to what he just asked opens: a background job finishing later stays a card, and with the supporting display open the conversation stays on the main screen. UI2-23 is rechecked on a build that contains CC7a.2b. The 10-06 public voice session on `bde22bb` establishes bounded ordered/full-text and arrival-focus subchecks in the [#191 voice receipt](docs/roadmap-log/2026-10-06-ws-20-codex-voice-acceptance-review.md); full UI2-22/23 protected/focus/scroll/size and remaining card/display cases stay open. Reuse those subchecks rather than repeat the same public text/routing cases solely for documentation. Approved design: `docs/interface-research/cc7a/cc7a-approved-design-2026-09-30.html` (transcript rows, compact cards, Recents menu, reuse reference line, no-jump notice); Codex's boundaries in plan §7.2.
- **Model version:** Historical implementation versions not recorded; do not infer from system name. Exact 10-09 cross-review: Claude Code 2.1.290 / `claude-sonnet-5`, recorded separately from Codex implementation in the linked receipt
- **Where:** `codex/ws17-current-request-arrival-20261018` from main `c244963`, under merged claim [PR #225](https://github.com/Larryfix71566/jarvis-voice-ai/pull/225). Separate verification documentation remains [PR #224](https://github.com/Larryfix71566/jarvis-voice-ai/pull/224); earlier implementation via #216 and all historical receipts remain in the plan/logs.
- **Plan:** `docs/plans/MORTIMER_COMMAND_CONSOLE_ATLAS_PLAN.md` §7.1 item 9 and §7.2
- **Scope:** Claimed current-request slice under merged #225: existing `App/AppMessageRouter.swift`, `Stores/WorkspaceStore.swift`, `Stores/ConversationStore.swift`, `Console/ConversationThreadView.swift`, the existing WS-17 console/DisplayPayload contract and inventory/turn-binding paths below, and directly related synthetic caller-chain tests; existing plan, canonical UI2-23 criterion in `docs/acceptance/adaptive-interface/RELEASE_READINESS.md` and WS-17 log only. Establish deterministic current-request eligibility, cancellation/supersession and one foreground winner before any focus change; preserve supporting-display ownership and all unrelated/background arrival behavior. No WS-05 `jarvis/agents/delegate.py`/Base/Registry edit, new durable task system, model/policy/account change or production operation. If the real caller chain needs another owner's path or a new wire identifier, stop for the corresponding scope/reservation before editing. Existing implemented scope follows: `App/ResponseResultRouter.swift`, `Stores/WorkspaceStore.swift`, `Stores/ConversationStore.swift`, `Console/AdaptiveStageView.swift`, `Console/ConversationThreadView.swift`, `Console/TopBarView.swift`, `Display/WorkspaceView.swift`, `App/AppMessageRouter.swift` (display arrivals: whether a result opens on arrival), voice result actions (`App/ConsoleActionCoordinator.swift`, `App/ConsoleActionRegistry.swift`, JarvisKit `ConsoleProtocol.swift`, `jarvis/bot/console_protocol.py`), DisplayPayload `subject_key` (JarvisKit + `jarvis/bot/display.py`), weather tools' reuse check; `Console/ConsoleActionBar.swift`, `Stores/WorkspaceRecents.swift`, `jarvis/bot/console_actions.py`, the console inventory/turn binding and result acknowledgement portions of `jarvis/bot/pipeline.py`, `jarvis/bot/weather_tool.py`, `jarvis/bot/weather_card.py`; CC7a.4 expansion reserved on main via #195: new `jarvis/bot/weather_reuse.py` and associated tests; only the weather-call interception in `jarvis/skills/registry.py` `_invoke`, using a request-owned ContextVar hook after existing guards and preserving classified `_finish_invocation` envelopes; optional bounded `weather_source` in Python/JarvisKit DisplayPayload (`AppMessage.swift`), with `WorkspaceStore` as the sole in-memory cache/freshness owner; shared `weather_reuse` and `result_reopen` actions under the §3/plan §7.2 contract. No process-global registry callback, backend TTL mirror or registry guard/policy change; associated unit/native/contract tests and exact-build WS-17 evidence in `docs/acceptance/adaptive-interface/RELEASE_READINESS.md`, `docs/acceptance/command-console/`; dated progress in the existing plan and WS-17-specific `docs/roadmap-log/` files. Bounded 10-17 repair extension, per #213: weather-repeat, numbered-result and roadmap-read routing instructions only in `jarvis/prompts.py`; tool description and reference parsing in `jarvis/bot/console_actions.py`; content-free console action/status logging and weather-delegation context minimization only in `jarvis/bot/pipeline.py`; `tests/evals/voice_workflow_eval.py` and `tests/evals/voice_workflow_cases.yaml` for the affected synthetic-history cases and action-level assertions; native Recents-menu rendering and spoken-reference tests. Additional Larry request 10-17: ensure Mortimer can read and knows how to read the roadmap. Add the canonical path/read-only tools and checkout-freshness guidance near the beginning of injected `docs/REPO_MAP.md`; add explicit Supervisor-to-Developer roadmap/status routing and Developer read guidance in `jarvis/prompts.py`, with focused prompt/navigation/read-access tests. Preserve repo path restrictions and source/privacy policy; no auto-fetch, broader filesystem access, memory copy of roadmap status, runtime activation or claim of main freshness. Roadmap-display addition authorized 10-17: read-only roadmap parsing, dated `docs/roadmap-log/` evidence and provenance in `mcp_servers/mcp_repo/logic.py` using existing guarded repository reads; deterministic snapshot filters and voice/pointer filter state in the existing roadmap-result paths; presentation mapping in `jarvis/bot/display.py` and associated Python/JarvisKit DisplayPayload schema; existing `Display/DisplayContentView.swift` and a bounded `Display/RoadmapView.swift`, with refresh/navigation wiring in the already-owned console paths and focused tests. Reuse current result identity, transport, sharing and WS-21 transfer; no new server, port, credentials, registry trust changes or alternate status database. Reserve any new wire field in §3 before implementation. No other Supervisor/tool policy, live model/route/account setting, source approval, private log disclosure or provider activation. Preserve WS-21 transfer/screen contracts and other active workstream behavior (CX-20) Bounded source-contract extension explicitly approved by Larry 10-17: `jarvis/skills/registry.py` `_repo_source_refs` and associated classification tests may verify the optional roadmap snapshot and every included guarded dated-log source/hash. Preserve the exact legacy response contract for other files, reject fabricated or mismatched snapshot/provenance/log data, retain existing source-policy floors and approvals, and make no changes to unrelated registry guards, credentials, routing or activation. This closes the schema incompatibility before the new reader transport is enabled. Bounded roadmap-event extension explicitly approved by Larry 10-17: `jarvis/agents/base.py` only the `agent_tool_result` observation projection for canonical `repo_read_file ROADMAP.md`, plus directly related tests. Preserve the existing 20,000-character limit for every other tool/file and every private/redacted path. Carry a complete, bounded, already host-classified roadmap snapshot to the native display without broadening source approval, changing model history, run-log caps, delegation, budgets, tool permissions or WS-05 source-before-sink enforcement. Refuse oversize/malformed roadmap observations explicitly rather than emitting truncated JSON. Coordinate this narrow observation-only exception with WS-05 ownership of Base; no other Base edits are authorized.
- **Next step:** codex: finish documentation-only publication and required publication-head CI for draft #226, preserving exact runtime/test identity with frozen `fbfb669`. larry: decide runtime merge and deployment separately; after an approved identified release and rollback proof, run the short UI2-24/25 fail-fast session, then affected UI2-23/22 and dependent UI2-04/09/13. Physical prerequisites and observation periods stay open; no live acceptance closes from source checks.
- **Updated:** 10-19 (#226 frozen `fbfb669`: original 12-check independent PASS; Claude No blocking findings; five source CI checks PASS; native 579/5 skips/0 failures; 61 focused and 88 roadmap contracts PASS; docs-only publication/final-head CI separate)



</details>

<details id="ws-13">
<summary>WS-13 — T5 mail, calendar and brief: draft reconciled with main, waiting on Larry's decisions · Claude (review)</summary>

### Approval and future acceptance checklist

This item is proposed, not ready for live acceptance. Future tests below apply after the plan is approved and implemented.

- [ ] **Claude / Codex · prerequisite review:** Reconcile the draft with current architecture, security/model-routing rules, actual native client and reserved migration `0035`; coordinate the existing plan edits before implementation.
- [ ] **Larry · plan decisions:** Approve read-only scope, calendar visibility/backend, Secretary routing/isolation and documented residual risks, vault names, brief schedule and permitted content/logging. Supply selected account access through the established vault/OS flow; credentials are not entered in this roadmap. (Decisions D1–D9 recorded 10-10 in plan §R.5; account access still to be supplied.)
- [ ] **Claude / Codex · implementation and security evidence:** Deliver reviewed implementation and required suites; mail secrets reach only the intended child, reads do not mark mail read, injection fixtures cause zero post-mail tool calls, routing meets the existing ≥90% floor, and digest speech is grounded in the visible facts.
- [ ] **Larry · future Mac checks:** Complete plan §R.12's Mac checks (the M rows, which replace V1–V10) on the selected backend: secret isolation, EventKit/CalDAV calendar parity, unread preservation, agent/injection isolation, routing, requested and once-daily scheduled brief, grounding and all kill switches. Record actual scores and outcomes rather than assuming the draft's defaults are correct.
- [ ] **Larry / Claude · release:** Approve the tested artifact/configuration, record deployment and reversible rollback, and confirm the brief/card/timezone and failure behavior on the Mac. Sending mail or writing calendar events remains outside this plan.

Source: [mail/calendar/brief plan §R.12](docs/plans/MORTIMER_MAIL_CALENDAR_BRIEF_PLAN.md). This is an approval/implementation dependency list, not a claim that the proposed feature exists.

**Workstream:** Review `MORTIMER_MAIL_CALENDAR_BRIEF_PLAN.md` (DRAFT, 2026-08-26) against today's main before anyone builds T5. Docs only.

- **Owner:** `claude`
- **Status:** landed: P1 (mail header source) merged in #204 as `575cc7b` (head `8b77df1`, revision 3) and deployed in `575cc7b` on 10-13; Codex reviewed revisions 1 and 2 and accepted the registry decisions (CX-21); Codex signed off revision 3 (`8b77df1`) on re-review; #205 (merged as `9f9bc71`) fixed the M1-1 preflight, which printed PASS with no mail name set; Codex's two further preflight corrections (startup-shell removals applied, relative `--env-file` resolved) are in PR `ws13/p1-preflight-rev3`; Larry ran M1-1 to M1-3 on the Mac on 10-13 against the deployed `575cc7b` and all three passed (Mac acceptance recorded below; formal M1-1 repeat from production after the next deployment); P2 and P3 not yet claimed
- **Implemented by:** P1: Claude (landed, #204 `575cc7b`); P2–P5: not started
- **Remaining work / acceptance:** P1 Mac acceptance, 10-13, deployed `575cc7b`: M1-1 PASS (the corrected preflight from this branch, with the four vault names set: each reaches `mcp-mail` and no other of the 15 servers; effective JARVIS_ENV_SCOPING_ENABLED on; Larry's `.env` does not set it); M1-3 PASS (bellsouth.net via `imap.mail.att.net` with the secure mail key, and Gmail with an app password: both `status=ok`, `exact` counts, headers complete, call 3.1-3.6 s against the 13 s bound; the first Gmail attempt failed `login_rejected` because the stored user was not the full address and the password was not an app password, both corrected in the vault); M1-2 PASS (one unread test message per account: a second read still counted it as UNSEEN, `exact:1` on both, so the first headers read set no \Seen flag, and Larry confirmed both still unread in webmail); `mcp_server_started name=mcp-mail tools=1` logged at the first session after the deploy. Open: Codex's review of `ws13/p1-preflight-rev3` (the preflight now replaces its environment with the startup shell's snapshot, so an `unset` in .env takes effect, and resolves a relative `--env-file` before loading; #205 at `9f9bc71` had the startup-shell read and the missing-server FAIL); the formal M1-1 repeat, `python scripts/check_mail_env.py` from production after the next deployment (the recorded deployment is still `575cc7b`; the checkout at `8842503` has no receipt); the macOS OSError seen in two Mac test runs before the `deadline` unification is still unidentified (it did not occur against the real servers). Then P2 (needs the Google account in macOS Internet Accounts for M2-2; its claim needs Codex's agreement on the WS-17 portions, plan §R.13) and P3, each claimed on its own against §R.12; P4/P5 stay separately gated (§R.11)
- **Model version:** not recorded; do not infer from system name.
- **Where:** main: P1 via #204 (`575cc7b`), the plan via #196, the preflight follow-up via #205 (`9f9bc71`); preflight revision 3 on branch `ws13/p1-preflight-rev3` (PR open)
- **Plan:** `docs/plans/MORTIMER_MAIL_CALENDAR_BRIEF_PLAN.md`; §R (10-07) is authoritative and the August text is history except where §R.9 keeps it. No GitHub branch other than this one touches the plan. Migration `0035` stays reserved for T5 (`0035_brief`).
- **Scope:** the plan file; and for P1 (plan §R.6): new `mcp_servers/mcp_mail/` (`__init__.py`, `logic.py`, `server.py`, `skill.yaml`), the `mcp-mail` entry in `config/mcp_servers.yaml`, the `mcp-mail` source-contract entries only in `jarvis/skills/registry.py` (WS-05 reviews; §4 CX-21), `EXPECTED` in `tests/unit/test_requires_env_snapshot.py`, `ALL_SERVERS`/`TOTAL_TOOLS` in `tests/integration/test_registry.py`, `EXPECTED_TOOLS` in `tests/integration/test_mcp_servers.py`, new `tests/unit/test_mcp_mail*.py` with the fake IMAP server fixture `tests/unit/mcp_mail_fake_server.py`, the names-only preflight script `scripts/check_mail_env.py` for M1-1, and `.env.example`. No agent, prompt, model, pipeline, Swift or migration change in P1
- **Next step:** codex: review PR `ws13/p1-preflight-rev3`; larry: merge it after Codex's approval, deploy with DEPLOY-MAIN, and run `python scripts/check_mail_env.py` from production (formal M1-1 repeat); claude: answer the review, then propose the P2 claim, which needs Codex's agreement on the WS-17 portions
- **Updated:** 10-17

</details>

### Built: live acceptance or status publication still open

<details id="ws-20">
<summary>WS-20 — Roadmap joint working: catch-up and drift prevention · Claude + Codex</summary>


**Acceptance campaign authorization — Larry, 2026-10-17:** Codex runs the
existing automated and live acceptance checks on
`codex/acceptance-campaign-20261017`; Larry supplies human/hardware actions.
Initial evidence merged via #208 (`f363444`); final results use
`codex/acceptance-campaign-results-20261017` under the same bounded scope.
The source baseline is `9f9bc71c26c82c832121be118346abaa1b4f89a4` (all PRs
merged); the installed candidate remains `575cc7b`. This bounded claim covers
test execution, evidence receipts, this note, the existing WS-20 plan/log,
the reconciled shared acceptance runbook, current evidence in Codex-owned WS-17 and Larry-owned WS-09/11,
and Larry’s observed WS-18 acceptance record. Preserve implementation owners;
failures are findings, not authority to change their code. AirPods are
available; external-display cases remain untested. No new development,
activation or deployment is authorized. Codex records exact outcomes before
closing any matching subcheck; parent gates remain open until fully evidenced.

**Bounded documentation authorization — Larry, 2026-10-17:** Codex owns this
acceptance-first documentation/triage slice on `codex/acceptance-first-20261017`:
the priority banner, this additive note, the final parked WS-22 entry, its
canonical plan, dated progress in the existing joint-working plan, and the
[acceptance triage](docs/roadmap-log/2026-10-17-ws-20-codex-acceptance-first.md).
No implementation, activation, deployment, or product acceptance is granted.
Existing fields below retain their historical scope; Claude's #205/#172/#174
corrections remain with their owner. Next: Codex publishes this documentation;
Larry reviews it and participates in the identified-candidate console session,
then audio/display checks when equipment is available. Unbuilt prerequisite
and activation decisions remain explicit; WS-22 stays parked.


**Additional cleanup authorization — Larry, 2026-10-17:** Codex owns the
bounded PR-backlog reconciliation on `codex/pr-backlog-cleanup-20261017`:
this additive roadmap note, the WS-21 plan/header and historical logs already
proposed by Claude in #174, and dated WS-20 progress/log. This supersedes the
earlier instruction to leave #172/#174 pending, without reassigning Claude's
code or acceptance work. The replacement preserves newer main and all gates;
#205 is reviewed independently at its exact head. No implementation or release
is authorized here.

**Status-refresh authorization — Larry, 2026-10-17:** Codex updates the shared
summary, its WS-17/20 status fields, dated joint-working plan/log, and the
existing right-pane preview on `codex/roadmap-status-20261017`. This is
documentation only; preserve other owners’ rows, checkboxes and pending #209.

### Acceptance checklist — remaining

B1–B4 implementation is merged; the 72-entry migration is already verified.

- [x] **Codex · documentation cleanup:** WS-10/11 lifecycle prefixes now describe their landed foundations while every acceptance gate stays open. The roadmap checker passes on this documentation candidate; the single Production line still matches the recorded `bde22bb` deployment. [Dated cleanup proof](docs/roadmap-log/2026-10-06-ws-20-codex-lifecycle-closeout.md).
- [x] **Codex / Claude · observation:** The first ten published post-migration PR merges (#161/#162/#163/#165/#166/#167/#168/#164/#169/#170) and their recorded integration merges replay with no conflict in §8 or `docs/roadmap-log/`. Exact complete merge trees and unchanged §8 are verified; [receipt](docs/roadmap-log/2026-10-06-ws-20-codex-ten-pr-change-log-observation.md). Unrecorded manual history is not claimed.
- [ ] **Larry · decision:** After the warn-only rollout period and owned corrections, decide whether the checker becomes a blocking CI gate; the chosen behavior is recorded and verified.
- [ ] **Each acceptance owner · evidence:** Link the remaining live checks to their own rows (WS-17, WS-18 and the other open gates); publish the final Phase A/B exit record without treating implementation as live acceptance.

Source: [joint-working plan §§3, 6–7](docs/plans/ROADMAP_JOINT_WORKING_PLAN.md).

**Workstream:** Larry, 10-02: bring the roadmap and open PRs up to date so Claude and Codex can work on it together, and stop the roadmap drifting. Larry chose: each system fixes its own rows; the change log moves out of `ROADMAP.md`, one production line, rows written as they read after merge, and a drift checker; the plan lives in the repo.

- **Owner:** `codex` (bounded roadmap documentation); `claude` retains B4 and WS-13 ownership. Remaining WS-17 implementation belongs to Codex under Larry’s 10-07 assignment (CX-20); historical Claude attribution is preserved.
- **Status:** claimed: Larry dispatched bounded acceptance-clearance evidence and safe-check execution on 2026-10-18. Existing foundation, #219 parked-card restoration and #220 clearance documentation remain landed; all accepted product scope and open live gates retain their state. Claim-only registration; no new acceptance.
- **Implemented by:** Codex (B1–B3); Claude (B4)
- **Remaining work / acceptance:** Final evidence is published via #209; acceptance owners resolve and retest their remaining gates. Larry decides whether the checker becomes blocking after the warning period. #172/#174 cleanup and #173 implementation handoffs are complete, not pending work.
- **Model version:** not recorded; do not infer from system name.
- **Where:** `codex/acceptance-clearance-20261018`, based on main `b29c7aba431eb1c9de6a0aa092128a8ce133119d`; isolated worktree. Historical foundation/campaign/status branches remain recorded in the plan and logs.
- **Plan:** `docs/plans/ROADMAP_JOINT_WORKING_PLAN.md`
- **Scope:** Bounded acceptance-clearance documentation/evidence and safe non-mutating checks: ROADMAP current acceptance/status summary and this WS-20 block; dated progress in existing `docs/plans/ROADMAP_JOINT_WORKING_PLAN.md`; WS-20-specific `docs/roadmap-log/**`; `docs/acceptance/IMPLEMENTATION_STATUS.md`, `docs/acceptance/ACCEPTANCE_RUNBOOK.md` and WS-20 evidence under `docs/acceptance/command-console/receipts/`. Preserve every existing owner, checkbox, receipt, scope and decision. Existing CX-23 documentation boundary remains; do not edit other owners’ implementation/feature plans or WS-17’s verification evidence. No runtime code, checker enforcement, config, credentials, access, provider workload, production write, restart or deployment.
- **Next step:** codex: after this claim lands, publish exact source/installed-artifact identity, reconcile reusable receipts and run safe checks in the isolated workspace; update evidence as it arrives. WS-28 owns cleanup repair; WS-17 owns exact-source cross-review and release verification. larry: retain live acceptance, checker and later deployment decisions.
- **Updated:** 10-18 (Larry-authorized acceptance execution claim; no gate closed)

</details>

<details id="ws-21">
<summary>WS-21 — Supporting display transfer: one validated, confirmed route · Claude implementation, Codex review</summary>

### Acceptance checklist — remaining

#171 is merged and deployed in `bde22bb`; merge/deploy are not pending acceptance tasks. The fields below reuse #172/#174's pending corrections; their other integration and WS-21 plan update remain Claude-owned.

- [ ] **Larry / Codex · real transfer:** Using voice and the pointer route, send an existing weather/radar result to the intended external screen. The actual result and screen match; success is spoken only after content/placement confirmation. Conversation stays on main, with radar controls/pins/reading state retained.
- [ ] **Larry · repeated request:** Ask for the same transfer again. Mortimer truthfully says “already showing”; identity stays the same, with no reopening, duplicate fetch or extra window.
- [ ] **Larry / Codex · rejected destinations/content:** With monitor unplugged, the request says unavailable and opens nothing. Stale/closed/protected result and unknown/disconnected-screen cases refuse before changing content or placement; console-screen targets are refused.
- [ ] **Larry / Codex · disconnect during confirmation:** Unplug during an in-flight transfer and exercise an unconfirmed transfer. A truthful failure restores/clears the prior selection and closes the window opened by the failed request; no empty leftover, stale locator or undoing a newer successful transfer.
- [ ] **Larry / Codex · placement and inventory:** Requested/published inventory agrees with the actual result, content, presentation and hardware screen. Applicable detach lands on the named connected screen; valid newer transfers supersede earlier ones without false success or destroying the newer state. Record exact-build outcomes and keep conversation on main throughout.

Source: [supporting-display plan §§4–5](docs/plans/MORTIMER_SUPPORTING_DISPLAY_TRANSFER_PLAN.md). Requires the physical external monitor; existing regression tests are implementation evidence, not a substitute for these live checks.

**Workstream:** Larry, 10-03, on deployed `63aaeef`: asked to put the weather radar on the external monitor, Mortimer said it was there while the supporting display opened empty (two `display_popout` calls, both `ok`). Codex's audit found five defects: a voice command that opens the window without content, success reported before the app confirms, detach accepting unknown results, screen IDs that placement does not recognise, and an incomplete contract and inventory. Repair: one coordinator for voice and pointer, validated before anything opens, confirmed before success is spoken.

- **Owner:** `claude` (implementation); `codex` reviews before merge
- **Status:** landed via PR #171, merged as `bde22bb` and deployed in `bde22bb` on 10-03 16:34 EDT; Mac external-display acceptance open
- **Implemented by:** Claude (Cowork)
- **Remaining work / acceptance:** Codex reviewed `43f3d5b` and found four defects (a refused request superseding a valid transfer, a failed replacement leaving an empty window, fixed-panel detach ignoring `screen_id`, the inventory missing transport results); Claude repaired them in `bb9cf35`, and Larry merged #171 on 10-03. A Codex re-review of `bb9cf35` is not recorded on the PR. Codex's audit tests and probes are archived in `docs/acceptance/supporting-display/codex-audit-2026-10-03/`, with regression twins in `VoiceDisplayAuditRegressionTests` and its four review probes in `SupportingDisplayTransferTests`. Deployed in `bde22bb` on 10-03 (clean receipt). Remaining: the external-display checks on the Mac.
- **Model version:** not recorded; do not infer from system name.
- **Where:** main (PR #171, merge `bde22bb`)
- **Plan:** `docs/plans/MORTIMER_SUPPORTING_DISPLAY_TRANSFER_PLAN.md`
- **Scope:** `jarvis/bot/ui_control.py`, `jarvis/bot/console_actions.py`, `UI_CONTROL_ADDENDUM` in `jarvis/prompts.py`; the display-transfer, panel and screen parts of `jarvis/bot/console_protocol.py`, JarvisKit `ConsoleProtocol.swift`, `App/ConsoleActionRegistry.swift`, `App/ConsoleActionCoordinator.swift` and the inventory in `Stores/WorkspaceStore.swift` (shared with WS-17, see CX-16); `App/UICommandRouter.swift`, `App/AppMessageRouter.swift` (console results for display transfers only), new `App/SupportingDisplayCoordinator.swift`, `App/MortimerHostApp.swift` (wiring only), `Placement/ScreenPlacement.swift`, `Placement/WindowPlacement.swift`, `Placement/DisplayPlacementPolicy.swift`, `Stores/PanelStore.swift`, `Display/DisplayWindowView.swift`, `Display/DisplayWindowStore.swift`, `docs/acceptance/supporting-display/**`, the display menus in `Console/ConsoleActionBar.swift` and `Display/WorkspaceView.swift`; tests for each
- **Next step:** larry: on the `bde22bb` deployment (10-03), with the external monitor: ask for the weather radar on the other screen (it appears there and Mortimer says so), ask again (already showing), ask with the monitor unplugged (Mortimer says it isn't connected), and check the conversation stays on the main screen. codex: if you re-reviewed `bb9cf35`, record the result here (post-merge).
- **Updated:** 10-07 (reuse of #172/#174 pending wording under WS-20 claim #192; live acceptance unchanged)

</details>

<details id="ws-05">
<summary>WS-05 — Model access: subscriptions, APIs and SAYGM · Codex</summary>

### Acceptance checklist — remaining

PR #177 is merged. Its green CI and localhost-only tool proof do not close live model or rollout acceptance.

- [ ] **Larry · prerequisites:** Decide the exact private `REPO_MAP` → Claude probe, provide an operator-issued service identity, assign the native-readiness test repair on main, and settle manual/private/public-crawl source authority. Document these before dependent provider or developer work.
- [ ] **Claude · review:** Record the cross-system review of merged #177; its merge is not evidence that this review happened.
- [ ] **Codex / Larry · baseline and release identity (MAR-A):** Freeze the candidate, verify the running app/backend/effective configuration, and capture representative quality, queue time, first useful output, total duration, calls and route/billing attribution. Historical missing measurements stay unknown.
- [ ] **Codex · effective routing and privacy (MAR-B/C/D/G):** On enabled workloads, saved route/model selections hold; unavailable models refuse; prompts, tool results, council calls and logs retain their actual source restrictions. Manual and crawl routes need complete proof; cancellation, recovery, bounded budgets, independent council identities and dedicated memory routes remain correct.
- [ ] **Codex / Larry · subscriptions (MAR-F; shares WS-02 evidence):** Validate the exact service-resolved runtime/model/controls and actual authenticated workload. Claude 2.1.291 is unverified; Codex tool workloads remain unsupported. Prove isolated sign-in, no inherited API credentials, cleanup and truthful exhaustion without paid fallback.
- [ ] **Codex / Larry · SAYGM (MAR-E):** A catalog-confirmed, eligible confidential route must exist before the synthetic confidential pilot; record model/tier/capabilities and required attestation. The current 64-model catalog advertises zero confidential models, so this gate is blocked rather than passed by catalog access.
- [ ] **Codex / Larry · representative pilots (MAR-I):** Complete equivalent baseline/candidate research retrieval, a real nonempty developer edit with all 12 sandbox checks, independent holdout quality and rollback, and synthetic confidential-memory cases. Verify exact source/parent ownership, constraints, cancellation and cleanup; a no-op or four-operation mock cannot close the developer pilot.
- [ ] **Larry, supported by Codex · controls (MAR-H):** Exercise native and spoken route selection, draft/confirm/cancel, unavailable choices and stale selections. The visible result and actual route agree; existing voice, results and monitor behavior remain intact.
- [ ] **Codex / Larry · quality and latency:** Compare cold/warm representative tasks with the same fixtures and rubric. Local acknowledgement ≤250 ms; short sub-agent median adds ≤1 second; added p95 delay >2 seconds requires review. Research/development use total time and quality; background work preserves voice priority.
- [ ] **Larry / Codex · account and rollout (MAR-J):** Record account allowance, billing source and paid-overage settings; unknown cost stays unknown. Approve staged defaults only after the preceding gates pass, verify quota/queue behavior with no API fallback, and record the tested/deployed configuration and rollback.

Sources: [model-use plan §§11, 14–15](docs/plans/MORTIMER_MODEL_USE_ENHANCEMENTS_PLAN.md), [current status and receipts](docs/acceptance/model-use-enhancements/STATUS.md). Source approvals and account decisions here are pending tasks, not authorization supplied by this checklist.

**Workstream:** Model Use Enhancements MAR-A…J (checklist in §7)

- **Owner:** `codex`
- **Status:** landed foundation via #177 (`c38d895`), owned-source fixture repair via #200 (`a5b6f88`), and bounded child-directory isolation via #201, merged as `83d90e8` on 10-10 (source `08c0635`, final head `de4381c`; all five CI checks passed). Larry approved revised `08c0635` for offline WS-17 verification only on 10-10. That comparison against candidate `59d57ea` is running; no result or live acceptance is claimed. Broader model/runtime/rollout acceptance remains open; no production activation or deployment
- **Implemented by:** Foundation contributions are not fully itemized; WS-02 isolation and MAR-A baseline work are Codex
- **Remaining work / acceptance:** Codex: complete the remaining acceptance once prerequisites are supplied; Claude: record cross-system review of the merged implementation; Larry: exact source authorization, operator-issued identity, native-test assignment, account and deployment decisions.
- **Model version:** not recorded; do not infer from system name.
- **Where:** bounded fixture branch `codex/ws05-capability-fixture-20261007`; #201 merged as `83d90e8`, source `08c0635`, final head `de4381c`. Documentation follow-up [PR #202](https://github.com/Larryfix71566/jarvis-voice-ai/pull/202) records the merged repair, exact CI and revised-reference approval. Original main claim #199 (`99993eb`) and #200 (`a5b6f88`) remain. [Notifier isolation evidence](docs/acceptance/model-use-enhancements/receipts/mar-capability-notifier-isolation-2026-10-09.json)
- **Prior landed foundation:** main (PR #177, merge `c38d895`); source branch `codex/ws05-execution-20261005`; claims #175 (`66198c5`), #176 (`0b6723c`), #178 (`0960373`), #179 (`fb3e1aa`) and #180 (`4a2d4aa`); merged implementation #177 (final head `06a7ad5`), frozen ordinary source repair `50daa8b`; advisory scope #181 merged as `ac8eb7a` and integrated before edits; advisory budget/source/integration `6007479` / `c091d7e` / `5da9b47`; descendant budget/council/review `cc420bf` / `df80223` / `58b4e21`; preflight repair `7d74226`; prerequisite claim #182 merged as `d5d8cae` and integrated before hash/storage edits; tokenizer recipe scope #183 merged as `4d2a3ce` and integrated before edits
- **Plan:** `docs/plans/MORTIMER_MODEL_USE_ENHANCEMENTS_PLAN.md`
- **Scope:** model-access policy/execution/preferences and subscription-tool bridge only: `jarvis/model_routing.py`, `jarvis/model_preferences.py`, `jarvis/model_execution.py`, `jarvis/subscription.py`, `jarvis/subscription_tools.py`, `jarvis/saygm.py`, `jarvis/privacy_policy.py`, `config/model_access.yaml`; prospective route/billing/duration metadata in `jarvis/usage_ledger.py` and `jarvis/llm_client.py`; bounded privacy source/sink repairs in `jarvis/agents/delegate.py`, `jarvis/memory_model.py`, `jarvis/memory_extraction.py`, and `jarvis/memory_sweep.py` (enabled-mode policy/execution only; preserve routing-off compatibility); model-route endpoints in `jarvis/admin/server.py`, route diagnostics in `jarvis/status/`, model-execution integration in `jarvis/agents/base.py` and `jarvis/bot/model_route_tool.py`; `macos/MortimerHost/Sources/MortimerHost/Drawer/RepoTab.swift`, model-route types in `macos/JarvisKit/Sources/JarvisKit/AdminAPI.swift`; related model-access tests and verification/pilot scripts; `docs/plans/MORTIMER_MODEL_USE_ENHANCEMENTS_PLAN.md`, `docs/acceptance/model-use-enhancements/**`, shared architecture/model-route references. Additional bounded MAR-B/D/G scope, claimed before edits: `jarvis/model_budget.py` for optional task-level configured-price admission; typed host source/result classification and payload-free early MCP error sinks in `jarvis/skills/registry.py`; policy propagation/retrospective MCP-buffer redaction in `jarvis/runlog/store.py`; repository source-path traversal validation only in `mcp_servers/mcp_repo/logic.py`; canonical identity validation only in `jarvis/agents/upgrade_agent.py` and `jarvis/council/config.py`. Related tests stay in this row; do not alter skill permission declarations, sandbox authorization, model/endpoint pins or historical fixtures. No WS-17/WS-21 console/result files or self-edit allowlist edits. Further bounded execution/source scope claimed before edits: per-run route/profile snapshots, tool-result policy, shared limits and enabled-mode no implicit failover in `jarvis/agents/upgrade_agent.py` (including AppBuildAgent); `jarvis/development_sources.py` for host-proven development source classification and `jarvis/development_attestation.py` for authenticated creator source receipts; source-provenance adapters only in `jarvis/selfedit/service.py`, `jarvis/agents/workspace.py` and `jarvis/skill_authoring.py`; authenticated creator result transport only in `jarvis/bot/server.py` `_dispatch_creator` and `jarvis/admin/server.py` creator association/tool endpoints; host source/session snapshot and receipt verification only in `sandbox/workspace.py`, `sandbox/session.py` and `sandbox/files.py`. Preserve all sandbox read/write/ceremony permissions, authorization, publication/validation gates, runtime lifecycle and source exclusions; no host execution bypass, broader public-data grant, account activation or production change. Further bounded council/MCP scope claimed before edits: `jarvis/council/council.py` and `jarvis/council/__main__.py` for one coordinator budget, trusted child sponsorship through proposer/judge/shadow/planning/replay calls, checked member routes, cancellation and authenticated thread-context propagation; bounded council/planning/research job budget and host-source policy threading in `jarvis/admin/server.py`. `mcp_servers/mcp_selfedit/server.py`, `mcp_servers/mcp_selfedit/logic.py`, `mcp_servers/mcp_apps/server.py` and `mcp_servers/mcp_apps/logic.py` for hidden request/response source-metadata adapters only; authenticated ordinary self-edit preview/start/run/read/write/status/finish and app-build job/submit source transport in `jarvis/admin/server.py`; corresponding host source bindings in `jarvis/development_sources.py`, receipt variants in `jarvis/development_attestation.py` and source-before-sink integration in `jarvis/skills/registry.py`. Related tests remain WS-05. Preserve all model identities, explicit council tier/seed/effort choices, single observed-usage accounting, sandbox read/write/ceremony/publication/validation gates, inactive production flags and legacy routing-off behavior. No skill permission declarations, GitHub client/template rewrites, WS-17/WS-21 files or self-edit allowlist changes; unknown/private foreign application source still requires a real host approval. Further bounded advisory source transport scope claimed before edits: `jarvis/advisory_sources.py` for separate authenticated planning/research caller and retained-action proof, `mcp_servers/mcp_web/server.py` and `mcp_servers/mcp_web/logic.py` for hidden request/response metadata only, and `jarvis/research/crawl.py` for host-acquired source/origin evidence and confidential defaults for unverified bytes. Existing WS-05 Base/Registry/model-budget/admin/self-edit/attestation paths may bind the actual Developer or Analyst caller, original durable host budget, accepted input floor before operation, cancellation/deadline ownership and signed results before sinks. Preserve workspace and creator protocol separation, all permissions, explicit council membership/model floors, research workflow/scorer behavior, routing-off parity and manual-action authorization. JSON limits, bearer authentication, HTTPS or crawler success cannot grant source approval or money allowance; no UI changes, provider activation or broader public-data grant. Further bounded image-source prerequisite scope claimed before edits: `sandbox/artifacts.py` only for exact path/SHA-256 pins of independently reviewed synthetic credential test fixtures, plus directly related source-archive tests. Keep `SECRET`, all path/source exclusions, historical baseline pins and both scanner enforcement sites unchanged; no path-only/pattern exemption, fixture-body edit, permission/lifecycle/profile waiver or production settings change. This scope does not include sandbox runtime/control/images/setup behavior. Further bounded pilot-isolation prerequisite scope claimed before edits: new stdlib-only `jarvis/storage_context.py` for immutable host-owned database/preference overrides, context propagation and retained worker drain before temporary cleanup; `jarvis/db.py` only its default-path resolver, with explicit paths and all migrations/DDL unchanged. Existing WS-05 `jarvis/usage_ledger.py`, `jarvis/model_routing.py`, `jarvis/model_execution.py` and pilot scripts may read that host-only context and retain owned asynchronous worker lifetime; related tests verify real DB/ledger isolation, foreign-thread separation, cancellation/drain and legacy parity. Do not mutate process-global database/preference environment to isolate a pilot; no production storage, schema, limit, route, source approval or account setting change. Further bounded tokenizer-image prerequisite scope claimed before edits: `sandbox/guest/prepare.sh` only, to acquire the officially SHA-256-pinned English `punkt_tab` data required by locked NLTK/Pipecat, install it under the protected Python prefix (`.venv/share/nltk_data`) during fresh online image preparation, and prove cold tokenizer use before preparation completes. Related recipe/resource acceptance tests and receipts remain WS-05. Preserve current hydration/cache ownership and read-only worker access, all twelve profile checks, source scanner/exclusions, network/audio/clipboard isolation, operator credentials and installed image/settings pointers. No RTVI/voice/test assertion edit, sleep/skip/timeout waiver, runtime/control/images behavior change, provider/model/endpoint/allowlist change or production activation. Further bounded capability-fixture scope assigned by Larry 10-07: `tests/unit/test_claude_developer_capability.py`, using the existing frozen current-worker-owned source fixture in `tests/unit/test_model_use_development_pilot.py` (helper changes only if necessary), directly related fixture regression tests, and this row's plan/evidence/log. Preserve every strict owner/link/mode/read guard, source bytes and scanner/pins, protected baseline, and all twelve verification checks; do not chown/adopt baseline files, change hydration/lifecycle/profile behavior, add test skips, weaken assertions or raise timeouts. Any new baseline/reference requires separate review and approval before another independent comparison.
- **Next step:** codex: finish and record the unchanged twelve-check offline WS-17 comparison on approved `08c0635` → frozen candidate `59d57ea` in WS-17; preserve the prior 10-09 `a5b6f88` → `ce6cde8` pass and later failed CI as separate records. Larry’s 10-10 reference approval grants no new Claude source transmission, release, deployment, provider call or account/routing activation. Other source/identity/native-readiness/manual-source/account/runtime/workload and rollout decisions remain unchanged; all broader acceptance flags stay false. Default CLI 2.1.291 and actual native capability remain unverified; the catalog still offers zero eligible confidential models. No source/policy/scanner/runner waiver or production change
- **Updated:** 10-10 (#201 merged `83d90e8`; five CI checks passed at `de4381c`; Larry approved `08c0635` for offline WS-17 comparison only; comparison running)

</details>



<details id="ws-01">
<summary>WS-01 — Reliability, privacy and memory gaps · Codex</summary>

### Acceptance checklist — remaining

The integration, deployment history and PR #125 claim-order repair retain their recorded evidence.

- [ ] **Codex / Larry · preparation:** Freeze the actual deployed candidate; receipts identify source, app/backend/configuration, executable hash and date. Follow current CC7a answer routing rather than the older captions/result-card wording.
- [ ] **Larry, supported by Codex · display recovery:** Exercise remaining research, graph and append-only developer-result scenarios: close/reopen, monitor unplug/reconnect and backend/voice reconnect. One owner and one bounded supporting stage remain; IDs, selection, pins and drafts survive with no duplicate fetches or window growth. Untested mirrored/three-screen hardware cases remain explicitly open.
- [ ] **Larry / Codex · Atlas freshness:** Verify authenticated refresh, source change, empty/partial failure, expired authentication, reconnect and late responses. Context precedes research results; state and limits are truthful; moving views does not duplicate fetching.
- [ ] **Larry / Codex · spoken, sharing and accessibility journeys:** Verify remaining real audio/result actions and text/image preview, copy, save, share-picker cancel/return and approved inbound transfer. Target/provider, bounds, cancellation and cleanup are visible; VoiceOver, keyboard and font/accessibility settings work. Preserve the narrower accepted WS-17 checks and WS-08 sign-off.
- [ ] **Owning systems / Larry · dependencies:** Complete the applicable audio/security/C8 gates under their existing protocols, WS-02/05 model gates and WS-10 memory rollout. UI2-04/09/13 await WS-17's conversation/card/Recents/reuse acceptance; speaker gating stays off pending its own effectiveness evidence.
- [ ] **Codex / Larry · release closure:** Obtain the exact-candidate independent verifier, prove rollback preserves data/preferences and loaded identities, and record five stable daily-driver days. Material changes restart affected measurements and the frozen-candidate observation period.

Sources: [verified-gap plan §§12–14](docs/plans/MORTIMER_VERIFIED_GAP_CLOSURE_PLAN.md), [acceptance runbook](docs/acceptance/ACCEPTANCE_RUNBOOK.md). Reuse valid receipts from the owning rows rather than repeat the same physical test for every workstream.

**Workstream:** Verified gap closure GC24-00…06: execution lifecycle, privacy log redaction, memory admission, Atlas

- **Owner:** `codex`
- **Status:** landed: action-claim settlement-order fix in PR #125 (`ab2a2ef`); earlier WS-01 foundation deployed; live acceptance open
- **Implemented by:** Codex
- **Remaining work / acceptance:** The app-build/self-edit action-claim ordering fix landed and PR #115 passed full CI with it. Larry retains the original physical/live acceptance.
- **Model version:** not recorded; do not infer from system name.
- **Where:** main (`539f8f6` foundation; PR #125 `ab2a2ef` claim-order fix); shared-roadmap documentation: `codex/isolated-20260924`
- **Plan:** `docs/plans/MORTIMER_VERIFIED_GAP_CLOSURE_PLAN.md`. The 12 gap-index plans fold into it (CX-05).
- **Scope:** Existing WS-01 scope includes execution routes in `jarvis/admin/server.py`. This bounded follow-up changes only app-build/self-edit terminal claim ordering there, focused tests in `tests/unit/test_admin_appbuild.py` and `tests/unit/test_admin_selfedit.py`, this row's plan/acceptance evidence, and `ROADMAP.md` status. It does not edit WS-08 orb files or alter idempotency decisions.
- **Next step:** Complete the original WS-01 physical/live acceptance on a frozen deployed candidate. The action-claim CI repair is on main; no new WS-01 code change was found in this read-only review.
- **Updated:** 10-02 (source/receipt recheck; no new live gate)

</details>

<details id="ws-04">
<summary>WS-04 — Remote access · Codex; Larry decides activation</summary>

### Acceptance checklist — remaining

R1 foundation and the remote-bind guard are merged. Local preparation, local activation and remote binding are separate gates.

- [ ] **Larry · prerequisite decision:** Choose supervised setup, one-time CLI or Mac pairing for local token onboarding. The R2 recommendation is not a substitute for the unresolved roadmap decision.
- [ ] **Codex · implementation prerequisite:** Build and validate the chosen vault/Keychain onboarding path. Under the proposed supervised path: mint once, pass secrets through stdin, verify vault/Keychain readback, refuse existing storage and clean only this attempt's partial state. No token appears in argv/logs/temp files/receipts; preparation changes no auth or remote flag.
- [ ] **Codex · disposable acceptance:** Verify first-run success, repeat refusal without another active identity, interrupted retry and failures after DB/vault/Keychain writes. Check the exact Keychain service/account, both-flag combinations and unauthenticated 401 behavior using disposable credentials.
- [ ] **Larry / Codex · live preparation:** With separate authorization, record exact source, presence/readback and both database identities; authentication stays off and bot/admin listeners stay loopback-only. Preparation alone does not close enabled-mode or Skills acceptance.
- [ ] **Larry / Codex · local activation, if approved:** Bare bot/admin requests return 401; authenticated Connect, voice/status and Skills Versions/inventory work. Verify actual sockets/no off-host listener, immediate device revocation and rollback to prior loopback behavior with remote binding false.
- [ ] **Larry · spoken check:** Record the still-unverified real `system_status` answer on the chosen frozen setup; health probes and native tests alone do not close this spoken gate.
- [ ] **Larry / Codex · remote mode only if separately chosen:** Record the remote-bind decision. If activated, complete G2/§8 tunnel/ACL/Funnel, LAN and tailnet socket, authenticated voice/barge-in/Runs, POST/PATCH offer, Keychain and immediate-revocation checks. If deferred, record that limitation rather than claiming remote access accepted.

Source: [remote-access plan Addenda R1/R2 and §8](docs/plans/MORTIMER_REMOTE_ACCESS_PLAN.md). This checklist grants no credential-minting or activation authority.

**Workstream:** Remote access T2: bearer tokens, fail-closed bind, Tailscale

- **Owner:** `codex` (Larry, 09-27)
- **Status:** landed foundation: R2 local-only design and separate remote-bind guard merged in PR #149 (`a39136a`) after the 09-30 `39fc6f9` deployment; the guard was deployed in `7c4637e` on 10-02 with authentication and remote binding still off. Its factual R2 status/header/checkpoint is reconciled via this PR after documentation claim #187 (`9be5dab`). Token provisioning and enabled-mode acceptance remain open
- **Implemented by:** Codex (remote foundation and R1)
- **Remaining work / acceptance:** Codex prepares local-only onboarding after Larry selects the method and a fresh provisioning slice is claimed. Larry separately decides credential preparation, local activation and any remote bind; live acceptance remains open
- **Model version:** not recorded; do not infer from system name.
- **Where:** main (R1 foundation `539f8f6`; R2 guard PR #149 `a39136a`; documentation claim #187 merged as `9be5dab`). R2 status correction publication: `docs/ws04-guard-status-20261006`, via this PR. Later provisioning requires its own fresh claim after the method decision.
- **Plan:** `docs/plans/MORTIMER_REMOTE_ACCESS_PLAN.md` (R1 implemented; R2 local-only onboarding design)
- **Scope:** Historical/inactive foundation scope: `jarvis/auth.py`, `jarvis/authmw.py`, `jarvis/bind.py`, `jarvis/urls.py`, `jarvis/bot/server.py`, auth middleware and bind in `jarvis/admin/server.py`. Plus the integration points in CX-11: `jarvis/bot/status_tool.py`, `scripts/deploy_main.sh` health checks, `mcp_servers/mcp_selfedit/logic.py` headers. The R2 design proposes `scripts/provision_local_auth.py`, a small JarvisKit stdin-to-Keychain executable, its `Package.swift` target, and tests; no provisioner is implemented.
- **Next step:** larry: select the local token-onboarding method (supervised deploy setup, one-time CLI, or Mac pairing). codex: after that decision, claim a fresh provisioning slice before implementing and validating the chosen vault/Keychain path. Local activation and any remote bind remain separate decisions; the R2 guard status documentation is reconciled.
- **Updated:** 10-06 (R2 guard status reconciled after claimed docs slice; no new live acceptance)

</details>

<details id="ws-02">
<summary>WS-02 — Subscription runtime isolation · Codex</summary>

### Acceptance checklist — remaining

Existing Codex loopback and Claude public-fixture proofs retain their narrow scope; neither certifies billing or real developer-workload acceptance.

- [ ] **Codex · runtime identity:** Record the service-resolved executable/version/hash, exact model, sign-in/input/output contract and customization/tool suppression. A changed or unverified runtime stays unavailable; Claude 2.1.291 currently needs validation.
- [ ] **Codex · installed-runtime isolation:** Prove stdin-only prompts, temporary working directory outside the repo, allowlisted environment, no inherited unrelated credentials/endpoints or project hooks/plugins/MCP/built-in tools, and refusal of malformed/contradictory terminal output.
- [ ] **Codex · lifecycle:** On the actual accepted runtime, success/failure/timeout/cancel clean their children and temporary state; termination grace is ≤2 seconds before escalation/reaping, and no late result is delivered.
- [ ] **Codex / Larry · authenticated workload:** Execute the exact supported model/capabilities through Mortimer without implicit model/account/API fallback. Regenerate the full local runtime receipt where needed; text login or the sanitized loopback receipt cannot activate unsupported capabilities. Shares representative workload evidence with WS-05.
- [ ] **Larry · account evidence:** Verify subscription/API identity, account allowance and paid-overage settings using supported account surfaces. Call success and list-price metadata alone do not prove zero cost.
- [ ] **Codex / Larry · release:** Record exact source/runtime/configuration and service-resolved authentication/isolation, cleanup and deployed behavior; activate only capabilities whose required receipts and workload gates pass.

Sources: [subscription-isolation plan SR-1…SR-6 and completion criteria](docs/plans/MORTIMER_SUBSCRIPTION_RUNTIME_ISOLATION_PLAN_2026-09-25.md), [latest model-use evidence](docs/acceptance/model-use-enhancements/STATUS.md).

**Workstream:** Subscription runtime isolation (GC24-04)

- **Owner:** `codex`
- **Status:** landed; deployed in `539f8f6` on 09-28 and again in `39fc6f9` on 09-30; live capability/isolation gates open
- **Implemented by:** Codex
- **Remaining work / acceptance:** Codex; live account checks as required
- **Model version:** not recorded; do not infer from system name.
- **Where:** main (`539f8f6`)
- **Plan:** `docs/plans/MORTIMER_SUBSCRIPTION_RUNTIME_ISOLATION_PLAN_2026-09-25.md`
- **Scope:** `jarvis/subscription.py`
- **Next step:** Run the installed-runtime capability, provider, billing and isolation checks in the WS-02 plan; an authenticated text probe alone does not close them.
- **Updated:** 10-02 (source/plan recheck; no new live gate)

</details>

<details id="ws-03">
<summary>WS-03 — Skills Workspace and skill creator · Codex</summary>

### Acceptance checklist — remaining

SW-B and SW-C are already accepted (2/12). Recorded selection/navigation timing passes are retained; they do not close the remaining SW-K checks.

- [ ] **Codex / Larry · remaining deployed baseline (SW-A):** Original skills, compact Conversation, voice/mute/orb, eight tabs, memory, Atlas, sharing and developer aggregation retain behavior; preexisting faults are identified separately.
- [ ] **Codex / Larry · recorded runs (SW-D):** Use actual successful/failed/skipped/unknown/legacy runs and duplicate/out-of-order/reconnect events. Intended steps stay distinct from the actual trace, progress is never invented, and details open without extra windows. Owner-scoped activity depends on WS-04 authentication.
- [ ] **Codex · privacy and owner boundaries (SW-E):** Verify canaries cannot leak through inventory, SQL/JSONL, diagnostics, argv, exports, screenshots, examples, evaluations or supporting displays, including wrong-owner requests.
- [ ] **Codex / Larry · real sandbox (SW-F):** On an authorized creator draft, the actual VM permits only approved package/fixture changes; offline validation and changed-candidate rejection work. No host fallback, live-checkout write, network/credential mount or receipt-drift activation. Depends on authentication, real VM and source/model readiness.
- [ ] **Codex / Larry · paired quality evaluation (SW-G):** Run six reviewed cases × two repetitions × baseline/candidate: 12 complete pairs / 24 trials with the frozen rubric. All deterministic safety checks pass; blinded quality passes ≥10/12 and is no worse than baseline. Record latency/calls/cost; eligible provider/budget authorization is a prerequisite.
- [ ] **Codex / Larry · lifecycle and activation (SW-H):** Duplicate requests produce one job/PR; cancel prevents late publication; restart reconciles uncertainty. Exact-diff review, merge, deploy and atomic activation remain separate; in-flight revisions stay stable and rollback restores the accepted version. Depends on SW-F/G and maintainer review.
- [ ] **Larry / Codex · voice/accessibility (SW-I):** Every control uses its shared voice action; stale/ambiguous targets clarify. VoiceOver, keyboard, large type, contrast and application accessibility settings work; search/filter persists and steps are usable without hover.
- [ ] **Larry / Codex · physical displays (SW-J):** One/two displays, two research results and a creator run: move, close/reopen, unplug during validation, reconnect and restart. One append-only creator tile retains steps/retries/selection; no duplicates, focus theft, orphan or unintended new job.
- [ ] **Codex / Larry · remaining performance (SW-K):** Paired voice p95 regression ≤50 ms; ten-minute library/live-trace memory growth ≤10 MiB, tied to the exact Mac/build. Retain the already-recorded ≤20 ms selection and ≤100 ms navigation sub-results.
- [ ] **Codex / Larry · release and handoff (SW-L):** Required frozen suites, actual app/backend/config/package identities, visible ready/loaded state, current evidence and rollback agree. Required authentication, evaluation/activation and parent privacy/model gates are satisfied; failed historical full-profile receipts remain failed.

- [x] **Codex · Versions wording subcheck:** On deployed native `bde22bb`, the intended dormant-auth explanation is visible and corroborated by the local 200 catalog / 503 Versions response; [dated proof](docs/acceptance/skills-workspace/receipts/versions-wording-2026-10-06/receipt.md). This does not close SW-A or change the 2/12 full-gate count.

Source: [Skills plan §12, SW-A…SW-L](docs/plans/MORTIMER_SKILLS_WORKSPACE_IMPLEMENTATION_PLAN.md). Dependencies are WS-04 local onboarding, WS-05 source/model readiness and the applicable parent release gates.

**Workstream:** Skills Workspace and skill creation (T6; supersedes `MORTIMER_SKILL_AUTHORING_PLAN.md`). Its own view, separate from the Workflow Viewer (Larry, 09-27)

- **Owner:** `codex`
- **Status:** landed foundation; the deployed Versions dormant-auth wording subcheck is verified on `bde22bb` (10-06) and recorded through this documentation PR. PRs #145/#146 are included in the deployed build. SW-A overall and authenticated/creator/provider/voice/display/activation gates remain open; SW-B/C remain the only accepted full gates (2/12).
- **Implemented by:** Codex
- **Remaining work / acceptance:** Codex; Larry for human review and physical acceptance
- **Model version:** not recorded; do not infer from system name.
- **Where:** main (foundation `539f8f6`; PRs #145/#146; documentation claim #186, merge `2d41ccd`). Build-identified Versions evidence is published through this documentation PR.
- **Plan:** `docs/plans/MORTIMER_SKILLS_WORKSPACE_IMPLEMENTATION_PLAN.md`
- **Scope:** `jarvis/skill_*.py`, `jarvis/agent_skills.py`, `jarvis/selfedit/skill_policy.py`, `/api/skills*` in `jarvis/admin/server.py`. The five console view-mode Swift files are **shared with WS-07's landed Workflow Viewer**: add a new `skills` mode beside `workflows`; do not replace or restyle the viewer.
- **Next step:** codex: finish the remaining frozen-build SW-A baseline and recorded-run/privacy checks as their prerequisites become available. larry: select WS-04 onboarding and decide eligible source/provider/budget gates, then perform the required voice, accessibility and physical-display checks. Owner-scoped Versions/runtime inventory/creator and activation/rollback remain separate; the dormant-auth wording subcheck is complete.
- **Updated:** 10-06 (build-identified Versions wording only; no new full acceptance gate)

</details>

<details id="ws-06">
<summary>WS-06 — Self-service recovery and model registry · Claude implementation; Larry acceptance</summary>

### Acceptance checklist — remaining

Keep the recorded Swift check and data-level model/subscription/status checks closed. Their spoken counterparts still need live evidence.

- [ ] **Larry / Claude · spoken status:** Ask which models work, whether services are up, whether the app rebuilt and where you are. Answers use actual tools, in one turn without unsolicited terminal commands/delegation. Record the still-open spoken counterparts of checklist #1/#2/#4/#8.
- [ ] **Larry / Claude · external status:** Ask whether the exact named model is available on the subscription, which provider models are new, and whether PRs are open. Replies name the real probe/catalog source and fetch time; the first daily connect reports findings only when something changed.
- [ ] **Larry / Claude · corrected retry:** The failed “Alfreda” request followed by “I meant Alpharetta” succeeds without the old retry lockout.
- [ ] **Larry / Claude · process recovery:** A long developer run survives a three-minute client disconnect and reports its result after reconnect, with no `Available: none`. A controlled `mcp-web` child crash is recovered on the next request, with the successful restart recorded.
- [ ] **Larry / Claude · graph and remaining source checks:** An unknown graph topic produces the truthful overview; structured sports answers or explicitly unconfirmed search fallback match the existing source policy. A one-day reconnect log supplies the recorded transport data.
- [ ] **Larry / Claude · registry split:** Registry/environment verdicts, live delegation and model-picker behavior remain equivalent; the sandbox loop creates a reviewed PR adding a profile on an existing endpoint without altering endpoint/credential ownership.
- [ ] **Claude / Larry · completeness:** Bring the referenced eleven-check Mac list into the existing repository plan and map every item to evidence, including still-open #3/#5/#6/#7/#10/#11. The detailed external checklist is not tracked here, so its numbering must not be guessed. Record the week's no-unsolicited-commands observation and the remaining `model_access.yaml` tier decision.

Sources: [self-service specification acceptance map and P2–P7](docs/plans/MORTIMER_SELF_SERVICE_ACCESS_IMPLEMENTATION_SPEC.md), [recovery plan §4](docs/plans/MORTIMER_SELF_SERVICE_ACCESS_AND_RECOVERY_PLAN.md), [registry split §8](docs/plans/MORTIMER_MODEL_REGISTRY_SPLIT_PLAN.md). These are the repo-backed checks; the eleven-item mapping remains an explicit documentation prerequisite.

**Workstream:** Self-service access and recovery P1–P7, plus registry split P5 (#86's files; merged in the 09-25 landing)

- **Owner:** `claude`
- **Status:** landed; Mac checks open
- **Implemented by:** Claude
- **Remaining work / acceptance:** Larry, guided by Claude. Of the 11 Mac checks: #9 is closed (Swift). #2 passes on data: after WS-14 was deployed, the daily file at 14:11 UTC 09-29 shows the Claude subscription `ok: true`, and Codex `not_installed` is expected. #1 and #4 pass on data. Still open are the spoken answers for #1, #2, #4 and #8, and checks #3, #5, #6, #7, #10 and #11. The tier decision for `config/model_access.yaml` is Larry's.
- **Model version:** not recorded; do not infer from system name.
- **Where:** main
- **Plan:** `docs/plans/MORTIMER_SELF_SERVICE_ACCESS_IMPLEMENTATION_SPEC.md` and its companion `docs/plans/MORTIMER_SELF_SERVICE_ACCESS_AND_RECOVERY_PLAN.md` (added to main in PR #100, CX-09). Registry half: `docs/plans/MORTIMER_MODEL_REGISTRY_SPLIT_PLAN.md`
- **Scope:** —
- **Next step:** Larry runs the spoken and process checks from Claude's checklist (`Claude outputs/checklists/WS-06_self_service_checks.md`), then decides the `model_access.yaml` tier (Claude recommends deny).
- **Updated:** 10-02 (read-only: recorded Mac checks and tier decision remain open)

</details>

<details id="ws-07">
<summary>WS-07 — Voice workflows and Workflow Viewer · Claude</summary>

### Acceptance checklist — remaining

The recorded one-answer-in-the-thread check stays closed. The full five-turn conversation belongs to WS-17.

- [ ] **Claude / Larry · reply-guard evidence:** Review genuine guard events in `log` mode, separating events from startup-setting lines; record precision and false refusals sufficient to judge a switch. The four previously recorded events did not establish this.
- [ ] **Larry · guard-mode decision:** After that evidence, approve keeping `log` or switching to `correct`; record the effective mode and verify correction does not fabricate completed actions or bypass confirmation. No automatic switch is authorized here.
- [ ] **Larry / Claude · remaining workflow live/evaluation record:** Record the planned workflow-enabled/disabled routing and voice evaluation outcomes and the unrecorded end-run live checks; retain prior suite/merge/deploy/memory-archive evidence.
- [ ] **Larry · viewer journey:** “Show me the workflows” and each Workflows button open the gallery; “Show workflows” uses the supporting display. The availability flow shows its three wrapped steps and the five draft cards remain dashed and clearly drafts.
- [ ] **Claude / Larry · closure:** Link the guard decision, viewer and remaining live/evaluation receipts to the exact build. UI2-22's five-turn outcome and any retry-location follow-up remain with their owning rows/backlog.

Sources: [voice-workflows plan Progress, §5 and §12](docs/plans/MORTIMER_VOICE_WORKFLOWS_PLAN.md), [Workflow Viewer §6](docs/plans/MORTIMER_WORKFLOW_VIEWER_PLAN.md).

**Workstream:** Voice workflows phases 1–4, Workflow Viewer, #80 privacy fix, DEPLOY-MAIN

- **Owner:** `claude`
- **Status:** landed (main `0b76f49`); thread-text fix landed 10-02 (#154) and deployed in `7c4637e` on 10-02; Larry's thread check passed on the Mac 10-02 (build `ae70f2c`)
- **Implemented by:** Claude
- **Remaining work / acceptance:** Larry: switch the reply guard from `log` to `correct` once the live log shows its precision. Recounted 09-30: the bot log holds four guard events (09-25, 09-29 twice, 09-30), all `action=logged kind=refusal`; the other `reply_guard=log` lines are startup settings, not events. Still not enough to judge precision. Backlog F1 (retry guard vs a different place) is in this area. Thread text once (10-02 fix): passed, Larry on the Mac 10-02, build `ae70f2c`: a spoken answer showed once in the thread. UI2-22's full five-turn check stays with WS-17.
- **Model version:** not recorded; do not infer from system name.
- **Where:** main
- **Plan:** `docs/plans/MORTIMER_VOICE_WORKFLOWS_PLAN.md`, `docs/plans/MORTIMER_WORKFLOW_VIEWER_PLAN.md`
- **Scope:** —
- **Next step:** larry: guard-mode decision after more live use (four events so far).
- **Updated:** 10-02

</details>

<details id="ws-09">
<summary>WS-09 — Command Console and Atlas acceptance · Larry acceptance</summary>


**Current evidence, 2026-10-17:** [Campaign receipt](docs/acceptance/command-console/receipts/acceptance-campaign-2026-10-17.md) identifies installed `575cc7b`, records the passed WS-18 switch and bounded five-turn conversation evidence, and reconciles the shared runbook to CC7a. All twelve independent checks passed on `9f9bc71`, but the final physical-Mac suite has two repeatable Vision OCR errors and Recents/reuse live failures remain. Parent acceptance remains open; other physical/configuration/coverage cases are not inferred.

### Acceptance checklist — remaining

Reuse valid shared receipts with WS-11 and preserve recorded orb, one-row and partial card/display checks. Older documents reuse some UI2 numbers; the linked requirement title determines the check.

- [ ] **Larry / evidence recorder · preparation:** Freeze source/build/configuration and record loaded path, executable hash and date. Reconcile pre-CC7a runbook wording and map every remaining preservation/C8/native-client requirement to evidence.
- [ ] **Larry · console, accessibility and transcript cleanup:** Check the remaining eight-tab/header-scroll/font/attention/unsent-draft/legacy-layout/keyboard/VoiceOver/contrast/notice interactions. Live user/Mortimer text stays in main history without duplicated compact-rail text or blank transcript-sized space; voice/mic controls remain. Changed UI2-04/13 checks wait for WS-17.
- [ ] **Larry / Codex · Atlas and graph:** Exercise source/provenance inspection, grouping, pins/comparison, graph selection/search/filter/path/camera/fallback and honest missing/truncated data. Authenticated refresh, source changes, failure/reconnect/late data preserve identity/reading state, with no duplicate fetching; live performance/VoiceOver/multi-display evidence remains required.
- [ ] **Larry / Codex · display governance:** Complete the remaining one/two/three/mirrored topology, manual placement, return-all, panel limit, pin-overflow and bounded one-to-four-result-stage checks. Stable IDs, drafts, pins and selection survive; no duplicate renderer, subscription, fetch or window storm. Unavailable hardware remains an explicit limitation; shares WS-21 transfer evidence.
- [ ] **Larry · outward sharing:** Real selected text and image: preview, copy into another app, save/reopen, folder access, cancel and Share-picker return. Only the selected artifact leaves the app; no adjacent private UI. Opening a picker never counts as recipient delivery.
- [ ] **Larry / implementation owner · inbound analysis:** Paste/drop/choose and explicit batches show the exact preview, provider/model and bounded progress; cancellation, failure, reconnect and ephemeral cleanup work. Malformed/oversize/imported-instruction/stale-session/unauthorized-batch tests refuse safely, including storage/diagnostic sinks; no upload or replay without approval.
- [ ] **Larry · complete voice parity:** After WS-17, exercise every new enabled action through voice and the shared pointer/keyboard action, including move/share/select and graph focus/filter/path. Ambiguous/stale targets clarify or refuse; late/unavailable-display outcomes are truthful; mute/PTT/wake and OS-dialog boundaries are preserved.
- [ ] **Implementation/evaluation owner · contracts and compatibility:** Verify ownership/schema/capability negotiation, acknowledgements, stale targets, cancellation, duplicate requests, menu/prompt/voice-fixture parity, old clients, disabled features and native/WebRTC messages. No fabricated success or duplicate side effect; existing evaluation floors and denominator/budgets hold.
- [ ] **Codex / Larry · combined load and glass:** Graph + six panels + maximum accepted attachment load during voice preserves audio and bounded memory. Selection p95 ≤16.7 ms, navigation acknowledgement p95 ≤200 ms, graph pan/zoom p95 ≤33.3 ms, with >10% baseline degradation treated as a regression. Actual developer same-run results stay grouped; supporting tiles and legacy fallback obey Liquid Glass on/off settings.
- [ ] **Verifier / Larry · release closure:** Exact-candidate required suites/CI/independent full-profile receipt pass; rollback preserves drafts/preferences/files and cancels pending transfers. Record loaded versions/hash/health, end-to-end voice/sharing and five frozen-candidate daily-driver days; material fixes restart the observation. Record each remaining gate and Larry's outcome.

Sources: [Command Console plan §8](docs/plans/MORTIMER_COMMAND_CONSOLE_ATLAS_PLAN.md), [release-readiness checklist](docs/acceptance/adaptive-interface/RELEASE_READINESS.md), [Atlas coverage and developer grouping/glass requirements](docs/acceptance/command-console/STATUS.md), [runbook](docs/acceptance/ACCEPTANCE_RUNBOOK.md). UI2-04/09/13 depend on WS-17's conversation/card/Recents/reuse gates.

**Workstream:** Command Console and Atlas release acceptance

- **Owner:** `larry`
- **Status:** landed (PR #99, `4986c10`) and deployed in `39fc6f9` on 09-30; Mac acceptance remains open, with UI2-04/09/13 dependent on WS-17
- **Implemented by:** Codex (Codex desktop; exact model build is not exposed)
- **Remaining work / acceptance:** Larry (Mac/live acceptance)
- **Model version:** not recorded in a handoff receipt.
- **Where:** [PR #99](https://github.com/Larryfix71566/jarvis-voice-ai/pull/99), merged to `main` as `4986c10`
- **Plan:** `docs/plans/MORTIMER_COMMAND_CONSOLE_ATLAS_PLAN.md`
- **Scope:** —
- **Next step:** Complete unaffected physical acceptance on the deployed build. Reconcile the WS-09 response-routing runbook with CC7a before UI2-04/09/13: it still describes one full answer in a result card and brief conversation captions, while CC7a.1 now shows full transcript rows and does not create a WorkspaceResult for ordinary spoken answers.
- **Updated:** 10-02

- [ ] **Single transcript surface (Larry, 2026-09-28):** keep the transcript in the main window; remove the duplicate transcript/captions from the left/compact panel and reclaim the vacated space. Preserve the orb, speaker feedback, microphone/voice controls, and main-window transcript history/accessibility. This supersedes earlier requirements to repeat brief captions in the compact rail; full response/results routing remains unchanged.
  - **Status:** Landed in `main` via PR #99 (`4986c10`) and included in the 09-30 deployment `39fc6f9`; implementation and automated validation complete; user/Mac acceptance remains open.
  - **Implementation owner:** Codex, explicitly dispatched by Larry on 2026-09-29; follows the Codex/Luna handoff specification. **Acceptance:** Larry. **Plan author:** Codex.
  - **Scope:** `macos/MortimerHost/Sources/MortimerHost/Console/OrbFieldView.swift`, `macos/MortimerHost/Tests/MortimerHostTests/CompactConversationTests.swift`, this roadmap and the linked plan progress only.
  - **Implementation handoff:** [WS-09 transcript cleanup — Luna implementation handoff](docs/plans/MORTIMER_COMMAND_CONSOLE_ATLAS_PLAN.md#ws-09-transcript-cleanup--luna-implementation-handoff).
  - **Validation:** focused compact transcript tests 3/3, live response stream 2/2, result router 7/7; full MortimerHost 374 passed, 7 environment-dependent skips, 0 failures. `git diff --check` passed. Render captures inspected at compact widths 512 and 1000; paths and details are in the linked plan.
  - **Log (2026-10-02 review):** PR #99 merged as `4986c10`; Codex’s layout-v2-only compact caption removal was included in the 09-30 deployment `39fc6f9`. WS-17 CC7a.1 subsequently changed ordinary spoken-answer placement in layout 2; that separate behavior is not a WS-09 transcript-cleanup regression. Mac acceptance of the compact-panel cleanup is still unrecorded. Source retains the “Microphone muted” indicator, but automated coverage does not explicitly assert that exact compact status yet.
  - **Close when:** live user and Mortimer speech updates the main-window transcript without a duplicate in the compact rail, in single- and multi-monitor layouts; no blank transcript-sized gap or loss of voice controls/history.

</details>

<details id="ws-10">
<summary>WS-10 — Automatic memory rollout · Claude + Codex implementation; Larry rollout</summary>

### Acceptance checklist — remaining

The provider shadow, offline staged-rollout gate and 28-exchange recovery are already recorded. Synthetic first-20 decisions are not review of real decisions.

- [ ] **Codex / Claude / Larry · preparation:** Freeze the merged release and verify the actual classifier, eligible dedicated memory route, effective automation stage and baseline. Satisfy WS-05 confidential/source gates for every enabled model route; shadow writes no live memory or prompt changes.
- [ ] **Larry, supported by the implementation owners · staged use:** Approve and record one daily-driver day of shadow, then explicit preferences, then corroborated inferences, with the required observation at each stage. Task rules remain tentative until existing workflow confirmation accepts them.
- [ ] **Larry · first 20 real decisions:** Inspect the first 20 live admissions/corrections; each has correct scope/evidence, is reversible, and does not turn assistant/quoted content into trusted user preference or permission.
- [ ] **Codex / Claude · benefit and budgets:** Record counts/denominators against the frozen baseline: preference use, relevant recall, repeated questions, interruptions and stale errors. No recall/preference regression; failing interruption/stale cases improve and zero-error baselines stay zero. Admission p95 ≤200 ms cached / ≤2 s one bounded model call; daily ≤100 candidates / five model calls; latency/cost and configured limits pass the versioned rollout gate.
- [ ] **Codex / Claude / Larry · privacy and voice:** Verify forget/delete/redaction across queue, retrieval, inspection/undo and usage; no duplicate durable rows or unauthorized scope. Restart-safe bounded maintenance preserves ongoing voice and prompts no routine cleanup chore.
- [ ] **Larry / implementation owners · rollback and receipt:** Prove reversible corrections and immediate disable on privacy, scope, duplicate, budget or stale-use regression; record effective settings, stage changes, real benefit/cost and Larry's staged acceptance. The historical recovery remains separate and closed.

Sources: [memory plan B5/B7/B9](docs/plans/MORTIMER_MEMORY_AUTOCONSOLIDATION_PLAN.md), [runbook §5](docs/acceptance/ACCEPTANCE_RUNBOOK.md), [rollout limits fixture](tests/fixtures/memory_rollout_acceptance.json). Existing fixture limits do not constitute live measurement or approval to enable automation.

**Workstream:** Memory automation: staged enablement on the Mac

- **Owner:** `larry`
- **Status:** landed foundation; pending merged-pipeline acceptance
- **Implemented by:** Claude: echo guard and auto-settlement; Codex: durable admission/classification and merge integration
- **Remaining work / acceptance:** Larry: merged-pipeline acceptance and staged rollout
- **Model version:** not recorded; do not infer from system name.
- **Where:** main (merged pipeline deployed in `539f8f6` on 09-28 and in `39fc6f9` on 09-30)
- **Plan:** `docs/plans/MORTIMER_MEMORY_AUTOCONSOLIDATION_PLAN.md`
- **Scope:** —
- **Next step:** CX-07 is resolved in main and deployed (§4). Production admission remains fail-closed according to the last recorded memory status (09-25); this review did not remeasure live stage/benefit/cost. Larry chooses staged Mac enablement only after the recorded monitoring gate.
- **Updated:** 10-02 (read-only; no new live memory gate)

</details>

<details id="ws-11">
<summary>WS-11 — Adaptive interface C8 acceptance · Larry acceptance</summary>


**Current evidence, 2026-10-17:** [Campaign receipt](docs/acceptance/command-console/receipts/acceptance-campaign-2026-10-17.md) identifies installed `575cc7b`, records the passed WS-18 switch and bounded five-turn conversation evidence, and reconciles the shared runbook to CC7a. All twelve independent checks passed on `9f9bc71`, but the final physical-Mac suite has two repeatable Vision OCR errors and Recents/reuse live failures remain. Parent acceptance remains open; other physical/configuration/coverage cases are not inferred.

### Acceptance checklist — remaining

WS-08's orb sign-off and other explicitly recorded partial checks remain closed. Shared WS-09/17/18 receipts may satisfy the same underlying requirement without duplicate runs.

- [ ] **Larry / Codex · candidate and coverage:** Reconcile stale C8 deployment/routing headers; freeze the actual source/fingerprint/loaded artifact/configuration/topology. Map every remaining C8 and P0/native-client row to a dated result; changed UI2-04/09/13 require WS-17 first.
- [ ] **Larry · remaining preservation workflows:** Check remaining legacy/candidate P0 interactions, Agents ticker/model-to-done, Repo/Edit/Memory/Runs round trips, Output/Log lineage, display modes and readable shared-glass/opaque fallback. Use disposable write targets and keep per-row evidence; preserve accepted subparts.
- [ ] **Larry / Codex · visual/accessibility matrix:** Conversation/results at 900×600, 1280×800, 1440×900, ultrawide and portrait external sizes; available Retina/non-Retina; docked/detached tabs, overflow/drafts, long/error payloads, two pins/comparison, graph states and font/keyboard/VoiceOver. No clipping, lost reading state or inaccessible controls. Orb appearance/Reduce Motion sign-off is not reopened; broader application accessibility still needs evidence.
- [ ] **Larry / Codex · remaining physical audio:** Built-in/headphones/AirPods and available alternate devices: mute/PTT, quiet/loud/noise, AI-only, interruption, output switch, reconnect, sleep/wake and mic denial. Preserve intelligibility/pitch/speed, timely truthful channels, wake/barge-in and requests; no echo-only false user turns or duplicate session. Record remaining AirPods echo benches and earbud-removal investigation; share the distinct WS-18 switch-during-answer result.
- [ ] **Larry / Codex · monitor and rollback tails:** Complete remaining applicable one/two/mirrored/three-display, graph/draft-display loss, changed order/resolution, manual intent, close/reopen, lock/sleep/Reset Layout and layout rollback/back cases. Controls become reachable ≤1 second after stable topology; drafts/results/pins/graph state survive with no snap-back over newer manual placement or conversation restart. Existing named topology passes remain bounded to their actual tested scope.
- [ ] **Verifier / Larry · closure:** Exact C5 verifier receipt matches the C8 commit/fingerprint. Each remaining row has positive evidence or an explicit written known-limitation acceptance. Record the outstanding native-client five-day outcome attestation and the separate redesign frozen-candidate observation; a historical layout-1 exception does not certify layout 2.

Sources: [adaptive closure plan C8](docs/plans/MORTIMER_ADAPTIVE_INTERFACE_CLOSURE_PLAN.md), [P0 preservation checklist](docs/acceptance/adaptive-interface/P0-preservation-checklist.md), [native client §8](docs/plans/MORTIMER_NATIVE_CLIENT_APP_PLAN.md), [C8 open items](docs/acceptance/adaptive-interface/C8-open-items.md), [release readiness](docs/acceptance/adaptive-interface/RELEASE_READINESS.md).

**Workstream:** Adaptive interface C8 acceptance

- **Owner:** `larry`
- **Status:** landed foundation; C8 acceptance open (Mac only)
- **Implemented by:** Not attributed by this acceptance-only workstream
- **Remaining work / acceptance:** Larry
- **Model version:** not recorded; do not infer from system name.
- **Where:** —
- **Plan:** `docs/plans/MORTIMER_ADAPTIVE_INTERFACE_PLAN.md`
- **Scope:** —
- **Next step:** `docs/acceptance/adaptive-interface/RELEASE_READINESS.md` still has 3 of 26 UI2 items checked (UI2-01, UI2-04a, UI2-21). UI2-04/09/13 wait for WS-17. Its header still calls `94a5641` the last recorded deployment and the shared runbook describes pre-CC7a answer routing; the acceptance owner must update both against the `bde22bb` deployment (10-03) before using them for a frozen-candidate sign-off.
- **Updated:** 10-07 (reuse of #174 deployment-reference correction under WS-20 claim #192; no C8 sign-off)

</details>


### Proposed enhancements — parked behind current acceptance

<details id="ws-23">
<summary>WS-23 — Acceptance Verifier within Systems · Proposed</summary>

**Workstream:** Extend Systems with a verification role, starting from a repeatable checklist and existing diagnostics. Reuse Council review and independent VM checks; keep live-Mac and physical evidence separate. It observes and evaluates criteria; it is not a repair agent or release authority.

### Requirements and dependencies

- Checklist-first adoption during current acceptance; a new automated profile waits for completed acceptance, explicit implementation dispatch and existing access/privacy prerequisites.
- Read only admitted build identity, approved diagnostics, test outcomes and receipts; bind each observation to an explicit criterion and tested build. Return passed, failed, blocked or untested, with supporting evidence.
- No code edits, weakened tests, waived criteria or release authorization. A successful tool call cannot establish feature success.

### Acceptance checklist — future increment

- [ ] Detect a seeded feature failure and return failed with the matching criterion/evidence.
- [ ] Reject a stale receipt and a receipt for the wrong build as current proof.
- [ ] Mark missing physical hardware blocked or untested; do not infer a pass from VM/CI success.
- [ ] Demonstrate that verification cannot repair code, change criteria or authorize a release.

- **Owner:** `codex` for roadmap intake only; implementation owner unassigned
- **Status:** parked: proposed by Larry 2026-10-17; no implementation or activation authorized
- **Implemented by:** Not implemented by this intake; reuse of existing components must be established in the implementation plan
- **Remaining work / acceptance:** Existing acceptance first, then owner/branch/scope dispatch and a bounded implementation plan satisfying the requirements and unchecked cases above; shared safeguards in intake item 8 apply
- **Model version:** not selected; choose eligible models by workload/privacy during planning
- **Where:** documentation on `codex/roadmap-status-20261017` (PR #211); no implementation branch
- **Plan:** This roadmap intake records requirements; a dedicated canonical implementation plan for this new row is required before its code claim
- **Scope:** Documentation only in this intake. Future code paths, existing-state reuse, schema/migration reservations, feature gate and rollback must be reviewed before claim; no new service, tool grants or migration number reserved here
- **Next step:** larry: finish current acceptance and dispatch implementation ownership when ready; assigned planner: map existing components and prepare the bounded design, tests and rollback before code
- **Updated:** 10-17 (consolidated enhancement intake; unimplemented and unaccepted)

</details>

<details id="ws-24">
<summary>WS-24 — Durable task ownership and restart recovery · Proposed</summary>

**Workstream:** Extend existing SQLite, run logging and durable notification paths with one authoritative overall-task lifecycle. A task is distinct from its individual agent runs, attempts and retries. This is the highest-priority new foundation after current acceptance.

### Requirements and dependencies

- Inventory existing task/job/run/outbox records and reconcile WS-22 lifecycle requirements before selecting schema changes; one authoritative task identity, not parallel task stores.
- Persist goal, source request, owner, completion/stopping condition, next check, dependencies, blocker, approval scope, attempts and latest evidence. Persist checkpoints and future checks rather than relying on session-local timers.
- Exclusive claims and stale-worker fencing; duplicate-action prevention; bounded retries; explicit cancellation. On restart reconcile unfinished/in-flight actions and resume only still-authorized work. An uncertain consequential action must be reconciled before retry, not blindly replayed.
- Deliver saved results through the existing durable notification path even without an active conversation. Preserve stable result/notification identities and delivery deduplication.

### Acceptance checklist — future increment

- [ ] Restart before execution: retain request, owner, dependencies and authorization; schedule one eligible attempt.
- [ ] Restart during execution: reconcile in-flight state and prevent stale or duplicate workers from repeating a consequential action.
- [ ] Restart after result persistence but before delivery: recover and deliver the saved result once at the user-visible level through stable-ID deduplication.
- [ ] Cancelled tasks remain cancelled; two workers cannot execute the same attempt. Expired/revoked approval prevents resume; retry exhaustion stops explicitly.

- **Owner:** `codex` for roadmap intake only; implementation owner unassigned
- **Status:** parked: proposed by Larry 2026-10-17; no implementation or activation authorized
- **Implemented by:** Not implemented by this intake; reuse of existing components must be established in the implementation plan
- **Remaining work / acceptance:** Existing acceptance first, then owner/branch/scope dispatch and a bounded implementation plan satisfying the requirements and unchecked cases above; shared safeguards in intake item 8 apply
- **Model version:** not selected; choose eligible models by workload/privacy during planning
- **Where:** documentation on `codex/roadmap-status-20261017` (PR #211); no implementation branch
- **Plan:** This roadmap intake records requirements; a dedicated canonical implementation plan for this new row is required before its code claim
- **Scope:** Documentation only in this intake. Future code paths, existing-state reuse, schema/migration reservations, feature gate and rollback must be reviewed before claim; no new service, tool grants or migration number reserved here
- **Next step:** larry: finish current acceptance and dispatch implementation ownership when ready; assigned planner: map existing components and prepare the bounded design, tests and rollback before code
- **Updated:** 10-17 (consolidated enhancement intake; unimplemented and unaccepted)

</details>

<details id="ws-25">
<summary>WS-25 — Commitment review with Scheduler and Librarian · Proposed</summary>

**Workstream:** Extend the existing Scheduler and Librarian roles; no new coordinator. Interpret commitments using models, while host code owns durable state, timing and approval enforcement.

### Requirements and dependencies

- Depends on WS-24 durable tasks and each source’s access/privacy prerequisites.
- Identify agreed tasks, dates, dependencies, blockers and people awaiting an outcome; link each commitment to its source evidence and authoritative task.
- Distinguish explicit user commitments from tentative plans, assistant suggestions, third-party requests and inferred priorities. Reconcile correction, completion and cancellation across conversations.
- Prepare useful next steps and reminders without making new commitments or autonomously sending external messages.

### Acceptance checklist — future increment

- [ ] Repeated discussion produces one linked commitment, not duplicate tasks/reminders.
- [ ] A quoted email or third-party request does not become user authorization.
- [ ] A corrected date supersedes its predecessor with provenance; cancelled/completed tasks stop generating reminders.

- **Owner:** `codex` for roadmap intake only; implementation owner unassigned
- **Status:** parked: proposed by Larry 2026-10-17; no implementation or activation authorized
- **Implemented by:** Not implemented by this intake; reuse of existing components must be established in the implementation plan
- **Remaining work / acceptance:** Existing acceptance first, then owner/branch/scope dispatch and a bounded implementation plan satisfying the requirements and unchecked cases above; shared safeguards in intake item 8 apply
- **Model version:** not selected; choose eligible models by workload/privacy during planning
- **Where:** documentation on `codex/roadmap-status-20261017` (PR #211); no implementation branch
- **Plan:** This roadmap intake records requirements; a dedicated canonical implementation plan for this new row is required before its code claim
- **Scope:** Documentation only in this intake. Future code paths, existing-state reuse, schema/migration reservations, feature gate and rollback must be reviewed before claim; no new service, tool grants or migration number reserved here
- **Next step:** larry: finish current acceptance and dispatch implementation ownership when ready; assigned planner: map existing components and prepare the bounded design, tests and rollback before code
- **Updated:** 10-17 (consolidated enhancement intake; unimplemented and unaccepted)

</details>

<details id="ws-26">
<summary>WS-26 — Relevant events and useful follow-through · Proposed</summary>

**Workstream:** Extend existing reminders, watchers and notifications using the durable task system. Begin with a requested build completing, a tracked deadline changing, or a blocker being resolved.

### Requirements and dependencies

- Depends on WS-24 plus each source’s existing access/privacy authorization; commitment-related events also reuse WS-25.
- Feed source changes and task-state changes into the same task lifecycle. Use events where supported and bounded polling otherwise. Preserve source identity, deduplicate, and recover after downtime.
- Add freshness/relevance criteria, quiet-time and suppression controls. Keep sensitive details out of generic notices; direct the user to an authorized protected view.

### Acceptance checklist — future increment

- [ ] Duplicate or reordered events produce one useful user-visible update without repeated action.
- [ ] Reconnect/downtime recovery restores pending results without losing requests or bypassing cancellation/approval.
- [ ] Irrelevant/stale events do not interrupt the user; quiet-time and suppression controls hold.
- [ ] Generic notifications contain no sensitive payload and resolve only to an authorized protected result.

- **Owner:** `codex` for roadmap intake only; implementation owner unassigned
- **Status:** parked: proposed by Larry 2026-10-17; no implementation or activation authorized
- **Implemented by:** Not implemented by this intake; reuse of existing components must be established in the implementation plan
- **Remaining work / acceptance:** Existing acceptance first, then owner/branch/scope dispatch and a bounded implementation plan satisfying the requirements and unchecked cases above; shared safeguards in intake item 8 apply
- **Model version:** not selected; choose eligible models by workload/privacy during planning
- **Where:** documentation on `codex/roadmap-status-20261017` (PR #211); no implementation branch
- **Plan:** This roadmap intake records requirements; a dedicated canonical implementation plan for this new row is required before its code claim
- **Scope:** Documentation only in this intake. Future code paths, existing-state reuse, schema/migration reservations, feature gate and rollback must be reviewed before claim; no new service, tool grants or migration number reserved here
- **Next step:** larry: finish current acceptance and dispatch implementation ownership when ready; assigned planner: map existing components and prepare the bounded design, tests and rollback before code
- **Updated:** 10-17 (consolidated enhancement intake; unimplemented and unaccepted)

</details>

### Completed: accepted product work and closed documentation reviews

Accepted product workstreams and closed documentation reviews are listed below; implementation milestones also appear in §6.

<details id="ws-18">
<summary>WS-18 — Native audio: survive an output switch during speech · Claude</summary>

### Acceptance checklist — completed

- [x] **Larry · live AirPods switch:** On a build containing #144 or later, switch AirPods → Mac speaker and Mac speaker → AirPods while Mortimer is mid-answer. In both directions the app stays alive, any voice gap is short, and the log shows `audio output flowing` after each rebuild. Record build, date and both outcomes. Passed 2026-10-17 on installed `575cc7b`: Larry confirmed both directions, continued connection and no noticeable silence or only brief gaps; Codex verified PID survival and output-flow diagnostics. [Receipt](docs/acceptance/command-console/receipts/acceptance-campaign-2026-10-17.md).

Source: [native-audio plan, WS-18 progress](docs/plans/MORTIMER_NATIVE_AUDIO_TRANSPORT_PLAN.md). The documented rollback flag is available; it is not an additional mandated live test.

**Workstream:** Larry, 09-30: Mortimer crashed at 18:09:08 after switching from AirPods to the Mac speaker mid-answer. Log: the engine rebuilt (`audio engine rebuilt after configuration change`), Voice Processing then reported `failed to run downlink DSP (state fault)`, and `AVAudioPlayerNode.play()` raised `player did not see an IO cycle` five seconds later (uncaught Objective-C exception, SIGABRT).

- **Owner:** `claude`
- **Status:** accepted 10-17 for the WS-18 mid-speech output-switch gate on installed `575cc7b`; implementation landed via PR #144 (`c2f0f49`). Separate echo/wake/device and broader audio acceptance remain under their original gates.
- **Implemented by:** Claude (Cowork)
- **Remaining work / acceptance:** None for this bounded output-switch criterion. Preserve the separate native-audio and WS-11 requirements; this is not blanket audio acceptance.
- **Model version:** not recorded; do not infer from system name.
- **Where:** main (PR #144, `c2f0f49`)
- **Plan:** `docs/plans/MORTIMER_NATIVE_AUDIO_TRANSPORT_PLAN.md` (progress entry 2026-09-30)
- **Scope:** `macos/JarvisKit/Sources/JarvisKit/AudioEngineIO.swift`, `macos/JarvisKit/Sources/JarvisKitObjC/`, `macos/JarvisKit/Package.swift` (new ObjC target), `JarvisFlags.outputIOWatchEnabled` in `JarvisConfig.swift`, `AudioEngineIOTests.swift`
- **Next step:** codex: preserve the published exact-artifact receipt; larry/acceptance owners: continue the separate echo, wake/device and combined-load checks. The existing rollback flag remains available.
- **Updated:** 10-17 (Larry physical acceptance; Codex evidence recording; implementation owner/scope unchanged)

</details>

<details id="ws-12">
<summary>WS-12 — CI upkeep before the Ubuntu 26 runner switch · Claude (accepted 10-02)</summary>

**Workstream:** Update the GitHub Actions versions (Node 20 deprecation warnings on `actions/checkout@v4` and `actions/setup-python@v5`) and pin `runs-on: ubuntu-24.04` before `ubuntu-latest` moves to Ubuntu 26 on 10-19.

- **Owner:** `claude`
- **Status:** accepted: every workflow pins `runs-on: ubuntu-24.04` and uses `actions/checkout@v7`, `actions/setup-python@v7` and `actions/setup-node@v7` (node24); the PR's checks ran green on them and Larry reviewed the diff before merging (10-02)
- **Implemented by:** Claude (Cowork)
- **Remaining work / acceptance:** None for WS-12. Not changed here: the frontend build still sets `node-version: "20"`; moving it is a separate decision.
- **Model version:** not recorded; do not infer from system name.
- **Where:** main (branch `ws12/ci-runner-pins`)
- **Plan:** none (small change; the PR body is the record)
- **Scope:** —
- **Next step:** None for WS-12.
- **Updated:** 10-02

</details>

<details id="ws-19">
<summary>WS-19 — Repository review and unified roadmap reconciliation · Codex</summary>

**Workstream:** Larry's 10-02 request to review the current repository and reconcile this roadmap against code, plans, acceptance evidence, deployment receipts, and PR state. Documentation and read-only review only.

- **Owner:** `codex`
- **Status:** landed: claim PR #150 merged as `f45f533`; reconciled roadmap PR #151 merged as `cfa0d2d`; docs-only review complete.
- **Implemented by:** Codex (review and roadmap update)
- **Remaining work / acceptance:** None for this documentation review. Product deployment and live acceptance remain in their own workstreams.
- **Model version:** not recorded; do not infer from system name.
- **Where:** main (PRs #150 and #151)
- **Plan:** this bounded review is tracked in this block and §8; no new implementation plan.
- **Scope:** `ROADMAP.md` only for edits; repository, plans, receipts, CI and PRs are read-only evidence.
- **Next step:** None for WS-19; owners follow the open gates in their workstream blocks.
- **Updated:** 10-02

**Review findings (read-only, 10-02):** Six PRs (#143, #144, #145, #146, #148, #149) merged after the deployed `39fc6f9`; #143/#148 are claims, while WS-03/04/18 product changes remain undeployed. The remaining product gates are predominantly Mac/provider/activation evidence, not a missing implementation claim. PR #142 (WS-08 acceptance), PR #147 (WS-17 CC7a.1b), and the now-redundant PR #138 (CX-15 scope, already recorded by #139) were open with conflicts at review time. The shared acceptance runbook, adaptive release-readiness header, `docs/acceptance/IMPLEMENTATION_STATUS.md`, and WS-04 plan status header described older candidate/branch states; their owners must reconcile them before using them as current release evidence. No production setting, token, provider route or acceptance checkbox was changed by this review.

</details>

<details id="ws-08">
<summary>WS-08 — Crystal orb, single shell · Claude + Codex (accepted 09-30)</summary>

**Workstream:** Orb crystal glass (#90), revised to use the crystal shell exclusively

- **Owner:** `codex`
- **Status:** accepted: Larry reported WS-08 tested and accepted on 2026-09-30; deployed in `c3607e6`, deployed again in `03b9e60` on 09-30
- **Implemented by:** Claude original crystal-glass workstream; Codex rendering performance fixes and single-shell cleanup
- **Remaining work / acceptance:** None for WS-08. Larry explicitly reported the work tested and accepted on 09-30. This is Larry's overall sign-off; individual fixture/state/placement observations were not separately itemized. Deployment, release tests, five current fixtures, compact/expanded appearance and Reduce Motion evidence are in the linked receipt.
- **Model version:** not recorded; do not infer from system name.
- **Where:** main (PR #112, `e9388fc`; acceptance evidence PR #115, `8222940`)
- **Plan:** `docs/plans/MORTIMER_ORB_CRYSTAL_GLASS_PLAN.md`
- **Scope:** Orb rendering, orb-specific configuration, performance/visual regression tests, and this plan's acceptance evidence.
- **Next step:** None for WS-08
- **Updated:** 10-02

</details>

<details id="ws-14">
<summary>WS-14 — Subscription probe: sign-in, command and category fixes · Claude (Codex post-merge review)</summary>

**Workstream:** Make the WS-06 check #2 subscription probe work under launchd and report why it fails. It touches WS-02's file (CX-13). Larry decided 09-29: Claude lands, Codex reviews before merge.

- **Owner:** `claude`
- **Status:** accepted for the bounded probe fix: PR #102 (`eb24e81`) deployed; 09-29 live daily probe passed and Codex post-merge review found no blocking issue. WS-06 overall acceptance remains separate.
- **Implemented by:** Claude
- **Remaining work / acceptance:** Live check passed: the `com.mortimer.status-daily` rerun at 14:11 UTC 09-29 shows `claude` `ok: true`. `codex` shows `not_installed`, which is correct because no Codex CLI is on the launchd PATH. Claude's earlier prediction of `gated` was wrong: `gated` appears only once a Codex CLI resolves. Codex completed a post-merge code review of PR #102 on 09-29; no blocking code issue found. The review did not independently reproduce the Mac Keychain/launchd test (CX-13).
- **Model version:** not recorded; do not infer from system name.
- **Where:** main
- **Plan:** Under `MORTIMER_SUBSCRIPTION_RUNTIME_ISOLATION_PLAN_2026-09-25.md`, which allows "home needed for provider-managed sign-in, plus only specifically justified" variables. The live evidence is in WS-06. Changes:
  1. `USER` and `LOGNAME` join the child-environment allowlist. They are not credentials, and there is a `pwd` fallback when launchd omits them.
  2. `_claude_argv` and `_codex_argv` run `provider_command()`, which reads the same `JARVIS_*_SUBSCRIPTION_COMMAND` variable as the installed check.
  3. `probe_subscription` keeps the runtime's own category when the legacy message table falls through to `runtime_error`. A `SubscriptionCapabilityError` reports `gated`. The legacy table and the `verify_model_access` golden output are unchanged.
- **Scope:** `jarvis/subscription.py`, `jarvis/status/subscriptions.py`, `tests/unit/test_subscription.py`, `tests/unit/test_status_subscriptions.py`
- **Next step:** None for WS-14; continue the separate WS-06 spoken and process checks.
- **Updated:** 10-02 (evidence recheck; no new Mac test)

</details>

<details id="ws-15">
<summary>WS-15 — Weather: fresh location and current radar · Claude (accepted 09-30)</summary>

**Workstream:** Larry, 09-29: weather must use where Larry is now and show current radar for that place, not a remembered place.

- **Owner:** `claude`
- **Status:** accepted: Larry on the Mac 2026-09-30, production `03b9e60` (A1–A8 pass; A6 with a wording follow-up)
- **Implemented by:** Claude (Cowork); PRs #110, #114, #118, #120, #123, #126, #127, #128, #131, #132, #133, #134, #136
- **Remaining work / acceptance:** None. Receipt: `docs/acceptance/weather/ws15-weather-location-radar-2026-09-30.md`. Follow-ups F1–F5 are in §5 Backlog.
- **Model version:** not recorded; do not infer from system name.
- **Where:** main
- **Plan:** `docs/plans/MORTIMER_WEATHER_LOCATION_AND_RADAR_PLAN.md`
- **Scope:** as built: `local_weather`, weather card and radar map, voice map control, stable app signing, display-window stores, Open-Meteo request fix
- **Next step:** None for WS-15
- **Updated:** 09-30

</details>

<details id="ws-16">
<summary>WS-16 — Protected-window capture gate repair · Codex</summary>

**Workstream:** Make the privacy-preserving live-window capture assertion deterministic enough to unblock DEPLOY-MAIN without weakening what it proves.

- **Owner:** `codex`
- **Status:** accepted: PR #121 merged as `c3607e6` and DEPLOY-MAIN passed 09-29
- **Implemented by:** Codex diagnosis and test-fixture repair
- **Remaining work / acceptance:** None for this capture gate. Larry's DEPLOY-MAIN for `c3607e6` passed phase A: the real ScreenCaptureKit protected-window test executed and passed (4.825 s), MortimerHost ran 383 tests with six unrelated skips and zero failures, JarvisKit ran 218 tests with zero failures, and Python had 4,924 passes and seven skips. Phase D reported healthy services and matching code, production and app-bundle revisions. Larry accepted WS-08 overall on 09-30; PR #142 publishes its final acceptance receipt.
- **Model version:** not recorded; do not infer from system name.
- **Where:** main (PR #117, `c5781a8`; PR #121, `c3607e6`); acceptance status on `codex/ws16-protected-capture-20260929`
- **Plan:** `docs/plans/MORTIMER_PROTECTED_WINDOW_CAPTURE_GATE_PLAN.md`
- **Scope:** `macos/MortimerHost/Tests/MortimerHostTests/ProtectedDisplayContentTests.swift`, this row's plan and acceptance evidence, and `ROADMAP.md` status only. Product display code remains outside this row; WS-15 owns `Display/DisplayContentView.swift` while active.
- **Next step:** None for WS-16 or WS-08.
- **Updated:** 10-02 (status cross-check only)

</details>

---

## 3. Reserved shared numbers

**WS-17 current-request wire reservation, 2026-10-19 (before implementation):**
`console/turn` version 1 is a host-generated session/generation-bound envelope
using existing `request_id`, `state` (`started`/`cancelled`) and a positive
`sequence`, with bounded `input_timestamp` and `input_user_id` copied from the
already delivered accepted RTVI final transcription. Optional
`origin_request_id` on DisplayPayload and internal `weather_reuse` arguments
binds a result/cache query to that exact request. These fields are never
model-supplied tool arguments or source-policy grants. Missing, malformed,
unknown, cancelled or superseded origin remains ineligible for foreground;
legacy content can still be retained as a card. The native store admits one
foreground result per request and preserves supporting-display ownership.
No configuration key, port, launchd label, migration or persistent task state.
**Compatibility marker reserved before its code, 2026-10-19:** optional
`console/inventory.data.foreground_request_version = 1` advertises support for
`origin_request_id` on internal weather-cache requests. The backend forwards
that argument only after this native capability is observed; older clients
retain their existing closed argument schema and cache behavior. The marker
is host metadata, omitted from model-disclosed inventory, and grants no source
or action permission. No action enum, config key or protocol version changes.



**Existing cleanup label reservation, WS-28 (2026-10-18):** `com.mortimer.sandbox-prune` is already emitted by merged #210 (`scripts/launchd_gen.py`, existing 04:20 job). Record Codex repair ownership here; no new label, schedule, installed job, privilege or activation is created. Job installation/activation is outside this claim.

**DB migrations** (`jarvis/db.py`, `MIGRATIONS`). Migrations are tracked by id string and applied in list order. Never rename an id that may already be applied in production.

| Id | Name | Owner | State |
|---|---|---|---|
| 0001–0027 | … `0025_notices`, `0026_expire_retired_actions`, `0027_notice_memory_review` | — | on main; treat as applied in production |
| 0028 | `memory_admission_jobs` (was Codex `0025`) | WS-01 | landed and applied in production 09-28; do not renumber |
| 0029 | `memory_classification_budget` (was Codex `0026`) | WS-01 | landed and applied in production 09-28; do not renumber |
| 0030 | `memory_admission_shadow` (was Codex `0027`) | WS-01 | landed and applied in production 09-28; do not renumber |
| 0031 | `agent_event_tool_call_identity` (was Codex `0028`) | WS-01 | landed and applied in production 09-28; do not renumber |
| 0032 | `execution_action_claims` (was Codex `0029`) | WS-01 | landed and applied in production 09-28; do not renumber |
| 0033 | `skill_events` (was Codex `0030`) | WS-03 | landed and applied in production 09-28; do not renumber |
| 0034 | `client_tokens` (was Codex `0031`) | WS-04 | landed and applied in production 09-28 as `0034_client_tokens`; auth remains dormant |
| 0035 | (T5 mail/calendar) | backlog | reserved |
| 0036 | `skill_step_check_receipts` (was Codex `0032`) | WS-03 | landed and applied in production 09-28; do not renumber |
| 0037+ | free | — | take the next one and write it here |

Renumbering completed in the main integration. Read-only production verification on 09-28 confirms `0028`–`0034` and `0036` are applied under the names above. **Do not renumber them again.** `0035` remains reserved for MAIL.

**Self-edit allow-list rows:** owned by `docs/plans/ALLOWLIST_SEQUENCE.md`. That rule is unchanged: every allow-list change is a human commit.

**Config keys reserved for WS-04 R2:** `JARVIS_REMOTE_BIND_ENABLED` (default false, independent of `JARVIS_AUTH_ENABLED`). Local bearer authentication may be enabled while this key remains false; only an explicit future remote-access decision may set it true. No new port or migration is reserved.

**Config keys reserved for WS-05, 2026-10-05:** `JARVIS_CODEX_SUBSCRIPTION_CAPABILITY_RECEIPT` points to a secret-free, version/model/binary/catalog/arguments-bound capability receipt; the existing no-tools verification flag alone does not establish capability. `JARVIS_SUBSCRIPTION_TOOLS_ENABLED` defaults false and gates a provider-native bridge whose tool operations must pass through Mortimer's permission and sandbox boundary. `JARVIS_SUBSCRIPTION_TOOL_CAPABILITY_RECEIPT` points to separate provider/version/schema/protocol tool acceptance; the tools flag alone does not establish native tool capability. Request-owned temporary Unix sockets/configuration have no fixed port or launch label. These reservations do not enable either route in production. No port or migration is reserved.

**WS-05 workload quality key reserved before implementation, 2026-10-05:** `model_access.defaults.minimum_quality_tier` and `model_access.workloads.<name>.minimum_quality_tier`, with the existing registry tiers `economy`, `mid`, `frontier`. Apply the standing Sonnet-or-better (`mid`) floor to ordinary non-voice specialists and private background work; planning keeps its frontier floor, while voice and the documented council tier-1 pool retain their legitimate economy choices. Explicit or saved choices below the workload floor are unavailable; they are never silently replaced.

**WS-05 optional workload-limit keys reserved before implementation, 2026-10-06:** `model_access.defaults.max_output_tokens_per_call`, `.deadline_seconds`, `.max_estimated_spend_usd_per_task`, and corresponding `model_access.workloads.<name>` keys. Absent/null values retain existing behavior; no production limit is assigned by this reservation. Spending is configured-price admission, not a guarantee of provider charges or account overage settings. Native routes refuse unsupported output/spend ceilings; enforceable deadlines remain available. Per-parent reservation state is separate from actual usage accounting in costs.db inline tables `model_task_budgets` and `model_call_budget_reservations`; no jarvis.db migration is needed. No port, launch label, credential reference or allowlist change is reserved.

---

**Config keys reserved for WS-13 P1, 2026-10-10 (plan §R.5 D6, §R.10.18):** vault names `MAIL_ATT_USER`, `MAIL_ATT_SECURE_MAIL_KEY`, `MAIL_GMAIL_USER`, `MAIL_GMAIL_APP_PASSWORD` (declared in `mcp-mail`'s `optional_env`; values only via `python -m jarvis.vault set`), and `JARVIS_MAIL_ENABLED` (default true, read only by `mcp-mail`). Migration `0035` stays reserved for P3 (`0035_brief`); P1 adds no migration.

**WS-05 creator source receipt reservation before implementation, 2026-10-06:** Protocol kind `mortimer.development-source.v1`; random per-call challenge and exact owner/session/request/developer-run/revision/job/tool/argument/content/source bindings. The admin signer keeps its Ed25519 private key only in process memory. A public trust anchor may be atomically published at `.source-authority/admin-ed25519-public.json` under the already configured `MORTIMER_SANDBOX_HOME`; it is public verification material, not a provider credential or persistent plaintext secret. Verify canonical host-owned directory/file modes, reject symlinks and stale/replaced authority, and never trust a public key supplied by result JSON. No new env/config key, port, DB migration, vault entry or service-token reuse is reserved. Authentication/source policy cannot be weakened by this receipt.


**WS-05 council/source reservations, 2026-10-06 (Codex):**

- Costs database inline tables `model_task_budget_links(child_scope_id, parent_scope_id, created_at)` and `model_call_budget_reservation_scopes(reservation_id, scope_id)` reserve durable sponsorship and scope membership for a single estimated reservation per outbound attempt. Atomic admission checks every inherited owner/child ceiling and deadline; reopening a child with omitted/null sponsorship cannot drop its recorded owner. Actual `llm_calls` remains singular and separate. No `jarvis.db` migration number or production limit value is assigned.
- Host-only sealed `ChildTaskBudget` and optional execution/coordinator keyword bindings carry the authenticated tenant, exact originating request and cancellation owner. Provider/context JSON and historical telemetry IDs cannot mint sponsorship. Replay creates a fresh audit coordinator.
- Ordinary workspace receipt variant `mortimer.workspace-source.v1` and MCP request/response `_meta.mortimer_development_source` namespace reserve authenticated caller owner/session/run/call, retained sandbox job/session/task/commit, operation/argument/content/source and one-use challenge bindings. Reuse the process-memory admin signer and existing owner-only public anchor; preserve the separate `mortimer.development-source.v1` creator contract without inventing skill IDs/revisions for ordinary work. Hidden metadata is never a model schema argument or provider content. No new environment key, fixed port, launch label, credential, private-key file or auth activation.

**WS-05 advisory source receipt reservation before implementation, 2026-10-06 (Codex):** Protocol kind `mortimer.advisory-source.v1` reserves actual authenticated owner/session/run/agent/tool/call/arguments, accepted input floor, retained action and one-use challenge bindings for planning/research only. Reuse the process-memory signer and host-pinned public anchor; hidden metadata remains outside provider tool schemas. Preserve the separate creator/workspace kinds. Actual retained host sponsorship is required for cross-process budgets; serialized fields cannot grant allowance. No new environment/config key, fixed port, launch label, vault secret, private-key file, `jarvis.db` migration or production limit value is reserved.

**WS-17 payload/inventory reservation, 2026-10-07 (Codex):** Existing plan §7.2 fields `subject_key` (kind plus canonical subject, at most 200 characters) and `fresh_until` (finite UTC epoch seconds, consistent with payload `ts`) are reserved for shared Python/JarvisKit display payloads and their privacy-safe result inventory metadata. The optional DisplayPayload `weather_source` contains only original public `{weather, radar, place}` JSON and optional canonical requested-city `subject_aliases` (at most 8 strings, at most 120 characters each). Its encoded JSON is capped at 16 KiB in Python and Swift; this is a cache-field cap, not a larger wire/message/tool budget. New source content and aliases stay in the native in-memory result and are not exported through inventory; inventory carries subject/freshness metadata only. Preserve actual source-fetch `ts`, including an explicit zero; `fresh_until` is finite and no later than `ts + 900`, and replay never resets either timestamp. Malformed/oversized cache metadata makes reuse unavailable while the legacy display body remains usable and safe same-key upsert still works. UUIDs remain canonical action targets; reference metadata uses the same result identity and conversation owner.

**WS-17 reuse actions reserved before implementation, 2026-10-07 (Codex):** `weather_reuse` is a freshness-aware native query with canonical result UUID `target` selected from the observed native inventory; typed `args` are `subject_key`, `tool` (`local_weather`, `get_weather` or `get_weather_radar`), `days` (integer 1–7), `units` (`metric` or `imperial`), and optional originating `run_id` for one ordered reference per run. The native cache validates ordinary-turn/privacy eligibility, exact subject/capabilities/expiry and session/generation/revision before returning original public source data on a hit. A genuine missing/expired/incomplete-capability cache or no matching public inventory candidate permits the existing fetch after its protected-source guard; ambiguity, stale target/revision, disconnect/timeout and other unsafe failures refuse truthfully without silently fetching. Metadata freshness is not a backend cache or authority. `result_reopen` is the separate explicit canonical-UUID cached-selection action, with spoken subject/index resolved against the observed inventory revision; it selects a retained result under existing protection/action rules and performs no fresh fetch. Automatic weather reuse preserves New/no-jump behavior while another result or view is being read. This expansion introduces no migration, config/environment key, port, launch label, allowlist change, model or provider route. Additional shared names require reservation before use.

**WS-17 host-only reuse eligibility reservation, 2026-10-07 (Codex):** Additional typed `weather_reuse` argument `ordinary_turn` is an exact boolean supplied only by the guarded host adapter. Backend turn classification remains authoritative and is checked before and after native awaiting; model-facing `console_action` refuses this internal action. Native requires this attestation to be `true` on its existing negotiated authenticated console channel, plus exact UUID/key/revision and explicitly public cache policy. Missing/false eligibility refuses without returning source. Native does not infer privacy from displayed text or default unknown turns to ordinary. No new classifier, privilege, external route, cache owner or credential is introduced.

**WS-17 roadmap snapshot reservation before implementation, 2026-10-17 (Codex):** Optional `roadmap` on the existing `repo_read_file` response and DisplayPayload, schema `mortimer.roadmap.v1`, carries a complete bounded read-only snapshot of the fixed `ROADMAP.md` and guarded dated log files. Fields: `schema`, `provenance` (`path`, local `revision`, `sha256`, `read_at`, nullable `dirty`, `source_kind`), `cards` (stable `id`, `title`, verbatim `status`, derived `lifecycle`, current `owner`, `fields`, `details`, `checklist`), `logs` (guarded `path`, front-matter `date`, `rows`, `sha256`, `title`), and `issues`. No provider-generated status, new permission, service, port, migration, persistent cache or implicit Git fetch. Oversized snapshots refuse explicitly instead of dropping rows. Native filters/actions will be reserved with their exact contract before they are implemented; this reservation alone does not activate a native view or filtering.

**WS-17 roadmap controls reservation, 2026-10-17 (Codex, before implementation):**
One additive `roadmap_control` console action (existing negotiated protocol).
Target is an existing roadmap result UUID; `args.operation` is `replace`,
`refine`, `clear`, `focus`, or `refresh`. Filter fields: `owners`, `authors`,
`states`, `topics`, `workstreams` (bounded string arrays); `checklist` is
`all`, `remaining` or `larry`; `blockers` is a boolean; `period` is `all`,
`this_week` or `last_seven_days`. AND across facets / OR within; empty arrays
clear a facet. Focus requires exactly one known workstream and clears conflicting
facets. Unknown values refuse without changing selection. Native and voice use
the same state owner. The existing console request/result channel carries fixed
read-only roadmap refresh requests and a bounded `data.display` reply; no model
call, new endpoint, arbitrary path or broader source authority. Refresh timeout
is 15 seconds native / 20 seconds voice, and source acquisition is bounded to
8 seconds. Optional DisplayPayload `roadmap_timezone` carries the configured
IANA timezone; unavailable/invalid timezone refuses relative-date filters.
Roadmap provenance adds `repository_id` (SHA-256 of the canonical guarded repo
root, never the raw path) to distinguish identity across checkouts. Filter state
and expansion remain native memory only. Sharing exports the frozen filtered
projection, never hidden cards; protected results retain their existing limits.


## 4. Conflict register

Open means not yet resolved. Each entry names who resolves it.

| ID | Conflict | Resolves | State |
|---|---|---|---|
| CX-25 | WS-17 current-request foreground behavior changes the prior §7.2 no-jump rule/UI2-23 criterion while another result is being read; WS-28 covers cleanup only and WS-17's current branch is release-verification-only. | Larry approved the foreground exception and review-only publication at 23:44 UTC on 10-18; Codex prepares claim registration | Policy resolved by Larry: open only the result proven to answer the still-active explicit request, including fresh native cache reuse; background, superseded, stale/cancelled and unrelated arrivals retain reading focus and supporting-display ownership. Implementation claim pending main: `codex/ws17-current-request-arrival-20261018`. Review-only publication does not authorize merging this claim or any runtime PR. No runtime edits or deployment in this proposal. |
| CX-24 | Larry authorizes acceptance execution and reassigns the two merged #210 cleanup defects to Codex on 10-18; prior main has no matching acceptance branch/cleanup claim. | Larry explicit 20:08:26 UTC dispatch; Codex claim-only registration | Resolved ownership boundary: WS-20 owns acceptance documentation/evidence on `codex/acceptance-clearance-20261018`; WS-17 retains patch-only cross-review and independent release verification on `codex/ws17-release-verification-20261018`; new WS-28 owns only cleanup-race/fingerprint repair on `codex/sandbox-cleanup-repair-20261018`. WS-05 source/session semantics and every unrelated owner remain intact. Claims must land before code. Only this separate claim-only PR may merge on required checks; runtime repair merge and production deployment/restart remain separate decisions. |
| CX-23 | WS-27 new documentation request expanded by Larry 10-18 to front acceptance clearance/current status; #218/#219 edit neighboring status and joint-plan progress. | Larry explicit documentation dispatch; Codex additive reconciliation on its isolated branch | Resolved documentation boundary: update current roadmap summary and existing status reports, append clearance/inventory to existing WS-20 plan, preserve #218/#219 intent, all restored proposals and all owners/criteria/receipts. Both PRs merged during publication and are incorporated via main `9ea27c7`. No runtime claim or review/deployment waiver. The conflict resolution retains the restored intake/cards/WS-22 dependency and both dated plan additions; no runtime change. |
| CX-22 | WS-17 roadmap first-arrival display needs the `agent_tool_result` observation projection in `jarvis/agents/base.py`, held by Codex WS-05. | Larry approved the bounded roadmap-only extension 10-17; Codex coordinates both scopes. | Approved and claimed on main through #217 (`ed21d82`): canonical roadmap observation only; preserve other caps, private redaction, model history, logs and source-before-sink guards. No broader Base edits. |
| CX-21 | WS-13 P1 adds the `mcp-mail` source contract to `jarvis/skills/registry.py`, which WS-05 (Codex, claimed) holds for source classification. WS-13 edits only the `mcp-mail` entries (classification and `EXTERNAL_TOOL_SERVERS`/source-operation sets), not `_invoke` or any existing entry; plan §R.13. | `codex` (WS-05): review those entries in the P1 PR | resolved: Codex revision-3 sign-off recorded in WS-13; #204 merged `575cc7b`. Subsequent mail-preflight/live acceptance remains separate |
| CX-20 | Larry explicitly reassigns remaining WS-17 from Claude to Codex on 10-07; WS-20 documentation #193 merged concurrently and edits narrow WS-17 state fields, and landed WS-21 shares console/inventory files. | `larry` (10-07): Codex owns remaining WS-17 implementation; `codex` preserves #173 and records this bounded coordination | resolved ownership/scope boundary: WS-17 owns its implementation/plan/evidence and current row; WS-20 retains operational summary/decision grouping and WS-20-specific logs; its landed #193 wording is reconciled to this newer assignment, with WS-17 owning its block/plan/receipts/logs; no edits to the other session’s branch. Preserve WS-21 transfer/screen behavior and its separate physical acceptance. Cross-review and release approvals remain required; no other row is reassigned |
| CX-16 | WS-21 (supporting display transfer) edits the display-transfer, panel and screen parts of files in WS-17's scope: `console_protocol.py`, `ConsoleProtocol.swift`, `ConsoleActionRegistry.swift`, `ConsoleActionCoordinator.swift`, the `WorkspaceStore` inventory, and the display menu in `WorkspaceView.swift`. Both rows are Claude's; WS-17 has no open branch. | `larry` (10-03): new row WS-21; WS-17's CC7a.3 starts from main after WS-21 merges | resolved 10-06: PR #171 merged as `bde22bb` on 10-03; its live display acceptance remains open in WS-21 |
| CX-11 | Historical T2 merge collision: (1) auth defaulted on; (2) internal callers and deployment health lacked service headers; (3) stale sidecar route inventory; (4) concurrent `mcp_selfedit` edits; (5) token setup remains CLI-only, while the native app already reads a Keychain token. Items (1)–(4) were resolved by dormant Addendum R1 and deployed. PR #149 added a second explicit remote-bind gate so local bearer auth need not expose a listener. | `codex`: choose and implement local-only token onboarding for (5); `larry` decides local activation and any remote bind separately | R1 deployed dormant; R2 bind guard merged as `a39136a` but not deployed in `39fc6f9`; onboarding method/provisioner and enabled-mode acceptance remain open |
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

Open or undecided conflicts are listed first.

---

## 5. Backlog (unclaimed)

Nobody works on these until Larry turns one into a §2 row.

- **WS-15 follow-ups (09-30, receipt F1–F5):** F1 retry guard refuses a different place after a failure (exempt when Larry's own words bring a new token; `jarvis/agents/delegate.py`, Claude's WS-07 area); F2 "London, UK" not geocoded on first try; F3 spoken weather drops "approximately" when location comes from the internet connection; F4 Mortimer is not told which place the card on screen shows; F5 speech-to-text mishearings ("ten miles", "weather").
- **T2 remote access: switching it on** (undecided). WS-04's dormant R1 foundation and R2 remote-bind guard are merged; local token onboarding is the active WS-04 step, with method selection pending. Local authentication and any remote listener require separate later activation decisions (CX-11 item 5).
- **T1.3 native client hardware verification** V3–V9: `MORTIMER_NATIVE_CLIENT_APP_PLAN.md` §8.
- **T1.4 web retirement:** `MORTIMER_WEB_RETIREMENT_PLAN.md` (DRAFT).
- **T3 local voice and Mac mini:** `MORTIMER_LOCAL_VOICE_AND_MINI_PLAN.md` (DRAFT; needs the hardware).
- **T4b sensitive tier:** gated on G3. Larry's rule: no financial piece until models run locally on the mini.
- **T5 mail, calendar and daily brief** (plan review proposed as WS-13): `MORTIMER_MAIL_CALENDAR_BRIEF_PLAN.md` (DRAFT). Codex edited the plan document on 09-26; no mail code was found. Migration `0035` is reserved.
- **Personal VAD / speaker gate:** built and switched off pending the §6 effectiveness protocol (see §7 below).
- **Optimization plan Rev 3.6:** remaining phases not reconciled in this pass.
- **T7 home automation / T8 surveillance:** queued, unassigned; platforms/devices and camera permissions undecided. Detailed plans unwritten; see [platform roadmap](docs/plans/MORTIMER_PLATFORM_ROADMAP.md) §2.7–2.8. Requested by Larry; implementation system not assigned.
- **T4c investing assistance:** queued, unassigned in the financial track; G3/G4 and local-model prerequisites remain. Detailed plan unwritten; see [platform roadmap](docs/plans/MORTIMER_PLATFORM_ROADMAP.md) §2.4.

---

## 7. Deferred features with revisit criteria

*Carried over unchanged from the previous `ROADMAP.md` (headings demoted one level). Each item still needs its own plan and a §2 row before anyone builds it.*

### Mortimer roadmap — deferred features with revisit criteria

Standing list of decided-but-not-yet-built directions. Each entry names
its trigger — the observable condition that says "build this now" —
per the discipline in MORTIMER_VOICE_UI_PLAN.md §7. Items here have had
their *direction* decided in discussion with Larry; each still gets its
own plan doc before implementation.

#### Model Use Enhancements (added 2026-09-20)

- [ ] **MAR-A** — Reconcile the deployed Mac checkout and capture live
  baseline evidence.
- [ ] **MAR-D** — Finish the broader tool-result/continuation privacy audit.
- [ ] **MAR-E** — Validate SAYGM credentials, catalog, and confidential
  synthetic inference.
- [ ] **MAR-F** — Re-authenticate Claude and validate subscription capabilities
  and account isolation.
- [ ] **MAR-G** — Produce enabled-mode runtime evidence across all routed
  non-voice call sites.
- [ ] **MAR-H** — Complete live voice route-control acceptance.
- [ ] **MAR-I** — Run the research, development, and confidential-memory pilot.
- [ ] **MAR-J** — Complete latency, quality, privacy, rollback, and deployed
  release evidence.

- [x] **MAR-B/C foundation** — Model/route/workload contracts and the
  provider-neutral execution boundary are implemented and covered by tests.
- [x] **MAR-D foundation** — Policy-aware run-log/council redaction and
  protected delegation activity-event handling are implemented.
- [x] **MAR-F foundation** — Gated Claude/Codex text adapters isolate
  subscription subprocesses from inherited API credentials and endpoints.
- [x] **MAR-H foundation** — Sidecar, native Repo controls, route metadata,
  and the gated voice preference tool share the same draft/confirm store.

See the detailed [Model Use Enhancements plan](docs/plans/MORTIMER_MODEL_USE_ENHANCEMENTS_PLAN.md)
and [acceptance status](docs/acceptance/model-use-enhancements/STATUS.md) for
evidence, test counts, and exact handoff commands.

**Status:** In progress. The routing foundation, SAYGM catalog parser,
privacy checks, provider-neutral execution contract, and read-only route
status are implemented behind `JARVIS_MODEL_ROUTING_ENABLED=1`; the sidecar
and native API now expose draft-confirmed persistent route controls. Live
provider credentials, subscription capability validation, runtime-enabled
evidence, and release deployment remain open.
The document records manual per-model and per-workload subscription/API
selection, separate Claude/Codex subscription adapters, SAYGM confidential
inference, privacy enforcement, and quality/latency acceptance.
Haiku voice orchestration, Deepgram, and ElevenLabs retain their existing
routes. No silent paid fallback or downgrade in privacy or model quality.

**Trigger to build:** Implementation is requested after the saved plan is
reviewed. Begin with MAR-A's deployed-backend reconciliation and baseline;
model availability and provider limitations are explicit validation gates.

#### Personal VAD — speaker-gated turn-taking (added 2026-08-16)

**Status (2026-09-22): BUILT, gated OFF.** Shipped 2026-08-22 (`88d58bc`)
as the Tier-2 speaker gate of `docs/plans/MORTIMER_VOICE_ISOLATION_TIER12_PLAN.md`,
with windowed scoring added by `MORTIMER_GATE_V2_AND_MODEL_REQUEST_PLAN.md`:
`jarvis/speaker.py` (local SpeechBrain ECAPA-TDNN embeddings, CPU, file-based
`python -m jarvis.speaker enroll|verify|status`) and
`jarvis/bot/speaker_gate.py` (`SpeakerTap`, `TranscriptGate`, and
`SpeakerVerifiedMinWordsTurnStartStrategy`, which makes barge-in while the
bot is speaking require a passing speaker score). `JARVIS_SPEAKER_GATE_ENABLED`
defaults to false and stays off until the plan's §6 effectiveness protocol
is run (`docs/acceptance/adaptive-interface/RELEASE_READINESS.md`). Still
unbuilt from the scope below: wake-word follow-up gating (nothing in
`jarvis/wakeword/` or `WakeWordListener.swift` consults the speaker
profile); turn-END gating as such (an unknown voice can still open and close
a turn while the bot is quiet — its transcript is dropped instead); and a
calibration command — the threshold is a fixed default
(`JARVIS_SPEAKER_THRESHOLD`, 0.40), with `JARVIS_SPEAKER_CAPTURE` recording
turn audio only as a calibration aid. The text below is the original
decision record.

**What:** local speaker recognition (enroll ~30s of Larry's voice once;
ECAPA-TDNN/resemblyzer-class embeddings, CPU, no cloud — same
local-first pattern as openwakeword) used to GATE turn-taking
decisions: only the enrolled speaker's voice may barge in, end a turn,
or follow a wake-word activation. It gates ACTIONS, not audio — STT
still runs on everything (no added first-word latency); interruption
and turn-end signals are suppressed unless the active speech segment
matches the enrolled profile.

**Why:** noise suppression (Workstream A) removes non-speech and the
VAD detects any speech — neither can reject the wrong HUMAN (TV,
another person, playback). Observed symptom: four consecutive
"[system] Your previous reply was interrupted" notices in one session
(logs/bot.log, 2026-08-16 19:41) — spurious barge-ins are the concrete
problem this solves.

**Boundaries decided in advance:** this is a UX filter, never
authentication — spoofable by recordings and degraded by illness or
distance, so it must never gate confirmation actions (commits, pushes,
submits). Threshold must be calibrated from logged data, not
hand-tuned (the PROCEDURE_MATCH_THRESHOLD `--calibrate` discipline),
with false-rejection (ignoring Larry from across the room) weighted as
the worse failure. Sequenced after or alongside the noise-suppression
workstream — NS cleans the signal, which makes the embeddings more
reliable.

**Trigger to build:** spurious barge-ins recur in normal use after the
VAD stop_secs tuning and (if enabled) noise suppression are in place —
i.e. this is the fix for the wrong-voice case specifically, not the
first lever to pull.

#### Other standing deferrals (pointers)

- **Native macOS client:** SUPERSEDED 2026-08-25 by the full-Swift
  decision (`docs/plans/MORTIMER_PLATFORM_ROADMAP.md` T1,
  `docs/plans/MORTIMER_NATIVE_CLIENT_CORE_PLAN.md`).
- **Voice UI deferrals:** local fast-path grammar, Window Management
  API auto-detect, named multi-windows, voice help tour, auto-hide
  chrome, speech-reactive overlay opacity — MORTIMER_VOICE_UI_PLAN.md
  §7 (revisit criteria there).
- **Council for app-scaffolding:** no trigger exists yet by design —
  CLAUDE.md's council section, "do not invent a trigger for it."


---

## 8. Change log

<!-- changelog: docs/roadmap-log/ -->

Dated entries live in `docs/roadmap-log/`, one Markdown file per entry. Add a file there with `date`, `system`, `rows`, and `prs` front matter; use `prs: []` when no PR applies. Do not add entries in this section.

---

## 6. Recently landed

Completed implementation and verification milestones are kept last. Open
acceptance remains in §2 even when a feature’s code has landed.

<details>
<summary>Completed — integration and Mac deployment · Codex integration; Claude release tooling; Larry merge/approval</summary>

- [x] Both branches integrated with preserved behavior; conflict resolutions and migrations landed.
- [x] Release `539f8f6` deployed on 2026-09-28 at 20:19 EDT, with database/code/app rollback snapshot and healthy services.
- [x] Exact-release verification: JarvisKit 219 passed; MortimerHost 372 executed, 7 skips, zero failures; Python 4,860 passed, 7 skipped, 2 subtests passed.
- [x] PR #97 merged as `180766e`: status/R1 follow-up; application remains deployed at `539f8f6`.
- **Evidence:** [deployment receipt](docs/acceptance/skills-workspace/receipts/rendering-performance-2026-09-28/deployment-receipt.json).
- **Attribution:** Codex integration and verification; Claude authored DEPLOY-MAIN under WS-07; Larry approved and merged. Exact model versions not recorded here.

</details>

<details>
<summary>Completed — Skills and orb performance fixes · Codex</summary>

- [x] Skills selection-to-layout p95 14.480 ms wide / 7.911 ms compact (20 ms limit).
- [x] Crystal orb p50/p95 4.841/13.370 ms; original relative and absolute limits passed.
- [x] Ten crystal/legacy voice-state render comparisons pixel-identical; no threshold relaxation.
- **Attribution:** Codex implementation and validation; Larry assigned the bounded orb performance fix from Claude to Codex on 09-28.
- **Acceptance:** Larry accepted WS-08 overall on 09-30; PR #142 publishes the status, plan and receipt.

</details>

<details>
<summary>Completed — workflows, recovery, Skills and model foundations · Claude + Codex</summary>

- [x] **Claude / WS-07:** voice workflows phases 1–4, Workflow Viewer, #80 privacy fix and DEPLOY-MAIN (09-25).
- [x] **Claude / WS-06:** self-service access/recovery and registry-split code (#86; 09-25 landing).
- [x] **Codex / WS-03:** separate Skills Workspace, developer-run creator and validation activity contracts.
- [x] **Claude original workstream / WS-08:** crystal-glass orb (#90; 09-24); later performance fixes by Codex above.
- [x] **WS-05 foundation:** provider-neutral execution, policy-aware logs, isolated subscription adapters and draft-confirmed preferences. The roadmap does not itemize every original contributor; Codex owns WS-02 isolation and has claimed remaining WS-05 work. MAR-A–J live rollout remains open.
- **Still open:** corresponding live/activation gates in §2; WS-07 status-header correction.

</details>

<details>
<summary>Completed — remote safeguards, release protections and historical repair · Codex + Larry; recovery operator unrecorded here</summary>

- [x] **Codex / WS-04:** dormant auth and Addendum R1; 140 focused tests passed; isolated enabled/dormant admin health proof recorded.
- [x] **Larry:** health-probe and frozen skill-fixture protection commits `617048a` and `1152dd5`; verified by Codex.
- [x] **Codex / WS-03:** creator claim-race fix.
- [x] Authorized 28-exchange historical-memory recovery; recovery operator not attributed in this roadmap. This does not close WS-10 staged rollout.
- **Still open:** remote activation, onboarding and live spoken status proof.

</details>

Earlier completed plans: [implemented plans](docs/plans/implemented/) and
[archive map](docs/archive/README.md).


## 9. New development — deferred until existing acceptance closes

<details id="ws-22">
<summary>WS-22 — Evidence-based investigation and development workflow · parked</summary>

**Dependency reconciliation, 10-17:** Intake item 7 reuses this plan. WS-24 must supply the shared task/run/attempt lifecycle; reconcile existing §5–6 schemas and recovery rules before code so this workflow does not create competing durable task authority. WS-23 supplies verification-role boundaries; item 8 safeguards apply. Existing acceptance-first prerequisite remains unchanged.

- **Owner:** `codex` for documentation only; implementation owner unassigned
- **Status:** parked: canonical implementation plan saved at Larry's request on 2026-10-17; no implementation is authorized
- **Implemented by:** not implemented; Codex documented the design and handoff contract
- **Remaining work / acceptance:** Close all pre-existing roadmap acceptance gates under their owning plans before a fresh implementation claim. Then implement R1–R10 and AT-01–AT-18 in the linked plan; separate core, coordinated integration, and live pilot. No skipped/blocked gate counts as acceptance and no new-development scope is granted by this entry.
- **Model version:** not recorded; the implementation contract is model-independent and capability-gated
- **Where:** documentation on `codex/acceptance-first-20261017`, via this PR; no implementation branch
- **Plan:** `docs/plans/MORTIMER_EVIDENCE_WORKFLOW_IMPLEMENTATION_PLAN.md`
- **Scope:** parked design only. Future proposed package `jarvis/investigation/`, focused tests and coordinated adapters into existing services require a fresh claim; these paths are not locked or authorized for implementation now. No migration/configuration/protocol identifier is reserved.
- **Next step:** larry: complete existing acceptance and then explicitly dispatch an owner/branch/scope; codex or assigned implementer: refresh main, dependencies and reservations before any code. Until then retain this plan as deferred development.
- **Updated:** 10-17 (Larry: acceptance before new development; previous parallel-start proposal superseded)

</details>

---

## 10. Mortimer enhancement implementation plan — Larry, 2026-10-18

<details id="ws-27">
<summary>WS-27 — Subsequent enhancement design, sandbox voice evaluation and private local model · documentation only</summary>

Larry requested this new plan at the end of the authoritative Git roadmap.
This is the documentation dispatch for the new row and its two technical
appendices; it grants no implementation claim. The acceptance-first priority
above remains binding. Proposed verification, durable recovery, commitment and
follow-through work restored by [merged #219](https://github.com/Larryfix71566/jarvis-voice-ai/pull/219)
keeps its own future workstream authority; this plan cross-references those
proposals rather than restoring or assigning them again. [Merged #218](https://github.com/Larryfix71566/jarvis-voice-ai/pull/218)
records existing release/acceptance status, which is preserved here.

- **Owner:** `codex` for this documentation dispatch only; implementation owners unassigned
- **Status:** landed documentation via this PR; all proposed development and benchmark execution remain parked behind existing acceptance and a fresh dispatch
- **Implemented by:** Codex authored the plan and technical appendices; no runtime implementation or benchmark results
- **Remaining work / acceptance:** Prioritize the front acceptance-clearance sequence and current status reconciliation; review design and unresolved decisions; finish existing applicable release acceptance under its owners; separately authorize an isolated harness, setup/access and spend before runs. Compare immutable baseline → sandbox shared optimization/ablations → candidate models → held-out results; separately decide any production migration. Jev is ON HOLD until voice optimization and newer-model comparison resolve.
- **Model version:** User requested GPT-6.1 Sol with high effort for planning; this entry records the preference, not independently verified execution telemetry or the deployed voice model
- **Where:** `codex/mortimer-enhancement-plan-20261018`, [draft PR #220](https://github.com/Larryfix71566/jarvis-voice-ai/pull/220), initially based on main `28420af`, reconciled with main `9ea27c7`; isolated worktree; no implementation branch
- **Plan:** [Canonical enhancement plan](docs/plans/MORTIMER_ENHANCEMENT_IMPLEMENTATION_PLAN_2026-10-18.md), with [sandbox voice-model evaluation protocol](docs/plans/MORTIMER_VOICE_EVALUATION_PROTOCOL_2026-10-18.md) and [local-model setup/integration runbook](docs/plans/MORTIMER_PRIVATE_LOCAL_MODEL_RUNBOOK_2026-10-18.md) as appendices of this same row
- **Scope:** Documentation only: the current roadmap acceptance/status summary and this new end section, the three linked enhancement documents, the dated new-row log, and Larry’s added acceptance-clearance/status reconciliation in the existing WS-20 plan and acceptance status/readiness/runbook references (CX-23). Existing source blocks, plans, production receipt, ownership and acceptance checkboxes stay authoritative. No runtime paths, credentials, policy settings, model installations, provider calls, shared config/port/migration/launchd identifiers or deployment are authorized or reserved.
- **Next step:** larry: review decisions and the sandbox-only test design; existing owners: complete release/acceptance first. Later assigned implementer: refresh main/claims, establish a safe non-destructive sandbox and obtain a bounded implementation/run dispatch. Do not invoke Tart pruning/reclaim while the recorded cleanup race/fingerprint blockers remain unresolved.
- **Updated:** 10-18 (new documentation request and sandbox optimization/testing constraints; no gate closed)

</details>
