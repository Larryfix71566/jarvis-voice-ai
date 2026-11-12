# Mortimer master roadmap

**Production:** `b136a2a66032b17082776a01353abe67e352c31e`, deployed 2026-10-19 10:41 EDT (receipt `~/MortimerRollback/logs/deployment-receipt-b136a2a.json`).

This file is the single record of **who is doing what** in this repository, for every system that writes code here. Plans (`docs/plans/`) hold design. Receipts (`docs/acceptance/`) hold evidence. **This file holds ownership and state.**

**Last full reconciliation:** 2026-10-02, read-only review of every §2 block against `origin/main` `a39136a` (before the WS-19 claim), tracked code/configuration, plan and acceptance headers, open PRs, CI, and the 09-30 DEPLOY-MAIN log. That earlier deployment of `39fc6f9` passed Python 4,938 / 7 skipped, MortimerHost 416 / 6 skipped / 0 failures, JarvisKit 219 / 0; phase D reported admin/vault 200, bot 307, and matching source/bundle revision. PRs #143–#149 merged after that earlier deployment; the 10-02 release in the Production line above subsequently included their code. This review created no new live acceptance. Original evaluation: [cross-system evaluation](docs/reviews/CROSS_SYSTEM_PLAN_EVAL_2026-09-27.md).

---

## Archived history

Sections moved verbatim on 2026-11-10 to the [roadmap history archive](docs/roadmap-log/archive/2026-11-10-roadmap-history.md): New aggregate draft — 2026-10-27 UTC; Current source reconciliation — 2026-10-27 UTC; Historical acceptance source status — 2026-10-21; Acceptance clearance — priority inventory · 2026-10-18; Historical acceptance reconciliation — 2026-10-18; Consolidated enhancement intake — Larry, 2026-10-17; Operational summary — 2026-10-07.

## 0. Protocol (binding for every system)

Systems: **`claude`** (Cowork or Claude Code), **`codex`**, **`kimi`** (Kimi Work on the Mac), **`larry`** (steps only a human can do).

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
13. **Everything in progress has a block, including work that isn't code** (reviews, option write-ups, plan edits, guided Mac checks). Add it as `proposed` before starting and mark it `claimed` when you start. If the work produces no PR of its own, update the block through a docs-only PR at the end of the session. All systems re-read §2 at the start of every session, because another system may have changed it.
14. **Assignments prevent overlap; they are not exclusive.** Larry, 2026-11-10 14:15:49 UTC, in his Claude Duet channel: "Ok the assignments are to keep models from overlapping work with other models. They are not meant to be exclusive or prohibit another model from picking up work another model is not currently engaged with". Any system not currently engaged may pick up work another system is not engaged with, by updating the row's Owner and Where first. No system reviews its own work: the reviewer of a PR is never its author.
15. **Code-only freeze for acceptance.** Larry approved this on 2026-11-10 at 14:16:18 UTC ("Approve all four", answering whether to approve a code-only freeze with docs merges still open, moving old history out of ROADMAP.md, letting Kimi take the reviews Codex owes, and a small CI fix). Larry starts the freeze by recording a freeze SHA in WS-17. From then until Mac acceptance closes, no PR merges that changes any file outside `docs/` and `ROADMAP.md` unless Larry approves that PR by name as an acceptance fix. Docs-only PRs keep merging. Validation and review bind the tree outside `docs/` and `ROADMAP.md` at the freeze SHA, so docs merges do not invalidate them. Until Larry records the SHA, no freeze is in effect.

**Joint-working rules (WS-20 Phase C):**

- **C1 — Session start:** All systems fetch main, read this file on `origin/main`, and run `python3 scripts/check_roadmap.py` once the WS-20 B4 checker lands. Fix findings in your own rows first; report other owners' findings in a change-log entry without editing their rows.
- **C2 — Row ownership:** Each system edits its own workstream blocks. The actor recording evidence may update Larry-owned acceptance blocks (WS-09, WS-10, WS-11). Shared §3–§5 may be edited by any system with a logged explanation. The one-time B2 mechanical sweep of current-production wording is assigned to Codex; other owners review only that wording.
- **C3 — Cross-review:** A PR that changes the other system's code waits for that system's review, as CX-13 and CX-15 already require case by case. A docs-only PR limited to the author's own row may merge on green checks.
- **C4 — PR age:** An open PR older than two days names its next step and actor in its row or is closed. Its owner resolves conflicts.
- **C5 — Handoffs:** `Next step` names `claude:`, `codex:`, `kimi:`, or `larry:`. Handoffs travel through main and PRs under rule 9; Claude still does not run git on the Mac.

Claude has one extra rule: it never runs `git` against the Mac repo (see `CLAUDE.md`). Larry commits.

**Status values:** `proposed` → `claimed` → `in-progress` → `review` (PR open) → `landed` (on main) → `accepted` (Mac/live acceptance done). Also `blocked` and `parked`.

**Dispatching work (Larry):**
1. Add or edit the row on main.
2. Tell the system: *"Take WS-xx per ROADMAP.md."*
3. The system confirms that the row, branch and scope match, merges main, and starts.

---


### Shared update format (all systems)

This Markdown file is the editable source for the expandable roadmap. GitHub
renders the `<details>` sections; all systems can read and edit the same plain
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
   it. `codex`, `claude` and `kimi` are systems; record an exact model only when the run
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
| `kimi` | Isolated worktrees under `~/Documents/kimi/workspace/kimi-work/`; the active branch for each task is named in its §2 block. | Kimi pushes scoped branches and opens PRs; Larry reviews and merges | `AGENTS.md` |
| `larry` | The Mac, production, the vault, GitHub | Merges PRs; deploys with `scripts/deploy_main.sh` | — |

---


