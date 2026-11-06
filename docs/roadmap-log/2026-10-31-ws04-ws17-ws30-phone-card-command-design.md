---
date: 2026-10-31
system: codex
rows: [WS-04, WS-17, WS-30]
prs: []
---

# Typed mobile result-card design — 2026-10-31

**Current disposition:** typed-card source `a121dfb06385702b82a18041d7d974ab40877ee9` / tree `10b9b68d7a27d52ca2b54d42784326b5da279f86` is independently bounded-accepted for synthetic/offline operation. The design/adoption/candidate/review-pending entries below are historical checkpoints, superseded by the final receipt at the end. No product, UI runtime or live acceptance is inferred.

System: Codex. Rows: WS-04/WS-17/WS-30. Coordinator task:
`01a18d51-6c8a-73e5-8c86-83fbf017e036`. Design only, not source adoption.

Claim `2a8ca04c` records the four documentation paths and all three owner
boundaries before plan edits. Isolated branch:
`codex/ws04-ws17-ws30-phone-card-design-20261031`, worktree
an isolated temporary worktree, base `8797891d48bbd4a7e1b9d755ac23d6bc9a2c2470`.
The R3.24 stale-status correction `c40b9cc2b11596ae38938b71a17e698f03b08614`
was separately committed on the recovery source branch and carried here as
`82cbfa76`; its corrected recovery tree is
`2b3bed408dee667bf0095caef734803efda9975e`. Accepted runtime source is unchanged.

Fresh read-only GitHub checks found main `5310d1a9305035f43143fcffad6161619281f475`
and draft/open/unmerged PR290 head `39208d18d8c6fde0a9a0539e4d7c3aa68de5610f`.
Main ROADMAP blob `7b9b6ded1146b92f1a9ba163656c66f287616317` matches the local
main commit's blob. The local handoff origin has no main ref, and ancestry
traversal encounters missing historical commit `2e53f5a`; no ancestry or merge
is fabricated. The existing coordinator branch-local exception applies; fresh
current-main reconciliation remains required before integration. No other
system's checkout was read or edited. No `.agents` directory exists here.

Read existing WS-04/17/30 plans, actual console domain actions/WorkspaceStore,
Python result/protocol/service ownership, checked Swift client/model/preview,
and frozen command/classification/isolation obligations. The canonical design
is appended to the existing remote plan; phone-plan §18 references it, rather
than creating another plan or implementing a generic console bridge.

The design proposes five closed card actions plus view read, exact read+action
and server-subset authorization, trusted classification before effect/output,
bounded per-login view state, revision/idempotency/uncertainty rules, actual
owned-process and Swift checked-client tests, and 20 exact future source/test
paths. Independent decisions are enumerated in the design. No runtime/source,
frozen fixture/adapter, shared reservation, signing, Keychain, controller-security,
model, production data, network, publication or merge change occurred.

Validation for this docs slice will record roadmap and diff checks, exact path
and source-preservation hashes in the external immutable design manifest. No
runtime, UI or product acceptance test is claimed. Independent design review,
coordinator adoption and fresh source claims remain the next steps.

Completed documentation checks: roadmap validator against exact current-main
commit `5310d1a9305035f43143fcffad6161619281f475` reports 0 errors/0 warnings;
`git diff --check` passes. Scope validation confirms exactly four documentation
paths changed from `8797891d`, 20 unique proposed implementation paths (17
existing and three explicitly new), and no runtime/source changes. The initial
log check detected missing front matter; adding the required date/system/rows/PR
metadata resolved it before commit. Runtime tests were not rerun for this design.


## Independent-review revision — 2026-10-31

Reviewer returned REVISE on design `1d75a2a2` for three technical gaps. The
current proposal now lists 22 paths (19 existing, three new), adding the actual
Swift operation-enum source and its exact-inventory test; the earlier 20-path
counts above are historical. Capability authority now has a single shared
runtime owner, immutable versioned records, explicit register/update/revoke/
replace CAS transitions, facade registration identity, concrete lock order and
receipt invalidation rules for expansion, narrowing and replacement. Actions
never reconcile source changes: ordinary changes to any visible card or a new
ordinary card require explicit view refresh. Fresh preparation, first publication
after ACK and historical replay have distinct checks. Snapshot/view content gaps
leave every action disabled, with explicit read reconciliation and no automatic
action retry. The new interleaving matrix specifies all these boundaries.

