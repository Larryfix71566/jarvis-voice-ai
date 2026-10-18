---
date: 2026-10-17
system: codex
rows: [WS-17]
prs: [216, 217]
---

Codex implemented the bounded read-only roadmap view, shared voice/pointer
filters, guarded fixed-source refresh and frozen filtered sharing on the
claimed branch. Focused backend tests: 265 passed; native roadmap controls,
actual router and compact/expanded accessibility: ten passed. Full native
suite: 563 tests, five skipped, zero failures before the two final guards;
those guards passed the focused tests. The full backend rerun remains open
after correcting two new disabled-console fixture failures.

Initial display still cannot pass the Developer's 20,000-character observation
cap. Larry approved a roadmap-only event extension; claim #217 precedes that
code. Draft #216 is not ready for merge or deployment. No acceptance gate closes.

Update after claim #217 merged (`ed21d82`): the complete first-arrival event
is now implemented, with other tool limits, private redaction and model history
preserved. All 22 current cards survive the actual observation mapping.
Final combined offline backend run: 6,802 passed, 15 skipped, zero failures;
111 focused event/privacy checks pass. Earlier disabled-console fixture and
pipeline-order expectation failures are corrected. JarvisKit: 235 passed.
Final full native verification is running. Exact-source cross-review,
independent release verification and live acceptance remain open; #216 stays
draft and production is untouched. Legacy observation creates no new policy
label; routed source envelopes retain their existing host validation.

Final native result: 563 tests, five skips, zero failures. Roadmap checker: zero errors and warnings; post-documentation complete-snapshot checks pass. Implementation is ready for exact-source cross-review, with release and live acceptance still open.
