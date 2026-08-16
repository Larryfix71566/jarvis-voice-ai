# Credential Vault Acceptance Checklist

Manual acceptance for MORTIMER_CREDENTIAL_VAULT_PLAN.md. Run on the real
machine (the Keychain path can't be exercised in CI). **Back up `.env`
somewhere safe before starting** (then delete the backup after — the
plan's whole point).

## Init + migrate

- [ ] `python -m jarvis.vault init` — creates `data/secrets.vault`,
      reports storing a key in the keychain. Confirm in Keychain Access:
      service `mortimer`, account `vault-key`.
- [ ] `python -m jarvis.vault migrate` — every API key/token line in
      `.env` becomes a `# NAME moved to vault ...` comment; config lines
      (ports, timezone, base URLs) are untouched; the summary lists each
      migrated name.
- [ ] `python -m jarvis.vault status` — reports present/decryptable with
      the right count. `list` shows names only, never values.
- [ ] `cat data/secrets.vault` — unreadable ciphertext JSON, no
      plaintext key material. `ls -l` shows `-rw-------` (0600).
- [ ] `git status` — `data/secrets.vault` does NOT appear (gitignored).

## The stack runs on vault secrets alone

- [ ] In a FRESH terminal that has NOT sourced `.env`:
      `python scripts/check_env.py` passes its required-vars check —
      proof the vault injection alone supplies the keys (plan §5 step 7).
- [ ] `./scripts/mortimer.sh` — bot, admin sidecar, and web console all
      start and function normally (speech round-trip, one delegation,
      Edit panel loads models).
- [ ] A self-edit run still works (planner keys come from the vault via
      the sidecar's import-time injection).

## Precedence

- [ ] `OPENAI_API_KEY=sk-wrong python scripts/check_env.py` — the LLM
      check FAILS with the wrong key: a non-empty env var beats the
      vault (the override channel works).

## Failure modes (S6)

- [ ] Temporarily rename the keychain entry (or run with
      `JARVIS_VAULT_KEY=bogus`): starting the bot fails LOUDLY with a
      remediation message — it does not run half-configured. Restore.
- [ ] `JARVIS_VAULT_ENABLED=false ./scripts/run_bot.sh` with the vault
      present and `.env` lines still commented: bot fails on missing
      keys (expected — kill switch means "pretend the vault doesn't
      exist"). Uncommenting `.env` lines restores pre-vault behavior
      exactly (the §6 rollback path).

## Portability

- [ ] `python -m jarvis.vault export-key` prints a base64 key (with a
      stderr warning). On a second machine (or a temp dir with
      `JARVIS_VAULT_PATH`), `JARVIS_VAULT_KEY=<that key>` +
      the copied vault file decrypts (`status` says yes).
- [ ] `python -m jarvis.vault rotate-key` — secrets preserved, `status`
      still decrypts, and the OLD exported key no longer works.

## Boundaries

- [ ] Ask Mortimer (voice or console) to read `data/secrets.vault` or
      `.env` via the Developer agent: refused by `mcp_repo`'s deny list.
- [ ] Confirm the Edit panel offers no vault UI and
      `http://127.0.0.1:7861` exposes no `/api/vault*` route.

## Suite

- [ ] `pytest tests/unit tests/integration -q` green.
- [ ] With a REAL vault present on this machine, the suite still passes
      and no real secret value appears in any test output (conftest
      isolation).
