# Mortimer — Right-Side Tabbed Drawer (push layout, resizable)

**Status:** Revisions 1–5 (D1–D43) IMPLEMENTED 2026-08-14 (build/lint/tests
green; see §10 for the verification detail). Manual acceptance
(`tests/acceptance/side-drawer.md`) not yet walked against a live session.
**Every decision in §3 is current, live text — read it as written.** Three
decisions were superseded while drafting (D18 entirely, D28 and D31 in
part, plus D33's original delete list); §3 carries only their final form,
and the superseded originals are quarantined in **Appendix A** so the
change in intent stays legible without a cold reader ever encountering
stale instructions first.
**Revision 5** (2026-08-14) — display payloads split by kind of content:
informational answers (weather, research, radar) keep a floating window
that can be parked on a second monitor; work product (diffs, commits,
project plans) goes to the drawer's Output tab. Scope decided by Larry:
multiple monitors driven by **one machine**, not multiple devices — which
keeps this entirely in the frontend (see D39/D40).
**Revision 4** (2026-08-14) — `DisplayPanel` becomes a sixth drawer tab.
D18 ("do not reposition `DisplayPanel`") was wrong in practice: the first
real use showed a 21-file diff summary floating over the drawer, which is
content you read, not glance at. See D28.
**Revision 3** (2026-08-14) — gaps found during a real implementation pass
(a separate model built revision 2 end to end; every gap below is a place
it had to invent something the plan should have specified). This plan is
written to be implemented by a model with no access to the conversation
that produced it.
**Scope decided by:** Larry, 2026-08-14 (three-question round: push layout,
one tabbed drawer, Developer as a fifth tab — §2).

### Revision 2 — gaps found by self-audit and the decision that closes each

| # | Gap in revision 1 | Closed by |
|---|---|---|
| 1 | Never said whether the drawer is unmounted when closed or rendered at zero width — decides panel refetch behavior, whether the transition is possible at all, and adds an unmount path D10 must survive. | **D23** |
| 2 | `agentRuns.ts`'s public API was named but not typed. Two consumers must agree on it; this is the same multi-consumer-contract hole the run-logging plan's D19 existed to prevent. | **D24** |
| 3 | Never said which property holds the width, which property transitions, or how dragging avoids fighting the easing. | **D25** |
| 4 | D20 said `Escape` acts "when it has focus within"; §5.6 said window-level "alongside the existing `T` handler." Contradiction — both read as instructions. | **D20** rewritten + §5.6 |
| 5 | `SideDrawer` props untyped; `TabKey` union had no defined home. | **D24** |
| 6 | Tab strip labels, the Developer topbar button's label/icon, and its position in the button row were unspecified. | **D26** |
| 7 | `.btn-active` was named with no declared properties. | **D26** |
| 8 | `localStorage` hydration timing unstated (initializer vs effect — decides flash on load). | **D13** amended |
| 9 | D16 didn't say whether the persisted width applies in overlay mode, or what happens to the resize handle there. | **D16** amended |
| 10 | D19 told the implementer to "verify `.editmode-panel` before writing the selector." | **D19** amended — all four class names verified, literal selector given |

### Revision 3 — gaps found while implementing revision 2

| # | Gap in revision 2 | Closed by |
|---|---|---|
| 11 | D7 said "a pulsing accent dot" with no class name, no properties, and no statement of which element it lives on. | **D7** amended |
| 12 | `SideDrawerProps` includes `onClose`, but nothing in §3 rendered a control that calls it — a dead prop as written. | **D27** (new) |
| 13 | D16 (overlay mode) and D23 (always mounted) directly conflict below 860px: an always-mounted, `position: fixed; width: 100vw` element with no closed-state rule paints as a full-screen block over the app even when `open` is false. | **D16** amended |
| 14 | §5.3 said the Developer tab reuses "the existing `agent-card*` classes," but `.agent-card` is `position: absolute` (`agentstatus.css`) — reused verbatim, every card in the drawer stacks at the same coordinates. | **D8** amended |
| 15 | D23's `pointer-events: none` on the closed handle plus D20's `tabIndex={0}` leaves a keyboard-focusable element inside an `aria-hidden` subtree while closed — a real accessibility fault, not a style nit. | **D20** amended |
| 16 | D8 and §5.1 both say the `AgentStatusPanel` → `agentRuns.ts` move is "verbatim." It cannot be, strictly: `removeRun`'s height-map cleanup and the store's card-height state can't both live in a non-component module, and `React.JSX.Element` isn't reliably in scope as a bare `JSX` reference under React 19's module types. Stated as verbatim, an implementer who takes that literally produces something that doesn't compile. | **D8/§5.1** amended, **D24** amended |

### Revision 4 — `DisplayPanel` becomes the Output tab

| # | Problem with revision 3 as shipped | Closed by |
|---|---|---|
| 17 | **D18 was wrong.** It kept `DisplayPanel` floating at `z-index: 30` on the grounds that it is "a transient results window the user dismisses in seconds." In practice its payloads include `git_diff_summary` output (a 21-file diff), `web_search` research briefs, and project plans — content that is read, not glanced at. Worse, it spawns at `x = innerWidth - 540 - 48`, hard against the right edge, so it reliably lands *on top of* the drawer it was supposed to coexist with. | **D28** (D18 reversed) |
| 18 | Display payload state lives in `DisplayPanel`'s `useState` and holds exactly one item (`setItem` replaces). As a drawer tab it would be destroyed on every tab switch — the same problem D10 solved for run state — and a second result would silently erase the first. | **D29** |
| 19 | The floating window's only virtue was appearing unprompted. A tab behind a closed drawer announces nothing. | **D31** |
| 20 | `ts` in the display payload is epoch **seconds** (`time.time()` in `jarvis/bot/display.py:77`), while the existing `relTime` helper takes an ISO string. Passing one to the other yields 1970. | **D34** |

### Revision 5 — split informational answers back out to a window

| # | Problem with revision 4 as drafted | Closed by |
|---|---|---|
| 21 | D28 sends **every** display payload to the Output tab, including weather, research, and radar. Those are answers to a spoken question — they belong in a window that can be glanced at, and (in a multi-monitor setup) parked on a second screen, not filed in a drawer tab. | **D28** (rewritten), **D36** |
| 22 | Nothing in the payload distinguishes the two categories, and the obvious candidate does not work: `kind` is `markdown`/`image`/`links`, and both a weather forecast and a git diff are `markdown`. Routing must key off the tool. | **D36** |
| 23 | A floating in-page window can never leave the browser viewport, so it cannot satisfy "assigned to another screen." | **D39**–**D42** |
| 24 | The display payload arrives on the WebRTC/RTVI data channel held by the console page. A second window has no session and cannot receive it directly. | **D40** |
| 25 | A popup opened without a user gesture is blocked by every browser's popup blocker — so "reopen the display window automatically when the next result arrives" silently fails once the user has closed it. | **D41** |

**Supersedes:** `MORTIMER_DEVELOPER_DOCK_PLAN.md` (DRAFT, never
implemented). That plan docked the Developer status card to the top-right
corner; this plan puts the same content in a drawer tab instead, which is
the same screen real estate. Its D1 (route on `isSelfEditRun`, a property
of the run) survives here as D9 — with a correction, see D9. Mark that
plan SUPERSEDED when this one is approved; do not implement both.

---

## §0 Constraints for the implementing model

1. Every design decision is already made. They are in §3, lettered D1–D43
   (plus D8a), each with rationale. **Everything in §3 is current — there
   is no superseded text inside it, so read it straight through and
   implement it as written.** If a choice seems open, re-read §3. If it is
   still open after that, it is a bug in this plan — say so rather than
   choosing.
1a. **D1–D27 are already implemented and shipped.** If you are picking this
   up now, your scope is D28–D43, steps §5.9–5.17, and the revision-4/5
   blocks of the §7 checklist. Do not re-implement D1–D27. The one
   exception: D18 is now a stub pointing at Appendix A — it was never
   implemented and must not be.
1b. **Appendix A exists only to record superseded reasoning.** Nothing in
   it is an instruction. Never implement from Appendix A.
2. **Almost entirely frontend.** The single backend change is `surface` in
   `jarvis/bot/display.py` (D36) and its unit test. No schema, no new
   endpoint, no change to what any panel fetches.
3. **Panel CONTENT does not change.** `GitPanel`, `EditModePanel`,
   `MemoryPanel`, and `RunsPanel` keep their current internals verbatim.
   This plan changes only where they are mounted and what chrome wraps
   them. Any temptation to "improve" a panel while moving it is out of
   scope.
4. **Naming: never call this a "sidecar."** In this codebase "sidecar"
   already means the admin Python process on `:7861`
   (`jarvis/admin/server.py`, `JARVIS_ADMIN_URL`, "admin sidecar offline"
   strings in the panels). This UI concept is the **side drawer**
   throughout — class names, component names, comments, commit messages.
   Same discipline as the run-logging plan's "procedure" vs "skill" rule.
5. The existing transcript drawer (`TranscriptDrawer`, `.drawer`, toggled
   by `T`) is a different component and stays separate — see D17.
6. Work through §5 in order. Each step leaves `npm run build` green.

---

## §1 Background: what is wrong today

1. **All four panels share one absolutely-positioned box.** `App.tsx`
   renders `GitPanel`, `EditModePanel`, `MemoryPanel`, and `RunsPanel`
   each inside `<div className="git-popover">`, and `.git-popover`
   (`command-deck.css:249`) is `position: absolute; top: 56px; right:
   16px; width: 340px`. Each panel has an independent `useState` boolean
   in `App.tsx` with nothing coordinating them, so opening two renders
   them at identical coordinates, stacked. DOM order decides the winner
   (Runs paints last). This is a live defect, not a hypothetical.
2. **The popover covers the stage.** At z-20 over `.main`, an open panel
   obscures the orb field, the satellites, and any anchored status cards
   behind it. There is no way to consult a panel and watch the interface
   at the same time.
3. **Width is fixed at 340px.** `.runs-panel` itself declares `width:
   460px` (`runs.css:10`), wider than its own host — it is only saved by
   `.git-popover` not clipping. There is no user control over width.
4. **`.git-popover` is `position: absolute` inside `.app`**, which is a
   flex column — so it does not participate in layout at all and nothing
   reflows around it.

---

## §2 What we are building

A single right-side **drawer** that:

- **pushes** the stage rather than covering it (D2/D3) — `.main` narrows,
  the orb field and satellites re-center automatically;
- hosts **five tabs** in one container — Repo, Edit, Memory, Runs,
  Developer (D4/D5);
- **resizes** by dragging its left edge, with the width persisted
  (D11/D12/D13);
- opens and closes without losing panel state or interface access;
- carries a **live indicator on its topbar button** so a running
  self-edit is visible even when the drawer is shut (D7 — this is the
  mitigation for the one real regression this design introduces).

Explicitly **out of scope**: folding the transcript drawer in as a sixth
tab (D17 — a reasonable follow-up), repositioning `DisplayPanel` (D18),
tearing out the now-unused legacy `.orb-wrap` rules in `App.css` (D21),
and any change to what the four existing panels fetch or render (§0.3).

---

## §3 Decisions already made (with rationale)

### Layout

**D1 — Naming.** Component `SideDrawer.tsx`; CSS block prefix
`.side-drawer`; new stylesheet `web/src/sidedrawer.css`; localStorage keys
namespaced `mortimer.drawer.*`. The word "sidecar" never appears in any of
it.
*Rationale:* §0.4. The one time this codebase reused an existing word for
a new concept ("skill"), it cost a rename across table names, module
names, and prompts. Cheaper to be deliberate now.

**D2 — Push, not overlay.** The drawer is a flex sibling of `.main`, not a
positioned overlay. When open, `.main` genuinely narrows.
*Rationale:* the stated requirement is that the interface keeps access
while the drawer is open — an overlay cannot deliver that, it only makes
the covering prettier. Push also gets satellite re-centering for free:
`OrbField` already publishes `.orb-field`'s measured rect through a
`ResizeObserver` (`OrbField.tsx:85-101` → `publishFieldRect`), and
`AgentStatusPanel` already subscribes (`subscribeFieldRect`). Narrowing
the stage fires that existing path with no new plumbing.

**D3 — Introduce a `.stage-row` flex-row wrapper.** `.app` currently
stacks `topbar / [popovers] / error-banner / main / bottombar` as a flex
column. Wrap `<main className="main">` and `<SideDrawer />` together in
`<div className="stage-row">`, which takes `flex: 1; display: flex;
flex-direction: row; min-height: 0`. `.main` keeps `flex: 1`; the drawer
takes `flex: 0 0 <width>px`.
*Rationale:* this is the minimal structural change that makes push work —
the drawer must share a row-direction flex parent with the stage, and
`.app` is a column. Putting the drawer directly in `.app` and switching
`.app` to row would break the topbar/bottombar stacking. A wrapper is
strictly local.
**Note for the implementer:** `.main` is declared twice — `App.css:250`
(`flex-direction: row`) and `command-deck.css:4` (no direction, so row by
default). Both currently apply; command-deck.css loads second. Do not
"clean this up" as part of this work — leave both, change neither.

**D4 — One drawer host, five tabs, not five drawers.** `SideDrawer`
renders a tab strip plus exactly one active tab's body. Tab keys:
`repo | edit | memory | runs | developer`.
*Rationale:* this makes §1.1's stacking bug impossible by construction —
there is one container, one width, one resize handle, one open/closed
state, and exactly one visible body. Independent drawers would require
inventing a policy for "what happens when two are open," which is how the
current mess arose.

**D5 — Topbar buttons become tab selectors, with a three-case toggle.**
The existing Repo/Edit/Memory/Runs buttons (plus a new Developer button)
behave as:

| Drawer state | Click button X | Result |
|---|---|---|
| closed | X | open, active tab = X |
| open, active = X | X | close (tab stays X for next open) |
| open, active = Y | X | stay open, active tab = X |

The button matching the active tab carries a `.btn-active` class while the
drawer is open, and `aria-expanded` reflects open state.
*Rationale:* preserves the existing muscle memory (a button toggles its
own panel) while making cross-panel switching one click instead of
two. Closing on re-click of the *active* tab is what makes the buttons
still feel like toggles rather than radio buttons.

**D6 — Drawer default state: closed, tab `runs`.** On a first visit with
no stored preference, the drawer is shut and its remembered tab is `runs`.
*Rationale:* this is a voice-first interface — the stage is the product,
panels are on demand. `runs` as the default tab because it is the only
panel that is useful without first performing an action.

### Developer tab

**D7 — The Developer topbar button carries a live run indicator.** While a
run routed to the Developer tab (D9) is in flight
(`runs.some(r => isSelfEditRun(r.name, r.tools) && r.doneAt === null)`,
read from `agentRuns.ts` — see D10/D24), two elements show a dot, both
reusing the existing `dot-pulse` keyframes (`App.css`, already used by
`.satellite-working .satellite-dot` and `.run-status-live`):
- **`.btn-live-dot`** — a 6px circular `span`, `background: var(--accent)`,
  `border-radius: 50%`, `animation: dot-pulse 1s ease-in-out infinite`,
  rendered as the last child inside the `🛠 Dev` topbar `<button>`
  (`aria-hidden="true"`, decorative only — the button's own accessible
  name doesn't change).
- **`.side-drawer-tab-dot`** — the same visual treatment, rendered inside
  the Developer tab strip button, so the indicator is still visible once
  the drawer is already open on a different tab.
Both respect `@media (prefers-reduced-motion: reduce)` by dropping the
`animation` (static dot instead).
*Rationale:* **this is the mitigation for the one genuine regression in
this design.** Today the Developer status card appears on screen
unprompted and is impossible to miss. Moving it into a tab inside a
drawer that defaults to closed would mean a multi-minute self-edit runs
with zero on-screen evidence — strictly worse than both current behavior
and the superseded dock plan, whose entire purpose was ambient awareness.
The topbar is the only surface that is always visible regardless of drawer
state, so `.btn-live-dot` is required, not optional; `.side-drawer-tab-dot`
is the same signal repeated where it's cheap to repeat it, for the case
where the drawer is already open on the wrong tab.

**D8 — The Developer tab keeps a bounded history and does NOT auto-fade.**
`AgentStatusPanel` removes a successful card after `DONE_FADE_MS` (8s).
Runs shown in the Developer tab are exempt: they persist, newest first,
capped at `MAX_DEVELOPER_RUNS = 20`, with completed runs visually settled
rather than removed. The 8s fade is unchanged for the four satellite
cards. The per-run dismiss button still works and removes that run
immediately.
*Rationale:* an 8-second fade is correct for an overlay card that is in
the way, and wrong for a panel the user deliberately opened to read. A
persistent surface should let you see what just happened; otherwise
opening the tab after a run finishes shows an empty panel, which is worse
than what we have now.

**Card styling in the Developer tab is NOT a verbatim reuse of
`.agent-card`.** `.agent-card` is `position: absolute` (`agentstatus.css`
— it exists to anchor a card next to a satellite in viewport pixels).
Rendered unmodified inside the drawer's flow layout, every card would
render at the same stacked coordinates. `DeveloperRunsTab` applies one
additional class alongside the existing ones —
`className={cardClassFor(r) + " developer-run-card"}` — and
`sidedrawer.css` (or `agentstatus.css`, either is fine, pick one and be
consistent) adds:
```css
.developer-run-card { position: static; box-shadow: none; }
```
Every other `.agent-card*` class (`.agent-card-working`,
`.agent-card-ok`, `.agent-card-fail`, `.agent-card-head`, `.agent-card-dot`,
etc., plus the `agent-stages`/`agent-stage-*` readout) is reused exactly
as-is — only positioning is overridden.
*Rationale:* "reuse the existing classes" (revision 2's §5.3 wording) is
correct for content and color but was never true for layout, because
those classes were written for one specific consumer
(`AgentStatusPanel`'s viewport-anchored cards) that this is not.

**D8a — The existing per-agent REPLACEMENT rule must be narrowed, or D8
cannot work.** `AgentStatusPanel.tsx:255` currently handles a `working`
message with:
```ts
setRuns((rs) => [...rs.filter((r) => r.name !== name), run]);
```
i.e. a new run for an agent deletes that agent's previous run. Applied
unchanged, every new Developer run would wipe the history D8 just asked
for — the two decisions directly contradict unless this is fixed.
Required behavior in `applyServerMessage` (D10):
- **non-Developer runs:** replacement is unchanged — filter out the same
  agent's prior run, exactly as today.
- **Developer runs** (`isSelfEditRun` true): append without filtering;
  then, if the agent's run list exceeds `MAX_DEVELOPER_RUNS`, drop the
  OLDEST **completed** run (`doneAt !== null`). Never drop a run that is
  still in flight, even if it is the oldest.
The `runIds` map (agent name → live run id) continues to track only the
one *live* run per agent; completed Developer runs are intentionally no
longer reachable through it, so `clearTimer`/replacement lookups are
unaffected.
*Rationale:* this is the single most likely place for an implementer to
produce something that looks right in a quick test (one run, works fine)
and is wrong in use (second run silently erases the first). Spelling out
both branches and the eviction rule removes the guess.

**D9 — Routing predicate is `isSelfEditRun(name, tools)`, and this plan
states plainly that it is currently equivalent to `name === "developer"`.**
Runs where it returns true render in the Developer tab; all others render
as satellite-anchored cards exactly as today.
*Rationale and correction:* the superseded dock plan's D1 claimed this
predicate meant "Developer doing an ordinary task stays anchored like
everyone else." **That claim is false.** The implementation
(`AgentStatusPanel.tsx:99-107`) is:
```ts
const n = name.toLowerCase();
return n.includes("self") || n.includes("edit") || n.includes("develop")
    || tools.some((t) => t.toLowerCase().startsWith("selfedit"));
```
`name` is the agent key, so `"developer".includes("develop")` is `true`
for every developer run before any tool is called. We keep using the
function — it is one definition, already used for the stage readout, and
it would also correctly catch a future agent named e.g. `selfedit` — but
the plan does not pretend it discriminates between self-edit and ordinary
developer work. Consequence to expect and accept: the Developer satellite
at the pentagon apex will never show an anchored card.

**D10 — Run state moves out of `AgentStatusPanel` into a module-level
store** (`web/src/agentRuns.ts`), following the exact publish/subscribe
shape already used by `agentLayout.ts`'s `publishFieldRect` /
`subscribeFieldRect` and `wakeWord.ts`'s `subscribeWake`. `AgentStatusPanel`
subscribes and renders non-Developer runs; the Developer tab subscribes and
renders Developer runs; the RTVI `ServerMessage` listener that maintains the
store lives in exactly one place.
*Rationale:* the Developer tab's body unmounts whenever another tab is
active or the drawer is closed. If run state lived in that component, a
self-edit's progress would be destroyed by a tab switch — the user would
open the tab mid-run and see nothing. State must therefore outlive both
components. A module store is chosen over lifting to `App` + prop drilling
because `AgentStatusPanel` and `SideDrawer` are siblings, so lifting would
mean threading state and a setter through `App` purely as a pass-through,
and because module-level publish/subscribe is the convention this file set
already established twice.
**Single-listener rule:** after this change exactly one component
registers `useRTVIClientEvent(RTVIEvent.ServerMessage, ...)` for agent
lifecycle messages. Registering it in both `AgentStatusPanel` and the
Developer tab would double-apply every event.

### Resizing and persistence

**D11 — Resize handle on the drawer's LEFT edge.** A 6px-wide hit target
(1px visible hairline) spanning the drawer's full height,
`cursor: col-resize`. Implemented with Pointer Events —
`pointerdown` + `setPointerCapture`, `pointermove`, `pointerup` — not
mouse events, so a drag that leaves the window still tracks.
*Rationale:* left edge is where the user asked for it and where it belongs
(the drawer grows leftward into the stage). `setPointerCapture` is what
makes drag-outside-the-element work without a document-level listener.

**D12 — Width bounds and throttling.** `DRAWER_DEFAULT_WIDTH_PX = 400`,
`DRAWER_MIN_WIDTH_PX = 300`, `DRAWER_MAX_WIDTH_PX` = `min(720,
window.innerWidth * 0.6)` evaluated at drag time. Width writes during a
drag are coalesced into one `requestAnimationFrame` callback. Double-click
on the handle resets to `DRAWER_DEFAULT_WIDTH_PX`.
*Rationale:* min 300 because `.memory-panel`/`.runs-panel` content stops
being legible below roughly that; the 60vw ceiling prevents dragging the
stage out of existence on a small window. rAF coalescing matters more than
usual here because every width change resizes `.orb-field`, which fires
the `ResizeObserver`, which re-renders every anchored card — an unthrottled
`pointermove` would run that chain at input-event frequency.

**D13 — Persist to `localStorage` under `mortimer.drawer.*`:**
`mortimer.drawer.width` (number), `mortimer.drawer.open` (boolean),
`mortimer.drawer.tab` (one of the five `TabKey`s). All reads are wrapped in
`try/catch` and validated: width parsed as a number, rejected if `NaN`,
then clamped to `[DRAWER_MIN_WIDTH_PX, DRAWER_MAX_WIDTH_PX]`; tab checked
against `TAB_KEYS`; anything missing, unparseable, or out of range falls
back to the D6 defaults (`open: false`, `tab: "runs"`,
`width: DRAWER_DEFAULT_WIDTH_PX`).
**Hydration timing:** read in the `useState` lazy initializer —
`useState<number>(() => readStoredWidth())` — not in a `useEffect`. Writes
happen in a `useEffect` keyed on each value.
*Rationale for the initializer:* hydrating in an effect renders one frame
at the default before correcting, which is a visible flash of a
wrong-width or wrongly-closed drawer on every page load. The initializer
runs before first paint. Validation on read because `localStorage` is
user-editable and survives across builds — a stale key from a future or
older version must not be able to render an unknown tab or a 3px drawer.
*Rationale:* width and tab are exactly the kind of preference that is
annoying to reset every reload. Validation on read because localStorage is
user-editable and a stale key from a future/older build must not be able
to render an unknown tab or a 3px-wide drawer. This is the app's own
origin, not a sandboxed artifact — `localStorage` is available and
appropriate.

### Interactions with existing work

**D14 — Fix the `window.innerWidth` clamp in `computeAnchoredStyle`.**
`AgentStatusPanel.tsx:139-150` clamps card position against
`window.innerWidth` / `window.innerHeight`. With a pushing drawer the
usable stage no longer extends to the window's right edge, so a
right-clamped card would slide *underneath* the drawer. Change the
horizontal bounds to derive from the field rect
(`fieldRect.left` and `fieldRect.left + fieldRect.width`) instead of
`window.innerWidth`. Vertical bounds keep using `window.innerHeight`
(unchanged — the drawer does not affect vertical extent).
*Rationale:* this is a real bug that push introduces, and it is invisible
in review because it only manifests with the drawer open. The field-rect
bound is also strictly more correct today (with the drawer closed the
field spans the full width, so the two are equivalent) — this is not a
special case for the drawer, it is the bound that was always meant.

**D15 — New constant `ANCHORED_CARDS_MIN_STAGE_PX = 720`, separate from
the existing `ANCHORED_CARDS_MIN_WIDTH_PX = 860`.** The existing constant
stays a *viewport* threshold (it mirrors the `@media (max-width: 860px)`
breakpoint). The new one is a *stage* threshold: when the measured field
width is below it, anchored cards fall back to the stacked bottom-left
column even though the viewport is wide. Exact change in
`AgentStatusPanel.tsx:298` — from:
```ts
const canAnchor = viewportWidth >= ANCHORED_CARDS_MIN_WIDTH_PX && fieldRect !== null;
```
to:
```ts
const canAnchor =
  viewportWidth >= ANCHORED_CARDS_MIN_WIDTH_PX &&
  fieldRect !== null &&
  fieldRect.width >= ANCHORED_CARDS_MIN_STAGE_PX;
```
*Rationale:* one number cannot mean both things. A 1200px window with a
420px drawer open leaves a 780px stage — wide viewport, cramped stage.
Reusing the 860 viewport number would either wrongly anchor five cards
into a narrow stage or wrongly disable anchoring on a wide window with the
drawer shut. Two thresholds, two constants, both `⚙ TUNING KNOB` entries in
`agentLayout.ts` alongside the existing ones.

**D16 — Below `ANCHORED_CARDS_MIN_WIDTH_PX` (860px viewport) the drawer
overlays instead of pushing.** In that media query the drawer becomes
`position: fixed; top: 52px; right: 0; bottom: 0; width: 100vw` — matching
what `.drawer` already does at `command-deck.css:508-510`. Because it
leaves normal flow, `.stage-row` is left with one in-flow child (`.main`),
which needs no rule of its own.
In overlay mode:
- **the persisted width is ignored** (the drawer is `100vw`) but is NOT
  overwritten — widening the window past 860px restores the user's stored
  width unchanged;
- the inline `flexBasis` from D25 is inert, since `position: fixed`
  removes the element from flex layout — no JS branch is needed, the media
  query alone handles it;
- **the resize handle is hidden** (`display: none`) — there is nothing
  meaningful to drag on a full-width overlay;
- **a CLOSED drawer must not render at all.** D23 keeps the drawer element
  always mounted so the push/slide transition has something to animate —
  but `position: fixed` combined with "always mounted" and no closed-state
  rule means a closed drawer below 860px would cover the entire screen.
  The media query must therefore include:
  ```css
  @media (max-width: 860px) {
    .side-drawer:not(.side-drawer-open) { display: none; }
    .side-drawer.side-drawer-open { transition: none; }
  }
  ```
  The second rule is a direct consequence of the first — `display: none`
  cannot participate in a transition, so pushing/sliding is only
  meaningful in the push layout above the breakpoint; below it, open and
  closed are a hard cut, not an animation.
*Rationale:* pushing on a 700px window leaves no usable stage; below this
width the honest behavior is a full-screen panel. Reusing the existing
860px breakpoint (and the constant that already mirrors it) keeps one
number in play rather than introducing a third. The closed-state rule is
not optional — without it, D16 and D23 combine into a bug where the app
becomes unusable on any narrow window until the drawer happens to be
opened once.

**D17 — The side drawer and the transcript drawer are mutually
exclusive.** Opening either closes the other. The transcript drawer is NOT
converted into a sixth tab in this plan.
*Rationale:* both occupy the right edge at z-20; open together they would
overlap with no defined winner. Mutual exclusion is one line of state
coordination and no new visual design. Converting the transcript into a
tab is the obviously better end state and an easy follow-up, but it would
mean reworking `TranscriptDrawer`'s open/close contract and its `T`
shortcut, which is scope this change does not need to carry.

**D18 — SUPERSEDED. Do not implement.** Replaced by D28 (payload routing)
and D36 (how the split is decided). Original text and the reason it was
wrong: Appendix A.

**D19 — Panel chrome moves to the drawer.** The four panel components keep
their internals, but inside the drawer their own box styling is
neutralized by a scoped override. All four class names are **verified
against source** (`GitPanel.tsx:82,90`; `EditModePanel.tsx:188,199`;
`MemoryPanel.tsx:77,86,95`; `RunsPanel.tsx:144,152`) — write this selector
literally:
```css
.side-drawer-body :is(.git-panel, .editmode-panel, .memory-panel, .runs-panel) {
  width: 100%;
  max-width: none;
  max-height: none;
  border: none;
  border-radius: 0;
  background: transparent;
  padding: 0;
}
```
Scrolling becomes the drawer body's job (`overflow-y: auto` on
`.side-drawer-body`), not each panel's.
*Rationale:* `.runs-panel` hardcodes `width: 460px` and `max-height:
70vh`, `.memory-panel` similar — dropped unmodified into a 400px drawer
they would overflow horizontally and introduce a second, nested scrollbar.
Overriding at the drawer boundary (rather than editing each panel's CSS)
keeps the panels renderable standalone and keeps this change reversible in
one place. **Verify `.editmode-panel` is the actual class name in
`editmode.css` before writing the selector** — confirm, do not assume.

**D20 — Accessibility and motion.** Tab strip gets `role="tablist"`, each
tab `role="tab"` + `aria-selected`, the body `role="tabpanel"`. Topbar
buttons get `aria-expanded` — each button reports whether ITS OWN tab is
the one currently open (`drawerOpen && drawerTab === thisTab`), not
whether the drawer as a whole is open; five buttons all claiming
`aria-expanded="true"` while only one panel is visible would misreport
the actual state. The resize handle gets `role="separator"`,
`aria-orientation="vertical"`, and Left/Right arrow keys that adjust
width by 16px per press (clamped by D12).
**`tabIndex` on the resize handle is `open ? 0 : -1`, not an unconditional
`0`.** D23 makes the closed drawer `aria-hidden="true"` (nothing inside it
should be reachable) and separately sets `pointer-events: none` on the
handle — but `pointer-events: none` has no effect on keyboard focus, so an
unconditional `tabIndex={0}` would leave a Tab-reachable control inside an
`aria-hidden` subtree, which is an accessibility fault (assistive tech and
the DOM disagree about whether the element exists). Tying `tabIndex` to
`open` closes that gap using the same signal already driving
`aria-hidden`, rather than a second one that could drift out of sync.
A `@media (prefers-reduced-motion: reduce)` block disables the
`flex-basis` transition (D25).

**`Escape` is a single window-level `keydown` listener** registered in
`App.tsx` in the same `useEffect` as the existing `T` handler, using the
same `isTypingTarget(e.target)` guard, and it closes the drawer only when
`drawerOpen` is true. It is **not** scoped to focus-within.
*Rationale:* a drag-only resize is unusable by keyboard, and this never
gets retrofitted. Window-level `Escape` because a push-layout drawer has
no backdrop to click away and the user's hands may be nowhere near it —
and because it matches the existing `T` handler's shape exactly, so there
is one keyboard pattern in this file rather than two. The
`isTypingTarget` guard means `Escape` inside a panel's text input does not
close the drawer out from under the user mid-edit; that is intended.

**D21 — Deletions and non-deletions.** Delete: `.git-popover` and
`.git-popover .git-panel` from `command-deck.css`, and the four
`<div className="git-popover">` wrappers in `App.tsx`. Do NOT delete: the
legacy `.orb-wrap` rules in `App.css:259+` and their media-query
counterpart, which are already unused by the current `App.tsx` and are
unrelated to this change.
*Rationale:* removing `.git-popover` is required (it is what is being
replaced); removing `.orb-wrap` is unrelated cleanup that would enlarge
the diff and the blast radius of a revert.

**D22 — No new dependency.** Tabs, the drawer, and the resize handle are
hand-rolled. No headless-UI or resizable-panel library is added.
*Rationale:* the surface is small (one tab strip, one pointer drag), and
`web/package.json` is deliberately lean. A dependency here would be more
code to audit than to write.

### Gaps closed in revision 2

**D23 — The drawer ELEMENT is always mounted; the drawer BODY is mounted
only while open.** Concretely, in `App.tsx` the drawer is rendered
unconditionally — `<SideDrawer open={drawerOpen} … />`, never
`{drawerOpen && <SideDrawer … />}` — and inside `SideDrawer`, the tab strip
and the active tab's body render only when `open` is true. When closed the
root keeps `flex-basis: 0` and `overflow: hidden`, and the resize handle
gets `pointer-events: none` so an invisible handle cannot be grabbed.
Consequences, all intended:
- The push/slide transition works, because the element exists on both sides
  of the state change (you cannot transition an element into existence).
- Exactly one panel is mounted at any time (the active tab's), and zero
  while closed — so no panel polls or fetches in the background behind a
  closed drawer.
- Panels **refetch on open and on every tab switch.** Accepted: all four
  are cheap admin-sidecar reads, and fresh data on open is the desirable
  behavior for a panel you just chose to look at.
- This is a *second* unmount path (in addition to tab switching) that the
  D10 run store must survive. It is the reason D10 is not optional.
*Rationale:* the alternative — keeping bodies mounted at zero width to
preserve their internal state — buys nothing here (none of the four panels
holds unsaved user input; the only state worth preserving is run state,
which D10 moves out anyway) and costs background network activity behind a
drawer the user has closed.

**D24 — Exact module and component contracts.** These are consumed by more
than one component and are therefore specified member-by-member. Implement
them as written.

`web/src/agentRuns.ts` public surface:
```ts
export interface RunState {           // moved verbatim from AgentStatusPanel
  id: number; name: string; displayName: string; task: string;
  tools: string[]; stage: number; startedAt: number;
  doneAt: number | null; ok: boolean; detail: string;
}

export type RunsListener = (runs: RunState[]) => void;

export const STAGES: readonly ["planning", "proposing", "validating", "submitting"];
export const DONE_FADE_MS: number;        // 8000, unchanged
export const MAX_TOOLS: number;           // 10, unchanged
export const MAX_DEVELOPER_RUNS: number;  // 20, new (D8)

/** Current runs, oldest first. Treat the returned array as immutable. */
export function getRuns(): RunState[];

/** Returns an unsubscribe function — same contract as
 *  agentLayout.ts's subscribeFieldRect. Listeners fire synchronously
 *  after each mutation, with the new array. */
export function subscribeRuns(cb: RunsListener): () => void;

/** Type-guards internally; a message of unrecognized shape is ignored.
 *  This is the ONLY function that mutates run state from RTVI events. */
export function applyServerMessage(msg: unknown): void;

export function removeRun(id: number): void;
export function isSelfEditRun(name: string, tools: string[]): boolean;
export function fmtElapsed(ms: number): string;
export function toolStage(tool: string): number;
export function clamp(s: string, max: number): string;
```

`TabKey` is defined in `SideDrawer.tsx` and imported by `App.tsx` — one
definition, not a duplicated union:
```ts
// Six tabs — "output" added by D35. This is the complete, current union;
// there is no five-key version to reconcile against.
export type TabKey =
  "repo" | "edit" | "memory" | "runs" | "developer" | "output";
export const TAB_KEYS: readonly TabKey[];   // same order as the tab strip

export interface SideDrawerProps {
  open: boolean;
  activeTab: TabKey;
  width: number;                       // px; ignored while closed (D23)
  onTabChange: (tab: TabKey) => void;
  onClose: () => void;                 // wired to a close control — see D27
  onWidthChange: (width: number) => void;
}
export default function SideDrawer(props: SideDrawerProps): React.ReactElement;
```

`DeveloperRunsTab` takes no props (it subscribes to `agentRuns.ts`
directly): `export default function DeveloperRunsTab(): React.ReactElement`.
*Rationale:* revision 1 named these functions without signatures. Two
components must agree on them, and "subscribe returns an unsubscribe" was
assumed from `subscribeFieldRect` rather than stated — exactly the class of
omission that produces two subtly different implementations. Return type
is `React.ReactElement`, not the bare global `JSX.Element` revision 2
specified — under React 19's module-scoped JSX types, `JSX` is not
reliably resolvable as an unqualified name inside a `.tsx` module without
an explicit import, and `React.ReactElement` is the stable equivalent
already available from the `react` import every component file has
regardless. This is a correction to revision 2, not a new requirement —
component behavior is unaffected either way; only write the annotation
that actually compiles.

**D25 — Width is applied as `flexBasis` via inline style; the transition is
on `flex-basis`; dragging suspends it.**
- `SideDrawer`'s root element: `style={{ flexBasis: open ? width : 0 }}`.
- `.side-drawer { flex-grow: 0; flex-shrink: 0; overflow: hidden;
  transition: flex-basis 0.28s ease; }` — 0.28s matches the existing
  `.drawer` transition (`command-deck.css:219`) so the two drawers feel
  the same.
- While a pointer drag is active, `SideDrawer` adds
  `.side-drawer-resizing`, which sets `transition: none`. Removed on
  `pointerup`.
- `@media (prefers-reduced-motion: reduce) { .side-drawer { transition:
  none; } }` (D20).
*Rationale:* inline `flexBasis` rather than a CSS custom property because
the value is React state that changes per drag frame — a style object is
the direct expression and avoids a second source of truth. The
`.side-drawer-resizing` escape hatch matters: without it, every drag frame
starts a fresh 280ms ease and the handle feels like it is dragging through
mud.

**D26 — Labels, button order, and active styling.** This table is the
single source of truth for the topbar row and the tab strip — D35 adds the
`output` row and adds nothing else; there is no separate table to
reconcile.

Topbar buttons, left to right after `VoicePicker`:

| Order | Topbar label | Tab strip label | Tab key |
|---|---|---|---|
| 1 | `⚙ Repo` | Repo | `repo` |
| 2 | `✎ Edit` | Edit | `edit` |
| 3 | `🧠 Memory` | Memory | `memory` |
| 4 | `📋 Runs` | Runs | `runs` |
| 5 | `🛠 Dev` | Developer | `developer` |
| 6 | `📄 Output` | Output | `output` |
| 7 | `Log` | — (transcript drawer, unchanged) | — |

Tab strip labels are plain words, no icons — the icons live only in the
topbar.

`.btn-active` (in `App.css`, following the existing `.btn-mic-on`
pattern at `App.css:466`):
```css
.btn-active {
  border-color: var(--accent-dim);
  color: var(--accent);
}
```
*Rationale:* icons in the topbar (already the convention there) and plain
words in the tab strip (where the icons would be redundant and the row is
narrow). `🛠 Dev` rather than `Developer` to keep the topbar from
wrapping. Note that `Edit` and `Dev` are deliberately distinct: `Edit` is
the self-edit *control* panel, `Dev` is self-edit *run status*. Merging
them is a plausible future change and explicitly not this one.

### Gaps closed in revision 3

**D27 — The drawer has its own in-panel close control, separate from the
topbar toggle.** A `×` button, `.side-drawer-close`, sits at the right end
of the tab strip (after the five tabs, same row), `aria-label="Close
drawer"`, `onClick={onClose}`.
*Rationale:* `SideDrawerProps.onClose` was specified in D24 with no caller.
Closing via the topbar button (D5's re-click case) still works and is
unaffected by this — this is a second, in-context way to close once
already inside the drawer, the same convenience `TranscriptDrawer` already
gives its own panel (`drawer-head`'s "Close (T)" button,
`TranscriptDrawer.tsx:14-16`). Without D27, `onClose` is a documented but
unreachable prop.

### The Output tab (D28–D35)

**D28 — Display payloads split by category: work product goes to the
Output tab, informational answers keep a floating window.** Routing is by
the `surface` field (D36):
- **`surface: "drawer"`** — `app_create`, `app_write_file`,
  `git_diff_summary`, `prepare_commit`, `commit`, `prepare_push`, `push`.
  These render in the Output tab per D29/D32/D33.
- **`surface: "window"`** — `web_search`, `get_weather`,
  `get_weather_radar`. These render in `DisplayPanel`, which **survives
  unchanged** as a floating in-page window (drag, resize, `×`,
  `z-index: 30` all kept) and additionally gains a pop-out into a real
  browser window that can be parked on a second monitor (D39–D42).

`DisplayPanel.tsx` is **not** deleted, and none of the `.display-panel` /
`.display-head` / `.display-resize` CSS is deleted (see D33). The payload
*rendering* — markdown via `marked` + `DOMPurify`, the 9-tile seamless
radar grid, the gallery, the link list — is extracted once and shared by
all three consumers (D43).
*Rationale:* a weather forecast or research brief is the answer to a
question you just asked out loud — you look at it, absorb it, move on.
Filing it into a drawer tab turns a transient answer into an archive entry
and takes it off the screen you were watching. A diff or commit summary is
the opposite: reference material read carefully while doing something
else, which is exactly what a pushed drawer is for. The earlier version of
this decision collapsed both into one surface on the premise that
"`DisplayPanel` was wrong" — it was in fact right for half its traffic.
See Appendix A for that superseded text.

**D29 — Display payloads live in a module-level store,
`web/src/displayResults.ts`, exactly mirroring `agentRuns.ts`.** Same
publish/subscribe shape, same reasons (D10): the Output tab body unmounts
on tab switch and on drawer close, so state cannot live in it.
```ts
export interface DisplayPayload {      // moved from DisplayPanel.tsx
  kind?: string;                       // "markdown" | "image" | "links"
  title?: string;
  body?: string;                       // markdown
  images?: string[];
  links?: { label?: string; url: string }[];
  agent?: string;
  ts?: number;                         // epoch SECONDS — see D34
}

/** One received payload plus a client-side identity, since the payload
 *  itself has no id and two results can be identical. */
export interface DisplayResult {
  id: number;                          // monotonic, assigned on arrival
  payload: DisplayPayload;
  receivedAt: number;                  // Date.now(), ms — see D34
}

export type DisplayListener = (results: DisplayResult[]) => void;

/** ⚙ TUNING KNOB — bounded history; oldest dropped first. */
export const MAX_DISPLAY_RESULTS = 20;

/** Newest FIRST (opposite of agentRuns.getRuns(), which is oldest-first —
 *  a results log reads newest-down, a run list reads oldest-up). */
export function getResults(): DisplayResult[];
export function subscribeResults(cb: DisplayListener): () => void;

/** Type-guards internally; ignores anything that is not
 *  {type: "display", display: {...}}. The ONLY mutator from RTVI events. */
export function applyServerMessage(msg: unknown): void;

export function removeResult(id: number): void;
export function clearResults(): void;
```
*Rationale:* one more module store rather than a new pattern, because the
constraint is identical to D10's and the codebase now has this shape three
times (`agentLayout`, `wakeWord`, `agentRuns`). Newest-first is stated
explicitly because it differs from `agentRuns.getRuns()` — an implementer
who assumes symmetry gets the list upside down.

**D30 — Exactly one RTVI listener for `type === "display"` messages, and
it lives in `App.tsx`.** It calls `displayResults.applyServerMessage`.
Note this is a *different* listener from D10's agent-lifecycle one in
`AgentStatusPanel` — two `useRTVIClientEvent(RTVIEvent.ServerMessage, …)`
registrations coexist because they filter on different `type` values, and
that is fine. What must not happen is two listeners for the *same* `type`.
*Rationale:* the listener has to outlive the Output tab body, so it cannot
live in `OutputTab.tsx`. `App.tsx` is already the permanently-mounted
component that subscribes to `agentRuns` for the D7 indicator, so it is
the established home for "always-on wiring the drawer reads."

**D31 — A new DRAWER-ROUTED result auto-opens the drawer to the Output tab
ONLY when the drawer is closed; otherwise it shows a live dot and does not
steal the current tab.** This rule applies exclusively to
`surface: "drawer"` payloads (D28/D36) — an informational payload never
opens, switches, or dots the drawer, it goes to the window (D41).
Exact rule, on each new drawer-routed payload:
- drawer closed → open it, set active tab to `output`;
- drawer open on `output` → nothing (the new item simply appears, newest
  first, and is auto-expanded per D32);
- drawer open on any other tab → **do not switch tabs.** Show
  `.btn-live-dot` on the `📄 Output` topbar button and
  `.side-drawer-tab-dot` on the Output tab, exactly as D7 does for
  Developer runs. The dot clears when the Output tab is next made active.
*Rationale:* the floating window's one real virtue was announcing itself,
and a tab behind a closed drawer announces nothing — this preserves
that. But yanking the user off the Memory panel mid-read because a
background `web_search` returned would be worse than the problem being
solved, hence the "only when closed" clause. Auto-opening is acceptable
here specifically *because* the drawer pushes rather than covers (D2):
the stage narrows, nothing is obscured.

**D32 — The Output tab is a bounded, newest-first list of collapsible
items, not a single slot.** Each item renders a header row — title ·
agent · relative time — that toggles its body open. The newest item on
arrival is auto-expanded; all others start collapsed. One expanded item at
a time, mirroring `RunsPanel`'s existing expand/collapse behavior
(`RunsPanel.tsx:122-140`). Each item has a `×` that calls `removeResult`;
the tab header has a "Clear" button that calls `clearResults`. When the
list exceeds `MAX_DISPLAY_RESULTS` the oldest is dropped.
*Rationale:* the floating window held exactly one payload and replaced it
silently, which is tolerable for a window you dismiss immediately and not
tolerable for a panel you consult. Collapsing is required because a single
`web_search` body plus a 20-line diff block would otherwise make the tab
unscrollable in practice.

**D33 — CSS: delete nothing; the `.display-*` rules gain a second and
third consumer.** An earlier version of this decision listed the floating
window's chrome for deletion; D28 keeps the window, so **that delete list
is void** (Appendix A). No rule in `command-deck.css` is removed by this
plan.
KEEP UNCHANGED — now shared by `DisplayPanel`, `OutputTab`, and
`DisplayWindowApp` via `DisplayContent` (D43): `.display-body`,
`.display-tiles`, `.display-tiles img`, `.display-gallery`,
`.display-gallery img`, every `.display-markdown *` rule, `.display-links`,
`.display-links li`, `.display-links a`, `.display-links a:hover`.
New list chrome (`.output-item`, `.output-item-head`, `.output-item-body`,
`.output-empty`, `.output-clear`) goes in `sidedrawer.css`, styled to
match `.runs-row` / `.runs-detail` rather than inventing a third visual
language for the same idea.
*Rationale:* the markdown/table/code styling is the valuable part and is
independent of how any container is positioned, which is exactly why three
different containers can share it. Stating "delete nothing" explicitly
prevents the predictable error of following the superseded delete list and
stripping the markdown styling out from under the window that is now
keeping it.

**D34 — `ts` is epoch SECONDS; `relTime` takes ISO. Extract a shared
millisecond-based helper.** New `web/src/timeFormat.ts`:
```ts
/** "12s ago" / "5m ago" / "3h ago" / "2d ago" from a millisecond epoch. */
export function relTimeFromMs(ms: number): string;
/** Same, from an ISO 8601 string. */
export function relTime(iso: string): string;   // = relTimeFromMs(Date.parse(iso))
```
`RunsPanel.tsx` deletes its local `relTime` (`RunsPanel.tsx:75-84`) and
imports it; `OutputTab` calls `relTimeFromMs(result.receivedAt)`.
**Do not call `relTime` or `new Date()` on `payload.ts` directly** — it is
seconds (`time.time()`, `jarvis/bot/display.py:77`), so `new Date(ts)`
yields January 1970. `DisplayResult.receivedAt` (D29) exists precisely so
the UI has an unambiguous millisecond timestamp and never has to reason
about the payload's unit; treat `payload.ts` as metadata only.
*Rationale:* a unit mismatch across a language boundary that produces a
plausible-looking wrong answer (a date, just the wrong one) rather than a
crash. Isolating the conversion in the store, at the single point of
arrival, means no consumer can get it wrong.

**D35 — `TabKey` gains `"output"`; topbar gains `📄 Output` before `Log`.**
The full six-tab union is given in D24 and the full seven-button topbar row
in D26 — both already include `output`. D35 adds nothing beyond those two
tables; do not maintain a third copy.

D6's default tab is unchanged (`runs`). A stored
`mortimer.drawer.tab` value of `output` is now valid and must pass D13's
`TAB_KEYS` validation automatically — no migration needed, since an
unknown value already falls back to the default.
*Rationale:* `📄 Output` last among the tabs because it is the one the
system opens *for* you (D31) rather than the one you navigate to. **Risk
worth noting:** this makes seven controls in the topbar plus brand,
connect button, and voice picker. At narrow-but-above-860px widths the row
may wrap. If it does, the fix is to drop the emoji from the topbar labels
(the tab strip already carries plain words) — not to remove a tab.

### The informational window (D36–D43)

**D36 — Routing is decided server-side by a new `surface` field on the
payload, set per tool in `jarvis/bot/display.py`.** Add alongside
`DISPLAY_TOOLS`:
```python
# Which surface a tool's result belongs on (side-drawer plan D36).
# "window" — an answer to a question the user just asked: glanceable,
#            transient, and on a multi-monitor setup parkable on a second
#            screen. "drawer" — work product: read carefully, kept.
DISPLAY_SURFACE: dict[str, str] = {
    "web_search":        "window",
    "get_weather":       "window",
    "get_weather_radar": "window",
    "app_create":        "drawer",
    "app_write_file":    "drawer",
    "git_diff_summary":  "drawer",
    "prepare_commit":    "drawer",
    "commit":            "drawer",
    "prepare_push":      "drawer",
    "push":              "drawer",
}
DEFAULT_DISPLAY_SURFACE = "drawer"
```
`build_display_payload` adds `"surface": DISPLAY_SURFACE.get(tool,
DEFAULT_DISPLAY_SURFACE)` to the returned dict. The frontend treats a
missing or unrecognized `surface` as `"drawer"` too, so an older bot
talking to a newer console degrades to the non-intrusive behavior.
*Rationale:* the decision belongs next to `DISPLAY_TOOLS`, which is
already the single place that knows which tools are display-worthy —
splitting that knowledge across the language boundary is how the two
drift. The default is `"drawer"` deliberately: a window that appears
unprompted is the more intrusive outcome, so intrusiveness is opt-in per
tool rather than the fallback. **Do not route on `kind`** — it is
`markdown`/`image`/`links`, and both categories produce `markdown`.

**D37 — The single display listener in `App.tsx` (D30) dispatches on
`surface`.** One `useRTVIClientEvent(RTVIEvent.ServerMessage, …)`
registration for `type === "display"`, which then either calls
`displayResults.applyServerMessage(payload)` (drawer) or
`displayWindow.publish(payload)` (window). D30's single-listener-per-type
rule is unchanged — this is still one listener, now with a two-way branch.

**D38 — The display window shows the latest informational payload only —
no history.** A new informational payload replaces the current one, which
is exactly what `DisplayPanel` does today (`setItem` replaces). The Output
tab's bounded history (D32) is for work product only.
*Rationale:* preserves current behavior rather than inventing a new one,
and nothing is actually lost — every tool result, displayed or not, is
already recorded durably in the run log (`agent_events` + the JSONL
payload, `MORTIMER_RUN_LOGGING_PLAN.md`), reviewable in the Runs tab.
Adding history to a glance-at-it window would also make its "assigned to a
second screen" role worse, not better: a wall display should show the
current answer, not a scrollback.

**D39 — The popped-out window is a SECOND VITE ENTRY (`display.html` +
`web/src/displayMain.tsx`), not a query-param mode of the main entry.**
`vite.config.ts` gains:
```ts
build: { rollupOptions: { input: {
  main: resolve(__dirname, "index.html"),
  display: resolve(__dirname, "display.html"),
} } }
```
`displayMain.tsx` renders `<DisplayWindowApp />` and **must not import
`./jarvisClient`**, directly or transitively.
*Rationale:* importing `jarvisClient` has side effects at module load —
it calls `installMicConstraints()` (which monkey-patches `getUserMedia`)
and constructs a `PipecatClient` with a `SmallWebRTCTransport`
(`jarvisClient.ts:8-14`). A query-param branch inside `main.tsx` would not
prevent this, because ES imports are hoisted and evaluated regardless of
which branch runs — the popup would patch its own `getUserMedia` and build
a transport for a session it must never open. A separate entry makes the
popup's module graph genuinely exclude all of it, which is a correctness
guarantee rather than a tidiness preference. In dev, the popup is just
`/display.html`; the `rollupOptions.input` change is only needed for
`npm run build`.

**D40 — Payloads reach the popup over `BroadcastChannel("mortimer.display")`,
with a replay handshake.** New `web/src/displayWindow.ts`, imported by
both entries:
```ts
export const DISPLAY_CHANNEL = "mortimer.display";

type DisplayMessage =
  | { t: "payload"; payload: DisplayPayload }
  | { t: "hello" }        // popup -> console: "I just opened, send current"
  | { t: "clear" };

/** Console side: publish to the in-page window AND the channel. */
export function publish(payload: DisplayPayload): void;
/** Popup side: subscribe. Returns an unsubscribe function. */
export function subscribeDisplay(cb: (m: DisplayMessage) => void): () => void;
```
The popup posts `{t:"hello"}` on mount; the console replies by
re-publishing its current payload, so a window opened *after* a result
arrived is not blank. `BroadcastChannel` is same-origin and same-browser,
which is exactly the stated deployment (multiple monitors, one machine).
*Rationale:* the payload arrives on the console's WebRTC data channel and
the popup has no session, so relaying is the only option. `BroadcastChannel`
over `localStorage` events because it is purpose-built, structured-cloneable,
and does not pollute storage. **Explicit limit, stated so nobody assumes
otherwise:** this does NOT cross devices. A second *machine* as a display
would need server-side fan-out (the bot or admin sidecar publishing over a
websocket) — a different and larger piece of work, deliberately out of
scope here per the scoping answer.

**D41 — Pop-out is user-initiated and gracefully degrades; the preference
is remembered but never forces a blocked popup.**
- `DisplayPanel`'s header gains a `⧉` pop-out button. Clicking it calls
  `openDisplayWindow()` → `window.open("/display.html", "mortimer-display",
  features)`. The fixed window **name** is what makes the browser reuse and
  remember the same window across opens.
- While a live popup exists (`popupRef && !popupRef.closed`), the in-page
  window renders nothing — the payload is showing on the other screen.
- The preference persists as `mortimer.display.popout` (boolean,
  `localStorage`, same guarded-read discipline as D13).
- **Popup blockers:** `window.open` outside a user gesture is blocked, and
  it returns `null`. So when an informational payload arrives with
  `popout === true` but the window has been closed, the console attempts
  the reopen, and **if `window.open` returns `null` it falls back to the
  in-page floating window** and shows the `⧉` button again. It must never
  swallow the payload waiting for a window that will never appear.
*Rationale:* this is the failure mode that turns a nice feature into "my
weather results stopped showing up." Auto-reopen is attempted because it
works in the common case (the window is merely hidden behind another, or
the browser allows it), but the fallback path is mandatory, not an
optimization.

**D42 — Programmatic screen assignment (Window Management API) is
DEFERRED, and `openDisplayWindow()` is the seam it will use.** Today the
function takes no placement and passes default `window.open` features; the
user drags the popup to the target monitor once and the browser remembers.
A later change gives it an optional placement argument and consults
`window.getScreenDetails()` to position the popup on a chosen screen, plus
a picker in settings.
*Rationale for deferring:* it needs a `window-management` permission
prompt, is Chromium-only, and — the constraint that actually matters here
— **requires a secure context.** The console is served over
`http://localhost:5173`, which *is* a secure context, so this will work on
this machine. It would silently not exist if a future deployment served
the console to another machine over plain LAN HTTP. Recording that now so
the constraint is discovered at design time rather than when the picker
mysteriously fails to appear.

**D43 — The window and the Output tab share rendering, not chrome.** The
markdown/tiles/gallery/links rendering (`renderMarkdown`, the
`images.length === 9` seamless rule, the link list) is extracted into
`web/src/components/DisplayContent.tsx`, taking `{ payload }`, and used by
`DisplayPanel`, `OutputTab`, and `DisplayWindowApp`. The `.display-body`
/ `.display-markdown` / `.display-tiles` / `.display-gallery` /
`.display-links` CSS is shared by all three; the window keeps
`.display-panel`/`-head`/`-resize`, the tab uses `.output-item*` (D33's
keep list), and the popup gets a minimal `.display-window` full-bleed
block in a new `web/src/displaywindow.css`.
*Rationale:* three consumers of one rendering path is exactly when to
extract it; leaving it inline in `DisplayPanel` and copying it twice is
how the radar's 9-tile special case ends up fixed in one place and broken
in two.

---

## §4 Files that will change

**New:**

| Path | Purpose |
|---|---|
| `web/src/components/SideDrawer.tsx` | Drawer host, tab strip, resize handle (D4/D5/D11) |
| `web/src/components/DeveloperRunsTab.tsx` | Developer tab body (D8/D9) |
| `web/src/agentRuns.ts` | Module-level run store + RTVI reducer (D10) |
| `web/src/sidedrawer.css` | `.stage-row`, `.side-drawer*`, panel overrides (D19) |
| `tests/acceptance/side-drawer.md` | Manual checklist |
| **rev 4:** `web/src/components/OutputTab.tsx` | Output tab body (D28/D32) |
| **rev 4:** `web/src/displayResults.ts` | Drawer-routed payload store (D29) |
| **rev 4:** `web/src/timeFormat.ts` | Shared `relTime`/`relTimeFromMs` (D34) |
| **rev 5:** `web/src/components/DisplayContent.tsx` | Shared payload rendering, 3 consumers (D43) |
| **rev 5:** `web/src/displayWindow.ts` | `BroadcastChannel` relay + `openDisplayWindow` (D40/D41/D42) |
| **rev 5:** `web/display.html` | Second Vite entry for the popup (D39) |
| **rev 5:** `web/src/displayMain.tsx` | Popup entry — must not import `jarvisClient` (D39) |
| **rev 5:** `web/src/components/DisplayWindowApp.tsx` | Popup root (D39/D40) |
| **rev 5:** `web/src/displaywindow.css` | Full-bleed popup layout (D43) |

**Deleted:** nothing. Revision 4 proposed deleting
`web/src/components/DisplayPanel.tsx`; D28 keeps it (narrowed to
informational payloads).

**Modified:**

| Path | Change |
|---|---|
| `web/src/App.tsx` | `.stage-row` wrapper, drawer state + localStorage hydration, topbar buttons → tab selectors, `🛠 Dev` button + D7 indicator (read-only `subscribeRuns`), `Escape` branch, remove four `.git-popover` wrappers |
| `web/src/App.css` | `.btn-active` style for the active tab button |
| `web/src/command-deck.css` | Remove `.git-popover` rules (D21) |
| `web/src/components/AgentStatusPanel.tsx` | Consume `agentRuns.ts`; filter out Developer runs; D14 clamp fix; D15 stage threshold |
| `web/src/agentLayout.ts` | Add `ANCHORED_CARDS_MIN_STAGE_PX` (D15) |
| `MORTIMER_DEVELOPER_DOCK_PLAN.md` | Mark SUPERSEDED (header note only) |
| `CLAUDE.md` | One paragraph under Architecture describing the drawer + the sidecar/drawer naming rule |
| **rev 4:** `web/src/components/SideDrawer.tsx` | `TabKey` gains `"output"`, `TAB_KEYS`/`TAB_LABELS` gain it, `OutputTab` added to `renderBody` (D35) |
| **rev 4:** `web/src/App.tsx` | `📄 Output` topbar button + dot, D30 display listener, D31 auto-open rule, D37 surface dispatch; `<DisplayPanel />` STAYS |
| **rev 4:** `web/src/components/RunsPanel.tsx` | Delete local `relTime`, import from `timeFormat.ts` (D34) |
| **rev 5:** `jarvis/bot/display.py` | `DISPLAY_SURFACE` map + `surface` on the payload (D36) |
| **rev 5:** `tests/unit/test_display.py` | Assert `surface` per tool + the unknown-tool default (D36) |
| **rev 5:** `web/src/components/DisplayPanel.tsx` | Narrowed to informational payloads; `⧉` pop-out button; renders via `DisplayContent` (D28/D41/D43) |
| **rev 5:** `web/vite.config.ts` | `build.rollupOptions.input` gains the `display` entry (D39) |
| **rev 5:** `web/src/command-deck.css` | No deletions (D33's delete list is void); `.display-*` rules now shared by three consumers |

---

## §5 Implementation steps

**5.1 — `web/src/agentRuns.ts`** (new). Move these out of
`AgentStatusPanel.tsx` **unchanged in behavior, not necessarily unchanged
in code shape** — see the note below: `RunState`, `AgentLifecycleMsg`,
`clamp`, `fmtElapsed`, `toolStage`, `isSelfEditRun`, `STAGES`,
`DONE_FADE_MS`, `MAX_TOOLS`. (`STAGES` moves because both
`AgentStatusPanel` and `DeveloperRunsTab` render the stage readout —
leaving it behind would mean a second copy. `computeAnchoredStyle` does
NOT move; it is positioning logic and stays in `AgentStatusPanel`.)
Add a module-level `runs: RunState[]`, `subscribeRuns(cb)`, `getRuns()`,
`applyServerMessage(msg)`, `removeRun(id)`, and the fade-timer
bookkeeping (`timers`, `runIds`, `seq` — currently `useRef`s, now module
state), implementing D8a's two-branch replacement/eviction rule and
`MAX_DEVELOPER_RUNS = 20` (D8).

**Not literally verbatim, and that's fine:** the original `removeRun`
also pruned `AgentStatusPanel`'s `cardHeights` map, which is React
component state (`useState`) and cannot be touched from a plain module.
The store's `removeRun` prunes run state only; `AgentStatusPanel` gets a
small `useEffect` that prunes its own `cardHeights` for ids no longer
present in the subscribed run list. This is a mechanical consequence of
splitting one component's internals into a module plus a consumer, not a
new design decision — the observable behavior (a removed run's measured
height is forgotten) is unchanged.

**5.2 — `AgentStatusPanel.tsx`**: subscribe to `agentRuns.ts` instead of
owning state; keep exactly one `useRTVIClientEvent` registration, which
calls `applyServerMessage` (D10 single-listener rule); filter its render
list to `!isSelfEditRun(r.name, r.tools)`; apply the D14 clamp fix and the
D15 stage threshold. Card markup unchanged.

**5.3 — `web/src/components/DeveloperRunsTab.tsx`** (new): subscribes to
`agentRuns.ts`, renders `isSelfEditRun` runs newest-first, capped at
`MAX_DEVELOPER_RUNS`, reusing the existing `agent-card*` classes and the
stage readout. Registers no RTVI listener of its own.

**5.4 — `web/src/components/SideDrawer.tsx`** (new): props `{ open,
activeTab, onTabChange, onClose, width, onWidthChange }`. Renders the tab
strip (D4/D20), the resize handle (D11/D12/D20), and the active body —
`GitPanel | EditModePanel | MemoryPanel | RunsPanel | DeveloperRunsTab`.

**5.5 — `web/src/sidedrawer.css`** (new): `.stage-row` (D3),
`.side-drawer` sizing/`flex-basis`/transition, `.side-drawer-tabs`,
`.side-drawer-body` (`overflow-y: auto`), `.side-drawer-handle`, the D19
panel overrides, the D16 narrow-viewport overlay block, and the D20
reduced-motion block.

**5.6 — `App.tsx`**, in this order:
1. Replace the four panel booleans with `{ drawerOpen, drawerTab,
   drawerWidth }`, each hydrated via a `useState` lazy initializer (D13),
   with a `useEffect` per value writing back to `localStorage`.
2. Wrap `<main className="main">` and `<SideDrawer …/>` in
   `<div className="stage-row">`. **`error-banner` stays OUTSIDE and above
   `.stage-row`** — it is a full-width bar in the `.app` column, not part
   of the stage row.
3. Render the drawer unconditionally, passing `open` (D23) — never
   `{drawerOpen && …}`.
4. Implement the D5 three-case click matrix for all five tab buttons, and
   add `.btn-active` (D26) to the button matching `drawerTab` while open.
5. Remove the four `<div className="git-popover">` blocks and the now-unused
   panel imports (`GitPanel`, `EditModePanel`, `MemoryPanel`, `RunsPanel`
   move into `SideDrawer.tsx`).
6. Add the `🛠 Dev` topbar button (D26) with the D7 live indicator. **This
   requires `App.tsx` to subscribe to the run store** — `useEffect(() =>
   subscribeRuns(setRuns), [])` — and derive
   `const devRunning = runs.some(r => isSelfEditRun(r.name, r.tools) && r.doneAt === null)`.
   This subscription is read-only; it must NOT register a second
   `useRTVIClientEvent` listener (D10's single-listener rule).
7. Wire D17 mutual exclusion: opening the drawer sets `drawerOpen` and
   clears `drawerOpen`'s counterpart — opening the transcript drawer sets
   `drawerOpen = false`, and opening/switching the side drawer sets
   `drawerOpen`(transcript) `= false`.
8. Extend the existing `T` `useEffect` with the D20 `Escape` branch, reusing
   its `isTypingTarget` guard.

**5.7 — `command-deck.css`**: delete the `.git-popover` rules (D21).
**`App.css`**: add `.btn-active`.

**5.8 — Docs**: `MORTIMER_DEVELOPER_DOCK_PLAN.md` header gets a
`**SUPERSEDED by MORTIMER_SIDE_DRAWER_PLAN.md**` line explaining that the
dock became a drawer tab. `CLAUDE.md` gains a short **Console side
drawer** paragraph under *Architecture*, stating the D1 naming rule
explicitly.

### Revision 4 steps (5.9–5.13) — the Output tab

Revisions 1–3 are already implemented; these steps apply on top of the
shipped code.

**5.9 — `web/src/timeFormat.ts`** (new): `relTimeFromMs(ms)` and
`relTime(iso)` per D34, lifted from `RunsPanel.tsx:75-84`. Update
`RunsPanel.tsx` to import it and delete its local copy — behavior
identical, one definition.

**5.10 — `web/src/displayResults.ts`** (new): the D29 store. Move
`DisplayPayload` here from `DisplayPanel.tsx`. `applyServerMessage`
filters `msg.type === "display" && msg.display`, assigns a monotonic `id`
and `receivedAt: Date.now()`, prepends (newest-first), and truncates to
`MAX_DISPLAY_RESULTS`.

**5.11 — `web/src/components/OutputTab.tsx`** (new): subscribes to
`displayResults`, renders the D32 collapsible newest-first list. The
markdown/image/link rendering bodies are lifted verbatim from
`DisplayPanel.tsx:142-170` (including `renderMarkdown` and the
`images.length === 9` seamless-tile rule); only the surrounding container
and header change. Registers no RTVI listener (D30).

**5.12 — `SideDrawer.tsx`**: add `"output"` to `TabKey`, `TAB_KEYS`, and
`TAB_LABELS`; add the `OutputTab` case to `renderBody`; extend the
existing `devRunning` dot logic with an equivalent
`newOutput` subscription so the Output tab shows `.side-drawer-tab-dot`
per D31.

**5.13 — `App.tsx`**: add the `📄 Output` topbar button with
`.btn-live-dot` (D35/D31); register the D30 display listener and, in that
same handler, apply D37's `surface` branch — `"drawer"` goes to
`displayResults.applyServerMessage` and then D31's three-case auto-open
rule; `"window"` goes to `displayWindow.publish`. **Keep the
`<DisplayPanel />` mount** (D28 — an earlier draft's instruction to delete
it is recorded in Appendix A and must not be followed).

### Revision 5 steps (5.14–5.17) — the informational window

**5.14 — `jarvis/bot/display.py`** (D36): add `DISPLAY_SURFACE`,
`DEFAULT_DISPLAY_SURFACE`, and `"surface"` in the dict returned by
`build_display_payload`. Extend `tests/unit/test_display.py` to assert the
surface of at least one tool from each category plus the unknown-tool
default. This is the only backend change in the whole plan.

**5.15 — `web/src/components/DisplayContent.tsx`** (new, D43): lift the
markdown/tiles/gallery/links rendering out of `DisplayPanel` verbatim,
taking `{ payload }`. Update `DisplayPanel` and `OutputTab` to use it.

**5.16 — `web/src/displayWindow.ts`** (new, D40/D41/D42): the
`BroadcastChannel` wrapper, `publish`, `subscribeDisplay`, the hello/replay
handshake, `openDisplayWindow()`, and the `mortimer.display.popout`
preference with guarded reads. Then `DisplayPanel` gains the `⧉` button,
the "hidden while a live popup exists" rule, and the popup-blocker
fallback (D41).

**5.17 — the popup entry** (D39): `web/display.html`,
`web/src/displayMain.tsx`, `web/src/components/DisplayWindowApp.tsx`,
`web/src/displaywindow.css`, and the `vite.config.ts` input change.
`DisplayWindowApp` subscribes via `subscribeDisplay`, posts `{t:"hello"}`
on mount, and renders `DisplayContent` full-bleed. **Verify by grepping
the popup's import graph that `jarvisClient` is not reachable from
`displayMain.tsx`.**

---

## §6 Where the tuning knobs live

`DRAWER_DEFAULT_WIDTH_PX` (400), `DRAWER_MIN_WIDTH_PX` (300),
`DRAWER_MAX_WIDTH_PX` (D12's `min(720, innerWidth * 0.6)`),
`DRAWER_RESIZE_KEY_STEP_PX` (16, D20) in `SideDrawer.tsx`;
`MAX_DEVELOPER_RUNS` (20) in `agentRuns.ts` — all as
`⚙ TUNING KNOB` constants, matching the convention in `agentLayout.ts` and
`jarvis/runlog/store.py`. `ANCHORED_CARDS_MIN_STAGE_PX` joins the existing
knobs in `agentLayout.ts`. No `.env` setting and no backend config — this
is per-user UI preference, and it lives in `localStorage` (D13).

---

## §7 Verification

**Automated — must all pass:**

1. `cd web && npm run build` — strict TS + production build (the CI gate
   in `.github/workflows/validate.yml`).
2. `cd web && npm run lint` — oxlint.
3. `pytest tests/unit/test_agents_yaml_frontend_parity.py -q` — this test
   regexes `key: "..."` out of `agentLayout.ts`; adding a constant must not
   break it. Adding `ANCHORED_CARDS_MIN_STAGE_PX` introduces no `key:`
   literal, so it should pass unchanged — confirm rather than assume.
4. `pytest tests/unit tests/integration -q` — unchanged, no Python touched.

**Note:** `web/` has no JS test runner (`package.json` has vite, tsc,
oxlint — no vitest/jest). Do not add one as part of this change; frontend
verification is the build, the linter, and the manual checklist below.
Revision 5's one backend change (D36) IS unit-testable and must be —
`tests/unit/test_display.py` already exists and covers
`build_display_payload`.

**Revision 5 additionally requires:** `cd web && npm run build` must emit
**both** `index.html` and `display.html` (D39) — confirm both appear in
the build output, since a missing `rollupOptions.input` entry fails
silently at build time and only surfaces as a 404 when the popup is
opened from a production build.

**Manual — `tests/acceptance/side-drawer.md`, written in this phase:**

- Open each of the five tabs; confirm exactly one body is visible and no
  two panels ever overlap (the §1.1 defect).
- Click the active tab's topbar button; confirm the drawer closes and
  reopens to the same tab.
- With the drawer open, confirm the orb, satellites, and mic controls are
  all visible and clickable — nothing is covered.
- Drag the left edge; confirm the stage re-centers live and the satellites
  follow, with no visible stutter.
- Drag to both extremes; confirm the width clamps and the stage never
  disappears.
- Reload; confirm width, open state, and active tab are restored.
- Trigger a delegation to a non-Developer agent with the drawer open;
  confirm its anchored card stays fully left of the drawer and never slides
  underneath (D14).
- Narrow the window below 860px; confirm the drawer overlays full-width and
  status cards fall back to the stacked column.
- Start a self-edit run with the drawer CLOSED; confirm the Developer
  topbar button shows the live indicator (D7), then open the tab and
  confirm the run's progress is intact, not restarted or missing (D10).
- Let a self-edit run finish, wait 15s, then open the Developer tab;
  confirm the completed run is still listed (D8).
- Run two Developer delegations back to back; confirm BOTH appear in the
  Developer tab and the second did not erase the first (D8a — the
  highest-risk regression in this plan).
- Open the transcript drawer while the side drawer is open; confirm one
  closes the other (D17).
- Tab to the resize handle and use Left/Right arrows; confirm the width
  changes (D20).
- Press `Escape` with the drawer open; confirm it closes. Press `Escape`
  while the cursor is in a panel's text input; confirm it does NOT close
  (D20's `isTypingTarget` guard).
- Open a panel, close the drawer, reopen it; confirm the panel refetches
  and shows current data rather than a stale snapshot (D23).
- Watch the network tab with the drawer closed for 30s; confirm no panel
  is polling behind it (D23).
- Shrink the window below 860px with a custom width saved; confirm the
  drawer goes full-width and the handle disappears. Widen it again;
  confirm the saved custom width returns unchanged (D16).

**Revision 4 — Output tab:**

- With the drawer CLOSED, ask for something that produces a display
  payload (e.g. "what are the working tree changes" → `git_diff_summary`,
  or a web search). Confirm the drawer auto-opens to the Output tab with
  the result expanded (D31), and that nothing floats over the stage.
- With the drawer OPEN on the Memory tab, trigger another payload.
  Confirm the tab does NOT switch, and the `📄 Output` topbar button and
  Output tab both show a live dot (D31). Click Output; confirm the dot
  clears.
- Trigger three payloads in a row. Confirm all three are listed
  newest-first, the newest is expanded, and the older two are collapsed
  (D32).
- Expand an older item; confirm the previously-expanded one collapses
  (one at a time).
- Dismiss one item with its `×`, then use "Clear"; confirm both work and
  the empty state renders (D32).
- Confirm a `get_weather_radar` result still renders as a seamless 3×3
  tile grid, and a `web_search` result still renders markdown with its
  link list (D28 — rendering reused, not rewritten).
- Confirm each item's relative time is sane ("12s ago", not "56y ago") —
  a 1970 timestamp means `payload.ts` was used instead of
  `receivedAt` (D34).
- Confirm the topbar row does not wrap at ~900px with seven controls
  present (D35's noted risk); if it does, drop the emoji from the topbar
  labels rather than removing a tab.

**Revision 5 — informational window and pop-out:**

- Ask for weather and then for a web search. Confirm each opens the
  floating window and that **neither touches the drawer** — no auto-open,
  no Output dot, nothing added to the Output tab (D28/D31).
- Ask for the working tree changes. Confirm it goes to the Output tab and
  does **not** open the floating window (D36 routing both ways).
- Click `⧉` in the window header. Confirm a real browser window opens, and
  that the in-page window disappears while it is open (D41).
- Drag the popup to the second monitor. Ask for weather. Confirm the
  result appears on that monitor and the console screen is untouched.
- Close the popup, then ask for weather again. Confirm the result is NOT
  lost — either the popup reopens or the in-page window comes back with
  the `⧉` button (D41's mandatory fallback). A blocked popup that swallows
  the payload is a failure.
- Reload the console with the popup preference on; confirm it is
  remembered (D41).
- Open the popup, then ask for weather, then close and immediately reopen
  the popup. Confirm the current result is shown rather than a blank
  window (D40's hello/replay handshake).
- Ask for a weather radar with the popup open; confirm the 3×3 seamless
  tile grid renders there correctly (D43 — shared rendering, not a copy).
- Confirm the popup never prompts for microphone access and the console's
  voice session is unaffected while it is open (D39 — no `jarvisClient` in
  the popup's module graph).

---

## §8 Rollback

Frontend-only, no schema, no persisted server state. Full revert is
`git revert` of the phase branch. A user left with stale
`mortimer.drawer.*` keys after a revert is unaffected — nothing reads them.
There is no feature flag: a flag would mean maintaining both the popover
and the drawer layout simultaneously, which is more risk than the revert
it protects against.

---

## §9 Risk

| Risk | Severity | Mitigation |
|---|---|---|
| Ambient awareness of self-edit runs is lost when the drawer is closed. | **High** | D7's topbar indicator is the whole answer, and it is a required part of this plan rather than a nicety. If it is cut, this design is a regression against today's behavior — the acceptance checklist tests it explicitly with the drawer closed. |
| Moving run state out of `AgentStatusPanel` breaks the live card lifecycle (fade timers, per-agent replacement). | Medium | 5.1 preserves observable behavior even where the code shape must change (see the `cardHeights` note in 5.1). The acceptance checklist re-tests the existing card behaviors (fade on success, persist on failure, replacement on a new run for the same agent) after the move. |
| D8's Developer history is silently erased by the existing per-agent replacement rule. | **High** | D8a spells out both branches and the eviction rule explicitly. This is the failure mode that passes a one-run smoke test and fails in real use; the acceptance checklist runs two consecutive Developer runs and asserts both are listed. |
| Two RTVI listeners double-apply every lifecycle event. | Medium | D10's explicit single-listener rule; symptom is duplicated tool chips, which the checklist would catch. |
| Width transition + `ResizeObserver` + five anchored cards causes visible jank. | Medium | D12's rAF coalescing on drag. The open/close CSS transition will still fire the observer once per frame for ~280ms; this is accepted (two subscribers, cheap handlers) and is checked by eye in the acceptance list. |
| `.git-popover` removal breaks a panel that depended on its box (padding, background). | Low | D19's scoped overrides supply the chrome at the drawer boundary; each panel is opened and inspected in the checklist. |
| The 860px overlay breakpoint and the 720px stage threshold interact confusingly at some widths. | Low | Two distinct constants with distinct meanings (D15/D16), both tunable in one file; the checklist exercises the narrow case explicitly. |
| **rev 4:** auto-opening the drawer on a new result (D31) is experienced as the UI grabbing focus. | Medium | Scoped to the drawer-closed case only, and it pushes rather than covers (D2) — nothing is obscured, the stage narrows. If it still annoys, the fallback is dot-only with no auto-open, a one-line change to D31's first clause. |
| **rev 4:** deleting `.display-panel` CSS takes the markdown styling with it. | Medium | D33 enumerates the delete list and the keep list explicitly rather than saying "remove the display styles"; the checklist re-renders a markdown result and a radar grid after the change. |
| **rev 4:** `payload.ts` (seconds) used where milliseconds are expected, yielding 1970 dates. | Medium | D34 adds `receivedAt` in the store so no consumer touches `payload.ts`, and the checklist asserts on the rendered relative time specifically. |
| **rev 5:** a popup blocked by the browser silently swallows an informational result. | **High** | D41 makes the in-page fallback mandatory when `window.open` returns `null`, and the checklist tests exactly this sequence (close popup → ask again → result must still appear somewhere). |
| **rev 5:** the popup imports `jarvisClient` transitively and opens a second WebRTC session or grabs the mic. | Medium | D39's separate Vite entry makes it structurally impossible rather than merely discouraged; §5.17 requires grepping the import graph, and the checklist watches for a mic prompt. |
| **rev 5:** `BroadcastChannel` is assumed to work across devices in a future deployment. | Medium | D40 states the same-browser limit explicitly and names what a multi-device setup would actually require (server-side fan-out), so the wrong assumption cannot be made silently. |
| **rev 5:** the Window Management API is added later against a non-secure-context deployment and silently does nothing. | Low | D42 records the secure-context requirement now, while `http://localhost` still satisfies it, rather than leaving it to be discovered when the picker fails to appear. |

---

## §10 Approval

**Revisions 1–3:**

- [x] Larry has read §2 (scope) and §3 (decisions) and approves —
  2026-08-14.
- [x] Implementation may begin — implemented 2026-08-14 by a separate
  model working from revision 2 with no access to the originating
  conversation. `tsc -b` clean, `vite build` succeeds, `oxlint` exit 0
  (3 `only-export-components` warnings, see revision-3 note), Python suite
  558 passed / 3 skipped with one pre-existing unrelated network failure
  (`test_mcp_web_server`). Revision 3 then closed the six gaps that pass
  surfaced; no code changes were needed for it, the implementation had
  already made the right call in each case.

**Revisions 4 + 5 (Output tab and the informational window, D28–D43):**

These are one unit of work — revision 5 amends revision 4 before either
was built, so they are approved and implemented together, not in sequence.

- [x] Larry has read D28–D43 and approves — 2026-08-14 ("implement the
  plan no additional approval needed. start to finish").
- [x] Implementation may begin — implemented 2026-08-14. All files in §4's
  rev-4/rev-5 rows exist as specified; `DisplayPanel.tsx` was narrowed
  (not deleted, per D28) and gained the `⧉` pop-out and the D41 fallback.
  `cd web && npm run build` succeeds and emits both `index.html` and
  `display.html` (confirmed via the build manifest, plus a grep of the
  `display` bundle showing zero `getUserMedia` references against four in
  the `main` bundle — D39's isolation guarantee holds). `npm run lint`:
  0 errors (3 pre-existing `only-export-components` warnings, unrelated).
  `tests/unit/test_display.py` extended with `TestDisplaySurface` (D36).
  Python suite: 563 passed / 3 skipped, one pre-existing unrelated
  network failure (`test_mcp_web_server`, same as revisions 1–3).
  `tests/acceptance/side-drawer.md` gained the Output-tab and
  informational-window checklists — not yet walked against a live
  two-monitor session.

---

## Appendix A — superseded decisions (RECORD ONLY, NEVER IMPLEMENT)

Nothing in this appendix is an instruction. It exists so the change in
intent between drafts stays legible without leaving stale instructions
interleaved with live ones in §3. If you are implementing, you can skip
this section entirely.

**A.1 — D18, as originally written (revision 1; reversed before any code
was written).**

> *`DisplayPanel` is not repositioned, and keeps painting above the
> drawer. Drawer at `z-index: 20`, `DisplayPanel` unchanged at
> `z-index: 30`. `DisplayPanel` is a transient results window that is
> deliberately in front of everything; making it dodge the drawer means
> teaching it about drawer width for a window the user dismisses in
> seconds. Accepted limitation, recorded so a future implementer does not
> think it was overlooked. Revisit only if it proves annoying in
> practice.*

**Why it was wrong:** "dismissed in seconds" was an assumption about usage,
not an observation of it. On first real use the window held a 21-file
`git_diff_summary` — reference material, read carefully. It also spawns at
`x = innerWidth - 540 - 48`, hard against the right edge, so it reliably
landed *on top of* the drawer it was supposed to coexist with. Replaced by
D28 (split by category) and D36 (how the split is decided).

**A.2 — D28, as originally written (revision 4; amended before any code
was written).**

> *`DisplayPanel` stops being a floating window and becomes the drawer's
> sixth tab, "Output." The floating chrome is deleted outright:
> `position: fixed` placement, header drag, corner resize, and the
> `pos`/`size` state that drives them. The component file is replaced by
> `web/src/components/OutputTab.tsx`; `DisplayPanel.tsx` is deleted.*

**Why it was wrong:** it over-corrected A.1. Having established that the
floating window was wrong for diffs, revision 4 concluded it was wrong for
everything — but it was right for half its traffic. A weather forecast or
research brief is a glanceable answer to a spoken question, and filing it
in a drawer tab turns it into an archive entry. The live D28 splits by
category instead.

**A.3 — D31, as originally written (revision 4).** Identical to the live
D31 except that it applied to *all* display payloads rather than only
`surface: "drawer"` ones. The live version adds that qualification;
nothing else changed.

**A.4 — D33's delete list (revision 4). VOID.**

> *From `command-deck.css`, DELETE: `.display-panel`, `.display-head`,
> `.display-head:active`, `.display-title`, `.display-agent`,
> `.display-close`, `.display-resize`, and the `.display-panel` override
> in the `@media (max-width: 860px)` block.*

**Why it is void:** it was a direct consequence of A.2 deleting the
floating window. D28 keeps the window, so every rule above is still in
use. The live D33 deletes nothing.
