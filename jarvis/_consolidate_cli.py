"""python -m jarvis.consolidate — review-only duplicate report (K2).

Deliberately two commands, not one: the default REPORTS and writes
nothing, and dropping a key is a separate explicit invocation naming that
key. There is no "merge everything" verb, by design — an automatic
rewriter that is subtly wrong costs more than the duplicates do.
"""

from __future__ import annotations

import argparse
import sys

from jarvis.consolidate import format_report, propose_merges
from jarvis.db import get_conn
from jarvis.memory import delete_fact


def _load_facts(conn) -> list[dict]:
    rows = conn.execute(
        "SELECT key, content, COALESCE(tier, 'project') AS tier "
        "FROM memories WHERE kind = 'fact'"
    ).fetchall()
    return [dict(r) for r in rows]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m jarvis.consolidate")
    p.add_argument("--drop", nargs="+", metavar="KEY",
                   help="delete these fact keys (the only writing action)")
    p.add_argument("--threshold", type=float, default=None,
                   help="override the duplicate overlap threshold")
    args = p.parse_args(argv)

    with get_conn() as conn:
        if args.drop:
            for key in args.drop:
                ok = delete_fact(conn, key)
                print(f"{'deleted' if ok else 'not found'}: {key}")
            conn.commit()
            return 0

        facts = _load_facts(conn)

    kwargs = {"threshold": args.threshold} if args.threshold is not None else {}
    proposals = propose_merges(facts, **kwargs)
    print(f"{len(facts)} facts stored.\n")
    print(format_report(proposals))
    return 0


if __name__ == "__main__":
    sys.exit(main())
