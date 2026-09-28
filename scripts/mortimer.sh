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

# 2026-09-06 — under launchd this script used to REFUSE, printing a hint
# that named only com.mortimer.bot (one of five) and exiting 3. So "one
# command to start or restart the whole stack" stopped being true in the
# one configuration that actually ships. launchd owns the processes, but
# restarting them is still one command; it is just kickstart rather than
# pkill-then-spawn.
#
# Order matters: bot's ProgramArguments wait on vault's port 8484 via
# wait_for.sh, so vault goes first and bot last.
#
# Rotation matters too: the plists write to logs/<svc>.launchd.log, a
# DIFFERENT file from the logs/<svc>.log this script rotates, and nothing
# rotated those at all — they grew without bound. Rotating them here keeps
# the promise the header makes about previous sessions surviving.
LAUNCHD_SERVICES=(vault admin extractor costs bot)

under_launchd() {
  launchctl print "gui/$(id -u)/com.mortimer.bot" >/dev/null 2>&1
}

launchd_restart() {
  echo "Mortimer is under launchd — restarting its services."
  mkdir -p logs
  local s failed=0
  for s in "${LAUNCHD_SERVICES[@]}"; do rotate_log "${s}.launchd"; done
  for s in "${LAUNCHD_SERVICES[@]}"; do
    if launchctl kickstart -k "gui/$(id -u)/com.mortimer.${s}" >/dev/null 2>&1; then
      echo "  restarted ${s}"
    else
      echo "  FAILED   ${s} — not installed? python scripts/launchd_gen.py --status" >&2
      failed=1
    fi
  done
  echo
  echo "Mortimer restarted. Logs: ./scripts/mortimer.sh logs"
  return $failed
}

case "$cmd" in
  stop)
    # Still refused under launchd, and this one is not a gap: every service
    # is KeepAlive=true, so killing it just respawns it. Stopping for real
    # means unloading the jobs.
    if under_launchd; then
      echo "Mortimer is under launchd — killing the processes would only respawn them (KeepAlive)." >&2
      echo "  stop for real : python scripts/launchd_gen.py --uninstall" >&2
      echo "  what is loaded: python scripts/launchd_gen.py --status" >&2
      echo "  just restart  : ./scripts/mortimer.sh" >&2
      exit 3
    fi
    stop_all
    echo "Mortimer stopped."
    exit 0
    ;;
  logs)
    # The plists write logs/<svc>.launchd.log; this used to tail only
    # logs/<svc>.log, so under launchd it followed files nothing was
    # writing to. Tail whatever exists, from both sets.
    files=()
    for f in logs/vault.log logs/bot.log logs/extractor.log logs/admin.log \
             logs/web.log logs/costs.log \
             logs/vault.launchd.log logs/bot.launchd.log \
             logs/extractor.launchd.log logs/admin.launchd.log \
             logs/costs.launchd.log; do
      [ -f "$f" ] && files+=("$f")
    done
    if [ ${#files[@]} -eq 0 ]; then echo "no logs yet — start Mortimer first" >&2; exit 1; fi
    exec tail -f "${files[@]}"
    ;;
  start)
    ;;
  *)
    echo "usage: $0 [start|stop|logs]" >&2
    exit 2
    ;;
esac

if under_launchd; then
  launchd_restart
  exit $?
fi

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

# Load the same runtime configuration consumed by run_bot.sh/run_admin.sh so
# the launcher's authenticated readiness probe uses the configured port.
set -a
. ./.env
set +a
ADMIN_PORT="${JARVIS_ADMIN_PORT:-7861}"

echo "Restarting Mortimer..."
stop_all

mkdir -p logs
rotate_log vault
rotate_log bot
rotate_log extractor
rotate_log admin
rotate_log costs

nohup ./scripts/run_kb.sh >> logs/vault.log 2>&1 &
VAULT_PID=$!
nohup bash -c "./scripts/wait_for.sh 127.0.0.1 ${VAULT_PORT} 30 vault && exec ./scripts/run_bot.sh" >> logs/bot.log 2>&1 &
BOT_PID=$!
nohup ./scripts/run_memory_extractor.sh >> logs/extractor.log 2>&1 &
EXTRACTOR_PID=$!
nohup ./scripts/run_admin.sh >> logs/admin.log 2>&1 &
ADMIN_PID=$!
nohup ./scripts/run_costs.sh >> logs/costs.log 2>&1 &
COSTS_PID=$!

# BIND_WAIT_S is 20 seconds. Wait longer before the readiness probe so a
# late Tailscale address cannot be reported as a healthy listener early.
sleep 25
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
check_admin() {
  if ! kill -0 "$ADMIN_PID" 2>/dev/null; then
    echo "  admin: FAILED to start — see logs/admin.log" >&2
    return
  fi
  if .venv/bin/python - <<'PY'
import os
from urllib.request import Request, urlopen

from jarvis.auth import service_headers
from jarvis.bind import resolve_bind_host
from jarvis.vault import inject_env

inject_env()
host = resolve_bind_host("admin-health-check")
port = int(os.environ.get("JARVIS_ADMIN_PORT", "7861"))
request = Request(f"http://{host}:{port}/api/health", headers=service_headers())
with urlopen(request, timeout=3) as response:
    if response.status != 200:
        raise SystemExit(f"health returned {response.status}")
PY
  then
    echo "  admin: healthy (authenticated /api/health on port $ADMIN_PORT)"
  else
    echo "  admin: running but authenticated health check failed — see logs/admin.log" >&2
  fi
}
check_admin
check costs     "$COSTS_PID"     "http://localhost:$COSTS_PORT"

echo
echo "Open MortimerHost (macos/MortimerHost, swift run or Xcode). Web console fallback: ./scripts/run_web.sh"
echo "Logs:  ./scripts/mortimer.sh logs   (or: tail -f logs/bot.log)"
echo "       previous sessions: logs/<name>.log.1 .. .${LOG_GENERATIONS}"
echo "Stop:  ./scripts/mortimer.sh stop"
