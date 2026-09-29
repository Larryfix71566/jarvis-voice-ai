# Mortimer — Subscription Runtime Isolation Plan

**Prepared:** 2026-09-25  
**Status:** Offline implementation package complete; installed-runtime capability, provider, billing, and release acceptance remain open.  
**Scope:** Close the newly verified subscription CLI isolation, parsing, and
cancellation gaps under GC24-04.  
**Working tree:** `codex/isolated-20260924`; inspect current dirty state and
file ownership before each further edit.

## Purpose and authority

This plan gives any implementation model a bounded sequence with fixed design,
security, and acceptance decisions. It supplements [Verified Gap
Closure](MORTIMER_VERIFIED_GAP_CLOSURE_PLAN.md), especially GC24-04 §§9.1–9.3,
and the [Model Use Enhancements](MORTIMER_MODEL_USE_ENHANCEMENTS_PLAN.md).
Those documents remain authoritative if wording differs. Keep the existing
provider-neutral execution contract and route policy; this plan hardens the
existing Claude and Codex text-only adapters in `jarvis/subscription.py`.

Do not redesign model routing, add an executor or queue, introduce a new
authentication method, change accounts, enable tool workloads, or migrate the
voice loop. Do not make live provider calls as part of unit or integration
verification. Do not claim subscription access is zero-cost from CLI output.

## Verified starting point

The source review found the following gaps in the current adapter:

- Both provider prompts are passed as positional command arguments, exposing
  prompt contents in process listings.
- Provider child processes inherit the caller's working directory. Claude may
  therefore load project instructions or customizations.
- `_subscription_env()` removes a known set of API credentials but otherwise
  inherits the environment; it is a denylist, not an allowlist.
- Claude's JSON decoder does not reject `is_error`; Codex accepts loose event
  shapes and does not require a successful terminal event. Empty or malformed
  output can become a successful empty answer.
- Async adapters run synchronous `subprocess.run` through `asyncio.to_thread`.
  Cancelling the awaiting task does not terminate or reap the provider process,
  and its late output may outlive the request.
- The installed local runtimes observed during review were Claude Code
  `2.1.278` and Codex CLI `0.155.0-alpha.16`. These are observations, not
  supported-version policy; recheck installed versions and official runtime
  controls before implementation.
- Local Claude help exposed stdin input, `--safe-mode`, `--tools ""`, JSON
  output, and disabled session persistence. Local Codex help exposed stdin,
  `--ephemeral`, `--ignore-user-config`, `--ignore-rules`, read-only sandbox,
  and JSONL output. The review did not establish a documented Codex control
  that disables every built-in tool. Do not infer that read-only sandbox means
  no tools.

These findings are limited to source and local CLI inspection. No provider
request, subscription billing check, confidential-route check, or live Mac
acceptance was performed.

