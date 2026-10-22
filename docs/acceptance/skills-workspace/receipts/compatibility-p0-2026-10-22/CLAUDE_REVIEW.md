# WS-03 P0 independent review: commit `4699a54`, base `edfa285`

## Verdict: REVISE (minor)

I found no Critical or High defect. Statically, the core admission logic meets the approved matrix:

- bounded reads
- event pre-scan before construction
- closed field and type validation
- casefolded root `scripts` refusal before any content read
- fixed reason codes
- writer validation before directory creation
- parser refusal reused at the final injection re-parse

Four Medium items should be fixed before the draft is called review-complete. Each is a small test or evidence addition.

**Basis.** This is static review of the supplied source only. I ran no tests and reproduced no hashes. The 36/4 baseline and 232-pass results are author-run evidence that I did not verify.

## What static review confirms

| Area | Finding |
|---|---|
| YAML bounds | The frontmatter byte cap applies to raw bytes before decoding (`parse_skill`, new ~L310–321). The string cap is re-applied in `load_frontmatter` (`skill_compatibility.py` L57). `yaml.parse` scans events before `yaml.load` builds anything (L61–74). Aliases, anchors and explicit tags (including `!`) refuse before the composer runs, so alias expansion cannot occur. Depth and count limits stop the scan early; the PyYAML parser keeps an explicit state stack rather than recursing. |
| No ignored semantics | `_StrictLoader.construct_mapping` (L43–52) requires keys tagged as strings. This rejects `<<` merge keys, `yes` and null keys, and complex keys; `flatten_mapping` is never called. It also rejects duplicates at every level. `validate_frontmatter` has a closed top-level set and closed metadata set. It does not coerce types, and `type(x) is int` correctly excludes booleans. |
| Script refusal | `os.scandir` checks only entry names, and the refusal returns before `os.open` (~L287–293). Directories, files, symlinks and FIFOs named `scripts` all refuse without being opened. The catalog digest runs first, so `symlink_in_package` and `unsafe_package_file` keep precedence. |
| Special files | `O_NOFOLLOW | O_NONBLOCK` is followed by an `fstat` check for a regular file. FIFOs do not block, and symlinks at the file itself fail. A symlinked package directory is refused. |
| Diagnostic privacy | Every `parse_skill` return is a fixed code. `compatibility_reason` filters through `REASONS`. The loader logs counts only. `--list`, `--explain` and `--validate` show ordinals for invalid packages. Frontmatter `allowed-tools` never reaches `required_tools`, so readiness reasons cannot echo it. |
| Final injection | `base.py` re-parses at selection time and at the final boundary, and both treat `None` as refusal. The new test changes the package only on the third `inspect_package` call while returning an unchanged revision, so the parser alone produces the refusal. |
| Writer | `safe_dump` indents multi-line continuations by two spaces, so a bare `---` cannot appear inside frontmatter. Validation, serialization and the size check all finish before `mkdir`. `open("x")` also refuses a dangling symlink. |

## Findings

### M1 (Medium, evidence): final-injection test lacks an asyncio marker

- **Where:** `tests/unit/test_skill_injection_boundary.py`, new test (~L71–73).
- **Problem:** The existing sibling test in the same file carries `@pytest.mark.asyncio`; the new one does not.
  - Under strict asyncio mode, pytest before 8.4 skips an unmarked async test, and 8.4 and later fail it.
  - The 232 dots are consistent with execution only if the repo runs in auto mode, which I cannot see.
  - This test is the only evidence for the final-injection focus area.
- **Fix:**
  - Add `@pytest.mark.asyncio`.
  - Attach `-rA` or `-v` output listing all six `test_compatibility_drift_refuses_at_final_injection_boundary[...]` IDs as PASSED.

### M2 (Medium, evidence): most numerical bounds have no boundary tests

- **What is covered:** inclusive 128 KiB file and 16 KiB frontmatter limits, depth 1000, and a 1025-character metadata string.
- **What is not covered:**
  - `MAX_ROOT_ENTRIES` at 256 accepted and 257 refused
  - `MAX_YAML_EVENTS` at 128 and 129
  - `MAX_YAML_DEPTH` at the exact 4 and 5 boundary
  - a metadata string of exactly 1024 characters accepted
  - proof that oversized frontmatter refuses before YAML is invoked
- **Fix:** Add parametrized boundary tests. For the oversized-frontmatter case, monkeypatch `yaml.parse` to call `pytest.fail` and assert `frontmatter_too_large`.

### M3 (Medium, evidence): unsupported and malformed codes are not asserted exactly

- **Where:** `test_skill_compatibility.py`
  - `test_unsupported_or_malformed_frontmatter_refuses_without_content`
  - `test_invalid_encoding_or_resource_limit_refuses` (~L79)
  - `test_yaml_shape_and_metadata_resource_refusals_are_safe`
- **Problem:** The contract says codes "must distinguish unsupported from malformed." These tests assert only that `problems` is non-empty.
  - The `b"\xff"` case actually returns `frontmatter_missing`, because the byte scan runs before decoding. As a result, `skill_encoding_invalid` is never exercised.
- **Fix:**
  - Assert exact codes, for example:
    - `disable-model-invocation` and `allowed-tools` → `unsupported_frontmatter_fields`
    - duplicate key → `frontmatter_duplicate_key`
    - anchor or tag → `frontmatter_yaml_features_unsupported`
  - Add a case like `b"---\nname: sample-skill\ndescription: \xff\n---\nb"` that asserts `["skill_encoding_invalid"]`.

