"""Client bearer tokens (K1) — mint, hash, verify, revoke.

Introduced by docs/plans/MORTIMER_REMOTE_ACCESS_PLAN.md §3 A1-A5, A13.

Imports: stdlib plus jarvis.db (which is itself stdlib-only). This module
is imported by the admin sidecar, by the bot's ASGI middleware, by three
MCP child processes, and by a CLI — one heavy import here lands in all
four, so there are none.

WHAT IS STORED. Only sha256(plaintext) hex. The plaintext is printed once
by `add` and never written by Mortimer to any file, log, or database. A
copy of data/jarvis.db therefore grants nobody access.

WHAT IS NOT HERE. There is no MCP tool and no HTTP endpoint that mints or
revokes (A13) — same rule and same reason as jarvis/vault.py: an
assistant that can mint its own credential has no credential.
"""

from __future__ import annotations

import argparse
import base64
import datetime as _dt
import hashlib
import hmac
import os
import secrets
import sqlite3
import sys
from dataclasses import dataclass

from jarvis.db import get_conn, now_iso, run_migrations

TOKEN_PREFIX = "jvt_"
TOKEN_BYTES = 32
# base64url of 32 bytes is 44 chars with padding, 43 without. A1 strips it.
TOKEN_BODY_LEN = 43
TOKEN_LEN = len(TOKEN_PREFIX) + TOKEN_BODY_LEN  # 47
DEFAULT_USER_ID = "larry"

ENABLED_ENV = "JARVIS_AUTH_ENABLED"
SERVICE_TOKEN_ENV = "JARVIS_SERVICE_TOKEN"

# F5: a busy database is not an auth decision. The verification READ is a
# WAL SELECT that does not block on a writer, but a checkpoint (or another
# process holding an exclusive lock) can still make it briefly unavailable;
# a short busy_timeout makes that fail fast instead of stalling the event
# loop, and the middleware answers 503 rather than 401.
VERIFY_BUSY_TIMEOUT_MS = 250
# last_used_at is bookkeeping, not correctness: only rewrite it when the
# stored value is older than this, so the busy voice path does not take a
# write lock on every request.
LAST_USED_THROTTLE_S = 60


class VerifyUnavailable(Exception):
    """Raised by verify_bearer when the verification READ cannot complete
    because SQLite was busy/locked. Means 'retry', not 'unauthenticated' —
    the middleware maps it to HTTP 503, never 401 (F5)."""


@dataclass(frozen=True)
class ClientIdentity:
    """Who presented a valid token. Frozen: a downstream handler must not
    be able to edit the identity it was handed (A9)."""

    name: str
    user_id: str


def auth_enabled() -> bool:
    """JARVIS_AUTH_ENABLED, dormant by default (Remote Access Addendum R1).

    THE ONLY READ OF THIS NAME IN THE CODEBASE (roadmap kill-switch rule).
    Only the exact string "true" (case-insensitive, stripped) enables it.
    Disabled auth always forces a loopback bind through jarvis.bind; enabling
    remote access remains an explicit operator decision.
    """
    return os.environ.get(ENABLED_ENV, "").strip().lower() == "true"


def service_headers() -> dict[str, str]:
    """Authorization header for Mortimer's own internal callers (K1).

    THE ONLY READ OF JARVIS_SERVICE_TOKEN. Returns {} when unset or empty
    so a caller can always splat it into httpx's headers= without a
    branch, and so a stack running with JARVIS_AUTH_ENABLED=false behaves
    exactly as it did before this plan.

    No database access: MCP children call this and must not need
    data/jarvis.db to build a header.
    """
    token = (os.environ.get(SERVICE_TOKEN_ENV) or "").strip()
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}"}


def mint_token() -> str:
    """A1: 'jvt_' + base64url(32 random bytes), padding stripped."""
    raw = secrets.token_bytes(TOKEN_BYTES)
    body = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    return TOKEN_PREFIX + body


