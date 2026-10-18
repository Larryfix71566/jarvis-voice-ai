---
date: 2026-10-17
system: claude
rows: [WS-17]
prs: []
---

- 2026-10-17 (WS-17 UI2-24/25 diagnosis, read-only): Claude (Cowork) read the campaign receipt, the code on main 7324d56 and the production bot log; no code, row or plan edit by Claude. The full document follows; Larry's dispatch is the companion larry entry.

# WS-17 repair plan — UI2-24/25 (Recents, voice selection, fresh-result reuse)

Claude (Cowork), 2026-10-17. Written against main `7324d56`, the 10-17 campaign receipt
(`docs/acceptance/command-console/receipts/acceptance-campaign-2026-10-17.md`), and the
code on main. Session: https://claude.ai/code/session_01L1hFDFBVF6d8f7XrXJei87

## 0. Ownership first

WS-17 is Codex's row. Larry reassigned the remaining CC7a work from Claude to Codex on
10-07 (ROADMAP §4 CX-20), and the row's current `Next step` reads *"codex: prepare the
bounded Recents/voice-selection/reuse repair under WS-17"*. So "a repair that does not
interfere with Codex" has exactly two honest shapes:

- **A — Diagnosis hand-off (no reassignment).** Claude supplies the diagnosis below and
  the evidence commands; Codex builds the repair under its row. Claude touches no WS-17
  scope path, no WS-17 row/plan/log file, and no Codex branch. This document is that
  hand-off; nothing else is needed from Claude unless Larry asks.
- **B — Reassignment.** Larry edits the WS-17 block on main (`Owner: claude` for the
  repair slice, branch in `Where`, status `claimed`, §4 note superseding CX-20's
  ownership line), tells Codex, and Claude builds on `ws17/ui2-24-25-repair` from main.
  Codex cross-reviews the exact head (C3; CX-15/CX-20 already require it). Codex's open
  PRs #209 and #210 were open when this was written and merged later on 10-17 (main `34e5d55`);
  neither path touches their content.

Larry's 10-17 acceptance-first priority says new code waits for *"a fresh implementation
dispatch"*; this repair is prerequisite code for open gates UI2-24/25, so it still needs
that dispatch in writing (path A: to Codex, which the row already does; path B: to
Claude). This plan grants nothing; it is Larry's decision which path runs.

Claude's one active overlap is WS-21 (Claude-owned; CX-16 shares `WorkspaceStore`,
`ConsoleActionCoordinator`, `ConsoleProtocol`, `console_protocol.py`). Under path A,
Claude makes no WS-21 code change on those files while the repair is open. Under path B,
WS-21 and the repair ride separate branches and the repair merges first.

## 1. What the evidence establishes, and what it does not

Three distinct failures were recorded. They do not share one cause.

### 1.1 UI2-24a — stale Recents menu (receipt steps 3 and 6, and "still omitted Atlanta even while pinned")

Established: with two results retained (both bodies open; Atlanta's card Open, Pin,
Compare all work by UUID), the Results ▾ menu kept showing the single row
"1 Weather · Folly Beach · now", on reopen and minutes later, in the rendered menu and in
the accessibility tree.

Code: the menu is `ConsoleActionBar.resultsMenu(icons:)`
(`Console/ConsoleActionBar.swift:156-225`). It computes `let listing = workspace.recents`
and `let count = workspace.results.count` in the view body, then builds a SwiftUI `Menu`
whose content closure captures `listing` by value. `WorkspaceStore.recents`
(`Stores/WorkspaceStore.swift:111`) is a pure function of `results`/`pinnedIDs`/
`unreadIDs`/`activeID`, and `WorkspaceRecents.listing` sorts newest first, so with both
results retained the correct menu is "1 Weather · Atlanta", "2 Weather · Folly Beach".

What is NOT established: where the staleness lives. Two candidates, one check each:

