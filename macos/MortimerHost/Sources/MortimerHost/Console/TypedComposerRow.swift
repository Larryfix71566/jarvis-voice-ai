import SwiftUI
import JarvisKit

/// C7b: the typed-request field above the content tray. Small on purpose;
/// every part is its own property so no expression is large.
struct TypedComposerRow: View {
    @Bindable var composer: TypedComposerModel
    @FocusState private var focused: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 8) { field; sendButton }
            statusLine
        }
        .onChange(of: composer.focusRequest) { _, _ in focused = true }
    }

    private var field: some View {
        TextField("Type a request", text: $composer.draft)
            .textFieldStyle(.roundedBorder)
            .focused($focused)
            .disabled(fieldDisabled)
            .onSubmit { submit() }
            .accessibilityLabel("Type a request")
    }

    private var sendButton: some View {
        Button(composer.isSendingDraft ? "Sending…" : "Send") { submit() }
            .disabled(!composer.canSubmit)
            .accessibilityLabel("Send request")
    }

    @ViewBuilder private var statusLine: some View {
        if let reason = composer.disabledReason {
            Text(reason).font(.caption).foregroundStyle(AppTheme.textDim)
        } else if let notice = composer.notice {
            Text(notice).font(.caption).foregroundStyle(AppTheme.red)
        }
    }

    private var fieldDisabled: Bool {
        composer.disabledReason != nil || composer.isSendingDraft
    }

    private func submit() {
        composer.submitDraft()
    }
}
