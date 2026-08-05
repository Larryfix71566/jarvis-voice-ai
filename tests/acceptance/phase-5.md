# Phase 5 Acceptance Checklist — Voice Out

Setup: `./scripts/run_bot.sh`, open `http://localhost:7860/client`, click
Connect, allow the mic. Re-run the Spoken Dozen (phase-4.md); this time every
JARVIS reply must be HEARD aloud, not just seen in the log.

## Heard-aloud replay
- [ ] All 12 Spoken Dozen turns produce audible speech in the default voice
      (rachel)
- [ ] Reply starts promptly after the turn (no multi-second dead air before
      the acknowledgment on delegated turns)

## Voice switching
- [ ] Say "Switch your voice to George" → set_voice tool fires, spoken
      confirmation "Voice switched to George", subsequent speech in George
- [ ] App-message path: send `{"type":"voice/set","voice":"eric"}`
      from the client console → voice switches, `{"type":"voice/current","voice":"eric"}`
      reply received
- [ ] CLI: `python3 -m jarvis.cli /voice eric` → voice list shows eric as
      current for new sessions
- [ ] Say "Switch your voice to Jarvis Prime" (unknown) → spoken error naming
      the available voices, voice unchanged

## Interruption
- [ ] While Jarvis is speaking a long answer, start talking → audio stops
      within ~1 s and Jarvis listens (Flux should_interrupt + VAD)

## Latency medians (server log TURN lines, ≥10 turns each class)
- [ ] Non-delegated turns: p50 user_end→first_audio ≤ 1200 ms
- [ ] Delegated turns: p50 user_end→first_audio ≤ 2500 ms

## BLOCKED ITEM (account-level, not code)
ElevenLabs TTS generation currently returns 401 `detected_unusual_activity`
("Free Tier access has been disabled") from this network. The key authenticates
and lists 21 voices, so wiring, catalog, set_voice, and interruption behavior
are all verified by tests; audible replay, latency medians, and the
heard-aloud portions above require the user to upgrade the ElevenLabs plan
($5 Starter) or clear the block with support. Until then the bot runs and
logs turns normally, but audio frames fail at the TTS stage.

## Automated gate (DONE)
- `pytest tests/unit tests/integration -q` → 166 passed, 3 skipped (live-gated)
- tests/integration/test_bot_wiring.py asserts: locked processor order
  (input → VAD → STT → user agg → LLM → transcript → TTS → output →
  assistant agg), `should_interrupt=True`, exactly two registered functions
  (`delegate_task`, `set_voice`), ElevenLabs settings from voices.yaml
  (model eleven_flash_v2_5, stability 0.5, similarity_boost 0.75)
- tests/unit/test_voice_switch.py: catalog ≥3 voices, id/label/unknown/empty
  resolution, handler pushes TTSUpdateSettingsFrame, unknown-voice error
  message lists available voices
