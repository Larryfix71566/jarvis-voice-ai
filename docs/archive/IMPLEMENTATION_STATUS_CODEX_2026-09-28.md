# Archived implementation-status snapshot

Historical source: isolated Codex worktree before CX-08 reconciliation. Original text SHA-256: `a5e07daae7ada5cb8ffa01c0d6000820038dbcacde61e83e4db8f1e689ccb034`. Relative Markdown links rebased for this archive.

This is historical evidence, not current status. Use [ROADMAP](../../ROADMAP.md) and [current implementation status](../acceptance/IMPLEMENTATION_STATUS.md).

---

# Implementation and acceptance status

## Skills workspace — implementation in progress; acceptance gates remain open

**2026-09-28:** [Skills Workspace and Skill Creation Implementation Plan](../plans/MORTIMER_SKILLS_WORKSPACE_IMPLEMENTATION_PLAN.md)
records the agreed native library, inspectable intended process, truthful run
activity, voice controls, shared-display behavior, and reviewed `skill-creator`
integration. It fixes package/selection/resource contracts and preserves sandbox,
privacy, provider-routing and PR/release boundaries. This is documentation only;
no skill has been installed or activated by this update. It supersedes the old
skill-authoring draft's conflicting scope; it closes no existing project gap.

- [ ] SW0: Freeze contracts, baseline and acceptance fixtures.
- [ ] SW1: Correct complete-body parsing; add pinned catalog/resources/readiness foundations.
- [ ] SW2: Add truthful, privacy-preserving selection/step evidence and read APIs.
- [ ] SW3: Add native library/detail/activity, voice navigation and shared-display views.
- [ ] SW4: Integrate reviewed creator and bounded sandbox authoring/testing lifecycle.
- [ ] SW5: Validate live comparisons, reviewed activation and rollback; verify loaded revision.
- [ ] SW6: Evaluate bounded multi-skill selection and complete frozen-candidate acceptance.

The plan's **SW-A through SW-L** define acceptance, not just implementation.
The per-increment handoff is recorded in
[Skills workspace status](../acceptance/skills-workspace/STATUS.md), with a reproducible
[baseline](../acceptance/skills-workspace/BASELINE.md). SW0–SW6 remain in
progress or implemented-unverified; SW-B and SW-C are the only accepted gates
(**2/12**). The weighted implementation estimate remains **90.7%**, not
recalculated for this increment, using SW0–SW6 scores
**88/84/98/99/97/87/73%** and weights **10/15/15/15/20/15/10%**.
Current code includes pinned package metadata and resource reads, authenticated
skill catalog/activity and creator-request APIs, the native library/process/
activity workspace with shared typed control actions, revision-bound cached
detail navigation, and sandbox-backed creator draft/validation/review plumbing.
SW2 now has host-owned checks for three
exact pinned process steps: current weather retrieval, Git repository status,
and Git history retrieval. Synthetic receipt tests persist only content-free
references. Latest full local suites pass **3,544 Python tests** (4 skipped, 11
warnings, 2 subtests), **347 MortimerHost tests** (9 environment-dependent
skips), and **212 JarvisKit tests**. Tart 2.39.0 and the existing Softnet helper
pass host diagnostics. A disposable VM completed dependency preparation and
IPv4 isolation probes, but the guest had no observed IPv6 default route, so
IPv6 containment is unverified and SW-F remains open. Current candidate release
receipts are stale after recent edits; the app remains unlaunched, uninstalled,
and undeployed. Creator activity ownership is decided: creator work must attach
to a real Developer SubAgent run, with the sandbox request/job ID kept distinct.
The admin sidecar currently cannot dispatch the bot-session Developer; the
authenticated dispatch contract is specified in the plan but not implemented.
Native skips and remaining gates are detailed in
the [Skills workspace status](../acceptance/skills-workspace/STATUS.md). Other process steps
still lack trusted check mappings. Runtime readiness, activation and rollback
remain fail-closed without live evidence. Provider-route, human-review, and
frozen-Mac acceptance remain open. Creator end-to-end acceptance precedes new
task-specific skill development. Unresolved parent privacy/model-route/release
gates remain applicable to each enabled feature.

## Existing implementation and acceptance work