1. The store is right and the rendered `Menu` is stale (SwiftUI `Menu` content on macOS
   not re-evaluated after `results` changes). Check: the button title is
   `"Results · \(count)"` from the same body evaluation. If the title read "Results · 2"
   while the rows showed one entry, the body re-ran and the menu content did not. The
   receipt does not record the title. [untested; the campaign did not capture it]
2. The store only held one result in `results` at that time. Check: the voice inventory
   (`consoleInventoryJSON`, `WorkspaceStore.swift:145`) is built from `results`; the
   `inventory` tool result the Supervisor received for the "number one" turn lists the
   rows. That text is redacted in the run log (see 1.3), so this is settled by a repeat,
   not by the 10-17 logs.

Existing tests cover the listing function and row strings only
(`Tests/MortimerHostTests/CC7a3RecentsTests.swift`: listing, numbering, age, row title,
resolve). No test renders the `Menu` and reads its rows after a second arrival. That gap
is exactly where the failure sits, whichever candidate is true.

### 1.2 UI2-24b — "Open result number one" did not complete (receipt step 5)

Established: correctly transcribed; Atlanta appeared; the app acknowledged
"Console action applied."; the assistant then said it opened the results view and asked
which result.

**Settled from the production log (read 10-17, 23:30 EDT; see §1.4):** the turn ran
exactly one tool call, `console_action {'action': 'view_set', 'args': {'mode':
'results'}}` at 18:05:36. No `inventory` read, no `result_select`, no number was ever
passed to a resolver. Atlanta "appeared" because `view_set results` shows the active
result, and Atlanta was active from its card's Open button in step 4. The assistant's
"opened the results view… which result?" was a literal description of what it did.
[certain]

So UI2-24b is a Supervisor tool-choice failure: "Open result number one" was mapped to
"show the results view", not to `result_select` with target `1` after an inventory
read, which is what the tool description asks for (`jarvis/bot/console_actions.py:49-57`).
The native and backend resolvers were not reached and are not implicated in this
observation.

Code facts that still matter for the repair:

- "Console action applied." is the summary for every `.applied` outcome
  (`App/AppMessageRouter.swift:205`), including `view_set`, so the on-screen notice
  cannot distinguish a view change from a selection. The content-free bot line
  (`supervisor_tool tool=console_action`, `pipeline.py:368`) and the redacted direct-tool
  run log (`sensitive=True`, `pipeline.py:370-373`; `runlog/store.py:197-199`) do not
  record the action either. What does is pipecat's own DEBUG line
  (`pipecat.services.llm_service:_run_function_call`), which production currently
  emits into `logs/bot.launchd.log`. The earlier draft of this document said the action
  could not be recovered; that was wrong, and §1.4 is the correction.
- Number resolution has a reproducible defect on both sides. Backend
  `_resolve_observed_reference` (`jarvis/bot/console_actions.py:115-150`) checks for a
  number before stripping filler words, so only a bare number phrase resolves. Verified
  on main with a two-row snapshot:

  | spoken target | result |
  |---|---|
  | `1`, `number one`, `number 1`, `one` | resolves to number 1 |
  | `result number one`, `open number one`, `open result number one`, `result one`, `the first one` | refused: "That result was not in the observed Recents list" |

  The native resolver mirrors it: `WorkspaceRecents.spokenNumber`
  (`Stores/WorkspaceRecents.swift:180-187`) requires exactly one word after an optional
  "number"/"no", and `fillerWords` (line 157) is applied only on the subject path. The
  Supervisor is told to pass "the Recents number or subject Larry said"
  (`console_actions.py:49-52`). On 10-17 it passed nothing (it never chose a result
  action), so this defect did not fire; it is the next failure in line once the model
  does choose `result_select`, because the phrasing Larry uses is one the resolver
  refuses unless the model trims it.
- The tool contract requires an `inventory` read with `scope='results'` and the
  `inventory_revision` before a spoken number (`console_actions.py:54-57`, enforced at
  248-254). The 10-17 turn made no inventory read (§1.4).

