---
date: 2026-10-31
system: codex
rows: [WS-04]
prs: [290]
---

# WS-04 R3.17 service/process composition source claim

**State:** design review ACCEPTED exact `d932e900f503ac118ff1d9900364a884f1c2bed0` (tree `bb953601e15c9bd45833d226a7eef038281f3acc`); the coordinator adopted the exact six-file source claim on 2026-10-31. Independent source review ACCEPTED final source candidate `2eb9412849aafb63dbcdb67c445a702d07233850` (tree `6171cbbf9a49a7d5a70f9fe176304b2a0385b0e4`). The source and this documentation receipt remain local and unpublished; no merge or production/live acceptance is claimed.

**Base:** public PR #290 was read-only verified open/draft/unmerged at `2e53f5aae66c67a19334c593b05b397987b7ab72`, tree `1e798d6db18d52a19b3f42358ba025839ecc6ee3`. Exact-head Validate #542, Sandbox #720 and Knowledge Base #724 passed; the accompanying run reported 7,360 unit tests, 37 skipped and 395 subtests, 197 integration tests and 13 evaluations. This local documentation branch begins at a commit whose tree matches that published tree.

**Owner/reviewer:** WS-04/Codex. Author: GPT-6 Luna. Nonauthor reviewer: `01a18584-92e2-7511-aca8-983bb3f230ef`. The coordinator-adopted claim uses Larry's one-final-merge exception and remains subject to independent exact-source review. Adoption grants no publication, merge, production, or live authority.

**Collision check at adoption:** current PR #290 changed-file inspection confirmed the five existing source paths are in this same WS-04 integration; repository-wide open-PR search returned only PR #290, so no separate open PR conflicts. Four paths (owner, process tests, channel and channel tests) were included in R3.16; `phone_remote_service.py` is in this PR but its composition was explicitly excluded. The new `tests/unit/test_phone_remote_authority_service.py` path is absent from the index and local history. Refresh refs and ownership before integration.

**Adopted source scope (active locally, not published):**

1. `macos/MortimerHost/Sources/PhoneRemoteAuthority/PhoneRemoteAuthorityOwner.swift`
2. `macos/MortimerHost/Tests/PhoneRemoteAuthorityTests/PhoneRemoteAuthorityProcessTests.swift`
3. `jarvis/bot/phone_remote_authority_channel.py`
4. `jarvis/bot/phone_remote_service.py`
5. `tests/unit/test_phone_remote_authority_channel.py`
6. `tests/unit/test_phone_remote_authority_service.py` (new)

The adopted architecture, closed v2 envelope and operation map, exact grant phases, single child-thread/ASGI handoff, closed owner-thread store entrypoints, release-ack semantics, terminal failure latch, bounded busy-rejection test, and explicitly deferred interleavings are in R3.17 of `docs/plans/MORTIMER_REMOTE_ACCESS_PLAN.md`. The ordinary `PhoneRemoteService` constructor remains exact fake-only; only the private controlled-child capability is allowed for this offline channel-backed composition. The implementation must keep the same service policy and one source of mutable peer/receipt/lease/ledger state in the trusted Python child. It does not edit the store, S0 core/fixture, `server.py`, app target, real transport, signing, Keychain, enrollment, restore tooling, credentials or runtime settings.

**Acceptance boundary:** source implementation and independent source review are complete only for the six claimed paths and accepted offline behavior. It claims no full conformance-vector result, production Keychain behavior, signed packaging, startup, listener, live service, device access or phone-call acceptance. Production setup remains separately gated.

**Review revision (2026-10-31):** independent design review requested bounded clarification of per-call channel contexts, exact v2 framing/phases, terminal cleanup without a second reader, release-ack visibility and child-thread/SQLite ownership. Those clarifications are incorporated in R3.17. The design was accepted and adopted for the bounded source claim; source paths and external production gates are unchanged.

**Second review revision (2026-10-31):** narrowed the source proposal to a single serialized child worker; added closed channel-backed owner-thread login/ticket/signout/security-mutation entrypoints; corrected the mandatory anchor-read accounting to use the mapped store method’s own `_check_pair()` read; added the post-ticket/pre-preparation authorization call; and explicitly deferred overlapping service/revocation/replacement interleaving coverage. The design remains adopted for this bounded source claim.

The test organization keeps pure v2 protocol/operation-context tests that do not need the native executable in an ungated test class. Only true native process-launch tests require `PHONE_REMOTE_AUTHORITY_OWNER_BIN`, with a precise skip reason if absent; this avoids hiding runnable protocol tests behind binary setup.

**Third review revision (2026-10-31):** added a narrowly scoped nonterminal `StoreDenied` path only for exact read-only `service.authorize` calls, with pre-grant denials requiring no IPC and post-stable-read denials requiring release acknowledgement. Added actual-process A-signout/A-denial/B-fresh-ticket same-child success and lost-ack global-fence variants. All other terminal failures stay fail-closed; the design remains adopted.

**Adoption record:** parent coordinator adopted the exact six-file R3.17 source scope after design ACCEPT. Branch `codex/ws04-phone-authority-channel-20261030`; published base PR #290 `2e53f5aae66c67a19334c593b05b397987b7ab72`/tree `1e798d6db18d52a19b3f42358ba025839ecc6ee3`. The local adoption commit preceded source implementation. This historical collision check is not current integration evidence; refresh refs and ownership before integration.

**Source acceptance receipt (2026-10-31):** independent review ACCEPTED `2eb9412849aafb63dbcdb67c445a702d07233850` (tree `6171cbbf9a49a7d5a70f9fe176304b2a0385b0e4`). The six-path claim is recorded above; five claimed source/test files differ from the published-base tree, while `PhoneRemoteAuthorityProcessTests.swift` is byte-identical to the base. Author-run focused pytest across `tests/unit/test_phone_remote_authority_service.py`, `tests/unit/test_phone_remote_authority_channel.py`, `tests/unit/test_phone_remote_service.py`, `tests/unit/test_phone_remote_asgi.py`, and `tests/unit/test_phone_admission_contract.py` passed 115 tests and 209 subtests. The independent reviewer reported 164 pytest tests and 254 subtests passing across eight modules; this is a separate reviewer aggregate and is not added to the author's count. The lost-output-preflight regression was mutation-checked: removing the centralized closed-channel fence caused its immediate-fence assertion to fail, and the source was restored before the final run. Focused Swift `PhoneRemoteAuthorityTests|DisplayPlacementPolicyTests|VoicePresentationStateTests` passed 19 tests (2 authority, 10 display, 7 voice) on the final candidate. The Swift owner source was unchanged by the final test-only correction; the independent review relied on prior 19-test/build evidence for byte-identical Swift source, while the author reran the same 19-test filter on the final candidate. The full repository pytest suite and all Swift tests were not run. These checks cover the bounded fully serialized offline actual-service/process composition, including the actual service peer/receipt/lease/media/output paths through the child process; overlapping service/revocation/replacement interleavings remain explicitly deferred. No production Keychain, signing/packaging, server construction, credentials, install, listener, live service, device, phone-call or D3 restore acceptance is established. The R3.17 source and this receipt remain local and unpublished; exact-head CI for this local candidate is not available. R3.16 is already published in the base PR #290, whose exact-head CI passed as recorded above.
