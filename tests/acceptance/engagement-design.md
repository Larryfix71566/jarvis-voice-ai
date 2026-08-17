# Engagement Design Acceptance Checklist

Manual acceptance for MORTIMER_ENGAGEMENT_DESIGN_PLAN.md. Restart the
full stack (`./scripts/mortimer.sh` — the sidecar gained `/api/ambient`)
and hard-refresh the console.

## Phase 1 — "alive"

### E2 boot sequence

- [ ] Click Connect: the readout letters cascade in, the satellites
      light in sequence, the wave rises from flatline, and one soft
      chirp plays. Total ~2 seconds.
- [ ] Disconnect and reconnect: the sequence replays (every connect is
      an arrival).
- [ ] With system reduced-motion enabled: everything appears instantly;
      the chirp still plays.

### E1 states

- [ ] Ask Mortimer to prepare (not confirm) a commit: once the draft
      appears in Output, the topbar toggle dot and the Output tab dot
      turn AMBER and the M.O.R.T.I.M.E.R. readout gains an amber glow.
- [ ] Confirm (or ask for anything else that lands in Output): amber
      clears back to cyan on the next result.
- [ ] Ask a question that takes a moment: the state label reads
      "Thinking" with a slow-shimmering dot between your question and
      the reply starting; it never shows while Mortimer is audibly
      speaking.

### E3 sounds

- [ ] Delegation plays a faint tick; a successful result plays a soft
      two-note tone; a failure (or the error banner) plays a low tone.
- [ ] The 🔊 bottombar button silences everything; toggling back on
      plays the boot chirp as confirmation; the preference survives a
      reload.

### E4 ambient strip

- [ ] While connected, the top-left shows a clock chip (updates
      by the minute).
- [ ] Set a reminder by voice: within a minute the ⏰ chip shows it
      with its relative due time.
- [ ] Ask for the weather: after the answer, the weather chip shows the
      answer title with its age, and persists across reloads.
- [ ] A session-summary chip appears when a running summary exists.
- [ ] Stop the admin sidecar: the reminder/summary chips disappear
      quietly (no error surface); clock and weather remain.
- [ ] Before Connect: no ambient strip at all.

## Phase 2 — "instruments" (pending implementation)

- [ ] Satellites: last-run ✓/✗ tick, hover shows last task, click opens
      Runs pre-filtered to that agent.
- [ ] Memory panel renders as grouped dossier cards with per-fact
      forget and observation promotion progress.
- [ ] The Log interleaves "→ Agent" / "✓ Agent" chips at the right
      points in the conversation.
- [ ] Empty-state hints appear on the stage (before first exchange) and
      in empty Runs/Output tabs, and nowhere else.

## Gates

- [ ] `pytest tests/unit tests/integration -q` green.
- [ ] `cd web && npm run build && npm run lint` clean.
