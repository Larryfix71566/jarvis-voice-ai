import Foundation
import SwiftUI
import Observation
import JarvisKit

/// MORTIMER_OPTIMIZATION_PLAN.md "Interface Task — Council Roster on the
/// Agent Card". The council's own lineup, rendered under the live agent
/// cards in the Agents tab: proposers with the means that chose the
/// winner, judges listed separately, and abstentions VISIBLE WITH THEIR
/// REASONS — `kimi-k3 ✗ judge call failed` four times on last night's
/// card would have surfaced the timeout bug at a glance. Silent pool
/// degradation is the same failure class the launcher work fixed for
/// services.
///
/// Every number here is assembled by the sidecar
/// (jarvis/council/council.py `build_roster`) and merely rendered here:
/// a mean recomputed in Swift could disagree with the winner chip above
/// it, and would sit outside the Python suite that pins the rule.
///
/// Deliberately NOT hung off an individual AgentRun: `council_rounds`
/// has a `run_id` column but it is NULL on every round ever recorded —
/// nothing passes one, and UpgradeAgent (the only caller that convenes)
/// never enters a run-logger scope to have one. Rounds are therefore
/// listed newest-first as their own section rather than pretending to an
/// attachment that does not exist. See the plan's Interface Task notes.
@MainActor
@Observable
final class CouncilViewModel {
    let api: AdminAPI
    var state: TabState<[CouncilRoster]> = .loading
    private var pollTask: Task<Void, Never>?
    private var stopped = false

    init(api: AdminAPI) { self.api = api }

    func startPolling() {
        guard pollTask == nil, !stopped else { return }
        pollTask = Task { [weak self] in
            while !Task.isCancelled {
                await self?.refresh()
                if self?.stopped == true { return }
                try? await Task.sleep(
                    nanoseconds: UInt64(AppTuning.councilPollSeconds * 1_000_000_000)
                )
            }
        }
    }

    func stopPolling() {
        pollTask?.cancel()
        pollTask = nil
    }

    func refresh() async {
        do {
            let list = try await api.councilRosterTyped()
            state = TabStateMapper.map(
                ok: list.ok, error: nil, isEmpty: list.rounds.isEmpty, value: list.rounds
            )
        } catch {
            let (message, unauthorized) = TabStateMapper.fromError(error)
            state = .error(message)
            if unauthorized { stopped = true; stopPolling() }
        }
    }
}

/// The section AgentsTab renders below its live runs.
struct CouncilRosterSection: View {
    @Bindable var model: CouncilViewModel

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("COUNCIL ROUNDS")
                .font(.system(size: 10, design: .monospaced))
                .kerning(2.0)
                .foregroundStyle(AppTheme.textDim)
            switch model.state {
            case .loading:
                Text("loading…").font(.caption).foregroundStyle(AppTheme.textDim)
            case .empty:
                Text("No council rounds recorded.")
                    .font(.caption).foregroundStyle(AppTheme.textDim)
            case .error(let message):
                Text(message).font(.caption).foregroundStyle(AppTheme.red)
            case .loaded(let rounds):
                ForEach(rounds) { round in
                    CouncilRoundCard(round: round)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .task { model.startPolling() }
        .onDisappear { model.stopPolling() }
    }
}

/// One round. Split out of the section so the SwiftUI type-checker sees
/// several small bodies rather than one very large one.
struct CouncilRoundCard: View {
    let round: CouncilRoster

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            header
            if round.degraded { degradation }
            if !round.proposers.isEmpty { proposerRows }
            if !round.judges.isEmpty { judgeRows(round.judges, shadow: false) }
            if !round.shadowJudges.isEmpty { judgeRows(round.shadowJudges, shadow: true) }
            footer
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .mortimerGlass(.card)
    }

    // The PRIMARY chip is the winner's resolved profile — the chip names
    // what actually proceeded (the plan's model-discipline rule).
    private var header: some View {
        HStack(spacing: 8) {
            Text(round.winnerProfile ?? "no winner")
                .font(.caption2)
                .padding(.horizontal, 6).padding(.vertical, 2)
                .foregroundStyle(round.winnerProfile == nil ? AppTheme.red : AppTheme.accent)
                .mortimerGlass(.chip)
                .help(round.selectReason ?? "the round selected nobody")
            Text(subtitle)
                .font(.caption2).foregroundStyle(AppTheme.textDim)
            Spacer()
            if round.degraded {
                Image(systemName: "exclamationmark.triangle.fill")
                    .font(.system(size: 9))
                    .foregroundStyle(AppTheme.amber)
            }
            Text(shortTime(round.startedAt))
                .font(.system(size: 9, design: .monospaced))
                .foregroundStyle(AppTheme.textDim)
        }
    }

    private var subtitle: String {
        var parts: [String] = [round.placement]
        if !round.trigger.isEmpty { parts.append(round.trigger) }
        if let tier = round.tier { parts.append("tier \(tier)") }
        if round.status != "ok", !round.status.isEmpty { parts.append(round.status) }
        return parts.joined(separator: " · ")
    }

