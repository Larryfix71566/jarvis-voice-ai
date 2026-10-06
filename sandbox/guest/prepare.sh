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
# NLTK's locked package does not include the tokenizer data Pipecat's RTVI
# observer needs. Seed only the official pinned English data while online;
# hydration preserves this Python prefix as a read-only worker dependency.
.venv/bin/python - <<'PY'
import hashlib
import io
from pathlib import Path
import sys
import urllib.request
import zipfile

url = "https://raw.githubusercontent.com/nltk/nltk_data/gh-pages/packages/tokenizers/punkt_tab.zip"
archive_size = 4319076
archive_sha256 = "e57f64187974277726a3417ca6f181ec5403676c717672eef6a748a7b20e0106"
files = {
    "abbrev_types.txt": (619, "92a3e070f43d9b4c5534758ca40ad7343b04e7e29bfe0c2eb658a39445a4f779"),
    "collocations.tab": (594, "8e2da1225e4dd2cc9dba261ee231ccb134859e21b46006e7f472c5ee269af0cf"),
    "ortho_context.tab": (236303, "4bbcca25ed3d3f06c02402abf8419b9f033b8adc06e7b482eca4e45f81a5dc4c"),
    "sent_starters.txt": (241, "f3f8535483e1dba487241b764945168123bca3209a9645e59acd1225dc76edac"),
}

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, target):
        return None

opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
with opener.open(url, timeout=45) as response:
    raw = response.read(archive_size + 1)
if len(raw) != archive_size or hashlib.sha256(raw).hexdigest() != archive_sha256:
    raise SystemExit("Official English tokenizer archive does not match its pinned size and SHA-256.")

contents = {}
with zipfile.ZipFile(io.BytesIO(raw)) as archive:
    names = archive.namelist()
    for name, (size, expected_hash) in files.items():
        member = "punkt_tab/english/" + name
        if names.count(member) != 1 or archive.getinfo(member).file_size != size:
            raise SystemExit("Official English tokenizer member is missing, duplicate or invalid.")
        content = archive.read(member)
        if len(content) != size or hashlib.sha256(content).hexdigest() != expected_hash:
            raise SystemExit("Official English tokenizer member does not match its pinned SHA-256.")
        contents[name] = content

destination = Path(sys.prefix) / "share/nltk_data/tokenizers/punkt_tab/english"
destination.mkdir(parents=True, exist_ok=False)
for name, content in contents.items():
    path = destination / name
    path.write_bytes(content)
    if hashlib.sha256(path.read_bytes()).hexdigest() != files[name][1]:
        raise SystemExit("Installed English tokenizer does not match its pinned SHA-256.")

import nltk
resolved = Path(str(nltk.data.find("tokenizers/punkt_tab/english/"))).resolve()
if resolved != destination.resolve():
    raise SystemExit("Cold tokenizer resolved outside the prepared Python prefix.")
if nltk.sent_tokenize("First sentence. Second sentence.") != ["First sentence.", "Second sentence."]:
    raise SystemExit("Cold English tokenizer smoke failed.")
print("Pinned English tokenizer installed and cold tokenization verified.")
PY
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
