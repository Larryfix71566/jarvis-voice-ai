#!/usr/bin/env bash
# Install the repository's knowledge-base package in its own environment.
# Does not initialize, import, or modify knowledge documents or credentials.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VAULT_DIR="${MORTIMER_VAULT_DIR:-$REPO_ROOT/services/mortimer-vault}"
PYTHON="${MORTIMER_KB_PYTHON:-python3.12}"

cd "$VAULT_DIR"
VAULT_DIR="$PWD"
if [ ! -x .venv/bin/python ]; then
  "$PYTHON" -m venv .venv
fi
.venv/bin/python -m pip install -e "$VAULT_DIR[test]"
echo "Knowledge-base package installed. Start with: bash $REPO_ROOT/scripts/run_kb.sh"
