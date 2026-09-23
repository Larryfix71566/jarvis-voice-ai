# Mortimer — Resume Brief: crash and interruption recovery

**Status:** SUPERSEDED 2026-08-21 by the reliability overhaul (barge-in survival, CLAUDE.md).
Author: Claude, 2026-08-20. Requested by Larry (*"how do we recover from a
crash and continue with what we were working on elegantly?"*).

This plan supersedes the conversational design of 2026-08-19 and addresses
the nine gaps the review of that design surfaced. Each gap is cited where
its fix lives (G1–G9).

---

## 0. Founding decisions (carried from the reviewed design, unchanged)

1. **Assembled from artifacts that already survive a crash.** No new
   logging during normal operation, no new privacy surface. The sources are
   `agent_runs` rows, self-edit branches, uncommitted git paths, plan docs,
   and the session summary — all durable today.
2. **No raw `logs/` access, ever.** `logs` stays in `mcp_repo`'s
   `DENY_SEGMENTS`: `logs/bot.log` holds the transcript, and `MemoryWatcher`
   folds transcripts into memory — the handoff plan routed clipboard content
   *around* the transcript for exactly this reason. Separately,
   `MAX_TOOL_ITERATIONS` makes "review all the logs" the canonical
   budget-exhausting task (run `b74ed019`).
3. **Resumption is named, never taken.** The brief states the resume path
   for each item; a human invokes it. Autonomous continuation is wrong for
   the same reason the retry guard exists — a half-done step redone is
   destructive, and everything else in this system is draft→confirm.
4. **Disagreements are reported, never resolved silently** — the
   `jarvis/toolresult.py` discipline applied to work state.

## 1. Vocabulary

- **Resume brief** — one structured JSON object describing possibly
  unfinished work, assembled read-only on demand.
- **Interrupted** vs **in progress** — the distinction G1 requires. State
  is *interrupted* only relative to an acknowledgement: the brief is
  offered when its content differs from what was last offered, never
  merely because state exists.
- **Crash** vs **planned stop** — G2's distinction, labelled per §3.

---

## R1 — `GET /api/resume` on the admin sidecar (G4: the owner)

The sidecar assembles the brief. It already owns `/api/ambient`, has the
repo, the runs store (`jarvis.runlog.store.list_runs`), and the self-edit
service; the console already polls it; and putting assembly in the bot
would re-create state the sidecar has. One new read-only endpoint:

```json
{
  "ok": true,
  "kind": "crash" | "in_progress" | null,
  "generated_at": "...",
  "content_hash": "sha256-of-the-items-below",
  "offered_before": false,
  "items": [
    {"type": "orphaned_run",   "run_id": "...", "agent": "...",
     "task_preview": "...", "age_h": 3.2, "payload_path": "...",
     "resume": "re-delegate with findings_path at the payload"},
    {"type": "selfedit_branch", "branch": "jarvis/self-edit/...",
     "validated": false, "checkpoint_path": "... or null",
     "resume": "selfedit_status, then validate or revert"},
    {"type": "plan_in_flight", "path": "docs/plans/X.md",
     "status_line": "APPROVED ...", "boxes_checked": 4, "boxes_total": 7,
     "conflict": "status says IMPLEMENTED but 3 boxes unchecked" ,
     "resume": "selfedit_start with plan_path"},
    {"type": "external_work", "uncommitted_paths": 45,
     "sample": ["jarvis/prompts.py", "..."], "resume": null},
    {"type": "git_lock", "age_s": 11235,
     "resume": "rm .git/index.lock if no git process is running"}
  ]
}
```

Item sources, each with its confinement:

- **orphaned_run** — `list_runs` filtered to `status IN ('running',
  'orphaned')`, **within `RESUME_RUN_WINDOW_H = 48`** (G7; ⚙ TUNING KNOB,
  same reasoning as `JARVIS_SCREEN_RETENTION_HOURS`: a three-week-old
  orphan is history, not unfinished work, and without a window the brief
  accretes noise faster than runlog pruning removes it). `payload_path` is
  included because `findings_path` re-delegation — the resume mechanism
  the handoff loop already built — needs a path, not a summary.
- **selfedit_branch** — `git branch --list 'jarvis/self-edit/*'` via
  `SelfEditService._git` (argument list, never a shell). `validated` from
  the service when the branch is the live session's; `null` otherwise —
  the in-memory `_validated_ok` does not survive a sidecar restart, and
  the brief says "unknown" rather than guessing.
- **plan_in_flight** — §4's rules.
- **external_work** — §5's rule. Path **names and counts only, never
  contents**: a diff body can contain anything the changed files contain.
- **git_lock** — reuse `check_env.py`'s existing staleness check (same age
  threshold, one implementation). Included because a stale lock blocks
  every git-touching resume action, and on 2026-08-19 one sat for 3+ hours
  (G9).

