#!/usr/bin/env python3
"""Latency probe (plan Phase 7, step 7.3 — locked).

Parses a bot log and reports per-turn `user_end->first_audio`: count, p50,
p90, split by delegated vs non-delegated. Legacy log mode uses the original
adjacent [AGENT] heuristic, suitable for historical diagnostics/CI fixtures,
not live acceptance.

For acceptance, supply an operator-labeled JSONL window (no transcript needed).
Use elapsed milliseconds since the end of the same user utterance. Example:
    {"turn_id":"t1","kind":"acknowledgement","ms":200}
    {"turn_id":"t1","kind":"useful_reply","ms":1000}
    {"turn_id":"t1","kind":"turn_complete","classification":"non-delegated"}
Use a synthetic prompt window with unique opaque IDs, and label every tested
turn complete even if nothing useful was heard (an absent reply then fails
acceptance). Mark delegation only when this turn actually dispatched to a
specialist; a tool-only turn is non-delegated. An acknowledgement is a verbal
holding message; first useful reply starts at the first audible speech that
delivers part of the requested answer or result. Use no prompt or reply text.
Events may arrive in any order. Only useful-reply latency is budgeted.
    python3 scripts/latency_probe.py --acceptance [samples.jsonl]

Usage:
    python3 scripts/latency_probe.py [path-to-bot-log]     # or stdin

Targets (plan Phase 7 tests):
    p50 <= 1200 ms non-delegated, p50 <= 2500 ms delegated,
    p90 <= 3500 ms overall.
"""

from __future__ import annotations

import argparse
import json
import re
import sys

TURN_RE = re.compile(r"TURN user_end->first_audio = (\d+)ms")
AGENT_RE = re.compile(r"\[AGENT\]")

P50_NON_DELEGATED_TARGET_MS = 1200
P50_DELEGATED_TARGET_MS = 2500
P90_OVERALL_TARGET_MS = 3500


def percentile(values: list[int], pct: float) -> float | None:
    """Linear-interpolation percentile (same method as numpy default)."""
    if not values:
        return None
    ordered = sorted(values)
    rank = (len(ordered) - 1) * (pct / 100.0)
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (rank - low)


def parse_latencies(text: str) -> dict[str, list[int]]:
    """Split user_end->first_audio latencies into delegated/non-delegated."""
    buckets: dict[str, list[int]] = {"delegated": [], "non-delegated": []}
    turn_delegated = False
    for line in text.splitlines():
        if AGENT_RE.search(line):
            turn_delegated = True
        match = TURN_RE.search(line)
        if match:
            key = "delegated" if turn_delegated else "non-delegated"
            buckets[key].append(int(match.group(1)))
            turn_delegated = False
    return buckets


def parse_acceptance(text: str) -> tuple[dict[str, list[int]], dict[str, list[int]]]:
    """Join explicit audible samples by turn ID; reject ambiguity or omissions."""
    useful: dict[str, list[int]] = {"delegated": [], "non-delegated": []}
    acknowledgements: dict[str, list[int]] = {"delegated": [], "non-delegated": []}
    turns: dict[str, dict[str, str | int]] = {}
    for line_number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except ValueError as exc:
            raise ValueError(f"line {line_number}: invalid JSON event") from exc
        if (not isinstance(item, dict)
                or not isinstance(turn_id := item.get("turn_id"), str)
                or not turn_id.strip() or turn_id != turn_id.strip()):
            raise ValueError(f"line {line_number}: missing or invalid turn id")
        kind = item.get("kind")
        if kind in ("acknowledgement", "useful_reply"):
            value = item.get("ms")
            valid = set(item) == {"turn_id", "kind", "ms"} and type(value) is int and value >= 0
        elif kind == "turn_complete":
            value = item.get("classification")
            valid = (set(item) == {"turn_id", "kind", "classification"}
                     and value in ("delegated", "non-delegated"))
        else:
            valid = False
        if not valid:
            raise ValueError(f"line {line_number}: invalid acceptance event")
        events = turns.setdefault(turn_id, {})
        if kind in events:
            raise ValueError(f"line {line_number}: duplicate acceptance event")
        events[kind] = value

    if not turns:
        raise ValueError("no labeled acceptance turns")
    for number, events in enumerate(turns.values(), 1):
        reply, label = events.get("useful_reply"), events.get("turn_complete")
        if not isinstance(reply, int) or not isinstance(label, str):
            raise ValueError(f"turn {number}: missing useful-reply sample or completion classification")
        ack = events.get("acknowledgement")
        if isinstance(ack, int):
            if ack > reply:
                raise ValueError(f"turn {number}: acknowledgement follows useful reply")
            acknowledgements[label].append(ack)
        useful[label].append(reply)
    return useful, acknowledgements


