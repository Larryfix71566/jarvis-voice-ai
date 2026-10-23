---
date: 2026-10-22
system: claude
rows: [WS-05]
prs: [242]
---

- 2026-10-22 (WS-05 harness: Claude adversarial matrix and offline daily test): Claude (Cowork), dispatched by Larry for the two Claude slices in WS-20 plan section 10 item 4, against #242 head d476905. Adds tests/unit/test_harness_daily_offline.py (two tests: the daily job's real model_access_status path returns the fixed not-supplied harness stub, makes no harness cache, preference, fetch or socket call, and stays quiet across two identical days; a negative control that forces an ambient read fails both) and a 30-row adversarial case matrix beside the #242 receipts. Findings for Codex: F1, the legacy matcher does not select the skill for "Switch the harness to Opus 5.5" (0.333) or "Is Opus 5.5 better than Fable for the harness?" (0.250), the two requests its blocked-switch and not-proven-better guidance exists for; the host still refuses the switch. F2, MODEL_ID ignores two-segment IDs such as claude-fable-5, the registry default. F3, an explicit refresh landing during the passive run's read-modify-write is overwritten (fails safe, loses the user's refresh). Test and documentation only; no runtime, skill, provider or installer change; WS-05's row and owner unchanged. Codex reviews before this enters #242.
