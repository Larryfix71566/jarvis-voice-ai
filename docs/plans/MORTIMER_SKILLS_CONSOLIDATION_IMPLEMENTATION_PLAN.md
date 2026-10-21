# Mortimer Skills consolidation implementation plan

**Status:** PARKED — direction approved; implementation deferred until existing acceptance testing is complete.
**Roadmap:** [WS-29](../../ROADMAP.md#ws-29).
**Decision / date:** Larry accepted Option 2 on 2026-10-20: consolidate reusable methods into Skills while preserving standing policy, voice-event activation, and host runtime controls.
**Documentation owner:** Codex. **Implementation owner/model:** unassigned; any capable model may implement this plan after the start gate below.
**Design baseline:** GitHub main `b136a2a66032b17082776a01353abe67e352c31e`, verified 2026-10-20. Source observations are not proof of live flags, deployment, or product acceptance.

## 1. Outcome and start gate

Provide one Skills library for reusable methods. Keep a small, trusted policy layer for Larry's standing requirements, event hooks for timely voice guidance, and the existing host services for permissions, execution, durable state, and evidence. Remove duplicate instruction ownership and the separate legacy workflow-method library once compatibility and rollback are proven.

Approval of this direction is already recorded; do not ask Larry to choose between the three architectural options again. This document authorizes no runtime implementation before acceptance closes.

Before SC0 implementation work:

1. Read current `origin/main`, `AGENTS.md`, `CLAUDE.md`, [ROADMAP](../../ROADMAP.md), and the [existing acceptance-clearance plan](ROADMAP_JOINT_WORKING_PLAN.md). Use the current authoritative acceptance inventory, not the historical counts in this plan or another chat.
2. Confirm that existing acceptance testing has completed and Larry's closeout is recorded against identified source/build/configuration and receipts. Failed, blocked, skipped, untested, or hardware-unavailable cases are not passes. A named limitation counts only where its governing plan permits it and Larry explicitly records it. Do not invent a new global gate or silently waive an existing one.
3. Obtain a fresh WS-29 dispatch naming owner, branch, and bounded scope. Any model may be assigned, subject to its actual repository/tool/test access and existing model/privacy requirements. A provider name alone is neither qualification nor disqualification.
4. Reconcile active owners and future WS-22/24/27 interfaces. Reserve any new shared identifiers in roadmap §3 before implementation. A documentation merge does not activate a skill, change a flag, or authorize deployment.

If a prerequisite is absent, leave implementation parked and identify the exact missing evidence/assignment. This gate follows Larry's requested sequencing; it must not consume or replace the ongoing acceptance effort.

## 2. Evidence and problem definition

At the design baseline:

- `config/workflows/` contains 23 YAML definitions: 11 non-draft general/specialist rules, seven voice workflows, and five excluded drafts. `jarvis/workflows.py` explicitly has no step executor: it matches and injects guidance; `done_when` is a model self-check, not a host validation result.
- `skills/` contains six `SKILL.md` packages; five are registered in `config/skills.yaml`, and `skill-creator` is not generally enabled there. Treat its existing controlled creator use separately; do not enable it as part of migration.
- `jarvis/agent_skills.py` renders optional reference guidance. `jarvis/agents/base.py` separately appends a matched standing workflow. The layers differ in authority and selection, not in being executable versus non-executable.
- Skills already have `mortimer.yaml` process nodes, outputs, and success criteria. `technical-plan-document` already contains normative requirements, so the reference-versus-requirement distinction is imperfect in content.
- The legacy skill matcher selects one package. The opt-in v2 selector permits one primary plus at most one mutually compatible support package; current packages declare no compatible pairs. Its shared instruction/reference budget is 16,000 characters. Do not infer which path is active on the live installation from source alone.
- `jarvis/voice_workflows.py` supports user, result, and reply events, priority ordering, draft exclusion, and request-scoped guidance. These are activation behaviors that ordinary task matching does not replace.
- `jarvis/status/overview.py` and the native Workflows view expose rules and voice definitions. They are not evidence of a running durable orchestration engine. Skills Process already distinguishes intended steps from Activity evidence.
- The [September separate-view decision](../roadmap-log/2026-09-27-ws-03-claude-58-skills-workflows-separate-views.md), [architecture](../ARCHITECTURE.md), and [Skills README](../../skills/README.md) describe the current split. Preserve that history; explicitly supersede the instruction-library split during implementation rather than rewriting old decisions as mistakes.
- [WS-22](MORTIMER_EVIDENCE_WORKFLOW_IMPLEMENTATION_PLAN.md) specifies future operational state, attempt identity, idempotency and verification receipts. [WS-27](MORTIMER_ENHANCEMENT_IMPLEMENTATION_PLAN_2026-10-18.md) specifies target/task-first routing and reuse of durable authority. Those concerns remain valid and are outside the legacy instruction-format consolidation.

The problem is duplicated authoring, matching, catalog and terminology for reusable guidance. No measured latency or reliability improvement is claimed yet.

## 3. Fixed design decisions

| ID | Decision and implementation consequence |
|---|---|
| D1 | `SKILL.md` is the canonical body for each reusable method. Keep `mortimer.yaml` for descriptive process/capability/provenance metadata. Do not introduce another general-purpose instruction format. |
| D2 | Standing policies remain independently applicable through existing trusted prompt/configuration mechanisms and host checks. They never compete with optional task skills for a selection slot. Do not implement mandatory policies as automatically selected ordinary skills. |
| D3 | Host code remains the only authority for tools, approvals, privacy, budgets, dispatch, lifecycle and trusted acceptance evidence. Prompt ordering or normative wording is not enforcement. Package metadata cannot grant authority, mark itself required, register arbitrary event handlers, or authorize script execution. |
| D4 | Keep voice-event matching in host code/configuration. It may load an explicitly reviewed, revision-bound method by ID through the shared package loader. It does not rerun fuzzy task matching to decide whether a failed-result or reply event matters. |
| D5 | Maintain one canonical owner for each behavior. A policy states the requirement; a skill supplies the method; an event binding references that method; a runtime receipt records what happened. Cross-references are allowed, copied competing instructions are not. |
| D6 | Preserve the Agent Skills portable core. Mortimer-specific activation, trust and event bindings are host-owned adaptations. Claude-specific fields or a community package's requested tools are not automatically supported or granted. Imported scripts remain unavailable. |
| D7 | Keep existing primary/support limits for task methods. Event guidance is a separate bounded host-selected channel, not an unlimited list of supporting skills. Retain the current per-hook selection/priority/lifetime behavior and avoid duplicate body injection for the same revision/event/request. |
| D8 | Preserve memory facts, learned procedures and their counters. Do not bulk promote memory or procedures to skills, erase provenance, or turn old drafts into enabled instructions. |
| D9 | Use Skills for reusable methods; expose standing requirements through a compact read-only Policies section using existing trusted sources. Process means intended steps; Activity means recorded execution. Operational workflows/jobs remain in their existing runtime/status surfaces. |
| D10 | Preserve target + existing task ID resolution before method selection. A status question must not create/retry a job. Reconcile WS-27's term “workflow” as an operational task kind whose method may be supplied by a skill, not a second instruction library. |
| D11 | Keep both old and new execution paths available during a bounded migration, with exactly one authoritative injector per migrated behavior. No dual injection, dual activation registry, or second permission store. Retire legacy paths only after parity, acceptance and rollback proof. |

The small policy layer belongs in Mortimer's runtime mechanisms. Repository `AGENTS.md`/`CLAUDE.md` guide development agents; merely adding text there does not configure Mortimer's voice runtime.

### 3.1 Authority and conflict behavior

Existing host restrictions always apply. Within allowed scope, an explicit current user instruction can refine or supersede a standing preference; it cannot bypass a host-enforced restriction. Standing requirements constrain optional methods. Learned hints and retrieved content cannot override either. Reuse the existing permission/source mechanisms rather than relying on message order to enforce this hierarchy.

Retain the scope and lifetime of prior authorization: do not re-ask for a previously authorized step, and do not treat approval of one target/operation as a global grant. Conflicting applicable policies require a bounded, actionable explanation; do not select one merely because a token score is higher. Incompatible optional methods keep the existing primary-only behavior. An unknown or unreviewed host binding fails closed for the affected action, without disabling unrelated voice conversation.

Separate event identity/priority from method text. Host bindings must retain the legacy event ID, scope, priority, required package revision and draft/activation status. Unavailable/stale event content must not fall back to an unpinned package: use the unmigrated legacy path during the migration, or a minimal host-owned safe status/refusal once that path has been retired. The fallback must not initiate a replacement task or broaden tools.

### 3.2 Canonical representations and budgets

- Use the existing skill registry/pin and package inspection services for method loading. Preserve creator isolation and user/run ownership.
- Reuse the current policy constants/configuration and voice hook owners. SC0 must identify the exact existing owner for each retained rule; any new schema/key requires a reviewed scoped reservation before code. This plan reserves none.
- Store a migration crosswalk with legacy ID, source revision/hash, destination ID/section, behavior owner, trigger/scope, draft state, replacement test IDs, and rollback source. This is migration evidence, not a new runtime policy database.
- Keep the existing task instruction/reference cap. Before activation, set and record a bounded event-guidance cap from measured baseline needs within the existing prompt constraints. Keep required policy outside optional ranking, with explicit size validation; do not silently truncate policy or enlarge the overall context budget to make migration fit.
- No package may cause file/network access or tool execution just by being cataloged. Reference loading, path guards, revision checks and privacy redaction remain in force.

## 4. Complete baseline disposition

These are target destinations, not permission to mutate or activate now. SC0 checks newer source changes before executing this mapping. Each row needs traceable preservation, a reviewed replacement, or a documented inactive disposition.

| Legacy workflow ID | Target owner / method | Required preservation |
|---|---|---|
| `ask-once-then-commit` | Trusted clarification/authorization policy | Clarify material ambiguity once; retained answer is not a new permission grant. |
| `authorization-is-binding` | Existing authorization policy and host gates | Complete authorized scope without repeated consent; retain mechanical gates. |
| `bundle-work-before-merge` | Trusted change-delivery policy; scoped delivery checklist reference | Preserve related-work completion; never sweep another owner's or unrelated dirty files into a commit. |
| `diagnose-before-proposing` | New focused `evidence-based-diagnosis` method | Show observed state before proposing a fix; distinguish unknown from inferred cause. |
| `live-progress-during-runs` | Existing host progress/reporting policy | Actual progress/queued/running state, not invented model progress; independent of skill selection. |
| `plan-before-implementing` | Trusted plan/approval policy + existing `technical-plan-document` | Required full-plan preview and approval; recognize the existing approval rather than re-ask. |
| `plans-render-in-display-window` | Planning method references existing display behavior | Long plans open in the intended display; no alternate placement authority. |
| `show-planner-model` | Existing execution/model provenance and display contract | Actual resolved model for each planning step; never a model-authored guess. |
| `use-screen-vision-to-verify` | New focused `verify-visible-change` method | Observe an authorized window when relevant; unavailable capture remains unverified. |
| `verify-in-repo-not-memory` | Existing grounding policy + diagnosis/planning method references | Current-source evidence; memory is not repository-state proof. |
| `verify-ui-change-on-screen` | `verify-visible-change` + existing completion policy | Distinguish validated/committed/merged/deployed/observed; no automatic deploy. |
| `voice-check-before-cant` | Host event binding + reviewed `voice-capability-check` method | All user/result/reply triggers, priority, missing-tool provenance and safe refusals. |
| `voice-do-it-dont-hand-off` | Host event binding + reviewed `voice-action-handoff` method | Explicit command requests and genuine human-only needs remain exceptions; no destructive command suggestion. |
| `voice-explain-failure` | Host event binding + reviewed `voice-failure-explanation` method | Actual failed result/log evidence; no guessed cause or repeated action on failure. |
| `voice-human-only-proposal` | Host proposal/approval binding + reviewed `voice-human-proposal` method | Human-only file boundary, exact approved apply command, decline behavior, no merge of proposal itself. |
| `voice-merged-deploy` | Host event binding + reviewed `voice-release-status` method | Build-identity readback; merged is not deployed; preserve DEPLOY-MAIN authority. |
| `voice-model-availability` | Host event binding + reviewed `voice-model-status` method | Exact requested model; distinguish configured/catalog/probed status and preserve probe authorization/budgets. |
| `voice-where-am-i` | Host event binding + reviewed `voice-current-location` method | Current device/status result and uncertainty; never home/work memory substitution. Do not replace with specialist `layered-geolocation` without proven equivalent scope. |
| `research-before-modifying` | Inactive draft retained for later review | No automatic activation or blanket research obligation. |
| `user-interface-analyst-visibility` | Inactive historical UI requirement | Link to existing UI requirement if still relevant; not a reusable runtime skill. |
| `user-style-ui-requirement` | Same inactive UI requirement, with both provenance links | Deduplicate the draft representation only; do not mark requirement implemented. |
| `user-style-display-output` | Inactive historical display requirement | Review against current native display architecture; no revival of obsolete HTML/window rules. |
| `user-task-website-comparison` | Inactive historical task context | Preserve history; never turn an old ongoing task into a standing method or schedule. |

The proposed voice packages are host-event-invoked, not new fuzzy task competitors. Add validated host-controlled eligibility to the existing selection path; a package cannot elect that status itself. Reuse the same registry and loader. The other four registered task methods remain behaviorally unchanged except for necessary validated metadata/reference repairs. Keep the controlled creator package's present activation boundary.

## 5. Implementation sequence and evidence

Each increment is a small reviewed slice with its own exact source, tests, remaining limitations and dated progress in this plan. Do not create another parallel plan for the same row.

### SC0 — Rebaseline and establish the migration contract

After the start gate, inventory current definitions, package pins, actual active flags, prompt assembly, runtime bindings, public API consumers, voice navigation, and accepted UX contracts. Do not read secrets or private transcripts merely to create a baseline; use existing authorized fixtures and content-free configuration evidence.

Produce the crosswalk from §4, an affected-path/owner list, paired replay corpus, and explicit baseline budget/latency measurements. Reconcile any source additions since `b136a2a`. Confirm the existing Skills loader/readiness path can support the pilot without pretending unfinished rollout gates have passed. Obtain any additional bounded claims; do not activate all Skills Workspace features as a shortcut.

**Exit:** every legacy definition accounted for; standing policies have noncompetitive owners; seven event contracts and five drafts accounted for; no shared-path conflict; AT-01 and AT-02 pass. Record performance acceptance thresholds before comparing candidates, preserving any stricter existing limits.

### SC1 — Build the bounded compatibility seam

Reuse package loading/pinning and current policy/voice owners. Introduce only the minimal validated host binding/eligibility representation needed to distinguish optional task methods from event-loaded methods. Preserve legacy execution when the migration is off. Required policies are applied separately from the task selector.

At request start, bind the selected implementation revision and policy/event configuration snapshot. An in-flight request does not switch format mid-turn. Record content-free selection provenance under existing owner/run/privacy rules. Keep observer comparison read-only: it must not invoke tools, create jobs, append authoritative “passed” events, or make provider calls twice.

**Exit:** AT-03–AT-07, AT-11–AT-13 and AT-16 pass with synthetic fixtures. No runtime activation and no change to host capabilities.

### SC2 — Pilot planning consolidation

Move planning method guidance into `technical-plan-document` and its declared references as needed. Keep plan-before-implementation authorization separately applied. Reuse display and per-step model evidence owners. Preserve the existing planning pathway and explicit unavailability behavior.

Use a narrow migration switch/reservation established in SC0; do not repurpose an existing flag to silently change unrelated behavior. Compare old/new paths for a new implementation request, an approved continuation, a plan-status query, “what's the plan for today,” a display request and an unavailable planning service. Match expected actions and evidence, not just final prose.

**Exit:** AT-03, AT-04, AT-08, AT-10, AT-11, AT-14 and AT-16 pass; no double guidance; Larry can review the complete artifact with retained approval. Stage live pilot only through the existing authorized release process.

### SC3 — Consolidate remaining methods and voice guidance

Apply §4 incrementally. For every voice binding preserve event stage, original trigger matching, priority/tie order, specialist/supervisor scope, request lifetime, correction limits and current guard mode. Preserve request tombstoning, barge-in and cancellation behavior; speech interruption is not task cancellation. Do not switch guard `log` to `correct` as part of this work.

Keep the drafts inactive and historical requirements out of skill auto-selection. Update package pins with their reviewed content; importing third-party packages still requires individual review. No community script execution or broad package installation.

**Exit:** all mapping rows have evidence, all seven voice contracts pass paired replay, and AT-05–AT-14 pass. Any behavior that cannot be preserved stays on its explicitly tracked legacy path; it cannot be counted as migrated.

### SC4 — Unify the user experience and documentation

Use the existing Skills workspace as the reusable-method catalog. Keep Process/Activity/Versions distinctions and provenance. Provide read-only access to standing policies derived from their canonical owners, without activation switches that imply a user can disable host safeguards. Clearly label event-loaded methods so users understand why they ran.

Retain the old Workflows API, view mode and voice navigation as compatibility adapters during migration; translate to canonical content with stable legacy IDs and no second mutable store. A capability/version signal distinguishes new hosts from older clients. “Show workflows” continues to open the appropriate guidance/policy destination, not a blank view. Missing or invalid data has an honest explicit state.

Update `docs/ARCHITECTURE.md`, `docs/REPO_MAP.md`, `skills/README.md`, relevant `CLAUDE.md` guidance and the existing Skills/voice/viewer plans in coordinated scopes. Add dated supersession notes for the September separate-view choice. Reconcile WS-22/24/27 by references without taking ownership of their runtime implementation or removing persisted state.

**Exit:** AT-09–AT-13 and AT-17 pass; accessibility, narrow/wide layouts, voice/pointer navigation and old-client compatibility are evidenced. Historical accepted receipts remain historical; changed behavior receives fresh evidence.

### SC5 — Verify, release, observe and prove rollback

Run relevant Python, native and repository-required checks against the exact candidate; preserve independent release verification and deployment ceremony. Pair baseline/candidate scenarios on the same hardware, resolved model route, inputs and settings. Record sample count, p50/p95 prompt/selection/voice latency and actual instruction/reference size, including warm/cold cases. Migration must meet all existing limits; a newly proposed regression allowance requires a recorded decision before activation, never a post-failure threshold edit.

Rehearse rollback in isolation before live activation. Freeze a candidate and run the applicable live voice/UI/privacy acceptance scenarios. Record Larry's acceptance of the changed experience, build identity, package pins/config and observation evidence. Do not claim completion from passing offline tests alone.

**Exit:** AT-01–AT-18 pass or remain explicitly unaccepted; no unresolved safety/authority regression; exact candidate, rollback receipt and human acceptance are linked from the roadmap.

### SC6 — Retire legacy instruction paths

Only after SC5, remove obsolete duplicate bodies/injectors and the separate editable workflow-method catalog. Keep historical provenance, old-ID mappings, necessary client adapters and real operational workflow/task state. Freeze a reviewed canonical representation before removing the old reader; do not delete the rollback evidence or user history.

Retire an adapter only after the supported-client inventory and voice/API regression checks demonstrate it is unused or its replacement is supported. Remove obsolete configuration flags only through a separate compatible rollout, with unknown/old settings handled explicitly. Update the crosswalk, plan and roadmap; accepted status requires the linked evidence, not just removed files.

## 6. Acceptance matrix

| ID | Required observable result |
|---|---|
| AT-01 | Start gate has a linked acceptance closeout, fresh WS-29 owner/branch/scope and current source/dependency snapshot. |
| AT-02 | Every baseline and newly discovered legacy definition has exactly one disposition, preserved provenance and test mapping; no duplicate runtime owner. |
| AT-03 | A selected technical skill cannot crowd out an applicable approval/grounding/privacy rule. Test no skill, one skill, conflicting skills and over-budget content. |
| AT-04 | Approval for the same scoped continuation is retained; changed target/action still faces the existing host gate. Status-only requests never start/retry/commit/deploy work. |
| AT-05 | Imported or modified packages cannot self-enable, assert policy authority, register triggers, execute scripts, expand tools, or substitute an unpinned revision. Controlled creator behavior remains scoped. |
| AT-06 | All seven voice definitions preserve user/result/reply matches, nonmatches, priorities/ties and agent scope on the paired corpus. Verify actual expected tool calls/refusals, not prose alone. |
| AT-07 | Inactive drafts never match even word-for-word; invalid/stale/missing event content takes the bounded safe path and cannot silently disable a required host check. |
| AT-08 | Planning pilot yields the complete artifact through the existing pathway; conversational plan/status negatives do not trigger full plan creation. |
| AT-09 | One Skills library exposes methods; policies remain inspectable; Process is not presented as executed evidence and Activity cannot manufacture passed steps. |
| AT-10 | UI verification distinguishes source, validation, PR, merge, deployment and on-screen observation; failed capture is explicitly unverified. |
| AT-11 | Instruction/reference/event budgets are bounded, required policies are not silently truncated, and no duplicated body/provider/tool execution occurs. |
| AT-12 | Package versions, event selection and activity stay owner/run scoped; private sources/results and sensitive skill identities retain existing redaction and egress controls. |
| AT-13 | Legacy API/view/voice consumers continue to work through documented adapters; stable IDs and permission boundaries survive transition. |
| AT-14 | Barge-in, cancellation, stale result arrival, repeated event and concurrent task cases preserve request identity and exactly-once side-effect authority. |
| AT-15 | Existing durable job/task/attempt/evidence records still resume and report correctly; no migration of those records into instruction files. |
| AT-16 | Turning migration off restores baseline behavior without enabling drafts, changing approvals or double-injecting; in-flight requests keep their bound revision/configuration. |
| AT-17 | Changed native library/policy/navigation surfaces pass relevant Swift tests, accessibility and live voice/pointer checks on identified builds. |
| AT-18 | Paired performance stays within pre-recorded limits; exact-release checks, rollback rehearsal, live observation and Larry's acceptance have receipts. |

### 6.1 Verification entry points

Use the tests that exist at implementation time; extend them with behavioral cases above, without weakening their assertions. Current starting points include:

```sh
python3 scripts/check_roadmap.py
python -m jarvis.agent_skills --validate
pytest tests/unit/test_workflows.py tests/unit/test_voice_workflows.py tests/unit/test_workflows_viewer.py -q
pytest tests/unit/test_agent_skills.py tests/unit/test_skill_selection.py tests/unit/test_skill_injection_boundary.py -q
pytest tests/unit/test_skill_catalog.py tests/unit/test_skill_resources.py tests/unit/test_skill_service.py -q
swift test --package-path macos/JarvisKit
swift test --package-path macos/MortimerHost
git diff --check
```

Also run affected console, privacy, creator, workflow-verification, step-evidence and integration tests, plus the repository's current required CI and independent release profile. Live/model evaluations require the already approved route, data and spending scope; do not run paid probes as part of documentation validation. Preserve holdout positive/negative utterances and controlled failure cases. A test passing with a stub does not prove a live provider, permission boundary or native interaction.

## 7. Rollout, rollback and ownership boundaries

Rollout order: isolated fixtures and observer comparison → planning pilot → event/method migration → unified read-only views → exact-release live acceptance → legacy retirement. Each stage names which paths are migrated. An off switch is not permission to bypass required policy or host checks.

Before each activation, retain code/configuration/package revisions and a content-free migration manifest. Roll back to the verified compatible code/configuration/package set through the existing release pathway. Restore legacy event routing only with its reviewed definitions; do not restore private runtime data from an old snapshot merely to undo a UI/instruction migration. Avoid destructive database changes; any necessary additive schema migration must independently prove old/new compatibility and reserve its ID. Preserve requests, event evidence, approvals and user content. A rollback that loses those records fails AT-16.

Potential affected paths (future claims only): `jarvis/agent_skills.py`, `skill_selection.py`, `skill_catalog.py`, `skill_resources.py`, `workflows.py`, `voice_workflows.py`, `agents/base.py`, `prompts.py`, relevant bot guidance/console dispatch, `status/overview.py`, existing admin catalog adapters, `config/skills.yaml`, `config/workflows/`, skill packages, JarvisKit contracts, native Skills/Workflows views/stores, related tests and architecture documentation. This list does not override another row's locks or authorize changes to all paths at once.

Coordinate WS-03 for Skills/creator; WS-07 for voice/viewer/release behavior; WS-05 for source/model/privacy boundaries; WS-17/21 for console/navigation/result identity; WS-20 for shared roadmap/acceptance conventions; and WS-22/24/27 for planned operational contracts. Do not create a second durable-task system, permission ledger, model registry or runtime executor. Do not rename internal `jarvis` or MCP `skill.yaml` identifiers, install models, enable dormant auth/selection features wholesale, change guard modes, import community bundles, or alter mail/finance policies in this work.

## 8. Handoff for any implementing model

Read this plan and the current roadmap; state the source/build/configuration actually inspected. Resume from the latest completed SC increment and linked evidence. Report completed work, remaining checks, exact limitations and the next actor. Preserve existing source changes from other owners and refresh dependencies before each slice. If a model cannot run a required check, hand off that bounded check to an eligible executor; never mark it passed or reduce the criterion.

Record each slice as: increment/AT IDs, source commit, package/config revisions, tests and outcomes, actual versus synthetic evidence, unresolved issues, rollback point and next action. Record exact model/version only when telemetry establishes it. There is no requirement to use Codex, Claude, a particular model family, or a council merely to implement this plan; existing host capability/privacy requirements and repository coordination still apply.

## 9. Official design references

Reviewed 2026-10-20; refresh product-specific behavior before implementation. These inform the design but do not prove Mortimer supports a vendor feature.

- [OpenAI: Build skills](https://developers.openai.com/plugins/build/skills): reusable workflow guidance in skills; controlled actions and authorization in tools/services.
- [OpenAI: Rethinking skills and prompts](https://developers.openai.com/blog/rethinking-skills-and-prompts-for-gpt-6-astra): concise triggers, selective loading and avoiding unnecessary procedural scaffolding.
- [OpenAI: Build skills in ChatGPT/Codex](https://learn.chatgpt.com/docs/build-skills): package structure and progressive loading.
- [Claude: Skills](https://code.claude.com/docs/en/skills): reusable instructions/procedures and custom-command consolidation; host extensions are not universal portability guarantees.
- [Claude: Extension boundaries](https://code.claude.com/docs/en/features-overview): standing instructions, skills, hooks and tools have different responsibilities.
- [Claude: Dynamic workflows](https://code.claude.com/docs/en/workflows): executable orchestration remains distinct from prompt-based methods.

## 10. Dated progress

- **2026-10-20 — Codex, documentation:** Larry accepted Option 2 and requested a model-neutral implementation plan appended to the roadmap after existing acceptance testing. Created WS-29, this canonical plan and its log from main `b136a2a`. Preserved all existing roadmap bytes and acceptance checkboxes; no runtime implementation, activation or product acceptance claimed. Baseline roadmap checker reports an existing WS-17 stale `review` status for the already merged #226 branch; record it without changing that row. Documentation validation and publication evidence are recorded in the same row's dated log.

Authored by Codex for Larry's accepted direction, 2026-10-20. Exact authoring model telemetry not independently recorded.
