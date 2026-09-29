# Mortimer master roadmap

This file is the single record of **who is doing what** in this repository, for every system that writes code here. Plans (`docs/plans/`) hold design. Receipts (`docs/acceptance/`) hold evidence. **This file holds ownership and state.**

**Last full reconciliation:** 2026-09-29, against main after PR #105. **Latest verified production:** `c3607e6` (PR #121 merge), deployed 09-29 18:04 EDT by DEPLOY-MAIN; this update records WS-16 acceptance only, not a full recheck of every workstream. Earlier blocks with older deployed revisions are covered by this release. Original evaluation: [cross-system evaluation](docs/reviews/CROSS_SYSTEM_PLAN_EVAL_2026-09-27.md).

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
| `codex` | Worktrees of `~/Documents/Codex/2026-09-09/can/work/active-repo`. Current: `codex-isolated-20260924`, branch `codex/isolated-20260924`. | Larry pushes the branch and opens the PR | `AGENTS.md` |
| `claude` | Cowork: Linux VM plus a bridge to the Mac, never runs git on the Mac. Claude Code: a GitHub clone. | A branch or patch plus a commit-message file; Larry commits and pushes unless the session has GitHub access | `CLAUDE.md` |
| `larry` | The Mac, production, the vault, GitHub | Merges PRs; deploys with `scripts/deploy_main.sh` | — |

---

## 2. Workstreams

- Scope locks only while status is `claimed`, `in-progress` or `review`.
- "(proposed)" next to an owner means Larry has not yet confirmed who owns the row.
- Expand a workstream for its editable fields. These blocks replace the former rows; the protocol’s references to a “row” mean the corresponding workstream block.
- Ordered by what still needs work (Larry, 09-29). When a block's status changes, move it to the matching group. Ids are stable, so links keep working.

### Needs work: not yet built (proposed, claimed, in progress, in review, blocked)

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
- **Next step:** Begin MAR-A: reconcile the deployed Mac checkout and capture live baseline evidence
- **Updated:** 09-29

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
- **Next step:** Larry picks it; Claude marks it `claimed` and drafts the change
- **Updated:** 09-28

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
- **Updated:** 09-28

</details>

<details id="ws-15">
<summary>WS-15 — Weather: fresh location and current radar · Claude</summary>

**Workstream:** Larry, 09-29: *"it is missing current radar and it defaults to memory for weather instead of checking current location and getting fresh weather."* A weather answer must use where Larry is now and show current radar for that place.

