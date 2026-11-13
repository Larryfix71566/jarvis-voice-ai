---
date: 2026-11-12
system: claude
rows: [WS-34]
prs: [365]
---

# C7b: typed-request composer, Command-K and the app's client header

Claude claims C7b (closure plan §4, WS-34 table) with PR #365 into `next`. It is cut from `next` at `b17842c`, after C0, C1a, C7-py and B1 merged.

## What changed

- JarvisKit: new `TypedRequest.swift` (`turn/typed`, `turn/result`); `ClientMessage.typedRequest`; `AppMessage.turnResult` (three one-line insertions beside `consoleResult`, so C4's edits to that file merge cleanly); `JarvisClient.appendTypedUserEntry`; `JarvisHTTP` sends `X-Mortimer-Client: mortimer-host` on every request (B2's "app's header line goes with C7b").
- MortimerHost: new `Console/TypedComposerModel.swift` (send, accept, reject, stale session, 10 s reply timeout that reuses the request id on resend) and `Console/TypedComposerRow.swift`; the row is the first line of `AttachmentTrayView`; a "Request" menu with Command-K that only focuses the field.
- Tests: JarvisKit `ClientMessageTests`, `AppMessageTests`, `TranscriptStreamingTests`, `ConfigAndAuthTests`; MortimerHost `TypedComposerModelTests` (new).

## Evidence

- No Swift toolchain in this session. The macOS Swift CI job (B1) on this PR is the only compiler and test run so far; the plan asks for a reviewer's local run as well.

## Scope and collisions (for §4 in the daily batch)

- Three files the first plan touched sit in other active rows' Scope and are not edited: `Console/CommandConsoleView.swift` and `Console/ConversationThreadView.swift` (WS-36, C7a), `App/AppMessageRouter.swift` (WS-35, C4). The composer reaches the tray through `.environment`, and binds to `JarvisClient` directly for `console/hello` identity and `turn/result`.
- Collision, not resolved here: `CurrentRequestArrivals` (in `ConversationThreadView.swift`) makes a `console/turn` current only after a matching `user-transcription`, which a typed turn never has (contract §2.4 rule 9). So a typed request's results arrive but are not brought to the front as the current request. The fix is an `expectTyped(UUID)` binding that accepts `input_user_id == "typed:<uuid>"` compared as a UUID. It belongs to whichever of C7a or C4 holds that file next.

## Contract gaps found

- §2.5 says "append the text to `ConversationStore`". The store is overwritten from `JarvisClient.transcript` on every publish, so the line is added to the transcript and reaches the store through the existing sink.
- `duplicate` is a listed `turn/result` code, but the bot never sends it: a repeated `request_id` gets the cached first reply.
- The contract names no client timeout; the app uses 10 s and keeps the request id for a resend within the bot's 300 s reply cache.

## Left

- Review by Kimi (the item's named reviewer), including a local `swift test` run; then Larry merges into `next`.
- The typed-turn foreground binding above.
- Next actor: Kimi (review).
