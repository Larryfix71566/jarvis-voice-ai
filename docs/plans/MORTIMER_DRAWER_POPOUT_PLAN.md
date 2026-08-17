# MORTIMER DRAWER POP-OUT — implementation plan

**Goal (Larry, 2026-08-17).** The side drawer — the right-side tabbed
panel (Repo / Edit / Memory / Runs / Dev / Output / Log) — should be
poppable into a real second browser window that parks on the extra
monitor, exactly as the display window already does, so the whole
console can live two-screen: wave + voice on the laptop, work surfaces
on the big screen.

**Naming (unchanged rule, MORTIMER_SIDE_DRAWER_PLAN.md D1):** this is
the side DRAWER and its popped form is the **drawer window** — never
"sidecar", which in this codebase means the admin Python process on
`:7861`.

**Why this is a plan and not a patch.** The display window pops out
cleanly because its content is one relayed payload. The drawer's tabs
have four different data supply lines, one of which (the Log) is
currently welded to the voice session object that must never exist in a
second window (`displayMain.tsx`'s D39 rule: no `jarvisClient.ts` in the
popup import graph). Popping the drawer means untangling that, not just
opening a window.

**Ground rule (same as every plan in this repo):** every decision below
has already been made. Implement it exactly as written; if something is
genuinely undecided, that is a defect in this document — stop and report
it rather than choosing.

---

## §1 Decisions

### DP1 — A third Vite entry: `drawer.html`

`web/drawer.html` + `web/src/drawerMain.tsx` + 
`web/src/components/DrawerWindowApp.tsx`, registered beside
`display.html` in the Vite build config (same mechanism, whatever form
that registration takes there today). Hard rule carried over verbatim
from D39: the entry's import graph must never reach `jarvisClient.ts`
(module-load side effects patch `getUserMedia` and construct a
`PipecatClient`) nor use any `@pipecat-ai/client-react` hook.
`DrawerWindowApp` renders the drawer's tab strip and exactly one active
body, full-bleed (no width drag — the OS window is the size control),
reusing the SAME tab-body components the in-page drawer mounts
(`GitPanel`, `EditModePanel`, `MemoryPanel`, `RunsPanel`,
`DeveloperRunsTab`, `OutputTab`, `Transcript`). Its active tab persists
under `localStorage["mortimer.drawerwin.tab"]` — deliberately a separate
key from `mortimer.drawer.tab` (two windows sharing one key would fight
over it).

### DP2 — Shared pop-out plumbing: `popoutWindow.ts`

The display window already solved presence (alive/bye/ping/close
heartbeat, 2026-08-17) and extended-screen placement (D42). Those parts
of `displayWindow.ts` are EXTRACTED into one shared module,
`web/src/popoutWindow.ts`, exposing:

- `createPopoutChannel(name)` — BroadcastChannel + the presence
  protocol (hello/alive/bye/ping/close message types, `isAlive()`,
  ref-recovery via named-window reuse) exactly as `displayWindow.ts`
  implements it today;
- `placeOnExtendedScreen(win, slot)` — the Window Management API
  placement, with a new `slot` argument (see DP8);
- `openPopout(url, name, features)` — open/refocus/re-place, the shape
  `openDisplayWindow` has today.

`displayWindow.ts` is refactored to consume this module with ZERO
behavior change (same channel name `mortimer.display`, same messages,
same localStorage keys). The drawer window uses it with channel
`mortimer.drawerwin` and window name `mortimer-drawer`. One
implementation, two windows — a presence bug can no longer exist in
only one of them.

### DP3 — Data supply: relay the RTVI-fed stores, leave HTTP panels alone

The drawer's tabs split cleanly by supply line:

- **HTTP panels — no relay, no change:** `GitPanel`, `EditModePanel`,
  `MemoryPanel`, `RunsPanel` fetch the admin sidecar (`:7861`) directly;
  they work identically from the drawer window. (The sidecar already
  runs CORS middleware; the acceptance checklist verifies the popup
  origin is accepted.)
- **RTVI-fed module stores — relayed:** `agentRuns.ts` (Dev tab, run
  chips) and `displayResults.ts` (Output tab, pending-draft amber) are
  fed only by the console's single RTVI listener (`AgentStatusPanel`,
  D10 — that rule is untouched). The console side republishes every
  store event onto the drawer channel; the drawer window applies them to
  its own module-store copies. The tab components are UNCHANGED — they
  already read the stores, and the stores are simply fed differently in
  each context.
