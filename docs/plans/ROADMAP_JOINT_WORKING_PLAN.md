# Roadmap joint working: catch-up and drift prevention (WS-20)

**Status:** IN PROGRESS, reconciled 2026-10-06. B2/B3 merged in #158, B4 merged in #156, and B1's 72-entry log migration merged in #160 (`30fa3db`). The ten-PR no-conflict observation and warn-only checker rollout remain open.
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
