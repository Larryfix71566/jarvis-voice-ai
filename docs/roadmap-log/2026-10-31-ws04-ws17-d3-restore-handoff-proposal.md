---
date: 2026-10-31
system: codex
rows: [WS-04, WS-17]
prs: [290]
---

# WS-04 / WS-17 D3 restore-owner handoff — adopted offline source claim

**State:** coordinator-adopted, branch-local seven-file WS-04 offline source claim on `codex/ws04-ws17-d3-restore-handoff-20261031`. The claim was recorded in this commit before source edits and follows independently accepted D3 design `d75ad6dd6180a036b839c3a1d604f731126b254b` (tree `e82c5cf7a3065f359e3ffb81bf18c8a7e5484b7c`). Owner and author: Codex; independent exact-source review ACCEPTED source commit `4d6371caf490c4a36393560b6c97f355df647223` (tree `1dca0ce9d6a8ec5dd1d27e2e094708bdd7bdfd7a`). Fresh local scope inspection found no competing D3 branch or out-of-row path owner; the parent coordinator reports GitHub connector refresh at 2026-10-31 06:53 UTC: main `5310d1a9305035f43143fcffad6161619281f475`, PR #290 `46e29c26e6a4262aa47dfa96615f3a91cc990572`, draft/open/unmerged, only open PR and no new comments/claim changes. Direct `git fetch` still fails DNS, so that connector evidence is the remote check. This source claim is limited to offline prepare/pending fencing and controlled-child shutdown; it is not a production restore path or permission to restore/deploy.

## Ownership and collision evidence

- **WS-04** retains the protected phone-authority/store/service design and the current exact `phone_remote_restore_v1` contract in `docs/plans/MORTIMER_REMOTE_ACCESS_PLAN.md` §3 / R3.5.
- **WS-17** retains ownership of deployment, rollback and restore invocation, including `scripts/deploy_main.sh` and its deployment tests. The existing branch-local guard record identifies `scripts/deploy_main.sh` and `tests/unit/test_deploy_main.py` as WS-17 scope; it rejects arguments in newly generated non-held rollback scripts. No ownership moves between workstreams.
- A local branch/path check found no other local D3/restore claim branch; the neighboring R3.21 audit is a separate WS-04 documentation lane and is not an ancestor of this candidate. The existing R3.19 Keychain owner boundary remains unchanged. There is a material WS-17 path overlap: its prior generated-rollback guard claim already names `scripts/deploy_main.sh` and `tests/unit/test_deploy_main.py`. Those paths are not free for D3 edits; the WS-17 coordinator must explicitly amend/coordinate the effective claim and preserve the guard before any implementation. No uncommitted source edit was found on this immutable base. `git fetch origin main` has not succeeded in this environment because DNS cannot resolve `github.com`; remote branch/PR claims therefore require a fresh check before adoption or source changes.

The exact adopted source/test scope is seven paths:

1. **WS-04 authority/store stage:** `macos/MortimerHost/Sources/PhoneRemoteAuthority/PhoneRemoteAuthorityOwner.swift`; `jarvis/bot/phone_remote_authority_channel.py`; `jarvis/bot/phone_admission_store.py`; `jarvis/bot/phone_remote_service.py`; `tests/unit/test_phone_admission_store.py`; `tests/unit/test_phone_remote_authority_service.py`; and `macos/MortimerHost/Tests/PhoneRemoteAuthorityTests/PhoneRemoteAuthorityProcessTests.swift`.
2. **WS-17 invocation stage, only after a trusted bridge exists:** `scripts/deploy_main.sh`; `tests/unit/test_deploy_main.py`; `tests/unit/test_deploy_held.py`; plus a focused restore-boundary test module if the independent review accepts one. Do not edit those paths under this docs-only proposal.
3. **Still-unresolved packaging/IPC stage:** the current native owner exposes a disposable test-owner process and a private inherited socketpair to its controlled Python child. The shell deployment helper is not that child and has no authorized owner channel. A private signed control-helper/XPC boundary or another independently reviewed, code-identity-checked design is required before WS-17 can call prepare/complete. Do not create a public HTTP/MCP route, trust UID/PID/path alone, pass bearer tokens in argv/environment/logs, or expose generic anchor/SQL commands. The exact helper target, signing requirement and entitlements are not reserved or selected here; production signing/package provenance is an explicit prerequisite.

## Source-supported path inventory (not an assertion about installed artifacts)

`scripts/deploy_main.sh` currently contains these relevant branches:

