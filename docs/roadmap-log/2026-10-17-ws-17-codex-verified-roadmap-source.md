---
date: 2026-10-17
system: codex
rows: [WS-17]
prs: [215, 216]
---
# Complete roadmap snapshots retain guarded source attestation

Approved scope #215 merged as `b2d1b10`; implementation verifies every derived
card, local provenance and guarded dated-log hash before source approval.
Reader/source-policy tests: 138 passed. Native decoder regressions: three passed.
Real source yields 22 cards and 185 dated logs without the old 30,000-character
cutoff. Unknown lifecycle remains unclassified. No privacy-floor relaxation.
The complete native view, filters, refresh and filtered sharing remain open.
Final source `0c6e1af`: full backend 6,543 passed / 11 skipped; affected native Recents/router 28 passed. The earlier storage failure did not recur; its cause remains unknown. Draft #216 is not ready to merge. No deployment or final acceptance is claimed.
