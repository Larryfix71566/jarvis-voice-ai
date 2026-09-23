# Model Use Enhancements — status

**As of:** 2026-09-20
**Plan:** [Model Use Enhancements](../../plans/MORTIMER_MODEL_USE_ENHANCEMENTS_PLAN.md)

This is an implementation status record, not a claim that the rollout is
complete.

## Open items first

- [ ] **MAR-A** — Reconcile the installed Mac checkout with the candidate
  release and capture live baseline latency/quality/usage.
- [ ] **MAR-D** — Apply privacy policy checks to every tool result, council
  continuation, and usage/logging path. Enabled-mode confidential and
  local-only sub-agent runs now redact tool arguments/results and final
  replies in the durable run log. Council proposer, judge, planning, and
  shadow passes now accept and enforce a stricter request policy, and their
  durable payload/score sinks redact protected content. Delegation status
  events now redact protected task text before stdout/UI emission; the
  shared MCP registry now blocks external servers during an armed sensitive
  turn before invocation; the remaining audit covers detached continuation
  and provider-specific result sinks.
- [ ] **MAR-E** — Perform the confidential-model portion of the SAYGM pilot.
  The Mac vault credential and live catalog check are now verified; the
  catalog returned 56 models but advertised zero confidential models, so a
  catalog-confirmed confidential synthetic test remains open.
- [x] **MAR-F** — Complete Claude re-authentication and capability evidence.
  Both Claude and Codex adapters are text-only and gated, and both
  subprocesses strip inherited provider API credentials and endpoint
  overrides before launch. Claude OAuth is currently not logged in and
  requires re-authentication. The installed Codex CLI authenticated
  successfully with its default model; the
  old OpenRouter `gpt-5.1-codex-max` identifier is rejected by the ChatGPT
  subscription and is therefore kept separate from the new verified profile.
  The established Mac vault is present at
  `/Users/larryfix/jarvis-voice-ai-clean/data/secrets.vault` and decrypts
  successfully. It contains `ANTHROPIC_API_KEY` (API fallback), but a Claude
  subscription is an OAuth/keychain session rather than a vault secret, so
  subscription authentication is kept outside the vault. On 2026-09-21 the
  refreshed Claude Max session passed the same noninteractive probe as Codex;
  both subscription routes now have live text capability evidence.
- [ ] **MAR-G** — Migrate all non-voice call sites and prove no background
  workload inherits the voice route. Memory, extraction, sweep, procedure,
  digest, agent, council, upgrade, and shared-content vision paths now resolve
  through the routing gate. The static inventory now covers all 13 production
  completion call sites with zero review-required entries; enabled-mode runtime
  evidence remains open.
- [ ] **MAR-H** — Add persistent route/workload controls to the existing
  native console and voice command path. The sidecar draft/confirm API and
  SQLite persistence are now landed; native-console wiring is landed in the
  Repo sidecar's MODEL ACCESS section; the gated `model_route` voice tool now
  shares the same draft/confirm store; live voice acceptance remains open.
- [ ] **MAR-I** — Run the research, development, and synthetic confidential
  memory pilot. The checked-in offline rollout fixture passes its monitoring
  gate without touching a live database; provider-backed shadow evidence is
  still credential-gated.
- [ ] **MAR-J** — Complete latency, quality, privacy, rollback, and deployed
  release evidence before changing defaults.

## Foundation landed

- [x] **MAR-B foundation** — `config/model_access.yaml` and
  `jarvis/model_routing.py` separate model identity, route, workload policy,
  privacy requirement, capabilities, credential reference, and billing source.
- [x] **MAR-C foundation** — `jarvis/model_execution.py` defines the
  provider-neutral request/result contract and preserves parent request IDs.
- [x] **MAR-D foundation** — `jarvis/privacy_policy.py` enforces strictest
  data policy before execution.
- [x] **MAR-E foundation** — `jarvis/saygm.py` parses catalog tiers and only
  recognizes `confidential` plus `-TEE` as confidential inference; SAYGM is
  included in the vault allowlist.
- [x] **MAR-F foundation** — `jarvis/subscription.py` provides explicitly
  gated text-only Claude and Codex subscription adapters. Both reject Mortimer
  tools and strip inherited API credentials/endpoint overrides before invoking
  their CLI; authentication and capability validation remain live gates.
- [x] **Status surface** — `GET /api/model-routes` exposes route/workload
  metadata without secret values.
