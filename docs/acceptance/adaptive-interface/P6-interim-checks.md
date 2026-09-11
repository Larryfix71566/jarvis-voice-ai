# Integrated acceptance — interim checks

Status: not final release acceptance. P2 audio, hardware, accessibility and
other phase acceptance remain open. No merge or deployment.

## Normal-order backend suite

Prepared offline Mortimer VM, task `66fed310bde6`; check
`p6-interim-unit-integration`. Command:

`/Users/admin/mortimer/dependencies/python/bin/python -m pytest tests/unit tests/integration -q -p no:randomly`

Result: 2,458 passed, 4 skipped, 27 warnings, pytest duration 376.05 seconds;
verifier duration 377.751 seconds, exit 0. The 900-second limit was preserved.
Log SHA-256: `f4cf56a946f02d9d74c38843aceeb06f2c49fc4d71552736417ca983db1b9a8c`.
No backend source or Python tests changed relative to baseline `30850f9`.
Native implementation present corresponds to `60a6cda`; this is an interim
check, not a frozen-source final verification receipt.

No skips were added or changed. The run did not print individual skip reasons;
reverse-order execution with `-rs` is pending to account for them explicitly.
The repository's existing live orchestrator tests are marked `live`, and the
unchanged tests/conftest.py requires RUN_LIVE=1 for them. Do not count skipped
external-service tests as exercised or enable live credentials in this offline VM.

## Still required

Reverse and deterministic seeded order, installed profile baseline/candidate
checks, final frozen-source receipt, live/hardware requirements, performance,
accessibility and rollback acceptance. A successful interim pytest run does
not substitute for any of those gates.

## Reverse-order backend suite

Check `p6-interim-reverse-unit-integration` reverses the complete collected item
list through a pytest collection hook; no tests are removed. Same two test roots,
`-q -rs -p no:randomly`, same installed interpreter and 900-second limit.
Result: 2,458 passed, 4 skipped, 27 warnings; pytest 372.60 seconds, verifier
373.871 seconds, exit 0. SHA-256:
`e31f16b651b84369d8a503b5d631f86126a96aff87ff9b86dca438628d5dcb91`.

The detailed summary identifies all skips: three cases in
`tests/integration/test_orchestrator_live.py` and one in
`tests/integration/test_mcp_servers.py:138`, all with the existing reason
“live test — set RUN_LIVE=1 to enable”. These external-service cases remain
unverified, not accepted. Seeded order and all other final gates remain open.

## Seeded-order failure and isolated fixture correction

Seed 20260911 shuffles the full collected item list using a local Random
instance. `p6-interim-seeded-unit-integration` completed with 2,457 passed,
1 failed, 4 existing live skips and 27 warnings, in 441.122 verifier seconds.
SHA-256 `7b7881d97b4481e6e267d34379d7b9c8822cc5bac2d41fdbc3fc1b4dd9f92361`.

Failure: `test_bare_run_empty_run_id_is_none` encountered FakeAgent.crash=True
left by `test_agent_crash_settles_job_as_error`. The two-test order reproduced
it independently (`p6-fake-agent-leak-repro`, SHA-256
`a522c082a175a309b97c023029325a997c9d08f3ecbda6d5567294bb10b0341d`).
The producer helper assigned shared class attributes directly. It now uses
monkeypatch.setattr for both crash and gate, restoring each at teardown. No
production behavior, assertions, waits, test selection or timeouts were changed.

After correction:
- The exact pair passes (`p6-fake-agent-leak-fixed`), SHA-256
  `0990d48a7900ad120e0d250730549f048c4f14e8b7a8bc21fc136d67066651b3`.
- The complete admin self-edit test module passes (`p6-selfedit-module-fixed`),
  SHA-256 `bdef4d81e56aca737fbf1139cd8c45be4bf568d61d3aeaef056d364683f24a5f`.

Full seeded/normal/reverse checks must pass again after this fixture correction.
The failed run remains failed evidence; the focused reproduction is not a
substitute for those complete reruns or the remaining release gates.

## Corrected full-suite results and review artifact

After local fixture commit `0fb982b`:
- `p6-corrected-seeded` (seed 20260911): 2,458 passed, 4 existing live skips,
  27 warnings; verifier 434.289 seconds. SHA-256
  `6f2ab5c9549ad3f3c5029801b36441455e032666199896c27382ed381e740fa6`.
- `p6-corrected-normal`: 2,458 passed, 4 existing live skips, 27 warnings;
  verifier 374.878 seconds. SHA-256
  `9b30c0c6a2753e7aad3bb0b4d794835414f497e7a1ec3b75f9a5e56d0a73fc14`.
- `p6-corrected-reverse`: 2,458 passed, 4 existing live skips, 27 warnings;
  pytest 373.09 seconds. Log SHA-256
  `6a1c3260e2173ae719feb8b3d21ab65912f49af287fa444dd802ba4c85d5f4cf`.

The isolated fixture correction is draft PR #65:
https://github.com/Larryfix71566/jarvis-voice-ai/pull/65
Remote commit `a3293cb7327683e38c3f43869c12dd0b34032ed5` is based on current main
`d36299bc899adc822f04c4e4991cb5a86b27ce1b` and changes only the reviewed test file.
Its blob `6bd7295caf52a93437cac8cccb58ce16b90e334a` matches the locally tested
file exactly. It does not publish or establish acceptance of the UI phases.
The plan PR #64 was independently confirmed merged. No implementation PR was
merged and no application deployment occurred during this work.
