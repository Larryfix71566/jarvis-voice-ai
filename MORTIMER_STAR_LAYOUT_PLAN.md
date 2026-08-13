# Mortimer Console — Five-Agent Star Layout + Anchored Status Cards

Status: **APPROVED 2026-08-12 by Larry — not yet started, implementation deliberately deferred.** All design decisions in §3 and all values in §5 are settled and approved as written. No step has been executed yet.

Date drafted: 2026-08-12

---

## §0 Constraints for the implementing model

Read this section before anything else. It is binding.

1. **Every design decision in this document is already made.** Do not substitute your own judgment on layout, colors, wording, geometry, or component structure. Where a number is given, use that number. Where a name is given, use that name. If you believe a decision is wrong, stop and say so — do not silently deviate.
2. **Values marked `⚙ TUNING KNOB` are expected to be adjusted by Larry after seeing it on screen.** Implement them at the stated starting value, and place them where §6 says so they are adjustable in one spot. Do not pre-tune them yourself.
3. **This is a frontend-only change.** No Python, no backend, no config schema, no prompt changes. `jarvis/prompts.py` is NOT touched, so the routing eval is not required.
4. **The status card's *content* does not change.** This work moves cards and adds a fifth agent. The card's internal markup (task text, tool chips, self-edit stage bar, elapsed timer, dismiss button, failure detail) stays exactly as it is today. Do not redesign the card body.
5. **Additive CSS only, matching existing conventions.** New rules go in the existing stylesheets named in each step. Do not restructure or reformat unrelated CSS.
6. **Do not change the sub-agent roster anywhere else.** `config/agents.yaml` already has all five agents and is correct. The bug is frontend-only.

---

## §1 Background: what is actually wrong today

Findings from reading the code, not assumptions:

**The missing Developer is a frontend drift bug.** `web/src/components/OrbField.tsx` hardcodes its own satellite roster:

```ts
const AGENTS = [
  { key: "scheduler", label: "Scheduler", x: 17, y: 24 },
  { key: "librarian", label: "Librarian", x: 17, y: 74 },
  { key: "analyst",   label: "Analyst",   x: 83, y: 24 },
  { key: "systems",   label: "Systems",   x: 83, y: 74 },
];
```

Four entries. `config/agents.yaml` has five (`scheduler`, `librarian`, `analyst`, `systems`, `developer`). The backend has always been correct — it emits `delegate_start`/`delegate_done` events for `developer` like any other agent, and `AgentStatusPanel` already renders a card for it. Only the satellite field is missing it. Nothing else is broken.

**Status cards are position-fixed in a corner, unrelated to which agent fired.** `web/src/agentstatus.css`:

```css
.agent-status {
  position: fixed;
  left: 16px;
  bottom: 72px;
  z-index: 25;
  ...
}
```

Every card for every agent stacks in that one bottom-left column. Since Phase 4 (parallel delegation) made concurrent sub-agent runs real, two or three unrelated cards now pile up in that corner with no spatial connection to the agent that produced them.

**Two structural facts that constrain the solution** (both verified by reading the CSS, and both are the reason the "obvious" approach does not work):

- `.orb-field` sets `overflow: hidden`. Any card rendered *inside* the orb field would be clipped at the field's edges.
- `.main` sets `position: relative; z-index: 1`, which creates a **stacking context**. `.topbar` and `.bottombar` are siblings of `.main` at `z-index: 2`. Therefore anything nested inside `.main` — no matter how high its own `z-index` — paints *below* the top and bottom bars. Cards moved inside `.orb-field` would be occluded by the bars near the top and bottom of the screen.

**Consequence (this is the key architectural decision, already made):** `AgentStatusPanel` **must stay outside `.main`** as a `position: fixed` layer at `z-index: 25`, exactly where it is in the DOM today. It cannot simply be moved inside `OrbField` to inherit the percentage coordinate space. Instead, the satellite geometry must be **shared between the two components**, and `AgentStatusPanel` must convert satellite percentages into viewport pixels using the measured on-screen rect of `.orb-field`.

**One more useful fact:** the beam SVG uses `viewBox="0 0 100 100" preserveAspectRatio="none"`, so beam endpoint coordinates are in the same 0–100 space as the satellites' CSS percentages and stretch identically. This means **the beams need no math changes** — they keep working automatically once the positions table changes.

