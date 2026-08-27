# Mortimer — Local voice services and Mac mini hosting (track T3)

**Status:** DRAFT for Larry's approval, 2026-08-26. Implements roadmap track T3
(`docs/plans/MORTIMER_PLATFORM_ROADMAP.md` §2.3, items T3.1–T3.5), gated by G3 (§4).

**Author / origin (Larry's words, quoted from the roadmap so intent survives):**

- *"can we move the voice piece to the mac mini?"* (roadmap §Origin)
- *"we will not implement the financial piece until the issues are resolved like
  moving to the mini so that we can process the models locally."* (roadmap
  §Origin, marked **Sequencing rule, verbatim**) — this is why T3 exists at all
  and why C3 makes G3 the precondition for T4b.
- Standing: *"the Mac mini is the near-term dev/cost host; cloud is the terminal
  host."*

---

## Revision — review findings closed (2026-08-27)

This revision closes the adversarial review
(`review-opus/MORTIMER_LOCAL_VOICE_AND_MINI_PLAN.review.md`) and applies the
cross-plan edits `CROSS_PLAN_RESOLUTION.md` assigns to LOCAL. Every runnable fix
was re-extracted into the sandbox and run against the review's own breaking
inputs; the commands and outputs are in §7 ("measured:" notes). One row per
finding closed.

| Finding | Sev | Section(s) changed | What changed |
|---|---|---|---|
| F1 | BLOCKER | §4, §5 Step 2/9.1, §7 | `WhisperSTTServiceMLX` hard-imports `faster_whisper` at module scope on **every** platform (`mlx_whisper` only on Darwin/arm64). Added `whisper` extra (`faster-whisper~=1.2.1`) so the module imports on Linux CI; corrected the two platform-gated pins to pipecat's actual constraints (`mlx-whisper~=0.4.2`, `kokoro-onnx>=0.5.0,<1` + `requests`); mini install installs all three; test #4 guarded with `importorskip`. |
| F2 | BLOCKER | Correction 5, §1.2/1.3, new L15, §5 Step 4/7 | jarvis's `start=[…]` replaces pipecat's default VAD start strategy, and `MinWordsUserTurnStartStrategy` only starts a turn on a transcript. Whisper emits no interim, so verified barge-in moves from ~0.5 s into speech to VAD-stop+inference. Made this an explicit **Larry decision** (L15) with two fully-wired configs, default = safe. |
| F3 | BLOCKER | Correction 1, §1.3, L8, L15 | Under Whisper with a transcript-driven turn-start, the late transcript triggers `_trigger_user_turn_start`, which **resets the stop strategies** (`user_turn_controller.py`), discarding the smart-turn verdict; end-of-turn falls to the "no VAD stop received" fallback. The analyzer only decides again if the turn starts at VAD onset (L15 Config W-onset). Recorded as deviation D-013. |
| F4 | BLOCKER | §5 Step 7, §6, §8 B | `TURN user_end->first_audio`'s clock starts at the aggregator's `UserStoppedSpeakingFrame`, which under Whisper waits for the transcript — the STT penalty lands before the clock and is invisible, and `stop_secs` is also before it. Added a `vad_stop->first_audio` instrument keyed on `VADUserStoppedSpeakingFrame` (both providers emit it from the VAD) and made **that** the G3(b) measurement. |
| F5 | BLOCKER | L10, L11, §5 Step 9, §8 E4, R-L2 | A `gui/<uid>` LaunchAgent loads at **login**, not boot, so it cannot satisfy G3(d) headless; and if a login session exists the Keychain works, collapsing L11. Switched to **LaunchDaemons** with `UserName`, which start at boot; the 0600 key file is then unavoidable and justified; R-L2 states the at-rest exposure without softening. |
| F6 | BLOCKER | L6, L7, §5 Step 9.4, §6 | Ollama's default context is 4096 tokens and it silently truncates; the Supervisor system prompt alone is ~3.4 k. Added `OLLAMA_CONTEXT_LENGTH=16384` to the plist and §6, and made L7 STEP A measure `ollama ps` after a real system-prompt request, not a `max_tokens:8` ping. |
| F7 | BLOCKER | §5 Step 6b, §7 | `scripts/check_env.py` is stdlib-only by contract; importing `jarvis.config` (pydantic) breaks the one validator that must survive a broken env. Inlined the provider rule stdlib-only; added `test_check_env_required_vars_match_config` to guard the duplicate. |
| F8 | MAJOR | Corrections (del. C3), §5 Step 6b, §10 R-L9 | Correction 3 was false: `check_env.py`'s `load_env()` is `dict(os.environ)` overlaid with `.env`, so it already reads the environment first. Deleted Correction 3, the second Step-6b bullet, and R-L9. |
| F9 | MAJOR | L12, §5 Step 6, §0.11 | The plan re-introduced the `.env`-vs-`os.environ` split for `JARVIS_STT_PROVIDER` in three new sites. Added one shared `cfg()` resolver (os.environ then repo `.env`) used by both scripts, stated once in L12. |
| F10 | MAJOR | §1.3, §4, §5 Step 4, §7 | `SpeakerTap` keys its scoring window on `UserStartedSpeakingFrame`, which under Whisper arrives during silence — the mid-turn score embeds silence and the final score an empty buffer. Re-keyed it on the VAD frames (reliable under both providers); added `speaker_gate.py` to Modify + two tests. |
| F11 | MAJOR | L7, L9, §5 Step 8 | L7 stops at the first passer, so "next smaller candidate that passed both gates" is always empty — both L9's REJECT and Step 8 S6 degenerated to STOP. Reordered the ladder strictly ascending; replaced the dead branches with the real one (record `REQUIRED_GB`, take STOP). |
| F12 | MAJOR | L9, §5 Step 8, §8 C | RAM formula double-counted headroom (8 GB additive **and** ×0.85), and `STT_GB` needed an `rss_at_startup` no step captured. Count headroom once; capture R0/R1 explicitly; `STT_GB = max(2.5, delta)` with the unified-memory reason. Worked example re-derived. |
| F13 | MAJOR | §5 Step 7a, §7 | The two new "Whisper timing" tests exercised frames `InterruptionNotifier` ignores (one duplicated an existing test). Replaced with a real `UserTurnController` ordering test that fails today and documents F3. |
| F14 | MINOR | L12, §5 Step 6a, §7 | `check_local_only` rule 4 "or absent" passed a config the bot can't boot; rule 5's failure message was `—`. Dropped "or absent"; wrote both messages out. |
| F15 / CP-F8 | MINOR/MAJOR | §8 A1 | `/65` → `/N` computed at runtime (fixture is 68 now, 86 after MAIL); record whether `secretary` is present when the ladder runs. |
| F16 | MINOR | §1.7 | "9 tests" → "8 tests". |
| F17 | MINOR | §4 | `REQUIRED_ENV_VARS` has no consumer outside `config.py`; comment corrected. |
| F18 | MINOR | §5 Step 5b | Line 1067 is inside `run_session` (binds `settings` and `runtime`), not `build_pipeline`; reason corrected. |
| F19 | MINOR | §5 Step 2, §6 | Deleted the bare `assert` production guard in `build_stt`; the constant check lives only in test #4. |
| F20 | MINOR | §5 Step 2, §6, L8 | `WhisperSTTServiceMLX` never sets `ttfs_p99_latency`; pass `WHISPER_TTFS_P99=1.0`, note it in the floor rationale. |
| F21 | MINOR | §5 Step 7 P0 | `mortimer.sh` is overridden by `.env`; added a P0 log-line verification so the baseline can't be silently measured on Whisper. |
| F22 | MINOR | §4, §5 Step 9.4, §8, R-L8 | launchd log growth had no rotation; specified `newsyslog.d/mortimer.conf` and a soak check. |
| CP-F9 | MAJOR | §0.11, §4, §5 | Anchor every `pipeline.py` edit site by quoted code text; line numbers in this plan are indicative only. |
| CP-F10 | MINOR | §4 | Added LOCAL's env vars to `.env.example`. |
| Resolution A | — | §4, §8 | LOCAL's W2 allow-list change (`deny += docs/runbooks/**`) is now "apply the LOCAL row of `docs/plans/ALLOWLIST_SEQUENCE.md`"; the JSON itself is SEC-owned. |

**Roadmap change this plan needs (for the SEC task to fold in):** none beyond what
`CROSS_PLAN_RESOLUTION.md` already assigns. L15 records a barge-in trade under
Whisper that touches roadmap R6 (*"local STT does not ship without turn detection
at parity"*); the plan resolves it with a default-safe config and a measured
opt-in rather than a roadmap edit, but if Larry rules that R6 forbids shipping
Whisper at all until barge-in parity exists, that is a roadmap decision recorded
in §8 A/B, not a silent regression here.

---

**Roadmap constraints this plan is bound by:**

| C | How this plan honours it |
|---|---|
| **C1** — backend contract does not change for the client migration | No RTVI app-message shape, no sidecar route, and no MCP tool signature changes. The provider seam is `jarvis/bot/providers.py` + three env vars; nothing in the pipeline learns "the mini". §3 L2, §4. |
| **C2** — localhost is the trust boundary until T2 lands | This plan never binds a port itself. Every bind goes through `resolve_bind_host` from `MORTIMER_REMOTE_ACCESS_PLAN.md` §3 A8 / §5 Step 3, which is fail-closed. The relocation runbook (§5 Step 9) refuses to proceed until G2 has passed. |
| **C3** — T4b does not start until G3 passes | This plan *is* G3's evidence. §8 records every gate item as a command with a pass/fail line. |
| **C4** — every mutation stays draft → confirm | This plan adds no mutating tool and no MCP server. The only new CLI verbs are read-only probes (`scripts/check_local_only.py`, `scripts/tts_ab.py`). |
| **C5** — sub-agents act on data, never on windows | Untouched. No agent gains a capability here. |
| **C6** — untrusted content never shares an agent with an outbound channel | Untouched; `config/agents.yaml` is not edited by this plan. |
| **C7** — routing eval stays ≥ 90 % | T3.3 **changes the Supervisor model**, so C7 binds hard. §3 L7 is a decision tree whose only accept branch is a recorded 3-run mean ≥ 90 % from `RUN_LIVE=1 python -m tests.evals.routing_eval`. §8 A1 records the number. |
| **C8** — self-edit allow/deny changes are human commits | §4 lists two deny-list entries; §5 Step 12 says **Larry commits them**, the implementer does not. |
| **C9** — secrets in the vault, never `.env`, never `config/`, **never a plist** | §3 L11 is written specifically because launchd plists tempt exactly that. No plist in §5 Step 9 contains a secret; the vault key reaches launchd through a 0600 file the wrapper sources, and every other secret still comes from `jarvis/vault.py`. |
| **C10** — degradation-proof | Every provider switch is literal code (§5 Steps 2–5); the interruption re-tune is a numbered procedure with a bound (§5 Step 7); model selection is a decision tree with an explicit stop branch (§3 L7); the RAM sizing is arithmetic with a rejection rule (§3 L9). |

**Contracts this plan INTRODUCES (consumed by later plans):**

- **K7 — local voice service switches.** Fully specified in §3 L1 (the three env
  vars, their exact enums, defaults, validators and single read site), §5 Step 1
  (`Settings` fields), and §5 Step 2 (`jarvis/bot/providers.py`, the one factory
  module that reads them). Consumed later by `MORTIMER_SENSITIVE_TIER_PLAN.md`
  (T4b's voice-in-for-sensitive-questions rule needs to ask "is STT local?" — it
  asks `settings.jarvis_stt_provider == "whisper_mlx"`, nothing else).
  **K7 clarification, not deviation:** K7's `JARVIS_TURN_DETECTOR` value `stt` is
  a historical name. It does **not** mean the STT decides the turn; see
  Correction 1. The three literal values, the default, and the variable names are
  exactly as K7 fixes them.
- **The relocation runbook** (§5 Step 9) is the reference other plans point at
  for "how Mortimer runs on a host it is not logged into".

**Contracts this plan CONSUMES (by doc + section — cited, never restated):**

- **K1 — client bearer tokens**: `MORTIMER_REMOTE_ACCESS_PLAN.md` §3 A1–A9, §5
  Steps 1–3. This plan mints exactly one token during relocation
  (`python -m jarvis.auth add service-bot`, per K1's bootstrap paragraph) and
  otherwise touches nothing about auth.
- **K5 — host/URL configuration**: `MORTIMER_REMOTE_ACCESS_PLAN.md` §3 A11
  (`jarvis/urls.py`, `JARVIS_ADMIN_URL`, `JARVIS_BOT_URL`). The wake-word client
  and the native client reach the mini through `JARVIS_BOT_URL`; this plan names
  no host except in the plists' comments and in `scripts/check_local_only.py`'s
  loopback test.
- **Fail-closed bind**: `MORTIMER_REMOTE_ACCESS_PLAN.md` §3 A8 / §5 Step 3
  (`jarvis/bind.py:resolve_bind_host`, exit code 2). The launchd plists in §5
  Step 9 invoke the same `python -m jarvis.bot.bot` / `python -m
  jarvis.admin.server` entry points, so they inherit that resolver. **Do not
  write a bind or host resolver in this plan.**
- **K2 — per-server env scoping**: `MORTIMER_SECURITY_HARDENING_PLAN.md` §3
  D-H1/D-H2, §5 Steps 1–2. This plan adds **no** MCP server, so it declares no
  `requires_env`. It does note (§5 Step 9.6) that `BASE_ENV_KEYS` from K2 is what
  a relocated MCP child sees, which is why the launchd wrapper must export
  `PATH`, `HOME` and `TMPDIR` explicitly.

---

## Corrections to the roadmap

Four. All verified against source; every one changes what the implementer must do.
(A fifth draft correction, about `scripts/check_env.py` reading the `.env` file
rather than the environment, was **withdrawn** after review finding F8 proved it
factually false — `load_env()` is `dict(os.environ)` overlaid with `.env`, so the
environment already wins. See §5 Step 6b and the deletion of R-L9.)

### Correction 1 — `LocalSmartTurnAnalyzerV3` is **already running today**. T3.2 is not "add smart-turn"; it is "make the analyzer explicit and tunable, and replace the *transcriber*."

Roadmap §2.3 T3.2 says local STT comes *"**plus** `LocalSmartTurnAnalyzerV3` (or
the CoreML variant) replacing the end-of-turn detection Flux performed inside the
STT."* Both halves of that sentence are wrong.

- `jarvis/bot/pipeline.py:631-638` constructs
  `LLMContextAggregatorPair(context, user_params=LLMUserAggregatorParams(
  user_turn_strategies=UserTurnStrategies(start=[turn_start_strategy])))` —
  it passes **only** `start=`.
- `UserTurnStrategies.__post_init__`
  (`pipecat/turns/user_turn_strategies.py:74-79`) fills an unset `stop` with
  `default_user_turn_stop_strategies()`, which is
  `[TurnAnalyzerUserTurnStopStrategy(turn_analyzer=LocalSmartTurnAnalyzerV3())]`
  (`pipecat/turns/user_turn_strategies.py:42-51`).
- So the bundled ONNX model
  `pipecat/audio/turn/smart_turn/data/smart-turn-v3.2-cpu.onnx` is loaded and
  deciding turn-close on every session today. `onnxruntime==1.24.4` and
  `soxr==1.0.0` are already pinned (`requirements-lock.txt:103,169`) — the two
  dependencies `local_smart_turn_v3.py` imports at module scope.
- `DEVIATIONS.md:84` states this in plain words already: *"pipecat 1.4.0's local
  `LocalSmartTurnAnalyzerV3`, **the actual turn-close decision-maker**, which is
  triggered by `VADUserStoppedSpeakingFrame`"*, and *"Flux's server-side EOT …
  **only finalizes transcripts mid-turn (harmless)**"*. `jarvis/bot/pipeline.py:672-677`
  repeats it in the pipeline comment.

**What this changes for the implementer.** T3.2's turn-detector work is not a new
capability; it is (a) making the implicit default explicit so it can be tuned and
logged, and (b) surviving the loss of Flux's *transcription* and its two
`UserStartedSpeakingFrame`/`UserStoppedSpeakingFrame` broadcasts. Both are
specified in §5 Steps 3 and 4.

**But the analyzer's role does not survive the STT swap unchanged — corrected
after review (F3).** The smart-turn analyzer decides end-of-turn only while the
turn was started **at VAD onset**. In jarvis's pipeline the turn is started by a
*transcript-driven* strategy (`SpeakerVerifiedMinWordsTurnStartStrategy`,
`jarvis/bot/speaker_gate.py` — anchor `class SpeakerVerifiedMinWordsTurnStartStrategy`),
so with Flux the interim transcript starts the turn mid-speech and the analyzer's
verdict computed at `VADUserStoppedSpeakingFrame` survives to gate end-of-turn.
With `WhisperSTTServiceMLX` the only transcript arrives **after** VAD stop; that
late transcript fires turn-start, and `UserTurnController._trigger_user_turn_start`
(installed Pipecat, anchor `# Reset all user turn stop strategies to start fresh`)
**resets every stop strategy**, wiping `_turn_complete`/`_vad_stopped_time` before
the same frame reaches the stop strategy — which then takes the
`# Fallback: handle transcripts when no VAD stop was received` branch of
`TurnAnalyzerUserTurnStopStrategy._handle_transcription` and ends the turn on
"a finalized transcript exists". **So under the default Whisper config the
analyzer runs and is ignored; end-of-turn = Whisper's VAD-stop segmentation
boundary.** The analyzer decides again only if the turn is started at VAD onset
(L15 Config W-onset). This is deviation D-013, and it is why the G3(b) procedure
(§5 Step 7) and its floor (L8) are written against the STT swap **and** against
the analyzer bypass, not against a turn-detector "turn-on".

### Correction 2 — `OPENAI_BASE_URL` **is** honoured by the pipeline, but "pointing at a local server is config" is still false, because the bot refuses to start without cloud keys.

Roadmap §2.3 T3.3 says *"(base URL + key from the vault; **no code change to the
service wiring**)"*. The first half is true; the second is false.

Verified true:
- `jarvis/bot/pipeline.py:521-525` — `OpenAILLMService(api_key=settings.openai_api_key,
  base_url=settings.openai_base_url, model=settings.openai_model)`. The base URL
  reaches the Supervisor service.
- Every other LLM caller does the same: `jarvis/agents/base.py:245,249`,
  `jarvis/agents/supervisor.py:68`, `jarvis/procedures.py:358`,
  `jarvis/memory.py:854`.
- The Google branch at `jarvis/bot/pipeline.py:512` only triggers on
  `"generativelanguage.googleapis.com" in settings.openai_base_url`, so a
  loopback base URL falls to `OpenAILLMService`. No change needed there.
- Pipecat's own `OLLamaLLMService` is nothing but
  `OpenAILLMService(base_url=..., api_key="ollama")`
  (`pipecat/services/ollama/llm.py:24,76`) — confirming K7's instruction to
  reuse the existing settings rather than add a parallel knob. **Do not import
  `OLLamaLLMService`.**

Verified false — the blocking part:
- `jarvis/config.py:28` — `REQUIRED_ENV_VARS = ("OPENAI_API_KEY",
  "DEEPGRAM_API_KEY", "ELEVENLABS_API_KEY")`, and `jarvis/config.py:52,57,58`
  declare `openai_api_key: str`, `deepgram_api_key: str`,
  `elevenlabs_api_key: str` with **no defaults**. `load_settings()`
  (`jarvis/config.py:210-219`) turns a missing one into `RuntimeError`.
- Therefore **G3(e) — "no cloud STT/LLM key present in the mini's vault" — is
  literally unsatisfiable today**: delete `DEEPGRAM_API_KEY` and the bot will not
  boot, whatever `JARVIS_STT_PROVIDER` says. §5 Step 1 makes the requirement
  conditional on the provider switches; that is a real code change, and it is the
  gate item's precondition.

### Correction 3 — WITHDRAWN (review F8)

The draft claimed `scripts/check_env.py` reads `OPENAI_BASE_URL` from the `.env`
file rather than the process environment. That is false. `load_env()`
(`scripts/check_env.py`, anchor `def load_env`) returns `dict(os.environ)` overlaid
with `.env` via `setdefault`, so **the environment already wins**; `:243` and
`:495` read it through that merged view. The real environment split the plan must
avoid is a *different* one — reading `os.environ` directly for `JARVIS_STT_PROVIDER`
so a `.env`-only value is missed — and that is closed by the shared `cfg()`
resolver in L12 / §5 Step 6 (review F9), not by touching the base-URL read. The
genuinely-correct base-URL behaviour is left exactly as it is.

### Correction 4 — G3(e) as written would also delete the **sub-agents'** cloud keys, which T3 never promised to replace.

Roadmap §4 G3(e): *"No cloud STT/LLM key present in the mini's vault (proves
nothing falls back silently)."* But roadmap §2.3 T3.3's scope is the **Supervisor**
LLM only; the five sub-agents resolve models from `config/upgrade_models.yaml`,
whose profiles name `MOONSHOT_API_KEY`, `ANTHROPIC_API_KEY` and
`OPENROUTER_API_KEY` (`config/upgrade_models.yaml:66,76,86,103,140,150,160,170,180,190,206,216,226`).
Removing those breaks every delegation, which no T3 item asks for.

§3 L12 resolves this by splitting the check into two modes with fixed rules:
default mode governs the **voice loop's own** credentials (that is what G3(e) is
for — proving no silent fallback in the path Larry hears), and `--strict` also
fails on sub-agent cloud keys and is what `MORTIMER_SENSITIVE_TIER_PLAN.md` will
need. G3(e) passes on the default mode; the strict-mode residual is printed, not
hidden.

### Correction 5 — the roadmap's §1 table calls `WhisperSTTServiceMLX` a drop-in for `DeepgramFluxSTTService`. It is a **different base class** with a different frame contract.

- `DeepgramFluxSTTService` is a streaming websocket service that
  **broadcasts** `UserStartedSpeakingFrame` on Deepgram's `StartOfTurn`
  (`pipecat/services/deepgram/flux/base.py:592`) and `UserStoppedSpeakingFrame`
  on `EndOfTurn` (`…/base.py:693`), pushes a final `TranscriptionFrame` on
  `EndOfTurn` (`…/base.py:676-691`), and pushes `InterimTranscriptionFrame` on
  `EagerEndOfTurn` (`…/base.py:730`) and `Update` (`…/base.py:742-753`).
- `WhisperSTTServiceMLX` extends `WhisperSTTService` → `SegmentedSTTService`
  (`pipecat/services/whisper/stt.py:386`, `pipecat/services/stt_service.py:717`).
  It **consumes** `VADUserStartedSpeakingFrame`/`VADUserStoppedSpeakingFrame`
  (`pipecat/services/stt_service.py:770-772`) to segment audio and emits exactly
  one `TranscriptionFrame` per segment, marked `finalized=True`
  (`pipecat/services/stt_service.py:752-764`). It emits **no**
  `UserStartedSpeakingFrame`, **no** `UserStoppedSpeakingFrame`, and **no**
  `InterimTranscriptionFrame`.

§1.3 enumerates every jarvis consumer of those frames and proves which ones
survive. The user aggregator broadcasts `UserStartedSpeakingFrame` /
`UserStoppedSpeakingFrame` itself on turn start/stop
(`pipecat/processors/aggregators/llm_response_universal.py:1180-1182` and
`1233-1236`, both gated on `params.enable_user_speaking_frames`, which defaults to
`True` at `pipecat/turns/user_start/base_user_turn_start_strategy.py:56` and
`pipecat/turns/user_stop/base_user_turn_stop_strategy.py:60`). The frames do not
disappear.

**But which frame exists is not the same as when it exists (review F2/F10), and
the draft's "the swap is safe" conclusion was wrong on timing.** Two jarvis
consumers are *load-bearing on timing*, and both were mis-stated:

