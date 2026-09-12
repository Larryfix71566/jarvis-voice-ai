# C1 — P1 gap closure record

Date: 2026-09-12. Candidate base `6bf0270` + uncommitted C1 edits (working tree, not committed). Verified on Larry's MacBook Air host toolchain (Apple Swift 6.3.3) via `closure-checks/run-host-c1.command` → `closure-checks/logs/host-c1.log`, SHA-256 `f7a004857207208bfa2d7e69127e02619ff66b40fa9c7077f09dd10813ba9c35`.

Baseline on the same host before any edit: `host-baseline.log` (SHA-256 `2de3e8f3bc0d2897167ded9721f36c7a1cbc6932414c74827689c0ec1972d25c`) — 125 tests, 0 failures, exit 0, including the nine `WindowVisibilityTests` that fail headless.

Result: **130 tests, 0 failures, exit 0** (125 baseline + 5 new). No existing test changed, removed or skipped.

| Gap | Change | Evidence |
|---|---|---|
| G01 keyboard navigation | `Drawer/DrawerTabStrip.swift`: the scroll container is `.focusable()` with a `@FocusState`; ← / → move selection by one tab through the shared `select` setter (no wrap at the ends), Home / End jump to first / last; accessibility hint added; focus ring kept visible. Selection reveal reuses the existing `onChange(of: selectedTab)` scroll. | `DrawerTabStripKeyboardTests.testArrowAndHomeEndKeysMoveSelectionAndRevealTheSelectedLabel` — synthesizes real `NSEvent` key events (Tab, ←, →, Home, End) into a 300 pt `NSWindow`, asserts each resulting selection and that every keyboard-selected label's accessibility frame lies inside the scroll viewport (outer padding, arrows and gaps excluded). Passed, 4.49 s. |
| G02 300 pt chrome, docked and detached | No source change needed — the fixture proves the existing layout. | `DrawerViewMinimumWidthTests` — hosts the whole `DrawerView` (strip + Aa + ⧉ + ×) at `AppTuning.drawerMinWidth` with an offline client, iterates all eight tabs in both `isPoppedOut` states, asserts chrome and the selected label are inside the window. Passed (docked 2.91 s, detached 3.01 s). |
| G03 §7 typography | Interface plan §7 amended: "Tab label text initial 11 points (amended 2026-09-12 …)". No strip change; 11 pt is what Larry accepted live. | `docs/plans/MORTIMER_ADAPTIVE_INTERFACE_PLAN.md` §7 |
| G04 scroll-offset writer | `Drawer/DrawerModels.swift`: per-tab scroll-writer lease (`claimScrollWriter`, `releaseScrollWriter`, `recordScroll`, `isScrollWriter`); `Drawer/DrawerScrollPosition.swift` claims on appear, records only while it holds the lease, releases on disappear. Remembered offsets are never discarded by a release. | `DrawerScrollWriterTests` (2 tests): outgoing presentation cannot overwrite or erase; leases independent per tab; non-finite offsets rejected; negative overscroll clamps to 0. Existing `DrawerScrollRestorationTests` and `DrawerModelsTests` unchanged and green. |

Open on this phase: nothing automated. Manual/VoiceOver traversal of the focused strip remains a C8 row (§9.2 "keyboard traversal, visible focus and VoiceOver names").

Contracts: UI-1 (all eight keys/labels/order from `DrawerState.tabKeys`, unchanged), UI-5 (writer lease is arbitration only; one owner unchanged), UI-7 (no skip/xfail; deprecation warnings for `accessibilitySetValue` are pre-existing in the same form in `DrawerTabStripRenderingTests`).

PR: "P1b — header keyboard navigation and minimum-width coverage" (C9 step 3), stacked on #66 and the L3 hoist PR.