---

## §2 What we are building

1. **Five satellites in a radial pentagon** (apex at top), replacing the four-corner layout. Each keeps its straight beam to the center that lights while that agent works — same mechanic as today, five points instead of four.
2. **Status cards anchored to their agent's satellite** instead of stacking bottom-left. A card appears offset beside/above its satellite, leaving the small pulsing dot + label visible.
3. **Cards clamped into the viewport** so a card near an edge nudges back on-screen rather than clipping.
4. `AgentStatusPanel` remains a **separate component with its own purpose** — it is where Larry reads a Developer-produced implementation plan, and its card content is unchanged. This work changes *where* cards appear, not *what* they contain.

Explicitly **not** in scope: merging the card into the satellite chip; changing card content; changing the ambient satellite dot/label design; any backend change.

---

## §3 Decisions already made (with rationale)

Recorded so the implementer does not re-litigate them, and so a future reader knows why.

| # | Decision | Rationale |
|---|---|---|
| D1 | Radial pentagon (5 points spoking to center), **not** a literal pentagram | The beam metaphor is "satellite → center, lit while working." A pentagram connects point-to-point and would break that meaning. Confirmed with Larry. |
| D2 | Satellite positions stay **hardcoded in the frontend**, not derived from `config/agents.yaml` | Positions are hand-tuned geometry, not data. Deriving names from config would couple layout math to config content for a roster that changes rarely. Mitigated by D3 (single source) and §7 (a test that fails if the roster drifts again). |
| D3 | A **single shared module** owns the agent roster + positions; both `OrbField` and `AgentStatusPanel` import it | This drift bug happened *because* the roster was duplicated. Two components now need the same geometry; giving them one source prevents recurrence. |
| D4 | `AgentStatusPanel` stays **outside `.main`**, `position: fixed`, `z-index: 25` | Forced by the stacking-context and `overflow: hidden` findings in §1. Moving it inside would put cards under the top/bottom bars and clip them. |
| D5 | Percentage coordinates (stretch with aspect ratio), **not** aspect-corrected geometry | The existing four-corner layout already stretches, and the beam SVG uses `preserveAspectRatio="none"` to match. Aspect-correcting would require changing the beam SVG too. **Accepted consequence: on a wide screen the pentagon reads as a wide, slightly flattened star, not a geometrically regular one.** The §6 radius knobs let Larry adjust how pronounced this is. |
| D6 | Developer takes the **top (apex)** position | It is the new one and the most prominent slot; its card is the tallest (self-edit stage bar), and the apex has the most clear vertical room. |
| D7 | The other four agents **keep their existing rough quadrant** | Scheduler stays upper-left, Librarian lower-left, Analyst upper-right, Systems lower-right. Minimizes relearning for a user who already reads this field at a glance. |
| D8 | Cards **auto-appear while working** (no click), and disappear on the existing done-fade | Consistent with the rest of this hands-free, voice-first interface — nothing else here requires a click. This is the behavior today; it is preserved. |
| D9 | Card offsets are an **explicit per-agent table**, not a computed radial algorithm | A radial-outward algorithm produces bad results at the apex (collides with topbar) and at the side points (overflows the viewport edge). Five explicit entries are deterministic and tunable. |
| D10 | Off-screen protection is a **final clamp**, applied after offset | Simple, deterministic, and handles every edge case including narrow windows, without per-point special-casing. |
| D11 | Card width shrinks from `360px` to `300px` | Five anchored cards need to coexist; two adjacent lower points are ~40% of field width apart, and 360px cards would overlap on common laptop widths. |
| D12 | The mobile/narrow breakpoint **falls back to today's stacked bottom-left column** | Below `860px` the satellite labels are already hidden and the field is too small for five anchored cards. Anchoring there would be unreadable. |

---

## §4 Files that will change

