# Claude subscription review — original repair c2cd6d9

Exact reviewed head: `c2cd6d9e2a23b8591c0a6615472f662b31165957`.
Base: `a3b4107f07e2d8a581cdf304bf172a8fb379eaf0`.
Official Claude Code 2.1.291, authenticated claude.ai Max; tools disabled,
empty MCP configuration, no API credentials inherited or model fallback.
Requested and returned identity: `claude-opus-5-5` (response metadata verified).
Packet: 132,274 bytes, SHA-256
`c436b182cc709f0bc1b775f764961932ab87eb074dba50eec303e54d9d2f6b96`.
Started 2026-10-22 23:28:39 UTC; completed 23:31:33 UTC, exit zero.
Input remained unchanged. Repository source/fixtures only; no private logs.
Latest explicit bounded-source subscription-review authorization superseded
this claim's earlier no-new-disclosure restriction for this review alone.

The following is the returned static review, not test-execution evidence.
Follow-up author changes/dispositions are recorded separately; this verdict
must not be relabeled as a review of those later changes.

---

**Verdict: ACCEPT**

I found no concrete correctness regression in the repair diff (a3b4107 → c2cd6d9). The findings below are coverage suggestions and pre-existing limitations, not blockers. This is static review only: I ran nothing and did not recompute the `config/skills.yaml` digest pin.

## What I checked

- **Passive vs. refresh serialization.** `run_passive` now reads `prior`, decides, and publishes all inside `_writer_lock`. `refresh_report` fetches outside the lock and publishes inside it. A passive worker that waits for the lock therefore sees any refresh that completed in the meantime. Commit order equals completion order, as documented. `_publish` is never called while holding the lock across fetch, selection, or notice work.
- **Lock mechanics.**
  - `flock` on a separately opened descriptor conflicts across processes and across threads, so it does not depend on fd sharing.
  - `O_NOFOLLOW`, the `S_ISREG` check, and never unlinking the lock file avoid the classic unlink-and-recreate lock split.
  - No path re-enters the lock, so there is no self-deadlock.
- **Late notice acknowledgement.**
  - The notice is sent outside the lock.
  - The acknowledgement re-reads under the lock and clears `notice_pending` only when the UUID `generation` matches.
  - A later refresh (which sets pending to false) or a later changed passive run (which publishes its own pending generation) is never overwritten.
  - On failure, the committed generation stays pending. Duplicates remain possible, which the at-least-once contract allows.
- **Unchanged path.** It reuses `prior` without republishing, so source dates and `generation` are retained and evidence is not laundered daily. Legacy schema-2 caches with no generation upgrade once, with sources unchanged.
- **Readers.** `read_report` and `_view` render from one `_raw` snapshot. The visible result of `run_passive` comes from the generation it captured. Atomic temp-file-then-replace writes keep readers coherent.
- **MODEL_ID.**
  - `{0,3}` plus the `(?![\w-]|\.\d)` lookahead accepts `claude-opus-5` and rejects `5.5`, `-extra`, `_foo`, and five-part IDs.
  - Backtracking cannot truncate a longer token into a shorter candidate. Every shorter prefix is followed by `-` or a word character.
  - Cached-ID revalidation uses the same pattern.
- **Matcher fixture and metadata.** The seven new fixture IDs match the new `example_ids`. Generic daily-brief requests share no tokens with the card. `switch`, `better`, `window`, and `display` are not card tokens.
- **Offline daily test.** Only `access_status` runs real code. Health and verdict values are synthetic, not skipped. Network, DB, subprocess, and passive-run calls fail loudly.

## Actionable findings

### 1. `test_writer_lock_covers_passive_read_through_commit` cannot detect a missing commit lock
**Severity:** Medium. Coverage only, not a blocker.
**Location:** `tests/unit/test_harness_cache_concurrency.py`, worker mode `locked_passive_read` and the test itself.

**Problem.** The passive worker uses an unchanged `selection`, so `changed` is false and it never publishes.

**Interleaving if the lock were removed:**
1. Passive captures `prior` = opus and pauses.
2. Refresh publishes sonnet.
3. Passive resumes, finds no change, and writes nothing.
4. The final `["claude-sonnet-5"]` assertion passes anyway.

The only discriminating check is the non-blocking `flock` probe. That proves the lock is held during the read, but not that it serializes a *committing* passive against a refresh.

Also, the `refresh` worker signals `reached` before it reaches the lock. Nothing establishes that it is actually blocked when the passive worker is released.

