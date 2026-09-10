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


def test_failed_retry_preserves_existing_backup_and_removes_staging(tmp_path, monkeypatch):
    import pytest

    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    monkeypatch.setattr(backup_db, "BACKUP_DIR", backup_dir)
    src = tmp_path / "jarvis.db"
    _make_db(src, ["original"])
    dst = backup_db.backup_one(src, "20260101-0300")
    original = dst.read_bytes()
    src.write_bytes(b"not a sqlite database")
    with pytest.raises(sqlite3.DatabaseError):
        backup_db.backup_one(src, "20260101-0300")
    assert dst.read_bytes() == original
    assert list(backup_dir.iterdir()) == [dst]


def test_backup_missing_source_does_not_create_empty_database(tmp_path, monkeypatch):
    import pytest

    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    monkeypatch.setattr(backup_db, "BACKUP_DIR", backup_dir)
    src = tmp_path / "missing.db"
    with pytest.raises(sqlite3.OperationalError):
        backup_db.backup_one(src, "20260101-0300")
    assert not src.exists()
    assert list(backup_dir.iterdir()) == []


def test_backup_includes_committed_wal_rows(tmp_path, monkeypatch):
    from contextlib import closing

    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    monkeypatch.setattr(backup_db, "BACKUP_DIR", backup_dir)
    src = tmp_path / "jarvis.db"
    with closing(sqlite3.connect(src)) as writer:
        assert writer.execute("PRAGMA journal_mode=WAL").fetchone() == ("wal",)
        writer.execute("PRAGMA wal_autocheckpoint=0")
        writer.execute("CREATE TABLE t (v TEXT)")
        writer.execute("INSERT INTO t VALUES ('committed in WAL')")
        writer.commit()
        assert src.with_name(src.name + "-wal").stat().st_size > 0
        dst = backup_db.backup_one(src, "20260101-0300")
        with closing(sqlite3.connect(dst)) as reader:
            assert reader.execute("SELECT v FROM t").fetchall() == [("committed in WAL",)]
            assert reader.execute("PRAGMA quick_check").fetchall() == [("ok",)]


def test_failed_backup_returns_failure_without_pruning(tmp_path, monkeypatch):
    monkeypatch.setattr(backup_db, "ROOT", tmp_path)
    monkeypatch.setattr(backup_db, "DBS", ("data/jarvis.db",))
    backup_dir = tmp_path / "data" / "backups"
    backup_dir.mkdir(parents=True)
    monkeypatch.setattr(backup_db, "BACKUP_DIR", backup_dir)
    monkeypatch.setattr(backup_db, "BACKUP_KEEP", 1)
    (tmp_path / "data" / "jarvis.db").write_bytes(b"corrupt")
    earlier = [backup_dir / f"jarvis.2026010{i}-0300.db" for i in (1, 2)]
    for path in earlier:
        _make_db(path, ["saved"])
    assert backup_db.main() == 1
    assert sorted(backup_dir.iterdir()) == earlier
