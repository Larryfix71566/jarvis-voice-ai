# Sharing acceptance

Text and image inputs are normalized locally with bounded quotas, allowlisted
MIME types, SHA-256 digests, and ephemeral storage. Approval and provider
disclosure are required before transfer. Clipboard content is excluded from
ordinary result exports.

- [x] Python normalization, quota, digest, versioned-envelope, and
  explicit-approval tests.
- [x] Swift transfer and session-lifetime privacy-latch tests.
- [x] Sandbox accept/ack pacing uses a server-issued transfer ID, one
  outstanding chunk, bounded acknowledgement waits, and explicit cancel.
- [x] Immutable preview, actual-write reporting, and cancellation tests.
- [x] Command Console exposes paste, choose and bounded native drop entry
  points before any item is staged; all paths use the same normalizer and
  approval gate.
- [x] Voice approval offers decode through JarvisKit, are session/generation
  checked, and surface explicit Send/Cancel controls that reuse the bounded
  manifest/chunk transfer.
- [ ] Mac exercise of paste/drop/choose and the system share picker.
- [ ] Provider upload, cancel, reconnect, and ephemeral cleanup journey.
