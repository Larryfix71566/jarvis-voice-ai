---
date: 2026-11-18
system: claude
rows: [WS-36]
prs: []
---

# 2026-11-18: WS-36 C7a, activity row and inline approve/decline (Claude)

- **System:** Claude (Claude Code cloud session), at the coordinator's request after Larry's "you tell me" on what to develop next.
- **Owner change (rule 14):** C7a moves to Claude. Codex's claim on `codex/ws36-c7a-claim-20261116` is docs only, and no Codex C7a code is in flight. Under rule 16 this log records the change; the daily batch folds it into the WS-36 row.
- **Base:** `next` at `2a15d86`.

## What changed

- **Activity row (box 192, contract 4.1).** One row under the thread names who is working and the current step, such as "Developer · Plan start", or "Mortimer · Thinking" while the Supervisor thinks. It updates in place and is never a transcript line. It shows fixed agent and tool names only, never a run's task text. Under Reduce Motion the spinner becomes a still icon. VoiceOver reads "Developer is working: Plan start" and the row is marked as updating often.
- **Inline approve and decline (contract §3).** JarvisKit decodes `approval/pending`, `approval/settled` and `approval/result` and encodes `approval/decide` (exactly seven keys). A new `ApprovalStore` keeps the open approvals for the current session and generation, validates them as 3.4 says, and clears them on disconnect, a new generation or `stale_session`.
  - The thread shows each open approval under the request that produced it, or at the end when `origin_request_id` is null. The transcript carries no request id, so the turn is found by arrival time, as for cards.
  - The row shows a hand symbol and the words "NEEDS YOU" in the needs-you yellow, the bot's summary verbatim, and Approve and Decline buttons with text labels. Yellow is never the only cue.
  - A tap sends one decision with a new request id and disables both buttons until `approval/result` or `approval/settled` arrives. `not_ready`, `protected_turn`, `disabled`, `duplicate` and a 10 s timeout bring the buttons back with one line of app text. A settled approval leaves one line of app text: "Approved.", "Declined.", "Done by voice.", "Replaced by a newer request." or "Expired before an answer.".
  - VoiceOver labels include the summary: "Needs your approval from Developer · plan_start: …", "Approve: …", "Decline: …".
- **`hasPendingDraft` (contract 3.9).** True while an approval is open or a file-send offer is pending, or by the older draft-tool rule. The orb ring, drawer dot and top bar keep reading the one property.
- **Space beside push-to-talk.** A pure `SpaceKeyRoute` decides each Space event. Text fields keep Space. A focused control (an AppKit control, or an approval button, which claims Space while it holds SwiftUI focus) gets Space and is pressed. A push-to-talk press that started keeps its repeats and key up wherever focus moves, so the mic never sticks on. Otherwise Space is push-to-talk as before. Approve and Decline also take Return.
- **Typed-turn foreground binding (left by C7b #365).** The composer and an approve tap name the input they just sent. A `console/turn` whose `input_user_id` is `typed:<request_id>` or `approval:<approval_id>` for that input becomes the current request at once, since no transcription follows those inputs. Each expectation is used once and the set is bounded at 16.
- **next's last red validate test.** `tests/unit/test_plan_manifests.py` no longer lists the deleted `App/ResponseResultRouter.swift`. Its tests file stays listed.

## Scope beyond the WS-36 file list

These are named in contract §3.11 or needed to wire the feature:
`JarvisKit/Approval.swift` (new), `AppMessage.swift`, `ClientMessage.swift`; `Stores/ApprovalStore.swift` (new), `Stores/DisplayResultStore.swift`; `App/MortimerHostApp.swift` (inject the store into all five windows and bind it); `App/AppMessageRouter.swift` and `Console/TypedComposerModel.swift` (the binding hooks); `Console/AdaptiveStageView.swift` (three call sites pass `thinking`; no orb slot changed). `ConsoleProtocol`, the console action registry and `ConsoleActionCoordinator` are untouched, because approve and decline are not console actions (contract 3.1).

## Tests

- JarvisKit `ApprovalMessageTests`: decode from the RTVI envelope, validation bounds, seven-key decide, and a debug line that never holds the summary.
- MortimerHost `ApprovalStoreTests`: validation, settle notes, every result code, the timeout, session changes and `hasPendingDraft`.
- MortimerHost `C7aActivityRowTests`: placement, the activity row, labels, `SpaceKeyRoute`, the typed and approve binding, and an OCR render of an approval row with its buttons and the activity row.
- No Swift toolchain was available in this session, so CI's macOS jobs are the compile and test run.

## Open

- **Kimi's orb hold guard:** `OrbPushToTalkGuard` in `VoiceWaveView.swift` (C6's file) still keeps its own state rather than `pttOwned`. That is C6's open item and is not changed here.
- **Keyboard reach:** Tab reaches the buttons when macOS "Keyboard navigation" is on (System Settings, Keyboard). VoiceOver reaches them either way.
- **Acceptance:** VoiceOver, keyboard and the visual check run on the enhanced build from `next` (rule 15).
