# Subscription probe receipt

**Date:** 2026-09-20 20:15 America/New_York  
**Data:** synthetic prompts only; no repository content or user data.

## Codex

- Installed CLI: `codex-cli 0.155.0-alpha.2.6`
- Command policy: `exec --json --ephemeral --skip-git-repo-check --sandbox read-only`
- Default authenticated model: returned `SUBSCRIPTION_PROBE_OK`.
- Mortimer adapter: returned `ADAPTER_PROBE_OK`.
- Explicit `gpt-5.1-codex-max`: rejected by the ChatGPT account as unsupported.
- Action: added the separate `codex-subscription` profile using the verified
  account default (`gpt-6-astra`); the existing OpenRouter profile remains
  unchanged.

## Claude

- Installed CLI: Claude Code `2.1.252`.
- Command policy: non-persistent print mode with common shell/file/web/
  delegation tools denied.
- Result: CLI reports `Not logged in`; no OAuth session is currently
  available in the Mac keychain/runtime.
- Action: adapter no longer uses `--bare`, so re-authentication can use the
  official OAuth/keychain path. The route remains disabled until re-auth and
  a repeat probe succeeds.
