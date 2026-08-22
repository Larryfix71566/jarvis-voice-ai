# Mortimer — Voice Isolation Tiers 1+2: Noise Suppression + Speaker Gate

**Status: APPROVED by Larry 2026-08-21 — ready for implementation.**
Author: Claude (Fable), 2026-08-21. Requested by Larry: *"clean up other
voices. do we employ some type of user identification so that unknown
voices are ignored? … let's implement tier 1 and 2 and then test
effectiveness before deciding anything further."*

**Implementer contract.** This plan is written to be implemented by any
model without making design decisions. Every choice below is LOCKED —
where an external API might differ from what is stated, the step includes
a verification command and a fully specified fallback. If something is
genuinely impossible as written, STOP and report the exact failing step
and observed error; do not substitute a different design. Do not touch
anything outside the files this plan names. Camera/face identification
(Tier 3) and target-speaker extraction (Tier 4) are explicitly OUT OF
SCOPE — do not scaffold for them.

---

## 0. Context — what already exists (verified 2026-08-21)

- **Server-side NS is scaffolded, not enabled.** `jarvis/audio/filters.py`
  has `DeepFilterNetFilter`, an RNNoise filter, `NullAudioFilter`, and a
  `build_audio_filter(settings)` factory (returns None when disabled).
  `jarvis/bot/bot.py` already wires the result into
  `TransportParams(audio_in_filter=...)`. `jarvis/config.py` has
  `jarvis_ns_enabled` (default False), `jarvis_ns_filter`
  (default "deepfilternet"), `jarvis_ns_atten_lim_db`,
  `jarvis_ns_post_filter`, `jarvis_ns_log_stats`. `scripts/eval_ns.py` is
  the eval harness. The ONLY missing piece is the engine packages
  (commented out at the bottom of `requirements.txt`).
- **Browser-side capture hardening is live** (`installMicConstraints()` in
  `web/src/jarvisClient.ts`) — do not touch it.
- **No speaker identity exists anywhere.** Silero VAD detects speech, not
  speakers. Anyone near the mic is treated as Larry.
- **Pipeline** (`jarvis/bot/pipeline.py` ~line 508): transport →
  `VADProcessor(vad_analyzer=SileroVADAnalyzer(params=VADParams(stop_secs=2.5)))`
  → `DeepgramFluxSTTService(should_interrupt=True)` → context aggregator →
  LLM → TTS. pipecat version is **0.0.108** (`python -c "import pipecat"`
  prints it). `MinWordsInterruptionStrategy` import verified available at
  `pipecat.audio.interruptions.min_words_interruption_strategy`.
  `VADParams` fields verified: `confidence, start_secs, stop_secs,
  min_volume`.
