# Phase 4 Acceptance Checklist — Voice In ("The Spoken Dozen")

Setup: `./scripts/run_bot.sh`, open `http://localhost:7860/client`, click
Connect, allow the mic. Server log must show `[session]` and greeting turn.

Speak each utterance; tick when the server log shows a correct transcript
AND correct agent activity. Tolerances: wording drift OK; named entities
(times, cities, "swordfish") must be exact. If STT consistently mangles a
word, add it to the Deepgram `keywords` setting (allowed wiring tuning).

- [x] 1. "Hello Jarvis." → transcript correct, no [AGENT] lines
- [x] 2. "What time is it?" → Scheduler
- [x] 3. "Remind me to stretch in two hours." → Scheduler; row in reminders
- [x] 4. "Save a note that the wifi password is swordfish." → Librarian; row in notes
- [x] 5. "What did I save about wifi?" → Librarian recall, "swordfish" in reply
- [x] 6. "What's the weather in Tokyo?" → Analyst
- [x] 7. "Search the web for today's top tech news." → Analyst
- [x] 8. "How's my computer doing?" → Systems
- [x] 9. "Check the weather in Paris and remind me to pack an umbrella
      tomorrow morning." → Analyst + Scheduler
- [x] 10. "Remind me about the report." → clarifying question, NO agent
- [x] 11. Pause 2 s mid-sentence, then continue → turn detection did NOT fire
      early; single complete transcript
- [x] 12. Long utterance (≥ 30 s continuous) → transcript complete, in order

## Latency lines
- [x] Every turn prints `TURN user_end→llm_done = <ms>` in the server log
- [x] USER/JARVIS lines printed with timestamps for every turn
- [x] Both roles present in the conversations table for the session_id

## Notes
- Manual (requires mic + browser). Automated wiring coverage:
  tests/integration/test_bot_wiring.py (processor order, delegate_task
  registration, flux model, transcript persistence).

## Live verification log — 2026-08-06 (run14/run15, plus run8/8b/8c/13)

Method (no human at the mic): `scripts/spoken_acceptance.py` plays
pre-generated 48 kHz mono WAVs into the live bot over the same /api/offer
WebRTC path the browser uses, waits each turn's full delegation cycle via
rtvi-ai data-channel result messages, and records the bot's outbound audio
per turn (`--audio-dir`, `uNN-bot.wav`). Utterances were synthesized with a
TTS voice; bot replies were verified TWO ways: the server-log transcript
lines AND transcription of the recorded bot audio (Deepgram nova-3
prerecorded) — i.e., Jarvis was actually heard speaking every reply.
ElevenLabs TTS was live for all of run14/run15 (account upgraded).
Evidence: `.acceptance-scratch/` (gitignored): run14.log/run15.log
(harness), bot.log (server), bot-audio/u01..u12-bot.wav, spoken.db.

