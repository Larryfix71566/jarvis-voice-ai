---
date: 2026-10-07
system: codex
rows: [WS-05]
prs: [199, 200]
---

After claim #199 merged `99993eb`, Codex repaired the two capability/source-fixture test files at frozen `a5b6f88`. Existing strict readers, source scanners/pins, original assertions, protected baseline and all twelve profile checks are unchanged. Two source-binding/actual-child regressions fail with the repair withheld; all three new witnesses pass after repair. Affected293 and full offline Python6,461 plus2 subtests /7 skips /zero failures pass. Independent Codex fixture review approves the bounded repair.

[Exact receipt](../acceptance/model-use-enhancements/receipts/mar-capability-owned-fixture-2026-10-07.json). Codex next needs review/approval of a corrected baseline/reference and candidate integration before another independent VM comparison. Prior failed evidence, required WS-17 Claude cross-review, live acceptance, model/account/source decisions and production remain unchanged.

Published as draft [PR #200](https://github.com/Larryfix71566/jarvis-voice-ai/pull/200); CI and corrected-reference approval remain open.
