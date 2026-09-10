#!/usr/bin/env python3
"""CI gate: fail if the diff touches paths outside the self-edit allowlist.

Self-edit branches (jarvis/self-edit/*) must only contain allowlisted
changes (plan section 2.2 step 2). Other branches (human development) are
exempt: the allowlist constrains the agent, not the humans.

Usage: python scripts/check_allowlist.py [base...head]   (default origin/main...HEAD)
Exit 0 = clean, 1 = violations found.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from jarvis.selfedit.allowlist import Allowlist  # noqa: E402

SELF_EDIT_PREFIX = "jarvis/self-edit"


def _current_branch() -> str:
    # PR checkouts use a detached merge commit. GitHub supplies the source
    # branch independently of that checkout. Unknown CI context stays
    # empty so it cannot accidentally exempt an agent-authored change.
    if os.environ.get("GITHUB_ACTIONS") == "true":
        if os.environ.get("GITHUB_EVENT_NAME") == "pull_request":
            return os.environ.get("GITHUB_HEAD_REF", "").strip()
        return ""
    proc = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    return proc.stdout.strip()


def main() -> int:
    diff_range = sys.argv[1] if len(sys.argv) > 1 else "origin/main...HEAD"
    branch = _current_branch()
    if branch and not branch.startswith(SELF_EDIT_PREFIX):
        print(f"check_allowlist: branch '{branch}' is not a self-edit branch - "
              "allowlist not enforced")
        return 0

    proc = subprocess.run(
        ["git", "diff", "--name-only", diff_range],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    if proc.returncode != 0:
        print(f"check_allowlist: git diff failed: {proc.stderr.strip()}")
        return 1
    changed = [n for n in proc.stdout.splitlines() if n.strip()]
    if not changed:
        print("check_allowlist: no changed files")
        return 0

    allowlist = Allowlist.load(REPO_ROOT / "config" / "self_edit_allowlist.json")
    violations = allowlist.filter_violations(changed)
    if violations:
        print("check_allowlist: FORBIDDEN paths in self-edit diff:")
        for v in violations:
            print(f"  - {v}")
        return 1
    print(f"check_allowlist: {len(changed)} changed file(s), all allowlisted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
