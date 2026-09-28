# Mortimer Skills workspace and skill creation implementation plan

Status: **approved direction; implementation in progress in an isolated candidate worktree**. Prepared 2026-09-25; reconciled 2026-09-27.

This is the implementation contract for the agreed Skills library, inspectable
processes, truthful execution history, and sandboxed skill creation. The current
candidate includes the parser/catalog/activity APIs, native library/process
views, pinned creator execution, authenticated sandbox drafting and validation,
exact-diff review, explicit digest-bound PR opening, and cancellation. Bounded
voice navigation/example preview and draft handoff are implemented in the
candidate; live voice acceptance, live-VM lifecycle acceptance, trusted process
events, live evaluation, activation/rollback, and full Mac acceptance remain open; see
the living [acceptance status](../acceptance/skills-workspace/STATUS.md) for
exact files and test receipts. This plan is not evidence of installation,
activation, full acceptance, or release. Implement in a dedicated worktree;
preserve concurrent work. Acceptance gates remain open until their full evidence
is recorded.

## 1. Outcome and scope

Larry can ask Mortimer to show its skills, inspect what a skill does, understand
why it was selected, follow an actual execution, and develop a new skill using
the reviewed skill-creator. The same functions work through voice, keyboard,
and pointer. The interface shows what is available, what is blocked, and what
actually happened without requiring the user to manage routine classification.

The first complete journey is skill creation. Finish and accept it before
developing additional task-specific skills. Existing skills remain usable.

This plan includes catalog discovery, package integrity, selection, references,
readiness, creator adaptation, evaluation, activation review, version history,
rollback, native presentation, voice actions, and display placement. It excludes
a general visual workflow editor, arbitrary code execution, bulk importing or
enabling Claude's repository, new provider authentication, and deployment of
home, surveillance, or investing automations.

## 2. Design decisions implementers must preserve

1. **Skills, workflows, and tools are different objects.** Skills supply reusable
   expertise; workflows express required procedure and completion criteria;
   tools perform executable actions. A skill can support several workflows.
   Existing `jarvis/workflows.py` workflows are prompt guidance, not an enforced
   state machine. Label them accordingly. Only the bounded creator lifecycle
   defined here gains code-enforced transitions; do not build a generic DAG engine.
2. **Intended process and observed execution are separate.** The Process tab
   describes the reviewed method. Activity shows recorded events. An instruction
   saying “validate” does not prove validation happened. Model-reported progress
   cannot mark a check passed or authorize publication.
3. **Native integration.** Extend SwiftUI/AppKit Command Console. Reuse its
   navigation, theme/Liquid Glass, accessibility, shared actions, results and
   display placement. Do not replace the app, introduce another daemon, add a
   WebView-based dashboard, or change the frozen web console.
4. **Preserve existing experience.** Keep compact Conversation startup, the
   connected/idle/muted orb behavior and speaker colors, all sidecar content and
   scrollable headers, clock placement, response/result ownership, sharing,
   automated memory, Atlas, developer-result aggregation, and hot-plug recovery.
   A background skill event never steals focus or opens a window.
5. **One owner per kind of state.** Backend owns catalog/readiness/lifecycle and
   run evidence; native stores are presentation caches. Existing workspace and
   display stores own content placement. Do not create another voice session,
   result ingestion path, model router, approval engine, or sandbox.
6. **Provider-neutral and bounded.** Reuse workload model/access/privacy policies.
   Subscription text adapters remain text-only. A skill cannot enable tools,
   select a less private route, widen permissions, or cause paid API fallback.
7. **Sandbox first, activation separately reviewed.** The existing behavior of
   starting authorized self-edit work after the spoken preview is preserved.
   Do not add a second generic spoken confirmation before sandbox drafting.
   Merging and releasing an enabled version remain the final human boundaries.
8. **Versioned, truthful status.** Installed, enabled, ready, tested, and deployed
   mean different things. A passing offline test is not live acceptance. A PR
   being open or merged does not mean the running Mac has loaded that version.
9. **One reviewed skill at a time.** Pin upstream provenance and retain licensing.
   Installation never silently activates a skill. No live mutable upstream sync.
10. **No hidden design changes.** If a required dependency or contract cannot be
    met, record the blocker and continue independent work. Do not remove a gate,
    fabricate evidence, relax a privacy tier, or substitute an incompatible UI.

### Approved dashboard and process interaction

The agreed presentation is one Skills workspace with a scannable library as its
landing view and a focused detail view for the selected skill. The library
answers “what is available, what is it for, and can I use it now?” The detail
view lets the user inspect the skill's intended procedure one step at a time,
then compare that design with recorded activity when a run is selected. This is
the approved interaction direction, not permission to replace the existing
Command Console or introduce a second skills application.

Keep these concepts visibly distinct throughout implementation:

- **Skill:** reusable domain instructions and declared resources.
- **Workflow:** a named procedure or completion standard. Existing workflows
  remain guidance unless a specific bounded lifecycle is enforced by code.
- **Tool:** an executable capability with its own permission and runtime
  boundary.
- **Intended process:** the reviewed ordered steps and labelled branches in the
  skill metadata. It is not evidence that a run followed or completed them.
- **Activity:** events and receipts actually recorded for one run. Missing
  instrumentation is shown as “Not recorded” or “No skill trace recorded,”
  never estimated from model narration or elapsed time.

The library is the dashboard; clicking, speaking, or keyboard-selecting a card
opens that skill's detail. The Process tab uses a readable ordered list as its
primary representation. Selecting a step persistently focuses it and exposes
its purpose, inputs, tools, outputs, approval boundary, success criteria, and
known evidence state. “Next” follows the metadata edge; at a branch, show the
condition and destination choices and let the user choose. A compact flow map
may supplement the list when useful, but must not become a generic workflow
editor or the sole way to understand the process.

Keep this as one responsive native experience: preserve the existing compact
Conversation/orb startup and sidecar, reuse shared display/result ownership,
and support pointer, voice, keyboard, and VoiceOver paths for the same actions.
At narrow widths or large text sizes, use list-to-detail navigation with Back;
at wider widths, use the library pane beside the detail. Moving a detail view to
another display transfers its presentation ownership and selection state; it
must not duplicate windows, interrupt a run, or steal focus. Existing privacy,
approval, tool, sandbox, memory, routing, and release boundaries remain in force.

For model handoff, implement in dependency order: establish truthful package
and readiness data; expose the read-only catalog/detail/run APIs; deliver the
native dashboard and intended-process/activity distinction; then add creator,
evaluation, activation, and rollback capabilities behind their separate gates.
Do not expose controls for a later phase merely because its UI can be drawn.
When a capability lacks backend evidence, show a specific unavailable/unknown
state and continue the independent read-only work.

## 3. Verified starting point

Inspected the isolated worktree at HEAD `977f50b` plus its existing uncommitted
changes on 2026-09-25. This is a working snapshot, not a frozen release candidate.
Recheck these facts before editing; record the new base and any differences.

- `jarvis/agent_skills.py` discovers root `skills/*/SKILL.md`, with explicit
  enablement from `config/skills.yaml` and `JARVIS_AGENT_SKILLS_ENABLED` kill
  switch. `jarvis/skills/` is the separate MCP server registry, not this library.
- Five skills are present and enabled: `git-history-and-status-review`,
  `current-weather-with-fahrenheit`, `layered-geolocation`,
  `technical-plan-document`, and `mcp-server-authoring`.
- Matching uses name/description token overlap, threshold 0.30, at least two
  shared tokens, and one injected skill. Skill bodies load on selection.
- `_split_frontmatter` splits again on later Markdown separators, losing the
  remainder of a body. A locally available Anthropic creator parsed as valid
  while loading only 2,919 body characters from a 33,168-character source and
  omitting “Creating a skill.” Validation alone is insufficient today.
- Bundled scripts are reported unavailable; the loader cannot execute them.
  References/assets are not a general supported progressive resource system.
- The knowledge API exposes skill counts and enabled names. The native client
  has no dedicated library/process/activity workspace.
- `skills/**` and `config/skills.yaml` are denied to normal self-edit. Sandbox
  `Runtime`, `Session`, `WorkspaceFiles`, verifier and publisher already provide
  isolated candidates, host-owned checks, immutable receipts and resumable PRs.
- `RunLogger` records real tool calls/results, but no complete skill selection
  and step-evidence contract exists. Some diagnostic skill logs deliberately
  omit names; do not reverse that privacy hardening.
- The upstream `skill-creator` exists in the user's Claude/Codex skill locations;
  that does not install it in Mortimer. It assumes capabilities requiring review
  and adaptation, including evaluation scripts and model invocation.

Usage review supports prioritizing development, repository review, plans,
research/weather, and memory/interface work. Home, surveillance and investment
skills are roadmap candidates, not demonstrated current skill coverage. Do not
copy private transcript excerpts into committed examples or evaluation fixtures.

### Relationship to existing plans

This plan supersedes the **skill-authoring portion** of
[Mortimer Skill Authoring](MORTIMER_SKILL_AUTHORING_PLAN.md), including its
proposed blanket `skills/**` allowlist move and separate `skill-authoring` name.
Use one canonical `skill-creator`, not competing creator skills.
It extends [Skill Library](MORTIMER_SKILL_LIBRARY_PLAN.md) only for reviewed
references and the sandbox operations specified here; the loader remains
non-executable. Earlier measurements remain historical evidence, not new gates.

It augments [Platform Roadmap](MORTIMER_PLATFORM_ROADMAP.md) track T6/G6(a,c),
without closing or changing G6(b) or unrelated tracks. The
[Command Console/Atlas contract](MORTIMER_COMMAND_CONSOLE_ATLAS_PLAN.md),
[current gap plan](MORTIMER_CURRENT_REVIEW_GAPS_IMPLEMENTATION_PLAN_2026-09-25.md),
[next gaps](MORTIMER_NEXT_GAPS_IMPLEMENTATION_PLAN_2026-09-25.md), and
[subscription isolation plan](MORTIMER_SUBSCRIPTION_RUNTIME_ISOLATION_PLAN_2026-09-25.md)
retain their existing acceptance boundaries. This document governs new Skills
behavior; a conflict with an existing security or release contract is a blocker
to the affected increment, not permission to weaken that contract.

## 4. Package, catalog, and readiness contract

### Package format and identity

Keep standard `skills/<slug>/SKILL.md`. Add an optional version-1
`mortimer.yaml` companion with strictly validated fields:

- `schema_version`, `skill_id` (same slug as frontmatter), `display_name`,
  `category`, `version` (human-readable only), `source` (URL, immutable revision,
  license identifier/path, source digest, adaptation notes).
- `capabilities`, `required_tools`, `required_credentials` (names only),
  `reference_paths`, `example_ids`, `related_workflow_ids`, `compatible_with`,
  and `process`.
- `process` contains at most 32 nodes with stable `step_id`, title, description,
  input/output descriptions, tool IDs, approval description, success criteria,
  and ordered edges with optional condition labels. No executable expressions.
  `kind` is `linear`, `branching`, or `guidance`; edges must reference existing
  IDs, with no cycles in v1. Repeated attempts belong to Activity, not a cycle.
- Examples are reviewed, public/synthetic fixtures with purpose and expected
  result, never commands automatically executed on opening a detail page.

No companion is required for the existing five skills. Their fallback process
is “Instruction-based skill; no reviewed step map.” Do not infer a workflow by
calling a model when the user opens a skill. Adding reviewed companion metadata
for them is part of this plan; preserve their instructional behavior.

Canonical revision is SHA-256 over sorted package-relative paths and exact
file bytes, including the companion and resources, excluding nothing executable
by policy. Reject symlinks, traversal, duplicate/case-colliding paths, nonregular
files, invalid UTF-8 text and unknown companion keys. Git commit and package
revision are separate. Snapshot the full selected package revision at run start
so an in-flight run cannot mix old instructions with new resources.

Fix frontmatter parsing using an exact delimiter line at the start and the
first exact closing delimiter line; preserve every remaining byte of the body
before the existing presentation trim. Cover LF/CRLF, Markdown rules, diff
headers, malformed/missing delimiters, and long source bodies. Never silently
truncate. Files over the admission limits are blocked with a reason.

Initial limits: 128 files/10 MiB per package, 128 KiB per instruction/reference
text file, 16,000 total injected characters per run across all selected skill
bodies/resources. Resources count toward the same budget. Split the creator
into reviewed concise instructions and on-demand references. Do not solve the
upstream length issue by increasing the supervisor's prompt indefinitely.
Package version changes invalidate prior readiness/evaluation attestations.

### Registry ownership and states

`config/skills.yaml` remains the reviewed source of enablement truth. Extend it
compatibly with `schema_version: 2`, existing `enabled` names, and a `revisions`
map from enabled slug to expected package digest. Migrate all five atomically
with matching digests before switching on the new loader. Legacy config remains
supported only in legacy mode; v2 mode rejects missing/mismatched pins per skill.
One broken package must not hide the rest of the library.

Expose independent fields, not a single misleading green badge:

- `installation`: `installed`, `candidate`, `catalog_only`, `invalid`.
- `enabled`: boolean, reflecting the running validated configuration.
- `readiness`: `ready`, `blocked`, `unknown`; include typed reason codes.
- `verification`: `not_tested`, `offline_passed`, `live_passed`, `failed`, `stale`.
- `publication`: `none`, `draft`, `awaiting_review`, `merged_pending_release`,
  `loaded`, `failed`; include safe PR link and observed loaded revision.

Readiness checks package integrity, route capabilities/privacy, required tool
availability, credential presence via existing host services, sandbox profile,
and revision-bound evidence. It does not run provider calls, expose secret values,
or assert credentials work from mere presence. Unknown authentication is shown
as unverified; a sandbox-only skill can be ready for draft while live evaluation
is explicitly blocked. Refresh on relevant config/tool/route changes and on
explicit refresh, with a 60-second cached snapshot; no polling of providers.

## 5. Selection and resources

Phase one preserves the existing lexical matcher. Record candidate score,
threshold outcome, selected revision and capability refusal as structured
selection evidence. “Why this skill?” displays this factual explanation, not
private chain of thought or a newly invented rationale.

Then add a feature-gated deterministic selector with these fixed rules:

1. User-explicit selection takes priority but never overrides disabled state,
   capability/privacy/readiness, or a workflow/tool policy. Clearly report refusal.
2. Automatic candidates must meet the current lexical threshold and shared-token
   floor, pass readiness, and match reviewed capability tags against the owning
   agent/tool inventory. Add curated aliases/positive trigger fixtures for intent
   coverage; no model request or embedding service in the voice hot path.
3. Select one primary. Allow at most one supporting skill only when both companion
   manifests explicitly declare compatibility, the supporting skill independently
   qualifies, and the combined body/resource budget fits. Stable tie-break is
   score descending then slug ascending. Duplicate candidate skill IDs make the
   package body ambiguous and must refuse the entire selection independent of
   input order. Otherwise retain only the primary and
   record why. Existing skills remain single-selection unless reviewed otherwise.
4. Required workflows retain their existing precedence. Resource content cannot
   change tool access, user permissions, privacy, or runtime policy. Never silently
   drop a required workflow to fit another skill. If skill text cannot fit, omit
   optional support first, then refuse that skill with a bounded explanation.

Keep anti-trigger phrases in bodies/test fixtures, not matchable descriptions;
reconcile the contradictory checklist in `skills/README.md`. Add explicit
conflict and overlap fixtures, including non-skill queries such as “what is the
plan for today.” Preserve the existing five skills' positive and negative cases.

Reference reads use a new bounded `skill_reference_read` tool through the
existing tool registry: arguments are active `skill_id`, snapshotted `revision`,
and a declared package-relative reference path. No URLs, absolute paths, globbing,
or arbitrary filesystem reads. Return validated UTF-8 content with remaining
budget; refuse an over-budget read rather than truncate required instructions.
Assets are inert previews through existing attachment validation. Opening a
library card must never read every reference or start any script.

## 6. Creator integration, sandbox and model execution

### Reviewed first package

Vendor/adapt only upstream `skill-creator`. Pin the exact upstream commit and
package digest during implementation; a moving `main` URL is a research pointer,
not a usable lock. Keep its license/attribution and record the imported files.
Adapt provider-specific prompts, triggering optimization, output locations, and
review interfaces to Mortimer. Remove assumptions that Claude CLI, a browser
server, or unrestricted host tools are available. Each removed/replaced feature
must be listed with its Mortimer equivalent; do not label a partial import ready.

Use the upstream ideas of drafting, with/without-skill comparison, objective
evaluation and iterative refinement. Render evaluation results in native detail
and results views. Do not execute the upstream CLI invocation scripts unchanged
or start its review server on the host.

### Bounded lifecycle (backend authority)

`requested → inspecting → drafting → validating → evaluating → review_ready →
pr_open → merged_pending_release → active`

`blocked`, `failed`, and `cancelled` are explicit outcomes at the relevant stage.
A validation/evaluation failure returns to a new draft revision only on a retry
request. Each retry has a new attempt ID linked to the same development request.

- Inspect: check existing skills and learned procedures for merge/reuse. Show
  the proposed scope, expected artifacts, privacy class and test budget.
- Draft: author in the existing sandbox session; do not write the live library.
- Validate: schema, complete body, paths, license, resource references, matcher
  fixtures, dependency profile, and allowed diff must pass host-owned checks.
  Matcher fixtures use inert `tests/fixtures/skills_authoring/<slug>/matcher-cases.json`
  with schema version 1 and 2–32 cases of exactly `{id, request,
  expect_selected}`. IDs must equal the companion manifest's `example_ids`,
  requests are bounded synthetic/public text, and the set must include both
  `true` and `false` expected selection outcomes. The host parses JSON only;
  it does not execute fixture content. Adapted/imported source must include its
  declared license file. Required tools must exist in the complete static host
  tool inventory; incomplete inventory is not a pass. Package scripts and
  executable dependencies are rejected in v1.
- Evaluate: run public/synthetic cases with and without the candidate using the
  same route/model/inputs/tool fixtures; record both outcomes and all failures.
  In the SW-G paired runner, a trial artifact is a bounded text response plus
  its frozen case/repetition identity, rubric criteria, route metrics, and
  blinded condition linkage. Deterministic artifact checks validate the exact
  fixture ID and SHA-256 against a host-owned allowlist before route resolution,
  required 24-trial coverage and pairing, nonempty bounded
  response text, complete rubric metadata, and complete bound metrics. This
  response record is not a generated skill package and cannot prove package
  validity. When a workflow actually drafts a package, SW4's host validator
  and sandbox receipts are the only package-validity evidence; never infer a
  valid package from model prose or invent a text-to-files format for SW-G. To
  revise evaluation cases, add a new versioned fixture ID and reviewed digest;
  never replace an accepted digest in place.
- Review: show exact diff, digest, comparisons, limitations and candidate results.
  “Ready for review” is not “activated.”
- Publish: reuse independently verified sandbox publication. Create/resume one
  PR per creator attempt. No automatic merge, deployment or activation.
- Activate: observe the approved configuration/package in a released checkout,
  verify all pins, build a complete registry snapshot, then atomically swap.
  Keep the previous snapshot on failure. Existing runs finish on their snapshot.

Normal development retains `skills/**` and `config/skills.yaml` protections.
Implement a **host-issued scoped skill-authoring policy** passed through the
existing sandbox `allowed` callable: only `skills/<approved-slug>/**` and that
skill's public fixtures may change in this session. All paths still pass the
sandbox source/secret scanner. It cannot edit the policy, registry config,
validator, dependencies, sibling packages, or execution code outside that package.
This narrow policy extension itself requires a maintainer-reviewed implementation
PR; skill content cannot issue or widen it. Do not broadly remove the deny rule.

