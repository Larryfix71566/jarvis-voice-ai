#!/usr/bin/env bash
# Phase 6: start the Jarvis web console (dev server on :5173).
# The bot must be running separately: ./scripts/run_bot.sh
set -euo pipefail
cd "$(dirname "$0")/../web"
if [ ! -d node_modules ]; then
  echo "web dependencies missing — installing (no bin links: sandbox mount)" >&2
  npm install --no-bin-links
fi
exec npm run dev
