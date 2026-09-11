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
HERE="$(cd "$(dirname "$0")/.." && pwd)"
cd "$HERE"
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
open "$APP"
