---
date: 2026-10-22
system: codex
rows: [WS-20]
prs: [249]
---

# Checker policy: approved decision, pending main registration

Larry's direct answer “agreed proceed” at 2026-10-22 15:39:07 UTC approved the
question recommending errors fail CI while warnings remain advisory, explicitly
preparing a reviewed workflow change without branch-protection or product
acceptance changes. Parent supplied that trusted transcript with the enforcement
dispatch. Larry separately approved merging documentation-only #249 after final review/CI
at 15:56:35 UTC. That does not authorize its inherited draft dependencies,
implementation code, deployment or PR #243.

Main inspected: `636880eabbe9dc756c30df7128d0a90c02d222bd`. WS-20's current claim
excludes checker enforcement and retains Claude B4 ownership; §0 requires claim
on main before code. This docs-only registration and exact proposed patch make
the next action reviewable without pretending the claim or enforcement is live.
WS-12 has accepted status and empty scope. Sync-owner coordination was sent before
registration edits. No workflow, checker source or repository test is changed.

#247 remains frozen at `e28452676c38c989308668fe3377c79ac9cd2635`. It was retargeted
to main and closed/reopened under parent authorization to run its existing CI;
that publication cycle is independent of this policy proposal.

## Exact proposed workflow delta (not applied)

```diff
--- a/.github/workflows/validate.yml
+++ b/.github/workflows/validate.yml
@@ -19,10 +19,9 @@
         run: python scripts/check_allowlist.py origin/main...HEAD
 
       # WS-20 B4: roadmap drift check (docs/plans/ROADMAP_JOINT_WORKING_PLAN.md).
-      # Warn-only for the first week (Larry, 10-02): findings show as
-      # annotations and never fail the job. Drop --warn-only to make it a gate.
-      - name: Roadmap drift check (warn-only)
-        run: python scripts/check_roadmap.py --warn-only
+      # Larry approved 2026-10-22: errors fail CI; warnings remain advisory.
+      - name: Roadmap drift check (errors fail, warnings advisory)
+        run: python scripts/check_roadmap.py
 
   policy-tests:
     runs-on: ubuntu-24.04
```

## Existing-checker command verification

Fixture runner imports the existing test helpers, creates one temporary Git
repository and invokes the unchanged checker with `GITHUB_ACTIONS=true`.
No real repository/runtime data or external services are used. The original
31-test suite remains green at its recorded source; no broad suite rerun.

```json
{
  "source": "e28452676c38c989308668fe3377c79ac9cd2635",
  "checker_sha256": "014f628d76f92de21f46b52bfd3a28419ac7ef2cbebfcb252c2862b356da3919",
  "proposed_patch_sha256": "6d6b042bf9339d5b6046f83fd86f345586790d2250c370a51b6983d74c1c9705",
  "scope": "Existing unchanged checker; proposed invocation without warn-only; temporary synthetic fixtures; no workflow edit applied",
  "cases": [
    {
      "case": "clean",
      "exit": 0,
      "expected_exit": 0,
      "stdout": "roadmap check: 0 errors, 0 warnings\n",
      "passed": true
    },
    {
      "case": "error_missing_scope",
      "exit": 1,
      "expected_exit": 1,
      "stdout": "ERROR   WS-20: missing fields: Scope\n::error file=ROADMAP.md,line=7::WS-20: missing fields: Scope\nroadmap check: 1 errors, 0 warnings\n",
      "passed": true
    },
    {
      "case": "warning_unknown_ws",
      "exit": 0,
      "expected_exit": 0,
      "stdout": "WARNING WS-99: mentioned but not defined as a block\n::warning file=ROADMAP.md,line=29::WS-99: mentioned but not defined as a block\nroadmap check: 0 errors, 1 warnings\n",
      "passed": true
    },
    {
      "case": "mixed_error_warning",
      "exit": 1,
      "expected_exit": 1,
      "stdout": "ERROR   WS-20: missing fields: Scope\n::error file=ROADMAP.md,line=7::WS-20: missing fields: Scope\nWARNING WS-99: mentioned but not defined as a block\n::warning file=ROADMAP.md,line=28::WS-99: mentioned but not defined as a block\nroadmap check: 1 errors, 1 warnings\n",
      "passed": true
    },
    {
      "case": "legacy_warn_only_error",
      "exit": 0,
      "expected_exit": 0,
      "stdout": "ERROR   WS-20: missing fields: Scope\n::warning file=ROADMAP.md,line=7::WS-20: missing fields: Scope\nroadmap check: 1 errors, 0 warnings (warn-only)\n",
      "passed": true
    }
  ]
} 
```

## Independent proposed-diff review and prerequisite disposition

One official tools-disabled Claude Code Max review returned **no diff blockers**,
conditioned on a real full-history strict roadmap check. Reviewer saw only the
supplied packet and did not execute tests. The assertion that the real roadmap
had never been checked was a packet-coverage limitation: #247's prior clean run
was already recorded. To satisfy the prerequisite explicitly with fresh refs,
Codex fetched origin and ran the unchanged script with no `--main` override on:

- main `636880eabbe9dc756c30df7128d0a90c02d222bd`: 0 errors, 0 warnings, exit0;
- frozen #247 `e28452676c38c989308668fe3377c79ac9cd2635`: 0 errors, 0 warnings, exit0;
- this documentation-only registration delta: 0 errors, 0 warnings, exit0.

The actual enforcement candidate must still repeat the strict check at its own
exact source after claim registration. No historical test or review substitutes
for future changed-source verification. The reviewed patch remains unapplied.
No enforcement CI or product acceptance is claimed.