Historical snapshot of who was working on what (2026-10-28 handoffs): moved to the [roadmap history archive](docs/roadmap-log/archive/2026-11-10-roadmap-history.md#from-roadmapmd-1-who-is-working-on-what--historical-snapshot-with-2026-10-28-handoffs-lines-433490-at-837bb04) on 2026-11-10.


## 2. Workstreams

- Scope locks only while status is `claimed`, `in-progress` or `review`.
- "(proposed)" next to an owner means Larry has not yet confirmed who owns the row.
- Expand a workstream for its editable fields. These blocks replace the former rows; the protocol’s references to a “row” mean the corresponding workstream block.
- Ordered by what still needs work (Larry, 09-29). When a block's status changes, move it to the matching group. Ids are stable, so links keep working.

**Reading the acceptance lists:** Each unfinished block lists its remaining decisions, prerequisite work and checks, with the responsible actor and pass condition. Check a box only when a dated receipt names the tested revision/configuration and result; record Larry's sign-off where the plan requires it. Valid shared receipts may satisfy more than one row. Completed workstreams stay below and are not reopened.

**Documentation authorization, 2026-10-06:** Larry asked Codex to add a list for every item needing acceptance. This bounded WS-20 documentation update adds plan-derived checklists across the open blocks on `codex/ws05-execution-20261005` (#184); implementation owners, existing status fields and acceptance decisions remain unchanged.

### Needs work: not yet built (proposed, claimed, in progress, in review, blocked)

<details id="ws-34">
<summary>WS-34 — Release closure lane: Python, contracts, CI triggers, removals · Claude</summary>

**Workstream:** Larry approved the three lane rows in his Claude Duet channel on 2026-11-11 at 02:35:41 UTC: "Take your picks", answering decisions 2 to 7 of `docs/plans/MORTIMER_RELEASE_CLOSURE_PLAN.md` §7 (decision 6: approve the WS-34 to WS-36 rows). His earlier direction for the split, 01:58:16 UTC: "first let's seperate this plan so that kimi and codex can help with development, the division should not be absolute but a guide to keep the models from stepping on each other, then we should freeze main and begin". Under §0 rule 14 a lane is a guide, not a lock: any system not engaged may pick up an item another system is not engaged with, by updating this block's Owner and Where first.

- **Owner:** `claude`
- **Status:** proposed; approved by Larry, starts when `next` exists (WS-34 item A2, after the freeze SHA is recorded in WS-17). Mark `claimed` when the first item starts.
- **Implemented by:** Claude
- **Remaining work / acceptance:** Items A1 (add `next` to the CI triggers), A2 (cut `next`), C0 (contracts), C0b (tokens for the approved palette), C3 (Python composer), C7-py (typed request and approve/decline handlers), C7b (composer, ⌘K, typed-request send path, after B1), C1b (delete `web/` and the old macOS packages), B2, B3 (patch only), B4, B6 and C8 (rewritten UI boxes into this file). Each item in the plan's §4 table for this lane, as a PR into `next` with its tests, reviewed by the item's named reviewer (never its author). Interface items then pass the rewritten UI boxes in `docs/acceptance/mac-acceptance-2026-11-11.md` §4 on the final build; `next` merges into `main` at closure.
- **Model version:** not recorded
- **Where:** not started; items branch from `next` (F1 and other acceptance fixes branch from `main`)
- **Plan:** `docs/plans/MORTIMER_RELEASE_CLOSURE_PLAN.md` §4 (WS-34) and §5; add only dated progress for this lane
- **Scope:** The files named for those items in the plan's §4 WS-34 table: `.github/workflows/{validate,sandbox,knowledge-base}.yml` trigger lines (A1); `docs/contracts/**`; `jarvis/bot/display.py`, new `jarvis/bot/compose*.py` and `jarvis/bot/typed_request.py`, the named display emit sites and registration lines in `jarvis/bot/pipeline.py`; `jarvis/admin/**`, `jarvis/costs_api.py`; `scripts/backup_db.py`; `web/**`, `macos/MortimerShell/**`, `macos/GlassSpike/**`, `macos/VPIOBench/**` and their listed fallout; C7b's Swift files. `sandbox/**`, `jarvis/selfedit/service.py` and `config/self_edit_allowlist.json` are supplied as patches for Larry to commit. Hand-off order for shared files is the plan's §4 "Hand-off points"; overlaps with other rows are CX-29.
- **Next step:** claude: A1 PR (`claude/ws34-a1-next-ci-triggers`) into `next`, which was cut from the freeze SHA `5777e98` (A2), then C0.
- **Updated:** 11-11

</details>

<details id="ws-35">
<summary>WS-35 — Release closure lane: CI, layouts, results, phone · Codex</summary>

**Workstream:** Larry approved the three lane rows in his Claude Duet channel on 2026-11-11 at 02:35:41 UTC: "Take your picks", answering decisions 2 to 7 of `docs/plans/MORTIMER_RELEASE_CLOSURE_PLAN.md` §7 (decision 6: approve the WS-34 to WS-36 rows). His earlier direction for the split, 01:58:16 UTC: "first let's seperate this plan so that kimi and codex can help with development, the division should not be absolute but a guide to keep the models from stepping on each other, then we should freeze main and begin". Under §0 rule 14 a lane is a guide, not a lock: any system not engaged may pick up an item another system is not engaged with, by updating this block's Owner and Where first.

- **Owner:** `codex`
- **Status:** in-progress; C10 baseline instructions delivered by #335; measurements not run. Review handoff recorded 2026-11-12; no merge or acceptance approval implied.
- **Implemented by:** Codex
- **Remaining work / acceptance:** Items C10 (box 810 performance baseline, before C1a), C1a (delete layouts 0 and 1), B1 (macOS Swift CI job), B5 (wider ruff, offline NLTK data), C4 (Swift block renderer), C5 (result carousel; the second screen keeps its grid, decision 4), C9 (phone orb on synthetic levels, decision 5, after moving the orb renderer to a shared package) and F1 (the `PhoneRemoteAuthorityProcessTests` failure, an acceptance fix on `main` approved by name). Each item in the plan's §4 table for this lane, as a PR into `next` with its tests, reviewed by the item's named reviewer (never its author). Interface items then pass the rewritten UI boxes in `docs/acceptance/mac-acceptance-2026-11-11.md` §4 on the final build; `next` merges into `main` at closure.
- **Model version:** not recorded
- **Where:** `codex/ws35-c10-baseline-20261111` (#335) into `next` (C10 instructions); `codex/ws35-contract-review-20261111` (#334, contract review). Code items branch from `next`, except F1 from `main`.
- **Plan:** `docs/plans/MORTIMER_RELEASE_CLOSURE_PLAN.md` §4 (WS-35) and §5; add only dated progress for this lane
- **Scope:** The files named for those items in the plan's §4 WS-35 table: `docs/acceptance/**` (C10); every MortimerHost source and test file that reads `layoutVersion` (C1a); `.github/workflows/validate.yml` (B1, B5, after A1); `macos/MortimerHost/Sources/MortimerHost/Display/**`, `App/AppMessageRouter.swift`, `macos/JarvisKit/Sources/JarvisKit/AppMessage.swift` (C4); the C5 result and carousel files; `ios/MortimerPhoneCore/**` and the shared orb package (C9). Hand-off order for shared files is the plan's §4 "Hand-off points"; overlaps with other rows are CX-29.
- **Next step:** kimi: review #335. Kimi reviews the instructions; Larry captures the freeze baseline before #337 merges. Other lane items retain their existing dependencies.
- **Updated:** 11-12


</details>

<details id="ws-36">
<summary>WS-36 — Release closure lane: Review, design tokens, orb, thread · Kimi</summary>

**Workstream:** Larry approved the three lane rows in his Claude Duet channel on 2026-11-11 at 02:35:41 UTC: "Take your picks", answering decisions 2 to 7 of `docs/plans/MORTIMER_RELEASE_CLOSURE_PLAN.md` §7 (decision 6: approve the WS-34 to WS-36 rows). His earlier direction for the split, 01:58:16 UTC: "first let's seperate this plan so that kimi and codex can help with development, the division should not be absolute but a guide to keep the models from stepping on each other, then we should freeze main and begin". Under §0 rule 14 a lane is a guide, not a lock: any system not engaged may pick up an item another system is not engaged with, by updating this block's Owner and Where first.

- **Owner:** `kimi`
- **Status:** proposed; approved by Larry, starts when `next` exists (WS-34 item A2, after the freeze SHA is recorded in WS-17). Mark `claimed` when the first item starts.
- **Implemented by:** Kimi
- **Remaining work / acceptance:** Items A3 (the WS-17 combined-source review, already claimed there), C2 (add the approved palette's tokens with `amber` unchanged; contrast on glass), C6 (glass energy orb on the Mac, replacing `OrbFieldView`'s compact satellites) and C7a (thread activity row and inline approve/decline). Each item in the plan's §4 table for this lane, as a PR into `next` with its tests, reviewed by the item's named reviewer (never its author). Interface items then pass the rewritten UI boxes in `docs/acceptance/mac-acceptance-2026-11-11.md` §4 on the final build; `next` merges into `main` at closure.
- **Model version:** not recorded
- **Where:** not started; items branch from `next` (F1 and other acceptance fixes branch from `main`)
- **Plan:** `docs/plans/MORTIMER_RELEASE_CLOSURE_PLAN.md` §4 (WS-36) and §5; add only dated progress for this lane
- **Scope:** The files named for those items in the plan's §4 WS-36 table: `App/AppTheme.swift`, `App/Glass.swift`, `App/AppTuning.swift`, `Console/TopBarView.swift`, `Console/ConsoleActionBar.swift` (C2); the orb files and the orb slots in `Console/AdaptiveStageView.swift`, `OrbFieldView.swift` removal (C6); `Console/ConversationThreadView.swift`, `MicControlsView.swift`, `CommandConsoleView.swift`, `App/ConsoleActionCoordinator.swift`, `Stores/ConversationStore.swift` (C7a). Paths are under `macos/MortimerHost/Sources/MortimerHost/`. A3 writes docs only. Hand-off order for shared files is the plan's §4 "Hand-off points"; overlaps with other rows are CX-29.
- **Next step:** kimi: A3 once the freeze SHA is recorded in WS-17; C2 after WS-34's C0b.
- **Updated:** 11-11

</details>

<details id="ws-33">
<summary>WS-33 — Acceptance unblock: code freeze, roadmap archive, CI gates · Claude</summary>

**Workstream:** Larry approved on 2026-11-10 in his Claude Duet channel: at 14:15:49 UTC "Ok the assignments are to keep models from overlapping work with other models. They are not meant to be exclusive or prohibit another model from picking up work another model is not currently engaged with"; at 14:16:18 UTC "Approve all four" (a code-only freeze with docs merges still open, moving old history out of ROADMAP.md, letting Kimi take the reviews Codex owes, and a small CI fix); at 14:16:37 UTC "Kimi" (owner of the combined-source review that lifts the WS-17 hold). This row carries out those picks from Claude's 2026-11-10 deep review.

- **Owner:** `claude`
- **Status:** landed via this PR (documentation: rules 14–15, Kimi's WS-17 review claim, roadmap archive); the CI part lands via #317
- **Implemented by:** Claude
- **Remaining work / acceptance:** Larry merges this PR and #317, then records the freeze SHA in WS-17 under §0 rule 15. Until the SHA is recorded no freeze is in effect. The Kimi combined-source review (WS-17) starts only after that. No deployment, restart or live acceptance is included.
- **Model version:** not recorded
- **Where:** this branch (`claude/ws33-roadmap-freeze-archive-20261110`) and `claude/ws33-ci-lock-push-20261110` (#317); [log](docs/roadmap-log/2026-11-10-ws-33-acceptance-unblock.md); [history archive](docs/roadmap-log/archive/2026-11-10-roadmap-history.md).
- **Plan:** Claude's 2026-11-10 deep review (Claude Doc in Larry's account), Improvement options 1, 2 and 4; no repo plan file
- **Scope:** The sections moved out of `ROADMAP.md` (the aggregate drafts, source reconciliations and intake summaries before §0, the §1 historical snapshot, four Status-line history tails and the resolved §4 rows), §0 rules 14–15, `AGENTS.md`, the WS-17 lines named in the claim above, this block, the archive and log files. CI part: `.github/workflows/validate.yml`, new `.github/workflows/dependency-drift.yml`.
- **Next step:** none for this row: the freeze SHA `5777e98` is recorded in WS-17 (11-11); the lanes continue under the release closure plan. kimi: WS-17 combined-source review.
- **Updated:** 11-11

</details>

<details id="ws-32">
<summary>WS-32 — Roadmap reader growth repair · Kimi (landed) + Claude (host-verifier follow-up)</summary>

**Workstream:** Larry approved Kimi claim registration on 2026-10-23 after exact main `c2e3c74a2f08dbe925303d19e6822383d53ddd73` reproduced two roadmap-reader failures: the canonical 259,344-byte roadmap exceeds the generic 256,000-byte file limit. Restore complete bounded roadmap reads without trimming source or weakening other guards.

- **Owner:** `kimi` (original reader repair #275, attribution and history retained); `claude` (host-verifier follow-up only, B1 of Claude's 2026-11-03 independent review, moved to Claude by Larry's explicit authorization in his Claude Duet channel on 2026-11-03 at 18:35:36 UTC ("I authorize you to take the work and complete it"), answering whether Claude should take over the remaining fix, and 18:36:03 UTC ("Update the roadmap to reflect that change")); `claude` also for the 2026-11-10 read-cap follow-up below, after Larry said in his Claude Duet channel at 14:51:35 UTC "The limit is causing more issues that it needs too" and at 15:24:22 UTC "Proceed"
- **Status:** landed via [#322](https://github.com/Larryfix71566/jarvis-voice-ai/pull/322) at merge commit `b83f0fc55c41edb6fab0a288b927d9e1b2678074` for the read-cap follow-up (Claude, `claude/ws32-roadmap-read-cap-20261110`; source only, not deployed or live-accepted; merged 2026-11-11 after Codex's review of head `fbce1e1` merged against main `a87256a`, APPROVE with no blocker, should-fix or nit findings, including 239 native JarvisKit tests passing on a Mac, recorded via [#324](https://github.com/Larryfix71566/jarvis-voice-ai/pull/324) at merge commit `b9024ed2bc641930314421c55f1237ae83d11578`; see the [Codex review log](docs/roadmap-log/2026-11-10-ws-32-codex-pr322-review.md)): `ROADMAP_READ_MAX_BYTES` is 1 MiB, and a roadmap read carries the text once, with a compact source snapshot; the display event and console refresh rebuild the cards from the verified text (Larry, 15:41:01 UTC: "Yes, fix it too"). Measured on `c5e1550`: agent reads now reach about 902 KB of workstream-card growth (was about 359 KB), the console about 559 KB, where the unchanged 1 MiB snapshot bound applies; see the [read-cap log](docs/roadmap-log/2026-11-10-ws-32-claude-roadmap-read-cap.md). Codex measured the console refresh limit lower for non-ASCII growth: about 420 KB when the growth is emoji inside a card field, because the pipeline's 1200 KiB escaped payload bound applies; every limit refuses the whole read rather than truncating. Earlier: landed via [#296](https://github.com/Larryfix71566/jarvis-voice-ai/pull/296) at merge commit `e54795eb1d985e29638df08bcb9a4f56661480ea` (B1 host-verifier follow-up by Claude on `claude/ws32-host-verifier-limit-20261103`; source only, not deployed or live-accepted; merged 2026-11-03 before the requested Codex review; Codex's post-merge WS-05 review of the registry delta at `e54795e` is APPROVE with no blocker, should-fix or nit findings and found the delta unchanged on main `837bb04` after #312, recorded via [#316](https://github.com/Larryfix71566/jarvis-voice-ai/pull/316) at merge commit `0e1a5f5520ba7db4c4bc8fa9c3539b2e33df9856`): `SkillRegistry._repo_source_refs` now bounds the canonical `ROADMAP.md` by `ROADMAP_READ_MAX_BYTES` (384 KiB) and every other path, including the `repo_search` verifier, by the unchanged 256,000-byte cap. Three registry-level regressions cover a canonical roadmap between the two limits (attested; fails before the change), above the roadmap limit (refused) and a non-roadmap file above the generic limit (refused); a mutation that removes the host size check fails the two refusal tests. The real 295,531-byte roadmap on `9feb38a` is now accepted by the host verifier. Claude's independent review of `5c5cb2e` that found B1 (verdict: changes requested) landed via [#293](https://github.com/Larryfix71566/jarvis-voice-ai/pull/293) at merge commit `30580f5793dedbc0a40f8e19e938a17a9d1c5cf6`. Earlier status text moved to the [roadmap history archive](docs/roadmap-log/archive/2026-11-10-roadmap-history.md) on 2026-11-10.
- **Implemented by:** Kimi, bounded WS-32 reader repair and synthetic regressions
- **Remaining work / acceptance:** The independent exact-source review of the original reader implementation is Claude's #293 at `5c5cb2e`: the reader change was correct within its own file, and its one blocking finding (B1, the host verifier's generic cap) was fixed by #296, which Codex approved via #316. No production deployment, live acceptance, roadmap-content trimming or other-owner correction is included. The inherited WS-05 stale-status checker finding was resolved separately; current roadmap validation is clean.
- **Model version:** not recorded; do not infer from system name
- **Where:** `claude/ws32-roadmap-read-cap-20261110` (read-cap follow-up, landed via #322 at `b83f0fc55c41edb6fab0a288b927d9e1b2678074`); review record `codex/ws32-pr322-review-20261110` (landed via #324 at `b9024ed2bc641930314421c55f1237ae83d11578`); `claude/ws32-host-verifier-limit-20261103` (B1 follow-up, landed via #296 at `e54795eb1d985e29638df08bcb9a4f56661480ea`); review record `claude/ws32-independent-review-20261103` (landed via #293 at `30580f5793dedbc0a40f8e19e938a17a9d1c5cf6`). Original: fix/ws32-roadmap-reader-limit-20261023; implementation `5c5cb2ee643655716774e05191e3c14c74504b05`; landed via #275 at `51a3f567d6f1f0ad1dc085cdc1127260cefffb77`
- **Plan:** `docs/plans/MORTIMER_COMMAND_CONSOLE_ATLAS_PLAN.md` §7.2; add only WS-32 dated progress during implementation
- **Scope:** Original WS-32 scope, unchanged: `mcp_servers/mcp_repo/logic.py` roadmap read-limit handling only; directly related `tests/unit/test_mcp_repo_logic.py`, `tests/unit/test_roadmap_reader.py` and `tests/unit/test_roadmap_event.py`; this WS-32 block, WS-32 dated entries in the existing plan and WS-32 `docs/roadmap-log/` entries. Preserve the 256,000-byte limit for every other path, stat-before-read and second-read race checks, path/secret guards, complete-card semantics, 512 KiB snapshot and 600 KiB display-event ceilings, sensitive-turn behavior and all other APIs. No roadmap content trimming, `jarvis/agents/base.py` change, UI/provider/configuration/credential/access change, live test, deployment or acceptance-checkbox closure. **Scope amendment, 2026-11-03 (Larry-authorized, Claude):** in `jarvis/skills/registry.py`, only the size check for the canonical `ROADMAP.md` inside `SkillRegistry._repo_source_refs` may use `ROADMAP_READ_MAX_BYTES`; every other path, `repo_search` verification, `_invoke`'s weather hook and all other source-classification rules stay unchanged. Directly related registry regressions in `tests/unit/test_registry_source_policy.py`, WS-32 dated plan progress and a WS-32 `docs/roadmap-log/` entry. WS-05's owner reviews the source-classification change (plan R.13 convention). No UI, provider, configuration, credential, deployment, live test or acceptance-checkbox change.
- **Next step:** none for the read-cap follow-up (#322 merged, Codex APPROVE via #324). larry: raising the console's 1 MiB snapshot bound would need a Swift change and is a separate decision. codex: none for #296 (recorded, APPROVE, via #316). larry: deployment and live acceptance of the console roadmap refresh remain separate decisions. kimi: no action required.
- **Updated:** 11-11 (Claude: #322 merged as `b83f0fc`; Codex's APPROVE recorded via #324 at `b9024ed`; no source change). Previous: 11-10 (Claude: read-cap follow-up and single-copy reads, #322). Previous: 11-10 (Claude: Codex's #296 registry review recorded, APPROVE via #316 at `0e1a5f5`; stale review-pending line corrected; no source change). Previous: 11-06 (Claude: review record #293 merged as `30580f5` on 11-03; stale merge request removed); 11-03 (Claude B1 host-verifier follow-up landed via #296; merge commit recorded)

</details>

<details id="ws-28">
<summary>WS-28 — Acceptance prerequisite: sandbox cleanup race and verifier fingerprint · Claude (prune-report fix; Codex repair landed)</summary>

**Workstream:** Larry approved Codex ownership and steps 1–2 of acceptance clearance on 2026-10-18 at 20:08:26 UTC: register ownership, repair the two #210 cleanup defects, independently review and verify. This is a release prerequisite repair, not new enhancement implementation or additional product acceptance criteria.

- **Owner:** `claude` (remaining prune operator-report fix, moved from Codex by Larry's explicit authorization in his Claude Duet channel on 2026-11-03 at 18:35:36 UTC ("I authorize you to take the work and complete it"), answering whether Claude should take over the remaining fix, and 18:36:03 UTC ("Update the roadmap to reflect that change")); `codex` retains attribution for the merged #222 repair and its synthetic verification; independent cross-system review is still required before any real prune/reclaim or affected sandbox creation
- **Status:** landed via [#295](https://github.com/Larryfix71566/jarvis-voice-ai/pull/295) at merge commit `4f2bc8337424ec397848b0e0d97821f1080527f5` (prune operator-report fix by Claude on `claude/ws28-prune-report-20261103`; source only; merged 2026-11-03 before the requested Codex cross-review; Codex's post-merge cross-review of `4f2bc83`, tested on main `837bb04`, is APPROVE with no blocker, should-fix or nit findings, recorded via [#316](https://github.com/Larryfix71566/jarvis-voice-ai/pull/316) at merge commit `0e1a5f5520ba7db4c4bc8fa9c3539b2e33df9856`): `python3 -m sandbox.prune` now prints would-delete (dry run) or deleted VMs, retained VMs with their reason, and malformed ownership/task records separately, and exits 1 when a deletion failed, 3 when any record is malformed, otherwise 0. The report gains a `retained` list; `kept` is unchanged. Four `main()` regressions; sandbox suite 164 tests pass. Eligibility, locking, leases, the corruption policy and the fingerprint rules are unchanged; `prune.py` is fingerprinted, so the runner fingerprint changes with this source. Earlier status text moved to the [roadmap history archive](docs/roadmap-log/archive/2026-11-10-roadmap-history.md) on 2026-11-10.
- **Implemented by:** Claude authored merged #210; Codex owns this explicitly dispatched repair only
- **Remaining work / acceptance:** Candidate revalidates cleanup eligibility under the existing start/delete lock while holding nonblocking target-owner session/file leases; verification-child reservation is serialized before reclamation and rejects an already-deleted parent. Cleanup code now participates in the runner fingerprint. Eight new regressions fail on unrepaired main and pass with the fix; full fake-controller suite 160 tests passes; three additional regressions reproduce and repair the foreign-session headroom blockage and ambiguous ownership on initial `24206281`. Independent review, separately authorized runtime merge and exact-candidate release verification remain open. No real cleanup/clone or product acceptance pass.
- **Model version:** not independently verified; do not infer from system name
- **Where:** `claude/ws28-prune-report-20261103` (landed via #295 at `4f2bc8337424ec397848b0e0d97821f1080527f5`). Historical: codex/sandbox-cleanup-repair-20261018, based on main `b29c7aba431eb1c9de6a0aa092128a8ce133119d`; isolated worktree after this claim lands
- **Plan:** `sandbox/IMPLEMENTATION.md` lifecycle/release ledger; existing `docs/plans/ROADMAP_JOINT_WORKING_PLAN.md` §9 retains acceptance sequencing
- **Scope:** Claude's claim: `sandbox/prune.py` `main()` output and exit status only (separate would-delete, retained and record-issue sections; a distinct nonzero exit code when record issues exist), plus the directly related regression in `sandbox/tests/`, dated progress in `sandbox/IMPLEMENTATION.md` and a WS-28 `docs/roadmap-log/` entry. Eligibility, locking, leases, the corruption policy, the fingerprint and every other cleanup rule stay as merged. Original scope and its exclusions, retained: Only the two cleanup prerequisite defects: `sandbox/prune.py`, `sandbox/control.py`, `sandbox/images.py`, `sandbox/session.py` and `sandbox/files.py` for eligibility/lifecycle-lock coordination strictly needed to prevent stale-plan deletion; `sandbox/verify.py` for runner fingerprint binding only; directly related synthetic `sandbox/tests/` regressions; dated progress/evidence in `sandbox/IMPLEMENTATION.md`, `sandbox/acceptance/` and WS-28 `docs/roadmap-log/`; this row and the existing cleanup launchd-label reservation in §3. Preserve all source/path/scanner/pin rules, privilege/network/audio/clipboard isolation, profiles, protected baseline, all twelve verification checks and original budgets/timeouts. No guest/dependency installation, startup/job activation, broad controller redesign, other owners’ model/source semantics, production source/settings/app changes or deployment. Synthetic tests use temporary homes and fake Tart only; no real prune/reclaim/clone until the repair has independent review.
- **Next step:** codex: none (the #295 cross-review is recorded, APPROVE, via #316). larry: any real prune, reclaim, clone, verification or launchd activation remains a separate decision.
- **Updated:** 11-10 (Claude: Codex's #295 cross-review recorded, APPROVE via #316 at `0e1a5f5`; no source change). Previous: 11-03 (Claude prune-report fix landed via #295; merge commit recorded)

</details>

<details id="ws-17">
<summary>WS-17 — Command Console CC7a: conversation-first stage · Codex remaining implementation</summary>

### Bounded roadmap reader repair — 2026-11-06

Larry approved a narrow branch-local registration exception for Codex on
`codex/roadmap-log-limit-20261106`: reader and tests, host attestation, and
roadmap-specific event/native decoding paths and tests. General source/privacy
limits, other owners and all acceptance criteria remain unchanged. Current
base is `555fe86`; local source repair preserves all dated logs, verifies the
complete log set before digest-bound provenance, and retains finite count,
byte and display ceilings. Larry subsequently approved branch publication and a draft PR for review;
merge, deployment and controller model changes remain unauthorized. Independent
static review and offline verification passed with documented skips/warnings. See the existing plan's dated entry
and [repair log](docs/roadmap-log/2026-11-06-ws-17-roadmap-log-limits.md).

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
- **Status:** landed: diagnostic-only #262 merged as `3cdb765`; historical frozen-candidate verification #224 merged as `c2e3c74`. The #224 receipt applies to `d38c886`, not freshly combined main. Actual restoration cause, current loaded identity and live/physical/observation acceptance remain unresolved. Historical source entry: landed via this PR (diagnostic source only; operational cause unconfirmed): the registered canonical restoration helper reports safe service/stage and exception class only after successful quarantine; quarantine failure never claims completion. Ten injected diagnostic regressions fail on the base; all78 focused offline tests pass with the change. Operational statements, checks, budgets and launch/readiness behavior are preserved. [Source/synthetic receipt](docs/acceptance/command-console/receipts/ws17-restoration-diagnostics-2026-10-22.md). Independent review and exact-head CI remain required; no installation, restoration retry or live/human acceptance is claimed. Historical 10-18 independent verification follows: frozen `d38c886` passed all twelve full-profile checks with source unchanged and a validated receipt; deployment, live acceptance, and physical/permission-gated checks remained open. [Exact receipt and limits](docs/acceptance/command-console/receipts/ws17-independent-verification-2026-10-18.md). Historical registration follows: landed via this PR (registration only; implementation pending): bounded canonical-deployer restoration diagnosis from source `c63ecce`; register content-free failure-stage/type reporting and only a causally verified minimal restoration repair. No runtime code is changed in this claim; required source review, CI, target identity and canonical held-release gates remain. Historical native milestone follows: landed via this PR (after-merge test-only state): verified programme `a672239` passes all12 original offline checks, six focused real-window cases with zero skips, exact-source independent review with no blocking findings, and all5 programme-head CI checks. Native582/five prerequisite skips/zero failures; every original28 assertion, negative wait, skip condition and3s readiness bound is preserved. [Final source receipt](docs/acceptance/command-console/receipts/ws17-native-deferred-hide-2026-10-22.md) retains both earlier nonpasses, exact programme/CI identities and coverage limits. Receipt-only metadata retains separate publication CI; actual-host, installation, full-context/workload, hardware and human gates remain open. No owner or checkbox changes. Earlier status text moved to the [roadmap history archive](docs/roadmap-log/archive/2026-11-10-roadmap-history.md) on 2026-11-10.
- **Implemented by:** Claude (Cowork): CC7a.1/1b/2/2b; Claude (Claude Code): CC7a.3 foundation from #173; Codex: observed-inventory voice/acknowledgement and Older-result repair `fee4ac0`, inventory-size/capacity correction `065d500`, measured reader retention `adf2597`, and CC7a.4 native-owned reuse/reference/upsert `6e218cd`/`47f9e05`; real thread-window capture readiness `0a2ff94`; source-age menu/VoiceOver/choices `748b1e5`
- **Remaining work / acceptance:** CC7a.1-CC7a.4, each a reviewed PR; RELEASE_READINESS UI2-22..UI2-25 on the Mac. UI2-04, UI2-09 and UI2-13 are held until then. Larry, Mac, 10-02, build `ae70f2c`: one console row with nothing below it in conversation, results and Knowledge Atlas (UI2-24's CC7a.1b part; its Recents parts wait for CC7a.3); Knowledge ▾ and Tools ▾ send content to the supporting display with no result open, and "Return display content here" brings it back; a spoken answer showed once in the thread. Larry, Mac, 10-03, build `9545641` (UI2-23): cards sat after their replies; Open showed the result and Conversation came back; pin, compare and close worked from a card and closing kept the Output record; after a layout 1 to 2 switch a new result arrived without taking the screen. A weather asked for from the conversation stayed a card; Larry decided it should open (CC7a.2b). After Codex's review of #169, only the answer to what he just asked opens: a background job finishing later stays a card, and with the supporting display open the conversation stays on the main screen. UI2-23 is rechecked on a build that contains CC7a.2b. The 10-06 public voice session on `bde22bb` establishes bounded ordered/full-text and arrival-focus subchecks in the [#191 voice receipt](docs/roadmap-log/2026-10-06-ws-20-codex-voice-acceptance-review.md); full UI2-22/23 protected/focus/scroll/size and remaining card/display cases stay open. Reuse those subchecks rather than repeat the same public text/routing cases solely for documentation. Approved design: `docs/interface-research/cc7a/cc7a-approved-design-2026-09-30.html` (transcript rows, compact cards, Recents menu, reuse reference line, no-jump notice); Codex's boundaries in plan §7.2.
- **Model version:** Historical implementation versions not recorded; do not infer from system name. Exact 10-09 cross-review: Claude Code 2.1.290 / `claude-sonnet-5`, recorded separately from Codex implementation in the linked receipt
- **Where:** main: diagnostic-only #262 (`3cdb765`, source `331d62e`) and historical verification evidence #224 (`c2e3c74`); prior native repair #243 remains landed. Existing release/install ownership is retained.
- **Plan:** `docs/plans/MORTIMER_COMMAND_CONSOLE_ATLAS_PLAN.md` §7.1 item 9 and §7.2
- **Scope:** Bounded canonical-deployer continuation: `scripts/deploy_main.sh` only safe service/stage and exception-class diagnostics after verified quarantine, plus a minimal restoration-readiness correction only after its cause is reproduced; directly related synthetic `tests/unit/test_deploy_held.py` and `tests/unit/test_deploy_main.py`; this WS17 block, existing plan, own dated log and source/synthetic receipts. Claim must land on main before code, except this exact branch-local generated-rollback-guard claim adopted under the §3 one-final-merge exception; no other work inherits the exception. Preserve all launch-source, PID/cwd/effective-policy, health, installed-program, receipt, hold and rollback checks; do not replace the runner bound to an existing snapshot. Any revised helper needs exact source review/CI and the canonical target-bound release ceremony before actual use. No raw exception text, secrets, real private records in review/publication, manual alternate launcher, service whitelist expansion, credential/security/model/provider/harness change, extra live test, cleanup invocation or acceptance checkbox closure. Earlier native-only scope is historical and did not authorize installer edits within that native slice: Bounded native prerequisite continuation explicitly assigned2026-10-22: `macos/MortimerHost/Tests/MortimerHostTests/WindowVisibilityTests.swift`, directly related test-only fixture support in that test file, and existing WS17 plan/evidence/daily log. Only if a product defect is causally reproduced, `macos/MortimerHost/Sources/MortimerHost/Console/WindowVisibilityReader.swift` may receive a narrowly scoped observer fix with review. Keep all existing hide/show/miniaturize/detach/animation assertions, real WindowServer prerequisites and skip semantics truthful; no blanket skip, timeout inflation, simulated pass, privacy/cost/provider/credential/configuration/activation change or installer edit. No additional live provider test; source/synthetic review remains separate. Independent and exact-head verification must be refreshed where changed bytes require it. Earlier scopes follow:  Bounded continuation explicitly authorized 2026-10-21: `jarvis/subscription_tools.py` exact verified-version set/comment only, directly related synthetic identity/stale-receipt tests and replayable offline receipt under existing WS17 evidence paths. Admit only independently probed2.1.291, retain2.1.290 and refuse unknown versions. No tools-enable flag, model/profile, request receipt, schema binding, privacy/source rule, provider endpoint, credential or production activation change. WS05 implementation and owners remain preserved. Existing scope follows: Larry-authorized selective-restoration prerequisite (2026-10-21): bounded `scripts/deploy_main.sh` install-held, base local restoration and rollback-held paths plus directly related synthetic tests in `tests/unit/test_deploy_main.py` and `tests/unit/test_deploy_held.py`; existing WS-17 plan/evidence/log only. Preserve human-only deny classification, the existing authenticated health helper and normal deployment semantics outside an active shutdown hold. No application/provider/model runtime edit, new credential/allowlist permission, live deployment/restart/inference, automatic database/settings rollback or cleanup lifecycle change. Additional Larry-approved acceptance repair (2026-10-21): existing WS-17 weather intent/dispatch and native reuse paths, bounded `jarvis/bot/weather_intent.py` if required, `jarvis/bot/weather_tool.py`, `jarvis/bot/weather_reuse.py`, request/console/weather adapters and payload-free identity tracing in `jarvis/bot/pipeline.py`; existing native arrival/selection and result-store files/tests below. Existing Supervisor/Developer guidance in `jarvis/prompts.py`, bounded acceptance/reporting guidance in `jarvis/bot/voice_guidance.py` and directly related existing voice-guidance helpers; existing conversation/run-log persistence and reviewed sandbox documentation-PR/readback workflow only. Task cancellation/deduplication may use existing delegation/task ownership paths only after explicit WS-05 boundary coordination (CX-27); do not edit shared delegate/Base/Registry or provider-construction hunks before coordination. Correct roadmap rendering/build/status and test-execution claims; when no approved runner exists, hand off truthfully rather than add a grant or pretend repository reads executed tests. Existing WS-17 plan/evidence/log and canonical UI2 wording only; preserve every human/visual checkbox until evidence and Larry observation warrant closure. No dedicated wizard, new durable task framework, credential/security/provider/model change, new tool privilege, schema/migration, paid benchmark, production-record disclosure or uncoordinated deployment. Investigate Skills-inventory 503 and memory warning read-only/separately unless a causal link is proven. Existing scope follows: Claimed current-request slice under merged #225: existing `App/AppMessageRouter.swift`, `Stores/WorkspaceStore.swift`, `Stores/ConversationStore.swift`, `Console/ConversationThreadView.swift`, the existing WS-17 console/DisplayPayload contract and inventory/turn-binding paths below, and directly related synthetic caller-chain tests; existing plan, canonical UI2-23 criterion in `docs/acceptance/adaptive-interface/RELEASE_READINESS.md` and WS-17 log only. Establish deterministic current-request eligibility, cancellation/supersession and one foreground winner before any focus change; preserve supporting-display ownership and all unrelated/background arrival behavior. No WS-05 `jarvis/agents/delegate.py`/Base/Registry edit, new durable task system, model/policy/account change or production operation. If the real caller chain needs another owner's path or a new wire identifier, stop for the corresponding scope/reservation before editing. Existing implemented scope follows: `App/ResponseResultRouter.swift`, `Stores/WorkspaceStore.swift`, `Stores/ConversationStore.swift`, `Console/AdaptiveStageView.swift`, `Console/ConversationThreadView.swift`, `Console/TopBarView.swift`, `Display/WorkspaceView.swift`, `App/AppMessageRouter.swift` (display arrivals: whether a result opens on arrival), voice result actions (`App/ConsoleActionCoordinator.swift`, `App/ConsoleActionRegistry.swift`, JarvisKit `ConsoleProtocol.swift`, `jarvis/bot/console_protocol.py`), DisplayPayload `subject_key` (JarvisKit + `jarvis/bot/display.py`), weather tools' reuse check; `Console/ConsoleActionBar.swift`, `Stores/WorkspaceRecents.swift`, `jarvis/bot/console_actions.py`, the console inventory/turn binding and result acknowledgement portions of `jarvis/bot/pipeline.py`, `jarvis/bot/weather_tool.py`, `jarvis/bot/weather_card.py`; CC7a.4 expansion reserved on main via #195: new `jarvis/bot/weather_reuse.py` and associated tests; only the weather-call interception in `jarvis/skills/registry.py` `_invoke`, using a request-owned ContextVar hook after existing guards and preserving classified `_finish_invocation` envelopes; optional bounded `weather_source` in Python/JarvisKit DisplayPayload (`AppMessage.swift`), with `WorkspaceStore` as the sole in-memory cache/freshness owner; shared `weather_reuse` and `result_reopen` actions under the §3/plan §7.2 contract. No process-global registry callback, backend TTL mirror or registry guard/policy change; associated unit/native/contract tests and exact-build WS-17 evidence in `docs/acceptance/adaptive-interface/RELEASE_READINESS.md`, `docs/acceptance/command-console/`; dated progress in the existing plan and WS-17-specific `docs/roadmap-log/` files. Bounded 10-17 repair extension, per #213: weather-repeat, numbered-result and roadmap-read routing instructions only in `jarvis/prompts.py`; tool description and reference parsing in `jarvis/bot/console_actions.py`; content-free console action/status logging and weather-delegation context minimization only in `jarvis/bot/pipeline.py`; `tests/evals/voice_workflow_eval.py` and `tests/evals/voice_workflow_cases.yaml` for the affected synthetic-history cases and action-level assertions; native Recents-menu rendering and spoken-reference tests. Additional Larry request 10-17: ensure Mortimer can read and knows how to read the roadmap. Add the canonical path/read-only tools and checkout-freshness guidance near the beginning of injected `docs/REPO_MAP.md`; add explicit Supervisor-to-Developer roadmap/status routing and Developer read guidance in `jarvis/prompts.py`, with focused prompt/navigation/read-access tests. Preserve repo path restrictions and source/privacy policy; no auto-fetch, broader filesystem access, memory copy of roadmap status, runtime activation or claim of main freshness. Roadmap-display addition authorized 10-17: read-only roadmap parsing, dated `docs/roadmap-log/` evidence and provenance in `mcp_servers/mcp_repo/logic.py` using existing guarded repository reads; deterministic snapshot filters and voice/pointer filter state in the existing roadmap-result paths; presentation mapping in `jarvis/bot/display.py` and associated Python/JarvisKit DisplayPayload schema; existing `Display/DisplayContentView.swift` and a bounded `Display/RoadmapView.swift`, with refresh/navigation wiring in the already-owned console paths and focused tests. Reuse current result identity, transport, sharing and WS-21 transfer; no new server, port, credentials, registry trust changes or alternate status database. Reserve any new wire field in §3 before implementation. No other Supervisor/tool policy, live model/route/account setting, source approval, private log disclosure or provider activation. Preserve WS-21 transfer/screen contracts and other active workstream behavior (CX-20) Bounded source-contract extension explicitly approved by Larry 10-17: `jarvis/skills/registry.py` `_repo_source_refs` and associated classification tests may verify the optional roadmap snapshot and every included guarded dated-log source/hash. Preserve the exact legacy response contract for other files, reject fabricated or mismatched snapshot/provenance/log data, retain existing source-policy floors and approvals, and make no changes to unrelated registry guards, credentials, routing or activation. This closes the schema incompatibility before the new reader transport is enabled. Bounded roadmap-event extension explicitly approved by Larry 10-17: `jarvis/agents/base.py` only the `agent_tool_result` observation projection for canonical `repo_read_file ROADMAP.md`, plus directly related tests. Preserve the existing 20,000-character limit for every other tool/file and every private/redacted path. Carry a complete, bounded, already host-classified roadmap snapshot to the native display without broadening source approval, changing model history, run-log caps, delegation, budgets, tool permissions or WS-05 source-before-sink enforcement. Refuse oversize/malformed roadmap observations explicitly rather than emitting truncated JSON. Coordinate this narrow observation-only exception with WS-05 ownership of Base; no other Base edits are authorized.
- **Next step:** codex: reconcile #254 roadmap findings and #275 under their respective owners; obtain exact combined-source independent review and combined-main validation before any separately authorized operational recovery. Diagnose actual readiness failure through the canonical target-bound path only when operations are authorized. Keep installation/restoration/restarts/live tests held; #224 historical verification does not certify current main.
- **Updated:** 10-27 UTC (merged source/evidence identities reconciled; no operational or acceptance change)

**Branch-local claimed extension (2026-10-30):** The coordinator adopted the independently reviewed narrow generated-rollback guard claim in PR #290 on `codex/ws17-generated-rollback-guard-20261030`, under the exact one-final-merge exception in §3. Owner: Codex. Status: claimed on this branch only; not on main. The claim is exactly `scripts/deploy_main.sh` plus synthetic tests in `tests/unit/test_deploy_main.py`. Candidate `2cb5af7e3207579ade6341d066baf56926c74673` is frozen on current PR base `838bac7d76dd282f21ad019dd9234b693c612fc3`; the exact two-module regression suite passes 87 tests under Python 3.12.13. Independent exact-source review remains required. Newly generated non-held rollback scripts reject every argument vector, including `--restore-db`, `--`, `['']`, and the flag in any position, before side effects; preserve no-argument rollback and held paths. This is not a database-free archive guarantee, restore hook implementation, complete D3 coverage, or authorization to execute old scripts or perform a restore/deploy. The matching claim-doc commit precedes source. Independent exact-source review and CI remain required. R3.22 is adopted branch-locally for exactly seven WS-04 files: offline `restore.prepare` pending fencing, service teardown, restore-specific grant retirement/shutdown and owner-lock hold. WS-17 retains all restore/deployment invocation and script ownership. Completion/recovery/rebinding, DB replacement, WS-17 script edits, production integration and live restore remain out of scope.

### Kimi combined-main validation — 2026-11-05

- **Owner:** `codex` retains WS-17, its implementation and every release/operational next step above; `kimi` owns only this bounded, read-only combined-main validation. Larry retains deployment, restart and live-acceptance decisions.
- **Status:** landed via #305 at merge commit `e782048965db98c397398077b9965bde5d6b7108` (documentation-only validation evidence): Kimi validated exact main `3695d78fc79c6c19db45fafc03a3adf0b48cb2a5`, whose tree outside `docs/` and `ROADMAP.md` equals `f874cf1a757b03d98336aca36ef08fb13c15c7a6`. On macOS 27.0.1 / arm64, every registered gate exited zero: 7,322 unit passes/11 skips/219 subtests; 197 integration passes/four skips; 13 offline evals; nine policy and 164 controller tests; 17 knowledge-base tests; JarvisKit 235/zero failures; MortimerHost 590/five skips/zero failures; clean-environment full pytest 7,528 passes/15 skips/219 subtests. Roadmap checking, backend import, latency, shell syntax, frontend install/build and allowlist dispatch also passed. Exact commands, exit codes and SHA-256 log hashes are in the evidence log.
- **Implemented by:** Kimi ran the checks and has no source authorship in the target. Claude wrote the merged claim and validation handoff at Larry's request.
- **Remaining work / acceptance:** This is local source/test evidence only. The exact combined-source independent review is assigned to Kimi (2026-11-10 claim below); the requested source reviews of merged #295/#296 remain with their named reviewers. Installed or loaded identity, deployment, restoration, live, physical and human checks remain open. A pass does not lift the operational hold by itself. Any later code-changing merge, including draft #301's Swift, needs fresh validation before deployment relies on it.
- **Where:** claim landed via #303 at `3695d78fc79c6c19db45fafc03a3adf0b48cb2a5`; Kimi evidence on `kimi/ws17-combined-main-validation-20261105`, landed via #305 at `e782048965db98c397398077b9965bde5d6b7108`; [claim log](docs/roadmap-log/2026-11-05-ws-17-kimi-combined-main-validation-claim.md) and [validation evidence](docs/roadmap-log/2026-11-05-ws-17-kimi-combined-main-validation.md).
- **Plan:** existing WS-17 plan, `docs/plans/MORTIMER_COMMAND_CONSOLE_ATLAS_PLAN.md`, dated entries 2026-11-05.
- **Scope:** Read-only checks in a fresh Kimi worktree at the exact target. Kimi writes only this sub-section, dated WS-17 progress in the plan above and WS-17 `docs/roadmap-log/` entries. No source, test, fixture, configuration or dependency edits; no `~/jarvis-voice-ai-clean`; no `scripts/deploy_main.sh`; no service, launchd, app install or launch; no `RUN_LIVE`, provider call, credential or vault; no other system's workspace; no checkbox; WS-17's main fields above stay Codex's.
- **Next step:** codex/coordinator: obtain the exact combined-source independent review (assigned to Kimi by Larry on 2026-11-10; see the claim below) before any separately authorized operational recovery; keep installation, restoration, restarts and live tests held. larry: retain every deployment, restart and live-acceptance decision. Any later code change requires fresh validation. Kimi's bounded validation and evidence publication are complete.
- **Updated:** 11-05 (post-merge: #305 landed as `e782048`; main's tree exactly matched the reviewed PR tree and all five PR checks passed; no runtime, operational or acceptance change).





### Kimi combined-main revalidation claim — 2026-11-06

- **Owner:** `codex` retains WS-17 and every release/operational next step; `kimi` owns only this bounded, read-only revalidation. Larry retains deployment, restart and live-acceptance decisions.
- **Status:** revalidated exact main `4e58eaaf2993ba46eba379ba93341287b9247296` after #311 landed. The target guard was empty against `a87256ad9e7966496542f2e7bf32582aa489cd10` outside `docs/` and `ROADMAP.md`, and main did not move during the run. **Overall FAIL:** fourteen of fifteen registered checks exited zero; `swift test --package-path macos/MortimerHost` exited 1 in both the initial run and the exact-command rerun. `PhoneRemoteAuthorityProcessTests.testOrdinaryUnknownWaitRetainsActualSingletonAfterPartialEOF` failed both times at line 76 with `XCTUnwrap failed: expected non-nil value of type "String"`. The main MortimerHost target passed 590 tests with five skips; JarvisKit passed 239 with no skips; clean full pytest passed 8,013 with 145 skips and 583 subtests. No source or test was changed and no acceptance or operational hold is lifted.
- **Implemented by:** Kimi runs the checks and has no source authorship in the target. Claude wrote this claim and the updated primer at Larry's request.
- **Remaining work / acceptance:** The original fourteen checks plus #317's blocking Ruff F821 gate, fifteen total: publication-equivalent gates of current `validate.yml`, `knowledge-base.yml` and `sandbox.yml`, both Swift suites and the clean-environment full `pytest` of `scripts/deploy_main.sh` phase A, with exact commands, exit codes, tallies, native skips and log hashes. Backend dependencies come from `requirements-lock.txt` to match current CI; the scheduled, non-blocking dependency-drift workflow is not a publication gate. Not covered: the exact combined-source independent review, source review of #301's WS-17-file Swift lines, the reviews of merged #295/#296, loaded identity, deployment and every live, physical or human check. A pass does not lift the hold by itself.
- **Where:** claim on `claude/ws17-kimi-revalidation-claim-20261106`, landed via #309; target rebind landed via #311; Kimi evidence on `kimi/ws17-combined-main-revalidation-20261106`, published via this docs-only PR; [claim log](docs/roadmap-log/2026-11-06-ws-17-kimi-combined-main-revalidation-claim.md) and [revalidation evidence](docs/roadmap-log/2026-11-06-ws-17-kimi-combined-main-revalidation.md).
- **Scope:** As the 2026-11-05 validation above: read-only checks in a fresh Kimi worktree at the exact target; Kimi writes only this sub-section, dated WS-17 progress in `docs/plans/MORTIMER_COMMAND_CONSOLE_ATLAS_PLAN.md` and WS-17 `docs/roadmap-log/` entries. No source, test, fixture, configuration or dependency edits, deployment, service operation, app launch, live call, credential or checkbox.
- **Next step:** larry: review and merge this evidence PR. codex/larry: route the repeated PhoneRemoteAuthority failure to its owning workstream for a separately reviewed source fix; do not treat this run as acceptance. kimi: make no source or test edit; after any code-changing merge, rebind and revalidate before deployment relies on it. Every operational, loaded-identity, live, physical and human decision remains separately held.
- **Updated:** 11-10 (Kimi completed the fifteen-check run at exact `4e58eaa`; overall FAIL from one repeated native test, with all other gates green; full commands, both attempts, skips, ignored outputs and log hashes recorded; no runtime or acceptance change).

### Kimi combined-source review claim — 2026-11-10

- **Owner:** `codex` retains WS-17 and every release/operational step; `kimi` owns only this bounded, read-only review, assigned by Larry on 2026-11-10 at 14:16:37 UTC in his Claude Duet channel ("Kimi", answering who owns the combined-source review that lifts the WS-17 hold). Larry retains deployment, restart and live-acceptance decisions.
- **Status:** claimed (landed with #318). Target: freeze SHA `5777e98cf1cdbaa65eb13079044693794c071927` (`origin/main` after #328, which gave the flaky `test_outer_task_deadline_covers_tool_execution` headroom, and the docs merges #325 to #327 and #329; its tree outside `docs/`, `ROADMAP.md` and `AGENTS.md` equals `b2fbb2d`), recorded here by Claude on Larry's word (2026-11-11 01:58:16 UTC: "...then we should freeze main and begin"); no result yet. Non-fix code now lands on the `next` branch cut from this SHA ([release closure plan](docs/plans/MORTIMER_RELEASE_CLOSURE_PLAN.md) §2), so this target does not move again unless Larry approves an acceptance fix by name.
- **Implemented by:** Kimi reviews and has no authorship of the target except the files excluded below. Claude wrote this claim at Larry's request.
- **Remaining work / acceptance:** Independent source review of the code delta from production `b136a2a66032b17082776a01353abe67e352c31e` to the freeze SHA, i.e. the tree outside `docs/` and `ROADMAP.md`, for release risk: correctness, security, data loss and operational recovery. Findings are reported as new fix PRs by the owning system. Kimi-authored code in that delta (WS-31 NR1 `jarvis/app_build_contract.py`, WS-32 reader repair #275) is excluded under §0 rule 14 and goes to a non-Kimi reviewer. A pass does not lift the operational hold by itself; Larry decides recovery and deployment.
- **Where:** Kimi review on `kimi/ws17-combined-source-review-20261110`, created only after this claim lands; claim on `claude/ws33-roadmap-freeze-archive-20261110`; [claim log](docs/roadmap-log/2026-11-10-ws-33-acceptance-unblock.md).
- **Scope:** Read-only. Kimi writes only this sub-section, dated WS-17 progress in `docs/plans/MORTIMER_COMMAND_CONSOLE_ATLAS_PLAN.md` and WS-17 `docs/roadmap-log/` entries. No source, test, configuration or dependency edits; no deployment, service operation, app launch, live call, credential or checkbox.
- **Next step:** kimi: review the frozen tree at the freeze SHA and publish a docs-only verdict PR; do not merge.
- **Updated:** 11-11 (Claude recorded the freeze SHA and linked the release closure plan and the `next` branch; no result, operational or acceptance change). Previous: 11-10 (Claude registered the claim at Larry's request).







**R3.23 Scope/Where amendment (2026-10-31):** WS-17 owns only `jarvis/bot/phone_remote_results.py` and `tests/unit/test_phone_remote_results.py` on `codex/ws04-ws17-ws30-results-snapshot-resume-20261031`, based on accepted design `92dbcc5a7d95f3f89f4c2b7312edd2bc1a9bd456`; synthetic trusted projector, classification, collection grant and bounded journal only. This is a branch-local amendment to the existing row. No WorkspaceStore or real-content bridge.

**R3.23 adopted offline results projection (2026-10-31):** The coordinator adopted the original 15-path synthetic snapshot/resume scope in [remote plan R3.23](docs/plans/MORTIMER_REMOTE_ACCESS_PLAN.md#r323-results-snapshot-resume); the effective coordinated source scope is 16 paths after the ASGI test-only amendment. WS-17 owns only `jarvis/bot/phone_remote_results.py` and `tests/unit/test_phone_remote_results.py`: trusted synthetic collection grants, projection, classification and bounded journal/cursor state. Independent review ACCEPTED exact source commit `b4ae7740719f45e4dd81ad3f4917c789c608f57c` (tree `88a201a809f1310c950032ee04d199fa63deeec6`). This adds no `WorkspaceStore` bridge or real-content access. Frozen S0 vectors remain unchanged with zero exact R3.23 executions; the separate accepted R3.21 audit branch is not integrated, and no full facade conformance is claimed.

**Historical typed phone-card design documentation claim (2026-10-31; superseded by the adopted source claim below):** Parent coordinator dispatches Codex to prepare this isolated docs-only design on `codex/ws04-ws17-ws30-phone-card-design-20261031`, based on immutable R3.24 finalization `8797891d48bbd4a7e1b9d755ac23d6bc9a2c2470`. Status: design prepared for independent review; source adoption remains pending. WS-17 owns the proposed mobile-view domain semantics and synthetic result/source projection; Mac console, WorkspaceStore and release scopes are unchanged. Effective documentation Scope/Where amendment: only the WS-04/WS-17/WS-30 blocks in `ROADMAP.md`, dated appendices in existing `docs/plans/MORTIMER_REMOTE_ACCESS_PLAN.md` and `docs/plans/MORTIMER_PHONE_ACCESS_PLAN.md`, and `docs/roadmap-log/2026-10-31-ws04-ws17-ws30-phone-card-command-design.md`. This claim is recorded before plan edits. Fresh read-only GitHub refresh confirms main `5310d1a9305035f43143fcffad6161619281f475` and draft/open/unmerged PR #290 at `39208d18d8c6fde0a9a0539e4d7c3aa68de5610f`; main ROADMAP blob matches local `5310d1a` exactly. Local origin has no main ref and ancestor traversal encounters a missing historical commit; retain the existing coordinator-authorized branch-local exception and require current-main reconciliation before integration. Fresh checkout is clean; active owners and source scopes stay intact. No runtime/source edit, frozen fixture/adapter change, identifier reservation, production controller/security, publication or live action is authorized. Next step: codex independent reviewer evaluates the exact design and proposed 22-path source/test map; coordinator adopts any later implementation claim separately. The completed documentation is in the existing remote plan and phone-plan §18; no implementation or test acceptance is claimed.


**Adopted typed phone-card source claim (2026-10-31):** Coordinator adopts independently accepted design `ffb1b1ccb4582bd38bd8ca426e9835a99a4e2ce9`, tree `1a6f090afd231766f32a44eb45e2a53824e7d280`, for complete synthetic offline implementation. Owner: `codex`; status: independently bounded-accepted synthetic/offline source `a121dfb06385702b82a18041d7d974ab40877ee9` / tree `10b9b68d7a27d52ca2b54d42784326b5da279f86`; Where: `codex/ws04-ws17-ws30-phone-card-source-20261031`. Effective source Scope for this row is exactly: `jarvis/bot/phone_remote_results.py`; `tests/unit/test_phone_remote_results.py`; `jarvis/bot/phone_remote_result_commands.py`; `tests/unit/test_phone_remote_result_commands.py`. Across WS-04/17/30 this is exactly 22 paths (7/4/11), 19 existing and three new, matching the verified design manifest. Documentation remains limited to these three roadmap blocks/shared reservation, existing remote/phone plans and the typed-card design log. Fresh local checks found all targets match accepted blobs and no dirty work; coordinator remote refresh at 14:52 reports main `5310d1a`, PR290 `39208d18`, green CI544 and no comments/other-PR/published collision. Local handoff origin lacks main and complete historical ancestry; the existing branch-local exception continues, with current-main reconciliation before integration. This amendment precedes all source edits. Preserve frozen fixture/adapter, R3.23 historical receipts and R3.24 recovery/proof/cancellation invariants. No production content/controller/Keychain/signing/network/live/external action or publication/merge is included. Next step: coordinator-managed current-public-main reconciliation and complete integration/validation packet; remaining foreground product construction and live prerequisites are enumerated in [phone-plan §19](docs/plans/MORTIMER_PHONE_ACCESS_PLAN.md#19-product-completion-audit--2026-10-31), without a new source claim. Independent final validation: 369 Python tests/501 subtests with warnings as errors, 67 PhoneCore tests and 24 scoped native tests, zero skips; earlier unsigned app/UI bundle build at `8c2e49f0` applies to unchanged Swift/native bytes. UI execution remains unrun because CoreSimulator 1171.7.0 is older than required 1174.21.0. Full-repository/integration CI, exact full-vector facade replay, production construction/content/transport and live release remain open. Final combined reentry/source-denial probe records uncertain and fences; healthy ordinary withholding stays unfenced. Claim metadata is Git-resolved. Dated verdict, exact artifact hashes and finalization evidence are in the existing remote/phone plans and typed-card log. This final slice updates four claimed docs only; accepted source/frozen/native bytes are preserved. No publication, merge or live acceptance is claimed.

</details>

<details id="ws-13">
<summary>WS-13 — T5 mail, calendar and brief: P1 landed; P3m (mail headlines on request) landed via this PR, Mac check open · Claude</summary>

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
- **Status:** landed via this PR (P3m, the requested mail-only subset of P3 in plan §R.0f, Larry's 11-03 choice "Mail headlines first"; branch `claude/ws13-mail-on-request-20261103`): the Supervisor's direct `daily_brief(scope="mail")` tool behind `JARVIS_BRIEF_ENABLED`, a protected typed `brief` card with each account's real status, and honest mail answers in the prompt. Python offline-tested; the Swift card is untested until built on the Mac. D2–D9 unchanged. Earlier increments: landed: P1 (mail header source) merged in #204 as `575cc7b` (head `8b77df1`, revision 3) and deployed in `575cc7b` on 10-13; Codex reviewed revisions 1 and 2 and accepted the registry decisions (CX-21); Codex signed off revision 3 (`8b77df1`) on re-review; #205 (merged as `9f9bc71`) fixed the M1-1 preflight, which printed PASS with no mail name set; Codex's two further preflight corrections (startup-shell removals applied, relative `--env-file` resolved) merged as #212 (`f3d5378`) on 10-17 (Larry merged; no Codex review of revision 3 is recorded); Larry ran M1-1 to M1-3 on the Mac on 10-13 against the deployed `575cc7b` and all three passed (Mac acceptance recorded below; formal M1-1 repeat from production after the next deployment); P2 and P3 not yet claimed
- **Implemented by:** P1: Claude (landed, #204 `575cc7b`); P3m: Claude (landed via this PR; plan by Claude on Opus, implementation by a Sonnet worker and reviewed by Claude, per Larry's 11-03 request); P2, the rest of P3, P4, P5: not started
- **Remaining work / acceptance:** P1 Mac acceptance, 10-13, deployed `575cc7b`: M1-1 PASS (the corrected preflight from this branch, with the four vault names set: each reaches `mcp-mail` and no other of the 15 servers; effective JARVIS_ENV_SCOPING_ENABLED on; Larry's `.env` does not set it); M1-3 PASS (bellsouth.net via `imap.mail.att.net` with the secure mail key, and Gmail with an app password: both `status=ok`, `exact` counts, headers complete, call 3.1-3.6 s against the 13 s bound; the first Gmail attempt failed `login_rejected` because the stored user was not the full address and the password was not an app password, both corrected in the vault); M1-2 PASS (one unread test message per account: a second read still counted it as UNSEEN, `exact:1` on both, so the first headers read set no \Seen flag, and Larry confirmed both still unread in webmail); `mcp_server_started name=mcp-mail tools=1` logged at the first session after the deploy. Open: a recorded Codex review of the merged revision 3, #212, if Codex wants one (the preflight now replaces its environment with the startup shell's snapshot, so an `unset` in .env takes effect, and resolves a relative `--env-file` before loading; #205 at `9f9bc71` had the startup-shell read and the missing-server FAIL); the formal M1-1 repeat, `python scripts/check_mail_env.py` from production after the next deployment (historical #254 wording, now superseded: "the recorded deployment is still `575cc7b`; #212 and everything merged after it are undeployed"). Current source reconciliation: #212 (`f3d5378`) is an ancestor of the later successful `b136a2a` deployment receipt dated 2026-10-19; ancestry and that receipt do not establish a formal M1-1 repeat, current loaded identity or new mail acceptance. Keep the formal M1-1 repeat open until its own dated eligible-build evidence exists; the macOS OSError seen in two Mac test runs before the `deadline` unification is still unidentified (it did not occur against the real servers). Then P2 (needs the Google account in macOS Internet Accounts for M2-2; its claim needs Codex's agreement on the WS-17 portions, plan §R.13) and P3, each claimed on its own against §R.12; P4/P5 stay separately gated (§R.11)
- **Model version:** not recorded; do not infer from system name.
- **Where:** main: P1 via #204 (`575cc7b`), the plan via #196, the preflight follow-up via #205 (`9f9bc71`), preflight revision 3 via #212 (`f3d5378`); P3m claimed via a docs-only PR (11-03); P3m implementation via this PR from `claude/ws13-mail-on-request-20261103`
- **Plan:** `docs/plans/MORTIMER_MAIL_CALENDAR_BRIEF_PLAN.md`; §R (10-07) is authoritative and the August text is history except where §R.9 keeps it. No GitHub branch other than this one touches the plan. Migration `0035` stays reserved for T5 (`0035_brief`).
- **Scope:** P3m (11-03, plan §R.0f): new `jarvis/brief.py`, `jarvis/bot/brief_tool.py`, `tests/unit/test_brief.py`, `tests/unit/test_brief_tool.py`; the `daily_brief` registration, menu flag and prompt flag in `jarvis/bot/pipeline.py`, `jarvis/bot/tool_schemas.py` and `build_supervisor_prompt` with its brief addenda in `jarvis/prompts.py`; only the brief lines of existing tests that pin the Supervisor menu and prompt; the brief scorer and cases in `tests/evals/routing_eval.py` and `tests/evals/cases.yaml`; `JARVIS_BRIEF_ENABLED` in `.env.example`; native (untested until the Mac): the `brief` section of JarvisKit `DisplayPayload` in `AppMessage.swift`, new `macos/MortimerHost/Sources/MortimerHost/Display/BriefCardView.swift`, the `brief` dispatch in `DisplayContentView.swift` and the brief no-auto-open rule in `ConversationThreadView.swift` (WS-17 files; WS-17 is landed, and Codex reviews these lines per plan §R.13). Earlier, the plan file; and for P1 (plan §R.6): new `mcp_servers/mcp_mail/` (`__init__.py`, `logic.py`, `server.py`, `skill.yaml`), the `mcp-mail` entry in `config/mcp_servers.yaml`, the `mcp-mail` source-contract entries only in `jarvis/skills/registry.py` (WS-05 reviews; §4 CX-21), `EXPECTED` in `tests/unit/test_requires_env_snapshot.py`, `ALL_SERVERS`/`TOTAL_TOOLS` in `tests/integration/test_registry.py`, `EXPECTED_TOOLS` in `tests/integration/test_mcp_servers.py`, new `tests/unit/test_mcp_mail*.py` with the fake IMAP server fixture `tests/unit/mcp_mail_fake_server.py`, the names-only preflight script `scripts/check_mail_env.py` for M1-1, and `.env.example`. No agent, prompt, model, pipeline, Swift or migration change in P1
- **Next step:** codex: review P3m's R.0f deviations and its WS-17-file Swift lines; larry: after deployment, run `swift test` for JarvisKit and MortimerHost, then ask Mortimer about mail and confirm the card shows Gmail and AT&T with their real status (P3m Mac check); claude: fix anything either finds. Still open from P1: larry: after the next recorded deployment of main through `scripts/deploy_main.sh` (as the WS-17 release owner runs it), run `python scripts/check_mail_env.py` from production (formal M1-1 repeat); codex: a review of merged revision 3 (#212) only if wanted; claude: propose the P2 claim after WS-17's open #216 follow-ups land, since it needs Codex's agreement on the WS-17 portions
- **Updated:** 11-03 UTC (Claude: P3m implemented, offline tests pass; earlier the same day, "Gmail unavailable" traced to no source, closing Codex's Gate 0, and P3m claimed via #299). Previous: 10-27 UTC (restore #254 source status and label its older deployment claim superseded; M1-1 repeat and all acceptance checkboxes remain open)

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

**Checker-policy decision — Larry, 2026-10-22 15:39:07 UTC:** errors fail CI;
warnings remain advisory. Larry approved preparing the reviewed enforcement
change, with no merge/deployment or branch-protection change. This separate
registration proposal uses `docs/ws20-checker-policy-claim-20261022`; #247 stays
frozen at `e284526`. B4 retains Claude ownership; Codex prepares documentation,
synthetic verification and reviewable integration under the delegated WS-20
workstream. Proposed implementation branch: `codex/ws20-checker-enforcement-20261022`,
with Claude's bounded cross-review required. Scope is only the existing
`.github/workflows/validate.yml` roadmap step's comment/name/invocation,
directly related synthetic checker tests, and this existing plan/row/log.
Preserve checker severity rules, all other jobs/triggers/permissions/action pins,
branch protection and every product acceptance criterion. No policy source or
workflow edit is applied by this registration. Under §0, this claim must reach
main before the enforcement implementation is applied. Larry separately approved
merging documentation-only #249 after final review and CI pass (2026-10-22 15:56:35 UTC); no broader dependency or implementation
merge is included. The approved decision is recorded; its checklist
milestone remains unchecked until the chosen behavior is implemented and verified.

**Full-program factual documentation — 2026-10-22:** Codex adopts the serial
coordinator’s all-31 current/future handoff in the existing joint plan on
`docs/ws20-program-receipts-20261022`, based on verified main `2944080`.
This documentation-only continuation preserves frozen #246/#247/#252 and all
checkboxes. Source claims, proposed Claude lanes, installed state and acceptance
stay distinct; no other owner or runtime scope changes. See the
[dated program and exact merge receipt](docs/plans/ROADMAP_JOINT_WORKING_PLAN.md#full-program-direction-and-serial-integration-receipt--2026-10-22).
The coordinator alone handles serial merges; the parent remains Larry’s decision
contact. #250 enforcement is proven (3/4 milestones evidenced); #252 retains
its separate checkbox synchronization and final acceptance checklist.

**Stage A continuity publication — 2026-10-22:** Codex publishes the complete
historical testing proposal and nine sanitized controller/Skills attachments
from frozen #246 on the existing `docs/ws20-program-receipts-20261022` branch,
refreshed from main `ab31dfa`. The coordinator reserved the single docs-map
link; both feature owners agreed to byte-exact historical adoption, keeping
canonical-plan pointers with their owners. The [dated publication log](docs/roadmap-log/2026-10-22-ws-20-continuity-stage-a.md)
records scope, source identities and review limits. This publication leaves
Stage B (#252 policy-checkbox/receipt and #247 runbook alignment) separate,
with every checkbox and other owner plan unchanged. No whole frozen branch
merge, source implementation or new execution authority is included.

**Enforcement closeout — 2026-10-22:** #250 merged as `6234949a524c84c91e6a459658cf02f290eac20e` after Larry’s explicit approval. Exact main readback and five CLI behavior cases passed; the real roadmap check reports zero errors/warnings. The historical registration note above is superseded by this [post-merge receipt](docs/roadmap-log/2026-10-22-ws-20-checker-enforcement.md#post-merge-enforcement-receipt--2026-10-22). **3 of 4 WS-20 milestones are complete**; this is not a product or code-completion percentage. Only the owner-evidence/Phase A/B milestone remains open.

### Acceptance checklist — remaining

B1–B4 implementation is merged; the 72-entry migration is already verified.

- [x] **Codex · documentation cleanup:** WS-10/11 lifecycle prefixes now describe their landed foundations while every acceptance gate stays open. The roadmap checker passes on this documentation candidate; the single Production line still matches the recorded `bde22bb` deployment. [Dated cleanup proof](docs/roadmap-log/2026-10-06-ws-20-codex-lifecycle-closeout.md).
- [x] **Codex / Claude · observation:** The first ten published post-migration PR merges (#161/#162/#163/#165/#166/#167/#168/#164/#169/#170) and their recorded integration merges replay with no conflict in §8 or `docs/roadmap-log/`. Exact complete merge trees and unchanged §8 are verified; [receipt](docs/roadmap-log/2026-10-06-ws-20-codex-ten-pr-change-log-observation.md). Unrecorded manual history is not claimed.
- [x] **Larry · decision:** After the warn-only rollout period and owned corrections, decide whether the checker becomes a blocking CI gate; the chosen behavior is recorded and verified. Completed by Larry’s errors-fail/warnings-advisory decision and #250 merge `6234949`; see the exact post-merge receipt above.
- [ ] **Each acceptance owner · evidence:** Link the remaining live checks to their own rows (WS-17, WS-18 and the other open gates); publish the final Phase A/B exit record without treating implementation as live acceptance.

Source: [joint-working plan §§3, 6–7](docs/plans/ROADMAP_JOINT_WORKING_PLAN.md).

**Workstream:** Larry, 10-02: bring the roadmap and open PRs up to date so Claude and Codex can work on it together, and stop the roadmap drifting. Larry chose: each system fixes its own rows; the change log moves out of `ROADMAP.md`, one production line, rows written as they read after merge, and a drift checker; the plan lives in the repo.

- **Owner:** `codex` (existing WS-20 documentation and bounded checker-enforcement integration on the registered branch); `claude` retains B4 authorship/ownership and required cross-review, plus WS-13 ownership. WS-17 release/install ownership is unchanged.
- **Status:** landed: #250 checker enforcement (`6234949`), #271 historical continuity adoption (`d4fde41`) and #273 policy/checklist closeout (`782baa3`). This reconciliation restores the #273 checklist state reverted by #264: 3/4 evidenced milestones; owner evidence and final Phase A/B remain open.
- **Implemented by:** Codex (B1–B3); Claude (B4)
- **Remaining work / acceptance:** Existing owners link complete applicable live, physical and observation evidence to their own rows and record final Phase A/B disposition. The checker choice is already implemented/verified; this update closes no product criterion. Future work retains its matching main claims and prerequisites.
- **Model version:** not recorded; do not infer from system name.
- **Where:** main via #250/#271/#273; historical `docs/ws20-program-receipts-20261022` and frozen #246/#247/#252 remain provenance, not new implementation authority.
- **Plan:** `docs/plans/ROADMAP_JOINT_WORKING_PLAN.md`
- **Scope:** Additional approved checker-enforcement integration: only `.github/workflows/validate.yml` roadmap-step comment/name/invocation, directly related synthetic tests in `tests/unit/test_check_roadmap.py`, dated progress in the existing joint-working plan and WS-20-specific log/evidence, and this row. Preserve checker logic/severity, all other jobs/triggers/permissions/action pins, branch protection and every product criterion; Claude cross-review is required. Existing acceptance-clearance documentation scope remains ROADMAP current acceptance/status summary and this block, `docs/plans/ROADMAP_JOINT_WORKING_PLAN.md`, WS-20 `docs/roadmap-log/**`, `docs/acceptance/IMPLEMENTATION_STATUS.md`, `docs/acceptance/ACCEPTANCE_RUNBOOK.md` and WS-20 receipts under `docs/acceptance/command-console/receipts/`. Preserve all other owners, checkboxes and receipts; do not edit other feature plans or WS-17 verification evidence. No application runtime, config, credentials, access, provider workload, production write, restart, deployment or enforcement beyond the named roadmap CI step.
- **Next step:** codex: retain the restored #273 policy receipt and reconcile applicable owner evidence for the remaining Phase A/B milestone. claude: retain B4 and current source ownership. larry: perform owner-gated acceptance only after eligible candidate readiness and retain release decisions. No service, cleanup, installation, live test or model change follows.
- **Updated:** 10-27 UTC (restore proven policy checkbox and prior continuity history lost in #264; all product criteria preserved)



- **Aggregate draft — 2026-10-27 UTC:** Codex coordinates the requested aggregate draft on `integration/unmerged-mortimer-20261027`; source owners remain unchanged, no merge or operational authority. [Full included/deferred manifest](docs/roadmap-log/2026-10-27-unmerged-integration.md).

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
<summary>WS-05 — Model access: subscriptions, APIs and SAYGM · Kimi status reconciliation; Codex implementation</summary>

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

- **Owner:** `kimi` for the bounded 2026-10-26 documentation-only status reconciliation; `codex` retains all WS-05 implementation and acceptance ownership
- **Status:** landed via this PR (documentation-only status reconciliation): PR #264 merged on 2026-10-23 as `204a74151293447898eab9243d0565d186a12bc6`; its recommendation-only harness foundation and bounded repair are landed source, with no installed/runtime acceptance implied. Larry authorized Kimi's bounded reconciliation on 2026-10-26. Codex's separate test-only worker-boundary fixture isolation repair is now a local candidate on its registered branch; independent review and exact-head CI remain pending. The candidate keeps subprocess environment and cwd out of the parent process and adds a deterministic parent-notifier poll regression; local focused pytest could not run because this executor lacks pytest and PyYAML. Historical status: separate test-only worker-boundary fixture isolation repair after its registration lands; no implementation yet. Existing harness after-merge state: landed recommendation-only harness foundation and bounded repair via PR #264 after coordinator integration; no installed/runtime acceptance is implied. Claim #266 landed as `67438c3a66827616a1f91cf692a98245a262813e` before this reconciliation; WS-03 acknowledged the exact roster/pin-only shared-test edits. Exact source reviews and CI are recorded in the canonical plan and receipts; fresh combined verification remains a publication gate. Historical registration status: claimed via this documentation amendment for exact recommendation-only foundation integration on the existing repair branch; candidate #264 remains unmerged and runtime adoption is unverified. Registration covers the inventoried frozen foundation plus reviewed repair, not new architecture or model switching. Historical narrow registration:  claimed for bounded harness recommendation remediation once this documentation amendment lands on main; source edits have not started. Frozen #242 `d476905057fc29207338721ce9ec2a452cb2085d` and #253 `a568f7dc282fff7436a4527feb7d162a2b021c81` remain review inputs, not installed or accepted builds. This narrow registration does not land or expand unmerged #241/#242. Prior provider status follows: landed via this PR (after-merge source state; publication checks remain recorded in the PR/log): October 22 correction of selective retirement to exclude only direct OpenAI/Anthropic while retaining explicitly configured other providers under existing identity/privacy/authentication/budget gates. Isolated WS-05 source only; WS-17 owns installation/restoration. Historical status: landed via paired PRs #232/#233 (after-merge implementation state; this preparation is not a merge verdict). Revised combined `e74e4b8` passes all twelve original independent checks, candidate backend6,764/11skips/two subtests, native580/eight prerequisite skips/zero failures and197integration/fourskips. Required exact-source cross-system review remains open; final publication CI is separate. No live/human checkbox closes. Earlier status text moved to the [roadmap history archive](docs/roadmap-log/archive/2026-11-10-roadmap-history.md) on 2026-11-10.
- **Implemented by:** Foundation contributions are not fully itemized; WS-02 isolation and MAR-A baseline work are Codex
- **Remaining work / acceptance:** Codex: complete the remaining implementation and acceptance once prerequisites are supplied; Claude: record cross-system review of the merged implementation; Larry: exact source authorization, operator-issued identity, native-test assignment, account and deployment decisions. Kimi's documentation reconciliation closes no acceptance checkbox or unresolved review/runtime gate.
- **Model version:** not recorded; do not infer from system name.
- **Where:** `codex/ws05-worker-fixture-isolation-20261023`, local fixture-only candidate based on current main `5310d1a9305035f43143fcffad6161619281f475`; independent review and publication remain open.
- **Historical harness source:** `codex/ws05-harness-remediation-20261022` landed via #264 as `204a74151293447898eab9243d0565d186a12bc6`; preserve frozen #242/#253 inputs. This merged branch is not the active fixture lane.
- **Status reconciliation provenance:** `kimi/ws05-status-claim-20261026` via #276; documentation-only, not an implementation branch.
- **CI546 test-isolation claim — 2026-11-01 UTC:** Codex continues on `codex/ws05-worker-fixture-isolation-20261023` from public PR #290 head `5255b23d555451ec47e60212f994dd8467d79da6`, with verified main `5310d1a9305035f43143fcffad6161619281f475` already an ancestor. Coordinator dispatched the five empty-client pilot failures. Exact amendment before edits: `tests/unit/test_model_use_development_pilot.py` for the inert VM fixture's disk-capacity input, explicit real-guard low-disk refusal and content-free assertion diagnostics; this WS-05 roadmap block and dated progress in `docs/plans/MORTIMER_MODEL_USE_ENHANCEMENTS_PLAN.md`. No runtime, workflow, dependency, model, profile, scanner, credential or threshold change. Local source has a deterministic five-failure reproduction with simulated free space below the existing 8 GiB guard; CI546 retained no report/disk evidence, so its specific trigger remains unproven. Independent review and corrected-head CI remain open; conformance work is isolated on its own branch.
- **CI546 local result — 2026-11-01 UTC:** Test-only candidate `66f0cac769ce07c96761a28f4941c4d2e6368f05` preserves the real guard and existing assertions, with explicit below-minimum refusal and bounded failure diagnostics. Full unit validation: 7,521 passed / 583 subtests / 141 prerequisite skips / 20 warnings; focused related rerun: 329 passed / eight existing diagnostic skips (included in the full unit inventory); separate sandbox suite: 160 passed. Independent review and corrected-head CI remain pending. CI546's exact runner trigger is unproven; deterministic low-capacity reproduction is not proof of its disk state. No runtime or model change, publication or live acceptance.
- **Coordination update — 2026-10-27 UTC:** Larry dispatched Codex to repair #275's WS-05 drift check with this metadata-only correction. Codex ownership, claimed fixture scope and every acceptance gate remain unchanged; Kimi retains #275 reader authorship and #276 plan/log reconciliation. Larry reviews and merges #275; no implementation, model switch, installation or acceptance is performed by this correction.
- **Fixture registration provenance:** `docs/ws05-worker-fixture-claim-20261023`; documentation-only registration, not an active implementation branch. Base `67438c3a66827616a1f91cf692a98245a262813e` includes corrected #266.
- **Separate deadline-test lane — 2026-10-31:** Codex test-only candidate on `codex/ws05-deadline-confirmed-phase-20261031`; claim `bf5fd6a`, source `465060b`, and the sole source path is `tests/unit/test_model_execution_deadlines.py` (SHA-256 `8d5736ddd02e7f245f0013516adc347bf78df72fc4db18db2cb055e4fef63172`). The full deadline module passed 16 tests and the seven-module model-execution/budget/ledger suite passed 230 tests in isolated Python 3.12.13 validation with lock-aligned Anthropic dependencies. Independent review and corrected-head CI remain pending; no production source or acceptance status changed. This lane is disjoint from the registered `test_claude_developer_capability.py` fixture lane.
- **Foundation registration provenance:** `docs/claim-ws05-harness-integration-20261022` via #266; this documentation branch is not an active implementation branch. Frozen #241 is not the current registration.
- **Historical provider source lineage:** `codex/ws05-subscription-retirement-20261020`, isolated checkout from `fd56e98`; claim [PR #230](https://github.com/Larryfix71566/jarvis-voice-ai/pull/230) merged as `005e2a4`; implementation [draft PR #232](https://github.com/Larryfix71566/jarvis-voice-ai/pull/232).
- **Historical fixture:** bounded fixture branch `codex/ws05-capability-fixture-20261007`; #201 merged as `83d90e8`, source `08c0635`, final head `de4381c`. Documentation follow-up [PR #202](https://github.com/Larryfix71566/jarvis-voice-ai/pull/202) records the merged repair, exact CI and revised-reference approval. Original main claim #199 (`99993eb`) and #200 (`a5b6f88`) remain. [Notifier isolation evidence](docs/acceptance/model-use-enhancements/receipts/mar-capability-notifier-isolation-2026-10-09.json)
- **Prior landed foundation:** main (PR #177, merge `c38d895`); source branch `codex/ws05-execution-20261005`; claims #175 (`66198c5`), #176 (`0b6723c`), #178 (`0960373`), #179 (`fb3e1aa`) and #180 (`4a2d4aa`); merged implementation #177 (final head `06a7ad5`), frozen ordinary source repair `50daa8b`; advisory scope #181 merged as `ac8eb7a` and integrated before edits; advisory budget/source/integration `6007479` / `c091d7e` / `5da9b47`; descendant budget/council/review `cc420bf` / `df80223` / `58b4e21`; preflight repair `7d74226`; prerequisite claim #182 merged as `d5d8cae` and integrated before hash/storage edits; tokenizer recipe scope #183 merged as `4d2a3ce` and integrated before edits
- **Plan:** `docs/plans/MORTIMER_MODEL_USE_ENHANCEMENTS_PLAN.md`
- **Provider source milestone:** Codex alpha.11 compatibility from frozen #244 `014f915bd8f8ac9a5e187779601fe1718d7e21b5` lands as source only after this separate integration is merged. Candidate branch `codex/ws05-alpha11-integration-20261022` reconciles verified main `2944080` without changing the active harness claim, Where, Scope, Next step or CX-28. Runtime/test blobs remain independently reviewed `b4ce39a`; receipt sanitation and current-main documentation reconciliation require fresh docs-delta review and publication CI. All live, installed-build and privacy gates remain open; no acceptance checkbox closes.
- **Scope:** Active Kimi claim (2026-10-26): documentation only, limited to this WS-05 block, dated progress in `docs/plans/MORTIMER_MODEL_USE_ENHANCEMENTS_PLAN.md`, and WS-05 `docs/roadmap-log/` entries. Record the verified #264 merge commit `204a74151293447898eab9243d0565d186a12bc6` and reconcile stale candidate/unmerged wording without changing any acceptance checkbox, unresolved review/runtime gate, implementation ownership, historical evidence or other row. No source, test, configuration, credential, deployment or live-acceptance work. Codex's existing scopes remain with Codex and are not reassigned. Historical scope: Recommendation-only foundation integration supplement: adopt only the exact frozen #242 hunks and their registered repair in #264, inventoried in the canonical plan at candidate `eba21305564b905299d4e59a761f6d4ca90bd2db`. Additional foundation paths beyond #257 are `jarvis/admin/server.py` model-route/status endpoints only; `jarvis/bot/model_route_tool.py` truthful preview/refusal; `jarvis/model_preferences.py` exact proposal validation and harness/voice-confirm refusal only; `jarvis/status/daily.py` additive passive hook with existing health coverage retained; `jarvis/status/models.py` isolated additive evidence reader; `macos/JarvisKit/Sources/JarvisKit/AdminAPI.swift` model-route types and `macos/MortimerHost/Sources/MortimerHost/Drawer/RepoTab.swift` model-access controls only; corresponding `ModelRouteControlsTests.swift`, `tests/unit/test_admin_api.py`, `test_auth_middleware.py`, `test_harness_confirmation.py`, `test_model_preferences.py`, `test_model_route_contracts.py`; authored `skills/harness-model-evaluation/**`, its one `config/skills.yaml` enabled entry and digest; only the two package-registration expectations in `tests/unit/test_agent_skills.py` (harness roster entry and matching-pin count), preserving every WS-03 compatibility assertion. Preserve #257's active narrow repair paths below. This adopts existing reviewed hunks, not arbitrary edits to shared files. WS-03 retains all loader/catalog/service/importer/matcher implementation and other shared-test changes; provider/release owners retain their files and settings. New or conflicting source changes outside these exact hunks return to the affected owner before edits. The retained #257 restrictions below govern new repair implementation; the exact frozen-hunk adoption above is the sole foundation exception. Bounded harness remediation only: `jarvis/status/harness.py` process-shared report serialization, generation-bound notice acknowledgement and finite supported short-Claude-ID recognition; `skills/harness-model-evaluation/SKILL.md` description, `mortimer.yaml` example references and matching-related package guidance only; `tests/fixtures/skills_authoring/harness-model-evaluation/matcher-cases.json`; corresponding harness package revision digest only in `config/skills.yaml` (no enabled list, registry policy or other package changes); `tests/unit/test_harness_brief.py`, isolated `test_harness_daily_offline.py` carried from #253, and at most one dedicated harness cache-concurrency test module. Own documentation: WS-05 block, this canonical plan, harness recommendation receipt directory and dated WS-05 log. Read existing daily/models paths but do not edit them; preserve health checks and tool menu. Do not edit WS-03 loader/catalog/service/selector/importer or its shared test files; no global matcher changes. No model-preference/routing/provider/credential/native/installer changes. Inherit reviewed #242 only as a separately identified unchanged dependency, not as new implementation permission; any main-integration conflict outside this repair scope returns to its owner. Further paths require a claim amendment. Prior provider scope remains with its existing owner: October 22 clarification: bounded `jarvis/provider_access.py`, API transport enforcement in `jarvis/llm_client.py`, `jarvis/subscription_readiness.py`, `.env.example`, related synthetic tests and existing plan/log. Read protected endpoint registry without editing it; retain SAYGM catalog verification and source privacy floors. No native/installer/acceptance file edits or service operations. Additional subscription-retirement dispatch (2026-10-20): existing WS-05 routing/execution/subscription/usage paths, `jarvis/config.py`, `jarvis/agents/supervisor.py`, `jarvis/bot/pipeline.py` (LLM service construction and subscription event/tool integration only), bounded new subscription voice adapter and provider-access policy modules; `config/model_endpoints.yaml`, `config/model_profiles.yaml`, `config/model_aliases.yaml`, `config/agents.yaml`, `config/upgrade_agent.yaml`, `.env.example`; background/vision/council/direct-client construction paths and corresponding startup/preflight/status scripts; directly related offline regression tests and operator migration documentation in the existing model-use plan/acceptance directory. Retire direct Anthropic/OpenAI inference, prohibit implicit paid fallback, and select official subscription runtimes only when exact runtime/authentication/capability checks succeed. OpenRouter and other billable providers are not subscription substitutes or automatic fallbacks. Preserve speech services, protected-source policies, sandbox permissions, model quality floors, existing WS-17 weather/result/display behavior and all historical evidence. No secret values in repository/logs, token extraction, sign-in, destructive credential removal or automatic production restart. Stage source changes and verified runtime readiness before activation; unsupported workloads remain explicitly unavailable. Confirmed source-policy-only handoff (2026-10-21): new `jarvis/voice_sources.py`; `jarvis/memory.py` rendered snapshot classification only; `jarvis/bot/late_result.py` rewrite policy retention; the agreed pipeline ingress/context/result regions, Base per-run policy export and Delegate immediate/late source transport. Preserve acceptance-owned weather intent, request identity, stop-turn refusal, terminal callbacks and ContextVar restoration. Registry remains unchanged. Existing scope follows: model-access policy/execution/preferences and subscription-tool bridge only: `jarvis/model_routing.py`, `jarvis/model_preferences.py`, `jarvis/model_execution.py`, `jarvis/subscription.py`, `jarvis/subscription_tools.py`, `jarvis/saygm.py`, `jarvis/privacy_policy.py`, `config/model_access.yaml`; prospective route/billing/duration metadata in `jarvis/usage_ledger.py` and `jarvis/llm_client.py`; bounded privacy source/sink repairs in `jarvis/agents/delegate.py`, `jarvis/memory_model.py`, `jarvis/memory_extraction.py`, and `jarvis/memory_sweep.py` (enabled-mode policy/execution only; preserve routing-off compatibility); model-route endpoints in `jarvis/admin/server.py`, route diagnostics in `jarvis/status/`, model-execution integration in `jarvis/agents/base.py` and `jarvis/bot/model_route_tool.py`; `macos/MortimerHost/Sources/MortimerHost/Drawer/RepoTab.swift`, model-route types in `macos/JarvisKit/Sources/JarvisKit/AdminAPI.swift`; related model-access tests and verification/pilot scripts; `docs/plans/MORTIMER_MODEL_USE_ENHANCEMENTS_PLAN.md`, `docs/acceptance/model-use-enhancements/**`, shared architecture/model-route references. Additional bounded MAR-B/D/G scope, claimed before edits: `jarvis/model_budget.py` for optional task-level configured-price admission; typed host source/result classification and payload-free early MCP error sinks in `jarvis/skills/registry.py`; policy propagation/retrospective MCP-buffer redaction in `jarvis/runlog/store.py`; repository source-path traversal validation only in `mcp_servers/mcp_repo/logic.py`; canonical identity validation only in `jarvis/agents/upgrade_agent.py` and `jarvis/council/config.py`. Related tests stay in this row; do not alter skill permission declarations, sandbox authorization, model/endpoint pins or historical fixtures. No WS-17/WS-21 console/result files or self-edit allowlist edits. Further bounded execution/source scope claimed before edits: per-run route/profile snapshots, tool-result policy, shared limits and enabled-mode no implicit failover in `jarvis/agents/upgrade_agent.py` (including AppBuildAgent); `jarvis/development_sources.py` for host-proven development source classification and `jarvis/development_attestation.py` for authenticated creator source receipts; source-provenance adapters only in `jarvis/selfedit/service.py`, `jarvis/agents/workspace.py` and `jarvis/skill_authoring.py`; authenticated creator result transport only in `jarvis/bot/server.py` `_dispatch_creator` and `jarvis/admin/server.py` creator association/tool endpoints; host source/session snapshot and receipt verification only in `sandbox/workspace.py`, `sandbox/session.py` and `sandbox/files.py`. Preserve all sandbox read/write/ceremony permissions, authorization, publication/validation gates, runtime lifecycle and source exclusions; no host execution bypass, broader public-data grant, account activation or production change. Further bounded council/MCP scope claimed before edits: `jarvis/council/council.py` and `jarvis/council/__main__.py` for one coordinator budget, trusted child sponsorship through proposer/judge/shadow/planning/replay calls, checked member routes, cancellation and authenticated thread-context propagation; bounded council/planning/research job budget and host-source policy threading in `jarvis/admin/server.py`. `mcp_servers/mcp_selfedit/server.py`, `mcp_servers/mcp_selfedit/logic.py`, `mcp_servers/mcp_apps/server.py` and `mcp_servers/mcp_apps/logic.py` for hidden request/response source-metadata adapters only; authenticated ordinary self-edit preview/start/run/read/write/status/finish and app-build job/submit source transport in `jarvis/admin/server.py`; corresponding host source bindings in `jarvis/development_sources.py`, receipt variants in `jarvis/development_attestation.py` and source-before-sink integration in `jarvis/skills/registry.py`. Related tests remain WS-05. Preserve all model identities, explicit council tier/seed/effort choices, single observed-usage accounting, sandbox read/write/ceremony/publication/validation gates, inactive production flags and legacy routing-off behavior. No skill permission declarations, GitHub client/template rewrites, WS-17/WS-21 files or self-edit allowlist changes; unknown/private foreign application source still requires a real host approval. Further bounded advisory source transport scope claimed before edits: `jarvis/advisory_sources.py` for separate authenticated planning/research caller and retained-action proof, `mcp_servers/mcp_web/server.py` and `mcp_servers/mcp_web/logic.py` for hidden request/response metadata only, and `jarvis/research/crawl.py` for host-acquired source/origin evidence and confidential defaults for unverified bytes. Existing WS-05 Base/Registry/model-budget/admin/self-edit/attestation paths may bind the actual Developer or Analyst caller, original durable host budget, accepted input floor before operation, cancellation/deadline ownership and signed results before sinks. Preserve workspace and creator protocol separation, all permissions, explicit council membership/model floors, research workflow/scorer behavior, routing-off parity and manual-action authorization. JSON limits, bearer authentication, HTTPS or crawler success cannot grant source approval or money allowance; no UI changes, provider activation or broader public-data grant. Further bounded image-source prerequisite scope claimed before edits: `sandbox/artifacts.py` only for exact path/SHA-256 pins of independently reviewed synthetic credential test fixtures, plus directly related source-archive tests. Keep `SECRET`, all path/source exclusions, historical baseline pins and both scanner enforcement sites unchanged; no path-only/pattern exemption, fixture-body edit, permission/lifecycle/profile waiver or production settings change. This scope does not include sandbox runtime/control/images/setup behavior. Further bounded pilot-isolation prerequisite scope claimed before edits: new stdlib-only `jarvis/storage_context.py` for immutable host-owned database/preference overrides, context propagation and retained worker drain before temporary cleanup; `jarvis/db.py` only its default-path resolver, with explicit paths and all migrations/DDL unchanged. Existing WS-05 `jarvis/usage_ledger.py`, `jarvis/model_routing.py`, `jarvis/model_execution.py` and pilot scripts may read that host-only context and retain owned asynchronous worker lifetime; related tests verify real DB/ledger isolation, foreign-thread separation, cancellation/drain and legacy parity. Do not mutate process-global database/preference environment to isolate a pilot; no production storage, schema, limit, route, source approval or account setting change. Further bounded tokenizer-image prerequisite scope claimed before edits: `sandbox/guest/prepare.sh` only, to acquire the officially SHA-256-pinned English `punkt_tab` data required by locked NLTK/Pipecat, install it under the protected Python prefix (`.venv/share/nltk_data`) during fresh online image preparation, and prove cold tokenizer use before preparation completes. Related recipe/resource acceptance tests and receipts remain WS-05. Preserve current hydration/cache ownership and read-only worker access, all twelve profile checks, source scanner/exclusions, network/audio/clipboard isolation, operator credentials and installed image/settings pointers. No RTVI/voice/test assertion edit, sleep/skip/timeout waiver, runtime/control/images behavior change, provider/model/endpoint/allowlist change or production activation. Further bounded capability-fixture scope assigned by Larry 10-07: `tests/unit/test_claude_developer_capability.py`, using the existing frozen current-worker-owned source fixture in `tests/unit/test_model_use_development_pilot.py` (helper changes only if necessary), directly related fixture regression tests, and this row's plan/evidence/log. Preserve every strict owner/link/mode/read guard, source bytes and scanner/pins, protected baseline, and all twelve verification checks; do not chown/adopt baseline files, change hydration/lifecycle/profile behavior, add test skips, weaken assertions or raise timeouts. Any new baseline/reference requires separate review and approval before another independent comparison.
- **Next step:** codex: obtain independent review of the CI546 test-isolation candidate and, after publication authorization, verify exact-head CI. Preserve the separate conformance candidate and all real/live gates. Historical next-step record: larry: review and merge this documentation-only status reconciliation. codex: retain all implementation and acceptance work, including the separate fixture-isolation lane on its registered future branch; no model switch, installation or live test is included. Frozen #269/#270 are not retried as a substitute for repair. The separate deadline-test lane has completed focused validation (230 tests); independent source review and corrected-head CI remain pending. kimi: no further WS-05 work without a new dispatch.
- **Updated:** 2026-11-01 (CI546 bounded test-isolation candidate validated locally; exact CI cause, independent review and corrected-head CI still open); prior: 2026-10-26 (Kimi reconciled #264's merged source identity and active branch lifecycle under Larry's authorization; no acceptance or runtime change); prior: 10-22 America/New_York (claim #266 landed; #264 current-main reconciliation; exact WS-03 acknowledgement; source-only after-merge status, no activation or acceptance closure); 2026-10-23 UTC fixture claim supplement only, no test edits or acceptance advance


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

R1 foundation and the remote-bind guard are merged. Local preparation, local activation and remote binding remain separate gates; completed synthetic/offline source is not production or live acceptance.

- [ ] **Codex · full oracle/integration:** Complete real-admission/facade mapping of the frozen 70-vector oracle. Historical S0/sensitivity/isolation evidence and the six-case refinement do not close this gate; preserve fixture/adapter and restore/incarnation requirements.
- [ ] **Larry · onboarding decision:** Choose supervised setup, one-time CLI or Mac pairing; the R2 recommendation is not approval.
- [ ] **Codex · onboarding implementation:** Claim and validate the chosen vault/Keychain path. Preserve one-time minting, stdin-only secrets, verified readback, existing-storage refusal and cleanup limited to this attempt; no auth/remote activation.
- [ ] **Codex · disposable acceptance:** Verify first-run/repeat/interruption and DB/vault/Keychain failures, exact storage identity, both flags and unauthenticated 401 behavior.
- [ ] **Larry / Codex · live preparation:** Separate authorization and exact source/presence/readback/database identities required. Auth stays off and listeners loopback-only; no enabled-mode/Skills acceptance implied.
- [ ] **Larry / Codex · authorized local activation:** Verify bare 401/authenticated Connect, voice/status/Skills, socket isolation, immediate revocation and rollback with remote bind false.
- [ ] **Larry · spoken check:** Record real system_status on the frozen setup; health/native tests do not close it.
- [ ] **Larry / Codex · separately chosen remote mode:** Record the decision, then G2/§8 tunnel/ACL/Funnel, LAN/tailnet sockets, authenticated voice/barge-in/Runs, offer methods, Keychain and immediate revocation. Deferred remote mode remains explicitly unaccepted.

Historical technical wording and all qualification details remain in the linked record (private evidence paths generalized) and canonical R1/R2/§8 contracts; these checklist items grant no credential/activation authority.

**Workstream:** Remote access T2 and staged offline phone admission, results and proof-bound connections.

- **Owner:** `codex`; Larry retains activation/live decisions. Other owners unchanged.
- **Status:** in-progress: public cumulative offline source `fff9fe8a` and local command refinement `68eb03b3` are independently accepted within scope. Eight translated rows/six unchanged markers; 107 markers and exact-vector/UI/live gates remain. The ten-path v4 proof-to-voice candidate `e2a3892f` is independently bounded-accepted; fresh independent native compilation and unlocked aggregate verification pass.
- **Implemented by:** Codex; historical attribution retained verbatim.
- **Remaining work / acceptance:** Complete oracle/main and remaining external-display/phone UI gates; production controller, credentials/protected owner, transport/content and signing/install remain separate. iOS 17 is adopted; device compatibility is unverified. Unlocked-desktop verification closes the five visibility failures without source/settings changes.
- **Model version:** Historical assignment retained; no harness-controller model change.
- **Where:** `codex/ws04-proof-voice-brokerage-20261031`, accepted design `ad376278` and effective claim `f55b1ac5`; accepted command candidate `68eb03b3` remains unchanged. Earlier lanes are historical inputs.
- **Plan:** [Canonical remote-access plan](docs/plans/MORTIMER_REMOTE_ACCESS_PLAN.md); [phone product plan](docs/plans/MORTIMER_PHONE_ACCESS_PLAN.md); [existing connection log](docs/roadmap-log/2026-10-31-ws04-phone-connection-design.md).
- **Scope:** Exactly the ten source/test paths enumerated in the adopted proof-to-voice claim below, plus this WS-04 block, existing remote plan and R3.21 refinement log. Frozen fixture/adapter, channel/ASGI runtime, other owners and unrelated history remain unchanged. Detailed process receipts stay local.
- **Next step:** codex: prepare/review the source-preserving 13-path publication candidate directly on verified public `fff9fe8a`; larry: authorize publication separately. Independent fresh native 28/phone 435 tests + 701 subtests and unlocked Host 587 + authority 28 pass; focused six visibility tests are included. Three external-display cases remain explicitly excluded for Larry's grouped session. Keep all 107 v3 markers, zero exact-vector replay, UI/device and live gates open.
- **Updated:** 2026-11-01; effective ten-path claim `f55b1ac542ae6860652d09b1c291490678da6707` precedes source `bfe801c5`; earlier command claim/source remain in the historical entry below. Evidence is in the existing remote plan/R3.21 log.

### Kimi independent admission-core review — 2026-11-01

- **Owner:** `codex` retains this bounded WS-04 admission implementation; `kimi` completed the bounded independent exact-source review of its admission core in #290, which landed on main as `137c6689d2d18f3765003aae1eeb610bd8945b0a`. Larry retains activation and live acceptance decisions.
- **Status:** Kimi gives a bounded source-only **APPROVE** for draft #290 at exact head `85bc736eff6311943bce77dfe769b683ec9d944d`, with zero blocker/should-fix/nit findings in the registered scope. The focused suite passes 12 tests/135 subtests and the independent synthetic harness passes 439 assertions. #290 landed on main via merge commit `137c6689d2d18f3765003aae1eeb610bd8945b0a` (2026-11-06 02:37 UTC, head `7d12cc2493a05ea7f96cb4fc18683deab945f0d8`); the five reviewed admission-core files are byte-identical there to the reviewed head. Kimi's approval covers only that admission-core scope. It is the only review of #290 by a system other than Codex; any review of #290's other slices is recorded only in Codex's own logs, by a nonauthor reviewer identified by ID, and GitHub shows no formal PR review. No part of #290 is accepted. No route, persistent grant store, tunnel, credential, installation, deployment or live acceptance is established.
- **Implemented by:** Codex / GPT-6 Luna authored the draft implementation; Kimi has no implementation authorship and performed only the independent review and documentation evidence.
- **Remaining work / acceptance:** No remediation arises from this bounded review. The documented identical-tuple restore limitation remains a later integration gate, not general restore safety. This review does not close Stage 1.1: persistence/host-anchor, route and peer-sink wiring need the plan's 0.2 reservations and later exact scope. Local token onboarding, credentials, local activation, remote binding, phone calls and release acceptance remain separately gated.
- **Model version:** GPT-6 Luna implementation assignment, per Larry's direction; exact runtime build not recorded. Independent reviewer: Kimi.
- **Where:** Codex implementation on `codex/ws04-phone-admission-core-20261029`, reviewed at `85bc736eff6311943bce77dfe769b683ec9d944d` and landed via #290 at merge commit `137c6689d2d18f3765003aae1eeb610bd8945b0a`; Kimi review evidence on `kimi/ws04-phone-admission-review-20261101` in [the exact-source review log](docs/roadmap-log/2026-11-01-ws-04-kimi-phone-admission-review.md).
- **Registration history:** The implementation claim was registered by draft PR #287 on `docs/ws04-phone-admission-claim-20261029`. The separate documentation-only review claim used `kimi/ws04-phone-admission-review-claim-20261101` and merged as #291; neither documentation branch is an implementation branch.
- **Plan:** [Canonical WS-04 plan](docs/plans/MORTIMER_REMOTE_ACCESS_PLAN.md); approved phone-admission stage in [phone plan §16](docs/plans/MORTIMER_PHONE_ACCESS_PLAN.md#16-approved-native-iphone-direction-and-staged-claims--revision-54-amendment-candidate-2026-10-28).
- **Scope:** Codex retains the registered implementation scope: `jarvis/bot/phone_admission.py`, `tests/unit/test_phone_admission.py`, `tests/unit/test_phone_admission_contract.py`, read-only `tests/fixtures/phone_admission_contract/v1.json`, this WS-04 block and dated progress in the canonical plan. Kimi's review-only scope was to read those files plus `tests/unit/test_phone_admission_boundary.py` at the recorded #290 head, run offline tests and bounded synthetic hostile checks, and write only this WS-04 block, dated WS-04 progress in `docs/plans/MORTIMER_REMOTE_ACCESS_PLAN.md` and WS-04 `docs/roadmap-log/` entries. No source/test/fixture edits, other #290 files, runner/VM, route/peer/sink wiring, persistent store/schema/host anchor, config key, credential, pairing/enrollment, tunnel/network change, service operation, iOS/APNs/CallKit, provider/media, live data, installation or deployment. No shared identifiers are reserved; full Stage 1.1 still requires approved 0.2 reservations and its own complete integration evidence.
- **Next step:** codex: retain implementation ownership and continue the separately gated integration work. Any later change to the reviewed admission-core files needs fresh exact-source review; onboarding, activation, remote binding and live acceptance remain separate decisions.
- **Updated:** 11-06 (Claude, at Larry's direction: recorded #290's merge as `137c668`; review scope unchanged; no source, runtime or acceptance change). Previous: 11-01 (Kimi completed the bounded independent review of exact #290 head `85bc736`; source-only approval with no findings, no runtime change and no live acceptance).

### R3.21 command refinement effective claim — 2026-10-31

Owner `codex`; Where `codex/ws04-r321-command-refinement-20261031`; status: test source `242c57c743df499584548c7520e9f7088bb4c272` bounded-accepted through final candidate `68eb03b3`; design claim `cbba8ba753f7d016e5ca4bb39476ac4ad079fdf4` preceded implementation. Larry's continued-development dispatch selects the existing frozen-oracle gap. Effective scope is exactly `tests/unit/test_phone_remote_authority_service.py`, this WS-04 block, `docs/plans/MORTIMER_REMOTE_ACCESS_PLAN.md`, and `docs/roadmap-log/2026-10-31-ws04-r3-21-frozen-vector-refinement-design.md`. No production source, native owner, frozen fixture/legacy adapter, other workstream, identifier or model changes. The clean base is published `fff9fe8af59ec48e3e911cc0108ec7b0878a8547`; actual main `5310d1a9305035f43143fcffad6161619281f475` is already an ancestor (merge reports up to date). Fetch of the local handoff origin succeeds but supplies no `origin/main`; the verified actual main object is used explicitly, without invented ancestry. Existing branch-local coordinated ownership remains effective. Fresh local target and worktree checks show no competing edits to these four paths. Detailed design and exact response relations are in the existing R3.21 log. Next: retain the accepted immutable candidate and review the separate next-boundary design before source adoption or further publication. External displays stay deferred; UI/live/security gates remain separate.

### Local merge-main validation — 2026-11-06

Codex merged main `e782048965db98c397398077b9965bde5d6b7108` into #290 head `85bc736eff6311943bce77dfe769b683ec9d944d` locally, preserving both documentation histories. No push, PR-state change, PR merge or operational action is authorized. All five admission-core inputs still match the exact Kimi-reviewed SHA-256 values. Validation of the combined source has two failing roadmap snapshot tests: the union contains 262 log files, above the unchanged 255-file bound; neither logs nor safeguards were removed. Other validate.yml gates passed locally; PhoneCore executed 67 tests with one prerequisite skip and zero failures. Full counts and limitations are in the canonical remote plan. Next: larry/coordinator decide the bounded log-capacity follow-up and authorize publication separately; no acceptance checkbox changes.

**Merge record (Claude, 2026-11-06):** Larry merged #290 at head `7d12cc2493a05ea7f96cb4fc18683deab945f0d8` as `137c6689d2d18f3765003aae1eeb610bd8945b0a` (02:37 UTC). Validate on that head finished after the merge and failed only the same two roadmap log-cap tests (7,774 passed). Codex's #312 then raised the cap; #312's head, which contains `137c668`, passed all five checks before it merged as `0a11a86`.

### Historical conformance boundary design claim — 2026-10-31 (superseded by adoption below)

Coordinator requests design-only analysis while immutable command candidate `68eb03b33fe5496631ce4a4a308004f4d29d7a0e` is independently reviewed. Owner `codex`; Where `codex/ws04-r321-boundary-design-20261031`, isolated from that unchanged candidate. Effective documentation scope: this WS-04 block, the existing `docs/plans/MORTIMER_REMOTE_ACCESS_PLAN.md`, and `docs/roadmap-log/2026-10-31-ws04-r3-21-frozen-vector-refinement-design.md`. Fresh local checks show the three target blobs match the clean candidate and no source edits or competing changes in this lane. Actual main `5310d1a` remains an ancestor; the recorded local-handoff-origin exception is unchanged. This claim precedes design edits. Scope: explain all 107 remaining unchanged markers, raw-facade versus trusted-call boundaries, and recommend an exact next offline source claim/acceptance map. Effective claim `c5b45e1881b14a032be36822250defd85efa8685` precedes the analysis in the existing R3.21 log. Independent review of `68eb03b3` is now bounded-accepted (407 tests/644 subtests, zero skips, eight translated rows); that immutable candidate is preserved. Historical eight-file proposal, now expanded to ten, remains unadopted: the original six paths plus `jarvis/bot/phone_admission_store.py` and `tests/unit/test_phone_admission_store.py` for monotonic consumption checks and owner-thread local ticket reclamation. B01–B15 and the lifecycle revision specify post-worker cleanup, retained peer/output deadlines, exact receipts, full lock phases and ticket bounds; independent design review precedes source adoption. The ordinary-owner correction additionally proposes `macos/MortimerHost/Sources/PhoneRemoteAuthority/PhoneRemoteAuthorityOwner.swift` and `macos/MortimerHost/Tests/PhoneRemoteAuthorityTests/PhoneRemoteAuthorityProcessTests.swift`: bounded normal-v4 owned-child termination/reap with singleton retention, revised B11 and new B16. No channel/ASGI-runtime scope is added. Source adoption and fresh native build/process validation remain pending. Runtime/test/native/frozen changes and publication are excluded; any proposed source adoption remains separate. Preserve fail-closed/uncertainty semantics and the one-final-merge plan, with external-display and live/security gates unchanged.

### Adopted offline proof-to-voice source claim — 2026-10-31

Owner `codex`; Where `codex/ws04-proof-voice-brokerage-20261031`; status: independently bounded-accepted at `e2a3892f`; publication pending. Coordinator adopts independently accepted design `ad376278e633977e4664a2212a1deab48cc13233` / tree `dea6f6a49dddf464418e5c7c514e705ed057b04d`. Fresh isolated checkout is clean and all ten target blobs match that design; accepted command candidate `68eb03b3` is preserved. Effective source Scope is exactly: `jarvis/bot/phone_remote_connection.py`; `jarvis/bot/phone_remote_service.py`; `jarvis/bot/phone_admission_store.py`; `tests/unit/test_phone_remote_connection.py`; `tests/unit/test_phone_remote_service.py`; `tests/unit/test_phone_remote_authority_service.py`; `tests/unit/test_phone_remote_asgi.py`; `tests/unit/test_phone_admission_store.py`; `macos/MortimerHost/Sources/PhoneRemoteAuthority/PhoneRemoteAuthorityOwner.swift`; `macos/MortimerHost/Tests/PhoneRemoteAuthorityTests/PhoneRemoteAuthorityProcessTests.swift`. Documentation remains this WS-04 block and existing remote plan/R3.21 log. This claim precedes source edits. Implement B01–B16, including bounded terminal wake for `_wait_worker=True` without fabricated worker completion, retained proof lifetime, owner-worker exact cleanup, store-owned monotonic tickets and ordinary-v4 bounded native reap. Five-second caller failure and subsequent 2,500 ms native cleanup are distinct; uncertainty retains singleton ownership. No frozen/channel/ASGI-runtime/other-owner scope, publication/merge, real credentials/content/Keychain/network/security/install/model change or display test is included. Effective claim `f55b1ac542ae6860652d09b1c291490678da6707` precedes corrected source `bfe801c5f418fb4f5d8be34460718d25436c15df`. Updated 2026-11-01: 435 Python tests / 701 subtests, 28 scoped native tests, zero skips; ordinary TERM/KILL reap, exact held-lock uncertainty, seven signout/expiry/disconnect boundaries and same-PID recovery/65 retired lifetimes are covered. Independent review of `9171c7d8` required stale-output, stale-watchdog-deadline and partial native receipt corrections; all three are implemented with deterministic regressions. Next: review the clean public-parent candidate and obtain separate publication authorization. Fresh independent build, exact-binary tests and unlocked aggregate closure are recorded in the existing R3.21 log; earlier failures remain historical. V4 brokerage does not alter the eight translated v3 rows/six markers/107 open/zero exact-vector coverage ledger.

**Publication preparation — 2026-11-01:** Existing WS-04 scope/branch and three-document claim remain effective; fresh local checks found no competing edits. Verified PR290 head is `fff9fe8a`, main `5310d1a` is already an ancestor. Only evidence wording changes after accepted `e2a3892f`; runtime/test/frozen inputs remain exact. The local clean commit must have that public head as its sole parent and exclude intermediate ancestry/private packets. No push or merge is authorized by this preparation.

### Current offline acceptance and inherited claims

| Accepted milestone | Immutable source | Exact inherited scope |
| --- | --- | --- |
| R3.24 recovery | `04afff4c4a4594c9bd1182a10ba45bb6a1fc0986` | 13 paths, including proof-login amendment; no live restore/WS-17 script authority. |
| R3.23 snapshot/resume | `b4ae7740719f45e4dd81ad3f4917c789c608f57c` | Amended 16 paths; bounded synthetic historical results and A/B isolation. |
| Five typed card actions | `a121dfb06385702b82a18041d7d974ab40877ee9` | 22 paths, WS-04/17/30 split 7/4/11; mobile-only synthetic effects. |
| Proof-bound connection | `bd90884830b47e26a1b90ba8b8971b73eedbc728` | Nine paths, effective claim `f99e261b7d9e1afc4e3d7ba9ac5bf25ef79124b3`; independent 403 Python/639 subtests, 24 native, 67 PhoneCore, zero skips. Six standalone probes are uncounted. |

Earlier authority/service/proof and prepare/pending milestones remain accepted within their recorded scopes. All exact designs, trees, claims and paths are linked below.

The [historical block with private evidence paths generalized](docs/plans/MORTIMER_REMOTE_ACCESS_PLAN.md#ws04-roadmap-history-1901e6ec) and canonical contracts preserve all exact scopes/designs/trees, reservations, invariants, failed candidates and receipts. No accepted requirement is reopened. Proof-only login, incarnation/lifetime/lock/terminal rules, owned cancellation/drain and durable recovery guarantees remain binding. No production, external-action or whole-host antirollback scope is added.

**Aggregate evidence:** historical `1901e6ec` initial/rerun counts remain distinct from a green full run. Repair candidate `82b9f78b` now passes one full unit run: 7,618 tests/731 subtests, 11 skips. Separately, unchanged `1901e6ec` passes independent unlocked-desktop verification: six focused visibility cases; full MortimerHost 587 passed/three external-display skips, plus 24 native passes. The focused six are not additive. No source/settings fix was needed. Exact earlier counts, final receipts and remaining exclusions are in the plan/log; the independent reviewer receipt for `1901e6ec` is retained locally.

**History/public boundary:** the archive retains every old field/checklist/claim/reservation and public/CI observation, labelled historical. Local `4e2152ec` matches supplied public `39208d18` tree `e31cdf9531908b0186d71d7af573da877e7b7eec`; complete hashes remain in the archive. This proves neither ancestry nor freshness. No evidence or open gate is removed.

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
<summary>WS-03 — Skills Workspace and skill creator · Codex (overall) + Claude (offline package adapter)</summary>

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

- **Owner:** `codex` (overall workstream, acceptance and historical attribution retained); `claude` (bounded offline instruction-package adapter only, moved from Codex by Larry's explicit authorization in his Claude Duet channel on 2026-11-03 at 21:04:42 UTC ("Yes, move and build"), answering whether Claude should move the offline skill package adapter from Codex to Claude and build it)
- **Status:** landed via [#300](https://github.com/Larryfix71566/jarvis-voice-ai/pull/300) at merge commit `f874cf1a757b03d98336aca36ef08fb13c15c7a6` (Claude, 2026-11-03; merged by Larry before an independent exact-source review; source only, not installed, activated or live-accepted): new `jarvis/skill_package_adapter.py` (inert `skill_package_compatibility` report, schema 1, `p0-text-v1`) with 121 offline tests in `tests/unit/test_skill_package_adapter.py`; no fixture files were needed. It returns a package-only payload only when every check passes, never a ready/approved/active state, and changes no existing source, registry, config or skills package. Independent review of the merged source (Kimi, posted by Larry on #302, 2026-11-05) found two fail-open gaps: baseline registries that the runtime reader rejects could still yield a payload, and a missing receipt or an unknown passing validator check was accepted. Claude's fix landed via [#304](https://github.com/Larryfix71566/jarvis-voice-ai/pull/304) at merge commit `5cd7532c56cca820925a35acefc3db2db2db18ff` (merged by Larry on 2026-11-06 at 02:30 UTC, after all five CI checks passed on head `723ad07` and before Kimi's re-review): the adapter now applies `read_skill_registry` semantics to the baseline bytes in memory and requires a real, bound receipt with only known checks. Claim history: claimed by Claude (2026-11-03): bounded offline instruction-package adapter on `claude/ws03-offline-package-adapter-20261103`, implemented against the unchanged 2026-10-22 contract in the canonical plan and the §3 report reservation. Codex's stalled delegated-author lane (no applied source; attempt-2 outcome never recorded) is superseded, not resumed. Prior status follows as history: claimed: bounded offline instruction-package adapter, using merged #251 P0 unchanged. Source starts only after this registration lands on main. Claude Max is the delegated patch author for the new adapter/test/synthetic fixture files only; Codex retains review, application and publication ownership. Historical P0 #251 merged as `b3a5fa1` (reviewed `e13fc89`, static approval, 346 offline passes and five CI checks; receipt in the WS-03 log); #258 was its documentation-only lifecycle correction; SW-B/C remain the only accepted full gates (2/12). No installation, activation or live acceptance follows from this claim.
- **Implemented by:** Codex
- **Remaining work / acceptance:** Codex; Larry for human review and physical acceptance
- **Model version:** not recorded; do not infer from system name.
- **Where:** `claude/ws03-offline-package-adapter-20261103` (adapter implementation, to start from main after this claim lands). Historical: `codex/ws03-offline-package-adapter-20261022` at `369057b`, docs-only, no adapter source; left untouched. Merged #251 head `e13fc89` and #258 head `aadb01e` remain frozen historical receipts; their branches are not active implementation lanes.
- **Plan:** `docs/plans/MORTIMER_SKILLS_WORKSPACE_IMPLEMENTATION_PLAN.md`
- **Scope:** Claude's claim (2026-11-03): the same three paths only, new `jarvis/skill_package_adapter.py`, new `tests/unit/test_skill_package_adapter.py` and bounded synthetic `tests/fixtures/skill_package_adapter/**`, authored, tested and published as a draft PR by Claude in its own clone. The read-only dependency list, report identities in §3, the bounded behavior and offline acceptance list in the canonical plan's 2026-10-22 claim section, and every exclusion below are unchanged. Documentation: this WS-03 block, dated WS-03 progress in the canonical plan and WS-03 `docs/roadmap-log/` entries. Original scope follows as history: New `jarvis/skill_package_adapter.py`, new `tests/unit/test_skill_package_adapter.py`, and bounded synthetic `tests/fixtures/skill_package_adapter/**` only. Official authenticated Claude Code Max may author a returned patch for exactly those files from a minimal sanitized repository packet with tools disabled and no checkout access; Codex alone applies, reviews, tests and publishes. Read-only dependencies are `jarvis/agent_skills.py`, `jarvis/skill_compatibility.py`, `jarvis/skill_catalog.py`, `jarvis/skill_authoring_validation.py`, `jarvis/skill_service.py`, `sandbox/artifacts.py` and `jarvis/selfedit/skill_policy.py`; no changes to existing source/tests/fixtures, skills packages, registry/config, provider/controller/Base/delegate, admin/native UI or sandbox runtime. Documentation: this WS-03 block, its section 3 report reservation, canonical plan and existing WS-03 log/receipts. Explicit delegated assignment applies only after the matching main claim; any wider dependency edit requires coordinated scope amendment. Later script/service/resource and invocation/tool-policy adapters remain separate work, not silently omitted or authorized here.
- **Next step:** kimi: re-review the merged fix (#304 head `723ad07`, merged as `5cd7532`) against the two 2026-11-05 findings; any new finding becomes a new fix. Installation, activation and every SW-A–L gate remain separate decisions.
- **Updated:** 11-06 (review fix landed via #304 at `5cd7532`; merge commit recorded; Kimi re-review still owed). Prior: 11-05 (Kimi review findings on #300 fixed by Claude on a review-fix PR). Prior: 11-03 (Claude offline package adapter landed via #300 at `f874cf1`; merge commit recorded; claim landed via #298 at `9d7982c`). Earlier 11-03: adapter moved to Claude on Larry's authorization; source not started. Prior: 10-22 (offline package-adapter claim; source implementation not started)


**Claim boundary:** Larry's current full-program direction authorizes this bounded next slice and relevant repository context through the existing Claude Max subscription. This documentation registers the precise delegated patch-author lane without reassigning overall Codex or human acceptance ownership. Source waits for this claim on main; Claude receives no Codex checkout access, tools, persistent grants, direct paid API route or fallback. The coordinator remains sole merge owner. No installation, activation, service/model change or live-provider/VM run is authorized.


- **Aggregate draft — 2026-10-27 UTC:** Dispatch/history-only snapshot from `369057b`; no adapter source in this aggregate. [Full included/deferred manifest](docs/roadmap-log/2026-10-27-unmerged-integration.md).

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
<summary>WS-23 — Acceptance Verifier within Systems · Kimi independent review APPROVE</summary>

**Workstream:** Extend Systems with a verification role, starting from a repeatable checklist and existing diagnostics. Reuse Council review and independent VM checks; keep live-Mac and physical evidence separate. It observes and evaluates criteria; it is not a repair agent or release authority. The expanded October 22 all-current-and-future-roadmap dispatch permits the isolated offline contract below after its main claim; a new automated profile and runtime rollout still require current acceptance and their existing gates.

### Requirements and dependencies

- Checklist-first adoption during current acceptance; a new automated profile waits for completed acceptance, explicit implementation dispatch and existing access/privacy prerequisites.
- Read only admitted build identity, approved diagnostics, test outcomes and receipts; bind each observation to an explicit criterion and tested build. Return passed, failed, blocked or untested, with supporting evidence.
- No code edits, weakened tests, waived criteria or release authorization. A successful tool call cannot establish feature success.

### Acceptance checklist — future increment

- [ ] Detect a seeded feature failure and return failed with the matching criterion/evidence.
- [ ] Reject a stale receipt and a receipt for the wrong build as current proof.
- [ ] Mark missing physical hardware blocked or untested; do not infer a pass from VM/CI success.
- [ ] Demonstrate that verification cannot repair code, change criteria or authorize a release.

- **Owner:** `codex` retains implementation accountability and original authorship; `kimi` owns the bounded independent exact-source review; existing acceptance owners unchanged
- **Status:** landed via [#281](https://github.com/Larryfix71566/jarvis-voice-ai/pull/281) at merge commit `dcdcad733d20b8cf17af2b548fd509799e003452` (documentation-only independent review): Kimi APPROVE for exact Codex source/test blobs at review base `233995cb9fb0f9a5e1f2fd35611b4cfa1b5e0af8`, byte-identical to author `1b07fd882ba0246768138d110fe8003a91a36730`. Evidence: 25 focused tests/63 subtests and 14 independent adversarial checks pass; no blocker, should-fix or nit finding. Post-merge verification on main `97ffb3bb19ce29a9c4e6768a481389ac147cd691` found unchanged source/test blobs; 32 focused/manifest tests with 63 subtests and 25 stdlib unittest methods passed. All five #281 checks passed. Codex contract source landed through #278 (`61870ff`); no runner, runtime wiring or product acceptance
- **Implemented by:** Codex authored the unused pure contract and synthetic tests at `1b07fd882ba0246768138d110fe8003a91a36730`, adopted in #278. Kimi independently reviewed the exact merged source without authorship or source repair
- **Remaining work / acceptance:** Preserve Kimi's source-only APPROVE and its limitations. All four acceptance criteria remain open; this pure supplied-metadata contract proves neither authenticity nor installed/physical/human acceptance. Future source changes require a new immutable review; runtime/profile rollout remains separately gated
- **Model version:** not selected; choose eligible models by workload/privacy during planning
- **Where:** review evidence on `kimi/ws23-evidence-contract-review-20261028`, landed via #281 at `dcdcad733d20b8cf17af2b548fd509799e003452`; merged source is on main via #278
- **Plan:** [Canonical plan](docs/plans/MORTIMER_ACCEPTANCE_VERIFIER_PLAN.md); existing historical requirements and acceptance gates retained
- **Scope:** Review-only: read `jarvis/acceptance_evidence.py` and `tests/unit/test_acceptance_evidence.py` at a recorded immutable main revision; run existing offline tests and bounded synthetic scratch checks. Write only this WS-23 block, `docs/plans/MORTIMER_ACCEPTANCE_VERIFIER_PLAN.md` and WS-23 entries under `docs/roadmap-log/`. No source/test/fixture edits, runner/VM, production importer, Systems/prompt/tool, storage, WS-24, criteria, provider/config/scripts/native/shared-test or other-owner edits. Codex retains source accountability; any repair requires a separately coordinated scope amendment
- **Next step:** codex: preserve the independent verdict and source accountability; coordinate any separately claimed remediation and rereview. larry: retain acceptance/release authority; no implementation merge, deployment or acceptance is advanced by this review
- **Updated:** 10-28 (#281 merged; post-merge source identity and offline tests verified on main `97ffb3bb19ce29a9c4e6768a481389ac147cd691`; all acceptance criteria remain open)


### Prior ownership/intake checkpoint (preserved history)

- **Previous Owner:** `codex` for roadmap intake only; implementation owner unassigned
- **Previous Status:** parked: proposed by Larry 2026-10-17; no implementation or activation authorized
- **Previous Where:** documentation on `codex/roadmap-status-20261017` (PR #211); no implementation branch
- **Previous Scope:** Documentation only in this intake. Future code paths, existing-state reuse, schema/migration reservations, feature gate and rollback must be reviewed before claim; no new service, tool grants or migration number reserved here
- **Previous Next step:** larry: finish current acceptance and dispatch implementation ownership when ready; assigned planner: map existing components and prepare the bounded design, tests and rollback before code
- **Previous Updated:** 10-17 (consolidated enhancement intake; unimplemented and unaccepted)


- **Historical aggregate draft — 2026-10-27 UTC (subsequently merged via #278):** Unused contract/tests from `1b07fd8` assembled for independent exact-source review; no runner or product acceptance. [Full included/deferred manifest](docs/roadmap-log/2026-10-27-unmerged-integration.md).

</details>

<details id="ws-24">
<summary>WS-24 — Durable task ownership and restart recovery · Proposed</summary>

**Workstream:** Extend existing SQLite, run logging and durable notification paths with one authoritative overall-task lifecycle. A task is distinct from its individual agent runs, attempts and retries. This is the highest-priority new foundation. The expanded October22 all-current-and-future-roadmap dispatch permits the isolated offline contract below after its main claim; product acceptance remains a separate prerequisite for later runtime rollout.

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

- **Owner:** `codex`; retained dispatcher owns the isolated offline recovery contract; existing acceptance and other source owners remain unchanged
- **Status:** landed: isolated offline transition contract via #270 (`40b24b1`) at source `38b0fcd`; the PR records independent APPROVE_SOURCE_DELTA and 32 synthetic tests. Historical publication validation failed (run 39875623174). Landed via this PR (documentation-only verification): Kimi verified exact combined main `5581d4f913d21cbc69a707905a9898780b4a1e3c` locally on macOS, including 7,085 unit passes/11 skips/29 subtests, 197 integration passes/four skips and all other local publication-equivalent checks. Exact-head PR CI is a separate publication receipt. No persistence, runtime activation or acceptance is claimed.
- **Implemented by:** Documentation preparation from #255 and merged claim #263; isolated `jarvis/task_recovery.py` plus 32 stdlib offline contract tests, with no production importer or storage wiring
- **Remaining work / acceptance:** Preserve the historical failed validation alongside Kimi's local combined-main evidence and this PR's exact-head CI. The local Mac pass does not by itself prove the historical Ubuntu worker-boundary failure resolved. All four future acceptance criteria remain open; pure transition tests cannot prove durable storage, atomic cross-process exclusion, real restart recovery or user-visible delivery.
- **Model version:** not selected; choose eligible models by workload/privacy during planning
- **Where:** source on main via #270 (`40b24b1`), source `38b0fcd` on historical `codex/ws24-recovery-foundation-20261022`; documentation-only verification on `kimi/ws24-combined-main-verification-20261026`; no ongoing storage/runtime claim.
- **Plan:** [Canonical plan](docs/plans/MORTIMER_DURABLE_TASK_RECOVERY_PLAN.md); existing historical requirements and acceptance gates retained
- **Scope:** Larry authorized Kimi on 2026-10-26 to record documentation-only combined-main verification in this WS-24 block, the existing canonical plan and a WS-24 `docs/roadmap-log/` entry. No source or test edits. Existing source scope remains only `jarvis/task_recovery.py`, `tests/unit/test_task_recovery.py` with inline synthetic fixtures, this WS-24 block, existing `docs/plans/MORTIMER_DURABLE_TASK_RECOVERY_PLAN.md`, and WS-24 `docs/roadmap-log/` entries. No storage, runlog, notices, delegation, creator, bot/admin, sandbox, provider, config, scripts, native, other-owner plan/test or production importer edits
- **Next step:** codex / coordinator: preserve exact source review, historical failed CI and Kimi's bounded local/publication evidence; separately register any future persistence/runtime scope and reservations. Existing product acceptance and release gates remain open.
- **Updated:** 10-26 (Kimi combined-main verification recorded under Larry's dispatch; no source or acceptance advance)


### Prior ownership/intake checkpoint (preserved history)

- **Previous Owner:** `codex` for roadmap intake only; implementation owner unassigned
- **Previous Status:** parked: proposed by Larry 2026-10-17; no implementation or activation authorized
- **Previous Where:** documentation on `codex/roadmap-status-20261017` (PR #211); no implementation branch
- **Previous Scope:** Documentation only in this intake. Future code paths, existing-state reuse, schema/migration reservations, feature gate and rollback must be reviewed before claim; no new service, tool grants or migration number reserved here
- **Previous Next step:** larry: finish current acceptance and dispatch implementation ownership when ready; assigned planner: map existing components and prepare the bounded design, tests and rollback before code
- **Previous Updated:** 10-17 (consolidated enhancement intake; unimplemented and unaccepted)

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
- **Status:** landed documentation via this reconciliation: October 27 source/PR/local-work review against `ae035de`, restoring evidenced merge-collision losses and correcting current provenance only. Earlier #150/#151 review remains historical.
- **Implemented by:** Codex (review and roadmap update)
- **Remaining work / acceptance:** None for this documentation review. Product deployment and live acceptance remain in their own workstreams.
- **Model version:** not recorded; do not infer from system name.
- **Where:** `docs/local-roadmap-review-20261027`, isolated documentation worktree based on `ae035de`; prior review on main via #150/#151.
- **Plan:** this bounded review is tracked in this block and §8; no new implementation plan.
- **Scope:** `ROADMAP.md` only for edits; repository, plans, receipts, CI and PRs are read-only evidence.
- **Next step:** codex: obtain independent review and exact-head checks for this bounded documentation correction; the serial coordinator may merge only after those gates pass under Larry’s approval. Existing implementation and acceptance owners retain all other work.
- **Updated:** 10-27 UTC (Larry-dispatched reconciliation; this dated row and top summary are the review log; no source, owner, scope or product acceptance changes)

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

**WS-04 proof-connection reservation (2026-10-31, before source edits):** `mortimer.phone-connection.v1` with closed preauth operations `auth.challenge` and `auth.prove`, only on the separately constructed default-disabled offline ASGI adapter. Existing `mortimer.phone-remote.v1` inventory and `/ws/phone-remote` path remain unchanged. No new port, native authority operation, configuration/environment key, migration, credential or server mount. Exact schemas and limits are the accepted connection design.

**WS-04 phone 0.2 branch-local reservations R3-02, adopted 2026-10-29:** Parent coordination adopts the independently accepted documentation on `codex/ws04-phone-admission-core-20261029` in PR #290 under Larry's authorized remote-access goal and narrow one-final-merge exception. These reservations and the two-file R3-S1 fake-store claim landed on main via #290 at merge commit `137c6689d2d18f3765003aae1eeb610bd8945b0a` (2026-11-06). They are not applied: migration `0037_phone_remote_authority` is not registered in `jarvis/db.py`, no code reads `JARVIS_PHONE_REMOTE_ENABLED`, and nothing is live-accepted. Exact contracts and dated collision evidence are in the existing [remote plan Addendum R3](docs/plans/MORTIMER_REMOTE_ACCESS_PLAN.md#addendum-r3--phone-access-02-reservation-proposal-2026-10-29). Reserve migration `0037_phone_remote_authority`; tables `phone_remote_meta`, `phone_remote_devices`, `phone_remote_grants`, `phone_remote_sessions` and their exact columns in R3.3; config `JARVIS_PHONE_REMOTE_ENABLED` default false; protocol `mortimer.phone-remote.v1`; internal WS-17-owned restore seam `phone_remote_restore_v1`; protected Keychain service `com.mortimer.phone-authority`, account `host-generation-v1`; separate conditional vault slot `PHONE_REMOTE_STORE_KEY`, never the anchor or an existing token item. No port, launchd label, allow-list privilege, credential creation or live setting is reserved/authorized. The protected host generation and login-incarnation fence must not roll back with SQLite/release snapshots. Whole-host/anchor rollback remains fail-closed trusted recovery, not claimed solved. Claimed next source scope is two new files only: `jarvis/bot/phone_admission_store.py`, `tests/unit/test_phone_admission_store.py`, disposable SQLite/fake anchor only; no production migration registration. Recheck main and PR head before source edits; reconcile any new collision before proceeding. Larry's narrow one-final-merge exception allows exact reviewed branch-local claims in this integration PR, not overlapping owner scope or waived security/review/live gates.

**WS-04 R3.16 adopted identifiers (2026-10-30):** reserve local child protocol `mortimer.phone-authority-channel.v1` and singleton lock inode path `~/Library/Application Support/com.mortimer.phone-authority/owner.lock` for the adopted native-owner claim. The channel is only an inherited socket-pair capability, not a network endpoint. This reserves names only; no real port, launchd label, migration, config key, allow-list privilege, Keychain item, credential, lockfile provisioning or startup behavior is included. Tests use a separately created temporary lock inode and test-only launch configuration.

**Coordinator-adopted WS-04 R3.10 offline path identifier:** `/ws/phone-remote` is accepted only as a path identifier in the injected, in-process ASGI test harness for the default-off adapter described in remote-plan §R3.10. It reuses the R3.9 service and `JARVIS_PHONE_REMOTE_ENABLED` semantics; this does not reserve a port or allocate/mount a runtime route. The adapter module does not edit `server.py`, construct production dependencies or start a listener. No bind, route enablement, credential, or live permission follows from adopting this identifier.

**R3.3a host-identity amendment (2026-10-29; adopted branch-locally):** The independent fake-store review of source hash `4b5a190237d7dc14d111176c5364ee75dde53f39c8c7ee83568ad096e79c6df7` reported that replacing only the anchor host ID HOST-A→HOST-B at equal generation/login-counter, while leaving SQLite unchanged, admitted an old-host ticket. Independent documentation review ACCEPTED the proposal at exact pre-adoption ROADMAP/plan hashes recorded in Addendum R3; parent coordination adopts it on this branch only. The schema adds `host_id` to `phone_remote_meta` and `phone_remote_sessions`; anchor/meta/session/ticket/peer bindings must match and equal-counter cross-host tests must deny. This is a synthetic finding, not a production vulnerability or corrected-store source acceptance. No migration execution or real Keychain change is authorized; `0037_phone_remote_authority` remains unregistered and unapplied.

**WS-03 offline package report reservation, 2026-10-22 (before implementation):**
Internal inert report `kind = skill_package_compatibility`, `schema_version = 1`,
`adapter_version = p0-text-v1`; fields `source_digest`, `inputs_digest`,
`baseline_digest`, nullable `candidate_digest`, nullable `validation_snapshot_digest`,
`report_digest`, `parser_fingerprint`, `inventory_digest`, `dispositions`,
`blockers`, and `validation`. SHA-256 identity uses deterministic canonical framing fixed by schema version 1; a framing change requires a schema-version change:

- `source_digest`: every original source record, framed by logical path, mode and bytes; includes original source manifests/file inventory.
- `inputs_digest`: all reviewed sidecar/provenance/license/matcher records, target slug and selected profile, even when no payload can be produced.
- `baseline_digest`: supplied immutable Candidate fingerprint, including its protected registry.
- `candidate_digest`: returned package-only payload fingerprint, no config/registry or baseline files. Null on failure/cancellation.
- `validation_snapshot_digest`: full temporary validation snapshot fingerprint (unchanged baseline plus package and scoped matcher fixtures); the nested validator receipt’s `candidate_digest` binds this snapshot, not the returned payload.
- `parser_fingerprint`: exact content digests of the enumerated read-only parser/catalog/validator/Candidate/service/policy dependencies; adapter code identity is also bound in report validation evidence alongside the profile version.
- `inventory_digest`: deterministic sorted static configured-tool names and completeness facts observed through the existing host helper, compared before/after validation. It is not a source-file or caller-supplied dependency inventory; no alternative dependency inventory is accepted.
- `report_digest`: canonical complete report excluding itself and any raw source bytes; nested validation evidence is included.

Source evidence is a separate bounded immutable bundle, never the content-free
report. On a secret-scan refusal, omit raw evidence and return only digests,
ordinals and fixed codes. Dispositions cover every declared feature/file;
unsafe or unrecognized labels use ordinals and fixed codes, never raw keys,
text or host paths. Unknown schema versions and changed bound identities
invalidate reuse. No `ready`, `approved` or `active` state is emitted;
authentication/runtime readiness remain unknown and inventory evidence is static only.
The report is not approval, owner/session proof or an activation token. No
HTTP/native wire, request ledger, DB migration, config key, port, credential,
service, tool grant or model route is introduced. This reservation does not
waive the existing package/source scanner or authorize ignored semantics.

**WS-05 harness foundation integration reservations, 2026-10-22:** Adopt the existing frozen candidate names from unmerged #241 without merging its stale ownership: GET `/api/status/harness-models`, explicit POST `/api/status/harness-models/refresh`, local `harness-model-brief.json` schema_version 2, native instruction package `harness-model-evaluation` and descriptive contract `mortimer.harness-model-management.v1`. Reuse existing `status_models`, mcp-status, daily_status outbox and status kill switch; no extra MCP tool. Scheduled paths read cached evidence/local metadata only; explicit refresh fetches fixed credential-free official documents. No migration, environment/config key, port, launchd label, allowlist privilege, account access or automatic model adoption.


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

**WS-05 subscription-retirement reservation (2026-10-20; expanded 2026-10-21):** `JARVIS_LLM_ACCESS_MODE` with explicit `legacy` / `subscription_only` / `direct_apis_disabled` values, used by one central provider-access policy and preflight. Larry's October 21 clarification preserves explicitly selected OpenRouter while disabling direct OpenAI/Anthropic. October 22 clarification: selective mode retires only direct OpenAI/Anthropic and recognizes other APIs through protected endpoint identity (including OpenRouter/Moonshot and the existing SAYGM validator), validated source-policy execution and existing route/authentication/budget gates, plus existing subscription/local routes; it creates no fallback or privacy grant. Subscription-only retains its stricter no-API meaning. Existing subscription CLI/tool/capability settings retain their names. No new port, launchd label, credential or database migration. Services remain reversibly stopped until acceptance owns a verified guarded restoration.

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
| 0037 | `phone_remote_authority` | WS-04 | R3-02 reservation; landed on main via PR #290 (`137c668`); not registered in `jarvis/db.py` or applied |
| 0038+ | free | — | recheck current main and branch claims before allocation |

Renumbering completed in the main integration. Read-only production verification on 09-28 confirms `0028`–`0034` and `0036` are applied under the names above. **Do not renumber them again.** `0035` remains reserved for MAIL.

**Self-edit allow-list rows:** owned by `docs/plans/ALLOWLIST_SEQUENCE.md`. That rule is unchanged: every allow-list change is a human commit.

**Config keys reserved for WS-04 R2:** `JARVIS_REMOTE_BIND_ENABLED` (default false, independent of `JARVIS_AUTH_ENABLED`). Local bearer authentication may be enabled while this key remains false; only an explicit future remote-access decision may set it true. No new port or migration is reserved.

**Config keys reserved for WS-05, 2026-10-05:** `JARVIS_CODEX_SUBSCRIPTION_CAPABILITY_RECEIPT` points to a secret-free, version/model/binary/catalog/arguments-bound capability receipt; the existing no-tools verification flag alone does not establish capability. `JARVIS_SUBSCRIPTION_TOOLS_ENABLED` defaults false and gates a provider-native bridge whose tool operations must pass through Mortimer's permission and sandbox boundary. `JARVIS_SUBSCRIPTION_TOOL_CAPABILITY_RECEIPT` points to separate provider/version/schema/protocol tool acceptance; the tools flag alone does not establish native tool capability. Request-owned temporary Unix sockets/configuration have no fixed port or launch label. These reservations do not enable either route in production. No port or migration is reserved.

**WS-05 workload quality key reserved before implementation, 2026-10-05:** `model_access.defaults.minimum_quality_tier` and `model_access.workloads.<name>.minimum_quality_tier`, with the existing registry tiers `economy`, `mid`, `frontier`. Apply the standing Sonnet-or-better (`mid`) floor to ordinary non-voice specialists and private background work; planning keeps its frontier floor, while voice and the documented council tier-1 pool retain their legitimate economy choices. Explicit or saved choices below the workload floor are unavailable; they are never silently replaced.

**WS-05 optional workload-limit keys reserved before implementation, 2026-10-06:** `model_access.defaults.max_output_tokens_per_call`, `.deadline_seconds`, `.max_estimated_spend_usd_per_task`, and corresponding `model_access.workloads.<name>` keys. Absent/null values retain existing behavior; no production limit is assigned by this reservation. Spending is configured-price admission, not a guarantee of provider charges or account overage settings. Native routes refuse unsupported output/spend ceilings; enforceable deadlines remain available. Per-parent reservation state is separate from actual usage accounting in costs.db inline tables `model_task_budgets` and `model_call_budget_reservations`; no jarvis.db migration is needed. No port, launch label, credential reference or allowlist change is reserved.

---

**Config keys reserved for WS-13 P1, 2026-10-10 (plan §R.5 D6, §R.10.18):** vault names `MAIL_ATT_USER`, `MAIL_ATT_SECURE_MAIL_KEY`, `MAIL_GMAIL_USER`, `MAIL_GMAIL_APP_PASSWORD` (declared in `mcp-mail`'s `optional_env`; values only via `python -m jarvis.vault set`), and `JARVIS_MAIL_ENABLED` (default true, read only by `mcp-mail`). Migration `0035` stays reserved for P3 (`0035_brief`); P1 adds no migration.

**Config key reserved for WS-13 P3m, 2026-11-03 (plan §R.0f, §R.4 kill switches):** `JARVIS_BRIEF_ENABLED` (default true; read once at the `daily_brief` registration site in `jarvis/bot/pipeline.py`, which passes the same boolean to the menu and the prompt). `JARVIS_BRIEF_TIME` stays unreserved until the scheduled brief is claimed. Migration `0035` stays reserved for `0035_brief`; P3m adds no migration.

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


**WS-17 canonical held-deployment CLI reservation, 2026-10-21 (before implementation):** Human-only `scripts/deploy_main.sh` may accept `--install-held --approval-receipt PATH` (optionally the existing `--reuse-verification`), `--restore-local SNAPSHOT costs,vault` and `--rollback-held SNAPSHOT`. These are canonical operator ceremony flags, not Mortimer tools, an API, new settings/credentials, ports, launch labels or source authority. Base local restoration excludes admin and every inference service. Existing deny classification and authenticated helper remain unchanged. A frozen private copy of the same protected script owns held rollback; no alternate installer or legacy settings/database restoration.

**WS-17 native compatibility identity reservation, 2026-10-21 (recorded before implementation; fulfilled by #235):** Existing Claude Code `2.1.291 (Claude Code)` may join the exact native-runtime verified-version set only after actual installed-binary localhost positive and hostile-tool protocol evidence. This reserves no new model, route, tool privilege, config key, credential, port or launch label; exact workload/model/schema/identity receipts and all privacy/activation gates still apply.

**WS-05 harness evidence reservation, 2026-10-22 (claim-only):** Reuse existing mcp-status and daily_status outbox. The previously proposed extra MCP tool is withdrawn; reuse existing `status_models` with additive passive evidence. Reserve GET `/api/status/harness-models`, explicit POST `/api/status/harness-models/refresh`, local evidence report `harness-model-brief.json` schema_version 2, native skill `harness-model-evaluation` and descriptive contract `mortimer.harness-model-management.v1`. Default/scheduled paths read cache and local metadata only; explicit refresh fetches fixed credential-free official documents. Existing status kill switch remains binding. No migration, config key, port, launchd label, allowlist row, provider grant or runtime activation is reserved.

**2026-10-22 CI correction disposition:** The reserved `status_harness_models` tool is unused and not implemented. Reuse existing `status_models` unchanged schema with additive passive `harness_brief` output; no new MCP menu entry. Native authenticated endpoint/report/skill reservations remain. This resolves frozen40-tool integration without new authority.


**Adopted typed phone-card wire reservation (2026-10-31, WS-04/17/30):** reserve closed operations `results.view`, `results.select`, `results.pin`, `results.unpin`, `results.close`, `results.reopen` in the existing `mortimer.phone-remote.v1` envelope, exactly as the independently accepted typed-card design specifies. Reuse `read`/`action` scopes and existing status/reason enums; add no port, launchd label, config key, migration, credential or general console-action permission. These identifiers serve only the injected synthetic offline slice until separate production claims.

## 4. Conflict register

Open means not yet resolved. Each entry names who resolves it.

| ID | Conflict | Resolves | State |
|---|---|---|---|
| CX-29 | The release closure lanes (WS-34 to WS-36) touch files that other open rows also hold: `.github/workflows/validate.yml` (A1, B1, B5, C1b; WS-20 and WS-30 claim parts), `scripts/deploy_main.sh` (two lines in C1b; WS-17's bounded scope), `jarvis/bot/pipeline.py` (C3 emit sites and C7-py registration; WS-17 and WS-05 hold parts under CX-26 and CX-27), and the human-only `sandbox/**`, `jarvis/selfedit/service.py` and `config/self_edit_allowlist.json` (C1b, B3). | Larry approved the lanes 2026-11-11 02:35:41 UTC; the lane item's author coordinates with the other row before editing | Open. Lane work lands on `next`, so it does not collide with those rows on `main` until `next` merges at closure; conflicts at that merge are resolved by the lane item's author with the other row's owner and recorded here. Human-only files are patches Larry commits. |
| CX-28 | Old #241 is unmerged and its branch/scope no longer represents current main; #257 registered only the repair, not the inherited #242 foundation. | Larry current-program direction; Codex registers exact integration; sole coordinator merges serially | This supplement registers only the canonical inventory of frozen foundation hunks plus the #257 repair on the same active branch. Preserve WS-03 implementation/compatibility tests except the two named package inventory expectations; provider and WS-17 installation scopes remain theirs. #241/#242/#253 stay immutable inputs. Claim landing precedes any new broader source edit; owner conflicts return for coordination. Exact combined source review/CI precede serial integration. No model change, live inference, installation or activation is authorized. |
| CX-27 | WS-17 acceptance repair shares `pipeline.py` and potentially task cancellation/deduplication in `jarvis/agents/delegate.py` with active WS-05 subscription retirement. | Larry approved complete acceptance repair 2026-10-21; Codex sessions coordinate through parent | WS-05 retains all provider/runtime/authentication/model-access/billing changes. WS-17 may change only existing weather/request/console adapters and reporting; the committed WS-05 handoff in `504f911` permits acceptance delegate/Base/Registry edits, and `763bfe1` retains WS-05 provider-selection constructors. Reproduce before changing focus semantics. Parent reconciles final integration; do not deploy before migration readiness or concurrently with another release. No other ownership changes. Parent/acceptance confirmed the source-policy-only handoff on 2026-10-21: memory prompt assembly, accepted input/assistant appends, direct-tool result policy transport, clipboard/late/deferred injection and history rewriting; WS-05 may add per-run Base policy export and Delegate immediate/late policy transport while preserving stop-command parsing, pending-task controls/deduplication, terminal callbacks, weather-reuse checks, request identity and ContextVar restoration. Registry remains unchanged unless a new gap is reported. WS-17 source stays frozen; test a separate combined preview. No transfer of WS-17 weather/foreground/cancellation ownership. |
| CX-26 | Larry requests retiring direct OpenAI/Anthropic APIs in favor of subscriptions; WS-05 prior claim preserves legacy routing and excludes model/endpoint pins, while voice construction shares `pipeline.py` with WS-17. | Larry dispatch 2026-10-20; Codex WS-05 registration | This claim permits the bounded model-access and LLM-construction changes in WS-05, preserving WS-17 weather/cache/console/result logic and all protected-source, sandbox and acceptance requirements. No other owner is reassigned. Claim must land before runtime code. |
| CX-25 | WS-17 current-request foreground behavior changes the prior §7.2 no-jump rule/UI2-23 criterion while another result is being read; WS-28 covers cleanup only and WS-17's current branch is release-verification-only. | Larry approved the foreground exception and review-only publication at 23:44 UTC on 10-18; Codex prepares claim registration | Policy resolved by Larry: open only the result proven to answer the still-active explicit request, including fresh native cache reuse; background, superseded, stale/cancelled and unrelated arrivals retain reading focus and supporting-display ownership. Implementation claim pending main: `codex/ws17-current-request-arrival-20261018`. Review-only publication does not authorize merging this claim or any runtime PR. No runtime edits or deployment in this proposal. |
| CX-24 | Larry authorizes acceptance execution and reassigns the two merged #210 cleanup defects to Codex on 10-18; prior main has no matching acceptance branch/cleanup claim. | Larry explicit 20:08:26 UTC dispatch; Codex claim-only registration | Resolved ownership boundary: WS-20 owns acceptance documentation/evidence on `codex/acceptance-clearance-20261018`; WS-17 retains patch-only cross-review and independent release verification on `codex/ws17-release-verification-20261018`; new WS-28 owns only cleanup-race/fingerprint repair on `codex/sandbox-cleanup-repair-20261018`. WS-05 source/session semantics and every unrelated owner remain intact. Claims must land before code. Only this separate claim-only PR may merge on required checks; runtime repair merge and production deployment/restart remain separate decisions. |
| CX-22 | WS-17 roadmap first-arrival display needs the `agent_tool_result` observation projection in `jarvis/agents/base.py`, held by Codex WS-05. | Larry approved the bounded roadmap-only extension 10-17; Codex coordinates both scopes. | Approved and claimed on main through #217 (`ed21d82`): canonical roadmap observation only; preserve other caps, private redaction, model history, logs and source-before-sink guards. No broader Base edits. |
| CX-20 | Larry explicitly reassigns remaining WS-17 from Claude to Codex on 10-07; WS-20 documentation #193 merged concurrently and edits narrow WS-17 state fields, and landed WS-21 shares console/inventory files. | `larry` (10-07): Codex owns remaining WS-17 implementation; `codex` preserves #173 and records this bounded coordination | resolved ownership/scope boundary: WS-17 owns its implementation/plan/evidence and current row; WS-20 retains operational summary/decision grouping and WS-20-specific logs; its landed #193 wording is reconciled to this newer assignment, with WS-17 owning its block/plan/receipts/logs; no edits to the other session’s branch. Preserve WS-21 transfer/screen behavior and its separate physical acceptance. Cross-review and release approvals remain required; no other row is reassigned |
| CX-11 | Historical T2 merge collision: (1) auth defaulted on; (2) internal callers and deployment health lacked service headers; (3) stale sidecar route inventory; (4) concurrent `mcp_selfedit` edits; (5) token setup remains CLI-only, while the native app already reads a Keychain token. Items (1)–(4) were resolved by dormant Addendum R1 and deployed. PR #149 added a second explicit remote-bind gate so local bearer auth need not expose a listener. | `codex`: choose and implement local-only token onboarding for (5); `larry` decides local activation and any remote bind separately | R1 deployed dormant; R2 bind guard merged as `a39136a` but not deployed in `39fc6f9`; onboarding method/provisioner and enabled-mode acceptance remain open |

Resolved, decided and closed rows (CX-23, CX-21, CX-16, CX-13, CX-15, CX-14, CX-01, CX-02, CX-03, CX-04, CX-05, CX-06, CX-07, CX-08, CX-09, CX-10, CX-12) moved to the [roadmap history archive](docs/roadmap-log/archive/2026-11-10-roadmap-history.md#from-roadmapmd-4-conflict-register-resolved-rows-table-at-lines-17181744-at-837bb04) on 2026-11-10.

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

## 11. Skills consolidation — approved direction, implementation after acceptance

<details id="ws-29">
<summary>WS-29 — Unified Skills library with preserved policy and runtime controls · parked</summary>

- **Owner:** `codex` for this documentation only; future implementation unassigned and model-neutral
- **Status:** parked: Larry accepted Option 2 on 2026-10-20 and requested this implementation plan at the end of the roadmap; implementation waits until existing acceptance testing is complete
- **Implemented by:** not implemented; Codex documented the accepted direction and future handoff
- **Remaining work / acceptance:** Complete existing acceptance under the authoritative clearance plan, record Larry's closeout, then dispatch a fresh bounded implementation claim. Implement SC0–SC7 and pass AT-01–AT-19 in the linked plan, including the policy-budget ledger, per-row backstops, named voice replay corpus, skill-displacement gate, request-bound method bodies, standing policies, all seven voice-event contracts, draft exclusion, trusted execution, privacy, and rollback. No present acceptance checkbox is closed by this entry.
- **Model version:** not recorded; any assigned model meeting the plan's capability and evidence requirements may implement it
- **Where:** original plan on `codex/skills-consolidation-plan-20261020`, merged [PR #227](https://github.com/Larryfix71566/jarvis-voice-ai/pull/227); Claude review amendments on `codex/ws29-claude-review-20261020`, merged [PR #228](https://github.com/Larryfix71566/jarvis-voice-ai/pull/228) as `0acf8a8`; merge record in [PR #229](https://github.com/Larryfix71566/jarvis-voice-ai/pull/229); review baseline main `e52bdae`; no runtime implementation branch or claim
- **Plan:** [Skills consolidation implementation plan](docs/plans/MORTIMER_SKILLS_CONSOLIDATION_IMPLEMENTATION_PLAN.md)
- **Scope:** Documentation only: this appended section, the linked canonical plan, the original plan log, and `docs/roadmap-log/2026-10-20-ws-29-claude-plan-review.md`. Future source/UI/schema changes are proposals, not current locks or assignments. No runtime, credential, model, provider, deployment, migration, configuration-key, port or allow-list change is authorized or reserved.
- **Next step:** larry: complete and record existing acceptance closeout, then dispatch WS-29 to any capable model with owner/branch/scope. Assigned implementer: refresh main and dependencies, follow SC0 before code, and coordinate existing owners; keep WS-22/24 operational state and WS-27 target/task routing intact.
- **Updated:** 10-20 (Claude implementation-readiness review incorporated; documentation only; future implementation remains parked)

</details>

## 12. Phone access — approved direction; staged implementation

<details id="ws-30">
<summary>WS-30 — Private phone voice, results and roadmap access · native-iPhone direction approved; gates remain</summary>

Larry requested saving the revised phone-access draft in the existing plan
folder and appending this initiative at the end of the roadmap on 2026-10-22.
On 2026-10-28 Larry approved the native SwiftUI iPhone direction, user-started
voice plus eligible incoming CallKit/PushKit calls, private Tailscale/WireGuard
transport, direct minimal Mac-to-APNs invitations, and explicitly admitted
memory-only shared information. The proposed canonical plan addendum is
[revision 5.4](docs/plans/MORTIMER_PHONE_ACCESS_PLAN.md#16-approved-native-iphone-direction-and-staged-claims--revision-54-amendment-candidate-2026-10-28).
This draft records product direction; it does not establish an installed app,
eligible APNs/VoIP use, live tunnel, running service, or accepted phone access.
WS-04 retains remote-authentication/admission foundations; WS-17 retains
result/roadmap and release seams; WS-05 retains provider/speech readiness;
WS-21 retains display-transfer ownership; WS-24 retains durable recovery.

- **Owner:** Codex is accountable for WS-30. WS-04/17/05/21/24 retain their existing runtime, provider, result, display, recovery, and release ownership.
- **Status:** in-progress — Larry approved the native SwiftUI iPhone direction, user-started voice, eligible incoming CallKit/PushKit calls, private-path transport, and admitted shared information on 2026-10-28. WS-30 S0 merged in PR #285 as `97ffb3bb19ce29a9c4e6768a481389ac147cd691`. The offline Mac admission source review ACCEPTED exact commit `6a4b22cbd38014b01fb2de6a35245416c20560b6`. The six-file WS-30 fake-host package source at `c0a0de93d046c13a4b64f21d2b0e18cd3559a274` and the two-file WS-04 isolated store candidate landed on main via #290 at merge commit `137c6689d2d18f3765003aae1eeb610bd8945b0a` (2026-11-06 02:37 UTC). Within #290 only the WS-04 admission core had review by a system other than Codex (Kimi); the WS-30 reviews recorded here and in their logs are Codex-coordinated, by a nonauthor reviewer identified by ID. No part is accepted. **Historical receipt:** at earlier integration head `300918674b36ccea2a2be7e2b689ed6639eae689`, Swift source review ACCEPTED and local tests passed 15/15; the disposable store hashes were `b89e1141d69aa1eba7129cfd35a1e2f0cd388ac7c828d669427ac1a0cf322b86` and `b1e15858c19228f4cb022645448021cd0b29b34f3155215ed6110576765abe79`, with its focused suite passing 34/34 under Python 3.12 using repository `ClientIdentity`. Those historical receipts establish neither production persistence nor a production store. Repository CI still does not run the Swift package. The precise one-file CI claim adopted below and in R3.8 was never implemented; #290 landed without it, and `.github/workflows/` on main has no Swift job. **Historical WS-04 receipt:** earlier head `f516d73dd5028391ede2bb1f4cf30d83f10069a8` had failed run #535 as recorded above. **Historical receipt:** head `cbba8645ceaa7ad81e83b8dce5af3f03d8ce00c5` passed exact-head CI run #538 (`41095632875`): 7,322 unit tests, 197 integration tests, 13 evals and all other checks; this is not current status. The current published head is `46e29c26e6a4262aa47dfa96615f3a91cc990572`; Validate #543 failed at 2026-10-31 05:47 UTC in `test_model_execution_deadlines.py::test_provider_swallowing_cancellation_cannot_return_or_publish_late_result[False-True]` (1 failed, 7,362 passed, 49 skipped, 398 subtests; downstream jobs skipped). The prior #537 and runs `40905287773`, `40905288031`, and `40905287877` are historical. No live acceptance is claimed.
- **Implemented by:** The accepted six-file fake-host package source is at `c0a0de93d046c13a4b64f21d2b0e18cd3559a274` in PR #290, which landed on main as `137c668`; independent review ACCEPTED the exact source. `swift test --package-path ios/MortimerPhoneCore` passed 15/15 locally with Swift 6.4 on macOS; the host OS version was not recorded. The offline two-file store candidate was integrated at `66121b8` and remains in the current head; its focused suite passed 34/34 under Python 3.12 using repository `ClientIdentity`. These prove offline policy, fake-host and fake-anchor behavior only—not an iOS app, device behavior, production persistence or a live service. PR #285 records the synthetic S0 merge.
- **Remaining work / acceptance:** The exact six WS-30 files in Scope are implemented and independently reviewed, but the repository has no CI job for this Swift package. Keep CI coverage open until the pending exact `.github/workflows/validate.yml` claim is independently reviewed/adopted, coordinated with Claude for cross-review/handoff, and the package job passes. No workflow edit or CI acceptance is claimed. WS-17 result payloads/cards and WS-05 voice readiness remain separate dependencies; CallKit/PushKit/APNs, real transport, device, Apple, microphone, install, deployment and privacy acceptance remain later separately gated work. Preserve the one-final-merge direction and all existing acceptance statuses. R3.12 remains a separate local phone-protocol increment. R3.20 adds the accepted bounded offline app scaffold, including an unsigned generic iOS Simulator build-for-testing; simulator UI execution and device acceptance remain open.
- **Model version:** Sol authored planning input SHA-256 `772328cfcc55c362cb5f7e84be875134bedcde25e95b3209f2ff38050527ebdc`. GPT-6 Luna authors this documentation-only amendment. The implementation owner reports the S0 successor branch/commit and oracle acceptance for hashes listed in §16; this documentation author has not independently inspected the source bytes. Historical Fable reviews cover only their recorded immutable inputs and do not review this addendum or current candidate bytes.
- **Where:** #290 landed on main at merge commit `137c6689d2d18f3765003aae1eeb610bd8945b0a` from head `7d12cc2493a05ea7f96cb4fc18683deab945f0d8`. Earlier published head `46e29c26e6a4262aa47dfa96615f3a91cc990572` (tree `2d4ceb0ad7817aebe04980c2a6983e621cfb45e5`) was based on main `5310d1a9305035f43143fcffad6161619281f475`. R3.20 source work was isolated to `codex/ws30-ios-app-scaffold-20261031`. The ten scaffold paths are now on main; they entered #290 in commit `fff9fe8`. Accepted commit `d636c328312458fa101e47bddcff406626410f7f` was never published, so this record does not confirm that main's files match it. The app target and unsigned generic iOS Simulator build-for-testing are established by the accepted local source candidate; simulator UI execution and device acceptance are not.
- **Registration history:** The original revision-5.4 documentation amendment was prepared on `docs/ws30-iphone-approval-20261028`; its original standalone documentation scope and the S0 successor evidence remain recorded in plan §16 and the dated claim log. Documentation registration on `docs/ws30-s0-claim-20261022` from main `ab31dfa8ddf58ad0583afcb25dffd18afbee5765` merged in #265. Frozen #240 stays at `87f163a` and must not merge.
- **Plan:** [Phone-access plan and revision 5.4 amendment](docs/plans/MORTIMER_PHONE_ACCESS_PLAN.md), including the frozen revision-5.3 claim/provenance and approved-direction addendum; [existing S0 claim log](docs/roadmap-log/2026-10-22-ws-30-s0-contract.md). WS-04's existing remote-access plan remains authoritative for shared authentication/bind foundations.
- **Prior documentation scope:** The original standalone revision-5.4 amendment changed only `docs/plans/MORTIMER_PHONE_ACCESS_PLAN.md`, the WS-30 roadmap block/ownership row, and `docs/roadmap-log/2026-10-22-ws-30-s0-contract.md`. This is preserved as history; it did not implement source, activate any service, or reserve the current six Swift paths.
- **Scope:** The active branch-local WS-30 source claim is exactly `ios/MortimerPhoneCore/Package.swift`; `ios/MortimerPhoneCore/Sources/MortimerPhoneCore/PhoneRemoteProtocolV1.swift`; `ios/MortimerPhoneCore/Sources/MortimerPhoneCore/PhoneSessionState.swift`; `ios/MortimerPhoneCore/Tests/MortimerPhoneCoreTests/FakePhoneRemoteHost.swift`; `ios/MortimerPhoneCore/Tests/MortimerPhoneCoreTests/PhoneRemoteProtocolTests.swift`; and `ios/MortimerPhoneCore/Tests/MortimerPhoneCoreTests/PhoneSessionStateTests.swift`. It is a test-only generic R3.4 envelope/status and local lifecycle model with an injected fake host. It defines no authentication or operation payload schema, result projection, real transport, voice path, call handling, CI workflow, network, credentials, Keychain, UI activation, or runtime service. The S0 test/fixture transfer to WS-04 and its oracle/versioning obligations remain binding; WS-30 retains no editing authority for those transferred paths. Adopted R3.12 adds exactly `ios/MortimerPhoneCore/Sources/MortimerPhoneCore/PhoneRemoteOperationsV1.swift`, `ios/MortimerPhoneCore/Tests/MortimerPhoneCoreTests/FakePhoneRemoteOperationsHost.swift`, and `ios/MortimerPhoneCore/Tests/MortimerPhoneCoreTests/PhoneRemoteOperationsV1Tests.swift`; it does not modify the accepted generic fake-host files. Its documentation is limited to this WS-30 block, §16 of the existing phone-access plan, and the dated proposal log. R3.20 amends the effective source Scope with exactly ten paths: modify `ios/MortimerPhoneCore/Package.swift`; add `ios/MortimerPhoneCore/Sources/MortimerPhoneCore/PhoneAppPreviewModel.swift`; add `ios/MortimerPhoneCore/Tests/MortimerPhoneCoreTests/PhoneAppPreviewModelTests.swift`; add `ios/MortimerPhoneApp/MortimerPhoneApp.xcodeproj/project.pbxproj`; add `ios/MortimerPhoneApp/MortimerPhoneApp.xcodeproj/xcshareddata/xcschemes/MortimerPhoneApp.xcscheme`; add `ios/MortimerPhoneApp/MortimerPhoneApp/Info.plist`; add `ios/MortimerPhoneApp/MortimerPhoneApp/MortimerPhoneApp.swift`; add `ios/MortimerPhoneApp/MortimerPhoneApp/PhonePreviewRootView.swift`; add `ios/MortimerPhoneApp/MortimerPhoneApp/PhonePreviewFakeTransport.swift`; and add `ios/MortimerPhoneApp/MortimerPhoneAppTests/PhonePreviewUITests.swift`. Only the package manifest is an existing path, already WS-30-owned; this is an amendment to that same claim, not a competing owner. The app branch and ten-path Where are recorded in the R3.20 claim log.
- **CI claim (adopted branch-locally; not implemented):** The exact one-job WS-30 coverage claim is limited to `.github/workflows/validate.yml`; it is recorded in R3.8 and adopted on this integration branch only. No workflow edit or CI acceptance is claimed. No other workflow path is included. WS-12 is a closed Claude-owned workflow-maintenance slice with no active path lock; before editing the shared workflow, coordinate a Claude handoff/cross-review and preserve the accepted WS-12 runner/action conventions and the narrow WS-20 roadmap-check step. This does not reopen or transfer WS-12/WS-20 ownership.
- **Next step:** codex: confirm main's ten R3.20 scaffold paths match accepted source `d636c32`, then run UI tests when a compatible CoreSimulator is available. The one-file CI workflow claim remains separately gated on Claude handoff/cross-review before any workflow edit. Keep result payloads with WS-17 and voice readiness with WS-05. Incoming calls and all real device, Apple, tunnel, microphone, install, release and privacy gates remain separate.
- **Updated:** 2026-11-06 UTC (Claude, at Larry's direction: recorded #290's merge as `137c668`; no source, runtime or acceptance change). Previous: 2026-10-31 UTC. R3.20 source commit `d636c328312458fa101e47bddcff406626410f7f` (tree `91fece35b01f8b8217ff5d0f12874e8b6695ac6f`) was independently accepted for the adopted ten-path unsigned scaffold. `swift test --package-path ios/MortimerPhoneCore` passed 46/46; unsigned generic simulator `build-for-testing` compiled the app and UI-test bundle. UI tests could not execute because installed CoreSimulator framework 1171.7.0 is incompatible with Xcode 27.2's required 1174.21.0; no runtime was installed or changed. PR #290 remains open/draft/unmerged at the last verified published head `46e29c26e6a4262aa47dfa96615f3a91cc990572`; Validate #543 failed on that earlier head as recorded above. The R3.20 candidate is local/unpublished and has no exact-head CI receipt. No device or live acceptance is claimed.

- **R3.13 adopted local claim:** The parent adopted the reviewed two-file WS-30 client claim. GPT-6 Luna authored the cancellation-linearization source candidate at `4e2507af17be12a40d6afdf07ad8a54f9cc37716`; existing reviewer `01a18584-92e2-7511-aca8-983bb3f230ef` remains the nonauthor reviewer. `swift test --package-path ios/MortimerPhoneCore` passed 40/40 (10 new client tests, 30 existing); exact-source review is pending. No publication, app, network transport, or live acceptance is claimed. See R3.13 in the remote-access plan.


- **Aggregate draft — 2026-10-27 UTC:** Synthetic S0 from `2cca0f1` plus two hashed dirty author repair files at local `ffecab1`; prior oracle REVISE and renewed review gate remain explicit. [Full included/deferred manifest](docs/roadmap-log/2026-10-27-unmerged-integration.md).

### Branch-local WS-30 fake-host package claim (implemented; independent source review accepted)

On the integration branch `codex/ws04-phone-admission-core-20261029` (PR #290 at then-published head `628d743efa6b23b3341840594b176f9562bcc154`; merged to main 2026-11-06 as `137c668`), the exact six-file WS-30 test-only Swift Package claim above is implemented at source commit `c0a0de93d046c13a4b64f21d2b0e18cd3559a274` and independently accepted. Local `swift test --package-path ios/MortimerPhoneCore` passed 15/15 with Swift 6.4 on macOS; the host OS version was not recorded. It landed on main with #290. It proves neither an iOS app/build nor device, UI, or live behavior. It is disjoint from WS-04's two R3-S1 Python paths, which were integrated at `66121b8` and remain present at the current head, and does not edit shared `macos/JarvisKit` or transfer their ownership.

The package follows the R3.4 `mortimer.phone-remote.v1` envelope/operation/status names and defines no authentication fields or operation payload schemas. It uses an injected deterministic fake host only; results payloads wait for WS-17, and voice readiness remains WS-05-owned. No network, credentials, Keychain, audio, UI activation, CallKit, PushKit, APNs, tunnel, or live Mac service is included. The accepted protocol and test boundary is in [R3.7](docs/plans/MORTIMER_REMOTE_ACCESS_PLAN.md#r37-adopted-ws-30-fake-host-swift-package-claim--2026-10-29). The one-final-merge exception does not transfer another workstream's ownership or acceptance gates.

**Adopted branch-local CI claim (workflow not implemented):** WS-30 claims exactly one `phone-core-swift` job in `.github/workflows/validate.yml` on `macos-15-intel`. Select the preinstalled Xcode 26.3 explicitly with job-level `DEVELOPER_DIR: /Applications/Xcode_26.3.app/Contents/Developer`; do not install a toolchain. The job uses `actions/checkout@v7` with `persist-credentials: false`, records `xcodebuild -version`, `swift --version`, `xcrun --version` and `xcrun --find xctest`, then runs `swift test --package-path ios/MortimerPhoneCore`. The package declares Swift tools 6.2 and its test suite invokes `/usr/bin/xcrun xctest` in a child process, so an Ubuntu job is incompatible. The image's default Xcode 16.4 supplies Swift 6.1, below the package tools baseline; Xcode 26.3 supplies Swift 6.2.3. The job inherits the existing `contents: read` permission and `pull_request` trigger; it adds no credentials, permissions, package dependencies, toolchain installation, signing or deployment. GitHub documents `macos-15-intel` as a standard runner for public repositories, and its macOS 15 image lists the exact Xcode 26.3 path and Xcode command-line tools. WS-12's Claude-owned CI maintenance is accepted/closed with no active path lock. Before the workflow edit, coordinate a Claude handoff/cross-review, preserve WS-12 action/runner conventions and the narrow WS-20 roadmap-check step, and make no ownership change. The sole changed source path in this adopted claim is `.github/workflows/validate.yml`; no workflow file is edited by this documentation proposal.

- **R3.12 adopted local source claim:** Foundation-only closed DTOs and fake-host tests for the four R3.9 operations `session.status`, `voice.offer`, `voice.update`, and `voice.end`; exact paths and checked JSON limits are in the canonical phone-access plan. This does not wait on WS-04 R3.11 mapping; source is local and pending independent review.

- **R3.20 adopted branch-local app-scaffold claim (offline source accepted; local/unpublished):** coordinator adopted the exact ten-path WS-30 claim on `codex/ws30-ios-app-scaffold-20261031`, amending this workstream’s effective Scope/Where, including its existing ownership of `ios/MortimerPhoneCore/Package.swift`. Scope adds the Foundation-only model/test and unsigned SwiftUI app project, shared scheme, fake transport and UI-test paths listed in phone plan §16 and the [claim log](docs/roadmap-log/2026-10-31-ws30-ios-app-scaffold-proposal.md). The app remains disconnected from Mortimer in every state; only an explicit synthetic demo uses the existing checked client and injected fake byte transport. The persistent “Disconnected from Mortimer. Synthetic preview only.” notice is in shared chrome, and the compiled UI-test bundle asserts its presence during navigation; runtime visibility is unverified. iOS 17 is the scaffold deployment minimum, not a product support decision. Independent review ACCEPTED source commit `d636c328312458fa101e47bddcff406626410f7f` (tree `91fece35b01f8b8217ff5d0f12874e8b6695ac6f`). The 46-test core suite and unsigned generic app/UI-test build-for-testing passed. UI execution remains unverified: installed CoreSimulator framework 1171.7.0 does not match Xcode 27.2's required 1174.21.0. Signing, device, network, authentication and live access remain unestablished.

**R3.23 Scope/Where amendment (2026-10-31):** The eight WS-30 paths on `codex/ws04-ws17-ws30-results-snapshot-resume-20261031` are `ios/MortimerPhoneCore/Sources/MortimerPhoneCore/PhoneRemoteOperationsV1.swift`, `ios/MortimerPhoneCore/Sources/MortimerPhoneCore/PhoneAppPreviewModel.swift`, `ios/MortimerPhoneApp/MortimerPhoneApp/PhonePreviewFakeTransport.swift`, `ios/MortimerPhoneApp/MortimerPhoneApp/PhonePreviewRootView.swift`, `ios/MortimerPhoneCore/Tests/MortimerPhoneCoreTests/PhoneRemoteOperationsV1Tests.swift`, `ios/MortimerPhoneCore/Tests/MortimerPhoneCoreTests/PhoneRemoteOperationsClientTests.swift`, `ios/MortimerPhoneCore/Tests/MortimerPhoneCoreTests/PhoneAppPreviewModelTests.swift`, and `ios/MortimerPhoneApp/MortimerPhoneAppTests/PhonePreviewUITests.swift`. This branch-local amendment adds only disconnected synthetic results behavior; it changes no transport or app activation.

**R3.23 adopted offline client extension (2026-10-31):** The coordinator adopted the exact eight WS-30 paths in [remote plan R3.23](docs/plans/MORTIMER_REMOTE_ACCESS_PLAN.md#r323-results-snapshot-resume), extending the checked DTO/client and disconnected preview for synthetic snapshot/resume only. Independent review ACCEPTED the combined source at `b4ae7740719f45e4dd81ad3f4917c789c608f57c` (tree `88a201a809f1310c950032ee04d199fa63deeec6`); all 58 Swift tests and the unsigned generic app/UI-test bundle build passed. UI execution and visuals remain unverified. The app continues to identify itself as disconnected; masking occurs only on observable local events or a received authority response. This does not create a live transport, result export or device-acceptance claim.

**Historical typed phone-card design documentation claim (2026-10-31; superseded by the adopted source claim below):** Parent coordinator dispatches Codex to prepare this isolated docs-only design on `codex/ws04-ws17-ws30-phone-card-design-20261031`, based on immutable R3.24 finalization `8797891d48bbd4a7e1b9d755ac23d6bc9a2c2470`. Status: design prepared for independent review; source adoption remains pending. WS-30 owns the proposed checked Swift DTO/client/model and disconnected preview behavior. Effective documentation Scope/Where amendment: only the WS-04/WS-17/WS-30 blocks in `ROADMAP.md`, dated appendices in existing `docs/plans/MORTIMER_REMOTE_ACCESS_PLAN.md` and `docs/plans/MORTIMER_PHONE_ACCESS_PLAN.md`, and `docs/roadmap-log/2026-10-31-ws04-ws17-ws30-phone-card-command-design.md`. This claim is recorded before plan edits. Fresh read-only GitHub refresh confirms main `5310d1a9305035f43143fcffad6161619281f475` and draft/open/unmerged PR #290 at `39208d18d8c6fde0a9a0539e4d7c3aa68de5610f`; main ROADMAP blob matches local `5310d1a` exactly. Local origin has no main ref and ancestor traversal encounters a missing historical commit; retain the existing coordinator-authorized branch-local exception and require current-main reconciliation before integration. Fresh checkout is clean; active owners and source scopes stay intact. No runtime/source edit, frozen fixture/adapter change, identifier reservation, production controller/security, publication or live action is authorized. Next step: codex independent reviewer evaluates the exact design and proposed 22-path source/test map; coordinator adopts any later implementation claim separately. The completed documentation is in the existing remote plan and phone-plan §18; no implementation or test acceptance is claimed.


**Adopted typed phone-card source claim (2026-10-31):** Coordinator adopts independently accepted design `ffb1b1ccb4582bd38bd8ca426e9835a99a4e2ce9`, tree `1a6f090afd231766f32a44eb45e2a53824e7d280`, for complete synthetic offline implementation. Owner: `codex`; status: independently bounded-accepted synthetic/offline source `a121dfb06385702b82a18041d7d974ab40877ee9` / tree `10b9b68d7a27d52ca2b54d42784326b5da279f86`; Where: `codex/ws04-ws17-ws30-phone-card-source-20261031`. Effective source Scope for this row is exactly: `ios/MortimerPhoneCore/Sources/MortimerPhoneCore/PhoneRemoteProtocolV1.swift`; `ios/MortimerPhoneCore/Tests/MortimerPhoneCoreTests/PhoneRemoteProtocolTests.swift`; `ios/MortimerPhoneCore/Sources/MortimerPhoneCore/PhoneRemoteOperationsV1.swift`; `ios/MortimerPhoneCore/Sources/MortimerPhoneCore/PhoneAppPreviewModel.swift`; `ios/MortimerPhoneApp/MortimerPhoneApp/PhonePreviewFakeTransport.swift`; `ios/MortimerPhoneApp/MortimerPhoneApp/PhonePreviewRootView.swift`; `ios/MortimerPhoneCore/Tests/MortimerPhoneCoreTests/PhoneRemoteOperationsV1Tests.swift`; `ios/MortimerPhoneCore/Tests/MortimerPhoneCoreTests/PhoneRemoteOperationsClientTests.swift`; `ios/MortimerPhoneCore/Tests/MortimerPhoneCoreTests/PhoneAppPreviewModelTests.swift`; `ios/MortimerPhoneCore/Tests/MortimerPhoneCoreTests/PhoneResultCommandsProcessTests.swift`; `ios/MortimerPhoneApp/MortimerPhoneAppTests/PhonePreviewUITests.swift`. Across WS-04/17/30 this is exactly 22 paths (7/4/11), 19 existing and three new, matching the verified design manifest. Documentation remains limited to these three roadmap blocks/shared reservation, existing remote/phone plans and the typed-card design log. Fresh local checks found all targets match accepted blobs and no dirty work; coordinator remote refresh at 14:52 reports main `5310d1a`, PR290 `39208d18`, green CI544 and no comments/other-PR/published collision. Local handoff origin lacks main and complete historical ancestry; the existing branch-local exception continues, with current-main reconciliation before integration. This amendment precedes all source edits. Preserve frozen fixture/adapter, R3.23 historical receipts and R3.24 recovery/proof/cancellation invariants. No production content/controller/Keychain/signing/network/live/external action or publication/merge is included. Next step: coordinator-managed current-public-main reconciliation and complete integration/validation packet; remaining foreground product construction and live prerequisites are enumerated in [phone-plan §19](docs/plans/MORTIMER_PHONE_ACCESS_PLAN.md#19-product-completion-audit--2026-10-31), without a new source claim. Independent final validation: 369 Python tests/501 subtests with warnings as errors, 67 PhoneCore tests and 24 scoped native tests, zero skips; earlier unsigned app/UI bundle build at `8c2e49f0` applies to unchanged Swift/native bytes. UI execution remains unrun because CoreSimulator 1171.7.0 is older than required 1174.21.0. Full-repository/integration CI, exact full-vector facade replay, production construction/content/transport and live release remain open. Final combined reentry/source-denial probe records uncertain and fences; healthy ordinary withholding stays unfenced. Claim metadata is Git-resolved. Dated verdict, exact artifact hashes and finalization evidence are in the existing remote/phone plans and typed-card log. This final slice updates four claimed docs only; accepted source/frozen/native bytes are preserved. No publication, merge or live acceptance is claimed.

</details>


## 13. REA-assisted app building — NR1 contract landed; operational work open

<details id="ws-31">
<summary>WS-31 — New apps and authorized feature recreation through Mortimer · Kimi NR1 implemented; F1–F4 fixed via #315; Claude independent review approved 11-10</summary>

Larry requested preserving the REA research and implementation plan, clarified
that REA should help Mortimer build new apps or recreate authorized app features,
and requested this plan at the end of the roadmap on 2026-10-22. This append
follows landed WS-30 phone documentation revision 5.2 without changing existing priorities or entries.

Registration provenance: documentation candidate `docs/ws31-main-integration-20261022` is based on `ab31dfa8ddf58ad0583afcb25dffd18afbee5765`; frozen REA #245 `b23b824` and corrected NR1 `eb413a25` are content inputs, not merged ancestry. Phone #265 has landed; frozen #240 remains historical. Sole serial coordinator owns integration. These registration/historical refs are not active implementation locations.

- **Owner:** `kimi` for the bounded NR1 pure no-reference contract implementation; `claude` owns the bounded independent exact-source review of NR1, moved from Codex by Larry's pick "WS-31 review" in his Claude Duet channel on 2026-11-06 at 02:43:00 UTC (Codex is out of usage this week); Claude did not author the implementation or the contract; broader implementation/acceptance owners unchanged
- **Status:** landed via [#283](https://github.com/Larryfix71566/jarvis-voice-ai/pull/283) at merge commit `81b6b4d9e05d5166da4c5809ff6efbc18516d0df`. Post-merge verification on main `075afb18c84a14bca517425f38934eafc92af50d` found the three implementation blobs unchanged and 81 focused tests passed; independent exact-source review (now Claude's) and all operational app-building/REA gates remain open. Independent exact-source review (Claude, nonauthor) recorded via this PR on 2026-11-06 against `d2e7a61`, whose three blobs are identical on main `b084f78`: **changes requested**. F1 (Medium): mapping preflight reports errors in dict insertion order, contrary to §11 and NR1-10; F2–F4 (Low): preflight ignores the stated error priority, keeps emitting `limit_exceeded` after the node budget, and its type check can call a metaclass `__eq__`. 81 focused tests pass; the NR1-01 digests match an independent calculation; no side effects under an audit hook. Details: `docs/roadmap-log/2026-11-06-ws-31-claude-nr1-review.md`. Kimi's fix for F1–F4 landed via [#315](https://github.com/Larryfix71566/jarvis-voice-ai/pull/315) at merge commit `0e1bd6f64f559c8d82ba388e9b60bf30bff041fe` (2026-11-10), code at `2d150902366ddd4909c8112f4f3d46bddc4fa3dc`, PR head `c43fdbf1c9063228f0162103720f3326b8e1b3f9`; #315 did not include its WS-31 block update, which this record supplies. Claude re-reviewed head `c43fdbf` on 2026-11-06: **APPROVE**, no new findings. All four findings are fixed; 85 focused tests pass (81 unchanged plus 4 new); the NR1-01 digests are unchanged; the original hostile probes and a new key-shuffle, error-cap, unknown-key and priority probe show no mismatches, while the same probes find mismatches against the pre-fix module. The three NR1 blobs on main `0e1bd6f` are identical to the reviewed head. Details: `docs/roadmap-log/2026-11-10-ws-31-claude-nr1-fix-approval.md`
- **Implemented by:** Kimi authored the three implementation files at `d2e7a61`; Codex authored the existing NR1 contract/claim and retains nonauthor review responsibility; original research and static-review authorship retained
- **Remaining work / acceptance:** The independent NR1 source-review gate is closed: Kimi fixed F1–F4 (#315) and Claude approved the exact head. Real app selection, build, Skill, route, recovery, publication and release gates remain separate; no acceptance closes
- **Model version:** separate Codex static contract review APPROVE at exact `eb413a25d80df202af8e6d0f04e737ef0463b992`; earlier `f6b6f6e` remains unapproved. Kimi implementation used no runtime model execution; independent source review (Claude, nonauthor) approved the fixed head `c43fdbf` on 2026-11-06, recorded 11-10
- **Where:** `kimi/ws31-no-reference-contract-20261028`; implementation `d2e7a61d46edcc66bbf1eb5746fb3282a14c7efd`; landed via #283 at `81b6b4d9e05d5166da4c5809ff6efbc18516d0df`. Review claim on `claude/ws31-nr1-review-claim-20261106` via [#310](https://github.com/Larryfix71566/jarvis-voice-ai/pull/310); Claude review record on `claude/ws31-nr1-review-20261106` via [#313](https://github.com/Larryfix71566/jarvis-voice-ai/pull/313) at `c7cc1181ad2de0eb5b5b3ec19cc696768cca288f`; Kimi fix on `kimi/ws31-nr1-review-fixes-20261106` via #315 at `0e1bd6f64f559c8d82ba388e9b60bf30bff041fe`; Claude approval record on `claude/ws31-record-315-approval-20261110` (this PR)
- **Plan:** [REA app-building integration plan](docs/plans/MORTIMER_REA_INTEGRATION_PLAN.md), with [complete preserved research](docs/interface-research/REA_INTEGRATION_RESEARCH_2026-10-22.md) and [original DOCX](docs/interface-research/REA_INTEGRATION_RESEARCH_2026-10-22.docx)
- **Scope:** NR1 only after main registration: new stdlib-only `jarvis/app_build_contract.py`, new `tests/unit/test_app_build_contract.py`, synthetic `tests/fixtures/app_build_contract/new_idea_v1.json`; this WS-31 block, canonical REA plan, dated WS-31 log and content-free NR1 receipt under `docs/acceptance/rea-app-building/`. No existing admin/agent/App Builder/Skill/provider/sandbox file, shared test, dependency/config/registry/policy, API/UI/tool wiring, persistence/migration, model call, reference acquisition/execution, new app repository, publication, credentials, service or deployment change. No runtime identifier reserved. Claude's review-only scope (11-06): read the three NR1 files at `d2e7a61`, run offline tests and bounded synthetic hostile checks outside the repository, and write only this WS-31 block, a dated entry in the canonical REA plan and WS-31 `docs/roadmap-log/` entries. Claude edits no NR1 source, test or fixture; findings go to Kimi as a separate fix
- **Next step:** larry: merge this approval record. larry: choose the actual app outcome before any later real build. Serial coordinator handles integration; no merge is delegated here
- **Updated:** 11-10 (Claude: #315 merge and Claude's approval of its exact head recorded; no source, runtime or acceptance change). 11-06: independent NR1 review recorded, changes requested (#313). Earlier 11-06: review moved from Codex to Claude by Larry's pick (#310). Previous: 10-28 (#283 merged; post-merge source identity and 81 focused tests verified on main `075afb18c84a14bca517425f38934eafc92af50d`; no activation, runtime wiring or acceptance change)

</details>
