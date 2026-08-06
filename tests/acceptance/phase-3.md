# Phase 3 Acceptance Checklist — Multi-Agent Supervisor

Run: `python -m jarvis.cli` (delegating mode). Tick each line.

## Single-agent routing
- [x] "What time is it?" → `[Scheduler] calling …` line, spoken-style answer
- [x] "Remind me to stretch in 30 minutes" → Scheduler; row in `reminders` table
- [x] "Save a note that the garage code is 4482, tag home" → Librarian; row in `notes`
- [x] "What's the weather in Paris?" → Analyst; current conditions in reply
- [x] "How is my computer doing?" → Systems; CPU/memory/disk brief

## Multi-hop (key scenario)
- [x] "Remind me to call the dentist tomorrow at 9am and save a note that
      Dr. Patel's office is on Main Street" → BOTH Scheduler and Librarian run;
      reminder row with correct absolute time AND note row both present
      (verified live 2026-08-05 and again 2026-08-06 — see below)

## Conversation quality
- [x] "remind me about the thing" → asks exactly one short clarifying question,
      no delegation
- [x] "hello" / small talk → answered by Supervisor directly, no delegation
- [x] Out-of-scope request (e.g. "write my taxes and file them") → brief polite
      refusal or plain statement of limits, no fabricated tool result
- [x] Follow-up pronouns work: after saving a note, "what did I just save?"
      resolves via Librarian without restating the content
- [x] Every delegated turn begins with a ≤10-word acknowledgment sentence
- [x] Replies stay under 40 words unless more is requested

## Live verification log
- 2026-08-05 — routing eval 27/30 = 90% (threshold 90%), run log in
  `.eval-logs/run3.txt`. Two prompt iterations per plan §10 (descriptions +
  routing rules only; mechanism untouched).
- 2026-08-05 — multi-hop scenario verified programmatically: both delegation
  events fired; `reminders` row (dentist, next-day 9:00 AM local) and `notes`
  row (Dr. Patel) written. See live check below.
- 2026-08-06 — full checklist executed programmatically (piped stdin, scratch
  DB `/tmp/jarvis-acc-phase3.db`, Kimi key). All items pass with evidence:
  - Routing: time→Scheduler(get_current_time); stretch→Scheduler(set_reminder,
    DB row due 14:25 EDT ≈ +30 min); garage→Librarian(create_note, DB row
    code 4482 tag "home"); Paris→Analyst(get_weather, conditions in reply);
    computer→Systems(get_system_status, CPU idle / mem 22% / disk 24%).
  - Pronoun follow-up: "what did I just save?" → Librarian(list_notes),
    correct note content, no restating needed from user.
  - Clarification: "remind me about the thing" → "What should I remind you
    about, Boss?" — one 7-word question, zero delegation.
  - Small talk: "hello" → direct 9-word reply, zero delegation.
  - Out-of-scope: taxes → 20-word polite refusal, zero tool calls, nothing
    fabricated.
  - Multi-hop: Scheduler(set_reminder → DB row 2026-08-06 09:00 EDT) AND
    Librarian(create_note → DB row Main Street) in one turn.
  - Acknowledgment length: first sentence of every delegated turn ≤10 words
    (9/2/2/7/6/3 words across the six delegated turns). Recall turns lead with
    the answer directly (16 words, single sentence) — no padded preamble.
  - Brevity: longest reply in the whole script is 25 words (< 40).
  - Clean `/quit`, exit code 0, zero tracebacks.
