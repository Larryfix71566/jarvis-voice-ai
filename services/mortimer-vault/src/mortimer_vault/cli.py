"""mortimer-vault CLI (§11)."""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from . import USER_ID
from .config import Paths, load_retrieval_config
from .gitutil import ensure_repo, commit
from .index import Index
from .mdfile import ParseError, parse, serialize
from .schema import is_valid_slug, now_iso, validate_strict, ValidationError
from .vault import Vault


def _slugify(name: str) -> str:
    s = name.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    s = re.sub(r"-+", "-", s)
    return s or "untitled"


def cmd_init(args):
    paths = Paths.build()
    paths.ensure_layout(USER_ID)
    ensure_repo(paths.vault)
    load_retrieval_config(paths)  # creates default config if absent
    index = Index(paths, USER_ID)
    n = index.rebuild_full()
    index.close()
    print(f"initialized {paths.home} ({n} files indexed)")


def cmd_serve(args):
    import uvicorn

    uvicorn.run("mortimer_vault.service:app", host="127.0.0.1", port=8484, log_level="info")


def cmd_reindex(args):
    paths = Paths.build()
    index = Index(paths, USER_ID)
    if args.full:
        n = index.rebuild_full()
        print(f"full reindex: {n} files")
    else:
        n = index.sync_incremental()
        print(f"incremental reindex: {n} files changed")
    index.close()


def cmd_import(args):
    paths = Paths.build()
    paths.ensure_layout(USER_ID)
    ensure_repo(paths.vault)
    vault = Vault(paths, USER_ID)
    src = Path(args.src_dir)
    existing_ids = vault._all_ids()

    count = 0
    for f in sorted(src.glob("*.md")):
        base_slug = _slugify(f.stem)
        slug = base_slug
        n = 2
        while slug in existing_ids:
            slug = f"{base_slug}-{n}"
            n += 1
        existing_ids.add(slug)

        stat = f.stat()
        from datetime import datetime, timezone

        ts = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        body = f.read_text(encoding="utf-8")
        fm = {
            "id": slug,
            "type": "area",
            "created": ts,
            "updated": ts,
            "last_accessed": ts,
            "tags": [],
            "confidence": "medium",
            "source_sessions": [],
            "schema": 1,
        }
        validate_strict(fm)
        path = paths.user_dir(USER_ID) / "areas" / f"{slug}.md"
        Vault._atomic_write(path, serialize(fm, body))
        commit(paths.vault, f"vault: create {slug}")
        count += 1
        print(f"imported {f.name} -> areas/{slug}.md")

    index = Index(paths, USER_ID)
    index.rebuild_full()
    index.close()
    print(f"imported {count} files")


def cmd_check(args):
    paths = Paths.build()
    user_dir = paths.user_dir(USER_ID)
    failures = []
    total = 0
    for sub in ("areas", "sessions", "inbox"):
        d = user_dir / sub
        if not d.exists():
            continue
        for p in sorted(d.glob("*.md")):
            total += 1
            try:
                fm, _ = parse(p.read_text(encoding="utf-8"))
                validate_strict(fm)
            except (ParseError, ValidationError) as e:
                failures.append((str(p), str(e)))

    print(f"checked {total} files")
    if failures:
        print(f"{len(failures)} failures:")
        for path, msg in failures:
            print(f"  {path}: {msg}")
        sys.exit(1)
    print("all valid")


def cmd_search(args):
    paths = Paths.build()
    index = Index(paths, USER_ID)
    results, meta = index.search(query=args.query)
    for r in results:
        print(f"[{r['score']:.3f}] {r['id']} ({r['type']}, {r['confidence']}) — {r['snippet']}")
    print(f"meta: {meta}")
    index.close()


def main():
    parser = argparse.ArgumentParser(prog="mortimer-vault")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init").set_defaults(func=cmd_init)
    sub.add_parser("serve").set_defaults(func=cmd_serve)

    p_reindex = sub.add_parser("reindex")
    p_reindex.add_argument("--full", action="store_true")
    p_reindex.set_defaults(func=cmd_reindex)

    p_import = sub.add_parser("import")
    p_import.add_argument("src_dir")
    p_import.set_defaults(func=cmd_import)

    sub.add_parser("check").set_defaults(func=cmd_check)

    p_search = sub.add_parser("search")
    p_search.add_argument("query")
    p_search.set_defaults(func=cmd_search)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
