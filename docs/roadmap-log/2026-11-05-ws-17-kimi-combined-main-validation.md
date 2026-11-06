---
date: 2026-11-05
system: kimi
rows: [WS-17]
prs: []
---

# WS-17 Kimi combined-main validation — 2026-11-05

Larry's merged #303 dispatched Kimi to run the bounded, read-only WS-17
combined-main validation. Exact target:
`3695d78fc79c6c19db45fafc03a3adf0b48cb2a5`. Its tree outside `docs/` and
`ROADMAP.md` is unchanged from
`f874cf1a757b03d98336aca36ef08fb13c15c7a6`, as required by the claim.
Codex retains WS-17 implementation and release ownership. Kimi authored no
source, test, fixture, configuration or dependency change.

## Target and host

Fresh worktree:
`kimi-work/worktrees/ws17-combined-main-validation-20261105`.
Host: macOS 27.0.1 (26A434), arm64; repository Python 3.12.13; Apple Swift
6.4.2; Node 24.22.1; npm 11.12.1. No `RUN_LIVE`, provider call, credential,
vault, deployment script, service, app installation or app launch was used.
The post-test target receipt has an empty non-documentation diff and an empty
tracked-status section.

Raw logs are local under
`/Users/larryfix/Documents/kimi/workspace/kimi-work/validation-logs/ws17-20261105/`.
Each command below used `tee`; the recorded exit code is the command's pipeline
status, not `tee`'s. Every command exited **0**. SHA-256 values below bind the
complete raw logs. For readability, `PY` denotes this literal interpreter:
`/Users/larryfix/Documents/kimi/workspace/kimi-work/jarvis-voice-ai/.venv/bin/python`.
Commands were run from the worktree root except where a subdirectory is named.

## Publication-equivalent CI and service gates

| Log | Exact command | Result | SHA-256 |
|---|---|---|---|
| `allowlist.log` | `python3 scripts/check_allowlist.py origin/main...HEAD` | Non-self-edit branch; enforcement not selected; exit 0 | `35bb42977dff8d0cee5c284d46d3bd6f279be8bbe6c14778b9d918412a2e34fd` |
| `roadmap.log` | `python3 scripts/check_roadmap.py` | 0 errors, 0 warnings | `4d8de58b23edcab668e15ac6864d7af3eaee7f6a7db0a83c9defeb2a4a783b95` |
| `policy-tests.log` | `PY -m unittest discover -s tests/ci -v` | 9 passed | `dfbeee3c37dd3fec4ffa993fbf5e817dd1d1b0d3d6a6d8411aa65ac55f7282a6` |
| `controller-tests.log` | `PY -m unittest discover -s sandbox/tests -v` | 164 passed | `6de803b76b48f7d972f4ea5e71678c8c5fb39b85b106812ef045eb9b33a03019` |
| `shell-syntax.log` | `bash -n sandbox/install-network-helper.sh sandbox/guest/*.sh` | Passed; no output | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `backend-import.log` | `PY -c "import jarvis, jarvis.config, jarvis.cli, jarvis.runlog"` | Passed; no output | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `kb-setup.log` | `bash scripts/setup_kb.sh` | Isolated KB environment installed | `0a31bdc14db3e88db951e503991d0e8ca1384a1866084c42a78a4a0c10e640a3` |
| `knowledge-base-tests.log` | `services/mortimer-vault/.venv/bin/python -m pytest services/mortimer-vault/tests -q` | 17 passed, 5 warnings | `3fea408b9302430a726f786bab276810f610bb5c4f38add8b236f892c5ee09c0` |
| `unit-tests.log` | `PY -m pytest tests/unit -q` | 7,322 passed, 11 skipped, 219 subtests passed, 19 warnings | `613cb7876c1b3812f9591b2f66247663c4ce3fd23f43ab7c93bf6803e473647e` |
| `integration-tests.log` | `PY -m pytest tests/integration -q` | 197 passed, 4 skipped, 3 warnings | `66d12b7774552750b7d36821880999969dde542351ec766da8712c3b418bb32f` |
| `sub-agent-evals.log` | `PY -m pytest tests/evals/sub_agent_evals.py -q` | 13 passed | `71797afb08cd62dfbefc56ad7a9745c9ca34640204b111cf263942e54f73d48a` |
| `latency-budget.log` | `PY scripts/latency_probe.py --budget tests/fixtures/latency_sample.log` | All recorded budgets passed | `c7cd0bada2326019039fa59822e768d8325a4ecd0b9c35b58cd9518ce9c53c2e` |
| `npm-ci.log` | `npm ci` in `web/` | 63 packages installed; audit reported 2 high + 1 critical vulnerabilities | `d7a64a38a9b7aa664231d656bf90f929c2298607c81b95b08c3f76cbfc952541` |
| `frontend-build.log` | `npm run build` in `web/` | Production build passed; existing Vite config warning retained | `950dfa41d319e64a218a92a7d788b7783fb2fe9772ed6eb27ed01880cf4d5492` |

