---
date: 2026-10-17
system: codex
rows: [WS-17]
prs: []
---

Real AppKit menu regression failed four checks with two store entries and now
passes after rebuilding the transient menu on consoleRevision; 35 related native
tests and 185 focused backend/prompt tests pass. Larry's original one-result
button remains a separate open trace/retest. Authorized pre-guidance Haiku
baseline on ed4107b: numbered selection FAIL (view_set twice), repeat weather
PASS (Analyst delegation), 1/2 total. Candidate routing and roadmap-read guidance
added; live comparison not yet run. Reserved the bounded roadmap snapshot field
before reader implementation. No production or #210 cleanup changes.

Broader local validation of this slice: Python unit suite 6,503 passed / 11 skipped / 13 warnings; full MortimerHost 553 executed / six skipped / zero failures, including actual private captures. No Tart/cleanup run or deployment. These are local suite results, not independent release acceptance.
