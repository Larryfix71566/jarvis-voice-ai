#!/usr/bin/env python3
"""Print payload-free migration readiness without login, inference or writes.

Only installed official CLIs' --version commands are invoked. No .env or
credential store is loaded. A nonzero exit means activation remains blocked.
"""
from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jarvis.subscription_readiness import retirement_readiness


def main() -> int:
    report = retirement_readiness()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["activation_ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
