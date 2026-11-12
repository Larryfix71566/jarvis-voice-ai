---
date: 2026-11-12
system: kimi
rows: [WS-17]
prs: []
---

# WS-17 Kimi combined-source review

## Verdict

**APPROVE — no new source-level merge blocker was found within the reviewed static scope.**

This is the WS-17/A3 independent combined-source verdict, not deployment approval, operational recovery, live acceptance, or a finding that the previously recorded F1 native-test failure is fixed. No source, test, fixture, configuration, dependency, acceptance-checkbox, or operational-hold change was made.

## Target and inventory

- Production base: `b136a2a66032b17082776a01353abe67e352c31e`.
- Frozen review target: `5777e98cf1cdbaa65eb13079044693794c071927`.
- Reviewed delta outside `docs/` and `ROADMAP.md`: **188 files, 53,460 insertions, 415 deletions**.
- At verdict time, `origin/main` and the documentation branch were `4a0dd9635227cce51b01fcfcd584b3850ae81042`. The diff from the freeze to that HEAD outside `docs/`, `ROADMAP.md`, and `AGENTS.md` was empty. The verdict remains bound to the freeze, not to any later uninspected source change.
- Excluded under the no-self-review rule: Kimi-authored WS-31 NR1 `jarvis/app_build_contract.py` and the original WS-32 reader repair #275. Later non-Kimi WS-32 changes remained in scope. These exclusions require a non-Kimi reviewer and are not silently approved here.

## Method and findings

The review inventoried the complete delta, classified production exposure, inspected the changed production implementations and relevant call sites, traced failure and recovery behavior, and used focused tests only to corroborate specific invariants. It was a risk-directed static review, not a line-by-line proof of every added line or a substitute for runtime acceptance.

| Severity | New confirmed findings |
|---|---:|
| Critical | 0 |
| High | 0 |
| Medium | 0 |
| Low | 0 |

No owning-system fix PR is requested by this review. The known F1 validation failure and the explicit limitations below remain open; neither is converted into a new, unsupported source finding.

## Reviewed risk areas

### Voice, model access, privacy, and local data

- The pipeline, subscription voice path, source provenance, provider access, routing/preferences/execution, delegation, memory, weather, daily brief, WebSocket checked-send, status, and operational scripts were inspected.
- `require_voice_readiness` fails closed for `subscription_only` and `direct_apis_disabled`; no direct-API fallback or privacy defect was confirmed.
- The daily brief remains loopback-eligible with confidential classified-mail access, checked sends, and session-owned cancellation.

### Deployment, recovery, and dormant adapters

- Held deployment, installation, local restoration, and rollback paths were inspected, including archive validation, quarantine, identity checks, and fail-closed behavior. No deployment or recovery command was run.
- `task_recovery.py` and `acceptance_evidence.py` are unused pure contracts. `skill_package_adapter.py` has no production callers and returns inert package/report data rather than installing or executing skills.

### Phone service, identity, and recovery

- Phone admission/store, protocol, proof/login, authority channel, connection registry, result projection/commands, full service/recovery, and ASGI adapters were inspected.
- Phone ASGI factories default to `enabled=False`; repository call-site scans found no production mounting path. `PhoneRemoteService` is synthetic and in-process. Fake context verification, media, results, and gates are not production implementations.
- The native authority owner's executable accepts only the test-owner path, uses a scrubbed child environment, and explicitly excludes production Keychain construction and listener/service wiring. Recovery retains the singleton and fails closed when persistence, child ownership, or reap state is uncertain.

### iOS preview and wire handling

- Operations/protocol models, preview model/client/view, fake transport, package/project manifests, and `Info.plist` were inspected.
- Wire decoding includes size, depth, duplicate-key, integer, canonical UUID, and result bounds, with request correlation and replay-conflict handling.
- The app uses only `PhonePreviewFakeTransport`; it declares no network/audio permission or live connected state and labels readiness/results as synthetic.

### Harness skill and model switching

- All seven `skills/harness-model-evaluation/` files and their registration/matcher fixtures were inspected. The package is instruction-only, has no scripts, grants no account/model/tool/spending authority, and keeps harness switching blocked pending a durable approval contract.
- The passive status path re-reads cached evidence without network or inference. Explicit refresh is limited to fixed public credential-free documentation endpoints; no redirect, authentication, API endpoint, or hidden model change was found.
- Focused offline corroboration passed: `../venvs/ws17-4e58eaa/bin/python -m pytest tests/unit/test_harness_brief.py tests/unit/test_skill_package_adapter.py -q` — **177 passed in 1.54s**. These tests used synthetic data and fake HTTP, not live providers.

CI/configuration and operational-script deltas were also reviewed, including locked CI dependencies, nonblocking dependency drift, model-access guards, subscription readiness, native capability diagnostics, weather intent/reuse, status/prompt changes, and package manifests. Final activation scans found no unreviewed production phone/recovery mount, listener, or provider activation.

## Existing validation evidence and open F1 work

The separate revalidation record for exact main `4e58eaaf2993ba46eba379ba93341287b9247296` reported fourteen of fifteen checks green, including clean full pytest **8,013 passed, 145 skipped, 583 subtests**, JarvisKit **239 passed**, and the main MortimerHost target **590 passed with five skips**. Its repeated failure was:

```text
PhoneRemoteAuthorityProcessTests.testOrdinaryUnknownWaitRetainsActualSingletonAfterPartialEOF
XCTUnwrap failed: expected non-nil value of type "String" at line 76
```

That evidence is recorded in [the revalidation log](2026-11-06-ws-17-kimi-combined-main-revalidation.md). It is not rerun or superseded by this static verdict. F1 remains a separate validation repair and review gate; Codex's open PR #339 is not reviewed or approved by this document. The follow-up review must run the full `swift test --package-path macos/MortimerHost` against the exact F1 head.

A standalone skill inventory/validation CLI probe using the internal Python did not reach its checks because that interpreter lacks `openai`; it is not counted as a pass or as a product failure. No environment repair was attempted for A3.

## Explicit limitations

This verdict provides no evidence of or authorization for:

- deployment, installation, restoration, rollback, service restart, application launch, or loaded-identity proof;
- live/provider calls, credentials, physical-device checks, or human acceptance;
- production phone transport, enrollment, real media/session behavior, or live WorkspaceStore-backed phone results;
- release of any operational hold;
- post-freeze source changes or the excluded Kimi-authored files;
- a passing full-suite result at the F1 candidate before that candidate is independently reviewed and tested.

Larry retains every merge, deployment, restart, recovery, and acceptance decision. A3's static source-review gate is complete with no new merge blocker; every other gate remains independently binding.
