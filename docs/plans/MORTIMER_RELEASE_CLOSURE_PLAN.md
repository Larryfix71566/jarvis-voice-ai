# Mortimer release closure plan: acceptance on main, new interface on `next`

- **Status:** adopted 2026-11-11 (#327). The freeze is WS-33 and the WS-17 combined-source review claim. The three lanes are rows WS-34 (Claude), WS-35 (Codex) and WS-36 (Kimi), approved by Larry on 2026-11-11 (decision 6) and on `main` since #329.
- **Source of truth:** this file. The Claude Doc "Mortimer combined implementation plan" in Larry's account mirrors it; when they differ, this file wins (ROADMAP.md §0 rule 11 still ranks ROADMAP.md above it).
- **Built at:** `origin/main` `4e58eaa`; checked again at `b9024ed` (2026-11-11, after #322 and #324). Line numbers below are from those commits.
- **Written by:** Claude (Opus), from Claude's 2026-11-10 deep review, the 2026-11-10 interface review and mockups, ROADMAP.md and AGENTS.md.
- **Interface design:** `docs/interface-research/orb-plasma/ORB_SPEC.md` is the approved direction (4 + 5 + 6), the palette and the orb spec that items C0b to C9 build. For the orb's own depth Larry picked refraction plus option 1's shadow (03:19:59); it is measured first (box 810), and the app's first Metal shader.

## Larry's direction

All times UTC, in his Claude Duet channel:

- 2026-11-11 02:35:41: "Take your picks", answering decisions 2 to 7 (§7). The orb design and its palette were approved before that in the same channel; this file records the palette as the coordinator relayed it.
- 2026-11-11 01:35:04: "so let's combined your findings from both the review and the interface enhancements into a single implementation plan that all three models can run. Revise the acceptance list to be in-line with the new interface design so that we dont waste time validating that has been changed. since this app is not currently in prod we can work quickly without worry about the app being used. that should reduce the projected timelines. I want to work thru this as quickly as possible."
- 2026-11-11 01:35:44, answering whether non-UI acceptance should run now: "Yes, run it now".
- 2026-11-11 01:58:16, answering whether main should freeze with the new interface on a `next` branch: "first let's seperate this plan so that kimi and codex can help with development, the division should not be absolute but a guide to keep the models from stepping on each other, then we should freeze main and begin".
- 2026-11-11 01:59:13: "additionally this plan needs to be sync to the repo so that each model has access".

## 1. How to use this plan

The lanes in §4 say who leads each piece of work. **They are a guide that keeps the three models from stepping on each other, not an exclusive claim** (Larry 01:58:16, and ROADMAP.md §0 rule 14). Any system that is not engaged may pick up an item no one is engaged on. Before starting an item:

1. Read ROADMAP.md on `origin/main` (§0, §2, §4) and this file on `next`.
2. Check that no open PR already touches the item's files: `gh pr list --base next` and `gh pr list --base main`.
3. If the item is in another lane, update that lane's row (Owner/Where for the item) in your PR, so the others can see who has it.
4. Stay inside the files listed for your item. If you must edit a file listed under another lane, say so in the PR body and add a line to ROADMAP.md §4.

No system reviews its own work (rule 14). Larry merges every PR.

## 2. Branches

- **`main` is frozen** under ROADMAP.md §0 rule 15 from the freeze SHA recorded in WS-17. Only docs-only PRs and acceptance fixes Larry approves by name merge there.
- **`next`** is cut from the freeze SHA. All other work in this plan targets `next`: base your branch on `origin/next` and open PRs with `--base next`.
- **Acceptance fixes** branch from `main`, merge to `main` on Larry's named approval, and are merged forward into `next` the same day by the fix's author (a merge of `main` into `next`, no rebase).
- **Closure:** when the run-now acceptance batch and the combined-source review have closed, Larry approves merging `next` into `main` by name; that merge ends the freeze. `scripts/deploy_main.sh` then deploys the final build unchanged (it deploys only `origin/main`, line 383, and refuses production work missing from main, lines 407 to 420), and the rewritten UI boxes run on it.
- **CI:** the three workflows trigger only on `main` today (`validate.yml` lines 2 to 6, `sandbox.yml`, `knowledge-base.yml`). The first PR into `next` (WS-34 item A1) adds `next` to those triggers; pull-request workflows run from the merge ref, so that PR checks itself.

## 3. Acceptance, split by what the new design changes

117 boxes in ROADMAP.md §2 at `4e58eaa`. The full revised list, with the rewritten boxes in full, is [`docs/acceptance/mac-acceptance-2026-11-11.md`](../acceptance/mac-acceptance-2026-11-11.md).

| Group | Boxes | When |
|---|---|---|
| Non-UI, run now | 9 | On the freeze build |
| UI kept (the view inside doesn't change) | 18 open + 1 passed | Open ones now, on the freeze build |
| UI rewritten for the new design | 19 | Once, on the final build |
| UI dropped (828, becomes a design rule) | 1 | Never |
| Non-UI, final build only | 11 | Release closure |
| Non-UI, blocked on unbuilt work or a decision | 54 | When the workstream unblocks |
| Non-UI, already checked | 4 | Done |

The rewritten boxes reach ROADMAP.md through WS-34 item C8, reviewed by Codex.

## 4. Lanes

Item ids are stable; sizes are estimates from line counts at `4e58eaa`, not measurements. Every item is a PR into `next` unless marked. **Every item includes its tests:** `macos/MortimerHost/Tests/**`, `macos/JarvisKit/Tests/**` or `tests/**` for the files it touches. The interface items (C*) were reviewed by a Fable 5.2 pass on 2026-11-11 (see the progress log); findings marked "direction 6" will be checked again when the orb and palette design is final.

### WS-34: Claude lane (Python, contracts, roadmap)

| Id | Work | Reviewer | Depends on | Files |
|---|---|---|---|---|
| A1 | Add `next` to the CI triggers | Codex | `next` exists | `.github/workflows/validate.yml`, `sandbox.yml`, `knowledge-base.yml` (trigger lines only; lands before B1) |
| A2 | Cut `next` from the freeze SHA | none | freeze SHA recorded | branch only |
| C0 | Contracts: block-kit `layout` schema for one composed answer, a typed-request client message, an approve/decline action (and whether it is a console action or a client message); design rule from box 828 | Codex and Kimi | A2 | `docs/contracts/**` (new), Python message types and their tests; if approve/decline is a console action, `jarvis/bot/console_protocol.py` and `tests/fixtures/command_console/protocol.json` |
| C0b | Colour and type tokens for the approved palette (decision 2): `listening` `#6673FF`, `user` teal `#2DD4BF`, `mortimer` rust `#E07020`, `ok` `#A6FFC1`, `approval` (the needs-you ring) `#FFD84A`, `error` `#FF598B`. All are new tokens; `amber`, `green` and `red` keep their values and meanings | Codex and Kimi | decision 2 (answered), final direction 6 | `docs/contracts/**` |
| C3 | Python composer: one composed answer per request, gathering every display emitter | Kimi | C0 | `jarvis/bot/display.py`, `jarvis/bot/compose*.py` (new), the display emit sites in `jarvis/bot/pipeline.py` (lines 1023 to 1077, 1120, 1323, 1374, 1560, 2545 at `b9024ed`), `handoff_tools.py`, `weather_tool.py`, `plan_watcher.py`, `research_watcher.py` |
| C7-py | Typed request and approve/decline handlers in the bot | Kimi | C0 | a new `jarvis/bot/typed_request.py`; registration lines in `jarvis/bot/pipeline.py` |
| C7b | Composer and ⌘K, and the typed-request send path in the app (moved from Kimi to balance days 7 to 11) | Kimi | C0, C1a, B1 green | `MortimerHostApp.swift` (`keyboardShortcut` and `CommandMenu` near line 276) or the key monitor in `ConsoleView.swift` (near line 225), `Console/AttachmentTrayView.swift`, `macos/JarvisKit/Sources/JarvisKit/ClientMessage.swift`, `JarvisClient.swift`, `ClientMessageTests` |
| C1b | Delete `web/`, `macos/MortimerShell`, `macos/GlassSpike`, `macos/VPIOBench` and what depends on them | Codex | B1, decision 3 | those paths; `.github/workflows/validate.yml` web steps (setup-node through the frontend build, lines 104 to 111 at `b9024ed`); `tests/unit/test_agents_yaml_frontend_parity.py`, `tests/unit/test_web_freeze_preflight.py`; `scripts/run_web.sh`, `scripts/mortimer.sh`, `scripts/build_shell.sh`, `scripts/deploy_main.sh` (lines 244, 418), `Procfile`; `CLAUDE.md`, `docs/REPO_MAP.md`, `macos/README.md`. Human-only, as a patch for Larry: `sandbox/profiles.py` (the `web` check), `sandbox/guest/hydrate.py`, `jarvis/selfedit/service.py`, `config/self_edit_allowlist.json` |
| B2 | Host and Origin allow-list plus a required header on mutating routes (admin, bot, costs) | Codex | A2 | `jarvis/admin/**`, `jarvis/costs_api.py`, the bot runner's middleware; the app's header line goes with C7b |
| B3 | Security modules and `config/model_access.yaml` into the self-edit deny tier | Kimi | A2 | patch only: `config/self_edit_allowlist.json` is a human commit (docs/plans/ALLOWLIST_SEQUENCE.md) |
| B4 | Off-disk backups: both databases, knowledge-base documents, vault-key export | Kimi | A2 | `scripts/backup_db.py`, a new restore check, docs |
| B6 | Split `jarvis/admin/server.py` (5,575 lines, 88 routes) into routers | Codex | B2 | `jarvis/admin/**` |
| C8 | Rewritten UI boxes into ROADMAP.md; box 549 ("one carousel owner on each screen") is reworded to match decision 4 | Codex | rows approved, decision 4 | ROADMAP.md acceptance lists |

Claude cannot run `swift test`; it writes no Swift until B1 shows the hosted runner builds and tests the app, and its Swift PRs (C7b) rely on that CI job plus a reviewer's local run.

### WS-35: Codex lane (CI, layouts, results, phone)

| Id | Work | Reviewer | Depends on | Files |
|---|---|---|---|---|
| C10 | Performance baseline for box 810 on the freeze build, before C1a merges: Codex writes the steps, Larry runs them on the Mac | Kimi | freeze build deployed | `docs/acceptance/**` |
| C1a | Delete layouts 0 and 1 in the app. Keep `OrbFieldView`'s compact mode, which layout 2 still embeds (`Console/AdaptiveStageView.swift` lines 115 and 130), until C6 replaces it | Kimi | A2, decision 3 | every file with `layoutVersion` (12 source and 13 test files at `b9024ed`: `grep -rl layoutVersion macos/MortimerHost`), including `App/InterfaceLayoutVersion.swift`, `MortimerHostApp.swift`, `ConsoleView.swift`, `App/AppMessageRouter.swift`, `App/SupportingDisplayCoordinator.swift`, `App/ConsoleActionCoordinator.swift`, `Display/DisplayWindowView.swift`, `WorkspaceView.swift`, `WorkspaceResultPane.swift`, `DisplayWindowStore.swift`, `Console/ConversationThreadView.swift`, `CommandConsoleView.swift`, `AdaptiveStageView.swift` |
| B1 | macOS Swift CI job: `swift test` for JarvisKit, MortimerHost and MortimerPhoneCore; extends WS-30's adopted `phone-core-swift` claim (ROADMAP.md line 1689 at `4e58eaa`) | Claude, Kimi | A1 | `.github/workflows/validate.yml` |
| B5 | Widen ruff from F821 to the pyflakes set; ship NLTK test data offline | Claude | B1 | `.github/workflows/validate.yml`, the lint fixes it forces |
| C4 | Swift block renderer that wraps the existing typed views | Kimi | C0, C1a | `Display/**`, `App/AppMessageRouter.swift`, `macos/JarvisKit/Sources/JarvisKit/AppMessage.swift`, `macos/JarvisKit/Tests/JarvisKitTests/Fixtures/` |
| C5 | Result carousel A, with "show all results" as B; flat fallback for Reduce Transparency and Reduce Motion; the reuse repair for box 196. Takes the result card and arrival notice out of the thread (`ConversationThreadView.swift` near lines 402 and 669) and the `result_next`/`result_previous`/`result_mode` actions. Acceptance: VoiceOver labels, keyboard paging, nothing shown by colour alone | Kimi | C4 | `Display/**`, `Stores/WorkspaceStore.swift`, `Stores/WorkspaceRecents.swift`, `Stores/DisplayResultStore.swift`, `Placement/**`, `App/ResponseResultRouter.swift`, `App/AppMessageRouter.swift`, `App/SupportingDisplayCoordinator.swift`, the carousel slot in `Console/AdaptiveStageView.swift`, those parts of `ConversationThreadView.swift` and `App/ConsoleActionCoordinator.swift` |
| C9 | Phone orb in the iPhone preview, synthetic levels until WS-30 phone voice exists. The orb renderer lives in the Mac app target and `ios/MortimerPhoneCore/Package.swift` has no dependencies, so C9 first moves `CometOrbRenderer` and `CrystalGlassRig` into a shared package both apps import (both are SwiftUI only) | Kimi | C6, decision 5 | `ios/**`, a new shared package and its `Package.swift`, the two renderer files (after C6 lands), `PhonePreviewUITests` |
| F1 | Acceptance fix (on `main`, by name): `PhoneRemoteAuthorityProcessTests.testOrdinaryUnknownWaitRetainsActualSingletonAfterPartialEOF` fails at `4e58eaa` (Kimi's revalidation, #325) | Kimi | none | `macos/MortimerHost/Sources/PhoneRemoteAuthority*/**` and its tests |

Interface-review findings whose files are in `Display/**` (the white-on-white export buttons, duplicated titles) ride with C4 or C5.

### WS-36: Kimi lane (review, design system, orb, thread)

| Id | Work | Reviewer | Depends on | Files |
|---|---|---|---|---|
| A3 | Combined-source review, production `b136a2a` to the freeze SHA (already claimed in WS-17); Kimi's own files go to Claude | Claude for the excluded files | freeze SHA | docs only |
| C2 | Add C0b's six tokens to `AppTheme` without changing `amber` (25 files use it for general warnings), `green` or `red`. Teal and rust already exist as `AppTuning`'s `userRGB` and `assistantRGB` (lines 125 and 126 at `b9024ed`); the tokens reuse those values, and the stale `#FFB454` in the doc comment at line 122 is corrected to `#E07020`. Check contrast of every new token on glass; fix the interface-review findings in these files. Moving call sites to the new tokens belongs to C5 (cards) and C7a (thread) | Codex | C0b | `App/AppTheme.swift`, `App/Glass.swift`, `App/AppTuning.swift`, `Console/TopBarView.swift`, `Console/ConsoleActionBar.swift` |
| C6 | Glass energy orb on the Mac: voice levels, thinking swirl, pointer bend, tap ripple; replaces `OrbFieldView`'s compact satellites. Builds `docs/interface-research/orb-plasma/ORB_SPEC.md`: a tap toggles the mic and a 350 ms hold is push-to-talk sharing Space's `pttOwned` guard (`MicControlsView.swift` lines 19 to 113), with a button role, since the orb view is not hit-testable today (`VoiceWaveView.swift` line 63); arcs probe in `OrbShellFrameTimeTests`; flash cap | Codex | C2, C5 (shares `AdaptiveStageView.swift`) | `Console/CometOrbRenderer.swift`, `VoiceWaveView.swift`, `CrystalGlassRig.swift`, `MotionPreferences.swift`, `WaveTuningView.swift`, `App/VoicePresentationState.swift`, the orb slots in `Console/AdaptiveStageView.swift`, `OrbFieldView.swift` (removal), `OrbShellFrameTimeTests` |
| C7a | Thread: activity row and inline approve/decline (reading the approval signal `hasPendingDraft` in `Stores/DisplayResultStore.swift`); Space reaches focused controls. Acceptance: VoiceOver, keyboard, nothing shown by colour alone | Codex | C0, C1a, C5 | `Console/ConversationThreadView.swift`, `MicControlsView.swift`, `CommandConsoleView.swift`, `App/ConsoleActionCoordinator.swift`, `Stores/ConversationStore.swift`; `ConsoleProtocol.swift` and `App/ConsoleActionRegistry.swift` if C0 makes approve/decline a console action |

Paths without a prefix are under `macos/MortimerHost/Sources/MortimerHost/`.

### Hand-off points (one file, two items)

- `.github/workflows/validate.yml`: A1 (Claude) first, then B1 and B5 (Codex), then C1b's web removal (Claude).
- `Console/AdaptiveStageView.swift`, the one place the thread, results and orb meet: C1a, then C5 (carousel slot), then C6 (orb slots) and C7a.
- `Console/ConversationThreadView.swift`, `App/ConsoleActionCoordinator.swift`, `Stores/DisplayResultStore.swift`: C1a, then C5 takes the result card, arrival notice and result actions, then C7a.
- `App/AppMessageRouter.swift`: C1a, then C4, then C5 (all Codex).
- `ConsoleView.swift`, `MortimerHostApp.swift`: C1a first; C7b builds on it.
- `macos/JarvisKit`: Codex edits `AppMessage.swift` (C4); Claude edits `ClientMessage.swift` and `JarvisClient.swift` (C7b).
- `jarvis/bot/pipeline.py`: C3's display emit sites and C7-py's registration lines; WS-17 and WS-05 hold other parts (§6). C3 lands first.
- `CometOrbRenderer.swift`, `CrystalGlassRig.swift`: C6, then C9 moves them into the shared package.

## 5. Sequence and estimates

| Days (from the freeze) | Claude | Codex | Kimi |
|---|---|---|---|
| 1 to 2 | A1, A2, C0 | C10 steps, C1a, F1 | A3 review |
| 3 to 6 | C0b, B2, B3, B4, C3, C1b (after B1) | B1, B5, C4 | A3 finish, C2 |
| 7 to 11 | C7-py, C7b, B6 | C5 | C6 (after C5's stage slot), C7a |
| 12 to 14 | C8, review | C9, review | C7a finish, review |

Agent-days per item (estimates): C0 1, C0b 0.5, C3 2 to 3, C7-py 1 to 2, C7b 2, C1b 1, B2 to B4 about 2, B6 2 to 3, C8 1; C10 0.5, C1a 1 to 2, B1 0.5 to 1, B5 0.5, C4 2 to 3, C5 3 to 4, C9 2 to 3, F1 unknown; A3 2 to 3, C2 1 to 2, C6 2 to 3, C7a 2. Speed basis: #171 (1,376 Swift lines, 1 day), #164 (769, 1 day), #216 (967, under a day), #198 (2,181, 3 days), #290 (7,272 Swift plus 25,040 Python, 8 days), from git merge history. Projected closure near 2026-12-09 if the freeze starts this week; a projection, not a measurement. The critical path is C0, C1a, C4, C5, then C6 and C7a.

The run-now acceptance batch (27 boxes) runs on the freeze build once A3 passes and Larry deploys; the final build adds the 19 rewritten UI boxes, the 11 final-build boxes and five days of use.

## 6. Scope overlaps to record in ROADMAP.md §4

- `.github/workflows/validate.yml`: A1, B1, B5 and C1b here; WS-20 and WS-30 already claim parts.
- `scripts/deploy_main.sh`: C1b edits two lines; the file sits in WS-17's bounded scope (Codex).
- `jarvis/bot/pipeline.py`: C3 changes the display emit sites and C7-py adds registration lines; WS-17 and WS-05 hold parts (CX-26, CX-27).
- `sandbox/**`, `jarvis/selfedit/service.py`, `config/self_edit_allowlist.json`: C1b supplies patches; Larry commits them.
## 7. Decisions

Decision 1 (freeze with `next`) is Larry's 01:58:16 answer. Larry answered decisions 2 to 7 at 02:35:41 ("Take your picks"):

| # | Decision | Answer | Affects |
|---|---|---|---|
| 2 | Palette | the approved orb palette: listening `#6673FF`, user teal `#2DD4BF`, Mortimer rust `#E07020`, OK `#A6FFC1`, needs-you ring `#FFD84A`, error `#FF598B`; all new tokens, `amber` unchanged | C0b, C2 |
| 3 | Delete layouts 0 and 1, `web/`, MortimerShell, GlassSpike, VPIOBench | delete all | C1a, C1b |
| 4 | Second screen: carousel too, or keep its grid | keep the grid | C5 scope; box 549's wording (C8); the five WS-21 boxes stay in sitting 2 |
| 5 | Phone orb now on synthetic levels, or wait for WS-30 phone voice | now | C9 |
| 6 | Approve the WS-34 to WS-36 rows | approved | rows added in a separate docs PR |
| 7 | Parked WS-23 to WS-26 | parked until after closure | nothing here |

## 8. Review protocol

- Reviewer is named per item above; if that system is busy, any system other than the author may review.
- Swift PRs need a `swift test` run by Codex, Kimi or (after B1) CI, recorded in the PR body with counts.
- PR body: system, session reference, row and item id, files outside the item's list with the reason, and the commands run.
- Review verdicts go in a docs-only log under `docs/roadmap-log/`, never as an edit to the author's code.

## 9. Not tested

- That GitHub's hosted `macos-15-intel` runner with Xcode 26.3 builds and tests MortimerHost (B1's first run settles it).
- That Liquid Glass stays readable on carousel panels at an acceptable GPU cost (a half-day spike in C5, then Instruments on Larry's Mac).
- That a typed request can reuse the bot's context-injection path (`jarvis/bot/late_result.py`, `pipeline.py` line 1581) as a real user turn with transcript and sensitive-turn handling intact (a C7-py unit test).
- Every size and day count in §5.
- What causes the `PhoneRemoteAuthority` failure (F1 investigates).

## Progress log

Only the daily batch PR adds lines here; other PRs record status in their own `docs/roadmap-log/` file (Larry, 2026-11-12 16:41:17 UTC, "Adopt the batch rule"; `AGENTS.md`, *Status records and the daily batch*).

- 2026-11-11: plan written and synced to the repo with the freeze docs PR (Claude). Freeze SHA not yet recorded: Larry is deciding whether the flaky `test_outer_task_deadline_covers_tool_execution` (seen in #324's CI) is fixed before the freeze.
- 2026-11-11: Larry's rule (02:07:51 UTC, "at least the enhancement planning"): interface planning runs on Fable 5.2. A Fable 5.2 review of the interface items, checked against the tree at `b9024ed`, changed §4 to §6: C1 split into C1a (app layouts, Codex, day 1) and C1b (`web/` and the old packages with their Python, sandbox, CI and docs fallout, Claude); C0b split out for tokens; C2 adds an `approval` token instead of recolouring `amber`; C7 split, with the composer half (C7b) moved to Claude; C10 added for the box 810 baseline; file lists for C3 to C7 and C9 completed; `AdaptiveStageView.swift` and three thread/result files added to the hand-offs; C9 gets a shared orb package. Before this, the plan's text was written by Claude on Opus; the deep review, UI critique, design directions 1 to 4 and the carousel idea it draws on were Fable 5.2.
- 2026-11-11: Larry answered decisions 2 to 7 (02:35:41, "Take your picks"). §7 records the answers; C0b and C2 carry the approved palette (errors are `#FF598B`, replacing the earlier proposed `#FF5C8A`); the three lane rows go to ROADMAP.md in their own docs PR. Four items still depend on the final orb design and are rechecked when the UI thread's Fable 5.2 pass lands: keeping `OrbFieldView`'s compact mode in C1a, the C0b/C2 tokens, C6's orb tap versus Space rule, and C9's shared package.
- 2026-11-11: #328 merged (`b2fbb2d`), giving the flaky deadline test headroom; #325 to #327 and #329 (docs) followed. Claude recorded `5777e98cf1cdbaa65eb13079044693794c071927` as the freeze SHA in WS-17's combined-source review claim on Larry's 01:58:16 direction and cut `next` from it (item A2).
- 2026-11-11: Larry approved the orb (03:07 UTC, "Looks right"); its spec and the mockups page are now in `docs/interface-research/orb-plasma/`. Claude rechecked the four orb-dependent items against it. (1) C1a still keeps `OrbFieldView`'s compact mode until C6, and C6 must move its pending-draft signal (`OrbFieldView.swift:289`) to the `#FFD84A` needs-you ring before removing it. (2) The C0b/C2 tokens match the spec unchanged; the muted arc grey `#5A6478` and the white core stay renderer constants, not theme tokens, and changing the idle `#7C8CFF` and the two nucleus tests needs Larry's OK (spec, Gates). (3) C6's tap versus Space rule is now settled by the spec (tap toggles, 350 ms hold is push-to-talk on the `pttOwned` guard); the C6 row says so. (4) C9's shared package still holds: the spec keeps `CrystalGlassRig.swift` and changes only `CometOrbRenderer.swift`, the same two files, and its arc-width floor is what keeps arcs visible at phone size. For the orb's own depth (his 03:12 question) Larry picked refraction plus option 1's contact shadow and cast light (03:18:31 "I think the third", 03:19:59 "I actually like the third but add the shadow from the first"). This adds to C6: a `layerEffect` Metal shader on the rail behind the orb, the app's first, and frame-time probes before the rest of the orb. The tilt-parallax fallback needs Larry's OK.
- 2026-11-11: A1 merged into `next` (#331), so validate, sandbox and knowledge-base now run on `next` pushes and PRs. C0 and C0b are drafted in #332 into `next` (`docs/contracts/MORTIMER_INTERFACE_CONTRACTS.md`, drafted on Fable 5.2); Codex and Kimi review it, and Larry answers its five §7 questions. C0 found that the `actions`-table draft gate is retired (`sandbox_required()` in `mcp_git` and `mcp_repo`), so `hasPendingDraft` has no live source; approve/decline is specified as a client-message pair, not a console action. WS-34 is now `claimed`.
- 2026-11-11: Larry's five §7 answers for #332 taken as the plan's picks (03:52:52, "Go with your picks"). Opened into `next`, all CI green: C0 types #336, C3 composer #344, C7-py handlers #345 (stacked in that order), B2 #342, B3 #343 (allowlist patch for Larry) and B4 #341. Kimi (B1 to B5, S1 to S4) and Codex (R1 to R3) requested changes on #332; it was revised at `14fa78b` (contract §8 maps each finding) and the code followed in #336, #344 and #345. Approve now settles only after its turn is enqueued, decline starts no model run, approvals are matched by operation identity, and composed messages carry a top-level `answer_revision`. Open for Larry: whether a bare yes with no tracked approval keeps going to the Supervisor (§3.10 rule 2).
- 2026-11-12: Claude did C8 in a docs PR to `main` (stacked on #333). The 19 rewritten UI boxes of `docs/acceptance/mac-acceptance-2026-11-11.md` section 4 are in `ROADMAP.md` in their own workstreams, unticked and tagged "(final build, C8)". Box 828 is now a design rule line. Box 549 is one of the 19 and now says the carousel is on the main screen and the second screen keeps its grid (decision 4). Codex reviews.
- 2026-11-12 (daily batch): A3, Claude's part. The Kimi-authored files excluded from Kimi's combined-source review (WS-31 NR1, WS-32 #275) are the approved bytes at the freeze; APPROVE, no release-risk finding (#349, [log](../roadmap-log/2026-11-12-ws-17-claude-a3-excluded-files.md)).
- 2026-11-12 (daily batch): Claude's nonauthor reviews of Codex's WS-35 PRs: C10 #335 APPROVE at `073c5ac` (#354, [log](../roadmap-log/2026-11-12-ws-35-c10-claude-review.md)); F1 #339 APPROVE at `baf4dfe` (#355, [log](../roadmap-log/2026-11-12-ws-35-f1-claude-review.md)); C1a #337 APPROVE at `7cc49f9` (#356, [log](../roadmap-log/2026-11-12-ws-35-c1a-claude-review.md)). B1 #338: the workflow is correct but not green (#347, [log](../roadmap-log/2026-11-12-ws-35-b1-claude-review.md)); its six hosted-runner failures are runner rendering, timing and OCR effects, not code bugs, with fix options for Larry and Codex (#357, [log](../roadmap-log/2026-11-12-ws-35-b1-runner-failures-claude-diagnosis.md)).
- 2026-11-12 (daily batch): C10 section 2 ran on Larry's Mac at the freeze `5777e98`: nine probes, all exit 0; medians crystal p50 6.150 ms and p95 13.499 ms, memory graph p95 9.656 ms, Skills selection-to-layout p95 13.402 ms wide and 7.958 ms compact. Section 3 waits on the freeze deploy (#339). Crystal p50 varied up to 23% between runs, so Larry set C6's rule (16:32 UTC, "Use your pick for C6"): five crystal and five arcs runs back to back in one session, comparing medians, 1.10× limits on p50 and p95, p95 under 16.7 ms; `ORB_SPEC.md` Measure first states it. Codex applies the wording to #335's section 4 after it merges (#358, [receipt](../roadmap-log/2026-11-12-ws-35-c10-component-baseline-receipt.md), [decision](../roadmap-log/2026-11-12-ws-36-c6-same-session-comparison-decision.md)).
- 2026-11-12 (daily batch): Larry adopted the daily status batch rule (16:41 UTC, "Adopt the batch rule"; §0 rule 16, `AGENTS.md`). From now on PRs record status only in their own log file and this log is filled by the daily batch PR (#359, [log](../roadmap-log/2026-11-12-ws-34-daily-status-batch-rule.md)).
- 2026-11-12 (daily batch): Codex's C0/C0b re-review: APPROVE at #332 `14fa78b`, with #334's R1–R3 and the origin-stamping note addressed. All five §4.3 greps ran (8/14/1/13/3 matches); only checks 3 and 5 meet their line allowlists today, and the legacy paths left are expected for C1a, C5 and C6. Source review only, no UI acceptance (#350, [log](../roadmap-log/2026-11-12-ws-35-c0-contract-rereview.md), [moved progress](../roadmap-log/2026-11-12-ws35-pr350-batch-rule-progress.md)).
- 2026-11-12 (daily batch): Kimi's independent reviews of Claude's docs PRs: #358 APPROVE at `6354680`, C10 medians recomputed from the raw files with no discrepancy (#360, [log](../roadmap-log/2026-11-13-ws-35-ws-36-pr-358-independent-review.md)); #359 APPROVE at `16ac1b9` (#361, [log](../roadmap-log/2026-11-13-ws-34-pr-359-independent-review.md)).
- 2026-11-12 (daily batch): Larry approved F1 #339 by name at 17:12:26 UTC ("I approve #339"), recorded on the PR under §0 rule 15. The merge decision is his.
- 2026-11-11 (daily batch, 11-13): the two C0/C0b reviews of #332 at `1f8aca7`, both CHANGES REQUESTED and both merged into `next`: Codex's R1 to R3 (fallback revision identity, direct-result completion, the legacy transcript-to-result route; #334, [log](https://github.com/Larryfix71566/jarvis-voice-ai/blob/next/docs/roadmap-log/2026-11-11-ws35-c0-contract-review.md), [moved progress](https://github.com/Larryfix71566/jarvis-voice-ai/blob/next/docs/roadmap-log/2026-11-12-ws35-pr334-batch-rule-progress.md)) and Kimi's five blockers (self-contained approval identity, exact-operation correlation, local decline with no model run, enqueue before settle, sensitive-turn guards; #340, [log](https://github.com/Larryfix71566/jarvis-voice-ai/blob/next/docs/roadmap-log/2026-11-11-ws-36-c0-contract-review.md)). #332's revision at `14fa78b` answered both.
- 2026-11-12 (daily batch, 11-13): Merged into `next`: C0 types #336, C3 composer #344 and C7-py handlers #345 (PR state; no log files). B6 #353: the admin sidecar's 88 route handlers moved verbatim into 13 modules under `jarvis/admin/routes/`, `server.py` from 5,579 to 2,835 lines; routes 88 to 88, middleware 4 to 4, the same unit failure set before and after; #363 carries the docs follow-up ([log](https://github.com/Larryfix71566/jarvis-voice-ai/blob/next/docs/roadmap-log/2026-11-12-ws-34-b6-admin-routes.md)).
- 2026-11-12 (daily batch, 11-13): Codex's review of B2 #342 at `5d714af`: CHANGES REQUESTED against Larry's current criteria. R1: no native request sets `X-Mortimer-Client` (shared HTTP sender and the voice WebSocket); R2: a request without Origin is allowed, not refused; R3: a malformed numeric port raises ValueError instead of a controlled 403/4403; C1: the three request-guard config keys are not reserved in §3. Reviewer-local tests 81 passed; 16 ASGI behavior assertions; four port-defect reproductions. #342 merged into `next` at `e42d09a`, which refuses malformed ports (R3); R1, R2 and C1 are open (#351, [log](../roadmap-log/2026-11-12-ws-35-b2-request-guard-review.md), [moved progress](../roadmap-log/2026-11-12-ws35-pr351-batch-rule-progress.md)).
- 2026-11-12 (daily batch, 11-13): Codex's review of C8 #348 at `aed1409`: APPROVE. All 19 rewritten boxes open and final-build-only, box 828 a design rule, box 549 per decision 4; 120 open to 119, all 25 checked entries kept. Nits: the source checklist's box 549 still says one carousel owner on each screen; record C8's after-merge state (#352, [log](../roadmap-log/2026-11-12-ws-35-c8-review.md), [moved progress](../roadmap-log/2026-11-12-ws35-pr352-batch-rule-progress.md)).
- 2026-11-12 (daily batch, 11-13): Merged into `next`: C10 instructions #335 ([log](https://github.com/Larryfix71566/jarvis-voice-ai/blob/next/docs/roadmap-log/2026-11-11-ws35-c10-baseline-instructions.md), [moved progress](https://github.com/Larryfix71566/jarvis-voice-ai/blob/next/docs/roadmap-log/2026-11-12-ws35-pr335-batch-rule-progress.md), [row text](https://github.com/Larryfix71566/jarvis-voice-ai/blob/next/docs/roadmap-log/2026-11-12-ws35-pr335-row-status-moved.md)) and C1a #337: layouts 0 and 1 removed, stored values migrate to 2, `appearance.set` rejects 0 and 1, the thread flag and compact `OrbFieldView` kept until C6; on source `69f9805` MortimerHost's app target ran 590 tests with 0 failures, and the authority target's one failure was F1's ([log](https://github.com/Larryfix71566/jarvis-voice-ai/blob/next/docs/roadmap-log/2026-11-11-ws35-c1a-layout-removal.md), [moved progress](https://github.com/Larryfix71566/jarvis-voice-ai/blob/next/docs/roadmap-log/2026-11-12-ws35-pr337-batch-rule-progress.md), [row text](https://github.com/Larryfix71566/jarvis-voice-ai/blob/next/docs/roadmap-log/2026-11-12-ws35-pr337-row-status-moved.md)).
- 2026-11-12 (daily batch, 11-13): B1 #338 merged into `next`: full `swift test` for JarvisKit, MortimerHost and MortimerPhoneCore on `macos-26-intel` with Xcode 26.3 (the plan's macOS 15 runner cannot run the macOS 26 targets). Hosted Swift 6.2.4 failed to type-check `SkillsWorkspaceView.swift:380`; Larry approved splitting the expression, after which 618 Host tests ran with 16 assertion failures in seven tests. Larry picked "Skip on GitHub only" (15:01 ET): six of those tests skip when `GITHUB_ACTIONS` is true and still gate on the Mac; the image-cancellation test stays enabled. The Scope line the PR carried is back in WS-35 ([log](https://github.com/Larryfix71566/jarvis-voice-ai/blob/next/docs/roadmap-log/2026-11-11-ws35-b1-swift-ci.md), [moved progress](https://github.com/Larryfix71566/jarvis-voice-ai/blob/next/docs/roadmap-log/2026-11-12-ws35-pr338-batch-rule-progress.md), [row text and Scope](https://github.com/Larryfix71566/jarvis-voice-ai/blob/next/docs/roadmap-log/2026-11-12-ws35-pr338-row-status-moved.md)).
- 2026-11-12 (daily batch, 11-13): F1 #339 merged into `main` as `c23dda5`. The authority process test now skips when the optional owner harness is absent and finds Python through the existing helper; with the owner enabled, the authority suite ran 28 tests with no skips, and the full MortimerHost run 618 tests, 7 skips, 0 failures. Production source unchanged. Its handoff asks its author to merge `main` forward into `next` without rebasing; `c23dda5` is not in `next` yet (#339, [log](../roadmap-log/2026-11-11-ws35-f1-process-prerequisites.md), [moved progress](../roadmap-log/2026-11-12-ws35-pr339-batch-rule-progress.md)).
