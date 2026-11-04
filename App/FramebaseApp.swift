import SwiftUI
import Foundation

@main
struct FramebaseApp: App {
    @State private var container: AppContainer

    init() {
        let appContainer = AppContainer()
        self._container = State(initialValue: appContainer)

        if ProcessInfo.processInfo.environment["FRAMEBASE_INGEST_GOOGLE_INTAKE"] == "1" {
            Task { @MainActor in
                let hscPath = NSString(string: "~/Pictures/HSC Library.framebase").expandingTildeInPath
                let hscURL = URL(fileURLWithPath: hscPath, isDirectory: true)
                await appContainer.openLibrary(at: hscURL)
                let model = LibraryWindowModel(container: appContainer)
                while true {
                    if case .ready = appContainer.libraryState {
                        break
                    }
                    if case .failed(let err) = appContainer.libraryState {
                        fputs("FRAMEBASE_GOOGLE_INTAKE_ERROR: \(err)\n", stderr)
                        exit(1)
                    }
                    try? await Task.sleep(for: .milliseconds(50))
                }
                do {
                    let count = try await model.ingestGoogleStagingFolder()
                    print("FRAMEBASE_GOOGLE_INTAKE_SUCCESS: \(count)")
                    fflush(stdout)
                    exit(0)
                } catch {
                    fputs("FRAMEBASE_GOOGLE_INTAKE_ERROR: \(error)\n", stderr)
                    exit(1)
                }
            }
        }
    }

    var body: some Scene {
        WindowGroup("Framebase", id: "library") {
            LibraryWindowView(container: container)
                .frame(minWidth: 1_100, minHeight: 700)
        }
        .defaultSize(width: 1_440, height: 900)
        .commands {
            FramebaseCommands()
        }

        Settings {
            FramebaseSettingsView(container: container)
        }
    }
}
