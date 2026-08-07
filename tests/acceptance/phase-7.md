# Phase 7 Acceptance Checklist — Polish & Proactivity

Setup: `./scripts/run_bot.sh` + `./scripts/run_web.sh`, connect in the browser.

Executed 2026-08-06/07 with the spoken harness + targeted env-fault restarts;
evidence in `.acceptance-scratch/` (run23–run32 logs, `bot.log`, `spoken.db`).

## Proactive reminders
- [x] Set a reminder 2 minutes out ("remind me to stand up in two minutes"),
      keep the session open → Jarvis speaks it UNPROMPTED within ~2.5 min;
      `reminders.delivered = 1` for the row (sqlite3 data/jarvis.db)
      — run23: spoken at the due tick ("Boss, your stretch reminder is due.
      Time to stand up and stretch for a moment."), row id=4 `delivered=1`
      in `.acceptance-scratch/spoken.db`
- [x] Disconnect, set another reminder already due (via CLI:
      `python3 -m jarvis.cli` then the reminder command), reconnect →
      delivered within 30 s of the watcher's next tick
      — run24: row inserted while disconnected (due 08:33), injected on the
      first watcher tick after reconnect and spoken merged with the greeting
      ("Welcome back, Boss. Time to drink water."); row id=5 `delivered=1`.
      (Harness `@AWAIT_TURN` reported TIMEOUT only because the injection was
      merged into the connect-greeting turn rather than a second turn —
      behavior itself verified by bot.log context + DB row.)
- [x] Server log shows no watcher tracebacks; watcher warnings (if any) are
      one-line and the session continues — 0 tracebacks across all of
      bot.log (including sessions with killed MCP servers); watcher kept
      ticking through fault-injection runs

## Degradation matrix (simulate each row safely)

| Failure | Expected | Tick |
|---|---|---|
| LLM API error mid-turn (bad OPENAI_API_KEY for one turn) | user hears nothing new; client shows error banner; next turn retries normally, context intact | [x] — run29: `OpenAILLMService#0 exception … 401` → ErrorFrame, zero TTS output, bot alive; run30 (restored key): normal reply ("Hello, Boss. Good to see you."). Banner display = phase-6 human item |
| ElevenLabs error (revoked key / account block) | error frame logged; banner shows speech-service error; text transcript still updates | [x] — run32 (invalid key): LLM text streamed to client ("Jarvis here. Ready when you are."), `ElevenLabsTTSService#0 connection failed` ERROR + ErrorFrame, no audio. (Also observed for real during the earlier account-block period.) |
| Deepgram error (bad key) | banner shows transcription error; suggest reconnect | [x] — run31 (invalid key): `DeepgramFluxSTTService#0 exception` ERROR; zero `user-stopped-speaking` events — nothing transcribed, no turn. Banner = phase-6 human item |
| Tavily missing/degraded (unset TAVILY_API_KEY) | analyst relays "Web search is unavailable…"; supervisor says it plainly, moves on | [x] — run28: "The web search is unavailable because no API key is configured. You will need to add a search API key to enable lookups." (Note: `get_weather` does not use Tavily — run27 answered weather normally; the search path is the degraded one.) |
| MCP server crash (kill one server process) | SkillRegistry.call returns a failure sentence; Supervisor relays it; RemindersWatcher unaffected | [x] — run26: killed `mcp-notes` child mid-session; `tool_call_failed tool=create_note` WARNING (one line), Supervisor spoke "The note failed to save due to a system error. Please try again in a moment."; no traceback; watcher unaffected. (Registry lifecycle is per-session: 5 stdio children spawn on connect — verified live — and are reaped on disconnect.) |
| Reminders while disconnected | accumulate undelivered; on next connect, watcher delivers within 30 s | [x] — run24 (see above): delivered on first tick after reconnect |

## Latency
- [ ] After a ≥15-turn session: `python3 scripts/latency_probe.py <bot log>`
      → p50 ≤ 1200 ms non-delegated, p50 ≤ 2500 ms delegated,
      p90 ≤ 3500 ms overall — **MISS** (2026-08-07, 26 turns):
      non-delegated p50 7886 ms (n=8), delegated p50 9710 ms (n=18),
      overall p90 29327 ms. Same environment-bound root cause and remedy as
      phase-5.md (Kimi K2.6 completion time dominates; `first_audio` tracks
      `llm_done` within ~2–400 ms; external control TTFB 1.84 s / total
      6.55 s; plan §4 config-only provider switch is the in-spec fix and
      needs a provider key from the user).

## Stretch (7.4) — wake word: IMPLEMENTED client-side
- `web/src/wakeWord.ts`: Porcupine Web with the built-in "Jarvis" keyword;
  on detection plays a WebAudio chime and unmutes the mic. Server unchanged.
- Opt-in: requires `VITE_PICOVOICE_ACCESS_KEY` in `web/.env`; without it the
  toggle is disabled with an explanatory tooltip.
- [ ] Manual: with a key configured, say "Jarvis" from across the room →
      chime + mic unmutes; toggle off stops listening.
      **Awaiting key**: Picovoice discontinued the free tier 2026-06-30;
      user to create the 7-day free trial at console.picovoice.ai (no card),
      paste the AccessKey into `web/.env`, then `cd web && npm run build`.

## Automated gate (DONE)
- `pytest tests/unit tests/integration -q` → 186 passed, 3 skipped
  (live-gated)
- tests/unit/test_reminders_watcher.py: one injection per due row; none when
  empty; none when disconnected (and registry NOT called while disconnected);
  never crashes on registry failure; dedup relies on the delivered flag
- tests/unit/test_latency_probe.py: delegated/non-delegated split, percentile
  math, target flags
- Degradation paths additionally covered: test_registry.py (isError /
  exception / timeout → failure strings), test_subagent.py (timeout /
  exception → FAILED), test_mcp_web_logic.py + test_mcp_servers.py
  (no-key degraded mode)
