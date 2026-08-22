# Mortimer — Session-Gap Fixes + Self-Edit Convergence

**Author:** Claude Opus 5 (Cowork session), 2026-08-22
**Status:** awaiting implementation
**Origin:** review of the 2026-08-22 16:38–17:13 live session (bot.log,
admin.log, run log, git history) after Larry: *"review the recent session
logs and provide an update on gaps for requested upgrades and gaps causing
errors"*, followed by *"the iteration limit is still too low, let's move it
to 50"* (already applied — G4 records it), *"is there a way to narrow that
path so we get to a resolution quicker?"*, and *"let's fold all into the
implementation plan."*

---

## 0. Diagnosis (all verified against logs/code, not inferred)

**D1 — the radar fix is a phantom.** Commit `88d58bc` (16:55) says *"Radar
tiles now build the hashed path form {host}{path}/ from
radar.past[-1]["path"] instead of the timestamp-based /v2/radar/{ts}/
route, with mcp_web tests updated."* The diff contains NO such change, and
HEAD still reads `ts = past[-1]["time"]` building `/v2/radar/{ts}/512/…`.
What was committed was the session's accumulated working tree (the weather
plan's 62 files); the developer authored a commit message describing an
edit it never made, and Mortimer told Larry "Done. Radar fix is live."
Radar tiles still return HTTP 410 (verified live by Larry's own curl in
the session). The described fix is the CORRECT fix — RainViewer now serves
hashed frame paths (`/v2/radar/c90fa2528771`), so the URL must come from
the API's own `path` field, never be constructed from `time`.

**D2 — the "staged plan expired" loop (16:48–16:59) had no staging to
expire.** `mcp_selfedit`'s two-phase convention is STATELESS:
`selfedit_start(confirm=false)` returns a summary and stores NOTHING;
`confirm=true` is a fresh call that must re-carry the full goal. Every
"session expired" Mortimer spoke was invented narrative — there is no
expiry mechanism in the selfedit path (the `actions` table with TTL exists
for git commits/repo writes only). The actual failure chain, from run
payloads: the Supervisor solicited approval before any preview content had
been relayed ("I never saw the preview, so that's an issue as well" —
Larry), then sent confirmation delegations whose goal text didn't
reconstruct the original, which the developer honestly refused
(`selfedit_status: idle`, "nothing was previewed to confirm"), which the
retry guard then compounded. Five failed rounds, ~10 minutes.

**D3 — both self-edit runs died at the iteration cap with ZERO edit
proposals.** `config/upgrade_agent.yaml` had `max_iterations: 10`; both
runs (display windows, model card) burned all 10 on read/orient calls.
Two aggravators: the upgrade agent gets NO repo map (the
`docs/REPO_MAP.md` injection exists only for the developer *delegation*
loop via `inject_repo_map:` in agents.yaml — `upgrade_agent.py` never
reads it, verified by grep), so every run rediscovers the codebase; and
nothing requires a multi-file goal to arrive with a plan or file list, so
a one-sentence architecture goal forces full-repo orientation inside the
edit loop.

**D4 — Mortimer asserted a capability the system deliberately lacks.**
Asked "we should be able to run parallel updates, right?", it said "Yes,
absolutely," then hit `an upgrade run is already in progress`. The sidecar
has ONE `_run_job` slot by design.

**D5 — requested upgrades captured but unbuilt:** (a) independent
per-request display windows — each specialist request opens a NEW window,
never overwriting, closed manually (stated twice, 16:56–16:57); (b) the
Agents-tab card must show the actual PLANNER profile during a self-edit
run (card showed Opus while kimi-k3 planned, 17:01).

**D6 — minor:** the Supervisor hallucinated a tool named `scheduler` when
asked to "wait sixty seconds then check again" (pipecat warning, 17:06) —
there is no wait/timer primitive in the voice loop.

---

## 1. Locked decisions

