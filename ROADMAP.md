# Mortimer master roadmap

This file is the single record of **who is doing what** in this repository, for every system that writes code here. Plans (`docs/plans/`) hold design. Receipts (`docs/acceptance/`) hold evidence. **This file holds ownership and state.**

**Last full reconciliation:** 2026-10-02, read-only review of every §2 block against `origin/main` `a39136a` (before the WS-19 claim), tracked code/configuration, plan and acceptance headers, open PRs, CI, and the latest DEPLOY-MAIN log. **Latest verified production:** `39fc6f9` (PR #141 merge), deployed 09-30 17:53 EDT. That deployment passed Python 4,938 / 7 skipped, MortimerHost 416 / 6 skipped / 0 failures, JarvisKit 219 / 0; phase D reported admin/vault 200, bot 307, and matching source/bundle revision. Main is ahead of production: PRs #143–#149 include WS-03, WS-04 and WS-18 changes that have **not** been verified in the running app. This review creates no new live acceptance. Original evaluation: [cross-system evaluation](docs/reviews/CROSS_SYSTEM_PLAN_EVAL_2026-09-27.md).

---

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
10. **Update your row when its state changes.** Do this on your branch; it lands with your PR. On merge the row becomes `landed`, with the PR number and merge commit, and the plan's status header is updated to match.
11. **Status hierarchy:** this file (owner, state) > plan status header (design status) > receipts (evidence). When they disagree, correct the plan header, unless this file is the one that's wrong.
12. **Attribution:** every PR body names the system and its session link.
13. **Everything in progress has a block, including work that isn't code** (reviews, option write-ups, plan edits, guided Mac checks). Add it as `proposed` before starting and mark it `claimed` when you start. If the work produces no PR of its own, update the block through a docs-only PR at the end of the session. Both systems re-read §2 at the start of every session, because the other system may have changed it.

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
5. Update the existing plan’s dated progress and add a §8 log entry with system,
   workstream, change, evidence, and remaining action. Link receipts rather than
   copying large logs. Commit/hand off through the existing branch/PR protocol.
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

### Needs work: not yet built (proposed, claimed, in progress, in review, blocked)

<details id="ws-20">
<summary>WS-20 — Roadmap joint working: catch-up and drift prevention · Claude + Codex (proposed)</summary>

**Workstream:** Larry, 10-02: bring the roadmap and open PRs up to date so Claude and Codex can work on it together, and stop the roadmap drifting. Larry chose: each system fixes its own rows; the change log moves out of `ROADMAP.md`, one production line, rows written as they read after merge, and a drift checker; the plan lives in the repo.

- **Owner:** `claude` (B4 checker, plan) and `codex` (B1–B3) (proposed)
- **Status:** proposed
- **Implemented by:** —
- **Remaining work / acceptance:** Phase A: #138 closed; #142, #147 and #152 merged; production at main; Larry's WS-18 and thread checks recorded. Phase B: the checker passes on main in CI; no row states current production; the next 10 PRs merge with no change-log conflict. Phase C rules are in §0.
- **Model version:** not recorded; do not infer from system name.
- **Where:** main (plan); work branches per part when claimed
- **Plan:** `docs/plans/ROADMAP_JOINT_WORKING_PLAN.md`
- **Scope:** none while proposed. When claimed: B1–B3 (Codex) `ROADMAP.md` §0, §8 and production wording, `docs/roadmap-log/**`; B4 (Claude) `scripts/check_roadmap.py`, `tests/unit/test_check_roadmap.py`, one step in `.github/workflows/validate.yml` after WS-12.
- **Next step:** larry: finish Phase A (plan §2) and dispatch WS-12; then dispatch B1–B3 to Codex and B4 to Claude. codex: confirm B1–B3 and the log-file format when claiming them.
- **Updated:** 10-02

</details>

<details id="ws-05">
<summary>WS-05 — Model access: subscriptions, APIs and SAYGM · Codex</summary>

**Workstream:** Model Use Enhancements MAR-A…J (checklist in §7)

- **Owner:** `codex`
- **Status:** claimed
- **Implemented by:** Not itemized for every foundation component; WS-02 isolation is Codex
- **Remaining work / acceptance:** Codex; Larry for live account/deployment steps
- **Model version:** not recorded; do not infer from system name.
- **Where:** `codex/isolated-20260924`
- **Plan:** `docs/plans/MORTIMER_MODEL_USE_ENHANCEMENTS_PLAN.md`
- **Scope:** `jarvis/model_routing.py`, `jarvis/model_preferences.py`, `config/model_access.yaml`
- **Next step:** Begin MAR-A against verified production `39fc6f9`, then capture live route/capability evidence. Read-only 10-02 check: no MAR-A change has landed since the claim; `config/model_access.yaml` still defaults to `direct_api`, with no automatic paid fallback. The route rollout remains gated.
- **Updated:** 10-02

</details>

<details id="ws-17">
<summary>WS-17 — Command Console CC7a: conversation-first stage · Claude implementation, Codex review</summary>

**Workstream:** Larry, 09-30: conversation is spread over one tab per turn, only Mortimer's side shows, the tab strip fills up, and asking again re-fetches. Increment CC7a of the Command Console plan (WS-09's plan): one conversation thread with both sides, results as inline cards, Recents instead of tabs, reuse a fresh result by subject.

