import SwiftUI

struct AtlasCardButton: View {
    let card: AtlasCard
    let selected: Bool
    let onOpen: () -> Void

    var body: some View {
        Button {
            guard card.kind == .result else { return }
            onOpen()
        } label: {
            AtlasCardView(card: card, selected: selected)
        }
        .buttonStyle(.plain)
        .disabled(card.kind != .result)
        .accessibilityLabel(card.accessibilityLabel)
        .accessibilityValue(card.accessibilityValue)
        .accessibilityHint(card.kind == .result
            ? "Opens this result in the response area"
            : "Informational Knowledge Atlas card")
    }
}

struct AtlasCardView: View {
    let card: AtlasCard
    let selected: Bool
    var body: some View {
        VStack(alignment: .leading, spacing: 7) {
            HStack(spacing: 8) {
                Text(card.kind.label.uppercased())
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(card.kind == .result ? AppTheme.accent : AppTheme.textDim)
                Spacer(minLength: 0)
            }
            Text(card.title).font(.headline).lineLimit(2)
            Text(card.summary).font(.subheadline).foregroundStyle(AppTheme.textDim).lineLimit(4)
            if let source = card.source { Text(source).font(.caption).foregroundStyle(AppTheme.accent) }
        }
        .frame(maxWidth: .infinity, minHeight: 120, alignment: .topLeading)
        .padding(14)
        .mortimerGlass(.card)
        .overlay(RoundedRectangle(cornerRadius: 12).stroke(selected ? AppTheme.accent : Color.clear, lineWidth: selected ? 2 : 0))
    }
}