- **Relevant repo disciplines that bind this plan:** logic pure / IO
  injected (every `logic.py`); kill switch enforced at ONE point; fail-open
  when a safety feature cannot run (mirror `keyhealth`'s "unknown is not
  unusable"); no second implementation of an existing thing; `data/**` is
  gitignored and self-edit-denied.

## 1. Locked decisions (the "why" — implementer reads, does not revisit)

| # | Decision | Rationale |
|---|---|---|
| L1 | NS engines: install BOTH `deepfilternet` and `pyrnnoise`; runtime default stays `jarvis_ns_filter=deepfilternet` | Tier 2 pulls torch anyway (speechbrain), so DFN's torch cost is already paid. RNNoise stays installed as the measured fallback if DFN's real-time factor is too high on Larry's machine (eval harness decides, not opinion). |
| L2 | Speaker embedding model: SpeechBrain ECAPA-TDNN, source `speechbrain/spkrec-ecapa-voxceleb`, savedir `data/models/ecapa` | Best accuracy/effort ratio; local inference; the model is downloaded ONCE by the enrollment CLI, never at bot boot — a fresh checkout with no model boots normally with the gate inert (fail-open). |
| L3 | Enrollment is file-based via CLI (`python -m jarvis.speaker enroll <wav...>`) | The mic lives in the browser; capturing enrollment audio through the WebRTC path is a project in itself. Recording 3 short WAVs with QuickTime is a one-time 2-minute task. |
| L4 | Profile storage: `data/speaker_profile.json` (metadata + per-file scores) + `data/speaker_profile.npy` (mean embedding, float32) | `data/**` is already gitignored and self-edit-denied. NOT the vault: the vault is CLI-managed secrets transported via env; a numpy array is neither. |
| L5 | Gate policy — an utterance PASSES when ANY of: cosine ≥ threshold (default **0.40**, env `JARVIS_SPEAKER_THRESHOLD`); speech duration < **1.0 s** (`MIN_VERIFY_SECS` — "yes"/"commit" carry too little voiceprint to judge); no profile enrolled; model not on disk; any error anywhere in the gate | Fail-open everywhere: this is convenience filtering (defeat the TV, houseguests), NOT security — a recording of Larry defeats it, and the plan says so rather than pretending otherwise. Silently eating Larry's own "yes" is the worst failure this feature can have. |
| L6 | A dropped utterance is dropped SILENTLY (log line + optional UI event, no spoken reply) | Talking back to the TV is worse than ignoring it. |
| L7 | v1 gates TRANSCRIPTS only. Unknown voices can still trigger a barge-in interruption of Mortimer's TTS | Gating the interruption itself needs a verdict BEFORE end-of-speech (streaming verification against Flux's internal turn logic). Barge-in survival (2026-08-21) already makes interruptions non-destructive, and Tier 1b reduces spurious ones. Revisit only with live evidence this is insufficient. |
| L8 | Kill switches: `JARVIS_SPEAKER_GATE_ENABLED` (default **false** — opt-in until effectiveness is proven) enforced at the single pipeline registration site; `JARVIS_NS_ENABLED` stays the NS switch it already is | House pattern (ui_control, screen vision): a disabled feature is not registered at all. |
| L9 | Verification runs on a THREAD (`asyncio.to_thread`), computed incrementally: first verdict at 1.0 s of accumulated speech, refreshed at end-of-utterance | Flux streams finals; waiting for end-of-utterance alone would make the gate miss fast transcripts. The transcript gate holds a frame at most `GATE_HOLD_TIMEOUT_S = 0.6` then fails open. |
| L10 | New python deps go in `requirements.txt` with comments; `requirements-lock.txt` regenerated by the implementer with `uv pip freeze` after install | Dependency changes are human-driven by policy (self-edit denies requirements*); this plan IS the human-driven change. |

## 2. Tier 1a — enable noise suppression

**Files: `requirements.txt`, `.env.example`, `README` section optional.**

1. In `requirements.txt`, replace the commented Workstream-A block at the
   bottom with active lines:
   ```
   # Voice isolation Tier 1 (MORTIMER_VOICE_ISOLATION_TIER12_PLAN.md):
   # both engines installed; JARVIS_NS_FILTER picks at runtime
   # (deepfilternet default, rnnoise the measured fallback).
   deepfilternet
   pyrnnoise
   pystoi          # scripts/eval_ns.py metric
   ```
2. Install: `uv pip install -r requirements.txt`, then regenerate the lock
   (`uv pip freeze > requirements-lock.txt`).
3. `.env.example`: document `JARVIS_NS_ENABLED=true`,
   `JARVIS_NS_FILTER=deepfilternet`, and the fallback line
   `# JARVIS_NS_FILTER=rnnoise  # if [ns] RTF logs exceed 0.8`.
4. **Verification (must run, results recorded in §6):**
   - `python -c "from df.enhance import init_df; print('dfn ok')"`
   - `python scripts/eval_ns.py --help` runs; then run it per its own
     usage against a noisy sample (the script documents its inputs).
   - Boot the bot with `JARVIS_NS_ENABLED=true`; confirm `[ns]` RTF
     telemetry lines appear in `logs/bot.log` and RTF < 0.8. If RTF ≥ 0.8,
     set `JARVIS_NS_FILTER=rnnoise` in `.env` and record that as the
     outcome — this is the L1 fallback, not a failure.

## 3. Tier 1b — barge-in requires real words

**File: `jarvis/bot/pipeline.py` (PipelineTask construction, ~line 657).**