Activation configuration is a maintainer-reviewed follow-up change binding the
exact approved digest. The dashboard's “Request activation” produces a review
artifact with that exact proposed configuration diff; it does not bypass the
protected-file publisher. A maintainer can include that diff in the reviewed
release change. The UI shows “Awaiting configuration review” until this occurs.
This deliberate human boundary must be visible rather than a toggle pretending
to enable instantly. “Request rollback” uses the same reviewed path to a known
accepted package/config pair, retaining evidence. The existing global kill
switch remains the immediate operational stop; do not add autonomous rollbacks.

Reuse `sandbox/runtime.py`, `session.py`, `files.py`, `verify.py`, `profiles.py`
and `publish.py`; no second VM manager or host command fallback. One active VM
on the current hardware; additional tests queue without blocking voice. Scripts
are data until reviewed and run through named, host-installed sandbox operations.
V1 permits only validation and offline fixture evaluation operations with fixed
argv, bounded arguments, 120-second per-operation and 15-minute batch timeout.
Use prepared profile dependencies; missing dependencies block instead of allowing
installation from candidate instructions. No live vault/home/SSH/CLI-auth mount,
public network allowance, or guest-held provider credential is added.

Draft/planning model calls use existing `planning` (text) and `developer`
(tool-capable) policies. Live comparison calls use a new explicit `skill_eval`
workload, background priority, no fallback, **disabled until manually configured**
to a profile/route/privacy/capability set. Text-only comparisons can use a verified
subscription route; tool-enabled cases require a tool-capable route and the
existing controlled executor. SAYGM has no implicit confidential exemption.
Host model routing performs calls; VM outputs are inert fixture/artifact inputs,
never a command to invoke providers. A curated host evaluation runner drives the
existing agent/tool policy with sandbox-bound file operations; no tool invocation
is delegated to an unrestricted subscription CLI.

Initial live evaluation limit: 6 cases × 2 conditions × 2 repetitions = 24
top-level trials, sequentially; max 4 model calls per trial and 96 total provider
calls, 15-minute batch deadline, 4,000 output tokens per call. A paid route also
requires an explicit numeric spend ceiling before starting, checked/reserved
before each call using conservative token bounds; unavailable pricing blocks
paid evaluation. Exhaustion stops with partial evidence. Subscription usage is
tracked against these call/time budgets; do not represent list-price estimates
as a billed charge. No automatic switch to API on quota/auth failure.

## 7. Evidence, safety and API contracts

### Intended steps versus actual events

Add typed skill events to the existing runlog pipeline, associated with the real
agent run and owning developer request. Event fields: `schema_version: 1`,
`event_id`, `run_id`, `request_id`, `seq`, `occurred_at`, `skill_id`,
`skill_revision`, optional `step_id`, `attempt_id`, `type`, `status`, and bounded
`evidence_refs` (tool_call_id, check receipt ID, artifact ID).
For a tool-backed process attempt, use that tool invocation's opaque
`tool_call_id` as `attempt_id` on both the started and finished event; multiple
tool invocations mapped to one intended step are separate attempts. Do not
persist tool arguments or result text in these activity records.

Types: `skill_selected`, `skill_resource_read`, `skill_step_started`,
`skill_step_finished`, `skill_step_skipped`, `skill_selection_refused`.
Step status: `running`, `passed`, `failed`, `skipped`, `unknown`. Only trusted
controller/validator events can produce `passed`; a tool result proves only
the operation it actually performed. The versioned host-owned
`SkillStepCheckReceipt` contract is implemented with controller identity,
process-local HMAC, receipt ID and issue/expiry times, run and owning request
IDs, skill ID and exact revision, step ID and attempt ID, and exact required
check IDs with boolean outcomes. Required check IDs resolve through the
host-code-owned checker registry and allowlisted mapping for the immutable
skill-revision/step snapshot, never model prose or candidate-authored success
claims. The validator matches every identity to the active run and recorded
attempt, requires every expected check exactly once and true, rejects
unknown/missing checks, and applies replay, expiry, and idempotency rules. Only
the internal controller receipt path can persist `passed`; generic run-log/tool
paths continue to reject it. The current host checker registry contains three
deliberately narrow checks: `weather.current_and_forecast_returned`,
`repository.status_observed`, and `repository.history_observed`, each bound to
an exact immutable revision and process step in
`config/skill_step_checks.yaml`. Every unmapped step remains `unknown`; a
successful tool call alone does not prove a broader natural-language step.
Advisory model progress is a separately labelled note with no completion
authority. Do not expose chain of thought.

The creator maps its fixed lifecycle to stable step IDs. Other skills without
instrumentation show available tool activity and “Step completion not recorded.”
Legacy runs remain “No skill trace recorded”; do not backfill invented links.
Each retry retains its evidence; one failed step cannot turn a run green because
the final natural-language reply sounds successful.

Persist bounded content-free selection/step metadata in a typed companion table
linked to existing `agent_runs`/`agent_events` via the normal DB migration system.
Unique `(user_id, run_id, event_id)` and `(user_id, run_id, seq)` enforce idempotency;
indexes support skill/revision and run cursors. Do not repurpose preview fields
as unvalidated JSON. Follow run deletion/pruning with cascade cleanup; cap at
256 skill events per run and emit an explicit truncation marker. Underlying
run privacy/retention rules still apply. Protected runs persist no skill IDs,
step labels, example text or resource contents; return “Protected activity” and
only lifecycle metadata already permitted by the existing privacy contract.
Temporary protected detail remains in memory and clears with its owning session.

Telemetry failure cannot interrupt voice or ordinary skill use. Missing evidence
appears unknown; it blocks creator review/activation when a required receipt is
missing. Lifecycle decisions use durable sandbox journals/receipts, not best-effort
runlog. Restart reconciles those records; never replay an uncertain external
side effect. Reuse `claim_execution_action` for request-owned side effects and
existing publisher reconciliation after an ambiguous response.

### Admin API (new, additive version-1 payloads)

Use existing localhost authentication/access controls and user scoping. No new
listener or unauthenticated mutation endpoint. Add:

- `GET /api/skills?cursor=&limit=`: catalog revision, feature capabilities,
  paginated cards, readiness reason codes, next cursor; default 50/max 100.
- `GET /api/skills/{skill_id}?revision=`: immutable detail, reviewed process,
  examples, related workflows, provenance, dependencies and version evidence.
- `GET /api/skills/{skill_id}/runs?cursor=&limit=`: existing run references and
  redacted status; default 20/max 100. No prompt/results bodies in list responses.
- `GET /api/skills/runs/{run_id}/events?after_seq=&limit=`: typed trace deltas,
  truncation/restart indicators; max 100. Register fixed `runs` routes before
  dynamic skill-ID routes. Scope all run lookups to the authorized user.
- `POST /api/skills/requests`: fixed operation `draft`, `test`,
  `request_activation`, `request_rollback`, or `cancel`, plus `request_id` UUID,
  expected catalog revision, skill ID/revision, typed operation fields and the
  existing explicit privacy context. No argv, provider credentials, arbitrary
  path, or unchecked model name. Return 202 with stable job/run IDs or an existing
  identical receipt. Conflicting reuse of a request ID returns 409.
- `GET /api/skills/requests/{request_id}`: reconcile progress after reconnect.

All responses carry `schema_version: 1`; unknown fields/enums fail at mutation
boundaries. Validate bounded UUIDs, slugs, digests and cursors. Max response 256 KiB;
paginate/explicitly report oversized details instead of silently truncating
instructions. Resource preview uses validated resource IDs, not a path-to-host API.
Raw private task text never enters catalog queries, request URLs or diagnostics.

Request `draft` fields: bounded task brief (max 8,000 chars), target slug, optional
existing revision; `test`: owning draft job ID, reviewed example IDs, scope
`offline|live`, route policy reference and budget; activation/rollback: exact
candidate/accepted revision plus review artifact reference; cancel: owning job
ID. Bind confirmations to these digests and budgets. Modified candidates
invalidate approvals/evidence. Safe retries return the original job, never a
second VM or PR. Persist content-free request receipts under the configured
sandbox host directory with owner-only permissions; bind `(user_id, request_id)`
to a canonical payload digest and never store the task brief in the receipt.
The existing append-only database migration sequence is shared with other
roadmap work, so this request ledger does not claim a new migration slot.

An offline validation receipt proves package and candidate checks only. It does
not prove matcher quality: `example_ids` are bound to the request, while running
with/without-skill comparisons remains the separate SW5 evaluator gate. Live
scope must return a clear disabled response until a reviewed route, privacy
policy, and numeric budget are configured. Protected-content requests are
refused because the durable sandbox session cannot meet the protected-run
retention contract. Activation/rollback requests create review artifacts only;
they never edit the live registry or activate a package.

Native polling uses one app-owned task per visible selected run, one-second
foreground interval while running, five seconds in background, stopping for
terminal/hidden content. Multiple windows subscribe to the same cached trace.
Refresh cursor gaps/restarts by authoritative snapshot; do not infer success
from lost connection. The existing result channel ingests final artifacts once.

## 8. Native Skills workspace

Add **Skills** alongside existing workspace destinations, using the current
scrollable/adaptive navigation. It does not replace a sidecar tab or Atlas.
Keep startup in compact Conversation. Opening Skills is an explicit action.

Library cards display name, one-line purpose, category, enabled/readiness badges,
last used time and last outcome if permitted. Search names/descriptions locally;
filter Installed, Proposed, Needs attention, and category. Home/Surveillance/
Finance categories with no installed skills show useful empty states, not fake
working integrations. Readiness blockers have a specific resolution, with no
repeated voice prompts just to classify a skill.

The dashboard must answer, without opening a card: **what skills exist, what
each is for, whether it is usable now, and whether recent use needs attention**.
Keep the overview scannable with a compact count/status summary and a stable
list/grid of cards; do not turn it into a dense node map or make color the only
status signal. Proposed and installed items remain visibly distinct. Search and
filters compose, survive opening and returning from a detail view, and have a
clear empty/reset state. Sort order is deterministic and must not imply model
quality or popularity. Last-used and outcome fields are omitted when the privacy
contract does not permit them. The initial release is read-only for library
management; creator and activation controls appear only when their lifecycle
capabilities are actually available.

Selecting a skill opens these detail tabs:

- **Overview:** purpose, when to use, examples, “Why this skill?” for a selected
  run, dependencies, origin/license, active revision, related workflows.
- **Process:** readable vertical step flow with optional labelled branches;
  select a node for inputs, tools, outputs, approvals and success criteria.
  Label the view “Intended process.” Do not require a force-directed graph to
  understand a short procedure. Offer linear accessible reading order.
- **Activity:** runs, actual event timeline, elapsed time, current step when
  instrumented, failures, skipped steps, evidence and final result links.
- **Versions:** candidate/active/previous revisions, diff, tests, request
  activation/rollback and review state. Never hide partial evaluation results.

The library is the dashboard and the selected skill is its drill-down. Keep the
first view scannable: show the installed/proposed/needs-attention state and the
skill's purpose before exposing implementation detail. A user must be able to
click, speak, or use the keyboard to open a skill and then follow its intended
process one step at a time. Selecting a process step visibly focuses that step
and reveals its inputs, outputs, tools, approval boundary, and success criteria;
the full ordered process remains readable without selecting nodes. Make
branches and terminal outcomes explicit, and identify steps whose completion
cannot yet be observed. Do not use a decorative graph, animation, or inferred
progress as a substitute for a legible process or recorded evidence. Preserve
the selected skill and step when resizing, changing text size, moving a detail
view to another display, or returning from the detail view.

In Process, provide a linear reading path as the canonical representation and a
compact flow treatment only as a supplement when it improves orientation. Each
step has a stable identifier, readable title, short purpose, and an explicit
selection state. Selecting a step updates a persistent detail region (or the
small-screen equivalent) rather than opening a pile of windows. “Next” follows
the declared edge; at a branch, present the condition labels and destination
steps without choosing for the user. The UI may indicate which steps have
trusted evidence for a selected run, but it must not paint the intended map as
completed from prose, elapsed time, or a model's self-report. A selected run
with missing instrumentation shows “Not recorded”; a run with no trace shows
“No skill trace recorded.”

At content width ≥960 points, use a 280-point library pane and flexible detail;
below that use list → detail navigation with a persistent Back control. Reuse
existing minimum window size, text-size setting, spacing and glass components.
Detail nodes wrap text; no clipped step names, horizontal scrolling requirement,
or hover-only controls. Large type may stack panes regardless of window width.
Respect Reduce Motion/Transparency and increase contrast; status uses text/icon
as well as color. All actions have VoiceOver labels and keyboard focus order.

“Try example” previews inputs, route, expected artifacts, side effects and budget.
Read-only synthetic examples can proceed on the user's run request; operations
with existing approval requirements keep those requirements. Tests run in the
sandbox. Never substitute live personal data for missing fixtures.

Detailed replies and evaluation artifacts appear in the existing response/results
area; conversation retains brief live captions. Group all artifacts for a single
creator/developer request into one result container with subsections/versions.
Sharing uses existing preview/copy/save/system sharing, with current privacy and
approval behavior; do not add a second exporter or leak protected trace data.

### Voice/pointer/keyboard parity

Extend both Python ConsoleProtocol and native ConsoleActionRegistry/coordinator
with `view_set(mode=skills)` and strict actions:

- `skills_search(query)` (max 256 chars), `skills_filter(category,state)` using
  the enumerated categories/states, and `skill_select(target)`.
- `skill_tab(tab=overview|process|activity|versions)`,
  `skill_step_select(target)`, `skill_step_explain(target)`,
  `skill_run_select(target)`, `skill_example_preview(target)`.
- `skill_request(operation=draft|test|request_publish|request_activation|request_rollback|cancel,
  preview_id)` dispatches the reviewed backend request; preview ID binds full
  operation parameters. Voice cannot manufacture an approval from a boolean.

`draft` runs the pinned creator only in the slug-scoped offline sandbox and
stops at `review_ready` when the host-owned validator receipt matches the exact
candidate digest. A model response cannot certify that state. The authenticated
request owner can inspect the bounded exact diff from the review-ready status;
the native UI must render the full diff before enabling `request_publish`.
Publication is a separate idempotent owner-scoped request bound to the draft
request ID, candidate digest, and package revision. It may open a review PR only;
it cannot merge, release, enable, or activate the skill. If publisher outcome is
ambiguous after a process restart, reconcile against the sandbox's recorded
publication and never blindly repeat the external side effect. Voice may start
or inspect drafting and request cancellation; opening a PR requires the native
diff review and an explicit user action.

The first native navigation increment implements the bounded read/navigation
subset: `skills_search`, `skills_filter`, `skill_select`, `skill_tab`,
`skill_step_select`, and `skill_run_select`. It does not expose draft, testing,
activation, rollback, or cancellation until the corresponding SW4/SW5 backend
lifecycle is implemented and reviewed. The app-owned Skills store publishes
only current target inventories (skill ID/display label/status, process step
ID/title, run ID/status/start time) so the Supervisor can resolve speech against
the same loaded objects the user sees. It excludes search text, prompts,
responses, resource bodies, secrets, and private artifact content. The native
coordinator revalidates each target against the current catalog, selected
skill's process, or that skill's run list; the request revision rejects stale
inventory. Search/filter values are bounded and enum checked in both protocol
implementations.

Targets are current inventory IDs, scoped to session/generation/revision;
enforce the existing stale/invalid/unsupported/capacity/pendingUser outcomes.
Reuse existing `content_scroll`, panel movement and share actions. Publish only
safe bounded inventory summaries, never resource bodies or confidential titles.
Unsupported older clients get an explicit capability result; no raw fallback
tool command. Navigation is local and does not make a model call.

Acceptance utterances include “Show my skills,” “Open skill creator,” “Explain
this step,” “Show its last failed run,” “Test that example,” “Cancel this test,”
and “Move this process to the second screen.” Ambiguous targets prompt one
concise disambiguation, never a guessed consequential action.

## 9. Display behavior

Single screen: library/detail stay in the central workspace; the orb and existing
sidecar remain available. Flow can expand within that area and return cleanly.

Multiple screens: user may move one skill detail/live-run view into the existing
shared supporting display stage. Main can retain library/conversation. Reuse a
stable content ID derived from skill revision + selected run (or detail view),
the existing tile limit, pinned behavior and developer aggregation key. One
development request produces one aggregate tile, not one window per step,
artifact, model reply or retry. Other research/results share available space.

Moving a view transfers presentation ownership; do not mirror full detail in
both places by default. The library may show a compact “On supporting display”
link. Closing the tile does not cancel the job; cancellation is explicit.
Unplug rehomes content, selection, scroll and trace cursor into main without
restarting jobs. Reconnect follows the existing saved-role placement policy,
without duplicating views or stealing focus. Spaces are not physical displays.
Do not reopen all historical skill runs on reconnect or app startup.

## 10. File ownership and implementation increments

Paths below are repository-relative. New paths are explicitly marked; existing
owners must be extended rather than duplicated. Before each increment rebase
the isolated branch safely and inspect concurrent changes; do not overwrite them.

### Parallel execution map (status checkpoint: 2026-09-27)

Parallel work is encouraged only across the bounded tracks below. Every track
must preserve the file ownership above, communicate API/fixture changes before
editing shared contracts, and integrate through the same candidate worktree
without committing or deploying intermediate states. The status labels below
describe implementation/evidence state, not completion:

| Step | Current status | Safe parallel work | Dependency / serialized gate |
| --- | --- | --- | --- |
| SW0 | `in_progress` | Finish baseline receipt and fixture coverage; can run beside SW1, SW3 UI review, SW5 runner scaffolding, and SW6 deterministic selector checks. | Freeze shared contracts before another track changes their schemas. Live baseline capture must precede claims of preserved behavior. |
| SW1 | `in_progress` | Finish parser/CLI/pin acceptance and readiness evidence; can run beside SW0, SW3, SW5 and SW6 when package/registry files have one named owner. | Do not turn on either runtime flag until dependent SW2 readiness, privacy, and release evidence is accepted. |
| SW2 | `in_progress` | Finish backend event/readiness/API edge cases and add an authenticated dispatch path that creates a real Developer SubAgent run for each creator request. Persist and validate the actual Developer `agent_runs.run_id` separately from the sandbox request/job UUID. | The admin sidecar currently cannot dispatch the bot-session-owned Developer SubAgent. Do not fake a Developer run or accept a client ID. Freeze the dispatch and activity contract with SW3 before integration; Mac runtime evidence follows. |
| SW3 | `in_progress` | Native library, accessibility, voice action and synthetic display work can proceed beside backend work against the versioned API contract. For creator flows, manual and voice entry must both invoke the SW2 Developer dispatch and render its server-returned run ID plus the separately identified sandbox job. | Creator UI wiring waits for a callable, authenticated SW2 dispatch contract. Live voice, physical display, and full native acceptance run after integration on a frozen build; do not create a second window/action owner. |
| SW4 | `in_progress` | Documentation, deterministic tests, and isolated authoring hardening can proceed beside SW3/SW5/SW6. The actual skill drafting tool must execute as a capability of the active Developer SubAgent run and bind async sandbox work to that real run. | Real-VM draft/cancel/retry/publish-reconciliation trials share mutable sandbox state and must run serially, one candidate/request at a time. Maintainer review remains separate from PR merge/deploy. |
| SW5 | `in_progress` | Six required cases, strict loader, paired runner, gated host CLI, pre-call budget/ledger attribution, randomized blinded outputs, private condition/usage artifacts, human rating template, and acceptance scorer are implemented and tested. Remaining: complete live route/privacy setup, run the 24 trials, obtain blinded human ratings, review the acceptance report, and prepare the activation diff/rollback evidence. | Fake-provider runner/tests can proceed beside SW0–SW4 and SW6, with one owner of `jarvis/skill_evaluation.py`. Live provider trials require explicit policy+environment enablement and parent privacy/model-route gates; execute the 24-trial comparison sequentially under the single bounded budget. Human blinded review follows artifact freeze; activation and rollback are later serialized gates. |
| SW6 | `in_progress` | Deterministic selector/conflict/compatibility fixtures and public dry-run evidence can proceed beside SW5 and UI work with exclusive ownership of selector/capability files. | Never compare by invoking both routes on live user tasks. Target-Mac latency/memory checks and any flag rollout follow integration and route/tool readiness receipts. |