| File | Change |
|---|---|
| `web/src/agentLayout.ts` | **NEW.** Single source of truth: agent roster, pentagon positions, card offsets, tuning knobs, and the `.orb-field` rect publisher. |
| `web/src/components/OrbField.tsx` | Delete the local `AGENTS` array; import from `agentLayout.ts`. Publish the field rect via `ResizeObserver`. |
| `web/src/components/AgentStatusPanel.tsx` | Position each card at its agent's satellite instead of stacking; subscribe to the field rect; apply offset + clamp. |
| `web/src/agentstatus.css` | `.agent-status` becomes a full-viewport non-interactive layer; cards become absolutely positioned; add the narrow-screen fallback. |
| `web/src/command-deck.css` | Nothing structural — only if a satellite spacing tweak is needed at the apex (see §5.2). |
| `tests/acceptance/star-layout.md` | **NEW.** Manual acceptance checklist. |
| `tests/unit/test_agents_yaml_frontend_parity.py` | **NEW.** Guards against the roster drifting again (§7). |

---

## §5 Implementation steps

### 5.1 — Create `web/src/agentLayout.ts` (new file)

This module is the single source of truth (D3). Create it first; everything else imports it.

It must export:

**(a) The agent layout table.** Exactly these five entries, in this order, with these exact values:

| key | label | x | y | cardAnchor |
|---|---|---|---|---|
| `developer` | `Developer` | `50` | `23` | `above` |
| `analyst` | `Analyst` | `82` | `42` | `left` |
| `systems` | `Systems` | `70` | `72` | `left` |
| `librarian` | `Librarian` | `30` | `72` | `right` |
| `scheduler` | `Scheduler` | `18` | `42` | `right` |

`x`/`y` are percentages of the `.orb-field` box, matching the existing convention (satellites use `left: x%; top: y%` with `transform: translate(-50%, -50%)`).

These coordinates are a pentagon with apex at top, centered at (50, 50), horizontal radius 34 and vertical radius 27, rounded to whole percent. Derivation is recorded here so the numbers are reproducible, **but use the table values as given — do not recompute at runtime.**

`cardAnchor` meanings (D9) — the direction the card body extends *from* the satellite:
- `above` — card sits above the dot, horizontally centered on it.
- `left` — card extends leftward (inward); its right edge sits to the left of the dot.
- `right` — card extends rightward (inward); its left edge sits to the right of the dot.

Side points anchor **inward** rather than outward because outward would push a 300px card past the viewport edge at x=82% / x=18% on common widths, and the §5.4 clamp would then drag it back on top of its own satellite.

**(b) Tuning knobs** (§0.2 — `⚙ TUNING KNOB`, starting values, all in one exported block):

| Name | Starting value | What it does |
|---|---|---|
| `CARD_WIDTH_PX` | `300` | Card width (D11). |
| `CARD_GAP_PX` | `14` | Gap between the satellite chip and its card. |
| `VIEWPORT_MARGIN_PX` | `12` | Minimum distance a card keeps from any viewport edge (§5.4 clamp). |
| `ANCHORED_CARDS_MIN_WIDTH_PX` | `860` | Below this viewport width, fall back to the stacked column (D12). Matches the existing `@media (max-width: 860px)` breakpoint already in `command-deck.css`. |

**(c) A field-rect publisher.** A module-level singleton with subscribe/get, following the existing pattern in `web/src/wakeWord.ts` (which already does module-level state + `subscribeWake(cb): () => void` returning an unsubscribe). Mirror that shape — do not introduce React Context or a state library.

It must expose:
- a setter used by `OrbField` to publish the measured `.orb-field` bounding rect,
- a getter returning the current rect or `null` if not yet measured,
- a subscribe function returning an unsubscribe function.

The rect must carry at least `left`, `top`, `width`, `height` in viewport pixels.

**(d) A percentage → viewport-pixel helper.** Given an agent's `x`/`y` percentages and the current field rect, return the satellite's viewport pixel position. Return `null` when no rect has been published yet.

### 5.2 — Update `web/src/components/OrbField.tsx`