def hash_token(token: str) -> str:
    """sha256 hex of the plaintext. 64 lowercase hex characters."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def parse_bearer(header_value: str | None) -> str | None:
    """Extract a syntactically valid token from an Authorization header.

    Returns None — never raises — for every malformed shape. NO DATABASE
    ACCESS HAPPENS HERE: a flood of junk headers costs string comparisons,
    not SQLite opens.

    Accepted: exactly two whitespace-separated fields, field one equal to
    "bearer" case-insensitively (RFC 7235 makes the scheme
    case-insensitive), field two of length TOKEN_LEN and starting with
    TOKEN_PREFIX.

    Rejected, each returning None: None, "", "   ", a bare token with no
    scheme, "Basic <tok>", "Token <tok>", "Bearer" alone, "Bearer a b",
    and a well-prefixed token of the wrong length.
    """
    if not header_value:
        return None
    parts = header_value.split()
    if len(parts) != 2:
        return None
    scheme, token = parts
    if scheme.lower() != "bearer":
        return None
    if len(token) != TOKEN_LEN:
        return None
    if not token.startswith(TOKEN_PREFIX):
        return None
    return token


def _touch_last_used(
    conn: sqlite3.Connection, row_id: int, last_used_at: str | None
) -> None:
    """Best-effort, throttled last_used_at write (F5). A lock here can
    NEVER change the auth verdict — the caller already decided the identity
    from the read. Any sqlite error (including a busy timeout on the write
    lock) is swallowed; the worst outcome is a slightly stale last_used_at.
    """
    now = now_iso()
    if last_used_at is not None:
        try:
            # Skip the write if the stored value is fresh enough.
            prev = _dt.datetime.fromisoformat(last_used_at)
            age = (_dt.datetime.now(_dt.timezone.utc) - prev).total_seconds()
            if age < LAST_USED_THROTTLE_S:
                return
        except (ValueError, TypeError):
            pass  # unparseable stored value: fall through and rewrite it
    try:
        conn.execute(
            "UPDATE client_tokens SET last_used_at = ? WHERE id = ?",
            (now, row_id),
        )
        conn.commit()
    except sqlite3.Error:
        return  # bookkeeping only — never fail a request over this


def verify_bearer(
    header_value: str | None, conn: sqlite3.Connection | None = None
) -> ClientIdentity | None:
    """K1's single verification helper.

    Returns None for missing, malformed, unknown, or revoked tokens. The
    VERDICT is decided entirely by a WAL SELECT, which does not block on a
    writer; on success it also does a best-effort, throttled last_used_at
    write whose success or failure cannot change the verdict (F5).

    Raises VerifyUnavailable if the verification READ itself cannot
    complete because the database was busy/locked (the middleware maps that
    to HTTP 503, not 401). Any other sqlite error on the read returns None
    (fail closed — a corrupt database must not become an open door).

    Connection ownership: opens and closes its own connection when conn is
    None; never closes a connection it was handed.

    The row loop deliberately does not break on a match, so the number of
    comparisons does not depend on which token was presented. Do not
    replace it with `WHERE token_hash = ?` (A5).
    """
    token = parse_bearer(header_value)
    if token is None:
        return None
    own_connection = conn is None
    conn = conn or get_conn()
    try:
        # Fail fast instead of stalling the event loop if the db is busy.
        conn.execute(f"PRAGMA busy_timeout = {VERIFY_BUSY_TIMEOUT_MS}")
        digest = hash_token(token)
        match: sqlite3.Row | None = None
        try:
            rows = list(
                conn.execute(
                    "SELECT id, name, user_id, token_hash, revoked_at, "
                    "last_used_at FROM client_tokens"
                )
            )
        except sqlite3.OperationalError as exc:
            # "database is locked"/"database is busy" on the READ — not an
            # auth decision. Signal retry.
            raise VerifyUnavailable(str(exc)) from exc
        for row in rows:
            if hmac.compare_digest(row["token_hash"], digest):
                match = row
        if match is None or match["revoked_at"] is not None:
            return None
        _touch_last_used(conn, match["id"], match["last_used_at"])
        return ClientIdentity(name=match["name"], user_id=match["user_id"])
    except sqlite3.Error:
        return None
    finally:
        if own_connection:
            conn.close()


def count_active_tokens(conn: sqlite3.Connection | None = None) -> int:
    """Unrevoked rows. 0 when the table does not exist yet — a database
    that has never been migrated must read as 'no tokens', which is what
    jarvis/bind.py needs to refuse a non-loopback bind."""
    own_connection = conn is None
    conn = conn or get_conn()
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM client_tokens WHERE revoked_at IS NULL"
        ).fetchone()
        return int(row["n"])
    except sqlite3.Error:
        return 0
    finally:
        if own_connection:
            conn.close()


# --------------------------------------------------------------------- CLI


def _cmd_add(name: str) -> int:
    name = name.strip()
    if not name:
        print("usage: python -m jarvis.auth add <name>", file=sys.stderr)
        return 2
    conn = get_conn()
    try:
        run_migrations(conn)
        token = mint_token()
        try:
            conn.execute(
                "INSERT INTO client_tokens (user_id, name, token_hash, created_at) "
                "VALUES (?, ?, ?, ?)",
                (DEFAULT_USER_ID, name, hash_token(token), now_iso()),
            )
        except sqlite3.IntegrityError:
            # A2: a name is never reused, revoked or not.
            print(
                f"a token named {name!r} already exists — revoke it first, "
                f"then add under a new name",
                file=sys.stderr,
            )
            return 2
        conn.commit()
    finally:
        conn.close()
    # The plaintext goes to stdout ALONE so `TOKEN=$(python -m jarvis.auth
    # add x)` works; everything else goes to stderr.
    print(token)
    print(
        f"# minted {name!r}. This is shown ONCE and is not stored — "
        f"copy it now.",
        file=sys.stderr,
    )
    return 0


def _cmd_list() -> int:
    conn = get_conn()
    try:
        run_migrations(conn)
        rows = list(
            conn.execute(
                "SELECT name, user_id, created_at, last_used_at, revoked_at "
                "FROM client_tokens ORDER BY id"
            )
        )
    finally:
        conn.close()
    if not rows:
        print("no client tokens — mint one with `python -m jarvis.auth add <name>`")
        return 0
    # token_hash is deliberately NOT selected and never printed.
    print(f"{'NAME':<24} {'USER':<10} {'CREATED':<28} {'LAST USED':<28} STATUS")
    for r in rows:
        status = "revoked" if r["revoked_at"] else "active"
        print(
            f"{r['name']:<24} {r['user_id']:<10} {r['created_at']:<28} "
            f"{(r['last_used_at'] or '-'):<28} {status}"
        )
    return 0


def _cmd_revoke(name: str) -> int:
    name = name.strip()
    if not name:
        print("usage: python -m jarvis.auth revoke <name>", file=sys.stderr)
        return 2
    conn = get_conn()
    try:
        run_migrations(conn)
        cur = conn.execute(
            "UPDATE client_tokens SET revoked_at = ? "
            "WHERE name = ? AND revoked_at IS NULL",
            (now_iso(), name),
        )
        conn.commit()
        changed = cur.rowcount
    finally:
        conn.close()
    if changed == 0:
        print(f"no active token named {name!r}", file=sys.stderr)
        return 2
    print(f"revoked {name}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m jarvis.auth",
        description="Client bearer tokens for the Mortimer sidecar and bot.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_add = sub.add_parser("add", help="mint a token (shown once)")
    p_add.add_argument("name")
    sub.add_parser("list", help="list tokens (never prints a hash)")
    p_rev = sub.add_parser("revoke", help="revoke a token by name")
    p_rev.add_argument("name")
    args = parser.parse_args(argv)
    if args.cmd == "add":
        return _cmd_add(args.name)
    if args.cmd == "list":
        return _cmd_list()
    return _cmd_revoke(args.name)


if __name__ == "__main__":
    raise SystemExit(main())
