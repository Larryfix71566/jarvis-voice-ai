"""Unit tests for scripts/restore_check.py (release-closure item B4).

Each test builds a real backup set with scripts/backup_db.py against a fake
repo, then runs the restore check over it."""
from __future__ import annotations

import io
import json
import sqlite3
import tarfile
from contextlib import closing
from pathlib import Path

import pytest

from jarvis import db as jarvis_db
from scripts import backup_db, restore_check


def _costs(path: Path, extra_col: bool = False) -> None:
    with closing(sqlite3.connect(path)) as c:
        c.execute("CREATE TABLE llm_calls (id INTEGER PRIMARY KEY, ts TEXT, model TEXT)")
        c.execute("INSERT INTO llm_calls (ts, model) VALUES ('t', 'm')")
        c.commit()


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.delenv("JARVIS_BACKUP_DEST", raising=False)
    root = tmp_path / "repo"
    (root / "data").mkdir(parents=True)
    monkeypatch.setattr(backup_db, "ROOT", root)
    monkeypatch.setattr(backup_db, "BACKUP_DIR", root / "data" / "backups")
    with closing(sqlite3.connect(root / "data" / "jarvis.db")) as conn:
        conn.row_factory = sqlite3.Row
        jarvis_db.run_migrations(conn)
    _costs(root / "data" / "costs.db")
    (root / "data" / "secrets.vault").write_bytes(b'{"ciphertext": "AAAA"}')
    home = tmp_path / "kbhome"
    for rel in ("vault/users/u/areas/a.md", "vault/users/u/sessions/b.md", "config/retrieval.yaml"):
        f = home / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("x")
    monkeypatch.setenv("MORTIMER_HOME", str(home))
    dest = tmp_path / "vol"
    dest.mkdir()
    monkeypatch.setenv("JARVIS_BACKUP_DEST", str(dest))
    assert backup_db.main([]) == 0
    return type("W", (), {"root": root, "home": home, "dest": dest, "local": root / "data" / "backups",
                          "remote": dest / "mortimer-backup"})


def _run(capsys, argv=None):
    rc = restore_check.main(argv)
    return rc, capsys.readouterr().out


def _resign(directory: Path, kind: str) -> None:
    """Re-record a changed artifact's sha256 in that directory's manifest."""
    mpath = max(directory.glob("manifest.*.json"))
    manifest = json.loads(mpath.read_text())
    for art in manifest["artifacts"]:
        if art["kind"] == kind:
            sub = {"jarvis-db": "db", "costs-db": "db", "kb": "kb", "vault": "secrets"}[kind]
            f = directory / art["file"]
            if not f.exists():
                f = directory / sub / art["file"]
            art["sha256"] = backup_db._sha256(f)
    mpath.write_text(json.dumps(manifest))


def _file(directory: Path, pattern: str) -> Path:
    found = list(directory.rglob(pattern))
    assert found
    return found[0]


def test_good_set_passes_everywhere(world, capsys):
    rc, out = _run(capsys)
    assert rc == 0, out
    assert "FAIL" not in out and "WARN" not in out.replace("WARN vault", "")
    assert out.count("== ") == 2
    assert "result: 0 failed" in out


def test_corrupted_db_fails_integrity_and_checksum(world, capsys):
    target = _file(world.local, "jarvis.*.db")
    data = bytearray(target.read_bytes())
    for i in range(4096, min(len(data), 8192)):
        data[i] = 0xFF
    target.write_bytes(bytes(data))
    rc, out = _run(capsys, ["--local-only"])
    assert rc == 1 and "sha256 differs" in out


def test_corrupted_db_with_matching_sha_still_fails_integrity(world, capsys):
    target = _file(world.local, "jarvis.*.db")
    data = bytearray(target.read_bytes())
    for i in range(4096, min(len(data), 16384)):
        data[i] = 0xFF
    target.write_bytes(bytes(data))
    _resign(world.local, "jarvis-db")
    rc, out = _run(capsys, ["--local-only"])
    assert rc == 1 and "FAIL" in out and ("integrity" in out or "cannot" in out)


def test_sha_mismatch_against_manifest_fails(world, capsys):
    _file(world.remote, "secrets.*.vault").write_bytes(b"tampered")
    rc, out = _run(capsys)
    assert rc == 1 and "sha256 differs" in out


