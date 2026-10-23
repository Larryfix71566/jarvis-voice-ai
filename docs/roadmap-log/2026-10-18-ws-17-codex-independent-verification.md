---
date: 2026-10-18
system: codex
rows: [WS-17]
prs: [222, 223]
---

# Frozen candidate passed all twelve independent VM checks

Verified #222/#223 merged as `406bec0`/`d38c886`, refreshed the registered
WS-17 branch, and ran the unchanged full-profile verifier on candidate
`305540b8…b361` against approved protected reference `08c0635`. Attempt
`105c7adecbd444eeb56844bc1badedd4` passed all twelve checks, final source
comparison and receipt/log-hash validation; terminal exit 0 at 22:20 UTC.
[Receipt, source identities, results and limits](../acceptance/command-console/receipts/ws17-independent-verification-2026-10-18.md).

The new isolated VM home prevented cleanup of existing assets. Both fresh
owned task clones were deleted; all seven existing VMs, rollback/app hashes
and image/settings pointer were preserved. Candidate native app: 563 tests,
eight skips, zero failures; skipped permission/physical cases remain open.
UI2-14 technical evidence is complete, while its global reconciliation and
UI2-15/16/17/18, UI2-22…25, dependent 04/09/13 and physical/observation gates
remain with their existing owners. No source/profile/test/budget waiver,
provider call, installation, host security change, app restart or deployment.
