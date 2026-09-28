# GC24-06 receipt — Atlas card accessibility content

**Date:** 2026-09-25  
**Branch:** `codex/isolated-20260924`  
**Base:** `977f50bec7b77bd7d3381d3b8f3d63fa69bd00e2`  
**State:** source change and native tests verified in the dirty isolated tree;
live VoiceOver acceptance remains open.

## Gap and change

Knowledge Atlas cards visually show a title, summary, and optional source, but
the parent button set a replacement accessibility label containing only the
card kind and title. VoiceOver could not announce the card's useful content.
`AtlasCard` now derives a stable label from kind and title and an accessibility
value from the full summary and optional source. The Atlas card control uses
these fields and supplies a result-navigation hint or an informational-card
hint. The visual layout, card identity, result routing, and selected state are
unchanged.

## Verification

- `swift test --filter KnowledgeAtlasTests` — **12 passed, 0 failures**.
- Full `swift test` in `macos/MortimerHost` — **267 executed, 7 skipped, 0
  failures**. The skip set includes hardware/display-gated cases.
- Both commands used the existing package checkout and `--disable-sandbox`,
  with Swift module caches directed to `/private/tmp` because the managed
  workspace cannot write to the user's home cache. No network fetch was
  needed for the successful run.

The focused suite includes a mounted `NSHostingView` test. It inspects the
rendered accessibility tree and verifies that the actual result control
exposes the full title/type label and summary/source value, and that its
standard accessibility press action invokes result selection. The test does
not establish live VoiceOver traversal or keyboard-only acceptance on the
running candidate; those remain open.