Review payload SHA-256:
`70018e1e68dbf573f785e5fb7b38d5abe99f6dd1f3e12cd7280e852af62e326b`
(40,780 bytes). Runtime reported `claude-opus-5-5`, one turn, successful result;
no model override, tools, API-key fallback or live benchmark. Full report below.

<details>
<summary>Original independent review, unchanged</summary>

# WS-20 Checker Policy Review: Proposed Patch Only

## Verdict

The diff itself has **no blockers**. One condition, listed first below, must be met before the workflow edit is applied. This review covers only the proposed patch. It does not approve, execute, merge or accept anything.

## Gating condition before apply

**The live ROADMAP.md has never been run without `--warn-only`.**
- The checker scans the whole `ROADMAP.md`, not the PR diff.
- Every case in the evidence is synthetic.
- `test_the_real_roadmap_parses_into_complete_blocks` checks only "missing fields". Its comment says lifecycle-word errors in the real roadmap are left for the owners to fix while CI is "warn-only for now".
- If `ROADMAP.md` on the candidate or current main has any error, every PR to main will fail, including unrelated ones.
- **Needed before applying:** a recorded run of `python scripts/check_roadmap.py` (no `--main`, so it uses the CI default `origin/main`) on the exact candidate with a full checkout. It should show 0 errors, or Larry should explicitly accept the existing errors.

## Semantics check (confirmed by reading source)

- **Exit code:** `return 1 if errors and not args.warn_only else 0`. Errors make the step fail; warning-only results exit 0. ✔
- **Annotations:** with `--warn-only` removed, each finding's own level maps to `::error` or `::warning`. A `::warning` never fails the step; the failure comes only from the exit code. ✔
- **Severity:** no checker code changes. The hunk (`-19,10 +19,9`) matches the supplied `validate.yml` and changes only the comment, step name and flag. ✔

## Unintended workflow effects (non-blocking; record them)

1. **Merge blocking through the `allowlist` job.** The roadmap step runs inside the `allowlist` job. If branch protection already requires `allowlist`, roadmap errors now block merges without any protection change. The claim mentions this; Larry should know that "errors fail CI" means "errors block merge" wherever that check is required.
2. **Failures not caused by the PR.**
   - Because `fetch-depth: 0` provides `origin/<branch>` refs, the merged-branch check gives a verdict (error) rather than a question (warning). A row can turn into an error when some *other* branch merges.
   - If a `**Production:**` line is ever added, production-phrase findings switch from warning to error.
   - Both are existing behavior, but the claim's list of errors leaves out this conditional production error.
3. **Unchanged step behavior.** The roadmap step is still skipped when allowlist enforcement fails, and it still uses the runner's default `python` with no `setup-python`. Neither changes with this patch.

## Adequacy of the synthetic verification

- The five CLI cases correctly cover exit codes and annotation types: clean, error, warning-only, mixed, and legacy `--warn-only`.
- The count of 31 unit tests matches the supplied test file.
- Gaps:
  - Every case uses `--main main`; none uses the CI default ref resolution.
  - No CLI-level case covers the merged-branch error or the production/receipt paths.
  - Nothing runs against the real `ROADMAP.md` (see the gating condition).
- None of this shows GitHub enforcement. The receipt says so itself.

## Owner and scope

- **Consistent with the approval:**
  - The edit touches only one step.
  - It does not enable `--github` or `--receipts`.
  - It makes no changes to severity, branch protection, merge or deploy.
  - Claude keeps B4 ownership, with Codex preparing the change.
  - Applying waits for the claim to be registered on main.
- **Minor follow-up:** the docstring in `check_roadmap.py` ("first week in CI, Larry 10-02") and the test comment ("warn-only in CI for now") will be out of date. Updating them is a documentation-only change and would need its own scope approval.

## Review limits

- I read only the supplied files. Nothing was executed.
- I could not verify:
  - the current contents of `ROADMAP.md` on main or the candidate
  - the branch-protection settings
  - the registration status on main
  - the "no workflow lock" statement
  - the claimed SHAs and hashes
  - that the receipt was produced by the shown script
- This is not runtime, product or CI-enforcement acceptance.

</details>



## Remaining registration blocker

[AGENTS.md](../../AGENTS.md) and ROADMAP §0 require the matching owner/branch/scope
claim on main before code. This separate docs-only proposal is ready to review;
it is not yet merged. Only this isolated documentation registration has
conditional merge approval after final review/CI. Therefore applying
`.github/workflows/validate.yml` remains **pending main registration**, not denied
by an approval tool. Exact proposed delta and tests/review are complete above.

No original checkbox, other workstream row, runtime/config/test source or
workflow was changed. #247's frozen publication head remains unchanged.


## Independent registration isolation

The initial #249 head `83fc361` inherited #246/#247. Parent explicitly required
removing that inheritance before the narrow conditional merge approval could
apply. This revised registration is based directly on main `636880e`, with only
three documentation files. Original decision, proposed patch, synthetic results
and complete original Claude report above are retained. The claim is formalized
in the existing WS-20 Owner/Status/Where/Scope fields, naming
`codex/ws20-checker-enforcement-20261022` and preserving Claude cross-review.
No other row, checkbox, workflow, checker or test source is edited.
#246/#247 remain separate open drafts; their contents are neither lost nor merged.
Final isolated-diff review and exact-head CI are recorded in the PR description.


## After-merge branch-check correction

A final integration check found that listing the registration branch in the
claimed row’s `Where` field would make the checker report it as already merged
after #249 lands. `Where` now names only the active implementation branch; the
registration branch remains recorded in the decision/history above. A strict
check using the candidate as the main ref simulates the registration being
merged and passes. No checker logic or other row is changed.
