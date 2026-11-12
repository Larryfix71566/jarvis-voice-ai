#!/usr/bin/env python3
"""Nightly backups (gap-closure plan GC7; release-closure item B4).

Local snapshots land in data/backups; when JARVIS_BACKUP_DEST names an existing
directory they are also copied off-disk and verified by sha256.

Artifacts: both SQLite databases (WAL-safe via sqlite3.Connection.backup), the
knowledge-base documents (tar.gz of MORTIMER_HOME vault/ and config/), the
ENCRYPTED secrets vault (ciphertext only) and a manifest.

Rules that keep this safe under macOS /usr/bin/python3 (3.9):
  * stdlib only, no 3.10+ syntax or APIs;
  * it never touches key material: it does not import the secrets-vault module
    or any crypto/keychain library and never reads the vault key from the
    environment. The key is exported by hand; --record-key-export only stores a
    note saying WHERE the human put it.
"""
from __future__ import annotations

import argparse
import datetime
import fnmatch
import hashlib
import json
import os
import re
import shutil
import sqlite3
import sys
import tarfile
import tempfile
import time
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DBS = ("data/jarvis.db", "data/costs.db")
BACKUP_DIR = ROOT / "data" / "backups"
BACKUP_KEEP = 14          # §6
DEST_SUBDIR = "mortimer-backup"
KB_HOME_DEFAULT = Path.home() / "Mortimer"
VAULT_REL = "data/secrets.vault"
KEY_RECORD = "vault-key-export.json"
# artifact kind -> (sub-directory under DEST/mortimer-backup, prune stem, suffix)
KINDS = {
    "jarvis-db": ("db", "jarvis", ".db"),
    "costs-db": ("db", "costs", ".db"),
    "kb": ("kb", "kb-vault", ".tar.gz"),
    "vault": ("secrets", "secrets", ".vault"),
}
_KEYLIKE = re.compile(r"^[A-Za-z0-9+/]{43}=$")


# --------------------------------------------------------------- primitives
def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _env_file_value(name: str):
    """One key from ROOT/.env (strict KEY=value lines); nothing else is read out."""
    try:
        text = (ROOT / ".env").read_text(encoding="utf-8")
    except OSError:
        return None
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, sep, val = line.partition("=")
        if not sep or key.strip() != name:
            continue
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        else:
            val = re.split(r"\s+#", val, maxsplit=1)[0].strip()
        return val or None
    return None


def _setting(name: str):
    val = os.environ.get(name)
    if val and val.strip():
        return val.strip()
    return _env_file_value(name)


def _kb_home() -> Path:
    val = _setting("MORTIMER_HOME")
    return Path(val) if val else KB_HOME_DEFAULT


def _backup_dest():
    """(path, error). path None + error None = not configured. Never creates it."""
    val = _setting("JARVIS_BACKUP_DEST")
    if not val:
        return None, None
    dest = Path(val)
    if not dest.is_absolute():
        return None, f"JARVIS_BACKUP_DEST must be an absolute path, got {val!r}"
    resolved = dest.resolve()
    root = ROOT.resolve()
    if resolved == root or root in resolved.parents:
        return None, "JARVIS_BACKUP_DEST is inside the repository (or data/); choose another volume"
    return dest, None


def _private_dir(path: Path) -> None:
    os.makedirs(path, mode=0o700, exist_ok=True)
    os.chmod(path, 0o700)


def _atomic_write(path: Path, data: bytes) -> None:
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _copy_verified(src: Path, dst_dir: Path) -> Path:
    """Copy via temp file + fsync + replace, then compare sha256 with the source."""
    _private_dir(dst_dir)
    dst = dst_dir / src.name
    fd, tmp = tempfile.mkstemp(prefix=f".{src.name}.", suffix=".tmp", dir=dst_dir)
    try:
        with os.fdopen(fd, "wb") as out, open(src, "rb") as inp:
            shutil.copyfileobj(inp, out, 1 << 20)
            out.flush()
            os.fsync(out.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, dst)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    if _sha256(dst) != _sha256(src):
        dst.unlink()
        raise OSError(f"checksum mismatch after copying {src.name}")
    return dst