| Source path | Current behavior evidenced by source/tests | D3 classification |
|---|---|---|
| `--rollback-held SNAPSHOT` | The held implementation validates the envelope, quarantines services and stops the app, then checks archive identity/safety before checkout/extraction; it restores the app bundle, verifies identity, and records `services_restarted:false`, `databases_restored:false`, `settings_restored:false`. It leaves services held. Tests include `test_rollback_restores_code_app_but_not_settings_databases_or_service_state`, unsafe archive rejection, quarantine failure and orphan-liveness cases. | Supported code/app rollback path; must prepare/fence before the first code/archive mutation. The held archive validator rejects DB-like files and protected settings. This is source/test evidence, not execution against a real archive. |
| `--restore-local SNAPSHOT costs,vault` | The helper permits only the costs/vault subset, checks source/policy, starts selected local jobs, checks identity/health and keeps other services held. It does not copy or replace the phone SQLite authority database. Tests constrain targets and quarantine failures. | Service recovery/start path, not a database restore. If it can run while a phone owner is active, its start must remain behind the D3 owner gate; no claim that it changes phone data. |
| Newly generated non-held `ROLLBACK.sh` with no arguments | The current generator emits a pre-effect argument-count guard; a zero-argument invocation quits the app, checks out/extracts the code archive, restores the app bundle and kickstarts configured services. Synthetic tests assert every argument vector is rejected before command effects. The current non-held archive exclusion list is narrower than the held archive validator: it excludes top-level `data`/`logs`, but does not generally reject nested SQLite/config paths. No actual archive contents were inspected. | Supported generated code/app rollback template, but unsafe to treat as “code-only” until the exact archive is inspected/rejected for every database, WAL/SHM and protected-settings path. Fence before quit/checkout/extraction; restart only after acknowledged completion. |
| Historical generated `ROLLBACK.sh --restore-db` branch in the generator | Source still contains a dormant branch that boots out services, copies `jarvis.db`, deletes `jarvis.db-wal`/`jarvis.db-shm`, then bootstraps services. The newly generated argument guard makes this branch unreachable for current generated scripts. Persisted older scripts are not rewritten by the guard. No old script was opened or run. | Explicitly unsupported for new generated scripts; existing historical artifacts are unverified and must not be run. A test may render the old branch synthetically and assert refusal before effects; it cannot establish installed-artifact coverage. |
| `restore_code()` deploy-failure helper | In held mode it calls the held rollback; in non-held mode it checks out prior code and extracts the archive, with warnings on failure. During the build failure call site, services have not yet been restarted. It restores app bundle separately at the call site. | Supported failure-recovery code path; must share the pre-fence and archive policy rather than bypassing them. Test each failure point with fake commands and a disposable checkout. |
| Manual copies, old scripts, third-party backup tools, full-host migration or Keychain restore | No complete repository inventory can establish every user-held/host-level mechanism. The code contains no `phone_remote_restore_v1`, `prepare_restore`, or `complete_restore` implementation/call. | Unverified. WS-17 must enumerate supported mechanisms and explicitly disable/un-support paths not covered. Whole-host rollback of both SQLite and protected Keychain remains outside demonstrated detection; `ThisDeviceOnly` and readback are not anti-rollback. |

The table describes source in this checkout, not all scripts already generated under a user’s rollback directory or installed services. The prior generated-script guard is prospective: it does not rewrite or retire old artifacts. No old artifact, live database, Keychain item, archive, service state or user account was inspected.

## Narrow next offline source proposal: prepare/pending fence and child shutdown only

This revision deliberately stops before completion, database replacement, or WS-17 script integration. The only proposed executable source slice is a synthetic `restore.prepare` operation which establishes a durable pending authority fence in disposable SQLite plus an injected fake anchor, invalidates active sessions/tickets, closes service peers/queued output, and shuts down the controlled Python child. It never restores a file and never returns the system to stable/admitting state. D3 remains incomplete after this slice.

### Closed prepare request, ownership and lifetime

- The operation is accepted only from the already-controlled child over the existing private owner/child socketpair and only by the native owner. It is a testable internal phase, not a script API. The current deployment shell has no access to that socketpair, so this proposal does not claim `deploy_main.sh` invokes it. The operation selector is exactly `restore.prepare`; there is no completion or restore-release operation, generic anchor write, SQL, path, reset, or migration message in this slice. Ordinary grant release remains available only on the verified stable, pre-write denial path described below.
- The existing v3 envelope remains closed and size-bounded: exact top-level keys `protocol`, `version`, `kind`, `owner_incarnation`, `child_incarnation`, `sequence`, `correlation_id`, `payload`; `protocol` and `version` retain their existing v3 values. Every request/response uses the current strict sequence and correlation rules and the same owner/child incarnation pair. The only new operation is `restore.prepare`; there is no v1/v2 fallback, external controller frame, `complete`, stable-finalize, arbitrary anchor write, SQL, path, reset, or migration message.
- The child requests `child.grant.acquire` with exactly `{operation:"restore.prepare"}`. The matching `owner.grant.acquired` response carries exactly `{grant_id, operation}` and echoes that request's correlation ID. It then sends `child.anchor.read` `{grant_id}` and requires `owner.anchor.state` with the same grant/correlation and an exact stable anchor/database pair. It sends `child.anchor.advance` `{grant_id, step:"restore_pending", state}`; the matching `owner.anchor.verified` echoes the request correlation. `state` is the existing strict schema: same anchor version/host ID, generation exactly `G+1`, login counter unchanged, transition ID equal to a fresh canonical operation UUID, and pending state. The operation UUID is also the `operation_id`; host ID/generation are compared to the verified read, never trusted from a caller. Wrong incarnation, malformed/extra fields, duplicate/skipped sequence, wrong correlation, unexpected phase or operation-ID replay is terminal protocol failure with child/service teardown; it does not promise unchanged peers.
- After verified anchor readback, the child commits one SQLite transaction setting matching pending metadata and revoking active sessions. It then sends one-way `child.restore.database_pending` `{grant_id, operation_id}` with a fresh canonical correlation ID; the owner sends no response and advances only after validating its frame order, sequence and correlation. The child fences service admission, cancels queued output, closes registered peers and drains owned work, then sends `child.restore.fenced` with the same exact payload and a fresh request correlation ID. `owner.restore.prepared` is the response to this fenced request: it carries exactly `{grant_id, operation_id, host_generation, transition_state:"pending"}` and echoes the `child.restore.fenced` correlation ID. Thus `database_pending` is one-way, while `fenced` is the request whose response acknowledges prepare.
- Before attempting to send `owner.restore.prepared`, the native owner atomically retires its active normal grant and stores only a terminal `pending_shutdown(operation_id, child_incarnation)` phase record; the prepared response is then sent with the `child.restore.fenced` correlation ID. On receiving that response, the child retires its matching grant locally. The `restore.prepare` context must signal this terminal outcome so ordinary successful-context cleanup does **not** auto-send `child.grant.release`; there is no post-prepare release or stable return. Both endpoints permit only the shutdown handshake thereafter. The owner sends `owner.shutdown` `{reason:"requested"}` with a fresh correlation ID; the child accepts it only in the retired pending-shutdown phase and sends `child.shutdown_ack` `{}` echoing that shutdown correlation. The child then closes and exits. The native owner reaps the child, keeps the singleton lock in terminal pending hold, and allows no child relaunch, grant, service response or output. If prepared/shutdown send or acknowledgment is lost, the owner closes the channel, terminates and reaps the child, keeps the lock and remains pending; no normal release is attempted. Only test teardown may terminate the owner, without clearing pending state. The deployment helper receives no acknowledgment; no script or external process can invoke this source slice.
- A local busy result is decided before `child.grant.acquire` is sent; it leaves the active owner/peers/in-flight operation untouched. A well-formed `restore.prepare` policy/expected-identity denial is nonterminal only after the child has verified an exact stable anchor/database pair and before any anchor write; it uses ordinary `child.grant.release`, waits for matching `owner.grant.released`, then returns a typed local denial without service mutation. Missing, pending, corrupt or mismatched anchor/database reads remain failures handled by existing fail-closed behavior; do not convert them into the special nonterminal denial or broaden ordinary login/service denial rules. A lost/invalid release acknowledgment is uncertain and terminal. Malformed, wrong-incarnation or replayed wire traffic is terminal and requires child/service teardown; do not describe its peer state as unchanged.