### 1.3 UI2-25 — fresh weather repeat: no reopen, no reference line

Established (receipt): the repeat "What's the weather in Folly Beach, South Carolina?" was
answered with the forecast, in Conversation, with no reopen and no reference line, and
"no new tool call was recorded for that repeat" in the agent-event metadata.

Code facts: the reuse path only exists underneath a tool call. The Supervisor must call
`delegate_task` (analyst); the analyst must call `get_weather`/`get_weather_radar`; the
registry intercepts those calls (`jarvis/skills/registry.py:1153-1198`), asks the native
store through `weather_reuse`, and on a hit the native side reopens the retained result
and writes the reference line (`AppMessageRouter.swift:158-177` →
`ConversationStore.recordCachedResult`). A reuse hit still records the MCP call through
`_finish_invocation`, so "no tool call recorded" means the analyst never ran, which means
the Supervisor did not delegate. The only path that produces a spoken forecast with no
delegation is the Supervisor answering from its own context, where the first Folly Beach
answer already sits. **Confirmed from the production log (§1.4):** between the Atlanta
delegation at 17:59:30 and the `view_set` call at 18:05:36 the bot completed three user
turns and made no tool call of any kind; after 18:05:39 there were further turns and,
again, no tool call. The repeat and both recognition-confounded re-asks were answered
without `delegate_task`. [certain]

Consequence for the repair: CC7a.4's reuse/reference machinery was never exercised on
10-17. It may be correct or not; the campaign is silent on it. The defect in front of it
is a Supervisor tool-choice problem, and the repo's own rule applies: a prompt line
without a mechanical backstop is a wish. The repair needs a backstop, and the choice of
backstop is a design decision (§3.3), not a one-line fix.

### 1.4 Production log, read 10-17 23:30 EDT (Claude, read-only, over the Mac bridge)

The live bot log is `logs/bot.launchd.log` (rotated to `.1` at 23:04; `logs/bot.log`
is a September file). The 10-17 session's Supervisor tool calls, in full:

| time (EDT) | call | note |
|---|---|---|
| 17:58:41 | `delegate_task` → analyst, `subagent_done` 17:58:49, `display_payload tool=get_weather_radar surface=window` | Folly Beach |
| 17:59:30 | `delegate_task` → analyst, `subagent_done` 17:59:39, `display_payload … surface=window` | Atlanta |
| 17:59:40–18:05:35 | three completed user turns (`TURN user_end->llm_done` 1415 / 1260 / 2635 ms), **no tool call** | includes the UI2-25 repeat |
| 18:05:36 | `console_action {'action': 'view_set', 'args': {'mode': 'results'}}` — the only console action of the session | "Open result number one" |
| after 18:05:39 | further turns, **no tool call** | re-asks, pointer checks |

Only tool names and the `view_set` arguments were read; no transcript text was.

## 2. Diagnosis steps (ordered; each names what settles it)

### 2.1 Larry, production, read-only (no code)

1. ~~Which tools ran~~ — done, §1.4. Nothing further to read for UI2-24b/25.
2. Fresh stale-menu discrimination, five minutes, current build: ask for weather in one
   city, then another, open Results ▾, and record (a) the button title ("Results · 2" or
   "Results · 1") and (b) the rows. This settles §1.1 candidate 1 vs 2 and is the
   affected-case reproduction the repair's retest will repeat. Still open.

### 2.2 Codex (or the assigned builder), in a worktree

3. Native rendering test for the menu (new, `CC7a3RecentsMenuRefreshTests.swift`): host
   `ConsoleActionBar` in an `NSHostingView` the way `ConsoleActionBarTests.swift:90-147`
   already does, add a second result to the store after first render, open the menu,
   and read the accessibility children. Expected two numbered rows. A failing test here
   confirms §1.1 candidate 1 and becomes the regression test for slice 3.1.
