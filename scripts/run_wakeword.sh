#!/bin/bash
# Run the Mortimer wake-word sidecar (openWakeWord): localhost-only
# websocket server on 7862. Requires: pip install openwakeword websockets
# and JARVIS_WAKEWORD_MODEL pointing at a trained 'Mortimer' model file.
set -e
cd "$(dirname "$0")/.."
set -a
. ./.env
set +a
if [ -x .venv/bin/python ]; then
  exec .venv/bin/python -m jarvis.wakeword.server
fi
exec python3 -m jarvis.wakeword.server
