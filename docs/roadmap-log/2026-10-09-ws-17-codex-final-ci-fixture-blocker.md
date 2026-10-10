---
date: 2026-10-09
system: codex
rows: [WS-17]
prs: [198, 201]
---

Final publication head `287b96d` CI failed only the WS-05 dry-child fixture's
empty-directory assertion: parent unit.db files appeared, with the actual child
configured for probe.db and its exit/exact JSON passing. An actual parent
notifier poll reproduced it. The approved a5b6f88→ce6cde8 offline twelve-check pass
remains source-specific positive evidence, not a green final-head CI claim.

Separate WS-05 PR #201 source `08c0635` isolates the child no-write directory,
forces parent polling and retains all original assertions/guards. 204 focused
cases pass; injected child probe.db still fails. This is outside WS-17's code
scope and was not inserted here or sent to Claude. Review/merge the fixture and
separately approve any revised reference before another comparison. Preserve
failed CI, prior VM/reviews and WS-13/release/live gates. No production change.
