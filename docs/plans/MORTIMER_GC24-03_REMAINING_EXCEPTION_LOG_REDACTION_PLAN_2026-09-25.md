# GC24-03 — Remaining Sensitive Diagnostic-Logging Plan

**Prepared:** 2026-09-25  
**Scope:** residual traceback, path-bearing, dynamic-field, and stdout
diagnostic sinks found in the latest isolated-tree source scan.  
**State:** slices A–E have scoped receipts; slice F now has twenty-five bounded
source/test entries, including newly indexed skill/workflow injection
metadata. Revalidate slice status against current code and receipts. The full
GC24-03 privacy audit remains open.  
**Target:** the existing dirty isolated worktree `codex/isolated-20260924`.

This is a focused continuation of the
[Fresh Review Implementation Plan](MORTIMER_FRESH_REVIEW_IMPLEMENTATION_PLAN_2026-09-25.md)
and GC24-03. The privacy plan, GC24 closure criteria, feature plans, and dated
receipts remain authoritative. Keep their stricter requirements. This plan
does not assert that the grep inventory is a complete source-to-sink audit.

## Goal

Remove user content, secrets, local paths, provider/backend messages, and
unnecessary identifiers from the remaining diagnostic sinks without reducing
the operational value of diagnostics or changing feature behavior. Each
bounded change must preserve the existing success/failure policy, retry,
cleanup, and fail-open/fail-closed behavior. A model implementing a slice
must not broaden scope or resolve an architectural ambiguity by inventing a
new logging, telemetry, or error-reporting system.

## Fixed constraints

- Work only in the designated isolated worktree. Before each slice, record
  branch, base/HEAD, dirty and untracked files, sibling worktrees, toolchain,
  and concurrent file ownership. Preserve all existing edits; do not clean,
  reset, transplant, commit, push, merge, or deploy.
- Re-read the exact source and tests before editing. The source scan below is
  a starting index, not proof that a sink still exists at the same line or
  that all sinks have been found.
- Do not log exception messages, tracebacks, request/prompt/result text,
  memory keys or values, raw file paths, audio/WAV paths or contents, tool or
  provider responses, credentials, headers, environment values, or raw
  identifiers that can identify a user or session.
- Prefer a stable event name, exception class, bounded enum/reason, and only
  an already-approved opaque correlation ID when needed. Do not add a new
  identifier or persist new data just to improve logs.
- Keep exception handling semantics unchanged. Do not swallow new failures,
  change retry/cancellation policy, or turn a best-effort operation into a
  fatal one (or vice versa).
- Use synthetic canary strings and fake paths in tests. Never use real user
  content, secrets, or production logs as fixtures.
- Keep this work separate from the broader open GC24-03 question of content
  flow through providers, tools, memory, TTS, persistence, display,
  copy/share/export, and telemetry. Log redaction alone does not prove those
  boundaries.

## Newly indexed residual sinks

The 2026-09-25 source scan found these candidate sinks. Confirm each against
current code and runtime reachability before changing it; classify false
positives and already-fixed paths in the slice receipt.

