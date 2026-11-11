---
date: 2026-11-11
system: codex
rows: [WS-35]
prs: [325, 334, 335, 337, 338]
---

# WS-35 F1: ordinary Swift process-test prerequisites

System/session: Codex, `codex/ws35-f1-phone-authority-20261111`, Larry's 2026-11-11 release-closure starter-prompt dispatch. Source commit: `3e04808de1f442ab68544b35bb48a751b759bf86`, based on `origin/main` `4a0dd9635227cce51b01fcfcd584b3850ae81042`. This is the separately scoped F1 acceptance-fix candidate; main remains frozen and Larry must approve the eventual PR by name before merge. Kimi reviews independently.

## Cause and repair

#325's `testOrdinaryUnknownWaitRetainsActualSingletonAfterPartialEOF` failed at line 76 before launching any owner: it unconditionally unwrapped `PHONE_REMOTE_AUTHORITY_OWNER_BIN`, then `PHONE_REMOTE_AUTHORITY_PYTHON`. Ordinary `swift test` supplies neither. Its sibling actual-process tests already use an explicit skip when the optional offline-owner harness is absent and discover Python through an existing helper. The documented focused command supplies the owner variable but does not require the Python override.

The twelve-line test-only change follows those existing prerequisites: absent/non-executable owner yields an explicit skip; Python uses the override or existing PATH discovery. Missing Python with the owner enabled remains a visible failure. All singleton-held-lock, partial EOF, ECHILD, no-KILL and teardown-unlock assertions are unchanged. No production source, harness-controller model, installed service, credentials, deployment or settings were changed.

## Verification on the exact source

| Invocation | Result |
|---|---|
| Explicitly enabled offline `PhoneRemoteAuthorityTests` | 28 tests, 0 skips, 0 failures |
| Formerly failing singleton test, owner configured and Python found on PATH | Passed, actual owner process exercised |
| Same test with explicit Python override | Passed, actual owner process exercised |
| Ordinary authority suite, owner/Python overrides unset | 28 tests, 4 owner-prerequisite skips, 0 failures |
| Full `swift test --package-path macos/MortimerHost`, owner/Python overrides unset | Exit 0: 618 tests, 7 skips, 0 failures. Authority 28/4 skips; app target 590/3 second-physical-display skips. |

The enabled run is necessary evidence: this repair does not claim a skip demonstrates singleton correctness. It proves the original assertions pass with the actual disposable offline owner. Tests were serialized with C1a's full runs, not run concurrently. No live/backend service used.

Full-run log SHA-256: `fa1505f18d61ff7691dbf059ebc71aa4d184541aefd6059c7204e329aa72cfe5`. Local logs retained in the worktree's ignored `.build/ws35-f1-evidence/` directory. Roadmap and diff checks passed. The documentation updates do not change the tested Swift source.

## Handoff

Kimi reviews the narrow test prerequisite repair. Larry approves this PR by name as an acceptance fix before merge to frozen `main`. After an authorized merge, its author merges `main` forward into `next` that day, without rebasing. Do not cherry-pick this candidate into C1a or claim C1a's existing full-suite failure already fixed there.

Other WS-35 work remains separate: #334 contract verdict; #335 unrun C10 baseline instructions; #337 C1a, which still needs the baseline and independent review; #338 hosted Swift CI, awaiting hosted results. No acceptance checkbox, merge, deployment or freeze closure is authorized by this receipt.
