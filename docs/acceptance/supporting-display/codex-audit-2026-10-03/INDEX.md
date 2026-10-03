# Codex audit evidence: supporting display transfer (WS-21)

Archived unchanged as Codex handed them over on 2026-10-03 (`Claude outputs/ws21/codex-review-20261003/`). Nothing in this folder is compiled or run by the test suites.

| File | What it is |
|---|---|
| `VoiceDisplayAuditTests.swift` | Codex's six native diagnostic tests against deployed `63aaeef`. They are **characterization tests**: they assert the defects and passed on `63aaeef`. |
| `ws17-voice-display-audit.log` | The run of those six tests on `63aaeef`. |
| `audit_python_probes.py` | The two Python probes from the same audit, reconstructed by Codex. They print observations; they are not pass/fail tests. |
| `REVIEW.txt`, `README.txt` | Codex's review of PR #171 head `43f3d5b` (request changes, four defects) and its handoff note. |
| `PR171-review-probes.diff`, `ws21-pr171-review-probes.log` | Codex's four desired-behaviour probes and their failing run on `43f3d5b` (nine assertion failures). |

Where each became a regression test:

- The six audit tests: `macos/MortimerHost/Tests/MortimerHostTests/VoiceDisplayAuditRegressionTests.swift`, one test per original with `Audit` replaced by `Regression` in the name and the repaired expectation.
- The four review probes: added unchanged to `SupportingDisplayTransferTests.swift` (`testReview…`).
- Python probe 1 (`display_popout` returns `ok` with no app acknowledgement): `display_popout` no longer claims to move content (`tests/unit/test_ui_control.py`); transfers use `console_action` `display_show`, which waits for the app's result.
- Python probe 2 (`screen_id` refused on `panel_detach`): `tests/unit/test_console_protocol.py`.
