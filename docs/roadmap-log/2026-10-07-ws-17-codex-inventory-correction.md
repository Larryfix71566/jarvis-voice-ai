---
date: 2026-10-07
system: codex
rows: [WS-17]
prs: [173, 195]
---

# Post-merge inventory correction

Code: `065d50058534d6e16e0c59cae0100d0b9bbb5406`, after Claude’s supplied
read-only request-changes review of `fee4ac0`; #173 merged as `bd18033` first.
Projection now precedes the unchanged 32 KiB inventory reply/publication guard;
explicit scopes, all numbered rows, cumulative omissions and observed-revision
binding survive. Native cap-100 ordering preserves newest public Recents and
original indexes; private rows never consume slots or enter the disclosure.

Evidence: 90 focused Python tests, 64 bot-wiring tests, 7 actual native console
encoder tests and 21 related native tests (two capacity regressions). All pass.
Synthetic 100-row ACKs exceed 32 KiB and confirm promptly; actual native sender
with 100 rows and 120-character titles is 42,729 bytes. Whole native numbers
encode as JSON integers, preserving strict Python validation. Independent
Codex review found no remaining defect in the corrective slice.

Limits: full native candidate verification remains pending at publication.
The previous `fee4ac0` full VM comparison failed its baseline Python suite
(7 failures/84 setup errors, `host_file_unverified`); all candidate and other
baseline checks passed. Both owned VMs are stopped; production and sandbox
settings were unchanged. No clean VM comparison is claimed for either source.
Claude subscription review timed out; automatic approval review rejected the
new six-file corrective source pending exact-source authorization. Required
cross-system review, release/deployment and UI2-22…25 remain open. Raw logs,
private runtime contents and authentication material are not published here.

Scope #195 merged as `4cf452e`, enabling CC7a.4 implementation under its
contract; this corrective PR contains no reuse implementation. Thread retention
repair/tests remain a separate in-progress slice.
