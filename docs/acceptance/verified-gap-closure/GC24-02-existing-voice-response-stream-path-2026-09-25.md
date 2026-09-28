# GC24-02 — Existing live voice response stream path

**Status:** Existing source path verified with focused client and host tests;
the exact deployed Mac candidate and end-to-end live voice journey remain
unverified.

**Worktree:** `codex/isolated-20260924`  
**Base/current HEAD:** `977f50bec7b77bd7d3381d3b8f3d63fa69bd00e2`

## Verified source path

Live RTVI `bot-llm-started`, `bot-llm-text`, and `bot-llm-stopped` messages are
handled by `JarvisClient`. Text chunks update the same assistant transcript
entry ID. `AppMessageRouter` observes that transcript, updates
`ConversationStore`, and passes the entries to `ResponseResultRouter` in the
Command Console layout. `ResponseResultRouter` appends to the same
request-owned `WorkspaceResult` and supporting-display panel. This is the
selected voice response/results path; do not add another consumer for the
same voice tokens.

The new `TranscriptStreamingTests` exercise inbound RTVI frame aggregation and
confirm two chunks produce one assistant transcript entry with a stable ID.
The new MortimerHost `LiveVoiceResponseStreamTests` drives a stub RTVI
transport through `JarvisClient`, `AppMessageRouter`, and the existing
`ResponseResultRouter`, proving two chunks update one result and one panel.
Existing `ResponseResultRouterTests` also exercise incremental updates, one
result per request, bounded supporting-display panels, preserved reading
state, and explicit close behavior.

## Verification

- `CLANG_MODULE_CACHE_PATH=/private/tmp/jarvis-clang-cache SWIFTPM_MODULECACHE_OVERRIDE=/private/tmp/jarvis-swift-module-cache swift test --scratch-path /private/tmp/jarvis-jarkit-build --filter TranscriptStreamingTests` — **2 passed**.
- `CLANG_MODULE_CACHE_PATH=/private/tmp/jarvis-clang-cache SWIFTPM_MODULECACHE_OVERRIDE=/private/tmp/jarvis-swift-module-cache swift test --scratch-path /private/tmp/mortimerhost-result-tests --filter ResponseResultRouterTests` — **7 passed**.
- `CLANG_MODULE_CACHE_PATH=/private/tmp/jarvis-clang-cache SWIFTPM_MODULECACHE_OVERRIDE=/private/tmp/jarvis-swift-module-cache swift test --scratch-path /private/tmp/mortimerhost-result-tests --filter LiveVoiceResponseStreamTests` — **1 passed**.
- `git diff --check` — passed.

SwiftPM required execution outside the restricted sandbox because its nested
sandbox runner could not start inside it. Build artifacts were directed to
`/private/tmp`.

## Limits and next proof

The new stub-transport test verifies the complete native source-to-result
path, but does not use the running backend or installed Mac candidate.
Complete the live candidate journey before claiming deployment acceptance.
The generic shared-execution `ModelExecutionEvent` stream still has no
production native result consumer; only inventoried non-voice callers that
need streaming should be connected to the existing result owner, with policy
enforcement and request identity intact.
