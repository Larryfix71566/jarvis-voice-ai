#!/bin/bash
# Run the Phase 2 per-exchange memory extraction worker
# (MORTIMER_OPTIMIZATION_PLAN.md Phase 2, "Extraction Gate"). Polls the
# conversations table for finished user->assistant exchanges and runs
# each through jarvis/memory_extraction.py's novelty gate. Independent of
# the bot process -- it only needs the sqlite db and the LLM API, so it
# does not wait on vault.
# Prefers the project venv when present; otherwise falls back to python3
# (e.g. deps installed in the user site). .env provides keys.
set -e
cd "$(dirname "$0")/.."
set -a
. ./.env
set +a
if [ -x .venv/bin/python ]; then
  exec .venv/bin/python -m jarvis.memory_extraction_worker
fi
exec python3 -m jarvis.memory_extraction_worker
