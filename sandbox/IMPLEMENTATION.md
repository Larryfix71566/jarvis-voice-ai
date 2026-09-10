# Sandbox implementation ledger

This ledger tracks the complete development sandbox. A working VM alone does
not complete the feature. The self-edit and app-building adapters now use VM sessions. The remaining
workflow, preview, provider and lifecycle requirements below still apply.

## Implemented and exercised

- Disposable macOS VM controller, one active VM, CPU/memory limits, read-only
  source input, no shared credentials/clipboard/audio, offline development.
- Explicit host/private-network blocks during dependency provisioning;
  independent canaries for host files, share writes, gateway, metadata and
  public/IPv6 access. See `VALIDATION.md` for the actual machine results.
- Python, Node, Swift/Xcode and Playwright preparation; backend, knowledge-base,
  web and native test/build commands; four service previews and browser smoke.
- Bounded guest file service for reads, writes and complete candidate capture.
  Host checks paths (including macOS collisions), modes, links, sizes, content
  and changed-path policy. Capture does not trust guest Git or `.gitignore`.
- Host-owned edit journal and candidate objects. Candidate fingerprints include
  every path, mode and content hash. A write invalidates earlier verification
  before contacting the VM, including when the response is lost.
- Durable host records, bounded captured output, and immutable service versions
  to avoid stale file handles when upgrading a running VM's read-only share.

- Reusable prepared templates, immutable dependency compatibility checks,
  fresh candidate hydration and independent verification VMs. Host-selected
  checks include protected baseline tests and separate native compiler output.
- Unprivileged guest workers, protected dependency code, synthetic native test
  Keychains, disabled shell startup files, and bounded flush-before-stop.
- Persistent shared sessions and host-only source caches. A setup interruption
  remains attached to its session, and cancellation covers verification children.
- Background cold resume with explicit file-request retry, saved app selection,
  and recovered publication links. Fresh controller instances reconcile actual
  VM state before trusting readiness. Interrupted verification cancels its
  abandoned child and clears the previous approval before resuming edits.
- Candidate-bound publication receipts and resumable GitHub object/branch/draft
  PR creation. Actual lost-response recovery and cleanup passed; CI recognizes
  the new sandbox self-edit branch prefix.

## Still required for the complete feature

1. **Agent integration:** complete bounded responses for failures during an
   already-ready file operation and for slow cancellation/cleanup. Initial
   authoring setup and cold resume now return promptly with an opening job;
   cold file requests require an explicit retry and never queue an unseen edit.
   App selection and saved publication results survive a host process restart.
   Close alternative direct-write paths as well. `SelfEditService` and `AppWorkspace`
   now route through persistent VM sessions; their cancellation endpoints stop
   running VM work, including finish-job verification. The controller is denied
   by the installed self-edit policy. `mcp_repo.repo_commit_write`,
   `mcp_apps.app_write_file`, initial app scaffolding and direct Git publication
   still need integration or an explicit, enforced non-development boundary.
   Those paths mean the complete application is not yet sandbox-only.
2. **Development profiles:** complete Mortimer and new-web-app profiles with
   runtimes, dependencies, startup/health checks, migrations, synthetic seeds,
   required checks, previews and starter templates. Unsupported platforms must
   identify the additional worker they require.
3. **Full-stack simulation:** deterministic AI, STT, TTS, search and external
   tool fakes; recorded audio; voice connection/interruption/reconnection,
   provider errors, duplicate/cancelled tools, memory extraction, costs,
   optional wake-word and backup/restore flows.
4. **Controlled live integrations:** host vault access through a scoped broker,
   explicit operation/domain policies, request/runtime/API-spend limits, and
   no provider credentials in the guest. Provisioning egress must narrow from
   public-internet access to the approved dependency/documentation policy.
5. **Preview and native acceptance:** authenticated task previews, guest desktop,
   logs/screenshots and a clear development indicator. Exercise native GUI
   journeys and representative self-edit/new-app workflows. Physical audio and
   device permissions need their own evidence where a change requires them.
6. **Lifecycle and release:** idle cleanup, retention/storage quotas, checkpoints,
   task crash recovery, archived evidence, approved deployment and rollback,
   including database backup/migration/restore. Exercise adversarial package
   and test code, resource exhaustion, and recovery rather than relying only
   on mocked tests.

## Current file-service acceptance

On the existing prepared offline VM (`231703e2d031`), the new service read and
edited a documentation file, collected the complete candidate twice, reopened
the saved candidate, and restored the original source. Only the intended path
changed. Baseline fingerprint:
`effe54c6edde0e163c866a84265a3c1dc1b75be6ffc3ed56f298fa5997785796`.
Edited candidate fingerprint:
`2032906c9fc8abe095f55cd3eda85e2685fba999d5e384d47145c816b6a5f086`.

This is file-transport acceptance, not an independent verification receipt and
not permission to publish or deploy that synthetic candidate. No production
checkout was edited, and the canary was removed from the VM.

An intentional one-second timeout of a 30-second guest sleep also exercised
the bounded-response path. The VM stopped, and its saved state matched Tart's
independently queried state. Forty sandbox regression tests and eight existing
allowlist/CI policy tests pass locally.

## Shared-session acceptance

The complete shared-session flow passed with source revision
`beeeaeec34f121801a59016aeaa28f755c81df06`: host-only bare source fetch,
fresh development VM, edit, fresh independent verification, saved-session
reopening, draft publication, simulated lost-response recovery, and cleanup.
All 12 required checks passed. Both backend runs passed 2,396 tests; both
candidate and baseline native runs passed 96 library and 39 app tests.

The temporary draft [PR 57](https://github.com/Larryfix71566/jarvis-voice-ai/pull/57)
was closed without merging. Its branch and disposable VMs were deleted, with
receipts and logs retained. No live checkout or deployment was changed.
The [acceptance record](acceptance/2026-09-10-session.json) records exact
candidate, source, image, runner and log identifiers. This completes the shared
session building block; it does not complete the remaining scope above.

## Resume and reconnect acceptance

An actual proposed edit survived a stopped development VM and a fresh host
controller. A stale saved running state was also reconciled against Tart.
Controlled interruption of verification stopped its running child VM, refused
that child's restart, cleared the injected old approval and check result, and
reopened the edited workspace. Both disposable VMs were deleted afterward.

The affected application/API selection passed 303 tests inside the VM; a later
publication-status selection passed 87. The trusted controller suite passed
101 tests. These are separate, overlapping runs. Exact source and log identifiers,
plus the controlled failure-injection limits, are recorded in
[the resume acceptance record](acceptance/2026-09-10-resume.json).
