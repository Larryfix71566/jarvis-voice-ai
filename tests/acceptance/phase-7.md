# Phase 7 Acceptance Checklist — Polish & Proactivity

Setup: `./scripts/run_bot.sh` + `./scripts/run_web.sh`, connect in the browser.

## Proactive reminders
- [ ] Set a reminder 2 minutes out ("remind me to stand up in two minutes"),
      keep the session open → Jarvis speaks it UNPROMPTED within ~2.5 min;
      `reminders.delivered = 1` for the row (sqlite3 data/jarvis.db)
- [ ] Disconnect, set another reminder already due (via CLI:
      `python3 -m jarvis.cli` then the reminder command), reconnect →
      delivered within 30 s of the watcher's next tick
- [ ] Server log shows no watcher tracebacks; watcher warnings (if any) are
      one-line and the session continues

## Degradation matrix (simulate each row safely)

| Failure | Expected | Tick |
|---|---|---|
| LLM API error mid-turn (bad OPENAI_API_KEY for one turn) | user hears nothing new; client shows error banner; next turn retries normally, context intact | [ ] |
| ElevenLabs error (revoked key / account block) | error frame logged; banner shows speech-service error; text transcript still updates | [ ] — currently OBSERVABLE: the account block makes every TTS fail while transcript/logging continue |
| Deepgram error (bad key) | banner shows transcription error; suggest reconnect | [ ] |
| Tavily missing/degraded (unset TAVILY_API_KEY) | analyst relays "Web search is unavailable…"; supervisor says it plainly, moves on | [ ] |
| MCP server crash (kill one server process) | SkillRegistry.call returns a failure sentence; supervisor relays it; RemindersWatcher unaffected | [ ] |
| Reminders while disconnected | accumulate undelivered; on next connect, watcher delivers within 30 s | [ ] |

## Latency
- [ ] After a ≥15-turn session: `python3 scripts/latency_probe.py <bot log>`
      → p50 ≤ 1200 ms non-delegated, p50 ≤ 2500 ms delegated,
      p90 ≤ 3500 ms overall

## Stretch (7.4) — wake word: IMPLEMENTED client-side
- `web/src/wakeWord.ts`: Porcupine Web with the built-in "Jarvis" keyword;
  on detection plays a WebAudio chime and unmutes the mic. Server unchanged.
- Opt-in: requires `VITE_PICOVOICE_ACCESS_KEY` in `web/.env` (free Picovoice
  Console key); without it the toggle is disabled with an explanatory tooltip.
- [ ] Manual: with a key configured, say "Jarvis" from across the room →
      chime + mic unmutes; toggle off stops listening.

## Automated gate (DONE)
- `pytest tests/unit tests/integration -q` → green (watcher + probe tests
  included)
- tests/unit/test_reminders_watcher.py: one injection per due row; none when
  empty; none when disconnected (and registry NOT called while disconnected);
  never crashes on registry failure; dedup relies on the delivered flag
- tests/unit/test_latency_probe.py: delegated/non-delegated split, percentile
  math, target flags

## BLOCKED ITEM (same as Phase 5/6)
Spoken delivery of reminders and real latency numbers require the ElevenLabs
account block to be lifted. Probe, watcher logic, connection gating, and the
degradation paths are all covered by automated tests; the spoken ticks above
remain for manual sign-off once audio works.