    private var degradation: some View {
        VStack(alignment: .leading, spacing: 2) {
            ForEach(Array(round.degradedReasons.enumerated()), id: \.offset) { _, reason in
                Text(reason)
                    .font(.caption2)
                    .foregroundStyle(AppTheme.amber)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    private var proposerRows: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text("proposers").font(.system(size: 9, design: .monospaced))
                .foregroundStyle(AppTheme.textDim)
            ForEach(Array(round.proposers.enumerated()), id: \.offset) { _, proposer in
                HStack(spacing: 6) {
                    Image(systemName: proposer.isWinner ? "checkmark.circle.fill" : "circle")
                        .font(.system(size: 7))
                        .foregroundStyle(proposer.isWinner ? AppTheme.accent : AppTheme.textDim)
                    Text(proposer.profile)
                        .font(.system(.caption2, design: .monospaced))
                        .foregroundStyle(proposer.isWinner ? AppTheme.text : AppTheme.textDim)
                    Spacer()
                    if proposer.abstainedBy > 0 {
                        Text("\(proposer.abstainedBy) abstained")
                            .font(.system(size: 9)).foregroundStyle(AppTheme.amber)
                    }
                    Text(meanText(proposer.mean))
                        .font(.system(.caption2, design: .monospaced)).monospacedDigit()
                        .foregroundStyle(proposer.isWinner ? AppTheme.accent : AppTheme.textDim)
                }
                .help(proposer.label)
            }
        }
    }

    private func judgeRows(_ judges: [CouncilJudge], shadow: Bool) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(shadow ? "shadow judges" : "judges")
                .font(.system(size: 9, design: .monospaced))
                .foregroundStyle(AppTheme.textDim)
            ForEach(Array(judges.enumerated()), id: \.offset) { _, judge in
                judgeRow(judge)
            }
        }
    }

    private func judgeRow(_ judge: CouncilJudge) -> some View {
        VStack(alignment: .leading, spacing: 1) {
            HStack(spacing: 6) {
                Image(systemName: judge.allAbstained ? "xmark" : "circle.fill")
                    .font(.system(size: judge.allAbstained ? 8 : 5))
                    .foregroundStyle(judge.allAbstained ? AppTheme.red
                                     : (judge.abstained > 0 ? AppTheme.amber : AppTheme.green))
                Text(judge.profile)
                    .font(.system(.caption2, design: .monospaced))
                    .foregroundStyle(judge.allAbstained ? AppTheme.text : AppTheme.textDim)
                if let tier = judge.tier, !tier.isEmpty {
                    Text(tier).font(.system(size: 9)).foregroundStyle(AppTheme.textDim)
                }
                if judge.alsoProposed {
                    Text("also proposed — not counted")
                        .font(.system(size: 9)).foregroundStyle(AppTheme.amber)
                }
                Spacer()
                Text("\(judge.scored) scored · \(judge.abstained) abstained")
                    .font(.system(size: 9, design: .monospaced))
                    .foregroundStyle(AppTheme.textDim)
            }
            // The reason IS the feature — a count alone is what let a
            // dead judge sit unnoticed for two weeks.
            ForEach(Array(judge.abstainReasons.enumerated()), id: \.offset) { _, reason in
                Text(reason)
                    .font(.system(size: 9))
                    .foregroundStyle(AppTheme.red.opacity(0.9))
                    .lineLimit(2)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.leading, 14)
                    .help(reason)
            }
        }
    }

    private var footer: some View {
        HStack(spacing: 8) {
            Text("\(round.tokens.total) tokens")
                .font(.system(size: 9, design: .monospaced))
                .foregroundStyle(AppTheme.textDim)
                .help("\(round.tokens.prompt) prompt + \(round.tokens.completion) completion")
            if let latency = round.latencyMs, latency > 0 {
                Text(String(format: "%.1fs", Double(latency) / 1000.0))
                    .font(.system(size: 9, design: .monospaced))
                    .foregroundStyle(AppTheme.textDim)
            }
            if let outcome = round.retryOutcome, !outcome.isEmpty {
                Text(outcome)
                    .font(.system(size: 9, design: .monospaced))
                    .foregroundStyle(outcome.hasPrefix("validated_ok") ? AppTheme.green : AppTheme.amber)
                    .help("what the retry this round produced actually did (migration 0018)")
            }
            Spacer()
        }
    }

    private func meanText(_ mean: Double?) -> String {
        guard let mean else { return "—" }
        return String(format: "%.2f", mean)
    }

    /// "2026-09-01T02:17:21.374092+00:00" -> "09-01 02:17". Never parsed
    /// into a Date: the sidecar's string is already the recorded instant,
    /// and a failed parse would silently render "now".
    private func shortTime(_ iso: String) -> String {
        guard iso.count >= 16 else { return iso }
        let date = iso.prefix(10).suffix(5)      // MM-DD
        let start = iso.index(iso.startIndex, offsetBy: 11)
        let end = iso.index(iso.startIndex, offsetBy: 16)
        return "\(date) \(iso[start..<end])"
    }
}
