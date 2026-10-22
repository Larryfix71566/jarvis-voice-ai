# WS-03 compatibility claim evidence — 2026-10-22

Baseline main: `636880eabbe9dc756c30df7128d0a90c02d222bd`.
This is documentation and read-only source inventory, not runtime implementation.

- `review-input.json` preserves the exact claim diff and project-source excerpts
  in its UTF-8 `text` value. Decoding that value reproduces the input SHA-256
  in `review-receipt.json`; JSON encoding preserves original whitespace.
- `source-manifest.json` binds the full source files used for those excerpts.
- `CLAUDE_REVIEW.md` is the unmodified response; `dispositions.md` distinguishes
  adopted findings, qualifications and a rejected script-admission suggestion.
- `package-inventory.json` records repository metadata field names and script
  directory presence for the six packages; it reads no live settings or logs.
- `rereview-9413b5e/` preserves the second unmodified REVISE review, exact input,
  source hashes, metadata type inventory and five passing CI checks for that head.
  The subsequent correction requires a fresh review; prior verdicts stay historical.

Three source/scope reviews ran through the authenticated Max subscription,
with tools/MCP/hooks disabled and no direct API credentials or fallback.
No live benchmark, imported script execution or implementation test ran.
No user-dependent acceptance passed; all twelve gates are inventoried in the
existing canonical plan. The claim still must land on main before code edits.

`rereview-7f34dde/` preserves the third REVISE verdict and receipt; its input is
the frozen `corrected-claim-review/review-input.json`. The next correction
addresses its six documentation findings. Review outcomes remain historical.
