# What is left, and what closes each

State at `9e11625` on `docs/wave-and-agent-recovery`, 2026-09-16. Twelve
items. Two are decisions,
two are investigations, three need one hardware run each, one needs
re-specifying, two are someone else's call, and one is a defect with a
measured cause.

Items 10 and 11 were added by Larry on 2026-09-16 from daily driving, not
from the plan. They outrank items 1-9: both are in the interface he is now
using every day.

---

## 1. Step 7 — delete the D8 band-aid — DECISION

**What it is.** `AudioInputCoordinator` repoints the system default input to
a rate-matching mic before connecting, to dodge the AirPods 24 kHz
slow-voice bug. D8 says remove it, with `JARVIS_MATCH_INPUT_RATE` and the
input-notice chip, once the native path is the default.

**Why it is still open.** It is gated to `transport is DirectWebRTCTransport`
(JarvisClient.swift:238), so it runs *only* on the rollback path — which §9
has now proven works and which exists precisely for when the native path
misbehaves. Deleting it takes the flag too, so a rollback on AirPods
reinstates the original bug with nothing left to restore the fix.

**To close.** Choose one:
- *Full deletion, per the plan.* `AudioInputCoordinator.swift` +
  `AudioInputChange`, `JarvisFlags.matchInputRate`
  (JarvisConfig.swift:133), `JarvisClient`'s `audioInputChange` /
  `audioInputCoordinator` / connect-path call / `restore()`,
  `AppMessageRouter`'s `audioInputSink`, `UICommandRouter`'s
  `audioInputNotice` + `showAudioInputNotice`, `OrbFieldView`:184 and :244,
  and the `AudioOutputTests` block at lines 53–91. Plus the P0
  preservation-checklist entry. One commit, revertible.
- *Partial.* Delete the flag and the notice UI; keep the coordinator running
  unconditionally on the WebRTC path. Needs a D8 amendment saying why.

Either way it is one commit. Nothing else depends on it.

## 2. `layoutVersion` default — CORRECTION: it is C9.5, gated on C8

**This entry was wrong as first written.** It said "No plan step covers
flipping it, so it would have stayed hidden indefinitely." The closure plan
covers it three times:

- **L4:** "Deployment target: `main` + installed on the MacBook Air with
  adaptive layout ON by default. `mortimer.interface.layoutVersion` defaults
  to `1` after acceptance."
- **G30** (gap register): "Adaptive layout off by default (L4)" → closure
  item **C9.5** → "Default flipped in its own PR after C8".
- C9 ladder item 7 spells out the change: default `1`, keep
  `Debug ▸ Use previous layout`, update both plans' status headers,
  `CLAUDE.md` and `docs/REPO_MAP.md`.

So the default being 0 is deliberate, tracked and sequenced — not an
oversight.

**What actually stands in front of it: C8 has not started.** C8 is an
integrated acceptance pass on the deployment Mac with five requirements —
the P0 preservation matrix exercised in *both* legacy and adaptive modes,
the §9.2 visual cases at five sizes, §9.3 real audio on the C0.4
paired-trial protocol, §9.4 monitor and rollback cases, and an independent
C5 receipt for the exact commit. Gate G-C8 requires every row to carry
positive evidence, or to be named in `C8-open-items.md` with Larry's written
acceptance as a known limitation.

Evidence it is unrun: `P0-preservation-checklist.md` has no exercised rows,
and `C8-open-items.md` does not exist.

**Why the gate is the right shape.** Flipping the default gives the adaptive
layout to everyone who launches the app, and the preservation matrix is
precisely the instrument for establishing that everything the previous
layout could do, the new one still can. Defaulting it on beforehand is the
class of regression that checklist was written to catch.

**To close.** Two separable things, and conflating them is what made this
look like an oversight:
- *Using* the adaptive layout needs no gate and is already done —
  `Debug ▸ Preview adaptive layout`, which persists per user. One menu
  press. That was the thing actually wanted.
- *Defaulting* it is C9.5 behind C8. Either run C8, or take the plan's own
  escape hatch: flip it and record the unexercised rows in
  `C8-open-items.md` with written acceptance. The second is legitimate under
  Gate G-C8, but it should be a deliberate choice rather than a shortcut
  taken by someone unaware the gate existed.

## 3. The rebuild churn — ONE HARDWARE RUN

**What it is.** On 2026-09-14, two device changes produced **six** engine
rebuilds in 3.4 s, each costing ~700 ms of dead audio — about 3.5 s where
0.7 s was needed.

