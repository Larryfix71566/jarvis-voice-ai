"""`log_search()` — bounded, redacted reads of Mortimer's own logs (spec T2.3).

The caller names a SOURCE, never a path: `LOG_SOURCES` is the whole map
and there is no path argument. Conversation lines and full LLM contexts
are always dropped, key-like strings are redacted, and the read is capped
at the last 5 MB of the file. Read-only.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]

LOG_SOURCES = {
    "bot": "logs/bot.launchd.log",
    "admin": "logs/admin.launchd.log",
    "extractor": "logs/extractor.launchd.log",
    "costs": "logs/costs.launchd.log",
    "vault": "logs/vault.launchd.log",
    "backup": "logs/backup.launchd.log",
    "app": "logs/mortimerhost-window.log",
}

MAX_READ_BYTES = 5 * 1024 * 1024
MAX_LINE_CHARS = 300
MAX_LIMIT = 200
MAX_SINCE_MINUTES = 7 * 24 * 60

_TIMESTAMP = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})(?:[,.]\d{3})?")
_CONVERSATION = re.compile(r"^\[\d\d:\d\d:\d\d\] (USER|MORTIMER):")
_LLM_CONTEXT = "Generating chat from context"

# Applied in this order.
_REDACTIONS: tuple[tuple[re.Pattern[str], str], ...] = (
    # Review finding 6 (I1): any auth scheme, GitHub and Tavily tokens, and
    # credentials in a URL's userinfo.
    (re.compile(r"(?i)(authorization:\s*)(?!bearer\b)(\S+)\s+\S+"), r"\1\2 <redacted>"),
    (re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"), "<redacted>"),
    (re.compile(r"github_pat_\S+"), "<redacted>"),
    (re.compile(r"tvly-\S+"), "<redacted>"),
    (re.compile(r"(://)[^/\s:@]+:[^/\s@]+@"), r"\1<redacted>@"),
    (re.compile(r"sk-[A-Za-z0-9_-]{8,}"), "sk-…"),
    (re.compile(r"(?i)(bearer|x-api-key)[:= ]+\S+"), r"\1 <redacted>"),
    (re.compile(r"[A-Za-z0-9+/]{40,}={0,2}"), "<redacted>"),  # 40+ hex or base64
)


def _now() -> datetime:
    """Local wall-clock time, matching the logs' own asctime stamps. Test seam."""
    return datetime.now()


def redact(line: str) -> str:
    for pattern, repl in _REDACTIONS:
        line = pattern.sub(repl, line)
    return line


def _tail(path: Path) -> tuple[list[str], bool]:
    size = path.stat().st_size
    with path.open("rb") as fh:
        if size > MAX_READ_BYTES:
            fh.seek(size - MAX_READ_BYTES)
            data = fh.read()
            data = data.split(b"\n", 1)[1] if b"\n" in data else b""  # drop the partial line
            clipped = True
        else:
            data = fh.read()
            clipped = False
    return data.decode("utf-8", errors="replace").splitlines(), clipped


def log_search(source: str, query: str, *, since_minutes: int = 60,
               limit: int = 50) -> dict[str, Any]:
    rel = LOG_SOURCES.get(source)
    if rel is None:
        return {"ok": False,
                "error": f"unknown log source {source!r}; known: {', '.join(sorted(LOG_SOURCES))}"}
    path = REPO_ROOT / rel
    if not path.is_file():
        return {"ok": False, "error": f"no log file yet for source {source!r}"}
    since = max(1, min(int(since_minutes), MAX_SINCE_MINUTES))
    limit = max(1, min(int(limit), MAX_LIMIT))
    cutoff = _now() - timedelta(minutes=since)
    needle = (query or "").lower()

    lines, clipped = _tail(path)
    kept: list[str] = []
    current: datetime | None = None
    for raw in lines:
        match = _TIMESTAMP.match(raw)
        if match:
            try:
                current = datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S")
            except ValueError:
                pass
        if current is None or current < cutoff:
            continue
        if _CONVERSATION.match(raw) or _LLM_CONTEXT in raw:
            continue
        line = redact(raw)
        if needle and needle not in line.lower():
            continue
        kept.append(line[:MAX_LINE_CHARS])

    return {
        "ok": True,
        "source": source,
        "file": rel,
        "since_minutes": since,
        "query": redact(query or ""),
        "matched": len(kept),
        "clipped_to_last_5mb": clipped,
        "lines": kept[-limit:],
    }
