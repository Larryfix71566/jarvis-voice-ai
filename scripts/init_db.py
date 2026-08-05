#!/usr/bin/env python3
"""Apply database migrations (plan Phase 0, step 0.6 / Exit Gate 0)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jarvis.db import run_migrations


def main() -> None:
    newly_applied = run_migrations()
    if newly_applied:
        print("migrations applied: " + ", ".join(newly_applied))
    else:
        print("migrations already up to date")


if __name__ == "__main__":
    main()
