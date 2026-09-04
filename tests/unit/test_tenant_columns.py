"""Contract GC-T (gap-closure plan GC8, 2026-09-04): every table carries a
user_id TEXT NOT NULL DEFAULT 'local' column. This test is deliberately
generic -- it walks sqlite_master rather than hardcoding the 15 tables
migration 0020 touched, so a FUTURE migration that creates a table without
the column fails this test immediately, not months later when someone
finally needs to filter by tenant."""
from __future__ import annotations

from jarvis.db import get_conn, run_migrations

EXCLUDED_PREFIXES = ("sqlite_",)
EXCLUDED_NAMES = {"migrations"}


def _is_covered_table(name: str) -> bool:
    if name in EXCLUDED_NAMES:
        return False
    if any(name.startswith(p) for p in EXCLUDED_PREFIXES):
        return False
    if "_fts" in name:  # FTS5 virtual table + its shadow tables
        return False
    return True


def test_every_table_has_default_local_user_id(tmp_path):
    conn = get_conn(tmp_path / "tenant_cols.db")
    run_migrations(conn)
    try:
        tables = [
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
            if _is_covered_table(row["name"])
        ]
        assert tables, "no tables found -- migrations did not run"
        missing = []
        for name in tables:
            cols = {
                row["name"]: row
                for row in conn.execute(f"PRAGMA table_info({name})")
            }
            col = cols.get("user_id")
            if col is None:
                missing.append(name)
                continue
            assert col["notnull"] == 1, f"{name}.user_id must be NOT NULL"
            assert col["dflt_value"] == "'local'", (
                f"{name}.user_id default is {col['dflt_value']!r}, expected \"'local'\""
            )
        assert not missing, f"tables missing user_id: {missing}"
    finally:
        conn.close()
