# Caption Placement Acceptance Checklist

Manual acceptance for MORTIMER_CAPTION_PLACEMENT_PLAN.md. Run the web
console (`./scripts/run_web.sh` or the full stack via
`./scripts/mortimer.sh`) and connect a session. Tick each line.

## Visibility

- [ ] With no conversation yet: no caption panel is visible anywhere —
      just the M.O.R.T.I.M.E.R. readout, state label, satellites, and
      wave (C4 — the panel never renders empty).
- [ ] Speak to Mortimer once. After the first exchange, the caption
      panel appears in the lower third of the stage and persists (no
      further disappearing) for the rest of the session.

## Legibility against the wave

- [ ] While Mortimer is SPEAKING (wave at its loudest, glow lit), both
      caption lines remain fully legible — the wave's center trace
      passes well above the panel, not through it.
- [ ] Trigger the wake word (if configured). The wake flash does not
      wash out or wash-through the caption text.

## Layout

- [ ] Open the side drawer and drag it to its widest. The caption panel
      stays horizontally centered on the shrunken stage (not the full
      viewport) and never slides under the drawer.
- [ ] At a typical window size (>=1100px wide), confirm the caption
      panel does not overlap the Systems or Librarian satellite chips
      (the two lowest, y=72% in agentLayout.ts).
- [ ] Resize the browser window narrower. The panel's max-width shrinks
      with it (min(560px, 86%)) rather than overflowing the stage edge.

## Fallback

- [ ] If testable (a browser/OS combo without `backdrop-filter`
      support, or DevTools' rendering emulation for it): confirm the
      panel still reads clearly via the solid fallback background
      rather than showing as transparent/unreadable.

## Build gate

- [ ] `cd web && npm run build` passes clean.
- [ ] `cd web && npm run lint` reports 0 errors (pre-existing
      SideDrawer.tsx fast-refresh warnings are expected and unrelated).
