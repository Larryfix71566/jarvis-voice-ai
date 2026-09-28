#!/usr/bin/env python3
"""Voice guard audit — MORTIMER_VOICE_WORKFLOWS_PLAN.md §7 T4/T5.

Read-only. Answers three questions for a period:
  1. How many assistant turns that reached Larry still contain a refusal or
     hand-off sentence (conversations table, same detector as the guard)?
  2. What did the hooks and the guard do (bot log lines)?
  3. Which capability gaps were logged (logs/capability_gaps.jsonl)?

Usage (repo root):
    python scripts/voice_guard_audit.py --since 2026-09-25
    python scripts/voice_guard_audit.py --since 2026-09-25 --turn-lines-after 1234

--turn-lines-after N: only "TURN user_end->first_audio" lines after the
first N such lines in logs/bot.launchd.log count toward the latency
median (record N with `grep -c "TURN user_end->first_audio"
logs/bot.launchd.log` just before the acceptance session).
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import statistics
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from jarvis.voice_workflows import reply_violations  # noqa: E402

# Pre-plan corpus, 2026-08-12 .. 2026-09-24 (plan §1): 75 of 2,013
# assistant turns contained a refusal or hand-off sentence.
BASELINE_PER_100 = 75 / 2013 * 100
BASELINE_FIRST_AUDIO_P50_MS = 969

GUARD_RE = re.compile(r"reply_guard action=(\w+) kind=(\w+)")
HOOK_RE = re.compile(r"voice_workflow_injected hook=(\w+) name=([\w-]+)")
TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})[ T]")
TURN_RE = re.compile(r"TURN user_end->first_audio = (\d+)ms")


def spoken_violations(db: Path, since: str) -> tuple[int, list[tuple[int, str, str, str]]]:
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    rows = conn.execute(
        "SELECT id, created_at, content FROM conversations "
        "WHERE role = 'assistant' AND created_at >= ? ORDER BY id", (since,)
    ).fetchall()
    conn.close()
    hits = []
    for row_id, created, content in rows:
        for sentence, kind in reply_violations(content or ""):
            hits.append((row_id, created[:16], kind, sentence))
            break
    return len(rows), hits


def log_counts(log_paths: list[Path], since: str) -> tuple[Counter, Counter]:
    guard, hooks = Counter(), Counter()
    for path in log_paths:
        if not path.exists():
            continue
        with path.open(errors="replace") as fh:
            for line in fh:
                ts = TS_RE.match(line)
                if ts and ts.group(1) < since:
                    continue
                m = GUARD_RE.search(line)
                if m:
                    guard[(m.group(1), m.group(2))] += 1
                    continue
                m = HOOK_RE.search(line)
                if m:
                    hooks[(m.group(1), m.group(2))] += 1
    return guard, hooks


def gap_summary(path: Path, since: str) -> tuple[int, Counter, list[str]]:
    if not path.exists():
        return 0, Counter(), []
    kinds, texts, total = Counter(), Counter(), 0
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if str(rec.get("ts", ""))[:10] < since:
            continue
        total += 1
        kinds[(rec.get("source"), rec.get("kind"), rec.get("agent"))] += 1
        texts[" ".join(str(rec.get("text", "")).split())[:120]] += 1
    return total, kinds, [f"{n}x {t}" for t, n in texts.most_common(10)]


def first_audio_p50(log: Path, after: int) -> tuple[int, float | None]:
    if not log.exists():
        return 0, None
    values = []
    seen = 0
    with log.open(errors="replace") as fh:
        for line in fh:
            m = TURN_RE.search(line)
            if not m:
                continue
            seen += 1
            if seen > after:
                values.append(int(m.group(1)))
    return len(values), (statistics.median(values) if values else None)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--since", required=True, help="YYYY-MM-DD (UTC for the database)")
    ap.add_argument("--db", type=Path, default=REPO / "data" / "jarvis.db")
    ap.add_argument("--logs", type=Path, nargs="*",
                    default=sorted((REPO / "logs").glob("bot.launchd.log*")))
    ap.add_argument("--gaps", type=Path, default=REPO / "logs" / "capability_gaps.jsonl")
    ap.add_argument("--turn-lines-after", type=int, default=None)
    args = ap.parse_args(argv)

    total, hits = spoken_violations(args.db, args.since)
    rate = (len(hits) / total * 100) if total else 0.0
    print(f"Assistant turns since {args.since}: {total}")
    print(f"  spoken refusal/hand-off: {len(hits)} ({rate:.1f} per 100; "
          f"pre-plan baseline {BASELINE_PER_100:.1f})")
    for row_id, created, kind, sentence in hits[:25]:
        print(f"    #{row_id} {created} {kind}: {sentence[:110]}")

    guard, hooks = log_counts(args.logs, args.since)
    print("Reply guard (bot log):")
    for (action, kind), n in sorted(guard.items()):
        print(f"  {action:<22} {kind:<8} {n}")
    print("Workflow injections (bot log):")
    for (hook, name), n in sorted(hooks.items()):
        print(f"  {hook:<7} {name:<28} {n}")

    n_gaps, kinds, top = gap_summary(args.gaps, args.since)
    print(f"Capability gaps logged: {n_gaps}")
    for (source, kind, agent), n in kinds.most_common():
        print(f"  {source:<12} {kind:<13} {agent or '-':<10} {n}")
    for line in top:
        print(f"    {line}")

    if args.turn_lines_after is not None:
        live_log = REPO / "logs" / "bot.launchd.log"
        n, p50 = first_audio_p50(live_log, args.turn_lines_after)
        shown = f"{p50:.0f} ms" if p50 is not None else "n/a"
        print(f"user_end->first_audio: n={n} p50={shown} "
              f"(pre-plan p50 {BASELINE_FIRST_AUDIO_P50_MS} ms; gate {BASELINE_FIRST_AUDIO_P50_MS + 150} ms)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
