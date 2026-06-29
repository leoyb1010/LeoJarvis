import SwiftUI

@main
struct LeoJarvisApp: App {
    @StateObject private var store = JarvisStore()
    @Environment(\.scenePhase) private var scenePhase

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(store)
                .task {
                    await store.bootstrap()
                }
        }
        .onChange(of: scenePhase) { _, phase in
            // 回前台立即重连实时通道（系统挂起时会断开 WS），并补拉一次最新数据。
            if phase == .active {
                store.notify.resumeIfNeeded()
            }
        }
    }
}