Only the original four documentation paths change. No new user choice, runtime
source change, operation reservation or source adoption is introduced. The R3.24
correction `c40b9cc2` is independently accepted per coordinator; its accepted
source/evidence and manifest are preserved. Independent review of this revised
immutable design remains pending.

Revised-design validation: roadmap checker against `5310d1a` reports 0 errors
and 0 warnings; diff whitespace checks pass. Programmatic scope validation
confirms exactly the same four documentation paths changed, 22 unique proposed
source/test paths (19 existing/three new), and both required Swift protocol paths
present in the map. All runtime/source and frozen fixture/adapter bytes remain
unchanged. Runtime and UI tests are unrun because this revision is docs only.

### Typed phone-card source adoption — 2026-10-31

Coordinator adopts independently accepted design `ffb1b1ccb4582bd38bd8ca426e9835a99a4e2ce9`, tree `1a6f090afd231766f32a44eb45e2a53824e7d280`, for the exact 22-path implementation map. Source branch is `codex/ws04-ws17-ws30-phone-card-source-20261031`; the effective WS-04/17/30 claims and six wire operation reservations are recorded before source edits. Fresh local inspection verifies all 19 existing blobs and absence of the three new files against the accepted manifest, with no uncommitted collision. Coordinator's 14:52 remote refresh reports unchanged main `5310d1a`/PR290 `39208d18`, green CI544 and no new conflict. Local handoff history/main limitations and the existing branch-local exception remain explicit. Complete offline implementation and independent source review are pending; design acceptance is not runtime acceptance. All accepted capability, source-reconciliation, first-publication/history, cancellation/drain, content-join and A/B isolation rules remain binding. No production/live/public action is included.


### Typed phone-card offline source candidate — 2026-10-31

Completed the adopted 22-path synthetic slice: six closed wire operations, runtime-owned CAS capabilities and per-binding mobile views, exact scope/source checks, view-first reconciliation, ACK-gated first publication, immutable historical receipts, terminal uncertainty/withholding, and checked Swift DTO/model/UI states. All five actions affect only synthetic phone selection/pinning/open state. The test-only bounded byte bridge exercises the checked Swift client/model through proof login and the actual native v4 owner/service child. No production controller, real content, Keychain, signing, live setup, external action, frozen fixture/adapter or publication changes are included.

Validation: the complete `tests/unit/test_phone*.py` suite passes 359 tests and 489 subtests with warnings as errors and no skips, using a freshly compiled native owner. PhoneCore passes 66 tests with no failures/skips, including the real process bridge. Exact copies of the unchanged native authority sources/tests in an isolated temporary Swift package pass all 24 authority tests with no skips. The unsigned generic iOS Simulator app and UI-test bundle build succeeds. UI test execution remains unrun: Xcode reports installed CoreSimulator 1171.7.0 older than required 1174.21.0; no compatible runner was available, and the inventory probe was bounded/stopped. This is build evidence, not UI runtime acceptance. The broader repository/app/integration CI, production usability and live release gates remain open.

The suite includes ordinary target/other-card edits and appearances around capture/effect/ACK/history, capability no-op/effective lifecycle and cached read/action invalidation, source classification gates, immutable receipt aliases, A/B and separate-login identity, pin/view capacity, preauthorization cancellation and postauthorization continuation/drain, actual-process repeated requests and lost release ACK, full-content joins and stale/reset response rejection. Existing R3.23/R3.24 and frozen S0 sensitivity/isolation regressions are included unchanged; exact full-vector replay count remains zero. Native source files and frozen fixture/adapter are preserved byte-for-byte.

Status: offline source candidate complete, pending independent immutable-source review; this is not source acceptance or permission to merge. The final commit/tree, exact path/mode/blob/SHA256 manifest, reproducible commands, scoped-copy hashes and complete logs are retained in the external `phone-card-source-<commit>` evidence directory. Next step: independent review of this immutable candidate, followed by coordinator-managed current-main reconciliation and remaining release gates. No public writes or merge were performed.


### Independent source-review corrections — 2026-10-31

