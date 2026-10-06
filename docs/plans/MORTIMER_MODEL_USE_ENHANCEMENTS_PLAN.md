# Model Use Enhancements

**Status:** IMPLEMENTATION IN PROGRESS — routing foundation landed; rollout remains gated.
**Recorded:** 2026-09-20.
**Origin:** Larry's model-access, subscription, SAYGM, orchestrator, and latency discussions; implementation plan preserved from the conversation at Larry's request.
**Scope:** Manual subscription/API selection, SAYGM integration, privacy-aware routing, and preservation of Mortimer's existing behavior. Voice-provider replacement is a separate decision requiring testing.
**Authorization:** Saving this document does not itself authorize implementation, deployment, account changes, or live provider calls.

**Current implementation evidence (2026-09-20):** `jarvis/model_routing.py`,
`jarvis/saygm.py`, `jarvis/privacy_policy.py`, and
`jarvis/model_execution.py`, and `jarvis/model_preferences.py` provide the
policy, catalog, privacy, provider-neutral execution, and draft-confirmed
preference foundations. The admin sidecar exposes `GET /api/model-routes` plus
the stage/confirm preference endpoints. Existing runtime behavior remains unchanged until
`JARVIS_MODEL_ROUTING_ENABLED=1`; Claude and Codex subscription adapters are
text-only and explicitly gated, reject Mortimer tools, and strip inherited API
credentials/endpoint overrides before launch, so tool-bearing subscription
workloads fail closed until a sandbox-preserving bridge is validated. Focused verification:
the full unit suite passes (2,644 tests, 2026-09-20) using the repository's installed test
environment. `JarvisKit.AdminAPI` now has typed route-status and
draft-confirm methods, and the native Repo sidecar presents those controls
plus selected-route capabilities/privacy/billing metadata; the JarvisKit suite
passes 195 tests. MortimerHost builds successfully, while its full 250-test
run has 3 display-dependent skips and 8 failures in `WindowVisibilityTests`
when run without a visibly unoccluded GUI window; re-run those tests in an
active GUI session before release sign-off. The gated `model_route` voice tool uses
the same preference store and confirmation boundary; live voice acceptance is
still required. Background memory factories retain the resolved route object,
so enabled-mode subscription/SAYGM adapters do not assume an API credential.
The preserved `claude-haiku-4-5` voice supervisor is resolved through a
voice-only built-in profile, so readiness checks validate the unchanged voice
route while the general model registry continues to reject Haiku for
non-voice workloads.

