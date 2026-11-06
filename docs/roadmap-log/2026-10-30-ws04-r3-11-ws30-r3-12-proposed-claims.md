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

## Starting security design defaults — approved in principle (2026-10-30)

Larry approved separate device-bound enrollment, fresh user Face ID/passcode verification, manual user-started first calls while the Mac is awake, fail-closed handling for absent keys/uncertain restore, and a restricted private phone service with authenticated TLS and no admin interface. This is design approval only; no keys, enrollment, service configuration, network path, route/listener, signing, installation, or live test was performed.

Larry subsequently answered “Yes to all” on the direct-only-versus-DERP and locked-Mac-reachability choices. The approved design intent is encrypted DERP fallback when direct connectivity fails and Mac reachability while locked. Whether a locked Mac may accept a new authenticated session or only sustain one established earlier remains for D1/D2 technical review; do not narrow the approval to existing sessions only. D2 should evaluate supporting new authenticated sessions after first unlock through a signed-in user Data Protection Keychain process, subject to review of exact accessibility, local verification and signing behavior. Pending review, access before first unlock after boot remains fail-closed. This does not prove Keychain persistence, tunnel behavior, or a running service, and does not decide sleep/wake/auto-start/restart behavior.

Required technical reviews remain: D1 exact device-bound enrollment, verification/reauthentication and session creation; D2 exact Keychain accessibility, typed locked/denied/missing failures, verified writes/readback, serialization with protected-anchor/SQLite transitions, and backup/loss/whole-host recovery; D3 WS-17 inventory of every supported restore/downgrade entry point, including generated `ROLLBACK.sh --restore-db` and related restore paths, plus verification of `phone_remote_restore_v1`. `ThisDeviceOnly` is not rollback protection; no restore hook is yet verified, so remote access stays disabled until coverage is established. Adopted R3.15 is the next useful pure offline verifier slice; it does not resolve these gates. No further code-only production wiring is ready until D1/D2/D3 and atomic challenge consumption/session creation are reviewed. The iOS deployment baseline remains undecided pending iPadOS test requirements. No device model/OS details were written into repository docs. No key, enrollment, network/service configuration, installation, or live behavior was changed or validated.

## WS-04 R3.15 native authentication-proof codec — adopted offline source claim (2026-10-30)

Coordinator adopted the bounded offline source claim on 2026-10-30. Author: GPT-6 Luna; independent reviewer: `01a18584-92e2-7511-aca8-983bb3f230ef`. Exact additions: `jarvis/bot/phone_remote_auth_proof.py` and `tests/unit/test_phone_remote_auth_proof.py`. No other source, dependency, route, protocol, store, service, client, fixture, or ownership path is in scope.

Read-only collision evidence: connected GitHub code search found no default-branch match for `phone_remote_auth_proof`; open-PR searches for that filename, “Mortimer phone auth proof,” and “P-256 phone authentication” returned no matches; current PR #290's file list excludes both paths. Local current-branch and `github/main` tree lookups also found neither path. Full local all-ref history inspection was incomplete because object `628d743efa6b23b3341840594b176f9562bcc154` is missing; recheck all branches/path claims before adoption rather than assuming no collision.

The pure module would parse one closed UTF-8 JSON proof (maximum 4096 bytes) for protocol `mortimer.phone-auth-proof.v1` and purpose `phone.session.create`; enforce exact fields/types and strict duplicate/nonfinite/depth/size/base64url rejection; then verify a domain-separated, fixed-order, length-prefixed binary transcript. It binds a 16-byte challenge ID, 32-byte nonce, service ID, host ID, enrolled key ID, current authority generation, and signed expiration. The exact 26-byte domain separator, fixed field/integer encoding, ECDSA P-256/SHA-256 transcript hashing, canonical DER and scalar bounds, frozen expectation/time contract, and fixed error mapping are specified in the canonical plan under R3.15. A pure verifier returns only a fixed internal result; it does not consume challenges, mint sessions, or emit a phone-facing response. Owner/device/grant/scope remain server-derived.

