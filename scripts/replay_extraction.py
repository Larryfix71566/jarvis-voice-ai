"""Replay memory extractions that failed (MORTIMER_VOICE_WORKFLOWS_PLAN.md
Phase 4 D1, Larry 2026-09-25: "replay the 28 lost extractions once at the
end run, on the Mac").

On 2026-09-16 one worker tick failed 28 exchanges with "database is locked"
(every one inside upsert_fact or add_observation; fixed by #78). Each
failure rolled back that exchange's writes and the cursor moved past it,
so whatever those exchanges held never reached memory. The log keeps
`memory_extraction_failed session=S source_turn=N` for each; N is the
assistant turn that closed the exchange, so the exchange itself is still
in `conversations`.

This does NOT simply rerun extract_from_exchange: that would stamp every
write "today" and let a 09-13 statement overwrite a fact Larry restated
since. Since W10 every memory carries its age, so a replayed fact carries
the time the exchange actually happened, and correct-first decides each
candidate against what is stored:

  new key, nothing similar stored ........ insert, dated to the exchange
  a similar fact is stored ................ skip (it already reached memory)
  stored and said since (or as new) ....... skip — the newer statement wins
                                            (a restatement in other words counts)
  stored but older than the exchange ...... update to the exchange's words and time
  archived before the exchange ............ bring back (the exchange restated it)
  archived after the exchange ............. skip — a later decision stands

Observations are not replayed: they are 14-day staging evidence, and ones
dated to 09-13..16 would expire at the next sweep.

Usage, from the repo root on the Mac (the model call needs the keys):
    .venv/bin/python scripts/replay_extraction.py            # dry run, writes nothing
    .venv/bin/python scripts/replay_extraction.py --apply    # writes, once
Running --apply twice changes nothing the second time (every candidate is
then stored as-new, so it is skipped).
"""
from __future__ import annotations

import argparse
import asyncio
import glob
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

FAIL_RE = re.compile(r"memory_extraction_failed session=(\S+) source_turn=(\d+)")
DEFAULT_LOGS = "logs/extractor.launchd.log*"


def failed_exchanges(paths: list[str]) -> list[tuple[str, int]]:
    """(session_id, assistant turn) for every logged failure, once each,
    oldest turn first."""
    found: set[tuple[str, int]] = set()
    for path in paths:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                match = FAIL_RE.search(line)
                if match:
                    found.add((match.group(1), int(match.group(2))))
    return sorted(found, key=lambda item: item[1])


def _when(value: str | None) -> datetime | None:
    try:
        stamp = datetime.fromisoformat((value or "").replace("Z", "+00:00"))
    except ValueError:
        return None
    return stamp if stamp.tzinfo else stamp.replace(tzinfo=timezone.utc)


def decide(conn, key: str, value: str, when: datetime, user: str, assistant: str) -> tuple[str, str]:
    """(action, reason) for one fact candidate; action is insert | update |
    revive | skip. Reads only."""
    from jarvis.memory import _is_volatile_state, scan_memory_content
    from jarvis.memory_extraction import _find_fact_match, extractor_rejection

    reason = scan_memory_content(key) or scan_memory_content(value)
    if reason is not None:
        return "skip", f"content scan: {reason}"
    if _is_volatile_state(key, value):
        return "skip", "volatile state"
    reason = extractor_rejection(key, value, user, assistant)
    if reason is not None:
        return "skip", reason
    row = conn.execute(
        "SELECT key, updated_at, last_seen_at, archived_at FROM memories "
        "WHERE kind = 'fact' AND key = ?",
        (key,),
    ).fetchone()
    if row is None or row["archived_at"]:
        # The worker's own novelty gate: a similar live fact means this
        # already reached memory under another name.
        near, _exact = _find_fact_match(conn, key, value)
        if near is not None:
            return "skip", f"similar fact stored: {near['key']}"
    if row is None:
        return "insert", "new"
    if row["archived_at"]:
        archived = _when(row["archived_at"])
        if archived is None or archived >= when:
            return "skip", "archived after this exchange"
        return "revive", "archived before this exchange, which restated it"
    # When Larry last said it: a restatement in other words moves
    # last_seen_at, not updated_at.
    said = [t for t in (_when(row["updated_at"]), _when(row["last_seen_at"])) if t]
    if not said or max(said) >= when:
        return "skip", "a newer statement is stored"
    return "update", "this exchange is newer than the stored fact"


