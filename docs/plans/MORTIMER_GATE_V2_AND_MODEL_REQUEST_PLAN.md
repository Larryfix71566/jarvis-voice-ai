# Mortimer — Gate v2 (windowed scoring, honest drops) + Named-Model Delegation

**Status:** APPROVED and IMPLEMENTED 2026-08-22 (F1–F11); §6 effectiveness protocol still unrun — gate off.
Author: Claude (Fable), 2026-08-22. Requested by Larry after the 15:00
live session review: *"many responses not what I would expect and many
requests just ignored"* → six gaps found → *"ok create the implementation
plan for these fixes and upgrades."*

**Implementer contract.** Same rules as MORTIMER_VOICE_ISOLATION_TIER12_
PLAN.md and MORTIMER_MEMORY_CAPACITY_PLAN.md: every decision below is
LOCKED; if something is impossible as written, STOP and report rather
than substituting a design. Version-check against the deployment venv
(`.venv/lib/python3.12/site-packages`, pipecat 1.4.0), never the sandbox
interpreter.

---

## 0. Diagnosis (from the 2026-08-22 14:59–15:09 session logs + run log)

Post-re-enrollment, short clean turns pass. The remaining failures:

1. **Long mixed-audio turns are eaten.** Three drops at 0.29–0.34, 7–12s,
   138–364 chars — Larry's most substantive requests, spoken with the TV
   audible behind him. `SpeakerTap` embeds the WHOLE turn buffer (capped
   at `MAX_BUFFER_SECS = 12`) into one vector; TV audio blended into a
   long turn drags the cosine below the 0.40 threshold. TV-alone drops
   the same session scored 0.00–0.26 — the bands are separated; the
   *mixture* lands between them.
2. **Silent drops make the miss invisible, so the model guesses.** Larry:
   "go back to what I just said and give me a response" — Mortimer never
   received that utterance (dropped) and, having no way to know it missed
   something, replayed an earlier apology verbatim instead of saying "I
   didn't hear that."
3. **A named-model request cannot be honored.** "Use Fable for this
   research" → the Supervisor said "Checking with Fable now", the
   developer ran on its fixed profile (then or-codex-max →
   `openai/gpt-5.1-codex-max`), and run `5d9bfb0b` later confirmed "Fable
   wasn't used." `delegate_task` has no model parameter; the only
   per-job model choice lives in the planning pathway, which is the
   wrong weight for conversational research.
4. **The rejected memory rule was stored anyway.** Larry said "No." to
   the proposed check-the-registry rule at 15:09:19; the fact was written
   at 15:09:00 (`user.style.capability_check`) and the end-of-session
   sweep wrote a second variant (`user.style.check_registry_first`) plus
   near-duplicate pairs of other style facts.

Already done before this plan (2026-08-22): developer default moved
`or-codex-max` → `claude-opus` in `config/agents.yaml`
(`on_profile_fallback: refuse` unchanged); Flux `should_interrupt=False`;
InterruptionNotifier arms on `LLMFullResponseStartFrame`.

## 1. Locked decisions