Adversarial tests must use actual cryptography with ephemeral test keys, an independent literal transcript oracle, exact JSON ordering/whitespace behavior, two-key identity separation, valid high-/low-S acceptance, and both proof-only versus coordinated expected-context mutations for every dynamic signed field. Also cover escaped duplicate keys, invalid caller time/expectation, duplicate/unknown/missing/wrong/deep/oversized/nonfinite JSON, noncanonical base64url, invalid keys/curves/DER/scalars, and expiry boundary. No always-true verifier. Signature possession alone cannot prove Secure Enclave storage or fresh local biometric/user-presence; the app must gate signing locally. A later service must consume the challenge ID exactly once in the same serialized authority decision that rechecks current key/owner/device/generation and creates the session; signature/hash is not the replay key.

`requirements-lock.txt` lists `cryptography==50.0.0`, but `requirements.txt` is unpinned and the lock entry does not prove CI/runtime resolution. This worktree's Python 3.12.13 cannot import the package, so no verifier API or tests ran here and no installation was attempted. Parent verified a separate authorized execution environment with Python 3.12.14 and cryptography 50.0.0 installed; before test execution, transfer the exact candidate, verify artifact hashes/runtime versions, then execute tests there. Do not install or change workflows. D1 pairing/auth/session semantics, D2 Keychain/locked-session and protected-anchor details, and D3 WS-17 restore coverage remain open technical reviews; no production wiring is ready before those reviews and atomic challenge-consumption design. This source claim creates no key or credential and authorizes no enrollment, service, network, installation, or live use.

### R3.15 source candidate receipt (2026-10-30)

**Historical attempt, superseded:** candidate `dcfba65c58259c04acdfd1d11c51ac28f593c2f0` (tree `02ed2914a713ca2a5c4b94cb5ecdc0a7ce2dd3ce`) had 19 test methods. Local Python 3.12.13 could not import `cryptography`, so that test run did not execute. Its `git diff --check` was a working-tree check, not committed-range evidence. This candidate is not the accepted source or final validation receipt.

**Final accepted receipt:** source candidate `7406dc8e1a2af89cafac71418ca89dd27941d781` (tree `075e12aea1bc7736b56eeedcdc145c4da3cf78de`) changes only `jarvis/bot/phone_remote_auth_proof.py` and `tests/unit/test_phone_remote_auth_proof.py`. SHA-256 values are `c7749602fc574c5d8b48a41b36da8ebf4ea01029e2727fd2de3cdcb010310bed` and `80e6b4d6074d403a90b216016228682b9eb2ac54c7545459af6733e28780e0d6`, respectively. Parent verified `python3.12 -m unittest tests.unit.test_phone_remote_auth_proof`: 20 tests passed, 0 failures, in 0.047 seconds on Python 3.12.14, cryptography 50.0.0, OpenSSL 4.0.1. Independent review ACCEPTED the exact source, and 327 independent native probes against the same module passed, including crypto/key substitution, high-S signatures, and result redaction. `py_compile`, committed-range `git diff --check`, and roadmap validation also passed. This is synthetic pure-verifier evidence only; no production authentication, enrollment, challenge consumption, or session issuance is established. The source is local and unpublished; nothing was merged, enrolled, configured, or activated.


### Combined local review checkpoint (2026-10-30)

The accepted R3.15 source hashes and accepted WS-17 rollback-guard source hashes are preserved together on `codex/ws17-r315-combined-20261030`, based on current published PR #290 head `838bac7d76dd282f21ad019dd9234b693c612fc3`. The combined source checkpoint is `6eaf6214e02bd8c6f9e3384effb7737f2266302a` (tree `626af61eb1075bd89b83bbf7522d5d70ec507ec2`). Their claims remain separate. Combined focused pytest run passed 107 tests and 71 subtests using Python 3.12.13, cryptography 50.0.0, OpenSSL 4.0.1. The 327 independent native probes apply to the proof verifier alone; they were not rerun against the combined candidate. No publication, merge, authentication, challenge consumption, session creation, enrollment, endpoint, restore, or deployment occurred.