| Slice | Candidate owners and current evidence | Main exposure to assess |
|---|---|---|
| A — memory extraction and worker | Current exception, rejection, and extraction diagnostics in `jarvis/memory_extraction.py` and `jarvis/memory_extraction_worker.py` are redacted and canary-tested in the [slice A receipt](../acceptance/verified-gap-closure/GC24-03-memory-extraction-worker-log-redaction-2026-09-25.md). | Closed only for the current listed log paths. Broader memory content flow remains open under GC24-03. Recheck the source before any follow-up; do not infer full privacy closure from this receipt. |
| B — speaker profiles and voice gate | Profile/metadata, model, embedding, capture, score, and delivery log paths are redacted and canary-tested in the [slice B receipt](../acceptance/verified-gap-closure/GC24-03-speaker-audio-log-redaction-2026-09-25.md). | Closed only for the listed speaker/gate log paths. Broader voiceprint/audio data-flow and retention remain open. |
| C — council and upgrade orchestration | Council and upgrade-agent exception paths use bounded event/error-class logging; proposer/judge messages, user-choice labels, and unknown retry-outcome values are redacted. See the [slice C receipt](../acceptance/verified-gap-closure/GC24-03-council-upgrade-log-redaction-2026-09-25.md). | Closed only for the exception/log paths tested in slice C. Council model-request, durable-record, and result data flow remain open. |
| D — screen capture and pruning | Screen capture, prune, retention, and model-failure logs are metadata-only and canary-tested in the [slice D receipt](../acceptance/verified-gap-closure/GC24-03-screen-log-redaction-2026-09-25.md). | Closed only for the listed log sinks. Low-confidence image retention and broader screen data flow remain open for privacy review. |
| E — procedure, skills, usage, and shared-content accounting | The listed paths are redacted and canary-tested in the [slice E receipt](../acceptance/verified-gap-closure/GC24-03-procedures-skills-usage-log-redaction-2026-09-25.md). | Closed only for those logging paths. Procedure/skill prompt injection and provider/model data flow remain open. |
| F — residual runtime diagnostics across provider, configuration, self-edit, IPC, transcript persistence, notification, client-message, route-refusal, verification, and transcript-content paths | Initially found in key health, KB/MCP, registry, config bridge, workflow, and console diagnostics. Expanded source scan added clipboard subprocess output, KB digest session identifiers/rejection details, invalid tenant ID values, vault paths, usage-ledger stderr payloads, self-edit staging IDs, skill/workflow injection labels, transcript persistence exceptions, raw `voice/set`/`ui/noop` client-message fields, reminder row IDs, override-refusal profile/reason fields, the branch label from self-edit appearance verification, and raw nonsensitive transcript text in the persistent bot log. | Provider/config details, paths, clipboard content, provider usage response fields, user/session/action/reminder identifiers, local skill/workflow metadata, client-supplied voice/reason values, route refusal details, user-selected branch names, and user/assistant transcript content. Reconcile existing receipts and current dirty owners before editing. |

### Slice F — executable ownership map

The following is the initial execution map from the current dirty-tree scan.
Treat it as a navigation aid: re-read current code, tests, and ownership
before editing because line numbers and behavior may have changed. Keep each
row a separate commit-sized *logical slice* (the work remains uncommitted in
this task); do not combine merely to reduce test runs.

