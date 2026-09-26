import SwiftUI
import JarvisKit

/// MORTIMER_WORKFLOW_VIEWER_PLAN.md (layout C, Larry 2026-09-25). A read-only
/// gallery of Larry's workflows; clicking a card replaces the gallery with
/// that workflow's flow (trigger → steps → done-when). Nothing here edits a
/// workflow: they are reviewed config, changed through self-edit or a PR.
struct WorkflowsView: View {
    let store: WorkflowsStore
    /// nil in tests and previews: the store is filled directly and nothing is fetched.
    let api: AdminAPI?

    var body: some View {
        Group {
            if let workflow = store.selected {
                WorkflowFlowView(store: store, workflow: workflow)
            } else {
                WorkflowsGalleryView(store: store,
                                     reload: api.map { api in { () -> Void in store.load(api: api, force: true) } })
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .task { if let api { store.load(api: api) } }
    }
}

struct WorkflowsGalleryView: View {
    @Bindable var store: WorkflowsStore
    /// Refetch from the sidecar, e.g. after a workflow file changed or a read failed.
    var reload: (() -> Void)? = nil
    static let columns = [GridItem(.adaptive(minimum: 240, maximum: 360), spacing: 12, alignment: .top)]

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 10) {
                Text("Workflows").font(.title3.weight(.semibold))
                Text("READ-ONLY").font(.caption2.monospaced().weight(.semibold))
                    .foregroundStyle(AppTheme.textDim)
                Spacer()
                TextField("Filter by name, trigger or step", text: $store.query)
                    .textFieldStyle(.roundedBorder)
                    .frame(maxWidth: 280)
                if let reload {
                    Button("Reload", action: reload).disabled(store.loading)
                }
            }
            if !store.enabled {
                ContentUnavailableView("Workflows are off", systemImage: "switch.2",
                    description: Text("JARVIS_WORKFLOWS_ENABLED is false, so none are loaded."))
            } else if let error = store.error {
                ContentUnavailableView("Workflows unavailable", systemImage: "exclamationmark.triangle",
                    description: Text(error))
            } else if store.loading && store.workflows.isEmpty {
                ProgressView("Loading workflows…")
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                ScrollView {
                    VStack(alignment: .leading, spacing: 18) {
                        ForEach(WorkflowGroup.allCases) { group in
                            let members = store.section(group)
                            if !members.isEmpty {
                                VStack(alignment: .leading, spacing: 8) {
                                    Text("\(group.title) · \(members.count)")
                                        .font(.caption.monospaced().weight(.semibold))
                                        .foregroundStyle(AppTheme.textDim)
                                    LazyVGrid(columns: Self.columns, alignment: .leading, spacing: 12) {
                                        ForEach(members) { workflow in
                                            Button { store.select(workflow.id) } label: {
                                                WorkflowCard(workflow: workflow)
                                            }
                                            .buttonStyle(.plain)
                                            .accessibilityLabel("Open workflow \(workflow.name)")
                                        }
                                    }
                                }
                            }
                        }
                        if store.loaded && !store.hasVisibleMatches {
                            Text(store.query.isEmpty ? "No workflows are loaded."
                                 : "No workflow matches “\(store.query)”.")
                                .foregroundStyle(AppTheme.textDim)
                        }
                    }
                    .padding(.bottom, 12)
                }
            }
        }
    }
}

/// One gallery card: name, the first step (two lines), a summary line and a
/// pip strip of the flow's shape. A draft has a dashed amber border.
struct WorkflowCard: View {
    let workflow: WorkflowDetail

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(workflow.name).font(.subheadline.weight(.semibold)).lineLimit(1)
            Text(workflow.steps.first ?? workflow.when)
                .font(.caption).foregroundStyle(AppTheme.textDim).lineLimit(2)
            HStack(spacing: 8) {
                Text(summary).font(.caption2.monospaced()).foregroundStyle(AppTheme.textDim).lineLimit(1)
                Spacer(minLength: 0)
                WorkflowPips(workflow: workflow)
            }
        }
        .padding(10)
        .frame(maxWidth: .infinity, minHeight: 92, alignment: .topLeading)
        .background(AppTheme.panel)
        .clipShape(RoundedRectangle(cornerRadius: 8))
        .overlay(RoundedRectangle(cornerRadius: 8).strokeBorder(
            workflow.draft ? AppTheme.amber.opacity(0.7) : AppTheme.hairline,
            style: StrokeStyle(lineWidth: 1, dash: workflow.draft ? [5, 4] : [])))
        .contentShape(Rectangle())
    }

    var summary: String {
        let steps = "\(workflow.steps.count) step\(workflow.steps.count == 1 ? "" : "s")"
        if workflow.isVoice { return "\(steps) · priority \(workflow.priority)" }
        let finish = workflow.doneWhen.isEmpty ? "no finish test" : "\(workflow.doneWhen.count) done-when"
        let who = workflow.agents.isEmpty ? "all specialists" : workflow.agents.joined(separator: ", ")
        return "\(steps) · \(finish) · \(who)"
    }
}