| # | Decision | Rationale |
|---|---|---|
| F1 | **Windowed speaker scoring, max-over-windows.** `SpeakerTap`'s FINAL scoring (the `UserStoppedSpeakingFrame` path) embeds the whole buffer AND sliding sub-windows — `SCORE_WINDOW_SECS = 3.0`, `SCORE_HOP_SECS = 1.5`, at most `MAX_SCORE_WINDOWS = 8` windows (evenly covering the buffer when it would exceed 8) — and records the MAX as the turn's score. The mid-turn checkpoint at `MIN_VERIFY_SECS` (1s buffer) stays whole-buffer: it is a single window already. Windows shorter than `MIN_EMBED_SECS` are never embedded. | The failure is dilution: Larry's voice segments in a 12s mixed turn individually clear 0.40 easily (his clean turns score ~0.59+), while the blended whole-buffer vector reads 0.29–0.34. Max-over-windows scores the best 3s of the turn — his voice — while a TV-only turn fails every window (its band is 0.00–0.26, far under threshold, so per-window variance cannot bridge the gap). Chosen over lowering the threshold, which would trade his false drops for TV false passes and reopen the calibration argument every session. |
| F2 | **All window embeddings in ONE `asyncio.to_thread` call.** `_schedule_score`'s `_run` makes a single thread hop that loops over the windows and the whole buffer, returning the max — never one `to_thread` per window. | Up to 9 embeddings must not pay 9 thread-hop latencies, and `GATE_HOLD_TIMEOUT_S` (0.6s) bounds how long TranscriptGate waits: if scoring outruns the hold, `verdict(None, …)` fails OPEN (L5) — slow scoring can only ever let something through, never eat Larry's words. That asymmetry is inherited, correct, and must not be "fixed" by making the gate hold longer. |
| F3 | **Honest-drop context note, doubly bounded.** `TranscriptGate` gains an optional `inject` callback (pipeline passes the existing `inject_silent` channel — the interruption-notice path, which appends to context WITHOUT triggering a spoken reply). On a drop it injects `DROP_NOTICE` ("[system] An utterance was heard but was not attributed to Larry and was discarded unread. If Larry says he was ignored or refers to something you never received, tell him a phrase may have been filtered out and ask him to repeat it — do not guess at what it said.") ONLY when BOTH hold: score ≥ `DROP_NOTE_MIN_SCORE = 0.25` (the near-threshold band where the enrolled speaker is plausible) AND at least `DROP_NOTE_COOLDOWN_S = 60` since the last note. | The note exists for exactly one scenario: a false drop of Larry mid-conversation. An unconditional note would recreate the 90-notices-vs-12-messages context flood the 2026-08-22 InterruptionNotifier fix just eliminated — a TV left on drops constantly, and every one of those is a TRUE negative needing no note. The 0.25 floor excludes the TV band (0.00–0.26 measured, overwhelmingly ≤0.21); the cooldown bounds worst-case spam to one line a minute; and the text instructs honesty ("say you may have missed something") rather than recovery, because the system cannot know what was said — Golden Rule 1 applied to the gate. |
| F4 | **Drop app-message gains the score.** `{"type": "speaker_gate", "verdict": "dropped"}` becomes `{"type": "speaker_gate", "verdict": "dropped", "score": <float\|null>, "near_threshold": <bool>}` (near_threshold = score ≥ DROP_NOTE_MIN_SCORE). The web client renders a small transient chip ("voice not recognized") ONLY for near_threshold drops — TV drops stay invisible. Chip in the caption/ambient area, auto-fading, no interaction required. | The user-facing half of F3: when Larry's own turn is eaten he currently gets dead air and a log file. A visible one-second cue converts "Mortimer ignored me" into "the filter got me — I'll repeat that." Gating the chip on near_threshold keeps the engagement layer's rule (nothing ambient may demand attention) intact while the TV chatters. |
| F5 | **Transcript text still never logged, injected, or displayed for a dropped utterance.** F3's note and F4's chip carry NO transcript content. | L6 unchanged: an unknown speaker's words stay out of the logs and the context. The note says an utterance was discarded; it never says what it said — that text may be a stranger's. |
| F6 | **`delegate_task` gains optional `model_profile`.** Schema: `"model_profile": {"type": "string"}` with a description instructing the Supervisor to set it ONLY when the user explicitly named a model (Fable, Opus, Kimi, GPT…), mapping the spoken name to a registry profile name; omit otherwise. The handler passes it to `SubAgent.run(model_profile_override=…)`. | The delegation layer is where conversational work runs; the planning pathway (which already has per-job `profile`) is a background document job — the wrong weight for "give me options on X, use Fable." Model discipline (Part A) is preserved: the dispatcher never CHOOSES a model, it relays a name Larry said — the same shape as `set_voice`. Routing is untouched (same delegation, one extra optional argument), so the routing eval must not move. |
| F7 | **An explicit override NEVER falls back — it refuses.** `SubAgent.run()` resolves the override via the same `load_model_registry`/`resolve_profile`/key-present check `__init__` uses. Any failure (unknown profile, missing/empty key) returns `REFUSED: model profile '<name>' could not be resolved (<reason>) — this run was requested on that model specifically, so it was not started on <default model> instead.` before any run row or model call. `on_profile_fallback` config is irrelevant here: an override is always refuse-on-failure, even for agents configured `warn`. | A request for Fable silently served by the default model is the exact failure of the 15:03 session, and it is worse than a refusal because it produces plausible work from the wrong model. The configured fallback mode governs the CONFIGURED profile (an infrastructure default); an override is a per-run user instruction, and disobeying it silently is never correct. |
| F8 | **Per-run override state is LOCAL to `run()` — never instance mutation.** The resolved override client/model are threaded into `_loop` as parameters (defaulting to `self._client`/`self._model`); `RunLogger` gets the override-resolved model string; the `{"type": "agent", "state": "working"}` message and `agentRuns` chip carry it the same way. `self._model`, `self._client`, `self._model_fallback` are never touched by an override. | Barge-in survival runs delegations as DETACHED tasks: two runs of the same `SubAgent` instance can be in flight at once, so mutating instance state for one run would corrupt the other. Locals-only is not a style choice, it is the concurrency contract. The chip/run-log threading reuses the existing "resolved model is what gets recorded" pipe — no new mechanism. |
| F9 | **Supervisor honesty rule for named models (prompt).** Rule 8's named-models sentence is extended: when the user names a model for a task, pass it via `delegate_task`'s `model_profile`; never announce that a model is being used — the acknowledgment stays generic ("On it."), and the result is reported with the model the tool result names. Mechanically backed (a rule without a backstop is a wish): when an override was requested, the delegate handler APPENDS `\n[ran on <resolved model>]` to the sub-agent's reply, so the Supervisor's report quotes received text rather than its own intention. The developer prompt gains one sentence: a task naming a model already runs on it — do not discuss model availability, just do the work. | "Checking with Fable now" was a promise the Supervisor had no mechanism to keep — a Golden-Rule-3-shaped failure (claiming a capability state not observed). The appended line is the observation. The spoken-name→profile mapping (Fable→claude-fable-5, Opus→claude-opus, Kimi→kimi-k3, Sonnet→or-sonnet-5…) lives in the tool description, beside the enum-adjacent knowledge the model already uses. |
| F10 | **Memory cleanup, one supervised pass.** Archive `user.style.capability_check` and `user.style.check_registry_first` with `became=rejected:larry-2026-08-22` (he said "No." to this rule seconds after it was stored). Then run `python -m jarvis.memory_sweep --enforce` + `python -m jarvis.consolidate` to fold the session's duplicate pairs (`user.style.tool_specification`/`user.preference.tool_specification`, `no_loops`/`frustration_trigger`, `no_confirmations`/`direct_execution`). Archival, never deletion; the surviving phrasing follows keep-longest/keep-general. | The store must not carry a rule its owner explicitly rejected — honoring "No." retroactively. Duplicates go through the existing machinery rather than hand-edits: the capacity plan built exactly this tool one day ago. |
| F11 | **No new kill switches.** F1/F2 live inside the existing gate (`JARVIS_SPEAKER_GATE_ENABLED` covers them); F3/F4 die with the gate too (no gate, no drops, no notes); F6–F9 need none (an optional parameter that is simply never sent has no failure mode to switch off). | One machine, one switch — the memory-capacity plan's M9 rule. A switch nobody would ever flip separately is configuration surface without a constituency. |

