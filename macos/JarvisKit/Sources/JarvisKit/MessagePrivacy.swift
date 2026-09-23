import Foundation

/// Privacy latch used by inbound shared-content flows. It is explicit and
/// session-scoped; enabling it never implies upload or memory persistence.
public struct MessagePrivacy: Codable, Sendable, Equatable {
    public let sessionID: UUID
    public private(set) var approvedContentIDs: Set<UUID>
    public private(set) var memoryAllowed: Bool

    public init(sessionID: UUID, memoryAllowed: Bool = false) {
        self.sessionID = sessionID; self.memoryAllowed = memoryAllowed
        self.approvedContentIDs = []
    }

    public mutating func approve(_ id: UUID) { approvedContentIDs.insert(id) }
    public mutating func revoke(_ id: UUID) { approvedContentIDs.remove(id) }
    public mutating func setMemoryAllowed(_ allowed: Bool) { memoryAllowed = allowed }
    public func canTransfer(_ id: UUID) -> Bool { approvedContentIDs.contains(id) }
}
