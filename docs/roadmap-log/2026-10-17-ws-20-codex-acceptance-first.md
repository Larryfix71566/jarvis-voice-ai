---
date: 2026-10-17
system: codex
rows: [WS-20, WS-22]
prs: []
---

# Acceptance-first sequencing and deferred investigation workflow

## Authorization and scope

Larry requested: save the model-independent investigation/development plan,
add it to the end of the roadmap as future development, and identify acceptance
work that can begin without interfering with Claude. All existing acceptance
gates precede new development. This supersedes the earlier parallel-core start.

Source: `origin/main` `4e350b466bc6efedde489612fc6232cd5fa15802`, fetched 2026-10-17.
Documentation branch: `codex/acceptance-first-20261017`.
Session: `01a14bae-5269-78b0-abe8-6611e9c357dc`.

Changed only documentation: priority banner, bounded WS-20 update, final parked
WS-22 block, its canonical plan, joint-working progress, and this triage/evidence.
No application code, production configuration, credentials, provider request,
activation, deployment, or product acceptance changed. No existing unchecked
acceptance item was checked. This is a dated assessment, not a second tracker.

## Read-only findings

- Refreshed main contains merged mail PR #204. The baseline roadmap checker
  returns 1 error / 0 warnings: WS-13 still says `review` although its branch
  is merged. Leave that correction to Claude's #205.
- The roadmap Production line names `dc59bd0` (10-11). The newest local
  deployment receipt records `575cc7b770b621b5c8049097ef63e93618ba3016`, deployed
  2026-10-13 20:02:02 EDT, `status=deployed`, with no reported problems.
  Production Git HEAD and installed app `MortimerSourceRevision` match that
  receipt. These are installed/deployment observations, not current live checks.
- The installed app executable SHA-256 is
  `6c67661bb94ddde5fa95d0a807dd77e5d837483a69c0d979412064fdcd3eaf29`;
  bundle configuration is `debug`. The source commit is an ancestor of inspected
  main, and `dc59bd0` is an ancestor of that deployed source.
- Restricted process lookup failed to enumerate processes; that failure is not
  evidence of absence. A subsequent approved unrestricted `pgrep -x MortimerHost`
  exited 1 with no matching PID. No matching app process was observed at that
  instant. Backend loaded identities, effective configuration, listeners, and
  health were not checked. Do not claim a running candidate is frozen.
- #205 proposes exactly the production-line correction above, WS-13 landed/Mac
  evidence, and the mail preflight fix. Its branch records Larry's M1-1/M1-2/M1-3
  outcomes on 10-13; these are published reported evidence, not independently
  rerun by this assessment. Formal M1-1 repeat after corrected production
  deployment and exact-head reviews remain open in that proposal.
- Open PR snapshot: #205 `47f588a53d83ca75fb65cd929d605615f414355f`;
  #174 `011fdb99021be991c078ec01e0714d24c4834e07`;
  #172 `33f5778fca287b39f892ba845b04b446fd752bbc`.

## Work that can begin without changing Claude's work

### A. Candidate and evidence preparation — first

**Rows:** WS-01/09/11/17, plus WS-03 baseline.
**Actor:** Codex records; Larry participates where the owning plan requires.

Use the installed identity observations above as preparation. When the app is
started for acceptance, capture actual loaded app/backend identities, effective
configuration/topology and health. Review relevant source changes against each
older receipt before reusing it. Do not upgrade an old test to current-build
acceptance merely because its commit is an ancestor.

Reuse existing bounded evidence rather than repeat tests solely to repair
documentation: WS-17's 10-06 ordered/full-text/arrival-focus receipt; Skills
SW-B/C accepted gates and Versions wording subcheck; accepted orb work; named
historical display cases. Preserve their original build, scope and limitations.
No current product gate was closed by this read-only preparation.

### B. Console acceptance — highest-value first live session

**Rows:** WS-17 UI2-22/23/24/25; then dependent WS-09/11 UI2-04/09/13.
**Prerequisite:** identified running build, existing route/source permission,
and Larry's live observations. Do not initiate provider workloads merely to
prepare documentation.

1. Five-turn/full-text conversation including a long answer, protected-content
   behavior, and retained reading/focus/scroll state.
2. Requested result opens from Conversation; new/late result while reading
   preserves focus and shows the correct notice/card.
3. Recents voice/pointer select/close/pin/reopen agree with actual inventory;
   ambiguous and stale requests clarify without the wrong target changing.
4. Weather → Atlanta → original gives two result identities, eligible fresh
   reuse avoids a fetch, and stale refresh updates the same identity.

Do not remove switches or alter source during acceptance. Failures become
evidence and a scoped repair request under the owning workstream. Full closure
requires all named cases, not a successful demonstration of one path.

### C. Audio and supporting-display sessions

**WS-18:** Larry switches AirPods → Mac speaker → AirPods during speech on the
identified candidate; record both directions, continuity, app survival and
`audio output flowing` after rebuild. Shares applicable evidence with WS-11;
does not close the separate echo/device-denial/audio matrix.