- **Owner:** `claude`
- **Status:** in-progress: PR 1 (#110) and PR 2 (#114 + #118 session fix) deployed; Larry confirmed the weather card works 09-29. Radar loaded slowly and flashed; smoothing fix in review.
- **Implemented by:** Claude (plan); code not started
- **Remaining work / acceptance:** Evidence from the 09-29 10:08 EDT session (`logs/agents/2026-09-29/`), read-only:
  1. **The location came from memory.** The voice model's delegation read *"typically in Spartanburg, SC or surrounding area"*. The analyst called `get_weather` and `get_weather_radar` with `"Spartanburg, SC"` and answered *"(assumed default, not confirmed device location)"*. Larry then had to name Charleston.
  2. **Cause in code.** The device-location resolver (`jarvis/bot/device_location.py`, order per D-L6: device fix, then IP, then "not available", never memory) is wired only into `system_status` ("where am I", `_location_answer` in `jarvis/bot/pipeline.py`). `mcp_web.get_weather(city)` and `get_weather_radar(city)` take only a city string, so "current" weather gets whatever place the voice model writes, which in practice comes from memory.
  3. **The app has not granted location since the rebuilds.** Its `location/hello` reported `authorization: not_determined` on 09-28 20:21 and 09-29 10:07. The last `authorized` hello with a fix was 09-25 22:58. So even a wired resolver would fall back to IP today. Why permission reset is untested; the app re-signing on rebuild is a candidate, not verified.
  4. **Radar ran, for the wrong place.** `get_weather_radar` ran and sent a window display payload three times on 09-29 (the RainViewer frame was about 8 minutes old); the first was for Spartanburg.
  5. **Larry, 09-29: "no radar showed up", and when radar does show, the map under it is wrong for the area.** Two separate issues:
     - **Map wrong for the area (cause found in code).** `get_weather_radar` returns nine zoom-6 tiles (a 3×3 grid about 1,900 km across; the tile maths for Spartanburg checks out at x=17, y=25). The docstring says the UI stitches them into a 3×3 grid, but `imagesStack` in `DisplayContentView.swift` renders them as a `ForEach` of nine separate full-width images stacked vertically, each with its own basemap. So the screen shows nine separate map squares in a column, not one map of the area. Zoom 6 is also too coarse for local radar, and there is no marker for the point.
     - **No radar at all (cause untested).** The server logged three `surface=window` radar payloads at 10:08–10:09, so it sent them. Whether the display window was open, whether later web-search results pushed the radar out of the supporting display (`maxSupportingStagePanels`), or whether the images failed to load has not been checked. It needs a live check with the display window open.
  6. **Device location works as of 11:39 EDT 09-29.** After the permission was granted: `authorization=authorized`, then a fix accurate to 35 m and 0.4 s old, labelled `Folly Beach, SC`. "Where am I?" answered "Folly Beach, South Carolina."

  Acceptance, now A1–A5 in the plan: "what's the weather" with no place named uses a fresh device fix, or IP labeled approximate, never memory; the radar shown is for that same point and is current; a place Larry names still wins.
- **Model version:** not recorded; do not infer from system name.
- **Where:** branch `ws15/radar-smooth-loop`
- **Plan:** `docs/plans/MORTIMER_WEATHER_LOCATION_AND_RADAR_PLAN.md` (Option A: `local_weather` direct tool; `jarvis/weather/report.py` with Weather.gov 7-day, hourly and alerts; IEM NEXRAD radar with RainViewer outside the US; native `RadarMapView` and `WeatherCardView`). It supersedes W5/W6 of `MORTIMER_WEATHER_FAHRENHEIT_AND_RADAR_PLAN.md`. Research: `Claude outputs/ws15/ws15_weather_research.html`.
- **Scope:** `jarvis/weather/` (new), `jarvis/weathergov.py`, `mcp_servers/mcp_web/logic.py`, `mcp_servers/mcp_web/server.py`, `jarvis/bot/weather_tool.py` (new), tool registration in `jarvis/bot/pipeline.py`, `jarvis/bot/display.py`, weather lines in `jarvis/prompts.py`, `macos/JarvisKit/Sources/JarvisKit/AppMessage.swift`, `Display/DisplayContentView.swift`, `Display/WeatherCardView.swift` and `Display/RadarMapView.swift` (new), and their tests and evals. Re-checked 09-29: none of these is inside another block's scope.
- **Next step:** Merge the radar smoothing PR and run DEPLOY-MAIN; Larry re-checks the radar loop, then acceptance A1–A7 (plan §6) and Claude checks A8 in the logs.
- **Updated:** 09-29

</details>

### Built: waiting on live checks or acceptance

<details id="ws-01">
<summary>WS-01 — Reliability, privacy and memory gaps · Codex</summary>

**Workstream:** Verified gap closure GC24-00…06: execution lifecycle, privacy log redaction, memory admission, Atlas

- **Owner:** `codex`
- **Status:** claimed: bounded action-claim settlement-order CI repair; earlier WS-01 foundation landed and deployed
- **Implemented by:** Codex
- **Remaining work / acceptance:** Codex fixes the app-build and self-edit action-claim ordering exposed by PR #115 CI; Larry retains the original physical/live acceptance.
- **Model version:** not recorded; do not infer from system name.
- **Where:** main (`539f8f6`); CI repair: `codex/ws01-action-claim-order-20260929`; shared-roadmap documentation: `codex/isolated-20260924`
- **Plan:** `docs/plans/MORTIMER_VERIFIED_GAP_CLOSURE_PLAN.md`. The 12 gap-index plans fold into it (CX-05).
- **Scope:** Existing WS-01 scope includes execution routes in `jarvis/admin/server.py`. This bounded follow-up changes only app-build/self-edit terminal claim ordering there, focused tests in `tests/unit/test_admin_appbuild.py` and `tests/unit/test_admin_selfedit.py`, this row's plan/acceptance evidence, and `ROADMAP.md` status. It does not edit WS-08 orb files or alter idempotency decisions.
- **Next step:** Merge this docs-only WS-01 claim, then make terminal claim persistence precede visible terminal job state, add deterministic race coverage, and pass targeted plus full CI. Rebase PR #115 on the merged fix.
- **Updated:** 09-29

</details>

<details id="ws-02">
<summary>WS-02 — Subscription runtime isolation · Codex</summary>

**Workstream:** Subscription runtime isolation (GC24-04)

- **Owner:** `codex`
- **Status:** landed; deployed `539f8f6`; live gates open
- **Implemented by:** Codex
- **Remaining work / acceptance:** Codex; live account checks as required
- **Model version:** not recorded; do not infer from system name.
- **Where:** main (`539f8f6`)
- **Plan:** `docs/plans/MORTIMER_SUBSCRIPTION_RUNTIME_ISOLATION_PLAN_2026-09-25.md`
- **Scope:** `jarvis/subscription.py`
- **Next step:** Staged deployment verified; run live capability/isolation gates
- **Updated:** 09-28

</details>

<details id="ws-03">
<summary>WS-03 — Skills Workspace and skill creator · Codex</summary>

**Workstream:** Skills Workspace and skill creation (T6; supersedes `MORTIMER_SKILL_AUTHORING_PLAN.md`). Its own view, separate from the Workflow Viewer (Larry, 09-27)

- **Owner:** `codex`
- **Status:** landed; deployed `539f8f6`; activation/live acceptance open
- **Implemented by:** Codex
- **Remaining work / acceptance:** Codex; Larry for human review and physical acceptance
- **Model version:** not recorded; do not infer from system name.
- **Where:** main (`539f8f6`)
- **Plan:** `docs/plans/MORTIMER_SKILLS_WORKSPACE_IMPLEMENTATION_PLAN.md`
- **Scope:** `jarvis/skill_*.py`, `jarvis/agent_skills.py`, `jarvis/selfedit/skill_policy.py`, `/api/skills*` in `jarvis/admin/server.py`. The five console view-mode Swift files are **shared with WS-07's landed Workflow Viewer**: add a new `skills` mode beside `workflows`; do not replace or restyle the viewer.
- **Next step:** Staged deployment verified; complete Skills UI/voice/provider/VM and activation gates
- **Updated:** 09-28

</details>

<details id="ws-04">
<summary>WS-04 — Remote access · Codex; Larry decides activation</summary>

**Workstream:** Remote access T2: bearer tokens, fail-closed bind, Tailscale

- **Owner:** `codex` (Larry, 09-27)
- **Status:** landed; deployed `539f8f6`; auth remains dormant
- **Implemented by:** Codex (remote foundation and R1)
- **Remaining work / acceptance:** Codex; Larry decides activation/token onboarding
- **Model version:** not recorded; do not infer from system name.
- **Where:** main (`539f8f6`)
- **Plan:** `docs/plans/MORTIMER_REMOTE_ACCESS_PLAN.md` (DRAFT) + **Addendum R1** (dormant-merge fixes, approved 09-27)
- **Scope:** `jarvis/auth.py`, `jarvis/authmw.py`, `jarvis/bind.py`, `jarvis/urls.py`, `jarvis/bot/server.py`, auth middleware and bind in `jarvis/admin/server.py`. Plus the integration points in CX-11: `jarvis/bot/status_tool.py`, `scripts/deploy_main.sh` health checks, `mcp_servers/mcp_selfedit/logic.py` headers
- **Next step:** Dormant deployment verified; enabled-mode gate and token onboarding remain separate
- **Updated:** 09-28

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
- **Updated:** 09-29

</details>

<details id="ws-07">
<summary>WS-07 — Voice workflows and Workflow Viewer · Claude</summary>

**Workstream:** Voice workflows phases 1–4, Workflow Viewer, #80 privacy fix, DEPLOY-MAIN

- **Owner:** `claude`
- **Status:** landed (main `0b76f49`)
- **Implemented by:** Claude
- **Remaining work / acceptance:** Larry: switch the reply guard from `log` to `correct` once the live log shows its precision. The live logs since the landing hold four `reply_guard` lines, which is not enough yet.
- **Model version:** not recorded; do not infer from system name.
- **Where:** main
- **Plan:** `docs/plans/MORTIMER_VOICE_WORKFLOWS_PLAN.md`, `docs/plans/MORTIMER_WORKFLOW_VIEWER_PLAN.md`
- **Scope:** —
- **Next step:** Plan headers corrected in PR #100 (09-28). Verified read-only: the end-run memory archive is done and the console is on. Next is the guard-mode decision after more live use.
- **Updated:** 09-28

</details>

<details id="ws-08">
<summary>WS-08 — Crystal orb, single shell · Codex implementation; Larry acceptance</summary>

**Workstream:** Orb crystal glass (#90), revised to use the crystal shell exclusively

- **Owner:** `codex`
- **Status:** landed (PR #112, merge commit `e9388fc`); deployment and live acceptance open
- **Implemented by:** Claude original crystal-glass workstream; Codex rendering performance fixes and single-shell cleanup
- **Remaining work / acceptance:** Deploy the merged crystal-only build, compare its five visual fixtures with the approved reference, then Larry verifies the orb in compact/expanded layouts and under Reduce Motion. His 09-29 observations pass the pre-cleanup build. The local full MortimerHost run had one environment-sensitive protected-window capture failure; PR #112's CI passed on rerun.
- **Model version:** not recorded; do not infer from system name.
- **Where:** main (PR #112, `e9388fc`)
- **Plan:** `docs/plans/MORTIMER_ORB_CRYSTAL_GLASS_PLAN.md`
- **Scope:** Orb rendering, orb-specific configuration, performance/visual regression tests, and this plan's acceptance evidence.
- **Next step:** Deploy `e9388fc` through the standard release flow, then Larry reviews the visual fixtures and rechecks compact/expanded layouts and Reduce Motion.
- **Updated:** 09-29

</details>

<details id="ws-09">
<summary>WS-09 — Command Console and Atlas acceptance · Larry acceptance</summary>

**Workstream:** Command Console and Atlas release acceptance

- **Owner:** `larry`
- **Status:** landed (PR #99, merge commit `4986c10`); deployed in `eb24e81` on 09-29; Mac acceptance remains open
- **Implemented by:** Codex (Codex desktop; exact model build is not exposed)
- **Remaining work / acceptance:** Larry (Mac/live acceptance)
- **Model version:** not recorded in a handoff receipt.
- **Where:** [PR #99](https://github.com/Larryfix71566/jarvis-voice-ai/pull/99), merged to `main` as `4986c10`
- **Plan:** `docs/plans/MORTIMER_COMMAND_CONSOLE_ATLAS_PLAN.md`
- **Scope:** —
- **Next step:** Larry completes the physical single- and multi-monitor acceptance on the deployed build (`eb24e81`)
- **Updated:** 09-29

- [ ] **Single transcript surface (Larry, 2026-09-28):** keep the transcript in the main window; remove the duplicate transcript/captions from the left/compact panel and reclaim the vacated space. Preserve the orb, speaker feedback, microphone/voice controls, and main-window transcript history/accessibility. This supersedes earlier requirements to repeat brief captions in the compact rail; full response/results routing remains unchanged.
  - **Status:** Landed in `main` via PR #99 (`4986c10`); implementation and automated validation complete; deployment and user/Mac acceptance remain open.
  - **Implementation owner:** Codex, explicitly dispatched by Larry on 2026-09-29; follows the Codex/Luna handoff specification. **Acceptance:** Larry. **Plan author:** Codex.
  - **Scope:** `macos/MortimerHost/Sources/MortimerHost/Console/OrbFieldView.swift`, `macos/MortimerHost/Tests/MortimerHostTests/CompactConversationTests.swift`, this roadmap and the linked plan progress only.
  - **Implementation handoff:** [WS-09 transcript cleanup — Luna implementation handoff](docs/plans/MORTIMER_COMMAND_CONSOLE_ATLAS_PLAN.md#ws-09-transcript-cleanup--luna-implementation-handoff).
  - **Validation:** focused compact transcript tests 3/3, live response stream 2/2, result router 7/7; full MortimerHost 374 passed, 7 environment-dependent skips, 0 failures. `git diff --check` passed. Render captures inspected at compact widths 512 and 1000; paths and details are in the linked plan.
  - **Log (2026-09-29):** PR #99 merged as `4986c10`; Codex’s layout-v2-only caption removal and rendered-regression tests are in `main`. Full response/history surfaces and legacy layout are preserved. No deployment or Mac acceptance has been performed. Source retains the “Microphone muted” indicator, but automated coverage does not explicitly assert that exact compact status yet.
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
- **Where:** —
- **Plan:** `docs/plans/MORTIMER_MEMORY_AUTOCONSOLIDATION_PLAN.md`
- **Scope:** —
- **Next step:** CX-07 integrated locally; validate and choose staged Mac enablement before rollout
- **Updated:** 09-27

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
- **Next step:** `docs/acceptance/adaptive-interface/RELEASE_READINESS.md`
- **Updated:** 09-22

</details>

<details id="ws-14">
<summary>WS-14 — Subscription probe: sign-in, command and category fixes · Claude (Codex post-merge review)</summary>

**Workstream:** Make the WS-06 check #2 subscription probe work under launchd and report why it fails. It touches WS-02's file (CX-13). Larry decided 09-29: Claude lands, Codex reviews before merge.

- **Owner:** `claude`
- **Status:** landed (PR #102, merge `eb24e81`); deployed 09-29 10:07 EDT by DEPLOY-MAIN (Python 4879 passed, JarvisKit 219/0, MortimerHost 374/0)
- **Implemented by:** Claude
- **Remaining work / acceptance:** Live check passed: the `com.mortimer.status-daily` rerun at 14:11 UTC 09-29 shows `claude` `ok: true`. `codex` shows `not_installed`, which is correct because no Codex CLI is on the launchd PATH. Claude's earlier prediction of `gated` was wrong: `gated` appears only once a Codex CLI resolves. Codex completed a post-merge code review of PR #102 on 09-29; no blocking code issue found. The review did not independently reproduce the Mac Keychain/launchd test (CX-13).
- **Model version:** not recorded; do not infer from system name.
- **Where:** main
- **Plan:** Under `MORTIMER_SUBSCRIPTION_RUNTIME_ISOLATION_PLAN_2026-09-25.md`, which allows "home needed for provider-managed sign-in, plus only specifically justified" variables. The live evidence is in WS-06. Changes:
  1. `USER` and `LOGNAME` join the child-environment allowlist. They are not credentials, and there is a `pwd` fallback when launchd omits them.
  2. `_claude_argv` and `_codex_argv` run `provider_command()`, which reads the same `JARVIS_*_SUBSCRIPTION_COMMAND` variable as the installed check.
  3. `probe_subscription` keeps the runtime's own category when the legacy message table falls through to `runtime_error`. A `SubscriptionCapabilityError` reports `gated`. The legacy table and the `verify_model_access` golden output are unchanged.
- **Scope:** `jarvis/subscription.py`, `jarvis/status/subscriptions.py`, `tests/unit/test_subscription.py`, `tests/unit/test_status_subscriptions.py`
- **Next step:** None for Codex review; Larry's live subscription acceptance remains as recorded in WS-06.
- **Updated:** 09-29

</details>

### Completed: accepted, nothing left

Accepted workstreams are listed below; implementation milestones also appear in §6.

<details id="ws-16">
<summary>WS-16 — Protected-window capture gate repair · Codex</summary>

**Workstream:** Make the privacy-preserving live-window capture assertion deterministic enough to unblock DEPLOY-MAIN without weakening what it proves.

- **Owner:** `codex`
- **Status:** accepted: PR #121 merged as `c3607e6` and DEPLOY-MAIN passed 09-29
- **Implemented by:** Codex diagnosis and test-fixture repair
- **Remaining work / acceptance:** None for this capture gate. Larry's DEPLOY-MAIN for `c3607e6` passed phase A: the real ScreenCaptureKit protected-window test executed and passed (4.825 s), MortimerHost ran 383 tests with six unrelated skips and zero failures, JarvisKit ran 218 tests with zero failures, and Python had 4,924 passes and seven skips. Phase D reported healthy services and matching code, production and app-bundle revisions. WS-08's separate visual and Reduce Motion acceptance remains open.
- **Model version:** not recorded; do not infer from system name.
- **Where:** main (PR #117, `c5781a8`; PR #121, `c3607e6`); acceptance status on `codex/ws16-protected-capture-20260929`
- **Plan:** `docs/plans/MORTIMER_PROTECTED_WINDOW_CAPTURE_GATE_PLAN.md`
- **Scope:** `macos/MortimerHost/Tests/MortimerHostTests/ProtectedDisplayContentTests.swift`, this row's plan and acceptance evidence, and `ROADMAP.md` status only. Product display code remains outside this row; WS-15 owns `Display/DisplayContentView.swift` while active.
- **Next step:** None for WS-16; continue the independently owned WS-08 visual acceptance on the deployed build.
- **Updated:** 09-29

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

---

## 4. Conflict register

Open means not yet resolved. Each entry names who resolves it.

| ID | Conflict | Resolves | State |
|---|---|---|---|
| CX-11 | Codex's T2 code against what Claude landed on main. (1) `JARVIS_AUTH_ENABLED` **defaults to true**, with no exempt routes, loopback included, so merging it turns auth on. (2) Main callers that send no token would then get 401: `jarvis/bot/status_tool.py` (the `system_status` tool from #86) and `scripts/deploy_main.sh` phase D, whose health checks expect 200 from `/api/health` and 200/307 from the bot, so the deploy would stop. (3) The route inventory in Codex's tree has 64 sidecar routes; main has 68 decorators, including 10 Codex's copy lacks: `/api/status/*` (9) and `/api/workflows`. (4) `mcp_servers/mcp_selfedit/logic.py`: Codex added service headers; main's copy also changed, so keep both. (5) Token setup is by CLI only (`python -m jarvis.auth add`), which conflicts with the no-shell-commands principle behind Claude's voice workflows (D-L2/D-L5). The native app already sends a Keychain token on every request (`JarvisHTTP.swift`), so it needs no code change, only a stored token. | `codex`: Addendum R1 fixes (1)–(4); `larry` decides (5) when T2 is decided (options in R1.9) | R1 implemented and deployed dormant; isolated enabled/dormant proof passes; token onboarding/remote activation remain undecided |
| CX-13 | WS-14 edits `jarvis/subscription.py`, which is WS-02's scope (Codex; landed, so unlocked, but its live isolation gates are open). The allowlist change adds `USER`/`LOGNAME`, justified by the live `Not logged in` result recorded in WS-06. | `larry` (09-29): Claude lands, and Codex reviews before merge | resolved 09-29: Codex post-merge review of PR #102 found no blocking code issue; Mac Keychain/launchd evidence remains reported live evidence, not independently reproduced |
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

- **T2 remote access: switching it on** (undecided). Codex builds it dormant under WS-04; turning it on, and how you get tokens without shell commands (CX-11 item 5), is a later decision.
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
- **Still open:** physical step 9 acceptance in WS-08.

</details>

<details>
<summary>Completed — workflows, recovery, Skills and model foundations · Claude + Codex</summary>

- [x] **Claude / WS-07:** voice workflows phases 1–4, Workflow Viewer, #80 privacy fix and DEPLOY-MAIN (09-25).
- [x] **Claude / WS-06:** self-service access/recovery and registry-split code (#86; 09-25 landing).
- [x] **Codex / WS-03:** separate Skills Workspace, developer-run creator and validation activity contracts.
- [x] **Claude original workstream / WS-08:** crystal-glass orb (#90; 09-24); later performance fixes by Codex above.
- [x] **WS-05 foundation:** provider-neutral execution, policy-aware logs, isolated subscription adapters and draft-confirmed preferences. The roadmap does not itemize every original contributor; Codex owns WS-02 isolation and is proposed for remaining WS-05 work.
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
