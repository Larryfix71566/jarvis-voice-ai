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

Alpha.11 runtime/test source `b4ce39a` passed 182 focused offline tests and
independent tools-disabled Fable 5.1 review with no blocking findings. Initial
Unix socket failures were tool-sandbox restrictions; the same-source host
rerun passed. Receipt includes launcher/test provenance and review dispositions.
Draft publication only: final-head CI pending; no merge or installation.
The diagnostic marker is informational, not a substitute for operator/live
authorization. Renewed exact-binary workload acceptance remains blocked until
fresh bounded live-test authorization; existing cost confirmations stand.

Separate alpha.11 integration candidate starts at coordinator-verified main
2944080 and preserves frozen014f915. Both dated canonical-plan additions and
the active #257 harness claim/CX-28 are retained; no runtime/test bytes change
from the reviewed provider slice. Removed raw personal launcher paths from the
final receipt and corrected the author disposition without rewriting history.
Fresh docs-delta review and publication CI precede coordinator-owned merge.
No installation, activation, live tests or acceptance advancement.