- [x] **Persistent preference foundation** — migration `0024` adds durable
  route preferences and expiring drafts; `POST /api/model-routes/stage` then
  `POST /api/model-routes/confirm` provides an explicit confirmation boundary.
  Unknown workloads/profiles are rejected and no credential values are
  returned; the preserved voice-only Haiku profile is accepted only for the
  `voice_supervisor` workload. Drafts now reject route capability and privacy
  mismatches before persistence; unavailable credentials remain displayable as
  an explicit readiness issue.
- [x] **Native API bridge** — `JarvisKit.AdminAPI` now exposes typed methods
  for route status, draft staging, and confirmation; Swift tests pass.
- [x] **Native console controls** — the Repo sidecar presents workload,
  profile, route, and privacy selectors with Draft/Confirm/Discard actions;
  workload defaults are refreshed from the backend catalog, and the selected
  route's capabilities, privacy, and billing metadata are shown beneath the
  Access picker for user verification.
- [x] **Voice route control foundation** — `jarvis/bot/model_route_tool.py`
  drafts and confirms the same preferences only when model routing and the
  Command Console are enabled; it never invokes a provider or bypasses the
  confirmation boundary.
- [x] **Billing identity foundation** — subscription clients use the distinct
  `subscription://` ledger provider, so subscription usage cannot be confused
  with direct API spend even when token pricing is unavailable.
- [x] **Background client bridge** — memory/background factories preserve the
  resolved route object and use the subscription/SAYGM adapter when routing is
  enabled instead of assuming every background route has an API key.
- [x] **Result-policy contract** — provider-neutral execution returns the
  inherited data policy with every result, so downstream tool/result handling
  has an explicit policy value to carry into logs and continuations.
- [x] **Route-aware run-log redaction** — `SubAgent.run()` derives the
  enabled workload privacy requirement and gives `RunLogger` the same
  redaction treatment used by sensitive turns. This prevents confidential or
  local-only workloads from writing payloads into ordinary SQLite/JSONL run
  logs; focused sub-agent/run-log tests pass.
- [x] **Protected delegation activity** — confidential/local-only delegation
  prompts remain available to the specialist and its policy-aware run log,
  while `delegate_start` status events expose only a protected-task marker.
- [x] **Sensitive external-tool gate** — `SkillRegistry.call()` refuses
  `mcp-web`, `mcp-apps`, `mcp-screen`, and `mcp-selfedit` during an armed
  sensitive turn before the child process receives arguments; local MCP
  servers remain available.
- [x] **Council policy boundary** — optional `data_policy`/`privacy` context
  is propagated through proposer, judge, planning, and shadow calls and
  rejects routes below the requested privacy level. Protected goals,
  contexts, proposals, justifications, and selection reasons are redacted in
  SQLite/JSONL council sinks. Existing callers omit the field and preserve
  their prior behavior; focused council policy tests pass.
- [x] **Vision route foundation** — `vision` is an explicit image-capable
  workload and shared-content analysis uses its validated route when routing
  is enabled; direct profiles only gain the image capability when their
  registry entry is marked `vision: true`.
- [x] **Call-site inventory** — `scripts/audit_model_call_sites.py` records
  every production completion call site and its reviewed ownership. The
  2026-09-20 receipt covers 13/13 call sites with zero unclassified entries;
  it never reads credentials or sends model requests.
- [x] **Readiness probe** — `scripts/verify_model_access.py` produces a
  secret-free route/workload report, optionally checks the SAYGM catalog, and
  supports `--require-ready` for launch gating.
- [x] **Voice profile routing reconciliation** — the preserved direct API
  voice supervisor profile (`claude-haiku-4-5`) is resolved as a
  voice-only built-in route, while remaining absent from the general model
  registry so non-voice workloads cannot select a below-floor model. Focused
  registry, routing, and readiness tests pass (26 tests).

## Verification receipts

- Full unit suite: **2,644 passed, 4 skipped**, 2026-09-20 (current checkout;
  2,648 collected and passed/skipped, plus 2 subtests). The repository-map
  size correction is included in this passing run.
- JarvisKit Swift suite: **195 passed**, 2026-09-20 (elevated compiler-cache
  build required by the sandbox).
- MortimerHost Swift build: **passed**, 2026-09-20. The full 250-test suite
  still has 3 environment-dependent skips and 8 failures in
  `WindowVisibilityTests` because the headless test process cannot create a
  visibly unoccluded macOS window; they are display-fixture failures observed
  in this headless run, not route UI compilation failures. Re-run those tests
  in an active GUI session before release sign-off.
- Subscription probes (synthetic, read-only): Codex default model returned
  `MORTIMER_SUBSCRIPTION_PROBE_OK`; Claude reports `Not logged in`. The
  Mortimer Codex adapter now parses the current `item.completed` JSONL event
  shape. No project data was sent.
