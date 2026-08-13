# Mortimer Console — Docked, Collapsible Status Cards for Long-Running Runs

**Status:** DRAFT — awaiting approval. No code has been written.
**Follows:** `MORTIMER_STAR_LAYOUT_PLAN.md` (anchored status cards, shipped)
and `MORTIMER_RUN_LOGGING_PLAN.md` (shipped, unrelated system — not touched
here).

---

## §0 Constraints for the implementing model

1. Every design decision is already made. They are in §3, lettered D1–D14,
   each with rationale. If a choice between two approaches seems open,
   re-read §3 first.
2. **Card content does not change.** This plan only changes *where* a card
   renders and whether it starts collapsed — the same rule the star-layout
   plan locked in at its §0.4, carried forward here.
3. This must not touch `OrbField.tsx`, `agentLayout.ts`, or the satellite
   field in any way. The satellite dot/beam/label for every agent, Developer
   included, is unaffected — only the *status card* changes.
4. Do not introduce a name-based check (`if name === "developer"`). The
   trigger for docked behavior is a property of the run
   (`isSelfEditRun`, already defined in `AgentStatusPanel.tsx`), not the
   agent's identity — see D1's rationale.
5. Work through §5 in order. Each step leaves `npm run build` and
   `npm run lint` clean.

---

## §1 Background: what is actually wrong today

1. Every status card — all five agents — anchors near its own satellite
   (`computeAnchoredStyle` in `AgentStatusPanel.tsx`, shipped by the
   star-layout plan). The clamp keeps a card on-screen and off the topbar,
   but has no awareness of *other cards*: two anchored cards can overlap.
2. The Developer card is the one this surfaces on in practice, for two
   reasons specific to it, not to its name: `isSelfEditRun` (already in
   this file) makes it the only card that renders the four-stage bar
   (`planning → proposing → validating → submitting`) plus plan/task text,
   making it the tallest card; and self-edit runs (`UpgradeAgent`,
   `config/upgrade_agent.yaml`) run for minutes, not seconds, making it the
   longest-lived. Tallest and longest-lived is exactly the combination that
   maximizes the odds of covering a neighboring satellite's card.
3. The user's own words: "it sometimes is in the way... it is covering
   status windows of other agents." The fix requested is a docked,
   collapsed-by-default console in the upper right, expandable on demand.
4. This is a narrower, later-discovered problem than star-layout's general
   overlap risk (flagged in that plan's options discussion as "sibling
   collision avoidance," never built). This plan does not build general
   collision avoidance — seven's a small fix for the specific, reported
   case; see D14 for why that scope line is deliberate.

---

## §2 What we are building

Any run whose card would currently render the self-edit stage bar
(`isSelfEditRun(name, tools)` true) renders in a **docked** slot instead of
an anchored-to-satellite slot: fixed position, upper right, below the
topbar, collapsed to a one-line header chip by default, expandable on
click to the full card (same content as today, unchanged). Multiple
simultaneous docked runs stack vertically. Every other run keeps today's
anchored-to-satellite behavior exactly as shipped.

Out of scope: general sibling-collision avoidance for anchored cards
(§1.4), a resizable/draggable dock, and any change to what a card
*contains*.

---

## §3 Decisions already made (with rationale)

**D1 — Trigger is `isSelfEditRun(name, tools)`, already defined in this
file, reused verbatim.** No new heuristic, no name check.
*Rationale:* this function already exists specifically to answer "is this
run self-edit-flavored" for the stage bar, and the overlap problem is
caused by exactly the runs that function already identifies (tall +
long-lived). Reusing it means the docked/anchored split can never disagree
with the stage-bar split — a run either gets both the stage bar and the
dock, or neither. It also means a future non-Developer run that happens to
call `selfedit_*` tools docks correctly with zero new code, and Developer
doing an ordinary non-self-edit task stays anchored like everyone else —
satisfying §0.4's ban on a name check without inventing a second signal.

**D2 — Docked cards are position: fixed, independent of the satellite
field's measured rect.** They do not use `agentViewportPosition`,
`fieldRect`, or the `ANCHORED_CARDS_MIN_WIDTH_PX` breakpoint at all.
*Rationale:* the anchored-card machinery exists to place a card *next to
its satellite*, which requires knowing the field's on-screen rect. A
docked card is deliberately placed in a fixed screen region unrelated to
any satellite, so none of that machinery applies — simpler and with fewer
failure modes (no dependency on `OrbField` having measured yet, no
narrow-viewport special case beyond an ordinary `max-width: 92vw`).

**D3 — Dock position: `top: TOPBAR_HEIGHT_PX + VIEWPORT_MARGIN_PX`,
`right: VIEWPORT_MARGIN_PX`.** Both constants already exist in
`agentLayout.ts` (52 and 12 respectively) — import and reuse them, do not
hardcode new pixel values.
*Rationale:* consistency with the clamp's own floor
(`topFloor = TOPBAR_HEIGHT_PX + VIEWPORT_MARGIN_PX`, already in
`computeAnchoredStyle`) — the dock sits exactly where an anchored card's
topmost legal position would be, so the two systems read as one visual
language, not two unrelated ones.

**D4 — Collapsed by default; state is per-run, toggled by clicking the
header row.** New component state: `Record<number, boolean>` (run id →
expanded), defaulting to `false` (collapsed) when a run first enters the
docked bucket. Clicking anywhere on the card's head row
(`.agent-card-head`) toggles it; a trailing caret (`▸` collapsed / `▾`
expanded) is the visual affordance.
*Rationale:* directly what was asked: "in a collapsed to the header state.
then it could be opened when needed." Per-run state (not a single global
flag) because two simultaneous docked runs may be at different points in
their own work — collapsing one must not collapse the other.

