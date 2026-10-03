Codex diagnostic and PR #171 review handoff — 2026-10-03
Reviewed GitHub head: 43f3d5b803ac600965ab952b9345668f5924ec3c.
No application-code changes, no merge and no deployment in this review.

VoiceDisplayAuditTests.swift is copied UNCHANGED from the original six-test diagnostic suite against 63aaeef.
IMPORTANT: these are characterization tests: their assertions document the old defective behavior and passed on 63aaeef.
Do not install them unchanged as regression tests requiring failure on 63aaeef and success on the repaired branch.
Archive the originals unchanged as evidence; adapt/reverse assertions and use current injected seams for repair regressions.
The plan's section 4 currently states the opposite and should be corrected.

The two Python diagnostics were executed inline in the original audit. audit_python_probes.py reconstructs the two probe bodies and adds only a run description.
They print observations; they are not regression tests. The first still documents the unacknowledged legacy UI transport, which should no longer be used for content transfers.

PR171-review-probes.diff adds ONLY four independent desired-behavior tests inside the existing SupportingDisplayTransferTests class.
SupportingDisplayTransferTests.with-codex-probes.swift includes the original PR file unchanged plus the four probes.
All four independent probes FAIL on the reviewed head, with nine assertions:
- rejected request incorrectly supersedes the valid in-flight transfer;
- failed replacement leaves the window created by its superseded predecessor open and empty;
- fixed-panel detach ignores screen_id, accepts disconnected screen, and does not record valid destination;
- inventory reports presented=false/content=null/result_id=null when an ordinary transport result IS presented in the shared stage.

Original PR tests: 17 passed. Python focused protocol/UI tests: 47 passed.
Independent audit fixtures are deterministic/injected, not live external-monitor acceptance.
Claude remains implementation owner. Codex holds merge approval until the reproduced defects are repaired.
