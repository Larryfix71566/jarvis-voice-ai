# WS-03 corrected claim re-review (commit `9413b5e`, base `636880e`)

## Verdict: **REVISE**

The claim is close. Sequencing is honest: main-first, no draft exception, no merge or deploy authority, and SW-B/C stay at 2/12. The enforcement seam is now correct and can be enforced inside the claimed files.

Three small text defects remain. None needs scope expansion, implementation work or live tests. This review covers only the supplied excerpts and files. It is not full-source review or gate evidence.

## Closure of prior findings

| # | Disposition | Status | Basis |
|---|---|---|---|
| F1 enforcement seam | Adopted, with nuance | **Closed** | See F1 notes below. |
| F2 strictness | Adopted | **Mostly closed** | Unique keys, byte caps before read and before YAML, no anchors, aliases or tags, and type checks before coercion are all stated. Treating #246 as a design reference rather than an executable oracle is reasonable. **Residual:** the escape clause on unknown fields (Blocker 2). |
| F3 diagnostics | Adopted | **Closed** | A closed vocabulary, trusted labels and counts only, and no keys, values, paths, snippets or exception text. Sinks include parser, catalog, readiness, refusal and logs. Tool-name leakage through readiness is named. |
| F4 scripts | Partially adopted; warning-only admission rejected | **Policy accepted; wording open** | The rejection is a user-level policy call. I take the no-silent-omission contract as given by the parent; its text was not supplied. The inventory supports zero impact on repository packages: six packages, five enabled, `scripts_present: false` for all. The rule as written is still not enforceable (Blocker 1). |
| F5 gate framing | Adopted | **Closed** | See F5 notes below. |
| F6 boundaries | Adopted | **Closed, one evidence gap** | #242 is preserved, #246 is pinned at `028b44e`, selector and `base.py` are unedited, and the review is labelled advisory. **Residual:** the hash-manifest assertion is not supported by the supplied files (Blocker 3). |

**F1 notes**
- Refusal happens in `parse_skill`, which returns `None`.
- Each consuming path then rejects the package:
  - `discover`/`load_skills` skip it (`agent_skills.py:416-418`).
  - `inspect_package` raises (`skill_catalog.py:296-298`).
  - `base.py` rejects it twice: once in `inspect_package` at `:1147` and once in the re-parse at `:1157-1163`, which the `:1178` handler then omits or `REFUSED`.
- The nuance in the disposition is accurate:
  - `select_primary_skill` refuses any entry with blockers (`skill_selection.py:362`).
  - `base.py:1172-1177` checks only enabled state, revision and pin.
  - The final loop after `:1239` was not supplied. The claim correctly says only that the final loop re-parses, not that it inspects blockers.
- The SW-D trace and generic-refusal gaps are recorded honestly.
- The isolation clarification (no secret substitution on an explicit refusal) matches `:1181-1186`.

**F5 notes**
- The table is retitled "as of main `636880e`".
- Only SW-A/B/C regression work and the SW-E canaries are P0.
- The stop rule for frozen fixtures is present.
- Minor nit: the ROADMAP Status line no longer records the `bde22bb` build identity for the Versions subcheck. "Remain unchanged" has no pointer. Restore a one-clause reference.

## Material remaining blockers (claim defects)

### 1. The script-dependency rule is not enforceable as worded

**Where:** plan, P0 contract, inventory bullet ("Reject **new** packages with required or unresolved script dependencies…").

**Problem**
- `parse_skill`, `inspect_package` and `load_skills` have no new-versus-existing distinction. `has_scripts` is a package property (`agent_skills.py:360`).
- "Required or unresolved script dependency" has no defined field. The only observable signal is a `scripts/` directory. The next sentence makes that directory sufficient for refusal anyway.
- The inventory is `read_only_repository_inventory` only. It cannot prove that no non-repository package on a host is affected.
- If refusal lands in `parse_skill` (the F1 seam), a scripts package changes from catalog `installed` + `bundled_scripts_are_not_available` to `invalid`. Legacy loader admission is also removed. If any frozen SW-B/C fixture covers a scripts package, the stop rule will block merge mid-slice instead of before it.

**Smallest fix:** replace the sentence with:

> P0 refuses any package containing `scripts/` (or a declared script dependency) on all paths via `parse_skill`. The repository inventory at `636880e` shows no affected package. Before coding, check the SW-B/C frozen fixtures for scripts cases. Any expected-outcome change there is reported to Larry for decision before implementation, not discovered at merge. Packages outside the repository are not covered by this inventory and must be inventoried before any rollout.

### 2. The unknown-field escape clause reopens the silent-acceptance gap

**Where:** plan, strictness bullet: "Unknown fields are blocked unless their recognized descriptive semantics are established."

**Problem:** this leaves the implementer to decide, at implementation time, which unknown keys count as descriptive. That is the F2 failure in a new form.

**Smallest fix:**
- Fix the P0 allowlist in the claim from the inventory:
  - Frontmatter: `name`, `description`, `metadata`.
  - `metadata` subkeys: `agent`, `source`, `promoted_successes`, `promoted_failures`, `concept_from`.
- Say that any addition needs a reviewed plan amendment.
- Note that metadata value types are not inventoried. "Scalar" schemas must be confirmed against existing packages, and a mismatch triggers the stop rule.

### 3. A receipt assertion lacks supplied evidence

**Where:** `dispositions.md` F6 says source hashes were "captured externally… receipt links the exact input to that manifest". The plan's task split requires preserving exact input and source hashes.

**Problem:** the supplied receipt set has only `CLAUDE_REVIEW.md`, `dispositions.md` and `package-inventory.json`. No hash manifest was supplied, so I cannot confirm the link.

**Smallest fix:** either
- add the input/source hash manifest to the receipt directory and reference it by path, or
- reword the disposition to state that hashes are not preserved in-repo.

Also update the log's "not independently re-reviewed" line if this review is recorded.

## Implementation test requirements (not claim defects)

These belong to the post-landing slice. They should not block this docs merge.

- An injection-boundary case in both flag states: enabled, pinned, refused package → omitted. An explicit request → `REFUSED`. An unrelated valid package still injects. Confirm against the full final loop after `base.py:1239`, which was not supplied.
- Map `parse_skill` refusal to a closed `SkillPackageError` code in `inspect_package`, and surface it through `list_catalog:379`.
- Manifest-declared controls: confirm whether `_manifest` rejects unknown keys. `inspect_package` runs on every injection in both modes (`base.py:1147`), so that seam reaches the legacy path too.
- Canary absence across all named sinks, including `--validate` output and the `skill_service` readiness reasons.
- Byte-identical outcome for all six inventoried packages, #242's count assertion, and the SW-B/C frozen reruns under the stop rule.
- Existing free-text problem assertions in `test_agent_skills.py` will change. These are in claimed files, so they need review rather than silent fixture adjustment.

## Scope enforceability

With Blockers 1 and 2 worded as above, P0 can be enforced entirely within the claimed files:
- `agent_skills.py`
- `skill_catalog.py`
- `skill_service.py`
- the new `skill_compatibility.py`
- the named tests

No change to `base.py` or `skill_selection.py` is needed. The claim's "stop and coordinate" rule covers any seam that turns out to be insufficient.

Nothing here authorizes merge, runtime edits before landing, deployment, benchmarks or permission changes.
