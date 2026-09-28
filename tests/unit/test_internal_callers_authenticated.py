"""Internal Mortimer HTTP callers must authenticate through service_headers."""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

_SERVICE_TARGET = re.compile(
    r"ADMIN_URL_ENV|DEFAULT_ADMIN_URL|admin_url\s*\(|bot_url\s*\(|"
    r"127\.0\.0\.1:786[01]|JARVIS_(?:ADMIN|BOT)_PORT"
)
_HTTP_CLIENT = re.compile(
    r"httpx\.(?:Async)?Client\s*\(|urlopen\s*\(|"
    r"urllib\.request\.Request\s*\("
)

# This module intentionally uses bare TCP/HTTP service checks for the bot,
# vault and costs processes; those probes are outside the T2 admin/bot API.
_ALLOWLISTED = {"jarvis/status/services.py"}


def _caller_files() -> list[Path]:
    files = [*REPO_ROOT.joinpath("jarvis").rglob("*.py"),
             *REPO_ROOT.joinpath("mcp_servers").rglob("*.py"),
             *REPO_ROOT.joinpath("scripts").glob("*.py")]
    return sorted(path for path in files if "tests" not in path.relative_to(REPO_ROOT).parts)


def test_every_internal_sidecar_or_bot_http_client_uses_service_headers() -> None:
    violations: list[str] = []
    observed_allowlist: set[str] = set()
    for path in _caller_files():
        source = path.read_text(encoding="utf-8")
        if not (_SERVICE_TARGET.search(source) and _HTTP_CLIENT.search(source)):
            continue
        relative = path.relative_to(REPO_ROOT).as_posix()
        if relative in _ALLOWLISTED:
            observed_allowlist.add(relative)
        elif "service_headers" not in source:
            violations.append(relative)

    assert observed_allowlist == _ALLOWLISTED
    assert not violations, (
        "internal sidecar/bot HTTP callers must import and use "
        f"service_headers(): {', '.join(violations)}"
    )
