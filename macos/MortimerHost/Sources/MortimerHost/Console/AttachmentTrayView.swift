import SwiftUI
import JarvisKit
import UniformTypeIdentifiers

struct AttachmentTrayView: View {
    @Environment(AttachmentStore.self) private var attachments
    @EnvironmentObject private var client: JarvisClient
    @Environment(TypedComposerModel.self) private var composer: TypedComposerModel?
    @State private var showPicker = false
    @State private var dropTargeted = false
    var onAsk: (() -> Void)?
    var onApproveOffer: (() -> Void)?
    var onDeclineOffer: (() -> Void)?
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            if let composer { TypedComposerRow(composer: composer) }
            HStack {
                if !attachments.staged.isEmpty {
                    Text("Staged content").font(.headline)
                }
                Spacer()
                Button("Paste") { paste() }
                    .accessibilityLabel("Paste content")
                Button("Choose") { showPicker = true }
                    .accessibilityLabel("Choose content")
            }
            if !attachments.staged.isEmpty {
                Text("Analysis provider: \(client.consoleInputProfile?.label ?? "Configured vision")")
                    .font(.caption)
                    .foregroundStyle(AppTheme.textDim)
            }
            if let offer = attachments.pendingOffer {
                VStack(alignment: .leading, spacing: 5) {
                    Text("Approval required").font(.subheadline.weight(.semibold))
                    Text("Send these selected items to \(offer.profile.label) for analysis? Memory saving will pause until reconnect.")
                        .font(.caption)
                    HStack {
                        Button("Send these items") { onApproveOffer?() }
                            .accessibilityLabel("Send these items")
                            .disabled(onApproveOffer == nil)
                        Button("Cancel these items") { onDeclineOffer?() }
                            .accessibilityLabel("Cancel these items")
                            .disabled(onDeclineOffer == nil)
                    }
                }
                .padding(8)
                .background(AppTheme.amber.opacity(0.12), in: RoundedRectangle(cornerRadius: 8))
                .accessibilityElement(children: .contain)
            }
            if attachments.staged.isEmpty {
                Label("Drop text or image files here", systemImage: "arrow.down.doc")
                    .font(.caption)
                    .foregroundStyle(dropTargeted ? AppTheme.accent : AppTheme.textDim)
                    .accessibilityLabel("Drop text or image files here")
                    .frame(maxWidth: .infinity, alignment: .center)
                    .padding(.vertical, 8)
                    .background((dropTargeted ? AppTheme.accent : AppTheme.hairline).opacity(0.12),
                                in: RoundedRectangle(cornerRadius: 8))
            }
            ForEach(attachments.staged, id: \.contentID) { item in
                HStack {
                    Text(item.kind.rawValue.capitalized)
                    Spacer()
                    Button(attachments.approvedIDs.contains(item.contentID) ? "Approved" : "Approve") { attachments.approve(item.contentID) }
                    Button("Remove") { attachments.remove(item.contentID) }
                }
            }
            if !attachments.staged.isEmpty {
                TextField("Question for Mortimer", text: Binding(
                    get: { attachments.question }, set: { attachments.setQuestion($0) }))
                    .textFieldStyle(.roundedBorder)
            }
            HStack {
                if let error = attachments.error { Text(error).foregroundStyle(AppTheme.red) }
                Spacer()
                if !attachments.staged.isEmpty {
                    Button("Clear") { attachments.clear() }
                    Button("Ask Mortimer") { onAsk?() }
                        // The tray is also used in previews and while the
                        // transport is being wired. Never present an enabled
                        // control that has no action behind it.
                        .disabled(onAsk == nil || attachments.approvedIDs.isEmpty ||
                                  attachments.question.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                        .help(onAsk == nil ? "Content analysis transport is not connected" : "Send the approved content to Mortimer")
                }
            }
        }
        .padding(12)
        .background(AppTheme.panel, in: RoundedRectangle(cornerRadius: 10))
        .onDrop(of: AttachmentIntake.dropTypeIdentifiers, isTargeted: $dropTargeted) { providers in
            AttachmentIntake.handleDrop(providers, into: attachments)
        }
        .fileImporter(isPresented: $showPicker, allowedContentTypes: AttachmentIntake.importContentTypes, allowsMultipleSelection: true) { result in
            AttachmentIntake.importFiles(result, into: attachments)
        }
    }

    private func paste() { AttachmentIntake.paste(into: attachments) }
}
