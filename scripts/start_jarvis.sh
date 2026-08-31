#!/usr/bin/env bash
# start_jarvis.sh — the single command. Run from repo root: ./scripts/start_jarvis.sh
set -euo pipefail
cd "$(dirname "$0")/.."
fail() { echo "FATAL: $*" >&2; exit 1; }
[[ -f Procfile ]] || fail "no Procfile in $(pwd)"
for port in 7860 8484; do
  if lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
    fail "port $port already in use — kill the old process first: lsof -i :$port"
  fi
done
[[ -f .env ]] || echo "note: no .env in repo root (fine if the vault holds everything)"
if command -v overmind >/dev/null 2>&1; then
  exec overmind start -f Procfile
elif command -v hivemind >/dev/null 2>&1; then
  exec hivemind Procfile
else
  fail "install a runner first: brew install overmind"
fi
