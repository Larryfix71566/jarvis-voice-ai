import SwiftUI
import AppKit

/// 2026-09-05 — the sidecar's graph images (MORTIMER_GRAPH_LAYER_PLAN.md
/// GL11, `/api/graph/<name>/image.png`) are server-side renders whose
/// layout is computed for the requested canvas, and the endpoint has
/// taken `w`/`h` since it shipped — the client just never sent them, so
/// every graph arrived as the 1400×900 default and was scaled down into
/// a 520×400 panel. This view asks for the image at the panel's real
/// pixel size and re-asks when the size settles after a resize.
///
/// Pure URL/size arithmetic lives in `GraphImageURL` so it is unit-tested
/// without a window (MortimerHostTests/GraphImageURLTests).
enum GraphImageURL {
    /// True for the sidecar's GL11 image endpoints only — radar tiles,
    /// basemaps and any other image keep AsyncImage's plain fetch.
    static func isGraphImage(_ url: URL) -> Bool {
        let path = url.path
        return path.contains("/api/graph/")
            && (path.hasSuffix("/image.png") || path.hasSuffix("/image.svg"))
    }

    /// The pixel size to request for a viewport of `viewport` points on a
    /// screen with `scale` backing pixels per point. `reserve` points are
    /// held back for the summary line above the image. Clamped to the
    /// sidecar's own [GRAPH_IMAGE_MIN_PX, GRAPH_IMAGE_MAX_PX] so the
    /// request is never one it would refuse or silently shrink. nil until
    /// the viewport has been measured.
    static func requestSize(
        viewport: CGSize, scale: CGFloat, reserve: CGFloat = 40,
        minPx: Int = AppTuning.graphImageMinPx, maxPx: Int = AppTuning.graphImageMaxPx
    ) -> (w: Int, h: Int)? {
        guard viewport.width >= 1, viewport.height >= 1, scale > 0 else { return nil }
        func px(_ points: CGFloat) -> Int {
            min(maxPx, max(minPx, Int((points * scale).rounded())))
        }
        return (px(viewport.width), px(max(1, viewport.height - reserve)))
    }

    /// `base` with `w`/`h` set to exactly these values — replaced, never
    /// duplicated, every other query item (focus, depth, edge_types,
    /// since) untouched.
    static func sized(_ base: URL, w: Int, h: Int) -> URL {
        guard var components = URLComponents(url: base, resolvingAgainstBaseURL: false) else { return base }
        var items = (components.queryItems ?? []).filter { $0.name != "w" && $0.name != "h" }
        items.append(URLQueryItem(name: "w", value: String(w)))
        items.append(URLQueryItem(name: "h", value: String(h)))
        components.queryItems = items
        return components.url ?? base
    }
}

/// Loads a graph image at the panel's pixel size; holds the current
/// bitmap through a resize and re-requests once the size has settled
/// (AppTuning.graphImageReloadDebounceSeconds), so a drag costs one
/// server render, not one per mouse event — and the picture never blinks
/// to a spinner between sizes.
struct GraphImageView: View {
    let baseURL: URL
    let viewport: CGSize
    let isResizing: Bool

    @State private var image: NSImage?
    @State private var loadedURL: URL?
    @State private var targetURL: URL?
    @State private var failed = false

    private var scale: CGFloat { NSScreen.main?.backingScaleFactor ?? 2 }

    /// Changes whenever the size settles or a resize starts/stops — the
    /// `.task(id:)` below restarts (cancelling its debounce sleep) on
    /// every change, which is the debounce.
    private var settleKey: String {
        "\(Int(viewport.width.rounded()))x\(Int(viewport.height.rounded()))|\(isResizing)"
    }

    var body: some View {
        ZStack {
            if let image {
                Image(nsImage: image)
                    .resizable()
                    .scaledToFit()
                    // Dim slightly while a re-render at the new size is on
                    // its way; full brightness during the drag itself.
                    .opacity(isResizing || loadedURL == targetURL ? 1 : 0.7)
            } else if failed {
                Text("graph image unavailable")
                    .font(.caption)
                    .foregroundStyle(AppTheme.textDim)
                    .padding(20)
            } else {
                ProgressView()
                    .padding(20)
            }
        }
        .frame(maxWidth: .infinity)
        .task(id: settleKey) { await settle() }
        .task(id: targetURL) { await load() }
    }

    /// Decide which URL to show for the current viewport, after the
    /// debounce. First appearance: wait briefly for the first real
    /// measurement so the initial load is already the sized one (one
    /// server render, not the default followed by a re-render).
    private func settle() async {
        if isResizing { return }
        if viewport.width < 1 || viewport.height < 1 {
            if targetURL == nil {
                try? await Task.sleep(nanoseconds: 500_000_000)
                guard !Task.isCancelled, targetURL == nil else { return }
                targetURL = baseURL   // never measured: the sidecar's default size
            }
            return
        }
        try? await Task.sleep(nanoseconds: UInt64(AppTuning.graphImageReloadDebounceSeconds * 1_000_000_000))
        guard !Task.isCancelled,
              let size = GraphImageURL.requestSize(viewport: viewport, scale: scale) else { return }
        let next = GraphImageURL.sized(baseURL, w: size.w, h: size.h)
        if next != targetURL { targetURL = next }
    }

    private func load() async {
        guard let url = targetURL, url != loadedURL else { return }
        do {
            let (data, response) = try await URLSession.shared.data(from: url)
            guard !Task.isCancelled else { return }
            if let http = response as? HTTPURLResponse, !(200...299).contains(http.statusCode) {
                if image == nil { failed = true }
                return
            }
            guard let loaded = NSImage(data: data) else {
                if image == nil { failed = true }
                return
            }
            image = loaded
            loadedURL = url
            failed = false
        } catch {
            guard !Task.isCancelled else { return }
            if image == nil { failed = true }
        }
    }
}
