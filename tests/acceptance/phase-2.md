# Phase 2 Acceptance Checklist — The Brain (Text)

Prereq: `.env` contains a working LLM key (`RUN_LIVE=1` tests + this CLI
checklist need it). Run `python -m jarvis.cli` and perform each turn.

## Automated
- [x] `pytest tests/unit -q` — all green
- [x] `pytest tests/integration -q` — registry integration green
- [x] `RUN_LIVE=1 pytest tests/integration -q` — green (needs keys; run at gate)

## Manual CLI script (needs LLM key — DEFERRED until keys arrive)
- [x] 1. "Hello" — brief greeting, no tool call in logs
- [x] 2. "What time is it?" — calls `get_current_time`, states correct time
- [x] 3. "Save a note titled Test with body abc, tag smoke" — confirms save
- [x] 4. "Search my notes for smoke" — recalls the note from turn 3
- [x] 5. "Set a reminder to stretch in 2 hours" — row exists in DB with sane due_at
- [x] 6. "What reminders are pending?" — lists the stretch reminder
- [x] 7. "What's the weather in Tokyo?" — analyst-quality answer via tools
- [x] 8. Multi-tool: "Note that my dentist is Dr. Patel, and remind me to call him tomorrow at 9am" — both stored
- [x] 9. `/tools` — lists 19 tools grouped by the 5 servers
- [x] 10. `/reset` then "what note did I just save about smoke?" — should NOT recall prior context (new session), but Librarian-style search still finds the note via tools
- [x] Each turn prints a gray `[<ms>]` latency line and logs `turn_complete ...`
- [x] `/quit` exits cleanly with no traceback

## Live verification log
- 2026-08-06 — full script executed programmatically (piped stdin, scratch DB
  `/tmp/jarvis-acc-phase2.db`, Kimi key). All 12 items pass with evidence:
  - Turn 1: greeting, zero tool calls.
  - Turn 2: `[Scheduler] calling get_current_time`; reply "1:49 PM EDT"
    cross-checked against system clock (17:49 UTC) — exact.
  - Turn 3: `notes` row {title: Test, body: abc, tags: smoke} verified in DB.
  - Turn 4: `search_notes` recall, note content in reply.
  - Turn 5: `reminders` row due 15:50 EDT (= 13:50 + 2h); turn 6 lists it.
  - Turn 7: `[Analyst] calling get_weather`; Tokyo conditions in reply.
  - Turn 8: BOTH `create_note` and `set_reminder` fired; note row (Dr. Patel)
    and reminder row (next-day 09:00 EDT) both verified in DB.
  - `/tools`: exactly 19 tools across mcp-time(4), mcp-notes(6),
    mcp-reminders(5), mcp-web(2), mcp-system(2).
  - Post-reset recall used `search_notes`+`get_note` (tool path, new session).
  - Every conversational turn printed `[<ms>]` and logged `turn_complete`.
  - Exit code 0, no traceback in the run log.
