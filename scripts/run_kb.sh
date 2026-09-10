#!/usr/bin/env bash
# Knowledge-base service (:8484), packaged in this repository.
#
# mcp-kb's tools and jarvis/kb_digest.py both call this service over HTTP —
# they do not import the mortimer-vault package. This script exists only
# to keep the vault service's own venv separate from Mortimer's, mirroring
# how run_admin.sh / run_web.sh each start their own process.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VAULT_DIR="${MORTIMER_VAULT_DIR:-$REPO_ROOT/services/mortimer-vault}"

if [ ! -d "$VAULT_DIR" ]; then
  echo "mortimer-vault not found at $VAULT_DIR (set MORTIMER_VAULT_DIR to override)" >&2
  exit 1
fi

cd "$VAULT_DIR"
if [ ! -x .venv/bin/mortimer-vault ]; then
  echo "Knowledge-base environment missing. Run: bash $REPO_ROOT/scripts/setup_kb.sh" >&2
  exit 1
fi
# MORTIMER_HOME still controls the data location (default: ~/Mortimer).
# Source location and private data location are intentionally independent.
exec .venv/bin/mortimer-vault serve

