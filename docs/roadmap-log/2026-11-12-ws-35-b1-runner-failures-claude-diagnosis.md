---
date: 2026-11-12
system: claude
rows: [WS-35]
prs: [338]
---

# WS-35 B1 hosted-runner test failures — Claude's diagnosis, 2026-11-12

System: Claude (Claude Code cloud session, Larry's Claude Duet channel). Read-only diagnosis, approved by Larry on 2026-11-12 at 15:37 UTC and routed to Claude at 16:01 UTC. Its purpose is to inform Codex's fix on #338, not to compete with it. Claude did not write #338 and changed no Swift, test, workflow, plan or ROADMAP block. This environment has no Swift toolchain, so nothing below was run. Every claim cites a job log line or a source line. Causes that the evidence does not settle are marked **untested**, each with the check that would settle it.

## Sources

- [#338](https://github.com/Larryfix71566/jarvis-voice-ai/pull/338) at `e4ef119`. Codex has pushed nothing since that head (checked 2026-11-12).
- Run [43242777826](https://github.com/Larryfix71566/jarvis-voice-ai/actions/runs/43242777826) at `e4ef119`, MortimerHost job log. The line numbers below refer to this log.
- Run [43240213503](https://github.com/Larryfix71566/jarvis-voice-ai/actions/runs/43240213503) at `3c85fcb`, for comparison. Same six failing tests.
- The test and view sources on #338.

Background, from [Claude's #338 review](2026-11-12-ws-35-b1-claude-review.md): these tests pass on Larry's Mac with the same MortimerHost sources. Kimi's run at `4e58eaa` reported 590 tests and 0 failures in the main target, and `git diff 4e58eaa origin/next -- macos/MortimerHost` is empty.

## Findings by test

### 1. CompactConversationTests: two tests, OCR misreads rendered text

`renderedText(in:)` caches the hosting view into a bitmap (`bitmapImageRepForCachingDisplay` and `cacheDisplay`). It then runs `VNRecognizeTextRequest` with `recognitionLevel = .fast` and `usesLanguageCorrection = false`, strips whitespace, and the asserts check `contains`.

The failure messages print the OCR output. The expected strings are present, but misread:

| Expected (test line) | OCR on the runner (log line) |
| --- | --- |
| `Legacyusercaptionb931` (131, asserted at 158) | `L8gacyus8rcaptlDnb931` (7284) |
| `Audioinputnoticeremainsvisible` (67, asserted at 89) | `AudknInputnotlc8` (7289) |
| `Transcriptsentineluser6f3a` (56, asserted at 119) | `Transcriptsentineluser6f8a` (7290) |
| `TranscriptsentinelMortimer4a82` (57, asserted at 120) | `TranscriptsentinelMortimer4882` (7291) |

**Evidenced:** the views rendered the right content. The tests fail because `.fast` OCR misreads it on the runner. In the same output, `LegacyMortimercaptione527` and `Transcriptsentinelarrivingupdate9c17` were read correctly. This is not a rendering or layout regression.

**Untested:** why OCR quality drops on the runner. One candidate is a lower backing scale factor, which gives a lower-resolution bitmap. Logging `bitmap.pixelsWide` against the view's point width, and `window.backingScaleFactor`, in one runner job would settle it.

**Interaction with #337:** C1a renames `testLegacyCompactOrbRetainsTranscriptCaptions` to `testRetiredLayoutPreferenceCannotRestoreOrbTranscriptCaptions` and inverts its asserts to `XCTAssertFalse` (#337, lines 158–159). Under OCR this unreliable, an `XCTAssertFalse(contains:)` passes even when the caption is on screen. On the runner, that test would pass without proving anything.

### 2. Frame-time budgets: three tests, measured times over the gate

| Test (assert line) | Gate | p95 at `e4ef119` (log line) | p95 at `3c85fcb` |
| --- | --- | --- | --- |
| Orb crystal shell (`OrbShellFrameTimeTests.swift:156`) | 16.7 ms | 25.21 ms (7796) | 24.73 ms |
| Memory graph pan and zoom (`MemoryGraphFrameTimeTests.swift:306`) | 33 ms | 73.53 ms (7691) | 178.18 ms |
| Skills, wide, selection (`SkillsRenderedNavigationBenchmarkTests.swift:287`) | 20 ms | 158.28 ms (8059) | 214.08 ms |
| Skills, wide, navigation (`:289`) | 100 ms | 391.90 ms (8060) | 688.97 ms |
| Skills, compact, selection (`:287`) | 20 ms | 76.08 ms (8062) | 80.94 ms |
| Skills, compact, navigation (`:289`) | 100 ms | 224.86 ms (8063) | 245.63 ms |

For comparison, the Mac receipt for the orb records p95 14.150 ms (`docs/acceptance/adaptive-interface/receipts/orb-crystal-glass-2026-09-29.md`, line 21: "Crystal p50/p95: 4.933 / 14.150 ms").

**Evidenced:** the runner measures 1.5 to 8 times the Mac budgets, and the memory graph and Skills numbers vary by as much as 2.4 times between two runs of the same source. These are measurements of the runner, not of the code.

### 3. Skills benchmark: the rendered bitmap does not change

`SkillsRenderedNavigationBenchmarkTests.swift:280` fails at both sizes with "navigation must change the actual rendered output": one distinct bitmap digest, not more than one (log lines 8058 and 8061).

The test already documents this behaviour. Its guest branch (flag read at line 144, comment at lines 273–276) says that "Tart's virtual display can return a stale NSHostingView bitmap even while native accessibility/render tests show the updated skill". Under `MORTIMER_SANDBOX_GUEST=1` it skips this assertion and both timing budgets.

**Evidenced:** the same stale-bitmap symptom that the repo already records for Tart VMs.

**Untested:** that the hosted runner and Tart have the same cause.

### 4. WindowVisibilityTests: the wave does not tick while visible

`testWaveStopsSamplingWhileWindowHiddenAndResumes` (`WindowVisibilityTests.swift:205–245`) counts calls to the `presentation` closure over 0.2-second windows. It fails at line 225 ("A visible active wave must sample new measured activity") and line 237 ("Restoring the window must restart the active wave"). The sample count stays at 2 in both windows (log lines 8379 and 8380).

The view drives sampling through `TimelineView(.animation(minimumInterval:paused: !visible || !windowVisible))` (`VoiceWaveView.swift`, lines 72 and 76). Its visibility comes from `WindowVisibilityReader`.

**Evidenced:** visibility reporting works on the runner. The other five tests in the class passed, including `testActualWindowHideShowAndDetachUpdateVisibility` (18.4 s) and the two `testVisibleFixtureRecovers…` tests. What fails is the animation timeline producing ticks inside a 0.2-second window.

**Untested:** whether the runner's display link fires at all, or only too slowly for 0.2 s. Codex's local note on the fixture (active = false, one screen) is consistent with this, but does not prove it. Counting ticks over a longer window (for example 2 s) in one runner job would separate "never ticks" from "ticks slowly".

### Not one of the six: MemoryGraphImageStoreTests

`testCancelledImageStaysStoppedUntilExplicitReload` failed at `3c85fcb` and passed at `e4ef119`, with identical Swift source. Its result varies between runs. No cause is established here.

## What the six have in common

Every failure is a rendering, timing or OCR effect. None is a logic assertion about app state. The repo already has a switch for this class of environment: `sandbox/verify.py:73` exports `MORTIMER_SANDBOX_GUEST=1` inside Tart verification VMs. Only two tests honour it: `OrbShellFrameTimeTests.swift:129` and `SkillsRenderedNavigationBenchmarkTests.swift:144`. The B1 workflow does not set it (`.github/workflows/validate.yml` on #338 has no reference to it).

## Options for the fix

These are decisions for Larry and Codex, not recommendations Claude is acting on.

1. **Treat the hosted runner as a guest.** Set `MORTIMER_SANDBOX_GUEST=1` in the MortimerHost leg, and extend the guest handling to the memory graph frame-time test, the two OCR tests and the wave test. This keeps everything else in the suite running on CI. The cost: the guest bypass skips the stale-bitmap check and the timing budgets, so on CI those six would prove only that the tests run.
2. **Keep these tests on the Mac only.** Skip them on CI under a narrower CI-only flag, and keep them as Mac acceptance evidence. The cost is the same loss of CI coverage, but the skip is named for what it is.
3. **Make the OCR tests robust instead of skipping them.** For example, use `.accurate` OCR, or assert on accessibility text instead of OCR. This needs a runner rerun to prove, and changes what the tests measure.

Whichever option is taken, the C10 rule applies: the timing budgets are Mac gates, and hosted CI must not stand in for the Mac probes. A skip on CI must not weaken the threshold on the Mac.

## Unchanged

No source, test, workflow, plan, ROADMAP block or acceptance checkbox was changed. No GitHub review or comment was posted on #338. No Swift test or benchmark was run.
