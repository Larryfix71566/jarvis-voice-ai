# Acceptance checklist — reliable automatic memory + procedures

Manual checklist for `MORTIMER_MEMORY_PROCEDURES_PLAN.md`. Part A
(D1–D8) and Part B (D9–D24, procedures-as-hints) are both implemented.
Requires a live voice session (`./scripts/mortimer.sh`).

## Part A — reliable automatic memory

- [ ] Say an explicit preference ("remember that I prefer metric units").
  Confirm `remember` fires (visible in `logs/bot.log`) and the fact
  appears in the Memory panel immediately, not at session end.
- [ ] Say something vague or one-off ("remind me about the thing later,
  maybe"). Confirm the Supervisor does NOT call `remember` for it — it
  should ask a clarifying question or handle it as a normal request
  instead.
- [ ] Have a session run past 5 minutes without disconnecting. Confirm a
  periodic sweep log line (`memory_updated session=...` from
  `jarvis/memory.py`, or a `memory_sweep_timeout`/`memory_sweep_failed`
  line on failure) appears before session end.
- [ ] Disconnect uncleanly (close the tab) mid-session, past one sweep
  interval (default 300s — temporarily lower
  `JARVIS_MEMORY_SWEEP_INTERVAL_S` for a faster manual check). Confirm the
  last sweep's facts/summary are present even though the teardown path
  never ran.
- [ ] Force a teardown-path timeout (e.g. temporarily set
  `MEMORY_EXTRACTION_TIMEOUT_S` very low in `jarvis/memory.py`, or block
  the LLM endpoint briefly) and disconnect cleanly. Confirm
  `memory_extraction_timeout session=<id>` appears in `logs/bot.log` —
  this is the exact bug D1 fixes: previously this case produced no log
  line at all.
- [ ] Confirm ordinary sessions with no explicit "remember" statement and
  no timeout are completely unaffected — memory still folds in at session
  end as before, no new log noise, no latency regression.

## Part B — procedures as hints

- [ ] Ask the same kind of question of the same specialist three times
  across separate sessions (e.g. three different weather lookups to the
  Analyst). Confirm `sqlite3 data/jarvis.db "select * from procedures"`
  shows one `candidate` row reach `active` on the third success.
- [ ] Confirm a fourth, similar request's sub-agent transcript (via
  `python -m jarvis.runlog --run <id>`, checking the JSONL payload's
  system messages, or temporary debug logging) shows the hint message
  present, prefixed "A similar task has succeeded before:".
- [ ] Force three failures against an active procedure (e.g. temporarily
  break the relevant MCP server or unset a required API key) and confirm
  it flips to `deprecated` and stops being injected on a subsequent
  success.
- [ ] Confirm ordinary delegations to agents/tasks with no matching
  procedure are completely unaffected — no hint message, no latency
  regression.
- [ ] Confirm `JARVIS_PROCEDURES_ENABLED=false` fully disables the
  feature: no hint ever injected, no new candidate ever created, existing
  `procedures` rows left untouched.
- [ ] Confirm a genuinely privileged sub-agent action (e.g. Developer's
  git push confirmation) is never bypassed by a procedure hint — the
  two-phase confirmation flow behaves identically whether or not a hint
  was injected for that task.
