# WS-03 claim correction review (post-`7f34dde` correction)

**Verdict: APPROVE.** All six findings from the `7f34dde` review are closed in the supplied text. I found no material contradiction that would block implementing the bounded P0 slice. The non-blocking notes below can go into the implementation record, or into a later documentation touch-up, without another claim review.

Scope: this covers only the supplied excerpts. `jarvis/skill_service.py`, `jarvis/agents/base.py`, `jarvis/skill_selection.py`, `tests/unit/test_skill_selection.py`, the #246 contract and the third-review input were not supplied. Hash values are the author's assertion; I did not recompute them. This review is not acceptance evidence and grants no merge permission beyond the parent's stated docs-only authorization.

## Closure of the `7f34dde` findings

| Finding | Status | Where it is closed |
|---|---|---|
| **F1** Parser vs. catalog script reads | **Closed** | Plan P0 script bullet: "The parser checks only entries… The existing catalog integrity digest may still traverse and hash package bytes… Keep existing integrity reason precedence, such as `symlink_in_package`." The matrix row matches. This agrees with `skill_catalog._package_digest`, which runs before `parse_skill` in `inspect_package`. No reordering is implied. |
| **F2** Disclosure and stop-rule scope | **Closed** | Plan bullet "These are the two known admission changes, not an exhaustive list… List any other changed assertion by test ID… including catalog script blockers, diagnostic text or CLI output." The frozen-fixture stop rule is kept. |
| **F3** Case-sensitivity | **Closed** | "listing package-root entries without following links, matching `entry.name.casefold() == "scripts"`". Any entry type refuses. |
| **F4** Null values and authoring writer | **Closed** | Matrix: present null refuses for `metadata` and each subkey. Below the matrix: `write_skill`/`skill_from_procedure` must use type-safe serialization or refuse. Empty agent is serialized as a quoted string. Round-trip tests cover `yes` and `2026-10-22`. `top-level-type-inventory.json` confirms six string name/description pairs. |
| **F5** CLI sinks | **Closed** | Diagnostics bullet now covers "compatibility failure output in CLI `--validate`/`--list`/`--explain` with canaries" and forbids directory names and paths in invalid-package labels. |
| **F6** Docstring overclaim | **Closed** | "Update the module docstring to describe this instruction-only subset; no drop-in community compatibility claim may remain." |

The prior non-blocking notes are also addressed:
- **Missing evidence files:** both `review-input.json` files and the original `CLAUDE_REVIEW.md` are now in the manifest, with author-run decode verification.
- **Dispositions wording:** the F5 disposition now says "stops implementation for coordination".
- **Creator follow-up:** the plan explicitly defers creator draft compatibility to SW-F.

## Non-blocking notes (priority order)

1. **CLI label rule vs. existing inventory identity.** *Low; implementation clarity.*
   - **Location:** plan diagnostics bullet ("must not echo directory names or paths"); `agent_skills.main --validate`; `skill_catalog.validate_skill_inventory`; `list_catalog`.
   - **Issue:** `--validate` prints `validate_skill_inventory` lines formatted as `f"{entry.skill_id}: {reason}"`. For invalid packages, `skill_id` is the slug directory name, and `list_catalog` uses it as the invalid entry's identity. Its dedupe also keys on `path.parent.name` and `invalid_skill_instructions`.
   - **Why it is not blocking:** the rule can be met in the claimed files, for example with ordinal labels in the CLI output.
   - **Smallest fix:** in the implementation record, state which label `--validate` uses for compatibility failures. Also confirm that the catalog API's slug-validated `skill_id` for invalid entries is unchanged; it is a non-CLI sink. List the dedupe change by test ID if any assertion moves.

2. **Third-review input hash not cross-verified.** *Low; evidence.*
   - **Location:** the "Author-run integrity verification" block covers only the first two inputs. `rereview-7f34dde/review-receipt.json` records `input_sha256 c973b3…` for `corrected-claim-review/review-input.json` (file hash `a5bb40…`).
   - **Smallest fix:** add a third entry with `decoded_input_sha256` and `matches_receipt` in the next receipt update.

3. **"No merge authorization" wording.** *Low; wording.*
   - **Location:** the ROADMAP claim boundary ("No merge or deployment authorization is conveyed by this dispatch") reads differently from the log and dispositions ("Larry approved documentation-only claim merge after final review/CI").
   - **Why it is not blocking:** the two can be reconciled, since one is the original dispatch and the other a later approval.
   - **Smallest fix:** change the sentence to "No feature-code merge or deployment authorization is conveyed; documentation-only claim merge was separately approved after final review/CI."

4. **Partial write on refusal.** *Low; implementation.*
   - **Location:** `write_skill` calls `folder.mkdir(...)` before `path.write_text(...)`.
   - **Issue:** "refuse before writing" should also mean refusing before the directory is created. Otherwise a refused candidate leaves an empty package folder, which `discover` ignores but which is still debris.
   - **Smallest fix:** validate and serialize fully before `mkdir`, and assert in the round-trip refusal test that no folder exists afterward.

5. **Scope of "unsupported tool names" in readiness reasons.** *Low; clarity.*
   - **Location:** diagnostics bullet; `test_skill_service.py` asserts `required_tool_not_configured:repo_read_file` and `required_credential_missing:SAMPLE_API_KEY`.
   - **Issue:** these existing reason codes come from manifest declarations. The new rule should read as applying to frontmatter-declared controls. Blocked frontmatter never reaches `evaluate_readiness`, because `inspect_package` raises first.
   - **Smallest fix:** in the implementation record, state that existing manifest-declared reason codes are unchanged.

## Contradiction check

No blocking contradiction found:
- The enforcement seam (`parse_skill` → `None`) reaches all three paths:
  - legacy `load_skills`/`discover`;
  - V2 `inspect_package`, which runs after the digest;
  - the final re-parse, which is the existing seam and is not edited.
- Closed field matrix vs. inventory: metadata and top-level types match both inventory files. `skill-creator`'s `{}` is covered by "absence/empty mapping accepted".
- Strict YAML: the existing `UniqueKeyLoader` pattern in `read_skill_registry` and `_manifest` gives a reuse path within the claimed files.
- The two disclosed test changes match the supplied `tests/unit/test_agent_skills.py`.
- `TestPromptRendering.test_bundled_scripts_are_declared_unavailable` constructs `Skill` directly and is unaffected.
- `TestShippedSkills` and the five-package pin test stay valid under the no-scripts inventory.

Source edits still wait for the claim to land on main. Exact-head CI on the corrected head is still required, per the parent's conditions.