**Where it stands.** Instrumented: the configuration-change observer now
logs the current device signature against the one the running graph was
built with, and prints `— NO DEVICE DIFFERENCE` when they match. Three
later sessions did not reproduce it, and in those both changes were
genuine, so the "our own rebuild provokes the next notification"
hypothesis is **unsupported**. The difference is what was done to the
hardware: the churn followed an earbud being physically removed (input
alternating 1 ch / 2 ch), not a Settings switch.

**To close.** One session, connect, then **pull an earbud out** — not a
Settings change. Then read the signature lines:
- all `NO DEVICE DIFFERENCE` → skipping those notifications is safe, and the
  fix is a two-line guard in the observer.
- signatures genuinely differ → it is the hardware settling, there is
  nothing to fix, and it gets recorded as expected behaviour.

## 4. The input channel's observation count — INVESTIGATION

**What it is.** Input observations per session: 1568, 840, **76**, 959. The
76 came from an 87 s session whose capture path delivered ~100 buffers/s —
roughly 8,700 buffers producing 76 accepted observations. `shown` equalled
`arrivals` exactly, so every entry was fresh; the accumulator simply had
nothing to hold most of the time.

**Why it matters.** The C7.5 gate now reads input arrival p95, so the figure
it depends on rested on a 76-sample base once. A gate is only as good as
the sample under it.

**To close.** Not a measurement — a code read plus one instrumented run.
`AudioActivityAccumulator` refuses observations on watermark, 300 ms
staleness and mute-eligibility rules; none obviously explains a 97%
rejection rate on a live capture path. Log the refusal reason per rejected
observation, run one session, count by reason. That says whether it is a
defect or correct behaviour nobody had quantified.

## 5. 24 kHz steady state — OPPORTUNISTIC RUN

**What it is.** AirPods negotiate either rate between sessions: 24 kHz
(480-frame buffers, 20 ms, input arrival p95 41.9 ms) or 48 kHz (10 ms,
23.5 ms). The steady-state gate has only been measured at 48 kHz.

**Why it matters.** 41.9 ms is the closest any healthy measurement has come
to the 50 ms gate. If 24 kHz is the normal case for some configuration, the
threshold has less headroom than it appears.

**To close.** A no-device-change AirPods session that happens to come up at
24 kHz — the engine log line says which. What *determines* the rate is not
known; until it is, this is repeat-until-observed rather than a test that
can be asked for.

## 6. §3.4 latency parity — RE-SPECIFY, THEN TWO SHORT RUNS

**What it is.** The plan wants native vs WebRTC latency compared, gated on a
C0.4 WebRTC baseline that was never captured.

**Why it cannot be done as written.** The client meter needs
`AudioLevelSource`, which only `NativeAudioTransport` implements —
`DirectWebRTCTransport` cannot, since this WebRTC build exposes no audio
renderer. So there is no client-side WebRTC latency to compare against, and
no amount of running produces one.

**To close.** Use the server-side turn metric instead, which the pipeline
emits transport-agnostically: `TURN user_end->first_audio`. The WebRTC
session on 2026-09-15 already produced 899, 1379 and 1431 ms. Two short
matched sessions — same device, same kind of question — give the comparison
the plan actually wanted. Amend §3.4 to name that metric.

## 7. §3.3 echo on AirPods — TWO BENCH RUNS, OR ACCEPT INDIRECT

**What it is.** The echo bench on AirPods-both and AirPods-out +
built-in-mic. Measured on the built-in array only (50.1 dB reduction,
residual 20.3 dB below the idle floor, 0 Silero turns against a control
raising 10).

**Where it stands.** Four AirPods conversations completed with no sign of
the bot transcribing itself, which is indirect evidence, not a measurement.

**To close.** Either `./closure-checks/run-echo-config.command airpods-both`
and `… airpods-out-builtin-mic` — about five minutes, silent, no
conversation needed — or record it as indirectly covered with that caveat
stated. The bench is cheap enough that measuring is the better answer.

## 8. Plan Status → IMPLEMENTED — LARRY'S CALL

Unchanged deliberately. §8 is now done; items 1–7 above are what stands
between here and that line being true.

## 9. PR #71's two open questions — SEPARATE WORKSTREAM

The model-registry split plan merged with two questions unanswered: where
the supervisor pin lives (`model_endpoints.yaml` vs the already-denied
`config/upgrade_agent.yaml`), and whether `scripts/sync_models.py` should be
Tier 0. Both shape the implementation, so they want answering before anyone
starts it.