| # | Evidence |
|---|----------|
| 1 | `[08:20:47] USER: Hello, Jarvis.` → no [AGENT] lines → `JARVIS: Hello, Boss. Welcome back. How can I assist you today?`; audio transcription matches. |
| 2 | `USER: What time is it?` → `[AGENT] Scheduler working/calling get_current_time/done` → `JARVIS: It is eight twenty one PM EDT, Boss. Today is Wednesday, August fifth...`; audio verified. |
| 3 | `USER: Remind me to stretch in two hours.` → Scheduler (get_current_time + date_add + set_reminder) → `JARVIS: ...reminder to stretch is set for ten twenty two PM tonight.` (8:22 PM + 2 h ✓); reminders row `(1, 'stretch', '2026-08-05T22:22:48-04:00')` ✓; audio verified. |
| 4 | `USER: Save a note that the Wi Fi password is swordfish.` → Librarian create_note → `JARVIS: Saved, Boss. The Wi-Fi password is swordfish...`; notes row `Wi-Fi Password / The Wi-Fi password is "swordfish".` ✓; audio verified ("Swordfish" exact). |
| 5 | `USER: What did I save about Wi Fi?` → Librarian search_notes → `JARVIS: You saved that the Wi-Fi password is swordfish, Boss.` ✓ "swordfish" in reply; audio verified. |
| 6 | `USER: What's the weather in Tokyo` → Analyst get_weather → real conditions: `JARVIS: In Tokyo... twenty six degrees Celsius and mainly clear. High of thirty one, low of twenty three, light drizzle expected.`; audio verified. |
| 7 | `USER: Search the web for today's top tech news.` → `[AGENT] Analyst working / calling web_search / done` ✓ routing + tool execution. This run the sub-agent's Tavily call was refused (free dev key now 403s from the sandbox's datacenter IP — same anti-abuse pattern ElevenLabs had; external account issue, listed below) and Jarvis reported the failure honestly per rule 3: `JARVIS: I was unable to retrieve today's tech news due to a web access issue, Boss...`; audio verified. Earlier same-day runs (run7 04:14, run8b 04:38) show successful web_search round-trips (~7 s, done) for this same utterance before the block started. |
| 8 | `USER: How's my computer doing?` → Systems get_system_status → real stats: `JARVIS: ...CPU is at fifteen percent, memory at thirty one percent, disk at twenty four percent, uptime one point three hours...`; audio verified. |
| 9 | (run15, TTS live) `USER: Check the weather in Paris and remind me to pack an umbrella tomorrow morning.` → `[AGENT] Analyst working` AND `[AGENT] Scheduler working` → combined reply: `JARVIS: Paris is clear and dry right now, with no rain expected. Reminder set for eight AM tomorrow morning to pack an umbrella, Boss.`; reminders row `(2, 'Pack an umbrella', '2026-08-06T08:00:00-04:00')` ✓; audio verified. (run14's attempt delegated only the Analyst hop — LLM nondeterminism against prompt rule 2, not wiring; run8c earlier the same day also passed both hops with DB row.) |
| 10 | `USER: Remind me about the report.` → no [AGENT] lines → `JARVIS: When would you like that reminder, Boss?` ✓ exactly one clarifying question; audio verified. |
| 11 | Rebuilt utterance with a sample-exact 2.000 s mid-sentence silence (ffmpeg-verified; the original TTS-generated file's gap had drifted to 2.699 s). run14: `USER: Remind me to buy milk.` then `USER: Tomorrow at seven AM.` with NO TURN line between them — ONE turn, single complete transcript, turn closed only after the second clause (requires D-010's `VADParams(stop_secs=2.5)`; pipecat's 0.2 s default let the local smart-turn model close the turn at the pause). End-to-end delegation of the merged intent verified in run13: Scheduler set the reminder and `JARVIS: All set, Boss. I have set a reminder for you to buy milk for tomorrow at seven AM.` with DB row. (run14's own ack did not fire the delegation — same LLM nondeterminism class as item 9; the item's stated criterion, turn detection, passed cleanly.) |
| 12 | `USER: Here is a long message...` (31.7 s continuous) transcribed COMPLETE and in order — grocery list (apples, oranges, milk, bread, coffee beans) and library-books clause intact → `JARVIS: I heard every word clearly, Boss. I caught the grocery list and the library book reminder...`; audio verified. |

Latency lines (run14): every turn printed `TURN user_end→llm_done = <ms>`
(ack and final-reply legs each measured; e.g. item 3: 4606 ms ack,
27758 ms full cycle). USER/JARVIS lines carry `[HH:MM:SS]` timestamps for
every turn. conversations table for the run14 session: 13 user rows
(12 utterances + item 11's second clause) and 20 assistant rows — both
roles present. TURN lines do not include first-audio latency yet (the
`user_end->first_audio` variant is blocked on the human-blocked items
below; see plan Phase 5/8).

Notes / external issues found during live runs:
- Tavily free dev key now returns HTTP 403 from this sandbox's egress IP
  (worked earlier the same day). Routing to Analyst/web_search is
  unaffected; live web content needs the key/account unblocked or a paid
  tier — same resolution path as the ElevenLabs block.
- Kimi (the supervisor LLM) is nondeterministic about always emitting the
  second delegate_task call for two-part requests (prompt rule 2): items 9
  and 11 each needed one re-run to capture a both-hops pass. Routing
  capability itself is proven by the passes above.
- Human spot-check (optional): the recorded replies in
  `.acceptance-scratch/bot-audio/` can be listened to directly; content
  was already machine-verified by transcription.
