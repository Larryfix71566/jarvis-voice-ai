#!/usr/bin/env python3
"""Restore check for the B4 backups (release-closure item B4). Read-only.

Run by hand in the project venv (it imports jarvis.db for the migration list,
so it is NOT meant for the system Python the nightly job uses):

    .venv/bin/python scripts/restore_check.py [--dest PATH] [--local-only]

Checks the newest backup set in data/backups and, when JARVIS_BACKUP_DEST is
set (or --dest is given), at the off-disk destination: database integrity and
migrations, schema of costs.db, knowledge-base archive safety and document
count, checksums against the manifest, and the vault-key export note. It never
decrypts the secrets vault and never reads the vault key; it prints the
attended commands for that instead. Exit 0 = nothing failed (warnings allowed),
1 = at least one failure or no backups found.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import tarfile
import time
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import backup_db

SUBDIR = {"jarvis-db": "db", "costs-db": "db", "kb": "kb", "vault": "secrets"}


class Report:
    def __init__(self) -> None:
        self.failed = 0
        self.warned = 0

    def ok(self, msg: str) -> None:
        print(f"ok   {msg}")

    def warn(self, msg: str) -> None:
        self.warned += 1
        print(f"WARN {msg}")

    def fail(self, msg: str) -> None:
        self.failed += 1
        print(f"FAIL {msg}")


def _open_ro(path: Path, immutable: bool = True) -> sqlite3.Connection:
    suffix = "?mode=ro&immutable=1" if immutable else "?mode=ro"
    return sqlite3.connect(path.resolve().as_uri() + suffix, uri=True)


def _integrity(path: Path, label: str, rep: Report) -> bool:
    try:
        with closing(_open_ro(path)) as conn:
            result = [r[0] for r in conn.execute("PRAGMA integrity_check")]
    except sqlite3.Error as exc:
        rep.fail(f"{label}: cannot open read-only: {exc}")
        return False
    if result != ["ok"]:
        rep.fail(f"{label}: integrity_check reported {result[:3]}")
        return False
    rep.ok(f"{label}: integrity_check ok")
    return True


def _check_migrations(path: Path, label: str, rep: Report) -> None:
    from jarvis.db import MIGRATIONS

    code = [m for m, _ in MIGRATIONS]
    try:
        with closing(_open_ro(path)) as conn:
            have = [r[0] for r in conn.execute("SELECT id FROM migrations ORDER BY rowid")]
    except sqlite3.Error as exc:
        rep.fail(f"{label}: cannot read migrations table: {exc}")
        return
    unknown = [m for m in have if m not in code]
    if unknown:
        rep.fail(f"{label}: migrations unknown to this code (backup is from a newer version): {unknown[:3]}")
    elif have == code:
        rep.ok(f"{label}: {len(have)} migrations, matches code")
    else:
        missing = [m for m in code if m not in have]
        rep.warn(f"{label}: {len(missing)} migrations behind the code; run_migrations after restore applies them")


def _schema(path: Path, live: Path, label: str, rep: Report) -> None:
    def shape(p: Path, immutable: bool):
        with closing(_open_ro(p, immutable)) as conn:
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            cols = {r[1] for r in conn.execute("PRAGMA table_info(llm_calls)")}
            rows = conn.execute("SELECT COUNT(*) FROM llm_calls").fetchone()[0] if cols else 0
        return tables, cols, rows

    try:
        tables, cols, rows = shape(path, True)
    except sqlite3.Error as exc:
        rep.fail(f"{label}: schema unreadable: {exc}")
        return
    rep.ok(f"{label}: {len(tables)} tables, llm_calls rows {rows}")
    if not live.is_file():
        rep.warn(f"{label}: no live costs.db to compare the schema with")
        return
    try:
        ltables, lcols, _ = shape(live, False)
    except sqlite3.Error as exc:
        rep.warn(f"{label}: live costs.db not comparable: {exc}")
        return
    if ltables - tables or lcols - cols:
        rep.fail(f"{label}: backup lacks tables {sorted(ltables - tables)} / llm_calls columns {sorted(lcols - cols)}")
    else:
        rep.ok(f"{label}: schema covers the live costs.db")


def _count_live_docs(home: Path) -> int:
    base = home / "vault" / "users"
    if not base.is_dir():
        return 0
    return sum(1 for p in base.rglob("*.md") if not (p.name.startswith(".") and p.name.endswith(".tmp")))


def _check_kb(path: Path, documents, label: str, rep: Report) -> None:
    docs = 0
    try:
        with tarfile.open(path, "r:gz") as tar:
            for member in tar:
                name = member.name
                if name.startswith("/") or ".." in Path(name).parts:
                    rep.fail(f"{label}: unsafe member {name!r}")
                    return
                if member.isfile():
                    fh = tar.extractfile(member)
                    while fh is not None and fh.read(1 << 20):
                        pass
                    if name.endswith(".md") and Path(name).parts[:2] == ("vault", "users"):
                        docs += 1
    except (tarfile.TarError, OSError, EOFError) as exc:
        rep.fail(f"{label}: archive unreadable: {type(exc).__name__}: {exc}")
        return
    rep.ok(f"{label}: archive reads cleanly, {docs} documents")
    if documents is not None and docs != documents:
        rep.fail(f"{label}: {docs} documents but the manifest says {documents}")
    live = _count_live_docs(backup_db._kb_home())
    if live > docs:
        rep.warn(f"{label}: live knowledge base has {live} documents, the backup {docs} (newer than the backup?)")


def check_set(label: str, directory: Path, flat: bool, rep: Report) -> None:
    print(f"== {label}: {directory}")
    manifests = sorted(directory.glob("manifest.*.json")) if directory.is_dir() else []
    if not manifests:
        rep.fail(f"no backups found in {directory}")
        return
    manifest_path = manifests[-1]
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        artifacts = manifest["artifacts"]
    except (OSError, ValueError, KeyError) as exc:
        rep.fail(f"{manifest_path.name}: unreadable manifest: {exc}")
        return
    rep.ok(f"newest set {manifest.get('stamp', manifest_path.name)} ({len(artifacts)} artifacts)")
    for art in artifacts:
        kind, name = art.get("kind"), art.get("file", "?")
        path = directory / name if flat else directory / SUBDIR.get(kind, "") / name
        if not path.is_file():
            rep.fail(f"{kind}: {name} is missing")
            continue
        if backup_db._sha256(path) != art.get("sha256"):
            rep.fail(f"{kind}: {name} sha256 differs from the manifest")
            continue
        rep.ok(f"{kind}: {name} sha256 matches the manifest")
        if kind == "jarvis-db":
            if _integrity(path, name, rep):
                _check_migrations(path, name, rep)
        elif kind == "costs-db":
            if _integrity(path, name, rep):
                _schema(path, backup_db.ROOT / "data" / "costs.db", name, rep)
        elif kind == "kb":
            _check_kb(path, art.get("documents"), name, rep)
        elif kind == "vault":
            age_h = int((time.time() - path.stat().st_mtime) // 3600)
            rep.ok(f"vault: {name} present, {age_h} h old (not decrypted)")
            print("     attended decrypt test (run yourself):")
            print(f"       JARVIS_VAULT_PATH={path} .venv/bin/python -m jarvis.vault status")
            print("     to test the exported key instead:")
            print("       read -rs JARVIS_VAULT_KEY && export JARVIS_VAULT_KEY && "
                  f"JARVIS_VAULT_PATH={path} .venv/bin/python -m jarvis.vault status; unset JARVIS_VAULT_KEY")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Read-only check of the newest backup set.")
    ap.add_argument("--dest", help="off-disk destination (default: JARVIS_BACKUP_DEST)")
    ap.add_argument("--local-only", action="store_true", help="check data/backups only")
    args = ap.parse_args([] if argv is None else argv)
    rep = Report()

    check_set("local", backup_db.BACKUP_DIR, True, rep)
    dirs = [backup_db.BACKUP_DIR]

    if args.local_only:
        print("off-disk: skipped (--local-only)")
    else:
        dest, err = (Path(args.dest), None) if args.dest else backup_db._backup_dest()
        if err:
            rep.fail(err)
        elif dest is None:
            print("off-disk: not configured; local backups only")
        elif not dest.is_dir():
            rep.fail(f"off-disk destination does not exist (volume not mounted?): {dest}")
        else:
            base = dest / backup_db.DEST_SUBDIR
            check_set("off-disk", base, False, rep)
            dirs.append(base)

    print(backup_db.key_export_status(dirs))
    print(f"result: {rep.failed} failed, {rep.warned} warnings")
    return 1 if rep.failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
