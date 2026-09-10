#!/usr/bin/env bash
# Trusted image preparation only. Never run this on the host Mac.
set -euo pipefail
if [ "$(sysctl -n kern.hv_vmm_present 2>/dev/null)" != "1" ]; then
  echo "This setup must run inside the development VM." >&2
  exit 1
fi

ROOT=/Users/admin/mortimer
INPUT='/Volumes/My Shared Files/input'
export PATH=/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin
# The host gateway is deliberately blocked, including its DNS proxy.
# Resolve public package registries directly through public DNS instead.
sudo -n /usr/sbin/networksetup -setdnsservers Ethernet 1.1.1.1 8.8.8.8
mkdir -p "$ROOT/source" "$ROOT/state" "$ROOT/logs" "$ROOT/reports"
if [ -e "$ROOT/source/.git" ]; then
  echo "Use a fresh task; refusing to overwrite an existing development checkout." >&2
  exit 1
fi
tar -xf "$INPUT/source.tar" -C "$ROOT/source"
cd "$ROOT/source"
git init -q
git -c user.name='Mortimer Sandbox' -c user.email=sandbox@example.invalid add .
git -c user.name='Mortimer Sandbox' -c user.email=sandbox@example.invalid commit -qm 'Imported source'

# No host credentials are imported. These values satisfy configuration parsing
# for deterministic tests; they cannot authenticate to any provider.
cat > "$ROOT/development.env" <<'ENV'
export PATH=/opt/homebrew/opt/node@22/bin:/opt/homebrew/opt/python@3.12/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin
export OPENAI_API_KEY=sandbox-placeholder
export DEEPGRAM_API_KEY=sandbox-placeholder
export ELEVENLABS_API_KEY=sandbox-placeholder
export ANTHROPIC_API_KEY=sandbox-placeholder
export JARVIS_VAULT_ENABLED=false
export JARVIS_DB_PATH=/Users/admin/mortimer/state/jarvis.db
export JARVIS_COSTS_DB=/Users/admin/mortimer/state/costs.db
export MORTIMER_HOME=/Users/admin/mortimer/state/knowledge
export RUN_LIVE=0
export JARVIS_REMINDER_NOTIFICATIONS_ENABLED=false
ENV
source "$ROOT/development.env"
cp "$ROOT/development.env" .env
brew install python@3.12 node@22
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-lock.txt
bash scripts/setup_kb.sh
.venv/bin/python scripts/init_db.py
services/mortimer-vault/.venv/bin/mortimer-vault init
(cd web && npm ci)
for package in JarvisKit MortimerHost; do
  (cd "macos/$package" && swift package resolve)
done
npm install --prefix "$ROOT/browser" --save-exact playwright@1.63.0
"$ROOT/browser/node_modules/.bin/playwright" install chromium
{
  sw_vers
  xcodebuild -version
  swift --version
  .venv/bin/python --version
  node --version
} > "$ROOT/reports/toolchains.txt"
echo "Dependency preparation complete. Stop and restart offline before development."