# ------------------------------------------------------------------ backups
def backup_one(src: Path, stamp: str) -> Path:
    dst = BACKUP_DIR / f"{src.stem}.{stamp}.db"
    # Publish only a complete, checked snapshot. A failed same-minute retry
    # must leave the preceding good backup intact.
    fd, temporary = tempfile.mkstemp(prefix=f".{dst.name}.", suffix=".tmp", dir=BACKUP_DIR)
    os.close(fd)
    staging = Path(temporary)
    try:
        with closing(sqlite3.connect(src.resolve().as_uri() + "?mode=ro", uri=True)) as s:
            with closing(sqlite3.connect(staging)) as d:
                s.backup(d)
                if d.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
                    raise sqlite3.DatabaseError("backup integrity check failed")
        os.replace(staging, dst)
    finally:
        staging.unlink(missing_ok=True)
    return dst


def prune(stem: str, keep: int, directory=None, suffix: str = ".db") -> list[Path]:
    directory = BACKUP_DIR if directory is None else Path(directory)
    files = sorted(directory.glob(f"{stem}.*{suffix}"))
    doomed = files[:-keep] if len(files) > keep else []
    for f in doomed:
        f.unlink()
    return doomed


def _migration_ids(db: Path) -> list:
    try:
        with closing(sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True)) as c:
            return [r[0] for r in c.execute("SELECT id FROM migrations ORDER BY rowid")]
    except sqlite3.Error:
        return []


def _artifact(kind: str, path: Path, **extra) -> dict:
    rec = {"kind": kind, "file": path.name, "bytes": path.stat().st_size,
           "sha256": _sha256(path), "path": path}
    rec.update(extra)
    return rec


def backup_kb(home: Path, stamp: str):
    """tar.gz of home/vault and home/config. Returns (archive, documents) or None."""
    if not (home / "vault").is_dir():
        return None
    dst = BACKUP_DIR / f"kb-vault.{stamp}.tar.gz"
    fd, tmp = tempfile.mkstemp(prefix=f".{dst.name}.", suffix=".tmp", dir=BACKUP_DIR)
    os.close(fd)
    documents = 0
    try:
        with tarfile.open(tmp, "w:gz") as tar:
            for top in ("vault", "config"):
                base = home / top
                if not base.is_dir():
                    continue
                tar.add(base, arcname=top, recursive=False)
                for cur, dirs, files in os.walk(base):
                    rel = Path(cur).relative_to(home)
                    dirs.sort()
                    for d in dirs:  # symlinked dirs are stored as links, not followed
                        tar.add(os.path.join(cur, d), arcname=str(rel / d), recursive=False)
                    for name in sorted(files):
                        if name.startswith(".") and name.endswith(".tmp"):
                            continue  # in-flight atomic write
                        tar.add(os.path.join(cur, name), arcname=str(rel / name), recursive=False)
                        if name.endswith(".md") and rel.parts[:2] == ("vault", "users"):
                            documents += 1
        os.replace(tmp, dst)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return dst, documents


def backup_vault_file(stamp: str):
    """Byte copy of the ENCRYPTED vault. Returns the copy or None if absent."""
    src = ROOT / VAULT_REL
    if not src.is_file():
        return None
    dst = BACKUP_DIR / f"secrets.{stamp}.vault"
    fd, tmp = tempfile.mkstemp(prefix=f".{dst.name}.", suffix=".tmp", dir=BACKUP_DIR)
    os.close(fd)
    try:
        shutil.copyfile(src, tmp)
        os.chmod(tmp, 0o600)
        os.replace(tmp, dst)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return dst