| Order | Source owner and observed sink | Test owner and required proof | Fixed implementation boundary |
|---|---|---|---|
| F1 | `jarvis/keyhealth.py`: probe failure detail is assembled from exception class plus message, stored in status details, and logged alongside key environment name/base URL; outer catch logs raw exception. | `tests/unit/test_keyhealth.py`: inject canaries in exception text, endpoint, and environment/key label; capture logs and status details; prove the existing healthy/unhealthy/unknown classification and return shape. | Implemented and canary-tested in the current isolated tree; see the [F1 receipt](../acceptance/verified-gap-closure/GC24-03-keyhealth-log-redaction-2026-09-25.md). Only probe outcomes/categories remain visible; existing health classification and fallback behavior remain unchanged. |
| F2 | `mcp_servers/mcp_kb/logic.py`: unreachable-provider warning includes configured base URL and raw exception text. | `tests/unit/test_mcp_kb_logic.py`: fake transport error containing distinct URL/body canaries; assert the warning remains and canaries are absent. | Implemented and canary-tested; see the [F2/F7 receipt](../acceptance/verified-gap-closure/GC24-03-mcp-kb-diagnostic-redaction-2026-09-25.md). Return behavior remains unchanged. |
| F3 | `jarvis/skills/registry.py`: unreadable/missing skill and model-upgrade/config diagnostics include paths, raw parser/exception details, and dynamic MCP validation text; tool failure also carries a run identifier. | `tests/unit/test_registry.py`; inspect related integration tests `tests/integration/test_registry.py` and `tests/integration/test_vault_registry.py` if present in the current tree. Use synthetic private-path/config/provider canaries; prove the same discovery, validation, and tool-failure result. | Implemented and canary-tested in the current isolated tree; see the [F3 receipt](../acceptance/verified-gap-closure/GC24-03-registry-diagnostic-redaction-2026-09-25.md). Focused registry suite passed **21**; full regression passed **3,043**, with **4 skipped**, **11 warnings**, and **2 subtests**. |
| F4 | `jarvis/config.py`: environment bridge degradation log interpolates raw exception detail. | `tests/unit/test_config.py`: force bridge exception with path/value canaries; assert safe event/type only and unchanged settings fallback. | Implemented and canary-tested; see the [F4 receipt](../acceptance/verified-gap-closure/GC24-03-config-bridge-log-redaction-2026-09-25.md). Best-effort dotenv fallback and environment precedence are unchanged. |
| F5 | `jarvis/workflows.py`: invalid workflow diagnostic includes the local file path. | `tests/unit/test_workflows.py`: load an invalid workflow from a synthetic private path; assert diagnostic identifies invalid/missing-name condition without path, and same workflow is rejected. | Implemented and canary-tested; see the [F5 receipt](../acceptance/verified-gap-closure/GC24-03-workflow-loader-log-redaction-2026-09-25.md). Focused suite passed **22**; full suite passed **3,043**, with **4 skipped**, **11 warnings**, and **2 subtests**. |
| F6 | `jarvis/bot/pipeline.py`: console inventory/request validation warnings interpolate `ValueError` text, which may contain rejected IDs or user-supplied values. | `tests/integration/test_bot_wiring.py`: exercise both rejection paths with distinct request-value canaries; assert safe warning and unchanged rejection/no-dispatch behavior. | Implemented and canary-tested; see the [F6 receipt](../acceptance/verified-gap-closure/GC24-03-console-validation-log-redaction-2026-09-25.md). Rejected inventory is not applied and malformed requests do not invoke the action callback. |
| F7 | `mcp_servers/mcp_kb/logic.py`: `kb_write_rejected` includes a dynamic reason and record ID. | `tests/unit/test_mcp_kb_logic.py`: reject a write using synthetic reason/ID canaries; assert bounded diagnostic and unchanged rejection result. | Implemented and canary-tested; see the [F2/F7 receipt](../acceptance/verified-gap-closure/GC24-03-mcp-kb-diagnostic-redaction-2026-09-25.md). The fixed rejection event is retained; the returned behavior is unchanged. |
| F8 | `jarvis/bot/pipeline.py`: agent progress stdout reaches persistent `logs/bot.log`; verify no task/title/tool values are emitted. | `tests/integration/test_bot_wiring.py` and `tests/unit/test_agent_events.py`: inject task/title canaries; assert static activity markers remain and content is absent from stdout and UI delivery remains unchanged. | The current `bot_event_log` emits only fixed `[AGENT]` event names and omits payload fields; see the [agent/event receipt](../acceptance/verified-gap-closure/GC24-03-agent-event-findings-log-redaction-2026-09-25.md). The receipt covers related event callbacks; broad data-flow remains open. |
| F9 | `jarvis/clipboard.py`: `pbcopy` failure output is written to the log and returned to the caller; `pbpaste` failure output is returned, so partial clipboard data could cross the failure path. | `tests/unit/test_clipboard.py`: return synthetic output canaries for clear/read failures; assert neither logs nor tool results contain them, and arming/read failure behavior is unchanged. | Implemented and canary-tested; see the [F9 receipt](../acceptance/verified-gap-closure/GC24-03-clipboard-failure-redaction-2026-09-25.md). Exit-code diagnostics and one-read-per-arm behavior are preserved. |
| F10 | `jarvis/kb_digest.py`: digest failure/rejection/write/flush diagnostics include session IDs; rejection logs a scanner reason. | `tests/unit/test_kb_digest.py`: canary session ID, digest text, provider/KB error; assert stage events remain and all canaries are absent. | Implemented and canary-tested; see the [F10 receipt](../acceptance/verified-gap-closure/GC24-03-kb-digest-log-redaction-2026-09-25.md). Best-effort flush/skip/write behavior remains unchanged. |
| F11 | `jarvis/tenant.py`: invalid user/tenant ID value is interpolated into warning logs. | `tests/unit/test_tenant.py`: invalid ID canary; assert fallback remains `local` and value is absent from logs. | Implemented and canary-tested; see the [F11 receipt](../acceptance/verified-gap-closure/GC24-03-tenant-id-log-redaction-2026-09-25.md). The fixed invalid-ID event and `local` fallback remain. |
| F12 | `jarvis/vault.py`: missing-vault event interpolates the configured local path. | `tests/unit/test_vault.py`: configured private path canary with absent vault; assert injection returns zero and the path is absent from logs. | Implemented and canary-tested; see the [F12 receipt](../acceptance/verified-gap-closure/GC24-03-vault-path-log-redaction-2026-09-25.md). Startup fallback and event visibility remain. |
| F13 | `jarvis/usage_ledger.py`: stderr prints raw usage object in debug mode, dynamic unknown rung, and raw persistence exception. | `tests/unit/test_usage_ledger.py`: provider usage canary, rung canary, and DB exception/path canary; assert normalized token counts/closed events remain, no canaries print, and ledger persistence semantics are unchanged. | Implemented and canary-tested; see the [F13 receipt](../acceptance/verified-gap-closure/GC24-03-usage-ledger-log-redaction-2026-09-25.md). Debug mode reports normalized counters; unknown rung rows are retained; DB failures log only bounded class. |
| F14 | `jarvis/admin/server.py`: staging-resolution event logs requested and selected staging IDs. | `tests/unit/test_admin_selfedit.py`: wrong/mangled requested-ID canary with one live staged action; assert the action still resolves and starts, while neither requested nor selected ID is logged. | Implemented and verified; see [F14 receipt](../acceptance/verified-gap-closure/GC24-03-selfedit-staging-log-redaction-2026-09-25.md). Exact single-live-stage fallback and consumption behavior remain. |
| F15 | `jarvis/agents/base.py`: refuse-mode diagnostic logs the full model-route/profile refusal reason, while the user-facing refusal must continue to explain the cause. | `tests/unit/test_subagent.py`: refusal canary in profile/error detail; assert user result still explains the refusal and logs contain only the event/agent metadata. | Implemented and verified; see [F15 receipt](../acceptance/verified-gap-closure/GC24-03-model-override-refusal-log-redaction-2026-09-25.md). Caller-facing refusal and no-fallback behavior remain. |
| F16 | `jarvis/admin/server.py`: sidecar startup log includes the absolute repository root. | `tests/unit/test_admin_api.py`: inspect the production `main()` logging call and capture the event; assert host/port remain and the root path is absent. | Implemented and verified; see [F16 receipt](../acceptance/verified-gap-closure/GC24-03-sidecar-root-log-redaction-2026-09-25.md). This does not assert live deployed startup. |
| F17 | `jarvis/council/council.py`: `council_too_small` logs an opaque round ID and a reason that may contain provider/model resolution details. | `tests/unit/test_council_gather.py`: inject round/reason/path canaries; assert logs omit them while the result and durable record retain their existing values. | Implemented and verified; see [F17 receipt](../acceptance/verified-gap-closure/GC24-03-council-small-round-log-redaction-2026-09-25.md). Durable council privacy remains in the broader GC24-03 audit. |
| F18 | `jarvis/agents/base.py`: skill/workflow injection diagnostics include local names and workflow source labels, which may be user-authored or reveal filesystem metadata. | `tests/unit/test_subagent.py`: inject distinct skill-name, workflow-name, and source-label canaries; assert injection events remain useful while the labels are absent from logs and prompt/result behavior is unchanged. | Implemented and canary-tested in the dirty isolated tree; see the [F18 receipt](../acceptance/verified-gap-closure/GC24-03-skill-workflow-injection-log-redaction-2026-09-25.md). This closes only these log fields, not the broader privacy flow. |
| F19 | `jarvis/bot/transcript_log.py`: `_persist` prints the raw DB exception to stdout, which is captured by the supported bot log. | `tests/unit/test_sensitive_turn.py`: force a persistence failure containing a distinct exception-message canary; assert the failure remains observable by exception class, the canary is absent, and `_persist` remains best-effort. | Implemented and canary-tested in the dirty isolated tree; see the [F19 receipt](../acceptance/verified-gap-closure/GC24-03-transcript-persistence-error-log-redaction-2026-09-25.md). This does not close transcript content data flow or the broader audit. |
| F20 | `jarvis/bot/pipeline.py`: `voice/set` prints the raw client-supplied voice value before validating it against the catalog. | `tests/integration/test_bot_wiring.py`: drive a client message with an unknown voice canary through the bounded log-event helper; assert the event remains visible and the supplied value is absent. Preserve current-voice reconciliation for invalid choices. | Implemented and canary-tested; see the [F20–F21 receipt](../acceptance/verified-gap-closure/GC24-03-client-app-message-log-redaction-2026-09-25.md). Voice validation and response semantics remain unchanged. |
| F21 | `jarvis/bot/pipeline.py`: `ui/noop` prints a client-supplied reason that is also spoken to the user. | `tests/integration/test_bot_wiring.py`: pass a synthetic reason canary through the bounded log-event helper; assert the event is visible and the reason is absent from logs. Preserve exact speech content and length guard. | Implemented and canary-tested; see the [F20–F21 receipt](../acceptance/verified-gap-closure/GC24-03-client-app-message-log-redaction-2026-09-25.md). TTS content, input validation, and user feedback remain unchanged. |
| F22 | `jarvis/admin/reminder_notifier.py`: post/mark failure logs include the reminder database row ID. | `tests/unit/test_reminder_notifier.py`: inject a failed reminder with a known synthetic row and exception; assert event/error class remain and the row ID/message are absent while the reminder can still retry. | Implemented and canary-tested; see the [F22 receipt](../acceptance/verified-gap-closure/GC24-03-reminder-row-id-log-redaction-2026-09-25.md). Retry, notification, and mark-notified behavior remain unchanged. |
| F23 | `jarvis/agents/base.py`: `subagent_override_refused` logs a model-profile override and its full refusal reason, then returns the explanation to the caller. | `tests/unit/test_subagent.py`: inject profile/reason canaries; assert caller result still explains refusal, no provider is called, and captured logs contain only the stable event/agent. | Implemented and canary-tested; see the [F23 receipt](../acceptance/verified-gap-closure/GC24-03-model-override-refusal-log-redaction-2026-09-25.md). User-facing refusal and no-fallback behavior remain unchanged. |
| F24 | `jarvis/admin/server.py`: self-edit appearance verification logs the returned Git branch label. | `tests/unit/test_admin_api.py`: inject a user-selected branch canary; assert the response retains the branch and captured logs retain only verification success/failure. | Implemented and canary-tested; see the [F24 receipt](../acceptance/verified-gap-closure/GC24-03-selfedit-branch-label-log-redaction-2026-09-25.md). The endpoint response and appearance behavior remain unchanged. |
| F25 | `jarvis/bot/transcript_log.py`: ordinary user and assistant transcript contents are printed to persistent stdout logs when the financial detector does not arm. | `tests/integration/test_bot_wiring.py` and `tests/unit/test_sensitive_turn.py`: inject synthetic ordinary and sensitive user/assistant canaries; assert speaker/timing markers remain, none of the transcript text reaches stdout, and existing conversation-row persistence/suppression behavior is unchanged. | Implemented and canary-tested; see the [F25 receipt](../acceptance/verified-gap-closure/GC24-03-transcript-content-log-redaction-2026-09-25.md). Emit only the existing `USER:`/`MORTIMER:` marker plus bounded character-count metadata; preserve in-app delivery, non-sensitive DB persistence for memory, sensitive-turn suppression, and latency parsing. |

