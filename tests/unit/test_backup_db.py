"""Unit tests for scripts/backup_db.py (gap-closure plan GC7). stdlib
sqlite3.Connection.backup is WAL-safe; these tests exercise the actual
backup_one/prune/main functions rather than mocking sqlite out."""
from __future__ import annotations

import sqlite3

from scripts import backup_db


def _make_db(path, rows):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
    conn.executemany("INSERT INTO t (v) VALUES (?)", [(r,) for r in rows])
    conn.commit()
    conn.close()


def test_backup_creates_copy_with_same_rows(tmp_path, monkeypatch):
    monkeypatch.setattr(backup_db, "BACKUP_DIR", tmp_path / "backups")
    backup_db.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    src = tmp_path / "jarvis.db"
    _make_db(src, ["a", "b", "c"])

    dst = backup_db.backup_one(src, "20260101-0300")

    assert dst.exists()
    conn = sqlite3.connect(dst)
    rows = [r[0] for r in conn.execute("SELECT v FROM t ORDER BY id")]
    conn.close()
    assert rows == ["a", "b", "c"]


def test_prune_keeps_newest_n(tmp_path, monkeypatch):
    monkeypatch.setattr(backup_db, "BACKUP_DIR", tmp_path)
    stamps = ["20260101-0000", "20260102-0000", "20260103-0000", "20260104-0000", "20260105-0000"]
    for stamp in stamps:
        (tmp_path / f"jarvis.{stamp}.db").write_bytes(b"")

    doomed = backup_db.prune("jarvis", keep=2)

    remaining = sorted(p.name for p in tmp_path.glob("jarvis.*.db"))
    assert remaining == ["jarvis.20260104-0000.db", "jarvis.20260105-0000.db"]
    assert len(doomed) == 3
    for d in doomed:
        assert not d.exists()


def test_missing_db_is_skipped_not_failed(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(backup_db, "ROOT", tmp_path)
    monkeypatch.setattr(backup_db, "BACKUP_DIR", tmp_path / "data" / "backups")

    rc = backup_db.main()

    out = capsys.readouterr().out
    assert rc == 0
    assert "skip data/jarvis.db: missing" in out
    assert "skip data/costs.db: missing" in out
