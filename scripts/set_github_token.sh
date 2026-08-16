#!/usr/bin/env bash
#
# set_github_token.sh — safely replace a GitHub token in .env
#
#   ./scripts/set_github_token.sh                     # GITHUB_TOKEN (mcp_apps)
#   ./scripts/set_github_token.sh JARVIS_GITHUB_TOKEN # self-edit service
#
# Why this exists (MORTIMER_AGENT_TRUST_PLAN.md §1.5, §7.1): a revoked
# GITHUB_TOKEN produced a two-day silent outage of every Developer file
# operation while scripts/check_env.py still reported PASS. Rotating it by
# hand went wrong repeatedly for three reasons this script removes:
#
#   1. The token was never verified, so a bad paste looked identical to a
#      bad token. Here it is checked against the GitHub API BEFORE .env is
#      touched — a failed check aborts without modifying anything.
#   2. .env is read ONCE at process start (scripts/run_bot.sh does
#      `set -a; . ./.env`) and the MCP servers inherit that environment when
#      they are spawned. Editing .env under a running stack changes nothing.
#      This script says so at the end; you must restart.
#   3. A token pasted as a command argument is visible in `ps` and lands in
#      shell history. Here it is read with `read -rs` (no echo, not a
#      command argument) and handed to python via the environment.
#
# The token is never printed, never written to a log, and never passed in
# argv. The backup file it writes DOES contain the old token — .gitignore
# covers `.env.bak*` for that reason. A real token was committed to this
# repo's history once already (commit 07f5400); do not let it happen twice.

set -euo pipefail
cd "$(dirname "$0")/.."

ENV_FILE=".env"
VAR="${1:-GITHUB_TOKEN}"

case "$VAR" in
  GITHUB_TOKEN|JARVIS_GITHUB_TOKEN) ;;
  *)
    echo "refusing: expected GITHUB_TOKEN or JARVIS_GITHUB_TOKEN, got '$VAR'" >&2
    exit 1
    ;;
esac

if [ ! -f "$ENV_FILE" ]; then
  echo "no $ENV_FILE here — run this from the repo root" >&2
  exit 1
fi

printf 'Paste the new %s (input hidden), then press Enter: ' "$VAR" >&2
IFS= read -rs NEW_TOKEN
printf '\n' >&2

if [ -z "${NEW_TOKEN:-}" ]; then
  echo "empty input — nothing changed" >&2
  exit 1
fi
export NEW_TOKEN VAR ENV_FILE

# --- 1. verify BEFORE writing -------------------------------------------
# A 401 here means the token is dead. Aborting now leaves the previous
# value intact rather than replacing one broken token with another.
echo "verifying against api.github.com…" >&2
python3 <<'PY'
import json, os, sys, urllib.error, urllib.request

token = os.environ["NEW_TOKEN"]
var = os.environ["VAR"]
req = urllib.request.Request(
    "https://api.github.com/user",
    headers={"Authorization": f"Bearer {token}",
             "Accept": "application/vnd.github+json",
             "User-Agent": "mortimer-set-token"},
)
try:
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.loads(r.read())
        scopes = r.headers.get("x-oauth-scopes") or ""
except urllib.error.HTTPError as e:
    print(f"  FAILED: HTTP {e.code} {e.reason}", file=sys.stderr)
    print("  The token is invalid, expired, or revoked. .env NOT modified.",
          file=sys.stderr)
    sys.exit(1)
except Exception as e:  # noqa: BLE001
    print(f"  Could not reach GitHub ({type(e).__name__}). .env NOT modified.",
          file=sys.stderr)
    sys.exit(1)

print(f"  OK — authenticated as {data.get('login')}")
print(f"  scopes: {scopes or '(none reported — fine-grained token)'}")

# mcp_apps/github.py needs a repo-capable PAT: app_create makes private
# repositories, which classic tokens express as the `repo` scope. A token
# that authenticates but cannot create repos fails LATER, as a confusing
# 403 on app_create only — so warn about it now, at the point of change.
if var == "GITHUB_TOKEN" and scopes and "repo" not in scopes.split(", "):
    print("  WARNING: 'repo' scope not present. app_create/app_write_file "
          "will fail with 403 even though this token authenticates.",
          file=sys.stderr)
PY

# --- 2. back up ----------------------------------------------------------
BACKUP="${ENV_FILE}.bak.$(date +%Y%m%d-%H%M%S)"
cp -p "$ENV_FILE" "$BACKUP"
chmod 600 "$BACKUP"
echo "backed up $ENV_FILE -> $BACKUP (contains the OLD token; gitignored)" >&2

# --- 3. rewrite the single line -----------------------------------------
# Done in python rather than sed -i, which is not portable between macOS
# (BSD) and Linux, and which would need the token as an argument.
python3 <<'PY'
import os

path = os.environ["ENV_FILE"]
var = os.environ["VAR"]
token = os.environ["NEW_TOKEN"]

with open(path, "r", encoding="utf-8") as fh:
    lines = fh.readlines()

out, replaced = [], False
for line in lines:
    if line.startswith(f"{var}="):
        out.append(f"{var}={token}\n")
        replaced = True
    else:
        out.append(line)

if not replaced:
    if out and not out[-1].endswith("\n"):
        out.append("\n")
    out.append(f"{var}={token}\n")

tmp = path + ".tmp"
fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, "w", encoding="utf-8") as fh:
    fh.write("".join(out))
os.replace(tmp, path)   # atomic: no window where .env is half-written
os.chmod(path, 0o600)

print(f"  {var} {'replaced' if replaced else 'appended'} in {path}")
PY

unset NEW_TOKEN

cat <<'EOF' >&2

Done. The running stack is STILL using the old value.

.env is read once at process start and the MCP skill servers inherit that
environment when spawned, so a full restart is required:

    ./scripts/mortimer.sh

Then confirm it reached the tool layer by asking Mortimer something that
uses the app tools (for example: "list my registered apps").
EOF
