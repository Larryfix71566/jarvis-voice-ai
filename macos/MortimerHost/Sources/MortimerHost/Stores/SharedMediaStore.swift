import Foundation
import Observation

@MainActor
@Observable
final class SharedMediaStore {
    private(set) var lastDigest: String?
    private(set) var status = "idle"

    func begin(_ digest: String) { lastDigest = digest; status = "pending" }
    func complete() { status = "complete" }
    func fail() { status = "failed" }
    func reset() { lastDigest = nil; status = "idle" }
}
