#!/usr/bin/env python3
"""Evaluate the offline staged-memory rollout gate without opening SQLite.

This command consumes only the checked-in redacted rollout fixture. It records
the fixture digest, stage-order/first-20 review result, benefit/cost comparison,
privacy safety and budget limits. It never loads credentials, enables the
worker, or changes a user database.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT))

from jarvis.memory_automation_eval import evaluate_rollout_gate  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fixture", type=Path,
        default=ROOT / "tests/fixtures/memory_rollout_acceptance.json",
    )
    parser.add_argument(
        "--output", type=Path,
        default=ROOT / "docs/acceptance/memory-automation/rollout-monitoring-receipt.json",
    )
    args = parser.parse_args()
    raw = args.fixture.read_bytes()
    payload = json.loads(raw)
    receipt = evaluate_rollout_gate(payload)
    output = {
        "version": "memory-automation-rollout-receipt-v1",
        "fixture": str(args.fixture.relative_to(ROOT)),
        "fixture_sha256": hashlib.sha256(raw).hexdigest(),
        "live_database_touched": False,
        "production_automation_enabled": False,
        "gate": receipt.to_dict(),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    print(json.dumps({"output": str(args.output), "passed": receipt.passed,
                      "violations": list(receipt.violations)}, sort_keys=True))
    return 0 if receipt.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
