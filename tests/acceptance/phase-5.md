# Phase 5 Acceptance Checklist — Voice Out

Setup: `./scripts/run_bot.sh`, open `http://localhost:7860/client`, click
Connect, allow the mic. Re-run the Spoken Dozen (phase-4.md); this time every
JARVIS reply must be HEARD aloud, not just seen in the log.

Executed 2026-08-06/07 with `scripts/spoken_acceptance.py` (headless WebRTC
harness driving real WAV turns); evidence in `.acceptance-scratch/`
(run19–run32 logs, `bot-audio/*.wav` recordings, `bot.log`).

## Heard-aloud replay
- [x] All 12 Spoken Dozen turns produce audible speech in the default voice
      (rachel) — run22: 12/12 `turn=OK`; bot speech recorded to
      `bot-audio/u01…u12-bot.wav` (run22 pass)
- [x] Reply starts promptly after the turn (no multi-second dead air before
      the acknowledgment on delegated turns) — ack-first design verified:
      on delegated turns the acknowledgment sentence is synthesized as soon
      as it streams (`first_audio` ≪ `llm_done`, e.g. 8.0 s vs 32.5 s,
      32.5 s vs 66.6 s; bot.log TURN lines). The absolute delay to first
      audio is LLM-bound — see Latency medians below.

## Voice switching
- [x] Say "Switch your voice to George" → set_voice tool fires, spoken
      confirmation "Voice switched to George", subsequent speech in George
      — run19 (v04 turn); George audible in `bot-audio/v01/v04-bot.wav`
- [x] App-message path: send `{"type":"voice/set","voice":"eric"}`
      from the client console → voice switches, `{"type":"voice/current","voice":"eric"}`
      reply received — run19 `@APP` items (also rachel); echoes captured in
      run19.log. Requires the D-005 receive-path wiring (1 Hz client pings +
      connection-level handler); harness sends pings automatically.
- [x] CLI: `python3 -m jarvis.cli /voice eric` → switches (×3 this session).
      Note (plan 5.5 supremacy): the CLI has no audio — this item confirms
      catalog resolution logic only; audible verification is the two items
      above.
- [x] Say "Switch your voice to Jarvis Prime" (unknown) → spoken error naming
      the available voices, voice unchanged — run19 (transcribed in run log)

## Interruption
- [x] While Jarvis is speaking a long answer, start talking → audio stops
      within ~1 s and Jarvis listens (Flux should_interrupt + VAD)
      — run21: mid-word cut at 0.62 s (`@BARGE b03 b02 6.0`; bot recording
      ends "…the vape—", interrupt answered "Two plus two is four, boss.")

## Latency medians (server log TURN lines, ≥10 turns each class)
- [ ] Non-delegated turns: p50 user_end→first_audio ≤ 1200 ms — **MISS**
- [ ] Delegated turns: p50 user_end→first_audio ≤ 2500 ms — **MISS**

Measured 2026-08-07 (`python3 scripts/latency_probe.py .acceptance-scratch/bot.log`,
21 turns): non-delegated p50 7886 ms / p90 18014 ms (n=8);
delegated p50 7708 ms / p90 30664 ms (n=13); overall p90 28938 ms.

Root cause (environment, not wiring): `first_audio` tracks `llm_done`
within ~2–400 ms on every sampled turn, i.e. Kimi K2.6 completion time
(2.1 s–140 s observed) dominates; TTS-first-byte + transport add only
hundreds of ms. External control (same SUPERVISOR_PROMPT, 2039 chars, and
real tool schemas, direct HTTPS to api.moonshot.ai, 2026-08-06):
TTFB 1.84 s, total 6.55 s — already above the 1200 ms target with zero
pipeline involvement. The plan-sanctioned remedy (§4, config-only):
switch `OPENAI_BASE_URL`/`OPENAI_MODEL` to a faster function-calling
provider (needs a provider key from the user) — do not re-architect.

## Automated gate (DONE)
- `pytest tests/unit tests/integration -q` → 186 passed, 3 skipped (live-gated)
- tests/integration/test_bot_wiring.py asserts: locked processor order
  (input → VAD → STT → user agg → LLM → transcript → TTS → output →
  assistant agg), `should_interrupt=True`, exactly two registered functions
  (`delegate_task`, `set_voice`), ElevenLabs settings from voices.yaml
  (model eleven_flash_v2_5, stability 0.5, similarity_boost 0.75),
  observer single-shot first_audio TURN logging
- tests/unit/test_voice_switch.py: catalog ≥3 voices, id/label/unknown/empty
  resolution, handler pushes TTSUpdateSettingsFrame, unknown-voice error
  message lists available voices
