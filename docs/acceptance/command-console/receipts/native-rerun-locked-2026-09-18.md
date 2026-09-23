# Native rerun under locked Mac session — 2026-09-18

The native suites were rerun from the release-review worktree after the
repository acceptance reconciliation.

## Results

- `swift test --package-path macos/JarvisKit`: **190 passed, 0 failures**.
- `swift test --package-path macos/MortimerHost`: **241 executed, 8 failures**.

All eight failures are in `WindowVisibilityTests`. The fixture reports
`occlusionState` without `.visible` even after `makeKeyAndOrderFront`, and the
wave samples consequently remain at their initial count. The test itself
prints `active=true`, `screens=2`, `onSpace=true`, and `occlusion=8192`; this is
the expected failure mode when the host Mac is locked or the window server
cannot provide an unoccluded surface. The Mac automation surface independently
reported that the Mac was locked during this run.

This receipt is environment evidence, not a code waiver. The prior complete
MortimerHost run remains the sandbox implementation receipt (**241 passed**),
while the locked-session rerun cannot replace the required unlocked native
acceptance. Re-run the full host suite after manually unlocking the Mac; do not
weaken or skip `WindowVisibilityTests`.