### Exact prepare/pending phase table

| Phase | Required action and acknowledgment | Durable state / failure rule |
|---|---|---|
| P0 — preflight | Local busy sends no frame. Otherwise acquire `restore.prepare`, verify exact stable anchor/database pair and compare expected host/generation. A well-formed policy/expected-identity denial is allowed only after that exact stable verification; release normally and require `owner.grant.released`. | Busy or known pre-write denial leaves active service state unchanged. Missing, pending, corrupt or mismatched state is handled by existing fail-closed errors, not the special denial. |
| P1 — anchor pending | Owner writes the exact `G+1` pending anchor and verifies it by readback; returns `owner.anchor.verified`. | If no write call was made and failure is proven pre-write, old stable bytes may remain. Once write is invoked but not verified, outcome is uncertain: no prepared acknowledgment or external effect; current owner terminally blocks service. Do not claim pending bytes necessarily persisted. |
| P2 — SQLite pending | Child transaction writes matching pending metadata and revokes sessions; commit succeeds; child sends `child.restore.database_pending`. | If anchor pending was verified but DB pending commit fails or is uncertain, the pair is pending/mismatched and normal startup must refuse it. |
| P3 — service fence | Child closes service admission/peers, cancels queued output and drains owned work; sends `child.restore.fenced`. | Anchor and DB remain pending. No service output/dequeue is allowed. Failure before the owner has received both ordered child phase frames gives no prepared response; tear down and leave durable state as actually observed. |
| P4 — prepared response / grant retirement | Owner validates phase/order/incarnations, atomically retires its normal grant into `pending_shutdown`, then sends `owner.restore.prepared` echoing the `child.restore.fenced` correlation. Child accepts the response, retires its matching grant, and suppresses ordinary context auto-release. | Anchor and DB are verified pending and local service fence reported. No `child.grant.release` follows. A lost response is uncertain; perform no file, checkout, extraction or restart action; close/terminate/reap and retain the owner lock. |
| P5 — shutdown/reap/hold | Only the terminal pending-shutdown phase may send/accept `owner.shutdown`; it uses a fresh correlation ID and `child.shutdown_ack` must echo it. Child closes/exits; native owner waits until reaped. | No normal grant or release is legal. Native owner retains the singleton lock in terminal pending hold and serves nothing. Test-only owner termination leaves the persisted pair untouched. |

No phase finalizes the anchor or DB back to stable. On any later process start, the normal startup path may admit only if its actual read observes an exact supported stable anchor/database pair; a verified pending anchor, pending DB, or mismatch must refuse. If a write/readback was uncertain, the on-disk anchor is not presumed pending: no prepared acknowledgment or external mutation is allowed, and restart behavior follows the exact bytes that can be read (exact stable pair may pass normal validation; pending/mismatched state must fail). This is not a promise that every crash leaves a pending marker. `advance_host_generation()` cannot be reused because it completes its ordinary transition to stable.

There is **no completion path** in this source slice. There is no replacement child, database replacement/reconciliation, restore invocation, service restart, or return to stable/admitting state. The prepared acknowledgment is solely local to the owner/child protocol and is not permission for a deployment controller to continue.

The proposed narrow source paths are:

