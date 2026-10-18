---
date: 2026-10-17
system: codex
rows: [WS-20, WS-13, WS-09, WS-11]
prs: [209, 210, 212]
---

# Three-PR review and cleanup

Larry requested review and cleanup of the three PRs. Reviewed source heads:
#209 `37b290d049fe4a79ab0830b0282401c3a3090d56`, #210
`8842503a4708759ca8a82c52a4d89d63179addab`, and #212
`e3a4b3db78f3eb896adb09dbfff9b20ea4484e4f`. #212 had already merged as
`f3d5378540390672ea91613c3a00fca0636ccd35` when queried. Review and synthetic
probes ran in isolated detached worktrees; no real VM was deleted and no
mailbox, vault, production source or deployment was changed.

## #209 — Documentation conflict resolved

Merged main `f3d5378` into the evidence branch, preserving both appended
joint-working progress records and all newer roadmap entries. The published
JSON parses, all twelve checks report success and each check hash matches the
corresponding attached log-manifest entry. Candidate and baseline are the
same snapshot: this is not a new historical-baseline comparison. The review
did not repeat the VM campaign or independently reread the raw private logs.
The receipt retains the two host OCR errors, live console failures, dirty
installed-artifact qualification and open acceptance gates. Historical mail
failures remain recorded; the current summary now points to their #212 fix.

## #210 — Changes requested before merge

### P1: Revalidate deletion eligibility under lifecycle synchronization

`sandbox/prune.py:163–168` computes the entire deletion plan once, then calls
`Controller.destroy` for each item. Destroy checks only that the parent VM is
stopped; it does not recheck the owning session, grace period or verification
children. A user can resume a planned idle session and begin validation while
an earlier deletion is running. Validation deliberately stops the parent.
The stale plan then deletes that parent despite its fresh owner and running
verification child. The session cannot resume its development VM afterward.

Reproduced with the PR's `PruneTests` fixture and real `Pruner.run` /
`Controller.destroy`, with only Tart commands mocked: select an eight-day-idle
parent, refresh the owner to `validating`, add a running verification child
before the plan is consumed. A newly computed plan correctly excludes the
parent, but `run` deletes it from the stale plan. Observed parent `deleted`,
child `running`.

Fix: synchronize pruning with session and child-allocation lifecycles, skip
busy owners, and re-read all eligibility evidence immediately before deletion
under the relevant locks. A second unlocked read alone does not close the
race. Preserve a consistent lock order because validation already holds the
session lock and invokes reclamation through `Images.create`. Add deterministic
regressions for owner refresh, a new child and a busy session between selection
and deletion. Never block/reenter the caller's own session lock during create.

### P2: Bind the new cleanup module to runner identity

`runner_fingerprint` in `sandbox/verify.py:23–30` hashes the existing controller,
image and verifier modules, but omits newly imported `sandbox/prune.py`, which
now executes inside creation and verification. A change to cleanup behavior
therefore leaves the recorded runner identity unchanged and cannot invalidate
a previously bound receipt as other runner changes do.

Reproduced by intercepting `Path.read_bytes` during the fingerprint operation:
`prune.py` was never read and altering its supplied bytes left the fingerprint
unchanged. Add the module to the runner's identity and a regression asserting
that a cleanup-module byte change alters that identity.

The focused suite passed: **57 tests and 4 subtests** across prune, images,
session, verify and launchd generation. These existing tests do not cover the
stale-plan interleaving above. The branch also needs its bounded sandbox owner,
scope and `com.mortimer.sandbox-prune` label reservation recorded in the roadmap
before landing; #210 currently changes no roadmap or log. Implementation stays
with its author; this review does not reassign the sandbox or install its job.

## #212 — No new blocking issue found in the changed code

The replacement snapshot removes names unset by the startup shell while
preserving unrelated inherited configuration; the vault fill follows it.
Resolving the env path before changing the loader's directory fixes the nested
relative-path case. The 30 registry/preflight tests passed independently.
The broader mail run initially hit the execution sandbox's localhost-listener
restriction; it is not a product failure. A host-permission rerun uses only the
synthetic local IMAP fixture, not real accounts: **117 tests passed in 16.83 seconds**.

WS-13's owner still needs to replace its stale review/merge-#212 handoff with
the actual merge and remaining deployment/production-repeat steps. Do not
convert the earlier user-run M1-1 into a new deployed-build acceptance.
