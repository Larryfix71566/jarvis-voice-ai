---
date: 2026-11-14
system: kimi
rows: [WS-17, WS-36]
prs: []
---

# WS-36 A3 / WS-17 combined-source review

## Verdict

**APPROVE.** No release-blocking correctness, security, data-loss, or operational-recovery finding was confirmed in the reviewable source delta. No owning-system code-fix request arises from this review.

This is the independent A3 source-review verdict for the exact deploy candidate below. It is not deployment approval, operational recovery, live acceptance, or authorization to restart any service. Larry retains the merge, deployment, 27-box acceptance batch, and every operational decision.

## Exact target, ancestry, and inventory

- Production base: `b136a2a66032b17082776a01353abe67e352c31e`.
- **Exact reviewed head: `c23dda5bdeae1e5a1b616e5fc69866655beff8fb`.**
- `git merge-base` returned the production SHA, and production is an ancestor of the reviewed head.
- Source delta outside `docs/` and `ROADMAP.md`: **189 files changed, 53,483 insertions, 419 deletions**.
- The reviewed head contains freeze `5777e98cf1cdbaa65eb13079044693794c071927`, #339's accepted test-prerequisite fix, and later documentation. The only non-documentation difference from the freeze after excluding `ROADMAP.md`, `AGENTS.md`, and `CLAUDE.md` is `macos/MortimerHost/Tests/PhoneRemoteAuthorityTests/PhoneRemoteAuthorityProcessTests.swift`; no post-freeze production source change was found.
- The verdict is bound to `c23dda5`, not inferred from the earlier review of `5777e98` or from current `main`.

## Required exclusions and authorship reconciliation

Kimi did not review Kimi-authored code. Claude's independent freeze review in `docs/roadmap-log/2026-11-12-ws-17-claude-a3-excluded-files.md` records **APPROVE** for these exclusions:

- WS-31 NR1: `jarvis/app_build_contract.py`, `tests/unit/test_app_build_contract.py`, and `tests/fixtures/app_build_contract/new_idea_v1.json`.
- Original WS-32 reader repair #275, reviewed at code commit `5c5cb2e`; later non-Kimi changes from #312 and #322 remained in this review's scope.

The range commit log, direct non-merge authors, and Kimi branch merges were reconciled. **No additional Kimi-authored source file was found, so there is no further file to hand to Claude.** The exclusions are not silently approved by this verdict.

## Findings

| Severity | Confirmed findings | File and line |
|---|---:|---|
| Critical | 0 | None |
| High | 0 | None |
| Medium | 0 | None |
| Low | 0 | None |

There are no finding locations to assign because no actionable defect was confirmed. Environment-limited test outcomes below are disclosed as evidence limitations, not misreported as product findings.

## Review coverage

The complete changed-file inventory and range history were classified, then production implementations, tests, call sites, failure paths, and activation boundaries were inspected by release-risk area. This was a risk-directed static review with offline corroboration, not a line-by-line proof of every added line or a substitute for Larry's acceptance run.

### Correctness, privacy, and provider/model access

Reviewed pipeline integration, weather intent binding, task-stop control, checked sends, source classification, subscription/model routing, readiness, model execution, LLM client construction, memory provenance, daily brief, native brief rendering, model-access configuration, environment checks, and CI workflows.

The access guards require route authorization and validated API requests; the direct-API-disabled policy remains fail-closed. Confidential memory and mail context remain bound to their rendered snapshots, and the brief path uses isolated sensitive-turn handling and bounded checked sends. No unauthorized provider fallback, confidential-rendering defect, or data-loss path was confirmed.

### Phone admission, protocol, identity, and recovery

Reviewed phone admission and store, ASGI adapters, authentication proofs, authority channel, connection/login/protocol handling, recovery, result commands/results, service coordination, and native/iOS protocol and preview changes.

The adapters default to disabled and no production mounting path was found. Protocol parsing enforces bounded closed schemas, duplicate-key rejection, finite numbers, canonical identifiers, and bounded recursion. Authentication and store operations bind the relevant identities, generations, expiration, revocation, and fencing. Recovery fails closed on ownership, persistence, identity, and child-process uncertainty. These are source-review observations, not live phone-transport acceptance.

### Deployment, data lifecycle, and operational recovery

Reviewed held installation, receipt verification, policy-floor enforcement, quarantine, local restoration, archive validation, rollback, task recovery, and sandbox pruning, together with their focused tests.

Deployment requires exact revisions and verifies receipt ownership, permissions, links, size, hashes, production-root identity, service holds, and launch envelopes. Archive validation rejects unsafe paths, links, settings, and databases. Rollback verifies identity and does not automatically restore databases or settings. No deployment, restoration, rollback, restart, or recovery command was executed.