- `macos/MortimerHost/Sources/PhoneRemoteAuthority/PhoneRemoteAuthorityOwner.swift` — closed prepare message and pending-phase protocol; keep the owner lock and reject all normal grants while pending.
- `jarvis/bot/phone_remote_authority_channel.py` — exact child-side request/method mapping and phase validation. No external shell client.
- `jarvis/bot/phone_admission_store.py` — new begin-only pending transition that revokes sessions and commits matching pending metadata without finalizing stable; no DB replacement/reconciliation code.
- `jarvis/bot/phone_remote_service.py` — internal preparation wrapper that blocks service calls/output, closes peers and waits for owned work before child shutdown; no production constructor or route.
- `tests/unit/test_phone_admission_store.py`, `tests/unit/test_phone_remote_authority_service.py`, and `macos/MortimerHost/Tests/PhoneRemoteAuthorityTests/PhoneRemoteAuthorityProcessTests.swift` — disposable DB/fake-anchor tests, actual owner/child process and denial tests.

These seven paths are the complete source claim. They do not change WS-17's existing `scripts/deploy_main.sh`/`tests/unit/test_deploy_main.py` guard claim or add any deploy/held test path. The shell cannot call the current private channel; a signed XPC/control helper is a distinct package/signing design and later claim. The claim does not include completion, recovery-child/rebinding, DB replacement, restore invocation, WS-17 scripts, production Keychain, signing, installation or live service changes.

### Narrow deterministic acceptance matrix

All tests use a temporary database, injected fake anchor, actual disposable owner/child process, synthetic operation identifiers, barriers and fake peers/sinks. No real deployment script or restore runs.

1. Valid prepare with a stable tuple: verify exact pending anchor `G+1`/operation ID, matching pending DB metadata, session revocation, no stable finalization, owner admission latch closed, all peers/queued canaries fenced, child exits and owner singleton remains held.
2. A local busy request is rejected before any wire grant and leaves the active operation untouched. A well-formed preflight denial after the exact stable anchor/database pair is verified releases normally and leaves authority/service state unchanged. Separately inject malformed fields, wrong incarnation, replayed/skipped sequence, wrong correlation and repeated operation ID; these are terminal protocol faults and assert channel closure, child/service teardown and no further admission, without asserting peers remain unchanged.
3. Inject failure before any anchor write call, during the write, during readback, after verified anchor pending, before/after the SQLite pending transaction commit, before/after service fencing, before/after prepared response, and during shutdown/reap. Proven pre-write failure may leave the prior stable pair. An invoked but unverified write has uncertain persistence; assert no prepared acknowledgment or external action, then determine restart behavior from actual readable bytes. Only verified pending anchor/DB state is required to refuse normal startup; do not claim every crash necessarily leaves pending state.
4. Lost prepared acknowledgment: the test controller performs no file, checkout, extraction or restart action. If verified pending bytes persist, standard store opening by a replacement child fails closed. Duplicate prepare, changed operation ID, replayed sequence, wrong correlation or wrong incarnation triggers terminal teardown; it cannot clear pending state. A second local request is busy before wire dispatch and leaves the current operation intact; a second wire acquire is a protocol violation.
5. Existing peers cannot send another service response after fence; output dequeues nothing; old process-local ticket, receipt/ledger, challenge, peer and resource state is destroyed only after child exit. The new child has a distinct incarnation and cannot silently resume old results.
6. Assert exact frame order/payloads/correlations; normal release only for a verified stable pre-write denial; no release after prepared; grant retirement at both endpoints; shutdown permitted only in terminal pending phase; shutdown acknowledgment correlation; child reaped before terminal-hold observation; and lock retained until test-only teardown. Include existing login, challenge and ordinary service-denial regressions to prove their semantics are unchanged. Assert absence of completion, stable-finalize, archive/database replacement, deployment-script calls, launchctl/app restart and automatic recovery. The test establishes only prepare/pending shutdown.

### Deferred boundary/design requirements

- **Restricted recovery child and rebinding:** after the old writer is killed, a later recovery actor is needed to inspect/reconcile SQLite while the anchor is pending. Normal `open_store` correctly rejects pending state. Define a restricted recovery-only child with an exact allowed method set and new process incarnation; do not let the old child continue writing or open a normal child beside it.
- **Durable completion/ack hold:** a memory-only latch cannot prove that a stable finalization whose reply was lost will remain held after process death. A persistent, protected operation/activation record and startup/launch gate are needed before any complete/stable transition is designed. The existing anchor schema/Keychain adapter has no separately reviewed completion tombstone.
- **SQLite files are not atomically replaced as a set:** DB, WAL and SHM require writer quiescence, checkpoint/close, exact hash verification, safe same-filesystem staging, sidecar disposition, atomic swap boundaries and crash recovery. The ordinary checkout/build rollback path also needs review; this prepare-only proposal performs none of these steps.
- **Authority rows on an older DB:** preserve the existing plan requirement that restored authority be reconciled to the protected generation and old grants/sessions/tickets are invalid. Do not assume that bumping `host_generation` is enough, because stale grant/device/key rows could be reintroduced. This proposal does not require blanket re-pairing or choose a restore policy. A later reconciliation must prove the restored database is the exact authorized image and revoke/reconcile stale authority, or refuse completion.
- **Whole-host rollback:** if both the SQLite DB and the Keychain anchor are restored, this protocol cannot detect that with the current evidence. Requires trusted external recovery state/authority or an explicit decision to disable that restore class. `ThisDeviceOnly`, file hashes and readback are not rollback protection.
- **WS-17 invocation and startup:** no script path is modified here. Every supported checkout, archive restore, held rollback, local service recovery, generated and already-existing rollback artifact must later be wired to the trusted prepare/completion gate or explicitly remain unsupported. Existing scripts/artifacts are not retroactively safe. Normal checkout/build failures must not bypass a required pre-fence.



