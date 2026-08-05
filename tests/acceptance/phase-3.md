# Phase 3 Acceptance Checklist — Multi-Agent Supervisor

Run: `python -m jarvis.cli` (delegating mode). Tick each line.

## Single-agent routing
- [ ] "What time is it?" → `[Scheduler] calling …` line, spoken-style answer
- [ ] "Remind me to stretch in 30 minutes" → Scheduler; row in `reminders` table
- [ ] "Save a note that the garage code is 4482, tag home" → Librarian; row in `notes`
- [ ] "What's the weather in Paris?" → Analyst; current conditions in reply
- [ ] "How is my computer doing?" → Systems; CPU/memory/disk brief

## Multi-hop (key scenario)
- [ ] "Remind me to call the dentist tomorrow at 9am and save a note that
      Dr. Patel's office is on Main Street" → BOTH Scheduler and Librarian run;
      reminder row with correct absolute time AND note row both present
      (verified live 2026-08-05 — see below)

## Conversation quality
- [ ] "remind me about the thing" → asks exactly one short clarifying question,
      no delegation
- [ ] "hello" / small talk → answered by Supervisor directly, no delegation
- [ ] Out-of-scope request (e.g. "write my taxes and file them") → brief polite
      refusal or plain statement of limits, no fabricated tool result
- [ ] Follow-up pronouns work: after saving a note, "what did I just save?"
      resolves via Librarian without restating the content
- [ ] Every delegated turn begins with a ≤10-word acknowledgment sentence
- [ ] Replies stay under 40 words unless more is requested

## Live verification log
- 2026-08-05 — routing eval 27/30 = 90% (threshold 90%), run log in
  `.eval-logs/run3.txt`. Two prompt iterations per plan §10 (descriptions +
  routing rules only; mechanism untouched).
- 2026-08-05 — multi-hop scenario verified programmatically: both delegation
  events fired; `reminders` row (dentist, next-day 9:00 AM local) and `notes`
  row (Dr. Patel) written. See live check below.
