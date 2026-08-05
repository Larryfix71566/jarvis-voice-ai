# Phase 2 Acceptance Checklist — The Brain (Text)

Prereq: `.env` contains a working LLM key (`RUN_LIVE=1` tests + this CLI
checklist need it). Run `python -m jarvis.cli` and perform each turn.

## Automated
- [x] `pytest tests/unit -q` — all green
- [x] `pytest tests/integration -q` — registry integration green
- [ ] `RUN_LIVE=1 pytest tests/integration -q` — green (needs keys; run at gate)

## Manual CLI script (needs LLM key — DEFERRED until keys arrive)
- [ ] 1. "Hello" — brief greeting, no tool call in logs
- [ ] 2. "What time is it?" — calls `get_current_time`, states correct time
- [ ] 3. "Save a note titled Test with body abc, tag smoke" — confirms save
- [ ] 4. "Search my notes for smoke" — recalls the note from turn 3
- [ ] 5. "Set a reminder to stretch in 2 hours" — row exists in DB with sane due_at
- [ ] 6. "What reminders are pending?" — lists the stretch reminder
- [ ] 7. "What's the weather in Tokyo?" — analyst-quality answer via tools
- [ ] 8. Multi-tool: "Note that my dentist is Dr. Patel, and remind me to call him tomorrow at 9am" — both stored
- [ ] 9. `/tools` — lists 19 tools grouped by the 5 servers
- [ ] 10. `/reset` then "what note did I just save about smoke?" — should NOT recall prior context (new session), but Librarian-style search still finds the note via tools
- [ ] Each turn prints a gray `[<ms>]` latency line and logs `turn_complete ...`
- [ ] `/quit` exits cleanly with no traceback
