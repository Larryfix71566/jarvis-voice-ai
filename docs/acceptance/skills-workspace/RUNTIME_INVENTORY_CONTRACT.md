# Skills runtime inventory contract

The voice process owns its live MCP `SkillRegistry`; the admin sidecar cannot
infer that registry's contents from static manifests. Each voice session sends
the admin sidecar a content-free inventory over the existing
`JARVIS_SERVICE_TOKEN` bearer channel at `POST /api/skills/runtime-inventory`.
The endpoint accepts only the token named `service-bot`.

Version 1 carries `runtime_id` (UUID), `active`, `complete`, and at most 256
discovered MCP tool names. Extra fields, duplicate/invalid names, oversized
inventories, and unsupported schema versions are refused. The sidecar retains
receipts in memory for at most 45 seconds. The bot refreshes every 10 seconds
and sends an inactive receipt during orderly shutdown. If any active session
has an incomplete inventory, readiness treats runtime tool evidence as unknown;
otherwise required tools must exist in every fresh session.

This receipt proves only that a tool was discovered in a live registry. It does
not prove successful invocation, package revision loading, provider access,
credential validity, model-route compatibility, privacy compatibility, or
sandbox availability. Those remain independent readiness evidence. Missing,
stale, or incomplete receipts remain unknown. The report is best-effort and
never delays voice startup, dispatches a tool, starts a provider, or includes
secret values, prompts, results, or transcripts.
