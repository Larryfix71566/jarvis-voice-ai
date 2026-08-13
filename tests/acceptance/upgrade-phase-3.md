# Upgrade Plan Phase 3 Acceptance Checklist — Interruption awareness

Manual acceptance for MORTIMER_INTERFACE_UPGRADE_PLAN.md Phase 3. Run the
full stack (`./scripts/mortimer.sh`) and talk to Mortimer through the web
console. Tick each line.

## Genuine interruptions

- [ ] Ask a question that produces a longer spoken reply, then interrupt
      **mid-sentence** while it's talking. Confirm the *next* reply
      acknowledges the interruption naturally (e.g. "sorry, you cut me off —
      what did you need?") rather than continuing or ignoring it.
- [ ] Ask a question, then interrupt **immediately** — before any audio has
      started playing (i.e. while the LLM/specialist is still "thinking").
      Confirm the next reply's acknowledgment (if any) makes sense for being
      cut off *before* speaking, not mid-speech (the two notice variants in
      `jarvis/prompts.py` should read naturally in each case).

## Negative case (mandatory — no false positives)

- [ ] Complete an entire normal turn without interrupting — ask a question,
      let Mortimer finish speaking completely, then ask a second unrelated
      question. Confirm the second reply shows **no** sign of an
      interruption note (no unprompted "sorry, was I cut off?" or similar).
      This is the important negative case: Flux's `should_interrupt=True`
      broadcasts an `InterruptionFrame` at the start of *every* turn, not
      just genuine barge-ins — `jarvis/bot/interruption.py`'s job is telling
      the two apart.

## Flag behavior

- [ ] Set `JARVIS_INTERRUPTION_NOTICE_ENABLED=false` in `.env`, restart, and
      repeat the mid-sentence interruption test. Confirm no acknowledgment
      appears — behavior should look like Phase 0 (bot stops talking, next
      reply proceeds as if nothing happened).
- [ ] Restore `JARVIS_INTERRUPTION_NOTICE_ENABLED=true` (or unset — default
      is `true`) before further testing.

## Automated coverage

Covered by `tests/unit/test_interruption.py` (6 cases: genuine mid-speech,
genuine while-thinking, disabled flag, upstream-direction dedup, no-double-
count within one turn, and the mandatory no-false-positive negative case).
Also run `RUN_LIVE=1 python -m tests.evals.routing_eval` (must stay ≥90%)
since `jarvis/prompts.py` changed — not run in this sandbox (no network
access to the LLM API); run it from a machine with API access before
merging.