## 10. The wave lost its amplitude and width — DEFECT, CAUSE MEASURED

**What it is.** Larry, 2026-09-16: "the sine wave for voice interaction lost
its amplitude and width from the previous version, I want that back."

**Cause.** Three separate terms, all in `VoiceWaveView.draw`'s adaptive
branch (`presentation != nil`), plus a layout choice. The amplitude line is
`amp = h * (dyn.base + breath + voice + 0.01 * flash) * ampScale`
(VoiceWaveView.swift:235, `ampScale = 2.0`):

1. **`dyn.base` is pinned to `0.004`** (VoiceWaveView.swift:196). That is the
   `.offline` target. The legacy path eases `dyn.base` toward the per-state
   target - `0.016` speaking, `0.01` listening (the `targets` table, :93-98).
   So the adaptive trace draws its *resting* thickness from the offline value
   in every state, a 4x cut while speaking.
2. **`voice = level * 0.115` now carries a real level** (:218). Both paths use
   the same `0.115`. Legacy fed it `simLevel(t)`, which returns
   `0.25 + 0.75*|...|` - a floor of 0.25 and a ceiling of 1.0 (:144-147).
   Adaptive feeds it `measuredEnvelope.advance(...)`, i.e. linear RMS, 0...1
   full scale (`AudioLevelSample.rms`). Speech RMS is nowhere near 1.
   Worked, at `h = 800`: legacy speaking peak
   `800 * (0.016 + 0.115) * 2 = 210 px`; adaptive at a measured RMS of 0.10,
   `800 * (0.004 + 0.0115) * 2 = 25 px`.
3. **`dyn.speed` is pinned to `0.45`** (:199), against a legacy speaking
   target of `1.0`. The wobble runs at a little under half rate, which reads
   as less alive even at equal amplitude.

**Width** is not the window function - `env = exp(-((x-cx)/(0.11*w))^4)` is
identical on both paths, so the lobe is always the same *fraction* of `w`.
What changed is `w`. Legacy renders the wave as a full-window background
(`ConsoleView.swift:44`, `.ignoresSafeArea()`), so `w` is the window width.
Adaptive has three call sites (`AdaptiveStageView.swift:53/66/78`) and only
the first is full-size: `.rail` clamps to `height: 150`, `.bottom` to
`width: 140`. At `w = 140` the lobe's half-width is `0.11 * 140 = 15 px`.

**What is not yet measured.** The actual RMS of Larry's speech through this
capture path. Item 2's figure of 0.10 above is illustrative, not observed -
no artifact records level magnitudes (`P2-latency.json` records arrival
*timing* only). That number sets how much of the 210 -> 25 px gap is the
level scale versus the base pin, so it decides which term to fix and by how
much.

**To close.** In order:
- Log `max(userLevel, outputLevel)` over one ordinary conversation. One
  os_log line in `VoicePresentationState.derive`, one session, one number.
- Then pick a mapping deliberately rather than reusing `0.115`: a measured
  RMS needs its own curve (a gain, or a perceptual/log mapping) to land in
  the same visual range the simulation occupied. This is the real decision -
  the honest level should stay honest and still be visible.
- Let `dyn.base` and `dyn.speed` ease to their per-state targets on the
  adaptive path too, instead of being pinned to the offline values. Keep the
  §7 colour pinning, which is a separate and deliberate choice (C2.4).
- Decide the frame: whether `.rail`/`.bottom` should give the wave more room,
  or whether the full-size `.conversation` wave is the one Larry means by
  "the previous version". Ask before changing the layout; the numbers above
  are enough to fix amplitude without touching it.

**Regression risk.** C7's whole point was that the meter shows measured
audio. Re-inflating the trace must not reintroduce motion when nothing is
arriving: `staticTrace` (:152) and the `VoiceEnvelope` clamp on stale or
absent levels are what keep that true, and any gain applied has to sit
*inside* them, not around them.

## 11. A sub-agent is unusable after an error — TESTED, NEITHER CAUSE REPRODUCED

**What it is.** Larry, 2026-09-16: "when a sub-agent hits an error it is no
longer usable... I need to be able to overcome an error and not have to
re-boot the interface to regain the use of the sub-agent."

