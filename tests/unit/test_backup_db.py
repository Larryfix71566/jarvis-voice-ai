"""Unit tests for scripts/backup_db.py (gap-closure plan GC7). stdlib
sqlite3.Connection.backup is WAL-safe; these tests exercise the actual
backup_one/prune/main functions rather than mocking sqlite out."""
from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import sqlite3
import tarfile
from pathlib import Path

import pytest

from scripts import backup_db


@pytest.fixture(autouse=True)
def _isolate_backup_env(tmp_path, monkeypatch):
    """B4: main() now reads JARVIS_BACKUP_DEST / MORTIMER_HOME; keep the real
    machine's values out of every test."""
    monkeypatch.delenv("JARVIS_BACKUP_DEST", raising=False)
    monkeypatch.setenv("MORTIMER_HOME", str(tmp_path / "no-such-kb-home"))


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


# ---------------------------------------------------------------- B4 tests
SENTINEL_KEY = "c2VudGluZWwta2V5LW1hdGVyaWFsLTMyYnl0ZXMhISE="


def _repo(tmp_path, monkeypatch, *, vault=True, kb=False):
    root = tmp_path / "repo"
    (root / "data").mkdir(parents=True)
    monkeypatch.setattr(backup_db, "ROOT", root)
    monkeypatch.setattr(backup_db, "BACKUP_DIR", root / "data" / "backups")
    _make_db(root / "data" / "jarvis.db", ["a"])
    conn = sqlite3.connect(root / "data" / "jarvis.db")
    conn.execute("CREATE TABLE migrations (id TEXT PRIMARY KEY, applied_at TEXT)")
    conn.execute("INSERT INTO migrations VALUES ('0001_init', 'x')")
    conn.commit()
    conn.close()
    _make_db(root / "data" / "costs.db", ["c"])
    if vault:
        (root / "data" / "secrets.vault").write_bytes(b'{"ciphertext": "AAAA"}')
    if kb:
        home = tmp_path / "kbhome"
        files = {
            "vault/users/u/areas/a.md": "A",
            "vault/users/u/sessions/b.md": "B",
            "vault/.git/HEAD": "ref: refs/heads/main",
            "vault/users/u/areas/.c.md.tmp": "partial",
            "index/vault.db": "derived",
            "logs/vault.log": "log",
            "config/retrieval.yaml": "k: v",
        }
        for rel, data in files.items():
            f = home / rel
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(data)
        monkeypatch.setenv("MORTIMER_HOME", str(home))
    return root


def _run(capsys, argv=None):
    rc = backup_db.main(argv)
    cap = capsys.readouterr()
    return rc, cap.out + cap.err


def _sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def test_dest_unset_reports_not_configured_and_writes_only_local(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path, monkeypatch)
    rc, out = _run(capsys)
    assert rc == 0
    assert "off-disk: not configured" in out
    outside = [p for p in tmp_path.rglob("*") if p.is_file() and root not in p.parents]
    assert outside == []


def test_dest_set_copies_verified_with_private_modes_and_manifest(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path, monkeypatch)
    dest = tmp_path / "vol"
    dest.mkdir()
    monkeypatch.setenv("JARVIS_BACKUP_DEST", str(dest))
    rc, out = _run(capsys)
    assert rc == 0, out
    base = dest / "mortimer-backup"
    copies = list((base / "db").glob("jarvis.*.db"))
    assert len(copies) == 1
    local = next((root / "data" / "backups").glob("jarvis.*.db"))
    assert _sha(copies[0]) == _sha(local)
    manifest = json.loads(next(base.glob("manifest.*.json")).read_text())
    names = {a["file"]: a for a in manifest["artifacts"]}
    assert copies[0].name in names and names[copies[0].name]["sha256"] == _sha(local)
    assert names[copies[0].name]["migrations"] == ["0001_init"]
    for d in (base, base / "db", base / "secrets"):
        assert (d.stat().st_mode & 0o777) == 0o700
    for f in base.rglob("*"):
        if f.is_file():
            assert (f.stat().st_mode & 0o777) == 0o600


