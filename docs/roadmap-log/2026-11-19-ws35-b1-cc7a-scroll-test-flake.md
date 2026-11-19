---
date: 2026-11-19
system: claude
rows: [WS-35]
prs: [396]
---

# 2026-11-19: CC7a thread scroll test no longer flakes on hosted macOS

- **System:** Claude (Claude Code cloud session), at the coordinator's request after Larry's "continue development" (Claude Duet channel, 2026-11-19 02:10 UTC). Item: B1, the macOS Swift CI job.
- **JarvisKit on `0fffa48` (#386's merge):** not a code failure. SwiftPM could not fetch `stasel/WebRTC` ("Failed to connect to github.com port 443", then "Could not resolve host"). The same job passed on `a42814c`, `941d5a0` and `510b989`. No change made.
- **The failure that keeps coming back:** MortimerHost, `CC7aThreadAcceptanceTests.testActualScrollViewFollowsGrowingReplyOnlyWhileReadingTheEnd`. It failed 3 of 18 hosted MortimerHost runs from 2026-11-18 01:20 UTC (runs 44216163065, 44220803450, 44337366571, all pushes to `next`). Each time it timed out waiting for the "New" button ("unmet prerequisite: real New conversation control"). XCTest reported the thrown error as "InvalidTransition { phase: idle targetPhase: failed(deinit) }"; that string is not in this repo and its source is not identified.
- **Evidence (PR #396 probe, temporary workflow, since removed):** the failure reproduced once in the full suite and 3 times in 75 repeats of the CC7a suite. In every failure the test moved the clip view up (offset 259.35, 481.65 pt from the end), and 50 ms later the view was back at the end (offset 733.35, 7.65 pt), with no change to the document height (1233). The view then followed the new reply, as it should for a reader at the end, so no New button appeared. In every pass the offset held at 259.35. What moved the view back is not identified. The test moves `NSClipView` directly, not by a reader's gesture. 160 single-test repeats, half with a synthesized scroll-wheel event, gave no failures either way, so they do not tell the two inputs apart.
- **Change (test only):** `scrollReaderUp(to:in:)` moves the clip view and returns once the reader position has held for 250 ms, scrolling again (up to 5 times) and printing a line if it was put back. It replaces the fixed 50 ms sleep. The assertions are unchanged. No view file changed.
- **After the change:** 75 of 75 repeats of the CC7a suite passed. The put-back happened once and the test recovered from it. Full `validate.yml` on `a5a9d38`: all six jobs green.
- **Not in scope, still open:** `WindowVisibilityTests.testActualWindowHideShowAndDetachUpdateVisibility` failed once on this PR's superseded probe head (`d763140`), and on earlier hosted runs on other branches. It is a separate window-server timing failure.
- **Untested:** whether a real reader's scroll can be put back to the end the same way.
- **Next actor:** larry: merge #396.