/// trigger · one pip per step · done (green) or no finish test (amber).
struct WorkflowPips: View {
    let workflow: WorkflowDetail

    var body: some View {
        HStack(spacing: 3) {
            Circle().fill(AppTheme.accent).frame(width: 6, height: 6)
            ForEach(workflow.steps.indices, id: \.self) { _ in
                Capsule().fill(AppTheme.text.opacity(0.55)).frame(width: 10, height: 4)
            }
            Circle().fill(workflow.doneWhen.isEmpty ? AppTheme.amber : AppTheme.green)
                .frame(width: 6, height: 6)
        }
        .accessibilityHidden(true)
    }
}

/// One workflow's flow: a horizontal scroll of fixed-width nodes that wrap
/// their text in full (the longest step today is 325 characters).
struct WorkflowFlowView: View {
    let store: WorkflowsStore
    let workflow: WorkflowDetail
    static let nodeWidth: CGFloat = 232

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 10) {
                Button("← All workflows") { store.showGallery() }
                Spacer()
                if let position = store.position {
                    Text("workflow \(position.index) of \(position.count)")
                        .font(.caption.monospaced()).foregroundStyle(AppTheme.textDim)
                }
                if let next = store.next {
                    Button("Next: \(next.name) →") { store.showNext() }
                }
            }
            VStack(alignment: .leading, spacing: 6) {
                Text(workflow.name).font(.title3.weight(.semibold))
                badges
            }
            ScrollView(.horizontal) {
                HStack(alignment: .top, spacing: 0) {
                    node(title: "TRIGGER", tint: AppTheme.accent, dashed: false) { triggerText }
                    ForEach(Array(workflow.steps.enumerated()), id: \.offset) { index, step in
                        connector
                        node(title: "STEP \(index + 1)", tint: AppTheme.text.opacity(0.6), dashed: false) {
                            Text(step)
                        }
                    }
                    connector
                    if workflow.doneWhen.isEmpty {
                        node(title: "DONE WHEN", tint: AppTheme.amber, dashed: true) {
                            Text("No finish test.")
                        }
                    } else {
                        node(title: "DONE WHEN", tint: AppTheme.green, dashed: false) {
                            VStack(alignment: .leading, spacing: 6) {
                                ForEach(Array(workflow.doneWhen.enumerated()), id: \.offset) { _, line in
                                    Text(line)
                                }
                            }
                        }
                    }
                }
                .padding(.vertical, 4)
            }
            Spacer(minLength: 0)
        }
    }

    @ViewBuilder
    private var triggerText: some View {
        if workflow.isVoice {
            VStack(alignment: .leading, spacing: 6) {
                Text(workflow.when)
                Text("Hooks: \(workflow.triggers.isEmpty ? "none" : workflow.triggers.joined(separator: " · "))")
                    .font(.caption.monospaced()).foregroundStyle(AppTheme.textDim)
                Text("Priority \(workflow.priority) · lowest wins")
                    .font(.caption.monospaced()).foregroundStyle(AppTheme.textDim)
            }
        } else {
            VStack(alignment: .leading, spacing: 6) {
                Text(workflow.when)
                Text("≥ \(Int((store.matchThreshold * 100).rounded()))% word overlap · strongest wins · one per run")
                    .font(.caption.monospaced()).foregroundStyle(AppTheme.textDim)
            }
        }
    }

    private var badges: some View {
        HStack(spacing: 6) {
            badge(workflow.isVoice ? "voice" : "standing rule")
            badge(workflow.agents.isEmpty ? "all specialists" : workflow.agents.joined(separator: ", "))
            if workflow.isVoice { badge("priority \(workflow.priority)") }
            if workflow.draft { badge("draft · never matched", tint: AppTheme.amber) }
            badge(workflow.source)
        }
    }

    private func badge(_ text: String, tint: Color = AppTheme.textDim) -> some View {
        Text(text).font(.caption2.monospaced()).foregroundStyle(tint)
            .padding(.horizontal, 6).padding(.vertical, 2)
            .overlay(Capsule().strokeBorder(tint.opacity(0.5)))
    }

    private var connector: some View {
        Image(systemName: "arrow.right")
            .font(.caption).foregroundStyle(AppTheme.textDim)
            .frame(width: 28).padding(.top, 18)
            .accessibilityHidden(true)
    }

    private func node<Content: View>(title: String, tint: Color, dashed: Bool,
                                     @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title).font(.caption2.monospaced().weight(.semibold)).foregroundStyle(tint)
            content().font(.callout).fixedSize(horizontal: false, vertical: true)
        }
        .padding(10)
        .frame(width: Self.nodeWidth, alignment: .topLeading)
        .background(AppTheme.panel)
        .clipShape(RoundedRectangle(cornerRadius: 8))
        .overlay(RoundedRectangle(cornerRadius: 8).strokeBorder(
            tint.opacity(0.7), style: StrokeStyle(lineWidth: 1, dash: dashed ? [5, 4] : [])))
    }
}
