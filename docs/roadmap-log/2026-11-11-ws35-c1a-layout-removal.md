---
date: 2026-11-11
system: codex
rows: [WS-35]
prs: [334, 335]
---

# WS-35 C1a: retired native layouts

- System: Codex. Session reference: `codex/ws35-c1a-layout-removal-20261111`, continuing Larry's 2026-11-11 roadmap-development request.
- Source: `69f98054ef470ac5bda5738c5dd073059927a6d9`, branch `codex/ws35-c1a-layout-removal-20261111`.
- Base: `origin/next` at `a1369e223e51cc499c8f942fae95133994a4facb`, with `origin/main` at `4a0dd9635227cce51b01fcfcd584b3850ae81042` merged before editing (merge `bbb3492`). Freeze remains `5777e98cf1cdbaa65eb13079044693794c071927`.
- Documentation integration: parent C0-review/C10 branch `745b76b` merged as `86ebc73`; no runtime-source changes relative to `69f9805`.
- Claim: Larry approved following the starter attachment, including proceeding under WS-35 before the normal claim PR lands. No merge or deployment authorized.

## Implemented

Layouts 0 and 1 are removed from console composition, supporting-display rendering and ownership, transcript routing, and action/control selection. Stored values migrate to 2, regardless of the old one-time migration marker. No native rendering or routing reads `layoutVersion` anymore. The Debug layout-cycle control is removed. `appearance.set` accepts 2 idempotently and rejects 0, 1 and unknown values without changing the stored setting.

The conversation-thread flag and its existing transcript-to-result fallback remain unchanged. The supporting display retains its bounded grid, pointer-selected supplemental content, pinned overflow and transfer confirmation. OrbFieldView retains the same compact rail, pending-draft signal, notices and agent status rendering until C6; only its retired full-stage branch and duplicate captions are deleted. No orb renderer, palette, theme, backend, harness model, credentials, deployment, web or old-package edits.

Tests cover retired and unknown persisted values, idempotent migration, rejected appearance actions, one control row, thread arrival ownership, compact-caption deduplication and preserved supporting-display reading state. `AdaptiveInterfaceClosureC2Tests.swift` did not read `layoutVersion`, but needed three initializer updates after removing OrbFieldView's obsolete `compactPresentation` parameter. Other edits are within C1a's source/test set; coordination documentation belongs to WS-35.

## Verification

Final serial run on source `69f9805` (runtime tree identical after the documentation merge):

| Command | Result |
|---|---|
| `swift test --package-path macos/MortimerHost` | App target: 590 tests, 3 physical-display skips, 0 failures. Authority target: 28 tests, 3 unconfigured-owner skips, 1 existing F1 failure. Overall command exits 1. |
| `swift test --package-path macos/JarvisKit` | 239 tests, 0 failures, no skips. |
| `swift test --package-path ios/MortimerPhoneCore` | 67 tests, 1 skip for unconfigured disposable Python/native-owner fixtures, 0 failures. |

The unchanged F1 failure is `PhoneRemoteAuthorityProcessTests.testOrdinaryUnknownWaitRetainsActualSingletonAfterPartialEOF`, line 76: unwrapping the absent `PHONE_REMOTE_AUTHORITY_OWNER_BIN`. F1 is being repaired separately, not cherry-picked here. The three app-target skips require a second physical display; synthetic grid and ownership tests did run. The complete Host rerun followed the other package runs and the separate F1 focused run, with no concurrent build/test work.

The first Host run reproduced F1 and two assertions in the retired compact-caption test compiled before its C1a update. The final complete run above validates that updated regression and all 590 app-target tests; the earlier run is not counted as a pass. Swift was Apple Swift 6.4.2, target arm64-apple-macosx27.0.0. Raw local logs are retained under `macos/MortimerHost/.build/ws35-c1a-evidence/`; rendered synthetic fixtures are under `.build/interface-fixtures/`. The 900×600 console fixture was visually inspected: Command Console controls, output drawer, compact orb and microphone controls rendered.

`git diff --check` passed. `python3 scripts/check_roadmap.py` passed after the documentation update (0 errors, 0 warnings). `python3 scripts/check_allowlist.py origin/main...HEAD` exits successfully but explicitly does not enforce the self-edit allowlist for this Codex branch.

## Gates and handoff

Review C1a with Kimi. C10 instructions are published in [#335](https://github.com/Larryfix71566/jarvis-voice-ai/pull/335); Larry has not run the baseline and it remains required before C1a merges. [#334](https://github.com/Larryfix71566/jarvis-voice-ai/pull/334) requests C0/C0b contract clarification and does not block this bounded layout deletion. Native `appearance.set` retirement should be reflected in later contract/backend work rather than expanded into this slice.

No physical acceptance boxes were checked. Automated rendering and performance-test output are not C10 baseline or live acceptance. Development handoff: source and verification recorded by this change. The coordinator publishes the draft PR and records its number; independent review and C10 baseline remain required before merge. No merge or deploy performed for C1a.

- 2026-11-12 (Codex, WS-35 C1a, #337): Larry requested reviewer-ready draft promotion. Exact prior head `5807eee5b84de3121de30545e4dbe42699f1969d` had green hosted workflows and no merge conflict. This handoff changes documentation only; source and prior test evidence are unchanged. Kimi reviews C1a; Larry captures C10 before merge. The known separate F1 authority-prerequisite failure remains disclosed; no full-Host green claim. Reviewer-ready is not approval to merge or live acceptance.
