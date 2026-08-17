# MORTIMER ENGAGEMENT DESIGN — implementation plan

**Problem.** The console's design review (2026-08-16) found a coherent
command-deck language undermined by one central gap: nothing answers
"is it alive?" The idle state is dead air (no ambient content), internal
states (thinking, needs-confirmation) are visually mute, connecting is
indistinguishable from a form submitting, the audio identity is one
chime deep, and the interface's signature — the agent star map — is
decoration rather than instrument.

**Choices locked with Larry (2026-08-16):** full ambient dashboard;
full state system; full boot sequence; four-tone sound palette; full
satellite instrumentation; memory card redesign; transcript action
chips; empty-state hints. Packaged as ONE plan, TWO phases: Phase 1
"alive" (E1–E4), Phase 2 "instruments" (E5–E8).

**Design constraints that govern everything below:** the screen stays
glanceable-ambient — nothing added may demand interaction or compete
with voice; the wave keeps its motion monopoly (no motion soup);
`prefers-reduced-motion` is honored everywhere; all client work stays
inside `web/src/**` (the self-edit allowlist — these are exactly the
tasks the loop should someday do); no new external API calls anywhere
in this plan.

**Ground rule (same as every plan in this repo):** every decision below
has already been made. Implement it exactly as written; if something is
genuinely undecided, that is a defect in this document — stop and
report it rather than choosing.

---

## §1 Phase 1 — "alive"

### E1 — Semantic state tokens + attention + thinking

**Tokens** (App.css `:root`, beside the existing accent variables):
`--attn: #ffb454; --attn-dim: rgba(255, 180, 84, 0.35);`. Cyan
(existing `--accent`) = alive/ok; amber = needs-your-attention; the
existing error red stays error. Dots stop meaning things by position:
any live/ok dot is cyan, any attention dot is amber.

