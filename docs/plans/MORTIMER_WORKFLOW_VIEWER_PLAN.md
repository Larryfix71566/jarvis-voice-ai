# Mortimer Workflow Viewer: Handoff Plan

**Status:** DECIDED and BUILT in the VM, 2026-09-25 (Larry chose the recommended option for D-V1, D-V2 and D-V3; §3). Branch `viewer`; patch `closure-checks/viewer-on-phase4.patch`. The Python half is tested in the VM. The Swift half compiled and passed on the Mac in check run 2 (2026-09-25 18:06; §8).
**Author:** Claude (Cowork), 2026-09-25 · **Approver:** Larry
**Parent:** `MORTIMER_VOICE_WORKFLOWS_PLAN.md` §12 (layout C chosen 2026-09-25). This is the handoff plan §12 asked for.
**Builds on:** branch `phase4` (Phases 1–4 + #86). It is a new branch `viewer` on top, and a sixth patch, `viewer-on-phase4.patch`, tested at the same end-of-project run.

---

## §1 What exists (verified 2026-09-25 on `phase4`)

- **23 workflows load** (`jarvis.workflows.load_workflows`, `config/workflows/*.yaml`):
  - 7 voice workflows (`agents: [supervisor]`, priorities 8–30);
  - 11 standing rules (every specialist, or `developer` for `verify-ui-change-on-screen`);
  - 5 drafts with a `REVIEW ME` header and an empty `done_when` (§3 D-V1).

  Steps per workflow: 1–5. The longest step is 325 characters (`voice-model-availability`), so cards must wrap text, never truncate it in the detail view.
- **No UI shows a workflow.** `/api/knowledge` (`jarvis/status/overview.py`) returns only `name`, `source` and `has_done_when`. JarvisKit's `KnowledgeWorkflow` (`AdminAPI.swift:579`) has the same three fields.
- **View modes are three booleans** in `WorkspaceStore` (`showsConversation`, `showsMemoryGraph` and `showsAtlas`; "results" is when all three are false). Each `open*` sets its own flag and clears the others. `consoleInventory` and `consoleInventoryJSON` derive `mode` in this order: conversation, memory, atlas, results.
- **`ConsoleActionCoordinator.execute` `.viewSet`** (`ConsoleActionCoordinator.swift:89`) switches on `conversation | memory | results | atlas`; anything else is `.invalid`.
- **The view buttons are in three places:**
  - `WorkspaceView.navigationControls` (plus its Display menu, "Show memory graph" → `sendToDisplay(.memoryGraph)`);
  - the `CommandConsoleView` header;
  - `AdaptiveStageView.conversationControls`.
- **`SupportingDisplayContent`** (`WorkspaceStore.swift:22`) is `result(UUID) | memoryGraph`. It is switched on exhaustively in `DisplayWindowStore.supplementalContent` and `isPresented`, and in `DisplayWindowView`'s `LegacySupportingDisplayStage` (the content and the title). The layout-1 branch of `DisplayWindowView` tests it with `==`. (Correction, found while building: `DetachedPanelView`'s `case .memoryGraph` is a different enum, the content-panel kind, and `AppMessageRouter` only calls `sendToDisplay(.memoryGraph)`; neither needs a change.)
- **`ResponseResultRouter`** keeps a new reply from taking over the workspace while the memory graph or the atlas is open. The viewer needs the same guard.
- **Voice entry is off in production today** [certain for `.env`]. `console_action` is registered only when `JARVIS_COMMAND_CONSOLE_ENABLED` is true (default false), and production's `.env` doesn't set it. The buttons and the Display menu work regardless.
- **Voice cannot find a view mode by name today.** `console_action`'s schema (`jarvis/bot/console_actions.py`) says only "A registered console action". The Python protocol checks the argument keys (`view_set` needs `mode`), not the values. No prompt, help text or inventory lists the valid modes; the only place they are written down is `MORTIMER_COMMAND_CONSOLE_ATLAS_PLAN.md:409`.
- **Usage data.** Specialists log `workflow_injected agent=… name=… source=…` (`jarvis/agents/base.py:669`, one workflow per run: `match_workflow` returns the single best match). Voice workflows log `voice_workflow_injected` for the user hook (`jarvis/bot/voice_guidance.py:129`) and the result hook (`jarvis/voice_workflows.py:284`); the reply hook logs `reply_guard action=…` with no workflow name. The retained production logs (`bot.launchd.log*`) hold 20 `workflow_injected` lines: 13 on 08-22, then 09-08, 09-17, 09-18 and 09-22. Five names appear. One of them, `project-registry-goal` (injected twice on 09-22), no longer exists (§3 D-V3). Production has no voice-workflow lines, because it doesn't run Phase 1.
- **Swift cannot be built in the Linux VM.** Org egress blocks `download.swift.org`. The Swift half is written in the VM and compiled and tested only on the Mac, by the check script, as Phase 2's was.

