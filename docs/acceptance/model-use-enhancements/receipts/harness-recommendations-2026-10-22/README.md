# Recommendation-only publication evidence

## Current R4 CI correction

Draft PR #242 initially published R3 at `49ebd29795b43422d02be685e77bdab8e1be7418`. Its clean-runner CI exposed a new MCP tool that violated the frozen 40-tool Developer menu, unsupported capability labels, and stale skill/auth inventory assertions. R4 fixes those integration gaps without changing the frozen schema/count pins or historical capability fixtures.

Current immutable source-only patch SHA256: `d0a42d8adb59e5501d6c108e06ada0b9b6f4632b7f06f2ef5b7c5c5abf680339`, base `636880eabbe9dc756c30df7128d0a90c02d222bd`, 24 files. See `r4-reviewed-file-manifest.json` and `r4-independent-review.md`. MCP server/logic/manifest and their existing tests are restored byte-for-byte to main. The native skill reads additive passive `harness_brief` through existing `status_models`; explicit document refresh remains the authenticated native button/API. Existing capability labels are reused, with no new tool or account grant. Auth coverage still asserts every route requires bearer authentication; exact inventory counts now match six skills and 88 routes.

Independent source review found no new defect and accepts this correction for draft publication. Its merge recommendation remains hold_for_evidence pending exact amended-head CI and required cross-system premerge code review. Claude document reviews do not satisfy code review. Final publication documentation is author-maintained and outside the immutable source review.

Focused correction checks: 414 passed, 8 skipped; the single sandbox-denied loopback fixture was rerun alone with local socket permission and passed (415 total passed). Five matcher cases and package validation passed. The previous 16 native controls tests remain applicable because native source/tests are unchanged; they were not rerun. Clean-runner CI for the amended head is recorded on the PR, not inferred from these local checks. Raw host logs and private data are not published.

No model switching, installation or benchmarks occurred. All-writer approval enforcement, runtime identity acknowledgment and rollback remain unimplemented; the harness change path is blocked. Claim-only draft #241 and required cross-system review remain merge prerequisites. Larry authorized publication and in-scope CI fixes, not merge or deployment.

## Historical R3 receipt (superseded source identity)

The following R3 records remain unchanged for provenance. Their 25-file byte-identity assertion applies only to the initial published head above, not the amended R4 candidate. `publication-source.json`, `reviewed-file-manifest.json`, `independent-review.md` and `independent-assessment.json` are historical R3 evidence.

# Recommendation-only R3 publication evidence

The published25 implementation/test/skill files are byte-identical to independently reviewed R3 SHA256 `32ccb1f8971ff3e8f11030ec502432cb80dae48bbcf8f45e8f3789b31517c2e4`, original base574282e. The patch applied cleanly to main636880e; intervening main changes affect unrelated native visibility tests and WS17 documentation. Publication adds only claim/plan/log/evidence documentation. No material source rebase or new benchmark occurred. See publication-source.json for every verified hash and original local test-log digests.

Independent reviewer found no remaining blockers within the narrowed foundation; human review required. Review assessed immutable source and executed synthetic status-switch closure probes; it did not independently rerun full suites or certify runtime adoption. Existing cross-system source review and full release gates still precede merge. Claim-only draft#241 is a prerequisite; publication is not claim landing.

Offline evidence:238 backend tests,16 native controls tests, five native skill matcher cases. Native dependencies were locally cached; no app launched. Main integration source identity is exact, while publication-head CI is recorded on the PR separately. Host logs/private records are not published.

Functionality: native authored skill, passive cached daily-status recommendation, explicit fixed-public-doc refresh and refusal of unsupported harness/voice confirmation. Existing health checks preserved. Active controller/account eligibility/performance remain unknown. Universal all-writer identity approval, runtime ACK and rollback remain UNIMPLEMENTED; this is not usable switching. No installation, model change, credential grant or live inference.

Testing plan Library libfile_502deeb949688191a3c41f02eafadb4c version2, SHA25623fd4aed98c3e86a2d31ee4a4a0fa26568bd7de8c2a0fb7b330c8b8cce840343. Three official Opus5.5 Max document reviews; final text corrections self-checked, not fourth-reviewed. No claim that Claude reviewed this code. The initial separately authorized experiment would be48 turns/model, maximum two candidates384 requests, not a thousands-request prerequisite.