- Detailed receipt: [`subscription-probes-2026-09-20.md`](receipts/subscription-probes-2026-09-20.md).
- Claude adapter now permits the official OAuth/keychain path (while keeping
  session persistence off and tools denied); its next probe is gated on Larry
  signing in to Claude Code.
- Integration smoke: **52 passed**, `test_bot_wiring.py` and
  `test_planning_council.py`, 2026-09-20.
- `git diff --check`: passed.
- Route/privacy integration verification: **115 focused tests passed**,
  including the model-floor guard, voice-only Haiku resolution, route-aware
  run-log redaction, subscription routing, and readiness checks.
- Latest route/call-site/subscription-isolation/preflight subset: **22 passed**
  offline on the current checkout.
- Privacy/event regression subset: **73 passed** offline, including protected
  delegation status redaction.
- External-tool privacy subset: **66 passed** offline, including the new
  pre-invocation sensitive-turn gate.
- Architecture/plan-manifest regression subset: **65 passed** offline.
- Fresh secret-free readiness receipt: [`route-readiness-2026-09-20.json`](receipts/route-readiness-2026-09-20.json). It confirms both subscription CLIs are installed, reports their declared text capability, and records API-environment isolation.
- Historical synthetic subscription probe: [`subscription-readiness-2026-09-20.json`](receipts/subscription-readiness-2026-09-20.json). That receipt captured the pre-login Claude gate; the 2026-09-21 user-run rerun supersedes it with successful Claude and Codex probes.
- External-state recheck: the established Mac vault is present and decryptable
  with ten secret names, including `ANTHROPIC_API_KEY` and `OPENAI_API_KEY`;
  no secret values were emitted. The candidate readiness command now accepts
  `JARVIS_VAULT_PATH` and injects that vault for its secret-free checks, so
  direct API credential readiness is no longer falsely reported as missing.
  That earlier recheck predates the refreshed Claude OAuth session.
- Historical SAYGM readiness receipt: [`saygm-readiness-2026-09-20.json`](receipts/saygm-readiness-2026-09-20.json). It captured the pre-key fail-closed state; the 2026-09-22 user-run check supersedes it with a successful live catalog request.
- Current vault-backed readiness rerun: Codex and Claude subscription
  commands are installed; the vault-backed `SAYGM_API_KEY` is present; all direct Anthropic
  workloads see the vault-backed `ANTHROPIC_API_KEY`; the voice supervisor
  remains on its preserved voice-only direct-API profile. The report is
  secret-free and has no local credential readiness issues. A user-run
  vault-backed rerun on 2026-09-21 returned `ready_issues: []` with both
  Claude and Codex probes successful. Subscription routing remains separately
  gated on enabling routing and completing the sandbox-preserving tool bridge.
- User-run live provider verification on 2026-09-22: SAYGM authentication and
  catalog succeeded (`models: 56`, `credential_present: true`), Claude and
  Codex subscription probes both succeeded, and `ready_issues` was empty.
  SAYGM reported no catalog models classified as confidential; this is the
  remaining MAR-E acceptance gate rather than a credential failure.
- Call-site inventory receipt: [`model-call-site-inventory-2026-09-20.json`](receipts/model-call-site-inventory-2026-09-20.json).
- Offline memory rollout gate: **passed** with `live_database_touched=false`
  and `production_automation_enabled=false`; receipt:
  [`rollout-monitoring-receipt.json`](../memory-automation/rollout-monitoring-receipt.json).
- SAYGM confidential-model attestation, subscription route enablement, and Mac
  deployment reconciliation remain incomplete. Claude re-authentication is
  complete and has passed the live noninteractive probe.

## Next exact handoff actions

1. Run live voice acceptance for the route tool and verify spoken confirmation
   updates the native catalog without an implicit fallback.
2. Preserve the validated Claude/Codex subscription sign-ins and implement a
   sandbox-preserving tool bridge before enabling subscription routes for
   developer/app-builder workloads.
3. Run live credential/catalog checks only on the Mac vault, then record the
   provider, catalog tier, capability result, and rollback evidence here.
   From this candidate checkout, set
   `JARVIS_VAULT_PATH=/Users/larryfix/jarvis-voice-ai-clean/data/secrets.vault`
   and run `uv run python scripts/verify_model_access.py --saygm
   --probe-subscriptions --output
   docs/acceptance/model-use-enhancements/receipts/live-route-readiness.json`.
4. Reconcile the installed checkout with this candidate before enabling
   `JARVIS_MODEL_ROUTING_ENABLED=1` in any deployed launch service.
