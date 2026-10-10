---
date: 2026-10-10
system: codex
rows: [WS-05]
prs: [201, 200, 198]
---

#201 merged as `83d90e86780c726684a295557057741ab7266397`; its final
`de4381c` head passed all five CI checks. Validate records 6,280 unit passes,
11 skips and two passing subtests; 196 integration passes and four skips.
Larry approved immutable source `08c06357267ef1348ec4b64dfdd12b26d4710a50`
for **offline WS-17 verification only** on 10-10. The repaired reference
introduces no runtime/configuration/profile change; already merged #197 is
also present in this newer reference.

The unchanged twelve-check comparison against WS-17 candidate
`59d57ea3f7eb007a02a17f425accf186a38108c2` is running at this dated record;
Codex records its terminal outcome under WS-17. No pass, cleanup, release or
live acceptance is inferred. The prior `a5b6f88`→`ce6cde8` pass and subsequent
CI failure remain separate history. Preserve the original October 9 receipt
snapshot, with the merged/CI/approval follow-up appended explicitly.

[Evidence](../acceptance/model-use-enhancements/receipts/mar-capability-notifier-isolation-2026-10-09.json).
No new Claude source transmission, production deployment, provider call or
account/routing activation; other model/runtime prerequisites and acceptance
flags remain unchanged.