If current source no longer contains a listed sink, record it as already
fixed or a false positive in the final receipt, with the exact source/test
evidence. If an additional sensitive sink appears while tracing a row, add it
to the inventory before implementation rather than silently expanding scope.

The index began with a search for `logger.exception`, `exc_info=True`, and
equivalent traceback output in `jarvis/` and `mcp_servers/`; the expanded F
map also includes dynamic log fields and stdout progress output. Every
implementation slice must repeat the search across production code, inspect
logging wrappers and structured exception serializers, and search for
`traceback`, `stack_info`, `format_exc`, f-string/interpolated exception text,
dynamic `logger`/`print` fields, and equivalent sinks that a narrow grep
might miss.

**2026-09-25 progress — slice A, memory extraction and worker logs:** the
current source still contained traceback output and memory/session/cursor
identifiers despite an older scoped receipt. These paths now emit bounded
events, aggregate counts, bounded exception class names, and existing
admission categories only. Focused extraction/worker tests passed **64**;
Ruff `F`/`I`, compileall, and `git diff --check` passed. See the [slice A
receipt](../acceptance/verified-gap-closure/GC24-03-memory-extraction-worker-log-redaction-2026-09-25.md).
This does not close the memory data-flow audit or slices B–E.

**2026-09-25 progress — slice B, speaker and audio-gate logs:** profile,
metadata, model, WAV, capture, scoring, and delivery diagnostics now omit
paths, raw exception text/tracebacks, transcript content, and turn IDs while
keeping bounded event/error classes and existing score/window/duration
metrics. Focused speaker suites passed **69** with **2 dependency deprecation
warnings**; Ruff `F`/`I`, compileall, and `git diff --check` passed. See the
[slice B receipt](../acceptance/verified-gap-closure/GC24-03-speaker-audio-log-redaction-2026-09-25.md).
This does not close audio data-flow or slices C–E.