4. Backend and native resolver tests for the spoken forms in §1.2 (table above), both
   expected to resolve to number 1. These fail on main today (verified for the backend).
5. Run-log/visibility: add one content-free line per console request on the bot side
   (`action=<name> status=<code>`), so the next campaign can answer "which action ran"
   without exposing targets or titles. Codex's #209 OCR work is unaffected.

## 3. Repair slices (bounded; each proven by the test named)

All paths below are inside WS-17's recorded `Scope`. Nothing here touches WS-21's
transfer/screen contract, `ResponseResultRouter`, or any WS-13 path.

| # | Slice | Files | Proof |
|---|---|---|---|
| 3.1 | Recents menu reflects the store after every arrival/pin/unpin/close (the fix depends on §2.1-2 / §2.2-3; if candidate 1, rebuild the `Menu` identity from the listing, e.g. `.id` keyed on the entries' ids+sections, or read `workspace.recents` inside the content closure) | `Console/ConsoleActionBar.swift`, new test file | §2.2-3 test green; §2.1-2 reproduction shows two rows |
| 3.2 | Number resolution tolerates the spoken frame ("open result number one", "the first one"): strip fillers except number words before the number check, on both sides, keeping "one" as a filler for subjects ("the Atlanta one") | `jarvis/bot/console_actions.py` (`_resolve_observed_reference`), `Stores/WorkspaceRecents.swift` (`spokenNumber`), `tests/unit/test_console_actions*.py`, `CC7a3RecentsTests.swift` | §2.2-4 tests green; existing resolve tests unchanged |
| 3.3 | **Supervisor tool choice, measured.** Both 10-17 voice failures are the model picking the wrong tool (§1.4): `view_set` for "open result number one", and no tool at all for a repeated weather question. The repo already has the instrument for this class: the voice-workflow eval (`tests/evals/voice_workflow_eval.py`, cases in `voice_workflow_cases.yaml`, live LLM, supports `prior` history and `require_tool`). Slice: (i) `console_action` description and Supervisor rule state that "open/show result N", "number N", "the first one" are `result_select` after an `inventory` read, never `view_set`; (ii) Supervisor rule: a weather question is always delegated, even when the same place was answered minutes ago, because reuse is decided below the tool; (iii) eval cases with `prior` turns that reproduce 10-17 — two weather results in history then "Open result number one" (require `console_action` with `action=result_select`; the eval gains an `require_action` check for that), and a Folly Beach result in history then the same question again (require `delegate_task`) — each run before and after the prompt change, the before-run recorded as the failing baseline | `jarvis/prompts.py`, `jarvis/bot/console_actions.py` (description text only), `tests/evals/voice_workflow_cases.yaml`, `tests/evals/voice_workflow_eval.py` | `RUN_LIVE=1 python -m tests.evals.voice_workflow_eval`: new cases pass, existing ≥ floor; then UI2-24b/25 live |
| 3.4 | **Mechanical backstop for the weather repeat**, decision for Larry: (a) none beyond 3.3 — accepted as a measured prompt behavior, not a guarantee; (b) after a weather delegation completes, replace the forecast body in the Supervisor's context with a short stub ("shown as the <place> weather card; ask the weather tool again for a repeat"), so a repeat cannot be answered from memory — the only option that makes the reopen mechanical; it changes what the Supervisor remembers within a session and belongs in plan §7.2 as a design amendment | `jarvis/bot/pipeline.py` (context handling), unit tests | Unit test: after a weather delegation, the context holds the stub, not the forecast; eval case from 3.3 passes with the rule removed |
| 3.5 | Diagnosability: one content-free INFO line per console request (`console_action action=… status=…`) so the next campaign does not depend on pipecat DEBUG being on | `jarvis/bot/pipeline.py` | Unit test asserts the line and that no target/title text is in it |

Order: 3.2 and 3.5 first (small, test-pinned, no design question); 3.3 next (the
eval baseline run is itself diagnosis); 3.1 after §2.1-2 settles which candidate; 3.4
only if Larry chooses (b). One PR per slice is cleaner for cross-review, but 3.2+3.5
may share one.

## 4. Non-interference rules while the repair is open

- Codex's #209 (final evidence) and #210 (Tart cleanup) merged on 10-17 (main `34e5d55`);
  the repair branch starts from current main and reopens nothing from them.
- Only the row owner edits the WS-17 block, plan §7.2 dated progress, and
  `docs/roadmap-log/*ws-17*` (C2). Under path A, Claude writes none of these; this
  file is delivered to Larry outside the repo and Codex cites or copies what it uses.
- WS-13 P2's claim still needs Codex's agreement on its WS-17 portions (plan §R.13);
  Claude does not raise it until the repair lands, so Codex has one WS-17 thread at a
  time.
- Production is not deployed from the repair branch; Larry's normal pinned merge →
  `scripts/deploy_main.sh` → receipt sequence applies, and UI2-24/25 are retested on
  the deployed revision, not on a worktree build.

## 5. Retest after deploy (affected cases only)

UI2-24: two cities → Results ▾ shows "1 <newest>", "2 <older>" (and Pinned first when
pinned); "open result number one" / "open number two" / "the Folly Beach one" each open
the named result with no follow-up question; ambiguous subject still asks. UI2-25:
weather A → weather B → weather A within 15 minutes gives two cards, reopens A with the
reference line, no fetch (run log shows the reuse hit, not a provider call); after 15
minutes the refresh replaces the same identity. UI2-22/23 bounded passes from 10-17
remain valid for their recorded cases and are not rerun for documentation.

## 6. Decisions recorded (Larry, 2026-10-17, 23:40 EDT)

1. **Path A: Codex builds.** Claude's involvement ends with this document; Claude
   writes no WS-17 code, row, plan or log edit, and cross-review stays Codex's to
   request if a Claude-authored path is touched (none is planned).
2. **Backstop (b): context stub after a weather delegation** (slice 3.4). Codex
   records it in plan §7.2 as a dated design amendment when claiming the slice.
3. The §2.1-2 reproduction is still open; Larry runs it on the current build before or
   with the first retest.

### Dispatch text (for Larry to send to Codex, and to record in the WS-17 block on main)

> Take the WS-17 UI2-24/25 repair per ROADMAP.md. Diagnosis and slices are in
> `Claude outputs/ws17/WS17_REPAIR_PLAN_2026-10-17.md` (Claude, 10-17): the 10-17
> voice failures are Supervisor tool choice (`view_set` instead of `result_select`;
> no delegation on a repeated weather question), confirmed from `logs/bot.launchd.log.1`;
> the stale Recents menu is a separate, still-undiscriminated defect. Build slices
> 3.2 + 3.5, then 3.3 with the eval baseline, then 3.1, then 3.4 option (b) as a §7.2
> amendment. Larry decided path A and backstop (b) on 10-17.

Row edit (Larry, on GitHub, WS-17 block): `Status` gains "repair slice claimed by
codex 10-17 per the Claude diagnosis"; `Next step` keeps its codex: wording and adds
"slices 3.2/3.5 → 3.3 → 3.1 → 3.4(b)"; `Updated: 10-17`. Codex adds the dated plan
§7.2 entry and `docs/roadmap-log/2026-10-17-ws-17-codex-ui2-24-25-repair-claim.md`
in its first commit.

## 7. What was asked of Larry (answered above; kept for the record)

1. Path A (Codex builds; this is the default the roadmap already states) or path B
   (reassign to Claude). If B, the row edit in §0 before any code.
2. The 3.4 backstop option (a or b). Option (b) changes what the Supervisor remembers
   within a session and should be stated in the Command Console plan §7.2 as a design
   amendment, whoever builds it.
3. The §2.1-2 reproduction (two cities, open Results ▾, note the title and the rows);
   it decides the shape of slice 3.1 and takes minutes on the current build.
