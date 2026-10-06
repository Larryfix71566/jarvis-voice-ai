---
date: 2026-10-06
system: codex
rows: [WS-05]
prs: [177]
---

PR #177 at `40958a7` failed Ubuntu validation only at the caller-cancellation outbound-phase assertion: its 50 `asyncio.sleep(0)` ticks did not schedule the durable worker-thread setup. Replace that scheduling assumption with a two-second deadline and 1 ms poll for the actual fake provider call, keeping all cancellation, terminal-event and admission-capacity assertions. Execution/limit suites pass 56 cases and 20/20 repeated cancellation runs pass. No provider timing, route or production limit changes. The source/development extension is separately claimed through docs-only #179 before new-path edits.