### Local source implementation and validation receipt

The adopted seven-file prepare-only source candidate is implemented at `4d6371caf490c4a36393560b6c97f355df647223` (tree `1dca0ce9d6a8ec5dd1d27e2e094708bdd7bdfd7a`). This is a local, unpublished candidate. It implements only the protocol above: pending fencing, service teardown, grant retirement, controlled-child shutdown/reaping, and retained owner lock. It does not implement completion, recovery/rebinding, database replacement, deployment integration, or live restore.

Author validation on the exact candidate rebuilt the disposable owner and ran 224 focused phone tests with 352 subtests, zero skips, using Python 3.12.13 and pytest 9.1.1. Eight restore-specific actual-process test methods and one restore-specific store test passed; all nine are included in the 224-test/352-subtest total, not additive. The process cases include alive-after-socket-close and withheld-shutdown-ack cases. Twenty-two selected Swift tests passed with zero skips in a temporary no-dependency package built from the exact owner sources. `python3 scripts/check_roadmap.py --main github/main` reported 0 errors and 0 warnings; `git diff --check` passed. Independent review separately reproduced 224 phone tests/352 subtests and 22 isolated Swift tests, all with zero skips. The full MortimerHost package test could not resolve its external WebRTC dependency; do not treat the isolated Swift package as full-package validation. Independent exact-source review ACCEPTED the exact source commit; the candidate remains unpublished, so exact-head CI is pending. No real Keychain, signing, installation, service shutdown, or restore was performed.

**Unresolved blockers:** The deployment controller has no authenticated owner API; after the old writer exits, no restricted recovery child or DB rebinding design exists; there is no durable completion-ack/startup hold; SQLite and WAL/SHM replacement is not atomic; WS-17 scripts/archives are not wired; already-generated/host-level artifacts are not inventoried; and same-generation or whole-host rollback is not detected. No DB rollback/re-pair policy is selected. This proposal does not mark D3 complete.


## R3.24 D3 recovery-completion design proposal (docs-only; not adopted source)

The coordinator adopted the independently accepted R3.24 design commit `e7eb2176f54f5c004be2bd16e159ce905080699a` (tree `b2b67ddfd4fbd4ab9960e93f11a6ce9aae5a7d67`) for the exact twelve-path offline source claim on `codex/ws04-ws17-d3-recovery-20261031`; adoption is recorded in the WS-04 row and canonical plan before code. Owner Codex; Luna author; existing independent WS-04 reviewer `01a18584-92e2-7511-aca8-983bb3f230ef`. Parent GitHub ownership refresh at 11:38 UTC found PR #290/main unchanged and no published collision; local status/path checks found no dirty conflict. The clone lacks `origin/main`, so the source branch descends from the accepted design and must reconcile main before integration. WS-04 owns owner/channel/store/recovery and service fencing; WS-17 retains restore/deploy invocation and scripts. Offline-only injected authorization, fake protected storage, disposable SQLite and controlled processes; no real Keychain, signing, installation, live database or restore. Independent exact-source review remains required; adoption is not source acceptance or live restore authorization.


### R3.24 design summary and limits

The adopted implementation scope requires checkpointed prepare after quiescent WAL normalization and a live-base digest, separately hashed backup image, and `prepare_resume` to distinguish exact-base from already-committed pending DB state after a lost acknowledgment. It freezes v4 supervision for recovery and normal-child lifecycle while preserving existing v3 operation names/payloads and six-field projection; `child.ready` is transport-only, and service admission waits for store.open release, schema validation, the exact DB-receipt/tombstone/retained-manifest comparison map, and owner/child activation. Normal v4 restore entry uses a fresh recovery operation ID bound to a `restore_quiesce` drain acknowledgment before mutation; its bounded barrier rejects new logical operations, settles queued unauthorised work locally, allows only already-authorized operation-bound continuations, and uses a fixed five-second monotonic deadline and bounded owned-child cleanup on uncertainty; v1/v2/v3 shutdown bytes remain unchanged, and existing exact channel/service/native version guards must be extended with regression coverage. It also defines the exact SQLite catalog including six pinned `sqlite_autoindex_phone_remote_*` rows with SQL NULL and tagged null encoding, and an O_EXCL `journal.next.tmp` that is validated/reclaimed and directory-synced before reuse rather than treated as cleanup state. The design preserves v1/v2 anchor/store compatibility, owner continuation/restart under the inherited singleton lock, per-file SQLite journal and dual-directory sync, DB-stable-before-anchor ordering, and readiness-gated completion. It distinguishes pre-quiescence policy denial from post-normalization technical failure, pending-operation continuation from stable-tombstone retry, and live-base hash from checkpoint-image hash. Retries use fresh request correlations but retain live process incarnations unless a process actually restarts, and perform zero repeated replacement effects; after pending, no denial or lost acknowledgment restores stable state or releases the hold. Existing R3.22 v1 pending state has no bound checkpoint and is explicitly refused as `legacy_pending_unbound`; it is not converted by guessing from the current database. Uncertain write/readback/rename/ack state cannot start normal service, and no distributed atomic commit is claimed.


### R3.24 drain-contract traceability note (2026-10-31)

