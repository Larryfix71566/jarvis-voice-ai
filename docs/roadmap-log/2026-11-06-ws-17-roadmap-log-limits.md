---
date: 2026-11-06
system: codex
rows: [WS-17]
prs: []
---
# Bounded roadmap log and display repair

Codex, branch `codex/roadmap-log-limit-20261106`, base `555fe86`.
Larry explicitly approved the narrow registration exception and reader/tests,
host-attestation and roadmap-specific delivery/decoding scope. Preserve all
historical logs and source/privacy caps; no production or model action.

The reader now has a 1,024-file ceiling, bounded reads, both declared and
actual aggregate-byte checks, and a 1 MiB complete snapshot ceiling. Larger
log sets retain every per-log hash in the sealed, host-rebuilt snapshot while
a deterministic manifest commitment keeps the existing 256-ref ceiling.
Roadmap-only display paths consistently cap envelopes at 1,200 KiB. Generic
limits and fail-closed behavior are unchanged. Final focused regressions passed 156 tests. Independent static review
approved without actionable defects. Backend unit/integration: 7,997 passed,
145 skipped, 583 subtests passed and 18 warnings; full JarvisKit: 239 passed;
MortimerHost roadmap controls: 10 passed; policy: 9 passed; evaluations:
13 passed. Import smoke, latency, frontend build and roadmap checker passed.
The full suite preceded three additional passing focused tests; source was
unchanged. Native refresh coverage includes large complete replies and
oversized-reply preservation of existing state. No live
acceptance, publication, merge or deployment is claimed.
