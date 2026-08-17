# Mac shell — acceptance checklist

MORTIMER_MODEL_DISCIPLINE_AND_MAC_SHELL_PLAN.md Part B. Manual, on a
real Mac with Xcode. Not run by pytest — no macOS runner exists in CI
and none is assumed. `./scripts/mortimer.sh` must be running first.

## B0 spike (do this first — see macos/MortimerShell/README.md)

- [ ] Mic/WebRTC capture inside WKWebView: PASS/FAIL recorded in the
      shell's README and in the plan file itself.
- [ ] BroadcastChannel across two WKWebViews: PASS/FAIL recorded in the
      same two places.

## B1 — three windows

- [ ] Launching the app opens exactly one console window loading
      `http://127.0.0.1:5173`.
- [ ] Display and Drawer windows do not appear until requested (B2).

## B2 — shell detection and the ⧉ buttons

- [ ] Inside the shell, clicking the topbar's `⧉ Display` button opens a
      NATIVE window (not a browser popup) titled "Mortimer Display".
      Clicking again while it's open focuses the existing window rather
      than opening a second one.
- [ ] Same for the drawer pop-out control.
- [ ] Voice commands `display_popout` / `drawer_popout` (`ui_control`)
      work identically to the buttons.
- [ ] The SAME build, run in a plain Chrome/Safari tab (not inside the
      shell) instead of the native app, still opens a real browser
      popup — the shell branch in `popoutWindow.ts` is provably inert
      outside the shell.

## B3 — native placement

- [ ] One extra monitor, only Display open: it fills that monitor.
- [ ] One extra monitor, both Display and Drawer open: Display left
      60%, Drawer right 40% of that one monitor.
- [ ] Two extra monitors, both open: each fills its own monitor.
- [ ] Plug in a second monitor while both are already open on the
      first extended screen: they redistribute onto both without
      needing to be reopened.
- [ ] No extra monitor: windows open beside the console, no crash or
      off-screen placement.

## B4 — loading source and failure mode

- [ ] Stop the stack (`Ctrl-C` on `./scripts/mortimer.sh`) — the
      console window (and any open Display/Drawer) shows the native
      retry screen, not a WKWebView error page.
- [ ] Restart the stack, click Retry — the webview loads normally.

## B5 — self-edit boundary

- [ ] Ask Mortimer (self-edit) to change something under `macos/**` —
      refused as off-allowlist, same as a request to touch
      `jarvis/vault.py` or `config/upgrade_models.yaml`.
- [ ] A self-edit touching only `web/src/**` still validates and
      submits normally — the shell's own deny rule doesn't collaterally
      block ordinary UI self-edits.

## B6 — scope guard

- [ ] No menu-bar extra, no global hotkey, no dock badge, no login
      item, no auto-start of the Python stack, no packaged/signed
      distributable exists in this build — confirm nothing beyond the
      three windows was added.

## B7 — naming

- [ ] Nowhere in the shell's UI or logs does "sidecar" appear referring
      to this app (sidecar = the `:7861` admin process only).
