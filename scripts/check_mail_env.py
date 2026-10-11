#!/usr/bin/env python3
"""Names-only preflight for mcp-mail (WS-13 plan §R.12 M1-1).

Prints, for EVERY MCP server in config/mcp_servers.yaml, whether each of the
four mail credential names and the kill switch would be forwarded to that
child by the registry's K2 env scoping (`build_child_env`), plus the
effective JARVIS_ENV_SCOPING_ENABLED. M1-1 passes when only `mcp-mail` says
yes and scoping is on. Values are never printed: a name is reported as
`set` (non-empty in this process after the vault is injected) or not.

Then it says which account(s) mail_headlines would read, by the same
per-account `not_configured` rule as mcp_servers/mcp_mail/logic.py. Nothing
here opens a socket. Exit 0 always; this is a report, not a gate.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SERVER = "mcp-mail"


def _servers() -> list[dict]:
    import yaml

    data = yaml.safe_load((ROOT / "config" / "mcp_servers.yaml").read_text()) or {}
    return data if isinstance(data, list) else (
        data.get("servers") or data.get("mcp_servers") or [])


def main() -> int:
    try:
        from jarvis.vault import inject_env
        inject_env()
    except ImportError:
        print("(vault module unavailable; reading the environment as-is)")

    from jarvis.skills.registry import build_child_env, env_scoping_enabled
    from mcp_servers.mcp_mail import logic

    names = [a.user_env for a in logic.ACCOUNTS] + [a.password_env for a in logic.ACCOUNTS]
    names.append(logic.ENV_MAIL_ENABLED)
    servers = _servers()
    scoping = env_scoping_enabled()
    print(f"JARVIS_ENV_SCOPING_ENABLED (effective): {'on' if scoping else 'OFF'}")
    print()

    # Forwarding matrix: one row per name, one column per server. A name an
    # unset process cannot forward is still listed, so the matrix shape never
    # depends on what is configured.
    children = {s["name"]: build_child_env(s) for s in servers}
    columns = [s["name"] for s in servers]
    width = max(len(n) for n in names) + 2
    print(f"{'name':{width}s} {'set':5s} " + " ".join(f"{c:>12s}" for c in columns))
    offenders: list[tuple[str, str]] = []
    for name in names:
        raw = os.environ.get(name, "")
        is_set = bool(raw.strip()) and "${" not in raw
        cells = []
        for server in columns:
            forwarded = name in children[server]
            cells.append(f"{'yes' if forwarded else 'no':>12s}")
            if forwarded and server != SERVER:
                offenders.append((name, server))
        print(f"{name:{width}s} {'yes' if is_set else 'no':5s} " + " ".join(cells))
    print()
    if not scoping:
        print("M1-1: FAIL - env scoping is off; every child inherits the whole environment.")
    elif offenders:
        print("M1-1: FAIL - forwarded beyond mcp-mail: "
              + ", ".join(f"{n} -> {s}" for n, s in offenders))
    else:
        print("M1-1: PASS - only mcp-mail receives the mail names, and scoping is on.")
    print()

    child = children.get(SERVER, {})
    if SERVER not in children:
        print(f"{SERVER}: not in config/mcp_servers.yaml")
        return 0
    print(f"mail enabled: {'yes' if logic.mail_enabled(child) else 'no (' + logic.ENV_MAIL_ENABLED + ')'}")
    for account in logic.ACCOUNTS:
        ready = logic._credentials(account, child) is not None
        print(f"account {account.key:6s} ({account.label}): "
              f"{'would be read' if ready else 'not_configured'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
