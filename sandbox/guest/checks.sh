#!/usr/bin/env bash
# Run with control.py exec TASK /bin/bash '/Volumes/My Shared Files/input/checks.sh'
set -uo pipefail
ROOT=/Users/admin/mortimer
cd "$ROOT/source" || exit 1
source "$ROOT/development.env"
mkdir -p "$ROOT/reports"
failed=0
check() {
  name="$1"
  shift
  if "$@" > "$ROOT/reports/$name.log" 2>&1; then
    printf '%s: passed\n' "$name"
  else
    printf '%s: failed (see reports/%s.log)\n' "$name" "$name"
    failed=1
  fi
}
check policy .venv/bin/python -m unittest discover -s tests/ci -v
check sandbox .venv/bin/python -m unittest discover -s sandbox/tests -v
check backend .venv/bin/python -m pytest tests/unit -q
check knowledge-base services/mortimer-vault/.venv/bin/python -m pytest services/mortimer-vault/tests -q
check web /bin/bash -c 'cd web && npm run build'
check native-library swift test --package-path macos/JarvisKit
check native-app swift test --package-path macos/MortimerHost
exit "$failed"