**2026-09-25 progress — slice C, council and upgrade logs:** exception
tracebacks/messages were removed from council and upgrade-agent best-effort
failure paths; proposer/judge exception strings, user-choice labels, and
unknown outcome values are no longer logged. Focused council/upgrade unit and
integration suites passed **88**; Ruff `F`/`I`, compileall, and
`git diff --check` passed. See the [slice C receipt](../acceptance/verified-gap-closure/GC24-03-council-upgrade-log-redaction-2026-09-25.md).
This does not close council content data flow or slices D–E.

**2026-09-25 progress — slice D, screen and pruning logs:** screen logs no
longer include questions, model answers, paths, display identifiers, raw
retention settings, exception text, or tracebacks; capture, retention, and
pruning behavior remain unchanged. Focused screen tests passed **28**; Ruff
`F`/`I`, compileall, and `git diff --check` passed. See the [slice D
receipt](../acceptance/verified-gap-closure/GC24-03-screen-log-redaction-2026-09-25.md).
Low-confidence image retention and broader screen data flow remain open.

**2026-09-25 progress — slice E, procedures/skills/usage/shared content:**
procedure, skill parsing, TTS/LLM usage, and shared-content usage failures now
omit raw content, paths, identifiers, exception text, and tracebacks while
preserving existing failure behavior and aggregate problem counts. Focused
suites passed **131** with **1 dependency deprecation warning**; Ruff `F`/`I`,
compileall, and `git diff --check` passed. See the [slice E
receipt](../acceptance/verified-gap-closure/GC24-03-procedures-skills-usage-log-redaction-2026-09-25.md).

