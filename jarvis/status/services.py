"""`service_health()` — which background services are up (spec T2.3).

Reachability is measured (a TCP connect or an HTTP GET, 2 s each); launchd
state is read from `launchctl print`. The per-service launchctl parse
lives HERE (`launchd_state`), and `scripts/launchd_gen.py:status()` calls
it, so the CLI and the status tools read one implementation (R8).

The admin sidecar is reported up by construction: it is the process
serving this request, and it never calls itself.

Also reports the checkout's `source` (HEAD and the count of dirty files),
which is how an overlay checkout like spec fact 3.1 shows up honestly.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import socket
import subprocess
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parents[2]
PROBE_TIMEOUT_S = 2.0
GIT_TIMEOUT_S = 5.0

# name -> probe target. "tcp://host:port" is a bare connect; http(s) URLs
# must answer 200. Services absent here (extractor, backup) have no port.
PROBES: dict[str, str] = {
    "bot": "tcp://127.0.0.1:7860",
    "vault": "http://127.0.0.1:8484/health",
    "costs": "http://127.0.0.1:8487/costs/summary",
}


def launchd_state(svc: str, *, run: Callable[..., Any] | None = None) -> str:
    """"not loaded" | "loaded (pid N)" | "loaded (idle)", or "unknown" when
    launchctl is absent (Linux, tests). Moved verbatim from
    scripts/launchd_gen.py:status(); `run` is the test seam."""
    if run is None:
        if shutil.which("launchctl") is None:
            return "unknown"
        run = subprocess.run
    target = f"gui/{os.getuid()}/com.mortimer.{svc}"
    try:
        proc = run(["launchctl", "print", target], check=False,
                   capture_output=True, text=True)
    except FileNotFoundError:
        return "unknown"
    if proc.returncode != 0:
        return "not loaded"
    pid = None
    for line in proc.stdout.splitlines():
        line = line.strip()
        if line.startswith("pid ="):
            pid = line.split("=", 1)[1].strip()
            break
    return f"loaded (pid {pid})" if pid else "loaded (idle)"


def _launchctl(svc: str) -> str:
    return launchd_state(svc)


def _http_probe(target: str) -> tuple[bool, str]:
    """(up, detail) for one PROBES target. Never raises."""
    parsed = urlparse(target)
    if parsed.scheme == "tcp":
        try:
            with socket.create_connection((parsed.hostname, parsed.port),
                                          timeout=PROBE_TIMEOUT_S):
                return True, "port open"
        except OSError as exc:
            return False, _describe(exc)
    try:
        with urllib.request.urlopen(target, timeout=PROBE_TIMEOUT_S) as resp:  # noqa: S310 — fixed localhost URLs
            code = resp.status
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code}"
    except Exception as exc:  # noqa: BLE001
        return False, _describe(exc)
    return (True, "HTTP 200") if code == 200 else (False, f"HTTP {code}")


def _describe(exc: BaseException) -> str:
    reason = getattr(exc, "reason", exc)
    if isinstance(reason, ConnectionRefusedError):
        return "connection refused"
    if isinstance(reason, (socket.timeout, TimeoutError)):
        return "timed out"
    return type(reason).__name__


def _git(args: list[str], repo_root: Path) -> str | None:
    try:
        proc = subprocess.run(["git", *args], cwd=repo_root, check=False,
                              capture_output=True, text=True, timeout=GIT_TIMEOUT_S)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return proc.stdout if proc.returncode == 0 else None


def repo_head(repo_root: Path = REPO_ROOT) -> str | None:
    out = _git(["rev-parse", "HEAD"], repo_root)
    return out.strip() if out else None


def source_state(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    """{"head": sha or None, "dirty_files": count of porcelain lines or None}."""
    porcelain = _git(["status", "--porcelain"], repo_root)
    return {
        "head": repo_head(repo_root),
        "dirty_files": (len([l for l in porcelain.splitlines() if l.strip()])
                        if porcelain is not None else None),
    }


def _launchd_services() -> tuple[str, ...]:
    """The launchd service list, from scripts/launchd_gen.py (its ONE
    definition). Loaded by path — scripts/ is not a package — the same way
    jarvis.keyhealth reuses scripts/check_env.py."""
    path = REPO_ROOT / "scripts" / "launchd_gen.py"
    spec = importlib.util.spec_from_file_location("_launchd_gen_services", path)
    if spec is None or spec.loader is None:
        return ()
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return tuple(getattr(module, "ALL_SERVICES", ()))


def service_health(*, http: Callable[[str], tuple[bool, str]] = _http_probe,
                   launchctl: Callable[[str], str] = _launchctl,
                   services: tuple[str, ...] | None = None,
                   repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    names = list(services if services is not None else _launchd_services())
    for extra in ("admin", *PROBES):
        if extra not in names:
            names.append(extra)
    rows: list[dict[str, Any]] = []
    for name in names:
        if name == "admin":
            state, detail = "up", "serving this request"
        elif name in PROBES:
            up, detail = http(PROBES[name])
            state = "up" if up else "down"
        else:
            state, detail = "no port", "no port to probe"
        rows.append({"name": name, "state": state, "detail": detail,
                     "launchd": launchctl(name)})
    return {
        "ok": True,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "services": rows,
        "source": source_state(repo_root),
    }
