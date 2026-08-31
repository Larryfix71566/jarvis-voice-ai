#!/usr/bin/env bash
# wait_for.sh HOST PORT TIMEOUT_SECS NAME — block until HOST:PORT accepts TCP, or fail loudly.
set -euo pipefail
HOST="${1:?usage: wait_for.sh HOST PORT TIMEOUT_SECS NAME}"
PORT="${2:?missing PORT}"
TIMEOUT="${3:-30}"
NAME="${4:-$HOST:$PORT}"
deadline=$((SECONDS + TIMEOUT))
until nc -z "$HOST" "$PORT" 2>/dev/null; do
  if (( SECONDS >= deadline )); then
    echo "FATAL: ${NAME} not listening on ${HOST}:${PORT} after ${TIMEOUT}s — refusing to start dependents." >&2
    exit 1
  fi
  echo "waiting for ${NAME} on ${HOST}:${PORT}..."
  sleep 1
done
echo "${NAME} is up on ${HOST}:${PORT}."