- **The turn-start strategy itself.** jarvis passes `start=[turn_start_strategy]`
  to `UserTurnStrategies`, which **replaces** pipecat's default
  `[VADUserTurnStartStrategy(), TranscriptionUserTurnStartStrategy()]`
  (installed Pipecat, `default_user_turn_start_strategies()` in
  `pipecat/turns/user_turn_strategies.py`). The strategy jarvis installs
  (`MinWordsUserTurnStartStrategy` / its speaker-verified subclass) starts a turn
  **only** on a `TranscriptionFrame` or `InterimTranscriptionFrame` (installed
  Pipecat, `min_words_user_turn_start_strategy.py`, anchor
  `elif isinstance(frame, InterimTranscriptionFrame) and self._use_interim`).
  With Flux the interim transcript starts the turn ~0.5 s into speech; with
  Whisper (no interim, transcript only after VAD stop) the turn — and with it the
  aggregator's `UserStartedSpeakingFrame` broadcast **and** its
  `broadcast_interruption()` — cannot fire until after VAD stop + inference. So
  **verified barge-in moves from ~0.5 s into speech to VAD-stop+inference.** This
  is the exact property the repo bought deliberately with `should_interrupt=False`
  (`jarvis/bot/pipeline.py`, anchor `should_interrupt=False`), stated in that
  comment as *"an unverified interruption a TV can fire is worse than a verified
  one that arrives half a second later."* Recovering onset barge-in requires
  re-adding a VAD start strategy, which re-opens exactly that unverified-interrupt
  path — a genuine trade, made an explicit Larry decision in **L15**.

- **`SpeakerTap`'s scoring window (F10).** It resets its audio buffer on
  `UserStartedSpeakingFrame`; under Whisper that frame arrives during silence
  (the aggregator broadcasts it late), so the mid-turn embedding is computed over
  silence and the final over an empty buffer. Fixed by re-keying `SpeakerTap` on
  the VAD frames (§5 Step 4, F10).

The remaining consumers survive; §1.3 gives each a verdict. The timing changes and
the L15 trade are the whole content of §5 Step 7's re-tune.

---

## §0 Binding constraints for the implementing model

1. **You may not make a design decision.** Every choice in this plan is already
   made. If you reach a point where two implementations look equally good, you
   have misread a step — re-read it. If a step genuinely cannot be executed as
   written, **stop, and report which step and why**. Do not improvise.
2. **Never guess a Pipecat API.** Pipecat 1.4.0 is installed at
   `/usr/local/lib/python3.11/dist-packages/pipecat/`. Every Pipecat symbol this
   plan uses is cited with a `path:line`. If a cited line does not say what this
   plan says it says, stop and report.
3. **The three K7 env vars are read in exactly one place: `jarvis/bot/providers.py`.**
   `jarvis/config.py`'s `Settings` fields exist for discoverability and validation
   (the pattern `jarvis_ui_control_enabled` and `jarvis_council_enabled` already
   follow — see `jarvis/config.py:128-150`). If you find yourself writing
   `os.environ.get("JARVIS_STT_PROVIDER")` outside `jarvis/config.py`'s field
   declaration, you are wrong.
4. **Do not write a bind-host resolver, a token verifier, or a URL default.**
   Those are `jarvis/bind.py`, `jarvis/auth.py`, `jarvis/urls.py` from
   `MORTIMER_REMOTE_ACCESS_PLAN.md`. Import them; do not reimplement them.
5. **Do not run `git` in the sandbox** (it leaves `index.lock`). Where this plan
   says "Larry commits", stop and print the branch name.
   Branch: `t3-local-voice-and-mini`.
6. **Secrets never enter a plist, a shell script committed to the repo, a
   `config/*.yaml`, or `.env`** (C9). The only secret-adjacent file this plan
   creates is `/usr/local/etc/mortimer/vaultkey`, created by Larry on the mini,
   never by you, never in the repo.
7. **The sandbox has no Keychain, no microphone, no Apple Silicon, no network to
   ElevenLabs/Deepgram, and no Mac mini.** Everything you can verify, verify with
   `pytest tests/unit -q`. Everything you cannot goes in §8 for Larry, and you
   say so rather than claiming a pass.
8. **`mlx-whisper` will not install in the sandbox** (it is Apple-Silicon only).
   Every import of it is lazy and inside the `whisper_mlx` branch, so
   `pytest tests/unit -q` must pass on Linux with `JARVIS_STT_PROVIDER=deepgram`.
   Tests that need the real model live in `tests/integration/` behind `RUN_LIVE`.
9. **Do not change the 9-processor pipeline order.** `jarvis/bot/pipeline.py:670-693`
   is a locked list. The STT swap replaces the object at the `stt` slot; it does
   not move, add, or remove a slot.
10. **Every number in this plan lives in exactly one place**, listed in §6. If you
    need a threshold that is not in §6, stop and report — do not invent one.
11. **Anchor every edit by quoted code text, never by line number (cross-plan F9).**
    `jarvis/bot/pipeline.py` is edited by sibling plans in the same and prior waves
    (SEC W0, MAIL same wave), so every `pipeline.py:NNN` in this plan is
    **indicative only**. Each §4 Modify row and each §5 edit step names a quoted
    anchor string; locate the site by that string. **If the anchor text is not
    found, stop and report** — do not edit by line number. The same rule applies to
    `jarvis/config.py`, `jarvis/bot/speaker_gate.py`, and `config/agents.yaml`.

---

## §1 What exists today (verified, `path:line`) and the gap

### 1.1 The voice pipeline, as constructed

`jarvis/bot/pipeline.py:670-693` assembles, in this order:

| # | Processor | Constructed at | Notes |
|---|---|---|---|
| 1 | `transport.input()` | `:671` | `SmallWebRTCTransport`, built in `jarvis/bot/bot.py:34-41` |
| 2 | `VADProcessor(vad_analyzer=SileroVADAnalyzer(params=VADParams(stop_secs=2.5)))` | `:678` | `stop_secs=2.5` is D-010's adaptation (`DEVIATIONS.md:81-86`) |
| 3 | `speaker_tap` (optional) | `:680-681`, built `:608` | `SpeakerTap`, only when a profile is enrolled and the encoder loads (`:599-610`) |
| 4 | `stt` | `:682`, built `:480-500` | `DeepgramFluxSTTService(model="flux-general-en", should_interrupt=False)` |
| 5 | `speaker_transcript_gate` (optional) | `:683-684`, built `:655-660` | `TranscriptGate` |
| 6 | `aggregators.user()` | `:686`, built `:631-638` | `LLMContextAggregatorPair` — **also where the turn strategies live** |
| 7 | `llm` | `:687`, built `:512-525` | `OpenAILLMService(base_url=settings.openai_base_url)` (or `GoogleLLMService` on a Google base URL) |
| 8 | `transcript` | `:688` | `TranscriptLogger` |
| 9 | `tts` | `:689`, built `:543-551` | `ElevenLabsTTSService(model="eleven_flash_v2_5")` |
| 10 | `transport.output()` | `:690` | |
| 11 | `aggregators.assistant()` | `:691` | |

`jarvis/bot/bot.py:6-11` records D-004: `TransportParams` in 1.4.0 has no
`vad_analyzer` and no `allow_interruptions`. **This is still true and it is why
§5 Step 4 attaches the turn analyzer at the aggregator, not the transport.**

### 1.2 Turn strategies today — the attachment point, exactly

```python
# jarvis/bot/pipeline.py:625-638, verbatim
    if speaker_gate_state is not None:
        turn_start_strategy = SpeakerVerifiedMinWordsTurnStartStrategy(
            speaker_gate_state, min_words=2
        )
    else:
        turn_start_strategy = MinWordsUserTurnStartStrategy(min_words=2)
    aggregators = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            user_turn_strategies=UserTurnStrategies(
                start=[turn_start_strategy],
            ),
        ),
    )
```

`stop=` is not passed → `UserTurnStrategies.__post_init__`
(`pipecat/turns/user_turn_strategies.py:74-79`) supplies
`[TurnAnalyzerUserTurnStopStrategy(turn_analyzer=LocalSmartTurnAnalyzerV3())]`.
**That is the attachment point** (`pipecat/turns/user_stop/turn_analyzer_user_turn_stop_strategy.py:32,48-56`).
`LocalSmartTurnAnalyzerV3.__init__` takes
`smart_turn_model_path: str | None = None, cpu_count: int = 1, **kwargs` and
forwards `params: SmartTurnParams | None` to `BaseSmartTurn`
(`pipecat/audio/turn/smart_turn/local_smart_turn_v3.py:36-42`,
`…/base_smart_turn.py:60-70`). `SmartTurnParams` has three fields:
`stop_secs: float = 3`, `pre_speech_ms: float = 500`,
`max_duration_secs: float = 8` (`…/base_smart_turn.py:28-44`).

`LocalCoreMLSmartTurnAnalyzer.__init__` requires
`smart_turn_model_path: str` (no default; raises if empty) and expects
`<path>/coreml/smart_turn_classifier.mlpackage` plus a HF feature-extractor
config at `<path>` (`…/local_coreml_smart_turn.py:48-69`).

### 1.3 The frames Flux emits, and every jarvis consumer of them

Enumerated from `pipecat/services/deepgram/flux/base.py` (`stt.py` only defines
`run_stt`, which yields `None`/`ErrorFrame` — `…/flux/stt.py:381-410`; all real
frames are pushed from the websocket event handlers in `base.py`):

| Flux event | Frame emitted | Where |
|---|---|---|
| `StartOfTurn` | `UserStartedSpeakingFrame` (broadcast) | `base.py:592` |
| `StartOfTurn` + `should_interrupt` | interruption broadcast — **disabled**, `should_interrupt=False` at `jarvis/bot/pipeline.py:499` | `base.py:593` |
| `EndOfTurn` | `TranscriptionFrame` (final) | `base.py:676-691` |
| `EndOfTurn` | `UserStoppedSpeakingFrame` (broadcast) | `base.py:693` |
| `EagerEndOfTurn` | `InterimTranscriptionFrame` | `base.py:730` |
| `Update` | `InterimTranscriptionFrame` | `base.py:742-753` |
| any error | `ErrorFrame` | `stt.py:407` |

Every jarvis consumer, and its verdict after the swap (corrected after review —
the draft omitted the start strategy and mis-graded the last two rows):

| Consumer | Frame(s) read | Anchor | Survives Whisper? |
|---|---|---|---|
| **user-turn start strategy** (`SpeakerVerifiedMinWordsTurnStartStrategy`) | `TranscriptionFrame` / `InterimTranscriptionFrame` — the **only** thing that starts a user turn (jarvis's `start=[…]` replaces pipecat's VAD default) | `jarvis/bot/speaker_gate.py` `class SpeakerVerifiedMinWordsTurnStartStrategy`; installed Pipecat `min_words_user_turn_start_strategy.py` | **Degraded.** No interim under Whisper → turn-start (and the interruption broadcast it drives) moves to VAD-stop+inference. This is F2. **The whole subject of L15.** |
| `SpeakerTap.process_frame` | `UserStartedSpeakingFrame` (turn id ++, buffer reset), `InputAudioRawFrame`, `UserStoppedSpeakingFrame` (final score) | `jarvis/bot/speaker_gate.py` (`if isinstance(frame, UserStartedSpeakingFrame):`) | **No, until fixed (F10).** The aggregator broadcasts the speaking frames *late* (turn-start is transcript-driven), so the buffer resets during silence and scores silence. Fixed by re-keying on the VAD frames — §5 Step 4. |
| `TranscriptGate.process_frame` | `InterimTranscriptionFrame` (passed through), `TranscriptionFrame` (held/scored/dropped) | `jarvis/bot/speaker_gate.py` (`if isinstance(frame, InterimTranscriptionFrame):`) | **Yes for `TranscriptionFrame`.** `InterimTranscriptionFrame` never arrives — the forward branch becomes dead but harmless. (Confirmed: `grep -rn InterimTranscriptionFrame jarvis/ scripts/ web/` finds **only** this consumer plus the start strategy above; no captions/console/web reader — measured in §7.) |
| `TranscriptLogger` | `UserStoppedSpeakingFrame` (turn clock start) | `jarvis/bot/transcript_log.py` (`if isinstance(frame, UserStoppedSpeakingFrame):`) | **Yes** — aggregator-sourced. But the clock now starts *after* inference, which is why G3(b) needs the VAD-keyed instrument (F4, §5 Step 7). |
| `TranscriptObserver` | `TranscriptionFrame` (persist USER line) | `jarvis/bot/transcript_log.py` | **Yes** — Whisper pushes one per segment, `finalized=True`. |
| `ProgressWatcher` | `UserStartedSpeakingFrame`, `UserStoppedSpeakingFrame` | `jarvis/bot/progress_watcher.py` | **Yes** — aggregator-sourced. |
| `InterruptionNotifier` | `LLMFullResponseStart/End`, `BotStarted/StoppedSpeaking`, `InterruptionFrame` | `jarvis/bot/interruption.py` | **Yes** — reads no STT frame at all; the 2026-08-22 arming fix means the STT swap cannot move it. It also **cannot prove the swap safe** (§1.7). |
| `TurnAnalyzerUserTurnStopStrategy` | `TranscriptionFrame.finalized`, `VADUserStopped/StartedSpeakingFrame` | installed Pipecat `turn_analyzer_user_turn_stop_strategy.py` | **Runs but is bypassed under the default Whisper config (F3).** The late transcript triggers turn-start, which resets this strategy before it can gate end-of-turn; end-of-turn falls to its `# Fallback: handle transcripts when no VAD stop was received` branch. It decides again only under L15 Config W-onset. |

**Corrected conclusion.** Three consumers change behaviour under Whisper: the
start strategy (F2, barge-in timing), `SpeakerTap` (F10, scoring window — fixed),
and the turn-analyzer stop strategy (F3, bypassed under the default config). The
one *pure* behavioural loss is `InterimTranscriptionFrame`, which only
`TranscriptGate` forwards; the other two are the L15 decision and the F10 fix.

### 1.4 The Supervisor LLM wiring

`jarvis/bot/pipeline.py:512-525`, quoted in Correction 2. `settings.openai_base_url`
defaults to `https://api.openai.com/v1` (`jarvis/config.py:53`),
`settings.openai_model` to `gpt-4.1-mini` (`jarvis/config.py:54`). Both are
plain `.env`/env values; `load_settings()` calls `inject_env()` first
(`jarvis/config.py:203-205`) so a vault-held value wins over nothing and an
environment value wins over `.env` (pydantic-settings precedence).

### 1.5 The eval harness that decides the local model

`tests/evals/routing_eval.py:39-73` — `_apply_candidate_overrides()` reads three
env vars and rewrites the process environment before `load_settings()`:

- `EVAL_MODEL` → `OPENAI_MODEL` (`:62-63`)
- `EVAL_BASE_URL` → `OPENAI_BASE_URL` (`:64-65`)
- `EVAL_KEY_ENV` — **the name of another env var**, whose *value* becomes
  `OPENAI_API_KEY` (`:66-73`). A name, never a value, because the vault never
  prints values.

`:95` prints `eval model: <model>  (<base_url>)` so a recorded run is
attributable. `ACCURACY_THRESHOLD = 0.90` (`:30`); `main()` exits 0 iff the
accuracy meets it and 2 without `RUN_LIVE=1` (`:136-141`).

The bench plan's V2 protocol
(`docs/plans/MORTIMER_VOICE_MODEL_BENCH_PLAN.md:269-290`) is the recorded
precedent for how a candidate is run: **3 runs, every "Routing accuracy" line
recorded, mean compared to the gate.** T3.3 reuses that protocol verbatim.

### 1.6 The latency instrument

`scripts/latency_probe.py:21` parses `TURN user_end->first_audio = (\d+)ms` out of
`logs/bot.log`. That line is printed by
`jarvis/bot/transcript_log.py:127` (and the generic form at `:78`). Targets are
`p50 ≤ 1200 ms` non-delegated, `p50 ≤ 2500 ms` delegated, `p90 ≤ 3500 ms`
overall (`docs/plans/MORTIMER_VOICE_MODEL_BENCH_PLAN.md:18-22`), enforced by
`enforce_budget()` (`scripts/latency_probe.py:89-113`) under `--budget`.

### 1.7 The interruption defect cases the re-tune must not break

`tests/unit/test_interruption.py` — 8 tests in two classes:

- `TestNoFalsePositive::test_completed_turn_produces_no_note` (`:55`)
- `TestNoFalsePositive::test_dropped_turn_with_no_reply_in_flight_produces_no_note` (`:67`) — the 2026-08-22 TV-flood defect
- `TestNoFalsePositive::test_repeated_dropped_turns_never_accumulate_notes` (`:87`) — 20 dropped turns, zero notes
- `TestGenuineInterruption::test_mid_speech_interruption` (`:104`)
- `TestGenuineInterruption::test_while_thinking_interruption` (`:120`)
- `TestGenuineInterruption::test_disabled_flag_suppresses_injection` (`:135`)
- `TestGenuineInterruption::test_upstream_direction_ignored` (`:149`)
- `TestGenuineInterruption::test_second_interruption_in_same_turn_not_double_counted` (`:167`)

All eight are frame-level and STT-agnostic: `InterruptionNotifier`
(`jarvis/bot/interruption.py:75-121`) arms on `LLMFullResponseStartFrame`, never
on an STT frame. **The STT swap cannot break them, and they cannot prove the STT
swap is safe.** §5 Step 7 adds the tests that can.

### 1.8 Startup scripts, as they are

`scripts/run_bot.sh`, `scripts/run_admin.sh`, `scripts/run_wakeword.sh` are
identical in shape: `cd` to repo root, `set -a; . ./.env; set +a`, then
`exec .venv/bin/python -m <module>` with a `python3` fallback. `scripts/mortimer.sh`
backgrounds bot + admin + web with `nohup`, rotates `logs/*.log` through 5
generations, and `pkill -f`s on stop. **None of them survives a reboot, and none
of them is a service.** That is the whole of the T3.1 gap on the process side.

### 1.9 The vault's key resolution order

`jarvis/vault.py:104-125`, `_load_key()`:

1. `JARVIS_VAULT_KEY` env var — if present, decoded; malformed is an **error**,
   not a fall-through (`:107-108`, `_decode_key` at `:90`).
2. Otherwise `keyring.get_password("mortimer", "vault-key")` (`:53-54,111`).
   A `KeyringError` raises `VaultError` naming `security unlock-keychain` and
   `JARVIS_VAULT_KEY` (`:112-118`). A `None` result raises `VaultError` naming
   `python -m jarvis.vault init` (`:120-123`).

There is **no import command**. `export-key` prints base64 of the 32-byte key to
stdout with a warning on stderr (`jarvis/vault.py:517-522`); `rotate-key`
generates a new key, `_store_key`s it into the Keychain and re-encrypts
(`:525-536`). Moving a vault to another machine is therefore: copy
`data/secrets.vault`, and get the key there — either through the Keychain (needs
a login session) or through `JARVIS_VAULT_KEY`. §3 L11 picks the second and says
exactly why.

### 1.10 The gap, stated plainly

Mortimer's voice loop cannot run without Deepgram and without a cloud Supervisor
endpoint, because `load_settings()` requires both keys and nothing in the repo
can select a different STT. There is no Whisper path, no explicit turn-analyzer
configuration, no local-TTS path, no way to prove no cloud fallback is happening,
no memory arithmetic for a host, and no way to run the stack as a service that
survives a reboot on a machine nobody is logged into.

---

## §2 Non-goals

1. **Local TTS as the default.** R7 stands. Kokoro ships behind
   `JARVIS_TTS_PROVIDER=kokoro`, default `elevenlabs`, for measurement only.
2. **Local sub-agent models.** T3.3's scope is the Supervisor LLM. The five
   sub-agents keep resolving `config/upgrade_models.yaml` profiles against cloud
   endpoints. Correction 4 explains why, and `scripts/check_local_only.py --strict`
   is where that residual is printed.
3. **Cloud hosting.** The terminal state. No file created here names a host
   outside `jarvis/urls.py`'s defaults (K5) and the operator-authored plists.
4. **Local vision.** `mcp-screen` is untouched.
5. **Any auth, bind, token or tunnel work.** All of that is T2
   (`MORTIMER_REMOTE_ACCESS_PLAN.md`). This plan *depends on* G2 and *uses* T2's
   modules; it changes none of them.
6. **Buying hardware.** O5 stays open until §5 Step 8's arithmetic runs against a
   model that has passed §3 L7.
7. **Changing the Supervisor prompt.** The bench plan already ruled that a
   separate change (`docs/plans/MORTIMER_VOICE_MODEL_BENCH_PLAN.md` §5.4). If the
   local model misses the bare-commit-imperative cases, that is recorded, not
   patched here.
8. **Removing `DeepgramFluxSTTService`.** `JARVIS_STT_PROVIDER=deepgram` stays
   the default and stays the rollback (§9).

---

## §3 Decisions — L1…L15

### L1 — K7's three switches are `Settings` fields with rejecting validators; the enum values are exactly as K7 fixes them

```
JARVIS_STT_PROVIDER   ∈ {deepgram, whisper_mlx}                        default deepgram
JARVIS_TURN_DETECTOR  ∈ {stt, smart_turn_v3, smart_turn_coreml}        default stt
JARVIS_TTS_PROVIDER   ∈ {elevenlabs, kokoro}                           default elevenlabs
```

*Why fields and not bare `os.environ` reads.* `jarvis/config.py:143-150` already
states the house rule for this exact case: the `Settings` field exists for
discoverability and a single enforcement point does the reading. Here the single
reading point is `jarvis/bot/providers.py`, and because the values are *enums*
rather than booleans they also need validation — a typo like
`JARVIS_STT_PROVIDER=whisper-mlx` must fail at startup with the variable named,
not silently select Deepgram. The validator style is copied verbatim from
`_units_must_be_known` (`jarvis/config.py:172-182`), which exists for the same
reason ("no `false`/off state and no silent degrade").

*What `JARVIS_TURN_DETECTOR=stt` means, honestly.* Per Correction 1 the name is
historical. Its meaning in code is: **do not pass `stop=` to `UserTurnStrategies`
— take Pipecat's implicit default**, which today is
`TurnAnalyzerUserTurnStopStrategy(LocalSmartTurnAnalyzerV3())`. That is
byte-for-byte today's behaviour, which is what a default must be. The other two
values pass an explicit `stop=` list so jarvis owns `SmartTurnParams`. §5 Step 4
logs the effective analyzer class name at startup so the fact is never
re-discovered by reading Pipecat's source again.

### L2 — one factory module, `jarvis/bot/providers.py`, is the only place the switches are read

Five factory functions plus one helper, each pure w.r.t. `Settings`:

```
build_stt(settings, keyterms) -> STTService
build_turn_start_strategies(settings, speaker_gate_state) -> list[BaseUserTurnStartStrategy]   # L15
build_turn_stop_strategies(settings) -> list[BaseUserTurnStopStrategy] | None
build_tts(settings, voice_row) -> TTSService
tts_voice_id(voice_row, settings) -> str
effective_turn_analyzer_name(settings) -> str            # startup-log helper
```

*Why a module and not three `if` blocks in `build_pipeline`.* `build_pipeline` is
already ~360 lines (`jarvis/bot/pipeline.py:330-694`). Three inline branches would
be three more things to keep in sync with the voice-switch path, and taxonomy item
4 (two sections describing the same behaviour differently) is exactly how that
goes wrong — `tts_voice_id` exists because the voice id is read at **three**
sites (`jarvis/bot/pipeline.py:546`, `jarvis/bot/pipeline.py:1067`,
`jarvis/bot/voice_switch.py:89`) and a Kokoro build must not change two of them
and forget the third. A pure module is also unit-testable without a transport,
which §7 uses.

### L3 — the STT swap replaces the object in slot 4 and nothing else

`pipeline_steps` (`jarvis/bot/pipeline.py:670-693`) is unchanged; only
`stt = DeepgramFluxSTTService(...)` at `:480-500` becomes `stt = build_stt(settings)`.
*Why:* §0.9 (locked order), and because §1.3 proves every downstream consumer is
fed by the aggregator or by `TranscriptionFrame`, both of which survive.

### L4 — Whisper is `WhisperSTTServiceMLX` with `MLXModel.LARGE_V3_TURBO`, English-locked, `no_speech_prob=0.6`

```python
WhisperSTTServiceMLX(settings=WhisperSTTServiceMLX.Settings(
    model=MLXModel.LARGE_V3_TURBO.value,   # "mlx-community/whisper-large-v3-turbo"
    language=Language.EN,
    no_speech_prob=0.6,
    temperature=0.0,
))
```

*Why each value.*
- `MLXModel.LARGE_V3_TURBO` = `"mlx-community/whisper-large-v3-turbo"`
  (`pipecat/services/whisper/stt.py:99`) — the roadmap's stated choice, and the
  constructor's own default is `MLXModel.TINY` (`…/stt.py:441`), so **not passing
  it silently ships `tiny`**. That is the trap this decision exists to close.
- `Language.EN`: locks the decoder. The service's own default is already
  `Language.EN` (`…/stt.py:442`); passing it makes the lock explicit and survives
  a Pipecat default change.
