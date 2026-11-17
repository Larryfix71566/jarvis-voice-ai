---
date: 2026-11-17
system: codex
rows: [WS-13]
prs: [380]
---

# WS-13: Codex independent review of PR #380

System: Codex. Session reference: parent thread `6afac5ab-3210-8191-a87a-f40521cd30ce`.
Review: https://github.com/Larryfix71566/jarvis-voice-ai/pull/380#pullrequestreview-5939835157
Status branch: `codex/ws13-pr380-review-20261117`, from main `5dfd9e35d107bc63a7c56e1517672c3b00216b0c`.
This record is documentation only. No shared status lines, plan progress, checklist boxes, reservations or runtime files changed.

## Scope and coordination

Larry explicitly requested this nonauthor review, an isolated worktree, a PR comment, and a new batch-rule record; never approve or merge. Reviewed repository AGENTS.md, current origin/main ROADMAP protocol/rows/conflicts, CLAUDE.md and relevant architecture/plan guidance. No tracked .agents/skills exists at this head; inspected the repository's MCP authoring and git review skills for relevance. The mail code remains Claude's; no ownership transfer or author-branch edit. Exact-head testing used detached worktree `pr380-review`; negative controls were restored. This separate docs worktree starts at current main. No section 3 numbers reserved. Only this new WS-13 roadmap-log file is changed.

## Review and evidence

Codex independent review of **142f4833750951eae31f408f65adb19a489d8a99**, against `next` base `efffa0a83e4e1d8b7aece635c4b3d2b56769ce9c`. **COMMENT only; no approval or merge.**

No blocking defect found in the logging change. One nonblocking test-coverage finding:

- **C1 — the successful tool call does not prove stdout is clean** (`tests/integration/test_mcp_servers.py:226–228`). MCP 1.29.0 forwards stdout parse exceptions to ClientSession's default message handler, which ignores them. I temporarily inserted `print("PR380_NON_JSON_STDOUT_CANARY", flush=True)` immediately before `mcp.run`; the new test still passed (1 passed, 12 deselected). Please replace that docstring claim and explicitly reject parse errors or validate captured raw stdout. The actual submitted implementation is clean: my independent raw-stream probes validated every stdout line as JSON-RPC. The mutation was restored.

Verified behavior:
- `setup_logging` uses `logging.basicConfig(..., force=True)` with no filename/stream, so its handler is stderr. FastMCP's own handler/banner also use stderr.
- Registry `_start_server` calls `stdio_client(params)`; pinned MCP 1.29.0 defaults `errlog=sys.stderr` and passes it as subprocess `stderr=errlog`. `JARVIS_LOG_LEVEL` is forwarded in `BASE_ENV_KEYS`. The launchd template's `StandardErrorPath` is `__REPO__/logs/__SVC__.launchd.log`, hence `logs/bot.launchd.log` for bot. This is source/synthetic evidence, not a live Mac log receipt.
- The mail INFO sites are `mail_account_done` and `mail_account_busy`. They carry fixed account keys, status/count-state/phase/reason, exception class/errno and duration; no count values, subjects, senders, addresses, credential values or raw IMAP error text. Worker warnings also avoid exception text.
- SDK `Processing request of type ...` lines carry only request class names and are acceptable noise. `ListToolsRequest` normally occurs at discovery; `CallToolRequest` occurs per call, so “two per read” is not a persistent-registry invariant. The SDK also has INFO paths for captured Python warning text and cancelled request IDs; I found no mail-content flow into these on the reviewed paths. DEBUG logs request objects, and generic malformed-request warnings can contain input, so this is not a blanket guarantee that every SDK diagnostic at every level is content-free.
- A `brief_job_sent` reason field is a useful optional correlation follow-up, not necessary to fix this loss. Use fixed account keys and a closed allowlist of reason codes from the validated envelope, with a fixed fallback. Do not interpolate arbitrary `accounts[].error`, raw exceptions or mail content. The assembled brief currently turns errors into fixed labels.

Independent local evidence (Python 3.12.14; mail/test dependency subset constrained by the lockfile, including MCP 1.29.0 and FastMCP 3.4.5):
- `pytest tests/integration/test_mcp_servers.py -k mail -q`: **2 passed, 11 deselected**.
- Restore only `server.py` from base, same command: **1 failed, 1 passed, 11 deselected**, specifically missing `mail_account_done`; restored exact head afterward.
- `pytest tests/unit/test_mcp_mail_logic.py tests/unit/test_mcp_mail_registry.py tests/integration/test_mcp_servers.py -k mail -q`: **119 passed, 11 deselected**.
- Raw stdio success and rejected-login probes: **3 valid JSON-RPC lines each, zero nonprotocol lines, zero synthetic credential/sender/subject leaks to stderr**; expected one account-done line each.
- Changed-file Ruff F, diff whitespace and roadmap checker passed. I did not reproduce the author's entire integration/unit runs; the full dependency install hit an unrelated CUDA cache-space limit.

Hosted evidence is separate: [validation run 44095815829](https://github.com/Larryfix71566/jarvis-voice-ai/actions/runs/44095815829), associated with this head, checked out PR merge `3bc7ee2da38c9b06882228ab7d6fe23cd851c8e2`. [Python job](https://github.com/Larryfix71566/jarvis-voice-ai/actions/runs/44095815829/job/134082526590): **27 failed, 8334 passed, 141 skipped, 15 errors**; **Integration tests SKIPPED** after unit failure. Missing `web/package.json`, removed `OrbFieldView.swift`, and a stale `ResponseResultRouter.swift` manifest dominate those failures. [MortimerHost job](https://github.com/Larryfix71566/jarvis-voice-ai/actions/runs/44095815829/job/134082526835) also failed: `VoiceWaveView.swift:407`, `WaveEngine.Dyn` has no member `g`. These paths are outside this three-file diff; I have not independently rerun the full base suite to certify baseline equivalence. Local mail success must not be described as hosted integration success.

Own batch status record: `docs/roadmap-log/2026-11-17-ws-13-codex-pr380-review.md` on separate branch `codex/ws13-pr380-review-20261117`. Claude owns C1; lane owners own the red CI; Larry owns any later merge/deploy and Mac confirmation.

## Remaining work

- Claude: consider C1's explicit stdout validation and correct the test's overclaim. Optional bot-line reason correlation must remain allowlisted and content-free.
- Respective release-lane owners: resolve hosted unit/native failures and obtain actual hosted integration results. The full base-suite equivalence claim was not independently reproduced in this review.
- Larry: any future merge/deploy and actual Mac log confirmation. This review performed neither, and does not close acceptance.
- Claude daily batch: fold this record only after its documentation PR is merged. The author PR remains a draft; review state is COMMENT.

## Local evidence artifacts

Scratch-only files, not required for production: `/tmp/pr380-negative-control.txt`, `/tmp/pr380-stdout-mutation.txt`, and `/tmp/pr380-raw-probe.py`. The commands and observed outcomes above are the durable review evidence. No real accounts, credentials, provider calls, or production processes were used.
