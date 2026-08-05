#!/bin/bash
# Run the Jarvis bot (plan Phase 4, step 4.3).
# Prefers the project venv when present; otherwise falls back to python3
# (e.g. deps installed in the user site). .env provides keys.
set -e
cd "$(dirname "$0")/.."
set -a
. ./.env
set +a
if [ -x .venv/bin/python ]; then
  exec .venv/bin/python -m jarvis.bot.bot
fi
exec python3 -m jarvis.bot.bot
