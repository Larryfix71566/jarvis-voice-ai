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
