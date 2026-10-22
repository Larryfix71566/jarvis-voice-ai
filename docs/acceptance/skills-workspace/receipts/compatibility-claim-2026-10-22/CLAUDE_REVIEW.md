# WS-03 P0 Compatibility Claim Review: REVISE

## Verdict: **REVISE**

The claim is honest about sequencing. It is documentation-only, waits on landing on main, asserts no draft exception and advances no gate. The P0 design is not yet complete enough to implement against, for three reasons:

1. **The enforcement point is not fixed.** The injection path in the excerpts never reads catalog blockers. A refusal implemented as a catalog blocker would not stop injection.
2. **"Strict" and "content-safe" are not defined.** The current parser has concrete gaps that the claim does not name.
3. **The gate table overstates authority and scope.**

All fixes are small documentation edits. None needs a scope expansion.

**Scope of this review:** it covers excerpts only. Line ranges are partial, and no file hashes or tests were provided. It should not be recorded as a full-source review or as evidence for any gate.

---

## Findings (prioritized)

### F1 — HIGH: The injection seam ignores catalog blockers. Fail-closed must be enforced in `parse_skill`, not in readiness.

**Where**
- `jarvis/agents/base.py:1172-1177`. After `inspect_package`, the injection path checks only `catalog_entry.enabled`, the revision and the pin. It never consults `catalog_entry.blockers` or `readiness`.
- The existing `bundled_scripts_are_not_available` blocker (`skill_catalog.py:309-310`) already demonstrates this. The catalog reports "blocked" while `base.py` injects anyway (`agent_skills.py:159-163`).

**Why it matters**
- If P0 adds "unsupported control" as a `SkillCatalogEntry.blockers` code or a `skill_service` readiness reason, both legacy and V2 injection will still occur.
- The claim's "refusal … on both legacy and V2 admission paths" would then be false.
- The claim defers `agents/base.py`, but it does not say how enforcement is reached without editing it.

**Smallest safe fix (claim text)**
State that enforcement lives in `parse_skill`, backed by the pure `skill_compatibility.py`. This is the one choke point all paths share:

| Path | Where it calls `parse_skill` |
|---|---|
| `discover`, used by `load_skills` and legacy matching | `agent_skills.py:386` |
| `inspect_package` | `skill_catalog.py:296` |
| The `base.py` snapshot re-parse, every mode | `base.py:1157` |

A refused package returns `None`. `base.py` then already omits it, and returns `REFUSED` for explicit requests, through existing code. No `base.py` edit is needed.

To keep the specific reason visible:
- `inspect_package` should raise `SkillPackageError(<compat_code>)` instead of the generic `invalid_skill_instructions`.
- `list_catalog` (line 379) then surfaces that code.

Record two consequences as known SW-D gaps rather than fixing them in P0:
- `catalog_entry` is `None` on this path, so no `skill_selection_refused` trace is emitted (`base.py:1187`).
- The internal reason reads `skill_snapshot_changed_during_selection`.

**Test**
Add an `test_skill_injection_boundary.py` case:
- An enabled package that is correctly pinned in V2 mode, but declares an unsupported control.
- It must not be injected in either legacy or V2 mode.
- An explicit request for it must return `REFUSED`.
- An unrelated valid skill must still inject in the same run.

### F2 — HIGH: SKILL.md frontmatter parsing is not strict, and is inconsistent with the manifest parser.

**Where**
- `agent_skills.py:341` uses `yaml.safe_load`. Duplicate keys silently take the last value, so a second `description:` or control key wins. The manifest path rejects duplicates via `UniqueKeyLoader` (`skill_catalog.py:181-201`); SKILL.md does not.
- `agent_skills.py:291-292` coerces with `str()` before checking type. For example, `description: [a, b]` becomes the valid string `"['a', 'b']"`. `str()` on an alias-shaped nested structure is also an amplification risk.
- `agent_skills.py:326-327` reads the whole file with no byte cap. The manifest, by contrast, caps before reading (`skill_catalog.py:177`). Anchors and aliases are accepted. Whether `_package_digest` bounds size is not shown, so treat it as unverified.
- `validate_frontmatter` (lines 280-314) checks only `name` and `description`. Every other top-level key is ignored silently, which is exactly the "ignored control treated as supported" failure the claim prohibits.

