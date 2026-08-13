"""mcp-notes: SQLite-backed notes pure logic (plan Phase 1, §1.2).

Sync functions, plain dicts in/out. Errors are returned as
{"error": "<plain sentence>"} — this module never raises across the
MCP boundary.
"""

from __future__ import annotations

import sqlite3

from jarvis.db import get_conn, now_iso


def _row_to_note(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "title": row["title"],
        "body": row["body"],
        "tags": row["tags"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def create_note(title: str, body: str, tags: str = "") -> dict:
    title = (title or "").strip()
    body = (body or "").strip()
    if not title:
        return {"error": "A note needs a title."}
    if not body:
        return {"error": "A note needs a body."}
    now = now_iso()
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO notes (title, body, tags, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (title, body, (tags or "").strip(), now, now),
        )
        note_id = cur.lastrowid
    return {"id": note_id, "message": f"Note saved: {title}"}


def list_notes(tag: str | None = None, limit: int = 20) -> dict:
    limit = max(1, min(int(limit), 100))
    with get_conn() as conn:
        if tag:
            rows = conn.execute(
                "SELECT * FROM notes WHERE lower(tags) LIKE '%' || lower(?) || '%' "
                "ORDER BY id DESC LIMIT ?",
                (tag.strip(), limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM notes ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
    return {"notes": [_row_to_note(row) for row in rows]}


def search_notes(query: str) -> dict:
    query = (query or "").strip()
    if not query:
        return {"error": "A search query is required."}
    like = f"%{query.lower()}%"
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM notes WHERE lower(title) LIKE ? "
            "OR lower(body) LIKE ? OR lower(tags) LIKE ? "
            "ORDER BY id DESC LIMIT 50",
            (like, like, like),
        ).fetchall()
    return {"notes": [_row_to_note(row) for row in rows]}


def get_note(note_id: int) -> dict:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
    if row is None:
        return {"error": f"No note with id {note_id}."}
    return {"note": _row_to_note(row)}


def update_note(
    note_id: int,
    title: str | None = None,
    body: str | None = None,
    tags: str | None = None,
) -> dict:
    if title is None and body is None and tags is None:
        return {"error": "Nothing to update — provide title, body or tags."}
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
        if row is None:
            return {"error": f"No note with id {note_id}."}
        conn.execute(
            "UPDATE notes SET title = ?, body = ?, tags = ?, updated_at = ? "
            "WHERE id = ?",
            (
                title if title is not None else row["title"],
                body if body is not None else row["body"],
                tags if tags is not None else row["tags"],
                now_iso(),
                note_id,
            ),
        )
    return {"message": f"Note {note_id} updated."}


def delete_note(note_id: int) -> dict:
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))
    if cur.rowcount == 0:
        return {"error": f"No note with id {note_id}."}
    return {"message": f"Deleted note {note_id}."}


# Upgrade plan Phase 5a: search across past conversation sessions, not just
# saved notes. Lives here (rather than a new mcp_memory server) because the
# Librarian is already the conceptual owner of "recall anything" and already
# has this server's mcp_servers grant in config/agents.yaml — one process
# fewer to spawn and supervise for a single tool. The trade-off is that
# "mcp-notes" now touches conversations as well as notes; revisit if the
# tool surface grows enough to warrant a split.
MAX_SEARCH_RESULTS = 20
SNIPPET_TOKENS = 12  # words of context either side of a match


def search_sessions(query: str, limit: int = 10) -> dict:
    """Full-text search over past conversation transcripts (FTS5, migration
    0005_conversation_search). Returns ranked snippets with session id and
    timestamp so the caller can ask a follow-up question about a specific
    past session."""
    query = (query or "").strip()
    if not query:
        return {"error": "A search query is required."}
    limit = max(1, min(int(limit), MAX_SEARCH_RESULTS))

    # Quote each token individually so FTS5 special characters/operators in
    # user input (unbalanced quotes, "-", "*", "AND"/"OR"/"NOT" as literal
    # words) can never produce a malformed MATCH query; tokens are ANDed,
    # matching the "all these words" intuition search_notes already uses.
    tokens = query.split()
    fts_query = " AND ".join('"' + t.replace('"', '""') + '"' for t in tokens)

    with get_conn() as conn:
        try:
            rows = conn.execute(
                "SELECT session_id, role, created_at, "
                "snippet(conversations_fts, 0, '[', ']', '…', ?) AS snippet, "
                "bm25(conversations_fts) AS rank "
                "FROM conversations_fts WHERE conversations_fts MATCH ? "
                "ORDER BY rank LIMIT ?",
                (SNIPPET_TOKENS, fts_query, limit),
            ).fetchall()
        except sqlite3.OperationalError as exc:
            return {"error": f"Search failed: {exc}"}

    return {
        "results": [
            {
                "session_id": row["session_id"],
                "role": row["role"],
                "created_at": row["created_at"],
                "snippet": row["snippet"],
            }
            for row in rows
        ]
    }
