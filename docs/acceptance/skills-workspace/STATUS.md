# Skills workspace implementation status

Plan: [Skills Workspace and Skill Creation Implementation Plan](../../plans/MORTIMER_SKILLS_WORKSPACE_IMPLEMENTATION_PLAN.md)

Status vocabulary: `not_started`, `in_progress`, `implemented_unverified`,
`blocked`, `accepted`. Implementation/deployment evidence is distinct from
live feature acceptance and activation.

Latest live UI audit (2026-09-30): the installed app and production checkout
both report `39fc6f9`; Skills library, Overview, intended Process navigation,
and the no-trace Activity state were observed in the connected native app.
The Versions endpoint returned the expected fail-closed 503 while bearer auth
is dormant; the running UI's generic connection message is corrected in merged
PR #145 (`9da99d4`) but is not yet deployed. No SW-A–SW-L gate was newly accepted.
See [live UI audit](receipts/live-ui-audit-2026-09-30.md).

Merged-source native check on the MacBook Air `Mac17,4` (Apple M5, macOS
27.0): JarvisKit passed 219 tests; the full MortimerHost test command passed.
Its 100-sample rendered Skills selection-to-layout p95 was 13.099 ms wide /
7.683 ms compact, and cached navigation p95 was 44.646/28.173 ms. Paired
voice latency and the ten-minute live-trace memory soak remain unmeasured, so
SW-K remains open.

Latest checkpoint (2026-09-28 20:19 EDT): PR #96 (`539f8f6`) is deployed on
the Mac through DEPLOY-MAIN. All CI workflows passed; exact merged-release
checks passed 4,860 Python tests (seven skips), JarvisKit 219 tests, and
MortimerHost 372 tests (seven environment skips), with zero failures. Both
human-only protection entries are on main. The creator claim race and the
Skills/orb rendering performance failures are fixed. Production code and app
revision match; all five services and the app are running from production.
See [deployment and rendering evidence](receipts/rendering-performance-2026-09-28/).
This does not accept or activate remaining live/provider/VM/UI gates below.

The prior historical VM verifier remains failed (11/12 stages), despite its
candidate checks passing: the old baseline has a floating-point assertion
failure. IPv4/IPv6 containment passed the later eight-observation canary, but
full live creator lifecycle and release acceptance remain open. Paid evaluation,
human review, physical monitors, live accessibility/voice, activation/rollback,
and remaining performance gates are unaccepted. No deployment is claimed.
Earlier checkpoints below are history, not current release status.

## Approved product direction

The Skills workspace is the dashboard: a scannable library opens into a
per-skill detail view. Process shows the reviewed intended steps; Activity shows
only actual recorded run evidence. The design contract, model-neutral handoff
sequence, and SW3 acceptance criteria are in the implementation plan. This
direction is agreed; it does not close any implementation, accessibility,
voice, display, privacy, or release gate.

## Current increment

**SW0 — in progress.** Baseline notes are recorded in [BASELINE.md](BASELINE.md).
Synthetic catalog, detail, creator-request, activity-event, package-metadata,
and voice-action contracts are in `tests/fixtures/skills_workspace/`. The
strict JSON schemas and consistency checks cover catalog/detail/request/event
contracts, package revisions, event identity and order, step references, and
forbidden catalog fields. Metadata and voice actions also pass the runtime
catalog parser and bounded console protocol validator. Visual/voice reference
capture and app/display baseline evidence remain open.

**SW1 — in progress.** Fixed complete-body parsing in `jarvis/agent_skills.py`:
frontmatter now closes only on an exact delimiter line and file reads preserve
LF/CRLF. Regression cases cover Markdown rules, diff headers, long bodies and
malformed delimiters. Added strict companion metadata for all five current
skills and `jarvis/skill_catalog.py` for read-only validation, safe package
limits, process graph checks and SHA-256 revision identity. Tests cover invalid
metadata, traversal references, symlinks, digest changes, and invalid package
cards. Added `jarvis/skill_resources.py` and wired `skill_reference_read` into
the existing SubAgent tool loop. Reads are limited to declared UTF-8 `.md` and
`.txt` files under the selected enabled package revision, use no-follow
descriptor-relative opens, reject stale digests and budget overruns without
truncation, and never execute package content. The shared 16,000-character
budget includes serialized reference results; an oversized selected skill
body is omitted rather than exceeding the cap. Migrated the five enabled
entries in authoritative `config/skills.yaml` to strict schema v2 with SHA-256
package pins. All five pins match on the current tree. Digest enforcement
remains off because `JARVIS_SKILLS_WORKSPACE_ENABLED` is unset; the legacy
runtime loader remains active pending rollout gates. `python -m
jarvis.agent_skills --validate` now checks each package's full catalog structure,
validates a companion manifest when present, rejects invalid registries and
missing enabled packages, and compares every enabled v2 digest pin while
allowing legacy skills without manifests. Focused agent-skills/catalog/CLI tests
pass **79 tests**. On the current tree, `--validate` succeeds and `--list`
reports six packages, five enabled with matching pins, and the creator inert.
Runtime digest enforcement and dependency readiness remain open.

**SW2 — in progress.** Added read-only `GET /api/skills` (bounded pagination)
and `GET /api/skills/{skill_id}` (revision-bound detail), plus
`GET /api/skills/{skill_id}/runs` and `GET /api/skills/runs/{run_id}/events`
to the existing admin service. Migration `0030_skill_events` stores typed,
bounded, content-free events with user/run/event and user/run/sequence
uniqueness. Actual skill selection records the package digest. A reference read
records a content-free event with the real tool-call ID; its contents are
available only in that run's next model context and are redacted from run logs,
activity events and API traces. Protected runs store only a generic marker, and
a run that becomes sensitive scrubs prior skill identity. Event reads are user-scoped,
cursor-based and omit prompts/results. Run retention removes skill events with
their owning run. Current readiness remains `unknown` because none of the
enabled packages has a runtime revision-pin, tool-session or route-compatibility
receipt. Selection, reference-read, and unambiguous tool-to-process-step
start/finish-attempt events are emitted; successful tool returns still leave
the natural-language step outcome `unknown`. The service does not claim a step
passed without trusted validator evidence. Added
`jarvis/skill_service.py` to check configured MCP tool manifests and credential
presence without launching servers or returning secret values. Missing
dependencies become typed blockers; configured tools, credential presence,
route/privacy compatibility and revision pinning remain explicitly unknown
until their runtime evidence is available. Corrected two stale tool names in
the weather and MCP-authoring skill manifests. The creator request API exists,
but creator readiness remains unavailable until runtime receipts are supplied.

SW2 boundary recheck (2026-09-26): the admin API and voice pipeline own separate
`SkillRegistry` instances in separate processes. The admin service therefore
cannot truthfully promote manifest-declared MCP tools to runtime-available; no
trusted cross-process session receipt currently exists. Route compatibility
and credential authentication likewise remain unknown without an owning
runtime attestation. This is the correct conservative result, not a missing
static check. The catalog's `activity_trace` capability refers to the bounded
read API and actual selection/reference-read events; it does not claim process
step completion. Focused catalog, API, ownership/cursor, privacy and readiness
verification on 2026-09-26 passed **66 tests** (one upstream FastAPI test-client
deprecation warning). Step completion remains unknown pending trusted
controller/validator evidence; no step success is inferred from the reviewed
process map. Current whole-worktree Python verification also passes **3,208
tests, 4 skipped, 11 warnings, and 2 subtests**. A fresh native host run built
and passed **278 tests with 7 skipped and 0 failures** using the existing local
SwiftPM checkout and a `/private/tmp` Clang module cache; the skips and physical
Mac acceptance remain open.

**SW3 — in progress.** Added the native Skills destination, searchable and
filterable responsive library, selectable intended-process nodes with detail
and branch navigation, typed run/activity API models, and an Activity timeline
for recorded run events. Linear processes now expose an explicit next-step
control; branch edges remain labelled and selectable. Activity polling stops
for settled runs and uses the planned foreground/background cadence while a
selected run is active. Added app-owned ephemeral `SkillsStore` state and closed
Python/native console actions for search, filters, skill selection, tabs,
process steps, and runs. Native inventory publishes bounded skill names/status,
step IDs/titles, and run IDs/status/timestamps; prompts, answers, resource
bodies, and search text are excluded. Coordinator rejects targets not present
in the currently loaded catalog/process/run. Existing compact voice region
remains in `AdaptiveStageView`; no new window or result owner was introduced.
Catalog and detail responses now include readiness reason codes; the native
overview renders concise explanations so “unknown” is distinguishable from a
known blocker.
The latest responsive review corrected two UX gaps: catalog load now lands on
the library without auto-opening its first card, and widths below 960 points
use a full list → detail navigation with a visible Back button. Back keeps the
selected skill and step in `SkillsStore`; resizing from wide detail into compact
layout keeps the detail open. Catalog rows now use app-owned surfaces rather
than the default black sidebar selection. The Process view now exposes declared
edges for both branching and guidance maps, and only linear maps get the
single-next-step treatment. Proposed-but-disabled packages are not counted as
attention solely because they are disabled; the policy now also excludes an
intentionally inert installed package when its reason codes are only
`skill_disabled` plus expected unknown runtime checks. Unexpected blockers and
failed/stale verification remain visible. Added policy tests for both paths;
the focused native policy suite passes **5 tests**.
After this filter change, the full native host suite passed **280 tests, 7
skipped, 0 failures**. The skips are not acceptance evidence for the skipped
display/foreground cases.
The read-only Versions view now reports manifest version, package SHA-256,
enabled registry-pin match state, and caller-owned candidate request evidence.
It does not claim activation or expose activation/rollback controls. Previous
installed revisions and Git history remain unavailable through this API. The
reference-read integration test verifies the declared resource reaches the next model round
but is absent from activity callbacks, application logs and persisted run
records. Latest verification on candidate `977f50bec7b77bd7d3381d3b8f3d63fa69bd00e2`
(uncommitted working tree):

- `./.venv/bin/python -m pytest tests/unit/test_agent_skills.py tests/unit/test_skill_service.py tests/unit/test_admin_skills_catalog.py tests/unit/test_skill_resources.py tests/unit/test_subagent.py -q` — **158 passed**.
- `./.venv/bin/python -m pytest -q` — **3,156 passed, 4 skipped, 2 subtests passed**, 11 warnings.
- `./.venv/bin/python -m jarvis.agent_skills --list` — five enabled skills;
  schema v2; all five package pins report `matches`; enforcement is off.
- `swift test --package-path macos/MortimerHost --skip-build` — **274 executed,
  6 skipped, 0 failures** before the latest responsive-view changes.
- `swift test --package-path macos/MortimerHost --filter SkillsWorkspacePresentationPolicyTests` — **3 passed**.
- `swift test --package-path macos/MortimerHost --filter SkillsWorkspaceRenderingTests` — **1 passed**; rendered synthetic library/detail fixtures at 1280- and 720-point widths. Screenshots are under ignored `.build/interface-fixtures/skills-*.png` and are test artifacts, not production Mac acceptance.
- `swift test --package-path macos/MortimerHost --skip-build` — **278 executed,
  6 skipped, 0 failures** after the responsive-view changes. Three skips require two connected displays; three
  window/animation skips report that the XCTest process cannot become the active
  app in this WindowServer session. `WindowVisibilityTests` now skips only when
  that host precondition fails; the hide/show/animation assertions remain active
  on a foreground-capable session. Skills action/coordinator and registry tests
  passed. Physical display and foreground-window behavior remain unverified.
- `swift test --package-path macos/JarvisKit` — **203 passed, 0 failures**,
  including typed Skills activity route and bounds tests.
- `git diff --check` — passed.

The first SwiftPM invocation was blocked by the workspace sandbox; the native
suite then ran with elevated test execution. These checks do not establish
visual, VoiceOver, live voice, physical display, or Mac deployment acceptance.
The CLI reports six skill folders, five enabled skills, and all six current
`SKILL.md` files valid.

The loader and nearby agent/runtime files contain preexisting concurrent
log-redaction and routing edits. They remain preserved.

**SW4 — in progress.** Added a Mortimer-specific `skills/skill-creator`
adaptation with concise authoring instructions, on-demand quality and lifecycle
references, Apache 2.0 license text, attribution, and a five-step reviewed
process map. Upstream provenance is pinned to
`anthropics/skills@33375500bcea98d610eb30ce10ac4e59b89c390d`; the source-tree
digest is recorded in its companion manifest. The adaptation omits upstream
scripts, evaluation UI, Claude CLI assumptions, and provider invocation. It is
present in the library but remains inert: it is absent from
`config/skills.yaml` and is not injected into runtime prompts. Added
`jarvis/selfedit/skill_policy.py`, a host-side helper that accepts only a
canonical approved slug and limits writes to that skill's text/metadata files
and its public fixture directory. Unit tests cover sibling, registry,
validator, sandbox, traversal, hidden/secret, executable, and malformed-slug
refusals. Added `jarvis/skill_authoring.py`, which binds that policy to a
slug-specific workspace key and delegates start/read/write/validate/cancel/
revert/draft-publication to the existing Runtime, Session, file journal,
verifier, and publisher. It keeps the package disabled and states the review
boundary in draft PR text. Added `jarvis/skill_authoring_validation.py`, a
provider-free host validator that reuses Mortimer's strict package parser,
checks required files, package limits, complete instruction bodies, declared
references, source-license files, matcher fixture shape/IDs/outcomes, static tool
availability, and an unchanged protected skill registry. It binds an immutable
receipt to the candidate fingerprint. The service
requires that receipt to match the same frozen snapshot as independent VM
verification before it will draft a PR. At the time of the original assessment,
it was not exposed through an admin/shared-console action. Inspection found the
localhost sidecar had no explicit authentication middleware; this was an
unresolved prerequisite, not evidence that localhost binding was authentication.
Larry approved resolving the shared migration conflict on 2026-09-26: Remote
Access now appends `0031_client_tokens` after `0030_skill_events`, and its
dependent Mail/Calendar migration follows as `0032_brief`. Tests use FakeRuntime
and do not prove behavior in the real VM.
Hardened the submit boundary to accept only a complete versioned receipt for
this skill, with a SHA-256 package revision, provider-call count of zero, passing
host checks, and the exact current candidate digest. The complete expected check
set is required. Malformed JSON shapes, incomplete receipts, and edits after
validation are refused before publication. Each new validation attempt clears
the prior receipt first, so a failed host recheck cannot leave old evidence
publishable. Receipt matching now runs as a preflight under the existing sandbox
session lock, held through publication, preventing a concurrent edit from
changing the reviewed snapshot between check and publish. Focused authoring,
validation, policy, session, and workspace tests pass **53 tests**; these include
FakeRuntime paths plus a real Session lock test and do not close real-VM
acceptance. The full Python suite passes **3,208 tests, 4 skipped, 2 subtests
passed**, with 11 warnings. This verifies repository regressions but does not
replace real-VM acceptance.
The inventory CLI now labels a schema-v2 package without an enablement pin as
“not configured (inert)” rather than a false digest mismatch. Focused validation
Focused creator/catalog/self-edit/sandbox tests passed **237 tests, 41
subtests**; full `./.venv/bin/python -m pytest -q` passed **3,178 tests, 4
skipped, 2 subtests**, with 11 warnings. After the host creator validator and
service receipt binding, focused validation/policy/service tests passed **26
tests**; full `./.venv/bin/python -m pytest -q` passed **3,186 tests, 4
skipped, 2 subtests**, with 11 warnings. `git diff --check` passed. The CLI lists six folders, five
enabled, creator inert, and all five enabled pins matching. `git diff --check`
passed. No live VM run or provider evaluation was performed.

**2026-09-27 authenticated request integration.** Added `jarvis/skill_requests.py`
and the authenticated `POST /api/skills/requests` plus
`GET /api/skills/requests/{request_id}` routes. The API derives the owner from
the bearer-authenticated request identity, binds each UUID to a canonical
payload digest, rejects conflicting reuse, stores only content-free receipts
under the sandbox host directory with mode `0700`/`0600`, and does not put task
briefs in status or diagnostics. Draft VM startup and offline validation return
stable asynchronous job IDs; status reconciliation consults the existing
slug-scoped Runtime session. A protected request is refused because persistent
sandbox work cannot satisfy protected retention. Live evaluation is explicitly
disabled. Activation/rollback create exact-revision maintainer review records;
they do not edit the registry or activate content. The offline validator checks
that matcher fixtures are well formed but does not run quality comparisons.
Focused request, whole-sidecar auth, catalog and authoring tests pass **43
tests**. The sidecar route inventory and exhaustive auth coverage were updated
from 62 to 64. At that checkpoint native request controls, voice action wiring,
real-VM cancellation/retry/publication, matcher evaluation, and maintainer
review acceptance remained open.
The post-integration full Python suite passed **3,305 tests, 4 skipped, and 2
subtests**, with 11 warnings. The run also exposed and closed unrelated
verification drift in the temporary admin test route cleanup, declared
service-token transitive reads, the auth table's documented `larry` default,
and startup-log redaction assertion. No macOS host VM or provider call was used.

**2026-09-27 creator execution and reviewed publication boundary.** The draft
worker now invokes the pinned `skill-creator` through the ordinary developer
workload route, using only `file_read`, `edit_propose`, `session_validate`, and
`session_decline`; it cannot submit. `review_ready` requires the host-owned
candidate-bound offline receipt, never model prose. The authenticated request
status includes only the exact bounded path/diff when the request owner still
matches the live sandbox candidate and creator receipt. Added explicit
`request_publish`, bound to the owner's draft request ID, candidate digest, and
package revision. It runs separately through the existing host publisher and
cannot merge or activate; uncertain publication is reconciled against the
sandbox record instead of blindly retried. The native Skills library now
exposes a capability-gated creation sheet, polls its owner request, displays
the exact diff, and requires an explicit “Open review PR” action. It also
exposes explicit cancellation while sandbox authoring is active. The brief
remains transient and is excluded from shared console inventory and durable
request receipts.

Before drafting, the host now adds an existing-skill reuse index containing
only installed package IDs, display names, descriptions, categories, and
related workflow IDs. It also locally matches the developer's authored
workflow and at most one active learned-procedure hint; only the workflow's
matched name/trigger/steps/completion criteria and the procedure's label and
description enter model context. Procedure task tokens and source-run IDs are
excluded. This gives the creator relevant prior context without granting
cross-skill file reads or treating learned hints as authority.

Latest focused Python verification at the initial integration checkpoint:
**43 tests passed** across creator-agent, request API, authoring
validation/service, and catalog suites. An earlier
request/API/auth run passed **29 tests**. The Swift build compiled both targets
and `SkillsWorkspaceRenderingTests` passed **2 tests**, including a synthetic
creator-form render. `git diff --check` passed.
No real sandbox VM was started, no GitHub publication was attempted, and no
live provider or matching-quality evaluation was run. Voice-driven authoring
and publish-preview binding, real-VM cancellation/retry/publication acceptance,
and macOS visual/VoiceOver acceptance remain open.

After the reconciliation and publish-idempotency checks were added, the latest
focused Python request/creator/auth/catalog run passed **29 tests**. The
subsequent full Python run, including the creator's bounded workflow/procedure
context, passed **3,318 tests, 4 skipped, 2 subtests**, with 11 warnings. The
latest focused creator/request/authoring/catalog run passed **47 tests**.
JarvisKit passed **204 tests**;
MortimerHost passed **280 tests, 6 skipped**, and the final incremental creator
form render passed **2 tests**. The skipped display/window tests still need the
specified physical-display or foreground-capable Mac conditions. The creator
form render is synthetic and does not establish live VoiceOver or Mac operator
acceptance.

## Open implementation sequence

Status checkpoint: **2026-09-28**. The steps below are all still open; the
completed code and test evidence described above are partial evidence only.
Implementation can proceed in parallel by lane, with one owner per shared
file/contract:

