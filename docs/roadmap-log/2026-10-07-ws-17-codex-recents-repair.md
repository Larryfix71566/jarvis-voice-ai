---
date: 2026-10-07
system: codex
rows: [WS-17]
prs: [173, 194, 195]
---

# CC7a.3 repaired source; local evidence and remaining gates

Source: `fee4ac058f18094867c0476e1aa588512c20ea66`, isolated branch
`codex/ws17-closure-20261007`. Claim #194 merged as `e7b099b`; merge `dcca93f`
preserved Claude’s #173 foundation `fb2e06f` and tests. Codex owns the remaining
implementation; historical attribution and every live acceptance box survive.

Fixed the reproduced numbered-target race, dropped ambiguity choices and Older
Close access, plus comparison transport and the real immediate-acknowledgement
race. Independent Codex review also identified omitted-revision rebinding,
non-string reply status and capacity failures, all repaired with causal tests.
Spoken references now require the exact disclosed revision and canonical UUID
resolution; stale/ambiguous/missing observation has zero unintended effect.
All thirty maximum-length ASCII numbered entries fit a valid 11,246-character
projection; declared scopes and other small-inventory metadata remain usable.
Extreme Unicode over the existing budget refuses truthfully. No limit increase,
second state owner, provider route or production edit.

## Local verification on this source

- `RUN_LIVE=0 PYTHONPATH=<candidate> <existing-venv-python> -m pytest tests/unit/test_console_actions.py tests/unit/test_console_voice_bridge.py tests/unit/test_console_protocol.py tests/unit/test_pipeline_names.py tests/unit/test_console_session.py -q`: 67 passed, two dependency warnings.
- `RUN_LIVE=0 JARVIS_DB_PATH=/private/tmp/ws17-bot-wiring-tests-final.db PYTHONPATH=<candidate> <existing-venv-python> -m pytest tests/integration/test_bot_wiring.py -q`: 64 passed, two dependency warnings. Vault/costs/test state is isolated by the repository fixtures; no live provider or user database test.
- `swift test --disable-sandbox --skip-update --build-system native --package-path macos/JarvisKit`: 226 tests, zero failures.
- Same Swift command for `macos/MortimerHost`: 512 tests, six skips, zero failures. Skips: three external-display prerequisites, and three existing WindowVisibility tests whose host could not become active. ProtectedDisplayContent’s actual fixture-window capture and DisplayWindowPrivacyBoundaryTests passed; this is not an actual protected conversation receipt.
- Pinned existing WebRTC cache prepared in the candidate only. A sandboxed compiler attempt stopped before compilation due to an unwritable compiler cache; the granted host test rerun passed. These are supplemental native host checks, not an independent VM receipt.
- `git diff --check` clean; receipt-mode roadmap checker zero errors/warnings before this status publication.

Local immutable test logs (raw logs stay local):
- `/private/tmp/ws17-cc7a3-backend-inventory-scope-final-tests.log` — SHA256 `7ef8f95a9db7491d75f8904494c1cca96a96ee919f245d4dfd582f2968adec11`
- `/private/tmp/ws17-cc7a3-bot-wiring-final.log` — SHA256 `11f5563c3f0efb78e7189c6987d35df330064cf5a834e2a8584ba5d777bfc942`
- `/private/tmp/ws17-cc7a3-jarviskit.log` — SHA256 `b1db4cd0aaa2090f751bd27ed1bc8b68c86610e7b7e09aeef0481e4c68e26e91`
- `/private/tmp/ws17-cc7a3-mortimerhost.log` — SHA256 `8a1841257bead84d3f61f2c971e65b204bf10af3eff994e525969e7891de344e`

The unchanged full-profile verifier is running for this committed source against
baseline `b2e17b4` with the existing dependency-matched `c43` image. Receipt target:
`/private/tmp/ws17-candidate-full-profile-fee4ac0.json`; no VM pass is claimed
until its actual terminal result. Earlier baseline audio-readiness timing risk
is retained, not skipped or waived.

Required cross-system review, merge/release, deployment and exact-build
UI2-22…25 remain open. #195 publishes CC7a.4’s additional contract/scope before
its code; reuse is not implemented. Production remains the existing roadmap
receipt. Prior #191 bounded public-text/routing evidence remains reusable;
this code/test slice closes no full live gate.

System: Codex. Session: `codex://threads/01a088c1-681c-70b0-ad7e-50ad6bccf83f`.
