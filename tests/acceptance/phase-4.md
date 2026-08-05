# Phase 4 Acceptance Checklist — Voice In ("The Spoken Dozen")

Setup: `./scripts/run_bot.sh`, open `http://localhost:7860/client`, click
Connect, allow the mic. Server log must show `[session]` and greeting turn.

Speak each utterance; tick when the server log shows a correct transcript
AND correct agent activity. Tolerances: wording drift OK; named entities
(times, cities, "swordfish") must be exact. If STT consistently mangles a
word, add it to the Deepgram `keywords` setting (allowed wiring tuning).

- [ ] 1. "Hello Jarvis." → transcript correct, no [AGENT] lines
- [ ] 2. "What time is it?" → Scheduler
- [ ] 3. "Remind me to stretch in two hours." → Scheduler; row in reminders
- [ ] 4. "Save a note that the wifi password is swordfish." → Librarian; row in notes
- [ ] 5. "What did I save about wifi?" → Librarian recall, "swordfish" in reply
- [ ] 6. "What's the weather in Tokyo?" → Analyst
- [ ] 7. "Search the web for today's top tech news." → Analyst
- [ ] 8. "How's my computer doing?" → Systems
- [ ] 9. "Check the weather in Paris and remind me to pack an umbrella
      tomorrow morning." → Analyst + Scheduler
- [ ] 10. "Remind me about the report." → clarifying question, NO agent
- [ ] 11. Pause 2 s mid-sentence, then continue → turn detection did NOT fire
      early; single complete transcript
- [ ] 12. Long utterance (≥ 30 s continuous) → transcript complete, in order

## Latency lines
- [ ] Every turn prints `TURN user_end→llm_done = <ms>` in the server log
- [ ] USER/JARVIS lines printed with timestamps for every turn
- [ ] Both roles present in the conversations table for the session_id

## Notes
- Manual (requires mic + browser). Automated wiring coverage:
  tests/integration/test_bot_wiring.py (processor order, delegate_task
  registration, flux model, transcript persistence).