The docs-only clarification in `c7cda2488ec8626c497ea95aa4e31bad6cc86904` restates the queued-before-authorization and bounded drain-failure contract already accepted in `e7eb2176f54f5c004be2bd16e159ce905080699a`; comparison found no new invariant or changed acceptance gate. The coordinator-adopted source claim remains active. Its partial local edits in the twelve claimed paths are preserved, uncommitted, incomplete, unpublished, and not independently accepted; no restore acceptance is claimed.

The corrected rule is operation-scoped: quiescence freezes only logical operations whose authorization has already completed. A queued `_submit` without authorization and receipt, and a caller cancelled before authorization, are removed and settled locally with zero authority IPC or service effects. After authorization, caller cancellation settles the caller but leaves the accepted operation owned through its exact `service.commit` and terminal bookkeeping; it cannot extend the frozen set or claim rollback. The owner uses one nonrenewable five-second monotonic drain deadline. A stalled continuation at the deadline, or a lost/malformed commit, release, or shutdown acknowledgment when observed, stops dispatch and grants and settles waiters as uncertain. `drained:true` is legal only in the child's `child.shutdown_ack` after receipt of `owner.shutdown` and completion of the frozen work set; no such acknowledgment may claim a stalled or uncertain drain. No checkpoint, pending transition, replacement, or prepared success follows drain failure. A later normal-child start is possible only after confirmed child reap, actual anchor/DB inspection under the lock, and successful ordinary stable-pair validation plus activation; it is not automatic or a recovery continuation. Cleanup closes the channel and targets only the owned child: TERM within the deadline, wait at most 250 ms, then KILL if needed and wait at most two seconds for confirmed reap. The singleton lock remains held; if reap is uncertain, remain unavailable and do not launch another child. Only after reap may the owner inspect actual state, without inferring rollback of an in-flight transaction.

The required regression matrix now names unauthenticated queued work/zero frames, precancellation/queue removal, post-authorization cancellation with retained operation ownership, exact authorized-commit continuation while new work is denied, fake-clock deadline expiry with no false `drained:true` in `child.shutdown_ack`, and lost commit/release/shutdown acknowledgments with bounded cleanup and retained lock. This is a traceability note, not an additional design gate or source acceptance. It does not widen the twelve-path claim or authorize publication, live recovery, restore scripts, or service changes.

The design does not wire `scripts/deploy_main.sh`, `scripts/backup_db.py`, old generated rollback scripts, current `--restore-local` or a live service. The backup helper creates snapshots; `--restore-local` currently affects costs/vault, not `jarvis.db`. Whole-host rollback restoring both DB and anchor remains undetectable without independent trusted state. Same-generation older SQLite images are not universally detected. No blanket revoke/re-pair policy is invented; current device/grant retention requires verified checkpoint reconciliation, otherwise recovery remains blocked.

The canonical plan records exact candidate WS-04 paths, separate WS-17 invocation ownership, frame/schema bounds, the rename/ack crash table and disposable actual-process acceptance. No source has yet been implemented or accepted. Native controller authentication, signing/entitlements, actual Keychain behavior, recovery invocation, supported archive inventory, ordinary checkout/build rollback and whole-host rollback handling remain open.

### R3.24 replacement implementation — 2026-10-31 (WIP; scope amendment pending)

Codex continued from immutable helper WIP `d1b616b92fb52b5597cb1b54eb8eedd605b178ce`
(tree `d0979c80ff1bc78d80faacbd7a9b4bbbda34397f`) in the authorized Mac checkout
on branch
`codex/ws04-ws17-d3-recovery-20261031`. Existing commits are preserved. This is
unfinished source, not acceptance or a complete review candidate.

The replacement WIP connects the closed recovery sequencer to the inherited
v4 channel and fixed-path SQLite executor; adds native-owner checkpoint,
pending-anchor, prepare/resume/recover child, database finalization, stable
anchor, cleanup and normal-child activation sequencing; and replaces the old
v4 cross-version fixture's false success assertion with fail-closed behavior.
The normal child now requires exact protected/store versions, retained manifest
and receipt mapping, cleanup completion, and the explicit activation exchange.
The owner keeps the singleton descriptor through child replacement and bounded
owned-child reaping. A local service-host quiescence/cancellation barrier is
present but is not accepted or fully process-validated.

The independent helper findings were addressed: explicit `BEGIN IMMEDIATE`
covers DDL, metadata, session clearing and receipt writes in both SQLite
isolation modes; the sequencer permits repeated inspection and phase-driven
crash continuation; illegal/reentrant/uncertain calls latch terminal failure;
and verified hashes plus exact integer types are checked before mutation.
New statement-failure, reentrancy, hash/type and crash-sequencing regressions
exercise those cases.

**New concrete scope blocker:** `PhoneRemoteLogin.__init__` in
`jarvis/bot/phone_remote_login.py` line 204 accepts only exact
`NativeProtectedAnchorV3`. The required full v4 `_AuthorityChildServiceHost`
therefore fails startup with `unsupported offline login dependencies`. That
module is outside the adopted twelve paths. No type spoofing, monkeypatch,
legacy-channel fallback, or omission of proof login is an acceptable fix.
A narrow amendment for that module and its existing login tests was requested;
no response or amendment is assumed, and neither file has been edited.
The prior store-only native-process recovery smoke is not full-service proof.

Validation of this WIP before the scope amendment:

- Existing v1/v2/v3 phone regression batch: 195 tests and 263 subtests passed
  in the isolated temporary Python environment, using the actual directly compiled native owner.
- Current recovery helper tests: 35 passed, nine subtests passed; the three
  blocked full-service process tests were explicitly deselected for this
  helper-only run, not counted as passes.