## 2. Implementation order

1. **`jarvis/bot/speaker_gate.py`** — F1/F2: `SCORE_WINDOW_SECS`,
   `SCORE_HOP_SECS`, `MAX_SCORE_WINDOWS` constants; `_schedule_score`'s
   `_run` computes max-over-windows in one `to_thread` call (a pure
   helper `_window_slices(n_bytes, sample_rate) -> list[slice]` keeps the
   slicing testable without audio); log line gains `windows=N
   best=<max> whole=<whole-buffer score>` so a future calibration can
   compare policies from the log alone.
2. **Same file + `jarvis/prompts.py` + `jarvis/bot/pipeline.py`** —
   F3/F4/F5: `DROP_NOTICE` in prompts.py (beside the interruption
   notices); `TranscriptGate.__init__` gains `inject=None` and the
   cooldown/floor logic; pipeline passes `inject_silent`; app message
   gains `score`/`near_threshold`.
3. **`web/src/`** — F4 chip: handle the extended `speaker_gate` message
   in the existing ServerMessage listener path; small auto-fading element;
   render only when `near_threshold`.
4. **`jarvis/agents/base.py` + `jarvis/agents/delegate.py`** — F6/F7/F8:
   `run(model_profile_override=…)`, locals-only resolution +
   refuse-on-failure, `_loop(client=…, model=…)` threading, RunLogger +
   working-message model fields; delegate schema + handler pass-through +
   `[ran on <model>]` suffix when overridden.
