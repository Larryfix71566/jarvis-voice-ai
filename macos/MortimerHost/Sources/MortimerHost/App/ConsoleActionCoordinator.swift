import Foundation
import AppKit
import JarvisKit

/// Single native mutation path for Command Console controls. Views and future
/// voice dispatch submit the same request; unsupported actions are explicit.
@MainActor
final class ConsoleActionCoordinator {
    enum Outcome: Equatable { case applied, noop, pendingUser, unsupported, capacity, invalid, stale }
    private let workspace: WorkspaceStore
    private let display: DisplayWindowStore
    private let placement: WindowPlacement
    private let atlas: AtlasStore?
    private let panels: PanelStore?
    private let drawer: DrawerState?
    private let sharing: ShareCoordinator?
    private let attachments: AttachmentStore?
    private let notices: ConsoleNoticeState?
    private weak var client: JarvisClient?
    private let registry = ConsoleActionRegistry()

    init(workspace: WorkspaceStore, display: DisplayWindowStore, placement: WindowPlacement,
         atlas: AtlasStore? = nil, panels: PanelStore? = nil, drawer: DrawerState? = nil,
         sharing: ShareCoordinator? = nil, attachments: AttachmentStore? = nil,
         client: JarvisClient? = nil, notices: ConsoleNoticeState? = nil) {
        self.workspace = workspace; self.display = display; self.placement = placement
        self.atlas = atlas; self.panels = panels; self.drawer = drawer; self.sharing = sharing
        self.client = client
        self.attachments = attachments
        self.notices = notices
    }

    func inventory() -> [String: Any] { workspace.consoleInventory }

    /// Route a native pointer/keyboard action through the same validated
    /// dispatcher used by voice requests. The negotiated identity is used
    /// when available; previews without a live client still execute locally,
    /// which preserves the existing view-test behavior.
    @discardableResult
    func executePointer(_ action: ConsoleAction, target: String? = nil,
                        secondaryTarget: String? = nil,
                        args: [String: JSONValue] = [:]) -> Outcome {
        let sessionID = client?.consoleSessionID ?? UUID()
        let generation = client?.consoleGeneration ?? UUID()
        let outcome = execute(ConsoleRequest(sessionID: sessionID, generation: generation,
                                             requestID: UUID(), revision: workspace.consoleRevision,
                                             action: action, target: target,
                                             secondaryTarget: secondaryTarget, args: args))
        // Pointer actions have no message-stream response to trigger the
        // inventory publication hook. Publish after the mutation so a later
        // voice command resolves against the state the user actually sees.
        publishInventory()
        return outcome
    }

    /// Publish the latest native-owned target inventory after a pointer or
    /// voice mutation. The backend uses the revision to reject stale targets.
    func publishInventory() {
        guard let client, let sessionID = client.consoleSessionID,
              let generation = client.consoleGeneration else { return }
        var data = workspace.consoleInventoryJSON
        if case .object(var object) = data {
            object["attachments"] = .array(attachments?.consoleInventoryEntries ?? [])
            // Dynamic content panels are the authoritative detachable
            // identities. Keep the legacy enum panels only as a fallback so
            // older clients still see their four fixed surfaces, while the
            // wire ceiling remains six entries.
            if let panels, !panels.contentInventoryEntries.isEmpty {
                let legacy = object["panels"].flatMap { value -> [JSONValue]? in
                    if case .array(let values) = value { return values }
                    return nil
                } ?? []
                object["panels"] = .array(Array((panels.contentInventoryEntries + legacy).prefix(6)))
            }
            data = .object(object)
        }
        client.send(.consoleInventory(ConsoleInventory(
            sessionID: sessionID, generation: generation,
            revision: workspace.consoleRevision,
            data: data)))
    }

