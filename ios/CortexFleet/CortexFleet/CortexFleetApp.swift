import SwiftUI
import SwiftData

@main
struct CortexFleetApp: App {
    @StateObject private var env = AppEnvironment()
    @StateObject private var store = FleetStore()
    @Environment(\.scenePhase) private var scenePhase

    init() {
        // Register the background refresh task before the app finishes launching.
    }

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
                .task {
                    BackgroundRefresh.shared.register(env: env)
                }
        }
        .onChange(of: scenePhase) { _, phase in
            if phase == .background { BackgroundRefresh.shared.schedule() }
        }
    }
}

struct RootView: View {
    @EnvironmentObject private var store: FleetStore
    @State private var onboarded = UserDefaults.standard.bool(forKey: "onboarding.done")

    var body: some View {
        if !onboarded {
            OnboardingView(done: $onboarded)
        } else {
            mainTabs
        }
    }

    private var mainTabs: some View {
        TabView {
            NavigationStack {
                OverviewView()
            }
            .tabItem {
                Label("总览", systemImage: "sparkles")
            }

            NavigationStack {
                BriefingView()
            }
            .tabItem {
                Label("简报", systemImage: "newspaper")
            }

            NavigationStack {
                NotebookView()
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
        .jarvisFloatingButton()
        .task {
            await store.refreshAll()
        }
    }
}