def test_missing_dest_fails_without_creating_it_and_keeps_local(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path, monkeypatch)
    dest = tmp_path / "not-mounted"
    monkeypatch.setenv("JARVIS_BACKUP_DEST", str(dest))
    rc, out = _run(capsys)
    assert rc == 1
    assert "FAILED off-disk" in out
    assert not dest.exists()
    assert list((root / "data" / "backups").glob("jarvis.*.db"))


def test_dest_read_from_dotenv_env_wins_and_other_values_stay_out(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path, monkeypatch)
    (tmp_path / "from_env").mkdir()
    (tmp_path / "from_dotenv").mkdir()
    (root / ".env").write_text(
        "# comment\nOPENAI_API_KEY=sk-secret-value\n"
        f'JARVIS_BACKUP_DEST="{tmp_path / "from_dotenv"}"  \nOTHER=1\n')
    rc, out = _run(capsys)
    assert rc == 0 and (tmp_path / "from_dotenv" / "mortimer-backup").is_dir()
    assert "sk-secret-value" not in out
    monkeypatch.setenv("JARVIS_BACKUP_DEST", str(tmp_path / "from_env"))
    rc, out = _run(capsys)
    assert (tmp_path / "from_env" / "mortimer-backup").is_dir()


@pytest.mark.parametrize("where", ["relative/path", "ROOT", "ROOT/data"])
def test_unsafe_dest_is_refused(tmp_path, monkeypatch, capsys, where):
    root = _repo(tmp_path, monkeypatch)
    value = where.replace("ROOT", str(root)) if where.startswith("ROOT") else where
    monkeypatch.setenv("JARVIS_BACKUP_DEST", value)
    rc, out = _run(capsys)
    assert rc == 1
    assert "FAILED off-disk" in out and "JARVIS_BACKUP_DEST" in out
    assert not (root / "mortimer-backup").exists()


def test_dest_pruning_keeps_fourteen_per_kind(tmp_path, monkeypatch, capsys):
    _repo(tmp_path, monkeypatch, kb=True)
    dest = tmp_path / "vol"
    base = dest / "mortimer-backup"
    seeds = (("db", "jarvis.{}.db"), ("db", "costs.{}.db"),
             ("kb", "kb-vault.{}.tar.gz"), ("secrets", "secrets.{}.vault"))
    for sub, name in seeds:
        (base / sub).mkdir(parents=True, exist_ok=True)
        for i in range(16):
            (base / sub / name.format(f"2025010{i // 10}-{i % 10:04d}")).write_bytes(b"x")
    for i in range(16):
        (base / f"manifest.2025010{i // 10}-{i % 10:04d}.json").write_text("{}")
    monkeypatch.setenv("JARVIS_BACKUP_DEST", str(dest))
    rc, out = _run(capsys)
    assert rc == 0, out
    assert len(list((base / "db").glob("jarvis.*.db"))) == 14
    assert len(list((base / "db").glob("costs.*.db"))) == 14
    assert len(list((base / "kb").glob("kb-vault.*.tar.gz"))) == 14
    assert len(list((base / "secrets").glob("secrets.*.vault"))) == 14
    assert len(list(base.glob("manifest.*.json"))) == 14


def test_kb_archive_contents_and_document_count(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path, monkeypatch, kb=True)
    rc, _ = _run(capsys)
    assert rc == 0
    archive = next((root / "data" / "backups").glob("kb-vault.*.tar.gz"))
    with tarfile.open(archive) as tar:
        names = set(tar.getnames())
    wanted = {"vault/users/u/areas/a.md", "vault/users/u/sessions/b.md",
              "vault/.git/HEAD", "config/retrieval.yaml"}
    assert wanted <= names
    assert not any(n.startswith(("index", "logs")) or n.endswith(".tmp") for n in names)
    manifest = json.loads(next((root / "data" / "backups").glob("manifest.*.json")).read_text())
    assert next(a for a in manifest["artifacts"] if a["kind"] == "kb")["documents"] == 2


