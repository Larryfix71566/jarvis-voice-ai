---
date: 2026-11-12
system: claude
rows: [WS-35]
prs: [338]
---

# WS-35 B1 Swift CI — Claude's independent review of #338, Claude, 2026-11-12

System: Claude (Claude Code cloud session, Larry's Claude Duet channel). Nonauthor reviewer named by the closure plan's B1 row ("Claude, Kimi (reviewers)"). Claude did not write #338. Documentation only: this entry. It does not change the WS-35 block, which is Codex's scope.

## What was reviewed

[#338](https://github.com/Larryfix71566/jarvis-voice-ai/pull/338), draft, head `31e52a54ac7de88e53da98ff6cc324f13ee453b6`, base `next` at `a1369e223e51cc499c8f942fae95133994a4facb`. Hosted run [42957886479](https://github.com/Larryfix71566/jarvis-voice-ai/actions/runs/42957886479) on 2026-11-11, 04:14–04:18 UTC.

The only workflow change is one new `swift-tests` job in `.github/workflows/validate.yml`:

- `runs-on: macos-26-intel`, 45-minute timeout, `contents: read`, `fail-fast: false`.
- Matrix: `macos/JarvisKit`, `macos/MortimerHost`, `ios/MortimerPhoneCore`.
- Xcode 26.3 is pinned through `DEVELOPER_DIR`. A preflight step checks macOS 26 or later, x86_64, the Xcode version and `xctest`.
- For MortimerHost only, a fixture step finds Python 3.12, imports the phone admission and authority modules, builds `PhoneRemoteAuthorityOwner` and exports its paths.
- Then `swift test --package-path <package>`.

`actions/checkout@v7` with `persist-credentials: false` matches the other workflows. The PR also carries the #334/#335 documentation (orb spec, UI directions page, C10 baseline, C0 review log, AGENTS.md, ROADMAP, plan), as its body says.

## Results of the hosted run

| Check | Result | Evidence from the job log |
| --- | --- | --- |
| Swift (macos/JarvisKit) | success | "Executed 239 tests, with 0 failures" |
| Swift (ios/MortimerPhoneCore) | success | "Executed 67 tests, with 1 test skipped and 0 failures" |
| Swift (macos/MortimerHost) | **failure** | compile error, no tests ran |
| validate, allowlist, policy-tests, controller-tests, knowledge-base | success | check runs on the head commit |

The PhoneCore skip is `PhoneResultCommandsProcessTests.testCheckedModelFiveActionsThroughNativeV4ProofSession`, "Requires configured disposable Python/native-owner process fixtures". The fixture step runs for MortimerHost only, so this skip is expected. Codex's B1 log already discloses it.

## The MortimerHost failure

In the MortimerHost job, the toolchain preflight passed, and so did the fixture step (it compiled `PhoneRemoteAuthorityOwner`). The test build then stopped with:

```
macos/MortimerHost/Sources/MortimerHost/Console/SkillsWorkspaceView.swift:380:9: error: the compiler is unable to type-check this expression in reasonable time; try breaking up the expression into distinct sub-expressions
```

The job ended with "Process completed with exit code 1". The other "error" strings in the log are warning context: a `locationManager(_:didFailWithError:)` signature and a deprecated placemark API. They do not fail the build.

Line 380 is the body of `workspaceContent(width:)`. On `next` at `a1369e2`, that expression is one modifier chain on `workspacePresentation(width:)` containing 1 `.background`, 2 `.task`, 14 `.onChange`, 1 `.onAppear` and 1 `.onDisappear`. #338 does not touch this file. It is identical on `main` and `next`, and it was last changed on 2026-09-30 by `51da994`.

What the run shows: this source does not type-check within the compiler's limit on the hosted x86_64 runner with Xcode 26.3. Whether it compiles on Larry's Mac with his toolchain is untested here. A local `swift build --package-path macos/MortimerHost` on that Mac would settle it.

## Verdict

- **The workflow is correct as written.** Every step it adds ran as intended: preflight, fixture preparation, and full suites on the two packages that compile. No changes to `validate.yml` are requested.
- **B1 cannot go green on this PR alone.** It needs a source change in `SkillsWorkspaceView.swift` that splits the chain, for example by moving the `.onChange` group into a separate `ViewModifier` or helper function. That file is outside B1's scope (`.github/workflows/validate.yml`). It needs a Swift compile to verify. Under the closure plan, Claude writes no Swift until B1 is green, so Claude cannot make this fix. Who owns the fix is Larry's call. It could land as its own small PR against `next`, with #338 rerun after it.
- Not a finding: the job's 45-minute timeout leaves room. The failing leg ran about 4 minutes.

## Addendum, same day: Codex's repair at `3c85fcb` and `e4ef119`

Codex pushed two commits on 2026-11-12 after the run above:

- `3c85fcb`: "split Skills workspace observers for Swift 6.2". Codex's B1 log says Larry approved this split on 2026-11-12.
- `e4ef119`: documentation only. It updates the B1 log, the closure plan and the WS-35 block.

The Swift source is identical at the two heads.

**The repair is behavior-preserving.** It splits `workspaceContent(width:)` into four chained helpers, each returning `some View`: `workspaceSelectionContent`, `workspaceLifecycleContent`, `workspaceActionContent` and `workspaceContent`. Extracting the modifier lines from all four helpers, in call order, gives 44 lines. They are identical, line for line, to the 44 lines of the single chain on `next`. The one call site, line 369, still calls `workspaceContent(width:)`. No other file changed.

**The compile blocker is resolved; the Host suite now fails on tests.** Checked in the job logs:

| Run (head) | Host result | Failing tests |
| --- | --- | --- |
| [43240213503](https://github.com/Larryfix71566/jarvis-voice-ai/actions/runs/43240213503) (`3c85fcb`) | "Executed 618 tests, with 3 tests skipped and 16 failures" | 7 |
| [43242777826](https://github.com/Larryfix71566/jarvis-voice-ai/actions/runs/43242777826) (`e4ef119`) | "Executed 618 tests, with 3 tests skipped and 14 failures" | 6 |

Six tests failed in both runs:

- `CompactConversationTests.testLegacyCompactOrbRetainsTranscriptCaptions`
- `CompactConversationTests.testV2CompactOrbOmitsTranscriptButKeepsConversationAndNotices`
- `MemoryGraphFrameTimeTests.testPanAndZoomFrameTimesOnTheDenseHubFixtureMeetTheP95Gate`
- `OrbShellFrameTimeTests.testCrystalShellStaysWithinTheFrameBudget`
- `SkillsRenderedNavigationBenchmarkTests.testRenderedCatalogSelectionAndCachedNavigationP95AtWideAndCompactSizes`
- `WindowVisibilityTests.testWaveStopsSamplingWhileWindowHiddenAndResumes`

`MemoryGraphImageStoreTests.testCancelledImageStaysStoppedUntilExplicitReload` failed at `3c85fcb` and passed at `e4ef119`, with identical Swift source. That test's result therefore varies between runs. Why it varies is not established here.

JarvisKit and PhoneCore passed in both runs. The first run's counts and test names match Codex's B1 log.

The same tests on Larry's Mac:

- Kimi's 2026-11-06 revalidation ([log](2026-11-06-ws-17-kimi-combined-main-revalidation.md)) ran `swift test --package-path macos/MortimerHost` at `4e58eaa` on Larry's Mac. The main target reported "590 tests, 5 skips, 0 failures". The only failure was F1, in the separate PhoneRemoteAuthority target.
- None of the seven tests above is in that log's skip list.
- `git diff --stat 4e58eaa origin/next -- macos/MortimerHost` is empty. Apart from the behavior-preserving split, the hosted runs compiled the same MortimerHost sources and tests that passed on the Mac.

So these seven tests pass on Larry's Mac and fail on the hosted x86_64 runner (Xcode 26.3, Swift 6.2.4). Why they fail on the runner is not established here: hardware, display/WindowServer, timing budgets and OCR are all untested candidates. A rerun on the Mac at `3c85fcb` would confirm that the split itself changes nothing there.

**Updated verdict.** The workflow and the Skills view split are both correct. B1 is still not green. The remaining blockers are the six consistent test failures plus the one that varies. All seven pass on Larry's Mac with the same sources. Their diagnosis is the next step, and Codex's B1 log says it needs Larry's authorization. The question of who should fix the compile timeout, raised above, is settled.

## Unchanged

No source, test, workflow, plan, ROADMAP block or acceptance checkbox was changed. No GitHub review or comment was posted on #338.