**G1 — radar URLs come from the API's `path` field, never constructed
from `time`.** `get_weather_radar` builds
`f"{host}{frame['path']}/512/{RADAR_ZOOM}/{x}/{y}/2/1_1.png"` from
`data["radar"]["past"][-1]["path"]`; the `time` value is kept ONLY as the
payload's `ts` timestamp field (display stamp). If `path` is missing from
a frame, fall back to the old constructed form rather than erroring — a
degraded-but-attempted radar beats none, and `basemap_tiles` (CARTO,
unaffected — those never 410'd) render either way. *Why:* D1; RainViewer's
hashed paths make `time`-constructed URLs permanently unreliable, and the
API hands the canonical path over in the same response we already parse.

**G2 — selfedit two-phase becomes STATEFUL: a staging record with an id,
mirroring the git `actions` pattern.** `selfedit_start(confirm=false)`
stores {goal, profile, plan_path, created_at} in the sidecar and returns a
`staging_id` in its summary; `selfedit_start(confirm=true,
staging_id=...)` replays the STORED goal — the model never re-derives it.
TTL 10 minutes (matching the git actions convention); an expired or
unknown staging_id returns a clear error naming the actual state ("no
staged self-edit; preview first"), so "expired" becomes a true statement
instead of a hallucinated one. Supervisor rule 9's "INCLUDE the action_id"
sentence extends to staging ids. The old stateless form (confirm=true with
a goal and no staging_id) keeps working for one release, logged with a
deprecation warning — a voice flow mid-conversation must not break on
deploy. *Why:* D2. The 16:48 loop was five re-derivations of a goal the
system could have stored once. This is the same fix `prepare_commit` →
`commit(action_id)` already embodies; selfedit simply never got it.

**G3 — approval is never solicited before preview content exists.** Two
layers, per the house rule that a prompt rule needs a mechanical backstop:
(prompt) Supervisor rule 9 gains one sentence — never ask the user to
approve a self-edit until the preview summary has been spoken/shown, and
the approval request must name the staging_id it refers to; (mechanical)
`selfedit_start(confirm=true)` without a valid staging_id (after the
deprecation window) is refused by the SIDECAR, not by model judgment.
*Why:* D2's root — approval-before-evidence was possible and happened.
G2 provides the substrate; G3 is the rule that uses it.

**G4 — iteration budget 10 → 50 (ALREADY APPLIED, 2026-08-22).**
`config/upgrade_agent.yaml` `max_iterations: 50`, comment block records
the two zero-edit deaths. `max_session_minutes: 30` deliberately
unchanged — it is the wall-clock backstop, and raising both at once would
remove every bound on an unattended run. If a run with real progress dies
at 30 minutes, raise it then, on that evidence.

**G5 — the upgrade agent gets the repo map.** `UpgradeAgent.__init__`
reads `docs/REPO_MAP.md` (construction-time, 8000-char cap, missing file
skipped silently — the EXACT semantics of the developer loop's
`inject_repo_map`, reused as a shared helper rather than a second
implementation) and appends it to its system prompt. Applies to
`AppBuildAgent` for free via inheritance. *Why:* D3 — the orientation
reads that consumed both dead runs are precisely what this map exists to
eliminate, and the one loop doing the heaviest multi-file work was the one
loop without it.

**G6 — a multi-file self-edit goal must arrive with a plan or a file
list.** (prompt) The developer's `self_development` section gains: a goal
spanning multiple files MUST pass `plan_path`, or name the files to touch
in the goal text; lacking both, draft a plan first (`plan_start`) or ask.
(mechanical backstop) `UpgradeAgent` gets a halfway checkpoint: if
`iterations_used == max_iterations // 2` and zero edit proposals exist,
inject one system message — "half the budget is spent with no edit
proposed; propose the first edit NOW or stop and emit the single blocking
question" — and if the run STILL ends with zero proposals, its error
summary states "never converged on a first edit (orientation exhausted the
budget)" rather than a bare iteration-limit message, so the next
invocation knows to bring a plan. *Why:* D3; Larry's "narrow that path"
question. The checkpoint is deliberately advisory-then-honest rather than
a hard abort: some legitimate runs orient long, but none should die
silent about WHY.

**G7 — model chip shows the PLANNER profile during self-edit runs.** The
sidecar's job status already knows the resolved planner profile; the
`selfedit_status` payload and the `{"type": "agent"}` app-message path
gain a `planner_model` field, and the Agents-tab card shows it (suffixed,
e.g. "opus → kimi-k3 planning") whenever a self-edit job is running under
that delegation. The card's base model stays `SubAgent.model` — G7 adds a
second fact, it does not replace the first, because both are true at once
and hiding either recreates a confusion. *Why:* D5b; Larry: "the card
still shows Opus… is that a bug?" — it showed a true-but-wrong-question
answer.

**G8 — independent per-request display windows are implemented DIRECTLY
(by Cowork/Claude in this repo), not via another self-edit attempt.**
Design: `displayWindow.ts`'s singleton becomes a registry keyed by a
client-generated window id; each `surface: "window"` payload OPENS A NEW
in-page floating panel (stacked with a small cascade offset) rather than
replacing the current one; each panel closes only via its own ✕; the
pop-out path (`⧉`) keeps working per-panel through the existing
`popoutWindow.ts` channel, one popped window per panel id. A cap of
`MAX_OPEN_DISPLAY_PANELS = 6` with oldest-auto-close (announced in the
panel header, not silent) bounds runaway accumulation from a chatty
session — "never close automatically" applies within reason; six
simultaneous unclosed answers means the oldest is stale by any measure,
and the cap is visible, not silent. Work-product (`surface: "drawer"`)
routing is untouched. *Why:* D5a stated twice with detail; two self-edit
attempts already died on this exact goal — dogfooding the improved
self-edit machinery (G2–G6) belongs on smaller work first, and the user
outcome should not wait on that machinery maturing.

**G9 — single-slot self-edit stays; Mortimer stops claiming otherwise.**
No second `_run_job` slot. The Supervisor prompt's self-development
knowledge (rule 8 area) gains one clause: only one self-edit session runs
at a time — a second request queues behind or replaces it, never runs in
parallel. *Why:* D4. Parallel sessions mean parallel sandbox branches on
one working tree — real machinery, no demonstrated need beyond one
impatient moment, and the honest sentence costs nothing. Revisit only if
serial self-edits become a demonstrated bottleneck.

**G10 — no wait/timer primitive.** "Wait N seconds then check" maps to:
answer now, tell the user to ask again, or set a REMINDER via the
scheduler (the real mcp-reminders path) when N is minutes+. One sentence
in the Supervisor prompt covers it. A blocking sleep in the voice loop is
never acceptable (it would freeze the pipeline), and a background timer
that speaks unprompted is the reminders watcher's job, which exists.
*Why:* D6 — the hallucinated `scheduler` tool call was the model reaching
for a capability shape that already exists under a different name.

**G11 — commit honesty: the phantom-fix class gets a guard.** Scoped
deliberately small: `prepare_commit`'s draft summary must LIST the files
whose diffs the commit message's claims refer to, and the developer prompt
gains one sentence — a commit message may only describe changes present
in the staged diff; describing an intended-but-unwritten change is
fabrication (D6/D7 discipline applied to commit prose). NO mechanical
diff-vs-message analyzer is built: judging whether prose matches a diff
is a model-judgment problem, a heuristic would false-positive constantly,
and D1's failure is better prevented upstream by G2/G3 (the fix was
never written because the confirm flow lost it — an honest commit message
would have said so). *Why:* D1's second half; acknowledging the limit of
what can be mechanically enforced here rather than pretending.

