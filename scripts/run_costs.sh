#!/bin/bash
# Run the costs API (jarvis/costs_api.py), :8487 -- serves cost_report.py's
# data over HTTP for the web console / admin sidecar. Matches every other
# scripts/run_*.sh: prefers the project venv, falls back to python3 on
# PATH; .env provides keys the underlying settings loader needs.
set -e
cd "$(dirname "$0")/.."
set -a
. ./.env
set +a
if [ -x .venv/bin/python ]; then
  exec .venv/bin/python -m uvicorn jarvis.costs_api:app --port 8487
fi
exec python3 -m uvicorn jarvis.costs_api:app --port 8487