| Step | Status | Remaining work | Parallel/dependency note |
| --- | --- | --- | --- |
| SW0 — baseline/contracts | `in_progress` | Synthetic catalog/detail/request/event/package/voice fixtures now pass cross-contract checks; finish baseline visual/voice/display evidence. CLI regression covers malformed v2 registries with missing/extra pins and unknown fields while enforcement is off. | Can proceed alongside SW1, SW3, SW5 scaffolding, and SW6 public fixtures. Freeze shared schemas before edits. |
| SW1 — loader/registry | `in_progress` | Selection now revalidates the enabled pin, package digest, and parsed instruction body immediately before prompt injection; stale primary skills fail closed and stale optional support is dropped. Focused race tests pass. Complete target-runtime readiness evidence; keep enforcement off. | Can proceed alongside SW0, SW3, SW5, SW6; use a single owner for package and registry files. |
| SW2 — readiness/activity API | `in_progress` | Implemented the host-controller receipt contract, authenticated owner scoping, cursor pagination, runtime inventory receipts, and three exact pinned-package step checks (weather conditions, Git status, and bounded Git history). Overflow (>8 reporters in one freshness window) still forces readiness to unknown. Synthetic receipt paths pass; live route, credentials, cross-process target-runtime readiness, and other process steps remain open. | Backend can proceed beside SW3 only while versioned API/event contracts remain stable. Live Mac readiness and broader host-check mappings are serialized before enabling trusted completion. |
| SW3 — native workspace | `in_progress` | Skills detail shares the supporting-display stage; pinned developer-run tiles continue aggregating results into one tile. Activity labels distinguish failure, observed return, unknown outcome, and historical package revision. Skills controls use shared typed actions; Activity responses require both run ID and selection generation. MortimerHost passes 329 tests with 7 skipped. Complete integrated VoiceOver/keyboard/large-text review, spoken navigation, Mac visual review, and physical-display behavior. | Synthetic/native implementation and accessibility checks can proceed beside SW2; live acceptance waits for integrated backend and frozen build. |
| SW4 — creator lifecycle | `in_progress` | Creator requests reject the reserved `skill-creator` package before durable reservation or sandbox start. Queued draft/validation work uses cross-process atomic claims. Post-call draft/validation receipts and cancellation require the exact expected sandbox run ID; regressions cover stale replacement runs. Complete real-VM isolation, restart/reconnect, and publisher-reconciliation trials; preserve maintainer review boundary. | Static tests/docs can proceed in parallel. Mutable sandbox lifecycle trials must run one request at a time. |
| SW5 — evaluator | `in_progress` | Core evaluation revalidates approved frozen fixture provenance before provider calls; blinded artifact writers enforce owner-only directories. Scoring now requires the with-skill and without-skill arms to match provider, model, route, and billing mode. Focused paired-review/budget tests pass 39; no provider calls have occurred. Live route setup, 24 trials, frozen artifacts, blinded human review, activation diff, and rollback remain open. | Fake-provider tests can proceed beside SW0–SW4 and SW6. Live trials require explicit policy+environment enablement and parent privacy/model-route gates; run the 24-trial comparison sequentially under its single bounded budget. Human review follows artifact freeze; activation and rollback are serialized gates. |
| SW6 — selection/release | `in_progress` | SW-C local selection criteria are accepted. The latest fresh 100-sample rendered-navigation run measured selection-to-layout p95 at 18.264 ms wide / 10.355 ms compact and cached navigation at 26.863 / 11.059 ms, within the 20/100 ms local budgets. Voice p95 regression, ten-minute memory growth, live route/tool readiness, activation/rollback, and release acceptance remain open. | Public deterministic fixtures can proceed beside SW5; paired voice/memory target-Mac checks and rollout wait for integration and verified receipts. |

Parallel work lanes now safe: **A)** SW0/SW1 baseline and loader evidence,
**B)** SW2 backend trace/readiness, **C)** SW3 native UI/accessibility,
**D)** SW5 fake-provider evaluator plus SW6 public deterministic fixtures.
SW4 static hardening may join any lane if it has a distinct file owner. Merge
and regression integration, mutable VM trials, live provider comparison,
physical-display/voice acceptance, activation/rollback, and release/handoff are
serialized gates. A workstream that needs to alter a shared API/event/fixture
contract must coordinate and version that change before dependent parallel work
continues. This schedule reduces independent implementation wait time; it does
not reduce any acceptance requirement or authorize live provider calls.

- [ ] SW0: Finish shared contract fixtures and capture application/voice/display baseline evidence.
- [ ] SW1: Finish loader/CLI acceptance and pin-based readiness evidence. V2 migration and five matching pins are present, but enforcement remains off and readiness is unknown where runtime evidence is absent.
- [ ] SW2: Complete runtime readiness evidence, trusted step instrumentation,
  reference-read trace edge cases, and API trace edge-case/ownership acceptance.
- [ ] SW3: Complete native library/detail/activity views and shared voice/display actions. Library-first wide/narrow layouts, complete cursor pagination, pointer selection beyond 32/50 entries, a capability-gated creator sheet, exact-diff review, explicit publish, synthetic rendering, preview-bound voice draft, listed-step explanation, declared-example preview, shared-stage skill-detail transfer/return, and privacy-safe async status announcements are implemented in the candidate. Integrated native test execution, actual VoiceOver/keyboard, native Mac visual review, live spoken-flow acceptance, and physical-display acceptance remain open.
- [ ] SW4: Complete reviewed creator package, scoped authoring policy and sandbox lifecycle. Package/provenance, slug-scoped policy, Runtime/Session adapter, host candidate-bound receipts, authenticated user-scoped/idempotent draft/status/publish/cancel requests, and native authoring controls are implemented and unit-tested. Real-VM lifecycle and live publisher-reconciliation acceptance remain open; fake-service receipt matching is covered.
- [ ] SW5: Finish the gated evaluator and verify comparison, activation review and rollback. Strict disabled-by-default route/budget parsing, the six required frozen cases, paired runner, conservative pre-call budget reservation, output-cap enforcement, usage attribution, randomized blinded export, private condition/usage files, human rating template, and acceptance scorer are implemented and locally tested. The CLI refuses to proceed without explicit policy and environment gates. No `skill_eval` route is configured; live comparison, actual human review, activation diff, and rollback remain open.
- [ ] SW6: Finish runtime evidence and release acceptance. The opt-in deterministic
  primary selector and explicit skill-ID path are implemented behind both flags;
  a global public dry-run reports exact legacy/v2 agreement on 14 cases. Live
  route/tool evidence, production rollout, candidate quality evaluation,
  activation, and rollback remain open. The optional mutually compatible
  supporting-skill path is implemented and tested; no current package pair
  declares compatibility.

## Acceptance gates

**SW-B package integrity is accepted** by
[`sw-b-package-integrity-20260928.json`](receipts/sw-b-package-integrity-20260928.json).
Its candidate suite covers body preservation, strict/duplicate metadata,
package-size limits, traversal/symlink refusal, digest drift, stale resource
reads, and inert-by-default installation; the catalog CLI confirms the five
active package pins match and the creator remains inert. **SW-B and SW-C are
the only accepted gates; SW-A and SW-D through SW-L remain open.** Five process metadata files are checked
in. The pinned creator and reviewed authoring path are integrated in this
candidate worktree, but no live sandbox run, skill activation, provider
evaluation, PR merge, or Mac deployment has been performed as part of this
increment.

## Next actions

1. Run the three `WindowVisibilityTests` on a foreground-capable Mac session;
   skipped visibility behavior remains unverified here.
2. Finish SW0 baseline visuals/voice/display receipts without overwriting
   concurrent changes.
3. Complete SW1 pin-based readiness and loader/CLI acceptance; keep enforcement
   off until all relevant rollout evidence exists.
4. Review the rendered Skills UI on the Mac, then verify VoiceOver, keyboard
   navigation, large text, and shared-display moves before accepting SW3.
5. Exercise the preview-bound voice draft flow, then draft, offline validation,
   cancellation, reconnect/retry, and reviewed draft-PR flows in the real VM.
   Voice can start a draft only; PR publication still requires the native
   exact-diff review. Keep candidate package,
   registry/config, validator/policy, and dependency edits outside the allowed
   set. The reviewed `0031_client_tokens` auth foundation is already applied.
6. Validate tool-backed process-step events on the Mac, then add further step
   success evidence only where validators prove it; successful tool returns and
   uninstrumented steps remain explicitly unknown.
7. Keep skill activation and live-provider evaluation off until their plan gates
   and parent privacy/model-route conditions are satisfied.
8. Run the frozen selector latency/memory budgets on the target Mac and gather
   live route/tool readiness evidence before considering any flag rollout;
   validate background refresh and synchronous rebuild when registry pins change.

**2026-09-27 explicit skill selection and runtime selector increment (SW6 partial).**
The existing delegation tool accepts an optional bounded `skill_id` only when
both Skills v2 rollout flags are enabled. Its description limits use to an exact
skill ID the user explicitly named. The runtime passes that request to the
deterministic selector, which bypasses lexical matching only; package pin,
readiness, route privacy, capability and live tool checks still apply. An
explicit request now refuses before any model call if the selector refuses or
its runtime evidence raises an error. No automatic legacy fallback occurs while
selection v2 is opted in. With flags unset, the old interface and matcher remain
unchanged. Focused selection, fixtures, package loader, SubAgent and delegation
tests pass **211 tests** after adding the selector-error refusal case. Live
provider/MCP evidence, production flag rollout, supporting-skill selection,
accessibility, voice acceptance, and SW-A through SW-L release gates remain
open. No activation, provider evaluation, PR, merge, or deployment was performed.

The migration choice was reaffirmed on 2026-09-27: auth remains `0031_client_tokens`
after `0030_skill_events`, and the dependent brief migration remains `0032_brief`.
This is already reflected in `jarvis/db.py` and both owning plans; old review
documents retain `0016` only as historical evidence of the resolved conflict.

**2026-09-27 public selection evaluation increment (SW6 partial).** Added a
global frozen fixture corpus and provider-free `scripts/check_skill_selection_fixtures.py`.
Unlike the per-package examples, each case names the exact expected skill ID or
explicitly expects no skill, so a negative case cannot pass by selecting the
wrong skill. The corpus has five positive, five no-skill and four overlapping
cross-skill requests. Both the unchanged legacy matcher and v2 selector match
all 14 expected outcomes under synthetic ready-route/tool evidence; the CLI
returns a per-candidate score/threshold/reason report and records package pins
and fixture digest. Receipt: `receipts/skill-selection-fixtures-2026-09-27.json`.
Focused fixture/selector tests pass **17 tests**. This is public synthetic
evidence only and does not enable either runtime flag or establish quality on
private/live tasks. Next SW6 work: supporting-skill conflict and combined-budget
selection tests, while keeping production packages single-skill absent mutual
compatibility declarations.

**2026-09-27 compatible supporting-skill selection increment (SW6 partial).**
The v2 selector now returns at most one independently qualifying support skill,
and only when both manifests mutually declare the primary/support relationship.
Undeclared or one-sided pairs preserve the primary alone; combined instruction
text must fit the fixed 16,000-character budget. The SubAgent snapshots and
rechecks both package pins before injection. The bounded reference tool can
read only from the selected primary or support package, using its run-snapshotted
revision and shared remaining budget; arbitrary skill IDs are refused. Current
repository packages declare no mutual skill-to-skill pair, so the public corpus
still selects no support. Tests cover mutual/one-sided compatibility, combined
budget refusal, two-body injection, and support-owned reference reads. The
focused selector, SubAgent, resource, fixture, and delegation suites pass
**161 tests**. Architecture, repository map and skill review guidance now
describe the opt-in limit. Live Mac performance, voice, route/MCP evidence,
production rollout, and SW-A through SW-L acceptance remain open.

**2026-09-27 selector snapshot/performance increment (SW6, SW-K partial).**
Added a 60-second package/catalog snapshot keyed by the enabled registry and
revision pins. MCP inventory, route/privacy compatibility, capability mapping,
credential presence and readiness are reevaluated on each selection. Package
snapshots are prewarmed during SubAgent construction only when both v2 flags are
enabled; before injection the selected packages are still re-read and checked
against the active pins. The benchmark fixture is materialized as 100 synthetic
packages in a temporary directory and exercises the real runtime selector on
this Mac without provider calls. Across 100 samples per positive/no-skill case,
warm-cache p95 was **4.39/4.37 ms** (20 ms budget); prewarm cost was **790.62 ms**.
Receipt: `receipts/skill-selection-performance-2026-09-27.json` records platform,
base commit, dirty-tree state, fixture/config/package-set and implementation
digests. After 60 seconds, a same-pin refresh now runs in a background worker
while the prior immutable snapshot remains usable; package contents are checked
against current pins before injection. Failed refreshes preserve the snapshot
and retry with backoff; registry pin changes take a synchronous verified rebuild.
Native navigation latency, paired voice p95,
memory growth, display, and full SW-K/SW6 gates remain open.

**2026-09-27 voice-draft binding increment.** Added closed Python and native
console actions `skill_request_preview` and `skill_request`. The preview accepts
only a draft operation, a new validated slug, and a brief capped at 8,000
characters. The host stores that payload only in process memory behind an
opaque UUID that expires after five minutes and can be consumed once. The
follow-up action opens the Skills workspace and passes the brief directly into
the existing authenticated creator sheet; the brief is never added to the
shared console inventory. Voice has no publish, activation, or rollback path.
The existing exact-diff sheet remains the only path to request publication.
The console tool description teaches the two-call preview/start sequence.

Focused verification: Python console protocol, skill request, and creator agent
tests passed **28 tests**; MortimerHost console coordinator tests passed **20**;
JarvisKit console protocol tests passed **6**; MortimerHost coordinator coverage
now includes **21 tests**, and Skills workspace synthetic rendering tests
passed **2**. The full Python suite passed **3,319 tests,
4 skipped, 2 subtests**, with 11 warnings. This covers protocol parity, invalid
operation/slug/preview-ID validation, expiry, one-time consumption, workspace handoff,
inventory privacy, and existing sheet rendering. Live voice timing,
VoiceOver, display routing, real sandbox lifecycle, and publisher
reconciliation remain unverified. No sandbox VM, provider request, GitHub PR,
or deployment was started.

The first whole-suite run reported **3,319 passed, 4 skipped, 2 subtests** and
one failure because the bearer-auth inventory test expected 64 routes. After
updating it to 65 and adding the production matcher assertion, the complete
Python suite passed **3,321 tests, 4 skipped, 2 subtests**, with 11 warnings.
The whole-route bearer test plus API/protocol cases passed **16 tests**; the
selector/fixture/API/auth set passed **13 tests**. MortimerHost coordinator
tests were rerun after the final store changes: **22 passed**. No runtime
voice, VoiceOver, display, real-VM, live-provider, PR, or Mac deployment
acceptance was performed.

**2026-09-27 process/example voice increment.** Added `skill_step_explain` to
the mirrored closed console protocol; it resolves only a listed step and opens
that step in the reviewed Process view. Added `skill_example_preview`, bound to
both a listed skill ID and one of that skill's declared example IDs. The
catalog exposes only those bounded IDs. A new read-only API serves a synthetic
request only when its case file is schema-valid, has matching positive and
negative cases, exactly matches the package's declared IDs, and its current
package digest matches the v2 registry pin. The native detail page displays
the request and expected routing outcome with a clear note that no skill or
model is executed. Five synthetic matcher files were added and validated
against the current lexical matcher; every expected positive and negative
selection matched. Their metadata digests were refreshed in `config/skills.yaml`.

Focused verification for this increment: Python Skills API/catalog/authoring
fixture/protocol tests passed **38 tests**; native console coordinator tests
passed **22**; Skills rendering passed **2**. The all-five CLI pin check reports
all enabled digests match. Mac visual/VoiceOver and actual live voice actions
remain unverified. Synthetic examples are initial fixtures, not evidence that
SW5 quality evaluation or activation has passed.

The 2026-09-27 architecture refresh now describes the synthetic-preview
boundary and the limited voice navigation/draft-handoff authority in
`docs/ARCHITECTURE.md`, `docs/REPO_MAP.md`, and `skills/README.md`. The current
worktree recheck reports all five enabled package pins match; `git diff --check`
is clean. System Python lacked PyYAML, so this check used `.venv/bin/python`.

Added JarvisKit contract tests for the native synthetic-example API call. They
assert the exact authenticated GET route, decode the synthetic marker and
expected-selection fields, and reject malformed skill/example IDs before any
network request. `swift test --package-path macos/JarvisKit --filter AdminAPITests`
passes **9 tests**. This closes a native API contract coverage gap; it does not
close the visual/runtime acceptance gates.

**2026-09-27 selector increment (SW6 partial).** Added the pure deterministic
`jarvis/skill_selection.py` primary selector. It preserves the lexical threshold
and shared-token floor, orders by score descending then slug ascending, lets an
explicit choice bypass lexical scoring only, and refuses disabled packages,
unknown readiness, absent tool/capability evidence, missing catalog snapshots,
and over-budget selected bodies. It returns structured per-candidate scores,
threshold outcomes and reason codes without task text or token strings. Only
the selected body is read for the final budget check, and callers cannot raise
the fixed 16,000-character cap. Tests cover tie-breaking, explicit-selection
boundaries, package/readiness/privacy/tool/capability failures, and budget
refusal. The shared public positive/negative fixtures now exercise both the
legacy matcher and this selector under explicitly synthetic evidence; the
selector/fixture/catalog API group passes **18 tests**. Selector plus legacy
matcher regressions pass **71 tests**. Ruff and `git diff --check` pass for the
changed selector, fixture and test files.
The runtime now chooses this path only when `JARVIS_SKILLS_SELECTION_V2=1`;
both it and `JARVIS_SKILLS_WORKSPACE_ENABLED=1` are required. In that mode the
SubAgent does not fall back to the legacy matcher if evidence is unavailable.
`config/skill_capabilities.yaml` maps every current manifest capability to
required model-route and live tool inventory evidence; the selector checks
current package pins, readiness, route privacy, actual registered tools, and
the capability map before selecting. Legacy single-skill behavior remains the
default with either flag unset. Current tests exercise helper selection with a
fake registry and the SubAgent opt-in branch; live provider/runtime, actual MCP
startup, production flag rollout, and the compatible supporting-skill phase
remain unaccepted.

**2026-09-27 synthetic example rendering increment (SW3 partial).** The
MortimerHost rendering fixture now declares one synthetic example in both the
catalog and skill detail. A new native test selects that example, confirms the
authenticated preview route was requested, and renders the Overview with the
synthetic request. The complete `SkillsWorkspaceRenderingTests` class passes
**4 tests**, including wide/narrow library/process, creator-sheet rendering,
and truthful tool-observation versus step-completion labels.
This verifies the view-to-API path using a stub; it does not establish live
Mac visual review, VoiceOver, or actual admin-service interoperability.

**2026-09-27 tool-backed process-step trace increment (SW2 partial).** The
SubAgent now records a step-start event before a tool call and a step-finish
event after the shared tool-result classifier returns, but only when exactly
one selected manifest step declares that tool. Each event is linked to the
actual tool-call ID. Tool failures produce `failed`; successful returns and
cancellation produce `unknown`, because a tool result alone does not prove the
manifest's natural-language success criteria. Ambiguous tool-to-step maps
produce no step claim. A fake-registry run verifies event sequence, status,
step ID and evidence reference. Focused SubAgent/runlog tests pass **39 tests**.
Live controller, cancellation, protected-data and native Activity acceptance
remain open; no step is marked successful solely from a successful tool call.
The combined focused Python selector/SubAgent/runlog/resource/delegation suite
passes **211 tests**. The native `SkillsWorkspaceRenderingTests` suite passes
**4 tests** and checks that tool-call evidence is labeled as an observation
with an unvalidated step outcome.

**2026-09-27 skill-evaluation route/budget preflight (SW5 partial).** The
dedicated `skill_eval` workload now requires both a strict `skill_evaluation`
budget block and `JARVIS_SKILL_EVAL_ENABLED=1`. It requires background priority,
no fallback and a route fixed by policy rather than user preference or runtime
override. Batch, per-trial, input/output token and deadline limits have hard
maximums. Paid routes require a numeric spend ceiling; each call must reserve a
known conservative cost before execution. The `skill_eval` usage-ledger rung is
registered. Tests cover disabled defaults, route override rejection, missing
spend caps, invalid ceilings, per-call reservations and subscription call
budgets; **26 tests pass**. No `skill_evaluation` block is configured in
`config/model_access.yaml`, the environment gate remains off, and no provider
was called. The with/without runner, blinded artifact, live comparison, human
quality review, activation diff and rollback remain open.
Adjacent model-route, model-execution, usage-ledger and evaluator-budget tests
pass **70 tests**.

**2026-09-27 evaluator runner increment (SW5 partial).** Added the fixed paired
runner for frozen public/synthetic fixtures, a six-case creator-skill rubric,
strict fixture loading, and the host CLI. It reserves each call before invoking
the existing model-execution callback, calculates a conservative input bound
from the actual UTF-8 prompt bytes, applies the configured output cap and
timeout, records usage under `skill_eval`, and refuses adapters that cannot
prove cap enforcement. API-compatible and SAYGM-gateway adapters are eligible;
subscription adapters remain refused until their cap behavior is verified.
The blinded review file and condition key are written with mode 0600 into
separate directories and existing evidence cannot be overwritten. The CLI
stops before provider execution unless policy and environment gates are active.
Focused evaluator tests pass **18 tests** and the adjacent route/execution/
ledger/evaluator suite passes **79**. No provider was called. Live route setup,
human quality review, activation diff and rollback remain open.