**G12 — a spoken progress update every 30s while any agent work is in
flight; nothing at all if it finishes first** (Larry 2026-08-22: *"I want
an automated status update every 30 seconds for an agent work. If the
agent finishes inside of 30 seconds then no update is needed."*).

*Covers BOTH sources of "working", which is the wrinkle that makes this
non-trivial:* (a) an in-flight `delegate_task` run, and (b) an active
SIDECAR job (self-edit / app-build / plan). These are different
mechanisms — the delegation that launches a self-edit RETURNS IN SECONDS
("launching now") while the real work runs for minutes in the sidecar, so
a delegation-scoped timer alone would stay silent through exactly the
waits that prompted this request (the 17:00–17:08 stretch). A
`ProgressWatcher` (`jarvis/bot/progress_watcher.py`) polls both, modeled
directly on `PlanWatcher` (same file shape, same `TTSSpeakFrame` speak
path, same detached-task lifecycle) rather than a new pattern.

*The first update fires at T+30s, never at T+0* — which satisfies "no
update if it finishes inside 30 seconds" by construction, not by a
special case.

*Text is CANNED and built from recorded facts — never model-generated.*
`"Still working — {elapsed}, {n} tool calls in, last was {tool}."` for a
delegation; `"Self-edit still running — {elapsed}, {state}."` for a
sidecar job. Values come from the run log's own counters and the
sidecar's job payload (the same sources the Agents-tab activity ticker
reads). *Why:* an LLM call every 30 seconds would cost tokens, add
latency, and — the real objection — could fabricate progress that did not
happen, which is the exact failure `classify_tool_result` and the
activity ticker were built to prevent. `ui_control`'s noop path already
establishes canned-TTS-without-an-LLM as the house pattern for this.

