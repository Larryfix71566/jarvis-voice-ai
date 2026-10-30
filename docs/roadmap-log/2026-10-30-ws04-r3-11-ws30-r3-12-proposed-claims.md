---
date: 2026-10-30
system: codex
rows: [WS-04, WS-30]
prs: [290]
---

# WS-04 R3.11 and WS-30 R3.12 offline claim proposals — revised 2026-10-30

**Author:** Codex; exact model not recorded for this documentation-only revision. **State:** R3.11 one-test claim and R3.12 Swift claim are adopted locally in separate lanes. R3.11 is authored by GPT-6 Luna and awaits its existing WS-04 nonauthor reviewer. R3.12 is authored by GPT-6 Luna and awaits exact-source review by reviewer `01a18584-92e2-7511-aca8-983bb3f230ef`. No public write is included.

## Base and evidence

The verified published PR #290 head is `cbba8645ceaa7ad81e83b8dce5af3f03d8ce00c5`, tree `188cb06814adc03c0f17b1165c1f856189e205ef`, parent `628d743efa6b23b3341840594b176f9562bcc154`. Exact-head CI run #538 (`41095632875`) passed 7,322 unit tests, 197 integration tests, 13 evals and all other checks. This is offline evidence only.

The local git object database lacks the remote head commit object. This candidate is locally parented to `9d096b1e736d6db59a9b2ab709e08200e64058de`, whose tree is exactly `188cb06814adc03c0f17b1165c1f856189e205ef`; the local parent identity is not represented as the remote PR commit. Read-only collision review found only PR #290 open and the proposed source paths absent from the verified tree.

The frozen fixture hash is `1cf1f8a377438a5fe04d0517535eee86166c48af6decb030da249b9ae5083950`; unchanged legacy adapter hash is `28936b4b3a00ed0bc6af4114493d6bbeffe1d40d66e6968221e33b41d9615720`. Both remain read-only.

## WS-04 R3.11 — adopted single combined invariant

Parent adopted the exact one-test claim locally on 2026-10-30. Only `tests/unit/test_phone_admission_boundary.py` is in scope. It creates sessions A/B, offers a voice peer for A to populate the service receipt ledger, queues two synthetic output canaries, snapshots raw SQLite, signs out A, and restores the raw snapshot twice without preparation hooks. After each restore it replays A’s exact request and attempts to drain one queued item: no cached success/SDP, no emitted bytes; session B must still pass an authorized `session.status`. B is only a status control, not a second owner voice lease.

Tested observations: exact denied/not_authorized/empty response to replay; output drain returns no data; queue shrinks one item per restore; B returns ok/none with readiness ready; final explicit tick closes the stale A peer. No private ledger/final DB state, no artificial hook, no fixture mutation. `python3.12 -m unittest tests.unit.test_phone_admission_boundary` passed 1 test. This scenario is not a fixture vector or sensitivity pass. It maps/passes zero of 70; R3.5/phone §13 remain open. Existing WS-04 nonauthor reviewer remains reviewer; parent is sole coordinator.

## WS-30 R3.12 — independently accepted bounded design

Reviewer accepted this design independently of R3.11. The parent adopted it as a local source claim on 2026-10-30; GPT-6 Luna authored initial Swift source commit `38ffbc739950e670a707c24b3cdf12449f56b0ea` (29/29 tests); final byte-exact request-ID correlation commit `c018e299b79a32417c448cfbacedcc9e1208f64e` passes 30/30 Swift package tests (15 new, 15 existing). Reviewer `01a18584-92e2-7511-aca8-983bb3f230ef` is assigned for exact-source review. Source awaits independent exact-source review before any publication.

Exact new paths:

- `ios/MortimerPhoneCore/Sources/MortimerPhoneCore/PhoneRemoteOperationsV1.swift`
- `ios/MortimerPhoneCore/Tests/MortimerPhoneCoreTests/FakePhoneRemoteOperationsHost.swift`
- `ios/MortimerPhoneCore/Tests/MortimerPhoneCoreTests/PhoneRemoteOperationsV1Tests.swift`

Foundation DTOs and fake-host tests cover only `session.status`, `voice.offer`, `voice.update` and `voice.end` per R3.9. Preserve exact request/response fields, success payloads, `{}` error payloads, fixed R3.9 statuses/reasons, nonempty request ID (maximum 128 UTF-8 bytes), 1 MiB request cap, depth 64, duplicate-key rejection, and closed key/type/value rules at a checked JSON boundary. Do not assume synthesized `Codable` alone enforces these constraints. No device, app target, OS minimum, signing, transport, authentication, microphone, result/call, or live assumptions.

