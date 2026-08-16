# MORTIMER CREDENTIAL VAULT — implementation plan

**Problem.** Every credential Mortimer uses — LLM/speech API keys, two
GitHub tokens, and (soon) OAuth tokens for integrations like Gmail —
lives in plaintext in `.env`. The file is chmod-default, readable by any
process running as the user, easy to leak into a backup or a paste, and
its history in this repo already includes one near-miss (see
`.gitignore`'s own comment about a `.env.bak` that reached a commit).
Future integrations make it worse: OAuth refresh tokens are
*written back* at runtime, which `.env` was never meant for.

**Chosen approach (Larry, 2026-08-16): option B** — an encrypted local
vault file, AES-256-GCM, with the master key stored in the macOS
Keychain (only the key lives in Keychain; the secrets live in the
file). Chosen over pure-Keychain storage for portability: the vault
file can be backed up or moved to another machine and unlocked there by
exporting the key once.

**Ground rule (same as every plan in this repo):** every decision below
has already been made. Implement it exactly as written; if something is
genuinely undecided, that is a defect in this document — stop and
report it rather than choosing.

---

## §1 Non-goals (read first)

- **No secrets in the browser or the LLM.** The console gets no vault
  panel; the admin sidecar gets no vault endpoints; no MCP tool reads
  or writes vault contents. Management is CLI-only
  (`python -m jarvis.vault`). A voice agent that can recite your API
  keys is a bug, not a feature.
- **No passphrase mode.** The master key is random bytes in Keychain
  (or `JARVIS_VAULT_KEY` for tests/CI/headless). No KDF, no passphrase
  prompt — your macOS login is the unlock.
- **No secrets server, no cloud.** Local-first, like everything else.
- **`.env` survives** for non-secret configuration (ports, timezone,
  feature flags, model names). Only credentials move.

---

## §2 Decisions

### S1 — File format and crypto

`data/secrets.vault` — a JSON envelope:

```json
{"version": 1, "nonce": "<b64 12 bytes>", "ciphertext": "<b64>"}
```

Ciphertext is AES-256-GCM (`cryptography.hazmat.primitives.ciphers.aead.
AESGCM`) over the UTF-8 JSON plaintext `{"secrets": {"NAME": "value",
...}}`, with `b"mortimer-vault-v1"` as GCM associated data. A fresh
random nonce is generated on every write. GCM authentication failure
(tampered or wrong-key file) raises a clear
`VaultError("vault authentication failed — wrong key or corrupted
file")` — never a silent fallback to `.env`, because a *present but
unreadable* vault is an incident, not a missing feature (contrast S6).
File is written atomically (`tempfile` in the same directory +
`os.replace`) with mode `0600`; writes take an `fcntl.flock` on
`data/secrets.vault.lock` around the read-modify-write so the CLI and a
future integration writing a refreshed OAuth token cannot interleave.
Readers do not lock (atomic replace guarantees they see a complete
envelope).

### S2 — Master key resolution, in this exact order

1. `JARVIS_VAULT_KEY` env var (base64 of 32 bytes) — for tests, CI, or
   a headless Linux box. If set but malformed: `VaultError`, not a
   fallthrough.
2. macOS Keychain via the `keyring` library: service `"mortimer"`,
   account `"vault-key"`, value base64 of 32 bytes. `keyring` errors
   (locked keychain, missing backend) surface as `VaultError` with the
   remediation in the message (`security unlock-keychain`, or set
   `JARVIS_VAULT_KEY`).

`python -m jarvis.vault init` generates the key, stores it in Keychain,
and creates an empty vault. `export-key` prints the base64 key to
stdout (with a stderr warning) for moving to another machine;
`rotate-key` generates a new key, re-encrypts, and replaces the
Keychain entry.

### S3 — One module, one resolution point: `jarvis/vault.py`

New module (NOT under `jarvis/skills/` — that subtree is on the
self-edit allowlist; see S8). Public surface:

```python
class VaultError(RuntimeError): ...
def vault_path() -> Path                     # data/secrets.vault (JARVIS_VAULT_PATH overrides, for tests)
def is_enabled() -> bool                     # JARVIS_VAULT_ENABLED, default true
def load_secrets() -> dict[str, str]         # {} if vault file absent
def get_secret(name: str) -> str | None
def set_secret(name: str, value: str) -> None   # the OAuth write-back path
def delete_secret(name: str) -> None
def inject_env() -> int                      # see S4; returns count injected
```

`jarvis/vault.py` imports nothing from `jarvis.*` (it is below
`jarvis.config` in the dependency order and must stay import-light).

### S4 — `inject_env()`: the environment stays the transport

Nothing downstream changes how it reads credentials — pydantic
`Settings`, `expand_env_vars` in `jarvis/skills/registry.py` (which
populates MCP child-process env), and `jarvis/agents/upgrade_agent.py`'s
direct `os.environ` reads all keep working untouched, because
`inject_env()` copies every vault secret into `os.environ` **before**
any of them look. Rules:

- A name is injected only when it is **missing from `os.environ` or
  present with an empty-string value**. The empty-string clause is
  load-bearing: the run scripts do `set -a; . ./.env; set +a`, and a
  migrated `.env` line commented out still leaves *older shells* or
  partial edits exporting `NAME=` as `""` — an empty env var must lose
  to the vault. A non-empty env var always wins (deliberate override
  channel for CI and experiments).
- If `is_enabled()` is false or the vault file does not exist:
  inject nothing, return 0, log one INFO line. Pre-migration and
  post-`JARVIS_VAULT_ENABLED=false` behavior is therefore *exactly*
  today's behavior — this is the kill switch, enforced only here.
- A present-but-undecryptable vault raises (S1); startup fails loudly
  with the remediation message rather than running with silently
  missing keys.

Call sites — exactly three, no more:

1. Top of `load_settings()` in `jarvis/config.py`, before `Settings`
   is constructed (covers bot, CLI, and anything else that loads
   settings; the registry spawns MCP servers after this point, so
   child env inherits the injected values).
2. Module top of `jarvis/admin/server.py` (the sidecar never calls
   `load_settings`; `UpgradeAgent` reads planner keys from
   `os.environ` directly).
3. `scripts/check_env.py`, wrapped in `try: from jarvis.vault import
   inject_env … except ImportError: pass` — that script is documented
   stdlib-only-before-deps and must keep working in a fresh checkout.

### S5 — What migrates: names, not guesses

`python -m jarvis.vault migrate` moves values from `.env` into the
vault for exactly this list plus pattern:

- Explicit: `OPENAI_API_KEY`, `DEEPGRAM_API_KEY`, `ELEVENLABS_API_KEY`,
  `TAVILY_API_KEY`, `GITHUB_TOKEN`, `MOONSHOT_API_KEY`,
  `ANTHROPIC_API_KEY`, `JARVIS_GITHUB_TOKEN`
- Pattern (future-proofing, applied to any other `.env` name):
  `*_API_KEY`, `*_TOKEN`, `*_SECRET`, `*_PASSWORD`

For each migrated name the `.env` line is rewritten as a comment —
`# OPENAI_API_KEY moved to vault (python -m jarvis.vault) 2026-08-16` —
NOT left as a blank `NAME=` (a blank line would export `""`; S4 defends
against that anyway, but don't create the hazard). Non-matching lines
are byte-for-byte untouched. The command prints a summary and reminds
the user to also delete any `.env` backups. Migration is idempotent:
already-migrated names are skipped.

### S6 — Missing-vault vs broken-vault, stated once

| State | Behavior |
|---|---|
| Vault file absent | Silent fallback to `.env`/env (INFO log) — fresh checkouts and pre-migration setups work unchanged |
| `JARVIS_VAULT_ENABLED=false` | Same as absent — kill switch |
| Vault present, key unavailable | **Hard error** with remediation — never run half-configured |
| Vault present, GCM auth fails | **Hard error** — tampering/corruption is an incident |

### S7 — CLI: `python -m jarvis.vault`

Subcommands: `init`, `status` (exists? decryptable? how many names —
never values), `list` (names only), `set NAME` (value via hidden
`getpass` prompt — never argv, never shell history; an empty or
whitespace-only value is rejected with an error, because S4 treats
empty as "unset" and an empty vault entry would be unreachable by
design), `get NAME`
(prints the value; intended for scripting, warns on TTY), `rm NAME`,
`migrate` (S5), `export-key`, `rotate-key` (S2). Same argparse
structure as `jarvis/runlog/cli.py` — copy that file's shape.

### S8 — The agent can never touch its own credential machinery

- `config/self_edit_allowlist.json` deny list gains: `jarvis/vault.py`,
  `data/**`, `*.vault`. (`jarvis/vault.py` is already outside every
  allow glob; the explicit entries are belt-and-braces, same discipline
  as `config/upgrade_models.yaml`.)
- `mcp_servers/mcp_repo/logic.py`: the `data` segment is *already* in
  `DENY_SEGMENTS` (read-denied); add `"*.vault"` to `DENY_FILE_GLOBS`
  so a vault file misplaced outside `data/` is still unreadable.
- `.gitignore` gains `*.vault` (belt-and-braces beside the existing
  `data/` coverage of DB files; the same backup-file lesson in that
  file's header comment applies here).
- No MCP server, no admin endpoint, no prompt ever exposes
  `jarvis.vault` — enforced by S1's Non-goals and checked in review,
  not by code.

### S9 — Dependencies

`cryptography` and `keyring` are appended to `requirements.txt`, and
`requirements-lock.txt` is regenerated (`uv pip compile` or the
project's existing freeze flow). Both are pure-Python-API,
well-maintained, and already transitively common; no alternatives
clause — if either cannot be installed, stop and report.

### S10 — Settings and docs stay honest

- `jarvis/config.py`: no new Settings field for the vault path/enabled
  flag (the module cannot depend on Settings — S3 import order); the
  two env vars are documented in `.env.example` instead, alongside a
  rewritten header explaining that credentials now live in the vault
  and `.env` holds configuration.
- `CLAUDE.md`: Commands section gains the `python -m jarvis.vault`
  block; Architecture gains a short **Credential vault** paragraph
  (boundaries: env-injection design, kill switch, CLI-only management,
  deny-list rule).
- `README` setup section: `python -m jarvis.vault init && python -m
  jarvis.vault migrate` inserted after `cp .env.example .env`.

---

## §3 Files

**New:**
- `jarvis/vault.py` — S1–S4, S6
- `jarvis/vault_cli.py` + `jarvis/vault.py`'s `__main__` hookup — no;
  **decision:** the CLI lives in `jarvis/vault.py`'s own
  `if __name__ == "__main__"` via a `main()` function and a
  `python -m jarvis.vault` entry (single file; it is small)
- `tests/unit/test_vault.py`
- `tests/acceptance/credential-vault.md`

**Modified:**
- `jarvis/config.py` — `inject_env()` call at top of `load_settings()`
- `jarvis/admin/server.py` — `inject_env()` at module top
- `scripts/check_env.py` — guarded `inject_env()` (S4.3)
- `config/self_edit_allowlist.json`, `mcp_servers/mcp_repo/logic.py`,
  `.gitignore` — S8
- `requirements.txt`, `requirements-lock.txt` — S9
- `.env.example`, `CLAUDE.md`, `README` — S10

---

## §4 Tests (tests/unit/test_vault.py — all with `JARVIS_VAULT_KEY` set and `JARVIS_VAULT_PATH` pointed at tmp_path; keyring is never touched by tests)

| Decision | Test |
|---|---|
| S1 | set/get/delete roundtrip survives process-independent reload |
| S1 | flipping one ciphertext byte → `VaultError`, message mentions corruption |
| S1 | vault file mode is 0600 after write |
| S2 | malformed `JARVIS_VAULT_KEY` → `VaultError`, no keyring fallthrough |
| S4 | `inject_env()` sets missing names; leaves non-empty env values alone; **replaces empty-string env values** |
| S4/S6 | absent vault file → returns 0, no error; `JARVIS_VAULT_ENABLED=false` → returns 0 even with vault present |
| S6 | present vault + missing key → raises (does not fall back) |
| S5 | migrate on a fixture `.env`: matched names land in vault, lines become comments, unmatched lines byte-identical, second run is a no-op |
| S7 | `set` via prompted input (monkeypatched getpass); `list` shows names not values |

Integration: one test in `tests/integration/` asserting that a spawned
MCP server (via `SkillRegistry`) sees a vault-injected variable through
`config/mcp_servers.yaml` `${VAR}` expansion.

---

## §5 Implementation order

1. `jarvis/vault.py` core (S1–S3, S6) + unit tests for crypto/precedence.
2. `inject_env` + its three call sites (S4) + tests.
3. CLI subcommands (S7) + tests; `migrate` (S5) last of these.
4. Deny-list/gitignore hardening (S8).
5. Dependencies + lockfile (S9).
6. Docs (S10) + acceptance checklist.
7. Full suite + `scripts/check_env.py` in a shell that has NOT sourced
   `.env` (proves vault injection alone satisfies the required-vars
   check post-migration).

---

## §6 Rollback

`JARVIS_VAULT_ENABLED=false` restores pre-vault behavior at the single
S4 enforcement point — provided `.env` still holds the values, which is
why `migrate` comments lines out rather than deleting them (uncomment
to fully revert). `rotate-key`/`export-key` make the Keychain entry
recoverable. No schema, no migration, no API change.

---

## §7 Risks

| Risk | Level | Mitigation |
|---|---|---|
| Keychain locked/absent in some launch context (LaunchAgent, SSH) | Medium | `JARVIS_VAULT_KEY` env path (S2.1) is the documented escape hatch; error messages name it |
| A blank `NAME=` in someone's stale `.env` shadows the vault | Medium | S4's empty-string-loses rule; migrate comments lines out (S5) |
| Future integration writes token while CLI writes another name | Low | flock around read-modify-write (S1) |
| Dependency surface (`cryptography`, `keyring`) | Low | Both mainstream; pinned via the lockfile |
| Agent gains a path to read the vault | Low | S8 triple coverage (allowlist deny, mcp_repo deny, no endpoint/tool by S1 Non-goals) |

---

## §8 Approval

**Implementation status (2026-08-16): implemented, §5 steps 1–7
complete.** S1–S10 all done; full suite green (850 passed, 3 skipped, 1
live-only test deselected); import smoke clean; a live end-to-end
init→migrate→status cycle verified against a scratch .env (line
commented out, vault 0600, decryptable). One rendering adaptation of
S6, documented inline at the call site: `scripts/check_env.py` reports
a broken vault as a `[FAIL]` line + exit 1 (its documented PASS/FAIL
contract) rather than an uncaught traceback — same hard stop, the
validator's format. Two additions beyond the plan's letter, both
test-infrastructure: `tests/conftest.py` isolates every test from a
real `data/secrets.vault` at conftest-import time (module-level, since
`jarvis/admin/server.py` injects at import; exempted under RUN_LIVE=1,
whose tests legitimately need the real credentials), and
`tests/integration/test_vault_registry.py` proves the vault→env→MCP-
child plumbing end-to-end. `tests/acceptance/credential-vault.md`
remains for the human pass — the Keychain path (`init` storing the key,
`export-key`/`rotate-key` against the real keychain) cannot be
exercised in CI and still needs a run on the actual machine, as does
the real `.env` migration.

- [ ] Larry has read §1–§2 and approves.
- [ ] Implementation may begin.