def test_one_migration_behind_warns_and_unknown_fails(world, capsys):
    target = _file(world.local, "jarvis.*.db")
    with closing(sqlite3.connect(target)) as c:
        last = c.execute("SELECT id FROM migrations ORDER BY rowid DESC LIMIT 1").fetchone()[0]
        c.execute("DELETE FROM migrations WHERE id = ?", (last,))
        c.commit()
    _resign(world.local, "jarvis-db")
    rc, out = _run(capsys, ["--local-only"])
    assert rc == 0 and "1 migrations behind" in out
    with closing(sqlite3.connect(target)) as c:
        c.execute("INSERT INTO migrations (id, applied_at) VALUES ('9999_future', 'x')")
        c.commit()
    _resign(world.local, "jarvis-db")
    rc, out = _run(capsys, ["--local-only"])
    assert rc == 1 and "unknown to this code" in out


def test_costs_backup_missing_live_column_fails(world, capsys):
    with closing(sqlite3.connect(world.root / "data" / "costs.db")) as c:
        c.execute("ALTER TABLE llm_calls ADD COLUMN cache_tokens INTEGER")
        c.commit()
    rc, out = _run(capsys, ["--local-only"])
    assert rc == 1 and "cache_tokens" in out


def _swap_kb(directory: Path, members) -> None:
    target = _file(directory, "kb-vault.*.tar.gz")
    with tarfile.open(target, "w:gz") as tar:
        for name in members:
            info = tarfile.TarInfo(name)
            info.size = 1
            tar.addfile(info, io.BytesIO(b"x"))
    _resign(directory, "kb")


@pytest.mark.parametrize("bad", ["../x", "/etc/x"])
def test_kb_archive_with_unsafe_member_fails(world, capsys, bad):
    _swap_kb(world.local, ["vault/users/u/a.md", bad])
    rc, out = _run(capsys, ["--local-only"])
    assert rc == 1 and "unsafe member" in out


def test_kb_document_count_below_manifest_fails_and_below_live_warns(world, capsys):
    mpath = max(world.local.glob("manifest.*.json"))
    manifest = json.loads(mpath.read_text())
    for art in manifest["artifacts"]:
        if art["kind"] == "kb":
            art["documents"] = 99
    mpath.write_text(json.dumps(manifest))
    rc, out = _run(capsys, ["--local-only"])
    assert rc == 1 and "manifest says 99" in out
    # restore the manifest, add a live document the backup does not have
    for art in manifest["artifacts"]:
        if art["kind"] == "kb":
            art["documents"] = 2
    mpath.write_text(json.dumps(manifest))
    (world.home / "vault/users/u/areas/new.md").write_text("n")
    rc, out = _run(capsys, ["--local-only"])
    assert rc == 0 and "live knowledge base has 3 documents" in out


def test_no_backups_found_fails(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("JARVIS_BACKUP_DEST", raising=False)
    monkeypatch.setattr(backup_db, "ROOT", tmp_path)
    monkeypatch.setattr(backup_db, "BACKUP_DIR", tmp_path / "data" / "backups")
    rc, out = _run(capsys)
    assert rc == 1 and "no backups found in" in out


def test_check_is_read_only(world, capsys):
    paths = [p for p in list(world.local.glob("*.db")) + list(world.remote.rglob("*.db"))]
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in paths}
    rc, _ = _run(capsys)
    assert rc == 0
    for p, (data, mtime) in before.items():
        assert (p.read_bytes(), p.stat().st_mtime_ns) == (data, mtime)
    assert not list(world.local.glob("*-wal")) + list(world.local.glob("*-shm"))
    assert not list(world.remote.rglob("*-wal")) + list(world.remote.rglob("*-shm"))


def test_dest_not_configured_checks_local_only(world, monkeypatch, capsys):
    monkeypatch.delenv("JARVIS_BACKUP_DEST")
    rc, out = _run(capsys)
    assert rc == 0 and "off-disk: not configured" in out and out.count("== ") == 1


def test_missing_dest_volume_fails(world, tmp_path, capsys):
    rc, out = _run(capsys, ["--dest", str(tmp_path / "gone")])
    assert rc == 1 and "does not exist" in out


def test_vault_check_never_decrypts(world, monkeypatch, capsys):
    from jarvis import vault

    def boom(*a, **k):
        raise AssertionError("restore_check must not load the vault key")

    monkeypatch.setattr(vault, "_load_key", boom)
    monkeypatch.setattr(vault, "_decrypt", boom)
    rc, out = _run(capsys)
    assert rc == 0
    assert "not decrypted" in out and "jarvis.vault status" in out