**Only one mechanism in the codebase refuses a delegation *because* of a
prior error**: the A2 retry guard (`jarvis/agents/delegate.py:330-364`).
On `FAILED:` it records `last_failure[agent] = (task_tokens, now)` (:462).
The next delegation to that agent is refused when all of:
- it arrives within `RETRY_GUARD_WINDOW_S = 120` s of the failure;
- `_overlap_score(prior, new) >= 0.5`;
- and it is not an *earned* continuation.

Three properties make it match Larry's description exactly:

- **It is session state.** `last_failure` is a closure local of
  `build_delegate_tool`, called from `build_pipeline` (pipeline.py:417),
  called from `run_session`, which pipecat runs **once per connection**
  (`jarvis/bot/bot.py:65`). A reconnect builds a fresh empty dict - which is
  what "re-boot the interface" does.
- **The escape hatch cannot be reached after a plain failure.** `continuation`
  is only honoured if `awaiting_user[agent]` is true, and that is set from
  the *agent's own reply* containing `NEEDS-INPUT:` or being exhausted
  (:458). A plain `FAILED:` sets it **false**. So after an ordinary failure
  there is no legitimate way for the Supervisor to re-delegate - and no way
  for Larry to authorise one either. An unearned claim is logged
  `delegate_continuation_unearned` and refused anyway.
- **A short natural re-ask is the most likely thing to be refused.**
  `_overlap_score` divides by the *smaller* token set
  (`jarvis/procedures.py:137-146`), so any terse follow-up whose tokens are a
  subset of the failed task scores **1.0**. "try the memory graph again"
  after a failed memory-graph task is a guaranteed refusal.

**The second candidate is the prompt, not the code.** Supervisor rule 11
(`jarvis/prompts.py:73`) says to report the sub-agent's reason and *ask how
to proceed*, and "Never immediately re-delegate a reworded version of a task
that FAILED". A model over-applying that will refuse to try again for the
rest of the conversation - also conversation-scoped, so also cleared by a
reconnect. Same symptom, different fix.

**Why the one occurrence that matters cannot be attributed.** A guard
refusal returns before `run_id` is generated, so **it creates no run row** -
`agent_runs` cannot show it. Its only trace is
`logger.info("delegate_retry_guard_refused ...")` on the bot's stdout.

That stdout *is* captured. The launcher Larry actually runs,
`closure-checks/run-bot-c6.command`, pipes it to
`closure-checks/logs/bot-c6.log` with `PYTHONUNBUFFERED=1`. The defect was
that it used a bare `tee`, which **truncates** - so every relaunch destroyed
the session before it:

- The librarian failed at 2026-09-16T00:09:18 UTC, which is 20:09 local.
- `bot-c6.log`'s first line is `2026-09-15 20:47:10`: a single launch,
  431 KB, ending 21:59. The bot was relaunched at 20:47 and took the 20:09
  session's log with it.
- What survives in that window: three delegations, all `analyst`, all
  `subagent_done` with no failure, and **zero** `delegate_retry_guard`
  lines. Nothing to attribute, and nothing that rules the guard out either.

`scripts/mortimer.sh` has rotated the launchd stack's logs through five
generations since the run-logging plan's D11, for exactly this reason. The
closure-checks launcher never did. Fixed 2026-09-16: same rotation, then
`tee -a`. That launcher lives under `closure-checks/`, which
`.git/info/exclude` ignores, so the fix is on the deployment Mac and not in
this commit.

What the run log *does* show (queried 2026-09-16): 40 runs, 4 failed. The
one relevant sequence is 2026-09-13 - analyst failed at 22:44:41, ran fine
at 22:49:54 (5 min later, outside the 120 s window), failed again at
22:50:18. Consistent with the guard, and equally consistent with no guard at
all. The newest failure is the librarian above,
`memory_graph_view found no node matching "interests"`, with **no librarian
run after it**.

**To close.** Three steps, in order:
1. **Stop destroying the log.** Done 2026-09-16 - the launcher rotates five
   generations and appends instead of truncating. Until that was in, the next
   occurrence would have been erased by the next restart, which is precisely
   what happened to the last one.
2. **Reproduce and discriminate.** The librarian failure above is
   reproducible - ask for a memory graph of a node that does not exist. Then
   re-ask *in the same words* inside 120 s:
   - Mortimer relays "blocked by a safety guard" wording, or the log shows
     `delegate_retry_guard_refused` -> **the guard**. Fix is an
     authorisation path.
   - Mortimer instead says it failed and asks how to proceed, and will not
     act on "try it again" -> **rule 11**. Fix is a prompt amendment.
   Then wait past 120 s and ask again. If it runs, nothing is permanently
   latched and a reconnect was never actually required - worth knowing either
   way.
