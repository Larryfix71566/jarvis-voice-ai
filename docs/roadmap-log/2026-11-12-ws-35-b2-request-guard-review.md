---
date: 2026-11-12
system: codex
rows: [WS-35]
prs: [342]
---

# WS-35 independent review of WS-34 B2 (#342)

- **System:** Codex; implementation author: Claude. Model version: not recorded.
- **Session reference:** `/root/identify_next_mortimer_work`, Larry's 2026-11-12 B2 queue-item dispatch.
- **Verdict:** **CHANGES REQUESTED against Larry's current acceptance criteria.**
- **Reviewed source:** [#342](https://github.com/Larryfix71566/jarvis-voice-ai/pull/342), exact head `5d714af994ed72799cbf96844a2c93fe500bd224`, targeting `next` `a1369e223e51cc499c8f942fae95133994a4facb`.
- **Coordination source:** current `origin/main` `4a0dd9635227cce51b01fcfcd584b3850ae81042`: AGENTS.md, ROADMAP.md §§0/2/4, WS-35, and closure-plan §4/§8. Fetched before work. The source checkout was detached and unchanged; this documentation branch starts from current main.
- **Scope:** eight-file B2 delta, its middleware/auth/CORS integrations, focused tests, and native request construction. No author-branch edit, formal GitHub review submission, merge, deployment, settings change, or live service request.

## Findings and required disposition

### R1 — Required native header coverage is absent (acceptance blocker)

Larry's current direction asks for `X-Mortimer-Client` on native request paths. #342 changes no Swift file and no native source sets that header. `JarvisHTTP.swift:45–56` adds Accept and optional Authorization only. AdminAPI's ordinary/read/write/health requests, CostsAPI, Signalling POST/PATCH, and MemoryGraphAPI's transient query/search/image paths all converge on that sender. The separate `NativeAudioTransport.swift:224–225` WebSocket request adds Authorization only; its URLSession adapter uses that request at line 682.

The closure plan deliberately assigns the app header line to C7b, and the PR describes native callers as exempt. That explains the implementation; it does not satisfy Larry's latest review criterion. Coordinate the missing shared HTTP and separate WebSocket header coverage with C7b and add request-capture tests for both, including transient graph requests. Do not claim every request path is covered now. Wake-word sockets and external map tiles are outside the three-service B2 boundary; a literal all-native-network-path requirement would need an explicit scope decision.

### R2 — Missing Origin is allowed, not universally refused (acceptance blocker)

`jarvis/request_guard.py:238–266` only evaluates Origin when it exists. Ordinary HTTP requests without Origin or fetch metadata, including POST/DELETE, reach the app without a client header. WebSockets without Origin also reach the app. Missing Origin with `Sec-Fetch-Site: same-origin` is exempt; missing Origin with cross-site metadata is rejected. The existing tests explicitly require the native exemption (`test_native_client_shape_needs_no_header`, `test_websocket_rules`).

This conflicts with an unconditional missing-Origin refusal criterion. It is an intentional compatibility rule, **not evidence of a browser-origin bypass**: browsers control Origin/fetch metadata, whereas raw native clients can forge either and the client-name header is not authentication. Foreign or null Origin is rejected even with a valid client header.

Before approval, reconcile the requirement in code/tests and the plan with Larry's current direction. Blanket absence rejection would break the present native and Python callers. A documented native/service exception must be explicitly accepted, bounded, and tested; alternatively migrate callers before enforcing refusal. Adding a native header alone does not make missing Origin fail closed in this implementation. Do not set `PIPECAT_ALLOWED_ORIGINS` as a shortcut: the existing native handshake lacks Origin and Pipecat would reject it with 4003.

### R3 — Malformed numeric port raises instead of controlled refusal (low-severity robustness defect)

`jarvis/request_guard.py:81–89` accepts `str.isdigit()` then calls `int()` without a failure boundary. With an allowed Host, `Origin: http://localhost:²` is Latin-1 representable and passes `isdigit()`, but `int()` raises ValueError. A 5,000-digit ASCII port also raises at Python 3.12's integer-conversion limit. Both HTTP and WebSocket scopes reproduce the exception before the inner app runs, rather than the intended 403/4403.

Use bounded ASCII port parsing, reject invalid/out-of-range ports, and test both protocols. This is not an authorization bypass and is not the reason for elevating the earlier source-only assessment to CHANGES REQUESTED.

### C1 — Coordination metadata still needs author reconciliation

The three introduced keys (`JARVIS_REQUEST_GUARD_ENABLED`, `JARVIS_ALLOWED_HOSTS`, `JARVIS_ALLOWED_ORIGINS`) are absent from current main ROADMAP.md §3 and the PR-head roadmap. AGENTS requires reservation before code. WS-34's current-main row also still says proposed/not-started, with the separate claim PR #333 open. This review does not edit Claude's row or reserve keys retroactively on its behalf. The shared new module and test are sensible for the integration but should be represented in the author scope/claim reconciliation.

## Verified behavior

One pure-ASGI guard is installed on admin, bot and costs. Admin retains outer CORS and existing 5xx logging, then guard before bearer auth; bot installation is idempotent. Costs has no bearer auth, unchanged by this PR. Lifespan bypass and the default-on kill switch are tested. CORS preflight can terminate outside the guard without invoking application routes; this is not data access.

| Input, valid Host unless stated | Result |
|---|---|
| Native-shaped POST, no Origin/header | allowed |
| Missing Origin plus valid client header | allowed |
| Foreign Origin, with or without client header | HTTP 403 |
| Null Origin | HTTP 403 / WS 4403 |
| Missing Origin, cross-site metadata (even with client header) | HTTP 403 / WS 4403 |
| Missing Origin, same-origin metadata | POST allowed |
| Missing Origin, mode-only browser metadata, no client header | HTTP 403 |
| Allowed dev Origin, mutating request, no header | HTTP 403 |
| Allowed dev Origin with valid header | allowed |
| Same-origin POST, no header | allowed |
| Foreign Host | HTTP 403 |
| Native-shaped WS, no Origin | allowed |
| Foreign Origin WS | ASGI close 4403 |
| Malformed Origin ports above | uncaught ValueError in both protocols |

ASGI close 4403 is a middleware event, not a claim that every rejected pre-accept WebSocket handshake exposes that close code to a real client.

## Tests actually run by this reviewer

Fresh isolated Mac checkout at the exact PR head, CPython 3.12.13, new venv installed from `requirements-lock.txt`; no copied production .env, no live tests. Locked Starlette 1.3.1, Uvicorn 0.52.1, HTTPX 0.28.1, Pipecat 1.4.0.

```text
RUN_LIVE=0 PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest \
  tests/unit/test_request_guard.py tests/unit/test_auth_middleware.py \
  tests/unit/test_bot_server.py tests/unit/test_costs_api.py \
  tests/integration/test_creator_dispatch_bridge.py -q -p no:cacheprovider
81 passed, 3 warnings in 19.24s
```

Warnings: Starlette HTTPX deprecation, audioop deprecation, and Pipecat AudioContextTTSService deprecation.

- Independent raw-ASGI matrix: **16/16 behavior assertions passed**, matching the table above, not the unmet unconditional-refusal requirement.
- Separate malformed-port probes: **4/4 reproductions confirmed** (two port inputs × HTTP/WS). These are verified defects, not passing correctness tests.
- `ruff check --no-cache --isolated --select F821` on the five changed Python files: **passed**.
- GitHub refresh: all **5** checks green, PR mergeable at the reviewed head. [Validate run](https://github.com/Larryfix71566/jarvis-voice-ai/actions/runs/42961637402), validation job 130329294853. These existing remote checks are distinct from the new reviewer-local run.
- Full Python suites and Swift suites were **not rerun** for this review. No Mac UI smoke, live URLSession header capture, remote MagicDNS/Tailscale check, credential activation, production restart, or deployment acceptance was performed.

## Remaining action

Claude coordinates R1/R2 with C7b and Larry's stricter criteria, fixes the parser failure, and reconciles the reservation/claim record. Codex then re-reviews the exact revised head with updated tests. B2 and the release remain unaccepted; green tests and mergeability do not authorize merging. The native voice + Costs/Memory/Edit smoke and rejection-log check remain open.

This record supersedes the earlier private source-only APPROVE-with-nit assessment for acceptance purposes: the source head did not change; the review now explicitly evaluates Larry's native-header and missing-Origin requirements.
