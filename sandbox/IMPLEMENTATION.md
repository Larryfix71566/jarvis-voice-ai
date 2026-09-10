# Sandbox implementation ledger

This ledger tracks the complete development sandbox. A working VM alone does
not complete the feature. The production self-edit and app-building services
still use their previous workspaces until the integration below is complete.

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

## Still required for the complete feature

1. **Agent integration:** shared persistent sessions for `SelfEditService` and
   `AppWorkspace`; all candidate reads/edits/commands inside VMs, no host
   execution fallback, restart/reconnect and cancellation through the same
   task identity. Protect the installed sandbox controller from self-edit.
2. **Independent verification:** reusable prepared images, dependency/profile
   compatibility checks, fresh candidate hydration, and verification in a
   separate disposable VM. Host-selected required checks and receipts must
   bind the frozen candidate, image, profile and runner version. Later changes
   must invalidate publication eligibility.
3. **Publication and recovery:** host-only GitHub credentials, strict candidate
   acceptance, resumable commit/branch/PR creation, duplicate avoidance and
   recovery after lost responses. No guest-provided commands or Git hooks on
   the host. Deployment remains a separately approved operation.
4. **Development profiles:** complete Mortimer and new-web-app profiles with
   runtimes, dependencies, startup/health checks, migrations, synthetic seeds,
   required checks, previews and starter templates. Unsupported platforms must
   identify the additional worker they require.
5. **Full-stack simulation:** deterministic AI, STT, TTS, search and external
   tool fakes; recorded audio; voice connection/interruption/reconnection,
   provider errors, duplicate/cancelled tools, memory extraction, costs,
   optional wake-word and backup/restore flows.
6. **Controlled live integrations:** host vault access through a scoped broker,
   explicit operation/domain policies, request/runtime/API-spend limits, and
   no provider credentials in the guest. Provisioning egress must narrow from
   public-internet access to the approved dependency/documentation policy.
7. **Preview and native acceptance:** authenticated task previews, guest desktop,
   logs/screenshots and a clear development indicator. Exercise native GUI
   journeys and representative self-edit/new-app workflows. Physical audio and
   device permissions need their own evidence where a change requires them.
8. **Lifecycle and release:** idle cleanup, retention/storage quotas, checkpoints,
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