**Model-ready execution plan (refreshed 2026-09-25):**
[Verified Gap Closure](../plans/MORTIMER_VERIFIED_GAP_CLOSURE_PLAN.md) maps the
verified implementation and release gaps inspected at main `4acb4dc` (#90) to
ordered implementation and acceptance increments. It specifies locked design
decisions, dependencies, file ownership, test requirements, privacy and
rollback boundaries, and acceptance evidence for each increment. It remains a
plan; it does not close the rows below.

The latest consolidated handoff from the current review is the [Current
Review Gaps Implementation Plan](../plans/MORTIMER_CURRENT_REVIEW_GAPS_IMPLEMENTATION_PLAN_2026-09-25.md).
It orders the remaining lifecycle, privacy, model-route, automatic-memory,
Atlas, and frozen-candidate work, preserving the existing feature contracts
and not claiming any live or release gate has passed. Focused receipts now
exist for [F14](../acceptance/verified-gap-closure/GC24-03-selfedit-staging-log-redaction-2026-09-25.md),
[F15](../acceptance/verified-gap-closure/GC24-03-model-override-refusal-log-redaction-2026-09-25.md),
[F16](../acceptance/verified-gap-closure/GC24-03-sidecar-root-log-redaction-2026-09-25.md),
and [F17](../acceptance/verified-gap-closure/GC24-03-council-small-round-log-redaction-2026-09-25.md).
These close only the named diagnostic fields; full privacy source-to-sink
coverage remains open.

The concise next-step handoff for implementation models is the [Next Gaps
Implementation Plan](../plans/MORTIMER_NEXT_GAPS_IMPLEMENTATION_PLAN_2026-09-25.md).
It reflects the latest protected-result renderer/share evidence and orders
the remaining lifecycle, privacy, model-route, memory, Atlas, and candidate
gates without changing their authoritative acceptance criteria. The
`app_create`/`app_register` action identity contract and T4b protected-history
policy remain explicit stop gates; independent, fully specified work can
continue.

**2026-09-25 subscription runtime follow-up:** source and installed-CLI review
found that the text-only subscription adapters still pass prompts in process
arguments, inherit project execution context, use a denylist rather than a
minimal environment allowlist, accept insufficiently validated provider
output, and cannot reliably terminate/reap async child processes on
cancellation. The [Subscription Runtime Isolation Plan](../plans/MORTIMER_SUBSCRIPTION_RUNTIME_ISOLATION_PLAN_2026-09-25.md)
defines a model-neutral GC24-04 implementation sequence and fail-closed gates.
This is the gap found during the initial review. Offline implementation
progress is recorded below; it remains neither live-verified nor release
accepted. Codex's installed-runtime no-built-in-tools control has not been
verified; read-only sandbox alone does not meet that requirement, so do not
rely on Codex subscription execution for a no-tools guarantee until that
control is proven.

**2026-09-25 implementation progress — model-route credential boundary:**
checked SAYGM resolution now uses the caller's explicit environment for
catalog authentication and fails before provider access when that mapping
omits the key. The focused routing, SAYGM, memory-model, and execution suites
passed **66**; the full Python unit/integration suite then passed **3,054**,
with **4 skipped**, **11 warnings**, and **2 subtests**. This closes only
explicit-environment credential selection;
route capability, provider isolation, confidential eligibility, tool safety,
and billing evidence remain open. See the [GC24-04 receipt](../acceptance/verified-gap-closure/GC24-04-explicit-environment-credential-isolation-2026-09-25.md).

**2026-09-25 T4a offline verification:** the focused detector, MCP child-env,
`requires_env` snapshot, and agent-isolation suites passed **152** on this
Darwin host. This is the offline V1 test portion only; live child-process,
voice, memory, and routing-eval checks remain open. See the [T4a receipt](../acceptance/verified-gap-closure/GC24-03-T4a-offline-security-tests-2026-09-25.md).

**2026-09-25 subscription runtime implementation progress:** the Claude and
Codex text adapters now isolate prompt input, working directory, child
environment, structured completion parsing, and async process-group
cancellation. The full Python unit/integration suite passed **3,079**, with
**4 skipped**, **11 warnings**, and **2 subtests**; focused adapter/routing/
execution tests passed **87**. The offline adapter implementation package is
complete; GC24-04 remains open because no provider was called, Codex's complete
no-tools capability remains gated unverified, and authentication, model/privacy
capability, billing, deployment, and Mac acceptance remain open. Inherited `CODEX_HOME` and
`CLAUDE_CONFIG_DIR` overrides are excluded from provider child environments;
a fresh local auth-status check found Claude unauthenticated and Codex logged
in, which does not establish successful completion behavior. See the [runtime isolation receipt](../acceptance/verified-gap-closure/GC24-04-subscription-runtime-isolation-2026-09-25.md)
and [implementation plan](../plans/MORTIMER_SUBSCRIPTION_RUNTIME_ISOLATION_PLAN_2026-09-25.md).

The model-neutral, work-package-level handoff for any implementation model is
the [Model-Neutral Gap Implementation Plan](../plans/MORTIMER_MODEL_NEUTRAL_GAP_IMPLEMENTATION_PLAN_2026-09-25.md).
It preserves the confirmed design and security constraints, orders the open
GC24 work, and marks the `app_create`/`app_register` identity contract as an
explicit unresolved decision rather than allowing an implementer to guess.

The app-build submit path now has a session-scoped durable replay claim and
focused unknown-outcome protection; see the [GC24-02 receipt](../acceptance/verified-gap-closure/GC24-02-appbuild-submit-session-claim-2026-09-25.md).
This closes only app-build PR submission replay in the isolated tree; live
GitHub publication and remaining caller lifecycle gates stay open.
The broader action inventory also found unresolved durable approval identity
for `app_create` and direct `app_register`; see the [identity audit
receipt](../acceptance/verified-gap-closure/GC24-02-mutating-caller-identity-audit-2026-09-25.md).

The latest full Python unit/integration run on the dirty isolated tree passed
**3,053**, with **4 skipped**, **11 warnings**, and **2 subtests**. See the
current review plan for the exact command and the asynchronous authoring-test
stability adjustment; this does not establish Mac, provider, or release
acceptance.

The model-ready work sequence is also available as a
[newly verified gaps implementation plan](../plans/MORTIMER_NEWLY_VERIFIED_GAPS_IMPLEMENTATION_PLAN.md).
It was refreshed 2026-09-25 against the current isolated-tree lifecycle,
privacy, model-access, automatic-memory, Atlas, and candidate/release gaps. It
keeps the accepted product and architecture decisions fixed, orders the work,
and defines handoff and evidence requirements; it does not claim release
acceptance.

The latest source-tree gap refresh is in the
[Current Verified Gaps Implementation Plan](../plans/MORTIMER_GAPS_IMPLEMENTATION_PLAN_2026-09-25.md).
It records the current isolated 26/26 call-site audit and replaces stale next-action wording
from earlier snapshots; acceptance thresholds remain owned by the linked
feature and closure plans.

The newest consolidated handoff is the
[Implementation Gaps Execution Plan](../plans/MORTIMER_IMPLEMENTATION_GAPS_EXECUTION_PLAN_2026-09-25.md).
It gives one dependency-ordered sequence for the currently open execution,
privacy, model-access, automatic-memory, Knowledge Atlas, and candidate/release
gates, with fixed design constraints and pass criteria. It is a plan for the
dirty isolated worktree, not evidence that those gates have passed.

The latest single-document handoff for implementation order and model
handoff is the [Reviewed Gaps Implementation Plan](../plans/MORTIMER_REVIEWED_GAPS_IMPLEMENTATION_PLAN_2026-09-25.md).
It consolidates the confirmed GC24-00/01 through GC24-07–10 gaps and their
pass conditions while keeping the linked feature contracts and receipts
authoritative.

The post-review, implementation-focused handoff is in the
[Post-Review Gap Closure Plan](../plans/MORTIMER_POST_REVIEW_GAP_CLOSURE_PLAN_2026-09-25.md).
It orders the still-open lifecycle, privacy, memory-admission, model-route,
Atlas, and candidate gates based on the current isolated source tree; it does
not change acceptance thresholds or claim live/release completion. It now
spells out the protected specialist-result leak, the required local-first
handoff, its fail-closed behavior, and the negative tests needed to close that
slice; it also records that SubAgent cancellation finalizes its run log and
the delegate-task UI receives one terminal event on normal, abnormal, or
shutdown paths, while full provider/tool/UI/database cancellation remains
open, and summarizes
redacted MCP, watcher, clipboard/command-title, agent/delegation/event, admin
job/status-error, memory, workflow-parser, KB-digest, and voice-pipeline
teardown diagnostic paths. These partial
slices are recorded in the [GC24-02 cancellation receipt](../acceptance/verified-gap-closure/GC24-02-cancellation-terminal-2026-09-25.md),
[Supervisor late-provider cancellation receipt](../acceptance/verified-gap-closure/GC24-02-supervisor-late-provider-cancellation-2026-09-25.md),
[GC24-02 delegate lifecycle receipt](../acceptance/verified-gap-closure/GC24-02-delegate-terminal-lifecycle-2026-09-25.md),
[GC24-03 protected-result receipt](../acceptance/verified-gap-closure/GC24-03-protected-local-result-handoff-2026-09-25.md),
[MCP log receipt](../acceptance/verified-gap-closure/GC24-03-mcp-exception-log-redaction-2026-09-25.md),
[watcher log receipt](../acceptance/verified-gap-closure/GC24-03-watcher-log-redaction-2026-09-25.md),
[clipboard log receipt](../acceptance/verified-gap-closure/GC24-03-clipboard-log-redaction-2026-09-25.md),
and [agent/event log receipt](../acceptance/verified-gap-closure/GC24-03-agent-event-findings-log-redaction-2026-09-25.md),
plus the [admin job log/status receipt](../acceptance/verified-gap-closure/GC24-03-admin-job-log-and-status-redaction-2026-09-25.md)
and [memory log receipt](../acceptance/verified-gap-closure/GC24-03-memory-log-redaction-2026-09-25.md),
the [workflow/KB digest log receipt](../acceptance/verified-gap-closure/GC24-03-workflow-and-kb-digest-log-redaction-2026-09-25.md),
and the [voice-pipeline teardown receipt](../acceptance/verified-gap-closure/GC24-03-voice-pipeline-teardown-log-redaction-2026-09-25.md).
The broader privacy phase remains open.

**2026-09-25 design reconciliation — Supervisor history:** the Security
Hardening Plan explicitly accepts same-session Supervisor history retention
during T4a because clearing it breaks conversational continuity, and assigns
protected-context handling to T4b. A candidate history-deletion change was
reverted because it would violate that accepted behavior. Track history
continuation as an open T4b-dependent privacy sink; do not close it through
lossy history deletion or placeholder substitution. See
[Security Hardening Plan](../plans/MORTIMER_SECURITY_HARDENING_PLAN.md) R-H7.

**2026-09-25 progress — protected-result sharing boundary:** a new
`ConsoleActionCoordinatorTests` canary verifies a protected result referenced
by an image preview cannot reach copy, save, or the system share picker. The
focused macOS suite passed **16 tests, 0 failures**. See the [GC24-03 receipt](../acceptance/verified-gap-closure/GC24-03-protected-result-share-actions-2026-09-25.md).
This closes only those result-action sinks; the full source-to-sink audit
remains open.

A consolidated model-neutral handoff for the gaps that remain after the latest
code review is in the [Review-Gap Implementation Plan](../plans/MORTIMER_REVIEW_GAPS_IMPLEMENTATION_PLAN_2026-09-25.md).
It orders the remaining lifecycle, privacy, model-route, memory durability,
Atlas, and release work; it keeps accepted design and architecture fixed and
does not claim candidate or release acceptance.

The current one-page execution index is the
[Remaining Gaps Execution Plan](../plans/MORTIMER_REMAINING_GAPS_EXECUTION_PLAN_2026-09-25.md).
It reconciles the open work packages and dependencies against the current
isolated-tree evidence, and directs implementers to the existing authoritative
contracts and receipts for detailed acceptance thresholds.

The refreshed model-neutral handoff is the
[Fresh Review Implementation Plan](../plans/MORTIMER_FRESH_REVIEW_IMPLEMENTATION_PLAN_2026-09-25.md).
It consolidates the remaining verified gaps, fixes accepted design and
architecture decisions, orders dependencies, and defines handoff and evidence
requirements. Its GC24-03 register now points to residual diagnostic slices
F1–F25, including skill/workflow injection metadata, transcript-persistence
exceptions and content, reminder identifiers, client-message logging, route
refusal details, and self-edit branch labels; the full privacy
source-to-sink audit remains open. It is a handoff for the dirty isolated
worktree and does not claim that any live, merge, or release gate has passed.

The follow-up [GC24-03 Sensitive Diagnostic-Logging Plan](../plans/MORTIMER_GC24-03_REMAINING_EXCEPTION_LOG_REDACTION_PLAN_2026-09-25.md)
organizes residual exception and dynamic-value logging work. Slices A–E have
scoped receipts. Slice F now indexes twenty-five source/test rows, including
additional runtime sinks for clipboard, usage accounting, tenant/vault data,
self-edit IDs, council diagnostics, and skill/workflow injection metadata.
Reconcile each row against current code and its receipt before closing it;
the broader privacy source-to-sink audit remains open.

**2026-09-25 progress — transcript content removed from persistent stdout:**
the transcript logger keeps role/timing markers and a character count while
omitting user and assistant words from `logs/bot.log`. Ordinary conversation
rows remain available to memory; sensitive-turn suppression and UI delivery
are unchanged. Focused transcript/wiring/latency tests passed **75**; the
complete Python unit/integration suite then passed **3,025**, with **4
skipped**, **11 warnings**, and **2 subtests**. Ruff `F`/`I`, compileall, and
`git diff --check` passed. See the [F25 receipt](../acceptance/verified-gap-closure/GC24-03-transcript-content-log-redaction-2026-09-25.md).
This closes only that stdout sink; the GC24-03 source-to-sink audit remains
open.

**2026-09-25 progress:** slice A of that plan rechecked and redacted current
memory extraction/worker logs, including residual tracebacks, memory/session
identifiers, and the worker cursor. The two focused suites passed **64**;
Ruff `F`/`I`, compileall, and `git diff --check` passed. See the [slice A
receipt](../acceptance/verified-gap-closure/GC24-03-memory-extraction-worker-log-redaction-2026-09-25.md).
See also the later slice B–E progress entries below. Slice F and the wider
privacy source-to-sink audit remain open.

**2026-09-25 progress:** slice B redacted speaker-profile and voice-gate logs
for local paths, raw exception text/tracebacks, transcript content, and turn
IDs while keeping bounded diagnostics. Focused tests passed **69** with **2
dependency deprecation warnings**; Ruff `F`/`I`, compileall, and
`git diff --check` passed. See the [speaker/audio receipt](../acceptance/verified-gap-closure/GC24-03-speaker-audio-log-redaction-2026-09-25.md).
Slices C–E and broader audio/privacy boundaries remain open.

**2026-09-25 progress:** slice C removed exception text and tracebacks from
council and upgrade-agent failure paths and stopped logging council choice
labels and unknown outcome values. Focused council/upgrade tests passed
**88**; Ruff `F`/`I`, compileall, and `git diff --check` passed. See the
[council/upgrade receipt](../acceptance/verified-gap-closure/GC24-03-council-upgrade-log-redaction-2026-09-25.md).
Council content data flow and slices D–E remain open.

**2026-09-25 progress:** slice D made screen diagnostics metadata-only while
preserving screen capture, low-confidence retention, and pruning behavior.
Focused tests passed **28**; Ruff `F`/`I`, compileall, and
`git diff --check` passed. See the [screen-log receipt](../acceptance/verified-gap-closure/GC24-03-screen-log-redaction-2026-09-25.md).
Low-confidence image retention and broader screen privacy remain open.

**2026-09-25 progress:** slice E redacted procedure, skill parsing, usage,
and shared-content diagnostics while preserving their best-effort behavior.
Focused suites passed **131** with **1 dependency deprecation warning**;
Ruff `F`/`I`, compileall, and `git diff --check` passed. See the
[slice E receipt](../acceptance/verified-gap-closure/GC24-03-procedures-skills-usage-log-redaction-2026-09-25.md).

**2026-09-25 plan refresh:** a follow-up scan has made slice F executable
with source/test ownership, canary requirements, and fixed behavior
constraints for twenty-five diagnostic candidates. Revalidate implementation
and receipts in the current dirty tree before closing any row. Completion of
these log slices will not close the wider privacy source-to-sink audit.

**2026-09-25 progress — transcript persistence error:** transcript DB
failures retain a bounded exception class in stdout diagnostics, without the
raw exception message. The focused transcript/sensitive-turn and pipeline
wiring suites passed **68**; Ruff `F`/`I`, compileall, and `git diff --check`
passed for the affected files. See the [F19 receipt](../acceptance/verified-gap-closure/GC24-03-transcript-persistence-error-log-redaction-2026-09-25.md).

**2026-09-25 progress — client app-message diagnostics:** voice-selection
and UI no-op stdout entries now retain static event names without client
values or spoken reason text. `test_bot_wiring.py` passed **52**; Ruff
`F`/`I`, compileall, and `git diff --check` passed for the affected files.
See the [F20–F21 receipt](../acceptance/verified-gap-closure/GC24-03-client-app-message-log-redaction-2026-09-25.md).

**2026-09-25 progress — reminder row identifiers:** notification post and
mark-notified failures no longer print reminder database IDs. The reminder
notifier suite passed **7**; Ruff `F`/`I`, compileall, and `git diff --check`
passed for the affected files. See the [F22 receipt](../acceptance/verified-gap-closure/GC24-03-reminder-row-id-log-redaction-2026-09-25.md).

**2026-09-25 progress — route override refusal diagnostics:** override
refusals retain their stable event and agent identity, while profile names
and route-resolution reasons remain in the user-facing refusal only. The
SubAgent suite passed **66**; Ruff `F`/`I`, compileall, and `git diff
--check` passed for the affected files. See the [F23 receipt](../acceptance/verified-gap-closure/GC24-03-model-override-refusal-log-redaction-2026-09-25.md).

**2026-09-25 progress — self-edit branch label:** appearance verification
still returns the branch to its caller but now logs only a presence flag.
`test_admin_api.py` passed **24**; Ruff `F`/`I`, compileall, and
`git diff --check` passed for the affected files. See the [F24 receipt](../acceptance/verified-gap-closure/GC24-03-selfedit-branch-label-log-redaction-2026-09-25.md).

**2026-09-25 progress — skill/workflow injection labels:** the F18
diagnostic fields now retain the event and agent identity while omitting
skill/workflow names and workflow source paths. Canary test and all 65
`test_subagent.py` tests pass; Ruff `F`/`I`, compileall, and `git diff
--check` pass for the affected files. This closes only the F18 log fields.
See the [F18 receipt](../acceptance/verified-gap-closure/GC24-03-skill-workflow-injection-log-redaction-2026-09-25.md).

**Reconciled 2026-09-25 against main `4acb4dc` (#90).** PR #90 updates the
accepted orb shell; it does not change the model execution, privacy, memory
admission, or Atlas lifecycle gaps in the closure plan. Its commit reports
MortimerHost 258 executed / 3 skipped / 0 failures, JarvisKit 199 passed, and
Crystal p95 13.59 ms at 1440×220. These are commit-reported results, not a
fresh test run in this Codex worktree. Installed app/service identity and
effective runtime settings remain unverified. See the
[`GC24-00 main refresh`](../acceptance/verified-gap-closure/GC24-00-main-refresh-2026-09-25.md)
and original
[`GC24-00 baseline`](../acceptance/verified-gap-closure/GC24-00-baseline-2026-09-25.md).

Updated September 18, 2026 from the release-review worktree; verification
counts reconciled and a model-use section added 2026-09-22 against main
`88b206f`. This matrix
separates repository implementation evidence from release acceptance evidence.
An implementation row is complete when its source, tests, and receipt are
present. A release row stays open when it needs physical hardware, a live
provider journey, or an observation period.

## Automated memory management

| Requirement | Implementation evidence | Acceptance evidence | Status |
| --- | --- | --- | --- |
| Automatic memory classification without user labeling | One strict `execute_chat` classifier is shared by production and synthetic shadow; migrations 0025–0027 add durable staging, shared budget reservation, and digest-only shadow metadata; idle worker and teardown enqueue before cursor/pairing advancement and drain resumable stages under explicit gates; claim-timestamp fencing includes stage transitions and atomic apply; tests cover terminal/apply rollback, stale apply-owner rejection, simultaneous two-connection and two-process single claim, forget racing apply and lease recovery across processes, enqueue/cursor recovery, and extract/classify recovery before commit and after committed transitions | Source-turn/provenance and current-turn admission tests, route-denial canary, shared-adapter/budget tests, stage/retry/forget tests, shadow dry-run, [admission worker receipt](../acceptance/verified-gap-closure/GC24-05-admission-worker-2026-09-25.md), [claim-fencing receipt](../acceptance/verified-gap-closure/GC24-05-admission-claim-fencing-2026-09-25.md), [apply-claim fencing receipt](../acceptance/verified-gap-closure/GC24-05-admission-apply-claim-fencing-2026-09-25.md), [concurrent claims receipt](../acceptance/verified-gap-closure/GC24-05-admission-concurrent-claims-2026-09-25.md), [forget/apply receipt](../acceptance/verified-gap-closure/GC24-05-admission-forget-apply-race-2026-09-25.md), [multi-process race receipt](../acceptance/verified-gap-closure/GC24-05-admission-multiprocess-races-2026-09-25.md), [apply/enqueue/stage/completion crash receipt](../acceptance/verified-gap-closure/GC24-05-admission-apply-rollback-2026-09-25.md) | Staged admission is implemented in the isolated tree and the focused admission/worker/acceptance suites pass 77 tests. Confidential route eligibility, production rollout, and staged Mac acceptance remain open; production classification stays fail-closed |
| Scoped corrections, provenance, revisions, validity | Memory and sweep changes | Offline B5 receipt; acceptance tests | Complete in sandbox |
| Task-relevant retrieval and usage accounting | Retrieval changes and `used_for` assertions | Focused memory suite | Complete in sandbox |
| Quiet bounded idle maintenance | `memory_watcher.py`, retry/budget tests | Worker and teardown tests | Complete in sandbox |
| Privacy-safe shadow and provider route | Provider runner and registry route | Provider shadow receipt and dry-run | Complete in sandbox; production disabled |
| Staged rollout and rollback thresholds | `JARVIS_MEMORY_AUTOMATION_STAGE`, evaluator | Rollout receipt; manifest checks | Complete in sandbox |
| Mac staged enablement and benefit/cost observation | Runtime procedure in runbook | Redacted daily-driver receipt | Open: requires Mac observation |

## Command Center and Knowledge Atlas

| Requirement | Implementation evidence | Acceptance evidence | Status |
| --- | --- | --- | --- |
| Layout 2 command console and compact Conversation startup | Native composition and layout tests | Full-console and live candidate inspection | Complete in sandbox; live candidate observed |
| Shared pointer/voice action ownership | `ConsoleActionCoordinator`, protocol/registry | Swift/Python parity and stale-target tests | Complete in sandbox |
| Atlas, graph, pins, comparison, reading state | Atlas/graph stores and rendering tests | Atlas, graph, large-fixture and frame-time receipts | Base projection and per-source refresh lifecycle implemented in isolated tree; latest MortimerHost run passes 267 with 7 environment/display skips and no failures. Atlas card summary/source are exposed to accessibility APIs; a mounted AX-tree test verifies the result control label/value and press activation. Live VoiceOver/keyboard traversal remains open. The prior window-visibility failures are specifically classified: three actual-window tests and the on-screen graph benchmark skip only when the XCTest process has no display; the unlock observer is deterministically injected for unit tests. Live auth/source changes, display-move no-duplicate proof, on-screen graph p95, physical monitor topology and candidate acceptance remain open; see the [GC24-06 fixture receipt](../acceptance/verified-gap-closure/GC24-06-headless-window-fixture-classification-2026-09-25.md) and [Atlas accessibility receipt](../acceptance/verified-gap-closure/GC24-06-atlas-card-accessibility-content-2026-09-25.md) |
| One response result per request | `ResponseResultRouter`, stable workspace/display IDs | Response-routing and focused native receipt | Complete in sandbox; live ownership observed |
| Bounded supporting display and return-to-main | Display stage budget and placement owner | Live two-result stage, automatic unplug/rehome, reconnect restoration, and close/return receipts | Open: voice-triggered repeat and provider/fetch evidence remain |
| Text/image sharing and inbound approval | Share coordinator, attachment transfer, privacy latch | Unit and protocol tests | Open: live picker/provider journey |
| Voice parity and two-channel measured audio | Native voice routing and waveform tests | `READY VOICE` observed; live spoken-response receipt | Open: active user/output audio evidence |
| Accessibility, rollback, independent verification | Test hooks and legacy layout paths | Mac accessibility, rollback, verifier receipts | Open |
| Five-day daily-driver acceptance | Candidate freeze/runbook | Dated daily-driver log | Open |

## Current automated verification

**Prior isolated-tree verification on 2026-09-25 (before the staged
self-edit cross-run claim):** after the protected
local-result, static-workload privacy-floor, SubAgent cancellation-during-
tool, SubAgent post-cancellation result suppression, direct-mode
SubAgent/self-edit planner tool-call ID replay protection, live Supervisor
whole-batch tool-call identity validation and direct-tool run logging, and
tenant-scoped durable one-shot plan_start claims keyed by SubAgent run ID, plus
run-scoped app_build_start claims and action-specific status lookup, plus
fail-closed external MCP blocking for missing or armed sensitivity context, plus
mid-task financial-result detection/stopping for SubAgent and Supervisor
continuations, plus
MCP/watcher/clipboard/agent-event/admin/memory log-redaction changes,
`.venv/bin/python -m pytest tests/unit tests/integration -q --tb=short`
passed **2,943 tests**, with **4 skipped**, **11 warnings**, and
**2 subtests**. The focused MortimerHost share/action run passed **19/19**;
Ruff `F`/`I` checks and `git diff --check` passed. The tree was already dirty
and contains concurrent work, so these counts describe that exact isolated
snapshot, not a clean commit. They do not establish Mac candidate, live
provider, deployment, or release acceptance. The cancellation increment's
focused run-log/SubAgent/integration suite passed 92 tests, the combined
registry/run-log/SubAgent suite passed 104, the watcher suite passed 48, and
the combined clipboard/watcher/pipeline suite passed 107. See the
[GC24-02 cancellation receipt](../acceptance/verified-gap-closure/GC24-02-cancellation-terminal-2026-09-25.md),
[GC24-02 delegate lifecycle receipt](../acceptance/verified-gap-closure/GC24-02-delegate-terminal-lifecycle-2026-09-25.md),
[GC24-02 cancellation-suppression receipt](../acceptance/verified-gap-closure/GC24-02-subagent-cancellation-suppression-2026-09-25.md),
[GC24-02 tool-call replay receipt](../acceptance/verified-gap-closure/GC24-02-tool-call-identity-replay-2026-09-25.md),
[GC24-02 Supervisor replay receipt](../acceptance/verified-gap-closure/GC24-02-supervisor-tool-call-identity-replay-2026-09-25.md),
the [direct Supervisor runlog receipt](../acceptance/verified-gap-closure/GC24-02-supervisor-direct-tool-runlog-2026-09-25.md),
and the [existing voice response-stream receipt](../acceptance/verified-gap-closure/GC24-02-existing-voice-response-stream-path-2026-09-25.md),
plus the [unknown-tool outcome observability receipt](../acceptance/verified-gap-closure/GC24-02-unknown-tool-outcome-observability-2026-09-25.md),
and the [run-scoped plan_start claim receipt](../acceptance/verified-gap-closure/GC24-02-plan-start-run-scoped-claim-2026-09-25.md),
and the [run-scoped app_build_start claim receipt](../acceptance/verified-gap-closure/GC24-02-appbuild-run-scoped-claim-2026-09-25.md),
and the [self-edit publication cross-run claim receipt](../acceptance/verified-gap-closure/GC24-02-selfedit-publication-cross-run-claim-2026-09-25.md),
and the [GC24-03 missing-context MCP privacy receipt](../acceptance/verified-gap-closure/GC24-03-external-mcp-missing-context-fail-closed-2026-09-25.md),
and the [GC24-03 mid-task tool-result receipt](../acceptance/verified-gap-closure/GC24-03-sensitive-tool-result-midtask-stop-2026-09-25.md),
the [GC24-03 protected-result receipt](../acceptance/verified-gap-closure/GC24-03-protected-local-result-handoff-2026-09-25.md),
the [GC24-03 MCP log-redaction receipt](../acceptance/verified-gap-closure/GC24-03-mcp-exception-log-redaction-2026-09-25.md),
the [GC24-03 watcher-log receipt](../acceptance/verified-gap-closure/GC24-03-watcher-log-redaction-2026-09-25.md),
the [GC24-03 clipboard-log receipt](../acceptance/verified-gap-closure/GC24-03-clipboard-log-redaction-2026-09-25.md),
the [GC24-03 agent/event-log receipt](../acceptance/verified-gap-closure/GC24-03-agent-event-findings-log-redaction-2026-09-25.md),
the [GC24-03 admin job-log/status receipt](../acceptance/verified-gap-closure/GC24-03-admin-job-log-and-status-redaction-2026-09-25.md),
and the [GC24-03 memory-log receipt](../acceptance/verified-gap-closure/GC24-03-memory-log-redaction-2026-09-25.md).

**Prior isolated-tree verification on 2026-09-25:** after the staged
self-edit cross-run claim and its status/client changes,
`.venv/bin/python -m pytest tests/unit tests/integration -q --tb=short`
passed **2,950 tests**, with **4 skipped**, **11 warnings**, and **2
subtests**. The final focused admin/self-edit/MCP/app-build/plan/run-log run
passed **212**, and the self-edit/MCP/end-to-end focused run passed **144**,
including all three self-edit end-to-end journeys. Ruff `F` checks on the five changed Python
files, Ruff `I` on the two implementation modules, and `git diff --check`
passed. See the [cross-run self-edit claim
receipt](../acceptance/verified-gap-closure/GC24-02-selfedit-staged-action-cross-run-claim-2026-09-25.md).
These counts describe the exact dirty isolated snapshot only; they do not
establish Mac candidate, provider, deployment, or release acceptance.

**Latest isolated-tree verification on 2026-09-25:** after redacting six
startup maintenance exception logs, `.venv/bin/python -m pytest tests/unit
tests/integration -q --tb=short` passed **2,956 tests**, with **4 skipped**,
**11 warnings**, and **2 subtests**. `tests/integration/test_bot_wiring.py`
passed **39**; Ruff `F`/`I` and `git diff --check` passed on the affected
files. See the [startup log-redaction
receipt](../acceptance/verified-gap-closure/GC24-03-startup-maintenance-log-redaction-2026-09-25.md).
This remains evidence from a dirty isolated worktree, not a candidate,
deployment, or release result.

**Latest isolated-tree verification on 2026-09-25:** self-edit PR publication
claims now cover background finish and native submit. They use the persisted
sandbox session identity after validation and before publication; duplicate
requests are suppressed, uncertain outcomes require reconciliation, and
status lookup survives movement of the in-memory job slot. Validation
failures remain repairable because they do not claim publication. The focused
admin/self-edit/MCP suite passed **151 tests**, and the full Python
unit/integration suite passed **2,963**, with **4 skipped**, **11 warnings**,
and **2 subtests**. Ruff `F`/`I`, compileall, and `git diff --check` passed.
See the [publication claim receipt](../acceptance/verified-gap-closure/GC24-02-selfedit-publication-cross-run-claim-2026-09-25.md).
This does not cover other mutation families or establish live GitHub, Mac,
merge, deployment, or release acceptance.

The latest full MortimerHost run passes **265 tests, 7 skipped, 0 failures**.
The skips are exact environment/hardware gates: three window-server visibility
tests and the on-screen graph benchmark require a visible display; external
topology and two supporting-display journeys require connected monitors. The
unlock callback unit test passes through an injected event source; real
`com.apple.screenIsUnlocked` delivery remains a live Mac check. See the
[GC24-06 fixture-classification receipt](../acceptance/verified-gap-closure/GC24-06-headless-window-fixture-classification-2026-09-25.md).

The existing voice result stream is also verified from RTVI `bot-llm-text`
frames through the transcript and response router. JarvisKit frame-aggregation
tests pass **2/2**, a stub-transport integration through `AppMessageRouter`
passes **1/1**, and MortimerHost `ResponseResultRouterTests` pass **7/7**.
These do not substitute for a live running-candidate voice journey. Generic shared-execution
`ModelExecutionEvent.text_delta` events still have no native result consumer.
See the [voice response-stream receipt](../acceptance/verified-gap-closure/GC24-02-existing-voice-response-stream-path-2026-09-25.md).

SubAgent run details now correlate tool-call IDs and surface dispatched calls
that remain unresolved or have an unknown outcome after cancellation. The
focused migration/runlog/SubAgent/MCP/e2e suite passes **124 tests**. After
the migration upgrade regression was added, the full suite passed **2,917
tests** with **4 skipped**, **11 warnings**, and **2 subtests**. This is
an operator reconciliation signal only; it does not establish whether a
mutation committed or prevent a later request from repeating it under a new
provider call ID. Cross-request action reconciliation and other caller
families remain open. See the
[unknown-tool outcome observability receipt](../acceptance/verified-gap-closure/GC24-02-unknown-tool-outcome-observability-2026-09-25.md).

The latest `main` commit evidence remains PR #90's merge report
(`4acb4dc`): MortimerHost 258 executed / 3 skipped / 0 failures, JarvisKit
199 passed / 0 failures, and Crystal p95 13.59 ms at 1440×220. These are
commit-reported results, not reruns here. PR #90 did not report a Python run;
PR #89's older Python commit report (`8bd5e7e`) was 2,773 passed / 4 skipped.
The dirty isolated Python source snapshot passed 2,972 unit/integration tests
after workflow, KB digest, and voice-pipeline teardown log redaction, with 4
skipped, 11 warnings, and 2 subtests. Focused results include 157 admin/
self-edit/MCP/run-ID tests, 31 workflow/KB digest tests, and 44 pipeline-
wiring tests; Ruff `F`/`I`, compileall, and `git diff --check` passed on the
associated increments. See the [bare self-edit start receipt](../acceptance/verified-gap-closure/GC24-02-selfedit-run-scoped-bare-start-claim-2026-09-25.md),
[workflow/KB digest receipt](../acceptance/verified-gap-closure/GC24-03-workflow-and-kb-digest-log-redaction-2026-09-25.md),
and [voice-pipeline teardown receipt](../acceptance/verified-gap-closure/GC24-03-voice-pipeline-teardown-log-redaction-2026-09-25.md).
After the mounted Atlas accessibility test was added, the full MortimerHost
target passed 267 tests with 7 hardware/display-gated skips and 0 failures; see the [Atlas
accessibility receipt](../acceptance/verified-gap-closure/GC24-06-atlas-card-accessibility-content-2026-09-25.md).
None of these source/test counts establish the installed app or current
runtime settings. The receipt-time and
`88b206f` comparisons below are historical and remain labelled as such.

**2026-09-25 progress — native Edit-tab action identity:** the bare-goal
Edit-tab caller now supplies a per-action UUID accepted by the existing
SQLite self-edit claim scope. A transport failure retains the original goal,
model, action ID, and backend endpoint; Retry / Check Run reuses that action
identity. The sidecar now refuses deprecated bare starts without `run_id`
before dispatch, while staged starts continue to use the issued staging ID.
Focused admin/self-edit/app-build/MCP/end-to-end/registry tests passed **176**
with **1 warning**; the full Python suite then passed **3,026**, with **4
skipped**, **11 warnings**, and **2 subtests**. Swift source parsing passed.
The focused Swift package
test was attempted but stalled while SwiftPM fetched the pinned WebRTC
binary artifact; compiled Swift and live UI behavior are unverified. See the
[native Edit-tab receipt](../acceptance/verified-gap-closure/GC24-02-native-edit-tab-action-id-2026-09-25.md).

**2026-09-25 progress — app-build start identity:** `app_build_start` now
requires the registry-injected ID at both the MCP helper and sidecar
boundaries; missing, blank, and overlong IDs are refused before a job
dispatch. The existing SQLite start claim and action-specific status remain
authoritative. Focused app-build/self-edit/MCP/registry suites passed **218**;
the full Python unit/integration suite passed **3,030**, with **4 skipped**,
**11 warnings**, and **2 subtests**. Ruff `F`/`I`, compileall, and
`git diff --check` passed. See the [app-build identity receipt](../acceptance/verified-gap-closure/GC24-02-appbuild-start-requires-action-id-2026-09-25.md).
Other mutation families and full lifecycle ownership remain open.

Reconciled 2026-09-22 against main `88b206f`. The figures below are the
counts recorded in the committed 2026-09-18 receipts (Mac, release-review
worktree). They are receipt-time counts, not current pass counts; the current
static test counts at `88b206f` are given for comparison.

- Python: **2611 passed, 4 skipped** in the Mac receipt. At `88b206f` on
  Linux, `pytest tests/unit` gave **2,526 passed** (run by Claude
  2026-09-22; a different platform and collection, so not directly comparable).
- JarvisKit: **190 passed** in the linked receipt. The earlier "195 passed"
  figure here (including the five `GraphImageRequestsTests`) is not recorded
  in a committed receipt; the source at `88b206f` has **195** static
  `func test` methods, so 195 is a static count, not a verified pass count.
- MortimerHost: **244 executed, 3 skipped, 0 failures** in the latest
  complete run in the receipt; the display-dependent skips require two
  connected displays and are covered by live monitor receipts. The source at
  `88b206f` has **250** static `func test` methods; no committed receipt
  records a run of all 250.
- Focused native rerun: **47 passed** in
  [current-focused-native-2026-09-18.md](../acceptance/command-console/receipts/current-focused-native-2026-09-18.md)
  (`ScreenPlacementTests` 8 + Command Center/rendering/ownership filter 39).
  The later full-verification receipt records `ScreenPlacementTests` **9/9**,
  which matches the 9 static tests now in that file.
- Plan manifest: **7 passed** (receipt); also 7 passed at `88b206f` on Linux,
  2026-09-22.
- Formatting: `git diff --check` passed.

The latest complete verification is recorded in
[full-verification-2026-09-18.md](../acceptance/command-console/receipts/full-verification-2026-09-18.md).

## Model use enhancements

Added 2026-09-22 (reconciled against main `88b206f`). The detailed record is
[model-use-enhancements/STATUS.md](../acceptance/model-use-enhancements/STATUS.md). The
committed receipts under `model-use-enhancements/receipts/` show only the
following:

| Requirement | Committed receipt | What it shows | Status |
| --- | --- | --- | --- |
| Call-site inventory (MAR-G) | `model-call-site-inventory-2026-09-20.json` | Static inventory: 13 call sites, 13 covered, 0 review-required, `secret_free: true` | Implementation evidence; enabled-mode runtime evidence open |
| Secret-free route readiness | `route-readiness-2026-09-20.json`, `vault-backed-route-readiness-2026-09-20.json` | Without the vault, every workload reports `ANTHROPIC_API_KEY is not set`; with the vault, `ready_issues: []`, `routing_enabled: false`, SAYGM route `credential_present: false`, no catalog or probe run | Readiness report only |
| SAYGM (MAR-E) | `saygm-readiness-2026-09-20.json` | Catalog check failed closed: `SAYGM_API_KEY is not set` | Open |
| Subscriptions (MAR-F) | `subscription-probes-2026-09-20.md`, `subscription-readiness-2026-09-20.json` | Codex probe returned `SUBSCRIPTION_PROBE_OK`; Claude reported `Not logged in` | Open |
| Memory pilot (MAR-I) | `../memory-automation/provider-shadow-receipt.json`, `../memory-automation/rollout-monitoring-receipt.json` | Direct-API 8-case synthetic memory shadow (8/8, no regression) and offline rollout gate; routing layer not enabled | Open |

The status file also describes user-run checks on 2026-09-21 and 2026-09-22
(Claude login and probe, SAYGM catalog with 56 models). They are not recorded
in a committed receipt and remain unverified.

The exact procedures for remaining rows are in
[ACCEPTANCE_RUNBOOK.md](../acceptance/ACCEPTANCE_RUNBOOK.md). Detailed checklists remain in
[memory status](../acceptance/memory-automation/STATUS.md), [Command Center status](../acceptance/command-console/STATUS.md),
[model-use status](../acceptance/model-use-enhancements/STATUS.md),
and [adaptive-interface release readiness](../acceptance/adaptive-interface/RELEASE_READINESS.md).

**2026-09-25 progress — plan-start action identity and regression repair:**
`/api/plan/start` and its MCP helper now reject confirmed starts without the
injected stable action identity. The sidecar checks missing, blank, and
overlong IDs before reviewing a document or dispatching a worker; accepted
requests keep the existing durable SQLite claim. The full regression run
exposed a test-fixture mismatch in the separate review mode, which was fixed
by modeling the same system-injected identity used by the registered caller.
Focused plan/review/MCP/registry tests passed **117**; `RUN_LIVE=0 ./.venv/bin/python -m pytest tests/unit tests/integration -q --tb=short` passed **3,033**, with **4 skipped**, **11 warnings**, and **2 subtests**. Ruff `F`/`I`, compileall, and `git diff --check` passed. See the [receipt](../acceptance/verified-gap-closure/GC24-02-plan-start-requires-action-id-2026-09-25.md). Research and other mutating action families remain open.

**2026-09-25 progress — paid research-start identity and duplicate control:**
`research_compare_start` and `research_status` now use the existing hidden
SubAgent execution-ID injection. Preview remains unchanged; confirmed research
fails closed without an ID, records its existing SQLite action claim, and
refuses a duplicate dispatch. The focused research/MCP/registry suite passed
**71** with **1 skipped**; the full Python unit/integration suite passed
**3,039**, with **4 skipped**, **11 warnings**, and **2 subtests**. Ruff
`F`/`I`, compileall, and `git diff --check` passed. See the [dated
receipt](../acceptance/verified-gap-closure/GC24-02-research-start-action-id-2026-09-25.md).
Other mutation families and full lifecycle ownership remain open.

**2026-09-25 progress — F1 key-health log redaction verified:** current
credential-health probes expose only a bounded outcome and fixed detail;
provider response text, endpoint, key environment name, and exception data
are absent from logs/status details. `tests/unit/test_keyhealth.py` passed
**12**; Ruff `F`/`I` and `git diff --check` passed. The accumulated full
Python run on this source snapshot passed **3,039**, with **4 skipped**, **11
warnings**, and **2 subtests**. See the [F1 receipt](../acceptance/verified-gap-closure/GC24-03-keyhealth-log-redaction-2026-09-25.md). Other F rows and the full privacy audit remain open.

**2026-09-25 progress — F2/F7 knowledge-base log redaction verified:** KB
transport failures retain only a bounded exception class, while configured
endpoints and backend exception details stay out of logs. Rejected-write logs
retain a fixed event without scanner reasons or record IDs. `test_mcp_kb_logic.py`
passed **13**; Ruff `F`/`I` and `git diff --check` passed. The accumulated full
Python unit/integration run passed **3,039**, with **4 skipped**, **11
warnings**, and **2 subtests**. See the [F2/F7 receipt](../acceptance/verified-gap-closure/GC24-03-mcp-kb-diagnostic-redaction-2026-09-25.md). Wider KB and privacy data flow remain open.

**2026-09-25 progress — F4 configuration-bridge redaction verified:** a
canary forces typed settings loading to fail; the bridge logs only the
exception type, keeps the dotenv fallback, and omits the private path/value.
`test_config.py` passed **17**, Ruff `F`/`I`, compileall, and
`git diff --check` passed. See the [F4 receipt](../acceptance/verified-gap-closure/GC24-03-config-bridge-log-redaction-2026-09-25.md).
The full Python suite after the F3 registry canaries passed **3,043**, with
**4 skipped**, **11 warnings**, and **2 subtests**. Broader
configuration/privacy gates remain open.

**2026-09-25 progress — F3 registry diagnostic redaction verified:** canary
coverage now proves malformed skill YAML, invalid dynamic sources, and
malformed model-upgrade configuration do not leak paths, source values, or
parser details. Existing tests retain registry failure/fallback behavior and
cover MCP tool/shutdown exception redaction. `test_registry.py` passed **21**;
Ruff `F`/`I` and `git diff --check` passed. The full Python unit/integration
suite passed **3,043**, with **4 skipped**, **11 warnings**, and **2
subtests**. See the [F3 receipt](../acceptance/verified-gap-closure/GC24-03-registry-diagnostic-redaction-2026-09-25.md). Broader environment-scope and privacy gates remain open.

**2026-09-25 progress — F5 workflow-loader log redaction verified:** malformed
workflow YAML logs only a bounded exception class; invalid workflow files use
a fixed reason without their path. Canary tests prove the source/path are
absent and that invalid workflows remain skipped while valid ones load.
`test_workflows.py` passed **22**; the full Python unit/integration suite
passed **3,043**, with **4 skipped**, **11 warnings**, and **2 subtests**.
Ruff `F`/`I` and `git diff --check` passed. See the [F5 receipt](../acceptance/verified-gap-closure/GC24-03-workflow-loader-log-redaction-2026-09-25.md). Prompt and general workflow data-flow policy remain open.

**2026-09-25 progress — F6 console-validation redaction verified:** malformed
inventory is not applied; malformed requests do not invoke the action callback
or echo the invalid field. Fixed rejection events remain observable.
`test_bot_wiring.py` plus the protocol/event tests passed **78**; the full
Python unit/integration suite passed **3,045**, with **4 skipped**, **11
warnings**, and **2 subtests**. See the [F6 receipt](../acceptance/verified-gap-closure/GC24-03-console-validation-log-redaction-2026-09-25.md).

**2026-09-25 progress — F9 clipboard failure redaction verified:** failed
`pbcopy`/`pbpaste` output is omitted from logs and caller-visible errors;
clear-to-arm and one-read semantics remain intact. `test_clipboard.py` passed
**28**; the full Python suite passed **3,045**, with **4 skipped**, **11
warnings**, and **2 subtests**. See the [F9 receipt](../acceptance/verified-gap-closure/GC24-03-clipboard-failure-redaction-2026-09-25.md).

**2026-09-25 progress — F10 KB-digest log redaction verified:** digest
failure/rejection/write/flush logs omit session IDs, scanner reasons, content,
backend details, and tracebacks while preserving best-effort returns and
flush behavior. `test_kb_digest.py` passed **9**; the full Python suite passed
**3,045**, with **4 skipped**, **11 warnings**, and **2 subtests**. See the
[F10 receipt](../acceptance/verified-gap-closure/GC24-03-kb-digest-log-redaction-2026-09-25.md).

**2026-09-25 progress — F11/F12 identity-path diagnostics redacted:** invalid
tenant IDs retain the `local` fallback without logging the value; missing-vault
startup remains visible without its configured filesystem path. The
tenant/vault/usage-ledger focused suites passed **39**, and the full Python
suite passed **3,045**, with **4 skipped**, **11 warnings**, and **2 subtests**.
See the [F11](../acceptance/verified-gap-closure/GC24-03-tenant-id-log-redaction-2026-09-25.md)
and [F12](../acceptance/verified-gap-closure/GC24-03-vault-path-log-redaction-2026-09-25.md) receipts.

**2026-09-25 progress — F13 usage-ledger diagnostics redacted:** debug
output contains normalized token/cache counters, unknown rung warnings omit
user-provided labels while retaining the ledger row, and persistence errors
emit only the exception class. Focused tenant/vault/usage-ledger suites passed
**39**; full Python passed **3,045**, with **4 skipped**, **11 warnings**, and
**2 subtests**. See the [F13 receipt](../acceptance/verified-gap-closure/GC24-03-usage-ledger-log-redaction-2026-09-25.md). Provider billing and usage completeness remain separate open requirements.