Candidate `99341e11` was not accepted: independent review found five defects despite its green tests. The corrected candidate addresses all five within the same adopted 22-path scope, with failing regressions recorded before runtime fixes. (1) Standalone v4 tick/revocation/feature-disable dispatch obtains one owning authorization before polling commits, preserving queued cancellation and one frozen continuation during drain. (2) Shared terminal/reentry state is rechecked after ACK and after the publication gate, including historical replay; swallowed reentry produces terminal uncertainty/fencing and no success. (3) A registered projector's collection replacement atomically validates/moves its logical slot under R→P, rejects collisions before changing the grant/view, and retains the old capability's grant binding until explicit replacement. Same-projector reattachment reuses its single slot; another runtime cannot acquire it. (4) Context retirement includes the exact login incarnation, so denial of a stale reused session ID cannot remove the surviving new login's view. (5) Checked malformed/correlation/terminal Swift client failures mask content and view state; only transport failure retains inert content for explicit refresh.

The new regression evidence includes first and historical native ACK reentry, real v4 tick/notify/feature-toggle success controls, queued cancellation without authority frames, authorized poll drain, both collection-collision orders, stale-login survivor unpin, swallowed publication reentry, and malformed action/refresh masking versus transport-retention controls. The older boundary-only drain mock now explicitly declares its empty view/peer inventory; its cancellation observations and assertions are unchanged. Frozen fixture/adapter and all native sources/tests remain byte-identical.

Corrected validation: complete Python phone suite 367 tests / 495 subtests, warnings as errors, zero skips; full PhoneCore 67 tests, zero failures/skips; 24 scoped native tests, zero failures/skips; unsigned generic simulator app/UI-test bundle build succeeds. UI runtime remains unrun for the recorded CoreSimulator 1171.7.0/1174.21.0 incompatibility. This supersedes the earlier candidate's completeness/validation evidence, not the independent review gate: corrected source acceptance remains pending. Full-repository/integration CI, current-main reconciliation and production/live release gates remain open. No public writes, merge, signing, Keychain, controller or live action occurred. The immutable corrected manifest retains failing/passing review probes, complete logs, exact scope/blob/mode/SHA256 comparisons, and the unchanged native binary/source evidence.


### Terminal-denial precedence correction — 2026-10-31

Independent review of `8c2e49f0` confirmed the original five reproductions fixed but found a combined terminal path: publication reentry latched failure, then a source-change `CommandDenied` returned as ordinary withholding before the terminal check. New failing local and actual-native regressions cover first publication with ordinary revision change and historical replay with visibility denial. The correction gives the shared terminal latch precedence over publication-denial exits and funnels terminal denials through the same uncertain/no-receipt/fence path as other uncertain failures. The ordinary-change-only positive control remains terminal-withheld without fencing; subsequent native session status still succeeds. No effect is rolled back or retried.

Validation: full Python phone suite 369 tests / 501 subtests, warnings as errors and zero skips; full PhoneCore 67 tests, zero failures/skips; scoped native authority 24 tests, zero failures/skips. Two combined regression tests / six subtests are included in the Python total. The previous unsigned app/UI bundle build receipt is carried forward because all Swift/app/UI files remain byte-identical to `8c2e49f0`; UI execution remains unrun for the recorded CoreSimulator incompatibility. Full-repository/integration/live gates remain open.

The prior external manifest's claim_commit field contained a transcription error. The corrected manifest resolves and validates the claim directly from Git as the parent of the first source commit: `4bb67a50dc766f39905077020eb77cb6b77b36e8`. Its four-document diff and ancestry precede all implementation. Immutable prior review artifacts are retained; the new manifest supersedes their incorrect claim metadata. This correction changes only the service and its two existing test files plus the four claimed docs, within the original adoption. Corrected source acceptance remains pending independent review; no publication, merge or live action occurred.


### Typed phone-card bounded source acceptance — 2026-10-31

Independent review accepted exact source `a121dfb06385702b82a18041d7d974ab40877ee9`, tree `10b9b68d7a27d52ca2b54d42784326b5da279f86`, on `codex/ws04-ws17-ws30-phone-card-source-20261031`. There is no remaining actionable finding in the adopted synthetic/offline scope. The effective claim `4bb67a50dc766f39905077020eb77cb6b77b36e8` is resolved from Git as the parent of first source `99341e11`, not transcribed. The 22 source/test paths (WS-04/17/30: 7/4/11) and four claimed docs remain the complete typed-card delta from accepted design `ffb1b1cc`. No native owner or frozen fixture/adapter bytes changed.

