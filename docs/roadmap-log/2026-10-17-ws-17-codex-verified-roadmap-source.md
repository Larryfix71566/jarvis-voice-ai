---
date: 2026-10-17
system: codex
rows: [WS-17]
prs: [215]
---
# Complete roadmap snapshots retain guarded source attestation

Approved scope #215 merged as `b2d1b10`; implementation verifies every derived
card, local provenance and guarded dated-log hash before source approval.
Reader/source-policy tests: 138 passed. Native decoder regressions: three passed.
Real source yields 22 cards and 185 dated logs without the old 30,000-character
cutoff. Unknown lifecycle remains unclassified. No privacy-floor relaxation.
The complete native view, filters, refresh and filtered sharing remain open.
Full backend rerun is pending; no deployment or final acceptance is claimed.