## §2 Scope

Build a read-only viewer: a gallery of workflow cards, and one workflow's flow on click. It opens in the workspace and in the supporting display window, from a button, the Display menu, or voice.

Not in scope:
- editing (workflows are reviewed config; a change goes through self-edit or a PR);
- a "which workflow matches this sentence" tester;
- new matching behaviour.

## §3 Decisions (Larry, 2026-09-25: the recommended option in all three)

**D-V1: the five REVIEW ME drafts.** `load_workflows()` has no draft filter, so they are live policy:
- `research-before-modifying` (313ba43, 08-18);
- `user-task-website-comparison` (a session note, 12fd986, 08-27);
- three from d74e40d (09-01): `user-interface-analyst-visibility`, `user-style-ui-requirement` (a near-duplicate of it) and `user-style-display-output`.

Each is one memory fact copied into `when` and `steps`, with no finish test. None has fired in the logs retained since 08-22.
- **A (recommended; CHOSEN): a `draft: true` field** that the loader skips for matching and the viewer shows in a "Drafts" group with dashed borders. The five files get the flag. Nothing is deleted, and matching behaviour is unchanged as far as the logs show.
- **B: delete the five files** and restore the memory facts they came from (`memory_restore`, Phase 4 W10). Each fact then shows its age in the prompt.
- **C: rewrite each** into a real workflow with a finish test. That needs his words for each, so it is slower.

**D-V2: usage counts in v1.**
- **A (recommended; CHOSEN): no counts in v1.** Only 20 injection lines survive log rotation, and the voice reply hook logs no workflow name, so any count would be partial and look authoritative.
- **B: counts from the logs**, labelled "since <oldest retained log>".
- **C: a durable `workflow_uses` table** (migration 0028), written where each injection is logged. It is exact from the deploy on, and the viewer shows it. This adds a write to the hot path of every delegation.

**D-V3 (found for this plan): six memories archived as workflows whose files do not exist.** A production copy has 35 facts archived as `workflow:<slug>` (K6.2 conversions). For 6 of them, no file exists in production's `config/workflows/` or in the repo:

| Fact | Archived | What happened to the file | Content (start) |
|---|---|---|---|
| `user.preference.model_defaults` | 08-31 | Committed in d74e40d, deleted on purpose in 7fc0991 ("retire the two workflow drafts the config now supersedes": the model floor is in `config/agents.yaml`, pinned by `test_model_floor.py`) | All specialist agents … must use Sonnet or better. Haiku is reserved for Mortimer's own co… |
| `user.preference.model_selection` | 08-31 | Same as above | Sonnet+ for all specialist agents and research; Haiku only for Mortimer's latency-critical responses |
| `user.style.ui_geometry` | 09-02 | Never committed | Connection line from screen center to analyst box should snap to nearest corner, not center point. |
| `project.weather.map_provider_backup_plan` | 09-02 | Never committed | Self-hosting if production rate-limiting occurs; explore on-demand basis |
| `project.registry.goal` | 09-18 | Never committed; injected twice on 09-22, gone now | Keep registry updated with newest models available |
| `project.registry.task.openrouter_sync` | 09-18 | Never committed | Set up daily updates from OpenRouter to catch new significant model improvements |

`extract_workflow` writes into the running checkout. The four files never committed existed only there and are gone; the most likely cause is the checkout being cleaned for a deploy [likely: untracked files leave no history]. Those four facts are now in neither memory nor workflows. A seventh, `user.style.direct_action` → `give-exact-commands`, is retired on purpose by Phase 1 (D13).
- **A (recommended; CHOSEN): restore the four lost ones** (`ui_geometry`, `map_provider_backup_plan`, `registry.goal`, `registry.task.openrouter_sync`) at the end run with `memory_restore`; they come back with their original ages. Leave the two model-floor facts archived: config enforces that policy, and 7fc0991 retired them on purpose.
- **B: restore all six.** The two model-floor facts would then restate, in the prompt, what config already enforces.
- **C: leave them.**