Author is GPT-6 Luna, with reviewer `01a18584-92e2-7511-aca8-983bb3f230ef`; parent remains sole coordinator. Source claim and checks are detailed in the canonical phone-access plan. Keep this lane separate from WS-04.

## Decisions and gates retained

Neither offline slice resolves production paired-device verifier, protected anchor, restore hook, service construction, route/listener, private identity/TLS/tunnel, Mac availability, content grants, voice readiness, calls, installation, device selection, signing or live access. No source change, publication, merge or activation is included.

## WS-30 R3.13 operation-client wrapper — proposal and implementation receipt

**State:** parent coordinator adopted the reviewed proposal and authorized this bounded offline implementation on 2026-10-30. Verified public PR #290 base: `ee510cfc8fbfd0973f1a7b7f83699f2ea11738f5`, tree `7c628d3266e9912fcee3ec57827770bc16859079`. Final source commit `4e2507af17be12a40d6afdf07ad8a54f9cc37716` is local on isolated branch `codex/ws04-phone-remote-asgi-combined-20261030`; independent exact-source review is pending. It is not published or activated.

Proposed exact source additions are `ios/MortimerPhoneCore/Sources/MortimerPhoneCore/PhoneRemoteOperationsClient.swift` and `ios/MortimerPhoneCore/Tests/MortimerPhoneCoreTests/PhoneRemoteOperationsClientTests.swift`. Proposed author is GPT-6 Luna; proposed nonauthor reviewer is `01a18584-92e2-7511-aca8-983bb3f230ef`; parent remains sole coordinator. Existing paths/claims are preserved, and no collisions were found in the current checkout or fresh PR view; recheck before implementation.

The client would use injected async byte transport and the checked R3.12 `PhoneRemoteOperationsJSON` boundary, with deterministic fake transport only. It would bind to one injected transport/session instance and local generation, generate fresh UUID request IDs, and compare response IDs byte-for-byte using UTF-8. Permit one owned exchange at a time with no queue; reject sends while busy, draining, reconnecting, or ended. A precancelled request dispatches no bytes. Invalidate the local generation before awaiting an interrupted/closed exchange; reject reconnect until actual drain completion, then require explicit reconnect with a new ID. A late reply after invalidation neither changes state nor reports success. Never automatically replay `voice.offer`, `voice.update`, or `voice.end` after uncertain completion. Keep ownership of started work through actual completion despite caller cancellation; no detached work or early slot release. A stuck injected dependency leaves the client pending/draining without a timeout promise. Use only existing state-machine actions/status mappings; do not invent transitions or fabricate server status for local failures. `voice.end` does not imply terminal session closure. Tests would use controllable continuations/barriers (no timing sleeps) to cover all four checked exchanges, simultaneous sends, precancel, interruption/close during dispatch, reconnect during/after drain, late responses, no replay, exact-byte correlation, malformed replies, and client-instance isolation. If existing APIs cannot express these semantics, stop for a narrow reviewed API amendment rather than editing unclaimed paths.

The proposal itself made no source changes. The adopted implementation receipt below records the two authorized source additions. No sockets, URLSession, app, production construction, credentials, microphone, live access, workflow, frozen fixture, or harness changes are included. No new device/security decisions are needed for this test-only slice; all production transport/authentication/anchor/device/signing/readiness/call/install/live gates remain open.

### R3.13 implementation receipt (2026-10-30)

GPT-6 Luna implemented only the two claimed Swift source/test paths in final local commit `4e2507af17be12a40d6afdf07ad8a54f9cc37716` (tree `2126525b4d48b864b3d6654aa4ea891e6b5d16d8`). `swift test --package-path ios/MortimerPhoneCore` passed 40/40 (10 new, 30 pre-existing). The new tests cover all four checked exchanges, single-flight sends, pre-cancel with zero dispatch, cancellation/close/interruption drain, stale responses, repeated explicit reconnect with fresh IDs and no automatic effect replay, invalid requests, exact response-ID matching, isolated clients, and cancellation-gate linearization around encoding/dispatch/publication. `git diff --check` and `python3 scripts/check_roadmap.py --main github/main` pass. Nonauthor source review remains required before publication.
