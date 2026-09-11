import Foundation

/// Geometry only: header scrolling never changes the selected tab or its model.
struct TabStripViewport: Equatable {
    var offset: CGFloat = 0
    var width: CGFloat = 0
    var contentWidth: CGFloat = 0

    private static let tolerance: CGFloat = 1
    var overflows: Bool { contentWidth > width + Self.tolerance }
    var canScrollBack: Bool { overflows && offset > Self.tolerance }
    var canScrollForward: Bool {
        overflows && offset + width < contentWidth - Self.tolerance
    }

    func target(forward: Bool, keys: [String], frames: [String: CGRect]) -> String? {
        guard forward ? canScrollForward : canScrollBack else { return nil }
        if forward {
            return keys.first { key in
                guard let frame = frames[key] else { return false }
                return frame.maxX > offset + width + Self.tolerance
            }
        }
        return keys.last { key in
            guard let frame = frames[key] else { return false }
            return frame.minX < offset - Self.tolerance
        }
    }
}