## §4 Design (layout C, as chosen)

- **Entry.**
  - A new view mode, `workflows`: `WorkspaceStore.showsWorkflows` plus `openWorkflows()`, the same pattern as `openAtlas()`. It is derived after `atlas` in both inventory builders.
  - A "Workflows" button beside "Knowledge Atlas" in all three button rows.
  - The Display menu gets "Show workflows", backed by a new case, `SupportingDisplayContent.workflows`.
  - Voice uses `console_action` `view_set` `mode=workflows`.
- **Gallery.**
  - A filter field searches name, `when` and step text.
  - Three groups: "Voice · supervisor" (sorted by priority), "Standing rules" (by name), and "Drafts · review me" (with dashed borders).
  - Each card shows the name; the first step, clamped to 2 lines; the step count; and either the done-when count or "no finish test". It also shows agents and priority, and a pip strip (trigger · one pip per step · done).
- **Detail (`WorkflowFlowView`).**
  - It replaces the gallery, with "← All workflows", "Next: <name> →" and "workflow n of N".
  - A horizontal scroll of fixed-width nodes (~232 pt) that wrap text in full:
    - the trigger node: for a keyword workflow, the `when` text and "≥ 35% word overlap · strongest wins · one per run" (`MATCH_THRESHOLD` from the endpoint); for a voice workflow, its hooks (user / result / reply) and priority;
    - one numbered node per step;
    - the done-when node: green, or a dashed amber "no finish test".
  - Badges: agents, priority, draft, and source file.

## §5 Pieces, files and tests

1. **Python: `GET /api/workflows`** (`jarvis/admin/server.py`, body in `jarvis/status/overview.py` beside `knowledge_overview`).
   - Returns `{"ok", "enabled", "match_threshold", "workflows": [...]}`. Each workflow has `name`, `when`, `steps`, `done_when`, `agents`, `source`, `triggers` (hook names only, never the regexes), `priority`, `kind` (`voice` or `rule`) and `draft`.
   - Read-only; never raises.
   - When workflows are off (`JARVIS_WORKFLOWS_ENABLED=false`) it returns `enabled: false` and an empty list, and the viewer says so.
   - Tests: fields and grouping over the real `config/workflows`, the disabled switch, and a bad file skipped.
2. **Python (D-V1 A).** `parse_workflow` reads `draft`, and `match_workflow` and `voice_workflows` skip drafts. The five files get `draft: true`. Tests: a draft never matches; the viewer still lists it.
3. **Python: voice can name the mode.** `CONSOLE_ACTION_SCHEMA`'s description lists the `view_set` modes (`conversation`, `results`, `atlas`, `memory`, `workflows`). The tool menu is otherwise unchanged. Tests pin the list against the Swift coordinator's cases (a shared constant file `config/console_view_modes.json`, read by both the Python test and a Swift test).
4. **JarvisKit.**
   - `WorkflowDetail`, a Codable with lenient decoding like `KnowledgeWorkflow`.
   - `WorkflowsResponse`.
   - `AdminAPI.workflows()`.
   - Test: decode a captured `/api/workflows` fixture from item 1.
5. **MortimerHost (as built).**
   - `Stores/WorkflowsStore.swift`: the `WorkflowGroup` enum and the store (load once unless forced, filter, groups, select, next with wrap-around, "n of N").
   - `Display/WorkflowsView.swift`: `WorkflowsView` (gallery or flow), `WorkflowsGalleryView`, `WorkflowCard`, `WorkflowPips` and `WorkflowFlowView`.
   - `WorkspaceStore`: `showsWorkflows`, cleared wherever `showsAtlas` is cleared; `openWorkflows()`; the mode in both inventory builders; `let workflows = WorkflowsStore()`; and `SupportingDisplayContent.workflows`.
   - The `ConsoleActionCoordinator` `.viewSet` case.
   - "Workflows" buttons in `WorkspaceView`, `CommandConsoleView` and `AdaptiveStageView`.
   - "Show workflows" in the Display menu.
   - `DisplayWindowStore` and `DisplayWindowView` cases, and the `ResponseResultRouter` guard.
   - Tests in `WorkflowsViewerTests.swift`:
     - store: groups and order, filter, select, next and back, reload, load once or forced, failure, workflows off, card summaries;
     - the four modes stay mutually exclusive, with the inventory reading `workflows`;
     - every mode in `config/console_view_modes.json` is applied, and an unknown one is invalid;
     - the supporting-display tile;
     - a render of the gallery, a flow with a 324-character step, and a draft.