**Attention (the confirmation gap).** Deterministic source, no new
protocol: `jarvis/bot/display.py`'s payload dict gains `"tool": tool`
(additive; the client type marks it optional, older payloads degrade
gracefully — same D36 discipline as `surface`). Client-side, attention
is ACTIVE iff the NEWEST drawer-routed item in `displayResults.ts` has
`tool ∈ {"prepare_commit", "prepare_push", "repo_write_file"}` (the
draft→confirm gates) — self-clearing when any newer item lands (the
confirm's executed payload, or anything else). While active: the topbar
toggle's dot renders amber (attention outranks the cyan live dot), the
Output tab dot renders amber, and `.orb-readout` gains an amber
underglow (`text-shadow` swap, no animation). A helper
`hasPendingDraft()` exported from `displayResults.ts` is the single
place this rule lives.

**Thinking shimmer.** Trigger: `RTVIEvent.BotLlmStarted` /
`BotLlmStopped` (client-js emits these alongside the speaking events).
Effect: `.orb-label` shows "Thinking" with a slow opacity shimmer on
the dot (CSS, 1.6s ease cycle) between LLM start and first
speech/stop. If those events do not exist in the installed client-js
version, the shimmer is omitted entirely (graceful no-op) and a note
recorded in the plan status — do not simulate thinking from timers.

### E2 — Boot sequence on Connect

Trigger: transport entering `ready` for this connection (once per
connect, tracked in a ref). ~1.8s total, all CSS-driven via a
`.booting` class on `.orb-field`:

1. 0–600ms: `.orb-readout` letters cascade in (per-letter
   `animation-delay` steps of 40ms, opacity+blur-in). The readout is
   already letter-dotted text; wrap letters in spans at render.
2. 200–1200ms: satellites fade/scale in, staggered 80ms apart in
   `AGENT_LAYOUT` order.
3. 0–900ms: the wave rises from flatline — `VoiceWave` gains a
   module-internal boot ramp (amplitude multiplied by an eased 0→1
   over 900ms, started by a `bootWave()` export the App calls on
   ready). No new props drilling; same pub/sub style as `wakeWord`.
4. t=0: boot chirp (E3), if sounds are on.

Under `prefers-reduced-motion`: no cascade, no stagger, no ramp —
everything appears instantly; the chirp still plays (sound is not
motion). Reconnects replay the sequence (each connect is an arrival).

### E3 — Four-tone sound palette

New module `web/src/sounds.ts` — Web Audio, synthesized at play time,
zero audio assets, one shared `AudioContext` created lazily on first
play (post-gesture, so autoplay policy is satisfied by the Connect
click). Master gain 0.08. The four tones, locked:

| Name | Spec | Played on |
|---|---|---|
| `boot` | two ascending sines 520→780 Hz, 180ms total | transport ready (E2) |
| `tick` | 1.2 kHz sine blip, 30ms | agent `working` message (OrbField's existing listener) |
| `done` | 660+990 Hz dyad, 120ms | agent `done` with ok=true |
| `fail` | 220 Hz triangle, 160ms | agent `done` with ok=false, and the error banner appearing |

Master toggle: 🔊/🔇 button in the bottombar beside the hints,
persisted at `localStorage["mortimer.sounds"]` (default ON), read via
the same guarded-read discipline as the drawer keys. No per-tone
settings. Voice control of the toggle is deliberately deferred (not a
`ui_control` action in this plan).

### E4 — Full ambient dashboard

**Server:** the admin sidecar gains `GET /api/ambient` returning
`{"ok": true, "reminder": {"text": ..., "due_at": ...} | null,
"summary": "<running session summary line>" | null}` — reminder from
`mcp_servers.mcp_reminders.logic.list_reminders("pending")` (first
upcoming by due time; the sidecar already imports mcp_git logic, same
pattern), summary from the same `jarvis.memory` helpers
`GET /api/memory` already uses. Read-only, no writes, no new tables.

**Client:** new `web/src/components/AmbientStrip.tsx`, mounted inside
`.orb-field`, anchored top-left of the stage (`position: absolute;
top: 16px; left: 16px`), a vertical stack of small frosted chips
(caption visual language: same background/hairline/blur tokens,
`font-size: 12px`, `--text-dim`):

1. **Clock** — client-side, `toLocaleTimeString` without seconds,
   updated every 30s. Always shown while connected.
2. **Next reminder** — "⏰ {text} · {relative due}", hidden when null.
3. **Weather (cached)** — populated client-side: when a
   `surface: "window"` payload with `tool === "get_weather"` passes
   through `displayWindow.publish`, cache `{title, ts}` at
   `localStorage["mortimer.ambient.weather"]`. Chip renders
   "{title} · {age}" (age via the existing `timeFormat.ts` helpers);
   hidden when nothing cached. NO proactive weather fetching — the
   cache only ever fills as a side effect of the user asking.
4. **Last session** — "{summary}" truncated to 90 chars, hidden when
   null.

Polling: `/api/ambient` every 60s while connected; on failure the
reminder/summary chips hide (the sidecar being down must not add an
error surface — the clock and weather chips are sidecar-independent).
The strip renders nothing at all while disconnected (the dead screen
before Connect stays clean).

---

## §2 Phase 2 — "instruments"

### E5 — Satellites become inspectable

All data from the existing `agentRuns.ts` store (`getRuns()` +
`subscribeRuns`) — no new listeners (D10's single-listener rule
holds):

1. **Last-run tick:** each satellite chip shows ✓ (cyan) or ✗ (red)
   for that agent's most recent completed run; persists until the next
   run replaces it; renders at 0.7 opacity so it reads as history, not
   alarm.
2. **Hover:** `title` attribute = last task, truncated to 80 chars.
3. **Click:** opens the drawer to Runs, pre-filtered to that agent.
   Mechanism: `agentRuns.ts` gains a tiny `requestAgentFilter(name)` /
   `subscribeAgentFilter` pub/sub (same shape as everything else in
   that file); the satellite click calls it and then
   `applyUiMessage({type: "ui", action: "drawer_tab", tab: "runs"})` —
   reusing the voice-command dispatch path, so click and voice
   converge on the same setters. `RunsPanel` subscribes and applies
   the name to its EXISTING `agentFilter` state.

Satellites gain `cursor: pointer` and a hover border-glow; nothing
else about the star map changes.

### E6 — Memory dossier

`MemoryPanel.tsx` re-rendered as grouped frosted cards over the SAME
`GET /api/memory` data (no backend change):

- **About you** — facts not matching the prefixes below.
- **Preferences** — keys starting `user.preference.`.
- **Style** — keys starting `user.style.`.
- **Observations** — each with a promotion progress bar
  (`seen/threshold` from the endpoint's existing promotion fields).
- **Session summary** — the running summary as a footer card.

Each fact row keeps its forget (×) action wired to the existing
`DELETE /api/memory/fact/{key}`. Cards use the caption/satellite
frosted tokens; key names render in `--mono` dimmed, values in body
text — the content is the hero, not the keys. Empty groups are
omitted entirely.

### E7 — Transcript action chips

`Transcript.tsx` merges agent-run events into the message flow by
timestamp (both sources already client-side: `usePipecatConversation`
messages + `agentRuns.getRuns()`): a small centered chip row
"→ {displayName}" at a run's `startedAt`, and "✓ {displayName}" /
"✗ {displayName}" at its `doneAt`. Chips are `--mono` 10px, dimmed,
non-interactive — the transcript stays a reading surface. Runs with no
`doneAt` yet show only the start chip.

### E8 — Empty-state hints

Locked copy, verbatim:

- **Stage** (connected, before the first exchange — rendered where the
  caption panel will later live, same frosted style, dismissed forever
  once a caption exists): `Try: "What's the weather?" · "Show me the
  runs" · "Remind me in twenty minutes"`
- **Runs tab empty:** `No runs yet — try "check how my computer is
  doing".`
- **Output tab empty:** `Work products — diffs, commits, scaffolds —
  land here. Try "show the repo status".`

No other surfaces gain hints; the Memory panel is never empty in
practice and the Log explains itself.

---

## §3 Files

**New:** `web/src/sounds.ts`, `web/src/components/AmbientStrip.tsx`,
`tests/unit/test_admin_ambient.py`,
`tests/acceptance/engagement-design.md`

**Modified:** `jarvis/bot/display.py` (payload `tool` field),
`jarvis/admin/server.py` (`GET /api/ambient`),
`web/src/displayResults.ts` (`tool` field + `hasPendingDraft()`),
`web/src/displayWindow.ts` (weather cache hook),
`web/src/App.tsx` (boot trigger, attention dot, sound toggle, hints),
`web/src/App.css` (tokens), `web/src/command-deck.css` (boot
animations, shimmer, attention glow, chips, satellite hover/tick),
`web/src/components/VoiceWave.tsx` (`bootWave()` ramp),
`web/src/components/OrbField.tsx` (letter spans, tick/tooltip/click,
stage hint, AmbientStrip mount),
`web/src/components/MemoryPanel.tsx` (E6), `web/src/memory.css` (E6),
`web/src/components/Transcript.tsx` (E7),
`web/src/components/RunsPanel.tsx` + `web/src/agentRuns.ts` (E5
filter), `web/src/components/OutputTab.tsx` +
`web/src/components/RunsPanel.tsx` (E8 empty copy), `CLAUDE.md`.

---

## §4 Implementation order

Phase 1: (1) E1 tokens + attention (display.py `tool` field first —
everything else reads it); (2) E3 sounds module + toggle; (3) E2 boot
sequence (consumes E3's chirp); (4) E4 sidecar endpoint + tests, then
AmbientStrip. Build/lint + full pytest after each step.

Phase 2: (5) E5 satellites; (6) E6 memory cards; (7) E7 chips;
(8) E8 empty states. Build/lint + full pytest; acceptance checklist;
CLAUDE.md note last.

---

## §5 Verification

- Unit: `test_admin_ambient.py` (endpoint shape, reminder ordering,
  null cases, sidecar pattern per `test_admin_council.py`); a
  `display.py` test asserting the `tool` field on draft/executed
  payloads.
- `tests/acceptance/engagement-design.md`: boot plays once per
  connect and is instant under reduced-motion; draft commit turns the
  dots amber until confirmed; thinking shimmer during a long question;
  each tone audible and the toggle silences all; ambient chips
  populate/hide correctly with the sidecar stopped; satellite
  tick/hover/click; memory cards group and forget correctly; chips
  interleave correctly in the Log; hints appear only when their
  surface is empty.
- `cd web && npm run build && npm run lint`; full pytest suite.

---

## §6 Rollback

Everything is additive UI + one additive payload field + one read-only
endpoint. No migrations, no env vars, no protocol changes. Reverting
the client files restores the current console exactly; the `tool`
field and `/api/ambient` are inert without their consumers.

---

## §7 Approval

**Phase 2 status (2026-08-16): implemented** — E5 (satellite ticks/
tooltips/click-through via `requestAgentFilter` + the `uiCommands`
dispatch, with `consumeRequestedAgentFilter` covering RunsPanel's
unmount-on-tab-switch), E6 (dossier cards + observation promotion
bars), E7 (timestamp-merged run chips in the Log), E8 (locked hint
copy on stage/Runs/Output). CLAUDE.md's Engagement layer note added.
Full suite green (879 passed); web build clean; lint 0 errors.
Remaining: Larry's live pass through the checklist's Phase 2 section.

**Phase 1 status (2026-08-16): implemented** — E1 (tokens, amber
attention via the `tool` payload field + `hasPendingDraft()`, thinking
shimmer on the verified `BotLlmStarted/Stopped` events), E2 (boot
cascade/stagger/wave-ramp/chirp, keyed per connect, reduced-motion
instant), E3 (`sounds.ts` four-tone palette + bottombar toggle), E4
(`GET /api/ambient` + 3 unit tests, `AmbientStrip` with
clock/reminder/weather-cache/summary chips). Full suite green (879
passed); web build clean; lint 0 errors (the new `bootWave` export adds
one benign fast-refresh warning of the same class as SideDrawer's
three). Paused here per the phase gate — Larry reviews Phase 1 live
(`tests/acceptance/engagement-design.md`, Phase 1 section; requires a
stack restart for the sidecar endpoint), then Phase 2 (E5–E8) proceeds
on his word. CLAUDE.md's note lands with Phase 2 per §4.

- [ ] Larry approves.
- [ ] Implementation may begin (Phase 1 first, pause for review, then
      Phase 2).