**2026-09-27 parallel implementation update.** SW0/SW1 evidence, SW2 backend
and API work, SW3 native UI/accessibility work, and SW5 fake-runner/SW6 public
fixture work can proceed in parallel with distinct owners and frozen shared
schemas. SW4 static hardening may join a lane with a separate file owner.
Contract changes must be coordinated and versioned before dependent work
continues. Mutable VM trials, live paired provider calls, integration and
regression acceptance, physical-display/voice acceptance, activation/rollback
and release remain serialized gates. Parallel execution shortens independent
implementation time without closing or waiving acceptance gates.

**2026-09-27 full regression verification.** The repository Python suite passes
**3,371 tests, 4 skipped, and 2 subtests**, with 11 warnings. This broad result
does not close target-Mac voice/display, VoiceOver, or real sandbox lifecycle
acceptance.

**2026-09-27 SW-G review-scoring increment.** The frozen fixture now covers the
six required categories: create, improve, ambiguous scope, existing-skill reuse,
malicious resource, and missing dependency. Added a review-template command
that is blinded to the condition key and a separate scorer that binds human
ratings to the exact review-file digest, requires all 24 outputs and 12 paired
trials, checks the 10/12 candidate threshold, baseline non-regression, and
security-critical rubric outcomes, and reports per-condition calls, latency,
reserved spend, and actual cost. Missing route, latency, or cost metrics cannot
pass acceptance. Private files are mode 0600 under mode 0700 directories.
The evaluator/routing/execution/ledger suite passes **84 tests** and targeted
Ruff checks pass. The full suite passes **3,371 tests, 4 skipped, and 2
subtests**, with 11 warnings; no provider calls were made.
SW-G itself remains open until the gated 24-trial run is reviewed by a human.

**2026-09-27 evaluator whole-batch budget preflight (SW5 partial).** Before
the first model call, the runner now checks that the complete paired batch fits
the total-call limit, per-trial limits, token bounds, known-price requirement,
and paid-route spend ceiling. A regression test proves an over-ceiling batch
fails with zero executor calls and zero reservations. Pricing-estimator
exceptions also fail closed during preflight and reservation. The focused
evaluator and review suite passes **25 tests**; targeted Ruff checks pass. Full
repository Python verification passes **3,373 tests, 4 skipped, 2 subtests**,
with 11 warnings. This closes the code-level whole-batch preflight item only;
no live provider calls were made, and SW-G plus all other release gates remain
open.

**2026-09-27 native workspace regression verification.** Current MortimerHost
and JarvisKit suites pass: `swift test --package-path macos/MortimerHost`
reports **286 tests, 6 skipped, 0 failures**; `swift test --package-path
macos/JarvisKit` reports **206 tests, 0 failures**. Skills rendering, Activity
copy, voice action and API bounds tests pass. Skips include physical-display
checks requiring multiple connected displays and on-screen tests requiring an
interactive foreground-capable WindowServer. Those remain acceptance work; the
native suite does not establish VoiceOver or target-Mac user acceptance.

**2026-09-27 Skills accessibility implementation increment (SW3 partial).**
The Skills workspace now marks the selected library row as selected for
accessibility, adds visible “Selected” text when the system requests color-
independent differentiation, strengthens the selected outline, and uses
near-opaque surfaces when Reduce Transparency is enabled. The selected process
step and activity rows follow the same preferences. The rebuilt focused native
Skills suite passes **9 tests**; actual system-setting, VoiceOver, keyboard,
contrast, and large-text acceptance remain open.

**2026-09-27 authoring cancellation-race increment (SW4/SW-H partial).** Added
regression coverage for cancellation arriving while sandbox startup is in flight
and for a late positive validation receipt after cancellation. The first case
proves creator execution never starts; the second proves the durable job stays
cancelled and discards the candidate digest even when the creator returns
success and the sandbox reports `validated`. Request, authoring service,
validation, and policy suites pass **53 tests**. These fake-service tests do
not close real-VM cancellation, restart/reconnect, or publisher-reconciliation
acceptance.

**2026-09-27 authoring cancellation confirmation and worker-race increment (SW4/SW-H partial).** Worker transitions now check the durable cancellation flag under the request-file lock before recording validation success or failure. Draft startup, final receipts, and exception paths preserve a winning cancel request; offline validation resolves its parent sandbox run and is marked cancelled only after that exact run reports `phase=cancelled`. Restart reconciliation covers test requests, and a late offline receipt cannot restore a candidate revision after cancellation. The focused request suite passes **18 tests**; request/authoring/service/validation/policy suites pass **56 tests**. Full Python suite passes **3,378 tests, 4 skipped, 2 subtests**, with 11 warnings. Ruff `F`/`I` and `git diff --check` pass on the touched implementation and tests. This is fake-service and repository evidence; real-VM lifecycle, restart/reconnect under a live VM, and publisher reconciliation remain open.

**2026-09-27 parallel SW0/SW2/SW3 local increments.** SW0 now has strict
versioned schemas for catalog, detail, creator-request, and activity-event
fixtures, plus consistency checks for package revisions, event identity/order,
step references, and forbidden catalog fields. SW2 activity reads bind to the
authenticated bearer identity and fail closed when that identity is absent;
with auth explicitly disabled they retain the configured local tenant. A
conflicting process-tenant/token-owner regression covers both run and event
reads. SW3 process steps expose both selected accessibility state and their
expanded/collapsed value, with rendered-tree assertions at wide and narrow
widths. Combined relevant Python regressions pass **159 tests**; focused Skills
workspace native regressions pass **9 tests**. No live VoiceOver or Mac
acceptance is claimed.

**2026-09-27 weighted implementation progress baseline.** Added a weighted
score to distinguish implementation progress from final acceptance. Weights
reflect relative scope/risk across seven workstreams; each score uses the same
0/25/50/75/100 evidence anchors, with intermediate estimates allowed, and is
capped below complete while its listed implementation or acceptance work
remains open. SW0–SW6 weights are 10/15/15/15/20/15/10%; workstream scores are
70/75/75/75/80/75/60%. The weighted score is **74% implementation complete**.
This is a
working-tree estimate, not a release-readiness or deployment percentage. All
SW-A–SW-L acceptance gates remain open. The latest cancellation changes have
18 focused request tests, 56 adjacent authoring/request tests, and 159 combined
Python regression tests across the active parallel lanes. The refreshed full
Python suite passes **3,382 tests, 4 skipped, 2 subtests**, with 11 warnings.
Real-VM lifecycle, live provider comparison, activation/rollback, accessibility,
voice/display, and Mac release acceptance remain unverified. Recalculate this
score whenever the status ledger changes; do not mark a stream complete from
code presence alone.

**2026-09-27 parallel implementation tranche.** SW0 strict fixture contracts
now validate catalog, detail, creator-request, and activity-event shapes and
cross-fixture consistency. SW2 activity reads enforce authenticated-owner
scoping; protected markers make mixed legacy traces private for the whole run,
with a regression proving ordinary stale rows cannot leak. SW3 exposes selected
and expanded process-step state to accessibility, and its Activity stream
filters wrong-run events, de-duplicates by event ID, and restores strict
sequence order when pages overlap or arrive out of order. SW4 offline-validation
restart recovery resumes only durably queued requests; interrupted tests
reconcile only against the same sandbox run and a fresh receipt, while ambiguous
cases become `needs_reconciliation` without replaying validation or claiming
success. Exact-run cancellation behavior remains covered.

The combined focused Python regressions pass **99 tests**; the focused native
Skills workspace suite passes **12 tests**; Ruff and `git diff --check` pass.
Individual SW-H request tests pass **21**. These are local test results, not
live VM, trusted production-step, VoiceOver, display, or release acceptance.
The full Python suite passes **3,387 tests, 4 skipped, 2 subtests**, with 11
warnings.

The weighted implementation estimate is now **78%** with the unchanged
SW0–SW6 weights of 10/15/15/15/20/15/10% and scores of 80/75/82/82/84/75/60%.
The score reflects strict fixture and privacy hardening, authenticated API
ownership, accessibility and event-order behavior, and restart reconciliation.
SW-A–SW-L and all target-environment/provider acceptance gates remain open;
this is not a deployment or release-readiness percentage.

**2026-09-27 privacy diagnostics and native regression increment.** Run-log
write failures now log only the exception type, never raw exception text; a
`PRIVATE_SKILL_TRACE_CANARY` regression proves the diagnostic sink stays clean.
The JarvisClient test initializer accepts an injected token provider, so unit
tests validate connect-time token refresh without writing/deleting credentials
in the real OS Keychain. AudioEngineIO now initializes its AVAudioPlayerNode
only when an engine starts, keeping an unused audio path inert in headless
contexts. Run-log/activity API tests pass **44**, Ruff passes, and the full
Python suite passes **3,387 tests, 4 skipped, 2 subtests**, with 11 warnings.
Full JarvisKit passes **206 tests, 0 failures**; full MortimerHost passes **290
tests, 7 skipped, 0 failures**. A compact layout fixture under SwiftUI's
largest accessibility-size environment verifies that process-step labels and
details remain present in the accessibility tree; rendered output does not
prove that macOS system text-size controls enlarge every custom view. The
MortimerHost skips still cover physical displays, foreground-window control,
and a frame-time measurement unavailable on this host. No target-Mac visual,
VoiceOver, or physical-display acceptance is claimed.

**2026-09-27 SW6 selector fixture rerun.** Re-ran the public provider-free
selector corpus against the current package pins and saved the new receipt at
`receipts/skill-selection-fixtures-2026-09-27-rerun.json`. All **14/14** cases
passed: five positive selections, five no-skill cases, and four overlap cases;
provider calls: **0**. This revalidates deterministic selection only; it does
not enable v2 routing or satisfy target-Mac performance and rollout gates.

**2026-09-27 SW-K selector performance rerun.** On the available Apple M5
macOS host, the runtime selector was measured on 100 fixed synthetic skills
for 100 unique-trigger and 100 no-skill queries. p95 was **4.46 ms** and
**4.43 ms**, respectively, below the 20 ms selector budget; provider calls:
**0**. Receipt: `receipts/skill-selection-performance-2026-09-27-rerun.json`.
This measures selector runtime only. Cached UI navigation, voice p95 under the
same workload, and ten-minute memory stability remain unmeasured.

**2026-09-27 parallel SW0/SW1/SW2/SW5 increment.** Added fail-closed CLI
regressions for malformed schema-v2 registries while runtime enforcement is
off, including missing pins, extra pins, and unknown fields. SW5 paired
evaluation now randomizes which condition runs first for each fixture and
repetition while retaining exact pairing and private condition labels. SW2
adds a service-bot-authenticated, bounded, in-memory runtime inventory receipt
from the live voice `SkillRegistry`; it reports discovered tool names only,
expires after 45 seconds, and leaves missing/stale/incomplete evidence
unknown. It does not attest successful tool execution, provider/credential
validity, route/privacy compatibility, package loading, or sandbox readiness.
The bot reports every 10 seconds on a best-effort basis and sends an inactive
receipt at shutdown. The receipt contract is documented in
`RUNTIME_INVENTORY_CONTRACT.md`.

Verification: CLI tests **5 passed**; evaluator budget/review tests **26
passed**; runtime inventory/readiness/auth tests **23 passed**. Ruff `F`/`I`
checks on the changed local code and `git diff --check` pass. No provider calls
were made. The combined whole-repository Python suite passes **3,401 tests, 4
skipped, 2 subtests**, with 11 warnings. This is local test evidence; live
voice-session readiness and target-Mac behavior remain unverified.

The weighted implementation estimate at this checkpoint is **80%** (SW0–SW6 weights
10/15/15/15/20/15/10%; scores 83/77/86/82/84/78/60%). The increase reflects
the additional fail-closed CLI contract, authenticated runtime evidence path,
and reduced paired-evaluation order bias. SW-A–SW-L and target-environment
acceptance gates remain open; this is not a release or deployment percentage.

**2026-09-27 parallel SW2/SW3/SW4 increment.** Added SW2 pagination regression
coverage for gap-free event sequences across pages, stable cursor retries, and
task/response-content exclusion. SW3 now has a separate compact-layout test
confirming that a process step still exposes its expanded accessibility state
at the largest supported text size; this complements the existing accessible
label checks and does not establish live VoiceOver behavior. SW4 publisher
recovery now requires the published sandbox receipt to match the durable
request's run ID, candidate digest, and package revision. A mismatched receipt
is kept in `publication_needs_reconciliation` and cannot surface a PR URL.
Fake-service tests cover the mismatch and restart path; no live VM or publisher
was contacted.

The SW2 cursor/activity tests pass **29 tests** together with runtime inventory,
catalog, and auth coverage. The SW4 request/authoring recovery group passes
**49 tests**. The focused native accessibility-state test passes **1 test**.
The final whole-repository Python suite passes **3,405 tests, 4 skipped, and 2
subtests**, with 11 warnings. Ruff `F`/`I` and `git diff --check` pass.

The weighted implementation estimate is now **81%** (same SW0–SW6 weights;
scores 83/77/89/83/86/78/60%). SW-A–SW-L remain open. Real-VM lifecycle,
provider comparison and human review, live voice/VoiceOver, physical-display,
activation/rollback, and Mac release acceptance remain external gates.

**2026-09-27 SW3 catalog completeness increment.** The native Skills view had
been loading only the first 50 catalog items, while the app-owned store retained
only 32 IDs, making later cards unreachable by pointer. `AdminAPI` now follows
the versioned cursor until completion, validates page schema/revision/cursor
progression and unique skill IDs, and refuses to return a partial catalog on
malformed or changing pages. The workspace replaces its cards atomically only
after all pages load. `SkillsStore` keeps the full ID membership needed for
pointer selection while publishing only its existing bounded 32-item shared
voice/action inventory.

Tests cover 61 catalog entries over three pages, repeated cursors, changing
revisions, duplicate IDs, and pointer selection past both prior caps. Full
JarvisKit passes **210 tests**; full MortimerHost passes **292 tests, 6
skipped, 0 failures**. The skips include physical-display/foreground-only
checks. The system currently reports only the built-in Apple M5 display, so
physical second-display acceptance remains unavailable. Synthetic catalog
coverage does not establish live Mac usability or VoiceOver acceptance.

The weighted implementation estimate is **82%** (rounded; SW0–SW6 weights
10/15/15/15/20/15/10%; scores 83/78/90/89/88/79/61%, weighted total 82.40%).
SW2 now rejects unsupported successful step claims; trusted receipt production
remains open. SW3 now includes a read-only Versions panel and synthetic
accessibility/rendering coverage. Remaining SW3 gates are live
VoiceOver/keyboard/voice review, display movement, and physical-monitor
behavior. SW-A–SW-L remain open.

**2026-09-27 parallel continuation — version visibility and trusted step status.**
The Versions tab now shows the current manifest version, package revision,
enabled registry pin and match state, and owner-scoped candidate request
evidence. The API intentionally does not invent a previous installed revision,
Git history, activation, or rollback state. Versions API/auth tests pass **36
tests**; synthetic native Skills rendering passes **8 tests**. Generic and
internal run-log writers now reject `skill_step_finished: passed` because the
runtime has no typed validator/controller receipt contract. Successful tool
activity remains `unknown`; focused run-log/cursor tests pass **41 tests**.
Actual trusted pass emission remains open until such a receipt contract exists.
Final integrated verification passes whole-repository Python **3,409 tests, 4
skipped, 2 subtests**, JarvisKit **210 tests**, and MortimerHost **293 tests, 6
skipped, 0 failures**. The combined API/auth/run-log suite passes **78 tests**;
the full synthetic Skills rendering suite passes **9 tests**. Ruff F checks and
`git diff --check` pass. The earlier whole-suite D17 source-inspection failure
did not recur in the final run. Architecture, Repo Map, and Skills README now
describe the Versions evidence and trusted-step boundary; Repo Map remains
within its 8,000-character prompt cap. Physical Mac, voice, VoiceOver,
multi-display, real-VM, live provider, human evaluation, activation/rollback,
and release gates remain open.

**2026-09-27 activation/rollback API gate.** Activation requests now fail with
HTTP 409 until accepted live evaluation and blinded human-review evidence can
be bound to the exact revision; offline package validation alone is insufficient.
Rollback requests fail until a previously accepted package and registry revision
is recorded. Neither refusal writes a request receipt. The focused request and
catalog suite passes **29 tests**; `test_repo_map.py` passes **7 tests**. Ruff F
checks and `git diff --check` pass. This leaves both actions unavailable through
the API until their evidence sources exist; no activation or rollback occurred.

**2026-09-27 parallel implementation increment.** SW1 registry loading now
rejects duplicate YAML keys, preventing ambiguous schema-v2 package pins from
passing `--validate`; focused CLI and parser suites pass **71 tests**. SW3 uses
single-pane navigation at accessibility Dynamic Type sizes even on a wide
display; its presentation-policy suite passes **6 tests**. SW4 publisher
reconciliation accepts only the exact open draft PR matching repository, base,
branch, and commit; sandbox publisher/session suites pass **20 tests and 6
subtests**. The full Python suite passes **3,410 tests, 4 skipped, 2 subtests**.
The integrated native host suite passes **294 tests, 6 skipped, 0 failures**
after the accessibility change. An independent SW2 runtime and
privacy audit found existing bounded inventory, authentication, expiry,
shutdown, and sensitive-trace protections sufficient for this increment and
made no code changes. These are local implementation checks, not target-Mac,
VoiceOver, physical-display, real-VM, live-provider, or maintainer acceptance.

**2026-09-27 SW5/SW6 evidence increment.** The blinded evaluation artifact now
binds the private condition key and usage metrics by canonical SHA-256; the
scorer rejects altered or detached files before applying human scores. This is
tamper-evident linkage, not signer identity or proof that ratings are
independent. Focused evaluation/review tests pass **28 tests**; no provider was
called. Native detail navigation now caches immutable package detail in a
32-entry process-local LRU keyed by skill ID and exact revision. Catalog changes
evict stale entries, and identity/revision mismatches and failed loads are
rejected before display or caching. Focused cache tests pass **7 tests**. A
100-sample warm resolver run measured p95 **0.0028 ms** in the focused run and
**0.0072 ms** during the full rendering suite; these samples measure JSON detail
resolution only, not SwiftUI transition or network time. The
updated full Python suite passes **3,412 tests, 4 skipped, 2 subtests**; the
full MortimerHost suite passes **300 tests, 6 skipped, 0 failures**. JarvisKit
remains at **210 passing tests** from the preceding verified run. Actual
navigation p95, selection overhead, paired voice latency, ten-minute memory
growth, live evaluation, independent human ratings, and all target-Mac/VM/release
gates remain open.

**2026-09-27 parallel implementation increment — SW1/SW3.** SW1 now reparses
the selected skill after matching and binds the prompt to that fresh package
snapshot. If the package changes between matching and validation, the stale
candidate is refused instead of injecting cached instructions under a newer
digest. A deterministic race test confirms neither version is injected;
SubAgent, agent-skills, and selector suites pass **151 tests** with Ruff checks.
SW3 now transfers selected skill detail to the existing supporting-display
stage as one supplemental tile, suppresses the duplicate main detail while
transferred, and returns it to the main Skills workspace. On a single display,
the detail stays inline. Loading, success, and failure transitions for catalog,
detail, activity, versions, and example preview now have short privacy-safe,
duplicate-suppressed accessibility announcements without moving focus. Two
accessibility status tests pass. The new/affected Swift files pass frontend
parse and `git diff --check`. The first SwiftPM invocation was blocked before
manifest validation by `sandbox-exec: sandbox_apply: Operation not permitted`;
rerunning with the existing package checkout, `--disable-sandbox`, and a
temporary Clang module cache allowed test execution. A missing
`DisplayWindowStore`/`DrawerState` injection in Skills rendering fixtures and
missing `SkillsStore` injection in supporting-display fixtures were corrected.
The integrated Skills workspace suite passes **19 tests**, ContentPanel tests
pass **18 tests**, and SupportingDisplay tests pass **2 tests with 2 skipped**
because two displays are not connected. The full MortimerHost suite passes
**304 tests, 7 skipped, 0 failures**. The full Python suite passes **3,417
tests, 4 skipped, 11 warnings, and 2 subtests**; focused SW1 suites pass **151
tests**, Ruff `F` checks and `git diff --check` pass. VoiceOver speech timing,
keyboard traversal, live voice/mic
interaction, physical display movement/reconnect, and real Mac acceptance remain
open. SW1 target-host runtime readiness also remains open.

