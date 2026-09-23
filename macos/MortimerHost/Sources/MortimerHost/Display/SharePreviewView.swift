import SwiftUI
import AppKit

struct SharePreviewView: View {
    let text: String
    var format: String = "text"
    var data: Data? = nil
    var body: some View {
        ScrollView {
            if format == "png", let data, let image = NSImage(data: data) {
                Image(nsImage: image).resizable().scaledToFit().padding(16)
            } else {
                Text(text).textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading).padding(16)
            }
        }
            .background(AppTheme.bg)
            .navigationTitle("Share preview")
    }
}