**Smallest safe fix (claim text)**
Name the P0 strictness rules explicitly:
- Unique keys.
- No anchors, aliases or non-default tags.
- A byte cap before reading, plus a frontmatter cap.
- Type checks before any coercion. `name` and `description` must be `str`; `metadata` must be a mapping of bounded scalars.
- A **closed allowlist** of top-level keys, each classified as *descriptive* (kept) or *control* (unsupported, so the package is refused).
- Any key not on the allowlist is refused with `unknown_frontmatter_field`.

An unknown key cannot be shown to be descriptive, so "unknown controls are blocked" needs this explicit rule. Cite the source of the allowlist by commit (#246 @ `028b44e`), so the implementation has a fixed oracle.

### F3 — HIGH: Existing diagnostics echo input. "Content-safe" is undefined.

**Where**
- `agent_skills.py:329`, `f"unreadable: {exc}"`, includes the absolute path.
- `agent_skills.py:343`, `f"frontmatter is not valid YAML: {exc}"`. PyYAML's problem mark quotes the offending line with a caret, so frontmatter content leaks.
- `agent_skills.py:301` includes `{name!r}`.
- `skill_service.py:147,152` embed manifest-supplied `tool_name` in readiness reasons. The comment at line 188 calls these "safe for the UI." Credential names are pattern-checked (line 159); tool names are not, in this excerpt.

These strings reach `--validate` and anything else that consumes `parse_skill` problems.

**Smallest safe fix (claim text)**
Define compatibility diagnostics as a **closed reason-code vocabulary**:
- Codes, plus at most a field name taken from the allowlist, plus counts or lengths.
- Never values, paths, YAML snippets or exception text.

Existing free-text problems from `parse_skill` should be replaced by code-mapped sentences in P0, since this is within the claimed files. The `tool_name` echo in `skill_service` should either be validated against a slug pattern or reduced to a count. That is a compatibility-only change inside the claimed file.

**Test**
Plant a canary token in each of these places:
- `name`
- a key that is malformed YAML on a line
- an unknown key's value
- the package path segment, where the slug allows it
- `required_tools`

Then assert that the canary is absent from:
- `parse_skill` problems
- catalog blockers
- readiness reasons
- the `REFUSED` text
- captured logs

### F4 — MEDIUM: The disposition of `scripts/` and host controls is ambiguous, and could disable valid instruction skills.

**Where**
The three surfaces disagree today:
- `load_skills` admits packages that bundle scripts, with a warning (`agent_skills.py:437-439`).
- `as_prompt` injects them with an "unavailable" notice (lines 159-163).
- The catalog marks them blocked (`skill_catalog.py:309-310`).

**Why it matters**
The claim promises both "refusal of unsupported/unknown execution … controls" and "scripts/host controls" tests. An implementer could reasonably treat a `scripts/` directory as an execution control and refuse it. That would silently disable currently enabled instruction-only skills, which the claim says must be preserved.

**Smallest safe fix (claim text)**
State explicitly that P0 does **not** change admission for packages that merely contain `scripts/`. Current behaviour stays: inject as reference, no execution. P0 refuses only *declared* controls in frontmatter or manifest. Any change to scripts policy is a separate decision, made after the inventory.

Also specify the inventory itself:
- Read-only and offline.
- Records per-package top-level key *names* and `scripts/` presence only, never content.
- Completed and recorded before code changes.
- Any enabled package that P0 would newly refuse is reported to Larry before merge, not after.

### F5 — MEDIUM: The gate table's framing overstates its authority and the authorized work.

**Where:** the plan diff, under "Twelve-gate reconciliation (authoritative main 636880e)" and in the "Code / offline work" column.

**Problems**
- The heading calls the table "authoritative" while it sits on an unlanded draft branch. It is at most an inventory *as of* `636880e`.
- The offline-work column for SW-D, E, F, H, I and J lists work outside the P0 file scope: wrong-owner contracts, the authoring validator, recovery and idempotency tests, and accessibility contracts. Next to "authorizes only the named P0 source work," this reads as though that work is authorized.
- The SW-B and SW-C rows say "rerun … on changed source" but give no stop rule. If strict parsing changes a frozen positive or negative fixture, the risk is quietly narrowing an accepted gate.

**Smallest safe fix**
- Retitle the heading to "inventory as of main `636880e`."
- Add a sentence or column stating that only SW-A, SW-B, SW-C and the SW-E diagnostic canaries have P0 work. All other rows are inventory only and need separate claims.
- Add a stop rule: any change to an SW-B or SW-C frozen-fixture outcome blocks the P0 merge and is reported as a regression. It is never re-scoped or re-accepted inside this slice.

### F6 — MEDIUM: Overlap and scope edges are not closed.

**#242**
- Its package-count assertion in `test_agent_skills.py` will break if P0 refuses any repo package.
- **Fix:** make "no shipped package changes admission outcome" a P0 acceptance condition. If the inventory shows otherwise, coordinate with #242's owner before editing that file.

**V2 selector**
- `jarvis/skill_selection.py`, which provides `select_runtime_primary_skill` (`base.py:1095`), is not in the claimed scope, yet "V2 admission" is promised. Its sourcing was not provided for review.
- **Fix:** state that V2 enforcement is reached through `parse_skill` and the `base.py` re-parse (F1), so `skill_selection.py` is unedited. Any needed edit triggers the claim's existing "report larger scope" rule.
- `test_skill_selection.py` should assert that the outcome is consistent, but should not depend on the selector's internals.

**#246 contract**
- The contract is frozen and unmerged, so it is not a stable normative reference.
- **Fix:** pin it by commit hash (`028b44e`) in the plan, and state that P0's allowlist and code set are implementation decisions checked against it, not a rewrite of it.

**Review evidence**
- The plan asks reviews to preserve input and source hashes. This review received excerpts without hashes. Record it as partial and advisory.

---

## Minimal first patch/test sequence (after the revised claim lands)

1. **Documentation revision on this branch, before landing:** apply F1 (enforcement point), F2 (allowlist rule and its source), F3 (code vocabulary), F4 (scripts unchanged), F5 (heading, P0-only rows, stop rule) and F6 (`skill_selection.py` and #242 conditions).
2. **Offline inventory (read-only):** for each enabled package, record top-level key names, manifest key names and `scripts/` presence. Report any package P0 would newly refuse. Stop if any is found.
3. **Red tests first,** in the new `tests/unit/test_skill_compatibility.py` with synthetic fixtures:
   - Duplicate key, alias or anchor, non-default tag, oversize file and oversize frontmatter.
   - Type-invalid `name`, `description` and `metadata`.
   - Unknown key, and a declared unsupported control.
   - An allowlisted descriptive key retained, and a valid instruction-only package left byte-identical.
   - The canary privacy set from F3.
4. **Pure `jarvis/skill_compatibility.py`:**
   - A strict loader: unique keys, no aliases or tags, caps.
   - The allowlist with descriptive or control classes.
   - The closed code set.
   - No I/O beyond the bytes it is given.
5. **Wire `parse_skill`:**
   - Cap before read, then call the compatibility module.
   - Refuse with codes, and replace the value-echoing problem strings.
   - Keep the soft body-length warning.
6. **Wire `inspect_package`:**
   - Raise `SkillPackageError(compat_code)` instead of the generic code.
   - Apply the `skill_service` tool-name redaction or validation.
7. **Consistency and boundary tests:**
   - Legacy `load_skills`, `list_catalog` and `inspect_package` produce the same outcome for each fixture.
   - The F1 injection-boundary case, in both legacy and V2 flag states.
   - Isolation: one invalid package beside valid ones.
8. **Regression rerun:** run the SW-B integrity contracts, the SW-C frozen positives and negatives, and #242's count assertion. Report any difference as a blocker under the F5 stop rule. Change no gate status.

Implementation, test results, this review, merge, deployment and acceptance remain separate records. None is implied by the steps above.
