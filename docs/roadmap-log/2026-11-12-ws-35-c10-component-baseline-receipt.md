---
date: 2026-11-12
system: claude
rows: [WS-35, WS-36]
prs: [335]
---

# WS-35 C10 component baseline receipt, freeze `5777e98`, 2026-11-12

System: Claude (Claude Code cloud session, Larry's Claude Duet channel). Larry ran the probes on his Mac. The coordinator session drafted this receipt from his uploaded files, and Claude checked every number against the raw files and wrote this entry. It records C10 section 2 (component probes) as Larry's dated baseline for box 810. It does not accept C1a, C5 or C6. **Larry has not yet confirmed this text.** Merging it, or correcting it, is that confirmation.

The C10 steps are Codex's document in [#335](https://github.com/Larryfix71566/jarvis-voice-ai/pull/335) (`docs/acceptance/ws35-c10-freeze-performance-baseline.md`, not yet merged). This receipt sits in `docs/roadmap-log/` because `docs/acceptance/**` is in WS-35's scope; Codex may move it there.

## Provenance

- **Run:** 2026-11-12, about 16:04–16:06 UTC (the orb JSON's `recorded_at` for run 1 is `2026-11-12T16:04:12Z`), by Larry on his Mac.
- **Source:** a fresh clone, detached at `5777e98cf1cdbaa65eb13079044693794c071927` ("HEAD is now at 5777e98c Merge pull request #329"). `git status --porcelain` printed nothing. From Larry's terminal transcript in the channel, 16:13:25 UTC.
- **Command:** for runs 1 to 3, `swift test --filter` on each of the three tests below, one at a time, in `macos/MortimerHost`. After each run, `.build/interface-fixtures/orb-frame-time.json` and `P4-frame-time.json` were copied. Same transcript.
- **Hardware and OS:** Apple M5, Mac17,4, main screen scale 2, macOS 27.0.1 (26A434). From the orb JSON's `hardware` block.
- **Toolchain:** Apple Swift 6.4.2 (swiftlang-6.4.2.1.9), target arm64-apple-macosx27.0.0, Xcode 27.2 (27B52). From Larry's terminal output at 16:03:09 UTC, same Mac. The script also wrote `toolchain.txt`, but that file was not uploaded.
- **Exit status:** 9 of 9 exited 0 (`exit-codes.txt`). Each log reports "Executed 1 test, with 0 failures" for the filtered test.
- **Sandbox bypass:** off. The Skills JSON reports `timing_budget_enforced: true` and `virtualized_guest: false` in all three runs, and the orb JSON reports `"budget": {"enforced": true}`.
- **Not recorded, Larry to fill:** AC power, display topology, accessibility settings, Liquid Glass state.

## Results (ms; median of three in bold)

### Orb (`OrbShellFrameTimeTests.testCrystalShellStaysWithinTheFrameBudget`), 1440×220, 300 frames per probe

| | run 1 | run 2 | run 3 | median |
| --- | --- | --- | --- | --- |
| crystal p50 | 5.428 | 7.576 | 6.150 | **6.150** |
| crystal p95 | 13.499 | 13.413 | 13.677 | **13.499** |
| crystal max | 14.373 | 15.155 | 15.346 | 15.155 |
| empty p50 | 0.745 | 0.766 | 0.767 | 0.766 |
| empty p95 | 0.840 | 0.871 | 0.846 | 0.846 |

The budget gate (crystal p95 ≤ 16.7) and the sensitivity gate (crystal p50 > 1.10 × empty p50) passed in all three runs.

### Memory graph (`MemoryGraphFrameTimeTests.testPanAndZoomFrameTimesOnTheDenseHubFixtureMeetTheP95Gate`), 1440×900, 500 nodes, 2,000 edges, hub degree 220

| | run 1 | run 2 | run 3 | median |
| --- | --- | --- | --- | --- |
| combined p50 | 8.042 | 7.997 | 8.078 | **8.042** |
| combined p95 | 10.689 | 9.656 | 9.643 | **9.656** |
| pan p95 | 9.921 | 9.660 | 9.591 | 9.660 |
| zoom p95 | 10.788 | 9.630 | 10.703 | 10.703 |
| control p50 | 4.031 | 3.904 | 3.553 | 3.904 |
| stress/control p50 | 1.995 | 2.048 | 2.274 | 2.048 |

The p95 gate (≤ 33) passed in all three runs. Stress/control p50 exceeded the test's 1.25 floor in all three.

### Skills rendered navigation (`SkillsRenderedNavigationBenchmarkTests`, component control, not box 810)

| | run 1 | run 2 | run 3 | median | test gate |
| --- | --- | --- | --- | --- | --- |
| wide selection-to-layout p95 | 12.073 | 13.402 | 13.591 | **13.402** | ≤ 20 |
| wide cached navigation p95 | 42.951 | 45.383 | 45.714 | **45.383** | ≤ 100 |
| compact selection-to-layout p95 | 7.118 | 7.958 | 8.120 | **7.958** | ≤ 20 |
| compact cached navigation p95 | 26.800 | 28.598 | 28.888 | **28.598** | ≤ 100 |
| wide selection render p95 | 28.656 | 30.585 | 30.705 | 30.585 | — |
| compact selection render p95 | 14.648 | 15.808 | 16.057 | 15.808 | — |

Every run reports `distinct_rendered_frames: 64` at both sizes, and 0 detail requests during measurement.

## Measured and not measured

- **Measured:** C10 section 2, the three component probes above.
- **Not measured, blocked:** section 3, the full-scene Instruments baseline on the installed freeze app, with the memory trace and the accessibility matrix. It needs the freeze build deployed (box 802), and the deploy waits on [#339](https://github.com/Larryfix71566/jarvis-voice-ai/pull/339).

## Finding for C6

Crystal p50 ranged from 5.428 to 7.576 ms over three runs of the same build; run 2 is 23% above the median. Crystal p95 ranged from 13.413 to 13.677 ms, about 2%. C6's rule of at most 1.10× the crystal p50 would therefore fail on noise alone if measured against a stored p50. Larry decided on 2026-11-12 that C6 compares against crystal runs from the same session. That decision is recorded in [the C6 decision entry](2026-11-12-ws-36-c6-same-session-comparison-decision.md) and in `ORB_SPEC.md`. This receipt stays as the record of the freeze.

## Raw files

[`2026-11-12-ws-35-c10-component-baseline-raw/`](2026-11-12-ws-35-c10-component-baseline-raw/) holds the 16 files Larry uploaded, byte for byte: nine test logs, six JSON files and `exit-codes.txt`. `SHA256SUMS.txt` in that folder is computed from those copies. It matches the coordinator's hash list for the same uploads. Larry's own `SHA256SUMS.txt` and `toolchain.txt` from the run folder were not uploaded, so the hashes cannot be checked against the ones made on his Mac.

## Unchanged

No source, test, workflow or acceptance checkbox was changed. No benchmark was run by Claude.
