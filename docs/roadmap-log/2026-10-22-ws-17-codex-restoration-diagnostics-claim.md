---
date: 2026-10-22
system: codex
rows: [WS-17]
prs: []
---

# Canonical local-restoration diagnostic continuation — claim only

Register the existing canonical deployer scope on
`codex/ws17-restoration-diagnostics-20261022` from main `c63ecce` before code.
The helper currently replaces every restoration failure with the same generic
message after quarantine. A source/synthetic-only diagnostic proposal reports
safe service/stage and exception class without raw exception text. Its new
regression fails on current code and all55 synthetic held-deployer tests pass
with the outside-repository proposal. It is not applied here and does not
establish any actual startup cause.

Keep existing source/policy/identity/health gates, the fixed local-service
whitelist, quarantine and snapshot-runner identity. Revised code requires
review, exact-source CI and canonical target-bound installation before use;
never substitute a different helper into an existing frozen rollback snapshot.
No runtime, configuration, access, model, harness, cleanup or acceptance change.
Other owners and all checkboxes remain unchanged. PR254 findings stay separate
from this bounded continuation and do not authorize its suggested changes.

The row uses after-merge lifecycle wording for this registration only. The
prospective merge tree is checked as main so registration does not leave a
claimed-but-merged branch error under the strict policy. No installer
implementation, release or restoration is described as landed by that wording.