def render_acknowledgements(buckets: dict[str, list[int]]) -> str:
    rows = [*buckets.items(), ("overall", buckets["delegated"] + buckets["non-delegated"])]
    lines = [f"{'class':<15} {'count':>5} {'p50':>10} {'p90':>10}"]
    for name, values in rows:
        lines.append(f"{name:<15} {len(values):>5} {fmt(percentile(values, 50)):>10}"
                     f" {fmt(percentile(values, 90)):>10}")
    return "\n".join(lines)


def fmt(value: float | None) -> str:
    return "-" if value is None else f"{value:.0f} ms"


def render_table(buckets: dict[str, list[int]]) -> str:
    overall = buckets["delegated"] + buckets["non-delegated"]
    rows = [
        ("non-delegated", buckets["non-delegated"],
         P50_NON_DELEGATED_TARGET_MS, None),
        ("delegated", buckets["delegated"], P50_DELEGATED_TARGET_MS, None),
        ("overall", overall, None, P90_OVERALL_TARGET_MS),
    ]
    lines = [f"{'class':<15} {'count':>5} {'p50':>10} {'p90':>10}  targets"]
    for name, values, p50_target, p90_target in rows:
        p50 = percentile(values, 50)
        p90 = percentile(values, 90)
        flags = []
        if p50_target is not None:
            flags.append(
                f"p50 {'OK' if p50 is not None and p50 <= p50_target else 'MISS'}"
                f" (<= {p50_target} ms)"
            )
        if p90_target is not None:
            flags.append(
                f"p90 {'OK' if p90 is not None and p90 <= p90_target else 'MISS'}"
                f" (<= {p90_target} ms)"
            )
        lines.append(
            f"{name:<15} {len(values):>5} {fmt(p50):>10} {fmt(p90):>10}"
            f"  {'; '.join(flags)}"
        )
    return "\n".join(lines)


def enforce_budget(buckets: dict[str, list[int]]) -> tuple[bool, list[str]]:
    """Check latencies against budget targets. Returns (all_pass, violations)."""
    violations = []
    overall = buckets["delegated"] + buckets["non-delegated"]

    p50_nd = percentile(buckets["non-delegated"], 50)
    if buckets["non-delegated"] and (p50_nd is None or p50_nd > P50_NON_DELEGATED_TARGET_MS):
        violations.append(
            f"non-delegated p50: {fmt(p50_nd)} exceeds target {P50_NON_DELEGATED_TARGET_MS} ms"
        )

    p50_d = percentile(buckets["delegated"], 50)
    if buckets["delegated"] and (p50_d is None or p50_d > P50_DELEGATED_TARGET_MS):
        violations.append(
            f"delegated p50: {fmt(p50_d)} exceeds target {P50_DELEGATED_TARGET_MS} ms"
        )

    p90_o = percentile(overall, 90)
    if overall and (p90_o is None or p90_o > P90_OVERALL_TARGET_MS):
        violations.append(
            f"overall p90: {fmt(p90_o)} exceeds target {P90_OVERALL_TARGET_MS} ms"
        )

    return len(violations) == 0, violations


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--budget", action="store_true", help="legacy first-audio CI budget")
    mode.add_argument("--acceptance", action="store_true", help="strict labeled audible-reply budget")
    parser.add_argument("logfile", nargs="?", help="input path (default stdin)")
    args = parser.parse_args(argv[1:])

    if args.logfile:
        with open(args.logfile, encoding="utf-8") as handle:
            text = handle.read()
    else:
        text = sys.stdin.read()

    if args.acceptance:
        try:
            buckets, acknowledgements = parse_acceptance(text)
        except ValueError as exc:
            print(f"Invalid latency acceptance window: {exc}", file=sys.stderr)
            return 1
        print("Audible acknowledgements (diagnostic only)")
        print(render_acknowledgements(acknowledgements))
        print("\nFirst useful audible reply (acceptance budget)")
    else:
        buckets = parse_latencies(text)
    print(render_table(buckets))

    if args.budget or args.acceptance:
        all_pass, violations = enforce_budget(buckets)
        if not all_pass:
            print("\n❌ LATENCY BUDGET EXCEEDED:")
            for v in violations:
                print(f"  {v}")
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