- Scoped Swift authority tests: 24 passed, zero failures, using an isolated
  temporary Swift package with symlinks to the actual source/test files,
  SwiftPM sandbox enabled and temporary caches. Direct `xcrun swiftc` also
  compiled the owner. This is not the full MortimerHost/JarvisKit suite.
- Before switching the recovery fixture to the full service host, 37 recovery
  tests/eight subtests passed, including actual native-owner/Python-child
  recovery, same-incarnation completed retry, completed restart, four lost
  mutation-ack restarts, and stable-anchor/cleanup restart. Those results cover
  the store-only child at that earlier working state, not current full-service
  startup or the whole accepted interruption/drain matrix.
- The subsequent current full-service combined run had 75 passes/four passing
  subtests and six failures (two tests plus four subtests) at the scope blocker.
  These failures are retained, not skipped or relabeled as passes.
- The normal package build was stopped while downloading the pinned WebRTC
  artifact; no package/toolchain/security setting was changed. The isolated
  authority package supplied the focused Swift result above.

The accepted design is unchanged. The full drain/durability/crash matrix,
complete controller retry/second-recovery behavior, independent exact-source
review and aggregate validation remain unfinished. No source acceptance,
publication, PR action, merge, real Keychain, live database, app installation,
WS-17 script or controller-model change occurred. `origin` remains the local
handoff clone without `origin/main`; GitHub DNS failed inside the ordinary
sandbox. Current-main reconciliation is still required before integration.

### R3.24 adopted scope extension — 2026-10-31

The coordinator independently verified and adopted adding only
`jarvis/bot/phone_remote_login.py` to the existing twelve source/test paths,
for thirteen effective paths on `codex/ws04-ws17-d3-recovery-20261031`.
Fresh local inspection found that target unchanged and no dirty target edit;
its last change is accepted R3.18 integration `860835238ab5ed3b138703ef738cc2f6982a2218`.
The registered local worktrees remain the prior results/design/refinement
lanes; none is a second recovery implementation. The parent retains the
independent immutable WIP review. This amendment is recorded before editing
that source file and is technical claim adoption, not product or source acceptance.

The new module change is limited to importing V4, annotating the two supported
concrete anchor types, and accepting exactly V3 or V4. All other exact
dependency, store-anchor identity, ownership, signature, expiry, replay and
login-proof checks remain binding. The existing claimed channel must remove
its proofless V4 `store.login` allowance: V4 uses `login_proof` exactly like V3.
Regressions belong in the already claimed authority channel/service test
modules; `test_phone_remote_login.py` is read/run unchanged. No additional
source or test path is added. The full recovery/drain/crash matrix and
independent source review remain open. No live action or publication is authorized.

### R3.24 proof-login and continuation slice — 2026-10-31 (unreviewed)

Implemented the adopted exact V3/V4 login guard amendment and removed V4
proofless login. Actual owner/child proof-success, replay, failed-proof-limit,
expiry and service-authorize/commit assertions pass with v4. New local tests
cover exact dependency/subclass rejection, queue cancellation/removal, retained
authorized ownership, nonextending deadline settlement and failed-resource-close
refusal. Fixed terminal admission publication before caller wakeup. Native v4
shutdown now validates the exact drained acknowledgment while v1/v2/v3 bytes
remain unchanged. Native recovery validates all inspect/stage/install/pending
reply shapes and bindings, supports a fresh second recovery after a tombstone,
and resumes the exact base after a pending-anchor interruption.

Validation: recovery, authority-service and unchanged proof-login modules passed
91 tests and 31 subtests using the directly compiled native executable and
isolated Python environment; the focused log is retained locally. This is
focused evidence, not full acceptance: remaining actual-process drain and
durability/receipt matrices, aggregate checks and independent source review
remain in progress. No public writes, live actions or scope expansion occurred.

### R3.24 offline recovery implementation candidate — 2026-10-31 (independent review pending)

The adopted thirteen-path offline implementation is connected end to end. The
native owner retains singleton supervision through normal v4 activation, a
fixed five-second admission/drain barrier, bounded owned-child TERM/KILL/reap,
checkpointed prepare, prepare-resume, recovery, stable-anchor readback, durable
cleanup and normal-child reactivation. The injected offline controller can
continue the same pending operation in the same owner after uncertain child
completion; other operation IDs and retired completion IDs have no replacement
effects. Completed retries retain healthy process identities, use fresh request
correlations and do not require the old backup source or send quiescence. A
new recovery preserves the previous receipt until its own completion and gets
a fresh owner-generated operation ID. Test-controller mailboxes and teardown
are confined to the disposable fixture; they do not implement production caller
authentication or expose a phone endpoint.

The candidate includes explicit atomic SQLite DDL/data transactions, strict
manifest/receipt and integer bindings, terminal uncertain/reentrant protocol
handling, actual-phase restart, independent native checkpoint verification,
private no-follow file checks, WAL-aware recovery reads, journaled renames and
cleanup, canonical source IDs, and exact v4 proof-login dependency guards.
Native SQLite opens account for macOS system path aliases while retaining
NOFOLLOW on the database. Ordinary v4 proof login, service authorization/commit,
signout and security revocation preserve the protected completion tombstone;
readiness compares receipt/manifest fields rather than the historical live-DB
digest. Legacy unbound pending state remains held without implicit conversion.

