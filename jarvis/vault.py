"""Credential vault (MORTIMER_CREDENTIAL_VAULT_PLAN.md).

Encrypted local secrets file — AES-256-GCM over a JSON payload, master
key in the macOS Keychain (or JARVIS_VAULT_KEY for tests/CI/headless).
The environment stays the transport: `inject_env()` copies vault
secrets into os.environ at exactly three call sites (S4), so pydantic
Settings, the MCP registry's ${VAR} expansion, and the upgrade agent's
direct os.environ reads all work unchanged and never know the vault
exists.

Boundaries (plan §1, non-negotiable):
- No console panel, no admin endpoint, no MCP tool touches this module.
  Management is CLI-only: `python -m jarvis.vault`.
- This module imports nothing from jarvis.* — it sits below
  jarvis.config in the dependency order and must stay import-light.
- Missing vault file == silent fallback to .env (pre-migration setups
  work unchanged). Present-but-unreadable vault == hard error (S6):
  a vault you HAVE but cannot open is an incident, not a missing
  feature.

Kill switch: JARVIS_VAULT_ENABLED=false (read here and only here, same
env-first pattern as jarvis/council/council.py's kill switch).
"""

from __future__ import annotations

import argparse
import base64
import fcntl
import getpass
import json
import logging
import os
import sys
import tempfile
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

import keyring
import keyring.errors

logger = logging.getLogger(__name__)

# --- constants (S1/S2) ---------------------------------------------------

VAULT_VERSION = 1
AAD = b"mortimer-vault-v1"
KEY_ENV = "JARVIS_VAULT_KEY"
PATH_ENV = "JARVIS_VAULT_PATH"
ENABLED_ENV = "JARVIS_VAULT_ENABLED"
KEYRING_SERVICE = "mortimer"
KEYRING_ACCOUNT = "vault-key"
DEFAULT_PATH = Path("data") / "secrets.vault"

# S5 — what `migrate` moves out of .env: this explicit list plus the
# name patterns below. Names, not guesses.
MIGRATE_NAMES = frozenset({
    "OPENAI_API_KEY", "DEEPGRAM_API_KEY", "ELEVENLABS_API_KEY",
    "TAVILY_API_KEY", "GITHUB_TOKEN", "MOONSHOT_API_KEY",
    "ANTHROPIC_API_KEY", "JARVIS_GITHUB_TOKEN",
    "SAYGM_API_KEY",
})
MIGRATE_SUFFIXES = ("_API_KEY", "_TOKEN", "_SECRET", "_PASSWORD")


class VaultError(RuntimeError):
    """Any vault failure the caller must not silently swallow."""


# --- paths / switches ----------------------------------------------------

def vault_path() -> Path:
    """data/secrets.vault; JARVIS_VAULT_PATH overrides (tests)."""
    override = os.environ.get(PATH_ENV)
    return Path(override) if override else DEFAULT_PATH


def is_enabled() -> bool:
    """JARVIS_VAULT_ENABLED, default true — the kill switch (S6),
    enforced only inside this module."""
    value = os.environ.get(ENABLED_ENV)
    if value is None:
        return True
    return value.strip().lower() not in ("false", "0", "no")


# --- master key resolution (S2) -----------------------------------------

def _decode_key(b64: str, source: str) -> bytes:
    try:
        raw = base64.b64decode(b64.strip(), validate=True)
    except Exception as exc:
        raise VaultError(
            f"vault key from {source} is not valid base64: {exc}"
        ) from exc
    if len(raw) != 32:
        raise VaultError(
            f"vault key from {source} must be 32 bytes (got {len(raw)})"
        )
    return raw


