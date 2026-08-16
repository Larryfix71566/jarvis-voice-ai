# Voice UI Control Acceptance Checklist

Manual acceptance for MORTIMER_VOICE_UI_PLAN.md. Run the full stack
(`./scripts/mortimer.sh`), connect, and speak each command. The hybrid
feedback rule (U5) is under test everywhere: a command that visibly
changes something should produce NO spoken comment; a command that
changes nothing should produce exactly one short spoken sentence.

## Drawer + tabs (Tier 1 — the headline symptom)

- [ ] "Open the drawer" — drawer opens; Mortimer says NOTHING about it.
- [ ] "Close the drawer" — closes, silently.
- [ ] "Open the drawer" while already open — one short spoken sentence
      ("already open"), nothing else changes.
- [ ] Each tab by name: "show me the runs", "open the edit panel",
      "show my memory", "open the repo panel", "show the developer
      status", "show the output" — drawer opens to the right tab.
- [ ] "Switch to the memory tab" while the drawer shows memory — spoken
      "already showing".

## Transcript (Tier 1)

- [ ] "Show the log" / "show the transcript" — transcript drawer opens
      (and the side drawer closes, per the existing D17 rule).
- [ ] "Hide the log" — closes, silently.
- [ ] "Hide the log" again — spoken "already closed".

## Display windows (Tier 1 / U3 / U4)

- [ ] Ask for the weather with no popup open — the answer appears in the
      frosted in-page overlay: translucent (wave/satellites visible
      through it), never more than ~40% of the screen, content scrolls
      inside it if long.
- [ ] The overlay PERSISTS (no auto-dismiss). "Close that" dismisses it,
      silently.
- [ ] "Close that" with nothing showing — spoken "nothing to dismiss".
- [ ] "Put that on the other screen" — the popup window opens with the
      payload; the in-page overlay disappears (no double display).
- [ ] Ask another informational question — the answer goes straight to
      the popup, not the overlay (implicit dual-screen mode).
- [ ] "Show it here" / "close the display window" — popup closes, the
      payload falls back to the in-page overlay.
- [ ] Reload the console with the popout preference on — a new
      informational answer re-opens the popup automatically (the
      existing auto-reopen behavior, now voice-set).

## Mic + wake word (Tier 2)

- [ ] "Stop listening" — mic mutes, Mortimer gives a ONE-PHRASE
      sign-off (e.g. "Going quiet"), then nothing further.
- [ ] Confirm no voice command works while muted (expected — U7), and
      the wake word or mic button brings it back.
- [ ] "Turn on the wake word" (sidecar running) — wake word arms,
      silently. "Turn off the wake word" — disarms, silently.
- [ ] "Turn on the wake word" with the sidecar NOT running — one spoken
      sentence about it being unavailable; nothing crashes.

## Feedback discipline (U5)

- [ ] Across all of the above, Mortimer never narrates a successful UI
      action ("I've opened the drawer for you") — silence on success is
      the contract.
- [ ] Mortimer never calls ui_control unprompted (watch a few ordinary
      exchanges — no drawer/tab changes you didn't ask for).
- [ ] "Add a button to the topbar" still delegates to developer (a
      BUILD change, not a view change — the rule 8 boundary).

## Buttons unaffected

- [ ] After a session of voice commands, every topbar button, tab, ⧉,
      and mic control still behaves exactly as before (voice and click
      share the same setters).

## Kill switch (U6)

- [ ] `JARVIS_UI_CONTROL_ENABLED=false` in `.env`, restart. "Open the
      drawer" gets a brief conversational reply (no tool, no crash);
      buttons unaffected. Restore `true`.

## Gates

- [ ] `RUN_LIVE=1 python -m tests.evals.routing_eval` ≥ 90% including
      the 10 new UI cases (which must NOT delegate to developer).
- [ ] `pytest tests/unit tests/integration -q` green;
      `cd web && npm run build && npm run lint` clean.
