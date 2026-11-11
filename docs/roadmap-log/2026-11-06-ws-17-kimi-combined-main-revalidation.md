---
date: 2026-11-06
system: kimi
rows: [WS-17]
prs: []
---

# WS-17 Kimi combined-main revalidation — executed 2026-11-10

## Verdict and target

**FAIL — one native test failed in both the initial full MortimerHost run and its exact-command rerun; the other fourteen registered checks passed.**

- Validated target: `4e58eaaf2993ba46eba379ba93341287b9247296`, the #311 merge commit.
- Required non-documentation tree: `a87256ad9e7966496542f2e7bf32582aa489cd10`.
- Target guard: `git diff --stat a87256ad9e7966496542f2e7bf32582aa489cd10 4e58eaaf2993ba46eba379ba93341287b9247296 -- . ':!docs' ':!ROADMAP.md'` produced no output.
- Main remained `4e58eaaf2993ba46eba379ba93341287b9247296` at the post-run fetch.
- Execution used a fresh detached worktree at the exact target. Final `git diff --check && git status --porcelain` exited 0 with no output; no tracked file changed.
- Kimi session: `20-34-29-68cd6dae`. Full logs are retained in that session's external `logs-reval/` directory; their names and SHA-256 values appear below.

## Environment

- macOS 27.0.1, build 26A434, arm64.
- Python 3.12.16; pip 26.3; pytest 9.1.1; Ruff 0.16.1.
- Git 2.54.0 (Apple Git-157); Node.js 24.22.1; npm 11.12.1.
- Apple Swift 6.4.2 (`swiftlang-6.4.2.1.9 clang-2100.4.1.1`), target `arm64-apple-macosx27.0.0`.
- Fresh external virtual environment, installed with `python -m pip install -r requirements-lock.txt`: exit 0. Setup log `00-environment-install.log`, SHA-256 `a77a5d654a328eb258829f1865b59e46707911dd81a9aa3a826c29647995d655`.
- `$V` below means `/Users/larryfix/Documents/kimi/tasks/2026-11-05/20-34-29-68cd6dae/venvs/ws17-4e58eaa`.

## Exact commands, exits, results and log hashes

