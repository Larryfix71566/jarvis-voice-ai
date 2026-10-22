---
date: 2026-10-22
system: codex
rows: [WS-20]
prs: [210, 222]
---

# Final cleanup review evidence recovered for WS-20 reconciliation

Read from [PR #222](https://github.com/Larryfix71566/jarvis-voice-ai/pull/222)'s
complete final-report body section on October 22. Exact reviewed source:
`1632afb726ae2fb4df25c6349647f2e731a29766`; merge:
`406bec0660a292447c58ba9bf786307581808854`.
The original final report below hashes to
`fcddaff9a1247c13775b16210cd9311739c97b6f9d3137f6f373f83a7a6348d2`
(UTF-8, one terminal newline), independently matching the release owner's
retained report digest. This commit preserves the report independently of the
mutable PR body. The old committed regression receipt's pending-review field
is historical; no cleanup repair or review rerun is needed for this index fix.

Disposition: original finding resolved; no new blocking findings. Coverage is
static exact-source review, not reviewer test execution, real cleanup,
installation or live acceptance. Conservative retention under corrupt
ownership metadata remains an explicit limitation. No owner source receipt
is overwritten. This is an evidence-index correction within WS-20 only.

---

## Disposition: Finding 1 (global malformed-record blast radius) — **RESOLVED**

### Grounds, from the final code

The original finding was that a single malformed/symlinked record *anywhere* on the host would abort `deletion_guard` for the task currently being deleted, and since `Pruner.run()` invokes the guard per-candidate, this would wedge reclamation of **every other task**, host-wide, including completely unrelated ones.

In the final diff, `plan()` (`sandbox/prune.py:150-187`) and `deletion_guard` (`sandbox/prune.py:213-243`) both branch on `state.get("purpose")`:

- **Verification tasks bypass the global issue check entirely.** In `plan()`, the retention guard is `if state.get("purpose") != "verification" and (self._issues or task in duplicates):` — verification records never hit this branch. In `Pruner.reason()`, the `purpose == "verification"` check returns `"verification finished; receipt and logs retained on host"` unconditionally, before `children`/`quiet`/owner lookups are even consulted. In `deletion_guard`, the whole `_sessions()/_records()` global-issue check is inside `if state.get("purpose") != "verification":` — a verification task's own guard never performs that scan.
- **Development/legacy tasks retain the broad, conservative check** (`self._issues or task in duplicates` in `plan()`; the explicit `session_issues or task_issues or task in duplicates` raise in `deletion_guard`). Any unreadable/malformed/symlinked record anywhere still retains *all* dev/legacy candidates — this is unchanged from before, but it is now scoped to that subset.

This is exactly the bounded policy described in the task: verification VMs — independently valid, grace-aged, stopped, with host-retained evidence — are decided purely on local data and are immune to unrelated corruption; development/legacy VMs, where owner/child relationships are genuinely ambiguous under corruption, are conservatively retained, accepting that headroom may not be recoverable. The tradeoff is explicit, not an accidental side effect: it's surfaced via `report["issues"]`/`report["kept"]` with per-record categories and persisted to `prune.log` whenever issues exist (`run()`'s logging condition now includes `report["issues"]`), and no corrupt file is ever read-and-discarded or overwritten (categories are content-free; raw bytes untouched).

This is directly exercised by `test_corrupt_metadata_retains_unknown_development_but_not_finished_verification` and `test_late_corruption_rechecks_development_but_continues_verification`: a corrupt/unreadable record (session or task, injected before or mid-run) retains the unrelated development VM but does **not** block deletion of the finished verification VM. `test_malformed_ownership_cannot_grant_orphan_cleanup` confirms the narrower, intentional dev-side behavior is otherwise preserved unchanged.

I did not execute these tests; this conclusion is based on reading the guard/plan logic directly against the scenarios the tests claim to cover.

### Why I'm not forcing a waiver here

The residual breadth — any one malformed record anywhere still retains *all* development/legacy candidates indefinitely, including a genuinely orphaned, reclaimable one, with no self-healing path short of an operator removing the bad file — is real and still present. I'm not calling it a new blocker because the task framing explicitly scopes and accepts it ("partial availability, NOT a claim that all corruption effects disappear"; "including when that means disk headroom cannot be recovered"), and the final code makes the tradeoff legible (categorized, logged, never silently dropped) rather than hiding it. If that acceptance were withdrawn, this would revert to a blocking finding for the dev/legacy path specifically — but it would no longer be host-wide across purposes, since verification is now structurally decoupled.

## New blocking findings

None found in this pass. Specifically checked and found sound:
- **Lock ordering / no new deadlock risk:** `Images.create` releases `start.lock` before calling `reclaim()`/`require_headroom()` for verification children (`sandbox/images.py:108-125`), so `reclaim → Pruner.run → Controller.destroy` re-acquiring `start.lock` on the same call stack cannot self-deadlock. Confirmed by `test_validating_session_can_reclaim_unrelated_vm_for_headroom`.
- **Fail-closed state write ordering preserved in `destroy`:** `state["status"]="deleting"` and the final `"deleted"` write both happen *inside* `with guard() ...` (`sandbox/control.py:448-454`), so a guard rejection before `yield` leaves the record at `"stopped"`, matching `test_busy_mutation_locks_retain_old_stopped_tasks`.
- **Child-registration-before-reclamation race (core WS-28 fix) intact:** verification child directory + `state.json(status="creating", parent_task=...)` are written under `start.lock` before any reclaim pass runs, so rule 4 (live-child protection) sees the child before the parent could be judged disposable. Parent-already-deleted is explicitly checked under the same lock (`sandbox/images.py:113-116`), covering the reverse race.
- **Symlink handling is consistent and non-destructive:** both `_sessions()` and `_records()` check `path.is_symlink() or path.parent.is_symlink()` before any read, and `deletion_guard` separately rejects symlinked lock paths — no symlink target is ever opened or logged.
- All eight named protections (stale-plan, busy target owner, duplicate owner, late child, stopped probe, child registration, fingerprint, and the independent-verification-candidate scan) remain present and distinguishable in the final code, each with a corresponding test named in the diff.

## Coverage limits

- Diff/code-reading review only; no commands, tests, or tools were run. Test-pass/fail claims (160 passing, the named regressions on `241a382`, four new corruption-coverage methods) are taken as given context, not independently reproduced.
- Line numbers are read from the provided file listings, not a checked-out, built repository.
- `Images.create`'s snapshot/hydration path after the lock release (`sandbox/images.py:122+`), `Controller.command`/`read`/`save`/`task_dir`, and session.py beyond the one cited call site are referenced but their internals are not part of this diff and are assumed correct, not verified, from this patch alone.
- No assessment of concurrent multi-process behavior beyond what `flock(LOCK_NB)` semantics and the given tests demonstrate; no load/stress or real filesystem/Tart execution was performed or simulated by me.
