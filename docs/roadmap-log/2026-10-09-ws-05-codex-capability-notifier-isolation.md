---
date: 2026-10-09
system: codex
rows: [WS-05]
prs: [201, 200, 198]
---

Continue the existing #199 capability-fixture assignment on the same branch.
WS-17's approved a5b6f88→ce6cde8 all twelve comparison passed; subsequent final-head
CI failed the dry-child empty-directory assertion because the parent notifier
created unit.db, while the child uses probe.db. An actual parent poll reproduced
it. Test-only `08c0635` gives the child a separate sibling directory and forces
that parent poll; original JSON/empty-directory/argv/timeout assertions remain.
Injected child probe.db still fails. All other 60 function/class ASTs, helper,
runtime/read/scanner/pins/baseline/profile stay unchanged. Independent Codex
review approves the scoped repair; all 204 focused tests pass with required
loopback access.

[Receipt](../acceptance/model-use-enhancements/receipts/mar-capability-notifier-isolation-2026-10-09.json).
Larry reviews the separate follow-up PR and approves any revised baseline before
another VM comparison. No later source sent to Claude, production change or live
acceptance. Keep both prior passing VM and failed CI evidence.
