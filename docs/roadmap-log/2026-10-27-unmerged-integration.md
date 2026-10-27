---
date: 2026-10-27
system: codex
rows: [WS-03, WS-20, WS-23, WS-30]
prs: []
---

# Remaining Mortimer work — draft integration manifest, 2026-10-27 UTC

System: Codex. Integration branch: `integration/unmerged-mortimer-20261027`.
Base: `5581d4f913d21cbc69a707905a9898780b4a1e3c` (2026-10-27 02:08:07 UTC).
Larry requested a new PR for all unmerged work. This is a reviewable aggregation
of the current claimed candidates, not approval to merge, deploy, activate or
complete their acceptance. Original branches, indexes and dirty worktrees are
preserved. No feature was implemented by the integration worker.

## Included current lanes

| Lane / original owner | Exact source | Included work / limits |
|---|---|---|
| WS-03 / Codex dispatcher, historical Claude patch author | `369057b1938b48fb70ec3fec066dac3cbdd1884a`; commits `fa8698d`, `4afd099`, `369057b` | Existing canonical plan/log dispatch, timeout/recovery and immutable-history entries. No adapter source returned/applied in the inspected lane. Requested versus observed model attribution remains historical; no model call/change here. |
| WS-23 / Codex | `1b07fd882ba0246768138d110fe8003a91a36730`; commits `9eb6c96`, `0cbe7b5` | Exact unused `jarvis/acceptance_evidence.py`, corresponding tests, canonical plan/log. Standard library only; no product caller, runner, store or I/O. Independent exact-source review remains pending. |
| WS-30 / Codex | remote `2cca0f1eedbf90a4fbdaf1e4babf026ac58795ba`; commits `8859bef`, `954c8ee`, `2cca0f1`; local head `ffecab10f6c16338423530703667df67377a3784` plus two dirty files | Test-local phone admission model and synthetic v1 fixture, canonical plan/log. Dirty author repair snapshot supersedes the earlier model/fixture bytes only; no product/runtime import or listener. Renewed independent oracle review remains required. |

Non-ROADMAP deltas were applied with Git three-way context and no conflicts.
Stale branch ROADMAP copies were not imported: current owners, scopes, all 32
IDs and every acceptance checkbox from base are retained, with dated integration
notes added only for the included lanes and WS-20 coordinator. Main's newer
WS-05/WS-32 records remain authoritative. No competing plan is introduced.

## Dirty WS-30 snapshot and review state

The owner task was idle after an interrupted repair turn. Its prior independent
oracle verdict was **REVISE**, applying to `954c8ee` (unchanged source at
`2cca0f1`): R1 stale-authority rollback could resurrect revoked grants, R2
malformed types/identities bypassed typed refusal, R3 nonfinite fake time bypassed
expiry. This integration does not claim those findings independently closed.
Only the two tracked project files below were copied; neither original changed.
The original 35 vectors, six sensitivity cases, three isolation probes and
constants are retained; the repair snapshot contains 67 vectors. These expected
outcomes remain author candidates, not an approved independent oracle.

| File | SHA-256 | Bytes |
|---|---|---|
| `tests/fixtures/phone_admission_contract/v1.json` | `92c82e4508189aa94165c9833f6ab202c944f7c3635ee95bed8b6f24854e06d8` | 129346 |
| `tests/unit/test_phone_admission_contract.py` | `9da359b176f2fda83dbd1f340ff9e1786f85ff76cc59c8e743ab1f4239cc77fc` | 26121 |

The earlier owner's publication hold is preserved as a **not-ready-for-merge**
review gate. Larry's later explicit request permits publishing this unfinished
aggregate draft; it does not turn the candidate into an approved oracle or
supersede independent review requirements. No runtime authority is added.

## Missing implementations and nonincluded local state

- **WS-05 fixture isolation:** main registration #272 exists; no implementation
  branch/source found in the inspected claimed lanes or remote refs. Main's
  #276 leading `landed` versus prose fixture claim inconsistency remains
  disclosed; owner/coordinator reconciliation precedes future implementation.
- **WS-31 NR1:** main registration #269 exists; inspected WS-31 main/claim/readiness
  lanes contain registration/history, no NR1 implementation. A gap is not an
  included implementation.
