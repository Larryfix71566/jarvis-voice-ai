# Mortimer master roadmap

**Production:** `63aaeef0ed44163d619fe269d018554d6cfc682a`, deployed 2026-10-03 13:55 EDT (receipt `~/MortimerRollback/logs/deployment-receipt-63aaeef.json`).

This file is the single record of **who is doing what** in this repository, for every system that writes code here. Plans (`docs/plans/`) hold design. Receipts (`docs/acceptance/`) hold evidence. **This file holds ownership and state.**

**Last full reconciliation:** 2026-10-02, read-only review of every §2 block against `origin/main` `a39136a` (before the WS-19 claim), tracked code/configuration, plan and acceptance headers, open PRs, CI, and the 09-30 DEPLOY-MAIN log. That earlier deployment of `39fc6f9` passed Python 4,938 / 7 skipped, MortimerHost 416 / 6 skipped / 0 failures, JarvisKit 219 / 0; phase D reported admin/vault 200, bot 307, and matching source/bundle revision. PRs #143–#149 merged after that earlier deployment; the 10-02 release in the Production line above subsequently included their code. This review created no new live acceptance. Original evaluation: [cross-system evaluation](docs/reviews/CROSS_SYSTEM_PLAN_EVAL_2026-09-27.md).

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

### Needs work: not yet built (proposed, claimed, in progress, in review, blocked)

<details id="ws-20">
<summary>WS-20 — Roadmap joint working: catch-up and drift prevention · Claude + Codex</summary>

**Workstream:** Larry, 10-02: bring the roadmap and open PRs up to date so Claude and Codex can work on it together, and stop the roadmap drifting. Larry chose: each system fixes its own rows; the change log moves out of `ROADMAP.md`, one production line, rows written as they read after merge, and a drift checker; the plan lives in the repo.