1. Delete the local `AGENTS` constant. Import the layout table from `agentLayout.ts` and use it in both existing `.map()` calls (the beams SVG and the satellite divs). **Do not change any other logic** — the `working`/`doneAt` state, the RTVI event handler, wake ripple, captions, and center readout all stay exactly as they are.
2. Add a `ResizeObserver` on the `.orb-field` element that publishes its bounding rect through the §5.1(c) publisher, and also publishes on mount and on window `scroll`/`resize`. Disconnect the observer on unmount.
3. **Verify the apex has clearance.** The Developer satellite at `y: 23` sits above `.orb-center`. If on a short viewport it visually crowds the `M.O.R.T.I.M.E.R.` readout, the fix is to reduce the vertical radius by adjusting the `developer` entry's `y` in the table (and only that) — not to add new CSS. Flag it to Larry rather than choosing a new value yourself.

Because the beam SVG already uses the same 0–100 coordinate space (§1), beams will follow the new positions with **no math changes**.

### 5.3 — Update `web/src/components/AgentStatusPanel.tsx`

Keep **all** existing behavior: run lifecycle from `delegate_start`/`agent_tool`/`delegate_done`, the 8s success fade, failure cards persisting until dismissed, the 1s elapsed-time heartbeat, tool chips, self-edit stage derivation, `MAX_TOOLS`, and the card markup. This step changes **positioning only**.

1. Subscribe to the field rect from `agentLayout.ts`; store it in component state so position recomputes on resize.
2. Track viewport width (existing `resize` listener or a new one) to drive the D12 fallback.
3. For each run, look up its agent in the layout table **by the `name` field already on the run** (this is the backend agent key: `scheduler`, `librarian`, `analyst`, `systems`, `developer` — the same key the layout table uses).
4. Compute each card's viewport position: satellite pixel position (§5.1d) → apply `cardAnchor` + `CARD_GAP_PX` → apply the §5.4 clamp.
5. Render each card absolutely positioned at that point, with `width: CARD_WIDTH_PX`.
6. **Fallback path (D12):** if viewport width `< ANCHORED_CARDS_MIN_WIDTH_PX`, *or* the field rect is `null` (not yet measured), *or* the run's agent name is not in the layout table — render that card in the original stacked bottom-left column. The unknown-agent case matters: if a sixth agent is ever added to `config/agents.yaml` without updating the layout table, its card must still appear somewhere rather than vanish.

### 5.4 — The clamp (D10)

Applied to every anchored card, after the anchor offset, before render. Deterministic, no special cases:

1. Compute the card's intended viewport rect (left/top from the anchor, width `CARD_WIDTH_PX`, height measured or estimated).
2. If `left < VIEWPORT_MARGIN_PX`, set `left = VIEWPORT_MARGIN_PX`.
3. If `left + width > viewportWidth - VIEWPORT_MARGIN_PX`, set `left = viewportWidth - width - VIEWPORT_MARGIN_PX`.
4. Apply the same two rules on the vertical axis against `top`/height and `viewportHeight`.
5. Additionally clamp `top` to no less than the bottom of `.topbar` (52px, per `App.css`) `+ VIEWPORT_MARGIN_PX`, so a card can never hide under the top bar.

Card height is not known before render. Use the measured height via a ref when available, and fall back to an assumed `160px` for the first paint. Do not block rendering on measurement.

### 5.5 — Update `web/src/agentstatus.css`

1. `.agent-status` becomes a full-viewport passthrough layer: `position: fixed; inset: 0; z-index: 25; pointer-events: none;`. Remove `left`, `bottom`, `width`, `max-height`, `overflow-y`, and the flex-column stacking from this rule — those move to the fallback class below.
2. `.agent-card` gains `pointer-events: auto` so the dismiss button stays clickable through the passthrough layer.
3. Add a modifier class for anchored cards: `position: absolute` (positioned inline via the computed left/top from §5.3).
4. Add a fallback container class carrying the **original** `.agent-status` rules verbatim (`left: 16px; bottom: 72px; width: 360px; max-height: 55vh; overflow-y: auto;` + flex column + `gap: 10px`), used by the D12 path. This is why the original values are preserved rather than deleted.
5. Leave every other rule in this file untouched, including the `prefers-reduced-motion` block.

---

## §6 Where the tuning knobs live

All four knobs from §5.1(b) live in **one exported block at the top of `web/src/agentLayout.ts`**, together with the position table. Larry adjusts values there after seeing it on screen; no logic changes required to tune. Do not scatter these values into CSS or into component bodies.

---

## §7 Verification

**Automated — must all pass:**

