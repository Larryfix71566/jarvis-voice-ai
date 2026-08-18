# Shell fix + screen vision — acceptance checklist

MORTIMER_SHELL_FIX_AND_SCREEN_VISION_PLAN.md. Manual, run against a live
stack after restarting the bot (prompts/config are read at boot — this
plan changed `jarvis/prompts.py`, `config/agents.yaml`, `config/
mcp_servers.yaml`, `config/upgrade_models.yaml`). The Part S items need
the Mortimer shell rebuilt in Xcode with this session's fixes; Part V
items work in a plain browser too. Not run by pytest, except where an
item names a specific automated test/command.

## Part S — shell pop-out fix

- [ ] Rebuild in Xcode with the S1/S2/S3 fixes (`open Package.swift`,
      build, run — see `macos/MortimerShell/README.md`'s "First open in
      Xcode" + new "2026-08-18" section).
- [ ] With a second monitor connected, click the topbar "◧ Panels"
      button (or say "pop out the drawer") from inside the shell's
      console window — the drawer window actually opens and fills the
      extended screen. Console.app, filtered to subsystem
      `com.mortimer.shell`, shows `openWindow: opening/focusing drawer`
      and `reposition: filling drawer-only onto 1 extended screen(s)` —
      not a `rejected unrecognized name` error (S1's exact bug).
- [ ] Also open the display window (⧉ Display button, or say "put that
      on the other screen" after asking a research question) — with
      both open on one extended screen, display fills the left 60% and
      drawer the right 40% (`reposition: one extended screen —
      splitting display 60% / drawer 40%` in the log).
- [ ] With two external monitors connected, opening both windows gives
      each its own full screen (`reposition: two+ extended screens...`).
- [ ] Unplug and replug a monitor while both windows are open — they
      relocate without needing to be reopened (`didChangeScreenParameters`
      → `reposition:` log lines fire on their own).
- [ ] Say "bring the panels back" (`drawer_popin`) — the drawer returns
      in-page cleanly and the native window actually closes (Console.app
      shows `didReceive closeWindow name='drawer'` then
      `closeWindow: closing drawer` — the 2026-08-18 close-path fix; the
      pre-fix symptom was the drawer flickering in-page for a beat and
      then popping back out as the still-open window's heartbeat won).
- [ ] Click the ↩︎ button beside "◪ Panels ⧉" in the topbar — same
      result as the voice command above. Repeat for the display window's
      ↩︎ beside "⧉ Display".
- [ ] Zombie-webview regression check (2026-08-18 second-layer fix):
      after pop-in, the in-page drawer STAYS in-page — no flip back to
      popped within the next ~10s (the pre-fix symptom: SwiftUI keeps
      the closed window's webview alive and its heartbeat kept claiming
      presence). Then pop out again — the reopened window must show live
      content (the kept-alive webview resumes with a fresh hello +
      snapshot replay), and pop-in a second time must also stick.
- [ ] Induce a failure on purpose (e.g. quit the shell mid-open, or test
      in a plain browser tab where pop-ups are blocked): the failure is
      audible/visible — a spoken `ui/noop` reason for a voice-initiated
      popout, or the small amber `.popout-error-notice` beside the
      clicked button for a button-initiated one — never silent, and the
      button/topbar state does NOT flip to "live" when it didn't
      actually open.
- [ ] Record the B0 spike verdicts in `macos/MortimerShell/README.md`
      (mic/WebRTC capture; BroadcastChannel across the shell's
      WKWebViews) and back in MORTIMER_MODEL_DISCIPLINE_AND_MAC_SHELL_
      PLAN.md, per that plan's own rule — this session's bot log
      already suggests mic capture works (a live voice exchange
      produced the `drawer_popout`/`drawer_popin` calls that surfaced
      this bug), but the formal checkbox is Larry's to tick.

## Part V — screen vision

- [ ] With `JARVIS_SCREEN_ENABLED` unset (default true) and at least one
      `vision: true` profile's API key present (e.g. `ANTHROPIC_API_KEY`
      for `claude-haiku`), ask "what's on my screen right now?" — the
      Supervisor calls `view_screen` directly (never delegates), and
      answers in one or two sentences without describing the capture
      mechanics.
- [ ] With two monitors connected, ask "how many screens do I have?" —
      the Supervisor calls `list_screens` and reports the count and
      resolutions; confirm the reported count/order matches reality (the
      `system_profiler` JSON parsing has never been verified on real
      hardware — see CLAUDE.md's screen vision paragraph).
- [ ] Ask "is the panel window actually on the second monitor?" while
      the drawer/display windows are open — the Supervisor's answer
      correctly reflects what's actually showing on that screen.
- [ ] Delegate a troubleshooting task to systems or developer that
      plausibly needs a visual check (e.g. "check if the pop-out window
      actually appeared") — the sub-agent calls `screen_view` itself
      rather than reporting it can't see the screen.
- [ ] Temporarily revoke Screen Recording permission (System Settings >
      Privacy & Security > Screen Recording) and ask `view_screen` again
      — the answer reports a low-confidence, wallpaper-only capture and
      names the permission as the likely cause, rather than presenting a
      confused vision-model answer as a real one. Re-grant the
      permission afterward.
- [ ] `python scripts/check_env.py` (or `check_screen_vision()` in
      isolation, same pattern as `check_model_registry()`'s sandbox
      workaround) reports which vision profile is ready and reminds
      about the Screen Recording permission.
- [ ] `JARVIS_SCREEN_ENABLED=false` in `.env`, restart the bot: asking
      "what's on my screen" gets a plain "that's not enabled" style
      answer (from `screen_view`'s `{"error": ...}` relayed verbatim),
      the topbar shows no screen-vision-related prompt behavior, and the
      mcp-screen MCP server tools also refuse identically (same kill
      switch, one check point).
- [ ] Privacy spot-check: confirm nothing under `data/` or `logs/`
      contains a captured screenshot after several `view_screen` calls —
      only the text answer should appear anywhere (run log, transcript).

## Notes

- Automated coverage for the deterministic parts of both tracks lives in
  `tests/unit/test_mcp_screen_logic.py` (17 tests),
  `tests/unit/test_screen_tool.py` (10 tests),
  `tests/integration/test_bot_wiring.py` (capability + screen kill-switch
  tests), `tests/integration/test_registry.py` (`TOTAL_TOOLS = 57`), and
  `tests/unit/test_check_env_model_registry.py`-style isolation testing
  for `check_screen_vision()` — all green as of 2026-08-18. The Swift
  changes (`WindowLookup.swift`, `ShellBridge.swift`, `ShellController.
  swift`, `ScreenPlacement.swift`) have no automated test coverage —
  Swift has never been runnable from this sandbox; correctness rests on
  careful manual review plus this checklist's live items.