- `no_speech_prob=0.6` is the service default (`…/stt.py:443`); it is named here
  so §6 can own it as a tuning knob rather than leaving a live number implicit.
  Note the filter's direction: `stt.py:365-370` accumulates a segment when
  `segment.no_speech_prob < threshold`, i.e. **lower is more silence-suspicious**;
  raising the number keeps *more* audio. Do not "tighten" it by raising it.
- `temperature=0.0`: greedy decode, deterministic transcripts. A voice agent that
  transcribes the same audio two ways across a retry is unreviewable.
- **Delta-mode `Settings` is correct here.** `ServiceSettings.apply_update`
  merges only fields that are *given* (`pipecat/services/settings.py:226-243`),
  and the constructor builds a full store-mode default first
  (`…/whisper/stt.py:440-446`) then applies the delta (`…/stt.py:472-473`). So a
  four-field `Settings(...)` is a legal delta.
- Import from the module, not the package: `pipecat/services/whisper/__init__.py`
  is empty. Use `from pipecat.services.whisper.stt import MLXModel, WhisperSTTServiceMLX`
  and `from pipecat.transcriptions.language import Language`
  (`pipecat/services/whisper/stt.py:26`).

### L5 — `deepgram_api_key` and `elevenlabs_api_key` become optional, and `REQUIRED_ENV_VARS` becomes provider-derived

Without this, G3(e) is unsatisfiable (Correction 2). The rule, exactly:

| Provider selection | Required env vars |
|---|---|
| `JARVIS_STT_PROVIDER=deepgram` | `DEEPGRAM_API_KEY` |
| `JARVIS_STT_PROVIDER=whisper_mlx` | *(none from STT)* |
| `JARVIS_TTS_PROVIDER=elevenlabs` | `ELEVENLABS_API_KEY` |
| `JARVIS_TTS_PROVIDER=kokoro` | *(none from TTS)* |
| always | `OPENAI_API_KEY` |

`OPENAI_API_KEY` stays unconditionally required because `OpenAILLMService` passes
it to the OpenAI SDK client, which rejects `None`. For a local server the value is
the literal sentinel **`local`** (Pipecat's own Ollama service does the same with
`api_key="ollama"` — `pipecat/services/ollama/llm.py:76`). `scripts/check_local_only.py`
knows that sentinel (L12).

*Why not delete the fields.* Deleting a `Settings` field means sweeping every test
fixture that constructs `Settings(...)` positionally or by keyword — there are at
least twelve (`tests/unit/test_subagent.py:22`, `tests/unit/test_memory.py:62`,
`tests/integration/test_bot_wiring.py:87,484`, …). `str | None = None` changes
none of them.

### L6 — the local OpenAI-compatible server is **Ollama**, at `http://127.0.0.1:11434/v1`

Chosen against the four the roadmap named, on four requirements the mini imposes:
headless operation with no logged-in GUI session; a launchd-manageable long-lived
process; OpenAI-compatible `/v1/chat/completions` **with tool calling** (the
Supervisor is nothing but tool calls — `delegate_task`, `set_voice`, `remember`,
`ui_control`, `view_screen`, `list_screens`, `show_commands`, `clear_clipboard`,
`read_clipboard`, registered at `jarvis/bot/pipeline.py:526-542`); and a
model-residency control, because a model that unloads between turns turns the
first turn after a pause into a 20-second cold start.

| Candidate | Verdict | Why |
|---|---|---|
| **Ollama** | **chosen** | Single static binary, `ollama serve` is a plain foreground process — the exact shape launchd wants. OpenAI-compatible `/v1/chat/completions` with `tools`. `OLLAMA_KEEP_ALIVE` controls residency directly. Model identity is one string (`qwen3:32b-q4_K_M`) that is both the pull command and the `OPENAI_MODEL` value — which matters because `EVAL_MODEL` is a *string*, and a server whose model id differs from its download id is a source of mis-attributed eval runs. Pipecat treats it as plain `OpenAILLMService` (`pipecat/services/ollama/llm.py:24,76`), so nothing in jarvis changes. |
| LM Studio | rejected | GUI-first. Headless operation goes through `lms server start`, which still expects the app's support directory and an interactive first-run. On a mini with no login session that is a second failure mode stacked on the Keychain one (L11). |
| vLLM | rejected | No Metal backend. vLLM targets CUDA/ROCm; on Apple Silicon it has no GPU path, so the model would run on CPU at unusable speed. |
| MLX (`mlx_lm.server`) | rejected | Fastest raw generation on Apple Silicon, but its OpenAI shim's tool-calling support is model-template-dependent and it has no model manager, no residency control, and no stable model-id convention — three operational holes for a marginal token-rate gain that is not the bottleneck (§1.6's budget is dominated by TTFT, not by generation). Keep as the documented escape hatch in §10 R-L4 if Ollama's throughput fails the latency gate. |

**Base URL is `http://127.0.0.1:11434/v1`** — loopback, not the tailnet address.
The Supervisor process and Ollama live on the same box; exposing the model server
on the tunnel would let any tunnel-joined device run inference with no token (K1
covers Mortimer's routes, not Ollama's).

### L7 — local-model selection is a decision tree over `RUN_LIVE=1 python -m tests.evals.routing_eval`, run on the candidate ladder in order, smallest-first

**Candidate ladder** (Ollama tags; run **in this order**, stop at the first
model that passes both gates — smallest passing model wins, because §3 L9's RAM
arithmetic is the binding constraint on the hardware Larry has not bought yet):

The ladder is ordered **strictly ascending by disk estimate** — the same quantity
L9's RAM arithmetic keys on — corrected after review F11, which found the draft's
order put #2 (~18 GB) before #3 (~13 GB) and #4 (~15 GB) while claiming
"smallest-first".

| # | Ollama tag | Class | Disk estimate | Why on the list |
|---|---|---|---|---|
| 1 | `qwen3:14b-q4_K_M` | dense 14B | ~9 GB | Smallest tag with reliable multi-tool function calling; if it passes, O5 becomes a 32 GB question. |
| 2 | `gpt-oss:20b` | dense 20B, MXFP4 | ~13 GB | Different family — a hedge against a Qwen-specific tool-template problem. |
| 3 | `mistral-small3.2:24b-instruct-2506-q4_K_M` | dense 24B | ~15 GB | Third family; strong instruction following, well-tested tool calls. |
| 4 | `qwen3:30b-a3b-instruct-q4_K_M` | MoE, ~3B active | ~18 GB | Best latency-per-capability: MoE active-parameter count sets TTFT, total weight sets RAM. Likely to satisfy both gates at once — but it is *larger on disk* than #2/#3, so it is tried after them, per the ascending rule. |
| 5 | `qwen3:32b-q4_K_M` | dense 32B | ~20 GB | Capability step up if 1–4 all miss on routing rather than latency. |
| 6 | `llama3.3:70b-instruct-q4_K_M` | dense 70B | ~43 GB | Last resort. Only reachable on ≥ 96 GB by L9's arithmetic; if this is the only passer, the honest answer is R-T3a (cloud Supervisor), not a bigger mini. |

**Disk estimates are estimates and are not the sizing input.** The number L9 uses
is what `ollama ps` prints in its `SIZE` column after one warm request. Record
that, not this table.

**The tree.** For each candidate, in ladder order:

```
STEP A — pull and warm (F6: warm with the REAL system prompt, not a ping)
  ollama pull <tag>
  # One real routing-eval run carries the ~3.4k-token Supervisor system prompt
  # and the nine tool schemas, so the KV cache — and thus `ollama ps` SIZE — is
  # sized for the real workload. A `max_tokens:8` "ping" would under-size it.
  EVAL_MODEL='<tag>' EVAL_BASE_URL=http://127.0.0.1:11434/v1 \
    EVAL_KEY_ENV=OLLAMA_API_KEY RUN_LIVE=1 python -m tests.evals.routing_eval
  ollama ps            # NOW record the SIZE column -> LLM_RESIDENT_GB for L9
  # Precondition (F6): OLLAMA_CONTEXT_LENGTH=16384 must be set in
  # com.mortimer.llm.plist. Ollama's 4096 default SILENTLY TRUNCATES the
  # Supervisor prompt and routing collapses for a reason that is not the model.
  # If this first run's routing looks catastrophic (< 50%), check
  # OLLAMA_CONTEXT_LENGTH before blaming the candidate.

STEP B — tool-call fidelity (cheap disqualifier, run before the 3-run eval)
  python scripts/voice_model_bench.py            # with EVAL_* set as in Step C
  If the candidate malforms tool calls -> DISQUALIFY, next candidate.
  (Precedent: MORTIMER_VOICE_MODEL_BENCH_PLAN.md:99 —
   "A model that malforms tool calls is disqualified".)

STEP C — routing accuracy, 3 runs, record every line
  export OLLAMA_API_KEY=local
  for i in 1 2 3; do
    EVAL_MODEL='<tag>' \
    EVAL_BASE_URL=http://127.0.0.1:11434/v1 \
    EVAL_KEY_ENV=OLLAMA_API_KEY \
    RUN_LIVE=1 python -m tests.evals.routing_eval
  done
  mean = (run1 + run2 + run3) / 3

STEP D — decision (ladder is strictly ascending, so there is no "smaller passer")
  IF mean >= 90%  AND  STEP E passes:
      ADOPT this candidate. Stop the ladder. Record the three lines and the mean
      in §8 A1. Set OPENAI_MODEL=<tag>, OPENAI_BASE_URL=http://127.0.0.1:11434/v1,
      OPENAI_API_KEY=local.
  IF mean >= 90%  AND  STEP E fails (accuracy pass, latency fail):
      The ladder is ascending, so every remaining candidate is BIGGER and
      therefore slower — none can fix a latency failure. Record
      "accuracy pass, latency fail" and go straight to STOP. Do NOT search
      backwards for a "smaller passer": by construction every earlier candidate
      already FAILED, so no such candidate exists (F11).
  IF mean < 90%:
      Next candidate on the ladder.
  IF the ladder is exhausted:
      -> STOP.

STEP E — latency gate (hard, same instrument as the bench plan)
  Larry runs 10 spoken turns (5 non-delegated, 5 delegated) on the mini, then:
      python scripts/latency_probe.py logs/bot.log --budget
  PASS = exit 0 (p50 <= 1200 ms non-delegated, p50 <= 2500 ms delegated,
  p90 <= 3500 ms overall — scripts/latency_probe.py:89-113).

STOP — no candidate passes
  Report, in these words, and change nothing else:
    "No local Supervisor model on the T3.3 ladder passed both gates.
     Per roadmap R-T3a the fallback is: local STT (T3.2) with a CLOUD
     Supervisor. T4b stays gated by C3 until this is revisited."
  Leave JARVIS_STT_PROVIDER=whisper_mlx, leave OPENAI_BASE_URL pointing at the
  cloud endpoint it points at today, and do NOT relax the 90% threshold.
```

*Why smallest-first and why stop at the first passer.* O5 (mini RAM) is still
open and is decided by L9's arithmetic on the chosen model. Ranking by capability
would pick the largest passer and then demand the largest machine, which inverts
the roadmap's own sequencing (*"do not buy before the eval runs"* — roadmap §7 O5).

*Why 3 runs and the mean.* `MORTIMER_VOICE_MODEL_BENCH_PLAN.md:290-297` recorded
Haiku swinging 85 % → 91 % across three runs on the same corpus. One run decides
nothing.

*The exact model-string format the eval needs.* `EVAL_MODEL` is copied verbatim
into `OPENAI_MODEL` (`tests/evals/routing_eval.py:62-63`) and from there into
`OpenAILLMService(model=...)` (`jarvis/bot/pipeline.py:524`). For Ollama that
string is the **full tag including the quantization suffix**, e.g.
`qwen3:30b-a3b-instruct-q4_K_M` — not `qwen3`, not `qwen3:30b`. Ollama resolves a
bare name to whatever it last pulled, which is how a recorded eval ends up
credited to the wrong weights.

### L8 — the G3(b) re-tune: a measurement with an instrument that actually spans the penalty, and a floor that depends on the L15 config

Corrected after review (F3/F4). The draft's re-tune measured a quantity that
**cannot see the Whisper penalty** and used a floor (1.75) that is **below** the
known failure point. Both are fixed here.

**The instrument (F4).** The end-to-end line the draft used,
`TURN user_end->first_audio`, starts its clock at the aggregator's
`UserStoppedSpeakingFrame` (anchor `if isinstance(frame, UserStoppedSpeakingFrame):`
in `jarvis/bot/transcript_log.py`). Under Whisper that broadcast waits for the
transcript, so the entire STT penalty **and** the `stop_secs` window both land
*before* the clock starts — the number is ≈ baseline whether or not the experience
regressed, and lowering `stop_secs` moves it by ≈ 0. The re-tune therefore adds a
second instrument keyed on `VADUserStoppedSpeakingFrame` — which **both** providers
emit from the VAD at the same instant, independent of STT —
`TURN vad_stop->first_audio` (§5 Step 7 wires it, §6 owns it). That interval
contains the STT latency **and** the `stop_secs` window, so the bound is meaningful
and the lever actually moves it. `B_ms`/`M_ms` are the **medians of that new line**,
not the old one.

- The **baseline** is measured first on Deepgram, same machine, same session
  shape: `JARVIS_STT_PROVIDER=deepgram`, 10 turns, `median(TURN vad_stop->first_audio)`
  → `B_ms`. **G3(b)'s bound is `B_ms + 150`** (roadmap §4 G3(b)), a bound on the
  median.

**The floor depends on the L15 config, because the analyzer's role does.**

- **Config W-safe (default):** the analyzer is bypassed (F3), so `stop_secs` is the
  *segmentation boundary* — a mid-sentence pause ≥ `stop_secs` makes Whisper cut and
  transcribe half a sentence, with no analyzer to merge it and no second chance.
  D-010 measured a sample-exact 2.000 s gap. Therefore under W-safe **`stop_secs`
  stays at 2.5 — no lowering** — and G3(b) has no latency lever: record `M_ms` at
  2.5 as MET or NOT MET. If NOT MET, that is the honest R6 outcome, reported
  verbatim (§5 Step 7 failure branch), not tuned away.
- **Config W-onset (opt-in):** the analyzer decides again and merges pauses across
  VAD stops, so `stop_secs` may be lowered from 2.5 in 0.25 steps to a floor of
  **2.0** — *not* below, because 2.0 is D-010's measured gap and the analyzer needs
  the VAD window to be at least as long as a legitimate pause to keep the turn open
  across it. Lowering is allowed only while the §7 turn-ordering test and the D-010
  single-turn live check stay green.

**Rejection rule:** if the applicable floor cannot get `M_ms ≤ B_ms + 150` while
the D-010 single-turn check passes, the procedure **stops and reports G3(b)
failure** (§5 Step 7 failure branch). It never relaxes the bound and never lowers
below the floor.

**One more term in the interval: `WHISPER_TTFS_P99 = 1.0` (F20).** The turn-stop
strategy computes its safety-net timeout as `max(0, ttfs_p99 - stop_secs)`
(installed Pipecat, anchor `timeout = max(0, self._stt_timeout - self._stop_secs)`).
With `WHISPER_TTFS_P99 = 1.0` (set explicitly in `build_stt`, §5 Step 2, so Pipecat
does not warn and fall back to its own 1.0), any `stop_secs ≥ 1.0` collapses that
timeout to 0 — a second, independent reason the floor never approaches 1.0.

`SmartTurnParams.stop_secs` (the analyzer's *internal* silence threshold, default
3 s) is deliberately **not** the lever and stays at pipecat's default; the lever is
always the VAD `stop_secs` in the pipeline. Moving both at once makes the
measurement uninterpretable.

### L9 — the T3.5 RAM formula, headroom counted once, and a REJECT branch that actually exists

Corrected after review F12: the draft counted OS headroom **twice** (an additive
8 GB *and* a multiplicative ×0.85), and asked for an `STT_GB` delta whose starting
point no step captured.

```
# PROCESS demand only — no OS term inside this sum:
PROCESS_GB  =  LLM_RESIDENT_GB      (measured: `ollama ps` SIZE, after the STEP A real request)
             + STT_GB               (measured: see §5 Step 8 S2a-S2c; = max(2.5, RSS delta))
             + TURN_GB              (0.5 — smart-turn-v3.2-cpu.onnx + onnxruntime arena)
             + SPEAKER_GB           (0.5 — jarvis/speaker.py encoder, when a profile is enrolled)
             + PYTHON_STACK_GB      (3.0 — bot + sidecar + the MCP children + aiortc)

# OS headroom is added ONCE, here, and nowhere else:
REJECT  IF  PROCESS_GB + OS_HEADROOM_GB(8.0)  >  PHYSICAL_RAM_GB
```

*Why headroom is counted once (F12).* `OS_HEADROOM_GB = 8.0` (roadmap §2.3 T3.5)
and a ×0.85 multiplier are the **same reservation** — both exist to keep macOS out
of compression/swap. Applying both reserved 8 + 0.15·RAM twice: on a 48 GB machine
that was 15.2 GB (32 %) held back for one purpose, and it rejected a 36 GB mini
whose actual process demand was 27 GB. The corrected rule reserves the 8 GB OS
headroom additively and compares against physical RAM directly.

*Why measured, not table-derived, for the two big terms.* A quantized model's
resident size is weights **plus** KV cache plus the runtime's arena, and the KV
cache scales with context — and the Supervisor's context is not small (system
prompt + voice addendum + up to three tool addenda + conversation, assembled in
`jarvis/bot/pipeline.py`, anchor `def build_pipeline`). `ollama list` reports the
file on disk and under-counts; `ollama ps` after the STEP A *real-system-prompt*
request (F6) reports what is actually resident for the real workload.

