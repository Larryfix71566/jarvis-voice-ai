"""macOS user notification via osascript (gap-closure plan GC9). Fixed argv,
never a shell — the pbcopy/pbpaste precedent (CLAUDE.md, handoff loop)."""
from __future__ import annotations
import logging, subprocess
logger = logging.getLogger(__name__)
NOTIFY_TIMEOUT_S = 5.0     # §6
NOTIFY_MAX_CHARS = 200     # §6

def _as_str(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'

def build_argv(message: str, title: str = "Mortimer") -> list[str]:
    msg = message[:NOTIFY_MAX_CHARS]
    return ["osascript", "-e", f"display notification {_as_str(msg)} with title {_as_str(title)}"]

def post_notification(message: str, title: str = "Mortimer") -> bool:
    try:
        proc = subprocess.run(build_argv(message, title), check=False,
                              timeout=NOTIFY_TIMEOUT_S, capture_output=True)
        return proc.returncode == 0
    except Exception as exc:  # noqa: BLE001 — a notification must never crash the notifier
        logger.warning("notify_failed error=%s", type(exc).__name__)
        return False