**2026-09-25 newly indexed slice F:** the repository-wide residual search
expanded the original key-health, MCP, registry, config-bridge, workflow,
and console diagnostics to include clipboard failures, digest identifiers,
tenant/vault values, usage output, self-edit identifiers, council metadata,
and skill/workflow injection labels. Confirm current implementations and
receipts row by row; the inventory is a starting index, not proof of complete
privacy coverage.

## Ordered implementation sequence

### 0. Reconcile and prove the inventory

Read the current GC24-03 gap register, all directly relevant receipts, the
listed source modules, tests, and logging configuration. Repeat broad source
searches and follow data from the affected exception origin into the emitted
record. Record which entries remain live, which are already covered, and
which sinks were newly found. Do not edit sources owned by concurrent work
until the owner is reconciled.

**Pass:** each live candidate has a source location, triggering input/error,
data that could reach the log, current expected behavior, test owner, and one
bounded slice. The resulting inventory is saved in the dated receipt or a
linked audit artifact.

### 1. Implement the remaining independent slice F rows

Slices A–E already have scoped receipts and are not reimplemented by this
plan. Take each remaining F row one at a time, with one owner and minimal files. For each
catch, replace traceback/message/path output with a bounded event and
approved metadata. If the exception class itself is not a safe bounded
value, map it to a stable category instead of formatting it.