### Native, skill trust, and post-freeze fix

Reviewed the changed JarvisKit and MortimerHost sources, package/project manifests, iOS preview/protocol/operations sources, skill compatibility/package adapter/registry, and upgrade-agent integration. Skill-package handling remains bounded and inert in the reviewed adapter; no production install or execution authority was found. Mail text in `BriefCardView.swift` uses verbatim rendering with selection disabled. #339's post-freeze test-only prerequisite fix was included at the exact target; no production source delta followed the freeze.

## Commands and checks

The following were run in an isolated detached checkout of the exact reviewed head. No live tests, provider calls, credentials, Keychain/vault access, application launch, deployment, restart, or production access occurred.

```bash
git merge-base b136a2a66032b17082776a01353abe67e352c31e c23dda5bdeae1e5a1b616e5fc69866655beff8fb
git merge-base --is-ancestor b136a2a66032b17082776a01353abe67e352c31e c23dda5bdeae1e5a1b616e5fc69866655beff8fb
git diff --stat b136a2a66032b17082776a01353abe67e352c31e c23dda5bdeae1e5a1b616e5fc69866655beff8fb -- . ':(exclude)docs/**' ':(exclude)ROADMAP.md'
git diff --name-status b136a2a66032b17082776a01353abe67e352c31e c23dda5bdeae1e5a1b616e5fc69866655beff8fb
git log --format='%H%x09%P%x09%an%x09%ae%x09%s' b136a2a66032b17082776a01353abe67e352c31e..c23dda5bdeae1e5a1b616e5fc69866655beff8fb
git log --merges --format='%H%x09%s' b136a2a66032b17082776a01353abe67e352c31e..c23dda5bdeae1e5a1b616e5fc69866655beff8fb
git diff --stat 5777e98cf1cdbaa65eb13079044693794c071927 c23dda5bdeae1e5a1b616e5fc69866655beff8fb
git diff --name-only 5777e98cf1cdbaa65eb13079044693794c071927 c23dda5bdeae1e5a1b616e5fc69866655beff8fb -- . ':(exclude)docs/**' ':(exclude)ROADMAP.md' ':(exclude)AGENTS.md' ':(exclude)CLAUDE.md'
git diff --check b136a2a66032b17082776a01353abe67e352c31e c23dda5bdeae1e5a1b616e5fc69866655beff8fb -- . ':(exclude)docs/**' ':(exclude)ROADMAP.md'
bash -n scripts/deploy_main.sh
python3 -m compileall -q jarvis mcp_servers sandbox scripts
```

Results: ancestry and inventory matched the values above; source whitespace validation, deployment-shell syntax, and Python bytecode compilation passed.

Targeted offline tests were run with isolated dependencies and synthetic/fake inputs. The broad changed-area run, excluding audio-stack and one environment-bound developer-capability test module, completed with:

```text
1611 passed, 130 skipped, 581 subtests passed, 5 failed
```

The five failures were environment/setup outcomes in the incomplete isolated runner, not confirmed source defects:

1. `test_service_health_prints_only_status_codes_against_local_stub`: its child process did not inherit the isolated dependency path and could not import `keyring`.
2. `test_late_real_sdk_response_retains_admitted_spend_reservation`: timed out in the incomplete isolated environment; a synthetic diagnostic also hung and was not treated as product evidence.
3. Three `test_actual_fresh_child_merged_policy_receipt_matches_parent_without_inference` cases: fresh children did not inherit the isolated dependency environment.

A full locked-dependency installation could not complete because `openwakeword` requested an unavailable Linux/Python 3.12 `tflite-runtime`; this matches the repository's documented CI workaround. Missing optional/import dependencies and an interrupted SciPy installation further limited local collection. Audio-stack tests and `test_claude_developer_capability.py` were excluded rather than triggering unrelated environment repair. No Swift test was run in this Linux review environment; #339's separate native validation evidence is not reproduced or replaced here.

## Explicit limitations and remaining gates

This verdict supplies no evidence of or authorization for deployment, installation, restoration, rollback, service restart, application launch, loaded-identity proof, live/provider calls, credential use, physical-device checks, production phone transport/enrollment/media/session behavior, live WorkspaceStore-backed results, or human acceptance.

The review does not approve the excluded Kimi-authored bytes, claim a complete local full-suite pass, or tick any acceptance box. It closes only the independent A3 source-review gate with no release-blocking finding. Larry may proceed with his separately controlled freeze-build deployment and 27-box acceptance batch; every other validation and operational gate remains independently binding.