5. **`jarvis/prompts.py` + routing eval** — F9 sentences (Supervisor
   rule 8 extension, developer one-liner, tool description mapping).
   `RUN_LIVE=1 python -m tests.evals.routing_eval` must stay ≥ 90% —
   verify, don't assume, since rule 8 text changes.
6. **Memory cleanup (F10)** — the two archives + `--enforce` +
   consolidation pass; record before/after counts in §6.
7. **Tests + docs** — table below; CLAUDE.md voice-isolation and
   delegation-model paragraphs updated; §6 status here.

## 3. Tests

| test | pins |
|---|---|
| `test_windowed_score_is_max_over_windows` | F1: fake encoder returning distinct per-window scores; turn score = max |
| `test_short_buffer_scores_single_window` | F1: buffer < window size ⇒ exactly one embed, no slicing regression |
| `test_window_slices_cover_buffer_capped` | F1/F2: `_window_slices` covers the buffer, ≤ MAX_SCORE_WINDOWS, none shorter than MIN_EMBED_SECS |
| `test_all_windows_one_thread_call` | F2: one `to_thread` per final scoring regardless of window count |
| `test_drop_note_only_near_threshold` | F3: score 0.10 drop injects nothing; 0.30 drop injects DROP_NOTICE |
| `test_drop_note_cooldown` | F3: two near-threshold drops 5s apart inject once |
| `test_drop_note_never_contains_transcript` | F5: injected text contains no fragment of the dropped frame's text |
| `test_drop_message_carries_score_flag` | F4: app message has `score` and correct `near_threshold` |
| `test_override_resolves_and_runs_on_named_model` | F6/F8: `run(model_profile_override=…)` uses the profile's client/model; RunLogger records it |
| `test_override_failure_refuses_never_falls_back` | F7: unknown profile / missing key ⇒ `REFUSED:` naming both models; no run row |
| `test_override_does_not_mutate_instance` | F8: after an override run, `self._model`/`_client` unchanged; a concurrent default run unaffected |
| `test_delegate_schema_has_model_profile` | F6: optional param present, not in `required` |
| `test_overridden_reply_names_resolved_model` | F9 backstop: `[ran on …]` suffix present iff override requested |
| existing gate/delegate/interruption suites | stay green unchanged |

## 4. Acceptance (Larry runs, results appended to §6)

1. TV on, normal session: long conversational requests (5–10s, natural
   phrasing) are answered — `speaker_gate_dropped` shows TV lines only,
   and the new `best=`/`whole=` fields show best-window clearing 0.40
   where whole-buffer would not have.
