"""Second-path ("backup") rules for read-only tools (WS-38 1A).

Design note: docs/reviews/2026-11-19-request-resolution-design-note.md §5.

A tool with two ways to get the same answer may try the second path only
when `may_fall_back(reason)` is true: the reason is a key of REASON_CLASSES,
its class is `transient` or `approach`, and it is not in NO_BACKUP_REASONS.
An unlisted reason is False, and `policy` is always False: a guard that
refused on purpose is never routed around. Rate limits, rejected keys,
exhausted quotas, rejected requests and missing configuration are listed
because the backup would hit the same account or the same input and fail
the same way, while costing a second call. Read-only tools only.

Which path served is recorded only as closed codes (PATHS), never free text,
so it is safe to log and to store on a private turn.

Stdlib, httpx and jarvis.toolresult only: MCP child processes import this.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import httpx

from jarvis.toolresult import REASON_CLASSES

# Closed path codes per tool, primary first. The three weather tools are
# reserved for the weather change and unused here.
PATHS: dict[str, tuple[str, ...]] = {
    "web_search": ("tavily_mcp", "tavily_rest"),
    "local_weather": ("saved_card", "live_fetch"),
    "get_weather": ("saved_card", "live_fetch"),
    "get_weather_radar": ("saved_card", "live_fetch"),
}

# Reasons where a second path would fail the same way.
NO_BACKUP_REASONS: frozenset[str] = frozenset({
    "upstream_rate_limited",
    "upstream_auth_rejected",
    "upstream_quota_exhausted",
    "upstream_rejected_request",
    "tool_not_configured",
    "invalid_arguments",
})


def may_fall_back(reason: str | None) -> bool:
    """True when a backup path may be tried after a failure with `reason`."""
    if not isinstance(reason, str) or reason not in REASON_CLASSES:
        return False
    if reason in NO_BACKUP_REASONS:
        return False
    return REASON_CLASSES[reason] in ("transient", "approach")


def http_failure_reason(exc: BaseException) -> str:
    """Map an httpx (or parsing) exception to a closed REASON_CLASSES key."""
    if isinstance(exc, httpx.TimeoutException):
        return "upstream_timeout"
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if status == 401:
            return "upstream_auth_rejected"
        if status == 403:
            return "upstream_blocked"
        if status == 429:
            return "upstream_rate_limited"
        # Tavily's quota statuses (untested against the live service).
        if status in (432, 433):
            return "upstream_quota_exhausted"
        if 400 <= status < 500:
            return "upstream_rejected_request"
        if status >= 500:
            return "upstream_error"
        return "upstream_protocol_error"
    if isinstance(exc, (httpx.ConnectError, httpx.NetworkError,
                        httpx.RemoteProtocolError, httpx.TransportError)):
        return "upstream_unreachable"
    # json.JSONDecodeError is a ValueError; anything else is a protocol fault.
    return "upstream_protocol_error"


@dataclass(frozen=True)
class PathServed:
    tool: str
    path: str
    after: str | None  # reason the earlier path failed, None for the primary


def served(tool: str, path: str, after: str | None = None) -> PathServed:
    if path not in PATHS.get(tool, ()):
        raise ValueError(f"unknown path {path!r} for tool {tool!r}")
    if after is not None and after not in REASON_CLASSES:
        raise ValueError(f"unlisted fallback reason {after!r}")
    return PathServed(tool, path, after)


def mark(body: dict, ps: PathServed) -> dict:
    """Return `body` with the closed path codes added."""
    out = dict(body)
    out["served_by"] = ps.path
    if ps.after:
        out["fallback_after"] = ps.after
    return out


def read_served(tool: str, result_str: str) -> PathServed | None:
    """Read the path codes back from a result string; None when absent or
    not a closed code for `tool`."""
    try:
        body = json.loads(result_str)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    if not isinstance(body, dict):
        return None
    path = body.get("served_by")
    if not isinstance(path, str) or path not in PATHS.get(tool, ()):
        return None
    after = body.get("fallback_after")
    if not isinstance(after, str) or after not in REASON_CLASSES:
        after = None
    return PathServed(tool, path, after)


def log_served(logger, ps: PathServed) -> None:
    logger.info("tool_path tool=%s path=%s after=%s", ps.tool, ps.path, ps.after)
