---
date: 2026-11-01
system: kimi
rows: [WS-04]
prs: [290, 291]
---

# WS-04 — Kimi independent phone-admission-core review, 2026-11-01

System: Kimi. Session: `conv-4bed9bc9306ce9544cad5e66`.
Workstream: WS-04. Branch: `kimi/ws04-phone-admission-review-20261101`.

## Verdict and exact binding

**APPROVE — bounded, source-only. [certain]** Kimi independently reviewed the deterministic offline admission core in draft PR #290 at exact head `85bc736eff6311943bce77dfe769b683ec9d944d`. There are **zero blocker, should-fix, or nit findings** within the registered review scope. Codex retains implementation ownership; Kimi changed no implementation, test, or fixture input.

This is not approval of the whole #290 diff, Stage 1.1, production integration, a route, persistent authority, a phone UI/device path, deployment, or live acceptance. The implementation remains draft and unmerged. A changed #290 head requires a fresh exact-source binding.

Review evidence branch: `kimi/ws04-phone-admission-review-20261101`. Review claim: merged PR #291, merge commit `78d874a4a87962daafb7b6a19ffe9c95d84b8012`. Before publication, GitHub still reported #290 open/draft at the exact reviewed head.

After merging that claim into the review branch, `git diff --exit-code 85bc736eff6311943bce77dfe769b683ec9d944d -- <five-review-inputs>` passed. The reviewed bytes are:

| Input | SHA-256 |
| --- | --- |
| `jarvis/bot/phone_admission.py` | `03f84b523ed0722378c77064cbc390d3bf994bae32c5f9a640f86bf556a8e117` |
| `tests/unit/test_phone_admission.py` | `620556c8a0193e4983b39f4c59224c0d60173d8c53cede89516594aec877851e` |
| `tests/unit/test_phone_admission_boundary.py` | `30a770326e7e1bb0ec799ddc5cf627665dadce56d55bbeee03bc89e741498398` |
| `tests/unit/test_phone_admission_contract.py` | `28936b4b3a00ed0bc6af4114493d6bbeffe1d40d66e6968221e33b41d9615720` |
| `tests/fixtures/phone_admission_contract/v1.json` | `1cf1f8a377438a5fe04d0517535eee86166c48af6decb030da249b9ae5083950` |

## Executed evidence

The project virtual environment ran:

```bash
python -m pytest \
  tests/unit/test_phone_admission.py \
  tests/unit/test_phone_admission_boundary.py \
  tests/unit/test_phone_admission_contract.py -q
```

Result: **12 tests passed, 135 subtests passed, zero failures/skips**. This includes the 70 S0 vectors, seven sensitivity cases, three isolation probes, focused identity/feature boundary tests, and the scoped signout/raw-restore boundary test.

Kimi also derived and ran an independent inline synthetic probe harness. Its final complete run reported **439 assertions passed**. Coverage included:

- exact `ClientIdentity` type and nonempty principal validation, wrong-owner denial for issue/consume/command/output/login, and legal positive controls;
- caller-supplied owner/grant/session/digest/peer mismatches, one-use replay, exact TTL expiry, update-ticket peer binding, restart invalidation, and no consumption on denial;
- session revocation across repeated stale restores, isolation of unrelated sessions/grants, and session-ID reuse under another grant without old peer/ticket authority;
- explicit feature-off refusal before authority work, with complete state unchanged;
- closed action/protocol and output classification/provenance/source/sink rules, including provider-input refusal;
- malformed shapes/types, NaN/infinity, unknown constants, and caller-content canaries: fixed two-field content-free responses, no escaped exception, and no reflected canary;
- constructor/view deep-copy isolation and caller event immutability on accepted and denied operations;
- static import/call inspection plus runtime blocking of file open, imports, sockets, subprocesses, and process execution while a legal issue/consume/command/output/snapshot/restore lifecycle passed.

Two initial harness drafts stopped on incorrect probe expectations: one did not account for an already closed peer on the second repeated-restore iteration, and two custom consume events omitted their issued digest. Kimi corrected only those inline probe inputs/expectations and reran the complete harness. These were not implementation failures or source changes; the final 439-assertion result above is the verdict evidence.

### Documented restore boundary retained

