---
date: 2026-11-17
system: claude
rows: [WS-13]
prs: [380]
---

# WS-13: the mail child's per-account failure reason now reaches the bot's log

System: Claude (Claude Code cloud session). Branch: `claude/mcp-mail-stderr-logging-20261117`, from `origin/next` at `efffa0a`. Draft PR into `next`. Reviewer: Kimi or Codex (no system reviews its own work).

## Why

On 2026-11-16, during Mac acceptance row M6, AT&T rejected the mail login. `logs/bot.launchd.log` showed only the brief job's per-account status (`brief_job_sent ... statuses=att=failed,...`), with no reason. The reason (`abort=login_rejected`) showed only when Larry ran `mail_headlines` by hand with logging configured.

## Cause (from the code and a local reproduction)

- `mcp_servers/mcp_mail/logic.py` already logs one content-free `mail_account_done` line per account at INFO (account, status, count state, phase, abort reason, exception type and errno, duration).
- `mcp_servers/mcp_mail/server.py` started FastMCP without configuring logging, so the `mcp_servers.mcp_mail` logger had no handler and Python dropped every INFO line. No `mcp_servers/*/server.py` configures logging.
- The child's stderr is not the problem: `jarvis/skills/registry.py` `_start_server` calls `stdio_client(params)`, whose default `errlog` (mcp 1.29.0, the lockfile pin) is the bot's own `sys.stderr`, and `scripts/launchd/com.mortimer.template.plist` writes the bot's stderr to `logs/bot.launchd.log`. In the reproduction, FastMCP's own startup lines reached the captured stderr; `mail_account_done` did not.
- `JARVIS_LOG_LEVEL` is in the registry's `BASE_ENV_KEYS`, so the child receives the bot's level.

## What changed

- `mcp_servers/mcp_mail/server.py`: under `__main__`, `setup_logging(JARVIS_LOG_LEVEL or "INFO")` from `jarvis/logging_config.py` before `mcp.run`. Its handler writes to stderr; stdout stays the MCP stdio channel.
- `tests/integration/test_mcp_servers.py`: new `test_mcp_mail_failure_reason_reaches_the_hosts_stderr`. It starts the existing fake IMAP server (`tests/unit/mcp_mail_fake_server.py`) with a rejected login, runs the real server module as `__main__` in a child pointed at it, captures the child's stderr the way the registry passes it, and asserts one `mail_account_done account=att status=failed ... phase=session abort=login_rejected` line, a working tool call over stdout, and no credential value in stderr.
- Side effect: the MCP SDK's own content-free INFO lines (`Processing request of type CallToolRequest` and `ListToolsRequest`) now also appear, about two per mail read.

Not changed: what the tool returns, the brief card, `jarvis/bot/brief_tool.py`. The tool result already carries each account's reason code (`accounts[].error`); the bot's `brief_job_sent` line logs status only. Adding the code there is a possible follow-up if reviewers want the reason on the same line as the brief.

## Files outside the row's listed Scope

WS-13's Scope line lists P3m files. `mcp_servers/mcp_mail/server.py` is WS-13 P1 code (#204) and the test sits in the existing shared stdio integration suite next to `test_mcp_mail_server`.

## Evidence (cloud session, Python 3.12, lockfile minus openwakeword's deps, as CI installs)

- The new test failed before the fix (captured stderr held only FastMCP's banner and startup line) and passes after it.
- `ruff check --isolated --select F jarvis mcp_servers scripts services sandbox tests --per-file-ignores "tests/unit/test_status_providers.py:F401"`: all checks passed.
- `pytest tests/integration`: 199 passed, 4 skipped.
- `pytest tests/unit`: 8,334 passed, 27 failed, 16 errors. The same 43 tests fail on clean `next` at `efffa0a` in the same environment (diffed: identical): 39 in the two model-use pilot files (C1b), 2 in `test_agents_yaml_frontend_parity.py`, 1 in `test_plan_manifests.py`, and the `test_ws_transport` teardown error (an earlier log, `2026-11-13-ws34-b2-client-header.md`, found it passes in hosted CI). None touches mail; `test_mcp_mail_logic.py` passes.

## What is left and next actor

- kimi or codex: review the draft PR.
- larry: merge into `next` if the review passes. It reaches the Mac with the `next` to `main` merge and deploy, unless Larry names it an acceptance fix for `main`. After deploy, the next brief's `mail_account_done` lines should appear in `logs/bot.launchd.log` (readable through the admin log endpoint, `source=bot`).
- Separate from this change: Larry's 2026-11-16 AT&T credential reset already made M6 pass.
