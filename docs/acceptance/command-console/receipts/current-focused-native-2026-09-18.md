# Current focused native acceptance — September 18, 2026

Commands were run from `macos/MortimerHost` against the current release-review
worktree and candidate runtime:

```sh
swift test --filter ScreenPlacementTests
swift test --filter 'FullConsoleRenderingTests|ConsoleActionCoordinatorTests|ContentPanelTests|SupportingDisplayAcceptanceTests'
```

Results:

- `ScreenPlacementTests`: **8 passed, 0 failures**. This includes virtual
  screen clamping, manual-frame preservation, mirrored-screen handling, and
  synthetic disconnect/reconnect recovery.
- Combined Command Center/rendering/ownership filter: **39 passed, 0
  failures**, including the four-result bounded stage and live-window
  response-routing tests.

These tests strengthen sandbox and synthetic topology evidence. They do not
replace the physical unplug/reconnect, live spoken-response, provider,
accessibility, rollback, or daily-driver gates.