Recommended parallel lanes: (1) SW0/SW1 evidence and loader acceptance,
(2) SW2 backend trace/readiness work, (3) SW3 native UX/accessibility work,
and (4) SW5 fake-provider runner plus SW6 public deterministic checks. SW4
static hardening may join any lane with a distinct file owner. Integration,
cross-lane regression, VM mutation trials, live provider comparison, physical
display/voice acceptance, activation/rollback, and release/handoff are explicit
barriers and must be performed in dependency order. If a lane needs to change a
shared contract, pause that lane's dependent edits, agree the versioned change,
then resume; parallelism must not produce competing executors, registries,
window owners, or independent budget authorities.

### Weighted implementation progress rubric

Report implementation progress separately from acceptance-gate completion and
release readiness. Score each workstream from 0–100 using the same evidence
anchors: 0 = not started; 25 = contracts/design and initial implementation;
50 = core behavior implemented with substantial planned work absent; 75 = most
planned implementation and focused regression coverage present, with integration
or target acceptance still open; 100 = every listed exit criterion for that
workstream has verified evidence. Intermediate scores are allowed when the
evidence falls between anchors. A workstream remains below 100 while any of its
exit criteria or required acceptance evidence is open. Code presence alone does
not earn completion; unverified, skipped, blocked, or simulated evidence cannot
be counted as accepted evidence.

Use these fixed scope weights so later updates remain comparable:

- SW0 — contracts, fixtures, and baseline: 10%.
- SW1 — loader, registry, package metadata, and resources: 15%.
- SW2 — readiness, truthful telemetry, and read API: 15%.
- SW3 — native library, accessibility, voice actions, and displays: 15%.
- SW4 — creator package and bounded sandbox lifecycle: 20%.
- SW5 — live evaluation, human review, activation, and rollback: 15%.
- SW6 — evaluated selection, performance, and release: 10%.

