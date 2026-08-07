#!/bin/bash
# Run the Jarvis admin sidecar (upgrade plan U1.5): localhost-only API on 7861.
set -e
cd "$(dirname "$0")/.."
set -a
. ./.env
set +a
if [ -x .venv/bin/python ]; then
  exec .venv/bin/python -m jarvis.admin.server
fi
exec python3 -m jarvis.admin.server
