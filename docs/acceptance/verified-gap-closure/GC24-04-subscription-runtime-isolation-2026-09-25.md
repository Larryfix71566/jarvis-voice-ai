# GC24-04 receipt — subscription runtime isolation

**Date:** 2026-09-25  
**Scope:** Offline implementation and regression verification in the isolated
worktree `codex/isolated-20260924`.  
**State:** Offline implementation package complete; installed-runtime, provider,
billing, and release acceptance remain open. GC24-04/MAR-F remain open.

## Changes verified

`jarvis/subscription.py` now:

- sends Claude and Codex prompt text through stdin rather than argv;
- launches each process in a fresh system-temp working directory and directs
  child temporary files there for automatic cleanup;
- passes only an allowlisted environment with API keys, endpoint overrides,
  app-specific variables, inherited `CODEX_HOME`/`CLAUDE_CONFIG_DIR`
  overrides, and the verification gate excluded; provider CLIs use their
  standard managed configuration below `HOME`;
- uses Claude's local-version-supported `--safe-mode`, `--restricted`,
  `--tools ""`, `--disallowed-tools mcp__*`, `--no-session-persistence`, JSON
  output, and noninteractive permission controls;
- asks Codex for ephemeral execution, ignores user configuration and rules,
  uses read-only sandboxing, disables the locally known execution/browser/app
  feature families, and reads its prompt from stdin;
- strictly rejects malformed Claude JSON, explicit error envelopes, loose or
  malformed Codex JSONL, failed/missing/duplicate terminal events, and missing
  final assistant text;
- emits safe normalized error categories without copying provider diagnostics
  into the returned error message;
- uses async child-process execution for async clients and owns the POSIX
  process group. Timeout/cancellation sends TERM, allows up to two seconds for
  the group to exit, then sends KILL, waits/reaps the leader, and suppresses
  late output. Cleanup also handles a leader that exits before a descendant
  holding stdout/stderr pipes.

Codex execution is fail-closed by default. Its clients require
`JARVIS_CODEX_SUBSCRIPTION_NO_TOOLS_VERIFIED=1` before starting a process. This
is a feature gate, not proof; no current evidence authorizes setting it. Keep
it unset until the installed runtime's full tool surface is proven empty.
Read-only sandboxing and the feature-disable flags alone do not establish that
fact.

## Evidence

- Local executable inspection (no provider request): Claude Code `2.1.278`;
  Codex CLI `0.155.0-alpha.16`. Local help confirmed the invocation options
  used by the respective adapter. A fresh `codex features list` confirmed the
  feature names passed to its CLI; it did not prove that every built-in/hosted
  tool was absent at runtime. A local Claude auth-status check reported
  unauthenticated; Codex reported logged in. Neither check made a provider
  request, and neither proves a completion route works end to end.
- Official reference checks: [Claude CLI reference](https://code.claude.com/docs/en/cli-reference)
  documents stdin/pipe input, empty `--tools`, restricted mode, MCP denial,
  disabled persistence, and permission prompt behavior. OpenAI's
  [Codex exec event schema](https://github.com/openai/codex/blob/main/codex-rs/exec/src/exec_events.rs)
  defines the top-level JSONL event types. Upstream source does not prove the
  installed Codex build exposes no tools.
- Focused adapter, access-probe, routing, and execution tests:
  **87 passed**.
- Subscription adapter tests: **31 passed**, including an actual local
  subprocess-group test and an orphan-descendant timeout test. These use local
  Python fake processes; they make no provider calls.
- Full Python unit/integration suite: **3,079 passed, 4 skipped, 11 warnings,
  2 subtests**, completed in 106.02 seconds.
- Ruff for `jarvis/subscription.py` and `tests/unit/test_subscription.py`:
  passed. `compileall` for those files: passed. `git diff --check` for those
  code files: passed.

## Still open

- No provider request was made. Claude subscription authentication and
  end-to-end no-tools behavior were not live-tested; local help only confirms
  option availability.
- Codex's exact-version no-tools capability remains unproven and gated off by
  default. Do not enable it based on this receipt.
- Live route/model capability, confidential eligibility, subscription-vs-API
  billing identity, paid-overage settings, and zero-cost claims are unverified.
- Exact candidate deployment, Mac acceptance, and release sign-off remain
  open. This receipt does not close GC24-04 or MAR-F.

This receipt is limited to the named adapter implementation and tests. It does
not validate unrelated dirty files, concurrent work, merged main, or the
running Mortimer candidate.
