# GC24-03 — Protected result share-action guards

**Date:** 2026-09-25  
**Branch:** `codex/isolated-20260924`  
**Base:** `977f50bec7b77bd7d3381d3b8f3d63fa69bd00e2`; source tree remains dirty.  
**State:** protected-result share-action boundary is covered by a new regression; broader GC24-03 remains open.

## Boundary and evidence

The native result pane disables sharing/export for protected local results, and
the console action coordinator checks the result's protected policy before
creating a text preview. It also rechecks the preview's result identity before
copy, save, or presenting the system share sheet. Coverage previously tested
preview creation and export, but did not prove the three later actions remain
blocked if a protected result is represented by an image preview.

Added `testProtectedImagePreviewCannotReachCopySaveOrShareActions` to
`ConsoleActionCoordinatorTests`. The test creates a protected result, creates
a synthetic image preview referring to that result, and verifies the shared
action registry returns `unsupported` for copy, save, and share-picker actions.
The injected clipboard writer is not called and the preview remains local.
Existing text-preview and workspace-export checks remain in place.

## Verification

- `swift test --package-path macos/MortimerHost --filter ConsoleActionCoordinatorTests`:
  **16 tests passed, 0 failures**.
- Initial sandboxed SwiftPM attempt was blocked because `sandbox-exec` was not
  permitted; the same focused local command completed with the required
  elevated build-tool access. Compiler emitted existing deprecation warnings
  in unrelated test files.
- `git diff --check`: passed.

## Limits and next work

This verifies only the console action layer for protected-result copy/save/
share-picker actions and the protected-result export guard. It does not prove
all data sources, image-generation inputs, all local display/capture paths,
provider/tool continuations, memory, TTS, transcript/provider persistence,
telemetry, or live-candidate behavior. The full GC24-03 source-to-sink audit
remains open. No user data was exported or sent to an external recipient.
