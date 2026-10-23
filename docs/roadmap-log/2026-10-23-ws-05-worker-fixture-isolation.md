---
date: 2026-10-23
system: codex
rows: [WS-05]
prs: []
---

# WS-05 — fresh-worker fixture isolation

2026-10-23 UTC (2026-10-22 Eastern). System: Codex, provider lane.
Coordinator: `01a1641a-bbc6-7257-b7e5-93b1b5bd60e0`.

Documentation-only main-first registration on `67438c3a66827616a1f91cf692a98245a262813e`, after #266. Future implementation branch `codex/ws05-worker-fixture-isolation-20261023`; exact test `tests/unit/test_claude_developer_capability.py`. Existing active harness claim, source inventory, CX-28 and acceptance checks are preserved. No runtime/test bytes changed. No shared numbers reserved.

The failing fresh-child assertion can observe a database created by the parent notifier because the shared fixture replaces the parent environment. The child refusal itself passes. Register separating fresh-child construction from in-process environment mutation and deterministic inert parent polling, with every original authority/refusal/no-write assertion retained. See the dated entry in the canonical model-use plan.

Next: sole coordinator lands this reviewed docs claim after required checks; provider owner verifies exact main registration before implementing. Bounded offline regression and independent review precede source integration. No rerun of frozen #269/#270, live CLI/model calls, dependency changes, full local suite/VM, service/configuration changes, installation or activation.
