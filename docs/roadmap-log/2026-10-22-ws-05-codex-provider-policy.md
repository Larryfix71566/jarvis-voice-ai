---
date: 2026-10-22
system: codex
rows: [WS-05]
prs: [239]
---

# WS-05 — 2026-10-22

Claimed bounded selective-policy correction on existing WS-05 branch after
fast-forward to main fccb760. Only direct Anthropic/OpenAI APIs are retired;
other recognized providers retain their existing explicit routing and gates.
No protected endpoint changes, native/installer edits, live inference or
service operations. Release owner retains guarded installation/restoration.

Implemented protected endpoint recognition, SAYGM catalog-policy compatibility
and redirect refusal. Reproduced five failing cases before repair; 243 focused
synthetic tests pass. Full offline and publication checks pending.

Draft #239 publishes the correction. The first broad run was interrupted
after test-only dotenv contamination; an isolated rerun exposed one genuine
single-registry-loader violation. Repaired by reusing the existing loader
with an explicit protected path. Expanded focused tests: 302 passed / three
prerequisite skips. Frozen full and CI results are recorded on #239; release
owner retains review/integration/installation. No new live inference.

Claimed alpha.11 offline compatibility continuation after main 636880e,
within the existing WS-05 subscription/runtime scope and branch. Source is
limited to exact version admission and related capability tests; preserve
all runtime receipt/privacy gates. Independent source review and focused
verification precede draft publication. No PR #243 merge, installation or
live test; prior exact-binary live acceptance does not transfer to alpha.11.