1. `cd web && npm run build` — strict TypeScript + production bundle. This is the real gate for frontend work.
2. `cd web && npm run lint` — must report **0 errors**.
3. `pytest tests/unit tests/integration -q` — must stay green (nothing here should touch it; a failure means something unintended changed).
4. **New:** `tests/unit/test_agents_yaml_frontend_parity.py` — reads the agent keys out of `config/agents.yaml`, reads the agent keys out of `web/src/agentLayout.ts` (regex over the source text is acceptable and appropriate here; do not add a JS runtime dependency to the Python suite), and asserts the two sets are identical. **This test is the direct fix for the class of bug in §1** — it fails loudly the next time an agent is added to config without being added to the layout.

Note on the sandbox environment: a previous session found `web/node_modules` missing native `arm64` bindings for `rolldown` and `oxlint`, causing both npm scripts to fail before any project code runs. If that happens, a plain `npm install` resolves it. That is an environment gap, not a code failure.

**Manual acceptance — new file `tests/acceptance/star-layout.md`, run with the full stack (`./scripts/mortimer.sh`):**

- [ ] Five satellites are visible, arranged as a star/pentagon with Developer at the top.
- [ ] Each of the five has a beam to the center; the beam lights while that agent works and fades after.
- [ ] Ask something that routes to **Developer** (e.g. "what's the git status?"). Confirm the Developer satellite lights **and** its status card appears anchored near the top satellite — this is the bug being fixed; Developer must now be visible and reactive.
- [ ] Confirm each of the other four agents, when called, produces a card anchored near **its own** satellite — not bottom-left.
- [ ] Confirm the satellite's pulsing dot + label remain visible while its card is shown (card offsets beside/above, does not cover the dot).
- [ ] **Parallel case (Phase 4):** ask a multi-part request hitting two specialists (e.g. "check the weather in Paris and remind me to pack an umbrella tomorrow"). Confirm two cards appear simultaneously at two different satellites and do not overlap each other illegibly.
- [ ] **Developer card content:** trigger a self-edit run and confirm the four-stage bar (planning → proposing → validating → submitting) still renders correctly inside the anchored card, and the plan text is readable. This card is the reason the panel exists — it must stay legible in its new position.
- [ ] **Failure case:** confirm a failed sub-agent's card still persists until dismissed, and the `×` dismiss button is clickable in the new anchored position.
- [ ] **Edge clamp:** narrow the browser window (staying above 860px) and confirm no card is clipped off-screen or hidden under the top/bottom bars.
- [ ] **Narrow fallback:** shrink below 860px and confirm cards revert to the stacked bottom-left column and remain readable.
- [ ] **Regression:** confirm the center readout, live captions, wake ripple, ⚙ Repo / ✎ Edit / 🧠 Memory panels, and the transcript drawer all still work — the topbar buttons and `.main` stacking were analyzed but not intentionally changed.
- [ ] **Visual tuning pass with Larry:** review the five knobs in §6 on a real screen and adjust to taste. Expected, not a defect.

---

## §8 Rollback

Purely additive and self-contained. To revert: restore the four-entry `AGENTS` array in `OrbField.tsx`, restore the original `.agent-status` CSS rule, and delete `agentLayout.ts` plus the new test and acceptance files. No data, schema, config, or backend state is involved.

---

## §9 Risk

**Low–medium, entirely visual.**

- The genuine risk is card placement looking wrong or overlapping at particular window sizes. Mitigated by the §5.4 clamp, the D12 narrow-screen fallback, and the §7 tuning pass. Nothing here can corrupt data or break the voice pipeline.
- The one non-obvious trap is the stacking context described in §1. An implementer who "simplifies" by moving `AgentStatusPanel` inside `OrbField` will get cards clipped by `overflow: hidden` and painted under the top/bottom bars. D4 exists specifically to prevent that; do not undo it.
- Second trap: assuming the beam SVG needs new math. It does not (§1) — changing it is more likely to break alignment than fix anything.

---

## §10 Approval

Larry approves before any code is written. Confirm: the pentagon coordinates in §5.1(a), the Developer-at-apex choice (D6), the inward card anchoring for side points (§5.1a), and the 300px card width (D11).