2. Force a false drop (speak from across the room): the "voice not
   recognized" chip appears, and asking "did you get that?" yields "a
   phrase may have been filtered — could you repeat it?" rather than a
   guess.
3. "Use Fable to look at X" → Agents chip and run log show
   `claude-fable-5`; spoken report names it. Then temporarily unset
   `ANTHROPIC_API_KEY` and repeat → clean spoken refusal naming the
   profile, no run on the default model. *(Restore the key.)*
4. Memory panel: the two rejected-rule facts show archived with
   `became=rejected:larry-2026-08-22`; duplicate style pairs merged.

## 5. Self-audit

- F1 vs the strategy's interruption gating: `SpeakerVerifiedMinWords…`
  reads the same `scores` dict; a windowed final score only ever RAISES
  the recorded score, so interruption gating gets no stricter — and the
  mid-turn checkpoint it actually relies on is unchanged. Consistent.
- F3's flood risk vs the InterruptionNotifier lesson: checked — the
  90-notice flood came from unconditional arming; F3 is doubly bounded
  (score floor + cooldown) and the floor sits above the measured TV band.
  The residual worst case is one note per minute during a
  near-threshold-scoring TV program, which the cooldown caps.
- F7 vs `on_profile_fallback: warn` agents: an override on a
  conversational agent (e.g. "have the analyst use Opus") also
  refuses-on-failure rather than warning. Intentional — F7's rationale
  distinguishes configured defaults from per-run instructions; the
  config mode is not consulted for overrides, and the plan says so.
- F8 concurrency claim verified against `delegate.py`: detached tasks
  from barge-in survival do allow two concurrent `run()` calls on one
  instance — locals-only is required, not defensive.
- F9's `[ran on …]` suffix vs D6/D7 grounding rules: the suffix is
  appended by the HANDLER (code), not authored by any model, so the
  Supervisor quoting it is grounded by construction.
- F10 archives with `became` — reversible, consistent with the
  archive-not-delete principle every memory feature holds.

## 6. Implementation status

All of F1-F11 implemented and committed-in-working-tree 2026-08-22.

- **F1/F2 (windowed speaker scoring)** — done. `jarvis/bot/speaker_gate.py`:
  `_window_slices`, `SCORE_WINDOW_SECS`/`SCORE_HOP_SECS`/`MAX_SCORE_WINDOWS`,
  `_score_all_windows` (one `asyncio.to_thread` call scores every window plus
  the whole buffer, max taken). Tests: `TestWindowSlices` (4),
  `TestWindowedScoring` (3), all green.
