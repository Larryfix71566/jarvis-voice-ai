"""Print an authenticated local Mortimer service's HTTP status only.

Usage: ``python scripts/service_health.py admin|bot``. Output is exactly one
three-digit status code, or ``000`` when the service cannot be reached. This
human-only helper bypasses proxies and does not follow redirects so the
service token remains on the loopback request and bot redirects stay visible.
"""

from __future__ import annotations

import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jarvis.auth import service_headers
from jarvis.vault import inject_env

TARGETS = {
    "admin": ("JARVIS_ADMIN_PORT", 7861, "/api/health"),
    "bot": ("JARVIS_BOT_PORT", 7860, "/"),
}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def _port(env_name: str, default: int) -> int:
    value = os.environ.get(env_name, str(default)).strip()
    port = int(value)
    if not 1 <= port <= 65535:
        raise ValueError("port out of range")
    return port


def status_code(target: str) -> int:
    """Return a local HTTP status, or zero for invalid input/unavailable service."""
    if target not in TARGETS:
        return 0
    try:
        inject_env()
        env_name, default_port, path = TARGETS[target]
        url = f"http://127.0.0.1:{_port(env_name, default_port)}{path}"
        request = urllib.request.Request(url, headers=service_headers())
        # Never let ambient proxy settings receive the internal bearer token
        # or route a loopback health check outside the host.
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}), _NoRedirect,
        )
        try:
            with opener.open(request, timeout=3) as response:
                code = response.getcode()
        except urllib.error.HTTPError as exc:
            # urllib represents non-followed redirects and HTTP errors this way.
            code = exc.code
        return code if isinstance(code, int) and 100 <= code <= 599 else 0
    except Exception:  # noqa: BLE001 - unavailable health must remain content-free
        return 0


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    target = args[0] if len(args) == 1 else ""
    print(f"{status_code(target):03d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
