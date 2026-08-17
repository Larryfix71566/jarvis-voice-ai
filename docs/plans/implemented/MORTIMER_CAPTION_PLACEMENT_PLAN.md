# MORTIMER CAPTION PLACEMENT — implementation plan

**Problem.** The live caption block (`.live-caption` in
`web/src/components/OrbField.tsx`) is flex-centered inside `.orb-center`,
which sits at the vertical center of `.orb-field`. The voice wave
(`web/src/components/VoiceWave.tsx`) draws its trace at exactly the same
place — `cy = h * 0.5`, with a super-Gaussian envelope concentrating
~94% of peak amplitude in the middle ~10% of the screen width, centered
on the same vertical line. The caption's only protection is a soft
radial scrim (`command-deck.css` `.live-caption`), which fails whenever
the wave is loud (speaking state, wake flash). Result: Mortimer's reply
text is obscured by the wave at precisely the moments it matters.

**Chosen approach (Larry, 2026-08-16): option D** — move the captions to
the lower third of the stage AND give them a frosted backdrop. The wave,
readout, state label, satellites, and beams are all untouched.

**Ground rule (same as every plan in this repo):** every decision below
has already been made. Implement it exactly as written; if something is
genuinely undecided, that is a defect in this document — stop and
report it rather than choosing.

---

## §1 Decisions

### C1 — Captions leave the center flex column

In `OrbField.tsx`, the `<div className="live-caption">…</div>` block
moves OUT of `.orb-center` and becomes a direct child of `.orb-field`
(rendered after `.orb-center`, before the closing `</section>`). Nothing
else in the JSX moves: the wake ripple, beams, satellites, readout
(`M.O.R.T.I.M.E.R.`), and state label stay exactly where they are.

### C2 — Anchored to the lower band, clear of the satellites

`.live-caption` is repositioned in `command-deck.css`:

```css
.live-caption {
  position: absolute;
  bottom: 8%;
  left: 50%;
  transform: translateX(-50%);
  z-index: 3;
  /* ...appearance per C3... */
}
```

Why `bottom: 8%`, specifically: the two lowest agent satellites
(Systems at y=72%, Librarian at y=72% — `web/src/agentLayout.ts`) define
the bottom of the satellite ring. A caption block anchored at 8% from
the field's bottom edge occupies roughly y≈84–95% depending on line
count, entirely below that ring and entirely below the wave's
high-energy band at y=50%. `z-index: 3` places it above the satellites
(`z-index: 2`) for the marginal case where a very wide caption's corner
approaches a satellite's label on a narrow window — the frosted panel
(C3) keeps the text readable if they ever touch. Do not use a
viewport-fixed position: `.orb-field` already shrinks when the side
drawer pushes the stage, and the caption must shrink with it (absolute
within the field gives this for free; `left: 50%` keeps it centered on
the *remaining* stage, not the viewport).

### C3 — Frosted panel replaces the radial scrim

The existing `background: radial-gradient(...)` on `.live-caption` is
REMOVED and replaced with:

```css
  max-width: min(560px, 86%);
  padding: 10px 18px;
  border-radius: 10px;
  background: rgba(4, 9, 12, 0.55);
  border: 1px solid var(--hairline);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
```

These values deliberately echo the `.satellite` chips (same base color
`rgba(4, 9, 12, 0.55)`, same hairline border, blur one step stronger
than their 4px) so the panel reads as part of the existing command-deck
language, not a new UI style. `max-width` gains the `86%` bound so the
panel never spans edge-to-edge when the drawer squeezes the stage.
Existing properties that stay: `display: flex`, `flex-direction:
column`, `align-items: center`, `gap: 4px`, `text-align: center`. The
`min-height: 44px` is REMOVED (see C4). The `.caption`,
`.caption-user`, and `.caption-bot` rules are unchanged.

### C4 — No empty frosted box

Today the caption block always renders (empty, min-height 44px) —
invisible because the scrim fades to transparent. A visible bordered
panel must not sit empty on the stage. In `OrbField.tsx`, the block
renders conditionally:

```tsx
{(lastUser || lastAssistant) && (
  <div className="live-caption">…unchanged inner content…</div>
)}
```

and the `min-height` is dropped from the CSS (C3). No fade-in/fade-out
animation is added — captions persist once the first exchange happens,
so appearance is a once-per-session event and animating it is not worth
the code.

### C5 — `backdrop-filter` fallback

Some environments disable backdrop filters (or `prefers-reduced-
transparency` setups). Add:

```css
@supports not (backdrop-filter: blur(8px)) {
  .live-caption {
    background: rgba(4, 9, 12, 0.88);
  }
}
```

Solid-enough dark background, same border — readable without blur.

### C6 — What this plan deliberately does NOT do

- Does not move or reshape the wave (`VoiceWave.tsx` untouched — its
  `cy`, envelope, and amplitude math are the visual centerpiece).
- Does not touch `.orb-center`, the readout, or the state label.
- Does not change caption content, truncation (160 chars), or the
  transcript drawer — this is placement/legibility only.
- Does not add a user-facing toggle or persisted preference; if the new
  position turns out wrong, that is a follow-up decision, not a knob to
  ship speculatively.

---

## §2 Files

**New:**
- `tests/acceptance/caption-placement.md` — the §4 manual checklist

**Modified:**
- `web/src/components/OrbField.tsx` — move caption block out of
  `.orb-center` (C1), conditional render (C4)
- `web/src/command-deck.css` — `.live-caption` repositioned (C2) and
  restyled (C3), `@supports` fallback (C5)

No backend, config, or automated-test changes. (No unit tests exist for
CSS placement; verification is the build gate + the manual checklist.)

---

## §3 Implementation order

1. `command-deck.css`: rewrite `.live-caption` per C2+C3+C5.
2. `OrbField.tsx`: move + conditionally render the block per C1+C4.
3. `cd web && npm run build && npm run lint` — both must pass clean.
4. Add the §4 items to `tests/acceptance/side-drawer.md`'s stage
   section — no; **decision:** they get their own short file
   `tests/acceptance/caption-placement.md` (the side-drawer checklist
   is a completed phase's record; don't append to it).

---

## §4 Verification (manual acceptance — tests/acceptance/caption-placement.md)

- [ ] With no conversation yet: no caption panel is visible anywhere
      (C4) — just readout, state label, satellites, wave.
- [ ] Speak to Mortimer. While Mortimer is SPEAKING (wave at maximum),
      both caption lines are fully legible in the lower band, with the
      wave's center trace passing well above them.
- [ ] Open the side drawer and drag it wide: the caption panel stays
      centered on the shrunken stage and never slides under the drawer.
- [ ] Trigger the wake word (if configured): the wake flash does not
      wash out the caption text.
- [ ] Confirm the Systems/Librarian satellites (lower corners) are not
      covered by the panel at typical window sizes (≥1100px wide).
- [ ] `npm run build` and `npm run lint` pass.

---

## §5 Rollback

Pure additive/positional CSS + one JSX block move; revert the two files
to restore the centered caption exactly. No state, storage, or API
surface is touched.

---

## §6 Approval

**Implementation status (2026-08-16): implemented** — C1–C6 all done in
`web/src/components/OrbField.tsx` and `web/src/command-deck.css`;
`npm run build` and `npm run lint` both clean (0 lint errors; the 3
pre-existing `SideDrawer.tsx` fast-refresh warnings are unrelated).
`tests/acceptance/caption-placement.md` is the manual checklist —
still needs a human pass against a live session (nothing here requires
further code changes).

- [ ] Larry approves the plan.
- [ ] Implementation may begin.
