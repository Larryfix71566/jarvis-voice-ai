# Model discipline — acceptance checklist

MORTIMER_MODEL_DISCIPLINE_AND_MAC_SHELL_PLAN.md Part A (and Part C, C1/C2,
below). Manual, run
against a live stack (`./scripts/mortimer.sh`) with `MOONSHOT_API_KEY`
(or whichever key the developer's `model_profile` points to) set. Not
run by pytest. **The bot must be restarted after this change** —
prompt and `agents.yaml` are read at boot.

- [ ] A1: `python -m jarvis.runlog --agent developer --limit 5` shows
      the `model` column as the resolved profile's model string (e.g.
      `kimi-k3`), not the voice model, on new runs.
- [ ] A1 fallback: temporarily unset the profile's API key env var,
      restart, delegate to developer — the run still completes (on the
      voice model), and the bot log shows
      `subagent_model_profile_fallback agent=developer profile=kimi-k3`.
- [ ] A3: "make the upper-left updates dismissible" (or similar,
      referencing `AmbientStrip.tsx`) — the developer finds the right
      component without exhausting its 5-iteration budget on repo
      exploration first.
- [ ] A2: force a developer failure (e.g. ask for something that will
      genuinely fail), then immediately ask for a reworded version of
      the same thing — Mortimer's spoken reply reports the failure and
      asks how to proceed, with no second delegation attempt. Re-run
      the exact original wording once more — same result (no retry).
- [ ] A2: ask for something genuinely different right after a failure —
      it delegates and runs normally (not refused).
- [ ] A2: after a SUCCESSFUL delegation to developer, a later failure-
      then-retry sequence is evaluated fresh (no stale guard state from
      the earlier success).
- [ ] Full `pytest tests/unit tests/integration -q` clean.
- [ ] `RUN_LIVE=1 python -m tests.evals.routing_eval` still scores
      ≥ 90% (no eval cases changed in Part A, but a supervisor prompt
      edit warrants a spot check).

## Part C: investigator + pytest validation gate

- [ ] C1: ask Mortimer (routed to developer) "how did the last few
      developer runs go?" — it calls `runlog_list`/`runlog_stats`
      itself rather than asking the user to read logs, and the reply
      reflects real run data (spot-check against
      `python -m jarvis.runlog --agent developer --limit 5`).
- [ ] C1: ask about a specific past council round ("what did the
      escalation council decide last time?") — `council_list` surfaces
      it.
- [ ] C1: `python -m mcp_servers.mcp_runlog.server < /dev/null` prints
      the FastMCP startup banner to stderr and exits only on EOF/kill —
      confirms the `mcp.run()` entrypoint is present (its absence is
      what caused the original registry regression: the process would
      import cleanly and exit 0 with no banner, surfacing as a
      same-looking `Connection closed` error on the NEXT server in
      `config/mcp_servers.yaml`, not on this one).
- [ ] C2: start a self-edit session, propose an edit that breaks a
      backend unit test on purpose, run `validate()` — the `pytest`
      check fails and `submit()` refuses ("validation has not passed").
      Fix the test, re-validate, confirm `submit()` proceeds.
- [ ] C2: confirm `.github/workflows/validate.yml`'s `Unit tests` step
      has no `continue-on-error` — a broken backend test now fails the
      PR check, not just a warning.
