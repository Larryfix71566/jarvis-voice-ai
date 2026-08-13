# Upgrade Plan Phase 4 Acceptance Checklist — Parallel delegation

Manual acceptance for MORTIMER_INTERFACE_UPGRADE_PLAN.md Phase 4. Run the
full stack (`./scripts/mortimer.sh`) and talk to Mortimer through the web
console. Tick each line.

## Multi-part request

- [ ] Ask a multi-part request that maps to two different specialists, e.g.
      "Check the weather in Paris and remind me to pack an umbrella
      tomorrow." Confirm BOTH specialists' results land in the single
      combined reply (Supervisor prompt rule 2 already requires this
      regardless of concurrency).
- [ ] Watch the **AgentStatusPanel** (status cards) while that request runs.
      Confirm **two cards appear and are both "working" at the same time**
      — not one finishing before the other starts.
- [ ] Watch the **OrbField satellites** (Scheduler/Librarian/Analyst/Systems
      dots + beams) during the same request. Confirm **two satellites light
      up simultaneously** (both beams `beam-live` at once), not sequentially.

## Timing

- [ ] Re-run the exact multi-part request used in the Phase 0.5 baseline
      timing measurement. Compare `TURN user_end->first_audio` (from
      `logs/bot.log` via `scripts/latency_probe.py`) against the Phase 0.5
      serial baseline. Record before/after here:
      - Phase 0.5 baseline (serial): ______ ms
      - Phase 4 (concurrent): ______ ms

## Failure isolation

- [ ] Temporarily break one specialist (e.g. unset `TAVILY_API_KEY` to make
      the Analyst fail) and ask a multi-part request that hits both the
      broken specialist and a healthy one. Confirm the healthy specialist's
      result still comes back normally and only the broken one is reported
      as failed — the healthy result must not be delayed or lost.

## Cap

- [ ] Set `JARVIS_MAX_PARALLEL_DELEGATIONS=1` in `.env`, restart, and repeat
      the multi-part request. Confirm it still works correctly (both
      results present) but the two status cards no longer overlap in time
      — the second starts only after the first finishes.
- [ ] Restore `JARVIS_MAX_PARALLEL_DELEGATIONS=3` (or unset — default is
      `3`) before further testing.

## Automated coverage

Covered by `tests/unit/test_delegate.py::TestParallelDelegation` (5 cases:
two independent delegations measurably overlap in wall-clock time, one
failure doesn't affect its sibling, `max_parallel=1` forces strictly serial
execution, `max_parallel=2` produces bounded 2-wide batching, and the
`DEFAULT_MAX_PARALLEL_DELEGATIONS` constant stays in sync with
`Settings.jarvis_max_parallel_delegations`'s default).
