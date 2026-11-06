import MortimerPhoneCore
import SwiftUI

@main
struct MortimerPhoneApp: App {
    @State private var previewModel = PhoneAppPreviewModel(
        client: PhoneRemoteOperationsClient(transport: PhonePreviewFakeTransport())
    )

    var body: some Scene {
        WindowGroup {
            PhonePreviewRootView(model: previewModel)
        }
    }
}
