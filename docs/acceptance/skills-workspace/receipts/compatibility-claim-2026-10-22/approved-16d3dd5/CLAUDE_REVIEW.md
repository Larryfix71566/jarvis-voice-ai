# WS-03 registration delta review (62f8805 → current head)

**Verdict: APPROVE.** I found no material new defect in the registration and evidence delta. The branch separation fixes the reproduced post-merge drift error without changing the approved P0 semantics, source scope or other workstreams. The notes below are low-priority and non-blocking.

**Scope and limits:**
- I reviewed only the supplied diff, the current WS-03 block, the plan section, the preserved artifacts and the branch-checker excerpt.
- `BRANCH_RE`, `OPEN_STATES`, `LIFECYCLE`, the full receipt README/manifest, ROADMAP §0.3 text and the CI results were not supplied. The 0-error results for both the normal and simulated-post-merge checks are your assertion; I did not reproduce them.
- Hashes are not recomputed.
- This is not acceptance evidence and adds no merge authority beyond the parent's docs-only authorization.

## Why the fix is correct

The fix is consistent with the supplied checker logic:
- `check_merged_branches` reads only the **Where** field.
- Before the fix, Where named `codex/ws03-compatibility-20261022`, the head branch of #248. After #248 merges, `origin/<branch>`'s SHA becomes an ancestor of main, so `branch_state` returns `"merged"`. With an open Status word, that produces an error. This matches the reported simulation failure.
- Where now names only `codex/ws03-compatibility-p0-20261022`. That branch does not exist yet, and no merge commit references it, so `branch_state` returns `"unknown"`. That yields no finding, neither error nor warning.
- After the implementation branch is pushed, it returns `"open"` until it merges, which is the intended lifecycle.
- The registration branch now appears only in the Claim boundary and the plan prose. Both are outside the checker's input, so after #248 lands they cannot trigger `"merged"` or `"maybe"`.

The text is consistent across files:
- ROADMAP Where, the Claim boundary, the plan Status line and the roadmap log all say the same thing:
  - the future implementation branch is distinct;
  - it is created from main only after the claim lands;
  - #248 is the registration vehicle on the old branch name.
- The Scope, Next step and Status fields are unchanged, as is the P0 contract text.

Prior non-blocking notes:
- **Note 3 (wording):** adopted essentially verbatim.
- **Note 2 (third input hash):** addressed. It is recorded in `third-input-integrity.json` and `IMPLEMENTATION_NOTES.md`, and attributed to the author rather than the reviewer.

## Non-blocking notes (priority order)

1. **Re-run the simulation on the exact rebased head after #249.** *Process condition, not a defect.*
   - **Issue:** The serial order puts #249 first. If #249 touches `ROADMAP.md` or main moves, #248's exact head changes. The earlier post-merge simulation would then not cover the head that actually merges.
   - **Smallest fix:** After rebasing onto main with #249 merged, re-run both the normal and the simulated-post-merge checks and CI on that exact head before merging.

2. **Reviewer vs. author attribution of the implementation notes.** *Low; evidence attribution.*
   - **Location:** Plan, "its unmodified response/receipt and non-blocking implementation notes are retained"; `IMPLEMENTATION_NOTES.md` header.
   - **Issue:** `IMPLEMENTATION_NOTES.md` was written by the author. It adds items that were not in the review: the strict-YAML anchor/tag detail, the 20,000-character body warning, and the sanitized test-environment rule. The plan phrasing attributes all of these notes to the review. The notes file correctly says the 62f8805 claim remains the authority, so this does not change the contract.
   - **Smallest fix:** In the plan, change the wording to "its unmodified response/receipt and author-prepared implementation notes derived from its non-blocking follow-ups are retained."

3. **`third-input-integrity.json` lacks its referents.** *Low; evidence self-description.*
   - **Location:** `approved-62f8805/third-input-integrity.json`.
   - **Issue:** The file records only `decoded_input_sha256` and `matches_receipt`. It does not name the input file (`corrected-claim-review/review-input.json`), its file hash, or the receipt it was checked against (`rereview-7f34dde/review-receipt.json`).
   - **Smallest fix:** Add `input_artifact`, `input_file_sha256` and `receipt` fields in the next receipt touch.

4. **The fourth receipt's input location is not shown in the README addition.** *Low; manifest completeness. Not verifiable from the excerpt.*
   - **Location:** The new README paragraph for `approved-62f8805/`. The receipt's `input_artifact` points to `../final-correction-review/review-input.json`.
   - **Smallest fix:** Name `final-correction-review/review-input.json` in that paragraph, unless the full manifest already lists it.

5. **Review count and Updated line will go stale.** *Low; wording.*
   - **Location:** README "Four source/scope reviews ran…"; ROADMAP `Updated: 10-22 (…)`.
   - **Issue:** Recording this delta review will make the count five. The Updated parenthetical does not mention the registration correction.
   - **Smallest fix:** Update both when you preserve this review's artifacts. For example, append "; registration branch separated before claim merge" to the Updated line.

## Contradiction check

No blocking contradiction found:
- **Baseline:** `636880e` now reads as the registration baseline. The implementation base is main after the claim lands. ROADMAP and the plan agree.
- **Main-first rule:** Source edits are still gated on the claim landing on main. No draft-branch exception is introduced.
- **Merge authority:** The claim still conveys no feature-code merge or deployment authority. The docs-only merge remains conditional on final review and CI, and WS-20 keeps the first merge slot.
