# Protected-window capture gate repair (WS-16)

**Status:** IN REVIEW (PR #117); real capture passed, deployment blocked by CX-14.
**Owner:** Codex. Larry runs DEPLOY-MAIN and accepts the live result.
**Recorded:** 2026-09-29.

## Problem and evidence

DEPLOY-MAIN for `d460809` stopped in phase A. JarvisKit passed 215/0;
MortimerHost ran 374 tests with five skips and one failure:
`ProtectedDisplayContentTests.testProtectedContentInActualWindowCaptureMatchesBodyOnlyReference`
at line 134. The script did not change production, which remains `e340101`.
The local log is
`/Users/larryfix/MortimerRollback/logs/deploy-main-20260929-154149.log`.

The assertion printed two 1240 × 840 RGBA captures. Read-only analysis found
21,946 differing pixels (2.107%): the outer capture edge and the rendered
body text near x=24–290, y=29–57. No pixels differ inside a 64-pixel inset.
The fixture creates and captures separate windows sequentially. Window
composition, placement or text-render timing is a hypothesis, not yet a
proven cause. The failure is not evidence that ancillary protected fields
were displayed, and it is not a passing privacy check.

## Fixed contract

- A protected payload displays its local body, with no image, basemap, link,
  command or clipboard content from the same payload.
- The test must still use ScreenCaptureKit to prove what an actual window
  capture contains. Passing through a headless skip cannot close this gate.
- Preserve a full-window comparison against the body-only reference. Do not
  crop away edges, loosen color tolerances, disable capture permission, or
  change production display code to satisfy the test.
- Keep failure output bounded: report dimensions, differing-pixel count and
  location rather than dumping millions of channel values.
- `DisplayContentView.swift` is active WS-15 scope. If evidence points to a
  product leak or a necessary display-code change, stop and coordinate through
  `ROADMAP.md` §4 before touching it.

## Implementation sequence

1. Claim WS-16 in `ROADMAP.md` on main, with this plan and the dedicated
   `codex/ws16-protected-capture-20260929` worktree.
2. Reproduce the actual-window test in a foreground-capable session with
   Screen Recording access. Record window frame/backing scale, capture
   dimensions and bounded pixel-difference locations; distinguish window
   edge changes from body-text changes.
3. Stabilize the fixture without reducing coverage. Prefer rendering the
   protected payload and the body-only reference in the same NSWindow at the
   same pixel-aligned frame, with a bounded wait for the window's content to
   settle before each capture. Keep the payloads and entire captured area.
   Treat any remaining content difference as a failure.
4. Run the focused protected-display tests repeatedly with real captures;
   require zero skips for the actual-window case. Run the full MortimerHost
   suite and JarvisKit if the package boundary is affected. Preserve all
   other test thresholds and assertions.
5. Push a scoped PR with captured counts and exact test results. After merge,
   Larry reruns DEPLOY-MAIN. Only a passing deploy allows WS-08 orb visual
   acceptance to resume.

## Progress

- 2026-09-29: Larry assigned Codex. Source inspection shows
  `ProtectedDisplayContentTests.swift` builds two NSWindows sequentially
  and compares raw pixel arrays; the source's protected render branch
  ignores ancillary fields. No source change or product code change yet.
- 2026-09-29: Claim landed in PR #116 (`5182bdf`). The test fixture now
  renders protected and body-only payloads into the same NSWindow, keeping
  its frame and ScreenCaptureKit capture target constant. It still compares
  every RGBA pixel in the actual capture and fails on any difference;
  failures report only a count and bounds, avoiding multi-megabyte dumps.
  No product display code or privacy assertion changed.
- 2026-09-29: Focused protected-content tests: four executed, one actual-
  window test skipped because this shell's test host could not activate,
  zero failures. Full MortimerHost: 374 executed, seven skipped, zero
  failures. A skipped actual capture does not satisfy the live acceptance
  gate. Run it from an interactive Terminal with Screen Recording access,
  then run DEPLOY-MAIN after review/merge.
- 2026-09-29: Larry's interactive Terminal run also skipped at the app-active
  prerequisite. The test did not need foreground app activation: it already
  requires a visible, unoccluded window and a real ScreenCaptureKit capture.
  Removing only that prerequisite made the full-window protected/body-only
  comparison execute and pass four consecutive focused runs with zero skips.
  The full MortimerHost suite then passed 374 tests with six unrelated skips
  and zero failures; its actual-window capture test executed and passed.
  PR #117 review/merge and Larry's DEPLOY-MAIN run remain open.
- 2026-09-29: Main `05c4a40` (WS-15 PR #114) was merged into the WS-16
  branch. The isolated real capture passed again without a skip. The full
  MortimerHost suite ran 383 tests, six skipped, with two assertions failed
  in `MemoryGraphClosureC3Tests` because new WS-15 `RadarMapView.swift`
  calls bare `URLSession.shared`. That code is Claude's active WS-15 scope;
  CX-14 records the handoff. DEPLOY-MAIN remains blocked until it is fixed.