Add negative canaries at the logging boundary. Inject exceptions containing
distinct markers for user content, backend detail, and path data. Assert that
the event remains observable, expected safe fields remain present, and none
of the markers, paths, or traceback frame/local content reaches captured
logs. Also assert the pre-existing return value, retry/cleanup behavior, and
failure policy are unchanged.

**Slice pass:** focused tests pass; applicable Ruff/type/compile checks pass;
`git diff --check` passes; review confirms there is no unrelated change; a
dated receipt records exact files, test commands/counts, skipped checks, and
remaining scope. Update the GC24-03 register/status only for the sink class
actually tested.

### 2. Re-scan and validate the combined result

After slices A–F, repeat the broad source search and manually inspect
remaining results. Do not mechanically remove every traceback: classify
whether the source is content-bearing, path-bearing, secret-bearing, or a
strictly bounded non-sensitive subsystem. Any remaining traceback must have
an explicit reason, demonstrated non-sensitive input boundary, and negative
canary. Run the relevant focused suites and the full Python unit/integration
suite for the exact accumulated source snapshot.

**Pass:** all identified sensitive exception paths have canary-backed
redaction, all remaining traceback sites are dispositioned with evidence,
and the status statement still clearly says the broader source-to-sink audit
is open where it is open.

## Required validation and receipt format

For each changed slice, use the repository's actual test environment and
record commands verbatim. At minimum:

1. A focused test for every modified event category, with multiple unique
   canaries and a captured-log assertion.
2. Relevant module/unit and integration suites to establish the unchanged
   behavior contract.
3. Ruff checks configured by the project for changed Python source/tests;
   compile checks if used by the established workflow; `git diff --check`.
4. A final residual search and manual disposition for traceback and exception
   formatting sinks. State exactly which directories and languages were
   searched.
5. A dated receipt that names the dirty isolated snapshot and explicitly
   states that it is not a clean commit, installed-Mac, live-provider,
   deployment, or release result unless those were separately verified.

Never copy a test count from an older receipt. Do not represent skipped,
hardware-gated, provider-gated, or unexecuted checks as passing.

## Dependency and stop rules

These logging slices can proceed independently after ownership is reconciled.
They do not depend on enabling memory, calling a live provider, or changing
the model route. Do not use a live provider or production data to reproduce a
logging issue. If evidence shows a log sink is also a data-flow/policy bypass,
record it and stop that sink for the existing GC24-03 privacy-boundary plan;
do not patch only its message and declare the boundary closed. If a safe
correlation identifier or error taxonomy is unclear, preserve existing
behavior and record the decision needed rather than inventing one.

## Handoff checklist for any model

Before a slice: read this plan and the applicable GC24-03 receipt; reconcile
the dirty tree and file owner; inspect current source/tests; state the exact
invariant and files. After a slice: run focused and relevant full checks; add
the receipt; update only evidence-backed status; review the diff for content,
paths, identifiers, changed failure semantics, hidden retries, and unrelated
edits. Leave all changes uncommitted and unpushed.