**Minimal change:**
- Make `locked_passive_read` use `changed_selection`, so the passive worker publishes a stale-opus generation.
- In the `refresh` mode, signal from a wrapper around `H._writer_lock` placed immediately before acquisition, not before `seed`.
- After the barrier, assert the refresh has not finished, e.g. `refresh.join(0.5); assert refresh.is_alive()`. This is a one-sided check that a slow machine cannot make falsely pass.
- Release, then assert the final report shows sonnet with refresh's selection digest (`"a"*64`).

With the lock removed, the passive worker's stale opus generation would then win, and the test would fail as intended.

The other race tests do discriminate against the base code:
- `before_passive_read`: base read `prior` before the selection pause.
- `during_notice`, single and overlapping: base rewrote the old payload after the notice.
- `slow_fetch`: the parent would hang if fetch held the lock.

Note that `before_passive_read` verifies read ordering, not locking. That matches its name.

### 2. New card tokens widen the false-positive surface; negatives don't probe it
**Severity:** Low. Coverage suggestion.
**Location:** `skills/harness-model-evaluation/SKILL.md` description, and `matcher-cases.json`.

**Problem.** The description now adds `claude`, `opus`, `sonnet`, `fable`, `codex`, `sol`, and `astra` to the matchable card. `match_skill` needs only `MIN_SHARED_TOKENS = 2` and a score of at least 0.30 against the smaller token set. A short non-harness request naming two of these words could therefore select this skill, and `MAX_INJECTED = 1` means it would displace a better one.

Plausible examples:
- "Tell me a fable about Claude"
- "Ask Claude Opus to summarize my email"

The current negatives (switch, compare, window, layout, model-access) contain none of these family words. I cannot compute `_tokens` and `_overlap_score` from the packet, so this is unproven.

**Minimal change:**
- Add negatives that pair two family words outside a harness or controller context.
- If any of them selects the skill, sharpen the description. Per the module's own guidance, do not name the anti-triggers there.

### 3. Matcher roster test depends on ambient environment variables
**Severity:** Low. Test determinism.
**Location:** `tests/unit/test_harness_brief.py::test_harness_matcher_cases_against_enabled_roster`.

**Problem.** `load_skills()` reads two environment variables:
- `JARVIS_AGENT_SKILLS_ENABLED`: if set to false, the roster is empty and the test fails spuriously.
- `JARVIS_SKILLS_WORKSPACE_ENABLED`: this toggles digest-pin enforcement.

**Minimal change:**
- Add `monkeypatch.delenv("JARVIS_AGENT_SKILLS_ENABLED", raising=False)`.
- Run the test once with `JARVIS_SKILLS_WORKSPACE_ENABLED=1`. Package-only matching then also proves the updated revision pin admits the package.

### 4. Pre-existing, not introduced here: digit runs are unbounded and Unicode-permissive
**Severity:** Low. Not a blocker for this repair.
**Location:** `jarvis/status/harness.py`, `MODEL_ID`.

**Problem.** `\d+` was unbounded in the base and remains so. Python's `\d` also matches non-ASCII digits. "Finite" therefore holds for model families but not for token length.

**Consequence.** Assume an official page contained an extremely long digit run after `claude-opus-`.
1. The written report can exceed `MAX_BYTES`, because `write_atomic` does not check size.
2. `_raw` then returns `None`.
3. `run_passive` treats the cache as absent and republishes empty sources with a notice.

This requires anomalous content on the fixed official sources, so it is not a patch regression.

**Minimal change:** compile with `re.ASCII` and bound the counts, e.g. `\d{1,3}(?:-\d{1,8}){0,3}` and `gpt-\d{1,3}(?:\.\d{1,3})?`.

### 5. Informational: stale passive selection can be committed after a refresh
**Severity:** Informational. No change required by the contract.
**Location:** `jarvis/status/harness.py::run_passive`.

**Interleaving:**
1. `current` is read before the lock and gets S1.
2. A refresh then commits with S2.
3. Passive sees the meaning differ and publishes S1, with sources preserved.

**Effect.**
- Readers with S2 report `selection_changed`. This is conservative and never falsely `recent`.
- Spurious notices can occur, which at-least-once delivery allows.
- No evidence or source dates are lost.

The base had the same pre-read and a worse overwrite. Moving the selection read inside the lock would violate the "no external work under lock" rule, so leave it.

## Out of scope and unchanged

- Switching remains blocked.
- The candidate set and gaps text make no claim of account eligibility or of which model is active.
- The unmerged foundation dependency is neither reviewed nor approved by this verdict.
- No benchmark or deployment gate applies to this source review.