- **WS-03 adapter:** only the author dispatch/history above exists in its current
  lane. No fabricated adapter source is included.
- **WS-24:** exact recovery source `38b0fcd` already merged through #270; no new
  runtime/persistence work is imported.
- A scratch merge checkout contains the fixture registration already adopted
  through #272; it supplies no separate repair. An incomplete historical REA
  checkout presents 1,923 apparent deletion entries; these are not treated as
  authored work and are entirely excluded. No generated/private host artifacts,
  credentials, ignored files, operational receipts or raw model transcripts are
  copied into this PR.
- #275, #276 and #277 are already merged in the base, not new included work.
  All five final-head #277 checks later completed successfully. No existing PR
  was closed or superseded by this integration. Remote inventory found zero open
  PRs immediately before assembly.

## Complete nonancestor remote-ref disposition

Nonancestor does not mean unmerged product work: many old PRs were squashed or
reintegrated. Exact merged-PR source ancestry/composite checks, current canonical
plans and explicit replacement records distinguish those cases. Deferred rows
are **not included** and are not represented as completed or deleted. Their
owners must establish current intent/scope before any later import.

| Remote branch | Head | Disposition | Evidence / reason |
|---|---|---|---|
| `claude/ws05-harness-matrix-20261022` | `a568f7dc282fff7436a4527feb7d162a2b021c81` | ALREADY MERGED PR HISTORY | [#253](https://github.com/Larryfix71566/jarvis-voice-ai/pull/253). Exact merged PR head or its ancestor; current main has the PR outcome despite nonancestor/squashed history. No new branch work evidenced. |
| `codex/acceptance-clearance-20261018` | `e28452676c38c989308668fe3377c79ac9cd2635` | SUPERSEDED/HISTORICAL | [#247](https://github.com/Larryfix71566/jarvis-voice-ai/pull/247). Closed #247; historical continuity adopted by #271/#273 and #277; retain current WS20 history, not frozen status. |
| `codex/phone-access-plan-20261022` | `87f163a7619596104e27af0bf50a3b6b88d28809` | SUPERSEDED/HISTORICAL | [#240](https://github.com/Larryfix71566/jarvis-voice-ai/pull/240). Closed #240; current provisional phone plan/main claim #268 supersede this older revision. |
| `codex/release-consolidation-20260917` | `1318f6512a46d59b13c8e00b1b008da70a7c4aa2` | ALREADY MERGED PR HISTORY | [#80](https://github.com/Larryfix71566/jarvis-voice-ai/pull/80), [#79](https://github.com/Larryfix71566/jarvis-voice-ai/pull/79). Exact merged PR head or its ancestor; current main has the PR outcome despite nonancestor/squashed history. No new branch work evidenced. |
| `codex/ws03-offline-package-adapter-20261022` | `369057b1938b48fb70ec3fec066dac3cbdd1884a` | INCLUDED | No matching PR. Bounded current lane delta imported; original branch retained. WS30 dirty author repair snapshot overlays committed candidate. |
| `codex/ws05-harness-recommendations-20261022` | `6e779ca354271e84959e1e2b388864f776ed2883` | ALREADY MERGED PR HISTORY | [#242](https://github.com/Larryfix71566/jarvis-voice-ai/pull/242). All nonmerge commits absent by ancestry are exact source heads of already merged PRs; historical composite, not new work. |
| `codex/ws05-ws17-preview-794a298` | `794a298e3498d1b6e3e4fa47519449f35c06bb3d` | SUPERSEDED/HISTORICAL | No matching PR. Frozen preview; main pipeline/voice_sources blobs match its later e74e4b8 derivative; current provider/release records #232/#233/#234 govern. |
| `codex/ws05-ws17-selective-preview-e74e4b8` | `e74e4b8e66916bb0de64c76a62333e6e4971e90f` | SUPERSEDED/HISTORICAL | No matching PR. Frozen source comparison adopted through #232/#233; main pipeline/voice_sources exact blob matches, provider policy subsequently corrected. Do not replay stale policy. |
| `codex/ws20-checker-enforcement-20261022` | `86d079f74de6b3bb07d2f05deeec18a516f472ea` | SUPERSEDED/HISTORICAL | [#252](https://github.com/Larryfix71566/jarvis-voice-ai/pull/252), [#250](https://github.com/Larryfix71566/jarvis-voice-ai/pull/250). Enforcement merged #250; closed #252 closeout adopted #273 and restored #277. |
| `codex/ws23-verifier-foundation-20261022` | `1b07fd882ba0246768138d110fe8003a91a36730` | INCLUDED | No matching PR. Bounded current lane delta imported; original branch retained. WS30 dirty author repair snapshot overlays committed candidate. |
| `codex/ws30-synthetic-admission-s0` | `2cca0f1eedbf90a4fbdaf1e4babf026ac58795ba` | INCLUDED | No matching PR. Bounded current lane delta imported; original branch retained. WS30 dirty author repair snapshot overlays committed candidate. |
| `docs/c6-remaining` | `c842431bbb7f276460262247608f8752ef3db6d4` | ALREADY MERGED PR HISTORY | [#74](https://github.com/Larryfix71566/jarvis-voice-ai/pull/74). Exact merged PR head or its ancestor; current main has the PR outcome despite nonancestor/squashed history. No new branch work evidenced. |
| `docs/continuation-handoff-20261022` | `028b44e11acff9dff3e00380e1624c8657ce545c` | SUPERSEDED/HISTORICAL | [#246](https://github.com/Larryfix71566/jarvis-voice-ai/pull/246). Closed #246; sanitized source attachments/continuity adopted by #271; immutable history stays linked. |
| `docs/cx15-scope-confirmation-20260930` | `4e540defbdf34b967b536f1780bf96417d749afc` | SUPERSEDED/HISTORICAL | [#138](https://github.com/Larryfix71566/jarvis-voice-ai/pull/138). Closed #138; September CX15 scope snapshot superseded by current WS17/21 ownership. |
| `docs/memory-automation-next-phase` | `af675f9be5c01600165cf3d74ad97b310f3b20ad` | ALREADY MERGED PR HISTORY | [#77](https://github.com/Larryfix71566/jarvis-voice-ai/pull/77). Exact merged PR head or its ancestor; current main has the PR outcome despite nonancestor/squashed history. No new branch work evidenced. |
| `docs/plan-status-headers` | `c9a9e5484f78b2013ddf8c0d434403f56d880090` | ALREADY MERGED PR HISTORY | [#75](https://github.com/Larryfix71566/jarvis-voice-ai/pull/75). Exact merged PR head or its ancestor; current main has the PR outcome despite nonancestor/squashed history. No new branch work evidenced. |
| `docs/rea-integration-publish-20261022` | `b23b824ff15e450fae60535b38a95559eeda9396` | SUPERSEDED/HISTORICAL | [#245](https://github.com/Larryfix71566/jarvis-voice-ai/pull/245). Closed #245; sanitized REA documentation/main registration adopted by #269; no NR1 implementation. |
| `docs/reconcile-status-88b206f` | `2d618bb1269bef27ad274975d2af3c2104316852` | ALREADY MERGED PR HISTORY | [#81](https://github.com/Larryfix71566/jarvis-voice-ai/pull/81). Exact merged PR head or its ancestor; current main has the PR outcome despite nonancestor/squashed history. No new branch work evidenced. |
| `docs/roadmap-sync-20261005` | `011fdb99021be991c078ec01e0714d24c4834e07` | SUPERSEDED/HISTORICAL | [#174](https://github.com/Larryfix71566/jarvis-voice-ai/pull/174). Closed #174; older deployment/status snapshot superseded by #191/#254/#277. |
| `docs/wave-and-agent-recovery` | `37f8cd9778cb718d584fb6ae436da97d3e195c05` | ALREADY MERGED PR HISTORY | [#76](https://github.com/Larryfix71566/jarvis-voice-ai/pull/76). Exact merged PR head or its ancestor; current main has the PR outcome despite nonancestor/squashed history. No new branch work evidenced. |
| `feat/orb-crystal-glass` | `810c615bb9fa2a0bcd1145c02262075266d5191f` | DEFERRED — HISTORICAL FOLLOW-UP | [#90](https://github.com/Larryfix71566/jarvis-voice-ai/pull/90). Branch extends the recorded merged PR head; later historical delta not proven adopted. No active claim/current author verified; reconcile before replaying. |
| `feat/selfedit-authoring` | `888feff042a13354203a939a945b364108375ebc` | ALREADY MERGED PR HISTORY | [#48](https://github.com/Larryfix71566/jarvis-voice-ai/pull/48). All nonmerge commits absent by ancestry are exact source heads of already merged PRs; historical composite, not new work. |
| `fix/audio-device-resilience` | `7435659e691aaece897a5e51e558639484beb08c` | DEFERRED — HISTORICAL FOLLOW-UP | [#73](https://github.com/Larryfix71566/jarvis-voice-ai/pull/73). Branch extends the recorded merged PR head; later historical delta not proven adopted. No active claim/current author verified; reconcile before replaying. |
| `fix/sandbox-baseline-source` | `141f44c215943ba9d87eb5905379a9f968a21cfb` | ALREADY MERGED PR HISTORY | [#78](https://github.com/Larryfix71566/jarvis-voice-ai/pull/78). Exact merged PR head or its ancestor; current main has the PR outcome despite nonancestor/squashed history. No new branch work evidenced. |
| `jarvis/self-edit/20260822-expand-the-bottom-of-stage-live` | `a528ce33208114891e81a1f79c8f959b9a9d3cc8` | DEFERRED — UNCLAIMED/UNKNOWN | No matching PR. No matching active main claim or current author provenance established; do not import obsolete runtime/agent instructions or unrelated app registration. Owner review required. |
| `jarvis/self-edit/20260830-consolidated-display-output-each` | `02b71510fbf90903123e5cb50e341139a85061ca` | DEFERRED — UNCLAIMED/UNKNOWN | No matching PR. No matching active main claim or current author provenance established; do not import obsolete runtime/agent instructions or unrelated app registration. Owner review required. |
| `jarvis/self-edit/20260908-add-edge-resize-handles-to-the-d` | `ae2ec89c7d9c0440e3feae4f410a5fee654f0e4a` | ALREADY MERGED PR HISTORY | [#49](https://github.com/Larryfix71566/jarvis-voice-ai/pull/49). Exact merged PR head or its ancestor; current main has the PR outcome despite nonancestor/squashed history. No new branch work evidenced. |
| `jarvis/self-edit/20260908-add-zoom-and-pan-to-macos-mortim` | `79b0b7e33cad2203a4aa7c16056f6c47c7227ae1` | ALREADY MERGED PR HISTORY | [#47](https://github.com/Larryfix71566/jarvis-voice-ai/pull/47). Exact merged PR head or its ancestor; current main has the PR outcome despite nonancestor/squashed history. No new branch work evidenced. |
| `maintenance/gap-closure-audit` | `0b21ab77985e6a80dd1e87249516f0b7aade81d3` | DEFERRED — HISTORICAL FOLLOW-UP | [#62](https://github.com/Larryfix71566/jarvis-voice-ai/pull/62). Branch extends the recorded merged PR head; later historical delta not proven adopted. No active claim/current author verified; reconcile before replaying. |
| `mortimer-dev` | `d16b9181ef779bfc4df0ad9f5d7dccd41fc00b0f` | DEFERRED — UNCLAIMED/UNKNOWN | No matching PR. No matching active main claim or current author provenance established; do not import obsolete runtime/agent instructions or unrelated app registration. Owner review required. |
| `plan/self-service-access-and-recovery` | `7020052ecbf9211db69808ae6b6b423677759eea` | SUPERSEDED/HISTORICAL | No matching PR. Historical proposal; both canonical documents already exist on main under WS06 and have evolved. No current unmerged implementation identified. |
| `ws21/roadmap-after-merge` | `33f5778fca287b39f892ba845b04b446fd752bbc` | SUPERSEDED/HISTORICAL | [#172](https://github.com/Larryfix71566/jarvis-voice-ai/pull/172). Closed #172; older lifecycle record superseded by #191/#254/#277. |

## Local claimed-lane inventory

The existing Codex task entries for WS-03/WS-23/WS-30 and adjacent claimed lanes
were idle at inspection; this is activity evidence, not owner reassignment.
Only the exact selected snapshots above are imported. Checkout labels below
omit private absolute host paths. Original branch tips and dirty-file hashes
are rechecked before publication. Kimi's #276 row explicitly requires a new
dispatch for further work; this aggregate does not edit that adopted row.

| Checkout label | Head | Branch | Dirty paths | Disposition |
|---|---|---|---|---|
| `mortimer-sync` | `b23b824ff15e450fae60535b38a95559eeda9396` | `docs/rea-integration-publish-20261022` | 0 | SUPERSEDED/HISTORICAL |
| `mortimer-ws23-claim` | `fb4b2cb2ae4e259ab302cba2db76f94d9107fa25` | `docs/ws23-evidence-contract-claim-20261022` | 0 | ALREADY IN MAIN by ancestry |
| `mortimer-ws23-runtime` | `1b07fd882ba0246768138d110fe8003a91a36730` | `codex/ws23-verifier-foundation-20261022` | 0 | INCLUDED current selected lane |
| `mortimer-ws24-claim` | `b37a28b6ac8d71595c49a8fe188bab1c9f34497e` | `docs/ws24-recovery-contract-claim-20261022` | 0 | ALREADY IN MAIN by ancestry |
| `mortimer-handoff` | `028b44e11acff9dff3e00380e1624c8657ce545c` | `docs/continuation-handoff-20261022` | 0 | SUPERSEDED/HISTORICAL |
| `mortimer-ws24-runtime` | `38b0fcd4ca9bceb9e95607451520e9b3d5dfc76f` | `codex/ws24-recovery-foundation-20261022` | 0 | ALREADY IN MAIN by ancestry |
| `mortimer-merge-check` | `d4fde41220bb66073631496333371f9c53d89d97` | `(detached)` | 3 | EXCLUDED scratch merge of fixture registration already merged #272; no implementation |
| `mortimer-dispatch` | `e508df324ed6a753db9540525f2bbccf58390dc4` | `docs/roadmap-preparation-claims-20261022` | 0 | ALREADY IN MAIN by ancestry |
| `checker-enforcement-main-readback` | `6234949a524c84c91e6a459658cf02f290eac20e` | `(detached)` | 0 | ALREADY IN MAIN by ancestry |
| `checker-enforcement` | `86d079f74de6b3bb07d2f05deeec18a516f472ea` | `codex/ws20-checker-enforcement-20261022` | 0 | Historical local head from merged PR; not replayed |
| `checker-policy-claim` | `83fc361233be77bd76346c8043268af89188947c` | `docs/ws20-checker-policy-claim-20261022` | 0 | Historical local head from merged PR; not replayed |
| `checker-policy-main-verification` | `636880eabbe9dc756c30df7128d0a90c02d222bd` | `(detached)` | 0 | ALREADY IN MAIN by ancestry |
| `checker-policy-isolated` | `bd02062df71f4a1a24dd3b65ce2c41ef99454b7b` | `docs/ws20-policy-isolated-build` | 0 | ALREADY IN MAIN by ancestry |
| `repo` | `e28452676c38c989308668fe3377c79ac9cd2635` | `codex/acceptance-clearance-20261018` | 0 | SUPERSEDED/HISTORICAL |
| `ws20-program-update` | `9a876864d5bca795b7a60ad7a2a111a0cb03819f` | `docs/ws20-program-receipts-20261022` | 0 | ALREADY IN MAIN by ancestry |
| `ws03-offline-package-adapter` | `369057b1938b48fb70ec3fec066dac3cbdd1884a` | `codex/ws03-offline-package-adapter-20261022` | 0 | INCLUDED current selected lane |
| `ws03-implementation` | `e13fc89221c964d9ace0699550a0b39b0f123f39` | `codex/ws03-compatibility-p0-20261022` | 0 | ALREADY IN MAIN by ancestry |
| `ws03-postmerge-status-implementation` | `aadb01e719064c564497f80c66c4b3c5430863c1` | `docs/ws03-status-landed-20261022` | 0 | ALREADY IN MAIN by ancestry |
| `ws03-offline-adapter-claim` | `5cfc4c97db4dfc36308ac9709b5214400e51db0d` | `docs/ws03-offline-adapter-claim-20261022` | 0 | ALREADY IN MAIN by ancestry |
| `phone-plan-project` | `ffecab10f6c16338423530703667df67377a3784` | `codex/ws30-synthetic-admission-s0` | 2 | INCLUDED committed lane plus only two hashed dirty files |
| `publication` | `d476905057fc29207338721ce9ec2a452cb2085d` | `codex/ws05-harness-recommendations-20261022` | 0 | ALREADY IN MAIN by ancestry |
| `harness-integration-claim` | `ce63de45565d4dcb9e8e7fe73c9d1990b1b9db0a` | `docs/claim-ws05-harness-integration-20261022` | 0 | ALREADY IN MAIN by ancestry |
| `harness-remediation-claim` | `fc439e76ab097fb0434eae0bf538a58385e4d481` | `docs/claim-ws05-harness-remediation-20261022` | 0 | ALREADY IN MAIN by ancestry |
| `harness-remediation` | `004171c31cd15049fdd63523d251d77c4cd9d671` | `codex/ws05-harness-remediation-20261022` | 0 | ALREADY IN MAIN by ancestry |
| `mortimer-ws31-main` | `5628d146da44a889f37b0db9ba29314c7f48be22` | `docs/ws31-main-integration-20261022` | 0 | ALREADY IN MAIN by ancestry |
| `mortimer-ws31-claim` | `eb413a25d80df202af8e6d0f04e737ef0463b992` | `docs/ws31-no-reference-claim-20261022` | 0 | DEFERRED historical/claim/scratch head; current source inclusion not established |
| `mortimer-ws31-readiness` | `1043b9661852deb50af7fe9a82df68e491907df2` | `(detached)` | 0 | ALREADY IN MAIN by ancestry |
| `mortimer-rea-docs` | `dd8e4f9a83d6e7e9a095a1657d001001f22e1586` | `docs/rea-integration-20261022` | 0 | DEFERRED historical/claim/scratch head; current source inclusion not established |
| `repo` | `b136a2a66032b17082776a01353abe67e352c31e` | `(detached)` | 1923 | EXCLUDED incomplete checkout; apparent deletions are not authored changes |
| `subscription-retirement` | `014f915bd8f8ac9a5e187779601fe1718d7e21b5` | `codex/ws05-subscription-retirement-20261020` | 0 | ALREADY IN MAIN by ancestry |
| `alpha11-integration` | `7484b7d3dc3ef954bbe28a6756b8bccd8aeee016` | `codex/ws05-alpha11-integration-20261022` | 0 | ALREADY IN MAIN by ancestry |
| `worker-fixture-claim` | `9baeb10a1d8f8f0ef748ce695822dd380544989d` | `docs/ws05-worker-fixture-claim-20261023` | 0 | ALREADY IN MAIN by ancestry |
| `worktree` | `754b7b5f0009cb6ec3d48c69a6d3ad9a0fa36f9c` | `codex/mortimer-enhancement-plan-20261018` | 0 | ALREADY IN MAIN by ancestry |
| `ws27-claim` | `7c87b1a46226924da3a5428041c2154fd78c358a` | `docs/ws27-target-task-claim-20261023` | 0 | DEFERRED historical/claim/scratch head; current source inclusion not established |
| `current-request-arrival` | `4b73fedb4259a2854e326255708ae5ff7c6ce967` | `codex/ws17-current-request-arrival-20261018` | 0 | ALREADY IN MAIN by ancestry |
| `arrival-claim` | `d8fd399b021d63c7f2366837ddf1190fc34c96d6` | `docs/ws17-arrival-claim-20261018` | 0 | ALREADY IN MAIN by ancestry |
| `acceptance-work` | `b29c7aba431eb1c9de6a0aa092128a8ce133119d` | `acceptance-inspection-base` | 0 | ALREADY IN MAIN by ancestry |
| `ws17-verification` | `dfa9c4e4e29cbeace30df2f7ba68309d89196eda` | `codex/ws17-release-verification-20261018` | 0 | ALREADY IN MAIN by ancestry |
| `acceptance-selective-verification-20261021` | `e74e4b8e66916bb0de64c76a62333e6e4971e90f` | `(detached)` | 0 | DEFERRED historical/claim/scratch head; current source inclusion not established |
| `acceptance-repair` | `331d62ee79625889d00376c547c459c2be09cbd4` | `codex/ws17-restoration-diagnostics-20261022` | 0 | ALREADY IN MAIN by ancestry |
| `acceptance-review` | `bffac3ab1097eb0b48e9013d4e23e873e675412e` | `docs/acceptance-claims-20261018` | 0 | ALREADY IN MAIN by ancestry |
| `arrival-baseline` | `c24496325c8c587c38c485e889db87f28fd14f7b` | `(detached)` | 0 | ALREADY IN MAIN by ancestry |
| `cleanup-repair` | `1632afb726ae2fb4df25c6349647f2e731a29766` | `codex/sandbox-cleanup-repair-20261018` | 0 | ALREADY IN MAIN by ancestry |

Additional registered owner worktrees were inspected read-only:

| Checkout | Head | Dirty paths | Disposition |
|---|---|---|---|
| `cc7a2-wt` | `16c98fef75c3075f6dea61901070c0ee6620a650` | 0 | already main by ancestry |
| `cc7a2b-wt` | `25c522949e2cb5a3874352d5d385bdd0667c6949` | 0 | already main by ancestry |
| `claude-1022-docs-wt` | `9bf0b01719a9bc301b8605ea289cb91b8c5aa757` | 0 | already main by ancestry |
| `roadmap-sync-wt` | `011fdb99021be991c078ec01e0714d24c4834e07` | 0 | historical owner checkout; no source imported without current provenance |
| `ws05-harness-matrix-wt` | `a568f7dc282fff7436a4527feb7d162a2b021c81` | 0 | historical owner checkout; no source imported without current provenance |
| `ws13-p1-followup-wt` | `09150adbbb5a804315a93f8b0b7c344f69c08627` | 0 | already main by ancestry |
| `ws13-p1-pf3-wt` | `e3a4b3db78f3eb896adb09dbfff9b20ea4484e4f` | 0 | already main by ancestry |
| `ws13-plan-wt` | `c435ffe1a5695c1d6cf99d9dadde83d32a036c16` | 0 | already main by ancestry |
| `ws17-dispatch-wt` | `d468bc06d528906b28ea9e5553d0deab566552e8` | 0 | already main by ancestry |
| `ws21-wt` | `bb9cf353d56a010c9dd0cf5774a137085a03dd17` | 0 | already main by ancestry |

## Verification and remaining gates

- Existing focused checker/plan-manifest/reader/event tests plus both imported
  suites: **100 passed, 186 subtests**, Python 3.12, no live mode or added
  dependencies. WS-30's green author harness is not independent oracle approval.
- Final local strict roadmap checks against origin/main and HEAD: **0 errors,
  0 warnings**. Preservation audit passed all 32 IDs and every Owner/Scope/Status
  and checkbox; WS-23 exact source and both WS-30 snapshot/original hashes match.
  Original 35 vectors, six mutations and three probes remain unchanged.
  Whitespace and explicit 13-file scope/secret-marker scans passed. Final-head CI
  remains separate; full runtime/native/VM/live acceptance is not claimed. No model invocation, installation, service restart
  or access/credential change is authorized or performed.
- Independent review of the complete aggregate, renewed WS-30 oracle review,
  WS-23 exact-source review and applicable final-head CI remain merge gates.
  This PR is **draft / not ready to merge**; Larry requested publication only.
- Deferred historical refs require owner/current-scope reconciliation, not a
  blanket replay. Missing WS-03/05/31 implementation is not authored here.
- Coordination requests previously posted during #275/#277 are historical PR
  handoffs. A later specific WS-05 scope-lock comment was blocked by approval
  review and was not posted; no acknowledgement is invented. This manifest is
  the new draft's repository handoff and preserves all original owner scopes.
