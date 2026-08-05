#!/usr/bin/env python3
"""Latency probe (plan Phase 7, step 7.3 — locked).

Parses a bot log and reports per-turn `user_end->first_audio`: count, p50,
p90, split by delegated vs non-delegated. A turn is delegated if an [AGENT]
line falls inside it (between the previous turn's first_audio and this one).

Usage:
    python3 scripts/latency_probe.py [path-to-bot-log]     # or stdin

Targets (plan Phase 7 tests):
    p50 <= 1200 ms non-delegated, p50 <= 2500 ms delegated,
    p90 <= 3500 ms overall.
"""

from __future__ import annotations

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


def main(argv: list[str]) -> int:
    if len(argv) > 1:
        with open(argv[1], encoding="utf-8") as handle:
            text = handle.read()
    else:
        text = sys.stdin.read()
    print(render_table(parse_latencies(text)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
