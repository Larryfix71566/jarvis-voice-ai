import AppKit
import CoreGraphics
import Foundation

/// Read-only topology probe for the physical/virtual-display acceptance gate.
/// macOS Spaces are intentionally not queried: they do not appear in
/// NSScreen.screens and therefore cannot satisfy this gate.
let application = NSApplication.shared
application.setActivationPolicy(.accessory)

func rect(_ value: CGRect) -> [String: Double] {
    ["x": value.origin.x, "y": value.origin.y,
     "width": value.size.width, "height": value.size.height]
}

let screens = NSScreen.screens.enumerated().map { index, screen -> [String: Any] in
    let id = (screen.deviceDescription[NSDeviceDescriptionKey("NSScreenNumber")] as? NSNumber)?.uint32Value
    var entry: [String: Any] = [
        "index": index,
        "localized_name": screen.localizedName,
        "frame": rect(screen.frame),
        "visible_frame": rect(screen.visibleFrame),
        "backing_scale": screen.backingScaleFactor,
        "is_main": screen == NSScreen.main,
    ]
    if let id { entry["display_id"] = Int(id) }
    return entry
}

let payload: [String: Any] = [
    "recorded_by": "DisplayTopologyProbe",
    "screen_count": screens.count,
    "screens": screens,
    "spaces_are_not_screens": true,
]
let data = try JSONSerialization.data(withJSONObject: payload, options: [.prettyPrinted, .sortedKeys])
FileHandle.standardOutput.write(data)
FileHandle.standardOutput.write(Data("\n".utf8))
