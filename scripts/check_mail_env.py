#!/usr/bin/env python3
"""Names-only preflight for mcp-mail (WS-13 plan §R.12 M1-1).

Prints, for EVERY MCP server in config/mcp_servers.yaml, whether each of the
four mail credential names and the kill switch would be forwarded to that
child by the registry's K2 env scoping (`build_child_env`), plus the
effective JARVIS_ENV_SCOPING_ENABLED. Values are never printed: a name is
reported as `set` (non-empty in this process) or not.

The environment is built the way the bot's run scripts build it: the repo's
.env is applied over the shell (`set -a; . ./.env`), then the vault fills any
name that is still missing or empty (`jarvis.vault.inject_env`). So the
effective scoping flag here is the one the bot gets.

M1-1 passes only when at least one mail name is set, every set name reaches
`mcp-mail`, none reaches any other server, and scoping is on. With no mail
name set the check has nothing to observe and says NOT TESTED rather than
pass. `--sentinel` sets each mail name to a fixed placeholder in this process
only (never a real credential, never printed, never written anywhere), so the
forwarding can be checked before the vault holds the real values.

Then it says which account(s) mail_headlines would read, by the same
per-account `not_configured` rule as mcp_servers/mcp_mail/logic.py. Nothing
here opens a socket. Exit 0 always; this is a report, not a gate.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SERVER = "mcp-mail"
SENTINEL = "preflight-sentinel-not-a-credential"


def _servers() -> list[dict]:
    import yaml

    data = yaml.safe_load((ROOT / "config" / "mcp_servers.yaml").read_text()) or {}
    return data if isinstance(data, list) else (
        data.get("servers") or data.get("mcp_servers") or [])


def _apply_dotenv() -> bool:
    """Mirror `set -a; . ./.env`: each KEY=VALUE line overrides the shell."""
    from jarvis.config import _dotenv_values

    path = ROOT / ".env"
    if not path.exists():
        return False
    for key, value in _dotenv_values(path).items():
        key = key.removeprefix("export ").strip()
        if key:
            os.environ[key] = value
    return True


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--sentinel", action="store_true",
                    help="set each mail name to a placeholder in this process to test forwarding")
    args = ap.parse_args(argv)

    # The registry warns about OTHER servers' missing requires_env names when
    # it builds their child environments; that is not what this report checks.
    # Restored on the way out so an in-process caller keeps its logging.
    registry_logger = logging.getLogger("jarvis.skills.registry")
    previous_level = registry_logger.level
    registry_logger.setLevel(logging.ERROR)
    try:
        return _report(args)
    finally:
        registry_logger.setLevel(previous_level)


def _report(args: argparse.Namespace) -> int:
    dotenv = _apply_dotenv()
    vault_note = "vault module unavailable"
    try:
        from jarvis.vault import inject_env
        vault_note = f"vault injected {inject_env()} name(s)"
    except ImportError:
        pass

    from jarvis.skills.registry import build_child_env, env_scoping_enabled
    from mcp_servers.mcp_mail import logic

    names = [a.user_env for a in logic.ACCOUNTS] + [a.password_env for a in logic.ACCOUNTS]
    names.append(logic.ENV_MAIL_ENABLED)
    credential_names = names[:-1]
    if args.sentinel:
        for name in credential_names:
            os.environ[name] = SENTINEL

    servers = _servers()
    scoping = env_scoping_enabled()
    print(f"environment: .env {'applied' if dotenv else 'absent'}, {vault_note}"
          + (", SENTINEL placeholders for the four mail names" if args.sentinel else ""))
    print(f"JARVIS_ENV_SCOPING_ENABLED (effective): {'on' if scoping else 'OFF'}")
    print()

    children = {s["name"]: build_child_env(s) for s in servers}
    columns = [s["name"] for s in servers]
    width = max(len(n) for n in names) + 2
    print(f"{'name':{width}s} {'set':5s} " + " ".join(f"{c:>12s}" for c in columns))
    offenders: list[tuple[str, str]] = []
    missing: list[str] = []
    set_names: list[str] = []
    for name in names:
        raw = os.environ.get(name, "")
        is_set = bool(raw.strip()) and "${" not in raw
        if is_set:
            set_names.append(name)
        cells = []
        for server in columns:
            forwarded = name in children[server]
            cells.append(f"{'yes' if forwarded else 'no':>12s}")
            if forwarded and server != SERVER:
                offenders.append((name, server))
        if is_set and SERVER in children and name not in children[SERVER]:
            missing.append(name)
        print(f"{name:{width}s} {'yes' if is_set else 'no':5s} " + " ".join(cells))
    print()
    if not scoping:
        print("M1-1: FAIL - env scoping is off; every child inherits the whole environment.")
    elif offenders:
        print("M1-1: FAIL - forwarded beyond mcp-mail: "
              + ", ".join(f"{n} -> {s}" for n, s in offenders))
    elif missing:
        print("M1-1: FAIL - set but not forwarded to mcp-mail: " + ", ".join(missing))
    elif not any(n in set_names for n in credential_names):
        print("M1-1: NOT TESTED - no mail credential name is set, so nothing can be seen being "
              "forwarded. Run with --sentinel, or after the vault holds the names.")
    else:
        print("M1-1: PASS - every set mail name reaches mcp-mail and no other server, "
              "and scoping is on.")
    print()

    if SERVER not in children:
        print(f"{SERVER}: not in config/mcp_servers.yaml")
        return 0
    child = children[SERVER]
    print(f"mail enabled: {'yes' if logic.mail_enabled(child) else 'no (' + logic.ENV_MAIL_ENABLED + ')'}")
    for account in logic.ACCOUNTS:
        ready = logic._credentials(account, child) is not None
        state = "would be read" if ready else "not_configured"
        if ready and args.sentinel:
            state = "configured (sentinel placeholders; not a real credential)"
        print(f"account {account.key:6s} ({account.label}): {state}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
