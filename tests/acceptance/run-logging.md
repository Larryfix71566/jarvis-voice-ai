# Run Logging Acceptance Checklist

Manual acceptance for MORTIMER_RUN_LOGGING_PLAN.md. Run the full stack
(`./scripts/mortimer.sh`) and talk to Mortimer through the web console.
Tick each line.

## Per-agent runs

- [ ] Ask something that routes to each of the five sub-agents in turn.
      Confirm `python -m jarvis.runlog` shows one row per delegation, with
      the correct agent, a non-zero latency, and the task text intact.

## A failing run surfaces detail that was previously lost

- [ ] Cause a sub-agent failure (e.g. ask for weather with
      `TAVILY_API_KEY` unset). Confirm the run shows `status=failed` and
      `python -m jarvis.runlog --run <id>` shows the underlying MCP-layer
      error in its `mcp_call` event — this is the specific gap this plan
      closes (§1.5): before this work, only a bare `FAILED: <type>` string
      was ever visible, nowhere durable.

## Parallel delegation

- [ ] Ask a multi-part request hitting two specialists at once (e.g.
      "check the weather in Paris and remind me to pack an umbrella
      tomorrow"). Confirm two distinct runs appear, each with its own
      `run_id`, tool events, and JSONL payload — no cross-contamination
      between the two (this is the regression scenario for D3/the
      ContextVar fix).

## Log rotation

- [ ] Note the contents of `logs/bot.log`. Restart Mortimer
      (`./scripts/mortimer.sh`). Confirm `logs/bot.log.1` now holds the
      previous session's content and `logs/bot.log` starts fresh (not
      wiped — this was the pre-existing bug D11 fixes).
- [ ] Restart four more times. Confirm `logs/bot.log.1` through `.5` exist
      and the oldest generation is dropped, not accumulated forever.

## CLI

- [ ] `python -m jarvis.runlog` lists recent runs in a readable table.
- [ ] `python -m jarvis.runlog --status failed` surfaces the failure above.
- [ ] `python -m jarvis.runlog --agent developer --since 1d` filters as
      expected.
- [ ] `python -m jarvis.runlog --run <run_id>` prints the full event and
      payload detail for one run.
- [ ] `python -m jarvis.runlog --json` produces valid JSON.

## Console Runs panel

- [ ] Click "📋 Runs" in the topbar. Confirm the panel opens and lists the
      same runs the CLI sees.
- [ ] Filter by agent and by status; confirm the list updates.
- [ ] Click a run row; confirm it expands to show events and the full
      JSONL payload, matching `python -m jarvis.runlog --run <id>`.
- [ ] Confirm there is no delete button and no re-run button (plan D15 —
      this panel is read-only by design).

## Retention

- [ ] Set `JARVIS_RUNLOG_RETENTION_DAYS=0` in `.env`, restart, confirm the
      startup log line shows `runs_deleted=0 dirs_deleted=0` even with old
      runs present (pruning disabled).
- [ ] Restore a normal retention value (e.g. `30`) and confirm a future
      restart's log line reports real counts once runs exist that are
      older than the window (this may require temporarily setting a very
      small retention value like `1` against a manually backdated test
      run, or simply confirming the log line appears with zero counts on
      a fresh install).

## Kill switch

- [ ] Set `JARVIS_RUNLOG_ENABLED=false` in `.env`, restart. Trigger a
      delegation. Confirm no new row appears in `agent_runs` and no new
      file appears under `logs/agents/`, and — critically — confirm the
      delegation itself still works normally (the sub-agent still
      responds; only logging is disabled). Restore `true` afterward.

## Regression — shared surfaces

- [ ] Confirm the star layout (five satellites, anchored status cards)
      still behaves exactly as before this work.
- [ ] Confirm ⚙ Repo, ✎ Edit, and 🧠 Memory panels still open/close/function
      normally.
- [ ] Confirm the transcript drawer (T key) still works.
- [ ] Confirm long-term memory extraction (`update_memory_from_session`)
      still runs at session end without errors in `logs/bot.log`.
