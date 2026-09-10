#!/usr/bin/env bash
# Development data services only. Provider-backed voice requires the future
# scoped API proxy and is not silently pointed at production credentials.
set -euo pipefail
ROOT=/Users/admin/mortimer
cd "$ROOT/source"
source "$ROOT/development.env"
mkdir -p "$ROOT/logs"
for service in knowledge admin costs web; do
  pidfile="$ROOT/state/$service.pid"
  if [ -f "$pidfile" ] && kill -0 "$(cat "$pidfile")" 2>/dev/null; then
    continue
  fi
  case "$service" in
    knowledge) command=(services/mortimer-vault/.venv/bin/mortimer-vault serve) ;;
    admin) command=(.venv/bin/python -m jarvis.admin.server) ;;
    costs) command=(.venv/bin/python -m uvicorn jarvis.costs_api:app --host 127.0.0.1 --port 8487) ;;
    web) command=(npm --prefix web run dev -- --host 127.0.0.1 --port 5173 --strictPort) ;;
  esac
  nohup "${command[@]}" > "$ROOT/logs/$service.log" 2>&1 < /dev/null &
  echo "$!" > "$pidfile"
done
.venv/bin/python - <<'PY'
import time
import urllib.error
import urllib.request

pending = {
    'knowledge': 'http://127.0.0.1:8484/health',
    'admin': 'http://127.0.0.1:7861/api/health',
    'costs': 'http://127.0.0.1:8487/costs/summary',
    'web': 'http://127.0.0.1:5173/',
}
deadline = time.monotonic() + 45
while pending and time.monotonic() < deadline:
    for name, url in list(pending.items()):
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    print(f'{name}: ready at {url}', flush=True)
                    del pending[name]
        except (OSError, urllib.error.URLError):
            pass
    if pending:
        time.sleep(0.5)
if pending:
    raise SystemExit('Preview startup failed; check guest logs for: ' + ', '.join(pending))
PY
echo 'Run or debug MortimerHost in Xcode inside the VM desktop.'
