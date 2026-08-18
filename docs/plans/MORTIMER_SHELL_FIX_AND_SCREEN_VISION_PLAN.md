# Mortimer — Shell Pop-out Fix + Screen Vision Plan

**Date:** 2026-08-18
**Author:** Claude (Cowork session), from live-log investigation with Larry
**Status:** approved 2026-08-18 — implemented. Steps 1-4 of §5 done and
verified from the sandbox (1112 unit/integration tests green, one
pre-existing unrelated network-test failure; `tsc -b --force` and
`oxlint` both clean). Step 5 (docs/acceptance — done) plus the two
live-only pieces below need Larry's machine: `npm run build`'s Vite step
and `RUN_LIVE=1 routing_eval` both hit the SAME two pre-existing sandbox
limitations already documented in MORTIMER_CONFIRMATION_AND_CAPABILITY_
PLAN.md's implementation (dist/ EPERM under this sandbox's FUSE
filesystem; the vault's keychain read needing a real macOS keychain) —
neither is fixable from here. S4/S5 (Xcode rebuild, live DP8 matrix, B0
verdict recording) and the Part V live acceptance items are Larry's next
step — see `tests/acceptance/shell-fix-and-screen-vision.md`.

Two parts. Part S fixes the Mac shell's broken pop-out/placement path,
found in the shell's first real test (2026-08-17 night build, tested
2026-08-18 morning). Part V gives Mortimer the ability to view any
connected screen — Larry's decision 2026-08-18: capture freely during any
task, tool available at both the Supervisor and sub-agent layers — so it
can troubleshoot visually (including verifying its own window placement)
and answer "what's on my screen" questions.

---

## §1 Evidence

Larry built and ran the Swift shell (`macos/MortimerShell/`) for the
first time last night, with a second monitor connected, and tested this
morning. Observed: voice `drawer_popout` did nothing (bot log 08:26:05
and 08:26:26 — two `ui_control drawer_popout` calls, no `ui/noop`, no
window); `drawer_popin` at 08:27:28 → "The panels aren't popped out.",
confirming the popout never happened; neither the drawer nor display
window could be opened and placed on the second screen; hot-plug
placement never fired.

Code reading identifies the causes:

1. **Name-contract mismatch (certain).** `web/src/popoutWindow.ts`'s
   shell branch posts `{cmd:"openWindow", name: windowName}` where
   `windowName` is the *browser* window name (`"mortimer-drawer"` /
   `"mortimer-display"`, from `drawerRelay.ts` / `displayWindow.ts`).
   `ShellController.openWindow` parses it with
   `ShellWindowKind(rawValue:)`, which accepts only `"console" |
   "display" | "drawer"`. The parse fails, the `guard` returns, and by
   the bridge's own ignore-unknown design nothing happens and nothing is
   logged. The two sides were each written to the plan but never
   integration-tested against each other (no macOS in the authoring
   sandbox).
2. **Window-lookup identifier assumption (likely; needs one live
   check).** `ShellController` and `ScreenPlacement` find windows via
   `window.identifier?.rawValue == kind.rawValue` (exact equality).
   SwiftUI on macOS typically decorates `NSWindow.identifier` (e.g.
   `"display-AppWindow-1"`), so the lookup returns nil for every window
   — which no-ops `reposition()` entirely (including `extendedScreens()`,
   which needs the console's screen) and the focus loop. This would break
   placement and hot-plug even with (1) fixed, and explains why manually
   opened windows never placed.
3. **Every layer fails silently.** The bridge ignores unknown messages
   with no log; `open()`'s shell branch returns null by design with no
   follow-up verification; `App.tsx`'s `openDrawerPopout` sets
   `drawerWinLive = true` and persists the popout preference without
   checking anything. Nobody at any layer can say "that didn't work."
4. **B0 spike verdicts unrecorded.** Whether mic/WebRTC capture works in
   the shell's WKWebView and whether `BroadcastChannel` crosses the
   shell's webviews (Part B's two predecided PASS/FAIL checkboxes) were
   not recorded from last night's run. Question 2 gates whether a popped
   drawer window receives any relayed data at all.

---

## §2 Part S — shell pop-out and placement fix (S1–S5)

**S1 — one name contract at the bridge seam.** The web side sends the
popout **role** — exactly `"display"` or `"drawer"` — not the browser
window name. `createPopoutChannel` already carries `role`; the shell
branch of `open()` posts `{cmd:"openWindow", name: role}`. The native
`ShellWindowKind` enum is unchanged. Both files get a comment naming the
other side as the contract peer. A unit test pins the posted message
shape (jsdom-level, no shell needed).

