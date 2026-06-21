import SwiftUI

@main
struct LeoJarvisApp: App {
    @StateObject private var store = JarvisStore()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(store)
                .task {
                    await store.bootstrap()
                }
        }
    }
}