The weighted implementation estimate is **83%** (SW0–SW6 weights
10/15/15/15/20/15/10%; refreshed workstream scores 83/79/90/89/88/79/61%,
weighted total 82.55%, rounded). This small increase reflects code and focused
regression progress in SW1/SW3; it does not close SW-A–SW-L or any live, target
Mac, physical display, VM, provider, human-review, activation, rollback, or
release gate.

**2026-09-27 SW0/SW5 parallel verification.** SW0 fixture checks now bind
catalog/detail identities and revisions, parse creator requests through the
actual API validator, enforce process graph identity/order/acyclicity, and
reject activity events that claim unsupported trusted success. Focused fixture
tests pass **13 tests** and adjacent catalog/request/event/selection/CLI tests
pass **66 tests**. SW5 now pins the approved `skill-creator-v1` fixture digest
before route resolution; the runner supplies no tools, requires empty typed
tool-call evidence, and records zero calls. Scoring labels the two safety case
ratings as human-reviewed (`reviewed_safety_rubric_pass`) and checks zero tool
execution deterministically (`no_tool_execution`); both are required.
Evaluation/review tests pass **33 tests**; combined fixture/evaluation tests
pass **46 tests**. Independent review found no false-pass in the intended
runner path. It did identify an assurance limit: artifact digests are unkeyed,
so an actor able to rewrite all owner-only JSON files can recompute them. Before
formal scoring, either trust the original private outputs under reviewer
procedure or require signed/append-only runner provenance if post-run tampering
is in scope. No provider calls occurred.

The integrated Python suite now passes **3,429 tests, 4 skipped, 11 warnings,
and 2 subtests**. Targeted Ruff F/I checks and `git diff --check` pass. The
weighted implementation estimate is **83%**; using revised workstream scores
SW0–SW6 of 84/79/90/89/89/80/62% at weights 10/15/15/15/20/15/10%, the total
is 83.1%. This estimate covers implementation progress only.
SW0 visual/voice/display baseline; SW1 target-runtime readiness; SW2 trusted
controller receipts/live readiness; SW3 VoiceOver/live voice/physical-display
acceptance; SW4 real-VM lifecycle; SW5 gated live trials, independent ratings,
artifact review, activation/rollback; and SW6 target-Mac performance/route and
release acceptance remain open. Runtime enforcement remains off.

**SW2/SW3 parallel audit outcome.** SW2 remains fail-closed: generic tool
success and model narration cannot emit `passed`, and missing evidence remains
`unknown`. Tool-backed step start/finish events now share the same opaque
`tool_call_id` as `attempt_id`, distinguishing repeated calls to one intended
step. The SubAgent/runlog regression suite passes **115 tests**. The plan now makes the
missing host-owned `SkillStepCheckReceipt` contract explicit: issuer, run and
request, exact skill revision, step and attempt, required check IDs/outcomes,
host-owned check mapping, and replay/expiry/idempotency semantics must be
specified before trusted success can be built. SW3's focused native Skills
workspace suite passes **19 tests**; no source change was justified without
interactive target-Mac acceptance. VoiceOver/speech timing, Full Keyboard
Access traversal and action parity, live spoken navigation, accessibility
settings, and supporting-display transfer/reconnect/disconnect checks still
require the frozen app on the target Mac.

SW4 then closed a local publisher-recovery gap: an already-published PR is
reconciled only when its receipt matches the exact parent draft run, reviewed
candidate digest, package revision, and nonempty PR URL. A mismatch remains
`publication_needs_reconciliation`, and a matching recovered publication is
not submitted twice. The focused request suite passes **30 tests**; Ruff F/I
and `git diff --check` pass. This does not replace real-VM lifecycle,
restart/cancellation/reconnect, live publisher, or maintainer-review checks.

**SW1/SW6 parallel continuation.** SW1 audit found no additional local
fail-closed gap; the strict v2 registry, duplicate YAML-key rejection, exact
pin checks, and opt-in feature flags are covered by **93 focused tests**.
Target-Mac package/runtime readiness, route/tool receipts, selector latency and
memory budgets, and pin-change refresh behavior remain unverified; flags stay
off. SW6 now refuses a candidate snapshot containing duplicate skill IDs
before scoring, eliminating input-order-dependent package choice. A regression
tests both input orders; selector plus fixture tests pass **25 tests** with
Ruff F and `git diff --check` clean. Target-Mac performance and release gates
remain open. A fresh [SW1 CLI validation receipt](receipts/sw1-loader-cli-20260927.json)
records schema-v2 validation success on macOS 27.0 arm64: five enabled packages
have matching pins, and `skill-creator` remains inert. Runtime digest enforcement
is reported off. `system_profiler` currently sees only the built-in Apple M5
display; process enumeration could not be verified because `sysmond` is
unavailable to this shell. This is not app-runtime, multi-display, or release
acceptance.

The full native package suites have now been rerun on this macOS 27.0 arm64
host: MortimerHost **304 tests, 7 skipped, 0 failures**; JarvisKit **210 tests,
0 failures**. The [native regression receipt](receipts/native-suites-20260927.json)
binds the package source/test tree digests and records local diagnostics:
500-node synthetic graph layout took 1.165 s (layout timing, not frame time),
and the 100-sample skill detail resolver p95 was 0.0082 ms (resolver only,
without SwiftUI/network). Native orb frame-time fixtures also ran. These are
useful local measurements, but no end-to-end navigation latency or ten-minute
memory-growth gate was measured; physical-display, interactive accessibility,
voice, VM, provider, and release acceptance remain open.

**2026-09-28 provenance and gate-audit continuation.** A deterministic
worktree candidate fingerprint tool is implemented and covered by **4 focused
tests**; acceptance receipts are excluded from its digest to prevent
self-reference. The release-config app bundle embeds the candidate fingerprint
and full source revision, is ad-hoc signed, and passes strict deep signature
verification. Its receipt is
[`mortimerhost-app-bundle-20260928.json`](receipts/mortimerhost-app-bundle-20260928.json).
The bundle was not launched, installed, or deployed. The release compiler was
run with debug-info generation disabled because the sandbox denies dSYM
creation. The evaluator and blinded review/scoring machinery are implemented,
but no `skill_evaluation` route is configured and no live trials or human
ratings were performed. SW-B package-integrity acceptance was closed in a
separate evidence-backed increment; SW-A and SW-C–SW-L remain open. See the
implementation plan for the independent release/evaluation audit and exact
remaining external gates.

**2026-09-28 SW2 receipt-contract increment.** Added a strict v1
`SkillStepCheckReceipt` schema with process-local HMAC authentication, exact
identity binding, a two-minute issue/expiry window, exact required-check
matching, and host-code-owned check dispatch. The checked-in host-check
registry and revision/step map are intentionally empty; no pass can be issued
until independently verifiable check functions and reviewed exact mappings
exist. `RunLogger` accepts a receipt only for its active owned run after the
same skill revision was selected and the exact attempt was recorded as
started. Receipt IDs and attempts are persisted atomically with the `passed`
event; identical replay is idempotent, conflicting/reused attempts are
rejected, and protected-run transition/retention pruning removes the receipt
metadata. The generic model/tool event path still cannot report `passed`.
Focused receipt/runlog/API/subagent suites pass **139 tests**. The full Python
suite passes **3,450 tests, 4 skipped, 11 warnings, and 2 subtests**. SW2 stays
in progress: host check functions/mappings, live runtime readiness, and the
remaining SW-A and SW-C–SW-L acceptance gates are still open.

The current weighted implementation estimate is **83.6%**, using SW0–SW6
weights 10/15/15/15/20/15/10% and revised scores 84/79/93/89/89/80/62%.
This reflects the implemented receipt validator/persistence contract while
keeping SW2 below complete because the host checker registry/map and target
readiness are still open. It is not a release or deployment percentage.

**2026-09-28 SW-B package-integrity acceptance closed.** The scoped package,
loader, and reference-resource regressions pass **89 tests**. They cover full
instruction bodies with embedded separator lines, invalid and duplicate
manifest metadata, the 128-file/10-MiB/128-KiB package limits, traversal and
symlink refusal, digest drift, stale/disabled/undeclared reference reads, and
the registration gate for on-disk packages. The actual candidate CLI reports
all six package directories valid, exactly five enabled skills with matching
pins, and `skill-creator` inert. Runtime digest enforcement remains off. The
receipt is [`sw-b-package-integrity-20260928.json`](receipts/sw-b-package-integrity-20260928.json).
The complete candidate Python suite passes **3,450 tests, 4 skipped, 11
warnings, and 2 subtests**. This closes only SW-B; SW-A and SW-C–SW-L remain
open.

**2026-09-28 parallel SW-A/SW-C/SW-D/SW-E/SW-H/SW-I hardening.** The
evaluator core now requires the approved frozen fixture ID and digest, reloads
and validates the fixture, and compares every supplied case before making any
provider call. This closes a bypass where non-CLI callers could send arbitrary
or protected prompts under the public evaluation policy. Evaluator/model-route
tests pass **42**, broader privacy-boundary tests pass **90**, and the full
Python suite passes **3,453 passed, 4 skipped, 11 warnings, and 2 subtests**.
Local evaluator privacy is hardened; SW-E source-to-sink verification across
the live app, screenshots, exports and supporting display remains open.

The durable request store now atomically claims queued draft and offline
validation work under its per-request lock before worker startup, preventing
duplicate starts across host processes. The focused request/authoring/service/
validation/policy suites pass **70 tests**; live VM restart, cancellation,
reconnect and publisher-reconciliation acceptance remain open (SW-H).

Native activity copy now distinguishes tool-call failure, observed return and
unknown step outcome. The Next-step VoiceOver hint accurately describes open-
and-scroll behavior. The focused native Skills rendering suite passes
**10 tests**; the full MortimerHost suite passes **304 tests, 7 skipped, and 0
failures**. This is synthetic/native regression evidence only; VoiceOver,
keyboard, visual, live voice and physical-display acceptance remain open
(SW-D/SW-I/SW3).

The selector audit reran **100 focused tests** and all **14/14** provider-free
fixture decisions with zero provider calls. A candidate-bound receipt now
records explicit-selection refusal, capability/privacy/readiness checks,
kill-switch behavior, compatibility, the two-skill limit, and the fixed
16,000-character ceiling. This closes only SW-C's deterministic
selection-quality criteria; SW6 target performance/live route readiness,
activation, rollback, and release remain separate. The SW-A audit found local
coverage for the five enabled skill IDs (72 tests passed), but no verified
baseline screenshots or voice/display recordings; the orb, sidecar, Atlas,
response sharing and developer aggregation still need live parity review.
**SW-B and SW-C are the only accepted SW-A–SW-L gates.** Weighted
implementation estimate remains **83.6%**; no release, live provider, physical
display, VoiceOver, VM or human-review gate is being represented as complete.


**2026-09-28 parallel implementation continuation (SW1/SW2/SW3/SW4/SW5/SW6).**
Runtime readiness now fails closed if more than eight MCP reporters are live in
one freshness window; a fresh inventory can recover the state. Focused
readiness/runtime/selector/catalog API tests pass **39**. SW4 rejects attempts
to self-edit the reserved `skill-creator` package before durable request
reservation or sandbox allocation, with a second service-boundary guard; the
queued draft/offline-validation atomic-claim fix is retained. Focused authoring,
validation and request suites pass **73**. These local checks do not prove real
VM isolation, restart, cancellation, or publication reconciliation.

SW5's blinded-evidence writer now requires private owner-only directories even
when called directly as a library; public output directories fail before any
artifact is written. Core evaluation independently verifies frozen public
fixture ID/digest and exact case equality before provider invocation. Focused
review/artifact tests pass **35**, evaluator/model-route tests pass **42**, and
no provider calls have been made. Route configuration, 24 live trials, blind
human scoring, activation, and rollback remain open.

SW3 now preserves single-tile aggregation when a developer result tile is
pinned. A full native build and test run passes **305 tests, 7 skipped, 0
failures**. Physical display cases are among the skips; live spoken interaction,
VoiceOver/keyboard, visual, and display behavior remain open.

A fresh 100-sample-per-case selector benchmark on macOS 27 arm64 measures
**4.485 ms p95** for unique-trigger hits and **4.467 ms p95** for no-skill
queries against the 20 ms budget, with zero provider calls. Receipt:
[`skill-selection-performance-2026-09-28.json`](receipts/skill-selection-performance-2026-09-28.json).
This covers selector time only; cached SwiftUI navigation, voice latency under
the same workload, and ten-minute process-memory stability remain open.

The latest full Python suite passes **3,458 passed, 4 skipped, 11 warnings, and
2 subtests**. The weighted implementation estimate is **84.4%**, using SW0–SW6
scores **84/80/93/90/90/81/64%** and unchanged weights
**10/15/15/15/20/15/10%**. It uses the plan’s 0/25/50/75/100 evidence anchors
with intermediate estimates; it is not release readiness. SW-B and SW-C
remain the only accepted SW-A–SW-L gates. The release bundle is a test
candidate and has not been launched, installed, or deployed.

## 2026-09-28 parallel local hardening follow-on

Five isolated lanes added or verified code-level progress for SW-D, SW-E, SW-H,
SW-I and SW-K:

- SW-H binds a reviewed draft receipt to one publish request ID, canonical
  payload digest and exact candidate/revision under a cross-process lock.
  Distinct request IDs for one candidate cannot create competing publish jobs;
  queued-to-publishing is claimed atomically. No GitHub operation was invoked.
- SW-E filters protected result titles and IDs (including active/comparison
  identities) from both supervisor inventory formats, rejects transfer of
  protected local results, hides them from the supporting-display menu, and
  blocks clipboard/export at the coordinator before the text reaches a writer.
  Canary tests cover these sinks; complete privacy acceptance remains open.
- SW-I improves large-text layout, accessibility values, detail-tab navigation
  and Reduce Transparency surfaces. Live VoiceOver traversal and manual system
  setting checks remain open.
- SW-D now explains an empty run trace as unknown/not completed and removes copy
  implying legacy runs appear in the traced-run list. Duplicate/out-of-order
  events, failure and unknown outcomes remain covered by deterministic tests;
  live reconnect and legacy-run UI verification remain open.
- SW-K adds 100-sample selection and cached store-navigation measurements using
  the public 100-skill fixture: latest integrated p95 **0.0021 ms** and
  **0.0214 ms**. This does
  not measure SwiftUI rendering, voice latency or process memory over time.

Final integrated verification after the clipboard/file-write guards: Python
**3,459 passed, 4 skipped, 11 warnings, 2 subtests**; MortimerHost **310 passed, 7 skipped, 0
failures**. The clipboard guard's focused `ShareCoordinatorTests` also pass
(**5 passed, 0 failures**). Focused
publication/request suites **79 passed**; `git diff --check` passes. Updated
weighted implementation estimate: **85.3%**, with unchanged weights
10/15/15/15/20/15/10% and scores SW0–SW6 **84/80/93/91/91/83/66%**. Only
SW-B and SW-C are accepted SW-A–SW-L gates. Real-VM lifecycle, provider
comparison and human review, full source-to-sink privacy, live VoiceOver and
system-setting checks, physical displays, rendered navigation/voice/memory
measurements, activation/rollback, and release acceptance remain open. The
older app-bundle/release-build receipt is bound to the earlier worktree
fingerprint; it must not be treated as current candidate evidence and should be
recreated only after the acceptance candidate is frozen.

## 2026-09-28 parallel remaining-gate follow-on

Independent SW-A/SW-E/SW-H/SW-K reviews and targeted SW-E/SW-H fixes ran in
parallel. SW-E now rejects protected `.window` results in `AppMessageRouter`
before either supporting-display store sees them, while retaining the result
in the main workspace. A regression test exercises the encoded app-message
route end to end. Focused native coverage passed **19 tests**; the full native
suite passed **311 tests, 7 skipped, 0 failures**. SW-E remains open: argv
canaries and an automated-screenshot protected-content scan are not yet proven.

SW-H now uses an atomic pre-submit barrier: cancellation that wins before the
barrier prevents publication, while cancellation after submit begins fails
closed and leaves the external outcome for reconciliation. Queued publish
requests left between reservation and worker claim can resume after restart,
with parent/candidate/payload bindings revalidated. Focused lifecycle coverage
passed **41 tests**. SW-H remains open for real-VM restart/reconnect, external
publisher reconciliation and accepted-evidence-gated activation/rollback.

SW-A remains open because its required baseline-versus-candidate interaction
matrix is not recorded. SW-K remains open because rendered navigation, paired
voice-latency regression and ten-minute memory growth on the target Mac are
not measured. The refreshed 100-sample selector run measured **4.418 ms p95**
for a unique-trigger hit and **4.408 ms p95** for no-skill; both are below the
20 ms selector budget and used zero provider calls. The current candidate-bound
SW-B, SW-C and selector-performance receipts are refreshed to the final
worktree fingerprint recorded in those receipts.

Final integrated validation after the parallel fixes: Python **3,463 passed,
4 skipped, 11 warnings, 2 subtests**; MortimerHost **311 passed, 7 skipped,
0 failures**; focused SW-H lifecycle tests **41 passed**; focused SW-E route
tests **19 passed**; and `git diff --check` passes. This evidence does not
authorize a release or deployment. The previous weighted implementation
estimate of **85.3%** is a prior checkpoint and was not recalculated in this
pass; all external and target-runtime acceptance gates remain open except
SW-B and SW-C.

## 2026-09-28 parallel implementation follow-on

Further parallel work closed several local defects without closing their
broader acceptance gates:

- **SW-D:** Activity refresh now keeps the last valid trace on transient
  failure, offers a retry, retries failed older-page loads, clears a trace as
  soon as run selection changes, and ignores stale/cancelled responses. Focused
  activity rendering tests passed **6/6**. Live reconnect, legacy-run and
  VoiceOver checks remain open.
- **SW-E:** Added argv canaries for protected request refusal, subscription
  prompts sent on stdin, and the Tart task-goal argument boundary. The focused
  boundary suite passed **105 tests, 7 subtests**. A screenshot-sink audit found
  native automated PNGs are rendered from synthetic fixtures; no live screen
  capture is used by those test writers. `ProtectedDisplayContentTests` now
  writes a protected-view PNG to a temporary file, decodes it, and compares its
  pixels with the body-only protected view; plaintext marker checks also run
  against the written bytes. The focused protected-display suite passes
  **3 tests**. This proves the protected renderer-to-PNG path for synthetic
  payloads; the focused evidence is in
  `receipts/sw-e-protected-png-20260928.json`. Broader app-flow privacy
  acceptance remains open.
