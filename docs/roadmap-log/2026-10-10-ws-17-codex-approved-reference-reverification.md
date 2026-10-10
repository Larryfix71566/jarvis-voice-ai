---
date: 2026-10-10
system: codex
rows: [WS-17]
prs: [198, 201]
---

Larry explicitly approved `08c06357267ef1348ec4b64dfdd12b26d4710a50` for
WS-17 offline verification only. PR #201 merged as `83d90e8` with five green
checks; Codex integrated current main into `codex/ws17-closure-20261007`.
Preparing an immutable candidate and exact manifest for the unchanged twelve
profile checks. Application source retains the two exact reviewed commits;
no later source is sent to Claude. Earlier passed comparison and failed CI
remain distinct evidence. Actual new results follow after completion.

Remaining: revised comparison, WS-13 revision 4 before #198, Larry's separate
release approval/deployment and exact-build UI2-22…25. No live acceptance or
production change is recorded.

The actual `08c0635`→`59d57ea` independent comparison completed with all twelve
required checks passed. Baseline/candidate Python 6,280/6,366; JarvisKit
227/232; MortimerHost 514/551 with seven/eight prerequisite skips; zero failures.
Independent audit matched every actual source path/mode/blob, ordered check,
log hash and fixed pin. Both owned VMs stopped, zero running, settings/image
record unchanged. Five CI checks passed on frozen candidate `59d57ea`.
[Completed receipt](../acceptance/command-console/CC7A_OFFLINE_VERIFICATION_2026-10-10.json).
Source-specific previous pass/failure/review records remain intact; no live
acceptance or release is inferred. WS-13 revision 4 and Larry's separate
release/deployment decision remain the next gates.
