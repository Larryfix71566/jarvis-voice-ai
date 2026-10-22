---
date: 2026-10-22
system: claude
rows: [WS-28]
prs: [222]
---

- 2026-10-22 (Claude cross-review of WS-28 at 1632afb: policy agreed, one required CLI change): Claude (Cowork) reviewed the exact merged source 1632afb (#222, 406bec0) on 10-22; sandbox/ on main 636880e is identical. This entry records it without editing Codex's row (C1); the full text and a reproduction are REVIEW_WS28_1632afb.md and REPRO_ws28_cli.py in Larry's Claude outputs. sandbox/tests: 160 passed. Agreed: the bounded corruption policy (verification VMs reclaim independently of unrelated malformed records; development and legacy VMs are retained while any ownership or child record is malformed, symlinked or duplicated), the start.lock race fix with non-blocking leases, and the prune.py runner fingerprint. Required before any real prune, reclaim or dry-run-based decision: sandbox.prune main() prints retained VMs under 'would delete' in dry-run, prints neither retained VMs nor malformed records in a real run, and exits 0, so the operator is told a retained development VM will be deleted and is never told why it was kept. Fix the output (would-delete vs retained vs record issues) and return a distinct nonzero code when issues exist, with a regression test. Non-blocking: no status or notice surfaces prune.log, and require_headroom's advice to run sandbox.prune does not help when development VMs are retained. No real cleanup, clone or production change was run.
