#!/usr/bin/env python3
"""check_github.py — thin wrapper, kept for muscle memory.

MORTIMER_AGENT_TRUST_PLAN.md D9 folded this script's logic into
scripts/check_env.py (the `check_github` / `github_probe` functions) so
GitHub credential health is checked as part of the one preflight command
rather than a second, easy-to-forget one. This file now just calls that.

    python scripts/check_github.py

For the full preflight (recommended): python scripts/check_env.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from check_env import check_github, load_env, read_dotenv_only, failures  # noqa: E402


def main() -> int:
    env = load_env()
    check_github(env, read_dotenv_only())
    # check_github() only ever reports PASS/WARN (D9 — never a required
    # FAIL for GitHub specifically), so `failures` cannot contain a GitHub
    # entry; this exit code exists only to flag a genuinely broken .env
    # parse, not a credential verdict.
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