The npm audit report is preserved, not silently waived or repaired. No
`npm audit fix`, dependency update or configuration edit was performed.

## Deployer-phase-A-equivalent clean full pytest

Exact command, run from the worktree root:

```bash
env -i HOME="$HOME" PATH="$PATH" USER="${USER:-larryfix}" \
  LOGNAME="${LOGNAME:-${USER:-larryfix}}" SHELL="${SHELL:-/bin/zsh}" \
  TMPDIR="${TMPDIR:-/tmp}" LANG="${LANG:-en_US.UTF-8}" \
  TERM="${TERM:-xterm-256color}" PYTHON_DOTENV_DISABLED=1 \
  /Users/larryfix/Documents/kimi/workspace/kimi-work/jarvis-voice-ai/.venv/bin/python \
  -m pytest -q -p no:cacheprovider
```

Exit **0**: **7,528 passed, 15 skipped, 19 warnings, 219 subtests passed** in
292.36 seconds. `clean-full-pytest.log` SHA-256:
`4417392ed11e88499980a215305a48b1c07b3e3115d3d777ab9eecbbd567aa67`.

## Native Swift suites

Both commands were the deployer-equivalent literal `swift test`, run in the
named package directory. Both compiled and exited zero.

| Log | Package directory | Result | SHA-256 |
|---|---|---|---|
| `jarviskit-swift.log` | `macos/JarvisKit` | 235 tests, 0 failures, 0 skips | `f42d705ccc5d6103bd376902b7b4a3d6ad3b294ac0a5716777ebd6b2e378cbd7` |
| `mortimerhost-swift.log` | `macos/MortimerHost` | 590 tests, 5 skipped, 0 failures | `f035eadc706a1f2103ba7858fc257655cd40944cebf615be23085a7a76f6fa87` |

The MortimerHost log retains compiler deprecation/concurrency warnings; no
source change was made. Its final XCTest tally is passing, and the later
zero-test Swift Testing runner line is not a substitute for that tally.

## Target and runtime receipts

| Log | Evidence | SHA-256 |
|---|---|---|
| `environment.log` | macOS, architecture, Python, Node/npm and Swift versions | `50f6ec0d253fc26ceda9f5e8e07c2813b5744902b932ee5686bc874a205a4f97` |
| `target-guard.log` | Exact HEAD; empty non-doc target diff; empty tracked status after tests | `1281e8f59c3f07a3b7ee50194f6445c495b4e965f2f28db19b4d968a7b16d4ec` |

## Boundary and remaining action

These are local macOS source/test receipts at the exact registered target, not
fresh Ubuntu CI, an exact combined-source independent review, installed/loaded
identity, deployment, operational recovery or product acceptance. The requested
reviews of merged #295/#296 remain with their named reviewers. Any later
code-changing merge, including draft #301, requires fresh validation before a
deployment relies on it. Larry reviews and merges this documentation-only
evidence; Kimi does not merge. All operational and live/human gates remain open.

---

## Independent corroborating run — Kimi session `20-34-29-68cd6dae`

This second, independent macOS run also validated `3695d78fc79c6c19db45fafc03a3adf0b48cb2a5` in a fresh detached worktree. The required diff against `f874cf1a757b03d98336aca36ef08fb13c15c7a6` outside `docs/` and `ROADMAP.md` was empty, the merged claim was present, and the initial tracked status was clean. Its external Python 3.12 virtual environment imported `jarvis` from the target worktree.

Host versions: macOS 27.0.1 (26A434); Xcode 27.2 (27B52); Apple Swift 6.4.2 (swiftlang-6.4.2.1.9 clang-2100.4.1.1), target arm64-apple-macosx27.0.0; Python 3.12.16; Node 24.22.1; npm 11.12.1.