    func execute(_ request: ConsoleRequest) -> Outcome {
        guard request.revision == workspace.consoleRevision else { return .stale }
        guard registry.validate(request, currentRevision: workspace.consoleRevision) else { return .invalid }
        switch request.action {
        case .help, .inventory:
            return .applied
        case .viewSet:
            switch stringArg(request, "mode") ?? request.target {
            case "conversation": workspace.returnToConversation(); return .applied
            case "memory": workspace.openMemoryGraph(); return .applied
            case "results": workspace.returnToWorkspace(); return .applied
            case "atlas": workspace.openAtlas(); return .applied
            default: return .invalid
            }
        case .resultSelect:
            guard let id = request.target.flatMap(UUID.init(uuidString:)),
                  workspace.results.contains(where: { $0.id == id }) else { return .invalid }
            workspace.select(id); return .applied
        case .resultPin:
            guard let id = request.target.flatMap(UUID.init(uuidString:)),
                  workspace.results.contains(where: { $0.id == id }) else { return .invalid }
            return workspace.pin(id) ? .applied : .noop
        case .resultUnpin:
            guard let id = request.target.flatMap(UUID.init(uuidString:)),
                  workspace.results.contains(where: { $0.id == id }) else { return .invalid }
            workspace.unpin(id); return .applied
        case .resultClose:
            guard let id = request.target.flatMap(UUID.init(uuidString:)),
                  workspace.results.contains(where: { $0.id == id }) else { return .invalid }
            workspace.close(id); return .applied
        case .resultNext:
            return workspace.selectAdjacentResult(step: 1) ? .applied : .noop
        case .resultPrevious:
            return workspace.selectAdjacentResult(step: -1) ? .applied : .noop
        case .compareSet:
            guard let id = request.target.flatMap(UUID.init(uuidString:)),
                  let other = request.secondaryTarget.flatMap(UUID.init(uuidString:)),
                  id != other,
                  workspace.results.contains(where: { $0.id == id }),
                  workspace.results.contains(where: { $0.id == other }) else { return .invalid }
            workspace.select(id)
            return workspace.compare(with: other) ? .applied : .invalid
        case .compareEnd:
            workspace.compare(with: nil); return .applied
        case .compareSide:
            guard let side = stringArg(request, "side") ?? request.target,
                  let value = WorkspaceComparisonSide(rawValue: side.uppercased()) else { return .invalid }
            return workspace.setComparisonSide(value) ? .applied : .noop
        case .contentScroll:
            let id = request.target.flatMap(UUID.init(uuidString:)) ?? workspace.activeID
            guard let id, let direction = stringArg(request, "direction") ?? request.secondaryTarget else { return .invalid }
            let viewport = doubleArg(request, "viewport") ?? 800
            return workspace.scrollResult(id, direction: direction, viewport: viewport) ? .applied : .invalid
        case .sourceSelect, .sourceOpen, .sourceInspector, .imageSelect:
            guard let id = request.target.flatMap(UUID.init(uuidString:)) ?? workspace.activeID,
                  let result = workspace.results.first(where: { $0.id == id }) else { return .invalid }
            switch request.action {
            case .sourceInspector:
                guard let open = boolArg(request, "open") else { return .invalid }
                return workspace.setSourceInspector(open, for: id) ? .applied : .invalid
            case .imageSelect:
                guard let index = intArg(request, "index") ?? request.secondaryTarget.flatMap(Int.init) else { return .invalid }
                return workspace.selectImage(index, for: id) ? .applied : .invalid
            default:
                guard let index = sourceIndex(request, result: result) else { return .invalid }
                if request.action == .sourceSelect {
                    return workspace.selectSource(index, for: id) ? .applied : .invalid
                }
                guard let url = workspace.markSourceOpened(index, for: id) else { return .invalid }
                return NSWorkspace.shared.open(url) ? .applied : .noop
            }
        case .atlasFit:
            workspace.openAtlas(); atlas?.fit(); return .applied
        case .atlasZoom:
            guard let atlas, let direction = stringArg(request, "direction") ?? request.target,
                  ["in", "out", "reset"].contains(direction) else { return .invalid }
            return atlas.zoom(direction) ? .applied : .invalid
        case .atlasPan:
            guard let atlas, let direction = stringArg(request, "direction") ?? request.target,
                  ["up", "down", "left", "right"].contains(direction) else { return .invalid }
            return atlas.pan(direction) ? .applied : .invalid
        case .atlasArrange:
            guard let atlas else { return .unsupported }
            atlas.arrange(); return .applied
        case .groupCreate:
            guard let atlas, let name = stringArg(request, "name") ?? request.target else { return .invalid }
            return atlas.createGroup(name) ? .applied : .noop
        case .groupRename:
            guard let atlas, let old = request.target,
                  let name = stringArg(request, "name") else { return .invalid }
            return atlas.renameGroup(old, to: name) ? .applied : .noop
        case .groupAssign:
            guard let atlas, let id = request.target.flatMap(UUID.init(uuidString:)),
                  let group = stringArg(request, "group") ?? request.secondaryTarget,
                  atlas.groups[group] != nil,
                  atlas.cards.contains(where: { $0.id == id }) else { return .invalid }
            atlas.assign(id, to: group); return .applied
        case .groupRemoveCard:
            guard let atlas, let id = request.target.flatMap(UUID.init(uuidString:)),
                  let group = stringArg(request, "group") ?? request.secondaryTarget else { return .invalid }
            return atlas.remove(id, from: group) ? .applied : .noop
        case .groupDissolve:
            guard let atlas, let group = request.target else { return .invalid }
            return atlas.dissolveGroup(group) ? .applied : .noop
        case .atlasMove:
            guard let atlas, let id = request.target.flatMap(UUID.init(uuidString:)),
                  atlas.cards.contains(where: { $0.id == id }) else { return .invalid }
            let relation = stringArg(request, "relation")
            let row = intArg(request, "row"), column = intArg(request, "column")
            guard (relation != nil) != (row != nil || column != nil) else { return .invalid }
            if let relation {
                guard let other = request.secondaryTarget.flatMap(UUID.init(uuidString:)),
                      atlas.cards.contains(where: { $0.id == other }) else { return .invalid }
                return atlas.move(id, relativeTo: other, relation: relation) ? .applied : .invalid
            }
            guard let row, let column else { return .invalid }
            return atlas.move(id, row: row, column: column) ? .applied : .invalid
        case .graphSearch:
            guard let query = stringArg(request, "query") ?? request.target else { return .invalid }
            workspace.memoryGraph.setSearch(query); return .applied
        case .graphSelect:
            guard let id = request.target,
                  workspace.memoryGraph.graph?.nodes.contains(where: { $0.id == id }) == true else { return .invalid }
            workspace.memoryGraph.select(id); return .applied
        case .graphSelectEdge:
            guard let index = request.target.flatMap(Int.init),
                  let edge = workspace.memoryGraph.graph?.edges.indices.contains(index) == true
                    ? workspace.memoryGraph.graph?.edges[index] : nil else { return .invalid }
            workspace.memoryGraph.select(edge: edge); return .applied
        case .graphBack:
            guard workspace.memoryGraph.canGoBack else { return .noop }
            workspace.memoryGraph.back(); return .applied
        case .graphReset:
            workspace.memoryGraph.resetLayout(); return .applied
        case .graphRetry:
            return workspace.memoryGraph.retry() ? .applied : .noop
        case .graphFit:
            workspace.memoryGraph.fit(size: display.viewportSize); return .applied
        case .graphFocus:
            guard let id = request.target,
                  workspace.memoryGraph.graph?.nodes.contains(where: { $0.id == id }) == true else { return .invalid }
            let depth = intArg(request, "depth")
            return workspace.memoryGraph.focus(id, depth: depth) ? .applied : .invalid
        case .graphZoom:
            guard let direction = request.target else { return .invalid }
            return workspace.memoryGraph.zoom(direction) ? .applied : .invalid
        case .graphPan:
            guard let direction = request.target else { return .invalid }
            return workspace.memoryGraph.pan(direction) ? .applied : .invalid
        case .graphFilter:
            guard let kind = stringArg(request, "kind"), let type = request.target,
                  let visible = boolArg(request, "visible") else { return .invalid }
            if kind == "node" { return workspace.memoryGraph.setNodeType(type, visible: visible) ? .applied : .invalid }
            if kind == "edge" { return workspace.memoryGraph.setEdgeType(type, visible: visible) ? .applied : .invalid }
            return .invalid
        case .graphGroup:
            guard let type = request.target, let collapsed = boolArg(request, "collapsed") else { return .invalid }
            return workspace.memoryGraph.setGroup(type, collapsed: collapsed) ? .applied : .invalid
        case .graphPath:
            guard let start = request.target, let end = request.secondaryTarget else { return .invalid }
            return workspace.memoryGraph.setPath(start: start, end: end) ? .applied : .invalid
        case .graphPathClear:
            workspace.memoryGraph.clearPath(); return .applied
        case .graphInspector:
            guard let open = boolArg(request, "open") else { return .invalid }
            workspace.memoryGraph.setInspector(open); return .applied
        case .graphCenter:
            guard let id = request.target,
                  workspace.memoryGraph.graph?.nodes.contains(where: { $0.id == id }) == true else { return .invalid }
            workspace.memoryGraph.select(id); workspace.memoryGraph.centerSelection(); return .applied
        case .graphMoveNode:
            guard let id = request.target, let x = doubleArg(request, "x"), let y = doubleArg(request, "y") else { return .invalid }
            return workspace.memoryGraph.moveNode(id, to: CGPoint(x: x, y: y)) ? .applied : .invalid
        case .graphOriginal:
            guard let enabled = boolArg(request, "enabled") else { return .invalid }
            workspace.memoryGraph.usesImageFallback = enabled; return .applied
        case .resultMode:
            guard let id = request.target.flatMap(UUID.init(uuidString:)),
                  let mode = stringArg(request, "mode"),
                  let selected = WorkspaceResultMode(rawValue: mode.capitalized),
                  let result = workspace.results.first(where: { $0.id == id }) else { return .invalid }
            workspace.presentation(for: result).mode = selected
            return .applied
        case .sharePreview:
            guard let sharing,
                  let target = request.target else { return .invalid }
            let format = stringArg(request, "format") ?? "text"
            guard ["text", "png"].contains(format) else { return .invalid }
            if target == "memory" || target == "graph" {
                guard format == "png", let id = workspace.activeID,
                      let data = workspace.memoryGraph.imageFallback.image?.pngData() else { return .unsupported }
                return sharing.beginImagePreview(resultID: id, pngData: data) ? .applied : .noop
            }
            if target == "comparison" {
                guard format == "text", let first = workspace.activeResult,
                      let second = workspace.comparisonResult else { return .invalid }
                let text = WorkspaceResultExport.text(first) + "\n--- Comparison ---\n\n" + WorkspaceResultExport.text(second)
                sharing.beginPreview(first, text: text)
                return .applied
            }
            guard let id = UUID(uuidString: target),
                  let result = workspace.results.first(where: { $0.id == id }) else { return .invalid }
            if format == "text" {
                let scope = stringArg(request, "scope") ?? "whole"
                let ordinal = intArg(request, "ordinal")
                guard let text = WorkspaceResultExport.scopedText(result, scope: scope, ordinal: ordinal) else { return .invalid }
                sharing.beginPreview(result, text: text)
                return .applied
            }
            guard let data = workspace.memoryGraph.imageFallback.image?.pngData() else {
                return .unsupported
            }
            return sharing.beginImagePreview(resultID: id, pngData: data) ? .applied : .noop
        case .shareCopy:
            guard let sharing, sharing.preview != nil else { return .invalid }
            return sharing.copy() ? .applied : .noop
        case .shareCancel:
            guard let sharing, sharing.preview != nil else { return .noop }
            sharing.cancel()
            return .applied
        case .shareSave:
            guard let sharing, sharing.preview != nil else { return .invalid }
            if let folder = workspace.exporter.exportFolderURL,
               let preview = sharing.preview {
                let suffix = preview.format == "png" ? "png" : "txt"
                let url = folder.appendingPathComponent("Mortimer-\(preview.id.uuidString).\(suffix)")
                Task { await sharing.save(to: url) }
            } else {
                sharing.chooseSave()
            }
            return .pendingUser
        case .sharePicker:
            guard let sharing, sharing.preview != nil else { return .invalid }
            return sharing.presentPicker() ? .pendingUser : .noop
        case .shareSource:
            guard let id = request.target.flatMap(UUID.init(uuidString:)) ?? workspace.activeID,
                  let result = workspace.results.first(where: { $0.id == id }),
                  let index = sourceIndex(request, result: result),
                  let url = workspace.markSourceOpened(index, for: id) else { return .invalid }
            return NSWorkspace.shared.open(url) ? .applied : .noop
        case .panelDetach, .panelReturn, .panelFocus, .panelClose, .panelFullscreen:
            guard let panels, let target = request.target else { return .invalid }
            // Dynamic content panels are addressed by UUID after they appear
            // in the native inventory. Their exact content identity remains
            // in PanelStore, so a delayed title or screen label cannot retarget
            // the request.
            if let uuid = UUID(uuidString: target), let contentID = panels.contentRecords.keys.first(where: { $0.rawValue == uuid }) {
                switch request.action {
                case .panelDetach, .panelFocus:
                    panels.focusContent(contentID)
                    placement.openContentPanel(contentID,
                                               screenID: panels.contentRecord(contentID)?.screenID)
                case .panelReturn, .panelClose:
                    panels.returnContent(contentID)
                    placement.dismissContentPanel(contentID)
                case .panelFullscreen:
                    guard let enabled = boolArg(request, "enabled") else { return .invalid }
                    panels.setContentFullscreen(contentID, enabled: enabled)
                    placement.openContentPanel(contentID,
                                               screenID: panels.contentRecord(contentID)?.screenID)
                default: break
                }
                workspace.noteConsoleMutation()
                return .applied
            }
            // A new panel may be requested with a closed content target. The
            // bounded store either opens/focuses it or returns the explicit
            // capacity outcome without evicting an existing panel.
            if request.action == .panelDetach, let content = PanelContent.parseTarget(target) {
                switch panels.openContent(content, origin: target,
                                           screenID: stringArg(request, "screen_id") ?? request.secondaryTarget) {
                case .opened(let id), .focused(let id):
                    placement.openContentPanel(id, screenID: panels.contentRecord(id)?.screenID)
                    workspace.noteConsoleMutation()
                    return .applied
                case .rejectedLimit:
                    return .capacity
                }
            }
            guard let panel = ConsolePanel(rawValue: target) else { return .invalid }
            switch request.action {
            case .panelDetach:
                panels.detach(panel)
                placement.openPanel(panel)
            case .panelReturn, .panelClose:
                panels.returnPanel(panel)
                placement.dismissPanel(panel)
            case .panelFocus:
                panels.focus(panel)
                placement.openPanel(panel, screenID: panels.screenByPanel[panel])
            case .panelFullscreen:
                guard let enabled = boolArg(request, "enabled") else { return .invalid }
                panels.setFullscreen(panel, enabled: enabled)
                if enabled {
                    panels.focus(panel)
                    placement.openPanel(panel, screenID: panels.screenByPanel[panel])
                }
                default: break
            }
            workspace.noteConsoleMutation()
            return .applied
        case .panelMove:
            guard let panels, let target = request.target,
                  let screen = stringArg(request, "screen_id") ?? request.secondaryTarget else { return .invalid }
            if let uuid = UUID(uuidString: target), let contentID = panels.contentRecords.keys.first(where: { $0.rawValue == uuid }) {
                guard panels.moveContent(contentID, to: screen) else { return .invalid }
                placement.openContentPanel(contentID, screenID: screen)
                workspace.noteConsoleMutation()
                return .applied
            }
            guard let panel = ConsolePanel(rawValue: target) else { return .invalid }
            guard panels.move(panel, to: screen) else { return .invalid }
            placement.openPanel(panel, screenID: screen)
            workspace.noteConsoleMutation()
            return .applied
        case .sidecarWidth:
            guard let drawer, let width = doubleArg(request, "points") ?? request.target.flatMap(Double.init) else { return .invalid }
            drawer.width = DrawerState.clampWidth(width, windowWidth: 1280)
            return .applied
        case .sidecarText:
            guard let size = intArg(request, "size") ?? request.target.flatMap(Int.init),
                  [11, 16, 22].contains(size) else { return .invalid }
            UserDefaults.standard.set(Double(size), forKey: "mortimer.interface.sidecarTabTextSize")
            return .applied
        case .sidecarScrollTabs:
            guard let drawer, let direction = stringArg(request, "direction") ?? request.target else { return .invalid }
            return drawer.scrollTabs(direction) ? .applied : .invalid
        case .appearanceSet:
            guard let layout = intArg(request, "layout") ?? request.target.flatMap(Int.init),
                  (0...2).contains(layout) else { return .invalid }
            UserDefaults.standard.set(layout, forKey: "mortimer.interface.layoutVersion")
            return .applied
        case .consoleCaption:
            guard let expanded = boolArg(request, "expanded") else { return .invalid }
            guard let notices else { return .unsupported }
            notices.captionExpanded = expanded
            return .applied
        case .consoleStatus:
            guard let open = boolArg(request, "open") else { return .invalid }
            guard let notices else { return .unsupported }
            notices.statusOpen = open
            return .applied
        case .waveTuningOpen:
            placement.openWaveTuning()
            return .pendingUser
        case .waveTuningSet:
            guard let key = stringArg(request, "key"), let value = doubleArg(request, "value") else { return .invalid }
            return setWaveTuning(key: key, value: value) ? .applied : .invalid
        case .resetLayout:
            ScreenPlacement.shared.resetLayout(); return .applied
        case .panelsReturnAll:
            panels?.returnAll(); panels?.returnAllContent()
            placement.dismissAllPanels(); placement.dismissAllContentPanels(); placement.closeDisplay()
            workspace.showOriginalDisplayPanels(); workspace.noteConsoleMutation(); return .applied
        case .inputPaste:
            guard let attachments else { return .unsupported }
            let format = stringArg(request, "format") ?? request.target ?? "auto"
            guard ["text", "image", "auto"].contains(format) else { return .invalid }
            return stageClipboard(format: format, into: attachments) ? .applied : .noop
        case .inputChoose:
            guard let attachments else { return .unsupported }
            let format = stringArg(request, "format") ?? request.target ?? "auto"
            guard ["text", "image"].contains(format) else { return .invalid }
            chooseInputFiles(format: format, into: attachments)
            return .pendingUser
        case .inputRemove:
            guard let attachments, let id = request.target.flatMap(UUID.init(uuidString:)) else { return .invalid }
            attachments.remove(id); return .applied
        case .inputClear:
            guard let attachments else { return .unsupported }
            attachments.clear(); return .applied
        case .inputPreview:
            guard let attachments else { return .unsupported }
            attachments.previewVisible = true; return .applied
        case .inputQuestion:
            guard let attachments, let question = stringArg(request, "question") ?? request.target else { return .invalid }
            attachments.setQuestion(question); return .applied
        case .inputCancel:
            guard let attachments else { return .unsupported }
            attachments.requestCancel(); return .applied
        case .inputNewConversation:
            guard let attachments, let confirmed = boolArg(request, "confirmed") else { return .invalid }
            guard confirmed else {
                attachments.stageError("Confirm starting a new conversation to clear staged content.")
                return .pendingUser
            }
            attachments.clear(); workspace.returnToConversation()
            if let client { Task { await client.reconnect() } }
            return .pendingUser
        case .exportFolderChoose:
            workspace.exporter.chooseFolder(); return .pendingUser
        case .exportFolderClear:
            workspace.exporter.clearFolder(); return .applied
        case .sharedContent:
            return .unsupported
        }
    }