| # | Exact command | Exit | Final result | Log and SHA-256 |
|---|---|---:|---|---|
| 1 | `"$V/bin/python" scripts/check_roadmap.py` | 0 | 0 errors, 0 warnings | `01-roadmap.log` — `4d8de58b23edcab668e15ac6864d7af3eaee7f6a7db0a83c9defeb2a4a783b95` |
| 2 | `"$V/bin/python" -m unittest discover -s tests/ci -v` | 0 | 9 tests, OK | `02-ci-unittest.log` — `1d02cf663bcf6bed2c6920aca8494a09a3ee178d28ca190fd103e14be194163c` |
| 3 | `"$V/bin/python" -c "import jarvis, jarvis.config, jarvis.cli, jarvis.runlog"` | 0 | Imports succeeded; no output | `03-import.log` — `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| 4 | `"$V/bin/ruff" check --isolated --select F821 --per-file-ignores "jarvis/bot/pipeline.py:F821" --per-file-ignores "tests/unit/test_mcp_mail_registry.py:F821" --per-file-ignores "tests/unit/test_phone_remote_service.py:F821" jarvis mcp_servers scripts services sandbox tests` | 0 | All checks passed | `04-ruff-f821.log` — `82b3e6a6c090a57601d22943bd23fca9218d1031dbe5a7b754092f9a156b4f18` |
| 5 | `"$V/bin/python" -m pytest tests/unit -q` | 0 | 7,806 passed, 141 skipped, 19 warnings, 583 subtests passed | `05-unit.log` — `a12abcd92b8ce18b5503adfe9c9e02e206420d221ee3aa85762e27474cdf7130` |
| 6 | `"$V/bin/python" -m pytest tests/integration -q` | 0 | 198 passed, 4 skipped, 3 warnings | `06-integration.log` — `746b5c6dd225d5dc915ca78cfbf7788a1bc7bccfb6a7f0224b08b99914135efc` |
| 7 | `"$V/bin/python" -m pytest tests/evals/sub_agent_evals.py -q` | 0 | 13 passed | `07-evals.log` — `6fdee15d45e1f362c492a6a5b478073e18ac0f422bc4295a78708d4d8988f60a` |
| 8 | `"$V/bin/python" scripts/latency_probe.py --budget tests/fixtures/latency_sample.log` | 0 | Non-delegated p50 1,153 ms; delegated p50 1,412 ms; overall p90 1,353 ms; all budgets OK | `08-latency.log` — `c7cd0bada2326019039fa59822e768d8325a4ecd0b9c35b58cd9518ce9c53c2e` |
| 9 | `(cd web && npm ci && npm run build)` | 0 | 207 modules transformed; build passed. npm reported 3 vulnerabilities: 2 high, 1 critical; Vite `__dirname` configLoader warning retained | `09-frontend.log` — `c811160ba6e61de59ab08dbc92260fe7ad3bb97f2329f16c63999fead5fc72a7` |
| 10 | `unset MORTIMER_VAULT_DIR; MORTIMER_KB_PYTHON=python3.12 bash scripts/setup_kb.sh && services/mortimer-vault/.venv/bin/python -m pytest services/mortimer-vault/tests -q` | 0 | 17 passed, 5 warnings | `10-knowledge-base.log` — `1b4c7682b40da6e537d385a5b91a454c23a6778174737770dcb96495d510df8c` |
| 11 | `"$V/bin/python" -m unittest discover -s sandbox/tests -v && bash -n sandbox/install-network-helper.sh sandbox/guest/*.sh` | 0 | 164 tests, OK; shell syntax passed | `11-sandbox.log` — `42baf19dca8bdd30525526265b7ed5b14295c3d5ee13bed9fb0f5bd108b40a41` |
| 12 | `swift test --package-path macos/JarvisKit` | 0 | 239 tests, 0 failures, 0 skips | `12-jarviskit.log` — `ea9a9a2abb92f15af07def7ce4d6a4c24142af200699dfc070a46742d3edec10` |
| 13, attempt 1 | `swift test --package-path macos/MortimerHost` | 1 | Main target: 590 tests, 5 skips, 0 failures. PhoneRemoteAuthority: 28 tests, 3 skips, 1 failure | `13-mortimerhost.log` — `f4ad82d16940a8e2710cbc29c9378774f3503e482aaff36006665545da45f0bd` |
| 13, exact rerun | `swift test --package-path macos/MortimerHost` | 1 | Same failing test; main target again 590 tests, 5 skips, 0 failures | `13-mortimerhost-rerun.log` — `ef2bf0f806e36e1fbf42a91f49554de61703c6865b1181f770766d67de75c8ae` |
| 14 | `env -i HOME="$HOME" PATH="$PATH" USER="$USER" LOGNAME="$USER" SHELL="$SHELL" TMPDIR="$TMPDIR" LANG=en_US.UTF-8 TERM="$TERM" PYTHON_DOTENV_DISABLED=1 "$V/bin/python" -m pytest -q -p no:cacheprovider` | 0 | 8,013 passed, 145 skipped, 19 warnings, 583 subtests passed | `14-clean-pytest.log` — `28768016e0ef24ec8570d12d59f54db18697dd5e6f851e2b0f6558c1bb562b40` |
| 15 | `git diff --check && git status --porcelain` | 0 | No output; tracked tree clean | `15-clean-tree.log` — `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |

No test was filtered, deselected or split. `npm audit fix` was not run.

## Repeated native failure

Both full-suite attempts failed the same test:

- Test: `PhoneRemoteAuthorityTests.PhoneRemoteAuthorityProcessTests testOrdinaryUnknownWaitRetainsActualSingletonAfterPartialEOF`.
- Location: `macos/MortimerHost/Tests/PhoneRemoteAuthorityTests/PhoneRemoteAuthorityProcessTests.swift:76`.
- First error line: `XCTUnwrap failed: expected non-nil value of type "String"`.
- Initial attempt: `PhoneRemoteAuthorityProcessTests` executed 8 tests, with 3 skips and 1 failure; `PhoneRemoteAuthorityTests.xctest` executed 28, with 3 skips and 1 failure; command exit 1.
- Exact rerun: same test, location, error, tallies and exit 1.

No source or test repair was attempted.

## Native skips and printed reasons

JarvisKit printed no skips. The following eight MortimerHost-package skips appeared in the initial run; the same three PhoneRemoteAuthority prerequisite skips appeared again in the rerun.

1. `PhoneRemoteAuthorityProcessTests testOwnerAndChildHoldTheSamePreprovisionedLockAcrossHandshake` — `focused process test requires the built offline owner executable`.
2. `PhoneRemoteAuthorityProcessTests testV3OwnerAndControlledChildCompleteVersionedHandshakeAndShutdown` — `focused process test requires the built offline owner executable`.
3. `PhoneRemoteAuthorityProcessTests testV4RejectsCrossVersionStoreWithoutChangingProtectedTombstone` — `focused process test requires the built offline owner executable`.
4. `CC7aThreadAcceptanceTests testActualThreadWindowCaptureDoesNotExposePrivateBodyExcerpt` — `Thread window capture requires Screen Recording and an interactive WindowServer; no acceptance is inferred`.
5. `ProtectedDisplayContentTests testProtectedContentInActualWindowCaptureMatchesBodyOnlyReference` — `Grant Screen Recording to the test runner to exercise real window capture`.
6. `ScreenPlacementTests testConnectedExternalDisplayIsExposedToPlacementTopology` — `requires at least two non-mirrored displays`.
7. `SupportingDisplayAcceptanceTests testPointerSelectedResultSharesStageOnConnectedDisplays` — `requires two connected displays`.
8. `SupportingDisplayAcceptanceTests testStreamedResponseRendersOnlyOnSupportingDisplayThenReturnsToMain` — `requires two connected displays`.

These remain skips, not passes or acceptance evidence.

## Ignored outputs

`git status --ignored --porcelain` reported the following ignored outputs after the run. Their contents were not inspected or published.

```text
!! .pytest_cache/
!! .ruff_cache/
!! data/jarvis.db
!! data/status/
!! jarvis/__pycache__/
!! jarvis/admin/__pycache__/
!! jarvis/agents/__pycache__/
!! jarvis/audio/__pycache__/
!! jarvis/bot/__pycache__/
!! jarvis/council/__pycache__/
!! jarvis/graphs/__pycache__/
!! jarvis/research/__pycache__/
!! jarvis/runlog/__pycache__/
!! jarvis/selfedit/__pycache__/
!! jarvis/skills/__pycache__/
!! jarvis/status/__pycache__/
!! jarvis/wakeword/__pycache__/
!! logs/
!! macos/JarvisKit/.build/
!! macos/MortimerHost/.build/
!! mcp_servers/__pycache__/
!! mcp_servers/mcp_apps/__pycache__/
!! mcp_servers/mcp_git/__pycache__/
!! mcp_servers/mcp_kb/__pycache__/
!! mcp_servers/mcp_mail/__pycache__/
!! mcp_servers/mcp_memory/__pycache__/
!! mcp_servers/mcp_notes/__pycache__/
!! mcp_servers/mcp_reminders/__pycache__/
!! mcp_servers/mcp_repo/__pycache__/
!! mcp_servers/mcp_runlog/__pycache__/
!! mcp_servers/mcp_screen/__pycache__/
!! mcp_servers/mcp_selfedit/__pycache__/
!! mcp_servers/mcp_status/__pycache__/
!! mcp_servers/mcp_system/__pycache__/
!! mcp_servers/mcp_time/__pycache__/
!! mcp_servers/mcp_web/__pycache__/
!! sandbox/__pycache__/
!! sandbox/guest/__pycache__/
!! sandbox/tests/__pycache__/
!! scripts/__pycache__/
!! services/mortimer-vault/.pytest_cache/
!! services/mortimer-vault/.venv/
!! services/mortimer-vault/src/mortimer_vault.egg-info/
!! services/mortimer-vault/src/mortimer_vault/__pycache__/
!! services/mortimer-vault/tests/__pycache__/
!! tests/__pycache__/
!! tests/ci/__pycache__/
!! tests/evals/__pycache__/
!! tests/integration/__pycache__/
!! tests/unit/__pycache__/
!! web/dist/
!! web/node_modules/
```

`ignored-outputs.log` SHA-256: `68cb76602a076f486207a428d684152c6d4d7065e663f353376e4d8393439833`.

## November 5 comparison

| Check | November 5 | This target |
|---|---|---|
| Unit | 7,322 passed / 11 skipped / 219 subtests | 7,806 passed / 141 skipped / 583 subtests |
| Integration | 197 passed / 4 skipped | 198 passed / 4 skipped |
| Evals | 13 passed | 13 passed |
| Policy | 9 passed | 9 passed |
| Sandbox controller | 164 passed | 164 passed |
| Knowledge base | 17 passed | 17 passed |
| JarvisKit | 239 was not the November 5 tally; 235 passed / 0 skips | 239 passed / 0 skips |
| Main MortimerHost target | 590 passed / 5 skips | 590 passed / 5 skips; separate PhoneRemoteAuthority target failed 1 test |
| Clean full pytest | 7,528 passed / 15 skipped / 219 subtests | 8,013 passed / 145 skipped / 583 subtests |

The larger Python totals are evidence for this exact target only. They do not erase the repeated native failure or establish live acceptance.

## Limits

This is not the combined-source independent review, not deployment, not loaded/installed identity, and not live, physical or human acceptance. No source, test, fixture, configuration or dependency edit; no deployment script, `launchctl`, `run_*.sh`, application installation/opening, service restart, live/provider call, credential/API-key/Keychain/vault access or checkbox change was performed. The repeated native failure requires a separately owned and reviewed fix; any later code-changing merge requires another target rebind and validation. Larry retains every merge, deployment, restart and acceptance decision.
