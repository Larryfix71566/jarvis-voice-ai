---
date: 2026-11-12
system: claude
rows: [WS-35]
prs: [337]
---

# WS-35 C1a layout removal — Claude's independent review of #337, Claude, 2026-11-12

System: Claude (Claude Code cloud session, Larry's Claude Duet channel). Nonauthor reviewer. The closure plan and #337's body name Kimi as C1a's reviewer. Larry reassigned this review to Claude on 2026-11-12 at 15:52:31 UTC ("Yes, Claude takes them", answering whether Claude takes Codex's #337 and #339 reviews from Kimi). Claude did not write #337. This change is documentation only: this entry. It does not change the WS-35 block, which is Codex's scope.

## What was reviewed

[#337](https://github.com/Larryfix71566/jarvis-voice-ai/pull/337), head `7cc49f9177ef08aeba6044ac1861328a7acbecfe`, base `next`. All five checks pass at that head. None of them builds Swift; B1 (#338) is not merged.

The runtime change is source commit `69f9805`: 13 MortimerHost source files and 11 test files. The rest is documentation: Codex's C1a log, the WS-35 block, closure-plan progress, and #334 and #335, which are ancestors of #337. `git diff pr/335 pr/337` is 28 files, 170 insertions and 523 deletions.

## What C1a does

Layouts 0 (orb field) and 1 (adaptive stage) are deleted; the Command Console (layout 2) is the only composition.

- `InterfaceLayoutVersion` loses `resolve()` and gains `current = 2`, `preferenceKey` and `migrate()`, which writes 2. `MortimerHostApp.init` calls it on every launch, replacing the one-time migration marker.
- The Debug menu's layout-cycle button is removed.
- `appearance_set` now accepts only layout 2 and rejects 0, 1 and anything else with `.invalid`, without changing the stored value.
- Every native view and router that read `mortimer.interface.layoutVersion` stops reading it. At #337's head, the only source references are `InterfaceLayoutVersion` itself, the launch migration and the `appearance_set` handler.

## Checks

| Claim | How checked | Result |
| --- | --- | --- |
| Behavior in layout 2 is unchanged | Read every removed branch in `ConsoleView`, `AdaptiveStageView`, `DisplayWindowView`, `DisplayWindowStore`, `SupportingDisplayCoordinator`, `ConversationThread`, `AppMessageRouter`, `WorkspaceView` and `WorkspaceResultPane`. Each removed path ran only when the layout was 0 or 1. Each kept path is the one layout 2 took: for example `routesSpokenAnswersToResults` was `layout == 2 && !threadEnabled` and is now `!threadEnabled`; `WorkspaceView(showsControls:)` was `!consoleBarOwnsControls`, which was `false` in layout 2, and is now `false` | confirmed |
| `OrbFieldView` keeps its compact rail and pending-draft signal until C6 (plan, 2026-11-11 orb recheck) | `OrbFieldView` at #337: `body` renders `compactReadout`; `attention` still reads `displayResults.hasPendingDraft` and drives the "Confirmation needed in Output" line, ring colour and shadow. Only the full-stage satellites, beams and `compactPresentation` flag are gone | confirmed |
| `AGENT_LAYOUT` still serves its other reader | `RunsTab.swift:141` iterates it; entries keep `key` and `label`; only the unused `x`/`y` positions are dropped | confirmed |
| Scope: files that read `layoutVersion` | Of the 24 source and test files changed, 23 read `layoutVersion` or `InterfaceLayoutVersion` on `next`. The exception, `AdaptiveInterfaceClosureC2Tests.swift`, only drops the removed `compactPresentation` argument; Codex discloses it | within scope |
| Retired values are rejected without side effects | `ConsoleActionCoordinatorTests.swift:669–680`: layout 2 is applied; 0, 1, −1 and 99 are `.invalid` both as target and as argument, and the stored value stays 2 | test present |
| Swift test counts recorded (plan §8) | PR body and Codex's log, source `69f9805` on arm64, Swift 6.4.2: app target 590 tests, 3 second-display skips, 0 failures; authority target 28 tests, 3 skips, 1 failure (F1, fixed separately in #339); JarvisKit 239, 0 failures; PhoneCore 67, 1 skip, 0 failures | recorded; the app-target count matches Kimi's 590 on `main` at `4e58eaa` |

Claude ran no Swift; this environment has no Swift toolchain.

## Findings

No blocking findings.

- **Merge conflict (needs the author).** GitHub reports #337 as `dirty`. Since #337 was cut, `next` gained #340 (now at `4e64137`). A local merge of `pr/337` into `origin/next` conflicts only in `docs/plans/MORTIMER_RELEASE_CLOSURE_PLAN.md`.
- **Nit, leftover writes of the retired key.** Three test files not otherwise changed still set `mortimer.interface.layoutVersion` (`CC7a4ConversationIntegrationTests.swift:75`, `LiveVoiceResponseStreamTests.swift:58` and `:107`), and `CC7a2ReviewRegressionTests.swift:110–115` loops through values 0 to 99. Nothing reads the key now, so these lines set a value the app ignores. The CC7a2 loop now confirms that the layout value has no effect, which is a useful regression. The other two could drop the line in a later cleanup.
- **Not a finding, contract follow-up.** `jarvis/bot/console_protocol.py:72` still accepts any integer `layout` for `appearance_set`; the native side now rejects all but 2. Codex's log assigns this to later contract work, which is the right place.

## Verdict

**APPROVE** at `7cc49f9`. The deletion is behavior-preserving for the shipped Command Console, stays within C1a's scope, keeps what C6 still needs, and has tests for the new migration and rejection rules.

Before merge:

1. Larry captures the C10 freeze baseline on his Mac ([#335](https://github.com/Larryfix71566/jarvis-voice-ai/pull/335)). The closure plan requires it before C1a merges, and Codex's log says Larry has not run it yet.
2. #335 merges first. #337 contains it.
3. Codex resolves the closure-plan conflict with current `next`.

#337 targets `next`, not frozen `main`, so §0 rule 15's approval by name does not apply to it.

## Unchanged

No source, test, workflow, plan, ROADMAP block or acceptance checkbox was changed. No GitHub review or comment was posted on #337. No Swift test or benchmark was run.