def test_missing_kb_home_is_skipped_not_failed(tmp_path, monkeypatch, capsys):
    _repo(tmp_path, monkeypatch)
    rc, out = _run(capsys)
    assert rc == 0 and "skip kb: missing" in out


def test_encrypted_vault_copied_byte_identical_to_both_places(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path, monkeypatch)
    dest = tmp_path / "vol"
    dest.mkdir()
    monkeypatch.setenv("JARVIS_BACKUP_DEST", str(dest))
    rc, _ = _run(capsys)
    assert rc == 0
    original = (root / "data" / "secrets.vault").read_bytes()
    local = next((root / "data" / "backups").glob("secrets.*.vault"))
    remote = next((dest / "mortimer-backup" / "secrets").glob("secrets.*.vault"))
    assert local.read_bytes() == original and remote.read_bytes() == original


def test_no_key_material_is_written_anywhere(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path, monkeypatch, kb=True)
    dest = tmp_path / "vol"
    dest.mkdir()
    monkeypatch.setenv("JARVIS_BACKUP_DEST", str(dest))
    monkeypatch.setenv("JARVIS_VAULT_KEY", SENTINEL_KEY)
    rc, out = _run(capsys)
    assert rc == 0
    assert SENTINEL_KEY not in out
    for base in (root / "data" / "backups", dest):
        for f in base.rglob("*"):
            if f.is_file():
                assert SENTINEL_KEY.encode() not in f.read_bytes()


def test_source_never_touches_key_machinery():
    src = Path(backup_db.__file__).read_text()
    for banned in ("JARVIS_VAULT_KEY", "keyring", "cryptography", "import jarvis", "from jarvis",
                   "subprocess"):
        assert banned not in src, banned


def test_record_key_export_writes_note_and_status_reports_it(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path, monkeypatch)
    rc, out = _run(capsys)
    assert "NOT RECORDED" in out
    rc, out = _run(capsys, ["--record-key-export", "1Password"])
    assert rc == 0
    rec = json.loads((root / "data" / "backups" / "vault-key-export.json").read_text())
    assert set(rec) == {"recorded_at", "stored_in"} and rec["stored_in"] == "1Password"
    rc, out = _run(capsys)
    assert re.search(r'recorded \d{4}-\d\d-\d\d \(0 days ago\), stored in "1Password"', out)


def test_record_key_export_refuses_key_shaped_value(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path, monkeypatch)
    rc, _ = _run(capsys, ["--record-key-export", SENTINEL_KEY])
    assert rc == 2
    assert not (root / "data" / "backups" / "vault-key-export.json").exists()


def test_key_file_next_to_backup_triggers_warning(tmp_path, monkeypatch, capsys):
    _repo(tmp_path, monkeypatch)
    dest = tmp_path / "vol"
    dest.mkdir()
    (dest / "vault-key.txt").write_text("oops")
    monkeypatch.setenv("JARVIS_BACKUP_DEST", str(dest))
    _rc, out = _run(capsys)
    assert "vault-key.txt" in out and "warning" in out


def test_offdisk_copy_failure_keeps_local_and_leaves_no_temp_files(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path, monkeypatch)
    dest = tmp_path / "vol"
    dest.mkdir()
    monkeypatch.setenv("JARVIS_BACKUP_DEST", str(dest))
    real_replace = os.replace

    def flaky(src, dst, *a, **k):
        if str(dest) in str(dst):
            raise OSError("disk full")
        return real_replace(src, dst, *a, **k)

    monkeypatch.setattr(os, "replace", flaky)
    rc, out = _run(capsys)
    assert rc == 1 and "FAILED off-disk" in out
    assert list((root / "data" / "backups").glob("jarvis.*.db"))
    assert not [p for p in dest.rglob("*") if p.is_file() and p.name.endswith(".tmp")]


def test_source_is_python39_compatible():
    src = Path(backup_db.__file__).read_text()
    ast.parse(src, feature_version=(3, 9))
    for banned in ("file_digest", "datetime.UTC", "filter="):
        assert banned not in src, banned
