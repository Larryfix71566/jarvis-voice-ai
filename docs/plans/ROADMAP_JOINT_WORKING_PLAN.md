# Roadmap joint working: catch-up and drift prevention (WS-20)

**Status:** FOUNDATION LANDED; completion candidate reconciled 2026-10-22 against main `636880eabbe9dc756c30df7128d0a90c02d222bd`, preserving continuity draft #246 at `028b44e11acff9dff3e00380e1624c8657ce545c`. B1–B4 and the ten-merge observation are complete. Two of four listed WS-20 milestones remain unchecked: Larry's checker decision and final owner-linked evidence/Phase A/B exit. §11 is the current gate reconciliation; §§9–10 retain their dated inventories and source limits. No live acceptance, enforcement change, release or installation is granted.
**Owners:** Claude: B4 checker, its own rows, this plan. Codex: B1–B3 protocol and change-log move, its own rows, review of B4. Larry: merges, deploys, Mac checks, approval of the protocol change.
**Recorded:** 2026-10-02 against main `cfa0d2d` and open PR #152 (WS-19 close).
**Author:** Claude (Cowork) · **Approver:** Larry

## 1. Why

Two full reconciliations in three days each found rows that later merges had left stale: Claude's on 09-30 (PR #139) and Codex's WS-19 on 10-02 (PRs #150, #151). WS-19 fixed the 10-02 findings within hours. The causes are still in place:

| Drift seen | Cause | Fix in §3 |
|---|---|---|
| WS-18 said "review" after PR #144 merged; WS-04 said "on branch" after #149 merged (09-30) | A PR writes its row for the PR's own state, so the merge leaves it stale | B3 |
| WS-02, WS-09, WS-10, WS-11 named `03b9e60` as production after `39fc6f9` deployed (09-30) | Rows state current production; every deploy makes them wrong. On #152, eight rows do so again (WS-02, 03, 04, 05, 08, 09, 10, 18) | B2 |
| PRs #142 and #147 conflict with main today; 53 of the 55 merges since 09-28 edited `ROADMAP.md`; 9 PRs needed 12 merge-from-main fix-ups | Every PR inserts its change-log line at the same spot at the top of §8 | B1 |
| WS-05's "Checked 09-30: no MAR-A commit" was wrong (Claude, #139); `addf278` on Codex's branch holds the MAR-A baseline | A "checked" claim without the ref it was checked against | B3 |
| All of the above were found only by hand | No mechanical check | B4 |

## 2. Phase A: finish the catch-up (now)

Run in this order; each script stops on anything unexpected.

| # | Who | Step | Done when |
|---|---|---|---|
| A1 | Larry | Merge PR #152 (WS-19 close) | WS-19 shows complete on main |
| A2 | Larry runs, Claude's row | `land_ws20_plan.sh`: this plan and the WS-20 row | WS-20 is on main as proposed |
| A3 | Larry runs, Claude's row | `land_ws07_text_once.sh`: Mortimer's text sent to the app once (the thread showed each line twice) | merged |
| A4 | Larry runs, Claude's row | `resolve_cc7a1b.sh`: merges main into PR #147, keeps main's WS-17 row and rewrites it as it will read after merge (B3), pushes, waits for checks. Does not merge | #147 green and mergeable |
| A5 | Codex | Review #147 (CX-15). Then Larry merges it; if GitHub reports a conflict again, rerun `resolve_cc7a1b.sh` first | merged |
| A6 | Codex | Resolve and land #142 (WS-08 acceptance); close #138 (WS-19 found it redundant: #139 recorded CX-15) | #142 merged, #138 closed |
| A7 | Larry | Quit Mortimer, run `scripts/deploy_main.sh` | receipt says deployed; production = main |
| A8 | Larry | Mac checks: AirPods to Mac speaker and back mid-answer (WS-18); each spoken answer shows once in the thread (UI2-22); one console row (UI2-24, after #147) | results recorded by the row owners |

Exit: no open PR without an owner and next step in its row; production equals main; A8 recorded.

A7 does not wait for A5. It ships the WS-18 crash fix (merged 09-30), WS-03's Versions wording, WS-04's bind gate (off by default) and the A3 fix. If #147 merges later, it needs a second deploy.

After A7, the eight rows that state current production are stale. B2 replaces that wording in one mechanical sweep, so no system edits them one by one.

## 3. Phase B: stop the drift

### B1 Change log out of `ROADMAP.md` (Codex; Claude reviews)

- New folder `docs/roadmap-log/`, one file per entry: `YYYY-MM-DD-<ws>-<system>-<slug>.md` with front matter `date`, `system`, `rows`, `prs`, then the entry text.
- Migration: a script moves every entry in §8 (72 on main `cc64d50` at the freeze window) into files verbatim; the entry count before and after must match.
- §8 becomes a pointer and one rule: add a file, never edit §8.
- Lands in a freeze window: after Phase A, with no open PR that edits `ROADMAP.md`. Both systems then switch their landing tooling to write a log file. Before #160, Claude's scripts inserted at the §8 anchor; they need a separate switch after #160 merges.

**Implemented in the freeze window, 2026-10-02, PR #160:** All 72 entries from main `cc64d50` were moved one-to-one, with their entry text unchanged. The §8 marker and file-writing rule replace the old in-file entries. Claude's landing scripts need their separate switch after #160 merges.

### B2 One production line (Codex; Claude reviews)

**Merged in #158 (`04eb3f0`), 2026-10-02.** The initial line used the exact `7c4637e` deployment receipt; after the later deployment, #159 refreshed it to `ae70f2c` at 19:23 EDT. The header and affected rows use dated deployment events; WS-03/04 merged-branch drift was corrected without claiming new live acceptance. The Production line changes only after a later deployment receipt exists.

- One line under the title: `**Production:** <sha>, deployed <date time> (receipt <path>)`.
- Rows record events, which stay true: "landed in #144 (`c2f0f49`)", "deployed in `39fc6f9` on 09-30", "accepted on `03b9e60`". Rows never state current production: no "still in production", "present in production", "not in production", "not deployed".
- Whether a landed change is live is computed: is its merge commit an ancestor of the production SHA. B4 reports it.
- Refresh: the first `ROADMAP.md` PR after a deploy updates the line from the newest receipt in `~/MortimerRollback/logs`. Claude's landing scripts will do this automatically; B4 run on the Mac flags a stale line.
- The same PR rewrites the eight rows' production wording mechanically. Owners review only that wording.

### B3 Rows written as they will read after merge (Codex writes the rule; both follow)

**Merged in #158 (`04eb3f0`), 2026-10-02.** Rule 10 requires after-merge wording and a ref for checked/verified claims. C1–C5 are below rule 13; the one-time B2 cross-owner wording review is explicit. B1 replaces the §8 logging instruction in #160.

- A PR sets its own row to what is true once it merges: "landed (branch `x`)", never "review" or "awaiting review". `review` is shown by B4 from open PRs, not written in the row.
- A "checked" or "verified" claim names what it was checked against: "Checked 10-02 on `origin/codex/isolated-20260924` (`addf278`)".
- Edits protocol rule 10 (§0); the rest of §0 is unchanged.

### B4 Drift checker `scripts/check_roadmap.py` (Claude; Codex reviews)

Python standard library only. Reads `ROADMAP.md` and git; `--receipts DIR` on the Mac; `--github` when `gh` is available. One finding per line, `WS-xx: problem (evidence)`; exit 1 on errors.

| Check | Mode | Catches |
|---|---|---|
| Every block has the shared fields; Status starts with a lifecycle word (`proposed` … `accepted`, `blocked`, `parked`) | CI | malformed rows |
| A row in `claimed`, `in-progress` or `review` whose `Where` branch is already merged into main | CI, needs full history | WS-18 and WS-04 on 09-30 |
| A row states current production (B2's phrase list) | CI; warning until B2 lands | the eight rows above |
| The production line matches the newest deployment receipt | `--receipts`, Mac | a deploy not yet recorded |
| An open PR older than 2 days whose number is not in any row's Next step | `--github` | #138, #142 |
| After B1: no entries under §8; every log file has its front matter and names an existing row | CI | change-log edits in `ROADMAP.md` |
| WS ids unique; ids named in §4 and §5 exist | CI | broken references |

- CI: one step in `validate.yml`'s allowlist job, which already checks out with `fetch-depth: 0`. WS-12 edits the same file and has a 10-19 deadline, so WS-12 lands first.
- Tests: `tests/unit/test_check_roadmap.py`, with one fixture per check built from real cases (WS-18's merged branch, the production phrases, a stale log entry).
- Order: B4 can land before B1–B3. The production check warns until B2 lands; the §8 check switches on when §8 says the log has moved.
- Larry decides whether CI fails or only warns. Claude recommends warn-only for the first week, then fail.

## 4. Phase C: working together (standing rules, added to §0 by the B3 PR)

- **C1 Session start (both).** Fetch, read `ROADMAP.md` on `origin/main`, run `python3 scripts/check_roadmap.py`. Fix findings in your own rows first. Report findings in the other system's rows in a log entry; do not edit them.
- **C2 Row ownership.** Each system edits only the rows it owns. Larry-owned acceptance rows (WS-09, WS-10, WS-11): the system that records the evidence updates the row in the same PR. Shared sections (§3 numbers, §4 conflicts, §5 backlog): either system, with a log entry.
- **C3 Reviews.** A PR that changes the other system's code waits for that system's review, as CX-13 and CX-15 already did case by case. A docs-only PR to your own row merges on green checks.
- **C4 PR age.** A PR open more than 2 days has its next step and actor in its row, or is closed. The PR's owner resolves its conflicts.
- **C5 Handoffs.** Next steps name the actor: `claude:`, `codex:`, `larry:`. Handoffs go only through main and PRs (rule 9). Claude still never runs git on the Mac: its work reaches GitHub through scripts Larry runs (§1).

## 5. After the catch-up: who works on what

| System | In order |
|---|---|
| Claude | WS-12 CI runner update (17 days to 10-19 on 10-02) → B4 checker → WS-17 CC7a.2, CC7a.3, CC7a.4 (each reviewed by Codex) → WS-07 guard-mode evidence for Larry |
| Codex | B1–B3 → WS-04 token provisioning once Larry picks the method → WS-03 frozen-release checks → WS-05 MAR-A → reviews of CC7a increments and B4 |
| Larry | Merges, deploys; decisions: WS-04 onboarding method, WS-07 guard mode, WS-10 enablement, B4 warn or fail; Mac checks: WS-18, UI2-22..25, WS-06, WS-09, WS-11, WS-01/02 live gates |

## 6. Exit criteria

- **Phase A:** #138 closed; #142, #147 and #152 merged; production at main; A8 recorded.
- **Phase B:** B4 passes on main in CI; no row states current production; the next 10 PRs merge with no change-log conflict.
- **Phase C:** C1–C5 are in §0.

## 7. Decisions

- **Made (Larry, 10-02):** each system fixes its own rows; B1, B2, B3 and B4 all go in; the plan lives in the repo.
- **Resolved by Larry on 10-02:** WS-12 landed; B1–B3 went to Codex and B4 to Claude; B4 runs warn-only in CI for the first week. The later strict-mode decision remains for Larry after the owned status-word cleanup.
- **Confirmed by Codex, 10-02:** B1–B3 as specified. Each migrated entry gets `YYYY-MM-DD-<ws>-<system>-<slug>.md` with `date`, `system`, `rows`, `prs` front matter; use `prs: []` when an entry has no PR. Preserve entry text verbatim and verify one-to-one count. Do not land B1 while any open PR edits `ROADMAP.md`.

## 8. Risks

- The B1 migration conflicts with every open PR that edits `ROADMAP.md`. Mitigation: the freeze window.
- False positives from B4 could block unrelated PRs. Mitigation: warn-only first week.
- The production line still depends on someone opening a PR after a deploy. Mitigation: Claude's scripts will refresh it, and B4 on the Mac flags it.
- Required cross-reviews add latency. They apply only to the other system's code, not to docs-only own-row PRs.

## Progress

- 2026-10-02 (Codex B1 migration): Fetched `origin/main` `cc64d50` and confirmed there were no open PRs before editing. Moved all 72 §8 entries verbatim into one file per entry under `docs/roadmap-log/`, retaining dates, attributed systems, referenced rows and PRs (explicit `prs: []` when none). §8 now contains the checker marker and a file-writing rule. Updated WS-20 against the merged #158, reviewed #147/#156, and deployed `ae70f2c` facts. The B4 checker remains warn-only in CI and still reports WS-10/11's pre-existing lifecycle words for their owner.

- 2026-10-02 (Codex B2/B3 implementation): Read `~/MortimerRollback/logs/deployment-receipt-7c4637e.json` without changing production. Added the exact deployed revision/time/receipt as the sole Production line; rewrote mutable production assertions in the header and WS-02/03/04/05/09/10 as dated events. Corrected WS-03/04 stale merged-branch states while keeping their acceptance and provisioning gates open. Added the after-merge rule and C1–C5. The B4 checker on the working branch reports only WS-10/11's pre-existing lifecycle-word warnings (their acceptance owner retains them). B1 waits for #147 and any other roadmap-editing PR to close before migration. No application code or runtime configuration changed.

- 2026-10-02 (Codex B1–B3 claim): Larry dispatched Codex through the WS-20 handoff. Codex confirmed the B1 log format above and reserved `docs/ws20-b123-claim-20261002` for the bounded work. #142's roadmap conflict was reconciled and the PR merged as `d01f9af` after five passing checks; Codex's reviews of #147 and #156 requested specific fixes. This claim changes no app code or production state. B1 migration waits for the roadmap PR freeze window; B2's production source will be the deployed `7c4637e` receipt, not main's header.

- 2026-10-02: plan proposed (Claude). Phase A scripts prepared: `land_ws20_plan.sh`, `land_ws07_text_once.sh`, `resolve_cc7a1b.sh` (in `Claude outputs/`). WS-19's reconciliation (#151) had already fixed the rows from Claude's 10-02 review; the remaining items are in Phase A.

### 2026-10-06 — Codex B1/B2 reconciliation

The original 72 entries in §8 at `cc64d50` match 72 migrated file bodies at #160 merge `30fa3db` verbatim; the separate migration entry is additional. B1 is complete. The production line was refreshed from the latest successful receipt, `bde22bb` deployed 2026-10-03 16:34 EDT. Checker strict-mode rollout and the ten-PR conflict observation are not inferred complete. Claude-owned status corrections remain proposed in #172/#174; this update does not claim their merge or new live acceptance.

### 2026-10-06 — Per-item acceptance lists (Codex; requested by Larry)

Added a concrete checklist near the top of every unfinished ROADMAP block, derived from its existing plan/readiness record. Each item names the actor, prerequisite or decision when applicable, and pass criteria. Existing accepted gates and partial passes are retained; no checkbox is newly accepted and no implementation owner/status is reassigned. The list distinguishes proposed mail/brief approval, future CC7a implementation and actual Mac tests, and exposes the untracked WS-06 eleven-item numbering as a documentation prerequisite. Shared receipts can close matching requirements without duplicate runs; source titles disambiguate reused UI2 numbers. This is the bounded roadmap documentation slice authorized in Larry's current request, not a new implementation plan or activation authority.

### 2026-10-06 — Resumed autonomous review and post-merge bookkeeping (Codex)

PR #184 merged as `a4ad5a4` with all five checks successful at `c32620f`. Its checklist documentation is on main; WS-20's historical branch reference is now written as a merged event so the checker does not misidentify the joint workstream as an already-merged active branch. The checker retains only the pre-existing WS-10/11 lifecycle findings; #174 proposes their correction.

Codex completed the assigned CC7a.3 review at #173 head `fb2e06f`: the actual Python revision-stamping/native dispatch closes the wrong newly arrived result after renumbering; the real acknowledgement callback loses ambiguity choices; an opened Older result is absent from the console Close list. Existing 10 Python and 13 Recents tests pass, while the independent wrong-target native witness fails two safety assertions. A separate existing voice comparison schema/secondary-target gap is documented without claiming it was introduced. Findings and causal artifact paths are on the PR; implementation remains Claude's. #172/#174 documentation reviews also record actual merge-tree conflicts and instructions to preserve the checklist/merged-state facts. No deployment, source grant, provider call or acceptance flag changed.

### 2026-10-06 — Review evidence available without human file transfer (Codex)

Embedded the exact public synthetic Python/native witnesses and observed output in the existing resumed-review log entry, exposed through #185. Claude can read/adopt them from the repository without Larry copying `/private/tmp` files. The entry separates defect-confirming Python assertions from the native intended-safety regression and preserves the focused-run/full-runtime distinction; no original product test or implementation behavior changed. #173 remains unapproved until its owner repairs the findings and Codex re-reviews the repaired head.

### 2026-10-06 — Ten published PRs observed without change-log conflict (Codex)

The first ten main merges after #160 are #161/#162/#163/#165/#166/#167/#168/#164/#169/#170, in actual merge order. Root and independent audits replay the exact published parents: all ten complete trees match and §8 is unchanged; both contributing integration merges have clean dated-log/§8 state, including a positive control reproducing one unrelated WS-05 row conflict. The ten-PR published-history observation is closed with [its receipt](../roadmap-log/2026-10-06-ws-20-codex-ten-pr-change-log-observation.md). Erased/rebased/unpublished manual attempts are not inferred. CI strict-mode decision/rollout and the remaining owned status corrections remain open; no live product gate is closed.


- 2026-10-06 (Codex documentation closeout): Starting from main `30dcb4e` and the bounded WS-20 claim, reconciled only WS-10/11's Status lifecycle prefixes under C2. WS-10 remains pending real merged-pipeline acceptance; WS-11 remains pending C8 on the Mac. Owners, dates, all acceptance checkboxes, historical limitations and rollout decisions are unchanged. B1–B4 and the ten-published-PR observation remain closed; checker enforcement and remaining live exit evidence remain open. The dated closeout entry records the checker and current production-receipt comparison. A separate dated WS-13/17 reviewer handoff records current draft-contract contradictions and unchanged #173 findings; it does not edit Claude's implementation or choose unresolved design/account settings. #172/#174 remain their owner's roadmap integrations.

- 2026-10-06 (Codex voice-test evidence): Larry performed a voice session on installed `bde22bb` and requested log review. The dated WS-20 voice-acceptance entry records seven user entries, ten Mortimer entries, five replies over 160 characters, full ordered native accessibility matching, requested-result opening and research selection preservation with a visible New notice. Only those bounded subchecks pass; full UI2-22…25, external transfer, Skills/memory/model activation and their required tails remain open. The review sent no additional voice/model request or production write.

### 2026-10-07 — Operational-roadmap scope claim (Codex; Larry approved)

Larry approved a documentation-only WS-20 claim expansion before substantive edits: a compact operational summary, decision queue, linked acceptance grouping and narrow stale wording, keeping ROADMAP.md the shared source. The implementation branch is `docs/ws20-operational-roadmap-20261007`. Concurrent #191 closeout/evidence merged as `b6f09f4` and was integrated into this claim without losing its checklist/receipts. Claude-owned #172/#174 integration and #173 repairs remain pending in their existing PRs. Larry expressly authorized merging this claim after checks, then preparing a separate draft for his review; he did not authorize merging the substantive update or other PRs. Preserve owners, detailed blocks, acceptance decisions and exact-build evidence. No new plan, activation, provider workload or deployment.

### 2026-10-07 — Operational summary and acceptance navigation (Codex)

Claim #192 merged as `e74f3af52a77e9651b0127d91da7bf6bba31b3fb` after five green checks at `d515286`. Codex refreshed/integrated main before edits on `docs/ws20-operational-roadmap-20261007`. Added a compact operational summary, existing Larry decision queue and linked ready-versus-dependent acceptance groups inside ROADMAP.md; the detailed blocks remain authoritative, with no second tracker or overall percentage. Recommended the everyday conversation/result milestone around WS-17/21 without reassignment or approval.

Reused #174's narrow WS-21 merged/deployed fields and WS-11 deployment reference rather than inventing a second correction; #172/#174 conflict integration and the supporting-display plan update stay Claude-owned. Corrected WS-17's stale new-branch/WS-21 dependency wording to the existing #173 repair/review handoff. #191 merged separately as `b6f09f4` during claim CI; its lifecycle prefixes, completed documentation gate and exact-build voice/review receipts are preserved and linked. Bounded public text/routing subchecks need no redundant rerun solely for documentation. Full UI2-22…25, external display, enabled authentication/model/memory and release acceptance remain open.

Validation: roadmap structural/warn-only checks, diff whitespace, policy checks and preservation/source-link audits; all owners/scopes, gate entries, production identity, protected sections and existing receipts retained. A just-created implementation branch initially equaled its claimed main base, so the session-start checker mechanically called that empty branch “already merged”; the after-merge documentation state removes that transient own-row finding. No checker change or suppression. This substantive PR remains a draft for Larry; no product feature, provider workload, credential, activation or deployment change.


### 2026-10-17 — Acceptance first; future workflow parked (Codex)

Larry explicitly requested saving the model-independent investigation workflow
as a document and placing it at the end of the roadmap, with all existing
acceptance gates closed before new development. Added parked WS-22 and its
canonical plan; even isolated-core development is deferred. This is a bounded
documentation addition to WS-20, not a new implementation or acceptance grant.

The [dated triage](../roadmap-log/2026-10-17-ws-20-codex-acceptance-first.md)
records the refreshed source, installed-build evidence, pending Claude PRs,
ready preparation/human checks, and blocked prerequisites. No product checkbox
is changed. Preserve #205's production/WS-13 corrections and #172/#174's owner
updates; do not duplicate those edits. Existing prerequisite code/activation
and any permitted known-limitation acceptance need their explicit decisions.


### 2026-10-17 — Open PR cleanup (Codex; Larry requested)

Reconciled stale documentation PRs #172/#174 onto main `1338fc7`, preserving
current roadmap facts, acceptance-first sequencing, and all existing gates.
Recovered Claude's two historical log entries verbatim and the outstanding
WS-21 implementation/deployment plan correction from #174. The corrected
plan still leaves Mac acceptance open. Published one replacement documentation
PR before closing superseded #172/#174; keep their branches and attribution.
Mail-preflight #205 remains a separate exact-head review, not folded into this
change. See the [cleanup record](../roadmap-log/2026-10-17-ws-20-codex-pr-cleanup.md).


### 2026-10-17 — Existing acceptance campaign (Codex)

Larry requested execution of all existing acceptance testing and offered human
intervention. Branch: `codex/acceptance-campaign-20261017`; frozen automated
source: `9f9bc71c26c82c832121be118346abaa1b4f89a4`. Installed live candidate:
`575cc7b770b621b5c8049097ef63e93618ba3016`. Test and record only; no feature
implementation, activation, production edit or deployment. AirPods available;
external display unavailable. Record results in the dated campaign receipt
and existing acceptance lists without converting subset passes into parent
sign-off. WS-22 remains parked.

Progress: Larry accepted the exact WS-18 switch criterion on installed
`575cc7b` (both directions, short/imperceptible gaps, survival and output-flow
logs). Current weather testing finds stale Recents, incomplete voice selection and
missing fresh-result reopening/reference behavior. Those are blockers, not
closed gates. Runtime source remains unchanged. Full host Python: 6,688 passed,
15 skipped, five failures; four wiring failures also reproduce in the separate
integration suite. Independent verification and remaining bounded live checks
are recorded in the campaign receipt; no test threshold is relaxed.

Final testing follow-up on `codex/acceptance-campaign-results-20261017`:
initial evidence #208 merged as `f363444` while verification ran. All twelve
independent checks on exact `9f9bc71` passed with unchanged source and validated
log/profile/runner identities; both owned VMs stopped. Disabling automatic
dotenv discovery eliminated the five configuration-contaminated host Python
failures. The remaining 5 ms deadline case passed quietly and in both VM unit
runs. The final host native suite passed the performance benchmark but failed
two Vision OCR calls; both failed again in the focused retry, leaving physical
Mac verification open. Recents/reuse and mail-preflight findings also remain.
No runtime, test, production configuration or activation changes were made.

### 2026-10-17 — Current status / right-pane refresh (Codex)

Larry requested updated roadmap statuses. Documentation branch
`codex/roadmap-status-20261017` starts from `f363444` and reconciles the shared
summary and Codex WS-17/20 handoffs. #204/#205/#207/#208 are merged; #209 final
evidence and #210 Tart cleanup remain open. Preserve the successful `575cc7b`
deployment receipt and separate current checkout/dirty-artifact provenance.
WS-18's bounded gate is accepted; Recents/reuse, physical-Mac OCR verification,
mail preflight, external hardware and other prerequisites remain open. Detailed
receipts and every checkbox are preserved. See the
[status reconciliation](../roadmap-log/2026-10-17-ws-20-codex-current-status-refresh.md).
No implementation, gate waiver, merge or deployment is included.


### 2026-10-17 — Consolidated enhancement intake (Codex)

At Larry’s request, map all eight supplied items into the shared roadmap.
Baseline/acceptance stays with existing owners; Mail Reader stays WS-13 P5
(separate from P4 prose); evidence/handoff stays WS-22. Add proposed, parked
WS-23 verification within Systems, WS-24 durable tasks, WS-25 Scheduler/Librarian
commitments and WS-26 event follow-through, with dependencies and acceptance
checklists. Preserve daily-report behavior as a baseline inventory requirement,
not an unsupported claim about complete deployed capability. Reconcile WS-22’s
future lifecycle with WS-24 so it cannot become a competing task authority.
No implementation is claimed or started; no existing acceptance box changes.

### 2026-10-17 — Three-PR review and cleanup (Codex)

Larry requested review and cleanup of the three PRs. #212 had already merged
as `f3d5378` when checked. #209's sole conflict was an appended progress record:
both entries are preserved, as are all receipts and acceptance limitations.
The twelve independent check hashes match the attached manifest. #210's
focused suite passed, but a mocked-Tart reproduction deleted a development VM
after its session began validation and a running child appeared; its cleanup
module is also absent from runner identity. Keep #210 open for scoped repairs
and re-review. No real VM was pruned, no mailbox contacted, and no deployment
or acceptance gate changed. Details: [review record](../roadmap-log/2026-10-17-ws-20-codex-three-pr-review.md).


### 2026-10-18 — Restore parked enhancement intake after #211 merge (Codex)

The 10-17 `fc9c958` candidate added the eight-item intake and four parked WS-23–26 cards after PR #211’s merged head `98ad864`. The merge therefore did not contain those later additions, although the old right-pane preview showed them. Rebased the exact documentation additions on current main `28420af`, preserving the separate three-PR review note and all intervening WS-17/13/20 source. The restoration creates no implementation claim, deployment or acceptance.

## 9. Acceptance clearance — current priority, 2026-10-18

Larry requested this concrete clearance plan and an accurate current status
report before enhancement implementation. This dated addition supersedes older
next-action/PR-status narratives in this plan; it does not change historical
receipts or product pass criteria. [Roadmap current status](../../ROADMAP.md#acceptance-clearance--next-priority--2026-10-18),
[current status report](../acceptance/IMPLEMENTATION_STATUS.md) and
[release checklist](../acceptance/adaptive-interface/RELEASE_READINESS.md)
use current main `9ea27c7`, refreshed 2026-10-18 after #218/#219 merged. The 97-obligation inventory source links stay pinned to initial `28420af`; runtime code and these active bullets are unchanged by the two documentation merges.

### Counts and what they mean

- **26 existing workstreams:** 14 retain current acceptance/decision obligations,
  seven are closed, five (WS-22–26) are parked. #219 merged during publication,
  restoring four parked cards with 15 future unchecked criteria. There are now
  **112 unchecked workstream bullets: 97 current obligations + 15 parked criteria**.
  WS-27 is a new documentation row excluded from these product-backlog counts;
  the 15 parked criteria are excluded from the runnable clearance queue.
- **97 unchecked aggregate bullets** across the 14 blocks, not 97 distinct
  tests. Counts by workstream: WS-17 11; WS-13 5; WS-20 2; WS-21 5; WS-05 10;
  WS-01 6; WS-04 7; WS-02 6; WS-03 10; WS-06 7; WS-07 5; WS-09 11;
  WS-10 6; WS-11 6. Eight extra MAR summary bullets repeat WS-05 obligations.
- **34 unchecked / 19 checked** entries in release readiness (the old 30/19
  prose was stale). The release backbone has **23 unique open UI2 IDs**:
  02–20 and 22–25. UI2-01, UI2-04a and UI2-21 stay checked. These IDs include
  compound requirements and cannot be equated to 23 individual executions.
- **24 P0 compound rows** and **five C8 umbrellas** overlap UI2 coverage;
  do not add these to the UI2 total. Skills has ten remaining SW gates
  (A,D,E,F,G,H,I,J,K,L), with B/C accepted. Model access has eight open MAR
  families (A,D,E,F,G,H,I,J); B/C foundations do not prove enabled workloads.
- Mail R.12 has **28 source rows** (S1 9, S2 5, S3 14) and **11 Mac rows**
  (M1 3, M2 2, M3 6). They are a coverage matrix, not 39 currently runnable
  tests. M1-2/3 retain October 13 bounded passes; M1-1 needs repeat after #212
  deployment; eight M2/M3 rows and 19 S2/S3 rows wait for P2/P3 implementation.

No audit-only parent checkbox closes. Different source matrices overlap and
have different scope; there is no defensible single “unique tests remaining”
number without breaking compound criteria into approved cases. The complete
97-obligation inventory below is exhaustive at the roadmap-bullet level; the
UI2 and feature-family maps identify the canonical requirement authorities.

### Current evidence dispositions

| Status category | Current truth and next action |
|---|---|
| Accepted with receipt, bounded scope | WS-08/12/14/15/16/18 and WS-19 documentation are closed in the roadmap. Preserve WS-18 switching, Skills B/C and Versions wording, orb, named historical display and bounded conversation/card results. Match build/config/scenario before reuse; a subset never closes a parent. |
| Runnable after candidate release prerequisites | UI2-24/25 fail-fast first; then 22/23 and dependent 04/09/13, Atlas/graph, selected sharing, enabled voice/accessibility and roadmap controls. Actual device/provider actions still need their established scope. |
| Blocked by repair/review/deployment | #210 is merged, not open; its stale-prune-plan race and omitted runner fingerprint remain unrepaired in inspected files. #216 is merged, not a draft; its Claude review timed out without verdict. Independent exact-release verification, deployment/loaded identity and live retest remain open. No cleanup runner is safe merely because focused tests passed. |
| Blocked by unimplemented or undecided prerequisite | WS-04 onboarding; WS-13 P2/P3, with P4/P5 later; Skills auth/VM/source/model/eval route; WS-02/05 runtime/source/account/confidential-route; WS-10 staged real-use decisions; WS-06 missing eleven-check map. These are not immediate Larry test chores. |
| Hardware unavailable | External hardware was unavailable October 17. Current physical availability must be checked before booking B3. Mirrored/three-screen/portrait/non-Retina cases remain blocked unless provided; synthetic virtual displays prove only their subset. |
| Elapsed observation pending | Five frozen-candidate daily-driver days (UI2-17), distinct earlier native-client attestation, WS-06's week without unsolicited commands, WS-10's approved staged observations. Concurrent observation is reusable only when dates/build/scenarios meet each criterion. Calendar passage alone is not evidence. |
| Explicitly parked/deferred | WS-22–26 (including proposals restored by merged #219) and WS-27 enhancement implementation. Optional remote activation and later private mail/model stages require decisions; deferral is neither a pass nor deletion of an obligation. |

**Newer evidence matters:** the October 17 campaign's two physical Vision OCR failures
remain recorded failures at their tested revision. Later #216 source evidence
reports MortimerHost **563 tests, five skips, zero failures**; reconcile exact
coverage/configuration before scheduling an OCR investigation. That later local
suite does not establish independent release or live acceptance. [Latest scoped
record](../roadmap-log/2026-10-17-ws-17-codex-roadmap-controls.md) and
[historical campaign](../acceptance/command-console/receipts/acceptance-campaign-2026-10-17.md)
remain linked rather than overwritten. No runtime tests ran for this audit.

### Shortest practical clearance sequence

Estimates below are planning ranges, not measured promises; stop a batch at its
first blocking failure. Prepare scripts and expected outcomes before Larry
sits down. Reuse one manifest and one evidence packet across applicable rows.

| Batch / order | Existing actor; work and dependency | Estimated operator time / elapsed | Exact exit |
|---|---|---|---|
| B0 — Evidence and release prerequisites | Existing Codex/Claude owners reconcile receipts, obtain missing exact-source #216 cross-review, repair/re-review both #210 findings under a fresh owning claim, and establish safe verification. Freeze one candidate; perform required independent suite/rollback preparation before separately authorized deployment. No feature/pruning work authorized by this plan. | Documentation/triage 1–2 h agent time; repair/review/VM duration unknown; Larry 10–15 min for concrete decisions once prepared | Source/build/config/hash/profile match; all required checks pass or explicit blockers. No pruning/reclaim while race unresolved. Selected deployment has its own authorization/receipt. |
| B1 — Fail-fast Recents/reuse | Larry, supported by Codex, on identified candidate after B0. Weather→Atlanta→original; ordinal/subject/stale/ambiguous targeting, refreshed Recents, pin/close/reopen; inspect result IDs and fetch counts. | 10–15 min | UI2-24/25 remaining criteria evidenced. Failure returns to scoped repair; do not spend a longer session on dependent UI. |
| B2 — One console/results/accessibility session | Larry + recorder, after B1. Finish22/23, dependent 04/09/13; shared actions03, Atlas05, sharing07/inbound08; roadmap completeness/provenance/filters/refresh. Cross-map applicable P0/C8, WS-01/09/11 and ready Skills A/D/I subparts. Use disposable targets and approved public/synthetic payloads. | 35–50 min, optional pause halfway | Exact scenario/expected result/trace for each covered row; ordinary speech stays in Conversation, no duplicate compact transcript; no false shared parent closure. Auth/creator-dependent Skills portions wait. |
| B3 — One physical display session | Larry + recorder with required hardware and B1/B2 candidate. UI2-06/19/20 + WS-21 transfer/repeat/refusal/disconnect/recovery and matching WS-01/09/11. Pair real display loss with draft/result/graph preservation. | 20–30 min when hardware exists; additional topologies estimate separately | Correct content and screen, real confirmation, identity/fetch/window bounds, latest manual intent and ≤1 s reachable controls where required. Record unavailable topologies individually. |
| B4 — Automated contracts plus short audible check | Existing implementation/evaluation owners automate03/10/11 contracts/security/menu/compatibility and synthetic failure/reconnect/load; Larry observes12 audio and outstanding physical device/echo cases. Controlled child crashes only in separately approved test scope. | Agent tests 1–3 h estimate; Larry 15–25 min; audio matrix may need more | Fixed denominators, no skip counted as pass; exact build/load/device metrics and audible result, separate WS-18 already accepted switching. |
| B5 — One shared observation window | After verified frozen release, recorder links UI2-17 five-day sessions and compatible native/WS-06 observations; WS-06 week remains a full week. WS-10 staged use is separate and not activated here. | Five days minimum; WS-06 week where applicable; Larry 2–3 min/day check-in estimate | Daily task/build/config/outcome evidence and Larry attestation; material fixes restart affected frozen observation; no elapsed-only pass. |
| B6 — Reconcile and close exact scope | Existing acceptance owners publish UI2-14/15/16 receipts where not already satisfied by B0; final UI2-18 and WS-20 exit; Larry signs outcomes/explicit permitted limitations. | 30–60 min agent paperwork; Larry 10–15 min | Every current-release criterion maps to positive evidence, an explicit blocker, or a governing-plan-permitted written limitation. Feature-specific future obligations remain visible. |

B0 static evidence mapping, offline corpus/contract preparation and hardware
availability planning can proceed independently in separate scopes. B4 offline
fixtures can run while a reviewer inspects B0; do not concurrently mutate the
candidate, run competing audio loads, access the same live test resources or
prune VMs. Existing owners retain claims. This is safe work scheduling, not
assignment of agents or authorization to start processes.

**Expected Larry time:** roughly 1.5–2.5 hours of batched active checks plus short
daily observations, excluding unresolved setup/repair, special hardware and
prerequisite features. The range is an estimate derived from B1–B6, not a promise
that all 97 aggregate obligations can close in that time.

### Canonical current-release requirement map (23 open UI2 IDs)

Primary categories here classify unique IDs for planning, not runnable atomic
tests: evidence/reconciliation **2**, automated contracts **3**, release
verification/rollback/deployment **3**, Larry UX/voice/accessibility **10**,
physical displays **3**, combined performance/audio **1**, elapsed observation
**1** = **23**. Per-ID dependencies and evidence:

| Canonical ID | Primary category / batch | Required evidence; shared coverage |
|---|---|---|
| UI2-02 | Evidence / B0 | Baseline manifest and exact preservation map; extends P0/C8/T1.3, not an extra full replay. |
| UI2-03 | Automated / B0/B2 | Owner/schema/action acknowledgments and actual shared UI action; WS-01/09/11 contracts. |
| UI2-04 | UX / B2 | Conversation/sidecar after 22–25; P0 relevant controls. |
| UI2-05 | UX / B2 | Atlas/graph source, selection/pins/comparison, partial data and recovery. |
| UI2-06 | Hardware / B3 | Applicable one/two/three/mirrored topology and real recovery; historical receipt subset only. |
| UI2-07 | UX / B2 | Selected text/image preview/copy/save/share/cancel, no adjacent private content. |
| UI2-08 | UX / B2 | Approved inbound preview/provider/bounds/cancel/cleanup; malformed/injection cases automated first. |
| UI2-09 | Voice / B2 | Every enabled shared action via voice; after 22–25, ambiguity/stale/OS boundary. |
| UI2-10 | Automated / B4 | Security V2–V6 extension and memory/sink canaries; feature-specific prerequisite isolation. |
| UI2-11 | Automated / B4 | Routing/menu/schema/capability/old-client parity, current fixed denominator/floor. |
| UI2-12 | Combined / B4 | Target-Mac load/performance and real audible behavior; no virtual audio proxy. |
| UI2-13 | UX / B2/B3 | C8/P0/T1.3 visual/accessibility sizes; unavailable physical variants explicitly blocked. |
| UI2-14 | Release / B0 | Independent full-profile receipt for exact candidate/runner, no mock or historical replacement. |
| UI2-15 | Release / B0/B6 | Actual authorized rollback preserving drafts/preferences/files and pending-transfer policy. |
| UI2-16 | Release / B0 | Separately authorized deployment plus loaded app/backend/hash/config/health identity. |
| UI2-17 | Observation / B5 | Five stable frozen-candidate days with outcomes; not old layout-1 attestation. |
| UI2-18 | Evidence / B6 | Final coverage and explicit remaining gaps/Larry decisions. |
| UI2-19 | Hardware / B3 | One renderer per result, repeat reuse, locator/pin and no duplicate fetch/subscription. Current CC7a ordinary speech stays in Conversation. |
| UI2-20 | Hardware / B3 | Bounded external stage, content roles/pins/topology/recovery; no extra windows. |
| UI2-22 | UX / B2 | Five full ordered spoken turns/protected turns/read focus; preserve October 17 bounded subset. |
| UI2-23 | UX / B2 | Requested result arrival versus late/background; preserved reading/selection/display identity. |
| UI2-24 | UX / B1 | Recents refreshed/ordinal/subject/stale/ambiguous/pin/close/reopen, accepted one-row subpart retained. |
| UI2-25 | UX / B1 | Two-card weather sequence, ≤15 min reuse no fetch, stale refresh same identity/reference. |

[Canonical full criteria](../acceptance/adaptive-interface/RELEASE_READINESS.md#todo--command-console--knowledge-atlas-implementation-closure)
remain unchanged except reconciliation of obsolete pre-CC7a answer-routing
wording. [P0](../acceptance/adaptive-interface/P0-preservation-checklist.md),
[C8](../acceptance/adaptive-interface/C8-open-items.md),
[display scope](../acceptance/command-console/DISPLAYS.md) and
[procedures](../acceptance/ACCEPTANCE_RUNBOOK.md) supply detailed steps. For each
covered P0 row record exact mode/action and receipt; C8's five umbrellas close
only from their complete scoped coverage. No summing overlapping test lists.

### Prerequisite and decision queue outside the immediate sessions

| Existing owner/source | Needed decision/work | Disposition and exit |
|---|---|---|
| WS-04 Codex/Larry | Select onboarding method, then fresh implementation/disposable proof, then separately authorized live preparation/activation | Unbuilt/undecided, not a ready test; remote mode separately optional. No token/security change here. |
| WS-02/05 Codex/Larry + cross-reviewer | Exact runtime/source/operator identity, missing reviews, account/overage/budget, eligible confidential route, safe nonempty developer sandbox proof | Blocked until those receipts/decisions; use shared WS-02/05 evidence once. Do not silently substitute paid API or an ineligible catalog model. |
| WS-03 Codex/Larry | Auth, creator real VM, source/model/eval route, SW-F/G/H | B/C accepted; ten remaining gates retain their own scope. Ready UI subparts can share B2, provider/creator work waits. |
| WS-10 existing owners/Larry | Eligible memory route, staged approvals, real shadow/admission/benefit evidence | Six aggregate obligations remain; synthetic tests cannot replace first 20 decisions or observation. No enablement here. |
| WS-13 existing Claude owner/Larry | Preserve D1–D9 already recorded October 10; verify deployed daily-report path without duplicating it. P1 M1-1 after #212 deploy; P2/P3 require fresh implementation scope | Revised R.12 replaces August V1–V10. Do not ask already answered plan questions or schedule eight unbuilt Mac rows. P4/P5 remain later/private-gated. |
| WS-06 Claude/Larry | Bring missing eleven-check mapping into existing repo plan; tier decision; actual spoken/recovery/probe evidence and one-week behavior | Do not inspect private Claude working folders or guess numbers. Known repo-backed scenarios may share B2/B4; external/runtime scope remains gated. |
| WS-07 Claude/Larry | Genuine reply-guard precision/false-refusal evidence then log/correct decision | Four historical events insufficient; keep current mode until explicit decision, no automatic activation. |
| WS-20 Larry | Warn-only checker → blocking decision | Documentation checker passing does not decide enforcement. |
| WS-01/09/11 and Larry | Missing topology/hardware, old V9 attestation, applicable known-limitations decision | Record not-applicable only with requirement-specific rationale/authority; defer if governing plan permits, otherwise blocked. Neither is a pass. |

Acceptance-first prioritizes current release gates and **scoped prerequisite
repairs needed for acceptance**. It does not create a circular ban on building
an unbuilt prerequisite while pretending its acceptance test is runnable. Nor
does it make every optional/unimplemented feature a new global release gate.
Keep obligations in their owning rows; Larry decides staged scope/disposition
under each governing plan. New enhancement implementation remains subsequent
and requires a fresh dispatch. Sandbox design/document review can proceed.

### Evidence reuse and exit rules

Use one receipt per session containing source/build/config/device identity,
case IDs, exact steps/expected/observed outcome, timestamp and raw evidence
references; cross-link it into every genuinely covered row. Reuse accepted
unchanged subparts after an applicability review. A source/material-config
change invalidates affected evidence only, with the reason recorded; frozen
release observation follows its stricter restart rule. Do not repeat a passing
AirPods switch just to fill a second list, reopen orb/SW-B/C, or replace a
historical failure with a newer unrelated suite count.

No test count is reduced by deleting rows, changing a denominator, weakening a
threshold or converting blocked/skipped/unknown into pass. Consolidation changes
execution scheduling and evidence links, not required behavior. Larry's written
accepted limitation applies only where the governing plan permits it and to
its named build/scope; it remains a recorded gap. No parent UI2 gate is closed
from this read-only audit. At B6 publish true remaining categories and explicit
feature-specific decisions, rather than an unsupported overall percent complete.

### Complete roadmap obligation inventory (97 aggregate bullets)

Ordinals below identify unchecked bullets in the inspected main block; they are **not new test IDs**. Links pin the inspected revision, so moving rows cannot silently change a reference. Actor names are copied from source, not assigned here. Each row preserves the full linked pass condition; the last columns identify primary disposition, dependencies/batch and required evidence. Categories are exclusive for counting only; an obligation may need several kinds of work. All remain open or prerequisite-blocked unless an explicitly named subpart has bounded prior evidence.

Category key: **A** automated regression; **B** decision/access or unimplemented dependency; **C** explicit code prerequisite; **D** review/release/deployment/evidence; **H** physical hardware; **O** elapsed observation; **S** reproducible system/sandbox test; **U** Larry UX/voice/accessibility.

Primary-category counts: **A 4**, **B 22**, **C 1**, **D 12**, **H 11**, **O 4**, **S 16**, **U 27** = **97**. These are obligation counts, not estimated test counts or unique executions.

| Source / ordinal | Existing actor and requirement | Primary category | Batch / dependency | Current disposition and evidence needed |
|---|---|---|---|---|
| [WS-17/01](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L247) | Larry · current five-turn conversation | U | B2 | Bounded old conversation evidence; finish exact-candidate UI2-22. |
| [WS-17/02](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L248) | Larry · current arrival-routing recheck | U | B2 | Partial card evidence; finish UI2-23 including late/background results. |
| [WS-17/03](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L249) | Codex / cross-reviewer / Larry · CC7a.3 implementation prerequisite | D | B0/B1 | Implementation merged, including #216; missing exact-source review/independent release proof, not a new CC7a build request. |
| [WS-17/04](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L250) | Larry · Recents live tail after CC7a.3 | U | B1 | UI2-24 fail-fast: refreshed inventory, ordinal/subject, ambiguity, pin/close/reopen. |
| [WS-17/05](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L251) | Codex / cross-reviewer, then Larry · CC7a.4 implementation and reuse | U | B1 | UI2-25 fail-fast: two cards, same identity on reuse, fetch counts and stale refresh. |
| [WS-17/06](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L252) | Larry / evidence recorder · dependent closure | U | B2 | Reuse B1/B2 receipts for dependent UI2-04/09/13 only where exact scenarios match. |
| [WS-17/07](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L256) | Codex · read-only roadmap result | U | B2 | Roadmap complete workstream representation on tested source. |
| [WS-17/08](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L260) | Codex · provenance and refresh | U | B2 | Checkout/main/deployed distinction; hash/read time/refresh and dirty marker. |
| [WS-17/09](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L264) | Codex · voice and existing controls | U | B2 | Voice roadmap + existing controls; one shared action/identity. |
| [WS-17/10](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L268) | Codex / Larry · roadmap filters | U | B2 | All named filters and clear/focus via pointer and voice. |
| [WS-17/11](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L274) | Cross-reviewer / Larry · acceptance | D | B0/B2 | Exact-source review then actual Mac outcomes; #216 timeout supplies no review verdict. |
| [WS-13/01](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L307) | Claude / Codex · prerequisite review | B | P-mail | Reconcile latest revised R scope; use #204/#205/#212 review, no superseded August criteria. |
| [WS-13/02](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L308) | Larry · plan decisions | B | P-mail | D1–D9 already answered October 10 (R.0d/R.5); retain choices, only actual outstanding account/setup scope stays pending. |
| [WS-13/03](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L309) | Claude / Codex · implementation and security evidence | A | P-mail | P1 synthetic evidence exists; reuse applicable R.12 S1 receipts. P2/P3 S2/S3 wait implementation. |
| [WS-13/04](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L310) | Larry · future Mac checks | B | P-mail | M1-2/3 October 13 preserved; repeat M1-1 after fixed #212 deployment. Eight P2/P3 Mac rows unbuilt. |
| [WS-13/05](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L311) | Larry / Claude · release | D | P-mail | P1 preflight release proof separate; later P2/P3/P4/P5 require own claim and applicable Mac proof. |
| [WS-20/01](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L384) | Larry · decision | B | Decision | Larry decides checker enforcement after warning-period evidence; no test rerun substitutes. |
| [WS-20/02](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L385) | Each acceptance owner · evidence | D | B6 | Publish linked exact evidence/limitations and owning decisions; no new product gate. |
| [WS-21/01](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L411) | Larry / Codex · real transfer | H | B3 | Physical external display: correct content/screen; confirmation before success. |
| [WS-21/02](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L412) | Larry · repeated request | H | B3 | Repeat transfer: already-showing, no duplicate fetch/window. |
| [WS-21/03](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L413) | Larry / Codex · rejected destinations/content | H | B3 | Disconnected/stale/protected/unknown targets refuse without side effects. |
| [WS-21/04](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L414) | Larry / Codex · disconnect during confirmation | H | B3 | Disconnect/race rollback preserves newer placement and no orphan window. |
| [WS-21/05](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L415) | Larry / Codex · placement and inventory | H | B3 | Inventory/content/placement agreement; virtual evidence is subset only. |
| [WS-05/01](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L441) | Larry · prerequisites | B | P-model | Source authority/operator identity/test-repair assignments remain decisions, not immediate live tests. |
| [WS-05/02](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L442) | Claude · review | B | P-model | Obtain missing cross-system review of exact #177 source; do not infer from merge. |
| [WS-05/03](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L443) | Codex / Larry · baseline and release identity (MAR-A) | D | B0/P-model | Freeze actual artifact/configuration and representative baseline, historical unknowns stay unknown. |
| [WS-05/04](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L444) | Codex · effective routing and privacy (MAR-B/C/D/G) | S | P-model | Approved enabled-mode source/sink/cancel/budget proof per workload; no route activation here. |
| [WS-05/05](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L445) | Codex / Larry · subscriptions (MAR-F; shares WS-02 evidence) | S | P-model | Share accepted exact-runtime subscription/isolation evidence with WS-02. |
| [WS-05/06](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L446) | Codex / Larry · SAYGM (MAR-E) | B | P-model | Catalog advertises zero confidential models; eligible route/attestation needed before pilot. |
| [WS-05/07](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L447) | Codex / Larry · representative pilots (MAR-I) | S | P-model | Equivalent research, nonempty developer all-12-check pilot and confidential synthetic workload; no mock substitution. |
| [WS-05/08](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L448) | Larry, supported by Codex · controls (MAR-H) | U | P-model | Approved native/spoken route controls agree with actual route; stale/refused/cancel. |
| [WS-05/09](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L449) | Codex / Larry · quality and latency | S | P-model | Cold/warm quality/latency under existing MAR targets; scope/budget prerequisites first. |
| [WS-05/10](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L450) | Larry / Codex · account and rollout (MAR-J) | B | P-model | Account/allowance/overage decision and staged rollout authorization, then exact release/rollback evidence. |
| [WS-01/01](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L479) | Codex / Larry · preparation | D | B0 | One shared candidate manifest, source/app/backend/config/hash/date. |
| [WS-01/02](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L480) | Larry, supported by Codex · display recovery | H | B3 | Reuse matching transfer/display recovery receipts; unavailable topology stays blocked. |
| [WS-01/03](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L481) | Larry / Codex · Atlas freshness | U | B2 | Atlas auth/freshness/late response/partial failure; no duplicate fetch. |
| [WS-01/04](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L482) | Larry / Codex · spoken, sharing and accessibility journeys | U | B2 | Selected sharing/inbound, actual voice and accessibility; reuse matching P0/UI2 cases. |
| [WS-01/05](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L483) | Owning systems / Larry · dependencies | B | Owning gates | Feature-specific model/memory/speaker/security dependencies remain under their plans; no blanket new release gate. |
| [WS-01/06](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L484) | Codex / Larry · release closure | O | B5 | Independent release + rollback first; five stable frozen-candidate daily-driver days. |
| [WS-04/01](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L510) | Larry · prerequisite decision | B | P-auth | Larry selects onboarding method; recommendation is not decision. |
| [WS-04/02](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L511) | Codex · implementation prerequisite | C | P-auth | Onboarding not built: fresh implementation claim for selected method before acceptance. |
| [WS-04/03](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L512) | Codex · disposable acceptance | S | P-auth | Disposable first/repeat/interrupted/failure, flag/socket/auth proof after implementation. |
| [WS-04/04](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L513) | Larry / Codex · live preparation | B | P-auth | Separate approved live preparation; no credential work in docs task. |
| [WS-04/05](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L514) | Larry / Codex · local activation, if approved | B | P-auth | Local activation only if explicitly chosen, with 401/auth/sockets/revoke/rollback proof. |
| [WS-04/06](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L515) | Larry · spoken check | U | P-auth/B2 | Actual spoken system_status on frozen authorized setup, share WS-06 exact scenario. |
| [WS-04/07](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L516) | Larry / Codex · remote mode only if separately chosen | B | P-auth | Remote activation separate optional decision; defer as limitation if chosen, never pass. |
| [WS-02/01](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L542) | Codex · runtime identity | S | P-model | Service-resolved runtime/hash/version/model/capability; unverified remains unavailable. |
| [WS-02/02](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L543) | Codex · installed-runtime isolation | S | P-model | Actual runtime stdin/env/temp/hooks/plugin/MCP isolation, no credential bleed. |
| [WS-02/03](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L544) | Codex · lifecycle | S | P-model | Actual-runtime success/failure/timeout/cancel cleanup and child reaping, no late result. |
| [WS-02/04](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L545) | Codex / Larry · authenticated workload | B | P-model | Authenticated supported workload needs provider/source/budget scope; share WS-05. |
| [WS-02/05](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L546) | Larry · account evidence | B | P-model | Supported account surfaces for allowance/billing/overage; list prices do not prove zero cost. |
| [WS-02/06](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L547) | Codex / Larry · release | D | P-model | Exact source/runtime/config and release/activation evidence after prerequisite proof. |
| [WS-03/01](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L573) | Codex / Larry · remaining deployed baseline (SW-A) | U | B2 | SW-A remaining baseline on exact release; B/C and Versions wording remain accepted. |
| [WS-03/02](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L574) | Codex / Larry · recorded runs (SW-D) | B | P-auth | SW-D recorded-run cases need owner-authenticated inventory, then event/reconnect proof. |
| [WS-03/03](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L575) | Codex · privacy and owner boundaries (SW-E) | A | P-auth | SW-E owner/privacy synthetic canaries, SQL/JSONL/log/diagnostic/screenshot/export sinks. |
| [WS-03/04](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L576) | Codex / Larry · real sandbox (SW-F) | S | P-auth/P-model | SW-F real offline VM and admitted creator; cleanup blocker first, no host fallback. |
| [WS-03/05](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L577) | Codex / Larry · paired quality evaluation (SW-G) | B | P-auth/P-model | SW-G six cases × two repeats × conditions =24 trials; approved route/budget then blinded >=10/12. |
| [WS-03/06](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L578) | Codex / Larry · lifecycle and activation (SW-H) | S | P-auth/P-model | SW-H idempotency/cancel/restart/exact-diff activation/rollback after F/G. |
| [WS-03/07](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L579) | Larry / Codex · voice/accessibility (SW-I) | U | B2 | SW-I shared voice actions + real VoiceOver/keyboard/type/contrast; stale target. |
| [WS-03/08](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L580) | Larry / Codex · physical displays (SW-J) | H | B3 | SW-J physical two-screen creator/research recovery after creator prerequisites. |
| [WS-03/09](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L581) | Codex / Larry · remaining performance (SW-K) | S | B4 | SW-K exact Mac performance: remaining voice p95 and 10-minute growth; preserve accepted navigation. |
| [WS-03/10](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L582) | Codex / Larry · release and handoff (SW-L) | D | B0/B6 | SW-L exact source/config/package/readiness and rollback; prerequisites remain feature-specific. |
| [WS-06/01](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L610) | Larry / Claude · spoken status | U | B2 | Known spoken #1/#2/#4/#8 counterparts; do not invent missing numbered checklist. |
| [WS-06/02](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L611) | Larry / Claude · external status | B | P-model | Exact probe/catalog source/date and changed-only daily notices; provider access required. |
| [WS-06/03](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L612) | Larry / Claude · corrected retry | U | B2 | Alfreda→Alpharetta corrected retry, no lockout. |
| [WS-06/04](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L613) | Larry / Claude · process recovery | S | B4 | Three-minute disconnect/late result and controlled child recovery in safe test scope. |
| [WS-06/05](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L614) | Larry / Claude · graph and remaining source checks | U | B2/B5 | Unknown graph truthful fallback; sports provenance and one-day transport log. |
| [WS-06/06](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L615) | Larry / Claude · registry split | S | P-model | Registry/env/route parity plus admitted sandbox profile PR proof; no endpoint authority change. |
| [WS-06/07](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L616) | Claude / Larry · completeness | O | P-map/B5 | Owner supplies eleven-check repository map; separate week without unsolicited commands and tier decision. |
| [WS-07/01](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L642) | Claude / Larry · reply-guard evidence | B | Decision | Genuine reply-guard events/precision/false refusals; four events insufficient, startup lines excluded. |
| [WS-07/02](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L643) | Larry · guard-mode decision | B | Decision | Larry keeps log or approves correct after evidence; verify no fabricated actions or confirmation bypass. |
| [WS-07/03](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L644) | Larry / Claude · remaining workflow live/evaluation record | S | B4 | Remaining workflow enabled/disabled routing/voice and end-run outcomes; source evidence is not live acceptance. |
| [WS-07/04](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L645) | Larry · viewer journey | U | B2 | Viewer gallery/buttons/supporting-display, wrapped steps and dashed draft cards. |
| [WS-07/05](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L646) | Claude / Larry · closure | D | B6 | Link guard/viewer/live receipts to exact build; full UI2-22 and retry-location retain own authority. |
| [WS-09/01](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L675) | Larry / evidence recorder · preparation | D | B0 | One manifest/coverage map; no redundant freeze per row. |
| [WS-09/02](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L676) | Larry · console, accessibility and transcript cleanup | U | B2 | Console/accessible transcript-only surface, dependent 04/13 after 24/25. |
| [WS-09/03](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L677) | Larry / Codex · Atlas and graph | U | B2 | Atlas/graph provenance/search/partial/stale/auth/reconnect and exact UI2-05. |
| [WS-09/04](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L678) | Larry / Codex · display governance | H | B3 | Topology and stage budgets UI2-06/19/20; explicit unavailable hardware. |
| [WS-09/05](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L679) | Larry · outward sharing | U | B2 | Outward selected text/image copy/save/share/cancel; picker is not delivery. |
| [WS-09/06](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L680) | Larry / implementation owner · inbound analysis | U | B2 | Inbound preview/provider/bounds/cancel/cleanup; synthetic refusal cases offline first. |
| [WS-09/07](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L681) | Larry · complete voice parity | U | B2 | Complete enabled voice/pointer parity UI2-09 after 22–25. |
| [WS-09/08](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L682) | Implementation/evaluation owner · contracts and compatibility | A | B0/B4 | UI2-03/10/11 schema/owner/menu/compat/security/duplicate contracts and current eval denominator. |
| [WS-09/09](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L683) | Codex / Larry · combined load and glass | S | B4 | UI2-12 measured graph/panels/attachments during voice + audible observation. |
| [WS-09/10](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L684) | Verifier / Larry · release closure | D | B0/B5/B6 | UI2-14/15/16/17/18: exact verification, rollback/deploy, observation and closure distinct. |
| [WS-09/11](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L701) | Single transcript surface (Larry, 2026-09-28) | U | B2 | Single main transcript; supersedes duplicate compact captions, no new parallel test. |
| [WS-10/01](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L719) | Codex / Claude / Larry · preparation | B | P-model/P-memory | Eligible dedicated memory route/source/stage baseline before shadow; no live mutation. |
| [WS-10/02](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L720) | Larry, supported by the implementation owners · staged use | O | P-memory | Explicit approved shadow day then staged preferences/inferences; not elapsed-only automatic promotion. |
| [WS-10/03](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L721) | Larry · first 20 real decisions | U | P-memory | Larry reviews first 20 actual admissions/corrections under approved scope. |
| [WS-10/04](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L722) | Codex / Claude · benefit and budgets | S | P-memory | Measured benefit/denominators/latency/daily caps, not synthetic replacement for real use. |
| [WS-10/05](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L723) | Codex / Claude / Larry · privacy and voice | A | P-memory | Forget/delete/redaction/canaries, restart/duplicate/privacy/voice boundaries. |
| [WS-10/06](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L724) | Larry / implementation owners · rollback and receipt | B | P-memory | Rollback/settings/stage receipt and Larry acceptance after benefit/privacy proof. |
| [WS-11/01](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L753) | Larry / Codex · candidate and coverage | D | B0 | Same exact candidate/fingerprint/coverage map; reconcile old C8 routing header. |
| [WS-11/02](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L754) | Larry · remaining preservation workflows | U | B2 | Remaining P0 journeys and real task/result lineage; preserve accepted subparts. |
| [WS-11/03](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L755) | Larry / Codex · visual/accessibility matrix | H | B2/B3 | Viewport/accessibility and physical Retina/portrait/ultrawide conditions; known orb sign-off stays closed. |
| [WS-11/04](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L756) | Larry / Codex · remaining physical audio | H | B4 | Physical audio/echo/earbud/wake/sleep/mic matrix; reuse WS-18 switch only for matching case. |
| [WS-11/05](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L757) | Larry / Codex · monitor and rollback tails | H | B3 | Applicable monitor/layout/rollback tails; unsupported topology explicit. |
| [WS-11/06](https://github.com/Larryfix71566/jarvis-voice-ai/blob/28420af29191716945e55f6aeec1f0fd125ea931/ROADMAP.md#L758) | Verifier / Larry · closure | O | B5/B6 | Exact C5/C8 proof + separate native/redesign daily-driver attestations, shared observations only if criteria match. |

### 2026-10-18 — Larry-authorized acceptance execution claim (Codex)

Larry approved ownership registration, the two cleanup prerequisite repairs,
missing #216 cross-review and independent verification at 20:08:26 UTC.
WS-20 now names `codex/acceptance-clearance-20261018` for bounded evidence/checks;
WS-17 retains its exact-source review/verifier work on a separate branch;
new WS-28 owns the cleanup-race/fingerprint repair. The claim-only workflow
may merge after required checks, while runtime repair merge and production
replacement/restart/deployment remain separate. Main inspected: `b29c7aba`;
no open PR or competing claim. No runtime work or acceptance closure in this
registration. Existing §9 sequencing and all counts/owners/receipts retained.

## 10. Claude continuation and repository synchronization — 2026-10-22

This is a dated handoff in the existing WS-20 coordination plan. `ROADMAP.md` remains the ownership/state authority. Read current main's `AGENTS.md`, `CLAUDE.md`, roadmap §§0/2/4 and the exact owning PR before work. This publication authorizes documentation drafts only. A branch or green suite is not a merge, installation, model switch or acceptance receipt. No new runtime ownership is transferred to Claude by this handoff.

### Source inventory and owners

Snapshot checked October 22, 2026. Refresh heads and open/merged state before continuing. Links identify source; PR text contains the dated evidence and limitations.

| Scope / owner | PR, branch and exact head | State and next action |
|---|---|---|
| Main / provider correction | [#239 merged](https://github.com/Larryfix71566/jarvis-voice-ai/pull/239), main `636880eabbe9dc756c30df7128d0a90c02d222bd` | Direct OpenAI/Anthropic API exclusion corrected to preserve explicitly eligible other-provider APIs. Source only; not installation. |
| WS-17 release owner | [#243](https://github.com/Larryfix71566/jarvis-voice-ai/pull/243), `codex/ws17-native-visibility-20261022`, `946f655fb0b88fef73fa1377532b85628c6de2f7` | Ready/unmerged; offline verification, independent review and all five publication CI checks complete. Direct PR-specific merge approval, guarded physical-host installation checks and live acceptance remain separate. |
| WS-05 provider owner | [#244](https://github.com/Larryfix71566/jarvis-voice-ai/pull/244), `codex/ws05-subscription-retirement-20261020`, `014f915bd8f8ac9a5e187779601fe1718d7e21b5` | Draft, unmerged. Codex `0.163.0-alpha.11` offline compatibility only. 182 offline passes; Fable 5.1 found no blocking issue on runtime/test source `b4ce39a2bba0dbe6c13723e311fae0bb3d7362d1`. All three publication workflows are successful at this head (read October 22); activation/live acceptance remains blocked. |
| WS-05 harness owner / CX-28 | [Claim #241](https://github.com/Larryfix71566/jarvis-voice-ai/pull/241), `docs/claim-ws05-harness-20261022`, `985379f425dc717997fe502dadfd3aaee0b37662` | Documentation claim draft, unmerged; all five CI checks passed. Do not treat it as a landed runtime claim. |
| WS-05 harness owner / CX-28 | [Implementation #242](https://github.com/Larryfix71566/jarvis-voice-ai/pull/242), `codex/ws05-harness-recommendations-20261022`, `d476905057fc29207338721ce9ec2a452cb2085d` | Recommendation-only skill/passive daily brief. All five CI checks passed. Exact Claude Opus 5.5 review completed: source ACCEPT, six prior groups closed, zero blocking findings; human review required. The linked owner receipt records limits; selected-versus-active distinction remains. Switching and voice confirmation blocked. |
| WS-30 phone documentation owner | [#240](https://github.com/Larryfix71566/jarvis-voice-ai/pull/240), `codex/phone-access-plan-20261022`, `87f163a7619596104e27af0bf50a3b6b88d28809` | Draft provisional plan revision 4; only revision 2 received Fable review. Revisions 3/4 author amendments have not been independently re-reviewed. No implementation. |
| WS-31 REA documentation owner | [#245](https://github.com/Larryfix71566/jarvis-voice-ai/pull/245), `docs/rea-integration-publish-20261022`, `b23b824ff15e450fae60535b38a95559eeda9396` | Sanitized derivative of local `dd8e4f9a83d6e7e9a095a1657d001001f22e1586`. Depends on #240; preserves its three files, appends WS-31 after WS-30. New apps/authorized feature recreation; no Mortimer self-modification, REA execution or implementation. |
| WS-03 compatibility / WS-20 sync | This draft, `docs/continuation-handoff-20261022` | Existing WS-03 plan extended with full compatibility proposal; complete controller testing proposal and owner handoff published as immutable evidence. The containing Git commit/PR identifies exact publication bytes; no circular self-hash is embedded. Runtime owners and all acceptance checkboxes remain unchanged. |

The existing [historical verification draft #224](https://github.com/Larryfix71566/jarvis-voice-ai/pull/224) is older evidence on its own candidate; do not replace the release owner's newer #243 verification with it. Existing historical branches remain available; synchronization does not force-push, delete, merge or rewrite their owners' work.

### Installed state and service holds

Release-owner read-only check at October 22 15:05 UTC: remote main `636880e`, installed development checkout and app `b136a2a66032b17082776a01353abe67e352c31e`. All six services plus cleanup remain disabled/unloaded and direct-API shutdown policy remains in force. This synchronization did not inspect private logs or operate services. The earlier architecture report identified dirty debug bundle provenance; neither Git main, a plan header nor offline checks establish a newly installed or loaded build. Current loaded identity and release acceptance require the release owner's separate attestation. Never infer installation from #243 being ready.

### Complete local deliverables and repository counterparts

| Original deliverable | Repository destination / disposition |
|---|---|
| REA integration plan/research and original DOCX | [#245 plan](https://github.com/Larryfix71566/jarvis-voice-ai/blob/b23b824ff15e450fae60535b38a95559eeda9396/docs/plans/MORTIMER_REA_INTEGRATION_PLAN.md); complete research beside it under `docs/interface-research/`. Source `dd8e4f9` retained privately; private storage/task IDs removed from publication. DOCX bytes retained after blank-author/metadata scan. |
| Skill compatibility plan, proposed full canonical copy and unapplied patch | [Existing WS-03 plan addendum](MORTIMER_SKILLS_WORKSPACE_IMPLEMENTATION_PLAN.md#2026-10-22--skill-compatibility-proposal-mortimerskill-compatibilityv1); complete technical proposal consolidated once. Original patch/full-copy are packaging duplicates, not separate plans. |
| 22-category matrix / 25 proposed acceptance cases | [Gap matrix](../acceptance/skills-workspace/receipts/compatibility-planning-2026-10-22/gap-matrix.csv) / [proposed cases](../acceptance/skills-workspace/receipts/compatibility-planning-2026-10-22/proposed-acceptance-cases.csv). Complete CSV field values preserved; record line endings normalized to LF. No proposed case executed. |
| Architecture improvement review, skill-reuse report/proof and evidence manifest | [Sanitized findings/provenance](../acceptance/skills-workspace/receipts/compatibility-planning-2026-10-22/publication-summary.md), all 19 completed synthetic checks in the adjacent proof summary, source-only revision/path/digest manifest. Raw host paths and private metadata omitted. |
| Full controller testing plan version 2 | [Complete immutable proposal](../acceptance/model-use-enhancements/receipts/controller-testing-proposal-2026-10-22/testing-plan-v2.md), exact source SHA-256 `23fd4aed98c3e86a2d31ee4a4a0fa26568bd7de8c2a0fb7b330c8b8cce840343`. All technical sections and review appendices retained. Three document reviews; third verdict REVISE; final author clarifications not fourth-reviewed. PLAN ONLY; no benchmark allowance. |
| Harness current checkpoint and source-review handoff | [Sanitized owner handoff](../acceptance/model-use-enhancements/receipts/controller-testing-proposal-2026-10-22/harness-review-handoff.md) and adjacent machine-readable review state. Original rolling checkpoint and unapplied owner patch are superseded for continuity; no active harness branch edited by sync. |
| Harness integration contract/skill and implementation | Already in [#242 source](https://github.com/Larryfix71566/jarvis-voice-ai/tree/d476905057fc29207338721ce9ec2a452cb2085d/skills/harness-model-evaluation). Reuse `mortimer.harness-model-management.v1`; do not duplicate registry, importer, evaluator or approval path. |
| Provider compatibility source, review and offline receipt | Already in [#244](https://github.com/Larryfix71566/jarvis-voice-ai/pull/244), with source-linked sanitized continuation. The public summary is intentionally not an installed runtime receipt. |
| Current 31-workstream progress roster and snapshot | [Sanitized roster](../roadmap-log/2026-10-22-continuity-evidence/workstreams.csv), [denominators and limits](../roadmap-log/2026-10-22-continuity-evidence/progress-methodology.json). Duplicate long historical status prose omitted; current head/status is above. |
| PDF/ZIP presentations, rendering outputs, preparation helpers | Duplicate delivery/QA packaging; deliberately not re-published. Full canonical text, matrices, proposed cases and necessary provenance are accounted for above. |
| Raw implementation-review source packets, invocation/authentication transport output, private logs/transcripts, account identifiers and local operational receipts | Deliberately excluded. No credential, token, private chat, personal log or blanket external-agent permission belongs in repository handoff. Technical hashes/verdicts/limitations are sufficient for continuation. |

No scoped planning/source deliverable is intentionally left available only through a Library link. The actual private operational evidence and excluded duplicates stay local by design. The full testing proposal is now a repository attachment under the existing WS-05 canonical plan; the owning harness PR may link it in a later owner-only documentation update. No implementation plan is copied into a second canonical workstream. The WS-05 owner authorized the append-only canonical-plan link/status entry in this documentation draft.

### Completed checks versus future work

- This sync runs documentation/link/whitespace/privacy/source-preservation checks and remote readback, not application or live-provider tests. Its publication CI is independent of the source evidence below.
- #243: original twelve-check profile and six focused visibility cases passed on the documented programme identity. Metadata head `946f655` preserves programme bytes; do not claim the full profile was rerun on metadata. Five publication CI checks pass.
- #242: 6,912 unit passes/11 skips/two subtests, 197 integration passes/four skips, 13 offline evals; focused local evidence 257 backend, 18 native, seven matching/package cases and three protected-fixture checks. These are owner/CI source results, not reruns by sync or live acceptance. The 18 native tests were an author-local Swift run, not Linux CI; source/test/log hashes match the committed receipt. Exact tools-disabled Claude Opus 5.5 review completed 15:05:17–15:07:43 UTC, returned source ACCEPT with zero blockers and human review required. Earlier failures, denial history and repairs remain in its receipts.
- #244: 182 offline checks and immutable-source independent review, no new live inference; renewed exact-binary workload acceptance remains required.
- Skills: 19 prior isolated reuse checks passed, including evidence that unsupported host semantics are not enforced. That is not readiness of a full activation service. All 25 proposed new acceptance cases remain unexecuted.
- Phone/REA/testing proposal: planning documents. Phone rev2 review does not approve rev4 amendments; REA has no independent plan review. The controller plan's reviews do not authorize its proposed requests, microphone work, services or model changes.

### Progress methodology

The owner's 14:57 UTC snapshot includes WS-01–29 from main and pending phone/REA entries: **7/31 closed (about 23%)**, 15 partially delivered or awaiting acceptance, nine without implementation. This weights each workstream equally and includes documentation and deferred features; it is not coding completion or effort completion. The interface checklist has 19/53 checks (36%) in its October 18 reconciliation, with overlapping criteria. Skills has two of 12 full gates, despite a differently shaped displayed remaining checklist. Where no complete denominator exists, overall percentage is unknown. Do not sum remaining-only checkbox lists or invent partial credit.

### Bounded continuation order

1. **Codex / WS-20:** verify current PR heads, required reviews, remote content and ownership before handing over any slice. Reconcile a changed head against the exact evidence; preserve #240 → #245 dependency and separate #241 claim from #242 source. No repeated green checks or benchmark calls just to refresh a narrative.
2. **WS-17 release owner + Larry:** keep #243 source ready while direct PR-specific merge approval, installation authorization/physical-host checks and live acceptance are resolved in their own workflow. This sync grants none of them. Services and cleanup remain held.
3. **WS-05 harness owner / Claude:** the exact-source review is complete. Preserve accepted `d476905` and the separate human claim/merge/deployment decisions. A docs-only publication needs fresh publication CI, not another source review. Any runtime/native/skill change needs focused re-review. Never duplicate a running/uncertain request; reconcile status first. Earlier denied attempts never executed; exact payload/destination approval enabled the one completed call. Plan reviews and green CI alone never substitute for source review.
4. **Reviewer-proposed next Claude slice, after a bounded owner/branch/test-path dispatch:** create an offline test-only case using fake daily dependencies with the real `model_access_status(registry=...)` path. Assert no `harness.read_report` or `configured_selection` call, a stable `access_status.harness_brief` stub and quiet day-over-day diff. Preserve all health checks; no runtime/skill/provider/installer changes. This is proposed, not executed or dispatched. A lower-scope documentation alternative is an adversarial case matrix for the existing harness skill/passive brief: unknown baseline/account access, stale or malformed evidence, unsupported model family, generic daily-brief negatives, unavailable adapters, no hidden fallback, selected versus active, and late/cancelled results. Use synthetic contracts from exact #242, ≤one bounded review/draft request, no tool execution, runtime edits, network probe or external-agent grants. Return precise case/input/expected-outcome/source-location rows; do not execute them or claim acceptance. Record owner/branch/path scope first; current rows are not silently reassigned.
5. **WS-03 / Claude plan review only after bounded assignment:** inspect all 22 categories and 25 proposed cases for complete preservation of required semantics. Flag unsupported/unknown required behavior; scripts and services require reviewed adapters. Produce findings against the existing canonical addendum, no importer implementation or activation.
6. **Later parked development:** phone rev4 amendment review, REA app-building reference/rights/static pilot selection, Skills implementation and larger controller experiments await their own approved scopes and acceptance-first prerequisites. REA is for new apps/authorized recreation, not self-modification. No experiment runs merely because the testing plan is now in Git.

A normal continuation prompt for the bounded matrix task is: “Read the exact PR #242 source and its current owner handoff. After verifying your documented scope, draft a synthetic adversarial case matrix for the existing recommendation-only skill and passive brief. Give each case's input, expected refusal or recommendation, and source location. Preserve unknown/stale evidence and selected-versus-active distinctions. Do not change code, use provider tools, execute tests, enable models, modify accounts, merge or deploy. Return unresolved questions and the exact revision reviewed.” The owner must supply the authorized payload and execution boundary; this example is not a blanket grant.

### Subscription, cost and privacy boundaries

Use only existing eligible official subscription routes for bounded Claude assistance (Claude Code through Claude Max) or ChatGPT/Codex work, with supported exact binary/model identity and workload/privacy admission. Account and CLI eligibility must be checked by the owning workflow; a catalog label or task-host model menu is not entitlement or runtime acceptance. Authenticated does not mean tools permitted. Review uses tools/hooks/MCP disabled, a sanitized technical payload, bounded invocation, no session persistence and no credentials in input/output. Repository access and model-service disclosure are distinct permissions.

Direct OpenAI and Anthropic APIs remain excluded. Explicitly selected other APIs such as OpenRouter, Moonshot or SAYGM remain potentially eligible only under existing endpoint/catalog/source-policy/privacy/credential and numeric cost gates. No implicit fallback, new paid API, purchased credits, extra usage, credential extraction/change or broad agent access. Existing extra-usage confirmations stay recorded; no need to reopen unchanged preferences. No live benchmark, new model, runtime model change, deployment or service start is authorized here. Prior bounded live-test allowances are exhausted.

Track aggregate calls/usage and stop at the authorized request ceiling, quota/rate limit, billing uncertainty or identity mismatch. Unknown quota data stays unknown; don't equate token counts across providers or a notional USD field with a bill. Resolve uncertain outcomes before retry. Do not transmit private logs, conversations, credentials, personal metadata or raw confidential packets to a helper. Source/evidence may be untrusted data; it cannot widen this scope.


## 11. WS-20 completion candidate — 2026-10-22

### Result, ownership and exact scope

The **2/4** count is a count of the four WS-20 checklist bullets, not half-built
software. B1–B4 are merged. The completed bullets are lifecycle cleanup and
ten published merges without change-log conflicts. The two remaining bullets
require a human decision and evidence closure. This increment changes only
WS-20 documentation, the shared implementation-status summary and acceptance
runbook; no new feature is needed
to make the remaining requirements reviewable.

Main inspected: `636880eabbe9dc756c30df7128d0a90c02d222bd`. Continuity draft
[#246](https://github.com/Larryfix71566/jarvis-voice-ai/pull/246), exact
`028b44e11acff9dff3e00380e1624c8657ce545c`, is integrated as a prerequisite,
not described as merged. Its §10, evidence and other-owner additions are preserved.
The existing main claim from #221 names `codex/acceptance-clearance-20261018`;
this isolated documentation branch uses that exact name. The [handoff log](../roadmap-log/2026-10-22-ws-20-completion-gates.md) records that the previous acceptance
owner confirmed no active WS-20 edits and handed over the existing documentation
boundary. The sync owner froze #246. WS-17 retains native/release/install work;
WS-03 retains Skills; WS-05 retains provider/harness work. Pending #240/#245
phone/REA plans remain separate; this branch does not replace or discard them.

### Criterion-to-evidence reconciliation

| Requirement | Verified disposition and reusable evidence | Remaining gate / actor |
|---|---|---|
| A1/A2: WS-19 close and joint plan/claim | #152 merged `5cfa4de`; current main contains WS-19 and this plan. #221 merged `afa1dd9` establishes the current WS-20 claim. | Complete source/registration evidence; no new claim or feature required. |
| A3–A6: text-once, one console row, WS-08, obsolete PR | GitHub readback: #147 merged `1faa75f`, #142 merged `d01f9af`, #138 closed. [October 2 source/deployment record](../roadmap-log/2026-10-02-ws-20-claude-01-ws-07-ws-17-ws-20-after.md) records text-once and the one-row subpart. | Historical catch-up source disposition complete; these are not full current UI2-22/24 acceptance. |
| A7: production equals the selected main | The same October 2 record names `ae70f2c`, clean deployment receipt, services and bundle. It proves that historical deployment event. Current source, installed development build and historical Production header are different identities. | WS-17 release owner supplies a new canonical deployment/loaded-identity receipt for the selected current candidate. Do not update Production from a checkout SHA or imply every later docs commit needs app installation. |
| A8: AirPods switch, answer once, one console row | October 2 record proves answer-once/one-row subparts; [October 17 campaign](../acceptance/command-console/receipts/acceptance-campaign-2026-10-17.md) records Larry's WS-18 acceptance on `575cc7b`. [October 6 bounded voice evidence](../roadmap-log/2026-10-06-ws-20-codex-voice-acceptance-review.md) retains its precise coverage. | Preserve those accepted scopes. UI2-22/24/25 and changed current-request scenarios require their own applicable candidate evidence; do not rerun accepted WS-18 solely to complete paperwork. |
| B1: 72-entry move | #160 merged `30fa3db`; [migration receipt](../roadmap-log/2026-10-02-ws-20-codex-b1-log-migration.md) preserves one-to-one original entries. | Complete; do not repeat migration. |
| B2/B3: production event wording and after-merge protocol | #158 merged `04eb3f0`; [lifecycle closeout](../roadmap-log/2026-10-06-ws-20-codex-lifecycle-closeout.md) and #191 (`b6f09f4`) preserve the corrected rows. | Complete implementation; retain single historical Production receipt and distinct installed identity. |
| B4: checker implementation | #156 merged `ae70f2c`; `.github/workflows/validate.yml` still runs `python scripts/check_roadmap.py --warn-only`. The strict local invocation passes on the documentation delta from `028b44e` (exact file hashes and validation in the [completion log](../roadmap-log/2026-10-22-ws-20-completion-gates.md)); a green warn-only CI job alone does not prove zero findings. | Larry chooses the policy below; implementation owner remains Claude for any separately dispatched CI change. No enforcement change in this PR. |
| B exit: ten merges, no change-log conflict | [Published-history receipt](../roadmap-log/2026-10-06-ws-20-codex-ten-pr-change-log-observation.md) binds #161/#162/#163/#165/#166/#167/#168/#164/#169/#170 to exact parents/trees, with an unrelated row-conflict positive control. | Complete for its published window; no claim about unpublished manual history. Reuse the receipt. |
| C1–C5 | Present in ROADMAP §0 at inspected main. | Complete standing protocol; continued compliance is operational, not another feature build. |
| Final Phase A/B exit and owner-linked evidence | The source/history portion is reconciled here; remaining owner gates are linked below. No single current release receipt covers every live requirement. | Keep the final evidence bullet unchecked until applicable outcomes, source/build/config identity and permitted dispositions are recorded by their existing owners. Publishing this table alone is not acceptance. |

### Practical gate checklist

| Gate | State now | Exact next action and completion evidence |
|---|---|---|
| WS-20 code | **Complete** for B1–B4; no runtime change in this slice. | Reuse original merge/migration/ten-merge receipts. |
| WS-20 documentation/evidence preparation | **Prepared for review** by this candidate. | Confirm source links, unchanged other-owner rows/checkboxes, strict checker and independent review. Publication CI is separate. |
| Checker decision | **Pending Larry**; warning-only remains effective. | Record explicit choice, date and scope. If retain warning-only, verify existing invocation and record the decision without changing CI. If blocking is chosen, dispatch the CI change to its owner, review it, and verify a malformed fixture fails while clean roadmap passes. `--github`/receipt checks and GitHub branch-protection settings are separate choices, not automatically enabled. |
| Source prerequisites for current release | **Verified only at their recorded sources.** | [Native compatibility receipt](../acceptance/command-console/receipts/ws17-native291-source-verification-2026-10-21.md) records reviewed cleanup and 12 checks at `e9c30b0`. [#243 frozen receipt](https://github.com/Larryfix71566/jarvis-voice-ai/blob/946f655fb0b88fef73fa1377532b85628c6de2f7/docs/acceptance/command-console/receipts/ws17-native-deferred-hide-2026-10-22.md) records final programme `a672239`, six focused cases without skips and 12 checks. GitHub readback: #243 head `946f655`, open/unmerged, all five CI checks pass. Earlier failed runs remain evidence; no broad suite rerun for these docs. |
| Old #210 cleanup finding disposition | **Repair and final review complete at exact source; index corrected.** | #222 merged `1632afb726ae2fb4df25c6349647f2e731a29766` as `406bec0660a292447c58ba9bf786307581808854`. Its PR body contains the final review; [preserved report and digest](../roadmap-log/2026-10-22-ws-20-cleanup-review-evidence.md) confirm the original finding resolved and no new blockers. SHA-256 `fcddaff9a1247c13775b16210cd9311739c97b6f9d3137f6f373f83a7a6348d2` matches the release owner's retained report. The [160-test regression receipt](../../sandbox/acceptance/2026-10-18-cleanup-regressions.json) retains historical pending prose. Static review did not execute tests; corrupt ownership metadata can still prevent development/legacy headroom recovery. This closes the missing index link, not physical acceptance or authority to run cleanup. |
| Old #216 cross-review disposition | **Review present; residual scope retained.** | #223 merged `d38c886` publishes [original exact-source review](../acceptance/command-console/receipts/ws17-cross-review-2026-10-18.md) and [Finding 1 reconciliation](../acceptance/command-console/receipts/ws17-cross-review-reconciliation-2026-10-18.md) at `61f701d683d76b3633afc1b060e4a19f20d9339d`. The missing-review obligation is superseded by these receipts; Finding 1 was invalidated with caller evidence. The secondary timezone-consistency coverage gap remains unresolved in that review, not a confirmed defect or a new live pass. WS-17 retains any later-source applicability/disposition; this packet does not waive it. |
| Physical host and installation | **Pending release owner/Larry.** | Exact #243 merge authorization remains separate; then existing release workflow proves target source, actual host prerequisites, installation and loaded identity. Prior release-owner snapshot reports development build `b136a2a` and services/cleanup held; this document does not probe or alter them. |
| Live / hardware / observation | **Open under each existing owner.** | Use identified candidate and the sequence below; record failures/skips/unavailable hardware honestly. Preserve previously accepted scopes and permitted limitations only where the governing criterion allows. |
| Final WS-20 evidence milestone | **Pending.** | Publish final Phase A/B exit disposition with the applicable owner receipts and remaining feature-specific blockers. Do not require parked/unbuilt unrelated features as invented global release gates; do not tick the broad milestone while required live criteria remain unsupported. |
| Release | **Not authorized by this candidate.** | Owner's separate merge/install/release decisions and receipts; source checks and this draft do not substitute. |

### Owner-linked live evidence and shortest next session

The existing [§9 full obligation inventory](#9-acceptance-clearance--current-priority-2026-10-18)
and canonical [release criteria](../acceptance/adaptive-interface/RELEASE_READINESS.md)
remain the denominator. Their October 18 totals are historical, not recomputed
current engineering percentages. The following links route work without
copying, narrowing or reassigning its criteria:

- [WS-17](../../ROADMAP.md#ws-17), Codex + Larry: after the release owner establishes
  one eligible installed candidate, run UI2-24/25 fail-fast, then 22/23 and
  dependent 04/09/13. The runbook now reflects the approved still-active explicit
  request exception; background, stale, superseded, cancelled and unrelated arrivals
  preserve focus. Stop on the first blocking failure.
- [WS-01](../../ROADMAP.md#ws-01), [WS-09](../../ROADMAP.md#ws-09),
  [WS-11](../../ROADMAP.md#ws-11) and [WS-21](../../ROADMAP.md#ws-21): reuse matching
  console/display evidence under their existing owners. Real display topology,
  recovery, identity/fetch counts and human observation remain required where named.
- [WS-18](../../ROADMAP.md#ws-18) is already accepted for its named output-switch
  scope. [WS-06](../../ROADMAP.md#ws-06) and UI2-17 keep their distinct week/five-day
  observation criteria; elapsed time alone is not evidence.
- [WS-02](../../ROADMAP.md#ws-02), [WS-03](../../ROADMAP.md#ws-03),
  [WS-04](../../ROADMAP.md#ws-04), [WS-05](../../ROADMAP.md#ws-05),
  [WS-07](../../ROADMAP.md#ws-07), [WS-10](../../ROADMAP.md#ws-10) and
  [WS-13](../../ROADMAP.md#ws-13): each owner prepares only its ready scenarios.
  Source/access/auth/model/guard-mode/memory/mail dependencies and decisions stay
  feature-specific. Do not schedule unbuilt creator/onboarding/mail stages as
  immediate human test chores or reactivate held services for this paperwork.

Each new outcome must include criterion/subpart, actor/date, source and installed
artifact identities (plus relevant backend/configuration), scenario and expected
result, actual result, receipt reference, coverage limits and owner disposition.
A reused receipt additionally needs source/scenario applicability. A failed or
missing case stays open; a named limitation requires the governing plan's route
and Larry's recorded decision. No raw transcripts, private logs or credentials
belong in the repository.

### Prepared decision prompts (not answers or approvals)

1. **Checker:** “Keep roadmap drift checks advisory, or make structural drift
   fail CI? The checker exists; the dated clean result is in the completion log. CI remains advisory until
   your choice is recorded. Blocking enforcement needs a separately reviewed
   owner change.” Either answer is a policy decision; silence is not one.
2. **Release handoff:** “PR #243 is verified at `946f655` but remains unmerged.
   The existing release owner needs the specific merge decision and physical
   host readiness before the identified-candidate acceptance session.” This
   records the existing release blocker and does not retry it or request new
   installation/cost approval already held by that owner.

The two unchecked WS-20 milestones remain unchecked. Documentation readiness,
user decision, physical acceptance and release are separate outcomes.