**D5 — Multiple docked runs stack vertically via flexbox, not pixel math.**
New container `.agent-status-docked`: `position: fixed`, `top`/`right` per
D3, `display: flex; flex-direction: column; gap: 8px`. Each docked run is
one flex child, in the same order `runs` already provides (insertion
order — oldest first, matching the fallback stack's existing behavior).
*Rationale:* the anchored cards need pixel math because they each target a
different point on screen; docked cards all target the same corner, so
letting flexbox stack them is strictly simpler and mirrors
`.agent-status-fallback`'s existing `flex-direction: column; gap: 10px`
pattern — no new layout algorithm.

**D6 — Collapsed chip shows: status dot, agent display name, elapsed/status
time, caret. No task text, no tool chips, no stage bar.** Expanded shows
everything the card shows today (task, tool chips, stage bar, failure
detail), unchanged.
*Rationale:* a header-only chip is the definition of "collapsed to the
header state." Reusing the *existing* head row markup for the collapsed
view (rather than inventing a new compact layout) keeps this a
presentation change, not a content change (plan §0.2).

**D7 — Implementation is a refactor of `renderCardBody` into two pieces:
`renderCardHead(r, { toggle })` and `renderCardDetails(r)`.** Docked mode
renders `renderCardHead` always, and `renderCardDetails` only when
expanded. Anchored and fallback modes call both, unconditionally, exactly
as `renderCardBody` does today — their JSX output must be byte-identical
to before this change.
*Rationale:* the smallest change that lets docked mode reuse the existing
head markup instead of duplicating it. `renderCardBody` becomes a thin
wrapper (`renderCardHead(r) + renderCardDetails(r)`) so the anchored/
fallback call sites don't need to change at all.

**D8 — Auto-fade-after-success and dismiss-on-failure are unchanged and
apply identically to docked cards.** `DONE_FADE_MS` timer logic, the `×`
dismiss button, and `removeRun` are untouched. A docked card's expand
state is irrelevant to fade/dismiss — collapsing or expanding never resets
or cancels the existing timer.
*Rationale:* plan §0.2 — only position/chrome changes. The fade/dismiss
contract already works and is orthogonal to where the card is drawn.

**D9 — Card width in the expanded state reuses `CARD_WIDTH_PX` (300, from
`agentLayout.ts`).** The collapsed chip does not set an explicit width —
it sizes to its content (dot + name + time + caret), matching how a
notification chip typically behaves, capped by the same
`max-width: 92vw` safety used elsewhere (`memory.css`, `runs.css`).
*Rationale:* reusing the existing width knob keeps one place to tune card
width for both anchored and docked-expanded states (plan §6 already
requires tuning knobs live in one place); the collapsed chip has no
analogous need since its content is short and fixed in shape.

**D10 — z-index: 26**, one above `.agent-status`'s existing 25
(`agentstatus.css`), below `.display-panel`'s 30.
*Rationale:* a docked card is the thing the user is actively expanding and
reading — it should render above ordinary anchored cards if they ever
visually overlap near the screen edge, but must still yield to the
results/display panel, matching the layering already documented in
`agentstatus.css`/`command-deck.css`.

**D11 — Partition logic becomes three-way, in this order: docked (D1) →
anchored (existing `canAnchor && findAgentLayout` check) → fallback
(everything else).** A run that would qualify for both docked and anchored
(e.g. Developer running a self-edit task, which has both a satellite entry
in `agentLayout.ts` and `isSelfEditRun` true) always goes to docked — the
docked check runs first and is exclusive.
*Rationale:* docked is a stronger, more specific signal than "has a
satellite" — every agent has a satellite entry, so checking anchored first
would never let a self-edit run reach the docked bucket at all. Checking
docked first is the only ordering that produces the requested behavior.

**D12 — No change to the narrow-viewport breakpoint (`ANCHORED_CARDS_MIN_WIDTH_PX`)
or to `.agent-status-fallback`.** Docked cards do not participate in that
breakpoint at all (D2) — a docked run stays docked regardless of viewport
width, protected only by `max-width: 92vw` (D9).
*Rationale:* the breakpoint exists because *anchored* cards need the field
rect to compute a position; docked cards never do, so there is nothing for
the breakpoint to protect them from.

**D13 — No new CSS variables; reuse `--green`/`--red`/`--accent`/`--text-dim`
already established in `agentstatus.css` for status coloring**, and reuse
the existing `.agent-card`, `.agent-card-working`, `.agent-card-ok`,
`.agent-card-fail` classes unchanged. Only new rules are for the
`.agent-status-docked` container, the collapsed-chip layout tweaks (no
task/tools/stage children rendered, so no new rules needed there — absence
of children is enough), and the caret.
*Rationale:* the entire card's visual language (colors, borders, shadows)
should look like the same product, not a second design. Everything about
a docked card's *content* is drawn with classes that already exist.

**D14 — General sibling-collision avoidance for anchored cards (star-layout's
"Option C," never built) is explicitly out of scope for this plan.**
*Rationale:* the reported problem is specifically the Developer/self-edit
card, which D1–D13 fix directly. Building general N-card collision
avoidance is a materially larger, fiddlier piece of work (star-layout's
own options discussion flagged it as "the fiddliest, can produce jumpy
layout") that the user has not asked for and that this fix does not
require as a prerequisite. If two *non-docked* cards still overlap after
this ships, that is a known, separate, smaller residual risk — worth a
one-line follow-up note in the final report, not a blocker here.

---

## §4 Files that will change

| Path | Change |
|---|---|
| `web/src/components/AgentStatusPanel.tsx` | Split `renderCardBody`; add docked bucket, per-run expand state, docked render path |
| `web/src/agentstatus.css` | New `.agent-status-docked` container + caret styling |
| `tests/acceptance/star-layout.md` | Add a docked-card section (this is a presentation refinement of that plan's shipped UI, not a new acceptance file) |

No backend files change. No `agentLayout.ts` change (§0.3).

---

## §5 Implementation steps

### 5.1 — `AgentStatusPanel.tsx`: split the render helper

Replace the single `renderCardBody(r)` with:

```tsx
const renderCardHead = (
  r: RunState,
  opts?: { onToggle?: () => void; expanded?: boolean },
) => {
  const working = r.doneAt === null;
  const elapsed = fmtElapsed((r.doneAt ?? now) - r.startedAt);
  return (
    <div
      className="agent-card-head"
      onClick={opts?.onToggle}
      role={opts?.onToggle ? "button" : undefined}
    >
      <span className="agent-card-dot" />
      <span className="agent-card-name">{r.displayName}</span>
      <span className="agent-card-time">
        {working ? elapsed : `${r.ok ? "done" : "failed"} · ${elapsed}`}
      </span>
      {opts?.onToggle && (
        <span className="agent-card-caret">{opts.expanded ? "▾" : "▸"}</span>
      )}
      {!working && !opts?.onToggle && (
        <button type="button" className="agent-card-close"
                onClick={() => removeRun(r.id)} aria-label="Dismiss">×</button>
      )}
    </div>
  );
};

const renderCardDetails = (
  r: RunState,
  opts?: { inlineDismiss?: boolean },
) => {
  const working = r.doneAt === null;
  return (
    <>
      {r.task && <div className="agent-card-task">{r.task}</div>}
      {r.tools.length > 0 && ( /* unchanged tool-chip block */ )}
      {isSelfEditRun(r.name, r.tools) && ( /* unchanged stage bar block */ )}
      {!working && !r.ok && r.detail && (
        <div className="agent-card-detail">{r.detail}</div>
      )}
      {opts?.inlineDismiss && !working && (
        <button type="button" className="agent-card-close-inline"
                onClick={() => removeRun(r.id)} aria-label="Dismiss">
          dismiss
        </button>
      )}
    </>
  );
};

const renderCardBody = (r: RunState) => (
  <>{renderCardHead(r)}{renderCardDetails(r)}</>
);
```

Anchored and fallback call sites keep calling `renderCardBody(r)`
unchanged — `renderCardDetails(r)` with no `opts` renders no inline
dismiss button, so their output is byte-identical to before this plan
(§0.2). **This `opts` gate is load-bearing, not optional** — without it,
every anchored and fallback card would grow a second dismiss button
alongside its existing head-row `×`, which is exactly the kind of content
change §0.2 forbids.

Note the dismiss button moves *only for docked cards*: in the non-docked
head row it stays exactly where it was (only reachable when `!working`
and no toggle handler is present — see `renderCardHead`). In docked mode,
since the head row's click now toggles expand/collapse, the `×` cannot
also live there without a click conflict — docked mode alone passes
`{ inlineDismiss: true }` to `renderCardDetails`, visible only when
expanded and not working. A failed, collapsed docked card is still
dismissible: expand it, then dismiss — never silently undismissable.

### 5.2 — Per-run expand state

```tsx
const [dockExpanded, setDockExpanded] = useState<Record<number, boolean>>({});

const toggleDock = useCallback((id: number) => {
  setDockExpanded((prev) => ({ ...prev, [id]: !(prev[id] ?? false) }));
}, []);
```

Clear the entry in `removeRun` alongside the existing `cardHeights`
cleanup (same pattern, same function, one more `delete`).

### 5.3 — Three-way partition

Replace the existing two-way loop:

```tsx
const docked: RunState[] = [];
const anchored: Array<{ run: RunState; entry: AgentLayoutEntry }> = [];
const fallback: RunState[] = [];
for (const r of runs) {
  if (isSelfEditRun(r.name, r.tools)) {
    docked.push(r);
    continue;
  }
  const entry = canAnchor ? findAgentLayout(r.name) : undefined;
  if (entry) anchored.push({ run: r, entry });
  else fallback.push(r);
}
```

(D11 — docked checked first, unconditionally, before the anchored check.)

### 5.4 — Docked render block

Inside the existing `<div className="agent-status" ...>` wrapper, alongside
the `anchored.map(...)` and the `fallback.length > 0 && (...)` blocks, add:

```tsx
{docked.length > 0 && (
  <div className="agent-status-docked">
    {docked.map((r) => {
      const expanded = dockExpanded[r.id] ?? false;
      return (
        <div
          key={r.id}
          className={cardClassFor(r) + " agent-card-docked"}
          style={expanded ? { width: CARD_WIDTH_PX } : undefined}
        >
          {renderCardHead(r, { onToggle: () => toggleDock(r.id), expanded })}
          {expanded && renderCardDetails(r, { inlineDismiss: true })}
        </div>
      );
    })}
  </div>
)}
```

### 5.5 — `agentstatus.css`

```css
/* Developer-dock plan §5.5: docked runs (isSelfEditRun) render fixed in
   the upper right, collapsed to a header chip by default, independent of
   the satellite field's measured rect — see plan D2. */
.agent-status-docked {
  position: fixed;
  top: calc(52px + 12px); /* TOPBAR_HEIGHT_PX + VIEWPORT_MARGIN_PX, plan D3 */
  right: 12px;
  z-index: 26;
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-width: 92vw;
  pointer-events: auto;
}

.agent-card-docked {
  /* width comes from inline style when expanded (CARD_WIDTH_PX); the
     collapsed chip sizes to its content — no explicit width here. */
}

.agent-card-head[role="button"] {
  cursor: pointer;
}

.agent-card-caret {
  font-family: var(--mono);
  font-size: 10px;
  color: var(--text-dim);
  margin-left: auto;
  flex: none;
}

.agent-card-close-inline {
  margin-top: 6px;
  font-family: var(--mono);
  font-size: 10px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  background: none;
  border: 1px solid var(--hairline);
  border-radius: 2px;
  color: var(--text-dim);
  padding: 3px 8px;
  cursor: pointer;
}

.agent-card-close-inline:hover {
  color: var(--text);
  border-color: var(--accent-dim);
}
```

Note: `.agent-card-time` already has `margin-left: auto` in the existing
rules — with the caret added after it, drop `margin-left: auto` from
`.agent-card-caret` if it collides (verify visually; if both have
`margin-left: auto` the caret simply also floats right, which still
reads correctly, but `flex: none` must stay so it doesn't stretch).

### 5.6 — Acceptance checklist addition

Append a new section to `tests/acceptance/star-layout.md` (the docked
behavior is a refinement of that shipped UI, not a separate feature):

```markdown
## Docked runs (Developer-dock plan)

- [ ] Trigger a self-edit run (voice: ask Mortimer to change something
      about its own UI). Confirm its card appears docked top-right,
      collapsed to a header chip (dot, name, elapsed time, caret) — not
      anchored near the Developer satellite.
- [ ] Click the collapsed chip. Confirm it expands to show task text,
      tool chips, and the four-stage bar, unchanged from how the card
      looked before this plan.
- [ ] Click again. Confirm it collapses back to the chip; the run keeps
      progressing underneath (elapsed time keeps ticking while collapsed).
- [ ] Trigger a second, non-self-edit task on a different agent while the
      self-edit run is active. Confirm that card still anchors near its
      own satellite, unaffected by the dock.
- [ ] Let the self-edit run fail. Confirm the docked card persists
      (auto-fade does not apply to failures, same as before), expand it,
      and confirm the "dismiss" button inside the expanded body removes
      it.
- [ ] Resize the browser narrow. Confirm the dock stays pinned top-right
      and never grows past ~92% of viewport width.
```

---

## §6 Where the tuning knobs live

This plan introduces no new numeric tuning knobs — it reuses
`TOPBAR_HEIGHT_PX`, `VIEWPORT_MARGIN_PX`, and `CARD_WIDTH_PX`, all already
defined and tunable in `web/src/agentLayout.ts` per the star-layout plan's
§6. The only new visual constant (`gap: 8px` between stacked docked cards)
lives directly in `.agent-status-docked` in `agentstatus.css`, matching
where `.agent-status-fallback`'s own `gap: 10px` already lives.

---

## §7 Verification

**Automated — must all pass:**

1. `cd web && npm run build` — strict TS, zero errors.
2. `cd web && npm run lint` — zero warnings, zero errors.
3. Visual confirmation that `renderCardBody`'s output for anchored and
   fallback cards is unchanged — no new DOM nodes added to those two call
   sites (the split in §5.1 must be a pure refactor for them). Specifically
   confirm no `.agent-card-close-inline` button appears on an anchored or
   fallback card — §5.1's `opts?.inlineDismiss` gate is what prevents this;
   its absence would be the regression to check for.

**Manual — `tests/acceptance/star-layout.md`'s new "Docked runs" section
(§5.6), same sandbox limitation as the star-layout plan itself: requires a
live voice session and a real browser, neither available in this
environment.**

---

## §8 Rollback

Revert the branch. No schema, no config, no backend — a pure frontend
presentation change with no migration to unwind.

---

## §9 Risk

| Risk | Severity | Mitigation |
|---|---|---|
| Two simultaneous self-edit-flavored runs stack and still crowd a small viewport. | Low | Flexbox stacking (D5) plus `max-width: 92vw` (D9) keeps this readable, if tight, on any screen size; two concurrent self-edit runs is already an edge case bounded by `JARVIS_MAX_PARALLEL_DELEGATIONS`. |
| The head-row click-to-toggle conflicts with the existing `×` dismiss button's click target on non-docked cards. | Low | §5.1's `renderCardHead` only attaches `onClick`/`role="button"` when `opts?.onToggle` is passed — anchored/fallback cards never pass it, so their head row's click behavior is unchanged (no-op background, `×` still its own button). |
| Non-docked anchored cards can still overlap each other (§1.4, D14). | Low — known, deferred | Explicitly out of scope (D14); flag in the final report as a residual, smaller issue distinct from the one this plan fixes. |
| `isSelfEditRun`'s heuristic (tool-name substring match) mis-fires on an unrelated agent whose tool happens to contain "edit" or "develop". | Low — pre-existing | Not introduced by this plan — the heuristic already exists and already gates the stage bar; this plan only adds a second consumer of an existing, already-accepted risk. |

---

## §10 Approval

- [ ] Larry has read §2 (scope) and §3 (decisions) and approves.
- [ ] Implementation may begin.