Runtime references reviewed for this implementation slice:
[Claude Code CLI reference](https://code.claude.com/docs/en/cli-reference),
[Codex `exec` JSONL event schema](https://github.com/openai/codex/blob/main/codex-rs/exec/src/exec_events.rs),
[Codex CLI feature registry](https://github.com/openai/codex/blob/main/codex-rs/features/src/lib.rs),
and [Codex core tool registry](https://github.com/openai/codex/blob/main/codex-rs/core/src/tools/spec_plan.rs).
The installed CLI help/version remains the evidence for the exact local build;
upstream `main` is reference material, not proof of the installed runtime's
complete no-tools behavior.

**Implementation update, 2026-09-25:** the current isolated tree now has the
SR-2/SR-3/SR-4 adapter changes and offline tests described below. The Claude
invocation uses stdin, a temporary working directory, an allowlisted child
environment, disabled persistence, safe/restricted mode, and an empty tools
list. The child environment no longer inherits `CODEX_HOME` or
`CLAUDE_CONFIG_DIR`; each CLI uses its standard provider-managed directory
under `HOME` unless a future, separately justified configuration is approved.
The Codex invocation also uses stdin, an ephemeral isolated cwd/config,
read-only sandboxing, and explicit feature disables. Because the installed
Codex runtime's complete tool surface has not been proven absent, both Codex
client paths fail closed unless
`JARVIS_CODEX_SUBSCRIPTION_NO_TOOLS_VERIFIED=1` is set. That environment
variable is only an explicit capability gate; setting it is not itself proof
of the runtime capability. It must remain unset until exact-version acceptance
evidence shows no built-in or hosted tool can run. Tests set it only to verify
the guarded command construction with a fake executable.

The focused adapter/route suite passed **87 tests**, and the full Python
unit/integration suite passed **3,079**, with **4 skipped**, **11 warnings**,
and **2 subtests**. Ruff, compileall, and diff whitespace checks passed for
the changed adapter and tests. No provider was called. GC24-04 and MAR-F remain
open: installed-runtime tool-surface verification, live subscription
authentication/model capability, billing/overage evidence, deployment, and
candidate acceptance are not established. See the [dated
receipt](../acceptance/verified-gap-closure/GC24-04-subscription-runtime-isolation-2026-09-25.md).

## Fixed requirements

1. Keep subscription routes text-only until every non-Mortimer tool is
   demonstrably disabled. Subscription tools remain `false`; developer,
   app-builder, image, and other unsupported workloads stay unavailable.
2. Use only official provider-supported authentication and launch interfaces.
   Preserve provider-managed sign-in. Never copy OAuth material, browser
   cookies, account passwords, or the project vault into the process or
   repository.
3. Use a per-call temporary working directory outside the repository, a
   minimal allowlisted child environment, stdin or another officially
   supported non-argv prompt channel, and nonpersistent provider sessions.
4. Keep model identity, route selection, workload, privacy eligibility,
   capability, and billing status separate. Never silently substitute a
   model, route, account, or API credential.
5. A failure, cancellation, timeout, malformed response, or missing terminal
   event must fail closed. It must not become an empty or partial successful
   answer, nor publish a late result.
6. Do not claim zero cost unless account mode and paid-overage behavior are
   independently verified. A CLI `costUSD` field alone is not billing proof.

## Ordered work packages

### SR-1 — Reconfirm ownership and runtime contracts

Before editing, inspect the current branch, dirty files, and diffs for
`jarvis/subscription.py`, its tests, route configuration, and related status
documents. Preserve concurrent work. Recheck the exact installed CLI versions
and `--help` output locally; inspect current official provider documentation
for the supported subscription authentication and noninteractive invocation.
Do not emit secrets or full process environments.

Write down the exact verified flags/input/output contract per runtime. If the
provider changes behavior or an option is undocumented/unsupported, mark that
route unavailable and stop only its dependent work; do not guess a flag.

**Pass:** dated evidence names the executable/version, supported auth mode,
input channel, no-customization/no-tool controls, output envelope, and known
limits for each provider. No provider request is made.

### SR-2 — Isolate invocation context

Refactor the current adapter invocation helper so each request:

- creates a unique temporary cwd outside the repository and removes it on
  success, failure, timeout, and cancellation;
- uses an explicit allowlist of ordinary runtime variables needed by the
  executable (for example, a justified executable search path, locale, and
  home needed for provider-managed sign-in), plus only specifically justified
  provider runtime settings;
- excludes API keys, API endpoint overrides, unrelated application secrets,
  and inherited `CODEX_HOME`/`CLAUDE_CONFIG_DIR` overrides. Let each CLI use
  its standard provider-managed configuration beneath `HOME`; if a custom
  auth directory is required, document and separately justify that exact path
  before adding it to the child environment;
- preserves official account sign-in without copying or logging credentials;
- disables project instructions, hooks, plugins, external MCP, rules, and
  built-in tools using verified controls for that exact runtime version;
- sends the assembled prompt on stdin (or another documented channel) and
  never includes user or protected prompt content in argv.

Do not use Claude `--bare` if it disables the OAuth/keychain sign-in required
for the subscription route. Do not treat Codex read-only sandbox as a
no-tools control. If no verified Codex no-tools mode is available, keep Codex
subscription execution disabled until a supported mode is identified.

**Tests:** fake executable records argv, cwd, and selected environment keys;
assert prompt sent only through stdin, cwd is temporary and outside the repo,
secret and canary variables are absent, required auth context is not copied,
project configuration is not consulted, and temp content is removed on every
exit path. Never print captured credential values in test failures.

### SR-3 — Own subprocess lifecycle and cancellation

Replace the async `to_thread(subprocess.run(...))` path with an asynchronous,
owned child process. Keep a synchronous compatibility adapter only where a
current caller requires it; make it use the same isolated invocation and
strict parser. On POSIX, own the process group/session so descendants are
included. Use the platform-equivalent process-tree ownership where needed.

On request cancellation or timeout:

1. Mark the request terminal/cancelled so no later output can be published.
2. Send terminate to the owned process group.
3. Wait no more than two seconds for graceful exit.
4. Kill the group if it remains, then await/reap the process and drain/close
   pipes.
5. Propagate cancellation or the normalized timeout failure; do not return
   collected partial output as a completed answer.

Make cleanup resilient to repeated cancellation (shield only the bounded
cleanup operation) and ensure exactly one terminal outcome. Do not block the
event loop waiting on a synchronous subprocess.

**Tests:** a fake parent with a child verifies group termination, the two
second bound, kill escalation, process reaping, closed pipes, repeated
cancellation, timeout, and absence of a late result or UI/result callback.
Tests must not sleep for long real intervals; use controllable child fixtures
or short bounded waits.

### SR-4 — Strict provider response and failure handling

Use versioned, documented output schemas. For Claude JSON, validate the
top-level object, explicit successful status (`is_error` false), expected text
field, and nonempty completion as required by the runtime contract. For Codex
JSONL, validate every nonempty line, recognized event types, exactly one
successful `turn.completed` terminal event, and final assistant message
ownership. Treat `turn.failed`, `error`, malformed JSON, contradictory
terminals, nonzero exit, authentication failure, absent completion, or
unexpected schema as failure even if process exit status is zero.

Normalize errors to safe categories (authentication, allowance/credit,
capability, policy, timeout/cancel, malformed output, process failure).
Provider stdout/stderr, raw JSON, prompt text, tokens, and credential-bearing
diagnostics must not be echoed into the user answer or ordinary logs. A
partial text delta, if the existing execution contract allows one, remains
nonterminal and must be suppressed after cancel/failure.

**Tests:** current success fixtures plus malformed/truncated JSON, missing
terminal, failed/error terminal, duplicate terminal, nonzero exit with
misleading stdout, empty output, authentication failure, and valid-looking
partial output without completion. Assert safe normalized errors and no false
success.

### SR-5 — Capability and billing gates

Update capability declarations only from verified evidence. Claude or Codex
may advertise subscription text capability only when SR-1 through SR-4 pass
for that pinned runtime. Keep tool/image/streaming/confidential capabilities
off unless independently proven by their existing acceptance contracts.
Require a verified non-tool execution mode for both providers; if only one
provider can meet it, leave the other route unavailable without fallback.

Record billing observations separately from model-call outcomes. Verify plan
mode and paid-overage controls only through supported account/settings
surfaces. If that evidence is unavailable, state billing as unknown and do not
represent the route as guaranteed no-cost.

### SR-6 — Evidence, status, and handoff

Create a dated receipt recording changed files, pinned CLI versions, exact
commands, offline fake-runtime tests, process cleanup evidence, capability
gates, skips, and unresolved live/provider facts. Never include prompts,
account identifiers, credentials, or raw provider payloads. Update the existing
GC24-04/model-use status and link this plan rather than creating another
parallel tracker.

Separate these states: code implemented, local fake-runtime tests passed,
installed candidate verified, subscription authentication live, capability
verified, billing verified, and deployed/accepted. Do not mark GC24-04 closed
from local tests alone.

## Required verification and completion criteria

Before code change, run the focused subscription tests and preserve the
baseline. After each work package, run those tests plus affected routing and
execution suites, formatting/lint checks, and `git diff --check`. Run the full
Python unit/integration suite after the final source change. Use fake
executables only; do not send a provider request under this plan.

This focused implementation slice is complete only when:

- prompts never appear in process arguments;
- child cwd, environment, provider customizations, and built-in tool access
  meet the verified contracts;
- all outcomes require valid successful terminal events;
- cancellation/timeout terminates and reaps the owned process tree within the
  specified bound and cannot publish late output;
- regression tests cover all success/failure/cancellation cases;
- unsupported routes/capabilities remain gated, and evidence/status clearly
  distinguish local implementation from live auth, billing, and release
  acceptance.

If runtime controls cannot be verified, the correct completion is a documented
blocked capability with its feature gate off, not a speculative workaround.


### 2026-09-28 — staged source deployment

Runtime isolation source is deployed with main `539f8f6` through DEPLOY-MAIN.
All exact-release test gates and service health checks passed. This is source
deployment evidence only: live subscription capability/isolation and routed
provider acceptance gates remain open. See the deployment receipt under
`docs/acceptance/skills-workspace/receipts/rendering-performance-2026-09-28/`.
