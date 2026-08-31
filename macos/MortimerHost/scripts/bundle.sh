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
# The copied binary keeps its absolute LC_RPATH entries into .build/, so the
# WebRTC.xcframework SPM linked resolves from the bundle location on this
# machine. Local-run packaging only — not a distributable build.
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
codesign --force --sign - "$APP" >/dev/null 2>&1 || true
echo "bundled: $APP"
open "$APP"
