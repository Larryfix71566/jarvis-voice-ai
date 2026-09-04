# Adversarial review — `MORTIMER_LOCAL_VOICE_AND_MINI_PLAN.md` (track T3)

Reviewed against: `/home/claude/repo` (jarvis-voice-ai-clean snapshot),
Pipecat 1.4.0 at `/usr/local/lib/python3.11/dist-packages/pipecat`,
`/home/claude/plans/BRIEF.md` (K1–K8).

**Verdict: not implementable as written.** The plan's central safety argument
(§1.3, Correction 5 — "the swap is safe because the user aggregator broadcasts
the speaking frames itself") is true about *which* frames exist and false about
*when* they exist, and the plan omits the one consumer that makes the timing
load-bearing. Separately, the `whisper_mlx` path cannot import at all on the
machine the runbook builds, and the launchd design cannot satisfy the gate item
(G3(d)) it exists to produce.

Counts: **7 BLOCKER**, **6 MAJOR**, **9 MINOR**.

---

## Findings

### F1 — The `whisper_mlx` path cannot import: `pipecat.services.whisper.stt` hard-requires `faster_whisper`, which the plan never installs [BLOCKER]

**Where:** §3 L4, §5 Step 2 (`build_stt`'s whisper branch), §4 Modify →
`requirements.txt`, §5 Step 9.1 (runbook venv), §7 test #4.

**What the plan says:**
> `requirements.txt` | Add the two Apple-Silicon-only optional extras … `mlx-whisper>=0.4.3 ; …` and `kokoro-onnx>=0.4.9 ; …`

and §5 Step 9.1:
> `uv pip install -r requirements-lock.txt` / `uv pip install "mlx-whisper>=0.4.3"`

and §7 test #4:
> `MLXModel.LARGE_V3_TURBO.value == providers.WHISPER_MODEL`. **Runs on Linux** (the enum is importable without `mlx_whisper`).

**Why it's wrong:** `mlx-whisper` is not the module's only hard dependency.
`pipecat/services/whisper/stt.py` imports `faster_whisper` at **module scope**
and converts a miss into a hard `ImportError` — before the MLX-only branch is
ever reached. `faster-whisper` is in neither `requirements.txt` nor
`requirements-lock.txt`, and `requirements.txt:1` requests the extras
`[deepgram,elevenlabs,openai,google,silero,mcp,runner,webrtc]` — no `whisper`.
So on the mini, `build_stt` with `JARVIS_STT_PROVIDER=whisper_mlx` raises
`ImportError` on the first line of its branch, and on Linux CI the new unit
test #4 errors rather than passing.

**Evidence:**
```
$ python3 -c "from pipecat.services.whisper.stt import MLXModel, WhisperSTTServiceMLX"
  File ".../pipecat/services/whisper/stt.py", line 35, in <module>
    raise ImportError(f"Missing module: {e}") from e
ImportError: Missing module: No module named 'faster_whisper'
```
`.../whisper/stt.py:30-35`:
```python
try:
    from faster_whisper import WhisperModel
except ModuleNotFoundError as e:
    logger.error('In order to use Whisper, you need to `uv add "pipecat-ai[whisper]"`.')
    raise ImportError(f"Missing module: {e}") from e
```
```
$ grep -in "pipecat\|faster\|mlx\|kokoro" requirements.txt requirements-lock.txt
requirements.txt:1:pipecat-ai[deepgram,elevenlabs,openai,google,silero,mcp,runner,webrtc]
requirements-lock.txt:112:pipecat-ai==1.4.0
   (no faster_whisper, no mlx, no kokoro anywhere)
```
The same trap exists for Kokoro: `pipecat/services/kokoro/tts.py:36` raises
`ImportError: No module named 'kokoro_onnx'`, and §5 Step 9.1 never installs
`kokoro-onnx` on the mini even though §5 Step 5 / L13 say the runbook pre-fetches
the Kokoro model.

**Fix:**
1. `requirements.txt:1` → `pipecat-ai[deepgram,elevenlabs,openai,google,silero,mcp,runner,webrtc,whisper]`
   and add `faster-whisper` to `requirements-lock.txt` at the pinned version
   that extra resolves to.
2. §5 Step 9.1 → `uv pip install "mlx-whisper>=0.4.3" "faster-whisper" "kokoro-onnx>=0.4.9"`.
3. §7 test #4 must be `pytest.importorskip("faster_whisper")`-guarded, or the
   constant check must be done without importing the module (hard-code the
   expected string and assert it in an Apple-only integration test). As written
   it violates §0.8 ("`pytest tests/unit -q` must pass on Linux").

---

### F2 — The frame-contract claim is incomplete: `MinWordsUserTurnStartStrategy` consumes `InterimTranscriptionFrame` and is the *only* thing that starts a user turn. Whisper emits none, so barge-in degrades from ~0.5 s to ≥ 2.5 s [BLOCKER]

**Where:** Correction 5, §1.3 (the consumer table), §3 L3, §5 Step 3.
Repo: `jarvis/bot/pipeline.py:625-638`, `jarvis/bot/pipeline.py:493-499`.

**What the plan says:**
> **Nothing in `jarvis/bot/` reads a Flux-only frame in a load-bearing way.** The single behavioural loss is `InterimTranscriptionFrame`, which only `TranscriptGate` touches and only to forward.

**Why it's wrong:** the §1.3 table enumerates seven consumers and omits the
eighth and most important one — the **user-turn start strategy**, which jarvis
itself constructs at `jarvis/bot/pipeline.py:626-630`. It is
`MinWordsUserTurnStartStrategy` (or jarvis's subclass), and it triggers on
`TranscriptionFrame` **or** `InterimTranscriptionFrame` and on nothing else.

Critically, jarvis passes `start=[turn_start_strategy]`, which **replaces**
Pipecat's default `[VADUserTurnStartStrategy(), TranscriptionUserTurnStartStrategy()]`
(`pipecat/turns/user_turn_strategies.py:27-40`). There is therefore **no
VAD-driven turn start in this pipeline at all**: the user turn — and with it the
aggregator's `UserStartedSpeakingFrame` broadcast *and* its
`broadcast_interruption()` — cannot fire until a transcript exists.

With Flux, an `InterimTranscriptionFrame` arrives ~0.5 s into speech
(`Update` events, `flux/base.py:742-753`), so the turn starts mid-speech. With
`WhisperSTTServiceMLX` (a `SegmentedSTTService`) the first and only transcript
is produced **after** `VADUserStoppedSpeakingFrame`, i.e. after `stop_secs`
(2.5 s) of silence plus MLX inference. So the interruption broadcast that
implements barge-in moves from "half a second after the user starts talking" to
"two and a half seconds plus inference after the user stops talking".

The repo has already paid for this exact property and documented the price:
`jarvis/bot/pipeline.py:493-499`
> "Cost: barge-in now fires at **first transcript** (~0.5 s after speech starts) instead of at VAD onset — an unverified interruption a TV can fire is worse than a verified one that arrives half a second later."

The plan silently converts "0.5 s after speech starts" into "≥ 2.5 s after
speech ends" and never mentions it. Roadmap R6 ("local STT does not ship without
turn detection at parity") is violated by construction, and §5 Step 7's re-tune
cannot detect it (see F4).

**Evidence:** `pipecat/turns/user_start/min_words_user_turn_start_strategy.py:51-69`:
```python
elif isinstance(frame, TranscriptionFrame):
    return await self._handle_transcription(frame)
elif isinstance(frame, InterimTranscriptionFrame) and self._use_interim:
    return await self._handle_transcription(frame)
return ProcessFrameResult.CONTINUE
```
`__init__(self, *, min_words: int, use_interim: bool = True, ...)` — interim is
on by default and jarvis does not turn it off (`pipeline.py:630`:
`MinWordsUserTurnStartStrategy(min_words=2)`).

`pipecat/services/stt_service.py:766-790` — `SegmentedSTTService` only reacts to
`VADUserStartedSpeakingFrame`/`VADUserStoppedSpeakingFrame` and runs the
transcription in `_handle_user_stopped_speaking`; it never emits an interim.

`pipecat/processors/aggregators/llm_response_universal.py:1180-1187` — the
`UserStartedSpeakingFrame` broadcast **and** `broadcast_interruption()` both hang
off `_on_user_turn_started`, i.e. off the start strategy firing.

**Fix:** the plan must add a VAD-driven start path for the `whisper_mlx`
provider, since the transcript-driven one no longer arrives in time. Concretely,
`build_turn_start_strategies(settings)` (a fifth factory in `providers.py`):

```python
def build_turn_start_strategies(settings, speaker_gate_state):
    base = (SpeakerVerifiedMinWordsTurnStartStrategy(speaker_gate_state, min_words=2)
            if speaker_gate_state is not None
            else MinWordsUserTurnStartStrategy(min_words=2))
    if settings.jarvis_stt_provider == "whisper_mlx":
        # Whisper emits no interim transcript, so the min-words strategy
        # cannot start a turn until after VAD stop. Add pipecat's VAD start
        # strategy AHEAD of it so barge-in still fires at speech onset.
        return [VADUserTurnStartStrategy(), base]
    return [base]
```
…and the plan must then state, in §5 Step 7, what this does to the TV/speaker-gate
defect that `should_interrupt=False` was introduced to fix
(`pipeline.py:483-499`) — a VAD-onset interruption is exactly the unverified
interruption that comment rejects. If that trade is unacceptable, the honest
outcome is that T3.2 fails R6 and the plan must say so rather than not noticing.

---

### F3 — Under Whisper the smart-turn analyzer stops deciding end-of-turn; a "no VAD stop received" fallback decides. Correction 1's premise stops holding at exactly the moment the plan relies on it [BLOCKER]

**Where:** Correction 1, §1.3 (last row: "**Yes, and better**"), §3 L8, §6
("Smart-turn internal silence … deliberately not the tuning lever").

**What the plan says:**
> `TurnAnalyzerUserTurnStopStrategy` … | **Yes, and better** — `SegmentedSTTService.push_frame` marks every `TranscriptionFrame` finalized …, so the STT-timeout safety net stops being the deciding path.

**Why it's wrong:** the ordering inverts. `UserTurnController.process_frame`
runs the **start** strategies first and the **stop** strategies second, on the
same frame (`pipecat/turns/user_turn_controller.py:161-171`), and
`_trigger_user_turn_start` **resets every stop strategy** before returning
(`user_turn_controller.py:276-278`).

- *With Flux:* the interim transcript fires turn-start early, so the reset lands
  **before** `VADUserStoppedSpeakingFrame`. The analyzer's verdict computed in
  `_handle_vad_user_stopped_speaking` (`turn_analyzer_user_turn_stop_strategy.py`,
  `self._turn_complete = state == EndOfTurnState.COMPLETE`) survives and gates
  end-of-turn. This is D-010's protection.
- *With Whisper:* the only transcript arrives **after** VAD stop, so the reset
  lands after it and wipes `_turn_complete`, `_vad_stopped_time`,
  `_transcript_finalized` and the timeout task. The stop strategy then sees the
  same `TranscriptionFrame`, finds `_turn_complete == False`, falls through to
  the explicit fallback branch —
  ```python
  # Fallback: handle transcripts when no VAD stop was received.
  if not self._vad_user_speaking and self._vad_stopped_time is None:
      ...
      # Without VAD/turn analyzer data, assume turn is complete
      self._turn_complete = True
  ```
  — and ends the turn on "a transcript exists", with the analyzer's prediction
  discarded.

Consequences the plan does not account for:
1. The smart-turn model is loaded, runs, and is ignored. Correction 1's headline
   ("it is already running, so expect no latency change") is true today and
   false after Step 3.
2. D-010's mid-sentence-pause protection now rests **entirely** on `stop_secs`,
   because Whisper's *segmentation boundary* is `VADUserStoppedSpeakingFrame`.
   A 2.0 s pause at `stop_secs = 1.75` does not merely risk an early turn close —
   it splits the **audio segment**, so Whisper transcribes half a sentence and
   there is no second chance. L8's floor of 1.75 is therefore below the known
   failure point (DEVIATIONS D-010 measured a sample-exact 2.000 s gap), not
   safely above it.
3. §6's rationale for freezing `SMART_TURN_STOP_SECS = 3.0` ("the analyzer's own
   internal silence threshold … moving both at once makes the measurement
   uninterpretable") is moot in the `whisper_mlx` configuration: the analyzer no
   longer participates.

**Evidence:** `pipecat/turns/user_turn_controller.py:161-171` (start loop then
stop loop), `:262-280` (`_trigger_user_turn_start` → `for s in stop: await s.reset()`),
`pipecat/turns/user_stop/turn_analyzer_user_turn_stop_strategy.py`
`reset()` (clears `_turn_complete`, `_vad_stopped_time`, `_transcript_finalized`)
and `_handle_transcription`'s fallback block quoted above.
`pipecat/services/stt_service.py:777-800` — the segment is cut at
`VADUserStoppedSpeakingFrame`, so `stop_secs` is the segmentation boundary.

**Fix:** either
(a) set `stop_secs` floor to **2.5** (no lowering) for `whisper_mlx` and record
    that G3(b) has no lever, or
(b) state in L8 that under `whisper_mlx` the end-of-turn decision is the
    fallback path, delete the "Yes, and better" row from §1.3, delete §6's
    "deliberately not the tuning lever" rationale, and add a test in
    `tests/unit/test_providers.py` that asserts the D-010 utterance's 2.0 s gap
    is shorter than the configured `stop_secs` (a pure numeric guard:
    `assert VAD_STOP_SECS > 2.0`).
Either way DEVIATIONS D-013 (§5 Step 10) must record *this* fact, not only the
"smart-turn was already on" one — the new deviation is that swapping the STT
turns it off.

---

### F4 — G3(b)'s instrument cannot see the regression, and `stop_secs` is not inside the interval it measures. The eight tests in P4(a) pass for every value of the knob [BLOCKER]

**Where:** §5 Step 7 (P0–P5), §3 L8, §1.6, §1.7, §8 B1–B7.

**What the plan says:**
> P3. IF `M_ms <= B_ms + 150` → G3(b) latency bound MET at `stop_secs=2.5`.
> P4. For `stop_secs` in 2.25, 2.00, 1.75: a. `pytest tests/unit/test_interruption.py -q` → must be green …

**Why it's wrong — two independent reasons.**

*(i) The clock starts after the thing being measured.*
`TURN user_end->first_audio` starts at `UserStoppedSpeakingFrame`
(`jarvis/bot/transcript_log.py:114-116` and `:58`), and the **last**
`UserStoppedSpeakingFrame` before the reply is the aggregator's turn-stop
broadcast. Turn stop happens:
- under Flux — at VAD stop (the final transcript arrived earlier, at Flux's
  `EndOfTurn`, so `_text` is already populated);
- under Whisper — at VAD stop **plus** MLX inference (turn stop waits for the
  transcript: `_maybe_trigger_user_turn_stopped` returns early on `if not self._text`).

So the entire Whisper penalty lands *before* `M_ms`'s clock starts and is
invisible to the measurement. `M_ms ≈ B_ms` is the expected result **whether or
not the user experience regressed**, which means P3 will report "MET" for the
wrong reason. G3(b) is a gate that can be met without the feature working.

Symmetrically, `stop_secs` is also entirely before the clock start (it is the
silence window that precedes VAD stop). Lowering it from 2.5 to 1.75 therefore
changes `M_ms` by approximately zero — so if P3 *does* fail, P4's only lever
cannot fix it. The bounded search is a ritual in both directions.
DEVIATIONS D-010 confirms the clock excludes the window: it records "every turn's
close latency grows by ~2.3 s" while `scripts/latency_probe.py`'s p50 budget is
1200 ms — those two numbers can only coexist if the 2.5 s window is outside the
measured interval.

*(ii) The eight regression tests are invariant under `stop_secs`.*
All eight tests in `tests/unit/test_interruption.py` construct
`InterruptionNotifier` directly and feed it hand-built frames through
`pushed(...)`. They never build a pipeline, never touch `VADParams`, never
import `jarvis.bot.pipeline`. The plan itself says so in §1.7 —
> "All eight are frame-level and STT-agnostic … **The STT swap cannot break them, and they cannot prove the STT swap is safe.**"

— and then uses them anyway as P4's per-step green light. That is exactly this
project's documented failure mode (a passing test that is passing for a reason
unrelated to the rule).

**Evidence:**
```
$ grep -c "def test_" tests/unit/test_interruption.py
8
$ grep -n "VADParams\|pipeline\|stop_secs" tests/unit/test_interruption.py
(no matches)
```
`jarvis/bot/transcript_log.py:113-127` — `_turn_start` is reset on **every**
`UserStoppedSpeakingFrame`, and the `TURN user_end->first_audio` line is emitted
on the first `OutputAudioRawFrame` after it.
`pipecat/turns/user_stop/turn_analyzer_user_turn_stop_strategy.py`
`_maybe_trigger_user_turn_stopped`: `if not self._text: return`.

**Fix:** G3(b) needs an instrument that spans the silence window. Add one line to
`jarvis/bot/transcript_log.py` keyed on `VADUserStoppedSpeakingFrame` (which both
providers emit at the same instant, from the VAD, independent of STT):

```python
if isinstance(frame, VADUserStoppedSpeakingFrame):
    self._vad_stop = time.perf_counter()
...
# on first OutputAudioRawFrame:
print(f"TURN vad_stop->first_audio = {ms}ms", flush=True)
```
and teach `scripts/latency_probe.py` a second regex for it. Measure **that**
number for `B_ms`/`M_ms`; it contains both the STT latency and `stop_secs`, so
the bound is meaningful and the lever actually moves it. Then replace P4(a)'s
`pytest tests/unit/test_interruption.py` with the D-010 single-turn check
(P4(b)), which is the only step in P4 that can fail for the right reason.

---

### F5 — The launchd design cannot satisfy §8 E4 / G3(d): a `gui/$(id -u)` LaunchAgent requires a login session, and if a login session exists the Keychain works — collapsing L11's entire premise [BLOCKER]

**Where:** §3 L10, §3 L11, §5 Step 9.3–9.4, §8 E4, §10 R-L2.

**What the plan says:**
> all **LaunchAgents** in `~/Library/LaunchAgents/` … (never LaunchDaemons: the stack needs `$HOME` …)
> `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.mortimer.bot.plist`
> **The problem.** … A launchd job gets the login keychain only when it runs in the user's Aqua session *and* that keychain is unlocked … A headless mini has no interactive login …
> E4. Reboot the mini. All three services back up **with no login**? yes / no

**Why it's wrong:** these three statements cannot all be true. The `gui/<uid>`
domain **is** the Aqua session domain. An agent bootstrapped into `gui/<uid>`
exists only while that user is logged into the GUI; `RunAtLoad` fires at *login*,
not at boot. So:
- If the mini has no login session, E4 fails — not because of the key file, but
  because a `gui/` agent is not loaded at all. The plan's E4 diagnostic
  ("the vault key file or its permissions are wrong — check `ls -l …`") points
  the operator at the wrong cause and will burn hours.
- If the mini *does* auto-login (the only way E4 passes), then the login keychain
  is unlocked by that login, `keyring.get_password("mortimer", "vault-key")`
  works, and L11's justification for writing the master key to disk in plaintext
  evaporates.

The plan therefore adopts the **LaunchAgent** domain (whose only advantage is
having a login session) *and* the **LaunchDaemon** key mechanism (whose only
justification is not having one), taking the security cost of the second without
the operational benefit it buys.

**Security assessment, honestly (as asked):** R-L2 understates the change.
"The bot process could already decrypt everything the key protects" is true of a
*running* bot; a 0600 file makes the master key readable at rest by anything that
can read one file as that user — a compromised MCP child running as Larry
(K2 scopes env, not filesystem), any backup, Time Machine, `find / -perm 600`,
and a future T4b sensitive tier on the same box. The Keychain's value is exactly
that a file read is not a key read. Calling this "moves the boundary from
Keychain ACL to file mode" is right; calling that "not from protected to exposed"
is not.

**Alternatives, evaluated:**
- `launchctl setenv JARVIS_VAULT_KEY <b64>` — **worse**. The value is readable by
  any process on the machine via `launchctl getenv`, and it lands in a
  system-wide environment. Do not use.
- `LaunchDaemon` in `/Library/LaunchDaemons` with `<key>UserName</key>` set to
  Larry — starts at **boot**, no login required, which is what G3(d) actually
  asks for. `$HOME` and the Homebrew prefix are supplied by
  `scripts/launchd_exec.sh` already (it exports both). This is the honest
  configuration if the mini is truly headless, and it is the one where the 0600
  key file is unavoidable and therefore justified.
- **Auto-login + LaunchAgent + Keychain** — no plaintext key at rest, but reboot
  recovery depends on the GUI login completing, and the login password is stored
  in the FileVault/auto-login keychain anyway. Acceptable if FileVault is off.
- `--interactive` unlock at boot — not viable: nothing is there to type.

**Fix:** pick one and write it out, because as drafted the implementer must
choose:
- **Option A (recommended if headless):** move the three plists to
  `/Library/LaunchDaemons/`, add `<key>UserName</key><string>USERNAME</string>`
  and `<key>GroupID</key>`… , load with `sudo launchctl bootstrap system <plist>`,
  keep `/usr/local/etc/mortimer/vaultkey` at 0600 owned by root with
  `<key>UserName</key>` matching, and change §8 E4's diagnostic to
  "check `sudo launchctl print system/com.mortimer.bot`".
- **Option B:** keep LaunchAgents, add an explicit runbook step
  "System Settings → Users & Groups → Automatically log in as `<user>`, and
  disable FileVault (auto-login requires it off)", **delete L11** and keep the
  Keychain path, deleting the key file entirely.
Either way §8 E4's question must change from "with no login" to whatever the
chosen option actually delivers, and R-L2 must state the at-rest exposure without
the softening clause.

---

### F6 — Ollama's default context is 4096 tokens; the Supervisor's system prompt alone is ~3.4 k. The L7 ladder will disqualify every candidate for a reason that is not the model [BLOCKER]

**Where:** §3 L6, §3 L7 (STEP A–D), §3 L9 (`ollama ps` SIZE),
§5 Step 9.4 (`com.mortimer.llm.plist`), §6 (Ollama knobs).

**What the plan says:** the plist sets `OLLAMA_HOST`, `OLLAMA_KEEP_ALIVE`,
`OLLAMA_MAX_LOADED_MODELS` and nothing else; L7's STEP A is `ollama pull` + one
`max_tokens: 8` warm request; L9 takes `ollama ps` SIZE as `LLM_RESIDENT_GB`.

**Why it's wrong:** Ollama's per-model default context window is 4096 tokens
unless `num_ctx` / `OLLAMA_CONTEXT_LENGTH` is set, and it **silently truncates**
rather than erroring. The Mortimer Supervisor prompt is not small:

| Component | chars |
|---|---|
| `GOLDEN_RULES` | 594 |
| `SUPERVISOR_PROMPT` template | 7,899 |
| `VOICE_ADDENDUM` | 267 |
| `UI_CONTROL_ADDENDUM` | 740 |
| `SCREEN_VISION_ADDENDUM` | 911 |
| `HANDOFF_ADDENDUM` | 955 |
| `catalog_summary` (24 voices) | ~1,898 |
| agent catalog + memory context | ≥ 400 |
| **total** | **~13,660 chars ≈ 3,400 tokens** |

…before the nine registered tool schemas (`pipeline.py:526-542`) and before a
single conversation turn. The first request already overflows 4096, Ollama drops
the oldest tokens (the system prompt), and routing collapses. Every candidate on
the ladder fails STEP C, the implementer reaches L7's STOP branch, and the
recorded conclusion — "no local Supervisor model passed" — is false.

The same omission corrupts L9: `ollama ps` SIZE includes the KV cache sized for
the *configured* context. Measured at 4096 it under-reports the resident size for
the real workload, so `LLM_RESIDENT_GB` — the largest term in the RAM formula and
the number that decides a hardware purchase — is measured under the wrong
conditions. §3 L9's own text acknowledges this ("the KV cache scales with
context — and the Supervisor's context is not small") and then does nothing
about it.

**Evidence:**
```
$ python3 - <<'EOF'   # measured against /home/claude/repo/jarvis/prompts.py + config/voices.yaml
voices: 24
catalog_summary approx chars: 1898
approx system prompt chars: 13664 -> approx tokens: 3416
EOF
```
`jarvis/bot/pipeline.py:459-478` (prompt assembly), `:526-542` (nine
`register_function` calls whose schemas go into every request).

**Fix:**
1. Add to `deploy/launchd/com.mortimer.llm.plist`'s `EnvironmentVariables`:
   `<key>OLLAMA_CONTEXT_LENGTH</key><string>16384</string>` with the comment
   "the Supervisor system prompt alone is ~3.4 k tokens (measured); Ollama's
   4096 default silently truncates it".
2. Add `OLLAMA_CONTEXT_LENGTH` to §6's knob table with home
   `deploy/launchd/com.mortimer.llm.plist`, default `16384`.
3. L7 STEP A must run `ollama ps` **after** a request that carries the real
   system prompt, not a `"ping"` with `max_tokens: 8`. Concretely, replace
   STEP A's `curl` with:
   `EVAL_MODEL=<tag> EVAL_BASE_URL=... EVAL_KEY_ENV=OLLAMA_API_KEY RUN_LIVE=1 python -m tests.evals.routing_eval`
   (one run), then `ollama ps`.
4. Add a hard precondition to STEP B: if the eval's first case returns a reply
   that ignores the system prompt, check `OLLAMA_CONTEXT_LENGTH` before
   disqualifying the model.

---

### F7 — `scripts/check_env.py` must stay stdlib-only; the plan tells it to import `jarvis.config` (pydantic), and the escape hatch's trigger is wrong [BLOCKER]

**Where:** §5 Step 6b, first bullet. Repo: `scripts/check_env.py:1-7`.

**What the plan says:**
> `from jarvis.config import required_env_vars  # noqa: E402  (script, not a package)`
> If importing `jarvis.config` from this script creates a cycle or a heavy import at module scope, inline the same three-line rule instead … so prefer the import and only inline if the import actually fails.

**Why it's wrong:** `scripts/check_env.py`'s module docstring states its contract:
> "**Stdlib only, so it works before any dependencies are installed.** Prints one PASS / FAIL / WARN line per check"

It is the Exit-Gate-0 validator — the thing you run on a fresh clone to find out
*why* nothing works. `jarvis/config.py:25-26` imports `pydantic` and
`pydantic_settings` at module scope. Adding that import turns the one diagnostic
that must survive a broken environment into `ModuleNotFoundError:
No module named 'pydantic'`.

The escape hatch makes it worse, not better: the stated trigger is "only inline
if the import **actually fails**". In the implementer's sandbox and on Larry's
dev machine pydantic *is* installed, so the import succeeds, the implementer
keeps it, and the breakage ships to the only environment that matters. This is a
decision-tree branch whose condition is evaluated in the wrong environment —
a §0.1-forbidden judgment call in disguise.

**Evidence:**
```
$ sed -n '1,7p' scripts/check_env.py
"""Environment & connectivity validator (plan Phase 0, step 0.5 / Exit Gate 0).
Stdlib only, so it works before any dependencies are installed. …"""
$ sed -n '25,26p' jarvis/config.py
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
```

**Fix:** delete the import and the conditional entirely. Inline the four-line
rule in `check_env.py` and mark it as a deliberate duplicate:

```python
# Deliberate duplicate of jarvis.config.required_env_vars — this script is
# stdlib-only by contract (see the module docstring) and must not import
# pydantic. Keep the two in sync; tests/unit/test_config.py::
# test_check_env_required_vars_match_config asserts they agree.
def _required_vars(stt: str, tts: str) -> list[str]:
    names = ["OPENAI_API_KEY"]
    if stt == "deepgram":
        names.append("DEEPGRAM_API_KEY")
    if tts == "elevenlabs":
        names.append("ELEVENLABS_API_KEY")
    return names
```
…and add the named unit test to §7 so the duplication cannot drift. (That test
*can* import both, since it runs under pytest with dependencies installed.)

---

### F8 — Correction 3 is factually false: `check_env.py` already reads `os.environ` first. The prescribed fix is a semantic no-op, and R-L9 guards an impossible risk [MAJOR]

**Where:** Corrections §3, §5 Step 6b (second bullet), §10 R-L9.
Repo: `scripts/check_env.py:53-58, 243, 482, 495`.

**What the plan says:**
> `scripts/check_env.py:243` — `voice_base = env.get("OPENAI_BASE_URL", …)` where `env` is `load_env()` (**the `.env` file**). … it breaks on a relocated mini where the launchd wrapper is the source of truth.
> Fix: `voice_base = (os.environ.get("OPENAI_BASE_URL") or env.get("OPENAI_BASE_URL") or "https://api.openai.com/v1")`

**Why it's wrong:** `load_env()` is **not** the `.env` file. It is
`dict(os.environ)` with `.env` values applied by `setdefault`, i.e. the process
environment *wins*:

```python
# scripts/check_env.py:53-58
def load_env() -> dict[str, str]:
    """os.environ overlaid with repo .env (simple KEY=VALUE parser)."""
    env = dict(os.environ)
    for key, value in read_dotenv_only().items():
        env.setdefault(key, value)
    return env
```
`main()` binds `env = load_env()` at `:482` and passes it to
`check_model_keys(env, …)` (`:200`), so both `:243` and `:495` already have
exactly the precedence the plan says it is adding. The `.env`-only reader is a
*different* function, `read_dotenv_only()` (`:36`), used only by the D9 shadowing
check.

The proposed replacement `os.environ.get(X) or env.get(X) or default` is
therefore semantically identical to `env.get(X, default)` (differing only in
treating an empty string as absent). The plan spends a "Correction to the
roadmap", a §5 step and a risk-table row (R-L9, "reintroduces the 2026-08-19
bug") on a change that changes nothing — while §11 item 9 asserts every
correction was verified against source.

**Evidence:** the `load_env` body above; `grep -n "env = load_env()" scripts/check_env.py`
→ `482:    env = load_env()`; the in-repo comment at `:234-242` even says
"`env` (load_env()), NOT os.environ", meaning "not the bare `os.environ` dict
without the `.env` overlay" — the plan read it as the opposite.

**Fix:** delete Correction 3, delete the second bullet of §5 Step 6b, delete
R-L9. Then keep the *real* version of the problem, which the plan created and
did not notice — see F9.

---

### F9 — The plan reintroduces the exact `.env`-vs-`os.environ` split it claims to fix, for `JARVIS_STT_PROVIDER`, in three new places [MAJOR]

**Where:** §5 Step 6b (first and third bullets), §3 L12 rule 1, §5 Step 6a
rules 1/3/4, §8 E6.

**What the plan says:**
```python
REQUIRED_VARS = list(required_env_vars(
    os.environ.get("JARVIS_STT_PROVIDER", "deepgram"),
    os.environ.get("JARVIS_TTS_PROVIDER", "elevenlabs")))
...
if os.environ.get("JARVIS_STT_PROVIDER", "deepgram") == "whisper_mlx":
```
and `check_local_only.py` rule 1: `os.environ.get("JARVIS_STT_PROVIDER")` (after
`inject_env()`), rule 3: `urlparse(os.environ.get("OPENAI_BASE_URL",""))`,
rule 4: `os.environ.get("OPENAI_API_KEY","")`.

**Why it's wrong:** `JARVIS_STT_PROVIDER` is documented (§5 Step 10, README) as
an ordinary `.env` variable, and `jarvis.vault.inject_env()` copies **vault
secrets** into `os.environ` — it does not read `.env`
(`jarvis/vault.py:266-289`). `.env` reaches the process only through the run
scripts' `set -a; . ./.env` (`scripts/run_bot.sh:7-9`). So:

- On the MacBook, `python scripts/check_env.py` with `JARVIS_STT_PROVIDER=whisper_mlx`
  in `.env` still computes `REQUIRED_VARS` for `deepgram` → false `FAIL Required
  env vars present — missing: DEEPGRAM_API_KEY`, and still probes Deepgram.
  This is the same class of defect as Correction 3's claimed one, now real.
- §8 E6 says, literally, `python scripts/check_local_only.py`. Run from an
  interactive shell on the mini (which does not source `.env` — only
  `launchd_exec.sh` does), `JARVIS_STT_PROVIDER` is unset → rule 1 FAILs
  ("STT provider is 'None'"), and `OPENAI_BASE_URL` is unset → rule 3 FAILs
  (`urlparse("").hostname is None`). G3(e) fails on a correctly configured mini.

**Evidence:**
```
$ python3 -c "from urllib.parse import urlparse; print(repr(urlparse('').hostname))"
None
$ sed -n '5,9p' scripts/run_bot.sh
set -a
. ./.env
set +a
$ sed -n '279,289p' jarvis/vault.py     # inject_env(): vault secrets only
```

**Fix:** give both scripts one shared, stated resolution order and use it for
every variable they read. Add to `scripts/check_local_only.py` (and reuse the
same helper in `check_env.py`, stdlib-only per F7):

```python
def cfg(name: str, default: str = "") -> str:
    """os.environ (which inject_env() has already populated from the vault)
    first, then repo .env. Production reads exactly this order: launchd's
    wrapper and the run scripts both `set -a; . ./.env`."""
    v = os.environ.get(name)
    if v:
        return v
    return _dotenv().get(name, default)
```
and change every `os.environ.get(...)` in §5 Step 6a rules 1/3/4/5/6 and in
Step 6b's two bullets to `cfg(...)`. State it once in L12 so the two scripts
cannot drift.

---

### F10 — `SpeakerTap`'s scoring window collapses under Whisper: the mid-turn score is computed over silence, and the final score over an empty buffer [MAJOR]

**Where:** §1.3 (row 1: "**Yes** — the aggregator broadcasts both … **Timing
changes** (see §5 Step 7)"), §5 Step 7 P5, §8 B7.
Repo: `jarvis/bot/speaker_gate.py:192-215, 217-233`, `jarvis/speaker.py:55, 93-104`.

**Why it's wrong:** §1.3 notes that the timing changes and then never says what
the new timing does. Here is what it does.

`SpeakerTap` resets its audio buffer and increments `turn_id` **only** on
`UserStartedSpeakingFrame`, and scores at two moments: mid-turn once the buffer
reaches `MIN_VERIFY_SECS` (1.0 s), and finally on `UserStoppedSpeakingFrame`.
`InputAudioRawFrame` flows continuously — `VADProcessor` forwards every frame
(`pipecat/processors/audio/vad_processor.py:103-115`), so the buffer fills during
silence too.

- *Today (Flux):* `UserStartedSpeakingFrame` is broadcast by the Flux service at
  `StartOfTurn` (`flux/base.py:592`), i.e. at speech onset. The buffer resets
  there, the 1.0 s mid-turn score is computed over the user's first second of
  **speech**, and that is the score `TranscriptGate` uses.
- *After the swap:* the only `UserStartedSpeakingFrame` is the aggregator's, and
  per F2 it arrives **after** the previous turn's transcript — i.e. during
  silence, before the next utterance. The buffer resets there, fills with 1.0 s
  of **silence**, `_verified_this_turn` flips true, and `_schedule_score()` embeds
  that silence. No further scoring happens until the next reset, so the gate's
  verdict for the *next* real utterance is computed from a silence embedding.
  The subsequent `UserStoppedSpeakingFrame` then runs `_schedule_score(final=True)`
  on an empty buffer, writing `speech_secs[turn_id] = 0.0`.

Outcome: the score falls far below `DEFAULT_THRESHOLD = 0.40`, so
`speaker.verdict()` returns `"drop"` for the enrolled speaker whenever
`speech_secs ≥ 1.0`, or `"pass"` for everything whenever it does not. Either way
Tier 2 is not doing what it does today, and §8 B7's expectation
(`"speaker_gate_drop" lines = ____ (expect > 0)`) will be satisfied by drops of
the *wrong* utterances — a pass criterion that cannot distinguish working from
inverted.

**Evidence:** `jarvis/bot/speaker_gate.py:195-213`:
```python
if isinstance(frame, UserStartedSpeakingFrame):
    self._state.turn_id += 1
    self._buffer = bytearray()
    self._verified_this_turn = False
elif isinstance(frame, InputAudioRawFrame):
    ...
    if not self._verified_this_turn and accumulated_secs >= speaker.MIN_VERIFY_SECS:
        self._verified_this_turn = True
        self._schedule_score()
elif isinstance(frame, UserStoppedSpeakingFrame):
    self._schedule_score(final=True)
```
`jarvis/speaker.py:93-104` (`verdict`), `:55` (`MIN_VERIFY_SECS = 1.0`),
`:57` (`DEFAULT_THRESHOLD = 0.40`).

**Fix:** F2's `VADUserTurnStartStrategy` addition does not help `SpeakerTap`,
which listens for the non-VAD frame. Change `SpeakerTap.process_frame` to reset
on `VADUserStartedSpeakingFrame` **in addition to** `UserStartedSpeakingFrame`
(both are emitted today; the VAD one is the reliable speech-onset marker under
both providers), and add `VADUserStoppedSpeakingFrame` to the final-score branch:

```python
if isinstance(frame, (UserStartedSpeakingFrame, VADUserStartedSpeakingFrame)):
    ...
elif isinstance(frame, (UserStoppedSpeakingFrame, VADUserStoppedSpeakingFrame)):
    self._schedule_score(final=True)
```
Because `turn_id` would then increment twice per turn under Flux, guard it:
increment only when `len(self._buffer) > 0 or not self._verified_this_turn`
— or, cleaner, key the reset on `VADUserStartedSpeakingFrame` alone and stop
listening for `UserStartedSpeakingFrame`. Add `jarvis/bot/speaker_gate.py` to
§4's Modify manifest (it is currently in "Explicitly NOT touched") and add two
unit tests to §7 driving the Whisper frame order.

---

### F11 — L9's REJECT branch is unreachable, and L7's ladder contradicts its own ordering rule [MAJOR]

**Where:** §3 L7 (ladder table, STEP D branch 2), §3 L9 ("*What REJECT means,
concretely*"), §5 Step 8 S6.

**What the plan says:**
> L7 … run **in this order**, stop at the first model that passes both gates — smallest passing model wins
> L7 STEP D … IF mean >= 90% AND STEP E fails: … go to the NEXT SMALLER candidate **already tested, if any passed accuracy**
> L9 … Go back to L7's ladder and take the next **smaller** candidate that **passed both gates**.
> Step 8 S6 … take the next smaller candidate that passed both gates; if there is none, take L7's STOP branch.

**Why it's wrong — two ways.**

*(i) The branch is empty by construction.* L7 stops at the **first** candidate
that passes both gates. Every candidate tested before it **failed**. Therefore
the set "smaller candidates that passed both gates" always has cardinality zero,
and both L9's REJECT branch and Step 8's S6 always degenerate to L7's STOP branch
(cloud Supervisor, T4b stays gated). The plan presents RAM rejection as a
recoverable outcome with a fallback; it is not. An implementer following L9 will
look for a list that does not exist and be stuck — §0.1's "if two implementations
look equally good you have misread a step" gives them no way out.

*(ii) The ladder is not ordered by the quantity it claims to order by.*

| # | tag | plan's disk estimate |
|---|---|---|
| 1 | `qwen3:14b-q4_K_M` | ~9 GB |
| 2 | `qwen3:30b-a3b-instruct-q4_K_M` | ~18 GB |
| 3 | `gpt-oss:20b` | ~13 GB |
| 4 | `mistral-small3.2:24b…` | ~15 GB |
| 5 | `qwen3:32b-q4_K_M` | ~20 GB |

#3 and #4 are **smaller** than #2 but come after it, so "smallest-first" is false
for the ladder as written, and STEP D's justification for going to STOP —
"next candidate on the ladder is not the answer (**bigger is slower**)" — is also
false: #3 is a dense 20 B model and #2 is an MoE with ~3 B active, so #3 is
very likely *slower* than #2 despite being smaller on disk.

**Fix:**
1. Reorder the ladder strictly ascending by the quantity L9 uses, and say which
   quantity that is: `1 qwen3:14b (~9) → 2 gpt-oss:20b (~13) → 3 mistral-small3.2:24b (~15) → 4 qwen3:30b-a3b (~18) → 5 qwen3:32b (~20) → 6 llama3.3:70b (~43)`.
2. Replace both dead branches with a real one. Since candidates are now strictly
   ascending, the only recoverable RAM rejection is "the accepted candidate is
   too big for the largest mini you will buy", so the branch must be:
   > **REJECT:** the ladder is ascending, so no *tested* candidate is both
   > smaller and passing. Do not search backwards. Record the rejection and the
   > `REQUIRED_GB`, then take L7's STOP branch verbatim.
3. Delete "if any passed accuracy" from STEP D branch 2 and replace it with the
   same STOP text.

---

### F12 — The RAM formula double-counts headroom, and `STT_GB`'s measurement procedure does not produce the value it asks for [MAJOR]

**Where:** §3 L9, §5 Step 8 S2–S4, §8 C1.

**What the plan says:**
```
REQUIRED_GB = LLM_RESIDENT_GB + STT_GB + 0.5 + 0.5 + 3.0 + OS_HEADROOM_GB(8.0)
REJECT IF REQUIRED_GB > PHYSICAL_RAM_GB * 0.85
S2. … ps -o rss= -p $(pgrep -f "jarvis.bot.bot")
    RECORD (rss_after_first_transcription - rss_at_startup) / 1048576 -> STT_GB.
    If you cannot get a clean before/after, use 2.5.
```

**Why it's wrong — three ways.**

*(i) Headroom counted twice.* `OS_HEADROOM_GB = 8.0` is an additive term for the
OS, and `× 0.85` is a 15 % multiplicative margin whose stated purpose is *also*
keeping macOS out of trouble ("macOS begins memory compression and then swap well
before physical exhaustion"). On a 48 GB machine that is 8 + 7.2 = 15.2 GB, 32 %
of the machine, reserved twice for the same thing. The plan's own worked example
shows the cost: 35.0 GB required rejects a 36 GB mini, when actual process
demand is 27 GB. This term decides a hardware purchase (O5), so the double count
is money.

*(ii) `STT_GB` is not derivable from the step that is supposed to produce it.*
S2 gives exactly one command, run **after** speaking a turn, and then asks for
`rss_after_first_transcription − rss_at_startup`. `rss_at_startup` is never
captured by any step. Per the BRIEF's taxonomy item 7 ("every value a step needs
actually derivable"), this fails.

*(iii) The fallback is the judgment call §0.1 forbids.* "If you cannot get a
clean before/after, use 2.5" has no test for "clean" and no threshold. That is
precisely the branch the review brief asked about, and it is the branch that
will be taken (see below).

Additionally, MLX allocates in Apple's **unified** memory pool; a large fraction
of the MLX arena does not appear in `ps` RSS at all, so even a correct
before/after will under-report — meaning the 2.5 fallback will be used in
practice, making the whole S2 measurement theatre.

**Fix:**
```
S2a. Before starting the bot:            (record R0)
       ./scripts/mortimer.sh stop
       ./scripts/mortimer.sh start ; sleep 20
       ps -o rss= -p $(pgrep -f "jarvis.bot.bot") | tr -d ' '   -> R0_kb
S2b. Speak ONE turn, wait for the USER: line in logs/bot.log, then:
       ps -o rss= -p $(pgrep -f "jarvis.bot.bot") | tr -d ' '   -> R1_kb
S2c. STT_GB = max(2.5, (R1_kb - R0_kb) / 1048576)
     The max() is not a fallback: MLX allocates in unified memory that ps does
     not attribute to the process, so the RSS delta is a lower bound. 2.5 GB is
     large-v3-turbo's fp16 weights (~1.6 GB) plus the MLX arena.
```
and change the rejection rule to count headroom once:
```
REQUIRED_GB = LLM_RESIDENT_GB + STT_GB + 0.5 + 0.5 + 3.0     # processes only
REJECT IF REQUIRED_GB + OS_HEADROOM_GB(8.0) > PHYSICAL_RAM_GB
```
Re-run the worked example under the corrected rule so §3 L9 and §8 C2 agree.

---

### F13 — The two new "Whisper timing" tests are tautologies; one duplicates an existing test verbatim [MAJOR]

**Where:** §5 Step 7a, §7 (`tests/unit/test_interruption.py`, 2 new tests),
§4 Modify row for `tests/unit/test_interruption.py`.

**What the plan says:**
> §1.7: "All eight are frame-level and STT-agnostic … they cannot prove the STT swap is safe. **§5 Step 7 adds the tests that can.**"

**Why it's wrong:** neither added test involves anything Whisper changes.
`InterruptionNotifier` handles exactly five frame types
(`jarvis/bot/interruption.py:92-121`) and `TranscriptionFrame` and
`UserStoppedSpeakingFrame` are **not** among them — both fall through with no
state change.

- `test_late_transcript_does_not_arm_the_notifier` pushes
  `UserStoppedSpeakingFrame` (ignored), `TranscriptionFrame` (ignored),
  `InterruptionFrame` with `_assistant_active == False` → no note. That is
  `test_dropped_turn_with_no_reply_in_flight_produces_no_note`
  (`tests/unit/test_interruption.py:67`) with two inert frames prepended.
- `test_barge_in_still_detected_when_transcript_is_late` pushes
  `LLMFullResponseStart → LLMFullResponseEnd → BotStartedSpeaking → Interruption`
  and expects `INTERRUPTION_NOTICE_MID_SPEECH`. That is byte-for-byte the frame
  sequence of the existing `test_mid_speech_interruption`
  (`tests/unit/test_interruption.py:104-118`). The docstring's claim ("even
  though the interrupting utterance's transcript has not arrived yet") is
  untestable here because the notifier never reads a transcript in any
  configuration.

So §1.7 promises tests that can prove the swap safe and then supplies two that
provably cannot — the plan's own stated failure mode.

**Evidence:** `jarvis/bot/interruption.py:92-121` — the only `isinstance` checks
are `LLMFullResponseStartFrame`, `LLMFullResponseEndFrame`,
`BotStartedSpeakingFrame`, `BotStoppedSpeakingFrame`, `InterruptionFrame`.
`tests/unit/test_interruption.py:104-118` (the duplicate).

**Fix:** delete both tests. The behaviour that actually changes lives in the turn
controller, so the test that can prove it must drive that. Add to §7, in a new
`tests/unit/test_turn_ordering.py`:

```python
async def test_whisper_ordering_starts_turn_before_stop_strategy_sees_transcript():
    """Under a SegmentedSTTService the only transcript arrives after VAD stop,
    so the start strategy fires the turn and RESETS the stop strategies before
    the same frame reaches them (pipecat user_turn_controller.py:161-171,276-278).
    Asserting the observable consequence: the turn-analyzer verdict recorded at
    VAD stop does NOT decide end-of-turn."""
```
driving a real `UserTurnController` with `start=[MinWordsUserTurnStartStrategy(min_words=2)]`,
`stop=[TurnAnalyzerUserTurnStopStrategy(turn_analyzer=<stub returning INCOMPLETE>)]`,
and the frame sequence `VADUserStarted → audio → VADUserStopped →
TranscriptionFrame(finalized=True)`. Assert `on_user_turn_stopped` fires even
though the analyzer said INCOMPLETE. That test fails today and documents F3.

---

### F14 — `check_local_only.py` rule 4 passes a configuration in which the bot cannot start; rule 5's failure message is unspecified [MINOR]

**Where:** §3 L12 rules 4–5, §5 Step 6a table rows 4–5, §7
`test_check_local_only.py` #7.

**What the plan says:**
> 4. `OPENAI_API_KEY` must be exactly the sentinel `local`, **or absent**.
> 5. … Absent → print `note: TTS credential absent; …` and FAIL only if `JARVIS_TTS_PROVIDER != "kokoro"` | **Failure message: —**

**Why it's wrong:**
- Rule 4's "or absent" branch: §3 L5 makes `OPENAI_API_KEY` **unconditionally
  required**, and §5 Step 1's `load_settings()` raises
  `"Missing required environment variables: OPENAI_API_KEY"`. So a machine where
  `OPENAI_API_KEY` is absent passes G3(e) and cannot boot the bot. A gate that
  passes on a dead system is exactly the "gate met without the feature working"
  case.
- Rule 5's Failure message cell is literally `—`, yet the rule can FAIL. The
  implementer must invent the string, violating §0.1 and taxonomy item 5
  ("copy … named but unspecified"), and §11 item 5 claims all six message shapes
  are written out.

**Fix:** rule 4 → `must be exactly the sentinel "local"` (drop "or absent"),
failure message
`FAIL OPENAI_API_KEY must be the sentinel 'local' for a local server (absent means the bot cannot start — see jarvis/config.py required_env_vars)`.
Rule 5 failure message →
`FAIL ELEVENLABS_API_KEY absent but JARVIS_TTS_PROVIDER is '<v>'; the voice loop has no TTS`.

---

### F15 — §8 A1's record sheet uses the wrong denominator: the routing eval has 68 cases, not 65 [MINOR]

**Where:** §8 A1.

**What the plan says:** `routing_eval run 1: ____/65 = ____%`

**Evidence:**
```
$ python3 -c "import yaml;print(len(yaml.safe_load(open('tests/evals/cases.yaml'))))"
68
$ head -6 tests/evals/cases.yaml
# … 3 troubleshooting->developer (2026-08-20) = 68 total.
```

**Fix:** `____/68`. (If the sibling MAIL_CALENDAR plan's K6 adds ≥ 12 secretary
utterances first, the denominator moves again — say "`____/<N>` where N is the
count printed by the eval" instead of hard-coding it.)

---

### F16 — §1.7 says "9 tests" and lists 8; §11 item 7's manifest claim is graded against the wrong count [MINOR]

**Where:** §1.7 opening line vs its own list and the later "All eight are
frame-level".

**Evidence:** `grep -c "def test_" tests/unit/test_interruption.py` → `8`.

**Fix:** "8 tests in two classes".

---

### F17 — §4's justification for keeping `REQUIRED_ENV_VARS` is false; nothing outside `jarvis/config.py` imports it [MINOR]

**Where:** §4 Modify row for `jarvis/config.py`
("keeping the constant as its default-args value for `scripts/check_env.py`")
vs §5 Step 1's inline comment
("scripts/check_env.py imports the function, not this").

**Evidence:**
```
$ grep -rn "REQUIRED_ENV_VARS" --include=*.py .
./jarvis/config.py:28:REQUIRED_ENV_VARS = ("OPENAI_API_KEY", "DEEPGRAM_API_KEY", "ELEVENLABS_API_KEY")
./jarvis/config.py:213:        missing = [name for name in REQUIRED_ENV_VARS if not os.environ.get(name)]
```
`scripts/check_env.py:22` has its own literal `REQUIRED_VARS` list and imports
nothing from `jarvis`. Line 213 is the only other use and §5 Step 1 deletes it.
Two sections describing the same thing differently — taxonomy item 4, which §11
item 4 claims was swept.

**Fix:** either delete `REQUIRED_ENV_VARS` outright (nothing reads it after
Step 1) or keep it with an accurate comment (`# kept for import-compatibility;
no in-repo consumer as of T3`).

---

### F18 — §5 Step 5b's fallback instruction is factually wrong about scope [MINOR]

**Where:** §5 Step 5b.

**What the plan says:**
> (If `runtime` is not in scope at that line, use the `settings` local that `build_pipeline` already binds at `:334`; the handler is a closure inside the same module.)

**Why it's wrong:** `jarvis/bot/pipeline.py:1067` is inside `run_session`
(which starts at `:737`), not inside `build_pipeline` (`:330-694`). Being "in the
same module" does not put another function's local in scope. Both suggested names
happen to work — `run_session` binds `settings` and constructs
`runtime = Runtime(settings=settings, …)` at `:827` — but the stated reason is
wrong and would mislead a model that tried to verify it.

**Fix:** "Line 1067 is inside `run_session`, which binds both `settings` and
`runtime` (`jarvis/bot/pipeline.py:827`). Use `settings`."

---

### F19 — `providers.py` uses a bare `assert` as a production guard [MINOR]

**Where:** §5 Step 2, `build_stt`:
```python
assert MLXModel.LARGE_V3_TURBO.value == WHISPER_MODEL, (...)
```

**Why it's wrong:** `python -O` strips asserts, so the guard R-L7 relies on is
absent from any optimized run, and an assert is not the failure mode a launchd
service wants (a bare `AssertionError` in `bot.log` with `KeepAlive` restarting
into it forever). §7 test #4 covers the same check at test time, which is where
it belongs.

**Fix:** delete the assert from `build_stt`; keep test #4 (guarded per F1).

---

### F20 — `WhisperSTTServiceMLX` never sets `ttfs_p99_latency`, so every startup logs a Pipecat warning and the turn-stop timeout uses a default the plan never mentions [MINOR]

**Where:** §3 L4 (the four settings), §6 (Whisper knobs).

**Evidence:** `pipecat/services/stt_service.py:504-508`:
```python
ttfs = self._ttfs_p99_latency
if ttfs is None:
    ttfs = DEFAULT_TTFS_P99
    logger.warning(f"{self.name}: ttfs_p99_latency not set, using default {ttfs}s")
```
`pipecat/services/stt_latency.py:38,65` — `DEFAULT_TTFS_P99 = 1.0`,
`WHISPER_TTFS_P99 = DEFAULT_TTFS_P99`. Flux by contrast declares
`supports_ttfs → False` (`deepgram/flux/stt.py:244-247`) and broadcasts `0.0`, so
today `_stt_timeout` is 0 — the swap changes it to 1.0 and the plan's §6 knob
table does not own the number.

**Fix:** pass `ttfs_p99_latency=WHISPER_TTFS_P99` in `build_stt`'s whisper branch
(import from `pipecat.services.stt_latency`), add it to §6 as
`jarvis/bot/providers.py WHISPER_TTFS_P99_S = 1.0`, and note in L8 that this
value participates in `max(0, ttfs - stop_secs)`
(`turn_analyzer_user_turn_stop_strategy.py`), so lowering `stop_secs` below 1.0
would *add* latency — a second reason the floor exists.

---

### F21 — §5 Step 7's `JARVIS_STT_PROVIDER=… ./scripts/mortimer.sh` prefix is silently overridden by `.env`, and P0 (the baseline) has no verification line [MINOR]

**Where:** §5 Step 7 P0, P1, P4(c).

**Why it's wrong:** `mortimer.sh` backgrounds `./scripts/run_bot.sh`
(`scripts/mortimer.sh:84`), and `run_bot.sh:5-9` does `set -a; . ./.env; set +a`
— which **overwrites** an inherited value with the `.env` one. Once
`JARVIS_STT_PROVIDER` is in `.env` (which §5 Step 9.6 and §5 Step 10's README
row make the normal configuration), the command prefix in P0/P1/P4 has no effect.
P1 has a log-line check that catches this; **P0 does not**, so a baseline
accidentally measured on Whisper would be recorded as `B_ms` and the whole gate
would compare Whisper to Whisper.

**Fix:** add to P0, verbatim:
```
Confirm logs/bot.log carries exactly one line matching
  "voice_providers stt=deepgram ".
If it says whisper_mlx, JARVIS_STT_PROVIDER is set in .env — comment it out
there (run_bot.sh's `set -a; . ./.env` overrides the command prefix) and redo P0.
```

---

### F22 — launchd log growth is named as a risk but no rotation is actually specified [MINOR]

**Where:** §5 Step 9.4 ("add a `newsyslog`-style note that the runbook's
maintenance section owns"), §10 R-L8 (likelihood **certain**).

**Why it's wrong:** the mitigation for a certain-likelihood risk is "the runbook
has a section that owns a note" — no file, no rotation interval, no size cap, no
command. The implementer writes `docs/runbooks/MAC_MINI_RELOCATION.md` and has
nothing to write there. Also note that `scripts/latency_probe.py` reads
`logs/bot.log` and P5's `grep -c` counts lines in it, so an unrotated
multi-gigabyte log degrades both instruments.

**Fix:** specify it. Add to §4's Create list
`deploy/newsyslog.d/mortimer.conf` and to §5 Step 9.4:
```
sudo tee /etc/newsyslog.d/mortimer.conf >/dev/null <<'EOF'
# logfile                                  owner:group  mode count size(KB) when flags
/Users/USERNAME/mortimer/logs/bot.log      USERNAME:staff 644  5     102400   *    J
/Users/USERNAME/mortimer/logs/admin.log    USERNAME:staff 644  5     102400   *    J
/Users/USERNAME/mortimer/logs/ollama.log   USERNAME:staff 644  3     102400   *    J
EOF
```
and add a §8 E-row: `E8. ls -l logs/*.log* after 3 days — none exceeds 100 MB?`

---

## What I verified and found correct

- **Correction 1's mechanism** — `UserTurnStrategies.__post_init__`
  (`pipecat/turns/user_turn_strategies.py:74-79`) does fill an unset `stop` with
  `default_user_turn_stop_strategies()` (`:43-51`), which does return
  `[TurnAnalyzerUserTurnStopStrategy(turn_analyzer=LocalSmartTurnAnalyzerV3())]`.
  `jarvis/bot/pipeline.py:631-638` does pass only `start=`. `onnxruntime==1.24.4`
  (`requirements-lock.txt:103`) and `soxr==1.0.0` (`:169`) are pinned.
  `DEVIATIONS.md:81-88` (D-010) confirms it in prose. **The claim is true as a
  statement about today** — F3 is about what happens to it after the swap, not
  about this.
- **`params.enable_user_speaking_frames` defaults `True`** —
  `pipecat/turns/user_start/base_user_turn_start_strategy.py:56` and
  `user_stop/base_user_turn_stop_strategy.py:60`. The aggregator does broadcast
  `UserStartedSpeakingFrame`/`UserStoppedSpeakingFrame` at
  `llm_response_universal.py:1182` / `1236`, and `broadcast_frame`
  (`processors/frame_processor.py:737-753`) does push both upstream and
  downstream, so upstream processors do receive them. **Which frames exist is
  right; when they exist is F2/F10.**
- **Correction 2's blocking half** — `jarvis/config.py:28` is
  `REQUIRED_ENV_VARS = ("OPENAI_API_KEY","DEEPGRAM_API_KEY","ELEVENLABS_API_KEY")`;
  `:52`, `:57`, `:58` declare the three keys with no defaults; `load_settings()`
  turns a miss into `RuntimeError` at `:213-219`. G3(e) is genuinely
  unsatisfiable today. The `required_env_vars()` design is sound and
  `getattr(settings, name.lower())` resolves correctly for all three names.
- **The two existing `test_config.py` tests survive Step 1** — `:33` matches
  `"OPENAI_API_KEY"` and `:38` asserts both other names appear; the rewritten
  message still contains all three. `test_bad_timezone_raises` (`:46`) matches
  `"Configuration error"`, which the new `except` branch still emits.
- **`OPENAI_BASE_URL` reaches the Supervisor** — `jarvis/bot/pipeline.py:520-524`;
  the Google branch keys on `"generativelanguage.googleapis.com" in
  settings.openai_base_url` (`:512`), so a loopback URL falls through to
  `OpenAILLMService`. `pipecat/services/ollama/llm.py` is indeed
  `OpenAILLMService(base_url=…, api_key="ollama")`.
- **Correction 4** — `config/upgrade_models.yaml` does name `MOONSHOT_API_KEY`
  (`:66,76`), `ANTHROPIC_API_KEY` (`:86,103`) and `OPENROUTER_API_KEY`
  (`:140,150,160,170,180,190,206,216,226`). Removing them would break delegation.
  The default/`--strict` split is the right resolution.
- **`MLXModel.LARGE_V3_TURBO == "mlx-community/whisper-large-v3-turbo"`**
  (`pipecat/services/whisper/stt.py:99`), and the constructor's default really is
  `MLXModel.TINY` (`:440-446`) — the trap L4 closes is real. The delta-`Settings`
  reasoning is correct: `ServiceSettings.apply_update` merges only *given* fields
  (`pipecat/services/settings.py:226-243`).
- **`SegmentedSTTService` marks every `TranscriptionFrame` finalized**
  (`pipecat/services/stt_service.py:752-764`) and emits exactly one per segment;
  it emits no interim and no speaking frames. Correction 5's frame inventory is
  accurate.
- **`SmartTurnParams` defaults** — `stop_secs=3`, `pre_speech_ms=500`,
  `max_duration_secs=8` (`base_smart_turn.py:27-30,32-44`). (It is a
  `BaseTurnParams` pydantic model, not a dataclass — cosmetic.)
- **`TranscriptionFrame`'s positional order** — `(text, user_id, timestamp,
  language=None, result=None, finalized=False)` (`pipecat/frames/frames.py:444-464`);
  the plan's four-argument call is legal. `UserStoppedSpeakingFrame`,
  `InterruptionFrame`, `LLMFullResponse*Frame` and `BotStartedSpeakingFrame` are
  all already imported at `tests/unit/test_interruption.py:17-24`, so only
  `TranscriptionFrame` needs adding — as the plan says.
- **`STT_KEYTERMS` is at `jarvis/bot/pipeline.py:324`** and used at `:483`, so
  passing it as a parameter to avoid the `providers ↔ pipeline` cycle is correct.
  The ElevenLabs import path matches `pipeline.py:104-107`. `voice_switch.py:89`
  and `pipeline.py:1067` are indeed the two other `elevenlabs_voice_id` reads, and
  `build_set_voice_tool`'s only non-test caller is `pipeline.py:352` — a defaulted
  third parameter breaks nothing (`tests/unit/test_voice_switch.py:53,64` pass two).
- **`jarvis/vault.py` key order** — `_load_key()` at `:104-125` checks
  `JARVIS_VAULT_KEY` first, treats a malformed value as an error not a
  fall-through (`_decode_key`, `:90-101`), and only then consults
  `keyring.get_password("mortimer","vault-key")`. There is no `import-key`
  command; `export-key` prints base64 to stdout; `init` refuses when the file
  exists. The runbook's "copy the vault file first / never `rotate-key` on the
  mini" warnings are correct and well placed.
- **Eval harness** — `tests/evals/routing_eval.py:30` `ACCURACY_THRESHOLD = 0.90`;
  `_apply_candidate_overrides` reads `EVAL_MODEL` → `OPENAI_MODEL`,
  `EVAL_BASE_URL` → `OPENAI_BASE_URL`, and `EVAL_KEY_ENV` as a *name* whose value
  becomes `OPENAI_API_KEY` (`:62-73`), applied **after** `inject_env()` so the
  override wins. `scripts/voice_model_bench.py` exists.
- **Latency instrument** — `scripts/latency_probe.py:21` regex matches the line
  printed at `jarvis/bot/transcript_log.py:127`; the constants
  `P50_NON_DELEGATED_TARGET_MS=1200`, `P50_DELEGATED_TARGET_MS=2500`,
  `P90_OVERALL_TARGET_MS=3500` are at `:24-26` with `enforce_budget` at `:89`.
  (What it measures is F4's problem; the citations are right.)
- **`stop_secs` lives in exactly one place** — `jarvis/bot/pipeline.py:678` is the
  only occurrence in `jarvis/`, `scripts/` or `tests/`.
- **The deny-list audit** — `config/self_edit_allowlist.json` `allow` contains
  `docs/**` and `*.md` but no `scripts/**`, `deploy/**` or `jarvis/config.py`;
  `deny` already covers `jarvis/bot/**`, `requirements*.txt`, `DEVIATIONS.md`,
  `config/upgrade_models.yaml` and `jarvis/vault.py`. Adding `docs/runbooks/**`
  is the correct minimal addition and does not overlap the two sibling plans'
  entries.
- **The loopback rule is not a security hole.** Run against adversarial URLs it
  rejects `http://127.0.0.1@evil.com/v1` (hostname `evil.com`) and
  `http://localhost.evil.com/v1`, and accepts `http://LOCALHOST:11434/v1`
  (urlparse lowercases). It false-FAILs `127.0.0.1:11434/v1` (no scheme),
  `http://127.0.0.2:…` and `http://[::ffff:127.0.0.1]:…` — all harmless, since a
  scheme-less base URL would break httpx anyway.
- **K7 compliance** — the three variable names, their exact value sets and their
  defaults match `/home/claude/plans/BRIEF.md` K7 exactly; no parallel LLM knob is
  introduced; `OPENAI_BASE_URL`/`OPENAI_MODEL`/`OPENAI_API_KEY` are reused as K7
  instructs. K1/K2/K5 are cited, not restated, and `jarvis/bind.py`,
  `jarvis/auth.py`, `jarvis/urls.py` are correctly declared out of scope (§0.4).
- **Non-goals and rollback** — every switch's default is today's behaviour, there
  is no schema migration, and the "unset environment is a full rollback" claim
  holds for T3.2/T3.3/T3.4 (F5's launchd/key work is the part that is not
  reversible by an env var, and §9 does list `rm` of the key file).