def write_manifest(directory: Path, stamp: str, artifacts: list) -> Path:
    body = {
        "stamp": stamp,
        "created_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "artifacts": [{k: v for k, v in a.items() if k != "path"} for a in artifacts],
    }
    out = directory / f"manifest.{stamp}.json"
    _atomic_write(out, (json.dumps(body, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    return out


# ------------------------------------------------------------- vault-key note
def _read_record(directory: Path):
    try:
        return json.loads((directory / KEY_RECORD).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def key_export_status(dirs) -> str:
    best = None
    for d in dirs:
        rec = _read_record(Path(d))
        if (isinstance(rec, dict) and rec.get("recorded_at")
                and (best is None or str(rec["recorded_at"]) > str(best["recorded_at"]))):
            best = rec
    if best is None:
        return ("vault key export: NOT RECORDED - run `python -m jarvis.vault export-key` by hand, "
                "store the output somewhere other than this Mac and the backup volume, "
                "then run `python3 scripts/backup_db.py --record-key-export \"<where>\"`")
    try:
        when = datetime.datetime.fromisoformat(str(best["recorded_at"]))
        if when.tzinfo is None:
            when = when.astimezone()
        ago = f"{(datetime.datetime.now().astimezone() - when).days} days ago"
    except ValueError:
        ago = "date unreadable"
    return (f"vault key export: recorded {str(best['recorded_at'])[:10]} ({ago}), "
            f"stored in \"{best.get('stored_in', '?')}\"")


def record_key_export(where: str) -> int:
    where = where.strip()
    if not where or _KEYLIKE.match(where) or len(where) > 80:
        print("refused: that does not look like a location note (looks like a key, or is empty/too long). "
              "Pass where the key is stored, e.g. \"1Password\".", file=sys.stderr)
        return 2
    rec = {"recorded_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
           "stored_in": where}
    data = (json.dumps(rec, indent=2) + "\n").encode("utf-8")
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    _atomic_write(BACKUP_DIR / KEY_RECORD, data)
    print(f"recorded vault key export note -> {BACKUP_DIR / KEY_RECORD}")
    dest, _err = _backup_dest()
    if dest is not None and dest.is_dir():
        _private_dir(dest / DEST_SUBDIR)
        _atomic_write(dest / DEST_SUBDIR / KEY_RECORD, data)
        print(f"recorded vault key export note -> {dest / DEST_SUBDIR / KEY_RECORD}")
    return 0


def _stray_key_files(dest: Path) -> list:
    found = []
    for d in (dest, dest / DEST_SUBDIR):
        if not d.is_dir():
            continue
        for p in sorted(d.iterdir()):
            n = p.name.lower()
            if n == KEY_RECORD:
                continue
            if fnmatch.fnmatch(n, "*vault-key*") or fnmatch.fnmatch(n, "*.key"):
                found.append(p)
    return found


# ----------------------------------------------------------------- off-disk
def offdisk(dest: Path, artifacts: list, stamp: str) -> bool:
    if not dest.is_dir():
        print(f"FAILED off-disk: destination does not exist (volume not mounted?): {dest}", file=sys.stderr)
        return False
    ok = True
    try:
        if os.stat(dest).st_dev == os.stat(ROOT).st_dev:
            print("warning: off-disk destination is on the same volume as data/ - it protects against "
                  "deletion, not disk loss, unless that folder syncs elsewhere")
    except OSError:
        pass
    base = dest / DEST_SUBDIR
    copied = []
    try:
        _private_dir(base)
    except OSError as exc:
        print(f"FAILED off-disk: {type(exc).__name__}: {exc}", file=sys.stderr)
        return False
    for art in artifacts:
        sub, stem, suffix = KINDS[art["kind"]]
        try:
            _copy_verified(art["path"], base / sub)
            prune(stem, BACKUP_KEEP, base / sub, suffix)
            copied.append(art)
        except Exception as exc:  # noqa: BLE001
            print(f"FAILED off-disk {art['file']}: {type(exc).__name__}: {exc}", file=sys.stderr)
            ok = False
    if copied:
        try:
            write_manifest(base, stamp, copied)
            prune("manifest", BACKUP_KEEP, base, ".json")
        except Exception as exc:  # noqa: BLE001
            print(f"FAILED off-disk manifest: {type(exc).__name__}: {exc}", file=sys.stderr)
            ok = False
    if ok:
        print(f"ok off-disk -> {base} ({len(copied)} files, verified)")
    for stray in _stray_key_files(dest):
        print(f"warning: {stray} looks like a vault key stored next to the backup; "
              "a key beside its ciphertext defeats the encryption - move it elsewhere")
    return ok


# --------------------------------------------------------------------- main
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Back up databases, knowledge base and encrypted vault.")
    ap.add_argument("--record-key-export", metavar="WHERE",
                    help="record WHERE you stored the hand-exported vault key (never the key itself)")
    args = ap.parse_args([] if argv is None else argv)
    if args.record_key_export is not None:
        return record_key_export(args.record_key_export)

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M")
    rc = 0
    artifacts = []
    for rel in DBS:
        src = ROOT / rel
        if not src.exists():
            print(f"skip {rel}: missing"); continue
        try:
            dst = backup_one(src, stamp)
            gone = prune(src.stem, BACKUP_KEEP)
            print(f"ok {rel} -> {dst.relative_to(ROOT)} (pruned {len(gone)})")
            if src.stem == "jarvis":
                artifacts.append(_artifact("jarvis-db", dst, migrations=_migration_ids(dst)))
            else:
                artifacts.append(_artifact("costs-db", dst))
        except Exception as exc:  # noqa: BLE001
            print(f"FAILED {rel}: {type(exc).__name__}: {exc}", file=sys.stderr); rc = 1

    try:
        kb = backup_kb(_kb_home(), stamp)
        if kb is None:
            print("skip kb: missing")
        else:
            gone = prune("kb-vault", BACKUP_KEEP, suffix=".tar.gz")
            print(f"ok kb -> {kb[0].name} ({kb[1]} documents, pruned {len(gone)})")
            artifacts.append(_artifact("kb", kb[0], documents=kb[1]))
    except Exception as exc:  # noqa: BLE001
        print(f"FAILED kb: {type(exc).__name__}: {exc}", file=sys.stderr); rc = 1

    try:
        vf = backup_vault_file(stamp)
        if vf is None:
            print(f"skip {VAULT_REL}: missing")
        else:
            gone = prune("secrets", BACKUP_KEEP, suffix=".vault")
            print(f"ok {VAULT_REL} (encrypted, ciphertext only) -> {vf.name} (pruned {len(gone)})")
            artifacts.append(_artifact("vault", vf))
    except Exception as exc:  # noqa: BLE001
        print(f"FAILED {VAULT_REL}: {type(exc).__name__}: {exc}", file=sys.stderr); rc = 1

    if artifacts:
        try:
            write_manifest(BACKUP_DIR, stamp, artifacts)
            prune("manifest", BACKUP_KEEP, suffix=".json")
        except Exception as exc:  # noqa: BLE001
            print(f"FAILED manifest: {type(exc).__name__}: {exc}", file=sys.stderr); rc = 1

    dest, err = _backup_dest()
    status_dirs = [BACKUP_DIR]
    if err:
        print(f"FAILED off-disk: {err}", file=sys.stderr); rc = 1
    elif dest is None:
        print("off-disk: not configured (set JARVIS_BACKUP_DEST to an existing directory on another volume)")
    else:
        if not offdisk(dest, artifacts, stamp):
            rc = 1
        status_dirs.append(dest / DEST_SUBDIR)

    print(key_export_status(status_dirs))
    print("reminder: the vault key is NOT backed up here — run `python -m jarvis.vault export-key` once and store it off-machine.")
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
