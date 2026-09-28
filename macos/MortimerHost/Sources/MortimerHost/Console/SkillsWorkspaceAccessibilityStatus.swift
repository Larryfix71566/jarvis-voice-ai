import AppKit

/// Produces short, content-free status announcements for asynchronous Skills
/// workspace updates. This state is separate from keyboard focus and view
/// selection so announcements never move either one.
struct SkillsWorkspaceAccessibilityStatus {
    enum Resource: String, CaseIterable {
        case catalog = "Skills library"
        case detail = "Skill details"
        case activity = "Skill activity"
        case versions = "Skill version evidence"
        case example = "Example preview"
    }

    enum Phase: String {
        case loading
        case loaded
        case failed
    }

    private(set) var lastPhaseByResource: [Resource: Phase] = [:]
    private(set) var selectedProcessStepID: String?
    private var hasObservedProcessStepSelection = false

    /// Returns nil when the same state was already announced. Messages never
    /// include skill names, task briefs, error text, or server-provided data.
    mutating func transition(resource: Resource, to phase: Phase) -> String? {
        guard lastPhaseByResource[resource] != phase else { return nil }
        lastPhaseByResource[resource] = phase
        switch phase {
        case .loading:
            return "\(resource.rawValue) loading."
        case .loaded:
            return "\(resource.rawValue) loaded."
        case .failed:
            return "\(resource.rawValue) could not be loaded. Retry when ready."
        }
    }

    /// Announces navigation initiated by voice or another shared action.
    /// The step identifier is used only for duplicate suppression and is never
    /// included in the spoken message.
    mutating func processStepSelectionChanged(to stepID: String?) -> String? {
        guard !hasObservedProcessStepSelection || selectedProcessStepID != stepID else { return nil }
        let previousStepID = selectedProcessStepID
        selectedProcessStepID = stepID
        hasObservedProcessStepSelection = true

        if stepID != nil { return "Process step selected." }
        return previousStepID == nil ? nil : "Process step collapsed."
    }

    @MainActor
    static func post(_ message: String) {
        NSAccessibility.post(
            element: NSApplication.shared,
            notification: .announcementRequested,
            userInfo: [
                .announcement: message,
                .priority: 10, // Low priority: do not interrupt current VoiceOver speech.
            ]
        )
    }
}