def _load_key() -> bytes:
    """S2's exact order: JARVIS_VAULT_KEY env (malformed = error, not a
    fallthrough), then macOS Keychain via keyring."""
    env_key = os.environ.get(KEY_ENV)
    if env_key:
        return _decode_key(env_key, f"${KEY_ENV}")
    try:
        stored = keyring.get_password(KEYRING_SERVICE, KEYRING_ACCOUNT)
    except keyring.errors.KeyringError as exc:
        raise VaultError(
            "could not read the vault key from the keychain "
            f"({exc}) — unlock it (`security unlock-keychain`) or set "
            f"{KEY_ENV} (base64 of the 32-byte key, see "
            "`python -m jarvis.vault export-key`)"
        ) from exc
    if stored is None:
        raise VaultError(
            "no vault key found — run `python -m jarvis.vault init` "
            f"first, or set {KEY_ENV} if the key lives on another machine"
        )
    return _decode_key(stored, "the keychain")


def _store_key(raw: bytes) -> None:
    try:
        keyring.set_password(
            KEYRING_SERVICE, KEYRING_ACCOUNT,
            base64.b64encode(raw).decode("ascii"),
        )
    except keyring.errors.KeyringError as exc:
        raise VaultError(
            f"could not store the vault key in the keychain: {exc}"
        ) from exc


# --- envelope read/write (S1) -------------------------------------------

def _decrypt(envelope: dict, key: bytes) -> dict[str, str]:
    if envelope.get("version") != VAULT_VERSION:
        raise VaultError(
            f"unsupported vault version {envelope.get('version')!r} "
            f"(this build reads version {VAULT_VERSION})"
        )
    try:
        nonce = base64.b64decode(envelope["nonce"], validate=True)
        ciphertext = base64.b64decode(envelope["ciphertext"], validate=True)
    except Exception as exc:
        raise VaultError(f"vault file is malformed: {exc}") from exc
    try:
        plaintext = AESGCM(key).decrypt(nonce, ciphertext, AAD)
    except InvalidTag as exc:
        raise VaultError(
            "vault authentication failed — wrong key or corrupted file"
        ) from exc
    payload = json.loads(plaintext.decode("utf-8"))
    secrets = payload.get("secrets")
    if not isinstance(secrets, dict):
        raise VaultError("vault payload is malformed: no 'secrets' object")
    return {str(k): str(v) for k, v in secrets.items()}


