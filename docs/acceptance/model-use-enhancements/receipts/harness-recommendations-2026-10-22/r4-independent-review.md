# Independent R4 source review

Recommendation / workflow label: **hold_for_evidence** for merge. **No new source defect found in the CI remedy.** The narrow source correction is acceptable for the authorized draft-PR update; required final CI and cross-system premerge review remain pending.

Repository: Larryfix71566/jarvis-voice-ai  
Base: 636880eabbe9dc756c30df7128d0a90c02d222bd  
Source-only patch SHA-256: d0a42d8adb59e5501d6c108e06ada0b9b6f4632b7f06f2ef5b7c5c5abf680339  
Frozen subject: review-code-r4/subject. Exact patch SHA and all 24 manifest after-hashes verified. No amended PR head was supplied for this review.

## CI remedy assessment

The repair preserves the frozen menu instead of weakening its guards. Independently compared these frozen R4 files to base636880e blobs; every byte matched:

- mcp-status server, logic, manifest, and existing logic test.
- Native40 capability verifier and its test, including exact40/schema checks.
- model_access.yaml, agents.yaml and mcp_servers.yaml provider/menu configuration.

No additional LLM-callable tool or refresh argument survives. The existing status_models tool continues its original GET /api/status/models call. The implementation adds harness_brief to that result through read_report only. Explicit public-document refresh remains the existing authenticated native button/API path and is not available as a new MCP operation.

A synthetic probe executed the actual AST-extracted model_access_status and existing MCP forwarding functions with fake dependencies: original status fields remained intact, harness_brief survived forwarding, one passive read occurred, and no POST occurred. No public request, real DB, model or provider was touched. An initial test harness attempt omitted the source's postponed-annotation semantics on the system Python; correcting that harness produced the passing result, with no subject change.

The skill now uses implementation_planning and acceptance_design, both already defined in the unchanged capability registry with text-only requirements. Its sole required tool is existing status_models; no credentials, new labels or roster grants were added. Source-level required-tool/capability filtering remains unchanged. The supplied static validator and five matcher fixtures passed, with package revision 8da0f1efe1ccb9f5f6940b04f8a00193296cc8b3e943e66c7c9dbbbb2f5ec540 matching the configured pin.

The changed skill-inventory assertions still require an exact six-name set and six matching pins; pin-mismatch checks remain. Authentication coverage still requires the exact route count, explicitly names both new endpoints, and iterates every APIRoute to require401 and the bearer challenge. Updating86 to88 reflects the two real authenticated routes; it does not remove an assertion or exempt a handler.

## Prior controls remain intact

The R3 backend voice stage/confirm block, LLM confirmation refusal, status kill-switch wrappers, passive scheduler hook, evidence freshness, and native unknown-active-model wording remain unchanged. Harness switching is still unavailable. Nonvoice preferences remain mutable aliases after save, with that limitation disclosed. No new universal guard over Settings, environment, registry or self-edit writers is claimed.

The source-only patch deliberately excludes publication documentation. This assessment does not certify that a later PR description or artifact correctly distinguishes published R3 history from final R4 provenance.

## Test evidence and merge hold

The completed supplied CI_FIX_TESTS.log reports **414 passed, 8 skipped, 1 failed**. The failure is the existing test_loopback_rejects_negative_lengths_and_drains_actual_thread, which stops at HTTPServer(('127.0.0.1',0)) with PermissionError: Operation not permitted. Its test and implementation are byte-identical to the base; this trace does not establish a product assertion regression. The author then supplied CI_FIX_LOOPBACK_TEST.log from an approved local-socket rerun: **1 passed in 1.48s**. That closes the observed infrastructure-stopped fixture. The reviewer inspected the receipt without retrying the bind or invoking a provider. Eight initial skips remain; this is not final amended-head CI.

The broader dotenv-contamination diagnosis was reported by the author; it was not independently reproduced in this source review and is not used to dismiss any source-visible failure.

The required cross-system premerge review and exact amended-head CI are still pending. These are evidence holds, not a request for another source change or permission to weaken the checks. Close the hold by:

1. Reviewing CI tied to the final amended commit, including the unchanged loopback test in a runner that permits its local fixture and the current menu/skill/auth assertions.
2. Completing the required cross-system review bound to that commit, including final publication provenance.

Passing, identity-matched checks and review with no material finding support merge/human_review_required; a product defect or material documentation contradiction requires revision; unavailable evidence keeps the hold.

## Ratings and scope

Impact if wrong: **high** due to shared and persistent preference behavior. Regression likelihood: **moderate**; no source defect established, but integration spans multiple surfaces. Protection: **partial**. Recoverability: **managed**. Source-review confidence is high; overall merge confidence remains **low** until the decision-critical evidence arrives. Auto-merge is excluded by persistent state, public contracts, shared behavior, native rollout and pending checks.

No source, frozen patch or active candidate was edited. No push, merge, install, service start, settings/model change, inference or benchmark occurred during this review.

Structured assessment: independent-assessment.json. This review is bound solely to the R4 source SHA above.