### M4 (Medium, regression evidence): public API changes have no caller inventory

Three things changed for callers outside the claimed module:

- `validate_frontmatter` now returns codes instead of sentences and rejects every key outside the closed set.
- `FileExistsError` now carries `skill_already_exists` instead of the path.
- The catalog blocker `bundled_scripts_are_not_available` can no longer be produced.

Callers outside the diff, such as the creator, sandbox drafting validation or `skill_selection`, are not supplied. The plan requires listing every changed assertion, including catalog script blockers.

- **Fix:** Record grep evidence of every caller and test reference for these three, and confirm no assertion changed beyond the two disclosed ones.

### L1 (Low): writer does not prove a full round trip

- **Where:** `write_skill` (~L490–496).
- **Problem:** It re-runs `load_frontmatter(front)` but never checks that the parsed result equals `data`. It also never splits the full `content` the way `parse_skill` does.
  - Today this is safe only because of how PyYAML's emitter behaves.
- **Fix:** Before `mkdir`, add:
  - `if _parsed != data: raise ValueError(...)`
  - `if _split_frontmatter(content)[0] != front: raise ValueError(...)`

### L2 (Low): writer write is not atomic, and a race leaks the path

- **Problems:**
  - An I/O error after `open("x")` leaves a partial `SKILL.md`.
  - If `mkdir` succeeds and `open` then fails, an empty folder is left behind.
  - If a race triggers `FileExistsError` inside `open("x")`, the error carries the path, and the CLI prints `refused: {exc}`.
- **Fix:**
  - Write to an `O_EXCL` temp file in the folder, then `os.link` or rename without replacing.
  - Map `FileExistsError` to `skill_already_exists`.

### L3 (Low): lazy `Skill.body()` bypasses the hardened reader

- **Where:** `Skill.body()`.
- **Problem:** When `_body is None`, it calls `path.read_text`, which is unbounded, follows symlinks and can block on a FIFO.
  - `parse_skill` always sets `_body`, so this is reachable only through other constructors.
- **Fix:** Route through the bounded reader, or raise when `_body is None`.

### L4 (Low): `--validate` misattributes a registry error to a package named `registry`

- **Where:** `main` `--validate` (~L777–792).
- **Problem:** `error.partition(":")[0]` matches the message `registry: invalid or unavailable` to a package directory named `registry` that has invalid frontmatter.
  - The output then shows `INVALID package-N: invalid or unavailable`, and the registry line disappears.
  - The exit code is still 1.
- **Fix:** Handle registry issues before the per-package merge.

### L5 (Low, portability): missing open flags escape as `AttributeError`

- **Where:** `parse_skill`.
- **Problem:** `os.O_NOFOLLOW` and `os.O_NONBLOCK` do not exist on Windows. The resulting `AttributeError` escapes the "never raises" contract.
- **Fix:** If either flag is missing, return `skill_unreadable` (fail closed).

### L6 (Info): byte and string delimiter scans can disagree

- **Problem:** `bytes.splitlines` and `str.splitlines` treat `\u2028`, `\x85`, `\x0b`, `\x0c` and `\x1c`–`\x1e` differently.
  - A closing delimiter preceded only by one of these is now refused as `frontmatter_missing`, where the base parsed it.
  - This fails closed and the content is exotic.
- **Fix:** Disclose it, or make the two scans consistent.

### L7 (Info): dead script-handling code

- **Problem:** Several `has_scripts` paths can no longer trigger:
  - the `as_prompt` header
  - the `skill_bundles_scripts` log
  - the `format_inventory` line
  - the catalog blocker
  - `test_none_of_them_bundle_scripts` is now weaker as a result.
- **Fix:** Follow-up cleanup.

### L8 (Trivial)

- If `os.fdopen` fails, the file descriptor leaks.
- `MAX_SKILL_BYTES` duplicates the catalog's `MAX_TEXT_FILE_BYTES`. Import one from the other.
- The log has a typo: "remain2/12".

## Numerical limits: compatibility and bypass

| Bound | Assessment |
|---|---|
| 128 KiB file (inclusive) | Equals the catalog `.md` cap, so no V2 regression. It newly bounds the legacy loader, which was previously unbounded; this is disclosed. Bytes are read capped at limit+1 after `fstat`. No bypass found. |
| 16 KiB frontmatter (inclusive, before YAML) | Enforced on raw bytes and again on the string. A matrix-valid payload of maximum-length strings made of 4-byte characters (1024 description + 3×1024 metadata characters) can exceed 16 KiB. The writer catches this through `load_frontmatter`, so nothing is written partially. This is acceptable but should be documented. |
| 128 events | A maximal matrix frontmatter uses about 24 events, leaving ample headroom. The check runs before construction. |
| Depth 4 | The matrix needs 2. Validated by scan before the recursive composer runs. |
| Metadata strings 1024 | Matches the description limit. The 1025 case is tested; the 1024 case is not (see M2). |
| 256 root entries | Above the catalog's 128-file recursive cap. The legacy path was previously unbounded. Ordering can return `package_entry_limit` instead of `unsupported_scripts_entry`, but both refuse. |

## Out of scope (unchanged limitations)

These remain outside P0 as stated in the claim:

- import UI and activation
- the script sandbox
- trace-event loss on refusal
- generic runtime refusal text
- comparison with #242
- creator and VM adapter compatibility (SW-F)

## Path to APPROVE

1. Resolve M1–M4.
2. Re-run the focused suites and attach the per-test output from M1.
3. L1–L5 may be fixed now or tracked as follow-ups.
