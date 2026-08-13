#!/usr/bin/env bash
# One command to start (or restart) the whole Mortimer stack.
#
# Usage:
#   ./scripts/mortimer.sh         start or restart everything (bot + admin + web)
#   ./scripts/mortimer.sh stop    stop everything
#   ./scripts/mortimer.sh logs    tail all component logs
#
# Components run in the background (nohup, survives terminal close) and
# append to logs/*.log. Idempotent: always safe to re-run; existing
# processes are stopped first, so this doubles as "restart".
#
# Log rotation (run-logging plan D11/§5.9): each restart used to truncate
# logs/*.log via `>`, destroying the previous session's diagnostics —
# most of Mortimer's runtime output (TURN, [AGENT], [session], USER:/BOT:
# lines) is print()-to-stdout, which a Python logging.FileHandler never
# sees, so rotation has to happen here, shell-side. Before each start,
# logs/<name>.log is shifted to .1, prior generations shift up to
# LOG_GENERATIONS, and the new run appends (`>>`) rather than truncates.
# Previous sessions live in logs/<name>.log.1 .. .LOG_GENERATIONS.
set -uo pipefail
cd "$(dirname "$0")/.."

BOT_PORT="${JARVIS_BOT_PORT:-7860}"
ADMIN_PORT=7861
WEB_PORT=5173
LOG_GENERATIONS=5

cmd="${1:-start}"

stop_all() {
  pkill -f "jarvis.bot.bot"        2>/dev/null
  pkill -f "jarvis.admin.server"   2>/dev/null
  pkill -f "vite"                  2>/dev/null
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
    exec tail -f logs/bot.log logs/admin.log logs/web.log
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
rotate_log bot
rotate_log admin
rotate_log web
nohup ./scripts/run_bot.sh   >> logs/bot.log   2>&1 &
BOT_PID=$!
nohup ./scripts/run_admin.sh >> logs/admin.log 2>&1 &
ADMIN_PID=$!
nohup ./scripts/run_web.sh   >> logs/web.log   2>&1 &
WEB_PID=$!

# Give the components a moment, then report health (best-effort).
sleep 4
check() {  # name pid url
  if kill -0 "$2" 2>/dev/null; then
    echo "  $1: running (pid $2) — $3"
  else
    echo "  $1: FAILED to start — see logs/$1.log" >&2
  fi
}
check bot   "$BOT_PID"   "http://localhost:$BOT_PORT"
check admin "$ADMIN_PID" "http://localhost:$ADMIN_PORT/api/health"
check web   "$WEB_PID"   "http://localhost:$WEB_PORT"

echo
echo "Open http://localhost:$WEB_PORT and click Connect."
echo "Logs:  ./scripts/mortimer.sh logs   (or: tail -f logs/bot.log)"
echo "       previous sessions: logs/<name>.log.1 .. .${LOG_GENERATIONS}"
echo "Stop:  ./scripts/mortimer.sh stop"