def apply(conn, action: str, key: str, value: str, when: datetime, session_id: str,
          turn: int) -> None:
    from jarvis.memory import MAX_FACT_CHARS, infer_tier

    stamp = when.isoformat()
    value = value[:MAX_FACT_CHARS]
    if action == "insert":
        conn.execute(
            "INSERT INTO memories (kind, key, content, source_session_id, created_at, "
            "updated_at, tier, content_revision, source_turn, last_seen_at) "
            "VALUES ('fact', ?, ?, ?, ?, ?, ?, 1, ?, ?)",
            (key, value, session_id, stamp, stamp, infer_tier(key), turn, stamp),
        )
    elif action in ("update", "revive"):
        # decide() only chose these when nothing stored is newer than the
        # exchange, so moving the times to it never moves them backwards.
        row = conn.execute("SELECT updated_at, last_seen_at FROM memories "
                           "WHERE kind = 'fact' AND key = ?", (key,)).fetchone()
        later = [t for t in (_when(row["updated_at"]), _when(row["last_seen_at"])) if t and t > when]
        if later:
            raise ValueError(f"{key} was stated after {stamp}; refusing to move it back")
        conn.execute(
            "UPDATE memories SET content = ?, source_session_id = ?, updated_at = ?, "
            "archived_at = NULL, became = NULL, source_turn = ?, last_seen_at = ?, "
            "content_revision = content_revision + 1, "
            "recurrence_count = COALESCE(recurrence_count, 1) + 1 "
            "WHERE kind = 'fact' AND key = ?",
            (value, session_id, stamp, turn, stamp, key),
        )
    else:
        raise ValueError(action)


async def replay(conn, exchanges: list[tuple[str, int]], settings: Any, *, write: bool,
                 client_factory: Callable[[Any], Any] | None = None, out=print) -> dict:
    """Dry run unless `write`. One model call per exchange, made outside any
    write transaction; each exchange's writes commit together."""
    from jarvis.memory_extraction import MAX_ROW_CHARS, extract_candidates, source_exchange

    totals = {"exchanges": 0, "missing": 0, "unparseable": 0, "failed": 0,
              "insert": 0, "update": 0, "revive": 0, "skip": 0, "observations": 0}
    for session_id, turn in exchanges:
        exchange = source_exchange(conn, turn)
        if exchange is None or exchange["session_id"] != session_id:
            totals["missing"] += 1
            out(f"turn {turn}: no exchange for session {session_id} — skipped")
            continue
        when = _when(conn.execute("SELECT created_at FROM conversations WHERE id = ?",
                                  (turn,)).fetchone()[0])
        user = exchange["user"][:MAX_ROW_CHARS]
        assistant = exchange["assistant"][:MAX_ROW_CHARS]
        try:
            parsed = await extract_candidates(settings, session_id, user, assistant, client_factory)
        except Exception as exc:  # noqa: BLE001 — report and move on
            totals["failed"] += 1
            out(f"turn {turn}: the model call failed ({exc}) — skipped")
            continue
        totals["exchanges"] += 1
        if parsed is None:
            totals["unparseable"] += 1
            out(f"turn {turn} ({when:%Y-%m-%d}): unparseable reply — skipped")
            continue
        totals["observations"] += len(parsed["observations"])
        # One key once per exchange: the worker would insert the first and
        # overwrite it with the next, so the last value is what it keeps.
        facts = dict(parsed["facts"])
        decisions = [(key, value, *decide(conn, key, value, when, user, assistant))
                     for key, value in facts.items()]
        out(f"turn {turn} ({when:%Y-%m-%d}): {len(decisions)} fact(s), "
            f"{len(parsed['observations'])} observation(s) not replayed")
        for key, value, action, reason in decisions:
            totals[action] += 1
            out(f"    {action:<6} {key} = {value[:80]!r}  ({reason})")
        if write and any(action != "skip" for _k, _v, action, _r in decisions):
            try:
                for key, value, action, _reason in decisions:
                    if action != "skip":
                        apply(conn, action, key, value, when, session_id, turn)
                conn.commit()
            except Exception as exc:  # noqa: BLE001 — this exchange only, then go on
                conn.rollback()
                totals["failed"] += 1
                out(f"    not written ({exc}); this exchange's writes were rolled back")
    out(("Applied" if write else "Dry run (nothing written)") + ": "
        + ", ".join(f"{k} {v}" for k, v in totals.items()))
    return totals


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--apply", action="store_true", help="write (default: dry run)")
    parser.add_argument("--log", action="append",
                        help=f"extractor log(s) to read (default: {DEFAULT_LOGS})")
    parser.add_argument("--db", help="database path (default: JARVIS_DB_PATH or data/jarvis.db)")
    args = parser.parse_args(argv)

    os.chdir(REPO_ROOT)
    paths = args.log or sorted(glob.glob(DEFAULT_LOGS))
    exchanges = failed_exchanges(paths)
    print(f"{len(exchanges)} failed exchange(s) in {', '.join(paths) or '(no logs)'}")
    if not exchanges:
        return 0
    from jarvis.config import load_settings
    from jarvis.db import get_conn

    conn = get_conn(args.db)
    try:
        asyncio.run(replay(conn, exchanges, load_settings(), write=args.apply))
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
