#!/usr/bin/env bash
# One-time host installation. macOS asks the user for administrator approval.
# Version and checksums are pinned to the upstream 0.23.0 release.
set -euo pipefail
STAGING="$(mktemp -d)"
trap 'rm -rf "$STAGING"' EXIT
curl -fL https://github.com/cirruslabs/softnet/releases/download/0.23.0/softnet.tar.gz -o "$STAGING/softnet.tar.gz"
echo "b5daa4e5efaef3c2716f872dcda3961a35b2bddcdf03fe630ac3db0ab8156f3e  $STAGING/softnet.tar.gz" | shasum -a 256 -c -
tar -xzf "$STAGING/softnet.tar.gz" -C "$STAGING" softnet
cat > "$STAGING/install.sh" <<'SCRIPT'
#!/bin/bash
set -euo pipefail
DEST=/usr/local/libexec/mortimer-sandbox
/usr/bin/install -d -o root -g wheel -m 0755 "$DEST"
/usr/bin/install -o root -g wheel -m 0755 "$1" "$DEST/softnet.new"
echo "5982c8cde55cd039d4aa71add54356224b8b8a040df1a8786f16327b421f701d  $DEST/softnet.new" | /usr/bin/shasum -a 256 -c -
/bin/chmod 4755 "$DEST/softnet.new"
/bin/mv -f "$DEST/softnet.new" "$DEST/softnet"
SCRIPT
/usr/bin/osascript - "$STAGING/install.sh" "$STAGING/softnet" <<'APPLESCRIPT'
on run argv
    do shell script "/bin/bash " & quoted form of (item 1 of argv) & " " & quoted form of (item 2 of argv) with administrator privileges
end run
APPLESCRIPT
