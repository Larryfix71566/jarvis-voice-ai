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

**Stage status:** MAR-A is in progress because the deployed checkout still
needs release reconciliation. MAR-B has its initial model/route/workload
contracts and MAR-C has the provider-neutral text execution contract. MAR-D
has local privacy enforcement and enabled-mode confidential/local-only
sub-agent run-log redaction, council call policy enforcement, and protected
council payload redaction. Delegation status events also redact protected task
text before stdout/UI emission, and the shared MCP registry blocks external
servers during an armed sensitive turn before invocation. The remaining audit
covers detached continuation and provider-specific result sinks.
MAR-E has catalog parsing, vault allowlisting,
and API-compatible routing; live credential/catalog verification remains open.
MAR-F has gated text-only Claude and Codex subscription adapters; their child
processes strip inherited API credentials and endpoint overrides before launch.
A synthetic
read-only Codex probe succeeded using the authenticated default model, while
the Claude probe reports that the CLI is not logged in. The prior OpenRouter
Codex model identifier was rejected by the subscription account. Claude
re-authentication, model capability evidence, and tool-preserving execution
remain open. MAR-G
through MAR-J remain open.

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
