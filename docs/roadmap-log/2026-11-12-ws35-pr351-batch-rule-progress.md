---
date: 2026-11-12
system: codex
rows: [WS-35]
prs: [351]
---

# PR #351: progress moved out of the shared plan

Larry requested this bounded migration under the daily batch rule recorded in #359. The closure plan progress section now matches the PR base main at 331b2837fd19b986a30c45fb701338dc856f9c25; its non-progress content and all other existing files are unchanged. Source head before this update: 614b90a2ac1738b70ff547d89f8529163d2ca2e9. No review, merge, deployment or acceptance gate is changed. Claude folds eligible merged progress into the daily status batch; existing next actors remain as recorded below.

## Preserved progress text


- 2026-11-12 (Codex, WS-35 independent reviewer): B2 #342 at `5d714af994ed72799cbf96844a2c93fe500bd224`, against `next` `a1369e2`, receives **CHANGES REQUESTED against Larry's current criteria**. The implementation intentionally exempts native/no-Origin requests and defers the app header to C7b; it therefore does not meet native-header coverage or unconditional missing-Origin refusal. Foreign/null origins are refused. A malformed numeric port also raises ValueError rather than controlled refusal. Independent locked-environment tests: 81 passed/3 warnings; 16 ASGI behavior assertions; four malformed-port defect reproductions; changed-Python F821 clean. See [the bounded review record](../roadmap-log/2026-11-12-ws-35-b2-request-guard-review.md). Claude coordinates R1/R2 with C7b and Larry's latest direction, repairs parsing, and reconciles config-key reservations; Codex re-reviews revised source. No source, author branch, other lane ownership, acceptance checkbox, merge or deployment changed.
