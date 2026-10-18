---
date: 2026-10-18
system: codex
rows: [WS-28]
prs: [210, 221]
---

# Cleanup prerequisite repair candidate

After claim #221 merged `afa1dd9b`, Codex repaired the stale cleanup-plan
deletion boundary and bound `prune.py` into the verifier runner fingerprint.
Eligibility is revalidated while shared lifecycle and mutation locks exclude
new start/child/session activity. Verification children reserve their parent
before reclamation; deletion winning first makes child creation refuse.

All 153 synthetic controller tests pass. Eight new methods fail against old
main (nine assertions including subtests) and pass on the candidate. Existing
145-test baseline, shell syntax and whitespace pass. Exact patch/log hashes
and the remaining gates are in `sandbox/acceptance/2026-10-18-cleanup-regressions.json`.
No profile, baseline, scanner, permission, job or production change occurred.
Independent review and real release verification remain pending; no real
prune/reclaim/clone, installation, app restart or deployment was invoked.

Additional source review identified foreign-session locking that prevented
otherwise-safe reclamation and could fail low-disk validation. Three new
regressions fail on initial `24206281` and pass after target-owner leasing and
ambiguous-owner refusal. The full suite is now 156 tests, zero failures.
The old Claude packet/result cannot clear this amended exact source.

## Corruption-policy correction

The final `241a382` Claude report identifies global malformed-record blocking.
Its original report is preserved. Candidate correction keeps unknown-owner/
child development VMs retained but permits independently valid stopped
verification VMs under their existing local rule. Initial and final scans
handle malformed shapes and symlinks without aborting independent candidates;
reports expose retained task IDs and content-free record categories. No new
ownership index, migration or authority. Full controller suite: 160 passing.
Final exact-source re-review and current CI remain pending; no real operations.
