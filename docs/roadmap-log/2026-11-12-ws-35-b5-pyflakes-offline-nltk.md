---
date: 2026-11-12
system: codex
rows: [WS-35]
prs: [367]
---
# B5: full pyflakes gate and pinned offline English tokenizer

Base: `next` at `b17842c2b772e195dcb4ac4f1555f6494e738fa5`.
Branch: `codex/ws35-b5-offline-lint-20261112`. Larry dispatched B5 after
the B1 Host rerun was triggered. Reviewer: Claude. Status is recorded only in
this new log, per the daily batch rule; no ROADMAP or closure-plan edits.

## Scope and implementation

- CI selects all pyflakes diagnostics (`ruff --isolated --select F`), removing
  the old per-file F821 exemptions. No blanket file/rule exclusions are added.
- Lint-only fixes remove genuinely unused imports, keep evaluated calls when
  dropping unused bindings, and add the missing Callable/subprocess/PreparedMedia
  imports. Explicit exports preserve the admin route facade, compatibility
  imports, and all 42 imported pytest fixtures; registration is not removed to
  make lint pass. Narrow existing-name compatibility imports remain documented.
- Four English `punkt_tab` text resources and the upstream model README are
  bundled. Every byte was compared with the official archive already pinned
  by `sandbox/guest/prepare.sh` (SHA-256
  `e57f64187974277726a3417ca6f181ec5403676c717672eef6a748a7b20e0106`).
  No invented models, pickle payloads, other-language corpus, runtime downloader
  or production tokenizer setting is introduced.
- A stdlib verifier checks the exact English member set, sizes and hashes before
  tests/application imports. CI and non-live pytest select the bundled resource.
  A cold subprocess smoke uses an empty HOME, removes NLTK search fallbacks and
  blocks downloads/socket connections while importing the real Pipecat utility
  and performing English sentence tokenization. Mutated/missing/linked/extra
  resource tests fail closed.

## Local verification

- Before frozen-fixture restoration, non-protected production/script/service/test
  paths passed full pyflakes. The final lint status is recorded below.
- Targeted fixture/import regression: 511 passed, 19 subtests passed.
- Offline data regressions: 8 passed.
- Vault: 17 passed, 5 existing deprecation warnings. The test environment needed
  its separately declared watchdog/python-ulid dependencies; no lock file changed.
- Policy: 9 passed. Offline evaluations: 13 passed. Roadmap checker and diff
  whitespace check passed. Supplemental independent review approved the source/data changes and reran
full-F lint on all non-sandbox paths plus the offline smoke. This does not
replace Claude's required review. Full backend unit/integration: 8,570 passed,
145 skipped, 583 subtests passed, 42 warnings. Import smoke and latency budget
passed. The final stronger DNS/datagram-prohibited cold smoke reran all eight
offline-data regressions successfully. Claude review remains pending.

## Human-only boundary

Full repository lint has 16 findings in the protected sandbox paths, plus
one frozen-fixture finding described below. The implementation has not edited them. A lint-only patch for
Larry removes unused imports and renames the unused hydration result binding,
preserving its evaluation. The unapplied patch is
[`docs/plans/ws35-b5-sandbox-pyflakes.patch`](../plans/ws35-b5-sandbox-pyflakes.patch);
`git apply --check` succeeds. Patch SHA-256:
`921449f4fa299b323e327c396ded1d58db5e27214260ca1addd16948cfdc1b0c`.
Paths: `sandbox/files.py`, `sandbox/guest/hydrate.py`, `sandbox/guest/rpc.py`,
`sandbox/images.py`, `sandbox/publish.py`, and sandbox tests `test_artifacts.py`,
`test_files.py`, `test_runtime.py`, `test_session.py`, `test_source.py`.
The full gate intentionally remains red until the protected patch is applied
by Larry or he explicitly authorizes this exact exception. No suppression masks
that prerequisite. No production, credential, controller-model, merge or
deployment action is part of B5.


## Frozen-fixture correction after draft publication

Draft #367 at `279019b7` exposed two controller failures: removing an unused
`pytest` import from `tests/unit/test_status_providers.py` changed a security-reviewed
whole-file hash. The fixture is restored exactly to its approved bytes,
SHA-256 `68eb01078156221de31ea83ea8b3588bfbc634a9fa78ca4ff04c47b08daa3caf`.
No security pin, scanner rule or protected source was changed. All ten frozen
fixture hashes are checked by the 164-test controller suite. Future lint work
must inventory these pins before touching fixture imports.

The restored immutable fixture retains one F401 (`pytest` imported but unused),
so full lint now has 17 known findings: that one plus the 16 protected sandbox
findings. No exception has been added. The proposed exception for Larry's
approval is only `tests/unit/test_status_providers.py:F401`, with this exact
fixture hash retained and independently checked; all other rules/files remain
enforced. Altering the approved fixture hash is not proposed. Required Claude
review and Larry's protected-patch/exception decisions remain open.

## Hosted verification on `48dc5359`

[Validation run 43310778076](https://github.com/Larryfix71566/jarvis-voice-ai/actions/runs/43310778076)
completed on exact PR head `48dc53590c3e297e08e2d9bbd2073d46a6ca9e3a`.
The bundled offline tokenizer verification and backend import smoke passed.
Ruff failed with exactly the 17 disclosed findings: 16 protected sandbox findings
and the frozen provider fixture's unused `pytest` import (F401). Backend unit
and integration tests, sub-agent evaluations, latency enforcement and frontend
build were skipped after lint failure; they are not hosted passes.
Allowlist/roadmap, policy, JarvisKit and MortimerPhoneCore passed. MortimerHost
was cancelled during its test suite, not passed. Separate exact-head knowledge
base run `43310776924` and controller run `43310776626` passed.

This evidence-only update does not apply the sandbox patch, add the proposed
F401 exception, change fixture pins, or resolve required Claude review. Those
prerequisites remain open. The results above belong to the named tested head;
any checks triggered by this documentation update are separate evidence.