Calculate the plan's implementation estimate as `sum(weight × workstream score)
/ 100`, with weights expressed as percentages. Show the seven scores and the
weighted contributions whenever reporting the total, round only the final total
to one decimal place, and retain the underlying unrounded result. Separately
report the number of accepted SW-A–SW-L gates out of 12; never derive that gate
count from the weighted implementation score.

### SW0 — Freeze contracts and baseline

- Create `docs/acceptance/skills-workspace/STATUS.md` and `BASELINE.md` (new).
  Record source/config/package digests, runtime versions, existing skill matcher
  fixtures, console/voice/default-layout screenshots and current open gates.
- Check route/privacy/approval and sandbox readiness against parent plans. Mark
  dependent live tests blocked when those gates are open; static UI work proceeds.
- Add JSON schema/fixtures under `tests/fixtures/skills_workspace/` (new) covering
  package metadata, catalog, requests, events and voice actions.
- Exit: reviewer can trace every agreed behavior to a gate in section 12.

### SW1 — Correct loading and build the registry

- Extend `jarvis/agent_skills.py`; add `jarvis/skill_catalog.py` and
  `jarvis/skill_resources.py` (new). Keep these distinct from MCP registry package.
- Add companion metadata for existing skills without rewriting their instruction
  semantics. Extend `config/skills.yaml` with migration/pinning support behind
  `JARVIS_SKILLS_WORKSPACE_ENABLED=false` and `JARVIS_SKILLS_SELECTION_V2=false`.
  Both default off. Global `JARVIS_AGENT_SKILLS_ENABLED` still wins.
- Add `tests/unit/test_skill_catalog.py`, `test_skill_resources.py` (new); extend
  `test_agent_skills.py`; correct `skills/README.md`.
- Exit: complete parsing, path/resource limits, immutable snapshots and five-skill
  legacy selection regression tests pass. No script execution in loader.

### SW2 — Readiness, truthful telemetry and read API

- Extend `jarvis/agents/base.py`, `jarvis/runlog/store.py` and `jarvis/db.py` with
  reviewed migration/typed metadata, redaction, pruning and event linkage.
- Extend `jarvis/admin/server.py`; add `jarvis/skill_service.py` (new) for typed
  catalog/readiness/request orchestration, not another router or executor.
- Add API/trace tests including ownership, protected data, missing evidence,
  replay/cursors and partial instrumentation. Add resource tool registration
  through existing registries with current permission/privacy checks.
- Exit: read API and actual selection/resource traces work; unavailable steps
  stay unknown; no private data is added to diagnostic logs.

### SW3 — Read-only native library, details and displays

- Extend `macos/JarvisKit/Sources/JarvisKit/AdminAPI.swift` and typed protocol
  messages. Add `SkillModels.swift` (new) for versioned decoding.
- Add `Stores/SkillsStore.swift` and `Console/Skills/` views (new) beneath
  `macos/MortimerHost/Sources/MortimerHost/`. Wire from `App/MortimerHostApp.swift`.
- Extend `Console/CommandConsoleView.swift`, `Stores/WorkspaceStore.swift`,
  `Display/WorkspaceView.swift`, `Display/DisplayWindowStore.swift` and
  `Display/DisplayWindowView.swift` using existing content/placement ownership.
- Extend `App/ConsoleActionRegistry.swift`, `App/ConsoleActionCoordinator.swift`,
  `jarvis/bot/console_protocol.py`, `console_actions.py`, protocol/voice fixtures
  and corresponding Swift/Python tests. No duplicate AppMessageRouter ingestion.
- Exit: pointer/keyboard/voice navigation, accessible Process/Activity distinction,
  resize, shared stage and disconnect recovery work with synthetic data. The
  library answers availability/purpose/readiness without opening a card; detail
  preserves selection while users inspect each ordered step; branches are
  explicit; Activity never implies a step passed without trusted evidence; the
  narrow layout and large-text path remain usable; voice and pointer reach the
  same targets; and display moves/unplug/reconnect preserve one presentation
  owner without opening extra windows or interrupting work.

### SW4 — Creator package and bounded authoring lifecycle

- Add reviewed `skills/skill-creator/` and provenance. Keep disabled initially.
- Add `jarvis/skill_authoring.py` (new) for the fixed lifecycle; reuse self-edit
  service jobs and sandbox Runtime/Session. Implement scoped authoring policy
  through `jarvis/selfedit/` and host-owned profile/verification changes in
  `sandbox/`. These are maintainer code changes, not creator self-edits.
- Add host-owned offline creator checks and fixtures, plus cancellation,
  side-effect claim/reconciliation, immutable approval and permission tests.
- Wire native preview/test/cancel/review requests through shared actions.
- Route every manual and voice creator draft through a real Developer-agent
  run. The backend must create and own the `agent_runs.run_id`, verify that it
  belongs to the authenticated user and has `agent="developer"`, and bind the
  async authoring job to that run. Keep the durable sandbox request/job UUID
  separate. The native client must consume the server-returned run identity;
  never accept a client-minted ID, reuse the request UUID, or attach work to a
  Supervisor direct-tool run. Activity must show the actual Developer run and
  separately expose the creator job's status/evidence.
- Dispatch contract: a native/manual or voice request carries only the
  authenticated session, accepted preview/request payload, and an idempotency
  key. The host creates the owner-scoped sandbox job/session, then a bot-owned
  dispatcher resolves that live session to its Developer `SubAgent` and starts
  `SubAgent.run`; the SubAgent's RunLogger is the sole source of the Developer
  run ID. The host durably associates that real run with the existing creator
  request and distinct sandbox job/session before any bounded creator tool can
  execute. The Developer run receives only the four approved creator tools for
  the exact sandbox job. Return the Developer run ID from the internal
  dispatcher only after durable association; the native request remains
  asynchronous and obtains both identities through its owner-scoped status
  receipt. Reject stale or cross-user sessions, unknown run IDs, duplicate keys
  with changed payloads, and requests when the Developer dispatcher is
  unavailable. Cancellation targets the exact creator request and sandbox job,
  and confirms the owning Developer run. Activity renders Developer-run
  lifecycle and sandbox-job lifecycle as separate evidence. Async validation
  activity attaches to the originating Developer run without changing its
  terminal run status. The admin sidecar must not fabricate a run or pretend it
  owns a bot-session SubAgent.
- Exit: synthetic skill drafted, evaluated offline, reviewed and exported through
  the sandbox with no live-library mutation and no provider/credential access
  from the guest. Failed tests cannot reach review-ready publication.

### SW5 — Live evaluation and reviewed activation

- Add `skill_eval` routing schema/policy support (disabled without explicit
  configuration), budget enforcement and usage attribution through existing
  `jarvis/model_routing.py` and ledger. Add `scripts/evaluate_agent_skill.py`
  (new), the host entry point for the bounded evaluator; no provider secrets in
  argv/logs/artifacts. Add deterministic fake-provider tests before live trials.
- Exercise the creator with/without skill; compare results and trigger coverage.
  Human review of blinded artifact quality is required; model grading alone does
  not establish correctness. Never change fixtures after seeing a failure without
  versioning them and rerunning both conditions.
- Produce exact activation diff and route it through maintainer review/release.
  Verify loaded digest on the Mac. Exercise a reviewed rollback and failure
  recovery; keep earlier evidence and package revision available.
- Exit: creator is installed, configured, tested, accepted and visibly loaded;
  only then begin creating domain-specific skills.

### SW6 — Evaluated selection improvement and release

- Implement section 5's bounded capability-aware selector in
  `jarvis/skill_selection.py` behind its own flag; map reviewed capability tags
  to route/tool requirements in `config/skill_capabilities.yaml`, refusing
  unknown tags. Collect dry-run decisions on public fixtures first. Do not
  invoke both routes on live user tasks or double their side effects for
  comparison.
- Accept single primary behavior first, then one compatible support with conflict,
  budget, snapshot and explicit-selection tests. Failed quality gates keep v2 off.
- Finish full native/voice/monitor/privacy/regression acceptance and update
  architecture references and release status from the frozen candidate.
- Exit: all section 12 gates have traceable evidence, or release explicitly
  retains an off flag for incomplete optional selection features and the overall
  plan stays incomplete. Do not call partial rollout full completion.

## 11. Candidate skill backlog from Anthropic research

Research inventory: 19 directories reviewed on 2026-09-25. Recheck the pinned
upstream snapshot during implementation. These are recommendations, not an
instruction to import all packages or license approval for redistribution.

- **First:** `skill-creator`, with the adaptation and acceptance above.
- **Next, after creator acceptance:** `doc-coauthoring` and `internal-comms`
  concepts to strengthen `technical-plan-document`, avoiding overlapping active
  plan skills; `mcp-builder` to strengthen `mcp-server-authoring`.
- **Interface work:** `frontend-design` and `theme-factory` concepts adapted to
  native SwiftUI/Liquid Glass and existing design tokens. `webapp-testing` is
  useful for actual web surfaces; it is not proof of SwiftUI/AppKit testing.
- **Behavioral guidance:** review `discernment-nudge` against existing shared
  prompts; adopt only useful missing principles, without redundant user questions
  or a separately auto-selected skill competing with task expertise.
- **Document outputs:** `pdf` and `docx` when requested; `xlsx` for the financial
  roadmap; `pptx` when presentation work is evidenced. These packages have
  distinct source-available license terms: review each before vendoring; do not
  assume the repository's other licenses apply.
- **Later:** `web-artifacts-builder` for sandboxed interactive results, preserving
  result ownership/sharing and approval rules. `algorithmic-art` and `canvas-design`
  for requested asset experiments, not replacing the accepted native orb.
- **Narrow/low priority:** `claude-api` as provider-specific reference without
  replacing model routing; `academy-guide` for user-requested learning;
  `brand-guidelines` does not define Mortimer's brand; `slack-gif-creator` has no
  demonstrated current need.

Sources: [Anthropic skills inventory](https://github.com/anthropics/skills/tree/main/skills),
[skill-creator](https://github.com/anthropics/skills/tree/main/skills/skill-creator),
[creator license](https://github.com/anthropics/skills/blob/main/skills/skill-creator/LICENSE.txt).
Each proposed adoption needs provenance/license review, existing-skill overlap
check, public positive/negative cases, sandbox tests and one-at-a-time approval.

## 12. Acceptance gates and evidence

For every gate record candidate commit and package/config digests, environment,
command or manual steps, expected/actual result, timestamp, redacted artifact,
reviewer and remaining limitation. Checkboxes mean accepted evidence exists,
not “code written.” No preexisting test count closes a new gate.

- [ ] **SW-A — Baseline preserved:** five original skills, compact Conversation,
  voice/orb including muted idle, eight sidecar tabs/content/scrolling, memory
  automation, Atlas, results/sharing and existing developer aggregation remain
  behaviorally equivalent. Record any preexisting failures separately.
- [x] **SW-B — Package integrity:** full upstream-like body survives separators;
  invalid schema, oversize files, traversal, symlinks, digest mismatch and stale
  resource reads fail safely. Installation alone never enables a package.
  Acceptance receipt: `docs/acceptance/skills-workspace/receipts/sw-b-package-integrity-20260928.json`.
- [x] **SW-C — Selection quality:** every frozen positive/negative legacy fixture
  retains its expected decision; explicit selection/capability refusal/kill switch
  work. V2 has zero new false positives on that set, passes conflict/compatibility
  cases, and never exceeds two skills or the 16,000-character budget.
  Local acceptance receipt: `docs/acceptance/skills-workspace/receipts/sw-c-selection-quality-20260928.json`.
- [ ] **SW-D — Truthful inspection:** intended process and real trace are visibly
  distinct; failed/skipped/unknown and old uninstrumented runs display correctly.
  Duplicate/out-of-order/reconnect events cannot invent progress or completion.
  Process is understandable in linear reading order, branches expose their
  labelled choices, and selecting a step reveals its declared detail without
  opening extra windows.
- [ ] **SW-E — Privacy:** protected input/IDs/names cannot escape via catalog,
  inventory, SQL/JSONL, diagnostics, argv, exports, screenshots taken by automated
  tests, examples, evaluator artifacts or secondary displays. Test source-to-sink
  canaries and user scoping; do not rely solely on a redaction helper unit test.
- [ ] **SW-F — Creator isolation:** authorized draft starts without another generic
  pre-sandbox confirmation; only approved package/fixture paths change; normal
  deny policy remains intact; no host fallback, live checkout edits, network or
  credential mount. Changed candidates invalidate receipts and cannot activate.
- [ ] **SW-G — Evaluation effectiveness:** 6 reviewed cases include create, improve,
  ambiguous scope, existing-skill reuse, malicious resource and missing dependency.
  Run both conditions twice against the exact frozen fixture digest. Each trial
  artifact is the bounded text response and its case/repetition/rubric linkage,
  not a generated skill package; deterministic checks require all six cases,
  12 complete pairs, bounded nonempty responses, matching frozen criteria, and
  complete metrics bound to the blinded review. Candidate responses must pass
  the human-reviewed safety rubric for malicious-resource and
  missing-dependency cases, meet ≥10/12 blinded task-quality pass judgments,
  pass the separate deterministic no-tool-execution gate for every trial, and
  score no worse than baseline. Actual candidate-package
  validity is established only by the SW4 host validator and sandbox receipts.
  Report latency, calls and cost for both; an inconclusive sample is not evidence
  of universal improvement.
- [ ] **SW-H — Lifecycle recovery:** duplicate requests create one job/PR;
  cancellation stops work and prevents late publication; restart reconciles
  uncertain results. Review/merge/deploy states remain distinct. Activation is
  atomic and in-flight versions stable; rollback to an accepted revision works.
- [ ] **SW-I — Voice/accessibility:** every control has a corresponding shared
  action; acceptance utterances, stale targets and ambiguity work; VoiceOver,
  keyboard, large type, Reduce Motion/Transparency and contrast are checked.
  Search/filter state survives detail navigation; overview and step selection
  remain operable without a pointer or hover.
- [ ] **SW-J — Display:** on one and two physical displays, open two research
  results plus one creator run; all steps/retries append to its one tile. Move,
  close/reopen, unplug during a test, reconnect and restart. No duplicate content,
  window storm, lost selection, new job, focus theft or hidden orphaned result.
- [ ] **SW-K — Performance:** using fixed public 100-skill fixtures on the target
  Mac, selection adds ≤20 ms p95 and cached navigation ≤100 ms p95 across 100
  samples. Existing voice latency checks still pass; paired voice p95 regression
  is ≤50 ms under the same workload. With library and live trace visible, ten
  minutes of steady state shows no monotonic memory growth >10 MiB. Latest
  release attached-window 100-sample run on the available macOS 27 arm64 host
  measures **15.224 ms wide / 7.235 ms compact selection-to-layout p95** and
  **46.491 ms wide / 28.239 ms compact cached navigation p95**. Store-only
  selection/navigation p95 is **0.0008/0.0081 ms**; runtime selector p95 is
  **4.576/4.607 ms** for unique-hit/no-skill cases. Full bitmap rendering is
  diagnostic and excluded from the selection acceptance metric. These local
  timing sub-budgets pass, but the hardware model is unavailable, paired voice
  latency is unmeasured, and the ten-minute steady-state memory soak has not
  run. SW-K remains open. Record hardware/build with each acceptance run.
- [ ] **SW-L — Release/handoff:** frozen candidate passes required suites; Mac
  reports matching app/backend/config/package revisions; creator is visibly
  ready and loaded; architecture/status/rollback docs and evidence are current.
  Parent GC24/privacy/model-route gates are satisfied for every enabled route.

Relevant existing commands (run from the candidate checkout with its prepared
dependencies; do not mistake MCP `scripts/check_skills.py` for Agent Skills validation):

```sh
python -m jarvis.agent_skills --list
python -m jarvis.agent_skills --validate
python -m pytest tests/unit/test_agent_skills.py tests/unit/test_workflows.py tests/unit/test_console_protocol.py tests/unit/test_console_actions.py tests/unit/test_console_session.py -q
swift test --package-path macos/JarvisKit
swift test --package-path macos/MortimerHost
```

Add the new skill catalog/resource/service/trace/authoring/evaluation tests and
sandbox policy tests to their existing suites and verifier profile. Run the
repository-required backend/integration/native checks on the frozen candidate,
then actual Mac voice/display acceptance. Tests marked skipped remain unverified.
No live provider probe, spend or deployment is authorized merely by this document.

## 13. Model handoff and ongoing status

Before implementation, read this plan, the existing architecture/repo map,
current gap/status docs and applicable repository instructions. Work in a
dedicated branch/worktree alongside Claude's work. Capture the starting status
and never sweep unrelated changes into a commit.

For each SW increment, update `docs/acceptance/skills-workspace/STATUS.md` with
`not_started | in_progress | implemented_unverified | blocked | accepted`, owner,
exact changed files/commit, tests and receipts, known failures, next action and
dependency. Link the same increment from the consolidated implementation status.
Keep uncompleted work first with unchecked boxes; completed accepted work below.
Do not mark SW-F or SW-L complete based on screenshots or mocked tests alone.

### Candidate handoff snapshot (2026-09-26, SW4 partial)

The isolated candidate at base `977f50bec7b77bd7d3381d3b8f3d63fa69bd00e2`
currently has partial SW0/SW1/SW2/SW3 work, the inert SW4 creator package, and an uncommitted working tree. The
loader body parser fix, strict catalog/process metadata, schema-v2 registry
with five matching SHA-256 pins, read-only skills list/detail and activity APIs,
typed selection/reference-read events, revision-pinned bounded reference tool,
and native Skills library/process/Activity views are present. Digest enforcement
remains off; the runtime loader uses legacy behavior. Shared synthetic fixtures
now cover catalog, detail, creator request, activity event, package metadata
(validated against JSON Schema and the runtime catalog parser), and bounded
voice actions (validated through the actual console request validator). Fixture
step start/finish events are schema examples, not evidence that production
currently emits them. Process nodes expose their
decision detail, linear steps have an explicit next-step control, branches stay
labelled, and Activity shows only recorded events. Initial shared voice actions
and bounded safe target inventories are implemented. The Mortimer-specific
`skill-creator` package is present but disabled, with its process metadata,
on-demand references, Apache 2.0 notice, and upstream revision/tree digest
recorded. A slug-scoped path-policy helper and `SkillAuthoringService` are
implemented. The service binds the policy to a slug-specific workspace kind and
reuses the existing Runtime, Session, file journal, verifier, and draft-PR
publisher. `jarvis/skill_authoring_validation.py` performs provider-free host
validation with the strict catalog parser and binds its receipt to the exact
candidate fingerprint; publication requires both that receipt and normal
offline VM verification to match the same frozen snapshot. Focused validation,
policy, and service tests pass. The service is not exposed through an
admin/shared-console action, and no real-VM lifecycle has been exercised.
Inspection found the localhost sidecar has no explicit authentication
middleware, so defining local authorization is a prerequisite to a new creator
write endpoint; loopback binding alone is not authentication.

Follow-up SW3 correction: the dashboard no longer counts a deliberately inert
disabled package as “needs attention” solely because readiness includes
`skill_disabled` and expected unknown runtime checks. It still surfaces any
unexpected blocker and failed/stale verification. The focused native policy
tests pass **5 tests**, and the full MortimerHost suite passes **280 tests, 7
skipped, 0 failures**. SW2 runtime evidence was rechecked: the sidecar and voice
pipeline have separate `SkillRegistry` instances/processes, so catalog
manifests do not prove a tool session is live. Tool-session, route-compatibility
and credential-authentication evidence remain unknown until the owning runtime
can provide a trusted receipt. Current focused readiness/API/event/privacy
tests pass **66 tests**; the full Python suite passes **3,208 tests, 4 skipped,
2 subtests**, with 11 warnings.

The current creator validator supports both new skill packages and revisions
to existing skill IDs, while refusing creator self-modification, registry
changes, incomplete bodies, missing references/licenses, malformed matcher
fixtures, unavailable declared tools, and executable package/fixture files.
Receipts are tied to the exact full candidate fingerprint
and are written only after the ordinary sandbox verification confirms that same
snapshot. Latest checks: focused creator validation/policy/service tests
**26 passed**; full Python suite **3,186 passed, 4 skipped, 2 subtests passed**
with 11 warnings; skill CLI confirms six packages, five enabled and the creator
inert; `git diff --check` passed.

On 2026-09-26, submit-time receipt validation was tightened: publication now
requires the complete version-1 host receipt shape, exact skill slug, candidate
fingerprint, valid package SHA-256, zero provider calls, positive check counts,
the complete required set of named checks passing. Each new validation attempt
clears any prior receipt before rechecking, so a failed revalidation cannot leave
old evidence publishable. Receipt matching runs as a preflight under the
existing sandbox session lock, held through publication so an edit cannot race
between check and publish. Malformed/truncated data, incomplete receipts, and
edits after validation are refused before the publisher is invoked. Focused
authoring, validation, policy, session, and workspace tests pass **53 tests**;
the session suite includes a lock-level concurrency check. The full Python suite
passes **3,208 tests, 4 skipped, 2 subtests passed**, with 11 warnings. Real-VM,
authenticated action, and UI acceptance remain open.

Current receipts: focused Skills Python suite **158 passed**; full Python suite
**3,208 passed, 4 skipped, 2 subtests passed**; focused dashboard policy tests
**5 passed**; synthetic Skills library/detail render test **1 passed** at 1280
and 720 points; latest full `MortimerHost` **280 tests, 7 skipped, 0 failures**;
`JarvisKit` **203 tests, 0 failures**; all five enabled CLI package pins report
`matches`; focused creator-policy/catalog checks passed **88 tests**, and
inventory lists six packages, five enabled, with the creator inert and no false
pin mismatch. After sandbox adapter work, the focused creator/catalog/self-edit/
sandbox group passed **237 tests, 41 subtests** and the full Python suite passed
**3,178 tests, 4 skipped, 2 subtests**, with 11 warnings; `git diff --check`
passed. Three native skips
require two physical displays; three require the test host to become the active
application. They remain unverified, as do visual/voice baseline evidence,
runtime readiness receipts, trusted process-step events, complete accessibility
and display acceptance, and actual Mac acceptance. See
`docs/acceptance/skills-workspace/STATUS.md` for commands and details.

SW0-SW4 remain in progress, not accepted. SW4 has a reviewed creator package,
inert catalog representation, unit-tested path policy, a service adapter
reusing existing sandbox sessions and draft publication, and candidate-bound
host-owned offline validation tied to VM checks before publication. Explicit
authenticated/idempotent action wiring, real-VM lifecycle acceptance, and
trusted lifecycle event receipts remain open. The creator receipt match is
rechecked under the session lock through publication; the focused sandbox and
creator concurrency/refusal suite passes **53 tests**. Focused new SW0 fixture,
catalog and console-protocol tests pass **25 tests**. The full suite now also
covers SW1 package CLI validation and passes **3,208 tests, 4 skipped, 2
subtests**, with 11 warnings. Visual baseline and actual Mac/voice/display
evidence remain open.
The authenticated-action dependency had a verified cross-plan migration
conflict: Remote Access reserved `0016_client_tokens`, already used by
`0016_memory_extraction_v2`. On 2026-09-26 Larry approved revising the shared
Remote Access contract; it now appends `0031_client_tokens` after current
`0030_skill_events`, with the dependent Mail/Calendar brief migration moved to
`0032_brief`. This resolves the numbering conflict at the plan level. The
authenticated creator request routes now use the existing bearer-token
identity/owner boundary; no creator-only authentication bypass was added.
The reference reader and conservative static readiness checks have focused coverage, but runtime readiness evidence,
readiness pin enforcement, full trace/API edge-case acceptance, creator and
evaluation lifecycles, activation/rollback, and SW-A through SW-L remain open.
SW4-SW6 and all SW-A through SW-L release gates remain open. Do not interpret
this implementation snapshot as merged, deployed, active, or Mac-verified.

Architecture documentation must describe the **implemented** authority boundaries
and reference this plan as planned until verified. Update `docs/ARCHITECTURE.md`,
`docs/REPO_MAP.md`, `skills/README.md` and T6 references when the owning increment
lands, keeping prompt-injection size caps intact. Make these references available
through the existing architecture reader for both self-edit and the user.

If assumptions drift, document the discovered fact and smallest compatible
change. Changes to approved behavior, authority boundaries, deployment defaults,
provider cost/privacy, or these acceptance criteria require explicit design
review before implementation. Routine coding decisions within this contract do
not require another user approval. No new task-specific skill development starts
until skill-creator's end-to-end acceptance is recorded.

### 2026-09-27 implementation checkpoint — voice draft preview binding

The initial voice authoring increment is implemented in this candidate
worktree. Closed mirrored Python/native actions accept a draft preview, issue
an opaque five-minute single-use preview ID, and allow a follow-up voice action
to consume it and hand the transient brief to the existing native Skills
creator sheet. Only new validated skill slugs are accepted through this voice
path. Console inventory omits the brief. Voice cannot publish, activate, or
roll back; the native exact-diff review remains mandatory before a PR request.
Focused Python console/request/creator tests passed 28; JarvisKit console
protocol tests passed 6; MortimerHost console coordinator tests now cover 21
cases and Skills rendering tests passed 2. The full Python suite passed **3,319 tests,
4 skipped, 2 subtests**, with 11 warnings. Actual spoken, VoiceOver, display, and live-sandbox acceptance remain
open. These code
tests do not close SW3, SW4, or SW-A–SW-L by themselves.

### 2026-09-27 implementation checkpoint — process and example voice actions

Implemented the remaining listed-step explanation and declared synthetic
matcher-example preview actions in both protocol validators and the shared
native coordinator. The catalog exposes the declared example IDs; the native
detail panel previews only bounded synthetic request text and expected routing.
The backend requires exact declaration, valid positive/negative fixture schema,
matching package IDs, and an exact v2 registry pin. Five current skill packages
now have positive/negative matcher samples, with refreshed digest pins; a test
exercises each sample against the real lexical selector. The initial full
Python run had 3,319 passes, four skips, and one stale route-count assertion;
after updating the count to 65, the full suite passed **3,321 tests, 4 skipped,
2 subtests**, with 11 warnings. The auth/API/protocol/fixture suite passed 16
focused tests; selector/API/auth checks passed 13. MortimerHost coordinator
tests pass 22 and Skills rendering passes 2. Actual voice, VoiceOver, display,
and live sandbox acceptance remain open, as do SW-A–SW-L release gates.

### 2026-09-27 implementation checkpoint — explicit runtime skill selection

The delegation schema now exposes an optional, bounded `skill_id` only when
both `JARVIS_SKILLS_SELECTION_V2` and `JARVIS_SKILLS_WORKSPACE_ENABLED` are on.
Its instruction permits the field only when the user names an exact skill ID.
That ID bypasses lexical matching only. Runtime selection still requires a
verified route, compatible privacy, the current package digest pin, ready
dependencies, required tools, and the reviewed capability map. If the request
cannot be selected safely—or selector evidence raises an error—the SubAgent
refuses before making a model call. In v2 mode it never silently falls back to
the legacy matcher; with either flag unset the existing behavior remains.

Focused selector, package fixture/loader, SubAgent and delegation verification
passes **211 tests**. This is implementation evidence only: live model/MCP
evidence, production flag rollout, supporting-skill selection, lifecycle
evaluation, activation/rollback, accessibility, spoken-flow and Mac acceptance
remain open. Release gates SW-A through SW-L remain open. No provider evaluation,
activation, PR, merge, or deployment was performed.

The public fixture dry-run requirement is now implemented by
`scripts/check_skill_selection_fixtures.py` and
`tests/fixtures/skills_workspace/selection-evaluation.json`. It verifies exact
global outcomes for five intended skills, five no-skill requests, and four
cross-skill overlaps using synthetic ready-route and tool evidence. Both the
legacy matcher and v2 selector agree with all 14 expected IDs. The generated
receipt `docs/acceptance/skills-workspace/receipts/skill-selection-fixtures-2026-09-27.json`
records candidate scores, threshold results, package revisions, fixture digest,
and zero provider calls. Focused fixture/selector tests pass **17 tests**. This
does not certify real-task quality or enable rollout.

The optional support path is now implemented end-to-end behind v2 selection:
the selector requires an independently qualified candidate and reciprocal
`compatible_with` declarations, enforces the combined 16,000-character body
budget, and reports a reason when support is omitted. SubAgent rechecks both
package revisions before injecting either body; the reference reader accepts
only a selected package ID and uses its snapshotted digest and shared budget.
Tests cover mutual and one-sided compatibility, budget refusal, dual injection,
and reading a declared support reference. No current repository pair declares
mutual compatibility, so live package behavior remains single-skill. The
focused selector, SubAgent, resource, fixture and delegation suites pass **161
tests**. Architecture, repo map and `skills/README.md` now explain the gate.
Next SW6 actions are target-Mac latency/memory measurement and real route/tool
readiness evidence; rollout remains disabled until all plan gates pass.

### 2026-09-27 implementation checkpoint — selector snapshot and performance

Added a bounded 60-second runtime package/catalog snapshot keyed by the active
schema-v2 skill IDs and SHA-256 pins. MCP tools, route/privacy facts, capability
mapping, credential presence and readiness are recomputed for each request;
selected packages are re-read and pin-checked before prompt injection. With
both v2 flags on, the first SubAgent construction prewarms this snapshot so the
normal request path avoids the filesystem/catalog scan. The cache remains
disabled with either flag off.

On macOS 27.0 arm64 with Python 3.12.13, the fixed public 100-skill runtime
fixture measured **4.39/4.37 ms p95** for matching/no-skill requests over 100
samples each, below SW-K's 20 ms selection budget. Snapshot prewarm took
**790.62 ms**. The receipt
`docs/acceptance/skills-workspace/receipts/skill-selection-performance-2026-09-27.json`
records the base commit, dirty-tree bit, source, fixture and synthetic config/
package-set digests, host and timings; no provider was called. The broader
selector/SubAgent/resource/fixture/delegation/repo-map/architecture suite passes
**173 tests** and targeted Ruff checks pass (four pre-existing codes are
excluded for the large legacy SubAgent files); `git diff --check` passes.

This is partial SW-K evidence only. Same-pin expiry now returns the existing
immutable snapshot while a daemon worker builds and atomically publishes its
replacement. Package contents are re-read and checked against the current pin
before prompt injection; a changed registry key still takes the synchronous
verified rebuild path. Refresh failures preserve the previous snapshot and use
a five-second retry backoff. The regenerated warm-path receipt reports 4.39/4.37
ms p95 for matching/no-skill selection; 100-skill prewarm is 790.62 ms.
Native cached navigation, paired voice latency, ten-minute memory
growth, real route/MCP readiness, accessibility and Mac/display acceptance
remain open. SW-A through SW-L remain open and neither runtime flag was enabled
for normal operation.

The migration numbering decision was reaffirmed on 2026-09-27: keep auth at
`0031_client_tokens` after `0030_skill_events` and the dependent brief migration
at `0032_brief`. `jarvis/db.py` and the two owning plans already implement this;
references to `0016` in dated review artifacts describe the resolved historical
conflict and are preserved as evidence.

### 2026-09-27 implementation checkpoint — truthful tool-backed step traces

The SubAgent now links actual tool-call attempts to a declared process step
only when exactly one selected step names that tool. It records `running` before
dispatch and a finish event after the shared tool-result classifier. A
classifier-confirmed tool failure is `failed`; successful tool returns and
cancellation remain `unknown`, since neither proves natural-language success
criteria. Repeated/ambiguous tool-to-step associations produce no step event.
Events contain only the step ID and tool-call ID evidence reference, under the
existing protected-run redaction and run event limits. A fake-registry test
verifies selection/start/finish order and unknown status on a successful tool
return; focused SubAgent and runlog tests pass 39 cases; the combined focused
Python selector/SubAgent/runlog/resource/delegation suite passes 211 tests. The
focused native rendering suite passes 4 tests and verifies that tool-call
evidence is labeled as an observation with an unvalidated step outcome. This is
partial SW2 evidence, not process completion proof. Controller acceptance, protected-run
verification, provider/MCP receipts and native Activity review remain open.

### 2026-09-27 implementation checkpoint — disabled-by-default evaluator budget

SW5 now has a strict optional `skill_evaluation` policy parser and a dedicated
`skill_eval` workload gate. It is unavailable unless the policy block is
explicitly enabled and `JARVIS_SKILL_EVAL_ENABLED=1`; the active model-access
file has no such block. The workload must be background, have no fallback, and
cannot be silently retargeted through model preferences or route environment
overrides. Hard limits cap cases, repetitions, calls, per-trial calls, batch
time, input tokens and output tokens. Paid routes require a numeric spend
ceiling and fail closed when a per-call price estimate is unavailable. The
in-memory budget reserves conservative cost before a call and retains the
reservation for failed/uncertain outcomes. Usage attribution has a dedicated
`skill_eval` rung. Focused route and budget tests pass 26 cases; the adjacent
model-route/model-execution/usage-ledger/evaluator-budget suite passes 70 tests.
No provider was called.

At this checkpoint, this was scaffolding rather than a usable evaluator. The
follow-up increment below adds the bounded paired runner; blinded export,
invocation CLI, explicit live enablement, and human review/activation workflow
remain open. No model-access policy was enabled and no live provider was called.

### 2026-09-27 implementation checkpoint — paired evaluator runner

SW5 now includes `run_skill_evaluation`, which accepts only a bounded immutable
tuple of public/synthetic fixtures, executes each fixture with and without the
candidate instructions, reserves conservative cost before each call, applies
the configured output-token cap and remaining batch deadline, and records
normalized usage under the dedicated `skill_eval` ledger rung. It reuses the
existing model-execution callback; it does not create a second provider
executor, grade outputs, activate packages, or write artifacts. The runner
refuses subscription adapters because their current CLI wrappers do not
demonstrate enforcement of the required output cap. Focused evaluator tests
pass **28 tests**; model-routing, model-execution, usage-ledger and evaluator
tests pass **72 tests** together. Ruff and `git diff --check` pass. No provider
was called. The next SW5 work is explicit live-route setup and human quality
review. Live comparison, activation diff, and rollback remain gated and open.

### 2026-09-27 implementation checkpoint — fixture CLI and blinded export

Added strict versioned fixture loading and six frozen public/synthetic cases
for the `skill-creator` package, each with prewritten human-review criteria.
The host command `scripts/evaluate_agent_skill.py` resolves only the configured
`skill_eval` route and reads the skill package by repository slug; it accepts no
arbitrary route/model or secret arguments. Its output and private condition key
must be written to separate preexisting mode-0700 directories, as mode-0600
files; prior evidence cannot be overwritten. The blinded file omits trial
condition labels and randomizes presentation order; the separate key maps
opaque IDs to with/without conditions. The active route and environment gates
are still disabled. Focused evaluator tests pass **18 tests** and the adjacent
model routing, execution, ledger and evaluator suite passes **79 tests**; Ruff
and `git diff --check` pass. The CLI
disabled-path test confirms it exits before provider execution. No live calls
were made. Explicit live-route setup, human review, activation diff and rollback
remain open.

### 2026-09-27 implementation checkpoint — SW-G human review and score

The frozen six-case skill-creator fixture now matches the acceptance categories:
create, improve, ambiguous scope, existing-skill reuse, malicious resource, and
missing dependency. Added a blinded rating-form generator and a scorer that
validates exact review-digest binding, all 24 outputs, the 12 complete pairs,
the ≥10/12 candidate quality threshold, non-regression against baseline, and
human rubric passes for malicious-resource and missing-dependency cases.
Scoring reports calls, mean/p95 latency, reserved spend and actual cost for
each condition; unknown latency, route or cost blocks acceptance. Review,
ratings, condition key, usage metrics and score are owner-only files in private
directories. The scorer only returns “eligible for maintainer review”; it has no
activation path. The focused evaluator/routing/execution/ledger suite passes
**84 tests** and Ruff/diff checks pass. No model calls were made. Actual live
trial, human review, activation diff and rollback evidence remain open.

The full repository Python suite passes **3,371 tests, 4 skipped, and 2
subtests**, with 11 warnings. This broad regression result does not establish
the target-Mac voice/display, VoiceOver, or live sandbox lifecycle gates.

### 2026-09-27 whole-batch budget preflight

Before the paired evaluator invokes its first model call, it now validates the
entire planned batch against total-call and per-trial caps, input/output token
bounds, known price availability, and the paid-route spend ceiling. A test
proves a batch that exceeds the ceiling is rejected with no executor calls and
no reserved calls. Pricing-estimator exceptions also fail closed during
preflight and per-call reservation. Focused evaluator/review tests pass **25
tests**, targeted Ruff checks pass, and the full Python suite passes **3,373
tests, 4 skipped, and 2 subtests**, with 11 warnings. This is implementation
evidence only: provider evaluation, blinded human scoring, activation review,
and rollback remain open.

### 2026-09-27 native regression verification

Current native suites pass: MortimerHost reports **286 tests, 6 skipped, 0
failures** and JarvisKit reports **206 tests, 0 failures**. Skills rendering,
Activity copy, voice action, and typed/bounded Skills API tests pass. Skipped
physical-display checks require multiple connected displays; on-screen checks
need an interactive foreground-capable WindowServer. VoiceOver and target-Mac
acceptance remain open.

### 2026-09-27 Skills accessibility implementation increment

The Skills library exposes selection through the accessibility selected trait;
when the system requests differentiation without color, selected cards and
process steps also show a text label and stronger outline. Reduce Transparency
uses near-opaque library, process, and Activity surfaces. The rebuilt focused
Skills native suite passes **9 tests**. System-setting, VoiceOver, keyboard,
contrast, and large-text acceptance still require review on the target Mac.

### 2026-09-27 authoring cancellation-race implementation increment

Added tests for cancellation during sandbox startup and for a late positive
validation receipt after cancellation. Startup cancellation prevents creator
execution; a late successful-looking creator/sandbox response cannot restore a
cancelled request to `review_ready` or retain its candidate digest. The request,
authoring-service, validation, and policy suites pass **53 tests**. These fake
service tests strengthen the lifecycle boundary but do not replace real-VM
cancellation, restart/reconnect, or publisher-reconciliation acceptance.

### 2026-09-27 parallel implementation continuation

SW0/SW1 added fail-closed CLI coverage for malformed schema-v2 registries with
runtime enforcement still off. SW2 added a service-bot-authenticated runtime
inventory from the live voice registry, short-lived conservative readiness,
and cursor pagination/replay coverage; the receipt reports discovered tools
only and does not claim invocation, route, credential, privacy, package, or
sandbox validity. SW4 now matches publisher-recovery receipts to the durable
request's exact run ID, candidate digest, and package revision; mismatches
remain `publication_needs_reconciliation` with no PR URL. SW5 randomizes the
order of each paired with/without fixture trial to reduce systematic order
bias while preserving private labels. These changes are documented in the
living [Skills Workspace status](../acceptance/skills-workspace/STATUS.md).

The SW3 native library now consumes the complete cursor-paginated catalog,
rejects malformed, repeated, overlapping, or revision-changing pages, and
commits the new catalog atomically only after every page succeeds. The store
tracks all loaded skill IDs so pointer selection works beyond the first 50
cards and former 32-ID cap, while keeping the shared-action voice inventory
bounded at 32. Synthetic tests cover a 61-entry catalog over three pages and
selection beyond both previous caps.

Latest verification: whole-repository Python **3,405 passed, 4 skipped, 2
subtests**, 11 warnings; full JarvisKit **210 passed**; full MortimerHost **292
executed, 6 skipped, 0 failures**. Target M5 profiling reports only the
built-in display. Physical-display, interactive VoiceOver, live voice, real-VM
lifecycle, paid/live provider comparison, human review, activation/rollback,
and frozen release acceptance remain open. The weighted implementation
estimate is **81%**; this is not a release-completion measure. Continue with
SW0/SW3 target-Mac baseline and accessibility evidence when available, then
run the serialized VM/provider/release gates in plan order. Keep both runtime
skill flags off until those gates are accepted.

### 2026-09-27 SW0 fixture and SW5 evaluator guard verification

SW0 synthetic Skills workspace fixtures now validate against the current
catalog, detail, creator-request, activity-event, package-metadata, and
voice-action contracts. Cross-fixture checks bind catalog/detail IDs and
revision digests; creator requests parse through the actual request model;
process graphs require unique IDs, valid targets/order, and acyclicity; and
synthetic event evidence does not claim a trusted pass without a receipt. The
focused fixture suite passes **13 tests**; adjacent catalog, request, event,
selection, and CLI suites pass **66 tests**. These checks cover fixtures and
synthetic contracts only; visual, voice, and display baseline evidence remains
open.


SW5 binds the evaluator to the frozen `skill-creator-v1` fixture SHA-256
(`43c563255e96bf4f081dcd497005af05986b6d01662e5c41cf11691140b85c12`)
before route resolution. The runner explicitly supplies no tools, requires
`ModelExecutionResult.tool_calls` to be an empty tuple, and records a validated
zero count for each trial. The scorer separates the human
`reviewed_safety_rubric_pass` from deterministic `no_tool_execution` and
requires both for all 24 outputs; missing, malformed, or nonzero tool evidence
refuses eligibility. Focused evaluation/review tests pass **33 tests**. This
does not replace blind independent ratings or authenticate locally editable
artifacts: linked JSON digests detect mismatches, but a person able to rewrite
all owner-only artifacts can recompute unkeyed hashes. If that threat is in
scope for formal scoring, require a signed/append-only runner receipt or
document reviewer trust in original owner-only outputs before live evaluation.
No provider route was enabled or called.

The live 24-trial comparison, blinded human ratings, actual package-validity
receipts, target-Mac voice/accessibility/display acceptance, real-VM lifecycle,
activation/rollback review, and release acceptance remain open. Runtime skill
enforcement remains disabled.

Integrated regression after these changes passes **3,424 Python tests, 4
skipped, 11 warnings, and 2 subtests**. Targeted Ruff F checks and
`git diff --check` pass. This confirms local repository behavior only; it does
not close the external acceptance gates above.

### 2026-09-27 SW2/SW3/SW4 parallel continuation

SW2 remains deliberately fail-closed: generic tool success and model
narration cannot emit a trusted step `passed` event, and missing evidence is
`unknown`. The trusted check-receipt contract is now spelled out above as an
implementation prerequisite, including immutable identity binding, a
host-owned required-check mapping, and replay/expiry/idempotency semantics.
The existing package-level authoring receipt is not sufficient for per-step
success. No code change was justified before these terms are established.

SW3's focused native Skills workspace suite passes **19 tests**. Review found
no source change that could safely substitute for target-Mac verification.
VoiceOver and speech timing, Full Keyboard Access traversal/action parity,
spoken navigation, accessibility settings, and supporting-display transfer,
return, and reconnect remain open.

SW4 now reconciles an already-published PR only when its receipt matches the
exact parent draft run, reviewed candidate digest, package revision, and
nonempty PR URL. A mismatch stays `publication_needs_reconciliation`; a
matching recovery completes without a second submit. The focused request suite
passes **30 tests**. Real-VM restart/cancel/reconnect and live publisher
acceptance remain open.

After SW4 reconciliation and SW6 duplicate-ID refusal, the integrated Python suite passes **3,429
tests, 4 skipped, 11 warnings, and 2 subtests**. Targeted Ruff F/I checks and
`git diff --check` pass. The weighted implementation estimate is **83%** using
SW0–SW6 scores 84/79/90/89/89/80/62% and weights 10/15/15/15/20/15/10% (83.1%).
This is an implementation estimate, not acceptance or release completion.

Fresh full native suites pass **MortimerHost 304 tests, 7 skipped, 0 failures**
and **JarvisKit 210 tests, 0 failures**. Their source/test tree digests and
limited local diagnostics are recorded in
`docs/acceptance/skills-workspace/receipts/native-suites-20260927.json`.
The 100-sample skill-detail resolver p95 is **0.0082 ms** but excludes SwiftUI
rendering/network; synthetic graph timings are layout-only, and the
ten-minute-memory and end-to-end latency budgets remain unmeasured. Physical
display, VoiceOver, live voice, VM, provider, activation/rollback, and release
acceptance remain open.

### 2026-09-28 parallel continuation: provenance and acceptance-gate audit

A deterministic worktree candidate fingerprint is now available at
`scripts/mortimer_candidate_fingerprint.py`. It binds tracked and non-ignored
untracked candidate files, including staged/unstaged content and symlink target
text, while excluding ignored outputs and the skills-workspace acceptance
receipt directory to avoid a self-referential receipt digest. Its focused suite
passes **4 tests** and Ruff passes. The release app bundle embeds the candidate
fingerprint and source revision; bundle verification receipt:
`docs/acceptance/skills-workspace/receipts/mortimerhost-app-bundle-20260928.json`.
The bundle is ad-hoc signed and `codesign --verify --deep --strict` passes.
It was not launched, installed, or deployed. The release build was performed
with debug-info generation disabled because this sandbox denies dSYM creation.

Independent release and provider-evaluation audits confirm that local
implementation evidence is substantial; those audits did not close SW-A–SW-L.
SW-B package-integrity acceptance is separately closed by the
`sw-b-package-integrity-20260928.json` receipt. The evaluator, frozen six-case fixture, budget guards, blind
review workflow, and scorer exist; the 24-trial comparison still requires an
explicitly reviewed `skill_evaluation` route, bounded spend policy and verified
credential, followed by independent ratings and maintainer review. SW2 now has
the host-issued receipt/check-map contract, durable one-shot acceptance, strict
run/attempt binding, expiry, replay, and protected-data handling. Its shipped
check registry and map are empty, so trusted outcomes remain `unknown` until
independent host check functions and exact reviewed mappings exist. VoiceOver,
live voice, supporting display, real-VM lifecycle, target-Mac performance,
activation/rollback, and final release acceptance remain open.

### 2026-09-28 SW2 trusted-step receipt contract

Implemented `jarvis/skill_step_checks.py` and the host-owned
`config/skill_step_checks.yaml` policy. Version 1 receipts bind a process-local
HMAC, issuer, user/run/request, immutable skill digest, process step, attempt,
exact ordered check IDs, boolean outcomes, issue time, and expiry. Host check
IDs must resolve to code-owned checker functions; both the shipped checker
registry and revision/step mapping remain empty until independently verifiable
checks are implemented and reviewed. This is deliberately non-operational by
default: untrusted model/tool results cannot supply or sign a receipt.

`RunLogger.accept_skill_step_check_receipt` validates the live run owner and
status, prior skill-selection event, exact started attempt, check-policy
mapping, and receipt lifetime before atomically persisting the receipt digest
and the only allowed trusted `skill_step_finished: passed` event. Exact receipt
replay is idempotent; altered receipts and repeated accepted attempts are
rejected. Protected-run transitions erase receipt identifiers/digests and
retention pruning removes them with their run. The generic event writer
continues to refuse model/tool-authored `passed` states. Focused receipt,
runlog, API, and subagent regressions pass **139 tests**. The complete Python
suite passes **3,450 tests, 4 skipped, 11 warnings, and 2 subtests**. SW2 remains
in progress pending actual host check implementations and target-runtime
readiness; the receipt contract alone does not close an acceptance gate.

The revised SW2 implementation score is 93% (up from 90%); SW-B acceptance is
closed, and the other explicit gates remain open. With SW0–SW6 weights
10/15/15/15/20/15/10% and scores
84/79/93/89/89/80/62%, the weighted implementation estimate is **83.6%**.

### 2026-09-28 SW-B package-integrity acceptance

Closed SW-B against the frozen candidate using 89 passing package/loader/
resource tests plus the real-catalog CLI validator. The evidence covers full
instruction bodies after separator lines; malformed/duplicate metadata;
package file-count, total-byte, and text-file limits; traversal and symlink
refusal; package digest drift and stale resource reads; and registration being
required before an on-disk skill is enabled. The CLI confirms all six package
directories are readable, exactly five remain enabled, all five active pins
match, and `skill-creator` remains inert. Runtime digest enforcement remains
off; SW-B proves package integrity and inert-by-default behavior, not runtime
readiness or release acceptance. Receipt:
`docs/acceptance/skills-workspace/receipts/sw-b-package-integrity-20260928.json`.
The complete candidate Python suite also passes **3,450 tests, 4 skipped, 11
warnings, and 2 subtests**.

### 2026-09-28 parallel acceptance hardening checkpoint

Parallel SW-A, SW-C, SW-D, SW-E, SW-H and SW-I reviews found and addressed
several repository-local gaps without treating them as target acceptance:

- SW-E: `run_skill_evaluation` now requires approved fixture identity and
  digest, reloads and verifies the frozen fixture in the core, and rejects
  caller-supplied cases that differ before any provider invocation. The CLI
  passes its verified provenance. Focused evaluator/model-routing tests pass
  **42**, broader privacy-boundary tests pass **90**, and the full Python suite
  passes **3,453 tests, 4 skipped, 11 warnings, and 2 subtests**. Privacy
  source-to-sink evidence on the actual app, exports, screenshots and
  supporting display is still required for SW-E acceptance.
- SW-H: queued draft and offline-validation requests are now claimed with a
  compare-and-set under the durable per-request file lock before starting a
  worker, preventing two host processes from starting the same request. The
  focused request/authoring/service/validation/policy suites pass **70 tests**.
  Real-VM restart, cancellation, reconnect and publisher-reconciliation trials
  remain required.
- SW-D: activity labels now distinguish failed tool calls, unknown outcomes,
  and observed tool returns. SW-I: the linear Next-step accessibility hint now
  says it opens and scrolls to the destination instead of claiming focus moves.
  The focused native rendering suite passes **10 tests**; the full MortimerHost
  native suite passes **304 tests, 7 skipped, 0 failures**. Live VoiceOver,
  keyboard, visual, voice and physical-display acceptance remain open.
- SW-C: closed by receipt against the frozen public fixture. Focused
  selector/fixture tests pass **100**, and the provider-free corpus returns all
  **14/14** expected decisions with zero provider calls. This closes the
  deterministic selection-quality criteria only; SW6 target performance/live
  route readiness, activation, rollback and release gates remain open.
- SW-A: the exact five enabled skills and package pins have local regression
  coverage (focused tests: **72 passed**). The repository has no verified
  baseline screenshots or voice/display recordings, so parity for the orb,
  sidecar, Atlas, results and developer aggregation still needs target
  interaction evidence.

SW-B and SW-C are the only closed SW-A–SW-L acceptance gates. The weighted
implementation estimate is unchanged at **83.6%**; target Mac, VM, provider,
human-review, privacy source-to-sink, display and release gates remain open.

### 2026-09-28 implementation continuation — readiness, isolation, evaluation and display

Local plan work continued in parallel after the SW-C receipt:

- Runtime readiness now fails closed on MCP inventory overflow (>8 reporters
  in one freshness window), and returns to normal only after fresh inventory
  evidence. Focused runtime/readiness/API tests pass **39**.
- The reserved `skill-creator` package is rejected at the authoring policy,
  service, and request boundaries before durable job reservation or sandbox
  allocation. Queued draft and offline-validation jobs use cross-process
  atomic claims. Focused authoring/request/lifecycle tests pass **73**; real VM
  isolation and restart/recovery acceptance remain open.
- Evaluation revalidates frozen fixture provenance and exact case content in
  the core before any provider call. Blinded-evidence APIs require owner-only
  output directories, not only the CLI. Focused evaluator/privacy regressions
  pass **35** and **42**; no live provider route was configured or called.
- A pinned developer result tile remains the aggregation owner for later
  results from the same run. The complete native host suite passes **305
  tests, 7 skipped, and 0 failures**; physical displays and interactive
  acceptance remain open.
- A fresh 100-sample-per-case macOS 27 arm64 benchmark records selector p95 of
  **4.485 ms** for a unique-trigger hit and **4.467 ms** for no-skill queries,
  within the 20 ms budget. It does not measure rendered navigation, end-to-end
  voice latency, or ten-minute memory growth. Receipt:
  `docs/acceptance/skills-workspace/receipts/skill-selection-performance-2026-09-28.json`.

The full Python suite passes **3,458 tests, 4 skipped, 11 warnings, and 2
subtests**. SW-B and SW-C are the only accepted SW-A–SW-L gates. The weighted
score is recalculated against the existing 0/25/50/75/100 evidence-anchor
rubric in the following checkpoint. Live target Mac,
provider, VoiceOver, physical display, real VM, human review, activation,
rollback and release work remains.

### 2026-09-28 weighted implementation estimate refresh

Using the documented 0/25/50/75/100 evidence anchors (intermediate estimates
allowed), the workstream scores are SW0–SW6 **84/80/93/90/90/81/64%**. With
weights **10/15/15/15/20/15/10%**, the weighted implementation estimate is
**84.4%**: 8.40 + 12.00 + 13.95 + 13.50 + 18.00 + 12.15 + 6.40. The modest
increase reflects the candidate-bound SW-B/SW-C receipts, runtime inventory
overflow fail-closed behavior, SW3 UI corrections and aggregation fix, SW4
creator self-target rejection and atomic job claims, SW5 core fixture/privacy
checks, and current selector benchmark. This is an implementation-progress
estimate, not a claim that any remaining target-Mac, provider, human, VM,
physical-display, activation/rollback, or release gate is complete. SW-B and
SW-C remain the only accepted SW-A–SW-L gates.

### 2026-09-28 parallel local hardening follow-on

Five isolated implementation/review lanes covered local SW-D, SW-E, SW-H,
SW-I and SW-K work:

- SW-H now binds a reviewed draft receipt to one publish request ID, payload
  digest and exact candidate/revision under a cross-process lock. Distinct
  request IDs for the same candidate cannot create competing publish jobs; the
  queued-to-publishing transition is claimed atomically. No GitHub operation
  was invoked.
- SW-E now omits protected result titles and IDs, including active/comparison
  identities, from both supervisor inventory formats. Protected local results
  cannot be transferred to a supporting display, are omitted from its Display
  menu, and are rejected at the local clipboard/export coordinator before a
  writer can receive their text. Canary tests cover inventory, display transfer,
  and clipboard/export sinks. Broader privacy acceptance remains open.
- SW-I improves large-text layouts and accessibility values, adapts detail
  navigation to a menu when space is constrained, and uses opaque surfaces
  under Reduce Transparency. Live VoiceOver and system-setting acceptance
  remain open.
- SW-D displays an explicit unknown/not-completed state when a run has no trace
  and corrects copy that implied uninstrumented runs were listed. Duplicate,
  out-of-order, failure and unknown trace handling remain covered locally;
  legacy-run and reconnect acceptance on the Mac remains open.
- SW-K adds 100-sample store-level navigation coverage against the public
  100-skill fixture. The latest integrated native suite reports 0.0021 ms
  selection p95 and 0.0214 ms cached store-navigation p95; this excludes
  SwiftUI rendering, network, live voice and long-run memory growth.

Final integrated checks on this candidate: Python **3,459 passed, 4 skipped,
11 warnings, 2 subtests**; MortimerHost **310 passed, 7 skipped, 0 failures**;
focused publication/request suites **79 passed**; `git diff --check` passes.
The weighted implementation estimate is now **85.3%**, with unchanged
10/15/15/15/20/15/10% weights and conservative SW0–SW6 scores
84/80/93/91/91/83/66%. Contributions are 8.40 + 12.00 + 13.95 + 13.65 +
18.20 + 12.45 + 6.60; total **85.3%**. The estimate reflects local
implementation and test evidence only. SW-B and SW-C remain the only accepted
SW-A–SW-L gates. Live
provider trials and human review, real-VM lifecycle tests, VoiceOver/manual
system-setting checks, physical-display tests, rendered-navigation/paired
voice/memory measurements, activation/rollback and release acceptance remain
open. The prior release-build/app-bundle receipt is bound to the earlier
candidate fingerprint and is not current release evidence; rebuild only after
the acceptance candidate is frozen.

### 2026-09-28 remaining acceptance work in parallel

An independent source-to-sink audit found that protected result payloads could
reach the supporting display through the app-message `.window` route before the
workspace transfer guard. `AppMessageRouter` now keeps protected results in
the main workspace and rejects that route before writing either display store;
an end-to-end encoded-message regression test passed. SW-E remains open until
argv canaries and protected-content screenshot scanning are covered.

The SW-H follow-on adds a serialized pre-submit cancellation barrier and
recovery for queued publication records left after reservation. A winning
pre-submit cancellation prevents submit; cancellation after submit starts is
rejected and preserves the uncertain outcome for reconciliation. Restart and
cancellation regression cases pass. SW-H remains open for real VM/reconnect,
publisher reconciliation, and activation/rollback acceptance.

SW-A still requires the recorded before/after interaction matrix in rollback
and adaptive modes. SW-K still requires target-Mac rendered navigation,
paired voice-latency and ten-minute memory-growth evidence. A refreshed
provider-free selector run measured 4.418 ms p95 for a unique-trigger hit and
4.408 ms for no-skill, below the 20 ms selector budget. Final integrated
validation after the parallel fixes passed: Python 3,463 passed/4 skipped, and
MortimerHost 311 passed/7 skipped. The prior weighted implementation estimate
of 85.3% is retained as a dated checkpoint, not recalculated in this pass.
These acceptance gates cannot be closed by local source tests or
selector/store microbenchmarks.

### 2026-09-28 parallel implementation follow-on

SW-D activity refresh preserves its last valid trace through transient errors,
exposes retry, retries older-page failures, clears prior-run data immediately
on selection change, and ignores stale/cancelled replies. SW-E adds argv
canaries for protected requests, subscription prompts and Tart task arguments.
Its renderer-to-screenshot test now writes and decodes an actual temporary PNG
for a protected synthetic payload and compares its pixels with a body-only
reference. It does not exercise a live application capture. SW-F explicitly denies
ordinary self-edit access to `tests/fixtures/skills_authoring/**`. SW-G binds
the blinded-output writer/scorer to the approved frozen fixture, exact 24
trials, 12 complete pairs and frozen criteria, stops on oversized response,
and fails incomplete token metrics. SW-I aligns Python/Swift Unicode-scalar
limits and distinguishes stale from unavailable voice targets.

The exact Softnet v0.23.0/Tart 2.37.0 implementation only supports IPv4 CIDR
rules. Adding `::/0` is unsupported, and failed IPv6 probes do not prove the
guest cannot send IPv6. Therefore SW-F remains open until independent IPv6
filtering (or a NIC-less offline VM) is provided and tested on the frozen
candidate. Target links: [Softnet v0.23.0 rules](https://github.com/openai/softnet/blob/0.23.0/lib/proxy/rule.rs),
[Tart 2.37.0 run command](https://github.com/cirruslabs/tart/blob/2.37.0/Sources/tart/Commands/Run.swift).

Latest full suites pass: Python **3,468 passed, 4 skipped**, MortimerHost
**314 passed, 6 skipped**, JarvisKit **210 passed, 0 skipped**. A standalone 100-sample
store-only run measured 0.0008 ms selection and 0.0076 ms cached-navigation
p95; selector-only measured 4.400 ms hit and 4.377 ms no-skill. These do not
measure rendered navigation, voice regression or ten-minute memory. External
SW-A/D/E/F/G/H/I/J/K/L acceptance and release handoff remain incomplete.
The focused store measurement is recorded in
`docs/acceptance/skills-workspace/receipts/skill-store-navigation-performance-2026-09-28.json`;
candidate-bound SW-B, SW-C, and selector receipts are refreshed after this
documentation update.

### 2026-09-28 continued local hardening

SW-D now clears the old activity trace immediately when the selected skill or
shared-navigation destination changes. SW-E also blocks protected PNG bytes
before they enter image-share preview state; its focused coordinator suite passes
23 tests, while the wider privacy sinks remain open. SW-H has a regression for a crash after
the durable `publication_submitting` barrier: recovery marks the result
uncertain when the sandbox still says `validated` and does not resubmit. The
publisher also rejects a nominally successful response with an empty PR URL.
SW-I guards skill-detail success and error responses with a request generation
and current-selection check, including overlapping requests for the same
skill. Skill cards expose enabled/disabled state to accessibility clients,
verified in the mounted native accessibility tree at both responsive widths. These are local regression fixes; live reconnect, real-VM publisher
reconciliation, speech and VoiceOver acceptance remain open.

The latest integrated native run also measured SW-K's public 100-skill store
fixture: selection p95 **0.0020 ms** and cached store-navigation p95 **0.0198 ms**
for 100 samples with 32 cached details. This is store-only evidence; SwiftUI
rendered navigation, paired live-voice latency and ten-minute memory growth are
still open.

The integrated Python suite passes **3,470 tests with 4 skips** and the full
MortimerHost suite passes **317 tests with 6 skips and 0 failures**; JarvisKit
passes **210 tests**. Focused SW-H recovery/request coverage passes **43
tests**. The six native skips require physical displays or a foreground
WindowServer process. A current `system_profiler SPDisplaysDataType -json`
probe reports only the built-in Apple M5 display, so physical two-screen
acceptance cannot run in this candidate session. `git diff --check` passes. SW-B and SW-C are still the only accepted gates. The 85.3% weighted estimate is a prior dated checkpoint
and was not recalculated. Candidate-bound local receipts have been refreshed for this dirty worktree;
the release-build receipt must be recreated against a frozen candidate. Hardware,
live-provider, real-VM, manual accessibility and release-handoff gates remain
open.

### 2026-09-28 creator fixture resource bounds

The offline authoring validator now applies the strict catalog resource limits
to scoped fixture files as well as skill-package files: 128 fixture files,
128 KiB per fixture, and 10 MiB aggregate. The host publication preflight
requires the three corresponding passing receipt checks, preventing an older
receipt from authorizing a candidate under the changed validation contract.
Regression tests cover all three boundaries; focused authoring and evaluator
suites pass 79 tests. This local change does not close SW-F or authorize the
creator: real VM restart/network-containment evidence, frozen-candidate route
receipts, and all remaining SW-A–SW-L acceptance requirements still apply.

### 2026-09-28 native control accessibility regression

The mounted Skills library test now checks the native accessibility names for
search and both filter pickers at wide and narrow widths, in addition to the
existing enabled/disabled card and selected-process state assertions. The
focused rendering test passes at both widths. This adds local UI-tree evidence
for SW-I, but does not replace actual VoiceOver, keyboard-only, macOS
accessibility-setting, or physical-display acceptance.

### 2026-09-28 native accessibility-name regression

The mounted library test checks search and both filter pickers in the native
accessibility tree at wide and narrow widths. The full
`SkillsWorkspaceRenderingTests` suite passes **14 tests**. AppKit combines the
picker's visible title with its descriptive accessibility label, so the
regression checks for the intended descriptive portion. This remains synthetic
native-tree evidence and does not close live VoiceOver, keyboard-only,
accessibility-setting, or physical-display acceptance.

### 2026-09-28 host-verified weather process-step increment

SW2 now maps one exact immutable package revision and process step to a
host-owned validator: `current-weather-with-fahrenheit@9064f3d61d680d8cbce9c4dda1b2d98b854624fce2b106f89cc7f13b4ace521e` /
`retrieve-conditions`. The check binds the returned payload to the requested
location (independent of Weather.gov's display-city label), requires at least
the requested number of forecast days, requires a fresh timezone-aware source
timestamp, checks Fahrenheit/Celsius coherence and daily high/low ordering, and
does not accept the Weather.gov forecast-period fallback as proof of a current
observation. The tool exposes the requested query and source timestamp to the
host check without persisting them in the skill activity trace.

The SubAgent-to-RunLogger integration test verifies a synthetic valid tool
result produces the exact step's `passed` event with receipt-reference evidence;
invalid or absent check evidence remains `unknown`. Focused tests passed **188
tests** across the receipt/check contract, SubAgent bridge, weather tool,
Weather.gov and ambient-weather suites. These tests validate host contract
behavior only; they are not live-provider, protected-run, cross-process runtime
readiness, or broad SW2 acceptance. SW2 remains in progress with this single
verified step mapping; all other trusted process-step mappings and documented
runtime and release gates remain open.
The full Python suite passes **3,482 tests, 4 skipped, 11 warnings, and 2
subtests** after this increment. This remains local test evidence and does not
close hardware, live-provider, real-VM, accessibility, or release gates.

### 2026-09-28 second host-verified process step and legacy trace evidence

SW2 now maps
`git-history-and-status-review@8794a16e69d4908ff12906e93b8b5cc01d0560c8c792d0ab43279c41ac1a5c7e` /
`inspect-repository` to the host-owned `repository.status_observed` check. The
read-only `git_status` response now includes the actual Git top-level path and
explicit upstream (or `null`), branch, changed paths, and ahead/behind counts;
outside a Git worktree it returns an error result that cannot pass validation.
The checker verifies exact result fields, bounded values and consistency
between `clean` and the changed-path list. A receipt-backed test confirms the
step can pass while the result paths are excluded from persisted skill events.

SW-D also gained an API regression for a legacy run with no skill trace: the
events endpoint returns `trace_status=unavailable`, an empty event page and
unchanged cursor, without exposing task or reply text. Full Python validation
passes **3,482 tests, 4 skipped, 11 warnings, and 2 subtests**. This proves
local contracts only; SW-D still requires native duplicate/out-of-order and
reconnect acceptance, and SW2 still has only two narrowly mapped process steps.
All remaining process steps and target-Mac, provider, VM, privacy, accessibility,
display and release gates remain open.

### 2026-09-28 shared-action parity and third verified process step

SW-I now routes the Skills Workspace controls through the shared typed action
dispatcher: refresh, search, filters, skill selection, tabs, process-step
expand/collapse/explain, run selection, example preview, supporting-display
transfer, compact Back, Conversation return, Activity retry/load-more, and
opening the existing Create a skill composer. `skill_creator_open` only opens
that composer when authoring is available for a pinned catalog; previewing,
starting, publishing, and activating remain separate gated actions. Focused
native coordinator/registry/policy and rendering suites pass **42** and **14**
tests; Python protocol/action tests pass **17**. A stale step ID is rejected
against the old inventory revision instead of resolving against another
selected skill.

SW2 also maps the pinned Git history skill's `inspect-history` step to a
host-owned check over a bounded structured Git log result: full commit IDs,
timezone-aware commit dates and subjects must agree with its display rows and
stay within the requested limit. Current full suites pass **3,482 Python tests
(4 skipped, 11 warnings, 2 subtests)**, **324 MortimerHost tests (7 skipped,
zero failures)**, and **210 JarvisKit tests (zero failures)**. Native skips
include display/foreground-window constraints; these results do not close live
voice, VoiceOver, keyboard-only, system-setting, supporting-display, or frozen
Mac acceptance. SW-I and SW2 remain in progress.

### 2026-09-28 parallel implementation of local acceptance gaps

SW-A adds a native rollback-layout rendering regression for sidecar and voice
control reachability. The interaction matrix across rollback/adaptive modes
still requires hands-on Mac acceptance.

SW-D prevents historical activity from borrowing step titles from the current
package revision. Matching revisions retain human-readable titles; mismatches
show the recorded step ID plus a package digest prefix; missing revisions are
marked unavailable. Focused regression coverage and the full **328-test**
MortimerHost suite pass (7 skipped).

SW-L adds a local fail-closed verifier for candidate-bound acceptance receipts
and the embedded app-bundle fingerprint, executable digest/size, bundle
identity, and candidate branch/HEAD/dirty state. Its six focused tests pass. It
rejected stale evidence before the latest parallel source changes. The release
bundle has since been rebuilt from the final candidate, its signature verifies,
and the candidate receipt refresh is complete; the verifier passes all six
required local candidate-bound receipts.

SW0 fixture checks now enforce catalog/detail parity across duplicate metadata
and reject readiness drift. SW1 revalidates the selected package pin, digest,
and instruction body immediately before prompt injection. SW-D applies strict
page validation at the API boundary and rejects stale A→B→A activity replies
using a monotonically increasing selection generation. These increments add
focused tests; reconnect/foreground and other human acceptance remain open.

The full Python suite passes 3,491 tests (4 skipped, 11 warnings, 2 subtests),
MortimerHost passes 329 (7 skipped), and JarvisKit passes 211. Scoped Ruff and
diff checks are clean. This is implementation evidence only; receipt identity
refresh did not rerun named measurements. SW-B and SW-C remain the only accepted
SW-A–SW-L gates; VoiceOver, keyboard-only, live voice, target-Mac visual review,
provider, VM, physical-display, activation/rollback, and release acceptance
remain open.

### 2026-09-28 latest implementation and acceptance checkpoint

SW4 now binds cancellation, draft receipts, and offline-validation receipt
association to the exact expected sandbox run ID; focused request and recovery
tests pass **74**. Real-VM lifecycle, restart/reconnect, and publisher
reconciliation remain open. SW5 requires paired evaluation conditions to share
provider, model, route, and billing mode; focused evaluator-review and budget
tests pass **39**. No live evaluation trials or independent human ratings have
run. SW-E's ScreenCaptureKit protected-content canary has **3 passing tests and
1 skipped** because Screen Recording permission is unavailable; capture by the
running Mortimer app and on a supporting display remains unverified.

Latest full local results: **3,496 Python passed, 4 skipped, 11 warnings, and 2
subtests; 330 MortimerHost tests with 8 skipped; 211 JarvisKit passed**. On an
Apple M5 Mac17,4 with 16 GB RAM and only the built-in display attached, a
100-sample run measured selection p95 **0.0008 ms** and cached store navigation
p95 **0.0075 ms**. The measurements exclude SwiftUI rendering and network
activity and do not establish multi-display performance.

The current weighted implementation estimate is **87.1%** using SW0–SW6 weights
**10/15/15/15/20/15/10%** and scores **86/82/94/93/93/85/68%**. This estimates
implementation progress; it does not mean acceptance gates are complete. The
candidate receipt fingerprint is stale following source and documentation
updates and must be refreshed before release evidence can verify. The candidate
app bundle has not been installed, launched, or deployed. Open manual/external
gates include VoiceOver and keyboard-only review, live voice and target-Mac
visual acceptance, Screen Recording permission and app/supporting-display
capture, physical multi-display behavior, real-VM restart/reconnect and
publisher recovery, provider trials with independent human review, activation
and rollback, and final release acceptance. SW-B and SW-C remain the only
accepted SW-A–SW-L gates.

### 2026-09-28 parallel implementation checkpoint — activity, privacy, and rendered-performance coverage

SW-D rejects malformed base64 run-list cursors unless the decoded timestamp is ISO-8601 with a timezone and the run ID is valid. A tied-timestamp pagination test proves no omissions or duplicates; malformed cursors return HTTP 400. Focused activity API, cursor-edge, and runlog tests pass **48 tests**.

SW-E adds local protected-content regression coverage for comparison sharing, all non-external share policies, clipboard and file-export refusal, inventory and supporting-display exclusion, and protected basemap images. Focused MortimerHost privacy suites pass **55 tests**; one ScreenCaptureKit test skips because Screen Recording permission is unavailable. Live app/supporting-display capture remains open.

SW-K adds a compiled 100-sample rendered-navigation harness for wide and compact layouts, with synthetic fixtures and real `NSHostingView` layout/display. The current test runner has no `NSScreen`, so the harness skipped without producing rendered p95 values. The latest integrated store-only measurements are selection p95 **0.0022 ms** and cached navigation p95 **0.0213 ms**; these exclude SwiftUI rendering and network activity. Rendered navigation, paired voice latency, and ten-minute memory growth remain unmeasured.

The latest full local results are **3,497 Python passed, 4 skipped, 11 warnings, 2 subtests; 334 MortimerHost tests with 9 skipped and 0 failures; and 211 JarvisKit tests with 0 failures**. SW4's exact-run cancellation fix passes **74 focused tests**. The updated weighted implementation estimate is **87.7%**: SW0–SW6 scores **86/82/95/94/94/85/69%** at weights **10/15/15/15/20/15/10%** (8.60 + 12.30 + 14.25 + 14.10 + 18.80 + 12.75 + 6.90). This is implementation progress, not acceptance completion. Only SW-B and SW-C are accepted. VoiceOver/keyboard/live-voice, target-Mac rendering and ScreenCaptureKit, physical display/unplug/reconnect, real-VM isolation/restart/recovery, live provider and blinded human review, activation/rollback, full SW-K budgets, and release handoff remain open; runtime enforcement stays disabled.

### Resolved design decision — asynchronous creator validation activity ownership

An independent SW2 review found that the offline validator receipt is bound to its durable sandbox run, slug, candidate digest, and validation checks, but not to a Mortimer `agent_runs` ID, owning developer request, or recorded `offline-validate` attempt. The creator manifest declares no tool for this step. The trusted step-receipt API requires a real owned run and exact started attempt; attaching the existing validation receipt after the fact would fabricate that link. Keep this process step `unknown` until the selected ownership and evidence contract below is implemented. No checker mapping or creator activation was added.

Larry selected attachment to the originating Developer run. Carry its real
agent-run ID plus creator request, sandbox job, validation request and attempt
identities through asynchronous validation. Record the attempt before invoking
the validator. Append late validation evidence to that run's Skills Activity
without reopening or changing the Developer run's terminal status. Keep the
validation job's lifecycle separate, with candidate-digest and exact-request
binding, cancellation/restart reconciliation, and content-free events. A
completed validator receipt without a recorded attempt is not retroactive
proof of a step execution. The creator transport now supplies the genuine
Developer identity. The late-validation source implementation is now present;
see the 2026-09-28 completed-run validation activity checkpoint in the acceptance
status. Live multi-process/VM acceptance remains open.

### 2026-09-28 parallel follow-on status

Local progress since the previous checkpoint: SW-H now tests publication recovery
after reopening a session following simulated host interruption; all 119 sandbox
tests pass. SW5 review scoring now revalidates approved frozen fixture bytes,
case criteria, package revision, and model identity; its focused review/budget
suites pass 42 tests. The full Python suite passes 3,500 tests, with 4 skipped,
11 warnings, and 2 subtests. No live provider call or real VM trial was run.

SW-I already has synthetic Dynamic Type, accessibility-value, and process-state
coverage. Remaining VoiceOver, Full Keyboard Access, actual system text sizing,
spoken flow, and creator review need a target-Mac session. SW-F's IPv6 filter is
unproven: current Softnet rules cover IPv4, and a failed guest IPv6 connection
does not prove enforcement without an active IPv6 route. Verify with a working
guest IPv6 route and host canary in both provisioning and offline modes.

The prior **87.7%** weighted implementation estimate remains the last scored
estimate; this checkpoint does not rescore it or change gate acceptance. Only
SW-B and SW-C are accepted. Live VM lifecycle, provider/human review,
target-Mac accessibility/voice/display, activation/rollback, rendered/voice/
memory performance, final release, and the asynchronous validation-activity
ownership decision remain open. Keep runtime enforcement disabled.

The sandbox probe now labels IPv6 containment as unverified and reports
`full_network_containment_proven=false` and `acceptance_complete=false` unless
affirmative active-route and blocked-canary evidence is supplied. The current
probe does not collect that evidence, so full network containment remains an
open target-Mac gate. Four focused gate tests and all **123 sandbox tests**
pass. Refresh candidate-bound release receipts after this change; do not infer
VM acceptance from the unit-test result.

### 2026-09-28 rendered benchmark and protected-response follow-up

The earlier rendered-benchmark attempt skipped because `NSScreen.screens` was
empty; that result is superseded for this run by a successful release build on
an attached-window fixture. Across 100 samples, wide 1280×800 selection-to-
layout p95 was **18.513 ms** and cached navigation p95 was **27.021 ms**;
compact 720×800 measured **10.413 ms** and **11.076 ms**. Both layouts meet
SW-K's 20 ms selection and 100 ms cached-navigation budgets. Full-window bitmap
p95 was **16.280 ms wide / 7.345 ms compact** and is diagnostic, excluded from
selection response latency. The fixture had 100 catalog skills, 32 cached
details, zero detail requests during measurement, and 65 distinct rendered
frames. Paired live-voice latency and ten-minute memory growth remain open.

The protected-local response regression exposed startup message loss:
`AppMessageRouter.start()` created its `messageStream()` subscription from
inside an asynchronously scheduled task. It now creates the stream
synchronously before launching the consumer task. The focused
`LiveVoiceResponseStreamTests` pass **2/2**, including immediate protected
window delivery to the main workspace and exclusion from supporting-display
stores. The async test flush now drains the transport and router actor hops.
`SkillsWorkspaceRenderingTests` pass **18/18**. The full native release suite
passed all **16 MemoryGraphStore tests**, then stalled at
`PanelStoreTests.testReturningContentReleasesCapacityAndInventoryUsesStableIdentity`.
The two preceding PanelStore tests passed; the named test started without a
terminal result in the captured log. The same test and all **3 PanelStore tests**
pass in isolation, so a suite-order interaction remains unresolved. The full
suite has no terminal summary. The last weighted implementation estimate
remains **87.7%**, unrescored. Only SW-B and SW-C are accepted; platform,
provider, VM, accessibility, live-voice, memory-soak, activation/rollback, and
release gates remain open.

A captured sample of the stalled test runner shows XCTest's main thread waiting
while the dispatch thread soft limit of 64 was reported reached across
**3,288 samples**; those samples show AppKit workers
sampled blocked inside AppKit `NSAnimation._runBlocking`; physical footprint
was 462 MiB at sample time with a 1.0 GiB peak. The stalled PanelStore method
is synchronous, uses a fresh store, passes alone and in a focused run after the
memory-graph frame-time test, and creates no AppKit views. This points to
accumulated AppKit/SwiftUI animation work in the larger test process. Two
perpetual animation modifiers in the console have now been gated by Reduce
Motion, and the full-console test fixture enables that setting. A focused
active-agent rendering regression was added, but it could not run because the
shared SwiftPM build lock remained held; an isolated scratch build was blocked
by sandbox setup. Window-detach cleanup alone did not resolve the hang: a later
sample again reported the 64-thread soft limit reached across 1,978 sampler
frames, with workers in `NSAnimation._runBlocking`. Treat the animation change
as an unverified hypothesis until focused tests and the complete suite run;
do not attribute the failure to PanelStore or claim the full suite passes.

### 2026-09-28 reduced-motion and test-isolation follow-up

Added `mortimerReduceMotion` as the effective app motion setting: it follows
macOS `accessibilityReduceMotion` unless a host supplies an override. The
console breathing dot, agent pulse, drawer-tab scroll, adaptive stage, skills
workspace, result workspace, and voice-wave timeline now read this shared
setting. Relevant UI fixtures set reduced motion to avoid leaving animation
work active after rendering and navigation checks.

The focused adaptive/drawer/console/compact/panel group passes **25/25**. A
single filtered release process containing every test class before
`PanelStoreTests` and `PanelStoreTests` itself passes **184/184**. The full
unfiltered release process still stalls at the PanelStore boundary; its sample
shows XCTest's object-deallocation check and AppKit `NSAnimation._runBlocking`
workers after the dispatch soft limit of 64 is reached. This establishes the
panel tests are not independently failing and that the runner issue depends on
unfiltered-suite context; it does not prove the animation changes resolve the
full-suite stall. Keep SW-L open until an unfiltered suite run completes. The
full Python suite passes **3,500 tests, 4 skipped, 11 warnings, and 2
subtests**. `git diff --check` passes. The weighted implementation estimate is
still **87.7%**, not rescored; only SW-B and SW-C are accepted.

### 2026-09-28 partitioned native acceptance follow-up

To isolate the unfiltered XCTest hang from test failures, every MortimerHost
test class was run in two release processes. The classes through
`PanelStoreTests` passed **184/184**. The remaining classes passed **150 tests,
6 skipped, 0 failures** when the live ScreenCaptureKit capture case was
excluded. That capture case was also attempted separately and failed at stream
start with ScreenCaptureKit internal error `-3811` even though
`CGPreflightScreenCaptureAccess()` returned true. This capture path remains
unverified in this environment. The unfiltered suite still stalls in XCTest's
deallocation check with AppKit `NSAnimation._runBlocking` workers and the
dispatch soft limit reached. Partitioned runs show the test bodies pass in
groups, but do not close SW-L's required unfiltered full-suite gate.

JarvisKit's release tests passed **211/211**. A fresh SW-K rendered benchmark
measured wide/compact selection-to-layout p95 at **18.264/10.355 ms** and
cached-navigation p95 at **26.863/11.059 ms**; these local sub-budgets pass.
Paired live-voice p95 and ten-minute memory growth remain unverified. The full
Python suite passed **3,500 tests, 4 skipped, 11 warnings, and 2 subtests**.
The weighted estimate remains **87.7%**, unrescored; only SW-B and SW-C are
accepted.


### 2026-09-28 parallel diagnostic follow-up

The protected-window capture test now activates the host and requires its
fixture window to be visible and unoccluded before ScreenCaptureKit capture.
The current runner passes Screen Recording preflight and enumerates a display,
but cannot make the host app active within three seconds; the test fails at
that prerequisite before capture. Keep SW-E open and rerun this canary in an
interactive, foreground-capable Mac session. This explains the local `-3811`
failure as a WindowServer/session limitation; it does not prove the product's
protected-content capture path is correct.

For the native suite stall, the focused adaptive/compact/orb/panel sequence
passed **15/15** and a prior filtered prefix through PanelStore passed
**184/184**. The unfiltered suite still intermittently stalls in XCTest's
deallocation wait while AppKit `NSAnimation._runBlocking` workers accumulate
to the 64-thread dispatch soft limit. No single fixture or PanelStore defect
has been isolated. Keep SW-L open; continue evidence-led suite-order isolation
without weakening acceptance assertions. No weighted-score recalculation was
made: **87.7%** remains the prior unrescored estimate, and SW-B/SW-C are the
only accepted gates.


### 2026-09-28 Reduce Motion coverage follow-up

The audit of production animation sites found and corrected three additional
paths not yet honoring the shared effective motion preference: the wake ripple,
connect/reconnect satellite and lettering entrance fades, and transcript
auto-scroll. Reduce Motion now leaves a static visible wake ring, suppresses
entrance motion (including when the setting changes while mounted), and uses
non-animated transcript scrolling. A focused MortimerHost release run compiled
the change and passed **11 tests, 3 skipped, 0 failures**. All three skips
require a foreground-capable WindowServer; interactive visibility and actual
VoiceOver/macOS review remain open under SW3. No acceptance gate or weighted
score was changed.


### 2026-09-28 waveform teardown regression follow-up

`WindowVisibilityTests.testWaveStopsSamplingWhileWindowHiddenAndResumes` now
also closes the active-wave window and asserts that the renderer stops
requesting samples. This protects view/timeline teardown in addition to
hide/show suspension and resumption. The focused release target compiled; its
non-window observer test passed, while the three actual window tests skipped
because this runner cannot become the active app. Therefore the new close
assertion still needs execution in a foreground-capable Mac session and is not
acceptance evidence yet. The change does not prove the full-suite stall's cause.


### 2026-09-28 Reduce Transparency and Increased Contrast follow-up

All shared `.mortimerGlass` surfaces now honor macOS accessibility appearance
settings. Normal settings retain the agreed liquid-glass style. Reduce
Transparency selects a fully opaque panel surface, and Increased Contrast
selects an opaque surface with a stronger border. The explicit glass-off
rollback appearance is preserved. Four focused policy tests pass. The visual
result still requires review with both system settings on an unlocked Mac; this
does not close SW-I.


Rendering follow-up: `FullConsoleRenderingTests`,
`SkillsWorkspaceRenderingTests`, and `GlassAccessibilityTests` passed
**27/27** after the shared modifier change. This verifies call-site rendering
regressions with the current runner defaults. It does not visually validate the
macOS Reduce Transparency or Increased Contrast appearances; target-Mac review
remains required.

### 2026-09-28 protected display-sink follow-up

The display store now rejects protected payloads before creating a supporting
panel, appending to an existing Developer-run batch, or replacing/creating a
streamed response tile. The router keeps protected responses in the main local
workspace if the display sink refuses them. The direct protected-sink tests
pass **2/2**. A focused native release run covering `ContentPanelTests`,
`DisplayWindowStoreFitTests`, and `ShareCoordinatorTests` passes **30/30**;
including the two new direct-sink tests gives **32/32**. This strengthens the
display handoff boundary but does not verify ScreenCaptureKit output from the
running app. SW-E capture acceptance and all other open gates remain open.

The weighted scorecard is recorded in `docs/acceptance/skills-workspace/STATUS.md`:
**88.2% implementation progress** (SW0–SW6 scores **86/82/95/96/94/86/69%**,
weights **10/15/15/15/20/15/10%**). Only SW-B and SW-C are accepted; this
implementation estimate does not represent acceptance or release completion.

The current unfiltered MortimerHost release run completes **341 tests with 6
skipped and 1 failure**. Its sole failure is the protected-window capture
fixture's foreground-app prerequisite: the test host did not become active, so
pixel capture and comparison did not run. This is not a product pass or a
product capture defect finding. Repeat the test in an unlocked,
foreground-capable session; SW-E and SW-L remain open. The prior unfiltered
XCTest teardown stall did not reproduce in this run.

The same test process reports a fresh 100-sample rendered Skills result:
wide/compact selection-to-layout p95 **19.141/11.397 ms**, cached-navigation
p95 **27.898/11.826 ms**. These meet the 20/100-ms sub-budgets, but the current
sandbox denied the `hw.model` query, so this result is not a verified
hardware-bound target-Mac receipt. Paired live-voice latency and ten-minute
memory growth remain open under SW-K.

SW2 currently has three exact host-owned step mappings in
`config/skill_step_checks.yaml`: current weather, repository status, and
repository history. The focused checker/service suites pass **29 tests**.
Every unmapped step still reports `unknown`; the general creator offline-
validation activity ownership question remains open and must not be filled by
attaching a receipt to a run after the fact.

### 2026-09-28 sandbox cancellation crash-recovery follow-up

`Session.resume()` now reconciles a durable cancellation marker with the
controller before returning a terminal cancellation error. This covers the
crash window where the host persisted `cancelled.json` but exited before
stopping a running or provisioning VM. The interruption-recovery regression
and focused session suite pass **10/10**. Tart is unavailable in this runner,
so real VM stop/reopen/reconnect recovery and SW-H acceptance remain open. The
weighted implementation estimate remains **88.2%** pending full rubric
recalibration against all listed milestones; only SW-B and SW-C are accepted.

The parallel SW-I accessibility audit found no substantiated local defect in
the inspected Skills Workspace controls: accessible labels/state, process-step
buttons, and large-text layout behavior already have focused coverage. The
agent could not rerun SwiftPM tests because sandbox application was denied
before build. Live VoiceOver, Full Keyboard Access, and unlocked-Mac visual
acceptance remain open.

The parallel SW-G offline evaluation audit found no further code gap. The
harness already verifies frozen fixtures, preflights trial budgets, runs
without tools, separates blinded outputs from condition keys, binds artifacts
by digest, and rejects incomplete or unsafe review evidence. **43** focused
evaluation tests passed and Ruff was clean. No provider calls were made; the
24 live provider trials and independent human ratings remain open.

The parallel SW-F network-isolation audit found no safe IPv6 fix supported by
the pinned runtime: Softnet 0.23.0 accepts IPv4 CIDRs, while omitting it from
Tart 2.37.0 restores shared NAT. Do not add an unsupported `::/0` rule or claim
containment. SW-F needs a separately verified IPv6 filtering layer or
supported NIC-less VM configuration, followed by active-route IPv6 canaries
in both modes on the target VM.

### 2026-09-28 unfiltered native suite prerequisite handling

The ScreenCaptureKit test now treats inability to activate the test host as an
environmental skip, while retaining the actual pixel-for-pixel protected vs.
body-only capture assertion whenever Screen Recording permission and a
foreground WindowServer are available. The focused target compiled and ran:
**4 tests, 1 skipped, 0 failures**; this locked session skipped at the earlier
Screen Recording permission check, so it did not exercise activation or actual
window capture. The fresh unfiltered MortimerHost suite completed **341 tests,
9 skipped, 0 failures** in 62 seconds. `git diff --check` passes. This replaces
the prior run's single activation-prerequisite failure and clears the local
unfiltered test-suite portion of SW-L; SW-E capture, all other SW-L evidence,
and the remaining acceptance gates remain open.

### 2026-09-28 parallel SW0/SW2/SW6 follow-up

SW0's fixture schema now accepts a successful `skill_step_finished` event only
when it carries a `check_receipt_id`; the synthetic event fixture demonstrates
that valid shape, and regression coverage rejects it when the receipt is
removed. Its README explicitly states this is a synthetic contract fixture,
not live execution evidence. SW2's configured MCP inventory now rejects
duplicate YAML mapping keys in the global config and marks an individual
server manifest incomplete when ambiguous; it no longer trusts PyYAML's
last-value behavior. SW6 adds exact and one-character-over primary and
primary-plus-support injection-budget boundary tests, including reversed input
ordering. Runtime flags remain off; provider calls: **0**.

Parent verification: the combined fixture, step-check, readiness, runtime
inventory, event API, and selector groups pass **77 tests**. The full Python
suite passes **3,505 tests, 4 skipped, 11 warnings, and 2 subtests** in 109
seconds. The unfiltered MortimerHost suite passes **341 tests, 9 skipped, 0
failures**. Ruff currently reports four style findings in the audited files
(three existing `jarvis/skill_service.py` import/branch findings and one
existing test `dict()` style finding); no lint-clean claim is made. The
creator-validation activity-ownership decision remains unresolved.

The release evidence verifier was rerun after the native-test changes and
reported candidate-bound receipts stale for SW-B, SW-C, SW-E, performance, and
the app bundle. The dirty worktree fingerprint has since changed again due to
the SW0/SW2 implementation and fixtures. Earlier SW-B/SW-C acceptance applies
to the prior fingerprint only; do not count it as acceptance for this current
candidate until their evidence is rerun and rebound. The current candidate has
**0/12 verified gates** until candidate-bound receipts are refreshed; the
previously frozen candidate had **2/12 accepted**. Screen Recording remains
unavailable, so actual window capture is still unverified.

The evidence-anchor score is recalibrated to **88.5% implementation progress**:
SW0–SW6 scores **87/82/96/96/94/86/70%**, with fixed weights
**10/15/15/15/20/15/10%** and contributions **8.70 + 12.30 + 14.40 + 14.40 +
18.80 + 12.90 + 7.00 = 88.50%**. The small SW0/SW2/SW6 increases reflect the
now-valid receipt-backed event fixture contract, duplicate-YAML fail-closed
inventory, and exact prompt-budget boundary regression coverage. This is an
implementation estimate; it does not turn stale receipts or skipped live
acceptance into completed gates.

### 2026-09-28 SW2 runtime/readiness YAML consistency

The strict duplicate-key YAML loader is now shared by the read-only MCP
inventory and the live `SkillRegistry`. Ambiguous `config/mcp_servers.yaml`
therefore returns unknown readiness and is rejected before any child server
starts, instead of being interpreted differently by the UI and runtime. The
loader still honors standard YAML merge semantics, including explicit
overrides of inherited defaults, while rejecting duplicate explicit keys at
any mapping depth. Added regressions cover runtime no-start on duplicate keys,
nested duplicate rejection, and valid merge override. Focused registry and
readiness suites pass **62 tests**; the full Python suite passes **3,509 tests,
4 skipped, 11 warnings, and 2 subtests** in 108 seconds. The helper has no Ruff
findings; Ruff still reports seven existing style findings in adjacent service,
registry, and service-test code. Runtime discovery and readiness from the live
voice process remain separate, unverified evidence.

SW2's evidence-anchor score increases to **97%** for aligning static inventory
and the actual MCP loader. The revised SW0–SW6 scores are **87/82/97/96/94/86/70%**.
At fixed weights **10/15/15/15/20/15/10%**, contributions are **8.70 + 12.30 +
14.55 + 14.40 + 18.80 + 12.90 + 7.00 = 88.65%**, reported as **88.7%
implementation progress**. Current-candidate acceptance remains **0/12** until
the source changes are finalized and candidate-bound receipts are rerun; no
acceptance gate or runtime feature flag is implied by this score.

### 2026-09-28 parallel SW-D/SW-E/SW-H follow-up

Local work proceeded in three independent lanes. Native Activity decoding now
rejects impossible lifecycle claims, unsupported or unbounded evidence refs,
success without a host `check_receipt_id`, and protected/truncated rows that
still expose identifiers. Memory-graph PNG sharing now fails closed until the
bitmap has payload-level privacy classification and identity; ordinary result
PNG paths no longer borrow that bitmap, while text sharing remains available.
Both Swift changes have regression tests and pass `swiftc -frontend -parse`,
but their focused SwiftPM tests could not execute because sandbox initialization
failed and the WebRTC dependency could not be fetched. They are implementation
changes, not verified acceptance.

Creator request reconciliation now preserves a concurrent cancellation request
instead of overwriting it with stale draft status. Its deterministic race test
passes; the focused request suite passes **43 tests**. Combined Python
verification passes **105 focused tests** and **3,510 full-suite tests, 4
skipped, 11 warnings, and 2 subtests**. Ruff passes on the touched YAML loader,
registry/readiness files and associated tests; 17 existing BLE001/S110 findings
remain elsewhere in `jarvis/skill_requests.py`. `git diff --check` and Swift
syntax parsing pass.

The weighted implementation estimate is **88.9%** (SW0–SW6 **87/82/97/96/95/86/70%**;
fixed weights **10/15/15/15/20/15/10%**; contributions **8.70 + 12.30 + 14.55 +
14.40 + 19.00 + 12.90 + 7.00 = 88.85%** before rounding). The one-point SW4
increase reflects tested cancellation-race handling; unexecuted Swift tests do
not increase SW3. Candidate-bound acceptance receipts are still stale and the
current dirty candidate remains **0/12 verified gates**. Real VM lifecycle,
protected-screen capture, integrated voice/accessibility, physical-display,
live evaluation, and final frozen-release acceptance remain outstanding.

### 2026-09-28 current-candidate receipt rebinding

All six receipts required by `scripts/verify_skills_workspace_release_evidence.py`
were refreshed against the final documented candidate fingerprint and verified
current. The verifier passes. SW-B and SW-C are the two accepted acceptance
gates for this candidate (**2/12**): 89 package-integrity tests, all five enabled
pins matching with `skill-creator` inert, and 14/14 public selection fixtures
plus 104 focused tests with zero provider calls. SW-E remains open because the
foreground-window pixel capture skipped; its protected PNG and share-path tests
pass locally. The release app bundle embeds the matching fingerprint and passes
strict signature verification, but was not launched, installed, or deployed.

Fresh 100-sample SW-K local results are selector p95 **4.427/4.397 ms** for
unique-hit/no-skill, store selection/cached navigation **0.0007/0.0075 ms**, and
rendered wide/compact selection-to-layout **18.944/10.824 ms** with cached
navigation **27.387/11.292 ms**. Local timing budgets pass; hardware identity
could not be verified, and paired voice latency and ten-minute memory growth
remain unmeasured. The weighted implementation estimate remains **89.0%**; this
receipt refresh does not imply release acceptance.

### 2026-09-28 native execution and local receipt refresh

The earlier SwiftPM test restriction was resolved using the cached WebRTC
checkout and manifest compilation permission. JarvisKit `AdminAPITests` pass
**11/11**, including strict Activity trace rejection; MortimerHost's full suite
passes **342 tests, 7 skipped, 0 failures**. The new memory-graph PNG sharing
privacy test and the complete `ConsoleActionCoordinatorTests` pass. The skipped
tests need foreground or connected-two-display conditions and do not count as
those acceptance checks.

Fresh local SW-B/SW-C evidence also passes: **89 package-integrity tests**, the
public selection corpus **14/14** with **zero provider calls**, and **104
selection/fixture/SubAgent tests**. Current runtime digest enforcement remains
off. No actual runtime readiness, visual app capture, VM isolation, or target
display evidence is inferred from these checks.

The weighted implementation estimate is now **89.0%**: SW0–SW6 scores
**87/82/97/97/95/86/70%** at fixed weights **10/15/15/15/20/15/10%**, with
contributions **8.70 + 12.30 + 14.55 + 14.55 + 19.00 + 12.90 + 7.00 =
89.00%**. The one-point SW3 increase reflects the passing native test suite;
unverified target acceptance remains open. The candidate evidence verifier
still reports stale receipt fingerprints and the current source remains **0/12
verified gates** until current evidence is rebound and the release bundle is
rebuilt.

### 2026-09-28 parallel implementation update: SW2, SW-F, and SW-I

Parallel local work added strict validation for host skill-step receipts, with
regressions for schema-version type confusion, timestamp shape/timezone, exact
identity, and check-list validation (**26 focused tests passed**). The guest
probe now reports an observed IPv6 default route and requires positive route
and blocked-canary evidence before it can report containment; absent evidence
remains inconclusive (**43 probe/controller tests passed**). Native shared
navigation now announces process-step selection and collapse with generic
VoiceOver messages and never reads internal step identifiers (**30 focused
SkillsWorkspace tests passed**).

The weighted implementation estimate is **89.3%**: SW0–SW6 scores
**87/82/98/98/95/86/70%**, fixed weights **10/15/15/15/20/15/10%**, and
contributions **8.70 + 12.30 + 14.70 + 14.70 + 19.00 + 12.90 + 7.00 =
89.30%**. This reflects the two-point improvement in SW2/SW3 local implementation
evidence. It does not close any target-environment gate. The current candidate
has **0/12 verified gates** because all six required candidate-bound receipts
are stale, including the release bundle fingerprint.

Remaining work: run Tart provisioning/offline IPv6 canary and lifecycle trials;
resolve the documented ownership model for asynchronous creator-validation
activity before implementing dependent attribution; complete integrated
readiness and real skill-runtime evidence; finish live VoiceOver, keyboard,
physical-display, and foreground capture acceptance; run the live paired
provider evaluation and blinded human review; measure latency and memory on the
identified target Mac; then freeze source, rerun required evidence, rebuild the
release bundle, and verify signatures and receipts. Tart is currently absent
(`ready_to_boot: false`), so VM containment acceptance remains open.

### 2026-09-28 additional parallel code closure and integrated verification

SW-E's native image-share path now requires the result's explicit
`approved_external` policy and exact image URL membership in that result's
declared image/basemap references. Memory-graph endpoints are denied, and image
bytes are decoded and re-encoded as bounded PNG before sharing, stripping source
metadata. Focused sharing/action tests pass **37 tests**; live protected-window
and supporting-display capture remains an acceptance prerequisite.

SW-G's review scorer now rejects cost evidence inconsistent with billing mode.
Subscription costs must use the fixed-fee basis and zero reported/reserved
cost; provider/local costs must use the price-map actual-usage basis. Focused
evaluation/budget tests pass **45 tests**, with no provider calls. Live paired
trials, frozen outputs, independent blinded ratings, and maintainer acceptance
remain open.

SW-H publication recovery now moves a dead worker with unavailable sandbox
status into an explicit reconciliation state and preserves the state while a
local worker remains alive. Focused publication/request tests pass **50 tests**.
This never treats uncertain publication as success.

Integrated local verification: Python **3,520 passed, 4 skipped, 11 warnings,
2 subtests**; MortimerHost **344 tests, 9 skipped, 0 failures**; JarvisKit
**212 tests, 0 failures**. The latest full MortimerHost skips still include
foreground/display requirements. The candidate verifier rejects all six
candidate-bound receipts as stale, leaving **0/12 gates verified for the
current dirty candidate**.

The weighted implementation estimate is **89.8%** with SW0–SW6 scores
**87/82/98/99/96/87/70%**, unchanged weights **10/15/15/15/20/15/10%**, and
contributions **8.70 + 12.30 + 14.70 + 14.85 + 19.20 + 13.05 + 7.00 =
89.80%**. The new SW3/SW4/SW5 points account only for tested local behavior;
they do not substitute for the plan's live acceptance criteria.

Remaining sequential/environment-bound work: answer the creator-validation
activity ownership design choice before linking offline validation to a real
run/attempt; run Tart lifecycle and IPv6 canary tests; complete live app,
VoiceOver, keyboard, and physical-display checks; gather runtime readiness and
actual skill-run evidence; perform the bounded 24-trial provider comparison and
independent human review; measure latency and memory on the identified target
Mac; then freeze candidate source, rerun/bind receipts, rebuild and verify the
release bundle. Runtime enforcement and creator activation stay disabled until
their stated gates pass.

### 2026-09-28 release bundle helper correction

The release packaging script now builds without a dSYM, avoiding the verified
`dsymutil` permission failure on this host, and supports an explicit opt-in
`MORTIMER_SWIFT_BUILD_DISABLE_SANDBOX=1` for controlled local SwiftPM builds.
Sandbox disabling remains off by default. Tests verify the release flags,
opt-in flag, code-sign ordering, and no-launch behavior. The release bundle
build and strict ad-hoc signature verification succeeded with launching
disabled; no installation or deployment occurred.

The weighted estimate is **89.9%** (SW0–SW6 **87/82/98/99/96/87/71%**;
weights **10/15/15/15/20/15/10%**; weighted contributions **8.70 + 12.30 +
14.70 + 14.85 + 19.20 + 13.05 + 7.10 = 89.90%**). SW6 increased one point
for the now reproducible local release bundle. Rebind receipts to the resulting
candidate fingerprint after the implementation and plan updates; stale receipt
identity must not be represented as current acceptance.

### 2026-09-28 current candidate evidence refresh

All six receipts required by the release-evidence verifier now match the
documented candidate fingerprint; the verifier passes. SW-B and SW-C are
verified for this candidate (**2/12 gates**): package-integrity regressions
pass **89/89** with all five enabled pins matching and the creator package
inert; deterministic selection fixtures pass **14/14**, followed by **104
focused tests**, with zero provider calls. SW-E's result-bound image sharing
path passes local tests. Foreground window capture remains skipped because the
runner lacks Screen Recording permission.

Current local SW-K samples measure runtime selector p95 at **8.530/8.043 ms**
and store selection/cached navigation p95 at **0.0009/0.0095 ms**. The rendered
navigation benchmark skipped because this host has no active display; hardware
identity, paired voice latency, and ten-minute memory growth remain unverified.
The release app bundle embeds the matching fingerprint and passes strict
ad-hoc signature verification. It was not launched, installed, or deployed.

These receipts do not close environment-bound acceptance. Tart IPv6/lifecycle,
live VoiceOver, physical displays, live provider evaluation and blinded human
review, target-Mac performance/soak, activation/rollback, and deployment remain
open. Preserve runtime enforcement and creator activation gates until their
acceptance criteria pass.

After the release-helper change, the final aggregate Python rerun passes **3,522
tests, 4 skipped, 11 warnings, and 2 subtests** in 113.97 seconds. MortimerHost
remains at **344 tests, 9 skipped, 0 failures** and JarvisKit at **212 tests, 0
failures**; the helper change itself is additionally covered by **9 focused
tests** and two subtests. Any later source or plan edit invalidates receipt
binding; rerun the candidate verifier before handoff.

### 2026-09-28 parallel audit fixes

Parallel SW1/SW2/SW4 implementation audits closed three local defects: package
catalog validation now verifies every declared resource is a canonical,
existing regular text file that the bounded reader can serve; runtime inventory
rejects overlong IDs and tool names at the authenticated API boundary; and
creator offline-validation receipts emit a specific failed reference check when
strict inspection rejects missing or unsafe resources. The full Python suite
passes **3,534 tests, 4 skipped, 11 warnings, and 2 subtests**; focused combined
verification passes **122 tests** and `jarvis.agent_skills --validate` passes.

The updated implementation estimate is **90.5%**, using SW0–SW6 scores
**87/83/98/99/97/87/73%**, weights **10/15/15/15/20/15/10%**, and a weighted
total of **90.45%**. Only **2/12 acceptance gates** remain verified. Candidate
receipts were refreshed to the final candidate fingerprint after the plan/status
update. Redirecting Swift and Clang module caches to `/private/tmp` allowed the
no-launch release app bundle to build; strict ad-hoc signature verification
passed, and `scripts/verify_skills_workspace_release_evidence.py --root .`
passes. The app was not launched, installed, or deployed. These local checks do
not represent release readiness or deployment, and all live VM, provider,
accessibility, physical-display, activation/rollback, and human-review gates
remain open.

The full native suites were rerun after the parallel fixes: MortimerHost passes
**346 tests with 9 skipped and 0 failures**; JarvisKit passes **212 tests with
0 failures**. The skips require Screen Recording, a foreground-capable app, or
two connected displays, so this is local regression evidence rather than live
acceptance. Candidate receipts and the release bundle fingerprint must be
refreshed once more after this plan/status update.

### 2026-09-28 current candidate verification

After SW2 readiness/privacy hardening and SW4 publication-retry recovery, the
current local suites pass: Python **3,542 passed, 4 skipped, 11 warnings, and 2
subtests**; MortimerHost **347 passed, 9 skipped, 0 failures**; JarvisKit **212
passed, 0 failures**. SW-B focused package checks pass **96 tests**; SW-C
selection checks pass **106 tests** and the public fixtures pass **14/14 with
zero provider calls**; SW-E passes **41 tests with one Screen Recording skip**.
The current no-launch production bundle passes strict ad-hoc signature
verification. Candidate-bound evidence is current, while the app remains
unlaunched, uninstalled, and undeployed.

The weighted implementation estimate remains **90.7%** using SW0–SW6 scores
**88/84/98/99/97/87/73%** at weights **10/15/15/15/20/15/10%**. This
implementation estimate is separate from the **2/12 accepted gates**. Tart
isolation/lifecycle, provider trials and blinded review, VoiceOver, physical
display behavior, target-Mac voice latency and memory soak,
activation/rollback, and final release handoff still require their specified
live evidence; no source-level score substitutes for those gates.

### 2026-09-28 SW2 inventory/privacy and SW4 publication-recovery follow-up

SW2's configured MCP inventory now fails closed when the config file or server
root is a symlink, in addition to refusing symlinked server directories and
manifests; an untrusted path cannot make the static tool inventory appear
complete. Runtime-inventory input remains bounded (36-character runtime IDs,
at most 256 tools, and 128 characters per tool). The trusted step-receipt writer
also checks the durable protected-run marker inside its SQLite write
transaction, so a late receipt cannot restore skill trace data after protected
activity has been scrubbed.

SW4 recovery now permits an idempotent retry from `publication_pending` after a
host interruption, but only when the current frozen candidate matches both the
session candidate digest and the complete offline creator receipt. The focused
creator and sandbox-session regression tests pass **30 tests**. These changes
improve local correctness; SW2/SW4 real-runtime lifecycle and privacy acceptance
remain open, and this update does not close an acceptance gate or change the
weighted estimate. Source and documentation changes require candidate evidence
to be refreshed before release review.

### 2026-09-28 final local verification after SW3 fix

The no-launch production bundle was rebuilt after the native source and
documentation updates, and strict ad-hoc signature verification passes.
Current receipts are rebound to the final candidate and the release-evidence
verifier passes. Final local suites are Python **3,537 passed, 4 skipped, 11
warnings, and 2 subtests**; MortimerHost **347 passed, 9 skipped, 0 failures**;
and JarvisKit **212 passed, 0 failures**. The app was not launched, installed,
or deployed. Nine host-suite tests still require Screen Recording, a foreground-
capable app, or two displays. Only **2/12 acceptance gates** are accepted;
runtime, hardware, provider, accessibility, human-review and release gates
remain open.

### 2026-09-28 SW0/SW2/SW5 parallel follow-up

SW0's package metadata schema now rejects vendor-reserved `claude` and
`anthropic` skill IDs, matching runtime frontmatter validation; negative fixture
tests cover both cases. SW2's trusted step-receipt insertion now checks the
durable protected-activity marker under its SQLite write transaction. The new
interleaving test proves a late receipt is refused after a protected-run scrub,
without restoring skill-specific trace data. SW5's provider-free evaluator
review found no local correctness gap; its 45 paired-review and budget tests
pass, and no model provider was called.

The complete Python suite passes **3,537 tests, 4 skipped, 11 warnings, and 2
subtests**; the combined focused schema/catalog/authoring/receipt checks pass
**70 tests**. Relevant Ruff `F,E9`, catalog validation, and diff checks pass.
The updated weighted estimate is **90.7%**: SW0–SW6 scores **88/84/98/99/97/87/73%**,
weights **10/15/15/15/20/15/10%**, contributions **8.80 + 12.60 + 14.70 +
14.85 + 19.40 + 13.05 + 7.30 = 90.70%**. Only **2/12 acceptance gates** are
accepted. The source and documentation changes invalidate prior candidate
receipt fingerprints; refresh the no-launch bundle and bind receipts after
this update. Physical-display, foreground, accessibility, live voice, Tart,
provider, human-review, activation/rollback, and deployment gates remain open.

### 2026-09-28 SW3 compact repeated-navigation fix

The compact Skills detail now opens for every valid shared navigation request,
including repeated selection of the currently selected skill/tab/run/step/example
after returning to the library. A separate navigation-request revision makes
valid repeated requests observable without treating invalid targets as state
changes. The focused Skills/action tests pass **71 tests**; the full MortimerHost
suite passes **347 tests, 9 skipped, 0 failures**. Store-only p95 is **0.0020 ms**
for selection and **0.0182 ms** for cached navigation across 100 samples; this
does not establish rendered or target-hardware performance. VoiceOver,
keyboard-only, and two-display acceptance remain open. The overall weighted
estimate remains **90.7%** because SW3 already remains below 100% pending those
live criteria. Refresh candidate bundle/receipts after this native change.

The full native suites were rerun after the parallel fixes: MortimerHost passes
**346 tests with 9 skipped and 0 failures**; JarvisKit passes **212 tests with
0 failures**. The skips require Screen Recording, a foreground-capable app, or
two connected displays, so this is local regression evidence rather than live
acceptance. Candidate receipts and the release bundle fingerprint must be
refreshed once more after this plan/status update.


### 2026-09-28 current-main integration and live IPv6 result

Fetched main `2e6f769` and read its AGENTS.md/ROADMAP protocol. WS-03 ownership
matches `codex/isolated-20260924`. Preserved the prior work in local checkpoint
`44cb8ae`, then started a merge of current main; shared-file conflicts are being
resolved by preserving both implementations. The pending allow-list deny-row
proposal is retained in the named stash `preserve human-commit allow-list
proposal during main integration`, rather than committed by the agent. No
production files were changed. Read-only production migration inspection found
only main IDs through `0027_notice_memory_review`, and none of the Codex IDs.

Reserved numbers follow ROADMAP §3: Skills events use 0033; client tokens use
0034; mail/calendar retains 0035; added the next available reservation 0036 for
skill step-check receipts. Both migration branches are retained in ordered form.
Twenty database tests pass, including upgrade from the deployed main schema
with preservation of existing notices and repeat-run idempotency. Other merged
code is not yet verified and the merge is not yet committed.

The actual IPv4/IPv6 canary test now passes: a gateway-matched synthetic path
works before and after both Softnet modes, and provisioning/offline modes block
both protocols. Eight observations, the exact driver, logs, receipt and hash
manifest are in `docs/acceptance/skills-workspace/receipts/ipv6-verified-2026-09-28/`.
The disposable VM was stopped and deleted. This closes the missing live IPv6
canary subcheck for installed Softnet 0.23.0-e5fd48c, not all of SW-F or release
acceptance. The first failed positive control remains preserved separately.

Per current-main ROADMAP, the memory ordering/ownership decision (CX-07) and
Skills navigation placement (WS-03) were requested from Larry. Continue
independent backend conflicts; do not decide these pending choices by timeout.
The bounded API-evaluation and physical-monitor questions also remain pending.

### 2026-09-28 — creator routing decision reconfirmed

Larry explicitly selected routing creator work through a real Developer agent
run. The merged delegate bridge calls the session's Developer `SubAgent.run`,
whose `RunLogger` creates the run identity; the pipeline retains that bridge
before wrapping ordinary delegation for voice workflows. Creator validation
remains attached to the originating run, with its separate job lifecycle and
without reopening a completed run. This decision is settled; current-main
integration and live acceptance are still incomplete.

### 2026-09-28 — navigation approval

Larry confirmed separate top-level Skills beside Workflows, inclusion in the
Display menu, voice navigation via “open skills”, and related-workflow links.
The merge must preserve the existing Workflow Viewer and its semantics. Native
integration and acceptance remain open; this decision authorizes the layout,
not a claim that the frozen candidate has passed.

### 2026-09-28 — integrated main verification

All merge conflicts are resolved. Skills and Workflows retain separate top-
level, Display-menu and voice view modes; related-workflow links select the
matching workflow without replacing the existing viewer. Creator execution
retains real Developer identity, exact-once dispatch across voice retries,
and late validation association. Native results: JarvisKit 219 tests with no
failures; MortimerHost 372 executed, seven environment-dependent skips, no
failures. Broad Python run: 4,851 pass, four skips and two outstanding human
deny-list gates (health script and frozen authoring fixtures). The proposal
patch is reviewable and not applied automatically.

Rendered 100-sample debug measurements on the current host: selection-to-layout
p95 19.844 ms wide / 7.514 ms compact; cached navigation p95 50.751 / 27.690 ms.
These pass their local timing sub-budgets. They do not close paired voice,
ten-minute memory growth, physical display, accessibility, provider evaluation,
human review, activation/rollback or frozen release acceptance. Exact logs and
hashes are under the main-integration-2026-09-28 acceptance receipts. No app was
deployed or activated by this work.

### 2026-09-28 — merged-release claim race

PR #94 merged as `79aad4c`, but its Linux validation failed one creator
claim-settlement test in addition to the two pending human allow-list checks.
The setup worker published `state=error` before its `finally` block persisted
`failed` for the staged action claim. The request could observe that gap and
return the error while the claim still read `claimed`. The intended 50 ms
worker join was mistakenly indented inside the thread-start exception path
and never ran. The follow-up puts the join after successful start and settles
an observed setup error's claim before returning it. The existing test now
holds the worker's claim update to force the race; the request must still
return a failed claim. The whole admin self-edit module passes 69 tests on the
Mac. No human allow-list edit, production deploy or Skills activation is
claimed by this follow-up.

Full disposable Mac verification at `b2d858a`, with the proposed two-entry
human allow-list patch applied only in that throwaway worktree and implicit
dotenv loading disabled, passed 4,860 Python tests, with seven skipped and two
subtests passed. GitHub Linux CI has not yet run on this follow-up commit.

Larry subsequently committed and pushed the two human-only protections as
`617048a` (health probe) and `1152dd5` (frozen authoring fixtures). Codex
verified both entries and the clean branch. These source protection gates
are now implemented; Linux CI, merge and staged deployment remain next.