The final independent actual-v4-owner probe combines publication reentry with an ordinary source revision change: empty-payload `unavailable` / `authority_unavailable`, ledger `uncertain`, host fenced, later status/retry denied, and no successful receipt. The earlier pin effect remains without rollback or retry. The ordinary-change-only control remains withheld without fencing; status works and explicit snapshot/view reconciliation reveals the retained pin. Earlier polling authorization, cancellation/drain, reentry, collection-slot collision, exact-incarnation retirement, malformed-response masking, five-action process, history/A-B, proof, recovery and frozen-regression controls remain green.

| Independent evidence | Exact result and boundary |
| --- | --- |
| Full `tests/unit/test_phone*.py` | 369 tests / 501 subtests, warnings as errors, zero skips; focused regression subsets are included. Standalone independent probes are recorded separately and are not added to these totals |
| PhoneCore | 67 tests, zero failures/skips, including checked five-action native proof-session bridge; byte-identical reviewed package with test root pointed at `a121dfb0` |
| Scoped native authority | 24 tests, zero failures/skips against this candidate's Python fixtures; five copied native inputs verified exactly |
| Native owner | Independently built unchanged owner SHA256 `ceed685e7495ed5dbeeac6b4c9c82f3df33e2d6aaf2d33540ed1ec4fa22a2360`; normal sandbox retained |
| Unsigned app/UI bundle | Independent successful build at `8c2e49f0` applies because all iOS/macOS bytes are unchanged; no new app build claimed at `a121dfb0` |
| UI execution | Unrun: installed CoreSimulator 1171.7.0 versus required 1174.21.0; compilation is not UI/usability acceptance |
| Broader gates | Full repository/integration CI, fresh public-main reconciliation, real controller/storage/content/transport, release and live acceptance remain open; exact frozen full-vector facade replay count remains **zero** |

Independent acceptance of `a121dfb06385702b82a18041d7d974ab40877ee9`, the Python/Swift/native logs and the carried `8c2e49f0` unsigned-build receipt are retained in the local review evidence. The immutable local source manifest has SHA256 `ce2f5141d9a91c78642b6a5812c3eeabc6b14b3f2f3eaba639ed1cc52d25f2aa`. Review verified all 2,186 distinct blobs, 12 artifact receipts and exact tree reconstruction. Source-versus-design counts are 3 added / 23 modified / 2,144 unchanged; source-versus-public-equivalent counts are 27 added / 21 modified / 2,122 unchanged, no deletions.

This finalization changes four documentation files only and preserves all accepted source. Its external `phone-card-final-<commit>` manifest records the docs commit/tree, complete path/mode/blob/SHA256 comparisons, evidence copies and local documentation checks. The published PR290 commit `39208d18d8c6fde0a9a0539e4d7c3aa68de5610f` is absent locally; cumulative comparison uses local `4e2152`'s verified equivalent tree `e31cdf9531908b0186d71d7af573da877e7b7eec`, without claiming public ancestry or freshness. Parent handles reconciliation and any later publication. No runtime tests are claimed anew for this docs-only finalization; no public write, merge or live action occurred.

Finalization also adds a read-only completion audit in [phone-plan §19](../plans/MORTIMER_PHONE_ACCESS_PLAN.md#19-product-completion-audit--2026-10-31). It maps the existing foreground product goal to the remaining authenticated host, admitted source/roadmap, checked real transport, voice, contract/UI/integration and live-release work; it distinguishes genuine device/account/content/network prerequisites from routine offline development. Later continuation, external-action confirmations, eligible incoming calls and deferred parity remain separate, with no extra scope invented. Only these four claimed docs changed. Roadmap validation against explicit main `5310d1a9305035f43143fcffad6161619281f475` and `git diff --check` are the local documentation checks, with exact results retained externally. This entry neither updates other owners' rows nor claims new remote freshness.


### Independent documentation-review wording correction — 2026-10-31

Review of `95cafd7b` verified source preservation, the complete cumulative manifest and the completion audit. This separate docs correction distinguishes included focused regression subsets from standalone independent probes outside the 369/501 pytest totals, and records the already adopted iOS 17 deployment minimum. Actual device/OS compatibility remains unverified; the minimum is not a new user decision. No accepted source or scope changed.
