# Model Use Enhancements — status

**As of:** 2026-10-06
**Plan:** [Model Use Enhancements](../../plans/MORTIMER_MODEL_USE_ENHANCEMENTS_PLAN.md)
**Execution sequence:** [Remaining Gaps Implementation Plan](../../plans/MORTIMER_REMAINING_GAPS_IMPLEMENTATION_PLAN.md)

**Historical reconciliation, 2026-09-25 against main `4acb4dc` (#90).** PR #90 changes the
accepted orb shell and does not change model execution, privacy, subscription
capability, memory admission, or route gates. Its commit reports MortimerHost
258 executed / 3 skipped / 0 failures, JarvisKit 199 passed, and Crystal p95
13.59 ms at 1440×220; these counts were not rerun here. Runtime identity and
effective settings remain unverified. See the
[`GC24-00 main refresh`](../verified-gap-closure/GC24-00-main-refresh-2026-09-25.md)
and the [verified gap-closure plan](../../plans/MORTIMER_VERIFIED_GAP_CLOSURE_PLAN.md).

This is an implementation status record, not a claim that the rollout is
complete.

**Reconciled 2026-09-22 against main `88b206f`.** The committed receipts in
[`receipts/`](receipts/) are dated 2026-09-20. Statements below about
2026-09-21 and 2026-09-22 events are user-reported checks: a Claude Max login
and successful Claude probe, a vault-backed rerun with both probes
succeeding, and a SAYGM catalog with 56 models. They are **not recorded in a
committed receipt and are unverified**. They are labelled where they appear,
and no item is ticked on their strength. Test counts in this file that have
no linked receipt are also unreceipted.

## Candidate validation — 2026-10-06

**Current diagnostic gate:** Exact code head `408bc6f` passes all five CI checks (6,214 unit plus two subtests / 11 skips; 196 integration / four skips; 13 eval). Actual synthetic localhost-only40 proof and all four cleanup owners pass; all full runtime/quality/billing/rollout acceptance flags stay false. Reviewed gates pass 146 focused, 386 affected (three existing skips) and 31 independent cases. No further autonomous implementation prerequisite was identified after current CI/status reconciliation. Default CLI2.1.291, exact external authorization, operator identity, manual-source authority, native test scope, compliant confidential route, Claude C3 review, account and deployed acceptance remain open. [Receipt](receipts/mar-native-api-wire-order-2026-10-06.json).

The earlier captures below record results at their named revisions. They do not supersede the current gate above or the terminal all12 result.

**Latest CI repair:** Ubuntu `aaedc37` fails4 cases/8 setup errors, all traced to absent Mac fixture paths and duplicated model-registry filename authority. Reviewed repair preserves the Mac production guard and all65 original assertions: author364/3 existing skips, independent165/3 and absent-parent106/0 pass. New-head CI remains required. The terminal all12 native gate and explicit approval questions below stay open. [Receipt](receipts/mar-native-diagnostic-ci-portability-2026-10-06.json).

**Latest terminal gate:** All12 at `a653289` finishes11 passed/one failed baseline-native-library ping-count test; Python and both MortimerHost suites pass. An unchanged host test/inverse proves scheduling sensitivity, without proving the exact guest mechanism. VMs stopped/settings unchanged. Native-readiness repair requires a matching main claim; assignment requested. The reviewed native40 diagnostic is pushed at `ddfacfa`, but live capture has not started: automatic approval review requires explicit permission for the exact private REPO_MAP document and Claude destination. No payload sent, no native incompatibility inferred. [Terminal/evidence receipt](receipts/mar-sandbox-full-profile-stability-2026-10-06.json). Earlier live/partial captures below are superseded at their named ref.

The dry-default full-menu native diagnostic is independently repaired and passes104 focused/303 affected/104 independent overlapping cases. Its normal missing-tools refusal remains; exact public live capture and all Developer/billing/rollout gates stay open. The four original causal witnesses are retained. [Diagnostic receipt](receipts/mar-native-full-menu-bootstrap-2026-10-06.json). All five GitHub checks now pass on frozen `a653289`; later heads require new checks. Actual all12 rerun at that ref has passed both Python suites (6,068 plus2 subtests/11 skips each); remaining checks are running, so no overall pass is inferred.

**Latest sandbox/CI stability evidence, 2026-10-06:** Actual pinned-image all12 baseline at `4fd8228` is terminal:11 checks passed; strict-owner host fixtures fail the baseline Python check. The reviewed test-only ownership and phase-entry repairs pass200 combined cases, with independent56 deadline and2 natural-deadline probes. Fresh CI and actual guest rerun are required; no Developer acceptance is inferred. [Terminal](receipts/mar-tokenizer-full-profile-terminal-2026-10-06.json), [fixture](receipts/mar-pilot-fixture-ownership-2026-10-06.json), [deadline](receipts/mar-deadline-confirmed-phases-2026-10-06.json).

Earlier captures below retain their named-source timing and failures; the terminal evidence above supersedes prior live wording.

Fresh immutable image `c43cc422…` is prepared from `8042722`. Actual normal offline worker at `4fd8228` proves protected default tokenizer lookup/four hashes/write refusal, the three unchanged RTVI cases and desktop/Keychain acceptance. Bounded tasks are stopped/settings unchanged. All12 verification is separately confirmed live (exec8389 / primary `f6ccb30d4441` / verification `c11a71ad1cb3`) with identical baseline/candidate; its pass is not inferred. [Image/worker receipt](receipts/mar-tokenizer-image-worker-2026-10-06.json). Native40 deterministic preflight/client order mismatch is repaired with author88/independent121 overlapping checks. Full-menu capability capture remains separate; normal native tools are unapproved.

The actual six-MCP/40-tool Developer harness is independently reviewed: author82 and independent111 overlapping checks pass, preserving original witnesses and exact causal refusals. Native40 capability, operator-issued identity, actual edit/all12/holdout/cleanup/rollback acceptance remain open. [Harness receipt](receipts/mar-full-developer-harness-2026-10-06.json).

Pinned English tokenizer preparation is implemented after main scope #183 merged and was integrated. Independent exact-block17 and root hydration/image11 plus6 subtests pass; actual fresh immutable image, different-UID offline worker and unchanged full12 acceptance remain open. [Recipe receipt](receipts/mar-tokenizer-recipe-2026-10-06.json).

The source-bound four-operation Developer driver is independently repaired (author113 / independent132 overlapping cases), with no live acceptance. Shared execution now accepts all40 installed Developer schemas; root229 affected cases and independent53 managed-path cases pass while other gates remain unchanged. The separate full40 harness now passes independent parent success-proof review; live acceptance remains open. [Receipt](receipts/mar-development-pilot-substrate-2026-10-06.json). The actual all12 sandbox baseline is terminal: ten checks passed and both Python checks failed on the same three missing-tokenizer observer cases. Main recipe scope claim #183 precedes any fix. [Terminal receipt](receipts/mar-full-sandbox-baseline-2026-10-06.json).

Normal task worker isolation and the real desktop/disposable Keychain preflight now pass on stopped owned task `fab0158b99aa`, with image/settings unchanged. [Receipt](receipts/mar-standard-worker-isolation-2026-10-06.json). The unchanged all12 verifier completed on frozen `4e225f3` (exec27828 / primary `de3a99ae63d2` / actual child `678b8671a334`) as a failed pre-edit baseline. Both owned tasks are stopped; no edited-candidate or model acceptance is claimed. Actual full40 live HTTP/source acceptance also needs an operator-issued service-bot identity: the read-only readiness check found no matching credential or active principal. A13 human-only credential minting is unchanged.

The bounded crawler transport repair now passes **44 root / 44 independently reviewed overlapping cases**: no response-cookie carryover, redirect credential spill, process proxy/TLS override or leaked clients. Existing research semantics remain. [Receipt](receipts/mar-crawl-transport-isolation-2026-10-06.json). The [10-06 vault-backed catalog read](receipts/model-access-catalog-readiness-2026-10-06.json) again reports64 SAYGM models and zero confidential models. Neither result establishes public-page origin, account billing, model quality or rollout acceptance.

**Frozen CI evidence: candidate `963ed85`, draft PR #177.** All five GitHub checks are green at that ref; later candidate heads require their own checks. Frozen Mac unit: **5,916 passed plus two subtests, three skips and the previously reproduced audio-default failure**; full deployment acceptance remains open. [Storage/admission receipt](receipts/mar-storage-admission-lifecycle-2026-10-06.json).

The standard immutable image is now prepared and registered as `9e71cb3f…` from `fd41f30`; production profile pointers/settings are unchanged. Actual bounded guest checks prove input write refusal and read-only synthetic DB integrity; both owned VMs are stopped. Normal clone/hydration worker and desktop preflight now pass; all twelve development checks and actual edited-candidate acceptance remain separate, with the unchanged-source baseline completed and failed on the missing-tokenizer prerequisite. [Image receipt](receipts/mar-immutable-image-readiness-2026-10-06.json).

The four-operation pilot implementation is repaired but has no live acceptance. The separate full40 candidate is independently reviewed for parent success-proof validation and has no live acceptance. Manual/public-crawl proof, confidential-memory route, account limits, cross-system review, voice and rollout remain open.

**Earlier candidate captures follow.** Each is evidence at its named ref; the latest record above supersedes its CI/image/prototype readiness wording. Counts overlap and are not additive.

Private-store and admission lifecycle repairs pass **395 focused cases**, with **45 storage** and **38/7 admission** independently reviewed overlapping groups. Original spend and causal cancellation/shutdown assertions remain. [Receipt](receipts/mar-storage-admission-lifecycle-2026-10-06.json). Published4dc3dfb CI failed17 deadline/admission cases; the actual double-cancel leak is reproduced and repaired, but its exact CI initiating event is unproven and new-head CI must rerun. Packaging/clone succeeds for1,738 source files atfd41f30; immutable-image preparation remains open after guest exec readiness failed, with task stopped and settings unchanged. The Developer prototype has four reviewed defects under repair and no live/full40 acceptance.

The exact synthetic-fixture hash repair is claimed on main through #182 (`d5d8cae`) and integrated before edits (`d052314`). Its48 tests plus48 subtests prove exact current bytes are accepted while edits/moves still refuse; scanner/exclusion AST, historical pins and fixture bodies are unchanged. [Receipt](receipts/mar-reviewed-fixture-hashes-2026-10-06.json). Immutable-image preparation and real Developer acceptance remain open. Context-local pilot storage repair is in progress; published candidate4dc3dfb CI remains live, not accepted.

The planner-cancellation CI case is repaired causally: cancellation now occurs after the pending request yields, with all original assertions and an added cleanup witness. Three related tests pass; a frozen original-test probe reproduces the20ms timer race. [Receipt](receipts/mar-planner-cancellation-phase-2026-10-06.json). Pilot directory cleanup is still under diagnosis; latest-head CI remains unverified.

The latest crawler-input repair passes **62 focused / 61 independently reviewed overlapping cases**, with exact source hashes in [its receipt](receipts/mar-research-input-egress-2026-10-06.json). Protected focus now refuses before actual crawler client/HTTP access, including a stricter host restriction between sites. This grants no public status to acquired unknown pages. Published `9f1e7d5` CI has **two failures**, pilot temporary-directory cleanup and cancellation occurring before the planner request starts; both repairs are in progress. Four other checks pass. An actual compatible-image preparation attempt failed before VM boot because ten synthetic credential fixture files lack current exact reviewed hashes; production settings stayed unchanged. This is a source-archive prerequisite, not Developer acceptance. Manual/public-crawl proof, representative pilots and rollout remain open.

Candidate: [draft PR #177](https://github.com/Larryfix71566/jarvis-voice-ai/pull/177),
pushed for cross-system review; not merged or deployed.

Latest bounded source repair: `50daa8b` passed **476 affected tests**, **two
installed-MCP stdio/loopback tests**, and independent reruns of **six unchanged
counterexamples plus 11 targeted legitimate-path/authentication checks**.
Those groups overlap and are not a unique total. The repair pins source floors
at actual file admission, lifecycle workers to retained ownership, real App
Builder role/parent identity, and exact saved PR handles. All 82 admin routes
remain covered by the existing bearer assertion. The frozen full unit run
passes **5,738 plus two subtests**, with **three skips and one failure**: the
same previously reproduced audio-default issue. The new auth inventory failure
is closed. Latest-head CI still needs publication/rerun; no VM, provider,
account or production action was performed. The
[ordinary source receipt](receipts/mar-ordinary-workspace-sources-2026-10-06.json)
records the exact frozen result. Manual advisory/research provenance and
real workload acceptance remain open.

The later advisory slice at `5da9b47` passes **501 affected cases**, **265
independent legacy/protocol cases**, **177 independently reviewed budget cases**,
**nine Base/Registry boundary cases** and **two installed-MCP stdio cases**
(overlapping groups). It retains original host budgets, signed preparation,
actual Developer/Analyst roles and owning cancellation/generation before sinks.
All 18 tool schemas are unchanged; all 86 admin routes retain authentication.
Frozen full unit: **5,803 plus two subtests passed, three skips and only the
same audio-default failure**. [Receipt](receipts/mar-advisory-source-budget-2026-10-06.json).
This supports single-author voice planning and protected source transport; it
does not close nested council/review, full research, real Developer capability,
private-memory availability, billing or deployment gates. Configured Tart and
Softnet are ready; the Developer pilot still needs a compatible image and real
sandbox/MCP driver. The prior published `cc37241` passed all five CI checks;
new-head CI remains separate.

The latest repair at `7d74226` passes **223 independent** and **105 focused** overlapping budget/execution cases, preserving the original SDK retry/no-reservation assertion. Read-only preflight precedes client construction, then actual retry proof precedes the atomic reservation. The repaired frozen full unit records **5,893 plus two subtests passed / three skips / only the existing audio-default failure**. Final source review at `58b4e21` is clean across 90 cases. No green full Mac deployment gate is claimed; new-head CI, broader source approval, real workload pilots and rollout remain open. [Receipt](receipts/mar-descendant-review-2026-10-06.json).

The subsequent descendant/review slice at `58b4e21` includes `cc420bf` budgets and `df80223` council/execution integration. Original D/P/C sponsorship, exact acquired-document context and before-client admission pass **192 independent budget**, **97 focused root / 27 independent root**, **422 affected source** and **two installed-MCP** overlapping cases. The 32 budget, eight root and ten review cases are new. Approved review documents retain council/economy eligibility; unknown bytes remain confidential. Frozen full unit records 5,851 passes plus two subtests / three skips / the prior audio failure and a new retry-proof reservation regression, subsequently repaired at `7d74226` without relaxing its assertion. Bounded final source review passes 90 cases; new-head CI remains pending. [Receipt](receipts/mar-descendant-review-2026-10-06.json). This is candidate evidence; manual/public-crawl provenance, full research, actual sandbox Developer and rollout remain open.

The 10-06 extensions are claimed through merged #178 (`0960373`) and #179 (`fb3e1aa`). They add
per-run SubAgent selection refresh, sealed host source handling before early
sinks, durable optional task admission and legacy canonical council guards.
Focused agent/execution/delegate tests: 260 passed; source registry/runlog/repo:
176 passed; identity suites: 298 passed / three historical skips. A wider unit
audit has 5,405 passes / three skips / the known audio-default failure; the final independent boundary suite passes 115 cases. The final integration/evals gate reports 173 passes, four skips and the same four baseline function-inventory failures. See [the source-bound integration receipt](receipts/mar-bdg-runtime-integration-2026-10-06.json). These counts do not supersede the
earlier broad/native receipts below or imply a green deployment gate.

See the [aggregate verification receipt](receipts/candidate-verification-2026-10-06.json)
and [independent subscription review](receipts/independent-subscription-review-2026-10-06.json).

- Final subscription/agent/execution focused suite: **243 passed**; source-bound independent review covers exact context/tool binding, system constraints, UTF8 transport, invalid-input child cleanup and cleanup quarantine.
- Broad Mac unit run: **5,076 passed, 3 skipped, 1 failed**; unchanged main has **4,802 passed, 3 skipped, the same audio-default failure**. The last receipt-await guard has a separate focused rerun.
- Integration/evals: **186 passed, 4 skipped, 4 failed** on both candidate and unchanged main (the same bot function-inventory assertions). Process-supervision failures from the initial restricted run pass with appropriate process access.
- Detached-checkout policy: **9 passed**. Call-site classification: **30/30**, not privacy acceptance. JarvisKit: **226 passed**. Native route controls: **10 passed**. Batched native coverage includes **493 unique identifiers**, six skips and one capture failure, also reproduced on unchanged main.
- No assertions were relaxed or tests removed. Full Mac/deployment gates are **not claimed green**. Global production routing and account settings remain unchanged.

The later committed development/source gate at `8902693` passes **572 tests and 45 subtests**, with zero failures/skips and three existing deprecation warnings. It covers actual inert host sandbox facets, authenticated creator IPC, route refresh, task bounds and cleanup ownership. See [the source-bound receipt](receipts/mar-development-source-bridge-2026-10-06.json). It does not replace broader repo/Mac results or establish live VM/provider acceptance.

The subsequent native-owner repair at `5c50385` passes **282 focused tests**, including four unchanged independent concurrency probes. Both actual text clients refuse queued starts and suppress active late publication after shared cleanup quarantine; Codex receipt-worker wait cannot bypass the guard. [Receipt](receipts/mar-native-text-quarantine-2026-10-06.json). Counts overlap the other focused gates and must not be added into a unique full-suite total.

## Open items first

The 10-05 changes below are **candidate implementation**, on the isolated
`codex/ws05-execution-20261005` branch claimed through #175, #176, #178, #179 and #180. They do not
change production routing, credentials, account settings or the deployed app.

- [ ] **MAR-A — deployed baseline and measurements.** The
  [fresh aggregate baseline](receipts/mar-a-baseline-2026-10-05.json) reconciles
  production, bundle and deployment receipt to `bde22bb`. Since deployment it
  records 26 provider calls (12 LLM), without populated historical route,
  billing-source or duration fields. The candidate's
  [41 offline API attribution tests](receipts/mar-a-prospective-api-attribution-2026-10-05.json)
  prove future non-streaming metadata and single-owner accounting. Historical
  timing is unrecoverable; effective bot activation, representative quality,
  voice/stream timing and deployed attribution remain open.
- [ ] **MAR-D — complete source/sink privacy coverage.** Exact route/key contracts,
  static privacy floors, confidential replay/settlement and sanitized late-delivery
  logs are implemented. The [source/sink regression receipt](receipts/mar-d-source-sink-regressions-2026-10-05.json)
  pins the offline repairs. Declared tool-result restrictions are checked before
  native continuation. The 10-06 typed registry/agent boundary also defaults
  unknown acquired sources confidential, validates guarded repository bytes,
  sanitizes public error payloads and redacts earlier MCP buffers. Installed
  Upgrade/AppBuild issuers and authenticated creator receipts now preserve exact
  host source/owner bindings before sinks. The ordinary self-edit/app MCP loop
  now uses a separate authenticated workspace receipt before sinks, with the
  50daa8b admission/lifecycle repairs above. Unknown raw outputs do not gain
  external approval. The later advisory transport has signed source/budget
  proof before sinks; complete manual/public-crawl approval remains open.
  Preserve standing project-code grants and private source floors.
- [ ] **MAR-E — SAYGM confidential pilot.** Authentication and catalog access
  [succeeded again on 10-05](receipts/model-access-catalog-readiness-2026-10-05.json): 64 models, zero advertised confidential models.
  Candidate execution binds the exact catalog ID, tier, capability shape and
  protected gateway/key contract; redirected catalog requests are refused.
  There is no available confidential pilot route to accept today; catalog
  checks do not establish attestation or account guardrail settings.
- [ ] **MAR-F — subscription capability, account and workload acceptance.**
  Installed Codex 0.160.0 has a [passing exact-model text/no-tools proof](receipts/mar-f-codex-text-capability-2026-10-05.json).
  Installed Claude 2.1.290 has a [passing isolated public native-tool fixture and
  negative unadvertised-Bash proof](receipts/mar-f-claude-native-fixture-capability-2026-10-05.json). Candidate Claude native tools require a
  separate exact binary/model/invocation/schema/control-protocol receipt and
  preserve the existing Mortimer tool executor, mandatory constraints and
  request cleanup. Codex tool workloads remain unsupported. The fixture does
  not authorize real Developer tools, prove account billing/overage settings,
  or establish model quality on those tools. Provider sign-in stores remain
  outside the vault; no token or credential was copied.
- [ ] **MAR-G — enabled-mode workload acceptance.** The candidate call-site
  inventory classifies 30/30 entries, including the repaired historical replay
  and review-settlement paths. Classification is not behavioral acceptance.
  Background work keeps dedicated profiles and static privacy/quality floors;
  the voice supervisor is unchanged. Enabled routing rejects duplicate canonical
  identities before any council provider call; the 10-06 legacy loader/member
  guard also rejects canonical and physical aliases before key lookup. Per-run
  saved SubAgent choices now refresh and optional parent limits are enforced.
  UpgradeAgent/AppBuildAgent now refresh confirmed choices per run, verify source
  envelopes and share limits without enabled-mode implicit failover. Capped
  council child sponsorship and larger-edit parity are implemented in the
  candidate: [317 council/budget cases](receipts/mar-council-child-budgets-2026-10-06.json)
  and [170 edit-transport cases](receipts/mar-large-edit-parity-2026-10-06.json)
  pass in their frozen overlapping gates. Advisory transport now has actual
  durable parent authority and cancellation ownership. The later descendant/review
  candidate supports nested sponsorship and sealed acquired documents; its bounded frozen gates are recorded above, while representative workload acceptance remains open. Complete
  enabled-mode run/usage/cancellation evidence remains open.
- [ ] **MAR-H — native and voice controls.** Native saved choices outrank defaults,
  unavailable choices remain visible, and changes invalidate drafts and late
  replies. Catalog descriptors separate profile capabilities, provider gates and
  admin activation from unverified bot state. [Ten native route-control tests](receipts/model-route-controls-native-2026-10-05.json)
  pass. Spoken stage/confirm behavior and deployed acceptance remain open.
  The broader native protected-window capture gate fails with ScreenCaptureKit
  `-3811` on both candidate and unchanged main; it was not removed or relaxed.
- [ ] **MAR-I — three-workload pilot.** The reproducible harness is bounded,
  dry-run by default, isolates databases, pins source/scorer hashes and records
  only aggregate results. The
  [Codex public research diagnostic](receipts/model-use-pilot-live-codex-research-2026-10-05.json)
  scored 3/3 cases, median 3914.5 ms and sample maximum 3974.5 ms. This is three
  cold source-packet synthesis calls, not complete research retrieval or stable
  p95 acceptance. Earlier
  [direct API](receipts/model-use-pilot-live-direct-research-2026-10-05.json) and
  [Claude](receipts/model-use-pilot-live-claude-research-2026-10-05.json) diagnostics
  completed 3/3 requests but failed the strict JSON-format gate; factual content
  is unscored. [Recomparison](receipts/model-use-pilot-comparison-recheck-2026-10-05.json)
  is explicitly inconclusive, and changed scorer/framework versions cannot be
  compared as if they were identical. Real sandbox Developer and confidential
  memory pilots remain open; historical public memory shadow is not a substitute.
- [ ] **MAR-J — rollout.** Verify workload quality/latency, privacy, effective
  service configuration, allowance/paid-overage settings, supported spend/output
  limits and deployed rollback before changing defaults. The authoritative
  endpoint registry has no direct OpenAI API endpoint; key presence alone is not
  evidence of one. Local runtime is a placeholder and private defaults have no
  compliant available route. Keep global production routing unchanged.

## Foundation landed

- [x] **MAR-B foundation** — `config/model_access.yaml` and
  `jarvis/model_routing.py` separate model identity, route, workload policy,
  privacy requirement, capabilities, credential reference, and billing source.
- [x] **MAR-C foundation** — `jarvis/model_execution.py` defines the
  provider-neutral request/result contract and preserves parent request IDs.
  (GC24-02 progress, 2026-09-24: context messages and normalized text/image
  attachments now retain order and source policy; external attachments require
  approval bound to exact route/model. Malformed, duplicate, unsupported-image
  and route/workload-mismatch requests fail before client creation. An async
  deadline includes queue time and cancels the awaited call. Two-slot
  interactive/background admission, bounded output requirements, usage
  metadata and allowlisted/schema-validated tool-call results are implemented
  and have locked-environment pytest evidence. Production call families now
  use the boundary under routing gates. The planner and shared-content vision
  migrations now pass the locked full suite (2,813 passed, 4 skipped, 2
  subtests); per-offer vision routing is bound to its consented batch.
  Provider-request/response progress events are now emitted by the boundary;
  tool-call IDs cannot be replayed inside a validated history or returned again
  by the provider for that history.
  Token-level text/artifact/tool-result streaming, exactly-once terminal
  handling across callers, downstream
  cancellation, and late-write suppression remain open. See the linked
  [GC24-02 implementation receipt](../verified-gap-closure/GC24-02-execution-boundary-implementation-2026-09-24.md).)
- [x] **MAR-D foundation** — `jarvis/privacy_policy.py` enforces strictest
  data policy before execution.
- [x] **MAR-E foundation** — `jarvis/saygm.py` parses catalog tiers and only
  recognizes `confidential` plus `-TEE` as confidential inference; SAYGM is
  included in the vault allowlist.
- [x] **MAR-F foundation** — `jarvis/subscription.py` provides explicitly
  gated text-only Claude and Codex subscription adapters. Both reject Mortimer
  tools and strip inherited API credentials/endpoint overrides before invoking
  their CLI; authentication and capability validation remain live gates.
- **2026-09-25 MAR-F offline implementation:** adapters now use stdin-only
  prompts, task-scoped temporary working directories, an allowlisted child
  environment, strict successful terminal-event parsing, and owned async
  process-group cancellation. Full Python unit/integration tests passed
  **3,079**; the focused adapter/routing/execution group passed **87**. Codex
  remains gated until its installed runtime is proven to expose no built-in or
  hosted tools; setting its gate is not itself evidence. Inherited
  `CODEX_HOME` and `CLAUDE_CONFIG_DIR` overrides are excluded. A fresh local
  auth-status check reported Claude unauthenticated and Codex logged in, but no
  provider request or completion was tested. No provider calls,
  live auth/billing checks, or deployment were performed. MAR-F stays open.
  See the [GC24-04 runtime isolation receipt](../verified-gap-closure/GC24-04-subscription-runtime-isolation-2026-09-25.md)
  and [model-ready implementation plan](../../plans/MORTIMER_SUBSCRIPTION_RUNTIME_ISOLATION_PLAN_2026-09-25.md).
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
  `subscription://` ledger provider. GC24-02 adds persisted billing-source,
  route, usage-known, cache-breakdown-known and duration metadata to new ledger
  rows; legacy rows remain explicitly unknown where those fields were not
  recorded.
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
  size correction is included in this passing run. (Not in a committed
  receipt. At `88b206f` on Linux, `pytest tests/unit` gave 2,526 passed, run
  by Claude on 2026-09-22.)
- JarvisKit Swift suite: **195 passed**, 2026-09-20 (elevated compiler-cache
  build required by the sandbox). (Not in a committed receipt. 195 equals the
  static `func test` count at `88b206f`. The newest committed JarvisKit logs,
  2026-09-18, record 190/190.)
- MortimerHost Swift build: **passed**, 2026-09-20 (not in a committed
  receipt; 250 is the static `func test` count at `88b206f`). The full 250-test suite
  still has 3 environment-dependent skips and 8 failures in
  `WindowVisibilityTests` because the headless test process cannot create a
  visibly unoccluded macOS window; they are display-fixture failures observed
  in this headless run, not route UI compilation failures. Re-run those tests
  in an active GUI session before release sign-off.
- Subscription probes (synthetic, read-only): Codex default model returned
  `SUBSCRIPTION_PROBE_OK` (the Mortimer adapter returned `ADAPTER_PROBE_OK`);
  Claude reports `Not logged in`. (Token names corrected 2026-09-22 to match
  the receipt; the earlier text said `MORTIMER_SUBSCRIPTION_PROBE_OK`.) The
  Mortimer Codex adapter now parses the current `item.completed` JSONL event
  shape. No project data was sent.
- Detailed receipt: [`subscription-probes-2026-09-20.md`](receipts/subscription-probes-2026-09-20.md).
- Claude adapter now permits the official OAuth/keychain path (while keeping
  session persistence off and tools denied); its next probe is gated on Larry
  signing in to Claude Code. (A 2026-09-21 sign-in and probe are
  user-reported below. No committed receipt records them.)
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
- Historical synthetic subscription probe: [`subscription-readiness-2026-09-20.json`](receipts/subscription-readiness-2026-09-20.json). That receipt captured the pre-login Claude gate; the 2026-09-21 user-run rerun supersedes it with successful Claude and Codex probes. (That rerun is not in a committed receipt, so this 2026-09-20 receipt is still the latest committed probe evidence.)
- External-state recheck: the established Mac vault is present and decryptable
  with ten secret names, including `ANTHROPIC_API_KEY` and `OPENAI_API_KEY`;
  no secret values were emitted. The candidate readiness command now accepts
  `JARVIS_VAULT_PATH` and injects that vault for its secret-free checks, so
  direct API credential readiness is no longer falsely reported as missing.
  That earlier recheck predates the refreshed Claude OAuth session.
- Historical SAYGM readiness receipt: [`saygm-readiness-2026-09-20.json`](receipts/saygm-readiness-2026-09-20.json). It captured the pre-key fail-closed state; the 2026-09-22 user-run check supersedes it with a successful live catalog request. (That check is not in a committed receipt, so this receipt is still the latest committed SAYGM evidence.)
- Current vault-backed readiness rerun: Codex and Claude subscription
  commands are installed; the vault-backed `SAYGM_API_KEY` is present; all direct Anthropic
  workloads see the vault-backed `ANTHROPIC_API_KEY`; the voice supervisor
  remains on its preserved voice-only direct-API profile. The report is
  secret-free and has no local credential readiness issues. A user-run
  vault-backed rerun on 2026-09-21 returned `ready_issues: []` with both
  Claude and Codex probes successful. Subscription routing remains separately
  gated on enabling routing and completing the sandbox-preserving tool bridge.
  Committed receipt:
  [`vault-backed-route-readiness-2026-09-20.json`](receipts/vault-backed-route-readiness-2026-09-20.json).
  (Reconciled 2026-09-22: the receipt shows `ready_issues: []`,
  `routing_enabled: false`, `credential_present: true` for every workload
  including `voice_supervisor` on `claude-haiku-4-5`, and both subscription
  CLIs `installed: true`. It records the SAYGM route with
  `credential_present: false` and has no `saygm_catalog` and no
  `subscription_probes`. So "`SAYGM_API_KEY` is present" is not supported by
  the committed receipt. The 2026-09-21 rerun with successful probes is
  user-reported and unverified.)
- User-run live provider verification on 2026-09-22: SAYGM authentication and
  catalog succeeded (`models: 56`, `credential_present: true`), Claude and
  Codex subscription probes both succeeded, and `ready_issues` was empty.
  SAYGM reported no catalog models classified as confidential; this is the
  remaining MAR-E acceptance gate rather than a credential failure.
  (Not recorded in a committed receipt; unverified.)
- Call-site inventory receipt: [`model-call-site-inventory-2026-09-20.json`](receipts/model-call-site-inventory-2026-09-20.json).
- Offline memory rollout gate: **passed** with `live_database_touched=false`
  and `production_automation_enabled=false`; receipt:
  [`rollout-monitoring-receipt.json`](../memory-automation/rollout-monitoring-receipt.json).
- SAYGM confidential-model attestation and subscription route enablement
  remain incomplete. The 2026-10-02 Claude recheck supersedes that day's
  earlier HTTP 401 result for the selected Homebrew CLI, while preserving it
  as evidence of the alternate signed-out executable. The deployed revision
  is documented under MAR-A.

## Next exact handoff actions

1. Run live voice acceptance for the route tool and verify spoken confirmation
   updates the native catalog without an implicit fallback.
2. Verify Claude subscription CLI resolution and auth inside the running
   service before activation; then validate allowance/billing and workload
   capabilities. Verify Codex's no-tools runtime capability for its installed
   version before lifting its adapter gate. A sandbox-preserving tool bridge
   is still required for tool-bearing developer/app-builder workloads.
3. Recheck SAYGM catalog and capability metadata when a confidential model is
   advertised; do not classify the current 64-model catalog as confidential.
4. Reconcile the installed checkout with this candidate before enabling
   `JARVIS_MODEL_ROUTING_ENABLED=1` in any deployed launch service.
