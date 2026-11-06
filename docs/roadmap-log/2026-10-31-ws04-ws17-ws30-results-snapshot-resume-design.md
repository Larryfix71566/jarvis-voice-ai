---
date: 2026-10-31
system: codex
rows: [WS-04, WS-17, WS-30]
prs: [290]
---

# WS-04 / WS-17 / WS-30 R3.23 results snapshot/resume implementation claim

Date: 2026-10-31 UTC

Status: offline source independently accepted at `b4ae7740719f45e4dd81ad3f4917c789c608f57c`; local/unpublished; docs reconciliation pending review.

## Accepted design, adoption and ownership check

Prepared on branch `docs/ws04-ws17-ws30-results-snapshot-design-20261031` from exact accepted D3 worktree commit `249a4e6c45cfe1ae2ffcc5c7fae8d9978df51a16` (tree `3c057960776f0245bba7ff55d41a88a64c9ee561`). The accepted D3 worktree remains untouched. The independent design was accepted at `92dbcc5a7d95f3f89f4c2b7312edd2bc1a9bd456` (tree `5853de654f236a3d07e636f751d0250f848f964d`); the coordinator adopted the exact 15-path source claim on `codex/ws04-ws17-ws30-results-snapshot-resume-20261031`. Fresh GitHub connector evidence reports PR #290 open/draft/unmerged at `46e29c26e6a4262aa47dfa96615f3a91cc990572`; search found no competing results snapshot/resume claim or PR. Direct Git fetch failed due DNS; remote evidence is connector-provided, not a locally refreshed ref. Local collision checks found the two WS-17 projector paths absent and the other 13 paths already in their respective WS-04/WS-30 claims; the coordinator adoption amends those claims only for this slice.

## Observed implementation boundary

Before R3.23 implementation, the Python protocol reserved `results.snapshot` and `results.resume` but marked them unavailable, and the service returned `unavailable/operation_unavailable`; the Swift checked DTO/client supported only `session.status` and the three voice operations. The accepted R3.20 app remains disconnected and synthetic-only. Mac `WorkspaceStore` has in-memory results and an inventory revision, but not a per-item revision/event journal; a result can change under stable UUID. No reviewed native-to-Python production source bridge exists. The existing phone plan requires a host-selected bounded ordinary-result collection, trusted source identity/revision/classification, and denial of protected, unknown or unprovenanced content. UI labels and the local `isProtectedLocal` convenience property are not authority.

## Proposal summary

The accepted R3.23 design specifies the new synthetic `PhoneResultCollectionGrantV1` as trusted test-constructed authority, distinct from existing `read` scope. It binds the server identities and a maximum-25 source-ID allowlist. Coherent preparation checks compare captured selected-source versions; committed historical pages are replayable across later ordinary edits after rechecking current binding, grant, membership, source identity and classification. Excluded-source mutations do not invalidate them. Client masking is limited to locally observed logout/foreground loss or a received reset/denial; offline inert screens may remain and emitted bytes cannot be recalled. Provider callbacks remain outside locks. The exact envelope, UUID/integer/string/cursor grammar, allowlisted status/reason mappings, complete snapshot overflow behavior, page high-water/`has_more`/repeat semantics, journal and cursor bounds, visibility-scoped metadata, no-tombstone reset rule, release-ack receipt point, cancellation drain and observable-event-based phone masking (with offline inert stale screens allowed, no push/polling/remote erasure) are frozen in the canonical remote plan. Protected/unselected activity cannot change visible counters or reveal IDs; a previously visible item becoming protected invalidates the collection epoch and masks cached bytes.

The adopted test scope includes `tests/unit/test_phone_remote_authority_service.py` as the actual-process service/authority harness, alongside the WS-17 projector, WS-04 protocol/service and WS-30 checked Swift client/preview tests listed below. Existing WS-04/WS-30 Scope/Where records are amended only for this coordinated slice. The immutable legacy 70-vector oracle remains at zero exact R3.23 replays; no facade-conformance claim is made.

## Adopted source paths

- **WS-17:** `jarvis/bot/phone_remote_results.py` (new), `tests/unit/test_phone_remote_results.py` (new).
- **WS-04:** `jarvis/bot/phone_remote_protocol.py`, `jarvis/bot/phone_remote_service.py`, `tests/unit/test_phone_remote_protocol.py`, `tests/unit/test_phone_remote_service.py`, `tests/unit/test_phone_remote_authority_service.py`.
- **WS-30:** `ios/MortimerPhoneCore/Sources/MortimerPhoneCore/PhoneRemoteOperationsV1.swift`, `ios/MortimerPhoneCore/Sources/MortimerPhoneCore/PhoneAppPreviewModel.swift`, `ios/MortimerPhoneApp/MortimerPhoneApp/PhonePreviewFakeTransport.swift`, `ios/MortimerPhoneApp/MortimerPhoneApp/PhonePreviewRootView.swift`, `ios/MortimerPhoneCore/Tests/MortimerPhoneCoreTests/PhoneRemoteOperationsV1Tests.swift`, `ios/MortimerPhoneCore/Tests/MortimerPhoneCoreTests/PhoneRemoteOperationsClientTests.swift`, `ios/MortimerPhoneCore/Tests/MortimerPhoneCoreTests/PhoneAppPreviewModelTests.swift`, and `ios/MortimerPhoneApp/MortimerPhoneAppTests/PhonePreviewUITests.swift`.

The adopted source is accepted as a bounded offline synthetic refinement. Existing frozen S0 files, owner/channel, `WorkspaceStore`, `ResponseResultRouter`, JarvisKit, production bridge, real user data, transport, signing, install and live service remain excluded. The accepted R3.21 audit is a separate branch and is not integrated into this candidate.

## Independent source acceptance receipt (2026-10-31)

Independent source review ACCEPTED exact commit `b4ae7740719f45e4dd81ad3f4917c789c608f57c` (tree `88a201a809f1310c950032ee04d199fa63deeec6`). Effective R3.23 scope is 16 source/test paths: the original 15 coordinated WS-04/WS-17/WS-30 paths plus the adopted ASGI test-only amendment. Review-driven fixes included canonical cursors in the app fake and raw JSON fixture, retiring uncommitted cursors after truncated-history snapshots while preserving committed receipts, and preventing finalization after failed preparation. The reviewer used unittest discovery with a subtest-counting runner and verified 257 phone tests and 360 subtests with zero skips; the 39-test actual-process `ResourceWarning`-as-error run is included in that total. The reviewer separately completed all 58 Swift package tests and an unsigned generic app/UI-test bundle build including the snapshot→resume fake-transport test. Author validation independently passed 257 tests/360 subtests, the 39-test warning-as-error process run, Core compile/test-source typecheck, app fake-transport checked snapshot→resume round trip, roadmap check (0 errors/0 warnings) and diff checks. The author’s SwiftPM test launch was blocked before test execution by the sandbox’s denial writing the user-specific Clang module-cache directory; reviewer execution completed through the normal approved Mac workflow. Counts are per-command and not additive.

The 58 Swift tests and unsigned app/UI bundle build passed in review; UI execution, rendered visuals and usability remain unverified. The source remains local/unpublished and has no exact-head CI. Public PR #290 remains represented here by its prior published base `46e29c26e6a4262aa47dfa96615f3a91cc990572` (tree `2d4ceb0ad7817aebe04980c2a6983e621cfb45e5`); Validate #543 failed on that published head. No R3.21 audit paths are included. The frozen 70-vector oracle remains unchanged with zero exact R3.23 executions; full facade conformance, D3 completion/recovery, production bridge/Keychain/signing, live transport and release acceptance remain open.