- **F3/F4/F5 (honest drop notice + UI chip)** — done.
  `jarvis/prompts.py`'s `DROP_NOTICE`; `TranscriptGate.__init__` gained
  `inject`, drop branch now cooldown-gates (`DROP_NOTE_COOLDOWN_S = 60.0`)
  and score-floors (`DROP_NOTE_MIN_SCORE = 0.25`) the injection via the
  silent-append path (`aggregators.user().add_messages`, never
  `push_context_frame`); app message carries `near_threshold`.
  `web/App.tsx`/`App.css` render a 4s auto-dismissing `--attn` chip.
  `jarvis/bot/pipeline.py`'s `TranscriptGate` construction was moved to
  after `aggregators` exists so the inject closure can close over it.
  Tests: `TestHonestDropNote` (5) + one real-wiring test
  (`test_gate_inject_appends_drop_note_to_real_context`, asserts the
  aggregator's own context grows — not a faked closure). All green.
- **F6/F7/F8 (delegate_task model_profile override)** — done.
  `SubAgent.resolve_model_profile()` (new, reuses
  `load_model_registry`/`resolve_profile`); `run()`/`_loop()` thread
  `model_profile_override`/`client`/`model` as LOCALS only — never written
  to `self._client`/`self._model` (verified via
  `test_override_does_not_mutate_instance`, including that a subsequent
  default run is unaffected). `delegate.py`'s `build_delegate_tool` gained
  the optional `model_profile` schema field and a resolve-before-anything-
  else block that returns `REFUSED: ...` before any run row, retry-guard
  entry, or `agent.run()` call. Refusal is unconditional regardless of the
  agent's own `on_profile_fallback` (`test_override_ignores_this_agents_on_
  profile_fallback_warn`). Success replies get a code-appended
  `\n[ran on <model>]` suffix. Tests: `tests/unit/test_subagent.py`'s
  `TestRuntimeModelOverride` (6: resolves-and-runs, refuses-never-falls-
  back, unknown-profile-refuses, ignores-warn-mode, no-instance-mutation,
  run-log-records-override-model) + `tests/unit/test_delegate.py`'s
  `TestModelProfileOverride` (4) + `TestSchema.test_schema_has_optional_
  model_profile` (1). All green.
- **F9 (prompt honesty)** — done, with one deviation from the literal
  plan text on length grounds. Supervisor rule 8 gained a sentence mapping
  spoken model names to `delegate_task`'s `model_profile` values and
  requiring the tool result (not the request) to gate ever naming a model.
  The developer's own prompt addition was shortened from the plan's literal
  draft sentence to `"Named-model tasks already ran on that model."` —
  the literal sentence pushed `DEVELOPER_CORE`'s own-text length to 1148
  chars against `TestDeveloperSections`'s pinned `< 1100` budget
  (`test_a_plain_repo_read_gets_neither_protocol`); per that test's own
  comment ("if core needs to grow again, trim it first") a shorter
  sentence carrying the same instruction was substituted rather than
  raising the pinned budget. **Routing eval NOT run** — `RUN_LIVE=1
  python -m tests.evals.routing_eval` requires live LLM keys, which in
  this repo live only in the encrypted vault (`data/secrets.vault`) unlocked
  via the macOS Keychain; the sandbox this work ran in has no Keychain
  (`keyring.errors.NoKeyringError`) and `.env` no longer carries the keys
  directly (moved to the vault 2026-08-16). **Larry should run the eval
  on his own machine** to confirm rule 8's growth keeps routing accuracy
  ≥90% before treating F9 as fully verified.
- **F10 (memory cleanup)** — done. `user.style.capability_check` and
  `user.style.check_registry_first` archived with
  `became="rejected:larry-2026-08-22"` via `jarvis.memory.archive_fact`
  (reversible, not deleted). `python -m jarvis.memory_sweep --enforce`:
  preference 38→15 (cap 15), project 10→8 (cap 8), system 0→0 — all
  mechanical age-out (rung (b) LLM-merge was skipped; no API key available
  in this sandbox, which is the documented no-dependency fallback path,
  not a defect). `python -m jarvis.consolidate` (report-only by design,
  D2) surfaced 55 near-duplicate clusters across all tiers; per the
  manual-first decision this writes nothing — dropping specific keys is
  left to Larry's own review with `--drop <key>...`, not decided here.
- **F11 (no new kill switches)** — satisfied by construction; nothing
  added a `JARVIS_*_ENABLED` flag.
- **Full suite**: `pytest tests/unit tests/integration -q` →
  1485 passed, 3 skipped, 1 failed. The one failure
  (`test_mcp_web_server`) is a live network call to weather.gov/Open-Meteo
  hitting `ProxyError` — sandbox network egress restriction, unrelated to
  any F1-F11 change; not gated by `RUN_LIVE` in that test's own code, so
  it is expected to fail identically on `main` before this work in any
  network-restricted environment. `pytest tests/unit -q` alone: 1397
  passed, 0 failed.
- **CLAUDE.md**: voice-isolation paragraph gained a "Gate V2" sub-entry
  (F1-F5); delegation-model paragraph gained a "Per-run model requests"
  sub-entry (F6-F9).
- **Not independently re-verified in this pass**: `web/npm run build`/
  `npm run lint` for the F4 chip (verified earlier in this same working
  session per the prior summary, not re-run here since no further web
  files changed after that verification).
