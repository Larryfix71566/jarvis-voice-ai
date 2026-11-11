"""Host/Origin allow-list plus a required client header (WS-34 B2).

One pure-ASGI middleware shared by the admin sidecar (:7861), the bot runner
(:7860) and the costs API (:8487). Pure ASGI, like jarvis/authmw.py, because
the bot's WebSocket routes are only visible to a middleware that inspects
scope["type"] itself.

Rules, in order (http and websocket scopes only):

1. Host: the hostname (port ignored) must be loopback, the listener's own
   address (scope["server"]), or named in JARVIS_ALLOWED_HOSTS. This is the
   DNS-rebinding defence: a rebinding page carries its own hostname.
2. Origin: absent passes (non-browser clients, same-origin GETs). Present, it
   must be same-origin with the validated Host or in the allowed-origin set.
   "null" is refused.
3. Sec-Fetch-Site: cross-site with no allowed Origin is refused.
4. X-Mortimer-Client is required on mutating http methods when the request is
   browser-shaped (Origin / Sec-Fetch-* present) and not same-origin. The
   native app and Python callers send none of those headers and are exempt.

Kill switch JARVIS_REQUEST_GUARD_ENABLED (default on) is read ONLY in
guard_enabled(); JARVIS_ALLOWED_HOSTS / JARVIS_ALLOWED_ORIGINS only here.
Do not set PIPECAT_ALLOWED_ORIGINS: the native app's /ws-client sends no
Origin and would be closed with 4003.
"""

from __future__ import annotations

import ipaddress
import json
import logging
import os
import re

logger = logging.getLogger(__name__)

ENABLED_ENV = "JARVIS_REQUEST_GUARD_ENABLED"
ALLOWED_HOSTS_ENV = "JARVIS_ALLOWED_HOSTS"
ALLOWED_ORIGINS_ENV = "JARVIS_ALLOWED_ORIGINS"
CLIENT_HEADER = "X-Mortimer-Client"
DEFAULT_BROWSER_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
WS_CLOSE_FORBIDDEN = 4403

_CLIENT_VALUE_RE = re.compile(r"[A-Za-z0-9._-]{1,64}")
_DEFAULT_PORTS = {"http": 80, "https": 443}

_HOST_BODY = json.dumps(
    {"ok": False, "error": "forbidden - request host or origin not allowed"}
).encode("utf-8")
_HEADER_BODY = json.dumps(
    {
        "ok": False,
        "error": "forbidden - X-Mortimer-Client header required for cross-origin writes",
    }
).encode("utf-8")


def guard_enabled() -> bool:
    """THE ONLY READ of JARVIS_REQUEST_GUARD_ENABLED. Unset means on."""
    value = os.environ.get(ENABLED_ENV, "").strip().lower()
    return value not in ("false", "0", "no")


def _csv(name: str) -> list[str]:
    return [p.strip() for p in os.environ.get(name, "").split(",") if p.strip()]


def allowed_extra_hosts() -> frozenset[str]:
    hosts: set[str] = set()
    for item in _csv(ALLOWED_HOSTS_ENV):
        if "*" in item:
            logger.warning("request_guard_ignored_wildcard_host entry=%r", item[:64])
            continue
        parsed = _split_host(item)
        if parsed:
            hosts.add(parsed)
    return frozenset(hosts)


def _port_of(value: str) -> int | None:
    value = value.strip()
    if value.startswith("["):
        rest = value[value.find("]") + 1 :]
        return int(rest[1:]) if rest.startswith(":") and rest[1:].isdigit() else None
    if ":" in value:
        port = value.rsplit(":", 1)[1]
        return int(port) if port.isdigit() else None
    return None


def _split_host(value: str) -> str | None:
    """'[::1]:7861' -> '::1', 'Evil.COM:80' -> 'evil.com'; bad input -> None."""
    value = (value or "").strip().lower()
    if not value or any(c in value for c in " /\\?#@\t\r\n"):
        return None
    if value.startswith("["):
        end = value.find("]")
        if end < 0:
            return None
        host = value[1:end]
        rest = value[end + 1 :]
        if rest and not (rest.startswith(":") and rest[1:].isdigit()):
            return None
        try:
            ipaddress.ip_address(host)
        except ValueError:
            return None
        return host
    if value.count(":") > 1:
        return None
    host = value
    if ":" in value:
        host, port = value.rsplit(":", 1)
        if port and not port.isdigit():
            return None
    return host or None


