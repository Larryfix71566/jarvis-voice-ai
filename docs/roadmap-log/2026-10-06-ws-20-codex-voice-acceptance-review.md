---
date: 2026-10-06
system: codex
rows: [WS-20, WS-17, WS-09, WS-21]
prs: [169, 171, 173, 190]
---

# Voice acceptance review — 2026-10-06

Larry reported a just-completed voice test and asked which acceptance gates its logs may clear. Codex inspected the actual launchd log, a read-only conversation query and the retained native interface. This records narrow positive evidence without changing any full product-acceptance checkbox.

## Identity and evidence scope

- Production checkout and installed native bundle report `bde22bb6425c6bf36a3e0d7cf53f2785c274190d`; the active native executable was PID 32144 at the installed MortimerHost app path. Its file SHA-256 is in the payload-free proof below. The earlier legacy Xcode wrapper is also present; the UI observation selected the exact native path. This is not a claim that current main or effective provider/configuration changes are deployed.
- Voice session `41ade440-25ba-4cbe-a530-fc9c1de75ad2` ran 21:32:31–21:36:30 EDT on 2026-10-06. Live output is `logs/bot.launchd.log`; `logs/bot.log` is stale, last dated September 5.
- The independent supporting-display audit correlated 16 native inventories, actual tool events and their acknowledgements. The root query opened SQLite with `mode=ro` and `PRAGMA query_only=ON`; it read only the named session. Native observations occurred after voice disconnected and did not send another voice/model request.
- Raw transcript, database, log excerpt, accessibility strings and screenshots stay local. This repository entry contains only bounded event metadata, counts and outcomes; no credential, exact location, question, model response or research payload is copied here.

## Narrow checks passed

1. **Normal conversation retention/order/full accessible text (UI2-22 subcheck):** seven user entries and ten Mortimer entries, including greeting and short acknowledgements, are retained in the native conversation thread. All 17 full texts match the ordered database rows after whitespace normalization; five Mortimer entries exceed 160 characters. A local screenshot also shows the long 471-character reply and following 307-character reply to their ends, with their user rows and inline cards. This establishes the exercised public conversation case, not protected-turn, scroll-follow or all pixel-size cases.
2. **Requested result opens from Conversation (UI2-23 arrival subcheck):** native inventory revision 6 initially reports Conversation/no active result. Requested weather arrives at 21:32:46.882, revision 8, and becomes the selected result. A later requested research result likewise opens from Conversation at 21:35:07.264, revision 14.
3. **Research arrival preserves active selection (UI2-23 subcheck):** research arrivals at revisions 9–11 retain the selected weather result; revisions 15–16 retain the selected research result. The post-session native observation showed `arrival-notice` with Show/Dismiss while the previously selected result remained on the stage. The notice is a visual corroboration at that observation, not proof of every weather/background route.
4. **Retained inline cards and return-to-Conversation inspection (bounded UI2-23 corroboration):** the retained conversation shows one weather card and six research cards interleaved with its transcript. Read-only navigation from a result to Conversation exposed that retained history; no new provider fetch was sent. Later user interaction selected a newer result, and observer actions stopped rather than overriding it. No compare/pin/close, Output retention or unread-clear acceptance is inferred.

## Full gates still open

- **UI2-22:** the protected-content and scroll-follow behavior, remaining focus/duplicate/size cases and exact-build acceptance tail are not certified by this public session alone.
- **UI2-23:** weather requested while another result is being read, a late unrelated background completion, image behavior, compare/pin/close with Output retention and the supporting-display route remain outside this session's proved coverage. Research's no-focus pass is not substituted for the separate weather route.
- **UI2-24/25:** new Recents/voice targeting and subject/freshness reuse are not deployed in `bde22bb`; PR #173 is still changes-requested and CC7a.4 remains unimplemented. This session clears neither future increment.
- **WS-21:** every inventory reports only the built-in screen; supporting `open` and `presented` are false, and no transfer/detach/move command or `console/result` acknowledgement occurred. Queued tile counts are not external presentation. Transfer, already-showing, missing-monitor, disconnect/reconnect and conversation-on-main checks remain open.
- **Skills, automated memory and model routing:** successful ordinary voice exchanges do not establish owner-authenticated skill runtime, staged memory enablement, eligible confidential routes, subscription billing/quality or rollout. Skills runtime inventory remained unavailable during this session.

The existing full-gate checkboxes remain open. Claude/Codex can reuse this dated evidence when closing the same subrequirements, so Larry need not repeat these already-observed normal text/routing cases solely for documentation.

## Payload-free conversation proof

```json
{
  "session_id": "41ade440-25ba-4cbe-a530-fc9c1de75ad2",
  "all_17_full_rows_present_in_order": true,
  "user_rows": 7,
  "assistant_rows": 10,
  "assistant_over160": 5,
  "ax_sha256": "24c8cb31eacbf00c8a4901481ba80ad17115fe41e1cc9d689841df53709f6afe",
  "scope": "retained native accessibility content; not protected-turn or all pixel/scroll behavior acceptance",
  "full_gate_accepted": false,
  "row_range": [
    3927,
    3943
  ],
  "production_source": "bde22bb6425c6bf36a3e0d7cf53f2785c274190d",
  "native_executable_sha256": "5f3d57b7bf8507631599c992f8b0ca04382abeaa1b3add130dff6ab14c53fe30"
}
```