**S2 — robust native window lookup.** Replace exact identifier equality
with: match if `identifier.rawValue == kind.rawValue` OR
`identifier.rawValue.hasPrefix(kind.rawValue + "-")` OR the window title
equals the scene title (`"Mortimer"` / `"Mortimer Display"` /
`"Mortimer Drawer"`). One helper used by both `ShellController` and
`ScreenPlacement` — not two matchers. On first live run, log which rule
matched (see S3) and record the observed identifier format in the shell
README; if SwiftUI turns out to provide clean identifiers, keep the
helper anyway as defense in depth.

**S3 — end the silent failures, both layers.**
- Native: an `os.Logger` (subsystem `com.mortimer.shell`) line for every
  bridge message received — including rejected ones, naming the bad
  `cmd`/`name`. Incident 1 of this plan would have been a one-line
  diagnosis in Console.app.
- Web: popout success is *verified*, not assumed. After a popout request,
  poll presence (`hasLiveDrawerWindow()` / `hasLivePopup()`) for
  `POPOUT_CONFIRM_TIMEOUT_MS` (5000). In a plain browser, a null return
  from `window.open` is an immediate failure (popup blocked) — report at
  once. Only on confirmed presence do `drawerWinLive` and the popout
  preference get set (or they revert on timeout). Voice-initiated
  popouts that fail send the existing `ui/noop` with a real reason
  ("The panel window didn't open — check the shell logs." / "The browser
  blocked the popup — click the Panels button once."), spoken verbatim
  per U5. Button-initiated failures surface the same message as a
  transient inline notice beside the button that was clicked (new, small:
  same visual language as E8's empty-state hints, auto-dismissing after a
  few seconds — no existing element serves this today, which the audit of
  this plan confirmed).

**S4 — record the B0 verdicts.** During S5's live session, settle and
write both spike checkboxes (mic capture in WKWebView; BroadcastChannel
across shell webviews) into `macos/MortimerShell/README.md` AND
MORTIMER_MODEL_DISCIPLINE_AND_MAC_SHELL_PLAN.md, per Part B's own rule.
If BroadcastChannel fails, the predecided relay fallback
(`useBroadcastRelayFallback`) becomes its own follow-up work item — not
silently absorbed into this plan.

**S5 — live acceptance on Larry's machine.** The full DP8 matrix, in the
shell, with the real second monitor: popout by voice and by button;
single auxiliary window fills the extended screen; both windows split
60/40; two extended screens each take one; hot-plugging a monitor
relocates live windows; `drawer_popin` returns cleanly. Iteration loop:
Claude proposes → Larry builds/runs in Xcode → observed behavior decides.
Claude may use Cowork's screen-viewing access (with Larry's approval at
that time) to verify placement directly.

---

## §3 Part V — screen vision (V1–V6)

**V1 — `mcp_servers/mcp_screen/`** (standard `logic.py` + `server.py`
convention; `logic.py` pure with injected capture/vision clients). Two
tools:
- `screen_list()` — connected displays with index, resolution, and
  main-display flag, via `system_profiler SPDisplaysDataType -json`
  (no new Python dependency; ~1s is acceptable for an enumeration call).
- `screen_view(display: int = 1, question: str)` — captures display N
  (`screencapture -x -D <n> <tmpfile>`, 1-based to match the CLI),
  sends the image plus `question` to a vision model (V2), returns the
  model's TEXT answer, and deletes the temp file in a `finally` — the
  image never persists and never enters any store or log.

**V2 — vision model routing through the ONE registry.**
`config/upgrade_models.yaml` profiles gain an optional `vision: true`
(set on `claude-haiku`, `claude-sonnet`, `claude-opus`,
`claude-fable-5`). `screen_view` resolves its model:
`JARVIS_VISION_PROFILE` env → else the first key-present `vision: true`
profile in registry order → else a clear error naming the fix. The call
uses the same OpenAI-compatible client construction the registry already
serves, with the image as a base64 data-URI `image_url` content part.
The screenshot goes into ONE one-shot vision call and only text returns
to the loop — images never enter the voice context or sub-agent
transcripts (token cost, latency, and log hygiene all say no).