    private func stringArg(_ request: ConsoleRequest, _ key: String) -> String? {
        request.args[key]?.stringValue
    }

    private func boolArg(_ request: ConsoleRequest, _ key: String) -> Bool? {
        request.args[key]?.boolValue
    }

    private func doubleArg(_ request: ConsoleRequest, _ key: String) -> Double? {
        request.args[key]?.doubleValue
    }

    private func intArg(_ request: ConsoleRequest, _ key: String) -> Int? {
        request.args[key]?.intValue
    }

    private func sourceIndex(_ request: ConsoleRequest, result: WorkspaceResult) -> Int? {
        if let index = intArg(request, "index") ?? request.secondaryTarget.flatMap(Int.init) { return index }
        let target = stringArg(request, "source") ?? request.target
        if let target, let index = result.payload.links?.firstIndex(where: { $0.url == target || $0.label == target }) { return index }
        return nil
    }

    private func stageClipboard(format: String, into attachments: AttachmentStore) -> Bool {
        let board = NSPasteboard.general
        if format != "text", let image = board.data(forType: .png), let item = AttachmentNormalizer.image(image, mimeType: "image/png") {
            attachments.stage(item); return true
        }
        if format != "image", let text = board.string(forType: .string), let item = AttachmentNormalizer.text(text) {
            attachments.stage(item); return true
        }
        attachments.stageError("Clipboard has no supported (format) content.")
        return false
    }

