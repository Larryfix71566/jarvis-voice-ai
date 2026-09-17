#!/usr/bin/env bash
# Wrap the SPM-built MortimerHost executable in a real .app bundle and launch it.
#
# Why (2026-08-31): run as a bare executable (`swift run` / Xcode running the
# SPM target) the process is not a full application to macOS — no menu bar,
# unreliable cursor tracking at window edges, and native Full Screen (a
# Spaces feature) is refused even with NSWindowCollectionBehaviorFullScreenPrimary
# set. A bundle with an Info.plist fixes all three, gives a Dock icon, and is
# what the microphone permission prompt attributes to the app.
#
# Usage:  macos/MortimerHost/scripts/bundle.sh [debug|release]   (default debug)
# Output: macos/MortimerHost/.build/MortimerHost.app  (then `open`s it)
#
# SPM resolves WebRTC beside the executable. Copy its resolved framework next
# to the executable, alongside SPM resource bundles, so launch does not depend
# on the executable remaining in SPM's build-products directory. Ad-hoc signing
# is for local testing; this is not a notarized distribution package.
set -euo pipefail
CONFIG="${1:-debug}"
case "$CONFIG" in debug|release) ;; *) echo "Expected debug or release" >&2; exit 2 ;; esac
HERE="$(cd "$(dirname "$0")/.." && pwd)"
cd "$HERE"
# Git is absent in a sanitized sandbox snapshot. The release driver can
# supply its immutable source revision; otherwise record what Git knows,
# or 'unknown'. Never mistake a constant bundle version for build provenance.
SOURCE_REVISION="${MORTIMER_SOURCE_REVISION:-$(git rev-parse HEAD 2>/dev/null || echo unknown)}"
if [[ "$SOURCE_REVISION" != "unknown" && ! "$SOURCE_REVISION" =~ ^[0-9a-f]{40}$ ]]; then
  echo "MORTIMER_SOURCE_REVISION must be a full Git revision" >&2; exit 2
fi
CANDIDATE_FINGERPRINT="${MORTIMER_CANDIDATE_FINGERPRINT:-unknown}"
if [[ "$CANDIDATE_FINGERPRINT" != "unknown" && ! "$CANDIDATE_FINGERPRINT" =~ ^[0-9a-f]{64}$ ]]; then
  echo "MORTIMER_CANDIDATE_FINGERPRINT must be a full source digest" >&2; exit 2
fi
SOURCE_DIRTY="unknown"
if git rev-parse --git-dir >/dev/null 2>&1; then
  SOURCE_DIRTY="false"
  if [ -n "$(git status --porcelain --untracked-files=normal)" ]; then SOURCE_DIRTY="true"; fi
fi
swift build -c "$CONFIG"
BIN="$HERE/.build/$CONFIG/MortimerHost"
APP="$HERE/.build/MortimerHost.app"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "$BIN" "$APP/Contents/MacOS/MortimerHost"
# Resource bundles SPM produced (e.g. JarvisKit_JarvisKit.bundle) sit beside
# the binary; Bundle.module looks for them next to the executable.
for b in "$HERE/.build/$CONFIG"/*.bundle; do
  [ -e "$b" ] && cp -R "$b" "$APP/Contents/MacOS/"
done
for framework in "$HERE/.build/$CONFIG"/*.framework; do
  [ -e "$framework" ] && cp -R "$framework" "$APP/Contents/MacOS/"
done
if [ ! -f "$APP/Contents/MacOS/WebRTC.framework/WebRTC" ]; then
  echo "Missing bundled WebRTC runtime; refusing to launch." >&2
  exit 1
fi
cat > "$APP/Contents/Info.plist" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleDevelopmentRegion</key><string>en</string>
  <key>CFBundleExecutable</key><string>MortimerHost</string>
  <key>CFBundleIdentifier</key><string>com.mortimer.host</string>
  <key>CFBundleInfoDictionaryVersion</key><string>6.0</string>
  <key>CFBundleName</key><string>Mortimer</string>
  <key>CFBundleDisplayName</key><string>Mortimer</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>0.1</string>
  <key>CFBundleVersion</key><string>1</string>
  <key>MortimerSourceRevision</key><string>$SOURCE_REVISION</string>
  <key>MortimerCandidateFingerprint</key><string>$CANDIDATE_FINGERPRINT</string>
  <key>MortimerSourceDirty</key><string>$SOURCE_DIRTY</string>
  <key>MortimerBuildConfiguration</key><string>$CONFIG</string>
  <key>LSMinimumSystemVersion</key><string>26.0</string>
  <key>NSPrincipalClass</key><string>NSApplication</string>
  <key>NSHighResolutionCapable</key><true/>
  <key>NSMicrophoneUsageDescription</key>
  <string>Mortimer listens to you through the microphone for voice conversation and the wake word.</string>
  <key>NSSupportsAutomaticTermination</key><false/>
  <key>NSSupportsSuddenTermination</key><false/>
</dict>
</plist>
PLIST
# Ad-hoc sign so TCC (microphone) attributes the grant to a stable identity.
# SPM's resolved framework is not necessarily signed. Sign only our embedded
# copy, then seal the containing app and verify both before attempting launch.
for framework in "$APP/Contents/MacOS"/*.framework; do
  [ -d "$framework" ] || continue
  codesign --force --sign - "$framework"
done
codesign --force --sign - "$APP"
codesign --verify --deep --strict "$APP"
echo "bundled: $APP"
if [ "${MORTIMER_BUNDLE_LAUNCH:-1}" != "0" ]; then
  open "$APP"
fi