Final validation on the candidate source: all thirteen `test_phone*.py` modules
passed **322 tests and 425 subtests**, with no skips, using
the isolated temporary Python interpreter and the directly compiled actual native owner.
The isolated authority Swift package, referencing the real source/test paths
and retaining normal SwiftPM sandboxing, passed **24 tests, zero failures**.
Coverage includes actual happy paths, repeated/lost acknowledgments, same-owner
and replacement-owner continuation, second recovery, source/preflight denial,
rename/commit/finalization/cleanup interruption, partial journal temp recovery,
receipt-field mismatches, activation uncertainty, queued cancellation, frozen
service continuation, fixed-deadline failure, forced KILL/reap, and a surviving
v4 child's inherited singleton exclusion after owner death. Existing proof,
results snapshot/resume, six-case refinement and v1/v2/v3 regressions remain in
the aggregate run. Final Python and Swift logs are retained locally;
the source review manifest records their hashes.

This is a source candidate, not independent source acceptance, production
readiness or live-restore authorization. Full repository pytest and the full
MortimerHost application package were not run in this slice; the earlier full
package attempt stopped during its pinned WebRTC artifact download. The scoped
Swift result is not represented as a full application build. Current-main
reconciliation and independent exact-source review remain integration gates.
The parent reports published WS05-only PR290 head
`39208d18d8c6fde0a9a0539e4d7c3aa68de5610f`, tree
`e31cdf9531908b0186d71d7af573da877e7b7eec`, parent `46e29c`; the cumulative
local branch already includes equivalent WS05 work through `4e2152`, so no
reset/rebase was performed. The parent owns CI544 and later reconciliation.
No public writes, PR approval, merge, live database, real Keychain, app install,
signing, controller-model change, WS17 script edit or production action occurred.

### R3.24 independent-review corrections — 2026-10-31

Addressed both findings against `7dc80e0093a0921f8c110e898180d8576bdb2d74`.
Cancellation is checked before queue insertion, retained on the owned request,
and observed by the worker before dispatch and at the authority boundary. The
worker also observes cancellation before publishing a successful terminal
result. Authorized work retains ownership and finishes its continuation; no
rollback is inferred. The deterministic fast-worker regression prevents the
caller cancellation poll from running until the worker settles and exercises
pre-submit, queued, pre-authorization and post-authorization cancellation plus
an uncancelled control. Running this regression against the original candidate
fails all four cancellation cases, while the corrected source passes. The
pending-anchor validator now checks the nested target generation's exact integer
type before dictionary comparison; floats, booleans and strings are rejected.

Validation: all thirteen phone modules pass **323 tests and 434 subtests**, zero
skips, with Python warnings treated as errors and the pytest-asyncio function
fixture-loop scope explicitly configured. A fresh native build using only
permitted temporary module caches succeeds, and the scoped Swift suite passes
**24 tests** with normal SwiftPM sandboxing enabled. The delivered reproduction
script independently creates a second fresh temporary build, redirects Swift,
Clang, SwiftPM manifest/cache/config/security paths there, builds the actual
native owner, and passes the same 24 tests. No sandbox-disabling flag or user
cache write is used. `r324-review-correction-artifacts/build-and-test-native.sh`
in the task artifact directory contains the exact commands; the corrected
source manifest binds that script, build artifacts and validation logs. The
earlier Python warning-as-error invocation stopped during pytest-asyncio
configuration before tests ran; specifying its existing function fixture scope
resolved that environment configuration issue without suppressing warnings.

Independent re-review is still required; full application/repository and live
validation remain outside these focused receipts. Source edits for this fix are
limited to the already claimed service/recovery modules and their two test
modules. No public write, merge, live action, new scope or model change occurred.

### R3.24 bounded acceptance and docs finalization — 2026-10-31

Coordinator reports independent offline source/process acceptance of
`04afff4c4a4594c9bd1182a10ba45bb6a1fc0986`, tree
`78ebb547f1e67ac7962dcf93e14a3cdceba08ef5`; both review findings are resolved.
Independent native rebuild SHA256 is
`64cfe906ff8f2f1bc9d58bdb615edb3ff033cef71fc5fbc7267877a66572dacd`.
Reviewer passed 323 phone tests/434 subtests, zero skips, warnings as errors,
with that rebuilt owner. Reviewer compared 15 changed/2,151 unchanged paths
against the accepted design. Author scoped Swift receipt covers 24 tests;
independent Swift startup was denied at `sandbox_apply`, so the reviewer verified
the receipt without independently executing those tests. The author's second
fresh build is not independent review or additional distinct test coverage.

This finalization edits only ROADMAP, the existing remote-access plan and this
log, preserving accepted source. The plan records the complete evidence boundary
and proposes typed mobile-view result commands plus production local-controller
authentication/construction prerequisites. Proposal only: no new source claim,
shared operation reservation, source change or activation. Full frozen-oracle
mapping, full repository/app tests, independent Swift execution, current-main
reconciliation, public integration and live gates remain open.

Public baseline reported by the coordinator is
`39208d18d8c6fde0a9a0539e4d7c3aa68de5610f`, tree
`e31cdf9531908b0186d71d7af573da877e7b7eec`. The local public commit object is
absent. Local `4e2152ec1b890e5383c42ac39d5605d57875886a` has exactly that tree;
use it for the cumulative manifest without asserting public-commit ancestry.
The final docs commit/tree and generated exact manifest are delivered outside
this commit. Parent retains CI544/publication coordination. No public write,
merge, deployment, real Keychain, live restore or controller-model change occurred.
