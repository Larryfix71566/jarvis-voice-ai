import SwiftUI
import JarvisKit

/// Native, owner-scoped skill creation flow. The sandbox owns task text and
/// candidate files; this view holds only its transient form and review result.
struct SkillCreatorSheet: View {
    @Environment(\.dismiss) private var dismiss
    let client: JarvisClient
    let catalogRevision: String
    let voiceDraft: SkillsStore.VoiceDraftRequest?

    @State private var skillID = ""
    @State private var brief = ""
    @State private var draftID: String?
    @State private var status: JSONValue?
    @State private var error: String?
    @State private var sending = false
    @State private var startedVoiceDraft = false

    init(client: JarvisClient, catalogRevision: String,
         voiceDraft: SkillsStore.VoiceDraftRequest? = nil) {
        self.client = client
        self.catalogRevision = catalogRevision
        self.voiceDraft = voiceDraft
    }

    private var state: String { status?["state"]?.stringValue ?? "" }
    private var reviewFiles: [JSONValue] { status?["review"]?["files"]?.arrayValue ?? [] }
    private var canPublish: Bool {
        state == "review_ready"
            && status?["review"]?["candidate_digest"]?.stringValue?.count == 64
            && status?["review"]?["skill_revision"]?.stringValue?.count == 64
            && !reviewFiles.isEmpty
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                Text("Create a skill").font(.title2.weight(.semibold))
                Spacer()
                Button("Done") { dismiss() }.disabled(sending)
            }
            if draftID == nil {
                TextField("Skill slug (for example, meeting-prep)", text: $skillID)
                    .textFieldStyle(.roundedBorder)
                    .accessibilityLabel("New skill slug")
                Text("Describe the reusable skill you want Mortimer to draft. The request runs in the existing disposable sandbox.")
                    .font(.callout).foregroundStyle(AppTheme.textDim)
                TextEditor(text: $brief)
                    .font(.body)
                    .frame(minHeight: 110)
                    .overlay(RoundedRectangle(cornerRadius: 8).stroke(AppTheme.textDim.opacity(0.35)))
                    .accessibilityLabel("Skill creation brief")
                Button("Start sandbox draft") { Task { await startDraft() } }
                    .buttonStyle(.borderedProminent)
                    .disabled(sending || skillID.isEmpty || brief.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            } else {
                Text("Skill: \(skillID)").font(.headline)
                Text(status?["result_code"]?.stringValue ?? state.replacingOccurrences(of: "_", with: " ").capitalized)
                    .font(.callout).foregroundStyle(AppTheme.textDim)
                if let runID = status?["developer_run_id"]?.stringValue, !runID.isEmpty {
                    Label {
                        Text("Developer run · \(runID)").textSelection(.enabled)
                    } icon: {
                        Image(systemName: "cpu")
                    }
                    .font(.caption.monospaced())
                    .foregroundStyle(AppTheme.textDim)
                    .accessibilityLabel("Developer agent run identifier \(runID)")
                }
                if let jobID = status?["sandbox_job_id"]?.stringValue, !jobID.isEmpty {
                    Label {
                        Text("Sandbox job · \(jobID)").textSelection(.enabled)
                    } icon: {
                        Image(systemName: "shippingbox")
                    }
                    .font(.caption.monospaced())
                    .foregroundStyle(AppTheme.textDim)
                    .accessibilityLabel("Sandbox job identifier \(jobID)")
                }
                if canPublish {
                    Text("Review the exact sandbox diff before opening a pull request.")
                        .font(.callout)
                    ScrollView {
                        VStack(alignment: .leading, spacing: 12) {
                            ForEach(Array(reviewFiles.enumerated()), id: \.offset) { _, file in
                                VStack(alignment: .leading, spacing: 6) {
                                    Text(file["path"]?.stringValue ?? "Candidate file")
                                        .font(.caption.monospaced().weight(.semibold))
                                    Text(file["diff"]?.stringValue ?? "")
                                        .font(.system(.caption, design: .monospaced))
                                        .textSelection(.enabled)
                                        .frame(maxWidth: .infinity, alignment: .leading)
                                        .padding(10)
                                        .background(AppTheme.panel, in: RoundedRectangle(cornerRadius: 8))
                                }
                            }
                        }
                    }
                    .frame(minHeight: 160)
                    Button("Open review PR") { Task { await publishReviewedCandidate() } }
                        .buttonStyle(.borderedProminent)
                        .accessibilityHint("Submits only the candidate digest shown above for maintainer review. It does not merge or activate the skill.")
                } else if state == "completed", let url = status?["pr_url"]?.stringValue,
                          let link = URL(string: url) {
                    Link("Open pull request", destination: link)
                } else if ["queued", "starting", "drafting", "cancel_requested"].contains(state) {
                    ProgressView("Sandbox work: \(state.isEmpty ? "starting" : state)…")
                    Button("Cancel sandbox work", role: .destructive) { Task { await cancelDraft() } }
                        .disabled(sending)
                } else if state == "publishing" {
                    ProgressView("Opening the reviewed pull request…")
                } else if state == "publication_needs_reconciliation" {
                    Text("The publisher outcome needs reconciliation. No automatic retry was made.")
                        .foregroundStyle(AppTheme.red)
                } else if state == "draft_needs_attention" || state == "failed" {
                    Text("The candidate needs attention. No review PR was opened.")
                        .foregroundStyle(AppTheme.red)
                }
            }
            if let error { Text(error).font(.callout).foregroundStyle(AppTheme.red) }
        }
        .padding(20)
        .frame(minWidth: 480, minHeight: 420)
        .background(AppTheme.bg)
        .onAppear {
            guard let voiceDraft, !startedVoiceDraft else { return }
            startedVoiceDraft = true
            Task { await startDraft(skillID: voiceDraft.skillID, brief: voiceDraft.taskBrief) }
        }
    }

    @MainActor
    private func startDraft(skillID overrideSkillID: String? = nil, brief overrideBrief: String? = nil) async {
        let requestedSkillID = overrideSkillID ?? skillID
        let requestedBrief = overrideBrief ?? brief
        guard validSlug(requestedSkillID), requestedBrief.count <= 8_000 else {
            error = "Use a lowercase hyphenated slug and a brief of at most 8,000 characters."
            return
        }
        guard let sessionID = client.consoleSessionID?.uuidString.lowercased() else {
            error = "Connect Mortimer before starting a skill draft so it can run under the active Developer session."
            return
        }
        skillID = requestedSkillID
        brief = requestedBrief
        sending = true
        let requestID: String
        do {
            let request = SkillAuthoringRequest(operation: "draft", expectedCatalogRevision: catalogRevision,
                skillID: requestedSkillID, botSessionID: sessionID, taskBrief: requestedBrief)
            let created = try await AdminAPI(config: client.config).createSkillRequest(request)
            guard let id = created["request_id"]?.stringValue else {
                throw JarvisError.decoding("Mortimer returned no request identifier")
            }
            draftID = id
            requestID = id
            status = created
            sending = false
        } catch {
            sending = false
            self.error = "Could not start the sandbox draft. Check Mortimer's connection and retry."
            return
        }
        await poll(requestID: requestID, until: ["review_ready", "draft_needs_attention", "failed", "cancelled"])
    }

    @MainActor
    private func publishReviewedCandidate() async {
        guard let draftID,
              let digest = status?["review"]?["candidate_digest"]?.stringValue,
              let revision = status?["review"]?["skill_revision"]?.stringValue else { return }
        await withSending {
            do {
                let request = SkillAuthoringRequest(operation: "request_publish", expectedCatalogRevision: catalogRevision,
                    skillID: skillID, skillRevision: revision, reviewArtifactRef: draftID,
                    candidateDigest: digest)
                let response = try await AdminAPI(config: client.config).createSkillRequest(request)
                status = response
                await poll(requestID: response["request_id"]?.stringValue ?? "", until: ["completed", "failed", "publication_needs_reconciliation"])
            } catch { self.error = "The reviewed candidate was not submitted. Refresh the Skills view and inspect its current status." }
        }
    }

    @MainActor
    private func cancelDraft() async {
        guard let draftID else { return }
        await withSending {
            do {
                let request = SkillAuthoringRequest(operation: "cancel", expectedCatalogRevision: catalogRevision,
                    skillID: skillID, jobID: draftID)
                let response = try await AdminAPI(config: client.config).createSkillRequest(request)
                status = response
            } catch { self.error = "Could not confirm sandbox cancellation. Refresh the request status." }
        }
    }

    @MainActor
    private func poll(requestID: String, until terminalStates: Set<String>) async {
        guard !requestID.isEmpty else { return }
        for _ in 0..<600 {
            if terminalStates.contains(state) { return }
            do {
                try await Task.sleep(for: .seconds(1))
                status = try await AdminAPI(config: client.config).skillRequestStatus(id: requestID)
            } catch {
                self.error = "Lost the request status connection. Reopen this Skills request to continue."
                return
            }
        }
        error = "The request is still running. Close this view and check its status again later."
    }

    @MainActor
    private func withSending(_ operation: () async -> Void) async {
        sending = true
        defer { sending = false }
        await operation()
    }

    private func validSlug(_ value: String) -> Bool {
        !value.isEmpty && value.count <= 64
            && value.range(of: "^[a-z0-9]+(?:-[a-z0-9]+)*$", options: .regularExpression) != nil
    }
}
