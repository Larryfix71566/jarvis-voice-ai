#!/usr/bin/env bash
# One command to start (or restart) the whole Mortimer stack: vault, bot,
# the Phase 2 memory-extraction worker, admin, web, and the costs API.
#
# Usage:
#   ./scripts/mortimer.sh         start or restart everything
#   ./scripts/mortimer.sh stop    stop everything
#   ./scripts/mortimer.sh logs    tail all component logs
#
# This replaces scripts/start_jarvis.sh (removed 2026-09-02) as the single
# canonical launcher -- that script drove the Procfile through overmind/
# hivemind; this one hand-launches each process itself instead, so it can
# do proper log rotation and a real stop-then-start restart (overmind's
# own restart semantics don't rotate logs the way this repo wants). The
# Procfile is kept only as a process inventory / reference -- nothing
# executes it anymore; keep it in sync with this file by hand.
#
# Components run in the background (nohup, survives terminal close) and
# append to logs/*.log. Idempotent: always safe to re-run; existing
# processes are stopped first, so this doubles as "restart".
#
# Log rotation (run-logging plan D11/§5.9): each restart used to truncate
# logs/*.log via `>`, destroying the previous session's diagnostics --
# most of Mortimer's runtime output (TURN, [AGENT], [session], USER:/BOT:
# lines) is print()-to-stdout, which a Python logging.FileHandler never
# sees, so rotation has to happen here, shell-side. Before each start,
# logs/<name>.log is shifted to .1, prior generations shift up to
# LOG_GENERATIONS, and the new run appends (`>>`) rather than truncates.
# Previous sessions live in logs/<name>.log.1 .. .LOG_GENERATIONS.
set -uo pipefail
cd "$(dirname "$0")/.."

BOT_PORT="${JARVIS_BOT_PORT:-7860}"
VAULT_PORT=8484
ADMIN_PORT=7861
WEB_PORT=5173
COSTS_PORT=8487
LOG_GENERATIONS=5

cmd="${1:-start}"

stop_all() {
  pkill -f "mortimer-vault serve"            2>/dev/null
  pkill -f "jarvis.bot.bot"                  2>/dev/null
  pkill -f "jarvis.memory_extraction_worker" 2>/dev/null
  pkill -f "jarvis.admin.server"             2>/dev/null
  pkill -f "vite"                            2>/dev/null
  pkill -f "jarvis.costs_api"                2>/dev/null
  sleep 1
  return 0
}

rotate_log() {  # name (e.g. "bot" -> logs/bot.log)
  local name="$1" i
  [ -f "logs/${name}.log" ] || return 0
  for ((i = LOG_GENERATIONS - 1; i >= 1; i--)); do
    if [ -f "logs/${name}.log.${i}" ]; then
      mv "logs/${name}.log.${i}" "logs/${name}.log.$((i + 1))"
    fi
  done
  mv "logs/${name}.log" "logs/${name}.log.1"
}

case "$cmd" in
  stop)
    stop_all
    echo "Mortimer stopped."
    exit 0
    ;;
  logs)
    exec tail -f logs/vault.log logs/bot.log logs/extractor.log logs/admin.log logs/web.log logs/costs.log
    ;;
  start)
    ;;
  *)
    echo "usage: $0 [start|stop|logs]" >&2
    exit 2
    ;;
esac

if [ ! -x .venv/bin/python ]; then
  echo "no virtualenv found at .venv — create it first:" >&2
  echo "  python3.12 -m venv .venv && source .venv/bin/activate" >&2
  echo "  pip install -r requirements-lock.txt && python scripts/init_db.py" >&2
  exit 1
fi
if [ ! -f .env ]; then
  echo "no .env file — copy .env.example to .env and fill in your keys" >&2
  exit 1
fi

echo "Restarting Mortimer..."
stop_all

mkdir -p logs
rotate_log vault
rotate_log bot
rotate_log extractor
rotate_log admin
rotate_log web
rotate_log costs

nohup ./scripts/run_kb.sh >> logs/vault.log 2>&1 &
VAULT_PID=$!
nohup bash -c "./scripts/wait_for.sh 127.0.0.1 ${VAULT_PORT} 30 vault && exec ./scripts/run_bot.sh" >> logs/bot.log 2>&1 &
BOT_PID=$!
nohup ./scripts/run_memory_extractor.sh >> logs/extractor.log 2>&1 &
EXTRACTOR_PID=$!
nohup ./scripts/run_admin.sh >> logs/admin.log 2>&1 &
ADMIN_PID=$!
nohup ./scripts/run_web.sh >> logs/web.log 2>&1 &
WEB_PID=$!
nohup ./scripts/run_costs.sh >> logs/costs.log 2>&1 &
COSTS_PID=$!

# Give the components a moment, then report health (best-effort). Bot
# waits on vault internally (up to 30s) before it actually launches, so
# this is a liveness check, not a readiness probe -- a bot that's still
# inside its own wait_for will still show "running".
sleep 6
check() {  # name pid label
  if kill -0 "$2" 2>/dev/null; then
    echo "  $1: running (pid $2) — $3"
  else
    echo "  $1: FAILED to start — see logs/$1.log" >&2
  fi
}
check vault     "$VAULT_PID"     "tcp 127.0.0.1:$VAULT_PORT"
check bot       "$BOT_PID"       "http://localhost:$BOT_PORT (waits on vault)"
check extractor "$EXTRACTOR_PID" "background worker, no port"
check admin     "$ADMIN_PID"     "http://localhost:$ADMIN_PORT/api/health"
check web       "$WEB_PID"       "http://localhost:$WEB_PORT"
check costs     "$COSTS_PID"     "http://localhost:$COSTS_PORT"

echo
echo "Open http://localhost:$WEB_PORT and click Connect."
echo "Logs:  ./scripts/mortimer.sh logs   (or: tail -f logs/bot.log)"
echo "       previous sessions: logs/<name>.log.1 .. .${LOG_GENERATIONS}"
echo "Stop:  ./scripts/mortimer.sh stop"