Each command below ran from the target worktree in the prescribed order. `$V` names the external Python 3.12 virtual environment. Each full log was saved outside the worktree in this session's workspace. Every exit code was 0, so no failure retry was needed.

| # | Check | Exact command | Exit | Final tally / result | Log SHA-256 |
|---:|---|---|---:|---|---|
| 1 | Roadmap checker | `"$V/bin/python" scripts/check_roadmap.py` | 0 | `roadmap check: 0 errors, 0 warnings` | `4d8de58b23edcab668e15ac6864d7af3eaee7f6a7db0a83c9defeb2a4a783b95` |
| 2 | CI policy tests | `"$V/bin/python" -m unittest discover -s tests/ci -v` | 0 | `Ran 9 tests in 1.393s` / `OK` | `66e5a17f2a757d2eec95cabf0479ff08f7ee2d88c9046bd38c337fb1179bd539` |
| 3 | Import smoke | `"$V/bin/python" -c "import jarvis, jarvis.config, jarvis.cli, jarvis.runlog"` | 0 | No output; all imports succeeded | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| 4 | Unit | `"$V/bin/python" -m pytest tests/unit -q` | 0 | `7322 passed, 11 skipped, 18 warnings, 219 subtests passed in 240.81s (0:04:00)` | `74fe5012c0ea75e6b8b404e11e7c4449ad3ec8d8f368b138650e156156b41fde` |
| 5 | Integration | `"$V/bin/python" -m pytest tests/integration -q` | 0 | `197 passed, 4 skipped, 2 warnings in 73.57s (0:01:13)` | `bde2d472714e9e3d1fa01c662129cd4ff7b4124a71b9523c5132118280d70a58` |
| 6 | Sub-agent evals | `"$V/bin/python" -m pytest tests/evals/sub_agent_evals.py -q` | 0 | `13 passed in 0.79s` | `6387b3b72c91bd521cd25d08bea685d95562f79515a542db306ac34ff5956e88` |
| 7 | Latency budget | `"$V/bin/python" scripts/latency_probe.py --budget tests/fixtures/latency_sample.log` | 0 | `overall 4 1184 ms 1353 ms p90 OK (<= 3500 ms)` | `c7cd0bada2326019039fa59822e768d8325a4ecd0b9c35b58cd9518ce9c53c2e` |
| 8 | Frontend build | `cd web && npm ci && npm run build; cd ..` | 0 | `✓ built in 157ms`; `3 vulnerabilities (2 high, 1 critical)`; no audit fix run | `0c26bc02d8bf6f9a06fda2b155b6b1c525c6136c40f277b08092b2830f1ad63d` |
| 9 | Knowledge base | `unset MORTIMER_VAULT_DIR; MORTIMER_KB_PYTHON=python3.12 bash scripts/setup_kb.sh && services/mortimer-vault/.venv/bin/python -m pytest services/mortimer-vault/tests -q` | 0 | `17 passed, 5 warnings in 6.06s` | `b5a1f87f30900e2226ea4ec01cbb86c8b0be82d614c977a59817e2a7a46f23dc` |
| 10 | Sandbox controller | `"$V/bin/python" -m unittest discover -s sandbox/tests -v && bash -n sandbox/install-network-helper.sh sandbox/guest/*.sh` | 0 | `Ran 164 tests in 4.554s` / `OK` | `849c29088f98ccbba6eeae671359420359abbab3f23ca64158decf0e6bf7bce4` |
| 11 | JarvisKit | `swift test --package-path macos/JarvisKit` | 0 | `Executed 235 tests, with 0 failures (0 unexpected) in 6.848 (6.864) seconds` | `d0daeb8e831ff362b4f65b2730dc480fa0aaf9509187000ebb9f0f37181b8aca` |
| 12 | MortimerHost | `swift test --package-path macos/MortimerHost` | 0 | `Executed 590 tests, with 5 tests skipped and 0 failures (0 unexpected) in 128.203 (128.252) seconds` | `b3e2963507be4abcf0bea6c1febd9f367cd14f7cb39714babda8b05a0ee9955d` |
| 13 | Deployer-equivalent full pytest | `env -i HOME="$HOME" PATH="$PATH" USER="$USER" LOGNAME="$USER" SHELL="$SHELL" TMPDIR="$TMPDIR" LANG=en_US.UTF-8 TERM="$TERM" PYTHON_DOTENV_DISABLED=1 "$V/bin/python" -m pytest -q -p no:cacheprovider` | 0 | `7528 passed, 15 skipped, 18 warnings, 219 subtests passed in 263.66s (0:04:23)` | `3ac5a41bb430037ce371d20be9b75614eb9727ec87769f167891696f1471a85d` |
| 14 | Clean tree | `git diff --check && git status --porcelain` | 0 | No output; tracked tree clean | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |

