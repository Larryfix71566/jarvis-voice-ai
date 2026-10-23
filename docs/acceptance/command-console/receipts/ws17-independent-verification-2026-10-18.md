# WS-17 full independent verification — 2026-10-18

Full ordered twelve-check offline VM verification **passed** on merged release source
`d38c88646113cf27fd5b165f08f4739d3fe6ca01`, from 21:53:01 to 22:20:09 UTC.
PR #222 merged as `406bec0660a292447c58ba9bf786307581808854`; #223 merged as
`d38c88646113cf27fd5b165f08f4739d3fe6ca01`. Both were verified merged before the run.
Larry’s 20:08 steps 1–2 authority and 21:49 continuation cover this verification,
not deployment. WS-17’s existing registered branch owns this evidence slice.

[Original verifier receipt](ws17-independent-verification-2026-10-18.json) and
[identity, preservation, test summaries and CI manifest](ws17-independent-verification-2026-10-18-manifest.json)
retain the exact results and hashes. The recorder ran the checks; Claude’s earlier
source review did not execute them.

## Identity and isolation

- Candidate commit: `d38c88646113cf27fd5b165f08f4739d3fe6ca01`.
- Candidate fingerprint: `305540b836a604d966580897ad15ad8ad28e87638eb8f4f774956523d884b361` (1,914 source files).
- Protected reference: approved `08c06357267ef1348ec4b64dfdd12b26d4710a50`, fingerprint `1cb637d1ad2667fb040715a9ba54f43b6216b1cf8b7c943d77649afc70e67711` (1,824 files).
- The raw receipt’s `source_commit` is that protected import/reference, **not the candidate commit**. Candidate identity is bound separately above and in the manifest; it is never relabeled as the baseline.
- Prepared image: `c43cc422ac3ecc9a5725a460caf64cf179205f1b931443a29b6164ebcb274e18`; profile `c400d0df293e470a810b7fda1916fee4c29d3f41cd0de78d7ef4a2219ec7a00e`; reviewed merged runner `62019da52862d37e1e9c12b521849171440d27c57846a156c3e6994ee71d4b39`.
- Attempt: `105c7adecbd444eeb56844bc1badedd4`; development `63ec4cc92721`; fresh verification `f894ca6ed5f5`.
- New isolated home: `task-3/acceptance-vm-home`. Its initial task/cleanup inventory was empty; a copy-on-write copy of the stopped prepared template was used. The existing home’s read-only plan listed two older tasks; neither was reclaimed. All seven preexisting VMs remain present and stopped.
- Repository `Images.create`, offline hydration, `WorkspaceFiles.freeze`, `Verifier.verify(timeout=7200)` and `Verifier.receipt` were used. All original twelve checks, 900-second backend budgets, baseline protections, scanner/pins, dependency/profile definitions and worker/network/audio/clipboard restrictions stayed intact. No provider call, installation, host security grant or image/settings pointer change.

## Actual results

| Check | Actual result |
|---|---|
| backend-imports | command exit 0 |
| baseline-backend | 6280 passed, 11 skipped, 54 warnings, 2 subtests passed in 421.22s (0:07:01) |
| backend | 6592 passed, 11 skipped, 53 warnings, 2 subtests passed in 422.23s (0:07:02) |
| scripted-evals | 13 passed, 1 warning in 0.93s |
| latency | command exit 0 |
| knowledge-base | 17 passed, 5 warnings in 3.07s |
| baseline-knowledge-base | 17 passed, 6 warnings in 4.68s |
| web | command exit 0 |
| native-library | Executed 235 tests, with 0 failures (0 unexpected) in 9.763 (9.790) seconds |
| native-app | Executed 563 tests, with 8 tests skipped and 0 failures (0 unexpected) in 160.675 (160.723) seconds |
| baseline-native-library | Executed 227 tests, with 0 failures (0 unexpected) in 9.632 (9.655) seconds |
| baseline-native-app | Executed 514 tests, with 7 tests skipped and 0 failures (0 unexpected) in 147.506 (147.556) seconds |

All twelve returned 0. The desktop probe passed; synthetic DB/vault seeds passed.
The final guest capture matched the frozen candidate. `Verifier.receipt` validated
candidate/baseline/image/profile/runner, ordered argv and all twelve log hashes.
The raw receipt SHA-256 is `43dbd825fdc090a054b3057efcffc1bae7048342e1d0a31cec15c922abcb4650`.
Logs remain under the isolated development task’s `verification/105c7adecbd444eeb56844bc1badedd4/` directory.

Candidate native app: **563 tests, eight skips, zero failures**; baseline app:
**514 tests, seven skips, zero failures**. Existing conditional skips cover
Screen Recording/window capture, absent two-display topology and inability of
the test host to become active in the VM’s WindowServer. Exact reasons are in
the manifest. No permission was granted and no skipped physical check is passed.
These VM results differ from the earlier physical 563/five-skip record. Backend
warnings include denied cache writes to the protected baseline; no protection
was weakened. No tests, skips, assertions or budgets were changed.

All five CI checks passed on both reviewed PR heads. The runtime/test/config/CI
source in candidate `d38c886` is byte-identical to cleanup head `1632afb`; only
six documentation/evidence paths differ, listed in the manifest. Those current
receipts support CI applicability; no CI run on an invented merge head is claimed.
The final cleanup reviewer resolved its corruption finding at 21:32:51 UTC with
no new blocker; full report and exact hashes remain on [#222](https://github.com/Larryfix71566/jarvis-voice-ai/pull/222).

## Preservation and remaining gates

Both fresh owned task clones were stopped/deleted; their host records, candidate,
receipt and logs remain. The copied stopped template is retained. The known-good
rollback code/archive/receipt hashes are unchanged. Installed app marker remains
`575cc7b`, dirty/debug with unknown fingerprint; executable SHA-256 remains
`6c67661bb94ddde5fa95d0a807dd77e5d837483a69c0d979412064fdcd3eaf29`.
This is read-only bundle identity, not loaded app/backend/config/health evidence.

UI2-14 now has the complete full-profile technical evidence for the frozen
candidate. Its global checklist reconciliation remains with the existing owner;
this WS-17 slice changes no compound parent or physical/live checkbox.
UI2-15 rollback exercise, UI2-16 separately authorized deployment/loaded identity,
UI2-17 actual five-day observation and UI2-18 final closure remain open. Rollback
preservation alone is not a rollback pass. UI2-24/25 must be retested on the
correct installed candidate before 22/23 and dependent 04/09/13. Missing hardware,
configuration/timezone, protected capture, voice/sharing and WS-06’s separate
week retain their original gates. No production restart, replacement or deployment.
