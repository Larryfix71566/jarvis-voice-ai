#!/bin/bash
# Closure C5.1: prove the worker owns an active, unoccluded desktop session
# before any native AppKit check runs. Runs as the unprivileged worker in
# the guest; exit 0 only when a real window reports itself visible and the
# login keychain accepts a write without a SecurityAgent prompt.
set -u
echo "identity=$(/usr/bin/id -un):$(/usr/bin/id -u) manager=$(/bin/launchctl managername 2>/dev/null) manageruid=$(/bin/launchctl manageruid 2>/dev/null) console=$(/usr/bin/stat -f '%Su' /dev/console)"
if [ "$(/bin/launchctl managername 2>/dev/null)" != "Aqua" ] || [ "$(/usr/bin/stat -f '%Su' /dev/console)" != "$(/usr/bin/id -un)" ]; then
  echo "desktop=absent reason=not-the-console-user-in-an-Aqua-session"; exit 2
fi
if /bin/ps -axo command | /usr/bin/grep -q "^/System/Library/CoreServices/Setup Assistant.app"; then
  echo "desktop=absent reason=setup-assistant-running"; exit 3
fi
probe_dir="$(/usr/bin/mktemp -d /tmp/desktop-probe.XXXXXX)"
/bin/cat > "$probe_dir/probe.swift" <<'SW'
import AppKit
let app = NSApplication.shared
app.setActivationPolicy(.regular)
app.finishLaunching()
app.activate(ignoringOtherApps: true)
let window = NSWindow(contentRect: NSRect(x: 120, y: 120, width: 320, height: 200), styleMask: [.titled], backing: .buffered, defer: false)
window.title = "desktop probe"
window.makeKeyAndOrderFront(nil)
// Pump AppKit events the way MortimerHostTests.WindowVisibilityTests does;
// occlusion changes arrive as window-server events, not via the run loop alone.
let deadline = Date().addingTimeInterval(2.0)
var visible = false
while Date() < deadline {
    if let event = app.nextEvent(matching: .any, until: Date().addingTimeInterval(0.01), inMode: .default, dequeue: true) { app.sendEvent(event) }
    app.updateWindows()
    RunLoop.main.run(until: Date().addingTimeInterval(0.005))
    visible = window.occlusionState.contains(.visible)
    if visible { break }
}
print("window visible=\(visible) isVisible=\(window.isVisible) activeSpace=\(window.isOnActiveSpace) appActive=\(app.isActive) screens=\(NSScreen.screens.count)")
exit(visible && window.isVisible ? 0 : 4)
SW
if ! /usr/bin/xcrun swiftc -O "$probe_dir/probe.swift" -o "$probe_dir/probe" >"$probe_dir/build.log" 2>&1; then
  echo "desktop=unknown reason=probe-build-failed"; /usr/bin/tail -5 "$probe_dir/build.log"; exit 5
fi
"$probe_dir/probe"; status=$?
if [ "$status" -ne 0 ]; then echo "desktop=absent reason=window-not-visible"; exit "$status"; fi
# The login keychain must be unlocked by the session (no password is known
# here); a locked keychain would raise a SecurityAgent prompt and hang.
keychain="$HOME/Library/Keychains/login.keychain-db"
/usr/bin/security add-generic-password -U -a desktop-probe -s desktop-probe -w probe-only "$keychain" >/dev/null 2>&1 &
pid=$!
for _ in $(seq 1 40); do /bin/kill -0 "$pid" 2>/dev/null || break; /bin/sleep 0.5; done
if /bin/kill -0 "$pid" 2>/dev/null; then /bin/kill "$pid" 2>/dev/null; echo "desktop=absent reason=keychain-prompt-pending"; exit 6; fi
wait "$pid" || { echo "desktop=absent reason=keychain-write-failed"; exit 7; }
/usr/bin/security delete-generic-password -a desktop-probe -s desktop-probe "$keychain" >/dev/null 2>&1
/bin/rm -rf "$probe_dir"
echo "desktop=visible keychain=unlocked"
exit 0