def _read_envelope(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VaultError(f"could not read vault file {path}: {exc}") from exc


def _write_vault(path: Path, secrets: dict[str, str], key: bytes) -> None:
    """Atomic write (same-dir tempfile + os.replace), mode 0600, fresh
    nonce every time (S1)."""
    nonce = os.urandom(12)
    plaintext = json.dumps({"secrets": secrets}).encode("utf-8")
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, AAD)
    envelope = {
        "version": VAULT_VERSION,
        "nonce": base64.b64encode(nonce).decode("ascii"),
        "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=".vault-tmp-")
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(envelope, fh)
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


class _vault_write_lock:
    """flock on <vault>.lock around read-modify-write (S1) so the CLI
    and a future integration writing a refreshed OAuth token cannot
    interleave. Readers do not lock — atomic replace guarantees they
    see a complete envelope."""

    def __init__(self, path: Path) -> None:
        self._lock_path = path.with_name(path.name + ".lock")
        self._fh = None

    def __enter__(self) -> "_vault_write_lock":
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(self._lock_path, "w")
        fcntl.flock(self._fh.fileno(), fcntl.LOCK_EX)
        return self

    def __exit__(self, *exc_info: object) -> None:
        if self._fh is not None:
            fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
            self._fh.close()
            self._fh = None


# --- public surface (S3) -------------------------------------------------

def load_secrets() -> dict[str, str]:
    """All secrets, decrypted. {} if the vault file is absent (S6's
    silent-fallback row); raises VaultError if present but unreadable."""
    path = vault_path()
    if not path.exists():
        return {}
    return _decrypt(_read_envelope(path), _load_key())


def get_secret(name: str) -> str | None:
    return load_secrets().get(name)


def set_secret(name: str, value: str) -> None:
    """The OAuth write-back path (S3). Empty values are rejected (S7):
    inject_env treats empty as 'unset', so an empty vault entry would
    be unreachable by design."""
    if not name or not name.strip():
        raise VaultError("secret name must be non-empty")
    if not value or not value.strip():
        raise VaultError(
            f"refusing to store an empty value for {name} — "
            "use `rm` to remove a secret"
        )
    path = vault_path()
    key = _load_key()
    with _vault_write_lock(path):
        secrets = _decrypt(_read_envelope(path), key) if path.exists() else {}
        secrets[name] = value
        _write_vault(path, secrets, key)


def delete_secret(name: str) -> None:
    path = vault_path()
    key = _load_key()
    with _vault_write_lock(path):
        secrets = _decrypt(_read_envelope(path), key) if path.exists() else {}
        if name not in secrets:
            raise VaultError(f"no secret named {name} in the vault")
        del secrets[name]
        _write_vault(path, secrets, key)


def inject_env() -> int:
    """Copy vault secrets into os.environ (S4). A name is injected only
    when missing from the environment OR present with an empty-string
    value — the empty-string clause is load-bearing: the run scripts
    `set -a; . ./.env` and a stale blank `NAME=` line exports "" which
    must lose to the vault. A non-empty env var always wins (the
    deliberate override channel for CI and experiments).

    Disabled or vault-absent: inject nothing, return 0 — exactly
    today's pre-vault behavior. Present-but-unreadable: raises (S6)."""
    if not is_enabled():
        logger.info("vault disabled (%s=false) — no secrets injected", ENABLED_ENV)
        return 0
    path = vault_path()
    if not path.exists():
        logger.info("no vault file at %s — using .env/environment as-is", path)
        return 0
    injected = 0
    for name, value in load_secrets().items():
        if os.environ.get(name, "") == "":
            os.environ[name] = value
            injected += 1
    logger.info("vault injected %d secret(s) into the environment", injected)
    return injected


# --- migrate (S5) --------------------------------------------------------

def _is_secret_name(name: str) -> bool:
    return name in MIGRATE_NAMES or any(
        name.endswith(suffix) for suffix in MIGRATE_SUFFIXES
    )


def migrate_env_file(env_path: Path) -> dict[str, list[str]]:
    """Move secret values from .env into the vault; each migrated line
    becomes a comment (NOT a blank `NAME=`, which would export "").
    Non-matching lines are byte-for-byte untouched. Idempotent:
    already-migrated (commented / absent / empty) names are skipped.

    Returns {"migrated": [...], "skipped": [...]}."""
    from datetime import date

    if not env_path.exists():
        raise VaultError(f"no env file at {env_path}")
    key = _load_key()
    path = vault_path()
    migrated: list[str] = []
    skipped: list[str] = []
    out_lines: list[str] = []
    today = date.today().isoformat()

    with _vault_write_lock(path):
        secrets = _decrypt(_read_envelope(path), key) if path.exists() else {}
        for raw_line in env_path.read_text(encoding="utf-8").splitlines(keepends=True):
            line = raw_line.rstrip("\n")
            stripped = line.strip()
            if stripped.startswith("#") or "=" not in stripped:
                out_lines.append(raw_line)
                continue
            name, _, value = stripped.partition("=")
            name = name.strip()
            value = value.strip()
            if not _is_secret_name(name):
                out_lines.append(raw_line)
                continue
            if not value:
                skipped.append(name)
                out_lines.append(raw_line)
                continue
            secrets[name] = value
            migrated.append(name)
            newline = "\n" if raw_line.endswith("\n") else ""
            out_lines.append(
                f"# {name} moved to vault (python -m jarvis.vault) {today}{newline}"
            )
        if migrated:
            _write_vault(path, secrets, key)
            env_path.write_text("".join(out_lines), encoding="utf-8")
    return {"migrated": migrated, "skipped": skipped}


# --- CLI (S7) ------------------------------------------------------------

def _cmd_init(_args: argparse.Namespace) -> int:
    path = vault_path()
    if path.exists():
        print(f"vault already exists at {path} — nothing to do")
        return 0
    if not os.environ.get(KEY_ENV):
        try:
            existing = keyring.get_password(KEYRING_SERVICE, KEYRING_ACCOUNT)
        except keyring.errors.KeyringError as exc:
            print(f"error: keychain unavailable ({exc}); set {KEY_ENV} instead",
                  file=sys.stderr)
            return 1
        if existing is None:
            _store_key(os.urandom(32))
            print("generated a new vault key and stored it in the keychain")
        else:
            print("using the existing vault key from the keychain")
    key = _load_key()
    with _vault_write_lock(path):
        _write_vault(path, {}, key)
    print(f"created empty vault at {path}")
    return 0


def _cmd_status(_args: argparse.Namespace) -> int:
    path = vault_path()
    print(f"vault file : {path} ({'present' if path.exists() else 'absent'})")
    print(f"enabled    : {is_enabled()}")
    if not path.exists():
        return 0
    try:
        secrets = load_secrets()
    except VaultError as exc:
        print(f"decryptable: NO — {exc}")
        return 1
    print(f"decryptable: yes ({len(secrets)} secret(s))")
    return 0


def _cmd_list(_args: argparse.Namespace) -> int:
    for name in sorted(load_secrets()):
        print(name)
    return 0


def _cmd_verify(_args: argparse.Namespace) -> int:
    """MORTIMER_KEY_VALIDITY_PLAN.md K3 — do the stored model credentials
    actually WORK?

    `status` and `list` answer "is it there", which is the same presence
    test every other check in this repo performs and which reported a dead
    ANTHROPIC_API_KEY as fine for as long as it sat in the vault. This is
    the only vault verb that asks the provider.

    Read-only: writes nothing, and prints names, endpoints and verdicts —
    never a value. Deliberately NOT wired into `set`: a probe at write time
    would make storing a key fail when the network is down, and the vault
    must stay usable offline. Verification is a separate act you invoke.

    Reuses scripts/check_env.py's model_key_probe rather than carrying a
    second "is this key good" implementation — the same one-judge rule
    jarvis/toolresult.py applies to tool results.
    """
    import importlib.util

    repo_root = Path(__file__).resolve().parent.parent
    spec = importlib.util.spec_from_file_location(
        "_check_env", repo_root / "scripts" / "check_env.py")
    if spec is None or spec.loader is None:
        print("could not load scripts/check_env.py for the probe")
        return 1
    check_env = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(check_env)

    try:
        import yaml
        registry = yaml.safe_load(
            (repo_root / "config" / "upgrade_models.yaml").read_text(
                encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001
        print(f"could not read the model registry: {exc}")
        return 1

    secrets = load_secrets()
    # Group by (key, endpoint): one credential can legitimately serve two
    # endpoints, and a verdict is only meaningful against the endpoint that
    # produced it.
    groups: dict[tuple[str, str], dict] = {}
    for prof in registry.get("profiles") or []:
        if not isinstance(prof, dict):
            continue
        key_env = str(prof.get("api_key_env", "OPENAI_API_KEY"))
        base = str(prof.get("base_url", ""))
        g = groups.setdefault((key_env, base),
                              {"model": str(prof.get("model", "")), "names": []})
        g["names"].append(str(prof.get("name", "?")))

    if not groups:
        print("no model profiles in the registry")
        return 0

    bad = 0
    for (key_env, base), g in sorted(groups.items()):
        used_by = ", ".join(g["names"])
        if key_env not in secrets:
            print(f"  --  {key_env:22} not in the vault  ({used_by})")
            continue
        outcome, detail = check_env.model_key_probe(
            base, secrets[key_env], g["model"])
        tag = {"ok": "OK  ", "rejected": "DEAD", "unreachable": "??  "}[outcome]
        print(f"  {tag} {key_env:22} {base}")
        print(f"       {detail}")
        print(f"       used by: {used_by}")
        if outcome == "rejected":
            bad += 1
    if bad:
        print(f"\n{bad} credential(s) were REFUSED by their own endpoint. "
              f"Rotate with `python -m jarvis.vault set NAME`.")
    return 0


def _cmd_set(args: argparse.Namespace) -> int:
    value = getpass.getpass(f"value for {args.name}: ")
    set_secret(args.name, value)
    print(f"stored {args.name}")
    return 0


def _cmd_get(args: argparse.Namespace) -> int:
    value = get_secret(args.name)
    if value is None:
        print(f"no secret named {args.name}", file=sys.stderr)
        return 1
    if sys.stdout.isatty():
        print("warning: printing a secret to a terminal", file=sys.stderr)
    print(value)
    return 0


def _cmd_rm(args: argparse.Namespace) -> int:
    delete_secret(args.name)
    print(f"removed {args.name}")
    return 0


def _cmd_migrate(args: argparse.Namespace) -> int:
    if not vault_path().exists():
        print("no vault yet — run `python -m jarvis.vault init` first",
              file=sys.stderr)
        return 1
    result = migrate_env_file(Path(args.env_file))
    for name in result["migrated"]:
        print(f"migrated {name}")
    for name in result["skipped"]:
        print(f"skipped {name} (empty value)")
    if not result["migrated"]:
        print("nothing to migrate")
    else:
        print(
            f"\n{len(result['migrated'])} secret(s) moved into the vault; "
            "their .env lines are now comments.\n"
            "Reminder: delete any .env backups (.env.bak etc.) that still "
            "hold plaintext values."
        )
    return 0


def _cmd_export_key(_args: argparse.Namespace) -> int:
    key = _load_key()
    print("warning: this is the vault master key — treat it like a password",
          file=sys.stderr)
    print(base64.b64encode(key).decode("ascii"))
    return 0


def _cmd_rotate_key(_args: argparse.Namespace) -> int:
    path = vault_path()
    old_key = _load_key()
    with _vault_write_lock(path):
        secrets = _decrypt(_read_envelope(path), old_key) if path.exists() else {}
        new_key = os.urandom(32)
        _store_key(new_key)
        _write_vault(path, secrets, new_key)
    print("vault key rotated and re-encrypted "
          f"({len(secrets)} secret(s) preserved)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m jarvis.vault",
        description="Mortimer credential vault (CLI-only management — "
                    "no console panel, no admin endpoint, by design).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="create the vault + keychain key").set_defaults(fn=_cmd_init)
    sub.add_parser("status", help="exists? decryptable? how many names").set_defaults(fn=_cmd_status)
    sub.add_parser("list", help="secret names (never values)").set_defaults(fn=_cmd_list)
    sub.add_parser(
        "verify",
        help="do the stored model keys actually work? (read-only, no values)",
    ).set_defaults(fn=_cmd_verify)

    p = sub.add_parser("set", help="store a secret (value prompted, never argv)")
    p.add_argument("name")
    p.set_defaults(fn=_cmd_set)

    p = sub.add_parser("get", help="print one secret value (for scripting)")
    p.add_argument("name")
    p.set_defaults(fn=_cmd_get)

    p = sub.add_parser("rm", help="remove a secret")
    p.add_argument("name")
    p.set_defaults(fn=_cmd_rm)

    p = sub.add_parser("migrate", help="move secrets out of .env into the vault")
    p.add_argument("--env-file", default=".env")
    p.set_defaults(fn=_cmd_migrate)

    sub.add_parser("export-key", help="print the base64 master key (for another machine)").set_defaults(fn=_cmd_export_key)
    sub.add_parser("rotate-key", help="new key, re-encrypt, update keychain").set_defaults(fn=_cmd_rotate_key)

    args = parser.parse_args(argv)
    try:
        return args.fn(args)
    except VaultError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
