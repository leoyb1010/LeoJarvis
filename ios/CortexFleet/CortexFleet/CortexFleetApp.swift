import SwiftUI
import SwiftData

@main
struct CortexFleetApp: App {
    @StateObject private var env = AppEnvironment()
    @StateObject private var store = FleetStore()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(store)
                .environmentObject(env)
                .environmentObject(env.llmConfig)
                .modelContainer(env.container)
                .onOpenURL { url in
                    store.applyBridgeConfigurationURL(url)
                }
        }
    }
}

struct RootView: View {
    @EnvironmentObject private var store: FleetStore

    var body: some View {
        TabView {
            NavigationStack {
                JarvisHomeView()
            }
            .tabItem {
                Label("总览", systemImage: "sparkles")
            }

            NavigationStack {
                MobileBriefingView()
            }
            .tabItem {
                Label("简报", systemImage: "newspaper")
            }

            NavigationStack {
                MobileNotesView()
            }
            .tabItem {
                Label("记事", systemImage: "note.text")
            }

            NavigationStack {
                FleetDashboardView()
            }
            .tabItem {
                Label("设备", systemImage: "gauge.with.dots.needle.33percent")
            }

            NavigationStack {
                SettingsView()
            }
            .tabItem {
                Label("设置", systemImage: "gearshape")
            }
        }
        .task {
            await store.refreshAll()
        }
    }
}