    private func chooseInputFiles(format: String, into attachments: AttachmentStore) {
        let panel = NSOpenPanel()
        panel.allowsMultipleSelection = true
        panel.canChooseDirectories = false
        panel.allowedContentTypes = format == "image" ? [.png, .jpeg, .heic, .webP] : [.plainText, .utf8PlainText, .png, .jpeg, .heic, .webP]
        panel.begin { response in
            guard response == .OK else { return }
            for url in panel.urls.prefix(4) {
                guard let data = try? Data(contentsOf: url) else { continue }
                let ext = url.pathExtension.lowercased()
                let mime = ["png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "heic": "image/heic", "heif": "image/heif", "webp": "image/webp"][ext] ?? "text/plain"
                if mime.hasPrefix("image/") {
                    if let item = AttachmentNormalizer.image(data, mimeType: mime) { attachments.stage(item) }
                } else if let item = AttachmentNormalizer.text(String(data: data, encoding: .utf8) ?? "") {
                    attachments.stage(item)
                }
            }
        }
    }

    private func setWaveTuning(key: String, value: Double) -> Bool {
        guard value.isFinite else { return false }
        let ranges: [String: ClosedRange<Double>] = [
            "input_floor": -80 ... -30, "input_ceiling": -40 ... 0,
            "output_floor": -60 ... -10, "output_ceiling": -25 ... 0,
            "width": AudioPresentationTuning.waveWidthRange,
        ]
        guard let range = ranges[key], range.contains(value) else { return false }
        let keys = ["input_floor": AudioPresentationTuning.inputFloorKey,
                    "input_ceiling": AudioPresentationTuning.inputCeilingKey,
                    "output_floor": AudioPresentationTuning.outputFloorKey,
                    "output_ceiling": AudioPresentationTuning.outputCeilingKey,
                    "width": AudioPresentationTuning.waveWidthKey]
        guard let defaultsKey = keys[key] else { return false }
        UserDefaults.standard.set(value, forKey: defaultsKey)
        return true
    }
}
