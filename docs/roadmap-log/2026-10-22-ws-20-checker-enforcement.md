---
date: 2026-10-22
system: codex
rows: [WS-20]
prs: []
---

# Approved checker enforcement: bounded implementation candidate

Main registration prerequisite is satisfied by #249 merge
`7b295cd92dfd331d49c08b723f622491e13f4dfa`, verified before edits.
This candidate contains the previously reviewed workflow delta: remove
`--warn-only`, rename the step and explain errors-fail/warnings-advisory.
No checker algorithm or severity changes. Existing B4 attribution and Claude
cross-review remain; no other owner or acceptance checkbox is changed.

## Verification

The 36 focused checker tests pass, including five new subprocess cases with
GitHub annotations and the default origin/main ref. Clean exits 0; an error
exits 1; warning-only exits 0; mixed exits 1; legacy warn-only errors exit 0 with
warning annotations. No live provider, runtime/service or installed-artifact
action is used. Strict real-roadmap check and diff preservation checks are
recorded in the PR with the frozen source. Final Claude review and publication
CI must match that candidate; no earlier receipt substitutes for them.

Changed implementation-file SHA-256 values:

- `.github/workflows/validate.yml`: `253990cc4a6ea507c8b59f1fd9ac91221efd1057151ba887313d2c1b89f45399`
- `tests/unit/test_check_roadmap.py`: `6461b5f883cdfb6f4473b8cbbd76fa58ce6e8fa3d4a3a0698837b92c1c3247c2`

## Boundaries

The CI job retains its current permissions, triggers, dependencies and action
pins. Optional GitHub PR-age and local receipt checks remain disabled.
Branch protection is untouched. The script’s historical first-week docstring
is outside the registered source scope and remains unchanged; the dated policy
and actual workflow command are authoritative for this candidate.

This is a separate draft implementation, not covered by the documentation-only
merge authorization. Larry retains the implementation-merge decision.
No product/live acceptance, #243 merge, installation or deployment is authorized
by these checks. Both WS-20 milestone checkboxes remain unchanged.


## Independent review disposition

The exact implementation at `4a15fd9` received an official Claude Max review
with no code blockers. The reviewer confirmed strict exit/annotation semantics,
all five CLI cases and unchanged checker severities. The roadmap status,
remaining-work and next-step fields were corrected to their after-merge state,
with actual pending merge authority retained in the PR and dated log. Missing
spaces in the exit-code prose were corrected. Workflow and test bytes are
unchanged; their hashes above still identify the reviewed implementation.

The tests invoke default ref resolution but do not independently prove ref
precedence when origin/main and main point to the same fixture commit. Checker source (`resolve_main` prefers `origin/main`) establishes precedence;
the full-history checkout makes that ref available;
no broader precedence-test claim is made. Repository-wide errors can fail
unrelated PRs; owners must correct their own stale rows. This is the approved
policy, not a new severity or branch-protection rule.
