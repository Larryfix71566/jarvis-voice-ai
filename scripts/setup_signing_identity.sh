#!/bin/bash
# One-time, per Mac: create a local code-signing identity for Mortimer.
#
# Why (2026-09-30): bundle.sh signed ad hoc, and an ad-hoc signature's
# designated requirement is the build's cdhash (Larry's Mac showed
# `designated => cdhash H"74b9..."`). Every deploy rebuilds the app, the
# cdhash changes, and macOS asks for microphone and location again. Signing
# every build with the same certificate gives a requirement of
# `identifier "com.mortimer.host" and certificate leaf = H"..."`, which stays
# the same across rebuilds, so a permission granted once is kept.
#
# The certificate is self-signed, stays in this Mac's login keychain, and is
# trusted for code signing only. No Apple ID or Xcode needed. macOS asks for
# your login password once (to trust it). Safe to re-run: it stops if the
# identity already exists.
# Usage: bash scripts/setup_signing_identity.sh
set -euo pipefail
NAME="${MORTIMER_SIGN_IDENTITY:-Mortimer Local Code Signing}"
KC="$HOME/Library/Keychains/login.keychain-db"
OPENSSL=/usr/bin/openssl   # macOS LibreSSL: its PKCS#12 output imports cleanly
if security find-identity -p codesigning "$KC" 2>/dev/null | grep -q "\"$NAME\""; then
  echo "Already set up:"; security find-identity -p codesigning "$KC" | grep "\"$NAME\""; exit 0
fi
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
cat > "$T/cfg" <<CFG
[req]
distinguished_name = dn
x509_extensions = ext
prompt = no
[dn]
CN = $NAME
[ext]
basicConstraints = critical,CA:false
keyUsage = critical,digitalSignature
extendedKeyUsage = critical,codeSigning
subjectKeyIdentifier = hash
CFG
"$OPENSSL" req -x509 -newkey rsa:2048 -nodes -days 3650 -config "$T/cfg" \
  -keyout "$T/key.pem" -out "$T/cert.pem" 2>/dev/null
PW=$("$OPENSSL" rand -hex 16)
"$OPENSSL" pkcs12 -export -inkey "$T/key.pem" -in "$T/cert.pem" -name "$NAME" \
  -out "$T/id.p12" -passout "pass:$PW"
security import "$T/id.p12" -k "$KC" -P "$PW" -T /usr/bin/codesign >/dev/null
echo "Imported '$NAME'. macOS will now ask for your login password to trust it for code signing..."
security add-trusted-cert -r trustRoot -p codeSign -k "$KC" "$T/cert.pem"
echo
security find-identity -v -p codesigning "$KC" | grep "\"$NAME\"" \
  || { echo "STOPPED: the identity is not valid for code signing. Tell Claude."; exit 1; }
echo "Done. Builds made by bundle.sh on this Mac will now be signed with '$NAME'."
echo "If a 'codesign wants to use your keychain' dialog appears on the next build, choose Always Allow."
