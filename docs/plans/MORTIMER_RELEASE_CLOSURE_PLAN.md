# Mortimer release closure plan: acceptance on main, new interface on `next`

- **Status:** adopted when the PR that adds this file merges. The freeze is WS-33 and the WS-17 combined-source review claim. The three lanes are proposed rows WS-34 (Claude), WS-35 (Codex) and WS-36 (Kimi); they reach ROADMAP.md §2 in a follow-up docs PR once Larry approves them (decision 6), and no lane item starts before its row is on `main` (AGENTS.md: no row, no work).
- **Source of truth:** this file. The Claude Doc "Mortimer combined implementation plan" in Larry's account mirrors it; when they differ, this file wins (ROADMAP.md §0 rule 11 still ranks ROADMAP.md above it).
- **Built at:** `origin/main` `4e58eaa`; checked again at `b9024ed` (2026-11-11, after #322 and #324). Line numbers below are from those commits.
- **Written by:** Claude (Opus), from Claude's 2026-11-10 deep review, the 2026-11-10 interface review and mockups, ROADMAP.md and AGENTS.md.

## Larry's direction

All times UTC, in his Claude Duet channel:

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

Item ids are stable; sizes are estimates from line counts at `4e58eaa`, not measurements. Every item is a PR into `next` unless marked.

### WS-34: Claude lane (Python, contracts, roadmap)

| Id | Work | Reviewer | Depends on | Files |
|---|---|---|---|---|
| A1 | Add `next` to the CI triggers | Codex | `next` exists | `.github/workflows/validate.yml`, `sandbox.yml`, `knowledge-base.yml` (trigger lines only; lands before B1) |
| A2 | Cut `next` from the freeze SHA | none | freeze SHA recorded | branch only |
| C0 | Contracts: block-kit `layout` schema for one composed answer, a typed-request client message, an approve/decline action, colour and type tokens; design rule from box 828 | Codex and Kimi | A2 | `docs/contracts/**` (new), Python message types and their tests |
| C3 | Python composer: one composed answer per request, built from the existing formatters | Kimi | C0 | `jarvis/bot/display.py`, `jarvis/bot/compose*.py` (new), their unit tests |
| C7-py | Typed request and approve/decline handlers in the bot | Kimi | C0 | a new `jarvis/bot/typed_request.py`; registration lines in `jarvis/bot/pipeline.py` (shared with WS-17/WS-05, see §6) |
| B2 | Host and Origin allow-list plus a required header on mutating routes (admin, bot, costs) | Codex | A2 | `jarvis/admin/**`, `jarvis/costs_api.py`, the bot runner's middleware; the app's header line is Kimi's (C7) |
| B3 | Security modules and `config/model_access.yaml` into the self-edit deny tier | Kimi | A2 | patch only: `config/self_edit_allowlist.json` is a human commit (docs/plans/ALLOWLIST_SEQUENCE.md) |
| B4 | Off-disk backups: both databases, knowledge-base documents, vault-key export | Kimi | A2 | `scripts/backup_db.py`, a new restore check, docs |
| B6 | Split `jarvis/admin/server.py` (5,575 lines, 88 routes) into routers | Codex | B2 | `jarvis/admin/**` |
| C8 | Rewritten UI boxes into ROADMAP.md | Codex | rows approved | ROADMAP.md acceptance lists |

Claude cannot run `swift test`; it writes no Swift until B1 shows the hosted runner builds the app.

### WS-35: Codex lane (CI, deletion, results, phone)

| Id | Work | Reviewer | Depends on | Files |
|---|---|---|---|---|
| B1 | macOS Swift CI job: `swift test` for JarvisKit, MortimerHost and MortimerPhoneCore; extends WS-30's adopted `phone-core-swift` claim (ROADMAP.md line 1689) | Claude, Kimi | A1 | `.github/workflows/validate.yml` |
| B5 | Widen ruff from F821 to the pyflakes set; ship NLTK test data offline | Claude | B1 | `.github/workflows/validate.yml`, the lint fixes it forces |
| C1 | Delete layouts 0 and 1 and the legacy stacks: `web/`, `macos/MortimerShell`, `macos/GlassSpike`, `macos/VPIOBench`, `OrbFieldView`, `AdaptiveStageView`'s layout branch | Kimi | A2, decision 3 | those paths; `App/InterfaceLayoutVersion.swift`, `MortimerHostApp.swift` layout storage, `ConsoleView.swift` layout branch; `scripts/deploy_main.sh` (lines 244, 418), `scripts/run_web.sh`, `validate.yml` lines 109 to 111 |
| C4 | Swift block renderer that wraps the existing typed views | Kimi | C0, C1 | `macos/MortimerHost/Sources/MortimerHost/Display/**`, `macos/JarvisKit/Sources/JarvisKit/AppMessage.swift` |
| C5 | Result carousel A, with "show all results" as B; flat fallback for Reduce Transparency and Reduce Motion; the reuse repair for box 196 | Kimi | C1 | `Display/**`, `Stores/WorkspaceStore.swift`, `Stores/WorkspaceRecents.swift`, `Stores/DisplayResultStore.swift`, `Placement/**` |
| C9 | Phone orb in the iPhone preview, synthetic levels until WS-30 phone voice exists | Kimi | C6, decision 5 | `ios/**` |
| F1 | Acceptance fix (on `main`, by name): `PhoneRemoteAuthorityProcessTests.testOrdinaryUnknownWaitRetainsActualSingletonAfterPartialEOF` fails at `4e58eaa` (Kimi's revalidation, #325) | Kimi | none | `macos/MortimerHost/Sources/PhoneRemoteAuthority*/**` and its tests |

Interface-review findings whose files are in `Display/**` (the white-on-white export buttons, duplicated titles) ride with C4 or C5.

### WS-36: Kimi lane (review, design system, orb, thread)

| Id | Work | Reviewer | Depends on | Files |
|---|---|---|---|---|
| A3 | Combined-source review, production `b136a2a` to the freeze SHA (already claimed in WS-17); Kimi's own files go to Claude | Claude for the excluded files | freeze SHA | docs only |
| C2 | Tokens and the interface-review findings in Kimi's files; approvals yellow `#FFD84A`, errors rose `#FF5C8A`, rust kept for Mortimer (decision 2) | Codex | C0, C1 | `App/AppTheme.swift`, `App/Glass.swift`, `App/AppTuning.swift`, `Console/TopBarView.swift`, `Console/ConsoleActionBar.swift` |
| C6 | Glass energy orb on the Mac: voice levels, thinking swirl, pointer bend, tap ripple | Codex | C2 | `Console/CometOrbRenderer.swift`, `VoiceWaveView.swift`, `CrystalGlassRig.swift`, `MotionPreferences.swift`, `WaveTuningView.swift` |
| C7 | Thread: activity row, inline approve/decline, composer and ⌘K; Space reaches focused controls | Codex | C0, C1 | `Console/ConversationThreadView.swift`, `AttachmentTrayView.swift`, `MicControlsView.swift`, `CommandConsoleView.swift`, `App/ConsoleActionCoordinator.swift`, `Stores/ConversationStore.swift`, `macos/JarvisKit/Sources/JarvisKit/ClientMessage.swift` |

Paths without a prefix are under `macos/MortimerHost/Sources/MortimerHost/`.

### Hand-off points (one file, two lanes)

- `.github/workflows/validate.yml`: A1 (Claude) lands first, then B1 and B5 (Codex). C1's web build removal goes after B1.
- `ConsoleView.swift`, `MortimerHostApp.swift`: C1 (Codex) lands first; C7 (Kimi) builds on it.
- `macos/JarvisKit`: Codex edits `AppMessage.swift` (C4), Kimi edits `ClientMessage.swift` (C7). Neither edits the other's file without saying so in the PR.
- `jarvis/bot/pipeline.py`: only C7-py's registration lines, which WS-17 and WS-05 also hold (§6).

## 5. Sequence and estimates

| Days (from the freeze) | Claude | Codex | Kimi |
|---|---|---|---|
| 1 to 2 | A1, A2, C0 | F1, B1, then C1 | A3 review |
| 3 to 6 | B2, B3, B4, C3 | C1 finish, B5, C4 | A3 finish, C2 |
| 7 to 11 | C7-py, B6 | C5 | C6, C7 |
| 12 to 14 | C8, review | C9, review | C7 finish, review |

Agent-days per item (estimates): C0 1, C3 2, C7-py 1 to 2, B2 to B4 about 2, B6 2 to 3, C8 1; B1 0.5 to 1, B5 0.5, C1 1 to 2, C4 2 to 3, C5 3 to 4, C9 1 to 2, F1 unknown; A3 2 to 3, C2 2, C6 2 to 3, C7 3 to 4. Speed basis: #171 (1,376 Swift lines, 1 day), #164 (769, 1 day), #216 (967, under a day), #198 (2,181, 3 days), #290 (7,272 Swift plus 25,040 Python, 8 days), from git merge history. Projected closure near 2026-12-09 if the freeze starts this week; a projection, not a measurement.

The run-now acceptance batch (27 boxes) runs on the freeze build once A3 passes and Larry deploys; the final build adds the 19 rewritten UI boxes, the 11 final-build boxes and five days of use.

## 6. Scope overlaps to record in ROADMAP.md §4

- `.github/workflows/validate.yml`: A1, B1, B5 and C1 here; WS-20 and WS-30 already claim parts.
- `scripts/deploy_main.sh`: C1 edits two lines; the file sits in WS-17's bounded scope (Codex owns both).
- `jarvis/bot/pipeline.py`: C7-py adds registration lines; WS-17 and WS-05 hold parts (CX-26, CX-27).

## 7. Decisions

Decision 1 (freeze with `next`) is Larry's 01:58:16 answer. Decisions 2 to 7 stay as Claude's recommendations until Larry answers; the items that depend on them wait:

| # | Decision | Recommendation | Waits on it |
|---|---|---|---|
| 2 | Approvals yellow `#FFD84A`, errors rose `#FF5C8A`, rust stays Mortimer's | both | C2 colours |
| 3 | Delete layouts 0 and 1, `web/`, MortimerShell, GlassSpike, VPIOBench | delete all | C1 |
| 4 | Second screen: carousel too, or keep its grid | keep the grid | C5 scope; the five WS-21 boxes |
| 5 | Phone orb now on synthetic levels, or wait for WS-30 phone voice | now | C9 |
| 6 | Approve the WS-34 to WS-36 rows | approve | merge of this file |
| 7 | Parked WS-23 to WS-26 | after closure | nothing here |

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

- 2026-11-11: plan written and synced to the repo with the freeze docs PR (Claude). Freeze SHA not yet recorded: Larry is deciding whether the flaky `test_outer_task_deadline_covers_tool_execution` (seen in #324's CI) is fixed before the freeze.
