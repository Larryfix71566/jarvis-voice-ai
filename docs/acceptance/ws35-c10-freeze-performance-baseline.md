# WS-35 C10: freeze-build performance baseline

**Status: instructions ready; measurements NOT RUN.** Codex prepares this procedure; Larry runs it on the Mac. Reviewer: Kimi. This is evidence collection before C1a merges, not deployment approval and not a pass for box 810.

Source: freeze `5777e98cf1cdbaa65eb13079044693794c071927`; closure plan §4 C10; `mac-acceptance-2026-11-11.md` box 810; approved `docs/interface-research/orb-plasma/ORB_SPEC.md`. Keep the freeze build available unchanged for comparison with the final build.

## 1. Before starting

1. Wait for the freeze build's separately approved deployment and same-build manifest (box 802). Record the loaded app path, app executable SHA-256, source commit, backend commit/configuration fingerprint and deployment receipt. Do not use the October production build as if it were the freeze. If these cannot be matched, stop and mark the run blocked.
2. Run from Larry's logged-in graphical Mac session, on AC power, with the same display topology, scaling/refresh rate, window sizes and audio input/output devices planned for the comparison. Record macOS, hardware, Xcode/Swift versions and whether power-saving modes are active. Close unrelated heavy jobs; do not change security/privacy settings or launch another backend.
3. Record interface layout 2 and thread preference, Liquid Glass state, Reduce Motion, Reduce Transparency and Increase Contrast. Record their original values before changing accessibility choices for the manual matrix, then restore them afterward. Do not change the frozen source or touch the production checkout.
4. Use synthetic, non-sensitive sample content. Do not grant file-send permission merely to measure a staged attachment. Live voice or model-backed sample creation is Larry-run under the already-approved acceptance session, not part of the automated commands below.
5. Make a dated receipt directory in your own evidence area. Preserve each run separately: the tests overwrite their JSON output. Keep raw logs and hashes, not just a copied p95. Record failures, skips and missing hardware without converting them to passes.

## 2. Reproducible component probes

In a separate Codex validation worktree checked out at the exact freeze SHA, with an empty `git status --porcelain`, run the following from the **MortimerHost package directory**. Dependencies/toolchain must already be available; stop and report if setup is blocked. Never run bundle/deploy/start scripts for these probes.

```sh
cd <isolated-freeze-worktree>/macos/MortimerHost
swift --version
xcodebuild -version
# Run separately, retaining each exit status and complete stdout/stderr.
swift test --filter OrbShellFrameTimeTests.testCrystalShellStaysWithinTheFrameBudget
swift test --filter MemoryGraphFrameTimeTests.testPanAndZoomFrameTimesOnTheDenseHubFixtureMeetTheP95Gate
swift test --filter SkillsRenderedNavigationBenchmarkTests.testRenderedCatalogSelectionAndCachedNavigationP95AtWideAndCompactSizes
```

Run each probe three times serially after the machine settles. Do not overlap these probes with C1a's builds/tests or other benchmarks. Retain all runs; do not select the fastest. For comparisons use the same run count/method and report each run plus the median of the three p50/p95 summaries. A test skip, zero completed frames, failed sensitivity control or missing output means unusable evidence, not a pass.

- **Orb:** `.build/interface-fixtures/orb-frame-time.json` under the package working directory. 1440×220 points, 10 warm-up + 300 recorded frames for each of empty/crystal; 310 render completions per probe. Record crystal p50, p95, maximum and both control/budget gates. The current test's sensitivity condition is crystal p50 > 1.10× empty p50; that is NOT the future regression rule. The current budget is crystal p95 ≤16.7 ms. Do not set `MORTIMER_SANDBOX_GUEST` to bypass enforcement. Historical 2026-09-29 p50 4.933/p95 14.150 ms is a reference only, not this baseline.
- **Graph:** `.build/interface-fixtures/P4-frame-time.json` under MortimerHost. 1440×900 points; 500 nodes/2,000 edges, dense hub degree 220, labels 48 characters; 150 pan + 150 zoom frames with the harness warm-up and four-node sensitivity control. Keep combined, pan and zoom p50/p95 plus the control. The existing test enforces 33 ms, slightly stricter than box 810's 33.3 ms; do not weaken it.
- **Skills rendered navigation:** preserve its JSON-bearing stdout. This is a component selection/navigation control, not proof of loaded stage/carousel performance. Do not label its timing as box 810's full-scene measurement.

These are frozen-source component probes. They do not prove the identity or behavior of the separately running installed app; retain both provenance records.

## 3. Full-scene baseline on the verified freeze app

The freeze has no new carousel. Use its current six-result workspace as the predecessor scene and label it explicitly. C5's final carousel comparison must use the same result contents/count and document the renderer change.