**Current candidate status (2026-10-06):** Draft [PR #177](https://github.com/Larryfix71566/jarvis-voice-ai/pull/177) contains the committed implementation and evidence. The isolated branch
`codex/ws05-execution-20261005` is claimed on main through #175 and #176.
Production checkout, installed bundle and deployment receipt agree on
`bde22bb`; the 10-05 aggregate-only baseline records 26 provider calls (12 LLM)
since deployment, with no populated historical route, billing-source or
model-duration fields. Those missing measurements cannot be recovered.
Running-process activation and representative workload quality remain open.

The candidate adds exact catalog/model/capability binding and pinned credential
contracts, workload quality floors, saved native preference and stale-draft
repairs, confidential replay/settlement execution, content-safe continuation
logs, and prospective non-streaming API accounting metadata. These are local
implementation results, not deployed acceptance.

Claude 2.1.290 has a separately gated native MCP bridge. Only Mortimer's existing
validated agent tool loop executes operations; request-bound IPC returns its
results and mandatory system constraints to the provider runtime. Passing
public-fixture receipts cover exact runtime/schema/protocol identities,
isolation, unadvertised-tool refusal and cleanup. They do not enable the actual
Developer registry. Codex 0.160.0 has a matching text-only no-tools proof; a
three-case public research diagnostic passed all scored cases (median 3.9 s,
three samples, no stable-p95 claim). Previous direct-API and Claude diagnostics
failed the strict JSON-format gate, leaving their content unscored. Those
receipts cannot establish a quality comparison with the newer Codex harness.

**Open rollout gates:** all newly acquired source policies and legacy council
identity coverage; representative research and real sandbox Developer quality;
confidential memory pilot; supported workload spending/output limits; exact
running-service capabilities and activation; billing/allowance/paid-overage
settings; voice route-control and deployed rollback acceptance. SAYGM's latest
authenticated catalog contains 64 models and zero advertised confidential
models. Local runtime is still a placeholder. Direct OpenAI API access is not
configured in the authoritative endpoint registry. Production global routing
must remain unchanged while its private workloads lack compliant routes.

**Reconciled 2026-09-22 against main `88b206f`.** This header and
[the status file](../acceptance/model-use-enhancements/STATUS.md) now agree
on what the committed receipts show. MAR-E and MAR-F remain **open**. The
only committed SAYGM receipt (`saygm-readiness-2026-09-20.json`) failed
closed with `SAYGM_API_KEY is not set`. The only committed subscription
probe receipts (`subscription-probes-2026-09-20.md`,
`subscription-readiness-2026-09-20.json`) record Codex returning
`SUBSCRIPTION_PROBE_OK` and Claude `Not logged in`. The status file also
describes a Claude login and successful probe on 2026-09-21 and a SAYGM
catalog with 56 models on 2026-09-22. Those are user-reported, not in a
committed receipt, and unverified. The "195" JarvisKit and "250-test"
MortimerHost figures above are the static `func test` counts at `88b206f`.
No committed receipt records those runs; the newest committed JarvisKit logs
(2026-09-18) record 190/190. Likewise, no committed receipt records the
2,644-test Python run.

The implementation must follow the decisions below. Missing credentials,
unavailable models, or unsupported provider features must produce a documented
blocker—not an improvised architectural change.

Related documents:

- [Roadmap](../../ROADMAP.md)
- [Architecture](../ARCHITECTURE.md)
- [Platform roadmap](MORTIMER_PLATFORM_ROADMAP.md)
- [Gap-closure plan](MORTIMER_GAP_CLOSURE_PLAN.md)
- [Implementation status](../acceptance/IMPLEMENTATION_STATUS.md)
- [Model-use status](../acceptance/model-use-enhancements/STATUS.md)
- [Command Console and Knowledge Atlas plan](MORTIMER_COMMAND_CONSOLE_ATLAS_PLAN.md)
- [Automated-memory plan](MORTIMER_MEMORY_AUTOCONSOLIDATION_PLAN.md)

## Progress

- 2026-10-06 (Codex, final candidate review): Independent regressions corrected ambiguous duplicate native calls, altered argument/history bindings, required PostToolUse system constraints, Unicode packet framing and invalid-UTF8 child cleanup. Unverified native cleanup now retains the owner and quarantines that client; active/queued or receipt-validation-wait requests cannot publish or start a new session after quarantine. The final focused subscription/agent/execution suite passes 243 tests. Broad Mac runs report 5,076 unit passes with one audio-default failure and 186 integration/eval passes with four function-inventory failures; unchanged main reproduces the same one/four failures. Nine detached-checkout policy tests, 226 JarvisKit tests and ten native route-control tests pass. The broader native capture failure also reproduces on unchanged main. These results do not claim a green full Mac deployment gate or complete WS-05 rollout.

- 2026-10-05 (Codex, MAR-B/D/E/F/H/I candidate): Route configuration cannot redefine native/local privacy or redirect authoritative API credentials; SAYGM catalog calls refuse redirects and use the exact catalog model, tier and advertised capabilities. Saved choices retain the static workload privacy/quality floors. Native controls preserve unavailable saved selections and bind confirmation to the exact current draft. Enabled historical-memory replay and review settlement now cross the shared confidential execution boundary, and late-delivery/settlement logs omit exception content and memory keys. Native subscription receipts and the bounded pilot harness are committed as scoped evidence, with account billing, complete source-policy coverage and representative Developer/private-memory acceptance explicitly open. No production activation or paid fallback was added. The ten native route-control tests pass; a protected-window capture failure also reproduces against unchanged main, so the deployment gate is not claimed green.

- 2026-10-05 (Codex, prospective MAR-A API metadata): On the isolated WS-05 branch claimed through #175 (`66198c5`) and audit extension #176 (`0b6723c`), the existing API factory now measures completed non-streaming calls while preserving client/response identity and arguments. Existing accounting remains its single owner; trusted local metadata supplies adapter route/billing and duration without saving content or relabeling old rows. Forty-one factory/ledger regressions pass, including actual one-row persistence, cache-control, cancellation and provider-extra spoof refusal. See [the offline receipt](../acceptance/model-use-enhancements/receipts/mar-a-prospective-api-attribution-2026-10-05.json). This is candidate code, not deployed evidence. Streaming/voice measurements, actual account billing and representative quality remain open; no production route or provider credential changed.


- 2026-10-02 (Codex, MAR-F Claude recheck): After Larry's sign-in, `/opt/homebrew/bin/claude` 2.1.278 reported Claude Max and completed a fixed public `claude-sonnet-5` prompt; the isolated Mortimer adapter returned the expected token as well. The older `~/.local/bin/claude` remained signed out. Installed bot/admin launch-agent `PATH` resolves Homebrew Claude and `.env` defines no override, but running process environment was not inspected. See the [recheck receipt](../acceptance/model-use-enhancements/receipts/mar-f-claude-subscription-recheck-2026-10-02.json). This clears the candidate text-authentication probe only; routing remains disabled and capability, billing, representative workload, privacy, and rollback gates remain open.

- 2026-10-02 (Codex, merged evidence handoff): MAR-A baseline PR #165 merged as `ecdf3a3` with all five checks passing, and MAR-E/F live-readiness PR #166 merged as `1ada011` after all five checks passed. The workstream remains in progress but has no active unmerged Codex branch; the next scoped slice must be claimed on main before implementation. Claude CLI reauthentication is a live user step; route activation remains gated.

- 2026-10-02 (Codex, MAR-E/F live readiness): On merged main `ecdf3a3`, the Mac vault-backed SAYGM catalog request succeeded with 64 models and zero advertised confidential models. Claude CLI 2.1.278 reported a signed-in Max account but both the isolated Mortimer adapter probe and a direct public-prompt CLI probe failed authentication (HTTP 401 on the direct call). Codex CLI 0.158.0-alpha.2.1 reported ChatGPT sign-in; its Mortimer adapter deliberately returned `gated` because no-tools runtime capability is not yet verified. See the [secret-free receipt](../acceptance/model-use-enhancements/receipts/model-access-live-readiness-2026-10-02.json). No route was enabled or production configuration changed.

- 2026-10-02 (Codex, MAR-A baseline refresh): The installed Mac remains on deployed `ae70f2c` while main is `bd41b5e`. Current launchd bot/admin/extractor/costs/vault PIDs match the clean deployment receipt; a read-only `ps` executable-name check confirms the production venv processes. The production checkout has zero tracked edits and five untracked entries. The routing flag and model-access override are absent from the sourced `.env` and launch-agent environment, but the running process environment itself was not inspected. Production and merged candidate each pass the Python 3.12 call-site audit at 28/28. The read-only ledger window since deployment contains 15 provider calls (8 LLM), with zero populated route, billing-source, or model-duration fields; one completed supervisor run is not a quality score. No provider call or production write was made during this aggregate baseline capture. See [`mar-a-baseline-refresh-2026-10-02.json`](../acceptance/model-use-enhancements/receipts/mar-a-baseline-refresh-2026-10-02.json). MAR-A remains open for representative quality/latency evidence, effective-routing verification, and production route/billing attribution.

- 2026-10-02 (Codex, MAR-A synthetic direct-API smoke): Ten public, tool-free, capped calls through the provider-neutral execution boundary produced exact expected outputs in five Haiku voice-supervisor and five Sonnet analyst fixtures. Median call durations were 508.3 ms and 994.0 ms; nearest-rank p95 is the sample maximum (617.0 ms and 1184.3 ms) with only five calls per model. The [receipt](../acceptance/model-use-enhancements/receipts/mar-a-synthetic-direct-api-2026-10-02.json) records route/billing metadata and token counts but no response text or credential. This is a narrow instruction-following and latency smoke, not representative workload quality or production route/billing attribution. MAR-A remains open.

- 2026-10-02 (Codex, bounded test-stability fix, PR #162 merged as `30ac2c7`): The model-admission priority test now waits up to two seconds for the interactive waiter registered on a worker thread, polling at 1 ms intervals instead of assuming 20 zero-delay event-loop turns suffice. Its existing capacity and priority assertions remain. Thirty focused iterations and all 38 tests in `tests/unit/test_model_execution.py` passed locally; all five PR checks passed. This is a test-only change; MAR-A live route/capability evidence and rollout remain open.

- 2026-10-02 (Codex, bounded test stability claim): Larry reported an intermittent failure in `test_background_admission_reserves_capacity_and_prioritizes_interactive`. The test waits at most 20 `asyncio.sleep(0)` turns for an interactive waiter registered by `_acquire` on a worker thread. Codex will replace that scheduling assumption with a deadline-based wait in `tests/unit/test_model_execution.py`, without changing `ModelAdmissionController` or route policy. The 10-02 baseline test passed eight local repeats, which does not disprove the reported approximately one-in-four failure. This is separate from MAR-A rollout and makes no live acceptance claim.

### Remaining bounded implementation boundaries — 2026-10-06

These open gates are not waived by the passing candidate tests:

- **Typed source policies (MAR-D/G):** Claim the local registry/executor contract before editing it. A host-issued tool-result envelope must bind source scope and privacy to the exact parent/task/tool-call, with source policy joined to input/workload floors before any run log, UI event, derived instruction or provider continuation. Unknown/mismatched newly acquired source defaults confidential. Provider JSON cannot approve itself; verified authorized repository reads remain approved external. Negative tests must cover pre-result sinks as well as the model continuation. Preserve routing-off compatibility without claiming it confidential.
- **Council identity (MAR-B/G):** The candidate enabled-route guard rejects duplicate canonical identities before provider construction. Extend the authoritative legacy loader/member selection only after its path is claimed and reviewed; the globally-off legacy path is still open. Judge/proposer independence uses identity, never profile name.
- **Workload limits (MAR-B/C/J):** Current request deadlines, tool counts, API token requirements and isolated pilot reservations are not a general spending policy. Reserve any added workload keys first. Subscription runtimes must refuse limits they cannot enforce; model-call estimates do not prove account charges. No exhaustion or limit failure may select a paid fallback implicitly.
- **Real Developer pilot (MAR-F/I):** Use the actual isolated sandbox driver through the existing permission/draft loop and exact real tool schemas. Obtain its own immutable capability receipt; the public fixture receipt cannot authorize it. Verify source policy, required constraints, cancellation, cleanup, consolidated parent ownership, quality and rollback. Text-only or no-op mocks cannot establish developer acceptance.
- **Research and private-memory acceptance (MAR-E/I/J):** Pin the same source/scorer/framework before and after measurements, compare equivalent baseline/candidate cases, and report schema failure separately from factual quality. Source-packet synthesis does not establish full research retrieval. Use a catalog-confirmed compliant route for confidential synthetic memory; current SAYGM catalog offers none. Account allowance/paid-overage and physical/spoken checks remain Larry's gates.

## 1. Lock the scope and intended outcome

Mortimer will support three model-access routes:

- **Subscription:** Official Claude and Codex runtimes authenticated through Larry's accounts.
- **Direct/provider API:** Existing Anthropic, OpenRouter, Moonshot, and other configured API routes.
- **SAYGM API:** Confidential inference or upstream-provider routing, explicitly distinguished.

The user will be able to configure the route for each model and override it for
particular workloads.

SAYGM confidential inference will be preferred for sensitive sub-agent work when
the selected model meets quality and capability requirements. Subscriptions will
be preferred for eligible work where their privacy characteristics are acceptable.

**The current Haiku voice supervisor, Deepgram transcription, and ElevenLabs
voice generation remain on their existing routes.** Replacing them is outside
this implementation.

The existing Mac remains the control center. No additional hardware or locally
hosted language model is required.

## 2. Establish the actual deployment baseline before changing routing

The running backend inspected on 2026-09-20 used the installed checkout, while
the release candidate contained newer memory-routing code. Resolve that
discrepancy first. This is a dated observation, not a permanent description of
the deployment.

The implementation must:

- Record the running backend paths, revisions, launch-service configuration, and interface build.
- Inventory every model call site, including background jobs and synchronous clients.
- Identify the release containing the accepted interface and automated-memory changes.
- Consolidate the intended backend changes through the existing release process.
- Confirm that background memory work uses its dedicated profile rather than inheriting the Haiku supervisor setting.
- Capture baseline quality, latency, errors, and usage before introducing new routes.

Do not overwrite local patches or assume the newest-looking interface proves
that the backend is current.

**Completion evidence:** One documented release identity, verified running
service paths, and an inventory mapping every workload to its effective model
and route.

## 3. Separate model identity, access route, and workload policy

Extend the existing model registry rather than creating a competing model list.

A **model record** must contain:

- Stable canonical identity.
- Display name and provider-specific model identifiers.
- Required quality tier.
- Verified capabilities: text, images, tool use, structured output, streaming, and cancellation.
- Available access routes.

An **access-route record** must contain:

- Unique route identifier.
- Adapter type: direct API, SAYGM, Claude subscription, or Codex subscription.
- Authentication reference; never the credential itself.
- Billing source.
- Availability and authentication status.
- For SAYGM, catalog tier and upstream provider.
- Capability-validation results and their date.

A **workload policy** must contain:

- Selected model and route.
- Minimum quality and required capabilities.
- Permitted data destinations and required privacy level.
- Priority, deadline, and queue behavior.
- Explicitly allowed fallback routes.
- Spending limit where applicable.

A model reached through two routes remains **one model identity**, particularly
for council independence.

Existing configured model names must not be silently replaced with whatever a
subscription happens to expose.

## 4. Make route selection deterministic

Use this fixed selection order:

1. Resolve the workload and its policy.
2. Apply an explicit per-task selection, if present.
3. Otherwise apply the workload override, then the model's configured default route.
4. Check privacy, allowed destinations, quality, and capabilities.
5. Check authentication, capacity, and spending limits.
6. Execute, queue, or return a specific unavailable-route status.

An explicit selection that fails validation must remain visible as unavailable.
Do not substitute a different model.

Automatic fallback is disabled by default. An enabled fallback must meet the
same privacy and quality requirements and be explicitly listed in the workload
policy.

**Subscription exhaustion must never silently trigger paid API usage.**

## 5. Implement one execution boundary for all model routes

Introduce a shared execution layer between workloads and provider adapters.
Retain the existing API client behavior behind the direct-API adapter.

The execution layer must accept a standard task containing:

- Workload, task, and parent-request identifiers.
- Selected model and route.
- Instructions, context, attachments, and output requirements.
- Permitted tools.
- Data-policy labels.
- Deadline and cancellation signal.

It must return normalized events for:

- Queued and started.
- Progress and text output.
- Tool requests and results.
- Artifacts.
- Completion, cancellation, and failure.
- Usage, billing source, and timing.

Existing result grouping must use the parent-request identifier so one
development request continues to produce one consolidated result area.

Provider differences belong inside adapters. Agent implementations must not
acquire provider-specific authentication or fallback logic.

Subscription runtimes may manage their own internal reasoning/tool loop, but
**every tool operation must pass through Mortimer's existing permission and
sandbox boundary**. Unrestricted built-in shell, filesystem, network, or
delegation tools must not create an alternate execution path.

If a runtime cannot enforce that boundary for a workload, mark that combination
unsupported.

## 6. Integrate SAYGM with explicit privacy distinctions

Add a SAYGM adapter using its documented interfaces. Discover supported models
and metadata from its catalog.

Store the SAYGM credential in the existing Mac vault. Use separate keys where
different guardrail policies are required.

Expose three distinct route descriptions:

- **SAYGM confidential inference**
- **SAYGM gateway → named upstream provider**
- **SAYGM open-model route → named upstream provider**

Only a catalog-confirmed confidential route may satisfy a confidential-inference
requirement. A `-TEE` suffix alone is insufficient evidence.

Enable and test applicable SAYGM redaction controls; they are documented as off
by default. Redaction is an additional safeguard, not proof that sensitive
content cannot escape. See the [SAYGM privacy model](https://docs.saygm.com/security/privacy/)
and [guardrails](https://docs.saygm.com/platform/guardrails/).

Keep these verification states separate:

- Provider-documented protection.
- Catalog metadata checked.
- Compatibility tested.
- Attestation independently verified.

Never display "attestation verified" unless verification actually occurred.
At the time of this plan, the documented buyer-facing verification interface
was not yet generally available; record that limitation without inventing a
substitute. Recheck the [SAYGM attestation documentation](https://docs.saygm.com/security/attestation/)
during implementation.

SAYGM usage must be recorded as paid API usage against its own credits,
separate from subscription consumption. See [SAYGM billing](https://docs.saygm.com/platform/billing/).

## 7. Integrate subscriptions through official runtimes

Use the official Claude runtime/Agent SDK and Codex SDK or app-server
interfaces. Pin tested versions.

Authentication must use the provider's own sign-in flow. Mortimer must not
collect browser cookies or copy subscription tokens into the project vault.

Subscription processes must have isolated environments so inherited API keys,
endpoint overrides, or provider configuration cannot unintentionally select
paid API access.

For each subscription route:

- Verify the authenticated account and access mode using supported mechanisms.
- Discover or validate available models.
- Confirm tool, image, structured-output, and cancellation support before enabling dependent workloads.
- Surface expired authentication and exhausted allowance distinctly.
- Record unavailable usage-limit information as unknown.
- Disable paid overage where supported and verify the relevant setting before claiming subscription-only operation.

Unavailable exact models remain unavailable. A replacement requires a recorded
model-selection change.

The supported mechanisms and account restrictions must be rechecked during
implementation against the official [Claude guidance](https://support.claude.com/en/articles/15036540-use-the-claude-agent-sdk-with-your-claude-plan),
[Claude authentication restrictions](https://code.claude.com/docs/en/legal-and-compliance),
and [Codex integration documentation](https://learn.chatgpt.com/docs/codex-sdk).

## 8. Enforce privacy before transmission and on results

Place policy enforcement locally, before every outbound model request and
external tool call.

Use three requirements:

- **Local only:** Content cannot leave the Mac.
- **Confidential inference required:** Content may reach approved confidential inference routes.
- **Approved external processing:** Content may reach specifically permitted external providers.

Determine requirements from workload policy and source metadata. Newly
introduced, unlabeled private documents, memory records, and attachments
default to confidential processing. Public sources can be marked for approved
external processing.

Do not send content to an external model merely to decide whether it is
sensitive. Automated content detection may tighten policy but must not
downgrade it.

When context is combined, retain the strictest applicable restrictions. Tool
results and model outputs inherit the restrictions of their inputs unless an
explicit, tested transformation permits a narrower release.

Apply this to:

- Prompts and conversation history.
- Retrieved memories and documents.
- Images and screenshots.
- Tool arguments and results.
- Council proposals and evaluations.
- Provider-side session history.
- Logs, telemetry, and error reports.

Check new tool results **before** they are fed back into a model. If a tool
retrieves content that the current route cannot receive, stop that continuation
and use only an explicitly permitted route or queue the task.

Secrets remain available only to the tools that need them; they must not enter
model context.

## 9. Preserve the voice supervisor while controlling confidential handoffs

Haiku continues to manage ordinary conversation and delegation.

For confidential sub-agent work:

- Pass an opaque task or document reference where possible.
- Let the authorized sub-agent retrieve the sensitive material directly.
- Return the full result to Mortimer's existing local response/results area.
- Give Haiku a fixed status message such as "The private result is ready," without the protected content.
- Keep that protected result out of subsequent supervisor context and ElevenLabs input unless its policy explicitly permits those destinations.

Existing memory context supplied to the supervisor must be audited and labeled.
Do not silently erase all personalization, and do not claim confidentiality
while restricted memories are still injected into Haiku's prompt.

The UI must distinguish **confidential delegated processing** from **an entirely
private conversation**. Existing speech may already have been processed by
Deepgram and Haiku; the new routing cannot undo that exposure.

This phase changes data handling where required, but does not replace the voice
providers or redesign the voice interaction.

## 10. Apply workload defaults without reducing quality

Configure the initial rollout as follows:

- **Voice supervisor:** Existing Haiku API route.
- **Memory extraction, consolidation, private-document analysis:** Prefer qualified SAYGM confidential models.
- **Librarian and other agents handling private records:** SAYGM confidential routes when their inputs require them.
- **General research and synthesis:** Subscription route where the data policy permits it.
- **Development and application building:** Subscription route for approved project content; confidential route where the project's policy requires it.
- **Scheduler and Systems:** Select by the information involved, not merely the agent's name.
- **Council:** Eligible subscription, SAYGM, and existing API members; each member must satisfy the task's data policy.
- **Vision:** Enable each route only after image-input tests.
- **Deepgram, ElevenLabs, Tavily, and unrelated integrations:** Existing routes remain.

No agent may fall below its existing quality floor.

If a confidential model cannot meet the required quality or capability, report
the workload as unavailable under its current policy. Do not silently send it
to a frontier provider or a weaker model.

## 11. Treat latency as a task-level acceptance criterion

Approximately one additional second for a delegated task is acceptable if
quality and privacy requirements are met. It is not permission to add one
second to every sequential model call without measuring the cumulative effect.

Measure:

- Queue time.
- Time to first useful output.
- Total task completion time.
- Per-call time and number of sequential calls.
- Tool execution time.
- Cancellation time.
- Median and 95th-percentile results.

Initial acceptance targets:

- Show a local acknowledgment or working state within **250 ms** under normal load.
- For short interactive sub-agent tasks, target **no more than one second additional median completion time** against the baseline.
- Flag **more than two seconds additional 95th-percentile delay** for review before changing defaults.
- Evaluate research and development using total completion time and quality, not a universal one-second threshold.
- Queue background memory maintenance behind interactive work without losing pending exchanges.

Benchmark cold starts and warm sessions separately. Do not reuse sessions
across unrelated privacy boundaries to improve timing.

Reserve execution capacity for interactive work. Background jobs must not
exhaust all subscription concurrency or interfere with audio processing on the
16 GB Mac.

## 12. Add controls within the existing console

Extend the current model/settings area. Do not create a replacement console or
remove existing sidecar content.

Provide:

- Model and route selection.
- Workload overrides.
- Privacy requirement and permitted destinations.
- Explicit fallback configuration.
- Authentication, capacity, and route-health status.
- SAYGM credit/cost information and subscription limits when available.
- A connection test using synthetic content.

Show each task's effective model, route, billing source, and privacy status in
its existing result details.

Preserve voice control for selecting configured routes and requesting status.
Route changes made by voice must use the same validation as changes made
visually.

Reuse the existing response window, parent-request grouping, multi-monitor
routing, typography, and Liquid Glass settings. Preserve the orb and its
speaker-state behavior.

## 13. Preserve execution, memory, and failure behavior

The implementation must retain:

- Sandbox isolation and existing tool permissions.
- Current self-edit behavior: work may start after the spoken preview, with the established PR approval boundary.
- Existing automated-memory admission, deduplication, and recovery behavior.
- Persistent pending work across restarts.
- Cancellation and visible progress.
- Existing council identity and self-judging restrictions.

Normalize failures into actionable categories: authentication required,
allowance exhausted, insufficient credit, unsupported model/capability,
privacy-policy mismatch, timeout, provider failure, and cancellation.

Failed or interrupted model calls must not blindly replay tools that may have
already changed state. Reconcile recorded tool execution before resuming.

Sensitive payloads must not be included in ordinary usage logs. Record
identifiers, route decisions, timings, and error categories sufficient to
diagnose problems.

## 14. Implement in gated stages

Each stage should be independently reviewable and reversible. All stages are
open when this plan is recorded; saving the document closes no implementation
or acceptance requirement. Use the `MAR-` identifiers below consistently in
future status updates.

- [ ] **MAR-A — Baseline:** Reconcile deployment, inventory call sites, capture measurements.
- [ ] **MAR-B — Contracts:** Add model/route/workload records and validation. Existing routes retain their behavior.
- [ ] **MAR-C — Execution boundary:** Wrap existing API execution and prove behavioral parity.
- [ ] **MAR-D — Privacy enforcement:** Add input, tool-result, output, and logging controls.
- [ ] **MAR-E — SAYGM:** Add catalog discovery, credentials, compatibility checks, and synthetic tests.
- [ ] **MAR-F — Subscriptions:** Add official runtime adapters and authentication isolation.
- [ ] **MAR-G — Workload integration:** Migrate all non-voice model call sites, including memory and council paths.
- [ ] **MAR-H — Console:** Add configuration, status, and voice-accessible controls.
- [ ] **MAR-I — Pilot:** Enable one research workload, one development workload, and one synthetic confidential-memory workload.
- [ ] **MAR-J — Rollout:** Expand defaults only after the quality, privacy, and latency gates pass.

Do not test production confidential data on an unvalidated route. Do not add
automatic production shadow calls that duplicate private content or charges.

Rollback must preserve privacy restrictions. If the previous software cannot
enforce an active restriction, pause that workload instead of routing it
through an older unrestricted path.

## 15. Require evidence before closing the work

Automated and live acceptance must demonstrate:

- Manual route selection is honored.
- Unavailable models are not silently substituted.
- Subscription calls do not inherit API authentication.
- Exhaustion causes the configured queue/failure behavior without paid fallback.
- Confidential content cannot reach disallowed models through prompts, tools, results, council calls, or logs.
- SAYGM frontier routes are never labeled confidential inference.
- Cancellation, restart recovery, and tool execution remain correct.
- Council members remain independent by canonical model identity.
- Memory work does not fall back to the voice model.
- Existing interface, orb, result grouping, and monitor behavior remain intact.
- Latency and quality meet the workload-specific acceptance criteria.
- The deployed build and effective configuration match the tested release.

Update the existing architecture documentation, roadmap, gap-closure plan, and
implementation status documents with one shared set of item identifiers.
Keep open items at the top and completed items below, with evidence links.

Mortimer's self-edit context and the user-visible architecture view must expose
the same routing rules, configuration ownership, and limitations.

**Completion means the routes are configurable, policy-enforced, tested,
deployed, and documented. An adapter existing in the repository alone does not
close the item.**


## 16. Progress log

### 2026-09-29 — WS-05 MAR-A baseline reconciliation

- Confirmed production deployment receipt and app bundle revision match production checkout `eb24e81`; launch agents report loaded, but current process identity was not independently verifiable.
- Ran the production Python 3.12 model-call-site audit: 28 covered, zero review-required.
- Captured aggregate-only usage/cost totals and workload counts. The ledger has no duration, quality score, or route/billing attribution.
- Added the evidence and limitations to [`mar-a-baseline-2026-09-29.json`](../acceptance/model-use-enhancements/receipts/mar-a-baseline-2026-09-29.json). MAR-A stays open pending a safe, approved measurement method and the missing metrics.
- No provider calls, feature activation, credential changes, prompt/response reads, or production writes.
