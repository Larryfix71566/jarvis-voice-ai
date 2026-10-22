---
date: 2026-10-22
system: codex
rows: [WS-05]
prs: []
---

# Bounded harness remediation registration

Larry dispatched remediation of PR #253's confirmed findings while preserving
#242 at d476905057fc29207338721ce9ec2a452cb2085d and #253 at
a568f7dc282fff7436a4527feb7d162a2b021c81. This docs-only amendment uses main
c63ecce97108787c55ef55fad73d32236694cc65 and leaves original claim #241 untouched.
The old claim is unmerged and does not satisfy the main-first rule.

Registers only the future codex/ws05-harness-remediation-20261022 branch and
precise paths in WS-05 Scope; refines the same pending CX-28 boundary. No
source edits, application tests, benchmarks, model changes or installation.
Read-only review confirmed the cache lost-update race, matching and ID gaps,
ambient test dependencies and incorrect cancellation/threshold expectations.
The reviewed commit-range patch SHA-256 is
661fae5da017849c444729546734db9056cf6cf596181a7ee4eb33cc0b7bb06a.

Before amendment, the roadmap checker reported zero errors and warnings.
Publication records the post-edit documentation checks separately. The
47-pass Claude VM receipt remains author evidence; no Mac or CI claim is made.

Next: larry/authorized maintainer decides claim landing; codex then refreshes
main and prepares only the bounded offline repair. Preserve provider/release,
WS-03 and every unfinished acceptance gate. No merge permission is implied.