Every item's `resume` field is a **statement, not an action** — founding
decision 3. The endpoint mutates nothing.

## R2 — Offered-once semantics: server-side acknowledgement (G1, G5)

**The gap that reshapes the design.** ~45 uncommitted files is this repo's
*normal working posture*. "Offer when non-empty" would fire on every
connect forever, which both violates the engagement layer's
nothing-demands-interaction rule and trains the user to ignore the one
brief that matters.

Fix: the ambient chips' dismiss-until-content-changes pattern
(`AmbientStrip`'s `LS_DISMISSED`, keyed by content), moved **server-side**:

- The sidecar keeps `data/resume_ack.json`: `{"content_hash": "...",
  "offered_at": "..."}`. Written **atomically** (tempfile + rename, the
  vault's write discipline) — an ack corrupted by the crash it describes
  must not wedge future briefs; an unreadable file is treated as absent.
- `GET /api/resume` computes `content_hash` over the items (excluding
  ages/timestamps, so mere passage of time is not "new content") and sets
  `offered_before = (hash == acked hash)`.
- `POST /api/resume/ack {content_hash}` records it. The BOT calls this
  after speaking the offer — offering IS acknowledging, exactly as a
  dismissed ambient chip stays hidden until its content changes. No
  separate dismiss step for the user to learn.

Server-side, not `localStorage`, deliberately (G5): the bot holds no UI
state by design, the CLI has no localStorage, and the shell runs three
webviews. One ack location serves every client, and survives bot restarts
without re-offering.

## R3 — Crash vs planned stop (G2)

Two events, different trust levels, one surface. Classified from evidence,
never inferred from prose:

- `kind = "crash"` when any `orphaned_run` item exists — a process died
  mid-run — or any self-edit checkpoint (§6) exists without a live
  session. The brief's framing: *"a run was interrupted"* and **plan
  checkboxes are flagged as suspect** (they are stale precisely when the
  updater died).
- `kind = "in_progress"` otherwise — an orderly stop. Plan docs are the
  primary source; the framing is *"we left off at…"*.

## R4 — Plan-state parsing: Status line first, conflicts reported (G3)

A plan with every box unchecked is indistinguishable from one never
approved, so checkboxes cannot be the primary signal. Rules, in order:

1. Parse the `**Status:**` line (existing convention:
   `AWAITING APPROVAL` / `APPROVED` / `IMPLEMENTED`, substring match,
   case-insensitive). No Status line → the doc is not a tracked plan;
   skip it.
2. `AWAITING APPROVAL` → not in flight; never in the brief.
3. `APPROVED` without `IMPLEMENTED` → in flight; count `- [x]` / `- [ ]`.
4. `IMPLEMENTED` with unchecked boxes → **in the brief as a CONFLICT**,
   `conflict` field populated, because at least one status line in this
   repo is known-stale (`MORTIMER_CONFIRMATION_AND_CAPABILITY_PLAN.md`).
   Founding decision 4: report the disagreement; never pick a winner.
5. Only `docs/plans/*.md` (not `implemented/`, not `docs/reviews/`), only
   files modified within `RESUME_PLAN_WINDOW_D = 14` days (⚙ TUNING KNOB)
   — G7's recency logic applied to plans.

Uncommitted paths overlapping a plan's subject are NOT matched
automatically — token-matching file paths to plan topics is a guess, and a
wrong guess ("plan X is done, ignore those files") is worse than listing
the two facts side by side.

## R5 — The voice offer at connect (G4's second half)

`pipeline.py`'s `on_client_connected` already injects a `[system]` greeting
message with the local time. It gains one best-effort step:

- HTTP `GET /api/resume` to the sidecar, **timeout 2s, failures silent** —
  a down sidecar must never delay or break connect (the ambient strip
  already models this: sidecar-down hides chips, never errors).
- If `ok`, `kind` is non-null, and `offered_before` is false: append ONE
  sentence to the greeting context — *"One line if there is unfinished
  work: e.g. 'We were implementing the key-validity plan — K5 through K7
  remain.'"* — then `POST /api/resume/ack`.
- Otherwise: nothing. No repeat on later turns, no nagging — the ack makes
  this mechanical rather than behavioural.

**Detail on request** is a direct Supervisor tool, `resume_brief` — the
`set_voice`/`ui_control`/`view_screen` pattern: direct, never a delegation,
registered in `pipeline.py` behind the kill switch. It fetches
`/api/resume` and returns the items for the model to narrate; the full
JSON also goes to the display window (`"window"` surface), because a list
of five items is display content, not speech. Routing-eval cases pin that
"what were we working on" is never delegated (the U8 precedent). Direct
tools are not in the MCP registry, so `TOTAL_TOOLS` is unchanged.

Console surface: the drawer's existing tabs suffice — no new panel in v1
(the same scope guard the app-build plan applied: panels grow from real
use). The brief is reachable via the display window and
`curl /api/resume`.

## R6 — Synthesis checkpoints for the two long loops (G6)

The one genuine gap needing a NEW artifact: `UpgradeAgent` dying at
iteration 12 of 15 leaves every tool call in the JSONL but no statement of
what it concluded. `findings_path` solves this for handoffs because the
agent *chooses* to write findings; a crash gives no such chance.

- **Scope: `UpgradeAgent` and `AppBuildAgent` only.** Voice-loop
  delegations are bounded at 5–15 iterations and seconds long;
  checkpointing them is cost without benefit.
- The loop writes `data/upgrade_checkpoints/<branch-slug>.md` every
  `CHECKPOINT_EVERY_N = 3` iterations (⚙ TUNING KNOB) and immediately
  before each `validate()`: goal, iteration count, files touched so far,
  and the model's own one-paragraph "state of the work" — prompted for as
  part of the loop turn, not a separate model call.
- **Atomic write** (tempfile + rename): a checkpoint corrupted by the
  crash it exists to survive is worse than none (G6's hard requirement).
- **Deleted on orderly completion** — `submit()` and `revert()` both
  remove it, so a checkpoint's existence *is* evidence of interruption
  (feeding R3's classifier). Orphans older than `RESUME_RUN_WINDOW_H` are
  pruned at sidecar startup beside the existing prunes.
- `data/**` is already self-edit-denied and gitignored — nothing new
  leaks into the repo, and the agent cannot edit its own checkpoints
  through the self-edit path.

## R7 — External (Cowork-shaped) work: report, never offer (G8)

Uncommitted changes with **no** matching orphaned run and **no** live
self-edit branch were made by an actor other than Mortimer — Larry
directly, or a Cowork session. Offering "shall I resume this?" invites two
actors editing the same files (today's diff is exactly this shape).

Rule, by construction: the `external_work` item's `resume` field is always
`null`, and the `resume_brief` tool's narration instruction says these are
reported as facts with no offered action. The brief informs; the human
coordinates.

## R8 — Kill switch and knobs

- `JARVIS_RESUME_ENABLED=false` — enforced at TWO points that fail
  independently: the sidecar endpoint returns `{"ok": false, "disabled":
  true}`, and `pipeline.py` skips both the connect fetch and the tool
  registration. (One switch, two enforcement sites, because the two
  processes restart independently and a half-disabled state must degrade
  to silence, not to errors.)
- `RESUME_RUN_WINDOW_H = 48`, `RESUME_PLAN_WINDOW_D = 14`,
  `CHECKPOINT_EVERY_N = 3` — all in one place in the new module, marked
  ⚙ TUNING KNOB per house style.

## R9 — Module layout

- `jarvis/resume.py` — pure assembly: `build_brief(...)` takes injected
  callables (runs lister, git runner, plans dir, ack reader) and returns
  the dict. No network, no FastAPI import — unit-testable like
  `council/scoring.py`.
- `jarvis/admin/server.py` — the two endpoints, thin wrappers.
- `jarvis/bot/resume_tool.py` — the direct tool + the connect-time fetch
  helper, mirroring `screen_tool.py`'s shape.
- Checkpoint writing inside `jarvis/agents/upgrade_agent.py` (both classes
  share the loop, so one implementation).

## Tests (`tests/unit/test_resume.py`, injected seams, no subprocesses)

| test | pins |
|---|---|
| `test_normal_dirty_tree_alone_is_not_offered_twice` | **G1, THE test** — same content acked once is `offered_before=true` on every later call |
| `test_new_orphaned_run_changes_the_hash` | new interruption re-offers |
| `test_ages_do_not_change_the_hash` | time passing is not new content |
| `test_orphaned_runs_outside_window_are_excluded` | G7 |
| `test_crash_vs_in_progress_classification` | G2 — orphan or checkpoint ⇒ crash |
| `test_status_line_beats_checkboxes_and_conflict_is_reported` | G3 — the stale-status case produces a `conflict`, not a silent pick |
| `test_awaiting_approval_plans_never_appear` | R4 rule 2 |
| `test_external_work_has_no_resume_action` | G8 |
| `test_external_paths_are_names_only` | no file contents in the brief |
| `test_ack_write_is_atomic_and_corrupt_ack_is_treated_as_absent` | R2 |
| `test_checkpoint_deleted_on_submit_and_revert` | R6 — existence means interruption |
| `test_sidecar_down_yields_no_offer_and_no_error` | R5, bot side |
| `test_kill_switch_silences_both_sites` | R8 |

Plus routing-eval cases: "what were we working on", "where did we leave
off" → `none` (direct tool, never delegated).

## What this plan deliberately does not do

- **No raw `logs/` access** (founding decision 2 — restated because it is
  the most tempting shortcut for any future implementer).
- **No autonomous resumption.** The brief names paths; humans take them.
- **No automatic matching of uncommitted files to plans** (R4) — a wrong
  guess is worse than two adjacent facts.
- **No new console panel in v1** (R5's scope guard).
- **No checkpointing of voice-loop delegations** (R6's scope).
- **No transcript content anywhere in the brief.** The session summary
  (`memory.get_summary_text`, already on `/api/ambient`) is the only
  conversation-derived text, and it already passed the memory layer's
  filters.

## Acceptance

1. Fresh connect with acked state → greeting contains no resume sentence.
2. Kill the bot mid-delegation, restart → next connect's greeting carries
   one sentence naming the interrupted agent; `/api/resume` shows the
   orphaned run with its `payload_path`; re-delegating with
   `findings_path` at that path resumes rather than re-derives.
3. Kill the sidecar mid-self-edit-run, restart → the brief lists the
   branch AND its checkpoint; the checkpoint's "state of the work"
   paragraph reflects an iteration within the last `CHECKPOINT_EVERY_N`.
4. A dirty tree with no Mortimer artifacts → `external_work` item, no
   resume action, one offer, then silence until the tree's path-set
   changes.
5. The stale-status plan (`MORTIMER_CONFIRMATION_AND_CAPABILITY_PLAN.md`,
   as it stands today) appears as a `conflict` item — the known-stale case
   is the live fixture.
6. `JARVIS_RESUME_ENABLED=false` → no sentence, no tool, endpoint says
   disabled; `pytest tests/unit tests/integration -q` green;
   `RUN_LIVE=1 python -m tests.evals.routing_eval` ≥ 90% with the new
   cases.

## Approval

- [ ] R1 — `/api/resume` assembly (items, windows, confinements)
- [ ] R2 — server-side ack, offered-once semantics
- [ ] R3 — crash vs in-progress classification
- [ ] R4 — plan Status-line parsing with reported conflicts
- [ ] R5 — connect-time sentence + `resume_brief` direct tool
- [ ] R6 — synthesis checkpoints (UpgradeAgent/AppBuildAgent only)
- [ ] R7 — external work reported, never offered
- [ ] R8 — kill switch + knobs
