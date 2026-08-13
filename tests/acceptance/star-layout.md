# Star Layout Acceptance Checklist

Manual acceptance for MORTIMER_STAR_LAYOUT_PLAN.md. Run the full stack
(`./scripts/mortimer.sh`) and talk to Mortimer through the web console.
Tick each line.

## Basic layout

- [ ] Five satellites are visible on the field, arranged as a star/pentagon
      with **Developer at the top** (apex).
- [ ] The other four keep their rough pre-existing quadrant: Scheduler
      upper-left, Librarian lower-left, Analyst upper-right, Systems
      lower-right.
- [ ] Each of the five has a beam to the center; the beam lights while
      that agent works and fades after (`beam-live` → `beam-done`).
- [ ] The Developer satellite at the apex does not visually crowd the
      `M.O.R.T.I.M.E.R.` center readout on your screen size. (Plan §5.2
      step 3 — if it does, the fix is reducing the `developer` entry's `y`
      value in `web/src/agentLayout.ts`, nothing else.)

## The bug fix

- [ ] Ask something that routes to **Developer** (e.g. "what's the git
      status?"). Confirm the Developer satellite lights up **and** its
      status card appears anchored near the top satellite. This is the
      original bug — Developer must now be visible and reactive, which it
      was not before this work.

## Anchored positioning

- [ ] Confirm each of the other four agents, when called, produces a card
      anchored near **its own** satellite — not stacked in a fixed corner.
- [ ] Confirm the satellite's pulsing dot + label remain visible while its
      card is shown (the card offsets beside/above per its `cardAnchor`,
      it does not cover the dot).
- [ ] Confirm side-point cards (Analyst, Systems, Librarian, Scheduler)
      extend **inward** toward the center, not off toward the screen edge.

## Concurrency (Phase 4 parallel delegation)

- [ ] Ask a multi-part request hitting two specialists (e.g. "check the
      weather in Paris and remind me to pack an umbrella tomorrow").
      Confirm two cards appear simultaneously at two different satellites
      and do not overlap each other illegibly.

## Developer card content (unchanged, just repositioned)

- [ ] Trigger a self-edit run and confirm the four-stage bar (planning →
      proposing → validating → submitting) still renders correctly inside
      the anchored card at the apex, and the plan/task text is readable.

## Failure and dismissal

- [ ] Cause a sub-agent failure (e.g. ask for weather with
      `TAVILY_API_KEY` unset). Confirm the failed card persists at its
      anchored position until dismissed, and the `×` button is clickable.

## Edge and viewport handling

- [ ] Resize the browser window narrower (staying above 860px width) and
      confirm no anchored card is clipped off-screen or hidden under the
      top or bottom bar.
- [ ] Shrink the window below 860px width. Confirm ALL cards revert to the
      original stacked bottom-left column (not a mix of anchored and
      stacked) and remain fully readable.
- [ ] Resize back above 860px and confirm cards return to anchored
      positioning on the next agent call.

## Regression — shared surfaces

- [ ] Confirm the center readout, live captions, and wake ripple still
      work exactly as before.
- [ ] Confirm ⚙ Repo, ✎ Edit, and 🧠 Memory panels still open/close/function
      normally.
- [ ] Confirm the transcript drawer (T key) still works.

## Visual tuning pass (expected step, not a defect)

- [ ] Review `CARD_WIDTH_PX`, `CARD_GAP_PX`, `VIEWPORT_MARGIN_PX`, and
      `ANCHORED_CARDS_MIN_WIDTH_PX` in `web/src/agentLayout.ts` on a real
      screen and adjust to taste.