- **Replay handshake (the display's D40 pattern, generalized):** on
  `hello`, the console responds with full snapshots — the current runs
  list, the current results list, and the conversation tail (DP4),
  capped at the stores' existing bounds — so a drawer window opened
  mid-session is never blank.

### DP4 — The Log tab: `conversationFeed.ts` unwelds it from the session

`Transcript.tsx` currently calls `usePipecatConversation` — a session
hook, unusable in the drawer window. New module store
`web/src/conversationFeed.ts` (same publish/subscribe shape as
`agentRuns.ts`, bounded at 200 entries): the console feeds it from a
headless component in `App.tsx` (the ONLY remaining
`usePipecatConversation` consumer), and `Transcript.tsx` switches to
reading the store. One code path serves both contexts; the console
relays feed events over the drawer channel like the other two stores.
The E7 run-chip merge logic in `Transcript.tsx` is unchanged (it already
reads `agentRuns`).

### DP5 — Single-place rule (same as the display window)

While a drawer window is alive (presence heartbeat), the in-page drawer
does not render its body and the topbar Panels button switches meaning:
label `◪ Panels ⧉`, title "Panels are on the display screen — click to
focus/move", click = `openPopout` (refocus + re-place) instead of
opening in-page. Closing the drawer window (its own close box, or voice)
returns the drawer to in-page mode with its prior open/tab state — the
same fallback-never-loses-anything rule as D41. The aggregate
live/new/attention dot stays on the Panels button in BOTH modes (it is
fed by the same stores either way).

### DP6 — Controls: one new button, two new voice actions

- A `⧉` button at the right end of the drawer window's OWN tab strip is
  NOT needed (it is already popped); the pop-out control is a `⧉` at the
  right end of the IN-PAGE drawer's tab strip, beside the close ×.
- `jarvis/bot/ui_control.py` gains two actions: `drawer_popout` (pop the
  drawer to the second screen; noop-with-reason if already popped) and
  `drawer_popin` (close the drawer window, return in-page; noop if not
  popped). `UI_CONTROL_ADDENDUM` in `jarvis/prompts.py` gains one
  sentence naming them ("send the panels to the display screen" /
  "bring the panels back"). Existing `drawer_open`/`drawer_tab` actions
  act wherever the drawer currently lives: when popped, the console
  forwards them over the drawer channel (the uiCommands dispatch gains
  one forwarding branch, keyed on drawer-window presence).
- Routing-eval: two cases pinning that these utterances are `ui_control`
  usage, never developer delegations (same rationale as the existing
  U8 cases).

### DP7 — What deliberately does NOT move

Mic controls, wake word, sound toggle, the voice wave, ambient strip,
captions: console-only, always. The drawer window is a work surface, not
a second console — it never requests the mic, never renders the wave,
and never registers RTVI anything (true by construction: no
`jarvisClient.ts` in its graph).

### DP8 — Two windows, one extra screen: deterministic slots

`placeOnExtendedScreen(win, slot)` with `slot: "fill" | "left" | "right"`:

- Only one pop-out alive → it takes `"fill"` (today's display behavior).
- Both alive on the same extended screen → display takes `"left"` (60%
  of `availWidth`), drawer takes `"right"` (40%) — work product reads
  denser than informational payloads. Each open/re-place recomputes
  both placements (the shared module keeps a registry of its live
  popouts, so opening the second one repositions the first).
- More than two screens: display on the first non-console screen,
  drawer on the second if present, else the split above.
- Safari (no Window Management API): open unplaced, drag by hand —
  feature-detected fallback, zero errors.

### DP9 — Persistence keys

`mortimer.drawerwin.tab` (DP1) and the popout preference
`mortimer.drawerwin.popout` (mirrors `mortimer.display.popout`: set by
`⧉`/voice popout, cleared by popin/close; when true, the console
re-opens the drawer window on next session load IF a user gesture is
available — i.e. it re-opens on the first click anywhere, matching
browser popup rules, and simply stays in-page until then). Same guarded
try/catch localStorage discipline as every `mortimer.*` key.

### DP10 — No kill switch

The drawer window exists only when explicitly opened (click or voice),
costs nothing when closed, and reverts to in-page rendering by simply
not being open. Same rationale as the planning pathway's no-kill-switch
decision.

---

## §2 Files

**New:** `web/drawer.html`, `web/src/drawerMain.tsx`,
`web/src/components/DrawerWindowApp.tsx`, `web/src/popoutWindow.ts`
(extracted shared plumbing), `web/src/conversationFeed.ts`,
`tests/acceptance/drawer-popout.md`.

**Modified:** `web/src/displayWindow.ts` (consume `popoutWindow.ts`,
zero behavior change); `web/src/components/Transcript.tsx` (read
`conversationFeed`); `web/src/App.tsx` (headless conversation feeder,
store relay onto the drawer channel, Panels-button popped state,
uiCommands forwarding branch); `web/src/components/SideDrawer.tsx`
(tab-strip `⧉`, body hidden while popped); Vite build config (third
entry); `web/src/command-deck.css` + `web/src/sidedrawer.css` (drawer
window chrome); `jarvis/bot/ui_control.py` + its unit tests
(`drawer_popout`/`drawer_popin`); `jarvis/prompts.py`
(`UI_CONTROL_ADDENDUM` sentence); `tests/evals/cases.yaml` (two
ui-not-developer cases); `CLAUDE.md` (drawer paragraph addendum).

**Untouched, load-bearing:** `AgentStatusPanel`'s single-RTVI-listener
rule (D10); `displayMain.tsx`; the admin sidecar (no new endpoints —
the drawer window is a pure client of existing ones).

---

## §3 Implementation order

1. `popoutWindow.ts` extraction + `displayWindow.ts` refactor onto it;
   tsc/lint; manual check that display pop-out behavior is unchanged.
2. `conversationFeed.ts` + `Transcript.tsx` store switch + App feeder —
   in-page Log identical before any window exists.
3. `drawer.html`/`drawerMain.tsx`/`DrawerWindowApp` + Vite entry; store
   relay + replay handshake; HTTP panels verified from the popup.
4. DP5 single-place rule + DP6 controls (in-page `⧉`, ui_control
   actions, prompt sentence, uiCommands forwarding).
5. DP8 slot placement in the shared module.
6. Acceptance checklist; full pytest (ui_control tests); web build/lint;
   routing eval cases (live, Larry).

---

## §4 Verification (tests/acceptance/drawer-popout.md, key items)

- [ ] `⧉` in the drawer pops a window; in Chrome it lands on the extra
      screen; with the display window also open, display left 60% /
      drawer right 40%.
- [ ] Every tab works in the popped window: Repo/Edit/Memory/Runs (HTTP),
      Dev + Output (relayed stores), Log (conversationFeed) — including a
      window opened mid-session showing existing runs/output/transcript
      (replay handshake).
- [ ] While popped: in-page drawer body hidden, Panels button shows the
      popped state, "show me the runs" by voice switches the POPPED
      window's tab.
- [ ] Console reload while popped: still popped, no double drawer
      (presence heartbeat), Panels click refocuses.
- [ ] "Bring the panels back" (voice) and closing the window both return
      the in-page drawer with prior state.
- [ ] The drawer window never prompts for mic access (D39-equivalent
      holds).
- [ ] Safari: everything works minus auto-placement; drag once.
- [ ] Full pytest + web build/lint clean; routing eval ≥ 90% including
      the two new ui cases.

---

## §5 Risks

| Risk | Level | Mitigation |
|---|---|---|
| `displayWindow.ts` refactor regresses display pop-out | Medium | Step 1 lands alone with a manual behavior check before anything else builds on it |
| Transcript store switch changes Log behavior in-page | Low | Step 2 lands alone; store is a pass-through of the same hook data |
| Two-window placement fights (both grab "fill") | Low | Single shared registry in `popoutWindow.ts` owns all placement (DP8) |
| Sidecar CORS rejects the popup origin | Low | Same origin as the console in practice (same dev server); acceptance item verifies |
| BroadcastChannel relay volume (chatty stores) | Low | Stores are already bounded; relay is per-event, no polling |

---

## §6 Rollback

Each step reverts file-by-file. `popoutWindow.ts` extraction is the only
step other work depends on — reverting it means also reverting steps
3–5, which is why it lands first and alone. Stale
`mortimer.drawerwin.*` keys are ignored by reverted code. No migrations,
no backend endpoints, nothing to clean server-side except the two
ui_control actions (self-contained in one module + its tests).

---

## §7 Approval

- [ ] Larry approves.
- [ ] Implementation may begin.
