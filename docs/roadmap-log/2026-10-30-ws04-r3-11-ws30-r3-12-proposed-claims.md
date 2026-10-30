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