### Native skips in the corroborating run

JarvisKit had no skipped tests. MortimerHost printed these five skips and reasons:

1. `CC7aThreadAcceptanceTests testActualThreadWindowCaptureDoesNotExposePrivateBodyExcerpt` — `Thread window capture requires Screen Recording and an interactive WindowServer; no acceptance is inferred`.
2. `ProtectedDisplayContentTests testProtectedContentInActualWindowCaptureMatchesBodyOnlyReference` — `Grant Screen Recording to the test runner to exercise real window capture`.
3. `ScreenPlacementTests testConnectedExternalDisplayIsExposedToPlacementTopology` — `requires at least two non-mirrored displays`.
4. `SupportingDisplayAcceptanceTests testPointerSelectedResultSharesStageOnConnectedDisplays` — `requires two connected displays`.
5. `SupportingDisplayAcceptanceTests testStreamedResponseRendersOnlyOnSupportingDisplayThenReturnsToMain` — `requires two connected displays`.

### Ignored outputs in the corroborating run

Final `git status --porcelain` was empty. `git status --short --ignored` listed only the following ignored outputs; none is a tracked source, test, fixture, configuration or dependency change:

```text
.pytest_cache/
data/jarvis.db
data/status/
jarvis/__pycache__/
jarvis/admin/__pycache__/
jarvis/agents/__pycache__/
jarvis/audio/__pycache__/
jarvis/bot/__pycache__/
jarvis/council/__pycache__/
jarvis/graphs/__pycache__/
jarvis/research/__pycache__/
jarvis/runlog/__pycache__/
jarvis/selfedit/__pycache__/
jarvis/skills/__pycache__/
jarvis/status/__pycache__/
jarvis/wakeword/__pycache__/
logs/
macos/JarvisKit/.build/
macos/MortimerHost/.build/
mcp_servers/__pycache__/
mcp_servers/mcp_apps/__pycache__/
mcp_servers/mcp_git/__pycache__/
mcp_servers/mcp_kb/__pycache__/
mcp_servers/mcp_mail/__pycache__/
mcp_servers/mcp_memory/__pycache__/
mcp_servers/mcp_notes/__pycache__/
mcp_servers/mcp_reminders/__pycache__/
mcp_servers/mcp_repo/__pycache__/
mcp_servers/mcp_runlog/__pycache__/
mcp_servers/mcp_screen/__pycache__/
mcp_servers/mcp_selfedit/__pycache__/
mcp_servers/mcp_status/__pycache__/
mcp_servers/mcp_system/__pycache__/
mcp_servers/mcp_time/__pycache__/
mcp_servers/mcp_web/__pycache__/
sandbox/__pycache__/
sandbox/guest/__pycache__/
sandbox/tests/__pycache__/
scripts/__pycache__/
services/mortimer-vault/.pytest_cache/
services/mortimer-vault/.venv/
services/mortimer-vault/src/mortimer_vault.egg-info/
services/mortimer-vault/src/mortimer_vault/__pycache__/
services/mortimer-vault/tests/__pycache__/
tests/__pycache__/
tests/ci/__pycache__/
tests/evals/__pycache__/
tests/integration/__pycache__/
tests/unit/__pycache__/
web/dist/
web/node_modules/
```

The earlier native figures are informational only: MortimerHost is now 590 executed / 5 prerequisite skips / 0 failures versus 582 / 5 / 0 at `a672239`; JarvisKit remains 235 / 0 failures, matching `d38c886`. No check failed and no failure retry was required.

**Verdict: PASS for combined-main validation of `3695d78fc79c6c19db45fafc03a3adf0b48cb2a5`.** This corroborating run is likewise not the combined-source independent review, not a deployment, not loaded or installed identity, and not live, physical or human acceptance. Installation, restoration, restarts and live tests remain held.
