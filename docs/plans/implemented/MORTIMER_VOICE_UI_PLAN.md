# MORTIMER VOICE UI CONTROL — implementation plan

**Problem.** Mortimer is a voice-first product whose UI chrome is
mouse-only: nine topbar controls, drawer tabs, transcript, display
windows — none reachable by voice. The Supervisor has no UI-affecting
tools; every server→client message today is a one-way data push. Larry's
concrete symptom: "I am not able to open/close the side drawer with my
voice."

**The precedent this plan generalizes:** voice selection ALREADY works
this way. `set_voice` (`jarvis/bot/voice_switch.py`) is a direct
Supervisor tool (no sub-agent), its side effect is injected by the
caller, and `VoicePicker.tsx` syncs its UI off a server message. This
plan builds the same shape for UI chrome.

**Decisions locked with Larry (2026-08-16):**
- Architecture: Supervisor tool now; a local (browser-side) fast-path is
  DEFERRED, not planned — revisit only if command latency proves
  annoying in practice (§7).
- Scope: Tier 1 (chrome: drawer/tabs/transcript/display) + Tier 2
  (states: mic mute, wake word). Tier 3 (content commands) is out.
- Feedback: hybrid — silent when something visibly changes; spoken only
  when nothing does.
- Display mode: implicit (live popup = dual-screen) now; Window
  Management API auto-detect deferred.
- Single-screen overlay: persistent until dismissed, frosted
  translucent, footprint cap (~40% of the stage).

**Ground rule (same as every plan in this repo):** every decision below
has already been made. Implement it exactly as written; if something is
genuinely undecided, that is a defect in this document — stop and
report it rather than choosing.

---

## §1 Decisions

### U1 — One Supervisor tool: `ui_control`

New module `jarvis/bot/ui_control.py`, structurally copied from
`jarvis/bot/voice_switch.py` (pure resolution + injected side effect;
`jarvis/bot/remember_tool.py` used the same template). Registered on the
LLM in `pipeline.py` beside `set_voice` and `remember` — it is a direct
Supervisor action, never a delegation.

Tool schema (verbatim):

```python
UI_CONTROL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "ui_control",
        "description": (
            "Control the console interface. Call when the user asks to "
            "open/close/show/hide a UI element by voice. Actions: "
            "drawer_open (optional tab), drawer_close, drawer_tab "
            "(requires tab), transcript_open, transcript_close, "
            "display_popout (move informational content to the separate "
            "display window), display_close (close it), overlay_dismiss "
            "(dismiss the on-stage content panel), mic_mute (stop "
            "listening), wake_on, wake_off. There is deliberately no "
            "mic_unmute: while muted the user cannot be heard, so the "
            "command could never arrive — unmuting is the wake word's or "
            "the mic button's job."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": [
                    "drawer_open", "drawer_close", "drawer_tab",
                    "transcript_open", "transcript_close",
                    "display_popout", "display_close", "overlay_dismiss",
                    "mic_mute", "wake_on", "wake_off",
                ]},
                "tab": {"type": "string", "enum": [
                    "repo", "edit", "memory", "runs", "developer", "output",
                ], "description": "Drawer tab, for drawer_open/drawer_tab"},
            },
            "required": ["action"],
        },
    },
}
```