- **Owner:** `claude` (implementation); `codex` reviews every increment before merge
- **Status:** in-progress: CC7a.1 landed (PR #140, `1a0aac7`, Codex reviewed) and deployed in `39fc6f9`; CC7a.1b is open in PR #147 with passing checks but a merge conflict; UI2-22 Mac check and CC7a.2–.4 remain open
- **Implemented by:** Claude (Cowork): CC7a.1
- **Remaining work / acceptance:** CC7a.1-CC7a.4, each a reviewed PR; RELEASE_READINESS UI2-22..UI2-25 on the Mac. UI2-04, UI2-09 and UI2-13 are held until then. Approved design: `docs/interface-research/cc7a/cc7a-approved-design-2026-09-30.html` (transcript rows, compact cards, Recents menu, reuse reference line, no-jump notice); Codex's boundaries in plan §7.2.
- **Model version:** not recorded; do not infer from system name.
- **Where:** main (CC7a.1); PR #147 branch `ws17/cc7a1b-single-console-row` (unmerged)
- **Plan:** `docs/plans/MORTIMER_COMMAND_CONSOLE_ATLAS_PLAN.md` §7.1 item 9 and §7.2
- **Scope:** `App/ResponseResultRouter.swift`, `Stores/WorkspaceStore.swift`, `Stores/ConversationStore.swift`, `Console/AdaptiveStageView.swift`, `Console/TopBarView.swift`, `Display/WorkspaceView.swift`, `App/AppMessageRouter.swift` (weather's select-on-arrival only), voice result actions (`App/ConsoleActionCoordinator.swift`, `App/ConsoleActionRegistry.swift`, JarvisKit `ConsoleProtocol.swift`, `jarvis/bot/console_protocol.py`), DisplayPayload `subject_key` (JarvisKit + `jarvis/bot/display.py`), weather tools' reuse check; tests for each
- **Next step:** Claude resolves PR #147 against current main and Codex reviews that increment before merge; Larry checks UI2-22 on the deployed conversation view. Then CC7a.2 adds inline cards without focus stealing, including weather. The WS-18 fix is merged but awaits deployment and a physical device-switch check.
- **Updated:** 10-02

</details>

<details id="ws-12">
<summary>WS-12 — CI upkeep before the Ubuntu 26 runner switch · Claude (proposed)</summary>

**Workstream:** Update the GitHub Actions versions (Node 20 deprecation warnings on `actions/checkout@v4` and `actions/setup-python@v5`) and pin `runs-on: ubuntu-24.04` before `ubuntu-latest` moves to Ubuntu 26 on 10-19.

- **Owner:** `claude`
- **Status:** proposed
- **Implemented by:** not started
- **Remaining work / acceptance:** Claude drafts; Larry reviews (the `.github/**` files are on the self-edit deny list, so this is a human-merged PR)
- **Model version:** not recorded; do not infer from system name.
- **Where:** new branch from `origin/main` when claimed
- **Plan:** none (small change; the PR body is the record)
- **Scope:** `.github/workflows/*.yml`
- **Next step:** Larry dispatches the proposed CI update; Claude claims it before changing workflows. Checked 10-02 on main: all three workflows still use `ubuntu-latest`, `actions/checkout@v4` and `actions/setup-python@v5`; `validate.yml` also uses `actions/setup-node@v4`. The planned runner transition remains an upcoming dependency, not a completed update.
- **Updated:** 10-02

</details>

<details id="ws-13">
<summary>WS-13 — T5 mail, calendar and brief: review the draft plan against current main · Claude (proposed)</summary>

**Workstream:** Review `MORTIMER_MAIL_CALENDAR_BRIEF_PLAN.md` (DRAFT, 2026-08-26) against today's main before anyone builds T5. Docs only.

- **Owner:** `claude`
- **Status:** proposed
- **Implemented by:** not started
- **Remaining work / acceptance:** Larry approves or revises the plan
- **Model version:** not recorded; do not infer from system name.
- **Where:** docs branch when claimed
- **Plan:** `docs/plans/MORTIMER_MAIL_CALENDAR_BRIEF_PLAN.md`. Codex edited this plan on 09-26, so coordinate with Codex before any edit. Migration `0035` stays reserved for T5.
- **Scope:** that plan file only
- **Next step:** Larry picks it; confirm with Codex that it has no pending edits to the plan
- **Updated:** 10-02 (read-only: plan remains draft and no T5 code/claim found)

</details>

### Built: live acceptance or status publication still open

<details id="ws-18">
<summary>WS-18 — Native audio: survive an output switch during speech · Claude</summary>

**Workstream:** Larry, 09-30: Mortimer crashed at 18:09:08 after switching from AirPods to the Mac speaker mid-answer. Log: the engine rebuilt (`audio engine rebuilt after configuration change`), Voice Processing then reported `failed to run downlink DSP (state fault)`, and `AVAudioPlayerNode.play()` raised `player did not see an IO cycle` five seconds later (uncaught Objective-C exception, SIGABRT).

- **Owner:** `claude`
- **Status:** landed in PR #144 (`c2f0f49`); not in verified production `39fc6f9`; physical acceptance open
- **Implemented by:** Claude (Cowork)
- **Remaining work / acceptance:** Larry switches AirPods to Mac speaker and back while Mortimer is mid-answer, both directions: the app stays up, with at most a short gap in his voice; the log shows `audio output flowing` after each rebuild.
- **Model version:** not recorded; do not infer from system name.
- **Where:** main (PR #144, `c2f0f49`)
- **Plan:** `docs/plans/MORTIMER_NATIVE_AUDIO_TRANSPORT_PLAN.md` (progress entry 2026-09-30)
- **Scope:** `macos/JarvisKit/Sources/JarvisKit/AudioEngineIO.swift`, `macos/JarvisKit/Sources/JarvisKitObjC/`, `macos/JarvisKit/Package.swift` (new ObjC target), `JarvisFlags.outputIOWatchEnabled` in `JarvisConfig.swift`, `AudioEngineIOTests.swift`
- **Next step:** Deploy a frozen main candidate, then Larry switches AirPods to Mac speaker and back during speech and checks for continued output and `audio output flowing`. The source rollback switch is `JARVIS_AUDIO_OUTPUT_WATCH=false`; the Objective-C `play()` catch remains.
- **Updated:** 10-02

</details>

<details id="ws-01">
<summary>WS-01 — Reliability, privacy and memory gaps · Codex</summary>

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

<details id="ws-02">
<summary>WS-02 — Subscription runtime isolation · Codex</summary>

**Workstream:** Subscription runtime isolation (GC24-04)

- **Owner:** `codex`
- **Status:** landed; deployed since `539f8f6` and present in production `39fc6f9`; live capability/isolation gates open
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

**Workstream:** Skills Workspace and skill creation (T6; supersedes `MORTIMER_SKILL_AUTHORING_PLAN.md`). Its own view, separate from the Workflow Viewer (Larry, 09-27)

- **Owner:** `codex`
- **Status:** in-progress: PRs #145 (`9da99d4`) and #146 (`92e9528`) merged; Versions dormant-auth wording, partial UI audit and native/performance evidence are on main but not deployed in production `39fc6f9`; SW-B and SW-C remain the only accepted gates (2/12); activation remains off
- **Implemented by:** Codex
- **Remaining work / acceptance:** Codex; Larry for human review and physical acceptance
- **Model version:** not recorded; do not infer from system name.
- **Where:** `codex/ws03-live-acceptance-20260930` (acceptance work); foundation on main (`539f8f6`)
- **Plan:** `docs/plans/MORTIMER_SKILLS_WORKSPACE_IMPLEMENTATION_PLAN.md`
- **Scope:** `jarvis/skill_*.py`, `jarvis/agent_skills.py`, `jarvis/selfedit/skill_policy.py`, `/api/skills*` in `jarvis/admin/server.py`. The five console view-mode Swift files are **shared with WS-07's landed Workflow Viewer**: add a new `skills` mode beside `workflows`; do not replace or restyle the viewer.
- **Next step:** Deploy and visually verify the merged Versions explanation, then run recorded-run/voice/accessibility, physical-display and real-VM checks against a frozen release. Owner-scoped Versions, runtime inventory and creator await WS-04 local authenticated client onboarding; provider evaluation, activation and rollback remain separate gates.
- **Updated:** 10-02

</details>

<details id="ws-04">
<summary>WS-04 — Remote access · Codex; Larry decides activation</summary>

**Workstream:** Remote access T2: bearer tokens, fail-closed bind, Tailscale

- **Owner:** `codex` (Larry, 09-27)
- **Status:** in-progress: R2 local-only design and separate remote-bind guard merged in PR #149 (`a39136a`), but not deployed in production `39fc6f9`; token provisioning and enabled-mode acceptance remain open; production authentication remains dormant
- **Implemented by:** Codex (remote foundation and R1)
- **Remaining work / acceptance:** Codex prepares local-only onboarding; Larry separately decides activation and any remote bind
- **Model version:** not recorded; do not infer from system name.
- **Where:** main (R1 foundation `539f8f6`; R2 guard PR #149 `a39136a`); further onboarding work on `codex/ws04-local-onboarding-20260930`
- **Plan:** `docs/plans/MORTIMER_REMOTE_ACCESS_PLAN.md` (R1 implemented; R2 local-only onboarding design)
- **Scope:** `jarvis/auth.py`, `jarvis/authmw.py`, `jarvis/bind.py`, `jarvis/urls.py`, `jarvis/bot/server.py`, auth middleware and bind in `jarvis/admin/server.py`. Plus the integration points in CX-11: `jarvis/bot/status_tool.py`, `scripts/deploy_main.sh` health checks, `mcp_servers/mcp_selfedit/logic.py` headers. The R2 design proposes `scripts/provision_local_auth.py`, a small JarvisKit stdin-to-Keychain executable, its `Package.swift` target, and tests; no provisioner is implemented.
- **Next step:** Larry selects the local token-onboarding method (supervised deploy setup, one-time CLI, or Mac pairing). Then Codex implements and tests the chosen vault/Keychain path and corrects the R2 plan header, which still calls the merged guard branch-only. Preparation does not itself enable auth; local activation and any remote bind remain separate decisions.
- **Updated:** 10-02

</details>

<details id="ws-06">
<summary>WS-06 — Self-service recovery and model registry · Claude implementation; Larry acceptance</summary>

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

**Workstream:** Voice workflows phases 1–4, Workflow Viewer, #80 privacy fix, DEPLOY-MAIN

- **Owner:** `claude`
- **Status:** landed (main `0b76f49`); thread-text fix landed 10-02 from branch `fix/ws07-bot-text-once`; Larry's thread check open
- **Implemented by:** Claude
- **Remaining work / acceptance:** Larry: switch the reply guard from `log` to `correct` once the live log shows its precision. Recounted 09-30: the bot log holds four guard events (09-25, 09-29 twice, 09-30), all `action=logged kind=refusal`; the other `reply_guard=log` lines are startup settings, not events. Still not enough to judge precision. Backlog F1 (retry guard vs a different place) is in this area. Thread text once (10-02 fix): on a build that contains it, Larry sees each spoken answer once in the conversation thread (UI2-22).
- **Model version:** not recorded; do not infer from system name.
- **Where:** main
- **Plan:** `docs/plans/MORTIMER_VOICE_WORKFLOWS_PLAN.md`, `docs/plans/MORTIMER_WORKFLOW_VIEWER_PLAN.md`
- **Scope:** —
- **Next step:** larry: deploy, then check one spoken answer in the thread (shows once). larry: guard-mode decision after more live use (four events so far).
- **Updated:** 10-02

</details>

<details id="ws-08">
<summary>WS-08 — Crystal orb, single shell · Larry accepted; receipt PR open</summary>

**Workstream:** Orb crystal glass (#90), revised to use the crystal shell exclusively

- **Owner:** `codex`
- **Status:** accepted by Larry on 09-30; implementation deployed since `c3607e6` and present in production `39fc6f9`; acceptance-status PR #142 remains open with merge conflicts
- **Implemented by:** Claude original crystal-glass workstream; Codex rendering performance fixes and single-shell cleanup
- **Remaining work / acceptance:** No further product acceptance requested: Larry explicitly accepted WS-08 overall. PR #142 must reconcile its roadmap/plan/receipt updates with current main before the acceptance record is published. The 09-29 evidence covers deployment, five fixtures, compact/expanded appearance and Reduce Motion; it does not separately itemize every live state and placement.
- **Model version:** not recorded; do not infer from system name.
- **Where:** main (PR #112, `e9388fc`; acceptance evidence PR #115, `8222940`)
- **Plan:** `docs/plans/MORTIMER_ORB_CRYSTAL_GLASS_PLAN.md`
- **Scope:** Orb rendering, orb-specific configuration, performance/visual regression tests, and this plan's acceptance evidence.
- **Next step:** Codex resolves PR #142's documentation conflict and lands the existing acceptance receipt; do not repeat accepted visual checks.
- **Updated:** 10-02

</details>

<details id="ws-09">
<summary>WS-09 — Command Console and Atlas acceptance · Larry acceptance</summary>

**Workstream:** Command Console and Atlas release acceptance

- **Owner:** `larry`
- **Status:** landed (PR #99, `4986c10`) and present in production `39fc6f9`; Mac acceptance remains open, with UI2-04/09/13 dependent on WS-17
- **Implemented by:** Codex (Codex desktop; exact model build is not exposed)
- **Remaining work / acceptance:** Larry (Mac/live acceptance)
- **Model version:** not recorded in a handoff receipt.
- **Where:** [PR #99](https://github.com/Larryfix71566/jarvis-voice-ai/pull/99), merged to `main` as `4986c10`
- **Plan:** `docs/plans/MORTIMER_COMMAND_CONSOLE_ATLAS_PLAN.md`
- **Scope:** —
- **Next step:** Complete unaffected physical acceptance on the deployed build. Reconcile the WS-09 response-routing runbook with CC7a before UI2-04/09/13: it still describes one full answer in a result card and brief conversation captions, while CC7a.1 now shows full transcript rows and does not create a WorkspaceResult for ordinary spoken answers.
- **Updated:** 10-02

- [ ] **Single transcript surface (Larry, 2026-09-28):** keep the transcript in the main window; remove the duplicate transcript/captions from the left/compact panel and reclaim the vacated space. Preserve the orb, speaker feedback, microphone/voice controls, and main-window transcript history/accessibility. This supersedes earlier requirements to repeat brief captions in the compact rail; full response/results routing remains unchanged.
  - **Status:** Landed in `main` via PR #99 (`4986c10`) and included in production `39fc6f9`; implementation and automated validation complete; user/Mac acceptance remains open.
  - **Implementation owner:** Codex, explicitly dispatched by Larry on 2026-09-29; follows the Codex/Luna handoff specification. **Acceptance:** Larry. **Plan author:** Codex.
  - **Scope:** `macos/MortimerHost/Sources/MortimerHost/Console/OrbFieldView.swift`, `macos/MortimerHost/Tests/MortimerHostTests/CompactConversationTests.swift`, this roadmap and the linked plan progress only.
  - **Implementation handoff:** [WS-09 transcript cleanup — Luna implementation handoff](docs/plans/MORTIMER_COMMAND_CONSOLE_ATLAS_PLAN.md#ws-09-transcript-cleanup--luna-implementation-handoff).
  - **Validation:** focused compact transcript tests 3/3, live response stream 2/2, result router 7/7; full MortimerHost 374 passed, 7 environment-dependent skips, 0 failures. `git diff --check` passed. Render captures inspected at compact widths 512 and 1000; paths and details are in the linked plan.
  - **Log (2026-10-02 review):** PR #99 merged as `4986c10`; Codex’s layout-v2-only compact caption removal is in production `39fc6f9`. WS-17 CC7a.1 subsequently changed ordinary spoken-answer placement in layout 2; that separate behavior is not a WS-09 transcript-cleanup regression. Mac acceptance of the compact-panel cleanup is still unrecorded. Source retains the “Microphone muted” indicator, but automated coverage does not explicitly assert that exact compact status yet.
  - **Close when:** live user and Mortimer speech updates the main-window transcript without a duplicate in the compact rail, in single- and multi-monitor layouts; no blank transcript-sized gap or loss of voice controls/history.

</details>

<details id="ws-10">
<summary>WS-10 — Automatic memory rollout · Claude + Codex implementation; Larry rollout</summary>

**Workstream:** Memory automation: staged enablement on the Mac

- **Owner:** `larry`
- **Status:** pending merged-pipeline acceptance
- **Implemented by:** Claude: echo guard and auto-settlement; Codex: durable admission/classification and merge integration
- **Remaining work / acceptance:** Larry: merged-pipeline acceptance and staged rollout
- **Model version:** not recorded; do not infer from system name.
- **Where:** main (merged pipeline deployed from `539f8f6`; present in production `39fc6f9`)
- **Plan:** `docs/plans/MORTIMER_MEMORY_AUTOCONSOLIDATION_PLAN.md`
- **Scope:** —
- **Next step:** CX-07 is resolved in main and deployed (§4). Production admission remains fail-closed according to the last recorded memory status (09-25); this review did not remeasure live stage/benefit/cost. Larry chooses staged Mac enablement only after the recorded monitoring gate.
- **Updated:** 10-02 (read-only; no new live memory gate)

</details>

<details id="ws-11">
<summary>WS-11 — Adaptive interface C8 acceptance · Larry acceptance</summary>

**Workstream:** Adaptive interface C8 acceptance

- **Owner:** `larry`
- **Status:** open (Mac only)
- **Implemented by:** Not attributed by this acceptance-only workstream
- **Remaining work / acceptance:** Larry
- **Model version:** not recorded; do not infer from system name.
- **Where:** —
- **Plan:** `docs/plans/MORTIMER_ADAPTIVE_INTERFACE_PLAN.md`
- **Scope:** —
- **Next step:** `docs/acceptance/adaptive-interface/RELEASE_READINESS.md` still has 3 of 26 UI2 items checked (UI2-01, UI2-04a, UI2-21). UI2-04/09/13 wait for WS-17. Its header still calls `94a5641` the last recorded deployment and the shared runbook describes pre-CC7a answer routing; the acceptance owner must update both against `39fc6f9` before using them for a frozen-candidate sign-off.
- **Updated:** 10-02

</details>



### Completed: accepted product work and closed documentation reviews

Accepted product workstreams and closed documentation reviews are listed below; implementation milestones also appear in §6.

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
- **Remaining work / acceptance:** None for this capture gate. Larry's DEPLOY-MAIN for `c3607e6` passed phase A: the real ScreenCaptureKit protected-window test executed and passed (4.825 s), MortimerHost ran 383 tests with six unrelated skips and zero failures, JarvisKit ran 218 tests with zero failures, and Python had 4,924 passes and seven skips. Phase D reported healthy services and matching code, production and app-bundle revisions. Larry later accepted WS-08 overall; its documentation PR #142 remains open.
- **Model version:** not recorded; do not infer from system name.
- **Where:** main (PR #117, `c5781a8`; PR #121, `c3607e6`); acceptance status on `codex/ws16-protected-capture-20260929`
- **Plan:** `docs/plans/MORTIMER_PROTECTED_WINDOW_CAPTURE_GATE_PLAN.md`
- **Scope:** `macos/MortimerHost/Tests/MortimerHostTests/ProtectedDisplayContentTests.swift`, this row's plan and acceptance evidence, and `ROADMAP.md` status only. Product display code remains outside this row; WS-15 owns `Display/DisplayContentView.swift` while active.
- **Next step:** None for WS-16.
- **Updated:** 10-02 (status cross-check only)

</details>

---

## 3. Reserved shared numbers

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

---

## 4. Conflict register

Open means not yet resolved. Each entry names who resolves it.

| ID | Conflict | Resolves | State |
|---|---|---|---|
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

- 2026-10-02 (WS-07 fix: Mortimer's lines doubled in the thread): Claude (Cowork). Larry saw each Mortimer line twice, interleaved, in the CC7a thread; the LLM context and the server transcript held it once. Cause: pipecat's RTVI observer sends one `bot-llm-text` per LLM text frame; the LLM pushes token frames and ReplyGuard (`log` mode in production) pushes new sentence frames, so the app received both. Fix: the observer ignores frames pushed by the LLM itself (`rtvi_observer_params`, `build_task`); every LLM frame is still reported once when the guard passes it on, and the thread shows what is spoken. Reproduced and pinned in `tests/unit/test_rtvi_bot_text.py`. Remaining: Larry's thread check on a build that contains it (UI2-22).

- 2026-10-02 (WS-20 proposed): Claude (Cowork), at Larry's request. Plan `docs/plans/ROADMAP_JOINT_WORKING_PLAN.md`: finish the catch-up after WS-19 (PRs #138, #142, #147, #152; deploy main; Larry's WS-18 and thread checks), then stop the drift with four changes Larry chose: the change log in `docs/roadmap-log/`, one production line, rows written as they read after merge, and `scripts/check_roadmap.py`. Evidence: 53 of the 55 merges since 09-28 edited `ROADMAP.md`; 9 PRs needed 12 merge-from-main fix-ups; eight rows state current production and go stale at the next deploy. Larry chose that each system fixes its own rows; Phase B ownership stays proposed until he dispatches it.

- 2026-10-02 (WS-19 publication): PR #151 merged the full roadmap reconciliation as `cfa0d2d` after five passing checks. The readable expandable preview was regenerated from that merged revision. This follow-up records the docs-only review as closed; it does not close any product deployment or acceptance gate.

- 2026-10-02 (WS-19 full repository/roadmap review): Codex compared all 18 pre-existing §2 workstreams with `origin/main` `a39136a`, tracked source/configuration, plan and acceptance headers, three open PRs, CI, and the latest DEPLOY-MAIN log. Verified production is `39fc6f9` (09-30 17:53 EDT; Python 4,938 passed/7 skipped, MortimerHost 416 with six skips/zero failures, JarvisKit 219/zero failures; matching bundle/service revisions). Corrected main-versus-production wording for WS-02/03/04/09/10/18, recorded PR #146/#149 merges, the pending PR #147 and #142 conflicts, and Larry's WS-08 overall acceptance without inventing a per-state observation matrix. Moved bounded WS-14 probe work to Completed based on its recorded daily-probe pass and Codex review; WS-06 overall checks stay open. Noted that the adaptive readiness header and shared acceptance runbook still describe older deployments/response routing. WS-03 remains 2/12 accepted; WS-04 auth and remote bind remain off in production; no new live gate was closed. `ROADMAP.md` local links resolve (10 checked). This entry is a read-only evidence reconciliation, not a release or activation receipt.

- 2026-09-30: Codex WS-04 added the R2 remote-bind gate on its isolated branch. With `JARVIS_AUTH_ENABLED=true`, a remote host still resolves to loopback unless `JARVIS_REMOTE_BIND_ENABLED=true`; auth-off remains loopback regardless. Existing remote tests now opt in explicitly. Focused auth/bind/caller/bot tests pass 109/109, including the real admin and bot startup host arguments; no token or production setting changed.

- 2026-09-30: Codex WS-04 selected the supervised local-only onboarding design in Addendum R2. It reserves `JARVIS_REMOTE_BIND_ENABLED` as a separate remote-listener gate, specifies vault/Keychain provisioning without an HTTP mint endpoint, and separates preparation from later local auth activation. This planning change creates no token, changes no runtime flag, and opens no listener; implementation and live acceptance remain open.

- 2026-09-30: Larry assigned Codex a local-only WS-04 token-onboarding design to unblock owner-scoped Skills acceptance. This claim reserves `codex/ws04-local-onboarding-20260930`; it does not create tokens, enable authentication, or open a remote bind. The existing R1.9 choices and current caller/Keychain contracts will be reconciled in the WS-04 plan.

- 2026-09-30 (WS-18 added, in review): Claude (Cowork), at Larry's request. Crash at 18:09:08 after an AirPods to Mac speaker switch: engine rebuilt, Voice Processing downlink state fault, no output IO, `AVAudioPlayerNode.play()` raised `player did not see an IO cycle`. Fix: start the player only once output IO is seen to flow (watch rebuilds a stalled output, 3 tries then a visible session failure) and catch the Objective-C exception around `play()`. Rollback switch `JARVIS_AUDIO_OUTPUT_WATCH`. WS-17 row updated: CC7a.1 landed (#140) and deployed (`39fc6f9`).

- 2026-09-30: Codex WS-03 observed the connected production Skills library, a three-step intended Process walkthrough, and truthful no-trace Activity on app/backend revision `39fc6f9`. Versions returned expected fail-closed 503 with dormant bearer auth, despite a misleading generic UI error; the WS-03 branch adds exact-state wording and a partial live receipt. Focused native Skills rendering tests passed 20/20. No new SW-A–SW-L gate is accepted; creator/provider/activation remain off.
- 2026-09-30: WS-03 PR #145 passed all five CI checks and merged as `9da99d4`. It changes only the exact dormant-auth Versions explanation and documentation; production still reports `39fc6f9`. The live UI gates remain open until the merged build is deployed and tested.

- 2026-09-30: Larry directed Codex to resume WS-03. This docs-only claim reserves `codex/ws03-live-acceptance-20260930` for the remaining Skills Workspace acceptance work. The implementation is already deployed; no provider evaluation, runtime enforcement, skill activation, or new acceptance gate is claimed by this edit. Codex will first reconcile SW-A–SW-L evidence against current production, then run the target-Mac and real-VM checks with separate human review where required.

- 2026-09-30 (WS-15 fix, deploy blocker): Claude (Cowork). DEPLOY-MAIN for `1a0aac7` stopped on `RadarTileStoreTests.testDroppedDecodedTilesComeBackWithoutADownload` (kept PNG missing, second download). The radar kept PNGs in an `NSCache`, which may evict under memory pressure. Now a dictionary with an explicit 64 MB budget, oldest first, plus a budget test. Radar behaviour otherwise unchanged.

- 2026-09-30 (WS-17 CC7a.1 in review): Claude (Cowork). Layout 2 stage shows the conversation as transcript rows with both speakers' full text (was the last two entries cut at 160 characters); spoken answers no longer become workspace results or supporting-display panels; structured payloads unchanged. Switch `mortimer.interface.conversationThread` (on by default). Awaiting Codex review before merge.

- 2026-09-30 (WS-17 design approved; CX-15 resolved): Claude (Cowork). Larry picked transcript rows (over chat bubbles, so long replies read at full width), compact cards opened on the stage, the Recents menu, a reference line when a fresh result is reused, and a notice instead of a jump when a result arrives while another is open. Codex confirmed scope with boundaries; Claude checked each against main (`latestCaptions` = last two, 160-character captions; pin/unpin do not advance `inventoryRevision`; weather calls `select` on arrival; Log bound 200; workspace keeps 20 unpinned). Recorded in plan §7.2 and UI2-22..25; mockups in `docs/interface-research/cc7a/`. Next: CC7a.1.

- 2026-09-30 (full reconciliation): Claude (Cowork), at Larry's request. Rechecked every §2 block against main, the DEPLOY-MAIN receipts in `~/MortimerRollback/logs` and the live bot log. Production is `03b9e60` (09-30 12:45 EDT). Codex's PR #130 had already corrected WS-01 and WS-08. Corrected here: header; WS-02/03/04/09/10 name the current production; WS-10's "integrated locally" replaced (CX-07 resolved and deployed); WS-07 guard events recounted (four); WS-11 progress count and stale RELEASE_READINESS deployment header noted; WS-12 deadline confirmed (workflows unchanged); WS-05 no MAR-A commits since claim. Unchanged after checking: WS-06, WS-13, WS-14, WS-15, WS-16.

- 2026-09-30 (WS-15 accepted): Claude (Cowork). Larry accepted weather on the Mac: A1–A8 pass on production `03b9e60`; A6 (location off) answered from the internet connection, labelled approximate, never a remembered place. Receipt added; WS-15 moved to Completed; follow-ups F1–F5 added to the backlog.

- 2026-09-30 (WS-17 claimed): Claude (Cowork). Larry: one conversation tab with both sides, fewer tabs, reuse earlier results; build it into the adaptive interface with Claude implementing and Codex reviewing. Folded into the Command Console plan as CC7a (§7.2) before the release candidate; RELEASE_READINESS UI2-22..25 added and UI2-04/09/13 held; CX-15 registered for Codex's scope confirmation. Evidence: `ResponseResultRouter` creates one result per turn with assistant text only (up to 20 kept).

- 2026-09-30 (stable app signing): Claude (Cowork). Larry: the app asked for microphone and location on every deploy. Evidence: `codesign -d -r-` showed `designated => cdhash H"74b9..."`; bundle.sh signed ad hoc, so each rebuild was a new app to macOS. New `scripts/setup_signing_identity.sh` creates a local code-signing identity once per Mac; bundle.sh signs with it when present and falls back to ad hoc otherwise. Codex: bundle.sh is shared release tooling.

- 2026-09-29: Codex / WS-01 action-claim ordering fix landed in PR #125 (`ab2a2ef`) with all five checks passing. WS-08 PR #115 integrated that fix, passed all five checks, and merged as `8222940`. The CI race is closed; the original WS-01 live acceptance remains open.

- 2026-09-29: Codex / WS-08 acceptance evidence landed in PR #115 (`8222940`) after all five checks passed. The current fixtures and receipt are on main; Larry's explicit five-fixture approval and any unobserved named live states/placements remain open.

- 2026-09-29: Codex / WS-08 merged current main including the WS-01 claim-order fix from PR #125 into PR #115, preserving both WS-08 acceptance evidence and WS-01/WS-15 history. PR #115 CI must now rerun against the fixed backend before its acceptance-evidence merge.

- 2026-09-29: Codex / WS-08 reconciled deployment and acceptance after WS-16 closed. Larry's DEPLOY-MAIN installed `c3607e6` with release gates green; Larry reaffirmed compact/expanded appearance and Reduce Motion stillness. Codex regenerated five fixtures from the deployed orb source (focused CrystalOrbShellTests 7/0), reviewed their expected features against the checked-in references, and attached them to the WS-08 receipt. Final Larry fixture approval and any unobserved named live states/placements remain open.

- 2026-09-29: Codex / WS-01: PR #124 merged the action-claim repair claim. The bounded worker fix now settles self-edit and app-build terminal action receipts before publishing terminal job state under the same job lock. Four barrier tests cover success and error ordering; 97 focused admin tests pass. The full Mac unit run had 4,740 passes, three skips and two out-of-scope failures (audio-filter shared state; deploy-script log flush); Linux CI and merge into WS-08 PR #115 remain open.

- 2026-09-29: Codex / WS-01 claim proposed for PR #115's unrelated CI failure. Two full validation attempts failed in app-build/self-edit durable action-claim tests while the WS-08 PR changed only documentation and fixture PNGs; the three failing tests pass together locally. Source inspection finds both workers set the visible job to `done` before committing the corresponding terminal action claim, allowing a status poll to observe the old `claimed` state. This docs-only claim reserves a bounded ordering fix and deterministic regression tests on `codex/ws01-action-claim-order-20260929`; no backend code changes or CI checks are bypassed.

- 2026-09-29 (late, WS-15 radar smoothing): Claude (Cowork). Larry: the weather card works, but radar comes up slowly and flashes. Cause in code: each loop step removed the shown radar overlay and added the next one before its tiles were loaded, and no tiles were kept. Now all frames stay on the map with only the shown one visible, tiles are kept per map and warmed across frames after the visible tile loads, the loop steps only to loaded frames, and the card says "Loading radar…" until the first frame is in.

- 2026-09-29: Codex / WS-16 accepted after Larry's DEPLOY-MAIN of PR #121 (`c3607e6`): real ScreenCaptureKit protected-window test executed and passed (4.825 s); MortimerHost 383 tests, six unrelated skips, zero failures; JarvisKit 218/0; Python 4,924 passed and seven skipped. Production, app bundle and main match; services healthy. WS-08 visual and Reduce Motion acceptance remains open. Evidence: `/Users/larryfix/MortimerRollback/logs/deploy-mortimerhost-20260929-175921.txt` and `/Users/larryfix/MortimerRollback/release-c3607e6-20260929-175921`.

- 2026-09-29: Larry's DEPLOY-MAIN for `2ed1986` stopped in phase A; the protected-window capture test timed out waiting for `occlusionState.visible` before taking a screenshot. Production remained at `adeffc1`. Codex's WS-16 follow-up removes only that prerequisite and adds a third real capture to prove the local body rendered; four focused actual-capture runs and the full MortimerHost suite (383 tests, six unrelated skips, zero failures) passed in this worktree. Merge and a fresh DEPLOY-MAIN run remain open.

- 2026-09-29: Codex WS-16 capture repair landed in PR #117 (`c5781a8`) after all five PR checks passed. The merged candidate passed MortimerHost 383 tests, five unrelated skips, zero failures; the actual protected-window capture executed and passed. Larry's DEPLOY-MAIN run and production acceptance remain open.

- 2026-09-29: Codex merged main `adeffc1` (WS-15 radar-session fix) into WS-16, preserving both roadmap histories. Focused radar policy and real protected-capture tests passed without skips; full MortimerHost passed 383 tests, five unrelated skips, zero failures, including both tests. CX-14 is resolved; PR #117 review and DEPLOY-MAIN remain open.

- 2026-09-29: Codex merged main `05c4a40` into WS-16 while preserving Claude's WS-15 roadmap entry. The actual protected-window capture passed on the merged tree. Full MortimerHost ran 383 tests with six skips and two failures, both in the `URLSession.shared` policy test caused by WS-15's new `RadarMapView.swift`. Registered CX-14 for Claude; WS-16 does not edit WS-15 product code.

- 2026-09-29: Codex WS-16 removed only the app-active precondition after Larry's interactive Terminal capture also skipped. ScreenCaptureKit's real full-window comparison then passed four focused runs without skips and the full MortimerHost suite (374 tests, six unrelated skips, zero failures). PR #117 remains in review; production deployment is still open.

- 2026-09-29: Codex WS-16 claim landed in PR #116 (`5182bdf`). Codex changed only the protected-window test fixture: protected and body-only payloads now render in the same live window; the full-frame exact comparison remains, with bounded pixel-difference diagnostics. Full MortimerHost passed 374 tests, seven skipped, zero failures. The capture test skipped because this shell's test host could not activate, so foreground capture and DEPLOY-MAIN remain open.

- 2026-09-29 (late, WS-15 PR 2 fix): Claude (Cowork). DEPLOY-MAIN for `05c4a40` stopped in phase A with 3 MortimerHost failures: two assertions of MemoryGraphClosureC3Tests (the new radar tile overlay used the shared URL session; now its own ephemeral session) and the WS-16 protected-window capture test (pre-existing and environment-sensitive, owned by Codex). Production was not changed.

- 2026-09-29 (night, WS-15 PR 2): Claude (Cowork). PR 1 (#110) is deployed and its logs confirm `local_weather` with the device fix. PR 2 follows Larry's one-window decision: the weather card lives in the main window only and is selected on arrival. It holds the summary, now, alerts, 12 hours, 7 days, and Apple's map with the NOAA/IEM radar loop and a pin; radar past zoom 8 is enlarged so it stays at street level.

- 2026-09-29: Larry assigned Codex WS-16 after DEPLOY-MAIN for `d460809` stopped before production changes on the protected-window screenshot equality test. The logged captures differ in 21,946/1,041,600 pixels at the frame edge and body text; the central content matches. This docs-only claim reserves the test file and a separate worktree; it does not change product display code or relax the privacy assertion.

- 2026-09-29: Codex WS-08 deployment follow-up. Larry ran DEPLOY-MAIN against `d460809`; phase A stopped on the protected-window capture test after JarvisKit passed. Production remained `e340101`. Analysis of the two pixel arrays found 21,946/1,041,600 differing pixels, all at the frame edge or the body-text area (none 64 px inside). The test is outside WS-08's assigned source scope; deployment and live orb acceptance remained blocked pending a separately assigned repair.

- 2026-09-29: Codex WS-08 crystal-only implementation landed in PR #112 as `e9388fc`. The first `validate` run failed in an unchanged app-build timing test; that isolated test passed locally and the complete workflow passed on rerun. Sandbox controller and Knowledge base workflows also passed. Deployment and Larry's live orb checks remain open.

- 2026-09-29: Codex completed the WS-08 crystal-only source change and updated the existing orb plan/acceptance record. Removed the atom-orb legacy draw branch, `OrbShell` runtime selector, and `JARVIS_ORB_CRYSTAL` flag; retained the separate Silo wave and all crystal art values. JarvisKit 215/0, focused crystal tests 7/0, focused orb frame-time test 1/0 (4.933/14.150 ms p50/p95; empty p50 0.842 ms). Full MortimerHost: 374 executed, five skipped, one environment-sensitive protected-window screenshot mismatch; on base `0cc42f2` and the focused current run it skipped because WindowServer could not activate the test host. PR and Larry's post-deployment visual/Reduce Motion acceptance remain open.
- 2026-09-29 (evening, WS-15 PR 1): Claude (Cowork). Gates passed. G-1: IEM `/cache/` tiles and Weather.gov (7-day, hourly, alerts) answer from the Mac. G-2: the missing radar card was received but left unread, because `WorkspaceStore.receive` only activates a session's first result. G-3: Apple's map and IEM radar render in the ad-hoc-signed app, but tiles past z8 must be enlarged. PR 1 adds `local_weather` (place from this device, never memory), a 7-day forecast with humidity, wind, chance of rain and alerts, and wording so Mortimer stops denying it has radar.

- 2026-09-29 (evening, plan): Claude (Cowork) claimed WS-15 and added `docs/plans/MORTIMER_WEATHER_LOCATION_AND_RADAR_PLAN.md`. Larry chose Option A after the research: native Apple map, NOAA radar via IEM (5-minute updates, zoom 8, 50-minute loop), Weather.gov for today, 7 days, hourly and alerts, and a `local_weather` tool that never uses memory for the place. The plan has gates G-1 to G-3, steps S1–S8 and acceptance checks A1–A8. Device location confirmed working at 11:39 EDT. CX-07 moved back among the resolved conflicts (the 09-29 reorder listed it as open by mistake).

- 2026-09-29: Codex completed the required post-merge review of WS-14 PR #102 for CX-13. The review found no blocking code issue in the identity-only environment additions, shared CLI command resolution, failure-category mapping or fail-closed Codex capability gate. The GitHub review explicitly notes that live Mac Keychain/launchd evidence was taken from the PR and not independently reproduced. CX-13 is resolved; live subscription acceptance remains in WS-06.

- 2026-09-29 (night, later): Claude (Cowork), at Larry's request: §2 is grouped as needs work, then built and waiting on checks, then completed. §4 lists open conflicts first, and its table rows are now contiguous (blank lines had split the table). No block content changed.

- 2026-09-29 (night): Claude (Cowork) reconciled the roadmap with production `eb24e81`. The header now names the live release. WS-09 is recorded as deployed (PR #99 is in `eb24e81`), leaving only Mac acceptance. WS-06 check #2 now passes on data. `gh pr list` showed no open PRs. Codex was asked to confirm WS-01 to WS-05 itself (rule 9).

- 2026-09-29 (evening): Claude (Cowork). WS-15 gains Larry's radar report: no radar showed, and the map under it is wrong for the area. Found in code: the app stacks the nine radar tiles vertically instead of stitching a 3×3 map, at a coarse zoom 6. Why radar did not show at all is untested. The scope adds the Swift radar view (coordinate with WS-09).

- 2026-09-29 (later): Claude (Cowork). WS-14 landed (PR #102, `eb24e81`) and was deployed. The live daily check now shows the Claude subscription `ok: true`. Added WS-15 (proposed), Larry's weather rework: "current" weather took its place from memory (Spartanburg) because the device-location resolver feeds only `system_status` and the weather tools take only a city name; the app's location permission has read `not_determined` since 09-28; the radar symptom still needs Larry's description. Evidence came from read-only reads of logs.

- 2026-09-29: Claude (Cowork). WS-06 check #2 traced on the Mac with Larry. There were three causes:
  1. The CLI isn't on the launchd PATH. Larry linked it into `/opt/homebrew/bin`.
  2. The bot strips `USER`, so the CLI can't find its Keychain sign-in (`Not logged in`).
  3. The command variable fed only the installed check, and the probe discarded the runtime's failure category.

  Added WS-14 and CX-13 for fixes 2 and 3. Larry decided Claude lands them and Codex reviews. Targeted tests pass: 95 total, 18 of them new; the related status suites give the same result before and after. Protocol note: while checking for overlapping edits, Claude compared `jarvis/subscription.py` hashes in Codex's worktrees (read-only). That goes against rule 9 and won't be repeated. Future overlap checks go through this file and open PRs.

- 2026-09-29: Codex reconciled WS-09 after PR #99 merged to `main` as `4986c10`. The transcript cleanup is landed; deployment and Larry’s single-/multi-monitor acceptance remain open. The Console/Atlas plan now records the merge and notes that compact-v2 automated tests do not explicitly assert the “Microphone muted” status string, though the source retains that indicator. No deployment or application tests were run for this documentation update.

- 2026-09-28: Claude (Cowork). PR #100 added the self-service spec and its companion plan to main (CX-09 resolved) and corrected the Voice Workflows and Workflow Viewer plan status lines (WS-07). WS-06 now records the checks vetted against `539f8f6`: 1 closed, 2 nearly closed, subscriptions failing (`not_installed` in the 09-26 to 09-28 daily files), 7 open. WS-08 points to Claude's step-9 checklist. Added protocol rule 13 and proposed blocks WS-12 (CI upkeep) and WS-13 (T5 plan review). Evidence came from read-only reads of production files; no git was run.

- 2026-09-28: Codex prepared Larry’s requested Luna handoff under the existing WS-09 Console/Atlas plan after inspecting `OrbFieldView`, `AdaptiveStageView`, `LogTab`, and transcript/result tests at `2c73700`. The duplicate is the `captions` call inside `compactReadout`; main history/results are separate. Plan only, no application edits or newly passed gates; intended executor Luna awaits dispatch.

- 2026-09-28: Codex recorded Larry’s WS-09 requirement to keep the transcript in the main window and remove the duplicate from the compact left panel. Added the design amendment to the existing Console/Atlas plan; implementation remains unassigned and unchecked. No application behavior changed.

- 2026-09-27: Claude (Cowork) turned this file into the master tracker: protocol, workstreams WS-01…11, migration reservations, conflict register CX-01…10. Reconciled against main `0b76f49` and Codex's worktree `codex/isolated-20260924`. The previous content (deferred features) is §7, unchanged. Owners marked "proposed" await Larry's confirmation.
- 2026-09-27 (later): Larry's decisions. **CX-04:** workflows and skills are different objects, so they get separate views; WS-03 adds its own `skills` mode, with layout options shown before any Swift UI is built. **CX-06:** remote access (T2) is an undecided roadmap item; WS-04 is parked and Codex's T2 code moves to a parked branch; migration `0034` is held. CX-07 rewritten with the verified details.
- 2026-09-27 (later still): Larry: T2 stays with Codex. WS-04 is back to `codex`, in-progress on its branch, and will merge only dormant (auth off by default) until Larry decides to turn it on. The parked-branch step is removed. CX-11 lists the conflicts between T2 and Claude's landed work.
- 2026-09-27 (evening): Larry approved the recommended fixes. Addendum R1 is appended to `MORTIMER_REMOTE_ACCESS_PLAN.md`: auth off unless set to "true"; a service token for `system_status`; both sides kept in the watchers and `mcp_selfedit`; a guard test for unauthenticated internal callers; authenticated DEPLOY-MAIN health checks (`scripts/service_health.py`); migration `0034`; the route inventory recounted. WS-04 and CX-11 point to it.

- 2026-09-28: Codex WS-01/03/04 integration on `codex/isolated-20260924`: 22 of 31 conflicted files resolved; remaining nine are memory/CX-07 and Swift/navigation. Main remains `2e6f769`. Architecture and repo map now fit injected prompt caps. Targeted workflow, validation, auth, subscription, web and bundle checks pass; full suites await a coherent merged tree. R1 synthetic health/caller/token checks: 14 pass, human deny-list gate still fails as expected pending W1-REMOTE-HEALTH. No deployment or activation.

- 2026-09-28: Codex CX-08 reconciled the implementation-status fork: one current 5.8 KB status linked to ROADMAP and per-workstream evidence, with both the main and isolated-branch originals preserved in docs/archive. Historical full-suite counts and failed verifier evidence are explicitly separated from current targeted checks.

- 2026-09-28: Codex CX-05 archived the twelve overlapping F7 gap indexes with lossless body/link verification and redirects. Root independently verified all twelve normalized bodies against HEAD and 217 archive/stub links. Canonical index links were also checked by the docs agent (269 links total). Documentation regression checks: 16 pass; the endpoint integration check remains blocked by unresolved memory imports. Architecture (10,387 chars) and repo map (6,190 chars) retain required references within their prompt caps.

- 2026-09-28: Larry confirmed CX-07 ordering and Codex ownership, WS-03 separate top-level navigation, and CX-12 restoration of the three original Anthropic streaming flags. Implementation resumed in the isolated merge worktree; these approvals do not enable production features or authorize paid evaluations.

- 2026-09-28: Codex completed all merge resolutions. Final broad Python run: 4,851 passed, 2 expected pending human deny-list failures, 4 skipped. Subsequent historical-fixture correction/streaming-overlay regression: 59 passed, 3 legitimate migration-snapshot skips. JarvisKit: 219/0 failures. MortimerHost: 372 executed, 7 skipped, 0 failures. Evidence is in `docs/acceptance/skills-workspace/receipts/main-integration-2026-09-28/`; no deployment/activation, paid evaluation, physical-display acceptance or full release claimed.

- 2026-09-28: Larry committed and pushed both human-only release protections (617048a health probe, 1152dd5 frozen authoring fixtures). Codex verified them on the release branch; creator claim-race follow-up awaits Linux CI and merge before staged deployment.

- 2026-09-28: PR #95 merged as 1ec20d6; all GitHub workflows passed. Two DEPLOY-MAIN attempts stopped in phase A before production changes: Skills wide selection-to-layout p95 20.350/20.213 ms versus 20 ms; second attempt also failed orb crystal/legacy median ratio (7.415/4.766 ms, limit 1.5). Three standalone Skills runs passed narrowly (19.906/19.949/19.964 ms); they do not override the full-suite failures. Production remains 0b76f49. WS-03 performance follow-up remains Codex; requested Larry's ownership decision for WS-08 orb before edits.

- 2026-09-28: Larry explicitly assigned both Skills and orb rendering performance fixes to Codex in this task. WS-08 transfers to Codex on the isolated branch; this overrides the prior Claude ownership for the bounded performance fix. No threshold relaxation or visual redesign is authorized.

- 2026-09-28: Codex WS-03/08 rendering fixes pass the full MortimerHost suite (372 tests, 7 skips, zero failures): Skills wide layout p95 13.127 ms; orb crystal p50/p95 4.830/14.705 ms versus legacy p50 4.911 ms. Actual catalog-button regression passes separately. Ten crystal/legacy voice-state renders have identical decoded pixels. Test budgets and frozen visual constants are unchanged. Source and receipts await CI/merge; production stays 0b76f49.

- 2026-09-28 20:19 EDT: PR #96 merged as 539f8f6 and DEPLOY-MAIN completed. Exact-release checks: JarvisKit 219/0 failures, MortimerHost 372/7 skips/0 failures, Python 4,860 passes/7 skips/2 subtests. Code, bundle revision and all five services match production; admin/vault health 200 and bot 307, no receipt problems. DB/code/app rollback snapshot saved. Physical/live/provider/activation gates remain open. Receipt: `docs/acceptance/skills-workspace/receipts/rendering-performance-2026-09-28/deployment-receipt.json`.

- 2026-09-28: At Larry's WS-01/04 follow-up, Codex fetched/read main instructions, confirmed the branch was clean and current, and rechecked R1 in code. Corrected stale §3 migration reservations and §4 "merge pending/implementation open" labels. An isolated actual admin server returns 401 without auth and 200 via the service helper when enabled, and 200 without credentials when dormant; production was not changed. Live spoken `system_status` acceptance remains unrecorded.

- 2026-09-28: Codex / WS-01, at Larry’s request: converted the master workstreams to editable expandable Markdown with implementation/acceptance attribution, documented a common update format for both systems, and moved completed milestones to the bottom. Source baseline `180766e`; no runtime or acceptance status changed. Pending documentation PR merge.

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
- **Acceptance:** Larry accepted WS-08 overall on 09-30; its status/plan/receipt publication remains pending in conflicting PR #142.

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
