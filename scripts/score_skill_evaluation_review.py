#!/usr/bin/env python3
"""Validate human ratings, unblind paired outcomes, and report SW-G metrics."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from jarvis.skill_evaluation_review import (
    read_private_review_file,
    score_human_review,
    write_private_review_json,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review", required=True, type=Path)
    parser.add_argument("--ratings", required=True, type=Path,
                        help="completed human ratings form")
    parser.add_argument("--condition-key", required=True, type=Path,
                        help="private condition-key.json")
    parser.add_argument("--metrics", required=True, type=Path,
                        help="private usage-metrics.json")
    parser.add_argument("--out", required=True, type=Path,
                        help="new path for the scored acceptance report")
    args = parser.parse_args()
    try:
        review_bytes = read_private_review_file(args.review)
        result = score_human_review(
            review_bytes=review_bytes,
            ratings=json.loads(read_private_review_file(args.ratings)),
            condition_key=json.loads(read_private_review_file(args.condition_key)),
            metrics=json.loads(read_private_review_file(args.metrics)),
        )
        write_private_review_json(args.out, result)
    except Exception as exc:  # noqa: BLE001 — do not print content or provider diagnostics
        print(f"Review scoring stopped ({type(exc).__name__}).", file=sys.stderr)
        return 2
    state = "passes" if result["accepted_for_maintainer_review"] else "does not pass"
    print(f"Evaluation {state} SW-G acceptance; report: {args.out}")
    return 0 if result["accepted_for_maintainer_review"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