The existing plan records that, without revocation, restoring and reusing an identical session/grant/owner tuple can retain an unexpired unused ticket in this synthetic model. The independent harness reproduced that exact documented behavior. This is **not a new finding** and must not be misread as general restore safety. The later durable integration still needs its non-rollbackable login-incarnation fence and exact integration evidence. Session revocation fences, cross-grant reuse fencing, restart invalidation, and full-host rollback limitations remain distinct.

## OWASP Top 10 coverage

Risk summary for this bounded source review: **RED High 0 | YELLOW Medium 0 | GREEN Low 0 | PASS 10**. Every category below was checked; “pass” is limited to the reviewed core and does not certify unreviewed production surfaces.

| Category | Result | Evidence and scope limit |
| --- | --- | --- |
| A01 — Broken Access Control | **PASS — no finding [certain]** | Server-derived binding/owner checks at `jarvis/bot/phone_admission.py:150-169`, `:236-246`, and `:283-372`; scope checks, replay/expiry, revocation, stale restore, and cross-grant reuse probes passed. Administrative events are explicitly trusted fixture controls (`:9`, `:373-482`), not reviewed public endpoints. |
| A02 — Cryptographic Failures | **PASS — no finding within scope [certain]** | No credential, cryptographic operation, secret store, or persistence exists in this core. Ticket cryptography and transport protection are expressly outside the synthetic proof and were not certified. |
| A03 — Injection | **PASS — no finding [certain]** | Closed event schemas (`:20-44`, `:215-234`), fixed symbolic actions/sinks, no SQL/template/shell/eval/exec path, and hostile malformed/content-canary probes passed. No renderer or query layer was reviewed. |
| A04 — Insecure Design | **PASS — no new finding [certain]** | Explicit feature gate, one-use/expiring tickets, authority fences, fail-closed uncertainty, and content admission were exercised. The already documented identical-tuple restore limitation remains an integration gate; production concurrency/rate limiting is not implemented or claimed by this pure serial model. |
| A05 — Security Misconfiguration | **PASS — no finding within scope [certain]** | `feature_enabled` requires an explicit bool (`:62-66`); feature-off denies before `_step` (`:248-262`); responses contain only `admitted` and a fixed reason. Deployment flags, listeners, headers, and service configuration were not reviewed. |
| A06 — Vulnerable and Outdated Components | **PASS — no new component finding; dependency audit not performed** | The core imports only `copy`, `math`, and the existing `ClientIdentity` boundary (`:11-16`). No new third-party component is introduced by this file. Kimi did not run a repository dependency/CVE audit, so this is not a repo-wide A06 verdict. |
| A07 — Identification and Authentication Failures | **PASS — no finding at the policy boundary [certain]** | Missing, wrong-type, blank, and wrong-owner identities deny; valid-owner positive controls pass (`:236-246`, `:248-262`). Bearer verification, credential issuance, MFA, brute-force controls, and live authentication were outside scope. |
| A08 — Software and Data Integrity Failures | **PASS — no finding [certain]** | Only typed built-in structures and `deepcopy` are used; there is no unsafe deserializer, dynamic import, update mechanism, or CI change. Exact source hashes and input/view immutability were verified. |
| A09 — Security Logging and Monitoring Failures | **PASS — no finding within scope [certain]** | The core performs no logging or ambient I/O, and denial responses do not reflect caller content. Production audit logging, alerting, and tamper resistance are separate operational concerns not assessed here. |
| A10 — Server-Side Request Forgery | **PASS — no finding within scope [certain]** | There is no URL input, HTTP client, DNS, socket, or fetch path. Runtime socket blocking plus a successful synthetic lifecycle found no ambient network attempt. No route or transport was reviewed. |

## Findings, disagreement, and remediation

- **Blocker:** no finding.
- **Should-fix:** no finding.
- **Nit:** no finding.
- **Structured disagreement with design choices:** none within the registered synthetic core scope. The known restore limitation and all later integration gates remain binding rather than being waived by this approval.
- **Remediation priority:** none from this review. Codex owns any separately scoped future integration or remediation; Kimi made no source fix.

**Could not review:** the remainder of #290; other runtime modules imported by the boundary test; actual bearer verification; routes and peer/media sinks; persistent store/schema/host anchor and real restore hooks; concurrency; real credentials/Keychain; tunnel/network/service configuration; provider/media behavior; iOS/APNs/CallKit, UI/device/install/signing; production deployment or live acceptance; and repository-wide dependency CVEs.