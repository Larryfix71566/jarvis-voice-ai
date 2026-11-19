import SwiftUI
import JarvisKit

/// Interface cleanup Phase 2: the console's one composer. At rest it is a
/// single ~44 pt pill (paperclip menu, typed field, Send). Staged content
/// opens a compact review panel above it; nothing is sent without explicit
/// approval and the panel always shows what is shared and with which provider.
struct ComposerPillView: View {
    @Environment(AttachmentStore.self) private var attachments
    @Environment(TypedComposerModel.self) private var composer: TypedComposerModel?
    @State private var showPicker = false
    var onAsk: (() -> Void)?
    var onApproveOffer: (() -> Void)?
    var onDeclineOffer: (() -> Void)?

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            if !attachments.staged.isEmpty || attachments.pendingOffer != nil {
                StagedContentPanel(onAsk: onAsk, onApproveOffer: onApproveOffer,
                                   onDeclineOffer: onDeclineOffer)
            }
            pill
            caption
        }
        .fileImporter(isPresented: $showPicker, allowedContentTypes: AttachmentIntake.importContentTypes,
                      allowsMultipleSelection: true) { result in
            AttachmentIntake.importFiles(result, into: attachments)
        }
    }

    private var pill: some View {
        HStack(spacing: 8) {
            attachMenu
            if let composer {
                ComposerPillField(composer: composer)
            } else {
                TextField("Type a request", text: .constant(""))
                    .textFieldStyle(.plain)
                    .disabled(true)
                    .accessibilityLabel("Type a request")
                Button("Send") {}
                    .disabled(true)
                    .accessibilityLabel("Send request")
            }
        }
        .padding(.horizontal, 12)
        .frame(height: 44)
        .mortimerGlass(.panel)
    }

    private var attachMenu: some View {
        Menu {
            Button("Paste content") { AttachmentIntake.paste(into: attachments) }
                .accessibilityLabel("Paste content")
            Button("Choose content…") { showPicker = true }
                .accessibilityLabel("Choose content")
        } label: {
            Image(systemName: "paperclip")
        }
        .menuStyle(.borderlessButton)
        .menuIndicator(.hidden)
        .fixedSize()
        .accessibilityLabel("Attach content")
    }

    @ViewBuilder private var caption: some View {
        if let composer {
            if let reason = composer.disabledReason {
                Text(reason).font(.caption).foregroundStyle(AppTheme.textDim)
            } else if let notice = composer.notice {
                Text(notice).font(.caption).foregroundStyle(AppTheme.red)
            }
        }
    }
}

/// The typed field and Send, split out so it can hold the @Bindable composer
/// and the focus state; submit and disabled rules match TypedComposerRow.
private struct ComposerPillField: View {
    @Bindable var composer: TypedComposerModel
    @FocusState private var focused: Bool

    var body: some View {
        HStack(spacing: 8) {
            TextField("Type a request", text: $composer.draft)
                .textFieldStyle(.plain)
                .focused($focused)
                .disabled(composer.disabledReason != nil || composer.isSendingDraft)
                .onSubmit { composer.submitDraft() }
                .accessibilityLabel("Type a request")
            Button(composer.isSendingDraft ? "Sending…" : "Send") { composer.submitDraft() }
                .disabled(!composer.canSubmit)
                .accessibilityLabel("Send request")
        }
        .onChange(of: composer.focusRequest) { _, _ in focused = true }
    }
}

/// Review panel for staged content. Labels match AttachmentTrayView.
struct StagedContentPanel: View {
    @Environment(AttachmentStore.self) private var attachments
    @EnvironmentObject private var client: JarvisClient
    var onAsk: (() -> Void)?
    var onApproveOffer: (() -> Void)?
    var onDeclineOffer: (() -> Void)?

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            if !attachments.staged.isEmpty { stagedSection }
            offerCard
            if let error = attachments.error {
                Text(error).font(.caption).foregroundStyle(AppTheme.red)
            }
        }
        .padding(12)
        .mortimerGlass(.card)
    }

    @ViewBuilder private var stagedSection: some View {
        Text("Staged content").font(.headline)
        Text("Analysis provider: \(client.consoleInputProfile?.label ?? "Configured vision")")
            .font(.caption)
            .foregroundStyle(AppTheme.textDim)
        ForEach(attachments.staged, id: \.contentID) { item in
            HStack {
                Text(item.kind.rawValue.capitalized)
                Spacer()
                Button(attachments.approvedIDs.contains(item.contentID) ? "Approved" : "Approve") {
                    attachments.approve(item.contentID)
                }
                Button("Remove") { attachments.remove(item.contentID) }
            }
        }
        TextField("Question for Mortimer", text: Binding(
            get: { attachments.question }, set: { attachments.setQuestion($0) }))
            .textFieldStyle(.roundedBorder)
        HStack {
            Spacer()
            Button("Clear") { attachments.clear() }
            Button("Ask Mortimer") { onAsk?() }
                // Never present an enabled control with no action behind it.
                .disabled(askDisabled)
                .help(onAsk == nil ? "Content analysis transport is not connected" : "Send the approved content to Mortimer")
        }
    }

    private var askDisabled: Bool {
        Self.askDisabled(hasAction: onAsk != nil, approvedCount: attachments.approvedIDs.count,
                         question: attachments.question)
    }

    /// Nothing is asked until something is approved and a question is typed.
    static func askDisabled(hasAction: Bool, approvedCount: Int, question: String) -> Bool {
        !hasAction || approvedCount == 0 ||
            question.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    @ViewBuilder private var offerCard: some View {
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
    }
}