- **Owner:** `claude` (B4 checker, plan) and `codex` (B1–B3, claimed by Codex on 10-02 at Larry's request)
- **Status:** in-progress: Phase A landed — plan #153, WS-07 fix #154, #138 closed, #142 merged as `d01f9af`; #147 and #156 merged after Codex's re-review (`1faa75f`, `ae70f2c`), and `ae70f2c` was deployed 10-02 19:23 with a clean receipt. B2's production line and event-wording sweep plus B3's after-merge/C1–C5 rules landed in #158 (`04eb3f0`). B4 landed in #156. B1 moves all 72 §8 entries to individual log files in PR #160.
- **Implemented by:** Codex (B1–B3); Claude (B4)
- **Remaining work / acceptance:** Phase A: #138 closed; #142, #147 and #152 merged; the 10-02 19:23 deployment and Larry's one-row, supporting-display and single-answer checks recorded; WS-18 AirPods and UI2-22 five-turn checks remain separate. Phase B: B1 log migration and checker warn-only rollout; WS-10/11 lifecycle wording awaits their acceptance owner; next 10 PRs merge without change-log conflict. Phase C rules are in §0.
- **Model version:** not recorded; do not infer from system name.
- **Where:** main (plan #153, B1–B3 claim #157, B2/B3 #158, B4 #156, B1 log migration #160).
- **Plan:** `docs/plans/ROADMAP_JOINT_WORKING_PLAN.md`
- **Scope:** B4 (Claude): `scripts/check_roadmap.py`, `tests/unit/test_check_roadmap.py`, the drift-check step in `.github/workflows/validate.yml`. B1–B3 (Codex): `ROADMAP.md` §0, §8 and production wording, `docs/roadmap-log/**`, and dated status/progress in `docs/plans/ROADMAP_JOINT_WORKING_PLAN.md`.
- **Next step:** codex: verify the merged log count and tell Claude the §8 anchor has moved. Both systems: monitor the next 10 PRs for change-log conflicts; the WS-10/11 acceptance owner corrects their lifecycle wording before CI leaves warn-only mode.
- **Updated:** 10-02

</details>

<details id="ws-05">
<summary>WS-05 — Model access: subscriptions, APIs and SAYGM · Codex</summary>

**Workstream:** Model Use Enhancements MAR-A…J (checklist in §7)

- **Owner:** `codex`
- **Status:** in-progress: bounded source/council/full-file, advisory and descendant/review repairs land via candidate #177; complete manual/public-crawl proof, representative workloads and rollout/account gates remain open; pinned tokenizer-image prerequisite scope #183 is merged before recipe edits
- **Implemented by:** Foundation contributions are not fully itemized; WS-02 isolation and MAR-A baseline work are Codex
- **Remaining work / acceptance:** Codex completes MAR-A evidence and subsequent open gates; Larry handles live provider/account and deployment decisions
- **Model version:** not recorded; do not infer from system name.
- **Where:** `codex/ws05-execution-20261005`; claims #175 (`66198c5`), #176 (`0b6723c`), #178 (`0960373`), #179 (`fb3e1aa`) and #180 (`4a2d4aa`); draft implementation #177, frozen ordinary source repair `50daa8b`; advisory scope #181 merged as `ac8eb7a` and integrated before edits; advisory budget/source/integration `6007479` / `c091d7e` / `5da9b47`; descendant budget/council/review `cc420bf` / `df80223` / `58b4e21`; preflight repair `7d74226`; prerequisite claim #182 merged as `d5d8cae` and integrated before hash/storage edits; tokenizer recipe scope #183 merged as `4d2a3ce` and integrated before edits
- **Plan:** `docs/plans/MORTIMER_MODEL_USE_ENHANCEMENTS_PLAN.md`
- **Scope:** model-access policy/execution/preferences and subscription-tool bridge only: `jarvis/model_routing.py`, `jarvis/model_preferences.py`, `jarvis/model_execution.py`, `jarvis/subscription.py`, `jarvis/subscription_tools.py`, `jarvis/saygm.py`, `jarvis/privacy_policy.py`, `config/model_access.yaml`; prospective route/billing/duration metadata in `jarvis/usage_ledger.py` and `jarvis/llm_client.py`; bounded privacy source/sink repairs in `jarvis/agents/delegate.py`, `jarvis/memory_model.py`, `jarvis/memory_extraction.py`, and `jarvis/memory_sweep.py` (enabled-mode policy/execution only; preserve routing-off compatibility); model-route endpoints in `jarvis/admin/server.py`, route diagnostics in `jarvis/status/`, model-execution integration in `jarvis/agents/base.py` and `jarvis/bot/model_route_tool.py`; `macos/MortimerHost/Sources/MortimerHost/Drawer/RepoTab.swift`, model-route types in `macos/JarvisKit/Sources/JarvisKit/AdminAPI.swift`; related model-access tests and verification/pilot scripts; `docs/plans/MORTIMER_MODEL_USE_ENHANCEMENTS_PLAN.md`, `docs/acceptance/model-use-enhancements/**`, shared architecture/model-route references. Additional bounded MAR-B/D/G scope, claimed before edits: `jarvis/model_budget.py` for optional task-level configured-price admission; typed host source/result classification and payload-free early MCP error sinks in `jarvis/skills/registry.py`; policy propagation/retrospective MCP-buffer redaction in `jarvis/runlog/store.py`; repository source-path traversal validation only in `mcp_servers/mcp_repo/logic.py`; canonical identity validation only in `jarvis/agents/upgrade_agent.py` and `jarvis/council/config.py`. Related tests stay in this row; do not alter skill permission declarations, sandbox authorization, model/endpoint pins or historical fixtures. No WS-17/WS-21 console/result files or self-edit allowlist edits. Further bounded execution/source scope claimed before edits: per-run route/profile snapshots, tool-result policy, shared limits and enabled-mode no implicit failover in `jarvis/agents/upgrade_agent.py` (including AppBuildAgent); `jarvis/development_sources.py` for host-proven development source classification and `jarvis/development_attestation.py` for authenticated creator source receipts; source-provenance adapters only in `jarvis/selfedit/service.py`, `jarvis/agents/workspace.py` and `jarvis/skill_authoring.py`; authenticated creator result transport only in `jarvis/bot/server.py` `_dispatch_creator` and `jarvis/admin/server.py` creator association/tool endpoints; host source/session snapshot and receipt verification only in `sandbox/workspace.py`, `sandbox/session.py` and `sandbox/files.py`. Preserve all sandbox read/write/ceremony permissions, authorization, publication/validation gates, runtime lifecycle and source exclusions; no host execution bypass, broader public-data grant, account activation or production change. Further bounded council/MCP scope claimed before edits: `jarvis/council/council.py` and `jarvis/council/__main__.py` for one coordinator budget, trusted child sponsorship through proposer/judge/shadow/planning/replay calls, checked member routes, cancellation and authenticated thread-context propagation; bounded council/planning/research job budget and host-source policy threading in `jarvis/admin/server.py`. `mcp_servers/mcp_selfedit/server.py`, `mcp_servers/mcp_selfedit/logic.py`, `mcp_servers/mcp_apps/server.py` and `mcp_servers/mcp_apps/logic.py` for hidden request/response source-metadata adapters only; authenticated ordinary self-edit preview/start/run/read/write/status/finish and app-build job/submit source transport in `jarvis/admin/server.py`; corresponding host source bindings in `jarvis/development_sources.py`, receipt variants in `jarvis/development_attestation.py` and source-before-sink integration in `jarvis/skills/registry.py`. Related tests remain WS-05. Preserve all model identities, explicit council tier/seed/effort choices, single observed-usage accounting, sandbox read/write/ceremony/publication/validation gates, inactive production flags and legacy routing-off behavior. No skill permission declarations, GitHub client/template rewrites, WS-17/WS-21 files or self-edit allowlist changes; unknown/private foreign application source still requires a real host approval. Further bounded advisory source transport scope claimed before edits: `jarvis/advisory_sources.py` for separate authenticated planning/research caller and retained-action proof, `mcp_servers/mcp_web/server.py` and `mcp_servers/mcp_web/logic.py` for hidden request/response metadata only, and `jarvis/research/crawl.py` for host-acquired source/origin evidence and confidential defaults for unverified bytes. Existing WS-05 Base/Registry/model-budget/admin/self-edit/attestation paths may bind the actual Developer or Analyst caller, original durable host budget, accepted input floor before operation, cancellation/deadline ownership and signed results before sinks. Preserve workspace and creator protocol separation, all permissions, explicit council membership/model floors, research workflow/scorer behavior, routing-off parity and manual-action authorization. JSON limits, bearer authentication, HTTPS or crawler success cannot grant source approval or money allowance; no UI changes, provider activation or broader public-data grant. Further bounded image-source prerequisite scope claimed before edits: `sandbox/artifacts.py` only for exact path/SHA-256 pins of independently reviewed synthetic credential test fixtures, plus directly related source-archive tests. Keep `SECRET`, all path/source exclusions, historical baseline pins and both scanner enforcement sites unchanged; no path-only/pattern exemption, fixture-body edit, permission/lifecycle/profile waiver or production settings change. This scope does not include sandbox runtime/control/images/setup behavior. Further bounded pilot-isolation prerequisite scope claimed before edits: new stdlib-only `jarvis/storage_context.py` for immutable host-owned database/preference overrides, context propagation and retained worker drain before temporary cleanup; `jarvis/db.py` only its default-path resolver, with explicit paths and all migrations/DDL unchanged. Existing WS-05 `jarvis/usage_ledger.py`, `jarvis/model_routing.py`, `jarvis/model_execution.py` and pilot scripts may read that host-only context and retain owned asynchronous worker lifetime; related tests verify real DB/ledger isolation, foreign-thread separation, cancellation/drain and legacy parity. Do not mutate process-global database/preference environment to isolate a pilot; no production storage, schema, limit, route, source approval or account setting change. Further bounded tokenizer-image prerequisite scope claimed before edits: `sandbox/guest/prepare.sh` only, to acquire the officially SHA-256-pinned English `punkt_tab` data required by locked NLTK/Pipecat, install it under the protected Python prefix (`.venv/share/nltk_data`) during fresh online image preparation, and prove cold tokenizer use before preparation completes. Related recipe/resource acceptance tests and receipts remain WS-05. Preserve current hydration/cache ownership and read-only worker access, all twelve profile checks, source scanner/exclusions, network/audio/clipboard isolation, operator credentials and installed image/settings pointers. No RTVI/voice/test assertion edit, sleep/skip/timeout waiver, runtime/control/images behavior change, provider/model/endpoint/allowlist change or production activation.
- **Next step:** codex: capture exact native4/full40 capability and finish research pilots; full40 harness parent-evidence review passes author82/independent111 overlapping checks; actual worker/desktop preflight passes and unchanged all12 baseline is terminal at `4e225f3` (ten passed checks; both Python checks fail the same three missing-tokenizer observer cases). Main recipe claim #183 is integrated; pinned tokenizer image `c43cc422…` is prepared and actual offline worker/default-prefix/hash/write-refusal/three unchanged RTVI/desktop probes pass. All12 unchanged baseline is live at frozen `4fd8228` (exec8389, primary `f6ccb30d4441`, verification `c11a71ad1cb3`). Native40 deterministic manifest/request order mismatch is repaired with author88/independent121 overlapping checks; finish exact full-menu named-reference protocol capture while normal native tools remain unapproved. CI7ff has three unit failures: portable receipt fixture is repaired locally54; diagnose two deadline phases and readonly baseline host-fixture ownership before closing verification. Crawler repair passes44 root/44 independent overlapping cases;10-06 catalog still has64 models/zero confidential. claude: cross-review draft #177 before merge. larry: pending manual-instruction privacy decision, operator-issued service identity for the isolated live full40 HTTP/source pilot, and later account/voice/deployment gates. Production routing/settings are unchanged.
- **Updated:** 10-06





</details>

<details id="ws-17">
<summary>WS-17 — Command Console CC7a: conversation-first stage · Claude implementation, Codex review</summary>

**Workstream:** Larry, 09-30: conversation is spread over one tab per turn, only Mortimer's side shows, the tab strip fills up, and asking again re-fetches. Increment CC7a of the Command Console plan (WS-09's plan): one conversation thread with both sides, results as inline cards, Recents instead of tabs, reuse a fresh result by subject.

- **Owner:** `claude` (implementation); `codex` reviews every increment before merge
- **Status:** in-progress: CC7a.1 (PR #140), CC7a.1b, one console row (PR #147, merged as `1faa75f`), CC7a.2, inline result cards (PR #164, Codex reviewed, merged as `9545641`) and CC7a.2b, a result asked for from the conversation opens (PR #169, Codex reviewed, merged as `63aaeef`), landed; CC7a.2 deployed in `9545641` on 10-02; CC7a.2b deployed in `63aaeef` on 10-03; CC7a.1b deployed in `ae70f2c` on 10-02 and Larry's Mac check passed the same day; CC7a.3–CC7a.4 remain
- **Implemented by:** Claude (Cowork): CC7a.1, CC7a.1b, CC7a.2, CC7a.2b
- **Remaining work / acceptance:** CC7a.1-CC7a.4, each a reviewed PR; RELEASE_READINESS UI2-22..UI2-25 on the Mac. UI2-04, UI2-09 and UI2-13 are held until then. Larry, Mac, 10-02, build `ae70f2c`: one console row with nothing below it in conversation, results and Knowledge Atlas (UI2-24's CC7a.1b part; its Recents parts wait for CC7a.3); Knowledge ▾ and Tools ▾ send content to the supporting display with no result open, and "Return display content here" brings it back; a spoken answer showed once in the thread. Larry, Mac, 10-03, build `9545641` (UI2-23): cards sat after their replies; Open showed the result and Conversation came back; pin, compare and close worked from a card and closing kept the Output record; after a layout 1 to 2 switch a new result arrived without taking the screen. A weather asked for from the conversation stayed a card; Larry decided it should open (CC7a.2b). After Codex's review of #169, only the answer to what he just asked opens: a background job finishing later stays a card, and with the supporting display open the conversation stays on the main screen. UI2-23 is rechecked on a build that contains CC7a.2b. UI2-22's five-turn check is not yet run. Approved design: `docs/interface-research/cc7a/cc7a-approved-design-2026-09-30.html` (transcript rows, compact cards, Recents menu, reuse reference line, no-jump notice); Codex's boundaries in plan §7.2.
- **Model version:** not recorded; do not infer from system name.
- **Where:** main (CC7a.1, CC7a.1b, CC7a.2, CC7a.2b); next increment on a new branch
- **Plan:** `docs/plans/MORTIMER_COMMAND_CONSOLE_ATLAS_PLAN.md` §7.1 item 9 and §7.2
- **Scope:** `App/ResponseResultRouter.swift`, `Stores/WorkspaceStore.swift`, `Stores/ConversationStore.swift`, `Console/AdaptiveStageView.swift`, `Console/ConversationThreadView.swift`, `Console/TopBarView.swift`, `Display/WorkspaceView.swift`, `App/AppMessageRouter.swift` (display arrivals: whether a result opens on arrival), voice result actions (`App/ConsoleActionCoordinator.swift`, `App/ConsoleActionRegistry.swift`, JarvisKit `ConsoleProtocol.swift`, `jarvis/bot/console_protocol.py`), DisplayPayload `subject_key` (JarvisKit + `jarvis/bot/display.py`), weather tools' reuse check; tests for each
- **Next step:** larry: on a build that contains CC7a.2b, ask for the weather from the conversation (it opens), again while reading another result (New notice, no jump), and a web search with the supporting display open (the conversation stays, the display shows it); then UI2-22's five-turn conversation. claude: CC7a.3 (Recents menu, voice result actions by number and subject), reviewed by codex, after WS-21 merges (CX-16). The supporting-display transfer defects found on `63aaeef` (10-03) are WS-21's.
- **Updated:** 10-03

</details>

<details id="ws-21">
<summary>WS-21 — Supporting display transfer: one validated, confirmed route · Claude implementation, Codex review</summary>

**Workstream:** Larry, 10-03, on deployed `63aaeef`: asked to put the weather radar on the external monitor, Mortimer said it was there while the supporting display opened empty (two `display_popout` calls, both `ok`). Codex's audit found five defects: a voice command that opens the window without content, success reported before the app confirms, detach accepting unknown results, screen IDs that placement does not recognise, and an incomplete contract and inventory. Repair: one coordinator for voice and pointer, validated before anything opens, confirmed before success is spoken.

- **Owner:** `claude` (implementation); `codex` reviews before merge
- **Status:** landed via PR #171 (Codex reviewed); Mac external-display acceptance open
- **Implemented by:** Claude (Cowork)
- **Remaining work / acceptance:** Codex re-reviews PR #171 after the repair of its 10-03 review (four defects: a refused request superseding a valid transfer, a failed replacement leaving an empty window, fixed-panel detach ignoring `screen_id`, the inventory missing transport results). Codex's audit tests and probes are archived in `docs/acceptance/supporting-display/codex-audit-2026-10-03/`, with regression twins in `VoiceDisplayAuditRegressionTests` and its four review probes in `SupportingDisplayTransferTests`. After approval, Larry merges and deploys, and runs the external-display checks on the Mac.
- **Model version:** not recorded; do not infer from system name.
- **Where:** `ws21/display-transfer`, PR #171
- **Plan:** `docs/plans/MORTIMER_SUPPORTING_DISPLAY_TRANSFER_PLAN.md`
- **Scope:** `jarvis/bot/ui_control.py`, `jarvis/bot/console_actions.py`, `UI_CONTROL_ADDENDUM` in `jarvis/prompts.py`; the display-transfer, panel and screen parts of `jarvis/bot/console_protocol.py`, JarvisKit `ConsoleProtocol.swift`, `App/ConsoleActionRegistry.swift`, `App/ConsoleActionCoordinator.swift` and the inventory in `Stores/WorkspaceStore.swift` (shared with WS-17, see CX-16); `App/UICommandRouter.swift`, `App/AppMessageRouter.swift` (console results for display transfers only), new `App/SupportingDisplayCoordinator.swift`, `App/MortimerHostApp.swift` (wiring only), `Placement/ScreenPlacement.swift`, `Placement/WindowPlacement.swift`, `Placement/DisplayPlacementPolicy.swift`, `Stores/PanelStore.swift`, `Display/DisplayWindowView.swift`, `Display/DisplayWindowStore.swift`, `docs/acceptance/supporting-display/**`, the display menus in `Console/ConsoleActionBar.swift` and `Display/WorkspaceView.swift`; tests for each
- **Next step:** codex: re-review PR #171 against the four review probes and the original scenarios (weather/radar transfer, repeated requests, stale result IDs, missing monitors, disconnect during transfer, the conversation remaining on the main screen). larry: merge and deploy after approval, then on the Mac with the external monitor: ask for the weather radar on the other screen (it appears there and Mortimer says so), ask again (already showing), ask with the monitor unplugged (Mortimer says it isn't connected), and check the conversation stays on the main screen.
- **Updated:** 10-03

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
- **Status:** landed in PR #144 (`c2f0f49`) and deployed in `7c4637e` on 10-02; physical acceptance open (Larry deferred the AirPods check, 10-02)
- **Implemented by:** Claude (Cowork)
- **Remaining work / acceptance:** Larry switches AirPods to Mac speaker and back while Mortimer is mid-answer, both directions: the app stays up, with at most a short gap in his voice; the log shows `audio output flowing` after each rebuild.
- **Model version:** not recorded; do not infer from system name.
- **Where:** main (PR #144, `c2f0f49`)
- **Plan:** `docs/plans/MORTIMER_NATIVE_AUDIO_TRANSPORT_PLAN.md` (progress entry 2026-09-30)
- **Scope:** `macos/JarvisKit/Sources/JarvisKit/AudioEngineIO.swift`, `macos/JarvisKit/Sources/JarvisKitObjC/`, `macos/JarvisKit/Package.swift` (new ObjC target), `JarvisFlags.outputIOWatchEnabled` in `JarvisConfig.swift`, `AudioEngineIOTests.swift`
- **Next step:** larry: when convenient, switch AirPods to the Mac speaker and back while Mortimer is mid-answer; the app stays up and the log shows `audio output flowing`. Rollback without a rebuild: `JARVIS_AUDIO_OUTPUT_WATCH=false`; the Objective-C `play()` catch stays.
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

**Workstream:** Skills Workspace and skill creation (T6; supersedes `MORTIMER_SKILL_AUTHORING_PLAN.md`). Its own view, separate from the Workflow Viewer (Larry, 09-27)

- **Owner:** `codex`
- **Status:** landed foundation: PRs #145 (`9da99d4`) and #146 (`92e9528`) merged after the 09-30 `39fc6f9` deployment; their Versions wording and evidence were included in the 10-02 `7c4637e` deployment, but the updated UI has not been visually accepted. SW-B and SW-C remain the only accepted gates (2/12); activation remains off
- **Implemented by:** Codex
- **Remaining work / acceptance:** Codex; Larry for human review and physical acceptance
- **Model version:** not recorded; do not infer from system name.
- **Where:** main (foundation `539f8f6`; PRs #145 and #146). The former `codex/ws03-live-acceptance-20260930` branch merged as PR #146; a fresh branch is required for further acceptance edits.
- **Plan:** `docs/plans/MORTIMER_SKILLS_WORKSPACE_IMPLEMENTATION_PLAN.md`
- **Scope:** `jarvis/skill_*.py`, `jarvis/agent_skills.py`, `jarvis/selfedit/skill_policy.py`, `/api/skills*` in `jarvis/admin/server.py`. The five console view-mode Swift files are **shared with WS-07's landed Workflow Viewer**: add a new `skills` mode beside `workflows`; do not replace or restyle the viewer.
- **Next step:** codex: visually verify the merged Versions explanation on deployed `7c4637e`, then run recorded-run/voice/accessibility, physical-display and real-VM checks against a frozen release. Owner-scoped Versions, runtime inventory and creator await WS-04 local authenticated client onboarding; provider evaluation, activation and rollback remain separate gates.
- **Updated:** 10-02

</details>

<details id="ws-04">
<summary>WS-04 — Remote access · Codex; Larry decides activation</summary>

**Workstream:** Remote access T2: bearer tokens, fail-closed bind, Tailscale

- **Owner:** `codex` (Larry, 09-27)
- **Status:** landed foundation: R2 local-only design and separate remote-bind guard merged in PR #149 (`a39136a`) after the 09-30 `39fc6f9` deployment; the guard was deployed in `7c4637e` on 10-02 with authentication and remote binding still off. Token provisioning and enabled-mode acceptance remain open
- **Implemented by:** Codex (remote foundation and R1)
- **Remaining work / acceptance:** Codex prepares local-only onboarding; Larry separately decides activation and any remote bind
- **Model version:** not recorded; do not infer from system name.
- **Where:** main (R1 foundation `539f8f6`; R2 guard PR #149 `a39136a`). The former `codex/ws04-local-onboarding-20260930` branch merged as PR #149; a fresh branch is required for provisioning work.
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

**Workstream:** Memory automation: staged enablement on the Mac

- **Owner:** `larry`
- **Status:** pending merged-pipeline acceptance
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

**WS-05 creator source receipt reservation before implementation, 2026-10-06:** Protocol kind `mortimer.development-source.v1`; random per-call challenge and exact owner/session/request/developer-run/revision/job/tool/argument/content/source bindings. The admin signer keeps its Ed25519 private key only in process memory. A public trust anchor may be atomically published at `.source-authority/admin-ed25519-public.json` under the already configured `MORTIMER_SANDBOX_HOME`; it is public verification material, not a provider credential or persistent plaintext secret. Verify canonical host-owned directory/file modes, reject symlinks and stale/replaced authority, and never trust a public key supplied by result JSON. No new env/config key, port, DB migration, vault entry or service-token reuse is reserved. Authentication/source policy cannot be weakened by this receipt.


**WS-05 council/source reservations, 2026-10-06 (Codex):**

- Costs database inline tables `model_task_budget_links(child_scope_id, parent_scope_id, created_at)` and `model_call_budget_reservation_scopes(reservation_id, scope_id)` reserve durable sponsorship and scope membership for a single estimated reservation per outbound attempt. Atomic admission checks every inherited owner/child ceiling and deadline; reopening a child with omitted/null sponsorship cannot drop its recorded owner. Actual `llm_calls` remains singular and separate. No `jarvis.db` migration number or production limit value is assigned.
- Host-only sealed `ChildTaskBudget` and optional execution/coordinator keyword bindings carry the authenticated tenant, exact originating request and cancellation owner. Provider/context JSON and historical telemetry IDs cannot mint sponsorship. Replay creates a fresh audit coordinator.
- Ordinary workspace receipt variant `mortimer.workspace-source.v1` and MCP request/response `_meta.mortimer_development_source` namespace reserve authenticated caller owner/session/run/call, retained sandbox job/session/task/commit, operation/argument/content/source and one-use challenge bindings. Reuse the process-memory admin signer and existing owner-only public anchor; preserve the separate `mortimer.development-source.v1` creator contract without inventing skill IDs/revisions for ordinary work. Hidden metadata is never a model schema argument or provider content. No new environment key, fixed port, launch label, credential, private-key file or auth activation.

**WS-05 advisory source receipt reservation before implementation, 2026-10-06 (Codex):** Protocol kind `mortimer.advisory-source.v1` reserves actual authenticated owner/session/run/agent/tool/call/arguments, accepted input floor, retained action and one-use challenge bindings for planning/research only. Reuse the process-memory signer and host-pinned public anchor; hidden metadata remains outside provider tool schemas. Preserve the separate creator/workspace kinds. Actual retained host sponsorship is required for cross-process budgets; serialized fields cannot grant allowance. No new environment/config key, fixed port, launch label, vault secret, private-key file, `jarvis.db` migration or production limit value is reserved.

## 4. Conflict register

Open means not yet resolved. Each entry names who resolves it.

| ID | Conflict | Resolves | State |
|---|---|---|---|
| CX-16 | WS-21 (supporting display transfer) edits the display-transfer, panel and screen parts of files in WS-17's scope: `console_protocol.py`, `ConsoleProtocol.swift`, `ConsoleActionRegistry.swift`, `ConsoleActionCoordinator.swift`, the `WorkspaceStore` inventory, and the display menu in `WorkspaceView.swift`. Both rows are Claude's; WS-17 has no open branch. | `larry` (10-03): new row WS-21; WS-17's CC7a.3 starts from main after WS-21 merges | open until WS-21 merges |
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
