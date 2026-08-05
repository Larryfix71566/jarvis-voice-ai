"""SQLite persistence (plan Phase 0 step 0.4, schema locked in §5/§0.4).

Stdlib sqlite3 only. WAL mode, row_factory = sqlite3.Row. Migrations are
applied in order and tracked in the `migrations` table; running them twice
is idempotent.

Exposes exactly (per plan): get_conn(), run_migrations(), now_iso().
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

MIGRATION_0001 = """
CREATE TABLE IF NOT EXISTS migrations (
  id TEXT PRIMARY KEY, applied_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS notes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL,
  body TEXT NOT NULL,
  tags TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reminders (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  message TEXT NOT NULL,
  due_at TEXT NOT NULL,              -- ISO 8601, timezone-aware
  status TEXT NOT NULL DEFAULT 'pending',   -- pending | done | cancelled
  delivered INTEGER NOT NULL DEFAULT 0,     -- 1 once spoken to the user
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS conversations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT NOT NULL,
  role TEXT NOT NULL,                -- user | assistant | tool
  content TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_reminders_due ON reminders(status, due_at);
CREATE INDEX IF NOT EXISTS idx_notes_tags ON notes(tags);
"""

# (migration_id, sql) — applied strictly in list order.
MIGRATIONS: list[tuple[str, str]] = [
    ("0001_init", MIGRATION_0001),
]


def _default_db_path() -> Path:
    return Path(os.environ.get("JARVIS_DB_PATH", "data/jarvis.db"))


def get_conn(db_path: str | Path | None = None) -> sqlite3.Connection:
    """Open a connection (WAL mode, Row factory). Creates the parent dir."""
    path = Path(db_path) if db_path is not None else _default_db_path()
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def now_iso() -> str:
    """Current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def run_migrations(conn: sqlite3.Connection | None = None) -> list[str]:
    """Apply pending migrations. Returns the ids applied in this run."""
    own_connection = conn is None
    conn = conn or get_conn()
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS migrations "
            "(id TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        already = {row["id"] for row in conn.execute("SELECT id FROM migrations")}
        newly_applied: list[str] = []
        for migration_id, sql in MIGRATIONS:
            if migration_id in already:
                continue
            conn.executescript(sql)
            conn.execute(
                "INSERT INTO migrations (id, applied_at) VALUES (?, ?)",
                (migration_id, now_iso()),
            )
            newly_applied.append(migration_id)
        conn.commit()
        return newly_applied
    finally:
        if own_connection:
            conn.close()