1. Primary approach: pass an interruption strategy to the task's params:
   ```python
   from pipecat.audio.interruptions.min_words_interruption_strategy import (
       MinWordsInterruptionStrategy)
   from pipecat.pipeline.task import PipelineParams
   task = PipelineTask(pipeline, params=PipelineParams(
       interruption_strategies=[MinWordsInterruptionStrategy(min_words=2)],
   ), observers=observers)
   ```
   Adapt to the EXISTING `PipelineTask(...)` call — add params, keep
   observers exactly as they are. If `PipelineParams` has no
   `interruption_strategies` field in 0.0.108 (check:
   `python -c "from pipecat.pipeline.task import PipelineParams; print(list(PipelineParams.model_fields))"`),
   use the field name that IS present for interruption strategies; if none
   exists at all, **skip Tier 1b entirely and record that in §6** — do not
   invent a replacement mechanism.
2. **Verification:** live test — while Mortimer is speaking, cough or say
   one word ("hm"): speech continues. Say a 3+ word sentence: it
   interrupts. Record both outcomes in §6. If interruption stops working
   entirely (Flux's `should_interrupt` may bypass strategies), REVERT this
   step and record that: Tier 1b is expendable, broken barge-in is not.

## 4. Tier 2 — speaker gate

### 4.1 `jarvis/speaker.py` (new module — profile, scoring, policy)

Pure policy separated from torch, matching the repo's logic/IO split:

- Constants: `MIN_VERIFY_SECS = 1.0`, `GATE_HOLD_TIMEOUT_S = 0.6`,
  `DEFAULT_THRESHOLD = 0.40` (env `JARVIS_SPEAKER_THRESHOLD` read once),
  `MODEL_DIR = Path("data/models/ecapa")`,
  `PROFILE_JSON = Path("data/speaker_profile.json")`,
  `PROFILE_NPY = Path("data/speaker_profile.npy")`,
  `KILL_SWITCH_ENV = "JARVIS_SPEAKER_GATE_ENABLED"` with `enabled()`
  defaulting **False** (note: opposite default from every other kill
  switch in the repo, per L8 — copy `keyhealth.enabled()` and flip:
  `value.strip().lower() in ("true", "1", "yes")`).
- `verdict(score: float | None, speech_secs: float, profile_loaded: bool) -> str`
  — pure, returns `"pass"` or `"drop"` per L5. `score=None` (not yet
  computed / error) → `"pass"`.
- `load_profile() -> np.ndarray | None` — None on any failure, logged once.
- `cosine(a, b) -> float` — plain numpy.
- `class Encoder` — lazy torch/speechbrain wrapper. `__init__(model_dir)`;
  `.load() -> bool` (False + one log line if `model_dir` missing or import
  fails — NEVER downloads); `.embed(pcm16: bytes, sample_rate: int) ->
  np.ndarray | None` (mono int16 → float32 tensor → ECAPA embedding;
  None + log on any exception). Import speechbrain as
  `from speechbrain.inference.speaker import EncoderClassifier`; if that
  import path fails, try `from speechbrain.pretrained import
  EncoderClassifier` (API moved across speechbrain 1.x) — both attempts in
  one try-chain, give up quietly after the second.

### 4.2 `python -m jarvis.speaker` CLI (same file, `__main__` block)

- `enroll <wav> [<wav> ...]` — downloads the model to `MODEL_DIR` if
  absent (`EncoderClassifier.from_hparams(source="speechbrain/spkrec-ecapa-voxceleb", savedir=str(MODEL_DIR))`
  — the ONE place download happens), embeds each file (soundfile or
  torchaudio for reading; add `soundfile` to requirements.txt), writes the
  MEAN embedding to `PROFILE_NPY` and metadata to `PROFILE_JSON`:
  `{"files": [...], "pairwise_scores": [...], "created_at": iso}` where
  pairwise_scores are the cosine similarities between the individual file
  embeddings and the mean — printed to the user as a calibration readout
  ("your own samples score 0.61–0.78 against your profile; the 0.40
  threshold has this much margin"). Requires ≥ 2 files; refuse 1.
- `verify <wav>` — prints the cosine score against the stored profile and
  the pass/drop verdict at the current threshold. This is the offline
  effectiveness tool: run it on a recording of the TV.
- `status` — profile present? model present? threshold? gate enabled?

### 4.3 Pipeline integration (`jarvis/bot/pipeline.py`)

Two small `FrameProcessor` subclasses defined in a new file
`jarvis/bot/speaker_gate.py` (keeps pipeline.py from growing), wired in
`build_pipeline` ONLY when `speaker.enabled()` AND a profile loads AND
`Encoder.load()` succeeds — otherwise neither processor is inserted and
one log line says why (`speaker_gate_inactive reason=...`).

- `SpeakerTap` — placed immediately AFTER the `VADProcessor`, BEFORE the
  STT service. Passes every frame through untouched. On
  `UserStartedSpeakingFrame`: clear buffer, start accumulating copies of
  `InputAudioRawFrame.audio` (bounded: `MAX_BUFFER_SECS = 12`). When
  accumulated speech first reaches `MIN_VERIFY_SECS`, and again on
  `UserStoppedSpeakingFrame`: schedule `asyncio.to_thread(encoder.embed, ...)`,
  store `(turn_id, score)` into the shared `GateState` (a plain object
  created in build_pipeline and handed to both processors). `turn_id` is a
  monotonically increasing int incremented on each
  `UserStartedSpeakingFrame`.
  - Exact frame class names to import (verify they exist in 0.0.108 with
    `python -c "from pipecat.frames.frames import InputAudioRawFrame, UserStartedSpeakingFrame, UserStoppedSpeakingFrame, TranscriptionFrame, InterimTranscriptionFrame; print('ok')"`;
    if any is missing, find its 0.0.108 name in
    `.venv/.../pipecat/frames/frames.py` and use that — record the
    substitution in §6).
- `TranscriptGate` — placed immediately AFTER the STT service, BEFORE the
  context aggregator. Passes everything through EXCEPT
  `TranscriptionFrame` (final transcripts). For those: consult
  `GateState` for the current turn's score; if no score yet, hold the
  frame up to `GATE_HOLD_TIMEOUT_S` (async sleep loop, 50 ms steps), then
  apply `verdict(score, speech_secs, True)`. `"pass"` → push the frame
  downstream unchanged. `"drop"` → do not push; log
  `speaker_gate_dropped score=%.2f secs=%.1f text_len=%d` (never log the
  text itself — an unknown speaker's words should not enter logs); send
  one app message `{"type": "speaker_gate", "verdict": "dropped"}` via the
  existing `send_app_message` so the console can show it later (no UI work
  in this plan — the message is fire-and-forget).
  `InterimTranscriptionFrame`s pass through untouched (they feed captions
  only; acting on them would double the gate's latency budget).
- **Ordering note for the implementer:** the pipeline list in
  `build_pipeline` is explicit; insert `tap` after the `VADProcessor`
  element and `gate` after the STT element. Nothing else moves.

### 4.4 Config & docs

- `jarvis/config.py`: no new Settings fields (the gate reads its two env
  vars directly, like `JARVIS_SCREEN_ENABLED` does) — do NOT add fields.
- `.env.example`: document `JARVIS_SPEAKER_GATE_ENABLED` (default false,
  what it does, enrollment prerequisite, the L5 pass conditions) and
  `JARVIS_SPEAKER_THRESHOLD`.
- `CLAUDE.md`: one paragraph under a "Speaker gate" heading: what it is,
  L5 policy, L7 limitation, fail-open discipline, kill switch, CLI.

## 5. Tests (`tests/unit/test_speaker.py`, `tests/unit/test_speaker_gate.py`)

No torch, no network, no model files in unit tests — `Encoder` is never
constructed; policy and gate logic take injected fakes.

| test | pins |
|---|---|
| `test_verdict_passes_above_threshold` | L5 arithmetic |
| `test_verdict_drops_below_threshold` | L5 arithmetic |
| `test_short_utterance_always_passes` | L5: < 1.0 s never judged |
| `test_no_score_passes` | L9/L5: verdict before embedding = pass |
| `test_no_profile_disables_gate_not_pipeline` | wiring guard: `build_pipeline` with gate enabled but no profile inserts NO gate processors (inspect pipeline element list) |
| `test_kill_switch_defaults_off` | L8: unset env = disabled |
| `test_gate_holds_then_fails_open` | fake GateState never delivers a score; TranscriptionFrame emerges after ≤ 0.6 s + margin |
| `test_gate_drops_unknown_speaker` | score 0.1 delivered; frame not forwarded; log line emitted |
| `test_gate_never_logs_transcript_text` | the drop log record does not contain the frame's text |
| `test_interim_frames_pass_untouched` | caption latency unaffected |
| `test_profile_roundtrip` | save/load mean embedding via tmp_path (numpy only) |
| `test_enroll_refuses_single_file` | L4/§4.2 |

Also: `pytest tests/unit -q` fully green; `cd web && npm run build` clean
(no web changes expected — this catches accidents).

## 6. Effectiveness protocol (Larry runs; results appended HERE)

1. Enroll: record 3 WAVs of ~20 s natural speech (QuickTime → File →
   New Audio Recording; convert if needed:
   `afconvert in.m4a out.wav -d LEI16 -f WAVE`). Run
   `python -m jarvis.speaker enroll a.wav b.wav c.wav`. Record the
   printed self-scores.
2. Offline check: record ~10 s of TV/podcast speech the same way; run
   `python -m jarvis.speaker verify tv.wav`. Expect score well below
   0.40. If ≥ 0.40, raise `JARVIS_SPEAKER_THRESHOLD` to midway between
   the TV score and your lowest self-score; re-verify both.
3. Live: set `JARVIS_SPEAKER_GATE_ENABLED=true`, restart, then:
   - Speak 10 normal commands → expect 10 answered, 0
     `speaker_gate_dropped` lines for them.
   - Play TV speech near the mic for 2 minutes → expect
     `speaker_gate_dropped` lines and NO Mortimer responses to it.
   - Say 5 one-word confirmations ("yes", "confirm") → all must land
     (the < 1.0 s bypass).
4. NS: with `JARVIS_NS_ENABLED=true`, `[ns]` RTF from logs, and a
   subjective before/after on transcript quality in a noisy room.
- **Acceptance:** ≥ 8/10 TV utterances dropped, 0/10 of Larry's dropped,
  0/5 confirmations dropped, RTF < 0.8. Anything else → record numbers
  here and stop; threshold tuning or engine fallback is a follow-up
  decision, not an improvisation.

## 7. Deliberately not done

- No camera/face work (Tier 3) and no target-speaker extraction (Tier 4).
- No interruption gating by speaker (L7) — transcripts only.
- No enrollment via the live mic path (L3).
- No spoken response to dropped utterances (L6).
- No multi-user profiles — one profile, Larry. The JSON schema
  (`speaker_profile.json`) would extend naturally; do not pre-build it.
- No UI panel — one fire-and-forget app message and log lines only.

## 8. Self-audit (cross-section contradictions checked before handoff)

- §4.3 inserts the tap only when the encoder loads; §5's
  `test_no_profile_disables_gate_not_pipeline` pins the same condition —
  consistent.
- L5 says fail-open on error; §4.1's `Encoder.embed` returns None on
  exception and `verdict(None, ...)` = pass — consistent.
- L9's incremental first-verdict at 1.0 s equals `MIN_VERIFY_SECS`, so any
  utterance long enough to be judged has a verdict attempt started before
  end-of-speech — the 0.6 s hold is margin, not the primary wait.
- Tier 1b's revert clause cannot conflict with Tier 2: the gate never
  touches interruption frames.
- The gate reads env directly while NS reads Settings — inconsistent on
  purpose, each follows the pattern of the feature it sits beside
  (screen vision vs. Workstream A), both documented in `.env.example`.

## 9. Approval

- [x] Tier 1a: enable NS engines, eval, RTF-gated fallback (L1)
- [x] Tier 1b: min-words barge-in, verify-or-revert (§3)
- [x] Tier 2: ECAPA speaker gate, fail-open, transcripts-only, opt-in
      (L2–L9)
- [x] Effectiveness protocol before any Tier 3 discussion (§6)

## 10. Implementation status (2026-08-21)

Code complete, unit-tested, verified against the real pipecat 0.0.108 API
in this environment. What "verified" means here vs. what still needs
Larry's Mac:

- **§2 Tier 1a**: `requirements.txt`/`.env.example` updated exactly per
  §2. NOT installed/run here — this sandbox's `.venv` is a macOS venv
  (broken symlinks under Linux) and has no audio hardware. Larry needs to
  run: `uv pip install -r requirements.txt`, regenerate the lock, then the
  §2.4 verification commands (including the live RTF check against
  `logs/bot.log`).
  - **2026-08-21, installed on Larry's Mac — both engines initially
    failed; RESOLVED same day, rnnoise is now the ONE engine.** Full
    diagnosis (verified against PyPI metadata + downloaded wheels, not
    guessed):
    - `deepfilternet` is **unfixable on py3.12 and removed from
      requirements.txt**. Its Rust core `deepfilterlib` has never shipped
      cp312 wheels (cp38–cp311 only, every release), so the resolver
      silently backtracked to 0.2.4 (2022) whose sdist happened to build —
      and 0.2.4 imports `torchaudio.backend.common`, removed in
      torchaudio ≥2.1. Worse: the LATEST release (0.5.6, mid-2023, project
      unmaintained since) has the identical unconditional import in
      `df/io.py` — confirmed by downloading and reading the wheel — so
      even a successful cp312 build would fail the same way.
      `jarvis_ns_filter`'s Settings default changed to `"rnnoise"`; the
      `deepfilternet` factory branch and `DeepFilterNetFilter` class stay
      (degrade to pass-through) for a future upstream revival.
    - `pyrnnoise` failed because its `audiolab` dependency imports
      `av.option`, which PyAV **removed in av 17** (Larry's env had
      av 17.1.0). It exists in av 14/15/16 (confirmed by inspecting the
      wheels), and `aiortc` 1.15 — the WebRTC transport, the other
      consumer of `av` — declares `av>=14,<18`, so **`av>=16,<17` (pinned
      in requirements.txt) satisfies both** with prebuilt cp312
      macos-arm64 wheels, no compilation. Verified END-TO-END in a clean
      environment: `av==16.0.1` + `audiolab==0.5.1` + `pyrnnoise==0.4.3`
      installs, `from pyrnnoise import RNNoise` succeeds, and
      `RNNoise.denoise_chunk` (the exact API pipecat's `RNNoiseFilter`
      calls) processes audio correctly — against numpy 2.2.6, so no numpy
      pin is needed. The earlier `av<12` attempt was the wrong target
      (needless source build); the removal boundary is 17, not 12.
    - Remaining Larry steps: `uv pip uninstall deepfilternet
      deepfilterlib`, `uv pip install "av>=16,<17"`, regenerate the lock,
      set `JARVIS_NS_ENABLED=true` in `.env` (filter default is now
      rnnoise), boot, confirm voice still connects (av downgrade touches
      the WebRTC path — within aiortc's declared range, but verify), and
      check `[ns]` telemetry in `logs/bot.log`.
- **§3 Tier 1b**: REWIRED 2026-08-21 after the first boot on Larry's Mac
  died on `ModuleNotFoundError: pipecat.audio.interruptions`. Root cause
  of the original miss: **§0's "pipecat version is 0.0.108" was verified
  in the implementation sandbox, whose GLOBAL python carries pipecat
  0.0.108 — Larry's venv runs pipecat 1.4.0** (which the pipeline
  docstring and D-004 comments correctly state; the plan's own §0 was the
  error, and the sandbox's DeprecationWarning naming the replacement API
  was the ignored tell). In 1.4 the old
  `PipelineParams(interruption_strategies=...)` path is gone; turn
  strategies live on the USER AGGREGATOR. Now wired (verified against the
  1.4 sources in Larry's actual venv):
  `LLMContextAggregatorPair(context, user_params=LLMUserAggregatorParams(user_turn_strategies=UserTurnStrategies(start=[MinWordsUserTurnStartStrategy(min_words=2)])))`.
  Semantics are BETTER than the old API: 1.4's
  `MinWordsUserTurnStartStrategy` applies `min_words` only while the bot
  is speaking; when the bot is quiet a single word starts a turn normally
  — the interruption-only behavior the plan wanted, built in. Lesson for
  future plans: version-check against the DEPLOYMENT venv
  (`.venv/lib/python3.12/site-packages`), never the sandbox interpreter.
  Live "cough vs. sentence" verification (§3.2) still needs Larry's mic.
- **§4 Tier 2**: `jarvis/speaker.py` and `jarvis/bot/speaker_gate.py`
  built exactly to spec (constants, `verdict`/`cosine`/`Encoder`, CLI,
  `SpeakerTap`/`TranscriptGate`, wiring guard in `build_pipeline`).
  `speechbrain`/`soundfile` added to `requirements.txt` (not installed
  here, same venv limitation as above).
- **§5 Tests**: `tests/unit/test_speaker.py` (16 tests) and
  `tests/unit/test_speaker_gate.py` (12 tests) — all pure/injected, no
  torch, no network, no model files, matching the plan's constraint.
  `pytest tests/unit -q`: **1352 passed**. `pytest tests/integration -q`:
  **97 passed, 3 skipped** (two pre-existing gaps unrelated to this plan
  were found and fixed along the way — a stale `ALL_SERVERS` list missing
  `mcp-memory`, and a stale expected-payload dict missing `run_id` — plus
  one environment-only failure, a sandbox proxy blocking the live weather
  API call in `test_mcp_web_server`, not a code defect).
  `cd web && npm run build`: TypeScript compiles clean (`tsc -b`, zero
  errors); the bundling step itself fails in this sandbox only because
  the mounted filesystem won't allow deleting `web/dist/*` (the same class
  of permission limitation documented elsewhere in this repo for `.git/`)
  — no `web/` files were touched by this plan, so this is not a
  regression to chase.
- **§6 Effectiveness protocol**: first live session run 2026-08-21
  evening. Enrollment: self-scores 0.89–0.94; offline TV verify: -0.006
  (verdict=drop) — calibration excellent in both directions. Live: every
  TV transcript that reached the gate was dropped (scores 0.07–0.18),
  Larry's own speech passed — but the session surfaced three defects,
  all fixed the same evening:
  1. **L7 was insufficient live** — the TV never got a transcript through
     yet interrupted Mortimer's TTS constantly (four consecutive
     "interrupted before any audio played" context notes). Fix:
     `SpeakerVerifiedMinWordsTurnStartStrategy` (jarvis/bot/speaker_gate.py)
     — while the bot speaks, an interruption requires min_words AND a
     passing speaker score; fail-CLOSED for interruptions only (missing
     score = "not yet", rechecked on the next interim ~1s in; L5's
     fail-open still governs transcripts). Quiet-bot behavior unchanged.
  2. **Dropped speech was persisted** — TranscriptObserver logged the
     STT→gate hop, so TV dialogue landed in the conversations table
     (which the memory sweep folds into memory). Fix: observer gains
     `only_from`; with the gate active it persists only frames the gate
     itself pushed, so the record matches what the LLM received.
  3. **ECAPA crashed on near-empty buffers** ("padding (2,2)... input
     [1, 80, 1]") — turns with <0.4s of audio scheduled embeds that
     raised. Fix: `MIN_EMBED_SECS = 0.4` guard; such turns pass via
     MIN_VERIFY_SECS as designed, now without the traceback.
  Also found: a stale `JARVIS_NS_FILTER=deepfilternet` line in Larry's
  `.env` (pre-dating this plan) had NS silently in pass-through all
  session; corrected to rnnoise.

  **Second live session (19:17–19:29, RNNoise + interruption gating
  active) — enrollment domain mismatch found.** The interruption gating
  held (conversation flowed, 18 turns answered), but the drop log showed
  two clusters: clear TV at 0.01–0.17, and a second cluster at
  **0.30–0.40 timed beside Larry's own "Yes." confirmations** — the gate
  was dropping some of HIS turns. Cause: enrollment WAVs were QuickTime
  recordings, but live audio reaches the gate through WebRTC capture +
  browser processing + RNNoise — a different acoustic domain, dragging
  his live scores from 0.89–0.94 (offline) down to ~0.30–0.55. **L3's
  file-based enrollment was the wrong domain, not merely a convenience
  trade-off.** Fix: `JARVIS_SPEAKER_CAPTURE=true` makes `SpeakerTap`
  save each final turn buffer (≥1s, newest 20 kept) as a WAV under
  `data/speaker_captures/`, so enrollment can be re-run FROM THE PATH THE
  GATE SCORES (`python -m jarvis.speaker enroll data/speaker_captures/*.wav`),
  then capture is switched off. Capture is opt-in and records everything
  the mic hears — it exists for calibration sessions only.
  `data/models/`, `data/speaker_profile.*`, and `data/speaker_captures/`
  joined `.gitignore` at the same time — §0's "data/** is already
  gitignored" was WRONG (only specific patterns were), and a voiceprint
  must never be committable. Live-path re-enrollment + the full §6
  acceptance pass still pending.

Net: everything in §§2–5 that can be verified without a microphone,
speaker hardware, or this specific machine's real Python environment has
been verified. §6 is next, on Larry's machine.

**2026-08-22 — log review of the 2026-08-21 evening sessions ("conversation
is not natural anymore and in some cases forced"), three compounding
defects found, two fixed:**

- **Flux's own interruption bypassed the gate entirely (FIXED).**
  `DeepgramFluxSTTService(should_interrupt=True)` broadcasts an
  interruption on EVERY VAD-level StartOfTurn — before any transcript or
  speaker score exists — so `SpeakerVerifiedMinWordsTurnStartStrategy`
  (which gates the AGGREGATOR's turn start) never saw the interruptions
  it was built to stop: 26 broadcasts in the 21:52 session, 36 in the
  19:17 one, each killing any in-flight reply "before any audio played."
  This is why the TV still cut Mortimer off after the strategy landed —
  the strategy was gating the second interruption source while the first
  kept firing. Fix: `should_interrupt=False`; the (gated) strategy is now
  the ONLY interruption trigger. Cost accepted: barge-in fires at first
  transcript (~0.5s after speech onset) instead of at VAD onset.
  Pinned by `test_flux_never_interrupts_on_its_own`.
- **InterruptionNotifier context flood (FIXED).** The notifier armed on
  `UserStoppedSpeakingFrame` — which fires for utterances the gate then
  DROPS — so every TV line armed it with no reply in flight, and the next
  routine InterruptionFrame injected a false "[system] Your previous
  reply was interrupted" note. Measured in the 21:52 session's final LLM
  context: **90 notices vs 12 real user messages** — the model's view of
  the conversation was 88% interruption spam, which is what made replies
  read clipped and apologetic. Fix: arm on `LLMFullResponseStartFrame`,
  so "active" means "a reply actually exists to interrupt" by
  construction. Pinned by
  `test_dropped_turn_with_no_reply_in_flight_produces_no_note` and
  `test_repeated_dropped_turns_never_accumulate_notes`.
- **False drops of Larry's own speech (NOT yet fixed — needs L-path
  re-enrollment).** The profile on disk is still the 18:54 QuickTime
  enrollment; the live-capture re-enroll never ran (captures only began
  accumulating 21:53). Drop scores are bimodal — 0.01–0.26 (other
  voices, correct) and 12 drops at 0.30–0.40 (long, on-topic,
  almost certainly Larry: a 12s/180-char utterance at 0.39, one at
  0.399 displayed as 0.40) — the 0.40 threshold sits inside Larry's own
  live-score band. Next step unchanged: `python -m jarvis.speaker verify
  data/speaker_captures/*.wav` to see the two bands, enroll from the
  captures that are him, and reset `JARVIS_SPEAKER_THRESHOLD` at the
  measured valley rather than the current guess.

**2026-08-22 (later) — live-path re-enrollment DONE on Larry's machine.**
The 14:05 session confirmed C+D working (clean turns, replies completing,
zero interruption spam) and produced 4 more false drops, all 0.30–0.37 —
including the telling sequence where two natural-length answers were
eaten and the clipped "No." passed only because <1s utterances skip
scoring (MIN_VERIFY_SECS fail-open): the gate was training Larry to bark
short phrases. Larry then enrolled from the three 14:0x live captures
(`python -m jarvis.speaker enroll data/speaker_captures/turn-140*.wav`):
new profile self-scores 0.86–0.88 in-sample, and a live-capture verify
scored 0.59 vs the old profile's 0.30–0.37 band — comfortably above the
0.40 threshold. Threshold left at 0.40. Remaining validation: one normal
session with the TV ON — the TV's 0.01–0.26 band was measured against
the OLD profile and is expected but not yet proven to stay low against
the new one; any of Larry's own turns appearing in
`speaker_gate_dropped` after this re-enrollment reopens the threshold
question. `JARVIS_SPEAKER_CAPTURE` should now be set back to false
(calibration over; the flag records everything the mic hears).