6. **Plan and records.** `MORTIMER_VOICE_WORKFLOWS_PLAN.md` §12 points here, and the end-run checklist gains the viewer's live checks.

## §6 Verification

- **VM:** the full Python suites (unit, integration, CI's other gates) and the JarvisKit decode fixture generated from item 1's real output.
- **Mac, via the check script (six patches):** JarvisKit and MortimerHost `swift test`, 0 failures, and the full Python suite.
- **Live at the end run:**
  - "show me the workflows" opens the gallery by voice;
  - "Workflows" opens it from each of the three button rows;
  - "Show workflows" puts it on the supporting display;
  - clicking `voice-model-availability` shows 3 steps, with the 325-character one wrapped;
  - the drafts group shows 5 dashed cards (D-V1 A).

## §7 Rollback and risks

- **Rollback.** Additive: remove the buttons and the menu item, or revert the patch. The `draft` flag (D-V1 A) only removes five never-fired files from matching; reverting restores them.
- **Risk: a fourth mode flag drifting out of mutual exclusion.** Mitigated by a test that walks every `open*` and asserts exactly one mode.
- **Risk: Swift compiles only on the Mac.** The first Mac run may fail to compile. This is the same exposure as Phase 2, which compiled first time.
- **Risk: the supervisor picks the wrong mode by voice.** Item 3 names the modes. No voice eval case was added: the eval offers no `console_action` (it passes no `command_console` flag), matching production, where the tool is off.

## §8 Build record (2026-09-25)

- **Python:** unit 3,862 passed. That count includes `test_workflows_viewer.py` (9), and every existing test passed. Integration and CI's other gates were run too (see the voice-workflows plan, rev 1.14).
- **Review of the uncompiled Swift (a second agent, 2026-09-25):** it found nothing that should fail to compile and no failing test, plus four defects, now fixed with tests:
  1. a failed read marked the store loaded, which blocked retries for the whole session; there is now also a Reload button;
  2. workflows were keyed by name, which `load_workflows()` doesn't keep unique; they are now keyed by file;
  3. closing the last result while the viewer was open left two views flagged at once, and a comparison stayed hidden behind the viewer;
  4. a stale comment in `config/console_view_modes.json`.

  It also noted that the added buttons may truncate in the narrowest layouts.
- **Swift:** not compiled. Every API used was checked against an existing use in this tree: `@Bindable` on an `@Observable` store, `.task` calling a `@MainActor` store, `ForEach(Array(x.enumerated()), id: \.offset) { index, item in }`, `GraphFixture.repositoryRoot()`, `ConsoleRequest`'s initializer, `DisplayWindowStore.setWindowOpen`, and `TabStateMapper.fromError`.
- **Mac check, run 1 (2026-09-25 18:02; `CHECK-phases-1-4.sh`, all six patches, trees matched):**
  - JarvisKit: 206 tests, 0 failures, including the two new decode tests.
  - Python: 4,018 passed, 4 skipped.
  - MortimerHost: the app sources compiled, but the test target did not. There was one error: `WorkflowsViewerTests.swift:35`, a default argument (`= sample()`) that calls a static method of the `@MainActor` test class. The review had judged this "at worst a warning"; the Mac compiler made it an error.
  - Fixed: the sample data moved to a nonisolated `enum WorkflowFixtures` outside the class.
- **Mac check, run 2 (2026-09-25 18:06; same script, all six patches, trees matched): ALL PASSED.**
  - JarvisKit: 206 tests, 0 failures.
  - MortimerHost: 275 tests, 3 skipped, 0 failures; all 14 `WorkflowsViewerTests` passed.
  - Python: 4,018 passed, 4 skipped.
- **D-V3 restore:** tested on a production copy. Restoring the four puts the project tier at 10 of its cap of 8. With no merge, capacity enforcement then ages out `project.model_registry.blocker` and `user.memory.fleetback_atlanta` (reproduced). Both stay restorable.