def _normalise_origin(value: str) -> tuple[str, str, int] | None:
    m = re.fullmatch(r"(https?|wss?)://([^/?#@\s]+)", value.strip().lower())
    if not m:
        return None
    scheme = {"ws": "http", "wss": "https"}.get(m.group(1), m.group(1))
    host = _split_host(m.group(2))
    if host is None:
        return None
    port = _port_of(m.group(2))
    if port is None:
        port = _DEFAULT_PORTS[scheme]
    return scheme, host, port


def allowed_browser_origins() -> tuple[str, ...]:
    out = list(DEFAULT_BROWSER_ORIGINS)
    for item in _csv(ALLOWED_ORIGINS_ENV):
        if item == "*" or item.lower() == "null" or _normalise_origin(item) is None:
            logger.warning("request_guard_ignored_origin entry=%r", item[:64])
            continue
        if item not in out:
            out.append(item)
    return tuple(out)


def client_headers(name: str = "mortimer-python") -> dict[str, str]:
    return {CLIENT_HEADER: name}


def host_allowed(host: str, server_host: str | None) -> bool:
    if host == "localhost":
        return True
    try:
        if ipaddress.ip_address(host).is_loopback:
            return True
    except ValueError:
        pass
    if server_host and host == server_host.lower():
        return True
    return host in allowed_extra_hosts()


def _headers(scope) -> dict[bytes, str]:
    out: dict[bytes, str] = {}
    for key, value in scope.get("headers", []):
        out.setdefault(key.lower(), value.decode("latin-1"))
    return out


def _same_origin(scope, origin: str, host_header: str) -> bool:
    o = _normalise_origin(origin)
    if o is None:
        return False
    raw = scope.get("scheme", "http")
    scheme = {"ws": "http", "wss": "https"}.get(raw, raw)
    port = _port_of(host_header)
    if port is None:
        port = _DEFAULT_PORTS.get(scheme, 80)
    return o == (scheme, _split_host(host_header), port)


def _origin_allowed(origin: str) -> bool:
    o = _normalise_origin(origin)
    if o is None:
        return False
    return any(_normalise_origin(a) == o for a in allowed_browser_origins())


def _printable(value: str | None) -> str:
    return "".join(c for c in (value or "") if c.isprintable())[:64]


async def _reject(scope, send, reason: str, host: str | None, body: bytes) -> None:
    logger.warning(
        "request_guard_rejected type=%s method=%s path=%s reason=%s host=%r",
        scope["type"],
        scope.get("method", "-"),
        scope.get("path", ""),
        reason,
        _printable(host),
    )
    if scope["type"] == "websocket":
        await send({"type": "websocket.close", "code": WS_CLOSE_FORBIDDEN})
        return
    await send(
        {
            "type": "http.response.start",
            "status": 403,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


class RequestGuardMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket") or not guard_enabled():
            await self.app(scope, receive, send)
            return

        h = _headers(scope)
        host_header = h.get(b"host")
        if not host_header:
            await _reject(scope, send, "host_missing", None, _HOST_BODY)
            return
        host = _split_host(host_header)
        server = scope.get("server")
        server_host = server[0] if server and isinstance(server[0], str) else None
        if host is None or not host_allowed(host, server_host):
            await _reject(scope, send, "host_not_allowed", host_header, _HOST_BODY)
            return

        origin = h.get(b"origin")
        origin_ok = False
        same_origin = False
        if origin is not None:
            same_origin = _same_origin(scope, origin, host_header)
            origin_ok = same_origin or _origin_allowed(origin)
            if not origin_ok:
                await _reject(scope, send, "origin_not_allowed", host_header, _HOST_BODY)
                return

        fetch_site = (h.get(b"sec-fetch-site") or "").strip().lower()
        if fetch_site == "cross-site" and not (origin is not None and origin_ok):
            await _reject(scope, send, "cross_site", host_header, _HOST_BODY)
            return

        if scope["type"] == "http" and scope.get("method", "GET").upper() not in SAFE_METHODS:
            browser_shaped = (
                origin is not None or b"sec-fetch-site" in h or b"sec-fetch-mode" in h
            )
            same = same_origin or (origin is None and fetch_site == "same-origin")
            if browser_shaped and not same:
                value = h.get(CLIENT_HEADER.lower().encode("ascii"))
                if value is None or not _CLIENT_VALUE_RE.fullmatch(value):
                    await _reject(
                        scope, send, "client_header_missing", host_header, _HEADER_BODY
                    )
                    return

        await self.app(scope, receive, send)
