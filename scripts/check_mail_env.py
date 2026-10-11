#!/usr/bin/env python3
"""Names-only preflight for mcp-mail (WS-13 plan §R.12 M1-1).

Answers two questions for each of the four mail credential names and the
kill switch, without ever printing a value:

  set        the name resolves to a non-empty value in this process after
             the vault is injected (vault, .env via the run scripts, or env)
  forwarded  the registry would hand that name to the mcp-mail child
             (K2 env scoping: BASE_ENV_KEYS + skill.yaml's declarations)

Then it says which account(s) mail_headlines would read, which is exactly
the per-account `not_configured` rule in mcp_servers/mcp_mail/logic.py:
an account needs both its user and its secret. Nothing here opens a
socket. Exit 0 always; this is a report, not a gate.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SERVER = "mcp-mail"


def main() -> int:
    try:
        from jarvis.vault import inject_env
        inject_env()
    except ImportError:
        print("(vault module unavailable; reading the environment as-is)")

    import yaml

    from jarvis.skills.registry import build_child_env
    from mcp_servers.mcp_mail import logic

    data = yaml.safe_load((ROOT / "config" / "mcp_servers.yaml").read_text()) or {}
    servers = data if isinstance(data, list) else (
        data.get("servers") or data.get("mcp_servers") or [])
    entry = next((s for s in servers if s.get("name") == SERVER), None)
    if entry is None:
        print(f"{SERVER}: not in config/mcp_servers.yaml")
        return 0
    child = build_child_env(entry)

    names = [a.user_env for a in logic.ACCOUNTS] + [a.password_env for a in logic.ACCOUNTS]
    names.append("JARVIS_MAIL_ENABLED")
    print(f"{'name':28s} {'set':5s} {'forwarded':9s}")
    for name in names:
        is_set = bool((os.environ.get(name) or "").strip()) and "${" not in os.environ.get(name, "")
        print(f"{name:28s} {'yes' if is_set else 'no':5s} {'yes' if name in child else 'no':9s}")

    print()
    print(f"mail enabled: {'yes' if logic.mail_enabled(child) else 'no (JARVIS_MAIL_ENABLED)'}")
    for account in logic.ACCOUNTS:
        ready = logic._credentials(account, child) is not None
        print(f"account {account.key:6s} ({account.label}): "
              f"{'would be read' if ready else 'not_configured'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
