#!/usr/bin/env python3
"""Prepare a human rating form without opening the private condition key."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from jarvis.skill_evaluation_review import (
    prepare_human_review,
    read_private_review_file,
    write_private_review_json,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review", required=True, type=Path,
                        help="blinded review.json from the evaluation run")
    parser.add_argument("--out", required=True, type=Path,
                        help="new path for the human ratings template")
    args = parser.parse_args()
    try:
        payload = prepare_human_review(read_private_review_file(args.review))
        write_private_review_json(args.out, payload)
    except Exception as exc:  # noqa: BLE001 — source/output details may be sensitive
        print(f"Review preparation stopped ({type(exc).__name__}).", file=sys.stderr)
        return 2
    print(f"Human rating form: {args.out}")
    print("Keep the condition key private until every rating is complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
