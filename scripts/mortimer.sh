#!/usr/bin/env bash
# One command to start (or restart) the whole Mortimer stack.
#
# Usage:
#   ./scripts/mortimer.sh         start or restart everything (bot + admin + web)
#   ./scripts/mortimer.sh stop    stop everything
#   ./scripts/mortimer.sh logs    tail all component logs
#
# Components run in the background (nohup, survives terminal close) and
# write to logs/*.log. Idempotent: always safe to re-run; existing
# processes are stopped first, so this doubles as "restart".
set -uo pipefail
cd "$(dirname "$0")/.."

BOT_PORT="${JARVIS_BOT_PORT:-7860}"
ADMIN_PORT=7861
WEB_PORT=5173

cmd="${1:-start}"

stop_all() {
  pkill -f "jarvis.bot.bot"        2>/dev/null
  pkill -f "jarvis.admin.server"   2>/dev/null
  pkill -f "vite"                  2>/dev/null
  sleep 1
  return 0
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
nohup ./scripts/run_bot.sh   > logs/bot.log   2>&1 &
BOT_PID=$!
nohup ./scripts/run_admin.sh > logs/admin.log 2>&1 &
ADMIN_PID=$!
nohup ./scripts/run_web.sh   > logs/web.log   2>&1 &
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
echo "Stop:  ./scripts/mortimer.sh stop"