- **SW-F:** The ordinary self-edit deny policy now explicitly blocks
  `tests/fixtures/skills_authoring/**`, preventing the broad `tests/**` allow
  from authorizing creator fixture edits outside the scoped sandbox. The
  focused policy/authoring/sandbox suite passed **203 tests, 11 subtests**.
  Softnet/Tart only document IPv4 CIDR blocking; no supported `::/0` rule or
  authoritative IPv6-frame drop guarantee was found. Keep IPv6 containment
  open until an independent deny control or NIC-less offline VM is implemented
  and verified on the frozen candidate. See the pinned
  [Softnet rule model](https://github.com/openai/softnet/blob/0.23.0/lib/proxy/rule.rs)
  and [Tart 2.37.0 run options](https://github.com/cirruslabs/tart/blob/2.37.0/Sources/tart/Commands/Run.swift).
- **SW-G:** Local evaluator output now requires the approved fixture bytes,
  exact six-case/two-repetition/two-condition trial set, all 12 complete pairs,
  and exact frozen criteria. Oversized output stops the current batch before
  another trial is spent; missing usage tokens make metrics incomplete. The
  focused evaluator/model/ledger suite passed **99 tests**. Live trials,
  approved route/privacy prerequisites, blinded human scoring and maintainer
  review remain open.
- **SW-I:** Native Swift limits now count Unicode scalars like Python limits,
  closing a decomposed-character bypass; stale and unavailable voice targets
  return distinct actionable outcomes. Focused coverage passed **10 Python
  protocol** and **28 native coordinator/registry** tests. Live speech,
  VoiceOver and system accessibility checks remain open.

Current full-suite validation: Python **3,468 passed, 4 skipped, 11 warnings,
2 subtests**; MortimerHost **314 passed, 6 skipped, 0 failures**; JarvisKit
**210 passed, 0 failures**. `git diff --check` passes. A standalone 100-sample
store test measured **0.0008 ms selection p95** and **0.0076 ms cached store
navigation p95**; a provider-free selector rerun measured **4.400 ms p95 hit**
and **4.377 ms p95 no-skill**. Both fit their local budgets but exclude
SwiftUI rendering, paired voice latency and ten-minute memory growth. The exact
hardware model could not be read in this sandbox. The 85.3% weighted estimate
is still the previous dated checkpoint; this pass did not recalculate it. SW-B
and SW-C remain the only accepted gates; release/deployment remains open.
Candidate-bound SW-B, SW-C and selector receipts have been refreshed after the
implementation and documentation updates. The focused native store measurement
is recorded in `receipts/skill-store-navigation-performance-2026-09-28.json`;
its 100-sample test passes locally and remains a store-only microbenchmark.

## 2026-09-28 continued local hardening

Additional regressions close local race and recovery gaps while leaving broader
gates open:

- **SW-D:** Switching skills or using shared navigation clears the prior
  activity trace immediately; selecting the same skill preserves the current inspection. Two regressions cover both behaviors. Live reconnect and VoiceOver checks remain open.
- **SW-E:** Image-sharing now requires the full result record and refuses a
  protected result before its PNG bytes are retained in the share preview. The
  focused coordinator suite passes **23 tests**; broader privacy acceptance for
  app captures, diagnostics, database/JSONL, argv, user scoping and displays
  remains open.
- **SW-H:** A crash after the durable `publication_submitting` barrier is
  covered: if the sandbox still reports `validated`, recovery records an
  uncertain outcome and does not resubmit. Publisher success also requires a
  nonempty PR URL; focused recovery/request coverage passes **43 tests**.
  Real-VM restart and external publisher reconciliation remain open.
- **SW-I:** Skill-detail loads use a request generation and current-selection
  check, so late success or error responses cannot replace current detail,
  including overlapping requests for the same skill. Skill cards now expose
  enabled/disabled state in their accessibility value; the corrected native
  accessibility-tree test passes at both responsive widths. Live speech,
  VoiceOver and system accessibility checks remain open.

- **SW-K:** The latest integrated 100-sample store benchmark recorded selection
  p95 **0.0020 ms** and cached store navigation p95 **0.0198 ms** across 100
  public-fixture skills and 32 cached details. Both are within the local budgets;
  rendered navigation, paired live-voice latency and ten-minute memory remain
  unmeasured.

Current full-suite validation after these changes: Python **3,470 passed, 4
skipped, 11 warnings, 2 subtests**; MortimerHost **317 executed, 6 skipped, 0
failures**; JarvisKit **210 passed, 0 skipped**. The latest native run also
contains the protected-image and enabled/disabled accessibility changes. The six native skips include
physical two-display and foreground-WindowServer cases. A current
`system_profiler SPDisplaysDataType -json` probe reports only the built-in Apple
M5 display, so two-screen hardware acceptance cannot run on this candidate
session.
`git diff --check` passes. The 85.3% weighted estimate remains the prior dated checkpoint and was not
recalculated. SW-B and SW-C remain the only accepted SW-A–SW-L gates;
physical display, target-Mac, VoiceOver, real-VM, live-provider and release
acceptance remain open. Current candidate-bound SW-B, SW-C, selector, store-navigation and protected-PNG
receipts are bound to the refreshed worktree fingerprint; existing release-build
evidence remains stale.

### 2026-09-28 fixture resource-bound follow-on

Offline skill-authoring validation now bounds scoped fixture directories using
the catalog's existing limits: at most 128 fixture files, at most 128 KiB per
fixture, and at most 10 MiB total. The publication preflight requires all three
new checks in the complete offline-validation receipt, so an older receipt
cannot authorize publication after the validator contract changes. Regression
tests cover file-count, per-file, and aggregate-size rejection. The focused
authoring validation/policy/service and evaluation review/budget suites pass
**79 tests**; `git diff --check` passes. This change does not enable or activate
the creator. It remains inert pending runtime receipts and the open SW-A–SW-L
acceptance gates.

This candidate environment has no `tart` executable, so it cannot produce new
real-VM restart, network-containment, or publisher-reconciliation evidence.
Previously recorded VM evidence remains scoped to its documented candidate and
is not a substitute for re-running the creator lifecycle against the frozen
Skills Workspace candidate.

### 2026-09-28 native control accessibility regression

The responsive Skills library rendering test now inspects the mounted macOS
accessibility tree at 1280- and 720-point widths. It verifies the search field
and both state/category filter pickers expose their purpose in their native
accessibility names, alongside the existing enabled/disabled card-state
checks. The focused rendering test passes at both widths. This is native-tree
evidence, not live VoiceOver, keyboard-only, system-setting, or physical-display
acceptance; SW-I remains open.

### 2026-09-28 native accessibility-name regression

The mounted library test now asserts that the native accessibility tree includes
the search field name and the purpose descriptions for the state and category
filters at both 1280- and 720-point widths. The complete
`SkillsWorkspaceRenderingTests` suite passes **14 tests**. The picker names were
present as combined native labels; the test checks the descriptive portion
without assuming AppKit's exact label concatenation. This remains synthetic
native-tree evidence; actual VoiceOver, keyboard-only, system-setting, and
physical-display acceptance are open.

### 2026-09-28 host-verified weather process-step increment

SW2 now has one intentionally narrow host-owned process-step check for
`current-weather-with-fahrenheit@9064f3d61d680d8cbce9c4dda1b2d98b854624fce2b106f89cc7f13b4ace521e` /
`retrieve-conditions`. The checker binds the returned result to the requested
location, requires the requested forecast horizon, checks source timestamps,
Fahrenheit/Celsius consistency and valid daily high/low ordering, and refuses
to treat the Weather.gov forecast-only fallback as a current observation. The
weather tool exposes the query location and provider time separately from its
display-city label so Weather.gov's nearby-city naming does not create a false
location failure. These fields are used only by the host checker; activity
events persist the receipt reference, not weather content.

An integrated SubAgent test confirms a synthetic, structurally and semantically
valid tool result transitions this exact step from `running` to host-verified
`passed`; missing or invalid evidence remains `unknown`. Focused validation
passed **188 tests** across the SubAgent bridge, receipt/check contract,
weather tool, Weather.gov and ambient-weather suites (3 dependency deprecation
warnings). This is synthetic contract evidence; no live provider query,
deployment, protected-run acceptance, runtime-readiness receipt, or other
process-step completion is claimed. SW2 and the broader Skills Workspace gates
remain in progress.
The full Python suite then passed **3,482 tests, 4 skipped, 11 warnings, and 2
subtests**. Skips/warnings are retained as reported by pytest; this local run
does not close hardware, live-provider, VM, accessibility, or release gates.

### 2026-09-28 second host-verified process step and legacy trace evidence

SW2 now has a second exact host-owned mapping for
`git-history-and-status-review@8794a16e69d4908ff12906e93b8b5cc01d0560c8c792d0ab43279c41ac1a5c7e` /
`inspect-repository`. The read-only `git_status` result now includes the actual
Git top-level path and explicit upstream (or `null`), alongside branch, dirty
paths and ahead/behind counts. Outside a valid Git worktree the tool returns a
bounded error result; the checker requires the exact structure and rejects
inconsistent clean/changed-path state. Receipt-backed completion persists only
the content-free receipt reference; the repository path and changed paths do
not appear in activity events.

SW-D's legacy-run contract also has an API regression: an older run with no
skill events returns `trace_status=unavailable`, an empty trace and unchanged
cursor, without task/reply content. The current full Python suite passes
**3,482 tests, 4 skipped, 11 warnings, and 2 subtests**, including the weather
and Git receipt paths, Git status output and legacy-run API case. These remain
local tests with synthetic tool results; no external Git/provider runtime,
cross-process receipt, or Mac UI acceptance is claimed. SW2 is still in
progress, and other process steps remain `unknown` unless separately mapped
and validated.

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

### 2026-09-28 parallel closeable implementation increment

SW-A gained a rendered rollback-layout regression confirming that the sidecar
and voice controls remain reachable. This supplements, but does not replace,
the required target-Mac before/after interaction matrix across rollback and
adaptive modes.

SW-D now labels historical Activity steps against their recorded package
revision. When the current skill revision differs, the UI displays the step ID
and historical digest prefix instead of borrowing a current step title. It
also identifies unavailable event revisions. Focused native rendering tests
cover matching, mismatched, and missing revisions; the full MortimerHost suite
passes **328 tests, 7 skipped, and zero failures**.

SW-L gained `scripts/verify_skills_workspace_release_evidence.py`, a fail-closed
local verifier for required candidate-bound receipts and the app bundle's
embedded candidate fingerprint, executable digest/size, bundle identity, and
candidate branch/HEAD/dirty state. Six focused tests pass. The release app
bundle has been rebuilt from the final candidate, its signature verifies, and
the candidate receipt refresh is complete; the fail-closed verifier passes all
six required local candidate-bound receipts.

SW0 now checks that catalog and detail fixtures agree on duplicated identity,
display, install, readiness, and process-summary fields; a mutation test proves
drift is rejected. SW1 now performs a final pin/digest/body validation at the
prompt-injection boundary. SW-D applies the existing strict Activity-page
validator at the API boundary and guards A→B→A selection changes with a
monotonic generation so stale event and error responses cannot replace the
current run. The focused fixture, injection, API, and rendering tests pass.

The full Python suite passes **3,491 tests, 4 skipped, 11 warnings, and 2
subtests**; MortimerHost passes **329 tests, 7 skipped**, and JarvisKit passes
**211 tests**. Scoped Ruff checks pass, and `git diff --check` is clean. These
local checks do not close VoiceOver, keyboard-only, live voice, target-Mac
visual review, provider, VM, physical-display, activation/rollback, or release
acceptance. The final receipt refresh updated candidate identity metadata only;
it did not rerun the named measurements or broaden their claims. SW-B and SW-C
remain the only accepted SW-A–SW-L gates.

### 2026-09-28 latest parallel implementation and acceptance checkpoint

SW4 now binds cancellation, draft receipts, and offline-validation receipt
association to the exact expected sandbox run ID; its focused request and
recovery suites pass **74 tests**. Real-VM lifecycle, restart/reconnect, and
publisher reconciliation remain open. SW5 now requires paired evaluation
conditions to use the same provider, model, route, and billing mode; focused
review and budget tests pass **39 tests**. No live evaluation trials or
independent human ratings have run. SW-E adds a ScreenCaptureKit protected-
content canary: **3 tests pass and 1 is skipped** because Screen Recording
permission is unavailable. This does not establish capture behavior for the
running Mortimer app or supporting display.

The latest full local suites pass **3,496 Python tests (4 skipped, 11 warnings,
2 subtests)**, **330 MortimerHost tests (8 skipped)**, and **211 JarvisKit
tests**. On the Apple M5 Mac17,4 with 16 GB RAM and only its built-in display,
100-sample measurements report selection p95 **0.0008 ms** and cached store
navigation p95 **0.0075 ms**; these timings exclude SwiftUI rendering and
network activity and do not establish multi-display performance.

Using the existing SW0–SW6 rubric (weights **10/15/15/15/20/15/10%**), the
current implementation estimate is **87.1%**, from scores **86/82/94/93/93/85/68%**.
This is an implementation-progress estimate, not a claim that acceptance gates
are complete. The candidate receipt fingerprint is stale after these source
and documentation updates and must be refreshed before release evidence can
verify. The app bundle has not been installed, launched, or deployed. Still-open
manual/external gates include VoiceOver and keyboard-only review; live voice and
target-Mac visual acceptance; Screen Recording permission and app/supporting-
display capture; physical multi-display behavior; real-VM restart/reconnect and
publisher recovery; provider trials with independent human review; activation
and rollback; and final release acceptance. SW-B and SW-C remain the only
accepted SW-A–SW-L gates.

### 2026-09-28 parallel implementation checkpoint — activity, privacy, and rendered-performance coverage

SW-D now rejects malformed base64 run-list cursors unless the decoded timestamp is ISO-8601 with a timezone and the run ID is valid. Pagination with tied timestamps returns every run exactly once; invalid cursors return HTTP 400. Focused activity API, cursor-edge, and runlog tests pass **48 tests**.

SW-E expands local protected-content tests across comparison sharing, every non-external share policy, clipboard and file export refusal, inventory and supporting-display exclusion, and protected basemap images. The focused MortimerHost privacy suites pass **55 tests**; one ScreenCaptureKit test remains skipped because this runner lacks Screen Recording permission. Actual app and supporting-display capture remains unverified.

SW-K now has a compiled 100-sample rendered-navigation harness for wide and compact layouts, using synthetic catalog/detail fixtures and real `NSHostingView` layout/display. This runner reports `NSScreen.screens` empty, so the benchmark skipped and produced no rendered p95 values. The latest integrated store-only measurements are selection p95 **0.0022 ms** and cached navigation p95 **0.0213 ms**; they exclude SwiftUI rendering and network activity and do not close the rendered, voice-latency, or memory-soak budgets.

Latest full local results: **3,497 Python passed, 4 skipped, 11 warnings, and 2 subtests**; **334 MortimerHost tests, 9 skipped, 0 failures**; **211 JarvisKit tests, 0 failures**. The 87.1% prior weighted estimate is updated to **87.7%**, using SW0–SW6 weights **10/15/15/15/20/15/10%** and scores **86/82/95/94/94/85/69%** (8.60 + 12.30 + 14.25 + 14.10 + 18.80 + 12.75 + 6.90). This remains an implementation-progress estimate, not gate or release completion.

The exact-run cancellation acknowledgement fix also has **74 focused authoring/request/recovery tests** passing. The release bundle is rebuilt and its current candidate fingerprint and receipt metadata are verified below; runtime and release acceptance remain separate gates. Only SW-B and SW-C remain accepted. Open gates still include VoiceOver/keyboard and live-voice review, target-Mac rendering and capture with Screen Recording enabled, physical multi-display/unplug/reconnect, real-VM isolation and restart/publisher recovery, live provider trials with independent ratings, activation/rollback, rendered/voice/memory performance budgets, and final release handoff. Runtime enforcement remains disabled.

### Open design decision — asynchronous creator validation activity ownership

An independent SW2 review found that the offline validator receipt is bound to its durable sandbox run, slug, candidate digest, and validation checks, but not to a Mortimer `agent_runs` ID, owning developer request, or recorded `offline-validate` attempt. The creator manifest declares no tool for this step. The trusted step-receipt API requires a real owned run and exact started attempt; attaching the existing validation receipt after the fact would fabricate that link. Keep this process step `unknown` until ownership is defined. No checker mapping or creator activation was added.

The implementation plan needs to select one boundary before code can close this gap: carry the originating agent-run/request/attempt identity through the asynchronous validation job and define how a late result is recorded if the conversation run has already ended; or create a host-owned validation-request activity lifecycle, linked to the originating run but distinct from the chat-run status. In either design, sandbox candidate digest, exact request/run identity, cancellation/restart reconciliation, and content-free events must remain enforced.

### 2026-09-28 parallel follow-on checks

SW-H adds a deterministic Session test for a host interruption after the
publisher's durable idempotency record is written but before the session result
is saved. Reopening the session reconciles to `publication_pending`, and retry
returns the recorded publication without creating another one. All **119
sandbox tests** pass. This is simulated recovery only; Tart VM restart,
reconnect, cancellation, and publisher reconciliation remain open.

SW5 hardens review scoring: the submitted fixture digest must match an
approved frozen fixture; the checked-in fixture bytes and complete case
criteria must still match; and package revision/model identity fields must be
well formed. The focused evaluator review/budget suites pass **42 tests**. No
provider calls were made. Route/budget setup, 24 live paired trials, blinded
human ratings, activation diff, and rollback evidence remain open.

SW-I review found existing automated coverage for large Dynamic Type layouts,
accessibility labels/values, and process-step state. No additional synthetic
test can prove the outstanding system-level behavior. The focused Swift test
could not start because this runner returned `sandbox_apply: Operation not
permitted`; the previously recorded MortimerHost suite remains **334 tests, 9
skipped, 0 failures**. VoiceOver traversal/announcements, Full Keyboard Access,
real system text-size settings, spoken navigation, and creator review still
require target-Mac acceptance.

SW-F remains open: `sandbox/control.py doctor` reports Tart unavailable and
the network helper ready (root-owned, setuid, executable). Without Tart, no
VM probe could run. The configured Softnet policy blocks IPv4 but does not
prove IPv6 filtering. A failed guest IPv6 connection is inconclusive unless an
active guest IPv6 route is established. Acceptance requires a target-Mac IPv6
canary with a known working route, proving IPv6 is blocked in provisioning and
offline modes while the expected IPv4 behavior is preserved.

After these additions, the full Python suite passes **3,500 tests, 4 skipped,
11 warnings, and 2 subtests**. The last weighted implementation estimate is
still **87.7%**; this follow-on has not been rescored, and the estimate is not
acceptance completion. Only SW-B and SW-C are accepted. The creator activity
ownership design decision above remains unanswered and its dependent receipt
work must stay open.

An additional SW-F guard now makes the probe report distinguish existing
observations from full containment: it emits `unverified` and sets
`full_network_containment_proven=false` and `acceptance_complete=false` unless
affirmative active-route and blocked-canary fields are present. The current
probe does not collect those fields, so it cannot report complete containment.
Four focused gate tests and all **123 sandbox tests** pass. Ruff import checks
and scoped `git diff --check` pass. Candidate-bound release receipts must be
refreshed after this code/documentation change; no VM or release run was made.

### 2026-09-28 rendered benchmark and protected-response follow-up

The earlier rendered-benchmark attempt skipped because `NSScreen.screens` was
empty; that result is superseded for this run by a successful release build on
an attached-window fixture. Across 100 samples, wide 1280×800 selection-to-
layout p95 was **18.513 ms** and cached navigation p95 was **27.021 ms**;
compact 720×800 measured **10.413 ms** and **11.076 ms**. These meet the
20 ms selection and 100 ms cached-navigation budgets. Full-window bitmap p95
was **16.280 ms wide / 7.345 ms compact** and remains diagnostic, excluded
from selection response latency. The fixture had 100 catalog skills, 32 cached
details, zero detail requests during measurement, and 65 distinct rendered
frames. This does not close paired live-voice latency or ten-minute memory
growth.

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
suite has no terminal summary. The last weighted estimate remains **87.7%**,
unrescored. Only SW-B and SW-C are accepted; remaining platform, provider, VM,
accessibility, live-voice, memory-soak, activation/rollback, and release gates
remain open.

### 2026-09-28 follow-up — Reduce Motion and suite hang

The rendered console's `BreathingDot` and `DotPulse` now honor the system
Reduce Motion setting, including changes while the view is active. The full
console rendering fixture enables Reduce Motion, and an active-agent compact
rail regression checks that the status remains visible in that mode. This is
a targeted hypothesis test for the AppKit animation accumulation above; it is
not evidence that the full-suite hang is fixed. Focused tests could not be run:
the repository SwiftPM build lock remained held, and an isolated scratch build
was rejected during sandbox setup. Re-run the focused UI tests and complete
release suite when a clean SwiftPM runner is available. Window-detach cleanup
alone did not resolve the hang; a post-cleanup sample again reported the
64-thread soft limit reached across 1,978 sampler frames, with workers in
`NSAnimation._runBlocking`. The full suite still has no final summary.

The captured runner sample shows XCTest's main thread waiting while the
dispatch thread soft limit of 64 was reported reached across **3,288 samples**;
those samples show AppKit workers blocked
inside AppKit `NSAnimation._runBlocking`; physical footprint was 462 MiB at
sample time with a 1.0 GiB peak. The stalled PanelStore method is synchronous,
uses a fresh store, passes alone and in a focused run after the memory-graph
frame-time test, and does not create AppKit views. This points to accumulated
AppKit/SwiftUI animation work in the larger test process, but the animation
source has not yet been localized. Treat this as an unresolved test-harness
stability issue; do not attribute it to PanelStore or claim the suite passes.

### 2026-09-28 follow-up — Reduced-motion fixture and suite isolation

Mortimer now exposes an effective motion preference that follows macOS
`accessibilityReduceMotion` by default and permits a host override for
deterministic UI fixtures. The console breathing dot, active-agent pulse,
drawer-tab scrolling, adaptive stage, skills workspace, result workspace, and
voice-wave timeline consume that effective preference. Relevant UI fixtures
set the override to reduced motion, preventing them from starting continuous
or scroll animations while preserving the normal system default in the app.

Verification: the focused adaptive/drawer/console/compact/panel group passed
**25/25**. All test classes before `PanelStoreTests`, plus `PanelStoreTests`,
passed **184/184** in one filtered release process. The unfiltered release
process still stalled at the PanelStore boundary. A current runner sample again
reported the 64-thread dispatch soft limit, AppKit `NSAnimation._runBlocking`
workers, and XCTest waiting for object deallocation. Thus, the panel tests pass
when selected after the same 181 preceding cases; the unfiltered runner remains
unstable and the causal animation source has not been proven. The full Python
suite passed **3,500 tests, 4 skipped, 11 warnings, and 2 subtests**;
`git diff --check` passes. The weighted estimate remains **87.7%**, unrescored;
only SW-B and SW-C are accepted gates.

### 2026-09-28 follow-up — Partitioned native acceptance

To separate runner instability from test failures, every MortimerHost class was
run in two release processes. All classes through `PanelStoreTests` passed
**184/184**; the remaining classes passed **150 tests, 6 skipped, 0 failures**
when the live ScreenCaptureKit capture case was excluded. That one case was
also attempted and failed at capture start with ScreenCaptureKit internal error
`-3811` despite `CGPreflightScreenCaptureAccess()` returning true; live
window-capture acceptance therefore remains unverified in this environment.
The full, unfiltered suite still stalls in XCTest's object-deallocation wait
with the dispatch soft limit at 64. Partitioned passes do not close SW-L's
unfiltered release gate. JarvisKit's release suite passed **211/211**. The
latest 100-sample SW-K run measured selection-to-layout p95 at **18.264 ms
wide / 10.355 ms compact** and cached navigation at **26.863 / 11.059 ms**.
These local sub-budgets pass; voice p95 and the ten-minute memory soak remain
open. The weighted estimate remains **87.7%**, unrescored.


### 2026-09-28 parallel diagnostics — capture prerequisite and suite-order stall

The protected-window capture fixture now attempts to activate the test host,
foreground its window, and verify that the window is visible and unoccluded
before asking ScreenCaptureKit for pixels. In this runner, Screen Recording
preflight succeeds and a display is enumerated, but the process does not become
active within the three-second prerequisite wait. The capture test therefore
fails before capture; this is evidence that the current WindowServer session
cannot present the test window, not evidence of a product capture defect. Do
not skip the test or mark SW-E accepted. Re-run in an interactive,
foreground-capable Mac session.

A focused sequence containing `AdaptiveInterfaceClosureC2Tests`,
`CompactConversationTests`, `OrbShellFrameTimeTests`, and `PanelStoreTests`
passed **15/15**. An earlier release prefix through PanelStore passed
**184/184**. The full unfiltered suite remains intermittent and order-sensitive;
the sampled stall is in XCTest's object-deallocation wait with AppKit
`NSAnimation._runBlocking` workers after the dispatch soft limit reaches 64.
No individual fixture or PanelStore defect has been established, so retain the
unfiltered SW-L gate and continue targeted isolation rather than changing
product behavior or weakening assertions. No new weighted estimate was
calculated; the last estimate remains **87.7%**, and only SW-B/SW-C are accepted.


### 2026-09-28 follow-up — complete Reduce Motion coverage for console transitions

A source audit found three remaining unguarded UI effects: the wake ripple,
connect/reconnect entrance fades, and transcript auto-scroll. They now follow
`mortimerReduceMotion`: wake events retain a static visible ring, entrance
changes settle without animation, and transcript updates scroll directly.
Focused release tests compiled the changes and passed **11 tests, 3 skipped,
0 failures**. The skips are the actual foreground-window visibility tests; this
runner still cannot activate the app, so the interactive acceptance remains
open. `git diff --check` passes. This is local implementation progress only;
SW3 platform review and the prior 87.7% weighted estimate remain unchanged.


### 2026-09-28 follow-up — assert active wave teardown on window close

The continuous-wave visibility test now asserts that sample callbacks stop
after its host window closes, in addition to checking suspension while hidden
and resumption when shown. The focused release target compiled and ran: **1
test passed, 3 visibility-dependent tests skipped, 0 failures**. The waveform
closure assertion itself was skipped because this WindowServer session cannot
activate the fixture; it remains to be exercised on an interactive Mac.
`git diff --check` passes. This adds a stronger lifecycle assertion but does not
localize or resolve the intermittent unfiltered-suite teardown stall.


### 2026-09-28 follow-up — system transparency and contrast preferences

The shared glass modifier now reads macOS Reduce Transparency and Increased
Contrast. Standard settings preserve the signed liquid-glass treatment; Reduce
Transparency forces a fully solid panel; Increased Contrast uses an opaque panel
and a stronger border. The explicit glass-off rollback fill is unchanged.
Focused `GlassAccessibilityTests` pass **4/4**. Visual verification with both
macOS settings remains open because this runner's Mac session is locked; no
VoiceOver, contrast or release acceptance is claimed.


The shared-glass follow-up then passed its rendering regression group:
`FullConsoleRenderingTests`, `SkillsWorkspaceRenderingTests`, and
`GlassAccessibilityTests` — **27/27**. This proves normal rendering call sites
remain functional with the environment-aware modifier; it does not validate
the actual appearance under macOS Reduce Transparency or Increased Contrast,
which still requires the unlocked Mac review above.

### 2026-09-28 weighted implementation scorecard refresh

The plan now defines fixed 0/25/50/75/100 evidence anchors and requires open
exit criteria or unverified acceptance evidence to keep a workstream below
100%. Fixed SW0–SW6 scope weights remain **10/15/15/15/20/15/10%**. The latest
calibrated workstream scores are **86/82/95/96/94/86/69%**, respectively. SW3
increased two points for completed reduced-motion transitions, system
transparency/contrast handling, and display-sink rejection of protected content,
with focused regressions. SW5 increased one point for binding human scores to
the exact blinded response text with focused integrity tests. The other stream
scores are unchanged because the follow-up work did not close a listed
milestone in those streams.

Weighted calculation: **8.60 + 12.30 + 14.25 + 14.40 + 18.80 + 12.90 + 6.90
= 88.15%**, reported as **88.2% implementation progress**. This is not a
release-readiness percentage. Only **2 of 12 SW-A–SW-L acceptance gates
(16.7%)** are accepted: SW-B and SW-C. Remaining open evidence includes the
unlocked-Mac visual/accessibility/capture checks, live voice and physical
multi-display behavior, Tart VM lifecycle and network containment, 24 live
provider trials with independent ratings, activation/rollback, memory soak, and
the unfiltered native release suite. Keep those gates open regardless of the
weighted score.

SW-E sink hardening also landed in this working tree: protected payloads are
rejected before display-panel creation, Developer-batch append, or streamed
response replacement; the router retains protected answers in the main local
workspace. The new direct-sink canaries pass **2/2**; related panel, share/export,
and display-fit regressions pass **30/30**. This source change does not prove
actual ScreenCaptureKit behavior; live app/supporting-display capture and the
SW-E acceptance gate remain open.

The complete unfiltered MortimerHost release run now finishes rather than
stalling: **341 tests executed, 6 skipped, 1 failure** in 100 seconds. The only
failure is `ProtectedDisplayContentTests.testProtectedContentInActualWindowCaptureMatchesBodyOnlyReference` timing out before capture because the test host cannot become the active app in this WindowServer session. No content-comparison assertion ran. This does not establish a product capture leak or prove capture safety; repeat in an unlocked foreground-capable session. The single failure keeps SW-E and SW-L open. The earlier full-suite teardown stall did not reproduce in this run.

Within that same release test process, the 100-sample synthetic rendered Skills
benchmark reported wide/compact selection-to-layout p95 of **19.141/11.397 ms**
and cached-navigation p95 of **27.898/11.826 ms**. These are within the
20/100-ms sub-budgets. `hw.model` could not be read in the current sandbox, so
do not treat this run as a hardware-bound target-Mac receipt. Paired live-voice
latency and ten-minute process-memory growth are still unmeasured; SW-K remains
open.

### 2026-09-28 sandbox cancellation crash-recovery follow-up

`Session.resume()` now reconciles a durable cancellation marker with the
controller before returning a terminal cancellation error. This covers the
crash window where the host persisted `cancelled.json` but exited before the
sandbox controller stopped a running or provisioning VM. The interruption-
recovery regression and focused session suite pass **10/10**. This is local
simulated recovery evidence only: Tart is unavailable in this runner, so real
VM stop/reopen/reconnect recovery and SW-H acceptance remain open. The weighted
score remains **88.2%** pending full rubric recalibration against all listed
milestones; only SW-B and SW-C remain accepted.

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

Three independent local gaps were closed. SW-D native activity decoding now
rejects unsupported lifecycle type/status pairs, unbounded or unsupported
evidence references, a `passed` step without a trusted `check_receipt_id`, and
protected/truncated events that still expose skill, revision, step, or evidence
data. Regression coverage was added, but the focused Swift test could not run:
SwiftPM was blocked by sandbox initialization and the retry could not fetch its
WebRTC dependency because network access was unavailable. `swiftc -frontend
-parse` succeeds; this is syntax evidence only.

SW-E now fails closed when the memory-graph bitmap lacks payload-level privacy
classification and identity. PNG sharing of that bitmap is refused, and an
ordinary result PNG request no longer borrows it. Text result sharing remains
available. Regression coverage checks both routes and that no preview is
created; SwiftPM test execution was blocked at manifest initialization. Syntax
parse and `git diff --check` pass. This is a deliberate image-sharing limitation
until a classified image source is implemented; protected-window pixel capture
acceptance remains open.

SW-H draft reconciliation now preserves a concurrently written cancellation
request instead of overwriting it with stale `drafting` state. A deterministic
threaded regression verifies the cancellation settles against the same request
and sandbox run. The focused request suite passes **43 tests**. Real-Tart stop,
restart/reconnect, and publication reconciliation acceptance remain open.

Parent verification after combining this work with the SW2 runtime/readiness
loader fix: focused registry/readiness/activity/request suites pass **105
tests**; the full Python suite passes **3,510 tests, 4 skipped, 11 warnings,
and 2 subtests**. Ruff passes on all touched YAML-loader, registry, readiness,
and test files. `jarvis/skill_requests.py` retains 17 existing Ruff BLE001/S110
findings outside the cancellation change. `git diff --check` and Swift syntax
parsing pass. The focused native regression tests remain unexecuted, so SW-D and
SW-E do not receive acceptance credit.

The implementation estimate is **88.9%** using fixed weights
**10/15/15/15/20/15/10%** and scores **87/82/97/96/95/86/70%**; contributions
are **8.70 + 12.30 + 14.55 + 14.40 + 19.00 + 12.90 + 7.00 = 88.85%** before
rounding. Only SW4 increases by one point for the tested cancellation-race
closure; unexecuted Swift regressions do not increase SW3. The latest release
evidence verifier still reports candidate-bound receipts stale (SW-B, SW-C,
SW-E, performance, and app bundle), so **0/12 gates are currently verified for
this dirty candidate**. Hardware, locked-Mac, physical-display, live-provider,
human-review, and frozen-release gates remain open.

### 2026-09-28 native execution and local receipt refresh

With the repository-cached WebRTC checkout, SwiftPM native tests ran after
allowing manifest compilation. JarvisKit `AdminAPITests` pass **11/11**,
including the new malformed lifecycle/protected-event cases. MortimerHost's
full suite passes **342 tests, 7 skipped, 0 failures**; the seven skips are
environmental display/foreground prerequisites, including the connected-two-
display acceptance cases. The new unclassified-memory-graph PNG regression
passes, as do the rest of `ConsoleActionCoordinatorTests`. Together with the
fresh SW-B and SW-C checks in this continuation—**89 package-integrity tests**,
the public selection fixture **14/14** with zero provider calls, and **104
selection/fixture/SubAgent tests**—the local regressions are verified for the
current source. These runs do not verify physical displays, live runtime
readiness, screenshots of the running app, or release behavior.

The SW3 implementation score increases by one point for passing native
regression and full-suite evidence, producing **89.0%** overall: scores
**87/82/97/97/95/86/70%**, weights **10/15/15/15/20/15/10%**, contributions
**8.70 + 12.30 + 14.55 + 14.55 + 19.00 + 12.90 + 7.00 = 89.00%**. This does
not change acceptance-gate count. The release verifier still rejects stale
candidate-bound receipts and the current candidate remains **0/12 verified**
until applicable receipts and the app bundle are rebound to the frozen source.

### 2026-09-28 current-candidate receipt rebinding

After the native and focused SW-B/SW-C reruns, all six receipts required by
`scripts/verify_skills_workspace_release_evidence.py` were rebound to candidate
fingerprint stored in their receipt metadata. The verifier passes. Current
SW-B and SW-C evidence is accepted for this candidate:
89 package-integrity tests, matching pins with creator inert, and 14/14 public
selection fixtures plus 104 focused tests with zero provider calls. Thus **2/12
acceptance gates are verified**, not 0/12. SW-E's PNG-path tests pass locally,
but actual foreground-window capture skipped; SW-K benchmarks pass their local
budgets, but `hw.model` was denied and paired voice latency/memory soak remain
open. The signed release app bundle embeds the current fingerprint and passed
strict signature verification; it was not launched, installed, or deployed.

Fresh SW-K measurements: selector unique-hit/no-skill p95 **4.427/4.397 ms**;
store selection/cached navigation p95 **0.0007/0.0075 ms**; rendered wide/compact
selection-to-layout p95 **18.944/10.824 ms** and cached-navigation p95
**27.387/11.292 ms**. The p95 thresholds pass locally. Hardware identity remains
unverified, so these do not close SW-K. The weighted implementation estimate
remains **89.0%**; source implementation did not change during receipt rebinding.

### 2026-09-28 parallel follow-up: SW2, SW-F, and SW-I

Three bounded parallel lanes completed local work. SW2 now validates host step
receipts fail-closed: boolean values cannot masquerade as schema version 1,
timestamps must have valid types and timezone-aware values, and receipt identity
and check-list fields are checked exactly. Its focused regression suite passes
**26 tests**. SW-F adds explicit IPv6 default-route observations and only reports
network containment when positive route and blocked-canary evidence are both
present. Missing or inconclusive observations cannot pass. The combined probe
and controller suite passes **43 tests**. SW-I announces process-step selection
and collapse to accessibility clients using generic messages; it does not speak
step IDs. The focused SkillsWorkspace suite passes **30 tests**. These are local
implementation and regression results; VoiceOver behavior on a live Mac remains
unverified.

`git diff --check` passes. A broad Ruff invocation reports 14 findings across
the existing sandbox controller/test files; no lint-clean claim is made. Live
Tart testing is unavailable (`tart: false`, `ready_to_boot: false`), so IPv6
containment and creator isolation remain open. The latest candidate evidence
verifier reports all six required receipts stale, including the app-bundle
fingerprint; the changed worktree currently has **0/12 candidate-bound
acceptance gates**.

The weighted implementation estimate is **89.3%** using the unchanged rubric:
SW0–SW6 scores **87/82/98/98/95/86/70%**, weights **10/15/15/15/20/15/10%**,
and contributions **8.70 + 12.30 + 14.70 + 14.70 + 19.00 + 12.90 + 7.00 =
89.30%**. SW2 and SW3 each increase one point for the tested exact receipt
validation and VoiceOver announcement behavior. SW-F diagnostics do not increase
its workstream score because the VM isolation behavior has not run. This is
implementation progress, not release readiness or gate completion.

Remaining high-risk closure work is target-Mac VoiceOver and display acceptance,
real Tart lifecycle and IPv6 canary trials, integrated runtime/readiness evidence,
the unresolved ownership decision for async creator-validation activity, the
provider comparison and blinded human review, target hardware latency/memory
measurements, then a frozen candidate with refreshed receipts and a rebuilt
release bundle. No commit, push, install, or deployment was performed.

### 2026-09-28 additional parallel code closure and full-suite verification

SW-E now authorizes image sharing only when the result explicitly uses the
approved-external policy and the image URL exactly matches that result's
declared image or basemap source. Memory-graph endpoints are refused, and the
validated PNG is decoded and re-encoded to remove source metadata. Its focused
ShareCoordinator and action-coordinator tests pass **37 tests**. This closes a
local unclassified-image sharing path; protected live-window and supporting-
display capture remain open.

SW-G now rejects evaluation metrics whose cost basis is unknown or inconsistent
with the declared billing mode; only internally consistent subscription or
price-map evidence can complete the scorer's metrics check. The focused
evaluation/budget tests pass **45 tests**. No provider calls were made. The
24-trial live comparison, frozen artifacts, independent blinded review, and
maintainer acceptance remain open.

SW-H now reconciles a dead publication worker to
`publication_needs_reconciliation` when sandbox status is unavailable, while
preserving an actively publishing state if its local worker is still alive.
The focused publication/request suites pass **50 tests** with one existing
warning. This prevents a request from appearing to publish indefinitely after
a restart without claiming publication success.

After these changes, broad local regression passes: Python **3,520 passed, 4
skipped, 11 warnings, 2 subtests**; MortimerHost **344 tests, 9 skipped, 0
failures**; JarvisKit **212 tests, 0 failures**. Focused SW2/SW-G Ruff checks
and `git diff --check` pass. The skipped native cases still include
foreground/display prerequisites. The candidate-bound verifier still rejects
all six required receipts as stale, so this dirty candidate remains at **0/12
verified gates**.

The recalculated weighted implementation estimate is **89.8%**. SW0–SW6 scores
are **87/82/98/99/96/87/70%**, using fixed weights **10/15/15/15/20/15/10%**;
contributions are **8.70 + 12.30 + 14.70 + 14.85 + 19.20 + 13.05 + 7.00 =
89.80%**. SW3 gains one point for source-bound, metadata-stripping image
sharing; SW4 gains one for tested dead-publication reconciliation; SW5 gains
one for rejecting unverifiable cost evidence. These changes do not close live
acceptance gates.

The next remaining work is target-environment acceptance: Tart lifecycle and
IPv6 canary trials; live app, VoiceOver, and physical-display capture; runtime
readiness and real skill-run evidence; paired provider trials and independent
human review; target-Mac latency/soak measurements; and frozen-candidate receipt
refresh plus release-bundle verification. Creator-validation activity ownership
is awaiting the user's design choice, so the dependent attribution change stays
parked.

### 2026-09-28 release-bundle build path correction

The release bundle helper now uses `-debug-info-format none` for release builds,
which avoids a host-specific dSYM generation failure. An explicit
`MORTIMER_SWIFT_BUILD_DISABLE_SANDBOX=1` opt-in passes `--disable-sandbox` to
SwiftPM for controlled local environments; it defaults off and rejects invalid
values. Regression tests assert the release flags and opt-in behavior. The
release build and ad-hoc bundle/signature verification succeeded with the
launcher disabled; no app was opened or deployed. `tests/unit/test_native_bundle.py`
passes **9 tests** with two subtests, and `bash -n` passes.

This lifts SW6 to 71% for a reproducible local release bundle path. The updated
weighted estimate is **89.9%**: SW0–SW6 scores **87/82/98/99/96/87/71%** at
weights **10/15/15/15/20/15/10%**, contributions **8.70 + 12.30 + 14.70 +
14.85 + 19.20 + 13.05 + 7.10 = 89.90%**. The previous full suites (Python
3,520 passed/4 skipped, MortimerHost 344/9 skipped, JarvisKit 212/0 skipped)
preceded this narrowly scoped packaging-script change; the helper's current
focused tests pass. The required local evidence receipts were subsequently
refreshed and are summarized below.

### 2026-09-28 current candidate evidence refresh

All six receipts required by `scripts/verify_skills_workspace_release_evidence.py`
are now bound to the documented candidate fingerprint, and the verifier passes.
SW-B and SW-C are verified for this candidate (**2/12 gates**): 89 package
integrity tests with all five active pins matching and creator inert; 14/14
selection fixtures plus 104 focused tests with zero provider calls. SW-E's
source-bound image sharing tests pass; actual foreground capture is skipped
without Screen Recording permission.

Current local SW-K numbers are selector p95 **8.530/8.043 ms** (100 samples)
and store selection/cached navigation p95 **0.0009/0.0095 ms** (100 samples),
within local budgets. Rendered-navigation benchmarking skipped because this
host has no active display, hardware identity remains unavailable, and paired
voice latency plus ten-minute memory growth remain unmeasured. The release app
bundle embeds this same candidate fingerprint and passes strict ad-hoc
signature verification; it was not opened, installed, or deployed.

The **89.9%** weighted implementation score remains separate from the **2/12**
verified-gate count and from readiness to release. The current receipts cover
candidate identity and local evidence only. Tart isolation/lifecycle, live
VoiceOver, physical displays, provider trials, independent human review,
target-Mac performance/soak, activation/rollback and deployment remain open.

Final aggregate Python rerun after the release-helper changes passes **3,522
tests, 4 skipped, 11 warnings, and 2 subtests** in 113.97 seconds. The full
MortimerHost and JarvisKit results remain **344/9 skipped/0 failures** and
**212/0 failures** respectively; only local release-helper packaging code
changed after those native runs. The helper's focused suite passes **9 tests**
with two subtests. Any later source or plan edit invalidates receipt binding;
rerun the candidate verifier before handoff.

### 2026-09-28 final local implementation follow-up

Three parallel local implementation gaps were closed. SW-D activity refresh now
restarts when the host connection changes from offline/failed to connected,
without putting diagnostic failure text into the refresh identity. SW-E activity
fallback text now rejects untrusted backend step IDs unless they are bounded,
identifier-shaped values. SW-K wide selection performance was optimized without
changing the benchmark or its 20 ms budget: overview selection no longer
restarts inactive activity/version tasks, unfiltered catalog reads reuse the
backing card array, row equality compares only visual/accessibility fields, and
exact-revision cached detail is installed in the selection update.

Current-candidate verification after those changes:

- `./.venv/bin/python -m pytest -q` — **3,526 passed, 4 skipped, 11 warnings,
  and 2 subtests**.
- `swift test --package-path macos/MortimerHost` — **346 tests, 7 skipped,
  0 failures**. Skips require Screen Recording permission, an active foreground
  app, or two connected displays; they are not live privacy/display acceptance.
- `swift test --package-path macos/JarvisKit` — **212 tests, 0 failures**.
- SW-B package integrity — **89 passed**, with `jarvis.agent_skills --validate`
  confirming all enabled pins match.
- SW-C selection — **14/14 fixture cases** and **104 focused tests passed**,
  with zero provider calls.
- SW-E privacy/sharing — **41 native tests, 1 Screen Recording-dependent skip,
  0 failures**; SW-D/SW-E rendering and activity tests — **20 passed**.
- SW-F probe/controller tests — **43 passed**. They validate fail-closed
  reporting only; Tart IPv6 network containment remains unproven.
- SW-K 100-sample rendered selection-to-layout p95: **15.224 ms wide** and
  **7.235 ms compact**. Cached rendered navigation: **46.491 ms wide** and
  **28.239 ms compact**. Store-only selection/navigation: **0.0008/0.0081 ms**.
  The new `scripts/check_process_memory_soak.py` helper has **4 passing tests**
  and measures a manually prepared MortimerHost process without launching or
  controlling it. The target-Mac 10-minute library-plus-live-trace soak and
  paired voice-latency comparison are still unmeasured.
- SW-J display aggregation tests pass locally, but one/two-physical-display
  move/unplug/reconnect/restart acceptance remains open.

The unchanged 20 ms SW-K threshold now passes consistently after the UI-path
optimization; observed wide p95 runs were **15.46, 16.11, 16.23, and 15.224 ms**.
The prior single full-suite miss (21.603 ms) and isolated repeat (20.521 ms)
were retained as evidence and resolved by the implementation change rather than
by relaxing the threshold. A final full MortimerHost run then passed.

The weighted implementation estimate is now **90.1%** using scores
**87/82/98/99/96/87/73%** for SW0–SW6, weights **10/15/15/15/20/15/10%**, and
contributions **8.70 + 12.30 + 14.70 + 14.85 + 19.20 + 13.05 + 7.30 = 90.10%**.
This remains distinct from acceptance: only **2/12** SW-A–SW-L gates are locally
accepted (SW-B and SW-C). Tart/IPv6 containment, the creator sandbox lifecycle,
live VoiceOver/voice/privacy behavior, physical displays, provider trials and
blinded human review, target-Mac memory/paired-latency acceptance, creator
validation activity ownership, activation/rollback, and release handoff remain
open. The SW-K acceptance paragraph in the implementation plan now reflects the
final measured run. After that plan/status edit, the candidate fingerprint was
recomputed, all six local receipts and the no-launch release bundle were
refreshed against it, and
`scripts/verify_skills_workspace_release_evidence.py --root .` passes. This
proves candidate identity and local evidence binding only; Mac/VM/provider,
human-review, and deployment gates remain separate. No launch, install,
commit, push, or deployment was performed.

### 2026-09-28 parallel implementation follow-up

Three bounded audit lanes found and fixed additional local correctness gaps:

- **SW1:** catalog inspection now rejects declared resources that are missing,
  directories, unsafe/noncanonical paths, reserved package files, or file types
  that the bounded reader cannot serve. Regression coverage includes valid
  nested references and the rejection cases.
- **SW2:** authenticated runtime-inventory input now bounds runtime IDs to the
  expected UUID length and individual tool names to 128 characters, with API
  regression tests.
- **SW4:** if strict package inspection rejects missing or unsafe declared
  references, the offline-validation receipt now includes an explicit failed
  `declared_references` check as well as the broader schema failure.

Verification after those source changes: the full Python suite passes **3,534
tests, 4 skipped, 11 warnings, and 2 subtests**; combined catalog, authoring
validation, runtime-inventory, admin-catalog, agent-skill and resource tests
pass **122 tests**; the SW-B-focused loader/catalog/resource set passes **102**;
`python -m jarvis.agent_skills --validate` and `git diff --check` pass. The
three small hardening increments raise SW0–SW6 estimates to
**87/83/98/99/97/87/73%**, at unchanged weights **10/15/15/15/20/15/10%**.
Contributions are **8.70 + 12.45 + 14.70 + 14.85 + 19.40 + 13.05 + 7.30 =
90.45%**, reported as **90.5% implementation progress**. This is not gate or
release completion; only **2/12** acceptance gates remain verified.

The initial app-bundle attempts hit SwiftPM sandbox and user-cache restrictions.
Redirecting the module caches to `/private/tmp` allowed the no-launch release
bundle to build. `codesign --verify --deep --strict` passed. The six required
candidate-bound receipts were rebound to this candidate, and
`scripts/verify_skills_workspace_release_evidence.py --root .` passes. A fresh
public fixture receipt records **14/14** selection cases. This closes only
local evidence freshness and bundle-build verification; it does not close
runtime or release acceptance. No app launch, installation, commit, push,
deployment, VM, network, or provider action occurred. Tart remains unavailable;
live lifecycle, physical Mac, provider, VoiceOver and release gates remain
open.

The full native suites were rerun after the fixes: MortimerHost passes **346
tests with 9 skipped and 0 failures**; JarvisKit passes **212 tests with 0
failures**. Skips still require Screen Recording, a foreground-capable app, or
two connected displays. The rendered-navigation benchmark within the host suite
passes its local budgets, but hardware identity, paired voice latency, the
ten-minute memory soak, and physical display behavior remain unverified. The
candidate fingerprint and all candidate-bound receipts will be refreshed after
this status update.

### 2026-09-28 parallel SW0/SW2/SW5 follow-up

The SW0 contract audit aligned the `skill_id` fixture schema with the runtime's
reserved-name rule, rejecting vendor-reserved `claude` and `anthropic` names and
adding negative schema tests. The SW2 audit fixed a privacy race: the trusted
step-receipt writer now checks the durable run-wide protected marker inside its
SQLite write transaction, so a late receipt cannot repopulate a trace after a
protected-run scrub. The new interleaving regression confirms the receipt is
refused, no receipt row is stored, and the API returns only the generic marker.
SW5's provider-free integrity audit found no local defect; the 45 paired-review
and budget tests pass, and no provider route or call was used.

After these changes the full Python suite passes **3,537 tests, 4 skipped, 11
warnings, and 2 subtests**. The combined receipt/schema/catalog/authoring suite
passes **70 tests**; relevant Ruff `F,E9` checks, skill catalog validation, and
`git diff --check` pass. The weighted implementation estimate is now **90.7%**
with scores **88/84/98/99/97/87/73%**, unchanged weights **10/15/15/15/20/15/10%**,
and contributions **8.80 + 12.60 + 14.70 + 14.85 + 19.40 + 13.05 + 7.30 =
90.70%**. Only **2/12** acceptance gates are accepted. The source changes
invalidate candidate-bound receipt fingerprints; rebuild/rebind is required
after this status and plan update. Live acceptance and Tart remain open.

### 2026-09-28 SW3 compact repeated-navigation fix

The Skills compact library/detail flow now reacts to every valid shared
navigation request, including selecting the already selected skill, tab, run,
step, or example after returning to the library. Previously, unchanged store
selection state meant no observable update and the detail could stay hidden.
Accepted repeat requests now publish a separate navigation revision; invalid
targets do not. The focused Skills/action suites pass **71 tests** and the full
MortimerHost suite passes **347 tests, 9 skipped, 0 failures**. Nine skips still
require Screen Recording, a foreground-capable process, or two displays. Latest
store-only performance values are 0.0020 ms selection and 0.0182 ms cached
navigation p95 across 100 samples; this is not rendered or target-hardware
acceptance. SW-I keyboard/VoiceOver and SW-J physical-display acceptance remain
open. The weighted estimate stays **90.7%** (SW3 is already capped below 100%
because its live acceptance criteria remain open). Rebuild and rebind final
candidate evidence after this native source and status update.

### 2026-09-28 final local verification after SW3 fix

The no-launch production app bundle was rebuilt after the native fix and latest
documentation; strict ad-hoc signature verification passed. Candidate-bound
receipts were refreshed to this final fingerprint and the release-evidence
verifier passes. Current full-suite evidence is **3,537 Python passed, 4
skipped, 11 warnings, 2 subtests; 347 MortimerHost passed, 9 skipped, 0
failures; 212 JarvisKit passed, 0 failures**. The app remains unlaunched,
uninstalled, and undeployed. Nine native tests require Screen Recording, an
active foreground-capable app, or two connected displays. Only **2/12** gates
are accepted; all live and target-hardware acceptance remains open.

### 2026-09-28 SW2 and SW4 lifecycle hardening

The configured MCP inventory now fails closed for symlinked config/server roots,
server directories, and manifests. Runtime inventory remains bounded to
36-character runtime IDs, 256 tools, and 128 characters per tool. The trusted
step-receipt writer checks the durable protected-run marker within the SQLite
write transaction, preventing late receipts from restoring trace data after a
protected-run scrub.

Creator recovery now allows a publication retry after `publication_pending`
only when the current frozen candidate, session digest, and complete offline
creator receipt agree. Focused creator and sandbox-session tests pass **30
tests**. This is local regression coverage; real VM/restart and privacy
acceptance remain open. The weighted score and accepted-gate count are
unchanged; candidate evidence must be refreshed after the code and documentation
updates.

### 2026-09-28 final verification after SW2/SW4 hardening

Current local verification passes: Python **3,542 passed, 4 skipped, 11
warnings, and 2 subtests**; MortimerHost **347 passed, 9 skipped, 0 failures**;
JarvisKit **212 passed, 0 failures**. SW-B's focused loader/catalog/resource
suite passes **96 tests** and catalog validation succeeds. SW-C's public
selection fixtures pass **14/14 with zero provider calls**, and its focused
selection suite passes **106 tests**. SW-E privacy/display tests pass **41
tests with one Screen Recording-dependent skip**. Store-only navigation p95 is
**0.0077 ms** across 100 samples; this excludes rendering and network. The
100-skill runtime selector benchmark remains within its 20 ms p95 budget with
zero provider calls.

The no-launch production bundle was rebuilt for this candidate and passed
`codesign --verify --deep --strict`. All seven candidate-bound local receipts
were refreshed, and `scripts/verify_skills_workspace_release_evidence.py
--root .` passes. The weighted estimate remains **90.7%** using SW0–SW6 scores
**88/84/98/99/97/87/73%** and weights **10/15/15/15/20/15/10%**; only **2/12**
acceptance gates are accepted. This evidence does not close Tart isolation or
lifecycle, live provider trials and blinded review, VoiceOver, physical
displays, target-Mac voice latency/memory soak, activation/rollback, or release
handoff. The app remains unlaunched, uninstalled, and undeployed.

### 2026-09-28 Tart 2.39.0 trial and creator-run ownership decision

Tart 2.39.0 was installed side-by-side in the project sandbox tools directory.
The official release archive checksum matched GitHub's published digest, the
installed app passed strict code-signature verification, and `doctor` reports
Tart and the already-installed Softnet helper ready. The cached macOS image was
used; no large image download or helper reinstall was needed. A real disposable
VM completed preparation (locked Python dependencies, Node/npm packages, Swift
dependency resolution, Playwright Chromium, vault initialization, and KB setup).
The offline and provisioning probes confirmed the host/input boundary, host
canary integrity, resource limits, and expected public IPv4 behavior. They did
not observe a guest IPv6 default route, so IPv6 containment is **unverified**;
the probe records `acceptance_complete=false`. The VM was stopped and the exact
temporary trial tasks were destroyed; older user VMs and cached images were
left intact.

The supplied crash report is from macOS 27.0 and records SIGABRT in Tart's
macOS graphics-device startup through HIServices/AppKit application
registration, before a guest process starts. It is a host GUI/application-
registration failure, not a candidate or guest crash. The report is consistent
with the earlier restricted-launch failure; the authorized controller later
ran outside that restricted command context. The acceptance app check needs
graphics, so headless mode is not a replacement for this GUI run. This identifies
the failing startup stage, but does not establish IPv6 containment or complete
SW-F. During in-guest checks against
the frozen HEAD, one cancellation test exposed a sleep-based race and one
scroll assertion exposed floating-point precision. Both test defects were
corrected in the candidate and their focused native tests pass locally; those
candidate fixes have **not** yet been rerun in a Tart guest.

Creator activity ownership is now decided: all manual and voice skill creation
must route through a genuine `agent="developer"` run, and async creator work
must attach to that real Developer run. A Supervisor direct-tool run is not an
acceptable substitute. The durable sandbox request/job ID remains distinct
from the Developer `agent_runs.run_id`; neither the client nor the worker may
invent or reuse an identifier. The current native entry points call the authoring
API directly or originate in the Supervisor, and therefore cannot claim a
Developer run yet. Backend and UI integration are in progress; keep this gap
open until the backend creates/owns the actual Developer run, authenticates the
association, and the native and voice paths display that same returned run ID.
The parallel implementation audit found no safe existing dispatch bridge: the
admin sidecar owns the Skills HTTP route, while the live Developer SubAgent is
owned by a bot-session `build_delegate_tool`; the two have no dispatch/lookup
interface. The existing creator `UpgradeAgent` has sandbox correlation but no
Developer `agent_runs` row. No false ID or UI field was added. SW2/SW3/SW4 now
specify the required bot-owned dispatch boundary and owner-scoped ID contract;
implementation remains open until that bridge and the Developer-owned creator
tool are built and tested.

After the current local edits, the full Python suite passes **3,544 tests, 4
skipped, 11 warnings, and 2 subtests**. Focused Tart controller/probe/session
tests pass **53 tests and 7 subtests**; focused Swift regressions for the two
native test fixes pass. The latest full native results are MortimerHost **347
passed, 7 skipped** and JarvisKit **212 passed**; the current candidate's full
Swift suites and all refreshed release receipts must be rerun after integration.
The latest release-evidence receipts predate this turn's edits and are stale.
SW-B/SW-C are still the only accepted gates (**2/12**); the previously reported
90.7% implementation estimate is not recalculated here. No app launch,
installation, deployment, commit, or push occurred.

### 2026-09-28 follow-up: Tart crash diagnosis and native guest acceptance

The supplied Tart 2.39.0 crash report specifies macOS 27.0 build 26A428 on
Mac17,4. Tart aborts in `HIServices.___RegisterApplication_block_invoke` while
`GetCurrentProcess` is called from AppKit menu-bar setup during
`Darwin.graphicsDevice(vmConfig:)`; the guest has not started at that point.
This is a host GUI-registration failure, not a Mortimer test or guest failure.
The same installed Tart 2.39.0 later launched successfully through the
authorized host execution context. This workaround is validated for this host;
it does not establish compatibility in every restricted launch context.

The candidate fixes exposed by the first guest run are now validated. A fresh,
offline worker passed the visible-desktop probe and the full MortimerHost suite:
**347 passed, 7 skipped, 0 failures**. The candidate fingerprint is
`33d8161aa31f6012bb6ddbeeeb10aa5cfcf37abdcce84e189875add0a2facc2a`; the
source commit used for that task is `ba82b7602f9d12e3e8202c78b2e57b39c8e80f5f`.
The redacted test log, desktop probe log, and run summary are retained under
`docs/acceptance/skills-workspace/receipts/tart-2026-09-28/`. Local MortimerHost
also passes **347 tests, 7 skipped, 0 failures**. Its rendered-selection
benchmark enforces the existing physical-Mac budget and measured **18.39 ms
wide** and **7.02 ms compact** p95 for selection-to-layout.

The tests now mark commands executed by the Tart verification runner with
`MORTIMER_SANDBOX_GUEST=1`. The guest still runs native rendering,
accessibility, and navigation behavior tests, but it records rather than
enforces frame-time and bitmap-change thresholds that depend on physical GPU
and display behavior. The latest virtual-display run measured **29.27 ms wide**
and **16.33 ms compact** selection-to-layout, and the `NSHostingView` bitmap
hash stayed at one distinct frame even though the guest's accessibility and
functional UI suite passed. Those VM timing and bitmap values are diagnostic;
physical-Mac performance remains the authoritative gate. The latest native
guest suite passed only with this clearly recorded environment distinction;
the project does not relax those limits on a physical Mac.

This adds real Tart GUI/lifecycle and native-suite evidence, but does not close
SW-F: the prior IPv6 route/canary gap remains unverified, and no full signed
independent `Verifier.verify` receipt was created for this manual acceptance
run. SW-B and SW-C remain the only formally accepted gates (**2/12**). The
weighted estimate remains **90.7%** and is stale relative to these changes;
recompute it only after refreshing all candidate-bound local receipts. The
Developer-run creator bridge, integrated restart/recovery and publication
acceptance, live provider trials, VoiceOver, physical multi-display testing,
target-Mac voice soak, activation/rollback, and release handoff remain open.
No production app was installed or deployed, and no commit or push occurred.

### 2026-09-28 creator-dispatch audit and implementation boundary

The user confirmed the selected architecture: route creator work through a
real Developer-agent run. A fresh source audit confirms that the current
`skill_requests._run_draft()` still starts the sandbox and calls the pinned
creator `UpgradeAgent` directly, so it does not create a Developer
`agent_runs` row. It also overloads the public request UUID as the sandbox
run ID. The existing genuine path is `build_delegate_tool()` in the bot
session, which owns the Developer `SubAgent`, event lifecycle, run ID, and
late-delivery bookkeeping. The admin Skills API runs in a separate process
and has no authenticated lookup/dispatch bridge to that bot-owned runtime.

Implementation must use one bot-owned dispatch path for manual and voice
requests. The dispatcher must bind the authenticated owner and live bot
session, let the Developer `SubAgent`/`RunLogger` create the actual run
identity, and durably associate it with separate idempotency/request,
sandbox job, sandbox session, and VM task identities before creator tools can
start work. The Developer run must receive only the bounded creator capability
for that request; it must not inherit broad authoring tools or create an
unrelated generic Developer run before invoking the current `UpgradeAgent`.
Keep the existing creator VM as the authoring boundary, and keep validation
results attached to the originating Developer run without changing that run's
terminal status. Manual and voice activity must display the same returned
Developer run ID and a separate creator-job lifecycle.

This increment adds the first owner/session plumbing: bearer middleware now
places the verified user in a request-scoped tenant context that propagates to
async child tasks, and `RunLogger` reads that owner instead of falling back to
the process-wide user setting. Live Skills runtime receipts now carry that
owner, and the draft API requires the active console session ID and rejects
missing, stale, or differently owned runtime receipts. The native creator
composer supplies its current console session and refuses to start while
disconnected. Focused auth/tenant/runtime/request tests pass **73 tests**;
the focused JarvisKit test could not run because SwiftPM's `sandbox-exec`
failed with `Operation not permitted` in this restricted launch context.

This does not yet implement the Developer dispatch bridge. The current direct
creator path remains open until the bot-owned dispatcher, bounded
Developer-run creator tool, durable request/run/job association, retry and
cancellation reconciliation, and native/voice activity linkage are
implemented and covered by cross-process tests. The plan's identity rules
remain authoritative; no fake run ID or fallback owner was introduced.

### 2026-09-28 follow-up: sandbox identity separation

The draft request now persists a generated `sandbox_job_id` distinct from
both the request UUID and the live bot `bot_session_id`; the resulting
`sandbox_session_id` and `sandbox_task_id` remain their own receipts. Draft lifecycle,
cancellation, candidate status, offline validation, and publication
reconciliation compare against the sandbox job identity. Publish/test records
retain the parent request ID separately from the parent sandbox job ID. Focused
request, runtime-inventory, tenant-context, and auth-middleware tests pass
**73 tests**; Python compilation and import-order checks pass. This closes an
identity collision in the current host API path, but it does not create the
Developer `agent_runs.run_id` or implement the bot-owned dispatch bridge, so
the creator integration gate remains open.

The newly supplied Tart report matches the earlier startup failure: SIGABRT
occurs in AppKit/HIServices while Tart initializes its host graphics device,
before the guest starts. A matching Codex issue documents this class of
AppKit registration failure in sandbox-launched macOS GUI applications
(https://github.com/openai/codex/issues/30043). The later authorized Tart
launch from the host execution context and guest acceptance recorded above
show the workaround succeeded on this machine; the crash report itself is
not evidence of a guest or Mortimer failure and does not close IPv6
containment or independent-verifier gates.

### 2026-09-28 Developer-run creator bridge follow-up

The selected bridge now routes manual and voice creator work through the
Developer `SubAgent` owned by the live bot session. Its `RunLogger` creates
the real run ID; the admin service durably associates that ID to the owner,
bot session, creator request, and separate sandbox job before the bounded
creator tools can run. The bot endpoint admits only the authenticated
`service-bot` identity and checks the live session owner. The dispatch scope
restores the verified human owner while the Developer run is created, so the
internal service identity is not recorded as run owner. Creator lifecycle
events forwarded to the console retain only bounded run/tool/status metadata;
the brief, tool arguments, file contents, and results are removed. The native
creator status view labels the Developer run ID separately from the sandbox
job ID. Existing cancellation still targets the exact request/session/run
tuple and waits for terminal cancellation evidence.

Regression coverage now exercises human-owner context propagation, creator
event redaction, authenticated route coverage, request identity schema,
cross-session ownership checks, and the real `SubAgent` run-ID/tool-scope
boundary. Focused integration/auth/request checks passed **271 tests**; the
full Python suite passed **3,554 tests, 4 skipped, 11 warnings, and 2
subtests**. `git diff --check`, Python compilation, and standalone Swift
syntax parsing of `SkillCreatorSheet.swift` passed. A fresh SwiftPM test build
could not run because the host denies its `sandbox-exec` operation; the native
change therefore remains compile/render-unverified here. This local bridge
increment supersedes the earlier statements above that the dispatch bridge
had not yet been implemented. Cross-process live bot/admin/VM acceptance,
voice authoring, validation activity attachment to the originating Developer
run, VoiceOver, physical Mac/display acceptance, and release evidence remain
open; no package was enabled, deployed, committed, or pushed.

The 2026-09-28 Tart report again shows Tart 2.39.0 aborting in
`HIServices._RegisterApplication` during AppKit graphics-device initialization
under the `com.openai.codex` coalition. This matches the sandboxed GUI-process
launch failure documented in Codex issue 30043. The report contains no
unified-log denial detail, so the specific denied service is not independently
proven from this report; it does establish that this launch failed before
guest startup. It does not invalidate the separately recorded successful
authorized Tart acceptance run.

### 2026-09-28 integrated creator transport verification

The next source audit found that the previous checkpoint overstated bridge
coverage: the endpoint supplied an unsupported `event_filter` keyword to the
session dispatcher, and the delegate treated the filter as the listener instead
of forwarding its result. Those would prevent real dispatch and visible
activity despite the earlier passing isolated tests. Both defects are fixed.
The registry now carries the live session's privacy holder into the service
request, alongside its authenticated human owner. An absent or protected
session refuses before provider execution. The creator emits ordinary
`delegate_start`/`delegate_done` lifecycle messages only after actual durable
run association; the native transport retains the real run ID on completion
and tool progress. The selected pinned creator revision is recorded on that
real run, making it visible through the existing Skills Activity query.

The scoped Developer run no longer automatically selects unrelated skills,
adds a reference-read tool, or injects unbounded procedure/workflow context.
It uses the same bounded creator-specific reuse/workflow/procedure context as
the previous authoring adapter. Tool responses are unwrapped from the HTTP
envelope so a failed sandbox tool remains failed in the run log and interface.
The bot and admin services must agree on the pinned creator revision; the
association stores that revision. A durable request lock permits only one
Developer run to claim a request and rejects cancellation or a changed run.
The authoring service checks the expected sandbox job when resolving the actual
session for reads, writes, and validation, closing the race between a status
check and a newer session replacing the same skill's job.

`tests/integration/test_creator_dispatch_bridge.py` exercises both authenticated
HTTP handlers, real session dispatch, actual Developer/RunLogger execution,
durable admin association, scoped tool calls, Skills Activity queries, and the
native message adapter. Model completion and sandbox operations are fakes.
Coverage includes exact-run cancellation, protected/missing/cross-owner
contexts, failed-tool verdicts, forbidden ambient tools, private payload
exclusion, and consistent run IDs at the native transport boundary. The expanded
bridge/request/authoring/event/bot/delegate/agent regression set passes **299
tests**. These are process-boundary
contract tests in one test process, not a live multi-process or real-VM run.

The previously blocked native build was retried through approved host execution.
SwiftPM compiled the current source: **29 AgentRunStore and SkillsWorkspaceRendering
tests passed**, followed by **31 JarvisKit AppMessage tests**. The native decoder
and store now match tool activity and completion to the exact run ID; tests with
concurrent Developer cards confirm that completing one leaves the other running.
An unknown run ID cannot update an unidentified legacy card. This supersedes the
preceding compile/render-unverified note for the current source; it is not live
display or VoiceOver acceptance.

The full Python suite passes **3,564 tests, 4 skipped, 11 warnings, and 2
subtests**. A subscription cancellation test exposed a readiness-file race in
its fake process; the fixture now publishes the completed PID file atomically,
and all 31 subscription tests plus the full suite pass. Runtime subscription
behavior was not changed. Python compilation and `git diff --check` also pass. Late
validation still requires a host-recorded `offline-validate` attempt and
candidate-bound evidence on the originating Developer run; no step pass is
fabricated from model prose or attached after the fact without that attempt.
Live bot/admin/VM authoring, restart/recovery, voice, VoiceOver, physical display,
provider evaluation/review, activation/rollback and release gates remain open.
No deployment, activation, commit, or push was performed.

### 2026-09-28 asynchronous validation ownership foundation

Offline test requests now snapshot the originating Developer run and pinned
creator revision from the owner-scoped parent draft. Client-supplied association
fields are ignored. Replaying a request preserves its original association;
missing, legacy, cross-owner, and different-skill parent associations are not
invented. Before invoking the validator, the worker durably records a unique
validation attempt ID and start time alongside its pre-validation baseline.
These request-ledger fields are not yet a Skills Activity event or a passed step.

The validation service now carries the expected sandbox job through actual
session resolution, closing a mutation race left by checking status only before
and after validation. A regression using the actual authoring service with a
fake runtime replaces the job immediately after the baseline read: the old
worker reports reconciliation needed and leaves the new job in its editing
phase. Worker restart coverage also verifies that the attempt exists before
validation and remains unchanged when the completed request is reconciled.

Verification: **80 request, authoring-service, and creator-bridge tests pass**;
`git diff --check` passes. The preceding 3,564-test full-suite result predates
this increment. No runtime deployment was performed.

Still open: publish the recorded attempt and independently verified result to
the originating run's Skills Activity, with transactional sequence allocation,
privacy checks, idempotent late receipts, cancellation and restart handling.
Preserve the terminal Developer row. Do not instantiate another RunLogger to
impersonate the original run or backfill an attempt for an old receipt. Live
multi-process/VM and remaining acceptance gates are unchanged.

### 2026-09-28 activity ordering for independent validation writers

Skill-event allocation now reads the durable per-owner/per-run maximum inside
the existing SQLite write transaction. Normal activity, trusted check receipts,
and privacy scrubbing all use that ordering. The live logger advances its local
counter to match; generic agent-event ordering remains unchanged. Before
scrubbing traces, the privacy marker reserves a sequence above all existing
activity so a client already at the previous cursor can receive the marker.

Regression evidence covers 16 independent writes through four concurrent
connections, a subsequent live-logger append, and privacy scrubbing after a
durable cursor has advanced beyond the logger's local counter. **77 runlog,
step-check, cursor-edge, and admin activity tests pass**. This provides the
transactional ordering prerequisite; it does not yet connect the async
validation worker to Skills Activity or accept a late terminal-run receipt.
No deployment or acceptance-gate closure is claimed.

### 2026-09-28 validation evidence consistency correction

While preparing late Activity receipts, source inspection found that restart
recovery trusted `SkillAuthoringService.status()` to verify complete package
evidence, but status previously checked only the receipt kind, slug, passed
flag and candidate digest. Unlike publication preflight, it could expose a
package revision despite missing checks, failed checks or provider use.

Status now uses the complete offline receipt validator, verifies the frozen
candidate fingerprint, and requires the resolved session to match both the
observed run and any expected job binding. The worker also requires its returned
validation result to agree with durable validated status, candidate digest and
package revision before marking the test request completed. A successful return
value alone is insufficient.

Verification: **91 authoring, request, publication-recovery and bridge tests
pass**, including malformed receipts and four contradictory durable-result
cases. `git diff --check` passes. This closes an evidence-validation defect;
late Skills Activity insertion and terminal-run receipt acceptance remain open.
No deployment or acceptance-gate closure was performed.

### 2026-09-28 completed-run validation activity

The asynchronous worker now records `offline-validate` activity on the real
originating Developer run before calling the validator. Completion appends a
signed host-check receipt to that same run without updating its terminal row.
The exact pinned creator step is mapped to a host-owned checker that re-reads
the owner-scoped request, parent association and complete candidate evidence.
The saved sandbox receipt now binds the validation request, attempt and sandbox
job, so a receipt for the same candidate from another validation cannot stand
in for the owning attempt.

`jarvis/skill_validation_activity.py` holds the durable request lock while
checking cancellation and appending evidence. SQLite rechecks ownership,
Developer identity, selected creator revision, recorded attempt, privacy and
event limits in the write transaction. Receipt replay is idempotent. Failed or
cancelled attempts get truthful non-passing terminal activity. Recovery can
append a verified result for an already recorded attempt; it never fabricates
a missing started event or runs the validator again. Legacy requests without
an association/attempt remain without a fabricated Skills trace.

Verification: the new suite passes **12 tests** using actual request storage,
RunLogger, SQLite, the authoring service and offline candidate validator with
a fake sandbox runtime. It covers completed-run attachment, unchanged original
run rows, repeated reconciliation, restart recovery without rerunning the
validator, missing attempts, wrong owner/run/pin/request/attempt, cancellation,
privacy scrubbing, malformed evidence, and failed validation. The focused
request/authoring/activity suites passed 86 tests before the last two identity
regressions were added. Scoped Ruff and `git diff --check` pass. The full Python
suite passes **3,587 tests, 4 skipped, 11 warnings, and 2 subtests** in 110.56
seconds; the final two identity cases were additionally verified by the
12-test activity suite.

This is local implementation evidence, not live bot/admin/VM acceptance. No
deployment, activation, commit or push occurred. The broader voice,
accessibility, physical-display, real-VM, provider/evaluation, release and
rollback gates remain open; the plan is not complete.

### 2026-09-28 independent verifier run started

Rechecked the configured Tart home and live host processes: no prior acceptance
VM was running, and the prepared Mortimer image remained available. The first
attempt stopped before VM launch because the historical source commit
`977f50bec7b77bd7d3381d3b8f3d63fa69bd00e2` failed the existing credential-shaped
fixture guard at `tests/unit/test_memory.py`. No guard was relaxed.

The current candidate passed all source path, size and credential checks. An
inert local Git snapshot of those 1,291 validated files was created at
`/private/tmp/mortimer-independent-20260928/source-snapshot`, commit
`4202d0475a97f9bfc1017cc942914a6622a53630`, candidate fingerprint
`427157652bb01208624134fed8c945057dd60bc1ce1df17316945346374eed87`.
The authorized independent `Verifier.verify` pipeline was started against that
snapshot using the installed Mortimer profile. Development task `7462cadbe69e`
was observed running and awaiting hydration. The live shell session is `8955`;
poll that handle before restarting anything. Driver output and durable run
summary are under `/private/tmp/mortimer-independent-20260928/`.

This run can establish independent candidate execution. Its baseline is the
validated candidate snapshot, so it cannot close historical-HEAD regression
acceptance. The earlier failed task is `3fcc9e240d55`; the running process uses
the later snapshot attempt. No passing verifier result, IPv6 containment,
deployment or overall acceptance is claimed at this checkpoint.

### 2026-09-28 independent verifier result and late-activity UI correction

The snapshot run completed: **all 12 configured verifier checks passed**, the
guest desktop probe passed, and the final source capture matched the candidate.
The final receipt and every check log are saved under
`receipts/independent-2026-09-28/`; each saved log hash was verified against the
receipt. Both backend suites passed **3,430 tests**. Both native-library suites
ran **212 tests with zero failures**; the native app ran **349 tests with 7
skipped and zero failures**. The stopped disposable development and verification
VMs were destroyed after preserving their host records and evidence.

This is a successful independent execution of snapshot `4202d0475a97f9bfc1017cc942914a6622a53630`
with candidate `427157652bb01208624134fed8c945057dd60bc1ce1df17316945346374eed87`.
It is not acceptance of all 12 SW gates and does not prove historical-HEAD
regression, IPv6 containment, physical-display behavior, or live provider/voice
operation. The later source changes below are not part of that snapshot.

Following the deferred validation result into the native view found that its
refresh loop stopped when the Developer run completed. The creator Activity
view now keeps refreshing at five seconds while active, fifteen when inactive;
live runs retain the one/five-second cadence. Other completed skill views still
settle. SwiftUI task cancellation still owns tab, selection and window lifetime.
This lets validation that starts after Developer completion become visible.
The corrected view compiled and passed **30 native policy/rendering tests** on
the host. It still requires a fresh frozen-candidate run and live acceptance.

The historical source refusal was traced to three synthetic credential-shaped
literals identical to the already-reviewed current memory-test fixture. Added
only its exact historical path/hash to `REVIEWED_BASELINE_TEST_FIXTURES`, retaining
the existing current-fixture checks. Changed bytes and copied/moved files remain
rejected. **129 sandbox tests plus 45 subtests passed**, and the original
`977f50bec7b77bd7d3381d3b8f3d63fa69bd00e2` baseline exported and decoded successfully
(1,073 files). This fixes baseline import; it does not yet prove its regression
suite passes against the current candidate. A new independent run is required.

Hardware is now observed as MacBook Air `Mac17,4`, Apple M5, 16 GB RAM. Only the
built-in display was reported; the external-monitor question remains pending.
No app deployment, skill activation, repository commit or push was performed.

### 2026-09-28 historical-baseline retry and evaluation preflight

The user's confirmed ownership decision remains authoritative: both manual and
voice creator work goes through a real Developer SubAgent run, and async
validation attaches to that originating run. The plan's SW4 dispatch contract
and implementation already reflect it; this does not authorize simulated or
Supervisor-owned Developer activity.

Historical run `87d3b93450da` stopped during hydration. Replaying capture locally
against its exact saved candidate and baseline reproduced precisely four missing
files, all untracked root `.build/` Swift cache markers. There were no unexpected
or changed files. Removing those generated files produced an exact fingerprint
match. Added `/.build/` to `.gitignore`; all four markers are now excluded from
source collection. No guest capture or credential guard was weakened.

A fresh run uses historical HEAD `977f50bec7b77bd7d3381d3b8f3d63fa69bd00e2`
and candidate `c21e7e1b03e5473dd7040cdce9b6edb558168d2d6130bd604722499d7656443e`
(1,287 files). Development task `1de0c2036283` and independent verification task
`cfc9d29a9b34` both passed hydration. The actual guest desktop probe passed in
28.201 seconds; `backend-imports` passed. Remaining profile checks are running.
Attempt: `0328283849e54dcda669b7309184f2f9`. Driver and summary:
`/private/tmp/mortimer-historical-clean-20260928/`; live shell session `12483`.
Poll that session before starting another run. This paragraph is a checkpoint,
not a passing final receipt, and these subsequent documentation changes are not
part of that frozen candidate.

SW-G preflight used a separate private temporary configuration and the installed
creator revision `9ec4a15fc4b4854dfdab5ce1ea74bacde27064d1ba5cb8bf51c6b88a3000927b`.
Claude Max authentication and CLI restricted/no-tool flags are available, but the
existing subscription adapter cannot enforce the evaluation output-token cap.
The evaluator correctly rejected it before the provider boundary; a dry run with
a provider sentinel reproduced that failure without sending a prompt. No live
routing was changed and no evaluation API calls were made. Asked whether to use
the configured Sonnet API route for this test only, 24 calls with a $1.25 modeled
spend ceiling; the repository price map reserves $1.061136 conservatively for
these exact fixture inputs and 4,000 output tokens per call. Actual billing may
differ. Approval remains pending; do not reroute to paid API based on elapsed
time. Live evaluation and independent blinded ratings remain open.

### 2026-09-28 IPv6 filter audit correction

The installed trusted helper reports `softnet 0.23.0-e5fd48c` and its SHA-256
matches the binary inside the official 0.23.0 release archive exactly. The
archive also matches GitHub's release asset digest. Pinned source inspection
found that `allowed_from_vm` and `allowed_from_host` accept only ARP/IPv4 Ethernet
protocols; all other protocols are rejected before forwarding. IPv6 therefore
has an existing protocol-level deny in this source. The earlier conclusion
that an additional filtering layer is necessarily required was too strong:
IPv4-only CIDR syntax does not imply that IPv6 is forwarded.

Evidence: `receipts/softnet-023-source-audit-20260928.json`, including installed/
release binary hashes, source file hashes and primary-source URLs. This is
source/binary-identity evidence, not a live target-VM canary. SW-F remains open.
Next validate the existing protocol filter with known-working-path IPv6 canaries
in both provisioning and offline modes; do not weaken this requirement or
invent an unsupported IPv6 CIDR argument. No helper or host network settings
were changed during this audit.

Live IPv6 probe preparation: `/private/tmp/mortimer-ipv6-live-20260928/probe.py`
is syntax-checked and its read-only preflight resolves the prepared image and
installed helper. It has not run. It refuses to start while any VM is running
and holds the sandbox start lock. It uses a fresh disposable trusted-image
clone with no host mounts or candidate import, proves a synthetic host-bridge
IPv6 UDP path before/after the filtered modes, then checks provisioning and
offline blocking. A failed positive control cannot pass containment. This
control path is test-only, never a development networking fallback. Run it
only after verification session `12483` is terminal and Tart reports no running
VM; preserve its receipt and inspect it before closing any gate.

Historical verifier checkpoint: `baseline-backend` passed in 309.608 seconds;
the candidate backend is running. Session `12483` was polled and confirmed live.
Source-tag API verification also bound the helper source audit to commit
`e5fd48cf033ed0ec376710607187d761e60c2374`, matching the installed version suffix.

### 2026-09-28 historical verifier completed

Session `12483` finished. All twelve stages ran; eleven passed. The candidate
passed its backend (3,430 tests), native library (212 tests, zero failures),
native app (351 tests, 7 skipped, zero failures), web, imports, and other
configured checks. The historical backend passed 2,684 tests; historical native
library passed 199. Final candidate capture matched the frozen fingerprint.

The historical native-app suite failed one test out of 256 (3 skipped):
`SupportingDisplayAcceptanceTests.testReturningToOriginalPanelsPreservesResearchPinsAndReadingState`,
line 192, compared `239.99999999999994` with `240.0` using exact equality. The
candidate already uses a 0.001-point tolerance and passed this test. This is a
confirmed historical assertion failure, not evidence of a candidate behavior
regression. No old test was changed or skipped to conceal it. The verifier's
actual final result is **failed**; publication stays denied by that receipt.

All twelve stage logs, desktop probe log, exact final receipt, driver summary,
and extracted test counts are preserved under `receipts/historical-2026-09-28/`.
Each copied check/probe log SHA-256 was compared with the receipt before copying.
The development and verification VMs stopped normally; they remain available
for diagnosis. Do not rerun the entire profile merely to chase a green baseline.
A baseline correction/disposition must be explicit before release acceptance.

The separate live IPv6 control/provisioning/offline/control test has started in
session `79912`, using `/private/tmp/mortimer-ipv6-live-20260928/probe.py`.
Poll that handle and read its final receipt before making any containment claim.
It runs only trusted prepared-image code with synthetic canaries, with no source
or host mounts; no app deployment or live routing changes were made.

### 2026-09-28 IPv6 positive control did not establish connectivity

Session `79912` is terminal (exit 1). In the unfiltered control phase the guest
observed its IPv6 target route and sent the synthetic UDP datagram, but the host
listener received nothing and the guest got no reply. The harness correctly
stopped before either filtered mode; no IPv6 containment pass is claimed.
The disposable VM was stopped and deleted. Exact driver, receipt and logs are
saved in `receipts/ipv6-control-2026-09-28/`.

The unresolved issue is now a failed positive-control path, rather than lack
of evidence about the installed helper's source policy. Before another
containment attempt, diagnose guest/host bridge selection and compare an IPv4
control on the same synthetic endpoint. Do not rerun unchanged, change host
network settings speculatively, or interpret a route-table entry as proof of
working IPv6 delivery. Both pending user questions (physical monitor and
bounded API evaluation) remain unanswered.