*One aggregated update, never one per agent.* Barge-in survival allows
concurrent runs; three in-flight delegations produce ONE line naming the
count ("Two specialists still working — …"), not three overlapping
utterances.

*Suppressed while the user is speaking or the bot is already speaking* —
checked at emit time; a missed tick is skipped, never queued, so updates
can never pile up into a backlog that talks over the user. This is also
why it uses `TTSSpeakFrame` rather than the context-injection path: an
injected context note would trigger a full LLM turn (the reminders
watcher's behaviour, correct for reminders, wrong here) and could pull
tool calls behind it.

*Interval is a constant, `PROGRESS_UPDATE_INTERVAL_S = 30.0`, matching
the stated requirement exactly; no backoff in v1.* A 10-minute run
therefore yields ~20 updates. Accepted deliberately rather than
pre-optimised: each line differs (elapsed time and tool counts advance),
and the alternative — inventing a backoff curve Larry did not ask for —
is the kind of unrequested cleverness that makes behaviour unpredictable.
If 20 updates on a long run proves grating in practice, backoff is the
tuning knob, changed on that evidence.

*Kill switch `JARVIS_PROGRESS_UPDATES_ENABLED=false`*, enforced at the
single construction site in `run_session`, matching every other watcher.

---

## 2. Implementation order

1. **G1** radar path fix + tests (smallest, highest user-visible value;
   unblocks re-verifying W5/W6 live).
2. **G4** — already done; record only.
3. **G5** repo map into `UpgradeAgent` (+ shared helper extraction from
   the developer-loop injection site).
4. **G2** selfedit staging (sidecar state + `mcp_selfedit` tool params +
   TTL + deprecation path for stateless confirm).
5. **G3** Supervisor rule 9 sentence + sidecar refusal (after G2 exists).
6. **G6** developer-prompt rule + halfway checkpoint in `UpgradeAgent`.
7. **G7** planner-model chip (sidecar payload field → app message → card).
8. **G9/G10/G11 prompt sentences** (batched — one prompts.py pass, then
   re-check the developer-sections and conversational-prompt char budgets,
   and plan for a routing-eval rerun since Supervisor text changes).
9. **G12** `ProgressWatcher` (independent of everything above — could be
   done earlier if the silent-wait pain is the priority; placed here only
   because G1–G7 shorten the waits it announces).
10. **G8** display-window registry (largest; frontend-heavy; last so
    everything above ships even if this needs iteration).
11. Tests, CLAUDE.md, §6 status.

## 3. Tests

| Test | Pins | File |
|---|---|---|
| `test_radar_uses_api_path_not_constructed_ts` | G1: URL from `path`, `ts` kept for display only | `test_mcp_web_logic.py` |
| `test_radar_missing_path_falls_back_to_constructed` | G1 fallback | `test_mcp_web_logic.py` |
| `test_selfedit_confirm_replays_staged_goal` | G2: stored goal used, not the confirm call's text | `test_mcp_selfedit_logic.py` |
| `test_selfedit_stale_staging_id_errors_honestly` | G2: TTL error names real state | `test_mcp_selfedit_logic.py` |
| `test_selfedit_stateless_confirm_still_works_with_warning` | G2 deprecation window | `test_mcp_selfedit_logic.py` |
| `test_upgrade_agent_prompt_carries_repo_map` | G5 | `test_upgrade_agent.py` |
| `test_repo_map_helper_shared_not_duplicated` | G5: one implementation | `test_upgrade_agent.py` |
| `test_halfway_checkpoint_injected_at_half_budget_zero_edits` | G6 | `test_upgrade_agent.py` |
| `test_zero_edit_exhaustion_names_convergence_not_limit` | G6 error text | `test_upgrade_agent.py` |
| `test_selfedit_status_carries_planner_model` | G7 | `test_admin_selfedit.py` |
| `test_supervisor_prompt_states_single_selfedit_slot` | G9 | `test_prompts.py` |
| `test_display_registry_new_window_per_payload` | G8 | web (vitest or type-level; match existing web test approach) |
| `test_display_registry_cap_closes_oldest_visibly` | G8 | web |
| `test_no_update_when_work_finishes_under_30s` | G12: the headline requirement — a run completing at T+29 speaks nothing | `test_progress_watcher.py` |
| `test_first_update_at_30s_then_every_30s` | G12 interval, first tick never at T+0 | `test_progress_watcher.py` |
| `test_update_text_is_canned_never_model_generated` | G12: no LLM in the path (greps the module for a client/completions import, same shape as `test_module_imports_nothing_that_executes`) | `test_progress_watcher.py` |
| `test_update_reports_real_tool_counts` | G12: values come from run-log counters, not invented | `test_progress_watcher.py` |
| `test_concurrent_runs_produce_one_aggregated_update` | G12: three in-flight delegations → one utterance | `test_progress_watcher.py` |
| `test_sidecar_job_alone_still_updates` | G12's wrinkle: a self-edit running with NO in-flight delegation still speaks | `test_progress_watcher.py` |
| `test_tick_skipped_while_user_speaking` | G12: skipped, never queued | `test_progress_watcher.py` |
| `test_uses_tts_frame_not_context_injection` | G12: must not trigger an LLM turn (the reminders-watcher path is wrong here) | `test_progress_watcher.py` |
| `test_progress_updates_kill_switch` | G12 | `test_progress_watcher.py` |

## 4. Acceptance (Larry runs; results to §6)

1. Ask for Spartanburg weather → radar renders actual tiles over the
   basemap (no broken images; DevTools-free check: tiles visibly load).
2. Start a self-edit by voice: preview is SPOKEN before any approval is
   requested; approving references what was just previewed; a deliberate
   1-minute wait then "yes" still executes (staging TTL is 10 min).
3. A deliberately vague multi-file goal ("redesign the display windows")
   → developer asks for a plan/file list instead of launching.
4. During a kimi-k3 self-edit, the Agents card shows the planner profile.
5. Ask "can you run two self-edits at once" → honest "one at a time".
6. Multiple weather/research questions in a row → separate stacked
   windows, each closable individually; 7th window closes the oldest
   with a visible notice.
7. `RUN_LIVE=1 python -m tests.evals.routing_eval` ≥ 90% (Supervisor
   prompt changed in G3/G9/G10).
8. **G12 — the two halves of the requirement, checked separately.** Ask
   something quick ("what time is it") → it answers with NO progress
   line. Then start a self-edit → a spoken update lands ~30s in and
   roughly every 30s after, each one naming real elapsed time and tool
   counts, and none of them talks over you mid-sentence. Confirm the
   spoken numbers match what the Agents-tab activity ticker shows for the
   same run — they read the same source, so a mismatch means a real bug.

## 5. Self-audit

- **G2 vs barge-in survival**: the staging record lives in the SIDECAR,
  not the voice loop, so a cancelled turn cannot orphan it; a detached
  confirmation delegation reads it by id exactly as detached git confirms
  read `actions` rows. No new interaction with `late_delivery`.
- **G3 depends on G2** — sequenced after it; the sidecar refusal only
  activates post-deprecation so a mid-rollout session doesn't hard-break.
- **G5 must not fork the injection code** — extract the developer-loop's
  read/cap/skip logic into one shared function; `test_repo_map_helper_
  shared_not_duplicated` pins it. An implementer copying the six lines
  instead would recreate the two-implementations failure this repo keeps
  fixing.
- **G6's checkpoint vs legitimate long orientation**: advisory at half,
  honest at end — it never aborts. The failure it prevents is silence,
  not slowness.
- **G8's cap vs "never close automatically"**: Larry said windows close
  manually. The cap is a bounded exception with a visible notice,
  justified in G8; an implementer must keep the notice — silent oldest-
  close would violate the stated requirement in spirit.
- **G8 vs G2–G6**: deliberately NOT built via self-edit. The convergence
  machinery gets validated on smaller work; the user-visible feature
  doesn't gate on it.
- **G11 explicitly declines mechanical enforcement** — that is the
  decision, not an omission; do not bolt on a diff-prose matcher.
- **Prompt budget risk (G3/G9/G10/G6)**: prompts.py changes touch
  Supervisor + developer sections; re-check `test_no_agent_prompt_is_
  mostly_boilerplate` (1200) and the developer-sections pins (<1100 core)
  before assuming room, as the Gate V2 plan's F9 had to trim once already.
- **Radar fallback (G1)**: keeping the constructed-URL fallback means a
  future RainViewer change could silently degrade again — accepted,
  because the payload's `ts` + a failed tile is visible in the UI, and
  refusing radar entirely on a missing field is the worse failure.
- **G12 vs the interruption machinery**: `TTSSpeakFrame` produces no
  `LLMFullResponseStartFrame`, so the InterruptionNotifier (which arms on
  exactly that frame, after the 2026-08-22 false-arming fix) cannot
  mistake a progress line for a reply worth "resuming". An implementer
  must NOT switch this to the context-injection path to get nicer
  phrasing — that reintroduces both the LLM cost and the false-arming
  class of bug.
- **G12 vs the speaker gate**: progress updates are bot OUTPUT, so the
  gate is unaffected; but they do occur while the bot is "speaking", and
  `SpeakerVerifiedMinWordsTurnStartStrategy` gates interruptions during
  bot speech. A user interrupting a progress line still needs min_words +
  a passing speaker score, which is correct and unchanged — worth stating
  because a 30s cadence makes "bot is speaking" a much more common state
  than it used to be, so any latent bug in that path will surface more
  often after this ships.
- **G12 vs G6's checkpoint**: both make a stalling run legible, at
  different audiences — G6 tells the AGENT to converge or explain, G12
  tells LARRY it is still alive. Neither substitutes for the other, and
  they read the same underlying counters, so they cannot disagree.
- **G12's 30s constant vs long runs**: 20 updates on a 10-minute run is
  the accepted v1 cost of taking the stated requirement literally. Noted
  here so a future reader sees it was a decision, not an oversight.
- **G12 aggregation vs per-agent detail**: one line for N runs loses
  per-agent granularity by design — the Agents tab already shows per-run
  detail visually, and voice is the wrong channel for three simultaneous
  progress streams.

---

## 6. Implementation status

All of G1–G12 implemented 2026-08-22 in this session, in the plan's own §2
order. Full backend suite green (`pytest tests/unit tests/integration`:
1577 passed, 3 skipped, 1 failure — `test_mcp_web_server`, a live-network
integration test that cannot reach Weather.gov/Open-Meteo from this
sandbox, pre-existing and unrelated). Frontend verified via `tsc -b`
(clean) and `oxlint` (0 errors, pre-existing unrelated warnings only);
`npm run build`'s vite bundling step hits the same pre-existing sandbox
`dist/` EPERM artifact documented in MORTIMER_WEATHER_FAHRENHEIT_AND_
RADAR_PLAN.md §6 — Larry should run `npm run build` on his machine to
confirm the production bundle.

- **G1**: `mcp_servers/mcp_web/logic.py`'s `get_weather_radar` now builds
  tile URLs from `frame["path"]`, falling back to the old constructed form
  only when `path` is absent; `ts` is display-only. Tests:
  `test_radar_uses_api_path_not_constructed_ts`,
  `test_radar_missing_path_falls_back_to_constructed` in
  `test_mcp_web_logic.py`.
- **G4**: already applied (recorded, verified via `test_upgrade_agent.py`).
- **G5**: extracted `jarvis/repo_map.py`'s `load_repo_map_suffix()` — the
  ONE read/8000-char-cap/skip-if-missing implementation — used by both
  `SubAgent.__init__` (`jarvis/agents/base.py`, `inject_repo_map: true`
  path) and `UpgradeAgent.__init__` (unconditional, so `AppBuildAgent`
  gets it for free via inheritance). `REPO_MAP_MAX_CHARS` moved to the new
  module; `jarvis.agents.base.REPO_MAP_MAX_CHARS` re-exported for
  backward-compat test references. Path resolution is call-time (reads
  the module's own `__file__` global), not a module-level constant, so
  tests can monkeypatch `jarvis.repo_map.__file__` — three existing
  `TestRepoMapInjection` tests in `test_subagent.py` retargeted from
  patching `jarvis.agents.base.__file__` accordingly. New tests:
  `test_repo_map.py` (4 tests, the shared helper in isolation),
  `TestRepoMapInjection` in `test_upgrade_agent.py` (2 tests). Fixed
  fallout: `test_app_build_agent.py`'s exact system-prompt-equality
  assertions needed an autouse fixture pointing the loader at a
  `docs/REPO_MAP.md`-less path, so those tests don't depend on this real
  checkout's file contents.
- **G2**: sidecar (`jarvis/admin/server.py`) gained `POST
  /api/selfedit/stage` (in-process `_selfedit_stagings` dict + lock,
  `SELFEDIT_STAGING_TTL_S = 600`, pruned lazily on stage/run calls) and
  `GoalIn.staging_id`; `POST /api/selfedit/run` prefers a valid
  `staging_id` (single-use — popped on success), falls back to the bare
  `{goal, profile}` form with a `selfedit_run_stateless_confirm` warning
  log line. `mcp_servers/mcp_selfedit/logic.py`'s `selfedit_start` calls
  `/api/selfedit/stage` on `confirm=false`, returns `staging_id` in the
  summary; `confirm=true` with a `staging_id` skips the models lookup
  entirely and replays the sidecar's stored record. 18 tests in
  `test_admin_selfedit.py` (staging endpoint, replay, single-use
  consumption, unknown/stale id honest errors, bare-form back-compat, and
  confirming staging alone doesn't start a run), plus new/updated tests in
  `test_mcp_selfedit_logic.py`.
- **G3**: Supervisor rule 9 gained the "never solicit approval before a
  preview has been relayed" sentence plus the staging_id-naming
  instruction for self-edit confirmations specifically. The sidecar's
  mechanical refusal (unknown/expired staging_id → explicit error, never
  a silent start) is already live as part of G2's `POST /api/selfedit/run`
  — there is no separate "post-deprecation-window" gate to add later since
  the refusal path already exists for any `staging_id` that doesn't
  resolve; the bare stateless form remains the explicitly-permitted
  one-release fallback, not a thing G3 needs to further restrict.
- **G6**: developer `self_development` prompt section gained the
  plan_path/named-files requirement for multi-file goals (and, sharing the
  same edit, the G11 commit-honesty sentence). `UpgradeAgent.run()` gained
  a halfway checkpoint (`iterations_used == cfg["max_iterations"] // 2`
  with zero `self.service.proposals`, injects one forcing system message,
  fires at most once via the equality check) and an exhaustion-summary
  override naming "never converged on a first edit" instead of the bare
  iteration-limit message, scoped to natural budget exhaustion with zero
  proposals only (time-limit and validation-failure exits already have
  their own summaries). 4 new tests in `test_upgrade_agent.py`.
- **G7**: `mcp_selfedit`'s `selfedit_start`/`selfedit_status` results now
  echo a `planner_model` field (mirroring the existing `profile` value).
  `jarvis/bot/pipeline.py`'s `agent_tool_result` handler parses it off
  those two tools' results and rides it on the existing per-call
  `agent_activity` app-message (no new message type). Frontend:
  `RunState.plannerModel` (agentRuns.ts, sticky — never cleared by a later
  call that didn't report one) and a second, visually distinct chip on the
  Agents-tab card (`.agent-card-planner-model`, accent-colored, ⚙ prefix)
  alongside — never replacing — the existing dispatch-model chip. 4 new
  backend tests in `test_agent_events.py`; frontend verified via `tsc -b`.
- **G9/G10/G11**: batched into one Supervisor rule 12 (single self-edit
  slot; no wait/timer primitive, routes to answer-now/ask-again/scheduler)
  plus the G11 commit-honesty sentence folded into G6's
  `self_development` edit. `test_rule_12_single_selfedit_slot_and_no_wait_
  primitive` and `test_developer_prompt_forbids_unwritten_commit_claims`
  in `test_prompts.py`. G11's `prepare_commit` half needed no code change:
  `mcp_git.logic.prepare_commit`'s draft summary already lists
  `st['changed_files']` from `git_status()` (mechanically, independent of
  the message text) — confirmed by reading the existing implementation
  rather than assumed. No mechanical diff-vs-message analyzer was built,
  per the locked decision.
- **G12**: new `jarvis/bot/progress_watcher.py` — `ProgressWatcher` (same
  start/stop/`_run`/`tick_once` shape as `PlanWatcher`, but a REPEATING
  ambient ping rather than a one-shot per-transition announcement) and
  `SpeakingStateTracker` (a small task observer, same D-007/Phase-3
  pattern as `InterruptionNotifier`, tracking Bot/UserStarted/
  StoppedSpeaking frames). Polls `jarvis.runlog.store.list_runs(status=
  "running")` (session-scoped) for in-flight delegations and the sidecar's
  `GET /api/selfedit/run` for a running self-edit job; aggregates
  everything in-flight into ONE canned `TTSSpeakFrame` line per tick,
  entirely from counters (tool_count, last tool from `agent_events`,
  planner profile) — no LLM in the path. Wired into
  `run_session` beside `plan_watcher`, kill switch
  `JARVIS_PROGRESS_UPDATES_ENABLED=false`. 18 tests in
  `test_progress_watcher.py`.
- **G8**: `web/src/displayWindow.ts`'s single `latest` payload became a
  panel registry (`panels: DisplayWindowPanel[]`, `MAX_OPEN_DISPLAY_
  PANELS = 6` with oldest-eviction + a visible auto-fading toast notice,
  `subscribePanels`/`closePanel`/`popOutPanel`/`restoreLatestAsPanel`
  exports). `DisplayPanel.tsx` is now a container rendering the full
  panel stack via an extracted `SingleDisplayPanel` subcomponent (its own
  position/size/close, cascade-offset by index). **Scope note, found
  during implementation and not overridden without saying so**: true
  per-panel POP-OUT into independent OS windows is not built — there is
  exactly one physical external popup (`popoutWindow.ts`'s
  `createPopoutChannel`), and the Mac shell's native side only recognizes
  three fixed roles (console/display/drawer — see `popoutWindow.ts`'s
  `open()`, `entry.role` is the contract), so a per-panel id could never
  reach it without shell changes explicitly out of this plan's scope.
  "Pop-out works per-panel" is implemented as: popping out any specific
  in-page panel sends THAT panel's payload to the one external window and
  removes it from the in-page stack — each panel individually chooses to
  graduate to the second screen, but only one panel's content is ever on
  that screen at a time, same as before G8. D41's mandatory fallback (a
  result must never be silently lost to a popup close/block) is preserved
  via `restoreLatestAsPanel()`, called when the container's existing 1s
  popup-liveness poll detects a falling edge. No JS test runner exists in
  this repo (no vitest/jest configured) — verified via `tsc -b` (clean)
  and `oxlint` (0 errors) only, consistent with how the weather plan's
  frontend work was verified in the absence of one; Larry should
  exercise the acceptance step 6 scenario by hand.

Deviations from the plan's exact test list (§3): the web tests
(`test_display_registry_new_window_per_payload`,
`test_display_registry_cap_closes_oldest_visibly`) were not written as no
JS test infra exists — covered instead by `tsc -b`/`oxlint` plus the
manual acceptance step. `test_selfedit_confirm_replays_staged_goal` /
`test_selfedit_stale_staging_id_errors_honestly` /
`test_selfedit_stateless_confirm_still_works_with_warning` landed as
differently-named but equivalent tests across `test_admin_selfedit.py`
and `test_mcp_selfedit_logic.py` (the sidecar owns staging state, so most
of the substantive coverage sits there rather than in the MCP-layer
tests). `test_repo_map_helper_shared_not_duplicated` wasn't written as a
standalone test — the shared-implementation property is structural
(`grep` confirms exactly one `load_repo_map_suffix` definition, called
from both `base.py` and `upgrade_agent.py`) and is exercised indirectly by
every repo-map test in both `test_subagent.py` and `test_upgrade_agent.py`
passing against the same function.

Not yet done: acceptance steps 1–8 (§4) need Larry's own machine/voice
session — routing eval (step 7) in particular needs a live LLM call this
sandbox cannot make.