**WS-21:** with an external display, exercise pointer and voice transfer,
already-showing, missing/stale/protected destination refusal, unplug during
confirmation, state restoration and truthful inventory. Preserve conversation
on main. Reuse matching results in WS-01/09/11; broader mirrored/three-screen
or inaccessible hardware cases remain open unless the owning plan permits and
Larry records a known-limitation acceptance.

These sessions test landed behavior and do not edit Claude's display/audio
code or acceptance plan. Coordinate actual device use with Larry; do not change
hardware while another live test is running.

### D. Other bounded UI evidence

After the required candidate/dependency checks, WS-03 remaining SW-A read-only
catalog/navigation baseline, WS-09/11 keyboard/VoiceOver/large-type/contrast,
sharing preview/cancel/copy/save using synthetic content, and result
close/reopen are candidates. Record exact cases; authenticated inventory,
creator, live provider, and physical-display gates remain distinct. Skills
versions wording already has a bounded receipt and need not be repeated only
for bookkeeping.

WS-07 viewer and WS-06 spoken-status/recovery are Claude-associated acceptance
work: read-only user journeys may be scheduled with the existing owners, but
do not take over their guard evaluation, missing checklist mapping, or source.
Their named closure decisions remain with Larry/Claude.

## Keep with Claude / existing review pathway

- **#205 / WS-13:** do not edit the mail preflight, registry tests, plan, WS-13
  row, or Production line here. The open PR already owns those corrections.
  Existing next steps name Codex exact-head review of #204 revision 3 and #205,
  Larry's merge/deploy, then the formal corrected preflight repeat. Reviewing
  that published patch is a compatible next task; implementation stays Claude's.
- **#172/#174:** do not duplicate WS-21 status/plan corrections or resolve those
  branches. Preserve the new acceptance-first banner/parked row when their owner
  integrates them. Shared `ROADMAP.md` changes warrant a merge-overlap check.
- **WS-05 #177 cross-review:** remains Claude's; do not substitute a Codex
  self-review or infer acceptance from merge.
- Do not message another chat, post PR feedback, alter Claude's checkout,
  activate accounts or run real mailbox/provider probes as part of this triage.

## Gates that cannot close through testing alone

- **WS-04:** onboarding method decision and unbuilt provisioner precede
  disposable/live auth checks. Local activation and remote binding are separate
  choices. WS-03 authenticated/creator gates inherit those prerequisites.
- **WS-02/05:** source authority, operator identity, exact runtime/capability,
  account/billing/overage and rollout decisions remain. The last recorded
  catalog lacked an eligible confidential model; do not treat that old snapshot
  as current availability or run a new paid probe without authority.
- **WS-03:** real creator/VM, 24-trial paired evaluation, activation/rollback,
  and remaining voice/performance gates require their actual dependencies.
- **WS-10:** eligible model/source/privacy prerequisites and staged approvals
  precede shadow/live memory, the first 20 decisions, and benefit/budget evidence.
- **WS-13:** mail acceptance does not establish calendar/brief completion.
  P2/P3 are unclaimed/unbuilt in the inspected records; P4/P5 remain separately
  gated. The new-development hold does not silently authorize or waive them.
- **WS-07:** genuine-event guard evidence and Larry's log/correct decision.
- **WS-20:** checker enforcement remains Larry's decision after owned drift
  corrections; a checker run alone cannot close that decision.
- **WS-01/09/11:** independent exact-candidate verification, rollback and five
  frozen daily-driver days require actual evidence over time. Elapsed calendar
  time since a deployment is not a five-day acceptance record.

Larry's “all acceptance first” objective therefore includes explicit decisions
about unbuilt existing prerequisites. Until those are addressed under their
owning rows, WS-22 stays parked. No automatic waiver or scope reduction.

## Validation and limits

Baseline checker: one inherited WS-13 merged-branch error. The same error is
expected until Claude's #205 lands; preserve it rather than editing his row.
Documentation validation must establish no added errors, no altered existing
acceptance checkboxes, complete WS-22 fields/links, and no unintended diff in
Claude's rows. A documentation check is not a product acceptance receipt.

Remaining next action: publish this documentation for review, then start with
the identified-candidate console session when Larry is ready. The application
was not launched, no live/provider tests were performed, and no product gate
is claimed closed by this entry.


### Documentation checks completed

- `git diff --check`: passed.
- Roadmap checker on the documentation candidate: same single inherited WS-13
  merged-branch error, zero new errors/warnings. No checker settings changed.
- All 124 pre-existing checkbox lines are byte-for-byte unchanged. WS-13,
  WS-17 and WS-21 blocks and the Production line are unchanged.
- Plan contains R1–R10 and AT-01–AT-18; parked WS-22 is the final roadmap block.
- Non-mutating Git merge-tree checks: #205 merges cleanly with both inspected
  main and this candidate. #172/#174 already conflict in ROADMAP on main;
  their conflict bodies and counts are unchanged by this candidate. These
  results apply only to the exact published heads recorded above.
