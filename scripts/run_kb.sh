#!/usr/bin/env bash
# Knowledge-base vault service (:8484). Source: ~/mortimer-vault (separate package).
#
# mcp-kb's tools and jarvis/kb_digest.py both call this service over HTTP —
# they do not import the mortimer-vault package. This script exists only
# to keep the vault service's own venv separate from Mortimer's, mirroring
# how run_admin.sh / run_web.sh each start their own process.
set -euo pipefail

VAULT_DIR="${MORTIMER_VAULT_DIR:-$HOME/mortimer-vault}"

if [ ! -d "$VAULT_DIR" ]; then
  echo "mortimer-vault not found at $VAULT_DIR (set MORTIMER_VAULT_DIR to override)" >&2
  exit 1
fi

cd "$VAULT_DIR"
source .venv/bin/activate
exec mortimer-vault serve