The handler validates action/tab (pure, unit-testable), then emits ONE
app message via the injected sender (`send_app_message` from
`pipeline.py`, same injection style as `set_voice`'s `push_frame`):

```python
{"type": "ui", "action": "<action>", "tab": "<tab or omitted>"}
```

Handler return values implement the U5 feedback contract:
- valid command → `"ok"` (the Supervisor stays silent per U5's prompt)
- invalid tab / unknown action → one sentence naming the valid options
- `mic_mute` → `"ok-muted"` (prompt has Mortimer say a short goodbye —
  the user must know listening stopped, since nothing visible may be
  in their gaze)
- `wake_on`/`wake_off` → `"ok"`; the CLIENT decides availability (U2) —
  the bot cannot know whether the wake sidecar is running.

The bot process holds NO UI state. It never knows whether the drawer is
open — "already open" no-ops are detected client-side (U2) and reported
back for speech via the existing client→bot message path ONLY in the
no-op case (see U5). This keeps a single source of truth (the browser,
which owns the state) and survives multiple consoles/reconnects.

### U2 — Client dispatch: one store, owners apply their own state

New module-level store `web/src/uiCommands.ts` — publish/subscribe, same
shape as `agentRuns.ts` (the established pattern for state that must
outlive component mounts). `App.tsx`'s EXISTING ServerMessage listener
(the one that already routes display results) additionally forwards
`{"type": "ui"}` messages into the store. No new listener registrations.

Each owner subscribes and applies only what it owns:
- `App.tsx`: drawer_open/close/tab (its `drawerOpen`/`drawerTab`
  state), transcript_open/close (`transcriptOpen`) — reusing the exact
  state setters the buttons already call, so voice and click can never
  diverge in behavior.
- `DisplayPanel.tsx` / `displayWindow.ts`: display_popout (set the
  popout preference + `openDisplayWindow()`), display_close (clear the
  preference + close via the existing channel), overlay_dismiss
  (dismiss the in-page panel).
- `MicControls.tsx`: mic_mute (`client.enableMic(false)` + its `muted`
  state — same code path as the button), wake_on/wake_off
  (`startWakeWord`/`stopWakeWord`). If `wakeWordAvailable` is false,
  wake_on is a no-op reported per U5.

**No-op reporting (the hybrid's spoken half):** when a command changes
nothing (drawer already open, popup already closed, wake unavailable),
the applying component sends one client→bot message through the
existing `_unwrap_client_message` path:

```
{"type": "ui/noop", "reason": "<short spoken sentence, e.g. "The drawer is already open.">"}
```

The bot speaks `reason` VERBATIM by pushing a `TTSSpeakFrame` (pipecat
frame, pushed via the same `pusher.push` injection `set_voice` uses for
`TTSUpdateSettingsFrame`) — deliberately NOT a Supervisor context note:
the tool call already returned `"ok"` and the Supervisor's turn is
over by the time the client detects the no-op, so an LLM-mediated reply
would surface a full exchange late. Canned TTS is immediate,
deterministic, and costs no tokens. The client owns the sentence text
(it knows the state); the bot is a dumb speaker for this one path. A
command that visibly succeeded sends nothing.

### U3 — Display mode is implicit: the live popup IS dual-screen

Formalizes what `displayWindow.ts` already half-does. The mode is not
stored anywhere; it is read, at routing time, as `hasLivePopup()`:

- Popup live → informational (`surface: "window"`) payloads go to the
  popup ONLY; the in-page DisplayPanel does NOT also render them
  (today it shows both — that double-display is removed).
- No live popup → payloads render in the in-page overlay panel (U4).
- The existing persisted popout preference remains the auto-reopen
  mechanism and becomes voice-set: `display_popout` sets it,
  `display_close` clears it — identical semantics to clicking ⧉.
- Voice overrides: "put that on the big screen" → `display_popout`
  (current payload follows via the existing "hello"/replay handshake);
  "show it here" → `display_close` (payload falls back to the overlay).
  These are not new actions — they are the same two actions; the
  Supervisor's tool description covers the phrasing.

Window Management API auto-detection (real monitor enumeration,
Chrome-only, permission-gated) is DEFERRED — `openDisplayWindow()`
already carries a comment marking where it would slot in. Do not
implement it in this plan.

### U4 — Single-screen overlay: persistent, frosted, capped

`DisplayPanel.tsx`'s in-page window is restyled to match the frosted
language shipped by MORTIMER_CAPTION_PLACEMENT_PLAN.md (same tokens:
`rgba(4, 9, 12, 0.55)` base, hairline border, `backdrop-filter:
blur(8px)`, plus the same `@supports` solid fallback) so the wave and
satellites read through it.

Footprint cap: `max-width: 40vw; max-height: 40vh; overflow-y: auto`
on the panel. The interface must stay visibly alive behind content —
content scrolls before it grows.

Behavior: persistent until dismissed — by voice (`overlay_dismiss`),
by its existing close button, or by being superseded by the next
payload. NO auto-dismiss timeout ("wait, what did that say?" is a
voice-first failure mode), NO speech-reactive opacity (deferred as
polish, §7).

### U5 — Hybrid feedback, enforced in the prompt

`jarvis/prompts.py` (the single source of truth for prompts) gains this
addendum to the Supervisor prompt, verbatim:

```
UI control: when a ui_control call returns "ok", say nothing about it —
the visible change is the confirmation; continue with at most the
answer to whatever else the user asked. When it returns "ok-muted",
give a one-phrase sign-off (e.g. "Going quiet."). When it returns an
error sentence, relay it in one short sentence. Never narrate UI
actions you were not asked to perform, and never call ui_control unless
the user asked for a UI change.
```

### U6 — Kill switch

`JARVIS_UI_CONTROL_ENABLED` (default true), read from the environment at
exactly one point: the tool-registration site in `pipeline.py` (same
env-first pattern as the council's kill switch). False = the tool is
not registered and not in the schema list; the Supervisor cannot call
what it cannot see. A matching discoverability field
`jarvis_ui_control_enabled: bool = True` goes in `jarvis/config.py`
Settings (same rationale as `jarvis_council_enabled`: documented, but
the enforcement read is the env one). `.env.example` documents it.

### U7 — The mute dead-end, stated once

`mic_mute` exists; `mic_unmute` deliberately does not (schema
description says why). While muted, no voice command can arrive; the
wake word (or the mic button / SPACE) is the way back. The prompt
addendum's "Going quiet" sign-off plus the existing mic-button state
are the full UX. If the user asks Mortimer "how do I unmute you" BEFORE
muting, that is ordinary conversation — no code path needed.

### U8 — Routing eval coverage

`tests/evals/routing_eval.py`'s case set gains 10 UI-control utterances
(e.g. "open the drawer", "show me the runs panel", "close that",
"put the weather on the other screen", "stop listening") whose expected
outcome is a `ui_control` call with the right action — NOT a
delegation. The ≥90% bar is unchanged and now covers the new cases.

### U9 — What this plan deliberately does NOT do

- No local/browser fast-path grammar (deferred; §7 revisit criterion).
- No Window Management API / monitor enumeration (deferred).
- No named multi-window support beyond the single popup (roadmap;
  the BroadcastChannel design does not preclude it).
- No OS-level always-on-top HUD over other applications — impossible
  from a browser tab; that is an Electron/Tauri packaging fork and a
  separate roadmap decision, explicitly not taken now.
- No voice help tour, auto-hide chrome, or session-recall affordance
  (evaluated, deliberately excluded from this plan's scope).
- No Connect-by-voice: the first click of a session is a browser
  autoplay/mic-permission constraint, not a design choice.
- No new confirmation gates touched: ui_control performs only
  reversible view-state changes, so it needs none.

---

## §2 Files

**New:**
- `jarvis/bot/ui_control.py` — U1 (schema + pure resolution + handler
  factory `build_ui_control_tool(send_message)`)
- `web/src/uiCommands.ts` — U2 store
- `tests/unit/test_ui_control.py` — U1 resolution/handler tests
- `tests/acceptance/voice-ui.md` — §4 checklist

**Modified:**
- `jarvis/bot/pipeline.py` — register tool behind U6's env read; route
  `ui/noop` client messages into a Supervisor context note
- `jarvis/prompts.py` — U5 addendum
- `jarvis/config.py` — U6 Settings field
- `web/src/App.tsx` — forward `ui` messages to the store; subscribe for
  drawer/transcript actions
- `web/src/components/DisplayPanel.tsx` — U3 popup-suppression, U4
  frosted style + cap, overlay_dismiss/display actions
- `web/src/displayWindow.ts` — display_popout/close application (if any
  helper is missing; `hasLivePopup`/`openDisplayWindow` already exist)
- `web/src/components/MicControls.tsx` — mic/wake subscription
- `web/src/command-deck.css` — U4 styles (`.display-panel` lives here,
  lines ~272/515)
- `tests/evals/routing_eval.py` — U8 cases
- `.env.example`, `CLAUDE.md` — U6 + a short Voice UI section

---

## §3 Implementation order

1. `jarvis/bot/ui_control.py` + unit tests (pure, no dependents).
2. `pipeline.py` registration + kill switch + `ui/noop` context note;
   `prompts.py` addendum; `config.py` field.
3. `web/src/uiCommands.ts` + `App.tsx` forwarding/subscription
   (drawer + transcript = Larry's headline symptom, testable first).
4. `MicControls.tsx` mic/wake subscription.
5. U3 popup-suppression + U4 overlay restyle/cap +
   display/overlay actions.
6. Routing eval cases (U8) + `RUN_LIVE=1` eval run ≥90%.
7. Docs + acceptance checklist; full pytest + web build/lint.

---

## §4 Verification (tests/acceptance/voice-ui.md, key items)

- [ ] "Open the drawer" / "close the drawer" — works, and Mortimer says
      NOTHING when it visibly happens (U5).
- [ ] "Show me the runs" (and each of the six tabs by name) — drawer
      opens to the right tab.
- [ ] "Open the drawer" when already open — Mortimer says so in one
      short sentence (the no-op path).
- [ ] "Show the log" / "hide the log" — transcript drawer.
- [ ] Weather/radar request with no popup → frosted overlay in-page,
      ≤40% of the stage, wave visible behind it; persists until
      "close that" dismisses it.
- [ ] "Put that on the other screen" → popup opens with the payload;
      the in-page panel does NOT also show it (U3's double-display
      removal). "Show it here" → back to the overlay.
- [ ] "Stop listening" → mic mutes, Mortimer gives a one-phrase
      sign-off; wake word (if on) can bring it back.
- [ ] "Turn on the wake word" with the sidecar not running → spoken
      one-sentence explanation (no-op path), nothing crashes.
- [ ] Buttons still work identically to voice (same setters — spot-check
      drawer and popout via mouse after using voice, and vice versa).
- [ ] `JARVIS_UI_CONTROL_ENABLED=false` → tool absent; "open the
      drawer" gets a normal conversational reply, no crash; buttons
      unaffected.
- [ ] Routing eval ≥90% including the 10 new cases.
- [ ] Full pytest suite + `npm run build` + `npm run lint` clean.

---

## §5 Risks

| Risk | Level | Mitigation |
|---|---|---|
| Supervisor over-calls ui_control (narrates/acts unasked) | Medium | U5's "never call unless asked" prompt line + U8 eval cases pin behavior |
| Command latency (~1–2s LLM round trip) feels sluggish | Medium | Accepted trade (architecture decision C); §7's fast-path criterion is the pressure valve |
| Multiple consoles open → command applies in all of them | Low | Acceptable: they'd diverge anyway via clicks; state is per-browser by design (U1: bot holds no UI state) |
| Popup suppression breaks the popout-preference auto-reopen | Low | U3 reuses the existing preference/handshake paths; acceptance items cover both directions |
| `ui/noop` chatter loops (noop → speech → noop) | Low | Noop messages are sent only in direct response to a `ui` command, never spontaneously; the TTSSpeakFrame path involves no LLM, so it cannot trigger further tool calls |

---

## §6 Rollback

`JARVIS_UI_CONTROL_ENABLED=false` removes the tool entirely; the client
store and dispatch code are inert without inbound `ui` messages. U3's
double-display removal and U4's restyle are the only behavior changes
that survive the kill switch — both are pure client rendering changes,
revertible by reverting the two display files.

---

## §7 Deferred, with revisit criteria

- **Local fast-path grammar:** revisit only if, after two weeks of real
  use, drawer/tab commands feel slow enough that Larry asks — measure
  then (transcript-to-action latency), don't build now.
- **Window Management API:** revisit when a third screen exists or
  popup placement annoys; slots into `openDisplayWindow()`'s marked
  comment.
- **Named multi-windows, voice help tour, auto-hide chrome, session
  recall, speech-reactive opacity, Electron/Tauri HUD:** separate
  plans, in that rough priority order, when asked.

---

## §8 Approval

**Implementation status (2026-08-16): implemented, §3 steps 1–7
complete.** Full suite green (865 passed); web `tsc`/`vite build`/
`oxlint` clean; import smoke clean. Three implementation-discovered
notes, each documented inline where it lives:

1. **U3's "double-display is removed" was already true** — DisplayPanel
   has hidden itself behind a live popup since the side-drawer plan
   (D41, `if (!item || popupOpen || dismissed) return null`). No change
   was needed; the plan's premise about current behavior was wrong, the
   end state is as specified.
2. **U8 as written was unimplementable in the existing harness**:
   `routing_eval` drives the text `Orchestrator`, which has only
   `delegate_task` — it cannot observe `ui_control` calls. Adapted to
   the hazard the decision actually protects against: 10 cases
   asserting UI utterances are NEVER delegated (rule 8's "changing your
   own interface → developer" misroute), plus one clarifying sentence
   added to rule 8 in `jarvis/prompts.py` ("view change, not
   development"). The tool-choice half of U8 is covered by unit tests
   + the U5 addendum + the acceptance checklist instead.
3. **The U5 addendum gained one sentence** beyond the plan's verbatim
   text, disambiguating ui_control from rule 8's developer routing —
   same boundary as note 2, stated on both sides.

Also fixed in passing (vault fallout, not this plan): the first
post-migration full-suite run on a machine with a real
`data/secrets.vault` exposed two test-isolation gaps —
`test_config.py`'s `clean_env` deleting conftest's vault isolation, and
`check_skills.py`'s `requires_env` check reading only os.environ/.env.
Both fixed; the vault plan's S4 was amended (three call sites → four)
with the reasoning recorded there.

Remaining: the manual pass through `tests/acceptance/voice-ui.md`
against a live session, and `RUN_LIVE=1 python -m tests.evals.
routing_eval` (needs real API keys — run on the real machine; the ≥90%
gate now includes the 10 UI cases).

- [ ] Larry has read §1 and approves.
- [ ] Implementation may begin.