**V3 — wiring at both layers (Larry's decision).**
- Sub-agents: `mcp-screen` added to `systems` and `developer` in
  `config/agents.yaml` (`config/mcp_servers.yaml` gains the server
  entry), so troubleshooting delegations can look at screens themselves.
- Supervisor: a direct `view_screen` tool following the
  `set_voice`/`ui_control` direct-tool pattern (registered in
  `pipeline.py`, prompt addendum in `jarvis/prompts.py`), calling the
  SAME `mcp_screen.logic` functions — one implementation, two entry
  points. "What's on my second monitor?" answers in one turn, no
  delegation round-trip.

**V4 — guardrails.** Capture happens only when a task calls the tool —
never scheduled, never continuous, no watcher. No screenshot is ever
stored (temp file deleted in `finally`; nothing under `data/`); the run
log records that a `screen_view` call happened and its text result,
never pixels. `JARVIS_SCREEN_ENABLED=false` is the kill switch, enforced
at exactly one point — the top of `logic.py`'s capture entry, which both
the Supervisor tool and the MCP server pass through (the pipeline
registration site also reads it to unregister the Supervisor tool and
omit the prompt addendum, same env var, same switch). Documented
plainly in `.env.example` and the acceptance checklist: **every capture
is sent to a cloud vision API** — anything visible on screen, including
a vault CLI session or a banking page, leaves the machine when this tool
fires. Larry accepts this trade-off for capture-freely operation
(2026-08-18); the kill switch is the off-ramp.

**V5 — preflight + permission.** macOS requires a one-time Screen
Recording (TCC) grant to the capturing process — the Python bot (in
practice, the terminal/launcher that runs `./scripts/mortimer.sh`, or
the shell app if it ever spawns the bot). Without it, `screencapture`
silently produces wallpaper-only images — a silent failure of exactly
the kind this plan exists to kill. `scripts/check_env.py` gains a
WARN-only "Screen vision" section: if `JARVIS_SCREEN_ENABLED` is not
false, state which process needs the grant and how to check (System
Settings → Privacy & Security → Screen Recording). `screen_view`'s
result includes a low-confidence warning when the vision model reports
an effectively empty/wallpaper image, naming the TCC grant as the likely
cause.

**V6 — prompts, routing, counts.** `SUPERVISOR_PROMPT` addendum: screen
questions and visual verification use `view_screen` directly; visual
troubleshooting inside a delegated task is the sub-agent's own
`screen_view`. Two new routing-eval cases pin that "what's on my second
screen" is answered directly (never delegated to developer) and that a
UI-placement verification request reaches a screen tool.
`tests/integration/test_registry.py`'s `TOTAL_TOOLS` goes 55 → 57.

---

## §4 Files

Part S: `web/src/popoutWindow.ts`, `web/src/App.tsx`,
`web/src/components/DisplayPanel.tsx`, `web/src/drawerRelay.ts` (comment
only), `web/src/displayWindow.ts` (comment only),
`macos/MortimerShell/Sources/MortimerShell/ShellBridge.swift`,
`ShellController.swift`, `ScreenPlacement.swift`, shell `README.md`,
MORTIMER_MODEL_DISCIPLINE_AND_MAC_SHELL_PLAN.md (B0 verdicts), web unit
tests.

Part V: `mcp_servers/mcp_screen/{logic.py,server.py,skill.yaml}` (new),
`config/mcp_servers.yaml`, `config/agents.yaml`,
`config/upgrade_models.yaml` (`vision:` flags), `jarvis/bot/pipeline.py`
+ new `jarvis/bot/screen_tool.py`, `jarvis/prompts.py`,
`scripts/check_env.py`, `.env.example`, `tests/evals/cases.yaml`,
`tests/unit/test_mcp_screen_logic.py` (new),
`tests/integration/test_registry.py`, CLAUDE.md, acceptance checklist.

Note: `macos/**` is on the self-edit deny list — Part S's Swift changes
are human-PR only, never a self-edit. `config/upgrade_models.yaml`
likewise stays off the allowlist; the `vision:` flags land by human PR.

---

## §5 Implementation order

1. S1 + S3(web) + S3(native) + S2, with web unit tests — one commit;
   Larry builds in Xcode.
2. S5 live matrix on Larry's machine (iterate until green); S4 verdicts
   recorded during the same session.
3. V1 + V2 + V4 kill switch + unit tests (capture fn and vision client
   injected — no live capture in pytest).
4. V3 wiring + V6 prompts/eval/counts + V5 preflight.
5. Docs (CLAUDE.md sections for the shell fix and screen vision),
   acceptance checklist `tests/acceptance/shell-fix-and-screen-vision.md`,
   full pytest + build/lint, `RUN_LIVE=1 routing_eval` ≥ 90% (prompts
   change), restart stack, live screen-vision acceptance ("what's on my
   second screen" by voice, and a developer delegation that verifies
   drawer placement visually).

## §6 Rollback

S1–S3 revert by commit (no migrations, no data shape). Part V:
`JARVIS_SCREEN_ENABLED=false` disables everything at one point;
removing `mcp-screen` from `agents.yaml` unwires sub-agents; the
Supervisor tool disappears with the same env var. No part of this plan
touches confirmation gates, the vault, or the council.

## §7 Open items carried, not blocked

The B0 BroadcastChannel verdict (S4) may spawn the relay-fallback work
item. The plain-browser popup-blocked path gets honesty (S3) but not
auto-placement — that remains architecturally impossible outside the
shell/Chromium, documented, not worked around.

## §8 Approval

- [ ] Larry approves.
- [ ] Implementation may begin.
