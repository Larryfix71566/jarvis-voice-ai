#!/usr/bin/env bash
# Build the Mortimer shell (MORTIMER_MODEL_DISCIPLINE_AND_MAC_SHELL_PLAN.md
# B5). Wraps `swift build` for humans — this is a Swift Package Manager
# executable target (macos/MortimerShell/Package.swift), not a hand-authored
# .xcodeproj (see that file's header comment for why). CI is untouched: no
# macOS runner is assumed anywhere in .github/workflows.
#
# Usage:
#   ./scripts/build_shell.sh            # debug build
#   ./scripts/build_shell.sh --release  # release build
#
# To actually RUN the shell with mic access, open macos/MortimerShell in
# Xcode instead (File > Open... on the folder, or `open Package.swift`)
# and apply the Info.plist / entitlements settings documented in
# macos/MortimerShell/templates/*.template — `swift build` alone produces
# an unsigned, unsandboxed binary that cannot request microphone access.

set -euo pipefail

if [[ "$(uname)" != "Darwin" ]]; then
  echo "build_shell.sh only runs on macOS (found $(uname))." >&2
  exit 1
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SHELL_DIR="$REPO_ROOT/macos/MortimerShell"

if ! command -v swift >/dev/null 2>&1; then
  echo "swift not found — install Xcode / Xcode command line tools." >&2
  exit 1
fi

CONFIG="debug"
if [[ "${1:-}" == "--release" ]]; then
  CONFIG="release"
fi

echo "Building MortimerShell ($CONFIG)..."
cd "$SHELL_DIR"
swift build -c "$CONFIG"
echo "Built. For a real run with mic entitlements, open this folder in Xcode."