*Why `STT_GB = max(2.5, delta)` and not "use 2.5 if you can't measure cleanly"
(F12).* MLX allocates in Apple's **unified** memory pool, a large fraction of which
`ps` RSS does not attribute to the process, so the RSS delta is a *lower bound*, not
an estimate that might be clean or dirty. The `max()` is therefore not a
judgment-call fallback: it is the correct combination of a measured lower bound with
the known floor (large-v3-turbo's ~1.6 GB fp16 weights plus the MLX arena ≈ 2.5 GB).

*What REJECT means, concretely (F11).* The L7 ladder is strictly ascending, so
there is **no** tested candidate that is both smaller and passing — the search
"backwards for a smaller passer" the draft described is empty by construction.
So REJECT records `PROCESS_GB`/`REQUIRED` and takes **L7's STOP branch** verbatim
(cloud Supervisor, T4b stays gated). **Buying more RAM is not a branch** — O5's
whole point is that the eval decides the hardware.

*Worked example, re-derived under the corrected rule* (real numbers come from
Larry's run): `qwen3:30b-a3b-instruct-q4_K_M` at a measured 20.5 GB resident →
`PROCESS_GB = 20.5 + 2.5 + 0.5 + 0.5 + 3.0 = 27.0 GB`. Add OS headroom once:
`27.0 + 8.0 = 35.0 GB`. On a 48 GB mini, `35.0 ≤ 48` → **accept**. On a 36 GB mini,
`35.0 ≤ 36` → **accept** (the draft's double-count wrongly rejected this). On a
32 GB mini, `35.0 > 32` → **reject** → L7 STOP branch.

### L10 — the relocation runbook is launchd **LaunchDaemons**, three services, one wrapper script, and no secret in any plist

Corrected after review F5. The draft used **LaunchAgents** (`gui/<uid>`), which
load at *login*, not boot — so they cannot come up on a headless reboot, which is
exactly what gate G3(d) demands. And a `gui/<uid>` agent only runs when a login
session exists, at which point the login Keychain is unlocked and L11's whole
justification for a plaintext key file evaporates. The draft took the security cost
of the key file *without* the operational benefit it is supposed to buy.

**The fix: three `LaunchDaemons` in `/Library/LaunchDaemons/`**, each with
`<key>UserName</key><string>USERNAME</string>` set to Larry's user so the process
runs as him (his `$HOME`, his Homebrew prefix) while **starting at boot with no
login**. `scripts/launchd_exec.sh` supplies `HOME`, the Homebrew `PATH` and
`TMPDIR` explicitly (a daemon inherits almost nothing), so the "needs `$HOME`"
objection to daemons is handled in the wrapper, not by choosing agents. Load with
`sudo launchctl bootstrap system <plist>`.

| Label | Runs | Why a service |
|---|---|---|
| `com.mortimer.llm` | `ollama serve` | Must be up before the bot's first turn; `OLLAMA_KEEP_ALIVE=-1` keeps weights resident. |
| `com.mortimer.admin` | `python -m jarvis.admin.server` | The sidecar owns self-edit and git; the drawer and the watchers call it. |
| `com.mortimer.bot` | `python -m jarvis.bot.bot` | The voice loop. |
| `com.mortimer.tailscale` | *not created* | Tailscale installs and manages its own; §5 Step 9.1 only verifies it. |

**Wake word stays on the client** (roadmap §2.3 T3.1: *"Wake word stays
client-side (it listens to the raw mic)"*). `scripts/run_wakeword.sh` continues to
run on the MacBook / native client host, and it reaches the mini through
`JARVIS_BOT_URL` (K5 — `MORTIMER_REMOTE_ACCESS_PLAN.md` §3 A11). No plist for it
on the mini. §5 Step 9.7 says what to check.

*Why not `scripts/mortimer.sh` on the mini.* It `nohup`s and `pkill -f`s
(`scripts/mortimer.sh:33-38`); nothing restarts a crashed process and nothing
survives a reboot. Those are the two properties T3.1 is for. `mortimer.sh` stays
exactly as it is for the MacBook development flow.

### L11 — on the mini the vault key comes from `JARVIS_VAULT_KEY`, sourced by the daemon wrapper from a `0600` root-owned file outside the repo; **the Keychain is not used there**

This is the decision the runbook exists to make, so it gets the full reasoning,
and (per review F5) the honest security cost stated without softening.

**The problem.** `jarvis/vault.py` (anchor `keyring.get_password("mortimer",
"vault-key")`) reads the macOS **login keychain**, which is unlocked only inside an
interactive GUI login. A headless mini booting unattended has no such session, so
the Keychain path leaves the bot in a crash loop whose error is
`VaultError: could not read the vault key from the keychain`. With the F5 switch to
LaunchDaemons the box now *does* come up headless at boot — which makes the Keychain
strictly unavailable there and the env-var path mandatory, not merely preferred.

**The decision.** On the mini, `JARVIS_VAULT_KEY` is set. `jarvis/vault.py` (anchor
`def _load_key`) checks it **first**, before the Keychain, and a malformed value is
an error rather than a fall-through — so there is no ambiguity about which path was
taken. Because the daemons run at boot before any user logs in, the key file is
**root-owned, mode `0600`** at `/usr/local/etc/mortimer/vaultkey`, one line
`JARVIS_VAULT_KEY=<base64>`; the daemon's `UserName` is Larry, and
`scripts/launchd_exec.sh` (run as Larry) reads it — so it must be readable by Larry,
i.e. owned by Larry mode `0600` (a root-only file a UserName=Larry daemon cannot
read is the failure the runbook's `ls -l` check catches). Every plist runs
`scripts/launchd_exec.sh <module>`, which sources that file and `exec`s.

**Alternatives, evaluated (F5), and why each is worse:**
- `launchctl setenv JARVIS_VAULT_KEY <b64>` — **rejected**: readable by any process
  on the machine via `launchctl getenv`, and system-wide. Strictly worse than a
  `0600` file.
- **Auto-login + LaunchAgent + Keychain** — no plaintext key at rest, but reboot
  recovery then depends on a GUI login completing, and auto-login requires FileVault
  **off**, and the login password is itself stored for auto-login. Only acceptable
  if the mini is a trusted physical location with FileVault off; it does not meet
  "comes up unattended after an OS-update reboot".
- `security unlock-keychain` in the wrapper — needs the keychain password, another
  secret, same problem one level down.
- **Interactive unlock at boot** — not viable; nothing is there to type.

The chosen LaunchDaemon + `0600` key file is the only option that satisfies G3(d)
(boot, no login) honestly. Its residual is R-L2, stated plainly there: the master
key is readable at rest by anything that can read one file as Larry — a compromised
MCP child (K2 scopes env, not the filesystem), any backup, Time Machine,
`find / -perm 600`. That is a real move from "Keychain ACL" to "file mode", and — a
correction the draft's R-L2 got wrong — a real move toward *exposed*, because a file
read is now a key read. The T4b sensitive-tier key is explicitly **not** in this
vault (R8: the client holds it), which is why this is acceptable for T3.

**Why not in the plist.** C9. A plist under `/Library/LaunchDaemons` is
world-readable, backed up by Time Machine in the clear — exactly the "never in a
plist" case C9 names. No `EnvironmentVariables` entry carries a secret.

**The MacBook is unchanged.** `JARVIS_VAULT_KEY` is not set there; the Keychain path
still wins. Two hosts, two key sources, one resolution order that handles both.

### L12 — G3(e) is a script, `scripts/check_local_only.py`, with two modes and fixed rules

**One shared config resolver `cfg()` (review F9), stated here once.** Both
`scripts/check_local_only.py` and `scripts/check_env.py` must read every config
variable through the **same** order production reads it: `os.environ` first (which
`jarvis.vault.inject_env()` has populated from the vault, and which launchd's
wrapper / the run scripts populate from `.env` via `set -a; . ./.env`), then the
repo `.env` as a fallback. Reading `os.environ` **alone** would miss a `.env`-only
`JARVIS_STT_PROVIDER` (the draft's bug); reading `.env` alone would miss a
launchd/vault value. The resolver is:

```python
def cfg(name: str, default: str = "") -> str:
    v = os.environ.get(name)
    if v:
        return v
    return _dotenv().get(name, default)   # simple KEY=VALUE parse of repo .env
```

Measured (§7): `os.environ` wins when set, `.env` fills in when it is not. **Every**
`os.environ.get(...)` in the rules below and in §5 Step 6 is `cfg(...)`.

Default mode answers the gate's actual question — *is the voice loop free of
cloud STT/LLM credentials?* — with these rules, in order:

1. `cfg("JARVIS_STT_PROVIDER")` must be `whisper_mlx`. Otherwise **FAIL**: "STT
   provider is `<value>`; G3(e) requires whisper_mlx".
2. `DEEPGRAM_API_KEY` must be absent from both `os.environ` (after
   `jarvis.vault.inject_env()`) and the vault's name list
   (`jarvis.vault.load_secrets().keys()` — names only, never values). Present →
   **FAIL**, naming which source held it.
3. `cfg("OPENAI_BASE_URL")` must resolve to a loopback host. The test is
   `urllib.parse.urlparse(url).hostname in {"127.0.0.1", "::1", "localhost"}`.
   Anything else → **FAIL**, printing the host.
4. `cfg("OPENAI_API_KEY")` must be **exactly the sentinel `local`** — *not* "or
   absent" (corrected after F14: §3 L5 makes `OPENAI_API_KEY` unconditionally
   required, so an absent value passes G3(e) on a machine where the bot cannot even
   start). Anything else → **FAIL**: "OPENAI_API_KEY must be the sentinel 'local'
   for a local server (absent means the bot cannot start — see
   jarvis/config.py required_env_vars)".
5. `ELEVENLABS_API_KEY` present is **expected and reported, not failed** — R7
   keeps TTS in the cloud. The script prints
   `residual: ElevenLabs sees every spoken reply (roadmap R7)`. Absent → print
   `note: TTS credential absent; JARVIS_TTS_PROVIDER must be kokoro` and **FAIL**
   only if `cfg("JARVIS_TTS_PROVIDER") != "kokoro"`, with the message
   `FAIL ELEVENLABS_API_KEY absent but JARVIS_TTS_PROVIDER is '<v>'; the voice loop has no TTS`.
6. Sub-agent key envs (`ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY`,
   `MOONSHOT_API_KEY` — the `api_key_env` values in
   `config/upgrade_models.yaml`, anchor `api_key_env:`) are **printed as residuals,
   not failed**, per Correction 4.

`--strict` additionally fails on rule 6. Nothing in T3 requires strict to pass;
`MORTIMER_SENSITIVE_TIER_PLAN.md` will.

Exit 0 iff every applicable rule passes. **Never prints a secret value** — the
same discipline `jarvis/vault.py` and `scripts/check_env.py:147-148` already keep.

### L13 — Kokoro is wired behind the flag with a fixed voice, and Larry gets a blind A/B script

`JARVIS_TTS_PROVIDER=kokoro` builds
`KokoroTTSService(settings=KokoroTTSService.Settings(voice=<KOKORO_DEFAULT_VOICE>))`.
`KokoroTTSService` auto-downloads its ONNX model and voices file on first use
(`pipecat/services/kokoro/tts.py:39-62,102`) — a **network fetch at first
synthesis**, which is why it is off by default and why §5 Step 5 pre-fetches it in
the runbook rather than discovering it mid-turn.

**Voice handling in Kokoro mode is fixed, not mapped.** `config/voices.yaml`'s rows
carry `elevenlabs_voice_id` and nothing else (read at `jarvis/bot/pipeline.py:546`,
`:1067`, `jarvis/bot/voice_switch.py:89`). Rather than invent a second id column
for a measurement-only flag, `tts_voice_id(voice_row, settings)` returns
`KOKORO_DEFAULT_VOICE` for every row when the provider is `kokoro`. Consequence,
stated so it is not a surprise: **`set_voice` becomes a no-op in Kokoro mode** —
the `voice/current` app-message still round-trips (so the UI reconciles,
`jarvis/bot/pipeline.py:1071-1073`) but the voice does not change. That is
acceptable for a default-off measurement path and unacceptable as a default, which
is one more reason R7 stands.

**The A/B script** `scripts/tts_ab.py` synthesizes the same N sentences through
both providers, writes them to a directory with **shuffled, non-revealing
filenames** (`a1.wav … a2N.wav`) plus a `key.json` Larry does not open until he has
scored, and prints the scoring sheet. R7's revisit condition is *"a blind A/B
Larry runs himself"* — a script that labels the files `kokoro_1.wav` would not be
one.

### L14 — nothing in this plan names the mini

Per roadmap §6 invariant 1. The audit: after §5, the literal hosts introduced by
this plan are (a) `http://127.0.0.1:11434/v1` as the *documented default* for
`OPENAI_BASE_URL` in `README.md` and in the runbook's plist — not in Python; and
(b) `scripts/check_local_only.py`'s loopback allow-set, which is a *test* of a
value, not a source of one. `jarvis/bot/providers.py` contains no host at all.
Everything client-facing goes through `jarvis/urls.py` (K5).

### L15 — the barge-in / turn-analyzer trade under Whisper is a Larry decision with two fully-wired configs; the default reopens no defect

This decision exists because the review (F2/F3) proved that a segmented STT cannot
reproduce Flux's verified barge-in, and that the choice is a real trade rather than
a tuning value. It is re-derived here from the installed Pipecat source, not from
the draft's claims.

**The mechanism, verified.** jarvis installs `start=[turn_start_strategy]`, which
**replaces** pipecat's default start list `[VADUserTurnStartStrategy(),
TranscriptionUserTurnStartStrategy()]` (installed Pipecat,
`default_user_turn_start_strategies()`). The installed strategy starts a turn only
on a transcript (anchor
`elif isinstance(frame, InterimTranscriptionFrame) and self._use_interim`).
Turn-start does two coupled things through the aggregator: it broadcasts
`UserStartedSpeakingFrame` **and** calls `broadcast_interruption()`. And
`UserTurnController._trigger_user_turn_start` (anchor
`# Reset all user turn stop strategies to start fresh`) resets the stop strategies.
Therefore:

- With **Flux**, the interim transcript starts the turn ~0.5 s into speech, so
  (a) verified barge-in fires ~0.5 s in, and (b) the analyzer's verdict computed at
  `VADUserStoppedSpeakingFrame` survives (the reset happened earlier) and gates
  end-of-turn.
- With **Whisper**, the only transcript is post-VAD-stop, so (a) verified barge-in
  moves to VAD-stop+inference, and (b) that late transcript's turn-start resets the
  analyzer, so end-of-turn falls to the `# Fallback: handle transcripts when no VAD
  stop was received` branch — the analyzer runs and is ignored.

Both effects are fixed by the same one change — **prepend `VADUserTurnStartStrategy()`
to the start list** — because starting the turn at VAD onset restores onset barge-in
*and* keeps the analyzer's verdict from being reset. But onset turn-start means the
interruption broadcast fires at VAD onset, **before any speaker score or word count
exists** — exactly the unverified interruption that `should_interrupt=False` was
introduced to kill (the 2026-08-22 TV-flood: 26 broadcasts in one 19-minute session
while every TV transcript was correctly dropped). Under a segmented STT you cannot
have both speaker-verified interruptions *and* onset-timed barge-in, because the
verification needs a transcript and the transcript does not exist until the segment
closes. That is the trade.

**The two configs, both implemented, selected by one flag
(`JARVIS_WHISPER_VAD_BARGE_IN`, default `false`):**

| | **Config W-safe (default)** | **Config W-onset (opt-in)** |
|---|---|---|
| Start strategy under `whisper_mlx` | `[speaker_verified_min_words]` (unchanged) | `[VADUserTurnStartStrategy(), speaker_verified_min_words]` |
| Barge-in during bot speech | fires at VAD-stop+inference (**degraded** — an R6 barge-in-parity miss) | fires at VAD onset (**parity restored**) |
| Interruption verification | speaker-gated as today, but only once the segment transcript exists | **none at onset** — a TV can interrupt the bot (transcript still dropped by `TranscriptGate`, but the reply is already interrupted) |
| Smart-turn analyzer | bypassed (F3); end-of-turn = VAD-stop segmentation | **decides again** (turn starts at onset, not reset); merges mid-sentence pauses across VAD stops into one aggregated user turn |
| Mid-sentence pause (D-010) | splits at `stop_secs`; the analyzer cannot merge across a Whisper segment boundary, so `stop_secs` floor is **2.5, no lowering** | analyzer holds the turn open across the pause; the multiple Whisper segments aggregate |
| Reopens the 2026-08-22 TV defect? | **No** | **Yes, by construction** |

**The decision rule.** Default is **W-safe**, because C10 (degradation-proof) and
the hard-won `should_interrupt=False` fix forbid silently reopening the TV defect.
W-safe's cost is honest and recorded: barge-in is slower and the analyzer is
bypassed — this is an R6 barge-in-parity **miss**, reported as such in §8 B, not
hidden. Larry evaluates W-onset on his hardware using the **same P5 TV-soak** that
already exists (§5 Step 7 P5): W-onset is acceptable **only if** its 10-minute
TV-soak still shows zero spurious `interrupted` lines. If the TV interrupts under
W-onset, W-onset is rejected and the recorded outcome is that Whisper cannot match
Flux's barge-in on this setup — a roadmap-R6 fact for Larry, not a thing this plan
tunes away.

**Why a flag and not a plan-time pick.** The choice is inherently empirical (it
depends on Larry's room, his TV, his voice-gate scores) and §8 is already
"Larry measures on hardware". The flag lets him A/B both configs with no code
change, matching every other switch in this plan. `build_turn_start_strategies`
(§5 Step 2) is the single read site; the flag is a validated `Settings` field like
the K7 three.

---

## §4 Files (create / modify / delete — complete manifest)

Every file named in §5 appears here, and every file here is touched by a §5 step.

Anchor strings are given per row (CP-F9); line numbers are indicative only.

### Create (13)

| Path | What | §5 step |
|---|---|---|
| `jarvis/bot/providers.py` | `build_stt`, `build_turn_stop_strategies`, `build_turn_start_strategies` (L15), `build_tts`, `tts_voice_id`, `effective_turn_analyzer_name` (L2), and the constants `KOKORO_DEFAULT_VOICE`, `WHISPER_MODEL`, `WHISPER_NO_SPEECH_PROB`, `WHISPER_TEMPERATURE`, `WHISPER_TTFS_P99_S`, `SMART_TURN_STOP_SECS`/`_PRE_SPEECH_MS`/`_MAX_DURATION_SECS` | 2 |
| `scripts/check_local_only.py` | G3(e), two modes, shared `cfg()` resolver (L12) | 6 |
| `scripts/tts_ab.py` | Blind ElevenLabs-vs-Kokoro A/B for Larry (L13) | 5 |
| `scripts/launchd_exec.sh` | The one launchd wrapper: sources the vault-key file, exports `PATH`/`HOME`/`TMPDIR`, `exec`s a module (L10, L11) | 9 |
| `deploy/launchd/com.mortimer.llm.plist` | Ollama **LaunchDaemon**, `OLLAMA_CONTEXT_LENGTH=16384`, no secrets | 9 |
| `deploy/launchd/com.mortimer.admin.plist` | Sidecar **LaunchDaemon**, `UserName`, no secrets | 9 |
| `deploy/launchd/com.mortimer.bot.plist` | Bot **LaunchDaemon**, `UserName`, no secrets | 9 |
| `deploy/newsyslog.d/mortimer.conf` | Log rotation for the three service logs (F22) | 9 |
| `docs/runbooks/MAC_MINI_RELOCATION.md` | The T3.1 runbook, executed by Larry on the mini | 9 |
| `tests/unit/test_providers.py` | factory tests incl. `build_turn_start_strategies` (§7) | 2, 3, 4, 5 |
| `tests/unit/test_check_local_only.py` | tests over the G3(e) rules + `cfg()` (§7) | 6 |
| `tests/unit/test_turn_ordering.py` | the F3 turn-controller ordering test (§7) | 4, 7 |
| `tests/integration/test_local_voice_live.py` | `RUN_LIVE`-gated: Whisper transcribes a fixture wav; Ollama answers a tool call (§7) | 3, 7 |

### Modify (15)

| Path | Exact change | Anchor(s) | §5 step |
|---|---|---|---|
| `jarvis/config.py` | Add `jarvis_stt_provider`, `jarvis_turn_detector`, `jarvis_tts_provider`, `jarvis_smart_turn_model_path`, `jarvis_whisper_vad_barge_in` + validators; make the three cloud keys `str \| None = None`; replace the `REQUIRED_ENV_VARS` constant with `required_env_vars(stt, tts)`; move the missing-key check into `load_settings()` after construction | `REQUIRED_ENV_VARS = (`, `openai_api_key:`, `def load_settings` | 1 |
| `jarvis/bot/pipeline.py` | `stt = build_stt(settings, STT_KEYTERMS)`; `tts = build_tts(settings, default_voice)`; the aggregator gets `start=build_turn_start_strategies(settings, speaker_gate_state)` **and** `stop=build_turn_stop_strategies(settings)`; the voice/set handler uses `tts_voice_id(voice, runtime.settings)`; one startup log line | `stt = DeepgramFluxSTTService(`, `tts = ElevenLabsTTSService(` (or the `ElevenLabsTTSSettings` block), `LLMContextAggregatorPair(`, `settings={"voice": voice["elevenlabs_voice_id"]}` | 3, 4, 5 |
| `jarvis/bot/voice_switch.py` | `tts_voice_id(voice, settings)`; `build_set_voice_tool` gains a defaulted `settings` parameter | `def build_set_voice_tool`, `voice["elevenlabs_voice_id"]` | 5 |
| `jarvis/bot/speaker_gate.py` | **F10:** `SpeakerTap` resets its buffer/`turn_id` on `VADUserStartedSpeakingFrame` and final-scores on `VADUserStoppedSpeakingFrame` (the reliable speech-onset/-offset markers under both providers); import both from `pipecat.frames.frames` | `if isinstance(frame, UserStartedSpeakingFrame):` (inside `class SpeakerTap`), `elif isinstance(frame, UserStoppedSpeakingFrame):` | 4 |
| `jarvis/bot/transcript_log.py` | **F4:** add a `vad_stop->first_audio` instrument — record `time.perf_counter()` on `VADUserStoppedSpeakingFrame` and print `TURN vad_stop->first_audio = <ms>ms` on the first `OutputAudioRawFrame` of the turn, alongside the existing line; import `VADUserStoppedSpeakingFrame` | `if isinstance(frame, UserStoppedSpeakingFrame):`, `TURN user_end->first_audio` | 7 |
| `scripts/check_env.py` | **F7 (stdlib-only):** `REQUIRED_VARS` becomes an **inlined** provider rule (do **not** import `jarvis.config`); reads `JARVIS_STT_PROVIDER`/`JARVIS_TTS_PROVIDER` via the merged `load_env()` view; the Deepgram probe is skipped with an explanatory line when the provider is `whisper_mlx`. Correction-3 base-URL edit **removed** (F8). | `REQUIRED_VARS =`, `def load_env`, the Deepgram-probe block | 6 |
| `scripts/latency_probe.py` | **F4:** add a second regex for `TURN vad_stop->first_audio = (\d+)ms`, selectable via a `--metric {user_end,vad_stop}` flag (default `user_end`, unchanged); the G3(b) procedure uses `--metric vad_stop` | `user_end->first_audio` regex line | 7 |
| `requirements.txt` | **F1:** add `whisper` to the pipecat extras bracket (pulls `faster-whisper~=1.2.1`, importable on Linux CI); add the two platform-gated lines at pipecat's real pins: `mlx-whisper~=0.4.2 ; sys_platform == "darwin" and platform_machine == "arm64"` and `kokoro-onnx>=0.5.0,<1 ; sys_platform == "darwin" and platform_machine == "arm64"` (`requests` is already a dep) | `pipecat-ai[` | 8 |
| `requirements-lock.txt` | **F1:** add `faster-whisper==1.2.1` as a top-level pin so CI installs it and test #4's `importorskip` guard actually runs there | `pipecat-ai==1.4.0` | 8 |
| `.env.example` | **CP-F10:** append a commented LOCAL block with `JARVIS_STT_PROVIDER`, `JARVIS_TURN_DETECTOR`, `JARVIS_TTS_PROVIDER`, `JARVIS_SMART_TURN_MODEL_PATH`, `JARVIS_WHISPER_VAD_BARGE_IN`, each with its default. **Create the file if a sibling wave has not** (three plans append distinct commented blocks, per CROSS_PLAN §C F10) | end of file | 10 |
| `README.md` | Env-var table gains the K7 vars + `JARVIS_WHISPER_VAD_BARGE_IN`, their enums and defaults; troubleshooting gains "bot starts but never transcribes → check `JARVIS_STT_PROVIDER`" | env-var table heading | 10 |
| `DEVIATIONS.md` | New `### D-013 — 2026-08-27` recording that swapping the STT **bypasses** the live smart-turn analyzer under the default config (Correction 1 + F3), not merely that smart-turn was already on | end of file | 10 |
| `tests/unit/test_interruption.py` | The two draft `TestWhisperTiming` tautologies are **removed** (F13); the real ordering test lives in `test_turn_ordering.py`. `TranscriptionFrame` import no longer needed here. | `class TestGenuineInterruption` (leave existing 8 untouched) | 7 |
| `tests/unit/test_config.py` | Append 4 tests for provider-derived required keys (§7); the two existing missing-key tests are untouched. | `def test_` (append) | 1 |
| `docs/plans/MORTIMER_PLATFORM_ROADMAP.md` | §2.3 T3.2/T3.3 and §4 G3(e) annotated with a pointer to this plan's Corrections 1/2/4 and L15. **Text only.** | — (SEC owns roadmap edits; note only) | 10 |

### Delete (0)

Nothing. `DeepgramFluxSTTService` stays the default and the rollback (§9).

### Larry's own commit (1) — via `ALLOWLIST_SEQUENCE.md`

The self-edit deny-list change LOCAL needs is **`deny += "docs/runbooks/**"`** (W2
row). Per `CROSS_PLAN_RESOLUTION.md` §A, the reconciled JSON and the four-row
ordered table live in the SEC-owned `docs/plans/ALLOWLIST_SEQUENCE.md`; **this plan
does not create or edit that file or `config/self_edit_allowlist.json`**. The
Larry step (§5 Step 12, §8) is: *apply the LOCAL row of
`docs/plans/ALLOWLIST_SEQUENCE.md` and run its verification command.*

*Why this entry.* `docs/runbooks/MAC_MINI_RELOCATION.md` carries the vault-key
handling procedure (L11); `docs/**` is otherwise self-editable, so a self-edit could
rewrite the runbook and mislead Larry into mishandling the key. Disjoint from SEC's
and REMOTE's entries (verified in `ALLOWLIST_SEQUENCE.md`).

### Explicitly NOT touched

`jarvis/bot/interruption.py` (§5 Step 7 explains why the re-tune changes no code
there), `jarvis/bot/progress_watcher.py`, `jarvis/vault.py`, `jarvis/keyhealth.py`,
`config/agents.yaml`, `config/upgrade_models.yaml`, `config/voices.yaml`,
`scripts/mortimer.sh`, `scripts/run_*.sh`, `tests/evals/routing_eval.py`,
`tests/evals/cases.yaml`, and every `web/` file. (`jarvis/bot/speaker_gate.py` and
`jarvis/bot/transcript_log.py` were moved **out** of this list into Modify by the
F10/F4 fixes.)

---

## §5 Implementation steps, in order

### Step 1 — `jarvis/config.py`: the three K7 fields, and provider-derived required keys

**File:** `jarvis/config.py`.

Replace line 28 with:

```python
STT_PROVIDERS = ("deepgram", "whisper_mlx")
TURN_DETECTORS = ("stt", "smart_turn_v3", "smart_turn_coreml")
TTS_PROVIDERS = ("elevenlabs", "kokoro")


def required_env_vars(
    stt_provider: str = "deepgram", tts_provider: str = "elevenlabs"
) -> tuple[str, ...]:
    """Which credentials this configuration actually needs (K7 / T3 L5).

    Before T3 this was a fixed tuple, which made roadmap gate G3(e) — "no
    cloud STT/LLM key present" — literally unsatisfiable: removing
    DEEPGRAM_API_KEY stopped the bot from starting even when
    JARVIS_STT_PROVIDER=whisper_mlx meant Deepgram was never called.
    OPENAI_API_KEY stays unconditional: OpenAILLMService hands it to the
    OpenAI SDK client, which rejects None. A local server ignores the
    value; the convention is the literal sentinel "local", which
    scripts/check_local_only.py knows.
    """
    names = ["OPENAI_API_KEY"]
    if stt_provider == "deepgram":
        names.append("DEEPGRAM_API_KEY")
    if tts_provider == "elevenlabs":
        names.append("ELEVENLABS_API_KEY")
    return tuple(names)


# Kept for import-compatibility; no in-repo consumer reads it after Step 1
# (F17: scripts/check_env.py is stdlib-only and inlines its own rule — it
# does NOT import this or required_env_vars). load_settings() below calls
# required_env_vars() directly.
REQUIRED_ENV_VARS = required_env_vars()
```

Replace lines 52–58 with:

```python
    # LLM (OpenAI-compatible)
    # All three are Optional at the type level and enforced in
    # load_settings() against required_env_vars(), because which of them
    # is required depends on the K7 provider switches below.
    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4.1-mini"

    # Speech
    deepgram_api_key: str | None = None
    elevenlabs_api_key: str | None = None
```

Add, immediately after the `jarvis_units` block (after `jarvis/config.py:94`):

```python
    # K7 — local voice service switches (MORTIMER_LOCAL_VOICE_AND_MINI_PLAN.md
    # L1). Read in exactly ONE place: jarvis/bot/providers.py. These fields
    # exist here for discoverability and validation, the same arrangement
    # jarvis_ui_control_enabled and jarvis_council_enabled use.
    #
    # jarvis_turn_detector="stt" is a HISTORICAL NAME and does not mean the
    # STT decides the turn. It means "pass no stop= to UserTurnStrategies",
    # which makes pipecat supply its own default —
    # TurnAnalyzerUserTurnStopStrategy(LocalSmartTurnAnalyzerV3()) — which is
    # exactly what has been running since 2026-08-06 (DEVIATIONS.md D-010).
    # The other two values pass an explicit stop= so jarvis owns
    # SmartTurnParams instead of inheriting pipecat's.
    jarvis_stt_provider: str = "deepgram"      # deepgram | whisper_mlx
    jarvis_turn_detector: str = "stt"          # stt | smart_turn_v3 | smart_turn_coreml
    jarvis_tts_provider: str = "elevenlabs"    # elevenlabs | kokoro
    # Only read when jarvis_turn_detector == "smart_turn_coreml"; the CoreML
    # analyzer has no default path and raises without one
    # (pipecat/audio/turn/smart_turn/local_coreml_smart_turn.py:61-63).
    jarvis_smart_turn_model_path: str | None = None
    # L15 — under whisper_mlx only: prepend VADUserTurnStartStrategy so barge-in
    # fires at speech onset and the smart-turn analyzer decides end-of-turn
    # again. Default False keeps the speaker-verified interruption gate (no
    # unverified TV interruptions). See L15 for the trade; a plain bool, no
    # validator (pydantic parses true/false/1/0). Ignored under deepgram.
    jarvis_whisper_vad_barge_in: bool = False
```

Add three validators beside `_units_must_be_known` (`jarvis/config.py:172`),
all the same shape — an unknown value is rejected outright, never degraded:

```python
    @field_validator("jarvis_stt_provider")
    @classmethod
    def _stt_provider_must_be_known(cls, v: str) -> str:
        if v not in STT_PROVIDERS:
            raise ValueError(
                f"JARVIS_STT_PROVIDER must be one of {STT_PROVIDERS}, got {v!r}")
        return v

    @field_validator("jarvis_turn_detector")
    @classmethod
    def _turn_detector_must_be_known(cls, v: str) -> str:
        if v not in TURN_DETECTORS:
            raise ValueError(
                f"JARVIS_TURN_DETECTOR must be one of {TURN_DETECTORS}, got {v!r}")
        return v

    @field_validator("jarvis_tts_provider")
    @classmethod
    def _tts_provider_must_be_known(cls, v: str) -> str:
        if v not in TTS_PROVIDERS:
            raise ValueError(
                f"JARVIS_TTS_PROVIDER must be one of {TTS_PROVIDERS}, got {v!r}")
        return v
```

Replace the body of `load_settings()` from `jarvis/config.py:209` down to the
`raise RuntimeError(...)` at `:219` with:

```python
    kwargs: dict = {"_env_file": None} if env_file is None else {"_env_file": env_file}
    try:
        settings = Settings(**kwargs)
    except Exception as exc:
        raise RuntimeError(f"Configuration error. Details: {exc}") from exc

    # T3 L5 — which keys are required depends on the K7 provider switches,
    # so the check happens AFTER construction, not through pydantic's
    # required-field mechanism. Message shape preserved: tests/unit/
    # test_config.py:33-44 match on "Missing required environment
    # variables" and on the key names.
    required = required_env_vars(
        settings.jarvis_stt_provider, settings.jarvis_tts_provider)
    missing = [
        name for name in required if not getattr(settings, name.lower(), None)
    ]
    if missing:
        raise RuntimeError(
            "Configuration error. Missing required environment variables: "
            f"{', '.join(missing)}."
        )
```

**Test that proves it:** `tests/unit/test_config.py` keeps passing unchanged
(the two missing-key tests at `:33` and `:38` still raise and still list the
names), plus the four new cases in §7 (`test_providers.py::TestSettingsSwitches`).

### Step 2 — `jarvis/bot/providers.py`, complete

**File:** `jarvis/bot/providers.py` (new). This is the only module that reads a
K7 switch.

```python
"""Provider selection for the voice loop (K7 / MORTIMER_LOCAL_VOICE_AND_MINI_PLAN.md L2).

THE ONE PLACE the K7 switches are read. jarvis/config.py declares and
validates them; jarvis/bot/pipeline.py calls the factories below and
never branches on a provider name itself.

Every import of a local-only engine is LAZY and inside its own branch:
faster-whisper (module-scope requirement of pipecat's whisper module),
mlx-whisper and kokoro-onnx are installed on the mini and (faster-whisper
only) on CI; a stock Linux CI checkout with the default deepgram provider
must still import jarvis.bot.pipeline without touching any of them.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# --- tuning knobs, one place each (see the plan's §6) --------------------

# Whisper: the roadmap's stated model. NOT passing this ships MLXModel.TINY,
# which is the service's own default (pipecat/services/whisper/stt.py:441).
WHISPER_MODEL = "mlx-community/whisper-large-v3-turbo"
# Segments with no_speech_prob BELOW this are kept
# (pipecat/services/whisper/stt.py:365-370) — lower is more
# silence-suspicious. Raising it keeps MORE audio, not less.
WHISPER_NO_SPEECH_PROB = 0.6
WHISPER_TEMPERATURE = 0.0
# F20 — the P99 speech-end→final-transcript latency the turn-stop timeout
# uses as max(0, ttfs - stop_secs). Equals pipecat's WHISPER_TTFS_P99 (1.0);
# named here so §6 owns it and so build_stt can pass it explicitly instead
# of triggering pipecat's "ttfs_p99_latency not set" warning + 1.0 fallback.
WHISPER_TTFS_P99_S = 1.0

# SmartTurnParams.stop_secs when jarvis owns the analyzer explicitly.
# pipecat's own default is 3.0 (base_smart_turn.py:28). This value is the
# analyzer's INTERNAL silence threshold and is deliberately left at
# pipecat's default: the tuning lever for end-of-turn latency is the VAD
# window in pipeline.py (DEVIATIONS.md D-010), and moving both at once
# makes the G3(b) measurement uninterpretable.
SMART_TURN_STOP_SECS = 3.0
SMART_TURN_PRE_SPEECH_MS = 500.0
SMART_TURN_MAX_DURATION_SECS = 8.0

# Kokoro is a measurement path (roadmap R7, default off), so it has one
# fixed voice rather than a second id column in config/voices.yaml.
KOKORO_DEFAULT_VOICE = "af_heart"


def build_stt(settings: Any, keyterms: list[str]):
    """Return the STT service for settings.jarvis_stt_provider.

    `keyterms` is jarvis/bot/pipeline.py:324's STT_KEYTERMS, passed in
    rather than imported: it is defined IN pipeline.py, and importing it
    from here would make providers.py import pipeline.py, which imports
    providers.py. Whisper ignores it (the MLX service has no keyterm
    concept); it is accepted unconditionally so the signature does not
    change with the provider.
    """
    provider = settings.jarvis_stt_provider
    if provider == "whisper_mlx":
        # Imports the module — which hard-requires faster_whisper at module
        # scope on EVERY platform (mlx_whisper only on Darwin/arm64). CI has
        # faster-whisper via the `whisper` extra; the mini has all three
        # (§5 Step 9.1). No assert here (F19): `python -O` strips asserts and
        # a bare AssertionError under launchd KeepAlive loops forever — the
        # WHISPER_MODEL/enum equality is guarded by test #4 instead.
        from pipecat.services.stt_latency import WHISPER_TTFS_P99
        from pipecat.services.whisper.stt import WhisperSTTServiceMLX
        from pipecat.transcriptions.language import Language

        logger.info("stt_provider provider=whisper_mlx model=%s", WHISPER_MODEL)
        return WhisperSTTServiceMLX(
            # F20: WhisperSTTServiceMLX does not set ttfs_p99_latency, so
            # pipecat warns and falls back to 1.0. Set it explicitly (the
            # value IS 1.0 — pipecat's WHISPER_TTFS_P99 — but naming it kills
            # the warning and pins the number the turn-stop timeout uses:
            # max(0, ttfs - stop_secs), which L8's floor depends on).
            ttfs_p99_latency=WHISPER_TTFS_P99,   # == WHISPER_TTFS_P99_S (§6)
            settings=WhisperSTTServiceMLX.Settings(
                model=WHISPER_MODEL,
                language=Language.EN,
                no_speech_prob=WHISPER_NO_SPEECH_PROB,
                temperature=WHISPER_TEMPERATURE,
            ),
        )

    # provider == "deepgram" — unchanged from jarvis/bot/pipeline.py:480-500.
    from pipecat.services.deepgram.flux.base import DeepgramFluxSTTSettings
    from pipecat.services.deepgram.flux.stt import DeepgramFluxSTTService

    logger.info("stt_provider provider=deepgram model=flux-general-en")
    return DeepgramFluxSTTService(
        api_key=settings.deepgram_api_key,
        settings=DeepgramFluxSTTSettings(
            model="flux-general-en", keyterm=keyterms,
        ),
        # was True (plan Phase 5, D-004) until 2026-08-22 — see the full
        # rationale at the original construction site's comment history.
        # False hands interruption duty to the speaker-verified turn-start
        # strategy, the one gated path.
        should_interrupt=False,
    )


def build_turn_start_strategies(settings: Any, speaker_gate_state: Any):
    """Return the `start=` list for UserTurnStrategies (L15).

    The base strategy is exactly what jarvis builds today: speaker-verified
    min-words when a profile is enrolled, plain min-words otherwise. This is
    imported from jarvis.bot.speaker_gate (not pipeline.py — that would be a
    cycle); pass speaker_gate_state through from build_pipeline.

    Under whisper_mlx with jarvis_whisper_vad_barge_in=True (L15 Config
    W-onset), prepend pipecat's VADUserTurnStartStrategy so the turn starts at
    VAD onset: this restores onset barge-in AND stops the late transcript from
    resetting the smart-turn analyzer (F2/F3). Residual: onset turn-start
    broadcasts an UNVERIFIED interruption — Larry gates this on the P5 TV-soak
    (L15). Default (W-safe) returns just [base]: today's behaviour, no
    reopened TV defect, degraded barge-in recorded honestly.
    """
    from jarvis.bot.speaker_gate import (
        SpeakerVerifiedMinWordsTurnStartStrategy,
    )
    from pipecat.turns.user_start import MinWordsUserTurnStartStrategy

    if speaker_gate_state is not None:
        base = SpeakerVerifiedMinWordsTurnStartStrategy(
            speaker_gate_state, min_words=2)
    else:
        base = MinWordsUserTurnStartStrategy(min_words=2)

    if (settings.jarvis_stt_provider == "whisper_mlx"
            and settings.jarvis_whisper_vad_barge_in):
        from pipecat.turns.user_start import VADUserTurnStartStrategy

        logger.info(
            "turn_start config=W-onset (VAD onset barge-in; interruptions "
            "UNVERIFIED — see L15)")
        return [VADUserTurnStartStrategy(), base]

    logger.info("turn_start config=W-safe (speaker-verified; barge-in at "
                "segment transcript)")
    return [base]


def build_turn_stop_strategies(settings: Any):
    """Return the `stop=` list for UserTurnStrategies, or None.

    None means "let pipecat fill in its default", which is
    [TurnAnalyzerUserTurnStopStrategy(LocalSmartTurnAnalyzerV3())]
    (pipecat/turns/user_turn_strategies.py:42-51,74-79). That default has
    been the live turn-close decision-maker since 2026-08-06
    (DEVIATIONS.md D-010), so returning None for the "stt" value is
    byte-for-byte today's behaviour.
    """
    detector = settings.jarvis_turn_detector
    if detector == "stt":
        return None

    from pipecat.audio.turn.smart_turn.base_smart_turn import SmartTurnParams
    from pipecat.turns.user_stop import TurnAnalyzerUserTurnStopStrategy

    params = SmartTurnParams(
        stop_secs=SMART_TURN_STOP_SECS,
        pre_speech_ms=SMART_TURN_PRE_SPEECH_MS,
        max_duration_secs=SMART_TURN_MAX_DURATION_SECS,
    )
    if detector == "smart_turn_coreml":
        from pipecat.audio.turn.smart_turn.local_coreml_smart_turn import (
            LocalCoreMLSmartTurnAnalyzer,
        )

        path = settings.jarvis_smart_turn_model_path
        if not path:
            raise RuntimeError(
                "JARVIS_TURN_DETECTOR=smart_turn_coreml requires "
                "JARVIS_SMART_TURN_MODEL_PATH pointing at the directory that "
                "contains coreml/smart_turn_classifier.mlpackage"
            )
        analyzer = LocalCoreMLSmartTurnAnalyzer(
            smart_turn_model_path=path, params=params)
    else:  # "smart_turn_v3"
        from pipecat.audio.turn.smart_turn.local_smart_turn_v3 import (
            LocalSmartTurnAnalyzerV3,
        )

        analyzer = LocalSmartTurnAnalyzerV3(params=params)

    logger.info(
        "turn_detector detector=%s analyzer=%s stop_secs=%.2f",
        detector, type(analyzer).__name__, SMART_TURN_STOP_SECS)
    return [TurnAnalyzerUserTurnStopStrategy(turn_analyzer=analyzer)]


def effective_turn_analyzer_name(settings: Any) -> str:
    """What is ACTUALLY deciding end-of-turn, for the startup log line.

    Exists so nobody has to re-derive Correction 1 by reading pipecat's
    source again: with the default switch value the answer is still
    LocalSmartTurnAnalyzerV3, supplied implicitly.
    """
    detector = settings.jarvis_turn_detector
    if detector == "stt":
        return "LocalSmartTurnAnalyzerV3 (pipecat default, implicit)"
    if detector == "smart_turn_coreml":
        return "LocalCoreMLSmartTurnAnalyzer (explicit)"
    return "LocalSmartTurnAnalyzerV3 (explicit)"


def tts_voice_id(voice_row: dict, settings: Any) -> str:
    """The provider-specific voice id for a config/voices.yaml row.

    Three call sites read a voice id (pipeline.py's TTS construction,
    pipeline.py's voice/set app-message handler, voice_switch.py's
    set_voice tool). All three go through here so a Kokoro build cannot
    change two of them and forget the third.
    """
    if settings.jarvis_tts_provider == "kokoro":
        # Kokoro is a measurement path with one fixed voice (plan L13):
        # set_voice becomes a no-op, and the voice/current app-message
        # still round-trips so the UI reconciles.
        return KOKORO_DEFAULT_VOICE
    return voice_row["elevenlabs_voice_id"]


def build_tts(settings: Any, voice_row: dict):
    """Return the TTS service for settings.jarvis_tts_provider."""
    voice = tts_voice_id(voice_row, settings)
    if settings.jarvis_tts_provider == "kokoro":
        from pipecat.services.kokoro.tts import KokoroTTSService

        logger.info("tts_provider provider=kokoro voice=%s", voice)
        # NOTE: first synthesis downloads the ONNX model and voices file
        # (pipecat/services/kokoro/tts.py:39-62). The relocation runbook
        # pre-fetches them; do not discover this mid-turn.
        return KokoroTTSService(settings=KokoroTTSService.Settings(voice=voice))

    from pipecat.services.elevenlabs.tts import (
        ElevenLabsTTSService,
        ElevenLabsTTSSettings,
    )

    logger.info("tts_provider provider=elevenlabs voice=%s", voice)
    return ElevenLabsTTSService(
        api_key=settings.elevenlabs_api_key,
        settings=ElevenLabsTTSSettings(
            voice=voice,
            model="eleven_flash_v2_5",
            stability=0.5,
            similarity_boost=0.75,
        ),
    )
```

**Two facts already verified, so nothing here is left to check:**

1. `STT_KEYTERMS` is defined at `jarvis/bot/pipeline.py:324` — **in
   `pipeline.py` itself**, and used at `:483`. That is why `build_stt` takes it
   as a parameter (above) instead of importing it: `providers.py` importing
   `pipeline.py` would be a cycle. Do not move `STT_KEYTERMS`.
2. The ElevenLabs import path above is copied verbatim from
   `jarvis/bot/pipeline.py:104-107`
   (`from pipecat.services.elevenlabs.tts import ElevenLabsTTSService,
   ElevenLabsTTSSettings`).

**Test that proves it:** `tests/unit/test_providers.py` (§7), which constructs a
stub settings object and asserts the returned types and the `None` for `"stt"`,
with no Pipecat service actually instantiated for the Apple-only branches
(they are asserted via `pytest.importorskip` / `monkeypatch`, per §7).

### Step 3 — wire the STT factory into the pipeline

**File:** `jarvis/bot/pipeline.py`.

Delete lines 480–500 (the whole `stt = DeepgramFluxSTTService(...)` block,
comments included — the comments move into `providers.build_stt`) and put in
their place:

```python
    stt = build_stt(settings, STT_KEYTERMS)
```

`STT_KEYTERMS` stays exactly where it is, at `jarvis/bot/pipeline.py:324`.

Add to the imports (beside the other `jarvis.bot` imports around `:59`):

```python
from jarvis.bot.providers import (
    build_stt,
    build_tts,
    build_turn_stop_strategies,
    effective_turn_analyzer_name,
    tts_voice_id,
)
```

Remove the now-unused `DeepgramFluxSTTSettings` / `DeepgramFluxSTTService`
imports at `jarvis/bot/pipeline.py:102-103` (they live in `providers.py` now).

**Test that proves it:** `tests/integration/test_bot_wiring.py` must still pass
unchanged (it constructs the pipeline with `deepgram_api_key="dg"` at
`:87,484`), plus `tests/unit/test_providers.py::test_default_settings_build_deepgram`.

### Step 4 — attach the turn analyzer at the real attachment point

**File:** `jarvis/bot/pipeline.py:631-638`.

The attachment point is **`UserTurnStrategies(stop=...)` on the user aggregator**,
not `TransportParams` (D-004, `jarvis/bot/bot.py:6-11`) and not `PipelineTask`
(the 0.0.108-era path that died on import, `jarvis/bot/pipeline.py:612-616`).

Locate the `LLMContextAggregatorPair(` construction (anchor `LLMContextAggregatorPair(`).
The inline `turn_start_strategy` construction that precedes it (the
`if speaker_gate_state is not None:` block choosing `SpeakerVerifiedMinWordsTurnStartStrategy`
vs `MinWordsUserTurnStartStrategy`) **moves into `providers.build_turn_start_strategies`**
(Step 2) and is deleted here. Replace the block with:

```python
    # start: L15 — build_turn_start_strategies owns the speaker-verified /
    #   min-words choice AND the whisper_mlx VAD-onset opt-in. Passing
    #   speaker_gate_state (already built above) keeps the Tier-1b behaviour
    #   for deepgram and W-safe whisper byte-for-byte.
    # stop: NEW ONLY IN BEING EXPLICIT for JARVIS_TURN_DETECTOR=stt — with
    #   stop=None, UserTurnStrategies.__post_init__ supplies
    #   [TurnAnalyzerUserTurnStopStrategy(LocalSmartTurnAnalyzerV3())]
    #   (installed Pipecat user_turn_strategies.py). build_turn_stop_strategies
    #   returns None for "stt" precisely so that default keeps applying.
    #   NOTE (F3/L15): under whisper_mlx W-safe, this analyzer runs but is
    #   BYPASSED — the late transcript resets it. It decides again only under
    #   W-onset (jarvis_whisper_vad_barge_in=True).
    aggregators = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            user_turn_strategies=UserTurnStrategies(
                start=build_turn_start_strategies(settings, speaker_gate_state),
                stop=build_turn_stop_strategies(settings),
            ),
        ),
    )
```

Then add, immediately after the `aggregators` assignment, the single startup log
line that makes the whole provider configuration legible in `logs/bot.log`:

```python
    _logger.info(
        "voice_providers stt=%s turn_detector=%s analyzer=%s tts=%s "
        "llm_base_url=%s llm_model=%s",
        settings.jarvis_stt_provider,
        settings.jarvis_turn_detector,
        effective_turn_analyzer_name(settings),
        settings.jarvis_tts_provider,
        settings.openai_base_url,
        settings.openai_model,
    )
```

**Why `stop=None` is legal.** `UserTurnStrategies` is a dataclass with
`stop: list[BaseUserTurnStopStrategy] | None = None`
(`pipecat/turns/user_turn_strategies.py:71-72`) and `__post_init__` tests
`if not self.stop:` (`:78`). Passing `None` explicitly is identical to omitting
it.

**Test that proves it:** `tests/unit/test_providers.py::TestTurnStop` and
`::TestTurnStart` (§7) — `"stt"` stop returns `None`; `"smart_turn_v3"` returns a
one-element list whose element is a `TurnAnalyzerUserTurnStopStrategy`;
`"smart_turn_coreml"` without a path raises `RuntimeError`; start returns `[base]`
for deepgram and W-safe whisper, and `[VADUserTurnStartStrategy, base]` for
whisper + `jarvis_whisper_vad_barge_in=True`.

### Step 4b — `SpeakerTap` scoring window keyed on the VAD frames (F10)

**File:** `jarvis/bot/speaker_gate.py`. Locate `SpeakerTap.process_frame` (anchor
`if isinstance(frame, UserStartedSpeakingFrame):` inside `class SpeakerTap`).

`SpeakerTap` today resets its buffer/`turn_id` on `UserStartedSpeakingFrame` and
final-scores on `UserStoppedSpeakingFrame`. Under Whisper those aggregator-sourced
frames arrive *late* (turn-start is transcript-driven), so the buffer resets during
the silence *before* the next utterance: the mid-turn embedding is silence and the
final embedding is an empty buffer, inverting the gate. The `VADUserStarted/StoppedSpeakingFrame`
pair fires at true speech onset/offset under **both** providers, so re-key on them:

```python
from pipecat.frames.frames import (   # add to the existing frames import
    VADUserStartedSpeakingFrame,
    VADUserStoppedSpeakingFrame,
)
...
        # Reset on the VAD onset marker (reliable under Flux AND Whisper).
        # Keep listening for UserStartedSpeakingFrame too, but guard the
        # increment so a turn that fires both frames does not double-count.
        if isinstance(frame, (VADUserStartedSpeakingFrame, UserStartedSpeakingFrame)):
            if len(self._buffer) > 0 or self._verified_this_turn:
                self._state.turn_id += 1
                self._buffer = bytearray()
                self._verified_this_turn = False
        elif isinstance(frame, InputAudioRawFrame):
            ...unchanged...
        elif isinstance(frame, (VADUserStoppedSpeakingFrame, UserStoppedSpeakingFrame)):
            self._schedule_score(final=True)
```

The guard (`len(self._buffer) > 0 or self._verified_this_turn`) makes the second
of the two start frames within one turn a no-op, so `turn_id` still increments once
per turn under Flux (where both fire) and once under Whisper (where only the VAD
one fires at onset). Two unit tests in §7 drive both frame orders.

**Why this is safe for `TranscriptGate`.** `TranscriptGate` keys its score lookup on
`self._state.turn_id` at the moment a `TranscriptionFrame` arrives; as long as
`turn_id` increments once per real utterance and the score is computed over that
utterance's audio, the lookup is correct. Under Whisper the VAD onset now drives
both, so the score and the transcript share a `turn_id`.

### Step 5 — TTS factory, the three voice-id sites, and the A/B script

**5a. `jarvis/bot/pipeline.py:543-551`** → `tts = build_tts(settings, default_voice)`.

**5b.** In the `voice/set` app-message handler (anchor
`settings={"voice": voice["elevenlabs_voice_id"]}`) → replace with
`settings={"voice": tts_voice_id(voice, runtime.settings)}`.
(F18 correction: this site is inside `run_session`, not `build_pipeline`;
`run_session` binds both `settings` and `runtime = Runtime(settings=settings, …)`.
Use `runtime.settings`. "Same module" does **not** put `build_pipeline`'s local in
scope — the earlier draft's reason was wrong even though the name happened to work.)

**5c. `jarvis/bot/voice_switch.py`** — `build_set_voice_tool` gains a third
parameter and uses it:

```python
def build_set_voice_tool(
    push_frame: Callable[[Any], Awaitable[None]],
    catalog: dict | None = None,
    settings: Any | None = None,
) -> tuple[dict, Callable[[dict], Any]]:
```

and at `:88-89`:

```python
        from jarvis.bot.providers import tts_voice_id
        await push_frame(TTSUpdateSettingsFrame(
            settings={"voice": tts_voice_id(voice, settings)}))
```

with `tts_voice_id` tolerating `settings=None` by treating it as ElevenLabs —
add to `providers.tts_voice_id`:

```python
    if settings is not None and settings.jarvis_tts_provider == "kokoro":
```

Update the call site at `jarvis/bot/pipeline.py:352` to
`build_set_voice_tool(pusher.push, catalog, settings)`.

*Why `settings=None` is tolerated rather than required.* `build_set_voice_tool`
is called from at least one place with two arguments today and is imported by
tests; a defaulted third parameter changes no existing caller and cannot
silently select the wrong provider (the default is the default provider).

**5d. `scripts/tts_ab.py`** (new) — the blind A/B R7's revisit condition names.

```
usage: python scripts/tts_ab.py --out audio/tts_ab [--sentences path]

Behaviour, fixed:
1. Sentences: 8 by default, taken from an embedded list in the script
   (2 short confirmations, 2 numeric/time-bearing, 2 multi-clause
   explanations, 2 with proper nouns — the four shapes Mortimer actually
   speaks). --sentences FILE overrides with one sentence per line.
2. For each sentence, synthesize once through ElevenLabs
   (build_tts on a Settings with jarvis_tts_provider="elevenlabs") and once
   through Kokoro. 16 files.
3. Write them as a1.wav … a16.wav in a RANDOM order (random.shuffle on the
   (provider, index) pairs), and write key.json mapping filename ->
   {provider, sentence}.
4. Print: "Score every file 1-5 for naturalness WITHOUT opening key.json.
   Write your scores to scores.csv as filename,score. Then run
   python scripts/tts_ab.py --reveal --out <dir>."
5. --reveal reads key.json + scores.csv and prints the per-provider mean
   and the count of files each provider won head-to-head on the same
   sentence. It refuses to run if scores.csv is absent, and it never
   prints the mapping before scores.csv exists.
```

*Why the refusal in step 5.* R7 says *"a blind A/B Larry runs himself"*. A script
that can reveal the key before the scores exist is not blind; the refusal is the
blindness.

**Test that proves it:** `tests/unit/test_providers.py::TestTTS` covers
`tts_voice_id` for both providers and for `settings=None`. `scripts/tts_ab.py`
is Larry-run (§8 D3) and has no unit test — it produces audio, which the sandbox
cannot make.

### Step 6 — `scripts/check_local_only.py` (G3(e)) and the `check_env.py` corrections

**6a. `scripts/check_local_only.py`** (new), complete behaviour:

```python
"""G3(e): prove the voice loop has no cloud STT/LLM credential.

MORTIMER_LOCAL_VOICE_AND_MINI_PLAN.md L12. Exit 0 iff every applicable
rule passes. NEVER prints a secret value — only names, verdicts and hosts.

Default mode governs the VOICE LOOP's own credentials, which is what the
gate asks about. --strict additionally fails on the sub-agent model keys
in config/upgrade_models.yaml; nothing in T3 requires strict to pass, and
MORTIMER_SENSITIVE_TIER_PLAN.md will.
"""
```

Rules, executed in order, each printing one `PASS`/`FAIL`/`residual` line. Every
config read is through the shared `cfg()` resolver (L12: `os.environ` — which
`inject_env()` has populated — then repo `.env`), so the script gives the same
answer from an interactive shell on the mini as the launchd wrapper does (F9):

| # | Rule | Failure message |
|---|---|---|
| 1 | `cfg("JARVIS_STT_PROVIDER") == "whisper_mlx"` | `FAIL STT provider is '<v>'; G3(e) requires whisper_mlx` |
| 2 | `DEEPGRAM_API_KEY` absent from `os.environ` **and** from `set(vault.load_secrets())` | `FAIL DEEPGRAM_API_KEY present in <environment\|vault>` |
| 3 | `urlparse(cfg("OPENAI_BASE_URL")).hostname in {"127.0.0.1","::1","localhost"}` | `FAIL OPENAI_BASE_URL host is '<host>'; expected loopback` |
| 4 | `cfg("OPENAI_API_KEY") == "local"` (**not** "or absent" — F14) | `FAIL OPENAI_API_KEY must be the sentinel 'local' for a local server (absent means the bot cannot start — see jarvis/config.py required_env_vars)` |
| 5 | `ELEVENLABS_API_KEY` present → print `residual: ElevenLabs sees every spoken reply (roadmap R7)`. Absent → print `note: TTS credential absent; JARVIS_TTS_PROVIDER must be kokoro` and FAIL only if `cfg("JARVIS_TTS_PROVIDER") != "kokoro"` | `FAIL ELEVENLABS_API_KEY absent but JARVIS_TTS_PROVIDER is '<v>'; the voice loop has no TTS` |
| 6 | For each `api_key_env` in `config/upgrade_models.yaml` other than `OPENAI_API_KEY`: present → `residual: <NAME> present (sub-agent models are cloud-hosted; T3.3 scope is the Supervisor only)`. **FAIL only under `--strict`.** | `FAIL --strict: <NAME> present` |

The vault read is **names only**: `list(jarvis.vault.load_secrets().keys())`.
`load_secrets()` returns the decrypted dict (`jarvis/vault.py:223-230`), so the
script must take `.keys()` and must never bind the dict to a name it later
prints. If the vault is absent or disabled the name set is empty and rules 2 and
6 fall back to `os.environ` alone — state that in the output as
`vault: not present`.

**6b. `scripts/check_env.py`**, two edits — and a deletion (F7/F8/F9):

**F7 — this script is stdlib-only by contract** (its module docstring: *"Stdlib
only, so it works before any dependencies are installed"*). It is the fresh-clone
Exit-Gate-0 validator; importing `jarvis.config` (which imports `pydantic` at
module scope, anchor `from pydantic import field_validator`) turns it into
`ModuleNotFoundError: pydantic` on exactly the broken environment it exists to
diagnose. So **do not import `jarvis.config`.** Inline the provider rule instead,
and mark it a deliberate duplicate guarded by a test:

- Replace the `REQUIRED_VARS` constant (anchor `REQUIRED_VARS =`) with:
  ```python
  # Deliberate duplicate of jarvis.config.required_env_vars. This script is
  # stdlib-only by contract (see the module docstring) and must NOT import
  # pydantic/jarvis.config. tests/unit/test_config.py::
  # test_check_env_required_vars_match_config asserts the two agree.
  def _required_vars(stt: str, tts: str) -> list[str]:
      names = ["OPENAI_API_KEY"]
      if stt == "deepgram":
          names.append("DEEPGRAM_API_KEY")
      if tts == "elevenlabs":
          names.append("ELEVENLABS_API_KEY")
      return names

  # F9: read providers through the merged load_env() view (os.environ then
  # .env), NOT os.environ directly — JARVIS_STT_PROVIDER lives in .env.
  _env = load_env()
  REQUIRED_VARS = _required_vars(
      _env.get("JARVIS_STT_PROVIDER", "deepgram"),
      _env.get("JARVIS_TTS_PROVIDER", "elevenlabs"),
  )
  ```
  (`load_env()` is defined below `REQUIRED_VARS`'s current site; move the
  `REQUIRED_VARS` computation to after `load_env`'s definition, or hoist
  `load_env`. Both are stdlib-only.)

- Wrap the Deepgram probe (anchor the `DEEPGRAM_API_KEY` reachability check) so it
  is skipped for the local provider, reading the provider through the same merged
  view:
  ```python
  if load_env().get("JARVIS_STT_PROVIDER", "deepgram") == "whisper_mlx":
      report(True, "Deepgram reachable",
             "skipped (JARVIS_STT_PROVIDER=whisper_mlx — STT is local)")
  elif env.get("DEEPGRAM_API_KEY"):
      ...existing probe...
  ```

**F8 — the base-URL edit is DELETED.** The draft's Correction 3 (make the
`OPENAI_BASE_URL` read "environment first") was a no-op: `load_env()` is already
`dict(os.environ)` overlaid with `.env`, so `:243`/`:495` already read the
environment first. **Leave those two reads exactly as they are.** R-L9 (which
guarded the imaginary regression) is deleted from §10.

**Test that proves it:** `tests/unit/test_check_local_only.py` (§7) drives the rule
functions with a fake `(env, vault_names)` pair, and `tests/unit/test_config.py::
test_check_env_required_vars_match_config` imports both `check_env._required_vars`
and `jarvis.config.required_env_vars` (it may — it runs under pytest with deps
installed) and asserts they agree for all four provider combinations.

### Step 7 — the G3(b) instrument, and the re-tune as a deterministic procedure

**No code changes to `jarvis/bot/interruption.py`.** §1.7 proves why: the notifier
arms on `LLMFullResponseStartFrame` (anchor `LLMFullResponseStartFrame` in
`jarvis/bot/interruption.py`) and reads no STT frame, so the STT swap cannot move
it. The re-tune touches the **VAD stop window** (the `VADParams(stop_secs=…)`
literal in `jarvis/bot/pipeline.py`) and the **new instrument** (below).

**7a — the instrument (F4), in code.** The existing `TURN user_end->first_audio`
line starts its clock at `UserStoppedSpeakingFrame`, which under Whisper waits for
the transcript — so it cannot see the STT penalty or the `stop_secs` window. Add a
second line keyed on `VADUserStoppedSpeakingFrame`, which both providers emit from
the VAD at the same instant.

- In `jarvis/bot/transcript_log.py` (anchor
  `if isinstance(frame, UserStoppedSpeakingFrame):`), also capture
  `self._vad_stop = time.perf_counter()` on `VADUserStoppedSpeakingFrame`, and on
  the first `OutputAudioRawFrame` of the turn print
  `TURN vad_stop->first_audio = <ms>ms` alongside the existing line. Import
  `VADUserStoppedSpeakingFrame` from `pipecat.frames.frames`.
- In `scripts/latency_probe.py` (anchor the `user_end->first_audio` regex), add a
  second regex `TURN vad_stop->first_audio = (\d+)ms` and a `--metric {user_end,vad_stop}`
  flag (default `user_end`, so every existing caller is unchanged). The G3(b)
  procedure runs `--metric vad_stop`.

**7b — the turn-ordering test that actually proves F3** (`tests/unit/test_turn_ordering.py`,
new; runs on Linux). It replaces the two draft `TestWhisperTiming` tests, which
exercised frames `InterruptionNotifier` ignores (one duplicated
`test_mid_speech_interruption` byte-for-byte — F13). This test drives a real
`UserTurnController` and asserts the observable F3 consequence:

```python
async def test_whisper_ordering_bypasses_analyzer_under_wsafe():
    """Under a SegmentedSTTService the only transcript arrives AFTER VAD stop,
    so the transcript-driven start strategy fires the turn and RESETS the stop
    strategies before the same frame reaches them (installed Pipecat
    user_turn_controller.py, `# Reset all user turn stop strategies`). The
    turn-analyzer's INCOMPLETE verdict is therefore discarded and end-of-turn
    fires anyway. Frame order: VADUserStarted -> audio -> VADUserStopped ->
    TranscriptionFrame(finalized=True). Assert on_user_turn_stopped fired even
    though the stub analyzer returned INCOMPLETE. This test FAILS if a future
    change makes the analyzer decide under W-safe — i.e. it documents F3."""
```

built with `start=[MinWordsUserTurnStartStrategy(min_words=2)]`,
`stop=[TurnAnalyzerUserTurnStopStrategy(turn_analyzer=<stub returning INCOMPLETE>)]`.
A companion `test_wonset_respects_analyzer` prepends `VADUserTurnStartStrategy()`
and asserts the turn does **not** stop while the analyzer says INCOMPLETE — the
W-onset guarantee. (Both are `@pytest.mark.asyncio` and need a task manager; the §7
fixture supplies one, or they `pytest.importorskip` the controller if setup is
non-trivial — but they must run on Linux, no audio, no model.)

The eight existing `tests/unit/test_interruption.py` tests are untouched; the
draft's `TranscriptionFrame` import there is no longer needed.

**7c — the measurement procedure Larry runs.** Every step is a command and a
recorded number. Run it for whichever L15 config is active
(`JARVIS_WHISPER_VAD_BARGE_IN`); the floor differs by config (L8). Do not skip the
baseline: without `B_ms` the bound has no meaning. **All medians are of
`TURN vad_stop->first_audio`** (`--metric vad_stop`), the F4 instrument.

```
P0. Baseline, on the SAME machine that will run P2-P5.
    JARVIS_STT_PROVIDER=deepgram ./scripts/mortimer.sh
    ***VERIFY THE BASELINE IS ACTUALLY DEEPGRAM (F21).***
    run_bot.sh does `set -a; . ./.env` which OVERRIDES the command prefix, so
    confirm logs/bot.log carries exactly one line matching
      "voice_providers stt=deepgram ".
    If it says whisper_mlx, JARVIS_STT_PROVIDER is set in .env — comment it out
    there and redo P0. (Without this check a baseline silently measured on
    Whisper makes the whole gate compare Whisper to Whisper.)
    Speak 10 turns: 5 that do not delegate ("what time is it",
      "say that again", "thanks", "what's the weather", "repeat that")
      and 5 that do ("remind me to buy milk tomorrow at seven",
      "what did I save about the wifi", "search the web for tech news",
      "what apps have you built", "check the build status").
    python scripts/latency_probe.py logs/bot.log --metric vad_stop
    RECORD: overall p50 -> B_ms.

P1. Switch to local STT.
    JARVIS_STT_PROVIDER=whisper_mlx JARVIS_TURN_DETECTOR=smart_turn_v3 \
      ./scripts/mortimer.sh
    Confirm logs/bot.log carries a line
      "voice_providers stt=whisper_mlx ..." and a "turn_start config=W-safe"
      (or "W-onset" if JARVIS_WHISPER_VAD_BARGE_IN=true) line.
    If stt=whisper_mlx but no turn_start line, STOP — Step 4 was not applied.

P2. Repeat the identical 10 turns.
    python scripts/latency_probe.py logs/bot.log --metric vad_stop
    RECORD: overall p50 -> M_ms at stop_secs=2.5.

P3. Decision:
    IF M_ms <= B_ms + 150  -> G3(b) latency bound MET at stop_secs=2.5.
                              Go to P5.
    ELSE, by config:
      W-safe : stop_secs has NO lever (the analyzer is bypassed and stop_secs
               is the segmentation boundary — L8). Go straight to the FAILURE
               branch and record NOT MET.
      W-onset: lower stop_secs by 0.25 (edit the single VADParams(stop_secs=…)
               literal) and go to P4.

P4. (W-onset only.) For stop_secs in 2.25, 2.00 (floor 2.0, NOT below — L8):
      a. pytest tests/unit/test_turn_ordering.py tests/unit/test_speaker_gate.py -q
                                                          -> must be green
      b. Re-run the D-010 utterance: play the 2.000 s-gap recording
         ("Remind me to buy milk." <2.0 s silence> "Tomorrow at seven AM.")
         and confirm ONE aggregated turn / one merged delegation to scheduler.
         If it splits -> this stop_secs is REJECTED; go to FAILURE.
      c. Repeat the 10 turns; python scripts/latency_probe.py logs/bot.log --metric vad_stop
      d. IF p50 <= B_ms + 150 -> MET. Record the stop_secs. Go to P5.
    If 2.0 is reached without meeting the bound, or any value is rejected by (b):
      FAILURE BRANCH — report verbatim:
        "G3(b) not met: local STT median vad_stop->first_audio is <M> ms
         against a Deepgram baseline of <B> ms (bound <B+150> ms) at the
         applicable stop_secs floor. Per roadmap R6, local STT does not ship
         without turn detection at parity; the recorded outcome is that T3.2
         fails its gate on this hardware / this L15 config."
      Do NOT lower stop_secs below the floor. Do NOT relax the bound.

P5. Full defect replay, with the final stop_secs and the active config:
      pytest tests/unit/test_turn_ordering.py tests/unit/test_interruption.py \
             tests/unit/test_speaker_gate.py -q
      Live: leave the TV on for 10 minutes with no one speaking, then grep:
        grep -c "interrupted" logs/bot.log          -> expect 0
        grep -c "speaker_gate_drop" logs/bot.log    -> expect > 0
      RECORD both numbers. This IS the L15 gate: if config=W-onset and
      "interrupted" > 0, W-onset is REJECTED (it reopened the TV defect) —
      fall back to W-safe and record that Whisper cannot match Flux barge-in
      here.
```

### Step 8 — T3.5 sizing, executed

Run **after** L7 has selected a model and **before** Larry buys anything (O5).

```
S1. On the machine running Ollama, after the L7 STEP A real-system-prompt run
    (NOT a max_tokens:8 ping — F6):
      ollama ps
    RECORD the SIZE column for the chosen tag -> LLM_RESIDENT_GB.
S2a. Capture bot RSS at startup BEFORE the first turn (F12 — the draft asked
     for an rss_at_startup no step produced):
      ./scripts/mortimer.sh stop
      ./scripts/mortimer.sh start ; sleep 20
      ps -o rss= -p $(pgrep -f "jarvis.bot.bot") | tr -d ' '   -> R0_kb
S2b. Speak ONE turn, wait for the USER: line in logs/bot.log, then:
      ps -o rss= -p $(pgrep -f "jarvis.bot.bot") | tr -d ' '   -> R1_kb
S2c. STT_GB = max(2.5, (R1_kb - R0_kb) / 1048576)
     The max() is NOT a judgment-call fallback (F12): MLX allocates in Apple's
     unified memory pool that ps does not attribute to the process, so the RSS
     delta is a LOWER BOUND. 2.5 GB is large-v3-turbo's ~1.6 GB fp16 weights
     plus the MLX arena.
S3. PROCESS_GB = LLM_RESIDENT_GB + STT_GB + 0.5 + 0.5 + 3.0     # no OS term here
S4. For each candidate mini configuration (24, 36, 48, 64, 96, 128 GB):
      ACCEPT iff PROCESS_GB + 8.0 <= RAM_GB          # OS headroom added ONCE (F12)
S5. Print the table. The SMALLEST accepting configuration is the answer to O5.
S6. If no configuration at or below 64 GB accepts: the L7 ladder is strictly
    ascending, so there is NO tested candidate that is both smaller and passing
    (F11). Do NOT search backwards. Record PROCESS_GB and take L7's STOP branch
    (cloud Supervisor, T4b stays gated).
```

Record the completed table in §8 C1. **This is the only place the arithmetic
lives** — do not re-derive it in the runbook.

### Step 9 — the T3.1 relocation runbook

**File:** `docs/runbooks/MAC_MINI_RELOCATION.md`, plus the four files it
references. Every command below is run **by Larry on the mini**, in order. The
implementing model writes the files; it does not run any of this.

**9.0 — Preconditions, checked and refused on.**
```
[ ] G2 has passed (MORTIMER_REMOTE_ACCESS_PLAN.md §8). C2 forbids proceeding
    otherwise. If G2 has not passed, STOP: an unauthenticated sidecar on a
    machine reachable from the tunnel is exactly what C2 exists to prevent.
[ ] Tailscale is installed and the mini shows in `tailscale status`.
[ ] Homebrew is installed at /opt/homebrew (Apple Silicon prefix).
[ ] The mini is on macOS 26 or later with `xcode-select --install` done
    (mlx-whisper builds nothing, but pyaudio-adjacent wheels want the CLTs).
```

**9.1 — Repo and venv.**
```
git clone <repo> ~/mortimer && cd ~/mortimer
uv venv && source .venv/bin/activate
uv pip install -r requirements-lock.txt
# F1 — the whisper branch needs faster-whisper (module-scope import on every
# platform) AND mlx-whisper (Apple Silicon runtime); kokoro needs kokoro-onnx.
# Pins match pipecat 1.4.0's extras exactly (measured: whisper->faster-whisper
# ~=1.2.1, mlx-whisper~=0.4.2, kokoro-onnx>=0.5.0,<1).
uv pip install "faster-whisper~=1.2.1" "mlx-whisper~=0.4.2" "kokoro-onnx>=0.5.0,<1"
python scripts/init_db.py
# Sanity: the whisper module now imports (this fails loudly if a pin is wrong):
python -c "from pipecat.services.whisper.stt import MLXModel, WhisperSTTServiceMLX; print(MLXModel.LARGE_V3_TURBO.value)"
```

**9.2 — Vault migration to the mini.** `jarvis/vault.py` has an export path and
no import command (§1.9), so the migration is: move the ciphertext, move the key,
verify, then destroy the intermediate.

```
# On the MacBook:
python -m jarvis.vault export-key          # prints base64 to STDOUT; stderr warns
# Copy data/secrets.vault to the mini over the tunnel (scp), NOT over email/chat:
scp data/secrets.vault larry@<mini-tailnet-name>:~/mortimer/data/secrets.vault

# On the mini, as Larry, with the exported base64 in the clipboard:
sudo mkdir -p /usr/local/etc/mortimer
sudo touch /usr/local/etc/mortimer/vaultkey
sudo chown "$USER" /usr/local/etc/mortimer/vaultkey
chmod 600 /usr/local/etc/mortimer/vaultkey
printf 'JARVIS_VAULT_KEY=%s\n' '<paste-the-base64>' > /usr/local/etc/mortimer/vaultkey

# Verify BEFORE going further. This must list the same names as the MacBook:
set -a; . /usr/local/etc/mortimer/vaultkey; set +a
python -m jarvis.vault list
python -m jarvis.vault status

# Then clear the clipboard and the shell history entry:
pbcopy < /dev/null
```

**Do not run `python -m jarvis.vault init` on the mini.** It would generate a
*new* key and write an *empty* vault (`jarvis/vault.py:350-371`), and the copied
ciphertext would then be undecryptable. `init` refuses when the file already
exists (`:352-354`), which is the only guard — copy the vault file **first**.

**Do not run `rotate-key` on the mini** while the MacBook still needs the vault:
`rotate-key` re-encrypts in place with a new Keychain-stored key
(`jarvis/vault.py:525-536`), which strands the other host.

**Why the Keychain is not used here:** L11. `jarvis/vault.py:106-108` checks
`JARVIS_VAULT_KEY` first, so the wrapper's `source` wins and the Keychain is
never consulted on this host.

**9.3 — `scripts/launchd_exec.sh`** (new, committed, contains no secret):

```bash
#!/bin/bash
# The one launchd wrapper (MORTIMER_LOCAL_VOICE_AND_MINI_PLAN.md L10/L11).
#
# launchd gives a job a nearly empty environment: no PATH beyond
# /usr/bin:/bin:/usr/sbin:/sbin, no HOME on some paths, and — crucially —
# no login keychain it can unlock. So this wrapper does three things and
# nothing else:
#   1. exports the shell environment the Python stack and its MCP children
#      need (K2's BASE_ENV_KEYS is what a child is allowed to inherit, so
#      PATH/HOME/TMPDIR must exist in the parent for it to inherit them);
#   2. sources /usr/local/etc/mortimer/vaultkey (mode 0600) so
#      JARVIS_VAULT_KEY is set before jarvis.vault._load_key() runs;
#   3. execs the module named as $1.
#
# NO SECRET IS WRITTEN HERE OR IN ANY PLIST (roadmap C9). The key file is
# created by hand on the host and is not in the repo.
set -euo pipefail

MORTIMER_HOME="${MORTIMER_HOME:-$HOME/mortimer}"
KEYFILE="${MORTIMER_KEYFILE:-/usr/local/etc/mortimer/vaultkey}"

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export HOME="${HOME:-/Users/$(id -un)}"
export TMPDIR="${TMPDIR:-/tmp}"
export LANG="${LANG:-en_US.UTF-8}"

cd "$MORTIMER_HOME"

if [ -r "$KEYFILE" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$KEYFILE"
  set +a
else
  echo "launchd_exec: $KEYFILE unreadable — the vault will fall back to the" \
       "Keychain, which is not available to launchd on a headless host" >&2
fi

# Non-secret configuration still comes from .env, exactly as run_bot.sh does.
if [ -r ./.env ]; then set -a; . ./.env; set +a; fi

exec .venv/bin/python -m "$1"
```

**9.4 — the three plists, as LaunchDaemons (F5).** All three go in
`/Library/LaunchDaemons/` on the mini (the repo copy under `deploy/launchd/` is the
source; Larry `sudo cp`s them). Each has `<key>UserName</key><string>USERNAME</string>`
so it runs as Larry — his `$HOME`, his Homebrew prefix — while **starting at boot
with no login**, which a `gui/<uid>` LaunchAgent cannot do (that was the draft's F5
bug). `KeepAlive` restarts a crashed process; `RunAtLoad` starts it at boot.
**No `EnvironmentVariables` entry contains a secret** (C9).

`deploy/launchd/com.mortimer.llm.plist`:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.mortimer.llm</string>
  <key>UserName</key><string>USERNAME</string>
  <key>ProgramArguments</key>
  <array><string>/opt/homebrew/bin/ollama</string><string>serve</string></array>
  <key>EnvironmentVariables</key><dict>
    <!-- loopback only: K1 protects Mortimer's routes, not Ollama's, so the
         model server must not be reachable from the tunnel -->
    <key>OLLAMA_HOST</key><string>127.0.0.1:11434</string>
    <!-- keep weights resident forever; an unloaded model turns the first
         turn after a pause into a cold start -->
    <key>OLLAMA_KEEP_ALIVE</key><string>-1</string>
    <key>OLLAMA_MAX_LOADED_MODELS</key><string>1</string>
    <!-- F6: the Supervisor system prompt alone is ~3.4k tokens (measured);
         Ollama's 4096 default SILENTLY TRUNCATES it and routing collapses -->
    <key>OLLAMA_CONTEXT_LENGTH</key><string>16384</string>
    <key>HOME</key><string>/Users/USERNAME</string>
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>/Users/USERNAME/mortimer/logs/ollama.log</string>
  <key>StandardErrorPath</key><string>/Users/USERNAME/mortimer/logs/ollama.log</string>
</dict></plist>
```

`deploy/launchd/com.mortimer.admin.plist` — identical shape (incl. `UserName`,
`RunAtLoad`, `KeepAlive`), with:
```xml
  <key>Label</key><string>com.mortimer.admin</string>
  <key>UserName</key><string>USERNAME</string>
  <key>ProgramArguments</key>
  <array>
    <string>/Users/USERNAME/mortimer/scripts/launchd_exec.sh</string>
    <string>jarvis.admin.server</string>
  </array>
  <key>StandardOutPath</key><string>/Users/USERNAME/mortimer/logs/admin.log</string>
  <key>StandardErrorPath</key><string>/Users/USERNAME/mortimer/logs/admin.log</string>
```

`deploy/launchd/com.mortimer.bot.plist` — identical shape, with:
```xml
  <key>Label</key><string>com.mortimer.bot</string>
  <key>UserName</key><string>USERNAME</string>
  <key>ProgramArguments</key>
  <array>
    <string>/Users/USERNAME/mortimer/scripts/launchd_exec.sh</string>
    <string>jarvis.bot.bot</string>
  </array>
  <key>StandardOutPath</key><string>/Users/USERNAME/mortimer/logs/bot.log</string>
  <key>StandardErrorPath</key><string>/Users/USERNAME/mortimer/logs/bot.log</string>
```

The runbook instructs Larry to install them into the **system** domain:
```
sudo cp deploy/launchd/com.mortimer.*.plist /Library/LaunchDaemons/
sudo sed -i '' "s/USERNAME/$(id -un)/g" /Library/LaunchDaemons/com.mortimer.*.plist
sudo chown root:wheel /Library/LaunchDaemons/com.mortimer.*.plist
sudo chmod 644 /Library/LaunchDaemons/com.mortimer.*.plist
sudo launchctl bootstrap system /Library/LaunchDaemons/com.mortimer.llm.plist
sudo launchctl bootstrap system /Library/LaunchDaemons/com.mortimer.admin.plist
sudo launchctl bootstrap system /Library/LaunchDaemons/com.mortimer.bot.plist
sudo launchctl print system/com.mortimer.bot | grep -E "state|last exit"  # state = running
```
Unload is `sudo launchctl bootout system/com.mortimer.bot`. Because these are
system daemons they start on **boot**, before any login — which is exactly what
G3(d) requires.

**Log rotation (F22).** `deploy/newsyslog.d/mortimer.conf` (new, committed):
```
# logfile                               owner:group    mode count size(KB) when flags
/Users/USERNAME/mortimer/logs/bot.log   USERNAME:staff 644  5     102400   *    J
/Users/USERNAME/mortimer/logs/admin.log USERNAME:staff 644  5     102400   *    J
/Users/USERNAME/mortimer/logs/ollama.log USERNAME:staff 644 3     102400   *    J
```
Install: `sudo sed "s/USERNAME/$(id -un)/g" deploy/newsyslog.d/mortimer.conf | sudo tee /etc/newsyslog.d/mortimer.conf >/dev/null`.

**Why `logs/bot.log` is the plist's `StandardOutPath`.** Most of Mortimer's runtime
output is `print()` to stdout, not `logging` (`scripts/mortimer.sh`, anchor the
rotation comment), and `scripts/latency_probe.py` parses exactly those printed
`TURN` lines. Pointing launchd's stdout at the same path keeps the latency
instrument working unchanged. launchd appends and never rotates itself — hence the
`newsyslog.conf` above, which caps each log at 100 MB across 5/3 generations so the
latency probe and P5's `grep -c` never read a multi-gigabyte file.

**9.5 — the service token (K1 bootstrap).**
```
python -m jarvis.auth add service-bot        # prints the token ONCE
python -m jarvis.vault set JARVIS_SERVICE_TOKEN   # paste it at the prompt
```
Per `MORTIMER_REMOTE_ACCESS_PLAN.md` K1's bootstrap paragraph. It reaches MCP
children through `requires_env` (K2). Nothing in this plan re-specifies it.

**9.6 — bind and URLs.** Set `JARVIS_BIND_HOST` to the mini's tailnet address in
`.env` on the mini. `jarvis/bind.py:resolve_bind_host`
(`MORTIMER_REMOTE_ACCESS_PLAN.md` §3 A8) refuses and exits 2 unless
`JARVIS_AUTH_ENABLED=true` and an unrevoked token exists — do not work around
that; if it exits 2, 9.5 was skipped. Clients get `JARVIS_BOT_URL` and
`JARVIS_ADMIN_URL` pointing at the same tailnet address (K5, `jarvis/urls.py`).

**9.7 — wake word stays on the client.** On the MacBook (or the native client
host), keep running `./scripts/run_wakeword.sh`. Point its bot target at the mini
through `JARVIS_BOT_URL`. Verify: say the wake word on the client, watch
`logs/bot.log` **on the mini** show a session start. If the wake word fires but
no session starts, the failure is `JARVIS_BOT_URL` or the token (K1), not this
plan.

**9.8 — G3(d)'s three days.** Run the full stack on the mini with **no MacBook
Python process** for 3 consecutive days. The check each morning:
```
sudo launchctl print system/com.mortimer.bot | grep -E "state|last exit"
pgrep -fl "jarvis.bot.bot|jarvis.admin.server"      # on the MacBook: must be EMPTY
```

### Step 10 — documentation and the deviation record

- `README.md`: add the K7 variables **and `JARVIS_WHISPER_VAD_BARGE_IN`** to the
  env table with their enums and defaults, and one troubleshooting row
  ("bot starts but never transcribes → check `JARVIS_STT_PROVIDER`").
- `.env.example` (CP-F10): append a commented LOCAL block — create the file if a
  sibling wave has not; three plans append distinct blocks and merge cleanly:
  ```
  # --- T3 local voice (MORTIMER_LOCAL_VOICE_AND_MINI_PLAN.md) ---
  # JARVIS_STT_PROVIDER=deepgram          # deepgram | whisper_mlx
  # JARVIS_TURN_DETECTOR=stt              # stt | smart_turn_v3 | smart_turn_coreml
  # JARVIS_TTS_PROVIDER=elevenlabs        # elevenlabs | kokoro
  # JARVIS_SMART_TURN_MODEL_PATH=         # required iff detector=smart_turn_coreml
  # JARVIS_WHISPER_VAD_BARGE_IN=false     # L15: true = VAD-onset barge-in (unverified)
  ```
- `DEVIATIONS.md`: append `### D-013 — 2026-08-27` recording **the real,
  post-review fact** (not just "smart-turn was already on"): *Plan reference:*
  roadmap §2.3 T3.2; *Specified:* "add `LocalSmartTurnAnalyzerV3` … replacing the
  end-of-turn detection Flux performed inside the STT"; *Installed reality:* the
  analyzer was **already** the live turn-close decision-maker via
  `UserTurnStrategies.__post_init__` — but swapping the STT to a segmented service
  **bypasses** it under the default config, because the late transcript's turn-start
  resets the stop strategies (cite `user_turn_strategies.py` default,
  `user_turn_controller.py` reset, and the stop strategy's `# Fallback: handle
  transcripts when no VAD stop was received`); *Adaptation:* `JARVIS_TURN_DETECTOR=stt`
  returns `None` so the default keeps applying, a startup log line names the
  effective analyzer and the L15 config, and `JARVIS_WHISPER_VAD_BARGE_IN=true`
  restores analyzer decisioning at the cost of unverified barge-in (L15);
  *Architecture impact:* the barge-in / analyzer trade under Whisper (L15), a Larry
  decision measured in §8 B.
- `docs/plans/MORTIMER_PLATFORM_ROADMAP.md`: annotate §2.3 T3.2/T3.3 and §4
  G3(e) with "see `MORTIMER_LOCAL_VOICE_AND_MINI_PLAN.md` Corrections 1/2/4 and
  L15". Do not edit the roadmap's decisions. (Roadmap edits are SEC-owned; this is
  a text-only pointer.)

### Step 11 — run the tests

```
pytest tests/unit -q                                   # all green on Linux
pytest tests/integration -q                            # non-live subset
python scripts/check_skills.py
cd web && npm run build                                # CI gate; unchanged by this plan
```

### Step 12 — hand off to Larry

Print, and stop:
```
Branch: t3-local-voice-and-mini
Larry commits:
  1. the branch above
  2. the LOCAL row of docs/plans/ALLOWLIST_SEQUENCE.md (deny += docs/runbooks/**),
     then run its verify command (C8; the JSON itself is SEC-owned — do NOT edit
     config/self_edit_allowlist.json directly)
Larry then runs, in order: §8 A (model selection), §8 B (G3(b) re-tune +
the L15 W-safe/W-onset decision), §8 C (sizing), §8 D (Kokoro A/B),
§8 E (relocation + G3).
```

---

## §6 Tuning knobs — where every number lives (one place each)

| Knob | Single home | Default | Env override | Notes |
|---|---|---|---|---|
| STT provider | `jarvis/config.py` `jarvis_stt_provider` | `deepgram` | `JARVIS_STT_PROVIDER` | K7. Read only in `jarvis/bot/providers.py`. |
| Turn detector | `jarvis/config.py` `jarvis_turn_detector` | `stt` | `JARVIS_TURN_DETECTOR` | K7. `stt` = pipecat's implicit `LocalSmartTurnAnalyzerV3` (Correction 1). |
| TTS provider | `jarvis/config.py` `jarvis_tts_provider` | `elevenlabs` | `JARVIS_TTS_PROVIDER` | K7 / R7. |
| CoreML model dir | `jarvis/config.py` `jarvis_smart_turn_model_path` | `None` | `JARVIS_SMART_TURN_MODEL_PATH` | Required iff detector is `smart_turn_coreml`. |
| Whisper VAD barge-in (L15) | `jarvis/config.py` `jarvis_whisper_vad_barge_in` | `false` | `JARVIS_WHISPER_VAD_BARGE_IN` | L15. `true` = W-onset (VAD-onset barge-in, unverified). whisper_mlx only. |
| Whisper model id | `jarvis/bot/providers.py` `WHISPER_MODEL` | `mlx-community/whisper-large-v3-turbo` | none (code constant) | Guarded by test #4 (no runtime assert — F19). |
| Whisper no-speech threshold | `jarvis/bot/providers.py` `WHISPER_NO_SPEECH_PROB` | `0.6` | none | Lower = more silence-suspicious (`pipecat/services/whisper/stt.py:365-370`). |
| Whisper temperature | `jarvis/bot/providers.py` `WHISPER_TEMPERATURE` | `0.0` | none | Deterministic transcripts. |
| Whisper TTFS p99 (F20) | `jarvis/bot/providers.py` `WHISPER_TTFS_P99_S` | `1.0` | none | Passed as `ttfs_p99_latency`; feeds `max(0, ttfs - stop_secs)`. Second reason the L8 floor is well above 1.0. |
| Smart-turn internal silence | `jarvis/bot/providers.py` `SMART_TURN_STOP_SECS` | `3.0` | none | pipecat's own default; deliberately not the tuning lever (L8). |
| Smart-turn pre-speech / max duration | `jarvis/bot/providers.py` `SMART_TURN_PRE_SPEECH_MS`, `SMART_TURN_MAX_DURATION_SECS` | `500.0`, `8.0` | none | pipecat defaults (`base_smart_turn.py:29-30`). |
| Kokoro voice | `jarvis/bot/providers.py` `KOKORO_DEFAULT_VOICE` | `af_heart` | none | Fixed; `set_voice` is a no-op in Kokoro mode (L13). |
| **VAD stop window — the G3(b) lever** | `jarvis/bot/pipeline.py` `VADParams(stop_secs=…)` | `2.5` | none (single literal) | D-010. Floor is **config-dependent (L8)**: W-safe = 2.5 (no lever); W-onset = 2.0. The one number the re-tune may change. |
| G3(b) instrument (F4) | `jarvis/bot/transcript_log.py` `TURN vad_stop->first_audio`; `scripts/latency_probe.py --metric vad_stop` | — | none | Spans STT latency + `stop_secs`; the medians `B_ms`/`M_ms` come from this line, not `user_end->first_audio`. |
| Latency targets | `scripts/latency_probe.py` `P50_NON_DELEGATED_TARGET_MS`, `P50_DELEGATED_TARGET_MS`, `P90_OVERALL_TARGET_MS` | `1200`, `2500`, `3500` | none | Unchanged by this plan. |
| Routing threshold | `tests/evals/routing_eval.py:30` `ACCURACY_THRESHOLD` | `0.90` | none | C7. Not relaxed under any branch of L7. |
| G3(b) latency bound | this plan, §3 L8 | `B_ms + 150` | none | `B_ms` measured in §5 Step 7 P0 (vad_stop metric). |
| OS headroom | this plan, §3 L9 | `8.0` GB | none | Roadmap §2.3 T3.5. Added ONCE in the RAM rule (F12 — no ×0.85 multiplier). |
| Ollama context length (F6) | `deploy/launchd/com.mortimer.llm.plist` `OLLAMA_CONTEXT_LENGTH` | `16384` | plist edit | Ollama's 4096 default silently truncates the ~3.4k-token Supervisor prompt. |
| Ollama residency | `deploy/launchd/com.mortimer.llm.plist` `OLLAMA_KEEP_ALIVE` | `-1` | plist edit | Never unload. |
| Ollama bind | `deploy/launchd/com.mortimer.llm.plist` `OLLAMA_HOST` | `127.0.0.1:11434` | plist edit | Loopback only (L6). |
| Vault key file path | `scripts/launchd_exec.sh` `KEYFILE` | `/usr/local/etc/mortimer/vaultkey` | `MORTIMER_KEYFILE` | L11. Contents are a secret; the path is not. |

Numbers that exist elsewhere and are **not** duplicated here: everything in
`MORTIMER_REMOTE_ACCESS_PLAN.md` §6 (bind wait, token length) and
`MORTIMER_SECURITY_HARDENING_PLAN.md` §6 (env-scoping switches, detector
thresholds).

---

## §7 Tests — by file and function, with inputs and expected outputs

### `tests/unit/test_providers.py` (new, 17 tests)

A module-level fixture builds a stub settings object so no `.env` and no
credential is needed:

```python
@dataclass
class FakeSettings:
    jarvis_stt_provider: str = "deepgram"
    jarvis_turn_detector: str = "stt"
    jarvis_tts_provider: str = "elevenlabs"
    jarvis_smart_turn_model_path: str | None = None
    jarvis_whisper_vad_barge_in: bool = False
    deepgram_api_key: str | None = "dg"
    elevenlabs_api_key: str | None = "el"
```

| # | Test | Input | Expected |
|---|---|---|---|
| 1 | `test_default_settings_build_deepgram` | `FakeSettings()`, `["mortimer"]` | `type(result).__name__ == "DeepgramFluxSTTService"` |
| 2 | `test_deepgram_receives_keyterms` | as above | the constructed service's settings carry `keyterm == ["mortimer"]` |
| 3 | `test_whisper_branch_selected` | `jarvis_stt_provider="whisper_mlx"`, with `pytest.importorskip("faster_whisper")` then `pytest.importorskip("mlx_whisper")` | `type(result).__name__ == "WhisperSTTServiceMLX"` (skips on Linux CI where mlx_whisper is absent) |
| 4 | `test_whisper_model_constant_matches_pipecat` | `pytest.importorskip("faster_whisper")` first (F1 — the module hard-imports `faster_whisper` at scope on all platforms), then `from pipecat.services.whisper.stt import MLXModel` | `MLXModel.LARGE_V3_TURBO.value == providers.WHISPER_MODEL`. Runs on Linux **only when faster-whisper is installed** (it is, via the `whisper` extra in requirements-lock — F1); otherwise skips. Catches a Pipecat bump renaming the model. |
| 5 | `test_turn_stop_stt_returns_none` | `jarvis_turn_detector="stt"` | `build_turn_stop_strategies(...) is None` |
| 6 | `test_turn_stop_v3_returns_one_strategy` | `"smart_turn_v3"` | list of length 1; `type(x[0]).__name__ == "TurnAnalyzerUserTurnStopStrategy"` |
| 7 | `test_turn_stop_v3_analyzer_is_local_v3` | `"smart_turn_v3"` | the strategy's `_turn_analyzer` is a `LocalSmartTurnAnalyzerV3` |
| 8 | `test_turn_stop_coreml_without_path_raises` | `"smart_turn_coreml"`, path `None` | `pytest.raises(RuntimeError, match="JARVIS_SMART_TURN_MODEL_PATH")` |
| 9 | `test_effective_analyzer_name_default_says_implicit` | `FakeSettings()` | string contains `"LocalSmartTurnAnalyzerV3"` **and** `"implicit"` — the anti-Correction-1 test: it fails if someone "fixes" the default to mean no analyzer |
| 10 | `test_tts_voice_id_elevenlabs` | row `{"elevenlabs_voice_id": "abc"}` | `"abc"` |
| 11 | `test_tts_voice_id_kokoro_is_fixed` | same row, `jarvis_tts_provider="kokoro"` | `providers.KOKORO_DEFAULT_VOICE` |
| 12 | `test_tts_voice_id_none_settings_is_elevenlabs` | `settings=None` | `"abc"` |
| 13 | `test_build_tts_elevenlabs` | `FakeSettings()` | `type(result).__name__ == "ElevenLabsTTSService"` |
| 14 | `TestSettingsSwitches::test_unknown_values_rejected` | four `load_settings` calls with `JARVIS_STT_PROVIDER=whisper-mlx`, `JARVIS_TURN_DETECTOR=smartturn`, `JARVIS_TTS_PROVIDER=piper`, and one valid combination | first three `pytest.raises(RuntimeError, match="JARVIS_…")`; the fourth returns settings |
| 15 | `TestTurnStart::test_deepgram_returns_base_only` | `FakeSettings()`, `speaker_gate_state=None` | list len 1; `type(x[0]).__name__ == "MinWordsUserTurnStartStrategy"` |
| 16 | `TestTurnStart::test_wsafe_whisper_returns_base_only` | `jarvis_stt_provider="whisper_mlx"`, `jarvis_whisper_vad_barge_in=False` | list len 1 (no VAD strategy) — the default is safe |
| 17 | `TestTurnStart::test_wonset_prepends_vad` | `jarvis_stt_provider="whisper_mlx"`, `jarvis_whisper_vad_barge_in=True` | list len 2; `type(x[0]).__name__ == "VADUserTurnStartStrategy"` |

### `tests/unit/test_config.py` (extended, 5 new tests)

| Test | Input | Expected |
|---|---|---|
| `test_whisper_provider_does_not_require_deepgram_key` | env: `OPENAI_API_KEY=x`, `ELEVENLABS_API_KEY=y`, `JARVIS_STT_PROVIDER=whisper_mlx`, no `DEEPGRAM_API_KEY` | `load_settings()` succeeds. **This is the test that makes G3(e) reachable.** |
| `test_deepgram_provider_still_requires_deepgram_key` | same but `JARVIS_STT_PROVIDER` unset | `RuntimeError` matching `DEEPGRAM_API_KEY` |
| `test_kokoro_provider_does_not_require_elevenlabs_key` | `JARVIS_TTS_PROVIDER=kokoro`, no `ELEVENLABS_API_KEY` | succeeds |
| `test_openai_key_always_required` | no `OPENAI_API_KEY`, both providers local | `RuntimeError` matching `OPENAI_API_KEY` |
| `test_check_env_required_vars_match_config` (F7) | for all four `(stt, tts)` combos | `check_env._required_vars(stt, tts) == list(jarvis.config.required_env_vars(stt, tts))` — pins the stdlib-only duplicate to the real rule |

The two existing missing-key tests must pass **unchanged** — that is the
regression check on the error-message shape.

### `tests/unit/test_turn_ordering.py` (new, 2 tests — replaces the F13 tautologies)

Drives a real `UserTurnController`; full description in §5 Step 7b.
`test_whisper_ordering_bypasses_analyzer_under_wsafe` asserts the turn stops even
though a stub analyzer returned INCOMPLETE (documents F3);
`test_wonset_respects_analyzer` asserts it does not. Both run on Linux, no audio,
no model. The two draft `TestWhisperTiming` tests in `test_interruption.py` are
**removed** (they tested frames `InterruptionNotifier` ignores; one duplicated an
existing test — F13).

### `tests/unit/test_speaker_gate.py` (extended, 2 new tests — F10)

| Test | Input | Expected |
|---|---|---|
| `test_speaker_tap_resets_on_vad_start_under_whisper` | drive `SpeakerTap` with `VADUserStartedSpeakingFrame → InputAudioRawFrame×N (speech) → VADUserStoppedSpeakingFrame` (no `UserStartedSpeakingFrame`) | `turn_id` incremented once; `speech_secs[turn_id]` reflects the buffered speech, not 0.0 |
| `test_speaker_tap_no_double_increment_under_flux` | drive both `VADUserStartedSpeakingFrame` and `UserStartedSpeakingFrame` in one turn | `turn_id` increments exactly once (the guard holds) |

### `tests/unit/test_check_local_only.py` (new, 9 tests)

Each drives one pure rule function with an explicit `(env, vault_names)` pair.

| # | Test | Input | Expected |
|---|---|---|---|
| 1 | `test_wrong_stt_provider_fails` | `JARVIS_STT_PROVIDER=deepgram` | fail, message contains `whisper_mlx` |
| 2 | `test_deepgram_key_in_env_fails` | `DEEPGRAM_API_KEY=abc` | fail, message contains `environment`, **not** `abc` |
| 3 | `test_deepgram_key_in_vault_fails` | vault names `{"DEEPGRAM_API_KEY"}` | fail, message contains `vault` |
| 4 | `test_remote_base_url_fails` | `OPENAI_BASE_URL=https://api.openai.com/v1` | fail, message contains `api.openai.com` |
| 5 | `test_loopback_base_url_passes` | `http://127.0.0.1:11434/v1` | pass |
| 6 | `test_real_openai_key_fails` | `OPENAI_API_KEY=sk-proj-REDACTED` | fail; **assert the key value is absent from the message** |
| 7 | `test_sentinel_openai_key_passes` | `OPENAI_API_KEY=local` | pass |
| 8 | `test_subagent_keys_are_residual_not_failure` | `ANTHROPIC_API_KEY=x`, default mode | overall exit 0; output contains `residual:` and `ANTHROPIC_API_KEY` |
| 9 | `test_subagent_keys_fail_under_strict` | same, `--strict` | non-zero exit |

**Adversarial cases test 2, 3 and 6 are the security-relevant ones**: a check
that leaks the credential it is checking is worse than no check.

### `tests/integration/test_local_voice_live.py` (new, `RUN_LIVE`-gated)

| Test | Precondition | Expected |
|---|---|---|
| `test_whisper_transcribes_fixture` | `RUN_LIVE=1`, Apple Silicon, `mlx_whisper` importable, `s1.wav` present at the repo root | `build_stt` on a whisper settings object transcribes `s1.wav` to non-empty text |
| `test_ollama_answers_a_tool_call` | `RUN_LIVE=1`, Ollama up at `OPENAI_BASE_URL` | a `/v1/chat/completions` request carrying the `delegate_task` schema returns a response whose `tool_calls[0].function.name == "delegate_task"` with parseable JSON arguments — the L7 Step B disqualifier, automated |

Both `pytest.skip` with a stated reason when their precondition is absent. They
never run in CI.

### Measured in the sandbox during this revision (measure, don't assert)

Each fix that changes runnable logic was re-extracted and run against the review's
breaking inputs before being written into the plan.

```
# F1 — the import the plan must make work (pipecat hard-imports faster_whisper):
$ python3 -c "from pipecat.services.whisper.stt import MLXModel"
ImportError: Missing module: No module named 'faster_whisper'
$ python3 -c "from pipecat.services.kokoro.tts import KokoroTTSService"
ImportError: Missing module: No module named 'kokoro_onnx'
# F1 — pipecat 1.4.0's real extra pins (drive the requirements edits):
faster-whisper~=1.2.1   mlx-whisper~=0.4.2   kokoro-onnx<1,>=0.5.0

# F2/parent-F5 — every jarvis consumer of InterimTranscriptionFrame:
$ grep -rn InterimTranscriptionFrame jarvis/ scripts/ web/
jarvis/bot/speaker_gate.py:36,310,400   # ONLY TranscriptGate (+ the start
# strategy, which is pipecat code jarvis configures). No captions/console/web.

# L5/G3(e) — the NEW provider-derived required_env_vars (makes G3(e) reachable):
required_env_vars("deepgram","elevenlabs") -> ('OPENAI_API_KEY','DEEPGRAM_API_KEY','ELEVENLABS_API_KEY')
required_env_vars("whisper_mlx","elevenlabs") -> ('OPENAI_API_KEY','ELEVENLABS_API_KEY')   # no DEEPGRAM
required_env_vars("whisper_mlx","kokoro")    -> ('OPENAI_API_KEY',)                          # no cloud STT/TTS

# L12 rule 3 — loopback test against the review's adversarial URLs:
http://127.0.0.1:11434/v1 -> True    http://LOCALHOST:11434/v1 -> True
https://api.openai.com/v1 -> False   http://127.0.0.1@evil.com/v1 -> host=evil.com False
http://localhost.evil.com/v1 -> False   "" -> host=None False

# F15/CP-F8 — the eval denominator is 68 today (NOT 65):
$ python3 -c "import yaml;print(len(yaml.safe_load(open('tests/evals/cases.yaml'))))"
68

# F20 — ttfs_p99_latency IS a valid STTService kwarg (services/stt_service.py:90),
# so passing it through WhisperSTTServiceMLX(**kwargs) is legal.
```

### What the sandbox cannot test, stated plainly

Whisper accuracy, Kokoro audio, ElevenLabs audio, real end-of-turn latency,
Keychain/launchd behaviour, Ollama throughput, and every number in §8. Those are
Larry's, and this plan does not claim any of them as passing.

---

## §8 Verification Larry runs on his hardware

The sandbox has no Keychain, no microphone, no Apple Silicon, no Mac mini, and no
network to ElevenLabs, Deepgram, or Ollama. Everything below is Larry's, in
order. **A, B and C can run on the MacBook before the mini exists** (roadmap
§2.3: *"T3.2/T3.3 can be developed on the MacBook before the mini arrives"*).

### A — G3(a): the local Supervisor model (C7)

Execute §3 L7's tree. Record:

```
A0. Fixture size N: run `python -c "import yaml;print(len(yaml.safe_load(
    open('tests/evals/cases.yaml')))))"` and record N (68 today; 86 after MAIL
    lands its secretary cases — CP-F8). Also record whether a `secretary` agent
    is present when the ladder runs (i.e. whether T5 landed): ____ (yes/no).
    All denominators below are /N, the count the eval itself prints — NOT a
    hard-coded 65 (F15). Do NOT land a fixture edit between a ladder run and its
    recorded result (CROSS_PLAN §C F8).
A1. Candidate adopted: ______________________  (Ollama tag, full, with quant suffix)
    routing_eval run 1: ____/N = ____%
    routing_eval run 2: ____/N = ____%
    routing_eval run 3: ____/N = ____%
    mean: ____%          (gate: >= 90%)
    ollama ps SIZE: ______ GB      -> LLM_RESIDENT_GB for C1
A2. Candidates rejected, with the reason for each:
    ____________________________________________
A3. Latency gate: python scripts/latency_probe.py logs/bot.log --budget
    exit code: ____   (gate: 0)
```

If A ends on L7's STOP branch, **stop here** and report it. B, C and E still
have value (local STT can ship without a local Supervisor), but G3 does not pass
and C3 keeps T4b gated.

### B — G3(b): the re-tune AND the L15 barge-in decision

Execute §5 Step 7's P0–P5. All medians are `TURN vad_stop->first_audio`
(`--metric vad_stop`, F4). Run once for the default **W-safe** config; if barge-in
feels too slow, run again with `JARVIS_WHISPER_VAD_BARGE_IN=true` (**W-onset**) and
compare on B7. Record:

```
B0. L15 config under test:                    W-safe / W-onset
B1. Deepgram baseline median (P0, vad_stop):  B_ms = ______ ms
B2. Whisper median at stop_secs=2.5 (P2):     M_ms = ______ ms
B3. Bound (B_ms + 150):                              ______ ms   MET / NOT MET
B4. Final stop_secs (W-safe: fixed 2.5; W-onset floor 2.0): ______
B5. pytest test_turn_ordering.py test_interruption.py test_speaker_gate.py -q  ____ passed
B6. D-010 utterance -> ONE aggregated turn?          yes / no
    (W-safe: expected NO — analyzer bypassed, records the honest R6 miss;
     W-onset: expected YES — analyzer merges the pause)
B7. 10-minute TV soak: "interrupted" lines = ____ (expect 0);
                       "speaker_gate_drop" lines = ____ (expect > 0)
    (W-onset ONLY passes if "interrupted" == 0. If > 0, W-onset reopened the
     TV defect — reject it, fall back to W-safe, record that Whisper cannot
     match Flux barge-in here.)
B8. L15 decision recorded: ____ (W-safe accepted / W-onset accepted / Whisper
    barge-in not at parity — R6 fact for roadmap).
```

### C — G3(c): the memory arithmetic

Execute §5 Step 8. Record:

```
C1. LLM_RESIDENT_GB  = ______   (ollama ps, after the STEP A real-prompt run)
    STT_GB           = ______   (= max(2.5, (R1_kb - R0_kb)/1048576); F12)
    TURN_GB          = 0.5
    SPEAKER_GB       = 0.5
    PYTHON_STACK_GB  = 3.0
    PROCESS_GB       = ______   (sum of the five above; NO OS term here)
C2. Smallest accepting mini config (PROCESS_GB + 8.0 <= RAM; headroom once, F12): ____ GB
    -> this is the answer to roadmap O5.
C3. If nothing at or below 64 GB accepts: record PROCESS_GB and take L7's STOP
    branch (the ladder is ascending — there is no smaller passer, F11). ____________________
```

### D — T3.4: the Kokoro A/B (R7's revisit condition)

```
D1. python scripts/tts_ab.py --out audio/tts_ab
D2. Score all 16 files 1-5 WITHOUT opening key.json. Write scores.csv.
D3. python scripts/tts_ab.py --reveal --out audio/tts_ab
D4. Record: ElevenLabs mean ____ ; Kokoro mean ____ ; head-to-head ____ / 8
D5. Decision: R7 stands unless Kokoro wins head-to-head on >= 6 of 8
    sentences. Anything less and JARVIS_TTS_PROVIDER stays elevenlabs.
    (A tie is not a win: switching costs the voice catalog, per L13.)
```

### E — G3(d) and G3(e): the relocation

Execute §5 Step 9 on the mini. Record:

```
E1. Preconditions 9.0 all checked?                   yes / no  (no -> STOP)
E2. python -m jarvis.vault list on the mini lists the same names as the
    MacBook?                                          yes / no
E3. sudo launchctl print system/com.mortimer.bot -> state = running?  yes / no
E4. Reboot the mini. All three services back up with NO login?         yes / no
    (F5: these are LaunchDaemons in the SYSTEM domain, so they start at boot.
     If no: first `sudo launchctl print system/com.mortimer.bot | grep -E
     "state|last exit"` — if the label is not loaded at all, the plist is not
     in /Library/LaunchDaemons or `bootstrap system` was not run. If it is
     loaded but crash-looping, check logs/bot.log for VaultError and verify
     `ls -l /usr/local/etc/mortimer/vaultkey` is 0600 and readable by the
     plist's UserName. Do NOT look for a gui/<uid> agent — there is none.)
E5. G3(d): 3 consecutive days, mini only, no MacBook Python process.
    day 1 ____  day 2 ____  day 3 ____
E6. G3(e): python scripts/check_local_only.py
    exit code: ____ (gate: 0)
    residuals printed: ______________________________________
E7. Wake word on the client starts a session on the mini?              yes / no
```

### F — regression sweep, on the mini, after E

```
F1. pytest tests/unit tests/integration -q                    ____ passed
F2. RUN_LIVE=1 python -m tests.evals.routing_eval             ____%  (C7: >= 90%)
F3. python scripts/check_env.py                               all required PASS?
F4. python scripts/latency_probe.py logs/bot.log --budget     exit ____
```

---

## §9 Rollback

Every piece of this plan is reversible by an environment variable, and the
default value of every switch is today's behaviour — so **an unset environment
is a full rollback of T3.2/T3.3/T3.4.**

| What to undo | How | Data to revert |
|---|---|---|
| Local STT | `JARVIS_STT_PROVIDER=deepgram` (or unset) and restore `DEEPGRAM_API_KEY` in the vault | none |
| Explicit turn analyzer | `JARVIS_TURN_DETECTOR=stt` (or unset) | none — `stt` restores pipecat's implicit default exactly (Correction 1) |
| Whisper VAD barge-in | `JARVIS_WHISPER_VAD_BARGE_IN=false` (or unset) | none — default is W-safe |
| Local TTS | `JARVIS_TTS_PROVIDER=elevenlabs` (or unset) | none |
| Local Supervisor LLM | Restore `OPENAI_BASE_URL` / `OPENAI_MODEL` / `OPENAI_API_KEY` to the cloud values in the vault; `sudo launchctl bootout system/com.mortimer.llm` | none |
| The VAD re-tune | Restore `stop_secs=2.5` at the single `VADParams(stop_secs=…)` literal in `jarvis/bot/pipeline.py` | none |
| The whole relocation | `sudo launchctl bootout system/com.mortimer.{bot,admin,llm}` on the mini; run `./scripts/mortimer.sh` on the MacBook as before | The DB and vault on the mini are **copies**; the MacBook's originals were never deleted (§5 Step 9.2 copies, never moves). **Do not `rotate-key` on the mini** — that is the one action that strands the MacBook. |
| Vault key file | `rm /usr/local/etc/mortimer/vaultkey` on the mini; the MacBook's Keychain key is untouched | none |
| The deny-list entry | Larry reverts the one-line commit | none |

**There is no schema migration in this plan**, so there is no data to migrate
back. The only new persistent artifacts are `logs/ollama.log`, the Ollama model
blobs (`ollama rm <tag>`), and the Kokoro ONNX download (delete the cache dir
Pipecat printed on first use).

**Kill-switch summary** (each read in one place):
`JARVIS_STT_PROVIDER`, `JARVIS_TURN_DETECTOR`, `JARVIS_TTS_PROVIDER` — all in
`jarvis/config.py`, all consumed only by `jarvis/bot/providers.py`.

---

## §10 Risks

| Id | Risk | Likelihood | Impact | Mitigation (and where it lives) |
|---|---|---|---|---|
| R-L1 | No candidate on the L7 ladder clears 90 % routing | medium | G3(a) fails; T4b stays gated by C3 | L7's STOP branch is written out verbatim, including the sentence to report. The fallback is roadmap R-T3a — local STT, cloud Supervisor — and the threshold is not relaxed. Evaluate on the MacBook **before** buying (O5). |
| R-L2 | The vault key on the mini is a 0600 file, not Keychain-protected (F5) | certain | **Anything that can read one file as Larry reads the master key at rest** — a compromised MCP child (K2 scopes env, not the filesystem), any backup, Time Machine, `find / -perm 600` | Accepted and recorded (L11). This is a real move from "Keychain ACL" to "file mode" and, honestly stated (correcting the draft), **toward exposed** — a file read is now a key read. It is unavoidable once the box must come up headless at boot (the LaunchDaemon requirement), and it is the least-bad of the F5 alternatives. The T4b sensitive-tier key is explicitly **not** in this vault (R8: the client holds it), which bounds the blast radius. |
| R-L3 | Whisper's segment latency pushes end-of-turn past `B_ms + 150` and the config's floor cannot absorb it | medium | G3(b) fails | §5 Step 7's P3/P4 is a bounded search with a config-dependent floor (L8) and an explicit failure sentence. R6 forbids shipping local STT without turn detection at parity, so "ship it anyway" is not a branch — the recorded outcome is the honest miss. |
| R-L4 | Ollama's throughput on Apple Silicon is below `mlx_lm.server`'s and the latency gate fails on generation, not on TTFT | low-medium | G3(a) Step E fails on a model that passed accuracy | Escape hatch recorded in L6: re-run the same candidate against `mlx_lm.server` at `http://127.0.0.1:8080/v1` with the same `EVAL_*` variables. If it then passes, the swap is a base-URL change and a different plist `ProgramArguments` — no jarvis code change, because both are `OpenAILLMService`. Record it as a deviation. |
| R-L5 | `SegmentedSTTService` buffers audio between VAD frames and a long utterance grows the buffer unbounded | low | memory spike on a monologue | `SmartTurnParams.max_duration_secs = 8` caps the analyzer's buffer; the STT's own buffer is bounded by the VAD stop window, which is ≤ 2.5 s of silence, not of speech. Watch `PYTHON_STACK_GB` in §8 C1; if the measured RSS delta exceeds 4 GB, report it rather than raising the budget. |
| R-L6 | Kokoro's first-use model download happens mid-turn | low | one very slow first reply | §5 Step 5 / the runbook pre-fetch it. Default-off makes the blast radius one measurement session. |
| R-L7 | A Pipecat upgrade changes `default_user_turn_stop_strategies()` and silently removes the analyzer | low | end-of-turn regresses with no error | `test_providers.py` #4 and #9 (§7) fail on that change. #9 asserts the *word* "implicit" in the effective-analyzer string, only correct while the default supplies the analyzer. (No runtime assert — F19 — the guard is the test.) |
| R-L8 | launchd's `StandardOutPath` appends forever; `logs/bot.log` grows unbounded on the mini | certain | disk fills over months | **Fixed, not just noted (F22):** `deploy/newsyslog.d/mortimer.conf` caps each log at 100 MB over 5/3 generations; §8 E-sweep can add a `ls -l logs/*.log*` soak check. `scripts/mortimer.sh`'s own rotation does not apply under launchd, which is why newsyslog owns it. |
| R-L9 | *(withdrawn — F8)* the draft's base-URL "fix" was a no-op; nothing changed, so there is no regression to guard. Row kept as a tombstone so the id is not silently reused. | — | — | Correction 3 and the Step-6b base-URL edit are deleted; `check_env.py`'s base-URL reads are untouched. |
| R-L10 | Two hosts, two vault key sources, and someone runs `rotate-key` | medium | the other host is stranded | Called out twice: §5 Step 9.2 and §9. There is no code guard — `rotate-key` cannot know about the other host — so this is a documented operational rule, stated as such. |

---

## §11 Self-audit — the nine-item taxonomy, walked

**1. Multi-consumer contracts named but not typed.**
K7 is the contract this plan introduces and more than one consumer reads it
(`jarvis/config.py` declares, `jarvis/bot/providers.py` reads,
`scripts/check_local_only.py` reads `JARVIS_STT_PROVIDER`,
`scripts/check_env.py` reads `JARVIS_STT_PROVIDER`/`JARVIS_TTS_PROVIDER`,
`MORTIMER_SENSITIVE_TIER_PLAN.md` will read `jarvis_stt_provider`). The three K7
variables plus `jarvis_smart_turn_model_path` and `jarvis_whisper_vad_barge_in`
(L15) are typed member-by-member in §3 L1/L15 and §5 Step 1: name, enum/type,
default, validator behaviour, and the single read site (`jarvis/bot/providers.py`).
The **five** `providers.py` functions (`build_stt`, `build_turn_start_strategies`,
`build_turn_stop_strategies`, `build_tts`, `tts_voice_id`, plus
`effective_turn_analyzer_name`) have full signatures in §3 L2/L15 and complete
source in §5 Step 2, including what `build_turn_stop_strategies` returning `None`
*means* and what `build_turn_start_strategies` returns per config.
`tts_voice_id`'s tolerance of `settings=None` is specified. **Checked.**

**2. Lifecycle left implicit.**
Three lifecycles were at risk. (a) *Does the STT survive a provider change at
runtime?* No — the switch is read once in `build_pipeline`, so a change needs a
restart; stated in §9's rollback rows ("restart" is implied by every launchctl
row and by `mortimer.sh`). (b) *Does the model stay resident between turns?*
Explicitly, via `OLLAMA_KEEP_ALIVE=-1`, with the reason (cold start). (c) *Do
the launchd services survive a reboot with nobody logged in?* That is the whole
of L11 and it is tested at §8 E4. **Checked.**

**3. How a value is applied — which property, which transition.**
The Whisper model reaches the service through `settings=WhisperSTTServiceMLX.Settings(model=…)`,
and §3 L4 explains the delta-merge mechanism (`apply_update`, cited to
`pipecat/services/settings.py:226-243`) rather than asserting it works. The turn
analyzer reaches the pipeline through `UserTurnStrategies(stop=…)` on the
**user aggregator**, with the D-004 non-attachment points (`TransportParams`,
`PipelineTask`) named so the implementer does not retry them. The voice id
reaches TTS through `TTSUpdateSettingsFrame(settings={"voice": …})` at three
enumerated sites. **Checked.**

**4. Two sections describing the same behaviour differently.** (Re-walked after
the revision.)
- *Correction 1 vs §3 L1 vs §5 Step 4 vs L15* — all say `stt` → `stop=None` →
  pipecat's `LocalSmartTurnAnalyzerV3`, AND all now carry the F3 caveat that under
  whisper W-safe that analyzer is *bypassed*. §5 Step 4 is the only place with
  code. No section still claims "no behaviour change".
- *§3 L8 vs §5 Step 7 vs §6* — L8 states the config-dependent floor (W-safe 2.5,
  W-onset 2.0) and the bound (`B_ms + 150`); Step 7 is the procedure; §6 lists the
  VAD lever and the vad_stop instrument each once. The floors agree across all
  three. (The old "1.75" is gone everywhere — grep-checked.)
- *§3 L9 vs §5 Step 8 vs §8 C1* — the formula appears once (L9, headroom-once);
  Step 8 obtains the measured terms; C1 is the blank. All three now use
  `PROCESS_GB + 8.0 <= RAM`, no ×0.85.
**Checked.**

**5. Copy and visual states named but unspecified.**
Every string a human sees is written out: the L7 STOP report, the G3(b) failure
sentence, `check_local_only.py`'s message shapes incl. rules 4 and 5's now-written
failure strings (§5 Step 6a — F14), `tts_ab.py`'s instruction, the
`launchd_exec.sh` stderr warning, the CoreML `RuntimeError`, the two
`build_turn_start_strategies` log lines (W-safe / W-onset), and the Step 12
hand-off block. **Checked.**

**6. Initialization timing.**
Load-bearing orderings, each stated: `inject_env()` before `Settings` (relied on
by `check_local_only.py`'s `cfg()`); the required-key check **after** construction
(Step 1); `speaker_gate_state` built before the aggregators (so
`build_turn_start_strategies` can receive it); Ollama up before the bot
(`RunAtLoad` + `OLLAMA_KEEP_ALIVE=-1`); and — new — the launchd services now start
at **boot** because they are system LaunchDaemons (F5), which is what makes E4
answerable "yes with no login". Kokoro's first-use download is moved to the
runbook. **Checked.**

**7. Signatures agree; every schema column is populated; every value a step
needs is derivable.**
- `build_stt(settings, keyterms)`, `build_turn_start_strategies(settings, speaker_gate_state)`,
  `build_turn_stop_strategies(settings)` — signatures match between §3 L2/L15, §5
  Step 2 source, and the §5 Step 3/4 call sites.
- `build_set_voice_tool(push_frame, catalog=None, settings=None)` — three args in
  §5 Step 5c and at its call site (located by anchor, not line).
- `required_env_vars(stt, tts)` — same two params in `jarvis/config.py` and
  `load_settings()`; `check_env.py` holds a **stdlib-only duplicate** `_required_vars`
  (F7) pinned equal by `test_check_env_required_vars_match_config`.
- Every §8 blank is produced by an earlier command: `B_ms`/`M_ms` from Step 7
  P0/P2 (**vad_stop** metric), `LLM_RESIDENT_GB` from Step 8 S1, `STT_GB` from
  S2a-S2c (R0 **and** R1 both captured now — F12), the eval percentages from L7
  Step C, `N` from A0.
**Checked.**

**8. Judgment left to the implementer.**
Swept again. The forbidden conditional the review flagged — Step 6b's "prefer the
import; inline only if it actually fails" (F7) — is **deleted**: the inline is now
unconditional (stdlib-only, always). The three genuinely open questions are
decision trees with explicit stops: model selection (L7 STOP text), the G3(b)
re-tune (Step 7, config-dependent floor + failure sentence), and sizing (L9
REJECT → STOP, never "buy more RAM"). One new decision — the L15 barge-in config —
is not left to the implementer: it wires **both** configs behind a flag and hands
the *empirical* choice to Larry via the P5 TV-soak, with a stated default (W-safe).
The `STT_GB` "use 2.5 if you can't measure cleanly" judgment call is replaced by
`max(2.5, delta)` (F12). **Checked.**

**9. Plan drift.** (Re-walked; the revision added five files.)
- Every file in §5 appears in §4's manifest, including the ones the revision added:
  `jarvis/bot/speaker_gate.py` (Step 4b, F10), `jarvis/bot/transcript_log.py`
  (Step 7a, F4), `scripts/latency_probe.py` (Step 7a, F4), `requirements-lock.txt`
  (Step 8, F1), `.env.example` (Step 10, CP-F10), `tests/unit/test_turn_ordering.py`
  (Step 7b, F13). Conversely `speaker_gate.py`/`transcript_log.py` were **removed**
  from "Explicitly NOT touched".
- The two draft `TestWhisperTiming` tests are removed from `test_interruption.py`
  in both §4 and §7 (no dangling reference — grep-checked "TestWhisperTiming").
- No "write X" / "X exists" contradiction; `jarvis/auth.py`/`bind.py`/`urls.py`
  remain cited-not-created; `config/self_edit_allowlist.json` and the roadmap and
  `ALLOWLIST_SEQUENCE.md` are cited-not-edited (SEC-owned).
- The roadmap claims this plan contradicts are all in Corrections 1/2/4/5 and L15,
  each cited, none silently restated as true later.
**Checked.**

### Contract-deviation register

| Contract | Deviation | Why |
|---|---|---|
| K7 | **None.** The three variable names, their value sets, and their defaults are exactly as the brief fixes them. `JARVIS_TURN_DETECTOR=stt` is *clarified* (it selects pipecat's implicit `LocalSmartTurnAnalyzerV3`, not an STT-driven turn) but not changed. `JARVIS_WHISPER_VAD_BARGE_IN` (L15) is an **added** switch, not a change to a K7 variable — it selects between two Whisper barge-in configs and defaults to today's safe behaviour. K7's "reuse the LLM settings, no parallel knob" clause is obeyed: `OPENAI_BASE_URL`/`OPENAI_MODEL`/`OPENAI_API_KEY` are reused as-is. |
| K1, K2, K5 | None. Consumed by citation only. |

### Roadmap gate coverage

| Gate item | Where it is produced | Where it is recorded |
|---|---|---|
| G3(a) routing ≥ 90 % with the local model | §3 L7 Step C | §8 A1 |
| G3(b) defect cases pass; median EOT ≤ baseline + 150 ms (measured `vad_stop->first_audio`, F4; config-dependent floor, L8) | §5 Step 7 | §8 B0–B8 |
| G3(c) memory arithmetic passes for installed RAM | §3 L9, §5 Step 8 | §8 C1–C3 |
| G3(d) 3 days, mini only | §5 Step 9.8 | §8 E5 |
| G3(e) no cloud STT/LLM key | §3 L12, §5 Step 6a | §8 E6 |

---

## §12 Approval checklist

- [ ] Corrections 1/2/4/5 accepted (Correction 3 was withdrawn — F8). In
      particular: smart-turn was already live but is **bypassed** by the Whisper
      swap under the default config (F3), and G3(e) needs `jarvis/config.py` to
      change before it can pass.
- [ ] K7's three switches and their defaults as written in §3 L1.
- [ ] **L6 — Ollama** at `http://127.0.0.1:11434/v1` with `OLLAMA_CONTEXT_LENGTH=16384`
      (F6), and `mlx_lm.server` as the recorded escape hatch (R-L4).
- [ ] **L7 — the ascending ladder and first-passer rule** (F11), including the
      STOP branch (no local model ⇒ cloud Supervisor, T4b stays gated).
- [ ] **L8 — the G3(b) procedure**: the `vad_stop->first_audio` instrument (F4),
      config-dependent `stop_secs` floor (W-safe 2.5 / W-onset 2.0), bound
      `B_ms + 150`, explicit failure sentence.
- [ ] **L9 — the RAM formula, headroom counted ONCE** (F12), as the answer to O5.
- [ ] **L11 — `JARVIS_VAULT_KEY` from a 0600 file on the mini via LaunchDaemons**
      (F5), Keychain not used there, and its honest residual R-L2.
- [ ] **L13 — Kokoro default off**, and the blind A/B's ≥ 6-of-8 bar before R7 is
      revisited.
- [ ] **L15 — the Whisper barge-in trade**: default W-safe (no reopened TV
      defect, degraded barge-in recorded); W-onset opt-in gated on Larry's P5
      TV-soak. This is the one genuinely new decision this revision adds.
- [ ] LOCAL's deny-list row (`docs/runbooks/**`) applied via
      `ALLOWLIST_SEQUENCE.md` — Larry's commit (C8); the JSON is SEC-owned.
- [ ] Branch name `t3-local-voice-and-mini`.
- [ ] §8's five record sheets are the deliverable Larry returns; G3 does not pass
      until every blank in A, B, C and E is filled, **and B8 records the L15
      decision.**
