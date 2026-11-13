---
date: 2026-11-13
system: claude
rows: [WS-34]
prs: []
---

# WS-34 B2 follow-up: every Mortimer caller sends X-Mortimer-Client

Row: WS-34. Plan item: B2 (`docs/plans/MORTIMER_RELEASE_CLOSURE_PLAN.md` §4). Answers R1 of Codex's #342 review (`docs/roadmap-log/2026-11-12-ws-35-b2-request-guard-review.md`). Reviewer: Codex.

## What changed

- Python callers of admin (:7861), bot (:7860) and costs (:8487) now send `X-Mortimer-Client` through `jarvis.request_guard.client_headers()`, next to the bearer token where one is sent. Names: `mortimer-mcp` (AdminClient, used by mcp_selfedit, mcp_web, mcp_apps, mcp_status and the bot's plan/research tools), `mortimer-bot` (status tool, watchers, skill inventory reporter, creator dispatch), `mortimer-admin` (skill request cancel and dispatch), `mortimer-health` (`scripts/service_health.py`, `scripts/mortimer.sh`, the status page's HTTP probe).
- The native voice WebSocket (`NativeAudioTransport.swift`) sets the header from `JarvisHTTP.clientHeaderName`/`clientHeaderValue`. Shared native HTTP already did, from #365.
- `jarvis.auth.service_headers()` is unchanged; its exact value is pinned by `tests/unit/test_auth.py`.
- The guard's rules are unchanged. A request with no Origin still passes without the header (R2).

## Not covered

- `scripts/run_model_use_full_development_pilot.py` and `scripts/spoken_acceptance.py` (operator scripts) and `macos/MortimerShell` (deleted by C1b) do not send the header.
- Wake-word socket (:7862), knowledge-base vault (:8484) and external map tiles are outside B2's three services.

## Waits on Larry

- R2: refusing a request with no Origin. Unchanged until Larry decides.
- C1: reserving `JARVIS_REQUEST_GUARD_ENABLED`, `JARVIS_ALLOWED_HOSTS` and `JARVIS_ALLOWED_ORIGINS` in ROADMAP.md §3 needs its own docs PR and Larry's yes.

## Checks run (cloud session, Python 3.13 with the lockfile minus torch and wake-word packages)

- Targeted: `test_service_token`, `test_request_guard`, `test_internal_callers_authenticated`, `test_auth`, `test_status_services`, `test_status_tool`, `test_mcp_selfedit_logic`, `test_mortimer_sh_guard`, `test_skill_requests`, `tests/integration/test_creator_dispatch_bridge.py`: 300 passed.
- Full `tests/unit` on this branch and on clean `next` (6a7ac28), same environment: 61 failed, 1 error on both, the same tests. 8,318 passed here against 8,311 on `next`; the seven extra are this PR's new tests. The shared failures: 60 `test_mcp_mail_logic` tests and a `test_ws_transport` teardown error, which pass in hosted CI on `next` (its unit step reports 1 failure), so they come from this sandbox; and `test_offline_nltk_data::test_ci_enforces_full_pyflakes_and_verifies_data_before_import` also fails in hosted CI on `next` at 6a7ac28 (the test still expects the ruff line without #367's `--per-file-ignores`). Larry approved fixing that test here (2026-11-13 23:52 UTC, "Yes, fix it in #369"); a separate commit updates its expected command, and the file passes (8 tests).
- Swift: not compiled here (no Swift toolchain). The `NativeAudioTransportTests` change relies on the B1 `swift-tests` CI job.
