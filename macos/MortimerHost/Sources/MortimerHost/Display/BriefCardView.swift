import SwiftUI
import JarvisKit

/// WS-13 P3m (MORTIMER_MAIL_CALENDAR_BRIEF_PLAN.md R.10.16): the mail brief
/// card. Every string here can be mail text (sender, subject), so it is drawn
/// with `Text(verbatim:)` only: no Markdown, no links, no data detectors, and
/// no text selection (copy, share and export are blocked for a protected
/// result, R.10.6). UNTESTED: written on Linux without a Swift toolchain.
struct BriefCardView: View {
    let card: BriefCard

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            ForEach(Array(card.sections.enumerated()), id: \.offset) { _, section in
                sectionView(section)
            }
            if !card.generatedAtLocal.isEmpty {
                Text(verbatim: "As of \(card.generatedAtLocal)")
                    .font(.caption)
                    .foregroundStyle(AppTheme.textDim)
                    .textSelection(.disabled)
            }
        }
        .padding(4)
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Mail")
    }

    private func sectionView(_ section: BriefSection) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(verbatim: "Mail").font(.title3.weight(.semibold)).textSelection(.disabled)
            VStack(alignment: .leading, spacing: 8) {
                ForEach(Array(section.accounts.enumerated()), id: \.offset) { _, account in
                    accountRow(account)
                }
            }
            if section.headlines.isEmpty {
                Text(verbatim: "No headlines to show.")
                    .font(.callout).foregroundStyle(AppTheme.textDim).textSelection(.disabled)
            } else {
                Divider()
                VStack(alignment: .leading, spacing: 10) {
                    ForEach(Array(section.headlines.enumerated()), id: \.offset) { _, headline in
                        headlineRow(headline)
                    }
                    if section.more > 0 {
                        Text(verbatim: "and \(section.more) more")
                            .font(.callout).foregroundStyle(AppTheme.textDim).textSelection(.disabled)
                    }
                }
            }
        }
    }

    private func accountRow(_ account: BriefAccount) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 10) {
            Circle().fill(statusColor(account.status)).frame(width: 8, height: 8)
            Text(verbatim: account.label).font(.callout.weight(.semibold))
            Text(verbatim: BriefCardText.statusLine(account))
                .font(.callout).foregroundStyle(AppTheme.textDim)
            Spacer(minLength: 8)
            Text(verbatim: BriefCardText.countLine(account)).font(.callout).monospacedDigit()
        }
        .textSelection(.disabled)
        .accessibilityElement(children: .combine)
    }

    private func headlineRow(_ headline: BriefHeadline) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Text(verbatim: headline.sender).font(.callout.weight(.semibold)).lineLimit(1)
                Spacer(minLength: 8)
                Text(verbatim: BriefCardText.meta(headline))
                    .font(.caption).foregroundStyle(AppTheme.textDim)
            }
            Text(verbatim: headline.subject).font(.callout).lineLimit(2)
        }
        .textSelection(.disabled)
        .accessibilityElement(children: .combine)
    }

    private func statusColor(_ status: String) -> Color {
        switch status {
        case "ok": return AppTheme.green
        case "partial", "timeout": return AppTheme.amber
        case "not_configured", "disabled": return AppTheme.textDim
        default: return AppTheme.red
        }
    }
}

/// Pure text helpers, kept separate so they can be unit-tested.
enum BriefCardText {
    /// "Signed in", or "Couldn't read: login rejected" for a failed account.
    static func statusLine(_ account: BriefAccount) -> String {
        guard let reason = account.reason, !reason.isEmpty else { return account.statusText }
        return "\(account.statusText): \(reason)"
    }

    /// The host-built count text ("3", "at least 3", "unknown"); never a
    /// blank or zero for a count that is not exact.
    static func countLine(_ account: BriefAccount) -> String {
        account.countText.isEmpty ? "unknown" : account.countText
    }

    /// "Gmail · 09:30"; the time is omitted when the host sent none.
    static func meta(_ headline: BriefHeadline) -> String {
        [headline.accountLabel, headline.receivedLocal].filter { !$0.isEmpty }.joined(separator: " · ")
    }
}
