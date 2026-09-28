# GC24-03 — Protected result rendering boundary

**Date:** 2026-09-25  
**Branch:** `codex/isolated-20260924`  
**Base:** `977f50bec7b77bd7d3381d3b8f3d63fa69bd00e2`; source tree remains dirty.  
**State:** native protected-payload rendering is constrained and covered; broader GC24-03 remains open.

## Gap and behavior

The shared `DisplayContentView` rendered a protected result body as non-selectable,
but still rendered its ancillary images, links, commands, and clipboard content.
That could start remote image requests, open external destinations, or expose
copy-to-clipboard controls if a protected payload were malformed or later
extended. `WorkspaceResultPane` also honored a saved Sources/Connections mode
for protected results, allowing those alternate renderers to bypass the
body-only local surface.

Protected payloads now render only their verbatim body in
`DisplayContentView`; text selection is disabled. The workspace does not show
result-mode switching for protected payloads and always selects the protected
body renderer. Ordinary payload rendering, source navigation, and command
copy affordances remain unchanged.

## Verification

- `swift test --package-path macos/MortimerHost --filter ProtectedDisplayContentTests`:
  **2 tests passed, 0 failures**. A rendered-pixel comparison proves that
  protected ancillary fields produce the same view as a body-only payload;
  an empty-body comparison proves the body remains visible. Ordinary command
  copy remains accessible.
- `swift test --package-path macos/MortimerHost --filter ConsoleActionCoordinatorTests`:
  **16 tests passed, 0 failures**, including protected-result copy/save/share
  action guards.
- Swift compiler emitted existing deprecation warnings in accessibility tests.
- `git diff --check`: passed.

## Limits and next work

This closes the native protected-result renderer and the named result-action
sinks. It does not prove all result producers, memory graph/sharing policy,
provider/tool continuations, TTS, provider/session persistence, telemetry,
every display or screenshot path, or exact-candidate behavior. The full
GC24-03 source-to-sink audit remains open; T4a external STT/TTS and
same-session Supervisor history are accepted residuals that must follow the
existing T3/T4b contracts.
