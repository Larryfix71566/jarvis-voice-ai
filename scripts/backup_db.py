#!/usr/bin/env python3
"""Nightly SQLite backups (gap-closure plan GC7). stdlib only; WAL-safe via
sqlite3.Connection.backup. Never touches secrets: prints a reminder to run
`python -m jarvis.vault export-key` by hand instead."""
from __future__ import annotations
import sqlite3, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
DBS = ("data/jarvis.db", "data/costs.db")
BACKUP_DIR = ROOT / "data" / "backups"
BACKUP_KEEP = 14          # §6

def backup_one(src: Path, stamp: str) -> Path:
    dst = BACKUP_DIR / f"{src.stem}.{stamp}.db"
    with sqlite3.connect(src) as s, sqlite3.connect(dst) as d:
        s.backup(d)
    return dst

def prune(stem: str, keep: int) -> list[Path]:
    files = sorted(BACKUP_DIR.glob(f"{stem}.*.db"))
    doomed = files[:-keep] if len(files) > keep else []
    for f in doomed:
        f.unlink()
    return doomed

def main() -> int:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M")
    rc = 0
    for rel in DBS:
        src = ROOT / rel
        if not src.exists():
            print(f"skip {rel}: missing"); continue
        try:
            dst = backup_one(src, stamp)
            gone = prune(src.stem, BACKUP_KEEP)
            print(f"ok {rel} -> {dst.relative_to(ROOT)} (pruned {len(gone)})")
        except Exception as exc:  # noqa: BLE001
            print(f"FAILED {rel}: {type(exc).__name__}: {exc}", file=sys.stderr); rc = 1
    print("reminder: the vault key is NOT backed up here — run `python -m jarvis.vault export-key` once and store it off-machine.")
    return rc

if __name__ == "__main__":
    sys.exit(main())
