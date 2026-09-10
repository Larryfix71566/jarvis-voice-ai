#!/usr/bin/env bash
# Development data services only. Provider-backed voice requires the future
# scoped API proxy and is not silently pointed at production credentials.
set -euo pipefail
ROOT=/Users/admin/mortimer
cd "$ROOT/source"
source "$ROOT/development.env"
mkdir -p "$ROOT/logs"
for service in knowledge admin costs; do
  pidfile="$ROOT/state/$service.pid"
  if [ -f "$pidfile" ] && kill -0 "$(cat "$pidfile")" 2>/dev/null; then
    continue
  fi
  case "$service" in
    knowledge) command=(services/mortimer-vault/.venv/bin/mortimer-vault serve) ;;
    admin) command=(.venv/bin/python -m jarvis.admin.server) ;;
    costs) command=(.venv/bin/python -m jarvis.costs_api) ;;
  esac
  nohup "${command[@]}" > "$ROOT/logs/$service.log" 2>&1 < /dev/null &
  echo "$!" > "$pidfile"
done
echo 'Guest previews: knowledge http://127.0.0.1:8484/health; admin http://127.0.0.1:7861/api/health'
echo 'Run or debug MortimerHost in Xcode inside the VM desktop.'
