# WS-03 corrected claim review

**Verdict: REVISE.** Six documentation-only text defects remain. None requires implementation, live evidence or a scope expansion. This review covers only the supplied excerpts. It is not a full-source review, gate evidence or merge authorization.

## Closure of the second review (9413b5e)

| Item | Status | Basis |
|---|---|---|
| B1: unenforceable script rule | **Closed in policy, two wording gaps** | The new-versus-existing split and "required/unresolved" wording are gone. Refusal is deterministic, covers empty directories, files and symlinks, and uses the `parse_skill` seam. Out-of-repository inventory before rollout is stated. Gaps: F1 and F3 below. |
| B2: unknown-field escape clause | **Closed, one gap** | The field/type matrix is closed. Additions need a reviewed amendment. Metadata types match `metadata-type-inventory.json`. Gap: F4 below. |
| B3: receipt evidence | **Closed in substance** | `source-manifest.json` hashes for `agent_skills.py`, `skill_catalog.py` and `base.py`, plus the rereview `skill_selection.py` hash, match the current manifest. This is consistent with no source edits. I cannot verify the input SHA-256 values, and neither `review-input.json` file appears in the current manifest (see the evidence note). |
| Nit: bde22bb pointer | **Closed** | The ROADMAP Status line and receipt link are restored. |
| Log "not re-reviewed" line | **Closed** | |

Requested checks:
- **Text/reference preservation:** correct. The Markdown and manifest-reference rows keep existing containment, and `references/` is not a trigger.
- **Partial-compatibility honesty in the plan:** good. The residual issue is in source (F6).
- **Two-test disclosure:** present, but its scope is incomplete (F2).

## Material findings, by priority

### F1 (High): "No traversal or script-content read" is false for the catalog, V2 and injection paths

**Where:**
- Plan matrix, row "`scripts` entry at package root": "no traversal or script-content read".
- P0 script bullet: "without following links or opening/executing script contents".

**Problem:**
- `skill_catalog.inspect_package` calls `_package_digest(directory)` before `parse_skill`.
- `_package_digest` uses `os.walk` into `scripts/` and calls `path.read_bytes()` on every file.
- It also raises `symlink_in_package` before any compatibility code for a symlinked `scripts`.
- `base.py:1147` and the V2 snapshot both call `inspect_package` first.

As written, the contract either forces an unplanned reorder of `inspect_package` or asserts something the code will not do.

**Smallest fix:** replace the row text with:

> `parse_skill` checks only the package-root entry (no link following, traversal or content read). The existing catalog integrity digest may still traverse and hash package bytes, including script files. It never executes, decodes, injects or displays them. Existing reason precedence (e.g. `symlink_in_package`) is retained.

Alternatively, commit to running the compatibility check in `inspect_package` before `_package_digest` and disclose the change in reason precedence.

### F2 (Medium): The disclosure and stop rule cover too little

**Where:** P0 bullet "Two known tests … intentionally need changed expectations… Any additional changed frozen fixture outcome stops…"

**Problem:**
- Refusal in `parse_skill` makes two existing behaviors unreachable through parsing:
  - the catalog blocker `bundled_scripts_are_not_available` (`inspect_package`);
  - the scripts header in `Skill.as_prompt`.
- Closed diagnostics will change free-text problems. `validate_frontmatter` echoes `name!r`, and `parse_skill` echoes `{exc}`.
- Tests in `test_skill_catalog.py`, `test_skill_service.py` and the injection-boundary module were not supplied and may assert these.
- The stop rule covers only frozen fixtures, not ordinary changed assertions.

**Smallest fix:** append:

> These are the two known admission-outcome changes in the supplied tests. Any other changed assertion in any test file (including `bundled_scripts_are_not_available`, diagnostic text or CLI output) is listed by test ID in the implementation PR before it is modified. A changed SW-B/C frozen fixture outcome stops work for coordination.

### F3 (Medium): Script-entry matching is not deterministic across filesystems

**Where:** script bullet and matrix row.

**Problem:**
- On case-insensitive APFS, a by-name lookup of `scripts` matches `Scripts/`. On a case-sensitive volume it does not.
- `_package_digest` already case-folds package paths, so the two checks would disagree.

**Smallest fix:** add:

> Detect by listing package-root entries without following links. Match the name case-insensitively (`casefold() == "scripts"`). Any entry type refuses.

### F4 (Medium): The matrix leaves present-null values unspecified, and the in-scope authoring writer can emit refused packages

**Where:** matrix rows `metadata.agent…` and `metadata.promoted_*`, and the absence of any authoring rule.

**Problem:**
- `skill_from_procedure` writes `agent: ` (YAML null) when the agent value is empty.
- `write_skill` serializes arbitrary metadata keys and unquoted values (`f"  {k}: {v}"`, `f"description: {description}"`). Under "no scalar coercion", a description such as `yes` or `2026-10-22` becomes a non-string.
- Both functions are in the claimed `agent_skills.py`.
- Top-level `name`/`description` types are not in the type inventory, which covers metadata only.

**Smallest fix:** add below the matrix:

> Present null for an optional metadata subkey refuses. `write_skill` and `skill_from_procedure` emit only matrix fields using type-safe YAML serialization, or refuse before writing. Round-trip tests cover an empty agent and YAML-ambiguous descriptions. Before coding, confirm that the six packages' `name` and `description` are YAML strings, under the stop rule.

Treating null as absent is also acceptable if stated. Choose one.

### F5 (Low–Medium): CLI output is missing from the diagnostic sinks

**Where:** diagnostics bullet, "Cover parser/catalog/readiness/refusal/log sinks".

**Problem:**
- `--validate` prints `INVALID {path}` and raw problems.
- `--list` and `--explain` print `path.parent.name`, which is not slug-checked in `discover`, along with problems.
- The second review named `--validate` explicitly.

**Smallest fix:** add "CLI `--validate`/`--list`/`--explain` output" to the sink list. Alternatively, state that printing local operator paths in the CLI is unchanged and outside P0, while compatibility reason text there still uses closed codes.

### F6 (Low): The source docstring will overstate compatibility after P0

**Where:** `jarvis/agent_skills.py` module docstring:
- "a community skill can be dropped in unchanged"
- "A bundled `scripts/` directory is detected and reported loudly… never invoked"

**Problem:** after P0, portable optional fields such as `license`, and any `scripts` entry, cause refusal.

**Smallest fix:** add one plan line:

> Update the `agent_skills.py` module docstring to describe the P0 instruction-only subset; no drop-in community compatibility is claimed.

## Non-blocking notes

- **Evidence:** the current manifest omits the original `CLAUDE_REVIEW.md` and both `review-input.json` files. I did not verify the stated input SHA-256 values (`03a4b6…`, `e351f4…`) or their decode equivalence. "Decoded input and source hashes verify" remains an author assertion. Add those file hashes to the next packet manifest.
- **Wording mismatch:** `dispositions.md` F5 says a fixture change "blocks merge"; the plan says it "stops implementation". Align the dispositions to the plan.
- **Unverified creator alignment:** if the creator's authoring validator can produce `scripts/` drafts, the drafts will now be unadmittable. That source was not supplied. Note it for the SW-F follow-up if confirmed.

Once F1–F6 are applied, I expect the claim to be approvable without further scope change. Source edits still wait for the claim to land on main. No merge permission is implied.
