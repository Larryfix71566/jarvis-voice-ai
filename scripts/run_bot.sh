#!/bin/bash
# Run the Jarvis bot (plan Phase 4, step 4.3).
# No venv on this platform — deps live in the user site; .env provides keys.
set -e
cd "$(dirname "$0")/.."
set -a
. ./.env
set +a
exec python3 -m jarvis.bot.bot
