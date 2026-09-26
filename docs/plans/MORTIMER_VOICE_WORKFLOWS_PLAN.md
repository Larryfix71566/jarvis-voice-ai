# Mortimer Voice Workflows — Implementation Plan

**Status:** Phase 1 READY FOR HANDOFF (patch against `main`) · Phases 2–4 BUILT in the VM (§11) · Workflow viewer BUILT; Mac check passed (§12) · #80 privacy fix BUILT in the VM (§13)
**Author:** Claude (Cowork), 2026-09-24 · **Approver:** Larry
**Source review:** "Mortimer Failure Review — Candidate Workflows" (Claude Doc, 2026-09-24)
**Reference package:** `docs/plans/voice_workflows_p1/` (apply script plus every new file, verified; see §7.0)

| Rev | Date | Change |
|---|---|---|
| 1.0 | 2026-09-24 | First issue. Larry's decisions of 2026-09-24 recorded in §3 (D-L1 to D-L4). |
| 1.1 | 2026-09-24 | Larry approved the plan as written (including F1–F4 and D14). §5 steps 1–2 DONE by Claude (Cowork) in the working tree; see Progress below. |
| 1.2 | 2026-09-25 | Larry's decisions: **F1 reversed** — the guard ships in `log` mode (config default and pipeline fallback), switched to `correct` after the live log confirms precision; D17 fixture committed as is; D13 memory-fact archive approved; D14 rule 12 kept until Phase 4. Moved off the production checkout onto `main` 4acb4dc; `give-exact-commands.yaml` deletion restored (a failed deploy's restore had brought the file back); `tests/integration/test_bot_wiring.py` locked processor order updated for the two new processors (the unit suite alone missed it). |
| 1.3 | 2026-09-25 | Larry chose layout **C** (display-window gallery) for a read-only workflow viewer (new §12). He first picked A, then changed to C the same day. Progress rewritten: Phase 1 now lives as a patch against `main` 4acb4dc and production does not run it. New open decision D-V1: the five REVIEW ME draft workflows load as live policy. |
| 1.4 | 2026-09-25 | Larry's decision **D-L5**: when he explicitly asks to be given a command, Mortimer may show it (never a destructive one). D10 gains the explicit-ask path; the handoff workflow, `HANDOFF_ADDENDUM`, the reply guard and the eval follow. Unit 3,131 passed and integration 101 passed in the VM. |
| 1.5 | 2026-09-25 | Larry's direction **D-L6** for Phase 2 location (D4): when online, find the current location; when offline, say it isn't available because there is no connection. Open sub-questions listed under D4 in §11. |
| 1.6 | 2026-09-25 | Larry settled D-L6. IP lookup is used last. Offline, the answer is "not available", with no last-known fix. `user.location.rule` is archived at the end-of-project run. §11 D4 now carries the agreed design. §5 step 8 fixed: the guard ships in `log` mode (1.2), so the deploy check greps `reply_guard=log`. |
| 1.7 | 2026-09-25 | Larry's decision **D-L7** (the Spartanburg loop). `user.location` and `user.location.current` are archived with `user.location.rule` at the end-of-project run. The per-exchange memory extractor no longer learns from Mortimer's own words or records the current location; this is built as the first Phase 2 change. |
| 1.8 | 2026-09-25 | Larry: "implement the plan". **Phase 2 BUILT in the VM** (branch `phase2` on Phase 1 + #86): D3, D4 (Python and MortimerHost), D5, W4, W5, W14, plus D-L7. Python: unit 3,679 passed, integration 132 passed and 4 skipped (live), `tests/ci` 9, sub-agent evals 13, latency probe OK. The Swift is written but not compiled: the VM has no Swift toolchain, and the org egress blocks download.swift.org. It compiles in the end-of-project Mac run. |
| 1.9 | 2026-09-25 | Phase 2's Swift compiled and passed on the Mac (JarvisKit 204 tests; MortimerHost 261, 3 skipped, 0 failures; Python 3,832 passed, 4 skipped). Larry's Phase 3 decisions: **W8 option A** (a proposal pull request plus one approval) and **self-rebuild option B** (the deploy stays his one command). **Phase 3 BUILT in the VM** (branch `phase3` on Phase 2). One change from the approved wording: the apply command pushes a branch of Larry's own, not Mortimer's, because CI gate 1 fails a self-edit branch that touches a human-only file (§11). W6, W7 and D6 needed no code (§11). An adversarial review found that the first apply script trusted the patch text; fixed and pinned (§11). Open: whether the script shows the diff before pushing. Unit 3,769 passed, integration 132 passed and 4 skipped. |
| 1.10 | 2026-09-25 | Larry: "proceed with recommendations". The apply command's own branch is confirmed. The script now shows the exact diff of every human-only file and pushes nothing until he types y. `DEPLOY-MAIN.sh` moves into the repo at the end run. Unit 3,774 passed, integration 132 passed and 4 skipped; 30 apply-script tests. |
| 1.11 | 2026-09-25 | Larry: "proceed" (Phase 4). Evidence gathered for every item (§11). **Built in the VM** (branch `phase4` on Phase 3): W11 topic resolution, W9 expiry of the 21 dead actions, W3 routing to `system_status`. **Already fixed, no code:** D1 (#78, 17 Sep), D8 (f4a3e5b, 30 Aug), two of D11's four signatures (71e449f, #84). **Open for Larry:** W10's rule details, W12's design, W9 for app builds, and replaying D1's 28 lost extractions. Unit 3,785 passed, integration 132 passed and 4 skipped. |
| 1.12 | 2026-09-25 | Larry's Phase 4 decisions: **W10 age-aware memory**, **W12 option B**, **W9 one approval** at `app_build_start`, **D1 replay** once at the end run. All four **built in the VM** (branch `phase4`, second commit; §11). Rule 12's timer clause retires with W12 (D14, §10). An adversarial review found nine defects in the first cut; each now has a test that fails on it. **Correction:** the W10 replay shown with the choice (no_lookups archived, clarity and research_display both kept) is not what the built rule is sure to do (§11 W10). **New, for Larry:** D1b, a pre-existing write lock held across the sweep's model calls. Unit 3,851 passed, integration 135 passed and 4 skipped. |
| 1.13 | 2026-09-25 | Larry: "proceed" on the three recommendations. **D1b built:** the sweep and capacity enforcement commit before every model call; two tests reproduce the lock without the change. `user.style.status_interval` joins `user.style.status` on the end-run archive list (the command was tested on a production copy). **Workflow viewer handoff plan written** (`MORTIMER_WORKFLOW_VIEWER_PLAN.md`), with D-V1 (drafts), D-V2 (usage counts) and the new D-V3 (six memories archived as workflows whose files do not exist) open. Unit 3,853 passed, integration 135 passed and 4 skipped. |
| 1.14 | 2026-09-25 | Larry chose the recommended option for **D-V1** (`draft: true`), **D-V2** (no usage counts) and **D-V3** (restore the four lost memories). **Workflow viewer built in the VM** (branch `viewer`, patch `viewer-on-phase4.patch`, the sixth in the Mac check). The Python half is tested: unit 3,862 passed, integration 135 passed and 4 skipped. The Swift half is not compiled, because the VM has no toolchain. A second agent reviewed it and found four defects, all fixed with tests. Found: voice entry needs `JARVIS_COMMAND_CONSOLE_ENABLED`, which production doesn't set. D-V3's restore would push the project tier to 10 of its cap of 8. |
| 1.15 | 2026-09-25 | Mac check run 2 passed at 18:06: JarvisKit 206, MortimerHost 275 (3 skipped, 0 failures), Python 4,018 passed and 4 skipped; all six patches' trees matched. Larry's landing decisions: **one PR with a merge commit**, **console on** at the end run (`JARVIS_COMMAND_CONSOLE_ENABLED=true`), **#80 fixed in this landing**, **#86's files merged as is**. **#80 privacy fix built in the VM** (branch `privacy`, patch `privacy-on-viewer.patch`, the seventh in the Mac check; §13). Unit 3,866 passed, integration 135 passed and 4 skipped. |

## Progress (read first)

- **Phase 1 is a patch, not a working tree.** `closure-checks/phase1-voice-workflows.patch` (23 files) applies to `main` 4acb4dc. The earlier working-tree copy in `~/jarvis-voice-ai-clean` was taken off production on 2026-09-25.
- **Production does not run Phase 1.** It is at 4acb4dc, and `jarvis/voice_workflows.py` and `jarvis/bot/voice_guidance.py` are absent. A restart loads nothing new.
- **Deploy hazard.** Production still holds untracked leftovers from the working-tree copy: this plan, `docs/plans/voice_workflows_p1/`, `tests/evals/voice_workflow_*`, `tests/fixtures/voice_failures.yaml`, and `tests/unit/test_{orchestrator_voice,show_commands_gate}.py`. They must be moved aside before Phase 1 deploys, because the checkout refuses to overwrite untracked files.
- **Verified in the Linux VM** (Python 3.12, pipecat-ai 1.4.0): unit suite 3,109 passed, integration suite 101 passed. `test_registry.py` is deselected because it can't start MCP servers in the VM, on `main` too.
- **Not yet done. This is the end-of-project run (Larry, Mac)**, per `closure-checks/PHASES-END-CHECKLIST.md`:
  - the Mac suites;
  - the evals (they need the vault);
  - archiving the memory fact;
  - commit, PR, CI and merge;
  - deploy;
  - the live check.
  Nothing merges or deploys before all phases are built.

---

## §0 Binding constraints for the implementing model

- **C1. Do exactly §5, in order.** Every design decision is made in §3. If a step seems to need a choice, the choice is missing from this plan: stop and report. Do not pick one.
- **C2. Apply the change with the script, not by hand.** `docs/plans/voice_workflows_p1/apply_phase1.py` applies every edit, anchored on exact text. It checks all anchors before writing anything, so any mismatch aborts with nothing changed.
- **C3. The tree is moving.** More than 40 core files changed between 2026-09-20 and this plan, including `jarvis/subscription.py` on 2026-09-24. If the dry run prints `ABORT`, stop and send Larry the ABORT line. Never edit an anchor, and never hand-apply part of the patch.
- **C4. No new model calls except one.** The only new LLM call is the reply guard's single regeneration, made by the Supervisor's own model (`claude-haiku-4-5`, verified in `.env` on 2026-09-24). No agent's model changes (model-floor policy).
- **C5. Scope is §2 only.** Files outside §4 are not touched. `docs/plans/voice_workflows_p1/` is reference material: copy from it, never edit it.
- **C6. Secrets stay in the vault.** Nothing in this plan reads or writes a key.
- **C7. The implementer does not run git.** Larry commits (§5 step 9).

---

## §1 Background (every number verified 2026-09-24 against a copy of `data/jarvis.db` and `logs/`)

**What went wrong.** From 2026-08-12 to 2026-09-24 Mortimer sent 2,013 replies. In 93 of them he refused, handed work to Larry, or failed without explaining why. Those 93 replies are pinned with their IDs in `tests/fixtures/voice_failures.yaml` (87 KB, generated from the database copy). The three biggest groups:

| Group | Replies | Last seen | Example |
|---|---|---|---|
| Handed work to Larry (commands, clipboard round trips, manual edits) | 25 | Sep 23 | "The developer can't execute curl directly. You'll need to run that command locally…" |
| Said "couldn't" with no cause given | 17 | Aug 30 | "Developer couldn't complete that investigation." |
| Refused without checking what it could do | 14 | Sep 24 | "I don't have a tool to detect device location from your connection." |

**Why the existing rules did not hold.** `SUPERVISOR_PROMPT` already forbids all three:

- Golden Rule 3: "never claim you lack one the specialists list covers".
- Rule 8: the Specialists list is the source of truth for what Mortimer can do.
- Rule 10: no "I can't" hedges.

The failures continued through Sep 24 anyway. Four facts in the code explain it:

1. **Workflows never reach the voice agent.** `config/workflows/*.yaml` is matched only inside specialist runs (`jarvis/agents/base.py`, `match_workflow(self.name, task)`). The Supervisor never sees a workflow.
2. **Three places tell Mortimer to hand work off:**
   - `config/workflows/give-exact-commands.yaml` says to "give the exact command to run".
   - `HANDOFF_ADDENDUM` says to call show_commands whenever "you need a command run that you cannot run yourself".
   - `AGENT_DISCIPLINE` tells every specialist: "if something is beyond your tools … write NEEDS-INPUT: then the exact command".
   - The live memory fact `user.style.troubleshooting` ("Willing to run local commands and handle copy-paste workflows") is also injected into every Supervisor prompt with "honor them".
3. **The trigger usually isn't in Larry's words.** The failure replies often follow "Yes.", "Thoughts?" or "Try another way." A regex on Larry's turn matches only 32 of the 93 (fixture field `user_trigger`). The real signal is in Mortimer's own reply, or in the specialist's result.
4. **Code backstops work where prompt rules failed.** `jarvis/bot/late_result.py` records that "two prompt-only rules failed on this same model in this same session", and that a note injected at the right moment is followed literally by Haiku (the 09-03 repeat incident).

**What a reply-level check would catch** (fixture, pinned):

| Measure | Value |
|---|---|
| Replies the detector flags | 75 of 2,013 (3.7 per 100) |
| Failure replies caught | 62 of 93 |
| Accepted false positives (legitimate replies it still flags) | 8, 0.4% of all replies; each costs one extra generation, then goes through |
| Flags on the 96-reply negative sample | 0 |
| Specialist results that carry a signal (61 logged) | 28 failed, 29 NEEDS-INPUT, 10 stated a limitation |

**Latency.** pipecat 1.4's `TTSService` defaults to `TextAggregationMode.SENTENCE` when no mode is given, and `pipeline.py` passes none (`ElevenLabsTTSService(... text_filters=[MarkdownTextFilter()])`). TTS therefore already waits for each sentence to end, and a guard that releases text one sentence at a time adds no delay by construction. The live measurement is §7 T4. Pre-plan `TURN user_end->first_audio`: n=268, p50 969 ms, p90 2,167 ms.

---

## §2 Scope (Phase 1)

**In:**

- A voice-workflow layer: workflow files marked `agents: [supervisor]`, reaching the Supervisor through three hooks — Larry's turn, a specialist's result, and Mortimer's own reply.
- Three voice workflows: W2 do-it-don't-hand-off, W1 check-before-can't, W13 explain-failure.
- A reply guard with off, log and correct modes.
- A capability-gap log.
- A last-resort gate on show_commands, with a destructive-command block (D10 of the review).
- Retiring the hand-off instructions: give-exact-commands.yaml, the first paragraph of `HANDOFF_ADDENDUM`, the NEEDS-INPUT clause in `AGENT_DISCIPLINE`, and the memory fact `user.style.troubleshooting`.
- Orchestrator parity, so both evals score what ships.
- The replay fixture, unit tests, a live eval, and an audit script.

**Out:**

- Every Phase 2–4 item (§11).
- Any new MCP tool.
- Any change to a specialist's model or tool list.
- Swift/UI changes. None are needed: everything is backend.
- Rule 12 of `SUPERVISOR_PROMPT` (D14).
- The existing specialist workflows. Only give-exact-commands is removed.

---

## §3 Decisions

### Larry's decisions (2026-09-24)

- **D-L1.** Workflows must reach the voice agent. When a task belongs to a specialist, delegating is the first step. Larry asked for a better path to be suggested if one exists; that is D6.
- **D-L2.** Retire the hand-off rules. Hand off only as a last resort, for a step only a human can do, with everything prepared so Larry only approves.
- **D-L3.** Phasing is behavior first: Phase 1 = replay test + W2, W13, W1 + the unsafe-advice guard. Phases 2–4 are listed in §11.
- **D-L4.** Memory review settles everything automatically, without leaving conflicting facts (Phase 4).
- **D-L7 (2026-09-25, Phase 2).** The Spartanburg loop is closed on both sides:
  - **Data.** The identity memories `user.location` ("User is located in Spartanburg") and `user.location.current` ("Spartanburg, SC") are archived with `became = "superseded:MORTIMER_VOICE_WORKFLOWS_PLAN.md D-L7"`, alongside `user.location.rule` (D-L6).
  - **Code.** `jarvis/memory_extraction.py` rejects a fact candidate whose words appear in Mortimer's reply but not in the user's line (`echo_of_reply`), and any `user.location` / `user.location.current` candidate (`current_location`). Both prompts gain the matching rules. The kill switch is `JARVIS_MEMORY_ECHO_GUARD=false`.
  - **Evidence.** 8 of the 10 logged rewrites of `user.location` came from greetings where only Mortimer said "Spartanburg". Replayed over the 150 logged extractions with a known source turn, the guard rejects 104 (83 `user.name` greeting refreshes, all 11 `user.location` rows, 3 `user.location.timezone`, 7 facts built from Mortimer's own reports) and admits 46.
- **D-L6 (2026-09-25, Phase 2).** When the Mac is online, Mortimer finds the current location. When it is offline, the answer is that the location isn't available because there is no connection. Larry noted that today there is no Mortimer to ask offline: speech-to-text (Deepgram), the model (`OPENAI_BASE_URL` is remote) and text-to-speech (ElevenLabs) all need the internet. So the offline answer matters once a local model runs on the planned Mac mini. Settled the same day: IP lookup is used **last**, and spoken as approximate. Offline, the answer is "not available", with **no** last-known fix. The Mortimer memory `user.location.rule` (20 Aug: Spartanburg as the last-resort answer) is archived with `became = "superseded:MORTIMER_VOICE_WORKFLOWS_PLAN.md D-L6"`.
- **D-L5 (2026-09-25).** When Larry explicitly asks to be given a command, Mortimer may show it with `show_commands`. It never shows a destructive command, and never speaks one aloud. This refines D-L2 and was chosen over keeping D-L2 strict when Codex's PR #86 (T1.3) raised the same question. The detector is `is_explicit_command_ask` in `jarvis/voice_workflows.py`. On the production log it matches exactly Larry's three real asks (user turns 764, 831, 833) out of 1,525 user turns, and none of the 93 logged failures.

### Plan decisions

- **D1. Voice workflows are ordinary workflow files.** They live in `config/workflows/` with `agents: [supervisor]`. The existing specialist matcher skips any workflow whose `agents` list lacks the caller, so these never reach a specialist (pinned by `test_voice_workflows_never_reach_specialists`). *Why:* one authored layer, one loader, one kill switch (`JARVIS_WORKFLOWS_ENABLED` disables both).
- **D2. Three hooks share one guidance text.** Each hook renders the matched workflow's `Workflow.as_prompt()`, prefixed with `[system] `:
  - `user`: before generation, on a new user turn.
  - `result`: appended to a `delegate_task` result.
  - `reply`: inside the guard's correction note.

  *Why:* the fixture shows each hook alone misses most failures: user 32/93, reply 62/93.
- **D3. Triggers are regex and named kinds, not token overlap.**
  - `triggers.user` holds regexes run against Larry's turn text.
  - `triggers.result` holds kinds from `failed`, `needs_input`, `missing_tool`, `limitation`.
  - `triggers.reply` holds kinds from `refusal`, `handoff`.

  *Why:* the voice turns are short ("Yes.", "Thoughts?"). Regexes are explicit and are pinned against the corpus.
- **D4. One guidance note per hook.** The lowest `priority` wins, with ties broken by name. W2 = 10, W1 = 20, W13 = 30.
- **D5. Notes are user-role `[system]` messages, cleared at the next turn.** This is the house channel (late results, the greeting, reminders). At the next real user turn every note is rewritten in place to `TOMBSTONE`, the same in-place rewrite `late_result.py` uses. A "real user turn" is the last message in the context with role `user`, string content not starting `[system]`, and not the same object as the last turn's message. Tool re-runs within a turn therefore never re-inject.
- **D6. The reply guard is the backstop (the better path Larry asked for).**
  - **Placement and release.** It sits between the LLM and the TranscriptLogger and releases text one sentence at a time (split on `[.!?]` followed by whitespace).
  - **Correct mode.** At the first violating sentence it drops that sentence and the rest of the response. When the response ends it asks for one regeneration with a correction note.
  - **When it does nothing:**
    - the response contains a function call — the refusal is dropped and the delegation stands;
    - Larry's turn asked about capabilities;
    - a correction was already made this turn — the sentence is spoken and logged as a capability gap.
  - **Modes:** `off` (identical frames), `log` (speak everything, log only), `correct` (default).
- **D7. The correction note text is fixed:** `voice_workflows.CORRECTION_TEMPLATE`, followed by the matched reply-hook workflow. It quotes the dropped sentence, tells Mortimer to delegate or give the sanctioned missing-tool sentence, and forbids asking Larry to run, copy or edit anything.
- **D8. Capability gaps go to a log.** `logs/capability_gaps.jsonl` gets one JSON object per line: `{ts, session_id, source, kind, agent, user_text, text, workflow}`. Text is replaced by `[sensitive]` on a sensitive turn. Evals redirect it with `JARVIS_CAPABILITY_GAP_LOG`. This log feeds the Phase 2–4 ordering (§11).
- **D9. The result hook wraps the delegate handler.** It uses `wrap_delegate_handler`, in both `pipeline.py` and the Orchestrator. It stamps `runtime.handoff_gate["needs_input_at"]`, logs `missing_tool`/`limitation` gaps, and appends guidance. A handler exception propagates unchanged.
- **D10. show_commands is the last resort.** With a gate dict, the checks run in this order:
  1. Refuse any destructive command (`DESTRUCTIVE_COMMAND_RE`: `git reset --hard`, `git clean -f`, `git checkout -- …`, `git restore` without `--staged`, force-push, `git branch -D`, any `rm`, `sudo`, `dd if=`, `mkfs`, `kill -9`, `killall`, `pkill`).
  2. Allow if Larry explicitly asked for a command within 600 s (D-L5). `VoiceWorkflowInjector` stamps `explicit_ask_at` on the gate. Read-only checks are allowed on this path because he asked.
  3. Refuse unless a NEEDS-INPUT arrived within 600 s.
  4. Refuse read-only checks (`READ_ONLY_COMMAND_RE`: curl, cat, ls, git status/log/diff/branch/show, etc.).

  On a turn with an explicit ask, the reply guard (pipeline and Orchestrator) does not treat a hand-off sentence as a violation. Refusals are still corrected.

  Each refusal is a fixed sentence returned to the model. Without a gate (tests, the CLI) nothing changes.
- **D11. `AGENT_DISCIPLINE` NEEDS-INPUT clause becomes (543 of the 550 allowed characters):** "If a step is beyond your tools, write MISSING TOOL: and the tool that would do it; write NEEDS-INPUT: only for a step only Larry can do." `HANDOFF_MARKER` is unchanged, so the continuation logic in `delegate.py` is untouched.
- **D12. The first paragraph of `HANDOFF_ADDENDUM` is rewritten as last resort** (exact text in `apply_phase1.py`, `E_HANDOFF`). The paragraph about continuations and the zsh warning are unchanged; `test_prompts.py` pins "zsh", "continuation" and "not a retry".
- **D13. Two hand-off sources are retired:**
  - Delete `config/workflows/give-exact-commands.yaml`.
  - Archive memory fact `user.style.troubleshooting` with `became = "superseded:MORTIMER_VOICE_WORKFLOWS_PLAN.md D13"`. `archive_fact` keeps the row, so this is reversible.
- **D14. Rule 12 stays as written in Phase 1.** Larry chose to retire it; this is a structured disagreement, see §10.
- **D15. The Orchestrator runs the same hooks.** It uses the whole reply rather than sentences, and the rejected reply never enters history. The flags are read with `getattr(..., False/"off")`, so bare test settings keep pre-plan behaviour; `load_settings()` defaults are on. The only intended difference from the pipeline: the pipeline speaks sentences before the violating one, the Orchestrator drops the whole reply.
- **D16. Settings:**
  - `jarvis_voice_workflows_enabled: bool = True` (`JARVIS_VOICE_WORKFLOWS_ENABLED`).
  - `jarvis_reply_guard_mode: str = "correct"` (`JARVIS_REPLY_GUARD_MODE`). Unknown values run as `log`, never `off`.
  - `pipeline.py` reads both with `getattr` and the production defaults, because tests build it from `SimpleNamespace` settings.
- **D17. The fixture is committed.** `tests/fixtures/voice_failures.yaml` contains Larry's own conversation text: 93 failures, 8 accepted false positives, 96 negatives, 61 specialist results. The repo is private. Larry reviews the file before committing (§5 step 9).

### Decisions made for Larry — check these before handoff

| # | What I decided | Why | To change |
|---|---|---|---|
| F1 | ~~The guard ships in `correct` mode, not `log`~~ — reversed by Larry 2026-09-25: ships in `log` | Precision on the corpus is high: 8 legitimate replies flagged in 2,013, each costing one extra generation | `JARVIS_REPLY_GUARD_MODE=log` in `.env` |
| F2 | Rule 12 kept until Phase 4 | §10 | Say so; it becomes a one-line edit |
| F3 | W13 included, although its 17 replies all predate Aug 31 | It is a YAML file plus the result hook; the eval confirms or clears it at no build cost | Delete `voice-explain-failure.yaml` before applying |
| F4 | `open` and read-only git commands count as "read-only checks" in the show_commands gate | The logged hand-offs a tool should have done were read-only probes: curl (turns 2157–2166, 3475, 3478), `ls` (2772), `git branch` (718) | Edit `READ_ONLY_COMMAND_RE` and its test together |

---

## §4 File manifest

New (copied verbatim from `docs/plans/voice_workflows_p1/files/` by the apply script):

| Path | What |
|---|---|
| `jarvis/voice_workflows.py` | Detectors, matcher, guidance, gap log, result wrapper (pure, never raises) |
| `jarvis/bot/voice_guidance.py` | `VoiceTurnState`, `VoiceWorkflowInjector`, `ReplyGuard` |
| `config/workflows/voice-do-it-dont-hand-off.yaml` | W2, priority 10 |
| `config/workflows/voice-check-before-cant.yaml` | W1, priority 20 |
| `config/workflows/voice-explain-failure.yaml` | W13, priority 30 |
| `tests/unit/test_voice_workflows.py` | Pinned detector and matcher tests (379 cases) |
| `tests/unit/test_voice_guidance.py` | Frame-level injector and guard tests |
| `tests/unit/test_show_commands_gate.py` | Gate plus adversarial commands |
| `tests/unit/test_orchestrator_voice.py` | Orchestrator parity |
| `tests/evals/voice_workflow_eval.py`, `tests/evals/voice_workflow_cases.yaml` | Live eval, 20 cases |
| `scripts/voice_guard_audit.py` | Read-only audit for T4/T5 |

Already in the repo: `tests/fixtures/voice_failures.yaml` (written by the plan author, 2026-09-24).

Modified by anchored edit:

| Path | Edit |
|---|---|
| `jarvis/workflows.py` | `Workflow.triggers`, `Workflow.priority`, `_coerce_triggers`, `_coerce_priority` |
| `jarvis/config.py` | 2 settings (D16) |
| `jarvis/prompts.py` | `AGENT_DISCIPLINE` (D11) plus a comment line; `HANDOFF_ADDENDUM` first paragraph (D12) |
| `jarvis/bot/handoff_tools.py` | Gate constants, `command_gate_refusal`, `gate=` kwarg, schema description (D10) |
| `jarvis/agents/supervisor.py` | Imports; voice state in `__init__`; `chat()` hooks; tool loop moved verbatim into `_tool_loop()` (D15) |
| `jarvis/bot/pipeline.py` | Docstring, imports, `Runtime.voice_state`, `Runtime.handoff_gate`, delegate wrap, show_commands gate, correction closure, two processors in `pipeline_steps` |
| `tests/unit/test_prompts.py` | The handoff-marker test asserts `MISSING TOOL:` instead of the retired wording |

Deleted: `config/workflows/give-exact-commands.yaml`.

---

## §5 Steps

The Mac, repo root, `.venv` active.

0. **Preconditions.**
   - Larry names the base branch; create `feat/voice-workflows-p1` from it.
   - Record the baseline: `.venv/bin/python -m pytest tests/unit -q -p no:cacheprovider -rf 2>&1 | grep -E "^(FAILED|ERROR)" | sort > /tmp/p1_baseline_failures.txt`.
   - Back up the database: `.venv/bin/python scripts/backup_db.py`.
1. **Dry run:** `.venv/bin/python docs/plans/voice_workflows_p1/apply_phase1.py`. Expected: 12 new files, 7 modified, 1 deleted, and "Dry run only". Any `ABORT` → stop (C3).
2. **Apply:** `.venv/bin/python docs/plans/voice_workflows_p1/apply_phase1.py --write`.
3. **Compile:** `.venv/bin/python -m py_compile jarvis/voice_workflows.py jarvis/bot/voice_guidance.py jarvis/agents/supervisor.py jarvis/bot/pipeline.py jarvis/bot/handoff_tools.py jarvis/prompts.py jarvis/config.py jarvis/workflows.py`.
4. **Unit suite:** `.venv/bin/python -m pytest tests/unit -q -p no:cacheprovider -rf 2>&1 | grep -E "^(FAILED|ERROR)" | sort > /tmp/p1_after_failures.txt`, then `comm -13 /tmp/p1_baseline_failures.txt /tmp/p1_after_failures.txt`.
   - Empty output → continue.
   - Any line → stop and report it. Do not fix other tests.
5. **Offline audit:** `.venv/bin/python scripts/voice_guard_audit.py --since 2026-09-01`. It must run without error and print the three sections; the numbers depend on the live database.
6. **Evals** (real LLM calls; §7 T3 has the pass rules):
   - `RUN_LIVE=1 JARVIS_VOICE_WORKFLOWS_ENABLED=false JARVIS_REPLY_GUARD_MODE=off .venv/bin/python -m tests.evals.routing_eval > /tmp/route_off.txt`
   - `RUN_LIVE=1 .venv/bin/python -m tests.evals.routing_eval > /tmp/route_on.txt`
   - `RUN_LIVE=1 JARVIS_VOICE_WORKFLOWS_ENABLED=false JARVIS_REPLY_GUARD_MODE=off .venv/bin/python -m tests.evals.voice_workflow_eval > /tmp/voice_off.txt`
   - `RUN_LIVE=1 .venv/bin/python -m tests.evals.voice_workflow_eval > /tmp/voice_on.txt`
7. **Archive the fact (D13):** `.venv/bin/python -c "from jarvis.db import get_conn; from jarvis.memory import archive_fact; c=get_conn(); r=archive_fact(c, 'user.style.troubleshooting', 'superseded:MORTIMER_VOICE_WORKFLOWS_PLAN.md D13'); c.commit(); print('archived' if r else 'not live')"`. Either printed word is acceptable.
8. **Deploy:** `./scripts/mortimer.sh start`. Under launchd this kickstarts all five services and rotates `logs/*.launchd.log`, so the new `bot.launchd.log` holds only post-deploy lines. Confirm with `grep "voice_workflows enabled=True reply_guard=log" logs/bot.launchd.log` after the first client connects.
9. **Hand back to Larry** the four `/tmp/*.txt` eval outputs, the step 4 `comm` output, and the list of changed files. Larry reviews `tests/fixtures/voice_failures.yaml` (D17) and commits.
10. **Live acceptance:** §7 T4, with Larry.

---

## §6 Tuning knobs (where each lives)

| Knob | Where | Rule |
|---|---|---|
| Refusal/hand-off/allowed/limitation regexes | `jarvis/voice_workflows.py` | Pinned by the fixture; edit only together with a fixture update Larry approves |
| User-turn triggers, priorities, guidance text | `config/workflows/voice-*.yaml` | `user` patterns pinned by the fixture's `user_triggers` |
| Guard mode, voice workflows on/off | `.env` (`JARVIS_REPLY_GUARD_MODE`, `JARVIS_VOICE_WORKFLOWS_ENABLED`) | — |
| NEEDS-INPUT window, destructive and read-only command lists | `jarvis/bot/handoff_tools.py` | Each list edit needs a matching test in `test_show_commands_gate.py` |

Nothing is tuned inline anywhere else.

---

## §7 Verification

**T0 — verified by the plan author before handoff** (2026-09-24, on a copy of the tree taken at 02:20 UTC, Python 3.12.14, pipecat-ai 1.4.0):

- The dry run found every anchor exactly once.
- After `--write`, the whole unit suite (158 test files, 3,108 tests) showed the same failure set as before: 23 failures in both runs, all from files the copy left out (docs/, macos/), 0 new.
- The new tests pass: 379 detector and matcher cases, the frame-level guard and injector tests, 38 gate cases, and 11 Orchestrator parity cases.
- The audit script ran against the database copy: 26 of 752 replies since Sep 1 flagged (3.5 per 100).

The Mac run in §5 step 4 is the one that counts.

**T1 — unit (deterministic).** §5 step 4: zero new failures.

**T2 — corpus replay (deterministic).** This is inside T1. `test_voice_workflows.py` asserts the pinned value for every fixture row: guard fires on the 62 failure replies marked `fire`, stays silent on the 31 marked `miss` and all 96 negatives, gives the right user trigger for each row, and the right result kinds for all 61 specialist results.

**T3 — live evals.** Pass rules:

- *Routing, no regressions:* a case marked `ok` in `/tmp/route_off.txt` that shows `MISS` in `/tmp/route_on.txt` fails T3. Stop and report both lines. Aggregate accuracy is recorded, not gated.
- *Voice workflows, ≥ 18/20:* `/tmp/voice_on.txt` must show at least 18 of 20. `/tmp/voice_off.txt` is the recorded baseline, not gated. Below 18 → stop and report the FAIL lines.

**T4 — live acceptance (Larry, one session, after step 8).** Larry says these eight, in order, waiting for each answer:

1. "Can you see my location?"
2. "Check which model keys are actually loaded."
3. "No, you do that for me."
4. "Why did that fail?"
5. "Give me tonight's baseball games."
6. "Check progress every thirty seconds."
7. "Give me a rundown of your capabilities."
8. "What's the weather in Alpharetta?"

Then the implementer runs `.venv/bin/python scripts/voice_guard_audit.py --since <today> --turn-lines-after 0`. Pass requires all of:

- (a) "spoken refusal/hand-off" lists only the sanctioned missing-tool sentence and replies to #7;
- (b) no show_commands card appeared, unless a specialist wrote NEEDS-INPUT for a human-only step;
- (c) every "isn't something I have a tool for yet" reply has a matching `capability_gaps.jsonl` line;
- (d) `user_end->first_audio` p50 ≤ 1,119 ms (the pre-plan 969 ms + 150 ms).

If (d) fails: set `JARVIS_REPLY_GUARD_MODE=log`, restart, and report. The guard is the only new component on the speaking path.

**T5 — seven-day check.** On day 7 run `scripts/voice_guard_audit.py --since <deploy date>`. Recorded, not gated:

- spoken violations per 100 replies (pre-plan 3.7);
- guard actions by kind;
- capability gaps by kind and agent.

The gap counts decide the order of Phases 2–4 (§11).

---

## §8 Rollback

| Level | How | Effect |
|---|---|---|
| Guard only | `JARVIS_REPLY_GUARD_MODE=off` in `.env`, then `./scripts/mortimer.sh start` | The guard passes the same frame objects through (pinned by `test_off_mode_passes_the_same_frame_objects`) |
| All voice workflows | Also `JARVIS_VOICE_WORKFLOWS_ENABLED=false` | No notes; the result hook still stamps the show_commands gate |
| Everything | Larry reverts the Phase 1 commit, and runs `UPDATE memories SET archived_at=NULL, became=NULL WHERE key='user.style.troubleshooting'` if he wants the fact back | Pre-plan state |

---

## §9 Risks

| Risk | Likelihood | Guard |
|---|---|---|
| The tree moved under the anchors | High (C3) | The apply script aborts with nothing written |
| The regeneration adds a second spoken reply after a partial first sentence | Occurs whenever the guard cuts a reply mid-way | The correction note tells Mortimer to answer the request again; T4 checks it |
| A legitimate refusal (e.g. Bluetooth routing) costs one extra generation | 8 in 2,013 replies on the corpus | One retry per turn, then spoken and logged |
| Guidance injected on unrelated turns (W1 regex matches 112 of 1,522 user turns) | Certain, low cost | A ~120-token note telling Mortimer to delegate rather than refuse; cleared next turn |
| show_commands refuses a step Larry truly must do | Low | Allowed whenever a NEEDS-INPUT arrived within 10 minutes and the command is neither read-only nor destructive |
| Codex's in-flight work on `subscription.py` | Unknown | Not touched by this plan |

---

## §10 Structured disagreement: rule 12 (D14)

**Larry's decision:** retire rule 12 ("There is no wait or timer capability…").

**Done in Phase 4 (rev 1.12), with W12.** The clause now reads "Only a tool can wait: never say you are waiting or will check back unless a tool call in this turn actually set that up." That holds with or without the timing tools registered; the tools and their prompt addenda ship together (§11 W12).

- **Reason to wait.** Today that sentence is true: there is no timer tool until W12 ships in Phase 4. Removing it now makes Mortimer claim a capability it lacks, which breaks Golden Rule 3.
- **Alternative.** Keep it through Phase 3. The reply guard already turns "I can't do that" into the sanctioned missing-tool sentence and logs the gap. Retire the rule in the same change that ships W12.
- **Downside of my approach.** Until Phase 4, "check every thirty seconds" still gets "that isn't something I have a tool for yet", though now with an offer to add it and a logged gap instead of a bare refusal.

**Approval:** Phase 1 handoff needs Larry's yes on this plan and on F1–F4.

---

## §11 Phases 2–4 (all built in the VM)

Each phase gets its own handoff-ready plan, written after Phase 1's T5 audit. Items are ordered by gap-log count; ties go to this plan's evidence counts.

**Phase 2: BUILT in the VM, 2026-09-25 (rev 1.8).** Branch `phase2` on Phase 1 + #86; patch `closure-checks/phase2-on-pr86.patch`. Everything below is untested live until the end-of-project run.

- **D-L7 memory echo guard.** See §3 D-L7.
- **D3 screen capture: root cause found.** Launchd supervision (17cee9e, 2026-09-04) started the services with `PATH=/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin`, and `screencapture` and `system_profiler` live in `/usr/sbin`. That is the 4 of 4 failures on 2026-09-08/09. #79 (2026-09-17) added `/usr/sbin:/sbin` to the template, but an installed plist is only rewritten when `launchd_gen` runs. `mcp_servers/mcp_screen/logic.py` now resolves both tools itself (`macos_tool`: PATH, then `/usr/sbin`, `/usr/bin`), and a test pins the template's PATH. No `screen_view` call is in the retained logs after 09-09.
- **D4 location (D-L6).** Built as designed, with one change of mechanism.
  - **The request.** The fix is requested on this session's own data channel, not posted to the sidecar and read back. The bot sends `location/request` only to a client that sent `location/hello`. MortimerHost answers with `location/result` (lat, lon, `accuracy_m`, `age_s`, label, or `error: denied|unavailable`). So the answer always comes from the device in this conversation, and an old or web client costs no wait.
  - **The code.** `jarvis/bot/device_location.py` holds the order (device → IP → "not available" + reason), the 10-minute freshness limit and the 1 km "approximately" threshold. It also builds the spoken sentence in code.
  - **Protected turns.** On a protected turn the IP step is skipped (device only). This replaces "add `location` to `EXTERNAL_TOPICS`", which would have refused the local device path as well.
  - **IP lookup.** `ambient_weather.ip_location` reports `offline` versus `lookup_failed`; the weather resolver is unchanged.
  - **Swift.** `JarvisKit/LocationProtocol.swift`, `MortimerHost/App/DeviceLocator.swift` (CoreLocation at 100 m, one `requestLocation()` per request, reverse-geocoded "City, ST" label; the fix is also POSTed to `/api/location` for the weather chip), and the usage strings in `bundle.sh` and the templates.
  - **`voice-where-am-i`** (supervisor, priority 15) sends location questions to `system_status`. Its trigger matches 8 of the 1,525 logged user turns, all about location. The fixture's pinned trigger for failures 126, 573, 2921 and 3535 moved to it.
  - **Eval.** Cases 126 and 3535 now `require_tool: system_status`, and the eval offers `system_status` as production does.
- **D5 analyst clock.** `config/agents.yaml` gives the analyst `mcp-time` and `clock: true`, so every run gets "Now: <weekday, date, time, zone> (<IANA>)" just before the task (`jarvis/agents/base.py` `clock_note`). Evidence: turn 911 "couldn't determine today's date"; turn 3173 stale games.
- **W4 place names.** Deepgram Flux keyterms add Larry's durable place words from memory (`user.location.home/work/primary/secondary`, never the current location). Today these are Florida, Alpharetta, Georgia and Spartanburg. Turn 3513 heard "Alfreda, Georgia" one minute after 3508 heard "Alpharetta" correctly.
- **W5 live data.** The sports source shipped in #86. The retry guard now lets a delegation through when Larry's own turn names a website (`espn.com`, "spn dot com") and the task names one. The exact failed task from 2026-09-13 22:50 is pinned in `tests/unit/test_delegate.py`. The kill switch is `JARVIS_RETRY_GUARD_NAMED_SOURCE_ENABLED=false`.
- **W14 verify on screen.** Developer workflow `verify-ui-change-on-screen`: a UI change is done only when visible. The developer checks where it is, uses `screen_view` if it should be visible, and names the step left or says "unverified". It matches the 4 logged zoom-and-pan status tasks of 2026-09-09.

**Phase 3: BUILT in the VM, 2026-09-25 (rev 1.9).** Branch `phase3` on Phase 2; patch `closure-checks/phase3-on-phase2.patch`. Larry's decisions (2026-09-25): W8 option A, self-rebuild option B. Everything below is untested live until the end-of-project run.

- **W8 human-only changes (option A).** Mortimer still never writes a human-only (Tier 0) file.
  - **The proposal.** A self-edit write to a human-only file is saved instead as `docs/proposals/<file>-<hash>.patch`, a git patch against the session's base revision with a header (Target, Base blob, Result blob, Why). `docs/` is routine, so the draft PR can carry it. `selfedit_read` shows the file read-only from the base snapshot (`Session.baseline_text`: host-side, the guest is not consulted). A test that needs the change joins the proposal (`proposal: true`); a file is either proposed or written in a session, never both. Secrets and runtime data (anything the source snapshot never carries: `.env`, `data/`, vaults, keys, databases) are still refused, at the preview and on write. The planner path gets the same routing through `SelfEditService.propose_edit`.
  - **What Larry hears.** The preview names the human-only files ("I won't change it … you approve it, then apply it with one command"). The PR body and the finish summary say HUMAN-ONLY PROPOSAL, "do not merge this pull request as it is", and carry the command. The result hook matches the marker to `voice-human-only-proposal` (supervisor, priority 8): say what it changes, ask "approve?", show the command only after yes. The show_commands gate lets exactly that command through with no NEEDS-INPUT window, because the yes can come much later: `cd` to this checkout (nowhere else), the PR number, and a 12-hex digest (`is_apply_proposal_command`, pinned to `proposals.apply_command`).
  - **The command.** `cd <production> && .venv/bin/python scripts/apply_proposal.py <PR> <digest>` runs under Larry's git and gh. It checks, before pushing anything:
    - the PR is an open Mortimer self-edit, fetched at exactly the commit GitHub reports;
    - its proposal files are exactly the ones the edit API wrote (the digest covers their paths and contents, so a file that a program added or changed during validation stops it);
    - every other file the PR changes is one Mortimer may write, by the trusted allowlist (Larry's branch leaves CI gate 1 behind);
    - after applying in a throwaway worktree with git hooks off, the net change is exactly the declared targets, each keeping its mode (a new file is 100644) and matching its Result blob, plus the removed proposal files. Any other change stops it: a second diff git would apply but the header check does not count, a rename, a symlink, a mode flip.
    Then it shows the diff and waits for y (next item). Only then does it commit, push `larry/proposal-<PR>`, open that PR for CI and close Mortimer's as superseded. `scripts/apply_proposal.py` is Tier 0.
  - **Adversarial review (2026-09-25).** The first version checked the patch text, not its effect: a proposal could carry a traditional `---`/`+++` diff before or after its header, and git applied it to another file. That was reproduced, then fixed by the net-change check, the digest, hooks off, and the gate's fixed checkout. Tests pin each (`tests/unit/test_apply_proposal.py`, now 30 cases).
  - **Informed approval (Larry, 2026-09-25: the recommended option).** CI runs as soon as the new PR opens, and GitHub gives a same-repository PR's workflows the repository's secrets and runs the PR's own copy of them. So the approval has to come after reading the change, not before. The script prints the exact diff of every human-only file (terminal control codes and Unicode direction overrides shown as escapes; no external diff or textconv), lists the PR's other files, and pushes nothing unless Larry types y. The voice "yes" now means "give me the command"; the y is the approval.
  - **One change from what Larry approved.** Option A said the command pushes to Mortimer's PR branch. CI gate 1 (`scripts/check_allowlist.py` in validate.yml) fails a self-edit branch (`mortimer/selfedit/*`) that touches a path outside the allowlist, and exempts every other branch ("the allowlist constrains the agent, not the humans"). So the applied change goes on Larry's own branch and PR. The one approval and the one command are unchanged; the PR number changes. Larry confirmed this on 2026-09-25.
  - **Evidence.** 2026-09-18 17:53: `selfedit_start` refused at preview for `jarvis/admin/server.py`, and the developer dropped that file. W8 cases 1951, 2620 and 2873–2889 were files that have since become routine (`jarvis/bot/display.py` is core, Swift sources are routine, and the registry split moved the profile pool out of Tier 0).
- **Self-rebuild (option B).** The deploy stays Larry's one command.
  - The 2026-09-09 hand-offs (2751, 2753, 2769) repeated the tool text of that day: `selfedit_status` results 5153 and 5414 said "cd macos/MortimerHost && scripts/bundle.sh". The sandbox rewrite of 2026-09-10 (cf4a5f6) removed it, and no assistant turn names `bundle.sh` after 2026-09-09.
  - Now the self_development section, the finish notices and the planner prompt say a merged change is live after "deploy with DEPLOY-MAIN" and never name a build script. Voice workflow `voice-merged-deploy` (supervisor, priority 9) matches 4 of the 1,525 logged user turns (2667, 2695, 2752, 2756), all about a merge or a rebuild. Asked whether a change is live, Mortimer checks `system_status`, topic build. `DEPLOY-MAIN.sh` lives in the git-ignored `closure-checks/`; at the end run it moves into the repo as `scripts/deploy_main.sh` (Tier 0), so the name Mortimer gives keeps pointing at something (Larry, 2026-09-25).
- **W6 tool-server health: covered by #86, no code.** The registry supervisor restarts a dead MCP child and retries the call (`tests/integration/test_registry_supervision.py`, e.g. `test_dead_child_is_restarted_and_call_succeeds`, `test_restart_backoff_marks_down_after_three`). The "./scripts/mortimer.sh" sentence is already gone from self_development (pinned by `test_an_offline_sidecar_is_reported_without_a_command`).
- **W7 self-edit recovery: superseded, no code.** Since 2026-09-10 a session publishes through the GitHub API from a frozen VM candidate onto a fresh branch, so there is no local branch to fall behind. The logged git failures (1878 and 1931 on 08-30, 2699 on 09-09) all predate it. Expired-staging errors: 2, both on 09-07, and none in the 21 `selfedit_start` calls of 09-17/18.
- **D6 tier check: confirmed, no code.** The `target_paths` rule (2026-09-07, F5) is pinned by `test_stage_classifies_target_paths_not_the_prose`; no preview has been refused for a file it only mentioned since.
- **VM results.** Unit 3,774 passed; integration 132 passed and 4 skipped (live), and the parent-terminated test passes by hand with CI's mcp 1.30 visible to the child; `tests/ci` 9; sandbox 113; sub-agent evals 13; latency probe and import smoke OK. `apply_proposal.py` is tested end to end against a real git origin with a fake `gh` (30 cases, including the service's own output). The voice eval grows to 24 cases (approve first; yes shows the command; "It looks merged" names DEPLOY-MAIN); it runs with the vault at the end.

**Phase 4: memory and conversation. BUILT in the VM, 2026-09-25 (rev 1.11 part 1, rev 1.12 part 2).** Branch `phase4` on Phase 3 (two commits); patch `closure-checks/phase4-on-phase3.patch`. Definitions are from the source review's candidate table. Everything below is untested live until the end-of-project run.

- **W11 memory graph by topic: BUILT.** `memory_graph_view` failed 5 times on 2026-09-09 to 09-18: "interests", "brief_answers", "user.style.brief_answers" (no such key), "user.preference,user.style" (two topics). `resolve_memory_focus` now resolves a spoken topic before searching text:
  - a plural or phrase naming a group: "interests" goes to `prefix:user.interest`;
  - the fact whose key names the topic's words; an archived match stands for the live fact it was folded into (`user.style.commands.brief` was consolidated into `user.preference.communication_style`), and one with no live successor is skipped;
  - a dotted name that is not a key: the deepest existing prefix, searched for the rest;
  - two topics at once: the prefix both sit under.
  Against a copy of production memory, all five logged misses now resolve. #86 (status spec T4.6) already shows the overview, flagged, when nothing matches.
- **W9 one approval per task: expiry BUILT; app builds OPEN.**
  - Every tool that created or confirmed an action was retired on 2026-09-10 (8b9dd59); `commit`, `push` and `repo_commit_write` refuse even an old id. The 21 pending rows (08-13 to 09-07) could never resolve, yet `list_actions('pending')` still offered them. Migration `0026_expire_retired_actions` marks them expired, once. Replayed on a copy of production: 21 pending became expired; committed and failed rows are untouched.
  - The logged double confirmations (423, 426 on 08-17) came from those retired write tools. Self-edit already takes one approval, at the preview.
  - **App builds: BUILT (Larry, 2026-09-25: the recommended option).** One yes at `app_build_start` covers the task through the draft PR. `app_build_submit` no longer asks: it still refuses until validation has passed, the PR is a draft, and only Larry merges. `confirm` is accepted and ignored, so an older caller keeps working. The start preview says the yes covers the draft. `app_create` keeps its own yes. The app_development and app_builder prompts say "never ask again".
- **W3 what models can I use: BUILT.** #86 already answers it: `system_status` topics `models` (configured, key health), `catalog` (what a provider offers now) and `subscription` (tries one exact model), plus the daily job `com.mortimer.status-daily` (06:30), which leaves a notice when a catalog, probe or key changes. The 2026-09-23 failures (3475, 3478, 3486) ran without #86, which production does not have yet. New voice workflow `voice-model-availability` (supervisor, priority 14) sends model questions there and forbids "run this command". It matches 10 of the 1,525 logged user turns, all about model access. Failures 2873 and 3486 are re-pinned to it, and eval cases 563, 3483 and 3486 pass on a `system_status` call too.
- **W10 age-aware memory: BUILT (Larry, 2026-09-25: "I prefer the correct info, so knowing how old a memory is would tell us if we need to refresh it before answering").**
  - **Every memory carries its age.** `render_memory_context` writes `- key (3 weeks ago): content` (`jarvis.memory.fact_age`: today, yesterday, N days, N weeks, N months; "undated" when unreadable). The age is relative because the Supervisor prompt has no clock (rule 3), and the prompt is rebuilt per session. It is `updated_at`, the last write, so a sweep merge makes a fact look younger than the statements behind it. On a copy of production memory: 10,671 of 12,000 characters, all 76 facts kept (9,628 before).
  - **Things that change are re-checked.** The memory paragraph says a memory about where the user is, which models, keys, subscriptions or services exist, the state of a job, build, run or project, or a schedule is an old observation. Mortimer finds it out the way it would with no memory; if nothing can check it, it says how old the memory is. Stable facts are answered from memory. Rule 3 and Golden Rule 1 say the same. No tool is named, so the paragraph holds whether or not `system_status` is registered.
  - **Open contradictions settle correct-first**, in the sweep (`memory_sweep.settle_open_reviews`), one model call per sweep for up to 10 reviews. The model answers three questions per review: did Larry say a (given its exchanges), did he say b, can both be true. The code decides:
    - a fact Larry did not say is archived as `not-stated:review-N`, but only on complete evidence: the words must still be that exchange's own, every sighting's exchange must be on record, and nothing may have been merged into it;
    - two that can both be true are both kept (the review is dismissed);
    - otherwise the one Larry said most recently wins (`max(updated_at, last_seen_at)`, so a restatement in other words counts), and the other is archived as `reviewed:kept:<winner>`;
    - anything the model does not answer stays open, and so does a tie.
    Cluster and "task rule?" reviews are not touched, so the 4 open audience items stay in the Memory panel. A review whose fact is gone is closed. Kill switch `JARVIS_MEMORY_AUTO_SETTLE=false`.
  - **What Larry hears.** One notice at the next greeting names what was archived and why, always within the 600-character notice limit ("and N more"), and ends "Any of them comes back if you ask me to restore it." Migration `0027_notice_memory_review` rebuilds `notices` for the new kind (rows, ids and index kept; tested on a production copy). Kept-both pairs are counted, not named.
  - **Restore by voice.** `memory_restore(key)` (mcp-memory, librarian) brings any archived fact back unchanged, keeps its age, and says what it had been archived as. A miss offers close archived keys. The restored fact is stamped seen now, and capacity age-out now goes least recently seen first, so the next sweep does not take it back.
  - **Fixed on the way.** `idx_memories_fact_key` is UNIQUE over archived rows too, so restating an archived key raised IntegrityError and lost that whole exchange's extraction. It now revives the row with the new words. A rewrite from anywhere but extraction (the remember tool, a merge, a review rewrite) clears `source_turn`, so the memory graph and the settle check no longer credit an exchange with words it never held.
  - **Correction to what Larry was shown (2026-09-25).** The preview beside the choice said `prefers_no_lookups` would be archived (built from Mortimer's words) and `clarity` and `research_display` both kept. The exchanges say something else:
    - `user.preference.clarity` ("clear distinction between retrieved information and information from long-term memory"): Larry asked why research he requested was not in the main window; "long-term memory" and the distinction are Mortimer's reply at turn 3313. The stem test (`echoes_reply`) calls it an echo.
    - `user.style.prefers_no_lookups` ("prefers assistant not to look up information"): Larry said "Can you not look it up?" after Mortimer asked for his city, which reads as asking for a lookup. The stem test does not call it an echo, because "look" is his word too.
    - `research_display` has two sightings and one recorded exchange, so it can never be archived as not-stated.
    What the settle does to these is the model's answer, untested until the end run. The end-run checklist runs `python -m jarvis.memory_sweep --settle-preview` on a backup copy with auto-settle off, and Larry sees every decision before any write.
  - Auto-converting a "task rule" into a workflow stays out: `extract_workflow` writes into the running checkout, which `DEPLOY-MAIN`'s guard refuses.
- **W12 timed follow-ups: BUILT (option B).** Two direct Supervisor tools (`jarvis/bot/follow_up.py`), each with its own switch, menu entry and prompt addendum, added after every existing tool so earlier menus keep their order:
  - `progress_updates(every_seconds)` sets the progress watcher's interval for the rest of the conversation: 10 to 300 seconds, or 0 for off. The wait restarts at once. Kill switch: the existing `JARVIS_PROGRESS_UPDATES_ENABLED`.
  - `follow_up(after_seconds, check)` is one-shot, 10 to 1,800 seconds, at most 3 pending, and 0 cancels them. When due, the check comes back as a `[follow-up due]` note through the same channel as a late result: deferred while a delegation is in flight, neutralized once relayed, refused once the session is ending. It waits up to 60 s while anyone is speaking. Kill switch `JARVIS_FOLLOW_UPS_ENABLED`.
  - The voice eval grades 1344, 1456 and 1865 on these tools (26 cases). The facts `user.style.status` and `user.style.status_interval` ("Requested twenty-second automatic status updates (acknowledged as currently infeasible)", added on Larry's "proceed", rev 1.13) are on the end-run archive list.
- **D1 extractor lock: FIXED 2026-09-17, no code.** The 28 failures were all inside one backlog tick on 09-16 (rows=299): the tick's own connection held the write lock while each exchange wrote through another. #78 commits per session ("Item 13"), pinned in `test_memory_extraction_worker.py`. The extractor log has no lock error after 09-16. The 28 exchanges were never extracted.
  - **Replay: BUILT (Larry, 2026-09-25: once, at the end run, on the Mac).** `scripts/replay_extraction.py` reads the failures from the extractor log (all 28 pair with their exchange in a production copy; they happened 09-13 to 09-16). It runs the extraction model on each exchange and decides every fact against what is stored. New facts are dated to the exchange. A similar fact already stored is skipped. So is one Larry said since, in any words. A stored fact older than the exchange takes its words and time. An archived fact is revived only if it was archived before the exchange. Observations are not replayed: they are 14-day staging evidence and would expire at the next sweep. Dry run by default; `--apply` writes each exchange in one transaction and a second run changes nothing. It does not rerun `extract_from_exchange`, which would date everything today and let an old statement overwrite a newer one.
- **D1b sweep write lock: FOUND and BUILT 2026-09-25 (pre-existing, in `main`; Larry: "proceed" on the recommendation, rev 1.13).** `run_sweep` writes (A1 archives, capacity merges) and then awaits model calls (capacity merges, classification) before its one commit, so the write lock is held across each call. Reproduced: with A1 archiving one duplicate, a second connection writing during the classification call gets "database is locked" (0.3 s timeout). Other writers wait 5 s, so a model call longer than that fails the extractor or the transcript write, the 09-16 failure mode. Retained logs show no such failure after 09-16. **Fix, built (third Phase 4 commit):** `run_sweep` commits before the classification call and the settle call, and `run_capacity_enforcement` commits before each merge call. Every step was already self-contained and reversible through `became`, so a failure later in the pass now keeps the steps already done. `test_classification_call_holds_no_write_lock_after_a1` and `test_capacity_merge_call_holds_no_write_lock` fail without the change.
- **Phase 4 VM results (rev 1.13).** Unit 3,853 passed; integration 135 passed and 4 skipped, and the parent-terminated test passes by hand; `tests/ci` 9; sandbox 113; sub-agent evals 13; latency probe and import smoke OK. `tests/integration/test_registry.py` counts 81 tools (`memory_restore`).
- **Adversarial review of part 2 (2026-09-25).** Nine defects, each reproduced, then fixed with a test that fails on the first cut (10 tests):
  - the settle call held the write lock;
  - a remember-tool or merge rewrite still counted as its old exchange's words;
  - a restatement in other words did not count as newer;
  - the notice was cut mid-word at 600 characters;
  - four replay faults: revive past a similar live fact, overwrite a later restatement, `last_seen_at` moved back, the same key twice crashing the run;
  - the `memory_settle` cost rung was unknown;
  - a restored fact was aged out again by the next sweep.
- **D8 orphaned runs: FIXED 2026-08-30, no code.** `runlog.finish()` raised UnboundLocalError from 08-28 (T4a's redaction), so no run ended. f4a3e5b fixed it. All 45 orphans are from 08-28 and 08-30, and every day since has ok or failed runs and none orphaned.
- **D11 voice transport: two of four FIXED, two residual.**
  - "Jarvis supports SmallWebRTC only" (6 on 09-13): the WebSocket case was added on 09-12 (71e449f); none since.
  - "StartFrame not received yet": the connect greeting was pushed before the pipeline started. #84 (`ConnectGreeting`, 09-23) waits for both events. The last error was 09-23 21:40, before #84 was deployed; the four connects on 09-24 logged none.
  - ElevenLabs "1001 going away" (09-08, 09-11, 09-17, 09-18): speech continued in the same session in 1 of the 3 cases checked; the other two sessions ended within 3 minutes. Cause not established.
  - "Event loop is closed" (40 on 09-18, 1 on 09-24): an httpx client closed after its event loop ended, logged at session start. The session continued; which client it is has not been traced.

## §12 Workflow viewer (read-only; layout C chosen 2026-09-25)

This is the one UI item in this plan. It's outside Phase 1's scope (C5), and like Phases 2–4 it gets its own handoff-ready plan. It is built after Phase 4 and before the end-of-project run, so the same Mac run tests it.

**Built in the VM 2026-09-25 (rev 1.14); Mac check run 2 passed 18:06 (rev 1.15).** Larry chose D-V1 A, D-V2 A and D-V3 A; `MORTIMER_WORKFLOW_VIEWER_PLAN.md` §8 has the build record. Two findings from the build:
- **Voice entry is off in production.** `console_action` is registered only with `JARVIS_COMMAND_CONSOLE_ENABLED=true`, which production's `.env` doesn't set. The buttons and the Display menu work regardless.
- **D-V3's restore displaces two facts.** It takes the project tier from 7 to 10 of its cap of 8. With no merge, the next sweep ages out the two least recently seen project facts; on a copy, those were `project.model_registry.blocker` and `user.memory.fleetback_atlanta`. They stay restorable.

**Handoff plan: written 2026-09-25 (rev 1.13), `MORTIMER_WORKFLOW_VIEWER_PLAN.md`.** It re-verifies everything below on `phase4`. There are now 23 workflows: 7 voice, 11 standing rules, 5 drafts. The longest step is 325 characters. Voice can't name a view mode today, because nothing lists them. The plan adds a new decision, D-V3: six memories were archived as workflows whose files no longer exist. Two of those files were retired on purpose in 7fc0991; four were never committed and are lost. The plan is waiting on D-V1 to D-V3; nothing is built.

**Larry's decision (2026-09-25).** Layout C was chosen from the options page "Workflow Viewer Options" (claude.ai artifact 3hFe7EgauR2AAg7QDRsXxS). He picked A first, then changed to C. The viewer is a **gallery of workflow cards in the workspace and display window**. Clicking a card replaces the gallery with that workflow's horizontal flow, with back and next buttons. There is no new sidecar tab.

**What exists (verified 2026-09-25).**
- No UI shows workflows.
- `/api/knowledge` (`jarvis/admin/server.py` ~1976) returns only `name`, `source` and `has_done_when`. The steps, `when`, `agents`, `triggers` and `priority` never leave the server. JarvisKit's `KnowledgeWorkflow` (`AdminAPI.swift:573`) has the same three fields.
- The workspace switches views through `ConsoleActionCoordinator` `.viewSet` (`ConsoleActionCoordinator.swift:89`). The modes are `conversation`, `memory`, `results` and `atlas`, and `WorkspaceView` has buttons for them ("Conversation", "Knowledge Atlas", "Memory graph"). There is also a Display menu, "Show memory graph" → `sendToDisplay(.memoryGraph)` (`WorkspaceView.swift:144`).
- The supervisor already has a `console_action` tool (`jarvis/bot/console_actions.py`) that sends `view_set` with a `mode`. A new mode is how "show me the workflows" opens it by voice.
- With Phase 1 applied, 18 workflows load, with 1–4 steps each. The longest step is 179 characters. Three are supervisor-only voice workflows and five are REVIEW ME drafts.

**Design.**
- **Entry.**
  - A new `.viewSet` mode `workflows`, with a "Workflows" button beside "Knowledge Atlas" and "Memory graph".
  - A Display menu item "Show workflows", using a new `SupportingDisplayContent.workflows` so it opens in the display window like the memory graph.
  - Voice uses the same mode through `console_action`.
- **Gallery.** A filter searches name, `when` and step text. There are three groups:
  - Voice · supervisor, sorted by priority;
  - Standing rules · all specialists;
  - Drafts · review me, drawn with dashed borders.

  Each card shows the name, the first step (clamped to 2 lines), the step count and done-when count (or agents and priority), and a pip strip of the flow's shape (trigger · steps · done). The usage count is described under Pieces, step 2.
- **Detail.** Clicking a card swaps the gallery for `WorkflowFlowView`, with "← All workflows" and "Next: <name> →" buttons and a "workflow n of 18" position. The flow is a horizontal scroll of fixed-width cards (~232 pt) that wrap their text:
  - **Trigger node.** For keyword workflows, it shows the `when` text, the match tokens, and the rule "≥ 35% overlap · strongest wins · 1 per run". For voice workflows, it shows the user / result / reply hooks and the priority.
  - **One node per step**, numbered.
  - **Done-when node.** Green when present. When missing, a dashed amber node that says "no finish test".
  - **Badges:** agents, priority, draft, source file.

**Pieces.**
1. `GET /api/workflows` returns every field plus a `draft` flag (true when `done_when` is empty). Python unit test.
2. *(Open, D-V2)* Usage: the count of `workflow_injected` log lines per name, with last date and agents. Log rotation limits the history, which goes back to 2026-08-22 today. Voice matches would need the same log line.
3. JarvisKit: a `WorkflowDetail` model and an `AdminAPI.workflows()` call. Decode test.
4. MortimerHost:
   - the `WorkflowsStore`;
   - `WorkflowsGalleryView` and `WorkflowFlowView`;
   - the `workflows` view mode in `ConsoleActionCoordinator`;
   - the "Workflows" button;
   - `SupportingDisplayContent.workflows` and the Display menu item.

   View tests, plus a coordinator test for the new mode.
5. Python: add `workflows` to the `view_set` modes the supervisor is told about, if the console inventory or help lists them (to check in the §12 handoff plan). Unit test.

**Not in v1.** Editing: workflows are "authored, reviewed and version controlled" config (`jarvis/workflows.py:48`), so an edit path would go through self-edit or a PR. A "which workflow would match this sentence" tester is also out.

**Open decisions.**
- **D-V1 (before or alongside the viewer).** The five REVIEW ME drafts from commit d74e40d are loaded as live policy. `load_workflows()` has no draft filter, and production has workflows on: there is no `JARVIS_WORKFLOWS_ENABLED` in `.env`, and there were injections as recently as 2026-09-18. None of the five has fired in the logs retained since 2026-08-22. `user-interface-analyst-visibility` and `user-style-ui-requirement` are near-duplicates, and `user-task-website-comparison` is a session note. The options are to review, delete, or add a `draft: true` field that the loader skips.
- **D-V2.** Whether to include usage counts in v1.

## §13 #80 privacy fix (built in the VM 2026-09-25, rev 1.15)

Larry, 2026-09-25: fix it in this landing, as a seventh patch through the same Mac check.

**The hole (reproduced 2026-09-25 on a scratch database).** #80 (`88b206f`) added model route preferences (`jarvis/model_preferences.py`). `_validate_choice` checked that the route could carry the privacy level the preference named, but not that the level was at least the workload's configured one. Staging `approved_external` for `librarian` (configured `confidential`) or `systems` (configured `local_only`) was accepted on `direct_api`, `saygm` and `local`. Confirming it made `resolve_policy(workload).privacy` return `approved_external`. Two things read that level:
- the run-log redaction for confidential and local-only workloads (`jarvis/agents/base.py` `_policy_requires_runlog_redaction`, active only with `JARVIS_MODEL_ROUTING_ENABLED=1`);
- the delegation status masking (`jarvis/agents/delegate.py`), active always.

With routing enabled, the lowered level also lets `resolve_model_route` send the workload over an external route: on a scratch database with the old code, a confirmed `librarian` preference for `direct_api` at `approved_external` resolved to `direct_api` (approved_external).

**Exposure.** Production has no preference rows and no drafts (read from a copy of `data/jarvis.db`, 2026-09-25). Routing is off there: `JARVIS_MODEL_ROUTING_ENABLED` is absent from `.env` and from the launchd template, and the Settings default is `False`. Nothing saved is affected.

**The fix.** `_validate_choice` refuses a level below the configured one: a preference may keep or raise a workload's privacy, never lower it. The `policy` it compares against is resolved with `include_preferences=False`, so it is the configured level. `confirm_preference` re-validates, so a lowering draft staged by the old code is refused at confirm too. The module's set of privacy levels and its ordering are now one `PRIVACY_ORDER`.

**Tests** (`tests/unit/test_model_preferences.py`):
- `test_a_preference_can_never_lower_a_workloads_privacy` (librarian and systems, all three routes);
- `test_a_draft_staged_before_the_fix_is_refused_at_confirm`;
- `test_keeping_or_raising_privacy_is_still_allowed`.

The first three cases fail with the old `_validate_choice` and pass with the new one. Unit 3,866 passed, integration 135 passed and 4 skipped, CI 9, sandbox 113, sub-agent evals 13.

**Found alongside, not changed.** With the shipped `config/model_access.yaml`, `librarian`, `systems`, `memory` and `background` cannot resolve a route when routing is enabled. Their configured route is `direct_api`, which provides only `approved_external`, and `resolve_model_route` refuses it (run 2026-09-25). Routing is off in production, so nothing fails today. Turning routing on would need a `confidential` or `local_only` route for those four first. Before this fix, a lowering preference was one way to make them resolve; now it is refused.