3. **Fix, per the outcome.** If it is the guard, the design constraint is
   real and must be kept: A2 exists because a live session produced six
   reworded retries in a row, one inventing "vault credentials", so
   authorisation must come from a source the Supervisor **cannot author**.
   `NEEDS-INPUT:` qualifies because another model wrote it. Options, to
   choose before writing code:
   - *User speech as the authoriser.* Allow one retry when a user transcript
     frame arrived between the refusal and the retry. STT output is not
     model-authored, so it cannot be forged - the same property that makes
     `NEEDS-INPUT:` usable.
   - *Refuse once, then warn.* The first re-delegation is refused; a second
     runs with the refusal text appended to the task. Bounded, not unbounded.
   - *Shorten the window.* Least invasive, does not solve "I want to retry
     now", and 120 s was not chosen arbitrarily.
   Whichever is chosen, the refusal text should stop claiming there is no way
   forward when there now is one.

**What must not regress.** The A2 test suite, and the 2026-08-25 carve-out
for the confirm-half of a two-phase flow (`_shares_long_identifier`). Any
new path has to leave both intact.

---

## Test result for item 11 — 2026-09-16, 11:42-11:45 local

Ran per the plan above: bot relaunched on the rotating launcher, the
librarian asked for a memory graph of a topic with no nodes, then asked
again in the same words. `closure-checks/logs/bot-c6.log`, one launch,
126 KB.

**Neither candidate fired.**

- **`delegate_retry_guard` lines in the log: zero.** Two librarian
  delegations went out 8 s apart with near-identical tasks
  (`toolu_015xcQQq...` at 11:44:12.869, `toolu_01QXiSD...` at 11:44:20.972)
  and **both ran to completion**. A developer delegation at 11:45:02 also
  ran fine, 41 s, `tools_ok=10`.
- **Rule 11 did not fire either.** The Supervisor relayed the failure
  correctly, re-delegated immediately, then delegated onward to the
  developer. It never declined to try again.

**Why the guard could not fire, which is itself the finding.** The first
delegation was orphaned by an interruption at 11:44:18.845
(`delegate_orphaned_by_interruption run_id=101c52cf`) and did not record its
failure until `subagent_done` at 11:44:21.964 - but the *second* delegation
was issued at 11:44:20.972, about a second **before** `last_failure` was
armed. In the interrupt-heavy path Larry actually uses, a retry routinely
outruns the failure record, so the 120 s window is much harder to reach than
reading the code suggests. The guard is real; it is not what he hit.