1. Prepare six stable, synthetic results (short/long text, weather, brief, graph and command content if available), two pinned results, and the graph view. Record exact fixture names/hashes and sizes. If a kind cannot be produced without an unapproved external call, record the gap instead of making that call.
2. Stage four synthetic attachments, the current count limit. The bot ceiling is 8 MiB per image, but actual normalized/accepted sizes can be smaller. Record each normalized MIME type, dimensions and byte count and the total actually accepted. Do not claim four maximum-size files merely from the configured limit. Keep them staged without sending for the baseline; if transfer/analysis is needed for the final workload, record that as a separately approved subcase.
3. Warm the scene for two minutes. Observe ten minutes of repeated result selection, navigation, graph pan/zoom and normal voice turns. Use a fixed recorded script of actions/content and repeat it for the final build. Note any audio dropout, unintended mic change, dropped frame burst, missing result, memory rise or failed operation with timestamp.
4. Capture Instruments traces for the installed app using the available Animation Hitches/Core Animation and memory tools. Record the actual Instruments template/version and event boundaries. Selection: input event to the newly selected content being presented. Navigation acknowledgement: input event to the visible acknowledgement. Graph: pan/zoom input through frame presentation. Collect at least 100 samples for selection and acknowledgement and 300 graph frames, retaining raw samples. Use nearest-rank p95 (sorted sample at `ceil(0.95*n)`). Do not use method execution time or manually guessed visual timing as frame-present latency.
5. If the frozen build/trace does not expose reliable start/end boundaries for a metric, mark that metric **unmeasured, instrumentation required**. Do not edit freeze code or substitute the skills benchmark. Ask Codex for a separately scoped measurement harness before treating box 810 as comparable. This procedure does not assert that new instrumentation already exists.
6. Record memory at the end of warm-up, then once per minute for ten minutes, and after clearing staged content/closing results and a one-minute settle. Use the same memory metric/tool both times (physical footprint preferred), recording bytes/MiB, minimum/maximum and end-minus-start. “Bounded” needs the trace, not one snapshot. The separate WS-03 box 702 limit is ≤10 MiB growth over ten minutes; do not silently use it to redefine box 810.
7. Repeat the full-scene recording for Liquid Glass on/off, Reduce Transparency, and Reduce Motion (individual changes with original settings recorded). Verify flat fallback/still-frame behavior visually. Missing topology or unavailable controls are limitations, not passes. Do not claim simultaneous voice-load coverage from the offline component probes.

## 4. Comparison and release gates

C10 supplies the baseline; it does not accept C1a, C5 or C6. Before C1a merges, Larry's dated baseline receipt must identify the freeze and explicitly list measured/unmeasured metrics. If key metrics are unmeasured, record the blocker and obtain a decision rather than treating this instruction file as the baseline.

For final box 810, compare like-for-like workload, hardware, configuration, method and units:

- Selection p95 ≤16.7 ms; navigation acknowledgement p95 ≤200 ms; graph pan/zoom p95 ≤33.3 ms.
- More than 10% worse than the corresponding baseline is a regression, even if the absolute ceiling passes. Report both gates; use `final / baseline - 1` only when baseline is positive and valid.
- For C6, arcs-only and arcs+refraction+shadow/cast-light probes use the same 1440×220/300-frame method. Each p50 and p95 must be ≤1.10× the crystal baseline; p95 must also meet the spec's <16.7 ms rule. A layerEffect that cannot render in the harness needs an explicitly recorded on-screen Instruments method and a matching crystal control. No substitute fallback is approved by this document.
- Memory remains bounded and audio has no regression during the combined load. Record observed defects separately from numerical gates. C9 phone performance needs a phone-specific probe; this Mac baseline is not a phone pass.

## 5. Receipt checklist (Larry fills after running)

- Date/time and operator:
- Freeze source, clean worktree, test toolchain:
- Loaded app path/hash, backend/configuration and deployment receipt:
- Machine/OS/power, screens/scaling/refresh, audio devices, window geometry:
- Layout/thread, glass and accessibility settings (before/after restoration):
- Synthetic result and attachment manifests, actual accepted count/bytes:
- Three component runs: exact command, exit status, counts, JSON/log path and SHA-256:
- Full-scene trace paths/hashes, sample counts and metric boundaries:
- p50/p95 per run, median summaries, absolute and regression limits:
- Ten-minute memory samples and audio observations:
- Unmeasured metrics, failures, skipped conditions and owner of next step:
- Larry baseline capture confirmation; Kimi review; C1a merge gate status:

**Preparation validation:** checked command/filter names and output paths against the freeze sources, attachment limits against `AttachmentStore.swift` and `jarvis/bot/shared_content.py`; documentation checks only. No benchmark, live voice run, deployment, setting change or acceptance occurred while writing this procedure.
