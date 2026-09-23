# Current full verification — 2026-09-18

This receipt records a fresh verification run from the current
release-review worktree after the monitor rehome fix. It is sandbox evidence;
it does not replace live provider, accessibility, rollback, deployment, or
daily-driver acceptance.

| Check | Result |
| --- | --- |
| `python -m pytest -q` | 2,611 passed / 4 skipped; 2 subtests passed |
| `swift test --package-path macos/JarvisKit` | 190 passed / 0 failures |
| `swift test --package-path macos/MortimerHost` | 244 executed, 0 failures, 3 skipped |
| `swift test --package-path macos/MortimerHost --filter ScreenPlacementTests` | 9 passed / 0 failures |
| `pytest -q tests/unit/test_plan_manifests.py` | 7 passed / 0 failures |
| `git diff --check` | passed |

The MortimerHost run recorded graph p95 at **9.627 ms** (maximum
**12.743 ms**), below the 33 ms gate. The three skipped native tests require
two connected displays; the physical unplug/rehome and reconnect behavior is
covered separately by the live candidate monitor receipts.
