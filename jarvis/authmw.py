"""One ASGI middleware, shared by the admin sidecar and the bot (K1, A6).

WHY PURE ASGI AND NOT BaseHTTPMiddleware. Starlette dispatches
BaseHTTPMiddleware — which is what `@app.middleware("http")` produces —
only for scope["type"] == "http". The Pipecat runner registers four
WebSocket routes (pipecat/runner/run.py:486, 491, 1274, 1279). A
middleware that cannot see a websocket scope would leave those four
unauthenticated. This class inspects scope["type"] itself.

WHY NOT PER-ROUTE Depends. 64 sidecar routes plus 16 measured bot routes,
where forgetting one fails silently. Middleware is coverage by
construction; tests/unit/test_auth_middleware.py enumerates app.routes and
proves it.

ORDERING. Starlette's add_middleware inserts at index 0, so the LAST
middleware added is the OUTERMOST. On both the sidecar and bot, this class
is added before CORSMiddleware, leaving CORS outermost so preflight works
and CORS headers are attached to auth failures — see the plan's A7.
"""

from __future__ import annotations

import json
import logging

from jarvis.auth import VerifyUnavailable, auth_enabled, verify_bearer
from jarvis.tenant import is_valid_user_id, user_id_scope

logger = logging.getLogger(__name__)

UNAUTHORIZED_BODY = json.dumps(
    {
        "ok": False,
        "error": "unauthorized - Authorization: Bearer <token> required",
    }
).encode("utf-8")

# F5: a database lock during verification is not an auth failure.
UNAVAILABLE_BODY = json.dumps(
    {"ok": False, "error": "service unavailable - verification backend busy"}
).encode("utf-8")

# 4000-4999 is the application-defined WebSocket close range; 4401 is the
# conventional analogue of HTTP 401. F14 NOTE: a close sent before accept is
# a handshake rejection, and uvicorn surfaces it to the client as HTTP 403 —
# 4401 is an ASGI-level intent only, asserted by T-A22 at the message level,
# never something the client reads.
WS_CLOSE_UNAUTHORIZED = 4401
WS_CLOSE_UNAVAILABLE = 4503


def _header(scope, name: bytes) -> str | None:
    for key, value in scope.get("headers", []):
        if key.lower() == name:
            return value.decode("latin-1")
    return None


async def _send_http(scope, send, status: int, body: bytes, extra_headers=()) -> None:
    headers = [
        (b"content-type", b"application/json"),
        (b"content-length", str(len(body)).encode("ascii")),
        *extra_headers,
    ]
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})


async def _reject(scope, send) -> None:
    if scope["type"] == "websocket":
        await send({"type": "websocket.close", "code": WS_CLOSE_UNAUTHORIZED})
        return
    await _send_http(
        scope, send, 401, UNAUTHORIZED_BODY,
        extra_headers=[(b"www-authenticate", b'Bearer realm="jarvis"')],
    )


async def _unavailable(scope, send) -> None:
    if scope["type"] == "websocket":
        await send({"type": "websocket.close", "code": WS_CLOSE_UNAVAILABLE})
        return
    await _send_http(
        scope, send, 503, UNAVAILABLE_BODY, extra_headers=[(b"retry-after", b"1")]
    )


class BearerAuthMiddleware:
    """Rejects every http and websocket request without a valid token."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            # "lifespan" and anything future. Never authenticated; there
            # is no caller.
            await self.app(scope, receive, send)
            return

        if not auth_enabled():
            await self.app(scope, receive, send)
            return

        if (
            scope["type"] == "http"
            and scope.get("method") == "OPTIONS"
            and _header(scope, b"origin") is not None
            and _header(scope, b"access-control-request-method") is not None
        ):
            # A GENUINE CORS preflight (both Origin and
            # Access-Control-Request-Method present) carries no
            # Authorization header by specification, so let it through to
            # CORSMiddleware. F16: a bare OPTIONS with neither header is NOT
            # a preflight and is authenticated like any other request, so
            # this branch is not a route-enumeration oracle (no 405/Allow
            # leak without a token). With CORS outermost (A7) this branch is
            # normally unreachable with CORS outermost; it remains as
            # defence if an embedding changes middleware order.
            await self.app(scope, receive, send)
            return

        header = _header(scope, b"authorization")
        try:
            identity = verify_bearer(header)
        except VerifyUnavailable:
            # F5: the database was busy — a retryable condition, not an auth
            # decision. 503, never 401.
            logger.warning(
                "auth_unavailable type=%s path=%s",
                scope["type"],
                scope.get("path", ""),
            )
            await _unavailable(scope, send)
            return
        if identity is None:
            logger.warning(
                "auth_rejected type=%s path=%s reason=%s",
                scope["type"],
                scope.get("path", ""),
                "missing" if not header else "invalid",
            )
            await _reject(scope, send)
            return

        # A9: the seam later plans need. Nothing reads it in T2. The token
        # itself is never placed on the scope.
        scope["client_identity"] = identity
        if not is_valid_user_id(identity.user_id):
            # A malformed tenant row must never fall back to the process-wide
            # tenant. Fail closed with the same retryable service response as
            # an unavailable identity backend.
            logger.warning("auth_identity_invalid type=%s", scope["type"])
            await _unavailable(scope, send)
            return
        with user_id_scope(identity.user_id):
            await self.app(scope, receive, send)
