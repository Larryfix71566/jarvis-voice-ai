# Upgrade Plan Phase 5e Acceptance Checklist — Memory visibility/correction panel

Manual acceptance for MORTIMER_INTERFACE_UPGRADE_PLAN.md Phase 5e. Run the
full stack (`./scripts/mortimer.sh`) and open the web console.

## Panel basics

- [ ] Click **🧠 Memory** in the top bar. A panel opens listing stored
      facts (key + content), the running summary (if any), and a capacity
      readout (`N / 30 facts`).
- [ ] If you have fewer than ~5 facts stored, hold a short conversation
      that states a new preference or fact, end the session (memory
      fold-in fires), reopen the panel, and confirm the new fact appears
      within ~15s (the panel polls every 15s) without a manual refresh.

## Correction

- [ ] Click the **×** next to a fact. Confirm it disappears from the list
      and a "Forgot ..." note appears.
- [ ] Ask Mortimer (by voice, in a new session) about that fact. Confirm
      it no longer has that information — the deletion actually took
      effect, not just in the panel's local state.

## Learning visibility

- [ ] If you have any behavioral tendencies still accumulating (not yet
      promoted to facts — check the `observations` table or watch for
      repeated similar requests across a few sessions), confirm the
      "Learning (not yet facts)" section shows the key and a
      `sessions/PROMOTE_AFTER` progress readout that increases as more
      sessions exhibit the pattern.

## Capacity (pairs with Phase 5c)

- [ ] If the fact count exceeds 30 (the `MAX_FACTS` cap), confirm the
      usage readout turns into the "over capacity" state and shows the
      note about `user.*` facts being prioritized.

## Shared surface regression (plan's explicit risk)

This phase touches `App.tsx`, which the Git and Edit panels also share.

- [ ] With the Memory panel open, click **⚙ Repo**. Confirm the Git panel
      still opens and functions normally (status, commit draft flow).
- [ ] With the Memory panel open, click **✎ Edit**. Confirm the Edit panel
      still opens and functions normally.
- [ ] Confirm all three panels can be toggled open/closed independently
      without interfering with each other.

## Automated coverage

Backend: `tests/unit/test_admin_api.py::TestMemoryEndpoints` (6 cases —
empty overview, facts+summary listing, observation promotion-progress
shape, delete removes a fact, delete-not-found, and independence from git
state). Frontend: `npm run build` (strict TypeScript compile + production
bundle) passed clean with `MemoryPanel.tsx` and the `App.tsx` wiring
included — confirmed via a direct `tsc -b` run in this sandbox after
working around a pre-existing native-binding gap in the sandbox's `vite`/
`rolldown`/`oxlint` install (unrelated to this change; resolved with a
plain `npm install`). `npm run lint` reports 0 errors.
