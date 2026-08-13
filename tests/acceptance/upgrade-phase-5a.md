# Upgrade Plan Phase 5a Acceptance Checklist — Session search (FTS5)

Manual acceptance for MORTIMER_INTERFACE_UPGRADE_PLAN.md Phase 5a. Run the
full stack (`./scripts/mortimer.sh`) and talk to Mortimer through the web
console. Tick each line.

## Recall from an old session

- [ ] Hold a conversation mentioning something specific and memorable that
      you do NOT explicitly ask Mortimer to save as a note (e.g. mention a
      specific person's name and a detail about them in passing). End the
      session.
- [ ] In a NEW session, days or at least hours later (or immediately, if
      testing), ask "what did we talk about regarding <that detail>?" or
      "did I mention anything about <name> before?"
- [ ] Confirm the Librarian finds and reports the detail, citing it came
      from a past conversation (not a saved note) — check `logs/bot.log`
      for a `search_sessions` tool call in the Librarian's trace.

## Fact-store overflow case (why this phase exists)

- [ ] If you have more than ~30 facts accumulated (check `memories` table
      row count for `kind='fact'`), confirm something discussed many
      sessions ago — old enough to have fallen out of the `MAX_FACTS`
      window in `render_memory_context` — is still recallable via
      `search_sessions`, proving this phase actually restores reachability
      that the facts-only path lost.

## Negative case

- [ ] Ask about something that was genuinely never discussed. Confirm
      Mortimer says it doesn't have that information, rather than
      hallucinating or returning an unrelated snippet.

## Routing note

This phase deliberately did NOT change `jarvis/prompts.py` (the Librarian's
sub-agent prompt still only names `search_notes` explicitly) to avoid
requiring the routing eval gate in a sandbox with no LLM API access. Tool
discovery relies on the `search_sessions` tool's own description being
clear enough for the model to reach for it unprompted.

- [ ] If the Librarian does NOT reach for `search_sessions` on a query that
      clearly calls for it (e.g. "what did we discuss last week"), that's a
      signal the prompt should be updated to mention it explicitly
      (`jarvis/prompts.py` `SUBAGENT_PROMPTS["librarian"]`) — run
      `RUN_LIVE=1 python -m tests.evals.routing_eval` afterward if you do.

## Automated coverage

`tests/unit/test_mcp_notes_logic.py::TestSearchSessions` (10 cases,
including FTS5 special-character safety and delete-trigger sync) and
`tests/integration/test_mcp_servers.py::test_mcp_notes_search_sessions_over_stdio`
(real stdio round trip). `scripts/check_skills.py` passes.