**What did reproduce is a third mechanism, and it is the better candidate.**
`SkillRegistry` is built per session (`pipeline.py:979`) and stopped in
`run_session`'s `finally` (`pipeline.py:1440`), where `stop()` sets
`self._tools = {}` (`skills/registry.py:286`). A sub-agent run survives the
session by design (barge-in survival, delegate.py's docstring) - but its
**tools do not**. Measured:

- 11:45:25.433 `[session] client disconnected`, pipeline cancelled.
- 11:45:27.6 the developer's `repo_read_file` calls still work.
- 11:45:33.6 and 11:45:43.9 its `repo_search` calls come back
  `Unknown tool 'repo_search'. Available: none.`
  (`skills/registry.py:332`, with `self._tools` empty).

`repo_search` is a real tool - `mcp-repo` started with 5 tools at
11:43:38 - so this is not a hallucinated name. The run finished `ok` with
`tools_failed=2`, and its own reply says the two failures stopped it from
answering the question it was sent to answer.

That is a sub-agent that is genuinely unusable after an error, triggered
from the client side, and cured by reconnecting - the shape of Larry's
report. **Not yet confirmed as what he experienced**: this needs a
disconnect while a run is in flight. What would test it: delegate a long
task, disconnect the app mid-run, reconnect, and check whether the run's
later tool calls carry `Available: none`.

**Fix shape.** The barge-in design deliberately outlives the voice turn.
Either the registry has to outlive it too (hoist it above `run_session`, or
reference-count it against in-flight detached runs), or a detached run has
to be told its tools are gone and say so, instead of reporting `ok` with two
silent failures. The second is smaller; the first is what the design implies.

## 12. The bot has been writing to the wrong database since 2026-09-13 — TOP PRIORITY

**What it is.** Larry, mid-test: *"I don't understand why they're not there.
We've had many discussions. There should be many memories."* He is right, and
the memories were never lost.

**Measured, both databases, 2026-09-16:**

| | `~/jarvis-voice-ai-clean/data/jarvis.db` | `…/active-repo/data/jarvis.db` |
|---|---|---|
| conversations | 2842, last 2026-09-11T19:20 | 288, last 2026-09-16T15:45 |
| extraction cursor | 2842, updated 2026-09-11T19:20 | **0, updated 1970-01-01** |
| memories | **434** | 2 |
| observations | **146** | 0 |

Everything Larry has said to Mortimer since 2026-09-13 went into
`active-repo/data/jarvis.db`: 288 conversations, an extraction cursor that
has **never advanced**, and two memory rows - a rolling summary and
`fact:user.name`. His real memory, 434 memories and 146 observations, is
intact in the clean copy, where the extraction worker had caught up
completely as of 09-11.

**Why nothing was extracted even there.** `extract_facts_and_observations =
not memory_extraction_v2_enabled()` (`bot/memory_watcher.py:85`,
`bot/pipeline.py:1390`). v2 is on, so the legacy in-session fact writes are
correctly skipped - hence `v2_writes_skipped=True` on every
`memory_updated` line - and the v2 worker
(`jarvis/memory_extraction_worker.py`, launched as `extractor` by
`scripts/mortimer.sh`) is supposed to do the work instead. That worker runs
against the clean copy: `logs/extractor.launchd.log` there was last written
2026-09-11T19:20, and `active-repo/logs/` has no extractor log at all. So
the DB the bot writes has no extractor, and the DB the extractor watches
gets no conversations.

**This also corrects the developer agent's own finding.** It reported
"real emptiness, not lost data… those facts were never stored." True of the
database it could see, and wrong about Larry. It could not check further
because `repo_search` had gone toolless (item 11 above).

**Not a stale read.** The write-ahead logs settle it: active-repo's
`jarvis.db-wal` is 1.77 MB timestamped 15:45 - the test session - while the
clean copy's is 8 KB and untouched since 2026-09-11T19:23, as is its main
database file. The split is real, not an artifact of reading a WAL-mode
database read-only.

**Where the path comes from - the obvious answer is ruled out.** The
launcher exports `JARVIS_DB_PATH="$CLEAN/data/jarvis.db"`, and its header now
has Python print what it actually resolves. At the 11:55 launch all three
agree:

```
db:    /Users/larryfix/jarvis-voice-ai-clean/data/jarvis.db   (python env)
db:    /Users/larryfix/jarvis-voice-ai-clean/data/jarvis.db   (settings)
db:    /Users/larryfix/jarvis-voice-ai-clean/data/jarvis.db   (RESOLVED)
```

So startup resolution is **correct**, and something later in the process
takes the relative fallback. Ruled out by reading: `db.py:605`
`_default_db_path()` reads that env var; `config.py:269` bridges with
`setdefault`, so a real env var keeps winning; `vault.inject_env` fills only
names that are missing or empty and injected 0 this launch; `active-repo`
has no `.env` for dotenv to win with; `JARVIS_DB_PATH` is in the registry's
`BASE_ENV_KEYS`, so MCP children receive it; and those children are spawned
with `cwd=REPO_ROOT` (`registry.py:430`). **Mechanism still unidentified -
untested.**

**The next test, and it costs one sentence of speech.** The 11:55 bot is
running and has served no session. Say one thing to it, then compare the two
`jarvis.db-wal` sizes:
- active-repo's WAL grows -> the writer ignores the resolved path, and the
  next step is one log line in `get_conn` printing `path.resolve()` once per
  distinct path, which names the writer on the following session.
- the clean copy's WAL grows -> something about the earlier launches was
  different (a stale bot process is the obvious candidate) and the fault may
  already be gone. Either way the answer arrives without more code reading.

**To close.** In order:
1. Run the WAL test above. One utterance, one answer.
2. Fix the writer, so the bot writes to the clean copy's DB - the one with
   his memory and the one the extractor watches.
3. Decide what to do with the 288 orphaned conversations: merge them into
   the real DB so the extractor can process them, or discard them. Merging
   is the only option that turns three days of talking into memories.
4. Only then re-test item 11 - and re-run the librarian graph, which should
   now find 434 memories to draw.

**Nothing else on this list matters until this is fixed.** Every
conversation held in the meantime goes to the wrong place.
