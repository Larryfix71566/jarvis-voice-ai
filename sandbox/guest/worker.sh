#!/usr/bin/env bash
# Establish an unprivileged execution account before loading any candidate.
set -euo pipefail
if [ "$(/usr/sbin/sysctl -n kern.hv_vmm_present 2>/dev/null)" != "1" ]; then
  echo "Worker setup must run inside a virtual machine." >&2
  exit 1
fi
if /usr/bin/id mortimer-dev >/dev/null 2>&1; then
  echo "Worker already exists; use a fresh prepared-image clone." >&2
  exit 1
fi
if [ -n "$(/usr/bin/dscl . -search /Users UniqueID 502)" ]; then
  echo "Reserved worker identity is already in use." >&2
  exit 1
fi
sudo -n /usr/bin/dscl . -create /Users/mortimer-dev
sudo -n /usr/bin/dscl . -create /Users/mortimer-dev UserShell /bin/bash
sudo -n /usr/bin/dscl . -create /Users/mortimer-dev UniqueID 502
sudo -n /usr/bin/dscl . -create /Users/mortimer-dev PrimaryGroupID 20
sudo -n /usr/bin/dscl . -create /Users/mortimer-dev NFSHomeDirectory /Users/mortimer-dev
sudo -n /usr/bin/dscl . -create /Users/mortimer-dev Password '*'
sudo -n /usr/bin/dscl . -create /Users/mortimer-dev IsHidden 1
sudo -n /bin/mkdir -p /Users/mortimer-dev
sudo -n /usr/sbin/chown mortimer-dev:staff /Users/mortimer-dev
sudo -n /bin/chmod 700 /Users/mortimer-dev

# Native authentication tests need a default Keychain. This contains only
# disposable test values and is created before any candidate code executes.
worker_keychain=/Users/mortimer-dev/Library/Keychains/sandbox.keychain-db
sudo -n -H -u mortimer-dev /bin/mkdir -p /Users/mortimer-dev/Library/Keychains /Users/mortimer-dev/Library/Preferences
sudo -n -H -u mortimer-dev /usr/bin/security create-keychain -p sandbox-test-only "$worker_keychain"
sudo -n -H -u mortimer-dev /usr/bin/security list-keychains -d user -s "$worker_keychain"
sudo -n -H -u mortimer-dev /usr/bin/security default-keychain -d user -s "$worker_keychain"
sudo -n -H -u mortimer-dev /usr/bin/security set-keychain-settings "$worker_keychain"
sudo -n -H -u mortimer-dev /usr/bin/security unlock-keychain -p sandbox-test-only "$worker_keychain"
sudo -n -H -u mortimer-dev /usr/bin/security default-keychain -d user >/dev/null
unset worker_keychain

# Public VM images have a known admin password. Replace it before candidate
# code runs; the host's Tart agent uses its existing privileged transport.
worker_admin_password="$(/usr/bin/openssl rand -hex 32)"
# Keep a random credential inside the disposable guest so the worker can
# auto-login when graphics-required verification restarts the clone.
worker_login_password="$(/usr/bin/openssl rand -hex 32)"
# Secure-token accounts require the image's existing administrator credential
# even when the caller is root. This is the public factory image password,
# never a password from the host Mac or its vault.
/usr/bin/dscl . -authonly admin admin >/dev/null 2>&1
sudo -n /usr/sbin/sysadminctl -adminUser admin -adminPassword admin \
  -resetPasswordFor admin -newPassword "$worker_admin_password" >/dev/null 2>&1
/usr/bin/dscl . -authonly admin "$worker_admin_password" >/dev/null 2>&1
if /usr/bin/dscl . -authonly admin admin >/dev/null 2>&1; then
  echo "Image administrator credential was not replaced." >&2
  exit 1
fi
# Tart's command agent starts in the image's login session. Update its
# automatic-login credential as well so controlled tasks survive a restart.
sudo -n /usr/sbin/sysadminctl -autologin set -userName admin -password "$worker_admin_password" \
  -adminUser admin -adminPassword "$worker_admin_password" >/dev/null 2>&1
sudo -n /usr/sbin/sysadminctl -adminUser admin -adminPassword "$worker_admin_password" \
  -resetPasswordFor mortimer-dev -newPassword "$worker_login_password" >/dev/null 2>&1
sudo -n /usr/sbin/sysadminctl -autologin set -userName mortimer-dev -password "$worker_login_password" \
  -adminUser admin -adminPassword "$worker_admin_password" >/dev/null 2>&1
sudo -n /usr/sbin/chown root:wheel /etc/kcpassword
sudo -n /bin/chmod 600 /etc/kcpassword
unset worker_login_password
unset worker_admin_password
sudo -n /bin/chmod o+x /Users/admin

# Share the installed browser engine read-only, independent of either user's
# mutable browser profile and cache directory.
if [ -d /Users/admin/Library/Caches/ms-playwright ]; then
  /bin/mv /Users/admin/Library/Caches/ms-playwright /Users/admin/mortimer/browser-engines
  /bin/chmod -R a+rX /Users/admin/mortimer/browser-engines
fi
if sudo -n -u mortimer-dev /usr/bin/sudo -n /usr/bin/true >/dev/null 2>&1; then
  echo "Worker unexpectedly has administrator access." >&2
  exit 1
fi
echo "Unprivileged candidate worker ready."
