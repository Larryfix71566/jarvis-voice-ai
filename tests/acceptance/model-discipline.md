# Model discipline — acceptance checklist

MORTIMER_MODEL_DISCIPLINE_AND_MAC_SHELL_PLAN.md Part A. Manual, run
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
